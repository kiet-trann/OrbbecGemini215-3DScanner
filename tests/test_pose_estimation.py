import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.tracking.aruco import MarkerPose
from scanner_app.tracking.pose import (
    CameraPoseSample,
    camera_pose_from_detection,
    camera_to_world_from_marker_pose,
    load_marker_world_transforms,
    save_pose_samples_jsonl,
    transform_from_rvec_tvec,
)


class PoseEstimationTests(unittest.TestCase):
    def test_transform_from_rvec_tvec_builds_marker_to_camera_matrix(self) -> None:
        transform = transform_from_rvec_tvec(
            np.zeros((3, 1), dtype=np.float64),
            np.array([[1.0], [2.0], [3.0]], dtype=np.float64),
        )

        np.testing.assert_array_equal(
            transform,
            np.array(
                [
                    [1.0, 0.0, 0.0, 1.0],
                    [0.0, 1.0, 0.0, 2.0],
                    [0.0, 0.0, 1.0, 3.0],
                    [0.0, 0.0, 0.0, 1.0],
                ],
                dtype=np.float64,
            ),
        )

    def test_camera_to_world_from_marker_pose_inverts_marker_to_camera(self) -> None:
        marker_to_camera = np.eye(4, dtype=np.float64)
        marker_to_camera[:3, 3] = [0.0, 0.0, 1.0]

        camera_to_world = camera_to_world_from_marker_pose(marker_to_camera)

        np.testing.assert_array_equal(camera_to_world[:3, 3], np.array([0.0, 0.0, -1.0]))

    def test_camera_pose_from_detection_uses_marker_world_transform(self) -> None:
        detection = MarkerPose(
            marker_id=4,
            corners=np.zeros((4, 2), dtype=np.float32),
            rvec=np.zeros((3, 1), dtype=np.float64),
            tvec=np.array([[0.0], [0.0], [0.5]], dtype=np.float64),
        )
        marker_to_world = np.eye(4, dtype=np.float64)
        marker_to_world[:3, 3] = [1.0, 2.0, 3.0]

        sample = camera_pose_from_detection(
            detection,
            timestamp_ms=1234.5,
            marker_to_world=marker_to_world,
        )

        self.assertEqual(sample.marker_id, 4)
        self.assertEqual(sample.timestamp_ms, 1234.5)
        np.testing.assert_array_almost_equal(sample.camera_to_world[:3, 3], [1.0, 2.0, 2.5])

    def test_camera_pose_from_detection_requires_pose_vectors(self) -> None:
        detection = MarkerPose(marker_id=1, corners=np.zeros((4, 2), dtype=np.float32))

        with self.assertRaisesRegex(ValueError, "does not contain pose vectors"):
            camera_pose_from_detection(detection, timestamp_ms=1.0)

    def test_load_marker_world_transforms_reads_layout_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "layout.json"
            path.write_text(
                json.dumps(
                    {
                        "markers": [
                            {
                                "id": 2,
                                "world_transform": [
                                    [1, 0, 0, 0.1],
                                    [0, 1, 0, 0.2],
                                    [0, 0, 1, 0.3],
                                    [0, 0, 0, 1],
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            transforms = load_marker_world_transforms(path)

            self.assertIn(2, transforms)
            np.testing.assert_array_equal(transforms[2][:3, 3], np.array([0.1, 0.2, 0.3]))

    def test_save_pose_samples_jsonl_writes_one_pose_per_line(self) -> None:
        sample = CameraPoseSample(
            timestamp_ms=10.5,
            marker_id=3,
            camera_to_world=np.eye(4, dtype=np.float64),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "poses.jsonl"

            save_pose_samples_jsonl(output_path, [sample])

            payload = json.loads(output_path.read_text(encoding="utf-8").strip())
            self.assertEqual(payload["timestamp_ms"], 10.5)
            self.assertEqual(payload["marker_id"], 3)
            self.assertEqual(payload["camera_to_world"][3], [0.0, 0.0, 0.0, 1.0])


if __name__ == "__main__":
    unittest.main()
