"""The third party licences the app ships and the dialog that shows them"""

import json
from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from lltexturecache_browser_qt import licences as module
from lltexturecache_browser_qt.licences import Component, LicencesDialog, components, text_view


@pytest.fixture
def packaged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A licence directory of this test's own, in place of the packaged one"""

    (tmp_path / "mit.txt").write_text("MIT licence text")
    (tmp_path / "index.json").write_text(
        json.dumps(
            [
                {
                    "name": "texture-courier",
                    "licence": "MIT",
                    "homepage": "https://example.invalid/courier",
                    "file": "mit.txt",
                }
            ]
        )
    )

    monkeypatch.setattr(module, "LICENCES_PATH", tmp_path)
    monkeypatch.setattr(module, "INDEX_PATH", tmp_path / "index.json")

    components.cache_clear()

    yield tmp_path

    components.cache_clear()


@pytest.fixture
def unpackaged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(module, "LICENCES_PATH", tmp_path)
    monkeypatch.setattr(module, "INDEX_PATH", tmp_path / "index.json")

    components.cache_clear()

    yield

    components.cache_clear()


class TestComponents:
    def test_the_index_is_read_into_components(self, packaged: Path) -> None:
        found = components()

        assert len(found) == 1
        assert found[0].name == "texture-courier"

    def test_a_component_reads_its_own_licence_text(self, packaged: Path) -> None:
        assert components()[0].text() == "MIT licence text"

    def test_the_index_is_read_once(self, packaged: Path) -> None:
        assert components() is components()

    def test_a_build_without_licences_lists_none(self, unpackaged: None) -> None:
        assert components() == []

    def test_a_component_cannot_be_edited(self) -> None:
        component = Component("name", "MIT", "https://example.invalid", "mit.txt")

        with pytest.raises(FrozenInstanceError):
            component.name = "other"  # type: ignore[misc]


class TestTextView:
    def test_licence_text_is_shown_read_only_and_unwrapped(self, holder: QWidget) -> None:
        from PySide6.QtWidgets import QPlainTextEdit

        view = text_view(holder)

        assert view.isReadOnly() is True
        assert view.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap


class TestDialog:
    def test_every_component_is_listed(self, app: QApplication, packaged: Path) -> None:
        dialog = LicencesDialog()

        assert dialog._list.count() == 1
        assert dialog._list.item(0).text() == "texture-courier"

    def test_the_dialog_opens_on_the_first_component(self, app: QApplication, packaged: Path) -> None:
        dialog = LicencesDialog()

        assert dialog._name.text() == "texture-courier"
        assert dialog._licence.text() == "MIT"
        assert "MIT licence text" in dialog._text.toPlainText()

    def test_the_homepage_is_shown_as_a_link(self, app: QApplication, packaged: Path) -> None:
        dialog = LicencesDialog()

        assert "https://example.invalid/courier" in dialog._link.text()
        assert dialog._link.openExternalLinks() is True

    def test_a_build_without_licences_says_so(self, app: QApplication, unpackaged: None) -> None:
        dialog = LicencesDialog()

        assert dialog._list.count() == 0
        assert "without licencing information" in dialog._text.toPlainText()

    def test_selecting_nothing_leaves_the_pane_alone(self, app: QApplication, packaged: Path) -> None:
        dialog = LicencesDialog()
        dialog.show_component(-1)

        assert dialog._name.text() == "texture-courier"
