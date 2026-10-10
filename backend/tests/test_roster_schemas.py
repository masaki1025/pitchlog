"""選手とチームレコードの DTO 契約を検証する。"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pitchlog.api.schemas.base import BaseSchema, Page, PageRequest, ReadSchema
from pitchlog.api.schemas.roster import (
    PlayerCreate,
    PlayerCreated,
    PlayerListRequest,
    PlayerRead,
    PlayerStatusApplied,
    PlayerStatusBulkRequest,
    PlayerStatusChange,
    PlayerStatusPreview,
    PlayerUpdate,
    TeamRecordCreate,
    TeamRecordCreated,
    TeamRecordListRequest,
    TeamRecordRead,
    TeamRecordUpdate,
)


def _player_values() -> dict[str, object]:
    """選手応答に必要な値を作る。

    Returns:
        選手応答の入力値。
    """
    return {
        "id": uuid4(),
        "team_record_id": uuid4(),
        "name": "投手",
        "roster_status_key": "future_vocabulary_key",
    }


def _player_create_values() -> dict[str, object]:
    """選手作成に必要な値を作る。

    Returns:
        選手作成の入力値。
    """
    return {
        "team_record_id": uuid4(),
        "name": "投手",
        "roster_status_key": "future_vocabulary_key",
    }


def _bulk_values() -> dict[str, object]:
    """一括要求に必要な値を作る。

    Returns:
        一括要求の入力値。
    """
    return {
        "player_ids": [uuid4()],
        "roster_status_key": "future_vocabulary_key",
        "roster_label_key": None,
    }


def test_read_dtos_use_common_base_and_omit_tenant_id() -> None:
    """応答型が属性を読めてテナント ID を出さないことを確認する。"""
    team_values = {"id": uuid4(), "kind": "opponent", "name": "相手"}
    team = TeamRecordRead.model_validate(
        SimpleNamespace(**team_values, tenant_id=uuid4())
    )
    player = PlayerRead.model_validate(
        SimpleNamespace(**_player_values(), tenant_id=uuid4())
    )

    assert isinstance(team, ReadSchema)
    assert isinstance(player, ReadSchema)
    assert team.hidden_at is None
    assert player.hidden_at is None
    assert "tenant_id" not in team.model_dump()
    assert "tenant_id" not in player.model_dump()


def test_created_and_bulk_response_dtos_keep_nested_shapes() -> None:
    """登録警告と一括変更結果が設計どおりの形を持つことを確認する。"""
    player_values = _player_values()
    team = TeamRecordCreated.model_validate(
        {"id": uuid4(), "kind": "opponent", "name": "相手", "similar_names": ["相手A"]}
    )
    player = PlayerCreated.model_validate(
        {**player_values, "same_number_players": [player_values]}
    )
    preview = PlayerStatusPreview.model_validate(
        {
            "changes": [
                {
                    "player_id": player_values["id"],
                    "name": "投手",
                    "before_status_key": "previous_key",
                    "after_status_key": "future_vocabulary_key",
                }
            ],
            "unchanged_player_ids": [],
            "not_found_player_ids": [],
        }
    )
    applied = PlayerStatusApplied.model_validate(
        {"applied": [player_values], "not_found_player_ids": []}
    )

    assert isinstance(team, TeamRecordRead)
    assert team.similar_names == ["相手A"]
    assert isinstance(player.same_number_players[0], PlayerRead)
    assert isinstance(preview.changes[0], PlayerStatusChange)
    assert isinstance(applied.applied[0], PlayerRead)
    assert "tenant_id" not in player.model_dump()


def test_team_create_accepts_name_only() -> None:
    """チーム作成で名前だけを受け付け、区分を要求から除くことを確認する。"""
    assert TeamRecordCreate(name="相手").model_dump() == {"name": "相手"}
    for payload in ({"name": ""}, {"name": "相手", "kind": "opponent"}):
        with pytest.raises(ValidationError):
            TeamRecordCreate.model_validate(payload)


@pytest.mark.parametrize("kind", ["self", "opponent"])
def test_team_read_accepts_defined_kinds(kind: str) -> None:
    """チーム区分の定義済み値を受け付けることを確認する。"""
    assert (
        TeamRecordRead.model_validate(
            {"id": uuid4(), "kind": kind, "name": "チーム"}
        ).kind
        == kind
    )


def test_team_read_rejects_unknown_kind() -> None:
    """未定義のチーム区分を拒否することを確認する。"""
    with pytest.raises(ValidationError):
        TeamRecordRead.model_validate(
            {"id": uuid4(), "kind": "other", "name": "チーム"}
        )


@pytest.mark.parametrize("schema", [PlayerRead, PlayerCreate, PlayerUpdate])
def test_player_throws_and_bats_use_defined_values(schema: type[BaseSchema]) -> None:
    """投打の値域を読み取り・作成・更新で揃えることを確認する。"""
    required = (
        _player_values()
        if schema is PlayerRead
        else _player_create_values()
        if schema is PlayerCreate
        else {}
    )
    for throws in ("right", "left"):
        for bats in ("right", "left", "both"):
            result = schema.model_validate({**required, "throws": throws, "bats": bats})
            assert result.model_dump()["throws"] == throws
            assert result.model_dump()["bats"] == bats
    for invalid in ({"throws": "both"}, {"bats": "switch"}):
        with pytest.raises(ValidationError):
            schema.model_validate({**required, **invalid})


@pytest.mark.parametrize("schema", [PlayerRead, PlayerCreate, PlayerUpdate])
def test_uniform_number_rejects_empty_but_accepts_none(
    schema: type[BaseSchema],
) -> None:
    """背番号なしを許し、空文字だけを拒否することを確認する。"""
    required = (
        _player_values()
        if schema is PlayerRead
        else _player_create_values()
        if schema is PlayerCreate
        else {}
    )
    assert (
        schema.model_validate({**required, "uniform_number": None}).model_dump()[
            "uniform_number"
        ]
        is None
    )
    assert (
        schema.model_validate({**required, "uniform_number": "12"}).model_dump()[
            "uniform_number"
        ]
        == "12"
    )
    with pytest.raises(ValidationError):
        schema.model_validate({**required, "uniform_number": ""})


def test_roster_status_key_is_not_a_closed_value_set() -> None:
    """在籍区分キーの値域をこの DTO で固定しないことを確認する。"""
    assert PlayerCreate.model_validate(_player_create_values()).roster_status_key == (
        "future_vocabulary_key"
    )
    assert (
        PlayerStatusBulkRequest.model_validate(_bulk_values()).roster_status_key
        == "future_vocabulary_key"
    )


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (TeamRecordRead, {"id": uuid4(), "kind": "self", "name": "自分"}),
        (TeamRecordCreate, {"name": "相手"}),
        (TeamRecordUpdate, {}),
        (
            TeamRecordCreated,
            {"id": uuid4(), "kind": "opponent", "name": "相手", "similar_names": []},
        ),
        (PlayerRead, _player_values()),
        (PlayerCreate, _player_create_values()),
        (PlayerUpdate, {}),
        (PlayerCreated, {**_player_values(), "same_number_players": []}),
        (PlayerListRequest, {"limit": 1}),
        (TeamRecordListRequest, {"limit": 1}),
        (PlayerStatusBulkRequest, _bulk_values()),
        (
            PlayerStatusChange,
            {
                "player_id": uuid4(),
                "name": "投手",
                "before_status_key": "a",
                "after_status_key": "b",
            },
        ),
        (
            PlayerStatusPreview,
            {"changes": [], "unchanged_player_ids": [], "not_found_player_ids": []},
        ),
        (PlayerStatusApplied, {"applied": [], "not_found_player_ids": []}),
    ],
)
def test_all_roster_dtos_forbid_extra_fields(
    schema: type[BaseSchema], payload: dict[str, object]
) -> None:
    """全 DTO が未知の入力項目を拒否することを確認する。"""
    with pytest.raises(ValidationError):
        schema.model_validate({**payload, "unexpected": "value"})


def test_patch_distinguishes_omitted_fields_and_explicit_null() -> None:
    """PATCH で省略と nullable 項目の明示 null を区別する。"""
    assert TeamRecordUpdate().model_dump(exclude_unset=True) == {}
    assert PlayerUpdate().model_dump(exclude_unset=True) == {}
    assert PlayerUpdate(uniform_number=None).model_dump(exclude_unset=True) == {
        "uniform_number": None
    }
    assert PlayerUpdate(throws=None, bats=None, roster_label_key=None).model_dump(
        exclude_unset=True
    ) == {"throws": None, "bats": None, "roster_label_key": None}
    assert TeamRecordUpdate(name="改名").model_dump(exclude_unset=True) == {
        "name": "改名"
    }


@pytest.mark.parametrize(
    ("schema", "field"),
    [
        (TeamRecordUpdate, "name"),
        (PlayerUpdate, "name"),
        (PlayerUpdate, "roster_status_key"),
    ],
)
def test_patch_rejects_null_for_nonnullable_fields(
    schema: type[BaseSchema], field: str
) -> None:
    """NULL にできない列への明示 null を検証エラーにする。"""
    with pytest.raises(ValidationError):
        schema.model_validate({field: None})


def test_player_update_rejects_team_record_id() -> None:
    """未分類の所属チーム変更を更新 DTO から除くことを確認する。"""
    assert "team_record_id" not in PlayerUpdate.model_fields
    with pytest.raises(ValidationError):
        PlayerUpdate.model_validate({"team_record_id": uuid4()})


@pytest.mark.parametrize("player_ids", [[], [uuid4()] * 2])
def test_bulk_rejects_empty_and_duplicate_player_ids(player_ids: list[object]) -> None:
    """空配列と重複 ID を検証エラーにする。"""
    with pytest.raises(ValidationError):
        PlayerStatusBulkRequest.model_validate(
            {**_bulk_values(), "player_ids": player_ids}
        )


def test_bulk_request_has_fifty_player_limit() -> None:
    """一括要求の件数境界を確認する。"""
    assert (
        len(
            PlayerStatusBulkRequest.model_validate(
                {**_bulk_values(), "player_ids": [uuid4() for _ in range(50)]}
            ).player_ids
        )
        == 50
    )
    with pytest.raises(ValidationError):
        PlayerStatusBulkRequest.model_validate(
            {**_bulk_values(), "player_ids": [uuid4() for _ in range(51)]}
        )


@pytest.mark.parametrize("schema", [PlayerListRequest, TeamRecordListRequest])
def test_list_requests_keep_required_limit_and_two_hundred_cap(
    schema: type[PageRequest],
) -> None:
    """一覧件数の必須・下限・上限を確認する。"""
    for payload in ({}, {"limit": 0}, {"limit": 201}):
        with pytest.raises(ValidationError):
            schema.model_validate(payload)
    assert schema(limit=1).limit == 1
    assert schema(limit=200).limit == 200


def test_list_requests_keep_cursor_and_resource_filters() -> None:
    """共通カーソルと資源ごとの絞り込みを確認する。"""
    team_id = uuid4()
    players = PlayerListRequest(
        limit=20,
        cursor="opaque-token",
        team_record_id=team_id,
        roster_status_key="future_vocabulary_key",
        include_hidden=True,
    )
    teams = TeamRecordListRequest(limit=20, include_hidden=True)

    assert players.team_record_id == team_id
    assert players.cursor == "opaque-token"
    assert teams.include_hidden
    assert Page[PlayerRead](items=[]).next_cursor is None
