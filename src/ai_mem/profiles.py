import re
import sqlite3
from pathlib import Path

from ai_mem.db.connection import open_db
from ai_mem.db.schema import migrate

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class UnknownProfile(Exception):
    """Requested profile has no database. Never auto-create — see spec 3.1."""


class InvalidProfileName(Exception):
    """Name is not a safe single path segment."""


class ProfileRegistry:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def _validate(self, name: str) -> str:
        if not _NAME_RE.match(name or ""):
            raise InvalidProfileName(name)
        return name

    def path_for(self, name: str) -> Path:
        return self.data_dir / f"{self._validate(name)}.db"

    def exists(self, name: str) -> bool:
        return self.path_for(name).exists()

    def exists_safe(self, name: str) -> bool:
        """exists(), but an invalid name is simply 'no' rather than an error.

        Used by the HTTP dispatcher, where a malformed profile must produce
        404 rather than a 500.
        """
        try:
            return self.exists(name)
        except InvalidProfileName:
            return False

    def create(self, name: str) -> Path:
        path = self.path_for(name)
        conn = open_db(path)
        try:
            migrate(conn)
        finally:
            conn.close()
        return path

    def list(self) -> list[str]:
        if not self.data_dir.exists():
            return []
        return sorted(p.stem for p in self.data_dir.glob("*.db"))

    def connect(self, name: str) -> sqlite3.Connection:
        if not self.exists(name):
            raise UnknownProfile(name)
        return open_db(self.path_for(name))
