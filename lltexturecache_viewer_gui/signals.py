import signal
import socket

from PySide6.QtCore import QObject, QSocketNotifier, Signal


class SignalWatcher(QObject):
    received = Signal(int)

    def __init__(self, *signums: int, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._reader, self._writer = socket.socketpair()
        self._reader.setblocking(False)
        self._writer.setblocking(False)

        signal.set_wakeup_fd(self._writer.fileno())

        for signum in signums:
            signal.signal(signum, lambda *_: None)

        self._notifier = QSocketNotifier(self._reader.fileno(), QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self.wake)

    def wake(self) -> None:
        for signum in self._reader.recv(4096):
            self.received.emit(signum)
