"""Shared fixtures

Qt objects cannot be built without an application behind them, and widgets need
a platform plugin on top of that. The offscreen plugin is the one that asks for
no display, so it is chosen before PySide6 is first imported anywhere.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication


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
