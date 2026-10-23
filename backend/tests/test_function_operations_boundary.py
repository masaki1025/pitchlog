"""固定関数登録と同一scope実行の閉鎖境界を確認する。"""

from __future__ import annotations

import inspect
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, dataclass, field, replace
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import (
    Integer,
    String,
    Uuid,
    bindparam,
    cast,
    delete,
    func,
    label,
    select,
    table,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import BindParameter, ColumnElement
from sqlalchemy.sql.functions import Function
from sqlalchemy.sql.selectable import Select
from sqlalchemy.sql.type_api import TypeDecorator
from test_authz_tenant_context import make_tenant_context

from pitchlog.db.game_state.rule_snapshot import (
    DomainValidatedRuleSnapshot,
    RuleSnapshotContractUnavailable,
)
from pitchlog.repositories import operation_registry, rule_resolution, transaction
from pitchlog.repositories.binding import TenantBindingError
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    FunctionOperationRegistration,
    _valid_db_identifier,
    build_function_registry,
    decode_function_result,
    prepare_function_operation,
)
from pitchlog.repositories.rule_resolution import (
    AppliedRuleSnapshot,
    RuleResolutionError,
    StageAResolveRuleToken,
    StageARuleRequest,
    resolve_stage_a_rule,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

_TENANT_ID = UUID("00000000-0000-0000-0000-000000000550")


@dataclass(frozen=True, slots=True)
class _FixedToken(TenantOperationToken):
    """試験専用の閉じた関数token。"""

    marker: str = "one"
    claimed_capability: str = "CAP:test:fixed"

    @property
    def capability_id(self) -> str:
        """登録済みcapabilityを返す。"""
        return self.claimed_capability


@dataclass(frozen=True, slots=True)
class _UnregisteredToken(TenantOperationToken):
    """未登録関数token。"""

    @property
    def capability_id(self) -> str:
        """偽のcapabilityを返す。"""
        return "CAP:test:fixed"


@dataclass(frozen=True, slots=True)
class _DerivedToken(_FixedToken):
    """登録型から派生した偽造token。"""


def _registration() -> FunctionOperationRegistration:
    """単一のschema修飾関数を試験内だけに登録する。"""
    statement = select(
        func.public.fixed_probe(bindparam("tenant_id"), bindparam("marker")).label(
            "value"
        )
    )
    return FunctionOperationRegistration(
        operation_id="test.fixed_probe",
        token_type=_FixedToken,
        capability_id="CAP:test:fixed",
        function_id="public.fixed_probe",
        statement=statement,
        input_fields=(("marker", str),),
        result_fields=(("value", str),),
        min_rows=1,
        max_rows=1,
        decoder=lambda result: result,
    )


def test_product_function_registry_keeps_rg1_and_adds_one_rule_operation() -> None:
    """RG1の2件を保ち、段階A読取だけを1件追加する。"""
    from pitchlog.repositories.rg1 import (
        RG1CommitCheckToken,
        RG1PrecheckToken,
    )

    assert tuple(
        entry.operation_id for entry in operation_registry.PRODUCT_FUNCTION_OPERATIONS
    ) == ("RG1:precheck", "RG1:commit_check", "RULE:resolve_stage_a")
    assert set(operation_registry.FUNCTION_OPERATION_REGISTRY) == {
        RG1PrecheckToken,
        RG1CommitCheckToken,
        StageAResolveRuleToken,
    }
    assert operation_registry.PRODUCT_OPERATIONS


def test_stage_a_rule_registration_has_exact_inputs_and_fixed_sql() -> None:
    """任意tenant・SQLを受け取らず固定4引数と不変結果だけを登録する。"""
    spec = operation_registry.FUNCTION_OPERATION_REGISTRY[StageAResolveRuleToken]
    request = StageAResolveRuleToken("game_official", "tournament_one", False)
    selected, parameters = prepare_function_operation(
        request, _TENANT_ID, operation_registry.FUNCTION_OPERATION_REGISTRY
    )
    assert selected is spec
    assert parameters == {
        "tenant_id": _TENANT_ID,
        "game_type_key": "game_official",
        "tournament_key": "tournament_one",
        "has_override": False,
    }
    assert spec.function_id == "public.resolve_stage_a_rule"
    assert spec.min_rows == spec.max_rows == 1
    assert spec.result_fields == (("resolution", MappingProxyType),)
    assert str(spec.statement.compile(dialect=postgresql.dialect())) == (
        "SELECT public.resolve_stage_a_rule(%(tenant_id)s::UUID, "
        "%(game_type_key)s, %(tournament_key)s, "
        "%(has_override)s) AS resolution"
    )
    assert set(inspect.signature(StageAResolveRuleToken).parameters) == {
        "game_type_key",
        "tournament_key",
        "has_override",
    }


@pytest.mark.parametrize("invalid", (None, 0, 1, "false"))
def test_stage_a_rule_registration_rejects_non_boolean_override(invalid: Any) -> None:
    """boolと紛らわしい入力もexact型検査でSQL実行前に拒否する。"""
    with pytest.raises(FunctionOperationError, match="has_override.*型が不一致"):
        prepare_function_operation(
            StageAResolveRuleToken("game_official", "tournament_one", invalid),
            _TENANT_ID,
            operation_registry.FUNCTION_OPERATION_REGISTRY,
        )


@pytest.mark.parametrize("field_name", ("game_type_key", "tournament_key"))
@pytest.mark.parametrize("mutated", (False, True))
def test_stage_a_empty_key_never_reaches_sql(
    field_name: str, mutated: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """構築時・強制変更後の空キーを実scopeのSQL実行前に拒否する。"""
    events: list[str] = []

    class _Session:
        def __init__(self, engine: object) -> None:
            events.append("session")

        def execute(self, statement: object, params: object) -> None:
            pytest.fail("空キーがSQL実行へ到達した")

        def close(self) -> None:
            events.append("close")

    @contextmanager
    def _binding(session: object, context: object) -> Iterator[None]:
        events.append("begin")
        try:
            yield
        except BaseException:
            events.append("rollback")
            raise
        else:
            events.append("commit")

    monkeypatch.setattr(transaction, "Session", _Session)
    monkeypatch.setattr(transaction, "create_database_engine", object)
    monkeypatch.setattr(transaction, "_tenant_transaction", _binding)
    keys = {"game_type_key": "game_official", "tournament_key": "tournament_one"}
    if not mutated:
        keys[field_name] = ""
    request = StageAResolveRuleToken(
        keys["game_type_key"], keys["tournament_key"], False
    )
    if mutated:
        object.__setattr__(request, field_name, "")
    with pytest.raises(FunctionOperationError, match=f"{field_name}.*空文字"):
        with transaction.tenant_transaction_scope(
            make_tenant_context(_TENANT_ID)
        ) as scope:
            scope.run_function(request)
    assert events == ["session", "begin", "rollback", "close"]


@pytest.mark.parametrize(
    "invalid",
    (None, [], ("missing",), ("marker", "marker"), (True,), ([],)),
)
def test_registration_rejects_invalid_nonempty_declaration(invalid: Any) -> None:
    """未知名・重複・非tuple・非文字列の非空宣言を登録時に拒否する。"""
    with pytest.raises(FunctionOperationError, match="非空入力宣言"):
        replace(_registration(), nonempty_inputs=invalid)


def test_registration_rejects_non_string_nonempty_input() -> None:
    """bool入力を非空文字列として宣言する登録を拒否する。"""
    spec = operation_registry.FUNCTION_OPERATION_REGISTRY[StageAResolveRuleToken]
    with pytest.raises(FunctionOperationError, match="非空入力宣言"):
        replace(spec, nonempty_inputs=("has_override",))


def test_nonempty_constraint_is_explicit_and_preserves_bind_values() -> None:
    """未指定入力の空文字と指定入力の空白を変換せず従来どおり渡す。"""
    spec = _registration()
    registry = build_function_registry((spec,), frozenset())
    assert (
        prepare_function_operation(_FixedToken(marker=""), _TENANT_ID, registry)[1][
            "marker"
        ]
        == ""
    )
    restricted = replace(spec, nonempty_inputs=("marker",))
    registry = build_function_registry((restricted,), frozenset())
    assert (
        prepare_function_operation(_FixedToken(marker=" "), _TENANT_ID, registry)[1][
            "marker"
        ]
        == " "
    )
    with pytest.raises(FunctionOperationError, match="空文字"):
        prepare_function_operation(_FixedToken(marker=""), _TENANT_ID, registry)
    for item in operation_registry.PRODUCT_FUNCTION_OPERATIONS:
        if item.operation_id.startswith("RG1:"):
            assert item.nonempty_inputs == ()


@pytest.mark.parametrize(
    "status",
    (
        "stage_a_unsupported",
        "rule_not_available",
        "invalid_rule",
        "outcome_unconfirmed",
    ),
)
def test_stage_a_rule_decoder_keeps_closed_failure_envelope(status: str) -> None:
    """DB失敗外形を保存成功や公開例外へ変換せず保持する。"""
    spec = operation_registry.FUNCTION_OPERATION_REGISTRY[StageAResolveRuleToken]
    result = TenantOperationResult(((MappingProxyType({"status": status}),),))
    assert decode_function_result(spec, result) is result


@pytest.mark.parametrize(
    "envelope",
    (
        {},
        {"status": "unknown"},
        {"status": 1},
        {"status": "resolved"},
        {"status": "resolved", "rule": ()},
        {"status": "resolved", "rule": MappingProxyType({}), "extra": True},
        {"status": "invalid_rule", "rule": MappingProxyType({})},
    ),
)
def test_stage_a_rule_decoder_rejects_unclosed_result(envelope: dict[str, Any]) -> None:
    """未知状態・欠落・余剰・成功失敗混在を固定decoderで拒否する。"""
    spec = operation_registry.FUNCTION_OPERATION_REGISTRY[StageAResolveRuleToken]
    with pytest.raises(FunctionOperationError):
        decode_function_result(
            spec, TenantOperationResult(((MappingProxyType(envelope),),))
        )


def test_stage_a_rule_operation_uses_real_scope_and_rejects_invalid_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """製品登録を実scope入口へ通し、不正戻りと失効scopeを拒否する。"""
    events: list[str] = []
    rule = {
        "ruleSetId": "00000000-0000-0000-0000-000000000550",
        "regulationInnings": 9,
        "coldConditions": [],
        "extensionLimit": 12,
        "tiebreak": None,
        "dh": True,
    }
    response: dict[str, object] = {"status": "resolved", "rule": rule}

    class _Session:
        def __init__(self, engine: object) -> None:
            events.append("session")

        def execute(
            self, statement: Select[Any], params: object
        ) -> list[tuple[object]]:
            spec = operation_registry.FUNCTION_OPERATION_REGISTRY[
                StageAResolveRuleToken
            ]
            assert statement is spec.statement
            assert params == {
                "tenant_id": _TENANT_ID,
                "game_type_key": "game_official",
                "tournament_key": "tournament_one",
                "has_override": False,
            }
            events.append("execute")
            return [(response,)]

        def close(self) -> None:
            events.append("close")

    @contextmanager
    def _binding(session: object, context: object) -> Iterator[None]:
        events.append("begin")
        try:
            yield
        except BaseException:
            events.append("rollback")
            raise
        else:
            events.append("commit")

    monkeypatch.setattr(transaction, "Session", _Session)
    monkeypatch.setattr(transaction, "create_database_engine", object)
    monkeypatch.setattr(transaction, "_tenant_transaction", _binding)
    request = StageAResolveRuleToken("game_official", "tournament_one", False)
    with transaction.tenant_transaction_scope(make_tenant_context(_TENANT_ID)) as scope:
        result = scope.run_function(request)
    assert events == ["session", "begin", "execute", "commit", "close"]
    assert isinstance(result.rows[0][0], MappingProxyType)
    with pytest.raises(RuntimeError, match="失効"):
        scope.run_function(request)
    assert events == ["session", "begin", "execute", "commit", "close"]
    events.clear()
    response = {"status": "resolved"}
    with pytest.raises(FunctionOperationError):
        with transaction.tenant_transaction_scope(
            make_tenant_context(_TENANT_ID)
        ) as scope:
            scope.run_function(request)
    assert events == ["session", "begin", "execute", "rollback", "close"]


def test_fixed_registration_prepares_exact_tenant_and_token_input() -> None:
    """Tenant IDはscopeからだけ渡し、入力はexact型とする。"""
    spec = _registration()
    registry = build_function_registry((spec,), frozenset())
    assert type(registry) is MappingProxyType
    assert prepare_function_operation(_FixedToken(), _TENANT_ID, registry) == (
        spec,
        {"tenant_id": _TENANT_ID, "marker": "one"},
    )
    with pytest.raises(FunctionOperationError, match="未登録または偽造"):
        prepare_function_operation(_UnregisteredToken(), _TENANT_ID, registry)
    with pytest.raises(FunctionOperationError, match="未登録または偽造"):
        prepare_function_operation(_DerivedToken(), _TENANT_ID, registry)
    with pytest.raises(FunctionOperationError, match="capability ID"):
        prepare_function_operation(
            _FixedToken(claimed_capability="forged"), _TENANT_ID, registry
        )
    with pytest.raises(FunctionOperationError, match="型が不一致"):
        prepare_function_operation(_FixedToken(marker=1), _TENANT_ID, registry)  # ty: ignore[invalid-argument-type]


def test_fixed_table_valued_function_has_declared_columns() -> None:
    """複数戻り列でも単一のschema修飾関数と固定列だけを許す。"""
    table = func.public.fixed_probe(
        bindparam("tenant_id"), bindparam("marker")
    ).table_valued("value", "revision")
    spec = replace(
        _registration(),
        statement=select(table.c.value, table.c.revision),
        result_fields=(("value", str), ("revision", int)),
    )
    result = TenantOperationResult(rows=(("ok", 1),))
    assert decode_function_result(spec, result) is result
    compiled = str(spec.statement.compile(dialect=postgresql.dialect()))
    assert "public.fixed_probe(" in compiled
    assert "value" in compiled and "revision" in compiled


def test_scalar_function_rejects_extra_declared_result_column() -> None:
    """単一列SELECTに存在しない戻り列を登録できない。"""
    with pytest.raises(FunctionOperationError, match="戻り列"):
        replace(
            _registration(),
            result_fields=(("value", str), ("extra", str)),
        )


def test_registration_rejects_sql_rewriting_bind_type() -> None:
    """Tenant bindを別テナントのSQLへ変換できる型を登録しない。"""

    class _TenantSwapType(TypeDecorator[UUID]):
        """tenant値をSQLコンパイル時に差し替える悪意ある型。"""

        impl = Uuid
        cache_ok = True

        @property
        def python_type(self) -> type[UUID]:
            """通常のUUID bindを装う。"""
            return UUID

        def bind_expression(
            self, bindparam: BindParameter[UUID]
        ) -> ColumnElement[UUID]:
            """実際にはscope由来のbindを捨てる。"""
            return cast(text("'00000000-0000-0000-0000-000000000551'"), Uuid)

    statement = select(
        func.public.fixed_probe(
            bindparam("tenant_id", type_=_TenantSwapType()),
            bindparam("marker"),
        ).label("value")
    )
    with pytest.raises(FunctionOperationError, match="未許可のSQL型"):
        replace(_registration(), statement=statement)

    variant = Uuid().with_variant(_TenantSwapType(), "postgresql")
    assert type(variant) is Uuid
    variant_statement = select(
        func.public.fixed_probe(
            bindparam("tenant_id", type_=variant),
            bindparam("marker"),
        ).label("value")
    )
    with pytest.raises(FunctionOperationError, match="dialect別"):
        replace(_registration(), statement=variant_statement)


def test_registration_rebuilds_safe_sql_from_validated_declaration() -> None:
    """戻り列の型とbind型の実装を実行用SQLへ持ち込まない。"""

    class _ResultRewriteType(TypeDecorator[str]):
        """SELECT列の式を差し替えられる型。"""

        impl = String
        cache_ok = True

        def column_expression(self, column: ColumnElement[str]) -> ColumnElement[str]:
            """登録元の列式を変更する。"""
            return cast(text("'replaced_value'"), String)

    changed_result = select(
        label(
            "value",
            func.public.fixed_probe(bindparam("tenant_id"), bindparam("marker")),
            type_=_ResultRewriteType(),
        )
    )
    result_spec = replace(_registration(), statement=changed_result)
    assert result_spec.statement is not changed_result
    assert "replaced_value" not in str(
        result_spec.statement.compile(dialect=postgresql.dialect())
    )

    changed_bind = Uuid()
    setattr(changed_bind, "dialect_impl", lambda dialect: _ResultRewriteType())
    supplied = select(
        func.public.fixed_probe(
            bindparam("tenant_id", type_=changed_bind),
            bindparam("marker"),
        ).label("value")
    )
    bind_spec = replace(_registration(), statement=supplied)
    assert bind_spec.statement is not supplied
    compiled = bind_spec.statement.compile(dialect=postgresql.dialect())
    assert "tenant_id" in compiled.params
    assert "replaced_value" not in str(compiled)


def test_registration_keeps_exact_function_names_with_trailing_underscore() -> None:
    """検証済みschema名・関数名を実行文でも同じ綴りに保つ。"""
    statement = select(
        Function(
            "fixed_probe_",
            bindparam("tenant_id"),
            bindparam("marker"),
            packagenames=("public_",),
        ).label("value")
    )
    spec = replace(
        _registration(),
        statement=statement,
        function_id="public_.fixed_probe_",
    )
    compiled = str(spec.statement.compile(dialect=postgresql.dialect()))
    assert "public_.fixed_probe_(" in compiled
    assert "public.fixed_probe(" not in compiled


@pytest.mark.parametrize("function_name", ("next_value", "substring"))
def test_registration_rejects_sqlalchemy_special_function_names(
    function_name: str,
) -> None:
    """DB関数名として見えてもコンパイラの特殊分岐へ入る名前を拒否する。"""
    statement = select(
        Function(
            function_name,
            bindparam("tenant_id"),
            bindparam("marker"),
            packagenames=("public",),
        ).label("value")
    )
    with pytest.raises(FunctionOperationError, match="特殊関数名"):
        replace(
            _registration(),
            statement=statement,
            function_id=f"public.{function_name}",
        )


@pytest.mark.parametrize("long_part", ("schema", "function"))
def test_registration_rejects_truncated_function_identity(long_part: str) -> None:
    """DBで切り詰められるschema名・関数名を登録しない。"""
    overlong = "f" * (postgresql.dialect().max_identifier_length + 1)
    schema = overlong if long_part == "schema" else "public"
    function_name = overlong if long_part == "function" else "fixed_probe"
    statement = select(
        Function(
            function_name,
            bindparam("tenant_id"),
            bindparam("marker"),
            packagenames=(schema,),
        ).label("value")
    )
    with pytest.raises(FunctionOperationError, match="schema修飾"):
        replace(
            _registration(),
            statement=statement,
            function_id=f"{schema}.{function_name}",
        )


def test_registration_rejects_result_columns_equal_after_db_truncation() -> None:
    """宣言上だけ異なる戻り列名のDB衝突を拒否する。"""
    first = "c" * postgresql.dialect().max_identifier_length
    second = first + "x"
    table = Function(
        "fixed_probe",
        bindparam("tenant_id"),
        bindparam("marker"),
        packagenames=("public",),
    ).table_valued(first, second)
    with pytest.raises(FunctionOperationError, match="入出力宣言"):
        replace(
            _registration(),
            statement=select(table.c[first], table.c[second]),
            result_fields=((first, str), (second, str)),
        )


def test_registration_accepts_identifier_at_postgresql_limit() -> None:
    """切り詰めが起きない上限ちょうどの関数名は維持する。"""
    function_name = "f" * postgresql.dialect().max_identifier_length
    statement = select(
        Function(
            function_name,
            bindparam("tenant_id"),
            bindparam("marker"),
            packagenames=("public",),
        ).label("value")
    )
    spec = replace(
        _registration(),
        statement=statement,
        function_id=f"public.{function_name}",
    )
    assert function_name in str(spec.statement.compile(dialect=postgresql.dialect()))


@pytest.mark.parametrize("part", ("schema", "function", "input", "result"))
@pytest.mark.parametrize(
    "invalid_name",
    (
        "select",
        "MixedCase",
        '"quoted"',
        "f" * (postgresql.dialect().max_identifier_length + 1),
    ),
    ids=("reserved", "case", "quoted", "overlong"),
)
def test_registration_rejects_noncanonical_identifiers_across_boundary(
    part: str, invalid_name: str
) -> None:
    """四種類の名前を同一規則で拒否し、宣言外SQLへ進めない。"""
    schema = invalid_name if part == "schema" else "public"
    function_name = invalid_name if part == "function" else "fixed_probe"
    input_name = invalid_name if part == "input" else "marker"
    result_name = invalid_name if part == "result" else "value"
    statement = select(
        Function(
            function_name,
            bindparam("tenant_id"),
            bindparam(input_name),
            packagenames=(schema,),
        ).label(result_name)
    )
    expected_error = "schema修飾" if part in ("schema", "function") else "入出力宣言"
    with pytest.raises(FunctionOperationError, match=expected_error):
        replace(
            _registration(),
            function_id=f"{schema}.{function_name}",
            statement=statement,
            input_fields=((input_name, str),),
            result_fields=((result_name, str),),
        )


def test_identifier_policy_matches_postgresql_unquoted_compilation() -> None:
    """有効名は未引用・正確な綴りで出力し、引用が要る名は一律拒否する。"""
    max_name = "f" * postgresql.dialect().max_identifier_length
    assert _valid_db_identifier(max_name)
    assert _valid_db_identifier("public_")
    for name in ("select", "user", "MixedCase", '"quoted"', max_name + "x"):
        assert not _valid_db_identifier(name)
    compiled = _registration().statement.compile(dialect=postgresql.dialect())
    assert str(compiled).startswith("SELECT public.fixed_probe(")
    assert tuple(compiled.params) == ("tenant_id", "marker")
    assert " AS value" in str(compiled)


@pytest.mark.parametrize(
    "schema",
    ("pg_temp", "pg_temp_3", "pg_toast_temp_3", "pg_catalog", "information_schema"),
)
def test_registration_rejects_session_alias_and_system_schemas(schema: str) -> None:
    """セッション別の一時schemaやシステムschemaを固定関数identityにしない。"""
    statement = select(
        Function(
            "fixed_probe",
            bindparam("tenant_id"),
            bindparam("marker"),
            packagenames=(schema,),
        ).label("value")
    )
    with pytest.raises(FunctionOperationError, match="schema修飾"):
        replace(
            _registration(),
            function_id=f"{schema}.fixed_probe",
            statement=statement,
        )


@pytest.mark.parametrize(
    "statement",
    (
        text("SELECT public.fixed_probe(:tenant_id, :marker)"),
        select(
            func.fixed_probe(bindparam("tenant_id"), bindparam("marker")).label("value")
        ),
        select(
            func.public.other(bindparam("tenant_id"), bindparam("marker")).label(
                "value"
            )
        ),
        select(
            func.public.fixed_probe(bindparam("tenant_id"), bindparam("other")).label(
                "value"
            )
        ),
        select(
            func.public.fixed_probe(
                bindparam("tenant_id"), bindparam("marker", type_=Integer)
            ).label("value")
        ),
        select(
            func.public.fixed_probe(
                bindparam("tenant_id", literal_execute=True), bindparam("marker")
            ).label("value")
        ),
        select(
            func.public.fixed_probe(
                bindparam("tenant_id"), bindparam("marker", literal_execute=True)
            ).label("value")
        ),
        select(
            func.public.fixed_probe(
                bindparam("tenant_id", expanding=True), bindparam("marker")
            ).label("value")
        ),
        select(
            func.public.fixed_probe(
                bindparam("tenant_id"), bindparam("marker", expanding=True)
            ).label("value")
        ),
        select(
            func.public.fixed_probe(bindparam("tenant_id"), bindparam("marker")).label(
                "value"
            )
        ).where(text("true")),
        select(
            func.public.fixed_probe(bindparam("tenant_id"), bindparam("marker")).label(
                "value"
            )
        ).add_cte(delete(table("other_tenant_data")).cte("wipe")),
    ),
)
def test_registration_rejects_arbitrary_sql_and_changed_function(
    statement: object,
) -> None:
    """任意SQL、別関数、bind変形、追加述語・DML CTEを拒否する。"""
    with pytest.raises(FunctionOperationError):
        replace(_registration(), statement=statement)  # type: ignore[arg-type]


def test_function_registry_rejects_dml_and_duplicate_registration() -> None:
    """DML token型または関数operation IDの重複を拒否する。"""
    spec = _registration()
    with pytest.raises(FunctionOperationError, match="重複"):
        build_function_registry((spec,), frozenset({_FixedToken}))
    with pytest.raises(FunctionOperationError, match="重複"):
        build_function_registry((spec, spec), frozenset())
    with pytest.raises(FunctionOperationError, match="重複"):
        build_function_registry((spec,), frozenset(), frozenset({"test.fixed_probe"}))
    with pytest.raises(FunctionOperationError, match="重複"):
        build_function_registry((spec,), frozenset(), frozenset({"CAP:test:fixed"}))


def test_function_entry_exposes_no_session_sql_or_tenant_argument() -> None:
    """callerへSession、任意SQL、tenant IDの引数を公開しない。"""
    assert tuple(
        inspect.signature(transaction._TenantTransaction.run_function).parameters
    ) == (
        "self",
        "operation",
    )
    assert "_session" not in transaction._TenantTransaction.__slots__


def test_decoder_rejects_wrong_columns_types_and_return_type() -> None:
    """戻り行を固定列・exact型・不変DTOへ閉じる。"""
    spec = _registration()
    result = TenantOperationResult(rows=(("ok",),))
    assert decode_function_result(spec, result) is result
    with pytest.raises(FunctionOperationError, match="戻り列"):
        decode_function_result(spec, TenantOperationResult(rows=((1,),)))
    with pytest.raises(FunctionOperationError, match="戻り列"):
        decode_function_result(spec, TenantOperationResult(rows=(("ok", "extra"),)))
    with pytest.raises(FunctionOperationError, match="戻り行数"):
        decode_function_result(spec, TenantOperationResult(rows=()))
    with pytest.raises(FunctionOperationError, match="decoder"):
        decode_function_result(replace(spec, decoder=lambda _: "bad"), result)  # type: ignore[arg-type]
    with pytest.raises(FunctionOperationError, match="戻り列"):
        decode_function_result(
            replace(
                spec, decoder=lambda _: TenantOperationResult(rows=((17, "extra"),))
            ),
            result,
        )
    with pytest.raises(FunctionOperationError, match="戻り行数"):
        decode_function_result(
            replace(spec, decoder=lambda _: TenantOperationResult(rows=())), result
        )


def test_run_function_rejects_unregistered_before_session_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RG1以外の未登録tokenはSessionへ到達する前に拒否する。"""

    class _NoExecuteSession:
        """SQL実行を許可しない試験用Session。"""

        def execute(self, statement: Select[Any], params: object) -> None:
            """未登録tokenが来たら試験を失敗させる。"""
            raise AssertionError("Session.executeへ到達した")

    context = make_tenant_context(_TENANT_ID)
    state_key = object()
    monkeypatch.setitem(
        transaction._TRANSACTION_RUNTIMES, state_key, (_NoExecuteSession(), object())
    )
    handle = transaction._TenantTransaction(
        context,
        state_key,
        _TENANT_ID,
        context._integrity_proof,
        transaction._HANDLE_CREATION_TOKEN,
    )
    with pytest.raises(FunctionOperationError, match="未登録または偽造"):
        handle.run_function(_FixedToken())
    handle._expire()
    with pytest.raises(RuntimeError, match="失効"):
        handle.run_function(_FixedToken())


def test_registered_function_uses_same_scope_and_rolls_back_on_decoder_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """試験専用登録を同じ入口で実行し、decoder失敗を全取消へ渡す。"""
    events: list[str] = []

    class _FakeSession:
        """固定結果だけを返す閉じた試験用Session。"""

        def __init__(self, engine: object) -> None:
            """scopeが生成したことを記録する。"""
            events.append("session")

        def execute(self, statement: Select[Any], params: object) -> list[tuple[str]]:
            """関数文とscope由来tenant IDを照合する。"""
            assert (
                statement
                is transaction.FUNCTION_OPERATION_REGISTRY[_FixedToken].statement
            )
            assert params == {"tenant_id": _TENANT_ID, "marker": "one"}
            events.append("execute")
            return [("ok",)]

        def close(self) -> None:
            """scopeの終了で閉じる。"""
            events.append("close")

    @contextmanager
    def _binding(session: object, context: object) -> Iterator[None]:
        """既存のtransaction境界へ成功・失敗を委ねる。"""
        events.append("begin")
        try:
            yield
        except BaseException:
            events.append("rollback")
            raise
        else:
            events.append("commit")

    spec = _registration()
    monkeypatch.setattr(transaction, "Session", _FakeSession)
    monkeypatch.setattr(transaction, "create_database_engine", object)
    monkeypatch.setattr(transaction, "_tenant_transaction", _binding)
    monkeypatch.setattr(
        transaction,
        "FUNCTION_OPERATION_REGISTRY",
        build_function_registry((spec,), frozenset()),
    )
    with transaction.tenant_transaction_scope(make_tenant_context(_TENANT_ID)) as scope:
        assert scope.run_function(_FixedToken()).rows == (("ok",),)
    assert events == ["session", "begin", "execute", "commit", "close"]

    events.clear()

    def _raise_decoder(result: TenantOperationResult) -> TenantOperationResult:
        """decoder故障を注入する。"""
        raise ValueError("decoder failure")

    monkeypatch.setattr(
        transaction,
        "FUNCTION_OPERATION_REGISTRY",
        build_function_registry((replace(spec, decoder=_raise_decoder),), frozenset()),
    )
    with pytest.raises(ValueError, match="decoder failure"):
        with transaction.tenant_transaction_scope(
            make_tenant_context(_TENANT_ID)
        ) as scope:
            scope.run_function(_FixedToken())
    assert events == ["session", "begin", "execute", "rollback", "close"]

    events.clear()
    context = make_tenant_context(_TENANT_ID)
    with pytest.raises(TenantBindingError, match="発行証跡"):
        with transaction.tenant_transaction_scope(context) as scope:
            object.__setattr__(
                context, "tenant_id", UUID("00000000-0000-0000-0000-000000000551")
            )
            scope.run_function(_FixedToken())
    assert events == ["session", "begin", "rollback", "close"]


def test_run_function_stops_reading_after_declared_row_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """過剰行は上限の次の1行で検出し、全件読み込まず全取消する。"""
    observed: list[str] = []

    class _RowsSession:
        """過剰行を返す試験専用Session。"""

        def __init__(self, engine: object) -> None:
            """scopeから生成する。"""

        def execute(
            self, statement: Select[Any], params: object
        ) -> Iterator[tuple[str]]:
            """3行目を読んだ場合に試験を失敗させる。"""
            for index in range(3):
                if index == 2:
                    raise AssertionError("上限を超えて全件読み込んだ")
                observed.append("read")
                yield ("ok",)

        def close(self) -> None:
            """scope終了で閉じる。"""
            observed.append("close")

    @contextmanager
    def _binding(session: object, context: object) -> Iterator[None]:
        """失敗時の全取消を観測する。"""
        try:
            yield
        except BaseException:
            observed.append("rollback")
            raise

    monkeypatch.setattr(transaction, "Session", _RowsSession)
    monkeypatch.setattr(transaction, "create_database_engine", object)
    monkeypatch.setattr(transaction, "_tenant_transaction", _binding)
    monkeypatch.setattr(
        transaction,
        "FUNCTION_OPERATION_REGISTRY",
        build_function_registry((_registration(),), frozenset()),
    )
    with pytest.raises(FunctionOperationError, match="戻り行数"):
        with transaction.tenant_transaction_scope(
            make_tenant_context(_TENANT_ID)
        ) as scope:
            scope.run_function(_FixedToken())
    assert observed == ["read", "read", "rollback", "close"]


def _resolver_rule_json() -> dict[str, object]:
    """正規codecへ渡すUUIDと5値の代表入力を返す。"""
    return {
        "ruleSetId": str(_TENANT_ID),
        "regulationInnings": 9,
        "coldConditions": [{"pointDifference": 7, "startInning": 7}],
        "extensionLimit": 12,
        "tiebreak": {
            "startInning": 10,
            "runnerPlacement": "no_out_first_second",
            "leadoffRule": "continue_lineup",
        },
        "dh": True,
    }


@dataclass
class _ResolverRuntime:
    """実scopeに接続する合成Sessionの入力と観測を保持する。"""

    rows: list[tuple[object, ...]] = field(
        default_factory=lambda: [
            ({"status": "resolved", "rule": _resolver_rule_json()},)
        ]
    )
    events: list[str] = field(default_factory=list)
    error: Exception | None = None
    expected_keys: tuple[str, str] = ("game_official", "tournament_one")
    expected_override: bool = False


@pytest.fixture
def resolver_runtime(monkeypatch: pytest.MonkeyPatch) -> _ResolverRuntime:
    """実registry/tenant scopeへ合成Sessionだけを供給する。"""
    runtime = _ResolverRuntime()

    class _Session:
        """SQLとscope由来bindの一致を観測する合成Session。"""

        def __init__(self, engine: object) -> None:
            """scopeが作るSessionの生成を記録する。"""
            runtime.events.append("session")

        def execute(
            self, statement: Select[Any], params: object
        ) -> list[tuple[object, ...]]:
            """実固定SQL/tenantを照合し、指定結果または故障を返す。"""
            assert (
                statement
                is operation_registry.FUNCTION_OPERATION_REGISTRY[
                    StageAResolveRuleToken
                ].statement
            )
            assert params == {
                "tenant_id": _TENANT_ID,
                "game_type_key": runtime.expected_keys[0],
                "tournament_key": runtime.expected_keys[1],
                "has_override": runtime.expected_override,
            }
            runtime.events.append("execute")
            if runtime.error is not None:
                raise runtime.error
            return runtime.rows

        def close(self) -> None:
            """scopeの終了を記録する。"""
            runtime.events.append("close")

    @contextmanager
    def _binding(session: object, context: object) -> Iterator[None]:
        """実scopeからの例外退出と通常終了を区別する。"""
        runtime.events.append("begin")
        try:
            yield
        except BaseException:
            runtime.events.append("rollback")
            raise
        else:
            runtime.events.append("commit")

    monkeypatch.setattr(transaction, "Session", _Session)
    monkeypatch.setattr(transaction, "create_database_engine", object)
    monkeypatch.setattr(transaction, "_tenant_transaction", _binding)
    return runtime


def _resolver_request() -> StageARuleRequest:
    """必須大会キーを含む公開入力を作る。"""
    return StageARuleRequest("game_official", "tournament_one", False)


def test_public_resolver_returns_canonical_immutable_snapshot(
    resolver_runtime: _ResolverRuntime,
) -> None:
    """実固定scopeの不変JSON結果を単一codecへ接続する。"""
    assert AppliedRuleSnapshot.__value__ is DomainValidatedRuleSnapshot
    request = _resolver_request()
    with transaction.tenant_transaction_scope(make_tenant_context(_TENANT_ID)) as scope:
        result = resolve_stage_a_rule(scope, request)
    assert type(result) is DomainValidatedRuleSnapshot
    structural = result.structural
    assert structural.rule_set_id == _TENANT_ID
    assert structural.regulation_innings == 9
    assert structural.cold_conditions[0].point_difference == 7
    assert structural.extension_limit == 12
    assert structural.tiebreak is not None
    assert structural.tiebreak.start_inning == 10
    assert structural.dh is True
    for target, attribute, value in (
        (request, "tournament_key", "other"),
        (result, "structural", None),
        (structural, "dh", False),
        (structural.cold_conditions[0], "start_inning", 1),
        (structural.tiebreak, "start_inning", 1),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(target, attribute, value)
    assert resolver_runtime.events == ["session", "begin", "execute", "commit", "close"]
    with pytest.raises(RuleResolutionError, match="outcome_unconfirmed"):
        resolve_stage_a_rule(scope, request)
    assert resolver_runtime.events.count("execute") == 1


@pytest.mark.parametrize(
    "status",
    (
        "stage_a_unsupported",
        "rule_not_available",
        "invalid_rule",
        "outcome_unconfirmed",
    ),
)
def test_public_resolver_failure_leaves_scope_by_exception(
    status: str, resolver_runtime: _ResolverRuntime
) -> None:
    """既知4失敗は同じcodeでscope外へ出て全取消する。"""
    resolver_runtime.rows = [({"status": status},)]
    with pytest.raises(RuleResolutionError) as captured:
        with transaction.tenant_transaction_scope(
            make_tenant_context(_TENANT_ID)
        ) as scope:
            resolve_stage_a_rule(scope, _resolver_request())
    assert captured.value.code == status
    assert str(captured.value) == status
    assert resolver_runtime.events == [
        "session",
        "begin",
        "execute",
        "rollback",
        "close",
    ]


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [({},)],
        [({"status": "unknown-internal"},)],
        [(None,)],
        [({"status": "resolved"},)],
        [({"status": "rule_not_available", "cause": "secret"},)],
        [({"status": "resolved", "rule": {"unexpected": b"private"}},)],
        [({"status": "rule_not_available"}, "extra")],
    ],
)
def test_public_resolver_rejects_unknown_result_without_internal_detail(
    rows: list[tuple[object, ...]], resolver_runtime: _ResolverRuntime
) -> None:
    """未知または非JSONの結果を結果不明へ閉じ、内部値を秘匿する。"""
    resolver_runtime.rows = rows
    with pytest.raises(RuleResolutionError) as captured:
        with transaction.tenant_transaction_scope(
            make_tenant_context(_TENANT_ID)
        ) as scope:
            resolve_stage_a_rule(scope, _resolver_request())
    assert captured.value.code == "outcome_unconfirmed"
    exposed = "".join(traceback.format_exception(captured.value))
    assert "secret" not in exposed and "private" not in exposed
    assert "unknown-internal" not in exposed
    assert resolver_runtime.events[-2:] == ["rollback", "close"]
    assert "commit" not in resolver_runtime.events


@pytest.mark.parametrize(
    "kind", ("empty", "five", "extra", "uuid", "value", "correlation")
)
def test_public_resolver_uses_codec_to_reject_invalid_snapshot(
    kind: str, resolver_runtime: _ResolverRuntime
) -> None:
    """構造・値域・相関の失敗を補完せず正規codecから伝播する。"""
    rule = _resolver_rule_json()
    if kind == "empty":
        rule = {}
    elif kind == "five":
        del rule["ruleSetId"]
    elif kind == "extra":
        rule["extra"] = True
    elif kind == "uuid":
        rule["ruleSetId"] = "not-a-uuid"
    elif kind == "value":
        rule["dh"] = 1
    else:
        rule["extensionLimit"] = 8
    resolver_runtime.rows = [({"status": "resolved", "rule": rule},)]
    with pytest.raises(RuleResolutionError, match="invalid_rule"):
        with transaction.tenant_transaction_scope(
            make_tenant_context(_TENANT_ID)
        ) as scope:
            resolve_stage_a_rule(scope, _resolver_request())
    assert resolver_runtime.events[-2:] == ["rollback", "close"]


@pytest.mark.parametrize("fault", ("sql", "contract", "unknown"))
def test_public_resolver_faults_are_unconfirmed_and_sanitized(
    fault: str,
    resolver_runtime: _ResolverRuntime,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SQL故障/契約読込不能/未知故障を内因を出さず全取消する。"""
    private = "PRIVATE_SQL_TENANT_CAUSE"
    if fault == "sql":
        resolver_runtime.error = OperationalError(private, {}, RuntimeError(private))
    else:

        def _fail(value: object) -> DomainValidatedRuleSnapshot:
            """codecの契約読込不能または未知故障を注入する。"""
            if fault == "contract":
                raise RuleSnapshotContractUnavailable(private)
            raise RuntimeError(private)

        monkeypatch.setattr(rule_resolution, "decode_applied_rules", _fail)
    with pytest.raises(RuleResolutionError) as captured:
        with transaction.tenant_transaction_scope(
            make_tenant_context(_TENANT_ID)
        ) as scope:
            resolve_stage_a_rule(scope, _resolver_request())
    assert captured.value.code == "outcome_unconfirmed"
    assert private not in "".join(traceback.format_exception(captured.value))
    assert private not in caplog.text
    assert resolver_runtime.events[-2:] == ["rollback", "close"]
    assert resolver_runtime.events.count("execute") == 1


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("game_type_key", ""),
        ("tournament_key", ""),
        ("tournament_key", None),
        ("game_type_key", 1),
        ("rule_override_present", 1),
        ("rule_override_present", None),
    ],
)
def test_public_resolver_rejects_mutated_request_before_sql(
    attribute: str, value: object, resolver_runtime: _ResolverRuntime
) -> None:
    """公開DTOの強制変更後も実行前に空/型不正を拒否する。"""
    request = _resolver_request()
    object.__setattr__(request, attribute, value)
    with pytest.raises(ValueError):
        with transaction.tenant_transaction_scope(
            make_tenant_context(_TENANT_ID)
        ) as scope:
            resolve_stage_a_rule(scope, request)
    assert resolver_runtime.events == ["session", "begin", "rollback", "close"]


def test_public_resolver_rejects_fake_session_and_derived_scope() -> None:
    """同じメソッドを持つ偽物・Session・派生scopeを受理しない。"""
    calls: list[str] = []

    class _FakeScope:
        """もっともらしい成功を返す偽物。"""

        def run_function(self, token: object) -> object:
            """呼び出された場合は偽成功を返す。"""
            calls.append("fake")
            return object()

    class _DerivedScope(transaction._TenantTransaction):  # ty: ignore[subclass-of-final-class]
        """実行時の派生型もexact型検査で拒否する。"""

    with Session() as session:
        for candidate in (_FakeScope(), session, object.__new__(_DerivedScope)):
            invalid: Any = candidate
            with pytest.raises(TypeError):
                resolve_stage_a_rule(invalid, _resolver_request())
    assert calls == []


def test_public_resolver_rejects_nonexact_request_and_keeps_whitespace(
    resolver_runtime: _ResolverRuntime,
) -> None:
    """任意入力型を拒否し、有効な文字列のトリムを追加しない。"""

    class _DerivedRequest(StageARuleRequest):
        """公開DTOの派生型。"""

    for candidate in (object(), object.__new__(_DerivedRequest)):
        invalid: Any = candidate
        with pytest.raises(TypeError):
            with transaction.tenant_transaction_scope(
                make_tenant_context(_TENANT_ID)
            ) as scope:
                resolve_stage_a_rule(scope, invalid)
    assert "execute" not in resolver_runtime.events
    resolver_runtime.expected_keys = (" game_official ", " tournament_one ")
    resolver_runtime.expected_override = True
    resolver_runtime.rows = [({"status": "stage_a_unsupported"},)]
    request = StageARuleRequest(*resolver_runtime.expected_keys, True)
    with pytest.raises(RuleResolutionError, match="stage_a_unsupported"):
        with transaction.tenant_transaction_scope(
            make_tenant_context(_TENANT_ID)
        ) as scope:
            resolve_stage_a_rule(scope, request)


@pytest.mark.parametrize(
    "game_key,tournament_key,override",
    [
        ("", "tournament_one", False),
        ("game_official", "", False),
        (None, "tournament_one", False),
        ("game_official", None, False),
        ("game_official", "tournament_one", 1),
    ],
)
def test_public_request_rejects_invalid_values_on_construction(
    game_key: Any,
    tournament_key: Any,
    override: Any,
) -> None:
    """生成時にも空キーとbool等の型混同を拒否する。"""
    with pytest.raises(ValueError):
        StageARuleRequest(game_key, tournament_key, override)


def test_public_failure_code_is_closed() -> None:
    """例外へ未定義literalや内部情報を設定できない。"""
    invalid: Any = "private_internal_code"
    with pytest.raises(ValueError, match="未定義"):
        RuleResolutionError(invalid)
