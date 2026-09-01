"""What the grid decodes next, and in what order"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QObject
from PySide6.QtGui import QColor, QPixmap, QPixmapCache
from PySide6.QtWidgets import QApplication
from texture_courier import Texture

from lltexturecache_browser_qt.grid.queue import (
    AHEAD_PRIORITY,
    CELL_PRIORITY,
    DECODES_IN_FLIGHT,
    DecodeQueue,
)
from tests import fakes

type Started = list[tuple[str, int]]


@pytest.fixture
def started() -> Started:
    return []


@pytest.fixture
def queue(app: QApplication, started: Started) -> Iterator[DecodeQueue]:
    QPixmapCache.clear()

    owner = QObject()

    def start(texture: Texture, priority: int) -> None:
        started.append((texture.uuid, priority))

    built = DecodeQueue(owner, start=start)

    yield built

    built.shutdown()


def cached(uuid: str) -> None:
    pixmap = QPixmap(4, 4)
    pixmap.fill(QColor("red"))

    QPixmapCache.insert(uuid, pixmap)


class TestWanted:
    def test_a_texture_nothing_has_yet_is_wanted(self, queue: DecodeQueue) -> None:
        assert queue.wanted(fakes.texture(uuid="one")) is True

    def test_an_incomplete_texture_is_never_decoded(self, queue: DecodeQueue) -> None:
        assert queue.wanted(fakes.texture(uuid="one", complete=False)) is False

    def test_a_texture_already_in_hand_is_not_wanted(self, queue: DecodeQueue) -> None:
        cached("one")

        assert queue.wanted(fakes.texture(uuid="one")) is False

    def test_a_texture_already_out_is_not_asked_for_again(self, queue: DecodeQueue) -> None:
        queue.request(fakes.texture(uuid="one"))

        assert queue.wanted(fakes.texture(uuid="one")) is False

    def test_a_texture_that_would_not_decode_is_not_asked_for_again(self, queue: DecodeQueue) -> None:
        queue.request(fakes.texture(uuid="one"))
        queue.landed("one", decoded=False)

        assert queue.wanted(fakes.texture(uuid="one")) is False


class TestEnqueue:
    def test_a_texture_is_queued_once(self, queue: DecodeQueue) -> None:
        texture = fakes.texture(uuid="one")

        assert queue.enqueue(texture, CELL_PRIORITY) is True
        assert queue.enqueue(texture, CELL_PRIORITY) is False

    def test_a_more_urgent_ask_moves_a_queued_texture_up(self, queue: DecodeQueue) -> None:
        texture = fakes.texture(uuid="one")

        queue.enqueue(texture, AHEAD_PRIORITY)

        assert queue.enqueue(texture, CELL_PRIORITY) is True

    def test_a_less_urgent_ask_leaves_a_queued_texture_where_it_is(self, queue: DecodeQueue) -> None:
        texture = fakes.texture(uuid="one")

        queue.enqueue(texture, CELL_PRIORITY)

        assert queue.enqueue(texture, AHEAD_PRIORITY) is False

    def test_a_texture_already_in_hand_is_never_queued(self, queue: DecodeQueue) -> None:
        cached("one")

        assert queue.enqueue(fakes.texture(uuid="one"), CELL_PRIORITY) is False


class TestPump:
    def test_a_request_starts_a_decode(self, queue: DecodeQueue, started: Started) -> None:
        queue.request(fakes.texture(uuid="one"))

        assert started == [("one", CELL_PRIORITY)]

    def test_no_more_than_the_limit_is_out_at_once(self, queue: DecodeQueue, started: Started) -> None:
        for texture in fakes.textures(DECODES_IN_FLIGHT + 5):
            queue.enqueue(texture, CELL_PRIORITY)

        queue.pump()

        assert len(started) == DECODES_IN_FLIGHT

    def test_a_landing_decode_makes_room_for_the_next(self, queue: DecodeQueue, started: Started) -> None:
        for texture in fakes.textures(DECODES_IN_FLIGHT + 1):
            queue.enqueue(texture, CELL_PRIORITY)

        queue.pump()

        landed = started[0][0]

        queue.landed(landed, decoded=True)
        queue.pump()

        assert len(started) == DECODES_IN_FLIGHT + 1

    def test_the_queue_drains_from_the_end(self, queue: DecodeQueue, started: Started) -> None:
        for texture in fakes.textures(3):
            queue.enqueue(texture, CELL_PRIORITY)

        queue.pump()

        assert [uuid for uuid, _ in started] == ["texture-2", "texture-1", "texture-0"]

    def test_a_cleared_queue_starts_nothing(self, queue: DecodeQueue, started: Started) -> None:
        queue.enqueue(fakes.texture(uuid="one"), CELL_PRIORITY)
        queue.clear()
        queue.pump()

        assert started == []


class TestRefill:
    def test_what_is_on_screen_outranks_the_band_around_it(self, queue: DecodeQueue, started: Started) -> None:
        textures = fakes.textures(5)

        queue.refill(textures, {"texture-2", "texture-3"})

        priorities = dict(started)

        assert priorities["texture-2"] == CELL_PRIORITY
        assert priorities["texture-3"] == CELL_PRIORITY
        assert priorities["texture-0"] == AHEAD_PRIORITY

    def test_what_is_already_in_hand_is_left_out(self, queue: DecodeQueue, started: Started) -> None:
        cached("texture-0")

        queue.refill(fakes.textures(5), set())

        assert "texture-0" not in [uuid for uuid, _ in started]

    def test_refilling_drops_what_was_waiting(self, queue: DecodeQueue, started: Started) -> None:
        # the grid has scrolled away from wherever the old queue was asked at
        queue.enqueue(fakes.texture(uuid="stale"), AHEAD_PRIORITY)
        queue.refill(fakes.textures(2), set())

        assert "stale" not in [uuid for uuid, _ in started]


class TestLanded:
    def test_an_ordinary_decode_is_kept(self, queue: DecodeQueue) -> None:
        queue.request(fakes.texture(uuid="one"))

        assert queue.landed("one", decoded=True) is True

    def test_a_decode_that_failed_is_not_kept(self, queue: DecodeQueue) -> None:
        queue.request(fakes.texture(uuid="one"))

        assert queue.landed("one", decoded=False) is False

    def test_a_decode_that_set_out_under_the_old_checkerboard_is_thrown_away(self, queue: DecodeQueue) -> None:
        queue.request(fakes.texture(uuid="one"))
        queue.restyle()

        assert queue.landed("one", decoded=True) is False

    def test_a_decode_that_set_out_afterwards_is_kept(self, queue: DecodeQueue) -> None:
        queue.restyle()
        queue.request(fakes.texture(uuid="one"))

        assert queue.landed("one", decoded=True) is True

    def test_a_texture_thrown_away_once_is_asked_for_again(self, queue: DecodeQueue) -> None:
        queue.request(fakes.texture(uuid="one"))
        queue.restyle()
        queue.landed("one", decoded=True)

        assert queue.wanted(fakes.texture(uuid="one")) is True


class TestReads:
    def test_everything_reads_through_the_one_lock(self, queue: DecodeQueue) -> None:
        assert queue.reads is queue.reads

    def test_the_lock_starts_free(self, queue: DecodeQueue) -> None:
        assert queue.reads.acquire(blocking=False) is True

        queue.reads.release()
