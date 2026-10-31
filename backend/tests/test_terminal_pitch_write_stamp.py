"""v2実SQLの原子的な親AFTERとrunner入場条件を検査する。"""

from pitchlog.authz.first_ball_write_stamp import formal_profile
from pitchlog.authz.terminal_pitch_write_stamp import candidate_function_bodies


def test_parent_after_closes_runner_checkpoint_history_and_consumption():
    """全10列INSERTを履歴/消費より先に同親statement内で行う。"""
    bodies = candidate_function_bodies()
    sql = " ".join(bodies["finish_play_prefix_projection"].split())
    assert "RETURNS trigger" in sql
    assert "TG_WHEN<>'AFTER'" in sql
    assert sql.index("INSERT INTO public.play_runners") < sql.index(
        "INSERT INTO sync_fence.ordinary_pitch_checkpoints"
    )
    assert "actual_runners IS DISTINCT FROM" in sql
    assert "RETURN NEW;" in sql
    assert "state='consumed'" in sql
    for name in (
        "prepare_play_prefix_projection",
        "assert_play_prefix_projection",
        "finish_play_prefix_projection",
    ):
        assert "pg_current_xact_id()" in bodies[name]
        assert "xmin::text::numeric" in bodies[name]
    runner = bodies["guard_play_prefix_runner_insert"]
    assert "pg_trigger_depth()<>2" in runner
    assert "pg_catalog.to_jsonb(NEW)" in runner
    assert "a.next_checkpoint_content->>'version' IS DISTINCT FROM '2'" in runner


def test_before_v2_assert_never_consumes_old_stamp():
    """新分岐はassertだけ、旧分岐は旧consumeを保持する。"""
    sql = next(
        r["sql"]
        for r in formal_profile()["functions"]
        if r["function_name"] == "guard_first_ball_projection_admission"
    )
    branch = sql.split(
        "IF event_row.payload->>'formatVersion'='play-prefix-play-v2' THEN"
    )[1].split("END IF;")[0]
    assert "assert_play_prefix_projection" in branch
    assert "RETURN NEW;" in branch
    assert "consume_ordinary_projection" not in branch
    assert "PERFORM sync_right_api.consume_ordinary_projection" in sql


def test_physical_runner_uses_before_slots_and_actual_hold_not_after_occupancy():
    """空BB/HBPをphysical1へ誤写像した旧候補を拒否する比較面を固定する。"""
    sql = candidate_function_bodies()["prepare_play_prefix_projection"]
    assert "pg_catalog.jsonb_array_length(after_cp->'runners')" not in sql
    assert "request'->'source'->'runners')" in sql
    assert "runnerDefaultAdvance'->(CASE m->>'base'" in sql
    assert "r->>'status'='継続'" in sql


def test_prepare_parenthesizes_five_case_expressions_without_other_sql_changes():
    """実PGの42601を閉じ、追加括弧以外の全byte/述語/拒否を固定する。"""
    import hashlib
    import re

    sql = candidate_function_bodies()["prepare_play_prefix_projection"]
    removed = []

    def original_case(match):
        # 既採用のrunner field選択 ->(CASE...) はそのまま保持する。
        if sql[max(0, match.start() - 2) : match.start()] == "->":
            return match.group()
        removed.append(match.group())
        return match.group()[1:-1]

    previous = re.sub(r"\(CASE\b[\s\S]*?\bEND\)", original_case, sql)
    assert len(removed) == 5
    assert not re.search(r"IS DISTINCT FROM\s+CASE\b|>\s*CASE\b", sql)
    assert (
        hashlib.sha256(previous.encode()).hexdigest()
        == "18fb89b0d4065b536a726bc5f17ccfcb5b3577825a42990387e08e07c891712d"
    )
