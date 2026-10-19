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
    default_row_limit: int = _int_env("DEFAULT_ROW_LIMIT", 5000)
    max_row_limit: int = _int_env("MAX_ROW_LIMIT", 50000)

    def __post_init__(self) -> None:
        if not _IDENT_RE.match(self.table):
            raise ValueError(f"Invalid LIVE_PHOTO_TABLE identifier: {self.table!r}")

    def connection_string(self) -> str:
        return (
            f"DRIVER={{{self.odbc_driver}}};SERVER={self.mssql_server};"
            f"DATABASE={self.mssql_database};UID={self.mssql_username};"
            f"PWD={self.mssql_password};TrustServerCertificate=yes;Encrypt=yes;"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
