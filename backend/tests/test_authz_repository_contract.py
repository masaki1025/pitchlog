"""リポジトリ基底の公開面・token・immutable 戻り値契約を検査する。"""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Callable, Generator, Iterator
from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast, get_type_hints
from uuid import UUID

import pytest
from sqlalchemy import (
    Result,
    ScalarResult,
    bindparam,
    column,
    create_engine,
    literal,
    or_,
    select,
    table,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Query,
    Session,
    mapped_column,
)
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.sql.schema import Table
from test_authz_tenant_context import make_tenant_context

from pitchlog.repositories import base as repository_base
from pitchlog.repositories import repository_contract
from pitchlog.repositories import tokens as repository_tokens
from pitchlog.repositories.base import (
    _IMMUTABLE_SCALAR_TYPES,
    CROSS_TENANT_FUNCTION_REGISTRY,
    TenantRepositoryBase,
    _materialize_rows,
    _TenantOperationError,
    _TenantScopedOperation,
)
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_CONTRACT_PATH = Path("contracts/tenant_boundary/repository-contract.json")
_TEST_TABLE = table(
    "repository_contract_probe",
    column("tenant_id"),
    column("marker"),
)


class _NoSessionRepository(TenantRepositoryBase):
    """拒否試験で Session に到達しないことを確認する基底具象。"""

    @property
    def _session(self) -> Session:
        raise AssertionError("未登録 token から Session へ到達した")


@dataclass(frozen=True, slots=True)
class _ForgedToken(TenantOperationToken):
    """製品 registry に存在しない偽造 token。"""

    @property
    def capability_id(self) -> str:
        """偽の capability ID を返す。"""
        return "forged"


@dataclass(frozen=True, slots=True)
class _RegisteredTestToken(TenantOperationToken):
    """公開戻り値 guard の試験だけに登録する閉じた token。"""

    @property
    def capability_id(self) -> str:
        """テスト専用 capability ID を返す。"""
        return "test.repository-contract.return"


@dataclass
class _MutableDTO:
    """frozen でない戻り値負例。"""

    value: str


class _TestOrmBase(DeclarativeBase):
    """接続中 ORM instance の負例にだけ使う test base。"""


class _AttachedOrmValue(_TestOrmBase):
    """Session に接続した状態を作る戻り値負例。"""

    __tablename__ = "repository_contract_attached_values"

    id: Mapped[int] = mapped_column(primary_key=True)


class _UnsafeReturnRepository(TenantRepositoryBase):
    """非公開実行器の戻り値を変異させるテスト専用具象。"""

    def __init__(self, value: object) -> None:
        """戻り値変異を保持する。"""
        self._value = value

    @property
    def _session(self) -> Session:
        raise AssertionError("戻り値変異から Session へ到達した")

    def _execute_operation(
        self,
        context: TenantContext,
        operation: TenantOperationToken,
    ) -> TenantOperationResult:
        """型注釈だけを偽装して危険な値を返す。"""
        del context, operation
        return cast(TenantOperationResult, self._value)


def _read_contract() -> dict[str, Any]:
    """リポジトリ契約資産を JSON object として読む。"""
    value = json.loads(
        (_REPOSITORY_ROOT / _CONTRACT_PATH).read_text(encoding="utf-8")
    )
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise AssertionError("repository contract が JSON object でない")
    return value


def _asset_digest(asset: dict[str, Any]) -> str:
    """source_digest を除く正規化 digest を計算する。"""
    payload = dict(asset)
    payload.pop("source_digest", None)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _generated_snapshot() -> dict[str, object]:
    """生成モジュールを資産と比較できる形へ変換する。"""
    return {
        "schema_version": repository_contract.SCHEMA_VERSION,
        "contract_revision": repository_contract.CONTRACT_REVISION,
        "asset_kind": repository_contract.ASSET_KIND,
        "canonicalization": repository_contract.CANONICALIZATION,
        "source_digest": repository_contract.SOURCE_DIGEST,
        "public_surface": {
            "repository_type": repository_contract.REPOSITORY_TYPE,
            "context_binding_entry": repository_contract.CONTEXT_BINDING_ENTRY,
            "cross_tenant_function_entry": (
                repository_contract.CROSS_TENANT_FUNCTION_ENTRY
            ),
            "operation_token_type": repository_contract.OPERATION_TOKEN_TYPE,
            "operation_result_type": repository_contract.OPERATION_RESULT_TYPE,
            "cross_tenant_function_registry": (
                repository_contract.CROSS_TENANT_FUNCTION_REGISTRY_SYMBOL
            ),
        },
        "executor": {
            "symbol": repository_contract.EXECUTOR_SYMBOL,
            "signature": repository_contract.EXECUTOR_SIGNATURE,
        },
        "return_contract": {
            "allowed_dtos": list(repository_contract.ALLOWED_DTOS),
            "immutable_scalar_types": list(
                repository_contract.IMMUTABLE_SCALAR_TYPES
            ),
            "immutable_container_grammar": list(
                repository_contract.IMMUTABLE_CONTAINER_GRAMMAR
            ),
            "forbidden_types": list(repository_contract.FORBIDDEN_TYPES),
        },
        "product_capability_ids": list(
            repository_contract.PRODUCT_CAPABILITY_IDS
        ),
        "product_operation_token_types": list(
            repository_contract.PRODUCT_OPERATION_TOKEN_TYPES
        ),
        "cross_tenant_functions": list(
            repository_contract.CROSS_TENANT_FUNCTIONS
        ),
    }


def _public_signature_violations(
    context_type: object,
    operation_type: object,
    return_type: object,
) -> set[str]:
    """公開 execute の型境界に対する変異違反を返す。"""
    violations: set[str] = set()
    if context_type is not TenantContext:
        violations.add("CONTEXT_TYPE")
    if operation_type is not TenantOperationToken:
        violations.add("OPERATION_TYPE")
    if return_type is not TenantOperationResult:
        violations.add("RETURN_TYPE")
    return violations


def test_generated_repository_contract_matches_asset() -> None:
    """資産の全フィールドと配布対象モジュールが一致することを確認する。"""
    asset = _read_contract()

    assert repository_contract.SOURCE_ASSET == _CONTRACT_PATH.as_posix()
    assert asset["source_digest"] == _asset_digest(asset)
    assert _generated_snapshot() == asset


def test_public_repository_surface_and_signature_are_exact() -> None:
    """公開面が token 入口だけで、生 Session や任意 query を公開しない。"""
    public_methods = {
        name
        for name, value in vars(TenantRepositoryBase).items()
        if not name.startswith("_") and inspect.isfunction(value)
    }
    signature = inspect.signature(TenantRepositoryBase.execute)
    hints = get_type_hints(TenantRepositoryBase.execute)

    assert repository_base.__all__ == (
        "CROSS_TENANT_FUNCTION_REGISTRY",
        "TenantRepositoryBase",
    )
    assert repository_tokens.__all__ == (
        "TenantOperationResult",
        "TenantOperationToken",
    )
    assert public_methods == {"execute"}
    assert tuple(signature.parameters) == ("self", "context", "operation")
    assert _public_signature_violations(
        hints["context"], hints["operation"], hints["return"]
    ) == set()
    assert getattr(TenantRepositoryBase.execute, "__final__", False) is True


def test_product_capabilities_tokens_and_cross_tenant_registry_are_empty() -> None:
    """TSK-424 と所有単位の実装前は製品操作と越境関数を一件も開かない。"""
    assert repository_contract.PRODUCT_CAPABILITY_IDS == ()
    assert repository_contract.PRODUCT_OPERATION_TOKEN_TYPES == ()
    assert (
        repository_contract.CROSS_TENANT_FUNCTION_ENTRY
        == repository_contract.CONTEXT_BINDING_ENTRY
    )
    assert type(repository_base._OPERATION_REGISTRY) is MappingProxyType
    assert repository_base._OPERATION_REGISTRY == {}
    assert CROSS_TENANT_FUNCTION_REGISTRY == frozenset()


def test_runtime_immutable_types_match_the_asset_exactly() -> None:
    """実行時 scalar 許可集合と資産の完全修飾名を exact-set で一致させる。"""
    expected_scalars = (
        "builtins.NoneType",
        "builtins.bool",
        "builtins.int",
        "builtins.float",
        "builtins.str",
        "builtins.bytes",
        "uuid.UUID",
        "decimal.Decimal",
        "datetime.date",
        "datetime.datetime",
        "datetime.time",
    )
    runtime_types = (
        "builtins.NoneType",
        *(
            f"{scalar_type.__module__}.{scalar_type.__qualname__}"
            for scalar_type in _IMMUTABLE_SCALAR_TYPES
        ),
    )

    assert repository_contract.ALLOWED_DTOS == (
        "pitchlog.repositories.tokens.TenantOperationResult",
    )
    assert repository_contract.IMMUTABLE_SCALAR_TYPES == expected_scalars
    assert runtime_types == expected_scalars
    assert repository_contract.IMMUTABLE_CONTAINER_GRAMMAR == (
        "tuple[T, ...]",
        "frozenset[T]",
    )
    assert repository_contract.FORBIDDEN_TYPES == (
        "typing.Any",
        "builtins.object",
        "collections.abc.Callable",
        "collections.abc.Iterator",
        "collections.abc.Generator",
        "sqlalchemy.engine.Result",
        "sqlalchemy.engine.ScalarResult",
        "sqlalchemy.orm.Query",
        "sqlalchemy.orm.DeclarativeBase",
        "sqlalchemy.sql.Executable",
        "sqlalchemy.sql.Select",
        "sqlalchemy.sql.schema.Table",
        "non_frozen_dataclass",
    )


@pytest.mark.parametrize(
    "operation_type",
    (
        Any,
        object,
        Callable[..., object],
        TextClause,
        Select,
        Table,
        _AttachedOrmValue,
    ),
)
def test_arbitrary_operation_parameter_type_mutations_are_red(
    operation_type: object,
) -> None:
    """Any・callable・statement・model・table の引数変異を拒否する。"""
    assert _public_signature_violations(
        TenantContext,
        operation_type,
        TenantOperationResult,
    ) == {"OPERATION_TYPE"}


@pytest.mark.parametrize(
    "return_type",
    (
        Any,
        object,
        Iterator[object],
        Generator[object, None, None],
        Result,
        ScalarResult,
        Query,
        DeclarativeBase,
        _MutableDTO,
    ),
)
def test_unsafe_return_type_mutations_are_red(return_type: object) -> None:
    """遅延・ORM・非frozen・非限定型を公開戻り値へ変える変異を拒否する。"""
    assert _public_signature_violations(
        TenantContext,
        TenantOperationToken,
        return_type,
    ) == {"RETURN_TYPE"}


@pytest.mark.parametrize(
    "candidate",
    (
        text("SELECT 1"),
        lambda: None,
        _ForgedToken(),
    ),
)
def test_statement_callable_and_forged_token_are_rejected_before_session(
    candidate: object,
) -> None:
    """任意 statement・callable・偽造 token が実行器へ到達しない。"""
    repository = _NoSessionRepository()
    context = make_tenant_context(_repository_contract_test_tenant_id())

    with pytest.raises(_TenantOperationError, match="未登録|偽造"):
        repository.execute(context, cast(TenantOperationToken, candidate))


def _repository_contract_test_tenant_id() -> UUID:
    """型変異を混ぜずに既存のテスト専用 TenantContext 生成経路へ UUID を渡す。"""
    return UUID("00000000-0000-0000-0000-000000000909")


@pytest.mark.parametrize(
    "statement",
    (
        select(_TEST_TABLE.c.marker),
        select(literal("tenant_id = :tenant_id")),
        select(_TEST_TABLE.c.marker).where(
            or_(
                _TEST_TABLE.c.tenant_id == bindparam("tenant_id"),
                literal(True),
            )
        ),
    ),
)
def test_tenant_scoped_statement_requires_explicit_tenant_condition(
    statement: Select[tuple[object, ...]],
) -> None:
    """欠落・字面偽装・OR 迂回を registry spec にできない。"""
    with pytest.raises(_TenantOperationError, match="tenant_id = :tenant_id"):
        _TenantScopedOperation(
            capability_id="test.missing-tenant",
            statement=statement,
            tenant_column=_TEST_TABLE.c.tenant_id,
        )


def test_tenant_scope_is_a_required_typed_operation_field() -> None:
    """テナント列を省略できない constructor 署名であることを固定する。"""
    signature = inspect.signature(_TenantScopedOperation)

    assert tuple(signature.parameters) == (
        "capability_id",
        "statement",
        "tenant_column",
    )
    assert signature.parameters["tenant_column"].default is inspect.Parameter.empty


def test_runtime_materializer_rejects_mutable_generator_and_attached_orm() -> None:
    """公開前の実体化処理が危険な値をすべて拒否する。"""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    attached = _AttachedOrmValue(id=1)
    try:
        with Session(engine) as session:
            session.add(attached)
            assert attached in session
            forbidden_values = (
                _MutableDTO("mutable"),
                (value for value in (1, 2)),
                attached,
            )
            for value in forbidden_values:
                with pytest.raises(
                    _TenantOperationError,
                    match="許可されていない",
                ):
                    _materialize_rows(((value,),))
    finally:
        engine.dispose()


def test_public_return_guard_rejects_lazy_and_mutable_executor_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """実行器の注釈偽装でも Result・ORM・generator・可変 DTO を公開しない。"""
    statement = select(_TEST_TABLE.c.marker).where(
        _TEST_TABLE.c.tenant_id == bindparam("tenant_id")
    )
    token = _RegisteredTestToken()
    monkeypatch.setattr(
        repository_base,
        "_OPERATION_REGISTRY",
        {
            _RegisteredTestToken: _TenantScopedOperation(
                capability_id=token.capability_id,
                statement=cast(Select[tuple[object, ...]], statement),
                tenant_column=_TEST_TABLE.c.tenant_id,
            )
        },
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    attached = _AttachedOrmValue(id=1)
    try:
        with Session(engine) as session:
            session.add(attached)
            raw_result = session.execute(text("SELECT 1"))
            forbidden_results = (
                raw_result,
                attached,
                _MutableDTO("mutable"),
                (value for value in (1, 2)),
            )
            for value in forbidden_results:
                with pytest.raises(
                    _TenantOperationError,
                    match="immutable DTO",
                ):
                    _UnsafeReturnRepository(value).execute(
                        make_tenant_context(_repository_contract_test_tenant_id()),
                        token,
                    )
    finally:
        engine.dispose()


def test_runtime_materializer_accepts_only_fully_materialized_values() -> None:
    """許可済み scalar と immutable container を frozen DTO へ閉じる。"""
    tenant_id = _repository_contract_test_tenant_id()

    result = _materialize_rows(
        ((tenant_id, "marker", (1, True), frozenset({"sealed"})),)
    )

    assert result.rows == (
        ((tenant_id, "marker", (1, True), frozenset({"sealed"}))),
    )
    with pytest.raises(FrozenInstanceError):
        setattr(result, "rows", ())


@pytest.mark.parametrize(
    "field",
    (
        "schema_version",
        "contract_revision",
        "asset_kind",
        "canonicalization",
        "source_digest",
        "public_surface",
        "executor",
        "return_contract",
        "product_capability_ids",
        "product_operation_token_types",
        "cross_tenant_functions",
    ),
)
def test_each_stale_generated_repository_field_is_red(field: str) -> None:
    """生成モジュールの各フィールドが古い変異を一致検査で検出する。"""
    generated = _generated_snapshot()
    generated[field] = object()

    assert generated != _read_contract()
