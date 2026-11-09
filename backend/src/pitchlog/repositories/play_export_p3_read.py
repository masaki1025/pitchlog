"""P3 CSVの同RR/RO専用有限read候補。登録されないreaderは実行しない。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import islice
from types import MappingProxyType
from typing import cast
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    String,
    Uuid,
    bindparam,
    column,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.functions import Function

from pitchlog.exports.p3_result import saved_result_id
from pitchlog.exports.p3_snapshot import P3SnapshotIdentity
from pitchlog.exports.play_rows import CSV_HEADERS, PlayExportSupplyError
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    FunctionOperationRegistration,
)
from pitchlog.repositories.play_export_source_codec import (
    _OUTPUTS as _SOURCE_OUTPUTS,
)
from pitchlog.repositories.play_export_source_codec import (
    SourceVersion,
)
from pitchlog.repositories.stats_native_operations import (
    _same_metadata,
    _same_statement,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

FUNCTION_ID = "stats_api.read_play_export_p3_snapshots"
OPERATION_ID = "PLAY_EXPORT_P3:read_snapshots"
CAPABILITY_ID = "CAP:play_export_p3:read_snapshots"
_INPUTS = (
    ("game_id", Uuid(as_uuid=True)),
    ("after_generation", BigInteger()),
    ("after_capsule_id", Uuid(as_uuid=True)),
    ("after_d1", BigInteger()),
    ("page_size", Integer()),
)
_ROW_OUTPUTS = (
    ("tenant_id", Uuid(as_uuid=True)),
    ("game_id", Uuid(as_uuid=True)),
    ("internal_generation", BigInteger()),
    ("capsule_id", Uuid(as_uuid=True)),
    ("d1", BigInteger()),
    ("original_play_row_id", Uuid(as_uuid=True)),
    ("effective_event_id", Uuid(as_uuid=True)),
    ("effective_play_row_id", Uuid(as_uuid=True)),
    ("play_row_version", BigInteger()),
    ("item_digest", String()),
    ("capsule_source_set_digest", String()),
    ("capsule_stats_version_id", Uuid(as_uuid=True)),
    ("plays_csv_json", JSONB()),
    ("full_innings_json", JSONB()),
    ("runner_rows_json", JSONB()),
    ("reference_json", JSONB()),
    ("captured_at", DateTime(timezone=True)),
    ("capsule_watermark", BigInteger()),
    ("capsule_target_d1", BigInteger()),
    ("current_head", Boolean()),
    ("item_json", JSONB()),
)
_OUTPUTS = (*_SOURCE_OUTPUTS[:6], ("overlay_count", BigInteger()), *_ROW_OUTPUTS)
_REGISTRATION = None


def _need(ok: bool):
    """値の補修・空欄化で原本不足を隠さない。"""
    if not ok:
        raise PlayExportSupplyError("P3 CSV完成原本の同版coverageが不足しています")


@dataclass(frozen=True, slots=True)
class ReadP3ExportPage(TenantOperationToken):
    """値だけを保持する固定読取token。単独でRR資格を持たない。"""

    game_id: UUID
    after_generation: int | None = None
    after_capsule_id: UUID | None = None
    after_d1: int | None = None
    page_size: int = 500

    def __post_init__(self):
        """cursor全組と正準型/頁上限を検査する。"""
        _need(type(self.game_id) is UUID)
        cursor = (self.after_generation, self.after_capsule_id, self.after_d1)
        if cursor != (None, None, None):
            _need(type(cursor[0]) is int and 0 < cursor[0] < 2**63)
            _need(type(cursor[1]) is UUID)
            _need(type(cursor[2]) is int and 0 < cursor[2] < 2**63)
        _need(type(self.page_size) is int and 1 <= self.page_size <= 500)

    @property
    def capability_id(self):
        """有限登録原本の能力名を返す。"""
        return CAPABILITY_ID


def build_call(token: ReadP3ExportPage):
    """変造済みtokenも再検査し固定関数以外を呼ばない。"""
    _need(type(token) is ReadP3ExportPage)
    token.__post_init__()
    table = Function(
        "read_play_export_p3_snapshots",
        *(bindparam(name, type_=kind) for name, kind in _INPUTS),
        packagenames=("stats_api",),
    ).table_valued(*(column(name, kind) for name, kind in _OUTPUTS))
    return select(*table.c), MappingProxyType(
        {name: getattr(token, name) for name, _ in _INPUTS}
    )


def _deny_generic_decode(_result):
    """汎用executorからRR資格を得る経路を作らない。"""
    raise FunctionOperationError("P3 CSV readは真正同RR scope専用です")


def registration_shape():
    """共有rootの有限family登録に必要な閉宣言だけを返す。"""
    statement, _ = build_call(ReadP3ExportPage(UUID(int=0)))
    result_types = []
    for name, kind in _OUTPUTS:
        result_types.append(
            (
                name,
                list
                if name in {"full_innings_json", "runner_rows_json"}
                else kind.python_type,
            )
        )
    return dict(
        operation_id=OPERATION_ID,
        token_type=ReadP3ExportPage,
        capability_id=CAPABILITY_ID,
        function_id=FUNCTION_ID,
        statement=statement,
        input_fields=tuple((name, kind.python_type) for name, kind in _INPUTS),
        result_fields=tuple(result_types),
        min_rows=1,
        max_rows=500,
        decoder=_deny_generic_decode,
        nonempty_inputs=(),
        nullable_results=tuple(name for name, _ in _ROW_OUTPUTS),
        aware_datetime_results=("captured_at",),
    )


def validate_registration(registration):
    """SQL/全metadataの同時差替えも固定原本へ全照合する。"""
    if type(registration) is not FunctionOperationRegistration:
        raise FunctionOperationError("P3 CSV登録型が不正")
    expected = registration_shape()
    for key, wanted in expected.items():
        actual = getattr(registration, key)
        if not (
            _same_statement(actual, wanted)
            if key == "statement"
            else _same_metadata(actual, wanted)
        ):
            raise FunctionOperationError("P3 CSV登録が固定原本と不一致")
    object.__setattr__(registration, "statement", expected["statement"])


def p3_read_operation():
    """rootが予約familyを供給した後のみ固定登録を作る。"""
    global _REGISTRATION
    if _REGISTRATION is None:
        _REGISTRATION = FunctionOperationRegistration(**registration_shape())
    validate_registration(_REGISTRATION)
    return _REGISTRATION


def run_qualified_p3_read(handle, operation):
    """自由Session/runnerを受けず実RR同Sessionだけで固定関数を実行する。"""
    from pitchlog.repositories import operation_registry, transaction

    transaction._require_play_export_scope(handle)
    _need(type(operation) is ReadP3ExportPage)
    spec = p3_read_operation()
    if operation_registry.FUNCTION_OPERATION_REGISTRY.get(type(operation)) is not spec:
        raise FunctionOperationError("P3 CSV readが未登録又は置換済み")
    statement, params = build_call(operation)
    if not _same_statement(spec.statement, statement):
        raise FunctionOperationError("P3 CSV read SQLが不一致")
    runtime = transaction._TRANSACTION_RUNTIMES.get(handle._state_key)
    if runtime is None:
        raise FunctionOperationError("P3 CSV read scopeが失効")
    with runtime[0].execute(statement, params) as result:
        rows = tuple(tuple(row) for row in islice(result, operation.page_size + 1))
    transaction._require_play_export_scope(handle)
    _need(transaction._TRANSACTION_RUNTIMES.get(handle._state_key) is runtime)
    _need(1 <= len(rows) <= operation.page_size)
    return TenantOperationResult(rows)


def decode_page(rows, token: ReadP3ExportPage, expected: SourceVersion):
    """真正read後の全header/順序/17列/item所属を閉検査する値境界。"""
    build_call(token)
    _need(type(expected) is SourceVersion and type(rows) is tuple)
    _need(1 <= len(rows) <= token.page_size)
    last = (
        None
        if token.after_generation is None
        else (
            token.after_generation,
            cast(UUID, token.after_capsule_id),
            cast(int, token.after_d1),
        )
    )
    total = None
    result = []
    for raw in rows:
        _need(type(raw) is tuple and len(raw) == len(_OUTPUTS))
        _need(
            all(
                type(a) is type(b) and a == b
                for a, b in zip(raw[:6], asdict(expected).values(), strict=True)
            )
        )
        _need(type(raw[6]) is int and 0 <= raw[6] < 2**63)
        _need(total is None or total == raw[6])
        total = raw[6]
        if raw[7:] == (None,) * len(_ROW_OUTPUTS):
            _need(len(rows) == 1)
            continue
        row = dict(zip((name for name, _ in _ROW_OUTPUTS), raw[7:], strict=True))
        identity = validate_snapshot_row(row, token.game_id)
        key = (identity.internal_generation, identity.capsule_id, identity.d1)
        _need(last is None or key > last)
        last = key
        result.append(row)
    return total, tuple(result)


class ReadP3ExportSnapshots:
    """既真正S取得と同じscopeだけを借りる一回限りの歴代原本reader。"""

    __slots__ = ("_handle", "_state_key", "_game", "_version", "_started")

    def __init__(self, handle, game_id: UUID, version: SourceVersion):
        """自由executorを受けず、実同RR handleと既SourceVersionだけを束縛する。"""
        from pitchlog.repositories.transaction import _require_play_export_scope

        _require_play_export_scope(handle)
        ReadP3ExportPage(game_id)
        _need(type(version) is SourceVersion)
        self._handle, self._state_key = handle, handle._state_key
        self._game, self._version, self._started = game_id, version, False

    def pages(self, *, page_size: int = 500):
        """500件keysetを反復し、件数/版/同snapshot/欠落を完全照合する。"""
        from pitchlog.repositories.transaction import _require_play_export_scope

        _need(not self._started)
        self._started = True
        cursor = (None, None, None)
        expected_count = None
        count = 0
        while True:
            _require_play_export_scope(self._handle)
            _need(self._handle._state_key is self._state_key)
            token = ReadP3ExportPage(self._game, *cursor, page_size)
            result = self._handle.run(token)
            _need(type(result) is TenantOperationResult)
            total, rows = decode_page(result.rows, token, self._version)
            _need(expected_count is None or expected_count == total)
            expected_count = total
            count += len(rows)
            _need(type(expected_count) is int and count <= expected_count)
            final = len(rows) < page_size
            if final:
                _need(count == expected_count)
            if rows:
                last = rows[-1]
                cursor = (last["internal_generation"], last["capsule_id"], last["d1"])
                yield rows
            if final:
                return


def _uuid_text(value):
    """UUID文字列を補修せず、非正準・別型を拒否する。"""
    _need(type(value) is str)
    try:
        _need(str(UUID(value)) == value)
    except ValueError as error:
        raise PlayExportSupplyError("P3 CSV監査参照が非正準です") from error


def _reference(value, identity, target):
    """自由参照JSONで現在資格を偽装しないよう保存codecの閉集合を確認する。"""
    _need(
        set(value)
        == {
            "formatVersion",
            "priorCapsuleId",
            "priorNativeVersionId",
            "priorCheckpoint",
            "replacementResult",
        }
    )
    _need(value["formatVersion"] == "p3-csv-references-v1")
    if value["priorCapsuleId"] is not None:
        _uuid_text(value["priorCapsuleId"])
    _uuid_text(value["priorNativeVersionId"])
    cp = value["priorCheckpoint"]
    _need(type(cp) is dict and set(cp) == {"id", "revision", "digest"})
    _uuid_text(cp["id"])
    _need(type(cp["revision"]) is int and 0 < cp["revision"] < 2**63)
    _need(
        type(cp["digest"]) is str
        and re.fullmatch(r"[a-f0-9]{64}", cp["digest"]) is not None
    )
    reference = value["replacementResult"]
    if identity.d1 != target:
        _need(reference is None)
        return
    _need(
        type(reference) is dict
        and set(reference)
        == {"id", "key", "displayName", "capturedAt", "capsuleId", "effectiveEventId"}
    )
    for name in ("id", "capsuleId", "effectiveEventId"):
        _uuid_text(reference[name])
    _need(
        reference["capsuleId"] == str(identity.capsule_id)
        and reference["effectiveEventId"] == str(identity.effective_event_id)
    )
    _need(
        type(reference["key"]) is str
        and reference["key"] in {"batting-result.ball", "batting-result.called-strike"}
    )
    _need(type(reference["displayName"]) is str and bool(reference["displayName"]))
    _need(type(reference["capturedAt"]) is str)
    try:
        _need(datetime.fromisoformat(reference["capturedAt"]).utcoffset() is not None)
    except ValueError as error:
        raise PlayExportSupplyError("P3 CSV訂正時刻の参照が不正です") from error


def validate_snapshot_row(row, game_id: UUID):
    """データの全値境界だけを再検査し、単独ではread/認可資格を作らない。"""
    from pitchlog.exports.p3_projection import p3_input_origin
    from pitchlog.sync.idempotency import source_fingerprint

    _need(type(row) is dict and set(row) == {name for name, _ in _ROW_OUTPUTS})
    identity = P3SnapshotIdentity(
        **{name: row[name] for name in P3SnapshotIdentity.__dataclass_fields__}
    )
    _need(row["game_id"] == game_id)
    for name in ("capsule_watermark", "capsule_target_d1"):
        _need(type(row[name]) is int and 0 < row[name] < 2**63)
    _need(
        identity.d1 <= row["capsule_watermark"]
        and row["capsule_target_d1"] <= row["capsule_watermark"]
    )
    _need(type(row["current_head"]) is bool)
    value = row["plays_csv_json"]
    _need(type(value) is dict and set(value) == set(CSV_HEADERS["plays.csv"]))
    _need(all(type(v) is str or v is None for v in value.values()))
    _need(
        type(row["full_innings_json"]) is list
        and type(row["runner_rows_json"]) is list
        and len(row["runner_rows_json"]) <= 3
    )
    _need(
        type(row["captured_at"]) is datetime
        and row["captured_at"].utcoffset() is not None
    )
    item = row["item_json"]
    _need(
        type(item) is dict
        and set(item)
        == {
            "tenant_id",
            "game_id",
            "internal_generation",
            "capsule_id",
            "d1",
            "d2",
            "state",
            "original_event_id",
            "effective_event_id",
            "original_play_row_id",
            "effective_play_row_id",
            "original_payload",
            "original_history_entry",
            "original_play_row",
            "original_play_runners",
            "payload",
            "history_entry",
            "play_row",
            "play_runners",
            "item_digest",
        }
    )
    _need(type(item["d2"]) is int and 0 < item["d2"] < 2**63)
    _need(type(item["state"]) is str and item["state"] in {"unchanged", "corrected"})
    core = {
        k: v
        for k, v in item.items()
        if k
        not in {
            "tenant_id",
            "game_id",
            "internal_generation",
            "capsule_id",
            "item_digest",
        }
    }
    _need(source_fingerprint(core) == identity.item_digest)
    _need(type(row["reference_json"]) is dict)
    _reference(row["reference_json"], identity, row["capsule_target_d1"])
    if identity.d1 == row["capsule_target_d1"]:
        _need(
            row["plays_csv_json"][CSV_HEADERS["plays.csv"][45]]
            == row["reference_json"]["replacementResult"]["displayName"]
        )
    for field, wanted in (
        ("tenant_id", str(identity.tenant_id)),
        ("game_id", str(identity.game_id)),
        ("internal_generation", identity.internal_generation),
        ("capsule_id", str(identity.capsule_id)),
        ("d1", identity.d1),
        ("item_digest", identity.item_digest),
        ("original_play_row_id", str(identity.original_play_row_id)),
        ("effective_event_id", str(identity.effective_event_id)),
        ("effective_play_row_id", str(identity.effective_play_row_id)),
    ):
        _need(type(item.get(field)) is type(wanted) and item[field] == wanted)
    _need(item.get("play_runners") == row["runner_rows_json"])
    if identity.d1 >= row["capsule_target_d1"]:
        origin = row["plays_csv_json"][CSV_HEADERS["plays.csv"][72]]
        _need(
            p3_input_origin(
                origin,
                item["payload"],
                identity,
                target=identity.d1 == row["capsule_target_d1"],
            )
            == origin
        )
    physical = item.get("play_row")
    _need(type(physical) is dict)
    if identity.d1 == row["capsule_target_d1"]:
        key = row["reference_json"]["replacementResult"]["key"]
        _need(
            type(item.get("payload")) is dict
            and saved_result_id(item["payload"]) == key
            and item["play_row"].get("batting_result_key") == key
        )
    physical = item.get("play_row")
    _need(
        type(physical) is dict
        and physical.get("id") == str(identity.effective_play_row_id)
        and physical.get("source_event_id") == str(identity.effective_event_id)
        and type(physical.get("version")) is int
        and physical["version"] == identity.play_row_version
    )
    return identity
