"""The grid of texture cells and the state it keeps around scrolling"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, QStringListModel, Qt
from PySide6.QtGui import QIcon, QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem, QWidget

from lltexturecache_browser_qt.grid import (
    MESSAGE_WIDTH,
    CellDelegate,
    EmptyState,
    TextureGrid,
    icon_mode,
)
from lltexturecache_browser_qt.images import THUMBNAIL_SIZE


@pytest.fixture
def grid(app: QApplication) -> Iterator[TextureGrid]:
    view = TextureGrid()

    yield view

    view.close()


def key(code: Qt.Key) -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, code, Qt.KeyboardModifier.NoModifier)


class TestIconMode:
    def test_a_disabled_cell_is_drawn_disabled(self) -> None:
        assert icon_mode(QStyle.StateFlag.State_None) == QIcon.Mode.Disabled

    def test_a_selected_cell_is_drawn_selected(self) -> None:
        state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Selected

        assert icon_mode(state) == QIcon.Mode.Selected

    def test_an_ordinary_cell_is_drawn_normally(self) -> None:
        assert icon_mode(QStyle.StateFlag.State_Enabled) == QIcon.Mode.Normal


class TestCellDelegate:
    def test_a_cell_is_a_thumbnail_square(self, app: QApplication) -> None:
        hint = CellDelegate().sizeHint(QStyleOptionViewItem(), QStringListModel(["a"]).index(0, 0))

        assert hint == QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE)

    def test_an_icon_with_nothing_in_it_marks_no_box(self, app: QApplication) -> None:
        assert CellDelegate().image_rect(QIcon(), QRect(0, 0, 100, 100), 2, 0) is None

    def test_a_mark_is_drawn_inside_the_image_rather_than_the_cell(self, app: QApplication) -> None:
        pixmap = QPixmap(40, 40)
        pixmap.fill(Qt.GlobalColor.red)

        box = CellDelegate().image_rect(QIcon(pixmap), QRect(0, 0, 100, 100), 2, 0)

        assert box is not None
        assert box.width() < 100
        assert box.center().toPoint() == QPoint(50, 50)

    def test_a_wider_mark_is_inset_further(self, app: QApplication) -> None:
        pixmap = QPixmap(40, 40)
        pixmap.fill(Qt.GlobalColor.red)

        icon = QIcon(pixmap)
        rect = QRect(0, 0, 100, 100)

        wide = CellDelegate().image_rect(icon, rect, 8, 0)
        narrow = CellDelegate().image_rect(icon, rect, 2, 0)

        assert wide is not None and narrow is not None
        assert wide.width() < narrow.width()


class TestEmptyState:
    def test_a_short_message_is_left_on_one_line(self, holder: QWidget) -> None:
        panel = EmptyState(holder)
        panel.set_message("No textures")

        assert panel.wordWrap() is False
        assert panel.width() < MESSAGE_WIDTH

    def test_a_long_message_wraps_within_the_reading_width(self, holder: QWidget) -> None:
        panel = EmptyState(holder)
        panel.set_message("No textures here " * 20)

        assert panel.wordWrap() is True
        assert panel.width() == MESSAGE_WIDTH

    def test_the_message_set_is_the_message_shown(self, holder: QWidget) -> None:
        panel = EmptyState(holder)
        panel.set_message("No textures")

        assert panel.text() == "No textures"


class TestEmptyGrid:
    def test_a_grid_with_no_model_is_empty(self, grid: TextureGrid) -> None:
        assert grid.is_empty() is True

    def test_a_grid_with_rows_is_not_empty(self, grid: TextureGrid) -> None:
        grid.setModel(QStringListModel(["a", "b"]))

        assert grid.is_empty() is False

    def test_a_model_with_no_rows_leaves_the_grid_empty(self, grid: TextureGrid) -> None:
        grid.setModel(QStringListModel([]))

        assert grid.is_empty() is True

    def test_the_panel_is_up_only_while_the_grid_is_empty(self, grid: TextureGrid) -> None:
        assert grid._empty.isHidden() is False

        grid.setModel(QStringListModel(["a"]))

        assert grid._empty.isHidden() is True

    def test_emptying_a_grid_brings_the_panel_back(self, grid: TextureGrid) -> None:
        model = QStringListModel(["a"])
        grid.setModel(model)

        model.setStringList([])

        assert grid._empty.isHidden() is False

    def test_swapping_the_model_stops_listening_to_the_old_one(self, grid: TextureGrid) -> None:
        first = QStringListModel(["a"])
        grid.setModel(first)
        grid.setModel(QStringListModel([]))

        # the old model still exists, and must no longer speak for the grid
        first.setStringList(["a", "b"])

        assert grid.is_empty() is True

    def test_a_model_can_be_taken_away_again(self, grid: TextureGrid) -> None:
        grid.setModel(QStringListModel(["a"]))
        grid.setModel(None)

        assert grid.is_empty() is True


class TestPinning:
    def test_a_grid_is_not_pinned_to_begin_with(self, grid: TextureGrid) -> None:
        assert grid._pin is None

    def test_pinning_to_a_place_keeps_it(self, grid: TextureGrid) -> None:
        grid.pin_to(40)

        assert grid._pin == 40

    def test_pinning_to_the_bottom_is_its_own_place(self, grid: TextureGrid) -> None:
        grid.pin_to_bottom()

        assert grid._pin == -1

    def test_the_wheel_lets_a_pin_go(self, grid: TextureGrid) -> None:
        grid.pin_to_bottom()
        grid.unpin()

        assert grid._pin is None

    def test_a_key_press_lets_a_pin_go(self, grid: TextureGrid) -> None:
        grid.setModel(QStringListModel(["a"]))
        grid.pin_to_bottom()

        grid.keyPressEvent(key(Qt.Key.Key_Down))

        assert grid._pin is None

    def test_scrolling_to_a_texture_outranks_the_pin(self, grid: TextureGrid) -> None:
        model = QStringListModel(["a", "b"])
        grid.setModel(model)
        grid.pin_to_bottom()

        grid.scrollTo(model.index(0, 0))

        assert grid._pin is None

    def test_the_place_reported_is_the_scrollbar_value(self, grid: TextureGrid) -> None:
        assert grid.place() == grid.verticalScrollBar().value()


class TestPreviewKey:
    def test_space_asks_for_a_preview(self, grid: TextureGrid) -> None:
        seen: list[None] = []
        grid.previewed.connect(lambda: seen.append(None))

        grid.keyPressEvent(key(Qt.Key.Key_Space))

        assert len(seen) == 1

    def test_another_key_does_not(self, grid: TextureGrid) -> None:
        seen: list[None] = []
        grid.previewed.connect(lambda: seen.append(None))

        grid.setModel(QStringListModel(["a"]))
        grid.keyPressEvent(key(Qt.Key.Key_Down))

        assert seen == []


class TestSelection:
    def test_a_grid_with_no_model_has_nothing_selected(self, grid: TextureGrid) -> None:
        assert grid.has_selection() is False

    def test_a_grid_with_nothing_picked_has_nothing_selected(self, grid: TextureGrid) -> None:
        grid.setModel(QStringListModel(["a", "b"]))

        assert grid.has_selection() is False

    def test_a_picked_row_counts_as_a_selection(self, grid: TextureGrid) -> None:
        model = QStringListModel(["a", "b"])
        grid.setModel(model)
        grid.selectionModel().select(model.index(0, 0), grid.selectionModel().SelectionFlag.Select)

        assert grid.has_selection() is True


class TestDragging:
    def test_starting_a_drag_announces_it(self, grid: TextureGrid) -> None:
        seen: list[None] = []
        grid.dragged.connect(lambda: seen.append(None))

        grid.startDrag(Qt.DropAction.CopyAction)

        assert len(seen) == 1

    def test_the_release_that_ends_a_drag_is_not_a_click(self, grid: TextureGrid) -> None:
        grid.setModel(QStringListModel(["a", "b"]))
        grid.startDrag(Qt.DropAction.CopyAction)

        assert grid._dragged is True

        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(1, 1),
            QPointF(1, 1),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )

        grid.mouseReleaseEvent(release)

        # the flag is spent on the release that ended the drag, so the next
        # click is a click again
        assert grid._dragged is False
