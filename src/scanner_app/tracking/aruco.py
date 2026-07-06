"""ArUco marker tracking helpers."""

from dataclasses import dataclass

import numpy as np

from scanner_app.camera.orbbec_capture import CameraIntrinsics


@dataclass(frozen=True)
class MarkerPose:
    marker_id: int
    corners: np.ndarray
    rvec: np.ndarray | None = None
    tvec: np.ndarray | None = None


def camera_matrix_from_intrinsics(intrinsics: CameraIntrinsics) -> np.ndarray:
    return np.array(
        [
            [intrinsics.fx, 0.0, intrinsics.cx],
            [0.0, intrinsics.fy, intrinsics.cy],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def detect_markers(
    color_bgr: np.ndarray,
    *,
    intrinsics: CameraIntrinsics | None = None,
    marker_size_m: float | None = None,
    dictionary_name: str = "DICT_4X4_50",
    dist_coeffs: np.ndarray | None = None,
) -> list[MarkerPose]:
    import cv2

    dictionary = _aruco_dictionary(cv2, dictionary_name)
    corners, marker_ids = _detect_aruco_markers(cv2, color_bgr, dictionary)
    if marker_ids is None or len(marker_ids) == 0:
        return []

    rvecs = None
    tvecs = None
    if intrinsics is not None and marker_size_m is not None:
        camera_matrix = camera_matrix_from_intrinsics(intrinsics)
        coefficients = np.zeros((5, 1), dtype=np.float64) if dist_coeffs is None else dist_coeffs
        rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(
            corners,
            float(marker_size_m),
            camera_matrix,
            coefficients,
        )

    detections: list[MarkerPose] = []
    for index, marker_id in enumerate(marker_ids.flatten()):
        rvec = None if rvecs is None else np.asarray(rvecs[index], dtype=np.float64).reshape(3, 1)
        tvec = None if tvecs is None else np.asarray(tvecs[index], dtype=np.float64).reshape(3, 1)
        detections.append(
            MarkerPose(
                marker_id=int(marker_id),
                corners=np.asarray(corners[index], dtype=np.float32).reshape(4, 2),
                rvec=rvec,
                tvec=tvec,
            )
        )
    return detections


def draw_marker_detections(
    color_bgr: np.ndarray,
    detections: list[MarkerPose],
    intrinsics: CameraIntrinsics,
    *,
    marker_size_m: float,
    dist_coeffs: np.ndarray | None = None,
) -> np.ndarray:
    import cv2

    output = color_bgr.copy()
    if not detections:
        return output

    corners = [detection.corners.reshape(1, 4, 2) for detection in detections]
    marker_ids = np.array([[detection.marker_id] for detection in detections], dtype=np.int32)
    cv2.aruco.drawDetectedMarkers(output, corners, marker_ids)

    camera_matrix = camera_matrix_from_intrinsics(intrinsics)
    coefficients = np.zeros((5, 1), dtype=np.float64) if dist_coeffs is None else dist_coeffs
    axis_length = float(marker_size_m) * 0.5
    for detection in detections:
        if detection.rvec is not None and detection.tvec is not None:
            cv2.drawFrameAxes(
                output,
                camera_matrix,
                coefficients,
                detection.rvec,
                detection.tvec,
                axis_length,
            )
    return output


def _aruco_dictionary(cv2, dictionary_name: str):
    dictionary_id = getattr(cv2.aruco, dictionary_name, None)
    if dictionary_id is None:
        raise ValueError(f"Unknown ArUco dictionary: {dictionary_name}")
    return cv2.aruco.getPredefinedDictionary(dictionary_id)


def _detect_aruco_markers(cv2, color_bgr: np.ndarray, dictionary):
    parameters_factory = getattr(cv2.aruco, "DetectorParameters", None)
    parameters = (
        parameters_factory()
        if parameters_factory is not None
        else cv2.aruco.DetectorParameters_create()
    )
    detector_factory = getattr(cv2.aruco, "ArucoDetector", None)
    if detector_factory is not None:
        detector = detector_factory(dictionary, parameters)
        corners, marker_ids, _ = detector.detectMarkers(color_bgr)
        return corners, marker_ids
    corners, marker_ids, _ = cv2.aruco.detectMarkers(color_bgr, dictionary, parameters=parameters)
    return corners, marker_ids
