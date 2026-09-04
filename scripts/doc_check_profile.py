"""文書検査プロファイルとレジストリを読み込む共通機構。"""

from __future__ import annotations

import hashlib
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
    try:
        validate_against_schema(raw, schema)
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

    return Profile(
        path=profile_path,
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
