"""The one pass over a cache that answers everything the grid can be asked

Which colours a texture holds, whether it holds a picture at all, and what
that picture looks like all come out of the same thumbnail the viewer kept
beside each entry. Reading every one of them takes long enough to be worth
doing off the ui thread, and once is enough, so the pass is made the once and
hands back an index for each question.
"""

import logging
import threading
from dataclasses import dataclass, replace

from PySide6.QtCore import QByteArray, QObject, QRunnable, Signal, Slot
from PySide6.QtGui import QImage
from texture_courier import Texture, TextureCacheError, Thumbnail

from lltexturecache_browser_qt.cache.color import (
    BLIND_BASE_BYTES,
    CLEAR_MIN_PIXELS,
    FLAT_BASE_BYTES,
    FLAT_MAX_DENSITY,
    ColorIndex,
    Signature,
    signature,
)
from lltexturecache_browser_qt.cache.likeness import LikenessIndex, describe
from lltexturecache_browser_qt.view.images import read_image

log = logging.getLogger(__name__)

PLACEHOLDER_BYTE = 0x80


def placeholder(kept: Thumbnail) -> bool:
    return bool(kept.pixels) and kept.pixels.count(PLACEHOLDER_BYTE) == len(kept.pixels)


@dataclass(frozen=True)
class Scan:
    """What a pass over a cache found, a row to an entry"""

    colors: ColorIndex
    likeness: LikenessIndex


class ScanSignals(QObject):
    done = Signal(object)


class CacheScan(QRunnable):
    """Reads every thumbnail in a cache, off the ui thread"""

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
        count = len(self._textures)

        colors = ColorIndex(count)
        likeness = LikenessIndex(count)

        for row, texture in enumerate(self._textures):
            if self._stopped.is_set():
                return

            kept = self.thumbnail(texture)

            if kept is None:
                continue

            image = read_image(QByteArray(kept.png()))

            if image.isNull():
                continue

            found = self.signature(texture, kept, image)

            if found is not None:
                colors.add(row, found)

            described = describe(image)

            if described is not None:
                likeness.add(row, described)

        if self._stopped.is_set():
            return

        try:
            self._signals.done.emit(Scan(colors, likeness))
        except RuntimeError:
            # the model this was reading for went out from under it between the
            # check above and here, taking the signals it reports through along
            log.debug("cache scan finished after its model closed", exc_info=True)

    def thumbnail(self, texture: Texture) -> Thumbnail | None:
        try:
            # the thumbnails all come out of the one file, the same as the reads
            # the grid makes, so this waits its turn among them
            with self._thumbnails:
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

        if found is not None and found.flat and self.dense(texture, kept, clear=found.clear):
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
