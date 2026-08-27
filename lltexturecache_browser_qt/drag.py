import atexit
import shutil
import tempfile
from functools import cache
from pathlib import Path
from threading import Lock

from PySide6.QtCore import QMimeData, QUrl
from texture_courier import Texture, TextureCacheError

from lltexturecache_browser_qt import APP_NAME
from lltexturecache_browser_qt.export import FORMATS, export_texture

STAGING_PREFIX = f"{APP_NAME}-drag-"

# this tends to be slow, so we have a built-in limit
DRAG_LIMIT = 200
DRAG_FORMAT = FORMATS[0]


@cache
def staging() -> Path:
    directory = Path(tempfile.mkdtemp(prefix=STAGING_PREFIX))

    atexit.register(shutil.rmtree, directory, ignore_errors=True)

    return directory


def staged(textures: list[Texture], reads: Lock) -> list[Path]:
    out_dir = staging()
    paths = []

    for texture in textures:
        try:
            paths.append(export_texture(texture, out_dir, DRAG_FORMAT, reads))
        except (TextureCacheError, OSError, ValueError):
            continue

    return paths


def drag_data(paths: list[Path]) -> QMimeData:
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])

    return data
