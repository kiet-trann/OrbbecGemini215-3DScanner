from threading import Lock

from scanner_app.camera.models import ImuSample


class ImuBuffer:
    def __init__(self) -> None:
        self._samples: list[ImuSample] = []
        self._lock = Lock()

    def push(self, sample: ImuSample) -> None:
        with self._lock:
            self._samples.append(sample)
            self._samples.sort(key=lambda item: item.timestamp_us)

    def pop_through(self, timestamp_us: int) -> tuple[ImuSample, ...]:
        with self._lock:
            split = 0
            while split < len(self._samples) and self._samples[split].timestamp_us <= timestamp_us:
                split += 1
            ready = tuple(self._samples[:split])
            del self._samples[:split]
            return ready
