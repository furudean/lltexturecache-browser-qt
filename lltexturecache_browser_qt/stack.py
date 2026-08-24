from math import sqrt
from random import Random

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap, QTransform

# how many of a selection are dealt out behind the one on top
STACK_CARDS = 4

STACK_TILT = 12
STACK_SHIFT = 0.05
STACK_SPAN_RATIO = 1.25
STACK_FRAME = 0.012

FRAME_FILL = QColor(0xFF, 0xFF, 0xFF)
FRAME_EDGE = QColor(0x00, 0x00, 0x00, 0x28)


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

    dealt = QSize(max(1, round(width * scale)), max(1, round(height * scale)))

    # the card that set the box is already the size it is being asked for
    if dealt == card.size():
        return card

    return card.scaled(
        dealt,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def biggest_card(cards: list[tuple[str, QPixmap]]) -> QSize:
    """The card the rest of a stack is sized against

    A pile is of one photograph size rather than of whatever each texture
    happens to be, so the biggest card keeps its size and everything else is
    dealt to sit with it. By area, since that is the room a card takes up on
    the pile rather than how far it reaches in one direction.
    """

    return max((card.size() for _, card in cards), key=lambda size: size.width() * size.height())


def stack_pixmap(cards: list[tuple[str, QPixmap]]) -> QPixmap:
    """Lay pixmaps out as a tilted stack, the last of them face up on top"""

    if not cards:
        return QPixmap()

    # every card is sized against the biggest of them but keeps the shape it was
    # stored at, since a selection is rarely all the one shape and a card cut to
    # someone else's is no longer the texture it was meant to be standing in for.
    # a small texture on top of larger ones is blown up to sit with them rather
    # than shrinking the whole pile down to its own size
    box = biggest_card(cards)
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
    # the card on top is dealt like the rest, and lands where it was stored
    # whenever it is the one that set the size
    dealt.append((dealt_card(cards[-1][1], box, span), QTransform()))

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
