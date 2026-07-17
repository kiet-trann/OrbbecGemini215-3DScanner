"""Preflight Gemini 215 camera profiles before RTAB-Map takes ownership."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from scanner_app.camera.models import CameraProfile, CameraSettingsSnapshot, CaptureConfig


class CameraPreflightError(RuntimeError):
    """Raised when a requested camera profile cannot be inspected or applied."""


class CameraPreflight:
    """Inspect or set a depth work mode without starting an RGB-D stream."""

    def __init__(
        self,
        *,
        sdk_module: Any | None = None,
        capture_config: CaptureConfig | None = None,
        alignment_target: str = "depth",
    ) -> None:
        self._sdk = sdk_module
        self._capture_config = capture_config or CaptureConfig()
        self._alignment_target = alignment_target

    def inspect(self, profile: CameraProfile) -> CameraSettingsSnapshot:
        return self._operate(profile, apply=False)

    def apply(self, profile: CameraProfile) -> CameraSettingsSnapshot:
        return self._operate(profile, apply=True)

    def _operate(self, profile: CameraProfile, *, apply: bool) -> CameraSettingsSnapshot:
        context: Any | None = None
        try:
            sdk = self._sdk or self._load_sdk()
            context = self._context(sdk)
            device = self._connected_device(context)
            modes = self._work_modes(device)
            selected = self._selected_mode(profile, modes)
            if apply and self._mode_name(device.get_depth_work_mode()) != self._mode_name(selected):
                device.set_depth_work_mode(selected)
            state = "applied-and-verified" if apply else "inspected"
            snapshot = self._snapshot(profile, state, device, modes, sdk)
            if apply and snapshot.confirmed_mode != self._mode_name(selected):
                raise CameraPreflightError("Camera did not retain the requested depth work mode.")
            return snapshot
        except CameraPreflightError:
            raise
        except Exception as error:
            raise CameraPreflightError(f"Cannot inspect Gemini 215 camera: {error}") from error
        finally:
            self._close_context(context)

    @staticmethod
    def _load_sdk() -> Any:
        try:
            return import_module("pyorbbecsdk")
        except ImportError as error:
            raise CameraPreflightError(
                "Orbbec Python SDK is not installed. Install pyorbbecsdk2 before configuring a profile."
            ) from error

    @staticmethod
    def _context(sdk: Any) -> Any:
        factory = getattr(sdk, "Context", None)
        if factory is None:
            raise CameraPreflightError("Orbbec SDK does not provide a device context.")
        return factory()

    @staticmethod
    def _connected_device(context: Any) -> Any:
        devices = context.query_devices()
        count_getter = getattr(devices, "get_count", None)
        count = int(count_getter() if count_getter is not None else len(devices))
        if count <= 0:
            raise CameraPreflightError("No Orbbec camera found. Connect Gemini 215 through USB 3.0.")
        getter = getattr(devices, "get_device_by_index", None)
        if getter is not None:
            return getter(0)
        try:
            return devices[0]
        except (IndexError, TypeError) as error:
            raise CameraPreflightError("Orbbec SDK cannot open the connected camera.") from error

    @staticmethod
    def _work_modes(device: Any) -> tuple[Any, ...]:
        try:
            modes = device.get_depth_work_mode_list()
            return tuple(modes.get_depth_work_mode_by_index(index) for index in range(modes.get_count()))
        except Exception as error:
            raise CameraPreflightError(f"Cannot list camera depth work modes: {error}") from error

    @staticmethod
    def _selected_mode(profile: CameraProfile, modes: tuple[Any, ...]) -> Any:
        for mode in modes:
            if profile.mode_name_matches(CameraPreflight._mode_name(mode)):
                return mode
        raise CameraPreflightError(
            f"{profile.display_name} is unavailable on this connected camera."
        )

    def _snapshot(
        self,
        profile: CameraProfile,
        state: str,
        device: Any,
        modes: tuple[Any, ...],
        sdk: Any,
    ) -> CameraSettingsSnapshot:
        device_info = self._optional_call(device, "get_device_info")
        return CameraSettingsSnapshot(
            profile=profile,
            preflight_state=state,
            confirmed_mode=self._mode_name(device.get_depth_work_mode()),
            supported_modes=tuple(self._mode_name(mode) for mode in modes),
            device_name=self._optional_device_info_value(device_info, "get_name"),
            serial_number=self._optional_device_info_value(device_info, "get_serial_number"),
            firmware_version=self._optional_device_info_value(device_info, "get_firmware_version"),
            capture_config=self._capture_config,
            alignment_target=self._alignment_target,
            enabled_depth_filters=self._enabled_depth_filters(device, sdk),
        )

    @staticmethod
    def _mode_name(mode: Any) -> str:
        name = getattr(mode, "name", None)
        if not isinstance(name, str) or not name:
            raise CameraPreflightError("Camera returned a depth work mode without a name.")
        return name

    @staticmethod
    def _optional_call(target: Any, method_name: str) -> Any | None:
        method = getattr(target, method_name, None)
        if method is None:
            return None
        try:
            return method()
        except Exception:
            return None

    @classmethod
    def _optional_device_info_value(cls, info: Any | None, method_name: str) -> str | None:
        value = cls._optional_call(info, method_name) if info is not None else None
        return str(value) if value is not None else None

    @classmethod
    def _enabled_depth_filters(cls, device: Any, sdk: Any) -> tuple[str, ...]:
        sensor_type = getattr(getattr(sdk, "OBSensorType", None), "DEPTH_SENSOR", None)
        get_sensor = getattr(device, "get_sensor", None)
        if sensor_type is None or get_sensor is None:
            return ()
        try:
            filters = get_sensor(sensor_type).get_recommended_filters()
            return tuple(
                str(depth_filter.get_name())
                for depth_filter in filters
                if depth_filter.is_enabled()
            )
        except Exception:
            return ()

    @staticmethod
    def _close_context(context: Any | None) -> None:
        close = getattr(context, "close", None)
        if close is not None:
            close()

