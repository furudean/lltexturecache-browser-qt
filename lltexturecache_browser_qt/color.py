import threading
from collections import Counter
from collections.abc import Iterable, Sequence
from functools import cache
from math import cbrt, dist, exp, hypot

from PySide6.QtCore import QByteArray, QObject, QRunnable, Signal, Slot
from PySide6.QtGui import QColor, QImage
from texture_courier import Texture, TextureCacheError

from lltexturecache_browser_qt.images import read_image

type Lab = tuple[float, float, float]

# how many colors are kept for a texture. a thumbnail is a few hundred pixels,
# and past a handful of colors the rest of them are specks
CLUSTERS = 5

# a pixel this faint shows none of its color, whatever the color is. above it
# a pixel counts for as much of itself as it is opaque, so a pane of glass or a
# haze of smoke is read as the little color it puts up rather than as a wall
ALPHA_FLOOR = 32

# how much of a texture has to be opaque before it is judged on its opaque
# pixels alone. under this the score is scaled down to match, so a texture that
# is three visible pixels of red does not outrank one that is red all over
MIN_COVERAGE = 0.1

# the lab bins the pixels are gathered into. a texture's colors are whatever
# survives rounding at this scale, which is a little coarser than the step at
# which anyone would give two colors different names
BIN_L = 12.0
BIN_AB = 16.0

# light and shadow move a texture's lightness much further than they move its
# hue, so a lit and a shaded patch of one paint should read as the one color.
# a color with no hue to go on has only its lightness to be told apart by,
# though, or every grey in a cache answers for black, so the discount is let
# out again as the color asked for loses its chroma
LIGHTNESS_WEIGHT = 0.45
FULL_CHROMA = 60.0

# how much a difference in chroma counts, next to a difference in hue. dust,
# wear and distance wash a color out without moving it round the wheel, the
# same way light and shadow move its lightness, so a faded red is still the red
# that was asked for. the discount fades out as either of the two colors greys,
# for the reason the one above fades: a color with no hue has nothing but its
# chroma to be told apart by, and discounting that hands every grey in the
# cache to whatever was asked for
CHROMA_WEIGHT = 2.0

# how much further apart lab writes a difference at chroma and at hue as a pair
# of colors moves out from grey, from cie's own correction. both are room let
# out, which `tightening` pays back over the query so that letting it out
# changes the shape of a match without changing how far one reaches
CHROMA_TOLERANCE = 0.045
HUE_TOLERANCE = 0.015

# the distance at which a color has fallen to about a third of a match, in the
# weighted lab the rest of this works in
SIGMA = 14.0

# how near two of a texture's own colors have to be before they are the one
# color. a bin edge is an arbitrary place to cut a patch that shades smoothly
# across it, and most textures lose a slot or more to halves that would answer
# alike to anything asked of them, so what putting those back together frees
# goes to colors that really are distinct.
#
# nothing to do with SIGMA, near as the two numbers are: this one says when two
# colors are one color, and that one says when a color answers for another.
# further out than this the halves being joined stop being halves of anything,
# and one centroid ends up standing in for two colors nobody would give the
# same name to
MERGE = 11.0

# how far out a color is still worth working out the falloff for, in sigmas
CUTOFF = 3.0

# how much of a texture has to be near a color before it is worth showing
MATCH_FLOOR = 0.12

# bits of each channel a color is rounded to before it is counted, which is
# 32768 colors and an error too small to move a texture in the ranking
QUANTUM = 5
LEVELS = 1 << QUANTUM

# the rounding itself, as the byte for byte table `bytes.translate` takes. the
# ends of the range stay where they are, so black and white, which are the two
# colors anyone reaches for first, land exactly on themselves
QUANTIZE = bytes(round((value >> (8 - QUANTUM)) * 255 / (LEVELS - 1)) for value in range(256))

# srgb's transfer curve, which is the only per channel work in the conversion
LINEAR = [value / 3294.6 if value <= 10 else ((value / 255 + 0.055) / 1.055) ** 2.4 for value in range(256)]

# the two constants cielab is cut at, and the d65 white srgb is written against
EPSILON = 216 / 24389
KAPPA = 24389 / 27
WHITE_X = 0.95047
WHITE_Z = 1.08883


@cache
def to_lab(rgb: int) -> Lab:
    """CIELAB for a packed rgb color, which is a space distance means something in

    Kept, since a cache is read one rounded color at a time and the same few
    thousand of them come round again and again.
    """

    red = LINEAR[(rgb >> 16) & 0xFF]
    green = LINEAR[(rgb >> 8) & 0xFF]
    blue = LINEAR[rgb & 0xFF]

    x = (0.4124564 * red + 0.3575761 * green + 0.1804375 * blue) / WHITE_X
    y = 0.2126729 * red + 0.7151522 * green + 0.0721750 * blue
    z = (0.0193339 * red + 0.1191920 * green + 0.9503041 * blue) / WHITE_Z

    fx = cbrt(x) if x > EPSILON else (KAPPA * x + 16) / 116
    fy = cbrt(y) if y > EPSILON else (KAPPA * y + 16) / 116
    fz = cbrt(z) if z > EPSILON else (KAPPA * z + 16) / 116

    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def lab_of(color: QColor) -> Lab:
    return to_lab((color.red() << 16) | (color.green() << 8) | color.blue())


def hueness(chroma: float) -> float:
    return min(chroma, FULL_CHROMA) / FULL_CHROMA


def lightness_weight(target: Lab) -> float:
    return 1.0 - (1.0 - LIGHTNESS_WEIGHT) * hueness(hypot(target[1], target[2]))


def tightening(target_chroma: float) -> float:
    room = (
        (1.0 + (CHROMA_WEIGHT - 1.0) * hueness(target_chroma))
        * (1.0 + CHROMA_TOLERANCE * target_chroma)
        * (1.0 + HUE_TOLERANCE * target_chroma)
    )

    return cbrt(room * room)


def counted(image: QImage) -> Counter[int]:
    argb = image.convertToFormat(QImage.Format.Format_ARGB32)

    # a row of 32 bit pixels is never padded out, so the buffer holds the
    # pixels and nothing besides, in the order a word of argb reads back in
    packed = bytes(argb.constBits()).translate(QUANTIZE)

    return Counter(memoryview(packed).cast("I"))


def signature(image: QImage) -> list[tuple[Lab, float]] | None:
    if image.isNull():
        return None

    counts = counted(image)
    gathered: dict[tuple[int, int, int], list[float]] = {}

    total = 0
    shown = 0.0

    for pixel, count in counts.items():
        total += count

        alpha = pixel >> 24

        if alpha < ALPHA_FLOOR:
            continue

        weight = count * (alpha / 255)
        shown += weight

        lightness, green_red, blue_yellow = to_lab(pixel & 0xFFFFFF)

        # rounding to a bin is a cluster of the only kind a few hundred pixels
        # can support, and unlike a k-means it lands in the same place each run
        key = (round(lightness / BIN_L), round(green_red / BIN_AB), round(blue_yellow / BIN_AB))
        bin = gathered.get(key)

        if bin is None:
            gathered[key] = [weight, lightness * weight, green_red * weight, blue_yellow * weight]
        else:
            bin[0] += weight
            bin[1] += lightness * weight
            bin[2] += green_red * weight
            bin[3] += blue_yellow * weight

    if not shown:
        return None

    coverage = min(1.0, shown / (total * MIN_COVERAGE))

    top = sorted(merged(gathered.values()), key=lambda bin: bin[0], reverse=True)[:CLUSTERS]

    return [
        ((lightness, green_red, blue_yellow), weight / shown * coverage)
        for weight, lightness, green_red, blue_yellow in top
    ]


def merged(bins: Iterable[list[float]]) -> list[list[float]]:
    """The bins as their centroids, with any that are the one color put back together

    Working down from the heaviest bin, since that is the one a split has left
    most of the color in and so the one the rest of it should be gathered onto.
    """

    centroids = sorted(
        ([weight, sum_l / weight, sum_a / weight, sum_b / weight] for weight, sum_l, sum_a, sum_b in bins),
        key=lambda bin: bin[0],
        reverse=True,
    )

    kept: list[list[float]] = []

    for weight, lightness, green_red, blue_yellow in centroids:
        for into in kept:
            if dist((lightness, green_red, blue_yellow), into[1:]) >= MERGE:
                continue

            # where one bin would have put the centroid, had the edge not
            # fallen across the patch
            heavier = into[0]
            into[0] = heavier + weight
            into[1] = (into[1] * heavier + lightness * weight) / into[0]
            into[2] = (into[2] * heavier + green_red * weight) / into[0]
            into[3] = (into[3] * heavier + blue_yellow * weight) / into[0]

            break
        else:
            kept.append([weight, lightness, green_red, blue_yellow])

    return kept


class ColorIndex:
    def __init__(self, count: int) -> None:
        self._count = count

        self._rows: list[int] = []
        self._lightness: list[float] = []
        self._green_red: list[float] = []
        self._blue_yellow: list[float] = []
        self._chroma: list[float] = []
        self._weights: list[float] = []

    def __len__(self) -> int:
        return self._count

    def add(self, row: int, colors: list[tuple[Lab, float]]) -> None:
        for (lightness, green_red, blue_yellow), weight in colors:
            self._rows.append(row)
            self._lightness.append(lightness)
            self._green_red.append(green_red)
            self._blue_yellow.append(blue_yellow)

            # scoring reads this off every entry it walks, once for each
            # color it is asked about, so it is worked out the once here
            self._chroma.append(hypot(green_red, blue_yellow))

            self._weights.append(weight)

    def scores(self, colors: Sequence[QColor]) -> list[float]:
        """How much of each texture is near every one of the colors asked for

        A texture is scored by the color it holds the least of, so the ones
        that answer for the whole set come out ahead of the ones that only
        answer for part of it.
        """

        if not colors:
            return [1.0] * self._count

        scored: list[float] | None = None

        for color in colors:
            against = self.matches(color)
            scored = against if scored is None else list(map(min, scored, against))

        return scored if scored is not None else [1.0] * self._count

    def matches(self, color: QColor) -> list[float]:
        """How much of each texture is near the one color"""

        target_l, target_a, target_b = lab_of(color)
        target_chroma = hypot(target_a, target_b)

        lightness_falls = lightness_weight((target_l, target_a, target_b))
        paid_back = tightening(target_chroma)
        discount = CHROMA_WEIGHT - 1.0

        falloff = 1.0 / (SIGMA * SIGMA)
        cutoff = (CUTOFF * SIGMA) ** 2

        match = [0.0] * self._count

        # the lists come out of self up front, since the loop below runs once
        # for every color every texture in the cache shows
        rows = self._rows
        lightness = self._lightness
        green_red = self._green_red
        blue_yellow = self._blue_yellow
        chroma = self._chroma
        weights = self._weights

        for entry, row in enumerate(rows):
            entry_chroma = chroma[entry]

            delta_l = (lightness[entry] - target_l) * lightness_falls
            delta_a = green_red[entry] - target_a
            delta_b = blue_yellow[entry] - target_b

            # what is left of the ab difference once the part of it that runs
            # along chroma is taken out is the part that runs round the wheel,
            # which is the difference in hue and the one that is kept whole
            delta_chroma = entry_chroma - target_chroma
            delta_hue = max(delta_a * delta_a + delta_b * delta_b - delta_chroma * delta_chroma, 0.0)

            # the chroma discount goes only as far as the greyer of the two
            # has hue to trade: a color with no chroma has no hue either, so
            # the whole of its difference lands here, and discounting that
            # would hand every grey in the cache to whatever was asked for
            mean_chroma = (entry_chroma + target_chroma) * 0.5
            shared = 1.0 + discount * hueness(min(entry_chroma, target_chroma))

            at_chroma = delta_chroma / (shared * (1.0 + CHROMA_TOLERANCE * mean_chroma))
            at_hue = 1.0 + HUE_TOLERANCE * mean_chroma

            distance = paid_back * (delta_l * delta_l + at_chroma * at_chroma + delta_hue / (at_hue * at_hue))

            # a color this far off counts for nothing either way, and asking
            # costs far less than working out how little
            if distance < cutoff:
                match[row] += weights[entry] * exp(-distance * falloff)

        return match


class ScanSignals(QObject):
    done = Signal(object)


class ColorScan(QRunnable):
    """Reads the colors of every texture in a cache, off the ui thread"""

    def __init__(self, textures: list[Texture], thumbnails: threading.Lock, signals: ScanSignals) -> None:
        super().__init__()

        self._textures = textures
        self._thumbnails = thumbnails
        self._signals = signals
        self._stopped = threading.Event()

    def cancel(self) -> None:
        self._stopped.set()

    @Slot()
    def run(self) -> None:
        index = ColorIndex(len(self._textures))

        for row, texture in enumerate(self._textures):
            if self._stopped.is_set():
                return

            colors = self.read(texture)

            if colors is not None:
                index.add(row, colors)

        if not self._stopped.is_set():
            self._signals.done.emit(index)

    def read(self, texture: Texture) -> list[tuple[Lab, float]] | None:
        try:
            # the thumbnails all come out of the one file, the same as the reads
            # the grid makes, so this waits its turn among them
            with self._thumbnails:
                thumbnail = texture.thumbnail_png()
        except (TextureCacheError, OSError):
            return None

        if thumbnail is None:
            return None

        return signature(read_image(QByteArray(thumbnail)))
