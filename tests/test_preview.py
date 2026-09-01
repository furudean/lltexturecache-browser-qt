"""The tool window showing one texture at the size it was drawn"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.view.checkerboard import CheckerTone, pane_tone, set_pane_tone
from lltexturecache_browser_qt.panes.preview import (
    MIN_PANE_SIZE,
    WINDOW_TITLE,
    PreviewWindow,
    nearest,
    preview_title,
)
from tests import fakes


@pytest.fixture
def window(app: QApplication) -> Iterator[PreviewWindow]:
    built = PreviewWindow()

    yield built

    built.close()


def settled(window: PreviewWindow, app: QApplication) -> None:
    """Let the geometry events a resize queues reach the window

    Nothing is delivered to a window that was never shown, and the size the
    window remembers is read off those events rather than off the resize.
    """

    window.show()

    app.processEvents()


def card(width: int = 40, height: int = 40, alpha: int = 0xFF) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.red if alpha == 0xFF else Qt.GlobalColor.transparent)

    return pixmap


class TestNearest:
    def test_an_edge_already_inside_the_room_is_left_alone(self) -> None:
        assert nearest(50, 100, 0, 1000) == 50

    def test_an_edge_off_the_near_side_is_pulled_back(self) -> None:
        assert nearest(-30, 100, 0, 1000) == 0

    def test_an_edge_off_the_far_side_is_pulled_back(self) -> None:
        assert nearest(950, 100, 0, 1000) == 901

    def test_something_wider_than_the_room_is_left_at_the_near_edge(self) -> None:
        assert nearest(50, 2000, 0, 1000) == 0


class TestPreviewTitle:
    def test_a_decoded_texture_is_titled_with_its_shape(self) -> None:
        title = preview_title(fakes.texture(), QSize(512, 256))

        assert "512" in title
        assert "256" in title

    def test_an_undecoded_texture_leaves_the_shape_out(self) -> None:
        title = preview_title(fakes.texture(), QSize())

        assert "×" not in title

    def test_an_incomplete_texture_says_so(self) -> None:
        assert "incomplete" in preview_title(fakes.texture(complete=False), QSize(64, 64))

    def test_a_complete_texture_does_not(self) -> None:
        assert "incomplete" not in preview_title(fakes.texture(), QSize(64, 64))

    def test_the_uuid_leads_the_title(self) -> None:
        texture = fakes.texture()

        assert preview_title(texture, QSize(64, 64)).startswith(texture.uuid)


class TestWindowStates:
    def test_a_fresh_window_is_titled_plainly(self, window: PreviewWindow) -> None:
        assert window.windowTitle() == WINDOW_TITLE

    def test_a_window_never_shrinks_past_a_grabbable_size(self, window: PreviewWindow) -> None:
        assert window.minimumSize() == QSize(MIN_PANE_SIZE, MIN_PANE_SIZE)

    def test_showing_a_texture_titles_the_window_for_it(self, window: PreviewWindow) -> None:
        texture = fakes.texture()
        window.show_texture(texture, (card(), QSize(64, 64)), None)

        assert texture.uuid in window.windowTitle()

    def test_clearing_puts_the_title_back(self, window: PreviewWindow) -> None:
        window.show_texture(fakes.texture(), (card(), QSize(64, 64)), None)
        window.clear()

        assert window.windowTitle() == WINDOW_TITLE
        assert window._message == "No selection"

    def test_a_texture_still_decoding_says_so(self, window: PreviewWindow) -> None:
        window.show_texture(fakes.texture(), None, None)

        assert window._message == "Decoding..."

    def test_a_texture_that_would_not_decode_says_so(self, window: PreviewWindow) -> None:
        window.show_texture(fakes.texture(), (QPixmap(), QSize()), None)

        assert window._message == "Could not decode"

    def test_an_incomplete_texture_says_so(self, window: PreviewWindow) -> None:
        window.show_texture(fakes.texture(complete=False), None, None)

        assert window._message == "Texture incomplete"

    def test_a_stand_in_is_shown_while_the_decode_is_out(self, window: PreviewWindow) -> None:
        stand_in = card(8, 8)

        window.show_texture(fakes.texture(), None, (stand_in, QSize(64, 64)))

        assert window._pixmap.size() == stand_in.size()

    def test_the_decode_is_preferred_over_the_stand_in(self, window: PreviewWindow) -> None:
        window.show_texture(fakes.texture(), (card(64, 64), QSize(64, 64)), (card(8, 8), QSize(64, 64)))

        assert window._pixmap.size() == QSize(64, 64)


class TestShaping:
    def test_a_window_takes_the_shape_of_the_texture(self, window: PreviewWindow) -> None:
        window.show_texture(fakes.texture(), (card(), QSize(400, 200)), None)

        assert window.width() > window.height()

    def test_a_texture_is_shaped_once_rather_than_on_every_decode(self, window: PreviewWindow) -> None:
        texture = fakes.texture()

        window.show_texture(texture, (card(), QSize(400, 200)), None)
        window.resize(300, 300)
        window.show_texture(texture, (card(), QSize(400, 200)), None)

        assert window.size() == QSize(300, 300)

    def test_a_different_texture_shapes_the_window_again(self, window: PreviewWindow) -> None:
        window.show_texture(fakes.texture(uuid="one"), (card(), QSize(400, 200)), None)
        window.resize(300, 300)
        window.show_texture(fakes.texture(uuid="two"), (card(), QSize(200, 400)), None)

        assert window.height() > window.width()

    def test_a_texture_with_no_known_shape_leaves_the_window_alone(self, window: PreviewWindow) -> None:
        window.resize(300, 300)
        window.show_texture(fakes.texture(), None, None)

        assert window.size() == QSize(300, 300)

    def test_the_size_a_window_was_put_at_by_hand_is_what_shapes_are_given(
        self, window: PreviewWindow, app: QApplication
    ) -> None:
        window.resize(200, 200)
        settled(window, app)

        assert window._box == QSize(200, 200)

    def test_a_shape_taken_on_is_not_mistaken_for_a_resize_by_hand(
        self, window: PreviewWindow, app: QApplication
    ) -> None:
        window.resize(200, 200)
        settled(window, app)

        window.show_texture(fakes.texture(), (card(), QSize(400, 100)), None)

        app.processEvents()

        assert window._box == QSize(200, 200)

    def test_a_shape_is_laid_inside_the_room_it_was_given(self, window: PreviewWindow, app: QApplication) -> None:
        window.resize(200, 200)
        settled(window, app)

        window.show_texture(fakes.texture(), (card(), QSize(400, 200)), None)

        assert window.width() <= 200
        assert window.height() <= 200


class TestInteraction:
    def test_a_click_on_a_texture_cycles_the_checkerboard(self, window: PreviewWindow) -> None:
        set_pane_tone(CheckerTone.LIGHT)

        window.resize(100, 100)
        window.show_texture(fakes.texture(), (card(), QSize(64, 64)), None)

        window.mousePressEvent(self.click(QEvent.Type.MouseButtonPress))
        window.mouseReleaseEvent(self.click(QEvent.Type.MouseButtonRelease))

        assert pane_tone() is not CheckerTone.LIGHT

    def test_a_click_on_an_empty_window_does_nothing(self, window: PreviewWindow) -> None:
        set_pane_tone(CheckerTone.LIGHT)

        window.resize(100, 100)
        window.clear()

        window.mousePressEvent(self.click(QEvent.Type.MouseButtonPress))
        window.mouseReleaseEvent(self.click(QEvent.Type.MouseButtonRelease))

        assert pane_tone() is CheckerTone.LIGHT

    def test_space_closes_the_window(self, window: PreviewWindow) -> None:
        window.show()
        window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier))

        assert window.isVisible() is False

    def test_escape_closes_the_window(self, window: PreviewWindow) -> None:
        window.show()
        window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))

        assert window.isVisible() is False

    def test_closing_announces_itself(self, window: PreviewWindow) -> None:
        seen: list[None] = []
        window.closed.connect(lambda: seen.append(None))

        window.close()

        assert len(seen) == 1

    @staticmethod
    def click(kind: QEvent.Type) -> QMouseEvent:
        at = QPointF(QPoint(10, 10))
        held = Qt.MouseButton.LeftButton if kind == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton

        return QMouseEvent(kind, at, at, Qt.MouseButton.LeftButton, held, Qt.KeyboardModifier.NoModifier)
