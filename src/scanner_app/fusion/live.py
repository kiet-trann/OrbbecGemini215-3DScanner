"""Live TSDF facade for markerless accepted keyframes."""

from collections.abc import Callable, Iterable
from typing import Any

import numpy as np

from scanner_app.camera.models import CameraIntrinsics, RgbdFrame


DEFAULT_ROI_HALF_EXTENT_M = 0.175
MAX_OBJECT_ROI_AXIS_M = 0.35


class LiveFusionEngine:
    def __init__(
        self,
        *,
        intrinsics: CameraIntrinsics | None = None,
        volume_factory: Callable[[], Any] | None = None,
        roi_min: np.ndarray | None = None,
        roi_max: np.ndarray | None = None,
        voxel_length_m: float = 0.0015,
        sdf_trunc_m: float = 0.006,
        min_depth_m: float = 0.20,
        max_depth_m: float = 0.30,
        integration_width: int | None = None,
        integration_height: int | None = None,
    ) -> None:
        self.intrinsics = intrinsics
        self.voxel_length_m = float(voxel_length_m)
        self.sdf_trunc_m = float(sdf_trunc_m)
        self.min_depth_m = float(min_depth_m)
        self.max_depth_m = float(max_depth_m)
        self.integration_width = integration_width
        self.integration_height = integration_height
        self.roi_min = np.asarray(
            roi_min if roi_min is not None else [-DEFAULT_ROI_HALF_EXTENT_M] * 3,
            dtype=np.float64,
        )
        self.roi_max = np.asarray(
            roi_max if roi_max is not None else [DEFAULT_ROI_HALF_EXTENT_M] * 3,
            dtype=np.float64,
        )
        _validate_roi(self.roi_min, self.roi_max)
        self.volume_factory = volume_factory or self._build_open3d_volume
        self._volume = self.volume_factory()

    def integrate(self, keyframe: Any) -> int:
        return int(self._volume.integrate_keyframe(keyframe, self.roi_min, self.roi_max))

    def extract_preview(self) -> Any:
        return self._volume.extract_triangle_mesh()

    def rebuild(self, keyframes: Iterable[Any]) -> Any:
        self._volume = self.volume_factory()
        for keyframe in keyframes:
            self.integrate(keyframe)
        return self.extract_preview()

    def _build_open3d_volume(self) -> "Open3dTsdfAdapter":
        if self.intrinsics is None:
            raise ValueError("intrinsics are required when using the Open3D TSDF volume.")
        return Open3dTsdfAdapter(
            intrinsics=self.intrinsics,
            voxel_length_m=self.voxel_length_m,
            sdf_trunc_m=self.sdf_trunc_m,
            min_depth_m=self.min_depth_m,
            max_depth_m=self.max_depth_m,
            integration_width=self.integration_width,
            integration_height=self.integration_height,
        )


class Open3dTsdfAdapter:
    def __init__(
        self,
        *,
        intrinsics: CameraIntrinsics,
        voxel_length_m: float,
        sdf_trunc_m: float,
        min_depth_m: float,
        max_depth_m: float,
        integration_width: int | None,
        integration_height: int | None,
    ) -> None:
        from scanner_app.fusion.tsdf import create_tsdf_volume

        self.intrinsics = intrinsics
        self.min_depth_m = float(min_depth_m)
        self.max_depth_m = float(max_depth_m)
        self.integration_width = integration_width
        self.integration_height = integration_height
        self._volume = create_tsdf_volume(
            voxel_length_m=voxel_length_m,
            sdf_trunc_m=sdf_trunc_m,
            with_color=True,
        )

    def integrate_keyframe(
        self,
        keyframe: Any,
        roi_min: np.ndarray,
        roi_max: np.ndarray,
    ) -> int:
        from scanner_app.fusion.tsdf import integrate_rgbd_frame

        frame, intrinsics = self._frame_and_intrinsics(keyframe)
        return integrate_rgbd_frame(
            self._volume,
            frame=frame,
            intrinsics=intrinsics,
            camera_to_world=keyframe.camera_to_world,
            min_depth_m=self.min_depth_m,
            max_depth_m=self.max_depth_m,
            min_bound=roi_min,
            max_bound=roi_max,
        )

    def extract_triangle_mesh(self) -> Any:
        mesh = self._volume.extract_triangle_mesh()
        mesh.compute_vertex_normals()
        return mesh

    def _frame_and_intrinsics(self, keyframe: Any) -> tuple[RgbdFrame, CameraIntrinsics]:
        packet = keyframe.packet
        if self.integration_width is None or self.integration_height is None:
            return (
                RgbdFrame(
                    color=packet.color_bgr,
                    depth=packet.depth_raw,
                    depth_scale=packet.depth_scale_mm,
                    timestamp_ms=packet.depth_timestamp_us / 1000.0,
                ),
                self.intrinsics,
            )

        import cv2
        from scanner_app.tracking.rgbd_odometry import scale_tracking_intrinsics

        width = int(self.integration_width)
        height = int(self.integration_height)
        color = cv2.resize(packet.color_bgr, (width, height), interpolation=cv2.INTER_NEAREST)
        depth = cv2.resize(packet.depth_raw, (width, height), interpolation=cv2.INTER_NEAREST)
        return (
            RgbdFrame(
                color=color,
                depth=depth,
                depth_scale=packet.depth_scale_mm,
                timestamp_ms=packet.depth_timestamp_us / 1000.0,
            ),
            scale_tracking_intrinsics(self.intrinsics, width, height),
        )


def _validate_roi(roi_min: np.ndarray, roi_max: np.ndarray) -> None:
    if roi_min.shape != (3,) or roi_max.shape != (3,):
        raise ValueError("ROI bounds must be 3D vectors.")
    if np.any(roi_min >= roi_max):
        raise ValueError("ROI min must be smaller than ROI max on every axis.")
    extent = roi_max - roi_min
    if np.any(extent > MAX_OBJECT_ROI_AXIS_M + 1e-12):
        raise ValueError("Object ROI cannot exceed 0.35 m on any axis.")
