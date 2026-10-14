"""D5 の内部候補、入力原本の同一性、競合時の再照合を扱う。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, cast
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from pitchlog.db.sync_protocol.models import IdempotencyLedger
from pitchlog.repositories.tokens import ImmutableValue, TenantOperationResult
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.model import ABSENT, SyncEvent, SyncRequest
from pitchlog.sync.tokens import (
    IdempotencyLedgerInsertToken,
    IdempotencyLedgerReadToken,
)

type D5Path = Literal["P1", "P2", "P3", "P4"]
type CandidateKind = Literal["stored_result", "conflict", "unused"]

_LEDGER_COLUMNS = tuple(IdempotencyLedger.__table__.c.keys())
_D5_CONSTRAINTS = frozenset({"pk_idempotency_ledger", "uq_idempotency_ledger_kind"})


@dataclass(frozen=True, slots=True)
class StoredResult:
    """台帳の確定済み結果。JSONB の値は実行境界で不変化済み。"""

    kind: str
    source_fingerprint: str
    result: Mapping[str, ImmutableValue]
    reason: str | None


@dataclass(frozen=True, slots=True)
class D5Candidate:
    """外部の ACK・境界結果をまだ確定しない D5 の内部候補。"""

    kind: CandidateKind
    boundary: Literal["B3b", "B13"] | None = None
    stored: StoredResult | None = None


def _json_value(value: object) -> object:
    """不変な入力の JSON コンテナを標準形へ移す。"""
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise TypeError("入力原本の JSON object のキーは文字列が必要")
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if value is None or type(value) in (bool, int, float, str):
        return value
    raise TypeError("入力原本に JSON 以外の値を含められない")


def source_fingerprint(source: Mapping[str, object]) -> str:
    """入力原本の全フィールドを正規化 JSON にして SHA-256 を取る。

    拒否理由など、入力から導出した値は呼び出し側が渡さない。
    """
    normalized = json.dumps(
        _json_value(source),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def event_source(event: SyncEvent) -> dict[str, object]:
    """欠落と null を区別したイベント原本を返す。"""
    source: dict[str, object] = {
        "d5": event.d5,
        "game_id": event.game_id,
    }
    if event.d1 is not None:
        source["d1"] = event.d1
    if event.d4 is not None:
        source["d4"] = event.d4
    # 要求からの欠落を省き、JSON null は値として残す。
    # 種別ごとの V 条件は D5 分類の後段で判定する。
    # 拒否・退避の原本も同じフィールド列挙を使う。
    for attribute, wire_name in _EVENT_SOURCE_FIELDS:
        value = getattr(event, attribute)
        if value is not ABSENT:
            source[wire_name] = value
    return source


def event_source_fingerprint(event: SyncEvent) -> str:
    """S-1 で保持したイベント原本を指紋化する。"""
    return source_fingerprint(event_source(event))


def _stored_result(row: tuple[ImmutableValue, ...]) -> StoredResult:
    """登録済み read operation の列順から台帳の値を取り出す。"""
    if len(row) != len(_LEDGER_COLUMNS):
        raise RuntimeError("D5 台帳の読み取り列数が正本と異なる")
    values = dict(zip(_LEDGER_COLUMNS, row, strict=True))
    kind = values["kind"]
    fingerprint = values["source_fingerprint"]
    result = values["result"]
    reason = values["reason"]
    if (
        type(kind) is not str
        or type(fingerprint) is not str
        or not isinstance(result, Mapping)
        or (reason is not None and type(reason) is not str)
    ):
        raise RuntimeError("D5 台帳の保存結果の型が不正")
    return StoredResult(
        kind, fingerprint, cast(Mapping[str, ImmutableValue], result), reason
    )


def classify_result(
    result: TenantOperationResult, fingerprint: str, path: D5Path
) -> D5Candidate:
    """DI2〜DI4 / I2〜I4 の 3 分類を DB 非依存で決める。"""
    if path not in ("P1", "P2", "P3", "P4"):
        raise ValueError("未知の適用経路")
    if not result.rows:
        return D5Candidate("unused")
    if len(result.rows) != 1:
        raise RuntimeError("同じテナントと D5 に複数の台帳行がある")
    stored = _stored_result(result.rows[0])
    if stored.source_fingerprint == fingerprint:
        return D5Candidate("stored_result", stored=stored)
    return D5Candidate("conflict", boundary="B13" if path == "P3" else "B3b")


def classify_d5(
    handle: _TenantTransaction, d5: UUID, fingerprint: str, path: D5Path
) -> D5Candidate:
    """束縛済みテナントの D5 だけを読んで内部候補に分類する。"""
    return classify_result(
        handle.run(IdempotencyLedgerReadToken(d5)), fingerprint, path
    )


def classify_request_d5(
    handle: _TenantTransaction,
    request: SyncRequest,
    fingerprints: tuple[str, ...] | None = None,
) -> tuple[D5Candidate, ...]:
    """要求内の全 D5 を、後段の結果確定より前に内部候補へ分類する。

    呼び出し側は認可・RG1、P3 では復旧世代照合を先に終える。
    戻り値は要求のイベント列と同じ順で、外部 A5 の確定順ではない。
    """
    if fingerprints is not None and len(fingerprints) != len(request.events):
        raise ValueError("D5 指紋の件数がイベント列と異なる")
    return tuple(
        classify_d5(
            handle,
            UUID(event.d5),
            event_source_fingerprint(event)
            if fingerprints is None
            else fingerprints[index],
            request.path,
        )
        for index, event in enumerate(request.events)
    )


def _d5_unique_violation(error: IntegrityError) -> bool:
    """D5 を含む台帳の一意制約衝突だけを再照合の契機とする。"""
    original = error.orig
    diagnostic = getattr(original, "diag", None)
    return (
        getattr(original, "sqlstate", None) == "23505"
        and getattr(diagnostic, "constraint_name", None) in _D5_CONSTRAINTS
    )


def insert_result_or_recheck(
    handle: _TenantTransaction, token: IdempotencyLedgerInsertToken, path: D5Path
) -> D5Candidate | None:
    """台帳 INSERT だけを SAVEPOINT で保護し、D5 競合なら照合し直す。

    戻り値 ``None`` はこのトランザクションで INSERT したことを表す。
    一意制約以外の失敗と、衝突後に行を観測できない異常は伝播する。
    """
    try:
        handle.run_in_savepoint(token)
    except IntegrityError as error:
        if not _d5_unique_violation(error):
            raise
        candidate = classify_d5(handle, token.d5, token.source_fingerprint, path)
        if candidate.kind == "unused":
            raise RuntimeError("D5 一意制約違反後に先着行を観測できない") from error
        return candidate
    return None


def recheck_and_insert_result(
    handle: _TenantTransaction, token: IdempotencyLedgerInsertToken, path: D5Path
) -> D5Candidate | None:
    """イベント内で D5 を再照合し、未使用の場合だけ確定結果を書く。"""
    candidate = classify_d5(handle, token.d5, token.source_fingerprint, path)
    if candidate.kind != "unused":
        return candidate
    return insert_result_or_recheck(handle, token, path)


class RegistrationSource(Protocol):
    """その場登録を D5 原本に含めるための不変な値の形。"""

    @property
    def temporary_id(self) -> UUID:
        """端末の一時 ID。"""
        ...

    @property
    def team_record_id(self) -> UUID:
        """作成先のチーム記録。"""
        ...

    @property
    def name(self) -> str:
        """選手名。"""
        ...

    @property
    def roster_status_key(self) -> str:
        """在籍区分。"""
        ...


@dataclass(frozen=True, slots=True)
class StoredNegativeResult:
    """拒否・退避の保存済み結果を経路に依存しない形で保持する。"""

    boundary: Literal["B3a", "B4"]
    d3: int
    state: Literal["拒否", "退避"]
    reason: str | None


def decode_stored_negative(stored: StoredResult) -> StoredNegativeResult:
    """台帳の T8・T9 結果を一か所で検証して再掲用に実体化する。"""
    if stored.kind not in {"rejected", "evacuated"}:
        raise RuntimeError("拒否・退避以外の保存済み結果")
    result = stored.result
    state: Literal["拒否", "退避"] = "拒否" if stored.kind == "rejected" else "退避"
    d3 = result.get("d3")
    if (
        result.get("state") != state
        or type(d3) is not int
        or d3 < 0
        or (stored.kind == "rejected" and not stored.reason)
        or (stored.kind == "evacuated" and stored.reason is not None)
    ):
        raise RuntimeError("拒否・退避の保存済み結果の形が不正")
    return StoredNegativeResult(
        "B3a" if stored.kind == "rejected" else "B4",
        d3,
        state,
        stored.reason,
    )


def operation_fingerprint(
    event: SyncEvent, path: D5Path, registration: RegistrationSource | None
) -> str:
    """受理・拒否・退避に共通する D5 内容同一性を一度だけ定義する。"""
    return source_fingerprint(
        {
            "event_fingerprint": event_source_fingerprint(event),
            "path": path,
            "registration": (
                None
                if registration is None
                else {
                    "temporary_id": str(registration.temporary_id),
                    "team_record_id": str(registration.team_record_id),
                    "name": registration.name,
                    "roster_status_key": registration.roster_status_key,
                }
            ),
        }
    )


_EVENT_SOURCE_FIELDS = (
    ("v5", "event_kind"),
    ("v6", "d2"),
    ("v7", "payload"),
    ("v8", "state_diff"),
    ("v9", "replacement_state"),
    ("v10", "target_reference"),
    ("v11", "expected_version"),
)
