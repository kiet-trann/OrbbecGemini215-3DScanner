"""Milestone 1: display RGB and depth frames from Gemini 215."""

import _bootstrap  # noqa: F401

from scanner_app.camera.orbbec_capture import OrbbecCapture


def main() -> None:
    camera = OrbbecCapture()
    camera.start()
    try:
        raise NotImplementedError("Display RGB/depth with OpenCV windows.")
    finally:
        camera.stop()


if __name__ == "__main__":
    main()
