try:
    from .base import BackendBase, ExecutionResult
except ImportError:
    from base import BackendBase, ExecutionResult
try:
    from .file_write import FileWriteBackend
except ImportError:
    from file_write import FileWriteBackend
try:
    from .addon_http import AddonHttpBackend
except ImportError:
    from addon_http import AddonHttpBackend
try:
    from .dll_ati import DllAtiBackend
except ImportError:
    from dll_ati import DllAtiBackend
try:
    from .win32_capture import Win32CaptureBackend
except ImportError:
    from win32_capture import Win32CaptureBackend
try:
    from .keyboard import KeyboardBackend
except ImportError:
    from keyboard import KeyboardBackend

__all__ = [
    "BackendBase",
    "ExecutionResult",
    "FileWriteBackend",
    "AddonHttpBackend",
    "DllAtiBackend",
    "Win32CaptureBackend",
    "KeyboardBackend",
]
