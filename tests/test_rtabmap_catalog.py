import json
from pathlib import Path

import pytest

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.rtabmap.catalog import SessionCatalog


def test_refresh_discovers_databases_without_writing_them(tmp_path: Path) -> None:
    database = tmp_path / "scan_box.db"
    database.write_bytes(b"sqlite-data")
    original_mtime = database.stat().st_mtime_ns
    catalog_path = tmp_path / "scanner_3d_catalog.json"
    catalog = SessionCatalog(tmp_path, catalog_path)

    sessions = catalog.refresh()

    assert [session.path.name for session in sessions] == ["scan_box.db"]
    assert database.stat().st_mtime_ns == original_mtime
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert payload["sessions"][0]["path"].endswith("scan_box.db")


def test_select_rejects_database_outside_the_configured_session_directory(tmp_path: Path) -> None:
    session_directory = tmp_path / "sessions"
    session_directory.mkdir()
    outside = tmp_path / "outside.db"
    outside.write_bytes(b"sqlite-data")
    catalog = SessionCatalog(session_directory, tmp_path / "catalog.json")

    with pytest.raises(ValueError, match="outside the configured session directory"):
        catalog.select(outside)
