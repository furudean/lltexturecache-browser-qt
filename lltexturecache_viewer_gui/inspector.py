from math import sqrt
from random import Random

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPalette,
    QPixmap,
    QResizeEvent,
    QTransform,
)
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from texture_courier import Texture

from lltexturecache_viewer_gui.formatting import format_count, format_size, format_time

INSPECTOR_WIDTH = 260
INSPECTOR_MIN_WIDTH = 200

PREVIEW_MIN_HEIGHT = 140

PANE_MARGIN = 16
PANE_SPACING = 6
HEADING_SPACING = 10

LABEL_SPACING = 12
ROW_SPACING = 4

STACK_CARDS = 4
STACK_TILT = 12
STACK_SHIFT = 0.05
STACK_SPAN_RATIO = 1.25
STACK_FRAME = 0.012

FRAME_FILL = QColor(0xFF, 0xFF, 0xFF)
FRAME_EDGE = QColor(0x00, 0x00, 0x00, 0x28)


def dim(label: QLabel) -> QLabel:
    label.setForegroundRole(QPalette.ColorRole.PlaceholderText)

    return label


def bold(label: QLabel) -> QLabel:
    font = label.font()
    font.setBold(True)

    label.setFont(font)

    return label


def wrapped(label: QLabel) -> QLabel:
    label.setWordWrap(True)

    # a form only widens the fields that ask to be widened, and a label left at
    # its own idea of a width gets laid out for the room it wanted and painted
    # in the room it got
    policy = label.sizePolicy()
    policy.setHorizontalPolicy(QSizePolicy.Policy.Expanding)

    label.setSizePolicy(policy)

    return height_for_width(label)


def height_for_width[W: QWidget](widget: W) -> W:
    policy = widget.sizePolicy()
    policy.setHeightForWidth(True)

    widget.setSizePolicy(policy)

    return widget


def copyable(label: QLabel) -> QLabel:
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    return label


def card_transform(uuid: str, side: float) -> QTransform:
    angles = Random(uuid)

    return (
        QTransform()
        .translate(angles.uniform(-STACK_SHIFT, STACK_SHIFT) * side, angles.uniform(-STACK_SHIFT, STACK_SHIFT) * side)
        .rotate(angles.uniform(-STACK_TILT, STACK_TILT))
    )


def dealt_card(card: QPixmap, box: QSize, span: int) -> QPixmap:
    width, height = card.width(), card.height()

    covers = sqrt((box.width() * box.height()) / (width * height))
    fits = min(box.width() / width, box.height() / height)

    scale = min(sqrt(covers * fits), span / max(width, height))

    return card.scaled(
        QSize(max(1, round(width * scale)), max(1, round(height * scale))),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def stack_pixmap(cards: list[tuple[str, QPixmap]]) -> QPixmap:
    """Lay pixmaps out as a tilted stack, the last of them face up on top"""

    if not cards:
        return QPixmap()

    top = cards[-1][1]

    # every card is sized against the one on top but keeps the shape it was
    # stored at, since a selection is rarely all the one shape and a card cut to
    # someone else's is no longer the texture it was meant to be standing in for
    box = top.size()
    side = max(box.width(), box.height())
    span = round(side * STACK_SPAN_RATIO)
    frame = max(2, round(side * STACK_FRAME)) if len(cards) > 1 else 0

    def framed(pixmap: QPixmap) -> QRectF:
        return QRectF(
            -pixmap.width() / 2 - frame,
            -pixmap.height() / 2 - frame,
            pixmap.width() + 2 * frame,
            pixmap.height() + 2 * frame,
        )

    dealt = [(dealt_card(card, box, span), card_transform(uuid, side)) for uuid, card in cards[:-1]]
    dealt.append((top, QTransform()))

    bounds = QRectF()

    for pixmap, transform in dealt:
        bounds = bounds.united(transform.mapRect(framed(pixmap)))

    laid = bounds.adjusted(-1, -1, 1, 1).toAlignedRect()

    canvas = QPixmap(laid.size())
    canvas.fill(Qt.GlobalColor.transparent)

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setPen(FRAME_EDGE)
    painter.translate(-laid.topLeft())

    for pixmap, transform in dealt:
        painter.save()
        painter.setWorldTransform(transform, True)

        rect = framed(pixmap)

        if frame:
            # a white border, so one texture against another still reads as two
            # cards rather than as one busy image
            painter.fillRect(rect, FRAME_FILL)
            painter.drawRect(rect)

        painter.drawPixmap(QPointF(-pixmap.width() / 2, -pixmap.height() / 2), pixmap)
        painter.restore()

    painter.end()

    return canvas


class PreviewLabel(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._source = QPixmap()

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # a label sizes itself to its pixmap by default, which would let a wide
        # texture pin the whole pane open at the width of the image. the height
        # comes from the image instead, so the name below sits the same distance
        # under a tall texture as it does under a wide one
        policy = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        policy.setHeightForWidth(True)

        self.setSizePolicy(policy)

    def set_source(self, pixmap: QPixmap) -> None:
        self._source = pixmap

        self.updateGeometry()
        self.refit()

    def heightForWidth(self, width: int) -> int:
        if self._source.isNull():
            return PREVIEW_MIN_HEIGHT

        fitted = self._source.size().scaled(self.box(width), Qt.AspectRatioMode.KeepAspectRatio)

        return max(fitted.height(), PREVIEW_MIN_HEIGHT)

    def box(self, width: int) -> QSize:
        return QSize(width, self.maximumHeight()).boundedTo(self._source.size())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        self.refit()

    def refit(self) -> None:
        if self._source.isNull():
            self.clear()
            return

        ratio = self.devicePixelRatioF()

        # the pixmap is scaled in device pixels and then told what it was scaled
        # for, so the image is drawn at the density of the screen rather than at
        # the coarser one qt lays widgets out in. the box is the one the height
        # was asked for with, so the image lands at the size it was measured at
        fitted = self._source.scaled(
            self.box(self.width()) * ratio,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        fitted.setDevicePixelRatio(ratio)

        self.setPixmap(fitted)


class InspectorPane(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._texture: Texture | None = None

        self.setMinimumWidth(INSPECTOR_MIN_WIDTH)

        self._empty = dim(QLabel("No selection"))
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._sidebar = PreviewLabel()

        self._name = wrapped(copyable(bold(QLabel())))

        self._kind = wrapped(dim(QLabel()))

        self._info = QFormLayout()
        self._info.setContentsMargins(0, 0, 0, 0)
        self._info.setHorizontalSpacing(LABEL_SPACING)
        self._info.setVerticalSpacing(ROW_SPACING)
        self._info.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self._info.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._info.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._info.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self._dimensions = self.row("Dimensions")
        self._size = self.row("Size")
        self._date = self.row("Date")
        self._entry = self.row("Entry")

        information = QVBoxLayout()
        information.setContentsMargins(0, HEADING_SPACING, 0, 0)
        information.setSpacing(PANE_SPACING)
        information.addWidget(bold(QLabel("Information")))
        information.addLayout(self._info)

        self._information = height_for_width(QWidget())
        self._information.setLayout(information)

        details = QVBoxLayout()
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(PANE_SPACING)
        details.addWidget(self._name)
        details.addWidget(self._kind)
        details.addWidget(self._information)
        # the slack in the pane collects here, under the rows, rather than
        # between the sidebar and the name
        details.addStretch(1)

        self._details = height_for_width(QWidget())
        self._details.setLayout(details)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(PANE_MARGIN, PANE_MARGIN, PANE_MARGIN, PANE_MARGIN)
        layout.setSpacing(PANE_SPACING)
        # a hidden widget is skipped by the layout, stretch and all, so the two
        # states can share one column without stepping on each other
        layout.addWidget(self._empty, 1)
        layout.addWidget(self._sidebar)
        layout.addWidget(self._details, 1)

        self.clear()

    def row(self, name: str) -> QLabel:
        value = wrapped(copyable(QLabel()))

        self._info.addRow(dim(QLabel(name)), value)

        return value

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        self.share_height()

    def share_height(self) -> None:
        width = self.width() - 2 * PANE_MARGIN
        text = self._details.heightForWidth(width) if width > 0 else self._details.sizeHint().height()
        room = max(self.height() - 2 * PANE_MARGIN - PANE_SPACING - text, PREVIEW_MIN_HEIGHT)

        if room != self._sidebar.maximumHeight():
            self._sidebar.setMaximumHeight(room)

    @property
    def texture(self) -> Texture | None:
        return self._texture

    def clear(self) -> None:
        self._texture = None

        self._sidebar.set_source(QPixmap())

        self._empty.setVisible(True)
        self._sidebar.setVisible(False)
        self._details.setVisible(False)

    def show_texture(self, texture: Texture, count: int, total: int) -> None:
        self._texture = texture

        self._empty.setVisible(False)
        self._sidebar.setVisible(True)
        self._details.setVisible(True)

        # finder titles a multiple selection by how much is in it rather than
        # by any one of the items, and a uuid up here would only name the one
        # texture the sidebar happened to land on
        self._name.setText(f"{format_count(count)} items" if count > 1 else texture.uuid)
        self._kind.setText(
            f"{format_count(count)} textures — {format_size(total)}"
            if count > 1
            else f"JPEG 2000 image — {format_size(texture.image_size)}"
        )

        # the rows below are about the one texture, and a selection is titled
        # by its count above rather than described item by item
        self._information.setVisible(count == 1)

        self._size.setText(format_size(texture.image_size))
        self._date.setText(format_time(texture.time))
        self._entry.setText(format_count(texture.index))

        # the rows just changed height, and the sidebar is owed what is left
        self.share_height()

        # the caller follows with the image it has, which is not this one
        self.set_sidebar(QPixmap(), None)

    def set_sidebar(self, pixmap: QPixmap, natural: QSize | None) -> None:
        self._sidebar.set_source(pixmap)

        self.share_height()

        if natural is None:
            self._dimensions.setText("Decoding...")
        elif natural.isEmpty():
            self._dimensions.setText("Could not decode")
        else:
            self._dimensions.setText(f"{format_count(natural.width())} × {format_count(natural.height())}")
