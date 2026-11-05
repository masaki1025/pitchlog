"""成績固定5関数の値codecを独立した手例で検査する。"""

import copy
import inspect
import json
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy import BigInteger, Numeric
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import BindParameter

from pitchlog.repositories import stats_function_codec as codec
from pitchlog.stats.generated.receiver import METRIC_IDS, SOURCE_MODEL_HASH

U = UUID("00000000-0000-0000-0000-000000000001")
V = UUID("00000000-0000-0000-0000-000000000002")
H = "a" * 64
NONCE = bytes(range(32))


def envelope():
    """期待を実計算出力から採らずABIの静的なゼロ手例を作る。"""
    return {
        "metrics": {
            key: {
                "state": "available",
                "value": "0",
                "display": "0",
                "reason": None,
                "credits": [],
            }
            for key in METRIC_IDS
        },
        "pa_row": None,
        "pending": {
            key: {"state": "decision_pending", "decision_id": decision, "value": None}
            for key, decision in (
                ("named_category", "D02"),
                ("appearances", "D03"),
                ("batters_faced", "D04"),
                ("ops", "D05"),
            )
        },
        "selected": True,
        "source_event_id": str(U),
        "native_rule_sha256": H,
    }


def save(**changes):
    """固定factoryに渡す値だけを差し替える。"""
    values: dict[str, Any] = dict(
        attempt_id=U,
        phase_id=V,
        source_event_id=U,
        model_sha256=SOURCE_MODEL_HASH,
        expected_revision=0,
        expected_source_set_sha256=None,
        evaluation_json=json.dumps(envelope()),
        binding_nonce=NONCE,
    )
    values.update(changes)
    return codec.build_save_source_call(**values)


def page(**changes):
    """完全なreceipt由来であるという資格はこの試験では発行しない。"""
    values: dict[str, Any] = dict(
        game_id=U,
        player_id=V,
        fact_version_id=U,
        revision=1,
        source_set_sha256=H,
        model_sha256=SOURCE_MODEL_HASH,
        after_d2=None,
        after_source_event_id=None,
        after_metric_id=None,
        page_size=500,
        transaction_id="123:456:789",
    )
    values.update(changes)
    return codec.build_page_call(**values)


def test_five_closed_function_signatures_and_typed_sql():
    """5関数の正式な引数数と列型をSQLAlchemy ASTで確認する。"""
    calls = [
        save(),
        codec.build_writer_state_call(U, V, U, SOURCE_MODEL_HASH, binding_nonce=NONCE),
        codec.build_open_snapshot_call(U, V, SOURCE_MODEL_HASH),
        page(),
        codec.build_totals_call(
            U, V, U, 1, H, SOURCE_MODEL_HASH, transaction_id="123:456:789"
        ),
    ]
    names = [
        "save_primitive_source",
        "read_primitive_writer_state",
        "open_primitive_snapshot",
        "read_play_export_primitives",
        "read_primitive_totals",
    ]
    for call, name, count, width in zip(
        calls, names, (8, 5, 3, 11, 7), (4, 2, 8, 5, 3), strict=True
    ):
        assert call.function_id == "stats_api." + name
        query = str(call.statement.compile(dialect=postgresql.dialect()))
        assert f"FROM stats_api.{name}(" in query
        assert "tenant_id" not in query
        assert len(call.parameters) == count
        assert len(call.statement.selected_columns) == width
        binds = [
            node
            for node in visitors.iterate(call.statement)
            if isinstance(node, BindParameter)
        ]
        assert {node.key for node in binds} == set(call.parameters)
        assert len(binds) == count
        with pytest.raises(TypeError):
            cast(Any, call.parameters)["extra"] = 1
        assert NONCE.hex() not in repr(call)
        assert "evaluation_json=" not in repr(call)
    page_columns = list(calls[3].statement.selected_columns)
    assert isinstance(page_columns[2].type, Numeric)
    assert isinstance(page_columns[3].type, BigInteger)
    save_binds = {
        node.key: node
        for node in visitors.iterate(calls[0].statement)
        if isinstance(node, BindParameter)
    }
    assert isinstance(save_binds["expected_revision"].type, BigInteger)
    assert isinstance(
        cast(Any, save_binds["evaluation_json"].type).impl, postgresql.JSONB
    )
    first = cast(Any, save_binds["evaluation_json"].type).process_bind_param(
        calls[0].parameters["evaluation_json"], postgresql.dialect()
    )
    second = cast(Any, save_binds["evaluation_json"].type).process_bind_param(
        calls[0].parameters["evaluation_json"], postgresql.dialect()
    )
    assert first == second == envelope()
    first["selected"] = False
    assert second["selected"] is True
    for factory in (
        codec.build_save_source_call,
        codec.build_writer_state_call,
        codec.build_open_snapshot_call,
        codec.build_page_call,
        codec.build_totals_call,
    ):
        assert not {
            "sql",
            "identity",
            "function_id",
            "tenant_id",
            "tenantflag",
            "arity",
        } & set(inspect.signature(factory).parameters)
    with pytest.raises(TypeError):
        cast(Any, codec.build_open_snapshot_call)(U, V, SOURCE_MODEL_HASH, tenant_id=U)


@pytest.mark.parametrize(
    "changes",
    [
        {"attempt_id": str(U)},
        {"phase_id": None},
        {"source_event_id": V},
        {"model_sha256": "sha256:" + H},
        {"binding_nonce": NONCE[:-1]},
        {"binding_nonce": bytearray(NONCE)},
        {"expected_revision": True},
        {"expected_revision": 1.0},
        {"expected_revision": -1},
        {"expected_revision": 2**63},
        {"expected_source_set_sha256": H},
        {"expected_revision": 1},
        {"expected_revision": 1, "expected_source_set_sha256": H.upper()},
    ],
)
def test_save_rejects_type_range_and_revision_pair(changes):
    """UUID/bytes/整数/初回REVとSの整合を補完しない。"""
    with pytest.raises(codec.StatsFunctionCodecError):
        save(**changes)


def test_save_positive_revision_and_bigint_are_lossless():
    """2^53を超えてもfloatを経由しない。"""
    call = save(expected_revision=2**63 - 1, expected_source_set_sha256=H)
    assert call.parameters["expected_revision"] == 2**63 - 1
    assert type(call.parameters["expected_revision"]) is int


@pytest.mark.parametrize(
    "changes",
    [
        {"revision": 0},
        {"revision": True},
        {"transaction_id": None},
        {"transaction_id": ""},
        {"transaction_id": "a\x00b"},
        {"after_d2": 1},
        {"after_source_event_id": U},
        {"after_metric_id": "h"},
        {"after_d2": 0, "after_source_event_id": str(U), "after_metric_id": "h"},
        {"after_d2": 0, "after_source_event_id": U, "after_metric_id": "unknown"},
        {"after_d2": 2**63, "after_source_event_id": U, "after_metric_id": "h"},
        {"after_d2": True, "after_source_event_id": U, "after_metric_id": "h"},
        {"page_size": 0},
        {"page_size": 501},
        {"page_size": True},
    ],
)
def test_page_rejects_partial_cursor_and_inexact_values(changes):
    """欠測cursor・過大pageを修復して実行しない。"""
    with pytest.raises(codec.StatsFunctionCodecError):
        page(**changes)


def test_full_cursor_signed_bigint_is_kept():
    """D2は正式bigintの値を保存し整数近似しない。"""
    call = page(after_d2=-(2**63), after_source_event_id=V, after_metric_id="h")
    assert call.parameters["after_d2"] == -(2**63)
    assert call.parameters["after_source_event_id"] is V


def test_nullable_pa_and_unavailable_metric_are_kept():
    """未観測を0へ補わず、PAの実表示値もエスケープ前に改変しない。"""
    data = envelope()
    data["metrics"]["rbi"] = dict(
        state="source_unavailable",
        value=None,
        display=None,
        reason="MISSING_OBSERVATION",
        credits=[],
    )
    data["pa_row"] = dict(
        pa_id=str(V),
        batter_id=str(U),
        ordinal_for_batter="1",
        inning="1",
        half="top",
        result_display="<b>実表示</b>",
        counts_as_ab=True,
        hit_kind="single",
        rbi=None,
        reached_by="hit",
        rbi_state="source_unavailable",
    )
    assert codec.parse_evaluation_json(json.dumps(data)) == data


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(extra=None),
        lambda d: d.pop("pa_row"),
        lambda d: d.update(selected=1),
        lambda d: d.update(native_rule_sha256="a" * 63),
        lambda d: d.update(source_event_id=str(U).upper().replace("000001", "00000A")),
        lambda d: d["metrics"].pop("h"),
        lambda d: d["metrics"]["h"].update(extra=None),
        lambda d: d["metrics"]["h"].update(value=0),
        lambda d: d["metrics"]["h"].update(value="00", display="00"),
        lambda d: d["metrics"]["h"].update(display="1"),
        lambda d: d["metrics"]["h"].update(reason="MISSING_OBSERVATION"),
        lambda d: d["metrics"]["h"].update(
            credits=[{"player_id": str(U), "quantity": "0"}]
        ),
        lambda d: d["metrics"]["h"].update(
            credits=[{"player_id": str(U), "quantity": "1"}] * 2
        ),
        lambda d: d["pending"]["ops"].update(decision_id="D02"),
        lambda d: d["pending"]["ops"].update(value="0"),
        lambda d: d.update(pa_row={}),
    ],
)
def test_evaluation_rejects_abi_corruption(mutation):
    """全階層の余剰・欠落・型混同を拒否する。"""
    data = envelope()
    mutation(data)
    with pytest.raises(codec.StatsFunctionCodecError):
        codec.parse_evaluation_json(json.dumps(data))


@pytest.mark.parametrize(
    "raw",
    [
        '{"selected":true,"selected":true}',
        "[NaN]",
        "[Infinity]",
        "[1]",
        "[1.0]",
        "{}",
        "null",
        '"text"',
        "{",
    ],
)
def test_evaluation_strict_json_parser(raw):
    """JSONB化する前に重複keyや非有限Numberを拒否する。"""
    with pytest.raises(codec.StatsFunctionCodecError):
        codec.parse_evaluation_json(raw)


def test_pa_extra_missing_and_rbi_correlation():
    """PA11列の不足とRBI状態/値の乖離を拒否する。"""
    base = envelope()
    base["pa_row"] = dict(
        pa_id=str(V),
        batter_id=str(U),
        ordinal_for_batter="1",
        inning="1",
        half="top",
        result_display="",
        counts_as_ab=True,
        hit_kind="single",
        rbi="0",
        reached_by="hit",
        rbi_state="available",
    )
    assert codec.parse_evaluation_json(json.dumps(base)) == base
    for key in base["pa_row"]:
        data = copy.deepcopy(base)
        del data["pa_row"][key]
        with pytest.raises(codec.StatsFunctionCodecError):
            codec.parse_evaluation_json(json.dumps(data))
    for updates in (
        {"rbi": "1"},
        {"rbi_state": "source_unavailable"},
        {"counts_as_ab": 1},
        {"inning": "0"},
        {"half": "TOP"},
        {"hit_kind": "unknown"},
        {"reached_by": "unknown"},
        {"result_display": "\ud800"},
        {"extra": None},
    ):
        data = copy.deepcopy(base)
        data["pa_row"].update(updates)
        with pytest.raises(codec.StatsFunctionCodecError):
            codec.parse_evaluation_json(json.dumps(data))


def test_valid_rows_preserve_null_decimal_and_all_fields():
    """SQLの全列を同じtupleで返し、欠測や巨大整数を置換しない。"""
    saved = ((V, U, SOURCE_MODEL_HASH, H),)
    assert codec.decode_save_source_rows(saved, source_event_id=U) is saved
    assert codec.decode_writer_state_rows(((0, None),)) == ((0, None),)
    assert codec.decode_writer_state_rows(((2**63 - 1, H),)) == ((2**63 - 1, H),)
    opened = (
        (V, 1, H, SOURCE_MODEL_HASH, 2**63 - 1, 2**63 - 1, "txid", "current_open"),
    )
    assert codec.decode_open_snapshot_rows(opened) is opened
    huge = Decimal("9" * 120)
    rows = (
        ("h", "available", huge, 2**63 - 1, U),
        ("rbi", "source_unavailable", None, -(2**63), V),
    )
    assert codec.decode_page_rows(rows, page_size=2) is rows
    assert codec.decode_page_rows((), page_size=1) == ()
    totals = tuple((key, "available", Decimal(0)) for key in METRIC_IDS)
    assert codec.decode_totals_rows(totals) is totals


@pytest.mark.parametrize(
    "value",
    [
        None,
        0,
        1.0,
        True,
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-1"),
        Decimal("0.1"),
    ],
)
def test_numeric_never_coerces_bad_values(value):
    """非有限・分数・boolを整数として通さない。"""
    with pytest.raises(codec.StatsFunctionCodecError):
        codec.decode_page_rows((("h", "available", value, 1, U),), page_size=1)


@pytest.mark.parametrize(
    "rows",
    [
        None,
        [],
        (None,),
        ((0,),),
        ((True, None),),
        ((0, H),),
        ((1, None),),
        ((-1, H),),
        ((2**63, H),),
        ((1, H), (1, H)),
    ],
)
def test_writer_result_requires_exact_honest_pair(rows):
    """空結果・NULL行を初回不在と誤認しない。"""
    with pytest.raises(codec.StatsFunctionCodecError):
        codec.decode_writer_state_rows(rows)


def test_result_schema_corruptions_are_rejected():
    """全関数の列数・cardinality・識別子・状態・NULLを閉検査する。"""
    bad_saves = [
        (),
        ((V, V, SOURCE_MODEL_HASH, H),),
        ((None, U, SOURCE_MODEL_HASH, H),),
        ((V, U, SOURCE_MODEL_HASH, H, None),),
    ]
    for rows in bad_saves:
        with pytest.raises(codec.StatsFunctionCodecError):
            codec.decode_save_source_rows(rows, source_event_id=U)
    opened: list[Any] = [V, 1, H, SOURCE_MODEL_HASH, 0, 0, "txid", "current_open"]
    for index, bad in (
        (0, str(V)),
        (1, 0),
        (2, None),
        (3, H),
        (4, True),
        (5, -1),
        (6, None),
        (7, "closed"),
    ):
        row = opened.copy()
        row[index] = bad
        with pytest.raises(codec.StatsFunctionCodecError):
            codec.decode_open_snapshot_rows((tuple(row),))
    for row in (
        ("unknown", "available", Decimal(0), 1, U),
        ("h", "unavailable", None, 1, U),
        ("h", "source_unavailable", Decimal(0), 1, U),
        ("h", "available", Decimal(0), True, U),
        ("h", "available", Decimal(0), 1, str(U)),
    ):
        with pytest.raises(codec.StatsFunctionCodecError):
            codec.decode_page_rows((row,), page_size=1)
    totals = tuple((key, "available", Decimal(0)) for key in METRIC_IDS)
    for rows in (
        totals[:-1],
        totals + totals[:1],
        totals[:1] * len(METRIC_IDS),
        (([], "available", Decimal(0)),) + totals[1:],
    ):
        with pytest.raises(codec.StatsFunctionCodecError):
            codec.decode_totals_rows(rows)


def test_contract_valid_129_digits_metric_and_credit_are_lossless():
    """metric/creditに契約外の128桁制限を追加しない。"""
    data = envelope()
    amount = "1" + "0" * 128
    data["metrics"]["runs"].update(
        value=amount,
        display=amount,
        credits=[{"player_id": str(U), "quantity": amount}],
    )
    result = codec.parse_evaluation_json(json.dumps(data))
    assert result == data
    assert result["metrics"]["runs"]["value"] == amount
    assert result["metrics"]["runs"]["credits"][0]["quantity"] == amount
    call = save(evaluation_json=json.dumps(data))
    assert call.parameters["evaluation_json"] == json.dumps(data)


@pytest.mark.parametrize("bad", [True, "-1", "1e2", "1.5", "NaN", "Infinity"])
@pytest.mark.parametrize("field", ["value", "quantity"])
def test_unbounded_integer_fields_still_reject_inexact_values(bad, field):
    """桁上限の除去でbool/負/指数/分数/非有限を許可しない。"""
    data = envelope()
    data["metrics"]["runs"].update(
        value="1",
        display="1",
        credits=[{"player_id": str(U), "quantity": "1"}],
    )
    if field == "value":
        data["metrics"]["runs"].update(value=bad, display=bad)
    else:
        data["metrics"]["runs"]["credits"][0]["quantity"] = bad
    with pytest.raises(codec.StatsFunctionCodecError):
        codec.parse_evaluation_json(json.dumps(data))


def test_explicit_pa_rbi_and_inning_lengths_are_retained():
    """PAの明記128/20桁はmetricの無上限と混同しない。"""
    base = envelope()
    base["pa_row"] = dict(
        pa_id=str(V),
        batter_id=str(U),
        ordinal_for_batter="1",
        inning="1",
        half="top",
        result_display="",
        counts_as_ab=True,
        hit_kind="single",
        rbi="0",
        reached_by="hit",
        rbi_state="available",
    )
    maximum = "1" * 128
    base["metrics"]["rbi"].update(value=maximum, display=maximum)
    base["pa_row"]["rbi"] = maximum
    assert codec.parse_evaluation_json(json.dumps(base)) == base
    for field in ("inning", "ordinal_for_batter"):
        data = copy.deepcopy(base)
        data["pa_row"][field] = "1" * 21
        with pytest.raises(codec.StatsFunctionCodecError):
            codec.parse_evaluation_json(json.dumps(data))
    base["metrics"]["rbi"].update(value="1" * 129, display="1" * 129)
    base["pa_row"]["rbi"] = "1" * 129
    with pytest.raises(codec.StatsFunctionCodecError):
        codec.parse_evaluation_json(json.dumps(base))
