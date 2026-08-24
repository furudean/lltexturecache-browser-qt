from functools import cache

from PySide6.QtCore import QBuffer, QByteArray, QSize, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QPixmap
from texture_courier.encode import wrap_jp2

from lltexturecache_browser_qt.checkerboard import over_checkerboard
from lltexturecache_browser_qt.decode import decode_rgba, extra_components

# the box a cell's texture is fitted into, and the size everything that stands
# in for one is drawn at
THUMBNAIL_SIZE = 100


def read_image(data: QByteArray) -> QImage:
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.ReadOnly)

    return QImageReader(buffer).read()


def decode_image(codestream: bytes) -> QImage:
    if not extra_components(codestream):
        return read_image(QByteArray(wrap_jp2(codestream)))

    rgba, width, height = decode_rgba(codestream)

    # QImage does not take a copy of what it is handed, and `rgba` goes out of
    # scope with this call, so the image has to own its pixels before it leaves
    return QImage(rgba, width, height, QImage.Format.Format_RGBA8888).copy()


def thumbnail_image(png: bytes) -> QImage:
    return fit_image(read_image(QByteArray(png)))


def fit_image(image: QImage, size: int = THUMBNAIL_SIZE, *, upscale: bool = True, board: bool = True) -> QImage:
    """Fit an image to a square box, over the board if transparent"""

    if image.isNull():
        return image

    box = QSize(size, size)

    if not upscale:
        # a cell has to fill its grid square either way, but a pane with room
        # to spare is better off leaving a 32x32 texture at 32x32 than blowing
        # it up into a blur
        box = box.boundedTo(image.size())

    scaled = image.scaled(
        box,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    # a caller that draws its own board underneath wants the alpha kept, since
    # a board painted into an image is scaled along with it
    return over_checkerboard(scaled) if board else scaled


@cache
def placeholder() -> QPixmap:
    pixmap = QPixmap(THUMBNAIL_SIZE, THUMBNAIL_SIZE)
    pixmap.fill(QColor(0xFF, 0x00, 0x00))

    return pixmap
