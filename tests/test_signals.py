"""Unix signals delivered onto the Qt event loop"""

import os
import signal

from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.signals import SignalWatcher


class TestSignalWatcher:
    def test_a_signal_reaches_the_event_loop(self, app: QApplication) -> None:
        seen: list[int] = []

        watcher = SignalWatcher(signal.SIGUSR1)
        watcher.received.connect(seen.append)

        os.kill(os.getpid(), signal.SIGUSR1)

        for _ in range(100):
            app.processEvents()

            if seen:
                break

        assert seen == [signal.SIGUSR1]

    def test_a_watched_signal_no_longer_stops_the_process(self, app: QApplication) -> None:
        SignalWatcher(signal.SIGUSR2)

        assert signal.getsignal(signal.SIGUSR2) not in (signal.SIG_DFL, signal.SIG_IGN)

    def test_several_signals_can_be_watched_at_once(self, app: QApplication) -> None:
        watcher = SignalWatcher(signal.SIGUSR1, signal.SIGUSR2)

        assert watcher._notifier.isEnabled() is True
