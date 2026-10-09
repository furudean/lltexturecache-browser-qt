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

# the formats qt's png reader hands a thumbnail back in, which scale a touch
# differently from the packed ones a decode is described in
THUMBNAIL_FORMATS = {
    GREYSCALE: QImage.Format.Format_Grayscale8,
    RGB: QImage.Format.Format_RGB32,
    RGBA: QImage.Format.Format_ARGB32,
}

# the box a cell's texture is fitted into, and the size everything that stands
# in for one is drawn at
THUMBNAIL_SIZE = 100


def decode_image(codestream: bytes, threads: int = 1) -> QImage:
    decoded = decode_texture(codestream, threads)

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


def thumbnail_pixels(kept: Thumbnail) -> QImage:
    """A cache thumbnail as an image, straight from the rows the viewer kept"""

    pixels = kept.pixels
    components = kept.components

    if len(pixels) != kept.width * kept.height * components:
        return QImage()

    if components == 2:
        # greyscale with opacity alongside, which qt has no format for, so the
        # one colour component is spread over three the way a decode's is
        grey = pixels[0::2]
        spread = bytearray(len(pixels) * 2)
        spread[0::4] = grey
        spread[1::4] = grey
        spread[2::4] = grey
        spread[3::4] = pixels[1::2]

        pixels = bytes(spread)
        components = RGBA

    image = QImage(pixels, kept.width, kept.height, kept.width * components, IMAGE_FORMATS[components])

    # the rows run bottom up, the way gl takes them. the flip is a copy, so the
    # image owns its pixels before they go out of scope
    return image.flipped(Qt.Orientation.Vertical).convertToFormat(THUMBNAIL_FORMATS[components])


def thumbnail_image(
    kept: Thumbnail,
    size: int = THUMBNAIL_SIZE,
    *,
    checkerboard: bool = True,
    ratio: float = 1.0,
) -> QImage:
    return fit_image(thumbnail_pixels(kept), size, checkerboard=checkerboard, ratio=ratio)


def fit_image(
    image: QImage,
    size: int | None = THUMBNAIL_SIZE,
    *,
    upscale: bool = True,
    checkerboard: bool = True,
    ratio: float = 1.0,
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
    return over_checkerboard(scaled, ratio) if checkerboard else scaled


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
