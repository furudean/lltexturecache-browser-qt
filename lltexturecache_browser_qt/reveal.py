import subprocess  # nosec B404 - see `ran`
import sys
from pathlib import Path

REVEAL_LIMIT = 100
REVEAL_TIMEOUT_S = 2.0


def quoted(text: str) -> str:
    return '"{}"'.format(text.replace("\\", "\\\\").replace('"', '\\"'))


def ran(command: list[str]) -> bool:
    """Run a file manager command and say whether it worked

    Every command here is a fixed argument list built in this module, run
    without a shell, and the only part of it that varies is a path the app
    itself wrote and `reveal` has already checked is absolute. Nothing a
    user types reaches it.
    """

    try:
        finished = subprocess.run(  # nosec B603 - fixed argv, no shell, paths checked by `reveal`
            command,
            capture_output=True,
            timeout=REVEAL_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    return finished.returncode == 0


def reveal_darwin(paths: list[Path]) -> bool:
    items = ", ".join(f"POSIX file {quoted(str(path))}" for path in paths)

    return ran(
        [
            "osascript",
            "-e",
            f'tell application "Finder" to reveal {{{items}}}',
            "-e",
            'tell application "Finder" to activate',
        ]
    )


def reveal_windows(paths: list[Path]) -> bool:
    if sys.platform != "win32":
        # type guard missing ctypes for other platforms
        return False

    # inside the guard rather than at the top of the module: ctypes.windll is
    # the one platform's, and a checker reading this on any other platform
    # only knows the names are safe to resolve once the guard has returned
    import ctypes
    from ctypes import wintypes

    shell32 = ctypes.windll.shell32

    shell32.ILCreateFromPathW.argtypes = (wintypes.LPCWSTR,)
    shell32.ILCreateFromPathW.restype = ctypes.c_void_p
    shell32.ILFree.argtypes = (ctypes.c_void_p,)
    shell32.ILFree.restype = None
    shell32.SHOpenFolderAndSelectItems.argtypes = (
        ctypes.c_void_p,
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.DWORD,
    )
    shell32.SHOpenFolderAndSelectItems.restype = ctypes.HRESULT

    folder = shell32.ILCreateFromPathW(str(paths[0].parent))
    items = [shell32.ILCreateFromPathW(str(path)) for path in paths]

    try:
        if not folder or not all(items):
            return False

        shell32.SHOpenFolderAndSelectItems(folder, len(items), (ctypes.c_void_p * len(items))(*items), 0)
    except OSError:
        return False
    finally:
        for item in (folder, *items):
            shell32.ILFree(item)

    return True


def reveal_linux(paths: list[Path]) -> bool:
    uris = ", ".join(quoted(path.as_uri()) for path in paths)

    return ran(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.freedesktop.FileManager1",
            "--object-path",
            "/org/freedesktop/FileManager1",
            "--method",
            "org.freedesktop.FileManager1.ShowItems",
            f"[{uris}]",
            "",
        ]
    )


def reveal(paths: list[Path]) -> bool:
    """Opens a file manager on these files, picked out, and says whether it could"""
    if not paths or len(paths) > REVEAL_LIMIT:
        return False

    if not all(path.is_absolute() for path in paths):
        return False

    if sys.platform == "darwin":
        return reveal_darwin(paths)

    if sys.platform == "win32":
        return reveal_windows(paths)

    return reveal_linux(paths)
