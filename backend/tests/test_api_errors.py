"""API の共通エラー応答を検証する。"""

import logging
from uuid import uuid4

import pytest
from api_fixtures import create_error_test_app, error_logger
from httpx import ASGITransport, AsyncClient

from pitchlog.api.schemas.base import ErrorEnvelope


@pytest.mark.anyio
async def test_error_envelope_has_no_code_field() -> None:
    """エラー封筒が理由コード用フィールドを持たないことを確認する。"""
    assert "code" not in ErrorEnvelope.model_fields


@pytest.mark.anyio
async def test_validation_error_returns_locations_only() -> None:
    """バリデーション失敗が発生箇所だけを持つ 422 になることを確認する。"""
    transport = ASGITransport(app=create_error_test_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/validation", json={})

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "message": "入力に誤りがあります",
            "fields": [{"location": "body.player_name"}],
        }
    }
    assert "input" not in response.text
    assert "Field required" not in response.text


@pytest.mark.anyio
async def test_not_found_returns_fixed_envelope() -> None:
    """存在しない経路が固定形の 404 応答になることを確認する。"""
    transport = ASGITransport(app=create_error_test_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {"error": {"message": "対象が見つかりません"}}


@pytest.mark.anyio
async def test_method_not_allowed_returns_fixed_envelope() -> None:
    """許可されないメソッドが固定形の 405 応答になることを確認する。"""
    transport = ASGITransport(app=create_error_test_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/validation")

    assert response.status_code == 405
    assert response.json() == {"error": {"message": "リクエストを処理できません"}}


@pytest.mark.anyio
@pytest.mark.usefixtures(error_logger.__name__)
async def test_forbidden_is_hidden_as_not_found_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """403 が 404 と同一の本文になり ERROR ログへ残ることを確認する。"""
    assert not logging.getLogger("pitchlog.api.errors").disabled
    caplog.set_level(logging.ERROR, logger="pitchlog.api.errors")
    transport = ASGITransport(app=create_error_test_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        not_found_response = await client.get("/missing")
        forbidden_response = await client.get("/forbidden")

    assert forbidden_response.status_code == 404
    assert forbidden_response.json() == not_found_response.json()
    assert any(
        record.name == "pitchlog.api.errors" and record.levelno == logging.ERROR
        for record in caplog.records
    )


@pytest.mark.anyio
@pytest.mark.usefixtures(error_logger.__name__)
async def test_unhandled_exception_returns_safe_response_and_logs_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """未捕捉例外が安全な 500 応答と traceback を残すことを確認する。"""
    assert not logging.getLogger("pitchlog.api.errors").disabled
    caplog.set_level(logging.ERROR, logger="pitchlog.api.errors")
    transport = ASGITransport(app=create_error_test_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/unhandled")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"message": "サーバー内部でエラーが発生しました"}
    }
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text
    assert "意図的なテスト例外" not in response.text
    assert any(
        record.name == "pitchlog.api.errors"
        and record.levelno == logging.ERROR
        and record.exc_info is not None
        for record in caplog.records
    )
    assert "Traceback" in caplog.text


@pytest.mark.anyio
@pytest.mark.usefixtures(error_logger.__name__)
async def test_unhandled_exception_does_not_log_request_secrets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """未捕捉例外時にも要求中の毒性値をログへ出さないことを確認する。"""
    assert not logging.getLogger("pitchlog.api.errors").disabled
    toxic_value = f"SUPER-SECRET-TOKEN-{uuid4()}"
    caplog.set_level(logging.ERROR, logger="pitchlog.api.errors")
    transport = ASGITransport(app=create_error_test_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/unhandled",
            params={"probe": toxic_value},
            headers={"Authorization": f"Bearer {toxic_value}"},
        )

    assert response.status_code == 500
    assert toxic_value not in caplog.text
