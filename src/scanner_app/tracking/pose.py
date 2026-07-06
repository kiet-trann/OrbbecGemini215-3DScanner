"""Camera pose estimation from marker observations."""

from dataclasses import dataclass
import json
from pathlib import Path

import cv2
import numpy as np

from scanner_app.tracking.aruco import MarkerPose


@dataclass(frozen=True)
class CameraPoseSample:
    timestamp_ms: float
    marker_id: int
    camera_to_world: np.ndarray

    def to_json_dict(self) -> dict:
        return {
            "timestamp_ms": self.timestamp_ms,
            "marker_id": self.marker_id,
            "camera_to_world": self.camera_to_world.tolist(),
        }


def invert_transform(transform: np.ndarray) -> np.ndarray:
    rotation = transform[:3, :3]
    translation = transform[:3, 3]

    inverse = np.eye(4, dtype=np.float64)
    inverse[:3, :3] = rotation.T
    inverse[:3, 3] = -rotation.T @ translation
    return inverse


def transform_from_rvec_tvec(rvec: np.ndarray, tvec: np.ndarray) -> np.ndarray:
    rotation, _ = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64).reshape(3, 1))
    translation = np.asarray(tvec, dtype=np.float64).reshape(3)

    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = rotation
    transform[:3, 3] = translation
    return transform


def camera_to_world_from_marker_pose(
    marker_to_camera: np.ndarray,
    *,
    marker_to_world: np.ndarray | None = None,
) -> np.ndarray:
    marker_world = np.eye(4, dtype=np.float64) if marker_to_world is None else marker_to_world
    camera_to_marker = invert_transform(marker_to_camera)
    return marker_world @ camera_to_marker


def camera_pose_from_detection(
    detection: MarkerPose,
    *,
    timestamp_ms: float,
    marker_to_world: np.ndarray | None = None,
) -> CameraPoseSample:
    if detection.rvec is None or detection.tvec is None:
        raise ValueError(f"Marker {detection.marker_id} does not contain pose vectors.")

    marker_to_camera = transform_from_rvec_tvec(detection.rvec, detection.tvec)
    camera_to_world = camera_to_world_from_marker_pose(
        marker_to_camera,
        marker_to_world=marker_to_world,
    )
    return CameraPoseSample(
        timestamp_ms=timestamp_ms,
        marker_id=detection.marker_id,
        camera_to_world=camera_to_world,
    )


def load_marker_world_transforms(path: str | Path) -> dict[int, np.ndarray]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    transforms: dict[int, np.ndarray] = {}
    for marker in payload.get("markers", []):
        marker_id = int(marker["id"])
        transform = np.asarray(marker["world_transform"], dtype=np.float64)
        if transform.shape != (4, 4):
            raise ValueError(f"Marker {marker_id} world_transform must be a 4x4 matrix.")
        transforms[marker_id] = transform
    return transforms


def save_pose_samples_jsonl(path: str | Path, samples: list[CameraPoseSample]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as file:
        for sample in samples:
            file.write(json.dumps(sample.to_json_dict(), separators=(",", ":")))
            file.write("\n")
