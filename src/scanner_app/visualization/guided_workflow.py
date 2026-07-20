"""Pure presentation state for the guided scanner workflow."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class DashboardLike(Protocol):
    """The dashboard fields needed to choose a guided workflow state."""

    runtime_message: str
    camera_controls_locked: bool
    camera_snapshot: object | None


class GuidedMode(str, Enum):
    CHECK_CAMERA = "check_camera"
    START_SCAN = "start_scan"
    LIVE_CONTROL = "live_control"


@dataclass(frozen=True)
class GuidedWorkflow:
    mode: GuidedMode
    primary_label: str
    camera_ready: bool
    camera_locked: bool
    results_ready: bool


def guided_workflow(dashboard: DashboardLike, *, has_sessions: bool) -> GuidedWorkflow:
    """Derive the current guided action from existing scanner state."""
    camera_ready = dashboard.camera_snapshot is not None
    if dashboard.camera_controls_locked:
        return GuidedWorkflow(
            GuidedMode.LIVE_CONTROL,
            "Tạm dừng",
            camera_ready,
            True,
            has_sessions,
        )
    if not camera_ready:
        return GuidedWorkflow(
            GuidedMode.CHECK_CAMERA,
            "Kiểm tra camera",
            False,
            False,
            has_sessions,
        )
    return GuidedWorkflow(
        GuidedMode.START_SCAN,
        "Bắt đầu quét",
        True,
        False,
        has_sessions,
    )
