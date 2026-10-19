"""Backend configuration, read from environment (optionally via .env)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache

try:  # optional: load backend/.env in local dev
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")

TABLE_KEYS = ("live", "archive")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    mssql_server: str = os.getenv("MSSQL_SERVER", "localhost,1433")
    mssql_database: str = os.getenv("MSSQL_DATABASE", "docai")
    mssql_username: str = os.getenv("MSSQL_USERNAME", "sa")
    mssql_password: str = os.getenv("MSSQL_PASSWORD", "LocalDev123!")
    odbc_driver: str = os.getenv("ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
    table: str = os.getenv("LIVE_PHOTO_TABLE", "LIVE_PHOTO_LOGS")
    archive_table: str = os.getenv("LIVE_PHOTO_ARCHIVE_TABLE", "LIVE_PHOTO_LOGS_ARCHIVE")
    live_window_days: int = _int_env("LIVE_WINDOW_DAYS", 7)

    def __post_init__(self) -> None:
        for name, value in (("LIVE_PHOTO_TABLE", self.table),
                            ("LIVE_PHOTO_ARCHIVE_TABLE", self.archive_table)):
            if not _IDENT_RE.match(value):
                raise ValueError(f"Invalid {name} identifier: {value!r}")

    def table_for(self, key: str) -> str:
        """Resolve a table selector ('live' | 'archive') to a table name."""
        if key not in TABLE_KEYS:
            raise ValueError(f"unknown table selector {key!r}; expected one of {TABLE_KEYS}")
        return self.table if key == "live" else self.archive_table

    def connection_string(self) -> str:
        return (
            f"DRIVER={{{self.odbc_driver}}};SERVER={self.mssql_server};"
            f"DATABASE={self.mssql_database};UID={self.mssql_username};"
            f"PWD={self.mssql_password};TrustServerCertificate=yes;Encrypt=yes;"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
