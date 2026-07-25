from __future__ import annotations
import ctypes
import ctypes.wintypes as wintypes
import os
import struct
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from .base import BackendBase, ExecutionResult
except ImportError:
    from base import BackendBase, ExecutionResult

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
gdi32 = ctypes.windll.gdi32

# ── Win32 constants ───────────────────────────────────────────────────
SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SW_RESTORE = 9
SW_SHOW = 5
SW_HIDE = 0
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_SHOWWINDOW = 0x0040
SRCCOPY = 0x00CC0020
PW_RENDERFULLCONTENT = 2
DIB_RGB_COLORS = 0
BI_RGB = 0
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
TH32CS_SNAPPROCESS = 0x00000002

# ── ctypes setup ──────────────────────────────────────────────────────
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


NT8_EXE = "NinjaTrader.exe"
NT8_DEFAULT_PATH = r"C:\Program Files\NinjaTrader 8\bin\NinjaTrader.exe"


def _find_nt8_pids() -> list[int]:
    pids = []
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return pids
    try:
        pe = PROCESSENTRY32()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if kernel32.Process32First(snap, ctypes.byref(pe)):
            while True:
                name = pe.szExeFile.decode("utf-8", errors="replace").lower()
                if name == NT8_EXE.lower():
                    pids.append(pe.th32ProcessID)
                if not kernel32.Process32Next(snap, ctypes.byref(pe)):
                    break
    finally:
        kernel32.CloseHandle(snap)
    return pids


def _find_nt8_windows() -> list[int]:
    """Return list of NT8 window handles."""
    nt8_pids = set(_find_nt8_pids())
    if not nt8_pids:
        return []

    handles = []
    pid_out = wintypes.DWORD()

    @WNDENUMPROC
    def callback(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_out))
            if pid_out.value in nt8_pids:
                handles.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return handles


def _get_window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _find_nt8_windows_with_titles() -> list[tuple[int, str]]:
    """Same window set as _find_nt8_windows, paired with their titles.
    Kept separate from _find_nt8_windows for backward compatibility."""
    handles = _find_nt8_windows()
    return [(h, _get_window_title(h)) for h in handles]


def _capture_hwnd_to_file(hwnd: int, tag: str = "capture") -> str | None:
    """Capture a single window handle to a PNG under the NT8 captures dir and
    return the absolute path. Module level so other backends (keyboard) can grab
    visual evidence without holding a backend instance. Returns None on failure."""
    if not hwnd or not user32.IsWindow(hwnd):
        return None
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None

    hwnd_dc = user32.GetDC(hwnd)
    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
    old_bmp = gdi32.SelectObject(mem_dc, bitmap)
    if not user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT):
        gdi32.BitBlt(mem_dc, 0, 0, width, height, hwnd_dc, 0, 0, SRCCOPY)

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB
    buf = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
    gdi32.SelectObject(mem_dc, old_bmp)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, hwnd_dc)

    captures_dir = Path.home() / "Documents" / "NinjaTrader 8" / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in str(tag))[:50]
    ts = int(time.time() * 1000)
    try:
        from PIL import Image
        img = Image.frombytes("RGBX", (width, height), buf.raw).convert("RGB")
        r, g, b = img.split()
        img = Image.merge("RGB", (b, g, r))
        out_path = captures_dir / f"{safe}_{ts}.png"
        img.save(str(out_path), "PNG")
        return str(out_path)
    except Exception:
        return None


def _sample_blank_ratio(bgra_data: bytes, width: int, height: int, sample_stride: int = 7) -> float:
    """Sample every Nth pixel and return the fraction that share the single
    most common sampled value. A high ratio suggests a blank/solid capture."""
    total_pixels = width * height
    if total_pixels == 0:
        return 0.0
    pixel_size = 4
    from collections import Counter
    counts: Counter = Counter()
    sampled = 0
    for idx in range(0, total_pixels, sample_stride):
        offset = idx * pixel_size
        pixel = bgra_data[offset:offset + pixel_size]
        if len(pixel) < pixel_size:
            continue
        counts[pixel] += 1
        sampled += 1
    if sampled == 0:
        return 0.0
    most_common = counts.most_common(1)[0][1]
    return most_common / sampled


class Win32CaptureBackend(BackendBase):
    name = "win32"

    def __init__(self):
        self._captures_dir = Path.home() / "Documents" / "NinjaTrader 8" / "captures"

    def is_available(self) -> bool:
        return os.name == "nt"

    def execute(self, action: str, args: dict[str, Any]) -> ExecutionResult:
        dispatch = {
            "detect_process": self._detect_process,
            "launch_process": self._launch_process,
            "kill_process": self._kill_process,
            "focus_window": self._focus_window,
            "capture_window": self._capture_window,
            "arrange_window": self._arrange_window,
            "window_state": self._window_state,
            "list_windows": self._list_windows,
        }
        handler = dispatch.get(action)
        if handler is None:
            return ExecutionResult(success=False, driver=self.name, stderr=f"Unknown action '{action}'")
        try:
            return handler(args)
        except Exception as exc:
            return ExecutionResult(success=False, driver=self.name, stderr=str(exc))

    # ── actions ────────────────────────────────────────────────────────

    def _detect_process(self, args: dict) -> ExecutionResult:
        pids = _find_nt8_pids()
        running = len(pids) > 0
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"NinjaTrader {'running' if running else 'not running'} (PIDs: {pids})",
            metadata={"running": running, "pids": pids},
        )

    def _launch_process(self, args: dict) -> ExecutionResult:
        exe_path = args.get("path", NT8_DEFAULT_PATH)
        if not Path(exe_path).exists():
            return ExecutionResult(success=False, driver=self.name, stderr=f"NinjaTrader not found at {exe_path}")

        existing = _find_nt8_pids()
        if existing:
            return ExecutionResult(
                success=True, driver=self.name,
                stdout=f"NinjaTrader already running (PIDs: {existing})",
                metadata={"already_running": True, "pids": existing},
            )

        proc = subprocess.Popen(
            [exe_path],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Launched NinjaTrader (PID: {proc.pid})",
            metadata={"pid": proc.pid},
        )

    def _kill_process(self, args: dict) -> ExecutionResult:
        pids = _find_nt8_pids()
        if not pids:
            return ExecutionResult(success=True, driver=self.name, stdout="NinjaTrader not running")

        force = args.get("force", False)
        flag = "/F " if force else ""
        result = subprocess.run(
            f"taskkill {flag}/IM {NT8_EXE}",
            shell=True, capture_output=True, text=True,
        )
        return ExecutionResult(
            success=result.returncode == 0,
            driver=self.name,
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
        )

    def _focus_window(self, args: dict) -> ExecutionResult:
        title_filter = args.get("title", "").lower()
        handles = _find_nt8_windows()

        if not handles:
            return ExecutionResult(success=False, driver=self.name, stderr="No NinjaTrader windows found")

        target = None
        if title_filter:
            for h in handles:
                if title_filter in _get_window_title(h).lower():
                    target = h
                    break
        if target is None:
            target = handles[0]

        user32.ShowWindow(target, SW_RESTORE)
        user32.SetForegroundWindow(target)
        title = _get_window_title(target)

        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Focused window: {title}",
            metadata={"hwnd": target, "title": title},
        )

    def _capture_window(self, args: dict) -> ExecutionResult:
        hwnd_arg = args.get("hwnd")
        if hwnd_arg:
            target = int(hwnd_arg)
            if not user32.IsWindow(target):
                return ExecutionResult(success=False, driver=self.name, stderr=f"hwnd {target} is not a valid window")
        else:
            title_filter = (args.get("title_contains") or args.get("title", "")).lower()
            handles = _find_nt8_windows()

            if not handles:
                return ExecutionResult(success=False, driver=self.name, stderr="No NinjaTrader windows found")

            target = None
            if title_filter:
                for h in handles:
                    if title_filter in _get_window_title(h).lower():
                        target = h
                        break
            if target is None:
                target = handles[0]

        # Get window dimensions
        rect = wintypes.RECT()
        user32.GetWindowRect(target, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top

        if width <= 0 or height <= 0:
            return ExecutionResult(success=False, driver=self.name, stderr="Window has zero dimensions")

        # Create device contexts and bitmap
        hwnd_dc = user32.GetDC(target)
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
        old_bmp = gdi32.SelectObject(mem_dc, bitmap)

        # PrintWindow for background-safe capture
        result = user32.PrintWindow(target, mem_dc, PW_RENDERFULLCONTENT)
        if not result:
            # Fallback to BitBlt
            gdi32.BitBlt(mem_dc, 0, 0, width, height, hwnd_dc, 0, 0, SRCCOPY)

        # Read bitmap bits
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height  # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB

        buf_size = width * height * 4
        buf = ctypes.create_string_buffer(buf_size)
        gdi32.GetDIBits(mem_dc, bitmap, 0, height, buf, ctypes.byref(bmi), DIB_RGB_COLORS)

        # Cleanup GDI
        gdi32.SelectObject(mem_dc, old_bmp)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(target, hwnd_dc)

        blank_ratio = _sample_blank_ratio(buf.raw, width, height)
        possibly_blank = blank_ratio > 0.97

        # Try Pillow first for PNG, fall back to BMP
        self._captures_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        title = _get_window_title(target)
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)[:50]

        try:
            from PIL import Image
            img = Image.frombytes("RGBX", (width, height), buf.raw)
            img = img.convert("RGB")
            # BGRA -> RGB swap (Windows bitmaps are BGRA)
            r, g, b = img.split()
            img = Image.merge("RGB", (b, g, r))
            filename = f"{safe_title}_{ts}.png"
            out_path = self._captures_dir / filename
            img.save(str(out_path), "PNG")
        except ImportError:
            # Write raw BMP
            filename = f"{safe_title}_{ts}.bmp"
            out_path = self._captures_dir / filename
            self._write_bmp(out_path, width, height, buf.raw)

        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Captured window to {out_path}",
            artifacts=[str(out_path)],
            metadata={
                "path": str(out_path),
                "width": width,
                "height": height,
                "title": title,
                "possibly_blank": possibly_blank,
                "blank_sample_ratio": round(blank_ratio, 4),
            },
        )

    def _write_bmp(self, path: Path, width: int, height: int, bgra_data: bytes):
        row_size = width * 4
        padded_row = (row_size + 3) & ~3
        pixel_size = padded_row * height
        file_size = 54 + pixel_size

        with open(path, "wb") as f:
            # BMP file header (14 bytes)
            f.write(b"BM")
            f.write(struct.pack("<I", file_size))
            f.write(struct.pack("<HH", 0, 0))
            f.write(struct.pack("<I", 54))
            # DIB header (40 bytes)
            f.write(struct.pack("<I", 40))
            f.write(struct.pack("<i", width))
            f.write(struct.pack("<i", height))  # bottom-up for BMP
            f.write(struct.pack("<HH", 1, 32))
            f.write(struct.pack("<I", BI_RGB))
            f.write(struct.pack("<I", pixel_size))
            f.write(struct.pack("<i", 0))
            f.write(struct.pack("<i", 0))
            f.write(struct.pack("<I", 0))
            f.write(struct.pack("<I", 0))
            # Pixel data, flip vertically (top-down capture to bottom-up BMP)
            for y in range(height - 1, -1, -1):
                row_start = y * row_size
                row = bgra_data[row_start:row_start + row_size]
                f.write(row)
                if padded_row > row_size:
                    f.write(b"\x00" * (padded_row - row_size))

    def _arrange_window(self, args: dict) -> ExecutionResult:
        handles = _find_nt8_windows()
        if not handles:
            return ExecutionResult(success=False, driver=self.name, stderr="No NinjaTrader windows found")

        title_filter = args.get("title", "").lower()
        target = None
        if title_filter:
            for h in handles:
                if title_filter in _get_window_title(h).lower():
                    target = h
                    break
        if target is None:
            target = handles[0]

        x = int(args.get("x", 0))
        y = int(args.get("y", 0))
        w = int(args.get("width", 0))
        h = int(args.get("height", 0))

        flags = SWP_NOZORDER | SWP_SHOWWINDOW
        if w == 0 and h == 0:
            flags |= SWP_NOSIZE
        if x == 0 and y == 0 and "x" not in args:
            flags |= SWP_NOMOVE

        user32.SetWindowPos(target, 0, x, y, w, h, flags)
        title = _get_window_title(target)

        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Arranged window '{title}' to ({x},{y}) {w}x{h}",
            metadata={"hwnd": target, "title": title, "x": x, "y": y, "width": w, "height": h},
        )

    def _window_state(self, args: dict) -> ExecutionResult:
        handles = _find_nt8_windows()
        if not handles:
            return ExecutionResult(success=False, driver=self.name, stderr="No NinjaTrader windows found")

        title_filter = args.get("title", "").lower()
        target = None
        if title_filter:
            for h in handles:
                if title_filter in _get_window_title(h).lower():
                    target = h
                    break
        if target is None:
            target = handles[0]

        state = args.get("state", "restore").lower()
        state_map = {
            "minimize": SW_MINIMIZE,
            "maximize": SW_MAXIMIZE,
            "restore": SW_RESTORE,
            "show": SW_SHOW,
            "hide": SW_HIDE,
        }
        cmd = state_map.get(state, SW_RESTORE)
        user32.ShowWindow(target, cmd)
        title = _get_window_title(target)

        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Set window '{title}' to {state}",
            metadata={"hwnd": target, "title": title, "state": state},
        )

    def _list_windows(self, args: dict) -> ExecutionResult:
        handles = _find_nt8_windows()
        windows = []
        for h in handles:
            rect = wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(rect))
            windows.append({
                "hwnd": h,
                "title": _get_window_title(h),
                "x": rect.left,
                "y": rect.top,
                "width": rect.right - rect.left,
                "height": rect.bottom - rect.top,
            })
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Found {len(windows)} NinjaTrader windows",
            metadata={"windows": windows},
        )
