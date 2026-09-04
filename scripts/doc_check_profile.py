"""文書検査プロファイルとレジストリを読み込む共通機構。"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CHECK_IDS_ALL: tuple[str, ...] = (
    "manifest-consistency",
    "element-coverage",
    "enum-propagation",
    "condition-key",
    "route-matrix",
    "scope-declaration",
    "order-use",
    "citation-format",
    "noncanonical-reference",
    "link-target",
    "emphasis",
    "draft-metadata",
    "forbidden-structure",
    "cross-consistency",
    "collection-consistency",
    "baseline-digest",
    "unique-owner",
    "reference-class",
    "attribution",
    "ledger",
    "attribution-destination",
    "attribution-direct",
)
GATING_KEYS: tuple[str, ...] = (
    "required_checks",
    "not_applicable",
    "invariant_kinds",
    "structure_extractors",
    "collection_sets",
    "assets",
    "direct_requirements",
    "reference_policy",
)

_PROFILE_SCHEMA = "profile.schema.json"
_REGISTRY_SCHEMA = "registry.schema.json"
_INVARIANT_SCHEMA = "invariant.schema.json"
_ASSETS_SCHEMA = "assets.schema.json"
_SCHEMA_VERSION = 1
_SUPPORTED_SCHEMA_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "enum",
        "items",
        "minLength",
        "pattern",
        "minItems",
        "uniqueItems",
    }
)
_SUPPORTED_TYPES = frozenset({"object", "array", "string", "integer", "boolean"})
_INVARIANT_KINDS = frozenset(
    {
        "forbidden-element",
        "row-selector",
        "row-contains",
        "section-contains",
        "exact-set",
        "cross-reference",
        "element-lookup",
        "row-scoped-forbidden",
        "any-of",
        "required-exclusion",
        "conditional-forbidden",
        "well-formedness",
        "absent-section",
        "required-element",
        "unique-owner",
    }
)
_DECLARATION_KINDS = _INVARIANT_KINDS - {"unique-owner"}
_DECLARATION_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "forbidden-element": frozenset({"defect_id", "kind", "literals"}),
    "row-selector": frozenset(
        {"defect_id", "kind", "id", "section", "mode", "keys"}
    ),
    "row-contains": frozenset({"defect_id", "kind", "row"}),
    "section-contains": frozenset(
        {"defect_id", "kind", "sections", "as"}
    ),
    "required-element": frozenset({"defect_id", "kind", "sections"}),
    "exact-set": frozenset(
        {"defect_id", "kind", "relation", "routes"}
    ),
    "cross-reference": frozenset(
        {"defect_id", "kind", "from", "to", "extract"}
    ),
    "element-lookup": frozenset(
        {"defect_id", "kind", "relation", "prefix", "section", "row_identifier"}
    ),
    "row-scoped-forbidden": frozenset(
        {"defect_id", "kind", "row", "literals"}
    ),
    "any-of": frozenset({"defect_id", "kind", "row", "literals"}),
    "required-exclusion": frozenset({"defect_id", "kind", "terms"}),
    "conditional-forbidden": frozenset(
        {"defect_id", "kind", "row", "literal", "unless"}
    ),
    "well-formedness": frozenset({"defect_id", "kind", "scope", "rule"}),
    "absent-section": frozenset({"defect_id", "kind", "section"}),
}

ASSET_IMMUTABLE_FIELDS: tuple[str, ...] = (
    "id",
    "baseline",
    "source",
    "location",
    "detection",
    "check",
    "owner_step",
    "invariant.scope",
    "invariant.forbidden",
    "invariant.positive",
    "invariant.mapping",
)
ASSET_MUTABLE_FIELDS: tuple[str, ...] = (
    "status",
    "discovered_at",
    "closure_evidence",
)
ASSET_NAMES: frozenset[str] = frozenset(
    {
        "claims",
        "auth_catalog",
        "ddl_elements",
        "auth_ddl_map",
        "product_ddl_map",
        "waiting",
        "forbidden",
        "direct_requirements",
        "expected_ids",
        "baseline_digest",
    }
)
_ASSET_DECLARATION_FIELDS = frozenset(
    {"path", "identity", "collections", "join", "normalize"}
)
_COLLECTION_FIELDS = frozenset(
    {
        "items",
        "id",
        "namespace",
        "role",
        "refs",
        "structures",
        "fields",
        "structure",
    }
)
_STRUCTURE_FIELDS = frozenset(
    {"kind", "source", "target", "direction", "participants"}
)
_STRUCTURE_DIRECTIONS = frozenset({"source->target", "target->source", "both"})
_NEW_CHECK_INPUTS: dict[str, tuple[frozenset[str], bool, bool]] = {
    "forbidden-structure": (frozenset({"forbidden"}), True, False),
    "cross-consistency": (
        frozenset(
            {
                "waiting",
                "auth_catalog",
                "ddl_elements",
                "auth_ddl_map",
                "product_ddl_map",
                "forbidden",
            }
        ),
        True,
        False,
    ),
    "collection-consistency": (frozenset(), False, True),
    "baseline-digest": (frozenset({"baseline_digest"}), False, False),
    "unique-owner": (
        frozenset({"baseline_digest", "expected_ids"}),
        False,
        False,
    ),
    "attribution-direct": (
        frozenset({"direct_requirements", "claims"}),
        False,
        True,
    ),
}
_REQUIRED_ASSET_PINS: dict[str, frozenset[str]] = {
    "forbidden-structure": frozenset({"forbidden"}),
    "cross-consistency": frozenset(
        {"forbidden", "auth_ddl_map", "product_ddl_map"}
    ),
    "baseline-digest": frozenset({"baseline_digest"}),
    "unique-owner": frozenset({"baseline_digest", "expected_ids"}),
    "attribution-direct": frozenset({"direct_requirements"}),
}


class ProfileError(Exception):
    """プロファイル、レジストリ、関連JSONの入力不正を表す。"""


@dataclass(frozen=True)
class Profile:
    """検証済みの文書検査プロファイル。

    Attributes:
        path: プロファイル自身の絶対パス。
        name: プロファイル名。
        document: 検査対象文書の絶対パス。
        manifest: 関係マニフェストの絶対パス。
        defects: 欠陥oracleの絶対パス。
        invariants: 宣言資産の絶対パス。未指定なら ``None``。
        requirements: 要件書の絶対パス。
        universe: 要件母集合の絶対パス。
        link_base_dir: Markdownリンクの解決基準となる絶対パス。
        direct_requirements: 直接要件資産の絶対パス。未指定なら ``None``。
        required_checks: 必須検査ID集合。
        not_applicable: 適用外検査IDと理由。
        invariant_kinds: 利用を宣言した不変条件kind集合。
        defect_id_namespaces: 全欠陥と機械欠陥の名前空間集合。
        raw: digest計算に用いる検証済みJSONオブジェクト。
    """

    path: Path
    root: Path
    schema_dir: Path
    name: str
    document: Path
    manifest: Path
    defects: Path
    invariants: Path | None
    requirements: Path
    universe: Path
    link_base_dir: Path
    direct_requirements: Path | None
    required_checks: frozenset[str]
    not_applicable: dict[str, str]
    invariant_kinds: frozenset[str]
    defect_id_namespaces: dict[str, frozenset[str]]
    raw: dict[str, Any]


@dataclass(frozen=True)
class RegistryEntry:
    """検証済みレジストリの1エントリ。

    Attributes:
        name: 登録プロファイル名。
        file: プロファイルの絶対パス。
        document: 検査対象文書の絶対パス。
        must_require: レジストリが強制する検査ID集合。
        pins: ゲート宣言と資産のdigest固定値。
    """

    name: str
    file: Path
    document: Path
    must_require: frozenset[str]
    pins: dict[str, Any]


@dataclass(frozen=True)
class Registry:
    """検証済みのプロファイルレジストリ。

    Attributes:
        path: レジストリ自身の絶対パス。
        entries: 登録順を保ったエントリ列。
        schema_dir: プロファイル解決にも使うスキーマディレクトリ。
    """

    path: Path
    entries: tuple[RegistryEntry, ...]
    schema_dir: Path


@dataclass(frozen=True)
class Invariants:
    """検証済みの不変条件宣言資産。

    Attributes:
        path: 宣言資産自身の絶対パス。
        structural_required: 構造判定を必須とする機械欠陥ID集合。
        legacy_structural: 旧構造分岐で暫定評価する欠陥ID集合。
        required_declarations: 構造判定外でも宣言を必須とする欠陥ID集合。
        declarations: 欠陥IDを持つ宣言列。
        global_invariants: 欠陥IDを持たない大域宣言列。
        raw: digest計算に用いる検証済みJSONオブジェクト。
    """

    path: Path
    structural_required: frozenset[str]
    legacy_structural: frozenset[str]
    required_declarations: frozenset[str]
    declarations: tuple[dict[str, Any], ...]
    global_invariants: tuple[dict[str, Any], ...]
    raw: dict[str, Any]


@dataclass(frozen=True, order=True)
class NamespacedId:
    """名前空間を保存した識別子。

    Attributes:
        namespace: 識別子の名前空間。
        id: 正規化後の識別子。
    """

    namespace: str
    id: str


@dataclass(frozen=True)
class StructureTuple:
    """資産または抽出器が導出した構造タプル。"""

    kind: str
    source: NamespacedId
    target: NamespacedId
    direction: str
    participants: tuple[NamespacedId, ...]


@dataclass(frozen=True)
class AssetRecord:
    """collectionの1項目とその展開値。"""

    identifiers: tuple[NamespacedId, ...]
    raw: dict[str, Any]
    fields: dict[str, Any]
    refs: tuple[NamespacedId, ...]
    structures: tuple[StructureTuple, ...]


@dataclass(frozen=True)
class AssetCollection:
    """検証済み資産collection。"""

    index: int
    namespace: str
    declaration: dict[str, Any]
    records: tuple[AssetRecord, ...]


@dataclass(frozen=True)
class LoadedAsset:
    """検証済み資産と1つ以上のcollection。"""

    name: str
    path: Path
    raw: Any
    declaration: dict[str, Any]
    collections: tuple[AssetCollection, ...]


@dataclass(frozen=True)
class AssetJoin:
    """異名キーで解決した資産間参照。"""

    source_asset: str
    source: NamespacedId
    target_asset: str
    target: NamespacedId


@dataclass(frozen=True)
class LoadedAssets:
    """プロファイルの全資産と導出結果。"""

    assets: dict[str, LoadedAsset]
    structures: tuple[StructureTuple, ...]
    joins: tuple[AssetJoin, ...]
    normalize: dict[str, Any] | None


@dataclass(frozen=True)
class CollectionSetResult:
    """collection setの集合関係判定。"""

    id: str
    relation: str
    satisfied: bool
    left_only: frozenset[str]
    right_only: frozenset[str]

    @property
    def reason(self) -> str | None:
        """違反時の差集合を含む文言を返す。"""
        if self.satisfied:
            return None
        return (
            f"{self.id}: {self.relation} 不一致"
            f"(left-only={sorted(self.left_only)}, "
            f"right-only={sorted(self.right_only)})"
        )


def validate_against_schema(
    instance: Any,
    schema: Mapping[str, Any],
    *,
    path: str = "$",
) -> None:
    """JSON Schemaの限定部分集合で値を検証する。

    Args:
        instance: 検証対象のJSON値。
        schema: 限定キーワードだけを使うJSON Schema。
        path: エラー表示に使う検証対象のJSONパス。

    Raises:
        ProfileError: スキーマが未対応の構文を含むか、値が違反する場合。
    """
    _validate_schema_definition(schema, path="$schema", root=True)
    _validate_instance(instance, schema, path=path)


def load_json(path: str | Path) -> Any:
    """UTF-8のJSONを重複キーを拒否して読む。

    Args:
        path: 読み込むJSONファイル。

    Returns:
        復号したJSON値。

    Raises:
        ProfileError: ファイルを読めない、JSONが不正、キーが重複する場合。
    """
    json_path = Path(path)

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ProfileError(f"{json_path}: JSONキー {key!r} が重複しています")
            value[key] = item
        return value

    try:
        text = json_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ProfileError(f"{json_path}: JSONファイルを読めません: {error}") from error
    try:
        return json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except ProfileError:
        raise
    except json.JSONDecodeError as error:
        raise ProfileError(
            f"{json_path}: JSONが不正です({error.lineno}行{error.colno}列): {error.msg}"
        ) from error


def canonical_digest(obj: Any) -> str:
    """JSON値をcanonical化してSHA-256の小文字hexを返す。

    Args:
        obj: digest対象のJSON値。

    Returns:
        canonical JSONのUTF-8バイト列に対するSHA-256。

    Raises:
        ProfileError: floatを含むかJSONとして直列化できない場合。
    """
    float_path = _find_float(obj)
    if float_path is not None:
        raise ProfileError(f"{float_path}: canonical JSONにfloatは使用できません")
    try:
        canonical = json.dumps(
            obj,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    except (TypeError, ValueError) as error:
        raise ProfileError(f"canonical JSONへ直列化できません: {error}") from error
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def file_digest(path: str | Path) -> str:
    """ファイルの逐語バイト列に対するSHA-256を返す。

    Args:
        path: digest対象ファイル。

    Returns:
        SHA-256の小文字hex。

    Raises:
        ProfileError: ファイルを読めない場合。
    """
    file_path = Path(path)
    try:
        content = file_path.read_bytes()
    except OSError as error:
        raise ProfileError(f"{file_path}: pin対象資産を読めません: {error}") from error
    return hashlib.sha256(content).hexdigest()


def json_path_values(instance: Any, path: str) -> tuple[Any, ...]:
    """限定JSONパスで値を0件以上の列として取り出す。

    ``$.a.b[*]`` 形の絶対パスと、``c`` / ``c[*]`` 形の
    collection項目内パスだけを受け付ける。

    Args:
        instance: 起点のJSON値。
        path: 限定JSONパス。

    Returns:
        ワイルドカードを展開した値列。

    Raises:
        ProfileError: パス文法が不正か、解決できない場合。
    """
    if path.startswith("$."):
        token_text = path[2:]
        if re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*(?:\[\*\])?"
            r"(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\*\])?)*",
            token_text,
        ) is None:
            raise ProfileError(f"JSONパスが限定文法に一致しません: {path}")
        tokens = token_text.split(".")
    else:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\[\*\])?", path) is None:
            raise ProfileError(f"JSONパスが限定文法に一致しません: {path}")
        tokens = [path]

    values = (instance,)
    for token in tokens:
        wildcard = token.endswith("[*]")
        key = token[:-3] if wildcard else token
        next_values: list[Any] = []
        for value in values:
            if not isinstance(value, Mapping) or key not in value:
                raise ProfileError(f"JSONパスを解決できません: {path}: {key}")
            selected = value[key]
            if wildcard:
                if not isinstance(selected, list):
                    raise ProfileError(
                        f"JSONパスの[*]対象がarrayではありません: {path}"
                    )
                next_values.extend(selected)
            else:
                next_values.append(selected)
        values = tuple(next_values)
    return values


def _asset_schema_instance(raw: Mapping[str, Any]) -> dict[str, Any]:
    """プロファイルの資産節をスキーマ入力に写す。"""
    return {
        "schema_version": _SCHEMA_VERSION,
        "immutable_fields": list(ASSET_IMMUTABLE_FIELDS),
        "mutable_fields": list(ASSET_MUTABLE_FIELDS),
        "assets": raw["assets"],
        "structure_extractors": raw["structure_extractors"],
        "collection_sets": raw["collection_sets"],
    }


def validate_asset_configuration(
    raw: Mapping[str, Any],
    *,
    profile_path: Path,
    schema_dir: Path,
) -> None:
    """資産・抽出器・集合宣言の閉じた形と必須連動を検査する。"""
    schema = _load_schema(schema_dir / _ASSETS_SCHEMA)
    try:
        validate_against_schema(_asset_schema_instance(raw), schema)
    except ProfileError as error:
        raise ProfileError(f"{profile_path}: {error}") from error

    for asset_name, declaration in raw["assets"].items():
        _validate_asset_declaration(asset_name, declaration, profile_path)
    _validate_single_normalizer(raw["assets"], profile_path)
    _validate_structure_extractors(raw["structure_extractors"], profile_path)
    _validate_collection_sets(raw["collection_sets"], profile_path)
    _validate_required_check_inputs(raw, profile_path)


def _validate_asset_declaration(
    asset_name: str,
    declaration: Any,
    profile_path: Path,
) -> None:
    """単一資産宣言のキーと値型を検査する。"""
    if not isinstance(declaration, Mapping):
        raise ProfileError(f"{profile_path}: assets.{asset_name} はobjectが必要です")
    unknown = set(declaration) - _ASSET_DECLARATION_FIELDS
    if unknown:
        raise ProfileError(
            f"{profile_path}: assets.{asset_name} に未知フィールドがあります: "
            f"{_format_values(unknown)}"
        )
    if not isinstance(declaration.get("path"), str) or not declaration["path"]:
        raise ProfileError(f"{profile_path}: assets.{asset_name}.path が不正です")
    identity = declaration.get("identity")
    if not isinstance(identity, Mapping):
        raise ProfileError(f"{profile_path}: assets.{asset_name}.identity が必要です")
    identity_unknown = set(identity) - {
        "schema_version",
        "asset_kind",
        "required_top_keys",
    }
    if identity_unknown:
        raise ProfileError(
            f"{profile_path}: assets.{asset_name}.identity に未知フィールド: "
            f"{_format_values(identity_unknown)}"
        )
    alternatives = {"asset_kind", "required_top_keys"} & set(identity)
    if len(alternatives) != 1:
        raise ProfileError(
            f"{profile_path}: assets.{asset_name}.identity は asset_kind / "
            "required_top_keys のどちらか一方が必要です"
        )
    if "schema_version" in identity and not isinstance(identity["schema_version"], int):
        raise ProfileError(
            f"{profile_path}: assets.{asset_name}.identity.schema_version が不正です"
        )
    if "asset_kind" in identity and (
        not isinstance(identity["asset_kind"], str) or not identity["asset_kind"]
    ):
        raise ProfileError(f"{profile_path}: assets.{asset_name}.identity.asset_kind が不正")
    required_top_keys = identity.get("required_top_keys")
    if required_top_keys is not None and not _is_string_sequence(required_top_keys):
        raise ProfileError(
            f"{profile_path}: assets.{asset_name}.identity.required_top_keys は"
            "文字列arrayが必要です"
        )

    collections = declaration.get("collections")
    if not isinstance(collections, list):
        raise ProfileError(f"{profile_path}: assets.{asset_name}.collections が必要です")
    for index, collection in enumerate(collections):
        _validate_collection_declaration(
            asset_name,
            index,
            collection,
            profile_path,
        )
    if "join" in declaration:
        join = declaration["join"]
        if not isinstance(join, Mapping) or set(join) != {"from_key", "to", "to_key"}:
            raise ProfileError(
                f"{profile_path}: assets.{asset_name}.join は "
                "from_key / to / to_key だけが必要です"
            )
        if not all(isinstance(join[key], str) and join[key] for key in join):
            raise ProfileError(f"{profile_path}: assets.{asset_name}.join に空値があります")
    if "normalize" in declaration:
        _validate_normalize(declaration["normalize"], profile_path)


def _validate_collection_declaration(
    asset_name: str,
    index: int,
    collection: Any,
    profile_path: Path,
) -> None:
    """collection宣言の閉包性と限定JSONパスを検査する。"""
    label = f"assets.{asset_name}.collections[{index}]"
    if not isinstance(collection, Mapping):
        raise ProfileError(f"{profile_path}: {label} はobjectが必要です")
    unknown = set(collection) - _COLLECTION_FIELDS
    if unknown:
        raise ProfileError(
            f"{profile_path}: {label} に未知フィールド: {_format_values(unknown)}"
        )
    for required in ("items", "id", "namespace"):
        if not isinstance(collection.get(required), str) or not collection[required]:
            raise ProfileError(f"{profile_path}: {label}.{required} が必要です")
    _validate_json_path_text(collection["items"], absolute=True)
    _validate_json_path_text(collection["id"], absolute=False)
    for optional in ("refs", "structures"):
        value = collection.get(optional)
        values = [value] if isinstance(value, str) else value
        if values is not None:
            if not _is_string_sequence(values):
                raise ProfileError(f"{profile_path}: {label}.{optional} が不正です")
            for path in values:
                _validate_json_path_text(path, absolute=False)
    fields = collection.get("fields", {})
    if not isinstance(fields, Mapping) or not all(
        isinstance(name, str)
        and isinstance(path, str)
        and name
        and path
        for name, path in fields.items()
    ):
        raise ProfileError(f"{profile_path}: {label}.fields が不正です")
    for path in fields.values():
        _validate_json_path_text(path, absolute=False)
    if "structure" in collection:
        _validate_structure_declaration(collection["structure"], f"{profile_path}: {label}")


def _validate_json_path_text(path: str, *, absolute: bool) -> None:
    """実値を解決せずに限定JSONパス文法だけを検査する。"""
    placeholder = {"a": {"b": []}, "c": []}
    try:
        if absolute:
            if not path.startswith("$."):
                raise ProfileError(f"items は $.で始まる必要があります: {path}")
            token_text = path[2:]
            pattern = (
                r"[A-Za-z_][A-Za-z0-9_]*(?:\[\*\])?"
                r"(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\*\])?)*"
            )
        else:
            token_text = path
            pattern = r"[A-Za-z_][A-Za-z0-9_]*(?:\[\*\])?"
        if re.fullmatch(pattern, token_text) is None:
            raise ProfileError(f"JSONパスが限定文法に一致しません: {path}")
    finally:
        del placeholder


def _validate_structure_declaration(structure: Any, label: str) -> None:
    """構造タプル導出宣言を検査する。"""
    if not isinstance(structure, Mapping) or set(structure) != _STRUCTURE_FIELDS:
        raise ProfileError(f"{label}.structure のフィールド集合が不正です")
    for key in ("kind", "source", "target"):
        if not isinstance(structure[key], str) or not structure[key]:
            raise ProfileError(f"{label}.structure.{key} が不正です")
    if structure["direction"] not in _STRUCTURE_DIRECTIONS:
        raise ProfileError(f"{label}.structure.direction が不正です")
    if not _is_string_sequence(structure["participants"]):
        raise ProfileError(f"{label}.structure.participants が不正です")
    for path in (structure["source"], structure["target"], *structure["participants"]):
        _validate_json_path_text(path, absolute=False)


def _validate_normalize(value: Any, profile_path: Path) -> None:
    """単一alias表を含む正規化宣言を検査する。"""
    required = {"strip_prefixes", "case", "separator", "aliases"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise ProfileError(f"{profile_path}: normalize のフィールド集合が不正です")
    if not _is_string_sequence(value["strip_prefixes"]):
        raise ProfileError(f"{profile_path}: normalize.strip_prefixes が不正です")
    if value["case"] not in {"preserve", "lower", "upper"}:
        raise ProfileError(f"{profile_path}: normalize.case が不正です")
    if not isinstance(value["separator"], str):
        raise ProfileError(f"{profile_path}: normalize.separator が不正です")
    aliases = value["aliases"]
    if not isinstance(aliases, Mapping):
        raise ProfileError(f"{profile_path}: normalize.aliases が不正です")
    for namespace, mapping in aliases.items():
        if not isinstance(namespace, str) or not isinstance(mapping, Mapping):
            raise ProfileError(f"{profile_path}: normalize.aliases が不正です")
        if not all(
            isinstance(alias, str)
            and isinstance(canonical, str)
            and alias
            and canonical
            for alias, canonical in mapping.items()
        ):
            raise ProfileError(f"{profile_path}: normalize.aliases.{namespace} が不正")
        canonical_values = set(mapping.values())
        re_aliased = set(mapping) & canonical_values
        if re_aliased:
            raise ProfileError(
                f"{profile_path}: canonical の再aliasまたは循環があります: "
                f"{_format_values(re_aliased)}"
            )
        normalized_aliases: dict[str, str] = {}
        for alias, canonical in mapping.items():
            normalized = _normalize_without_alias(alias, value)
            previous = normalized_aliases.get(normalized)
            if previous is not None and previous != canonical:
                raise ProfileError(
                    f"{profile_path}: alias {alias!r} が2つのcanonicalに衝突します"
                )
            normalized_aliases[normalized] = canonical


def _validate_single_normalizer(assets: Mapping[str, Any], profile_path: Path) -> None:
    """aliasの供給元が資産全体で1つ以下か検査する。"""
    providers = [name for name, declaration in assets.items() if "normalize" in declaration]
    if len(providers) > 1:
        raise ProfileError(
            f"{profile_path}: normalize/alias表の供給元は1つだけです: {providers}"
        )


def _validate_required_check_inputs(raw: Mapping[str, Any], profile_path: Path) -> None:
    """必須の新検査に対応する資産・抽出器・集合宣言を求める。"""
    required_checks = set(raw["required_checks"])
    asset_names = set(raw["assets"])
    for check_id, (required_assets, needs_extractors, needs_sets) in _NEW_CHECK_INPUTS.items():
        if check_id not in required_checks:
            continue
        missing_assets = required_assets - asset_names
        if missing_assets:
            raise ProfileError(
                f"{profile_path}: required_checks={check_id} に必要なassetsがありません: "
                f"{_format_values(missing_assets)}"
            )
        if needs_extractors and not raw["structure_extractors"]:
            raise ProfileError(
                f"{profile_path}: required_checks={check_id} にstructure_extractorsが必要です"
            )
        if needs_sets and not raw["collection_sets"]:
            raise ProfileError(
                f"{profile_path}: required_checks={check_id} にcollection_setsが必要です"
            )


def _validate_structure_extractors(values: Any, profile_path: Path) -> None:
    """構造抽出器宣言をsource別に検査する。"""
    if not isinstance(values, list):
        raise ProfileError(f"{profile_path}: structure_extractors はarrayが必要です")
    identifiers: list[str] = []
    allowed = {"id", "source", "kind", "section", "table", "map", "from", "rule"}
    for index, extractor in enumerate(values):
        label = f"structure_extractors[{index}]"
        if not isinstance(extractor, Mapping):
            raise ProfileError(f"{profile_path}: {label} はobjectが必要です")
        unknown = set(extractor) - allowed
        if unknown:
            raise ProfileError(
                f"{profile_path}: {label} に未知フィールド: {_format_values(unknown)}"
            )
        for required in ("id", "source", "kind"):
            if not isinstance(extractor.get(required), str) or not extractor[required]:
                raise ProfileError(f"{profile_path}: {label}.{required} が必要です")
        identifiers.append(extractor["id"])
        source = extractor["source"]
        if source not in {"manifest", "document", "derived"}:
            raise ProfileError(f"{profile_path}: {label}.source が不正です: {source}")
        if source == "derived":
            if set(extractor) & {"section", "table", "map"}:
                raise ProfileError(f"{profile_path}: {label} derived に表写像は指定できません")
            if not isinstance(extractor.get("from"), str) or extractor.get("rule") not in {
                "transitive-closure",
                "inverse",
            }:
                raise ProfileError(f"{profile_path}: {label} derived の from/rule が不正です")
            continue
        if "from" in extractor or "rule" in extractor:
            raise ProfileError(f"{profile_path}: {label} の from/rule はderived専用です")
        mapping = extractor.get("map")
        _validate_extractor_map(mapping, label, profile_path, document=source == "document")
        if source == "document":
            if not isinstance(extractor.get("section"), str) or not extractor["section"]:
                raise ProfileError(f"{profile_path}: {label}.section が必要です")
            table = extractor.get("table")
            if not isinstance(table, Mapping) or set(table) != {"header_match"}:
                raise ProfileError(f"{profile_path}: {label}.table.header_match が必要です")
            if not _is_string_sequence(table["header_match"]) or not table["header_match"]:
                raise ProfileError(f"{profile_path}: {label}.table.header_match が不正です")
        elif "section" in extractor or "table" in extractor:
            raise ProfileError(f"{profile_path}: {label} manifest にsection/tableは使えません")
    duplicates = {value for value in identifiers if identifiers.count(value) > 1}
    if duplicates:
        raise ProfileError(
            f"{profile_path}: structure_extractors[].id が重複: {_format_values(duplicates)}"
        )


def _validate_extractor_map(
    mapping: Any,
    label: str,
    profile_path: Path,
    *,
    document: bool,
) -> None:
    """抽出器の構造写像と端点名前空間を検査する。"""
    if not isinstance(mapping, Mapping) or set(mapping) != {
        "source",
        "target",
        "direction",
        "participants",
    }:
        raise ProfileError(f"{profile_path}: {label}.map のフィールド集合が不正です")
    if mapping["direction"] not in _STRUCTURE_DIRECTIONS:
        raise ProfileError(f"{profile_path}: {label}.map.direction が不正です")
    if not isinstance(mapping["participants"], list):
        raise ProfileError(f"{profile_path}: {label}.map.participants はarrayが必要です")
    for endpoint_name in ("source", "target"):
        endpoint = mapping[endpoint_name]
        if document:
            _validate_document_endpoint(endpoint, f"{profile_path}: {label}.map.{endpoint_name}")
        elif not isinstance(endpoint, str) or not endpoint:
            raise ProfileError(f"{profile_path}: {label}.map.{endpoint_name} が不正です")
    for participant in mapping["participants"]:
        if not isinstance(participant, str) or not participant:
            raise ProfileError(f"{profile_path}: {label}.map.participants が不正です")


def _validate_document_endpoint(endpoint: Any, label: str) -> None:
    """文書表の列端点にcolumnとnamespaceを要求する。"""
    if not isinstance(endpoint, Mapping) or set(endpoint) - {
        "column",
        "regex",
        "namespace",
    }:
        raise ProfileError(f"{label} は column/regex?/namespace のobjectが必要です")
    if set(endpoint) < {"column", "namespace"}:
        raise ProfileError(f"{label} に column と namespace が必要です")
    if not _is_nonnegative_integer(endpoint["column"]):
        raise ProfileError(f"{label}.column は0以上のintegerが必要です")
    if not isinstance(endpoint["namespace"], str) or not endpoint["namespace"]:
        raise ProfileError(f"{label}.namespace が必要です")
    if "regex" in endpoint:
        try:
            pattern = re.compile(endpoint["regex"])
        except (TypeError, re.error) as error:
            raise ProfileError(f"{label}.regex が不正です: {error}") from error
        if pattern.groups != 1:
            raise ProfileError(f"{label}.regex は捕捉グループ1個が必要です")


def _validate_collection_sets(values: Any, profile_path: Path) -> None:
    """collection_setsの3関係と左右項を検査する。"""
    if not isinstance(values, list):
        raise ProfileError(f"{profile_path}: collection_sets はarrayが必要です")
    identifiers: list[str] = []
    for index, declaration in enumerate(values):
        label = f"collection_sets[{index}]"
        if not isinstance(declaration, Mapping) or set(declaration) != {
            "id",
            "relation",
            "left",
            "right",
        }:
            raise ProfileError(f"{profile_path}: {label} のフィールド集合が不正です")
        if not isinstance(declaration["id"], str) or not declaration["id"]:
            raise ProfileError(f"{profile_path}: {label}.id が不正です")
        identifiers.append(declaration["id"])
        if declaration["relation"] not in {"exact", "subset", "disjoint"}:
            raise ProfileError(f"{profile_path}: {label}.relation が不正です")
        _validate_collection_side(declaration["left"], f"{profile_path}: {label}.left")
        _validate_collection_side(declaration["right"], f"{profile_path}: {label}.right")
    duplicates = {value for value in identifiers if identifiers.count(value) > 1}
    if duplicates:
        raise ProfileError(f"{profile_path}: collection_sets[].id が重複: {duplicates}")


def _validate_collection_side(side: Any, label: str) -> None:
    """collection setの資産側またはmanifest側を検査する。"""
    if not isinstance(side, Mapping):
        raise ProfileError(f"{label} はobjectが必要です")
    if "asset" in side:
        allowed = {"asset", "collection", "filter", "key"}
        if set(side) - allowed or not {"asset", "key"} <= set(side):
            raise ProfileError(f"{label} の資産参照が不正です")
        if "collection" in side and not _is_nonnegative_integer(side["collection"]):
            raise ProfileError(f"{label}.collection が不正です")
        if "filter" in side:
            filter_value = side["filter"]
            if not isinstance(filter_value, Mapping) or set(filter_value) != {
                "field",
                "equals",
            }:
                raise ProfileError(f"{label}.filter が不正です")
    elif "manifest" in side:
        if set(side) != {"manifest", "key"} or side["manifest"] != "relations":
            raise ProfileError(f"{label} のmanifest参照が不正です")
    else:
        raise ProfileError(f"{label} にassetまたはmanifestが必要です")
    if not isinstance(side.get("key"), str) or not side["key"]:
        raise ProfileError(f"{label}.key が必要です")


def _normalize_without_alias(raw_id: str, normalize: Mapping[str, Any] | None) -> str:
    """prefix・大小文字・区切り文字だけを正規化する。"""
    if normalize is None:
        return raw_id
    value = raw_id
    for prefix_value in sorted(normalize["strip_prefixes"], key=len, reverse=True):
        prefix = str(prefix_value)
        if prefix and value.startswith(prefix):
            value = value[len(prefix) :]
            break
    if normalize["case"] == "lower":
        value = value.lower()
    elif normalize["case"] == "upper":
        value = value.upper()
    separator = normalize["separator"]
    value = re.sub(r"[-_.:/]+", separator, value)
    return value


def normalize_identifier(
    raw_id: str,
    namespace: str,
    normalize: Mapping[str, Any] | None = None,
) -> NamespacedId:
    """名前空間を保ったまま識別子に単一alias表を適用する。"""
    if not isinstance(raw_id, str) or not raw_id:
        raise ProfileError(f"識別子が非空文字列ではありません: {raw_id!r}")
    normalized = _normalize_without_alias(raw_id, normalize)
    if normalize is not None:
        aliases = normalize["aliases"].get(namespace, {})
        direct = aliases.get(raw_id)
        normalized_alias = aliases.get(normalized)
        if direct is not None and normalized_alias is not None and direct != normalized_alias:
            raise ProfileError(
                f"名前空間 {namespace} のalias {raw_id!r} が2つのcanonicalを指します"
            )
        canonical = direct if direct is not None else normalized_alias
        if canonical is not None:
            normalized = _normalize_without_alias(canonical, normalize)
    if not normalized:
        raise ProfileError(f"正規化後の識別子が空です: {namespace}:{raw_id}")
    return NamespacedId(namespace=namespace, id=normalized)


def load_assets(profile: Profile) -> LoadedAssets:
    """プロファイルの資産を読み、collection・構造・joinを展開する。"""
    declarations = profile.raw["assets"]
    normalizers = [
        dict(declaration["normalize"])
        for declaration in declarations.values()
        if "normalize" in declaration
    ]
    normalize = normalizers[0] if normalizers else None
    collision_registry: dict[tuple[str, str], set[str]] = {}
    loaded: dict[str, LoadedAsset] = {}
    all_structures: list[StructureTuple] = []
    for asset_name, declaration_value in declarations.items():
        declaration = dict(declaration_value)
        path = _resolve_path(profile.root, declaration["path"])
        raw = _load_asset_value(path, asset_name)
        _validate_asset_identity(raw, declaration["identity"], path, asset_name)
        collections: list[AssetCollection] = []
        for index, collection_value in enumerate(declaration["collections"]):
            collection = _load_asset_collection(
                raw,
                asset_name=asset_name,
                index=index,
                declaration=dict(collection_value),
                normalize=normalize,
                collisions=collision_registry,
            )
            collections.append(collection)
            all_structures.extend(
                structure
                for record in collection.records
                for structure in record.structures
            )
        loaded[asset_name] = LoadedAsset(
            name=asset_name,
            path=path,
            raw=raw,
            declaration=declaration,
            collections=tuple(collections),
        )
    joins = _resolve_asset_joins(loaded, normalize)
    return LoadedAssets(
        assets=loaded,
        structures=tuple(all_structures),
        joins=joins,
        normalize=normalize,
    )


def asset_structures(assets: LoadedAssets, asset_name: str) -> tuple[StructureTuple, ...]:
    """資産の全構造タプルを宣言順で返す。

    collectionの ``structures`` で抽出した構造に加え、
    ``forbidden`` 資産のように項目自体が構造形の場合も扱う。

    Args:
        assets: 検証済み資産集合。
        asset_name: 構造を取り出す資産名。

    Returns:
        名前空間と正規化を保存した構造タプル列。

    Raises:
        ProfileError: 資産が未宣言か、構造項目の形が不正な場合。
    """
    asset = assets.assets.get(asset_name)
    if asset is None:
        raise ProfileError(f"資産がありません: {asset_name}")
    structures: list[StructureTuple] = []
    for collection in asset.collections:
        for record in collection.records:
            structures.extend(record.structures)
            if _STRUCTURE_FIELDS <= set(record.raw):
                value = {key: record.raw[key] for key in _STRUCTURE_FIELDS}
                structures.append(_structure_from_raw(value, assets.normalize))
    return tuple(structures)


def _load_asset_value(path: Path, asset_name: str) -> Any:
    """JSON資産とbaselineテキストを読む。"""
    if asset_name == "baseline_digest" and path.suffix != ".json":
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise ProfileError(f"{path}: 資産を読めません: {error}") from error
    return load_json(path)


def _validate_asset_identity(
    raw: Any,
    identity: Mapping[str, Any],
    path: Path,
    asset_name: str,
) -> None:
    """資産の版・asset_kindまたは必須トップキーを照合する。"""
    if isinstance(raw, Mapping):
        if "schema_version" in identity and raw.get("schema_version") != identity["schema_version"]:
            raise ProfileError(
                f"{path}: {asset_name} schema_version 不一致"
                f"(期待={identity['schema_version']!r}, 実際={raw.get('schema_version')!r})"
            )
        if "asset_kind" in identity and raw.get("asset_kind") != identity["asset_kind"]:
            raise ProfileError(
                f"{path}: {asset_name} asset_kind 不一致"
                f"(期待={identity['asset_kind']!r}, 実際={raw.get('asset_kind')!r})"
            )
        missing = set(identity.get("required_top_keys", [])) - set(raw)
        if missing:
            raise ProfileError(
                f"{path}: {asset_name} の必須トップキーがありません: "
                f"{_format_values(missing)}"
            )
        return
    if identity.get("required_top_keys") == [] and "schema_version" not in identity:
        return
    raise ProfileError(f"{path}: {asset_name} のidentityにobject資産が必要です")


def _load_asset_collection(
    raw: Any,
    *,
    asset_name: str,
    index: int,
    declaration: dict[str, Any],
    normalize: Mapping[str, Any] | None,
    collisions: dict[tuple[str, str], set[str]],
) -> AssetCollection:
    """collectionの項目・ID・参照・構造を展開する。"""
    items = json_path_values(raw, declaration["items"])
    namespace = declaration["namespace"]
    records: list[AssetRecord] = []
    for item in items:
        record_item = item if isinstance(item, dict) else {"value": item}
        raw_ids = json_path_values(record_item, declaration["id"])
        identifiers = tuple(
            _registered_identifier(
                raw_id,
                namespace,
                normalize,
                collisions,
            )
            for raw_id in raw_ids
        )
        fields = {
            name: _collapse_values(json_path_values(record_item, path))
            for name, path in declaration.get("fields", {}).items()
        }
        refs = tuple(
            normalize_identifier(str(value), _namespace_from_path(path, namespace), normalize)
            for path in _string_or_sequence(declaration.get("refs"))
            for value in json_path_values(record_item, path)
        )
        structures = list(
            structure
            for path in _string_or_sequence(declaration.get("structures"))
            for value in json_path_values(record_item, path)
            for structure in (_structure_from_raw(value, normalize),)
        )
        if "structure" in declaration:
            structures.extend(
                _structures_from_collection_item(
                    record_item,
                    declaration["structure"],
                    namespace,
                    normalize,
                )
            )
        records.append(
            AssetRecord(
                identifiers=identifiers,
                raw=record_item,
                fields=fields,
                refs=refs,
                structures=tuple(structures),
            )
        )
    return AssetCollection(
        index=index,
        namespace=namespace,
        declaration=declaration,
        records=tuple(records),
    )


def _registered_identifier(
    raw_id: Any,
    namespace: str,
    normalize: Mapping[str, Any] | None,
    collisions: dict[tuple[str, str], set[str]],
) -> NamespacedId:
    """正規化後の名前空間内単射性を検査したIDを返す。"""
    if not isinstance(raw_id, str) or not raw_id:
        raise ProfileError(f"collection id が非空文字列ではありません: {raw_id!r}")
    identifier = normalize_identifier(raw_id, namespace, normalize)
    key = (namespace, identifier.id)
    previous = collisions.setdefault(key, set())
    if previous and raw_id not in previous and not _normalization_merge_is_explicit(
        previous,
        raw_id,
        namespace,
        normalize,
    ):
        raise ProfileError(
            f"名前空間 {namespace} 内で異なる元IDが {identifier.id!r} へ衝突: "
            f"{sorted(previous | {raw_id})}"
        )
    previous.add(raw_id)
    return identifier


def _normalization_merge_is_explicit(
    previous: set[str],
    raw_id: str,
    namespace: str,
    normalize: Mapping[str, Any] | None,
) -> bool:
    """prefix除去またはaliasで明示された統合か返す。"""
    if normalize is None:
        return False
    aliases = normalize["aliases"].get(namespace, {})
    if raw_id in aliases or any(value in aliases for value in previous):
        return True

    def stripped(value: str) -> str:
        for prefix_value in sorted(normalize["strip_prefixes"], key=len, reverse=True):
            prefix = str(prefix_value)
            if prefix and value.startswith(prefix):
                return value[len(prefix) :]
        return value

    return all(stripped(value) == stripped(raw_id) for value in previous)


def _string_or_sequence(value: Any) -> tuple[str, ...]:
    """任意の文字列または文字列arrayをタプル化する。"""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _collapse_values(values: tuple[Any, ...]) -> Any:
    """1値はscalar、複数値はタプルとして保存する。"""
    return values[0] if len(values) == 1 else values


def _namespace_from_path(path: str, fallback: str) -> str:
    """IDフィールド名から端点名前空間を導出する。"""
    field = path.removesuffix("[*]")
    if field.endswith("_ids"):
        return field[:-4]
    if field.endswith("_id"):
        return field[:-3]
    return fallback


def _structure_from_raw(
    value: Any,
    normalize: Mapping[str, Any] | None,
) -> StructureTuple:
    """資産内の構造objectを名前空間付きタプルにする。"""
    if not isinstance(value, Mapping) or set(value) != _STRUCTURE_FIELDS:
        raise ProfileError(f"資産内structuresのフィールド集合が不正: {value!r}")
    if value["direction"] not in _STRUCTURE_DIRECTIONS:
        raise ProfileError(f"資産内structures.directionが不正: {value['direction']!r}")
    source = _raw_endpoint(value["source"], "source", normalize)
    target = _raw_endpoint(value["target"], "target", normalize)
    participants_value = value["participants"]
    if not isinstance(participants_value, list):
        raise ProfileError("資産内structures.participantsはarrayが必要です")
    participants = tuple(
        _raw_endpoint(participant, "participant", normalize)
        for participant in participants_value
    )
    return StructureTuple(
        kind=str(value["kind"]),
        source=source,
        target=target,
        direction=str(value["direction"]),
        participants=participants,
    )


def _raw_endpoint(
    value: Any,
    fallback_namespace: str,
    normalize: Mapping[str, Any] | None,
) -> NamespacedId:
    """``{namespace,id}``端点を正規化する。"""
    if not isinstance(value, Mapping) or set(value) != {"namespace", "id"}:
        raise ProfileError(
            f"構造端点 {fallback_namespace} に namespace/id が必要です: "
            f"{value!r}"
        )
    namespace = value["namespace"]
    raw_id = value["id"]
    if not isinstance(namespace, str) or not isinstance(raw_id, str):
        raise ProfileError(f"構造端点が不正です: {value!r}")
    return normalize_identifier(raw_id, namespace, normalize)


def _structures_from_collection_item(
    item: Mapping[str, Any],
    declaration: Mapping[str, Any],
    fallback_namespace: str,
    normalize: Mapping[str, Any] | None,
) -> tuple[StructureTuple, ...]:
    """collection項目の配列端点を1タプルずつに展開する。"""
    source_path = declaration["source"]
    target_path = declaration["target"]
    source_values = json_path_values(item, source_path)
    target_values = json_path_values(item, target_path)
    structures: list[StructureTuple] = []
    for source_value, target_value in itertools.product(source_values, target_values):
        source = normalize_identifier(
            str(source_value),
            _namespace_from_path(source_path, fallback_namespace),
            normalize,
        )
        target = normalize_identifier(
            str(target_value),
            _namespace_from_path(target_path, fallback_namespace),
            normalize,
        )
        participants: list[NamespacedId] = []
        for participant_path in declaration["participants"]:
            if participant_path == source_path:
                participant_values = (source_value,)
            elif participant_path == target_path:
                participant_values = (target_value,)
            else:
                participant_values = json_path_values(item, participant_path)
            participants.extend(
                normalize_identifier(
                    str(participant),
                    _namespace_from_path(participant_path, fallback_namespace),
                    normalize,
                )
                for participant in participant_values
            )
        structures.append(
            StructureTuple(
                kind=declaration["kind"],
                source=source,
                target=target,
                direction=declaration["direction"],
                participants=tuple(participants),
            )
        )
    return tuple(structures)


def _resolve_asset_joins(
    assets: Mapping[str, LoadedAsset],
    normalize: Mapping[str, Any] | None,
) -> tuple[AssetJoin, ...]:
    """異名キーjoinを解決し、対応先不在をfail-closedにする。"""
    joins: list[AssetJoin] = []
    for asset_name, asset in assets.items():
        declaration = asset.declaration.get("join")
        if declaration is None:
            continue
        target_name = declaration["to"]
        target_asset = assets.get(target_name)
        if target_asset is None:
            raise ProfileError(f"assets.{asset_name}.join.to の資産がありません: {target_name}")
        target_values: dict[str, NamespacedId] = {}
        for collection in target_asset.collections:
            for record in collection.records:
                for raw_target in json_path_values(record.raw, declaration["to_key"]):
                    endpoint = normalize_identifier(
                        str(raw_target),
                        collection.namespace,
                        normalize,
                    )
                    target_values[endpoint.id] = endpoint
        for collection in asset.collections:
            for record in collection.records:
                for raw_reference in json_path_values(record.raw, declaration["from_key"]):
                    key = normalize_identifier(
                        str(raw_reference),
                        next(iter(target_values.values())).namespace
                        if target_values
                        else collection.namespace,
                        normalize,
                    )
                    target = target_values.get(key.id)
                    if target is None:
                        raise ProfileError(
                            f"assets.{asset_name}.join の参照先がありません: "
                            f"{raw_reference!r} -> {target_name}.{declaration['to_key']}"
                        )
                    for source in record.identifiers:
                        joins.append(AssetJoin(asset_name, source, target_name, target))
    return tuple(joins)


def extract_structures(
    profile: Profile,
    assets: LoadedAssets,
    *,
    text: str,
    manifest: Mapping[str, Any],
) -> dict[str, tuple[StructureTuple, ...]]:
    """manifest・文書・導出規則から構造タプルを得る。"""
    results: dict[str, tuple[StructureTuple, ...]] = {}
    for declaration in profile.raw["structure_extractors"]:
        source = declaration["source"]
        if source == "manifest":
            structures = _extract_manifest_structures(
                declaration,
                manifest,
                assets.normalize,
            )
        elif source == "document":
            structures = _extract_document_structures(
                declaration,
                text,
                assets.normalize,
            )
        else:
            from_id = declaration["from"]
            if from_id not in results:
                raise ProfileError(
                    f"structure extractor {declaration['id']} のfromが未定義: {from_id}"
                )
            structures = _derive_structures(declaration, results[from_id])
        if not structures:
            raise ProfileError(
                f"structure extractor {declaration['id']} が構造を1件も得られません"
            )
        _validate_extracted_endpoints(structures, assets, declaration["id"])
        results[declaration["id"]] = structures

    forbidden = assets.assets.get("forbidden")
    if forbidden is not None:
        forbidden_kinds = {
            str(record.raw["kind"])
            for collection in forbidden.collections
            for record in collection.records
            if "kind" in record.raw
        }
        extracted_kinds = {
            structure.kind
            for structures in results.values()
            for structure in structures
        }
        missing_kinds = forbidden_kinds - extracted_kinds
        if missing_kinds:
            raise ProfileError(
                "forbiddenの構造kindを覆うextractorがありません: "
                f"{_format_values(missing_kinds)}"
            )
    return results


def _validate_extracted_endpoints(
    structures: Sequence[StructureTuple],
    assets: LoadedAssets,
    extractor_id: str,
) -> None:
    """登録済み名前空間の抽出端点が別名を含め解決済みか検査する。"""
    known = {
        identifier
        for asset in assets.assets.values()
        for collection in asset.collections
        for record in collection.records
        for identifier in record.identifiers
    }
    known_namespaces = {identifier.namespace for identifier in known}
    unresolved = {
        endpoint
        for structure in structures
        for endpoint in (structure.source, structure.target, *structure.participants)
        if endpoint.namespace in known_namespaces and endpoint not in known
    }
    if unresolved:
        raise ProfileError(
            f"structure extractor {extractor_id} に未登録の別名またはID: "
            f"{_format_values(unresolved)}"
        )


def _extract_manifest_structures(
    declaration: Mapping[str, Any],
    manifest: Mapping[str, Any],
    normalize: Mapping[str, Any] | None,
) -> tuple[StructureTuple, ...]:
    """manifest.relationsのパス写像から構造を導出する。"""
    relations = manifest.get("relations")
    if isinstance(relations, Mapping):
        items = tuple(relations.values())
    elif isinstance(relations, list):
        items = tuple(relations)
    else:
        raise ProfileError("manifest.relations がarrayまたはobjectではありません")
    mapping = declaration["map"]
    structures: list[StructureTuple] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ProfileError("manifest.relations[] がobjectではありません")
        source_values = json_path_values(item, mapping["source"])
        target_values = json_path_values(item, mapping["target"])
        for source_value, target_value in itertools.product(source_values, target_values):
            source = normalize_identifier(
                str(source_value),
                _namespace_from_path(mapping["source"], "manifest"),
                normalize,
            )
            target = normalize_identifier(
                str(target_value),
                _namespace_from_path(mapping["target"], "manifest"),
                normalize,
            )
            participants: list[NamespacedId] = []
            for path in mapping["participants"]:
                if path == mapping["source"]:
                    values = (source_value,)
                elif path == mapping["target"]:
                    values = (target_value,)
                else:
                    values = json_path_values(item, path)
                participants.extend(
                    normalize_identifier(
                        str(value),
                        _namespace_from_path(path, "manifest"),
                        normalize,
                    )
                    for value in values
                )
            structures.append(
                StructureTuple(
                    kind=declaration["kind"],
                    source=source,
                    target=target,
                    direction=mapping["direction"],
                    participants=tuple(participants),
                )
            )
    return tuple(structures)


def _markdown_section(text: str, section_id: str) -> tuple[str, ...]:
    """節IDの見出しから次の同レベル以上までを取り出す。"""
    lines = text.splitlines()
    heading_re = re.compile(
        rf"^(?P<marks>#{{1,6}})\s+{re.escape(section_id)}(?:[.\s(])"
    )
    start: int | None = None
    level = 0
    for index, line in enumerate(lines):
        match = heading_re.match(line)
        if match is not None:
            start = index
            level = len(match.group("marks"))
            break
    if start is None:
        return ()
    end = len(lines)
    for index in range(start + 1, len(lines)):
        heading = re.match(r"^(#{1,6})\s+", lines[index])
        if heading is not None and len(heading.group(1)) <= level:
            end = index
            break
    return tuple(lines[start:end])


def _markdown_cells(line: str) -> tuple[str, ...] | None:
    """Markdown表行をセル列へ分解する。"""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return tuple(cell.strip() for cell in stripped[1:-1].split("|"))


def _is_markdown_separator(cells: Sequence[str]) -> bool:
    """Markdown表の区切り行か返す。"""
    return bool(cells) and all(
        re.fullmatch(r":?-{3,}:?", cell) is not None for cell in cells
    )


def _extract_document_structures(
    declaration: Mapping[str, Any],
    text: str,
    normalize: Mapping[str, Any] | None,
) -> tuple[StructureTuple, ...]:
    """節内の識別済み表から列写像で構造を導出する。"""
    lines = _markdown_section(text, declaration["section"])
    expected_header = tuple(declaration["table"]["header_match"])
    header_index: int | None = None
    header_width = 0
    for index, line in enumerate(lines):
        cells = _markdown_cells(line)
        if cells is not None and all(value in cells for value in expected_header):
            header_index = index
            header_width = len(cells)
            break
    if header_index is None:
        raise ProfileError(
            f"structure extractor {declaration['id']} の表ヘッダーが見つかりません: "
            f"{list(expected_header)}"
        )
    mapping = declaration["map"]
    structures: list[StructureTuple] = []
    for line in lines[header_index + 1 :]:
        cells = _markdown_cells(line)
        if cells is None:
            if structures:
                break
            continue
        if _is_markdown_separator(cells):
            continue
        if len(cells) != header_width:
            raise ProfileError(
                f"structure extractor {declaration['id']} の表列数が不一致: {line}"
            )
        source = _document_endpoint(cells, mapping["source"], normalize)
        target = _document_endpoint(cells, mapping["target"], normalize)
        participants = tuple(
            source
            if participant == "source"
            else target
            if participant == "target"
            else _document_endpoint(cells, mapping[participant], normalize)
            if participant in mapping and isinstance(mapping[participant], Mapping)
            else _raise_unknown_participant(declaration["id"], participant)
            for participant in mapping["participants"]
        )
        structures.append(
            StructureTuple(
                kind=declaration["kind"],
                source=source,
                target=target,
                direction=mapping["direction"],
                participants=participants,
            )
        )
    return tuple(structures)


def _raise_unknown_participant(extractor_id: str, participant: str) -> NamespacedId:
    """文書抽出器の未定義participantを例外にする。"""
    raise ProfileError(
        f"structure extractor {extractor_id} のparticipantが未定義: {participant}"
    )


def _document_endpoint(
    cells: Sequence[str],
    endpoint: Mapping[str, Any],
    normalize: Mapping[str, Any] | None,
) -> NamespacedId:
    """文書表の1セルをregexとnamespaceで端点にする。"""
    column = endpoint["column"]
    if column >= len(cells):
        raise ProfileError(f"文書抽出器のcolumn={column} が表の範囲外です")
    value = cells[column]
    if "regex" in endpoint:
        match = re.search(endpoint["regex"], value)
        if match is None:
            raise ProfileError(
                f"文書抽出器のregexがセルに一致しません: {value!r}"
            )
        value = match.group(1)
    return normalize_identifier(value, endpoint["namespace"], normalize)


def _derive_structures(
    declaration: Mapping[str, Any],
    source: Sequence[StructureTuple],
) -> tuple[StructureTuple, ...]:
    """inverseまたはtransitive-closureで構造を導出する。"""
    kind = declaration["kind"]
    if declaration["rule"] == "inverse":
        return tuple(
            StructureTuple(
                kind=kind,
                source=structure.target,
                target=structure.source,
                direction=structure.direction,
                participants=tuple(reversed(structure.participants)),
            )
            for structure in source
        )
    edges = {(structure.source, structure.target) for structure in source}
    closure = set(edges)
    changed = True
    while changed:
        changed = False
        additions = {
            (left_source, right_target)
            for left_source, left_target in closure
            for right_source, right_target in closure
            if left_target == right_source and (left_source, right_target) not in closure
        }
        if additions:
            closure.update(additions)
            changed = True
    direction = source[0].direction if source else "source->target"
    return tuple(
        StructureTuple(
            kind=kind,
            source=edge_source,
            target=edge_target,
            direction=direction,
            participants=(edge_source, edge_target),
        )
        for edge_source, edge_target in sorted(closure)
    )


def evaluate_collection_sets(
    profile: Profile,
    assets: LoadedAssets,
    *,
    manifest: Mapping[str, Any],
) -> tuple[CollectionSetResult, ...]:
    """collection_setsのexact・subset・disjointを評価する。"""
    results: list[CollectionSetResult] = []
    for declaration in profile.raw["collection_sets"]:
        left = _collection_side_values(declaration["left"], assets, manifest)
        right = _collection_side_values(declaration["right"], assets, manifest)
        relation = declaration["relation"]
        if relation == "exact":
            satisfied = left == right
        elif relation == "subset":
            satisfied = left <= right
        else:
            satisfied = left.isdisjoint(right)
        results.append(
            CollectionSetResult(
                id=declaration["id"],
                relation=relation,
                satisfied=satisfied,
                left_only=frozenset(left - right),
                right_only=frozenset(right - left),
            )
        )
    return tuple(results)


def _collection_side_values(
    side: Mapping[str, Any],
    assets: LoadedAssets,
    manifest: Mapping[str, Any],
) -> set[str]:
    """collection setの片側を文字列集合へ展開する。"""
    values: set[str] = set()
    if "asset" in side:
        asset = assets.assets.get(side["asset"])
        if asset is None:
            raise ProfileError(f"collection_setの資産がありません: {side['asset']}")
        if "collection" in side:
            index = side["collection"]
            if index >= len(asset.collections):
                raise ProfileError(
                    f"collection_setのcollectionが範囲外: {side['asset']}[{index}]"
                )
            collections = (asset.collections[index],)
        else:
            collections = asset.collections
        for collection in collections:
            for record in collection.records:
                filter_value = side.get("filter")
                if filter_value is not None:
                    actual = _collapse_values(
                        json_path_values(record.raw, filter_value["field"])
                    )
                    if actual != filter_value["equals"]:
                        continue
                values.update(
                    normalize_identifier(
                        str(value),
                        collection.namespace,
                        assets.normalize,
                    ).id
                    for value in json_path_values(record.raw, side["key"])
                )
        return values

    relations = manifest.get("relations")
    if isinstance(relations, Mapping):
        relation_values = relations.values()
    elif isinstance(relations, list):
        relation_values = relations
    else:
        raise ProfileError("collection_setのmanifest.relationsが不正です")
    for relation in relation_values:
        values.update(str(value) for value in json_path_values(relation, side["key"]))
    return values


def validate_profile_assets(profile: Profile) -> LoadedAssets:
    """資産・抽出器・集合宣言を実ファイルに対して検証する。"""
    assets = load_assets(profile)
    if profile.raw["structure_extractors"] or profile.raw["collection_sets"]:
        manifest_value = load_json(profile.manifest)
        if not isinstance(manifest_value, Mapping):
            raise ProfileError(f"{profile.manifest}: manifestはobjectが必要です")
    else:
        manifest_value = {}
    if profile.raw["structure_extractors"]:
        try:
            text = profile.document.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise ProfileError(f"{profile.document}: 抽出対象文書を読めません: {error}") from error
        extract_structures(profile, assets, text=text, manifest=manifest_value)
    if profile.raw["collection_sets"]:
        evaluate_collection_sets(profile, assets, manifest=manifest_value)
    return assets


def _validate_asset_pins(
    entry: RegistryEntry,
    profile: Profile,
    assets: LoadedAssets,
) -> None:
    """レジストリの資産pinと必須検査のpin完全性を検査する。"""
    pins = entry.pins["asset_digests"]
    required_pins: set[str] = set()
    for check_id, names in _REQUIRED_ASSET_PINS.items():
        if check_id in profile.required_checks:
            required_pins.update(names)
    missing_pins = required_pins - set(pins)
    if missing_pins:
        raise ProfileError(
            f"{entry.file}: 必須検査の pins.asset_digests がありません: "
            f"{_format_values(missing_pins)}"
        )
    unknown_pins = set(pins) - set(assets.assets)
    if unknown_pins:
        raise ProfileError(
            f"{entry.file}: pins.asset_digests の資産宣言がありません: "
            f"{_format_values(unknown_pins)}"
        )
    for asset_name, expected in pins.items():
        actual = file_digest(assets.assets[asset_name].path)
        if actual != expected:
            raise ProfileError(
                f"{entry.file}: pins.asset_digests.{asset_name} が不一致です"
                f"(期待={expected}, 実際={actual})"
            )


def default_registry_path(root: str | Path) -> Path:
    """本番レジストリの絶対パスを返す。

    Args:
        root: リポジトリルート。

    Returns:
        ``scripts/design_relations/profiles/registry.json`` の絶対パス。
    """
    return Path(root).resolve() / "scripts/design_relations/profiles/registry.json"


def default_schema_dir(root: str | Path) -> Path:
    """本番スキーマディレクトリの絶対パスを返す。

    Args:
        root: リポジトリルート。

    Returns:
        ``scripts/design_relations/schemas`` の絶対パス。
    """
    return Path(root).resolve() / "scripts/design_relations/schemas"


def validate_declaration(declaration: Mapping[str, Any]) -> None:
    """kind別の宣言引数が設計契約を満たすか検査する。

    Args:
        declaration: ``declarations[]`` の1宣言。

    Raises:
        ProfileError: kindが未対応か、必須引数・排他的引数が不正な場合。
    """
    kind = declaration.get("kind")
    defect_id = declaration.get("defect_id", "<不明>")
    if not isinstance(kind, str) or kind not in _DECLARATION_KINDS:
        raise ProfileError(f"宣言 {defect_id}: 未対応の kind です: {kind!r}")
    missing = _DECLARATION_REQUIRED_FIELDS[kind] - set(declaration)
    if missing:
        raise ProfileError(
            f"宣言 {defect_id} ({kind}): 必須引数がありません: "
            f"{_format_values(missing)}"
        )

    if kind in {"row-contains", "section-contains", "required-element"}:
        _require_one_declaration_field(
            declaration,
            kind=kind,
            defect_id=str(defect_id),
            fields=("literals", "elements"),
        )
    if kind == "required-element" and declaration.get("as", "text") != "text":
        raise ProfileError(
            f"宣言 {defect_id} ({kind}): alias の as は 'text' である必要があります"
        )
    if kind in {"exact-set", "required-exclusion"}:
        _require_one_declaration_field(
            declaration,
            kind=kind,
            defect_id=str(defect_id),
            fields=("row", "sections"),
        )
    if kind == "required-exclusion":
        terms = declaration["terms"]
        if not isinstance(terms, list) or not 1 <= len(terms) <= 2:
            raise ProfileError(
                f"宣言 {defect_id} ({kind}): terms は1〜2件である必要があります"
            )
    if kind == "cross-reference":
        for endpoint_name in ("from", "to"):
            endpoint = declaration[endpoint_name]
            if (
                not isinstance(endpoint, Mapping)
                or set(endpoint) != {"row"}
                or not isinstance(endpoint.get("row"), str)
                or not endpoint["row"]
            ):
                raise ProfileError(
                    f"宣言 {defect_id} ({kind}): {endpoint_name} は"
                    "非空の row だけを持つ必要があります"
                )
        extract = declaration["extract"]
        try:
            pattern = re.compile(extract)
        except re.error as error:
            raise ProfileError(
                f"宣言 {defect_id} ({kind}): extract の正規表現が不正です: "
                f"{error}"
            ) from error
        if pattern.groups != 1:
            raise ProfileError(
                f"宣言 {defect_id} ({kind}): extract は捕捉グループを"
                f"1個だけ持つ必要があります: {pattern.groups}個"
            )


def load_invariants(
    path: str | Path,
    *,
    schema_dir: str | Path | None = None,
) -> Invariants:
    """不変条件宣言資産をスキーマ検証して読む。

    Args:
        path: 宣言資産のパス。
        schema_dir: スキーマディレクトリ。省略時は資産の兄弟 ``schemas``。

    Returns:
        検証済みの不変条件宣言資産。

    Raises:
        ProfileError: スキーマ違反、版不一致、kind別引数違反がある場合。
    """
    invariant_path = Path(path).resolve()
    resolved_schema_dir = (
        invariant_path.parent.parent / "schemas"
        if schema_dir is None
        else Path(schema_dir).resolve()
    )
    raw = _load_object(invariant_path, label="不変条件宣言資産")
    schema = _load_schema(resolved_schema_dir / _INVARIANT_SCHEMA)
    try:
        validate_against_schema(raw, schema)
    except ProfileError as error:
        raise ProfileError(f"{invariant_path}: {error}") from error
    if raw["schema_version"] != _SCHEMA_VERSION:
        raise ProfileError(
            f"{invariant_path}: $.schema_version は "
            f"{_SCHEMA_VERSION} である必要があります"
        )
    declarations = tuple(dict(value) for value in raw["declarations"])
    for declaration in declarations:
        validate_declaration(declaration)
    return Invariants(
        path=invariant_path,
        structural_required=frozenset(raw["structural_required"]),
        legacy_structural=frozenset(raw["legacy_structural"]),
        required_declarations=frozenset(raw["required_declarations"]),
        declarations=declarations,
        global_invariants=tuple(
            dict(value) for value in raw.get("global_invariants", [])
        ),
        raw=raw,
    )


def validate_binding_rules(
    invariants: Invariants,
    *,
    machine_defect_ids: Iterable[str],
    forbidden_defect_ids: Iterable[str],
    legacy_branch_ids: Iterable[str],
) -> None:
    """不変条件宣言と欠陥oracleの汎用結合規則1〜5を検査する。

    Args:
        invariants: 検証済みの不変条件宣言資産。
        machine_defect_ids: 機械欠陥ID集合 ``M``。
        forbidden_defect_ids: forbiddenを持つ欠陥ID集合 ``F``。
        legacy_branch_ids: 旧構造分岐を持つ欠陥ID集合。

    Raises:
        ProfileError: 結合規則1〜5のいずれかに違反した場合。
    """
    machine = frozenset(machine_defect_ids)
    forbidden = frozenset(forbidden_defect_ids)
    legacy_branches = frozenset(legacy_branch_ids)
    structural = invariants.structural_required
    required = invariants.required_declarations
    legacy = invariants.legacy_structural
    declared = frozenset(
        declaration["defect_id"] for declaration in invariants.declarations
    )

    outside_machine = (structural | required) - machine
    overlap = structural & required
    if outside_machine or overlap:
        raise ProfileError(
            "結合規則1: structural_required / required_declarations が不正です"
            f"(機械欠陥外={_format_values(outside_machine)}, "
            f"重複={_format_values(overlap)})"
        )

    missing_declarations = ((structural - legacy) | required) - declared
    if missing_declarations:
        raise ProfileError(
            "結合規則2: 必須宣言が declarations にありません: "
            f"{_format_values(missing_declarations)}"
        )

    legacy_outside_structural = legacy - structural
    legacy_declared = legacy & declared
    legacy_without_branch = legacy - legacy_branches
    if legacy_outside_structural or legacy_declared or legacy_without_branch:
        raise ProfileError(
            "結合規則3: legacy_structural が不正です"
            f"(structural_required外={_format_values(legacy_outside_structural)}, "
            f"宣言と重複={_format_values(legacy_declared)}, "
            f"旧分岐なし={_format_values(legacy_without_branch)})"
        )

    declarations_outside_machine = declared - machine
    declarations_outside_binding = declared - (structural | required)
    if declarations_outside_machine or declarations_outside_binding:
        raise ProfileError(
            "結合規則4: declarations に余分な欠陥IDがあります"
            f"(機械欠陥外={_format_values(declarations_outside_machine)}, "
            f"結合集合外={_format_values(declarations_outside_binding)})"
        )

    forbidden_only_missing = machine - structural - required - forbidden
    if forbidden_only_missing:
        raise ProfileError(
            "結合規則5: 構造宣言対象外の機械欠陥に forbidden がありません: "
            f"{_format_values(forbidden_only_missing)}"
        )


def load_profile(
    path: str | Path,
    *,
    root: str | Path,
    schema_dir: str | Path | None = None,
) -> Profile:
    """プロファイルをスキーマ検証と意味検査の後に返す。

    Args:
        path: プロファイルファイル。相対パスはroot基準。
        root: 全プロファイル内パスの解決基準。
        schema_dir: スキーマディレクトリ。省略時は本番既定値。

    Returns:
        検証済みプロファイル。

    Raises:
        ProfileError: スキーマ違反または意味上の不整合がある場合。
    """
    root_path = Path(root).resolve()
    profile_path = _resolve_path(root_path, path)
    resolved_schema_dir = _schema_dir(root_path, schema_dir)
    raw = _load_object(profile_path, label="プロファイル")
    schema = _load_schema(resolved_schema_dir / _PROFILE_SCHEMA)
    profile_schema_value = dict(raw)
    if isinstance(raw.get("assets"), Mapping):
        profile_schema_value["assets"] = {}
    if isinstance(raw.get("structure_extractors"), list):
        profile_schema_value["structure_extractors"] = [
            {} for _ in raw["structure_extractors"]
        ]
    if isinstance(raw.get("collection_sets"), list):
        profile_schema_value["collection_sets"] = [
            {} for _ in raw["collection_sets"]
        ]
    try:
        validate_against_schema(profile_schema_value, schema)
    except ProfileError as error:
        raise ProfileError(f"{profile_path}: {error}") from error
    if raw["schema_version"] != _SCHEMA_VERSION:
        raise ProfileError(
            f"{profile_path}: $.schema_version は {_SCHEMA_VERSION} である必要があります"
        )

    required_values = raw["required_checks"]
    if len(required_values) != len(set(required_values)):
        raise ProfileError(f"{profile_path}: $.required_checks に重複IDがあります")
    required_checks = frozenset(required_values)
    not_applicable = dict(raw["not_applicable"])
    known_checks = frozenset(CHECK_IDS_ALL)
    unknown_not_applicable = set(not_applicable) - known_checks
    if unknown_not_applicable:
        raise ProfileError(
            f"{profile_path}: $.not_applicable に未知IDがあります: "
            f"{_format_values(unknown_not_applicable)}"
        )
    empty_reasons = {
        check_id for check_id, reason in not_applicable.items() if not reason.strip()
    }
    if empty_reasons:
        raise ProfileError(
            f"{profile_path}: $.not_applicable の理由が空です: "
            f"{_format_values(empty_reasons)}"
        )
    overlap = required_checks & set(not_applicable)
    covered = required_checks | set(not_applicable)
    if overlap:
        raise ProfileError(
            f"{profile_path}: required_checks と not_applicable が重複しています: "
            f"{_format_values(overlap)}"
        )
    if covered != known_checks:
        missing = known_checks - covered
        unknown = covered - known_checks
        raise ProfileError(
            f"{profile_path}: 検査IDの完全分割が不正です"
            f"(不足={_format_values(missing)}, 未知={_format_values(unknown)})"
        )

    invariant_values = raw["invariant_kinds"]
    if len(invariant_values) != len(set(invariant_values)):
        raise ProfileError(f"{profile_path}: $.invariant_kinds に重複kindがあります")
    unknown_kinds = set(invariant_values) - _INVARIANT_KINDS
    if unknown_kinds:
        raise ProfileError(
            f"{profile_path}: $.invariant_kinds に未知kindがあります: "
            f"{_format_values(unknown_kinds)}"
        )

    namespace_values = raw["defect_id_namespaces"]
    all_namespaces = frozenset(namespace_values["all"])
    machine_namespaces = frozenset(namespace_values["machine"])
    if len(all_namespaces) != len(namespace_values["all"]):
        raise ProfileError(f"{profile_path}: $.defect_id_namespaces.all に重複があります")
    if len(machine_namespaces) != len(namespace_values["machine"]):
        raise ProfileError(
            f"{profile_path}: $.defect_id_namespaces.machine に重複があります"
        )
    if not machine_namespaces <= all_namespaces:
        outside = machine_namespaces - all_namespaces
        raise ProfileError(
            f"{profile_path}: 機械欠陥の名前空間がallにありません: "
            f"{_format_values(outside)}"
        )

    validate_asset_configuration(
        raw,
        profile_path=profile_path,
        schema_dir=resolved_schema_dir,
    )

    return Profile(
        path=profile_path,
        root=root_path,
        schema_dir=resolved_schema_dir,
        name=raw["name"],
        document=_resolve_path(root_path, raw["document"]),
        manifest=_resolve_path(root_path, raw["manifest"]),
        defects=_resolve_path(root_path, raw["defects"]),
        invariants=_optional_path(root_path, raw.get("invariants")),
        requirements=_resolve_path(root_path, raw["requirements"]),
        universe=_resolve_path(root_path, raw["universe"]),
        link_base_dir=_resolve_path(root_path, raw["link_base_dir"]),
        direct_requirements=_optional_path(root_path, raw.get("direct_requirements")),
        required_checks=required_checks,
        not_applicable=not_applicable,
        invariant_kinds=frozenset(invariant_values),
        defect_id_namespaces={
            "all": all_namespaces,
            "machine": machine_namespaces,
        },
        raw=raw,
    )


def load_registry(
    path: str | Path,
    *,
    root: str | Path,
    schema_dir: str | Path | None = None,
) -> Registry:
    """レジストリを検証し、列挙ファイルとの完全一致を確認する。

    Args:
        path: レジストリファイル。相対パスはroot基準。
        root: レジストリ内パスの解決基準。
        schema_dir: スキーマディレクトリ。省略時は本番既定値。

    Returns:
        検証済みレジストリ。

    Raises:
        ProfileError: スキーマ違反、重複、列挙不一致がある場合。
    """
    root_path = Path(root).resolve()
    registry_path = _resolve_path(root_path, path)
    resolved_schema_dir = _schema_dir(root_path, schema_dir)
    raw = _load_object(registry_path, label="レジストリ")
    schema = _load_schema(resolved_schema_dir / _REGISTRY_SCHEMA)
    try:
        validate_against_schema(raw, schema)
    except ProfileError as error:
        raise ProfileError(f"{registry_path}: {error}") from error
    if raw["schema_version"] != _SCHEMA_VERSION:
        raise ProfileError(
            f"{registry_path}: $.schema_version は {_SCHEMA_VERSION} である必要があります"
        )
    if not raw["profiles"]:
        raise ProfileError(f"{registry_path}: $.profiles は1件以上必要です")

    entries = tuple(
        RegistryEntry(
            name=value["name"],
            file=_resolve_path(root_path, value["file"]),
            document=_resolve_path(root_path, value["document"]),
            must_require=frozenset(value["must_require"]),
            pins=dict(value["pins"]),
        )
        for value in raw["profiles"]
    )
    _require_unique(registry_path, "name", [entry.name for entry in entries])
    _require_unique(registry_path, "document", [entry.document for entry in entries])
    _require_unique(registry_path, "file", [entry.file for entry in entries])

    registered_files = {entry.file for entry in entries}
    actual_files = {
        candidate.resolve()
        for candidate in registry_path.parent.glob("*.json")
        if candidate.resolve() != registry_path
    }
    if registered_files != actual_files:
        unregistered = actual_files - registered_files
        missing = registered_files - actual_files
        raise ProfileError(
            f"{registry_path}: profilesの登録集合と実ファイル集合が一致しません"
            f"(未登録={_format_values(unregistered)}, "
            f"登録先不在={_format_values(missing)})"
        )
    return Registry(
        path=registry_path,
        entries=entries,
        schema_dir=resolved_schema_dir,
    )


def resolve_profiles(
    registry: Registry,
    *,
    root: str | Path,
) -> tuple[Profile, ...]:
    """レジストリの全プロファイルを読み、entryの固定値と照合する。

    Args:
        registry: 検証済みレジストリ。
        root: プロファイル内パスの解決基準。

    Returns:
        レジストリ順の検証済みプロファイル列。

    Raises:
        ProfileError: entryとの不一致またはpin不一致がある場合。
    """
    root_path = Path(root).resolve()
    profiles: list[Profile] = []
    for entry in registry.entries:
        profile = load_profile(
            entry.file,
            root=root_path,
            schema_dir=registry.schema_dir,
        )
        if entry.name != profile.name:
            raise ProfileError(
                f"{entry.file}: entry.name={entry.name!r} と "
                f"profile.name={profile.name!r} が一致しません"
            )
        if entry.document != profile.document:
            raise ProfileError(
                f"{entry.file}: entry.document={entry.document} と "
                f"profile.document={profile.document} が一致しません"
            )
        missing_required = entry.must_require - profile.required_checks
        if missing_required:
            raise ProfileError(
                f"{entry.file}: required_checks が must_require を満たしません: "
                f"{_format_values(missing_required)}"
            )
        gating = {key: profile.raw[key] for key in GATING_KEYS if key in profile.raw}
        actual_gating_digest = canonical_digest(gating)
        expected_gating_digest = entry.pins["profile_gating_digest"]
        if expected_gating_digest != actual_gating_digest:
            raise ProfileError(
                f"{entry.file}: pins.profile_gating_digest が不一致です"
                f"(期待={expected_gating_digest}, 実際={actual_gating_digest})"
            )

        invariants_digest = entry.pins.get("invariants_digest")
        if profile.invariants is not None and invariants_digest is None:
            raise ProfileError(
                f"{entry.file}: invariants={profile.invariants} に対する "
                "pins.invariants_digest がありません"
            )
        if profile.invariants is None and invariants_digest is not None:
            raise ProfileError(
                f"{entry.file}: pins.invariants_digest がありますが "
                "profile.invariants がありません"
            )
        if profile.invariants is not None and invariants_digest is not None:
            actual_invariants_digest = canonical_digest(load_json(profile.invariants))
            if invariants_digest != actual_invariants_digest:
                raise ProfileError(
                    f"{entry.file}: pins.invariants_digest が不一致です"
                    f"(期待={invariants_digest}, 実際={actual_invariants_digest})"
                )
        if "unique-owner" in profile.required_checks:
            if profile.invariants is None:
                raise ProfileError(
                    f"{entry.file}: required_checks=unique-owner に invariants が必要です"
                )
            invariant_set = load_invariants(
                profile.invariants,
                schema_dir=registry.schema_dir,
            )
            unique_owner = tuple(
                declaration
                for declaration in invariant_set.global_invariants
                if declaration.get("kind") == "unique-owner"
            )
            if len(unique_owner) != 1:
                raise ProfileError(
                    f"{entry.file}: required_checks=unique-owner に "
                    "global_invariants.unique-owner 1件が必要です"
                )
        assets = validate_profile_assets(profile)
        _validate_asset_pins(entry, profile, assets)
        profiles.append(profile)
    return tuple(profiles)


def validate_defect_id_namespaces(
    profile: Profile,
    defect_ids: Iterable[str],
) -> None:
    """欠陥IDの全名前空間と機械欠陥名前空間を検証する。

    Args:
        profile: 検証済みプロファイル。
        defect_ids: 検証対象の欠陥ID列。

    Raises:
        ProfileError: 未登録名前空間または機械欠陥の区分違反がある場合。
    """
    identifiers = tuple(defect_ids)
    all_namespaces = profile.defect_id_namespaces["all"]
    machine_namespaces = profile.defect_id_namespaces["machine"]
    unknown = {
        _defect_namespace(identifier)
        for identifier in identifiers
        if _defect_namespace(identifier) not in all_namespaces
    }
    if unknown:
        raise ProfileError(
            f"{profile.path}: 欠陥IDに未登録の名前空間があります: "
            f"{_format_values(unknown)}"
        )

    defects = _load_object(profile.defects, label="欠陥oracle")
    wrong_machine = {
        _defect_namespace(identifier)
        for identifier in identifiers
        if isinstance(defects.get(identifier), dict)
        and defects[identifier].get("detection") == "machine"
        and _defect_namespace(identifier) not in machine_namespaces
    }
    if wrong_machine:
        raise ProfileError(
            f"{profile.path}: 機械欠陥の名前空間がmachineにありません: "
            f"{_format_values(wrong_machine)}"
        )


def _validate_schema_definition(
    schema: Mapping[str, Any],
    *,
    path: str,
    root: bool = False,
) -> None:
    """スキーマ定義全体を先にfail-closedで検査する。"""
    if not isinstance(schema, Mapping):
        raise ProfileError(f"{path}: スキーマはobjectである必要があります")
    allowed = _SUPPORTED_SCHEMA_KEYWORDS | ({"schema_version"} if root else set())
    unsupported = set(schema) - allowed
    if unsupported:
        raise ProfileError(
            f"{path}: 未対応スキーマキーワードがあります: "
            f"{_format_values(unsupported)}"
        )
    if root and "schema_version" in schema:
        version = schema["schema_version"]
        if isinstance(version, bool) or version != _SCHEMA_VERSION:
            raise ProfileError(
                f"{path}.schema_version は {_SCHEMA_VERSION} である必要があります"
            )

    schema_type = schema.get("type")
    if schema_type is not None:
        type_names = _schema_type_names(schema_type, f"{path}.type")
        unknown_types = set(type_names) - _SUPPORTED_TYPES
        if unknown_types:
            raise ProfileError(
                f"{path}.type に未対応typeがあります: "
                f"{_format_values(unknown_types)}"
            )
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise ProfileError(f"{path}.properties はobjectである必要があります")
    for name, child in properties.items():
        if not isinstance(name, str) or not isinstance(child, Mapping):
            raise ProfileError(f"{path}.properties の定義が不正です")
        _validate_schema_definition(
            child,
            path=f"{path}.properties.{name}",
        )

    required = schema.get("required", [])
    if not _is_string_sequence(required):
        raise ProfileError(f"{path}.required は文字列arrayである必要があります")
    if "additionalProperties" in schema and schema["additionalProperties"] is not False:
        raise ProfileError(
            f"{path}.additionalProperties はfalseだけを使用できます"
        )
    enum_values = schema.get("enum")
    if enum_values is not None and not isinstance(enum_values, list):
        raise ProfileError(f"{path}.enum はarrayである必要があります")
    if "items" in schema:
        items = schema["items"]
        if not isinstance(items, Mapping):
            raise ProfileError(f"{path}.items はスキーマobjectである必要があります")
        _validate_schema_definition(items, path=f"{path}.items")
    for keyword in ("minLength", "minItems"):
        if keyword in schema and not _is_nonnegative_integer(schema[keyword]):
            raise ProfileError(f"{path}.{keyword} は0以上のintegerである必要があります")
    if "uniqueItems" in schema and not isinstance(schema["uniqueItems"], bool):
        raise ProfileError(f"{path}.uniqueItems はbooleanである必要があります")
    if "pattern" in schema:
        pattern = schema["pattern"]
        if not isinstance(pattern, str):
            raise ProfileError(f"{path}.pattern はstringである必要があります")
        try:
            re.compile(pattern)
        except re.error as error:
            raise ProfileError(f"{path}.pattern が不正です: {error}") from error


def _validate_instance(instance: Any, schema: Mapping[str, Any], *, path: str) -> None:
    """検証済みスキーマを用いて1つのJSON値を検査する。"""
    schema_type = schema.get("type")
    if schema_type is not None:
        type_names = _schema_type_names(schema_type, "$schema.type")
        if not any(_matches_type(instance, name) for name in type_names):
            raise ProfileError(
                f"{path}: typeが不正です"
                f"(期待={' または '.join(type_names)}, 実際={_json_type(instance)})"
            )
    if "enum" in schema and not any(
        _json_equal(instance, candidate) for candidate in schema["enum"]
    ):
        raise ProfileError(f"{path}: enumに含まれない値です: {instance!r}")

    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(instance)
        if missing:
            raise ProfileError(
                f"{path}: 必須フィールドがありません: {_format_values(missing)}"
            )
        if schema.get("additionalProperties") is False:
            unknown = set(instance) - set(properties)
            if unknown:
                raise ProfileError(
                    f"{path}: 未知フィールドがあります: {_format_values(unknown)}"
                )
        for name, child_schema in properties.items():
            if name in instance:
                _validate_instance(instance[name], child_schema, path=f"{path}.{name}")

    if isinstance(instance, list):
        minimum = schema.get("minItems")
        if minimum is not None and len(instance) < minimum:
            raise ProfileError(
                f"{path}: 要素数がminItems={minimum}未満です(実際={len(instance)})"
            )
        if schema.get("uniqueItems") is True:
            for index, value in enumerate(instance):
                if any(_json_equal(value, previous) for previous in instance[:index]):
                    raise ProfileError(f"{path}[{index}]: uniqueItemsに違反しています")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, value in enumerate(instance):
                _validate_instance(value, item_schema, path=f"{path}[{index}]")

    if isinstance(instance, str):
        minimum_length = schema.get("minLength")
        if minimum_length is not None and len(instance) < minimum_length:
            raise ProfileError(
                f"{path}: 文字数がminLength={minimum_length}未満です"
            )
        pattern = schema.get("pattern")
        if pattern is not None and re.search(pattern, instance) is None:
            raise ProfileError(f"{path}: pattern={pattern!r}に一致しません")


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    """JSONファイルを読み、トップレベルobjectを要求する。"""
    value = load_json(path)
    if not isinstance(value, dict):
        raise ProfileError(f"{path}: {label}のトップレベルはobjectである必要があります")
    return value


def _load_schema(path: Path) -> dict[str, Any]:
    """版付きスキーマobjectを読む。"""
    schema = _load_object(path, label="スキーマ")
    if schema.get("schema_version") != _SCHEMA_VERSION:
        raise ProfileError(
            f"{path}: schema_version は {_SCHEMA_VERSION} である必要があります"
        )
    return schema


def _schema_dir(root: Path, schema_dir: str | Path | None) -> Path:
    """明示または既定スキーマディレクトリを絶対化する。"""
    if schema_dir is None:
        return default_schema_dir(root)
    return _resolve_path(root, schema_dir)


def _resolve_path(root: Path, value: str | Path) -> Path:
    """root基準でパスを解決する。"""
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _optional_path(root: Path, value: Any) -> Path | None:
    """任意文字列パスを絶対化する。"""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProfileError(f"パス値はstringである必要があります: {value!r}")
    return _resolve_path(root, value)


def _require_one_declaration_field(
    declaration: Mapping[str, Any],
    *,
    kind: str,
    defect_id: str,
    fields: tuple[str, str],
) -> None:
    """宣言が選択肢のフィールドをちょうど1つ持つことを要求する。"""
    present = [field for field in fields if field in declaration]
    if len(present) != 1:
        raise ProfileError(
            f"宣言 {defect_id} ({kind}): "
            f"{fields[0]} / {fields[1]} はどちらか一方だけ必要です"
        )


def _require_unique(path: Path, field: str, values: Sequence[Any]) -> None:
    """レジストリフィールドの値が一意であることを検査する。"""
    duplicates = {value for value in values if values.count(value) > 1}
    if duplicates:
        raise ProfileError(
            f"{path}: profiles[].{field} が重複しています: "
            f"{_format_values(duplicates)}"
        )


def _schema_type_names(value: Any, path: str) -> tuple[str, ...]:
    """typeキーワードを正規化した文字列列として返す。"""
    if isinstance(value, str):
        return (value,)
    if _is_string_sequence(value) and value:
        return tuple(value)
    raise ProfileError(f"{path} はstringまたは非空の文字列arrayである必要があります")


def _matches_type(instance: Any, type_name: str) -> bool:
    """JSON値が限定type名に一致するか返す。"""
    if type_name == "object":
        return isinstance(instance, dict)
    if type_name == "array":
        return isinstance(instance, list)
    if type_name == "string":
        return isinstance(instance, str)
    if type_name == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if type_name == "boolean":
        return isinstance(instance, bool)
    return False


def _json_type(instance: Any) -> str:
    """エラー表示用のJSON type名を返す。"""
    if isinstance(instance, bool):
        return "boolean"
    if isinstance(instance, dict):
        return "object"
    if isinstance(instance, list):
        return "array"
    if isinstance(instance, str):
        return "string"
    if isinstance(instance, int):
        return "integer"
    if isinstance(instance, float):
        return "number"
    if instance is None:
        return "null"
    return type(instance).__name__


def _json_equal(left: Any, right: Any) -> bool:
    """booleanとintegerを区別してJSON値を比較する。"""
    if _json_type(left) != _json_type(right):
        return False
    return left == right


def _is_string_sequence(value: Any) -> bool:
    """値が文字列だけのlistか返す。"""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_nonnegative_integer(value: Any) -> bool:
    """値がbooleanでない0以上のintegerか返す。"""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _find_float(value: Any, *, path: str = "$") -> str | None:
    """入れ子のJSON値から最初のfloatのパスを返す。"""
    if isinstance(value, float):
        return path
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, float):
                return f"{path}.<key>"
            found = _find_float(item, path=f"{path}.{key}")
            if found is not None:
                return found
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            found = _find_float(item, path=f"{path}[{index}]")
            if found is not None:
                return found
    return None


def _defect_namespace(identifier: str) -> str:
    """欠陥IDのハイフン前を名前空間として返す。"""
    return identifier.split("-", 1)[0]


def _format_values(values: Iterable[Any]) -> str:
    """診断用に値を決定的な順で整形する。"""
    return ", ".join(sorted(str(value) for value in values)) or "なし"
