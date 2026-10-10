"""選手と対戦相手チームに閉じた単一表 operation を定義する。"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any, Union, cast
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Integer,
    Table,
    Text,
    Uuid,
    and_,
    bindparam,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.selectable import Select

from pitchlog.api.schemas.roster import (
    ROSTER_PAGE_SIZE_MAX,
)
from pitchlog.api.schemas.roster import (
    PlayerUpdate as PlayerUpdateSchema,
)
from pitchlog.api.schemas.roster import (
    TeamRecordUpdate as TeamRecordUpdateSchema,
)
from pitchlog.db.game_state.models import Game
from pitchlog.db.tenant_isolation.models import Player, TeamRecord
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.operation_registration import (
    OperationRegistration,
    PreparedOperation,
    RequiredBinding,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

__all__ = (
    "RosterReferenceUnavailable",
    "create_roster_player",
    "PlayerCreateToken",
    "PlayerReadToken",
    "PlayerUpdateToken",
    "TeamRecordCreateToken",
    "TeamRecordReadToken",
    "TeamRecordUpdateToken",
    "TeamRecordDeleteToken",
    "GameTeamLinkReadToken",
)


class RosterReferenceUnavailable(Exception):
    """選手の参照先を対象テナント内で利用できないことを表す。"""


_PLAYER_REFERENCE_FKS = frozenset(
    {"fk_players_team", "fk_players_roster_status", "fk_players_roster_label"}
)


def create_roster_player(
    context: TenantContext, operation: PlayerCreateToken
) -> TenantOperationResult:
    """選手を追加し、参照先不在を外へ漏らさない拒否へ写す。"""
    from pitchlog.repositories.transaction import tenant_transaction_scope

    try:
        with tenant_transaction_scope(context) as scope:
            return scope.run(operation)
    except IntegrityError as error:
        diagnostic = getattr(error.orig, "diag", None)
        if (
            getattr(error.orig, "sqlstate", None) == "23503"
            and getattr(diagnostic, "constraint_name", None) in _PLAYER_REFERENCE_FKS
        ):
            raise RosterReferenceUnavailable from error
        raise


_PLAYERS = cast(Table, Player.__table__)
_TEAM_RECORDS = cast(Table, TeamRecord.__table__)
_GAMES = cast(Table, Game.__table__)

_PLAYER_UPDATE_COLUMNS = frozenset(PlayerUpdateSchema.model_fields)
_TEAM_RECORD_UPDATE_COLUMNS = frozenset(TeamRecordUpdateSchema.model_fields)
# migration 0028 と同じ Unicode White_Space 集合を、類似名の SQL 判定に渡す。
_SIMILAR_NAME_WHITESPACE = (
    "\t\n\v\f\r \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005"
    "\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
)


def _require_uuid(value: object, field: str) -> None:
    """識別子の実行時型を閉じる。"""
    if type(value) is not UUID:
        raise ValueError(f"{field} は UUID が必要")


def _require_optional_uuid(value: object, field: str) -> None:
    """省略可能な識別子の実行時型を閉じる。"""
    if value is not None:
        _require_uuid(value, field)


def _require_text(value: object, field: str) -> None:
    """必須文字列の空値と異なる型を拒否する。"""
    if type(value) is not str or not value:
        raise ValueError(f"{field} は空でない文字列が必要")


def _require_optional_text(value: object, field: str) -> None:
    """省略可能な文字列の空値と異なる型を拒否する。"""
    if value is not None:
        _require_text(value, field)


@dataclass(frozen=True, slots=True)
class PlayerReadToken(TenantOperationToken):
    """選手の取得または最大 200 件の一覧を要求する。"""

    limit: int
    record_id: UUID | None = None
    team_record_id: UUID | None = None
    roster_status_key: str | None = None
    uniform_number: str | None = None
    exclude_id: UUID | None = None
    cursor_team_record_id: UUID | None = None
    cursor_id: UUID | None = None
    include_hidden: bool = False

    def __post_init__(self) -> None:
        """ページ境界と複合カーソルを検査する。"""
        if type(self.limit) is not int or not 1 <= self.limit <= ROSTER_PAGE_SIZE_MAX:
            raise ValueError(f"limit は 1〜{ROSTER_PAGE_SIZE_MAX} が必要")
        if type(self.include_hidden) is not bool:
            raise ValueError("include_hidden は真偽値が必要")
        for field in (
            "record_id",
            "team_record_id",
            "exclude_id",
            "cursor_team_record_id",
            "cursor_id",
        ):
            _require_optional_uuid(getattr(self, field), field)
        _require_optional_text(self.roster_status_key, "roster_status_key")
        _require_optional_text(self.uniform_number, "uniform_number")
        if (self.cursor_team_record_id is None) != (self.cursor_id is None):
            raise ValueError("選手カーソルの 2 つの ID は同時に指定する")

    @property
    def capability_id(self) -> str:
        """選手の読み取り capability を返す。"""
        return "CAP:players:read"


@dataclass(frozen=True, slots=True)
class PlayerCreateToken(TenantOperationToken):
    """選手を 1 行作成する。"""

    id: UUID
    team_record_id: UUID
    name: str
    roster_status_key: str
    throws: str | None = None
    bats: str | None = None
    uniform_number: str | None = None
    roster_label_key: str | None = None

    def __post_init__(self) -> None:
        """作成対象と値域を検査する。"""
        _require_uuid(self.id, "id")
        _require_uuid(self.team_record_id, "team_record_id")
        _require_text(self.name, "name")
        _require_text(self.roster_status_key, "roster_status_key")
        _require_optional_text(self.uniform_number, "uniform_number")
        _require_optional_text(self.roster_label_key, "roster_label_key")
        if self.throws not in {None, "right", "left"}:
            raise ValueError("throws は right/left/NULL が必要")
        if self.bats not in {None, "right", "left", "both"}:
            raise ValueError("bats は right/left/both/NULL が必要")

    @property
    def capability_id(self) -> str:
        """選手の追加 capability を返す。"""
        return "CAP:players:insert"


@dataclass(frozen=True, slots=True)
class PlayerUpdateToken(TenantOperationToken):
    """変更する列を明示して選手 1 行を更新する。"""

    id: UUID
    changes: tuple[tuple[str, str | None], ...]

    def __post_init__(self) -> None:
        """変更列を閉じ、重複と非 nullable 列の NULL を拒否する。"""
        _require_uuid(self.id, "id")
        if type(self.changes) is not tuple or any(
            type(item) is not tuple or len(item) != 2 for item in self.changes
        ):
            raise ValueError("changes は不変な列と値の組が必要")
        names = [name for name, _ in self.changes]
        if not names or len(names) != len(set(names)):
            raise ValueError("変更列は 1 件以上かつ重複なしが必要")
        if not set(names) <= _PLAYER_UPDATE_COLUMNS:
            raise ValueError("選手の未許可列は更新できない")
        for name, value in self.changes:
            if value is not None and (type(value) is not str or not value):
                raise ValueError(f"{name} は空でない文字列または NULL が必要")
            if name == "throws" and value not in {None, "right", "left"}:
                raise ValueError("throws は right/left/NULL が必要")
            if name == "bats" and value not in {None, "right", "left", "both"}:
                raise ValueError("bats は right/left/both/NULL が必要")
        if any(
            name in {"name", "roster_status_key"} and value is None
            for name, value in self.changes
        ):
            raise ValueError("非 nullable 列を NULL にできない")

    @property
    def capability_id(self) -> str:
        """選手の更新 capability を返す。"""
        return "CAP:players:update"


@dataclass(frozen=True, slots=True)
class TeamRecordReadToken(TenantOperationToken):
    """対戦相手チームの取得または最大 200 件の一覧を要求する。"""

    limit: int
    record_id: UUID | None = None
    cursor_id: UUID | None = None
    include_hidden: bool = False
    similar_name: str | None = None
    exclude_id: UUID | None = None

    def __post_init__(self) -> None:
        """ページ上限を検査する。"""
        if type(self.limit) is not int or not 1 <= self.limit <= ROSTER_PAGE_SIZE_MAX:
            raise ValueError(f"limit は 1〜{ROSTER_PAGE_SIZE_MAX} が必要")
        if type(self.include_hidden) is not bool:
            raise ValueError("include_hidden は真偽値が必要")
        _require_optional_uuid(self.record_id, "record_id")
        _require_optional_uuid(self.cursor_id, "cursor_id")
        _require_optional_uuid(self.exclude_id, "exclude_id")
        _require_optional_text(self.similar_name, "similar_name")

    @property
    def capability_id(self) -> str:
        """チームレコードの読み取り capability を返す。"""
        return "CAP:team_records:read"


@dataclass(frozen=True, slots=True)
class TeamRecordCreateToken(TenantOperationToken):
    """対戦相手の kind をサーバー側で固定して 1 行作成する。"""

    id: UUID
    name: str

    def __post_init__(self) -> None:
        """作成する対戦相手の値を検査する。"""
        _require_uuid(self.id, "id")
        _require_text(self.name, "name")

    @property
    def capability_id(self) -> str:
        """チームレコードの追加 capability を返す。"""
        return "CAP:team_records:insert"


@dataclass(frozen=True, slots=True)
class TeamRecordUpdateToken(TenantOperationToken):
    """対戦相手チームの名前を 1 行更新する。"""

    id: UUID
    name: str

    def __post_init__(self) -> None:
        """更新する対戦相手の値を検査する。"""
        _require_uuid(self.id, "id")
        _require_text(self.name, "name")

    @property
    def capability_id(self) -> str:
        """チームレコードの更新 capability を返す。"""
        return "CAP:team_records:update"


@dataclass(frozen=True, slots=True)
class TeamRecordDeleteToken(TenantOperationToken):
    """対戦相手チームの非表示時刻だけを 1 行更新する。"""

    id: UUID
    hidden_at: datetime

    def __post_init__(self) -> None:
        """対象 ID と非表示時刻を検査する。"""
        _require_uuid(self.id, "id")
        if type(self.hidden_at) is not datetime or self.hidden_at.tzinfo is None:
            raise ValueError("非表示時刻はタイムゾーン付き日時が必要")

    @property
    def capability_id(self) -> str:
        """論理削除に使うチーム更新 capability を返す。"""
        return "CAP:team_records:update"


@dataclass(frozen=True, slots=True)
class GameTeamLinkReadToken(TenantOperationToken):
    """指定チームを参照する試合があるかを 1 件だけ調べる。"""

    team_record_id: UUID

    def __post_init__(self) -> None:
        """対象 ID の型を検査する。"""
        _require_uuid(self.team_record_id, "team_record_id")

    @property
    def capability_id(self) -> str:
        """試合の読み取り capability を返す。"""
        return "CAP:games:read"


type _RosterBuilderOperation = (
    PlayerReadToken
    | PlayerUpdateToken
    | TeamRecordReadToken
    | GameTeamLinkReadToken
    | TeamRecordUpdateToken
    | TeamRecordDeleteToken
    | None
)


def _build_roster_statement(
    kind: str,
    operation: _RosterBuilderOperation,
) -> Union[Select, Insert, Update]:
    """許可された組み立て API だけで登録文と実行文を作る。"""
    if kind == "player_read":
        if operation is not None and not isinstance(operation, PlayerReadToken):
            raise ValueError("player_read には PlayerReadToken が必要")
        if operation is None:
            return (
                select(
                    _PLAYERS.c.id,
                    _PLAYERS.c.team_record_id,
                    _PLAYERS.c.name,
                    _PLAYERS.c.throws,
                    _PLAYERS.c.bats,
                    _PLAYERS.c.uniform_number,
                    _PLAYERS.c.roster_status_key,
                    _PLAYERS.c.roster_label_key,
                    _PLAYERS.c.hidden_at,
                )
                .where(_PLAYERS.c.tenant_id == bindparam("tenant_id"))
                .where(
                    or_(
                        bindparam("record_id", type_=Uuid(as_uuid=True)).is_(None),
                        _PLAYERS.c.id
                        == bindparam("record_id", type_=Uuid(as_uuid=True)),
                    )
                )
                .where(
                    or_(
                        bindparam("team_record_id", type_=Uuid(as_uuid=True)).is_(None),
                        _PLAYERS.c.team_record_id
                        == bindparam("team_record_id", type_=Uuid(as_uuid=True)),
                    )
                )
                .where(
                    or_(
                        bindparam("roster_status_key", type_=Text).is_(None),
                        _PLAYERS.c.roster_status_key
                        == bindparam("roster_status_key", type_=Text),
                    )
                )
                .where(
                    or_(
                        bindparam("include_hidden", type_=Boolean).is_(True),
                        _PLAYERS.c.hidden_at.is_(None),
                    )
                )
                .where(
                    or_(
                        bindparam(
                            "cursor_team_record_id", type_=Uuid(as_uuid=True)
                        ).is_(None),
                        _PLAYERS.c.team_record_id
                        > bindparam("cursor_team_record_id", type_=Uuid(as_uuid=True)),
                        and_(
                            _PLAYERS.c.team_record_id
                            == bindparam(
                                "cursor_team_record_id", type_=Uuid(as_uuid=True)
                            ),
                            _PLAYERS.c.id
                            > bindparam("cursor_id", type_=Uuid(as_uuid=True)),
                        ),
                    )
                )
                .order_by(_PLAYERS.c.team_record_id, _PLAYERS.c.id)
                .limit(bindparam("limit", type_=Integer))
            )
        token = operation
        statement = select(
            *cast(
                Select[Any], _build_roster_statement("player_read", None)
            ).selected_columns
        ).where(_PLAYERS.c.tenant_id == bindparam("tenant_id"))
        if not token.include_hidden:
            statement = statement.where(_PLAYERS.c.hidden_at.is_(None))
        if token.record_id is not None:
            statement = statement.where(_PLAYERS.c.id == bindparam("record_id"))
        if token.team_record_id is not None:
            statement = statement.where(
                _PLAYERS.c.team_record_id == bindparam("team_record_id")
            )
        if token.roster_status_key is not None:
            statement = statement.where(
                _PLAYERS.c.roster_status_key == bindparam("roster_status_key")
            )
        if token.uniform_number is not None:
            statement = statement.where(
                _PLAYERS.c.uniform_number == bindparam("uniform_number")
            )
        if token.exclude_id is not None:
            statement = statement.where(_PLAYERS.c.id != bindparam("exclude_id"))
        if token.cursor_team_record_id is not None:
            statement = statement.where(
                or_(
                    _PLAYERS.c.team_record_id
                    > bindparam("cursor_team_record_id", type_=Uuid(as_uuid=True)),
                    and_(
                        _PLAYERS.c.team_record_id
                        == bindparam("cursor_team_record_id", type_=Uuid(as_uuid=True)),
                        _PLAYERS.c.id
                        > bindparam("cursor_id", type_=Uuid(as_uuid=True)),
                    ),
                )
            )
        return statement.order_by(_PLAYERS.c.team_record_id, _PLAYERS.c.id).limit(
            bindparam("limit", type_=Integer)
        )
    if kind == "player_create":
        if operation is not None:
            raise ValueError("player_create には operation を渡せない")
        return insert(_PLAYERS).values(
            tenant_id=bindparam("tenant_id"),
            id=bindparam("id"),
            team_record_id=bindparam("team_record_id"),
            name=bindparam("name"),
            throws=bindparam("throws"),
            bats=bindparam("bats"),
            uniform_number=bindparam("uniform_number"),
            roster_status_key=bindparam("roster_status_key"),
            roster_label_key=bindparam("roster_label_key"),
        )
    if kind == "player_update":
        if operation is not None and not isinstance(operation, PlayerUpdateToken):
            raise ValueError("player_update には PlayerUpdateToken が必要")
        if operation is None:
            return (
                update(_PLAYERS)
                .where(_PLAYERS.c.tenant_id == bindparam("where_tenant_id"))
                .where(_PLAYERS.c.id == bindparam("where_id"))
                .values(name=bindparam("value_name"))
            )
        token = operation
        values = {name: bindparam(f"value_{name}") for name, _ in token.changes}
        return (
            update(_PLAYERS)
            .where(_PLAYERS.c.tenant_id == bindparam("where_tenant_id"))
            .where(_PLAYERS.c.id == bindparam("where_id"))
            .values(**values)
        )
    if kind == "team_read":
        if operation is not None and not isinstance(operation, TeamRecordReadToken):
            raise ValueError("team_read には TeamRecordReadToken が必要")
        if operation is None:
            return (
                select(
                    _TEAM_RECORDS.c.id,
                    _TEAM_RECORDS.c.kind,
                    _TEAM_RECORDS.c.name,
                    _TEAM_RECORDS.c.hidden_at,
                )
                .where(_TEAM_RECORDS.c.tenant_id == bindparam("tenant_id"))
                .where(_TEAM_RECORDS.c.kind == bindparam("kind", type_=Text))
                .where(
                    or_(
                        bindparam("record_id", type_=Uuid(as_uuid=True)).is_(None),
                        _TEAM_RECORDS.c.id
                        == bindparam("record_id", type_=Uuid(as_uuid=True)),
                    )
                )
                .where(
                    or_(
                        bindparam("include_hidden", type_=Boolean).is_(True),
                        _TEAM_RECORDS.c.hidden_at.is_(None),
                    )
                )
                .where(
                    or_(
                        bindparam("cursor_id", type_=Uuid(as_uuid=True)).is_(None),
                        _TEAM_RECORDS.c.id
                        > bindparam("cursor_id", type_=Uuid(as_uuid=True)),
                    )
                )
                .order_by(_TEAM_RECORDS.c.id)
                .limit(bindparam("limit", type_=Integer))
            )
        token = operation
        statement = (
            select(
                *cast(
                    Select[Any], _build_roster_statement("team_read", None)
                ).selected_columns
            )
            .where(_TEAM_RECORDS.c.tenant_id == bindparam("tenant_id"))
            .where(_TEAM_RECORDS.c.kind == bindparam("kind", type_=Text))
        )
        if not token.include_hidden:
            statement = statement.where(_TEAM_RECORDS.c.hidden_at.is_(None))
        if token.record_id is not None:
            statement = statement.where(_TEAM_RECORDS.c.id == bindparam("record_id"))
        if token.cursor_id is not None:
            statement = statement.where(_TEAM_RECORDS.c.id > bindparam("cursor_id"))
        if token.similar_name is not None:
            normalized_name = func.pg_catalog.lower(
                func.pg_catalog.btrim(
                    func.pg_catalog.normalize(
                        _TEAM_RECORDS.c.name,
                        bindparam("similar_form", "NFKC", type_=Text),
                    ),
                    bindparam(
                        "similar_whitespace", _SIMILAR_NAME_WHITESPACE, type_=Text
                    ),
                )
            )
            normalized_input = func.pg_catalog.lower(
                func.pg_catalog.btrim(
                    func.pg_catalog.normalize(
                        bindparam("similar_name", type_=Text),
                        bindparam("similar_form", "NFKC", type_=Text),
                    ),
                    bindparam(
                        "similar_whitespace", _SIMILAR_NAME_WHITESPACE, type_=Text
                    ),
                )
            )
            statement = statement.where(normalized_name == normalized_input)
        if token.exclude_id is not None:
            statement = statement.where(_TEAM_RECORDS.c.id != bindparam("exclude_id"))
        return statement.order_by(_TEAM_RECORDS.c.id).limit(
            bindparam("limit", type_=Integer)
        )
    if kind == "team_create":
        if operation is not None:
            raise ValueError("team_create には operation を渡せない")
        return insert(_TEAM_RECORDS).values(
            tenant_id=bindparam("tenant_id"),
            id=bindparam("id"),
            kind=bindparam("kind", type_=Text),
            name=bindparam("name"),
        )
    if kind == "team_update":
        if operation is not None and not isinstance(operation, TeamRecordUpdateToken):
            raise ValueError("team_update には TeamRecordUpdateToken が必要")
        return (
            update(_TEAM_RECORDS)
            .where(_TEAM_RECORDS.c.tenant_id == bindparam("where_tenant_id"))
            .where(_TEAM_RECORDS.c.id == bindparam("where_id"))
            .where(_TEAM_RECORDS.c.kind == bindparam("where_kind", type_=Text))
            .where(_TEAM_RECORDS.c.hidden_at.is_(None))
            .values(name=bindparam("name"))
        )
    if kind == "team_delete":
        if operation is not None and not isinstance(operation, TeamRecordDeleteToken):
            raise ValueError("team_delete には TeamRecordDeleteToken が必要")
        return (
            update(_TEAM_RECORDS)
            .where(_TEAM_RECORDS.c.tenant_id == bindparam("where_tenant_id"))
            .where(_TEAM_RECORDS.c.id == bindparam("where_id"))
            .where(_TEAM_RECORDS.c.kind == bindparam("where_kind", type_=Text))
            .where(_TEAM_RECORDS.c.hidden_at.is_(None))
            .values(hidden_at=bindparam("hidden_at"))
        )
    if kind == "game_team_link_read":
        if operation is not None and not isinstance(operation, GameTeamLinkReadToken):
            raise ValueError("game_team_link_read には GameTeamLinkReadToken が必要")
        return (
            select(_GAMES.c.id)
            .where(_GAMES.c.tenant_id == bindparam("tenant_id"))
            .where(
                or_(
                    _GAMES.c.home_team_record_id == bindparam("team_record_id"),
                    _GAMES.c.away_team_record_id == bindparam("team_record_id"),
                )
            )
            .limit(bindparam("limit", type_=Integer))
        )
    raise ValueError(f"未知の roster 文: {kind}")


def player_update_statement(operation: PlayerUpdateToken) -> Update:
    """閉じた変更列から 1 個の UPDATE 文を組み立てる。"""
    return cast(Update, _build_roster_statement("player_update", operation))


def player_read_statement(operation: PlayerReadToken) -> Select[Any]:
    """指定された条件だけを使い、索引に沿う 1 個の SELECT 文を作る。"""
    return cast(Select[Any], _build_roster_statement("player_read", operation))


def team_record_read_statement(operation: TeamRecordReadToken) -> Select[Any]:
    """対戦相手だけを対象に、指定条件で 1 個の SELECT 文を作る。"""
    return cast(Select[Any], _build_roster_statement("team_read", operation))


def _token_parameters(operation: TenantOperationToken) -> dict[str, object]:
    """不変 token のフィールドだけを束縛値に変換する。"""
    return {
        field.name: getattr(operation, field.name)
        for field in fields(cast(Any, operation))
    }


def _prepare_player_read(operation: TenantOperationToken) -> PreparedOperation:
    """選手の読み取り条件と次ページ判定分を準備する。"""
    token = cast(PlayerReadToken, operation)
    parameters = _token_parameters(token)
    parameters["limit"] = token.limit + 1
    return player_read_statement(token), parameters


def _prepare_player_create(operation: TenantOperationToken) -> PreparedOperation:
    """選手追加の束縛値を準備する。"""
    return _build_roster_statement("player_create", None), _token_parameters(operation)


def _prepare_player_update(operation: TenantOperationToken) -> PreparedOperation:
    """選手 PATCH の変更列と束縛値を準備する。"""
    token = cast(PlayerUpdateToken, operation)
    parameters = {"where_id": token.id}
    parameters.update({f"value_{name}": value for name, value in token.changes})
    return player_update_statement(token), parameters


def _prepare_team_record_read(operation: TenantOperationToken) -> PreparedOperation:
    """対戦相手の読み取り条件と次ページ判定分を準備する。"""
    token = cast(TeamRecordReadToken, operation)
    parameters = _token_parameters(token)
    parameters["limit"] = token.limit + 1
    parameters["kind"] = "opponent"
    return team_record_read_statement(token), parameters


def _prepare_team_record_create(operation: TenantOperationToken) -> PreparedOperation:
    """対戦相手の固定種別と追加値を準備する。"""
    return _build_roster_statement("team_create", None), {
        **_token_parameters(operation),
        "kind": "opponent",
    }


def _prepare_team_record_update(operation: TenantOperationToken) -> PreparedOperation:
    """対戦相手の固定種別と更新値を準備する。"""
    token = cast(TeamRecordUpdateToken, operation)
    parameters: dict[str, object] = {
        "where_id": token.id,
        "where_kind": "opponent",
        "name": token.name,
    }
    return _build_roster_statement("team_update", token), parameters


def _prepare_team_record_delete(operation: TenantOperationToken) -> PreparedOperation:
    """対戦相手の固定種別と非表示時刻を準備する。"""
    token = cast(TeamRecordDeleteToken, operation)
    return _build_roster_statement("team_delete", token), {
        "where_id": token.id,
        "where_kind": "opponent",
        "hidden_at": token.hidden_at,
    }


def _prepare_game_team_link_read(operation: TenantOperationToken) -> PreparedOperation:
    """試合の参照確認を 1 件に閉じる。"""
    token = cast(GameTeamLinkReadToken, operation)
    return _build_roster_statement("game_team_link_read", token), {
        "team_record_id": token.team_record_id,
        "limit": 1,
    }


# クラス集合は repository-contract.json の token 型集合と一致させる。
ROSTER_OPERATIONS: tuple[OperationRegistration, ...] = (
    OperationRegistration(
        PlayerReadToken,
        "CAP:players:read",
        _build_roster_statement("player_read", None),
        _PLAYERS.c.tenant_id,
        _prepare_player_read,
        required_limit_parameter="limit",
        required_limit_max=ROSTER_PAGE_SIZE_MAX + 1,
    ),
    OperationRegistration(
        PlayerCreateToken,
        "CAP:players:insert",
        _build_roster_statement("player_create", None),
        _PLAYERS.c.tenant_id,
        _prepare_player_create,
    ),
    OperationRegistration(
        PlayerUpdateToken,
        "CAP:players:update",
        _build_roster_statement("player_update", None),
        _PLAYERS.c.tenant_id,
        _prepare_player_update,
        allowed_update_columns=_PLAYER_UPDATE_COLUMNS,
    ),
    OperationRegistration(
        TeamRecordReadToken,
        "CAP:team_records:read",
        _build_roster_statement("team_read", None),
        _TEAM_RECORDS.c.tenant_id,
        _prepare_team_record_read,
        required_bindings=(RequiredBinding(_TEAM_RECORDS.c.kind, "kind", "opponent"),),
        required_limit_parameter="limit",
        required_limit_max=ROSTER_PAGE_SIZE_MAX + 1,
    ),
    OperationRegistration(
        TeamRecordCreateToken,
        "CAP:team_records:insert",
        _build_roster_statement("team_create", None),
        _TEAM_RECORDS.c.tenant_id,
        _prepare_team_record_create,
        required_bindings=(RequiredBinding(_TEAM_RECORDS.c.kind, "kind", "opponent"),),
    ),
    OperationRegistration(
        TeamRecordUpdateToken,
        "CAP:team_records:update",
        _build_roster_statement("team_update", None),
        _TEAM_RECORDS.c.tenant_id,
        _prepare_team_record_update,
        required_bindings=(
            RequiredBinding(_TEAM_RECORDS.c.kind, "where_kind", "opponent"),
        ),
        allowed_update_columns=_TEAM_RECORD_UPDATE_COLUMNS,
    ),
    OperationRegistration(
        TeamRecordDeleteToken,
        "CAP:team_records:update",
        _build_roster_statement("team_delete", None),
        _TEAM_RECORDS.c.tenant_id,
        _prepare_team_record_delete,
        required_bindings=(
            RequiredBinding(_TEAM_RECORDS.c.kind, "where_kind", "opponent"),
        ),
        allowed_update_columns=frozenset({"hidden_at"}),
    ),
    OperationRegistration(
        GameTeamLinkReadToken,
        "CAP:games:read",
        _build_roster_statement("game_team_link_read", None),
        _GAMES.c.tenant_id,
        _prepare_game_team_link_read,
        required_limit_parameter="limit",
        required_limit_max=1,
    ),
)
