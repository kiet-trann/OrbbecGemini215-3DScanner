from __future__ import annotations

import pytest

from scanner_app.camera.models import CameraProfile
from scanner_app.camera.preflight import CameraPreflight, CameraPreflightError


class FakeDepthWorkMode:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeDepthWorkModeList:
    def __init__(self, names: tuple[str, ...]) -> None:
        self._modes = tuple(FakeDepthWorkMode(name) for name in names)

    def get_count(self) -> int:
        return len(self._modes)

    def get_depth_work_mode_by_index(self, index: int) -> FakeDepthWorkMode:
        return self._modes[index]


class FakeDeviceInfo:
    def __init__(self, connection_type: str | None = "USB3.0") -> None:
        self._connection_type = connection_type

    def get_name(self) -> str:
        return "Gemini 215"

    def get_serial_number(self) -> str:
        return "G215-123"

    def get_firmware_version(self) -> str:
        return "1.0.0"

    def get_connection_type(self) -> str | None:
        return self._connection_type


class FakeDevice:
    def __init__(
        self,
        modes: tuple[str, ...],
        *,
        retain_mode: bool = True,
        connection_type: str | None = "USB3.0",
    ) -> None:
        self._modes = FakeDepthWorkModeList(modes)
        self.selected_depth_mode = modes[0]
        self.retain_mode = retain_mode
        self.connection_type = connection_type
        self.set_mode_calls = 0

    def get_depth_work_mode_list(self) -> FakeDepthWorkModeList:
        return self._modes

    def get_depth_work_mode(self) -> FakeDepthWorkMode:
        return FakeDepthWorkMode(self.selected_depth_mode)

    def set_depth_work_mode(self, mode: FakeDepthWorkMode) -> None:
        self.set_mode_calls += 1
        if self.retain_mode:
            self.selected_depth_mode = mode.name

    def get_device_info(self) -> FakeDeviceInfo:
        return FakeDeviceInfo(self.connection_type)


class FakeDeviceList:
    def __init__(self, device: FakeDevice) -> None:
        self._device = device

    def get_count(self) -> int:
        return 1

    def get_device_by_index(self, index: int) -> FakeDevice:
        assert index == 0
        return self._device


class FakeContext:
    def __init__(self, device: FakeDevice) -> None:
        self._device = device
        self.closed = False

    def query_devices(self) -> FakeDeviceList:
        return FakeDeviceList(self._device)

    def close(self) -> None:
        self.closed = True


class FakePipeline:
    start_calls = 0


class FakeSdk:
    def __init__(
        self,
        modes: tuple[str, ...],
        *,
        retain_mode: bool = True,
        connection_type: str | None = "USB3.0",
    ) -> None:
        self.device = FakeDevice(
            modes,
            retain_mode=retain_mode,
            connection_type=connection_type,
        )
        self.context = FakeContext(self.device)
        self.pipeline = FakePipeline()

    def Context(self) -> FakeContext:
        return self.context


def test_apply_switches_to_enumerated_far_mode_and_reads_it_back() -> None:
    sdk = FakeSdk(("Close_Up Precision Mode", "Long-distance Mode"))

    snapshot = CameraPreflight(sdk_module=sdk).apply(CameraProfile.FAR)

    assert sdk.device.selected_depth_mode == "Long-distance Mode"
    assert snapshot.confirmed_mode == "Long-distance Mode"
    assert snapshot.supported_modes == ("Close_Up Precision Mode", "Long-distance Mode")
    assert snapshot.device_name == "Gemini 215"
    assert sdk.context.closed


def test_inspect_does_not_change_current_mode() -> None:
    sdk = FakeSdk(("Close_Up Precision Mode", "Long-distance Mode"))

    snapshot = CameraPreflight(sdk_module=sdk).inspect(CameraProfile.FAR)

    assert sdk.device.set_mode_calls == 0
    assert snapshot.confirmed_mode == "Close_Up Precision Mode"
    assert snapshot.preflight_state == "inspected"


def test_apply_rejects_an_unavailable_profile_without_starting_a_stream() -> None:
    sdk = FakeSdk(("Close_Up Precision Mode",))

    with pytest.raises(CameraPreflightError, match="Far"):
        CameraPreflight(sdk_module=sdk).apply(CameraProfile.FAR)

    assert sdk.pipeline.start_calls == 0
    assert sdk.context.closed


def test_apply_rejects_mode_that_does_not_remain_selected() -> None:
    sdk = FakeSdk(("Close_Up Precision Mode", "Long-distance Mode"), retain_mode=False)

    with pytest.raises(CameraPreflightError, match="did not retain"):
        CameraPreflight(sdk_module=sdk).apply(CameraProfile.FAR)


def test_inspect_reports_usb2_without_rejecting_read_only_diagnostics() -> None:
    sdk = FakeSdk(("Close_Up Precision Mode",), connection_type="USB2.0")

    snapshot = CameraPreflight(sdk_module=sdk).inspect(CameraProfile.NEAR)

    assert snapshot.connection_type == "USB2.0"
    assert sdk.device.set_mode_calls == 0
    assert sdk.context.closed


@pytest.mark.parametrize("connection_type", ["USB3.0", "USB 3.0", "usb3"])
def test_apply_accepts_normalized_usb3_connection(connection_type: str) -> None:
    sdk = FakeSdk(
        ("Close_Up Precision Mode", "Long-distance Mode"),
        connection_type=connection_type,
    )

    snapshot = CameraPreflight(sdk_module=sdk).apply(CameraProfile.FAR)

    assert snapshot.connection_type == connection_type
    assert sdk.device.set_mode_calls == 1


def test_apply_rejects_usb2_before_changing_depth_mode() -> None:
    sdk = FakeSdk(
        ("Close_Up Precision Mode", "Long-distance Mode"),
        connection_type="USB2.0",
    )

    with pytest.raises(CameraPreflightError, match="USB 3"):
        CameraPreflight(sdk_module=sdk).apply(CameraProfile.FAR)

    assert sdk.device.set_mode_calls == 0
    assert sdk.context.closed


def test_apply_rejects_missing_connection_metadata() -> None:
    sdk = FakeSdk(("Close_Up Precision Mode",), connection_type=None)

    with pytest.raises(CameraPreflightError, match="không xác định"):
        CameraPreflight(sdk_module=sdk).apply(CameraProfile.NEAR)

    assert sdk.context.closed

