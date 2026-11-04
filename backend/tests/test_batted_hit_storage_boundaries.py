"""新安打の既署名SQLだけを変え、他の保存権限・旧v2本文を維持する。"""

import hashlib

from pitchlog.authz.first_ball_product import _function_argument_names
from pitchlog.authz.terminal_pitch_write_stamp import (
    _v2_function_bodies,
    candidate_function_bodies,
)

# f93c46c1の採用済み既関数から先置き。候補SQLから期待を再生成しない。
UNCHANGED = {
    "read_play_prefix_checkpoint": (
        "22e4cb446bbbce7a8f15133874f79ad6aa462c1bf21f113fd9a1f4dbc1a25be3"
    ),
    "lock_play_prefix_checkpoint": (
        "d9291635f8ad6db4707c01a2f8ccf86bf3d84a78403cbbc0502287a87c3153c1"
    ),
    "read_play_prefix_history_page": (
        "2346ea918bfa470ae69add54c31572667451814498383164ecb5870e59f30f5e"
    ),
    "assert_play_prefix_projection": (
        "3b0058ead18e47a00d51365dcd578435f08b6f35e902c31e8dc59c14d0d22c8a"
    ),
    "finish_play_prefix_projection": (
        "4665b56bb8d7ac806bd6480b77171dd4b27995c6a8679c260dc53914ed7407f6"
    ),
    "guard_play_prefix_runner_insert": (
        "3489089a548fecef4a062abc1f8e1f9bd5feefda78e4ea2ec0be0a0b749113e6"
    ),
    "read_lineup_started_origin": (
        "730d153b7c27c6f5f42112a3790cc1ca30fe549b4602ed108c83e5ba77e1b6b4"
    ),
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
        == "6a51bc53df61ecd37262d8fa3b05c4f702f4861f419376d752062de170bce6b6"
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
