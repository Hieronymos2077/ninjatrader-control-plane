from __future__ import annotations
import os
import re
import shutil
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .base import BackendBase, ExecutionResult
except ImportError:
    from base import BackendBase, ExecutionResult


def _find_nt8_data_dir() -> Path:
    docs = Path.home() / "Documents" / "NinjaTrader 8"
    if docs.exists():
        return docs
    onedrive = Path.home() / "OneDrive" / "Documents" / "NinjaTrader 8"
    if onedrive.exists():
        return onedrive
    return docs


_TYPE_SUBDIRS = {
    "strategy": "bin/Custom/Strategies",
    "indicator": "bin/Custom/Indicators",
    "addon": "bin/Custom/AddOns",
    "drawingtool": "bin/Custom/DrawingTools",
}

_TRACE_LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}:\d{3})\s+(.*)$")
_CS_ERROR_RE = re.compile(
    r"^(?P<file>.+?\.cs)\((?P<line>\d+)(?:,(?P<col>\d+))?\)\s*:\s*(?:error|warning)\s+"
    r"(?P<code>[A-Za-z]+\d+)\s*:\s*(?P<message>.*)$"
)


class FileWriteBackend(BackendBase):
    name = "file_write"

    def __init__(self, nt8_data_dir: Path | None = None):
        self.nt8_root = nt8_data_dir or _find_nt8_data_dir()

    def is_available(self) -> bool:
        return self.nt8_root.exists()

    def execute(self, action: str, args: dict[str, Any]) -> ExecutionResult:
        dispatch = {
            "write_file": self._write_file,
            "read_file": self._read_file,
            "list_files": self._list_files,
            "delete_file": self._delete_file,
            "search_files": self._search_files,
            "read_log": self._read_log,
            "compile_status": self._compile_status,
            "parse_compile_errors": self._parse_compile_errors,
            "analyzer_status": self._analyzer_status,
            "analyzer_results": self._analyzer_results,
            "analyzer_list_results": self._analyzer_list_results,
        }
        handler = dispatch.get(action)
        if handler is None:
            return ExecutionResult(success=False, driver=self.name, stderr=f"Unknown action '{action}'")
        try:
            return handler(args)
        except Exception as exc:
            return ExecutionResult(success=False, driver=self.name, stderr=str(exc))

    # ── helpers ────────────────────────────────────────────────────────

    def _resolve_dir(self, file_type: str) -> Path:
        subdir = _TYPE_SUBDIRS.get(file_type)
        if subdir is None:
            raise ValueError(f"Unknown file type '{file_type}'. Valid: {list(_TYPE_SUBDIRS)}")
        return self.nt8_root / subdir

    def _resolve_file(self, name: str, file_type: str) -> Path:
        if not name.endswith(".cs"):
            name += ".cs"
        if "/" in name or "\\" in name or ".." in name:
            raise ValueError(f"Invalid file name (path traversal not allowed): {name}")
        directory = self._resolve_dir(file_type)
        target = directory / name
        resolved = target.resolve()
        directory_resolved = directory.resolve()
        if directory_resolved != resolved and directory_resolved not in resolved.parents:
            raise ValueError(f"Resolved path escapes allowed directory: {target}")
        return target

    def _backup(self, path: Path) -> str | None:
        if path.exists():
            bak = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, bak)
            return str(bak)
        return None

    # ── actions ────────────────────────────────────────────────────────

    def _write_file(self, args: dict) -> ExecutionResult:
        name: str = args["name"]
        content: str = args["content"]
        file_type: str = args.get("type", "strategy")

        target = self._resolve_file(name, file_type)
        target.parent.mkdir(parents=True, exist_ok=True)

        artifacts: list[str] = []
        bak = self._backup(target)
        if bak:
            artifacts.append(bak)

        target.write_text(content, encoding="utf-8")
        artifacts.insert(0, str(target))

        return ExecutionResult(
            success=True,
            driver=self.name,
            stdout=f"Wrote {len(content)} bytes to {target}",
            artifacts=artifacts,
            metadata={"path": str(target), "size": len(content)},
        )

    def _read_file(self, args: dict) -> ExecutionResult:
        name: str = args["name"]
        file_type: str = args.get("type", "strategy")
        target = self._resolve_file(name, file_type)

        if not target.exists():
            return ExecutionResult(success=False, driver=self.name, stderr=f"File not found: {target}")

        content = target.read_text(encoding="utf-8", errors="replace")
        return ExecutionResult(
            success=True,
            driver=self.name,
            stdout=f"Read {len(content)} bytes from {target}",
            metadata={"path": str(target), "content": content, "size": len(content)},
        )

    def _list_files(self, args: dict) -> ExecutionResult:
        file_type: str | None = args.get("type")
        types_to_scan = [file_type] if file_type else list(_TYPE_SUBDIRS)

        files: list[dict] = []
        for ft in types_to_scan:
            directory = self._resolve_dir(ft)
            if not directory.exists():
                continue
            for p in directory.glob("*.cs"):
                stat = p.stat()
                files.append({
                    "name": p.name,
                    "type": ft,
                    "path": str(p),
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    "size": stat.st_size,
                })

        files.sort(key=lambda f: f["modified"], reverse=True)
        return ExecutionResult(
            success=True,
            driver=self.name,
            stdout=f"Found {len(files)} .cs files",
            metadata={"files": files},
        )

    def _delete_file(self, args: dict) -> ExecutionResult:
        name: str = args["name"]
        file_type: str = args.get("type", "strategy")
        target = self._resolve_file(name, file_type)

        if not target.exists():
            return ExecutionResult(success=False, driver=self.name, stderr=f"File not found: {target}")

        bak = self._backup(target)
        target.unlink()
        artifacts = [bak] if bak else []
        return ExecutionResult(
            success=True,
            driver=self.name,
            stdout=f"Deleted {target} (backup: {bak})",
            artifacts=artifacts,
        )

    def _search_files(self, args: dict) -> ExecutionResult:
        query: str = args["query"]
        file_type: str | None = args.get("type")
        types_to_scan = [file_type] if file_type else list(_TYPE_SUBDIRS)

        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        matches: list[dict] = []
        for ft in types_to_scan:
            directory = self._resolve_dir(ft)
            if not directory.exists():
                continue
            for p in directory.glob("*.cs"):
                try:
                    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                hit_lines = []
                for i, line in enumerate(lines, 1):
                    if pattern.search(line):
                        hit_lines.append({"line": i, "text": line.rstrip()})
                if hit_lines:
                    matches.append({
                        "name": p.name,
                        "type": ft,
                        "path": str(p),
                        "matches": hit_lines,
                    })

        return ExecutionResult(
            success=True,
            driver=self.name,
            stdout=f"Found {sum(len(m['matches']) for m in matches)} matches in {len(matches)} files",
            metadata={"results": matches},
        )

    def _read_log(self, args: dict) -> ExecutionResult:
        log_type: str = args.get("log_type", "log")
        num_lines: int = int(args.get("lines", 100))
        tail: bool = args.get("tail", True)
        contains: str | None = args.get("contains")

        if log_type == "trace":
            log_dir = self.nt8_root / "trace"
        else:
            log_dir = self.nt8_root / "log"

        if not log_dir.exists():
            return ExecutionResult(success=False, driver=self.name, stderr=f"Log directory not found: {log_dir}")

        log_files = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not log_files:
            log_files = sorted(log_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not log_files:
            return ExecutionResult(success=False, driver=self.name, stderr=f"No log files in {log_dir}")

        target = log_files[0]
        try:
            all_lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as e:
            return ExecutionResult(success=False, driver=self.name, stderr=f"Cannot read {target}: {e}")

        if contains:
            all_lines = [l for l in all_lines if contains.lower() in l.lower()]

        if tail:
            selected = all_lines[-num_lines:]
        else:
            selected = all_lines[:num_lines]

        content = "\n".join(selected)
        return ExecutionResult(
            success=True,
            driver=self.name,
            stdout=content,
            metadata={
                "log_file": str(target),
                "total_lines": len(all_lines),
                "returned_lines": len(selected),
            },
        )

    # ── compile detection ─────────────────────────────────────────────

    def _dll_path(self) -> Path:
        return self.nt8_root / "bin" / "Custom" / "NinjaTrader.Custom.dll"

    def _newest_file(self, directory: Path, pattern: str) -> Path | None:
        if not directory.exists():
            return None
        candidates = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0] if candidates else None

    def _parse_since(self, since: str | None) -> datetime | None:
        if not since:
            return None
        try:
            dt = datetime.fromisoformat(since)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _parse_trace_line(self, line: str) -> tuple[datetime | None, str]:
        m = _TRACE_LINE_RE.match(line)
        if not m:
            return None, line
        ts_str, rest = m.group(1), m.group(2)
        try:
            dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S:%f").replace(tzinfo=timezone.utc)
        except ValueError:
            return None, line
        return dt, rest

    def _compile_status(self, args: dict) -> ExecutionResult:
        dll_path = self._dll_path()
        exists = dll_path.exists()
        mtime_iso = None
        size = None
        if exists:
            stat = dll_path.stat()
            mtime_iso = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            size = stat.st_size

        trace_dir = self.nt8_root / "trace"
        newest_trace = self._newest_file(trace_dir, "trace.*.txt")
        trace_lines: list[str] = []
        if newest_trace is not None:
            try:
                lines = newest_trace.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                lines = []
            matching = [l for l in lines if "compile" in l.lower()]
            trace_lines = matching[-30:]

        return ExecutionResult(
            success=True,
            driver=self.name,
            stdout=f"DLL {'exists' if exists else 'not found'} at {dll_path}",
            metadata={
                "dll_path": str(dll_path),
                "exists": exists,
                "mtime_iso": mtime_iso,
                "size": size,
                "trace_file": str(newest_trace) if newest_trace else None,
                "trace_lines": trace_lines,
            },
        )

    def _parse_compile_errors(self, args: dict) -> ExecutionResult:
        since_dt = self._parse_since(args.get("since"))

        sources: list[Path] = []
        newest_trace = self._newest_file(self.nt8_root / "trace", "trace.*.txt")
        if newest_trace is not None:
            sources.append(newest_trace)
        newest_log = self._newest_file(self.nt8_root / "log", "log.*.txt")
        if newest_log is not None:
            sources.append(newest_log)

        errors: list[dict] = []
        found_failure_marker = False
        scanned_files: list[str] = []

        for src in sources:
            scanned_files.append(str(src))
            try:
                lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                if not line.strip():
                    continue
                ts, rest = self._parse_trace_line(line)
                if since_dt is not None and ts is not None and ts <= since_dt:
                    continue
                if "unable to compile" in rest.lower():
                    found_failure_marker = True
                    errors.append({"raw": line, "source": str(src)})
                    continue
                m = _CS_ERROR_RE.match(rest.strip())
                if m:
                    errors.append({
                        "file": m.group("file"),
                        "line": int(m.group("line")),
                        "code": m.group("code"),
                        "message": m.group("message").strip(),
                        "source": str(src),
                    })

        return ExecutionResult(
            success=True,
            driver=self.name,
            stdout=f"Found {len(errors)} compile error entr" + ("y" if len(errors) == 1 else "ies")
            + (", failure marker seen" if found_failure_marker else ", no failure marker"),
            metadata={
                "errors": errors,
                "found_failure_marker": found_failure_marker,
                "scanned_files": scanned_files,
                "since": args.get("since"),
            },
        )

    # ── strategy analyzer results ─────────────────────────────────────

    def _analyzer_dir(self) -> Path:
        return self.nt8_root / "strategyanalyzerlogs"

    def _strategy_guess(self, filename: str) -> str:
        stem = Path(filename).stem
        parts = stem.split("_")
        guess_parts: list[str] = []
        for p in parts:
            if p.isdigit() and len(p) >= 6:
                break
            guess_parts.append(p)
        if not guess_parts:
            return stem
        return "_".join(guess_parts)

    def _matches_strategy(self, filename: str, guess: str, strategy_filter: str | None) -> bool:
        if not strategy_filter:
            return True
        lowered = strategy_filter.lower()
        return lowered in guess.lower() or lowered in filename.lower()

    def _analyzer_status(self, args: dict) -> ExecutionResult:
        since_dt = self._parse_since(args.get("since"))
        strategy_filter = args.get("strategy")

        analyzer_dir = self._analyzer_dir()
        if not analyzer_dir.exists():
            return ExecutionResult(
                success=True,
                driver=self.name,
                stdout=f"strategyanalyzerlogs directory not found: {analyzer_dir}",
                metadata={"found": False, "entries": [], "analyzer_dir": str(analyzer_dir)},
            )

        raw_entries: list[tuple[datetime, dict]] = []
        for p in analyzer_dir.glob("*.xml"):
            try:
                stat = p.stat()
            except OSError:
                continue
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            guess = self._strategy_guess(p.name)
            if not self._matches_strategy(p.name, guess, strategy_filter):
                continue
            raw_entries.append((mtime, {
                "name": p.name,
                "path": str(p),
                "mtime_iso": mtime.isoformat(),
                "strategy_guess": guess,
            }))

        raw_entries.sort(key=lambda t: t[0], reverse=True)
        entries = [e for _, e in raw_entries]

        found = False
        if raw_entries:
            found = since_dt is None or raw_entries[0][0] > since_dt

        return ExecutionResult(
            success=True,
            driver=self.name,
            stdout=f"Found {len(entries)} matching analyzer xml file(s), found={found}",
            metadata={"found": found, "entries": entries, "analyzer_dir": str(analyzer_dir)},
        )

    def _pick_analyzer_xml(self, args: dict) -> Path | None:
        analyzer_dir = self._analyzer_dir()
        if not analyzer_dir.exists():
            return None

        name = args.get("name")
        if name:
            candidate = analyzer_dir / name
            return candidate if candidate.exists() else None

        strategy_filter = args.get("strategy")
        since_dt = self._parse_since(args.get("since"))

        matches: list[tuple[datetime, Path]] = []
        for p in analyzer_dir.glob("*.xml"):
            try:
                stat = p.stat()
            except OSError:
                continue
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            if since_dt is not None and mtime <= since_dt:
                continue
            guess = self._strategy_guess(p.name)
            if not self._matches_strategy(p.name, guess, strategy_filter):
                continue
            matches.append((mtime, p))

        if not matches:
            return None
        matches.sort(key=lambda t: t[0], reverse=True)
        return matches[0][1]

    def _parse_analyzer_xml(self, path: Path) -> dict:
        tree = ET.parse(str(path))
        root = tree.getroot()
        entry = root.find(".//StrategyAnalyzerGridEntry")
        if entry is None:
            entry = root

        def _text(tag: str) -> str | None:
            el = entry.find(tag)
            if el is not None and el.text:
                return el.text.strip()
            return None

        action = _text("Action")
        date = _text("Date")
        instrument = _text("Instrument")
        from_date = _text("From")
        strategy_file = _text("StrategyFile") or _text("Guid")

        parameters: dict[str, str | None] = {}
        opt_params = entry.find("OptimizationParameters")
        if opt_params is not None:
            for param in opt_params.findall("Parameter"):
                name_el = param.find("Name")
                value_el = param.find("Value")
                pname = param.get("Name") or (name_el.text.strip() if name_el is not None and name_el.text else None)
                pvalue = param.get("Value") or (value_el.text.strip() if value_el is not None and value_el.text else None)
                if pname is not None:
                    parameters[pname] = pvalue

        performance: dict[str, dict] = {}
        for sp in entry.findall(".//SummaryPerformances"):
            unit_el = sp.find("PerformanceUnit")
            unit = sp.get("Unit") or (unit_el.text.strip() if unit_el is not None and unit_el.text else "Unknown")
            serialize_el = sp.find("SummaryPerformancesSerialize")
            raw = serialize_el.text if serialize_el is not None and serialize_el.text else (sp.text or "")
            metrics: dict[str, dict] = {}
            for entry_str in raw.split("|"):
                entry_str = entry_str.strip()
                if not entry_str:
                    continue
                parts = entry_str.split(";")
                metric_name = parts[0]
                metrics[metric_name] = {
                    "all": parts[1] if len(parts) > 1 else None,
                    "long": parts[2] if len(parts) > 2 else None,
                    "short": parts[3] if len(parts) > 3 else None,
                }
            performance[unit] = metrics

        return {
            "action": action,
            "date": date,
            "instrument": instrument,
            "from_date": from_date,
            "strategy_file": strategy_file,
            "parameters": parameters,
            "performance": performance,
        }

    def _analyzer_results(self, args: dict) -> ExecutionResult:
        path = self._pick_analyzer_xml(args)
        if path is None:
            return ExecutionResult(
                success=False,
                driver=self.name,
                stderr="No matching analyzer xml file found",
                metadata={"error_code": "ANALYZER_RESULTS_NOT_FOUND"},
            )

        try:
            parsed = self._parse_analyzer_xml(path)
        except ET.ParseError as exc:
            return ExecutionResult(
                success=False,
                driver=self.name,
                stderr=f"Failed to parse xml {path}: {exc}",
                metadata={"path": str(path), "error_code": "ANALYZER_XML_PARSE_ERROR"},
            )

        parsed["source_file"] = str(path)
        return ExecutionResult(
            success=True,
            driver=self.name,
            stdout=f"Parsed analyzer results from {path.name}",
            metadata=parsed,
        )

    def _analyzer_list_results(self, args: dict) -> ExecutionResult:
        strategy_filter = args.get("strategy")
        limit = int(args.get("limit", 10))

        analyzer_dir = self._analyzer_dir()
        if not analyzer_dir.exists():
            return ExecutionResult(
                success=True,
                driver=self.name,
                stdout=f"strategyanalyzerlogs directory not found: {analyzer_dir}",
                metadata={"results": []},
            )

        candidates: list[tuple[float, Path, str]] = []
        for p in analyzer_dir.glob("*.xml"):
            try:
                stat = p.stat()
            except OSError:
                continue
            guess = self._strategy_guess(p.name)
            if not self._matches_strategy(p.name, guess, strategy_filter):
                continue
            candidates.append((stat.st_mtime, p, guess))

        candidates.sort(key=lambda t: t[0], reverse=True)
        candidates = candidates[:limit]

        results: list[dict] = []
        for mtime, p, guess in candidates:
            entry = {
                "name": p.name,
                "path": str(p),
                "mtime_iso": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                "strategy_guess": guess,
            }
            try:
                parsed = self._parse_analyzer_xml(p)
                currency = parsed["performance"].get("Currency", {})
                for key in ("TotalNetProfit", "ProfitFactor", "TotalNumTrades", "MaxDrawdown"):
                    metric = currency.get(key)
                    entry[key] = metric["all"] if metric else None
            except ET.ParseError:
                entry["parse_error"] = True
            results.append(entry)

        return ExecutionResult(
            success=True,
            driver=self.name,
            stdout=f"Listed {len(results)} analyzer result(s)",
            metadata={"results": results},
        )
