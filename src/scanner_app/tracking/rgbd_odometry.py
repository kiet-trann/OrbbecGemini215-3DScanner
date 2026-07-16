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


def estimate_rigid_transform_3d(
    source_points: np.ndarray,
    target_points: np.ndarray,
) -> tuple[np.ndarray, float]:
    source = np.asarray(source_points, dtype=np.float64)
    target = np.asarray(target_points, dtype=np.float64)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 3:
        raise ValueError("source_points and target_points must be Nx3 arrays.")
    if source.shape[0] < 3:
        raise ValueError("At least three 3D correspondences are required.")

    source_center = np.mean(source, axis=0)
    target_center = np.mean(target, axis=0)
    source_centered = source - source_center
    target_centered = target - target_center
    covariance = source_centered.T @ target_centered
    u, _s, vt = np.linalg.svd(covariance)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0.0:
        vt[-1, :] *= -1.0
        rotation = vt.T @ u.T
    translation = target_center - rotation @ source_center

    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = rotation
    transform[:3, 3] = translation
    residual = (source @ rotation.T + translation) - target
    rmse = float(np.sqrt(np.mean(np.sum(residual * residual, axis=1))))
    return transform, rmse


class OpenCvRgbdOdometryBackend:
    def __init__(
        self,
        max_features: int = 800,
        min_matches: int = 12,
        ransac_threshold_m: float = 0.01,
    ) -> None:
        self.max_features = int(max_features)
        self.min_matches = int(min_matches)
        self.ransac_threshold_m = float(ransac_threshold_m)
        self._orb = cv2.ORB_create(nfeatures=self.max_features, fastThreshold=7)
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

    def estimate(
        self,
        previous_color_rgb: np.ndarray,
        previous_depth_m: np.ndarray,
        current_color_rgb: np.ndarray,
        current_depth_m: np.ndarray,
        intrinsics: CameraIntrinsics,
        initial_transform: np.ndarray,
    ) -> OdometryEstimate:
        previous_gray = cv2.cvtColor(previous_color_rgb, cv2.COLOR_RGB2GRAY)
        current_gray = cv2.cvtColor(current_color_rgb, cv2.COLOR_RGB2GRAY)
        previous_keypoints, previous_descriptors = self._orb.detectAndCompute(previous_gray, None)
        current_keypoints, current_descriptors = self._orb.detectAndCompute(current_gray, None)
        if previous_descriptors is None or current_descriptors is None:
            return _failed_estimate(initial_transform, current_depth_m)

        matches = sorted(
            self._matcher.match(previous_descriptors, current_descriptors),
            key=lambda match: match.distance,
        )
        source_points, target_points = self._matched_depth_points(
            matches,
            previous_keypoints,
            current_keypoints,
            previous_depth_m,
            current_depth_m,
            intrinsics,
        )
        if len(source_points) < self.min_matches:
            return _failed_estimate(initial_transform, current_depth_m)

        source = np.asarray(source_points, dtype=np.float64)
        target = np.asarray(target_points, dtype=np.float64)
        ok, affine, inliers = cv2.estimateAffine3D(
            source,
            target,
            ransacThreshold=self.ransac_threshold_m,
            confidence=0.99,
        )
        if not ok or affine is None or inliers is None:
            return _failed_estimate(initial_transform, current_depth_m)

        inlier_mask = inliers.reshape(-1).astype(bool)
        minimum_inliers = int(getattr(self, "min_inliers", self.min_matches))
        if int(np.count_nonzero(inlier_mask)) < minimum_inliers:
            return _failed_estimate(initial_transform, current_depth_m)

        transform, rmse_m = estimate_rigid_transform_3d(source[inlier_mask], target[inlier_mask])
        return OdometryEstimate(
            relative_transform=transform,
            fitness=float(np.mean(inlier_mask)),
            rmse_m=rmse_m,
            depth_valid_ratio=float(np.mean(current_depth_m > 0.0)),
        )

    def _matched_depth_points(
        self,
        matches,
        previous_keypoints,
        current_keypoints,
        previous_depth_m: np.ndarray,
        current_depth_m: np.ndarray,
        intrinsics: CameraIntrinsics,
    ) -> tuple[list[np.ndarray], list[np.ndarray]]:
        source_points: list[np.ndarray] = []
        target_points: list[np.ndarray] = []
        for match in matches:
            previous_u, previous_v = previous_keypoints[match.queryIdx].pt
            current_u, current_v = current_keypoints[match.trainIdx].pt
            previous_point = _backproject_depth_pixel(
                previous_depth_m,
                previous_u,
                previous_v,
                intrinsics,
            )
            current_point = _backproject_depth_pixel(
                current_depth_m,
                current_u,
                current_v,
                intrinsics,
            )
            if previous_point is None or current_point is None:
                continue
            source_points.append(previous_point)
            target_points.append(current_point)
        return source_points, target_points


class BackgroundAssistedRgbdOdometryBackend(OpenCvRgbdOdometryBackend):
    """Strict ORB/RANSAC tracking for native RGB with depth aligned to color."""

    def __init__(
        self,
        max_features: int = 1600,
        min_matches: int = 24,
        min_inliers: int = 16,
        ransac_threshold_m: float = 0.008,
    ) -> None:
        super().__init__(
            max_features=max_features,
            min_matches=min_matches,
            ransac_threshold_m=ransac_threshold_m,
        )
        self.min_inliers = int(min_inliers)


def _failed_estimate(initial_transform: np.ndarray, current_depth_m: np.ndarray) -> OdometryEstimate:
    return OdometryEstimate(
        relative_transform=np.asarray(initial_transform, dtype=np.float64).copy(),
        fitness=0.0,
        rmse_m=float("inf"),
        depth_valid_ratio=float(np.mean(current_depth_m > 0.0)),
    )


def _backproject_depth_pixel(
    depth_m: np.ndarray,
    u: float,
    v: float,
    intrinsics: CameraIntrinsics,
) -> np.ndarray | None:
    x = int(round(u))
    y = int(round(v))
    if y < 0 or y >= depth_m.shape[0] or x < 0 or x >= depth_m.shape[1]:
        return None
    z = float(depth_m[y, x])
    if not np.isfinite(z) or z <= 0.0:
        return None
    return np.array(
        [
            (float(u) - intrinsics.cx) * z / intrinsics.fx,
            (float(v) - intrinsics.cy) * z / intrinsics.fy,
            z,
        ],
        dtype=np.float64,
    )


class RgbdOdometryAdapter:
    def __init__(
        self,
        intrinsics: CameraIntrinsics,
        backend: RgbdOdometryBackend | None = None,
        tracking_width: int = 640,
        tracking_height: int = 400,
        min_backend_valid_pixels: int = 1_000,
        enable_icp: bool = True,
    ) -> None:
        self.intrinsics = scale_tracking_intrinsics(intrinsics, tracking_width, tracking_height)
        self._backend = backend
        self.tracking_width = int(tracking_width)
        self.tracking_height = int(tracking_height)
        self.min_backend_valid_pixels = int(min_backend_valid_pixels)
        self.enable_icp = bool(enable_icp)

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
        previous_valid_pixels = int(np.count_nonzero(previous_depth_m > 0.0))
        current_valid_pixels = int(np.count_nonzero(current_depth_m > 0.0))

        if (
            previous_valid_pixels < self.min_backend_valid_pixels
            or current_valid_pixels < self.min_backend_valid_pixels
        ):
            initial_transform = np.asarray(initial_transform, dtype=np.float64)
            return OdometryEstimate(
                relative_transform=initial_transform.copy(),
                fitness=0.0,
                rmse_m=float("inf"),
                depth_valid_ratio=depth_valid_ratio,
            )

        estimate = self._get_backend().estimate(
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

    def _get_backend(self) -> RgbdOdometryBackend:
        if self._backend is None:
            self._backend = Open3dRgbdOdometryBackend(enable_icp=self.enable_icp)
        return self._backend

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
    def __init__(self, enable_icp: bool = True) -> None:
        import open3d as o3d

        self._o3d = o3d
        self.enable_icp = bool(enable_icp)

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

        if self.enable_icp:
            source_cloud = o3d.geometry.PointCloud.create_from_rgbd_image(source_rgbd, camera)
            target_cloud = o3d.geometry.PointCloud.create_from_rgbd_image(target_rgbd, camera)
            transform, fitness, rmse_m = self._refine_with_point_to_plane_icp(
                source_cloud,
                target_cloud,
                np.asarray(transform, dtype=np.float64),
            )
        else:
            fitness = 1.0 if success else 0.0
            rmse_m = 0.0 if success else float("inf")
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
