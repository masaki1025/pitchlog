"""未登録DB印のmodel/DDL/profile閉検査。実PGの順序/lock成功ではない。"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from pitchlog.authz import first_ball_write_stamp as api
from pitchlog.db import all_models
from pitchlog.sync.control_provider.writer_binding_models import (
    FirstBallWriteAdmission,
    WriterAdmission,
    WriterBinding,
)

_ROOT = Path(__file__).resolve().parents[1]
_GUARD_DIGESTS = {
    "guard_first_ball_projection_lock": (
        "6f56a458e8709ed56c8908252a5cef1cb51864822ca7c26eab03c1df5397dce9"
    ),
    "guard_first_ball_projection_admission": (
        "9bd0dffbde1f502302f8ebdbaab385696806a58ddd25b9eb8fc4e2fdcc2b45ea"
    ),
}
_REVISION = _ROOT / "migrations/versions/0038_first_ball_write_admission.py"


class _Recorder:
    """Alembicを呼ばず静的DDLを捕捉する。"""

    def __init__(self) -> None:
        self.metadata = sa.MetaData()
        self.tables: list[sa.Table] = []
        self.statements: list[str] = []

    def create_table(self, name: str, *items: Any, schema: str) -> None:
        self.tables.append(sa.Table(name, self.metadata, *items, schema=schema))

    def execute(self, sql: str) -> None:
        self.statements.append(sql)


def _revision() -> ModuleType:
    """実候補revisionをcacheからのみ読み込む。"""
    spec = importlib.util.spec_from_file_location(
        "first_ball_stamp_candidate", _REVISION
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _shape(c: sa.Constraint) -> tuple[object, ...]:
    """制約の全属性を比較し、遅延FKを落とさない。"""
    if isinstance(c, sa.CheckConstraint):
        return ("CHECK", c.name, str(c.sqltext))
    if isinstance(c, sa.ForeignKeyConstraint):
        return (
            "FK",
            c.name,
            tuple(e.parent.name for e in c.elements),
            tuple(e.target_fullname for e in c.elements),
            c.match,
            c.ondelete,
            c.deferrable,
            c.initially,
        )
    assert isinstance(c, (sa.PrimaryKeyConstraint, sa.UniqueConstraint))
    return (type(c).__name__, c.name, tuple(col.name for col in c.columns))


def test_model_full_identity_and_nullable_consumption_columns() -> None:
    """既2モデルを再定義せず、全27不変列と4条件更新列を分類する。"""
    all_models
    table = FirstBallWriteAdmission.__table__
    binding = WriterBinding.__table__
    assert isinstance(table, sa.Table) and isinstance(binding, sa.Table)
    assert len(table.c) == 31
    protected = WriterBinding.immutability.protected_columns
    assert len(protected) == 27
    assert FirstBallWriteAdmission.immutability.protected_columns == protected
    assert FirstBallWriteAdmission.immutability.conditional_update_columns == frozenset(
        {
            "state",
            "source_event_id",
            "play_row_id",
            "consumed_at",
        }
    )
    for name in protected:
        assert str(table.c[name].type) == str(binding.c[name].type)
        assert not table.c[name].nullable
    assert [name for name in table.c.keys() if table.c[name].nullable] == [
        "source_event_id",
        "play_row_id",
        "consumed_at",
    ]
    assert not list(table.indexes)
    assert {
        name
        for name in table.c
        if "credential" in name.name or name.name in {"nonce", "proof"}
    } == set()
    assert isinstance(WriterAdmission.__table__, sa.Table)
    assert len(WriterAdmission.__table__.c) == 5
    assert len(binding.c) == 29


def test_static_migration_matches_all_columns_constraints_and_default_deny(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """実upgradeを捕捉し、全列/制約とACL未供給を検査する。"""
    module = _revision()
    recorder = _Recorder()
    monkeypatch.setattr(module, "op", recorder)
    module.upgrade()
    assert module.revision == "0038_first_ball_write_admission"
    assert module.down_revision == "0037_sync_writer_binding"
    assert len(recorder.tables) == 1
    actual, expected = recorder.tables[0], FirstBallWriteAdmission.__table__
    assert isinstance(expected, sa.Table)
    assert [(c.name, str(c.type), c.nullable, c.server_default) for c in actual.c] == [
        (c.name, str(c.type), c.nullable, c.server_default) for c in expected.c
    ]
    assert {_shape(c) for c in actual.constraints} == {
        _shape(c) for c in expected.constraints
    }
    assert recorder.statements == [
        "ALTER TABLE sync_fence.first_ball_write_admissions OWNER TO pitchlog_owner",
        "ALTER TABLE sync_fence.first_ball_write_admissions ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE sync_fence.first_ball_write_admissions FORCE ROW LEVEL SECURITY",
        "REVOKE ALL ON TABLE sync_fence.first_ball_write_admissio"
        "ns FROM PUBLIC, pitchlog_app, pitchlog_sync_binding_acto"
        "r, pitchlog_rg1_control_actor, pitchlog_sync_right_fn_ow"
        "ner",
    ]
    with pytest.raises(RuntimeError, match="履歴は削除できません"):
        module.downgrade()
    sql = str(CreateTable(expected).compile(dialect=postgresql.dialect()))
    assert "DEFERRABLE INITIALLY DEFERRED" in sql
    assert "MATCH SIMPLE" in sql
    assert "CASCADE" not in sql
    assert "CREATE TRIGGER" not in "\n".join(recorder.statements)


def test_closed_state_and_minimum_privilege_contract() -> None:
    """二flag/逆順/終端復活の許可を宣言せず、ownerだけの狭い権限に閉じる。"""
    profile = api.formal_profile()
    api.require_formal(profile)
    assert profile["state_transitions"] == [
        ["absent", "device_true", "device_verified"],
        ["device_verified", "device_true", "device_verified"],
        ["device_verified", "right_true", "right_verified"],
        ["right_verified", "right_true", "right_verified"],
        ["right_verified", "consume", "consumed"],
    ]
    assert profile["terminal_states"] == ["consumed", "invalid"]
    assert profile["roles"] == [] and profile["runtime_registered"] is True
    assert profile["stamp_issuance"] == "STAMPED_BIND_RIGHT"
    assert (
        profile["table"]["force_rls"] is True and profile["table"]["enable_rls"] is True
    )
    assert profile["table"]["physical_delete_allowed"] is False
    assert profile["table"]["truncate_allowed"] is False
    assert all(
        row["grantee"] == "pitchlog_sync_right_fn_owner"
        for row in profile["column_acls"]
    )
    assert all(
        row["privilege"] == "SELECT"
        for row in profile["column_acls"]
        if row["table_id"] != "first_ball_write_admissions"
    )
    assert {row["privilege"] for row in profile["column_acls"]} == {
        "SELECT",
        "INSERT",
        "UPDATE",
    }
    update = next(row for row in profile["column_acls"] if row["privilege"] == "UPDATE")
    assert update["columns"] == [
        "state",
        "source_event_id",
        "play_row_id",
        "consumed_at",
    ]
    insert = next(row for row in profile["column_acls"] if row["privilege"] == "INSERT")
    assert not {"source_event_id", "play_row_id", "consumed_at"} & set(
        insert["columns"]
    )
    assert all(not row["grantable"] for row in profile["column_acls"])
    assert all(
        row["command"] == "SELECT"
        for row in profile["policies"]
        if row["table_id"] != "first_ball_write_admissions"
    )


def test_sql_guard_order_scope_current_conditions_and_consumption() -> None:
    """実PG成功を推定せず、必要SQL述語と権限順を静的に固定する。"""
    profile = api.formal_profile()
    lock, admit = profile["functions"]
    assert [row["security_mode"] for row in profile["functions"]] == [
        "invoker",
        "definer",
    ]
    assert [row["trigger_name"] for row in profile["triggers"]] == [
        "trg_first_ball_10_lock",
        "trg_first_ball_20_admit",
    ]
    for row in profile["functions"]:
        assert row["search_path"] == ["pg_catalog", "pg_temp"]
        assert row["owner_role_id"] == "pitchlog_sync_right_fn_owner"
        assert row["acl_expectations"] == []
        assert "TG_WHEN<>'BEFORE'" in row["sql"] and "TG_LEVEL<>'ROW'" in row["sql"]
        assert (
            "TG_OP<>'INSERT'" in row["sql"]
            and "TG_TABLE_NAME<>'play_rows'" in row["sql"]
        )
        assert "session_user<>'pitchlog_app'" in row["sql"]
        assert "ERRCODE='42501'" in row["sql"]
        assert "set_config" not in row["sql"] and "RAISE NOTICE" not in row["sql"]
        assert "GRANT EXECUTE" not in row["sql"]
    assert lock["sql"].index("FROM public.games") < lock["sql"].index(
        "FROM public.recording_generations"
    )
    assert lock["sql"].count("FOR UPDATE") == 2
    sql = admit["sql"]
    for required in [
        "s.state='right_verified'",
        "b.state='open'",
        "b.transaction_id=own_xid",
        "b.backend_pid=pg_catalog.pg_backend_pid()",
        "b.postmaster_started_at=pg_catalog.pg_postmaster_start_time()",
        "b.expires_at>pg_catalog.clock_timestamp()",
        "s.internal_generation=event_row.generation",
        "a.lease_id=b.lease_id",
        "a.transaction_id=own_xid",
        "FOR UPDATE OF s",
        "a.xmin::text::numeric=pg_catalog.mod",
        "l.source_fingerprint=stamp.event_fingerprint",
        "g.state='open'",
        "g.recovery_generation=stamp.recovery_generation",
        "r.holder_device=stamp.device_id::text",
        "r.revoked_at IS NULL",
        "r.retired_at IS NULL",
        "d.device_id=stamp.device_id AND d.revoked_at IS NULL FOR SHARE",
        "e.event_kind='play_input'",
        "AND NOT e.is_tombstone",
        "e.replaced_at IS NULL",
        "e.import_batch_id IS NULL",
        "NOT e.migration_unverified",
        "SET state='consumed'",
        "RETURNING s.xmin::text INTO row_xmin",
        "row_xmin::numeric<>pg_catalog.mod",
        "play_row_id=NEW.id",
    ]:
        assert required in sql
    assert "request_fingerprint=stamp.event_fingerprint" not in sql
    assert "PERFORM sync_right_api.bind_device" not in sql
    assert "DELETE FROM" not in sql and "TRUNCATE" not in sql
    assert all(
        row["enabled"] == "O" and row["when"] is None and row["events"] == ["INSERT"]
        for row in profile["triggers"]
    )


def test_reflection1_native_scope_and_owner_privileges_are_closed() -> None:
    """native限定3値と、right ownerの実行に要る最小の列権限だけを固定する。"""
    profile = api.formal_profile()
    lock, admit = (row["sql"] for row in profile["functions"])
    for sql in (lock, admit):
        assert "NEW.import_batch_id IS NOT NULL" in sql
        assert "NEW.legacy_row_identifier IS NOT NULL" in sql
        assert "NEW.migration_unverified IS DISTINCT FROM false" in sql
    assert "e.legacy_row_identifier IS NULL AND NOT e.migration_unverified" in admit
    # UPDATE権限のないwriter_bindingsを再lockしない。lockは既assertが保持する。
    binding_read = admit[admit.index("SELECT b.* INTO STRICT binding") :]
    binding_read = binding_read[: binding_read.index(";")]
    assert "FOR SHARE" not in binding_read and "FOR UPDATE" not in binding_read
    code = "\n".join(
        line for line in admit.splitlines() if not line.lstrip().startswith("--")
    )
    # 残るFOR SHAREは既UPDATE(revoked_at)権限のあるtrusted_devicesだけ。
    assert code.count("FOR SHARE") == 1
    assert "d.revoked_at IS NULL FOR SHARE" in code
    assert "FOR UPDATE OF s" in admit
    assert "a.xmin::text::numeric=pg_catalog.mod" in admit
    acl = {
        (row["schema_name"], row["table_id"], row["privilege"]): row["columns"]
        for row in profile["column_acls"]
    }
    assert len(acl) == len(profile["column_acls"])
    # xminは列ACLに書かない(正式catalogはattnum>0だけを突合する)。表単位SELECTで読む。
    assert all("xmin" not in columns for columns in acl.values())
    assert ("sync_fence", "first_ball_write_admissions", "SELECT") not in acl
    assert ("sync_fence", "writer_admissions", "SELECT") not in acl
    assert profile["table_acls"] == [
        {
            "table_id": name,
            "schema_name": "sync_fence",
            "grantee": "pitchlog_sync_right_fn_owner",
            "privilege": "SELECT",
            "grantable": False,
        }
        for name in ("first_ball_write_admissions", "writer_admissions")
    ]
    assert "legacy_row_identifier" in acl[("public", "operation_events", "SELECT")]
    assert acl[("public", "recording_generations", "SELECT")] == ["import_batch_id"]
    assert not [
        key
        for key in acl
        if key[2] != "SELECT" and key[1] != "first_ball_write_admissions"
    ]
    # 既policyのある既表へ新policyを増やさない。
    assert "recording_generations" not in {
        row["table_id"] for row in profile["policies"]
    }


def test_reflection2_consumption_runs_outside_the_exception_subtransaction() -> None:
    """EXCEPTION付きblockはsubtransactionなので、印の書込とxmin照合をその外へ置く。"""
    admit = api.formal_profile()["functions"][1]["sql"]
    code = "\n".join(
        line.strip()
        for line in admit.splitlines()
        if line.strip() and not line.strip().startswith("--")
    )
    assert code.count("EXCEPTION WHEN") == 1
    handler = code.index("EXCEPTION WHEN no_data_found")
    inner_end = code.index("END;", handler)
    update = code.index("UPDATE sync_fence.first_ball_write_admissions")
    xmin_check = code.index("row_xmin::numeric<>pg_catalog.mod")
    # 内側block: 最初のBEGINの直後にもう1つBEGIN、handlerの後にEND;
    assert (
        code.startswith("CREATE FUNCTION")
        and "BEGIN\nBEGIN\nIF TG_TABLE_SCHEMA" in code
    )
    assert handler < inner_end < update < xmin_check
    assert code.count("UPDATE sync_fence.first_ball_write_admissions") == 1
    assert "INTO STRICT row_xmin" not in code
    assert "IF NOT FOUND OR row_xmin IS NULL" in code
    # 外側の終端は例外節なしのEND。
    assert code.rstrip().endswith(
        "FROM PUBLIC, pitchlog_app, pitchlog_sync_binding_actor, "
        "pitchlog_rg1_control_actor;"
    )
    tail = code[xmin_check:]
    assert "EXCEPTION WHEN" not in tail


def test_reflection2_guard_bodies_are_pinned_by_digest() -> None:
    """部分文字列照合では見えない述語の中和も、本文digestの固定で検出する。"""
    digests = {
        row["function_name"]: row["sql_sha256"]
        for row in api.formal_profile()["functions"]
    }
    assert digests == _GUARD_DIGESTS


def _leaves(value: Any, path: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    if isinstance(value, dict):
        return [p for key, item in value.items() for p in _leaves(item, (*path, key))]
    if isinstance(value, list) and value:
        return [
            p for key, item in enumerate(value) for p in _leaves(item, (*path, key))
        ]
    return [path]


@pytest.mark.parametrize("path", _leaves(api.formal_profile()))
def test_every_profile_leaf_mutation_is_rejected(path: tuple[Any, ...]) -> None:
    """各body/属性/ACL/政策/状態の変更を全値比較で拒否する。"""
    profile = api.formal_profile()
    cursor = profile
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = "tampered-secret-marker"
    with pytest.raises(ValueError, match="^初球書込印の閉profileが不一致$") as error:
        api.require_formal(profile)
    assert "tampered-secret-marker" not in str(error.value)
    assert error.value.__cause__ is None


@pytest.mark.parametrize("key", list(api.formal_profile()))
@pytest.mark.parametrize("mode", ["missing", "extra"])
def test_top_level_missing_extra_reject(key: str, mode: str) -> None:
    """最上位の未知/欠落を無視しない。"""
    profile = copy.deepcopy(api.formal_profile())
    if mode == "missing":
        del profile[key]
    else:
        profile["unknown-" + key] = True
    with pytest.raises(ValueError):
        api.require_formal(profile)


@pytest.mark.parametrize("value", [None, 1, False, (), {"runtime_registered": 0}])
def test_profile_requires_exact_json_types(value: object) -> None:
    """JSON型違いを強制変換しない。"""
    with pytest.raises(ValueError):
        api.require_formal(value)


def test_formal_metadata_has_exact_column_and_table_acl_union() -> None:
    """xminを列ACLに出さず、state権限の和集合を単一の列行へ写す。"""
    rows = api.formal_declarations()
    assert {key: len(value) for key, value in rows.items()} == {
        "functions": 2,
        "policies": 5,
        "acl_expectations": 2,
        "column_acl_expectations": 83,
    }
    assert all(row["column_id"] != "xmin" for row in rows["column_acl_expectations"])
    state = [
        row
        for row in rows["column_acl_expectations"]
        if row["object_id"] == "first_ball_write_admissions"
        and row["column_id"] == "state"
    ]
    assert len(state) == 1 and state[0]["privilege_ids"] == ["INSERT", "UPDATE"]
    assert {row["object_id"] for row in rows["acl_expectations"]} == {
        "first_ball_write_admissions",
        "writer_admissions",
    }
    assert all(
        row["privilege_ids"] == ["SELECT"] and row["grant_option"] is False
        for row in rows["acl_expectations"]
    )


def test_invoker_is_last_and_is_the_only_trigger_creation_point() -> None:
    """既definer→invoker順を変えず両guardの定義後にだけtriggerを配置する。"""
    bodies = api.formal_function_bodies()
    lock = bodies["FUNCTION:sync_right_api:guard_first_ball_projection_lock()"]
    admit = bodies["FUNCTION:sync_right_api:guard_first_ball_projection_admission()"]
    assert lock.count("CREATE TRIGGER") == 2
    assert "CREATE TRIGGER" not in admit
    assert lock.index("$stamp$;") < lock.index("CREATE TRIGGER trg_first_ball_10_lock")
    assert lock.index("CREATE TRIGGER trg_first_ball_10_lock") < lock.index(
        "CREATE TRIGGER trg_first_ball_20_admit"
    )
    assert (
        api.stamp_trigger_expectations()[2][0]
        == "trg_play_rows_projection_identity_immutable"
    )
    check = api.stamp_trigger_reapply_check()
    assert "jsonb_agg(r.value ORDER BY r.value->>0)" in check
    assert (
        "NOT t.tgisinternal" in check
        and "first ball projection trigger definition collision" in check
    )
