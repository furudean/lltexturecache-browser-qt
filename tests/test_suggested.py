"""The caches the app finds on the machine without being told where to look"""

from pathlib import Path

import pytest

from lltexturecache_browser_qt.cache import suggested as module
from lltexturecache_browser_qt.cache.suggested import paths, resolve


@pytest.fixture(autouse=True)
def cleared() -> None:
    module._paths = []


class TestResolve:
    def test_what_is_found_is_handed_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        found = [Path("/caches/one"), Path("/caches/two")]

        monkeypatch.setattr(module, "list_texture_caches", lambda: found)

        assert resolve() == found

    def test_nothing_installed_resolves_to_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def missing() -> list[Path]:
            raise FileNotFoundError

        monkeypatch.setattr(module, "list_texture_caches", missing)

        assert resolve() == []

    def test_a_directory_we_cannot_read_resolves_to_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def refused() -> list[Path]:
            raise PermissionError

        monkeypatch.setattr(module, "list_texture_caches", refused)

        assert resolve() == []

    def test_a_failed_resolve_clears_what_was_found_before(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(module, "list_texture_caches", lambda: [Path("/caches/one")])
        resolve()

        def missing() -> list[Path]:
            raise FileNotFoundError

        monkeypatch.setattr(module, "list_texture_caches", missing)

        assert resolve() == []
        assert paths() == []


class TestPaths:
    def test_nothing_has_been_looked_for_yet(self) -> None:
        assert paths() == []

    def test_what_was_found_is_kept(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(module, "list_texture_caches", lambda: [Path("/caches/one")])
        resolve()

        assert paths() == [Path("/caches/one")]

    def test_the_list_handed_out_is_a_copy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(module, "list_texture_caches", lambda: [Path("/caches/one")])
        resolve()

        paths().clear()

        assert paths() == [Path("/caches/one")]
