from __future__ import annotations

import time
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageStat
except Exception:
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageStat = None  # type: ignore[assignment]


DEFAULT_ROI_REGISTRY: dict[str, dict[str, float]] = {
    "chart_area": {"x": 0.0, "y": 0.05, "width": 1.0, "height": 0.65},
    "control_center": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.05},
    "output_window": {"x": 0.0, "y": 0.70, "width": 1.0, "height": 0.30},
    "chart_trader": {"x": 0.75, "y": 0.05, "width": 0.25, "height": 0.65},
    "strategy_analyzer": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
    "instrument_overlay": {"x": 0.0, "y": 0.05, "width": 0.20, "height": 0.04},
    "toolbar": {"x": 0.0, "y": 0.04, "width": 1.0, "height": 0.03},
    "market_analyzer": {"x": 0.0, "y": 0.0, "width": 0.30, "height": 0.50},
    "order_entry": {"x": 0.70, "y": 0.05, "width": 0.30, "height": 0.40},
}


DEFAULT_VISUAL_REQUIREMENTS: dict[str, list[dict[str, Any]]] = {
    "terminal.capture": [{"type": "panel_visible", "panel": "chart_area", "min_variance": 1.0}],
    "chart.open": [{"type": "panel_visible", "panel": "chart_area", "min_variance": 0.8}],
    "chart.screenshot": [{"type": "panel_visible", "panel": "chart_area", "min_variance": 1.0}],
    "chart.switch_instrument": [{"type": "panel_visible", "panel": "chart_area", "min_variance": 0.8}],
    "chart.switch_timeframe": [{"type": "panel_visible", "panel": "chart_area", "min_variance": 0.8}],
    "chart.indicator_add": [{"type": "panel_visible", "panel": "chart_area", "min_variance": 0.8}],
    "chart.indicator_remove": [{"type": "panel_visible", "panel": "chart_area", "min_variance": 0.8}],
    "chart.template_apply": [{"type": "panel_visible", "panel": "chart_area", "min_variance": 0.8}],
    "strategy.attach": [{"type": "panel_visible", "panel": "chart_area", "min_variance": 0.8}],
    "tester.open": [{"type": "panel_visible", "panel": "strategy_analyzer", "min_variance": 0.8}],
    "tester.start": [{"type": "panel_visible", "panel": "strategy_analyzer", "min_variance": 0.8}],
    "tester.status": [{"type": "panel_visible", "panel": "strategy_analyzer", "min_variance": 0.8}],
    "tester.results": [{"type": "panel_visible", "panel": "strategy_analyzer", "min_variance": 0.8}],
    "compile.all": [{"type": "panel_visible", "panel": "output_window", "min_variance": 0.8}],
    "compile.check": [{"type": "panel_visible", "panel": "output_window", "min_variance": 0.8}],
    "logs.output": [{"type": "panel_visible", "panel": "output_window", "min_variance": 0.8}],
    "trade.place": [{"type": "panel_visible", "panel": "control_center", "min_variance": 0.8}],
    "position.list": [{"type": "panel_visible", "panel": "control_center", "min_variance": 0.8}],
    "order.list": [{"type": "panel_visible", "panel": "control_center", "min_variance": 0.8}],
}


def _require_pillow() -> None:
    if Image is None:
        raise RuntimeError("Pillow is required for NT8 visual capture operations.")


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _normalize_bounds(left: int, top: int, right: int, bottom: int, width: int, height: int) -> tuple[int, int, int, int]:
    left = _clamp(left, 0, width - 1 if width > 0 else 0)
    top = _clamp(top, 0, height - 1 if height > 0 else 0)
    right = _clamp(right, left + 1, width if width > 0 else left + 1)
    bottom = _clamp(bottom, top + 1, height if height > 0 else top + 1)
    return left, top, right, bottom


def resolve_region_bounds(
    region: dict[str, Any] | list[Any] | tuple[Any, ...],
    *,
    image_width: int,
    image_height: int,
    roi_registry: dict[str, dict[str, float]] | None = None,
) -> tuple[int, int, int, int]:
    registry = dict(DEFAULT_ROI_REGISTRY)
    if roi_registry:
        registry.update(roi_registry)

    if isinstance(region, (list, tuple)) and len(region) == 4:
        x = _as_int(region[0], 0)
        y = _as_int(region[1], 0)
        w = _as_int(region[2], image_width)
        h = _as_int(region[3], image_height)
        return _normalize_bounds(x, y, x + max(1, w), y + max(1, h), image_width, image_height)

    if not isinstance(region, dict):
        raise ValueError("region must be a dict or [x, y, width, height] list")

    panel = str(region.get("panel", "")).strip()
    if panel:
        panel_roi = registry.get(panel)
        if panel_roi is None:
            raise ValueError(f"Unknown ROI panel '{panel}'")
        x = int(round(_as_float(panel_roi.get("x"), 0.0) * image_width))
        y = int(round(_as_float(panel_roi.get("y"), 0.0) * image_height))
        w = int(round(_as_float(panel_roi.get("width"), 1.0) * image_width))
        h = int(round(_as_float(panel_roi.get("height"), 1.0) * image_height))
        return _normalize_bounds(x, y, x + max(1, w), y + max(1, h), image_width, image_height)

    relative = bool(region.get("relative", False))
    if all(k in region for k in ("left", "top", "right", "bottom")):
        if relative:
            left = int(round(_as_float(region.get("left"), 0.0) * image_width))
            top = int(round(_as_float(region.get("top"), 0.0) * image_height))
            right = int(round(_as_float(region.get("right"), 1.0) * image_width))
            bottom = int(round(_as_float(region.get("bottom"), 1.0) * image_height))
        else:
            left = _as_int(region.get("left"), 0)
            top = _as_int(region.get("top"), 0)
            right = _as_int(region.get("right"), image_width)
            bottom = _as_int(region.get("bottom"), image_height)
        return _normalize_bounds(left, top, right, bottom, image_width, image_height)

    if all(k in region for k in ("x", "y", "width", "height")):
        if relative:
            x = int(round(_as_float(region.get("x"), 0.0) * image_width))
            y = int(round(_as_float(region.get("y"), 0.0) * image_height))
            w = int(round(_as_float(region.get("width"), 1.0) * image_width))
            h = int(round(_as_float(region.get("height"), 1.0) * image_height))
        else:
            x = _as_int(region.get("x"), 0)
            y = _as_int(region.get("y"), 0)
            w = _as_int(region.get("width"), image_width)
            h = _as_int(region.get("height"), image_height)
        return _normalize_bounds(x, y, x + max(1, w), y + max(1, h), image_width, image_height)

    raise ValueError("region must define panel, [left/top/right/bottom], or [x/y/width/height]")


def crop_region(
    *,
    source_path: Path,
    region: dict[str, Any] | list[Any] | tuple[Any, ...],
    output_path: Path,
    roi_registry: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    _require_pillow()
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as image:
        bounds = resolve_region_bounds(
            region,
            image_width=image.width,
            image_height=image.height,
            roi_registry=roi_registry,
        )
        cropped = image.crop(bounds)
        cropped.save(output_path)

    return {"source_path": str(source_path), "output_path": str(output_path), "bounds": list(bounds)}


def crop_multi_region(
    *,
    source_path: Path,
    regions: list[dict[str, Any]],
    output_dir: Path,
    file_prefix: str,
    roi_registry: dict[str, dict[str, float]] | None = None,
) -> list[dict[str, Any]]:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for idx, region in enumerate(regions, start=1):
        name = str(region.get("name", f"region_{idx:02d}")).strip() or f"region_{idx:02d}"
        safe_name = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in name)
        out_path = output_dir / f"{file_prefix}_{idx:02d}_{safe_name}.png"
        results.append(
            {
                "name": name,
                **crop_region(
                    source_path=source_path,
                    region=region,
                    output_path=out_path,
                    roi_registry=roi_registry,
                ),
            }
        )
    return results


def annotate_image(
    *,
    source_path: Path,
    annotations: list[dict[str, Any]],
    output_path: Path,
    roi_registry: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    _require_pillow()
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as image:
        draw = ImageDraw.Draw(image)
        rendered: list[dict[str, Any]] = []
        for idx, item in enumerate(annotations, start=1):
            if not isinstance(item, dict):
                continue
            region = item.get("region")
            if region is None:
                region = {
                    "panel": item.get("panel"),
                    "x": item.get("x"),
                    "y": item.get("y"),
                    "width": item.get("width"),
                    "height": item.get("height"),
                    "left": item.get("left"),
                    "top": item.get("top"),
                    "right": item.get("right"),
                    "bottom": item.get("bottom"),
                    "relative": bool(item.get("relative", False)),
                }
            bounds = resolve_region_bounds(
                region,
                image_width=image.width,
                image_height=image.height,
                roi_registry=roi_registry,
            )
            color = str(item.get("color", "#FF3B30"))
            width = max(1, _as_int(item.get("line_width"), 2))
            label = str(item.get("label", f"A{idx}"))
            draw.rectangle(bounds, outline=color, width=width)
            draw.text((bounds[0] + 2, max(0, bounds[1] - 14)), label, fill=color)
            rendered.append({"label": label, "bounds": list(bounds), "color": color, "line_width": width})
        image.save(output_path)

    return {"source_path": str(source_path), "output_path": str(output_path), "annotations": rendered}


def _ocr_text(image: Any) -> tuple[str, str | None]:
    try:
        import pytesseract  # type: ignore[import-untyped]
    except Exception:
        return "", "pytesseract not installed"
    try:
        text = str(pytesseract.image_to_string(image))
        return text, None
    except Exception as exc:
        return "", str(exc)


class VisualAssertionEngine:
    def __init__(self, *, roi_registry: dict[str, dict[str, float]] | None = None) -> None:
        self.roi_registry = dict(DEFAULT_ROI_REGISTRY)
        if roi_registry:
            self.roi_registry.update(roi_registry)

    def evaluate(
        self,
        *,
        image_path: Path,
        assertions: list[dict[str, Any]],
        retries: int = 1,
        retry_delay_seconds: float = 0.2,
    ) -> dict[str, Any]:
        _require_pillow()
        attempts = max(1, int(retries) + 1)
        retry_delay = max(0.0, float(retry_delay_seconds))
        if not assertions:
            return {
                "performed": False,
                "passed": True,
                "passed_count": 0,
                "failed_count": 0,
                "assertions": [],
                "image_path": str(image_path),
                "reason": "no_assertions_configured",
            }

        with Image.open(image_path) as image:
            img = image.copy()

        assertion_results: list[dict[str, Any]] = []
        for idx, assertion in enumerate(assertions, start=1):
            last_result: dict[str, Any] | None = None
            for attempt in range(1, attempts + 1):
                result = self._evaluate_one(img, assertion=assertion, assertion_index=idx)
                result["attempt"] = attempt
                last_result = result
                if result.get("passed"):
                    break
                if attempt < attempts and retry_delay > 0:
                    time.sleep(retry_delay)
            assertion_results.append(last_result or {"passed": False, "message": "assertion evaluation failed"})

        passed_count = sum(1 for item in assertion_results if item.get("passed"))
        failed_count = len(assertion_results) - passed_count
        return {
            "performed": True,
            "passed": failed_count == 0,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "assertions": assertion_results,
            "image_path": str(image_path),
        }

    def _evaluate_one(self, image: Any, *, assertion: dict[str, Any], assertion_index: int) -> dict[str, Any]:
        assertion_type = str(assertion.get("type", "panel_visible")).strip().lower()
        assertion_id = str(assertion.get("id", f"assert_{assertion_index:02d}"))
        if assertion_type in ("panel_visible", "pixel_variance_min"):
            return self._assert_panel_visible(image, assertion=assertion, assertion_id=assertion_id, assertion_type=assertion_type)
        if assertion_type == "text_contains":
            return self._assert_text_contains(image, assertion=assertion, assertion_id=assertion_id)
        if assertion_type == "icon_state":
            return self._assert_icon_state(image, assertion=assertion, assertion_id=assertion_id)
        return {
            "id": assertion_id,
            "type": assertion_type,
            "passed": False,
            "message": f"Unsupported visual assertion type '{assertion_type}'",
            "details": {"supported_types": ["panel_visible", "pixel_variance_min", "text_contains", "icon_state"]},
        }

    def _resolve_assertion_bounds(self, image: Any, assertion: dict[str, Any]) -> tuple[int, int, int, int]:
        region = assertion.get("region")
        if region is None:
            panel = str(assertion.get("panel", "")).strip()
            region = {"panel": panel} if panel else {"x": 0, "y": 0, "width": image.width, "height": image.height}
        return resolve_region_bounds(
            region,
            image_width=image.width,
            image_height=image.height,
            roi_registry=self.roi_registry,
        )

    def _assert_panel_visible(self, image: Any, *, assertion: dict[str, Any], assertion_id: str, assertion_type: str) -> dict[str, Any]:
        bounds = self._resolve_assertion_bounds(image, assertion)
        region = image.crop(bounds).convert("L")
        variance = float(ImageStat.Stat(region).var[0]) if ImageStat is not None else 0.0
        min_variance = _as_float(assertion.get("min_variance"), 1.0)
        passed = variance >= min_variance
        return {
            "id": assertion_id,
            "type": assertion_type,
            "passed": passed,
            "message": "" if passed else f"Region variance {variance:.3f} below min {min_variance:.3f}",
            "details": {"bounds": list(bounds), "variance": round(variance, 6), "min_variance": min_variance},
        }

    def _assert_text_contains(self, image: Any, *, assertion: dict[str, Any], assertion_id: str) -> dict[str, Any]:
        bounds = self._resolve_assertion_bounds(image, assertion)
        region = image.crop(bounds)
        text, error = _ocr_text(region)
        expected = assertion.get("expected")
        if isinstance(expected, str):
            expected_values = [expected]
        elif isinstance(expected, list):
            expected_values = [str(item) for item in expected if str(item).strip()]
        else:
            expected_values = []
        case_sensitive = bool(assertion.get("case_sensitive", False))

        haystack = text if case_sensitive else text.lower()
        matches: list[str] = []
        for token in expected_values:
            needle = token if case_sensitive else token.lower()
            if needle in haystack:
                matches.append(token)
        passed = bool(expected_values) and len(matches) == len(expected_values) and not error

        message = ""
        if error:
            message = f"OCR failed: {error}"
        elif not expected_values:
            message = "text_contains requires non-empty expected list or string"
        elif not passed:
            message = f"OCR text missing expected tokens: {expected_values}"

        return {
            "id": assertion_id,
            "type": "text_contains",
            "passed": passed,
            "message": message,
            "details": {
                "bounds": list(bounds),
                "expected": expected_values,
                "matched": matches,
                "ocr_error": error,
                "ocr_text_sample": text[:160],
            },
        }

    def _assert_icon_state(self, image: Any, *, assertion: dict[str, Any], assertion_id: str) -> dict[str, Any]:
        point = assertion.get("point")
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            return {
                "id": assertion_id,
                "type": "icon_state",
                "passed": False,
                "message": "icon_state requires point=[x,y]",
                "details": {},
            }

        x = _clamp(_as_int(point[0], 0), 0, max(0, image.width - 1))
        y = _clamp(_as_int(point[1], 0), 0, max(0, image.height - 1))
        expected = assertion.get("expected_rgb")
        if not isinstance(expected, (list, tuple)) or len(expected) != 3:
            return {
                "id": assertion_id,
                "type": "icon_state",
                "passed": False,
                "message": "icon_state requires expected_rgb=[r,g,b]",
                "details": {"point": [x, y]},
            }

        tolerance = _as_int(assertion.get("tolerance"), 24)
        pixel = image.convert("RGB").getpixel((x, y))
        diffs = [abs(int(pixel[i]) - _as_int(expected[i], 0)) for i in range(3)]
        passed = all(diff <= tolerance for diff in diffs)
        return {
            "id": assertion_id,
            "type": "icon_state",
            "passed": passed,
            "message": "" if passed else f"Pixel {pixel} differs from {tuple(expected)} by {diffs}",
            "details": {"point": [x, y], "pixel": list(pixel), "expected_rgb": list(expected), "tolerance": tolerance, "diffs": diffs},
        }
