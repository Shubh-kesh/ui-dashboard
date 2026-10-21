"""Backend configuration, read from environment (optionally via .env).

Database credentials follow the workspace convention:
  * ``ENVIRONMENT=DEV`` (default) -> plain ``MSSQL_USERNAME`` / ``MSSQL_PASSWORD``
    env values, which is what local Docker/Azure SQL Edge uses.
  * any other environment (UAT/PROD) -> username/password are fetched from
    GCP Secret Manager via the GKE metadata server. The pod service account
    needs ``roles/secretmanager.secretAccessor`` on the configured secrets.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from functools import lru_cache

try:  # optional: load backend/.env in local dev
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")

TABLE_KEYS = ("live", "archive")

_METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/"
    "instance/service-accounts/default/token"
)
_GCP_SECRET_CACHE: dict[str, str] = {}


def _http_json(url: str, headers: dict[str, str], timeout: int = 5) -> dict:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_gcp_secret(secret_id: str) -> str:
    """Fetch the latest version of a GCP Secret Manager secret (cached).

    Uses the GKE metadata server for the access token, so no key file is
    needed. Raises RuntimeError with an actionable message on failure.
    """
    if secret_id in _GCP_SECRET_CACHE:
        return _GCP_SECRET_CACHE[secret_id]

    project = os.getenv("GCP_PROJECT_ID", "").strip()
    location = os.getenv("GCP_LOCATION", "").strip()
    if not project or not location:
        raise RuntimeError(
            f"Cannot fetch secret '{secret_id}': GCP_PROJECT_ID and GCP_LOCATION "
            "must be set (non-DEV environments)."
        )
    try:
        token = _http_json(_METADATA_TOKEN_URL, {"Metadata-Flavor": "Google"})["access_token"]
        url = (
            f"https://secretmanager.{location}.rep.googleapis.com/v1/projects/"
            f"{project}/locations/{location}/secrets/{secret_id}/versions/latest:access"
        )
        body = _http_json(url, {"Authorization": f"Bearer {token}"})
        value = base64.b64decode(body["payload"]["data"]).decode("utf-8")
    except Exception as exc:  # pragma: no cover - requires GCP metadata server
        raise RuntimeError(
            f"Failed to fetch secret '{secret_id}' from Secret Manager: {exc}. "
            "Check GCP_PROJECT_ID/GCP_LOCATION and the pod service account's "
            "Secret Accessor binding."
        ) from exc

    _GCP_SECRET_CACHE[secret_id] = value
    return value


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("ENVIRONMENT", "DEV")
    mssql_server: str = os.getenv("MSSQL_SERVER", "localhost,1433")
    mssql_database: str = os.getenv("MSSQL_DATABASE", "docai")
    mssql_username: str = os.getenv("MSSQL_USERNAME", "sa")
    mssql_password: str = os.getenv("MSSQL_PASSWORD", "LocalDev123!")
    odbc_driver: str = os.getenv("ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
    table: str = os.getenv("LIVE_PHOTO_TABLE", "LIVE_PHOTO_LOGS")
    archive_table: str = os.getenv("LIVE_PHOTO_ARCHIVE_TABLE", "LIVE_PHOTO_LOGS_ARCHIVE")
    live_window_days: int = _int_env("LIVE_WINDOW_DAYS", 7)
    # GCP Secret Manager knobs (ignored in DEV).
    gcp_project_id: str = os.getenv("GCP_PROJECT_ID", "")
    gcp_location: str = os.getenv("GCP_LOCATION", "")
    mssql_username_secret_id: str = os.getenv(
        "MSSQL_USERNAME_SECRET_ID", "sm-aikyc-uat-db-username")
    mssql_password_secret_id: str = os.getenv(
        "MSSQL_PASSWORD_SECRET_ID", "sm-aikyc-uat-db-password")

    def __post_init__(self) -> None:
        for name, value in (("LIVE_PHOTO_TABLE", self.table),
                            ("LIVE_PHOTO_ARCHIVE_TABLE", self.archive_table)):
            if not _IDENT_RE.match(value):
                raise ValueError(f"Invalid {name} identifier: {value!r}")

    @property
    def is_dev(self) -> bool:
        return self.environment.strip().upper() == "DEV"

    def table_for(self, key: str) -> str:
        """Resolve a table selector ('live' | 'archive') to a table name."""
        if key not in TABLE_KEYS:
            raise ValueError(f"unknown table selector {key!r}; expected one of {TABLE_KEYS}")
        return self.table if key == "live" else self.archive_table

    def db_credentials(self) -> tuple[str, str]:
        """(username, password): env in DEV, Secret Manager otherwise."""
        if self.is_dev:
            return self.mssql_username, self.mssql_password
        username = get_gcp_secret(self.mssql_username_secret_id)
        password = get_gcp_secret(self.mssql_password_secret_id)
        if not username or not password:
            raise RuntimeError(
                "Secret Manager returned an empty DB credential "
                f"('{self.mssql_username_secret_id}'/'{self.mssql_password_secret_id}')."
            )
        return username, password

    def validate_credentials(self) -> None:
        """Resolve credentials at startup so a misconfigured pod fails fast."""
        if not self.is_dev:
            self.db_credentials()

    def connection_string(self) -> str:
        username, password = self.db_credentials()
        return (
            f"DRIVER={{{self.odbc_driver}}};SERVER={self.mssql_server};"
            f"DATABASE={self.mssql_database};UID={username};"
            f"PWD={password};TrustServerCertificate=yes;Encrypt=yes;"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
