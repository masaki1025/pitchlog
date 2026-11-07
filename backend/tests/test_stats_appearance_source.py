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
            "revision,source_set_sha256,supply_complete,member_count,"
            "checkpoint_id,checkpoint_generation,checkpoint_revision,checkpoint_digest,"
            "d3,lifecycle_receipt_id,entry_set_sha256)"
        )
        db.execute(
            "CREATE TABLE appearance_members (tenant_id,game_id,fact_version_id,"
            "revision,source_set_sha256,player_id,proof_kind,proof_source_id,"
            "checkpoint_id,checkpoint_generation,checkpoint_revision,checkpoint_digest,"
            "d3,lifecycle_receipt_id,entry_set_sha256)"
        )
        db.executemany(
            "INSERT INTO appearance_scope VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", scopes
        )
        db.executemany(
            "INSERT INTO appearance_members VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            members,
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


def _scope(
    game="g1",
    *,
    version="v1",
    revision=1,
    digest="s1",
    count=1,
    complete=True,
    context=None,
):
    return (
        "t1",
        game,
        version,
        revision,
        digest,
        complete,
        count,
        *(context or ("cp1", 1, 1, "cp-digest1", 0, None, "entry-set1")),
    )


def _member(
    game="g1",
    *,
    player="p1",
    proof="proof1",
    kind="pitcher-defensive-entry",
    version="v1",
    revision=1,
    digest="s1",
    context=None,
):
    return (
        "t1",
        game,
        version,
        revision,
        digest,
        player,
        kind,
        proof,
        *(context or ("cp1", 1, 1, "cp-digest1", 0, None, "entry-set1")),
    )


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


@pytest.mark.parametrize("index", range(7))
def test_same_native_version_does_not_authorize_old_checkpoint_or_entry_set(index):
    """0球交代でnative版が同じでもCP/水位/終了receipt/集合の旧資格を拒否。"""
    context = ["cp1", 1, 1, "cp-digest1", 0, None, "entry-set1"]
    context[index] = 2 if index in {1, 2, 4} else "changed"
    assert _evaluate([_scope()], [_member(context=context)]) == (
        "appearances",
        "source_unavailable",
        None,
    )


def test_current_nullable_receipt_and_confirmed_receipt_are_distinct():
    """未終了receiptのNULLは正当、終了後の別receiptに持ち越さない。"""
    current = ["cp1", 1, 1, "cp-digest1", 0, None, "entry-set1"]
    ended = [*current[:5], "receipt-v1", current[6]]
    assert _evaluate([_scope(context=current)], [_member(context=current)])[1:] == (
        "available",
        1,
    )
    assert _evaluate([_scope(context=ended)], [_member(context=ended)])[1:] == (
        "available",
        1,
    )
    assert _evaluate([_scope(context=ended)], [_member(context=current)])[1:] == (
        "source_unavailable",
        None,
    )


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


def _entry_projection(**changes):
    """既kernel結果の合成値を単一SQLへ渡す。真正writer資格とは別の試験。"""
    values = dict(
        tenant_id="tenant",
        game_id="game",
        source_id="start-attempt",
        origin_kind="start",
        internal_generation=1,
        d1=None,
        before_inning=None,
        before_half=None,
        after_inning=1,
        after_half="top",
        after_home_pitcher_id="home-starter",
        after_away_pitcher_id="away-starter",
        before_home_pitcher_id=None,
        before_away_pitcher_id=None,
        changed_side=None,
        half_completed=None,
        end_condition_detected=None,
        lock_further_play=None,
        outcome=None,
        x_mark=None,
        released_end_condition=None,
        half_started_before=None,
        artifact_sha256="a" * 64,
        source_fingerprint="b" * 64,
    )
    values.update(changes)
    bundle, _ = generate_appearance_bundle()
    query = bundle["backend/src/pitchlog/stats/generated/pitcher_entry_projection.sql"]
    with sqlite3.connect(":memory:") as db:
        names = ",".join(values)
        binds = ",".join("?" for _ in values)
        return db.execute(
            f"WITH appearance_transition({names}) AS (VALUES ({binds})) "
            f"SELECT * FROM ({query}) projected",
            tuple(values.values()),
        ).fetchone()


def _play_transition(**changes):
    """第3out後のT1/T2既結果を固定する。期待をkernelで作り直さない。"""
    values = dict(
        origin_kind="play",
        source_id="accepted-play",
        d1=3,
        before_inning=1,
        before_half="top",
        after_inning=1,
        after_half="bottom",
        half_completed=True,
        end_condition_detected=False,
        lock_further_play=False,
        outcome="no-end",
        x_mark="recorded-score",
    )
    values.update(changes)
    return _entry_projection(**values)


def test_start_enters_only_home_pitcher_before_any_pitch():
    """開始TXの0球時点で後攻投手のみ。未守備先攻は生成しない。"""
    row = _entry_projection()
    assert row[0] == "evaluated"
    assert row[6] is None
    assert row[7:12] == ("home-starter", "home", 1, "top", "defensive-half-entry")


def test_ordinary_half_transition_enters_next_defender():
    """第三out後に既T2が継続を確定した半回だけを写す。"""
    row = _play_transition()
    assert row[0] == "evaluated"
    assert row[7:12] == ("away-starter", "away", 1, "bottom", "defensive-half-entry")


@pytest.mark.parametrize("outcome", ["normal-end", "cold-end", "limit-draw"])
def test_terminal_top_completion_does_not_enter_unstarted_bottom(outcome):
    """表完了でも裏未開始なら先攻投手の出場を推測しない。"""
    row = _play_transition(
        end_condition_detected=True,
        lock_further_play=True,
        outcome=outcome,
        x_mark="x-mark",
    )
    assert row[0] == "evaluated" and row[7:12] == (None,) * 5


def test_pitch_without_half_transition_does_not_create_another_entry():
    """同じ半回の通常1球は既出場を増やさない。"""
    row = _play_transition(before_half="top", after_half="top", half_completed=False)
    assert row[0] == "evaluated" and row[7:12] == (None,) * 5


@pytest.mark.parametrize("side,expected", [("home", "relief"), ("away", None)])
def test_zero_pitch_substitution_counts_only_current_defending_side(side, expected):
    """守備中の0球交代は出場、攻撃中の投手割当変更はまだ出場しない。"""
    row = _entry_projection(
        origin_kind="substitution",
        source_id="sub",
        d1=2,
        before_inning=1,
        before_half="top",
        changed_side=side,
        before_home_pitcher_id="home-starter",
        after_home_pitcher_id="relief",
    )
    assert row[0] == "evaluated" and row[7] == expected
    if expected is not None:
        assert row[11] == "pitcher-defensive-entry"


def test_pending_offensive_pitcher_changes_take_effect_only_when_defense_starts():
    """攻撃中A→B→Cを数えず、次守備半回の有効Cを保存する。"""
    row = _play_transition(after_away_pitcher_id="final-C")
    assert row[0] == "evaluated" and row[7] == "final-C"


@pytest.mark.parametrize("started,expected", [(False, "away-starter"), (True, None)])
def test_reopen_enters_only_previously_unstarted_released_half(started, expected):
    """未開始半回を開く再開のみ出場。既半回の再開で増やさない。"""
    row = _play_transition(
        origin_kind="reopen", released_end_condition=True, half_started_before=started
    )
    assert row[0] == "evaluated" and row[7] == expected


@pytest.mark.parametrize(
    "fault",
    [
        {"origin_kind": "unknown"},
        {"d1": 1},
        {"after_half": "bottom"},
        {"after_home_pitcher_id": None},
        {"internal_generation": 0},
    ],
)
def test_invalid_start_entry_is_unavailable(fault):
    """架空D1や未知origin/初期half/投手不足を成功へ補完しない。"""
    assert _entry_projection(**fault)[0] == "source_unavailable"


def _decoded_row(**changes):
    """正準DB scalarから構成した固定期待。資格ではない。"""
    from uuid import UUID

    values = dict(
        state="evaluated",
        tenant_id=UUID(int=1),
        game_id=UUID(int=2),
        origin_kind="start",
        source_id=UUID(int=3),
        generation=1,
        d1=None,
        player_id=UUID(int=4),
        side="home",
        inning=1,
        half="top",
        kind="defensive-half-entry",
        artifact="a" * 64,
        fingerprint="b" * 64,
    )
    values.update(changes)
    return (tuple(values.values()),)


def test_projection_codec_does_not_turn_values_into_writer_authority():
    """全値codecは型付き値だけを返し、開始D1を作らない。"""
    from pitchlog.stats.pitcher_appearance_source import decode_projected_entry

    entry = decode_projected_entry(_decoded_row())
    assert entry is not None and entry.d1 is None and entry.defending_side == "home"
    assert not hasattr(entry, "writer") and not hasattr(entry, "nonce")


@pytest.mark.parametrize(
    "change",
    [
        {"generation": True},
        {"d1": 0},
        {"tenant_id": "1"},
        {"side": "away"},
        {"player_id": None},
        {"origin_kind": "unknown"},
        {"artifact": "A" * 64},
        {"half": "bottom"},
        {"kind": "pitcher-defensive-entry"},
    ],
)
def test_projection_codec_refuses_noncanonical_or_inconsistent_values(change):
    """型違い/部分NULL/偽開始positionを補完しない。"""
    from pitchlog.stats.pitcher_appearance_source import (
        PitcherAppearanceSourceUnavailable,
        decode_projected_entry,
    )

    with pytest.raises(PitcherAppearanceSourceUnavailable):
        decode_projected_entry(_decoded_row(**change))


def test_candidate_models_keep_raw_proof_immutable_without_native_only_header():
    """0球交代ではnative版不変のため原本1表だけと実効contextを保持する。"""
    from sqlalchemy.dialects.postgresql import dialect
    from sqlalchemy.schema import CreateTable

    from pitchlog.db import all_models
    from pitchlog.db.game_state import pitcher_appearance_models as models

    assert all_models.IMPORTED_MODEL_MODULE_NAMES
    table = models.PitcherEntrySource.__table__
    ddl = str(CreateTable(table).compile(dialect=dialect()))
    assert table.info["append_only"] is True
    assert "ON DELETE NO ACTION" in ddl
    assert not {"deleted_at", "updated_at", "created_at"}.intersection(table.c.keys())
    assert "d1 IS NOT NULL AND slot_version IS NOT NULL" in ddl
    assert "d1 IS NULL AND slot_version IS NULL" in ddl
    assert "fk_pitcher_entry_generation" in ddl
    assert "context_sha256" in ddl
    assert not hasattr(models, "PitcherEntryVersion")
    assert not hasattr(models, "PitcherEntryMember")


def test_start_entry_save_candidate_rechecks_actual_db_source_and_actor():
    """callerの成功bool/自由選手を受けず同TX実原本へ束縛する候補。"""
    from pitchlog.repositories.stats_appearance import candidate_start_entry_function

    body = candidate_start_entry_function()
    header = body.split("RETURNS TABLE", 1)[0]
    assert "p_tenant_id uuid,p_attempt_id uuid,p_generation bigint" in header
    assert "p_player" not in header and "p_success" not in body
    assert "session_user IS DISTINCT FROM 'pitchlog_initial_actor'" in body
    assert "current_user IS DISTINCT FROM 'pitchlog_initial_fn_owner'" in body
    assert "p_tenant_id IS DISTINCT FROM v_tenant" in body
    assert "a.outcome='committed'" in body
    assert "xmin" not in body  # 私有parentのROW_COUNT確認後だけが呼出点。
    assert "ON CONFLICT (tenant_id,game_id,proof_sha256) DO NOTHING" in body
    assert "pg_catalog.to_jsonb(e)-'proof_sha256'=v_proof" in body
    assert "DO UPDATE" not in body and "DELETE FROM" not in body
    target = generate_appearance_bundle()[0][
        "backend/src/pitchlog/stats/generated/pitcher_entry_projection.sql"
    ]
    assert body.count(target) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"outcome": "invented"},
        {"x_mark": "blank"},
        {"end_condition_detected": True, "lock_further_play": False},
        {"half_completed": False, "before_half": "bottom", "before_inning": 2},
    ],
)
def test_inconsistent_kernel_output_is_unavailable_without_reevaluating_rules(change):
    """既出力の型/一致だけを拒否し、終了条件やスコアを再計算しない。"""
    assert _play_transition(**change)[0] == "source_unavailable"


def test_entry_helper_is_owner_only_without_new_public_token_or_capability():
    """既保存関数の内部callだけへ閉じ、外部の自由tokenを増やさない。"""
    import pitchlog.repositories.stats_appearance as module

    declarations, bodies = module.candidate_private_entry_declarations()
    assert len(declarations["functions"]) == 3 and len(bodies) == 5
    entry = declarations["functions"][0]
    assert entry["owner_role_id"] == "pitchlog_initial_fn_owner"
    assert entry["acl_expectations"] == []
    assert {x["grantee"] for x in entry["revoked_acl_expectations"]} == {
        "PUBLIC",
        "pitchlog_app",
        "pitchlog_initial_actor",
        "pitchlog_sync_binding_actor",
        "pitchlog_sync_right_fn_owner",
    }
    assert not hasattr(module, "PersistStartPitcherEntryToken")
    assert not hasattr(module, "ReadPitcherEntryPageToken")
    install = module.candidate_private_entry_install_sql()
    assert "GRANT EXECUTE" not in install and "REVOKE ALL ON FUNCTION" in install


def test_start_helper_reads_only_previously_granted_columns():
    """system列/INSERT専用水位のために広いSELECT権限を要求しない。"""
    import re

    from pitchlog.repositories.stats_appearance import candidate_start_entry_function

    root = Path(__file__).resolve().parents[2]
    catalog = json.loads(
        (root / "contracts/authz/product/ddl-elements.json").read_text()
    )
    tables = {
        "a": "game_start_attempts",
        "r": "game_start_requests",
        "g": "games",
        "rg": "recording_generations",
        "l": "game_lineups",
    }
    body = candidate_start_entry_function()
    for alias, table in tables.items():
        allowed = {
            row["column_id"]
            for row in catalog["column_acl_expectations"]
            if row["object_id"] == table
            and row["grantee_role_id"] == "pitchlog_initial_fn_owner"
            and "SELECT" in row["privilege_ids"]
        }
        actual = set(re.findall(r"\b" + alias + r"\.([a-z_]+)", body))
        assert actual <= allowed, (table, actual - allowed)


def test_immutable_entry_guards_are_actual_db_triggers_not_model_labels():
    """新原表にも強制RLSと両immutable triggerを候補SQLとして供給する。"""
    from pitchlog.repositories.stats_appearance import (
        candidate_entry_table_install_sql,
        candidate_private_entry_install_sql,
    )

    table = candidate_entry_table_install_sql()
    assert "FORCE ROW LEVEL SECURITY" in table
    assert "TO pitchlog_initial_fn_owner,pitchlog_sync_right_fn_owner" in table
    assert "GRANT SELECT,INSERT" in table
    body = candidate_private_entry_install_sql()
    assert "BEFORE UPDATE OR DELETE" in body
    assert "BEFORE TRUNCATE" in body
    assert "immutable boundary rejected" in body
    assert "GRANT EXECUTE" not in body


def test_writer_entry_uses_physical_xmin_not_composite_row_header():
    """ROWTYPEに存在しないsystem列/合成rowの擬似xminで同TXを認めない。"""
    from pitchlog.repositories.stats_appearance import candidate_writer_entry_function

    body = candidate_writer_entry_function()
    assert "v_event.xmin" not in body
    assert "SELECT e.xmin INTO STRICT v_event_xmin FROM public.operation_events" in body
    assert "s.xmin=v_event_xmin AND v.xmin=v_event_xmin" in body
    assert "sr.xmin=v_event_xmin AND n.xmin=v_event_xmin" in body
    assert "c.state='current' AND c.xmin=v_event_xmin" in body


def test_writer_xmin_acl_is_exactly_two_readonly_columns_not_table_select():
    """既native原表のsystem列2つだけをofficial列ACL builderで供給する。"""
    from pitchlog.repositories.stats_appearance import (
        candidate_entry_table_install_sql,
        candidate_private_entry_declarations,
        candidate_private_entry_install_sql,
    )

    declarations, _ = candidate_private_entry_declarations()
    rows = declarations["column_acl_expectations"]
    assert len(rows) == 2
    assert {r["object_id"] for r in rows} == {
        "stats_primitive_sources",
        "stats_fact_versions",
    }
    for row in rows:
        assert row["column_id"] == "xmin" and row["privilege_ids"] == ["SELECT"]
        assert row["grantee_role_id"] == "pitchlog_sync_right_fn_owner"
        assert row["grant_option"] is False
    sql = candidate_private_entry_install_sql()
    assert sql.count("GRANT SELECT (xmin)") == 2
    assert "GRANT SELECT ON sync_fence.stats_primitive_sources" not in sql
    assert "GRANT SELECT ON sync_fence.stats_fact_versions" not in sql
    assert "OWNER TO pitchlog_owner" in candidate_entry_table_install_sql()


def test_writer_saved_source_does_not_reenter_prior_state_or_undo_only_columns():
    """実Save/0044の保存済原本だけを使用し旧profile/未保持列を前提化しない。"""
    from pitchlog.repositories.stats_appearance import candidate_writer_entry_function

    sql = candidate_writer_entry_function()
    assert "read_primitive_writer_state" not in sql
    assert "n.source_event_id=v_event.id" not in sql
    assert "SELECT n.artifact_sha256" not in sql
    assert "sr.source_event_id=v_event.id AND sr.source_d1=v_event.d1" in sql
    assert "v_artifact:=v_cp.content#>>'{content,executionArtifactSha256}'" in sql
    assert "n.nonce_digest=pg_catalog.sha256(p_binding_nonce)" in sql
    assert "n.transaction_id=v_xid" in sql
    assert "s.d2=v_event.d2 AND s.wire_d4=v_binding.wire_d4" in sql
    assert "v.is_current AND v.invalidated_at IS NULL" in sql
    assert "s.xmin=v_event_xmin AND v.xmin=v_event_xmin" in sql


def test_context_reader_reuses_both_full_authority_guards_in_same_rr():
    """既CP検査を同RRへ転用しても原本/物理印/越境拒否を落とさない。"""
    from pitchlog.authz.nonplay_prefix_read_sql import (
        _legacy_read_sql,
        candidate_read_function_bodies,
    )
    from pitchlog.repositories.stats_appearance import (
        _candidate_context_guards,
        candidate_appearance_context_function,
    )

    legacy, normal = _candidate_context_guards()
    original = candidate_read_function_bodies()["read_nonplay_active_history"]
    marker = " SELECT c.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints c"
    original_normal = original[original.rindex(marker) :].split(" WITH active AS (", 1)[
        0
    ]
    rejected = (
        "RAISE EXCEPTION 'pitcher appearance context rejected' USING ERRCODE='42501';"
    )
    original_legacy = _legacy_read_sql("D03_ACTIVE_QUERY_NOT_EXECUTED", rejected)
    original_legacy = original_legacy[original_legacy.index(marker) :].split(
        " WITH active AS (", 1
    )[0]
    assert legacy == original_legacy.replace(" FOR SHARE OF c;", ";")
    assert normal == original_normal.replace(" FOR SHARE OF c;", ";")
    body = candidate_appearance_context_function()
    assert legacy in body and normal in body
    assert "LANGUAGE plpgsql STABLE SECURITY DEFINER" in body
    assert "'transaction_isolation')\n IS DISTINCT FROM 'repeatable read'" in body
    assert "'transaction_read_only') IS DISTINCT FROM 'on'" in body
    assert "session_user IS DISTINCT FROM 'pitchlog_app'" in body
    assert "p_tenant_id IS DISTINCT FROM NULLIF(" in body
    assert "FOR SHARE" not in body and "FOR UPDATE" not in body
    assert "GRANT EXECUTE" not in body
    assert "'checkpoint_digest',cp.content_digest" in body
    assert "'d3',cp.confirmed_watermark" in body


def test_real_source_provider_closes_unsupported_history_and_keeps_unique_count():
    """原本供給は独自replay/別COUNTを作らず、未知/P3/取消を未供給へ保つ。"""
    from pitchlog.repositories.stats_appearance import (
        candidate_appearance_read_install_sql,
        candidate_appearance_source_query,
    )
    from pitchlog.stats.basic_sql import appearance_query

    source = candidate_appearance_source_query()
    assert "JOIN canonical_s c" in source
    assert "c.source_state='included'" in source
    assert "appearance_projected AS MATERIALIZED" in source
    assert "source_state='source_unavailable'" in source
    assert (
        "e.event_kind NOT IN\n "
        "('play_input','substitution','game_end_declaration','game_reopen')" in source
    )
    assert "v.completion_receipt_id::text" in source
    assert "e.context_sha256=pg_catalog.encode(pg_catalog.sha256" in source
    assert "(pg_catalog.to_jsonb(e)-'proof_sha256')::text" in source
    assert "h.canonical_source_set_sha256=v.source_set_sha256" in source
    assert "COUNT(DISTINCT m.game_id)" not in source
    count = appearance_query()
    assert count.count("COUNT(DISTINCT m.game_id)") == 1
    assert "SELECT DISTINCT game_id FROM version_scope" in count
    assert "read_pitcher_appearance_source($1,g.game_id,$9)" in count
    assert "appearance_packets AS MATERIALIZED" in count
    assert "current_roster" not in source and "game_lineups" not in source
    install = candidate_appearance_read_install_sql()
    assert "GRANT EXECUTE" not in install
    assert install.count("OWNER TO pitchlog_sync_right_fn_owner") == 2


def test_normal_reopen_keeps_actual_boolean_without_assuming_end_mutated_state():
    """終了宣言はcurrentを変えず、再開だけgameEndedをfalseへする。"""
    from pitchlog.repositories.stats_appearance import candidate_appearance_source_query

    source = candidate_appearance_source_query()
    assert (
        "pg_catalog.jsonb_typeof(a.preparation#>'{before_source,checkpoint,"
        "\n content,restored,current,stateFields,state.gameEnded}')='boolean'"
    ) in source
    assert "stateFields,state.gameEnded}'='true'::jsonb" not in source
    assert "stateFields,state.gameEnded}'='false'::jsonb" in source
    assert source.count("#- '{current,stateFields,state.gameEnded}'") == 2
    assert "decision,lockFurtherPlayInput}'='false'::jsonb" in source
