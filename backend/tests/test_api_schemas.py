"""API スキーマの共通基底と共通型を検証する。"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from pitchlog.api.schemas.base import (
    BaseSchema,
    EntityId,
    ErrorDetail,
    ErrorEnvelope,
    ErrorField,
    HealthResponse,
    ReadSchema,
    Timestamp,
    VersionResponse,
)


class _AttributeSource:
    """属性から値を提供するテスト用オブジェクト。"""

    value = "属性の値"


class _BaseValueSchema(BaseSchema):
    """属性構築を許可しない検証用スキーマ。"""

    value: str


class _ReadValueSchema(ReadSchema):
    """属性構築を許可する検証用スキーマ。"""

    value: str


class _EntityIdSchema(BaseSchema):
    """ID 共通型を検証するためのスキーマ。"""

    value: EntityId


class _TimestampSchema(BaseSchema):
    """時刻共通型を検証するためのスキーマ。"""

    value: Timestamp


def test_existing_schemas_keep_field_shapes_and_defaults() -> None:
    """既存スキーマのフィールド定義と省略時の挙動が変わらないことを確認する。"""
    assert all(
        issubclass(schema, BaseSchema)
        for schema in (
            ErrorField,
            ErrorDetail,
            ErrorEnvelope,
            HealthResponse,
            VersionResponse,
        )
    )

    assert tuple(ErrorField.model_fields) == ("location",)
    assert ErrorField.model_fields["location"].annotation is str
    assert ErrorField.model_fields["location"].is_required()

    assert tuple(ErrorDetail.model_fields) == ("message", "fields")
    assert ErrorDetail.model_fields["message"].annotation is str
    assert ErrorDetail.model_fields["message"].is_required()
    assert ErrorDetail.model_fields["fields"].annotation == list[ErrorField] | None
    assert not ErrorDetail.model_fields["fields"].is_required()
    assert ErrorDetail.model_fields["fields"].default is None
    assert ErrorDetail(message="入力に誤りがあります").model_dump() == {
        "message": "入力に誤りがあります",
        "fields": None,
    }

    assert tuple(ErrorEnvelope.model_fields) == ("error",)
    assert ErrorEnvelope.model_fields["error"].annotation is ErrorDetail
    assert ErrorEnvelope.model_fields["error"].is_required()

    assert tuple(HealthResponse.model_fields) == ("status",)
    assert HealthResponse.model_fields["status"].annotation is str
    assert HealthResponse.model_fields["status"].is_required()

    assert tuple(VersionResponse.model_fields) == ("version",)
    assert VersionResponse.model_fields["version"].annotation is str
    assert VersionResponse.model_fields["version"].is_required()


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (ErrorField, {"location": "body", "unknown": "value"}),
        (ErrorDetail, {"message": "入力に誤りがあります", "unknown": "value"}),
        (
            ErrorEnvelope,
            {"error": {"message": "入力に誤りがあります"}, "unknown": "value"},
        ),
        (HealthResponse, {"status": "ok", "unknown": "value"}),
        (VersionResponse, {"version": "0.1.0", "unknown": "value"}),
    ],
)
def test_existing_schemas_reject_unknown_fields(
    schema: type[BaseSchema],
    payload: dict[str, object],
) -> None:
    """共通基底を継承した既存スキーマが未知フィールドを拒否することを確認する。"""
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


def test_read_schema_builds_from_attributes_but_base_schema_does_not() -> None:
    """読み取り用基底だけが属性からの構築を許可することを確認する。"""
    source = _AttributeSource()

    assert _ReadValueSchema.model_validate(source).value == "属性の値"
    with pytest.raises(ValidationError):
        _BaseValueSchema.model_validate(source)


def test_entity_id_accepts_uuid() -> None:
    """ID 共通型が UUID を受理し、JSON では文字列に直列化することを確認する。"""
    value = uuid4()

    result = _EntityIdSchema(value=str(value))

    assert EntityId is UUID
    assert result.value == value
    assert result.model_dump(mode="json") == {"value": str(value)}


def test_entity_id_rejects_non_uuid_value() -> None:
    """ID 共通型が UUID として解釈できない値を拒否することを確認する。"""
    with pytest.raises(ValidationError):
        _EntityIdSchema(value="not-a-uuid")


@pytest.mark.parametrize(
    "value",
    [
        datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
        "2026-09-17T12:00:00+09:00",
    ],
)
def test_timestamp_accepts_aware_datetime(value: datetime | str) -> None:
    """時刻共通型がタイムゾーン情報を持つ日時を受理することを確認する。"""
    result = _TimestampSchema(value=value)

    assert result.value.tzinfo is not None
    assert result.value.utcoffset() is not None


@pytest.mark.parametrize(
    "value",
    [
        datetime(2026, 9, 17, 12, 0),
        "2026-09-17T12:00:00",
    ],
)
def test_timestamp_rejects_naive_datetime(value: datetime | str) -> None:
    """時刻共通型がタイムゾーン情報を持たない日時を拒否することを確認する。"""
    with pytest.raises(ValidationError):
        _TimestampSchema(value=value)
