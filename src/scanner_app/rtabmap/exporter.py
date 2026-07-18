"""Native RTAB-Map textured-mesh export with artifact validation."""

import argparse
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
import subprocess

from scanner_app.rtabmap.viewer_bundle import create_3d_viewer_bundle


@dataclass(frozen=True)
class ExportRequest:
    database: Path
    output_root: Path


@dataclass(frozen=True)
class ExportResult:
    output_dir: Path
    obj: Path | None
    mtl: Path | None
    textures: tuple[Path, ...]
    viewer_obj: Path | None
    log: Path
    error: str | None


Runner = Callable[..., subprocess.CompletedProcess[str]]


class ExportService:
    def __init__(
        self,
        *,
        exporter: Path,
        runner: Runner = subprocess.run,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.exporter = exporter
        self._runner = runner
        self._clock = clock

    def export(self, request: ExportRequest) -> ExportResult:
        database = request.database.resolve()
        output_dir = (
            request.output_root.resolve()
            / f"{database.stem}_{self._clock().strftime('%Y%m%d_%H%M%S')}"
            / "raw"
        )
        output_dir.mkdir(parents=True, exist_ok=False)
        log_path = output_dir / "export.log"
        command = [
            str(self.exporter),
            "--mesh",
            "--texture",
            "--output",
            database.stem,
            "--output_dir",
            str(output_dir),
            str(database),
        ]
        completed = self._runner(command, cwd=self.exporter.parent, capture_output=True, text=True)
        log_path.write_text(
            (completed.stdout or "") + (completed.stderr or ""),
            encoding="utf-8",
        )
        result = self._validate(output_dir, log_path, completed.returncode)
        if result.error is not None or result.obj is None:
            return result
        try:
            viewer = create_3d_viewer_bundle(result.obj, output_dir.parent / "viewer")
        except (OSError, ValueError) as error:
            return replace(result, error=f"3D Viewer bundle failed: {error}")
        return replace(result, viewer_obj=viewer.obj)

    @staticmethod
    def _validate(output_dir: Path, log_path: Path, returncode: int) -> ExportResult:
        obj = next(iter(sorted(output_dir.glob("*.obj"))), None)
        mtl = next(iter(sorted(output_dir.glob("*.mtl"))), None)
        if obj is None:
            return ExportResult(output_dir, None, mtl, (), None, log_path, f"Export did not produce an OBJ (exit {returncode})")
        if mtl is None:
            return ExportResult(output_dir, obj, None, (), None, log_path, "Export did not produce an MTL file")
        textures = tuple(_referenced_textures(mtl))
        if not textures:
            return ExportResult(output_dir, obj, mtl, (), None, log_path, "Export did not produce a texture image")
        return ExportResult(output_dir, obj, mtl, textures, None, log_path, None)


def _referenced_textures(mtl: Path) -> list[Path]:
    textures: list[Path] = []
    for line in mtl.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.lower().startswith("map_kd "):
            continue
        candidate = (mtl.parent / line.split(maxsplit=1)[1]).resolve()
        if candidate.suffix.lower() in {".jpg", ".jpeg", ".png"} and candidate.is_file():
            textures.append(candidate)
    return textures


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a textured OBJ from a saved RTAB-Map database.")
    parser.add_argument("database", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    exporter = Path(__file__).resolve().parents[3] / "third_party" / "rtabmap" / "RTABMap-0.23.1-win64" / "bin" / "rtabmap-export.exe"
    result = ExportService(exporter=exporter).export(
        ExportRequest(database=args.database, output_root=args.output_root)
    )
    print(result.log)
    return 0 if result.error is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
