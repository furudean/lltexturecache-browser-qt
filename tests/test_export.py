"""Writing textures out in the formats the app offers"""

import os
from dataclasses import FrozenInstanceError
from pathlib import Path
from threading import Lock

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication
from texture_courier import TextureCacheError

from lltexturecache_browser_qt.export import (
    DEFAULT_FORMAT,
    FORMATS,
    ExportJob,
    encodable,
    export_path,
    export_texture,
)
from tests import fakes

PNG = next(fmt for fmt in FORMATS if fmt.encoder == "PNG")
TIFF = next(fmt for fmt in FORMATS if fmt.encoder == "TIFF")
JP2 = next(fmt for fmt in FORMATS if fmt.encoder is None)


@pytest.fixture
def reads() -> Lock:
    return Lock()


class TestFormats:
    def test_the_original_is_offered_first(self) -> None:
        assert FORMATS[0] is DEFAULT_FORMAT
        assert DEFAULT_FORMAT.encoder is None

    def test_every_format_has_a_label_and_a_suffix(self) -> None:
        assert all(fmt.label and fmt.suffix for fmt in FORMATS)

    def test_the_suffixes_are_distinct(self) -> None:
        assert len({fmt.suffix for fmt in FORMATS}) == len(FORMATS)

    def test_a_format_cannot_be_edited_after_it_is_built(self) -> None:
        with pytest.raises(FrozenInstanceError):
            DEFAULT_FORMAT.suffix = "gif"  # type: ignore[misc]


class TestExportPath:
    def test_a_file_is_named_for_its_texture_and_format(self, tmp_path: Path) -> None:
        assert export_path(tmp_path, "abc", PNG) == tmp_path / "abc.png"

    def test_each_format_writes_to_its_own_name(self, tmp_path: Path) -> None:
        paths = {export_path(tmp_path, "abc", fmt) for fmt in FORMATS}

        assert len(paths) == len(FORMATS)


class TestEncodable:
    def test_png_widens_a_mode_it_cannot_write(self) -> None:
        assert encodable(Image.new("CMYK", (2, 2)), PNG).mode == "RGBA"

    def test_png_leaves_a_mode_it_can_write_alone(self) -> None:
        image = Image.new("RGBA", (2, 2))

        assert encodable(image, PNG) is image

    def test_tiff_takes_any_mode_as_it_stands(self) -> None:
        image = Image.new("CMYK", (2, 2))

        assert encodable(image, TIFF) is image


class TestExportTexture:
    def test_the_original_is_written_through_untouched(self, tmp_path: Path, reads: Lock) -> None:
        path = export_texture(fakes.texture(), tmp_path, JP2, reads)

        assert path.read_bytes() == fakes.PAYLOAD

    def test_the_written_file_is_stamped_with_the_texture_time(self, tmp_path: Path, reads: Lock) -> None:
        texture = fakes.texture()
        path = export_texture(texture, tmp_path, JP2, reads)

        assert os.stat(path).st_mtime == pytest.approx(texture.time.timestamp(), abs=1.0)

    def test_a_texture_that_cannot_be_read_raises(self, tmp_path: Path, reads: Lock) -> None:
        with pytest.raises(TextureCacheError):
            export_texture(fakes.texture(unreadable=True), tmp_path, JP2, reads)

    def test_the_read_lock_is_taken_and_given_back(self, tmp_path: Path, reads: Lock) -> None:
        export_texture(fakes.texture(), tmp_path, JP2, reads)

        assert reads.acquire(blocking=False) is True

        reads.release()

    def test_the_lock_is_given_back_even_when_the_read_fails(self, tmp_path: Path, reads: Lock) -> None:
        with pytest.raises(TextureCacheError):
            export_texture(fakes.texture(unreadable=True), tmp_path, JP2, reads)

        assert reads.acquire(blocking=False) is True

        reads.release()


class TestExportJob:
    def test_a_job_with_nothing_in_it_finishes_at_once(self, app: QApplication, tmp_path: Path, reads: Lock) -> None:
        finished: list[tuple[int, int, bool]] = []

        job = ExportJob([], tmp_path, JP2, reads)
        job.finished.connect(lambda *args: finished.append(args))
        job.start()

        assert finished == [(0, 0, False)]

    def test_a_job_reports_what_it_wrote(self, app: QApplication, tmp_path: Path, reads: Lock) -> None:
        finished: list[tuple[int, int, bool]] = []

        textures = fakes.textures(4)

        job = ExportJob(textures, tmp_path, JP2, reads)
        job.finished.connect(lambda *args: finished.append(args))
        job.start()

        while not finished:
            app.processEvents()

        assert finished == [(4, 0, False)]
        assert len(job.written_paths) == 4
        assert job.failed == []

    def test_a_job_reports_what_it_could_not_write(self, app: QApplication, tmp_path: Path, reads: Lock) -> None:
        finished: list[tuple[int, int, bool]] = []

        textures = [fakes.texture(uuid="good"), fakes.texture(uuid="bad", unreadable=True)]

        job = ExportJob(textures, tmp_path, JP2, reads)
        job.finished.connect(lambda *args: finished.append(args))
        job.start()

        while not finished:
            app.processEvents()

        assert finished == [(1, 1, False)]
        assert [uuid for uuid, _ in job.failed] == ["bad"]

    def test_progress_is_reported_as_each_one_is_done(self, app: QApplication, tmp_path: Path, reads: Lock) -> None:
        seen: list[int] = []
        finished: list[object] = []

        textures = fakes.textures(3)

        job = ExportJob(textures, tmp_path, JP2, reads)
        job.progressed.connect(seen.append)
        job.finished.connect(lambda *args: finished.append(args))
        job.start()

        while not finished:
            app.processEvents()

        assert seen == [1, 2, 3]

    def test_a_cancelled_job_says_so(self, app: QApplication, tmp_path: Path, reads: Lock) -> None:
        finished: list[tuple[int, int, bool]] = []

        job = ExportJob([], tmp_path, JP2, reads)
        job.finished.connect(lambda *args: finished.append(args))
        job.cancel()
        job.start()

        assert finished[0][2] is True

    def test_a_job_finishes_only_once(self, app: QApplication, tmp_path: Path, reads: Lock) -> None:
        finished: list[object] = []

        job = ExportJob([], tmp_path, JP2, reads)
        job.finished.connect(lambda *args: finished.append(args))
        job.start()
        job.finish()

        assert len(finished) == 1
