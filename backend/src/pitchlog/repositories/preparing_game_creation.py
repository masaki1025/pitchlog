"""準備中作成の固定6文と未登録7token候補を定義する。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import DateTime, Integer, Table, Text, Uuid, bindparam, insert, select
from sqlalchemy.sql.dml import Insert
from sqlalchemy.sql.selectable import Select

from pitchlog.api.schemas.games import (
    ExistingTournament,
    GameTypeKey,
    NewTournament,
    PreparationOptionsRequest,
    PreparingGameCreate,
    decode_preparation_options_cursor,
)
from pitchlog.db.game_state.models import Game
from pitchlog.db.game_state.rule_snapshot import decode_applied_rules
from pitchlog.db.tenant_isolation.models import TeamRecord, TenantVocabulary
from pitchlog.repositories.operation_registration import (
    OperationRegistration,
    PreparedOperation,
    PrimaryKeyBinding,
    RequiredBinding,
)
from pitchlog.repositories.tokens import TenantOperationToken

_GAMES = cast(Table, Game.__table__)
_VOCABULARIES = cast(Table, TenantVocabulary.__table__)
_TEAMS = cast(Table, TeamRecord.__table__)


def _uuid(value: object) -> None:
    """内部識別子をexact UUIDに限定する。"""
    if type(value) is not UUID:
        raise ValueError("識別子はUUIDが必要")


def _key(value: object) -> None:
    """キーを非空文字列に限定し、正規化しない。"""
    if type(value) is not str or not value:
        raise ValueError("キーは空でない文字列が必要")


@dataclass(frozen=True, slots=True)
class PreparingGameInsertToken(TenantOperationToken):
    """server値と検証済み保存JSONを1試合のINSERTへ渡す。"""

    game_id: UUID
    scheduled_at: datetime
    game_type_key: GameTypeKey
    tournament_key: str
    away_team_record_id: UUID
    home_team_record_id: UUID
    applied_rules_json: str
    plate_umpire: str | None = None
    section_label: str | None = None
    week_label: str | None = None
    day_label: str | None = None
    game_number_label: str | None = None

    def __post_init__(self) -> None:
        """既存DTO/codecの単一検証を使い、内部tokenも入力を検査する。"""
        _uuid(self.game_id)
        _uuid(self.away_team_record_id)
        _uuid(self.home_team_record_id)
        _key(self.tournament_key)
        if type(self.scheduled_at) is not datetime:
            raise ValueError("予定日時はaware datetimeが必要")
        PreparingGameCreate(
            scheduled_at=self.scheduled_at,
            game_type_key=self.game_type_key,
            tournament=ExistingTournament(kind="existing", key=self.tournament_key),
            away_team_record_id=self.away_team_record_id,
            home_team_record_id=self.home_team_record_id,
            plate_umpire=self.plate_umpire,
            section_label=self.section_label,
            week_label=self.week_label,
            day_label=self.day_label,
            game_number_label=self.game_number_label,
        )
        if type(self.applied_rules_json) is not str:
            raise ValueError("保存JSONは文字列が必要")
        decode_applied_rules(json.loads(self.applied_rules_json))

    @property
    def capability_id(self) -> str:
        """既存の試合INSERTを使う。"""
        return "CAP:games:insert"


@dataclass(frozen=True, slots=True)
class PreparingTournamentInsertToken(TenantOperationToken):
    """新大会キーと入力表示名だけをINSERTする。"""

    key: str
    display_name: str

    def __post_init__(self) -> None:
        """キーと今回承認された名称条件を検査する。"""
        _key(self.key)
        NewTournament(kind="new", display_name=self.display_name)

    @property
    def capability_id(self) -> str:
        """既存のチーム語彙INSERTを使う。"""
        return "CAP:tenant_vocabularies:insert"


@dataclass(frozen=True, slots=True)
class PreparingTournamentOptionsToken(TenantOperationToken):
    """有効大会を最大1ページ読む。"""

    limit: int = 20
    cursor: str | None = None

    def __post_init__(self) -> None:
        """件数と位置を既存DTO経由で検査する。"""
        if type(self.limit) is not int:
            raise ValueError("件数は整数が必要")
        PreparationOptionsRequest(limit=self.limit, cursor=self.cursor)

    @property
    def capability_id(self) -> str:
        """既存のチーム語彙読取を使う。"""
        return "CAP:tenant_vocabularies:read"


@dataclass(frozen=True, slots=True)
class PreparingTournamentNameExistsToken(TenantOperationToken):
    """完全一致の大会表示名が既存なら最大1件読む。"""

    display_name: str

    def __post_init__(self) -> None:
        """空白名を拒否し、既存の入力文字列を変えない。"""
        NewTournament(kind="new", display_name=self.display_name)

    @property
    def capability_id(self) -> str:
        """無効化済みを含む大会の存在確認にも同じ権限を使う。"""
        return "CAP:tenant_vocabularies:read"


@dataclass(frozen=True, slots=True)
class PreparingTournamentParentToken(TenantOperationToken):
    """指定キーの有効大会親だけを最大1件読む。"""

    key: str

    def __post_init__(self) -> None:
        """キーを非空文字列に限定する。"""
        _key(self.key)

    @property
    def capability_id(self) -> str:
        """既存のチーム語彙読取を使う。"""
        return "CAP:tenant_vocabularies:read"


@dataclass(frozen=True, slots=True)
class PreparingSelfTeamLockToken(TenantOperationToken):
    """self行の可視性を確定まで保持する。"""

    team_record_id: UUID

    def __post_init__(self) -> None:
        """対象IDをexact UUIDに限定する。"""
        _uuid(self.team_record_id)

    @property
    def capability_id(self) -> str:
        """既存の限定team読取ロックを使う。"""
        return "CAP:team_records:read"


@dataclass(frozen=True, slots=True)
class PreparingOpponentTeamLockToken(TenantOperationToken):
    """opponent行の可視性を確定まで保持する。"""

    team_record_id: UUID

    def __post_init__(self) -> None:
        """対象IDをexact UUIDに限定する。"""
        _uuid(self.team_record_id)

    @property
    def capability_id(self) -> str:
        """既存の限定team読取ロックを使う。"""
        return "CAP:team_records:read"


def _preparing_game_insert_statement() -> Insert:
    """利用者にtenant/状態/権利列を選ばせず試合を挿入する。"""
    return insert(_GAMES).values(
        tenant_id=bindparam("tenant_id", type_=Uuid(as_uuid=True)),
        id=bindparam("game_id", type_=Uuid(as_uuid=True)),
        scheduled_at=bindparam("scheduled_at", type_=DateTime(timezone=True)),
        game_type_key=bindparam("game_type_key"),
        game_type_category=bindparam("game_type_category"),
        tournament_key=bindparam("tournament_key"),
        away_team_record_id=bindparam("away_team_record_id", type_=Uuid(as_uuid=True)),
        home_team_record_id=bindparam("home_team_record_id", type_=Uuid(as_uuid=True)),
        plate_umpire=bindparam("plate_umpire"),
        section_label=bindparam("section_label"),
        week_label=bindparam("week_label"),
        day_label=bindparam("day_label"),
        game_number_label=bindparam("game_number_label"),
        status=bindparam("status"),
        applied_rules=bindparam("applied_rules", type_=_GAMES.c.applied_rules.type),
    )


def _preparing_tournament_insert_statement() -> Insert:
    """新大会の必要列だけを挿入し、無効名の復活/上書きをしない。"""
    return insert(_VOCABULARIES).values(
        tenant_id=bindparam("tenant_id", type_=Uuid(as_uuid=True)),
        key=bindparam("key"),
        category=bindparam("category"),
        display_name=bindparam("display_name"),
        disabled=bindparam("disabled"),
        pitch_family=bindparam("pitch_family"),
        abbreviation=bindparam("abbreviation"),
    )


def _preparing_tournament_options_statement(
    cursor_key: str | None = None,
) -> Select[Any]:
    """有効大会だけをkey順/limit付きで読む。"""
    statement = (
        select(_VOCABULARIES.c.key, _VOCABULARIES.c.display_name)
        .where(_VOCABULARIES.c.tenant_id == bindparam("tenant_id"))
        .where(_VOCABULARIES.c.category == bindparam("category"))
        .where(_VOCABULARIES.c.disabled == bindparam("disabled"))
    )
    if cursor_key is not None:
        statement = statement.where(
            _VOCABULARIES.c.key > bindparam("cursor_key", type_=Text)
        )
    return statement.order_by(_VOCABULARIES.c.key).limit(
        bindparam("limit", type_=Integer)
    )


def _preparing_tournament_name_exists_statement() -> Select[Any]:
    """同名の有効/無効大会を区別せず最大1件で確認する。"""
    return (
        select(_VOCABULARIES.c.key)
        .where(_VOCABULARIES.c.tenant_id == bindparam("tenant_id"))
        .where(_VOCABULARIES.c.category == bindparam("category"))
        .where(_VOCABULARIES.c.display_name == bindparam("display_name"))
        .limit(bindparam("limit", type_=Integer))
    )


def _preparing_tournament_parent_statement() -> Select[Any]:
    """指定キーの有効大会を最大1件で確認する。"""
    return (
        select(_VOCABULARIES.c.key)
        .where(_VOCABULARIES.c.tenant_id == bindparam("tenant_id"))
        .where(_VOCABULARIES.c.key == bindparam("key"))
        .where(_VOCABULARIES.c.category == bindparam("category"))
        .where(_VOCABULARIES.c.disabled == bindparam("disabled"))
        .limit(bindparam("limit", type_=Integer))
    )


def _preparing_team_lock_statement() -> Select[Any]:
    """既存の限定team行ロックと同じexact形を使う。"""
    return (
        select(_TEAMS.c.id)
        .where(_TEAMS.c.tenant_id == bindparam("tenant_id"))
        .where(_TEAMS.c.id == bindparam("team_record_id"))
        .where(_TEAMS.c.kind == bindparam("kind"))
        .where(_TEAMS.c.hidden_at.is_(None))
        .with_for_update()
    )


def _prepare_game(operation: TenantOperationToken) -> PreparedOperation:
    """強制変更後もDTO/codecを通し、INSERT束縛値を固定する。"""
    if type(operation) is not PreparingGameInsertToken:
        raise ValueError("試合INSERT tokenが必要")
    operation.__post_init__()
    return _preparing_game_insert_statement(), {
        "game_id": operation.game_id,
        "scheduled_at": operation.scheduled_at,
        "game_type_key": operation.game_type_key,
        "game_type_category": "game_type",
        "tournament_key": operation.tournament_key,
        "away_team_record_id": operation.away_team_record_id,
        "home_team_record_id": operation.home_team_record_id,
        "plate_umpire": operation.plate_umpire,
        "section_label": operation.section_label,
        "week_label": operation.week_label,
        "day_label": operation.day_label,
        "game_number_label": operation.game_number_label,
        "status": "preparing",
        "applied_rules": json.loads(operation.applied_rules_json),
    }


def _prepare_tournament(operation: TenantOperationToken) -> PreparedOperation:
    """大会INSERTの型/名称を再確認して定数列を束縛する。"""
    if type(operation) is not PreparingTournamentInsertToken:
        raise ValueError("大会INSERT tokenが必要")
    operation.__post_init__()
    return _preparing_tournament_insert_statement(), {
        "key": operation.key,
        "display_name": operation.display_name,
        "category": "tournament",
        "disabled": False,
        "pitch_family": None,
        "abbreviation": None,
    }


def _prepare_options(operation: TenantOperationToken) -> PreparedOperation:
    """位置/上限を再確認し、SQLでlimit+1件へ限定する。"""
    if type(operation) is not PreparingTournamentOptionsToken:
        raise ValueError("大会options tokenが必要")
    operation.__post_init__()
    key = (
        decode_preparation_options_cursor(operation.cursor)
        if operation.cursor is not None
        else None
    )
    parameters: dict[str, object] = {
        "category": "tournament",
        "disabled": False,
        "limit": operation.limit + 1,
    }
    if key is not None:
        parameters["cursor_key"] = key
    return _preparing_tournament_options_statement(key), parameters


def _prepare_name(operation: TenantOperationToken) -> PreparedOperation:
    """完全一致名の存在確認を1行へ限定する。"""
    if type(operation) is not PreparingTournamentNameExistsToken:
        raise ValueError("大会名存在tokenが必要")
    operation.__post_init__()
    return _preparing_tournament_name_exists_statement(), {
        "category": "tournament",
        "display_name": operation.display_name,
        "limit": 1,
    }


def _prepare_parent(operation: TenantOperationToken) -> PreparedOperation:
    """有効大会のkey照合を1行へ限定する。"""
    if type(operation) is not PreparingTournamentParentToken:
        raise ValueError("大会親tokenが必要")
    operation.__post_init__()
    return _preparing_tournament_parent_statement(), {
        "key": operation.key,
        "category": "tournament",
        "disabled": False,
        "limit": 1,
    }


def _prepare_team(operation: TenantOperationToken) -> PreparedOperation:
    """2exact型から固定kindを導出し、任意のkindを受け取らない。"""
    if type(operation) not in (
        PreparingSelfTeamLockToken,
        PreparingOpponentTeamLockToken,
    ):
        raise ValueError("teamロックtokenが必要")
    token = cast(PreparingSelfTeamLockToken | PreparingOpponentTeamLockToken, operation)
    token.__post_init__()
    return _preparing_team_lock_statement(), {
        "team_record_id": token.team_record_id,
        "kind": "self" if type(token) is PreparingSelfTeamLockToken else "opponent",
    }


_CATEGORY = RequiredBinding(_VOCABULARIES.c.category, "category", "tournament")
_ENABLED = RequiredBinding(_VOCABULARIES.c.disabled, "disabled", False)

# ステップ3で通常registryへ候補接続する。正式7.7/実RG1成功は別ゲート。
PREPARING_GAME_CREATE_OPERATIONS: tuple[OperationRegistration, ...] = (
    OperationRegistration(
        PreparingGameInsertToken,
        "CAP:games:insert",
        _preparing_game_insert_statement(),
        _GAMES.c.tenant_id,
        _prepare_game,
        required_bindings=(
            RequiredBinding(_GAMES.c.status, "status", "preparing"),
            RequiredBinding(
                _GAMES.c.game_type_category, "game_type_category", "game_type"
            ),
        ),
    ),
    OperationRegistration(
        PreparingTournamentInsertToken,
        "CAP:tenant_vocabularies:insert",
        _preparing_tournament_insert_statement(),
        _VOCABULARIES.c.tenant_id,
        _prepare_tournament,
        required_bindings=(
            _CATEGORY,
            _ENABLED,
            RequiredBinding(_VOCABULARIES.c.pitch_family, "pitch_family", None),
            RequiredBinding(_VOCABULARIES.c.abbreviation, "abbreviation", None),
        ),
    ),
    OperationRegistration(
        PreparingTournamentOptionsToken,
        "CAP:tenant_vocabularies:read",
        _preparing_tournament_options_statement(),
        _VOCABULARIES.c.tenant_id,
        _prepare_options,
        required_bindings=(_CATEGORY, _ENABLED),
        required_limit_parameter="limit",
        required_limit_max=101,
    ),
    OperationRegistration(
        PreparingTournamentNameExistsToken,
        "CAP:tenant_vocabularies:read",
        _preparing_tournament_name_exists_statement(),
        _VOCABULARIES.c.tenant_id,
        _prepare_name,
        required_bindings=(_CATEGORY,),
        required_limit_parameter="limit",
        required_limit_max=1,
    ),
    OperationRegistration(
        PreparingTournamentParentToken,
        "CAP:tenant_vocabularies:read",
        _preparing_tournament_parent_statement(),
        _VOCABULARIES.c.tenant_id,
        _prepare_parent,
        required_bindings=(_CATEGORY, _ENABLED),
        required_limit_parameter="limit",
        required_limit_max=1,
    ),
    *(
        OperationRegistration(
            token_type,
            "CAP:team_records:read",
            _preparing_team_lock_statement(),
            _TEAMS.c.tenant_id,
            _prepare_team,
            required_bindings=(RequiredBinding(_TEAMS.c.kind, "kind", kind),),
            primary_key_bindings=(
                PrimaryKeyBinding(_TEAMS.c.tenant_id, "tenant_id"),
                PrimaryKeyBinding(_TEAMS.c.id, "team_record_id"),
            ),
            for_update=True,
            use_capability_lock_shape=True,
        )
        for token_type, kind in (
            (PreparingSelfTeamLockToken, "self"),
            (PreparingOpponentTeamLockToken, "opponent"),
        )
    ),
)
