"""D03の完全な版付き供給を仮定したSQLだけを独立期待へ照合する。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from pitchlog.domaingen.stats_appearance import (
    AppearanceDeclarationError,
    generate_appearance_bundle,
)

_ROOT = Path(__file__).resolve().parents[2]
_TARGET = "backend/src/pitchlog/stats/generated/appearances.sql"


def _query():
    """期待ケースを入力にせず実builderから唯一SQLを読む。"""
    bundle, manifest = generate_appearance_bundle()
    assert manifest["providerInstalled"] is False
    return bundle[_TARGET]


def _evaluate(scopes, members, *, player="p1", tenant="t1", expected_games=None):
    """合成sourceだけをSQLiteへ与える。真正PG/provider成功とは分ける。"""
    with sqlite3.connect(":memory:") as db:
        db.execute(
            "CREATE TABLE appearance_scope (tenant_id,game_id,fact_version_id,"
            "revision,source_set_sha256,supply_complete,member_count)"
        )
        db.execute(
            "CREATE TABLE appearance_members (tenant_id,game_id,fact_version_id,"
            "revision,source_set_sha256,player_id,proof_kind,proof_source_id)"
        )
        db.executemany("INSERT INTO appearance_scope VALUES (?,?,?,?,?,?,?)", scopes)
        db.executemany(
            "INSERT INTO appearance_members VALUES (?,?,?,?,?,?,?,?)", members
        )
        return db.execute(
            _query(),
            {
                "tenant_id": tenant,
                "player_id": player,
                "expected_game_count": len(scopes)
                if expected_games is None
                else expected_games,
            },
        ).fetchone()


def _scope(game="g1", *, version="v1", revision=1, digest="s1", count=1, complete=True):
    return ("t1", game, version, revision, digest, complete, count)


def _member(
    game="g1",
    *,
    player="p1",
    proof="proof1",
    kind="pitcher-defensive-entry",
    version="v1",
    revision=1,
    digest="s1",
):
    return ("t1", game, version, revision, digest, player, kind, proof)


def test_generated_target_is_reproducible_and_unconnected():
    """候補生成物は実宣言と一致するがprovider登録成功を名乗らない。"""
    query = _query()
    assert (_ROOT / _TARGET).read_text() == query
    _, manifest = generate_appearance_bundle()
    assert (
        json.loads(
            (_ROOT / "backend/domain/stats-appearance.manifest.json").read_text()
        )
        == manifest
    )
    assert query.count("COUNT(DISTINCT m.game_id)") == 1
    assert "game_lineups" not in query and "pitch_count" not in query
    assert "participation_intervals" not in query


@pytest.mark.parametrize("kind", ["defensive-half-entry", "pitcher-defensive-entry"])
def test_actual_entry_without_pitch_is_counted(kind):
    """供給済み実出場は球数0でも1。球数自体を入力にしない。"""
    assert _evaluate([_scope()], [_member(kind=kind)]) == (
        "appearances",
        "available",
        1,
    )


def test_repeat_entry_one_game_and_two_games_are_distinct():
    """同試合再登板は1、別試合は2。メンバー順を変えても同値。"""
    scopes = [_scope(count=2), _scope("g2")]
    members = [_member(), _member(proof="proof2"), _member("g2")]
    for rows in [members, list(reversed(members))]:
        assert _evaluate(scopes, rows) == ("appearances", "available", 2)


def test_complete_zero_and_unrelated_player_are_zero():
    """完全空集合だけは0。不足供給を0へ変えない。"""
    assert _evaluate([_scope(count=0)], []) == ("appearances", "available", 0)
    assert _evaluate([_scope()], [_member(player="p2")]) == (
        "appearances",
        "available",
        0,
    )
    assert _evaluate([_scope(count=0, complete=False)], []) == (
        "appearances",
        "source_unavailable",
        None,
    )


@pytest.mark.parametrize(
    "fault",
    [
        "version",
        "revision",
        "digest",
        "missing",
        "count",
        "unknown-proof",
        "no-proof",
        "no-player",
        "null-scope",
        "duplicate-game",
    ],
)
def test_incomplete_or_mismatched_supply_is_not_zero(fault):
    """旧版/不足/偽の出場種類をavailableへ写さない。"""
    scopes = [_scope()]
    members = [_member()]
    if fault == "version":
        members = [_member(version="v0")]
    elif fault == "revision":
        members = [_member(revision=0)]
    elif fault == "digest":
        members = [_member(digest="wrong")]
    elif fault == "missing":
        members = []
    elif fault == "count":
        scopes = [_scope(count=2)]
    elif fault == "unknown-proof":
        members = [_member(kind="listed-in-starting-lineup")]
    elif fault == "no-proof":
        members = [_member(proof=None)]
    elif fault == "no-player":
        members = [_member(player=None)]
    elif fault == "null-scope":
        scopes = [_scope(version=None)]
    else:
        scopes = [_scope(), _scope(version="v2")]
    assert _evaluate(scopes, members) == ("appearances", "source_unavailable", None)


def test_other_tenant_rows_cannot_create_an_appearance_or_poison_supply():
    """別tenantの原本を計数や自tenantの失敗へ混ぜない。認可証拠ではない。"""
    foreign = ("t2", *list(_member())[1:])
    assert _evaluate([_scope(count=0)], [foreign]) == ("appearances", "available", 0)


@pytest.mark.parametrize(
    "mutation", ["unknown-root", "wrong-kind", "drop-complete", "count-pitches"]
)
def test_generator_rejects_changed_meaning(tmp_path, mutation):
    """未知の宣言を既D03の生成へ紛れ込ませない。"""
    for name in [
        "backend/domain/stats-appearance.model.json",
        "backend/domain/stats-appearance.schema.json",
        "backend/src/pitchlog/domaingen/stats_appearance.py",
    ]:
        out = tmp_path / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes((_ROOT / name).read_bytes())
    path = tmp_path / "backend/domain/stats-appearance.model.json"
    model = json.loads(path.read_text())
    if mutation == "unknown-root":
        model["extra"] = True
    elif mutation == "wrong-kind":
        model["source"]["proofKinds"] = ["starter-listed"]
    elif mutation == "drop-complete":
        model["source"]["requiresCompleteSupply"] = False
    else:
        model["aggregate"]["key"] = "pitch_count"
    path.write_text(json.dumps(model))
    with pytest.raises(AppearanceDeclarationError):
        generate_appearance_bundle(tmp_path)


def test_early_end_unfielded_starter_is_not_in_complete_entry_set():
    """合成完全原本では実守備の後攻投手だけ1、未守備先攻投手は0。"""
    scopes = [_scope()]
    members = [_member(player="home-pitcher", kind="defensive-half-entry")]
    assert _evaluate(scopes, members, player="home-pitcher") == (
        "appearances",
        "available",
        1,
    )
    assert _evaluate(scopes, members, player="away-listed-starter") == (
        "appearances",
        "available",
        0,
    )
    assert _evaluate(
        [_scope(complete=False)], members, player="away-listed-starter"
    ) == ("appearances", "source_unavailable", None)


def test_edited_current_version_must_supply_members_of_same_new_version():
    """新終了版に旧出場版を混ぜると未供給、再束縛済み集合だけ同じ1件。"""
    scopes = [_scope(version="v2", revision=2, digest="s2")]
    assert _evaluate(scopes, [_member()]) == ("appearances", "source_unavailable", None)
    assert _evaluate(scopes, [_member(version="v2", revision=2, digest="s2")]) == (
        "appearances",
        "available",
        1,
    )


def test_equal_but_nonpositive_version_is_still_unavailable():
    """source/memberが同じ誤版でも正の版境界を満たさなければ拒否する。"""
    assert _evaluate([_scope(revision=0)], [_member(revision=0)]) == (
        "appearances",
        "source_unavailable",
        None,
    )


def test_missing_entire_scope_does_not_look_like_zero_season():
    """真正対象集合が1試合ならscope全欠落を空seasonの0へ変えない。"""
    assert _evaluate([], [], expected_games=1) == (
        "appearances",
        "source_unavailable",
        None,
    )
    assert _evaluate([], [], expected_games=0) == ("appearances", "available", 0)
