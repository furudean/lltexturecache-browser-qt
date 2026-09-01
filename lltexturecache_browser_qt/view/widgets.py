from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QMouseEvent, QPalette
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget


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


def linked(label: QLabel) -> QLabel:
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextBrowserInteraction | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
    )

    return label


def copyable(label: QLabel) -> QLabel:
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    return label


class ClickTracker:
    """Whether a press and release together make a click

    A widget that can also be dragged out of cannot act on the press: the
    press is where a drag starts too, and only the release says which of the
    two happened. A click is a press this widget took, followed by a release
    of the same button still inside it.
    """

    def __init__(self) -> None:
        self._pressed = False
        self._origin = QPoint()

    @property
    def origin(self) -> QPoint:
        return self._origin

    @property
    def pressed(self) -> bool:
        return self._pressed

    def press(self, event: QMouseEvent, *, taking: bool = True) -> bool:
        self._pressed = taking and event.button() == Qt.MouseButton.LeftButton
        self._origin = event.position().toPoint()

        return self._pressed

    def dragged_past(self, event: QMouseEvent, reach: int) -> bool:
        """Whether the pointer has moved far enough to mean a drag rather than a twitch

        The press is spent either way: what follows is a drag, and the release
        that ends it is not a click.
        """

        if not self._pressed or not (event.buttons() & Qt.MouseButton.LeftButton):
            return False

        if (event.position().toPoint() - self._origin).manhattanLength() < reach:
            return False

        self._pressed = False

        return True

    def cancel(self) -> None:
        """Give up on the press without it counting as a click

        A context menu comes up over the press, and whatever the user does
        next is about the menu rather than about the widget under it.
        """

        self._pressed = False

    def release(self, event: QMouseEvent, within: QRect) -> bool:
        pressed, self._pressed = self._pressed, False

        return pressed and event.button() == Qt.MouseButton.LeftButton and within.contains(event.position().toPoint())
