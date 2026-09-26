"""テナント境界の迂回を AST と import 境界で検査する。

条件 5(TenantContext 生成経路)の保証単位は「構築に使われる名前が、
変更ファイル内で読み取れること」である。型の解決可否は保証の条件にしない。
赤にするもの: (i) 完全修飾名が構築シンボルに解決される / (ii) 資産が列挙する禁止構築シンボル /
(iii) 名前が読み取れない callable(属性式でない呼び出し)/ (iv) 末尾名が構築シンボル末尾名に一致
(属性でも裸の名前でも)/ (v) 再輸出写像の可能な起源集合に構築シンボルが含まれる、
または内部再輸出の解決が unresolved(深さ上限 / star / 条件分岐 / 循環 / 自己参照 /
欠落した pitchlog.* モジュール / 未対応の静的代入)。

守らないもの(正式に縮小する — 人間承認の対象):
1. 再輸出元だけを変更し、利用側を変更しない漂流。CI の母集団が変更ファイルに限られるため
2. registry[k].make_context(t) のように、構築シンボル以外の属性名で、
   再輸出写像でも解決できない callable を経由した構築
3. (iii) と (iv)(v) の非対称は原理ではなく、既存負例が守る範囲を落とさないための線である
4. 引数・局所変数・クロージャ変数として外から渡された callable を経由した構築。
   依存性注入は型注釈でも由来を確定できず、赤にすると通常の設計パターンが
   機械的に通らなくなるため。
"""

from __future__ import annotations

import argparse
import ast
import builtins
import copy
import difflib
import dis
import hashlib
import json
import re
import shlex
import subprocess
import symtable
import sys
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# このファイルは importlib でパス指定ロードされるため、同階層 import を解決する。
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import frozen_history  # noqa: E402

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
# 比較元は基準の値ではなく検査の手続きに属するため、検査対象の資産には置かない。
# 本検査器は base-allowlist.json の外部凍結対象なので、既定値を動かす変更にも
# 識別値の更新と履歴が必要になり、資産から記録なしに自己申告する経路を作らない。
DEFAULT_BASE_REF = "origin/develop"
FROZEN_BASELINE_ASSETS = (
    Path("contracts/tenant_boundary/base-allowlist.json"),
    Path("contracts/tenant_boundary/cache-invalidation-contract.json"),
    Path("contracts/tenant_boundary/db-api-inventory.json"),
    Path("contracts/tenant_boundary/negative-fixtures.json"),
    Path("contracts/tenant_boundary/repository-contract.json"),
    Path("contracts/tenant_boundary/runtime-authz-contract.json"),
    Path("contracts/tenant_boundary/tenant-context-allowlist.json"),
)
# 資産の場所だけは、その宣言を読む前に必要になる bootstrap なので残す。
# 基準値・合否写像は各資産から読み、この一覧を第二の決定元にはしない。
CONDITION_IDS = frozenset({1, 2, 3, 4, 5})
PENDING_APPROVAL = "未承認(PR #72 のレビュー待ち)"
PENDING_SOURCE_COMMIT = "PENDING_ACCEPTANCE"
NO_BASELINE = "NO_BASELINE"
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
class _ApiMatch:
    """DB API 照合結果と、完全修飾名で確定したかを表す。"""

    api: ApiSpec
    exact: bool


@dataclass(frozen=True)
class ReceiverFactory:
    """DB receiver を返す factory または member API を表す。"""

    symbol: str
    returns: str


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
class Condition2Adjudication:
    """条件 2 の候補から非同期セマンティクスと裁定したシンボルを表す。"""

    symbol: str
    reason: str


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
    forbidden_construction_symbols: frozenset[str]
    integrity_secret_symbol: str
    integrity_secret_allowed_symbols: frozenset[str]
    integrity_proof_factory_symbol: str
    integrity_proof_factory_allowed_symbols: frozenset[str]
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
    receiver_factories: tuple[ReceiverFactory, ...]
    symbol_aliases: Mapping[str, str]
    conservative_member_names: frozenset[str]
    allowed_symbols: tuple[AllowedSymbol, ...]
    rules: tuple[ConditionRule, ...]
    condition2_adjudications: tuple[Condition2Adjudication, ...]
    negative_fixtures: tuple[NegativeFixture, ...]
    tenant_context: TenantContextConstructionContract
    cache_invalidation: CacheInvalidationBypassContract
    diff_command: tuple[str, ...]


@dataclass(frozen=True, order=True)
class Violation:
    """検出した迂回または検査契約違反を表す。"""

    path: str
    line: int
    condition: int
    code: str
    symbol: str
    message: str
    end_line: int = 0
    scope: str = "<module>"


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


def _identifier_map(
    value: object,
    location: str,
) -> dict[str, tuple[str, ...]]:
    """資産パスから資産内で一意な識別値列へのmapを取得する。"""
    raw_map = _object(value, location)
    if not raw_map:
        raise ContractError(f"{location}: 空にできない")
    identifiers: dict[str, tuple[str, ...]] = {}
    for asset_path, raw_identifiers in raw_map.items():
        if not asset_path:
            raise ContractError(f"{location}: 資産パスは空にできない")
        parsed = _string_array(raw_identifiers, f"{location}.{asset_path}")
        if not parsed:
            raise ContractError(f"{location}.{asset_path}: 空にできない")
        identifiers[asset_path] = parsed
    return identifiers


def _validate_baseline_control(
    asset: Mapping[str, object],
    location: str,
) -> tuple[Mapping[str, object], ...]:
    """7.7-2 の基準識別・更新履歴・連鎖を検証する。

    Args:
        asset: 基準と履歴を持つ契約資産。
        location: エラー表示用の資産パス。

    Returns:
        append-only 比較に使う検証済み履歴。

    Raises:
        ContractError: 宣言、必須項目、承認状態、または連鎖が不正な場合。
    """
    control = _object(asset.get("baseline_control"), f"{location}.baseline_control")
    _strict_keys(
        control,
        {"identity", "movement_policy", "history", "history_authority"},
        f"{location}.baseline_control",
    )
    if type(control["history_authority"]) is not bool:
        raise ContractError(f"{location}: history_authority は bool が必要")
    identity = _object(control["identity"], f"{location}.baseline_control.identity")
    _strict_keys(
        identity,
        {
            "scheme",
            "field",
            "current_identifiers",
            "no_baseline_marker",
            "frozen_projection",
        },
        f"{location}.baseline_control.identity",
    )
    if _string(identity["scheme"], f"{location}.identity.scheme") != (
        "integer_revision_field"
    ):
        raise ContractError(f"{location}: 基準識別方式が未知")
    field = _string(identity["field"], f"{location}.identity.field")
    revision = _integer(asset.get(field), f"{location}.{field}")
    current_identifiers = _string_array(
        identity["current_identifiers"],
        f"{location}.identity.current_identifiers",
    )
    if current_identifiers != (f"{field}:{revision}",):
        raise ContractError(f"{location}: 現在の基準識別値が revision field と不一致")
    no_baseline_marker = _string(
        identity["no_baseline_marker"],
        f"{location}.identity.no_baseline_marker",
    )
    if no_baseline_marker != NO_BASELINE:
        raise ContractError(f"{location}: 基準未設置 marker が固定値と不一致")
    projection = _object(
        identity["frozen_projection"],
        f"{location}.identity.frozen_projection",
    )
    _strict_keys(
        projection,
        {"algorithm", "included", "excluded", "external_files"},
        f"{location}.identity.frozen_projection",
    )
    if _string(projection["algorithm"], f"{location}.projection.algorithm") != (
        "sha256-canonical-json-and-external-files-v1"
    ):
        raise ContractError(f"{location}: 凍結射影の algorithm が未知")
    if _string(projection["included"], f"{location}.projection.included") != (
        "all_top_level_fields"
    ):
        raise ContractError(f"{location}: 凍結対象の included が固定値と不一致")
    excluded = frozenset(
        _string_array(projection["excluded"], f"{location}.projection.excluded")
    )
    if excluded != {"baseline_control", "source_digest"}:
        raise ContractError(f"{location}: 凍結対象から除外する metadata が不一致")
    _string_array(projection["external_files"], f"{location}.projection.external_files")

    policy = _object(
        control["movement_policy"],
        f"{location}.baseline_control.movement_policy",
    )
    _strict_keys(
        policy,
        {
            "acceptance_unit",
            "previous_state",
            "new_state",
            "intermediate_commits_are_records",
            "movement_triggers",
            "affected_baselines",
            "history_append_only",
        },
        f"{location}.baseline_control.movement_policy",
    )
    if _string(policy["acceptance_unit"], f"{location}.policy.acceptance_unit") != (
        "single_review_acceptance"
    ):
        raise ContractError(f"{location}: 受理単位が固定値と不一致")
    if _string(policy["previous_state"], f"{location}.policy.previous_state") != (
        "state_immediately_before_review_acceptance"
    ):
        raise ContractError(f"{location}: 直前状態の算出方法が不一致")
    if _string(policy["new_state"], f"{location}.policy.new_state") != (
        "state_immediately_after_review_acceptance"
    ):
        raise ContractError(f"{location}: 直後状態の算出方法が不一致")
    if policy["intermediate_commits_are_records"] is not False:
        raise ContractError(f"{location}: 途中コミットを履歴行に数えてはならない")
    try:
        frozen_history.validate_movement_triggers(
            policy,
            f"{location}.policy",
        )
    except frozen_history.ContractError as error:
        raise ContractError(str(error)) from error
    if _string(policy["affected_baselines"], f"{location}.policy.affected_baselines") != (
        "all_baselines_matching_any_declared_trigger"
    ):
        raise ContractError(f"{location}: 行為の対象となる基準規則が不一致")
    if policy["history_append_only"] is not True:
        raise ContractError(f"{location}: 履歴は追記専用でなければならない")

    history: list[Mapping[str, object]] = []
    previous_new: tuple[str, ...] | None = None
    source_commits: set[str] = set()
    for index, raw in enumerate(_array(control["history"], f"{location}.history")):
        entry_location = f"{location}.history[{index}]"
        entry = _object(raw, entry_location)
        if "record_schema_version" in entry:
            if entry.get("record_schema_version") != 2:
                raise ContractError(f"{entry_location}: v2 以外の明示版は不正")
            _strict_keys(
                entry,
                {
                    "record_schema_version",
                    "acceptance_id",
                    "new_baseline_identifiers",
                    "previous_baseline_identifiers",
                    "change",
                    "movement_fact",
                    "reason",
                    "approved_by",
                    "approved_on",
                },
                entry_location,
            )
            _identifier_map(
                entry["new_baseline_identifiers"],
                f"{entry_location}.new_baseline_identifiers",
            )
            _identifier_map(
                entry["previous_baseline_identifiers"],
                f"{entry_location}.previous_baseline_identifiers",
            )
            _string(entry["acceptance_id"], f"{entry_location}.acceptance_id")
            _string(entry["movement_fact"], f"{entry_location}.movement_fact")
            _string(entry["reason"], f"{entry_location}.reason")
            _string(entry["approved_by"], f"{entry_location}.approved_by")
            _string(entry["approved_on"], f"{entry_location}.approved_on")
            history.append(entry)
            continue
        _strict_keys(
            entry,
            {
                "source_commit",
                "new_baseline_identifiers",
                "previous_baseline_identifiers",
                "change",
                "movement_fact",
                "reason",
                "approved_by",
                "approved_on",
            },
            entry_location,
        )
        source_commit = _string(entry["source_commit"], f"{entry_location}.source_commit")
        if source_commit != PENDING_SOURCE_COMMIT and re.fullmatch(
            r"[0-9a-f]{7,40}", source_commit
        ) is None:
            raise ContractError(
                f"{entry_location}: source_commit は受理待ち marker または Git hash が必要"
            )
        if source_commit in source_commits:
            raise ContractError(f"{location}: source_commit を重複できない")
        source_commits.add(source_commit)
        new_identifiers = _string_array(
            entry["new_baseline_identifiers"],
            f"{entry_location}.new_baseline_identifiers",
        )
        previous_identifiers = _string_array(
            entry["previous_baseline_identifiers"],
            f"{entry_location}.previous_baseline_identifiers",
        )
        if not new_identifiers or not previous_identifiers:
            raise ContractError(f"{entry_location}: 新旧の基準識別値は空にできない")
        if NO_BASELINE in new_identifiers and new_identifiers != (NO_BASELINE,):
            raise ContractError(f"{entry_location}: 新基準の未設置 marker は単独値が必要")
        if NO_BASELINE in previous_identifiers and previous_identifiers != (NO_BASELINE,):
            raise ContractError(f"{entry_location}: 直前基準の未設置 marker は単独値が必要")
        if previous_new is not None and previous_identifiers != previous_new:
            raise ContractError(f"{entry_location}: 直前の基準識別値の連鎖が切れている")
        change = _object(entry["change"], f"{entry_location}.change")
        _strict_keys(
            change,
            {"subject", "before", "after"},
            f"{entry_location}.change",
        )
        _string(change["subject"], f"{entry_location}.change.subject")
        for field_name in ("before", "after"):
            snapshot = _object(
                change[field_name],
                f"{entry_location}.change.{field_name}",
            )
            _strict_keys(
                snapshot,
                {"state", "frozen_projection_sha256"},
                f"{entry_location}.change.{field_name}",
            )
            state = _string(
                snapshot["state"],
                f"{entry_location}.change.{field_name}.state",
            )
            digest = _string(
                snapshot["frozen_projection_sha256"],
                f"{entry_location}.change.{field_name}.frozen_projection_sha256",
            )
            if state not in {"NO_BASELINE", "PRESENT"}:
                raise ContractError(f"{entry_location}: 基準状態が未知")
            if (state == "NO_BASELINE") != (digest == NO_BASELINE):
                raise ContractError(f"{entry_location}: 基準状態と射影識別値が不一致")
            if state == "PRESENT" and re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ContractError(f"{entry_location}: 射影 SHA-256 が不正")
        _string(entry["movement_fact"], f"{entry_location}.movement_fact")
        _string(entry["reason"], f"{entry_location}.reason")
        approved_by = _string(entry["approved_by"], f"{entry_location}.approved_by")
        approved_on = _string(entry["approved_on"], f"{entry_location}.approved_on")
        pending_values = {approved_by == PENDING_APPROVAL, approved_on == PENDING_APPROVAL}
        if len(pending_values) != 1:
            raise ContractError(f"{entry_location}: 承認者と承認日は同時に確定する")
        if approved_on != PENDING_APPROVAL and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", approved_on
        ) is None:
            raise ContractError(f"{entry_location}: 承認日は YYYY-MM-DD が必要")
        if source_commit == PENDING_SOURCE_COMMIT and approved_by != PENDING_APPROVAL:
            raise ContractError(f"{entry_location}: 受理済み記録に受理待ち marker を残せない")
        history.append(entry)
        previous_new = new_identifiers
    if not history and control["history_authority"] is not False:
        raise ContractError(f"{location}: 更新履歴は空にできない")
    return tuple(history)


def _load_inventory(
    value: dict[str, Any],
) -> tuple[
    tuple[ApiSpec, ...],
    tuple[ReceiverFactory, ...],
    Mapping[str, str],
    frozenset[str],
]:
    """DB API inventory を検証して読む。"""
    _strict_keys(
        value,
        {
            "schema_version",
            "inventory_revision",
            "closed_world",
            "apis",
            "receiver_factories",
            "symbol_aliases",
            "conservative_member_names",
            "baseline_control",
        },
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

    member_owners = {
        api.symbol.rsplit(".", 1)[0] for api in apis if api.kind == "member"
    }
    receiver_factories: list[ReceiverFactory] = []
    for index, raw in enumerate(
        _array(value["receiver_factories"], "inventory.receiver_factories")
    ):
        item = _object(raw, f"inventory.receiver_factories[{index}]")
        _strict_keys(
            item,
            {"symbol", "returns"},
            f"inventory.receiver_factories[{index}]",
        )
        returns = _string(
            item["returns"], f"inventory.receiver_factories[{index}].returns"
        )
        if returns not in member_owners:
            raise ContractError(
                f"inventory.receiver_factories[{index}].returns が receiver 型でない"
            )
        receiver_factories.append(
            ReceiverFactory(
                symbol=_string(
                    item["symbol"],
                    f"inventory.receiver_factories[{index}].symbol",
                ),
                returns=returns,
            )
        )
    factory_symbols = [item.symbol for item in receiver_factories]
    if not receiver_factories or len(factory_symbols) != len(set(factory_symbols)):
        raise ContractError("receiver_factories は空にできず、symbol は一意でなければならない")

    symbol_aliases: dict[str, str] = {}
    for index, raw in enumerate(
        _array(value["symbol_aliases"], "inventory.symbol_aliases")
    ):
        item = _object(raw, f"inventory.symbol_aliases[{index}]")
        _strict_keys(
            item,
            {"symbol", "target"},
            f"inventory.symbol_aliases[{index}]",
        )
        symbol = _string(
            item["symbol"], f"inventory.symbol_aliases[{index}].symbol"
        )
        target = _string(
            item["target"], f"inventory.symbol_aliases[{index}].target"
        )
        if symbol in symbol_aliases:
            raise ContractError("inventory.symbol_aliases.symbol は一意でなければならない")
        if target not in member_owners:
            raise ContractError(
                f"inventory.symbol_aliases[{index}].target が receiver 型でない"
            )
        symbol_aliases[symbol] = target
    if not symbol_aliases:
        raise ContractError("inventory.symbol_aliases は空にできない")
    conservative_member_names = frozenset(
        _string_array(
            value["conservative_member_names"],
            "inventory.conservative_member_names",
        )
    )
    inventory_member_names = {
        api.symbol.rsplit(".", 1)[1] for api in apis if api.kind == "member"
    }
    if not conservative_member_names or not (
        conservative_member_names <= inventory_member_names
    ):
        raise ContractError(
            "conservative_member_names は inventory の member 名の非空部分集合が必要"
        )
    return (
        tuple(apis),
        tuple(receiver_factories),
        symbol_aliases,
        conservative_member_names,
    )


def _load_allowlist(
    value: dict[str, Any], inventory_bytes: bytes, apis: tuple[ApiSpec, ...]
) -> tuple[
    tuple[AllowedSymbol, ...],
    tuple[ConditionRule, ...],
    tuple[Condition2Adjudication, ...],
    tuple[str, ...],
]:
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
            "condition_2_adjudications",
            "baseline_control",
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
    if (
        len(command) < 6
        or command[:3] != ("git", "diff", "-U0")
        or command[3] != "{base_ref}...HEAD"
        or command[4] != "--"
        or not all(part for part in command[5:])
    ):
        raise ContractError(
            "diff.command は外部から与える base_ref の三点差分 template が必要"
        )

    ci = _object(value["ci"], "allowlist.ci")
    _strict_keys(ci, {"job", "command"}, "allowlist.ci")
    _string(ci["job"], "allowlist.ci.job")
    _string(ci["command"], "allowlist.ci.command")

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

    condition2_adjudications: list[Condition2Adjudication] = []
    for index, raw in enumerate(
        _array(
            value["condition_2_adjudications"],
            "allowlist.condition_2_adjudications",
        )
    ):
        item = _object(raw, f"allowlist.condition_2_adjudications[{index}]")
        _strict_keys(
            item,
            {"symbol", "reason"},
            f"allowlist.condition_2_adjudications[{index}]",
        )
        symbol = _string(
            item["symbol"],
            f"allowlist.condition_2_adjudications[{index}].symbol",
        )
        if "." not in symbol or not all(
            part.isidentifier() for part in symbol.split(".")
        ):
            raise ContractError(
                "condition_2_adjudications.symbol は完全修飾シンボルが必要"
            )
        condition2_adjudications.append(
            Condition2Adjudication(
                symbol=symbol,
                reason=_string(
                    item["reason"],
                    f"allowlist.condition_2_adjudications[{index}].reason",
                ),
            )
        )
    adjudicated_symbols = [item.symbol for item in condition2_adjudications]
    if not condition2_adjudications or len(adjudicated_symbols) != len(
        set(adjudicated_symbols)
    ):
        raise ContractError(
            "condition_2_adjudications は空にできず、symbol は一意でなければならない"
        )

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
    condition2_rule = next(rule for rule in rules if rule.condition == 2)
    for adjudication in condition2_adjudications:
        candidates = {_normalize_identifier(adjudication.symbol)}
        candidates.update(
            _normalize_identifier(part)
            for part in adjudication.symbol.split(".")
        )
        if not any(
            pattern.search(candidate)
            for candidate in candidates
            for pattern in condition2_rule.patterns
        ):
            raise ContractError(
                "condition_2_adjudications.symbol は条件 2 の候補でなければならない: "
                f"{adjudication.symbol}"
            )
    return (
        tuple(allowed_symbols),
        tuple(rules),
        tuple(condition2_adjudications),
        command,
    )


def _load_negative_fixtures(value: dict[str, Any]) -> tuple[NegativeFixture, ...]:
    """負例 fixture の全数表を検証して読む。"""
    _strict_keys(
        value,
        {
            "schema_version",
            "fixture_set_revision",
            "fixture_root",
            "fixtures",
            "baseline_control",
        },
        "negative-fixtures.json",
    )
    if _integer(value["schema_version"], "negative.schema_version") != 1:
        raise ContractError("negative.schema_version は 1 でなければならない")
    if _integer(value["fixture_set_revision"], "negative.fixture_set_revision") < 1:
        raise ContractError("negative.fixture_set_revision は 1 以上が必要")
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
        allowed_errors = {f"TB00{condition}"}
        if condition == 5:
            allowed_errors.add("TB007")
        if expected_error not in allowed_errors:
            raise ContractError(
                f"negative.fixtures[{index}].expected_error が条件 {condition} と不一致"
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
            "forbidden_construction_symbols",
            "integrity_secret_symbol",
            "integrity_secret_allowed_symbols",
            "integrity_proof_factory_symbol",
            "integrity_proof_factory_allowed_symbols",
            "allowed_test_modules",
            "allowed_product_modules",
            "baseline_control",
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
    if "." not in constructor_symbol:
        raise ContractError("TenantContext のコンストラクタは完全修飾名が必要")
    forbidden_construction_symbols = frozenset(
        _string_array(
            value["forbidden_construction_symbols"],
            "tenant_context.forbidden_construction_symbols",
        )
    )
    if not forbidden_construction_symbols:
        raise ContractError("TenantContext の禁止生成・改竄経路は空にできない")
    integrity_secret_symbol = _string(
        value["integrity_secret_symbol"],
        "tenant_context.integrity_secret_symbol",
    )
    integrity_secret_allowed_symbols = frozenset(
        _string_array(
            value["integrity_secret_allowed_symbols"],
            "tenant_context.integrity_secret_allowed_symbols",
        )
    )
    if not integrity_secret_symbol.startswith("pitchlog.") or not (
        integrity_secret_allowed_symbols
    ):
        raise ContractError("発行証跡の秘密と参照許可シンボルは閉集合が必要")
    integrity_proof_factory_symbol = _string(
        value["integrity_proof_factory_symbol"],
        "tenant_context.integrity_proof_factory_symbol",
    )
    integrity_proof_factory_allowed_symbols = frozenset(
        _string_array(
            value["integrity_proof_factory_allowed_symbols"],
            "tenant_context.integrity_proof_factory_allowed_symbols",
        )
    )
    if not integrity_proof_factory_symbol.startswith("pitchlog.") or not (
        integrity_proof_factory_allowed_symbols
    ):
        raise ContractError("発行証跡の導出関数と参照許可シンボルは閉集合が必要")
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
        forbidden_construction_symbols=forbidden_construction_symbols,
        integrity_secret_symbol=integrity_secret_symbol,
        integrity_secret_allowed_symbols=integrity_secret_allowed_symbols,
        integrity_proof_factory_symbol=integrity_proof_factory_symbol,
        integrity_proof_factory_allowed_symbols=(
            integrity_proof_factory_allowed_symbols
        ),
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
            "baseline_control",
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
    asset_values: dict[Path, dict[str, Any]] = {
        DEFAULT_INVENTORY: inventory_value,
        DEFAULT_ALLOWLIST: allowlist_value,
        DEFAULT_NEGATIVE_FIXTURES: negative_value,
        DEFAULT_TENANT_CONTEXT_ALLOWLIST: tenant_context_value,
        DEFAULT_CACHE_INVALIDATION_CONTRACT: cache_invalidation_value,
    }
    for asset_path in FROZEN_BASELINE_ASSETS:
        if asset_path not in asset_values:
            asset_values[asset_path], _ = _read_json(repository_root / asset_path)
        _validate_baseline_control(asset_values[asset_path], asset_path.as_posix())
    (
        apis,
        receiver_factories,
        symbol_aliases,
        conservative_member_names,
    ) = _load_inventory(inventory_value)
    allowed_symbols, rules, condition2_adjudications, diff_command = _load_allowlist(
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
        receiver_factories=receiver_factories,
        symbol_aliases=symbol_aliases,
        conservative_member_names=conservative_member_names,
        allowed_symbols=allowed_symbols,
        rules=rules,
        condition2_adjudications=condition2_adjudications,
        negative_fixtures=negative_fixtures,
        tenant_context=tenant_context,
        cache_invalidation=cache_invalidation,
        diff_command=diff_command,
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


def _absolute_import_from_module(
    *,
    current_module: str,
    current_is_package: bool,
    imported_module: str | None,
    level: int,
) -> str | None:
    """現在のモジュールと相対 level から import 元の絶対名を返す。"""
    if level == 0:
        return imported_module
    if level < 0 or not current_module:
        return None

    package_parts = current_module.split(".")
    if not current_is_package:
        package_parts.pop()
    parents_to_drop = level - 1
    if not package_parts or parents_to_drop >= len(package_parts):
        return None
    if parents_to_drop:
        package_parts = package_parts[:-parents_to_drop]
    if imported_module:
        package_parts.extend(imported_module.split("."))
    return ".".join(package_parts)


_MAX_REEXPORT_DEPTH = 8
_WILDCARD_EXPORT = "*"


@dataclass(frozen=True)
class _ExportResolution:
    """再輸出名が到達しうる終端起源と解決不能状態を表す。"""

    origins: frozenset[str] = frozenset()
    unresolved: bool = False


@dataclass(frozen=True)
class _ExportReference:
    """再輸出の参照先を表す。terminal はそれ以上追跡しない起源を示す。"""

    module: str
    name: str
    terminal: bool = False

    @property
    def symbol(self) -> str:
        """参照先を完全修飾名へ整形する。"""
        return f"{self.module}.{self.name}".strip(".")


@dataclass(frozen=True)
class _RawExport:
    """解決前の再輸出参照集合を表す。"""

    references: frozenset[_ExportReference] = frozenset()
    unresolved: bool = False


def _static_export_reference(
    node: ast.AST,
    *,
    current_module: str,
    module_aliases: Mapping[str, str],
) -> _ExportReference | None:
    """静的な名前・module 属性式を再輸出参照へ変換する。"""
    if isinstance(node, ast.Name):
        imported_module = module_aliases.get(node.id)
        if imported_module is not None:
            return _ExportReference(imported_module, "", terminal=True)
        return _ExportReference(current_module, node.id)
    if not isinstance(node, ast.Attribute):
        return None
    attributes: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        attributes.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    imported_module = module_aliases.get(current.id)
    if imported_module is None:
        return None
    attributes.reverse()
    return _ExportReference(
        ".".join([imported_module, *attributes[:-1]]),
        attributes[-1],
    )


def _unknown_compound_exports(node: ast.AST) -> set[str]:
    """未対応の複合文がトップレベルへ束縛しうる名前を返す。"""
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(child.name)
        elif isinstance(child, ast.Import):
            names.update(
                alias.asname or alias.name.split(".")[0]
                for alias in child.names
            )
        elif isinstance(child, ast.ImportFrom):
            names.update(
                alias.asname or alias.name
                for alias in child.names
                if alias.name != "*"
            )
        elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            names.add(child.id)
    return names


def _raw_module_exports(
    tree: ast.Module,
    *,
    module: str,
    module_is_package: bool,
    initial: Mapping[str, _RawExport] | None = None,
) -> dict[str, _RawExport]:
    """1 モジュールのトップレベル束縛を未解決の再輸出グラフへ変換する。"""
    bindings = dict(initial or {})
    module_aliases: dict[str, str] = {}

    def process_block(
        statements: Sequence[ast.stmt],
        target_bindings: dict[str, _RawExport],
        target_aliases: dict[str, str],
    ) -> None:
        for statement in statements:
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    local = alias.asname or alias.name.split(".")[0]
                    imported = alias.name if alias.asname else alias.name.split(".")[0]
                    target_aliases[local] = imported
                    target_bindings[local] = _RawExport(
                        frozenset(
                            {_ExportReference(imported, "", terminal=True)}
                        )
                    )
                continue
            if isinstance(statement, ast.ImportFrom):
                provider = _absolute_import_from_module(
                    current_module=module,
                    current_is_package=module_is_package,
                    imported_module=statement.module,
                    level=statement.level,
                )
                for alias in statement.names:
                    if alias.name == "*":
                        target_bindings[_WILDCARD_EXPORT] = _RawExport(
                            unresolved=True
                        )
                        continue
                    local = alias.asname or alias.name
                    target_aliases.pop(local, None)
                    if provider is None:
                        target_bindings[local] = _RawExport(unresolved=True)
                    else:
                        target_bindings[local] = _RawExport(
                            frozenset({_ExportReference(provider, alias.name)})
                        )
                continue
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                target_aliases.pop(statement.name, None)
                target_bindings[statement.name] = _RawExport(
                    frozenset(
                        {
                            _ExportReference(
                                module,
                                statement.name,
                                terminal=True,
                            )
                        }
                    )
                )
                continue
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                value = statement.value
                targets: Sequence[ast.expr]
                if isinstance(statement, ast.Assign):
                    targets = statement.targets
                else:
                    targets = (statement.target,)
                reference = (
                    None
                    if value is None
                    else _static_export_reference(
                        value,
                        current_module=module,
                        module_aliases=target_aliases,
                    )
                )
                for target in targets:
                    if not isinstance(target, ast.Name):
                        continue
                    target_aliases.pop(target.id, None)
                    target_bindings[target.id] = (
                        _RawExport(unresolved=True)
                        if reference is None
                        else _RawExport(frozenset({reference}))
                    )
                continue
            if isinstance(statement, ast.If):
                before_bindings = dict(target_bindings)
                branches: list[
                    tuple[dict[str, _RawExport], dict[str, str]]
                ] = []
                bodies = [statement.body]
                if statement.orelse:
                    bodies.append(statement.orelse)
                else:
                    bodies.append([])
                for body in bodies:
                    branch_bindings = dict(before_bindings)
                    branch_aliases = dict(target_aliases)
                    process_block(body, branch_bindings, branch_aliases)
                    branches.append((branch_bindings, branch_aliases))
                changed_names = {
                    name
                    for branch_bindings, _ in branches
                    for name in set(before_bindings) | set(branch_bindings)
                    if branch_bindings.get(name) != before_bindings.get(name)
                }
                for name in changed_names:
                    references = frozenset(
                        reference
                        for branch_bindings, _ in branches
                        for reference in branch_bindings.get(
                            name,
                            _RawExport(unresolved=True),
                        ).references
                    )
                    target_bindings[name] = _RawExport(
                        references,
                        unresolved=True,
                    )
                    target_aliases.pop(name, None)
                if any(
                    _WILDCARD_EXPORT in branch_bindings
                    for branch_bindings, _ in branches
                ):
                    target_bindings[_WILDCARD_EXPORT] = _RawExport(
                        unresolved=True
                    )
                continue
            if isinstance(
                statement,
                (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith,
                 ast.Try, ast.TryStar, ast.Match),
            ):
                for name in _unknown_compound_exports(statement):
                    target_aliases.pop(name, None)
                    target_bindings[name] = _RawExport(unresolved=True)
                if any(
                    isinstance(child, ast.ImportFrom)
                    and any(alias.name == "*" for alias in child.names)
                    for child in ast.walk(statement)
                ):
                    target_bindings[_WILDCARD_EXPORT] = _RawExport(
                        unresolved=True
                    )

    process_block(tree.body, bindings, module_aliases)
    return bindings


def _build_reexport_map(
    sources: Mapping[str, str],
) -> dict[str, dict[str, _ExportResolution]]:
    """snapshot 全体からモジュール別の再輸出起源写像を構築する。"""
    raw_modules: dict[str, dict[str, _RawExport]] = {}
    for path, source in sorted(sources.items()):
        module = _module_name(path)
        if not module:
            continue
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError:
            raw_modules.setdefault(module, {})[_WILDCARD_EXPORT] = _RawExport(
                unresolved=True
            )
            continue
        raw_modules[module] = _raw_module_exports(
            tree,
            module=module,
            module_is_package=Path(path).stem == "__init__",
            initial=raw_modules.get(module),
        )

    def resolve(
        module: str,
        name: str,
        *,
        depth: int,
        visiting: frozenset[tuple[str, str]],
    ) -> _ExportResolution:
        key = (module, name)
        if depth > _MAX_REEXPORT_DEPTH or key in visiting:
            return _ExportResolution(unresolved=True)
        bindings = raw_modules.get(module)
        if bindings is None:
            if module == "pitchlog" or module.startswith("pitchlog."):
                return _ExportResolution(unresolved=True)
            return _ExportResolution(frozenset({f"{module}.{name}".strip(".")}))
        binding = bindings.get(name)
        if binding is None:
            return _ExportResolution(unresolved=True)
        origins: set[str] = set()
        unresolved = binding.unresolved
        next_visiting = visiting | {key}
        for reference in binding.references:
            if reference.terminal:
                origins.add(reference.symbol)
                continue
            resolution = resolve(
                reference.module,
                reference.name,
                depth=depth + 1,
                visiting=next_visiting,
            )
            origins.update(resolution.origins)
            unresolved = unresolved or resolution.unresolved
        return _ExportResolution(frozenset(origins), unresolved)

    return {
        module: {
            name: (
                _ExportResolution(unresolved=True)
                if name == _WILDCARD_EXPORT
                else resolve(
                    module,
                    name,
                    depth=0,
                    visiting=frozenset(),
                )
            )
            for name in bindings
        }
        for module, bindings in raw_modules.items()
    }


def _lookup_reexport_symbol(
    symbol: str,
    *,
    current_module: str,
    reexport_map: Mapping[str, Mapping[str, _ExportResolution]] | None,
) -> _ExportResolution | None:
    """完全修飾名または現在モジュールの裸名を再輸出写像へ照合する。

    ``reexport_map`` が ``None`` の単一 source 検査では (v) を適用しない。
    本番の repository 検査は snapshot ごとの写像を必ず供給する。
    """
    if reexport_map is None:
        return None
    if "." not in symbol:
        exports = reexport_map.get(current_module)
        if exports is None:
            return None
        return exports.get(symbol) or exports.get(_WILDCARD_EXPORT)
    for module in sorted(reexport_map, key=len, reverse=True):
        prefix = f"{module}."
        if not symbol.startswith(prefix):
            continue
        export_name = symbol.removeprefix(prefix)
        if "." in export_name:
            return None
        exports = reexport_map[module]
        return exports.get(export_name) or exports.get(_WILDCARD_EXPORT)
    if symbol.startswith("pitchlog."):
        return _ExportResolution(unresolved=True)
    return None


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """関数定義を整形非依存の署名文字列へ変換する。"""
    clone = copy.copy(node)
    clone.decorator_list = []
    clone.body = [ast.Pass()]
    rendered = ast.unparse(clone).splitlines()[0]
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    return rendered.removeprefix(prefix).removesuffix(":")


def _constant_string(node: ast.AST) -> str | None:
    """文字列リテラルとその ``+`` 連結を静的に畳み込む。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _constant_string(node.left)
        right = _constant_string(node.right)
        if left is not None and right is not None:
            return left + right
    return None


class _AliasCollector(ast.NodeVisitor):
    """import・型注釈・単純代入からシンボルと receiver の由来を収集する。"""

    def __init__(
        self,
        member_owners: Set[str],
        call_returns: Mapping[str, str],
        symbol_aliases: Mapping[str, str],
        conservative_member_names: frozenset[str],
        module: str,
        module_is_package: bool,
    ) -> None:
        self.aliases: dict[str, str] = {}
        self.known_symbols: dict[str, str] = {
            name: f"builtins.{name}"
            for name, value in vars(builtins).items()
            if callable(value)
        }
        self.known_receiver_kinds: dict[str, str] = {
            name: "symbol" for name in self.known_symbols
        }
        self.known_class_symbols: set[str] = {
            f"builtins.{name}"
            for name, value in vars(builtins).items()
            if isinstance(value, type)
        }
        self.function_returns: dict[str, str] = {}
        self.member_owners = member_owners
        self.call_returns = call_returns
        self.symbol_aliases = symbol_aliases
        self.conservative_member_names = conservative_member_names
        self.module = module
        self.module_is_package = module_is_package
        self.class_stack: list[str] = []
        self.unresolved_database_callables: dict[str, str] = {}
        self.direct_import_names: set[str] = set()

    def canonical(self, symbol: str) -> str:
        """公開 re-export を inventory の標準 receiver へ寄せる。"""
        return self.symbol_aliases.get(symbol, symbol)

    def resolve(self, node: ast.AST) -> str | None:
        """式を既知の完全修飾名へ解決する。"""
        if isinstance(node, ast.Subscript):
            return self.resolve(node.value)
        if isinstance(node, ast.Name):
            return self.canonical(self.aliases.get(node.id, node.id))
        if isinstance(node, ast.Attribute):
            parent = self.resolve(node.value)
            if parent is None:
                return None
            qualified = f"{parent}.{node.attr}"
            return self.canonical(self.aliases.get(qualified, qualified))
        return None

    def resolve_value(self, node: ast.AST) -> str | None:
        """別名式または既知 factory の戻り receiver 型を解決する。"""
        resolved = self.resolve(node)
        if resolved is not None:
            return resolved
        if not isinstance(node, ast.Call):
            return None
        called = self.resolve(node.func)
        if called is not None and called in self.call_returns:
            return self.call_returns[called]
        if called not in {"getattr", "builtins.getattr"} or len(node.args) < 2:
            return None
        receiver = self.resolve(node.args[0])
        attribute = _constant_string(node.args[1])
        if receiver is None or attribute is None:
            return None
        return self.canonical(f"{receiver}.{attribute}")

    def resolve_known(self, node: ast.AST) -> str | None:
        """静的な由来が確認できる式だけを完全修飾名へ解決する。"""
        if isinstance(node, ast.Subscript):
            return self.resolve_known(node.value)
        if isinstance(node, ast.Name):
            return self.known_symbols.get(node.id)
        if isinstance(node, ast.Attribute):
            parent = self.resolve_known(node.value)
            if parent is None:
                return None
            qualified = f"{parent}.{node.attr}"
            return self.canonical(self.aliases.get(qualified, qualified))
        if isinstance(node, ast.Call):
            called = self.resolve_known(node.func)
            if called is None:
                return None
            if called in self.call_returns:
                return self.call_returns[called]
            if called in self.known_class_symbols:
                return called
            return self.function_returns.get(called)
        if isinstance(node, ast.Dict):
            return "builtins.dict"
        if isinstance(node, ast.List):
            return "builtins.list"
        if isinstance(node, ast.Set):
            return "builtins.set"
        if isinstance(node, ast.Tuple):
            return "builtins.tuple"
        if isinstance(node, ast.Constant):
            return f"builtins.{type(node.value).__name__}"
        return None

    def receiver_provenance(
        self,
        node: ast.AST,
        *,
        tenant_context_symbol: str,
    ) -> str:
        """receiver を DB・TenantContext・非 DB・不明へ分類する。"""
        resolved = self.resolve_known(node)
        if resolved is None:
            return "unknown"
        canonical = self.canonical(resolved)
        if canonical == tenant_context_symbol:
            return "tenant_context"
        if canonical in self.member_owners:
            return "db"
        if isinstance(node, ast.Name):
            kind = self.known_receiver_kinds.get(node.id, "unknown")
            return kind if kind in {"db", "non_db"} else "unknown"
        if isinstance(node, ast.Call) or isinstance(
            node,
            (ast.Constant, ast.Dict, ast.List, ast.Set, ast.Tuple),
        ):
            return "non_db"
        return "unknown"

    def _record_known(
        self,
        local_name: str,
        symbol: str,
        *,
        receiver_kind: str = "symbol",
    ) -> None:
        """由来を確認できたローカル名だけを記録する。"""
        canonical = self.canonical(symbol)
        self.aliases[local_name] = canonical
        self.known_symbols[local_name] = canonical
        self.known_receiver_kinds[local_name] = receiver_kind

    def _receiver_kind_for_type(self, symbol: str) -> str:
        """明示された型を DB receiver または非 DB 型へ分類する。"""
        return "db" if self.canonical(symbol) in self.member_owners else "non_db"

    def _known_value_receiver_kind(self, node: ast.AST, symbol: str) -> str:
        """代入元の由来種別を、単なる import 済みシンボルと区別して返す。"""
        if isinstance(node, ast.Name):
            return self.known_receiver_kinds.get(node.id, "symbol")
        if isinstance(node, ast.Call) or isinstance(
            node,
            (ast.Constant, ast.Dict, ast.List, ast.Set, ast.Tuple),
        ):
            return self._receiver_kind_for_type(symbol)
        return "symbol"

    def _resolve_known_value(self, node: ast.AST) -> str | None:
        """代入値について、確認できた由来だけを返す。"""
        return self.resolve_known(node)

    def _record_arguments(self, arguments: ast.arguments) -> None:
        """引数の型注釈から任意名 receiver の由来を解決する。"""
        positional = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
        for argument in positional:
            if argument.annotation is None:
                continue
            resolved = self.resolve(argument.annotation)
            if resolved is not None and resolved not in {
                "Any",
                "object",
                "builtins.object",
                "typing.Any",
                "typing_extensions.Any",
            }:
                self._record_known(
                    argument.arg,
                    resolved,
                    receiver_kind=self._receiver_kind_for_type(resolved),
                )
        for argument in (arguments.vararg, arguments.kwarg):
            if argument is None or argument.annotation is None:
                continue
            resolved = self.resolve(argument.annotation)
            if resolved is not None and resolved not in {
                "Any",
                "object",
                "builtins.object",
                "typing.Any",
                "typing_extensions.Any",
            }:
                self._record_known(
                    argument.arg,
                    resolved,
                    receiver_kind=self._receiver_kind_for_type(resolved),
                )

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        """import 文のローカル名を記録する。"""
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".")[0]
            imported = alias.name if alias.asname else alias.name.split(".")[0]
            self.direct_import_names.add(local_name)
            self._record_known(local_name, imported)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        """from import 文のローカル名を記録する。"""
        module = _absolute_import_from_module(
            current_module=self.module,
            current_is_package=self.module_is_package,
            imported_module=node.module,
            level=node.level,
        )
        for alias in node.names:
            if alias.name == "*":
                continue
            local_name = alias.asname or alias.name
            self.direct_import_names.add(local_name)
            if module is None:
                continue
            self._record_known(
                local_name,
                f"{module}.{alias.name}",
            )

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        """名前別名と factory 戻り値の receiver 型を記録する。"""
        self.generic_visit(node.value)
        resolved = self.resolve_value(node.value)
        known = self._resolve_known_value(node.value)
        if resolved is None and known is None:
            return
        resolved = known if resolved is None else resolved
        assert resolved is not None
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.aliases[target.id] = resolved
                if known is not None:
                    self.known_symbols[target.id] = known
                    self.known_receiver_kinds[target.id] = (
                        self._known_value_receiver_kind(node.value, known)
                    )
                elif (
                    isinstance(node.value, ast.Attribute)
                    and node.value.attr in self.conservative_member_names
                ):
                    self.unresolved_database_callables[target.id] = (
                        node.value.attr
                    )
                elif (
                    isinstance(node.value, ast.Name)
                    and node.value.id in self.unresolved_database_callables
                ):
                    self.unresolved_database_callables[target.id] = (
                        self.unresolved_database_callables[node.value.id]
                    )
            elif isinstance(target, ast.Attribute):
                target_name = self.resolve(target)
                if target_name is not None:
                    self.aliases[target_name] = resolved

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        """注釈付きの単純な名前別名代入を記録する。"""
        resolved_annotation = self.resolve(node.annotation)
        informative_annotation = resolved_annotation not in {
            None,
            "Any",
            "object",
            "builtins.object",
            "typing.Any",
            "typing_extensions.Any",
        }
        if isinstance(node.target, ast.Name) and informative_annotation:
            assert resolved_annotation is not None
            self._record_known(
                node.target.id,
                resolved_annotation,
                receiver_kind=self._receiver_kind_for_type(resolved_annotation),
            )
        if node.value is None:
            return
        self.generic_visit(node.value)
        if isinstance(node.target, ast.Name) and informative_annotation:
            return
        resolved = self.resolve_value(node.value)
        known = self._resolve_known_value(node.value)
        resolved = known if resolved is None else resolved
        if resolved is not None and isinstance(node.target, ast.Name):
            self.aliases[node.target.id] = resolved
            if known is not None:
                self.known_symbols[node.target.id] = known
                self.known_receiver_kinds[node.target.id] = (
                    self._known_value_receiver_kind(node.value, known)
                )

    def _record_function_return(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        symbol: str,
    ) -> None:
        """ローカル factory の明示した戻り型を記録する。"""
        if node.returns is None:
            return
        resolved = self.resolve(node.returns)
        if resolved is not None and resolved not in {
            "Any",
            "object",
            "builtins.object",
            "typing.Any",
            "typing_extensions.Any",
        }:
            self.function_returns[symbol] = resolved

    def _record_with_items(self, items: list[ast.withitem]) -> None:
        """context manager の既知 factory 戻り値を ``as`` 変数へ伝播する。"""
        for item in items:
            if not isinstance(item.optional_vars, ast.Name):
                continue
            known = self._resolve_known_value(item.context_expr)
            if known is not None:
                self._record_known(
                    item.optional_vars.id,
                    known,
                    receiver_kind=self._receiver_kind_for_type(known),
                )

    def visit_With(self, node: ast.With) -> None:  # noqa: N802
        """同期 context manager の ``as`` 変数を記録する。"""
        self._record_with_items(node.items)
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:  # noqa: N802
        """非同期 context manager の ``as`` 変数を記録する。"""
        self._record_with_items(node.items)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        """ローカルクラスとメソッドの ``self`` / ``cls`` の由来を記録する。"""
        symbol = ".".join([self.module, *self.class_stack, node.name]).strip(".")
        self._record_known(node.name, symbol)
        self.known_class_symbols.add(symbol)
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """同期関数の引数注釈と本体の別名を収集する。"""
        symbol = ".".join([self.module, *self.class_stack, node.name]).strip(".")
        self._record_known(node.name, symbol)
        self._record_function_return(node, symbol)
        if self.class_stack and node.args.args:
            self._record_known(
                node.args.args[0].arg,
                ".".join([self.module, *self.class_stack]).strip("."),
                receiver_kind="non_db",
            )
        self._record_arguments(node.args)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        """非同期関数の引数注釈と本体の別名を収集する。"""
        symbol = ".".join([self.module, *self.class_stack, node.name]).strip(".")
        self._record_known(node.name, symbol)
        self._record_function_return(node, symbol)
        if self.class_stack and node.args.args:
            self._record_known(
                node.args.args[0].arg,
                ".".join([self.module, *self.class_stack]).strip("."),
                receiver_kind="non_db",
            )
        self._record_arguments(node.args)
        self.generic_visit(node)


@dataclass(frozen=True)
class _FlowValue:
    """値の可能な起源集合・未解決性・外部入力性を保持する。"""

    symbol: str | None = None
    kind: str = "unknown"
    elements: tuple[_FlowValue, ...] = ()
    origins: frozenset[str] = frozenset()
    unresolved: bool = False
    external_input: bool = False

    def __post_init__(self) -> None:
        """単一起源の既存生成箇所を起源集合へ自動的に反映する。"""
        if self.symbol is not None and not self.origins:
            object.__setattr__(self, "origins", frozenset({self.symbol}))


_UNKNOWN_FLOW_VALUE = _FlowValue(unresolved=True)
_EXTERNAL_INPUT_FLOW_VALUE = _FlowValue(external_input=True)


@dataclass(frozen=True)
class _FlowOutcome:
    """文または文列から後続へ到達できる由来環境を表す。"""

    environment: dict[str, _FlowValue] | None
    breaks: tuple[dict[str, _FlowValue], ...] = ()
    continues: tuple[dict[str, _FlowValue], ...] = ()


@dataclass(frozen=True)
class _ModuleBindings:
    """module-wide の別名解決を無効にする再束縛名を表す。"""

    global_names: frozenset[str]
    condition2_names: frozenset[str]
    defined_names: frozenset[str]
    has_star_import: bool


def _module_bindings(source: str, path: str) -> _ModuleBindings:
    """構文の種類を列挙せず、コンパイラのシンボル表から再束縛名を得る。

    ``global`` / ``nonlocal`` は宣言だけなら再束縛とせず、代入または import の
    writer をシンボル表で検出する。クラス名前空間のローカル名は
    メソッドの閉包ではないため callable 判定から除き、条件 2 の裁定だけを
    fail-closed にする。クラス配下の関数・lambda の束縛は通常どおり含める。
    """
    table = symtable.symtable(source, path, "exec")
    module_code = compile(source, path, "exec")
    module_operations = Counter(
        instruction.argval
        for instruction in dis.get_instructions(module_code)
        if instruction.opname
        in {"STORE_NAME", "STORE_GLOBAL", "DELETE_NAME", "DELETE_GLOBAL"}
        and isinstance(instruction.argval, str)
    )
    module_rebindings = {
        name for name, count in module_operations.items() if count > 1
    }
    module_defined_names = {
        symbol.get_name()
        for symbol in table.get_symbols()
        if symbol.is_assigned()
        and not symbol.is_imported()
        and module_operations[symbol.get_name()] == 1
    }
    global_names = set(module_rebindings)
    condition2_names = set(module_rebindings)
    condition2_names.update(
        symbol.get_name()
        for symbol in table.get_symbols()
        if symbol.is_annotated()
    )

    def collect(scope: symtable.SymbolTable) -> None:
        for symbol in scope.get_symbols():
            rebound = (
                symbol.is_parameter()
                or symbol.is_imported()
                or symbol.is_assigned()
            )
            if not rebound:
                continue
            condition2_names.add(symbol.get_name())
            if symbol.is_global() and (
                symbol.is_assigned() or symbol.is_imported()
            ):
                global_names.add(symbol.get_name())
        for child in scope.get_children():
            collect(child)

    for child in table.get_children():
        collect(child)
    return _ModuleBindings(
        global_names=frozenset(global_names),
        condition2_names=frozenset(condition2_names),
        defined_names=frozenset(module_defined_names),
        has_star_import=any(
            isinstance(node, ast.ImportFrom)
            and any(alias.name == "*" for alias in node.names)
            for node in ast.walk(ast.parse(source, filename=path))
        ),
    )


class _LexicalCallClassifier(ast.NodeVisitor):
    """裸名が実際に参照する字句束縛をコンパイラの表から特定する。"""

    def __init__(self, table: symtable.SymbolTable) -> None:
        self.scope_stack = [table]
        self.used_children: dict[symtable.SymbolTable, set[int]] = {}
        self.comprehension_names: list[set[str]] = []
        self.lexical_name_ids: set[int] = set()

    def _take_child(
        self,
        expected_type: str,
        expected_name: str,
        *,
        required: bool,
    ) -> symtable.SymbolTable | None:
        """現在の表から AST と対応する未使用の子スコープを得る。"""
        parent = self.scope_stack[-1]
        children = parent.get_children()
        used = self.used_children.setdefault(parent, set())
        for index, child in enumerate(children):
            if index in used or child.get_name() != expected_name:
                continue
            candidate = child
            if child.get_type() == "type parameter":
                candidate = next(
                    (
                        nested
                        for nested in child.get_children()
                        if nested.get_type() == expected_type
                        and nested.get_name() == expected_name
                    ),
                    child,
                )
            if candidate.get_type() != expected_type:
                continue
            used.add(index)
            return candidate
        if required:
            raise ContractError(
                "字句スコープと AST の対応を解決できない: "
                f"{expected_type} {expected_name}"
            )
        return None

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        """定義時の式は外側、本体は関数のシンボル表で訪問する。"""
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)
        arguments = (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
            node.args.vararg,
            node.args.kwarg,
        )
        for argument in arguments:
            if argument is not None:
                self.visit(argument)
        if node.returns is not None:
            self.visit(node.returns)
        for type_param in node.type_params:
            self.visit(type_param)
        scope = self._take_child("function", node.name, required=True)
        assert scope is not None
        self.scope_stack.append(scope)
        for statement in node.body:
            self.visit(statement)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """同期関数の定義式と本体を別スコープで訪問する。"""
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        """非同期関数の定義式と本体を別スコープで訪問する。"""
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        """クラス本体を独立名前空間として訪問する。"""
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)
        for type_param in node.type_params:
            self.visit(type_param)
        scope = self._take_child("class", node.name, required=True)
        assert scope is not None
        self.scope_stack.append(scope)
        for statement in node.body:
            self.visit(statement)
        self.scope_stack.pop()

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
        """lambda の既定値を外側、本体を lambda スコープで訪問する。"""
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)
        scope = self._take_child("function", "lambda", required=True)
        assert scope is not None
        self.scope_stack.append(scope)
        self.visit(node.body)
        self.scope_stack.pop()

    @staticmethod
    def _target_names(target: ast.AST) -> set[str]:
        """内包表記 target が束縛する裸名を返す。"""
        return {
            child.id
            for child in ast.walk(target)
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
        }

    def _visit_comprehension(
        self,
        node: ast.DictComp | ast.GeneratorExp | ast.ListComp | ast.SetComp,
        expressions: Sequence[ast.expr],
    ) -> None:
        """内包 target の有効範囲を評価順に反映する。"""
        first, *remaining = node.generators
        self.visit(first.iter)
        scope = self._take_child(
            "function",
            "genexpr" if isinstance(node, ast.GeneratorExp) else type(node).__name__.lower(),
            required=isinstance(node, ast.GeneratorExp),
        )
        if scope is not None:
            self.scope_stack.append(scope)
        names = self._target_names(first.target)
        self.comprehension_names.append(names)
        self.visit(first.target)
        for condition in first.ifs:
            self.visit(condition)
        for generator in remaining:
            self.visit(generator.iter)
            names.update(self._target_names(generator.target))
            self.visit(generator.target)
            for condition in generator.ifs:
                self.visit(condition)
        for expression in expressions:
            self.visit(expression)
        self.comprehension_names.pop()
        if scope is not None:
            self.scope_stack.pop()

    def visit_DictComp(self, node: ast.DictComp) -> None:  # noqa: N802
        """辞書内包の字句束縛を訪問する。"""
        self._visit_comprehension(node, (node.key, node.value))

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:  # noqa: N802
        """生成内包の字句束縛を訪問する。"""
        self._visit_comprehension(node, (node.elt,))

    def visit_ListComp(self, node: ast.ListComp) -> None:  # noqa: N802
        """リスト内包の字句束縛を訪問する。"""
        self._visit_comprehension(node, (node.elt,))

    def visit_SetComp(self, node: ast.SetComp) -> None:  # noqa: N802
        """集合内包の字句束縛を訪問する。"""
        self._visit_comprehension(node, (node.elt,))

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        """Load が module でなく字句束縛へ解決される場合だけ記録する。"""
        if not isinstance(node.ctx, ast.Load):
            return
        if any(node.id in names for names in self.comprehension_names):
            self.lexical_name_ids.add(id(node))
            return
        scope = self.scope_stack[-1]
        if scope.get_type() != "function":
            return
        try:
            symbol = scope.lookup(node.id)
        except KeyError:
            return
        if not symbol.is_global():
            self.lexical_name_ids.add(id(node))


def _lexically_bound_name_ids(
    tree: ast.Module,
    source: str,
    path: str,
) -> frozenset[int]:
    """関数・lambda・内包表記の字句束縛を参照する Name ID を返す。"""
    classifier = _LexicalCallClassifier(symtable.symtable(source, path, "exec"))
    classifier.visit(tree)
    return frozenset(classifier.lexical_name_ids)


class _FlowProvenance:
    """危険呼び出しに必要な由来だけを字句スコープと制御フロー沿いに追跡する。"""

    def __init__(
        self,
        *,
        module: str,
        module_is_package: bool,
        member_owners: Set[str],
        receiver_names: Set[str],
        call_returns: Mapping[str, str],
        symbol_aliases: Mapping[str, str],
        tenant_context_symbol: str,
    ) -> None:
        self.module = module
        self.module_is_package = module_is_package
        self.member_owners = member_owners
        self.database_type_names = {
            *(owner.rsplit(".", 1)[-1] for owner in member_owners),
            *receiver_names,
        }
        self.call_returns = call_returns
        self.symbol_aliases = symbol_aliases
        self.tenant_context_symbol = tenant_context_symbol
        self.callable_symbols: dict[int, str | None] = {}
        self.callable_values: dict[int, _FlowValue] = {}
        self.receiver_kinds: dict[int, str] = {}
        self.argument_kinds: dict[tuple[int, int], str] = {}
        self.function_returns: dict[str, _FlowValue] = {}
        self.return_value_stack: list[list[_FlowValue]] = []
        self.class_members: dict[str, _FlowValue] = {}
        self.class_base_values: dict[int, _FlowValue] = {}
        self.class_stack: list[str] = []

    def canonical(self, symbol: str) -> str:
        """inventory が宣言した re-export を標準シンボルへ寄せる。"""
        return self.symbol_aliases.get(symbol, symbol)

    def _kind_for_type(self, symbol: str) -> str:
        """明示型を DB・TenantContext・非 DB へ分類する。"""
        canonical = self.canonical(symbol)
        if canonical == self.tenant_context_symbol:
            return "tenant_context"
        if canonical in self.member_owners:
            return "db"
        return "non_db"

    def _resolve_annotation(
        self,
        node: ast.AST | None,
        environment: Mapping[str, _FlowValue],
    ) -> _FlowValue:
        """注釈を、現在位置で確認できる型だけへ解決する。"""
        if node is None:
            return _UNKNOWN_FLOW_VALUE
        if isinstance(node, ast.Subscript):
            wrapper = self._resolve_annotation(node.value, environment).symbol
            elements = (
                tuple(node.slice.elts)
                if isinstance(node.slice, ast.Tuple)
                else (node.slice,)
            )
            if wrapper in {"typing.Annotated", "typing_extensions.Annotated"}:
                return self._resolve_annotation(elements[0], environment)
            if wrapper in {
                "typing.Optional",
                "typing.Union",
                "typing_extensions.Optional",
                "typing_extensions.Union",
            }:
                members = [
                    self._resolve_annotation(element, environment)
                    for element in elements
                ]
                if wrapper.endswith(".Optional"):
                    members.append(_FlowValue("builtins.NoneType", "non_db"))
                return self._join_annotation_members(members)
            return self._resolve_annotation(node.value, environment)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return self._join_annotation_members(
                (
                    self._resolve_annotation(node.left, environment),
                    self._resolve_annotation(node.right, environment),
                )
            )
        if isinstance(node, ast.Constant) and node.value is None:
            return _FlowValue("builtins.NoneType", "non_db")
        if isinstance(node, ast.Name):
            value = environment.get(node.id, _UNKNOWN_FLOW_VALUE)
            if value.kind in {"class_non_db", "class_unknown"}:
                kind = "non_db" if value.kind == "class_non_db" else "unknown"
                return _FlowValue(
                    value.symbol,
                    kind,
                    origins=value.origins,
                    unresolved=value.unresolved,
                    external_input=value.external_input,
                )
            if value.symbol is None or value.symbol in {
                "typing.Any",
                "typing_extensions.Any",
                "builtins.object",
            }:
                return _FlowValue(
                    kind="unknown",
                    origins=value.origins,
                    unresolved=value.unresolved,
                    external_input=value.external_input,
                )
            return _FlowValue(
                value.symbol,
                self._kind_for_type(value.symbol),
                origins=value.origins,
                unresolved=value.unresolved,
                external_input=value.external_input,
            )
        if isinstance(node, ast.Attribute):
            value = self._expression(node, dict(environment))
            if value.symbol is None:
                return _FlowValue(
                    kind="unknown",
                    origins=value.origins,
                    unresolved=value.unresolved,
                    external_input=value.external_input,
                )
            return _FlowValue(
                value.symbol,
                self._kind_for_type(value.symbol),
                origins=value.origins,
                unresolved=value.unresolved,
                external_input=value.external_input,
            )
        return _UNKNOWN_FLOW_VALUE

    def _join_annotation_members(
        self,
        members: Sequence[_FlowValue],
    ) -> _FlowValue:
        """Union 系注釈を DB 優先・不明 fail-closed で分類する。"""
        joined = self._joined_value(members)
        if any(member.kind == "db" for member in members):
            return _FlowValue(
                kind="db",
                origins=joined.origins,
                unresolved=joined.unresolved,
                external_input=joined.external_input,
            )
        if any(member.kind == "unknown" for member in members):
            return joined
        tenant_members = [
            member for member in members if member.kind == "tenant_context"
        ]
        if tenant_members:
            if all(
                member.kind == "tenant_context"
                or member.symbol == "builtins.NoneType"
                for member in members
            ):
                return _FlowValue(
                    self.tenant_context_symbol,
                    "tenant_context",
                    origins=joined.origins,
                    unresolved=joined.unresolved,
                    external_input=joined.external_input,
                )
            return joined
        return _FlowValue(
            kind="non_db",
            origins=joined.origins,
            unresolved=joined.unresolved,
            external_input=joined.external_input,
        )

    def _call_result(self, callable_value: _FlowValue) -> _FlowValue:
        """既知 factory・ローカルクラス・明示戻り型だけを戻り値へ伝播する。"""
        symbol = callable_value.symbol
        if symbol is not None and symbol in self.call_returns:
            returned = self.canonical(self.call_returns[symbol])
            return _FlowValue(returned, self._kind_for_type(returned))
        if callable_value.kind == "class_non_db":
            return _FlowValue(symbol, "non_db")
        if callable_value.kind == "class_unknown":
            return _FlowValue(
                kind="unknown",
                origins=callable_value.origins,
                unresolved=True,
                external_input=callable_value.external_input,
            )
        if symbol is not None and symbol in self.function_returns:
            return self.function_returns[symbol]
        if callable_value.kind == "function" and callable_value.elements:
            return self._joined_value(callable_value.elements)
        if symbol is not None and symbol.startswith("builtins."):
            builtin_name = symbol.rsplit(".", 1)[-1]
            value = vars(builtins).get(builtin_name)
            if isinstance(value, type):
                return _FlowValue(symbol, "non_db")
        # callable の由来が既知でも未対応の戻り値は外部入力とは限らない。
        # 起源を証明できない値として扱い、後段を fail-closed に保つ。
        return _UNKNOWN_FLOW_VALUE

    def _joined_value(self, values: Sequence[_FlowValue]) -> _FlowValue:
        """分岐の可能な起源を失わず、種別だけを保守的に合流する。"""
        if not values:
            return _UNKNOWN_FLOW_VALUE
        first = values[0]
        if all(value == first for value in values):
            return first
        kinds = {value.kind for value in values}
        kind = (
            first.kind
            if len(kinds) == 1
            and first.kind
            in {"db", "non_db", "non_db_attribute", "tenant_context"}
            else "unknown"
        )
        symbols = {value.symbol for value in values}
        symbol = symbols.pop() if len(symbols) == 1 else None
        elements = (
            first.elements
            if all(value.elements == first.elements for value in values)
            else ()
        )
        return _FlowValue(
            symbol,
            kind,
            elements,
            origins=frozenset(
                origin for value in values for origin in value.origins
            ),
            unresolved=any(value.unresolved for value in values),
            external_input=any(value.external_input for value in values),
        )

    def _return_summary(
        self,
        values: Sequence[_FlowValue],
        *,
        declared: _FlowValue | None = None,
    ) -> _FlowValue:
        """実 return は起源だけを要約し、安全な戻り型は注釈からのみ得る。"""
        actual = self._joined_value(values)
        if declared is None:
            return _FlowValue(
                origins=actual.origins,
                unresolved=actual.unresolved,
                external_input=actual.external_input,
            )
        return _FlowValue(
            declared.symbol,
            declared.kind,
            declared.elements,
            origins=declared.origins | actual.origins,
            unresolved=declared.unresolved or actual.unresolved,
            external_input=declared.external_input or actual.external_input,
        )

    def _attribute_value(
        self,
        node: ast.Attribute,
        environment: dict[str, _FlowValue],
    ) -> tuple[_FlowValue, _FlowValue]:
        """属性と receiver を一度だけ評価して返す。"""
        receiver = self._expression(node.value, environment)
        if receiver.unresolved:
            return (
                _FlowValue(
                    origins=receiver.origins,
                    unresolved=True,
                    external_input=receiver.external_input,
                ),
                receiver,
            )
        if receiver.symbol is None:
            return (
                _FlowValue(
                    kind="unknown",
                    origins=frozenset(
                        f"{origin}.{node.attr}" for origin in receiver.origins
                    ),
                    unresolved=receiver.unresolved,
                    external_input=receiver.external_input,
                ),
                receiver,
            )
        symbol = self.canonical(f"{receiver.symbol}.{node.attr}")
        declared = self.class_members.get(symbol)
        if declared is not None:
            return declared, receiver
        if receiver.kind == "db":
            kind = "db"
        elif receiver.kind in {"non_db", "non_db_attribute"}:
            kind = "non_db_attribute"
        else:
            kind = "symbol"
        return _FlowValue(symbol, kind), receiver

    def _expression(
        self,
        node: ast.AST,
        environment: dict[str, _FlowValue],
    ) -> _FlowValue:
        """式を評価順に走査し、呼び出し位置の由来を記録する。"""
        if isinstance(node, ast.Name):
            return environment.get(node.id, _UNKNOWN_FLOW_VALUE)
        if isinstance(node, ast.Attribute):
            value, _ = self._attribute_value(node, environment)
            return value
        if isinstance(node, ast.Call):
            receiver = _UNKNOWN_FLOW_VALUE
            if isinstance(node.func, ast.Attribute):
                callable_value, receiver = self._attribute_value(
                    node.func,
                    environment,
                )
            else:
                callable_value = self._expression(node.func, environment)
            self.callable_symbols[id(node)] = callable_value.symbol
            self.callable_values[id(node)] = callable_value
            self.receiver_kinds[id(node)] = receiver.kind
            argument_values: list[_FlowValue] = []
            for index, argument in enumerate(node.args):
                argument_value = self._expression(argument, environment)
                argument_values.append(argument_value)
                self.argument_kinds[(id(node), index)] = argument_value.kind
            for keyword in node.keywords:
                self._expression(keyword.value, environment)
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr
                in {
                    "append",
                    "extend",
                    "insert",
                    "update",
                    "setdefault",
                    "__setitem__",
                }
            ):
                written = self._joined_value(argument_values)
                self._invalidate_storage(
                    node.func.value,
                    written,
                    environment,
                )
            if (
                callable_value.symbol == "builtins.getattr"
                and argument_values
                and argument_values[0].kind
                in {"non_db", "non_db_attribute", "class_non_db"}
            ):
                target = argument_values[0]
                result = _FlowValue(
                    f"{target.symbol or '<non-db>'}.<dynamic-attribute>",
                    "non_db_attribute",
                    origins=target.origins,
                    unresolved=target.unresolved,
                    external_input=target.external_input,
                )
            elif callable_value.symbol == "builtins.dict.get" and receiver.elements:
                candidates = [*receiver.elements]
                if len(argument_values) >= 2:
                    candidates.append(argument_values[1])
                result = self._joined_value(candidates)
            else:
                result = self._call_result(callable_value)
            if callable_value.kind in {"class_non_db", "class_unknown"}:
                result = _FlowValue(
                    result.symbol,
                    result.kind,
                    tuple(argument_values),
                    origins=frozenset(
                        {
                            *result.origins,
                            *(
                                origin
                                for value in argument_values
                                for origin in value.origins
                            ),
                        }
                    ),
                    unresolved=result.unresolved
                    or any(value.unresolved for value in argument_values),
                    external_input=result.external_input
                    or any(value.external_input for value in argument_values),
                )
            if result.kind == "unknown" and receiver.kind in {"db", "db_result"}:
                return _FlowValue(kind="db_result")
            return result
        if isinstance(node, ast.NamedExpr):
            value = self._expression(node.value, environment)
            self._assign_target(node.target, value, environment)
            return value
        if isinstance(node, ast.Dict):
            elements: list[_FlowValue] = []
            for key, value in zip(node.keys, node.values, strict=True):
                if key is not None:
                    self._expression(key, environment)
                elements.append(self._expression(value, environment))
            return _FlowValue(
                "builtins.dict",
                "non_db",
                tuple(elements),
                origins=frozenset(
                    {
                        "builtins.dict",
                        *(origin for value in elements for origin in value.origins),
                    }
                ),
                unresolved=any(value.unresolved for value in elements),
                external_input=any(value.external_input for value in elements),
            )
        if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
            elements = tuple(self._expression(item, environment) for item in node.elts)
            type_name = type(node).__name__.lower()
            symbol = f"builtins.{type_name}"
            return _FlowValue(
                symbol,
                "non_db",
                elements,
                origins=frozenset(
                    {
                        symbol,
                        *(origin for value in elements for origin in value.origins),
                    }
                ),
                unresolved=any(value.unresolved for value in elements),
                external_input=any(value.external_input for value in elements),
            )
        if isinstance(node, ast.Constant):
            return _FlowValue(f"builtins.{type(node.value).__name__}", "non_db")
        if isinstance(node, ast.Subscript):
            container = self._expression(node.value, environment)
            self._expression(node.slice, environment)
            if not container.elements:
                if (
                    not container.unresolved
                    and container.symbol is not None
                    and container.kind == "symbol"
                ):
                    return container
                return _FlowValue(
                    kind="unknown",
                    origins=container.origins,
                    unresolved=True,
                    external_input=container.external_input,
                )
            if (
                isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, int)
            ):
                index = node.slice.value
                if -len(container.elements) <= index < len(container.elements):
                    return container.elements[index]
            return self._joined_value(container.elements)
        if isinstance(node, ast.IfExp):
            self._expression(node.test, environment)
            return self._joined_value(
                (
                    self._expression(node.body, dict(environment)),
                    self._expression(node.orelse, dict(environment)),
                )
            )
        if isinstance(node, ast.BoolOp):
            return self._joined_value(
                tuple(self._expression(value, environment) for value in node.values)
            )
        if isinstance(node, ast.DictComp):
            # 従来評価済みの key/value は保ち、新規位置だけ fail-closed で覆う。
            coverage_environment: dict[str, _FlowValue] = {}
            for generator in node.generators:
                iterable = self._expression(
                    generator.iter,
                    coverage_environment,
                )
                self._assign_iteration_target(
                    generator.target,
                    iterable,
                    coverage_environment,
                )
                for condition in generator.ifs:
                    self._expression(condition, coverage_environment)
            self._expression(node.key, environment)
            self._expression(node.value, environment)
            return _UNKNOWN_FLOW_VALUE
        if isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
            local = dict(environment)
            for generator in node.generators:
                iterable = self._expression(generator.iter, local)
                self._assign_iteration_target(generator.target, iterable, local)
                for condition in generator.ifs:
                    self._expression(condition, local)
            element = self._expression(node.elt, local)
            if isinstance(node, ast.ListComp):
                return _FlowValue(
                    "builtins.list",
                    "non_db",
                    (element,),
                    origins=frozenset({"builtins.list", *element.origins}),
                    unresolved=element.unresolved,
                    external_input=element.external_input,
                )
            if isinstance(node, ast.SetComp):
                return _FlowValue(
                    "builtins.set",
                    "non_db",
                    (element,),
                    origins=frozenset({"builtins.set", *element.origins}),
                    unresolved=element.unresolved,
                    external_input=element.external_input,
                )
            return _FlowValue(
                "builtins.generator",
                "non_db",
                (element,),
                origins=frozenset({"builtins.generator", *element.origins}),
                unresolved=element.unresolved,
                external_input=element.external_input,
            )
        if isinstance(node, ast.Lambda):
            default_values = self._argument_default_values(node.args, environment)
            local = dict(environment)
            self._bind_arguments(
                node.args,
                local,
                default_values=default_values,
            )
            returned = self._expression(node.body, local)
            return _FlowValue(
                kind="function",
                elements=(self._return_summary((returned,)),),
            )
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._expression(child, environment)
        return _UNKNOWN_FLOW_VALUE

    def _assign_iteration_target(
        self,
        target: ast.AST,
        iterable: _FlowValue,
        environment: dict[str, _FlowValue],
    ) -> None:
        """既知 tuple 列から内包表記の分割代入を保守的に導出する。"""
        if not iterable.elements:
            self._assign_target(
                target,
                self._unresolved_from(iterable),
                environment,
            )
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            columns: list[list[_FlowValue]] = [[] for _ in target.elts]
            for element in iterable.elements:
                if len(element.elements) != len(target.elts):
                    self._assign_target(
                        target,
                        self._unresolved_from(iterable),
                        environment,
                    )
                    return
                for index, item in enumerate(element.elements):
                    columns[index].append(item)
            for item_target, values in zip(target.elts, columns, strict=True):
                self._assign_target(
                    item_target,
                    self._joined_value(values),
                    environment,
                )
            return
        self._assign_target(
            target,
            self._joined_value(iterable.elements),
            environment,
        )

    @staticmethod
    def _unresolved_from(value: _FlowValue) -> _FlowValue:
        """既知起源を保持したまま値の精密な形だけを不明へ倒す。"""
        return _FlowValue(
            origins=value.origins,
            unresolved=True,
            external_input=value.external_input,
        )

    @staticmethod
    def _storage_root_name(node: ast.AST) -> str | None:
        """属性・添字の格納域を保持する最外の裸名を返す。"""
        current = node
        while isinstance(current, (ast.Attribute, ast.Subscript)):
            current = current.value
        return current.id if isinstance(current, ast.Name) else None

    def _invalidate_storage(
        self,
        storage: ast.AST,
        written: _FlowValue,
        environment: dict[str, _FlowValue],
    ) -> None:
        """可変格納域の既知要素を破棄し、書込値を含む可能起源だけ残す。"""
        root = self._storage_root_name(storage)
        if root is None or root not in environment:
            return
        previous = environment[root]
        environment[root] = _FlowValue(
            previous.symbol,
            previous.kind,
            origins=previous.origins | written.origins,
            unresolved=True,
            external_input=previous.external_input or written.external_input,
        )

    def _assign_target(
        self,
        target: ast.AST,
        value: _FlowValue,
        environment: dict[str, _FlowValue],
    ) -> None:
        """代入先を更新し、未解決値なら以前の証明を破棄する。"""
        if isinstance(target, ast.Name):
            environment[target.id] = value
            return
        if isinstance(target, ast.Starred):
            self._assign_target(target.value, value, environment)
            return
        if isinstance(target, ast.Attribute):
            self._expression(target.value, environment)
            self._invalidate_storage(target.value, value, environment)
            return
        if isinstance(target, ast.Subscript):
            self._expression(target.value, environment)
            self._expression(target.slice, environment)
            self._invalidate_storage(target.value, value, environment)
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            if len(value.elements) == len(target.elts):
                for item, element in zip(target.elts, value.elements, strict=True):
                    self._assign_target(item, element, environment)
            else:
                for item in target.elts:
                    self._assign_target(
                        item,
                        self._unresolved_from(value),
                        environment,
                    )

    def _join_environments(
        self,
        environments: Sequence[Mapping[str, _FlowValue]],
    ) -> dict[str, _FlowValue]:
        """全分岐で同じ由来だけを合流後へ残す。"""
        names = set().union(*(environment.keys() for environment in environments))
        joined: dict[str, _FlowValue] = {}
        for name in names:
            values = [environment.get(name, _UNKNOWN_FLOW_VALUE) for environment in environments]
            joined[name] = self._joined_value(values)
        return joined

    def _class_value(
        self,
        node: ast.ClassDef,
        environment: dict[str, _FlowValue],
    ) -> _FlowValue:
        """同名 shadow と DB 継承を除外してローカルクラスの安全性を返す。"""
        symbol = ".".join([self.module, *self.class_stack, node.name]).strip(".")
        if node.name in self.database_type_names:
            return _FlowValue(symbol, "class_unknown")
        base_values = [self._expression(base, environment) for base in node.bases]
        for base, resolved in zip(node.bases, base_values, strict=True):
            self.class_base_values[id(base)] = resolved
        if any(
            resolved.kind in {"unknown", "db", "tenant_context"}
            or self.tenant_context_symbol in resolved.origins
            for resolved in base_values
        ):
            return _FlowValue(
                symbol,
                "class_unknown",
                origins=frozenset(
                    {
                        symbol,
                        *(
                            origin
                            for resolved in base_values
                            for origin in resolved.origins
                        ),
                    }
                ),
                unresolved=any(value.unresolved for value in base_values),
                external_input=any(
                    value.external_input for value in base_values
                ),
            )
        return _FlowValue(symbol, "class_non_db")

    def _bind_arguments(
        self,
        arguments: ast.arguments,
        environment: dict[str, _FlowValue],
        *,
        annotation_environment: Mapping[str, _FlowValue] | None = None,
        default_values: Mapping[str, _FlowValue] | None = None,
    ) -> None:
        """関数引数を外部入力と既定値の可能な起源へ束縛する。"""
        annotations = annotation_environment or environment
        defaults = default_values or {}
        positional = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
        for argument in positional:
            resolved = self._resolve_annotation(
                argument.annotation,
                annotations,
            )
            external = (
                _EXTERNAL_INPUT_FLOW_VALUE
                if resolved == _UNKNOWN_FLOW_VALUE
                else _FlowValue(
                    resolved.symbol,
                    resolved.kind,
                    resolved.elements,
                    origins=resolved.origins,
                    unresolved=resolved.unresolved,
                    external_input=True,
                )
            )
            environment[argument.arg] = (
                self._joined_value((external, defaults[argument.arg]))
                if argument.arg in defaults
                else external
            )
        for argument in (arguments.vararg, arguments.kwarg):
            if argument is not None:
                resolved = self._resolve_annotation(
                    argument.annotation,
                    annotations,
                )
                environment[argument.arg] = (
                    _EXTERNAL_INPUT_FLOW_VALUE
                    if resolved == _UNKNOWN_FLOW_VALUE
                    else _FlowValue(
                        resolved.symbol,
                        resolved.kind,
                        resolved.elements,
                        origins=resolved.origins,
                        unresolved=resolved.unresolved,
                        external_input=True,
                    )
                )

    def _argument_default_values(
        self,
        arguments: ast.arguments,
        environment: dict[str, _FlowValue],
    ) -> dict[str, _FlowValue]:
        """定義時環境で評価した既定値を対応する引数名へ割り当てる。"""
        values: dict[str, _FlowValue] = {}
        positional = [*arguments.posonlyargs, *arguments.args]
        if arguments.defaults:
            default_arguments = positional[-len(arguments.defaults) :]
            for argument, default in zip(
                default_arguments,
                arguments.defaults,
                strict=True,
            ):
                values[argument.arg] = self._expression(default, environment)
        for argument, default in zip(
            arguments.kwonlyargs,
            arguments.kw_defaults,
            strict=True,
        ):
            if default is not None:
                values[argument.arg] = self._expression(default, environment)
        return values

    def _refine_isinstance_true_branch(
        self,
        test: ast.AST,
        environment: dict[str, _FlowValue],
    ) -> None:
        """単純な isinstance 真分岐だけを明示型へ絞り込む。"""
        if not (
            isinstance(test, ast.Call)
            and isinstance(test.func, ast.Name)
            and test.func.id == "isinstance"
            and len(test.args) == 2
            and isinstance(test.args[0], ast.Name)
        ):
            return
        refined = self._resolve_annotation(test.args[1], environment)
        if refined.kind != "unknown":
            environment[test.args[0].id] = refined

    def _bind_match_pattern(
        self,
        pattern: ast.pattern,
        subject: _FlowValue,
        environment: dict[str, _FlowValue],
    ) -> None:
        """pattern の捕捉名へ subject の可能な起源を保守的に伝播する。"""
        def sequence_value(values: Sequence[_FlowValue]) -> _FlowValue:
            """star capture 用に要素列と全起源を保持した list 値を作る。"""
            return _FlowValue(
                "builtins.list",
                "non_db",
                tuple(values),
                origins=frozenset(
                    {
                        "builtins.list",
                        *(origin for value in values for origin in value.origins),
                    }
                ),
                unresolved=any(value.unresolved for value in values),
                external_input=any(value.external_input for value in values),
            )

        if isinstance(pattern, ast.MatchAs):
            if pattern.pattern is not None:
                self._bind_match_pattern(pattern.pattern, subject, environment)
            if pattern.name is not None:
                environment[pattern.name] = subject
            return
        if isinstance(pattern, ast.MatchStar):
            if pattern.name is not None:
                environment[pattern.name] = (
                    sequence_value(subject.elements)
                    if subject.elements
                    and subject.symbol in {"builtins.list", "builtins.tuple"}
                    else subject
                )
            return
        if isinstance(pattern, ast.MatchMapping):
            for child in pattern.patterns:
                self._bind_match_pattern(child, subject, environment)
            if pattern.rest is not None:
                environment[pattern.rest] = subject
            return
        if isinstance(pattern, ast.MatchSequence):
            values = (
                subject.elements
                if subject.symbol in {"builtins.list", "builtins.tuple"}
                else ()
            )
            star_index = next(
                (
                    index
                    for index, child in enumerate(pattern.patterns)
                    if isinstance(child, ast.MatchStar)
                ),
                None,
            )
            for index, child in enumerate(pattern.patterns):
                captured = subject
                if values:
                    if index == star_index:
                        assert star_index is not None
                        trailing = len(pattern.patterns) - star_index - 1
                        stop = len(values) - trailing if trailing else len(values)
                        captured = sequence_value(values[star_index:stop])
                    elif star_index is None or index < star_index:
                        if index < len(values):
                            captured = values[index]
                    else:
                        trailing_index = len(values) - (len(pattern.patterns) - index)
                        if 0 <= trailing_index < len(values):
                            captured = values[trailing_index]
                self._bind_match_pattern(child, captured, environment)
            return
        if isinstance(pattern, ast.MatchClass):
            children = (*pattern.patterns, *pattern.kwd_patterns)
            for child in children:
                self._bind_match_pattern(child, subject, environment)
            return
        if isinstance(pattern, ast.MatchOr):
            branch_environments: list[dict[str, _FlowValue]] = []
            for child in pattern.patterns:
                branch = dict(environment)
                self._bind_match_pattern(child, subject, branch)
                branch_environments.append(branch)
            environment.update(self._join_environments(branch_environments))

    def _analyze_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        environment: dict[str, _FlowValue],
        *,
        self_value: _FlowValue | None = None,
        body_environment: dict[str, _FlowValue] | None = None,
    ) -> None:
        """定義式と本体の環境を分け、外側を書き換えず解析する。"""
        local = dict(body_environment if body_environment is not None else environment)
        default_values = self._argument_default_values(node.args, environment)
        self._bind_arguments(
            node.args,
            local,
            annotation_environment=environment,
            default_values=default_values,
        )
        if self_value is not None and node.args.args:
            local[node.args.args[0].arg] = self_value
        for decorator in node.decorator_list:
            self._expression(decorator, environment)
        arguments = (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
            node.args.vararg,
            node.args.kwarg,
        )
        for argument in arguments:
            if argument is not None and argument.annotation is not None:
                self._expression(argument.annotation, environment)
        if node.returns is not None:
            self._expression(node.returns, environment)
        for type_param in node.type_params:
            self._expression(type_param, environment)
        symbol = ".".join([self.module, *self.class_stack, node.name]).strip(".")
        self.return_value_stack.append([])
        self._analyze_block(node.body, local)
        returned_values = self.return_value_stack.pop()
        if returned_values:
            declared = self.function_returns.get(symbol)
            self.function_returns[symbol] = self._return_summary(
                returned_values,
                declared=declared,
            )

    def _register_class_contracts(
        self,
        node: ast.ClassDef,
        environment: dict[str, _FlowValue],
        class_symbol: str,
    ) -> None:
        """同ファイルの属性注釈とメソッド戻り注釈を先に登録する。"""
        for statement in node.body:
            if (
                isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
            ):
                declared = self._resolve_annotation(
                    statement.annotation,
                    environment,
                )
                self.class_members[
                    f"{class_symbol}.{statement.target.id}"
                ] = declared
                continue
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbol = f"{class_symbol}.{statement.name}"
                returned = self._resolve_annotation(statement.returns, environment)
                if returned.kind != "unknown":
                    self.function_returns[symbol] = returned

    def _analyze_statement(
        self,
        node: ast.stmt,
        environment: dict[str, _FlowValue],
    ) -> _FlowOutcome:
        """1 文を解析し、後続へ到達する環境とループ制御を返す。"""
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                imported = alias.name if alias.asname else alias.name.split(".")[0]
                environment[local] = _FlowValue(imported, "symbol")
            return _FlowOutcome(environment)
        if isinstance(node, ast.ImportFrom):
            module = _absolute_import_from_module(
                current_module=self.module,
                current_is_package=self.module_is_package,
                imported_module=node.module,
                level=node.level,
            )
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                if module is None:
                    environment[local] = _UNKNOWN_FLOW_VALUE
                else:
                    symbol = self.canonical(f"{module}.{alias.name}")
                    environment[local] = _FlowValue(symbol, "symbol")
            return _FlowOutcome(environment)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbol = ".".join([self.module, *self.class_stack, node.name]).strip(".")
            environment[node.name] = _FlowValue(symbol, "function")
            returned = self._resolve_annotation(node.returns, environment)
            if returned.kind != "unknown":
                self.function_returns[symbol] = returned
            self._analyze_function(node, environment)
            return _FlowOutcome(environment)
        if isinstance(node, ast.ClassDef):
            for keyword in node.keywords:
                self._expression(keyword.value, environment)
            for type_param in node.type_params:
                self._expression(type_param, environment)
            class_value = self._class_value(node, environment)
            environment[node.name] = class_value
            for decorator in node.decorator_list:
                self._expression(decorator, environment)
            self.class_stack.append(node.name)
            class_environment: dict[str, _FlowValue] | None = dict(environment)
            if class_value.symbol is not None:
                self._register_class_contracts(
                    node,
                    class_environment,
                    class_value.symbol,
                )
            for statement in node.body:
                statement_environment = (
                    class_environment
                    if class_environment is not None
                    else {}
                )
                if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self._analyze_function(
                        statement,
                        statement_environment,
                        body_environment=environment,
                        self_value=_FlowValue(
                            class_value.symbol,
                            (
                                "non_db"
                                if class_value.kind == "class_non_db"
                                else "unknown"
                            ),
                        ),
                    )
                else:
                    outcome = self._analyze_statement(
                        statement,
                        statement_environment,
                    )
                    if class_environment is not None:
                        class_environment = outcome.environment
            self.class_stack.pop()
            return _FlowOutcome(environment)
        if isinstance(node, ast.Assign):
            value = self._expression(node.value, environment)
            for target in node.targets:
                self._assign_target(target, value, environment)
            return _FlowOutcome(environment)
        if isinstance(node, ast.AnnAssign):
            self._expression(node.annotation, environment)
            annotation = self._resolve_annotation(node.annotation, environment)
            value = (
                self._expression(node.value, environment)
                if node.value is not None
                else annotation
            )
            if value.kind == "unknown" and annotation.kind != "unknown":
                value = annotation
            self._assign_target(node.target, value, environment)
            return _FlowOutcome(environment)
        if isinstance(node, ast.AugAssign):
            self._expression(node.value, environment)
            self._assign_target(node.target, _UNKNOWN_FLOW_VALUE, environment)
            return _FlowOutcome(environment)
        if isinstance(node, ast.If):
            self._expression(node.test, environment)
            body_start = dict(environment)
            self._refine_isinstance_true_branch(node.test, body_start)
            body = self._analyze_block(node.body, body_start)
            otherwise = self._analyze_block(node.orelse, dict(environment))
            fallthrough = [
                outcome.environment
                for outcome in (body, otherwise)
                if outcome.environment is not None
            ]
            return _FlowOutcome(
                (
                    self._join_environments(fallthrough)
                    if fallthrough
                    else None
                ),
                (*body.breaks, *otherwise.breaks),
                (*body.continues, *otherwise.continues),
            )
        if isinstance(node, (ast.For, ast.AsyncFor)):
            iterable = self._expression(node.iter, environment)
            body_start = dict(environment)
            self._assign_iteration_target(node.target, iterable, body_start)
            body = self._analyze_block(node.body, body_start)
            natural_paths = [dict(environment), *body.continues]
            if body.environment is not None:
                natural_paths.append(body.environment)
            natural = self._join_environments(natural_paths)
            otherwise = self._analyze_block(node.orelse, natural)
            exits = [*body.breaks]
            if otherwise.environment is not None:
                exits.append(otherwise.environment)
            return _FlowOutcome(
                self._join_environments(exits) if exits else None,
                otherwise.breaks,
                otherwise.continues,
            )
        if isinstance(node, ast.While):
            self._expression(node.test, environment)
            body = self._analyze_block(node.body, dict(environment))
            natural_paths = [dict(environment), *body.continues]
            if body.environment is not None:
                natural_paths.append(body.environment)
            natural = self._join_environments(natural_paths)
            otherwise = self._analyze_block(node.orelse, natural)
            exits = [*body.breaks]
            if otherwise.environment is not None:
                exits.append(otherwise.environment)
            return _FlowOutcome(
                self._join_environments(exits) if exits else None,
                otherwise.breaks,
                otherwise.continues,
            )
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                value = self._expression(item.context_expr, environment)
                if item.optional_vars is not None:
                    self._assign_target(item.optional_vars, value, environment)
            return self._analyze_block(node.body, environment)
        if isinstance(node, (ast.Try, ast.TryStar)):
            body = self._analyze_block(node.body, dict(environment))
            handlers: list[_FlowOutcome] = []
            for handler in node.handlers:
                handler_environment = dict(environment)
                handler_type = _UNKNOWN_FLOW_VALUE
                if handler.type is not None:
                    handler_type = self._expression(
                        handler.type,
                        handler_environment,
                    )
                if handler.name is not None:
                    handler_environment[handler.name] = _FlowValue(
                        origins=handler_type.origins,
                        unresolved=handler_type.unresolved,
                        external_input=handler_type.external_input,
                    )
                handlers.append(
                    self._analyze_block(handler.body, handler_environment)
                )
            normal = body
            if body.environment is not None and node.orelse:
                normal = self._analyze_block(node.orelse, body.environment)
            candidates = [
                outcome.environment
                for outcome in (normal, *handlers)
                if outcome.environment is not None
            ]
            joined = self._join_environments(candidates) if candidates else None
            breaks = [*normal.breaks]
            continues = [*normal.continues]
            for handler in handlers:
                breaks.extend(handler.breaks)
                continues.extend(handler.continues)
            if joined is None:
                final = self._analyze_block(node.finalbody, dict(environment))
                return _FlowOutcome(
                    None,
                    (*breaks, *final.breaks),
                    (*continues, *final.continues),
                )
            final = self._analyze_block(node.finalbody, joined)
            return _FlowOutcome(
                final.environment,
                (*breaks, *final.breaks),
                (*continues, *final.continues),
            )
        if isinstance(node, ast.Match):
            subject = self._expression(node.subject, environment)
            branches: list[_FlowOutcome] = []
            for case in node.cases:
                case_environment = dict(environment)
                self._bind_match_pattern(
                    case.pattern,
                    subject,
                    case_environment,
                )
                if case.guard is not None:
                    self._expression(case.guard, case_environment)
                branches.append(
                    self._analyze_block(case.body, case_environment)
                )
            fallthrough = [dict(environment)]
            fallthrough.extend(
                outcome.environment
                for outcome in branches
                if outcome.environment is not None
            )
            return _FlowOutcome(
                self._join_environments(fallthrough),
                tuple(item for outcome in branches for item in outcome.breaks),
                tuple(item for outcome in branches for item in outcome.continues),
            )
        if isinstance(node, ast.Return):
            returned = (
                self._expression(node.value, environment)
                if node.value is not None
                else _FlowValue("builtins.NoneType", "non_db")
            )
            if self.return_value_stack:
                self.return_value_stack[-1].append(returned)
            return _FlowOutcome(None)
        if isinstance(node, ast.Raise):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.expr):
                    self._expression(child, environment)
            return _FlowOutcome(None)
        if isinstance(node, ast.Break):
            return _FlowOutcome(None, (dict(environment),))
        if isinstance(node, ast.Continue):
            return _FlowOutcome(None, continues=(dict(environment),))
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._expression(child, environment)
        return _FlowOutcome(environment)

    def _analyze_block(
        self,
        statements: Sequence[ast.stmt],
        environment: dict[str, _FlowValue],
    ) -> _FlowOutcome:
        """文列をソース順に解析し、終端後も不明由来で Call を採取する。"""
        current: dict[str, _FlowValue] | None = environment
        breaks: list[dict[str, _FlowValue]] = []
        continues: list[dict[str, _FlowValue]] = []
        for statement in statements:
            if current is None:
                self._analyze_statement(statement, {})
                continue
            outcome = self._analyze_statement(statement, current)
            current = outcome.environment
            breaks.extend(outcome.breaks)
            continues.extend(outcome.continues)
        return _FlowOutcome(current, tuple(breaks), tuple(continues))

    def analyze(self, tree: ast.Module) -> None:
        """モジュールを解析して各呼び出し位置の由来を確定する。"""
        builtins_environment = {
            name: _FlowValue(f"builtins.{name}", "symbol")
            for name, value in vars(builtins).items()
            if callable(value)
        }
        for statement in tree.body:
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    local = alias.asname or alias.name.split(".")[0]
                    imported = (
                        alias.name if alias.asname else alias.name.split(".")[0]
                    )
                    builtins_environment[local] = _FlowValue(imported, "symbol")
            elif isinstance(statement, ast.ImportFrom):
                module = _absolute_import_from_module(
                    current_module=self.module,
                    current_is_package=self.module_is_package,
                    imported_module=statement.module,
                    level=statement.level,
                )
                for alias in statement.names:
                    if alias.name == "*":
                        continue
                    local = alias.asname or alias.name
                    if module is None:
                        builtins_environment[local] = _UNKNOWN_FLOW_VALUE
                    else:
                        symbol = self.canonical(f"{module}.{alias.name}")
                        builtins_environment[local] = _FlowValue(symbol, "symbol")
        for statement in tree.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbol = f"{self.module}.{statement.name}".strip(".")
                builtins_environment[statement.name] = _FlowValue(
                    symbol,
                    "function",
                )
        self._analyze_block(tree.body, builtins_environment)

    def receiver_provenance(self, node: ast.Call) -> str:
        """属性呼び出し receiver の呼び出し時点の由来を返す。"""
        return self.receiver_kinds.get(id(node), "unknown")

    def argument_provenance(self, node: ast.Call, index: int) -> str:
        """呼び出し引数の評価時点の由来を返す。"""
        return self.argument_kinds.get((id(node), index), "unknown")

    def callable_symbol(self, node: ast.Call) -> str | None:
        """呼び出し時点で解決できた callable シンボルを返す。"""
        return self.callable_symbols.get(id(node))

    def callable_value(self, node: ast.Call) -> _FlowValue:
        """呼び出し時点の可能な起源集合と外部入力性を返す。"""
        return self.callable_values.get(id(node), _UNKNOWN_FLOW_VALUE)

    def class_base_value(self, node: ast.AST) -> _FlowValue:
        """クラス基底式の可能な起源集合と外部入力性を返す。"""
        return self.class_base_values.get(id(node), _UNKNOWN_FLOW_VALUE)


class _SourceScanner(ast.NodeVisitor):
    """1 モジュールの変更行を検査する。"""

    def __init__(
        self,
        *,
        path: str,
        module: str,
        tree: ast.Module,
        source: str | None = None,
        changed_lines: Set[int] | None,
        contract: Contract,
        reject_all_db_calls: bool,
        reexport_map: Mapping[
            str,
            Mapping[str, _ExportResolution],
        ] | None = None,
    ) -> None:
        self.path = path
        self.module = module
        self.module_is_package = Path(path).stem == "__init__"
        self.changed_lines = changed_lines
        self.contract = contract
        self.reject_all_db_calls = reject_all_db_calls
        self.reexport_map = reexport_map
        binding_source = source if source is not None else ast.unparse(tree)
        self.module_bindings = _module_bindings(binding_source, path)
        self.lexically_bound_name_ids = _lexically_bound_name_ids(
            tree,
            binding_source,
            path,
        )
        self.class_stack: list[str] = []
        self.function_stack: list[tuple[str, str]] = []
        self.safe_non_context_objects: list[set[str]] = []
        self.violations: list[Violation] = []
        self._violation_keys: set[tuple[int, int, str, str]] = set()
        self.checked_call_ids: set[int] = set()
        member_owners = {
            api.symbol.rsplit(".", 1)[0]
            for api in contract.apis
            if api.kind == "member"
        }
        call_returns = {
            item.symbol: item.returns for item in contract.receiver_factories
        }
        collector = _AliasCollector(
            member_owners,
            call_returns,
            contract.symbol_aliases,
            contract.conservative_member_names,
            module,
            self.module_is_package,
        )
        collector.visit(tree)
        self.aliases = collector
        receiver_names = {
            receiver
            for api in contract.apis
            if api.kind == "member"
            for receiver in api.receivers
        }
        flow = _FlowProvenance(
            module=module,
            module_is_package=self.module_is_package,
            member_owners=member_owners,
            receiver_names=receiver_names,
            call_returns=call_returns,
            symbol_aliases=contract.symbol_aliases,
            tenant_context_symbol=contract.tenant_context.constructor_symbol,
        )
        flow.analyze(tree)
        self.flow = flow
        self.api_by_symbol = {api.symbol: api for api in contract.apis}
        self.member_apis_by_method: dict[str, tuple[ApiSpec, ...]] = {}
        for api in contract.apis:
            if api.kind != "member":
                continue
            method = api.symbol.rsplit(".", 1)[1]
            self.member_apis_by_method[method] = (
                *self.member_apis_by_method.get(method, ()),
                api,
            )
        self.allowed_by_symbol = {
            item.symbol: item for item in contract.allowed_symbols
        }
        self.condition2_adjudicated_symbols = frozenset(
            item.symbol for item in contract.condition2_adjudications
        )
        self.condition2_patterns = next(
            rule.patterns for rule in contract.rules if rule.condition == 2
        )

    def _validate_call_coverage(self, tree: ast.Module) -> None:
        """AST・flow・scanner の Call 集合が同一であることを検証する。"""
        calls = {
            id(node): node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        ast_call_ids = frozenset(calls)
        flow_callable_ids = frozenset(self.flow.callable_symbols)
        flow_receiver_ids = frozenset(self.flow.receiver_kinds)
        scanner_call_ids = frozenset(self.checked_call_ids)
        if (
            ast_call_ids
            == flow_callable_ids
            == flow_receiver_ids
            == scanner_call_ids
        ):
            return

        def locations(call_ids: frozenset[int]) -> list[str]:
            """Call ID 集合を安定したソース位置へ変換する。"""
            return sorted(
                f"{calls[call_id].lineno}:{calls[call_id].col_offset}"
                for call_id in call_ids
                if call_id in calls
            )

        raise ContractError(
            f"{self.path}: Call 被覆不変条件が不一致: "
            f"ast={len(ast_call_ids)}, "
            f"flow_callable={len(flow_callable_ids)}, "
            f"flow_receiver={len(flow_receiver_ids)}, "
            f"scanner={len(scanner_call_ids)}, "
            f"flow_missing={locations(ast_call_ids - flow_callable_ids)}, "
            f"flow_extra={len(flow_callable_ids - ast_call_ids)}, "
            f"receiver_missing={locations(ast_call_ids - flow_receiver_ids)}, "
            f"receiver_extra={len(flow_receiver_ids - ast_call_ids)}, "
            f"scanner_missing={locations(ast_call_ids - scanner_call_ids)}, "
            f"scanner_extra={len(scanner_call_ids - ast_call_ids)}"
        )

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
        scope = (
            self.function_stack[-1][0]
            if self.function_stack
            else ".".join([self.module, *self.class_stack, "<module>"])
        )
        self.violations.append(
            Violation(
                path=self.path,
                line=line,
                condition=condition,
                code=code,
                symbol=symbol,
                message=message,
                end_line=getattr(node, "end_lineno", line),
                scope=scope,
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

    def _pool_connection_invalidation_allowed(self, text: str | None) -> bool:
        """真正性違反接続の破棄をキャッシュ無効化語彙から区別する。"""
        return bool(
            text
            in {
                "connection_record.invalidate",
                "sqlalchemy.pool.ConnectionPoolEntry.invalidate",
            }
            and self.function_stack
            and self.function_stack[-1][0]
            == "pitchlog.db.engine._verify_application_role_on_checkout"
        )

    def _check_identifier(
        self,
        text: str,
        node: ast.AST,
        *,
        allow_condition4: bool = False,
        condition2_candidate: str | None = None,
        condition2_symbol: str | None = None,
        condition2_only: bool = False,
    ) -> None:
        if not self._is_changed(node):
            return
        for rule in self.contract.rules:
            if condition2_only and rule.condition != 2:
                continue
            candidate_text = (
                condition2_candidate
                if rule.condition == 2 and condition2_candidate is not None
                else text
            )
            candidates = {_normalize_identifier(candidate_text)}
            candidates.update(
                _normalize_identifier(part)
                for part in candidate_text.split(".")
            )
            if (
                rule.condition == 2
                and (condition2_symbol or text)
                in self.condition2_adjudicated_symbols
            ):
                continue
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

    def _condition2_symbol_for_name(
        self,
        node: ast.Name,
        resolved: str,
    ) -> str:
        """裸名候補を、再束縛が無い場合だけ裁定用シンボルへ解決する。"""
        if (
            self.module_bindings.has_star_import
            or node.id in self.module_bindings.condition2_names
        ):
            return node.id
        if (
            node.id in self.module_bindings.defined_names
            and id(node) not in self.lexically_bound_name_ids
        ):
            return f"{self.module}.{node.id}"
        if not self._is_condition2_candidate(node.id):
            return resolved
        if node.id in self.aliases.direct_import_names or (
            node.id[:1].isupper()
            and resolved in self.aliases.known_class_symbols
        ):
            return resolved
        return node.id

    def _condition2_candidate_for_name(
        self,
        node: ast.Name,
    ) -> str:
        """条件 2 の候補を Store / Load とも構文上の裸名から得る。"""
        return node.id

    def _condition2_symbol_for_attribute(
        self,
        node: ast.Attribute,
        resolved: str,
    ) -> str:
        """receiver が再束縛されていない属性だけを裁定用に解決する。"""
        root: ast.AST = node.value
        while isinstance(root, (ast.Attribute, ast.Subscript)):
            root = root.value
        if not isinstance(root, ast.Name):
            return node.attr
        if (
            self.module_bindings.has_star_import
            or root.id in self.module_bindings.condition2_names
            or id(root) in self.lexically_bound_name_ids
        ):
            return node.attr
        return resolved

    def _check_condition2_syntax(self, name: str, node: ast.AST) -> None:
        """別名解決を使わず、構文上の identifier を条件 2 へ照合する。"""
        self._check_identifier(
            name,
            node,
            condition2_candidate=name,
            condition2_symbol=name,
            condition2_only=True,
        )

    def _is_condition2_candidate(self, text: str) -> bool:
        """文字列が変更不能な条件 2 パターンの候補に入るか返す。"""
        candidates = {_normalize_identifier(text)}
        candidates.update(_normalize_identifier(part) for part in text.split("."))
        return any(
            pattern.search(candidate)
            for candidate in candidates
            for pattern in self.condition2_patterns
        )

    def _raw_expression(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = self._raw_expression(node.value)
            if parent is None:
                return None
            return f"{parent}.{node.attr}"
        return None

    def _reexport_resolution(
        self,
        node: ast.AST,
        resolved: str | None,
    ) -> _ExportResolution | None:
        """式の局所 export 名と解決済み名を再輸出写像へ照合する。"""
        candidates: list[str] = []
        if isinstance(node, ast.Name):
            candidates.append(node.id)
        if resolved is not None and resolved not in candidates:
            candidates.append(resolved)
        resolutions = [
            resolution
            for candidate in candidates
            if (
                resolution := _lookup_reexport_symbol(
                    candidate,
                    current_module=self.module,
                    reexport_map=self.reexport_map,
                )
            )
            is not None
        ]
        if not resolutions:
            return None
        return _ExportResolution(
            frozenset(
                origin
                for resolution in resolutions
                for origin in resolution.origins
            ),
            any(resolution.unresolved for resolution in resolutions),
        )

    def _reject_reexport_call(
        self,
        node: ast.Call,
        *,
        resolved: str | None,
        callable_name: str | None,
        resolution: _ExportResolution | None,
        allowed_modules: Set[str],
    ) -> bool:
        """危険または解決不能な再輸出 callable を拒否したか返す。"""
        if resolution is None:
            return False
        if resolution.unresolved:
            self._add(
                node,
                condition=5,
                code="TB007",
                symbol=resolved or callable_name or "<unresolved-reexport>",
                message="再輸出 callable の起源を一意に解決できない",
            )
            return True
        if (
            self.contract.tenant_context.constructor_symbol
            not in resolution.origins
        ):
            return False
        if self.module in allowed_modules:
            return True
        self._add(
            node,
            condition=5,
            code="TB007",
            symbol=resolved or callable_name or "<tenant-context-reexport>",
            message="再輸出経由の TenantContext 構築は許可されない",
        )
        return True

    def _matching_api(self, node: ast.AST) -> _ApiMatch | None:
        """完全修飾一致と receiver 名だけの推測を区別して返す。"""
        resolved = self.aliases.resolve(node)
        raw = self._raw_expression(node)
        raw_root = "" if raw is None else raw.split(".", 1)[0]
        directly_imported = raw_root in self.aliases.direct_import_names
        if directly_imported and resolved in self.api_by_symbol:
            return _ApiMatch(self.api_by_symbol[resolved], True)
        if directly_imported and raw in self.api_by_symbol:
            return _ApiMatch(self.api_by_symbol[raw], True)
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
                return _ApiMatch(api, False)
        return None

    def _matching_dynamic_member(
        self,
        receiver_node: ast.AST,
        method: str,
    ) -> ApiSpec | None:
        """getattr の receiver と静的に畳み込んだ属性名を inventory へ照合する。"""
        resolved_receiver = self.aliases.resolve(receiver_node)
        raw_receiver = self._raw_expression(receiver_node)
        for receiver in (resolved_receiver, raw_receiver):
            if receiver is None:
                continue
            symbol = self.aliases.canonical(f"{receiver}.{method}")
            if symbol in self.api_by_symbol:
                return self.api_by_symbol[symbol]
        resolved_name = "" if resolved_receiver is None else resolved_receiver.rsplit(".", 1)[-1]
        raw_name = "" if raw_receiver is None else raw_receiver.rsplit(".", 1)[-1]
        for api in self.contract.apis:
            if api.kind != "member" or api.symbol.rsplit(".", 1)[1] != method:
                continue
            if resolved_name in api.receivers or raw_name in api.receivers:
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

    def _current_symbol(self) -> str | None:
        """現在検査中の関数・メソッドの完全修飾名を返す。"""
        return self.function_stack[-1][0] if self.function_stack else None

    def _check_db_call(self, node: ast.Call) -> None:
        if not self._is_changed(node):
            return
        provenance = self.flow.receiver_provenance(node)
        flow_symbol = self.flow.callable_symbol(node)
        flow_api = self.api_by_symbol.get(flow_symbol or "")
        match = (
            _ApiMatch(flow_api, True)
            if flow_api is not None
            else self._matching_api(node.func)
        )
        if match is not None and not match.exact and provenance == "non_db":
            match = None
        candidates = () if match is None else (match.api,)
        if (
            not candidates
            and isinstance(node.func, ast.Name)
            and node.func.id in self.aliases.unresolved_database_callables
        ):
            method = self.aliases.unresolved_database_callables[node.func.id]
            candidates = self.member_apis_by_method.get(method, ())
        if (
            not candidates
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in self.contract.conservative_member_names
        ):
            if provenance == "non_db":
                return
            candidates = self.member_apis_by_method.get(node.func.attr, ())
        if not candidates:
            return
        allowed = self._current_allowed_symbol()
        if (
            not self.reject_all_db_calls
            and allowed is not None
            and any(api.id in allowed.allowed_api_ids for api in candidates)
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
            symbol="|".join(sorted({item.symbol for item in candidates})),
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
        lexically_bound_callable = (
            isinstance(node.func, ast.Name)
            and id(node.func) in self.lexically_bound_name_ids
        )
        globally_rebound_callable = (
            isinstance(node.func, ast.Name)
            and not lexically_bound_callable
            and (
                self.module_bindings.has_star_import
                or node.func.id in self.module_bindings.global_names
            )
        )
        resolved = self.aliases.resolve(node.func) or self._raw_expression(node.func)
        if resolved is None and isinstance(node.func, ast.Call):
            dynamic_function = self.aliases.resolve(
                node.func.func
            ) or self._raw_expression(node.func.func)
            if (
                dynamic_function in {"getattr", "builtins.getattr"}
                and len(node.func.args) >= 2
                and (
                    self.aliases.resolve(node.func.args[0])
                    or self._raw_expression(node.func.args[0])
                )
                in {"object", "builtins.object"}
                and _constant_string(node.func.args[1]) == "__new__"
            ):
                resolved = "builtins.object.__new__"
        canonical_aliases = {
            "object.__new__": "builtins.object.__new__",
            "object.__setattr__": "builtins.object.__setattr__",
            "type": "builtins.type",
        }
        canonical_resolved = canonical_aliases.get(resolved or "", resolved)
        forbidden = self.contract.tenant_context.forbidden_construction_symbols
        constructor_lifecycle_symbols = {
            f"{self.contract.tenant_context.constructor_symbol}.__new__",
            f"{self.contract.tenant_context.constructor_symbol}.__init__",
        }
        if canonical_resolved in constructor_lifecycle_symbols:
            self._add(
                node,
                condition=5,
                code="TB007",
                symbol=canonical_resolved,
                message=(
                    "TenantContext の __new__ / __init__ 直接呼び出しによる "
                    "構築迂回は禁止"
                ),
            )
            return
        if (
            canonical_resolved == "builtins.object.__new__"
            and canonical_resolved in forbidden
            and node.args
        ):
            if (
                isinstance(node.args[0], ast.Name)
                and node.args[0].id == "cls"
                and self.class_stack
                and ".".join([self.module, *self.class_stack])
                != self.contract.tenant_context.constructor_symbol
            ):
                return
            self._add(
                node,
                condition=5,
                code="TB007",
                symbol="builtins.object.__new__",
                message="型を解決できない object.__new__ も TenantContext 生成迂回として拒否",
            )
            return
        if (
            canonical_resolved == "builtins.object.__setattr__"
            and canonical_resolved in forbidden
            and node.args
        ):
            target = node.args[0]
            target_name = target.id if isinstance(target, ast.Name) else None
            canonical_init = (
                f"{self.contract.tenant_context.constructor_symbol}.__init__"
            )
            safe_target = bool(
                self.safe_non_context_objects
                and target_name in self.safe_non_context_objects[-1]
            )
            if self._current_symbol() == canonical_init and target_name == "self":
                return
            if safe_target:
                return
            self._add(
                node,
                condition=5,
                code="TB007",
                symbol="builtins.object.__setattr__",
                message="正規構築箇所以外の object.__setattr__ による文脈改竄は禁止",
            )
            return
        if canonical_resolved == "dataclasses.replace" and canonical_resolved in forbidden:
            target_provenance = (
                self.flow.argument_provenance(node, 0)
                if node.args
                else "unknown"
            )
            if target_provenance == "non_db":
                return
            self._add(
                node,
                condition=5,
                code="TB007",
                symbol=canonical_resolved,
                message="dataclasses.replace による TenantContext 複製迂回は禁止",
            )
            return
        if canonical_resolved == "copy.copy":
            target_provenance = (
                self.flow.argument_provenance(node, 0)
                if node.args
                else "unknown"
            )
            if target_provenance == "non_db":
                return
            self._add(
                node,
                condition=5,
                code="TB007",
                symbol=canonical_resolved,
                message="copy.copy による TenantContext 複製迂回は禁止",
            )
            return
        if isinstance(node.func, ast.Call):
            factory = self.aliases.resolve(node.func.func) or self._raw_expression(
                node.func.func
            )
            canonical_factory = canonical_aliases.get(factory or "", factory)
            if canonical_factory == "builtins.type" and canonical_factory in forbidden:
                self._add(
                    node,
                    condition=5,
                    code="TB007",
                    symbol="builtins.type(...)(...)",
                    message="type(context) による TenantContext 複製迂回は禁止",
                )
                return
        rebound_bare_name = globally_rebound_callable
        callable_value = (
            _UNKNOWN_FLOW_VALUE
            if rebound_bare_name
            else self.flow.callable_value(node)
        )
        known_callable = callable_value.symbol
        allowed_modules = (
            self.contract.tenant_context.allowed_test_modules
            | self.contract.tenant_context.allowed_product_modules
        )
        if (
            self.contract.tenant_context.constructor_symbol
            in callable_value.origins
        ):
            if self.module in allowed_modules:
                return
            self._add(
                node,
                condition=5,
                code="TB007",
                symbol=self.contract.tenant_context.constructor_symbol,
                message=(
                    "可能な callable 起源に TenantContext が含まれるため拒否"
                ),
            )
            return
        if (
            known_callable == self.contract.tenant_context.constructor_symbol
            and self.module in allowed_modules
        ):
            return
        constructor_name = (
            self.contract.tenant_context.constructor_symbol.rsplit(".", 1)[-1]
        )
        callable_name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else None
        )
        if callable_name == constructor_name:
            self._add(
                node,
                condition=5,
                code="TB007",
                symbol=callable_name,
                message=(
                    "TenantContext と同名の callable は由来種別に関係なく拒否"
                ),
            )
            return
        reexport = (
            None
            if rebound_bare_name
            else self._reexport_resolution(node.func, resolved)
        )
        if known_callable is None:
            if isinstance(node.func, ast.Attribute):
                self._reject_reexport_call(
                    node,
                    resolved=resolved,
                    callable_name=callable_name,
                    resolution=reexport,
                    allowed_modules=allowed_modules,
                )
                return
            # 起源集合を分岐・コンテナ・閉包まで保持し、TenantContext 起源が無く
            # 未解決でもない外部入力だけを保証外 callable として免除する。
            if (
                lexically_bound_callable
                and callable_value.external_input
                and not callable_value.unresolved
            ):
                return
            alias_resolved = self.aliases.resolve(node.func)
            # resolve() は未知の裸名も生テキストで返す。known_symbols を読む
            # resolve_known() でも解決できた Name だけを既知 callable とする。
            known_alias_callable: str | None = None
            if (
                isinstance(node.func, ast.Name)
                and alias_resolved is not None
                and not rebound_bare_name
            ):
                known_alias_callable = self.aliases.resolve_known(node.func)
            if (
                known_alias_callable is not None
                and self.aliases.canonical(known_alias_callable)
                != self.contract.tenant_context.constructor_symbol
            ):
                self._reject_reexport_call(
                    node,
                    resolved=resolved,
                    callable_name=callable_name,
                    resolution=reexport,
                    allowed_modules=allowed_modules,
                )
                return
            self._add(
                node,
                condition=5,
                code="TB007",
                symbol=resolved or "<unresolved-callable>",
                message=(
                    "由来を完全修飾名へ解決できない callable は "
                    "TenantContext の生成経路として拒否"
                ),
            )
            return
        if self._reject_reexport_call(
            node,
            resolved=resolved,
            callable_name=callable_name,
            resolution=reexport,
            allowed_modules=allowed_modules,
        ):
            return
        if known_callable != self.contract.tenant_context.constructor_symbol:
            return
        if self.module in allowed_modules:
            return
        self._add(
            node,
            condition=5,
            code="TB007",
            symbol=known_callable,
            message="TenantContext は生成箇所 allowlist 内のモジュールだけで構築できる",
        )

    def _check_integrity_reference(self, text: str, node: ast.AST) -> None:
        """発行証跡の秘密・導出関数を許可シンボル外へ公開しない。"""
        if not self._is_changed(node):
            return
        protected = (
            (
                self.contract.tenant_context.integrity_secret_symbol,
                self.contract.tenant_context.integrity_secret_allowed_symbols,
                "TenantContext 発行証跡の秘密は許可シンボル外から参照できない",
            ),
            (
                self.contract.tenant_context.integrity_proof_factory_symbol,
                self.contract.tenant_context.integrity_proof_factory_allowed_symbols,
                "TenantContext 発行証跡の導出関数は許可シンボル外から参照できない",
            ),
        )
        for symbol, allowed_symbols, message in protected:
            if text not in {symbol, symbol.rsplit(".", 1)[1]}:
                continue
            if self._current_symbol() in allowed_symbols:
                return
            self._add(
                node,
                condition=5,
                code="TB007",
                symbol=symbol,
                message=message,
            )
            return

    def _check_dynamic_call(self, node: ast.Call) -> None:
        """動的名前解決による DB API・保護型への到達を保守的に拒否する。"""
        if not self._is_changed(node):
            return
        resolved = self.aliases.resolve(node.func) or self._raw_expression(node.func)
        if resolved in {
            "eval",
            "builtins.eval",
            "exec",
            "builtins.exec",
            "__import__",
            "builtins.__import__",
            "importlib.import_module",
        }:
            self._add(
                node,
                condition=5,
                code="TB005",
                symbol=resolved,
                message="動的評価・import による保護対象 API への到達は禁止",
            )
            return
        if resolved not in {"getattr", "builtins.getattr"} or len(node.args) < 2:
            return
        receiver = self.aliases.resolve(node.args[0]) or self._raw_expression(
            node.args[0]
        )
        method = _constant_string(node.args[1])
        secret = self.contract.tenant_context.integrity_secret_symbol
        proof_factory = self.contract.tenant_context.integrity_proof_factory_symbol
        for symbol in (secret, proof_factory):
            if method == symbol.rsplit(".", 1)[1]:
                self._add(
                    node,
                    condition=5,
                    code="TB007",
                    symbol=symbol,
                    message="getattr による TenantContext 発行証跡内部への参照は禁止",
                )
        provenance = self.flow.argument_provenance(node, 0)
        member_owners = {
            api.symbol.rsplit(".", 1)[0]
            for api in self.contract.apis
            if api.kind == "member"
        }
        receiver_is_protected = receiver in member_owners or any(
            receiver is not None
            and receiver.rsplit(".", 1)[-1] in api.receivers
            for api in self.contract.apis
            if api.kind == "member"
        )
        if method is None:
            if receiver_is_protected:
                self._add(
                    node,
                    condition=5,
                    code="TB005",
                    symbol="getattr(<database-receiver>, <dynamic>)",
                    message="DB receiver の動的属性解決は禁止",
                )
            return
        api = self._matching_dynamic_member(node.args[0], method)
        method_is_dangerous = method in self.contract.conservative_member_names
        if api is not None or (
            method_is_dangerous and provenance != "non_db"
        ):
            self._add(
                node,
                condition=5,
                code="TB005",
                symbol=(
                    api.symbol
                    if api is not None
                    else f"<unknown-database-receiver>.{method}"
                ),
                message="getattr による危険 DB API 名の動的解決は禁止",
            )
        constructor = self.contract.tenant_context.constructor_symbol
        if receiver == constructor and method in {"__new__", "__init__"}:
            self._add(
                node,
                condition=5,
                code="TB007",
                symbol=f"getattr({constructor}, {method})",
                message="TenantContext の動的構築は生成箇所 allowlist を迂回する",
            )

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        """import のモジュール名と別名を禁止語彙へ照合する。"""
        for alias in node.names:
            self._check_identifier(alias.name, node)
            if alias.asname is not None:
                self._check_identifier(alias.asname, node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        """from import のモジュール名・シンボル名・別名を照合する。"""
        provider_module = self.contract.cache_invalidation.provider_module
        imported_module = _absolute_import_from_module(
            current_module=self.module,
            current_is_package=self.module_is_package,
            imported_module=node.module,
            level=node.level,
        )
        if imported_module is not None:
            self._check_identifier(
                imported_module,
                node,
                allow_condition4=imported_module == provider_module,
            )
        for alias in node.names:
            imported_symbol = (
                f"{imported_module}.{alias.name}"
                if imported_module is not None
                else alias.name
            )
            self._check_integrity_reference(imported_symbol, node)
            import_is_allowed = (
                imported_symbol
                in self.contract.cache_invalidation.public_symbols
            )
            if (
                imported_module == provider_module
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
                condition2_symbol=imported_symbol,
            )
            if alias.asname is not None:
                self._check_identifier(alias.asname, node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        """非 TenantContext クラスの object.__new__ 戻り値だけを局所追跡する。"""
        if isinstance(node.value, ast.Call):
            resolved = self.aliases.resolve(node.value.func) or self._raw_expression(
                node.value.func
            )
            if (
                resolved in {"object.__new__", "builtins.object.__new__"}
                and node.value.args
                and isinstance(node.value.args[0], ast.Name)
                and node.value.args[0].id == "cls"
                and self.class_stack
                and ".".join([self.module, *self.class_stack])
                != self.contract.tenant_context.constructor_symbol
                and self.safe_non_context_objects
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.safe_non_context_objects[-1].add(target.id)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        """クラス内のメソッド完全修飾名を構築する。"""
        class_symbol = ".".join(
            [self.module, *self.class_stack, node.name]
        ).strip(".")
        self._check_identifier(
            node.name,
            node,
            condition2_symbol=class_symbol,
        )
        allowed_modules = (
            self.contract.tenant_context.allowed_test_modules
            | self.contract.tenant_context.allowed_product_modules
        )
        for base in node.bases:
            flow_base = self.flow.class_base_value(base)
            resolved = self.aliases.resolve(base) or self._raw_expression(base)
            reexport = self._reexport_resolution(base, resolved)
            if (
                self._is_changed(base)
                and self.contract.tenant_context.constructor_symbol
                in flow_base.origins
                and self.module not in allowed_modules
            ):
                self._add(
                    base,
                    condition=5,
                    code="TB007",
                    symbol=self.contract.tenant_context.constructor_symbol,
                    message=(
                        "可能なクラス基底起源に TenantContext が含まれるため拒否"
                    ),
                )
                continue
            if self._is_changed(base) and flow_base.unresolved:
                self._add(
                    base,
                    condition=5,
                    code="TB007",
                    symbol=resolved or "<unresolved-class-base>",
                    message=(
                        "起源を解決できない class base は "
                        "TenantContext 継承迂回として拒否"
                    ),
                )
                continue
            if (
                self._is_changed(base)
                and reexport is not None
                and (
                    reexport.unresolved
                    or self.contract.tenant_context.constructor_symbol
                    in reexport.origins
                )
                and (
                    reexport.unresolved
                    or self.module not in allowed_modules
                )
            ):
                self._add(
                    base,
                    condition=5,
                    code="TB007",
                    symbol=resolved or "<unresolved-reexport>",
                    message=(
                        "再輸出経由または起源不明の TenantContext 継承は禁止"
                    ),
                )
                continue
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
        for keyword in node.keywords:
            self.visit(keyword)
        for type_param in node.type_params:
            self.visit(type_param)
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
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)
        arguments = (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
            node.args.vararg,
            node.args.kwarg,
        )
        for argument in arguments:
            if argument is not None:
                self.visit(argument)
        if node.returns is not None:
            self.visit(node.returns)
        for type_param in node.type_params:
            self.visit(type_param)
        self.function_stack.append((symbol, signature))
        self.safe_non_context_objects.append(set())
        for statement in node.body:
            self.visit(statement)
        self.safe_non_context_objects.pop()
        self.function_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """同期関数のシンボル・署名・本体を検査する。"""
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        """非同期関数のシンボル・署名・本体を検査する。"""
        self._visit_function(node)

    def visit_arg(self, node: ast.arg) -> None:
        """引数名を条件 2 の構文候補として照合する。"""
        self._check_condition2_syntax(node.arg, node)
        if node.annotation is not None:
            self.visit(node.annotation)

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        """名前参照を禁止語彙へ照合する。"""
        resolved = self.aliases.resolve(node) or node.id
        if isinstance(node.ctx, ast.Load):
            self._check_integrity_reference(resolved, node)
        self._check_identifier(
            resolved,
            node,
            allow_condition4=self._condition4_reference_allowed(resolved),
            condition2_candidate=self._condition2_candidate_for_name(node),
            condition2_symbol=self._condition2_symbol_for_name(node, resolved),
        )

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        """属性参照を禁止語彙へ照合する。"""
        resolved = self.aliases.resolve(node) or self._raw_expression(node) or node.attr
        self._check_integrity_reference(resolved, node)
        self._check_identifier(
            resolved,
            node,
            allow_condition4=self._condition4_reference_allowed(resolved),
            condition2_candidate=node.attr,
            condition2_symbol=self._condition2_symbol_for_attribute(
                node,
                resolved,
            ),
        )
        self.generic_visit(node)

    def visit_keyword(self, node: ast.keyword) -> None:
        """呼び出し・class keyword 名を条件 2 の構文候補として照合する。"""
        if node.arg is not None:
            self._check_condition2_syntax(node.arg, node)
        self.visit(node.value)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:  # noqa: N802
        """match capture 名を条件 2 の構文候補として照合する。"""
        if node.name is not None:
            self._check_condition2_syntax(node.name, node)
        if node.pattern is not None:
            self.visit(node.pattern)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:  # noqa: N802
        """star capture 名を条件 2 の構文候補として照合する。"""
        if node.name is not None:
            self._check_condition2_syntax(node.name, node)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:  # noqa: N802
        """mapping rest capture 名を条件 2 の構文候補として照合する。"""
        if node.rest is not None:
            self._check_condition2_syntax(node.rest, node)
        self.generic_visit(node)

    def visit_MatchClass(self, node: ast.MatchClass) -> None:  # noqa: N802
        """class pattern の keyword 名を条件 2 の構文候補として照合する。"""
        for name in node.kwd_attrs:
            self._check_condition2_syntax(name, node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        """呼び出しを DB API・禁止シンボル・生成箇所へ照合する。"""
        self.checked_call_ids.add(id(node))
        resolved = self.aliases.resolve(node.func) or self._raw_expression(node.func)
        condition4_call_allowed = (
            resolved
            in self.contract.cache_invalidation.allowed_call_symbols
            or self._pool_connection_invalidation_allowed(resolved)
        )
        if resolved is not None:
            condition2_name = (
                node.func if isinstance(node.func, ast.Name) else None
            )
            self._check_identifier(
                resolved,
                node,
                allow_condition4=condition4_call_allowed,
                condition2_candidate=(
                    condition2_name.id
                    if condition2_name is not None
                    else None
                ),
                condition2_symbol=(
                    self._condition2_symbol_for_name(
                        condition2_name,
                        resolved,
                    )
                    if condition2_name is not None
                    else None
                ),
            )
        self._check_db_call(node)
        self._check_set_config_call(node)
        self._check_tenant_context_call(node)
        self._check_dynamic_call(node)
        if not condition4_call_allowed:
            self.visit(node.func)
        for argument in node.args:
            self.visit(argument)
        for keyword in node.keywords:
            self.visit(keyword)

    def visit_BinOp(self, node: ast.BinOp) -> None:  # noqa: N802
        """保護対象名を組み立てる文字列連結を拒否する。"""
        folded = _constant_string(node)
        if folded is not None and self._is_changed(node):
            normalized = _normalize_identifier(folded)
            protected_fragments = (
                "execute",
                "exec_driver_sql",
                "psycopg",
                "send_query",
                "tenant_context",
            )
            if any(fragment in normalized for fragment in protected_fragments):
                self._add(
                    node,
                    condition=5,
                    code="TB005",
                    symbol=folded,
                    message="保護対象 API・型名の文字列連結は禁止",
                )
        self.generic_visit(node)

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
    reexport_map: Mapping[
        str,
        Mapping[str, _ExportResolution],
    ] | None = None,
) -> list[Violation]:
    """1 つの Python ソースを検査する。

    Args:
        source: Python ソース。
        path: source root 相対パス。
        contract: 読み合わせ済み検査契約。
        changed_lines: 検査する新側行番号。``None`` は全行。
        reject_all_db_calls: 正例の実効性を測る全拒否変異を有効にするか。
        reexport_map: 同じ snapshot から作ったモジュール別再輸出写像。
            ``None`` なら再輸出規則 (v) は適用しない。

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
        source=source,
        changed_lines=changed_lines,
        contract=contract,
        reject_all_db_calls=reject_all_db_calls,
        reexport_map=reexport_map,
    )
    scanner.visit(tree)
    scanner._validate_call_coverage(tree)
    return sorted(scanner.violations)


def scan_source_change(
    baseline_source: str | None,
    head_source: str,
    *,
    path: str,
    contract: Contract,
    changed_lines: Set[int],
    baseline_reexport_map: Mapping[
        str,
        Mapping[str, _ExportResolution],
    ] | None = None,
    head_reexport_map: Mapping[
        str,
        Mapping[str, _ExportResolution],
    ] | None = None,
) -> list[Violation]:
    """差分があるファイルを全行解析し、新たに生じた違反だけを返す。

    由来を決める注釈・代入だけが変更された場合でも、その依存先である
    据え置きの呼び出しを再判定する。基準版の違反と相殺できるのは、
    同じ所属シンボルにあり、旧新の未変更行が対応する同一 AST 範囲だけとする。

    Args:
        baseline_source: merge-base 側のソース。新規ファイルは ``None``。
        head_source: 新側のソース。
        path: source root 相対パス。
        contract: 読み合わせ済み検査契約。
        changed_lines: ``git diff -U0`` から得た新側行番号。純粋削除では空。
        baseline_reexport_map: merge-base snapshot だけから作った再輸出写像。
            ``None`` なら baseline 側へ再輸出規則 (v) は適用しない。
        head_reexport_map: HEAD snapshot だけから作った再輸出写像。
            ``None`` なら HEAD 側へ再輸出規則 (v) は適用しない。

    Returns:
        基準版にはなく、新側で増えた違反。
    """
    _ = changed_lines
    baseline_violations = (
        []
        if baseline_source is None
        else scan_source(
            baseline_source,
            path=path,
            contract=contract,
            reexport_map=baseline_reexport_map,
        )
    )
    head_violations = scan_source(
        head_source,
        path=path,
        contract=contract,
        reexport_map=head_reexport_map,
    )

    def identity(
        violation: Violation,
        *,
        line: int,
        end_line: int,
    ) -> tuple[str, int, int, int, str, str, str]:
        """所属シンボル・対応行・違反内容を含む識別値を返す。"""
        return (
            violation.scope,
            line,
            end_line,
            violation.condition,
            violation.code,
            violation.symbol,
            violation.message,
        )

    baseline_lines = baseline_source.splitlines() if baseline_source is not None else []
    head_lines = head_source.splitlines()
    head_to_baseline: dict[int, int] = {}
    matcher = difflib.SequenceMatcher(
        None,
        baseline_lines,
        head_lines,
        autojunk=False,
    )
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            head_to_baseline[block.b + offset + 1] = block.a + offset + 1

    remaining = Counter(
        identity(
            item,
            line=item.line,
            end_line=item.end_line or item.line,
        )
        for item in baseline_violations
    )
    introduced: list[Violation] = []
    for violation in head_violations:
        head_end = violation.end_line or violation.line
        mapped_span = [
            head_to_baseline.get(line)
            for line in range(violation.line, head_end + 1)
        ]
        if any(line is None for line in mapped_span):
            introduced.append(violation)
            continue
        baseline_span = [int(line) for line in mapped_span if line is not None]
        if any(
            next_line != previous_line + 1
            for previous_line, next_line in zip(
                baseline_span,
                baseline_span[1:],
                strict=False,
            )
        ):
            introduced.append(violation)
            continue
        key = identity(
            violation,
            line=baseline_span[0],
            end_line=baseline_span[-1],
        )
        if remaining[key] > 0:
            remaining[key] -= 1
        else:
            introduced.append(violation)
    return sorted(introduced)


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


def changed_files_from_diff(diff: str) -> frozenset[str]:
    """``git diff`` から HEAD に残る変更ファイル集合を導出する。

    新側行番号とは独立に、純粋削除で行集合が空のファイルと rename 先も
    検査対象へ残す。ファイル自体の削除は HEAD に存在しないので除外する。

    Args:
        diff: unified diff。

    Returns:
        ``backend/src`` 相対の HEAD 側変更ファイル集合。
    """

    def relative_path(raw_path: str) -> str | None:
        if raw_path == "/dev/null":
            return None
        try:
            parsed = shlex.split(raw_path)
        except ValueError as error:
            raise ContractError(f"差分のパスを解釈できない: {raw_path}") from error
        if len(parsed) != 1:
            raise ContractError(f"差分のパス形式が不正: {raw_path}")
        path = parsed[0].removeprefix("b/")
        prefix = "backend/src/"
        return path.removeprefix(prefix) if path.startswith(prefix) else None

    changed: set[str] = set()
    for line in diff.splitlines():
        raw_path: str | None = None
        if line.startswith("+++ "):
            raw_path = line[4:]
        elif line.startswith("rename to "):
            raw_path = line.removeprefix("rename to ")
        elif line.startswith("copy to "):
            raw_path = line.removeprefix("copy to ")
        if raw_path is None:
            continue
        relative = relative_path(raw_path)
        if relative is not None:
            changed.add(relative)
    return frozenset(changed)


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


def _git_json_asset(
    repository_root: Path,
    revision: str,
    path: Path,
) -> dict[str, Any] | None:
    """指定 revision に存在する JSON 資産を読む。存在しなければ None を返す。"""
    object_name = f"{revision}:{path.as_posix()}"
    if not _git_regular_blob(repository_root, revision, path, required=False):
        return None
    source = _run_git(repository_root, ["show", object_name])
    try:
        value = json.loads(source)
    except json.JSONDecodeError as error:
        raise ContractError(f"比較元の契約資産が JSON でない: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ContractError(f"比較元の契約資産ルートがオブジェクトでない: {path}")
    return value


def _git_regular_blob(
    repository_root: Path,
    revision: str,
    path: Path,
    *,
    required: bool = True,
) -> bool:
    """Git tree上のパスが通常blobであることを検査する。"""
    output = _run_git(
        repository_root,
        ["--literal-pathspecs", "ls-tree", revision, "--", path.as_posix()],
    ).strip()
    if not output:
        if required:
            raise ContractError(f"Git treeに通常ファイルが無い: {revision}:{path}")
        return False
    metadata, separator, actual_path = output.partition("\t")
    fields = metadata.split()
    if (
        separator != "\t"
        or actual_path != path.as_posix()
        or len(fields) != 3
        or fields[0] not in {"100644", "100755"}
        or fields[1] != "blob"
    ):
        raise ContractError(f"Git treeの通常blobが必要: {revision}:{path}")
    return True


def _asset_external_files(asset: Mapping[str, object], location: str) -> tuple[str, ...]:
    """資産宣言から外部凍結対象を取得する。"""
    control = _object(asset.get("baseline_control"), f"{location}.baseline_control")
    identity = _object(control.get("identity"), f"{location}.identity")
    projection = _object(
        identity.get("frozen_projection"),
        f"{location}.identity.frozen_projection",
    )
    external_files = _string_array(
        projection.get("external_files"),
        f"{location}.identity.frozen_projection.external_files",
    )
    try:
        return tuple(
            frozen_history.validate_repository_relative_path(
                path,
                f"{location}.identity.frozen_projection.external_files[]",
            ).as_posix()
            for path in external_files
        )
    except frozen_history.ContractError as error:
        raise ContractError(str(error)) from error


def _materialize_git_snapshots(
    repository_root: Path,
    revision: str,
    destination: Path,
) -> None:
    """比較元 revision の content-addressed snapshot 群を一時領域へ復元する。"""
    snapshot_directory = "contracts/tenant_boundary/history-snapshots"
    entries = _run_git(
        repository_root,
        ["ls-tree", "-r", revision, "--", snapshot_directory],
    )
    destination.mkdir(parents=True, exist_ok=True)
    for entry in entries.splitlines():
        metadata, separator, name = entry.partition("\t")
        fields = metadata.split()
        if (
            separator != "\t"
            or len(fields) != 3
            or fields[0] not in {"100644", "100755"}
            or fields[1] != "blob"
        ):
            raise ContractError(f"比較元snapshotは通常blobが必要: {name}")
        relative_name = Path(name).relative_to(snapshot_directory)
        if len(relative_name.parts) != 1:
            raise ContractError("history-snapshots は直下の通常ファイルだけを許可する")
        content = _run_git(repository_root, ["show", f"{revision}:{name}"])
        (destination / relative_name).write_bytes(content.encode("utf-8"))


def _validate_git_tree_directory_regular_blobs(
    repository_root: Path,
    revision: str,
    directory: str,
) -> None:
    """Git tree内の指定ディレクトリを通常blobだけに限定する。"""
    entries = _run_git(
        repository_root,
        ["ls-tree", "-r", revision, "--", directory],
    )
    for entry in entries.splitlines():
        metadata, separator, name = entry.partition("\t")
        fields = metadata.split()
        if (
            separator != "\t"
            or len(fields) != 3
            or fields[0] not in {"100644", "100755"}
            or fields[1] != "blob"
        ):
            raise ContractError(f"Git treeの通常blobが必要: {revision}:{name}")


def _git_tenant_boundary_assets(
    repository_root: Path,
    revision: str,
) -> tuple[Path, ...]:
    """比較元revisionのtenant_boundary JSON資産を独立列挙する。"""
    asset_root = Path("contracts/tenant_boundary")
    entries = _run_git(
        repository_root,
        ["ls-tree", "-r", revision, "--", asset_root.as_posix()],
    )
    assets: list[Path] = []
    for entry in entries.splitlines():
        metadata, separator, raw_name = entry.partition("\t")
        path = Path(raw_name)
        if path.parent != asset_root or path.suffix != ".json":
            continue
        fields = metadata.split()
        if (
            separator != "\t"
            or len(fields) != 3
            or fields[0] not in {"100644", "100755"}
            or fields[1] != "blob"
        ):
            raise ContractError(f"比較元の契約資産は通常blobが必要: {path}")
        assets.append(path)
    return tuple(sorted(assets))


def _head_tenant_boundary_assets(repository_root: Path) -> tuple[Path, ...]:
    """HEAD作業ツリーのtenant_boundary JSON資産を実ファイルから列挙する。"""
    try:
        asset_root = frozen_history.validate_repository_directory(
            repository_root,
            "contracts/tenant_boundary",
            "HEAD.contracts/tenant_boundary",
        )
        assets: list[Path] = []
        for path in asset_root.iterdir():
            if path.suffix != ".json":
                continue
            relative_path = path.relative_to(repository_root)
            frozen_history.read_repository_file(
                repository_root,
                relative_path.as_posix(),
                f"HEAD.{relative_path.as_posix()}",
            )
            _git_regular_blob(
                repository_root,
                "HEAD",
                relative_path,
                required=False,
            )
            assets.append(relative_path)
        return tuple(sorted(assets))
    except (OSError, frozen_history.ContractError) as error:
        raise ContractError(f"HEAD の契約資産集合を列挙できない: {error}") from error


def _validate_repository_histories(
    repository_root: Path,
    comparison_revision: str,
    evaluation_context: frozen_history.EvaluationContext,
) -> None:
    """比較元と HEAD の 7 資産を単一 authority 履歴として照合する。"""
    previous_assets: dict[str, object] = {}
    current_assets: dict[str, object] = {}
    previous_paths = _git_tenant_boundary_assets(
        repository_root,
        comparison_revision,
    )
    current_paths = _head_tenant_boundary_assets(repository_root)
    for path in previous_paths:
        previous_asset = _git_json_asset(repository_root, comparison_revision, path)
        if previous_asset is None:
            raise ContractError(f"比較元の契約資産を取得できない: {path}")
        previous_assets[path.as_posix()] = previous_asset
    for path in current_paths:
        current_asset, _ = _read_json(repository_root / path)
        _validate_baseline_control(current_asset, path.as_posix())
        current_assets[path.as_posix()] = current_asset

    previous_external_paths = {
        external_path
        for asset_name, asset in previous_assets.items()
        for external_path in _asset_external_files(
            _object(asset, asset_name),
            asset_name,
        )
    }
    current_external_paths = {
        external_path
        for asset_name, asset in current_assets.items()
        for external_path in _asset_external_files(
            _object(asset, asset_name),
            asset_name,
        )
    }
    previous_implementations: dict[str, bytes] = {}
    for path in sorted(previous_external_paths):
        _git_regular_blob(
            repository_root,
            comparison_revision,
            Path(path),
        )
        previous_implementations[path] = _run_git(
            repository_root,
            ["show", f"{comparison_revision}:{path}"],
        ).encode("utf-8")
    try:
        current_implementations = frozen_history._read_external_implementations(
            repository_root,
            tuple(sorted(current_external_paths)),
            "HEAD.external_files",
        )
        for path in sorted(current_external_paths):
            _git_regular_blob(
                repository_root,
                "HEAD",
                Path(path),
                required=False,
            )
    except (OSError, frozen_history.ContractError) as error:
        raise ContractError(f"外部凍結対象を解決できない: {error}") from error

    snapshot_directory = "contracts/tenant_boundary/history-snapshots"
    try:
        head_snapshot_root = frozen_history.validate_repository_directory(
            repository_root,
            snapshot_directory,
            "HEAD.history-snapshots",
        )
    except frozen_history.ContractError as error:
        raise ContractError(str(error)) from error
    _validate_git_tree_directory_regular_blobs(
        repository_root,
        "HEAD",
        snapshot_directory,
    )

    parent_line = _run_git(
        repository_root,
        ["rev-list", "--parents", "-n", "1", "HEAD"],
    ).split()
    head_parents = tuple(parent_line[1:])
    with tempfile.TemporaryDirectory(prefix="tenant-boundary-base-snapshots-") as raw:
        base_snapshot_root = Path(raw)
        _materialize_git_snapshots(
            repository_root,
            comparison_revision,
            base_snapshot_root,
        )
        try:
            frozen_history.validate_repository_histories(
                previous_assets,
                current_assets,
                base_implementations=previous_implementations,
                head_implementations=current_implementations,
                base_snapshot_root=base_snapshot_root,
                head_snapshot_root=head_snapshot_root,
                head_parents=head_parents,
                evaluation_context=evaluation_context,
            )
        except frozen_history.ContractError as error:
            raise ContractError(str(error)) from error

    for path, raw_asset in current_assets.items():
        current_asset = _object(raw_asset, path)
        history = _validate_baseline_control(current_asset, path)
        for entry in history:
            if "source_commit" not in entry:
                continue
            source_commit = _string(entry["source_commit"], "history.source_commit")
            if source_commit == PENDING_SOURCE_COMMIT:
                continue
            _run_git(
                repository_root,
                ["rev-parse", "--verify", f"{source_commit}^{{commit}}"],
            )


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
    inspection_population: Mapping[str, frozenset[int]],
    contract: Contract,
    *,
    baseline_sources: Mapping[str, str] | None = None,
    head_sources: Mapping[str, str] | None = None,
) -> list[Violation]:
    """変更ファイルを全行解析し、基準版から増えた違反を検出する。"""
    if head_sources is None:
        head_sources = _git_snapshot(repository_root, "HEAD")
    head_reexport_map = _build_reexport_map(head_sources)
    baseline_reexport_map = (
        None
        if baseline_sources is None
        else _build_reexport_map(baseline_sources)
    )
    violations: list[Violation] = []
    for relative, lines in sorted(inspection_population.items()):
        path = repository_root / "backend/src" / relative
        if path.suffix not in {".py", ".pyi"}:
            violations.append(
                Violation(
                    path=f"backend/src/{relative}",
                    line=min(lines, default=0),
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
        if baseline_sources is None:
            violations.extend(
                scan_source(
                    source,
                    path=relative,
                    changed_lines=lines,
                    contract=contract,
                    reexport_map=head_reexport_map,
                )
            )
        else:
            violations.extend(
                scan_source_change(
                    baseline_sources.get(relative),
                    source,
                    path=relative,
                    changed_lines=lines,
                    contract=contract,
                    baseline_reexport_map=baseline_reexport_map,
                    head_reexport_map=head_reexport_map,
                )
            )
    return sorted(violations)


def _has_changed_lines(
    changed_lines: Mapping[str, frozenset[int]],
) -> bool:
    """差分から導出した新側行が 1 行以上あるか判定する。"""
    return any(lines for lines in changed_lines.values())


def _contract_symbol_population(
    head_sources: Mapping[str, str],
    contract: Contract,
) -> dict[str, frozenset[int]]:
    """HEAD に実在する許可シンボルのファイルを検査母集団へ変換する。

    三点差分が統合後に空になっても、製品の強制点そのものを再検査して
    fail-open を避ける。製品シンボル導入前は空集合を返す。
    """
    population: dict[str, frozenset[int]] = {}
    for path, source in sorted(head_sources.items()):
        definitions, _ = _definitions({path: source}, contract)
        if not definitions:
            continue
        population[path] = frozenset(range(1, len(source.splitlines()) + 1))
    return population


def _inspection_population(
    changed_lines: Mapping[str, frozenset[int]],
    head_sources: Mapping[str, str],
    *,
    contract: Contract,
    changed_files: Set[str] | None = None,
) -> dict[str, frozenset[int]]:
    """PR 新側行または統合済み強制点から非空の検査母集団を導出する。

    Args:
        changed_lines: 三点差分から導出した新側行。
        head_sources: HEAD の ``backend/src`` Python ソース。
        contract: 読み合わせ済み検査契約。
        changed_files: HEAD に残る変更ファイル。``None`` は行集合のキーを使う。

    Returns:
        実際に AST 検査へ渡すファイル別行番号。
    """
    files = frozenset(changed_lines) if changed_files is None else frozenset(changed_files)
    if files:
        return {
            path: changed_lines.get(path, frozenset())
            for path in sorted(files)
        }
    return _contract_symbol_population(head_sources, contract)


def _application_population_violations(
    changed_lines: Mapping[str, frozenset[int]],
    baseline_sources: Mapping[str, str],
    head_sources: Mapping[str, str],
    *,
    contract: Contract,
    changed_files: Set[str] | None = None,
) -> list[Violation]:
    """製品強制点を導入した PR の検査母集団空洞化を拒否する。

    Args:
        changed_lines: 三点差分から導出した新側行。
        baseline_sources: merge-base の ``backend/src`` スナップショット。
        head_sources: HEAD の ``backend/src`` スナップショット。
        contract: 読み合わせ済み検査契約。
        changed_files: HEAD に残る変更ファイル。

    Returns:
        導入シンボルがあるのに新側行が 0 件なら ``TB008``、それ以外は空。
    """
    baseline_definitions, _ = _definitions(baseline_sources, contract)
    head_definitions, _ = _definitions(head_sources, contract)
    introduced_symbols = sorted(
        set(head_definitions) - set(baseline_definitions)
    )
    has_changed_files = (
        _has_changed_lines(changed_lines)
        if changed_files is None
        else bool(changed_files)
    )
    if not introduced_symbols or has_changed_files:
        return []
    return [
        Violation(
            path="backend/src",
            line=0,
            condition=0,
            code="TB008",
            symbol=",".join(introduced_symbols),
            message=(
                "製品の許可シンボルを導入した PR なのに、"
                "三点差分の検査母集団が空"
            ),
        )
    ]


def _resolve_repository_evaluation(
    repository_root: Path,
    base_ref: str | None,
    evaluation_context: frozen_history.EvaluationContext | None = None,
) -> tuple[frozen_history.EvaluationContext, str]:
    """明示注入または環境強制で評価コンテキストと比較元を確定する。

    Args:
        repository_root: 検査対象のリポジトリルート。
        base_ref: 呼び出し元が指定した比較元。
        evaluation_context: テスト等が明示注入する評価コンテキスト。
            ``None`` の本番経路は環境変数から強制する。

    Returns:
        検査対象へ適用する評価コンテキストと比較元 revision。

    Raises:
        ContractError: PR event または明示比較元が不正な場合。
    """
    if evaluation_context is None:
        try:
            context = frozen_history.resolve_evaluation_context()
        except frozen_history.ContractError as error:
            raise ContractError(str(error)) from error
    else:
        context = evaluation_context
    if context.mode is frozen_history.EvaluationMode.INVARIANT:
        return context, base_ref or DEFAULT_BASE_REF

    pull_request = context.pull_request
    if pull_request is None:
        raise ContractError("PR 受理モードの event 情報が無い")
    if base_ref is not None:
        explicit_base_sha = _run_git(
            repository_root,
            ["rev-parse", "--verify", f"{base_ref}^{{commit}}"],
        ).strip()
        if explicit_base_sha != pull_request.base_sha:
            raise ContractError(
                "PR workspace の明示 base_ref が event の base.sha と不一致"
            )
    return context, pull_request.base_sha


def check_repository(
    repository_root: Path,
    base_ref: str | None = None,
    *,
    evaluation_context: frozen_history.EvaluationContext | None = None,
) -> list[Violation]:
    """リポジトリの PR 差分と基底シンボル継続性を検査する。

    Args:
        repository_root: リポジトリルート。
        base_ref: PR の比較元。``None`` は検査器の凍結された既定値を使う。
        evaluation_context: テスト等が明示注入する評価コンテキスト。
            ``None`` の本番経路は環境変数から強制する。

    Returns:
        検出した違反。
    """
    contract = load_contract(repository_root)
    evaluation_context, effective_base_ref = _resolve_repository_evaluation(
        repository_root,
        base_ref,
        evaluation_context,
    )
    diff_arguments = list(contract.diff_command[1:])
    diff_arguments[2] = f"{effective_base_ref}...HEAD"
    diff = _run_git(repository_root, diff_arguments)
    changed_lines = changed_lines_from_diff(diff)
    changed_files = changed_files_from_diff(diff)
    merge_base = _run_git(
        repository_root,
        ["merge-base", effective_base_ref, "HEAD"],
    ).strip()
    _validate_repository_histories(
        repository_root,
        effective_base_ref,
        evaluation_context,
    )
    baseline_sources = _git_snapshot(repository_root, merge_base)
    head_sources = _git_snapshot(repository_root, "HEAD")
    population = _inspection_population(
        changed_lines,
        head_sources,
        contract=contract,
        changed_files=changed_files,
    )
    violations = _changed_source_violations(
        repository_root,
        population,
        contract,
        baseline_sources=(baseline_sources if changed_files else None),
        head_sources=head_sources,
    )
    violations.extend(
        _application_population_violations(
            changed_lines,
            baseline_sources,
            head_sources,
            contract=contract,
            changed_files=changed_files,
        )
    )
    violations.extend(
        continuity_violations(
            baseline_sources,
            head_sources,
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
    parser.add_argument("--base-ref")
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
