"""認証素材がアプリと SQLAlchemy のログ・例外へ出ない範囲を確認する。"""

import base64
import logging
import secrets
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from pitchlog.api.app import create_app
from pitchlog.authz.database_transport import DatabaseTransportConfigurationError
from pitchlog.authz.signing_key_config import SigningKeyConfigurationError
from pitchlog.authz.token_presentation import TokenPresentation
from pitchlog.authz.verified_tenant import logout_token, verify_tenant_id
from pitchlog.db.engine import create_database_engine


class _CollectingHandler(logging.Handler):
    """例外情報を含む整形済みログを外へ出さずに保持する。"""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        """ログレコードを整形してメモリ内だけに保存する。"""
        self.messages.append(self.format(record))


@contextmanager
def _capture_logger(name: str, level: int) -> Iterator[list[str]]:
    """対象ロガーの出力を捕まえ、設定を必ず元に戻す。

    Args:
        name: 捕捉するロガーの名前。
        level: 試験中に有効にするレベル。

    Yields:
        整形済みログのリスト。
    """
    logger = logging.getLogger(name)
    previous_level = logger.level
    previous_propagation = logger.propagate
    handler = _CollectingHandler()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    try:
        yield handler.messages
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagation


def test_verify_db_exception_hides_material_from_full_traceback() -> None:
    """既存の照合例外試験に不足するトレースバック全文を確認する。"""
    key = secrets.token_bytes(32)
    presentation = TokenPresentation(key)
    token_id = uuid4()
    value = presentation.encode(token_id)
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.execute.side_effect = SQLAlchemyError(f"{token_id} {value}")

    with pytest.raises(RuntimeError, match="トークンの照合を完了できない") as error:
        verify_tenant_id(value, presentation, engine)

    assert error.value.__context__ is None
    assert error.value.__cause__ is None
    message = str(error.value)
    full_traceback = "".join(traceback.format_exception(error.value))
    materials = (value, str(token_id), base64.b64encode(key).decode("ascii"))
    assert all(material not in message for material in materials), (
        "公開例外に認証素材が含まれる"
    )
    assert all(material not in full_traceback for material in materials), (
        "スタックトレースに認証素材が含まれる"
    )


def test_configuration_exceptions_hide_values_from_full_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """鍵と通信設定の拒否時に設定値を例外と全トレースへ残さない。"""
    invalid_key = "invalid-secret-key-" + uuid4().hex
    monkeypatch.setenv("PITCHLOG_TOKEN_SIGNING_KEY_B64", invalid_key)
    with pytest.raises(SigningKeyConfigurationError) as key_error:
        create_app()

    password = "private-password-" + uuid4().hex
    monkeypatch.setenv(
        "PITCHLOG_DATABASE_URL",
        f"postgresql://test_user:{password}@db.example/pitchlog?sslmode=prefer",
    )
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
    with pytest.raises(DatabaseTransportConfigurationError) as transport_error:
        create_database_engine()

    for error, material in (
        (key_error.value, invalid_key),
        (transport_error.value, password),
    ):
        message_contains_material = material in str(error)
        trace_contains_material = material in "".join(traceback.format_exception(error))
        assert not message_contains_material, "設定値が公開例外に含まれる"
        assert not trace_contains_material, "設定値がスタックトレースに含まれる"


@pytest.mark.parametrize(
    ("hide_parameters", "id_is_logged"), ((False, True), (True, False))
)
def test_sqlalchemy_info_logging_observes_bound_token_id(
    hide_parameters: bool, id_is_logged: bool
) -> None:
    """INFO では束縛 ID が出る条件と隠す条件を実行して区別する。"""
    token_id = uuid4()
    presentation = TokenPresentation(secrets.token_bytes(32))
    value = presentation.encode(token_id)
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", hide_parameters=hide_parameters
    )
    try:
        with _capture_logger("sqlalchemy.engine", logging.INFO) as messages:
            for action in (verify_tenant_id, logout_token):
                with pytest.raises(RuntimeError):
                    action(value, presentation, engine)
        output = "\n".join(messages)
        assert "authn.verify_token" in output
        assert "authn.logout" in output
        id_observed = str(token_id) in output
        value_observed = value in output
        assert id_observed is id_is_logged, "束縛 ID のログ判定が異なる"
        assert not value_observed, "提示値が SQLAlchemy ログに含まれる"
    finally:
        engine.dispose()


def test_product_engine_hides_parameters_without_enabling_echo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """製品の engine 生成時点で束縛値の非表示を固定する。"""
    monkeypatch.setenv(
        "PITCHLOG_DATABASE_URL",
        "postgresql://test_user:test_password@127.0.0.1/pitchlog?sslmode=disable",
    )
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")

    engine = create_database_engine()
    try:
        assert engine.hide_parameters is True
        assert not engine.echo
    finally:
        engine.dispose()


def test_app_key_and_transport_paths_do_not_log_auth_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """起動・鍵の拒否・通信設定の拒否で素材がアプリログへ出ない。"""
    key = secrets.token_bytes(32)
    encoded_key = base64.b64encode(key).decode("ascii")
    token_id = uuid4()
    value = TokenPresentation(key).encode(token_id)
    monkeypatch.setenv("PITCHLOG_TOKEN_SIGNING_KEY_B64", encoded_key)
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")

    with _capture_logger("pitchlog", logging.DEBUG) as messages:
        logging.getLogger("pitchlog").debug("capture-ready")
        assert messages == ["capture-ready"]
        messages.clear()

        app = create_app()
        assert app.state.token_presentation.decode(value) == token_id

        monkeypatch.delenv("PITCHLOG_TOKEN_SIGNING_KEY_B64")
        with pytest.raises(SigningKeyConfigurationError):
            create_app()
        monkeypatch.setenv("PITCHLOG_TOKEN_SIGNING_KEY_B64", "A" * 40)
        with pytest.raises(SigningKeyConfigurationError):
            create_app()

        monkeypatch.setenv(
            "PITCHLOG_DATABASE_URL",
            "postgresql://test_user:test_password@127.0.0.1/pitchlog?sslmode=disable",
        )
        engine = create_database_engine()
        engine.dispose()
        monkeypatch.setenv(
            "PITCHLOG_DATABASE_URL",
            "postgresql://test_user:test_password@db.example/pitchlog?sslmode=prefer",
        )
        with pytest.raises(DatabaseTransportConfigurationError):
            create_database_engine()

    output = "\n".join(messages)
    materials = (encoded_key, key.hex(), repr(key), value, str(token_id))
    assert all(material not in output for material in materials), (
        "アプリログに認証素材が含まれる"
    )
