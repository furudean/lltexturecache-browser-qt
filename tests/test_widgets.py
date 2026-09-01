"""The small adjustments labels are put through before they go in a form"""

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent, QPalette
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from lltexturecache_browser_qt.view.widgets import (
    ClickTracker,
    bold,
    copyable,
    dim,
    height_for_width,
    linked,
    wrapped,
)


class TestAdjustments:
    def test_every_adjustment_hands_the_label_back(self, app: object) -> None:
        label = QLabel("text")

        assert dim(label) is label
        assert bold(label) is label
        assert wrapped(label) is label
        assert linked(label) is label
        assert copyable(label) is label

    def test_a_dimmed_label_is_painted_as_a_placeholder(self, app: object) -> None:
        assert dim(QLabel()).foregroundRole() == QPalette.ColorRole.PlaceholderText

    def test_a_bold_label_is_bold(self, app: object) -> None:
        assert bold(QLabel()).font().bold() is True

    def test_bolding_leaves_the_rest_of_the_font_alone(self, app: object) -> None:
        label = QLabel()
        before = label.font().pointSizeF()

        assert bold(label).font().pointSizeF() == before

    def test_a_wrapped_label_wraps_and_asks_for_the_room(self, app: object) -> None:
        label = wrapped(QLabel("a good deal of text"))

        assert label.wordWrap() is True
        assert label.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
        assert label.sizePolicy().hasHeightForWidth() is True

    def test_height_for_width_works_on_any_widget(self, app: object) -> None:
        widget = height_for_width(QWidget())

        assert widget.sizePolicy().hasHeightForWidth() is True

    def test_a_linked_label_opens_its_links_outside_the_app(self, app: object) -> None:
        assert linked(QLabel('<a href="https://example.invalid">link</a>')).openExternalLinks() is True

    def test_a_copyable_label_can_be_selected_but_not_edited(self, app: object) -> None:
        from PySide6.QtCore import Qt

        flags = copyable(QLabel("text")).textInteractionFlags()

        assert flags & Qt.TextInteractionFlag.TextSelectableByMouse
        assert not flags & Qt.TextInteractionFlag.TextEditable


class TestClickTracker:
    """Whether a press and a release together make a click"""

    @staticmethod
    def press(at: QPoint = QPoint(5, 5), button: Qt.MouseButton = Qt.MouseButton.LeftButton) -> QMouseEvent:
        return QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(at),
            QPointF(at),
            button,
            button,
            Qt.KeyboardModifier.NoModifier,
        )

    @staticmethod
    def move(at: QPoint) -> QMouseEvent:
        return QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(at),
            QPointF(at),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

    @staticmethod
    def release(at: QPoint = QPoint(5, 5)) -> QMouseEvent:
        return QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(at),
            QPointF(at),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )

    def test_nothing_is_pressed_to_begin_with(self, app: object) -> None:
        assert ClickTracker().pressed is False

    def test_a_left_press_is_taken(self, app: object) -> None:
        assert ClickTracker().press(self.press()) is True

    def test_a_right_press_is_not(self, app: object) -> None:
        assert ClickTracker().press(self.press(button=Qt.MouseButton.RightButton)) is False

    def test_a_widget_with_nothing_in_it_takes_no_press(self, app: object) -> None:
        assert ClickTracker().press(self.press(), taking=False) is False

    def test_the_press_is_remembered_as_the_origin(self, app: object) -> None:
        tracker = ClickTracker()
        tracker.press(self.press(QPoint(9, 4)))

        assert tracker.origin == QPoint(9, 4)

    def test_a_press_and_a_release_inside_make_a_click(self, app: object) -> None:
        tracker = ClickTracker()
        tracker.press(self.press())

        assert tracker.release(self.release(), QRect(0, 0, 20, 20)) is True

    def test_a_release_outside_is_not_a_click(self, app: object) -> None:
        tracker = ClickTracker()
        tracker.press(self.press())

        assert tracker.release(self.release(QPoint(90, 90)), QRect(0, 0, 20, 20)) is False

    def test_a_release_with_no_press_behind_it_is_not_a_click(self, app: object) -> None:
        assert ClickTracker().release(self.release(), QRect(0, 0, 20, 20)) is False

    def test_a_press_is_spent_by_its_release(self, app: object) -> None:
        tracker = ClickTracker()
        tracker.press(self.press())
        tracker.release(self.release(), QRect(0, 0, 20, 20))

        assert tracker.release(self.release(), QRect(0, 0, 20, 20)) is False

    def test_a_twitch_is_not_yet_a_drag(self, app: object) -> None:
        tracker = ClickTracker()
        tracker.press(self.press(QPoint(5, 5)))

        assert tracker.dragged_past(self.move(QPoint(6, 5)), 10) is False
        assert tracker.pressed is True

    def test_moving_far_enough_is_a_drag(self, app: object) -> None:
        tracker = ClickTracker()
        tracker.press(self.press(QPoint(5, 5)))

        assert tracker.dragged_past(self.move(QPoint(50, 5)), 10) is True

    def test_a_drag_spends_the_press_so_the_release_is_not_a_click(self, app: object) -> None:
        tracker = ClickTracker()
        tracker.press(self.press(QPoint(5, 5)))
        tracker.dragged_past(self.move(QPoint(50, 5)), 10)

        assert tracker.release(self.release(QPoint(50, 5)), QRect(0, 0, 100, 100)) is False

    def test_nothing_drags_without_a_press_behind_it(self, app: object) -> None:
        assert ClickTracker().dragged_past(self.move(QPoint(50, 5)), 10) is False

    def test_cancelling_gives_up_on_the_press(self, app: object) -> None:
        tracker = ClickTracker()
        tracker.press(self.press())
        tracker.cancel()

        assert tracker.pressed is False
        assert tracker.release(self.release(), QRect(0, 0, 20, 20)) is False
