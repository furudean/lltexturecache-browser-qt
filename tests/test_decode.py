"""Turning a jpeg 2000 codestream into pixels anything else can read"""

from dataclasses import FrozenInstanceError
from typing import Any

import imagecodecs
import numpy
import pytest
from texture_courier import TextureCacheError

from lltexturecache_browser_qt.decode import GREYSCALE, RGB, RGBA, Decoded, decode_texture


def stub(decoded: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(imagecodecs, "jpeg2k_decode", lambda codestream: decoded)


class TestDecoded:
    def test_a_row_of_greyscale_is_one_byte_a_pixel(self) -> None:
        assert Decoded(b"", 10, 4, GREYSCALE).stride == 10

    def test_a_row_of_rgb_is_three_bytes_a_pixel(self) -> None:
        assert Decoded(b"", 10, 4, RGB).stride == 30

    def test_a_row_of_rgba_is_four_bytes_a_pixel(self) -> None:
        assert Decoded(b"", 10, 4, RGBA).stride == 40

    def test_a_decoded_texture_cannot_be_edited(self) -> None:
        with pytest.raises(FrozenInstanceError):
            Decoded(b"", 1, 1, RGB).width = 2  # type: ignore[misc]


class TestComponentCounts:
    def test_a_single_component_image_comes_back_greyscale(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub(numpy.zeros((4, 6), dtype="uint8"), monkeypatch)

        decoded = decode_texture(b"")

        assert (decoded.width, decoded.height, decoded.components) == (6, 4, GREYSCALE)
        assert len(decoded.pixels) == 24

    def test_three_components_come_back_as_they_were(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub(numpy.zeros((4, 6, 3), dtype="uint8"), monkeypatch)

        decoded = decode_texture(b"")

        assert decoded.components == RGB
        assert len(decoded.pixels) == 4 * 6 * 3

    def test_four_components_come_back_as_they_were(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub(numpy.zeros((4, 6, 4), dtype="uint8"), monkeypatch)

        assert decode_texture(b"").components == RGBA

    def test_greyscale_with_opacity_is_spread_over_the_colour_channels(self, monkeypatch: pytest.MonkeyPatch) -> None:
        raw = numpy.zeros((1, 2, 2), dtype="uint8")
        raw[0, 0] = [90, 200]
        raw[0, 1] = [10, 255]

        stub(raw, monkeypatch)

        decoded = decode_texture(b"")

        assert decoded.components == RGBA
        assert bytes(decoded.pixels) == bytes([90, 90, 90, 200, 10, 10, 10, 255])

    def test_components_past_the_fourth_are_dropped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # second life tags some material textures with five components
        raw = numpy.zeros((1, 1, 5), dtype="uint8")
        raw[0, 0] = [1, 2, 3, 4, 5]

        stub(raw, monkeypatch)

        decoded = decode_texture(b"")

        assert decoded.components == RGBA
        assert bytes(decoded.pixels) == bytes([1, 2, 3, 4])

    def test_the_rows_of_a_sliced_image_are_gathered_tight(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub(numpy.zeros((3, 5, 6), dtype="uint8"), monkeypatch)

        decoded = decode_texture(b"")

        assert len(decoded.pixels) == 3 * 5 * RGBA
        assert len(decoded.pixels) == decoded.stride * decoded.height


class TestRejections:
    def test_a_codestream_openjpeg_will_not_take_is_named_in_the_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fails(codestream: bytes) -> Any:
            raise imagecodecs.Jpeg2kError("truncated")

        monkeypatch.setattr(imagecodecs, "jpeg2k_decode", fails)

        with pytest.raises(TextureCacheError, match="openjpeg could not decode"):
            decode_texture(b"")

    def test_wider_components_are_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub(numpy.zeros((2, 2, 3), dtype="uint16"), monkeypatch)

        with pytest.raises(TextureCacheError, match="8 bit"):
            decode_texture(b"")

    def test_an_image_with_too_many_axes_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub(numpy.zeros((2, 2, 2, 2), dtype="uint8"), monkeypatch)

        with pytest.raises(TextureCacheError, match="two or three axis"):
            decode_texture(b"")

    def test_an_image_with_no_picture_in_it_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub(numpy.zeros((2, 2, 0), dtype="uint8"), monkeypatch)

        with pytest.raises(TextureCacheError, match="not a picture"):
            decode_texture(b"")


class TestRoundTrip:
    def test_a_real_codestream_decodes_to_the_pixels_it_was_encoded_from(self) -> None:
        pixels = numpy.zeros((8, 8, 3), dtype="uint8")
        pixels[:, :, 0] = 200
        pixels[:4, :, 1] = 100

        codestream = imagecodecs.jpeg2k_encode(pixels, codecformat="J2K", level=0)
        decoded = decode_texture(bytes(codestream))

        assert (decoded.width, decoded.height, decoded.components) == (8, 8, RGB)
        assert decoded.pixels == pixels.tobytes()

    def test_a_truncated_codestream_is_refused(self) -> None:
        pixels = numpy.zeros((8, 8, 3), dtype="uint8")
        codestream = bytes(imagecodecs.jpeg2k_encode(pixels, codecformat="J2K", level=0))

        with pytest.raises(TextureCacheError):
            decode_texture(codestream[: len(codestream) // 2])
