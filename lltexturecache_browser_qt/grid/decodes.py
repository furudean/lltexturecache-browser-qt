"""The bigger decodes the panes ask for

The grid decodes every texture down to a cell. The inspector and the preview
each want one texture at a time and at a size of their own, so each keeps its
own small store rather than competing with the wall of cells for room in the
pixmap cache.
"""

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QPixmap
from texture_courier import Texture

from lltexturecache_browser_qt.view.images import placeholder

# how many inspector-sized decodes are kept. a selection walked with the arrow
# keys comes back through the ones just left, and a screenful of them is more
# than anyone walks back through
FULL_CACHE = 12


class FullDecodes:
    """Inspector-sized decodes, and the few most recent of them kept

    Held rather than put in the pixmap cache: these are much larger than a
    cell, and a handful of them would push out the thousands of cells the
    grid is painting from.
    """

    def __init__(self) -> None:
        self._ready: dict[str, tuple[QPixmap, QSize]] = {}
        self._running: set[str] = set()

    def ready(self, uuid: str) -> tuple[QPixmap, QSize] | None:
        return self._ready.get(uuid)

    def wanted(self, texture: Texture) -> bool:
        if not texture.whole() or texture.uuid in self._running:
            return False

        self._running.add(texture.uuid)

        return True

    def landed(self, uuid: str, image: QImage, natural: QSize) -> bool:
        """Take a decode, and say whether it is one the inspector still wants

        Always, as it happens: unlike the preview, the inspector shows a pile
        rather than one texture, and a decode that lands after the selection
        has moved on is still one of the cards on some earlier pile. The bool
        is here so the two stores read the same way at their call sites.
        """

        self._running.discard(uuid)

        # a texture that cannot be decoded caches its placeholder, or every
        # reselect would set the same doomed decode going again
        pixmap = placeholder() if image.isNull() else QPixmap.fromImage(image)

        self._ready[uuid] = (pixmap, natural)

        while len(self._ready) > FULL_CACHE:
            del self._ready[next(iter(self._ready))]

        return True

    def clear(self) -> None:
        self._ready.clear()
        self._running.clear()


class PreviewDecodes:
    """The one texture the preview window is on

    A preview shows one texture at whatever size it was drawn, which is far
    too large to keep several of: the one being looked at is the only one
    worth the room.
    """

    def __init__(self) -> None:
        self._ready: tuple[str, QPixmap, QSize] | None = None
        self._showing: str | None = None
        self._running: set[str] = set()

    def now_showing(self, texture: Texture) -> tuple[QPixmap, QSize] | None:
        """Saying which texture the preview is on is what makes a decode the
        selection has walked past droppable when it lands.
        """

        self._showing = texture.uuid

        if self._ready is not None and self._ready[0] == texture.uuid:
            return self._ready[1], self._ready[2]

        return None

    def wanted(self, texture: Texture) -> bool:
        if not texture.whole() or texture.uuid in self._running:
            return False

        self._running.add(texture.uuid)

        return True

    def landed(self, uuid: str, image: QImage, natural: QSize) -> bool:
        self._running.discard(uuid)

        if uuid != self._showing:
            return False

        # a texture that could not be decoded comes back null, and is held that
        # way so a reselect does not set the same doomed decode going again
        self._ready = (uuid, QPixmap.fromImage(image), natural)

        return True

    def clear(self) -> None:
        self._ready = None
        self._showing = None
        self._running.clear()
