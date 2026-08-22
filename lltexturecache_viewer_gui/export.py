import os
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from texture_courier import Texture
from texture_courier.core import TextureCacheError
from texture_courier.encode import wrap_jp2

from lltexturecache_viewer_gui.decode import decode_rgba, extra_components
from lltexturecache_viewer_gui.reveal import REVEAL_LIMIT

CONCURRENCY = 8

PNG_MODES = frozenset({"1", "L", "LA", "I", "I;16", "P", "RGB", "RGBA"})


@dataclass(frozen=True)
class Format:
    label: str
    suffix: str
    encoder: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


FORMATS = (
    Format("JPEG 2000", "jp2"),
    Format("PNG", "png", encoder="PNG"),
    Format("TIFF", "tif", encoder="TIFF", options={"compression": "tiff_lzw"}),
)

DEFAULT_FORMAT = FORMATS[0]


def encodable(image: Image.Image, format: Format) -> Image.Image:
    if format.encoder == "PNG" and image.mode not in PNG_MODES:
        return image.convert("RGBA")

    # tiff can natively handle the alpha without widening

    return image


def open_image(codestream: bytes) -> Image.Image:
    if not extra_components(codestream):
        return Image.open(BytesIO(wrap_jp2(codestream)))

    rgba, width, height = decode_rgba(codestream)

    return Image.frombytes("RGBA", (width, height), rgba)


def export_path(out_dir: Path, uuid: str, format: Format) -> Path:
    return out_dir / f"{uuid}.{format.suffix}"


def export_texture(texture: Texture, out_dir: Path, fmt: Format, reads: Lock) -> Path:
    with reads:
        codestream = texture.loads_j2c()

    path = export_path(out_dir, texture.uuid, fmt)

    if fmt.encoder is None:
        path.write_bytes(wrap_jp2(codestream))
    else:
        with open_image(codestream) as image:
            encodable(image, fmt).save(path, fmt.encoder, **fmt.options)

    os.utime(path, (texture.time.timestamp(), texture.time.timestamp()))

    return path


class ExportSignals(QObject):
    # (uuid, error reason)
    done = Signal(str, str)


class ExportTask(QRunnable):
    def __init__(self, texture: Texture, out_dir: Path, format: Format, reads: Lock, signals: ExportSignals):
        super().__init__()

        self._texture = texture
        self._out_dir = out_dir
        self._format = format
        self._reads = reads
        self._signals = signals

    @Slot()
    def run(self) -> None:
        try:
            export_texture(self._texture, self._out_dir, self._format, self._reads)
        except (TextureCacheError, OSError, ValueError) as e:
            self._signals.done.emit(self._texture.uuid, str(e) or type(e).__name__)
        else:
            self._signals.done.emit(self._texture.uuid, "")


class ExportJob(QObject):
    progressed = Signal(int)
    finished = Signal(int, int, bool)

    def __init__(
        self,
        textures: list[Texture],
        out_dir: Path,
        format: Format,
        reads: Lock,
        parent: QObject | None = None,
    ):
        super().__init__(parent)

        self._textures = textures
        self._out_dir = out_dir
        self._format = format
        self._reads = reads

        self._next = 0
        self._running = 0
        self._written = 0
        self._paths: list[Path] = []
        self._failed: list[tuple[str, str]] = []
        self._cancelled = False
        self._finished = False

        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(CONCURRENCY)

        self._signals = ExportSignals(self)
        self._signals.done.connect(self.wrote)

    @property
    def written_paths(self) -> list[Path]:
        return list(self._paths)

    @property
    def failed(self) -> list[tuple[str, str]]:
        return list(self._failed)

    def start(self) -> None:
        self.pump()

        # a job with nothing in it has already done all of it
        if self._running == 0:
            self.finish()

    def cancel(self) -> None:
        self._cancelled = True

    def pump(self) -> None:
        while not self._cancelled and self._next < len(self._textures) and self._running < CONCURRENCY:
            texture = self._textures[self._next]

            self._next += 1
            self._running += 1

            self._pool.start(ExportTask(texture, self._out_dir, self._format, self._reads, self._signals))

    @Slot(str, str)
    def wrote(self, uuid: str, error: str) -> None:
        self._running -= 1

        if error:
            self._failed.append((uuid, error))
        else:
            self._written += 1

            if len(self._paths) < REVEAL_LIMIT + 1:
                self._paths.append(export_path(self._out_dir, uuid, self._format))

        self.pump()

        self.progressed.emit(self._written + len(self._failed))

        if self._running == 0:
            self.finish()

    def finish(self) -> None:
        if self._finished:
            return

        self._finished = True

        self.finished.emit(self._written, len(self._failed), self._cancelled)

    def shutdown(self) -> None:
        self._signals.done.disconnect(self.wrote)

        self.cancel()

        self._pool.clear()
        self._pool.waitForDone()
