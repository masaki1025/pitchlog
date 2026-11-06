"""同一tenant snapshotから毎球CSV・全サイドカーの保存値を有限ページで読む。

この module は保存値の参照結合だけを行い、T1/T2 の状態や座標を再計算しない。
供給できない列は 0・NULL・現在名簿で補わず、列名と供給群を伴う非成功にする。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, Table, Text, Uuid, and_, bindparam, or_, select
from sqlalchemy.sql.selectable import Select

from pitchlog.db.game_state.models import (
    Game,
    ParticipationInterval,
    PlayRow,
    PlayRunner,
)
from pitchlog.db.sync_protocol.models import OperationEvent
from pitchlog.db.tenant_isolation.models import Player, TeamRecord, TenantVocabulary
from pitchlog.exports.play_rows import CSV_HEADERS, SavedCsvRow
from pitchlog.repositories.operation_registration import (
    OperationRegistration,
    PreparedOperation,
)
from pitchlog.repositories.roster import (
    PlayerReadToken,
    SelfTeamRecordReadToken,
    TeamRecordReadToken,
)
from pitchlog.repositories.started_snapshot_operations import StartedLineupsReadToken
from pitchlog.repositories.tokens import (
    TenantOperationResult,
    TenantOperationToken,
)
from pitchlog.sync.tokens import GameReadToken

if TYPE_CHECKING:
    from pitchlog.repositories.transaction import _TenantTransaction

JST = ZoneInfo("Asia/Tokyo")
MAX_PAGE_SIZE = 500
ROSTER_PAGE_SIZE = 200


class PlayExportNotVisible(Exception):
    """不存在・別tenant・隠蔽・退避済みの試合。"""


@dataclass(frozen=True, slots=True)
class MissingSupply:
    """供給できない列と、その供給群・必要producer。"""

    header: str
    column_index: int
    supply_group: str
    producer: str


class PlayExportSourceUnavailable(Exception):
    """88列を完成できない保存値不足。"""

    def __init__(self, missing: tuple[MissingSupply, ...]) -> None:
        """列名だけを含む固定の非成功を作る。"""
        if not missing:
            raise ValueError("不足なしでは例外を構築できない")
        self.missing = missing
        super().__init__("毎球CSVの供給が不足しています")


class PlayExportSnapshotChanged(Exception):
    """出力準備後、送出前の再確認で版が変わった。"""

    def __init__(self) -> None:
        """内部値を持たない固定の非成功。"""
        super().__init__("毎球CSVの出力版が変わりました")


@dataclass(frozen=True, slots=True)
class PlayExportSnapshot:
    """同一REPEATABLE READで確定した出力版。"""

    game_id: UUID
    snapshot_id: str
    source_versions: str
    exported_at: str


@dataclass(frozen=True, slots=True)
class PlayExportSource:
    """context内だけで使う、同一snapshotの保存値参照。"""

    handle: _TenantTransaction
    game: Mapping[str, Any]
    lineups: tuple[Mapping[str, Any], ...]
    participations: tuple[Mapping[str, Any], ...]
    players: Mapping[UUID, Mapping[str, Any]]
    teams: Mapping[UUID, Mapping[str, Any]]
    tenant_vocabularies: Mapping[tuple[str, str], Mapping[str, Any]]
    events: Mapping[UUID, Mapping[str, Any]]
    snapshot: PlayExportSnapshot
    max_rows: int = field(default=1_000_000)

    def iter_plays(self) -> Iterator[Mapping[str, Any]]:
        """有効PlayRowを(play_number,id)のキーセットで返す。"""
        after_number: int | None = None
        after_id: UUID | None = None
        while True:
            rows = _read_rows(
                self.handle,
                PlayExportPlayRowsToken(
                    self.snapshot.game_id,
                    after_number,
                    after_id,
                    MAX_PAGE_SIZE,
                ),
                PLAY_ROW_COLUMNS,
            )
            for row in rows:
                yield row
            if len(rows) < MAX_PAGE_SIZE:
                return
            last = rows[-1]
            after_number = cast(int, last["play_number"])
            after_id = cast(UUID, last["id"])

    def iter_events(self) -> Iterator[Mapping[str, Any]]:
        """受理済みOperationEventを(d2 NULLS LAST,id)の順で返す。"""
        yield from sorted(
            self.events.values(),
            key=lambda event: (
                event["d2"] is None,
                event["d2"] if event["d2"] is not None else 0,
                str(event["id"]),
            ),
        )

    def iter_participations(self) -> Iterator[Mapping[str, Any]]:
        """保存済み出場区間をid順で返す。"""
        yield from self.participations

    def iter_runners_for(
        self, play_ids: tuple[UUID, ...]
    ) -> Iterator[Mapping[str, Any]]:
        """ページ内play_id集合の走者を一括で返す。"""
        if not play_ids:
            return
        after_play_id: UUID | None = None
        after_id: UUID | None = None
        while True:
            rows = _read_rows(
                self.handle,
                PlayExportRunnersToken(
                    play_ids, after_play_id, after_id, MAX_PAGE_SIZE
                ),
                PLAY_RUNNER_COLUMNS,
            )
            for row in rows:
                yield row
            if len(rows) < MAX_PAGE_SIZE:
                return
            last = rows[-1]
            after_play_id = cast(UUID, last["play_id"])
            after_id = cast(UUID, last["id"])

    def iter_tenant_vocabularies(self) -> Iterator[Mapping[str, Any]]:
        """参照するtenant語彙をカテゴリ・key順で返す。"""
        for category in sorted(TENANT_VOCABULARY_CATEGORIES):
            after_key: str | None = None
            while True:
                rows = _read_rows(
                    self.handle,
                    PlayExportTenantVocabularyToken(
                        category, after_key, MAX_PAGE_SIZE + 1
                    ),
                    TENANT_VOCABULARY_COLUMNS,
                )
                for row in rows:
                    yield row
                if len(rows) < MAX_PAGE_SIZE + 1:
                    break
                after_key = cast(str, rows[-1]["key"])

    def project_play(
        self,
        play: Mapping[str, Any],
        runners: tuple[Mapping[str, Any], ...],
    ) -> dict[str, str | int | None]:
        """保存済み値だけで88列を組み立てる。欠測は例外にする。"""
        return project_play_row(self, play, runners)

    def missing_supply(
        self, play: Mapping[str, Any], runners: tuple[Mapping[str, Any], ...]
    ) -> tuple[MissingSupply, ...]:
        """一行の欠測列を返す。"""
        return project_play_cells(self, play, runners)[1]


def _rows(
    result: TenantOperationResult, columns: tuple[str, ...]
) -> list[dict[str, Any]]:
    """実行結果の列数・型を検証し、列名付きの行へ写す。"""
    if type(result) is not TenantOperationResult or type(result.rows) is not tuple:
        raise ValueError("出力読取の結果型が不正です")
    if any(type(row) is not tuple or len(row) != len(columns) for row in result.rows):
        raise ValueError("出力読取の列数が不正です")
    return [dict(zip(columns, row, strict=True)) for row in result.rows]


def _read_rows(
    handle: _TenantTransaction,
    operation: TenantOperationToken,
    columns: tuple[str, ...],
) -> list[dict[str, Any]]:
    """一件の登録readを実行し、有限行を列名付きで返す。"""
    return _rows(handle.run(operation), columns)


def _read_one(
    handle: _TenantTransaction,
    operation: TenantOperationToken,
    columns: tuple[str, ...],
) -> dict[str, Any] | None:
    """0/1行だけを許すread。"""
    rows = _read_rows(handle, operation, columns)
    if len(rows) > 1:
        raise ValueError("単一行readが複数行を返しました")
    return rows[0] if rows else None


_GAMES = cast(Table, Game.__table__)
_PLAYS = cast(Table, PlayRow.__table__)
_EVENTS = cast(Table, OperationEvent.__table__)
_RUNNERS = cast(Table, PlayRunner.__table__)
_PARTICIPATIONS = cast(Table, ParticipationInterval.__table__)
_TENANT_VOCABULARIES = cast(Table, TenantVocabulary.__table__)
_PLAYERS = cast(Table, Player.__table__)
_TEAM_RECORDS = cast(Table, TeamRecord.__table__)

GAME_COLUMNS = tuple(_GAMES.c.keys())
PLAY_ROW_COLUMNS = tuple(_PLAYS.c.keys())
EVENT_COLUMNS = tuple(_EVENTS.c.keys())
PLAY_RUNNER_COLUMNS = tuple(_RUNNERS.c.keys())
PARTICIPATION_COLUMNS = tuple(_PARTICIPATIONS.c.keys())
TENANT_VOCABULARY_COLUMNS = tuple(_TENANT_VOCABULARIES.c.keys())
PLAYER_COLUMNS = (
    "id",
    "team_record_id",
    "name",
    "throws",
    "bats",
    "uniform_number",
    "roster_status_key",
    "roster_label_key",
    "hidden_at",
)
TEAM_RECORD_COLUMNS = ("id", "kind", "name", "hidden_at")
LINEUP_COLUMNS = (
    "tenant_id",
    "id",
    "game_id",
    "team_record_id",
    "entries_with_uniform_number_snapshot",
)
TENANT_VOCABULARY_CATEGORIES = frozenset(
    {"pitch_type", "strategy", "tournament", "roster_label"}
)


def _uuid_parameter(name: str) -> Any:
    """UUIDの型を明示した bind を作る。"""
    return bindparam(name, type_=Uuid(as_uuid=True))


@dataclass(frozen=True, slots=True)
class _PlayExportToken(TenantOperationToken):
    """game_idだけを受け取り、tenantは実行器が注入する基底。"""

    game_id: UUID
    _capability: ClassVar[str]

    def __post_init__(self) -> None:
        """UUID文字列の暗黙変換を拒否する。"""
        if type(self.game_id) is not UUID:
            raise ValueError("出力読取にはUUID実値が必要です")

    @property
    def capability_id(self) -> str:
        """固定の既存read capabilityを返す。"""
        return self._capability


@dataclass(frozen=True, slots=True)
class PlayExportPlayRowsToken(_PlayExportToken):
    """有効PlayRowのキーセットページ。"""

    after_play_number: int | None
    after_id: UUID | None
    limit: int
    _capability = "CAP:play_rows:read"

    def __post_init__(self) -> None:
        """キーセットと上限を検査する。"""
        _PlayExportToken.__post_init__(self)
        if (self.after_play_number is None) != (self.after_id is None):
            raise ValueError("play行カーソルは2値同時が必要です")
        if self.after_play_number is not None and (
            type(self.after_play_number) is not int or self.after_play_number < 0
        ):
            raise ValueError("play番号カーソルが不正です")
        if self.after_id is not None and type(self.after_id) is not UUID:
            raise ValueError("play IDカーソルが不正です")
        if type(self.limit) is not int or not 1 <= self.limit <= MAX_PAGE_SIZE:
            raise ValueError("play行の上限が不正です")


def _play_rows_statement(
    *,
    after: bool,
    descending: bool = False,
) -> Select[Any]:
    """tenant/game/非隠蔽とキーセットだけの固定SELECT。"""
    statement = (
        select(*_PLAYS.c)
        .where(_PLAYS.c.tenant_id == _uuid_parameter("tenant_id"))
        .where(_PLAYS.c.game_id == _uuid_parameter("game_id"))
        .where(_PLAYS.c.hidden_at.is_(None))
    )
    if after:
        if descending:
            statement = statement.where(
                or_(
                    _PLAYS.c.play_number
                    < bindparam("after_play_number", type_=Integer),
                    and_(
                        _PLAYS.c.play_number
                        == bindparam("after_play_number", type_=Integer),
                        _PLAYS.c.id < _uuid_parameter("after_id"),
                    ),
                )
            )
        else:
            statement = statement.where(
                or_(
                    _PLAYS.c.play_number
                    > bindparam("after_play_number", type_=Integer),
                    and_(
                        _PLAYS.c.play_number
                        == bindparam("after_play_number", type_=Integer),
                        _PLAYS.c.id > _uuid_parameter("after_id"),
                    ),
                )
            )
    if descending:
        return statement.order_by(
            _PLAYS.c.play_number.desc(), _PLAYS.c.id.desc()
        ).limit(bindparam("limit", type_=Integer))
    return statement.order_by(_PLAYS.c.play_number, _PLAYS.c.id).limit(
        bindparam("limit", type_=Integer)
    )


def _prepare_play_rows(operation: TenantOperationToken) -> PreparedOperation:
    """play行tokenを固定文と束縛値へ写す。"""
    if type(operation) is not PlayExportPlayRowsToken:
        raise ValueError("play行tokenが必要です")
    operation.__post_init__()
    after = operation.after_play_number is not None
    parameters: dict[str, object] = {
        "game_id": operation.game_id,
        "limit": operation.limit,
    }
    if after:
        parameters["after_play_number"] = operation.after_play_number
        parameters["after_id"] = operation.after_id
    return _play_rows_statement(after=after), parameters


@dataclass(frozen=True, slots=True)
class PlayExportEventsToken(_PlayExportToken):
    """全受理eventのキーセットページ。"""

    null_d2: bool
    after_d2: int | None
    after_id: UUID | None
    limit: int
    descending: bool = False
    _capability = "CAP:operation_events:read"

    def __post_init__(self) -> None:
        """null位置とキーセット・上限を検査する。"""
        _PlayExportToken.__post_init__(self)
        if type(self.null_d2) is not bool or type(self.descending) is not bool:
            raise ValueError("eventの位置・順序指定が不正です")
        if self.null_d2:
            if self.after_d2 is not None:
                raise ValueError("d2がNULLのカーソルにd2を指定できません")
        elif (self.after_d2 is None) != (self.after_id is None):
            raise ValueError("eventカーソルは2値同時が必要です")
        if self.after_d2 is not None and (
            type(self.after_d2) is not int or self.after_d2 < 0
        ):
            raise ValueError("d2カーソルが不正です")
        if self.after_id is not None and type(self.after_id) is not UUID:
            raise ValueError("event IDカーソルが不正です")
        if type(self.limit) is not int or not 1 <= self.limit <= MAX_PAGE_SIZE:
            raise ValueError("event行の上限が不正です")


def _events_statement(
    *,
    null_d2: bool,
    after: bool,
    descending: bool = False,
) -> Select[Any]:
    """全受理eventをd2位置ごとのキーセットで読む。"""
    statement = (
        select(*_EVENTS.c)
        .where(_EVENTS.c.tenant_id == _uuid_parameter("tenant_id"))
        .where(_EVENTS.c.game_id == _uuid_parameter("game_id"))
    )
    statement = statement.where(
        _EVENTS.c.d2.is_(None) if null_d2 else _EVENTS.c.d2.is_not(None)
    )
    if after:
        if null_d2:
            if descending:
                statement = statement.where(_EVENTS.c.id < _uuid_parameter("after_id"))
            else:
                statement = statement.where(_EVENTS.c.id > _uuid_parameter("after_id"))
        elif descending:
            statement = statement.where(
                or_(
                    _EVENTS.c.d2 < bindparam("after_d2", type_=Integer),
                    and_(
                        _EVENTS.c.d2 == bindparam("after_d2", type_=Integer),
                        _EVENTS.c.id < _uuid_parameter("after_id"),
                    ),
                )
            )
        else:
            statement = statement.where(
                or_(
                    _EVENTS.c.d2 > bindparam("after_d2", type_=Integer),
                    and_(
                        _EVENTS.c.d2 == bindparam("after_d2", type_=Integer),
                        _EVENTS.c.id > _uuid_parameter("after_id"),
                    ),
                )
            )
    if null_d2:
        return statement.order_by(
            _EVENTS.c.id.desc() if descending else _EVENTS.c.id
        ).limit(bindparam("limit", type_=Integer))
    return statement.order_by(
        _EVENTS.c.d2.desc() if descending else _EVENTS.c.d2,
        _EVENTS.c.id.desc() if descending else _EVENTS.c.id,
    ).limit(bindparam("limit", type_=Integer))


def _prepare_events(operation: TenantOperationToken) -> PreparedOperation:
    """Event tokenを固定文と束縛値へ写す。"""
    if type(operation) is not PlayExportEventsToken:
        raise ValueError("event tokenが必要です")
    operation.__post_init__()
    after = operation.after_id is not None
    parameters: dict[str, object] = {
        "game_id": operation.game_id,
        "limit": operation.limit,
    }
    if after:
        parameters["after_id"] = operation.after_id
        if not operation.null_d2:
            parameters["after_d2"] = operation.after_d2
    return (
        _events_statement(
            null_d2=operation.null_d2,
            after=after,
            descending=operation.descending,
        ),
        parameters,
    )


@dataclass(frozen=True, slots=True)
class PlayExportRunnersToken(TenantOperationToken):
    """ページ内play_id集合の走者を一括で読む。"""

    play_ids: tuple[UUID, ...]
    after_play_id: UUID | None
    after_id: UUID | None
    limit: int

    def __post_init__(self) -> None:
        """対象集合とカーソルを検査する。"""
        if (
            type(self.play_ids) is not tuple
            or not self.play_ids
            or len(self.play_ids) > MAX_PAGE_SIZE
        ):
            raise ValueError("走者読取のplay集合が不正です")
        if any(type(play_id) is not UUID for play_id in self.play_ids):
            raise ValueError("走者読取のplay IDが不正です")
        if len(set(self.play_ids)) != len(self.play_ids):
            raise ValueError("走者読取のplay IDが重複しています")
        if (self.after_play_id is None) != (self.after_id is None):
            raise ValueError("走者カーソルは2値同時が必要です")
        if self.after_play_id is not None and type(self.after_play_id) is not UUID:
            raise ValueError("走者play IDカーソルが不正です")
        if self.after_id is not None and type(self.after_id) is not UUID:
            raise ValueError("走者IDカーソルが不正です")
        if type(self.limit) is not int or not 1 <= self.limit <= MAX_PAGE_SIZE:
            raise ValueError("走者行の上限が不正です")

    @property
    def capability_id(self) -> str:
        """既存の走者read capabilityを返す。"""
        return "CAP:play_runners:read"


def _runners_statement(*, after: bool, play_count: int = 1) -> Select[Any]:
    """tenantとページ内play_id集合だけに閉じた走者SELECT。"""
    play_filter = or_(
        *(
            _RUNNERS.c.play_id == _uuid_parameter(f"play_id_{index}")
            for index in range(play_count)
        )
    )
    statement = (
        select(*_RUNNERS.c)
        .where(_RUNNERS.c.tenant_id == _uuid_parameter("tenant_id"))
        .where(play_filter)
    )
    if after:
        statement = statement.where(
            or_(
                _RUNNERS.c.play_id > _uuid_parameter("after_play_id"),
                and_(
                    _RUNNERS.c.play_id == _uuid_parameter("after_play_id"),
                    _RUNNERS.c.id > _uuid_parameter("after_id"),
                ),
            )
        )
    return statement.order_by(_RUNNERS.c.play_id, _RUNNERS.c.id).limit(
        bindparam("limit", type_=Integer)
    )


def _prepare_runners(operation: TenantOperationToken) -> PreparedOperation:
    """走者tokenを固定文と束縛値へ写す。"""
    if type(operation) is not PlayExportRunnersToken:
        raise ValueError("走者tokenが必要です")
    operation.__post_init__()
    after = operation.after_play_id is not None
    parameters: dict[str, object] = {
        f"play_id_{index}": play_id for index, play_id in enumerate(operation.play_ids)
    }
    parameters["limit"] = operation.limit
    if after:
        parameters["after_play_id"] = operation.after_play_id
        parameters["after_id"] = operation.after_id
    return _runners_statement(
        after=after, play_count=len(operation.play_ids)
    ), parameters


@dataclass(frozen=True, slots=True)
class PlayExportParticipationsToken(_PlayExportToken):
    """出場区間のキーセットページ。"""

    after_id: UUID | None
    limit: int
    descending: bool = False
    _capability = "CAP:participation_intervals:read"

    def __post_init__(self) -> None:
        """カーソルと上限を検査する。"""
        _PlayExportToken.__post_init__(self)
        if self.after_id is not None and type(self.after_id) is not UUID:
            raise ValueError("出場区間カーソルが不正です")
        if type(self.descending) is not bool:
            raise ValueError("出場区間の順序指定が不正です")
        if type(self.limit) is not int or not 1 <= self.limit <= MAX_PAGE_SIZE:
            raise ValueError("出場区間の上限が不正です")


def _participations_statement(*, after: bool, descending: bool = False) -> Select[Any]:
    """tenant/gameだけに閉じた出場区間SELECT。"""
    statement = (
        select(*_PARTICIPATIONS.c)
        .where(_PARTICIPATIONS.c.tenant_id == _uuid_parameter("tenant_id"))
        .where(_PARTICIPATIONS.c.game_id == _uuid_parameter("game_id"))
    )
    if after:
        statement = statement.where(
            _PARTICIPATIONS.c.id < _uuid_parameter("after_id")
            if descending
            else _PARTICIPATIONS.c.id > _uuid_parameter("after_id")
        )
    return statement.order_by(
        _PARTICIPATIONS.c.id.desc() if descending else _PARTICIPATIONS.c.id
    ).limit(bindparam("limit", type_=Integer))


def _prepare_participations(operation: TenantOperationToken) -> PreparedOperation:
    """出場区間tokenを固定文と束縛値へ写す。"""
    if type(operation) is not PlayExportParticipationsToken:
        raise ValueError("出場区間tokenが必要です")
    operation.__post_init__()
    parameters: dict[str, object] = {
        "game_id": operation.game_id,
        "limit": operation.limit,
    }
    if operation.after_id is not None:
        parameters["after_id"] = operation.after_id
    return (
        _participations_statement(
            after=operation.after_id is not None,
            descending=operation.descending,
        ),
        parameters,
    )


@dataclass(frozen=True, slots=True)
class PlayExportTenantVocabularyToken(TenantOperationToken):
    """tenant語彙のカテゴリ別キーセットページ。"""

    category: str
    after_key: str | None
    limit: int

    def __post_init__(self) -> None:
        """カテゴリ・カーソル・上限を検査する。"""
        if self.category not in TENANT_VOCABULARY_CATEGORIES:
            raise ValueError("出力対象外のtenant語彙カテゴリです")
        if self.after_key is not None and (
            type(self.after_key) is not str or not self.after_key
        ):
            raise ValueError("tenant語彙カーソルが不正です")
        if type(self.limit) is not int or not 1 <= self.limit <= MAX_PAGE_SIZE + 1:
            raise ValueError("tenant語彙の上限が不正です")

    @property
    def capability_id(self) -> str:
        """既存のtenant語彙read capabilityを返す。"""
        return "CAP:tenant_vocabularies:read"


def _tenant_vocabularies_statement(*, after: bool) -> Select[Any]:
    """tenant/category/有効行だけの語彙SELECT。"""
    statement = (
        select(*_TENANT_VOCABULARIES.c)
        .where(_TENANT_VOCABULARIES.c.tenant_id == _uuid_parameter("tenant_id"))
        .where(_TENANT_VOCABULARIES.c.category == bindparam("category", type_=Text))
        .where(_TENANT_VOCABULARIES.c.disabled.is_(False))
    )
    if after:
        statement = statement.where(
            _TENANT_VOCABULARIES.c.key > bindparam("after_key", type_=Text)
        )
    return statement.order_by(_TENANT_VOCABULARIES.c.key).limit(
        bindparam("limit", type_=Integer)
    )


def _prepare_tenant_vocabularies(
    operation: TenantOperationToken,
) -> PreparedOperation:
    """tenant語彙tokenを固定文と束縛値へ写す。"""
    if type(operation) is not PlayExportTenantVocabularyToken:
        raise ValueError("tenant語彙tokenが必要です")
    operation.__post_init__()
    parameters: dict[str, object] = {
        "category": operation.category,
        "limit": operation.limit,
    }
    if operation.after_key is not None:
        parameters["after_key"] = operation.after_key
    return (
        _tenant_vocabularies_statement(after=operation.after_key is not None),
        parameters,
    )


PLAY_EXPORT_OPERATIONS: tuple[OperationRegistration, ...] = (
    OperationRegistration(
        PlayExportPlayRowsToken,
        "CAP:play_rows:read",
        _play_rows_statement(after=False),
        _PLAYS.c.tenant_id,
        _prepare_play_rows,
        required_limit_parameter="limit",
        required_limit_max=MAX_PAGE_SIZE,
    ),
    OperationRegistration(
        PlayExportEventsToken,
        "CAP:operation_events:read",
        _events_statement(null_d2=False, after=False),
        _EVENTS.c.tenant_id,
        _prepare_events,
        required_limit_parameter="limit",
        required_limit_max=MAX_PAGE_SIZE,
    ),
    OperationRegistration(
        PlayExportRunnersToken,
        "CAP:play_runners:read",
        _runners_statement(after=False, play_count=1),
        _RUNNERS.c.tenant_id,
        _prepare_runners,
        required_limit_parameter="limit",
        required_limit_max=MAX_PAGE_SIZE,
    ),
    OperationRegistration(
        PlayExportParticipationsToken,
        "CAP:participation_intervals:read",
        _participations_statement(after=False),
        _PARTICIPATIONS.c.tenant_id,
        _prepare_participations,
        required_limit_parameter="limit",
        required_limit_max=MAX_PAGE_SIZE,
    ),
    OperationRegistration(
        PlayExportTenantVocabularyToken,
        "CAP:tenant_vocabularies:read",
        _tenant_vocabularies_statement(after=False),
        _TENANT_VOCABULARIES.c.tenant_id,
        _prepare_tenant_vocabularies,
        required_limit_parameter="limit",
        required_limit_max=MAX_PAGE_SIZE + 1,
    ),
)


def _as_utc(value: datetime) -> datetime:
    """タイムゾーンなしを現在時刻で補わない。"""
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("保存日時にタイムゾーンがありません")
    return value


def _jst_text(value: datetime | None, pattern: str) -> str | None:
    """保存日時をJSTの固定書式へ写す。NULLはNULLのまま。"""
    if value is None:
        return None
    return _as_utc(value).astimezone(JST).strftime(pattern)


def _canonical(value: object) -> str:
    """Snapshot digest用に保存値を決定的なJSONへ写す。"""

    def default(item: object) -> object:
        if isinstance(item, UUID):
            return str(item)
        if isinstance(item, datetime):
            return item.isoformat()
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, MappingProxyType):
            return dict(item)
        raise TypeError("未対応のsnapshot値")

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=default,
        allow_nan=False,
    )


def _digest(value: object) -> str:
    """正規JSONのSHA256。"""
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _read_reference_bundle(
    handle: _TenantTransaction, game_id: UUID
) -> tuple[
    dict[str, Any],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    dict[UUID, dict[str, Any]],
    dict[UUID, dict[str, Any]],
    dict[tuple[str, str], dict[str, Any]],
    dict[UUID, dict[str, Any]],
    PlayExportSnapshot,
]:
    """gameと参照資源を読み、同じsnapshotのdigestを先に確定する。"""
    game = _read_one(handle, GameReadToken(game_id), GAME_COLUMNS)
    if game is None or not _visible_game(game, game_id, handle._bound_tenant_id):
        raise PlayExportNotVisible

    lineups = tuple(
        _read_rows(handle, StartedLineupsReadToken(game_id), LINEUP_COLUMNS)
    )
    if any(lineup["game_id"] != game_id for lineup in lineups):
        raise ValueError("lineupの試合が一致しません")

    participations: list[dict[str, Any]] = []
    after_id: UUID | None = None
    while True:
        rows = _read_rows(
            handle,
            PlayExportParticipationsToken(game_id, after_id, MAX_PAGE_SIZE),
            PARTICIPATION_COLUMNS,
        )
        participations.extend(rows)
        if len(rows) < MAX_PAGE_SIZE:
            break
        after_id = cast(UUID, rows[-1]["id"])
    if any(row["game_id"] != game_id for row in participations):
        raise ValueError("出場区間の試合が一致しません")

    teams: dict[UUID, dict[str, Any]] = {}
    for team_id in (game["away_team_record_id"], game["home_team_record_id"]):
        if type(team_id) is not UUID:
            raise ValueError("試合のチームIDが不正です")
        row = _read_one(
            handle,
            TeamRecordReadToken(limit=1, record_id=team_id, include_hidden=True),
            TEAM_RECORD_COLUMNS,
        )
        if row is None:
            own = _read_one(
                handle,
                SelfTeamRecordReadToken(),
                TEAM_RECORD_COLUMNS,
            )
            if own is not None and own["id"] == team_id:
                row = own
        if row is None:
            raise ValueError("試合のチーム参照がありません")
        teams[team_id] = row

    players: dict[UUID, dict[str, Any]] = {}
    for team_id in teams:
        cursor_team: UUID | None = None
        cursor_id: UUID | None = None
        while True:
            rows = _read_rows(
                handle,
                PlayerReadToken(
                    limit=ROSTER_PAGE_SIZE,
                    team_record_id=team_id,
                    include_hidden=True,
                    cursor_team_record_id=cursor_team,
                    cursor_id=cursor_id,
                ),
                PLAYER_COLUMNS,
            )
            if len(rows) > ROSTER_PAGE_SIZE:
                page = rows[:ROSTER_PAGE_SIZE]
                has_more = True
            else:
                page = rows
                has_more = False
            for row in page:
                players[cast(UUID, row["id"])] = row
            if not has_more:
                break
            cursor_team = cast(UUID, page[-1]["team_record_id"])
            cursor_id = cast(UUID, page[-1]["id"])

    vocabularies: dict[tuple[str, str], dict[str, Any]] = {}
    for category in sorted(TENANT_VOCABULARY_CATEGORIES):
        after_key: str | None = None
        while True:
            rows = _read_rows(
                handle,
                PlayExportTenantVocabularyToken(category, after_key, MAX_PAGE_SIZE + 1),
                TENANT_VOCABULARY_COLUMNS,
            )
            if len(rows) > MAX_PAGE_SIZE:
                page = rows[:MAX_PAGE_SIZE]
                has_more = True
            else:
                page = rows
                has_more = False
            for row in page:
                vocabularies[(category, cast(str, row["key"]))] = row
            if not has_more:
                break
            after_key = cast(str, page[-1]["key"])

    events: dict[UUID, dict[str, Any]] = {}
    for null_d2 in (False, True):
        after_d2: int | None = None
        after_event_id: UUID | None = None
        while True:
            rows = _read_rows(
                handle,
                PlayExportEventsToken(
                    game_id, null_d2, after_d2, after_event_id, MAX_PAGE_SIZE
                ),
                EVENT_COLUMNS,
            )
            for row in rows:
                events[cast(UUID, row["id"])] = row
            if len(rows) < MAX_PAGE_SIZE:
                break
            after_event_id = cast(UUID, rows[-1]["id"])
            if not null_d2:
                after_d2 = cast(int, rows[-1]["d2"])

    latest_play = _read_one(
        handle,
        PlayExportPlayRowsToken(game_id, None, None, 1),
        PLAY_ROW_COLUMNS,
    )
    latest_event = _read_one(
        handle,
        PlayExportEventsToken(game_id, False, None, None, 1, descending=True),
        EVENT_COLUMNS,
    )
    latest_null_event = _read_one(
        handle,
        PlayExportEventsToken(game_id, True, None, None, 1, descending=True),
        EVENT_COLUMNS,
    )
    latest_participation = _read_one(
        handle,
        PlayExportParticipationsToken(game_id, None, 1, descending=True),
        PARTICIPATION_COLUMNS,
    )
    exported_at = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    digest_facts = {
        "game": game,
        "lineups": lineups,
        "participations": participations,
        "players": sorted((str(player_id), row) for player_id, row in players.items()),
        "teams": sorted((str(team_id), row) for team_id, row in teams.items()),
        "vocabularies": sorted(
            (f"{category}:{key}", row) for (category, key), row in vocabularies.items()
        ),
        "latest_play": latest_play,
        "latest_event": latest_event,
        "latest_null_event": latest_null_event,
        "latest_participation": latest_participation,
    }
    snapshot_id = _digest({"kind": "play-export-snapshot", **digest_facts})
    source_versions = _digest({"kind": "play-export-sources", **digest_facts})
    return (
        game,
        lineups,
        tuple(participations),
        players,
        teams,
        vocabularies,
        events,
        PlayExportSnapshot(game_id, snapshot_id, source_versions, exported_at),
    )


def _visible_game(game: Mapping[str, Any], game_id: UUID, tenant_id: UUID) -> bool:
    """不存在・別tenant・隠蔽・退避を同じ不可視へ閉じる。"""
    return (
        game.get("id") == game_id
        and game.get("tenant_id") == tenant_id
        and game.get("trashed_at") is None
        and game.get("hidden_at") is None
        and game.get("status") not in {"trashed", "hidden"}
    )


def read_play_export_source(
    handle: _TenantTransaction, game_id: UUID
) -> PlayExportSource:
    """認可済みhandleから、同一snapshotの保存値参照を返す。

    Args:
        handle: ``tenant_export_read_scope`` が返した生存中の読取専用TX。
        game_id: 対象試合。tenantはhandleからのみ得る。

    Returns:
        同じsnapshotの参照値。context外へ持ち出さない。

    Raises:
        PlayExportNotVisible: 不存在・別tenant・隠蔽・退避済みの場合。
        ValueError: 保存値の型・参照が壊れている場合。
        OSError: DB接続・読取が失敗した場合。
    """
    from pitchlog.repositories.transaction import _TenantTransaction

    if type(handle) is not _TenantTransaction or type(game_id) is not UUID:
        raise ValueError("出力読取のhandleまたは試合IDが不正です")
    if type(handle._bound_tenant_id) is not UUID:
        raise ValueError("出力読取のtenantが確定していません")
    (
        game,
        lineups,
        participations,
        players,
        teams,
        vocabularies,
        events,
        snapshot,
    ) = _read_reference_bundle(handle, game_id)
    return PlayExportSource(
        handle=handle,
        game=game,
        lineups=lineups,
        participations=participations,
        players=players,
        teams=teams,
        tenant_vocabularies=vocabularies,
        events=events,
        snapshot=snapshot,
    )


# 88列の供給群・producer。列定義の正は candidate JSON と同じ順序で固定する。
COLUMN_SUPPLY: tuple[tuple[str, int, str, str], ...] = (
    ("試合日時", 0, "G01", "games.scheduled_at"),
    ("Season", 1, "G01", "games.section_label"),
    ("Kind", 2, "G01", "game_type label binding"),
    ("Week", 3, "G01", "games.week_label"),
    ("Day", 4, "G01", "games.day_label"),
    ("GameNumber", 5, "G01", "games.game_number_label"),
    ("主審", 6, "G01", "games.plate_umpire"),
    ("後攻チーム", 7, "G01", "team_records.home"),
    ("先攻チーム", 8, "G01", "team_records.away"),
    ("プレイの番号", 9, "G02", "play_rows.play_number"),
    ("回", 10, "G04-R", "saved T1 after.state.inning"),
    ("表.裏", 11, "G04-R", "saved T1 after.state.half"),
    ("先攻得点", 12, "G04-R", "saved T1 after.state.score.away"),
    ("後攻得点", 13, "G04-R", "saved T1 after.state.score.home"),
    ("S", 14, "G04-R", "saved T1 after.count.strikes"),
    ("B", 15, "G04-R", "saved T1 after.count.balls"),
    ("アウト", 16, "G04-R", "saved T1 after.outs"),
    ("打席の継続", 17, "G04-R", "saved T1 plateAppearanceEnded"),
    ("イニング継続", 18, "G04-R", "saved T1 before/after half"),
    ("試合継続", 19, "G04-R", "saved T1 after.gameEnded"),
    ("一走打順", 20, "G05", "play_runners + participation"),
    ("一走氏名", 21, "G05", "play_runners + player"),
    ("二走打順", 22, "G05", "play_runners + participation"),
    ("二走氏名", 23, "G05", "play_runners + player"),
    ("三走打順", 24, "G05", "play_runners + participation"),
    ("三走氏名", 25, "G05", "play_runners + player"),
    ("打順", 26, "G02", "play_rows.batting_order"),
    ("打者氏名", 27, "G06", "play_rows.batter_id + player"),
    ("打席左右", 28, "G02", "play_rows.batting_side"),
    ("作戦", 29, "G02", "play_rows.strategy_key + vocabulary"),
    ("作戦2", 30, "G02", "play_rows.strategy_detail_key + vocabulary"),
    ("作戦結果", 31, "G02", "play_rows.strategy_result_key + vocabulary"),
    ("投手氏名", 32, "G06", "play_rows.pitcher_id + player"),
    ("投手左右", 33, "G06", "play_rows.pitcher_id + player.throws"),
    ("球数", 34, "G04-A", "ReadPlayExportPrimitives"),
    ("捕手", 35, "G06", "play_rows.catcher_id + player"),
    ("一走状況", 36, "G05", "play_runners.status"),
    ("二走状況", 37, "G05", "play_runners.status"),
    ("三走状況", 38, "G05", "play_runners.status"),
    ("打者状況", 39, "G02", "play_rows.batter_status"),
    ("プレイの種類", 40, "G02", "play_rows.event_kind"),
    ("構え", 41, "G02", "play_rows.stance"),
    ("コースX", 42, "G03", "saved observations.course.x"),
    ("コースY", 43, "G03", "saved observations.course.y"),
    ("球種", 44, "G02", "play_rows.pitch_type_key + vocabulary"),
    ("打撃結果", 45, "G02", "play_rows.batting_result_key + vocabulary"),
    ("打撃結果2", 46, "G02", "play_rows.secondary_batting_result_key + vocabulary"),
    ("捕球選手", 47, "G02", "play_rows.raw_fielder_position"),
    ("打球タイプ", 48, "G02", "play_rows.batted_ball_type + vocabulary"),
    ("打球強度", 49, "G02", "play_rows.batted_ball_strength + vocabulary"),
    ("打球位置X", 50, "G10", "play_rows.hit_x + field geometry"),
    ("打球位置Y", 51, "G10", "play_rows.hit_y + field geometry"),
    ("牽制の種類", 52, "G02", "play_rows.pickoff_type + vocabulary"),
    ("牽制詳細", 53, "G02", "play_rows.pickoff_detail + vocabulary"),
    ("エラーの種類", 54, "G02", "play_rows.error_type + vocabulary"),
    ("タイムの種類", 55, "G02", "play_rows.raw_error_position"),
    ("球速", 56, "G02", "saved observations.pitchSpeed.kmh"),
    ("プレス", 57, "G02", "play_rows.press"),
    ("偽走", 58, "G02", "play_rows.fake_run"),
    ("打者位置", 59, "G06", "participation fielding position"),
    ("打席Id", 60, "G02", "play_rows.comment"),
    ("打席結果", 61, "G04-R", "declared display formatter"),
    ("Result_col", 62, "G04-R", "declared display formatter"),
    ("打者登録名", 63, "G06", "player.name"),
    ("打者番号", 64, "G06", "lineup/participation uniform snapshot"),
    ("一走登録名", 65, "G06", "runner player.name"),
    ("一走番号", 66, "G06", "runner uniform snapshot"),
    ("二走登録名", 67, "G06", "runner player.name"),
    ("二走番号", 68, "G06", "runner uniform snapshot"),
    ("三走登録名", 69, "G06", "runner player.name"),
    ("三走番号", 70, "G06", "runner uniform snapshot"),
    ("投手番号", 71, "G06", "lineup/participation pitcher uniform"),
    ("入力項目", 72, "G07", "native input provenance"),
    ("先攻打順", 73, "G04-R", "per-team batting order pointer"),
    ("後攻打順", 74, "G04-R", "per-team batting order pointer"),
    ("経過時間", 75, "G08", "native event timestamp"),
    ("開始時刻", 76, "G01", "games.started_at"),
    ("現在時刻", 77, "G08", "native event timestamp"),
    ("top_poses", 78, "G09", "lineup/participation roster"),
    ("top_names", 79, "G09", "lineup/participation roster"),
    ("top_nums", 80, "G09", "lineup/participation roster"),
    ("top_lrs", 81, "G09", "lineup/participation roster"),
    ("bottom_poses", 82, "G09", "lineup/participation roster"),
    ("bottom_names", 83, "G09", "lineup/participation roster"),
    ("bottom_nums", 84, "G09", "lineup/participation roster"),
    ("bottom_lrs", 85, "G09", "lineup/participation roster"),
    ("top_score", 86, "G04-A", "ReadPlayExportPrimitives"),
    ("bottom_score", 87, "G04-A", "ReadPlayExportPrimitives"),
)
COLUMN_BY_HEADER = {row[0]: row for row in COLUMN_SUPPLY}
assert tuple(header for header, *_ in COLUMN_SUPPLY) == CSV_HEADERS["plays.csv"]


def _missing(header: str) -> MissingSupply:
    """列名から供給不足の記述を作る。"""
    name, index, group, producer = COLUMN_BY_HEADER[header]
    return MissingSupply(name, index, group, producer)


def _put(
    values: dict[str, str | int | None],
    missing: list[MissingSupply],
    header: str,
    value: str | int | None,
) -> None:
    """供給値があれば写し、Noneでも供給済みの明示NULLなら写す。"""
    values[header] = value


def _game_type_label(key: str) -> str | None:
    """Migration 0030 のシステム試合区分表示へ写す。"""
    return {
        "game_official": "公式戦",
        "game_semi_official": "準公式戦",
        "game_open": "オープン戦",
        "game_intrasquad": "紅白戦",
        "game_other": "その他",
    }.get(key)


_INPUT_VOCABULARY_PATH = "contracts/vocabulary/input_vocabulary_v1.json"


def _input_vocabulary() -> dict[str, str]:
    """既存の入力語彙契約から key→表示名を読む（計算なし）。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    raw = json.loads((root / _INPUT_VOCABULARY_PATH).read_text(encoding="utf-8"))
    result: dict[str, str] = {}
    for axis in raw["axes"]:
        for entry in axis["entries"]:
            result[entry["id"]] = entry["initialDisplayName"]
    return result


_INPUT_LABELS = _input_vocabulary()


def _vocabulary_label(
    source: PlayExportSource, category: str, key: str | None
) -> str | None:
    """tenant語彙の保存表示名を優先し、既存入力語彙へ限定fallbackする。"""
    if key is None:
        return None
    stored = source.tenant_vocabularies.get((category, key))
    if stored is not None:
        return cast(str, stored["display_name"])
    return _INPUT_LABELS.get(key)


def _player(source: PlayExportSource, player_id: object) -> Mapping[str, Any] | None:
    """参照先選手を現在名の表示参照として返す。"""
    if type(player_id) is not UUID:
        return None
    return source.players.get(player_id)


def _player_name(source: PlayExportSource, player_id: object) -> str | None:
    """登録名。履歴snapshotではなく保存済みの現在参照である。"""
    player = _player(source, player_id)
    return None if player is None else cast(str, player["name"])


_HANDEDNESS = {"right": "右", "left": "左"}


def _handedness(value: object) -> str | None:
    """保存済み利き手コードを旧表示へ写す。"""
    return _HANDEDNESS.get(value) if type(value) is str else None


_FIELDING_LABELS = {
    1: "P",
    2: "C",
    3: "1B",
    4: "2B",
    5: "3B",
    6: "SS",
    7: "LF",
    8: "CF",
    9: "RF",
}


def _active_interval(
    source: PlayExportSource,
    player_id: UUID,
    slot_kind: str,
    d2: int,
) -> Mapping[str, Any] | None:
    """保存済み出場区間から、そのD2で有効な区間を選ぶ（再計算なし）。"""
    candidates = [
        row
        for row in source.participations
        if row["player_id"] == player_id
        and row["slot_kind"] == slot_kind
        and row["valid_from_d2"] <= d2
        and (row["valid_until_d2"] is None or d2 < row["valid_until_d2"])
        and row["retired_at"] is None
    ]
    if len(candidates) != 1:
        return None
    return candidates[0]


def _lineup_entry(
    source: PlayExportSource, player_id: UUID
) -> Mapping[str, Any] | None:
    """開始lineupの保存entryを返す。"""
    for lineup in source.lineups:
        entries = lineup["entries_with_uniform_number_snapshot"]
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if entry.get("player_id") == str(player_id):
                return entry
    return None


def _uniform(source: PlayExportSource, player_id: UUID, d2: int) -> str | None:
    """保存済み背番号snapshotを優先し、現在値で履歴を偽装しない。"""
    interval = _active_interval(source, player_id, "fielding_position", d2)
    if interval is None:
        interval = _active_interval(source, player_id, "batting_order", d2)
    if interval is not None and interval["uniform_number_snapshot"] is not None:
        return cast(str, interval["uniform_number_snapshot"])
    entry = _lineup_entry(source, player_id)
    if entry is not None and entry.get("uniform_number_snapshot") is not None:
        return cast(str, entry["uniform_number_snapshot"])
    return None


def _batting_order(source: PlayExportSource, player_id: UUID, d2: int) -> int | None:
    """保存済み打順区間のslotを旧INTEGERへ写す。"""
    interval = _active_interval(source, player_id, "batting_order", d2)
    if interval is None:
        return None
    try:
        return int(cast(str, interval["slot"]))
    except (TypeError, ValueError):
        return None


def _fielding_position(
    source: PlayExportSource, player_id: UUID, d2: int
) -> str | None:
    """保存済み守備位置区間のslotを旧表示へ写す。"""
    interval = _active_interval(source, player_id, "fielding_position", d2)
    if interval is None:
        return None
    slot = cast(str, interval["slot"])
    if slot == "DH":
        return "DH"
    try:
        return _FIELDING_LABELS.get(int(slot))
    except (TypeError, ValueError):
        return None


def _payload_calculation(event: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """保存eventのcalculation request/responseを返す。再計算しない。"""
    if event is None:
        return None
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return None
    calculation = payload.get("calculation")
    return calculation if isinstance(calculation, Mapping) else None


def _saved_t1(
    event: Mapping[str, Any] | None,
) -> tuple[Mapping[str, Any], Mapping[str, Any]] | None:
    """保存T1のrequest/responseを返す。"""
    calculation = _payload_calculation(event)
    if calculation is None:
        return None
    request = calculation.get("request")
    response = calculation.get("response")
    if not isinstance(request, Mapping) or not isinstance(response, Mapping):
        return None
    t1 = request.get("t1")
    value = response.get("value")
    if not isinstance(t1, Mapping) or not isinstance(value, Mapping):
        return None
    saved_t1 = value.get("t1")
    if not isinstance(saved_t1, Mapping):
        return None
    return t1, saved_t1


def _state(snapshot: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """保存済みafter状態のstateFields。"""
    if not isinstance(snapshot, Mapping):
        return None
    fields = snapshot.get("stateFields")
    return fields if isinstance(fields, Mapping) else None


def _runner_by_base(
    runners: tuple[Mapping[str, Any], ...], base: int
) -> Mapping[str, Any] | None:
    """ページ内の走者を塁で引く。"""
    for runner in runners:
        if runner["base"] == base and runner["retired_at"] is None:
            return runner
    return None


def project_play_cells(
    source: PlayExportSource,
    play: Mapping[str, Any],
    runners: tuple[Mapping[str, Any], ...],
) -> tuple[dict[str, str | int | None], tuple[MissingSupply, ...]]:
    """保存値だけで一行分の88列を組み立て、欠測を分離して返す。"""
    values: dict[str, str | int | None] = {}
    missing: list[MissingSupply] = []
    game = source.game
    play_number = cast(int, play["play_number"])
    d2 = play_number
    event = source.events.get(cast(UUID, play["source_event_id"]))
    saved = _saved_t1(event)
    before_state = _state(saved[0].get("before")) if saved is not None else None
    after_state = _state(saved[1].get("after")) if saved is not None else None

    # G01
    values["試合日時"] = _jst_text(
        cast(datetime | None, game["scheduled_at"]), "%Y/%m/%d"
    )
    values["Season"] = cast(str | None, game["section_label"])
    label = _game_type_label(cast(str, game["game_type_key"]))
    if label is None:
        missing.append(_missing("Kind"))
    else:
        values["Kind"] = label
    values["Week"] = cast(str | None, game["week_label"])
    values["Day"] = cast(str | None, game["day_label"])
    values["GameNumber"] = cast(str | None, game["game_number_label"])
    values["主審"] = cast(str | None, game["plate_umpire"])
    away_team = source.teams.get(cast(UUID, game["away_team_record_id"]))
    home_team = source.teams.get(cast(UUID, game["home_team_record_id"]))
    values["後攻チーム"] = None if home_team is None else cast(str, home_team["name"])
    values["先攻チーム"] = None if away_team is None else cast(str, away_team["name"])
    values["開始時刻"] = _jst_text(
        cast(datetime | None, game["started_at"]), "%Y/%m/%d %H:%M:%S"
    )

    # G02
    values["プレイの番号"] = play_number
    values["打順"] = cast(int | None, play["batting_order"])
    values["打席左右"] = cast(str | None, play["batting_side"])
    values["作戦"] = _vocabulary_label(
        source, "strategy", cast(str | None, play["strategy_key"])
    )
    values["作戦2"] = _vocabulary_label(
        source, "strategy", cast(str | None, play["strategy_detail_key"])
    )
    values["作戦結果"] = _vocabulary_label(
        source, "strategy", cast(str | None, play["strategy_result_key"])
    )
    values["打者状況"] = cast(str | None, play["batter_status"])
    event_kind = cast(str, play["event_kind"])
    if event_kind == "pitch":
        values["プレイの種類"] = "投球"
    else:
        missing.append(_missing("プレイの種類"))
    values["構え"] = cast(str | None, play["stance"])
    values["球種"] = _vocabulary_label(
        source, "pitch_type", cast(str | None, play["pitch_type_key"])
    )
    values["打撃結果"] = _vocabulary_label(
        source, "batting_result", cast(str | None, play["batting_result_key"])
    )
    values["打撃結果2"] = _vocabulary_label(
        source,
        "secondary_result",
        cast(str | None, play["secondary_batting_result_key"]),
    )
    values["捕球選手"] = cast(str | None, play["raw_fielder_position"])
    values["打球タイプ"] = _vocabulary_label(
        source, "batted_ball_type", cast(str | None, play["batted_ball_type"])
    )
    values["打球強度"] = _vocabulary_label(
        source,
        "batted_ball_strength",
        cast(str | None, play["batted_ball_strength"]),
    )
    values["牽制の種類"] = _vocabulary_label(
        source, "pickoff", cast(str | None, play["pickoff_type"])
    )
    values["牽制詳細"] = _vocabulary_label(
        source, "pickoff", cast(str | None, play["pickoff_detail"])
    )
    values["エラーの種類"] = _vocabulary_label(
        source, "error_type", cast(str | None, play["error_type"])
    )
    values["タイムの種類"] = cast(str | None, play["raw_error_position"])
    if saved is None:
        missing.append(_missing("球速"))
    else:
        payload = event.get("payload") if event is not None else None
        observations = (
            payload.get("observations") if isinstance(payload, Mapping) else None
        )
        pitch_speed = (
            observations.get("pitchSpeed")
            if isinstance(observations, Mapping)
            else None
        )
        kmh = pitch_speed.get("kmh") if isinstance(pitch_speed, Mapping) else None
        if kmh is None:
            missing.append(_missing("球速"))
        else:
            values["球速"] = cast(str, kmh)
    values["プレス"] = cast(str | None, play["press"])
    values["偽走"] = cast(str | None, play["fake_run"])
    values["打席Id"] = cast(str | None, play["comment"])

    # G04-R: 保存T1の完成値だけを写す。
    if after_state is None:
        for header in (
            "回",
            "表.裏",
            "先攻得点",
            "後攻得点",
            "S",
            "B",
            "アウト",
            "打席の継続",
            "イニング継続",
            "試合継続",
            "打者位置",
        ):
            missing.append(_missing(header))
    else:
        assert saved is not None
        values["回"] = cast(str, after_state["state.inning"])
        values["表.裏"] = "表" if after_state["state.half"] == "top" else "裏"
        score = after_state["state.score"]
        values["先攻得点"] = cast(str, score["away"])
        values["後攻得点"] = cast(str, score["home"])
        values["S"] = cast(str, after_state["state.count.strikes"])
        values["B"] = cast(str, after_state["state.count.balls"])
        values["アウト"] = cast(str, after_state["state.outs"])
        ended = saved[1].get("plateAppearanceEnded")
        values["打席の継続"] = "打席完了" if ended is True else "打席継続"
        game_ended = after_state["state.gameEnded"]
        values["試合継続"] = "試合終了" if game_ended is True else "試合継続"
        if game_ended is True:
            values["イニング継続"] = "試合終了"
        elif before_state is not None and (
            before_state["state.inning"] != after_state["state.inning"]
            or before_state["state.half"] != after_state["state.half"]
        ):
            values["イニング継続"] = "イニング開始"
        else:
            values["イニング継続"] = "イニング継続"
        batter_id = play["batter_id"]
        position = (
            _fielding_position(source, batter_id, d2)
            if type(batter_id) is UUID
            else None
        )
        if position is None:
            missing.append(_missing("打者位置"))
        else:
            values["打者位置"] = position

    # G05
    for base, order_header, name_header, status_header in (
        (1, "一走打順", "一走氏名", "一走状況"),
        (2, "二走打順", "二走氏名", "二走状況"),
        (3, "三走打順", "三走氏名", "三走状況"),
    ):
        runner = _runner_by_base(runners, base)
        if runner is None:
            values[order_header] = 0
            values[name_header] = None
            values[status_header] = "0"
            continue
        runner_id = cast(UUID, runner["runner_id"])
        order = _batting_order(source, runner_id, d2)
        if order is None:
            missing.append(_missing(order_header))
        else:
            values[order_header] = order
        values[name_header] = _player_name(source, runner_id)
        values[status_header] = cast(str, runner["status"])

    # G06
    values["打者氏名"] = _player_name(source, play["batter_id"])
    values["投手氏名"] = _player_name(source, play["pitcher_id"])
    values["捕手"] = _player_name(source, play["catcher_id"])
    pitcher = _player(source, play["pitcher_id"])
    throws = None if pitcher is None else _handedness(pitcher["throws"])
    if throws is None:
        missing.append(_missing("投手左右"))
    else:
        values["投手左右"] = throws
    batter_name = _player_name(source, play["batter_id"])
    if batter_name is None:
        missing.append(_missing("打者登録名"))
    else:
        values["打者登録名"] = batter_name
    for prefix, runner in (
        ("一走", _runner_by_base(runners, 1)),
        ("二走", _runner_by_base(runners, 2)),
        ("三走", _runner_by_base(runners, 3)),
    ):
        if runner is None:
            values[f"{prefix}登録名"] = None
            values[f"{prefix}番号"] = None
            continue
        runner_id = cast(UUID, runner["runner_id"])
        name = _player_name(source, runner_id)
        if name is None:
            missing.append(_missing(f"{prefix}登録名"))
        else:
            values[f"{prefix}登録名"] = name
        values[f"{prefix}番号"] = _uniform(source, runner_id, d2)
    for header, player_id in (
        ("打者番号", play["batter_id"]),
        ("投手番号", play["pitcher_id"]),
    ):
        if type(player_id) is not UUID:
            values[header] = None
        else:
            values[header] = _uniform(source, player_id, d2)

    # G07/G08: 新規nativeに旧移行原字面は無い。旧TagはWon'tのためNULL。
    values["入力項目"] = None
    values["経過時間"] = None
    values["現在時刻"] = None

    # G09: 保存済みlineup/出場区間から旧配列を組み立てる。
    for side, team_id in (
        ("top", cast(UUID, game["away_team_record_id"])),
        ("bottom", cast(UUID, game["home_team_record_id"])),
    ):
        roster = _roster_arrays(source, team_id, d2)
        for suffix, header in (
            ("poses", f"{side}_poses"),
            ("names", f"{side}_names"),
            ("nums", f"{side}_nums"),
            ("lrs", f"{side}_lrs"),
        ):
            if roster is None:
                missing.append(_missing(header))
            else:
                values[header] = json.dumps(
                    roster[suffix],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )

    # G03/G04-A/G10: 現行の生成target/DB primitiveが未接続。
    for header in (
        "コースX",
        "コースY",
        "打球位置X",
        "打球位置Y",
        "球数",
        "打席結果",
        "Result_col",
        "先攻打順",
        "後攻打順",
        "top_score",
        "bottom_score",
    ):
        missing.append(_missing(header))

    return values, tuple(missing)


def _roster_arrays(
    source: PlayExportSource, team_id: UUID, d2: int
) -> dict[str, list[str]] | None:
    """保存済みlineup/出場区間から旧4配列を組み立てる。"""
    lineup = next(
        (row for row in source.lineups if row["team_record_id"] == team_id), None
    )
    if lineup is None:
        return None
    entries = lineup["entries_with_uniform_number_snapshot"]
    if not isinstance(entries, list):
        return None

    def current_player(slot_kind: str, slot: str) -> UUID | None:
        for row in source.participations:
            if (
                row["slot_kind"] == slot_kind
                and row["slot"] == slot
                and row["valid_from_d2"] <= d2
                and (row["valid_until_d2"] is None or d2 < row["valid_until_d2"])
                and row["retired_at"] is None
            ):
                return cast(UUID, row["player_id"])
        return None

    bat: list[UUID | None] = []
    for slot in range(1, 10):
        player_id = current_player("batting_order", str(slot))
        if player_id is None:
            for entry in entries:
                if entry.get("batting_order") == slot:
                    player_id = UUID(cast(str, entry["player_id"]))
                    break
        bat.append(player_id)
    field: dict[int, UUID | None] = {}
    for position in range(1, 10):
        player_id = current_player("fielding_position", str(position))
        if player_id is None:
            for entry in entries:
                role = entry.get("fielding_position")
                if (
                    isinstance(role, Mapping)
                    and role.get("kind") == "fielding"
                    and str(role.get("position")) == str(position)
                ):
                    player_id = UUID(cast(str, entry["player_id"]))
                    break
        field[position] = player_id

    def name(player_id: UUID | None) -> str:
        return "" if player_id is None else (_player_name(source, player_id) or "")

    def number(player_id: UUID | None) -> str:
        if player_id is None:
            return ""
        return _uniform(source, player_id, d2) or ""

    def handed(player_id: UUID | None, *, throws: bool = False) -> str:
        player = _player(source, player_id) if player_id is not None else None
        if player is None:
            return ""
        return _handedness(player["throws" if throws else "bats"]) or ""

    poses = [
        _fielding_position(source, player_id, d2) or "" if player_id else ""
        for player_id in [*bat, field.get(1)]
    ]
    names = (
        [name(player_id) for player_id in bat]
        + [name(field.get(position)) for position in range(1, 10)]
        + ["", ""]
    )
    nums = [number(player_id) for player_id in [*bat, field.get(1)]]
    lrs = [handed(player_id) for player_id in bat] + [
        handed(field.get(1), throws=True),
        handed(field.get(2), throws=True),
    ]
    return {"poses": poses, "names": names, "nums": nums, "lrs": lrs}


def project_play_row(
    source: PlayExportSource,
    play: Mapping[str, Any],
    runners: tuple[Mapping[str, Any], ...],
) -> dict[str, str | int | None]:
    """一行を完成し、欠測があれば固定の非成功にする。"""
    values, missing = project_play_cells(source, play, runners)
    if missing:
        raise PlayExportSourceUnavailable(missing)
    return values


def iter_play_rows(
    source: PlayExportSource,
) -> Iterator[SavedCsvRow]:
    """88列本体を供給順に返す。未供給行は部分出力しない。"""
    for play in source.iter_plays():
        play_id = cast(UUID, play["id"])
        runners = tuple(source.iter_runners_for((play_id,)))
        values = project_play_row(source, play, runners)
        if set(values) != set(CSV_HEADERS["plays.csv"]):
            raise ValueError("88列の供給キーが一致しません")
        yield SavedCsvRow(
            game_id=source.snapshot.game_id,
            snapshot_id=source.snapshot.snapshot_id,
            values=values,
        )


def iter_sidecar_rows(source: PlayExportSource, name: str) -> Iterator[SavedCsvRow]:
    """サイドカーを同名の固定ヘッダ順で返す。"""
    if name == "play_links.csv":
        for play in source.iter_plays():
            yield _row(
                source,
                name,
                {
                    "row_number": None,
                    "game_id": str(source.snapshot.game_id),
                    "recording_generation": _generation(play),
                    "event_sequence": None,
                    "source_event_id": str(play["source_event_id"]),
                    "play_row_id": str(play["id"]),
                    "play_number": play["play_number"],
                    "version": play["version"],
                },
            )
        return
    if name == "events.csv":
        for event in source.iter_events():
            yield _row(
                source,
                name,
                {
                    "game_id": str(source.snapshot.game_id),
                    "recording_generation": event["generation"],
                    "event_sequence": event["d2"],
                    "source_event_id": str(event["id"]),
                    "event_kind": event["event_kind"],
                    "d2": event["d2"],
                    "target_generation": event["target_generation"],
                    "target_event_sequence": event["target_d1"],
                    "expected_version": event["expected_version"],
                    "change_order": event["change_order"],
                    "is_tombstone": "true" if event["is_tombstone"] else "false",
                    "replaced_at": _jst_text(
                        cast(datetime | None, event["replaced_at"]),
                        "%Y-%m-%d %H:%M:%S",
                    ),
                    "retired_at": _jst_text(
                        cast(datetime | None, event["retired_at"]),
                        "%Y-%m-%d %H:%M:%S",
                    ),
                    "business_payload_json": _json_text(event["payload"]),
                    "state_diff_json": _json_text(event["state_diff"]),
                },
            )
        return
    if name == "runners.csv":
        for play in source.iter_plays():
            play_id = cast(UUID, play["id"])
            for runner in source.iter_runners_for((play_id,)):
                yield _row(
                    source,
                    name,
                    {
                        "game_id": str(source.snapshot.game_id),
                        "recording_generation": None,
                        "event_sequence": None,
                        "source_event_id": str(play["source_event_id"]),
                        "play_row_id": str(play_id),
                        "runner_row_id": str(runner["id"]),
                        "base": runner["base"],
                        "runner_id": str(runner["runner_id"]),
                        "responsible_pitcher_id": str(runner["responsible_pitcher_id"]),
                        "status": runner["status"],
                        "status_source": runner["status_source"],
                        "retired_at": _jst_text(
                            cast(datetime | None, runner["retired_at"]),
                            "%Y-%m-%d %H:%M:%S",
                        ),
                        "source_json": _json_text(runner),
                    },
                )
        return
    if name == "lineups.csv":
        for lineup in source.lineups:
            yield _row(
                source,
                name,
                {
                    "game_id": str(source.snapshot.game_id),
                    "lineup_id": str(lineup["id"]),
                    "team_record_id": str(lineup["team_record_id"]),
                    "entries_json": _json_text(
                        lineup["entries_with_uniform_number_snapshot"]
                    ),
                },
            )
        return
    if name == "participations.csv":
        for row in source.iter_participations():
            yield _row(
                source,
                name,
                {
                    "game_id": str(source.snapshot.game_id),
                    "participation_id": str(row["id"]),
                    "source_json": _json_text(row),
                },
            )
        return
    if name == "game.csv":
        yield _row(
            source,
            name,
            {
                "game_id": str(source.snapshot.game_id),
                "source_json": _json_text(source.game),
            },
        )
        return
    if name == "references.csv":
        for team_id, team in sorted(source.teams.items()):
            yield _row(
                source,
                name,
                {
                    "game_id": str(source.snapshot.game_id),
                    "reference_kind": "team_record",
                    "reference_id": str(team_id),
                    "source_json": _json_text(team),
                },
            )
        for player_id, player in sorted(source.players.items()):
            yield _row(
                source,
                name,
                {
                    "game_id": str(source.snapshot.game_id),
                    "reference_kind": "player",
                    "reference_id": str(player_id),
                    "source_json": _json_text(player),
                },
            )
        for (category, key), row in sorted(source.tenant_vocabularies.items()):
            yield _row(
                source,
                name,
                {
                    "game_id": str(source.snapshot.game_id),
                    "reference_kind": f"tenant_vocabulary:{category}",
                    "reference_id": key,
                    "source_json": _json_text(row),
                },
            )
        return
    if name == "projections.csv":
        for play in source.iter_plays():
            play_id = cast(UUID, play["id"])
            runners = tuple(source.iter_runners_for((play_id,)))
            cells, missing = project_play_cells(source, play, runners)
            yield _row(
                source,
                name,
                {
                    "game_id": str(source.snapshot.game_id),
                    "recording_generation": _generation(play),
                    "event_sequence": None,
                    "source_event_id": str(play["source_event_id"]),
                    "projection_kind": "play_export_projection",
                    "source_version": play["version"],
                    "source_json": _json_text(
                        {
                            "values": cells,
                            "missing": [
                                {
                                    "header": item.header,
                                    "column_index": item.column_index,
                                    "supply_group": item.supply_group,
                                    "producer": item.producer,
                                }
                                for item in missing
                            ],
                        }
                    ),
                },
            )
        return
    if name == "preserved_sources.csv":
        return
    raise ValueError("未登録の出力ファイルです")


def _row(
    source: PlayExportSource,
    name: str,
    values: Mapping[str, object],
) -> SavedCsvRow:
    """固定ヘッダの全キーを検証して一行を作る。"""
    headers = CSV_HEADERS[name]
    if set(values) != set(headers):
        raise ValueError(f"{name}の供給キーが一致しません")
    normalized = {header: _cell(values[header]) for header in headers}
    return SavedCsvRow(
        game_id=source.snapshot.game_id,
        snapshot_id=source.snapshot.snapshot_id,
        values=normalized,
    )


def _cell(value: object) -> str | int | None:
    """CsvCellへ写せる値だけを返す。"""
    if value is None or type(value) in (str, int):
        return cast(str | int | None, value)
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is UUID:
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise ValueError("サイドカーに未対応の値型があります")


def _json_text(value: object) -> str:
    """業務JSONを正規形で保持する。"""
    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _json_value(value: object) -> object:
    """JSONへ写せる不変値へ変換する。"""
    if value is None or type(value) in (str, int, float, bool):
        return value
    if type(value) is UUID:
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, MappingProxyType):
        return {str(key): _json_value(item) for key, item in value.items()}
    raise ValueError("JSONへ写せない保存値です")


def _generation(play: Mapping[str, Any]) -> int | None:
    """PlayRowから記録世代を引く補助。"""
    return cast(int | None, play.get("generation"))
