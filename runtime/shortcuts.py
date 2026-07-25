from __future__ import annotations

from typing import Any


NT8_SHORTCUTS: list[dict[str, str]] = [
    # Chart navigation
    {"keys": "Up", "action": "Scroll chart up / increase price axis."},
    {"keys": "Down", "action": "Scroll chart down / decrease price axis."},
    {"keys": "Left", "action": "Scroll chart left (older bars)."},
    {"keys": "Right", "action": "Scroll chart right (newer bars)."},
    {"keys": "PageUp", "action": "Fast-scroll chart left (older bars)."},
    {"keys": "PageDown", "action": "Fast-scroll chart right (newer bars)."},
    {"keys": "Home", "action": "Jump to oldest visible bar in chart history."},
    {"keys": "End", "action": "Jump to most recent bar (chart end)."},
    {"keys": "Ctrl+Up", "action": "Zoom in on price axis (vertical zoom)."},
    {"keys": "Ctrl+Down", "action": "Zoom out on price axis (vertical zoom)."},
    {"keys": "Ctrl+Left", "action": "Zoom in on time axis (fewer bars visible)."},
    {"keys": "Ctrl+Right", "action": "Zoom out on time axis (more bars visible)."},
    {"keys": "+", "action": "Zoom in (bar width increase)."},
    {"keys": "-", "action": "Zoom out (bar width decrease)."},
    # Global shortcuts
    {"keys": "Ctrl+Shift+N", "action": "Open new chart window."},
    {"keys": "Ctrl+R", "action": "Open Strategy Analyzer window."},
    {"keys": "Ctrl+E", "action": "Toggle Automated Trading on/off."},
    {"keys": "F5", "action": "Compile all NinjaScript code."},
    {"keys": "Ctrl+N", "action": "Open NinjaScript Editor."},
    {"keys": "Ctrl+O", "action": "Open NinjaScript Output Window."},
    {"keys": "Ctrl+L", "action": "Open Log viewer."},
    {"keys": "Ctrl+F", "action": "Open FX Board (forex order entry)."},
    {"keys": "Ctrl+T", "action": "Open Trade Performance window."},
    {"keys": "Ctrl+Shift+T", "action": "Open Time & Sales window."},
    {"keys": "Ctrl+M", "action": "Open Market Analyzer window."},
    {"keys": "Ctrl+B", "action": "Open Basic Entry order window."},
    {"keys": "Ctrl+Shift+B", "action": "Open Chart Trader panel on chart."},
    {"keys": "Ctrl+D", "action": "Open Data Box window."},
    {"keys": "Ctrl+Shift+H", "action": "Open Hot List Analyzer."},
    {"keys": "Ctrl+P", "action": "Print chart."},
    {"keys": "F1", "action": "Open Help documentation."},
    {"keys": "Ctrl+Tab", "action": "Cycle through open chart windows."},
    {"keys": "Alt+F4", "action": "Close NinjaTrader."},
    # NinjaScript Editor shortcuts
    {"keys": "Ctrl+S", "action": "Save current NinjaScript file (in editor)."},
    {"keys": "Ctrl+Z", "action": "Undo last edit (in editor)."},
    {"keys": "Ctrl+Y", "action": "Redo last undo (in editor)."},
    {"keys": "Ctrl+Shift+F", "action": "Find and replace in NinjaScript Editor."},
    {"keys": "Ctrl+G", "action": "Go to line number (in editor)."},
    {"keys": "Ctrl+K, Ctrl+C", "action": "Comment selected lines (in editor)."},
    {"keys": "Ctrl+K, Ctrl+U", "action": "Uncomment selected lines (in editor)."},
    {"keys": "F7", "action": "Compile NinjaScript from editor."},
    # Order entry shortcuts
    {"keys": "Ctrl+Shift+O", "action": "Open Order Ticket window."},
    {"keys": "Escape", "action": "Cancel current action / close dialog."},
    {"keys": "Enter", "action": "Confirm / submit active form or dialog."},
    # Chart object shortcuts
    {"keys": "Delete", "action": "Delete selected drawing object on chart."},
    {"keys": "Ctrl+A", "action": "Select all drawing objects on chart."},
    {"keys": "Backspace", "action": "Remove last drawing object placed."},
    # Workspace
    {"keys": "Ctrl+W", "action": "Close active workspace tab."},
    {"keys": "Ctrl+Shift+W", "action": "Open Workspace management."},
    # Data and connections
    {"keys": "Ctrl+Shift+C", "action": "Open Connections dialog."},
    {"keys": "Ctrl+Shift+D", "action": "Open database management."},
    # Chart type toggles
    {"keys": "Alt+1", "action": "Switch chart to OHLC bar style."},
    {"keys": "Alt+2", "action": "Switch chart to candlestick style."},
    {"keys": "Alt+3", "action": "Switch chart to line on close style."},
    {"keys": "Alt+4", "action": "Switch chart to HeikinAshi style."},
    # Simulated trading
    {"keys": "Ctrl+Shift+E", "action": "Open Simulated Data Feed settings."},
    # Control Center navigation
    {"keys": "F2", "action": "Open Account Performance in Control Center."},
    {"keys": "F3", "action": "Open Orders tab in Control Center."},
    {"keys": "F4", "action": "Open Positions tab in Control Center."},
    {"keys": "F6", "action": "Open Executions tab in Control Center."},
    {"keys": "F8", "action": "Open Strategies tab in Control Center."},
    {"keys": "F9", "action": "Open Alerts tab in Control Center."},
    {"keys": "F10", "action": "Open News tab in Control Center."},
    {"keys": "F11", "action": "Toggle full screen mode."},
    {"keys": "F12", "action": "Open About NinjaTrader dialog."},
]


def list_nt8_shortcuts() -> list[dict[str, Any]]:
    return list(NT8_SHORTCUTS)
