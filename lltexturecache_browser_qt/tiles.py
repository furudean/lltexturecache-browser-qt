import threading
from functools import cache

from PySide6.QtCore import (
    QAbstractItemModel,
    QAbstractListModel,
    QBuffer,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QImageReader,
    QMouseEvent,
    QPainter,
    QPalette,
    QPixmap,
    QPixmapCache,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QListView,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)
from texture_courier import Texture, TextureCacheError
from texture_courier.encode import wrap_jp2

from lltexturecache_browser_qt.checkerboard import checkerboard_generation, over_checkerboard
from lltexturecache_browser_qt.decode import decode_rgba, extra_components
from lltexturecache_browser_qt.formatting import format_time

FULL_SIZE = 800
CELL_PADDING = 14

THUMBNAIL_SIZE = 100
PREVIEW_SIZE = 2048

FULL_PRIORITY = 1
PREVIEW_PRIORITY = 2

# a full decode is a quarter of a megabyte against the 16 KB a cell costs, so
# only the last few textures the selection passed through are worth holding.
# a stack of cards is several of those at once, and they have to outlive each
# other for the stack to stay put
FULL_CACHE = 12

# a decoded cell is 64x64x4 bytes, or 16 KB, so this holds about 64k textures
PIXMAP_CACHE_KB = 1024 * 1024

DECODE_THREADS = 4
DECODES_IN_FLIGHT = DECODE_THREADS * 2

# how far the empty grid's message may run before it wraps, so a window dragged
# wide reads as a line of text in the middle of it rather than as a banner
MESSAGE_WIDTH = 320

# an invalid index is the root of a list model, and it is a plain value type,
# so one shared instance stands in for the default argument
ROOT = QModelIndex()

type Index = QModelIndex | QPersistentModelIndex


def sidebar_key(uuid: str) -> str:
    return f"sidebar:{uuid}"


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


def icon_mode(state: QStyle.StateFlag) -> QIcon.Mode:
    if not (state & QStyle.StateFlag.State_Enabled):
        return QIcon.Mode.Disabled

    return QIcon.Mode.Selected if state & QStyle.StateFlag.State_Selected else QIcon.Mode.Normal


class CellDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Index) -> None:
        cell = QStyleOptionViewItem(option)
        self.initStyleOption(cell, index)

        icon = QIcon(cell.icon)
        cell.icon = QIcon()
        cell.showDecorationSelected = True

        style = cell.widget.style() if cell.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, cell, painter, cell.widget)

        icon.paint(painter, option.rect, Qt.AlignmentFlag.AlignCenter, icon_mode(cell.state))

    def sizeHint(self, option: QStyleOptionViewItem, index: Index) -> QSize:
        return QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE)


class EmptyState(QWidget):
    opened = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._message = QLabel()
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._message.setForegroundRole(QPalette.ColorRole.Text)

        self._open = QPushButton("Open...")
        self._open.clicked.connect(self.opened)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._message, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._open, 0, Qt.AlignmentFlag.AlignHCenter)

    def set_message(self, message: str) -> None:
        self._message.setText(message)

        self._message.setWordWrap(False)

        width = self._message.sizeHint().width()
        wraps = width > MESSAGE_WIDTH

        self._message.setWordWrap(wraps)
        self._message.setFixedWidth(MESSAGE_WIDTH if wraps else width)

        self.adjustSize()


class TextureGrid(QListView):
    opened = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._banding = False

        # a child of the viewport rather than of the view, so it is clipped to
        # the area the textures are drawn in and not to the frame around it
        self._empty = EmptyState(self.viewport())
        self._empty.opened.connect(self.opened)

        self.sync_empty()

    def set_message(self, message: str) -> None:
        self._empty.set_message(message)

        self.centre_empty()

    def is_empty(self) -> bool:
        model = self.model()

        return model is None or model.rowCount() == 0

    def setModel(self, model: QAbstractItemModel | None) -> None:
        old = self.model()

        if old is not None:
            old.modelReset.disconnect(self.sync_empty)
            old.rowsInserted.disconnect(self.sync_empty)
            old.rowsRemoved.disconnect(self.sync_empty)

        super().setModel(model)

        if model is not None:
            model.modelReset.connect(self.sync_empty)
            model.rowsInserted.connect(self.sync_empty)
            model.rowsRemoved.connect(self.sync_empty)

        self.sync_empty()

    def sync_empty(self) -> None:
        # a grid with textures in it says what it holds by showing them, and
        # the panel would only be laid over the top of them
        self._empty.setVisible(self.is_empty())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        self.centre_empty()

    def centre_empty(self) -> None:
        viewport = self.viewport().rect()

        # a viewport too small to hold the panel crops it rather than letting
        # it hang off the edges, so what is left of it stays in the middle
        box = QRect(QPoint(), self._empty.sizeHint().boundedTo(viewport.size()))
        box.moveCenter(viewport.center())

        self._empty.setGeometry(box)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._banding = not self.indexAt(event.position().toPoint()).isValid()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._banding:
            return

        super().mouseMoveEvent(event)


class DecodeSignals(QObject):
    done = Signal(str, QImage, QSize)


class DecodeTask(QRunnable):
    def __init__(
        self,
        texture: Texture,
        reads: threading.Lock,
        signals: DecodeSignals,
        size: int = THUMBNAIL_SIZE,
        *,
        upscale: bool = True,
        board: bool = True,
    ):
        super().__init__()

        self._texture = texture
        self._reads = reads
        self._signals = signals
        self._size = size
        self._upscale = upscale
        self._board = board

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

        return fit_image(image, self._size, upscale=self._upscale, board=self._board), image.size()


class TextureModel(QAbstractListModel):
    full_ready = Signal(str)
    preview_ready = Signal(str)

    def __init__(self, textures: list[Texture], parent: QObject | None = None):
        super().__init__(parent)

        self._textures = textures
        self._rows = {texture.uuid: row for row, texture in enumerate(textures)}
        # the newest request is the one most likely to be on screen, so the
        # queue is drained from the end. a dict is the ordered set python does
        # not have: it keeps insertion order, pops from the end, and still
        # answers "is this queued" in constant time
        self._queue: dict[str, None] = {}
        self._running: set[str] = set()
        self._failed: set[str] = set()
        self._no_sidebar: set[str] = set()
        self._full: dict[str, tuple[QPixmap, QSize]] = {}
        self._full_running: set[str] = set()
        # decodes that set out under the palette before this one, which is to
        # say the ones whose results are already out of date on arrival
        self._stale: set[str] = set()
        self._full_stale: set[str] = set()
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

        # the preview window decodes larger again and keeps its alpha, since it
        # lays the board down behind the image rather than into it
        self._preview_signals = DecodeSignals(self)
        self._preview_signals.done.connect(self.preview_decoded)

    @property
    def reads(self) -> threading.Lock:
        """The turn a texture's bytes have to be read on

        Every texture in a cache reads through one shared BytesIO, so anything
        reading alongside the grid's decodes has to wait for the same lock.
        """

        return self._reads

    def rowCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() else len(self._textures)

    def texture(self, row: int) -> Texture:
        return self._textures[row]

    def row(self, uuid: str) -> int | None:
        return self._rows.get(uuid)

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> QIcon | str | None:
        if not index.isValid():
            return None

        texture = self._textures[index.row()]

        if role == Qt.ItemDataRole.DecorationRole:
            return self.icon(texture)

        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{texture.uuid}\n{format_time(texture.time)}"

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

    def thumbnail(self, texture: Texture) -> QImage:
        try:
            with self._thumbnails:
                thumbnail = texture.thumbnail_png()
        except (TextureCacheError, OSError):
            thumbnail = None

        return thumbnail_image(thumbnail) if thumbnail is not None else QImage()

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

        if decode and uuid not in self._full_running:
            self._full_running.add(uuid)

            # the selection is what the user is looking at, so this goes in
            # ahead of the screenful of cells the grid has already asked for
            task = DecodeTask(texture, self._reads, self._full_signals, FULL_SIZE, upscale=False)

            self._pool.start(task, FULL_PRIORITY)

        return None

    def standing(self, texture: Texture) -> tuple[QPixmap, QSize] | None:
        """The best decode already in hand, and the size it came in at if known

        Nothing is started for it: this is only what a pane or a window can
        put up on the spot while the decode it really wants is out.
        """

        if (ready := self.full(texture, decode=False)) is not None:
            return ready

        # a cell is the grid's own decode, or the thumbnail the cache keeps
        # alongside it, and carries no record of what it was cut down from
        cell = self.cell(texture)

        return (cell, QSize()) if not cell.isNull() else None

    def preview(self, texture: Texture) -> tuple[QPixmap, QSize] | None:
        uuid = texture.uuid

        self._previewing = uuid

        if self._preview is not None and self._preview[0] == uuid:
            return self._preview[1], self._preview[2]

        if uuid not in self._preview_running:
            self._preview_running.add(uuid)

            task = DecodeTask(texture, self._reads, self._preview_signals, PREVIEW_SIZE, upscale=False, board=False)

            self._pool.start(task, PREVIEW_PRIORITY)

        return None

    def restyle(self) -> bool:
        """Let go of everything drawn against a checkerboard that has since moved

        The images themselves are the grid's, and are dropped by whoever calls
        this; what is here is the inspector's copies and the decodes still out.
        Returns whether there was anything to let go of.
        """

        generation = checkerboard_generation()

        if generation == self._generation:
            return False

        self._generation = generation

        # a decode already running was handed the old board, so whatever it
        # comes back with is painted on a background that is no longer there
        self._stale = set(self._running)
        self._full_stale = set(self._full_running)

        self._full.clear()

        return True

    def request(self, texture: Texture) -> None:
        uuid = texture.uuid

        if uuid in self._queue or uuid in self._running or uuid in self._failed:
            return

        self._queue[uuid] = None

        self.pump()

    def pump(self) -> None:
        while self._queue and len(self._running) < DECODES_IN_FLIGHT:
            uuid, _ = self._queue.popitem()

            self._running.add(uuid)

            self._pool.start(DecodeTask(self._textures[self._rows[uuid]], self._reads, self._signals))

    def drain(self, first_row: int, last_row: int) -> None:
        # the list is not just for show, it lets fromkeys size the dict up front
        self._queue = dict.fromkeys([uuid for uuid in self._queue if first_row <= self._rows[uuid] <= last_row])

    @Slot(str, QImage, QSize)
    def decoded(self, uuid: str, image: QImage, _natural: QSize) -> None:
        self._running.discard(uuid)

        self.pump()

        row = self._rows.get(uuid)

        if row is None:
            return

        if uuid in self._stale:
            # nothing is kept from a decode that came back on the old board.
            # the repaint below asks for the texture again, and the second time
            # around it is decoded against the board the system is now on
            self._stale.discard(uuid)
        elif image.isNull():
            # nothing goes in the pixmap cache, so without this the repaint
            # below would ask for the same broken texture forever
            self._failed.add(uuid)
        else:
            QPixmapCache.insert(uuid, QPixmap.fromImage(image))

            # the real texture is in now, so the sidebar is dead weight
            QPixmapCache.remove(sidebar_key(uuid))

        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])

    @Slot(str, QImage, QSize)
    def full_decoded(self, uuid: str, image: QImage, natural: QSize) -> None:
        self._full_running.discard(uuid)

        if uuid in self._full_stale:
            # the same as a cell decoded against the old board, except that
            # nothing repaints the inspector on its own, so the texture is
            # asked for again here rather than waiting to be asked for
            self._full_stale.discard(uuid)

            row = self._rows.get(uuid)

            if row is not None:
                self.full(self._textures[row])

            return

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

        self._queue.clear()
        self._full.clear()

        self._preview = None
        self._previewing = None

        self._pool.clear()
        self._pool.waitForDone()
