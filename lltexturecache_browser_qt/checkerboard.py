from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPixmapCache
from PySide6.QtWidgets import QApplication

CHECKEDBOARD_SIZE = 8
LIGHTNESS_THRESHOLD = 128
LIGHT_SHADE = 51
DARK_SHADE = 38

# the board the decode threads paint with, and the palette it was built for. a
# thread partway through a paint holds the tile it started with, since a change
# of scheme puts a new image up here rather than drawing over the one already out
_checkerboard = QImage()
_checker_colors: tuple[QColor, QColor] | None = None

# how many boards the textures have been through
_generation = 0


def shaded(color: QColor, by: int) -> QColor:
    lightness = color.lightness()

    # neither end of the range has anywhere to go but inwards, and a background
    # sits at one end or the other in any scheme worth calling light or dark
    step = by if lightness < LIGHTNESS_THRESHOLD else -by

    # hsl leaves whatever tint a scheme gives its background where it is, and an
    # untinted grey reports no hue at all, which is not a hue hsl will take back
    lifted = QColor(color)
    lifted.setHsl(max(color.hue(), 0), color.saturation(), min(max(lightness + step, 0), 255))

    return lifted.toRgb()


def checker_colors() -> tuple[QColor, QColor]:
    base = QApplication.palette().base().color()

    # which of the two boards that makes it is the scheme's own to say
    shade = DARK_SHADE if base.lightness() < LIGHTNESS_THRESHOLD else LIGHT_SHADE

    return base, shaded(base, shade)


def sync_checkerboard() -> bool:
    global _checkerboard, _checker_colors, _generation

    colors = checker_colors()

    if colors == _checker_colors:
        return False

    _checkerboard = checker_tile(*colors)
    _checker_colors = colors
    _generation += 1

    QPixmapCache.clear()

    return True


def checkerboard() -> QImage:
    if _checkerboard.isNull():
        sync_checkerboard()

    return _checkerboard


def checkerboard_generation() -> int:
    return _generation


def checkerboard_at(square: int) -> QImage:
    board = checkerboard()

    if square == CHECKEDBOARD_SIZE or _checker_colors is None:
        return board

    return checker_tile(*_checker_colors, square)


def checker_tile(light: QColor, dark: QColor, square: int = CHECKEDBOARD_SIZE) -> QImage:
    tile = QImage(square * 2, square * 2, QImage.Format.Format_RGB32)
    tile.fill(light)

    painter = QPainter(tile)
    painter.fillRect(0, 0, square, square, dark)
    painter.fillRect(square, square, square, square, dark)
    painter.end()

    return tile


def over_checkerboard(image: QImage) -> QImage:
    if not image.hasAlphaChannel():
        return image

    backed = QImage(image.size(), QImage.Format.Format_RGB32)

    painter = QPainter(backed)
    painter.fillRect(backed.rect(), QBrush(checkerboard()))
    painter.drawImage(0, 0, image)
    painter.end()

    return backed
