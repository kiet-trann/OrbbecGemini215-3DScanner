"""Orbbec Gemini 215 capture adapter.

The implementation will wrap pyorbbecsdk2 and expose a small stable interface
for the rest of the prototype.
"""

from importlib import import_module
import os
from pathlib import Path
from typing import Any

import numpy as np

from scanner_app.camera.imu_buffer import ImuBuffer
from scanner_app.camera.models import (
    CameraIntrinsics,
    CaptureConfig,
    ImuSample,
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
        capture_config: CaptureConfig | None = None,
        timeout_ms: int = 1000,
        align_to_depth: bool = False,
        alignment_target: str | None = None,
    ) -> None:
        self._sdk = sdk_module
        self._color_frame_converter = color_frame_converter
        self._capture_config = capture_config or CaptureConfig()
        self._timeout_ms = timeout_ms
        if alignment_target is None:
            alignment_target = "depth" if align_to_depth else "none"
        if alignment_target not in {"none", "depth", "color"}:
            raise ValueError("alignment_target must be one of: none, depth, color.")
        self._alignment_target = alignment_target
        self._align_filter: Any | None = None
        self._depth_filters: tuple[Any, ...] = ()
        self.enabled_depth_filter_names: tuple[str, ...] = ()
        self._pipeline: Any | None = None
        self._last_depth_scale: float | None = None
        self._last_color_timestamp_us = 0
        self._imu_buffer = ImuBuffer()
        self._imu_pipeline: Any | None = None
        self._sequence = 0

    def start(self) -> None:
        sdk = self._sdk or self._load_sdk()
        self._sdk = sdk
        self._ensure_sdk_log_directory()
        self._assert_device_available(sdk)
        pipeline = sdk.Pipeline()
        self._pipeline = pipeline
        try:
            config = self._build_stream_config(sdk, pipeline)
            self._configure_depth_mode_and_filters(sdk, pipeline)
            self._align_filter = (
                self._build_align_filter(sdk, self._alignment_target)
                if self._alignment_target != "none"
                else None
            )
            enable_sync = getattr(pipeline, "enable_frame_sync", None)
            if enable_sync is None:
                raise OrbbecCameraError("Orbbec pipeline does not provide enable_frame_sync.")
            try:
                enable_sync()
            except Exception as error:
                raise OrbbecCameraError(
                    f"Failed to enable Orbbec frame sync: {error}"
                ) from error
            pipeline.start(config)
            self._start_imu_pipeline(sdk)
        except Exception as error:
            self._clear_started_state()
            if isinstance(error, OrbbecCameraError):
                raise
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

        for depth_filter in self._depth_filters:
            filtered = depth_filter.process(depth_frame)
            if filtered is None:
                raise OrbbecFrameError(f"Depth filter failed: {depth_filter.get_name()}")
            depth_frame = filtered.as_depth_frame()
            if depth_frame is None:
                raise OrbbecFrameError(f"Depth filter failed: {depth_filter.get_name()}")

        color_frame = frames.get_color_frame()
        color = self._convert_color_frame(color_frame) if color_frame is not None else None
        self._last_color_timestamp_us = (
            self._frame_timestamp_us(color_frame) if color_frame is not None else 0
        )

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

    def read_packet(self) -> SynchronizedFramePacket:
        frame = self.read()
        if frame.color is None:
            raise OrbbecFrameError("Color frame missing from Orbbec frame set.")

        depth_timestamp_us = int(round(frame.timestamp_ms * 1000.0))
        packet = SynchronizedFramePacket(
            color_bgr=frame.color,
            depth_raw=frame.depth,
            depth_scale_mm=frame.depth_scale,
            depth_timestamp_us=depth_timestamp_us,
            color_timestamp_us=self._last_color_timestamp_us,
            imu_samples=self._imu_buffer.pop_through(depth_timestamp_us),
            sequence=self._sequence,
        )
        self._sequence += 1
        return packet

    def intrinsics(self) -> CameraIntrinsics:
        if self._pipeline is None:
            raise OrbbecFrameError("Camera pipeline has not been started.")

        camera_param = self._pipeline.get_camera_param()
        intrinsic = (
            getattr(camera_param, "rgb_intrinsic", None)
            if self._alignment_target == "color"
            else camera_param.depth_intrinsic
        )
        if intrinsic is None:
            raise OrbbecCameraError("Orbbec camera parameters do not provide RGB intrinsics.")
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
        self._stop_imu_pipeline()
        if self._pipeline is not None:
            self._pipeline.stop()
        self._clear_started_state()

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

    def _build_stream_config(self, sdk: Any, pipeline: Any) -> Any:
        config_factory = getattr(sdk, "Config", None)
        sensor_type = getattr(sdk, "OBSensorType", None)
        if config_factory is None or sensor_type is None:
            missing_name = "Config" if config_factory is None else "OBSensorType"
            raise OrbbecCameraError(f"Orbbec SDK does not provide required {missing_name} API.")

        config = config_factory()
        enable_stream = getattr(config, "enable_stream", None)
        if enable_stream is None:
            raise OrbbecCameraError("Orbbec Config does not provide required enable_stream API.")
        get_profile_list = getattr(pipeline, "get_stream_profile_list", None)
        if get_profile_list is None:
            raise OrbbecCameraError(
                "Orbbec pipeline does not provide required get_stream_profile_list API."
            )
        try:
            depth_sensor = getattr(sensor_type, "DEPTH_SENSOR")
            depth_profiles = get_profile_list(depth_sensor)
            depth_profile_getter = getattr(depth_profiles, "get_video_stream_profile", None)
            if depth_profile_getter is None:
                raise OrbbecCameraError(
                    "Orbbec depth profiles do not provide required get_video_stream_profile API."
                )
            depth_profile = depth_profile_getter(
                self._capture_config.depth_width,
                self._capture_config.depth_height,
                self._sdk_format(sdk, self._capture_config.depth_format),
                self._capture_config.depth_fps,
            )
            enable_stream(depth_profile)
        except Exception as error:
            if isinstance(error, OrbbecCameraError):
                raise
            raise OrbbecCameraError(f"Cannot configure Orbbec depth stream: {error}") from error

        try:
            color_sensor = getattr(sensor_type, "COLOR_SENSOR")
            color_profiles = get_profile_list(color_sensor)
            color_profile_getter = getattr(color_profiles, "get_video_stream_profile", None)
            if color_profile_getter is None:
                raise OrbbecCameraError(
                    "Orbbec color profiles do not provide required get_video_stream_profile API."
                )
            color_profile = color_profile_getter(
                self._capture_config.color_width,
                self._capture_config.color_height,
                self._sdk_format(sdk, self._capture_config.color_format),
                self._capture_config.color_fps,
            )
            enable_stream(color_profile)
        except Exception as error:
            if isinstance(error, OrbbecCameraError):
                raise
            raise OrbbecCameraError(f"Cannot configure Orbbec color stream: {error}") from error

        aggregate_mode = getattr(sdk, "OBFrameAggregateOutputMode", None)
        set_aggregate_mode = getattr(config, "set_frame_aggregate_output_mode", None)
        if aggregate_mode is None:
            raise OrbbecCameraError(
                "Orbbec SDK does not provide required OBFrameAggregateOutputMode API."
            )
        if set_aggregate_mode is None:
            raise OrbbecCameraError(
                "Orbbec Config does not provide required set_frame_aggregate_output_mode API."
            )
        set_aggregate_mode(getattr(aggregate_mode, "FULL_FRAME_REQUIRE"))

        return config

    @staticmethod
    def _sdk_format(sdk: Any, format_name: str) -> Any:
        sdk_formats = getattr(sdk, "OBFormat", None)
        frame_format = getattr(sdk_formats, format_name, None)
        if frame_format is None:
            raise OrbbecCameraError(f"Orbbec SDK does not provide required {format_name} format.")
        return frame_format

    def _configure_depth_mode_and_filters(self, sdk: Any, pipeline: Any) -> None:
        get_device = getattr(pipeline, "get_device", None)
        sensor_type = getattr(sdk, "OBSensorType", None)
        if get_device is None or sensor_type is None:
            missing_name = "get_device" if get_device is None else "OBSensorType"
            raise OrbbecCameraError(
                f"Orbbec SDK does not provide required {missing_name} API for depth mode setup."
            )

        device = get_device()
        self._select_depth_work_mode(device)
        get_sensor = getattr(device, "get_sensor", None)
        if get_sensor is None:
            raise OrbbecCameraError(
                "Orbbec device does not provide required get_sensor API for depth filters."
            )
        depth_sensor = get_sensor(getattr(sensor_type, "DEPTH_SENSOR"))
        self._depth_filters = tuple(
            depth_filter
            for depth_filter in depth_sensor.get_recommended_filters()
            if depth_filter.is_enabled()
        )
        self.enabled_depth_filter_names = tuple(
            depth_filter.get_name() for depth_filter in self._depth_filters
        )

    def _select_depth_work_mode(self, device: Any) -> None:
        required_mode_name = self._required_depth_work_mode_name()
        try:
            modes = device.get_depth_work_mode_list()
            close_up = next(
                mode
                for mode in (
                    modes.get_depth_work_mode_by_index(index) for index in range(modes.get_count())
                )
                if mode.name == required_mode_name
            )
        except StopIteration as error:
            raise OrbbecCameraError(
                f"Required Orbbec depth work mode is unavailable: {required_mode_name}"
            ) from error
        except Exception as error:
            raise OrbbecCameraError(f"Cannot inspect Orbbec depth work modes: {error}") from error

        try:
            current_mode = device.get_depth_work_mode()
            if current_mode.name != close_up.name:
                device.set_depth_work_mode(close_up)
        except Exception as error:
            raise OrbbecCameraError(f"Cannot select Orbbec depth work mode: {error}") from error

    def _required_depth_work_mode_name(self) -> str:
        if self._capture_config.depth_precision_mode == "Close_Up":
            return "Close_Up Precision Mode"
        return str(self._capture_config.depth_precision_mode)

    def _start_imu_pipeline(self, sdk: Any) -> None:
        pipeline_factory = getattr(sdk, "Pipeline", None)
        config_factory = getattr(sdk, "Config", None)
        sample_rates = getattr(sdk, "OBGyroSampleRate", None)
        if pipeline_factory is None or config_factory is None or sample_rates is None:
            raise OrbbecCameraError("Orbbec SDK does not provide required IMU pipeline APIs.")
        sample_rate = getattr(sample_rates, f"SAMPLE_RATE_{self._capture_config.imu_hz}_HZ", None)
        if sample_rate is None:
            raise OrbbecCameraError(f"Orbbec SDK does not provide a {self._capture_config.imu_hz} Hz IMU rate.")
        pipeline = pipeline_factory()
        config = config_factory()
        enable_accel = getattr(config, "enable_accel_stream", None)
        enable_gyro = getattr(config, "enable_gyro_stream", None)
        if enable_accel is None or enable_gyro is None:
            raise OrbbecCameraError("Orbbec Config does not provide required IMU stream APIs.")
        self._imu_buffer = ImuBuffer()
        try:
            enable_accel(sample_rate=sample_rate)
            enable_gyro(sample_rate=sample_rate)
            pipeline.start(config, self._handle_imu_frames)
        except Exception as error:
            raise OrbbecCameraError(f"Failed to start Orbbec IMU pipeline: {error}") from error
        self._imu_pipeline = pipeline

    def _handle_imu_frames(self, frames: Any) -> None:
        for sensor_name, getter_name in (("gyro", "get_gyro_frame"), ("accel", "get_accel_frame")):
            getter = getattr(frames, getter_name, None)
            frame = getter() if getter is not None else None
            if frame is not None:
                self._imu_buffer.push(
                    ImuSample(
                        sensor=sensor_name,  # type: ignore[arg-type]
                        timestamp_us=int(frame.get_timestamp_us()),
                        xyz=np.array(
                            [float(frame.get_x()), float(frame.get_y()), float(frame.get_z())],
                            dtype=np.float64,
                        ),
                    )
                )

    def _stop_imu_pipeline(self) -> None:
        if self._imu_pipeline is not None:
            self._imu_pipeline.stop()
        self._imu_pipeline = None

    def _clear_started_state(self) -> None:
        self._stop_imu_pipeline()
        self._pipeline = None
        self._align_filter = None
        self._depth_filters = ()
        self.enabled_depth_filter_names = ()
        self._last_color_timestamp_us = 0

    @staticmethod
    def _build_align_filter(sdk: Any, alignment_target: str) -> Any:
        align_filter_factory = getattr(sdk, "AlignFilter", None)
        stream_type = getattr(sdk, "OBStreamType", None)
        if align_filter_factory is None or stream_type is None:
            raise OrbbecCameraError("Orbbec SDK does not provide RGB-D alignment support.")

        stream_name = "COLOR_STREAM" if alignment_target == "color" else "DEPTH_STREAM"
        target_stream = getattr(stream_type, stream_name, None)
        if target_stream is None:
            raise OrbbecCameraError(f"Orbbec SDK does not provide required {stream_name} API.")
        return align_filter_factory(align_to_stream=target_stream)

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

    @staticmethod
    def _frame_timestamp_us(frame: Any) -> int:
        method = getattr(frame, "get_timestamp_us", None)
        if method is not None:
            return int(method())
        return int(round(OrbbecCapture._frame_timestamp_ms(frame) * 1000.0))
