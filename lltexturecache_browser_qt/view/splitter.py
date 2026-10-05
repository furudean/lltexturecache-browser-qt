from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QRegion, QResizeEvent
from PySide6.QtWidgets import QSplitter, QSplitterHandle, QWidget

HAIRLINE_WIDTH = 1

# how far past the hairline a press still grabs it. the trailing pane gets
# more of the reach because it starts with an empty margin, and the leading
# one keeps its scroll bar right up against the line
GRAB_LEADING = 2
GRAB_TRAILING = 6


class HairlineHandle(QSplitterHandle):
    def __init__(self, orientation: Qt.Orientation, parent: QSplitter) -> None:
        super().__init__(orientation, parent)

        self.setAttribute(Qt.WidgetAttribute.WA_MouseNoMask)

        if orientation == Qt.Orientation.Horizontal:
            self.setContentsMargins(GRAB_LEADING, 0, GRAB_TRAILING, 0)
        else:
            self.setContentsMargins(0, GRAB_LEADING, 0, GRAB_TRAILING)

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.setMask(QRegion(self.contentsRect()))

        QWidget.resizeEvent(self, event)


class HairlineSplitter(QSplitter):
    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None) -> None:
        super().__init__(orientation, parent)

        self.setHandleWidth(HAIRLINE_WIDTH)

    def createHandle(self) -> QSplitterHandle:
        return HairlineHandle(self.orientation(), self)

    def restoreState(self, state: QByteArray | bytes | bytearray | memoryview) -> bool:
        restored = super().restoreState(state)

        # a stored state carries a handle width of its own
        self.setHandleWidth(HAIRLINE_WIDTH)

        return restored
