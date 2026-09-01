"""The about window"""

from PySide6.QtWidgets import QApplication, QWidget

from lltexturecache_browser_qt import APP_DISPLAY_NAME, __version__
from lltexturecache_browser_qt.about import HOMEPAGE, SUMMARY, AboutDialog, app_icon, icon_label, title_label


class TestIcon:
    def test_an_icon_is_found_even_when_the_app_was_not_packaged_with_one(self, app: QApplication) -> None:
        assert not app_icon().isNull()

    def test_the_icon_label_carries_a_picture(self, holder: QWidget) -> None:
        assert not icon_label(holder).pixmap().isNull()


class TestTitle:
    def test_the_title_names_the_app(self, holder: QWidget) -> None:
        assert title_label(holder).text() == APP_DISPLAY_NAME

    def test_the_title_is_set_larger_than_the_body(self, holder: QWidget) -> None:
        label = title_label(holder)

        assert label.font().pointSizeF() > holder.font().pointSizeF()
        assert label.font().bold() is True


class TestDialog:
    def test_the_window_is_titled_for_the_app(self, app: QApplication) -> None:
        assert APP_DISPLAY_NAME in AboutDialog().windowTitle()

    def test_the_version_and_summary_are_shown(self, app: QApplication) -> None:
        from PySide6.QtWidgets import QLabel

        dialog = AboutDialog()
        text = " ".join(label.text() for label in dialog.findChildren(QLabel))

        assert __version__ in text
        assert SUMMARY in text

    def test_the_homepage_is_offered_as_a_link(self, app: QApplication) -> None:
        from PySide6.QtWidgets import QLabel

        dialog = AboutDialog()

        assert any(HOMEPAGE in label.text() for label in dialog.findChildren(QLabel))

    def test_the_window_is_not_resizable(self, app: QApplication) -> None:
        dialog = AboutDialog()

        assert dialog.minimumWidth() == dialog.maximumWidth()
        assert dialog.isSizeGripEnabled() is False
