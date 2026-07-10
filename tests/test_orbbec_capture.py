import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.camera.models import CaptureConfig
from scanner_app.camera.orbbec_capture import CameraIntrinsics, OrbbecCameraError, OrbbecCapture


class FakeDepthFrame:
    def __init__(self) -> None:
        self.data = np.array([[100, 200], [0, 300]], dtype=np.uint16)

    def get_width(self) -> int:
        return 2

    def get_height(self) -> int:
        return 2

    def get_depth_scale(self) -> float:
        return 0.5

    def get_data(self) -> bytes:
        return self.data.tobytes()


class FakeColorFrame:
    def __init__(self) -> None:
        self.data = np.arange(12, dtype=np.uint8).reshape(2, 2, 3)

    def get_width(self) -> int:
        return 2

    def get_height(self) -> int:
        return 2


class FakeFrameSet:
    def __init__(self) -> None:
        self.color_frame = FakeColorFrame()
        self.depth_frame = FakeDepthFrame()

    def get_color_frame(self) -> FakeColorFrame:
        return self.color_frame

    def get_depth_frame(self) -> FakeDepthFrame:
        return self.depth_frame


class FakeIntrinsic:
    fx = 500.0
    fy = 501.0
    cx = 320.0
    cy = 240.0
    width = 640
    height = 480


class FakeCameraParam:
    depth_intrinsic = FakeIntrinsic()


class FakePipeline:
    def __init__(
        self,
        depth_profiles: "FakeVideoProfileList | None" = None,
        color_profiles: "FakeVideoProfileList | None" = None,
    ) -> None:
        self.started = False
        self.stopped = False
        self.frame_sync_enabled = False
        self.wait_timeout_ms = None
        self.start_config = None
        self.device = FakeDevice()
        self.depth_profiles = depth_profiles or FakeVideoProfileList("depth-profile")
        self.color_profiles = color_profiles or FakeVideoProfileList("color-profile")

    def start(self, config=None) -> None:
        self.started = True
        self.start_config = config

    def get_stream_profile_list(self, sensor_type: str) -> "FakeVideoProfileList":
        if sensor_type == "depth":
            return self.depth_profiles
        return self.color_profiles

    def get_device(self) -> "FakeDevice":
        return self.device

    def enable_frame_sync(self) -> None:
        self.frame_sync_enabled = True

    def wait_for_frames(self, timeout_ms: int) -> FakeFrameSet:
        self.wait_timeout_ms = timeout_ms
        return FakeFrameSet()

    def get_camera_param(self) -> FakeCameraParam:
        return FakeCameraParam()

    def stop(self) -> None:
        self.stopped = True


class FakeSdk:
    class OBSensorType:
        DEPTH_SENSOR = "depth"
        COLOR_SENSOR = "color"

    class OBFrameAggregateOutputMode:
        FULL_FRAME_REQUIRE = "full-frame-require"

    class OBStreamType:
        DEPTH_STREAM = "depth-stream"

    class OBFormat:
        Y16 = "y16"
        RGB = "rgb"

    def __init__(self) -> None:
        self.depth_profiles = FakeVideoProfileList("depth-profile")
        self.color_profiles = FakeVideoProfileList("color-profile")
        self.pipeline = FakePipeline(self.depth_profiles, self.color_profiles)
        self.config = FakeConfig()
        self.align_filter = None

    def Pipeline(self) -> FakePipeline:
        return self.pipeline

    def Config(self):
        return self.config

    def AlignFilter(self, align_to_stream):
        self.align_filter = FakeAlignFilter(align_to_stream)
        return self.align_filter


class FakeAlignFilter:
    def __init__(self, align_to_stream) -> None:
        self.align_to_stream = align_to_stream
        self.processed_frames = None

    def process(self, frames):
        self.processed_frames = frames
        return frames


class FakeVideoProfileList:
    def __init__(self, profile) -> None:
        self.profile = profile
        self.requests = []

    def get_default_video_stream_profile(self):
        return self.profile

    def get_video_stream_profile(self, width, height, frame_format, fps):
        self.requests.append((width, height, frame_format, fps))
        return f"{self.profile}-rgb" if frame_format == "rgb" else self.profile


class FakeDepthWorkMode:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeDepthWorkModeList:
    def __init__(self) -> None:
        self.modes = (
            FakeDepthWorkMode("Default Mode"),
            FakeDepthWorkMode("Close_Up Precision Mode"),
        )

    def get_count(self) -> int:
        return len(self.modes)

    def get_depth_work_mode_by_index(self, index: int) -> FakeDepthWorkMode:
        return self.modes[index]


class FakeDepthFilter:
    def __init__(self, name: str, enabled: bool) -> None:
        self.name = name
        self.enabled = enabled
        self.processed_frame = None

    def is_enabled(self) -> bool:
        return self.enabled

    def get_name(self) -> str:
        return self.name

    def process(self, depth_frame):
        self.processed_frame = depth_frame
        return FakeFilteredDepthFrame(depth_frame)


class FakeFilteredDepthFrame:
    def __init__(self, depth_frame) -> None:
        self.depth_frame = depth_frame

    def as_depth_frame(self):
        return self.depth_frame


class FakeDepthSensor:
    def __init__(self) -> None:
        self.filters = (
            FakeDepthFilter("TemporalFilter", True),
            FakeDepthFilter("DisabledFilter", False),
        )

    def get_recommended_filters(self):
        return self.filters


class FakeDevice:
    def __init__(self) -> None:
        self.depth_modes = FakeDepthWorkModeList()
        self.selected_depth_mode = "Default Mode"
        self.depth_sensor = FakeDepthSensor()

    def get_depth_work_mode_list(self) -> FakeDepthWorkModeList:
        return self.depth_modes

    def get_depth_work_mode(self) -> FakeDepthWorkMode:
        return FakeDepthWorkMode(self.selected_depth_mode)

    def set_depth_work_mode(self, mode: FakeDepthWorkMode) -> None:
        self.selected_depth_mode = mode.name

    def get_sensor(self, sensor_type: str) -> FakeDepthSensor:
        if sensor_type != "depth":
            raise AssertionError(f"Unexpected sensor requested: {sensor_type}")
        return self.depth_sensor


class FakeConfig:
    def __init__(self) -> None:
        self.enabled_profiles = []
        self.frame_aggregate_output_mode = None

    def enable_stream(self, profile) -> None:
        self.enabled_profiles.append(profile)

    def set_frame_aggregate_output_mode(self, mode) -> None:
        self.frame_aggregate_output_mode = mode


class FailingPipeline:
    def start(self, config=None) -> None:
        raise RuntimeError("No device found")


class FailingSdk:
    def Pipeline(self) -> FailingPipeline:
        return FailingPipeline()


class FakeEmptyDeviceList:
    def get_count(self) -> int:
        return 0


class FakeContextWithoutDevices:
    def query_devices(self) -> FakeEmptyDeviceList:
        return FakeEmptyDeviceList()


class FakePipelineShouldNotStart:
    def start(self) -> None:
        raise AssertionError("Pipeline.start should not be called without devices")


class NoDeviceSdk:
    def Context(self) -> FakeContextWithoutDevices:
        return FakeContextWithoutDevices()

    def Pipeline(self) -> FakePipelineShouldNotStart:
        return FakePipelineShouldNotStart()


class OrbbecCaptureTests(unittest.TestCase):
    def test_start_uses_explicit_30_fps_rgbd_profiles_and_enables_sync(self) -> None:
        sdk = FakeSdk()
        capture = OrbbecCapture(sdk_module=sdk, capture_config=CaptureConfig())

        capture.start()

        self.assertTrue(sdk.pipeline.frame_sync_enabled)
        self.assertIn((1280, 800, "y16", 30), sdk.depth_profiles.requests)
        self.assertIn((1280, 720, "rgb", 30), sdk.color_profiles.requests)
        self.assertEqual(sdk.pipeline.device.selected_depth_mode, "Close_Up Precision Mode")
        self.assertEqual(capture.enabled_depth_filter_names, ("TemporalFilter",))

    def test_start_configures_depth_stream_before_starting_pipeline(self) -> None:
        sdk = FakeSdk()

        capture = OrbbecCapture(sdk_module=sdk)

        capture.start()

        self.assertIs(sdk.pipeline.start_config, sdk.config)
        self.assertIn("depth-profile", sdk.config.enabled_profiles)

    def test_start_requires_full_rgbd_frame_sets_when_sdk_supports_it(self) -> None:
        sdk = FakeSdk()

        capture = OrbbecCapture(sdk_module=sdk)

        capture.start()

        self.assertEqual(sdk.config.frame_aggregate_output_mode, "full-frame-require")

    def test_start_prefers_rgb_color_profile_when_sdk_supports_it(self) -> None:
        sdk = FakeSdk()

        capture = OrbbecCapture(sdk_module=sdk)

        capture.start()

        self.assertIn("color-profile-rgb", sdk.config.enabled_profiles)

    def test_start_read_intrinsics_and_stop_use_sdk_pipeline(self) -> None:
        sdk = FakeSdk()
        capture = OrbbecCapture(
            sdk_module=sdk,
            color_frame_converter=lambda frame: frame.data,
            timeout_ms=123,
        )

        capture.start()
        frame = capture.read()
        intrinsics = capture.intrinsics()
        capture.stop()

        self.assertTrue(sdk.pipeline.started)
        self.assertTrue(sdk.pipeline.stopped)
        self.assertEqual(sdk.pipeline.wait_timeout_ms, 123)
        self.assertIsNotNone(sdk.pipeline.device.depth_sensor.filters[0].processed_frame)
        self.assertIsNone(sdk.pipeline.device.depth_sensor.filters[1].processed_frame)
        np.testing.assert_array_equal(frame.color, np.arange(12, dtype=np.uint8).reshape(2, 2, 3))
        np.testing.assert_array_equal(
            frame.depth,
            np.array([[100, 200], [0, 300]], dtype=np.uint16),
        )
        self.assertEqual(frame.depth_scale, 0.5)
        self.assertIsInstance(intrinsics, CameraIntrinsics)
        self.assertEqual(intrinsics.fx, 500.0)
        self.assertEqual(capture.depth_scale(), 0.5)

    def test_align_to_depth_processes_frame_set_before_reading_frames(self) -> None:
        sdk = FakeSdk()
        capture = OrbbecCapture(
            sdk_module=sdk,
            color_frame_converter=lambda frame: frame.data,
            align_to_depth=True,
        )

        capture.start()
        capture.read()

        self.assertIsNotNone(sdk.align_filter)
        self.assertEqual(sdk.align_filter.align_to_stream, "depth-stream")
        self.assertIsInstance(sdk.align_filter.processed_frames, FakeFrameSet)

    def test_start_creates_sdk_log_directory_and_wraps_sdk_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("os.getcwd", return_value=temp_dir):
                capture = OrbbecCapture(sdk_module=FailingSdk())

                with self.assertRaisesRegex(OrbbecCameraError, "No device found"):
                    capture.start()

                self.assertTrue((Path(temp_dir) / "Log").is_dir())

    def test_start_fails_before_pipeline_when_no_orbbec_devices_are_connected(self) -> None:
        capture = OrbbecCapture(sdk_module=NoDeviceSdk())

        with self.assertRaisesRegex(OrbbecCameraError, "No Orbbec device found"):
            capture.start()


if __name__ == "__main__":
    unittest.main()
