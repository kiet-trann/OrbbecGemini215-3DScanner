"""Milestone 1: display RGB and depth frames from Gemini 215."""

import _bootstrap  # noqa: F401

import time

import cv2
import numpy as np

from scanner_app.camera.orbbec_capture import (
    OrbbecCameraError,
    OrbbecCapture,
    OrbbecFrameError,
    OrbbecSdkNotAvailable,
)


WINDOW_NAME = "Gemini 215 RGB-D Viewer"
ESC_KEY = 27
MIN_DEPTH_MM = 150
MAX_DEPTH_MM = 700
STATUS_INTERVAL_SECONDS = 2.0


def render_depth(depth_mm: np.ndarray) -> np.ndarray:
    clipped = np.clip(depth_mm, MIN_DEPTH_MM, MAX_DEPTH_MM)
    normalized = (clipped - MIN_DEPTH_MM) / (MAX_DEPTH_MM - MIN_DEPTH_MM)
    depth_8bit = (normalized * 255).astype(np.uint8)
    return cv2.applyColorMap(depth_8bit, cv2.COLORMAP_JET)


def format_frame_status(frame_count: int, elapsed_seconds: float, frame) -> str:
    fps = frame_count / elapsed_seconds if elapsed_seconds > 0 else 0.0
    color_shape = None if frame.color is None else frame.color.shape
    return (
        f"RGB-D frames: {frame_count} | {fps:.1f} FPS | "
        f"depth={frame.depth.shape} scale={frame.depth_scale} | color={color_shape}"
    )


def main() -> None:
    camera = OrbbecCapture()
    try:
        camera.start()
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW_NAME, 1280, 480)
        print("Gemini 215 viewer started. Press Q or ESC to exit.")

        frame_count = 0
        started_at = time.monotonic()
        last_status_at = started_at

        while True:
            try:
                frame = camera.read()
            except OrbbecFrameError as error:
                print(f"Frame warning: {error}")
                continue

            frame_count += 1
            now = time.monotonic()
            if now - last_status_at >= STATUS_INTERVAL_SECONDS:
                print(format_frame_status(frame_count, now - started_at, frame))
                last_status_at = now

            color = frame.color
            if color is None:
                color = np.zeros((*frame.depth.shape, 3), dtype=np.uint8)

            depth_view = render_depth(frame.depth_mm)
            display_height = 480
            display_width = 640
            color = cv2.resize(color, (display_width, display_height))
            depth_view = cv2.resize(depth_view, (display_width, display_height))
            combined = np.hstack((color, depth_view))

            cv2.imshow(WINDOW_NAME, combined)
            key = cv2.waitKey(1)
            if key in (ord("q"), ord("Q"), ESC_KEY):
                break
    except OrbbecSdkNotAvailable as error:
        print(error)
    except OrbbecCameraError as error:
        print(error)
        print("Check USB 3.0 connection, camera power, Orbbec driver/runtime, and Orbbec Viewer.")
    finally:
        camera.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
