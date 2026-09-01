"""The pane describing whatever is selected in the grid"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, Qt
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from lltexturecache_browser_qt.panes.inspector import (
    SIDEBAR_MIN_HEIGHT,
    InspectorPane,
    SidebarLabel,
)
from tests import fakes


@pytest.fixture
def sidebar(holder: QWidget) -> SidebarLabel:
    return SidebarLabel(holder)


@pytest.fixture
def pane(app: QApplication) -> Iterator[InspectorPane]:
    built = InspectorPane()

    yield built

    built.close()


def press(at: QPoint, button: Qt.MouseButton = Qt.MouseButton.LeftButton) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(at),
        QPointF(at),
        button,
        button,
        Qt.KeyboardModifier.NoModifier,
    )


def move(at: QPoint) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(at),
        QPointF(at),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def release(at: QPoint) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(at),
        QPointF(at),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


class TestSidebarHeight:
    def test_an_empty_sidebar_keeps_a_minimum_height(self, sidebar: SidebarLabel) -> None:
        assert sidebar.heightForWidth(200) == SIDEBAR_MIN_HEIGHT

    def test_a_wide_texture_is_shorter_than_a_tall_one(self, sidebar: SidebarLabel) -> None:
        sidebar.setMaximumHeight(1000)

        sidebar.set_source(fakes.card(400, 100))
        wide = sidebar.heightForWidth(200)

        sidebar.set_source(fakes.card(100, 400))
        tall = sidebar.heightForWidth(200)

        assert wide < tall

    def test_a_small_texture_is_not_blown_up_past_its_own_size(self, sidebar: SidebarLabel) -> None:
        sidebar.setMaximumHeight(1000)
        sidebar.set_source(fakes.card(32, 32))

        assert sidebar.box(400) == QSize(32, 32)

    def test_the_room_asked_for_is_in_device_pixels(self, sidebar: SidebarLabel) -> None:
        sidebar.resize(100, 100)
        sidebar.setMaximumHeight(80)

        assert sidebar.room() == QSize(100, 80) * sidebar.devicePixelRatioF()


class TestSidebarTip:
    def test_an_opaque_texture_offers_dragging_and_a_menu(self, sidebar: SidebarLabel) -> None:
        sidebar.set_source(fakes.card())

        assert "Drag out to save" in sidebar.toolTip()
        assert "alpha" not in sidebar.toolTip()

    def test_a_transparent_texture_offers_the_checkerboard_too(self, sidebar: SidebarLabel) -> None:
        sidebar.set_source(fakes.card(), transparent=True)

        assert "alpha" in sidebar.toolTip()


class TestSidebarMouse:
    def test_a_click_on_a_texture_is_reported(self, sidebar: SidebarLabel) -> None:
        sidebar.resize(100, 100)
        sidebar.set_source(fakes.card())

        seen: list[None] = []
        sidebar.clicked.connect(lambda: seen.append(None))

        sidebar.mousePressEvent(press(QPoint(10, 10)))
        sidebar.mouseReleaseEvent(release(QPoint(10, 10)))

        assert len(seen) == 1

    def test_a_click_on_an_empty_sidebar_is_not(self, sidebar: SidebarLabel) -> None:
        sidebar.resize(100, 100)

        seen: list[None] = []
        sidebar.clicked.connect(lambda: seen.append(None))

        sidebar.mousePressEvent(press(QPoint(10, 10)))
        sidebar.mouseReleaseEvent(release(QPoint(10, 10)))

        assert seen == []

    def test_dragging_far_enough_starts_a_drag_rather_than_a_click(self, sidebar: SidebarLabel) -> None:
        sidebar.resize(200, 200)
        sidebar.set_source(fakes.card())

        clicks: list[None] = []
        drags: list[None] = []

        sidebar.clicked.connect(lambda: clicks.append(None))
        sidebar.dragged.connect(lambda: drags.append(None))

        sidebar.mousePressEvent(press(QPoint(10, 10)))
        sidebar.mouseMoveEvent(move(QPoint(10 + QApplication.startDragDistance() + 5, 10)))
        sidebar.mouseReleaseEvent(release(QPoint(60, 10)))

        assert len(drags) == 1
        assert clicks == []

    def test_a_twitch_is_still_a_click(self, sidebar: SidebarLabel) -> None:
        sidebar.resize(200, 200)
        sidebar.set_source(fakes.card())

        clicks: list[None] = []
        drags: list[None] = []

        sidebar.clicked.connect(lambda: clicks.append(None))
        sidebar.dragged.connect(lambda: drags.append(None))

        sidebar.mousePressEvent(press(QPoint(10, 10)))
        sidebar.mouseMoveEvent(move(QPoint(11, 10)))
        sidebar.mouseReleaseEvent(release(QPoint(11, 10)))

        assert drags == []
        assert len(clicks) == 1

    def test_a_right_click_asks_for_the_menu(self, sidebar: SidebarLabel) -> None:
        from PySide6.QtGui import QContextMenuEvent

        seen: list[QPoint] = []
        sidebar.menued.connect(seen.append)

        sidebar.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5), QPoint(105, 105)))

        assert seen == [QPoint(105, 105)]


class TestPaneStates:
    def test_a_fresh_pane_shows_nothing_selected(self, pane: InspectorPane) -> None:
        assert pane.texture is None
        assert pane._empty.isHidden() is False
        assert pane._details.isHidden() is True

    def test_showing_a_texture_puts_the_details_up(self, pane: InspectorPane) -> None:
        texture = fakes.texture()
        pane.show_texture(texture, 1, texture.image_size)

        assert pane.texture is texture
        assert pane._empty.isHidden() is True
        assert pane._details.isHidden() is False

    def test_clearing_puts_the_pane_back(self, pane: InspectorPane) -> None:
        pane.show_texture(fakes.texture(), 1, 1024)
        pane.clear()

        assert pane.texture is None
        assert pane._empty.isHidden() is False


class TestPaneDetails:
    def test_one_texture_is_titled_by_its_uuid(self, pane: InspectorPane) -> None:
        texture = fakes.texture()
        pane.show_texture(texture, 1, texture.image_size)

        assert pane._name.text() == texture.uuid

    def test_a_selection_is_titled_by_how_much_is_in_it(self, pane: InspectorPane) -> None:
        pane.show_texture(fakes.texture(), 4, 40960)

        assert "4 items" == pane._name.text()

    def test_a_selection_hides_the_rows_about_one_texture(self, pane: InspectorPane) -> None:
        pane.show_texture(fakes.texture(), 4, 40960)

        assert pane._information.isHidden() is True

    def test_a_complete_texture_is_named_an_image(self, pane: InspectorPane) -> None:
        pane.show_texture(fakes.texture(), 1, 1024)

        assert "image" in pane._kind.text()

    def test_an_incomplete_texture_is_named_a_thumbnail(self, pane: InspectorPane) -> None:
        pane.show_texture(fakes.texture(complete=False), 1, 1024)

        assert "thumbnail" in pane._kind.text()

    def test_the_entry_number_is_shown(self, pane: InspectorPane) -> None:
        pane.show_texture(fakes.texture(index=42), 1, 1024)

        assert "42" in pane._entry.text()


class TestPaneDimensions:
    def test_a_texture_with_no_decode_yet_says_so(self, pane: InspectorPane) -> None:
        pane.show_texture(fakes.texture(), 1, 1024)

        assert pane._dimensions.text() == "Decoding..."

    def test_a_decoded_texture_reports_its_shape(self, pane: InspectorPane) -> None:
        pane.show_texture(fakes.texture(), 1, 1024)
        pane.set_sidebar(fakes.card(), QSize(512, 256))

        assert "512" in pane._dimensions.text()
        assert "256" in pane._dimensions.text()

    def test_a_texture_that_would_not_decode_says_so(self, pane: InspectorPane) -> None:
        pane.show_texture(fakes.texture(), 1, 1024)
        pane.set_sidebar(QPixmap(), QSize())

        assert pane._dimensions.text() == "Could not decode"

    def test_an_incomplete_texture_has_no_shape_to_report(self, pane: InspectorPane) -> None:
        pane.show_texture(fakes.texture(complete=False), 1, 1024)
        pane.set_sidebar(fakes.card(), None)

        assert pane._dimensions.text() == "Unknown"
