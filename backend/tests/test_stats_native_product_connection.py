"""成績canonical接合の旧全値保持と有限追加を検証する。"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import frozen_history

from pitchlog.authz import first_ball_product as product
from pitchlog.authz import stats_primitive_product as stats
from pitchlog.authz import stats_primitive_write_state as writer
from pitchlog.authz.function_result_type import pg_result_type
from pitchlog.authz.product_catalog import _LIFECYCLE_FUNCTION_DETAILS_QUERY


def _hash(value: object) -> str:
    """接合前に独立保存した旧集合の全byte相当を比較する。"""
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def _profile_from_fixed_git(root, revision, tmp_path, *, original=False):
    """導入当時の全宣言・323本文・29guardを固定Gitの実codeで保持する。"""
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", revision, "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        timeout=30,
    )
    paths = (
        "backend/src",
        "backend/migrations",
        "backend/domain",
        "frontend/src",
        "frontend/public",
        "contracts",
        "docs/features/mvp-stats-primitives",
        "backend/tests/test_stats_native_product_connection.py",
    )
    # 過去のsnapshot保全庫はこのproducerのimport依存でない。
    # 元検査と現検査の検出対象は変えず、隔離moduleの入力だけを選ぶ。
    names = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", revision, "--", *paths],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.splitlines()
    names = [
        name
        for name in names
        if not name.startswith("contracts/tenant_boundary/history-snapshots/")
    ]
    assert names and len(names) <= 5000
    assert sum(len(name.encode()) + 1 for name in names) <= 512 * 1024
    archive = subprocess.run(
        ["git", "archive", "--format=tar", revision, *names],
        cwd=root,
        check=True,
        capture_output=True,
        timeout=30,
    ).stdout
    assert len(archive) <= 64 * 1024 * 1024
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        members = source.getmembers()
        assert all(
            not member.issym()
            and not member.islnk()
            and Path(member.name).name != ".env"
            for member in members
        )
        source.extractall(tmp_path, filter="data")
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(tmp_path / "backend/src")
    environment.pop("PITCHLOG_TEST_ADMIN_DSN", None)
    environment.pop("PITCHLOG_TEST_ROLE_DSN", None)
    script = """
import json
from pitchlog.authz import first_ball_product as p, stats_primitive_product as s
if ORIGINAL:
    from runpy import run_path
    case=run_path('backend/tests/test_stats_native_product_connection.py')
    case['test_all_old_declarations_bodies_details_and_guards_remain_exact']()
d,b=s.connection_declarations()
rows={
    section:[r for r in values if r[p.IDS[section]] not in
             {x[p.IDS[section]] for x in d.get(section,[])}]
    for section,values in p.ADDITIONS.items()
}
bodies={k:v for k,v in p.BODIES.items() if k not in b}
details=[r for r in p.function_details() if r[0]!='stats_api']
guards={
    r['function_id']:p.application_function_sql(
        r['function_id'],p.body('function',r['function_id']))
    for r in p.ADDITIONS['functions'] if r['schema_name']!='stats_api'
}
print(json.dumps({'additions':rows,'bodies':bodies,'details':details,'guards':guards}))
""".replace("ORIGINAL", repr(original))
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


_SUCCESSOR_FIXTURE = "backend/tests/fixtures/nonplay_product_successors_v1.json"
_BODY_SUCCESSORS = frozenset(
    {
        "column_acl_expectation|COLUMN-ACL:public:play_rows:hidden_at:pitchlog_sync_right_fn_owner",
        (
            "function|FUNCTION:sync_right_api:prepare_play_prefix_projection"
            "(uuid, uuid, uuid, bytea, uuid, uuid, text)"
        ),
        "function|FUNCTION:sync_right_api:finish_play_prefix_projection()",
        "function|FUNCTION:sync_right_api:guard_play_prefix_runner_insert()",
    }
)


def _successor_revision(root):
    """別途凍結する後継入力を補修せず読み、現木を期待値にしない。"""
    path = root / _SUCCESSOR_FIXTURE
    if not stat.S_ISREG(path.lstat().st_mode) or path.is_symlink():
        raise ValueError("後継原典は通常ファイルだけ")

    def closed_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("後継原典の重複key")
            value[key] = item
        return value

    value = json.loads(path.read_text(), object_pairs_hook=closed_pairs)
    if (
        type(value) is not dict
        or set(value) != {"schema_version", "source_revision"}
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or type(value["source_revision"]) is not str
        or len(value["source_revision"]) != 40
        or any(c not in "0123456789abcdef" for c in value["source_revision"])
    ):
        raise ValueError("後継原典の閉schema不一致")
    return value["source_revision"]


def test_original_native_all_values_and_finite_successors_remain_fixed(tmp_path):
    """旧全値を保持し、既非playの列ACL1/本文4だけ別の固定Git全値へ束縛する。"""
    root = Path(__file__).resolve().parents[2]
    original = _profile_from_fixed_git(
        root,
        frozen_history.read_original_pr197_pin("pr197_source_revision", root),
        tmp_path / "original",
        original=True,
    )
    successor = _profile_from_fixed_git(
        root,
        _successor_revision(root),
        tmp_path / "successor",
    )
    assert {
        key
        for key, body in original["bodies"].items()
        if successor["bodies"].get(key) != body
    } == _BODY_SUCCESSORS
    for section, rows in original["additions"].items():
        for row in rows:
            expected = copy.deepcopy(row)
            key = row[product.IDS[section]]
            if (
                key
                == "COLUMN-ACL:public:play_rows:hidden_at:pitchlog_sync_right_fn_owner"
            ):
                assert row["privilege_ids"] == ["SELECT"]
                expected["privilege_ids"] = ["SELECT", "UPDATE"]
            assert product.declaration(section, key) == expected
    for key, body in original["bodies"].items():
        expected = successor["bodies"][key] if key in _BODY_SUCCESSORS else body
        assert product.BODIES.get(key) == expected
    identities = {tuple(row[:3]) for row in original["details"]}
    actual_details = [
        list(row) for row in product.function_details() if tuple(row[:3]) in identities
    ]
    post_details = {tuple(row[:3]): row for row in successor["details"]}
    expected_details = []
    for row in original["details"]:
        body_key = f"function|FUNCTION:{row[0]}:{row[1]}({row[2]})"
        if body_key in _BODY_SUCCESSORS:
            replacement = post_details[tuple(row[:3])]
            # 変更を許すのは凍結された本文だけ。owner/ACL側の属性は旧全値。
            assert replacement[:-1] == row[:-1]
            expected_details.append(replacement)
        else:
            expected_details.append(row)
    assert json.loads(json.dumps(actual_details)) == expected_details
    for key, guard in original["guards"].items():
        expected = (
            successor["guards"][key] if "function|" + key in _BODY_SUCCESSORS else guard
        )
        body = product.body("function", key)
        assert body is not None
        assert product.application_function_sql(key, body) == expected


@pytest.mark.parametrize(
    "invalid",
    [
        '{"schema_version":1,"source_revision":"a","extra":0}',
        '{"schema_version":true,"source_revision":"a"}',
        '{"schema_version":2,"source_revision":"a"}',
        '{"schema_version":1,"source_revision":null}',
        '{"schema_version":1,"source_revision":"ABC"}',
        '{"schema_version":1,"source_revision":"a","schema_version":1}',
        "[]",
    ],
)
def test_successor_reference_never_repairs_invalid_fixture(tmp_path, invalid):
    """後継原典の不正型・余剰・重複keyを補修しない。"""
    path = tmp_path / _SUCCESSOR_FIXTURE
    path.parent.mkdir(parents=True)
    path.write_text(invalid)
    with pytest.raises(ValueError):
        _successor_revision(tmp_path)


def test_successor_reference_refuses_symlink(tmp_path):
    """別パスへの差替えを後継原典として読まない。"""
    path = tmp_path / _SUCCESSOR_FIXTURE
    path.parent.mkdir(parents=True)
    target = tmp_path / "target.json"
    target.write_text("{}")
    path.symlink_to(target)
    with pytest.raises(ValueError):
        _successor_revision(tmp_path)


_STATUS_ACL = "COLUMN-ACL:public:games:status:pitchlog_sync_right_fn_owner"


def _current_row(section, row):
    """終了再開が必要とする既1列の更新権だけを完全な後継値にする。"""
    expected = copy.deepcopy(row)
    if (
        section == "column_acl_expectations"
        and row[product.IDS[section]] == _STATUS_ACL
    ):
        assert row["privilege_ids"] == ["SELECT"]
        expected["privilege_ids"] = ["SELECT", "UPDATE"]
    return expected


def _current_body(key, sql):
    """同1列のGRANT以外は元canonical本文をそのまま要求する。"""
    if key == "column_acl_expectation|" + _STATUS_ACL:
        return (
            "GRANT SELECT (status),UPDATE (status) ON TABLE public.games "
            "TO pitchlog_sync_right_fn_owner;\n"
        )
    return sql


def test_new_five_functions_and_one_private_invoker_are_exact():
    """SQL/ACL/RLSを同じcanonical producerから既installerへ供給する。"""
    declarations, bodies = stats.connection_declarations()
    assert {section: len(rows) for section, rows in declarations.items()} == {
        "functions": 6,
        "policies": 10,
        "column_acl_expectations": 70,
        "schemas": 1,
        "tables": 3,
    }
    assert len(bodies) == 90
    for section, rows in declarations.items():
        for row in rows:
            key = row[product.IDS[section]]
            assert product.declaration(section, key) == _current_row(section, row)
            assert key in product.pre_rule_deferred_ids()
    assert set(stats.candidate_function_bodies()) == {
        "save_primitive_source",
        "open_primitive_snapshot",
        "read_play_export_primitives",
        "read_primitive_totals",
    }
    assert writer.FUNCTION_ID in {
        row["function_id"] for row in declarations["functions"]
    }
    for key, sql in bodies.items():
        kind, identifier = key.split("|", 1)
        canonical = product.body(kind, identifier)
        assert canonical is not None
        assert (
            canonical
            == f"-- ELEMENT-TYPE: {kind}\n-- ELEMENT-ID: {identifier}\n\n"
            + _current_body(key, sql)
        )
        if kind == "function":
            guard = product.application_function_sql(identifier, canonical)
            assert guard is not None
            for condition in (
                "function definition collision",
                "function privilege collision",
                "p.proargnames IS NOT DISTINCT FROM",
                "p.proargmodes IS NOT DISTINCT FROM",
                (
                    "p.prosecdef=FALSE"
                    if identifier.startswith(
                        "FUNCTION:stats_api:rebuild_after_nonplay_undo("
                    )
                    else "p.prosecdef=TRUE"
                ),
                "p.proconfig=ARRAY",
                "pg_catalog.btrim(p.prosrc",
            ):
                assert condition in guard
            with pytest.raises(ValueError):
                product.application_function_sql(identifier, canonical + "\n")
    helpers = [
        row
        for row in declarations["functions"]
        if row["function_name"] == "rebuild_after_nonplay_undo"
    ]
    assert len(helpers) == 1
    assert (
        helpers[0]["security_mode"] == "invoker"
        and helpers[0]["acl_expectations"] == []
    )
    for row in declarations["tables"]:
        assert row["table_id"] in product.TABLES
        assert row["schema_name"] == "sync_fence"
        assert row["enable_row_level_security"] is True
        assert row["force_row_level_security"] is True
    schema = stats.candidate_schema()
    assert schema["owner"] == "pitchlog_owner"
    assert schema["schema_name"] in product.SCHEMAS
    assert schema["acl_expectations"] == [
        {"grantee": stats.APP, "privilege": "USAGE", "grantable": False},
        {"grantee": stats.OWNER, "privilege": "USAGE", "grantable": False},
    ]
    assert all(not row["grantable"] for row in schema["revoked_acl_expectations"])
    assert "'stats_api'" in _LIFECYCLE_FUNCTION_DETAILS_QUERY


@pytest.mark.parametrize(
    "mutation",
    ["role", "privilege", "grant", "unknown_column", "unknown_table", "unknown_schema"],
)
def test_changed_or_unknown_new_declaration_is_rejected(mutation):
    """xminも固定4列だけで、未知列/owner/権限へ一般化しない。"""
    declarations, _ = stats.connection_declarations()
    row = copy.deepcopy(
        next(
            r
            for r in declarations["column_acl_expectations"]
            if r["column_id"] == "xmin"
        )
    )
    if mutation == "role":
        row["grantee_role_id"] = "pitchlog_app"
    elif mutation == "privilege":
        row["privilege_ids"] = ["SELECT", "UPDATE"]
    elif mutation == "grant":
        row["grant_option"] = True
    elif mutation == "unknown_column":
        row["column_id"] = "unknown"
    elif mutation == "unknown_table":
        row["object_id"] = "unknown"
    else:
        row["object_schema"] = "unknown"
    with pytest.raises(ValueError):
        product.require_row("column_acl_expectations", row)


def test_duplicate_same_column_keeps_old_body_and_conflicts_fail(monkeypatch):
    """同値重複で再描画せず、異値/余剰本文は拒否する。"""
    existing = copy.deepcopy(product.ADDITIONS)
    old_bodies = copy.deepcopy(product.BODIES)
    monkeypatch.setattr(product, "ADDITIONS", existing)
    monkeypatch.setattr(product, "BODIES", old_bodies)
    # 再実行するのは後発終了再開が列ACLを追加する前のstats接合点。
    rows, native_bodies = stats.connection_declarations()
    status = next(
        r for r in rows["column_acl_expectations"] if r["expectation_id"] == _STATUS_ACL
    )
    actual_status = next(
        r
        for r in existing["column_acl_expectations"]
        if r["expectation_id"] == _STATUS_ACL
    )
    assert actual_status == _current_row("column_acl_expectations", status)
    existing["column_acl_expectations"][
        existing["column_acl_expectations"].index(actual_status)
    ] = copy.deepcopy(status)
    body_key = "column_acl_expectation|" + _STATUS_ACL
    old_bodies[body_key] = (
        f"-- ELEMENT-TYPE: column_acl_expectation\n-- ELEMENT-ID: {_STATUS_ACL}\n\n"
        + native_bodies[body_key]
    )
    before_rows = copy.deepcopy(existing)
    before_bodies = copy.deepcopy(old_bodies)
    product._activate_stats_profile()
    assert product.ADDITIONS == before_rows
    assert product.BODIES == before_bodies
    original = stats.connection_declarations
    rows, bodies = original()
    row = rows["column_acl_expectations"][0]
    row["grant_option"] = True
    monkeypatch.setattr(stats, "connection_declarations", lambda: (rows, bodies))
    with pytest.raises(ValueError, match="既宣言と衝突"):
        product._activate_stats_profile()
    rows, bodies = original()
    bodies["function|unknown"] = "SELECT true"
    monkeypatch.setattr(stats, "connection_declarations", lambda: (rows, bodies))
    with pytest.raises(ValueError, match="本文集合"):
        product._activate_stats_profile()


@pytest.mark.parametrize("first", ["first_ball_product", "stats_primitive_product"])
def test_real_import_both_orders_without_cycle(first):
    """独立processの実import順2通りと旧名互換を確認する。"""
    other = (
        "stats_primitive_product"
        if first == "first_ball_product"
        else "first_ball_product"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"from pitchlog.authz import {first}; from pitchlog.authz import {other}",
        ],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    for value in ("TABLE (a uuid)", "TABLE(a bigint)", "void", "trigger"):
        assert product._pg_result_type(value) == pg_result_type(value)


@pytest.mark.parametrize("mutation", ["none", "missing", "extra", "owner", "bool_int"])
def test_prospective_profile_requires_exact_closed_new_set(mutation):
    """正式資産供給前でも閉集合の欠落/未知/権限改変を拒否する。"""
    asset = copy.deepcopy(product.ADDITIONS)
    asset["databases"] = [
        {
            "acl_expectations": [copy.deepcopy(product.DB_GRANT)],
            "revoked_acl_expectations": copy.deepcopy(product.DB_REVOKES),
        }
    ]
    asset["schemas"].append(
        {
            "schema_name": "public",
            "acl_expectations": copy.deepcopy(product.PUBLIC_GRANTS),
            "revoked_acl_expectations": [],
        }
    )
    row = next(r for r in asset["functions"] if r["schema_name"] == "stats_api")
    if mutation == "missing":
        asset["functions"].remove(row)
    elif mutation == "extra":
        extra = copy.deepcopy(row)
        extra["function_id"] += "_unknown"
        asset["functions"].append(extra)
    elif mutation == "owner":
        row["owner_role_id"] = "pitchlog_app"
    elif mutation == "bool_int":
        row["acl_expectations"][0]["grantable"] = 0
    if mutation == "none":
        assert product.validate(asset) is True
    else:
        with pytest.raises(ValueError):
            product.validate(asset)


@pytest.mark.parametrize(
    "change", ["owner", "public_create", "app_create", "function_owner_create"]
)
def test_schema_owner_and_create_grant_changes_are_rejected(change):
    """新schemaの既ownerや最小USAGE以外を宣言へ混ぜられない。"""
    declarations = copy.deepcopy(product.ADDITIONS)
    declarations["databases"] = [
        {
            "acl_expectations": [copy.deepcopy(product.DB_GRANT)],
            "revoked_acl_expectations": copy.deepcopy(product.DB_REVOKES),
        }
    ]
    declarations["schemas"].append(
        {
            "schema_name": "public",
            "acl_expectations": copy.deepcopy(product.PUBLIC_GRANTS),
            "revoked_acl_expectations": [],
        }
    )
    schema = next(r for r in declarations["schemas"] if r["schema_name"] == "stats_api")
    if change == "owner":
        schema["owner"] = "pitchlog_app"
    else:
        grantee = {
            "public_create": "PUBLIC",
            "app_create": stats.APP,
            "function_owner_create": stats.OWNER,
        }[change]
        schema["acl_expectations"].append(
            {"grantee": grantee, "privilege": "CREATE", "grantable": False}
        )
    with pytest.raises(ValueError):
        product.validate(declarations)


def test_schema_create_owner_collision_guard_and_minimal_acl_body():
    """既規約と同型で異ownerを修復せず拒否し、CREATE権限を残さない。"""
    sql = stats.candidate_schema_body()
    canonical = product.body("schema", "stats_api")
    assert canonical == "-- ELEMENT-TYPE: schema\n-- ELEMENT-ID: stats_api\n\n" + sql
    assert sql.count("CREATE SCHEMA stats_api AUTHORIZATION pitchlog_owner;") == 1
    assert "n.nspname='stats_api' AND r.rolname='pitchlog_owner'" in sql
    assert "RAISE EXCEPTION 'stats schema owner collision';" in sql
    assert "ALTER SCHEMA" not in sql
    assert "REVOKE ALL ON SCHEMA stats_api FROM PUBLIC;" in sql
    assert (
        "REVOKE CREATE ON SCHEMA stats_api FROM "
        "pitchlog_app,pitchlog_sync_right_fn_owner;" in sql
    )
    assert (
        "GRANT USAGE ON SCHEMA stats_api TO pitchlog_app,pitchlog_sync_right_fn_owner;"
        in sql
    )
    assert "GRANT CREATE" not in sql


def test_canonical_declarations_remain_exact_after_real_json_roundtrip():
    """ORM quoted_nameをJSONへ保存して戻しても厳密型・全fieldを維持する。"""
    declarations, _ = stats.connection_declarations()
    restored = json.loads(json.dumps(declarations, ensure_ascii=False))
    assert product._exact(restored, declarations)


def test_current_v2_sink_does_not_execute_historical_model_or_artifact():
    """履歴profileの来歴を現在5関数の自由な代替版へ変えない。"""
    from pitchlog.repositories.stats_function_codec import _native_profiles
    from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

    profiles = _native_profiles()
    functions = stats.candidate_function_bodies()
    assert len(functions) == 4
    for text in functions.values():
        assert SOURCE_MODEL_HASH in text
        assert profiles["v1"]["model_sha256"] not in text
    save = functions["save_primitive_source"]
    assert "p_evaluation_json->'decisions' IS DISTINCT FROM" in save
    assert "p_evaluation_json->'pending'" not in save
    assert profiles["v1"]["artifact_binding"]["model_sha256"] not in save
    writer_sql = writer.candidate_sql()
    assert f"OR p_model_sha256 IS DISTINCT FROM '{SOURCE_MODEL_HASH}'" in writer_sql
    assert profiles["v1"]["model_sha256"] not in writer_sql
