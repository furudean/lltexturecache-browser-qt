from pathlib import Path

from texture_courier import list_texture_caches

_paths: list[Path] = []


def resolve() -> list[Path]:
    global _paths

    try:
        _paths = list_texture_caches()
    except (FileNotFoundError, OSError):
        # nothing installed, or nothing we are allowed to look at
        _paths = []

    return paths()


def paths() -> list[Path]:
    return list(_paths)
