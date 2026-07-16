import numpy as np
import importlib.util
from pathlib import Path
import sys

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.camera.diagnostics import summarize_capture_visibility
from scanner_app.camera.models import SynchronizedFramePacket


def test_diagnostic_reports_visible_color_and_color_alignment() -> None:
    color = np.full((4, 4, 3), 80, dtype=np.uint8)
    depth = np.full((4, 4), 250, dtype=np.uint16)

    result = summarize_capture_visibility(
        color,
        "color",
        depth,
        depth_scale_mm=1.0,
        min_depth_m=0.20,
        max_depth_m=0.30,
    )

    assert result.color_visible is True
    assert result.alignment_target == "color"
    assert result.depth_valid_ratio == 1.0


def test_diagnostic_reports_black_color_and_invalid_depth() -> None:
    result = summarize_capture_visibility(
        np.zeros((2, 2, 3), dtype=np.uint8),
        "depth",
        np.zeros((2, 2), dtype=np.uint16),
        depth_scale_mm=1.0,
        min_depth_m=0.20,
        max_depth_m=0.30,
    )

    assert result.color_visible is False
    assert result.depth_valid_ratio == 0.0


def test_diagnostic_script_defaults_to_depth_to_color_alignment() -> None:
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(
        "capture_diagnostic", scripts_dir / "16_capture_diagnostic.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    args = module.build_argument_parser().parse_args(["--headless", "--max-frames", "1"])
    packet = SynchronizedFramePacket(
        color_bgr=np.full((2, 2, 3), 50, dtype=np.uint8),
        depth_raw=np.full((2, 2), 250, dtype=np.uint16),
        depth_scale_mm=1.0,
        depth_timestamp_us=1,
        color_timestamp_us=1,
        imu_samples=(),
        sequence=0,
    )

    payload = module.diagnostic_payload(packet, args)

    assert args.alignment_target == "color"
    assert payload["color_visible"] is True
    assert payload["alignment_target"] == "color"
