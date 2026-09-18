"""テナント境界の迂回を AST と import 境界で検査する。"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_INVENTORY = Path("contracts/tenant_boundary/db-api-inventory.json")
DEFAULT_ALLOWLIST = Path("contracts/tenant_boundary/base-allowlist.json")
DEFAULT_NEGATIVE_FIXTURES = Path(
    "contracts/tenant_boundary/negative-fixtures.json"
)
DEFAULT_TENANT_CONTEXT_ALLOWLIST = Path(
    "contracts/tenant_boundary/tenant-context-allowlist.json"
)
DEFAULT_CACHE_INVALIDATION_CONTRACT = Path(
    "contracts/tenant_boundary/cache-invalidation-contract.json"
)
EXPECTED_DIFF_COMMAND = (
    "git",
    "diff",
    "-U0",
    "origin/develop...HEAD",
    "--",
    "backend/src",
)
EXPECTED_CI_JOB = "tenant-boundary-bypass"
EXPECTED_CI_COMMAND = "uv run python scripts/check_tenant_boundary_bypass.py"
EXPECTED_TENANT_CONTEXT_CONSTRUCTOR = (
    "pitchlog.repositories.context.TenantContext"
)
CONDITION_IDS = frozenset({1, 2, 3, 4, 5})
SET_TENANT_RE = re.compile(
    r"\bSET\s+(?!(?:LOCAL)\b)(?:SESSION\s+)?app\.tenant_id\b", re.IGNORECASE
)
NONLOCAL_SET_CONFIG_RE = re.compile(
    r"set_config\s*\(.*?,\s*(?:false|'false'|\"false\")\s*\)",
    re.IGNORECASE | re.DOTALL,
)


class ContractError(ValueError):
    """検査契約の不整合を表す。"""


@dataclass(frozen=True)
class ApiSpec:
    """閉じた DB 到達 API の 1 要素を表す。"""

    id: str
    symbol: str
    kind: str
    receivers: tuple[str, ...]


@dataclass(frozen=True)
class AllowedSymbol:
    """DB 到達を許可する完全修飾シンボルを表す。"""

    symbol: str
    signature: str
    allowed_api_ids: frozenset[str]
    fixture: str


@dataclass(frozen=True)
class ConditionRule:
    """条件 1〜4 の禁止識別子規則を表す。"""

    condition: int
    error: str
    patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class NegativeFixture:
    """負例 fixture の契約行を表す。"""

    id: str
    path: str
    condition: int
    mutation: str
    expected_error: str


@dataclass(frozen=True)
class TenantContextConstructionContract:
    """TenantContext の構築を許可するモジュール集合を表す。"""

    schema_version: int
    contract_revision: int
    source_digest: str
    constructor_symbol: str
    allowed_test_modules: frozenset[str]
    allowed_product_modules: frozenset[str]


@dataclass(frozen=True)
class CacheInvalidationBypassContract:
    """条件 4 で参照・呼び出しを許す単一 API 境界を表す。"""

    provider_module: str
    factory_symbol: str
    public_symbols: frozenset[str]
    allowed_call_symbols: frozenset[str]


@dataclass(frozen=True)
class Contract:
    """検査に必要な資産を読み合わせた契約を表す。"""

    apis: tuple[ApiSpec, ...]
    allowed_symbols: tuple[AllowedSymbol, ...]
    rules: tuple[ConditionRule, ...]
    negative_fixtures: tuple[NegativeFixture, ...]
    tenant_context: TenantContextConstructionContract
    cache_invalidation: CacheInvalidationBypassContract


@dataclass(frozen=True, order=True)
class Violation:
    """検出した迂回または検査契約違反を表す。"""

    path: str
    line: int
    condition: int
    code: str
    symbol: str
    message: str


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    """JSON オブジェクトと元のバイト列を読む。

    Args:
        path: 読み込む JSON のパス。

    Returns:
        JSON オブジェクトと元のバイト列。

    Raises:
        ContractError: ファイルが無い、JSON でない、またはルートがオブジェクトでない場合。
    """
    try:
        source = path.read_bytes()
    except OSError as error:
        raise ContractError(f"契約資産を読めない: {path}: {error}") from error
    try:
        value = json.loads(source)
    except json.JSONDecodeError as error:
        raise ContractError(f"契約資産が JSON でない: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ContractError(f"契約資産のルートはオブジェクトでなければならない: {path}")
    return value, source


def _strict_keys(value: Mapping[str, object], expected: Set[str], location: str) -> None:
    """オブジェクトのキー集合を exact-set で検査する。

    Args:
        value: 検査対象のオブジェクト。
        expected: 期待するキー集合。
        location: エラー表示用の位置。

    Raises:
        ContractError: キーに過不足がある場合。
    """
    actual = set(value)
    if actual != set(expected):
        raise ContractError(
            f"{location}: キー集合が不一致: missing={sorted(set(expected) - actual)}, "
            f"extra={sorted(actual - set(expected))}"
        )


def _string(value: object, location: str) -> str:
    """空でない文字列を取得する。

    Args:
        value: 検査対象。
        location: エラー表示用の位置。

    Returns:
        検証済み文字列。

    Raises:
        ContractError: 空でない文字列でない場合。
    """
    if not isinstance(value, str) or not value:
        raise ContractError(f"{location}: 空でない文字列が必要")
    return value


def _integer(value: object, location: str) -> int:
    """bool でない整数を取得する。

    Args:
        value: 検査対象。
        location: エラー表示用の位置。

    Returns:
        検証済み整数。

    Raises:
        ContractError: 整数でない場合。
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{location}: 整数が必要")
    return value


def _object(value: object, location: str) -> dict[str, Any]:
    """文字列キーのオブジェクトを取得する。

    Args:
        value: 検査対象。
        location: エラー表示用の位置。

    Returns:
        検証済みオブジェクト。

    Raises:
        ContractError: オブジェクトでないか文字列以外のキーを含む場合。
    """
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ContractError(f"{location}: 文字列キーのオブジェクトが必要")
    return value


def _array(value: object, location: str) -> list[object]:
    """配列を取得する。

    Args:
        value: 検査対象。
        location: エラー表示用の位置。

    Returns:
        検証済み配列。

    Raises:
        ContractError: 配列でない場合。
    """
    if not isinstance(value, list):
        raise ContractError(f"{location}: 配列が必要")
    return value


def _string_array(value: object, location: str) -> tuple[str, ...]:
    """重複のない文字列配列を取得する。

    Args:
        value: 検査対象。
        location: エラー表示用の位置。

    Returns:
        検証済み文字列の組。

    Raises:
        ContractError: 配列要素が文字列でないか重複する場合。
    """
    items = tuple(_string(item, f"{location}[]") for item in _array(value, location))
    if len(items) != len(set(items)):
        raise ContractError(f"{location}: 重複を許可しない")
    return items


def _load_inventory(value: dict[str, Any]) -> tuple[ApiSpec, ...]:
    """DB API inventory を検証して読む。"""
    _strict_keys(
        value,
        {"schema_version", "inventory_revision", "closed_world", "apis"},
        "db-api-inventory.json",
    )
    if _integer(value["schema_version"], "inventory.schema_version") != 1:
        raise ContractError("inventory.schema_version は 1 でなければならない")
    if _integer(value["inventory_revision"], "inventory.inventory_revision") < 1:
        raise ContractError("inventory.inventory_revision は 1 以上でなければならない")
    if value["closed_world"] is not True:
        raise ContractError("inventory.closed_world は true でなければならない")

    apis: list[ApiSpec] = []
    for index, raw in enumerate(_array(value["apis"], "inventory.apis")):
        item = _object(raw, f"inventory.apis[{index}]")
        _strict_keys(
            item,
            {"id", "symbol", "kind", "receivers"},
            f"inventory.apis[{index}]",
        )
        kind = _string(item["kind"], f"inventory.apis[{index}].kind")
        if kind not in {"function", "member"}:
            raise ContractError(f"inventory.apis[{index}].kind が未知: {kind}")
        receivers = _string_array(
            item["receivers"], f"inventory.apis[{index}].receivers"
        )
        if kind == "member" and not receivers:
            raise ContractError(f"inventory.apis[{index}]: member には receivers が必要")
        if kind == "function" and receivers:
            raise ContractError(f"inventory.apis[{index}]: function の receivers は空にする")
        apis.append(
            ApiSpec(
                id=_string(item["id"], f"inventory.apis[{index}].id"),
                symbol=_string(item["symbol"], f"inventory.apis[{index}].symbol"),
                kind=kind,
                receivers=receivers,
            )
        )
    if not apis:
        raise ContractError("inventory.apis は空にできない")
    ids = [api.id for api in apis]
    symbols = [api.symbol for api in apis]
    if len(ids) != len(set(ids)) or len(symbols) != len(set(symbols)):
        raise ContractError("inventory.apis の id と symbol はそれぞれ一意でなければならない")
    return tuple(apis)


def _load_allowlist(
    value: dict[str, Any], inventory_bytes: bytes, apis: tuple[ApiSpec, ...]
) -> tuple[tuple[AllowedSymbol, ...], tuple[ConditionRule, ...]]:
    """基底 allowlist と禁止識別子規則を検証して読む。"""
    _strict_keys(
        value,
        {
            "schema_version",
            "contract_revision",
            "diff",
            "ci",
            "inventory",
            "allowed_symbols",
            "conditions",
        },
        "base-allowlist.json",
    )
    if _integer(value["schema_version"], "allowlist.schema_version") != 1:
        raise ContractError("allowlist.schema_version は 1 でなければならない")
    if _integer(value["contract_revision"], "allowlist.contract_revision") < 1:
        raise ContractError("allowlist.contract_revision は 1 以上でなければならない")

    diff = _object(value["diff"], "allowlist.diff")
    _strict_keys(diff, {"command"}, "allowlist.diff")
    command = _string_array(diff["command"], "allowlist.diff.command")
    if command != EXPECTED_DIFF_COMMAND:
        raise ContractError(
            f"diff コマンドが固定値と不一致: expected={EXPECTED_DIFF_COMMAND}, actual={command}"
        )

    ci = _object(value["ci"], "allowlist.ci")
    _strict_keys(ci, {"job", "command"}, "allowlist.ci")
    if _string(ci["job"], "allowlist.ci.job") != EXPECTED_CI_JOB:
        raise ContractError(f"CI ジョブ名は {EXPECTED_CI_JOB} でなければならない")
    if _string(ci["command"], "allowlist.ci.command") != EXPECTED_CI_COMMAND:
        raise ContractError(f"CI コマンドは {EXPECTED_CI_COMMAND} でなければならない")

    inventory = _object(value["inventory"], "allowlist.inventory")
    _strict_keys(
        inventory, {"path", "schema_version", "sha256"}, "allowlist.inventory"
    )
    if _string(inventory["path"], "allowlist.inventory.path") != str(
        DEFAULT_INVENTORY
    ):
        raise ContractError("allowlist.inventory.path が固定パスと不一致")
    if _integer(inventory["schema_version"], "allowlist.inventory.schema_version") != 1:
        raise ContractError("allowlist が参照する inventory schema が不一致")
    expected_digest = _string(inventory["sha256"], "allowlist.inventory.sha256")
    actual_digest = hashlib.sha256(inventory_bytes).hexdigest()
    if expected_digest != actual_digest:
        raise ContractError(
            "DB API inventory の集合が封印値と不一致。集合の改訂は allowlist 側の明示更新も必要: "
            f"expected={expected_digest}, actual={actual_digest}"
        )

    api_ids = {api.id for api in apis}
    allowed_symbols: list[AllowedSymbol] = []
    for index, raw in enumerate(
        _array(value["allowed_symbols"], "allowlist.allowed_symbols")
    ):
        item = _object(raw, f"allowlist.allowed_symbols[{index}]")
        _strict_keys(
            item,
            {"symbol", "signature", "allowed_api_ids", "fixture"},
            f"allowlist.allowed_symbols[{index}]",
        )
        allowed_api_ids = frozenset(
            _string_array(
                item["allowed_api_ids"],
                f"allowlist.allowed_symbols[{index}].allowed_api_ids",
            )
        )
        unknown_api_ids = allowed_api_ids - api_ids
        if unknown_api_ids:
            raise ContractError(
                f"allowlist.allowed_symbols[{index}] が inventory 外 API を参照: "
                f"{sorted(unknown_api_ids)}"
            )
        allowed_symbols.append(
            AllowedSymbol(
                symbol=_string(
                    item["symbol"], f"allowlist.allowed_symbols[{index}].symbol"
                ),
                signature=_string(
                    item["signature"],
                    f"allowlist.allowed_symbols[{index}].signature",
                ),
                allowed_api_ids=allowed_api_ids,
                fixture=_string(
                    item["fixture"], f"allowlist.allowed_symbols[{index}].fixture"
                ),
            )
        )
    symbols = [item.symbol for item in allowed_symbols]
    fixtures = [item.fixture for item in allowed_symbols]
    if not allowed_symbols or len(symbols) != len(set(symbols)):
        raise ContractError("allowed_symbols は空にできず、symbol は一意でなければならない")
    if len(fixtures) != len(set(fixtures)):
        raise ContractError("allowed_symbols.fixture は一意でなければならない")

    rules: list[ConditionRule] = []
    conditions = _array(value["conditions"], "allowlist.conditions")
    for index, raw in enumerate(conditions):
        item = _object(raw, f"allowlist.conditions[{index}]")
        _strict_keys(
            item,
            {"condition", "error", "patterns"},
            f"allowlist.conditions[{index}]",
        )
        condition = _integer(
            item["condition"], f"allowlist.conditions[{index}].condition"
        )
        if condition not in {1, 2, 3, 4}:
            raise ContractError("conditions には条件 1〜4 だけを置く")
        compiled: list[re.Pattern[str]] = []
        for pattern in _string_array(
            item["patterns"], f"allowlist.conditions[{index}].patterns"
        ):
            try:
                compiled.append(re.compile(pattern))
            except re.error as error:
                raise ContractError(
                    f"allowlist.conditions[{index}] の正規表現が不正: {pattern}: {error}"
                ) from error
        if not compiled:
            raise ContractError(f"allowlist.conditions[{index}].patterns は空にできない")
        rules.append(
            ConditionRule(
                condition=condition,
                error=_string(
                    item["error"], f"allowlist.conditions[{index}].error"
                ),
                patterns=tuple(compiled),
            )
        )
    if {rule.condition for rule in rules} != {1, 2, 3, 4}:
        raise ContractError("conditions の条件番号は 1〜4 の exact-set でなければならない")
    return tuple(allowed_symbols), tuple(rules)


def _load_negative_fixtures(value: dict[str, Any]) -> tuple[NegativeFixture, ...]:
    """負例 fixture の全数表を検証して読む。"""
    _strict_keys(
        value,
        {"schema_version", "fixture_root", "fixtures"},
        "negative-fixtures.json",
    )
    if _integer(value["schema_version"], "negative.schema_version") != 1:
        raise ContractError("negative.schema_version は 1 でなければならない")
    if _string(value["fixture_root"], "negative.fixture_root") != (
        "tests/fixtures/tenant_boundary/negative"
    ):
        raise ContractError("negative.fixture_root が固定パスと不一致")
    fixtures: list[NegativeFixture] = []
    for index, raw in enumerate(_array(value["fixtures"], "negative.fixtures")):
        item = _object(raw, f"negative.fixtures[{index}]")
        _strict_keys(
            item,
            {"id", "path", "condition", "mutation", "expected_error"},
            f"negative.fixtures[{index}]",
        )
        condition = _integer(item["condition"], f"negative.fixtures[{index}].condition")
        if condition not in CONDITION_IDS:
            raise ContractError(f"negative.fixtures[{index}].condition が未知")
        expected_error = _string(
            item["expected_error"], f"negative.fixtures[{index}].expected_error"
        )
        if expected_error != f"TB00{condition}":
            raise ContractError(
                f"negative.fixtures[{index}].expected_error は TB00{condition} が必要"
            )
        fixtures.append(
            NegativeFixture(
                id=_string(item["id"], f"negative.fixtures[{index}].id"),
                path=_string(item["path"], f"negative.fixtures[{index}].path"),
                condition=condition,
                mutation=_string(
                    item["mutation"], f"negative.fixtures[{index}].mutation"
                ),
                expected_error=expected_error,
            )
        )
    ids = [fixture.id for fixture in fixtures]
    paths = [fixture.path for fixture in fixtures]
    if not fixtures or len(ids) != len(set(ids)) or len(paths) != len(set(paths)):
        raise ContractError("負例 fixture の id と path は空でなく、それぞれ一意でなければならない")
    if {fixture.condition for fixture in fixtures} != CONDITION_IDS:
        raise ContractError("負例 fixture は条件 1〜5 をすべて含まなければならない")
    return tuple(fixtures)


def _load_tenant_context_allowlist(
    value: dict[str, Any],
) -> TenantContextConstructionContract:
    """TenantContext の生成箇所 allowlist を検証して読む。

    Args:
        value: JSON 資産から読んだオブジェクト。

    Returns:
        検証済みの生成箇所契約。

    Raises:
        ContractError: 資産の形式、封印値、または初期閉鎖状態が不正な場合。
    """
    _strict_keys(
        value,
        {
            "schema_version",
            "contract_revision",
            "asset_kind",
            "canonicalization",
            "source_digest",
            "constructor_symbol",
            "allowed_test_modules",
            "allowed_product_modules",
        },
        "tenant-context-allowlist.json",
    )
    schema_version = _integer(
        value["schema_version"], "tenant_context.schema_version"
    )
    if schema_version != 1:
        raise ContractError("tenant_context.schema_version は 1 でなければならない")
    contract_revision = _integer(
        value["contract_revision"], "tenant_context.contract_revision"
    )
    if contract_revision < 1:
        raise ContractError("tenant_context.contract_revision は 1 以上が必要")
    if (
        _string(value["asset_kind"], "tenant_context.asset_kind")
        != "tenant_context_construction_allowlist"
    ):
        raise ContractError("tenant_context.asset_kind が固定値と不一致")
    if (
        _string(value["canonicalization"], "tenant_context.canonicalization")
        != "json-sort-keys-utf8-v1"
    ):
        raise ContractError("tenant_context.canonicalization が固定値と不一致")

    expected_digest = _string(
        value["source_digest"], "tenant_context.source_digest"
    )
    digest_payload = dict(value)
    digest_payload.pop("source_digest")
    serialized = json.dumps(
        digest_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    actual_digest = hashlib.sha256(serialized).hexdigest()
    if expected_digest != actual_digest:
        raise ContractError(
            "TenantContext allowlist の封印値が不一致: "
            f"expected={expected_digest}, actual={actual_digest}"
        )

    constructor_symbol = _string(
        value["constructor_symbol"], "tenant_context.constructor_symbol"
    )
    if constructor_symbol != EXPECTED_TENANT_CONTEXT_CONSTRUCTOR:
        raise ContractError("TenantContext のコンストラクタシンボルが固定値と不一致")
    allowed_test_modules = frozenset(
        _string_array(
            value["allowed_test_modules"], "tenant_context.allowed_test_modules"
        )
    )
    if not allowed_test_modules:
        raise ContractError("TenantContext のテスト専用生成経路は空にできない")
    if any(
        module == "pitchlog" or module.startswith("pitchlog.")
        for module in allowed_test_modules
    ):
        raise ContractError("テスト用 allowlist に製品モジュールを置けない")
    allowed_product_modules = frozenset(
        _string_array(
            value["allowed_product_modules"],
            "tenant_context.allowed_product_modules",
        )
    )
    if allowed_product_modules:
        raise ContractError(
            "U-A1 / TSK-217 が未導入のため製品モジュールの生成経路は 0 件が必要"
        )
    return TenantContextConstructionContract(
        schema_version=schema_version,
        contract_revision=contract_revision,
        source_digest=expected_digest,
        constructor_symbol=constructor_symbol,
        allowed_test_modules=allowed_test_modules,
        allowed_product_modules=allowed_product_modules,
    )


def _load_cache_invalidation_bypass_contract(
    value: dict[str, Any],
) -> CacheInvalidationBypassContract:
    """条件 4 の許可側をキャッシュ無効化契約資産から読む。

    Args:
        value: JSON 資産から読んだオブジェクト。

    Returns:
        検証済みの条件 4 許可契約。

    Raises:
        ContractError: 資産・digest・純粋 API 境界が不正な場合。
    """
    _strict_keys(
        value,
        {
            "schema_version",
            "contract_revision",
            "asset_kind",
            "canonicalization",
            "source_digest",
            "source",
            "api",
            "scopes",
            "triggers",
            "excluded_triggers",
            "propagation",
            "physical_key_adt",
            "durable_intent",
            "trigger_emission",
            "preaggregation_independent",
        },
        "cache-invalidation-contract.json",
    )
    if _integer(value["schema_version"], "cache.schema_version") != 1:
        raise ContractError("cache.schema_version は 1 でなければならない")
    if _integer(value["contract_revision"], "cache.contract_revision") < 1:
        raise ContractError("cache.contract_revision は 1 以上が必要")
    if (
        _string(value["asset_kind"], "cache.asset_kind")
        != "cache_invalidation_contract"
    ):
        raise ContractError("cache.asset_kind が固定値と不一致")
    if (
        _string(value["canonicalization"], "cache.canonicalization")
        != "json-sort-keys-utf8-v1"
    ):
        raise ContractError("cache.canonicalization が固定値と不一致")

    expected_digest = _string(value["source_digest"], "cache.source_digest")
    digest_payload = dict(value)
    digest_payload.pop("source_digest")
    serialized = json.dumps(
        digest_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    actual_digest = hashlib.sha256(serialized).hexdigest()
    if expected_digest != actual_digest:
        raise ContractError(
            "キャッシュ無効化契約の封印値が不一致: "
            f"expected={expected_digest}, actual={actual_digest}"
        )

    api = _object(value["api"], "cache.api")
    _strict_keys(
        api,
        {
            "kind",
            "provider_module",
            "factory_symbol",
            "public_symbols",
            "condition4_allowed_call_symbols",
            "owns_trigger_emission",
            "writes_persistent_intents",
            "tsk_424_capability_dependency",
        },
        "cache.api",
    )
    if _string(api["kind"], "cache.api.kind") != "pure_request_factory":
        raise ContractError("条件 4 の許可 API は純粋な要求生成器だけを許す")
    for field in (
        "owns_trigger_emission",
        "writes_persistent_intents",
        "tsk_424_capability_dependency",
    ):
        if api[field] is not False:
            raise ContractError(f"cache.api.{field} は false が必要")

    provider_module = _string(
        api["provider_module"], "cache.api.provider_module"
    )
    public_symbols = frozenset(
        _string_array(api["public_symbols"], "cache.api.public_symbols")
    )
    allowed_calls = frozenset(
        _string_array(
            api["condition4_allowed_call_symbols"],
            "cache.api.condition4_allowed_call_symbols",
        )
    )
    factory_symbol = _string(
        api["factory_symbol"], "cache.api.factory_symbol"
    )
    if not public_symbols or not allowed_calls:
        raise ContractError("条件 4 の公開シンボルと許可呼び出しは空にできない")
    if allowed_calls - public_symbols or factory_symbol not in allowed_calls:
        raise ContractError("条件 4 の許可呼び出しは公開 API の部分集合が必要")
    if any(
        not symbol.startswith(f"{provider_module}.")
        for symbol in public_symbols
    ):
        raise ContractError("条件 4 の公開シンボルが単一 provider 外を参照")
    return CacheInvalidationBypassContract(
        provider_module=provider_module,
        factory_symbol=factory_symbol,
        public_symbols=public_symbols,
        allowed_call_symbols=allowed_calls,
    )


def load_contract(repository_root: Path) -> Contract:
    """リポジトリから迂回検査契約を読む。

    Args:
        repository_root: リポジトリルート。

    Returns:
        読み合わせ済みの検査契約。

    Raises:
        ContractError: 資産の形式・閉集合・fixture 集合に不整合がある場合。
    """
    inventory_value, inventory_bytes = _read_json(repository_root / DEFAULT_INVENTORY)
    allowlist_value, _ = _read_json(repository_root / DEFAULT_ALLOWLIST)
    negative_value, _ = _read_json(repository_root / DEFAULT_NEGATIVE_FIXTURES)
    tenant_context_value, _ = _read_json(
        repository_root / DEFAULT_TENANT_CONTEXT_ALLOWLIST
    )
    cache_invalidation_value, _ = _read_json(
        repository_root / DEFAULT_CACHE_INVALIDATION_CONTRACT
    )
    apis = _load_inventory(inventory_value)
    allowed_symbols, rules = _load_allowlist(
        allowlist_value, inventory_bytes, apis
    )
    negative_fixtures = _load_negative_fixtures(negative_value)
    tenant_context = _load_tenant_context_allowlist(tenant_context_value)
    cache_invalidation = _load_cache_invalidation_bypass_contract(
        cache_invalidation_value
    )

    declared_positive = {item.fixture for item in allowed_symbols}
    positive_root = repository_root / "tests/fixtures/tenant_boundary/positive"
    actual_positive = {
        path.relative_to(repository_root).as_posix()
        for path in positive_root.rglob("*.py")
    }
    if actual_positive != declared_positive:
        raise ContractError(
            "正例 fixture が allowlist の exact-set と不一致: "
            f"missing={sorted(declared_positive - actual_positive)}, "
            f"extra={sorted(actual_positive - declared_positive)}"
        )

    negative_root = repository_root / "tests/fixtures/tenant_boundary/negative"
    actual_negative = {
        path.relative_to(negative_root).as_posix()
        for path in negative_root.rglob("*.py")
    }
    declared_negative = {item.path for item in negative_fixtures}
    if actual_negative != declared_negative:
        raise ContractError(
            "負例 fixture が全数表の exact-set と不一致: "
            f"missing={sorted(declared_negative - actual_negative)}, "
            f"extra={sorted(actual_negative - declared_negative)}"
        )
    return Contract(
        apis=apis,
        allowed_symbols=allowed_symbols,
        rules=rules,
        negative_fixtures=negative_fixtures,
        tenant_context=tenant_context,
        cache_invalidation=cache_invalidation,
    )


def _normalize_identifier(value: str) -> str:
    """Python 識別子または完全修飾名を snake_case 相当へ正規化する。"""
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^A-Za-z0-9]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_").lower()


def _module_name(path: str) -> str:
    """source root 相対パスから Python モジュール名を導出する。"""
    relative = Path(path)
    if relative.suffix not in {".py", ".pyi"}:
        return ""
    parts = list(relative.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """関数定義を整形非依存の署名文字列へ変換する。"""
    clone = copy.copy(node)
    clone.decorator_list = []
    clone.body = [ast.Pass()]
    rendered = ast.unparse(clone).splitlines()[0]
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    return rendered.removeprefix(prefix).removesuffix(":")


class _AliasCollector(ast.NodeVisitor):
    """import と単純代入による別名を収集する。"""

    def __init__(self, member_owners: Set[str]) -> None:
        self.aliases: dict[str, str] = {}
        self.member_owners = member_owners

    def resolve(self, node: ast.AST) -> str | None:
        """式を既知の完全修飾名へ解決する。"""
        if isinstance(node, ast.Name):
            return self.aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            parent = self.resolve(node.value)
            if parent is None:
                return None
            qualified = f"{parent}.{node.attr}"
            return self.aliases.get(qualified, qualified)
        return None

    def _record_arguments(self, arguments: ast.arguments) -> None:
        """引数の型注釈から任意名の DB receiver を解決する。"""
        positional = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
        for argument in positional:
            if argument.annotation is None:
                continue
            resolved = self.resolve(argument.annotation)
            if resolved is not None and resolved in self.member_owners:
                self.aliases[argument.arg] = resolved
        for argument in (arguments.vararg, arguments.kwarg):
            if argument is None or argument.annotation is None:
                continue
            resolved = self.resolve(argument.annotation)
            if resolved is not None and resolved in self.member_owners:
                self.aliases[argument.arg] = resolved

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        """import 文のローカル名を記録する。"""
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".")[0]
            self.aliases[local_name] = alias.name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        """from import 文のローカル名を記録する。"""
        module = node.module or ""
        for alias in node.names:
            if alias.name == "*":
                continue
            local_name = alias.asname or alias.name
            self.aliases[local_name] = f"{module}.{alias.name}".strip(".")

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        """単純な名前別名代入を記録する。"""
        self.generic_visit(node.value)
        resolved = self.resolve(node.value)
        if resolved is None:
            return
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.aliases[target.id] = resolved
            elif isinstance(target, ast.Attribute):
                target_name = self.resolve(target)
                if target_name is not None:
                    self.aliases[target_name] = resolved

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        """注釈付きの単純な名前別名代入を記録する。"""
        if node.value is None and isinstance(node.target, ast.Name):
            resolved_annotation = self.resolve(node.annotation)
            if (
                resolved_annotation is not None
                and resolved_annotation in self.member_owners
            ):
                self.aliases[node.target.id] = resolved_annotation
            return
        if node.value is None:
            return
        self.generic_visit(node.value)
        resolved = self.resolve(node.value)
        if resolved is not None and isinstance(node.target, ast.Name):
            self.aliases[node.target.id] = resolved

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """同期関数の引数注釈と本体の別名を収集する。"""
        self._record_arguments(node.args)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        """非同期関数の引数注釈と本体の別名を収集する。"""
        self._record_arguments(node.args)
        self.generic_visit(node)


class _SourceScanner(ast.NodeVisitor):
    """1 モジュールの変更行を検査する。"""

    def __init__(
        self,
        *,
        path: str,
        module: str,
        tree: ast.Module,
        changed_lines: Set[int] | None,
        contract: Contract,
        reject_all_db_calls: bool,
    ) -> None:
        self.path = path
        self.module = module
        self.changed_lines = changed_lines
        self.contract = contract
        self.reject_all_db_calls = reject_all_db_calls
        self.class_stack: list[str] = []
        self.function_stack: list[tuple[str, str]] = []
        self.violations: list[Violation] = []
        self._violation_keys: set[tuple[int, int, str, str]] = set()
        member_owners = {
            api.symbol.rsplit(".", 1)[0]
            for api in contract.apis
            if api.kind == "member"
        }
        collector = _AliasCollector(member_owners)
        collector.visit(tree)
        self.aliases = collector
        self.api_by_symbol = {api.symbol: api for api in contract.apis}
        self.allowed_by_symbol = {
            item.symbol: item for item in contract.allowed_symbols
        }

    def _is_changed(self, node: ast.AST) -> bool:
        if self.changed_lines is None:
            return True
        start = getattr(node, "lineno", 0)
        end = getattr(node, "end_lineno", start)
        return any(line in self.changed_lines for line in range(start, end + 1))

    def _add(
        self,
        node: ast.AST,
        *,
        condition: int,
        code: str,
        symbol: str,
        message: str,
    ) -> None:
        line = getattr(node, "lineno", 0)
        key = (line, condition, code, symbol)
        if key in self._violation_keys:
            return
        self._violation_keys.add(key)
        self.violations.append(
            Violation(
                path=self.path,
                line=line,
                condition=condition,
                code=code,
                symbol=symbol,
                message=message,
            )
        )

    def _condition4_reference_allowed(self, text: str) -> bool:
        """条件 4 の公開型・enum 参照に限って許可する。"""
        boundary = self.contract.cache_invalidation
        if text == boundary.factory_symbol:
            return False
        return any(
            text == symbol or text.startswith(f"{symbol}.")
            for symbol in boundary.public_symbols
        )

    def _check_identifier(
        self,
        text: str,
        node: ast.AST,
        *,
        allow_condition4: bool = False,
    ) -> None:
        if not self._is_changed(node):
            return
        candidates = {_normalize_identifier(text)}
        candidates.update(_normalize_identifier(part) for part in text.split("."))
        for rule in self.contract.rules:
            if rule.condition == 4 and (
                allow_condition4
                or self.module
                == self.contract.cache_invalidation.provider_module
            ):
                continue
            for candidate in candidates:
                if any(pattern.search(candidate) for pattern in rule.patterns):
                    self._add(
                        node,
                        condition=rule.condition,
                        code=rule.error,
                        symbol=text,
                        message=f"条件 {rule.condition} の禁止シンボルを検出",
                    )
                    break

    def _raw_expression(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = self._raw_expression(node.value)
            if parent is None:
                return None
            return f"{parent}.{node.attr}"
        return None

    def _matching_api(self, node: ast.AST) -> ApiSpec | None:
        resolved = self.aliases.resolve(node)
        if resolved in self.api_by_symbol:
            return self.api_by_symbol[resolved]
        raw = self._raw_expression(node)
        if raw in self.api_by_symbol:
            return self.api_by_symbol[raw]
        candidate = resolved or raw
        if candidate is None or "." not in candidate:
            return None
        method = candidate.rsplit(".", 1)[1]
        raw_receiver = ""
        if raw is not None and "." in raw:
            raw_receiver = raw.rsplit(".", 2)[-2]
        resolved_receiver = candidate.rsplit(".", 2)[-2]
        for api in self.contract.apis:
            if api.kind != "member" or api.symbol.rsplit(".", 1)[1] != method:
                continue
            if raw_receiver in api.receivers or resolved_receiver in api.receivers:
                return api
        return None

    def _current_allowed_symbol(self) -> AllowedSymbol | None:
        if not self.function_stack:
            return None
        symbol, signature = self.function_stack[-1]
        allowed = self.allowed_by_symbol.get(symbol)
        if allowed is None or allowed.signature != signature:
            return None
        return allowed

    def _check_db_call(self, node: ast.Call) -> None:
        if not self._is_changed(node):
            return
        api = self._matching_api(node.func)
        if api is None:
            return
        allowed = self._current_allowed_symbol()
        if (
            not self.reject_all_db_calls
            and allowed is not None
            and api.id in allowed.allowed_api_ids
        ):
            return
        code = "TB900" if self.reject_all_db_calls else "TB005"
        message = (
            "全拒否変異が DB 到達呼び出しを拒否"
            if self.reject_all_db_calls
            else "DB 到達 API は許可された基底シンボルの内側だけで使用できる"
        )
        self._add(
            node,
            condition=5,
            code=code,
            symbol=api.symbol,
            message=message,
        )

    def _check_set_config_call(self, node: ast.Call) -> None:
        resolved = self.aliases.resolve(node.func) or self._raw_expression(node.func) or ""
        if resolved.rsplit(".", 1)[-1] != "set_config" or not self._is_changed(node):
            return
        if len(node.args) >= 3 and isinstance(node.args[2], ast.Constant):
            value = node.args[2].value
            if value is False or (isinstance(value, str) and value.lower() == "false"):
                self._add(
                    node,
                    condition=5,
                    code="TB005",
                    symbol="set_config(..., false)",
                    message="transaction-local でない set_config は禁止",
                )

    def _check_tenant_context_call(self, node: ast.Call) -> None:
        """TenantContext の構築元モジュールを閉じた集合へ照合する。"""
        if not self._is_changed(node):
            return
        resolved = self.aliases.resolve(node.func) or self._raw_expression(node.func)
        if resolved != self.contract.tenant_context.constructor_symbol:
            return
        allowed_modules = (
            self.contract.tenant_context.allowed_test_modules
            | self.contract.tenant_context.allowed_product_modules
        )
        if self.module in allowed_modules:
            return
        self._add(
            node,
            condition=5,
            code="TB007",
            symbol=resolved,
            message="TenantContext は生成箇所 allowlist 内のモジュールだけで構築できる",
        )

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        """import のモジュール名と別名を禁止語彙へ照合する。"""
        for alias in node.names:
            self._check_identifier(alias.name, node)
            if alias.asname is not None:
                self._check_identifier(alias.asname, node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        """from import のモジュール名・シンボル名・別名を照合する。"""
        if node.module is not None:
            provider_module = self.contract.cache_invalidation.provider_module
            self._check_identifier(
                node.module,
                node,
                allow_condition4=node.module == provider_module,
            )
        for alias in node.names:
            imported_symbol = (
                f"{node.module}.{alias.name}"
                if node.module is not None
                else alias.name
            )
            import_is_allowed = (
                imported_symbol
                in self.contract.cache_invalidation.public_symbols
            )
            if (
                node.module
                == self.contract.cache_invalidation.provider_module
                and not import_is_allowed
                and self._is_changed(node)
            ):
                self._add(
                    node,
                    condition=4,
                    code="TB004",
                    symbol=imported_symbol,
                    message="条件 4 の provider から非公開シンボルを import できない",
                )
            self._check_identifier(
                imported_symbol if import_is_allowed else alias.name,
                node,
                allow_condition4=import_is_allowed,
            )
            if alias.asname is not None:
                self._check_identifier(alias.asname, node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        """クラス内のメソッド完全修飾名を構築する。"""
        self._check_identifier(node.name, node)
        allowed_modules = (
            self.contract.tenant_context.allowed_test_modules
            | self.contract.tenant_context.allowed_product_modules
        )
        for base in node.bases:
            resolved = self.aliases.resolve(base) or self._raw_expression(base)
            if (
                self._is_changed(base)
                and resolved == self.contract.tenant_context.constructor_symbol
                and self.module not in allowed_modules
            ):
                self._add(
                    base,
                    condition=5,
                    code="TB007",
                    symbol=resolved,
                    message=(
                        "TenantContext は生成箇所 allowlist 外で継承できない"
                    ),
                )
        self.class_stack.append(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for statement in node.body:
            self.visit(statement)
        self.class_stack.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._check_identifier(node.name, node)
        prefix = ".".join([self.module, *self.class_stack]).strip(".")
        symbol = f"{prefix}.{node.name}" if prefix else node.name
        signature = _function_signature(node)
        expected = self.allowed_by_symbol.get(symbol)
        if expected is not None and signature != expected.signature and self._is_changed(node):
            self._add(
                node,
                condition=5,
                code="TB005",
                symbol=symbol,
                message=(
                    "基底シンボルの署名が契約と不一致: "
                    f"expected={expected.signature}, actual={signature}"
                ),
            )
        for decorator in node.decorator_list:
            resolved = self.aliases.resolve(decorator)
            if resolved is not None:
                self._check_identifier(resolved, decorator)
            self.visit(decorator)
        self.function_stack.append((symbol, signature))
        for statement in node.body:
            self.visit(statement)
        self.function_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """同期関数のシンボル・署名・本体を検査する。"""
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        """非同期関数のシンボル・署名・本体を検査する。"""
        self._visit_function(node)

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        """名前参照を禁止語彙へ照合する。"""
        resolved = self.aliases.resolve(node) or node.id
        self._check_identifier(
            resolved,
            node,
            allow_condition4=self._condition4_reference_allowed(resolved),
        )

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        """属性参照を禁止語彙へ照合する。"""
        resolved = self.aliases.resolve(node) or self._raw_expression(node) or node.attr
        self._check_identifier(
            resolved,
            node,
            allow_condition4=self._condition4_reference_allowed(resolved),
        )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        """呼び出しを DB API・禁止シンボル・生成箇所へ照合する。"""
        resolved = self.aliases.resolve(node.func) or self._raw_expression(node.func)
        condition4_call_allowed = (
            resolved
            in self.contract.cache_invalidation.allowed_call_symbols
        )
        if resolved is not None:
            self._check_identifier(
                resolved,
                node,
                allow_condition4=condition4_call_allowed,
            )
        self._check_db_call(node)
        self._check_set_config_call(node)
        self._check_tenant_context_call(node)
        if not condition4_call_allowed:
            self.visit(node.func)
        for argument in (*node.args, *(item.value for item in node.keywords)):
            self.visit(argument)

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        """SQL 文字列中の非局所 GUC 設定を検査する。"""
        if not isinstance(node.value, str) or not self._is_changed(node):
            return
        if SET_TENANT_RE.search(node.value):
            self._add(
                node,
                condition=5,
                code="TB005",
                symbol="SET app.tenant_id",
                message="SET app.tenant_id は禁止。transaction-local な束縛を使う",
            )
        if NONLOCAL_SET_CONFIG_RE.search(node.value):
            self._add(
                node,
                condition=5,
                code="TB005",
                symbol="set_config(..., false)",
                message="transaction-local でない set_config は禁止",
            )


def scan_source(
    source: str,
    *,
    path: str,
    contract: Contract,
    changed_lines: Set[int] | None = None,
    reject_all_db_calls: bool = False,
) -> list[Violation]:
    """1 つの Python ソースを検査する。

    Args:
        source: Python ソース。
        path: source root 相対パス。
        contract: 読み合わせ済み検査契約。
        changed_lines: 検査する新側行番号。``None`` は全行。
        reject_all_db_calls: 正例の実効性を測る全拒否変異を有効にするか。

    Returns:
        検出した違反。構文エラーも fail-closed の違反として返す。
    """
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as error:
        return [
            Violation(
                path=path,
                line=error.lineno or 0,
                condition=0,
                code="TB000",
                symbol="<syntax>",
                message=f"AST 解析に失敗: {error.msg}",
            )
        ]
    scanner = _SourceScanner(
        path=path,
        module=_module_name(path),
        tree=tree,
        changed_lines=changed_lines,
        contract=contract,
        reject_all_db_calls=reject_all_db_calls,
    )
    scanner.visit(tree)
    return sorted(scanner.violations)


def scan_directory(
    source_root: Path,
    *,
    contract: Contract,
    reject_all_db_calls: bool = False,
) -> list[Violation]:
    """fixture などの source root 配下を全行検査する。

    Args:
        source_root: Python パッケージの起点。
        contract: 読み合わせ済み検査契約。
        reject_all_db_calls: 全拒否変異を有効にするか。

    Returns:
        全 Python ファイルから検出した違反。
    """
    violations: list[Violation] = []
    for path in sorted(source_root.rglob("*.py")):
        relative = path.relative_to(source_root).as_posix()
        violations.extend(
            scan_source(
                path.read_text(encoding="utf-8"),
                path=relative,
                contract=contract,
                reject_all_db_calls=reject_all_db_calls,
            )
        )
    return sorted(violations)


def changed_lines_from_diff(diff: str) -> dict[str, frozenset[int]]:
    """``git diff -U0`` から新側の変更行を導出する。

    Args:
        diff: unified context 0 の差分。

    Returns:
        ``backend/src`` 相対パスから新側行番号集合への対応。
    """
    result: dict[str, set[int]] = {}
    current_path: str | None = None
    hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")
    for line in diff.splitlines():
        if line.startswith("+++ "):
            raw_path = line[4:]
            if raw_path == "/dev/null":
                current_path = None
                continue
            path = raw_path.removeprefix("b/")
            prefix = "backend/src/"
            current_path = path.removeprefix(prefix) if path.startswith(prefix) else None
            if current_path is not None:
                result.setdefault(current_path, set())
            continue
        if current_path is None:
            continue
        match = hunk_re.match(line)
        if match is None:
            continue
        start = int(match.group("start"))
        count = int(match.group("count") or "1")
        result[current_path].update(range(start, start + count))
    return {path: frozenset(lines) for path, lines in result.items()}


class _DefinitionCollector(ast.NodeVisitor):
    """許可対象シンボルの定義と署名をスナップショットから採取する。"""

    def __init__(self, module: str, allowed: Set[str]) -> None:
        self.module = module
        self.allowed = allowed
        self.class_stack: list[str] = []
        self.definitions: dict[str, str] = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        """クラス階層を記録して本体を巡回する。"""
        self.class_stack.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self.class_stack.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        prefix = ".".join([self.module, *self.class_stack]).strip(".")
        symbol = f"{prefix}.{node.name}" if prefix else node.name
        if symbol in self.allowed:
            self.definitions[symbol] = _function_signature(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """許可対象の同期関数署名を採取する。"""
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        """許可対象の非同期関数署名を採取する。"""
        self._visit_function(node)


def _definitions(
    sources: Mapping[str, str], contract: Contract
) -> tuple[dict[str, str], list[Violation]]:
    allowed = {item.symbol for item in contract.allowed_symbols}
    definitions: dict[str, str] = {}
    violations: list[Violation] = []
    for path, source in sources.items():
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as error:
            violations.append(
                Violation(
                    path=path,
                    line=error.lineno or 0,
                    condition=0,
                    code="TB000",
                    symbol="<syntax>",
                    message=f"AST 解析に失敗: {error.msg}",
                )
            )
            continue
        collector = _DefinitionCollector(_module_name(path), allowed)
        collector.visit(tree)
        definitions.update(collector.definitions)
    return definitions, violations


def continuity_violations(
    baseline_sources: Mapping[str, str],
    head_sources: Mapping[str, str],
    *,
    contract: Contract,
) -> list[Violation]:
    """基底シンボルの追加を許しつつ、既存定義の巻き戻しを拒否する。

    基準版と HEAD の双方が空なら正常である。基準版に一度現れた許可シンボルは
    HEAD から消せず、HEAD に現れた定義は常に契約署名と一致しなければならない。

    Args:
        baseline_sources: merge-base の ``backend/src`` スナップショット。
        head_sources: HEAD の ``backend/src`` スナップショット。
        contract: 読み合わせ済み検査契約。

    Returns:
        構文エラー、署名不一致、または巻き戻しの違反。
    """
    baseline, violations = _definitions(baseline_sources, contract)
    head, head_violations = _definitions(head_sources, contract)
    violations.extend(head_violations)
    expected = {item.symbol: item.signature for item in contract.allowed_symbols}
    for symbol, signature in head.items():
        if signature != expected[symbol]:
            violations.append(
                Violation(
                    path="backend/src",
                    line=0,
                    condition=5,
                    code="TB006",
                    symbol=symbol,
                    message=(
                        "HEAD の基底シンボル署名が契約と不一致: "
                        f"expected={expected[symbol]}, actual={signature}"
                    ),
                )
            )
    for symbol in sorted(set(baseline) - set(head)):
        violations.append(
            Violation(
                path="backend/src",
                line=0,
                condition=5,
                code="TB006",
                symbol=symbol,
                message="基準版に存在した基底シンボルが HEAD から消えた",
            )
        )
    return sorted(violations)


def _run_git(repository_root: Path, arguments: Sequence[str]) -> str:
    """Git コマンドを実行して標準出力を返す。"""
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ContractError(
            f"git {' '.join(arguments)} に失敗: {result.stderr.strip()}"
        )
    return result.stdout


def _git_snapshot(repository_root: Path, revision: str) -> dict[str, str]:
    """指定 revision の backend/src Python ソースを読む。"""
    names = _run_git(
        repository_root,
        ["ls-tree", "-r", "--name-only", revision, "--", "backend/src"],
    )
    sources: dict[str, str] = {}
    for full_path in names.splitlines():
        path = Path(full_path)
        if path.suffix not in {".py", ".pyi"}:
            continue
        relative = path.relative_to("backend/src").as_posix()
        sources[relative] = _run_git(
            repository_root, ["show", f"{revision}:{full_path}"]
        )
    return sources


def _changed_source_violations(
    repository_root: Path,
    changed_lines: Mapping[str, frozenset[int]],
    contract: Contract,
) -> list[Violation]:
    """HEAD の変更行に対して検査を実行する。"""
    violations: list[Violation] = []
    for relative, lines in sorted(changed_lines.items()):
        if not lines:
            continue
        path = repository_root / "backend/src" / relative
        if path.suffix not in {".py", ".pyi"}:
            violations.append(
                Violation(
                    path=f"backend/src/{relative}",
                    line=min(lines),
                    condition=0,
                    code="TB000",
                    symbol="<unsupported>",
                    message="backend/src の変更ファイルを AST 解析できない",
                )
            )
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as error:
            raise ContractError(f"HEAD の変更ファイルを読めない: {path}: {error}") from error
        violations.extend(
            scan_source(
                source,
                path=relative,
                changed_lines=lines,
                contract=contract,
            )
        )
    return sorted(violations)


def check_repository(repository_root: Path, base_ref: str = "origin/develop") -> list[Violation]:
    """リポジトリの PR 差分と基底シンボル継続性を検査する。

    Args:
        repository_root: リポジトリルート。
        base_ref: PR の比較元。通常は ``origin/develop``。

    Returns:
        検出した違反。
    """
    contract = load_contract(repository_root)
    diff = _run_git(
        repository_root,
        ["diff", "-U0", f"{base_ref}...HEAD", "--", "backend/src"],
    )
    changed_lines = changed_lines_from_diff(diff)
    violations = _changed_source_violations(repository_root, changed_lines, contract)
    merge_base = _run_git(repository_root, ["merge-base", base_ref, "HEAD"]).strip()
    violations.extend(
        continuity_violations(
            _git_snapshot(repository_root, merge_base),
            _git_snapshot(repository_root, "HEAD"),
            contract=contract,
        )
    )
    return sorted(set(violations))


def _format_violations(violations: Iterable[Violation]) -> str:
    """違反を 1 行 1 件の安定した形式へ整形する。"""
    return "\n".join(
        f"{item.path}:{item.line}: {item.code} condition={item.condition} "
        f"symbol={item.symbol}: {item.message}"
        for item in violations
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI の入口。

    Args:
        argv: コマンドライン引数。``None`` は ``sys.argv`` を使う。

    Returns:
        合格は 0、違反は 1、契約または Git の異常は 2。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base-ref", default="origin/develop")
    args = parser.parse_args(argv)
    try:
        violations = check_repository(args.root.resolve(), args.base_ref)
    except ContractError as error:
        print(f"tenant-boundary contract error: {error}", file=sys.stderr)
        return 2
    if violations:
        print(_format_violations(violations), file=sys.stderr)
        return 1
    print("tenant-boundary bypass check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
