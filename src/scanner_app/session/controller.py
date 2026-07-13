"""Small live scan session controller helpers."""

from queue import Empty, Full, Queue
from typing import TypeVar

from scanner_app.session.models import ScanSessionState, ScannerSnapshot


T = TypeVar("T")


def put_latest(queue: Queue[T], item: T) -> None:
    try:
        queue.put_nowait(item)
    except Full:
        try:
            queue.get_nowait()
        except Empty:
            pass
        queue.put_nowait(item)


class ScanSession:
    def __init__(self) -> None:
        self.state = ScanSessionState.IDLE
        self._snapshot = ScannerSnapshot.idle()

    def start(self) -> None:
        if self.state not in (ScanSessionState.IDLE, ScanSessionState.PAUSED):
            raise RuntimeError("Session can start only from IDLE or PAUSED.")
        self.state = ScanSessionState.TRACKING

    def pause(self) -> None:
        if self.state is not ScanSessionState.TRACKING:
            raise RuntimeError("Session can pause only from TRACKING.")
        self.state = ScanSessionState.PAUSED

    def finish_pass(self) -> None:
        if self.state is not ScanSessionState.TRACKING:
            raise RuntimeError("Session can finish only from TRACKING.")
        self.state = ScanSessionState.FINALIZING

    def reset(self) -> None:
        self.state = ScanSessionState.IDLE
        self._snapshot = ScannerSnapshot.idle()

    def latest_snapshot(self) -> ScannerSnapshot:
        return self._snapshot

    def close(self) -> None:
        if self.state not in (ScanSessionState.COMPLETE, ScanSessionState.ERROR):
            self.state = ScanSessionState.IDLE
