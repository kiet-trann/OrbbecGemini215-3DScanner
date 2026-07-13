"""RGB-D odometry adapter for markerless handheld tracking."""

from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np

from scanner_app.camera.models import CameraIntrinsics, SynchronizedFramePacket
from scanner_app.processing.depth_pipeline import ProcessedDepth


@dataclass(frozen=True)
class OdometryEstimate:
    relative_transform: np.ndarray
    fitness: float
    rmse_m: float
    depth_valid_ratio: float


class RgbdOdometryBackend(Protocol):
    def estimate(
        self,
        previous_color_rgb: np.ndarray,
        previous_depth_m: np.ndarray,
        current_color_rgb: np.ndarray,
        current_depth_m: np.ndarray,
        intrinsics: CameraIntrinsics,
        initial_transform: np.ndarray,
    ) -> OdometryEstimate: ...


def scale_tracking_intrinsics(
    source: CameraIntrinsics,
    width: int = 640,
    height: int = 400,
) -> CameraIntrinsics:
    scale_x = float(width) / float(source.width)
    scale_y = float(height) / float(source.height)
    return CameraIntrinsics(
        fx=source.fx * scale_x,
        fy=source.fy * scale_y,
        cx=source.cx * scale_x,
        cy=source.cy * scale_y,
        width=width,
        height=height,
    )


class RgbdOdometryAdapter:
    def __init__(
        self,
        intrinsics: CameraIntrinsics,
        backend: RgbdOdometryBackend | None = None,
        tracking_width: int = 640,
        tracking_height: int = 400,
    ) -> None:
        self.intrinsics = scale_tracking_intrinsics(intrinsics, tracking_width, tracking_height)
        self.backend = backend if backend is not None else Open3dRgbdOdometryBackend()
        self.tracking_width = int(tracking_width)
        self.tracking_height = int(tracking_height)

    def estimate(
        self,
        previous_packet: SynchronizedFramePacket,
        previous_depth: ProcessedDepth,
        current_packet: SynchronizedFramePacket,
        current_depth: ProcessedDepth,
        imu_rotation: np.ndarray,
    ) -> OdometryEstimate:
        initial_transform = np.eye(4, dtype=np.float64)
        initial_transform[:3, :3] = np.asarray(imu_rotation, dtype=np.float64)

        previous_color_rgb = self._resize_color_bgr_to_rgb(previous_packet.color_bgr)
        current_color_rgb = self._resize_color_bgr_to_rgb(current_packet.color_bgr)
        previous_depth_m = self._resize_depth_m(previous_depth.depth_m)
        current_depth_m = self._resize_depth_m(current_depth.depth_m)
        depth_valid_ratio = float(np.mean(current_depth_m > 0.0))

        estimate = self.backend.estimate(
            previous_color_rgb,
            previous_depth_m,
            current_color_rgb,
            current_depth_m,
            self.intrinsics,
            initial_transform,
        )
        return OdometryEstimate(
            relative_transform=estimate.relative_transform,
            fitness=estimate.fitness,
            rmse_m=estimate.rmse_m,
            depth_valid_ratio=depth_valid_ratio,
        )

    def _resize_color_bgr_to_rgb(self, color_bgr: np.ndarray) -> np.ndarray:
        color_rgb = np.asarray(color_bgr)[..., ::-1]
        return cv2.resize(
            color_rgb,
            (self.tracking_width, self.tracking_height),
            interpolation=cv2.INTER_NEAREST,
        )

    def _resize_depth_m(self, depth_m: np.ndarray) -> np.ndarray:
        return cv2.resize(
            np.asarray(depth_m, dtype=np.float32),
            (self.tracking_width, self.tracking_height),
            interpolation=cv2.INTER_NEAREST,
        ).astype(np.float32, copy=False)


class Open3dRgbdOdometryBackend:
    def __init__(self) -> None:
        import open3d as o3d

        self._o3d = o3d

    def estimate(
        self,
        previous_color_rgb: np.ndarray,
        previous_depth_m: np.ndarray,
        current_color_rgb: np.ndarray,
        current_depth_m: np.ndarray,
        intrinsics: CameraIntrinsics,
        initial_transform: np.ndarray,
    ) -> OdometryEstimate:
        o3d = self._o3d
        source_rgbd = self._rgbd_image(previous_color_rgb, previous_depth_m)
        target_rgbd = self._rgbd_image(current_color_rgb, current_depth_m)
        camera = self._camera_intrinsic(intrinsics)

        success, transform, _info = o3d.pipelines.odometry.compute_rgbd_odometry(
            source_rgbd,
            target_rgbd,
            camera,
            np.asarray(initial_transform, dtype=np.float64),
            o3d.pipelines.odometry.RGBDOdometryJacobianFromHybridTerm(),
            o3d.pipelines.odometry.OdometryOption(),
        )
        if not success:
            transform = np.asarray(initial_transform, dtype=np.float64)

        source_cloud = o3d.geometry.PointCloud.create_from_rgbd_image(source_rgbd, camera)
        target_cloud = o3d.geometry.PointCloud.create_from_rgbd_image(target_rgbd, camera)
        transform, fitness, rmse_m = self._refine_with_point_to_plane_icp(
            source_cloud,
            target_cloud,
            np.asarray(transform, dtype=np.float64),
        )
        return OdometryEstimate(
            relative_transform=transform,
            fitness=fitness,
            rmse_m=rmse_m,
            depth_valid_ratio=float(np.mean(current_depth_m > 0.0)),
        )

    def _rgbd_image(self, color_rgb: np.ndarray, depth_m: np.ndarray):
        o3d = self._o3d
        color = o3d.geometry.Image(np.ascontiguousarray(color_rgb.astype(np.uint8, copy=False)))
        depth = o3d.geometry.Image(np.ascontiguousarray(depth_m.astype(np.float32, copy=False)))
        return o3d.geometry.RGBDImage.create_from_color_and_depth(
            color,
            depth,
            depth_scale=1.0,
            depth_trunc=3.0,
            convert_rgb_to_intensity=False,
        )

    def _camera_intrinsic(self, intrinsics: CameraIntrinsics):
        return self._o3d.camera.PinholeCameraIntrinsic(
            intrinsics.width,
            intrinsics.height,
            intrinsics.fx,
            intrinsics.fy,
            intrinsics.cx,
            intrinsics.cy,
        )

    def _refine_with_point_to_plane_icp(
        self,
        source_cloud,
        target_cloud,
        initial_transform: np.ndarray,
    ) -> tuple[np.ndarray, float, float]:
        o3d = self._o3d
        transform = initial_transform
        result = None
        for voxel_size, max_correspondence_m, iterations in (
            (0.04, 0.07, 20),
            (0.02, 0.04, 15),
            (0.01, 0.02, 10),
        ):
            source_down = source_cloud.voxel_down_sample(voxel_size)
            target_down = target_cloud.voxel_down_sample(voxel_size)
            source_down.estimate_normals(
                o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 2.0, max_nn=30)
            )
            target_down.estimate_normals(
                o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 2.0, max_nn=30)
            )
            result = o3d.pipelines.registration.registration_icp(
                source_down,
                target_down,
                max_correspondence_m,
                transform,
                o3d.pipelines.registration.TransformationEstimationPointToPlane(),
                o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=iterations),
            )
            transform = result.transformation

        if result is None:
            return transform, 0.0, float("inf")
        return result.transformation, float(result.fitness), float(result.inlier_rmse)
