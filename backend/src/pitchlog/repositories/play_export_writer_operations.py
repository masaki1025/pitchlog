"""毎球CSV同TX保存の一回私有SQLsiteを閉じる。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping, cast
from uuid import UUID

from sqlalchemy import BigInteger, LargeBinary, String, Uuid, bindparam, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.functions import Function
from sqlalchemy.sql.selectable import Select

from pitchlog.exports.play_rows import CSV_HEADERS
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    FunctionOperationRegistration,
)
from pitchlog.repositories.stats_native_operations import _same_statement
from pitchlog.repositories.tokens import TenantOperationToken

if TYPE_CHECKING:
    from pitchlog.sync.stats_native_hook import _NativeStatsSource

_OPERATION = "PLAY_EXPORT_WRITER:save_snapshot"
_CAPABILITY = "CAP:play_export_writer:save_snapshot"
_FUNCTION = "stats_api.save_writer_play_export_snapshot"
_COLUMNS = frozenset(CSV_HEADERS["plays.csv"])
_DIRECT = _COLUMNS - frozenset({"球数", "top_score", "bottom_score"})
_INPUTS = (
    ("attempt_id", Uuid(as_uuid=True)),
    ("phase_id", Uuid(as_uuid=True)),
    ("source_event_id", Uuid(as_uuid=True)),
    ("fact_version_id", Uuid(as_uuid=True)),
    ("source_set_sha256", String()),
    ("revision", BigInteger()),
    ("binding_nonce", LargeBinary()),
    ("direct_json", JSONB()),
)


@dataclass(frozen=True, slots=True, init=False)
class _SaveExportSnapshotCall(TenantOperationToken):
    """値型単独からwriter資格を発行しない私有token。"""

    attempt_id: UUID
    phase_id: UUID
    source_event_id: UUID
    fact_version_id: UUID
    source_set_sha256: str
    revision: int
    binding_nonce: bytes = field(repr=False)
    direct_json: dict[str, str | None] = field(repr=False)

    def __new__(cls, *args, **kwargs):
        """通常構築を拒否する。"""
        raise FunctionOperationError("毎球CSVの私有tokenは生成できません")

    @property
    def capability_id(self) -> str:
        """閉じた保存能力を示す。"""
        return _CAPABILITY


@dataclass(frozen=True, slots=True)
class PlayExportWriterCall:
    """実行資格でなく固定SQLと値だけを保持する。"""

    statement: Select[Any]
    parameters: Mapping[str, object] = field(repr=False)


def _statement() -> Select[Any]:
    """単一function identityと8引数の型付きSelectを構成する。"""
    result = Function(
        "save_writer_play_export_snapshot",
        *(bindparam(name, type_=kind) for name, kind in _INPUTS),
        packagenames=("stats_api",),
        type_=Uuid(as_uuid=True),
    ).label("play_row_id")
    return select(result)


def _closed_direct(direct: object) -> dict[str, str | None]:
    """JSONB化前に85列のexact keyと有限scalarを確認する。"""
    if (
        type(direct) is not dict
        or set(direct) != _DIRECT
        or any(type(value) not in (str, type(None)) for value in direct.values())
        or any(type(value) is str and "\x00" in value for value in direct.values())
    ):
        raise FunctionOperationError("毎球CSVの保存列が不正")
    return cast(dict[str, str | None], direct)


def build_save_snapshot_call(
    source: _NativeStatsSource,
    fact_version_id: UUID,
    source_set_sha256: str,
    revision: int,
    direct: dict[str, str | None],
) -> PlayExportWriterCall:
    """真正scope側で照合したsource/版から固定引数だけを組む。"""
    from pitchlog.sync.stats_native_hook import _NativeStatsSource

    if (
        type(source) is not _NativeStatsSource
        or type(fact_version_id) is not UUID
        or type(source_set_sha256) is not str
        or re.fullmatch(r"[a-f0-9]{64}", source_set_sha256) is None
        or type(revision) is not int
        or not 1 <= revision < 2**63
        or type(source.binding_nonce) is not bytes
        or len(source.binding_nonce) != 32
    ):
        raise FunctionOperationError("毎球CSVのwriter値が不正")
    values: dict[str, object] = {
        "attempt_id": source.attempt_id,
        "phase_id": source.phase_id,
        "source_event_id": source.source_event_id,
        "fact_version_id": fact_version_id,
        "source_set_sha256": source_set_sha256,
        "revision": revision,
        "binding_nonce": source.binding_nonce,
        "direct_json": _closed_direct(direct),
    }
    return PlayExportWriterCall(_statement(), MappingProxyType(values))


def _private_decoder(_result):
    """汎用decoderから私有保存成功を復元しない。"""
    raise FunctionOperationError("毎球CSVは私有writerだけが読取れます")


def _shape() -> dict[str, Any]:
    """固定登録の全フィールドを同じ宣言から組む。"""
    return {
        "operation_id": _OPERATION,
        "token_type": _SaveExportSnapshotCall,
        "capability_id": _CAPABILITY,
        "function_id": _FUNCTION,
        "statement": _statement(),
        "input_fields": tuple(
            (name, dict if name == "direct_json" else kind.python_type)
            for name, kind in _INPUTS
        ),
        "result_fields": (("play_row_id", UUID),),
        "min_rows": 1,
        "max_rows": 1,
        "decoder": _private_decoder,
        "nonempty_inputs": (),
        "nullable_results": (),
        "aware_datetime_results": (),
    }


def validate_registration(registration: object) -> None:
    """同時に書き換えた偽SQL/型を初期化と実呼出しで拒否する。"""
    if type(registration) is not FunctionOperationRegistration:
        raise FunctionOperationError("毎球CSV登録の実型が不正")
    expected = _shape()
    for key, value in expected.items():
        observed = getattr(registration, key)
        if key == "statement":
            if not _same_statement(observed, value):
                raise FunctionOperationError("毎球CSVのSQL構造が不一致")
        elif observed != value:
            raise FunctionOperationError("毎球CSVの登録値が不一致")
    object.__setattr__(registration, "statement", expected["statement"])


SAVE_EXPORT_SNAPSHOT_OPERATION = FunctionOperationRegistration(**_shape())


def require_private_save_call(call: PlayExportWriterCall, registry: Mapping) -> None:
    """公開Portと切り離し、実登録の固定SQLと全bindだけを許す。"""
    expected = SAVE_EXPORT_SNAPSHOT_OPERATION
    if registry.get(_SaveExportSnapshotCall) is not expected:
        raise FunctionOperationError("毎球CSVの登録が不一致")
    validate_registration(expected)
    if (
        type(call) is not PlayExportWriterCall
        or not _same_statement(call.statement, expected.statement)
        or tuple(call.parameters) != tuple(name for name, _ in _INPUTS)
    ):
        raise FunctionOperationError("毎球CSVの呼出しが不一致")


def decode_saved_play(rows: object, expected_play: UUID) -> None:
    """保存成功を行数と真正play idの一致でのみ受理する。"""
    if (
        type(rows) is not tuple
        or len(rows) != 1
        or type(rows[0]) is not tuple
        or len(rows[0]) != 1
        or type(rows[0][0]) is not UUID
        or rows[0][0] != expected_play
    ):
        raise FunctionOperationError("毎球CSV保存応答が不一致")
