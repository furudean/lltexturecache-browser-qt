from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
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
