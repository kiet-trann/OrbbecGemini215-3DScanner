"""Orbbec Gemini 215 capture adapter.

The implementation will wrap pyorbbecsdk2 and expose a small stable interface
for the rest of the prototype.
"""

from importlib import import_module
import os
from pathlib import Path
from typing import Any

import numpy as np

from scanner_app.camera.models import (
    CameraIntrinsics,
    CaptureConfig,
    RgbdFrame,
    SynchronizedFramePacket,
)


class OrbbecSdkNotAvailable(RuntimeError):
    """Raised when the Orbbec Python SDK is not installed."""


class OrbbecCameraError(RuntimeError):
    """Raised when the Orbbec camera cannot be started or used."""


class OrbbecFrameError(RuntimeError):
    """Raised when the camera does not provide a usable RGB-D frame set."""


class OrbbecCapture:
    """Thin wrapper around pyorbbecsdk2 for Gemini 215."""

    def __init__(
        self,
        sdk_module: Any | None = None,
        color_frame_converter: Any | None = None,
        timeout_ms: int = 1000,
        align_to_depth: bool = False,
    ) -> None:
        self._sdk = sdk_module
        self._color_frame_converter = color_frame_converter
        self._timeout_ms = timeout_ms
        self._align_to_depth = align_to_depth
        self._align_filter: Any | None = None
        self._pipeline: Any | None = None
        self._last_depth_scale: float | None = None

    def start(self) -> None:
        sdk = self._sdk or self._load_sdk()
        self._sdk = sdk
        self._ensure_sdk_log_directory()
        self._assert_device_available(sdk)
        self._pipeline = sdk.Pipeline()
        config = self._build_stream_config(sdk, self._pipeline)
        self._align_filter = self._build_align_filter(sdk) if self._align_to_depth else None
        try:
            self._pipeline.start(config)
        except Exception as error:
            self._pipeline = None
            self._align_filter = None
            raise OrbbecCameraError(f"Failed to start Orbbec camera: {error}") from error

    def read(self) -> RgbdFrame:
        if self._pipeline is None:
            raise OrbbecFrameError("Camera pipeline has not been started.")

        frames = self._pipeline.wait_for_frames(self._timeout_ms)
        if frames is None:
            raise OrbbecFrameError("No RGB-D frames received from Orbbec camera.")

        if self._align_filter is not None:
            frames = self._align_filter.process(frames)
            if frames is None:
                raise OrbbecFrameError("RGB-D alignment did not return a frame set.")

        depth_frame = frames.get_depth_frame()
        if depth_frame is None:
            raise OrbbecFrameError("Depth frame missing from Orbbec frame set.")

        color_frame = frames.get_color_frame()
        color = self._convert_color_frame(color_frame) if color_frame is not None else None

        width = depth_frame.get_width()
        height = depth_frame.get_height()
        depth = np.frombuffer(depth_frame.get_data(), dtype=np.uint16).reshape((height, width))
        depth_scale = float(depth_frame.get_depth_scale())
        self._last_depth_scale = depth_scale

        return RgbdFrame(
            color=color,
            depth=depth,
            depth_scale=depth_scale,
            timestamp_ms=self._frame_timestamp_ms(depth_frame),
        )

    def intrinsics(self) -> CameraIntrinsics:
        if self._pipeline is None:
            raise OrbbecFrameError("Camera pipeline has not been started.")

        camera_param = self._pipeline.get_camera_param()
        intrinsic = camera_param.depth_intrinsic
        return CameraIntrinsics(
            fx=float(intrinsic.fx),
            fy=float(intrinsic.fy),
            cx=float(intrinsic.cx),
            cy=float(intrinsic.cy),
            width=int(intrinsic.width),
            height=int(intrinsic.height),
        )

    def depth_scale(self) -> float:
        if self._last_depth_scale is None:
            raise OrbbecFrameError("Depth scale is not available until a depth frame is read.")
        return self._last_depth_scale

    def stop(self) -> None:
        if self._pipeline is not None:
            self._pipeline.stop()
            self._pipeline = None
        self._align_filter = None

    @staticmethod
    def _load_sdk() -> Any:
        try:
            return import_module("pyorbbecsdk")
        except ImportError as error:
            raise OrbbecSdkNotAvailable(
                "Orbbec Python SDK is not installed. Install it with: "
                "python -m pip install --upgrade pyorbbecsdk2"
            ) from error

    @staticmethod
    def _ensure_sdk_log_directory() -> None:
        Path(os.getcwd(), "Log").mkdir(exist_ok=True)

    @staticmethod
    def _assert_device_available(sdk: Any) -> None:
        context_factory = getattr(sdk, "Context", None)
        if context_factory is None:
            return

        context = context_factory()
        devices = context.query_devices()
        count_getter = getattr(devices, "get_count", None)
        device_count = int(count_getter() if count_getter is not None else len(devices))
        if device_count <= 0:
            raise OrbbecCameraError(
                "No Orbbec device found. Connect Gemini 215 through USB 3.0 and verify it in "
                "Orbbec Viewer or Device Manager."
            )

    @staticmethod
    def _build_stream_config(sdk: Any, pipeline: Any) -> Any | None:
        config_factory = getattr(sdk, "Config", None)
        sensor_type = getattr(sdk, "OBSensorType", None)
        if config_factory is None or sensor_type is None:
            return None

        config = config_factory()
        try:
            depth_sensor = getattr(sensor_type, "DEPTH_SENSOR")
            depth_profiles = pipeline.get_stream_profile_list(depth_sensor)
            depth_profile = depth_profiles.get_default_video_stream_profile()
            config.enable_stream(depth_profile)
        except Exception as error:
            raise OrbbecCameraError(f"Cannot configure Orbbec depth stream: {error}") from error

        try:
            color_sensor = getattr(sensor_type, "COLOR_SENSOR")
            color_profiles = pipeline.get_stream_profile_list(color_sensor)
            color_profile = OrbbecCapture._color_stream_profile(sdk, color_profiles)
            config.enable_stream(color_profile)
        except Exception:
            pass

        aggregate_mode = getattr(sdk, "OBFrameAggregateOutputMode", None)
        set_aggregate_mode = getattr(config, "set_frame_aggregate_output_mode", None)
        if aggregate_mode is not None and set_aggregate_mode is not None:
            set_aggregate_mode(getattr(aggregate_mode, "FULL_FRAME_REQUIRE"))

        return config

    @staticmethod
    def _color_stream_profile(sdk: Any, color_profiles: Any) -> Any:
        frame_format = getattr(getattr(sdk, "OBFormat", None), "RGB", None)
        get_video_profile = getattr(color_profiles, "get_video_stream_profile", None)
        if frame_format is not None and get_video_profile is not None:
            try:
                return get_video_profile(0, 0, frame_format, 0)
            except Exception:
                pass
        return color_profiles.get_default_video_stream_profile()

    @staticmethod
    def _build_align_filter(sdk: Any) -> Any:
        align_filter_factory = getattr(sdk, "AlignFilter", None)
        stream_type = getattr(sdk, "OBStreamType", None)
        if align_filter_factory is None or stream_type is None:
            raise OrbbecCameraError("Orbbec SDK does not provide RGB-D alignment support.")

        depth_stream = getattr(stream_type, "DEPTH_STREAM")
        return align_filter_factory(align_to_stream=depth_stream)

    def _convert_color_frame(self, color_frame: Any) -> np.ndarray:
        if self._color_frame_converter is not None:
            return self._color_frame_converter(color_frame)

        try:
            import cv2
        except ImportError as error:
            raise OrbbecFrameError(
                "OpenCV is required to convert Orbbec color frames. "
                "Install opencv-contrib-python."
            ) from error

        width = color_frame.get_width()
        height = color_frame.get_height()
        data = np.asanyarray(color_frame.get_data())
        frame_format = color_frame.get_format()
        format_name = getattr(frame_format, "name", str(frame_format))

        if format_name.endswith("RGB"):
            image = np.resize(data, (height, width, 3))
            return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        if format_name.endswith("BGR"):
            return np.resize(data, (height, width, 3))
        if format_name.endswith("MJPG"):
            image = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if image is None:
                raise OrbbecFrameError("Failed to decode MJPG color frame.")
            return image
        if format_name.endswith("YUYV"):
            image = np.resize(data, (height, width, 2))
            return cv2.cvtColor(image, cv2.COLOR_YUV2BGR_YUYV)
        if format_name.endswith("UYVY"):
            image = np.resize(data, (height, width, 2))
            return cv2.cvtColor(image, cv2.COLOR_YUV2BGR_UYVY)

        raise OrbbecFrameError(f"Unsupported Orbbec color frame format: {frame_format}")

    @staticmethod
    def _frame_timestamp_ms(frame: Any) -> float:
        for method_name in ("get_timestamp", "get_system_timestamp"):
            method = getattr(frame, method_name, None)
            if method is not None:
                return float(method())
        return 0.0
