"""Presentation helpers for the live markerless scanner."""

from dataclasses import dataclass

from scanner_app.session.models import ScannerSnapshot
from scanner_app.tracking.models import TrackingState


@dataclass(frozen=True)
class ScannerStatus:
    tracking_text: str
    tracking_color: tuple[float, float, float]
    guidance: str
    integrating: bool


def status_from_snapshot(snapshot: ScannerSnapshot) -> ScannerStatus:
    tracking_state = None if snapshot.tracking is None else snapshot.tracking.state
    if tracking_state is TrackingState.LOST:
        return ScannerStatus(
            tracking_text="LOST",
            tracking_color=(1.0, 0.2, 0.2),
            guidance="Return to the last accepted view",
            integrating=False,
        )
    if tracking_state is TrackingState.DEGRADED:
        return ScannerStatus(
            tracking_text="WEAK",
            tracking_color=(1.0, 0.75, 0.1),
            guidance="Move slowly and keep overlap",
            integrating=False,
        )
    if tracking_state is TrackingState.TRACKING:
        return ScannerStatus(
            tracking_text="TRACKING",
            tracking_color=(0.2, 0.85, 0.35),
            guidance="",
            integrating=True,
        )
    return ScannerStatus(
        tracking_text="READY",
        tracking_color=(0.7, 0.7, 0.7),
        guidance="Hold the camera still",
        integrating=False,
    )


def format_status_line(snapshot: ScannerSnapshot) -> str:
    status = status_from_snapshot(snapshot)
    guidance = f" | {status.guidance}" if status.guidance else ""
    metrics = snapshot.tracking.metrics if snapshot.tracking is not None else None
    quality = ""
    if metrics is not None:
        reason = snapshot.tracking.reason or "-"
        quality = f" | reason={reason} | fit={metrics.fitness:.2f} | rmse={metrics.rmse_m:.4g}"
    return (
        f"{status.tracking_text} | capture={snapshot.capture_fps:.1f} FPS | "
        f"tracking={snapshot.tracking_fps:.1f} FPS | preview={snapshot.preview_fps:.1f} FPS | "
        f"depth={snapshot.depth_valid_ratio:.2f} | coverage={snapshot.coverage_ratio:.0%}"
        f"{quality}{guidance}"
    )


class ScannerWindow:
    """Lazy Open3D GUI shell for future richer embedding.

    Phase 3's runnable scanner uses OpenCV + Open3D Visualizer windows because
    they are more reliable with the current native stack. This class preserves a
    stable extension point for a single Open3D GUI window without importing GUI
    bindings during tests.
    """

    def __init__(self, session) -> None:
        self.session = session

    def run(self) -> None:
        from open3d.visualization import gui

        gui.Application.instance.initialize()
        window = gui.Application.instance.create_window(
            "Gemini 215 Markerless Scanner",
            1440,
            820,
        )
        window.set_on_close(self._on_close)
        gui.Application.instance.run()

    def _on_close(self) -> bool:
        self.session.close()
        return True
