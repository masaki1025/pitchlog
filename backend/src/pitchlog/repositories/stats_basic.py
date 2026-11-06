"""基本成績のread固定関数を閉じたtokenとして登録する。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Function,
    Integer,
    String,
    Uuid,
    bindparam,
    column,
    select,
)
from sqlalchemy.sql.selectable import Select

from pitchlog.repositories.function_operations import FunctionOperationRegistration
from pitchlog.repositories.tokens import (
    TenantOperationResult,
    TenantOperationToken,
)
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

_SHA256 = SOURCE_MODEL_HASH
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_GROUPS = {
    "official": ("game_official", "game_semi_official"),
    "practice": ("game_open", "game_intrasquad", "game_other"),
    "all": (
        "game_official",
        "game_semi_official",
        "game_open",
        "game_intrasquad",
        "game_other",
    ),
}


def _require_sha(value: object) -> None:
    """現在の共通model hashだけを受理する。"""
    if value != _SHA256:
        raise ValueError("成績model hashが不一致です")


@dataclass(frozen=True, slots=True)
class ReadBasicStatsToken(TenantOperationToken):
    """試合またはJST暦年の基本成績を固定関数で読む。

    ``game_id`` が空なら暦年read、UUIDなら試合readである。公式/暫定は
    試合readだけが切り替え、暦年readは常に終了確定のみを対象にする。
    """

    game_id: str
    year_start: str
    year_end: str
    category: str
    official: bool
    after_player_id: str
    page_size: int
    model_sha256: str = _SHA256
    raw_game_type_keys: str = ""

    def __post_init__(self) -> None:
        """型・範囲・区分写像・cursorを実行前に閉じる。"""
        if type(self.game_id) is not str or (
            self.game_id and _UUID_RE.fullmatch(self.game_id) is None
        ):
            raise ValueError("game_idが不正です")
        if type(self.official) is not bool:
            raise ValueError("officialが不正です")
        if type(self.after_player_id) is not str or (
            self.after_player_id and _UUID_RE.fullmatch(self.after_player_id) is None
        ):
            raise ValueError("cursorが不正です")
        if type(self.page_size) is not int or not 1 <= self.page_size <= 200:
            raise ValueError("page_sizeが不正です")
        _require_sha(self.model_sha256)
        if self.game_id:
            if self.year_start or self.year_end:
                raise ValueError("試合readに暦年境界は指定できません")
            if self.category != "all":
                raise ValueError("試合readの区分はall固定です")
        else:
            if self.official is not True:
                raise ValueError("暦年readは終了確定のみです")
            if type(self.year_start) is not str or type(self.year_end) is not str:
                raise ValueError("暦年境界の型が不正です")
            if not self.year_start or not self.year_end:
                raise ValueError("暦年境界が必要です")
            start = re.fullmatch(r"([0-9]{4})-01-01T00:00:00[+]09:00", self.year_start)
            end = re.fullmatch(r"([0-9]{4,5})-01-01T00:00:00[+]09:00", self.year_end)
            if (
                start is None
                or end is None
                or not 1 <= int(start[1]) <= 9999
                or int(end[1]) != int(start[1]) + 1
            ):
                raise ValueError("JST暦年境界が不正です")
            if self.category not in _GROUPS:
                raise ValueError("区分名が不正です")
        expected = ",".join(_GROUPS[self.category])
        object.__setattr__(self, "raw_game_type_keys", expected)

    @property
    def capability_id(self) -> str:
        """既存の成績read capabilityだけを返す。"""
        return "CAP:stats_basic:read"


def _statement() -> Select[Any]:
    """登録型検査用の固定table-valued function Selectを返す。"""
    table = Function(
        "read_basic_stats",
        bindparam("tenant_id", type_=Uuid()),
        bindparam("game_id", type_=String()),
        bindparam("year_start", type_=String()),
        bindparam("year_end", type_=String()),
        bindparam("category", type_=String()),
        bindparam("raw_game_type_keys", type_=String()),
        bindparam("official", type_=Boolean()),
        bindparam("after_player_id", type_=String()),
        bindparam("page_size", type_=Integer()),
        bindparam("model_sha256", type_=String()),
        packagenames=("stats_basic_api",),
    ).table_valued(
        column("player_id", Uuid()),
        column("player_name", String()),
        column("uniform_number", String()),
        column("team_record_id", Uuid()),
        column("team_name", String()),
        column("metrics_json", String()),
    )
    return select(*(table.c[name] for name in table.c.keys()))


def _decode(result: TenantOperationResult) -> TenantOperationResult:
    """値の意味はAPI層が閉じて読む。ここでは行をそのまま返す。"""
    return result


STATS_BASIC_FUNCTION_OPERATIONS: tuple[FunctionOperationRegistration, ...] = (
    FunctionOperationRegistration(
        operation_id="STATS_BASIC:read",
        token_type=ReadBasicStatsToken,
        capability_id="CAP:stats_basic:read",
        function_id="stats_basic_api.read_basic_stats",
        statement=_statement(),
        input_fields=(
            ("game_id", str),
            ("year_start", str),
            ("year_end", str),
            ("category", str),
            ("raw_game_type_keys", str),
            ("official", bool),
            ("after_player_id", str),
            ("page_size", int),
            ("model_sha256", str),
        ),
        result_fields=(
            ("player_id", UUID),
            ("player_name", str),
            ("uniform_number", str),
            ("team_record_id", UUID),
            ("team_name", str),
            ("metrics_json", str),
        ),
        min_rows=0,
        max_rows=1000,
        decoder=_decode,
    ),
)
