from enum import StrEnum
from typing import ClassVar, Self

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPixmap, QPixmapCache
from PySide6.QtWidgets import QApplication

CHECKERBOARD_SIZE = 8
LIGHTNESS_THRESHOLD = 128
LIGHT_SHADE = 51
DARK_SHADE = 38

GRID_KEY = "checkerboardGrid"

LIGHT_BASE = QColor(0xFF, 0xFF, 0xFF)
DARK_BASE = QColor(0x2B, 0x2B, 0x2B)

# the square a texture is measured down to before its brightness is read off.
# small enough to be a handful of reads and large enough that a texture whose
# only opaque part is a hairline still has something left to weigh
SAMPLE_SIZE = 16


class CheckerTone(StrEnum):
    AUTO = "auto"
    LIGHT = "light"
    DARK = "dark"
    NONE = "none"


TONE_CYCLE = (CheckerTone.LIGHT, CheckerTone.DARK, CheckerTone.NONE)


class CheckerboardChanges(QObject):
    changed = Signal()

    _shared: ClassVar[Self | None] = None

    @classmethod
    def shared(cls) -> Self:
        if cls._shared is None:
            cls._shared = cls()

        return cls._shared


# every checkerboard a texture may be laid on, by the pair of colours it is made of,
# and the scheme's own pair as it stood when they were built. a decode thread
# reads these and never writes one, so a change of scheme replaces the lot here
# rather than drawing over an image already out with a thread
_checkerboards: dict[tuple[int, int], QImage] = {}
_scheme_colors: tuple[QColor, QColor] | None = None

# the tone the cells are on and the scheme they were decoded against, which is
# what says whether a cell already drawn is still the right one
_grid_state: tuple[CheckerTone, tuple[QColor, QColor] | None] | None = None

# read out of the store the first time it is asked for, which is after the app
# has a name to look one up under
_grid_tone: CheckerTone | None = None

# a look at a texture rather than a way the app is set up, so it is not kept:
# every run opens on the checkerboard the scheme would have drawn anyway
_pane_tone = CheckerTone.AUTO

# how many checkerboards the cells have been through
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


def shades(base: QColor) -> tuple[QColor, QColor]:
    # which of the two checkerboards a background makes is its own to say
    shade = DARK_SHADE if base.lightness() < LIGHTNESS_THRESHOLD else LIGHT_SHADE

    return base, shaded(base, shade)


def scheme_base() -> QColor:
    return QApplication.palette().base().color()


# the light and the dark checkerboard never move, whatever the window is doing
LIGHT_SHADES = shades(LIGHT_BASE)
DARK_SHADES = shades(DARK_BASE)


def predominant_lightness(image: QImage) -> float | None:
    sample = image

    if sample.width() > SAMPLE_SIZE or sample.height() > SAMPLE_SIZE:
        sample = image.scaled(
            SAMPLE_SIZE,
            SAMPLE_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    # a premultiplied image reports each colour already scaled by its own alpha,
    # which reads a faint white pixel as a dark grey one and would put half the
    # textures in the app on the wrong checkerboard. pixmaps are held that way, so the
    # conversion is here rather than left to whoever is asking
    if sample.format() is not QImage.Format.Format_ARGB32:
        sample = sample.convertToFormat(QImage.Format.Format_ARGB32)

    total = 0.0
    weight = 0.0

    for y in range(sample.height()):
        for x in range(sample.width()):
            # read as an integer rather than as a colour, since building a colour
            # per pixel is the expensive half of a loop this shape
            pixel = sample.pixel(x, y)
            alpha = pixel >> 24

            if not alpha:
                continue

            red, green, blue = (pixel >> 16) & 0xFF, (pixel >> 8) & 0xFF, pixel & 0xFF

            # the lightness hsl reports, which is what the threshold above is held
            # against everywhere else in here
            total += (max(red, green, blue) + min(red, green, blue)) / 2 * alpha
            weight += alpha

    return total / weight if weight else None


def pixmap_lightness(pixmap: QPixmap) -> float | None:
    if pixmap.isNull() or not pixmap.hasAlphaChannel():
        return None

    # scaled while it is still a pixmap, so a texture at its own size is not
    # copied into an image only for the copy to be thrown away
    sample = pixmap.scaled(
        SAMPLE_SIZE,
        SAMPLE_SIZE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    return predominant_lightness(sample.toImage())


def opposing_tone(lightness: float | None) -> CheckerTone | None:
    if lightness is None:
        return None

    return CheckerTone.DARK if lightness >= LIGHTNESS_THRESHOLD else CheckerTone.LIGHT


def tone_colors(tone: CheckerTone, lightness: float | None = None) -> tuple[QColor, QColor] | None:
    if tone is CheckerTone.NONE:
        return None

    if tone is CheckerTone.AUTO:
        opposed = opposing_tone(lightness)

        if opposed is None:
            # nothing to stand off, so the checkerboard goes with the window instead:
            # the scheme's own background, tint and all, which reads as part of
            # the pane rather than as something laid over it
            return _scheme_colors

        tone = opposed

    return LIGHT_SHADES if tone is CheckerTone.LIGHT else DARK_SHADES


def resolved_tone(tone: CheckerTone) -> CheckerTone:
    if tone is not CheckerTone.AUTO:
        return tone

    return CheckerTone.DARK if scheme_base().lightness() < LIGHTNESS_THRESHOLD else CheckerTone.LIGHT


def grid_tone() -> CheckerTone:
    global _grid_tone

    if _grid_tone is None:
        stored = QSettings().value(GRID_KEY)

        # a store written by a later version, or by hand, still has to open
        tones = {tone.value: tone for tone in CheckerTone}

        _grid_tone = tones.get(stored, CheckerTone.AUTO) if isinstance(stored, str) else CheckerTone.AUTO

    return _grid_tone


def set_grid_tone(tone: CheckerTone) -> None:
    global _grid_tone, _pane_tone

    # picking the checkerboard the grid is already on is still worth something while
    # the panes have been clicked off it, since it is how they are called back
    if tone == grid_tone() and tone == _pane_tone:
        return

    _grid_tone = tone
    _pane_tone = tone

    QSettings().setValue(GRID_KEY, tone.value)

    sync_checkerboard()

    CheckerboardChanges.shared().changed.emit()


def pane_tone() -> CheckerTone:
    return _pane_tone


def set_pane_tone(tone: CheckerTone) -> None:
    global _pane_tone

    if tone == _pane_tone:
        return

    _pane_tone = tone

    # the cells are not drawn against this one, so nothing is decoded again and
    # the generation the threads watch stays where it is
    CheckerboardChanges.shared().changed.emit()


def cycle_pane_tone() -> None:
    at = TONE_CYCLE.index(resolved_tone(_pane_tone))

    set_pane_tone(TONE_CYCLE[(at + 1) % len(TONE_CYCLE)])


def sync_checkerboard() -> bool:
    global _checkerboards, _scheme_colors, _grid_state, _generation

    scheme = shades(scheme_base())

    if scheme != _scheme_colors:
        _scheme_colors = scheme
        _checkerboards = {
            checkerboard_key(colors): checker_tile(*colors) for colors in (LIGHT_SHADES, DARK_SHADES, scheme)
        }

    # the tone is carried alongside the scheme, but only while the grid is one
    # that reads it: a light checkerboard is a light checkerboard whatever the
    # window is doing, and a wall of cells is not worth decoding again over a
    # palette it ignores
    state = (grid_tone(), scheme if grid_tone() is CheckerTone.AUTO else None)

    if state == _grid_state:
        return False

    _grid_state = state
    _generation += 1

    QPixmapCache.clear()

    return True


def checkerboard_key(colors: tuple[QColor, QColor]) -> tuple[int, int]:
    return colors[0].rgb(), colors[1].rgb()


def checkerboard_at(colors: tuple[QColor, QColor], square: int = CHECKERBOARD_SIZE) -> QImage:
    if square == CHECKERBOARD_SIZE:
        built = _checkerboards.get(checkerboard_key(colors))

        if built is not None:
            return built

    return checker_tile(*colors, square)


def checkerboard_generation() -> int:
    return _generation


def pane_lightness(pixmap: QPixmap) -> float | None:
    # only the automatic checkerboard looks at what it is going behind
    return pixmap_lightness(pixmap) if _pane_tone is CheckerTone.AUTO else None


def pane_colors(lightness: float | None = None) -> tuple[QColor, QColor] | None:
    """The two colours the panes lay behind a texture, or neither of them"""

    return tone_colors(_pane_tone, lightness)


def pane_checkerboard(lightness: float | None = None) -> QImage | None:
    colors = pane_colors(lightness)

    return checkerboard_at(colors) if colors is not None else None


def pane_checkerboard_at(square: int, lightness: float | None = None) -> QImage | None:
    colors = pane_colors(lightness)

    return checkerboard_at(colors, square) if colors is not None else None


def checker_tile(light: QColor, dark: QColor, square: int = CHECKERBOARD_SIZE) -> QImage:
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

    tone = grid_tone()

    # only the automatic checkerboard looks at what it is going behind, and this runs on
    # a decode thread, where the measurement is off the grid's way either way
    colors = tone_colors(tone, predominant_lightness(image) if tone is CheckerTone.AUTO else None)

    # with no checkerboard to paint, the transparency is left as it is and whatever the
    # cell is drawn against shows through it
    if colors is None:
        return image

    checkerboard = checkerboard_at(colors)

    backed = QImage(image.size(), QImage.Format.Format_RGB32)

    painter = QPainter(backed)
    painter.fillRect(backed.rect(), QBrush(checkerboard))
    painter.drawImage(0, 0, image)
    painter.end()

    return backed
