"""成績5固定関数の値だけを束縛する。資格・登録・実行は発行しない。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping, cast
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Uuid,
    bindparam,
    column,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.functions import Function
from sqlalchemy.sql.selectable import Select
from sqlalchemy.types import TypeDecorator

from pitchlog.stats.generated.receiver import METRIC_IDS, SOURCE_MODEL_HASH


class StatsFunctionCodecError(ValueError):
    """値の閉契約への違反。入力値やnonceを例外に含めない。"""

    def __init__(self) -> None:
        """固定文言だけで失敗する。"""
        super().__init__("成績固定関数の値が閉契約と一致しません")


def _require(ok: bool) -> None:
    """偽の条件を補完せず拒否する。"""
    if not ok:
        raise StatsFunctionCodecError()


def _uuid(value: object) -> None:
    """UUID文字列やsubclassをUUIDオブジェクトへ変換しない。"""
    _require(type(value) is UUID)


def _bigint(value: object, minimum: int = -(2**63)) -> None:
    """boolやfloatを整数として近似しない。"""
    _require(type(value) is int and minimum <= value < 2**63)


def _hash(value: object) -> None:
    """正準小文字64桁以外を修復しない。"""
    _require(type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None)


def _model(value: object) -> None:
    """既唯一モデル版だけを受ける。"""
    _require(type(value) is str and value == SOURCE_MODEL_HASH)


def _text(value: object, *, empty: bool = False) -> None:
    """PG text/JSONBに保存できる原文字列を変換せず保持する。"""
    _require(type(value) is str)
    if type(value) is str:
        _require((empty or bool(value)) and "\x00" not in value)
        try:
            value.encode("utf-8")
        except UnicodeError:
            raise StatsFunctionCodecError() from None


def _nonce(value: object) -> None:
    """長さ検査は資格照合ではない。真正な値はrootが別に渡す。"""
    _require(type(value) is bytes and len(value) == 32)


def _revision(revision: object, source_set: object, *, initial: bool) -> None:
    """0/NULLの初回だけを許し、正REVの欠測Sを補わない。"""
    _bigint(revision, 0 if initial else 1)
    if revision == 0:
        _require(initial and source_set is None)
    else:
        _hash(source_set)


def _object(value: object, keys: set[str]) -> dict[str, Any]:
    """JSON objectの余剰・欠落と型混同を拒否する。"""
    _require(type(value) is dict and set(value) == keys)
    return cast(dict[str, Any], value)


def _uint(value: object, *, positive: bool = False, length: int | None = None) -> None:
    """計算せず既ABIの正準整数文字列だけを検査する。"""
    pattern = r"[1-9][0-9]*" if positive else r"(?:0|[1-9][0-9]*)"
    _require(
        type(value) is str
        and (length is None or len(value) <= length)
        and re.fullmatch(pattern, value) is not None
    )


def _json_uuid(value: object) -> None:
    """JSON側のUUIDは正準文字列として保持する。"""
    _require(type(value) is str)
    try:
        _require(type(value) is str and str(UUID(value)) == value)
    except (ValueError, AttributeError, TypeError):
        raise StatsFunctionCodecError() from None


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """JSONB化で重複keyを消す前に閉拒否する。"""
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _invalid_number(_: str) -> None:
    """評価ABIにはJSON Numberが無く、NaN等も受けない。"""
    raise StatsFunctionCodecError()


def parse_evaluation_json(value: object) -> dict[str, Any]:
    """全26metric/nullable PA11/pending4を検査し、T5を再計算しない。"""
    _text(value)
    try:
        data = json.loads(
            cast(str, value),
            object_pairs_hook=_unique,
            parse_int=_invalid_number,
            parse_float=_invalid_number,
            parse_constant=_invalid_number,
        )
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise StatsFunctionCodecError() from None
    data = _object(
        data,
        {
            "metrics",
            "pa_row",
            "pending",
            "selected",
            "source_event_id",
            "native_rule_sha256",
        },
    )
    _require(data["selected"] is True)
    _json_uuid(data["source_event_id"])
    _hash(data["native_rule_sha256"])
    metrics = _object(data["metrics"], set(METRIC_IDS))
    for metric in metrics.values():
        row = _object(metric, {"state", "value", "display", "reason", "credits"})
        _require(type(row["credits"]) is list and len(row["credits"]) <= 4)
        if row["state"] == "available":
            _uint(row["value"])
            _require(row["display"] == row["value"] and row["reason"] is None)
            players = set()
            for raw_credit in row["credits"]:
                credit = _object(raw_credit, {"player_id", "quantity"})
                _json_uuid(credit["player_id"])
                _uint(credit["quantity"], positive=True)
                _require(credit["player_id"] not in players)
                players.add(credit["player_id"])
        else:
            _require(
                row["state"] == "source_unavailable"
                and row["value"] is None
                and row["display"] is None
                and row["credits"] == []
                and row["reason"] in ("MISSING_OBSERVATION", "MISSING_ATTRIBUTION")
            )
    pending = _object(
        data["pending"], {"named_category", "appearances", "batters_faced", "ops"}
    )
    for key, decision in [
        ("named_category", "D02"),
        ("appearances", "D03"),
        ("batters_faced", "D04"),
        ("ops", "D05"),
    ]:
        row = _object(pending[key], {"state", "decision_id", "value"})
        _require(
            row["state"] == "decision_pending"
            and row["decision_id"] == decision
            and row["value"] is None
        )
    if data["pa_row"] is not None:
        row = _object(
            data["pa_row"],
            {
                "pa_id",
                "batter_id",
                "ordinal_for_batter",
                "inning",
                "half",
                "result_display",
                "counts_as_ab",
                "hit_kind",
                "rbi",
                "reached_by",
                "rbi_state",
            },
        )
        for name in ("pa_id", "batter_id"):
            _json_uuid(row[name])
        for name in ("ordinal_for_batter", "inning"):
            _uint(row[name], positive=True, length=20)
        _require(row["half"] in ("top", "bottom") and type(row["counts_as_ab"]) is bool)
        _text(row["result_display"], empty=True)
        _require(row["hit_kind"] in ("none", "single", "double", "triple", "home_run"))
        _require(
            row["reached_by"]
            in (
                "none",
                "hit",
                "walk",
                "hit_by_pitch",
                "error",
                "fielders_choice",
                "catcher_interference",
                "runner_interference",
            )
        )
        if row["rbi_state"] == "available":
            _uint(row["rbi"], length=128)
        _require(
            row["rbi_state"] == metrics["rbi"]["state"]
            and row["rbi"] == metrics["rbi"]["value"]
        )
    return data


class _EvaluationJSONB(TypeDecorator[str]):
    """immutable JSON原文字列を実bind時にも検査しJSONBへ写す。"""

    impl = JSONB
    cache_ok = True

    def process_bind_param(self, value: object, dialect: Any) -> dict[str, Any]:
        """caller所有のmutable dictを保持せず、実bind直前に新しく読む。"""
        return parse_evaluation_json(value)


@dataclass(frozen=True, slots=True)
class StatsFunctionCall:
    """値部品。これを所持してもrootのprivate資格は得られない。"""

    function_id: str
    statement: Select[Any]
    parameters: Mapping[str, object] = field(repr=False)


# identity/引数順/型/結果型は5件だけ。callerからSQL/tenant flagを受けない。
_UUID = Uuid(as_uuid=True)
_TEXT = String()
_BIG = BigInteger()
_SPECS = {
    "save_primitive_source": (
        (
            ("attempt_id", _UUID),
            ("phase_id", _UUID),
            ("source_event_id", _UUID),
            ("model_sha256", _TEXT),
            ("expected_revision", _BIG),
            ("expected_source_set_sha256", _TEXT),
            ("evaluation_json", _EvaluationJSONB()),
            ("binding_nonce", LargeBinary()),
        ),
        (
            ("fact_version_id", _UUID),
            ("source_event_id", _UUID),
            ("model_sha256", _TEXT),
            ("source_set_sha256", _TEXT),
        ),
    ),
    "open_primitive_snapshot": (
        (("game_id", _UUID), ("player_id", _UUID), ("model_sha256", _TEXT)),
        (
            ("fact_version_id", _UUID),
            ("revision", _BIG),
            ("source_set_sha256", _TEXT),
            ("model_sha256", _TEXT),
            ("source_count", _BIG),
            ("row_count", _BIG),
            ("transaction_id", _TEXT),
            ("completion_state", _TEXT),
        ),
    ),
    "read_play_export_primitives": (
        (
            ("game_id", _UUID),
            ("player_id", _UUID),
            ("fact_version_id", _UUID),
            ("revision", _BIG),
            ("source_set_sha256", _TEXT),
            ("model_sha256", _TEXT),
            ("transaction_id", _TEXT),
            ("after_d2", _BIG),
            ("after_source_event_id", _UUID),
            ("after_metric_id", _TEXT),
            ("page_size", Integer()),
        ),
        (
            ("metric_id", _TEXT),
            ("state", _TEXT),
            ("value", Numeric(asdecimal=True)),
            ("d2", _BIG),
            ("source_event_id", _UUID),
        ),
    ),
    "read_primitive_totals": (
        (
            ("game_id", _UUID),
            ("player_id", _UUID),
            ("fact_version_id", _UUID),
            ("revision", _BIG),
            ("source_set_sha256", _TEXT),
            ("model_sha256", _TEXT),
            ("transaction_id", _TEXT),
        ),
        (("metric_id", _TEXT), ("state", _TEXT), ("value", Numeric(asdecimal=True))),
    ),
    "read_primitive_writer_state": (
        (
            ("attempt_id", _UUID),
            ("phase_id", _UUID),
            ("source_event_id", _UUID),
            ("model_sha256", _TEXT),
            ("binding_nonce", LargeBinary()),
        ),
        (("revision", _BIG), ("source_set_sha256", _TEXT)),
    ),
}


def _call(name: str, values: tuple[object, ...]) -> StatsFunctionCall:
    """閉factoryだけが使うSelect。tenant bindを先頭へ追加しない。"""
    inputs, outputs = _SPECS[name]
    _require(len(inputs) == len(values))
    table = Function(
        name,
        *(bindparam(key, type_=kind) for key, kind in inputs),
        packagenames=("stats_api",),
    ).table_valued(*(column(key, kind) for key, kind in outputs))
    return StatsFunctionCall(
        "stats_api." + name,
        select(*table.c),
        MappingProxyType(dict(zip((key for key, _ in inputs), values, strict=True))),
    )


def build_save_source_call(
    attempt_id: UUID,
    phase_id: UUID,
    source_event_id: UUID,
    model_sha256: str,
    expected_revision: int,
    expected_source_set_sha256: str | None,
    evaluation_json: str,
    *,
    binding_nonce: bytes,
) -> StatsFunctionCall:
    """同frame gate後の元評価/nonceだけをrootが供給する値入口。"""
    for value in (attempt_id, phase_id, source_event_id):
        _uuid(value)
    _model(model_sha256)
    _nonce(binding_nonce)
    _revision(expected_revision, expected_source_set_sha256, initial=True)
    data = parse_evaluation_json(evaluation_json)
    _require(data["source_event_id"] == str(source_event_id))
    return _call(
        "save_primitive_source",
        (
            attempt_id,
            phase_id,
            source_event_id,
            model_sha256,
            expected_revision,
            expected_source_set_sha256,
            evaluation_json,
            binding_nonce,
        ),
    )


def build_writer_state_call(
    attempt_id: UUID,
    phase_id: UUID,
    source_event_id: UUID,
    model_sha256: str,
    *,
    binding_nonce: bytes,
) -> StatsFunctionCall:
    """同frame gate後のpreflight5値。JSONやnonceから資格を発行しない。"""
    for value in (attempt_id, phase_id, source_event_id):
        _uuid(value)
    _model(model_sha256)
    _nonce(binding_nonce)
    return _call(
        "read_primitive_writer_state",
        (attempt_id, phase_id, source_event_id, model_sha256, binding_nonce),
    )


def build_open_snapshot_call(
    game_id: UUID, player_id: UUID, model_sha256: str
) -> StatsFunctionCall:
    """RRRO実scopeを別に要するOpenの3値を束縛する。"""
    _uuid(game_id)
    _uuid(player_id)
    _model(model_sha256)
    return _call("open_primitive_snapshot", (game_id, player_id, model_sha256))


def _read_values(
    game_id,
    player_id,
    fact_version_id,
    revision,
    source_set_sha256,
    model_sha256,
    transaction_id,
):
    """Private receipt由来であることはrootが検査し、ここは値だけを見る。"""
    for value in (game_id, player_id, fact_version_id):
        _uuid(value)
    _revision(revision, source_set_sha256, initial=False)
    _model(model_sha256)
    _text(transaction_id)
    return (
        game_id,
        player_id,
        fact_version_id,
        revision,
        source_set_sha256,
        model_sha256,
        transaction_id,
    )


def build_page_call(
    game_id: UUID,
    player_id: UUID,
    fact_version_id: UUID,
    revision: int,
    source_set_sha256: str,
    model_sha256: str,
    after_d2: int | None,
    after_source_event_id: UUID | None,
    after_metric_id: str | None,
    page_size: int,
    *,
    transaction_id: str,
) -> StatsFunctionCall:
    """全か無かのcursorと有界page、実receiptのsnapshot値を束縛する。"""
    values = _read_values(
        game_id,
        player_id,
        fact_version_id,
        revision,
        source_set_sha256,
        model_sha256,
        transaction_id,
    )
    _require(type(page_size) is int and 1 <= page_size <= 500)
    cursor = (after_d2, after_source_event_id, after_metric_id)
    if any(value is not None for value in cursor):
        _bigint(after_d2)
        _uuid(after_source_event_id)
        _require(type(after_metric_id) is str and after_metric_id in METRIC_IDS)
    return _call("read_play_export_primitives", (*values, *cursor, page_size))


def build_totals_call(
    game_id: UUID,
    player_id: UUID,
    fact_version_id: UUID,
    revision: int,
    source_set_sha256: str,
    model_sha256: str,
    *,
    transaction_id: str,
) -> StatsFunctionCall:
    """同handle private receiptが別に必須なTotalsの7値。"""
    return _call(
        "read_primitive_totals",
        _read_values(
            game_id,
            player_id,
            fact_version_id,
            revision,
            source_set_sha256,
            model_sha256,
            transaction_id,
        ),
    )


def _rows(
    rows: object, width: int, minimum: int, maximum: int
) -> tuple[tuple[Any, ...], ...]:
    """NULL行や欠落を仮の0行へ変えず、正規化済みtupleだけを受ける。"""
    _require(type(rows) is tuple and minimum <= len(rows) <= maximum)
    result = cast(tuple[tuple[Any, ...], ...], rows)
    for row in result:
        _require(type(row) is tuple and len(row) == width)
    return result


def decode_save_source_rows(
    rows: object, *, source_event_id: UUID
) -> tuple[tuple[Any, ...], ...]:
    """戻り元sourceを照合する。SQL成功を認可receiptとして発行しない。"""
    _uuid(source_event_id)
    result = _rows(rows, 4, 1, 1)
    for version, source, model, fingerprint in result:
        _uuid(version)
        _uuid(source)
        _model(model)
        _hash(fingerprint)
        _require(source == source_event_id)
    return result


def decode_writer_state_rows(rows: object) -> tuple[tuple[Any, ...], ...]:
    """実不在の0/NULLだけを許し、空結果を不在と推測しない。"""
    result = _rows(rows, 2, 1, 1)
    _revision(*result[0], initial=True)
    return result


def decode_open_snapshot_rows(rows: object) -> tuple[tuple[Any, ...], ...]:
    """Open全8列を保持する。値だけでは同handle receiptを成立させない。"""
    result = _rows(rows, 8, 1, 1)
    for (
        version,
        revision,
        fingerprint,
        model,
        sources,
        count,
        transaction,
        state,
    ) in result:
        _uuid(version)
        _revision(revision, fingerprint, initial=False)
        _model(model)
        _bigint(sources, 0)
        _bigint(count, 0)
        _text(transaction)
        _require(type(state) is str and state == "current_open")
    return result


def _metric(metric: object, state: object, value: object) -> None:
    """NUMERICをfloat/intへ変換せず、有限非負整数Decimalだけ保持する。"""
    _require(type(metric) is str and metric in METRIC_IDS)
    if state == "source_unavailable":
        _require(type(state) is str and value is None)
    else:
        _require(type(state) is str and state == "available")
        _require(
            type(value) is Decimal
            and value.is_finite()
            and value >= 0
            and value == value.to_integral_value()
        )


def decode_page_rows(rows: object, *, page_size: int) -> tuple[tuple[Any, ...], ...]:
    """NULLのmetric値を0へ変えず、既keyset行型とページ上限を保つ。"""
    _require(type(page_size) is int and 1 <= page_size <= 500)
    result = _rows(rows, 5, 0, page_size)
    for metric, state, value, d2, source in result:
        _metric(metric, state, value)
        _bigint(d2)
        _uuid(source)
    return result


def decode_totals_rows(rows: object) -> tuple[tuple[Any, ...], ...]:
    """既固定26群の全行を保持し、欠落/重複を0で埋めない。"""
    result = _rows(rows, 3, len(METRIC_IDS), len(METRIC_IDS))
    for metric, state, value in result:
        _metric(metric, state, value)
    _require({row[0] for row in result} == set(METRIC_IDS))
    return result
