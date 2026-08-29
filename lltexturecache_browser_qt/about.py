from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from lltexturecache_browser_qt import APP_DISPLAY_NAME, __version__
from lltexturecache_browser_qt.licences import LicencesDialog
from lltexturecache_browser_qt.widgets import bold, copyable, linked, wrapped

ICON_PATH = Path(__file__).parent / "assets" / "slcachegirl.png"

SUMMARY = "A cross-platform tool to browse and export textures from the Second Life texture cache."
HOMEPAGE = "https://github.com/furudean/lltexturecache-browser-qt"

ICON_SIZE = 160
TITLE_SCALE = 1.5

DIALOG_MARGIN = 36
COLUMN_SPACING = 32

TITLE_SPACING = 4
LINK_SPACING = 12
BLOCK_SPACING = 20

TEXT_WIDTH = 340


def app_icon() -> QIcon:
    packaged = QGuiApplication.windowIcon()

    return packaged if not packaged.isNull() else QIcon(str(ICON_PATH))


def icon_label(parent: QWidget) -> QLabel:
    label = QLabel(parent)

    label.setPixmap(app_icon().pixmap(QSize(ICON_SIZE, ICON_SIZE), parent.devicePixelRatioF()))

    return label


def title_label(parent: QWidget) -> QLabel:
    label = bold(QLabel(APP_DISPLAY_NAME, parent))

    font = label.font()
    font.setPointSizeF(font.pointSizeF() * TITLE_SCALE)

    label.setFont(font)

    return wrapped(label)


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowTitle(f"About {APP_DISPLAY_NAME}")
        self.setSizeGripEnabled(False)

        link = wrapped(linked(QLabel(f'<a href="{HOMEPAGE}">{HOMEPAGE}</a>', self)))

        licences = QPushButton("Open Source Licenses...", self)
        licences.setAutoDefault(False)
        licences.clicked.connect(self.show_licences)

        column = QVBoxLayout()
        column.setSpacing(TITLE_SPACING)
        column.addWidget(title_label(self))
        column.addWidget(bold(QLabel(__version__, self)))
        column.addSpacing(BLOCK_SPACING)
        column.addWidget(copyable(wrapped(QLabel(SUMMARY, self))))
        column.addSpacing(LINK_SPACING)
        column.addWidget(link)
        column.addSpacing(LINK_SPACING)
        column.addWidget(licences, 0, Qt.AlignmentFlag.AlignLeft)
        column.addStretch()

        body = QHBoxLayout(self)
        body.setContentsMargins(DIALOG_MARGIN, DIALOG_MARGIN, DIALOG_MARGIN, DIALOG_MARGIN)
        body.setSpacing(COLUMN_SPACING)
        body.addWidget(icon_label(self), 0, Qt.AlignmentFlag.AlignTop)
        body.addLayout(column)

        # the text column decides how wide the window is, rather than a long
        # paragraph stretching it across the screen
        width = max(TEXT_WIDTH, licences.sizeHint().width())

        self.setFixedWidth(DIALOG_MARGIN * 2 + COLUMN_SPACING + ICON_SIZE + width)

        self.setFixedHeight(max(self.minimumSizeHint().height(), body.heightForWidth(self.width())))

    def show_licences(self) -> None:
        LicencesDialog.show_shared()
