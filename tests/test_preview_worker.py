from threading import Event
import time

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.fusion.preview_worker import LivePreviewWorker


def wait_until(predicate, timeout_s: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_worker_integrates_keyframe_and_publishes_latest_mesh() -> None:
    class FakeFusion:
        def __init__(self) -> None:
            self.integrated = []

        def integrate(self, keyframe) -> None:
            self.integrated.append(keyframe)

        def extract_preview(self):
            return {"integrated": list(self.integrated)}

    fusion = FakeFusion()
    worker = LivePreviewWorker(lambda **_kwargs: fusion, {})
    worker.start()
    worker.submit("keyframe-1")

    assert wait_until(lambda: worker.drain_latest_mesh() == {"integrated": ["keyframe-1"]})

    worker.close()


def test_worker_drops_stale_pending_keyframes() -> None:
    entered = Event()
    release = Event()

    class BlockingFusion:
        def __init__(self) -> None:
            self.integrated = []

        def integrate(self, keyframe) -> None:
            self.integrated.append(keyframe)
            if keyframe == "first":
                entered.set()
                assert release.wait(1.0)

        def extract_preview(self):
            return {"integrated": list(self.integrated)}

    fusion = BlockingFusion()
    worker = LivePreviewWorker(lambda **_kwargs: fusion, {})
    worker.start()
    worker.submit("first")
    assert entered.wait(1.0)
    worker.submit("stale")
    worker.submit("latest")
    release.set()

    assert wait_until(lambda: fusion.integrated == ["first", "latest"])

    worker.close()
