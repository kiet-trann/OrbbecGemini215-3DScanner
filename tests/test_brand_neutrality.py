from __future__ import annotations

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_TOP_LEVEL_DIRECTORIES = {"third_party", "outputs"}


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
    )
    return [
        Path(path)
        for path in result.stdout.decode("utf-8").split("\0")
        if path and Path(path).parts[0] not in EXCLUDED_TOP_LEVEL_DIRECTORIES
    ]


def test_tracked_tree_contains_no_protected_former_brand() -> None:
    protected_former_brand = "ID" + "EA"
    matches: list[str] = []

    for relative_path in _tracked_files():
        if protected_former_brand.casefold() in relative_path.as_posix().casefold():
            matches.append(relative_path.as_posix())
            continue
        if protected_former_brand.casefold() in (PROJECT_ROOT / relative_path).read_text(
            encoding="utf-8", errors="ignore"
        ).casefold():
            matches.append(relative_path.as_posix())

    assert not matches, "Protected former-brand references remain:\n" + "\n".join(matches)
