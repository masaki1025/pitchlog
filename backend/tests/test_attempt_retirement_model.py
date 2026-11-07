"""0046実migrationの構造をモデルへ移す際に列/制約を落とさない。"""

from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import MetaData, Table
from sqlalchemy.dialects.postgresql import dialect

from pitchlog.db import all_models, current_product_startup
from pitchlog.db.writer_binding.attempt_recovery_models import SyncAttemptRetirement


def test_retirement_model_matches_actual_migration(monkeypatch):
    """別の期待DDLを作らず、実upgradeが宣言する全構造と比較する。"""
    captured = []

    def capture_table(name, *items, **kwargs):
        table = Table(name, MetaData(), *items, **kwargs)
        from pitchlog.db.game_state.models import Game

        cast(Table, Game.__table__).to_metadata(table.metadata)
        captured.append(table)

    import alembic

    monkeypatch.setattr(
        alembic,
        "op",
        SimpleNamespace(
            create_table=capture_table, execute=lambda _: None, get_bind=lambda: None
        ),
    )
    path = (
        Path(__file__).parents[1]
        / "migrations/versions/0046_sync_attempt_retirement.py"
    )
    source = run_path(str(path))
    source["upgrade"].__globals__["_upgrade_existing_functions"] = lambda _: None
    source["upgrade"]()
    assert len(captured) == 1
    actual = captured[0]
    model = SyncAttemptRetirement.__table__
    assert actual.fullname == model.fullname == "sync_fence.attempt_retirements"

    def columns(table: Table) -> list[tuple[Any, ...]]:
        return [
            (
                c.name,
                c.type.compile(dialect=dialect()),
                c.nullable,
                c.default,
                c.server_default,
                c.identity,
                c.computed,
            )
            for c in table.c
        ]

    assert columns(model) == columns(actual)
    assert len(columns(model)) == 11
    assert current_product_startup._expected_constraints(
        model
    ) == current_product_startup._expected_constraints(actual)
    assert not model.indexes and not actual.indexes
    assert model.info == {"append_only": True}
    assert "pitchlog.db.writer_binding.models" in all_models.IMPORTED_MODEL_MODULE_NAMES
    from pitchlog.db.writer_binding import models

    assert models.sync_attempt_retirements is model


@pytest.mark.parametrize("phase", ["pre-full", "full"])
def test_retirement_guards_require_exact_phase(phase):
    """配備前0件・全配備2件だけを受け、部分や無効guardを補修しない。"""
    from contextlib import contextmanager

    full = [
        ("sync_attempt_retirement_immutable", 27, True),
        ("sync_attempt_retirement_no_truncate", 34, True),
    ]

    class Connection:
        def __init__(self, rows):
            self.rows = rows

        @contextmanager
        def cursor(self):
            yield self

        def execute(self, statement):
            assert "pg_catalog.pg_trigger" in statement

        def fetchall(self):
            return self.rows

    valid = [] if phase == "pre-full" else full
    current_product_startup._check_attempt_retirement_guards(Connection(valid), phase)
    bad = [
        full[:1],
        full[1:],
        list(reversed(full)),
        [*full, full[0]],
        [(full[0][0], 19, True), full[1]],
        [(full[0][0], 27, False), full[1]],
        [("unknown", 27, True), full[1]],
        full if phase == "pre-full" else [],
    ]
    for rows in bad:
        with pytest.raises(current_product_startup.CurrentProductStartupError):
            current_product_startup._check_attempt_retirement_guards(
                Connection(rows), phase
            )
    with pytest.raises(current_product_startup.CurrentProductStartupError):
        current_product_startup._check_attempt_retirement_guards(
            Connection(valid), "unknown"
        )


def test_retirement_profile_rejects_extra_policy_for_nonbinding_role():
    """退役表への未知policyもlegacy側へ漏らさず閉じた全集合で拒否する。"""
    import copy
    import json

    from pitchlog.authz.first_ball_product import TABLES, _reserved, validate

    asset_path = Path(__file__).parents[2] / "contracts/authz/product/ddl-elements.json"
    asset = json.loads(asset_path.read_text())
    assert "attempt_retirements" in TABLES
    assert validate(asset) is True
    owner = next(
        row for row in asset["policies"] if row["table_id"] == "attempt_retirements"
    )
    unknown = copy.deepcopy(owner)
    unknown.update(
        policy_id="POLICY:attempt_retirements:unreviewed",
        policy_name="unreviewed",
        role_ids=["pitchlog_app"],
    )
    assert _reserved(unknown, "policies") is True
    asset["policies"].append(unknown)
    with pytest.raises(ValueError, match="余剰"):
        validate(asset)
