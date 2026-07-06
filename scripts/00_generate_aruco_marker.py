"""Generate printable ArUco markers for prototype tracking tests."""

import _bootstrap  # noqa: F401

import argparse
from pathlib import Path

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "calibration"


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a printable ArUco marker PNG.")
    parser.add_argument("--dictionary", default="DICT_4X4_50")
    parser.add_argument("--id", type=int, default=0)
    parser.add_argument("--marker-size-px", type=int, default=800)
    parser.add_argument("--border-px", type=int, default=160)
    parser.add_argument("--output", type=Path, default=None)
    return parser


def build_output_path(
    dictionary_name: str,
    *,
    marker_id: int,
    marker_size_px: int,
) -> Path:
    return OUTPUT_DIR / f"aruco_{dictionary_name}_id{marker_id}_{marker_size_px}px.png"


def generate_marker_image(
    *,
    dictionary_name: str,
    marker_id: int,
    marker_size_px: int,
    border_px: int,
) -> np.ndarray:
    dictionary_id = getattr(cv2.aruco, dictionary_name, None)
    if dictionary_id is None:
        raise ValueError(f"Unknown ArUco dictionary: {dictionary_name}")

    dictionary = cv2.aruco.getPredefinedDictionary(dictionary_id)
    marker = cv2.aruco.generateImageMarker(dictionary, marker_id, marker_size_px)
    image = np.full(
        (marker_size_px + border_px * 2, marker_size_px + border_px * 2),
        255,
        dtype=np.uint8,
    )
    image[border_px : border_px + marker_size_px, border_px : border_px + marker_size_px] = marker
    return image


def write_marker_image(output_path: str | Path, image: np.ndarray) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Failed to write marker image: {path}")


def main(argv: list[str] | None = None) -> None:
    args = build_argument_parser().parse_args(argv)
    output_path = args.output or build_output_path(
        args.dictionary,
        marker_id=args.id,
        marker_size_px=args.marker_size_px,
    )
    image = generate_marker_image(
        dictionary_name=args.dictionary,
        marker_id=args.id,
        marker_size_px=args.marker_size_px,
        border_px=args.border_px,
    )
    write_marker_image(output_path, image)
    print(f"Saved ArUco marker {args.dictionary} id={args.id} to: {output_path}")


if __name__ == "__main__":
    main()
