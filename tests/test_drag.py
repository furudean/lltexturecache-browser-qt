"""Files staged on disk so a selection can be dragged out of the window"""

from pathlib import Path
from threading import Lock

import pytest
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt import drag as module
from lltexturecache_browser_qt.drag import DRAG_FORMAT, STAGING_PREFIX, drag_data, staged, staging
from tests import fakes


@pytest.fixture
def out_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(module, "staging", lambda: tmp_path)

    return tmp_path


class TestStaging:
    def test_the_staging_directory_is_made_once(self) -> None:
        assert staging() is staging()

    def test_the_staging_directory_is_named_for_the_app(self) -> None:
        assert staging().name.startswith(STAGING_PREFIX)

    def test_the_staging_directory_exists(self) -> None:
        assert staging().is_dir()


class TestStaged:
    def test_a_file_is_written_for_every_texture(self, out_dir: Path) -> None:
        paths = staged(fakes.textures(2), Lock())

        assert len(paths) == 2
        assert all(path.exists() for path in paths)

    def test_the_files_are_written_in_the_drag_format(self, out_dir: Path) -> None:
        paths = staged(fakes.textures(1), Lock())

        assert paths[0].suffix == f".{DRAG_FORMAT.suffix}"

    def test_a_texture_that_cannot_be_read_is_left_out(self, out_dir: Path) -> None:
        textures = [fakes.texture(uuid="good"), fakes.texture(uuid="bad", unreadable=True)]

        assert [path.stem for path in staged(textures, Lock())] == ["good"]

    def test_nothing_to_stage_writes_nothing(self, out_dir: Path) -> None:
        assert staged([], Lock()) == []


class TestDragData:
    def test_the_staged_files_are_offered_as_urls(self, app: QApplication, tmp_path: Path) -> None:
        paths = [tmp_path / "one.jp2", tmp_path / "two.jp2"]
        data = drag_data(paths)

        assert data.hasUrls()
        assert [url.toLocalFile() for url in data.urls()] == [str(path) for path in paths]

    def test_nothing_staged_offers_no_urls(self, app: QApplication) -> None:
        assert drag_data([]).urls() == []
