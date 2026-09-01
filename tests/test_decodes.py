"""The bigger decodes the panes ask for"""

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.grid.decodes import FULL_CACHE, FullDecodes, PreviewDecodes
from tests import fakes


def image(width: int = 8, height: int = 8) -> QImage:
    built = QImage(width, height, QImage.Format.Format_RGB32)
    built.fill(QColor("red"))

    return built


class TestFullDecodes:
    def test_nothing_is_ready_to_begin_with(self, app: QApplication) -> None:
        assert FullDecodes().ready("one") is None

    def test_a_texture_nothing_has_yet_is_worth_decoding(self, app: QApplication) -> None:
        assert FullDecodes().wanted(fakes.texture(uuid="one")) is True

    def test_an_incomplete_texture_is_never_decoded(self, app: QApplication) -> None:
        assert FullDecodes().wanted(fakes.texture(uuid="one", complete=False)) is False

    def test_a_decode_already_out_is_not_started_again(self, app: QApplication) -> None:
        store = FullDecodes()
        texture = fakes.texture(uuid="one")

        store.wanted(texture)

        assert store.wanted(texture) is False

    def test_a_landed_decode_is_handed_back(self, app: QApplication) -> None:
        store = FullDecodes()

        assert store.landed("one", image(), QSize(64, 64)) is True

        ready = store.ready("one")

        assert ready is not None
        assert ready[1] == QSize(64, 64)

    def test_a_landed_decode_frees_the_texture_to_be_asked_for_again(self, app: QApplication) -> None:
        store = FullDecodes()
        texture = fakes.texture(uuid="one")

        store.wanted(texture)
        store.landed("one", image(), QSize(64, 64))

        assert store.wanted(texture) is True

    def test_only_the_most_recent_decodes_are_kept(self, app: QApplication) -> None:
        store = FullDecodes()

        for index in range(FULL_CACHE + 3):
            store.landed(f"texture-{index}", image(), QSize(64, 64))

        assert store.ready("texture-0") is None
        assert store.ready(f"texture-{FULL_CACHE + 2}") is not None

    def test_the_store_never_grows_past_its_limit(self, app: QApplication) -> None:
        store = FullDecodes()

        for index in range(FULL_CACHE * 3):
            store.landed(f"texture-{index}", image(), QSize(64, 64))

        kept = sum(1 for index in range(FULL_CACHE * 3) if store.ready(f"texture-{index}") is not None)

        assert kept == FULL_CACHE

    def test_a_texture_that_would_not_decode_keeps_a_placeholder(self, app: QApplication) -> None:
        store = FullDecodes()
        store.landed("one", QImage(), QSize())

        ready = store.ready("one")

        # cached either way, or every reselect would set the same doomed
        # decode going again
        assert ready is not None
        assert ready[0].isNull() is False

    def test_clearing_lets_everything_go(self, app: QApplication) -> None:
        store = FullDecodes()
        store.landed("one", image(), QSize(64, 64))
        store.clear()

        assert store.ready("one") is None


class TestPreviewDecodes:
    def test_nothing_is_ready_to_begin_with(self, app: QApplication) -> None:
        assert PreviewDecodes().now_showing(fakes.texture(uuid="one")) is None

    def test_a_texture_nothing_has_yet_is_worth_decoding(self, app: QApplication) -> None:
        assert PreviewDecodes().wanted(fakes.texture(uuid="one")) is True

    def test_an_incomplete_texture_is_never_decoded(self, app: QApplication) -> None:
        assert PreviewDecodes().wanted(fakes.texture(uuid="one", complete=False)) is False

    def test_a_decode_already_out_is_not_started_again(self, app: QApplication) -> None:
        store = PreviewDecodes()
        texture = fakes.texture(uuid="one")

        store.wanted(texture)

        assert store.wanted(texture) is False

    def test_the_texture_asked_for_takes_its_decode(self, app: QApplication) -> None:
        store = PreviewDecodes()
        texture = fakes.texture(uuid="one")

        store.now_showing(texture)

        assert store.landed("one", image(), QSize(64, 64)) is True
        assert store.now_showing(texture) is not None

    def test_a_decode_the_selection_has_walked_past_is_dropped(self, app: QApplication) -> None:
        store = PreviewDecodes()

        store.now_showing(fakes.texture(uuid="one"))
        store.now_showing(fakes.texture(uuid="two"))

        assert store.landed("one", image(), QSize(64, 64)) is False

    def test_only_the_one_texture_is_kept(self, app: QApplication) -> None:
        store = PreviewDecodes()

        first = fakes.texture(uuid="one")

        store.now_showing(first)
        store.landed("one", image(), QSize(64, 64))

        second = fakes.texture(uuid="two")

        store.now_showing(second)
        store.landed("two", image(), QSize(32, 32))

        assert store.now_showing(first) is None

    def test_a_texture_that_would_not_decode_is_held_that_way(self, app: QApplication) -> None:
        store = PreviewDecodes()
        texture = fakes.texture(uuid="one")

        store.now_showing(texture)
        store.landed("one", QImage(), QSize())

        ready = store.now_showing(texture)

        assert ready is not None
        assert ready[0].isNull()

    def test_clearing_lets_everything_go(self, app: QApplication) -> None:
        store = PreviewDecodes()
        texture = fakes.texture(uuid="one")

        store.now_showing(texture)
        store.landed("one", image(), QSize(64, 64))
        store.clear()

        assert store.now_showing(texture) is None
