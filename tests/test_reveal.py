"""Revealing exported files in the platform's file manager"""

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import lltexturecache_browser_qt.reveal as reveal_module
from lltexturecache_browser_qt.reveal import (
    REVEAL_LIMIT,
    quoted,
    ran,
    reveal,
    reveal_darwin,
    reveal_linux,
)


class TestQuoted:
    def test_plain_text_is_wrapped_in_quotes(self) -> None:
        assert quoted("hello") == '"hello"'

    def test_a_quote_is_escaped(self) -> None:
        assert quoted('say "hi"') == '"say \\"hi\\""'

    def test_a_backslash_is_escaped_before_the_quotes_are_added(self) -> None:
        assert quoted("a\\b") == '"a\\\\b"'

    def test_a_backslash_before_a_quote_does_not_escape_it(self) -> None:
        # the backslash doubles first, so the quote's own escape stands alone
        assert quoted('a\\"') == '"a\\\\\\""'


def recorder[T](into: list[T]) -> Callable[[T], bool]:
    """Stands in for a call that reports success, keeping what it was handed"""

    def record(handed: T) -> bool:
        into.append(handed)

        return True

    return record


class TestRan:
    def test_a_command_that_succeeds_reports_success(self) -> None:
        assert ran(["true"]) is True

    def test_a_nonzero_exit_reports_failure(self) -> None:
        assert ran(["false"]) is False

    def test_a_missing_command_reports_failure_rather_than_raising(self) -> None:
        assert ran(["lltexturecache-browser-qt-no-such-command"]) is False

    def test_a_command_that_hangs_is_given_up_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def timeout(*args: Any, **kwargs: Any) -> None:
            raise subprocess.TimeoutExpired(cmd="sleep", timeout=1)

        monkeypatch.setattr(subprocess, "run", timeout)

        assert ran(["sleep", "60"]) is False

    def test_the_command_is_run_without_a_shell(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, Any] = {}

        class Finished:
            returncode = 0

        def record(command: list[str], **kwargs: Any) -> Finished:
            seen["command"] = command
            seen["kwargs"] = kwargs

            return Finished()

        monkeypatch.setattr(subprocess, "run", record)

        ran(["echo", "; rm -rf /"])

        assert seen["command"] == ["echo", "; rm -rf /"]
        assert "shell" not in seen["kwargs"]


class TestRevealGuards:
    def test_nothing_to_reveal_is_refused(self) -> None:
        assert reveal([]) is False

    def test_more_than_the_limit_is_refused(self, tmp_path: Path) -> None:
        paths = [tmp_path / f"{index}.png" for index in range(REVEAL_LIMIT + 1)]

        assert reveal(paths) is False

    def test_a_relative_path_is_refused(self) -> None:
        assert reveal([Path("relative.png")]) is False

    def test_the_limit_itself_is_allowed_through(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        reached: list[list[Path]] = []

        for name in ("reveal_darwin", "reveal_windows", "reveal_linux"):
            monkeypatch.setattr(reveal_module, name, recorder(reached))

        paths = [tmp_path / f"{index}.png" for index in range(REVEAL_LIMIT)]

        assert reveal(paths) is True
        assert reached == [paths]


class TestPlatformCommands:
    def test_darwin_names_every_file_to_the_finder(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[list[str]] = []

        monkeypatch.setattr(reveal_module, "ran", recorder(seen))

        reveal_darwin([tmp_path / "one.png", tmp_path / "two.png"])

        script = seen[0][2]

        assert "one.png" in script
        assert "two.png" in script
        assert script.startswith('tell application "Finder" to reveal')

    def test_linux_hands_the_file_manager_uris(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[list[str]] = []

        monkeypatch.setattr(reveal_module, "ran", recorder(seen))

        reveal_linux([tmp_path / "one.png"])

        assert seen[0][0] == "gdbus"
        assert "file://" in seen[0][-2]
