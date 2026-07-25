from __future__ import annotations
import ctypes
import ctypes.wintypes as wintypes
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .base import BackendBase, ExecutionResult
except ImportError:
    from base import BackendBase, ExecutionResult

user32 = ctypes.windll.user32

# ── Virtual key codes ─────────────────────────────────────────────────
KEY_MAP = {
    "ctrl": 0x11, "control": 0x11,
    "shift": 0x10,
    "alt": 0x12, "menu": 0x12,
    "enter": 0x0D, "return": 0x0D,
    "tab": 0x09,
    "escape": 0x1B, "esc": 0x1B,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E, "del": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
    "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79,
    "f11": 0x7A, "f12": 0x7B,
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45,
    "f": 0x46, "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A,
    "k": 0x4B, "l": 0x4C, "m": 0x4D, "n": 0x4E, "o": 0x4F,
    "p": 0x50, "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54,
    "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58, "y": 0x59, "z": 0x5A,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE,
    "/": 0xBF, "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
}

MODIFIER_KEYS = {"ctrl", "control", "shift", "alt", "menu"}

# ── Foreground control ────────────────────────────────────────────────
SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
SPIF_SENDCHANGE = 0x02


def _kill_foreground_lock() -> None:
    """Disable the Windows foreground lock so SetForegroundWindow works from a
    background process. Without this NT8's editor never truly gets keyboard
    focus and F5 is silently dropped."""
    try:
        user32.SystemParametersInfoW(SPI_SETFOREGROUNDLOCKTIMEOUT, 0, ctypes.c_void_p(0), SPIF_SENDCHANGE)
    except Exception:
        pass


def _robust_foreground(hwnd: int) -> bool:
    """Force a window to the foreground using the AttachThreadInput trick.
    Returns True when the window ends up foreground."""
    _kill_foreground_lock()
    try:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        fg = user32.GetForegroundWindow()
        t1 = user32.GetWindowThreadProcessId(fg, 0)
        t2 = user32.GetWindowThreadProcessId(hwnd, 0)
        user32.AttachThreadInput(t1, t2, True)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
        user32.AttachThreadInput(t1, t2, False)
    except Exception:
        return False
    time.sleep(0.35)
    return user32.GetForegroundWindow() == hwnd


def _window_rect(hwnd: int):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


def _click_window_point(hwnd: int, rel_x: float, rel_y: float) -> None:
    """Left click at a relative point inside a window (0..1 fractions)."""
    r = _window_rect(hwnd)
    x = int(r.left + (r.right - r.left) * rel_x)
    y = int(r.top + (r.bottom - r.top) * rel_y)
    user32.SetCursorPos(x, y)
    time.sleep(0.2)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


def _find_windows_by_title(sub: str) -> list[int]:
    out: list[int] = []
    lowered = sub.lower()

    def cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if lowered in buf.value.lower():
                    out.append(hwnd)
        return True

    WP = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WP(cb), 0)
    return out


def _handle_addon_authorization() -> bool:
    """NT8 shows a modal Warning dialog the first time it sees a new or changed
    AddOn: 'NinjaTrader has detected new add on(s) ... Do you wish to authorize
    these add ons?'. It silently blocks compilation until answered. Detect it and
    click Yes. Returns True when a dialog was found and answered."""
    for hwnd in _find_windows_by_title("Warning"):
        if not _robust_foreground(hwnd):
            continue
        # The Yes button sits at the lower left of the two buttons on this dialog.
        _click_window_point(hwnd, 0.80, 0.86)
        time.sleep(0.6)
        return True
    return False


# ── SendInput structures ──────────────────────────────────────────────
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001

EXTENDED_KEYS = {
    0x26, 0x28, 0x25, 0x27,  # arrows
    0x24, 0x23, 0x21, 0x22,  # home/end/pgup/pgdn
    0x2D, 0x2E,              # insert/delete
}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("padding", ctypes.c_byte * 24)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


def _make_key_input(vk: int, up: bool = False) -> INPUT:
    flags = 0
    if up:
        flags |= KEYEVENTF_KEYUP
    if vk in EXTENDED_KEYS:
        flags |= KEYEVENTF_EXTENDEDKEY

    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki.wVk = vk
    inp.ki.wScan = user32.MapVirtualKeyW(vk, 0)
    inp.ki.dwFlags = flags
    inp.ki.time = 0
    inp.ki.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
    return inp


def _send_key_combo(keys: list[int]):
    """Press all keys down (modifiers first), then release in reverse."""
    inputs = []
    for vk in keys:
        inputs.append(_make_key_input(vk, up=False))
    for vk in reversed(keys):
        inputs.append(_make_key_input(vk, up=True))

    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(INPUT))


def _send_key_hold(vk: int, hold_ms: int = 80):
    """Press a single key with a real hold between key down and key up. WPF
    KeyBindings (such as NT8's F5 compile) ignore a zero duration press, so a
    batched down plus up in one SendInput call gets dropped. Holding the key for
    a few dozen milliseconds makes the compile hotkey register reliably. Uses
    keybd_event with a scan code, which reaches NT8's WPF hotkey handler where a
    plain SendInput virtual key does not."""
    scan = user32.MapVirtualKeyW(vk, 0)
    user32.keybd_event(vk, scan, 0, 0)
    time.sleep(max(0, hold_ms) / 1000.0)
    user32.keybd_event(vk, scan, 2, 0)  # KEYEVENTF_KEYUP


def _type_string(text: str, delay_ms: int = 20):
    """Type a string character by character."""
    for ch in text:
        lower = ch.lower()
        if lower in KEY_MAP:
            vk = KEY_MAP[lower]
            needs_shift = ch.isupper() or ch in '~!@#$%^&*()_+{}|:"<>?'
            inputs = []
            if needs_shift:
                inputs.append(_make_key_input(0x10, up=False))
            inputs.append(_make_key_input(vk, up=False))
            inputs.append(_make_key_input(vk, up=True))
            if needs_shift:
                inputs.append(_make_key_input(0x10, up=True))
            n = len(inputs)
            arr = (INPUT * n)(*inputs)
            user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(INPUT))
        else:
            # Use VkKeyScan for unmapped characters
            vk_scan = user32.VkKeyScanW(ord(ch))
            if vk_scan != -1:
                vk = vk_scan & 0xFF
                shift_state = (vk_scan >> 8) & 0xFF
                inputs = []
                if shift_state & 1:
                    inputs.append(_make_key_input(0x10, up=False))
                if shift_state & 2:
                    inputs.append(_make_key_input(0x11, up=False))
                if shift_state & 4:
                    inputs.append(_make_key_input(0x12, up=False))
                inputs.append(_make_key_input(vk, up=False))
                inputs.append(_make_key_input(vk, up=True))
                if shift_state & 4:
                    inputs.append(_make_key_input(0x12, up=True))
                if shift_state & 2:
                    inputs.append(_make_key_input(0x11, up=True))
                if shift_state & 1:
                    inputs.append(_make_key_input(0x10, up=True))
                n = len(inputs)
                arr = (INPUT * n)(*inputs)
                user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(INPUT))

        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)


def _parse_key_combo(keys_str: str) -> list[int]:
    """Parse 'ctrl+shift+n' into list of VK codes, modifiers first."""
    parts = [p.strip().lower() for p in keys_str.split("+")]
    modifiers = []
    regulars = []
    for p in parts:
        if p in MODIFIER_KEYS:
            modifiers.append(KEY_MAP[p])
        elif p in KEY_MAP:
            regulars.append(KEY_MAP[p])
        else:
            raise ValueError(f"Unknown key: '{p}'")
    return modifiers + regulars


# ── pure helpers (no win32 calls, unit testable) ────────────────────────

def _match_window_by_title(
    windows: list[tuple[int, str]], title_contains: str | None
) -> tuple[int, str] | None:
    """Given a list of (hwnd, title) pairs, find the first whose title contains
    title_contains (case insensitive). If title_contains is falsy, return the
    first window. Returns None if no window matches."""
    if not windows:
        return None
    if not title_contains:
        return windows[0]
    lowered = title_contains.lower()
    for hwnd, title in windows:
        if lowered in title.lower():
            return (hwnd, title)
    return None


def _is_chart_title(title: str) -> bool:
    """True for windows that are plausibly NT8 chart windows: not the Control
    Center, not the NinjaScript Editor, not the Strategy Analyzer."""
    lowered = title.lower()
    if "control center" in lowered:
        return False
    if "ninjascript editor" in lowered:
        return False
    if "strategy analyzer" in lowered:
        return False
    return True


def _pick_chart_window(
    windows: list[tuple[int, str]], title_contains: str | None
) -> tuple[int, str] | None:
    """Pick a chart window: honor an explicit title_contains filter, else pick
    the first non Control Center, non Editor, non Strategy Analyzer window."""
    if title_contains:
        return _match_window_by_title(windows, title_contains)
    for hwnd, title in windows:
        if _is_chart_title(title):
            return (hwnd, title)
    return None


_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _substitute_placeholders(text: str, context: dict) -> str:
    """Replace {name} tokens in text with values from context. Missing keys
    resolve to an empty string."""
    def repl(match: re.Match) -> str:
        val = context.get(match.group(1))
        return "" if val is None else str(val)
    return _PLACEHOLDER_RE.sub(repl, text)


def _normalize_steps(steps: list[dict] | None, defaults: list[dict]) -> list[dict]:
    """Validate a configure_tester step list. Falls back to defaults when
    steps is None. Raises ValueError on a malformed step (never silently
    drops one)."""
    if steps is None:
        return list(defaults)
    normalized = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"Step {i} is not an object: {step!r}")
        if "keys" not in step and "text" not in step and "wait_ms" not in step:
            raise ValueError(f"Step {i} must contain one of: keys, text, wait_ms. Got: {step!r}")
        normalized.append(step)
    return normalized


def _get_mtime_iso(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _newest_trace_file(trace_dir: Path) -> Path | None:
    if not trace_dir.exists():
        return None
    files = sorted(trace_dir.glob("trace.*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


# Default configure_tester step sequence. The orchestrator can override this
# entirely by passing args["steps"], and each step is one of:
#   {"keys": "tab"}          send a key combo
#   {"text": "{strategy}"}   type text, with {name} placeholders resolved from
#                            args (strategy, instrument, from_date, to_date);
#                            a step whose resolved text is empty is skipped
#   {"wait_ms": 300}         pause only
# "description" and "wait_ms" may be combined with "keys" or "text" to pause
# after that step. This sequence encodes the best known 8.1 Strategy Analyzer
# tab order (unconfirmed) and is meant to be tuned live.
TESTER_CONFIG_STEPS: list[dict] = [
    {"keys": "tab", "description": "Tab from the Strategy Analyzer toolbar into the strategy filter box", "wait_ms": 200},
    {"text": "{strategy}", "description": "Type the strategy name into the filter box (skipped if not provided)", "wait_ms": 300},
    {"keys": "enter", "description": "Confirm the filtered strategy selection", "wait_ms": 300},
]


class KeyboardBackend(BackendBase):
    name = "keyboard"

    def is_available(self) -> bool:
        import os
        return os.name == "nt"

    def execute(self, action: str, args: dict[str, Any]) -> ExecutionResult:
        dispatch = {
            "send_keys": self._send_keys,
            "type_text": self._type_text,
            "compile": self._compile,
            "open_chart": self._open_chart,
            "switch_instrument": self._switch_instrument,
            "switch_timeframe": self._switch_timeframe,
            "open_tester": self._open_tester,
            "configure_tester": self._configure_tester,
            "start_tester": self._start_tester,
            "toggle_autotrading": self._toggle_autotrading,
            "close_chart": self._close_chart,
        }
        handler = dispatch.get(action)
        if handler is None:
            return ExecutionResult(success=False, driver=self.name, stderr=f"Unknown action '{action}'")
        try:
            return handler(args)
        except Exception as exc:
            return ExecutionResult(success=False, driver=self.name, stderr=str(exc))

    # ── helpers ────────────────────────────────────────────────────────

    def _ensure_nt8_focus(self, title_hint: str = "") -> int | None:
        """Try to focus an NT8 window. Returns hwnd or None."""
        from .win32_capture import _find_nt8_windows, _get_window_title, SW_RESTORE
        handles = _find_nt8_windows()
        if not handles:
            return None

        target = handles[0]
        if title_hint:
            for h in handles:
                if title_hint.lower() in _get_window_title(h).lower():
                    target = h
                    break

        user32.ShowWindow(target, SW_RESTORE)
        user32.SetForegroundWindow(target)
        time.sleep(0.15)
        return target

    def _focus_hwnd(self, hwnd: int) -> bool:
        """Focus a specific window handle (not just any NT8 window). Uses the
        foreground lock override so focus actually sticks from a background
        process. Retries a few times because a single attempt can lose a race
        with the previously foreground window. Returns True when focused."""
        for _ in range(5):
            if _robust_foreground(hwnd):
                return True
            time.sleep(0.3)
        # fall back to a plain attempt
        from .win32_capture import SW_RESTORE
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.15)
        return user32.GetForegroundWindow() == hwnd

    def _nt8_data_dir(self) -> Path:
        docs = Path.home() / "Documents" / "NinjaTrader 8"
        if docs.exists():
            return docs
        onedrive = Path.home() / "OneDrive" / "Documents" / "NinjaTrader 8"
        if onedrive.exists():
            return onedrive
        return docs

    # ── actions ────────────────────────────────────────────────────────

    def _send_keys(self, args: dict) -> ExecutionResult:
        keys_str: str = args["keys"]
        delay_ms: int = int(args.get("delay_ms", 50))

        # Support multiple combos separated by space: "ctrl+shift+n enter"
        combos = keys_str.strip().split()
        for combo in combos:
            vk_list = _parse_key_combo(combo)
            _send_key_combo(vk_list)
            if delay_ms > 0 and combo != combos[-1]:
                time.sleep(delay_ms / 1000.0)

        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Sent keys: {keys_str}",
            metadata={"keys": keys_str},
        )

    def _type_text(self, args: dict) -> ExecutionResult:
        text: str = args["text"]
        delay_ms: int = int(args.get("delay_ms", 20))
        _type_string(text, delay_ms)
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Typed {len(text)} characters",
            metadata={"text": text},
        )

    def _compile(self, args: dict) -> ExecutionResult:
        from .win32_capture import _find_nt8_windows_with_titles

        timeout_seconds = float(args.get("timeout_seconds", 120))
        nt8_root = self._nt8_data_dir()
        dll_path = nt8_root / "bin" / "Custom" / "NinjaTrader.Custom.dll"
        trace_dir = nt8_root / "trace"

        dll_mtime_before = _get_mtime_iso(dll_path)
        trace_file = _newest_trace_file(trace_dir)
        trace_offset = trace_file.stat().st_size if trace_file is not None else 0

        start = time.time()

        windows = _find_nt8_windows_with_titles()
        editor = _match_window_by_title(windows, "NinjaScript Editor")
        if editor is None:
            control_center = _match_window_by_title(windows, "Control Center")
            if control_center is None:
                return ExecutionResult(
                    success=False, driver=self.name,
                    stderr="EDITOR_NOT_OPEN: no NinjaScript Editor or Control Center window found",
                    metadata={
                        "error_code": "EDITOR_NOT_OPEN",
                        "remediation": "Start NinjaTrader and log in, then retry compile.",
                    },
                )
            self._focus_hwnd(control_center[0])
            _send_key_combo(_parse_key_combo("ctrl+n"))
            time.sleep(2.0)
            windows = _find_nt8_windows_with_titles()
            editor = _match_window_by_title(windows, "NinjaScript Editor")

        if editor is None:
            return ExecutionResult(
                success=False, driver=self.name,
                stderr="EDITOR_NOT_OPEN: could not open a NinjaScript Editor window",
                metadata={
                    "error_code": "EDITOR_NOT_OPEN",
                    "remediation": "Manually open the NinjaScript Editor (Tools > Edit NinjaScript, or Ctrl+N from Control Center), then retry compile.",
                },
            )

        hwnd, title = editor
        self._focus_hwnd(hwnd)
        # Click into the code area so the editor text pane holds keyboard focus,
        # then send F5. NT8 only compiles when the editor pane is truly focused.
        _click_window_point(hwnd, 0.3, 0.4)
        time.sleep(0.3)
        self._focus_hwnd(hwnd)
        _send_key_hold(0x74, hold_ms=80)  # F5 with a real hold so the compile hotkey registers

        # A freshly deployed or changed AddOn triggers a modal Warning dialog that
        # blocks the compile until authorized. Answer it if it appears.
        authorized = False

        trace_lines: list[str] = []
        errors: list[str] = []
        success = False
        resent = False
        resent_at = 0.0
        deadline = start + timeout_seconds

        while time.time() < deadline:
            time.sleep(1.0)

            if not authorized and _handle_addon_authorization():
                authorized = True

            # If nothing has happened after 10 seconds, the F5 keystroke may have
            # been dropped by a focus race. Re-focus and send it once more.
            if not resent and not authorized and (time.time() - start) > 10 and _get_mtime_iso(dll_path) == dll_mtime_before:
                resent = True
                resent_at = time.time()
                self._focus_hwnd(hwnd)
                _click_window_point(hwnd, 0.3, 0.4)
                time.sleep(0.3)
                self._focus_hwnd(hwnd)
                _send_key_hold(0x74, hold_ms=80)

            # A successful compile writes the new assembly within a few seconds.
            # Once we have resent F5 and given it a generous window with no dll
            # change, conclude early rather than waiting out the full timeout: NT8
            # produces no on disk signal for a failed compile.
            if resent and (time.time() - resent_at) > 15 and _get_mtime_iso(dll_path) == dll_mtime_before:
                break

            current_trace_file = _newest_trace_file(trace_dir)
            if current_trace_file is not None:
                if current_trace_file != trace_file:
                    trace_file = current_trace_file
                    trace_offset = 0
                try:
                    with open(trace_file, "r", encoding="utf-8", errors="replace") as fh:
                        fh.seek(trace_offset)
                        chunk = fh.read()
                        trace_offset = fh.tell()
                except OSError:
                    chunk = ""
                new_lines = [l for l in chunk.splitlines() if l.strip()]
                trace_lines.extend(new_lines)
                for line in new_lines:
                    if "unable to compile" in line.lower():
                        errors.append(line)

            if _get_mtime_iso(dll_path) != dll_mtime_before and dll_path.exists():
                success = True
                break
            if errors:
                break

        duration_ms = int((time.time() - start) * 1000)
        dll_mtime_after = _get_mtime_iso(dll_path)

        base_metadata = {
            "success": success,
            "duration_ms": duration_ms,
            "dll_mtime_before": dll_mtime_before,
            "dll_mtime_after": dll_mtime_after,
            "trace_lines": trace_lines,
            "errors": errors,
            "hwnd": int(hwnd) if hwnd is not None else None,
            "editor_title": title,
            "addon_authorized": authorized,
        }

        if success:
            return ExecutionResult(
                success=True, driver=self.name,
                stdout=f"Compile succeeded: NinjaTrader.Custom.dll mtime changed after {duration_ms}ms",
                metadata=base_metadata,
            )
        if errors:
            base_metadata["error_code"] = "COMPILE_FAILED"
            return ExecutionResult(
                success=False, driver=self.name,
                stderr="COMPILE_FAILED: " + "; ".join(errors),
                metadata=base_metadata,
            )
        # No new assembly appeared. NT8's F5 compile writes nothing to disk on
        # failure (it silently restores the previous dll), so the honest reading
        # is: the compile produced no new assembly. This almost always means a
        # compile error. Capture the editor as visual evidence of the Errors panel,
        # since NT8 exposes the error detail only in that panel, not in any file.
        screenshot_path = None
        try:
            from .win32_capture import _capture_hwnd_to_file
            screenshot_path = _capture_hwnd_to_file(hwnd, "compile_no_new_assembly")
        except Exception:
            screenshot_path = None
        base_metadata["error_code"] = "COMPILE_NO_NEW_ASSEMBLY"
        base_metadata["screenshot"] = screenshot_path
        artifacts = [screenshot_path] if screenshot_path else []
        return ExecutionResult(
            success=False, driver=self.name,
            artifacts=artifacts,
            stderr=(
                "COMPILE_NO_NEW_ASSEMBLY: no new NinjaTrader.Custom.dll was produced within "
                f"{timeout_seconds}s. NT8 restores the previous assembly on a failed compile and "
                "writes nothing to disk, so this means the compile most likely failed. Open the "
                "NinjaScript Editor Errors panel (see the captured screenshot) for the error detail, "
                "fix the code, and recompile."
            ),
            metadata=base_metadata,
        )

    def _open_chart(self, args: dict) -> ExecutionResult:
        instrument: str = args.get("symbol", args.get("instrument", "ES 09-25"))
        hwnd = self._ensure_nt8_focus("Control Center")
        if hwnd is None:
            return ExecutionResult(success=False, driver=self.name, stderr="NinjaTrader Control Center not found")

        # File > New > Chart or Ctrl+Shift+N (from some NT8 versions)
        # Standard: Click on "New" menu. Safer to just use Ctrl+Shift+N
        _send_key_combo(_parse_key_combo("ctrl+shift+n"))
        time.sleep(1.5)

        # Type instrument name and press Enter
        _type_string(instrument, delay_ms=30)
        time.sleep(0.3)
        _send_key_combo(_parse_key_combo("enter"))
        time.sleep(0.5)

        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Opened new chart for {instrument}",
            metadata={"instrument": instrument},
        )

    def _switch_instrument(self, args: dict) -> ExecutionResult:
        instrument: str = args.get("symbol", args.get("instrument", ""))
        title_hint: str = args.get("chart_title", "Chart")

        hwnd = self._ensure_nt8_focus(title_hint)
        if hwnd is None:
            return ExecutionResult(success=False, driver=self.name, stderr="No chart window found")

        # Click instrument box (typically can just type when chart is focused)
        # In NT8, typing in the instrument field when the chart is focused
        _type_string(instrument, delay_ms=30)
        time.sleep(0.3)
        _send_key_combo(_parse_key_combo("enter"))

        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Switched instrument to {instrument}",
            metadata={"instrument": instrument},
        )

    def _switch_timeframe(self, args: dict) -> ExecutionResult:
        period: str = args.get("period", "5")
        period_type: str = args.get("period_type", "m")  # m=minute, d=day, w=week
        title_hint: str = args.get("chart_title", "Chart")

        hwnd = self._ensure_nt8_focus(title_hint)
        if hwnd is None:
            return ExecutionResult(success=False, driver=self.name, stderr="No chart window found")

        # Type period in the timeframe box
        text = f"{period}{period_type}"
        _type_string(text, delay_ms=30)
        time.sleep(0.3)
        _send_key_combo(_parse_key_combo("enter"))

        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Switched timeframe to {text}",
            metadata={"period": period, "period_type": period_type},
        )

    def _open_tester(self, args: dict) -> ExecutionResult:
        from .win32_capture import _find_nt8_windows_with_titles
        # The Strategy Analyzer opens from the Control Center New menu. The Ctrl+R
        # hotkey is not bound to it in a default NT8 config (it is the chart
        # crosshair), so we drive the menu and then verify the window appeared
        # rather than reporting a blind success.
        already = _match_window_by_title(_find_nt8_windows_with_titles(), "Strategy Analyzer")
        if already is not None:
            return ExecutionResult(
                success=True, driver=self.name,
                stdout="Strategy Analyzer already open",
                metadata={"hwnd": int(already[0])},
            )

        windows = _find_nt8_windows_with_titles()
        cc = _match_window_by_title(windows, "Control Center")
        if cc is None:
            return ExecutionResult(success=False, driver=self.name, stderr="NinjaTrader Control Center not found")

        cc_hwnd = cc[0]
        self._focus_hwnd(cc_hwnd)
        # Open the New menu, then click the Strategy Analyzer item. The item sits
        # at a stable fraction of the Control Center window in the New dropdown.
        # Note: opening a WPF menu via a synthetic click from a background process
        # is inherently unreliable, which is why this command verifies the window
        # appeared and returns an honest failure with coordinate overrides rather
        # than a blind success. When it fails, open the analyzer manually once (it
        # persists in the workspace) or pass tuned menu coordinates.
        new_rel_x = float(args.get("menu_rel_x", 0.145))
        new_rel_y = float(args.get("menu_rel_y", 0.016))
        _click_window_point(cc_hwnd, new_rel_x, new_rel_y)
        time.sleep(0.8)
        item_rel_y = float(args.get("menu_item_rel_y", 0.642))
        item_rel_x = float(args.get("menu_item_rel_x", 0.162))
        _click_window_point(cc_hwnd, item_rel_x, item_rel_y)

        deadline = time.time() + 8
        analyzer = None
        while time.time() < deadline:
            time.sleep(0.7)
            analyzer = _match_window_by_title(_find_nt8_windows_with_titles(), "Strategy Analyzer")
            if analyzer is not None:
                break

        if analyzer is None:
            return ExecutionResult(
                success=False, driver=self.name,
                stderr="ANALYZER_NOT_OPEN: opened the New menu but no Strategy Analyzer window appeared. The menu item position may differ on this screen. Open it manually via Control Center New menu then Strategy Analyzer, or pass menu_item_rel_x and menu_item_rel_y.",
                metadata={"error_code": "ANALYZER_NOT_OPEN"},
            )
        return ExecutionResult(
            success=True, driver=self.name,
            stdout="Opened Strategy Analyzer",
            metadata={"hwnd": int(analyzer[0])},
        )

    def _configure_tester(self, args: dict) -> ExecutionResult:
        from .win32_capture import _find_nt8_windows_with_titles, Win32CaptureBackend

        windows = _find_nt8_windows_with_titles()
        analyzer = _match_window_by_title(windows, "Strategy Analyzer")
        if analyzer is None:
            return ExecutionResult(
                success=False, driver=self.name,
                stderr="ANALYZER_NOT_OPEN: no Strategy Analyzer window found",
                metadata={
                    "error_code": "ANALYZER_NOT_OPEN",
                    "remediation": "Open the Strategy Analyzer (tester.open sends Ctrl+R) before calling configure_tester.",
                },
            )

        hwnd, title = analyzer
        self._focus_hwnd(hwnd)

        try:
            steps = _normalize_steps(args.get("steps"), TESTER_CONFIG_STEPS)
        except ValueError as exc:
            return ExecutionResult(success=False, driver=self.name, stderr=str(exc))

        context = {
            "strategy": args.get("strategy", ""),
            "instrument": args.get("instrument", ""),
            "from_date": args.get("from_date", ""),
            "to_date": args.get("to_date", ""),
        }

        executed: list[dict] = []
        for step in steps:
            record = dict(step)
            if "keys" in step:
                _send_key_combo(_parse_key_combo(step["keys"]))
            if "text" in step:
                resolved = _substitute_placeholders(step["text"], context)
                if resolved:
                    _type_string(resolved, delay_ms=20)
                    record["resolved_text"] = resolved
                else:
                    record["skipped"] = True
                    record["reason"] = "empty resolved text"
            wait_ms = step.get("wait_ms")
            if wait_ms:
                time.sleep(int(wait_ms) / 1000.0)
            executed.append(record)

        screenshot_path = None
        try:
            capture = Win32CaptureBackend()
            capture_result = capture.execute("capture_window", {"hwnd": hwnd})
            if capture_result.success:
                screenshot_path = capture_result.metadata.get("path")
        except Exception:
            screenshot_path = None

        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Executed {len(executed)} configure step(s) against focused Strategy Analyzer window",
            metadata={
                "verified": False,
                "note": "Steps executed against a focused Strategy Analyzer window. This does not confirm the backtest was configured correctly; completion and results are verified separately via analyzer_status/analyzer_results after tester.start.",
                "hwnd": hwnd,
                "title": title,
                "steps_executed": executed,
                "screenshot_path": screenshot_path,
            },
        )

    def _start_tester(self, args: dict) -> ExecutionResult:
        from .win32_capture import _find_nt8_windows_with_titles

        windows = _find_nt8_windows_with_titles()
        analyzer = _match_window_by_title(windows, "Strategy Analyzer")
        if analyzer is None:
            return ExecutionResult(
                success=False, driver=self.name,
                stderr="ANALYZER_NOT_OPEN: no Strategy Analyzer window found",
                metadata={
                    "error_code": "ANALYZER_NOT_OPEN",
                    "remediation": "Open the Strategy Analyzer (tester.open sends Ctrl+R) before calling start_tester.",
                },
            )

        hwnd, title = analyzer
        self._focus_hwnd(hwnd)
        key = args.get("key", "f5")
        _send_key_combo(_parse_key_combo(key))

        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Sent '{key}' to focused Strategy Analyzer window to trigger the backtest run",
            metadata={
                "verified": False,
                "note": "Run triggered on a focused Strategy Analyzer window. Completion is detected via analyzer_status, not by this call.",
                "hwnd": hwnd,
                "title": title,
                "key": key,
            },
        )

    def _close_chart(self, args: dict) -> ExecutionResult:
        from .win32_capture import _find_nt8_windows_with_titles

        title_contains = args.get("title_contains")
        windows = _find_nt8_windows_with_titles()
        target = _pick_chart_window(windows, title_contains)
        if target is None:
            return ExecutionResult(
                success=False, driver=self.name,
                stderr="No matching NT8 chart window found",
                metadata={"error_code": "CHART_NOT_FOUND"},
            )

        hwnd, title = target
        self._focus_hwnd(hwnd)
        _send_key_combo(_parse_key_combo("ctrl+w"))

        deadline = time.time() + 3.0
        gone = False
        while time.time() < deadline:
            time.sleep(0.2)
            current = _find_nt8_windows_with_titles()
            if not any(h == hwnd for h, _ in current):
                gone = True
                break

        return ExecutionResult(
            success=gone, driver=self.name,
            stdout=f"Closed chart window: {title}" if gone else f"Chart window still present after ctrl+w: {title}",
            stderr="" if gone else "CHART_CLOSE_TIMEOUT: window handle still present 3s after ctrl+w",
            metadata={"hwnd": hwnd, "title": title, "closed": gone},
        )

    def _toggle_autotrading(self, args: dict) -> ExecutionResult:
        hwnd = self._ensure_nt8_focus("")
        if hwnd is None:
            return ExecutionResult(success=False, driver=self.name, stderr="NinjaTrader not found")

        # Ctrl+E toggles autotrading
        _send_key_combo(_parse_key_combo("ctrl+e"))
        time.sleep(0.3)

        return ExecutionResult(
            success=True, driver=self.name,
            stdout="Toggled autotrading (Ctrl+E sent)",
        )
