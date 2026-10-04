from functools import cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QPixmap
from texture_courier import Thumbnail

from lltexturecache_browser_qt.cache.decode import GREYSCALE, RGB, RGBA, decode_texture
from lltexturecache_browser_qt.view.checkerboard import over_checkerboard

# how a decoded texture's components are described to qt
IMAGE_FORMATS = {
    GREYSCALE: QImage.Format.Format_Grayscale8,
    RGB: QImage.Format.Format_RGB888,
    RGBA: QImage.Format.Format_RGBA8888,
}

SCALING_FORMATS = {
    RGB: QImage.Format.Format_RGB32,
    RGBA: QImage.Format.Format_ARGB32,
}

# the box a cell's texture is fitted into, and the size everything that stands
# in for one is drawn at
THUMBNAIL_SIZE = 100


def decode_image(codestream: bytes) -> QImage:
    decoded = decode_texture(codestream)

    # the rows are packed tight, which is not the alignment QImage assumes when
    # it is left to work the stride out for itself
    image = QImage(
        decoded.pixels,
        decoded.width,
        decoded.height,
        decoded.stride,
        IMAGE_FORMATS[decoded.components],
    )

    # QImage does not take a copy of what it is handed, and the pixels go out of
    # scope with this call, so the image has to own them before it leaves
    return image.copy()


def read_thumbnail(thumbnail: Thumbnail) -> QImage:
    format = IMAGE_FORMATS.get(thumbnail.components)
    stride = thumbnail.width * thumbnail.components

    if format is None or len(thumbnail.pixels) != stride * thumbnail.height:
        return QImage()

    # the rows are packed tight and stored bottom up. converting gives the
    # image its own copy of the pixels, which it can then flip in place
    image = QImage(thumbnail.pixels, thumbnail.width, thumbnail.height, stride, format)
    image = image.convertToFormat(SCALING_FORMATS.get(thumbnail.components, format))
    image.flip(Qt.Orientation.Vertical)

    return image


def thumbnail_image(thumbnail: Thumbnail, *, checkerboard: bool = True) -> QImage:
    return fit_image(read_thumbnail(thumbnail), checkerboard=checkerboard)


def fit_image(
    image: QImage, size: int | None = THUMBNAIL_SIZE, *, upscale: bool = True, checkerboard: bool = True
) -> QImage:
    """Fit an image to a square box, over the checkerboard if transparent"""

    if image.isNull():
        return image

    if size is None:
        scaled = image
    else:
        box = QSize(size, size)

        if not upscale:
            # a cell has to fill its grid square either way, but a pane with
            # room to spare is better off leaving a 32x32 texture at 32x32 than
            # blowing it up into a blur
            box = box.boundedTo(image.size())

        scaled = image.scaled(
            box,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    # a caller that draws its own checkerboard underneath wants the alpha kept, since
    # a checkerboard painted into an image is scaled along with it
    return over_checkerboard(scaled) if checkerboard else scaled


@cache
def placeholder() -> QPixmap:
    pixmap = QPixmap(THUMBNAIL_SIZE, THUMBNAIL_SIZE)
    pixmap.fill(QColor(0xFF, 0x00, 0x00))

    return pixmap


def image_file(path: Path) -> QImage:
    """Whatever qt can read out of the file, or a null image if it is not a picture"""

    reader = QImageReader(str(path))
    reader.setAutoTransform(True)

    return reader.read()


def readable_image(path: Path) -> bool:
    """Whether the file is one qt would have a reader for

    Off the file rather than off its name: a screenshot dragged out of another
    app arrives under whatever name that app gave it, and qt sniffs the bytes.
    """

    return path.is_file() and QImageReader(str(path)).canRead()


def image_filter() -> str:
    """The file dialog's filters, over whatever formats this build of qt reads

    With everything else behind them, since the reader goes by the bytes and
    the filter can only go by the name: a screenshot saved by another app
    arrives under whatever name that app gave it, extension or none.
    """

    suffixes = sorted({QByteArray(format).toStdString() for format in QImageReader.supportedImageFormats()})
    images = " ".join(f"*.{suffix}" for suffix in suffixes)

    return f"Images ({images});;All Files (*)"
