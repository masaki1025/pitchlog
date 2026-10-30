"""リポジトリ基底の公開面・token・immutable 戻り値契約を検査する。"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import inspect
import json
from collections.abc import Callable, Generator, Iterator
from dataclasses import FrozenInstanceError, dataclass
from datetime import date, datetime, time
from decimal import Decimal
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
from pitchlog.repositories.tokens import (
    ImmutableValue,
    TenantOperationResult,
    TenantOperationToken,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_CONTRACT_PATH = Path("contracts/tenant_boundary/repository-contract.json")
_ALLOWLIST_PATH = Path("contracts/tenant_boundary/base-allowlist.json")
_LEXICAL_MODULE = "pitchlog.recording_rights.rg1_lifecycle"
_LEXICAL_SYMBOLS = frozenset(
    f"{_LEXICAL_MODULE}.serve_fresh_controller.{name}"
    for name in ("control", "assert_borrower_backend")
)
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
    value = json.loads((_REPOSITORY_ROOT / _CONTRACT_PATH).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AssertionError("repository contract が JSON object でない")
    return value


def _read_allowlist() -> dict[str, Any]:
    """DB API 許可シンボル資産を JSON object として読む。"""
    value = json.loads((_REPOSITORY_ROOT / _ALLOWLIST_PATH).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AssertionError("base allowlist が JSON object でない")
    return value


def _lexical_function(source: str, symbol: str) -> ast.FunctionDef:
    """採用した2関数だけを、blockを越えてもlexical scopeを越えず解決する。"""
    assert symbol in _LEXICAL_SYMBOLS, "未登録のlexical symbol"
    current: ast.Module | ast.FunctionDef = ast.parse(source)
    for name in symbol.removeprefix(f"{_LEXICAL_MODULE}.").split("."):
        matches: list[ast.AST] = []

        def visit(node: ast.AST) -> None:
            """同じscopeの定義を集め、別関数/classの内部へは入らない。"""
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == name:
                    matches.append(node)
                return
            for child in ast.iter_child_nodes(node):
                visit(child)

        for statement in current.body:
            visit(statement)
        assert len(matches) == 1, "lexical定義が欠損または重複"
        match = matches[0]
        assert isinstance(match, ast.FunctionDef), "同期関数以外のlexical定義"
        assert not match.decorator_list and not match.type_params, "未知のlexical修飾"
        current = match
    assert isinstance(current, ast.FunctionDef)
    return current


def _resolve_symbol(symbol: str) -> object:
    """完全修飾名を import 可能な最長 module と属性列へ分けて解決する。"""
    if symbol in _LEXICAL_SYMBOLS:
        source = (
            _REPOSITORY_ROOT
            / "backend/src"
            / Path(*_LEXICAL_MODULE.split(".")).with_suffix(".py")
        )
        return _lexical_function(source.read_text(encoding="utf-8"), symbol)
    parts = symbol.split(".")
    for module_size in range(len(parts), 0, -1):
        module_name = ".".join(parts[:module_size])
        try:
            value: object = importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            if error.name is not None and not module_name.startswith(error.name):
                raise
            continue
        for attribute in parts[module_size:]:
            value = getattr(value, attribute)
        return value
    raise AssertionError(f"実装シンボルを解決できない: {symbol}")


def _declared_function(signature: str) -> ast.FunctionDef:
    """資産の署名を関数定義の構文木として読む。"""
    tree = ast.parse(f"def {signature}:\n    pass\n")
    assert len(tree.body) == 1
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    return function


def _declared_parameter_shape(
    function: ast.FunctionDef,
) -> tuple[tuple[str, object, object], ...]:
    """引数名・種類・既定値を実行時署名と同じ形へ落とす。"""

    def row(
        argument: ast.arg, kind: object, default: ast.expr | None = None
    ) -> tuple[str, object, object]:
        """1 引数の既定値をリテラルとして解釈する。"""
        value = (
            inspect.Parameter.empty if default is None else ast.literal_eval(default)
        )
        return argument.arg, kind, value

    arguments = function.args
    positional = [*arguments.posonlyargs, *arguments.args]
    defaults: list[ast.expr | None] = [None] * (
        len(positional) - len(arguments.defaults)
    ) + list(arguments.defaults)
    result = [
        row(argument, inspect.Parameter.POSITIONAL_ONLY, default)
        for argument, default in zip(
            arguments.posonlyargs, defaults[: len(arguments.posonlyargs)], strict=True
        )
    ]
    result.extend(
        row(argument, inspect.Parameter.POSITIONAL_OR_KEYWORD, default)
        for argument, default in zip(
            arguments.args, defaults[len(arguments.posonlyargs) :], strict=True
        )
    )
    if arguments.vararg is not None:
        result.append(row(arguments.vararg, inspect.Parameter.VAR_POSITIONAL))
    result.extend(
        row(argument, inspect.Parameter.KEYWORD_ONLY, default)
        for argument, default in zip(
            arguments.kwonlyargs, arguments.kw_defaults, strict=True
        )
    )
    if arguments.kwarg is not None:
        result.append(row(arguments.kwarg, inspect.Parameter.VAR_KEYWORD))
    return tuple(result)


def _declared_type_hints(
    function: ast.FunctionDef, namespace: dict[str, Any]
) -> dict[str, Any]:
    """宣言の型名を対象モジュールの名前空間で実際の型へ解決する。"""
    arguments = function.args
    parameters = [
        *arguments.posonlyargs,
        *arguments.args,
        *arguments.kwonlyargs,
    ]
    if arguments.vararg is not None:
        parameters.append(arguments.vararg)
    if arguments.kwarg is not None:
        parameters.append(arguments.kwarg)
    annotations = {
        argument.arg: ast.unparse(argument.annotation)
        for argument in parameters
        if argument.annotation is not None
    }
    if function.returns is not None:
        annotations["return"] = ast.unparse(function.returns)
    probe = type("_DeclaredAnnotations", (), {"__annotations__": annotations})
    return get_type_hints(
        probe, globalns=namespace, localns=namespace, include_extras=True
    )


def _assert_declared_runtime_signature(symbol: str, signature: str) -> None:
    """宣言と実装の関数形・解決済み型を過不足なく照合する。"""
    value = _resolve_symbol(symbol)
    if isinstance(value, ast.FunctionDef):
        namespace = vars(importlib.import_module(_LEXICAL_MODULE))
        _assert_lexical_signature(value, signature, namespace)
        return
    assert callable(value)
    callable_value = cast(Callable[..., object], value)
    function = _declared_function(signature)
    runtime = inspect.signature(callable_value)
    assert function.name == getattr(callable_value, "__name__", None)
    assert _declared_parameter_shape(function) == tuple(
        (parameter.name, parameter.kind, parameter.default)
        for parameter in runtime.parameters.values()
    )
    namespace = vars(importlib.import_module(callable_value.__module__))
    assert _declared_type_hints(function, namespace) == get_type_hints(
        callable_value, include_extras=True
    ), f"型注釈が不一致: {symbol}"


def _assert_lexical_signature(
    actual: ast.FunctionDef, signature: str, namespace: dict[str, Any]
) -> None:
    """実ASTの引数形とmodule名前空間で解決した型を既署名へ一致させる。"""
    declared = _declared_function(signature)
    assert declared.name == actual.name
    assert _declared_parameter_shape(declared) == _declared_parameter_shape(actual)
    assert _declared_type_hints(declared, namespace) == _declared_type_hints(
        actual, namespace
    ), "lexicalの型注釈が不一致"


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
            "transaction_scope_entry": repository_contract.TRANSACTION_SCOPE_ENTRY,
            "function_registration_type": (
                repository_contract.FUNCTION_REGISTRATION_TYPE
            ),
            "function_transaction_entry": (
                repository_contract.FUNCTION_TRANSACTION_ENTRY
            ),
            "function_operation_registry": (
                repository_contract.FUNCTION_OPERATION_REGISTRY
            ),
        },
        "executor": {
            "symbol": repository_contract.EXECUTOR_SYMBOL,
            "signature": repository_contract.EXECUTOR_SIGNATURE,
        },
        "function_executor": {
            "symbol": repository_contract.FUNCTION_EXECUTOR_SYMBOL,
            "signature": repository_contract.FUNCTION_EXECUTOR_SIGNATURE,
        },
        "return_contract": {
            "allowed_dtos": list(repository_contract.ALLOWED_DTOS),
            "scalar_type_match": repository_contract.SCALAR_TYPE_MATCH,
            "container_type_match": repository_contract.CONTAINER_TYPE_MATCH,
            "immutable_scalar_types": list(repository_contract.IMMUTABLE_SCALAR_TYPES),
            "immutable_container_grammar": list(
                repository_contract.IMMUTABLE_CONTAINER_GRAMMAR
            ),
            "forbidden_types": list(repository_contract.FORBIDDEN_TYPES),
        },
        "operation_guards": {
            "canonical_table": repository_contract.CANONICAL_TABLE,
            "update_identity": repository_contract.UPDATE_IDENTITY,
            "update_bind_names": repository_contract.UPDATE_BIND_NAMES,
            "tenant_primary_key_bind": repository_contract.TENANT_PRIMARY_KEY_BIND,
            "row_lock": repository_contract.ROW_LOCK,
            "unlocked_read": repository_contract.UNLOCKED_READ,
            "sync_apply_scope": repository_contract.SYNC_APPLY_SCOPE,
        },
        "product_capability_ids": list(repository_contract.PRODUCT_CAPABILITY_IDS),
        "product_operation_token_types": list(
            repository_contract.PRODUCT_OPERATION_TOKEN_TYPES
        ),
        "product_function_operation_ids": list(
            repository_contract.PRODUCT_FUNCTION_OPERATION_IDS
        ),
        "cross_tenant_functions": list(repository_contract.CROSS_TENANT_FUNCTIONS),
    }


def _asset_snapshot(asset: dict[str, Any]) -> dict[str, Any]:
    """更新履歴を除く生成対象フィールドを返す。"""
    snapshot = dict(asset)
    snapshot.pop("baseline_control", None)
    return snapshot


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
    assert _generated_snapshot() == _asset_snapshot(asset)


def test_declared_repository_symbols_resolve() -> None:
    """公開面と DB API 許可対象の全宣言が実装オブジェクトへ解決できる。"""
    contract = _read_contract()
    allowlist = _read_allowlist()
    declared_symbols = (
        *contract["public_surface"].values(),
        *(item["symbol"] for item in allowlist["allowed_symbols"]),
    )

    resolved = {symbol: _resolve_symbol(symbol) for symbol in declared_symbols}

    assert set(resolved) == set(declared_symbols)


def test_allowed_repository_symbol_signatures_match_runtime() -> None:
    """別名を実際の型へ解決して DB API 許可署名を exact 一致させる。"""
    allowlist = _read_allowlist()

    for item in allowlist["allowed_symbols"]:
        _assert_declared_runtime_signature(item["symbol"], item["signature"])


def test_allowed_symbol_wrong_aliased_type_is_red() -> None:
    """別名を用いた宣言でも型を取り違えれば照合が落ちる。"""
    for item in _read_allowlist()["allowed_symbols"]:
        function = _declared_function(item["signature"])
        value = _resolve_symbol(item["symbol"])
        if isinstance(value, ast.FunctionDef):
            namespace = vars(importlib.import_module(_LEXICAL_MODULE))
            actual_hints = _declared_type_hints(value, namespace)
        else:
            assert callable(value)
            namespace = vars(importlib.import_module(value.__module__))
            actual_hints = get_type_hints(value)
        for argument in [*function.args.posonlyargs, *function.args.args]:
            annotation = argument.annotation
            if not (
                isinstance(annotation, ast.Name)
                and annotation.id.startswith("_")
                and annotation.id in namespace
            ):
                continue
            _assert_declared_runtime_signature(item["symbol"], item["signature"])
            assert actual_hints[argument.arg] is not str
            argument.annotation = ast.Name(id="str", ctx=ast.Load())
            header = ast.unparse(function).splitlines()[0]
            assert header.startswith("def ") and header.endswith(":")
            mutated = header.removeprefix("def ").removesuffix(":")
            parsed = _declared_function(mutated)
            assert any(
                parameter.arg == argument.arg
                and isinstance(parameter.annotation, ast.Name)
                and parameter.annotation.id == "str"
                for parameter in [*parsed.args.posonlyargs, *parsed.args.args]
            )
            with pytest.raises(AssertionError, match="型注釈が不一致"):
                _assert_declared_runtime_signature(item["symbol"], mutated)
            return
    pytest.fail("別名を使う許可署名が見つからない")


def test_generated_repository_constant_surface_is_exact() -> None:
    """生成モジュールへ契約外の旧定数を残さない。"""
    expected = {
        "ALLOWED_DTOS",
        "ASSET_KIND",
        "CANONICALIZATION",
        "CONTAINER_TYPE_MATCH",
        "CONTEXT_BINDING_ENTRY",
        "CONTRACT_REVISION",
        "CANONICAL_TABLE",
        "CROSS_TENANT_FUNCTIONS",
        "CROSS_TENANT_FUNCTION_ENTRY",
        "CROSS_TENANT_FUNCTION_REGISTRY_SYMBOL",
        "EXECUTOR_SIGNATURE",
        "EXECUTOR_SYMBOL",
        "FUNCTION_REGISTRATION_TYPE",
        "FUNCTION_TRANSACTION_ENTRY",
        "FUNCTION_OPERATION_REGISTRY",
        "FUNCTION_EXECUTOR_SYMBOL",
        "FUNCTION_EXECUTOR_SIGNATURE",
        "FORBIDDEN_TYPES",
        "IMMUTABLE_CONTAINER_GRAMMAR",
        "IMMUTABLE_SCALAR_TYPES",
        "OPERATION_RESULT_TYPE",
        "OPERATION_TOKEN_TYPE",
        "PRODUCT_CAPABILITY_IDS",
        "PRODUCT_OPERATION_TOKEN_TYPES",
        "PRODUCT_FUNCTION_OPERATION_IDS",
        "REPOSITORY_TYPE",
        "ROW_LOCK",
        "SCALAR_TYPE_MATCH",
        "SCHEMA_VERSION",
        "SOURCE_ASSET",
        "SOURCE_DIGEST",
        "TENANT_PRIMARY_KEY_BIND",
        "SYNC_APPLY_SCOPE",
        "TRANSACTION_SCOPE_ENTRY",
        "UNLOCKED_READ",
        "UPDATE_BIND_NAMES",
        "UPDATE_IDENTITY",
    }
    actual = {
        name
        for name in vars(repository_contract)
        if name.isupper() and not name.startswith("_")
    }

    assert actual == expected


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
    assert (
        _public_signature_violations(
            hints["context"], hints["operation"], hints["return"]
        )
        == set()
    )
    assert getattr(TenantRepositoryBase.execute, "__final__", False) is True


def test_roster_capabilities_tokens_and_registry_are_exact() -> None:
    """選手・対戦相手・無効化意図の登録を契約と一致させる。"""
    expected_capabilities = (
        "CAP:players:read",
        "CAP:players:insert",
        "CAP:players:update",
        "CAP:team_records:read",
        "CAP:team_records:insert",
        "CAP:team_records:update",
        "CAP:games:read",
        "CAP:invalidation_intents:insert",
        "CAP:lineup_memories:read",
        "CAP:lineup_memories:insert",
        "CAP:lineup_memories:update",
        "CAP:recording_generations:read",
        "CAP:recording_generations:update",
        "CAP:event_slots:read",
        "CAP:event_slots:insert",
        "CAP:event_slots:update",
        "CAP:operation_events:read",
        "CAP:operation_events:insert",
        "CAP:operation_events:update",
        "CAP:temporary_player_id_mappings:read",
        "CAP:temporary_player_id_mappings:insert",
        "CAP:idempotency_ledger:read",
        "CAP:idempotency_ledger:insert",
        "CAP:rejected_event_originals:read",
        "CAP:rejected_event_originals:insert",
        "CAP:invalidation_intents:read",
        "CAP:invalidation_intents:update",
        "CAP:evacuated_event_originals:read",
        "CAP:evacuated_event_originals:insert",
        "CAP:tenants:read",
        "CAP:game_lineups:read",
        "CAP:play_rows:read",
        "CAP:play_rows:insert",
        "CAP:games:insert",
        "CAP:tenant_vocabularies:insert",
        "CAP:tenant_vocabularies:read",
    )
    expected_sync_operations = (
        ("GameReadToken", "CAP:games:read"),
        ("GameLockToken", "CAP:games:read"),
        ("RecordingGenerationReadToken", "CAP:recording_generations:read"),
        ("RecordingGenerationByNumberReadToken", "CAP:recording_generations:read"),
        ("RecordingGenerationLockToken", "CAP:recording_generations:read"),
        ("RecordingPrefixUpdateToken", "CAP:recording_generations:update"),
        ("EventSlotReadToken", "CAP:event_slots:read"),
        ("EventSlotInsertToken", "CAP:event_slots:insert"),
        ("EventSlotVersionUpdateToken", "CAP:event_slots:update"),
        ("OperationEventReadToken", "CAP:operation_events:read"),
        ("OperationEventOrderReadToken", "CAP:operation_events:read"),
        ("OperationEventInsertToken", "CAP:operation_events:insert"),
        ("OperationEventOrderUpdateToken", "CAP:operation_events:update"),
        ("OperationEventReplaceToken", "CAP:operation_events:update"),
        ("TemporaryPlayerMappingReadToken", "CAP:temporary_player_id_mappings:read"),
        (
            "TemporaryPlayerMappingInsertToken",
            "CAP:temporary_player_id_mappings:insert",
        ),
        ("IdempotencyLedgerReadToken", "CAP:idempotency_ledger:read"),
        ("IdempotencyLedgerInsertToken", "CAP:idempotency_ledger:insert"),
        ("RejectedOriginalReadToken", "CAP:rejected_event_originals:read"),
        ("RejectedOriginalInsertToken", "CAP:rejected_event_originals:insert"),
        ("InvalidationIntentReadToken", "CAP:invalidation_intents:read"),
        ("InvalidationIntentPendingToken", "CAP:invalidation_intents:read"),
        ("SyncInvalidationIntentInsertToken", "CAP:invalidation_intents:insert"),
        ("SyncSharedInvalidationIntentInsertToken", "CAP:invalidation_intents:insert"),
        ("InvalidationIntentDeliveredToken", "CAP:invalidation_intents:update"),
        ("EvacuatedOriginalReadToken", "CAP:evacuated_event_originals:read"),
        ("EvacuatedOriginalInsertToken", "CAP:evacuated_event_originals:insert"),
    )
    expected_token_types = (
        "pitchlog.repositories.roster.PlayerReadToken",
        "pitchlog.repositories.roster.PlayerCreateToken",
        "pitchlog.repositories.roster.PlayerUpdateToken",
        "pitchlog.repositories.roster.PlayerRosterStatusUpdateToken",
        "pitchlog.repositories.roster.PlayerRosterLabelUpdateToken",
        "pitchlog.repositories.roster.TeamRecordReadToken",
        "pitchlog.repositories.roster.SelfTeamRecordReadToken",
        "pitchlog.repositories.roster.TeamRecordCreateToken",
        "pitchlog.repositories.roster.TeamRecordUpdateToken",
        "pitchlog.repositories.roster.TeamRecordDeleteToken",
        "pitchlog.repositories.roster.GameTeamLinkReadToken",
        "pitchlog.repositories.invalidation_intents.InvalidationIntentInsertToken",
        "pitchlog.repositories.lineup_memory._SelfTeamLockToken",
        "pitchlog.repositories.lineup_memory._ActiveLineupPlayerLockToken",
        "pitchlog.repositories.lineup_memory.LineupMemoryReadToken",
        "pitchlog.repositories.lineup_memory._LineupMemoryInsertToken",
        "pitchlog.repositories.lineup_memory._LineupMemoryUpdateToken",
        *(f"pitchlog.sync.tokens.{name}" for name, _ in expected_sync_operations),
        "pitchlog.repositories.tenant_profile.TenantProfileReadToken",
        "pitchlog.repositories.games.PreparingGameListToken",
        "pitchlog.repositories.games.PreparingGameDetailToken",
        "pitchlog.repositories.started_snapshot_operations.StartedLineupsReadToken",
        "pitchlog.repositories.started_snapshot_operations.StartedEventSlotsExistenceToken",
        "pitchlog.repositories.started_snapshot_operations.StartedOperationEventsExistenceToken",
        "pitchlog.repositories.started_snapshot_operations.StartedPlayRowsExistenceToken",
        "pitchlog.sync.first_ball_tokens.FirstBallPlayRowInsertToken",
        "pitchlog.sync.first_ball_tokens.FirstBallPlayRowReadToken",
        "pitchlog.repositories.recorded_snapshot_operations.RecordedEventRowsReadToken",
        "pitchlog.repositories.recorded_snapshot_operations.RecordedEventSlotsReadToken",
        "pitchlog.repositories.recorded_snapshot_operations.RecordedPlayRowsReadToken",
        "pitchlog.repositories.preparing_game_creation.PreparingGameInsertToken",
        "pitchlog.repositories.preparing_game_creation.PreparingTournamentInsertToken",
        "pitchlog.repositories.preparing_game_creation.PreparingTournamentOptionsToken",
        "pitchlog.repositories.preparing_game_creation.PreparingTournamentNameExistsToken",
        "pitchlog.repositories.preparing_game_creation.PreparingTournamentParentToken",
        "pitchlog.repositories.preparing_game_creation.PreparingSelfTeamLockToken",
        "pitchlog.repositories.preparing_game_creation.PreparingOpponentTeamLockToken",
        "pitchlog.repositories.pitch_type_options.PitchTypeOptionsToken",
        "pitchlog.sync.ordinary_pitch_tokens.OrdinaryPlayRowInsertToken",
    )
    assert repository_contract.PRODUCT_CAPABILITY_IDS == expected_capabilities
    assert repository_contract.PRODUCT_OPERATION_TOKEN_TYPES == expected_token_types
    assert len(expected_token_types) == 65
    assert (
        repository_contract.CROSS_TENANT_FUNCTION_ENTRY
        == repository_contract.CONTEXT_BINDING_ENTRY
    )
    assert type(repository_base._OPERATION_REGISTRY) is MappingProxyType
    assert {
        f"{token_type.__module__}.{token_type.__qualname__}": spec.capability_id
        for token_type, spec in repository_base._OPERATION_REGISTRY.items()
    } == dict(
        zip(
            expected_token_types,
            (
                *expected_capabilities[:3],
                "CAP:players:update",
                "CAP:players:update",
                expected_capabilities[3],
                expected_capabilities[3],
                *expected_capabilities[4:6],
                "CAP:team_records:update",
                expected_capabilities[6],
                expected_capabilities[7],
                expected_capabilities[3],
                expected_capabilities[0],
                *expected_capabilities[8:11],
                *(capability for _, capability in expected_sync_operations),
                "CAP:tenants:read",
                "CAP:games:read",
                "CAP:games:read",
                "CAP:game_lineups:read",
                "CAP:event_slots:read",
                "CAP:operation_events:read",
                "CAP:play_rows:read",
                "CAP:play_rows:insert",
                "CAP:play_rows:read",
                "CAP:operation_events:read",
                "CAP:event_slots:read",
                "CAP:play_rows:read",
                "CAP:games:insert",
                "CAP:tenant_vocabularies:insert",
                "CAP:tenant_vocabularies:read",
                "CAP:tenant_vocabularies:read",
                "CAP:tenant_vocabularies:read",
                "CAP:team_records:read",
                "CAP:team_records:read",
                "CAP:tenant_vocabularies:read",
                "CAP:play_rows:insert",
            ),
            strict=True,
        )
    )
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
    assert repository_contract.SCALAR_TYPE_MATCH == "exact"
    assert repository_contract.CONTAINER_TYPE_MATCH == "exact"
    assert repository_contract.IMMUTABLE_SCALAR_TYPES == expected_scalars
    assert runtime_types == expected_scalars
    assert repository_contract.IMMUTABLE_CONTAINER_GRAMMAR == (
        "tuple[T, ...]",
        "frozenset[T]",
        "mappingproxy[str, T]",
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
        object(),
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

    assert result.rows == (((tenant_id, "marker", (1, True), frozenset({"sealed"}))),)
    with pytest.raises(FrozenInstanceError):
        setattr(result, "rows", ())


def _leaky_immutable_subclasses(handle: object) -> tuple[tuple[str, object], ...]:
    """DB ハンドルを属性に保持する許可型サブクラスを生成する。"""
    specifications: tuple[tuple[str, type[object], tuple[object, ...]], ...] = (
        ("int", int, (1,)),
        ("float", float, (1.0,)),
        ("str", str, ("value",)),
        ("bytes", bytes, (b"value",)),
        ("uuid", UUID, ("00000000-0000-0000-0000-000000000909",)),
        ("decimal", Decimal, ("1.0",)),
        ("date", date, (2026, 9, 19)),
        ("datetime", datetime, (2026, 9, 19, 12, 0)),
        ("time", time, (12, 0)),
        ("tuple", tuple, ((1, 2),)),
        ("frozenset", frozenset, ({1, 2},)),
    )
    values: list[tuple[str, object]] = []
    for name, base_type, arguments in specifications:
        mutation_type = type(f"Leaky{name.title()}", (base_type,), {})
        value = mutation_type(*arguments)
        object.__setattr__(value, "database_handle", handle)
        values.append((name, value))
    return tuple(values)


def test_immutable_subclasses_cannot_leak_database_handles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全サブクラス化可能型が DB ハンドルを保持しても公開されない。"""
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
    context = make_tenant_context(_repository_contract_test_tenant_id())
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with Session(engine) as session:
            raw_result = session.execute(text("SELECT 1"))
            for handle in (session, raw_result, object()):
                for type_name, value in _leaky_immutable_subclasses(handle):
                    with pytest.raises(
                        _TenantOperationError,
                        match="許可されていない",
                    ):
                        _materialize_rows(((value,),))
                    with pytest.raises(
                        _TenantOperationError,
                        match="許可されていない",
                    ):
                        _UnsafeReturnRepository(
                            TenantOperationResult(
                                rows=cast(
                                    tuple[tuple[ImmutableValue, ...], ...],
                                    ((value,),),
                                )
                            )
                        ).execute(context, token)
                    assert type_name
    finally:
        engine.dispose()


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
        "function_executor",
        "return_contract",
        "operation_guards",
        "product_capability_ids",
        "product_operation_token_types",
        "product_function_operation_ids",
        "cross_tenant_functions",
    ),
)
def test_each_stale_generated_repository_field_is_red(field: str) -> None:
    """生成モジュールの各フィールドが古い変異を一致検査で検出する。"""
    generated = _generated_snapshot()
    generated[field] = object()

    assert generated != _asset_snapshot(_read_contract())


def test_stage_a_function_registration_matches_exact_asset_and_retains_rg1() -> None:
    """旧8と端末状態read登録の生成全fieldを照合し、DMLとは混同しない。"""
    from pitchlog.repositories.operation_registry import (
        PRODUCT_FUNCTION_OPERATIONS,
        PRODUCT_OPERATIONS,
    )
    from pitchlog.repositories.rule_resolution import StageAResolveRuleToken

    asset = _read_contract()
    expected = (
        "RG1:precheck",
        "RG1:commit_check",
        "RG1:scope_binding",
        "RULE:resolve_stage_a",
        "SYNC_FIRST_BALL:bind_device",
        "SYNC_FIRST_BALL:check_current_right",
        "SYNC_WRITER_BINDING:read_writer_identity",
        "SYNC_WRITER_BINDING:assert_writer_binding",
        "SYNC_FIRST_BALL:read_device_state",
        "SYNC_ORDINARY_PITCH:bind_ordinary_device",
        "SYNC_ORDINARY_PITCH:check_ordinary_right",
        "SYNC_ORDINARY_PITCH:prepare_ordinary_projection",
        "SYNC_ORDINARY_PITCH:read_ordinary_checkpoint",
        "SYNC_ORDINARY_PITCH:lock_ordinary_checkpoint",
        "SYNC_ORDINARY_PITCH:read_ordinary_history_page",
        "SYNC_ORDINARY_PITCH:read_ordinary_order_summary",
    )
    assert tuple(asset["product_function_operation_ids"]) == expected
    assert repository_contract.PRODUCT_FUNCTION_OPERATION_IDS == expected
    assert tuple(row.operation_id for row in PRODUCT_FUNCTION_OPERATIONS) == expected
    assert tuple(row.function_id for row in PRODUCT_FUNCTION_OPERATIONS) == (
        "rg1_api.rg1_read_open",
        "rg1_api.rg1_assert_open_before_commit",
        "rg1_control.scope_binding",
        "public.resolve_stage_a_rule",
        "sync_right_api.bind_device",
        "sync_right_api.check_current_right",
        "sync_fence_api.read_writer_identity",
        "sync_fence_api.assert_writer_binding",
        "sync_right_api.read_device_state",
        "sync_right_api.bind_ordinary_device",
        "sync_right_api.check_ordinary_right",
        "sync_right_api.prepare_ordinary_projection",
        "sync_right_api.read_ordinary_checkpoint",
        "sync_right_api.lock_ordinary_checkpoint",
        "sync_right_api.read_ordinary_history_page",
        "sync_right_api.read_ordinary_order_summary",
    )
    from pitchlog.repositories.rg1 import (
        RG1CommitCheckToken,
        RG1PrecheckToken,
        RG1ScopeBindingToken,
    )

    for row, token, capability, result in zip(
        PRODUCT_FUNCTION_OPERATIONS[:3],
        (RG1PrecheckToken, RG1CommitCheckToken, RG1ScopeBindingToken),
        ("CAP:rg1:precheck", "CAP:rg1:commit_check", "CAP:rg1:scope_binding"),
        ((("is_open", bool),), (("is_open", bool),), (("binding", str),)),
        strict=True,
    ):
        assert row.token_type is token
        assert row.capability_id == capability
        assert row.input_fields == row.nonempty_inputs == ()
        assert row.result_fields == result
        assert row.statement.compile().params == {"tenant_id": None}
        assert row.min_rows == row.max_rows == 1
        assert all(item.token_type is not token for item in PRODUCT_OPERATIONS)
    registration = PRODUCT_FUNCTION_OPERATIONS[3]
    assert registration.token_type is StageAResolveRuleToken
    assert registration.capability_id == "CAP:rules:resolve_stage_a"
    assert registration.input_fields == (
        ("game_type_key", str),
        ("tournament_key", str),
        ("has_override", bool),
    )
    assert registration.nonempty_inputs == ("game_type_key", "tournament_key")
    assert registration.result_fields == (("resolution", MappingProxyType),)
    assert registration.min_rows == registration.max_rows == 1
    assert all(
        row.token_type is not StageAResolveRuleToken for row in PRODUCT_OPERATIONS
    )
    assert _generated_snapshot() == _asset_snapshot(asset)


@pytest.mark.parametrize(
    "function_id", ("public.unregistered_rule", "other.resolve_stage_a_rule")
)
def test_stage_a_function_identity_mutation_is_rejected(function_id: str) -> None:
    """既存factoryと異なるDB関数への登録差替えを拒否する。"""
    from dataclasses import replace

    from pitchlog.repositories.function_operations import FunctionOperationError
    from pitchlog.repositories.operation_registry import PRODUCT_FUNCTION_OPERATIONS

    with pytest.raises(FunctionOperationError):
        replace(PRODUCT_FUNCTION_OPERATIONS[3], function_id=function_id)


@pytest.mark.parametrize("symbol", sorted(_LEXICAL_SYMBOLS))
@pytest.mark.parametrize(
    "mutation", ("missing", "other-scope", "duplicate", "class", "async", "decorated")
)
def test_lexical_symbols_reject_missing_duplicate_or_wrong_scope(
    symbol: str,
    mutation: str,
) -> None:
    """同名の別scope・欠損・複数・classをruntime除外の代用にしない。"""
    module = importlib.import_module(_LEXICAL_MODULE)
    assert module.__file__ is not None
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    target = _lexical_function(source, symbol)
    for parent in ast.walk(tree):
        for _, value in ast.iter_fields(parent):
            if not isinstance(value, list):
                continue
            found = next(
                (
                    node
                    for node in value
                    if isinstance(node, ast.FunctionDef)
                    and node.lineno == target.lineno
                ),
                None,
            )
            if found is None:
                continue
            if mutation == "duplicate":
                value.append(copy.deepcopy(found))
            elif mutation == "decorated":
                found.decorator_list = [ast.Name(id="unexpected", ctx=ast.Load())]
            elif mutation == "async":
                value[value.index(found)] = ast.parse(
                    f"async def {found.name}():\n    pass\n"
                ).body[0]
            elif mutation == "class":
                value[value.index(found)] = ast.ClassDef(
                    name=found.name,
                    bases=[],
                    keywords=[],
                    body=[ast.Pass()],
                    decorator_list=[],
                    type_params=[],
                )
            else:
                value.remove(found)
                if mutation == "other-scope":
                    value.append(
                        ast.FunctionDef(
                            name="other_scope",
                            args=ast.arguments(
                                posonlyargs=[],
                                args=[],
                                kwonlyargs=[],
                                kw_defaults=[],
                                defaults=[],
                            ),
                            body=[found],
                            decorator_list=[],
                            type_params=[],
                        )
                    )
            with pytest.raises(AssertionError, match="lexical"):
                _lexical_function(ast.unparse(ast.fix_missing_locations(tree)), symbol)
            return
    pytest.fail("実lexical関数の親が見つからない")


@pytest.mark.parametrize("symbol", sorted(_LEXICAL_SYMBOLS))
@pytest.mark.parametrize("mutation", ("parameter", "return", "kind", "alias"))
def test_lexical_signatures_reject_type_and_parameter_mutations(
    symbol: str,
    mutation: str,
) -> None:
    """閉じた2署名でも型/返値/引数種別/誤aliasを独立に拒否する。"""
    module = importlib.import_module(_LEXICAL_MODULE)
    assert module.__file__ is not None
    actual = _lexical_function(
        Path(module.__file__).read_text(encoding="utf-8"), symbol
    )
    signature = next(
        row["signature"]
        for row in _read_allowlist()["allowed_symbols"]
        if row["symbol"] == symbol
    )
    namespace = dict(vars(module))
    _assert_lexical_signature(actual, signature, namespace)
    if mutation == "kind":
        actual.args.posonlyargs = [actual.args.args.pop(0)]
    elif mutation == "return":
        actual.returns = ast.Name(id="str", ctx=ast.Load())
    else:
        argument = actual.args.args[0]
        wrong = (
            int if _declared_type_hints(actual, namespace)[argument.arg] is str else str
        )
        if mutation == "alias":
            namespace["_WrongLexicalAlias"] = wrong
            argument.annotation = ast.Name(id="_WrongLexicalAlias", ctx=ast.Load())
        else:
            argument.annotation = ast.Name(id=wrong.__name__, ctx=ast.Load())
    with pytest.raises(AssertionError):
        _assert_lexical_signature(actual, signature, namespace)


def test_unregistered_lexical_symbol_is_rejected() -> None:
    """登録2symbolの後方/似た名前をlexical許可へ拡張しない。"""
    for symbol in _LEXICAL_SYMBOLS:
        with pytest.raises(AssertionError, match="未登録"):
            _lexical_function("", symbol + ".extra")
