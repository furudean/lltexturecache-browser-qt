import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
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

from lltexturecache_browser_qt.widgets import bold, dim, linked

LICENCES_PATH = Path(__file__).parent / "assets" / "licences"
INDEX_PATH = LICENCES_PATH / "index.json"

DIALOG_MARGIN = 16
COLUMN_SPACING = 16

HEADING_SPACING = 2
BLOCK_SPACING = 12

LIST_WIDTH = 200
DIALOG_SIZE = (760, 480)


@dataclass(frozen=True)
class Component:
    name: str
    licence: str
    homepage: str
    file: str

    def text(self) -> str:
        return (LICENCES_PATH / self.file).read_text()


@cache
def components() -> list[Component]:
    if not INDEX_PATH.exists():
        return []

    return [Component(**entry) for entry in json.loads(INDEX_PATH.read_text())]


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

        for component in components():
            QListWidgetItem(component.name, self._list)

        self._list.currentRowChanged.connect(self.show_component)

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

        if components():
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

    def show_component(self, row: int) -> None:
        if row < 0:
            return

        component = components()[row]

        self._name.setText(component.name)
        self._licence.setText(component.licence)
        self._link.setText(f'<a href="{component.homepage}">{component.homepage}</a>')

        self._text.setPlainText(component.text())

        self._text.moveCursor(self._text.textCursor().MoveOperation.Start)
