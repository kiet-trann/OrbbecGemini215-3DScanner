"""Background worker for the temporary live TSDF mesh preview."""

from queue import Empty, Full, Queue
from threading import Thread
from typing import Any, Callable

from scanner_app.session.controller import put_latest


_SENTINEL = object()


class LivePreviewWorker:
    """Owns preview fusion so mesh extraction never blocks pose tracking."""

    def __init__(self, fusion_factory: Callable[..., Any], fusion_kwargs: dict[str, Any]) -> None:
        self._fusion_factory = fusion_factory
        self._fusion_kwargs = dict(fusion_kwargs)
        self._pending: Queue[Any] = Queue(maxsize=1)
        self._completed: Queue[Any] = Queue(maxsize=1)
        self._worker: Thread | None = None
        self._error: BaseException | None = None
        self._closed = False

    def start(self) -> None:
        if self._worker is not None:
            raise RuntimeError("Live preview worker is already started.")
        self._worker = Thread(target=self._run, name="live-preview", daemon=True)
        self._worker.start()

    def submit(self, keyframe: Any) -> None:
        self._raise_worker_error()
        if self._closed:
            raise RuntimeError("Live preview worker is closed.")
        put_latest(self._pending, keyframe)

    def drain_latest_mesh(self) -> Any | None:
        self._raise_worker_error()
        latest = None
        while True:
            try:
                latest = self._completed.get_nowait()
            except Empty:
                return latest

    def close(self) -> None:
        if self._closed:
            self._raise_worker_error()
            return
        self._closed = True
        if self._worker is not None:
            while True:
                try:
                    self._pending.put(_SENTINEL, timeout=0.1)
                    break
                except Full:
                    try:
                        self._pending.get_nowait()
                    except Empty:
                        pass
            self._worker.join()
        self._raise_worker_error()

    def _run(self) -> None:
        try:
            fusion = self._fusion_factory(**self._fusion_kwargs)
            while True:
                keyframe = self._pending.get()
                if keyframe is _SENTINEL:
                    return
                fusion.integrate(keyframe)
                put_latest(self._completed, fusion.extract_preview())
        except BaseException as error:
            self._error = error

    def _raise_worker_error(self) -> None:
        if self._error is not None:
            raise RuntimeError("Live preview worker failed.") from self._error
