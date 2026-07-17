"""Read-only discovery of saved RTAB-Map databases."""

from datetime import datetime, timezone
import json
from pathlib import Path

from scanner_app.rtabmap.models import SavedSession


class SessionCatalog:
    def __init__(self, session_dir: Path, catalog_path: Path) -> None:
        self._session_dir = session_dir.resolve()
        self._catalog_path = catalog_path.resolve()

    def refresh(self) -> list[SavedSession]:
        sessions = sorted(
            (self._to_session(path) for path in self._session_dir.glob("*.db")),
            key=lambda session: session.modified_at,
            reverse=True,
        )
        payload = {"sessions": [session.to_json() for session in sessions]}
        self._catalog_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._catalog_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self._catalog_path)
        return sessions

    def select(self, path: Path) -> SavedSession:
        resolved = path.resolve()
        if not resolved.is_relative_to(self._session_dir):
            raise ValueError("session database is outside the configured session directory")
        if resolved.suffix.lower() != ".db":
            raise ValueError("session path must have a .db extension")
        if not resolved.is_file():
            raise FileNotFoundError(f"session database does not exist: {resolved}")
        return self._to_session(resolved)

    @staticmethod
    def _to_session(path: Path) -> SavedSession:
        stat = path.stat()
        return SavedSession(
            path=path.resolve(),
            size_bytes=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        )
