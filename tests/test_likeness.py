"""What one picture is remembered by, and how near two of them are"""

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.cache.color import QUANTIZE
from lltexturecache_browser_qt.cache.likeness import (
    BACKDROP,
    CELLS,
    Descriptor,
    LikenessIndex,
    describe,
    layout,
    likeness,
    over_backdrop,
    rounded,
    shared,
    squashed,
)

SIDE = 16


def painted(top: QColor, bottom: QColor, *, upright: bool = True) -> QImage:
    """A picture of two halves, cut across or down"""

    image = QImage(SIDE, SIDE, QImage.Format.Format_ARGB32)

    for x in range(SIDE):
        for y in range(SIDE):
            near = y < SIDE // 2 if upright else x < SIDE // 2

            image.setPixelColor(x, y, top if near else bottom)

    return image


def dimmed(image: QImage, share: float) -> QImage:
    """The picture as it looks under less light"""

    faded = image.copy()

    for x in range(SIDE):
        for y in range(SIDE):
            color = faded.pixelColor(x, y)

            faded.setPixelColor(
                x,
                y,
                QColor.fromRgb(
                    round(color.red() * share),
                    round(color.green() * share),
                    round(color.blue() * share),
                    color.alpha(),
                ),
            )

    return faded


def described(image: QImage) -> Descriptor:
    found = describe(image)

    assert found is not None

    return found


class TestSquashed:
    def test_a_picture_comes_out_as_one_cell_a_patch(self, app: QApplication) -> None:
        assert len(squashed(painted(QColor("black"), QColor("white")))) == CELLS

    def test_one_flat_colour_fills_every_cell_with_itself(self, app: QApplication) -> None:
        cells = squashed(painted(QColor("red"), QColor("red")))

        assert all(cell == cells[0] for cell in cells)

    def test_a_solid_picture_is_solid_in_every_cell(self, app: QApplication) -> None:
        cells = squashed(painted(QColor("black"), QColor("white")))

        assert all(cell[3] == 100.0 for cell in cells)

    def test_a_clear_picture_is_clear_in_every_cell(self, app: QApplication) -> None:
        clear = QImage(SIDE, SIDE, QImage.Format.Format_ARGB32)
        clear.fill(QColor(0, 0, 0, 0))

        assert all(cell[3] == 0.0 for cell in squashed(clear))


class TestRounded:
    def test_a_colour_is_left_on_the_grid_the_lab_table_is_kept_against(self) -> None:
        assert rounded(0x123456) == (QUANTIZE[0x12] << 16 | QUANTIZE[0x34] << 8 | QUANTIZE[0x56])

    def test_rounding_a_rounded_colour_leaves_it_where_it_is(self) -> None:
        once = rounded(0x123456)

        assert rounded(once) == once

    def test_the_ends_of_the_range_land_on_themselves(self) -> None:
        assert rounded(0x000000) == 0x000000
        assert rounded(0xFFFFFF) == 0xFFFFFF


class TestOverBackdrop:
    def test_a_solid_pixel_is_left_where_it_is(self) -> None:
        assert over_backdrop(0xFF123456, 0xFF) == 0x123456

    def test_a_clear_pixel_is_the_backdrop_and_nothing_of_its_own(self) -> None:
        packed = BACKDROP << 16 | BACKDROP << 8 | BACKDROP

        assert over_backdrop(0x00FFFFFF, 0x00) == packed

    def test_a_half_clear_pixel_meets_the_backdrop_halfway(self) -> None:
        halved = over_backdrop(0x80000000, 0x80)

        assert halved & 0xFF == round(BACKDROP * (1 - 0x80 / 255))


class TestLayout:
    def test_a_channel_that_never_moves_has_no_layout(self) -> None:
        assert layout([5.0] * CELLS) == ((0.0,) * CELLS, 0.0)

    def test_how_high_the_channel_sits_is_taken_out_of_it(self) -> None:
        low, _ = layout([1.0, 2.0, 3.0, 4.0])
        high, _ = layout([101.0, 102.0, 103.0, 104.0])

        assert low == high

    def test_how_far_it_swings_is_taken_out_of_it(self) -> None:
        gentle, near = layout([1.0, 2.0, 3.0, 4.0])
        steep, far = layout([10.0, 20.0, 30.0, 40.0])

        assert gentle == steep
        assert far > near


class TestShared:
    def test_two_that_reach_as_far_share_all_of_it(self) -> None:
        assert shared(3.0, 3.0) == 1.0

    def test_the_fainter_of_the_two_is_what_is_shared(self) -> None:
        assert shared(1.0, 4.0) == 0.25

    def test_nothing_is_shared_with_a_layout_that_is_not_there(self) -> None:
        assert shared(0.0, 4.0) == 0.0


class TestDescribe:
    def test_there_is_nothing_to_remember_an_empty_image_by(self) -> None:
        assert describe(QImage()) is None

    def test_a_flat_colour_has_no_layout_to_remember(self, app: QApplication) -> None:
        found = described(painted(QColor("red"), QColor("red")))

        assert found.contrast == 0.0
        assert found.colourfulness == 0.0

    def test_a_picture_of_two_halves_has_a_layout(self, app: QApplication) -> None:
        assert described(painted(QColor("black"), QColor("white"))).contrast > 0.0

    def test_a_solid_picture_has_no_outline_to_remember(self, app: QApplication) -> None:
        assert described(painted(QColor("black"), QColor("white"))).shapeliness == 0.0


class TestLikeness:
    def test_a_picture_looks_exactly_like_itself(self, app: QApplication) -> None:
        found = described(painted(QColor("black"), QColor("white")))

        assert likeness(found, found) > 0.9

    def test_the_same_picture_under_less_light_still_looks_like_it(self, app: QApplication) -> None:
        picture = painted(QColor("navy"), QColor("khaki"))

        assert likeness(described(dimmed(picture, 0.7)), described(picture)) > 0.9

    def test_the_same_layout_the_other_way_up_looks_less_like_it_than_nothing_does(self, app: QApplication) -> None:
        upright = described(painted(QColor("black"), QColor("white")))
        upended = described(painted(QColor("white"), QColor("black")))

        assert likeness(upright, upended) < 0.0

    def test_the_same_layout_in_the_opposite_colour_is_still_an_answer(self, app: QApplication) -> None:
        """A penalty meant to settle ties should not put a layout out of the running

        The two are laid out alike to the pixel and painted the colours that
        stand furthest apart in lab, which is the most the colour penalty can
        ever come to.
        """

        query = described(painted(QColor("#303000"), QColor("#ffff80")))
        opposed = described(painted(QColor("#000030"), QColor("#8080ff")))
        upended = described(painted(QColor("#ffff80"), QColor("#303000")))

        assert likeness(query, opposed) > likeness(query, upended)

    def test_a_layout_lying_the_other_way_looks_less_like_it(self, app: QApplication) -> None:
        query = described(painted(QColor("black"), QColor("white")))
        along = described(painted(QColor("black"), QColor("white")))
        across = described(painted(QColor("black"), QColor("white"), upright=False))

        assert likeness(query, along) > likeness(query, across)

    def test_the_same_layout_in_another_colour_looks_less_like_it(self, app: QApplication) -> None:
        query = described(painted(QColor("darkred"), QColor("pink")))
        same = described(painted(QColor("darkred"), QColor("pink")))
        other = described(painted(QColor("darkgreen"), QColor("lightgreen")))

        assert likeness(query, same) > likeness(query, other)


class TestLikenessIndex:
    def test_an_index_is_as_long_as_the_cache_it_was_built_over(self) -> None:
        assert len(LikenessIndex(7)) == 7

    def test_a_row_the_scan_read_nothing_of_is_left_out_rather_than_scored(self, app: QApplication) -> None:
        index = LikenessIndex(2)
        index.add(0, described(painted(QColor("black"), QColor("white"))))

        scores = index.scores(described(painted(QColor("black"), QColor("white"))))

        assert 1 not in scores

    def test_every_row_is_scored_against_the_picture(self, app: QApplication) -> None:
        index = LikenessIndex(2)
        index.add(0, described(painted(QColor("black"), QColor("white"))))
        index.add(1, described(painted(QColor("white"), QColor("black"))))

        scores = index.scores(described(painted(QColor("black"), QColor("white"))))

        assert scores[0] > scores[1]
