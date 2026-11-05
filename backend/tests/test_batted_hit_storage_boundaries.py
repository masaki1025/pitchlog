"""新安打の既署名SQLだけを変え、他の保存権限・旧v2本文を維持する。"""

import hashlib

from first_ball_expected_source_pins import read_expected_source_pins

from pitchlog.authz.first_ball_product import _function_argument_names
from pitchlog.authz.terminal_pitch_write_stamp import (
    _v2_function_bodies,
    candidate_function_bodies,
)

_EXPECTED_BATTED_PINS = read_expected_source_pins(
    "test_batted_hit_storage_boundaries.py"
)


# f93c46c1の採用済み既関数から先置き。候補SQLから期待を再生成しない。
UNCHANGED = {
    "read_play_prefix_checkpoint": (
        _EXPECTED_BATTED_PINS["read_play_prefix_checkpoint"]
    ),
    "lock_play_prefix_checkpoint": (
        _EXPECTED_BATTED_PINS["lock_play_prefix_checkpoint"]
    ),
    "read_play_prefix_history_page": (
        _EXPECTED_BATTED_PINS["read_play_prefix_history_page"]
    ),
    "assert_play_prefix_projection": (
        _EXPECTED_BATTED_PINS["assert_play_prefix_projection"]
    ),
    "finish_play_prefix_projection": (
        _EXPECTED_BATTED_PINS["finish_play_prefix_projection"]
    ),
    "guard_play_prefix_runner_insert": (
        _EXPECTED_BATTED_PINS["guard_play_prefix_runner_insert"]
    ),
    "read_lineup_started_origin": (_EXPECTED_BATTED_PINS["read_lineup_started_origin"]),
}


def test_existing_seven_functions_and_old_v2_branch_remain_byte_identical():
    """prepare以外7関数の全byteとoldv2の全BODYを比較する。"""
    bodies = candidate_function_bodies()
    assert set(bodies) == set(UNCHANGED) | {"prepare_play_prefix_projection"}
    for name, expected in UNCHANGED.items():
        assert hashlib.sha256(bodies[name].encode()).hexdigest() == expected
    old = _v2_function_bodies()["prepare_play_prefix_projection"]
    assert (
        hashlib.sha256(old.encode()).hexdigest()
        == _EXPECTED_BATTED_PINS["old_v2_prepare_body_sha256"]
    )
    body = "DECLARE" + old.split("DECLARE", 1)[1].rsplit("$ordinary$;", 1)[0]
    assert body in bodies["prepare_play_prefix_projection"]


def test_closed_signature_and_existing_installer_parser_are_preserved():
    """CAPやoperationを増やさず既7引数/1結果を保つ。"""
    bodies = candidate_function_bodies()
    for sql in bodies.values():
        _function_argument_names(sql)
    assert _function_argument_names(bodies["prepare_play_prefix_projection"]) == (
        (
            "p_tenant_id",
            "p_attempt_id",
            "p_phase_id",
            "p_binding_nonce",
            "p_device_id",
            "p_game_id",
            "p_preparation_json",
            "prepared",
        ),
        True,
    )


def test_new_guard_follows_actual_writer_event_and_keeps_atomic_before_runners():
    """新観測guardを既sameTX印より前の自己申告入口へ移さない。"""
    sql = candidate_function_bodies()["prepare_play_prefix_projection"]
    start = sql.index("batted_obs:=source_row.payload")
    assert sql.index("own_xid:=pg_catalog.pg_current_xact_id()") < start
    assert sql.index("s.state='right_verified'") < start
    assert sql.index("JOIN sync_fence.writer_bindings") < start
    assert sql.index("source_row.id::text") < start
    assert "request'->'source'->'runners')" in sql
    assert "runnerDefaultAdvance'->(CASE m->>'base'" in sql
    assert "batted hit physical source rejected" in sql
    assert "state='consumed'" not in sql
    assert "GRANT" not in sql and "BYPASSRLS" not in sql
