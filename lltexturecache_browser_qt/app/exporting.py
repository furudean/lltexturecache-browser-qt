"""Running an export against a window

An export is a job on a thread pool, a progress dialog over the window, and a
line on the status bar once it lands, plus the menus that have to stay shut
while it runs. Threading those together is a job of its own, so a window keeps
one of these while an export is out and asks it what it needs to know.
"""

from collections.abc import Callable
from functools import partial
from pathlib import Path
from threading import Lock

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QProgressDialog, QWidget
from texture_courier import Texture

from lltexturecache_browser_qt.cache.export import ExportJob, Format
from lltexturecache_browser_qt.reveal import reveal
from lltexturecache_browser_qt.view.formatting import format_count

# how long a progress dialog waits before coming up, so a short export runs to
# the end without a window flashing over the one being worked in
DELAY_MESSAGE_DURATION_MS = 250


def ask_for_directory(parent: QWidget, textures: list[Texture], format: Format) -> Path | None:
    """Where to write an export, or nothing if it was called off"""

    dialog = QFileDialog(parent, f"Export {format_count(len(textures))} textures as {format.label}")
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setLabelText(QFileDialog.DialogLabel.Accept, "Export")

    return Path(dialog.selectedFiles()[0]) if dialog.exec() else None


def export_summary(out_dir: Path, written: int, failed: int, *, cancelled: bool) -> str:
    """What an export left behind, as the status bar says it"""

    note = "Cancelled export of" if cancelled else "Exported"
    summary = f"{note} {format_count(written)} texture(s) to {out_dir}"

    return f"{summary} ({format_count(failed)} could not be written)" if failed else summary


def show_written(out_dir: Path, paths: list[Path]) -> None:
    """Put the exported files in front of the user

    Picked out in a file manager where one will do it, and failing that by
    opening the directory they went to, which every platform manages.
    """

    if not reveal(paths):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))


class ExportRun:
    """One export, from the progress dialog going up to the report coming back"""

    def __init__(
        self,
        parent: QWidget,
        textures: list[Texture],
        out_dir: Path,
        format: Format,
        reads: Lock,
        *,
        done: Callable[[str], None],
    ) -> None:
        self._out_dir = out_dir
        self._done = done

        self._progress = QProgressDialog(
            f"Exporting {format_count(len(textures))} textures as {format.label}...",
            "Cancel",
            0,
            len(textures),
            parent,
        )
        self._progress.setWindowTitle("Export")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(DELAY_MESSAGE_DURATION_MS)
        self._progress.setValue(0)

        self._job = ExportJob(textures, out_dir, format, reads, parent)
        self._job.progressed.connect(self._progress.setValue)
        self._job.finished.connect(partial(self.finished))

        self._progress.canceled.connect(self._job.cancel)

    def start(self) -> None:
        self._job.start()

    def shutdown(self) -> None:
        self._job.shutdown()

    def finished(self, written: int, failed: int, cancelled: bool) -> None:
        self._progress.reset()
        self._progress.deleteLater()

        paths = self._job.written_paths

        self._job.deleteLater()

        self._done(export_summary(self._out_dir, written, failed, cancelled=cancelled))

        if written and not cancelled:
            show_written(self._out_dir, paths)
