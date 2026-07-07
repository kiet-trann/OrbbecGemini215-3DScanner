import importlib.util
from pathlib import Path
import sys
import unittest

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()


def load_merge_script_module():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = project_root / "scripts" / "05_merge_pointcloud.py"
    spec = importlib.util.spec_from_file_location("merge_pointcloud", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MergePointCloudScriptTests(unittest.TestCase):
    def test_build_output_path_uses_ply_directory_and_timestamp(self) -> None:
        module = load_merge_script_module()

        path = module.build_output_path(now=module.datetime(2026, 7, 6, 12, 34, 56))

        self.assertEqual(path.name, "merged_cloud_20260706_123456.ply")
        self.assertEqual(path.parent.name, "ply")
        self.assertEqual(path.parent.parent.name, "outputs")

    def test_format_merge_status_reports_tracking_counts_and_points(self) -> None:
        module = load_merge_script_module()

        status = module.format_merge_status(
            frame_count=12,
            elapsed_seconds=3.0,
            tracked_frames=8,
            skipped_frames=4,
            marker_frames=9,
            no_marker_frames=2,
            empty_cloud_frames=1,
            rejected_count=6,
            merged_points=12345,
        )

        self.assertEqual(
            status,
            "Merge frames: 12 | 4.0 FPS | tracked=8 | skipped=4 | markers=9 | "
            "no_marker=2 | empty_cloud=1 | rejected=6 | merged_points=12345",
        )

    def test_parser_accepts_target_tracked_frames(self) -> None:
        module = load_merge_script_module()

        args = module.build_argument_parser().parse_args(["--target-tracked-frames", "50"])

        self.assertEqual(args.target_tracked_frames, 50)

    def test_parser_accepts_voxel_size_m(self) -> None:
        module = load_merge_script_module()

        args = module.build_argument_parser().parse_args(["--voxel-size-m", "0.003"])

        self.assertEqual(args.voxel_size_m, 0.003)

    def test_parser_accepts_capture_seconds_and_tracked_frame_stride(self) -> None:
        module = load_merge_script_module()

        args = module.build_argument_parser().parse_args(
            ["--capture-seconds", "30", "--tracked-frame-stride", "3"]
        )

        self.assertEqual(args.capture_seconds, 30.0)
        self.assertEqual(args.tracked_frame_stride, 3)

    def test_parser_accepts_preview(self) -> None:
        module = load_merge_script_module()

        args = module.build_argument_parser().parse_args(["--preview"])

        self.assertTrue(args.preview)

    def test_parser_accepts_marker_relative_roi_bounds(self) -> None:
        module = load_merge_script_module()

        args = module.build_argument_parser().parse_args(
            [
                "--roi-min-x",
                "-0.20",
                "--roi-max-x",
                "0.02",
                "--roi-min-y",
                "-0.12",
                "--roi-max-y",
                "0.10",
                "--roi-min-z",
                "0.01",
                "--roi-max-z",
                "0.12",
            ]
        )

        self.assertEqual(args.roi_min_x, -0.20)
        self.assertEqual(args.roi_max_x, 0.02)
        self.assertEqual(args.roi_min_y, -0.12)
        self.assertEqual(args.roi_max_y, 0.10)
        self.assertEqual(args.roi_min_z, 0.01)
        self.assertEqual(args.roi_max_z, 0.12)

    def test_build_roi_bounds_uses_unbounded_axes_when_values_are_missing(self) -> None:
        module = load_merge_script_module()
        args = module.build_argument_parser().parse_args(["--roi-max-x", "0.0"])

        min_bound, max_bound = module.build_roi_bounds(args)

        self.assertEqual(min_bound.tolist(), [-float("inf"), -float("inf"), -float("inf")])
        self.assertEqual(max_bound.tolist(), [0.0, float("inf"), float("inf")])

    def test_validate_roi_bounds_rejects_inverted_finite_axis(self) -> None:
        module = load_merge_script_module()
        args = module.build_argument_parser().parse_args(["--roi-min-x", "0.10", "--roi-max-x", "0.0"])
        min_bound, max_bound = module.build_roi_bounds(args)

        with self.assertRaisesRegex(ValueError, "ROI min x must be smaller than ROI max x"):
            module.validate_roi_bounds(min_bound, max_bound)

    def test_format_preview_overlay_reports_marker_and_merge_state(self) -> None:
        module = load_merge_script_module()

        overlay = module.format_preview_overlay(
            elapsed_seconds=12.3,
            capture_seconds=30.0,
            marker_count=1,
            rejected_count=4,
            tracked_frames=7,
            skipped_frames=2,
            merged_points=123456,
        )

        self.assertEqual(
            overlay,
            "12.3/30.0s | markers=1 rejected=4 | merged=7 skipped=2 | points=123456",
        )

    def test_should_stop_capture_when_target_tracked_frames_is_reached(self) -> None:
        module = load_merge_script_module()

        self.assertTrue(
            module.should_stop_capture(
                frame_count=120,
                tracked_frames=50,
                max_frames=0,
                target_tracked_frames=50,
                elapsed_seconds=5.0,
                capture_seconds=0.0,
            )
        )
        self.assertFalse(
            module.should_stop_capture(
                frame_count=120,
                tracked_frames=49,
                max_frames=0,
                target_tracked_frames=50,
                elapsed_seconds=5.0,
                capture_seconds=0.0,
            )
        )

    def test_should_stop_capture_when_max_frames_is_reached_without_target(self) -> None:
        module = load_merge_script_module()

        self.assertTrue(
            module.should_stop_capture(
                frame_count=120,
                tracked_frames=3,
                max_frames=120,
                target_tracked_frames=0,
                elapsed_seconds=5.0,
                capture_seconds=0.0,
            )
        )

    def test_should_stop_capture_when_capture_seconds_is_reached(self) -> None:
        module = load_merge_script_module()

        self.assertTrue(
            module.should_stop_capture(
                frame_count=10,
                tracked_frames=2,
                max_frames=0,
                target_tracked_frames=0,
                elapsed_seconds=30.0,
                capture_seconds=30.0,
            )
        )
        self.assertFalse(
            module.should_stop_capture(
                frame_count=10,
                tracked_frames=2,
                max_frames=0,
                target_tracked_frames=0,
                elapsed_seconds=29.9,
                capture_seconds=30.0,
            )
        )

    def test_should_merge_tracked_frame_uses_one_based_stride(self) -> None:
        module = load_merge_script_module()

        self.assertTrue(module.should_merge_tracked_frame(marker_frame_count=1, stride=3))
        self.assertFalse(module.should_merge_tracked_frame(marker_frame_count=2, stride=3))
        self.assertFalse(module.should_merge_tracked_frame(marker_frame_count=3, stride=3))
        self.assertTrue(module.should_merge_tracked_frame(marker_frame_count=4, stride=3))

    def test_resolve_effective_max_frames_ignores_default_when_timed_capture_is_used(self) -> None:
        module = load_merge_script_module()

        self.assertEqual(
            module.resolve_effective_max_frames(
                max_frames=120,
                capture_seconds=30.0,
                max_frames_supplied=False,
            ),
            0,
        )
        self.assertEqual(
            module.resolve_effective_max_frames(
                max_frames=500,
                capture_seconds=30.0,
                max_frames_supplied=True,
            ),
            500,
        )


if __name__ == "__main__":
    unittest.main()
