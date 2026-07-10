import numpy as np
import pytest

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.camera.models import CameraIntrinsics
from scanner_app.processing.depth_pipeline import ProcessedDepth
from scanner_app.processing.object_roi import estimate_object_roi


def test_object_roi_centers_on_median_central_depth_with_synthetic_override() -> None:
    depth = np.zeros((10, 10), dtype=np.float32)
    depth[4:6, 4:6] = 0.30
    processed = ProcessedDepth(depth, depth > 0, 0.04, 0.30)
    intrinsics = CameraIntrinsics(100.0, 100.0, 4.5, 4.5, 10, 10)

    roi = estimate_object_roi(
        processed,
        intrinsics,
        extent_m=0.35,
        min_valid_pixels=4,
    )

    np.testing.assert_allclose(roi.center_camera_m, [0.0, 0.0, 0.30], atol=0.002)
    np.testing.assert_allclose(roi.max_bound - roi.min_bound, [0.35] * 3)


def test_object_roi_default_rejects_fewer_than_20_valid_central_pixels() -> None:
    depth = np.zeros((10, 10), dtype=np.float32)
    depth[4:6, 4:6] = 0.30
    processed = ProcessedDepth(depth, depth > 0, 0.04, 0.30)
    intrinsics = CameraIntrinsics(100.0, 100.0, 4.5, 4.5, 10, 10)

    with pytest.raises(ValueError, match="20 valid central depth pixels"):
        estimate_object_roi(processed, intrinsics)
