"""初球書込印の発行(B)と消費(A)を、owned PGの実経路で縦に確かめる。

印はbind_device→check_current_rightの正規経路でだけ作る。adminが印を直接
INSERT/UPDATEするscaffoldは0件(V10で全statementを表明する)。適用するのは
「候補」(unit Aのcandidate_profile全キーの機械描画と、印付き2 body)であり、
正式installerでの成功ではない。DBはfixtureが作るowned PGだけで、共有DSNは使わない。

構成:
- DB1(module): 候補適用済みの共有DB。破壊しない試験(V・M・T)。
- DB2(module): 候補適用前から始め、破壊を伴う試験(T22・T15・T11・変異)を順に行う。
- 実cookie縦断(V11/T16)は候補適用なし/ありの2つの独立DBで行う。
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from pitchlog.authz.first_ball_write_stamp import STATE_TRANSITIONS, TERMINAL_STATES
from pitchlog.authz.sync_right_sql import (
    render_stamped_function_sql,
    render_sync_right_sql,
)

from .first_ball_stamp_support import (
    BIND_REJECT,
    RIGHT_OWNER,
    STAMP_REJECT,
    STAMP_TABLE,
    Ctx,
    apply_candidates,
    error_lines,
    exec_text,
    leaks,
    peer,
    stamp_dml_statements,
)
from .sync_writer_binding_support import (
    APP,
    _literal,
    binding_app,
    binding_broker,
    owned_binding_database,
    prepare_binding_database,
)
from .test_initial_recording_right_scope import (
    admin_connection as admin_connection,
)
from .test_initial_recording_right_scope import (
    tested_role_connection as tested_role_connection,
)

pytestmark = pytest.mark.requires_db

_RESULTS: dict[str, Any] = {}


def _record(key: str, value: Any) -> None:
    """結果JSON(PITCHLOG_STAMP_RESULTS)用に各caseの観測値を残す。"""
    _RESULTS[key] = value


@pytest.fixture(scope="module", autouse=True)
def _dump_results() -> Iterator[None]:
    """module終了時に観測値をJSONへ書く(環境変数があるときだけ)。"""
    yield
    target = os.environ.get("PITCHLOG_STAMP_RESULTS")
    if target:
        Path(target).write_text(
            json.dumps(_RESULTS, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8",
        )


@dataclass
class Env:
    """1つのowned DBと、そこで使う資格値。"""

    owner: Any
    db: Any
    ctx: Ctx
    good: bytes
    bad: bytes
    bad_proof: bytes
    applied: bool


def _make_env(monkeypatch: pytest.MonkeyPatch, *, apply: bool) -> Iterator[Env]:
    """Owned DB(正式installer適用済み)を作り、必要なら候補を適用して供給する。"""
    from db_fixtures import _dsn_names

    from pitchlog.repositories.initial_recording_right import _credential_digest

    with owned_binding_database(monkeypatch) as owner:
        admin_name, role_name = _dsn_names()
        monkeypatch.setenv(admin_name, owner.authority.database.primary_admin)
        monkeypatch.setenv(role_name, owner.authority.database.endpoints.primary_dsn)
        db = prepare_binding_database(owner)
        issued = owner.actor("grant=issue(); print(json.dumps(receipt(grant)))")
        ctx = Ctx(db, issued)
        if apply:
            apply_candidates(owner)
        proof = ctx.proof
        yield Env(
            owner=owner,
            db=db,
            ctx=ctx,
            good=_credential_digest("credential-a"),
            bad=_credential_digest("credential-b"),
            bad_proof=bytes([proof[0] ^ 1]) + proof[1:],
            applied=apply,
        )


@pytest.fixture(scope="module")
def _db1() -> Iterator[Env]:
    """DB1: 候補適用済み。破壊しない試験が共有する。"""
    with pytest.MonkeyPatch.context() as patch:
        yield from _make_env(patch, apply=True)


@pytest.fixture(scope="module")
def _db2() -> Iterator[Env]:
    """DB2: 候補適用前の状態から始め、破壊を伴う試験が順に使う。"""
    with pytest.MonkeyPatch.context() as patch:
        yield from _make_env(patch, apply=False)


@pytest.fixture
def initial_scope_database(request: pytest.FixtureRequest) -> Any:
    """既存のautouse(実identity検査)へ、そのtestが使うowned DBを渡す。"""
    name = "_db2" if "_db2" in request.fixturenames else "_db1"
    if "_db1" not in request.fixturenames and "_db2" not in request.fixturenames:
        # 実cookie縦断は自前のfixtureを使う(下のreal_owner)。
        return request.getfixturevalue("real_owner")
    return request.getfixturevalue(name).owner


@pytest.fixture
def db1(_db1: Env) -> Env:
    """DB1を各testへ。"""
    return _db1


@pytest.fixture
def db2(_db2: Env) -> Env:
    """DB2を各testへ。"""
    return _db2


# ---------------------------------------------------------------------------
# 共通の手順
# ---------------------------------------------------------------------------


def _bind(w: Any, env: Env, b: dict, *, bad: bool = False):
    return w.run(env.ctx.bind_sql(b, env.bad if bad else env.good))


def _right(w: Any, env: Env, b: dict, *, bad_proof: bool = False):
    return w.run(env.ctx.right_sql(b, env.bad_proof if bad_proof else env.ctx.proof))


def _new_attempt(env: Env, w: Any, *, ttl: int = 25, **event_kw: Any):
    """TXを開き、eventと束縛を1組作る(scaffoldのeventは印ではない)。"""
    event = env.ctx.event(**event_kw)
    env.ctx.begin(w)
    return event, env.ctx.publish(w, event, ttl=ttl)


def _insert(w: Any, env: Env, event: dict, row: Any | None = None):
    return w.run(env.ctx.insert_sql(event["id"], row or uuid4()))


def _insert_is_rejected(env: Env, steps: list, label: str) -> dict:
    """steps(関数呼び出し列)の後にPlayRowをINSERTし、42501で拒否されることを確かめる。"""
    with peer(env.db, APP) as w:
        event, b = _new_attempt(env, w)
        outcomes = [step(w, env, b)[:2] for step in steps]
        ins = _insert(w, env, event)
        w.run("ROLLBACK")
    result = {"steps": outcomes, "insert_sqlstate": ins[1], "stderr": ins[2][:300]}
    assert ins[1] == "42501", (label, result)
    assert STAMP_REJECT in ins[2], (label, result)
    return result


# ---------------------------------------------------------------------------
# V: 縦の試験(DB1)
# ---------------------------------------------------------------------------


def test_v1_b_issues_and_a_consumes_in_one_insert(db1: Env) -> None:
    """V1: bind(true)→right(true,true)→PlayRow INSERT 1回で、印がconsumedになる。

    印はBの正規経路だけで作られ、adminが印を入れるscaffoldは使わない。
    """
    env, ev, row = db1, None, uuid4()
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        r1 = _bind(w, env, b)
        r2 = _right(w, env, b)
        ri = w.run(env.ctx.insert_sql(ev["id"], row))
        rc = w.run("COMMIT")
    result = dict(bind=r1[:2], right=r2[:2], insert=ri[1], commit=rc[1])
    assert r1[:2] == (("t",), "00000"), result
    assert r2[:2] == (("t|t",), "00000"), result
    assert ri[1] == "00000" and rc[1] == "00000", result
    stamp = env.ctx.stamp_row(b)
    assert stamp == [["consumed", str(ev["id"]), str(row), True]], stamp
    plays = env.ctx.admin(
        "SELECT count(*) FROM public.play_rows WHERE tenant_id=%s AND id=%s",
        (env.ctx.tenant, row),
        fetch=True,
    )
    assert plays == [(1,)]
    _record("V1", {**result, "stamp": stamp})


def test_v2_issue_without_insert_is_committed_as_right_verified(db1: Env) -> None:
    """V2: INSERTなしでCOMMITすると、印はright_verifiedのまま残る(1行)。"""
    env = db1
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        _bind(w, env, b)
        _right(w, env, b)
        assert w.run("COMMIT")[1] == "00000"
    stamp = env.ctx.stamp_row(b)
    assert stamp == [["right_verified", None, None, False]], stamp
    _record("V2", stamp)


def test_v3_no_issue_then_insert_is_rejected(db1: Env) -> None:
    """V3: 印の発行なしのINSERTは42501でPlayRowが0行。"""
    env = db1
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        ins = _insert(w, env, ev, row := uuid4())
        w.run("ROLLBACK")
    assert ins[1] == "42501" and STAMP_REJECT in ins[2]
    plays = env.ctx.admin(
        "SELECT count(*) FROM public.play_rows WHERE id=%s", (row,), fetch=True
    )
    assert plays == [(0,)]
    _record("V3", dict(insert=ins[1]))


def test_v4_device_only_then_insert_is_rejected(db1: Env) -> None:
    """V4: bind(true)だけ(right未成功)でのINSERTは42501。"""
    _record(
        "V4", _insert_is_rejected(db1, [lambda w, e, b: _bind(w, e, b)], "device-only")
    )


def test_v5_reverse_order_makes_the_stamp_invalid(db1: Env) -> None:
    """V5: 逆順(right→bind)は印がinvalid(新行)になり、INSERTは42501。"""
    env = db1
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        r = _right(w, env, b)
        d = _bind(w, env, b)
        w.run("COMMIT")
    # 逆順の戻り値は既存と同じ(right=t|t, bind=t)。印だけがinvalid。
    assert r[:2] == (("t|t",), "00000") and d[:2] == (("t",), "00000")
    assert env.ctx.stamp_row(b) == [["invalid", None, None, False]]
    _record(
        "V5",
        _insert_is_rejected(
            env,
            [lambda w, e, b: _right(w, e, b), lambda w, e, b: _bind(w, e, b)],
            "reverse",
        ),
    )


def test_v6_false_then_true_does_not_revive_the_phase(db1: Env) -> None:
    """V6: bind(false)の後にbind(true)・right(true)をしても、印はinvalidのまま。"""
    env = db1
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        r1 = _bind(w, env, b, bad=True)
        r2 = _bind(w, env, b)
        r3 = _right(w, env, b)
        ins = _insert(w, env, ev)
        w.run("ROLLBACK")
    assert r1[:2] == (("f",), "00000") and r2[:2] == (("t",), "00000")
    assert r3[:2] == (("t|t",), "00000")
    assert ins[1] == "42501" and STAMP_REJECT in ins[2]
    # 発行側の保存は、invalidのままcommitされる(右の戻りの真偽は変わらない)。
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        _bind(w, env, b, bad=True)
        _bind(w, env, b)
        _right(w, env, b)
        w.run("COMMIT")
    assert env.ctx.stamp_row(b) == [["invalid", None, None, False]]
    _record("V6", dict(bind_false=r1[:2], insert=ins[1]))


def test_v7_right_mismatch_makes_the_stamp_invalid(db1: Env) -> None:
    """V7: proof不一致(t,f)・epoch不一致(f,f)の後は、印invalid・INSERT 42501。"""
    env = db1
    out = {}
    for label, kwargs, expected in (
        ("proof", dict(bad_proof=True), (("t|f",), "00000")),
        ("epoch", dict(), (("f|f",), "00000")),
    ):
        with peer(env.db, APP) as w:
            ev, b = _new_attempt(env, w)
            _bind(w, env, b)
            if label == "epoch":
                got = w.run(env.ctx.right_sql(b, epoch=env.ctx.epoch + 1000))
            else:
                got = _right(w, env, b, **kwargs)
            ins = _insert(w, env, ev)
            w.run("ROLLBACK")
        assert got[:2] == expected, (label, got)
        assert ins[1] == "42501", (label, ins)
        # 同じ手順をcommitして印の状態を観測する(INSERTなし)。
        with peer(env.db, APP) as w:
            ev, b = _new_attempt(env, w)
            _bind(w, env, b)
            if label == "epoch":
                w.run(env.ctx.right_sql(b, epoch=env.ctx.epoch + 1000))
            else:
                _right(w, env, b, **kwargs)
            w.run("COMMIT")
        assert env.ctx.stamp_row(b) == [["invalid", None, None, False]], label
        out[label] = dict(right=got[:2], insert=ins[1])
    _record("V7", out)


def test_v8_savepoint_rules(db1: Env) -> None:
    """V8: savepoint内・ROLLBACK TOのみの後は42501、RELEASE後は通り消費される。"""
    env = db1
    out: dict[str, Any] = {}
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        w.run("SAVEPOINT s1")
        n1 = _bind(w, env, b)  # (a) 初回bindをsavepoint内で
        w.run("ROLLBACK TO SAVEPOINT s1")
        n2 = _bind(w, env, b)  # (b) ROLLBACK TOだけ(RELEASEなし)の後
        w.run("ROLLBACK TO SAVEPOINT s1")
        w.run("RELEASE SAVEPOINT s1")
        n3 = _bind(w, env, b)  # (c) RELEASE後はtop-level
        n4 = _right(w, env, b)
        ins = _insert(w, env, ev, row := uuid4())
        w.run("COMMIT")
    out.update(nested=n1[1], after_rollback_to=n2[1], after_release=n3[:2])
    # 初回のnested bindは既存のassert(入口)が「top-levelが必要」として拒否する。
    assert n1[1] == "42501" and "top-level" in n1[2], n1
    assert n2[1] == "42501", n2
    assert n3[:2] == (("t",), "00000") and n4[:2] == (("t|t",), "00000")
    assert ins[1] == "00000"
    assert env.ctx.stamp_row(b) == [["consumed", str(ev["id"]), str(row), True]]
    # (d) savepoint内のINSERT(Aの外側照合)は42501。
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        _bind(w, env, b)
        _right(w, env, b)
        w.run("SAVEPOINT s2")
        nested_insert = _insert(w, env, ev)
        w.run("ROLLBACK TO SAVEPOINT s2")
        w.run("RELEASE SAVEPOINT s2")
        w.run("ROLLBACK")
    assert nested_insert[1] == "42501" and STAMP_REJECT in nested_insert[2]
    out["nested_insert"] = nested_insert[1]
    _record("V8", out)


def test_v9_consumed_is_stable_and_second_insert_is_rejected(db1: Env) -> None:
    """V9: consumedの後のbind/rightは据え置き(23514なし)。2行目のINSERTは42501。"""
    env = db1
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        _bind(w, env, b)
        _right(w, env, b)
        i1 = _insert(w, env, ev, row := uuid4())
        again_b = _bind(w, env, b)
        again_r = _right(w, env, b)
        i2 = _insert(w, env, ev)
        w.run("ROLLBACK" if i2[1] != "00000" else "COMMIT")
    assert i1[1] == "00000" and i2[1] == "42501", (i1[1], i2[1])
    assert again_b[:2] == (("t",), "00000") and again_r[:2] == (("t|t",), "00000")
    # 2行目の拒否でTXをrollbackしたので、consumedはcommitされない。
    # consumedの据え置きをcommitして観測する。
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        _bind(w, env, b)
        _right(w, env, b)
        _insert(w, env, ev, row := uuid4())
        _bind(w, env, b)
        _right(w, env, b)
        assert w.run("COMMIT")[1] == "00000"
    assert env.ctx.stamp_row(b) == [["consumed", str(ev["id"]), str(row), True]]
    _record("V9", dict(second_insert=i2[1], again=[again_b[:2], again_r[:2]]))


# ---------------------------------------------------------------------------
# M1: 遷移の全行列(5状態x4事象)
# ---------------------------------------------------------------------------

_STATES = ("absent", "device_verified", "right_verified", "invalid", "consumed")
_EVENTS = ("device_true", "device_false", "right_true", "right_false")


def _expected(state: str, event: str) -> str:
    """Aの定数(STATE_TRANSITIONS/TERMINAL_STATES)だけから全域化した期待値。"""
    table = {(a, e): n for a, e, n in STATE_TRANSITIONS}
    if (state, event) in table:
        return table[(state, event)]
    if state in TERMINAL_STATES:
        return state
    return "invalid"


def test_m1_transition_matrix_20_cells(db1: Env) -> None:
    """M1: 5状態x4事象の20セルを実PGで表駆動検査する。返却値は既存と同じ。"""
    env = db1
    pre = {
        "absent": [],
        "device_verified": ["device_true"],
        "right_verified": ["device_true", "right_true"],
        "invalid": ["device_false"],
        "consumed": ["device_true", "right_true", "INSERT"],
    }
    # Aの宣言は「成立した事象」だけを持つ。device_false/right_falseはAの表に無く
    # 全域化規則(終端なら据え置き、それ以外はinvalid)で扱う。
    returned_expect = {
        "device_true": (("t",), "00000"),
        "device_false": (("f",), "00000"),
        "right_true": (("t|t",), "00000"),
        "right_false": (("t|f",), "00000"),
    }
    results: dict[str, Any] = {}

    def call(w: Any, b: dict, name: str):
        if name == "device_true":
            return _bind(w, env, b)
        if name == "device_false":
            return _bind(w, env, b, bad=True)
        if name == "right_true":
            return _right(w, env, b)
        return _right(w, env, b, bad_proof=True)

    for state in _STATES:
        for event in _EVENTS:
            with peer(env.db, APP) as w:
                ev, b = _new_attempt(env, w)
                for step in pre[state]:
                    if step == "INSERT":
                        r = _insert(w, env, ev)
                    else:
                        r = call(w, b, step)
                    assert r[1] == "00000", (state, event, step, r[2][:200])
                got = call(w, b, event)
                assert got[1] == "00000", (state, event, got[2][:200])
                assert w.run("COMMIT")[1] == "00000", (state, event)
            rows = env.ctx.stamp_row(b)
            actual = "absent" if not rows else rows[0][0]
            key = f"{state}|{event}"
            results[key] = dict(
                expected=_expected(state, event), actual=actual, returned=got[0]
            )
            assert actual == _expected(state, event), (key, results[key])
            assert got[:2] == returned_expect[event], (key, got)
            # absentへの事象は、逆順・失敗でも新行を作るので「absent」のまま残らない。
    assert len(results) == 20
    _record("M1", results)


# ---------------------------------------------------------------------------
# T: 追加の実PG試験(DB1)
# ---------------------------------------------------------------------------


def test_t07_phases_are_not_merged(db1: Env) -> None:
    """T07: phase Aのdevice trueとphase Bのright trueは合成されない。"""
    env = db1
    with peer(env.db, APP) as w:
        event_a = env.ctx.event()
        event_b = env.ctx.event()
        env.ctx.begin(w)
        a = env.ctx.publish(w, event_a)
        b = env.ctx.publish(w, event_b)
        _bind(w, env, a)
        _right(w, env, b)
        assert w.run("COMMIT")[1] == "00000"
    assert env.ctx.stamp_row(a) == [["device_verified", None, None, False]]
    assert env.ctx.stamp_row(b) == [["invalid", None, None, False]]
    _record("T07", "A=device_verified,B=invalid")


def test_t08_other_tx_cannot_reuse_a_binding(db1: Env) -> None:
    """T08: TX1でcommitした後、別TXの同じ束縛はassertが42501で、印はTX1のまま。"""
    env = db1
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        _bind(w, env, b)
        _right(w, env, b)
        w.run("COMMIT")
    before = env.ctx.stamp_row(b)
    with peer(env.db, APP) as w2:
        env.ctx.begin(w2)
        r1 = _bind(w2, env, b)
        w2.run("ROLLBACK")
    assert r1[1] == "42501", r1
    assert env.ctx.stamp_row(b) == before == [["right_verified", None, None, False]]
    _record("T08", r1[1])


def test_t09_savepoint_variants(db1: Env) -> None:
    """T09(a)〜(e): savepoint内・ROLLBACK TO後のbind/rightは42501で印を作らない。"""
    env = db1
    out: dict[str, Any] = {}
    # (a) 初回bindをsavepoint内で → 42501、commitしても印0行。
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        w.run("SAVEPOINT s")
        a = _bind(w, env, b)
        w.run("ROLLBACK TO SAVEPOINT s")
        w.run("RELEASE SAVEPOINT s")
        w.run("COMMIT")
    assert a[1] == "42501"
    assert env.ctx.stamp_row(b) == []
    out["a_first_bind_nested"] = a[1]
    # (b)(c)(d) top-levelのbind(true)の後のnested bind/right/falseは42501。
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        _bind(w, env, b)
        for name, call in (
            ("b_nested_bind", lambda: _bind(w, env, b)),
            ("c_nested_right", lambda: _right(w, env, b)),
            ("d_nested_false", lambda: _bind(w, env, b, bad=True)),
        ):
            w.run("SAVEPOINT s")
            got = call()
            w.run("ROLLBACK TO SAVEPOINT s")
            w.run("RELEASE SAVEPOINT s")
            # 入口の印(top-level)ができた後のnested呼出しは、印のxmin照合が拒否する。
            assert got[1] == "42501" and BIND_REJECT in got[2], (name, got)
            out[name] = got[1]
        w.run("COMMIT")
    assert env.ctx.stamp_row(b) == [["device_verified", None, None, False]]
    # (e) ROLLBACK TOの後にRELEASEしないと、bind/rightは42501。
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        w.run("SAVEPOINT s")
        w.run("ROLLBACK TO SAVEPOINT s")
        e = _bind(w, env, b)
        w.run("ROLLBACK")
    assert e[1] == "42501"
    out["e_after_rollback_to_without_release"] = e[1]
    _record("T09", out)


def _lock_state(env: Env, b: dict) -> str:
    """別接続から端末行へFOR UPDATE NOWAITを試みた結果('free'または'locked')。"""
    with psycopg.connect(env.ctx.admin_dsn, autocommit=True) as conn:
        try:
            conn.execute(
                "SELECT 1 FROM public.trusted_devices WHERE tenant_id=%s "
                "AND device_id=%s FOR UPDATE NOWAIT",
                (env.ctx.tenant, env.ctx.device),
            )
        except psycopg.errors.LockNotAvailable as error:
            assert error.sqlstate == "55P03"
            return "locked"
        return "free"


def test_t10_device_lock_follows_the_top_level_tx(db1: Env) -> None:
    """T10: top-levelのbindの端末FOR SHAREは、savepointのrollbackで解放されない。

    nestedだけのbindはrollbackでlockも残らない。
    """
    env = db1
    out: dict[str, Any] = {}
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        _bind(w, env, b)
        w.run("SAVEPOINT s")
        w.run("ROLLBACK TO SAVEPOINT s")
        w.run("RELEASE SAVEPOINT s")
        out["top_level_held"] = _lock_state(env, b)
        w.run("COMMIT")
    out["after_commit"] = _lock_state(env, b)
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        w.run("SAVEPOINT s")
        got = _bind(w, env, b)  # nestedなので42501、lockも取り消される
        w.run("ROLLBACK TO SAVEPOINT s")
        w.run("RELEASE SAVEPOINT s")
        out["nested_only_held"] = _lock_state(env, b)
        w.run("ROLLBACK")
    assert got[1] == "42501"
    assert out == {
        "top_level_held": "locked",
        "after_commit": "free",
        "nested_only_held": "free",
    }, out
    _record("T10", out)


def test_t13_concurrent_transactions(db1: Env) -> None:
    """T13: (a)同じ束縛を第2接続から呼ぶと42501。(b)同端末の別束縛2TXは両方通る。"""
    env = db1
    with peer(env.db, APP) as w1, peer(env.db, APP) as w2:
        ev, b = _new_attempt(env, w1)
        _bind(w1, env, b)
        env.ctx.begin(w2)
        cross = _bind(w2, env, b)
        w2.run("ROLLBACK")
        assert cross[1] == "42501", cross
        w1.run("COMMIT")
    assert env.ctx.stamp_row(b) == [["device_verified", None, None, False]]
    with peer(env.db, APP) as w1, peer(env.db, APP) as w2:
        ev1, b1 = _new_attempt(env, w1)
        ev2, b2 = _new_attempt(env, w2)
        r1 = _bind(w1, env, b1)
        r2 = _bind(w2, env, b2)
        locked = _lock_state(env, b1)
        w1.run("COMMIT")
        still = _lock_state(env, b2)
        w2.run("COMMIT")
        free = _lock_state(env, b2)
    assert r1[:2] == r2[:2] == (("t",), "00000")
    assert (locked, still, free) == ("locked", "locked", "free")
    assert env.ctx.stamp_row(b1) == env.ctx.stamp_row(b2)
    _record("T13", dict(cross=cross[1], locks=[locked, still, free]))


def test_t14_privileges_and_system_column_acl(db1: Env) -> None:
    """T14: app/actorは印へ直接触れない。right ownerはDELETE/TRUNCATEなし。"""
    env = db1
    out: dict[str, Any] = {}
    from .sync_writer_binding_support import ACTOR

    for role in (APP, ACTOR):
        with peer(env.db, role) as w:
            for verb, statement in (
                ("select", "SELECT 1 FROM " + STAMP_TABLE + " LIMIT 1"),
                ("insert", "INSERT INTO " + STAMP_TABLE + " DEFAULT VALUES"),
                ("update", "UPDATE " + STAMP_TABLE + " SET state='invalid'"),
                ("delete", "DELETE FROM " + STAMP_TABLE),
                ("truncate", "TRUNCATE " + STAMP_TABLE),
            ):
                got = w.run(statement)
                assert got[1] == "42501", (role, verb, got)
                out[f"{role}.{verb}"] = got[1]
    owner_privs = env.ctx.admin(
        "SELECT has_table_privilege(%s,%s,'DELETE'),"
        "has_table_privilege(%s,%s,'TRUNCATE'),"
        "has_any_column_privilege(%s,%s,'INSERT'),"
        "has_any_column_privilege(%s,%s,'UPDATE'),"
        "has_table_privilege('public',%s,'SELECT')",
        (RIGHT_OWNER, STAMP_TABLE) * 2
        + (RIGHT_OWNER, STAMP_TABLE, RIGHT_OWNER, STAMP_TABLE, STAMP_TABLE),
        fetch=True,
    )
    assert owner_privs == [(False, False, True, True, False)], owner_privs
    # xmin(system列)のACLはattnum<=0に格納され、正式catalog(attnum>0だけ)から見えない。
    acl = env.ctx.admin(
        "SELECT c.relname,a.attname,a.attacl::text FROM pg_attribute a "
        "JOIN pg_class c ON c.oid=a.attrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='sync_fence' AND a.attnum<=0 AND c.relname IN "
        "('first_ball_write_admissions','writer_admissions') AND a.attacl IS NOT NULL",
        fetch=True,
    )
    assert acl == [], acl
    # 表単位SELECTを使う2表(xminを読むため)。
    selects = env.ctx.admin(
        "SELECT has_table_privilege(%s,"
        "'sync_fence.first_ball_write_admissions','SELECT'),"
        "has_table_privilege(%s,'sync_fence.writer_admissions','SELECT')",
        (RIGHT_OWNER, RIGHT_OWNER),
        fetch=True,
    )
    assert selects == [(True, True)]
    _record("T14", dict(out, owner=owner_privs, system_column_acl=acl))


def test_t17_tenant_isolation(db1: Env) -> None:
    """T17: GUCと引数のtenantが食い違うbind/rightは42501で、印を作らない。"""
    env = db1
    other = env.owner.other_tenant_id
    out = {}
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        # 引数のtenantを別tenantへ。
        statement = env.ctx.bind_sql(b, env.good).replace(
            _literal(env.ctx.tenant), _literal(other), 1
        )
        assert _literal(other) in statement
        got = w.run(statement)
        w.run("ROLLBACK")
        out["arg_other_tenant"] = got[1]
        assert got[1] == "42501", got
        # GUCを別tenantへ。
        env.ctx.begin(w)
        w.query("SELECT set_config('app.tenant_id','" + str(other) + "',true)")
        got2 = _right(w, env, b)
        w.run("ROLLBACK")
        out["guc_other_tenant"] = got2[1]
        assert got2[1] == "42501", got2
    assert env.ctx.stamp_row(b) == []
    _record("T17", out)


def test_t20_context_rejections(db1: Env) -> None:
    """T20: 欠落・偽造・別端末・別試合・失効(期限)の文脈は、印を進めない。

    D09の「全適用経路の拒否検証」への入力であり、対応表や検証そのものではない。
    """
    env = db1
    out: dict[str, Any] = {}
    other_device, other_game = uuid4(), uuid4()
    # 欠落: 束縛が無い(publishしていない)attempt/phase。
    with peer(env.db, APP) as w:
        env.ctx.begin(w)
        phantom = {
            "attempt": uuid4(),
            "phase": uuid4(),
            "nonce": os.urandom(32),
            "binding": {},
            "event": {},
        }
        got = _bind(w, env, phantom)
        w.run("ROLLBACK")
    # 束縛が無いときは既存のassertが「no_data_found(P0002)」で閉じる(B以前の挙動)。
    assert got[1] in {"42501", "P0002"}, got
    assert leaks(got[2], [str(env.ctx.tenant), phantom["nonce"].hex()]) == []
    out["missing_binding"] = got[1]
    # 偽造: nonceが違う。
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        forged = dict(b, nonce=os.urandom(32))
        got = _bind(w, env, forged)
        w.run("ROLLBACK")
    assert got[1] == "42501"
    out["forged_nonce"] = got[1]
    # 別端末・別試合(束縛と引数のdevice_id/game_idがずれる)。
    for label, kwargs in (
        ("other_device", dict(device=other_device)),
        ("other_game", dict(game=other_game)),
    ):
        with peer(env.db, APP) as w:
            ev, b = _new_attempt(env, w)
            got_b = w.run(env.ctx.bind_sql(b, env.good, **kwargs))
            w.run("ROLLBACK")
        assert got_b[1] == "42501", (label, got_b)
        out[label] = got_b[1]
        assert env.ctx.stamp_row(b) == []
    # 偽造: 資格digestが違う → bind=false・印invalid(commit後に観測)。
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        got = _bind(w, env, b, bad=True)
        w.run("COMMIT")
    assert got[:2] == (("f",), "00000")
    assert env.ctx.stamp_row(b) == [["invalid", None, None, False]]
    out["forged_credential"] = "bind=false,invalid"
    # 失効(期限切れ): bind(true)の後、期限を過ぎてright → 42501。savepointで取り消して
    # top-levelへ戻すと、印はdevice_verifiedのまま残る(期限切れは印を進めない)。
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w, ttl=3)
        _bind(w, env, b)
        time.sleep(4)
        w.run("SAVEPOINT s")
        late = _right(w, env, b)
        w.run("ROLLBACK TO SAVEPOINT s")
        w.run("RELEASE SAVEPOINT s")
        ins = _insert(w, env, ev)
        w.run("ROLLBACK" if ins[1] != "00000" else "COMMIT")
    assert late[1] == "42501" and ins[1] == "42501", (late, ins)
    out["expired"] = [late[1], ins[1]]
    _record("T20", out)


# 42501=資格/照合の拒否、55000=gate閉、55P03=lock待ち。P0002は束縛が無いときの
# 既存assert(B以前)の挙動で、拒否ではなくfail-closedの別SQLSTATEとして区別する。
_SQLSTATE_OK = {"42501", "55000", "55P03", "P0002"}


def test_t21_sqlstate_contract_and_no_sensitive_values(db1: Env) -> None:
    """T21: Bの拒否のSQLSTATEは42501/55000、lock待ちは55P03(固定文言・機微値なし)。"""
    env = db1
    seen: dict[str, str] = {}
    texts: list[tuple[str, str, list[str]]] = []
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        sens = env.ctx.sensitive(b)
        # 資格の拒否: 入力検査・binding不成立。
        short = w.run(
            "SELECT device_matches FROM sync_right_api.bind_device("
            + env.ctx.common_args(b)
            + ",'\\x00'::bytea)"
        )
        w.run("ROLLBACK")
        texts.append(("input_rejected", short[2], sens))
        seen["input_rejected"] = short[1]
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        sens = env.ctx.sensitive(b)
        w.run("SAVEPOINT s")
        nested = _bind(w, env, b)
        w.run("ROLLBACK TO SAVEPOINT s")
        w.run("ROLLBACK")
        texts.append(("stamp_nested", nested[2], sens))
        seen["stamp_nested"] = nested[1]
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        sens = env.ctx.sensitive(b)
        forged = _bind(w, env, dict(b, nonce=os.urandom(32)))
        w.run("ROLLBACK")
        texts.append(("assert_rejected", forged[2], sens))
        seen["assert_rejected"] = forged[1]
    with peer(env.db, APP) as w:
        env.ctx.begin(w)
        phantom = {
            "attempt": uuid4(),
            "phase": uuid4(),
            "nonce": os.urandom(32),
        }
        missing = _bind(w, env, phantom)
        w.run("ROLLBACK")
        texts.append(
            (
                "missing_binding",
                missing[2],
                [str(env.ctx.tenant), str(phantom["attempt"]), phantom["nonce"].hex()],
            )
        )
        seen["missing_binding"] = missing[1]
    # lock待ち: 別接続が端末行をFOR UPDATEで保持し、lock_timeoutを短くする。
    with (
        psycopg.connect(env.ctx.admin_dsn) as holder,
        peer(env.db, APP) as w,
    ):
        holder.execute(
            "SELECT 1 FROM public.trusted_devices WHERE tenant_id=%s "
            "AND device_id=%s FOR UPDATE",
            (env.ctx.tenant, env.ctx.device),
        )
        ev, b = _new_attempt(env, w)
        sens = env.ctx.sensitive(b)
        w.query("SET LOCAL lock_timeout='300ms'")
        waited = _bind(w, env, b)
        w.run("ROLLBACK")
        holder.rollback()
        texts.append(("lock_timeout", waited[2], sens))
        seen["lock_timeout"] = waited[1]
    assert seen == {
        "input_rejected": "42501",
        "stamp_nested": "42501",
        "assert_rejected": "42501",
        "lock_timeout": "55P03",
        "missing_binding": "P0002",
    }, seen
    assert set(seen.values()) <= _SQLSTATE_OK
    for label, text, sens in texts:
        assert leaks(text, sens) == [], (label, leaks(text, sens))
        assert all("ERROR" in line for line in error_lines(text)), (
            label,
            error_lines(text),
        )
    _record(
        "T21",
        dict(
            sqlstates=seen,
            error_lines={label: error_lines(text) for label, text, _ in texts},
        ),
    )


def test_t22_ii_signature_after_apply_matches_the_formal_signature(db1: Env) -> None:
    """T22(ii): 候補適用後のbind/rightの署名・所有者・ACLは正式なものと同じ。"""
    env = db1
    rows = env.ctx.admin(
        "SELECT p.proname,pg_get_function_identity_arguments(p.oid),"
        "pg_get_function_result(p.oid),p.prosecdef,p.provolatile,p.proconfig::text,"
        "pg_get_userbyid(p.proowner),p.proacl::text,l.lanname "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "JOIN pg_language l ON l.oid=p.prolang "
        "WHERE n.nspname='sync_right_api' AND p.proname IN "
        "('bind_device','check_current_right') ORDER BY 1",
        fetch=True,
    )
    assert rows is not None and len(rows) == 2
    by_name = {r[0]: r for r in rows}
    for name, result in (
        ("bind_device", "TABLE(device_matches boolean)"),
        (
            "check_current_right",
            "TABLE(recovery_matches boolean, right_matches boolean)",
        ),
    ):
        row = by_name[name]
        assert row[2] == result, row
        assert row[3] is True and row[4] == "v" and row[8] == "plpgsql", row
        config = row[5].replace('"', "").replace(" ", "")
        assert config == "{search_path=pg_catalog,pg_temp}", row
        assert row[6] == RIGHT_OWNER, row
        # 実行権はappだけ(CREATE OR REPLACEで所有者・ACLを変えていない)。
        acl = row[7].strip("{}").split(",")
        assert "pitchlog_app=X/" + RIGHT_OWNER in acl, row
        assert not any(item.startswith("=") for item in acl), row  # PUBLICなし
    _record("T22_ii", {k: list(v) for k, v in by_name.items()})


# ---------------------------------------------------------------------------
# DB2: 候補適用前から始める破壊を伴う試験(定義順に実行する)
# ---------------------------------------------------------------------------


def _report(conn: psycopg.Connection, oid: int):
    from pitchlog.authz.product_catalog import inspect_product_authz_catalog

    try:
        return inspect_product_authz_catalog(
            conn, privileged_role_oids=frozenset({oid})
        )
    finally:
        conn.rollback()


def test_t22_i_formal_catalog_before_and_after_candidates(db2: Env) -> None:
    """T22(i): 結合後の正式installer適用DBでは正式catalogがok。候補適用はdrift。

    あわせて、xmin列ACLの付与は正式catalogが見逃し(盲点)、直接検査が検出することを記録する。
    """
    env = db2
    assert not env.applied
    with psycopg.connect(env.ctx.admin_dsn) as conn:
        row = conn.execute(
            "SELECT oid FROM pg_roles WHERE rolname=session_user"
        ).fetchone()
        assert row is not None
        oid = row[0]
        conn.rollback()
        before = _report(conn, oid)
        assert before.ok and not before.violations, before.violations[:3]
        n_checked = len(before.checked_ids)
        assert n_checked >= 31
        # 盲点の記録: xminの列SELECTを足しても正式catalogはdrift0、直接検査は検出する。
        conn.execute(
            "GRANT SELECT (xmin) ON sync_fence.first_ball_write_admissions "
            "TO " + RIGHT_OWNER
        )
        conn.commit()
        blind = _report(conn, oid)
        direct = conn.execute(
            "SELECT a.attacl::text FROM pg_attribute a WHERE a.attrelid="
            "'sync_fence.first_ball_write_admissions'::regclass AND a.attnum<=0 "
            "AND a.attacl IS NOT NULL"
        ).fetchall()
        conn.rollback()
        conn.execute(
            "REVOKE SELECT (xmin) ON sync_fence.first_ball_write_admissions "
            "FROM " + RIGHT_OWNER
        )
        conn.commit()
        assert blind.ok, "盲点の前提(xmin列ACLは正式catalogから見えない)が成立しない"
        assert direct, "直接検査がxmin列ACLを検出しない"
        # 署名の記録(適用前)。
        before_sig = conn.execute(
            "SELECT p.proname,pg_get_function_identity_arguments(p.oid),"
            "pg_get_function_result(p.oid),p.prosecdef,p.proconfig::text,"
            "pg_get_userbyid(p.proowner),p.proacl::text FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname="
            "'sync_right_api' AND p.proname IN ('bind_device','check_current_right') "
            "ORDER BY 1"
        ).fetchall()
        conn.rollback()
    counts = apply_candidates(env.owner)
    env.applied = True
    with psycopg.connect(env.ctx.admin_dsn) as conn:
        after = _report(conn, oid)
        after_sig = conn.execute(
            "SELECT p.proname,pg_get_function_identity_arguments(p.oid),"
            "pg_get_function_result(p.oid),p.prosecdef,p.proconfig::text,"
            "pg_get_userbyid(p.proowner),p.proacl::text FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname="
            "'sync_right_api' AND p.proname IN ('bind_device','check_current_right') "
            "ORDER BY 1"
        ).fetchall()
        conn.rollback()
    assert before_sig == after_sig, "適用の前後で署名・所有者・ACLが変わった"
    assert not after.ok
    checks = sorted({v.check_id for v in after.violations})
    assert checks == [
        "PRODUCT-CATALOG:COLUMN-ACL",
        "PRODUCT-CATALOG:LIFECYCLE-FUNCTION-DETAILS",
        "PRODUCT-CATALOG:POLICIES",
        "PRODUCT-CATALOG:SCHEMA-ACL",
        "PRODUCT-CATALOG:TABLE-ACL",
    ], checks
    _record(
        "T22_i",
        dict(
            before=dict(ok=True, n_checked=n_checked),
            blind_spot=dict(catalog_ok=blind.ok, direct_attacl=direct),
            after_candidate=dict(ok=after.ok, check_ids=checks),
            signature_unchanged=True,
            applied_counts=counts,
        ),
    )


def test_t15_reapply(db2: Env) -> None:
    """T15: (a)B版bodyのDBへ現行installerを再実行すると衝突停止。(b)適用は冪等。"""
    from pitchlog.authz.product_provisioning import apply_product_authz_ddl

    env = db2
    assert env.applied
    sig_sql = (
        "SELECT p.proname,md5(p.prosrc),p.proacl::text,pg_get_userbyid(p.proowner) "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname='sync_right_api' AND p.proname IN "
        "('bind_device','check_current_right') ORDER BY 1"
    )
    before = env.ctx.admin(sig_sql, fetch=True)
    # (b) 候補の2回適用(CREATE OR REPLACE)は冪等。
    with psycopg.connect(env.ctx.admin_dsn) as conn:
        for text in render_stamped_function_sql().values():
            exec_text(conn, text)
        conn.commit()
    assert env.ctx.admin(sig_sql, fetch=True) == before
    # (a) 現行installer(0037世代のbody資産)の再実行 → 衝突で停止。
    with psycopg.connect(env.ctx.admin_dsn) as applicator:
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="first ball function definition collision",
        ) as error:
            apply_product_authz_ddl(applicator)
        applicator.rollback()
    assert error.value.sqlstate == "P0001"
    assert env.ctx.admin(sig_sql, fetch=True) == before
    _record("T15", dict(idempotent=True, installer_reapply="collision(P0001)"))


def _old_bind_replace_sql() -> str:
    """正式(0037世代)のbind_deviceを`CREATE OR REPLACE`にした文(変異用)。"""
    old = render_sync_right_sql()
    match = re.search(
        r"CREATE FUNCTION (sync_right_api\.bind_device\(.*?\$function\$;)",
        old,
        re.S,
    )
    assert match
    return "CREATE OR REPLACE FUNCTION " + match.group(1)


def test_c8_mutation_without_bind_stamp_turns_the_vertical_red(db2: Env) -> None:
    """C8: bind_deviceの印書込を外すと縦(V1)が赤になる。印は正規経路の本文に依る。"""
    env = db2
    assert env.applied
    stamped = render_stamped_function_sql()
    with psycopg.connect(env.ctx.admin_dsn) as conn:
        exec_text(conn, _old_bind_replace_sql())
        conn.commit()
    try:
        with peer(env.db, APP) as w:
            ev, b = _new_attempt(env, w)
            r1 = _bind(w, env, b)
            r2 = _right(w, env, b)
            ins = _insert(w, env, ev)
            w.run("ROLLBACK")
        # bindの戻りは変わらないが印が作られず、rightは逆順としてinvalidを書く。
        assert r1[:2] == (("t",), "00000") and r2[:2] == (("t|t",), "00000")
        assert ins[1] == "42501", "bindの印書込を外してもINSERTが通ってしまった"
    finally:
        with psycopg.connect(env.ctx.admin_dsn) as conn:
            exec_text(conn, stamped["bind_device"])
            conn.commit()
    # 元の本文へ戻すとV1相当が再び成立する。
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        _bind(w, env, b)
        _right(w, env, b)
        ins = _insert(w, env, ev)
        w.run("COMMIT")
    assert ins[1] == "00000"
    _record("C8_mutation", dict(without_bind_stamp_insert="42501", restored="00000"))


def test_t11_gate_epoch_and_revocation(db2: Env) -> None:
    """T11: gate閉・epoch変更・端末失効は、印を進めない(最後に端末を失効させる)。"""
    env = db2
    out: dict[str, Any] = {}
    # gate閉: 束縛の発行と端末照合を済ませた後、admin接続がcommitして閉じる。
    # check_current_rightは55000で閉じ、印は変わらない(savepointで取り消して観測)。
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        _bind(w, env, b)
        with psycopg.connect(env.ctx.admin_dsn) as conn:
            conn.execute("SET lock_timeout='3s'")
            try:
                conn.execute("UPDATE public.rg1_restore_gate SET state='closed'")
                conn.commit()
                out["gate_close"] = "committed"
            except psycopg.Error as error:
                conn.rollback()
                out["gate_close"] = error.sqlstate
        if out["gate_close"] == "committed":
            w.run("SAVEPOINT s")
            closed = _right(w, env, b)
            w.run("ROLLBACK TO SAVEPOINT s")
            w.run("RELEASE SAVEPOINT s")
            w.run("COMMIT")
            with psycopg.connect(env.ctx.admin_dsn) as conn:
                conn.execute("UPDATE public.rg1_restore_gate SET state='open'")
                conn.commit()
            # gateが閉じると、入口のassert_writer_bindingが先に42501で閉じる
            # (check_current_right自身の55000は、assertを通る状態では到達しない)。
            assert closed[1] == "42501" and "writer binding rejected" in closed[2]
            assert env.ctx.stamp_row(b) == [["device_verified", None, None, False]]
            out["gate_closed_right"] = closed[1]
        else:
            w.run("ROLLBACK")
    # 端末失効: bindはfalse、印はinvalid。以後のright(true)でも復活しない。
    with psycopg.connect(env.ctx.admin_dsn) as conn:
        conn.execute(
            "UPDATE public.trusted_devices SET revoked_at=clock_timestamp() "
            "WHERE tenant_id=%s AND device_id=%s",
            (env.ctx.tenant, env.ctx.device),
        )
        conn.commit()
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        rev = _bind(w, env, b)
        right = _right(w, env, b)
        ins = _insert(w, env, ev)
        w.run("ROLLBACK")
    assert rev[:2] == (("f",), "00000"), rev
    assert right[:2] == (("t|t",), "00000"), right
    assert ins[1] == "42501", ins
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        _bind(w, env, b)
        _right(w, env, b)
        w.run("COMMIT")
    assert env.ctx.stamp_row(b) == [["invalid", None, None, False]]
    out["revoked"] = dict(bind=rev[0], insert=ins[1], stamp="invalid")
    # epoch変更(最後。戻せない前提で行う): 束縛の後にgateのepochが進むと、
    # 束縛の復元世代と食い違い、入口のassertが42501で閉じる。印は進まない。
    with peer(env.db, APP) as w:
        ev, b = _new_attempt(env, w)
        with psycopg.connect(env.ctx.admin_dsn) as conn:
            conn.execute("SET lock_timeout='3s'")
            try:
                conn.execute(
                    "UPDATE public.rg1_restore_gate SET recovery_generation="
                    "recovery_generation+1"
                )
                conn.commit()
                out["epoch_change"] = "committed"
            except psycopg.Error as error:
                conn.rollback()
                out["epoch_change"] = error.sqlstate
        if out["epoch_change"] == "committed":
            changed = _bind(w, env, b)
            w.run("ROLLBACK")
            assert changed[1] == "42501", changed
            out["epoch_change_bind"] = changed[1]
        else:
            w.run("ROLLBACK")
    _record("T11", out)


# ---------------------------------------------------------------------------
# V10: scaffoldの印0件(DB1の全admin statementの台帳)
# ---------------------------------------------------------------------------


def test_v10_no_scaffold_stamp_dml(db1: Env, db2: Env) -> None:
    """V10: adminが実行した全statementに、印の表への直接INSERT/UPDATE/DELETEが0件。

    変異(adminが印を入れる版)は検出器が赤にする。
    """
    for label, env in (("db1", db1), ("db2", db2)):
        assert stamp_dml_statements(env.ctx.admin_log) == [], label
        assert len(env.ctx.admin_log) > 0
    forged = (
        "INSERT INTO sync_fence.first_ball_write_admissions(tenant_id,state) "
        "SELECT tenant_id,'right_verified' FROM sync_fence.writer_bindings"
    )
    assert stamp_dml_statements([forged]) == [forged]
    assert stamp_dml_statements(
        ["UPDATE sync_fence.first_ball_write_admissions SET state='consumed'"]
    )
    # 印の表のSELECT(観測)は書込ではない。
    assert not stamp_dml_statements(
        ["SELECT state FROM sync_fence.first_ball_write_admissions"]
    )
    _record(
        "V10",
        dict(
            admin_statements=dict(
                db1=len(db1.ctx.admin_log), db2=len(db2.ctx.admin_log)
            ),
            stamp_dml=0,
            scaffold_rows=sorted(set(db1.ctx.scaffold)),
        ),
    )


# ---------------------------------------------------------------------------
# V11 / T16 / T09(f): 実cookie・実run_functionの縦断(独立DB)
# ---------------------------------------------------------------------------


@pytest.fixture(params=[False, True], ids=["no-candidate", "candidate"])
def real_owner(request: pytest.FixtureRequest) -> Iterator[Any]:
    """実cookie縦断用の独立owned DB(候補適用なし/あり)。"""
    from db_fixtures import _dsn_names

    with pytest.MonkeyPatch.context() as patch:
        with owned_binding_database(patch) as owner:
            admin_name, role_name = _dsn_names()
            patch.setenv(admin_name, owner.authority.database.primary_admin)
            patch.setenv(role_name, owner.authority.database.endpoints.primary_dsn)
            if request.param:
                apply_candidates(owner)
            setattr(owner, "_stamp_candidate_applied", request.param)
            yield owner


def _assert_real_stack_scenarios(report: dict[str, Any]) -> None:
    """実SQLAlchemy・実run_in_savepointでのT09(f)・T18(a)(b)の観測を表明する。"""
    t09f, t18a, t18b = report["t09f"], report["t18a"], report["t18b"]
    # T09(f): bind tokenはDML registry外なのでPython側で止まり、SQLは何も出ない
    # (SAVEPOINTも出ない)。TXはtop-levelのままで、その後のbindは通る。
    assert t09f["python_stop"] == "_TenantOperationError", t09f
    assert "reached_db" not in t09f and t09f["nested_after"] is False, t09f
    assert t09f["savepoint_statements"] == [], t09f
    assert t09f["bind_after"] == "((True,),)", t09f
    # T18(a): 実D5一意衝突でSAVEPOINT→INSERT→ROLLBACK TO(RELEASEなし)。
    # その後のbindは42501。
    assert t18a["d5_race_candidate"] == "stored_result", t18a
    assert t18a["savepoint_statements"] == [
        "SAVEPOINT sa_savepoint_1",
        "ROLLBACK TO SAVEPOINT sa_savepoint_1",
    ], t18a
    assert t18a["bind_after"] == "42501", t18a
    # T18(b): 実run_in_savepointが成功(RELEASE)した後のbind/rightは通る。
    assert t18b["insert_result"] is None, t18b
    assert t18b["savepoint_statements"] == [
        "SAVEPOINT sa_savepoint_1",
        "RELEASE SAVEPOINT sa_savepoint_1",
    ], t18b
    assert t18b["bind"] == "((True,),)" and t18b["right"] == "((True, True),)", t18b


def test_v11_t16_real_run_function_path(real_owner: Any) -> None:
    """V11/T16: 実cookie・実run_functionでbind→rightを呼ぶ既存縦断の回帰と、印の観測。

    候補適用なしでは印は0行(既存縦断は緑のまま)。候補適用ありではcommit後に
    right_verifiedの1行(2つ目のattemptはrollbackで0行)。candidateでは、実SQLAlchemyの
    経路でT09(f)・T18(a)(b)(実run_in_savepointの失敗・成功の後のbind)も観測する。
    """
    from pitchlog.repositories.initial_recording_right import _credential_digest

    db = real_owner
    applied = bool(getattr(db, "_stamp_candidate_applied", False))
    issued = db.actor("grant=issue(); print(json.dumps(receipt(grant)))")
    token, subject = UUID(int=7201), UUID(int=7202)
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.system_settings(key,value) VALUES "
            "('auth.token_ttl_seconds','3600') ON CONFLICT(key) "
            "DO UPDATE SET value=EXCLUDED.value"
        )
        admin.execute(
            "INSERT INTO public.tenant_auth_subjects(tenant_id,id) VALUES (%s,%s)",
            (db.tenant_id, subject),
        )
        admin.execute(
            "INSERT INTO public.tenant_credentials(auth_subject_id,password_hash,"
            "generation) VALUES (%s,'public-unused-login-vector',1)",
            (subject,),
        )
        admin.execute(
            "INSERT INTO public.tenant_tokens(tenant_id,id,auth_subject_id,"
            "credential_generation,expires_at,last_used_at) VALUES "
            "(%s,%s,%s,1,clock_timestamp()+interval '1 hour',clock_timestamp())",
            (db.tenant_id, token, subject),
        )
    credential = _credential_digest("credential-a").hex()
    if applied:
        # T18(a)用のscaffold: 先着のD5台帳行(印ではない)。実D5一意衝突を起こす。
        with psycopg.connect(db.authority.database.business_admin) as admin:
            admin.execute(
                "INSERT INTO public.idempotency_ledger(tenant_id,d5,kind,"
                "source_fingerprint,result) VALUES (%s,%s,'accepted',"
                "'public-event-fp','{}'::jsonb)",
                (db.tenant_id, UUID(int=9001)),
            )
    scenarios = """
from sqlalchemy import event
from pitchlog.repositories.transaction import _TRANSACTION_RUNTIMES
from pitchlog.sync.idempotency import insert_result_or_recheck
from pitchlog.sync.tokens import IdempotencyLedgerInsertToken
CRED=bytes.fromhex('%s')
PROOF=bytes.fromhex('%s')
CURRENT=[]
HOOKED=set()
def sqlstate(error):
 return getattr(getattr(error,'orig',None),'sqlstate',None) or type(error).__name__
def scenario(name,steps):
 sa=AttemptBinding(authority,context.tenant_id,attempt.device_id,attempt.game_id,
  attempt.wire_d4,attempt.internal_generation,uuid4(),1,'public-'+name+'-rq',1)
 sp=EventPhaseBinding(sa,uuid4(),1,1,uuid4(),'public-'+name+'-ev')
 out={}
 try:
  with tenant_transaction_scope(context) as tx:
   session,_=_TRANSACTION_RUNTIMES[tx._state_key]
   engine=session.get_bind()
   if id(engine) not in HOOKED:
    HOOKED.add(id(engine))
    event.listen(engine,'before_cursor_execute',
     lambda c,cur,st,pa,ctx,em: CURRENT and
      CURRENT[-1].append(st.split(chr(10))[0][:40]))
   log=[];CURRENT.append(log)
   bound=control.bind_writer(tx,context,sp,cookie=cookie)
   bt=_BindFirstBallDeviceToken(sa.attempt_id,sp.phase_id,bound._lease.nonce,
    sa.device_id,sa.game_id,CRED)
   rt=_CheckFirstBallRightToken(sa.attempt_id,sp.phase_id,bound._lease.nonce,
    sa.device_id,sa.game_id,sa.internal_generation,1,PROOF)
   steps(tx,session,bt,rt,out)
   out['savepoint_statements']=[x for x in log if x.startswith(
    ('SAVEPOINT','ROLLBACK TO','RELEASE'))]
   raise PlannedRollback(name)
 except PlannedRollback:
  pass
 return out
def t09f(tx,session,bt,rt,out):
 try:
  tx.run_in_savepoint(bt); out['reached_db']=True
 except Exception as error:
  out['python_stop']=type(error).__name__
 out['nested_after']=session.in_nested_transaction()
 try:
  out['bind_after']=str(tx.run_function(bt).rows)
 except Exception as error:
  out['bind_after']=sqlstate(error)
def t18a(tx,session,bt,rt,out):
 token=IdempotencyLedgerInsertToken(UUID(int=9001),'accepted','public-event-fp','{}')
 out['d5_race_candidate']=insert_result_or_recheck(tx,token,'P1').kind
 try:
  out['bind_after']=str(tx.run_function(bt).rows)
 except Exception as error:
  out['bind_after']=sqlstate(error)
def t18b(tx,session,bt,rt,out):
 token=IdempotencyLedgerInsertToken(uuid4(),'accepted','public-event-fp','{}')
 out['insert_result']=insert_result_or_recheck(tx,token,'P1')
 out['bind']=str(tx.run_function(bt).rows)
 out['right']=str(tx.run_function(rt).rows)
extra['t09f']=scenario('t09f',t09f)
extra['t18a']=scenario('t18a',t18a)
extra['t18b']=scenario('t18b',t18b)
""" % (credential, issued["proof_digest"])
    body = f"""
authority=AuthorityBinding(UUID(int=7101),UUID(int=7102),UUID(int=7103))
attempt=AttemptBinding(authority,context.tenant_id,UUID('{db.device_id}'),
 UUID('{db.game_id}'),'fixture-first-ball',{issued["generation"]},uuid4(),1,
 'public-single-request-fp',1)
phase=EventPhaseBinding(attempt,uuid4(),1,1,uuid4(),'public-single-event-fp')
with tenant_transaction_scope(context) as tx:
 bound=control.bind_writer(tx,context,phase,cookie=cookie)
 bound.assert_current()
 device=tx.run_function(_BindFirstBallDeviceToken(attempt.attempt_id,
  phase.phase_id,bound._lease.nonce,attempt.device_id,attempt.game_id,
  bytes.fromhex('{credential}')))
 assert device.rows==((True,),)
 right=tx.run_function(_CheckFirstBallRightToken(attempt.attempt_id,
  phase.phase_id,bound._lease.nonce,attempt.device_id,attempt.game_id,
  attempt.internal_generation,1,bytes.fromhex('{issued["proof_digest"]}')))
 assert right.rows==((True,True),)
class PlannedRollback(Exception):
 pass
try:
 with tenant_transaction_scope(context) as tx:
  second_attempt=AttemptBinding(authority,context.tenant_id,attempt.device_id,
   attempt.game_id,attempt.wire_d4,attempt.internal_generation,uuid4(),1,
   'public-second-request-fp',1)
  second_phase=EventPhaseBinding(second_attempt,uuid4(),1,1,uuid4(),
   'public-second-event-fp')
  control.bind_writer(tx,context,second_phase,cookie=cookie)
  raise PlannedRollback('controlled outer rollback')
except PlannedRollback:
 pass
else:
 raise AssertionError('outer rollback was not propagated')
extra={{}}
{scenarios if applied else ""}
print(json.dumps(dict(actual_cookie=True,actual_u1_device=True,
 actual_u1_right=True,actual_commit_and_terminal=True,actual_rollback=True,
 **extra)))
"""
    with binding_broker(db, token):
        got = binding_app(db, body)
    t09f_report = {k: got.pop(k) for k in ("t09f", "t18a", "t18b") if k in got}
    assert got == dict(
        actual_cookie=True,
        actual_u1_device=True,
        actual_u1_right=True,
        actual_commit_and_terminal=True,
        actual_rollback=True,
    ), got
    with psycopg.connect(db.authority.database.business_admin) as admin:
        stamp = admin.execute(
            "SELECT state,source_event_id IS NULL,play_row_id IS NULL FROM "
            + STAMP_TABLE
        ).fetchall()
        bindings = admin.execute(
            "SELECT state,count(*) FROM sync_fence.writer_bindings GROUP BY state"
        ).fetchall()
    # 既存縦断の他の観測(2束縛ともclosed)は維持される。
    assert bindings and all(state == "closed" for state, _ in bindings), bindings
    if applied:
        assert stamp == [("right_verified", True, True)], stamp
        # T09(f): 実run_in_savepointはbind tokenを関数へ届けず(DML registry外)、
        # SQL/SAVEPOINTは発行されずtop-levelを保ち、後続run_function(bind)は成功する。
        assert t09f_report is not None, got
        _assert_real_stack_scenarios(t09f_report)
    else:
        assert stamp == [], stamp
    _record(
        "V11_T16_" + ("candidate" if applied else "no_candidate"),
        dict(stamp=stamp, bindings=bindings, t09f=t09f_report),
    )
