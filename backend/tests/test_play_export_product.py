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
        "column_acl_expectations": 19,
    }
    assert len(bodies) == 26
    assert set(declarations) == {
        "tables",
        "functions",
        "policies",
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
