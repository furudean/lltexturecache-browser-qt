"""Which textures the grid shows, and in what order"""

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.cache.color import ColorIndex, Signature, to_lab
from lltexturecache_browser_qt.cache.likeness import Descriptor, LikenessIndex, describe
from lltexturecache_browser_qt.cache.scan import Scan
from lltexturecache_browser_qt.grid.narrowing import SHORTLIST, Narrowing


def scanned(count: int, **rows: object) -> Scan:
    """A scan over `count` rows, with the named rows given a colour or flagged flat"""

    index = ColorIndex(count)

    for name, signature in rows.items():
        assert isinstance(signature, Signature)

        index.add(int(name.removeprefix("row")), signature)

    return Scan(colors=index, likeness=LikenessIndex(count))


def pictured(count: int, **rows: object) -> Scan:
    """A scan over `count` rows, with the named rows holding a picture"""

    likeness = LikenessIndex(count)

    for name, picture in rows.items():
        assert isinstance(picture, QImage)

        described = describe(picture)

        assert described is not None

        likeness.add(int(name.removeprefix("row")), described)

    return Scan(colors=ColorIndex(count), likeness=likeness)


def split(*, upright: bool, tinted: bool = False) -> QImage:
    """A picture of two halves, one dark and one light, cut one way or the other"""

    dark, light = (QColor("#000030"), QColor("#8080ff")) if tinted else (QColor("black"), QColor("white"))

    image = QImage(16, 16, QImage.Format.Format_ARGB32)
    image.fill(dark)

    for x in range(16):
        for y in range(16):
            half = y < 8 if upright else x < 8

            if half:
                image.setPixelColor(x, y, light)

    return image


def described(picture: QImage) -> Descriptor:
    found = describe(picture)

    assert found is not None

    return found


class TestAsking:
    def test_a_fresh_narrowing_asks_for_nothing(self) -> None:
        assert Narrowing().asking is False

    def test_a_colour_is_something_asked_for(self, app: QApplication) -> None:
        assert Narrowing(colors=[QColor("red")]).asking is True

    def test_hiding_simple_textures_is_something_asked_for(self) -> None:
        assert Narrowing(simple_hidden=True).asking is True

    def test_a_picture_is_something_asked_for(self, app: QApplication) -> None:
        assert Narrowing(reference=described(split(upright=True))).asking is True


class TestNarrowed:
    def test_nothing_asked_for_narrows_nothing(self) -> None:
        assert Narrowing().narrowed is False

    def test_a_colour_with_no_scan_behind_it_narrows_nothing_yet(self, app: QApplication) -> None:
        assert Narrowing(colors=[QColor("red")]).narrowed is False

    def test_a_colour_the_scan_can_answer_narrows_the_grid(self, app: QApplication) -> None:
        narrowing = Narrowing(colors=[QColor("red")], scan=scanned(3))

        assert narrowing.narrowed is True

    def test_hiding_simple_textures_is_not_narrowing_by_colour(self) -> None:
        assert Narrowing(simple_hidden=True, scan=scanned(3)).narrowed is False

    def test_a_picture_with_no_scan_behind_it_narrows_nothing_yet(self, app: QApplication) -> None:
        assert Narrowing(reference=described(split(upright=True))).narrowed is False

    def test_a_picture_the_scan_can_answer_narrows_the_grid(self, app: QApplication) -> None:
        narrowing = Narrowing(reference=described(split(upright=True)), scan=scanned(3))

        assert narrowing.narrowed is True


class TestMatching:
    def test_nothing_is_matched_against_no_picture(self) -> None:
        assert Narrowing(scan=scanned(3)).matching is False

    def test_a_picture_with_no_scan_behind_it_is_not_matching_yet(self, app: QApplication) -> None:
        assert Narrowing(reference=described(split(upright=True))).matching is False

    def test_a_picture_the_scan_can_answer_is_matching(self, app: QApplication) -> None:
        assert Narrowing(reference=described(split(upright=True)), scan=scanned(3)).matching is True


class TestHidden:
    def test_nothing_is_hidden_before_the_scan(self) -> None:
        assert Narrowing(simple_hidden=True).hidden() == 0

    def test_nothing_is_hidden_while_simple_textures_are_shown(self) -> None:
        scan = scanned(3, row0=Signature(flat=True))

        assert Narrowing(scan=scan).hidden() == 0

    def test_the_flat_textures_are_counted_when_they_are_hidden(self) -> None:
        scan = scanned(3, row0=Signature(flat=True), row1=Signature(flat=True))

        assert Narrowing(simple_hidden=True, scan=scan).hidden() == 2


class TestFlatUuids:
    def test_no_scan_means_nothing_is_known_to_be_flat(self) -> None:
        assert Narrowing().flat_uuids(["a", "b", "c"]) == set()

    def test_the_flat_rows_are_named(self) -> None:
        scan = scanned(3, row0=Signature(flat=True), row2=Signature(flat=True))

        assert Narrowing(scan=scan).flat_uuids(["a", "b", "c"]) == {"a", "c"}

    def test_flat_textures_are_named_whether_or_not_they_are_hidden(self) -> None:
        scan = scanned(2, row0=Signature(flat=True))

        assert Narrowing(simple_hidden=True, scan=scan).flat_uuids(["a", "b"]) == {"a"}


class TestKept:
    def test_nothing_asked_for_keeps_every_row_in_order(self) -> None:
        assert Narrowing().shown_rows(4) == [0, 1, 2, 3]

    def test_a_colour_with_no_scan_behind_it_cannot_be_answered(self, app: QApplication) -> None:
        assert Narrowing(colors=[QColor("red")]).shown_rows(4) is None

    def test_hiding_simple_textures_with_no_scan_cannot_be_answered(self) -> None:
        assert Narrowing(simple_hidden=True).shown_rows(4) is None

    def test_hiding_simple_textures_leaves_them_out(self) -> None:
        scan = scanned(4, row1=Signature(flat=True))

        assert Narrowing(simple_hidden=True, scan=scan).shown_rows(4) == [0, 2, 3]

    def test_showing_them_keeps_every_row(self) -> None:
        scan = scanned(4, row1=Signature(flat=True))

        assert Narrowing(scan=scan).shown_rows(4) == [0, 1, 2, 3]

    def test_a_colour_keeps_what_answers_for_it(self, app: QApplication) -> None:
        scan = scanned(
            3,
            row0=Signature(colors=[(to_lab(0xFF0000), 1.0)]),
            row1=Signature(colors=[(to_lab(0x0000FF), 1.0)]),
        )

        kept = Narrowing(colors=[QColor("red")], scan=scan).shown_rows(3)

        assert kept == [0]

    def test_the_best_match_comes_first(self, app: QApplication) -> None:
        scan = scanned(
            3,
            row0=Signature(colors=[(to_lab(0xFF0000), 0.3)]),
            row1=Signature(colors=[(to_lab(0xFF0000), 1.0)]),
        )

        kept = Narrowing(colors=[QColor("red")], scan=scan).shown_rows(3)

        assert kept is not None
        assert kept[0] == 1

    def test_a_colour_nothing_holds_keeps_nothing(self, app: QApplication) -> None:
        scan = scanned(2, row0=Signature(colors=[(to_lab(0x0000FF), 1.0)]))

        assert Narrowing(colors=[QColor("red")], scan=scan).shown_rows(2) == []

    def test_a_flat_texture_is_hidden_even_when_it_answers_for_the_colour(self, app: QApplication) -> None:
        scan = scanned(
            2,
            row0=Signature(colors=[(to_lab(0xFF0000), 1.0)], flat=True),
            row1=Signature(colors=[(to_lab(0xFF0000), 1.0)]),
        )

        kept = Narrowing(colors=[QColor("red")], simple_hidden=True, scan=scan).shown_rows(2)

        assert kept == [1]

    def test_asking_for_two_colours_keeps_what_holds_both(self, app: QApplication) -> None:
        scan = scanned(
            2,
            row0=Signature(colors=[(to_lab(0xFF0000), 1.0)]),
            row1=Signature(colors=[(to_lab(0xFF0000), 0.5), (to_lab(0x0000FF), 0.5)]),
        )

        kept = Narrowing(colors=[QColor("red"), QColor("blue")], scan=scan).shown_rows(2)

        assert kept == [1]


class TestNearest:
    def test_a_picture_with_no_scan_behind_it_cannot_be_answered(self, app: QApplication) -> None:
        assert Narrowing(reference=described(split(upright=True))).shown_rows(4) is None

    def test_the_texture_that_looks_like_it_comes_first(self, app: QApplication) -> None:
        scan = pictured(3, row0=split(upright=True), row1=split(upright=False))

        kept = Narrowing(reference=described(split(upright=False)), scan=scan).shown_rows(3)

        assert kept is not None
        assert kept[0] == 1

    def test_a_texture_the_scan_read_nothing_of_is_no_answer(self, app: QApplication) -> None:
        scan = pictured(3, row1=split(upright=True))

        kept = Narrowing(reference=described(split(upright=True)), scan=scan).shown_rows(3)

        assert kept == [1]

    def test_only_the_nearest_of_them_are_shown(self, app: QApplication) -> None:
        count = SHORTLIST + 10
        scan = pictured(count, **{f"row{row}": split(upright=True) for row in range(count)})

        kept = Narrowing(reference=described(split(upright=True)), scan=scan).shown_rows(count)

        assert kept is not None
        assert len(kept) == SHORTLIST

    def test_a_texture_laid_out_like_it_in_another_colour_is_still_ranked(self, app: QApplication) -> None:
        """The colour penalty settles ties; it does not put a layout out of the running"""

        scan = pictured(2, row0=split(upright=False), row1=split(upright=True, tinted=True))

        kept = Narrowing(reference=described(split(upright=True)), scan=scan).shown_rows(2)

        assert kept is not None
        assert kept[0] == 1

    def test_a_picture_is_asked_instead_of_the_colours_rather_than_inside_them(self, app: QApplication) -> None:
        scan = Scan(
            colors=scanned(
                2,
                row0=Signature(colors=[(to_lab(0xFF0000), 1.0)]),
                row1=Signature(colors=[(to_lab(0x0000FF), 1.0)]),
            ).colors,
            likeness=pictured(2, row0=split(upright=True), row1=split(upright=True)).likeness,
        )

        narrowing = Narrowing(
            colors=[QColor("red")],
            reference=described(split(upright=True)),
            scan=scan,
        )

        # the blue row holds none of the colour asked for, and is kept anyway
        assert narrowing.shown_rows(2) == [0, 1]

    def test_the_simple_textures_are_still_left_out_of_the_ranking(self, app: QApplication) -> None:
        scan = Scan(
            colors=scanned(2, row0=Signature(flat=True)).colors,
            likeness=pictured(2, row0=split(upright=True), row1=split(upright=True)).likeness,
        )

        narrowing = Narrowing(
            reference=described(split(upright=True)),
            simple_hidden=True,
            scan=scan,
        )

        assert narrowing.shown_rows(2) == [1]
