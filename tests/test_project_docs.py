from pathlib import Path


def test_readmes_explain_the_default_3d_viewer_bundle() -> None:
    for name in ("README.md", "README.en.md"):
        text = Path(name).read_text(encoding="utf-8")
        assert "4096" in text
        assert "viewer" in text.lower()
        assert "raw" in text.lower()
