"""Deterministic depth processing for synchronized capture packets."""

from dataclasses import dataclass

import numpy as np

from scanner_app.camera.models import SynchronizedFramePacket


@dataclass(frozen=True)
class ProcessedDepth:
    depth_m: np.ndarray
    valid_mask: np.ndarray
    valid_ratio: float
    median_depth_m: float | None


class DepthProcessor:
    def __init__(self, min_depth_m: float = 0.15, max_depth_m: float = 0.50) -> None:
        if min_depth_m <= 0 or min_depth_m >= max_depth_m:
            raise ValueError("Depth range must satisfy 0 < min < max.")
        self.min_depth_m = float(min_depth_m)
        self.max_depth_m = float(max_depth_m)

    def process(self, packet: SynchronizedFramePacket) -> ProcessedDepth:
        depth_m = packet.depth_m
        valid_mask = (depth_m >= self.min_depth_m) & (depth_m <= self.max_depth_m)
        filtered = np.where(valid_mask, depth_m, 0.0).astype(np.float32)
        valid_depth = filtered[valid_mask]
        median_depth_m = (
            round(float(np.median(valid_depth)), 6) if valid_depth.size else None
        )

        return ProcessedDepth(
            depth_m=filtered,
            valid_mask=valid_mask,
            valid_ratio=float(np.mean(valid_mask)),
            median_depth_m=median_depth_m,
        )
