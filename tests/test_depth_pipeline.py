import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.camera.models import SynchronizedFramePacket
from scanner_app.processing.depth_pipeline import DepthProcessor


def test_depth_processor_applies_metric_range_and_reports_coverage() -> None:
    packet = SynchronizedFramePacket(
        color_bgr=np.zeros((2, 2, 3), dtype=np.uint8),
        depth_raw=np.array([[100, 200], [400, 600]], dtype=np.uint16),
        depth_scale_mm=1.0,
        depth_timestamp_us=1,
        color_timestamp_us=1,
        imu_samples=tuple(),
        sequence=0,
    )

    result = DepthProcessor(min_depth_m=0.15, max_depth_m=0.50).process(packet)

    np.testing.assert_array_equal(
        result.depth_m,
        np.array([[0.0, 0.2], [0.4, 0.0]], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        result.valid_mask,
        np.array([[False, True], [True, False]]),
    )
    assert result.valid_ratio == 0.5
    assert result.median_depth_m == 0.3

