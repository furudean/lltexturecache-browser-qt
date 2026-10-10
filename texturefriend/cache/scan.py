import logging
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtGui import QImage
from texture_courier import Texture, TextureCacheError, Thumbnail

from texturefriend.cache.color import (
    BLIND_BASE_BYTES,
    CLEAR_MIN_PIXELS,
    FLAT_BASE_BYTES,
    FLAT_MAX_DENSITY,
    ColorIndex,
    Signature,
    signature,
)
from texturefriend.cache.likeness import Descriptor, LikenessIndex, describe
from texturefriend.view.images import thumbnail_pixels

log = logging.getLogger(__name__)

PLACEHOLDER_BYTE = 0x80

SLICE_SECONDS = 0.004


def placeholder(kept: Thumbnail) -> bool:
    return bool(kept.pixels) and kept.pixels.count(PLACEHOLDER_BYTE) == len(kept.pixels)


@dataclass(frozen=True)
class Scan:
    """What a pass over a cache found, a row to an entry"""

    colors: ColorIndex
    likeness: LikenessIndex


@dataclass(frozen=True)
class Traits:
    signature: Signature | None
    descriptor: Descriptor | None


type Stamp = tuple[str, int, int]

type KnownTraits = dict[Stamp, Traits]


def stamp(texture: Texture) -> Stamp:
    return texture.uuid, texture.image_size, texture.body_size


def forget_gone(known: KnownTraits, textures: Iterable[Texture]) -> None:
    """Drop the traits of textures the cache has evicted or rewritten"""

    live = {stamp(texture) for texture in textures}

    for key in [key for key in known if key not in live]:
        del known[key]


class CacheScan(QObject):
    done = Signal(object)

    def __init__(
        self,
        textures: list[Texture],
        known: KnownTraits | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)

        self._known: KnownTraits = known if known is not None else {}

        self._left: Iterator[tuple[int, Texture]] | None = enumerate(textures)

        self._colors = ColorIndex(len(textures))
        self._likeness = LikenessIndex(len(textures))

        # a zero interval fires once per pass of the event loop, so a slice runs
        # after whatever input and repaints were waiting
        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.step)

    def start(self) -> None:
        self.resume()

    def cancel(self) -> None:
        self._left = None
        self._timer.stop()

    def pause(self) -> None:
        self._timer.stop()

    def resume(self) -> None:
        if self._left is not None:
            self._timer.start()

    @Slot()
    def step(self) -> None:
        left = self._left

        if left is None:
            return

        stop = time.perf_counter() + SLICE_SECONDS

        for row, texture in left:
            self.read(row, texture)

            if time.perf_counter() >= stop:
                return

        self.cancel()
        self.done.emit(Scan(self._colors, self._likeness))

    def read(self, row: int, texture: Texture) -> None:
        key = stamp(texture)
        found = self._known.get(key)

        if found is None:
            found = self.traits(texture)

            if found is None:
                return

            self._known[key] = found

        if found.signature is not None:
            self._colors.add(row, found.signature)

        if found.descriptor is not None:
            self._likeness.add(row, found.descriptor)

    def traits(self, texture: Texture) -> Traits | None:
        kept = self.thumbnail(texture)

        if kept is None:
            return None

        image = thumbnail_pixels(kept)

        if image.isNull():
            return None

        return Traits(self.signature(texture, kept, image), describe(image))

    def thumbnail(self, texture: Texture) -> Thumbnail | None:
        try:
            kept = texture.thumbnail
        except (TextureCacheError, OSError) as e:
            # a texture with no readable thumbnail has nothing to be filed
            # under, which leaves it out of the indexes rather than stopping the scan
            log.debug("no thumbnail for %s: %s", texture.uuid, e)

            return None

        if kept is not None and placeholder(kept):
            log.debug("thumbnail for %s is the viewer's fill", texture.uuid)

            return None

        return kept

    def signature(self, texture: Texture, kept: Thumbnail, image: QImage) -> Signature | None:
        found = signature(image)

        if found is None or not found.flat:
            return found

        if not texture.whole() or self.dense(texture, kept, clear=found.clear):
            return replace(found, flat=False, clear=False)

        return found

    def dense(self, texture: Texture, kept: Thumbnail, *, clear: bool = False) -> bool:
        if not kept.width or not kept.height:
            return False

        if kept.width * kept.height == 1:
            return texture.image_size > BLIND_BASE_BYTES

        width, height = kept.source_dimensions
        pixels = width * height

        if clear and pixels < CLEAR_MIN_PIXELS:
            return False

        return texture.image_size > FLAT_BASE_BYTES + pixels * FLAT_MAX_DENSITY
