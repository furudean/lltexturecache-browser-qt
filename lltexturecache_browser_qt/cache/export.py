import os
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from texture_courier import Texture, TextureCacheError

from lltexturecache_browser_qt.cache.decode import GREYSCALE, RGB, RGBA, decode_texture
from lltexturecache_browser_qt.reveal import REVEAL_LIMIT

CONCURRENCY = 8

# what a texture is called while it is still being written
PARTIAL_SUFFIX = ".partial"

PNG_MODES = frozenset({"1", "L", "LA", "I", "I;16", "P", "RGB", "RGBA"})

# how a decoded texture's components are described to pillow
IMAGE_MODES = {GREYSCALE: "L", RGB: "RGB", RGBA: "RGBA"}


@dataclass(frozen=True)
class Format:
    label: str
    suffix: str
    encoder: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


FORMATS = (
    Format("Original (JPEG 2000)", "jp2"),
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
    decoded = decode_texture(codestream)

    return Image.frombytes(IMAGE_MODES[decoded.components], (decoded.width, decoded.height), decoded.pixels)


def export_path(out_dir: Path, uuid: str, format: Format) -> Path:
    return out_dir / f"{uuid}.{format.suffix}"


def write_texture(texture: Texture, path: Path, fmt: Format, reads: Lock) -> None:
    if fmt.encoder is None:
        with reads:
            jp2_bytes = texture.jpeg_2000()

        with path.open("wb") as out:
            out.write(jp2_bytes)

        return

    with reads:
        # the codestream decodes as it is, so wrapping it in a container
        # first would be work nothing downstream asks for
        codestream = texture.codestream()

    with open_image(codestream) as image:
        encodable(image, fmt).save(path, fmt.encoder, **fmt.options)


def export_texture(texture: Texture, out_dir: Path, fmt: Format, reads: Lock) -> Path:
    """Write one texture out, and hand back where it landed

    An export runs against a cache the viewer is still writing to, and a read
    that fails part way through leaves whatever was written behind it. So the
    file is built under a name of its own and moved into place once it is
    whole: what appears at the exported path is either the finished texture or
    nothing at all, never a truncated file that opens as a broken image.
    """

    path = export_path(out_dir, texture.uuid, fmt)
    partial = path.with_name(f"{path.name}{PARTIAL_SUFFIX}")

    try:
        write_texture(texture, partial, fmt, reads)

        stamp = texture.time.timestamp()
        os.utime(partial, (stamp, stamp))

        # a rename within the one directory replaces whatever was there in a
        # single step, so a re-export never blanks a good file on its way in
        partial.replace(path)
    except BaseException:
        partial.unlink(missing_ok=True)

        raise

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
