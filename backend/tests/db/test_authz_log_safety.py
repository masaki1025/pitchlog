"""実 DB の認証関数呼び出しでアプリとドライバのログを確認する。"""

import base64
import logging
import secrets
from uuid import UUID

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy.engine import URL

from pitchlog.authz.token_presentation import TokenPresentation
from pitchlog.authz.verified_tenant import logout_token, verify_tenant_id
from pitchlog.db.engine import create_database_engine

from .conftest import ProvisionedProductCatalog
from .test_product_authz_authn_app import (
    _app_dsn,
    _login,
    _seed_identity,
    _seed_settings,
)

pytestmark = pytest.mark.requires_db


def test_real_driver_and_engine_logs_omit_auth_material(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """実際の照合・ログアウト時に SQL とドライバのログを採取する。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    identity = _seed_identity(catalog, app_dsn)
    token_id = _login(identity)
    assert isinstance(token_id, UUID)
    key = secrets.token_bytes(32)
    presentation = TokenPresentation(key)
    value = presentation.encode(token_id)
    options = conninfo_to_dict(app_dsn)
    url = URL.create(
        "postgresql+psycopg",
        username=str(options["user"]),
        password=str(options["password"]),
        host=str(options["host"]),
        port=int(str(options["port"])),
        database=str(options["dbname"]),
        query={"sslmode": "disable"},
    )
    monkeypatch.setenv(
        "PITCHLOG_DATABASE_URL", url.render_as_string(hide_password=False)
    )
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")

    with (
        caplog.at_level(logging.INFO, logger="sqlalchemy.engine"),
        caplog.at_level(logging.DEBUG, logger="psycopg"),
    ):
        # 後から入る DEBUG 設定で caplog のハンドラも DEBUG にする。
        caplog.clear()
        with pytest.raises(psycopg.OperationalError):
            psycopg.connect(
                host="127.0.0.1",
                hostaddr="127.0.0.1",
                port=1,
                dbname="log_probe",
                user="log_probe",
                connect_timeout=1,
            )
        probe_records = tuple(
            record for record in caplog.records if record.name.startswith("psycopg")
        )
        assert any(
            "connection attempt" in record.getMessage() for record in probe_records
        )
        assert any(
            "connection failed" in record.getMessage() for record in probe_records
        )
        caplog.clear()

        engine = create_database_engine()
        try:
            with engine.connect():
                pass
            caplog.clear()
            assert verify_tenant_id(value, presentation, engine) == identity.tenant_id
            assert logout_token(value, presentation, engine) is None
            assert verify_tenant_id(value, presentation, engine) is None
        finally:
            records = tuple(caplog.records)
            caplog.clear()
            engine.dispose()

    formatter = logging.Formatter("%(message)s")
    engine_messages = "\n".join(
        formatter.format(record)
        for record in records
        if record.name.startswith("sqlalchemy.engine")
    )
    driver_messages = "\n".join(
        formatter.format(record)
        for record in records
        if record.name.startswith("psycopg")
    )
    assert "authn.verify_token" in engine_messages
    assert "authn.logout" in engine_messages
    assert not driver_messages, "psycopg が認証 SQL 実行中にログを出した"

    materials = (
        value,
        str(token_id),
        base64.b64encode(key).decode("ascii"),
        key.hex(),
        repr(key),
        str(options["password"]),
    )
    assert all(material not in engine_messages for material in materials), (
        "SQLAlchemy ログに認証素材が含まれる"
    )
    assert all(material not in driver_messages for material in materials), (
        "psycopg ログに認証素材が含まれる"
    )
