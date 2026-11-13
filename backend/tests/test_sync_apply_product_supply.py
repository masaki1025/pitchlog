"""初球製品供給のexact差分・旧投影・DDL非実行を確認する。"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest
from first_ball_expected_source_pins import (
    read_ci_followup_inputs,
    read_expected_source_pins,
)

from pitchlog.authz import product_catalog as cat
from pitchlog.authz import product_provisioning as prov
from pitchlog.authz.asset_spec import PRODUCT_SPEC, load_product_application_steps
from pitchlog.authz.first_ball_product import ADDITIONS, IDS, legacy_asset, validate

# 終端prefixの正式7関数・2policy・runner有限10列（旧集合は維持）。
_TERMINAL_FUNCTION_IDS = frozenset(
    {
        "FUNCTION:sync_right_api:assert_play_prefix_projection(jsonb)",
        "FUNCTION:sync_right_api:finish_play_prefix_projection()",
        "FUNCTION:sync_right_api:guard_play_prefix_runner_insert()",
        (
            "FUNCTION:sync_right_api:lock_play_prefix_checkpoint(uuid, uuid, "
            "uuid, bytea, uuid, uuid, bigint)"
        ),
        (
            "FUNCTION:sync_right_api:prepare_play_prefix_projection(uuid, "
            "uuid, uuid, bytea, uuid, uuid, text)"
        ),
        "FUNCTION:sync_right_api:read_play_prefix_checkpoint(uuid, uuid, bigint)",
        (
            "FUNCTION:sync_right_api:read_play_prefix_history_page(uuid, "
            "uuid, bigint, bigint, uuid, bigint, bigint, bigint, bigint, "
            "bigint, uuid, integer)"
        ),
    }
)
_TERMINAL_POLICY_IDS = frozenset(
    {
        "POLICY:play_runners:play_prefix_insert_play_runners",
        "POLICY:play_runners:play_prefix_select_play_runners",
    }
)
_TERMINAL_COLUMN_ACL_IDS = frozenset(
    f"COLUMN-ACL:public:play_runners:{column}:pitchlog_sync_right_fn_owner"
    for column in (
        "tenant_id",
        "id",
        "play_id",
        "base",
        "runner_id",
        "status",
        "status_source",
        "responsible_pitcher_id",
        "import_batch_id",
        "retired_at",
    )
)


_LINEUP_FUNCTION_IDS = frozenset(
    {
        "FUNCTION:sync_right_api:read_lineup_started_origin(uuid, uuid, bigint)",
    }
)
_LINEUP_POLICY_IDS = frozenset(
    {
        "POLICY:game_start_attempts:lineup_prefix_game_start_attempts_select",
        "POLICY:game_start_requests:lineup_prefix_game_start_requests_select",
    }
)
_LINEUP_COLUMN_ACL_IDS = frozenset(
    f"COLUMN-ACL:public:{table}:{column}:pitchlog_sync_right_fn_owner"
    for table, columns in (
        (
            "game_start_attempts",
            ("tenant_id", "game_id", "device_id", "start_request_id", "outcome"),
        ),
        (
            "game_start_requests",
            ("tenant_id", "game_id", "device_id", "start_request_id"),
        ),
    )
    for column in columns
)


_EXPECTED_SOURCE_PINS = read_expected_source_pins("test_sync_apply_product_supply.py")

ROOT = Path(__file__).resolve().parents[2]


def asset():
    """検証用の実資産を読み、予期しない処理を閉じる。"""
    return json.loads((ROOT / "contracts/authz/product/ddl-elements.json").read_bytes())


ROWS = [(s, i) for s, rows in ADDITIONS.items() for i in range(len(rows))]


@pytest.mark.parametrize("section,index", ROWS)
@pytest.mark.parametrize("fault", ["missing", "mutated", "duplicate"])
def test_extension_rejects_every_missing_mutated_or_duplicate_row(
    section, index, fault
):
    """実認可資産の閉集合と失敗条件を検査する。"""
    value = asset()
    target = ADDITIONS[section][index]
    key = IDS[section]
    at = next(i for i, r in enumerate(value[section]) if r[key] == target[key])
    if fault == "missing":
        value[section].pop(at)
    elif fault == "duplicate":
        value[section].append(copy.deepcopy(value[section][at]))
    else:
        value[section][at]["unexpected"] = True
    with pytest.raises(ValueError):
        validate(value)


def test_legacy_projection_preserves_semantics_and_input():
    """実認可資産の閉集合と失敗条件を検査する。"""
    value = asset()
    assert validate(value)
    legacy = legacy_asset(value)
    assert not validate(legacy)
    assert legacy_asset(legacy) == legacy
    assert not any(r.get("schema_name") == "sync_fence" for r in legacy["tables"])
    assert value == asset()


@pytest.mark.parametrize(
    "fault", ["connect", "usage", "namespace", "invoker", "unknown-invoker", "bool-int"]
)
def test_profile_rejects_partial_privileges_namespace_and_mode(fault):
    """実認可資産の閉集合と失敗条件を検査する。"""
    value = asset()
    if fault == "connect":
        value["databases"][0]["acl_expectations"] = [
            r
            for r in value["databases"][0]["acl_expectations"]
            if r["grantee"] != "pitchlog_sync_binding_actor"
        ]
    elif fault == "usage":
        next(r for r in value["schemas"] if r["schema_id"] == "public")[
            "acl_expectations"
        ].pop()
    elif fault == "namespace":
        value["tables"][-1]["schema_name"] = "public"
    elif fault == "bool-int":
        value["roles"][-1]["bypass_rls"] = 0
    else:
        r = next(r for r in value["functions"] if r["function_kind"] == "invoker")
        if fault == "invoker":
            r["security_mode"] = "definer"
        else:
            r["function_id"] = "FUNCTION:sync_fence_api:unknown(uuid)"
    with pytest.raises(ValueError):
        validate(value)


def test_catalog_keeps_added_objects_and_actual_bodies():
    """実認可資産の閉集合と失敗条件を検査する。"""
    e = cat._load_product_expectations()
    assert {("sync_fence", "writer_bindings"), ("sync_fence", "writer_admissions")} <= {
        r[:2] for r in e.tables
    }
    rows = [
        r
        for r in cat._expected_lifecycle_function_details()
        if r[0] in {"sync_fence_api", "sync_right_api"}
    ]
    old_names = {
        "observe_writer_binding",
        "guard_first_ball_projection_admission",
        "read_ordinary_order_summary",
        "read_device_state",
        "read_ordinary_checkpoint",
        "assert_writer_binding",
        "prepare_ordinary_projection",
        "guard_writer_records",
        "guard_first_ball_projection_lock",
        "read_writer_database_identity",
        "bind_device",
        "check_ordinary_right",
        "bind_ordinary_device",
        "consume_ordinary_projection",
        "close_writer_binding",
        "check_current_right",
        "read_ordinary_history_page",
        "lock_ordinary_checkpoint",
        "read_writer_identity",
        "publish_writer_binding",
    }
    recovery_names = {"read_attempt_d5", "retire_sync_attempt"}
    p3_names = {
        "append_p3_projection_page",
        "begin_p3_projection_page",
        "bind_p3_device",
        "check_p3_right",
        "finalize_p3_projection_page",
        "persist_p3_projection",
        "read_p3_current",
        "read_p3_current_header",
        "read_p3_current_page",
        "read_p3_writer_binding",
    }
    started_read_names = {
        "read_started_nonplay_active_history",
        "read_started_ordinary_history_page",
        "read_started_play_prefix_history_page",
        "read_viewer_effective_version",
        "read_viewer_play_prefix_history_page",
    }
    preceding_names = {
        "bind_nonplay_device",
        "check_nonplay_right",
        "consume_game_lifecycle",
        "consume_nonplay_substitution",
        "consume_nonplay_tiebreak_start",
        "consume_nonplay_undo",
        "lock_nonplay_checkpoint",
        "prepare_game_lifecycle",
        "prepare_nonplay_undo",
        "read_lifecycle_display",
        "read_lifecycle_state",
        "read_nonplay_active_history",
        "read_nonplay_history_page",
        "verify_replay_device",
    }
    assert {r[1] for r in rows} == (
        old_names
        | preceding_names
        | recovery_names
        | p3_names
        | started_read_names
        | {
        value.split(":")[-1].split("(")[0]
            for value in _TERMINAL_FUNCTION_IDS | _LINEUP_FUNCTION_IDS
        }
    )
    assert len(old_names) == 20
    assert len(preceding_names) == 14
    assert len(p3_names) == 10 and len(started_read_names) == 5
    assert len(_TERMINAL_FUNCTION_IDS) == 7 and len(_LINEUP_FUNCTION_IDS) == 1
    assert len(rows) - len(_TERMINAL_FUNCTION_IDS) - len(_LINEUP_FUNCTION_IDS) == 51
    assert len(rows) == 59
    assert sum(r[4] is False for r in rows) == 2
    assert all(r[9] and r[8] == ("search_path=pg_catalog, pg_temp",) for r in rows)


def test_invoker_has_exact_helper_step_position():
    """実認可資産の閉集合と失敗条件を検査する。"""
    s = load_product_application_steps(ROOT, PRODUCT_SPEC)
    assert s.application_steps[2].element_groups == (
        "functions:rls_helper",
        "functions:definer",
        "functions:invoker",
    )


def test_full_apply_has_attempt_retirement_definitions_and_six_guards():
    """実認可資産の閉集合と失敗条件を検査する。"""
    _, s = prov._build_operation_statements(prov.ProductOperation.APPLY)
    sql = "\n".join(r.sql for r in s)
    assert sql.count("CREATE FUNCTION sync_fence_api.") == 10
    assert (
        sql.count("CREATE FUNCTION sync_right_api.")
        - len(_TERMINAL_FUNCTION_IDS)
        - len(_LINEUP_FUNCTION_IDS)
        == 39
    )
    assert sql.count("CREATE FUNCTION sync_right_api.") == 47
    assert sql.count("CREATE TRIGGER trg_play_prefix_") == 2
    assert sql.count("CREATE TRIGGER sync_writer_") == 4
    assert sql.count("CREATE TRIGGER sync_attempt_retirement_") == 2
    assert sql.count("CREATE TRIGGER trg_first_ball_") == 2


def test_pre_rule_defers_unavailable_dependencies():
    """実認可資産の閉集合と失敗条件を検査する。"""
    _, s = prov._build_operation_statements(prov.ProductOperation.APPLY_PRE_RULE)
    sql = "\n".join(r.sql for r in s)
    assert "CREATE FUNCTION sync_fence_api." not in sql
    assert "CREATE FUNCTION sync_right_api." not in sql
    assert "ALTER TABLE sync_fence." not in sql
    assert "CREATE ROLE pitchlog_sync_binding_actor" in sql


def test_unapply_rejects_before_generation_or_execution(monkeypatch):
    """実認可資産の閉集合と失敗条件を検査する。"""

    def forbidden(*a, **kw):
        """検証用の実資産を読み、予期しない処理を閉じる。"""
        raise AssertionError("DDL生成へ進めない")

    monkeypatch.setattr(prov, "generate_authz_ddl", forbidden)
    with pytest.raises(prov.ProductProvisioningError, match="退役は未提供"):
        prov._build_operation_statements(prov.ProductOperation.UNAPPLY)


def test_reapply_is_closed_to_exact_nine_and_preserves_frozen_first_apply():
    """新9は未存在分岐だけで元全文を実行し既存時は検査だけを行う。"""
    from pitchlog.authz.first_ball_product import (
        application_function_sql,
        body,
        function_details,
    )

    volatilities = {row[1]: row[7] for row in function_details()}
    for row in ADDITIONS["functions"]:
        original = body("function", row["function_id"])
        assert original is not None
        # triggerの付与取消は別の再適用試験が検査する。
        if not original.lstrip().startswith("CREATE FUNCTION"):
            continue
        wrapped = application_function_sql(row["function_id"], original)
        assert wrapped is not None
        assert wrapped.startswith("DO $first_ball_reapply$")
        literal = "'" + original.replace("'", "''") + "'"
        assert wrapped.count("EXECUTE " + literal) == 1
        assert (
            f"IF existing IS NULL THEN\n        EXECUTE {literal};\n        RETURN;"
            in wrapped
        )
        existing_branch = wrapped.split("        RETURN;\n    END IF;", 1)[1]
        assert "CREATE FUNCTION " not in existing_branch
        assert "CREATE TRIGGER " not in existing_branch
        assert "ALTER FUNCTION " not in existing_branch
        assert "GRANT " not in existing_branch
        assert "REVOKE " not in existing_branch
        assert "DROP " not in existing_branch
        # 新しい語彙readだけは採用済みSTABLE。他の旧関数はVOLATILEを維持する。
        expected_volatility = volatilities[row["function_name"]]
        for required in (
            "p.prokind='f'",
            f"p.provolatile='{expected_volatility}'",
            "p.proparallel='u'",
            "NOT p.proisstrict",
            "NOT p.proleakproof",
            "p.provariadic=0",
            "p.pronargdefaults=0",
            "p.proargmodes IS NOT DISTINCT FROM",
            "p.procost=100",
            "p.prorows=",
            "p.prosupport=0",
            "p.probin IS NULL",
            "p.prosqlbody IS NULL",
            "p.protrftypes IS NULL",
            "p.proargnames IS NOT DISTINCT FROM",
            "p.prosecdef=",
            "p.proretset=",
            "pg_get_function_result(p.oid)",
            "p.proconfig=ARRAY['search_path=pg_catalog, pg_temp']::pg_catalog.text[]",
            "pg_catalog.btrim(p.prosrc, E' \\t\\r\\n')=",
            "p.proowner",
            "a.privilege_type,a.is_grantable",
            "a.grantee<>p.proowner",
            "first ball function definition collision",
            "first ball function privilege collision",
        ):
            assert required in existing_branch
        assert f"o.rolname='{row['owner_role_id']}'" in existing_branch
        with pytest.raises(ValueError, match="凍結値"):
            application_function_sql(row["function_id"], original + "-- changed")
    assert (
        application_function_sql("FUNCTION:other:unknown()", "CREATE FUNCTION x")
        is None
    )


def test_reapply_guard_retains_exact_six_triggers_and_refuses_collisions():
    """guardの対象/事象/行単位/関数/有効状態/余剰を検査し修復しない。"""
    from pitchlog.authz.first_ball_product import application_function_sql, body

    key = "FUNCTION:sync_fence_api:guard_writer_records()"
    original = body("function", key)
    assert original is not None
    wrapped = application_function_sql(key, original)
    assert wrapped is not None
    check = wrapped.split("        RETURN;\n    END IF;", 1)[1]
    for name, table, tgtype in (
        ("sync_writer_binding_immutable", "writer_bindings", 27),
        ("sync_writer_binding_no_truncate", "writer_bindings", 34),
        ("sync_writer_admission_immutable", "writer_admissions", 27),
        ("sync_writer_admission_no_truncate", "writer_admissions", 34),
        ("sync_attempt_retirement_immutable", "attempt_retirements", 27),
        ("sync_attempt_retirement_no_truncate", "attempt_retirements", 34),
    ):
        assert (
            f"t.tgname='{name}' AND t.tgrelid='sync_fence.{table}'"
            f"::pg_catalog.regclass AND t.tgtype={tgtype}"
        ) in check
    for required in (
        "<> 6",
        "NOT t.tgisinternal",
        "t.tgfoid=existing",
        "t.tgenabled='O'",
        "NOT t.tgdeferrable",
        "NOT t.tginitdeferred",
        "t.tgconstraint=0",
        "t.tgnargs=0",
        "t.tgattr::text=''",
        "t.tgqual IS NULL",
        "t.tgargs=''::pg_catalog.bytea",
        "t.tgoldtable IS NULL",
        "t.tgnewtable IS NULL",
        "first ball trigger definition collision",
    ):
        assert required in check


# 安打の後発差分だけをimmutable Git原本へ束縛する。旧43pinは変更しない。
_BATTED_SOURCE_REFERENCE_PATH = (
    Path(__file__).parent / "fixtures/batted_source_extension_reference_v1.json"
)
_BATTED_SOURCE_REFERENCE_SHA256 = _EXPECTED_SOURCE_PINS[
    "batted_extension_reference_sha256"
]
_BATTED_PREPARE_ID = (
    "FUNCTION:sync_right_api:prepare_play_prefix_projection(uuid, uuid, uuid, "
    "bytea, uuid, uuid, text)"
)
_BATTED_ADDED_IDS = frozenset(
    {
        "pitchlog_recording_vocab_fn_owner",
        "recording_vocab_api",
        "FUNCTION:recording_vocab_api:read_batted_ball_options(uuid, integer, text)",
        "POLICY:admin_vocabularies:batted_hit_select_admin_vocabularies",
        "POLICY:tenant_vocabularies:batted_hit_select_tenant_vocabularies",
        "POLICY:admin_vocabularies:recording_vocab_select_batted_ball",
        *(
            f"COLUMN-ACL:public:{table}:{column}:{owner}"
            for table, columns, owner in (
                (
                    "admin_vocabularies",
                    ("category", "disabled", "key"),
                    "pitchlog_sync_right_fn_owner",
                ),
                (
                    "tenant_vocabularies",
                    ("category", "disabled", "key", "tenant_id"),
                    "pitchlog_sync_right_fn_owner",
                ),
                (
                    "admin_vocabularies",
                    ("category", "disabled", "display_name", "key"),
                    "pitchlog_recording_vocab_fn_owner",
                ),
            )
            for column in columns
        ),
    }
)


def _load_batted_source_reference(raw: bytes | None = None):
    """全fixture byteを固定し、変更した期待値による自己合格を拒否する。"""
    import hashlib

    data = _BATTED_SOURCE_REFERENCE_PATH.read_bytes() if raw is None else raw
    assert hashlib.sha256(data).hexdigest() == _BATTED_SOURCE_REFERENCE_SHA256
    return json.loads(data)


_BATTED_SUCCESSOR_PATH = (
    Path(__file__).parent / "fixtures/batted_source_extension_successor_v1.json"
)


def _load_batted_successor(raw: bytes | None = None):
    """後継fixtureの全byteを独立pinへ照合し、現木採取の自己合格を拒否する。"""
    import hashlib

    data = _BATTED_SUCCESSOR_PATH.read_bytes() if raw is None else raw
    assert (
        hashlib.sha256(data).hexdigest()
        == _EXPECTED_SOURCE_PINS["batted_extension_successor_sha256"]
    )
    return json.loads(data)


_HISTORICAL_PROJECTION_PATH = (
    Path(__file__).parent / "fixtures/product_supply_historical_projection_v1.json"
)


def _load_historical_projection(raw: bytes | None = None):
    """MVP統合前の637+31文を独立pinへ照合し、現行期待への流用を拒否する。"""
    import hashlib

    data = _HISTORICAL_PROJECTION_PATH.read_bytes() if raw is None else raw
    assert (
        hashlib.sha256(data).hexdigest()
        == _EXPECTED_SOURCE_PINS["product_supply_historical_projection_sha256"]
    )
    fixture = json.loads(data)
    for key in ("keep", "terminal"):
        digest = hashlib.sha256(
            json.dumps(
                [
                    {"sequence": row["sequence"], "sql": row["sql"]}
                    for row in fixture[key]
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        pin = (
            _EXPECTED_SOURCE_PINS["other_generated_statements_sha256"]
            if key == "keep"
            else _EXPECTED_SOURCE_PINS["terminal_generated_statements_sha256"]
        )
        assert digest == pin == fixture[
            "other_generated_statements_sha256"
            if key == "keep"
            else "terminal_generated_statements_sha256"
        ]
    return fixture


def _successor_current_rows(successor, rows):
    """後継fixtureの3文が現行生成行の同byte一件だけを指すことを検査する。"""
    changed = successor["changed_statements"]
    assert len(changed) == 3
    assert {row["element_id"] for row in changed} == {
        _BATTED_PREPARE_ID,
        "FUNCTION:sync_right_api:finish_play_prefix_projection()",
        "FUNCTION:sync_right_api:guard_play_prefix_runner_insert()",
    }
    observed = {}
    for row in rows:
        marker = re.findall(r"(?m)^-- ELEMENT-ID: ([^\n]+)", row.sql)
        assert len(marker) == 1
        if marker[0] in {item["element_id"] for item in changed}:
            observed.setdefault(marker[0], []).append(
                {"sequence": row.sequence, "sql": row.sql}
            )
    for item in changed:
        assert observed[item["element_id"]] == [item["current"]]
    return {item["element_id"]: item["current"] for item in changed}


def _verify_successor_git(successor):
    """後継のcatalog/生成器treeを固定Gitの同一objectへ束縛する。"""
    import hashlib
    import subprocess

    catalog = successor["catalog"]
    generator = successor["generator"]
    revision = generator["revision"]
    assert revision == catalog["revision"]
    assert (
        subprocess.check_output(
            ["git", "rev-parse", "--verify", revision + "^{commit}"],
            cwd=ROOT,
            text=True,
        ).strip()
        == revision
    )
    for path, tree_oid in generator["tree_paths"].items():
        assert (
            subprocess.check_output(
                ["git", "rev-parse", f"{revision}:{path}"], cwd=ROOT, text=True
            ).strip()
            == tree_oid
        )
        assert (
            subprocess.check_output(
                ["git", "rev-parse", f"HEAD:{path}"], cwd=ROOT, text=True
            ).strip()
            == tree_oid
        )
    current = (ROOT / catalog["path"]).read_bytes()
    assert hashlib.sha256(current).hexdigest() == catalog["sha256"]
    assert (
        subprocess.check_output(
            ["git", "show", f"{revision}:{catalog['path']}"], cwd=ROOT
        )
        == current
    )


def _batted_statement_id(sql: str) -> str:
    """原典のmarkerが一意な文だけを有限対応へ送る。"""
    markers = re.findall(r"(?m)^-- ELEMENT-ID: ([^\n]+)", sql)
    assert len(markers) == 1
    return markers[0]


def _project_stats_source_extension(rows):
    """真正Gitの成績89追加だけを外し、旧705文の全byte比較を維持する。"""
    import subprocess

    path = "contracts/authz/product/ddl-elements.json"
    pins = read_ci_followup_inputs()
    revisions = (pins["catalog_before_revision"], pins["catalog_after_revision"])
    before, after = (
        json.loads(subprocess.check_output(["git", "show", f"{rev}:{path}"], cwd=ROOT))
        for rev in revisions
    )
    section_sizes = {
        "roles": 0,
        "databases": 0,
        "schemas": 1,
        "extensions": 0,
        "functions": 5,
        "tables": 3,
        "predicates": 0,
        "policies": 10,
        "acl_expectations": 0,
        "column_acl_expectations": 70,
    }
    added: set[tuple[str, str]] = set()
    for section in PRODUCT_SPEC.element_sections:
        old = {row[section.id_field]: row for row in before[section.section_name]}
        new = {row[section.id_field]: row for row in after[section.section_name]}
        assert len(old) == len(before[section.section_name])
        assert len(new) == len(after[section.section_name])
        assert old.keys() <= new.keys()
        assert all(new[key] == value for key, value in old.items())
        fresh = new.keys() - old.keys()
        assert len(fresh) == section_sizes[section.section_name]
        added.update((section.element_type, key) for key in fresh)
    assert len(added) == 89
    added_ids = {identifier for _, identifier in added}
    assert len(added_ids) == len(added)
    observed: set[str] = set()
    for row in rows:
        # 既batted対向と同じ型拒否を、成績89文の後継検査前にも適用する。
        assert type(row.sequence) is int
        assert type(row.sql) is str
        markers = re.findall(r"(?m)^-- ELEMENT-ID: ([^\n]+)", row.sql)
        assert len(markers) == 1
        key = markers[0]
        assert key not in observed
        observed.add(key)
    # 歴史的89文は現行集合にも同じIDで一件ずつ残る。
    assert added_ids <= observed
    return tuple(rows)


def _project_batted_source_extension(rows):
    """旧17追加と3文の後継だけを全値照合し、残りを歴史原典へ戻す。"""
    import hashlib
    from dataclasses import replace

    reference = _load_batted_source_reference()
    successor = _load_batted_successor()
    _verify_successor_git(successor)
    assert len(rows) == successor["statement_count"]
    assert (
        hashlib.sha256(
            json.dumps(
                [{"sequence": row.sequence, "sql": row.sql} for row in rows],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        == successor["statements_sha256"]
    )
    additions = reference["added_statements"]
    assert len(additions) == len(_BATTED_ADDED_IDS) == 17
    assert {row["element_id"] for row in additions} == _BATTED_ADDED_IDS
    assert reference["changed_statement"]["element_id"] == _BATTED_PREPARE_ID
    public = reference["public_usage"]
    usage = "\nGRANT USAGE ON SCHEMA public TO pitchlog_recording_vocab_fn_owner;\n"
    assert public["after"]["sequence"] == public["before"]["sequence"]
    assert public["after"]["sql"] == public["before"]["sql"] + usage
    current = _successor_current_rows(successor, rows)
    successor_by_id = {
        item["element_id"]: item for item in successor["changed_statements"]
    }
    historical = {
        _BATTED_PREPARE_ID: reference["changed_statement"]["after"],
    }
    for row in reference["terminal_before"]:
        element_id = _batted_statement_id(row["sql"])
        if element_id == _BATTED_PREPARE_ID:
            continue
        historical[element_id] = {"sequence": row["sequence"], "sql": row["sql"]}
    for element_id, item in successor_by_id.items():
        assert item["historical"] == historical[element_id]
        assert current[element_id] == item["current"]
    projected = []
    found = []
    actual_added = []
    terminal_ids = set(historical) - {_BATTED_PREPARE_ID}
    changed_ids = set(successor_by_id)
    for row in rows:
        assert type(row.sequence) is int
        assert type(row.sql) is str
        markers = re.findall(r"(?m)^-- ELEMENT-ID: ([^\n]+)", row.sql)
        assert len(markers) == 1
        element_id = markers[0]
        found.append(element_id)
        if element_id in _BATTED_ADDED_IDS:
            actual_added.append(
                {"element_id": element_id, "sequence": row.sequence, "sql": row.sql}
            )
            continue
        if element_id in changed_ids:
            continue
        if element_id == _BATTED_PREPARE_ID:
            row = replace(row, sql=historical[element_id]["sql"])
        elif element_id in terminal_ids:
            expected = historical[element_id]
            assert {"sequence": row.sequence, "sql": row.sql} == expected
        projected.append(row)
    assert len(found) == len(set(found)) == len(rows)
    assert actual_added == additions
    assert set(successor_by_id) <= set(found)
    return tuple(projected)


def _batted_source_reference_revisions():
    """正式frozen入力の固定2commitだけを独立原典として読む。"""
    import subprocess

    from first_ball_expected_source_pins import _unique_object

    document = json.loads(
        (ROOT / "contracts/tenant_boundary/frozen-inputs.json").read_text(),
        object_pairs_hook=_unique_object,
    )
    result = {}
    for label, key, purpose in (
        (
            "before",
            "pr196_batted_reference_base_revision",
            "PR196安打source差分の正式before原典。旧43pin/全宣言の投影根拠に限り、任意基線へ流用しない。",
        ),
        (
            "after",
            "pr196_batted_reference_candidate_revision",
            "PR196採用安打source差分の固定after原典。既beforeとの全前後値検証に限り、現木期待を生成しない。",
        ),
    ):
        entry = document["frozen_inputs"][key]
        assert type(entry) is dict and set(entry) == {"value", "purpose", "sources"}
        assert entry["purpose"] == purpose
        assert entry["sources"] == [
            "backend/tests/test_sync_apply_product_supply.py:_batted_source_reference_revisions",
        ]
        value = entry["value"]
        assert type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value)
        assert (
            subprocess.check_output(
                ["git", "rev-parse", "--verify", value + "^{commit}"],
                cwd=ROOT,
                text=True,
            ).strip()
            == value
        )
        result[label] = value
    return result


def test_batted_source_reference_is_bound_to_immutable_git():
    """原典commit/tree/全source blobをGitへ照合し、現出力を原典にしない。"""
    import hashlib
    import subprocess

    reference = _load_batted_source_reference()
    assert {key: row["commit"] for key, row in reference["origins"].items()} == {
        **_batted_source_reference_revisions(),
    }
    repository = ROOT
    for origin in reference["origins"].values():
        revision = origin["commit"]
        for path, oid in origin["tree_oids"].items():
            assert (
                subprocess.check_output(
                    ["git", "rev-parse", f"{revision}:{path}"],
                    cwd=repository,
                    text=True,
                ).strip()
                == oid
            )
        for row in origin["files"]:
            assert (
                subprocess.check_output(
                    ["git", "rev-parse", f"{revision}:{row['path']}"],
                    cwd=repository,
                    text=True,
                ).strip()
                == row["git_blob_oid"]
            )
            content = subprocess.check_output(
                ["git", "show", f"{revision}:{row['path']}"], cwd=repository
            )
            assert hashlib.sha256(content).hexdigest() == row["sha256"]
    assert (
        hashlib.sha256(
            json.dumps(
                reference["terminal_before"], ensure_ascii=False, separators=(",", ":")
            ).encode()
        ).hexdigest()
        == _EXPECTED_SOURCE_PINS["terminal_generated_statements_sha256"]
    )


@pytest.mark.parametrize("index", range(30))
def test_batted_extension_rejects_every_other_old_statement(index, monkeypatch):
    """prepare以外の旧30文を1文ずつ改変しても旧署名で通さない。"""
    from dataclasses import replace

    reference = _load_batted_source_reference()
    successor = _load_batted_successor()
    _, base_rows = prov._build_operation_statements(prov.ProductOperation.APPLY)
    current = _successor_current_rows(successor, base_rows)
    others = [
        row
        for row in reference["terminal_before"]
        if f"-- ELEMENT-ID: {_BATTED_PREPARE_ID}\n" not in row["sql"]
    ]
    assert len(others) == 30
    element_id = _batted_statement_id(others[index]["sql"])
    target = current.get(element_id, others[index])["sql"]
    # 基準テストが赤いまま負例の失敗を成功に写さない。
    test_reapply_keeps_all_other_generated_statements_exact()
    steps, rows = prov._build_operation_statements(prov.ProductOperation.APPLY)
    assert sum(row.sql == target for row in rows) == 1
    changed = tuple(
        replace(row, sql=row.sql + "\n-- unknown mutation\n")
        if row.sql == target
        else row
        for row in rows
    )
    monkeypatch.setattr(prov, "_build_operation_statements", lambda _: (steps, changed))
    with pytest.raises(AssertionError):
        test_reapply_keeps_all_other_generated_statements_exact()


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "duplicate",
        "added-sql",
        "prepare-sql",
        "public-sql",
        "old637-sql",
        "sequence",
        "unknown-id",
    ],
)
def test_batted_extension_rejects_unregistered_delta(fault, monkeypatch):
    """有限追加/元SQLの欠落・重複・未知差分・部分一致を拒否する。"""
    from dataclasses import replace

    steps, rows = prov._build_operation_statements(prov.ProductOperation.APPLY)
    changed = list(rows)
    target = next(
        i
        for i, row in enumerate(rows)
        if _batted_statement_id(row.sql) in _BATTED_ADDED_IDS
    )
    if fault == "missing":
        changed.pop(target)
    elif fault == "duplicate":
        changed.append(changed[target])
    else:
        if fault == "prepare-sql":
            target = next(
                i
                for i, row in enumerate(rows)
                if (f"-- ELEMENT-ID: {_BATTED_PREPARE_ID}\n" in row.sql)
            )
        elif fault == "public-sql":
            target = next(
                i
                for i, row in enumerate(rows)
                if ("-- ELEMENT-ID: public\n" in row.sql)
            )
        elif fault == "old637-sql":
            target = next(
                i
                for i, row in enumerate(rows)
                if ("-- ELEMENT-ID: pitchlog_app\n" in row.sql)
            )
        row = changed[target]
        changed[target] = (
            replace(row, sequence=row.sequence + 1)
            if fault == "sequence"
            else replace(row, sql=row.sql.replace("-- ELEMENT-ID:", "-- UNKNOWN:", 1))
            if fault == "unknown-id"
            else replace(row, sql=row.sql + "\n-- unknown\n")
        )
    monkeypatch.setattr(
        prov, "_build_operation_statements", lambda _: (steps, tuple(changed))
    )
    with pytest.raises(AssertionError):
        test_reapply_keeps_all_other_generated_statements_exact()


@pytest.mark.parametrize("location", ["added", "prepare", "old637"])
@pytest.mark.parametrize(
    "fault",
    [
        "float-sequence",
        "bool-sequence",
        "str-sequence",
        "none-sequence",
        "subclass-sequence",
        "subclass-sql",
        "bytes-sql",
        "none-sql",
    ],
)
def test_batted_extension_rejects_nonexact_statement_types(
    location, fault, monkeypatch
):
    """数値同値や同内容の派生型を含め、全行の型を除外前に拒否する。"""
    from dataclasses import replace

    class Sequence(int):
        """同値のint派生型を検査する。"""

    class Sql(str):
        """同内容のstr派生型を検査する。"""

    identifiers = {
        "added": "pitchlog_recording_vocab_fn_owner",
        "prepare": _BATTED_PREPARE_ID,
        "old637": "pitchlog_app",
    }
    steps, rows = prov._build_operation_statements(prov.ProductOperation.APPLY)
    changed = list(rows)
    target = next(
        i
        for i, row in enumerate(rows)
        if _batted_statement_id(row.sql) == identifiers[location]
    )
    row = changed[target]
    if fault.endswith("sequence"):
        values = {
            "float-sequence": float(row.sequence),
            "bool-sequence": bool(row.sequence),
            "str-sequence": str(row.sequence),
            "none-sequence": None,
            "subclass-sequence": Sequence(row.sequence),
        }
        changed[target] = replace(row, sequence=values[fault])
    else:
        values = {
            "subclass-sql": Sql(row.sql),
            "bytes-sql": row.sql.encode(),
            "none-sql": None,
        }
        changed[target] = replace(row, sql=values[fault])
    monkeypatch.setattr(
        prov, "_build_operation_statements", lambda _: (steps, tuple(changed))
    )
    with pytest.raises(AssertionError):
        test_reapply_keeps_all_other_generated_statements_exact()


@pytest.mark.parametrize("fault", ["unknown", "old-before", "anchor", "new-after"])
def test_batted_extension_rejects_reference_mutation(fault):
    """fixture/原典/旧署名対象の書換えを新期待として受理しない。"""
    reference = _load_batted_source_reference()
    if fault == "unknown":
        reference["unknown"] = True
    elif fault == "old-before":
        reference["terminal_before"][0]["sql"] += "\n-- changed\n"
    elif fault == "anchor":
        reference["origins"]["after"]["commit"] = "0" * 40
    else:
        reference["changed_statement"]["after"]["sql"] += "\n-- changed\n"
    with pytest.raises(AssertionError):
        _load_batted_source_reference(json.dumps(reference).encode())


def test_historical_projection_pin_cannot_be_zeroed(monkeypatch):
    """旧637/31文の固定pinをゼロや別値へ差し替えても成功にしない。"""
    for key in (
        "product_supply_historical_projection_sha256",
        "other_generated_statements_sha256",
        "terminal_generated_statements_sha256",
    ):
        with monkeypatch.context() as patch:
            patch.setitem(_EXPECTED_SOURCE_PINS, key, "0" * 64)
            with pytest.raises(AssertionError):
                _load_historical_projection()


def test_reapply_keeps_all_other_generated_statements_exact():
    """歴史層を保持し、統合後の全生成集合を後継pinの同一byteへ束縛する。"""
    import hashlib

    _, rows = prov._build_operation_statements(prov.ProductOperation.APPLY)
    for row in rows:
        assert type(row.sequence) is int
        assert type(row.sql) is str
    successor = _load_batted_successor()
    _verify_successor_git(successor)
    assert len(rows) == successor["statement_count"]
    assert (
        hashlib.sha256(
            json.dumps(
                [{"sequence": row.sequence, "sql": row.sql} for row in rows],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        == successor["statements_sha256"]
    )
    # 歴史的89追加・17追加・旧31文の不変条件を通過した場合だけ後継を成功とする。
    projected = _project_batted_source_extension(
        _project_stats_source_extension(rows)
    )
    historical = _load_historical_projection()
    current_by_id = {
        _batted_statement_id(row.sql): row
        for row in rows
    }
    changed_keep = set(successor["historical_keep_changed_ids"])
    historical_keep = []
    for row in historical["keep"]:
        current = current_by_id[row["element_id"]]
        assert current.sequence == row["sequence"]
        if row["element_id"] in changed_keep:
            assert current.sql != row["sql"]
            historical_keep.append(
                {"sequence": row["sequence"], "sql": row["sql"]}
            )
        else:
            assert current.sql == row["sql"]
            historical_keep.append(
                {"sequence": current.sequence, "sql": current.sql}
            )
    changed_terminal = {
        item["element_id"] for item in successor["changed_statements"]
    }
    historical_terminal = []
    for row in historical["terminal"]:
        current = current_by_id[row["element_id"]]
        assert current.sequence == row["sequence"]
        if row["element_id"] in changed_terminal:
            assert current.sql != row["sql"]
        else:
            assert current.sql == row["sql"]
        historical_terminal.append({"sequence": row["sequence"], "sql": row["sql"]})
    for values, pin in (
        (historical_keep, "other_generated_statements_sha256"),
        (historical_terminal, "terminal_generated_statements_sha256"),
    ):
        assert (
            hashlib.sha256(
                json.dumps(
                    values, ensure_ascii=False, separators=(",", ":")
                ).encode()
            ).hexdigest()
            == _EXPECTED_SOURCE_PINS[pin]
        )
    terminal_ids = (
        _TERMINAL_FUNCTION_IDS
        | _TERMINAL_POLICY_IDS
        | _TERMINAL_COLUMN_ACL_IDS
        | _LINEUP_FUNCTION_IDS
        | _LINEUP_POLICY_IDS
        | _LINEUP_COLUMN_ACL_IDS
    )
    found = [
        _batted_statement_id(row.sql)
        for row in rows
        if _batted_statement_id(row.sql) in terminal_ids
    ]
    assert frozenset(found) == terminal_ids
    assert len(found) == len(terminal_ids) == 31
    assert type(projected) is tuple


def test_reapply_is_per_function_and_normalizes_only_new_table_spacing():
    """部分既配置でも一関数ずつ照合し未知の名前/型を補わない。"""
    from pitchlog.authz.first_ball_product import (
        _function_argument_names,
        _pg_result_type,
        application_function_sql,
        body,
        function_details,
    )

    assert _pg_result_type("TABLE (x boolean)") == "TABLE(x boolean)"
    assert _pg_result_type("void") == "void"
    for row in function_details():
        assert isinstance(row[6], str)
        assert (
            row[6] == "void"
            or row[6] == "trigger"
            or row[6].startswith("TABLE(")
            or " " not in row[6]
        )
    key = "FUNCTION:sync_fence_api:read_writer_identity(uuid)"
    original = body("function", key)
    assert original is not None
    wrapped = application_function_sql(key, original)
    assert wrapped is not None
    assert "guard_writer_records()" not in wrapped
    assert "assert_writer_binding(" not in wrapped
    names, table = _function_argument_names(original)
    assert table is True
    assert names == (
        "p_tenant_id",
        "system_identifier",
        "database_oid",
        "postmaster_started_at",
        "backend_pid",
        "backend_start",
        "transaction_id",
    )
    with pytest.raises(ValueError):
        _function_argument_names("CREATE PROCEDURE x.y() LANGUAGE sql")


def test_device_state_formal_declaration_uses_shared_pipeline():
    """新read1だけを固定owner/ACLと既canonical描画へ追加する。"""
    from pitchlog.authz.first_ball_product import body, declaration
    from pitchlog.authz.sync_right_sql import render_device_state_read_create_sql

    key = "FUNCTION:sync_right_api:read_device_state(uuid, uuid)"
    row = declaration("functions", key)
    assert row is not None
    assert row == {
        "function_id": key,
        "schema_name": "sync_right_api",
        "function_name": "read_device_state",
        "identity_args": "uuid, uuid",
        "function_kind": "definer",
        "owner_role_id": "pitchlog_sync_right_fn_owner",
        "language": "plpgsql",
        "returns": "TABLE(device_active boolean)",
        "security_mode": "definer",
        "volatility": "volatile",
        "search_path": ["pg_catalog", "pg_temp"],
        "acl_expectations": [
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False}
        ],
        "revoked_acl_expectations": [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
        ],
    }
    original = body("function", key)
    assert original is not None
    assert (
        render_device_state_read_create_sql().replace(
            "CREATE OR REPLACE FUNCTION", "CREATE FUNCTION", 1
        )
        in original
    )
    assert "OWNER TO pitchlog_sync_right_fn_owner" in original
    assert "FROM PUBLIC" in original and "TO pitchlog_app" in original


def test_device_state_overload_guard_only_extends_new_wrapper():
    """同名別署名だけを拒否し、真の欠落は既CREATE分岐へ進める。"""
    from pitchlog.authz.first_ball_product import application_function_sql, body

    for row in ADDITIONS["functions"]:
        canonical = body("function", row["function_id"])
        assert canonical is not None
        wrapped = application_function_sql(row["function_id"], canonical)
        assert wrapped is not None
        has_guard = "other.oid IS DISTINCT FROM existing" in wrapped
        assert has_guard is (
            row["function_name"] in {"read_device_state", "verify_replay_device"}
        )
        if has_guard:
            assert wrapped.index("other.oid IS DISTINCT FROM existing") < wrapped.index(
                "IF existing IS NULL THEN"
            )
            assert (
                f"AND other.proname='{row['function_name']}'" in wrapped
            )


def test_expected_source_pin_fixture_has_all_thirty_independent_values():
    """旧37期待/終端5を保持し、原本read1期待だけを分離して閉照合する。"""
    fixture = Path(__file__).parent / "fixtures/first_ball_expected_source_pins_v1.json"
    raw = json.loads(fixture.read_text())
    terminal_keys = {
        "test_sync_apply_product_supply.py": {"terminal_generated_statements_sha256"},
        "test_sync_apply_writer_binding.py": {
            "SYNC_PLAY_PREFIX:read_play_prefix_checkpoint",
            "SYNC_PLAY_PREFIX:lock_play_prefix_checkpoint",
            "SYNC_PLAY_PREFIX:read_play_prefix_history_page",
            "SYNC_PLAY_PREFIX:prepare_play_prefix_projection",
        },
    }
    assert sum(len(keys) for keys in terminal_keys.values()) == 5
    for name, keys in terminal_keys.items():
        assert keys <= raw["pins"][name].keys()
    lineup_keys = {
        "test_sync_apply_writer_binding.py": {
            "SYNC_LINEUP_PREFIX:read_lineup_started_origin",
        },
    }
    assert sum(len(keys) for keys in lineup_keys.values()) == 1
    for name, keys in lineup_keys.items():
        assert keys <= raw["pins"][name].keys()
        assert not keys & terminal_keys.get(name, set())
    batted_keys = {
        "test_batted_hit_product_declarations.py": {
            "old_terminal_declarations_sha256",
            "adopted_prepare_body_sha256",
        },
        "test_batted_hit_storage_boundaries.py": {
            "read_play_prefix_checkpoint",
            "lock_play_prefix_checkpoint",
            "read_play_prefix_history_page",
            "assert_play_prefix_projection",
            "finish_play_prefix_projection",
            "guard_play_prefix_runner_insert",
            "read_lineup_started_origin",
            "old_v2_prepare_body_sha256",
        },
        "test_sync_apply_product_supply.py": {
            "batted_extension_reference_sha256",
            "batted_extension_successor_sha256",
            "product_supply_historical_projection_sha256",
        },
    }
    assert sum(map(len, batted_keys.values())) == 13
    for name, keys in batted_keys.items():
        assert keys <= raw["pins"][name].keys()
    total = sum(len(values) for values in raw["pins"].values())
    assert total - 13 - 5 - 1 == 37
    assert total - 13 - 1 == 42
    assert total - 13 == 43
    assert total == 56
    assert {name: read_expected_source_pins(name) for name in raw["pins"]} == raw[
        "pins"
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        "version",
        "top-extra",
        "file-missing",
        "file-extra",
        "pin-missing",
        "pin-extra",
        "value-type",
        "value-shape",
        "duplicate",
    ],
)
def test_expected_source_pin_reader_rejects_invalid_fixture(mutation, tmp_path):
    """欠落/未知/重複/型/不正桁から固定比較を失わせない。"""
    from first_ball_expected_source_pins import SourcePinError

    fixture = Path(__file__).parent / "fixtures/first_ball_expected_source_pins_v1.json"
    raw = json.loads(fixture.read_text())
    name = "test_sync_apply_product_supply.py"
    key = "other_generated_statements_sha256"
    if mutation == "version":
        raw["schema_version"] = True
    elif mutation == "top-extra":
        raw["extra"] = None
    elif mutation == "file-missing":
        del raw["pins"][name]
    elif mutation == "file-extra":
        raw["pins"]["unknown.py"] = {}
    elif mutation == "pin-missing":
        del raw["pins"][name][key]
    elif mutation == "pin-extra":
        raw["pins"][name]["unknown"] = raw["pins"][name][key]
    elif mutation == "value-type":
        raw["pins"][name][key] = False
    elif mutation == "value-shape":
        raw["pins"][name][key] = "g" * 64
    text = json.dumps(raw)
    if mutation == "duplicate":
        text = text.replace(
            '"schema_version": 1', '"schema_version": 1, "schema_version": 1'
        )
    target = tmp_path / "pins.json"
    target.write_text(text)
    with pytest.raises(SourcePinError):
        read_expected_source_pins(name, path=target)


def test_expected_source_pin_reader_rejects_missing_file_and_unknown_request(tmp_path):
    """fixture欠落と未登録要求は製品から補完せず拒否する。"""
    from first_ball_expected_source_pins import SourcePinError

    with pytest.raises(SourcePinError):
        read_expected_source_pins(
            "test_sync_apply_product_supply.py", path=tmp_path / "missing.json"
        )
    with pytest.raises(SourcePinError):
        read_expected_source_pins("unknown.py")


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "extra",
        "bool",
        "short",
        "not_hex",
        "unknown_commit",
        "purpose",
        "consumer",
        "wrong_existing_commit",
    ],
)
def test_batted_reference_typed_inputs_do_not_authorize_new_origins(
    monkeypatch,
    tmp_path,
    fault,
):
    """型/用途/consumer/実Gitと独立fixture原典の全一致を要求する。"""
    import subprocess
    import sys

    frozen_path = tmp_path / "contracts/tenant_boundary/frozen-inputs.json"
    frozen_path.parent.mkdir(parents=True)
    frozen = json.loads(
        (ROOT / "contracts/tenant_boundary/frozen-inputs.json").read_text()
    )
    (tmp_path / ".git").symlink_to(ROOT / ".git")
    key = "pr196_batted_reference_base_revision"
    entry = frozen["frozen_inputs"][key]
    if fault == "missing":
        del frozen["frozen_inputs"][key]
    elif fault == "extra":
        entry["extra"] = True
    elif fault == "purpose":
        entry["purpose"] += " forged"
    elif fault == "consumer":
        entry["sources"] = []
    else:
        entry["value"] = {
            "bool": True,
            "short": "bad",
            "not_hex": "x" * 40,
            "unknown_commit": "0" * 40,
            "wrong_existing_commit": frozen["frozen_inputs"][
                "pr196_batted_reference_candidate_revision"
            ]["value"],
        }[fault]
    frozen_path.write_text(json.dumps(frozen))
    original = _load_batted_source_reference()
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    with pytest.raises((AssertionError, KeyError, subprocess.CalledProcessError)):
        assert _batted_source_reference_revisions() == {
            label: row["commit"] for label, row in original["origins"].items()
        }
