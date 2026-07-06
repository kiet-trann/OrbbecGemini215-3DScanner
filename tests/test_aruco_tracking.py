import unittest

import cv2
import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.camera.orbbec_capture import CameraIntrinsics
from scanner_app.tracking.aruco import camera_matrix_from_intrinsics, detect_markers


def make_marker_scene(marker_id: int = 0, marker_size_px: int = 160) -> np.ndarray:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker = cv2.aruco.generateImageMarker(dictionary, marker_id, marker_size_px)
    scene = np.full((320, 320), 255, dtype=np.uint8)
    offset = (scene.shape[0] - marker_size_px) // 2
    scene[offset : offset + marker_size_px, offset : offset + marker_size_px] = marker
    return cv2.cvtColor(scene, cv2.COLOR_GRAY2BGR)


class ArucoTrackingTests(unittest.TestCase):
    def test_camera_matrix_from_intrinsics_uses_depth_calibration_values(self) -> None:
        intrinsics = CameraIntrinsics(fx=500.0, fy=501.0, cx=160.0, cy=120.0, width=320, height=240)

        camera_matrix = camera_matrix_from_intrinsics(intrinsics)

        np.testing.assert_array_equal(
            camera_matrix,
            np.array(
                [
                    [500.0, 0.0, 160.0],
                    [0.0, 501.0, 120.0],
                    [0.0, 0.0, 1.0],
                ],
                dtype=np.float64,
            ),
        )

    def test_detect_markers_returns_marker_id_corners_and_pose(self) -> None:
        image = make_marker_scene(marker_id=7)
        intrinsics = CameraIntrinsics(fx=500.0, fy=500.0, cx=160.0, cy=160.0, width=320, height=320)

        detections = detect_markers(
            image,
            intrinsics=intrinsics,
            marker_size_m=0.06,
            dictionary_name="DICT_4X4_50",
        )

        self.assertEqual(len(detections), 1)
        detection = detections[0]
        self.assertEqual(detection.marker_id, 7)
        self.assertEqual(detection.corners.shape, (4, 2))
        self.assertEqual(detection.rvec.shape, (3, 1))
        self.assertEqual(detection.tvec.shape, (3, 1))
        self.assertGreater(float(detection.tvec[2, 0]), 0.0)

    def test_detect_markers_returns_empty_list_when_no_marker_is_visible(self) -> None:
        image = np.full((320, 320, 3), 255, dtype=np.uint8)
        intrinsics = CameraIntrinsics(fx=500.0, fy=500.0, cx=160.0, cy=160.0, width=320, height=320)

        detections = detect_markers(image, intrinsics=intrinsics, marker_size_m=0.06)

        self.assertEqual(detections, [])

    def test_detect_markers_rejects_unknown_dictionary_names(self) -> None:
        image = make_marker_scene()

        with self.assertRaisesRegex(ValueError, "Unknown ArUco dictionary"):
            detect_markers(image, dictionary_name="DICT_DOES_NOT_EXIST")


if __name__ == "__main__":
    unittest.main()
