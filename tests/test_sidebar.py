"""How the inspector's pile sizes its cards"""

from PySide6.QtCore import QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from texturefriend.grid.decodes import FULL_SIZE, full_size
from texturefriend.panes.inspector import card_room
from texturefriend.panes.sidebar import pile_card

# what a widget's maximum height is until something sets one
WIDGET_MAX = 16777215


class TestCardRoom:
    def test_an_unlaid_sidebar_composes_at_full_size(self, app: QApplication) -> None:
        assert card_room(QSize()) == QSize(FULL_SIZE, FULL_SIZE)
        assert card_room(QSize(0, 300)) == QSize(FULL_SIZE, FULL_SIZE)

    def test_an_unshared_height_is_held_to_full_size(self, app: QApplication) -> None:
        assert card_room(QSize(456, WIDGET_MAX)) == QSize(456, FULL_SIZE)

    def test_a_room_bigger_than_a_full_decode_is_held_to_it(self, app: QApplication) -> None:
        assert card_room(QSize(2000, 1500)) == QSize(FULL_SIZE, FULL_SIZE)


class TestPileCard:
    def test_the_card_keeps_its_size_when_the_decode_lands(self, app: QApplication) -> None:
        natural = QSize(1024, 512)
        room = QSize(456, 1412)

        stand_in = pile_card(QPixmap(100, 50), natural, room)
        landed = pile_card(QPixmap(full_size(natural)), natural, room)

        assert stand_in.size() == landed.size() == QSize(456, 228)

    def test_a_wide_card_fits_a_short_room(self, app: QApplication) -> None:
        card = pile_card(QPixmap(100, 25), QSize(1024, 256), QSize(600, 100))

        assert card.size() == QSize(400, 100)

    def test_a_card_smaller_than_the_room_is_left_alone(self, app: QApplication) -> None:
        pixmap = QPixmap(64, 64)

        assert pile_card(pixmap, QSize(64, 64), QSize(456, 456)).cacheKey() == pixmap.cacheKey()

    def test_a_card_of_unknown_shape_is_still_held_to_the_room(self, app: QApplication) -> None:
        assert pile_card(QPixmap(800, 400), QSize(), QSize(200, 200)).size() == QSize(200, 100)
