"""Milestone 3: detect ArUco markers and estimate marker pose."""

import _bootstrap  # noqa: F401

import argparse
import time

import cv2

from scanner_app.camera.orbbec_capture import (
    OrbbecCameraError,
    OrbbecCapture,
    OrbbecFrameError,
    OrbbecSdkNotAvailable,
)
from scanner_app.tracking.aruco import detect_markers, draw_marker_detections


WINDOW_NAME = "Gemini 215 ArUco Tracking"
ESC_KEY = 27
STATUS_INTERVAL_SECONDS = 2.0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Track ArUco markers with Orbbec Gemini 215 RGB-D.")
    parser.add_argument("--dictionary", default="DICT_4X4_50")
    parser.add_argument("--marker-size-m", type=float, default=0.06)
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N frames; 0 means unlimited.")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Read and track frames without opening an OpenCV window.",
    )
    return parser


def format_tracking_status(frame_count: int, elapsed_seconds: float, detections) -> str:
    fps = frame_count / elapsed_seconds if elapsed_seconds > 0 else 0.0
    status = f"Marker frames: {frame_count} | {fps:.1f} FPS | markers={len(detections)}"
    if detections:
        detection = detections[0]
        if detection.tvec is not None:
            x, y, z = detection.tvec.reshape(3)
            status += f" | id={detection.marker_id} t=({x:.3f}, {y:.3f}, {z:.3f})m"
        else:
            status += f" | id={detection.marker_id}"
    return status


def main(argv: list[str] | None = None) -> None:
    args = build_argument_parser().parse_args(argv)
    camera = OrbbecCapture(align_to_depth=True)

    try:
        camera.start()
        intrinsics = camera.intrinsics()

        if args.headless:
            print("Headless ArUco marker tracking started.")
        else:
            cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
            print("ArUco marker tracking started. Press Q or ESC to exit.")

        frame_count = 0
        started_at = time.monotonic()
        last_status_at = started_at

        while True:
            frame = camera.read()
            if frame.color is None:
                raise OrbbecFrameError("Color frame missing; marker tracking requires RGB.")

            detections = detect_markers(
                frame.color,
                intrinsics=intrinsics,
                marker_size_m=args.marker_size_m,
                dictionary_name=args.dictionary,
            )
            frame_count += 1

            now = time.monotonic()
            if now - last_status_at >= STATUS_INTERVAL_SECONDS or args.headless:
                print(format_tracking_status(frame_count, now - started_at, detections))
                last_status_at = now

            if not args.headless:
                display = draw_marker_detections(
                    frame.color,
                    detections,
                    intrinsics,
                    marker_size_m=args.marker_size_m,
                )
                cv2.imshow(WINDOW_NAME, display)
                key = cv2.waitKey(1)
                if key in (ord("q"), ord("Q"), ESC_KEY):
                    break

            if args.max_frames > 0 and frame_count >= args.max_frames:
                break

    except OrbbecSdkNotAvailable as error:
        print(error)
    except (OrbbecCameraError, OrbbecFrameError, ValueError) as error:
        print(error)
    finally:
        camera.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
