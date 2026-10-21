from app import config
from app.config import Settings


def test_dev_uses_plain_env_credentials():
    settings = Settings(environment="DEV", mssql_username="sa", mssql_password="pw")
    assert settings.is_dev
    assert settings.db_credentials() == ("sa", "pw")
    conn = settings.connection_string()
    assert "UID=sa" in conn and "PWD=pw" in conn


def test_non_dev_fetches_credentials_from_secret_manager(monkeypatch):
    calls = []

    def fake_secret(secret_id):
        calls.append(secret_id)
        return {"sm-user": "uat_user", "sm-pass": "uat_pass"}[secret_id]

    monkeypatch.setattr(config, "get_gcp_secret", fake_secret)
    settings = Settings(
        environment="UAT",
        mssql_username_secret_id="sm-user",
        mssql_password_secret_id="sm-pass",
    )
    assert not settings.is_dev
    assert settings.db_credentials() == ("uat_user", "uat_pass")
    assert calls == ["sm-user", "sm-pass"]
    assert "UID=uat_user" in settings.connection_string()
