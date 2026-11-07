"""毎球CSVの唯一SQL源と閉publisherの全値照合。実DB/正式受理ではない。"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from pitchlog.authz import play_export_product as product
from pitchlog.authz import play_export_source_read_product as source_read
from pitchlog.authz import play_export_writer_product as writer


def test_closed_declarations_keep_exact_column_privileges_and_function_types():
    """10列SELECT/9列INSERT以外の既role拡権を作らない。"""
    declarations, bodies = product.connection_declarations()
    assert {key: len(rows) for key, rows in declarations.items()} == {
        "tables": 1,
        "functions": 4,
        "policies": 2,
        "acl_expectations": 0,
        "column_acl_expectations": 19,
    }
    assert len(bodies) == 26
    assert set(declarations) == {
        "tables",
        "functions",
        "policies",
        "acl_expectations",
        "column_acl_expectations",
    }
    assert declarations["tables"] == [
        {
            "table_id": "play_export_snapshots",
            "schema_name": "public",
            "enable_row_level_security": True,
            "force_row_level_security": True,
        }
    ]
    columns = product.source_structure()["columns"]
    assert [(row["name"], row["type"], row["nullable"]) for row in columns] == [
        ("tenant_id", "uuid", False),
        ("game_id", "uuid", False),
        ("play_row_id", "uuid", False),
        ("plays_csv_json", "jsonb", False),
        ("full_innings_json", "jsonb", False),
        ("source_event_id", "uuid", False),
        ("play_version", "bigint", False),
        ("recording_generation", "bigint", False),
        ("event_sequence", "bigint", False),
        ("captured_at", "timestamptz", False),
    ]
    assert columns[6]["suffix"] == "CHECK (play_version > 0)"
    assert columns[9]["suffix"] == "DEFAULT pg_catalog.now()"
    actual = [
        (
            row["column_id"],
            row["grantee_role_id"],
            row["privilege_ids"],
            row["grant_option"],
        )
        for row in declarations["column_acl_expectations"]
    ]
    assert actual == [
        (row["name"], "pitchlog_app", ["SELECT"], False) for row in columns
    ] + [
        (row["name"], "pitchlog_sync_right_fn_owner", ["INSERT"], False)
        for row in columns[:-1]
    ]
    for row in declarations["functions"]:
        assert row["owner_role_id"] == "pitchlog_sync_right_fn_owner"
        assert row["security_mode"] == row["function_kind"] == "definer"
        assert row["language"] == "plpgsql"
        assert row["search_path"] == ["pg_catalog", "pg_temp"]
        assert row["acl_expectations"] == [
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False}
        ]
        assert row["revoked_acl_expectations"] == [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
        ]
    assert [row["volatility"] for row in declarations["functions"]] == [
        "volatile",
        "volatile",
        "volatile",
        "stable",
    ]
    assert product.validate(declarations, bodies) is True


def test_all_four_function_bodies_reuse_the_only_provider_bytes():
    """生成集計/保存/原本readを別実装や加工SQLへ置き換えない。"""
    declarations, bodies = product.connection_declarations()
    sql = {
        row["function_name"]: bodies["function|" + row["function_id"]]
        for row in declarations["functions"]
    }
    assert sql["read_writer_play_export_aggregate"].startswith(
        writer.candidate_function_body()
    )
    assert sql["save_writer_play_export_snapshot"].startswith(
        writer.candidate_save_body()
    )
    assert (
        sql["read_writer_play_export_aggregate"]
        + sql["save_writer_play_export_snapshot"]
    ) == writer.candidate_install_sql()
    source = Path(product._SOURCE).read_text()
    assert (
        sql["read_writer_play_export_substitute"]
        == source[
            source.index(
                "CREATE FUNCTION stats_api.read_writer_play_export_substitute("
            ) :
        ]
    )
    assert sql["read_play_export_source_page"] == source_read.candidate_read_bundle()[1]
    assert len(product.source_structure()["indexes"]) == 3
    assert tuple(product.source_structure()["indexes"]) == (
        "ix_play_export_snapshots_game_captured",
        "ix_play_rows_export_audit",
        "ix_operation_events_export_audit",
    )
    metadata = product.source_structure()
    assert (
        metadata["create_table"]
        == source[
            source.index("CREATE TABLE public.play_export_snapshots") : source.index(
                "\nALTER TABLE public.play_export_snapshots"
            )
        ].rstrip()
    )
    for name, statement in metadata["indexes"].items():
        start = source.index("CREATE INDEX " + name)
        assert statement == source[start : source.index(";", start) + 1]
    assert "CREATE TABLE" not in bodies["table|play_export_snapshots"]
    assert "CREATE INDEX" not in bodies["table|play_export_snapshots"]
    assert bodies["table|play_export_snapshots"].count("ROW LEVEL SECURITY") == 2


def test_publisher_copies_outputs_and_keeps_unrelated_asset_separate():
    """呼出側の変更で原典や次の描画を変えず、全母集合受理へ拡張しない。"""
    declarations, bodies = product.connection_declarations()
    original = copy.deepcopy(declarations)
    declarations["tables"].append({"table_id": "unrelated", "schema_name": "public"})
    bodies["table|unrelated"] = "-- unrelated source"
    assert product.validate(declarations, bodies) is True
    assert product.connection_declarations()[0] == original
    assert product.validate({key: [] for key in original}, {}) is False


def test_source_byte_change_is_not_silently_accepted(tmp_path, monkeypatch):
    """原典の無裁定の追補を、動的期待値の描画だけで受理しない。"""
    changed = tmp_path / "changed.sql"
    changed.write_bytes(product._SOURCE.read_bytes() + b"\n")
    monkeypatch.setattr(product, "_SOURCE", changed)
    with pytest.raises(ValueError, match="固定byte"):
        product.connection_declarations()


@pytest.mark.parametrize(
    "case",
    [
        "table-rls",
        "table-bool-as-int",
        "function-owner",
        "function-security",
        "function-volatility",
        "function-result",
        "function-path",
        "function-grant",
        "column-update",
        "column-grant-option",
        "column-role",
        "column-name",
        "policy-role",
        "policy-expression",
        "extra-field",
    ],
)
def test_full_field_mutations_are_rejected(case):
    """既期待を部分一致へ弱めず、型/owner/権限/式の差を拒否する。"""
    declarations, bodies = product.connection_declarations()
    if case == "table-rls":
        declarations["tables"][0]["force_row_level_security"] = False
    elif case == "table-bool-as-int":
        declarations["tables"][0]["force_row_level_security"] = 1
    elif case.startswith("function-"):
        field, value = {
            "function-owner": ("owner_role_id", "pitchlog_app"),
            "function-security": ("security_mode", "invoker"),
            "function-volatility": ("volatility", "stable"),
            "function-result": ("returns", "TABLE(pitcher_pitch_count text)"),
            "function-path": ("search_path", ["pg_catalog", "public"]),
            "function-grant": (
                "acl_expectations",
                [{"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}],
            ),
        }[case]
        declarations["functions"][0][field] = value
    elif case.startswith("column-"):
        field, value = {
            "column-update": ("privilege_ids", ["SELECT", "UPDATE"]),
            "column-grant-option": ("grant_option", True),
            "column-role": ("grantee_role_id", "PUBLIC"),
            "column-name": ("column_id", "captured_at"),
        }[case]
        declarations["column_acl_expectations"][0][field] = value
    elif case == "policy-role":
        declarations["policies"][0]["role_ids"] = ["PUBLIC"]
    elif case == "policy-expression":
        declarations["policies"][0]["using_expression"] = "true"
    else:
        declarations["functions"][0]["unreviewed"] = True
    with pytest.raises(ValueError, match="全field"):
        product.validate(declarations, bodies)


@pytest.mark.parametrize(
    "section",
    [
        "tables",
        "functions",
        "policies",
        "column_acl_expectations",
    ],
)
@pytest.mark.parametrize("fault", ["missing", "duplicate", "unknown-id"])
def test_partial_duplicate_and_extra_target_declarations_are_rejected(section, fault):
    """対象table/objectを別名にしても、部分/重複/余剰を見逃さない。"""
    declarations, bodies = product.connection_declarations()
    if fault == "missing":
        declarations[section].pop()
    else:
        extra = copy.deepcopy(declarations[section][0])
        if fault == "unknown-id":
            key = {
                "tables": "table_id",
                "functions": "function_id",
                "policies": "policy_id",
                "column_acl_expectations": "expectation_id",
            }[section]
            extra[key] += ":unreviewed"
        declarations[section].append(extra)
    with pytest.raises(ValueError, match="部分/余剰"):
        product.validate(declarations, bodies)


def test_extra_table_acl_is_rejected_even_without_any_function_only_role():
    """app/PUBLIC向け表GRANTを、role名だけで対象外へ漏らさない。"""
    declarations, bodies = product.connection_declarations()
    declarations["acl_expectations"].append(
        {
            "acl_id": "ACL:public:play_export_snapshots:PUBLIC",
            "object_kind": "table",
            "object_schema": "public",
            "object_id": "play_export_snapshots",
            "profile": "function_only",
            "grantee_role_id": "PUBLIC",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        }
    )
    with pytest.raises(ValueError, match="acl_expectations"):
        product.validate(declarations, bodies)


@pytest.mark.parametrize("fault", ["body-change", "body-missing", "body-extra"])
def test_body_equality_is_full_and_does_not_ignore_unknown_target_keys(fault):
    """正文を一字も無視せず、余剰sourceも取り込まない。"""
    declarations, bodies = product.connection_declarations()
    key = next(k for k in bodies if k.startswith("function|"))
    if fault == "body-change":
        bodies[key] += "\n"
    elif fault == "body-missing":
        del bodies[key]
    else:
        bodies["function|FUNCTION:stats_api:read_play_export_unreviewed()"] = (
            "SELECT true;"
        )
    with pytest.raises(ValueError, match="本文"):
        product.validate(declarations, bodies)


@pytest.mark.parametrize(
    "fault",
    [
        "owner",
        "grant-option",
        "security",
        "volatility",
        "search-path",
        "arg-type",
        "result-type",
        "duplicate",
        "extra-sql",
        "parallel",
        "strict",
        "body-change",
    ],
)
def test_provider_attribute_or_unknown_sql_changes_are_rejected(fault, monkeypatch):
    """唯一providerを名乗っても署名/実行属性/ACL/文数の差は通さない。"""
    original = writer.candidate_install_sql()
    altered = {
        "owner": lambda: original.replace(
            "OWNER TO pitchlog_sync_right_fn_owner", "OWNER TO pitchlog_app", 1
        ),
        "grant-option": lambda: original.replace(
            "TO pitchlog_app;", "TO pitchlog_app WITH GRANT OPTION;", 1
        ),
        "security": lambda: original.replace("SECURITY DEFINER", "SECURITY INVOKER", 1),
        "volatility": lambda: original.replace("VOLATILE", "STABLE", 1),
        "search-path": lambda: original.replace(
            "search_path=pg_catalog,pg_temp", "search_path=pg_catalog,public", 1
        ),
        "arg-type": lambda: original.replace(
            "p_attempt_id uuid", "p_attempt_id text", 1
        ),
        "result-type": lambda: original.replace(
            "pitcher_pitch_count bigint", "pitcher_pitch_count text", 1
        ),
        "duplicate": lambda: original + original,
        "extra-sql": lambda: original + "\nGRANT SELECT ON public.games TO PUBLIC;\n",
        "parallel": lambda: original.replace(
            "SECURITY DEFINER", "SECURITY DEFINER PARALLEL SAFE", 1
        ),
        "strict": lambda: original.replace(
            "SECURITY DEFINER", "SECURITY DEFINER STRICT", 1
        ),
        "body-change": lambda: original.replace("p_revision<1", "p_revision<2", 1),
    }[fault]()
    assert altered != original
    monkeypatch.setattr(writer, "candidate_install_sql", lambda: altered)
    with pytest.raises(ValueError):
        product.connection_declarations()


def test_reader_cannot_overwrite_another_provider_under_a_duplicate_function_name(
    monkeypatch,
):
    """dict合成による別sourceへの置換を、各源の閉集合で拒否する。"""
    query, original = source_read.candidate_read_bundle()
    extra = original + writer.candidate_install_sql()
    monkeypatch.setattr(source_read, "candidate_read_bundle", lambda: (query, extra))
    with pytest.raises(ValueError, match="個別関数源"):
        product.connection_declarations()
