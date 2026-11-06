"""非作者採用のnative4SQL/84bodyと実modelの閉producerを照合する。"""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import patch

import pytest
from sqlalchemy import Column, Text
from test_stats_native_undo import verified_native_root as verified_native_root

from pitchlog.authz import stats_primitive_product as product
from pitchlog.authz import stats_primitive_sql as sql
from pitchlog.authz.first_ball_product import _function_argument_names
from pitchlog.db.game_state.stats import StatsFactVersion
from pitchlog.domaingen.core import GenerationError

# de9d8cb3の非作者採用対象。runtime生成結果から期待を更新しない。
_SQL_SHA = {
    "open_primitive_snapshot": (
        "1ad8be9a35bf0887d24e77f9fd10541e8c13b89e87e557dc1665e62bb1bea9aa"
    ),
    "read_play_export_primitives": (
        "c914af15584d7fc32c9d915f67cc979c74b88a41ae03e1c0a8d19c8a74db50cd"
    ),
    "read_primitive_totals": (
        "2157a5fb5bba534f1bbbd3a770cc06c77d3c989d2aab2863edecace9d0f75c83"
    ),
    "save_primitive_source": (
        "d26495276d4060a16ff33bcb2a6d127a85c4b0608ec05e0d63f6844dcd4ad68b"
    ),
}
_DECLARATIONS_SHA = "93c0ef2811060437b51ad1f74f05a614913fa52e60bb7ddf8de9676ba44e69bc"
_BODIES_SHA = "490600c54796286043cfe8317f9c5b5386792ee6bd86194566d26c6f88e70b45"
_INSTALLER_SHA = "cca40e353ddca6b40ceedbb57ee3404013a279fefa826dd96709d26ed353b122"
_OPERATIONS_SHA = "b79d2cae20e3a71028f10c0a4acb21a64be2a383eeedbcef286efaea9037a2a3"


def _json_sha(value):
    """採用cacheと同じJSON描画の全byteを比較する。"""
    return hashlib.sha256(
        (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    ).hexdigest()


def _legacy_sql(tmp_path, monkeypatch):
    """真正immutable v1入力を同compilerへ渡し、旧SQL全期待を歴史比較する。"""
    root = sql._ROOT
    contract = json.loads(
        (
            root / "docs/features/mvp-stats-primitives/primitive-output.candidate.json"
        ).read_text()
    )
    origin = contract["x-v1-immutable-model-inputs"]

    def blob(path):
        return subprocess.check_output(
            ["git", "-C", str(root), "show", origin["revision"] + ":" + path]
        )

    manifest = json.loads(blob(sql._MANIFEST_PATH))
    paths = {sql._MANIFEST_PATH, *origin["paths"], *manifest["generatedFiles"]}
    for name in paths:
        raw = blob(name)
        if name in origin["paths"]:
            assert hashlib.sha256(raw).hexdigest() == origin["paths"][name]
        if name in manifest["generatedFiles"]:
            assert hashlib.sha256(raw).hexdigest() == manifest["generatedFiles"][name]
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    source_name = "backend/src/pitchlog/authz/stats_primitive_sql.py"
    module = ModuleType("__legacy_stats_sql__")
    module.__dict__["__file__"] = str(tmp_path / source_name)
    source = blob(source_name)
    exec(compile(source, "<immutable-v1-stats-sql>", "exec"), module.__dict__)
    module.__dict__["_ROOT"] = tmp_path
    module.__dict__["SOURCE_MODEL_HASH"] = manifest["commonModelHash"]
    historical_model = json.loads(blob("backend/domain/play-export.model.json"))
    module.__dict__["METRIC_IDS"] = tuple(
        row["id"]
        for row in historical_model["calculations"][0]["typedProgram"]["metrics"]
    )
    monkeypatch.setattr(
        product,
        "candidate_function_bodies",
        module.__dict__["candidate_function_bodies"],
    )
    return module


@pytest.fixture
def legacy_sql(tmp_path, monkeypatch):
    """旧installer比較だけに閉じた一時supplierを渡す。"""
    return _legacy_sql(tmp_path, monkeypatch)


def test_all_four_sql_and_84_bodies_preserve_adopted_whole_bytes():
    """既write-state試験からの引数なし呼出し互換も保つ。"""
    temporary_root = Path(
        os.environ.get("PITCHLOG_PYTEST_TMPDIR")
        or Path.home() / ".cache/pitchlog/pytest-tmp"
    )
    temporary_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix="stats-v1-reference-", dir=temporary_root
    ) as directory:
        with pytest.MonkeyPatch.context() as monkeypatch:
            _assert_legacy_sql_values(_legacy_sql(Path(directory), monkeypatch))


def _assert_legacy_sql_values(legacy_sql):
    """rawSQLと旧54列/7policy+追加16列/3policyを全値で保つ。"""
    bodies = legacy_sql.candidate_function_bodies()
    assert {
        name: hashlib.sha256(body.encode()).hexdigest() for name, body in bodies.items()
    } == _SQL_SHA
    declarations, raw = product.candidate_declarations()
    assert _json_sha(declarations) == _DECLARATIONS_SHA
    assert _json_sha(raw) == _BODIES_SHA
    assert {key: len(value) for key, value in declarations.items()} == {
        "functions": 4,
        "policies": 10,
        "column_acl_expectations": 70,
    }
    assert len(raw) == 84
    assert legacy_sql.candidate_function_bodies() == bodies


def test_installer_and_operation_requirements_preserve_adopted_values(legacy_sql):
    """実適用待ちのowner/ACL footerとnonce/RRRO境界を落とさない。"""
    assert (
        hashlib.sha256(product.candidate_install_sql().encode()).hexdigest()
        == _INSTALLER_SHA
    )
    assert _json_sha(product.operation_candidates()) == _OPERATIONS_SHA
    declarations, bodies = product.candidate_declarations()
    for row in declarations["functions"]:
        key = row["function_id"]
        raw = bodies["function|" + key]
        applied = product.function_application_body(key)
        assert applied is not None and applied.startswith(raw + "\nALTER FUNCTION")
        assert f" OWNER TO {product.OWNER};\n" in applied
        assert " FROM PUBLIC,pitchlog_app;\n" in applied
        assert " TO pitchlog_app;\n" in applied
        assert product.declaration("functions", key) == row
        names, table_result = _function_argument_names(raw)
        assert table_result is True
        assert names[: len(row["identity_args"].split(","))] == tuple(
            p["name"]
            for op in product.operation_candidates()
            if op["function_id"] == key
            for p in op["parameters"]
        )
    assert product.declaration("unknown", "unknown") is None
    assert product.function_application_body("FUNCTION:stats_api:unknown()") is None
    assert product.body("function", "FUNCTION:stats_api:unknown()") is None


def test_schema_usage_and_function_details_are_closed_without_create_grant():
    """既ownerのみがschemaを所有し、app/FnOwnerのUSAGEへ閉じる。"""
    assert product.candidate_schema() == {
        "schema_id": "stats_api",
        "schema_name": "stats_api",
        "creation": "product_ddl",
        "owner": "pitchlog_owner",
        "ownership_path": "direct",
        "acl_expectations": [
            {"grantee": "pitchlog_app", "privilege": "USAGE", "grantable": False},
            {
                "grantee": "pitchlog_sync_right_fn_owner",
                "privilege": "USAGE",
                "grantable": False,
            },
        ],
        "revoked_acl_expectations": [
            {"grantee": role, "privilege": privilege, "grantable": False}
            for role, privilege in [
                ("PUBLIC", "USAGE"),
                ("PUBLIC", "CREATE"),
                ("pitchlog_app", "CREATE"),
                ("pitchlog_sync_right_fn_owner", "CREATE"),
            ]
        ],
    }
    details = product.function_details()
    assert len(details) == 4
    assert {row[1] for row in details} == set(_SQL_SHA)
    assert all(
        row[0] == "stats_api"
        and row[3:6] == ("pitchlog_sync_right_fn_owner", True, "plpgsql")
        and row[7:9] == ("v", ("search_path=pg_catalog, pg_temp",))
        for row in details
    )
    declarations, bodies = product.candidate_declarations()
    for row in declarations["column_acl_expectations"]:
        assert row["object_kind"] == "column"
        assert row["grantee_role_id"] == "pitchlog_sync_right_fn_owner"
        assert row["grant_option"] is False
        assert set(row["privilege_ids"]) <= {"SELECT", "INSERT", "UPDATE"}
    assert not any(
        " TO pitchlog_app" in value
        for key, value in bodies.items()
        if key.startswith("column_acl")
    )


@pytest.fixture
def copied_inputs(tmp_path, monkeypatch):
    """既唯一モデルの入力6ファイルだけを試験所有先へコピーする。"""
    paths = [
        sql._MODEL_PATH,
        sql._CONSUMER_PATH,
        sql._MANIFEST_PATH,
        *sql._SQL_PATHS,
        *sql._ARTIFACT_PATHS,
        "backend/domain/play-export-undo-selection.model.json",
        "backend/src/pitchlog/exports/generated/play_primitives_native.sql",
        "backend/src/pitchlog/stats/generated/stats_native.sql",
        "backend/src/pitchlog/stats/generated/stats_rates_native.sql",
        "backend/domain/model.schema.json",
        "docs/features/mvp-stats-primitives/primitive-output.candidate.json",
    ]
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((sql._ROOT / relative).read_bytes())
    monkeypatch.setattr(sql, "_ROOT", tmp_path)
    # 対向の前に、同じ供給全体が実際に成立することを確認する。
    sql._verified_inputs(tmp_path)
    return tmp_path


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown-model",
        "unknown-metric",
        "unknown-type",
        "consumer-cycle",
        "SQL-extra",
        "artifact",
        "binding-model",
        "binding-extra",
        "manifest-model",
    ],
)
def test_unknown_or_changed_generation_inputs_never_publish(copied_inputs, mutation):
    """未知モデル/演算/型/参照/生成SQL/実artifactを成功へ補修しない。"""
    root = copied_inputs
    path = sql._MODEL_PATH if mutation.startswith("unknown") else sql._MANIFEST_PATH
    if mutation == "consumer-cycle":
        path = sql._CONSUMER_PATH
    value = json.loads((root / path).read_text())
    if mutation == "unknown-model":
        value["unknown"] = True
    elif mutation == "unknown-metric":
        value["calculations"][0]["typedProgram"]["metrics"][0]["id"] = "unknown"
    elif mutation == "unknown-type":
        value["calculations"][0]["typedProgram"]["fields"]["event_kind"]["type"] = (
            "unknown"
        )
    elif mutation == "consumer-cycle":
        value["calculations"][0]["typedProgram"]["commonCalculationId"] = (
            "same-as-consumer"
        )
    elif mutation == "SQL-extra":
        (root / sql._SQL_PATH).write_text(
            (root / sql._SQL_PATH).read_text() + "\nSELECT 1;\n"
        )
    elif mutation == "artifact":
        target = root / sorted(sql._ARTIFACT_PATHS)[0]
        target.write_text(target.read_text() + "\n# changed\n")
    elif mutation == "binding-model":
        value["t5ArtifactSetBinding"]["model_sha256"] = "sha256:" + "0" * 64
    elif mutation == "binding-extra":
        value["t5ArtifactSetBinding"]["artifacts"]["unregistered"] = "0" * 64
    else:
        value["commonModelHash"] = "sha256:" + "0" * 64
    (root / path).write_text(json.dumps(value))
    with pytest.raises((ValueError, GenerationError)):
        sql.candidate_function_bodies()


@pytest.mark.parametrize("mutation", ["column", "type", "nullable", "schema"])
def test_actual_model_unknown_columns_and_types_refuse_acl(mutation):
    """modelの列追加/型/NULL/配置変化を全表grantで吸収しない。"""
    table = StatsFactVersion.__table__
    if mutation == "column":
        added = Column("unregistered", Text)
        table.append_column(added)
        try:
            with pytest.raises(ValueError):
                product.candidate_declarations()
        finally:
            table._columns.remove(added)
    else:
        target = table.c.revision if mutation != "schema" else table
        attribute = {"type": "type", "nullable": "nullable", "schema": "schema"}[
            mutation
        ]
        value = {"type": Text(), "nullable": True, "schema": "public"}[mutation]
        with patch.object(target, attribute, value):
            with pytest.raises(ValueError):
                product.candidate_declarations()


def test_unknown_function_and_unapproved_privilege_are_refused(monkeypatch):
    """関数集合や列権限の増加を固定件数だけで通さない。"""
    original = product.candidate_function_bodies
    monkeypatch.setattr(
        product,
        "candidate_function_bodies",
        lambda: {**original(), "unknown": "SELECT 1"},
    )
    with pytest.raises(ValueError):
        product.candidate_declarations()
    for privileges in (["DELETE"], ["SELECT", "EXECUTE"], ["SELECT", "UPDATE"]):
        with pytest.raises(ValueError):
            product._add_column({}, {}, "public", "players", "id", privileges)


def test_private_table_profiles_match_existing_migration_owner_force_rls():
    """実表3/54列とowner/FORCE RLSを登録側から取りこぼさない。"""
    import ast
    import re

    from sqlalchemy.dialects import postgresql

    from pitchlog.db.game_state.stats import StatsPrimitiveFact, StatsPrimitiveSource

    migration = sql._ROOT / "backend/migrations/versions/0041_stats_fact_versions.py"
    tree = ast.parse(migration.read_text())
    upgrade = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
    )
    commands = [
        re.sub(r"\s+", " ", node.args[0].value).strip()
        for node in ast.walk(upgrade)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ]
    assert sum(command.startswith("CREATE TABLE ") for command in commands) == 3
    profiles = product.candidate_table_profile()
    tables, bodies = product.candidate_table_declarations()
    assert len(profiles) == len(tables) == len(bodies) == 3
    for model, profile, declaration in zip(
        (StatsFactVersion, StatsPrimitiveSource, StatsPrimitiveFact),
        profiles,
        tables,
        strict=True,
    ):
        name = model.__table__.name
        assert profile == {
            "table_id": name,
            "schema_name": "sync_fence",
            "owner": "pitchlog_owner",
            "enable_row_level_security": True,
            "force_row_level_security": True,
        }
        assert declaration == {
            key: value for key, value in profile.items() if key != "owner"
        }
        ddl = next(
            command
            for command in commands
            if command.startswith("CREATE TABLE sync_fence." + name + " (")
        )
        column_text = ddl.split("(", 1)[1].split("PRIMARY KEY", 1)[0].rstrip(", ")
        actual = [value.strip() for value in column_text.split(",")]
        expected = [
            column.name
            + " "
            + str(column.type.compile(dialect=postgresql.dialect()))
            + (" NOT NULL" if column.nullable is False else "")
            for column in model.__table__.c
        ]
        assert actual == expected
        assert f"ALTER TABLE sync_fence.{name} OWNER TO pitchlog_owner" in commands
        assert f"ALTER TABLE sync_fence.{name} ENABLE ROW LEVEL SECURITY" in commands
        assert f"ALTER TABLE sync_fence.{name} FORCE ROW LEVEL SECURITY" in commands
        assert (
            f"REVOKE ALL ON TABLE sync_fence.{name} FROM PUBLIC, pitchlog_app, "
            "pitchlog_sync_binding_actor, pitchlog_rg1_control_actor, "
            "pitchlog_sync_right_fn_owner"
        ) in commands
        assert bodies["table|" + name] == (
            f"ALTER TABLE sync_fence.{name} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE sync_fence.{name} FORCE ROW LEVEL SECURITY;\n"
            f"REVOKE ALL ON TABLE sync_fence.{name} FROM PUBLIC,pitchlog_app;\n"
        )


def test_undo_private_helper_has_no_app_or_public_execute(verified_native_root):
    """既4関数のfamilyを増やさず、SQL内呼出専用invokerだけを別宣言する。"""
    declarations, bodies = product.undo_candidate_declarations()
    assert set(declarations) == {"functions"}
    (row,) = declarations["functions"]
    assert row["function_kind"] == row["security_mode"] == "invoker"
    assert row["acl_expectations"] == []
    assert row["revoked_acl_expectations"] == [
        {"grantee": role, "privilege": "EXECUTE", "grantable": False}
        for role in ("PUBLIC", "pitchlog_app")
    ]
    assert product.declaration("functions", row["function_id"]) == row
    assert (
        product.body("function", row["function_id"])
        == bodies["function|" + row["function_id"]]
    )
    installed = product.undo_candidate_install_sql()
    assert "SECURITY INVOKER" in installed
    assert "FROM PUBLIC,pitchlog_app" in installed
    assert "GRANT EXECUTE" not in installed
