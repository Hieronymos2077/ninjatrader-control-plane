"""Dynamic consistency suite for the NT8 command catalog and backend wiring.

Reads NT8_COMMAND_CATALOG, _BACKEND_ACTION_MAP, and NT8ControlPlane._macro_dispatch
straight from the live runtime\\controller.py, and cross checks them against the
real dispatch tables in runtime\\backends\\*.py and the backend registry in
runtime\\__main__.py. Nothing here is a hardcoded copy of an expected command
list, everything is derived from whatever the code says right now. This is the
test class that catches the historical CRIT-3 (missing backend action) and
CRIT-5 (mapped action absent from the target backend) bug family.

Run directly:
    python diagnostics\\test_consistency.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    BACKEND_MODULE_PATHS,
    Result,
    extract_backend_dispatch_keys,
    extract_main_backend_names,
    report,
)

CONTROLLER_LEVEL_PREFIXES = ("macro.", "system.")
CONTROLLER_LEVEL_EXACT = {"bridge.deploy"}


def _is_controller_level(command: str, backends: list) -> bool:
    if command.startswith(CONTROLLER_LEVEL_PREFIXES) or command in CONTROLLER_LEVEL_EXACT:
        return True
    if backends == ["auto"]:
        return True
    return False


def check_a_catalog_has_action_map_coverage(catalog: dict, action_map: dict) -> list[Result]:
    results: list[Result] = []
    for command, entry in sorted(catalog.items()):
        backends = list(entry.get("backends", []))
        if _is_controller_level(command, backends):
            results.append(Result("PASS", f"catalog_coverage[{command}]", "controller level command, no per backend mapping required"))
            continue

        mapping = action_map.get(command, {})
        missing = [b for b in backends if b != "auto" and b not in mapping]
        if missing:
            results.append(
                Result(
                    "FAIL",
                    f"catalog_coverage[{command}]",
                    f"backends {missing} are listed in the catalog but have no entry in _BACKEND_ACTION_MAP",
                )
            )
        else:
            results.append(Result("PASS", f"catalog_coverage[{command}]", f"backends {backends} all mapped"))
    return results


def check_b_actions_exist_in_backend_dispatch(action_map: dict) -> list[Result]:
    results: list[Result] = []
    dispatch_cache: dict[str, set] = {}
    for command, mapping in sorted(action_map.items()):
        for backend_name, action_name in sorted(mapping.items()):
            if backend_name not in BACKEND_MODULE_PATHS:
                results.append(
                    Result(
                        "FAIL",
                        f"action_exists[{command}:{backend_name}]",
                        f"backend name '{backend_name}' referenced in _BACKEND_ACTION_MAP is not a known backend module",
                    )
                )
                continue
            if backend_name not in dispatch_cache:
                dispatch_cache[backend_name] = extract_backend_dispatch_keys(backend_name)
            dispatch_keys = dispatch_cache[backend_name]
            if action_name not in dispatch_keys:
                results.append(
                    Result(
                        "FAIL",
                        f"action_exists[{command}:{backend_name}]",
                        f"action '{action_name}' is not in {backend_name}'s dispatch table (has: {sorted(dispatch_keys)})",
                    )
                )
            else:
                results.append(Result("PASS", f"action_exists[{command}:{backend_name}]", f"'{action_name}' found in {backend_name} dispatch table"))
    return results


def check_c_backend_names_registered_in_main(action_map: dict) -> list[Result]:
    results: list[Result] = []
    used_backend_names: set[str] = set()
    for mapping in action_map.values():
        used_backend_names.update(mapping.keys())

    registered = extract_main_backend_names()
    if not registered:
        results.append(Result("FAIL", "main_backend_registry", "could not find a 'backends = {...}' dict literal in runtime\\__main__.py"))
        return results

    for backend_name in sorted(used_backend_names):
        if backend_name in ("auto",):
            continue
        if backend_name in registered:
            results.append(Result("PASS", f"main_registration[{backend_name}]", "registered in runtime\\__main__.py backends dict"))
        else:
            results.append(
                Result(
                    "FAIL",
                    f"main_registration[{backend_name}]",
                    f"'{backend_name}' is used in _BACKEND_ACTION_MAP but not registered in runtime\\__main__.py (has: {sorted(registered)})",
                )
            )
    return results


def check_d_arg_specs_are_string_lists(catalog: dict) -> list[Result]:
    results: list[Result] = []
    for command, entry in sorted(catalog.items()):
        for field in ("required_args", "optional_args"):
            value = entry.get(field, [])
            ok = isinstance(value, list) and all(isinstance(x, str) for x in value)
            if ok:
                results.append(Result("PASS", f"arg_spec[{command}.{field}]", f"{value}"))
            else:
                results.append(Result("FAIL", f"arg_spec[{command}.{field}]", f"expected a list of strings, got {value!r}"))
    return results


def check_e_macros_have_dispatch_handlers(catalog: dict, macro_dispatch: dict) -> list[Result]:
    results: list[Result] = []
    macro_commands = [c for c in catalog if c.startswith("macro.")]
    for command in sorted(macro_commands):
        if command in macro_dispatch:
            results.append(Result("PASS", f"macro_handler[{command}]", "handler present in NT8ControlPlane._macro_dispatch"))
        else:
            results.append(
                Result(
                    "FAIL",
                    f"macro_handler[{command}]",
                    f"'{command}' is in NT8_COMMAND_CATALOG but has no entry in NT8ControlPlane._macro_dispatch",
                )
            )
    return results


def main() -> int:
    from runtime.controller import NT8_COMMAND_CATALOG, _BACKEND_ACTION_MAP, NT8ControlPlane

    catalog = NT8_COMMAND_CATALOG
    action_map = _BACKEND_ACTION_MAP
    macro_dispatch = NT8ControlPlane._macro_dispatch

    results: list[Result] = []
    results.append(Result("PASS", "catalog_size", f"{len(catalog)} commands loaded from live runtime.controller.NT8_COMMAND_CATALOG"))
    results += check_a_catalog_has_action_map_coverage(catalog, action_map)
    results += check_b_actions_exist_in_backend_dispatch(action_map)
    results += check_c_backend_names_registered_in_main(action_map)
    results += check_d_arg_specs_are_string_lists(catalog)
    results += check_e_macros_have_dispatch_handlers(catalog, macro_dispatch)

    return report(results, "test_consistency")


if __name__ == "__main__":
    sys.exit(main())
