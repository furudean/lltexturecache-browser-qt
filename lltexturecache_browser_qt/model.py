import threading
from collections.abc import Iterable

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap, QPixmapCache
from texture_courier import Texture, TextureCacheError

from lltexturecache_browser_qt.checkerboard import checkerboard_generation
from lltexturecache_browser_qt.color import MATCH_FLOOR, ColorIndex, ColorScan, ScanSignals
from lltexturecache_browser_qt.formatting import format_size, format_time
from lltexturecache_browser_qt.images import (
    THUMBNAIL_SIZE,
    decode_image,
    fit_image,
    placeholder,
    thumbnail_image,
)

FULL_SIZE = 800

FULL_PRIORITY = 1
PREVIEW_PRIORITY = 2

FULL_CACHE = 12

# a decoded cell is 100x100 at 32 bits, or 39 KB, so this holds about 27k textures
PIXMAP_CACHE_KB = 1024 * 1024

DECODE_THREADS = 4
DECODES_IN_FLIGHT = DECODE_THREADS * 2

# an invalid index is the root of a list model, and it is a plain value type,
# so one shared instance stands in for the default argument
ROOT = QModelIndex()

type Index = QModelIndex | QPersistentModelIndex

# whether the row's entry is one the cache never finished downloading, which the
# grid marks and nothing else has a way of asking about
INCOMPLETE_ROLE = Qt.ItemDataRole.UserRole


def sidebar_key(uuid: str) -> str:
    return f"sidebar:{uuid}"


def alpha_key(uuid: str) -> str:
    return f"alpha:{uuid}"


def full_size(natural: QSize) -> QSize:
    return natural.scaled(QSize(FULL_SIZE, FULL_SIZE).boundedTo(natural), Qt.AspectRatioMode.KeepAspectRatio)


class DecodeSignals(QObject):
    done = Signal(str, QImage, QSize)


class DecodeTask(QRunnable):
    def __init__(
        self,
        texture: Texture,
        reads: threading.Lock,
        signals: DecodeSignals,
        size: int | None = THUMBNAIL_SIZE,
        *,
        upscale: bool = True,
        checkerboard: bool = True,
    ):
        super().__init__()

        self._texture = texture
        self._reads = reads
        self._signals = signals
        self._size = size
        self._upscale = upscale
        self._board = checkerboard

    @Slot()
    def run(self) -> None:
        image, natural = self.decode()

        self._signals.done.emit(self._texture.uuid, image, natural)

    def decode(self) -> tuple[QImage, QSize]:
        try:
            # buffered with lock
            with self._reads:
                codestream = self._texture.codestream()

            image = decode_image(codestream)
        except (TextureCacheError, OSError):
            return QImage(), QSize()

        return fit_image(image, self._size, upscale=self._upscale, checkerboard=self._board), image.size()


class TextureModel(QAbstractListModel):
    full_ready = Signal(str)
    preview_ready = Signal(str)
    ranked = Signal()

    def __init__(self, textures: list[Texture], parent: QObject | None = None):
        super().__init__(parent)

        self._textures = list(textures)
        self._lookup = {texture.uuid: texture for texture in self._textures}
        self._filtered_textures = self._textures
        self._filtered_rows = {texture.uuid: row for row, texture in enumerate(self._filtered_textures)}
        self._colors: list[QColor] = []
        self._index: ColorIndex | None = None
        # drained from the end, so whatever fills it puts the rows wanted
        # soonest last
        self._queue: dict[str, None] = {}
        self._running: set[str] = set()
        self._failed: set[str] = set()
        self._no_sidebar: set[str] = set()
        self._natural: dict[str, QSize] = {}
        self._full: dict[str, tuple[QPixmap, QSize]] = {}
        self._full_running: set[str] = set()
        # cell decodes that set out under the palette before this one, which is
        # to say the ones whose results are already out of date on arrival. a
        # decode that keeps its opacity is not among them: it is painted over
        # whatever checkerboard is down when it is drawn
        self._stale: set[str] = set()
        # a preview window shows the one texture it is on, so the last one
        # asked for is the only one worth the room a full sized decode takes
        self._preview: tuple[str, QPixmap, QSize] | None = None
        self._previewing: str | None = None
        self._preview_running: set[str] = set()
        self._generation = checkerboard_generation()
        self._reads = threading.Lock()
        self._thumbnails = threading.Lock()

        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(DECODE_THREADS)

        self._signals = DecodeSignals(self)
        self._signals.done.connect(self.decoded)

        # the inspector's decodes report separately, since they come back at
        # their own size and land in their own cache
        self._full_signals = DecodeSignals(self)
        self._full_signals.done.connect(self.full_decoded)

        # the preview window decodes at whatever size the texture is and keeps
        # its alpha, since it lays the checkerboard down behind the image rather than
        # into it
        self._preview_signals = DecodeSignals(self)
        self._preview_signals.done.connect(self.preview_decoded)

        self._scan_signals = ScanSignals(self)
        self._scan_signals.done.connect(self.scanned)

        self._scan = ColorScan(self._textures, self._thumbnails, self._scan_signals)

        QThreadPool.globalInstance().start(self._scan)

    @property
    def reads(self) -> threading.Lock:
        """The turn a texture's bytes have to be read on

        Every texture in a cache reads through one shared BytesIO, so anything
        reading alongside the grid's decodes has to wait for the same lock.
        """

        return self._reads

    def rowCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() else len(self._filtered_textures)

    def total(self) -> int:
        return len(self._textures)

    @property
    def narrowed(self) -> bool:
        return bool(self._colors) and self._index is not None

    @property
    def colors(self) -> list[QColor]:
        return list(self._colors)

    def texture(self, row: int) -> Texture:
        return self._filtered_textures[row]

    def row(self, uuid: str) -> int | None:
        return self._filtered_rows.get(uuid)

    def flags(self, index: Index) -> Qt.ItemFlag:
        flags = super().flags(index)

        if not index.isValid():
            return flags

        return flags | Qt.ItemFlag.ItemIsDragEnabled

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> QIcon | str | bool | None:
        if not index.isValid():
            return None

        texture = self._filtered_textures[index.row()]

        if role == Qt.ItemDataRole.DecorationRole:
            return self.icon(texture)

        if role == INCOMPLETE_ROLE:
            return not texture.whole()

        if role == Qt.ItemDataRole.ToolTipRole:
            lines = [texture.uuid, format_time(texture.time)]

            if not texture.whole():
                lines.append(f"Incomplete — {format_size(texture.cached_size)} of {format_size(texture.image_size)}")

            return "\n".join(lines)

        return None

    def icon(self, texture: Texture) -> QIcon:
        decoded = QPixmap()

        if QPixmapCache.find(texture.uuid, decoded):
            return QIcon(decoded)

        self.request(texture)

        return QIcon(self.sidebar(texture))

    def sidebar(self, texture: Texture) -> QPixmap:
        if texture.uuid in self._no_sidebar:
            return placeholder()

        cached = QPixmap()

        if QPixmapCache.find(sidebar_key(texture.uuid), cached):
            return cached

        image = self.thumbnail(texture)

        if image.isNull():
            self._no_sidebar.add(texture.uuid)

            return placeholder()

        pixmap = QPixmap.fromImage(image)

        QPixmapCache.insert(sidebar_key(texture.uuid), pixmap)

        return pixmap

    def thumbnail(self, texture: Texture, *, checkerboard: bool = True) -> QImage:
        try:
            with self._thumbnails:
                thumbnail = texture.thumbnail_png()
        except (TextureCacheError, OSError):
            thumbnail = None

        return thumbnail_image(thumbnail, checkerboard=checkerboard) if thumbnail is not None else QImage()

    def cell(self, texture: Texture) -> QPixmap:
        """Whatever the grid already holds for a texture, without decoding"""

        pixmap = QPixmap()

        for key in (texture.uuid, sidebar_key(texture.uuid)):
            if QPixmapCache.find(key, pixmap):
                return pixmap

        return QPixmap()

    def full(self, texture: Texture, *, decode: bool = True) -> tuple[QPixmap, QSize] | None:
        """An inspector sized decode and the size it was stored at, once it is in

        Starts one if there is none, unless asked only to look.
        """

        uuid = texture.uuid

        if (ready := self._full.get(uuid)) is not None:
            return ready

        if decode and texture.whole() and uuid not in self._full_running:
            self._full_running.add(uuid)

            # the selection is what the user is looking at, so this goes in
            # ahead of the screenful of cells the grid has already asked for
            task = DecodeTask(texture, self._reads, self._full_signals, FULL_SIZE, upscale=False, checkerboard=False)

            self._pool.start(task, FULL_PRIORITY)

        return None

    def natural(self, texture: Texture) -> QSize:
        return self._natural.get(texture.uuid, QSize())

    def standing(self, texture: Texture) -> tuple[QPixmap, QSize] | None:
        """The best decode already in hand, and the size it came in at if known

        Nothing is started for it: this is only what a pane or a window can
        put up on the spot while the decode it really wants is out. The shape
        is handed over beside it, since a decode at any size knew what it was.

        What comes back keeps its opacity wherever it can, since a stand-in is
        drawn larger than it was kept and a checkerboard painted into it is drawn
        larger with it, at squares several times the size of the ones the
        decode it stands in for is laid over.
        """

        uuid = texture.uuid

        if (ready := self.full(texture, decode=False)) is not None:
            return ready

        kept = QPixmap()

        if QPixmapCache.find(alpha_key(uuid), kept):
            return kept, self.natural(texture)

        # a texture with no thumbnail beside it in the cache falls back to the
        # grid's cell, which has the checkerboard painted into it at the size a cell is
        if uuid in self._no_sidebar:
            return self.cell_standing(texture)

        image = self.thumbnail(texture, checkerboard=False)

        if image.isNull():
            self._no_sidebar.add(uuid)

            return self.cell_standing(texture)

        pixmap = QPixmap.fromImage(image)

        QPixmapCache.insert(alpha_key(uuid), pixmap)

        return pixmap, self.natural(texture)

    def cell_standing(self, texture: Texture) -> tuple[QPixmap, QSize] | None:
        cell = self.cell(texture)

        return (cell, self.natural(texture)) if not cell.isNull() else None

    def preview(self, texture: Texture) -> tuple[QPixmap, QSize] | None:
        uuid = texture.uuid

        self._previewing = uuid

        if self._preview is not None and self._preview[0] == uuid:
            return self._preview[1], self._preview[2]

        if texture.whole() and uuid not in self._preview_running:
            self._preview_running.add(uuid)

            task = DecodeTask(texture, self._reads, self._preview_signals, None, checkerboard=False)

            self._pool.start(task, PREVIEW_PRIORITY)

        return None

    def restyle(self) -> bool:
        """Take note of a checkerboard that has since moved

        The cells are the grid's, and are dropped by whoever calls this; what is
        here is the cell decodes still out, which are the only ones with a checkerboard
        painted into what they bring back. Returns whether the checkerboard has moved.
        """

        generation = checkerboard_generation()

        if generation == self._generation:
            return False

        self._generation = generation

        # a cell decode already running was handed the old checkerboard, so whatever
        # it comes back with is painted on a background that is no longer there
        self._stale = set(self._running)

        return True

    def set_filters(self, colors: list[QColor]) -> bool:
        self._colors = list(colors)

        return self.apply_filters()

    def apply_filters(self) -> bool:
        if not self._colors:
            self.reorder(self._textures)

            return True

        if self._index is None:
            return False

        scores = self._index.scores(self._colors)

        floor = MATCH_FLOOR / len(self._colors)

        kept = [row for row, score in enumerate(scores) if score >= floor]
        kept.sort(key=lambda row: -scores[row])

        self.reorder([self._textures[row] for row in kept])

        return True

    def reorder(self, textures: list[Texture]) -> None:
        if textures == self._filtered_textures:
            return

        self.beginResetModel()

        self._filtered_textures = textures
        self._filtered_rows = {texture.uuid: row for row, texture in enumerate(textures)}

        self._queue.clear()

        self.endResetModel()

    @Slot(object)
    def scanned(self, index: ColorIndex) -> None:
        self._index = index

        if self._colors and self.apply_filters():
            self.ranked.emit()

    def request(self, texture: Texture) -> None:
        if self.enqueue(texture):
            self.pump()

    def enqueue(self, texture: Texture) -> bool:
        uuid = texture.uuid

        if uuid in self._queue or not self.wanted(texture):
            return False

        self._queue[uuid] = None

        return True

    def wanted(self, texture: Texture) -> bool:
        uuid = texture.uuid

        # an entry the cache never finished downloading has no codestream to
        # decode, so the thumbnail beside it in the cache is all there ever is
        if not texture.whole():
            return False

        if uuid in self._running or uuid in self._failed:
            return False

        return not QPixmapCache.find(uuid, QPixmap())

    def prefetch(self, rows: Iterable[int]) -> None:
        self._queue = dict.fromkeys([texture.uuid for texture in map(self.texture, rows) if self.wanted(texture)])

        self.pump()

    def pump(self) -> None:
        while self._queue and len(self._running) < DECODES_IN_FLIGHT:
            uuid, _ = self._queue.popitem()

            row = self._filtered_rows.get(uuid)

            if row is None:
                continue

            self._running.add(uuid)

            self._pool.start(DecodeTask(self._filtered_textures[row], self._reads, self._signals))

    def learn(self, uuid: str, natural: QSize) -> None:
        if not natural.isEmpty():
            self._natural[uuid] = natural

    @Slot(str, QImage, QSize)
    def decoded(self, uuid: str, image: QImage, natural: QSize) -> None:
        self._running.discard(uuid)

        # a cell is cut down to the size of a cell, but the decode behind it saw
        # the texture whole, and that is worth keeping for the panes that ask
        self.learn(uuid, natural)

        self.pump()

        if uuid in self._stale:
            # nothing is kept from a decode that came back on the old checkerboard.
            # the repaint below asks for the texture again, and the second time
            # around it is decoded against the checkerboard the system is now on
            self._stale.discard(uuid)
        elif image.isNull():
            # nothing goes in the pixmap cache, so without this the repaint
            # below would ask for the same broken texture forever
            self._failed.add(uuid)
        else:
            QPixmapCache.insert(uuid, QPixmap.fromImage(image))

            # the real texture is in now, so the sidebar is dead weight
            QPixmapCache.remove(sidebar_key(uuid))

        row = self._filtered_rows.get(uuid)

        if row is None:
            return

        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])

    @Slot(str, QImage, QSize)
    def full_decoded(self, uuid: str, image: QImage, natural: QSize) -> None:
        self._full_running.discard(uuid)

        self.learn(uuid, natural)

        # a texture that cannot be decoded caches its placeholder, or every
        # reselect would set the same doomed decode going again
        pixmap = placeholder() if image.isNull() else QPixmap.fromImage(image)

        self._full[uuid] = (pixmap, natural)

        while len(self._full) > FULL_CACHE:
            del self._full[next(iter(self._full))]

        self.full_ready.emit(uuid)

    @Slot(str, QImage, QSize)
    def preview_decoded(self, uuid: str, image: QImage, natural: QSize) -> None:
        self._preview_running.discard(uuid)

        # the shape stands even if the selection has moved on from the image
        self.learn(uuid, natural)

        if uuid != self._previewing:
            return

        # a texture that could not be decoded comes back null, and is held that
        # way so a reselect does not set the same doomed decode going again
        self._preview = (uuid, QPixmap.fromImage(image), natural)

        self.preview_ready.emit(uuid)

    def shutdown(self) -> None:
        # a decode the pool already started still reports back, and this model
        # is on its way out, so a stale image could land on top of a fresher
        # one under the same key. dropping the connection drops those reports
        self._signals.done.disconnect(self.decoded)
        self._full_signals.done.disconnect(self.full_decoded)
        self._preview_signals.done.disconnect(self.preview_decoded)

        self._scan.cancel()
        self._scan_signals.done.disconnect(self.scanned)

        self._queue.clear()
        self._full.clear()

        self._preview = None
        self._previewing = None

        self._pool.clear()
        self._pool.waitForDone()
