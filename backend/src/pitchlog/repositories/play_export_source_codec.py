"""CSV同RR source identityの閉値契約。計算・認可資格を発行しない。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, cast
from uuid import UUID

from sqlalchemy import BigInteger, Integer, String, Uuid, bindparam, column, select
from sqlalchemy.sql.functions import Function
from sqlalchemy.sql.selectable import Select

from pitchlog.repositories.tokens import TenantOperationToken

FUNCTION_ID = "stats_api.read_play_export_source_page"
OPERATION_ID = "PLAY_EXPORT_SOURCES:read_page"
CAPABILITY_ID = "CAP:play_export_sources:read"
_INPUTS = (
    ("game_id", Uuid(as_uuid=True)),
    ("after_generation", BigInteger()),
    ("after_d1", BigInteger()),
    ("page_size", Integer()),
)
_OUTPUTS = (
    ("fact_version_id", Uuid(as_uuid=True)),
    ("revision", BigInteger()),
    ("source_set_sha256", String()),
    ("source_count", BigInteger()),
    ("completion_state", String()),
    ("transaction_id", String()),
    ("recording_generation", BigInteger()),
    ("d1", BigInteger()),
    ("d2", BigInteger()),
    ("source_event_id", Uuid(as_uuid=True)),
    ("play_row_id", Uuid(as_uuid=True)),
    ("slot_version", BigInteger()),
    ("play_row_version", BigInteger()),
    ("base_event_id", Uuid(as_uuid=True)),
    ("source_fingerprint", String()),
)


class PlayExportSourceError(ValueError):
    """閉形・版・同snapshot・順序違反を固定文言で拒否する。"""

    def __init__(self) -> None:
        """原要求や資格を例外へ含めない。"""
        super().__init__("毎球CSVのsource identityが不正又は未供給です")


def _need(ok: bool) -> None:
    """不正値を正準形へ補修しない。"""
    if not ok:
        raise PlayExportSourceError


def _integer(value: object, minimum: int = 1) -> None:
    """bool/小数/非正準文字列を整数として受けない。"""
    _need(type(value) is int and minimum <= value < 2**63)


@dataclass(frozen=True, slots=True)
class ReadExportSourcePageToken(TenantOperationToken):
    """固定値だけを保持し、単独では実行資格を持たない。"""

    game_id: UUID
    after_generation: int | None = None
    after_d1: int | None = None
    page_size: int = 500

    def __post_init__(self) -> None:
        """試合とcursor全組、最大pageを閉じる。"""
        _need(type(self.game_id) is UUID)
        if self.after_generation is not None or self.after_d1 is not None:
            _integer(self.after_generation)
            _integer(self.after_d1)
        _integer(self.page_size)
        _need(self.page_size <= 500)

    @property
    def capability_id(self) -> str:
        """rootの正式登録待ちである限定読取能力を示す。"""
        return CAPABILITY_ID


@dataclass(frozen=True, slots=True)
class SourceReadCall:
    """固定SQLと値だけを保持し、認可成功を表さない。"""

    statement: Select[Any]
    parameters: Mapping[str, object]


def build_source_read_call(token: ReadExportSourcePageToken) -> SourceReadCall:
    """変造済みtokenも再検査して固定関数だけを呼ぶ。"""
    _need(type(token) is ReadExportSourcePageToken)
    token.__post_init__()
    table = Function(
        "read_play_export_source_page",
        *(bindparam(name, type_=kind) for name, kind in _INPUTS),
        packagenames=("stats_api",),
    ).table_valued(*(column(name, kind) for name, kind in _OUTPUTS))
    return SourceReadCall(
        select(*table.c),
        MappingProxyType({name: getattr(token, name) for name, _ in _INPUTS}),
    )


@dataclass(frozen=True, slots=True)
class SourceVersion:
    """実読取結果の全pageを同じ版/snapshotへ束縛する値。"""

    fact_version_id: UUID
    revision: int
    source_set_sha256: str
    source_count: int
    completion_state: str
    transaction_id: str


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    """真正S会員の物理原本と論理位置を写す値。"""

    recording_generation: int
    d1: int
    d2: int
    source_event_id: UUID
    play_row_id: UUID
    slot_version: int
    play_row_version: int
    base_event_id: UUID
    source_fingerprint: str

    @property
    def ordering_key(self) -> tuple[int, int]:
        """唯一S pageのkeysetを返す。"""
        return self.recording_generation, self.d1


@dataclass(frozen=True, slots=True)
class SourcePage:
    """0件はheader sentinelだけで表し、偽行を作らない。"""

    version: SourceVersion
    rows: tuple[SourceIdentity, ...]


def decode_source_page(
    rows: object,
    token: ReadExportSourcePageToken,
    expected: SourceVersion | None = None,
) -> SourcePage:
    """返却の余剰/欠落/古い版/逆行/部分NULLを拒否する。"""
    build_source_read_call(token)
    if type(rows) is not tuple:
        raise PlayExportSourceError
    _need(1 <= len(rows) <= token.page_size)
    header = None
    result = []
    last = (
        None
        if token.after_generation is None
        else (token.after_generation, cast(int, token.after_d1))
    )
    for row in rows:
        if type(row) is not tuple:
            raise PlayExportSourceError
        row = cast(tuple[Any, ...], row)
        _need(len(row) == len(_OUTPUTS))
        version, revision, digest, count, completion, snapshot = row[:6]
        _need(type(version) is UUID)
        _integer(revision)
        _need(type(digest) is str and re.fullmatch(r"[a-f0-9]{64}", digest) is not None)
        _integer(count, 0)
        _need(
            type(completion) is str
            and completion in ("current_open", "confirmed_ended")
        )
        _need(
            type(snapshot) is str
            and re.fullmatch(r"[0-9]+:[0-9]+:(?:[0-9]+(?:,[0-9]+)*)?", snapshot)
            is not None
        )
        current = SourceVersion(*row[:6])
        _need(header is None or current == header)
        _need(expected is None or current == expected)
        header = current
        if row[6:] == (None,) * 9:
            _need(len(rows) == 1)
            _need(count == 0 or last is not None)
            continue
        _need(all(value is not None for value in row[6:]))
        generation, d1, d2, event, play, slot, play_version, base, fingerprint = row[6:]
        for value in (generation, d1, slot, play_version):
            _integer(value)
        _integer(d2, -(2**63))
        _need(all(type(value) is UUID for value in (event, play, base)))
        _need(
            type(fingerprint) is str
            and re.fullmatch(r"(?:wire-v1:)?[a-f0-9]{64}", fingerprint) is not None
        )
        identity = SourceIdentity(*row[6:])
        _need(last is None or identity.ordering_key > last)
        last = identity.ordering_key
        result.append(identity)
    if header is None:
        raise PlayExportSourceError
    _need(len(result) <= header.source_count)
    return SourcePage(header, tuple(result))
