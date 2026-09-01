"""Shared fixtures

Qt objects cannot be built without an application behind them, and widgets need
a platform plugin on top of that. The offscreen plugin is the one that asks for
no display, so it is chosen before PySide6 is first imported anywhere.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication, QWidget


@pytest.fixture(scope="session")
def app() -> Iterator[QApplication]:
    """The one application every Qt object in the suite is built under"""

    existing = QApplication.instance()

    if isinstance(existing, QApplication):
        yield existing
        return

    application = QApplication([])

    yield application

    application.quit()


@pytest.fixture
def settings(app: QApplication, tmp_path: Path) -> Iterator[None]:
    """Point QSettings at a file of this test's own

    Settings are otherwise read and written wherever the machine running the
    suite keeps them, which would pick up whatever the developer's own copy of
    the app has stored and write the test's values back over it.
    """

    QCoreApplication.setOrganizationName("lltexturecache-browser-qt-tests")
    QCoreApplication.setApplicationName("suite")

    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(tmp_path),
    )

    QSettings().clear()

    yield

    QSettings().clear()


@pytest.fixture
def moment() -> datetime:
    """A fixed time, so nothing under test is read against the clock"""

    return datetime(2024, 3, 7, 15, 4, 5, tzinfo=UTC)


@pytest.fixture
def holder(app: QApplication) -> Iterator[QWidget]:
    """A parent widget something under test can be built under

    A Qt child goes when its parent does, and a parent built inline in a test
    goes as soon as the line it was built on ends.
    """

    widget = QWidget()

    yield widget

    widget.close()


@pytest.fixture
def quiet_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the colour scan off the global pool

    A model starts one the moment it is built, and it reads through a real
    cache. Nothing under test here depends on what it would find, and a scan
    left running reorders rows out from under whatever is asserting on them.
    """

    from PySide6.QtCore import QThreadPool

    from lltexturecache_browser_qt import model as module

    class Idle:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def cancel(self) -> None:
            pass

    monkeypatch.setattr(module, "ColorScan", Idle)
    monkeypatch.setattr(QThreadPool.globalInstance(), "start", lambda *args, **kwargs: None)
