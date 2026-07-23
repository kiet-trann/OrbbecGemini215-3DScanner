from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.rtabmap.exporter import ExportRequest, ExportResult, ExportService, build_argument_parser, main
from scanner_app.rtabmap.models import RtabmapPaths


@dataclass(frozen=True)
class FakeCompletedProcess:
    returncode: int
    stdout: str
    stderr: str


class FakeRunner:
    def __init__(self, *, write_texture: bool) -> None:
        self.write_texture = write_texture
        self.args: list[str] | None = None

    def __call__(self, args: list[str], **_kwargs: object) -> FakeCompletedProcess:
        self.args = args
        output_dir = Path(args[args.index("--output_dir") + 1])
        output_stem = args[args.index("--output") + 1]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{output_stem}.obj").write_text(
            "\n".join((
                "mtllib mesh.mtl", "v 0 0 0", "v 1 0 0", "v 0 1 0",
                "vt 0 0", "vt 1 0", "vt 0 1", "vn 0 0 1", "usemtl material",
                "f 1/1/1 2/2/1 3/3/1", "",
            )),
            encoding="utf-8",
        )
        (output_dir / "mesh.mtl").write_text("newmtl material\nmap_Kd texture.jpg\n", encoding="utf-8")
        if self.write_texture:
            assert cv2.imwrite(str(output_dir / "texture.jpg"), np.zeros((64, 64, 3), dtype=np.uint8))
        return FakeCompletedProcess(1, "export complete", "PCL warning after output")


def fixed_clock() -> datetime:
    return datetime(2026, 7, 17, 10, 0, 0)


def test_export_accepts_complete_textured_bundle_even_with_post_export_nonzero_exit(tmp_path: Path) -> None:
    database = tmp_path / "scan.db"
    database.write_bytes(b"source")
    original = database.read_bytes()
    runner = FakeRunner(write_texture=True)
    service = ExportService(exporter=tmp_path / "rtabmap-export.exe", runner=runner, clock=fixed_clock)

    result = service.export(ExportRequest(database=database, output_root=tmp_path / "exports"))

    assert runner.args is not None
    assert runner.args[:3] == [str(service.exporter), "--mesh", "--texture"]
    assert result.error is None
    assert result.obj is not None and result.obj.is_file()
    assert result.mtl is not None and result.mtl.is_file()
    assert [path.name for path in result.textures] == ["texture.jpg"]
    assert result.viewer_model is not None and result.viewer_model.is_file()
    assert result.viewer_model.suffix == ".glb"
    assert result.viewer_model.read_bytes()[:4] == b"glTF"
    assert result.log.is_file()
    assert database.read_bytes() == original


def test_export_reports_missing_texture_without_deleting_raw_output(tmp_path: Path) -> None:
    database = tmp_path / "scan.db"
    database.write_bytes(b"source")
    service = ExportService(
        exporter=tmp_path / "rtabmap-export.exe",
        runner=FakeRunner(write_texture=False),
        clock=fixed_clock,
    )

    result = service.export(ExportRequest(database=database, output_root=tmp_path / "exports"))

    assert result.error == "Export did not produce a texture image"
    assert result.log.is_file()
    assert any(result.output_dir.glob("*.obj"))


def test_exporter_cli_accepts_database_and_output_root() -> None:
    args = build_argument_parser().parse_args(["scan.db", "--output-root", "exports"])

    assert args.database == Path("scan.db")
    assert args.output_root == Path("exports")


def test_exporter_main_uses_resolved_runtime(tmp_path: Path) -> None:
    selected = RtabmapPaths(
        executable=tmp_path / "bin" / "RTABMap.exe",
        exporter=tmp_path / "bin" / "rtabmap-export.exe",
    )
    seen: list[Path] = []

    class FakeService:
        def __init__(self, *, exporter: Path) -> None:
            seen.append(exporter)

        def export(self, request: ExportRequest) -> ExportResult:
            return ExportResult(request.output_root, None, None, (), None, tmp_path / "log", "stop")

    exit_code = main(
        ["scan.db", "--output-root", "exports"],
        project_root=tmp_path,
        resolve_paths=lambda _root: selected,
        service_factory=FakeService,
    )

    assert exit_code == 2
    assert seen == [selected.exporter]
