"""閉ABI/終結比較/能力分離。純比較は実DBの証拠と区別する。"""

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID

import pytest

from pitchlog.durable_rights_ledger.adapter import (
    LedgerUnavailable,
    _authorize_operation,
)
from pitchlog.durable_rights_ledger.authority import (
    AuthorityUnavailable,
    _validate_binding_config,
)
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    build_function_registry,
    decode_function_result,
    prepare_function_operation,
)
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.repositories.writer_binding import (
    _UNREGISTERED_DECLARATIONS,
    _AssertWriterBindingToken,
)
from pitchlog.sync.control_provider.binding_control import (
    BindingOutcome,
    _BindingAuthority,
    _classify_observation,
    _writer_from_wire,
)
from pitchlog.sync.control_provider.writer_binding import (
    WriterBindingUnavailable,
    WriterIdentity,
    _issue_live_writer_binding,
    _LiveWriterBinding,
)

# 反映1の21対向候補172c8501を固定。実DB結果ではない。
_CASES = [
    (
        "publish_unasserted_outer_live",
        True,
        True,
        0,
        0,
        "in progress",
        "ENTRY_CLOSED_UNADMITTED",
    ),
    ("top_level_admission_commit", True, True, 1, 1, "committed", "COMMITTED"),
    (
        "committed_admission_status_retention_expired",
        True,
        True,
        1,
        1,
        None,
        "COMMITTED",
    ),
    (
        "top_level_admission_outer_abort",
        True,
        True,
        0,
        0,
        "aborted",
        "ROLLBACK_CONFIRMED",
    ),
    ("assert_reply_lost_then_committed", True, True, 1, 1, "committed", "COMMITTED"),
    (
        "assert_reply_lost_then_aborted",
        True,
        True,
        0,
        0,
        "aborted",
        "ROLLBACK_CONFIRMED",
    ),
    ("assert_reply_lost_no_admission_status_null", True, True, 0, 0, None, "UNKNOWN"),
    (
        "savepoint_rejected_outer_live",
        True,
        True,
        0,
        0,
        "in progress",
        "ENTRY_CLOSED_UNADMITTED",
    ),
    (
        "savepoint_rejected_then_outer_aborted",
        True,
        True,
        0,
        0,
        "aborted",
        "ROLLBACK_CONFIRMED",
    ),
    (
        "unasserted_outer_committed",
        True,
        True,
        0,
        0,
        "committed",
        "ENTRY_CLOSED_UNADMITTED",
    ),
    ("business_close_commit_reply_lost", True, False, 1, 1, "committed", "UNKNOWN"),
    ("drain_timeout_old_writer_live", True, False, 0, 0, "in progress", "UNKNOWN"),
    ("authority_restart_no_recent_status", True, True, 0, 0, None, "UNKNOWN"),
    (
        "authority_restart_same_binding_committed",
        True,
        True,
        1,
        1,
        "committed",
        "COMMITTED",
    ),
    ("authority_restart_other_instance", False, True, 1, 1, "committed", "UNKNOWN"),
    ("caller_claimed_admitted_status_null", True, True, 0, 0, None, "UNKNOWN"),
    ("other_lease_admission", True, True, 1, 0, "committed", "UNKNOWN"),
    ("admission_status_contradiction", True, True, 1, 1, "aborted", "UNKNOWN"),
    ("duplicate_admission", True, True, 2, 2, "committed", "UNKNOWN"),
    (
        "committed_observation_terminal_append_unknown",
        True,
        True,
        1,
        1,
        "committed",
        "COMMITTED",
    ),
    (
        "terminal_durable_lease_close_reply_lost",
        True,
        True,
        1,
        1,
        "committed",
        "COMMITTED",
    ),
]


@pytest.mark.parametrize(
    "name,identity,closed,count,matching,status,expected",
    _CASES,
    ids=[r[0] for r in _CASES],
)
def test_closed_observation(name, identity, closed, count, matching, status, expected):
    """未assert/NULL/close不明をrollbackへ昇格しない。"""
    assert len(_CASES) == 21
    assert _classify_observation(
        closed=closed,
        identity_valid=identity,
        admissions=count,
        matching=matching,
        xid_status=status,
    ) == BindingOutcome(expected)


def _writer():
    """実証でない純型検査値。"""
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    return WriterIdentity("123", "16384", now, 23, now, "18446744073709551615")


@pytest.mark.parametrize(
    "xid", ["0", "01", "-1", "18446744073709551616", True, 1, None]
)
def test_xid8_rejects_noncanonical_values(xid):
    """全64bitを文字列のまま扱い、符号/型を補正しない。"""
    with pytest.raises(WriterBindingUnavailable):
        replace(_writer(), transaction_id=xid)


def test_xid8_roundtrip_and_private_issuer():
    """scalarだけでprivate資格を発行しない。"""
    assert _writer_from_wire(_writer().wire()) == _writer()
    with pytest.raises(WriterBindingUnavailable):
        _LiveWriterBinding(None, None, _writer(), cast(Any, None), object())


@pytest.mark.parametrize(
    "change",
    [
        {"backend_pid": True},
        {"extra": "x"},
        {"transaction_id": 1},
        {"postmaster_started_at": "2026-10-27"},
    ],
)
def test_writer_wire_closed(change):
    """任意JSONをwriterの証明にしない。"""
    with pytest.raises(WriterBindingUnavailable):
        _writer_from_wire(_writer().wire() | change)


def test_exact_declarations():
    """新2関数だけ。登録/秘密長/戻りNULLの境界を維持する。"""
    registry = build_function_registry(_UNREGISTERED_DECLARATIONS, frozenset())
    token = _AssertWriterBindingToken(
        UUID(int=1), UUID(int=2), b"n" * 32, UUID(int=3), UUID(int=4)
    )
    assert (
        prepare_function_operation(token, UUID(int=5), registry)[1]["binding_nonce"]
        == b"n" * 32
    )
    assert "nnnn" not in repr(token)
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(token, UUID(int=5), {})
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(
            replace(token, binding_nonce=b"n" * 31), UUID(int=5), registry
        )
    result = TenantOperationResult(((None,),))
    assert decode_function_result(_UNREGISTERED_DECLARATIONS[1], result) == result
    with pytest.raises(FunctionOperationError):
        replace(
            _UNREGISTERED_DECLARATIONS[1], function_id="other.assert_writer_binding"
        )


@pytest.mark.parametrize(
    "op",
    [
        "epoch",
        "reserve",
        "claim",
        "fence_open",
        "fresh_activation_open",
        "binding_close",
    ],
)
def test_binding_peer_denies_other_capabilities(op):
    """専用peerから既能力へ到達させない。"""
    with pytest.raises(LedgerUnavailable):
        _authorize_operation("sync_binding", op)


@pytest.mark.parametrize("role", ["generation", "fresh_controller"])
def test_legacy_peer_cannot_open_binding(role):
    """旧peerのnonce権限を拡張しない。"""
    with pytest.raises(LedgerUnavailable):
        _authorize_operation(role, "binding_open")
    _authorize_operation("sync_binding", "binding_open")


def _config():
    """非秘密の新profile検査値。"""
    return {
        "binding_business_dsn": (
            "host=/owned/business dbname=test user=pitchlog_sync_binding_actor"
        ),
        "binding_control_dsn": (
            "host=/owned/control dbname=test user=pitchlog_sync_binding_actor"
        ),
        "binding_authority": {
            "control_instance": str(UUID(int=1)),
            "business_instance": str(UUID(int=2)),
            "restore_epoch": str(UUID(int=3)),
            "control_version": 1,
        },
    }


@pytest.mark.parametrize(
    "dsn",
    [
        "host=localhost dbname=test user=pitchlog_sync_binding_actor",
        "host=/owned dbname=test user=pitchlog_app",
        "host=/owned dbname=test user=pitchlog_sync_binding_actor password=forbidden",
        "host=/a,/b dbname=test user=pitchlog_sync_binding_actor",
    ],
)
def test_new_config_rejects_general_roles_and_secrets(dsn):
    """専用actor/Unix非秘密接続だけを設定として受理する。"""
    config = _config()
    _validate_binding_config(config)
    config["binding_business_dsn"] = dsn
    with pytest.raises(AuthorityUnavailable):
        _validate_binding_config(config)


def test_close_failure_is_unknown(monkeypatch):
    """closeの応答不明はcaller ACKで補わない。実DB故障結果ではない。"""
    authority = _BindingAuthority({}, UUID(int=1))
    calls = []
    record = {
        n: str(UUID(int=i + 1))
        for i, n in enumerate(
            ("tenant_id", "attempt_id", "phase_id", "lease_id", "close_id")
        )
    }

    def call(which, statement, params, *, write=False):
        calls.append((statement, write))
        raise OSError("comparison only")

    monkeypatch.setattr(authority, "_call", call)
    assert authority.resolve(record) == BindingOutcome.UNKNOWN
    assert len(calls) == 1 and calls[0][1] is True


def test_fake_writer_handle_does_not_issue_capability():
    """構造が似たhandleやscalar leaseから実資格を作らない。"""
    with pytest.raises(WriterBindingUnavailable):
        _issue_live_writer_binding(object(), cast(Any, object()))


@pytest.mark.parametrize("value", [True, False, 0, "", ()])
def test_assert_void_response_cannot_be_synthetic_success(value):
    """固定assertのvoidをbool等の代替成功応答へ拡張しない。"""
    with pytest.raises(FunctionOperationError):
        decode_function_result(
            _UNREGISTERED_DECLARATIONS[1], TenantOperationResult(((value,),))
        )


def _control_sql() -> str:
    """制御PGの実供給SQLを読み、DB実行の代替としない。"""
    from pathlib import Path

    return (
        Path(__file__).resolve().parents[1]
        / "src/pitchlog/sync/control_provider/sql/writer-binding-control.sql"
    ).read_text()


def _assert_closed_control_role_guard(source: str) -> None:
    """GRANT前のexact2role/属性/双方向edge検査を静的に凍結する。"""
    import re

    prefix, suffix = source.split("GRANT USAGE", 1)
    guard = re.sub(r"\s+", " ", prefix)
    assert (
        "FOREACH role_name IN ARRAY ARRAY['pitchlog_sync_binding_fn_owner',"
        "'pitchlog_sync_binding_actor'] LOOP" in guard
    )
    assert "actor:=role_name='pitchlog_sync_binding_actor';" in guard
    assert "SELECT * INTO r FROM pg_roles WHERE rolname=role_name;" in guard
    assert "IF NOT FOUND THEN" in guard
    for role, login in (
        ("pitchlog_sync_binding_actor", "LOGIN"),
        ("pitchlog_sync_binding_fn_owner", "NOLOGIN"),
    ):
        assert (
            f"CREATE ROLE {role} {login} NOSUPERUSER NOINHERIT NOBYPASSRLS "
            "NOCREATEROLE NOCREATEDB NOREPLICATION;" in guard
        )
    expected = (
        "ELSIF r.rolcanlogin IS DISTINCT FROM actor OR r.rolsuper OR r.rolinherit "
        "OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication "
        "OR r.rolconnlimit<>-1 OR r.rolvaliduntil IS NOT NULL "
        "OR EXISTS(SELECT FROM pg_auth_members m WHERE m.member=r.oid "
        "OR m.roleid=r.oid) THEN RAISE EXCEPTION "
        "'binding control role configuration rejected' USING ERRCODE='42501'; END IF;"
    )
    assert expected in guard
    assert "END LOOP; END;$roles$;" in guard
    assert re.search(r"\bALTER\s+ROLE\b", source, re.IGNORECASE) is None
    assert "TO pitchlog_sync_binding_actor,pitchlog_sync_binding_fn_owner;" in suffix


def test_control_existing_roles_are_exactly_guarded_before_grant():
    """未存在CREATE/正常既roleの経路を保ち、危険な既roleは先に拒否する構造。"""
    _assert_closed_control_role_guard(_control_sql())


@pytest.mark.parametrize(
    "fragment",
    [
        "r.rolcanlogin IS DISTINCT FROM actor",
        "r.rolsuper",
        "r.rolinherit",
        "r.rolbypassrls",
        "r.rolcreaterole",
        "r.rolcreatedb",
        "r.rolreplication",
        "r.rolconnlimit<>-1",
        "r.rolvaliduntil IS NOT NULL",
        "m.member=r.oid",
        "m.roleid=r.oid",
    ],
)
def test_control_role_guard_static_counterexamples_are_detected(fragment):
    """属性・edge片側を削った旧反例を静的検査が拒否する。実PG結果ではない。"""
    source = _control_sql()
    assert fragment in source
    with pytest.raises(AssertionError):
        _assert_closed_control_role_guard(source.replace(fragment, "false", 1))


@pytest.mark.parametrize(
    "old,new",
    [
        (
            "'pitchlog_sync_binding_fn_owner','pitchlog_sync_binding_actor'",
            "'pitchlog_sync_binding_actor'",
        ),
        (
            "actor:=role_name='pitchlog_sync_binding_actor'",
            "actor:=role_name='pitchlog_sync_binding_fn_owner'",
        ),
        (
            "IF NOT FOUND THEN",
            "IF NOT FOUND THEN ALTER ROLE pitchlog_sync_binding_actor LOGIN;",
        ),
    ],
)
def test_control_guard_rejects_owner_omission_login_inversion_and_repair(old, new):
    """owner未検査/LOGIN逆転/勝手なALTER修復を対向で保持する。"""
    source = _control_sql()
    assert old in source
    with pytest.raises(AssertionError):
        _assert_closed_control_role_guard(source.replace(old, new, 1))


# 以下は実DB成功ではなく、OID2278の実driver loader→SQLAlchemy→既decoderの純境界。
def _void_result_processor():
    """実行時と同じcompiled result metadataからprocessorを取得する。"""
    from sqlalchemy.dialects import postgresql

    registration = _UNREGISTERED_DECLARATIONS[1]
    dialect = postgresql.dialect()
    compiled = registration.statement.compile(dialect=dialect)
    return compiled._result_columns[0].type._cached_result_processor(dialect, 2278)


def test_void_driver_text_loader_to_existing_decoder():
    """実TEXT loaderの空文字だけを内部NULLへ変え既decoderを通す。"""
    from psycopg.adapt import Transformer
    from psycopg.pq import Format
    from sqlalchemy.sql.sqltypes import NullType
    from sqlalchemy.sql.type_api import TypeDecorator

    loader = Transformer().get_loader(2278, Format.TEXT)
    raw = loader.load(b"")
    assert type(raw) is str and raw == ""
    spec = _UNREGISTERED_DECLARATIONS[1]
    selected = tuple(spec.statement.selected_columns)[0]
    assert isinstance(selected.type, TypeDecorator)
    assert type(selected.type.impl) is NullType
    assert selected.type.cache_ok is True
    processor = _void_result_processor()
    assert processor is not None
    normalized = processor(raw)
    assert normalized is None
    result = TenantOperationResult(((normalized,),))
    assert decode_function_result(spec, result) is result
    # 旧None fixtureは内部値だけ。driverのNoneを正常応答とは扱わない。
    with pytest.raises(FunctionOperationError):
        processor(None)


class _VoidStringSubclass(str):
    """同値のstr派生型もdriverのexact strには含めない。"""


@pytest.mark.parametrize(
    "raw",
    [
        None,
        True,
        False,
        0,
        1,
        0.0,
        "x",
        b"",
        b"private",
        bytearray(),
        memoryview(b""),
        [],
        {},
        _VoidStringSubclass(""),
    ],
)
def test_void_result_processor_rejects_noncanonical_values_without_echo(raw):
    """欠落/偽成功/byte列等は一定の秘匿エラーで拒否する。"""
    processor = _void_result_processor()
    assert processor is not None
    with pytest.raises(FunctionOperationError) as caught:
        processor(raw)
    assert str(caught.value) == "writer assertのdriver応答が不一致"


@pytest.mark.parametrize("raw", ["", True, False, 0, 1, b""])
def test_void_existing_decoder_is_not_widened(raw):
    """正規化を迂回した元decoderは従来どおりNone以外を拒否する。"""
    with pytest.raises(FunctionOperationError):
        decode_function_result(
            _UNREGISTERED_DECLARATIONS[1], TenantOperationResult(((raw,),))
        )


def test_void_statement_sql_bind_signature_and_result_contract_unchanged():
    """SQL/六bind型順序/戻り宣言を全値固定し型adapterだけを許可する。"""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.sql.sqltypes import LargeBinary, Uuid

    spec = _UNREGISTERED_DECLARATIONS[1]
    compiled = spec.statement.compile(dialect=postgresql.dialect())
    assert str(compiled) == (
        "SELECT sync_fence_api.assert_writer_binding(%(tenant_id)s::UUID, "
        "%(attempt_id)s::UUID, %(phase_id)s::UUID, %(binding_nonce)s, "
        "%(device_id)s::UUID, %(game_id)s::UUID) AS asserted"
    )
    assert tuple(compiled.params) == (
        "tenant_id",
        "attempt_id",
        "phase_id",
        "binding_nonce",
        "device_id",
        "game_id",
    )
    assert tuple(type(compiled.binds[k].type) for k in compiled.params) == (
        Uuid,
        Uuid,
        Uuid,
        LargeBinary,
        Uuid,
        Uuid,
    )
    assert spec.result_fields == (("asserted", bool),)
    assert spec.nullable_results == ("asserted",)
    assert spec.aware_datetime_results == ()
    assert (spec.min_rows, spec.max_rows) == (1, 1)


def test_void_caller_result_type_is_discarded_by_canonical_rebuild():
    """callerの型processorを再構築に持ち込まず固定adapterだけを使う。"""
    from sqlalchemy import select
    from sqlalchemy.sql.functions import Function
    from sqlalchemy.sql.sqltypes import NullType
    from sqlalchemy.sql.type_api import TypeDecorator

    class CallerType(TypeDecorator):
        """呼出側が挿入しようとする偽の結果型。"""

        impl = NullType
        cache_ok = True

        def process_result_value(self, value, dialect):
            """このprocessorが実行されたら検査を失敗させる。"""
            raise AssertionError("caller processor must never execute")

    original = _UNREGISTERED_DECLARATIONS[1]
    function = tuple(original.statement.selected_columns)[0].element
    unsafe = select(
        Function(
            "assert_writer_binding",
            *tuple(function.clauses),
            packagenames=("sync_fence_api",),
            type_=CallerType(),
        ).label("asserted")
    )
    rebuilt = replace(original, statement=unsafe)
    selected = tuple(rebuilt.statement.selected_columns)[0]
    assert type(selected.type) is type(
        tuple(original.statement.selected_columns)[0].type
    )
    assert not isinstance(selected.type, CallerType)
    from sqlalchemy.dialects import postgresql

    processor = selected.type._cached_result_processor(postgresql.dialect(), 2278)
    assert processor is not None and processor("") is None


def test_void_adapter_preserves_every_other_registered_function():
    """既全関数のSQL/bind/選択型/processor欠如を実before全値へ束縛する。"""
    import hashlib
    import json

    from sqlalchemy.dialects import postgresql

    from pitchlog.repositories.first_ball import _UNREGISTERED_DECLARATIONS as right
    from pitchlog.repositories.initial_recording_right import (
        _ALL_INITIAL_REGISTRATIONS,
        _INITIAL_ENROLL_FUNCTION_OPERATIONS,
        _INITIAL_RESOLVE_FUNCTION_OPERATIONS,
    )
    from pitchlog.repositories.operation_registry import PRODUCT_FUNCTION_OPERATIONS

    expected = {
        "RG1:precheck": (
            "cd36c04857da91f506e29414e5bf0bb07d4b7c6b2826ccf97be1bb123823051c"
        ),
        "RG1:commit_check": (
            "c6a149e5bce9efc167b60642f4dc536445f711e0a537dde3f49fd03b2a1f0c75"
        ),
        "RG1:scope_binding": (
            "0f4af18080ce42056c5f7d66fa7c9bbac42179d5c410e5613377d7be37a5e5db"
        ),
        "RULE:resolve_stage_a": (
            "d3a2465260b7380558ee8f362866c69207b35d5556118242610f41039f56eef5"
        ),
        "INITIAL_RIGHT:lock_device": (
            "aced3e0bc2fd3095caa500564e95d49e1b09f0e1a64d4e09477f09e1e69850e6"
        ),
        "INITIAL_RIGHT:read_existing_start": (
            "ce6742722c0572b1a158f97c8840baec9cb1398ac3bfa7c9273ff0ac7b2ab9eb"
        ),
        "INITIAL_RIGHT:read_start_game": (
            "fe9fd82c90394114e326b54234ee8a176883eafbed9b708f51efcf4132a31171"
        ),
        "INITIAL_RIGHT:lock_preparing_game": (
            "a608825e1ba4981cf0f59698410fb3d81efb4ce7acaae4cb81446fbbf24b9c6d"
        ),
        "INITIAL_RIGHT:lock_current_start": (
            "71948d14b70b2d85d5b49329dfad22f3edd4bb4ac164ff15182c15b3e7bb89a9"
        ),
        "INITIAL_RIGHT:check_business_epoch": (
            "b298e0d985736f4230d6d55d9d1454b59dcaa7f75411c1ad0daeb3639fda09b2"
        ),
        "INITIAL_RIGHT:insert_initial_grant": (
            "df0403f96f7adb136977cbb4463a0e04aa4cf71ac010bbfec8954eda389dc0a4"
        ),
        "INITIAL_RIGHT:begin_start_attempt": (
            "958edd7069e0055f9908016186c4aa142f9fbe3f98d214fb6795338eb4b7202c"
        ),
        "INITIAL_RIGHT:resolve_start_attempt": (
            "8112937671d5c575b4cb091708d734e425ebada4ca4e3ecf5b11f0de20f0b88f"
        ),
        "INITIAL_RIGHT:read_initial_start_context": (
            "2bcb2a0d5f9849a258a9c190170f83cb1b2eaa12b6c9f1ccddf337138b5e712b"
        ),
        "INITIAL_RIGHT:persist_initial_start": (
            "bdf1d6879538fd537913bc371e44059ac8eb9f389ed2489a24b89af2d8bc27bb"
        ),
        "INITIAL_RIGHT:enroll_device": (
            "0ff335f54a8dc6d749432ca057d707c8873d7434f9d8f06daa57577d4481fc49"
        ),
        "INITIAL_RIGHT:lookup_existing_start_attempt": (
            "fc58b83f41a47046d7ae690198d51998e28b20afe739c51126b7109cdaa9a6a4"
        ),
        "SYNC_FIRST_BALL:bind_device": (
            "15c3702e4e5390b856669ea1ffd49343b9a1769e324f501daec593c876a2e96e"
        ),
        "SYNC_FIRST_BALL:check_current_right": (
            "d0790dd944798534a8df3d2079aa438e7d3307d0de9acb654c2fd7e874ae8704"
        ),
        "SYNC_FIRST_BALL:read_device_state": (
            "281792f9b426c1fdc7eba3305c069f5fd3afcde268a367fc06583bc006652e71"
        ),
        "SYNC_WRITER_BINDING:read_writer_identity": (
            "4122d688347d16207dbe0129eee860404763b4c2f3fa6dd4ef52d3a20fa74169"
        ),
    }
    expected.update(
        {
            "SYNC_ORDINARY_PITCH:read_ordinary_order_summary": (
                "9fe964ac9acdc55affd49aeec9af7e5bfdf9d7423cb7f40e05964ce04901ae0a"
            ),
            "SYNC_ORDINARY_PITCH:bind_ordinary_device": (
                "62979ada626c6a44ba564a67b172c82592939c0add19aa32c5c9b9aa1f71ba8f"
            ),
            "SYNC_ORDINARY_PITCH:check_ordinary_right": (
                "81a812e044a95a1da0ec1032e269f6bd9a8748a0267376577629790a5362d901"
            ),
            "SYNC_ORDINARY_PITCH:prepare_ordinary_projection": (
                "8fea7cdc1033a5db6bce8b5e4a96b8d5b4ddddba57b76b6709c3520c88bcc313"
            ),
            "SYNC_ORDINARY_PITCH:read_ordinary_checkpoint": (
                "fe353fa7741a11b5654f7a0ddab87faf1138fc45ea67c527c591202221fb7d2c"
            ),
            "SYNC_ORDINARY_PITCH:lock_ordinary_checkpoint": (
                "9109e453e8aa0cc6011444c735d5d59a4b73a3abfce6725558d298abf797fdee"
            ),
            "SYNC_ORDINARY_PITCH:read_ordinary_history_page": (
                "3e80687f6ebbf0f09c830534fa40e5a78ccb3fea4cd5d1b0396a2ab59a05494d"
            ),
        }
    )
    dialect = postgresql.dialect()
    actual = {}
    registrations = (
        *PRODUCT_FUNCTION_OPERATIONS,
        *_ALL_INITIAL_REGISTRATIONS,
        *_INITIAL_ENROLL_FUNCTION_OPERATIONS,
        *_INITIAL_RESOLVE_FUNCTION_OPERATIONS,
        *right,
        *_UNREGISTERED_DECLARATIONS,
    )
    for spec in registrations:
        if spec.function_id == "sync_fence_api.assert_writer_binding":
            continue
        compiled = spec.statement.compile(dialect=dialect)
        row = {
            "function_id": spec.function_id,
            "operation_id": spec.operation_id,
            "sql": str(compiled),
            "bind": [
                (k, type(compiled.binds[k].type).__name__, str(compiled.binds[k].type))
                for k in compiled.params
            ],
            "selected": [
                (
                    x.name,
                    type(x.type).__name__,
                    str(x.type),
                    x.type._cached_result_processor(dialect, 2278) is None,
                )
                for x in spec.statement.selected_columns
            ],
        }
        digest = hashlib.sha256(
            json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        assert actual.get(spec.operation_id, digest) == digest
        actual[spec.operation_id] = digest
    assert actual == expected


@pytest.mark.parametrize(
    "field",
    (
        None,
        "request_fingerprint",
        "event_fingerprint",
        "device_id",
        "tenant_id",
        "game_id",
        "wire_d4",
        "codec_version",
        "position",
        "d1",
        "event_count",
    ),
)
def test_rpc_phase_snapshot_rejects_later_mutation(field):
    """送信後のphase差替えを純比較する。真正lease/DBの実証ではない。"""
    import json
    from datetime import timedelta

    from pitchlog.sync.control_provider.binding_control import (
        _LEASE_CREATION,
        BindingControl,
        _BindingLease,
        _phase_wire,
    )
    from pitchlog.sync.control_provider.evidence import (
        AttemptBinding,
        AuthorityBinding,
        EventPhaseBinding,
    )

    attempt = AttemptBinding(
        AuthorityBinding(UUID(int=1), UUID(int=2), UUID(int=3)),
        UUID(int=4),
        UUID(int=5),
        UUID(int=6),
        "generation-A",
        1,
        UUID(int=7),
        1,
        "wire-request-v1:" + "a" * 64,
        1,
    )
    phase = EventPhaseBinding(
        attempt, UUID(int=8), 1, 1, UUID(int=9), "wire-v1:" + "b" * 64
    )
    snapshot = json.dumps(
        {
            "tenant_id": str(attempt.tenant_id),
            "phase": _phase_wire(phase, UUID(int=10), 1),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    if field is not None:
        value = (
            2
            if field in ("codec_version", "position", "d1", "event_count")
            else UUID(int=20)
            if field.endswith("_id")
            else "other-value"
        )
        object.__setattr__(
            phase if field in ("event_fingerprint", "position", "d1") else attempt,
            field,
            value,
        )
    stamp = datetime.now(timezone.utc)
    identity = WriterIdentity("1", "1", stamp, 1, stamp, "1")
    reply = {
        "nonce": "01" * 32,
        "lease_id": str(UUID(int=11)),
        "expires_at": (stamp + timedelta(seconds=30)).isoformat(),
    }
    control = object.__new__(BindingControl)
    if field is None:
        lease = _BindingLease(
            control,
            None,
            None,
            phase,
            identity,
            reply,
            _LEASE_CREATION,
            phase_snapshot=snapshot,
        )
        assert lease._phase_snapshot == snapshot
    else:
        with pytest.raises(WriterBindingUnavailable):
            _BindingLease(
                control,
                None,
                None,
                phase,
                identity,
                reply,
                _LEASE_CREATION,
                phase_snapshot=snapshot,
            )


@pytest.mark.parametrize(
    "change",
    (
        None,
        "request_hash",
        "event_hash",
        "position",
        "game",
        "device",
        "codec",
        "epoch",
        "snapshot",
        "handle",
        "registry",
    ),
)
def test_pure_actual_phase_source_comparison_no_real_lease(monkeypatch, change):
    """私有registry doubleの比較試験。認証・PG・実leaseの成立ではない。"""
    import json
    from types import SimpleNamespace

    import test_sync_apply_source_binding as source_test

    from pitchlog.sync import source_binding as source
    from pitchlog.sync.control_provider import writer_binding as writer
    from pitchlog.sync.control_provider.binding_control import _phase_wire
    from pitchlog.sync.control_provider.evidence import (
        AttemptBinding,
        AuthorityBinding,
        EventPhaseBinding,
    )

    receipt, request = source_test._receipt_double(source_test._raw())
    state = source._RECEIPTS[receipt]
    binding = source.e1_event_source(receipt, 1)
    assert type(request.d4) is str and type(request.events[0].d1) is int
    phase = EventPhaseBinding(
        AttemptBinding(
            AuthorityBinding(UUID(int=1), UUID(int=2), UUID(int=3)),
            state.tenant_id,
            UUID(int=5),
            UUID(request.game_id),
            request.d4,
            1,
            UUID(int=7),
            1,
            state.source.request_fingerprint,
            1,
        ),
        UUID(int=8),
        1,
        request.events[0].d1,
        UUID(request.events[0].d5),
        state.source.event_fingerprints[0],
    )
    snapshot = json.dumps(
        {
            "tenant_id": str(state.tenant_id),
            "phase": _phase_wire(phase, UUID(int=10), 1),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    bound = object.__new__(writer._LiveWriterBinding)
    bound._used = False
    bound._owner = (object(),)
    bound._handle = SimpleNamespace(_context=state.context)
    bound._lease = cast(Any, SimpleNamespace(_phase_snapshot=snapshot))
    bound._phase_snapshot = snapshot
    writer._LIVE_BINDINGS[bound._owner[0]] = bound
    calls = []
    monkeypatch.setattr(
        writer._LiveWriterBinding,
        "assert_current",
        lambda self: calls.append("current"),
    )
    try:
        if change in ("request_hash", "device", "game", "codec"):
            name, value = {
                "request_hash": ("request_fingerprint", "wire-request-v1:wrong"),
                "device": ("device_id", UUID(int=20)),
                "game": ("game_id", UUID(int=20)),
                "codec": ("codec_version", 2),
            }[change]
            object.__setattr__(phase.attempt, name, value)
        elif change == "event_hash":
            object.__setattr__(phase, "event_fingerprint", "wire-v1:wrong")
        elif change == "position":
            object.__setattr__(phase, "position", 2)
        elif change == "epoch":
            object.__setattr__(phase.attempt.authority, "restore_epoch", UUID(int=20))
        elif change == "snapshot":
            bound._lease._phase_snapshot = "{}"
        elif change == "handle":
            bound._handle._context = object()
        elif change == "registry":
            del writer._LIVE_BINDINGS[bound._owner[0]]
        if change is None:
            actual = bound.assert_event_source(
                binding,
                context=state.context,
                request=request,
                event=request.events[0],
                phase=phase,
            )
            assert actual.event_fingerprint == state.source.event_fingerprints[0]
            assert calls == ["current", "current"]
        else:
            with pytest.raises(WriterBindingUnavailable):
                bound.assert_event_source(
                    binding,
                    context=state.context,
                    request=request,
                    event=request.events[0],
                    phase=phase,
                )
    finally:
        writer._LIVE_BINDINGS.pop(bound._owner[0], None)
        source._RECEIPTS.clear()
        source._SELECTIONS.clear()
