"""Running an export against a window"""

from pathlib import Path
from threading import Lock

import pytest
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QWidget

from lltexturecache_browser_qt.app import exporting as module
from lltexturecache_browser_qt.app.exporting import ExportRun, export_summary, show_written
from lltexturecache_browser_qt.cache.export import FORMATS
from tests import fakes

JP2 = FORMATS[0]


class TestExportSummary:
    def test_a_finished_export_says_what_it_wrote(self, tmp_path: Path) -> None:
        summary = export_summary(tmp_path, 4, 0, cancelled=False)

        assert summary.startswith("Exported 4")
        assert str(tmp_path) in summary

    def test_a_cancelled_export_says_so(self, tmp_path: Path) -> None:
        assert export_summary(tmp_path, 2, 0, cancelled=True).startswith("Cancelled export of 2")

    def test_what_could_not_be_written_is_counted(self, tmp_path: Path) -> None:
        assert "3 could not be written" in export_summary(tmp_path, 1, 3, cancelled=False)

    def test_an_export_that_lost_nothing_says_nothing_about_it(self, tmp_path: Path) -> None:
        assert "could not be written" not in export_summary(tmp_path, 4, 0, cancelled=False)


class TestShowWritten:
    def test_files_a_file_manager_can_pick_out_are_picked_out(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opened: list[object] = []

        monkeypatch.setattr(module, "reveal", lambda paths: True)
        monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(opened.append))

        show_written(tmp_path, [tmp_path / "one.jp2"])

        assert opened == []

    def test_otherwise_the_directory_they_went_to_is_opened(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opened: list[str] = []

        monkeypatch.setattr(module, "reveal", lambda paths: False)
        monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda url: opened.append(url.toLocalFile())))

        show_written(tmp_path, [tmp_path / "one.jp2"])

        assert opened == [str(tmp_path)]


class TestExportRun:
    def test_a_run_reports_when_it_lands(
        self, app: QApplication, holder: QWidget, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(module, "show_written", lambda out_dir, paths: None)

        reported: list[str] = []

        run = ExportRun(holder, fakes.textures(3), tmp_path, JP2, Lock(), done=reported.append)
        run.start()

        while not reported:
            app.processEvents()

        assert reported[0].startswith("Exported 3")

    def test_a_run_writes_the_textures_it_was_given(
        self, app: QApplication, holder: QWidget, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(module, "show_written", lambda out_dir, paths: None)

        reported: list[str] = []

        run = ExportRun(holder, fakes.textures(3), tmp_path, JP2, Lock(), done=reported.append)
        run.start()

        while not reported:
            app.processEvents()

        assert len(list(tmp_path.iterdir())) == 3

    def test_an_empty_run_lands_at_once(
        self, app: QApplication, holder: QWidget, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        shown: list[object] = []

        monkeypatch.setattr(module, "show_written", lambda out_dir, paths: shown.append(paths))

        reported: list[str] = []

        run = ExportRun(holder, [], tmp_path, JP2, Lock(), done=reported.append)
        run.start()

        assert reported[0].startswith("Exported 0")
        # nothing was written, so there is nothing to put in front of anyone
        assert shown == []

    def test_what_could_not_be_read_is_counted_rather_than_stopping_the_run(
        self, app: QApplication, holder: QWidget, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(module, "show_written", lambda out_dir, paths: None)

        reported: list[str] = []

        textures = [fakes.texture(uuid="good"), fakes.texture(uuid="bad", unreadable=True)]

        run = ExportRun(holder, textures, tmp_path, JP2, Lock(), done=reported.append)
        run.start()

        while not reported:
            app.processEvents()

        assert "1 could not be written" in reported[0]
