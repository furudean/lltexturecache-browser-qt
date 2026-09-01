"""The small adjustments labels are put through before they go in a form"""

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from lltexturecache_browser_qt.widgets import (
    bold,
    copyable,
    dim,
    height_for_width,
    linked,
    wrapped,
)


class TestAdjustments:
    def test_every_adjustment_hands_the_label_back(self, app: object) -> None:
        label = QLabel("text")

        assert dim(label) is label
        assert bold(label) is label
        assert wrapped(label) is label
        assert linked(label) is label
        assert copyable(label) is label

    def test_a_dimmed_label_is_painted_as_a_placeholder(self, app: object) -> None:
        assert dim(QLabel()).foregroundRole() == QPalette.ColorRole.PlaceholderText

    def test_a_bold_label_is_bold(self, app: object) -> None:
        assert bold(QLabel()).font().bold() is True

    def test_bolding_leaves_the_rest_of_the_font_alone(self, app: object) -> None:
        label = QLabel()
        before = label.font().pointSizeF()

        assert bold(label).font().pointSizeF() == before

    def test_a_wrapped_label_wraps_and_asks_for_the_room(self, app: object) -> None:
        label = wrapped(QLabel("a good deal of text"))

        assert label.wordWrap() is True
        assert label.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
        assert label.sizePolicy().hasHeightForWidth() is True

    def test_height_for_width_works_on_any_widget(self, app: object) -> None:
        widget = height_for_width(QWidget())

        assert widget.sizePolicy().hasHeightForWidth() is True

    def test_a_linked_label_opens_its_links_outside_the_app(self, app: object) -> None:
        assert linked(QLabel('<a href="https://example.invalid">link</a>')).openExternalLinks() is True

    def test_a_copyable_label_can_be_selected_but_not_edited(self, app: object) -> None:
        from PySide6.QtCore import Qt

        flags = copyable(QLabel("text")).textInteractionFlags()

        assert flags & Qt.TextInteractionFlag.TextSelectableByMouse
        assert not flags & Qt.TextInteractionFlag.TextEditable
