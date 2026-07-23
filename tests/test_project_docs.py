from pathlib import Path
import tomllib


def test_readmes_explain_the_default_3d_viewer_bundle() -> None:
    for name in ("README.md", "README.en.md"):
        text = Path(name).read_text(encoding="utf-8")
        assert "4096" in text
        assert "GLB" in text
        assert "viewer" in text.lower()
        assert "raw" in text.lower()


def test_rtabmap_runtime_selection_is_documented_and_centralized() -> None:
    runtime_source = Path("src/scanner_app/rtabmap/runtime.py").read_text(encoding="utf-8")

    assert "SCANNER_RTABMAP_VERSION" in runtime_source
    assert '"0.23.8"' in runtime_source
    assert '"0.23.1"' in runtime_source

    for source in Path("src/scanner_app").rglob("*.py"):
        if source.name == "runtime.py":
            continue
        assert "RTABMap-0.23.1-win64" not in source.read_text(encoding="utf-8")


def test_rtabmap_runtime_rollback_and_native_regressions_are_documented() -> None:
    readmes = {
        name: Path(name).read_text(encoding="utf-8")
        for name in ("README.md", "README.en.md")
    }

    for text in readmes.values():
        assert "RTABMap-0.23.8-win64" in text
        assert "RTABMap-0.23.1-win64" in text
        assert "0.23.8" in text and "default" in text.lower()
        assert "Gemini 215" in text and "1.0.9" in text
        assert "$env:SCANNER_RTABMAP_VERSION='0.23.1'" in text
        assert "Remove-Item Env:SCANNER_RTABMAP_VERSION -ErrorAction SilentlyContinue" in text
        assert "RTABMAP_INTEGRATION_DB" in text
        assert "RTABMAP_GUI_SMOKE" in text
        assert "tests\\test_rtabmap_runtime_integration.py" in text

    assert "database nguồn" in readmes["README.md"].lower()
    assert "không thay đổi" in readmes["README.md"].lower()
    assert "source database" in readmes["README.en.md"].lower()
    assert "unchanged" in readmes["README.en.md"].lower()


def test_readmes_document_the_actual_0238_portable_runtime_dependencies() -> None:
    readmes = {
        name: Path(name).read_text(encoding="utf-8")
        for name in ("README.md", "README.en.md")
    }

    for text in readmes.values():
        assert "| OrbbecSDK | 2.8.7 |" in text
        assert "| OpenCV | 4.12.0 |" in text
        assert "| PCL | 1.15.1 |" in text
        assert "| VTK | 9.3.20231030 |" in text
        assert "OpenCV 4.13.0" in text
        assert "PCL 1.15.0" in text
        assert "release" in text.lower()


def test_pytest_registers_the_native_integration_marker() -> None:
    configuration = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    markers = configuration["tool"]["pytest"]["ini_options"]["markers"]
    assert any(marker.startswith("integration:") for marker in markers)


def test_readmes_document_gemini_usb3_preflight_and_cli_limitation() -> None:
    vietnamese = Path("README.md").read_text(encoding="utf-8")
    english = Path("README.en.md").read_text(encoding="utf-8")

    for readme in (vietnamese, english):
        assert "USB2.0" in readme
        assert "USB3.0" in readme
        assert "opencv_highgui4.dll" in readme
        assert "rtabmap-rgbd_camera.exe" in readme
        assert "Orbbec SDK" in readme
        assert "More Options" in readme

    assert "chọn nguồn Orbbec Gemini 215" not in vietnamese
    assert "select the Orbbec Gemini 215 source" not in english
