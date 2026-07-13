"""Coverage estimate for a handheld pass around a small object."""

import numpy as np


class ViewCoverage:
    def __init__(
        self,
        object_center: np.ndarray,
        azimuth_bins: int = 24,
        elevation_bins: int = 3,
    ) -> None:
        self.object_center = np.asarray(object_center, dtype=np.float64)
        self.azimuth_bins = int(azimuth_bins)
        self.elevation_bins = int(elevation_bins)
        if self.azimuth_bins <= 0 or self.elevation_bins <= 0:
            raise ValueError("Coverage bins must be positive.")
        self._visited: set[tuple[int, int]] = set()
        self._trajectory: list[np.ndarray] = []

    def add_camera_position(self, position: np.ndarray) -> None:
        position = np.asarray(position, dtype=np.float64)
        direction = position - self.object_center
        horizontal_radius = float(np.linalg.norm(direction[[0, 2]]))
        if np.linalg.norm(direction) == 0.0:
            return

        azimuth = (np.arctan2(direction[2], direction[0]) + 2 * np.pi) % (2 * np.pi)
        elevation = np.arctan2(direction[1], horizontal_radius)
        azimuth_bin = min(
            int(azimuth / (2 * np.pi) * self.azimuth_bins),
            self.azimuth_bins - 1,
        )
        normalized_elevation = np.clip((elevation + np.pi / 2) / np.pi, 0.0, 0.999999)
        elevation_bin = int(normalized_elevation * self.elevation_bins)
        self._visited.add((azimuth_bin, elevation_bin))
        self._trajectory.append(position.copy())

    @property
    def ratio(self) -> float:
        return len(self._visited) / float(self.azimuth_bins * self.elevation_bins)

    @property
    def trajectory(self) -> tuple[np.ndarray, ...]:
        return tuple(point.copy() for point in self._trajectory)

