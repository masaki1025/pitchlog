"""API スキーマの共通基底と共通型を検証する。"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from annotated_types import Le, Lt
from pydantic import ValidationError

from pitchlog.api.schemas.base import (
    BaseSchema,
    EntityId,
    ErrorDetail,
    ErrorEnvelope,
    ErrorField,
    HealthResponse,
    Page,
    PageRequest,
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


def test_page_request_limit_is_required_without_a_default() -> None:
    """ページ要求の件数が既定値を持たない必須項目であることを確認する。"""
    assert tuple(PageRequest.model_fields) == ("limit", "cursor")
    assert PageRequest.model_fields["limit"].is_required()

    with pytest.raises(ValidationError):
        PageRequest.model_validate({})


@pytest.mark.parametrize("limit", [10**3, 10**6, 10**9, 2**63 - 1])
def test_page_request_preserves_large_limit_values(limit: int) -> None:
    """ページ要求が標本の大きな件数を拒否も改変もせずに受理することを確認する。"""
    request = PageRequest(limit=limit)

    assert request.limit == limit


@pytest.mark.parametrize("limit", [0, -1])
def test_page_request_rejects_limit_below_one(limit: int) -> None:
    """ページ要求が 1 未満の件数を拒否することを確認する。"""
    with pytest.raises(ValidationError):
        PageRequest(limit=limit)


def test_page_request_accepts_limit_one() -> None:
    """ページ要求が下限ちょうどの件数を受理することを確認する。"""
    assert PageRequest(limit=1).limit == 1


def test_page_request_limit_has_no_upper_bound_metadata() -> None:
    """ページ要求の件数に上限を表すメタデータが無いことを確認する。"""
    metadata = PageRequest.model_fields["limit"].metadata

    assert not any(isinstance(item, (Le, Lt)) for item in metadata)


def test_page_request_cursor_uses_none_for_no_continuation() -> None:
    """ページ要求の継続位置が None を受理し空文字列を拒否することを確認する。"""
    cursor = "opaque cursor /?=+"

    assert PageRequest(limit=1).cursor is None
    assert PageRequest(limit=1, cursor=None).cursor is None
    assert PageRequest(limit=1, cursor=cursor).cursor == cursor
    with pytest.raises(ValidationError):
        PageRequest(limit=1, cursor="")


def test_page_next_cursor_uses_none_for_no_continuation() -> None:
    """ページ応答の継続位置が None を受理し空文字列を拒否することを確認する。"""
    next_cursor = "opaque cursor /?=+"

    assert Page[HealthResponse](items=[]).next_cursor is None
    assert Page[HealthResponse](items=[], next_cursor=None).next_cursor is None
    assert (
        Page[HealthResponse](items=[], next_cursor=next_cursor).next_cursor
        == next_cursor
    )
    with pytest.raises(ValidationError):
        Page[HealthResponse](items=[], next_cursor="")


def test_page_has_no_total_count_field() -> None:
    """共通ページ応答が総件数のフィールドを持たないことを確認する。"""
    assert tuple(Page.model_fields) == ("items", "next_cursor")


def test_page_can_specialize_its_item_type() -> None:
    """共通ページ応答が具体的な項目型で利用できることを確認する。"""
    page = Page[HealthResponse].model_validate({"items": [{"status": "ok"}]})

    assert page.items == [HealthResponse(status="ok")]
    assert page.next_cursor is None
    with pytest.raises(ValidationError):
        Page[HealthResponse].model_validate({})
