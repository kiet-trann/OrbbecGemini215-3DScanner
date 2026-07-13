from queue import Queue

import numpy as np
import pytest

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.session.controller import ScanSession, put_latest
from scanner_app.session.coverage import ViewCoverage
from scanner_app.session.models import ScanSessionState, ScannerSnapshot


def test_put_latest_drops_stale_item_from_full_queue() -> None:
    queue: Queue[str] = Queue(maxsize=1)
    queue.put("old")

    put_latest(queue, "new")

    assert queue.get_nowait() == "new"


def test_finish_is_allowed_only_from_tracking() -> None:
    session = object.__new__(ScanSession)
    session.state = ScanSessionState.IDLE

    with pytest.raises(RuntimeError, match="TRACKING"):
        session.finish_pass()


def test_finish_transitions_tracking_session_to_finalizing() -> None:
    session = object.__new__(ScanSession)
    session.state = ScanSessionState.TRACKING

    session.finish_pass()

    assert session.state is ScanSessionState.FINALIZING


def test_view_coverage_counts_unique_azimuth_bins() -> None:
    coverage = ViewCoverage(
        object_center=np.zeros(3),
        azimuth_bins=4,
        elevation_bins=1,
    )

    coverage.add_camera_position(np.array([1.0, 0.0, 0.0]))
    coverage.add_camera_position(np.array([0.0, 0.0, 1.0]))
    coverage.add_camera_position(np.array([1.0, 0.0, 0.0]))

    assert coverage.ratio == 0.5
    assert len(coverage.trajectory) == 3


def test_snapshot_defaults_to_idle_without_camera_frame() -> None:
    snapshot = ScannerSnapshot.idle()

    assert snapshot.state is ScanSessionState.IDLE
    assert snapshot.color_bgr is None
    assert snapshot.coverage_ratio == 0.0
