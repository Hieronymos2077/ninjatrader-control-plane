"""Entry point for NT8 API Server."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backends.file_write import FileWriteBackend
from backends.addon_http import AddonHttpBackend
from backends.dll_ati import DllAtiBackend
from backends.win32_capture import Win32CaptureBackend
from backends.keyboard import KeyboardBackend
from controller import NT8ControlPlane
from server import NT8ApiServer


def main():
    port = int(os.environ.get("NT8_API_PORT", "8088"))
    addon_port = int(os.environ.get("NT8_ADDON_PORT", "8089"))
    workspace = Path(__file__).parent.parent

    backends = {
        "file_write": FileWriteBackend(),
        "addon_http": AddonHttpBackend(port=addon_port),
        "dll_ati": DllAtiBackend(),
        "win32": Win32CaptureBackend(),
        "keyboard": KeyboardBackend(),
    }

    nt8_data_dir = Path.home() / "Documents" / "NinjaTrader 8"
    if not nt8_data_dir.exists():
        onedrive_dir = Path.home() / "OneDrive" / "Documents" / "NinjaTrader 8"
        if onedrive_dir.exists():
            nt8_data_dir = onedrive_dir

    print(f"NT8 data dir resolved to: {nt8_data_dir}")
    if not nt8_data_dir.exists():
        print(
            f"ERROR: NT8 data dir not found at {nt8_data_dir}. "
            "Launch NinjaTrader 8 at least once so it creates its Documents folder, "
            "or set the correct path, then retry."
        )
        sys.exit(1)

    cp = NT8ControlPlane(nt8_data_dir=nt8_data_dir, backends=backends, workspace=workspace)

    server = NT8ApiServer(control_plane=cp, port=port)

    print(f"NT8 API Server starting on http://127.0.0.1:{port}")
    print(f"AddOn bridge expected at http://127.0.0.1:{addon_port}")
    print(f"Workspace: {workspace}")
    print(f"Backends: {', '.join(backends.keys())}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
