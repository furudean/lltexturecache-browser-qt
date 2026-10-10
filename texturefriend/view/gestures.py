from math import exp

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QNativeGestureEvent, QWheelEvent

# a wheel notch is 120 eighths of a degree, and moves a zoom one notch ratio
WHEEL_STEP = 120


def pinch_scale(event: QEvent) -> float | None:
    if not isinstance(event, QNativeGestureEvent) or event.gestureType() != Qt.NativeGestureType.ZoomNativeGesture:
        return None

    # a pinch's changes in scale sum to the log of its total scale
    return exp(event.value())


def wheel_zooms(event: QWheelEvent) -> bool:
    # the command key on mac, and control elsewhere
    return bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)


def wheel_scale(event: QWheelEvent, notch_ratio: float) -> float:
    # a flick carries on scrolling after the fingers lift, which a zoom ignores
    if event.phase() == Qt.ScrollPhase.ScrollMomentum:
        return 1.0

    return float(notch_ratio ** (event.angleDelta().y() / WHEEL_STEP))
