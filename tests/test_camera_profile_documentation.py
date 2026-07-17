from pathlib import Path


def test_readme_describes_preflight_and_mode_lock() -> None:
    text = Path("README.md").read_text(encoding="utf-8")

    assert "Apply & Open RTAB-Map" in text
    assert "không thể đổi" in text
    assert "chế độ" in text


def test_english_readme_describes_preflight_and_mode_lock() -> None:
    text = Path("README.en.md").read_text(encoding="utf-8")

    assert "Apply & Open RTAB-Map" in text
    assert "cannot change the profile" in text
