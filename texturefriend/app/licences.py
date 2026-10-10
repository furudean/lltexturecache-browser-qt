import tomllib
from dataclasses import dataclass
from functools import cache
from typing import ClassVar

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from texturefriend.assets import LICENCES
from texturefriend.view.widgets import bold, dim, linked

LICENCES_PATH = LICENCES
INDEX_PATH = LICENCES_PATH / "index.toml"

DIALOG_MARGIN = 16
COLUMN_SPACING = 16

HEADING_SPACING = 2
BLOCK_SPACING = 12

LIST_WIDTH = 200
DIALOG_SIZE = (760, 480)


@dataclass(frozen=True)
class License:
    name: str
    licence: str
    homepage: str
    file: str

    def text(self) -> str:
        return (LICENCES_PATH / self.file).read_text(encoding="utf-8")


@cache
def licenses() -> list[License]:
    if not INDEX_PATH.exists():
        return []

    return [License(**entry) for entry in tomllib.loads(INDEX_PATH.read_text(encoding="utf-8"))["license"]]


def text_view(parent: QWidget) -> QPlainTextEdit:
    view = QPlainTextEdit(parent)
    view.setReadOnly(True)

    # licence text is written to be read at a fixed width, so it is shown in the
    # font it was laid out for rather than reflowed
    view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
    view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    return view


class LicencesDialog(QDialog):
    _shared: ClassVar["LicencesDialog | None"] = None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Open Source Licences")

        self._name = bold(QLabel(self))
        self._licence = dim(QLabel(self))
        self._link = linked(QLabel(self))
        self._text = text_view(self)

        self._list = QListWidget(self)
        self._list.setFixedWidth(LIST_WIDTH)

        for component in licenses():
            QListWidgetItem(component.name, self._list)

        self._list.currentRowChanged.connect(self.show_license)

        heading = QVBoxLayout()
        heading.setSpacing(HEADING_SPACING)
        heading.addWidget(self._name)
        heading.addWidget(self._licence)
        heading.addWidget(self._link)

        column = QVBoxLayout()
        column.setSpacing(BLOCK_SPACING)
        column.addLayout(heading)
        column.addWidget(self._text)

        body = QHBoxLayout(self)
        body.setContentsMargins(DIALOG_MARGIN, DIALOG_MARGIN, DIALOG_MARGIN, DIALOG_MARGIN)
        body.setSpacing(COLUMN_SPACING)
        body.addWidget(self._list)
        body.addLayout(column)

        self.resize(*DIALOG_SIZE)

        if licenses():
            self._list.setCurrentRow(0)
        else:
            self._text.setPlainText("The app was built without licencing information.")

    @classmethod
    def show_shared(cls) -> None:
        if cls._shared is None:
            cls._shared = LicencesDialog()

        window = cls._shared

        window.show()
        window.raise_()
        window.activateWindow()

    def show_license(self, row: int) -> None:
        if row < 0:
            return

        license = licenses()[row]

        self._name.setText(license.name)
        self._licence.setText(license.licence)
        self._link.setText(f'<a href="{license.homepage}">{license.homepage}</a>')

        self._text.setPlainText(license.text())

        self._text.moveCursor(self._text.textCursor().MoveOperation.Start)
