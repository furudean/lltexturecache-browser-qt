"""Laying a selection out as a tilted pile of cards"""

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.checkerboard import CHECKERBOARD_SIZE
from lltexturecache_browser_qt.stack import (
    STACK_SPAN_RATIO,
    biggest_card,
    card_transform,
    checker_square_size,
    dealt_card,
    stack_pixmap,
)


def card(width: int, height: int, color: str = "red") -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(color))

    return pixmap


class TestCardTransform:
    def test_the_same_texture_is_always_dealt_the_same_way(self, app: QApplication) -> None:
        assert card_transform("abc", 100.0) == card_transform("abc", 100.0)

    def test_two_textures_are_dealt_differently(self, app: QApplication) -> None:
        assert card_transform("abc", 100.0) != card_transform("def", 100.0)

    def test_a_card_is_tilted_rather_than_left_square(self, app: QApplication) -> None:
        assert not card_transform("abc", 100.0).isIdentity()


class TestBiggestCard:
    def test_the_card_taking_the_most_room_sets_the_size(self, app: QApplication) -> None:
        cards = [("a", card(10, 100)), ("b", card(40, 40)), ("c", card(90, 10))]

        assert biggest_card(cards) == QSize(40, 40)

    def test_a_single_card_sets_its_own_size(self, app: QApplication) -> None:
        assert biggest_card([("a", card(30, 20))]) == QSize(30, 20)


class TestDealtCard:
    def test_a_card_already_the_right_size_is_handed_straight_back(self, app: QApplication) -> None:
        pixmap = card(40, 40)

        assert dealt_card(pixmap, QSize(40, 40), round(40 * STACK_SPAN_RATIO)) is pixmap

    def test_a_dealt_card_keeps_its_shape(self, app: QApplication) -> None:
        dealt = dealt_card(card(80, 20), QSize(40, 40), 50)

        assert dealt.width() > dealt.height()

    def test_a_small_card_is_blown_up_to_sit_with_the_rest(self, app: QApplication) -> None:
        small = card(8, 8)
        dealt = dealt_card(small, QSize(64, 64), 80)

        assert dealt.width() > small.width()

    def test_a_card_never_deals_to_nothing(self, app: QApplication) -> None:
        dealt = dealt_card(card(1000, 1), QSize(4, 4), 5)

        assert dealt.width() >= 1
        assert dealt.height() >= 1

    def test_a_card_is_never_dealt_past_the_span(self, app: QApplication) -> None:
        dealt = dealt_card(card(400, 400), QSize(40, 40), 50)

        assert max(dealt.width(), dealt.height()) <= 50


class TestCheckerSquareSize:
    def test_with_no_room_given_the_squares_stay_their_own_size(self, app: QApplication) -> None:
        assert checker_square_size(QSize(100, 100), None) == CHECKERBOARD_SIZE

    def test_an_empty_room_leaves_the_squares_alone(self, app: QApplication) -> None:
        assert checker_square_size(QSize(100, 100), QSize(0, 0)) == CHECKERBOARD_SIZE

    def test_an_empty_canvas_leaves_the_squares_alone(self, app: QApplication) -> None:
        assert checker_square_size(QSize(0, 0), QSize(50, 50)) == CHECKERBOARD_SIZE

    def test_a_stack_shown_smaller_gets_larger_squares(self, app: QApplication) -> None:
        # the squares are drawn into the stack, so being shrunk on the way out
        # has to be paid for on the way in
        assert checker_square_size(QSize(400, 400), QSize(100, 100)) > CHECKERBOARD_SIZE

    def test_a_stack_shown_at_its_own_size_keeps_its_squares(self, app: QApplication) -> None:
        assert checker_square_size(QSize(100, 100), QSize(100, 100)) == CHECKERBOARD_SIZE

    def test_a_stack_shown_larger_is_not_given_smaller_squares(self, app: QApplication) -> None:
        assert checker_square_size(QSize(50, 50), QSize(400, 400)) == CHECKERBOARD_SIZE


class TestStackPixmap:
    def test_an_empty_stack_is_a_null_pixmap(self, app: QApplication) -> None:
        assert stack_pixmap([]).isNull()

    def test_one_card_comes_back_about_its_own_size(self, app: QApplication) -> None:
        stacked = stack_pixmap([("a", card(40, 40))])

        assert stacked.width() == pytest.approx(40, abs=4)
        assert stacked.height() == pytest.approx(40, abs=4)

    def test_a_pile_reaches_further_than_the_card_on_top(self, app: QApplication) -> None:
        cards = [(f"texture-{index}", card(40, 40)) for index in range(4)]
        stacked = stack_pixmap(cards)

        assert stacked.width() > 40

    def test_a_pile_lays_out_the_same_way_every_time(self, app: QApplication) -> None:
        cards = [(f"texture-{index}", card(40, 40)) for index in range(4)]

        assert stack_pixmap(cards).size() == stack_pixmap(cards).size()

    def test_a_pile_of_transparent_cards_is_laid_out(self, app: QApplication) -> None:
        clear = QPixmap(40, 40)
        clear.fill(QColor(0xFF, 0x00, 0x00, 0x80))

        assert not stack_pixmap([("a", clear), ("b", clear)]).isNull()

    def test_the_room_a_stack_is_seen_at_does_not_change_its_size(self, app: QApplication) -> None:
        cards = [(f"texture-{index}", card(40, 40)) for index in range(3)]

        assert stack_pixmap(cards, QSize(20, 20)).size() == stack_pixmap(cards).size()
