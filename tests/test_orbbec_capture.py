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
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.wait_timeout_ms = None

    def start(self) -> None:
        self.started = True

    def wait_for_frames(self, timeout_ms: int) -> FakeFrameSet:
        self.wait_timeout_ms = timeout_ms
        return FakeFrameSet()

    def get_camera_param(self) -> FakeCameraParam:
        return FakeCameraParam()

    def stop(self) -> None:
        self.stopped = True


class FakeSdk:
    def __init__(self) -> None:
        self.pipeline = FakePipeline()

    def Pipeline(self) -> FakePipeline:
        return self.pipeline


class FailingPipeline:
    def start(self) -> None:
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
        np.testing.assert_array_equal(frame.color, np.arange(12, dtype=np.uint8).reshape(2, 2, 3))
        np.testing.assert_array_equal(
            frame.depth,
            np.array([[100, 200], [0, 300]], dtype=np.uint16),
        )
        self.assertEqual(frame.depth_scale, 0.5)
        self.assertIsInstance(intrinsics, CameraIntrinsics)
        self.assertEqual(intrinsics.fx, 500.0)
        self.assertEqual(capture.depth_scale(), 0.5)

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
