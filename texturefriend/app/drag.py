import atexit
import logging
import shutil
import tempfile
from functools import cache
from pathlib import Path
from threading import Lock

from PySide6.QtCore import QEventLoop, QMimeData, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QProgressDialog, QWidget
from texture_courier import Texture

from texturefriend import APP_NAME
from texturefriend.app.exporting import DELAY_MESSAGE_DURATION_MS
from texturefriend.cache.export import ExportJob, export_format, export_path
from texturefriend.view.formatting import format_count

log = logging.getLogger(__name__)

STAGING_PREFIX = f"{APP_NAME}-drag-"

# this tends to be slow, so we have a built-in limit
DRAG_LIMIT = 200


@cache
def staging() -> Path:
    directory = Path(tempfile.mkdtemp(prefix=STAGING_PREFIX))

    atexit.register(shutil.rmtree, directory, ignore_errors=True)

    return directory


def held() -> bool:
    return bool(QGuiApplication.mouseButtons() & Qt.MouseButton.LeftButton)


def staged(
    parent: QWidget,
    textures: list[Texture],
    reads: Lock,
    *,
    title: str,
    while_held: bool = False,
) -> list[Path]:
    out_dir = staging()
    format = export_format()

    def wanted() -> bool:
        return held() or not while_held

    progress = QProgressDialog(
        f"Preparing {format_count(len(textures))} textures as {format.label}...",
        "Cancel",
        0,
        len(textures),
        parent,
    )
    progress.setWindowTitle(title)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(DELAY_MESSAGE_DURATION_MS)
    progress.setValue(0)

    job = ExportJob(textures, out_dir, format, reads, parent)
    waiting = QEventLoop()

    def progressed(done: int) -> None:
        progress.setValue(done)

        if not wanted():
            job.cancel()

    job.progressed.connect(progressed)
    job.finished.connect(waiting.quit)
    progress.canceled.connect(job.cancel)

    job.start()

    if not job.done:
        waiting.exec()

    progress.reset()
    progress.deleteLater()
    job.deleteLater()

    if job.cancelled or not wanted():
        return []

    # a drag or a copy carries what it can. one texture the cache will not give up is no
    # reason to drop the rest of the selection on the floor
    failed = set()

    for uuid, reason in job.failed:
        log.warning("leaving %s out of the files: %s", uuid, reason)
        failed.add(uuid)

    return [export_path(out_dir, texture.uuid, format) for texture in textures if texture.uuid not in failed]


def file_data(paths: list[Path]) -> QMimeData:
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])

    return data
