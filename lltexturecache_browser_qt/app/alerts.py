from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QMessageBox, QStyle, QWidget

from lltexturecache_browser_qt.app.about import app_icon

ICON_SIZE = 64
BADGE_SCALE = 0.5


def alert_icon(widget: QWidget, badge: QStyle.StandardPixmap) -> QPixmap:
    ratio = widget.devicePixelRatioF()
    badge_size = round(ICON_SIZE * BADGE_SCALE)

    icon = app_icon().pixmap(QSize(ICON_SIZE, ICON_SIZE), ratio)
    sign = widget.style().standardIcon(badge).pixmap(QSize(badge_size, badge_size), ratio)

    painter = QPainter(icon)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawPixmap(
        QRectF(ICON_SIZE - badge_size, ICON_SIZE - badge_size, badge_size, badge_size),
        sign,
        QRectF(sign.rect()),
    )
    painter.end()

    return icon


def warn(parent: QWidget, message: str, detail: str = "") -> None:
    box = QMessageBox(parent)

    box.setIconPixmap(alert_icon(box, QStyle.StandardPixmap.SP_MessageBoxWarning))
    box.setText(message)

    if detail:
        box.setInformativeText(detail)

    box.exec()


def fail(parent: QWidget | None, message: str, detail: str = "", trace: str = "") -> None:
    box = QMessageBox(parent)

    box.setIconPixmap(alert_icon(box, QStyle.StandardPixmap.SP_MessageBoxCritical))
    box.setText(message)

    if detail:
        box.setInformativeText(detail)

    if trace:
        # the traceback stays folded away behind the details button: it is for
        # the report the user files, not for the sentence they read here
        box.setDetailedText(trace)

    box.exec()
