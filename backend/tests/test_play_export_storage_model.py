"""0047の実upgradeと型元の全構造・監査索引を照合する。"""

from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy import CheckConstraint, MetaData, Table, text
from sqlalchemy.dialects.postgresql import dialect

from pitchlog.db import all_models
from pitchlog.db import current_product_startup as current
from pitchlog.db.game_state.models import Game, PlayRow
from pitchlog.db.play_export.models import (
    PlayExportSnapshot,
    event_audit_index,
    play_audit_index,
    snapshot_game_index,
)


def test_actual_migration_and_play_export_model_match(monkeypatch):
    """モデルを自己期待にせず実upgradeが作る列/制約/索引と比較する。"""
    tables, indexes, statements = [], [], []

    def create_table(name, *items, **kwargs):
        table = Table(name, MetaData(), *items, **kwargs)
        cast(Table, Game.__table__).to_metadata(table.metadata)
        cast(Table, PlayRow.__table__).to_metadata(table.metadata)
        tables.append(table)

    def create_index(name, table_name, columns, **kwargs):
        indexes.append((name, table_name, columns, kwargs))

    import alembic

    monkeypatch.setattr(
        alembic,
        "op",
        SimpleNamespace(
            create_table=create_table,
            create_index=create_index,
            execute=statements.append,
        ),
    )
    migration = run_path(
        str(
            Path(__file__).parents[1]
            / "migrations/versions/0047_play_export_snapshots.py"
        )
    )
    migration["upgrade"]()
    assert len(tables) == 1
    actual, model = tables[0], PlayExportSnapshot.__table__
    assert actual.fullname == model.fullname == "public.play_export_snapshots"

    def columns(table):
        return [
            (
                c.name,
                c.type.compile(dialect=dialect()),
                c.nullable,
                c.default,
                None
                if c.server_default is None
                else str(c.server_default.arg).replace("pg_catalog.now()", "now()"),
                c.identity,
                c.computed,
            )
            for c in table.c
        ]

    assert columns(actual) == columns(model)
    assert len(columns(actual)) == 10
    shapes = next(
        c
        for c in actual.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_play_export_snapshot_shapes"
    )
    original = str(shapes.sqltext)
    assert original.count("pg_catalog.jsonb_typeof(") == 2
    shapes.sqltext = text(original.replace("pg_catalog.jsonb_typeof(", "jsonb_typeof("))
    assert current._expected_constraints(actual) == current._expected_constraints(model)
    assert len(actual.constraints) == 5
    expected_indexes = []
    for index in (snapshot_game_index, play_audit_index, event_audit_index):
        assert index.table is not None
        options = {"schema": "public"}
        predicate = index.dialect_options["postgresql"]["where"]
        if predicate is not None:
            options["postgresql_where"] = predicate
        expected_indexes.append(
            (index.name, index.table.name, [c.name for c in index.columns], options)
        )
    assert [
        (n, t, c, {k: str(v) for k, v in kw.items()}) for n, t, c, kw in indexes
    ] == [
        (n, t, c, {k: str(v) for k, v in kw.items()})
        for n, t, c, kw in expected_indexes
    ]
    assert statements == [
        "ALTER TABLE public.play_export_snapshots ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE public.play_export_snapshots FORCE ROW LEVEL SECURITY",
        "REVOKE ALL ON TABLE public.play_export_snapshots FROM PUBLIC,pitchlog_app",
    ]
    assert "pitchlog.db.play_export.models" in all_models.IMPORTED_MODEL_MODULE_NAMES
    with pytest.raises(RuntimeError, match="物理削除"):
        migration["downgrade"]()


def test_whole_profile_keeps_legacy_primitives_and_rejects_export_grant():
    """旧原始値readは全値保持し、未知のPUBLIC表権限を分類で拒否する。"""
    import copy
    import json

    from pitchlog.authz.first_ball_product import _reserved, validate

    asset = json.loads(
        (
            Path(__file__).parents[2] / "contracts/authz/product/ddl-elements.json"
        ).read_text()
    )
    assert validate(asset) is True
    unknown = {
        "acl_id": "ACL:public:play_export_snapshots:PUBLIC",
        "object_kind": "table",
        "object_schema": "public",
        "object_id": "play_export_snapshots",
        "grantee_role_id": "PUBLIC",
        "privilege_ids": ["UPDATE"],
        "grant_option": False,
    }
    assert _reserved(unknown, "acl_expectations") is True
    changed = copy.deepcopy(asset)
    changed["acl_expectations"].append(unknown)
    with pytest.raises(ValueError, match="余剰"):
        validate(changed)
    changed = copy.deepcopy(asset)
    primitive = next(
        row
        for row in changed["functions"]
        if row["function_name"] == "read_play_export_primitives"
    )
    primitive["security_mode"] = "invoker"
    with pytest.raises(ValueError):
        validate(changed)
