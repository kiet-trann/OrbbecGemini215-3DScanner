from pathlib import Path


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
