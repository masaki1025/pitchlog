"""writer前値のSQL/旧84body保持を純検査し、実PG成立とは分ける。"""

import copy

import pytest

from pitchlog.authz import stats_primitive_product as product
from pitchlog.authz import stats_primitive_write_state as state
from pitchlog.authz.stats_primitive_sql import candidate_function_bodies


def test_old_four_sql_and_84_bodies_remain_exact():
    """別非作者採用済みの固定全byte期待を再利用し、既資産を書換えない。"""
    from test_stats_primitive_product import (
        test_all_four_sql_and_84_bodies_preserve_adopted_whole_bytes,
    )

    before = product.candidate_declarations()
    old_sql = candidate_function_bodies()
    state.candidate_declarations()
    assert product.candidate_declarations() == before
    assert candidate_function_bodies() == old_sql
    test_all_four_sql_and_84_bodies_preserve_adopted_whole_bytes()


def test_full_source_guard_is_save_guard_without_the_not_yet_known_cas_values():
    """native印・binding・PlayRow・canonical_current全照合をそのまま参照する。"""
    source = candidate_function_bodies()["save_primitive_source"]
    old = source.split("\nBEGIN\n", 1)[1].split(
        "\n SELECT * INTO STRICT health FROM (", 1
    )[0]
    begin = old.index("\n OR p_expected_revision IS NULL")
    end = old.index("\n THEN RAISE EXCEPTION", begin)
    expected = old[:begin] + old[end:]
    raw = state.candidate_sql()
    assert raw.split("\nBEGIN\n", 1)[1].split("\n BEGIN\n", 1)[0] == expected
    assert "p_expected_revision" not in raw and "p_evaluation_json" not in raw
    for fragment in state._REQUIRED_GUARDS:
        assert fragment in raw


def test_only_true_absence_returns_zero_and_all_bad_series_raise():
    """終了/失効をWHEREで消さず、複数と過去行だけの状態も0へ補修しない。"""
    raw = state.candidate_sql()
    lookup, tail = raw.split("\n BEGIN\n", 1)[1].split(
        " EXCEPTION WHEN NO_DATA_FOUND THEN\n", 1
    )
    assert lookup == (
        "  SELECT v.* INTO STRICT series FROM sync_fence.stats_fact_versions v\n"
        "  WHERE v.tenant_id=tenant AND v.game_id=p_game_id\n"
        "  AND v.model_sha256=p_model_sha256 AND v.is_current FOR UPDATE;\n"
    )
    assert "WHEN OTHERS" not in raw and "WHEN TOO_MANY_ROWS" not in raw
    assert raw.count("RETURN QUERY SELECT 0::bigint,NULL::text;") == 1
    absence = tail.split("RETURN QUERY SELECT 0::bigint,NULL::text;")[0]
    assert "IF EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v" in absence
    assert "v.tenant_id=tenant AND v.game_id=p_game_id" in absence
    assert "AND v.model_sha256=p_model_sha256) THEN" in absence
    assert "RAISE EXCEPTION" in absence
    for fragment in (
        "series.invalidated_at IS NOT NULL",
        "series.completion_state IS DISTINCT FROM 'current_open'",
        "series.revision IS NULL OR series.revision<1",
        "series.source_set_sha256 IS NULL",
        "series.source_set_sha256 !~ '^[a-f0-9]{64}$'",
        "RETURN QUERY SELECT series.revision,series.source_set_sha256;",
    ):
        assert fragment in tail
    assert "INSERT INTO" not in raw
    assert "UPDATE sync_fence.stats_" not in raw and "DELETE FROM" not in raw


def test_declaration_operation_and_footer_are_finite():
    """既owner/保存capabilityだけを使い、表/role/余剰grantを増やさない。"""
    declarations, bodies = state.candidate_declarations()
    assert declarations == {
        "functions": [
            {
                "function_id": state.FUNCTION_ID,
                "schema_name": "stats_api",
                "function_name": "read_primitive_writer_state",
                "identity_args": "uuid, uuid, uuid, text, bytea",
                "function_kind": "definer",
                "owner_role_id": "pitchlog_sync_right_fn_owner",
                "language": "plpgsql",
                "returns": "TABLE(revision bigint,source_set_sha256 text)",
                "security_mode": "definer",
                "volatility": "volatile",
                "search_path": ["pg_catalog", "pg_temp"],
                "acl_expectations": [
                    {
                        "grantee": "pitchlog_app",
                        "privilege": "EXECUTE",
                        "grantable": False,
                    }
                ],
                "revoked_acl_expectations": [
                    {
                        "grantee": "PUBLIC",
                        "privilege": "EXECUTE",
                        "grantable": False,
                    }
                ],
            }
        ]
    }
    assert bodies == {"function|" + state.FUNCTION_ID: state.candidate_sql()}
    raw = bodies["function|" + state.FUNCTION_ID]
    assert state.function_application_body(state.FUNCTION_ID) == raw + (
        "\nALTER FUNCTION stats_api.read_primitive_writer_state"
        "(uuid, uuid, uuid, text, bytea) OWNER TO pitchlog_sync_right_fn_owner;\n"
        "REVOKE ALL ON FUNCTION stats_api.read_primitive_writer_state"
        "(uuid, uuid, uuid, text, bytea) FROM PUBLIC,pitchlog_app;\n"
        "GRANT EXECUTE ON FUNCTION stats_api.read_primitive_writer_state"
        "(uuid, uuid, uuid, text, bytea) TO pitchlog_app;\n"
    )
    assert state.function_application_body("unknown") is None
    operation = state.operation_candidate()
    assert operation["capability_id"] == "CAP:stats_primitives:save_source"
    assert operation["operation_id"] == "STATS_PRIMITIVES:read_writer_state"
    assert operation["parameters"] == [
        {"name": "p_attempt_id", "sql_type": "uuid"},
        {"name": "p_phase_id", "sql_type": "uuid"},
        {"name": "p_source_event_id", "sql_type": "uuid"},
        {"name": "p_model_sha256", "sql_type": "text"},
        {"name": "p_binding_nonce", "sql_type": "bytea"},
    ]
    assert operation["results"] == [
        {"name": "revision", "sql_type": "bigint", "nullable": False},
        {"name": "source_set_sha256", "sql_type": "text", "nullable": True},
    ]
    assert (operation["min_rows"], operation["max_rows"]) == (1, 1)
    assert "not value authority" in operation["qualification"]
    declarations["functions"][0]["owner_role_id"] = "pitchlog_app"
    assert state.candidate_declarations()[0]["functions"][0]["owner_role_id"] == (
        "pitchlog_sync_right_fn_owner"
    )


@pytest.mark.parametrize(
    "before,after",
    [
        ("octet_length(p_binding_nonce)<>32", "octet_length(p_binding_nonce)<>31"),
        ("b.state='open'", "b.state='closed'"),
        ("b.transaction_id=own_xid", "b.transaction_id IS NOT NULL"),
        ("s.state='consumed'", "s.state='ready'"),
        ("s.consumed_at IS NOT NULL", "true"),
        ("s.transaction_id=own_xid", "true"),
        ("current_source.slot_version IS DISTINCT FROM 1::bigint", "false"),
        ("INTO STRICT series", "INTO series"),
        ("AND v.is_current FOR UPDATE", "AND v.is_current"),
        ("WHEN NO_DATA_FOUND THEN", "WHEN OTHERS THEN"),
        (
            "IF EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v",
            "IF false THEN --",
        ),
        ("series.invalidated_at IS NOT NULL", "false"),
        ("series.completion_state IS DISTINCT FROM 'current_open'", "false"),
        ("series.revision IS NULL OR series.revision<1", "series.revision<0"),
        (
            "RETURN QUERY SELECT 0::bigint,NULL::text",
            "RETURN QUERY SELECT 0::bigint,''::text",
        ),
    ],
)
def test_scope_or_lifecycle_mutants_are_not_canonical(before, after):
    """構造変異の拒否であり、実DB故障系を実証したとは扱わない。"""
    raw = state.candidate_sql()
    assert before in raw
    with pytest.raises(ValueError, match="canonical"):
        state.validate_candidate_sql(raw.replace(before, after, 1))


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown-set",
        "marker",
        "cas",
        "nonce",
        "consumed",
        "model",
    ],
)
def test_unknown_upstream_guard_is_rejected(monkeypatch, mutation):
    """参照元の境界が不一致なら、別の曖昧な切出しを試さない。"""
    supplied = copy.deepcopy(candidate_function_bodies())
    if mutation == "unknown-set":
        supplied["unknown"] = "unknown"
    else:
        before, after = {
            "marker": ("SELECT * INTO STRICT health FROM (", "SELECT health FROM ("),
            "cas": ("p_expected_revision IS NULL", "p_expected_revision<0"),
            "nonce": ("octet_length(p_binding_nonce)<>32", "true"),
            "consumed": ("s.state='consumed'", "s.state='ready'"),
            "model": ("OR p_model_sha256 IS DISTINCT FROM '", "OR p_model_sha256 = '"),
        }[mutation]
        assert before in supplied["save_primitive_source"]
        supplied["save_primitive_source"] = supplied["save_primitive_source"].replace(
            before, after
        )
    monkeypatch.setattr(state, "candidate_function_bodies", lambda: supplied)
    with pytest.raises(ValueError):
        state.candidate_sql()
