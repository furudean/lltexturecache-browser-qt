"""The scrim a window puts up while something is being dragged over it"""

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication, QWidget

from lltexturecache_browser_qt.dropzone import DropZone


class TestDropZone:
    def test_a_zone_starts_out_of_the_way(self, app: QApplication) -> None:
        assert DropZone().isHidden() is True

    def test_a_zone_never_takes_the_pointer(self, app: QApplication) -> None:
        assert DropZone().testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) is True

    def test_an_offer_puts_the_zone_up_where_it_was_asked_for(self, holder: QWidget) -> None:
        zone = DropZone(holder)

        zone.offer("Drop a cache here", QRect(0, 0, 100, 50))

        assert zone.isHidden() is False
        assert zone.geometry() == QRect(0, 0, 100, 50)

    def test_the_message_offered_is_the_one_kept(self, holder: QWidget) -> None:
        zone = DropZone(holder)
        zone.offer("Drop a cache here", QRect(0, 0, 100, 50))

        assert zone._message == "Drop a cache here"

    def test_withdrawing_takes_the_zone_back_down(self, holder: QWidget) -> None:
        zone = DropZone(holder)
        zone.offer("Drop a cache here", QRect(0, 0, 100, 50))
        zone.withdraw()

        assert zone.isHidden() is True

    def test_a_second_offer_moves_the_zone_rather_than_stacking_one(self, holder: QWidget) -> None:
        zone = DropZone(holder)
        zone.offer("first", QRect(0, 0, 100, 50))
        zone.offer("second", QRect(10, 10, 20, 20))

        assert zone.geometry() == QRect(10, 10, 20, 20)
        assert zone._message == "second"
