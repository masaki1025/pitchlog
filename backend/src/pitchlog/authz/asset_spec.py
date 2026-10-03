"""認可 DDL ツールチェーンが読む資産一式を不変値で指定する。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

type AuthzAssetKind = Literal["probe", "product"]
type AuthzScopeValue = str | bool


@dataclass(frozen=True, slots=True)
class AuthzElementSectionSpec:
    """DDL 要素種別と資産セクションの対応を表す。"""

    element_type: str
    section_name: str
    id_field: str
    position: int

    def __post_init__(self) -> None:
        """対応を構成する値が空でないことを保証する。"""
        if not self.element_type or not self.section_name or not self.id_field:
            raise ValueError("要素セクション指定の値は空にできない")
        if self.position < 0:
            raise ValueError("要素セクション指定の位置は負にできない")


@dataclass(frozen=True, slots=True)
class AuthzOperationHandlerSpec:
    """適用器の操作種別と処理関数の対応を表す。"""

    operation_kind: str
    handler_name: str

    def __post_init__(self) -> None:
        """操作種別と処理関数名が空でないことを保証する。"""
        if not self.operation_kind or not self.handler_name:
            raise ValueError("操作種別と処理関数名は空にできない")


class AuthzApplicationStepsError(ValueError):
    """製品認可の適用手順資産が静的契約を満たさないことを表す。"""


@dataclass(frozen=True, slots=True)
class ProductApplicationStep:
    """製品認可を適用する 1 手順を表す。"""

    step_id: str
    sequence: int
    operation_kind: str
    element_groups: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProductUnapplicationStep:
    """製品認可を取り外す 1 手順を表す。"""

    step_id: str
    sequence: int
    operation_kind: str
    reverses_application_step_id: str


@dataclass(frozen=True, slots=True)
class ProductApplicationSteps:
    """検証済みの製品認可の適用・取り外し手順を表す。"""

    transaction: str
    operation_kinds: tuple[str, ...]
    application_steps: tuple[ProductApplicationStep, ...]
    unapplication_steps: tuple[ProductUnapplicationStep, ...]
    preserved_role_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AuthzAssetSpec:
    """認可資産の配置と許可する意味を束ねる不変値。

    Attributes:
        asset_root: リポジトリルートからの資産ルート。
        ddl_elements_path: DDL 要素ファイルのリポジトリ相対パス。
        body_manifest_path: body manifest のリポジトリ相対パス。
        body_directory: SQL body ディレクトリのリポジトリ相対パス。
        body_checker_path: body 静的検査器のリポジトリ相対パス。
        scope_field: DDL 要素ファイルの scope object のフィールド名。
        scope_status_field: scope の種別値を持つフィールド名。
        allowed_scope_status: DDL 要素ファイルで許可する scope.status。
        asset_kind: probe または product の閉じた資産種別。
        element_sections: 要素種別と配列・ID列の不変な対応。
        operation_handlers: 適用器が許可する操作種別と処理関数の対応。
        exact_scope_items: scope object に要求するキーと値の完全な対応。None は
            status 以外に追加の制約を課さない。
        application_steps_path: 製品専用の適用手順資産。probe は None。
    """

    asset_root: PurePosixPath
    ddl_elements_path: PurePosixPath
    body_manifest_path: PurePosixPath
    body_directory: PurePosixPath
    body_checker_path: PurePosixPath
    scope_field: str
    scope_status_field: str
    allowed_scope_status: str
    asset_kind: AuthzAssetKind
    element_sections: tuple[AuthzElementSectionSpec, ...]
    operation_handlers: tuple[AuthzOperationHandlerSpec, ...]
    exact_scope_items: tuple[tuple[str, AuthzScopeValue], ...] | None = None
    application_steps_path: PurePosixPath | None = None

    def __post_init__(self) -> None:
        """パス・列挙・要素対応を fail-closed に検証する。"""
        repository_paths = (
            self.asset_root,
            self.ddl_elements_path,
            self.body_manifest_path,
            self.body_directory,
            self.body_checker_path,
            *((self.application_steps_path,) if self.application_steps_path else ()),
        )
        for path in repository_paths:
            if path.root or not path.parts or ".." in path.parts:
                raise ValueError(
                    f"資産パスは正規なリポジトリ相対パスでなければならない: {path}"
                )
        asset_root_parts = self.asset_root.parts
        for path in (
            self.ddl_elements_path,
            self.body_manifest_path,
            self.body_directory,
            *((self.application_steps_path,) if self.application_steps_path else ()),
        ):
            if path.parts[: len(asset_root_parts)] != asset_root_parts:
                raise ValueError(f"資産パスが資産ルート外を指している: {path}")
        try:
            self.body_manifest_path.relative_to(self.body_directory)
        except ValueError as error:
            raise ValueError("body manifestがbodyディレクトリ外を指している") from error
        if self.asset_kind not in {"probe", "product"}:
            raise ValueError(f"資産種別が閉じた列挙にない: {self.asset_kind!r}")
        if not self.scope_field or not self.scope_status_field:
            raise ValueError("scopeのフィールド名は空にできない")
        if not self.allowed_scope_status:
            raise ValueError("許可するscope値は空にできない")
        if self.exact_scope_items is not None:
            scope_names = tuple(name for name, _ in self.exact_scope_items)
            if not scope_names or len(scope_names) != len(set(scope_names)):
                raise ValueError(
                    "scopeの完全指定は空にできず、キーは一意である必要がある"
                )
            if not all(scope_names):
                raise ValueError("scopeの完全指定に空のキーは使えない")
            if not all(
                isinstance(value, (str, bool)) and value != ""
                for _, value in self.exact_scope_items
            ):
                raise ValueError("scopeの完全指定の値は空でない文字列か真偽値に限る")
            status_values = tuple(
                value
                for name, value in self.exact_scope_items
                if name == self.scope_status_field
            )
            if status_values != (self.allowed_scope_status,):
                raise ValueError(
                    "scopeの完全指定は許可するstatusをちょうど1つ含む必要がある"
                )
        if not self.element_sections:
            raise ValueError("要素セクション指定は空にできない")
        if self.asset_kind == "probe" and not self.operation_handlers:
            raise ValueError("probeの操作種別と処理関数の対応は空にできない")
        if self.asset_kind == "probe" and self.application_steps_path is not None:
            raise ValueError("probeに製品の適用手順資産は指定できない")
        dimensions = (
            tuple(section.element_type for section in self.element_sections),
            tuple(section.section_name for section in self.element_sections),
            tuple(section.id_field for section in self.element_sections),
            tuple(section.position for section in self.element_sections),
        )
        if any(len(values) != len(set(values)) for values in dimensions):
            raise ValueError("要素セクション指定の各次元は一意でなければならない")
        operation_kinds = tuple(
            operation.operation_kind for operation in self.operation_handlers
        )
        if len(operation_kinds) != len(set(operation_kinds)):
            raise ValueError("操作種別は一意でなければならない")


def asset_scope_validation_error(
    scope: object,
    spec: AuthzAssetSpec,
) -> str | None:
    """Scope object を資産指定の単一契約で検査する。

    Args:
        scope: DDL 要素資産から読んだ scope 値。
        spec: 許可する status と、必要なら object 全体の完全指定。

    Returns:
        違反理由。契約を満たす場合は None。
    """
    if not isinstance(scope, dict):
        return "scopeはobjectでなければならない"
    status = (
        scope[spec.scope_status_field] if spec.scope_status_field in scope else None
    )
    if status != spec.allowed_scope_status:
        return (
            "scope.statusが資産指定と一致しない: "
            f"期待={spec.allowed_scope_status!r}, 実際={status!r}"
        )
    if spec.exact_scope_items is None:
        return None

    for name, expected in spec.exact_scope_items:
        if name not in scope:
            return f"scopeのキー集合が資産指定と一致しない: 不足={name!r}"
        actual = scope[name]
        if expected is True or expected is False:
            if actual is not expected:
                return (
                    f"scope.{name}が資産指定と一致しない: "
                    f"期待={expected!r}, 実際={actual!r}"
                )
        elif actual != expected:
            return (
                f"scope.{name}が資産指定と一致しない: "
                f"期待={expected!r}, 実際={actual!r}"
            )

    for actual_name in scope:
        declared = False
        for expected_name, _ in spec.exact_scope_items:
            if actual_name == expected_name:
                declared = True
                break
        if not declared:
            return f"scopeのキー集合が資産指定と一致しない: 許可外={actual_name!r}"
    return None


_PRODUCT_APPLICATION_ELEMENT_GROUPS = (
    ("roles",),
    ("databases", "schemas"),
    ("functions:rls_helper",),
    ("tables",),
    ("policies", "predicates"),
    ("acl_expectations", "column_acl_expectations"),
    ("functions:migration_trigger",),
)
_PRODUCT_FUNCTION_KINDS = ("rls_helper", "migration_trigger")


def _read_json_object(path: Path, label: str) -> dict[str, object]:
    """JSON object を読み、適用手順の検証例外へ変換する。"""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AuthzApplicationStepsError(
            f"{label}を読めない: {path}: {error}"
        ) from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AuthzApplicationStepsError(f"{label}はJSON objectでなければならない")
    return value


def _require_exact_keys(
    value: dict[str, object], expected: set[str], label: str
) -> None:
    """Object のキー集合を過不足なく検査する。"""
    actual = set(value)
    if actual != expected:
        raise AuthzApplicationStepsError(
            f"{label}のキー集合が不一致: "
            f"不足={sorted(expected - actual)}, 許可外={sorted(actual - expected)}"
        )


def _require_string(value: object, label: str) -> str:
    """空でない文字列を取得する。"""
    if not isinstance(value, str) or not value:
        raise AuthzApplicationStepsError(f"{label}は空でない文字列でなければならない")
    return value


def _require_string_tuple(value: object, label: str) -> tuple[str, ...]:
    """空でない一意な文字列配列を取得する。"""
    if not isinstance(value, list) or not value:
        raise AuthzApplicationStepsError(
            f"{label}は空でない文字列配列でなければならない"
        )
    if not all(isinstance(item, str) and item for item in value):
        raise AuthzApplicationStepsError(
            f"{label}は空でない文字列配列でなければならない"
        )
    result = tuple(item for item in value if isinstance(item, str))
    if len(result) != len(set(result)):
        raise AuthzApplicationStepsError(f"{label}の値は一意でなければならない")
    return result


def _require_sequence(value: object, label: str) -> int:
    """正の整数の手順番号を取得する。"""
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise AuthzApplicationStepsError(f"{label}は正の整数でなければならない")
    return value


def _parse_application_steps(value: object) -> tuple[ProductApplicationStep, ...]:
    """適用手順を閉じた形で解釈する。"""
    if not isinstance(value, list):
        raise AuthzApplicationStepsError("application_stepsはarrayでなければならない")
    steps: list[ProductApplicationStep] = []
    for index in range(len(value)):
        raw_step = value[index]
        label = f"application_steps[{index}]"
        if not isinstance(raw_step, dict):
            raise AuthzApplicationStepsError(f"{label}はobjectでなければならない")
        _require_exact_keys(
            raw_step,
            {"step_id", "sequence", "operation_kind", "element_groups"},
            label,
        )
        steps.append(
            ProductApplicationStep(
                step_id=_require_string(raw_step["step_id"], f"{label}.step_id"),
                sequence=_require_sequence(raw_step["sequence"], f"{label}.sequence"),
                operation_kind=_require_string(
                    raw_step["operation_kind"], f"{label}.operation_kind"
                ),
                element_groups=_require_string_tuple(
                    raw_step["element_groups"], f"{label}.element_groups"
                ),
            )
        )
    return tuple(steps)


def _parse_unapplication_steps(
    value: object,
) -> tuple[ProductUnapplicationStep, ...]:
    """取り外し手順を閉じた形で解釈する。"""
    if not isinstance(value, list):
        raise AuthzApplicationStepsError("unapplication_stepsはarrayでなければならない")
    steps: list[ProductUnapplicationStep] = []
    for index in range(len(value)):
        raw_step = value[index]
        label = f"unapplication_steps[{index}]"
        if not isinstance(raw_step, dict):
            raise AuthzApplicationStepsError(f"{label}はobjectでなければならない")
        _require_exact_keys(
            raw_step,
            {
                "step_id",
                "sequence",
                "operation_kind",
                "reverses_application_step_id",
            },
            label,
        )
        steps.append(
            ProductUnapplicationStep(
                step_id=_require_string(raw_step["step_id"], f"{label}.step_id"),
                sequence=_require_sequence(raw_step["sequence"], f"{label}.sequence"),
                operation_kind=_require_string(
                    raw_step["operation_kind"], f"{label}.operation_kind"
                ),
                reverses_application_step_id=_require_string(
                    raw_step["reverses_application_step_id"],
                    f"{label}.reverses_application_step_id",
                ),
            )
        )
    return tuple(steps)


def _validate_element_coverage(
    ddl_elements: dict[str, object],
    application_steps: tuple[ProductApplicationStep, ...],
    spec: AuthzAssetSpec,
) -> None:
    """PRODUCT_SPEC の全要素を手順の要素群が一度ずつ覆うか検査する。"""
    expected_groups: set[str] = set()
    element_keys: set[tuple[str, str]] = set()
    pitchlog_owner_is_external = False
    for section in spec.element_sections:
        if section.section_name not in ddl_elements:
            raise AuthzApplicationStepsError(
                f"ddl-elements.{section.section_name}が存在しない"
            )
        raw_rows = ddl_elements[section.section_name]
        if not isinstance(raw_rows, list) or not raw_rows:
            raise AuthzApplicationStepsError(
                f"ddl-elements.{section.section_name}は空でないarrayでなければならない"
            )
        if section.section_name == "functions":
            for function_kind in _PRODUCT_FUNCTION_KINDS:
                expected_groups.add(f"functions:{function_kind}")
        else:
            expected_groups.add(section.section_name)
        for index in range(len(raw_rows)):
            raw_row = raw_rows[index]
            label = f"ddl-elements.{section.section_name}[{index}]"
            if not isinstance(raw_row, dict):
                raise AuthzApplicationStepsError(f"{label}はobjectでなければならない")
            element_id = _require_string(
                raw_row[section.id_field] if section.id_field in raw_row else None,
                f"{label}.{section.id_field}",
            )
            element_key = (section.element_type, element_id)
            if element_key in element_keys:
                raise AuthzApplicationStepsError(
                    f"PRODUCT_SPECの要素が重複している: {element_key}"
                )
            element_keys.add(element_key)
            if section.section_name == "functions":
                function_kind = _require_string(
                    raw_row["function_kind"] if "function_kind" in raw_row else None,
                    f"{label}.function_kind",
                )
                if function_kind not in _PRODUCT_FUNCTION_KINDS:
                    raise AuthzApplicationStepsError(
                        f"関数の要素群が未定義: {function_kind!r}"
                    )
            if section.section_name == "roles" and element_id == "pitchlog_owner":
                pitchlog_owner_is_external = (
                    raw_row["creation"] if "creation" in raw_row else None
                ) == "external_applicator"

    assigned_groups = tuple(
        group for step in application_steps for group in step.element_groups
    )
    if len(assigned_groups) != len(set(assigned_groups)):
        raise AuthzApplicationStepsError("要素群が複数の適用手順へ重複している")
    assigned_group_set = set(assigned_groups)
    if assigned_group_set != expected_groups:
        raise AuthzApplicationStepsError(
            "適用手順がPRODUCT_SPECの全要素を一度ずつ覆っていない: "
            f"不足={sorted(expected_groups - assigned_group_set)}, "
            f"過剰={sorted(assigned_group_set - expected_groups)}"
        )
    if not element_keys or not pitchlog_owner_is_external:
        raise AuthzApplicationStepsError(
            "PRODUCT_SPECの全要素または外部作成のpitchlog_ownerを確認できない"
        )


def validate_product_application_steps(
    asset: dict[str, object],
    ddl_elements: dict[str, object],
    spec: AuthzAssetSpec,
) -> ProductApplicationSteps:
    """製品認可の適用手順資産を静的契約へ照合する。

    Args:
        asset: ``application-steps.json`` の JSON object。
        ddl_elements: 製品の DDL 要素資産。
        spec: 製品資産の配置と要素セクション指定。

    Returns:
        検証済みで不変な適用・取り外し手順。

    Raises:
        AuthzApplicationStepsError: 手順、被覆、操作種別に不整合がある場合。
    """
    if spec.asset_kind != "product" or spec.application_steps_path is None:
        raise AuthzApplicationStepsError("製品の資産指定が必要")
    _require_exact_keys(
        asset,
        {
            "schema_version",
            "asset_kind",
            "transaction",
            "operation_kinds",
            "application_steps",
            "unapplication_steps",
            "preserved_role_ids",
        },
        "application-steps",
    )
    if asset["schema_version"] != 1 or isinstance(asset["schema_version"], bool):
        raise AuthzApplicationStepsError("schema_versionは1でなければならない")
    if asset["asset_kind"] != "authz_product_application_steps":
        raise AuthzApplicationStepsError("asset_kindが製品適用手順でない")
    transaction = _require_string(asset["transaction"], "transaction")
    if transaction != "single":
        raise AuthzApplicationStepsError("transactionはsingleでなければならない")

    operation_kinds = _require_string_tuple(asset["operation_kinds"], "operation_kinds")
    application_steps = _parse_application_steps(asset["application_steps"])
    unapplication_steps = _parse_unapplication_steps(asset["unapplication_steps"])
    preserved_role_ids = _require_string_tuple(
        asset["preserved_role_ids"], "preserved_role_ids"
    )

    expected_sequences = tuple(range(1, 8))
    if tuple(step.sequence for step in application_steps) != expected_sequences:
        raise AuthzApplicationStepsError("適用手順は1から7の連番でなければならない")
    if tuple(step.sequence for step in unapplication_steps) != expected_sequences:
        raise AuthzApplicationStepsError("取り外し手順は1から7の連番でなければならない")
    application_ids = tuple(step.step_id for step in application_steps)
    unapplication_ids = tuple(step.step_id for step in unapplication_steps)
    if len(application_ids) != len(set(application_ids)) or len(
        unapplication_ids
    ) != len(set(unapplication_ids)):
        raise AuthzApplicationStepsError(
            "適用・取り外しのstep_idは一意でなければならない"
        )
    _validate_element_coverage(ddl_elements, application_steps, spec)
    if tuple(step.element_groups for step in application_steps) != (
        _PRODUCT_APPLICATION_ELEMENT_GROUPS
    ):
        raise AuthzApplicationStepsError(
            "適用手順が補助関数をポリシーより先に置く固定順序と一致しない"
        )
    reversed_application_ids = tuple(
        step.step_id for step in reversed(application_steps)
    )
    if (
        tuple(step.reverses_application_step_id for step in unapplication_steps)
        != reversed_application_ids
    ):
        raise AuthzApplicationStepsError("取り外し手順が適用手順の逆順でない")
    if preserved_role_ids != ("pitchlog_owner",):
        raise AuthzApplicationStepsError(
            "取り外しではpitchlog_ownerだけを削除対象から保護しなければならない"
        )

    used_operation_kinds = tuple(
        step.operation_kind for step in application_steps
    ) + tuple(step.operation_kind for step in unapplication_steps)
    if operation_kinds != used_operation_kinds:
        raise AuthzApplicationStepsError(
            "operation_kindsは適用・取り外し手順の閉じた集合でなければならない"
        )
    probe_operation_kinds = {
        operation.operation_kind for operation in PROBE_SPEC.operation_handlers
    }
    overlap = set(operation_kinds) & probe_operation_kinds
    if overlap:
        raise AuthzApplicationStepsError(
            f"製品とprobeの操作種別が交差している: {sorted(overlap)}"
        )

    return ProductApplicationSteps(
        transaction=transaction,
        operation_kinds=operation_kinds,
        application_steps=application_steps,
        unapplication_steps=unapplication_steps,
        preserved_role_ids=preserved_role_ids,
    )


def load_product_application_steps(
    root: Path,
    spec: AuthzAssetSpec,
) -> ProductApplicationSteps:
    """正規の製品資産を読み、適用・取り外し手順を検証する。

    Args:
        root: リポジトリルート。
        spec: 製品資産の配置と要素セクション指定。

    Returns:
        検証済みで不変な適用・取り外し手順。

    Raises:
        AuthzApplicationStepsError: 資産を読めないか静的契約に反する場合。
    """
    if spec.asset_kind != "product" or spec.application_steps_path is None:
        raise AuthzApplicationStepsError("製品の資産指定が必要")
    asset = _read_json_object(root / spec.application_steps_path, "application-steps")
    ddl_elements = _read_json_object(root / spec.ddl_elements_path, "ddl-elements")
    return validate_product_application_steps(asset, ddl_elements, spec)


PROBE_SPEC = AuthzAssetSpec(
    asset_root=PurePosixPath("contracts/authz"),
    ddl_elements_path=PurePosixPath("contracts/authz/ddl-elements.json"),
    body_manifest_path=PurePosixPath("contracts/authz/function-bodies/manifest.json"),
    body_directory=PurePosixPath("contracts/authz/function-bodies"),
    body_checker_path=PurePosixPath("scripts/check_authz_function_bodies.py"),
    scope_field="scope",
    scope_status_field="status",
    allowed_scope_status="verified_probe_configuration",
    asset_kind="probe",
    element_sections=(
        AuthzElementSectionSpec("role", "roles", "role_id", position=0),
        AuthzElementSectionSpec("schema", "schemas", "schema_id", position=1),
        AuthzElementSectionSpec("table", "tables", "table_id", position=2),
        AuthzElementSectionSpec("predicate", "predicates", "predicate_id", position=3),
        AuthzElementSectionSpec("policy", "policies", "policy_id", position=4),
        AuthzElementSectionSpec("function", "functions", "function_id", position=5),
        AuthzElementSectionSpec(
            "acl_expectation",
            "acl_expectations",
            "acl_id",
            position=6,
        ),
        AuthzElementSectionSpec(
            "column_acl_expectation",
            "column_acl_expectations",
            "expectation_id",
            position=7,
        ),
    ),
    operation_handlers=(
        AuthzOperationHandlerSpec(
            "create_no_login_bypass_owner",
            "_create_roles",
        ),
        AuthzOperationHandlerSpec(
            "temporarily_grant_set_membership",
            "_open_set_path",
        ),
        AuthzOperationHandlerSpec(
            "create_and_assign_owned_objects",
            "_assign_objects",
        ),
        AuthzOperationHandlerSpec(
            "revoke_public_and_grant_named_execute",
            "_close_function_acl",
        ),
        AuthzOperationHandlerSpec(
            "revoke_temporary_membership",
            "_close_set_path",
        ),
    ),
)


PRODUCT_SPEC = AuthzAssetSpec(
    asset_root=PurePosixPath("contracts/authz/product"),
    ddl_elements_path=PurePosixPath("contracts/authz/product/ddl-elements.staged.json"),
    body_manifest_path=PurePosixPath(
        "contracts/authz/product/function-bodies/manifest.json"
    ),
    body_directory=PurePosixPath("contracts/authz/product/function-bodies"),
    body_checker_path=PurePosixPath("scripts/check_authz_function_bodies.py"),
    scope_field="scope",
    scope_status_field="status",
    allowed_scope_status="product_configuration",
    asset_kind="product",
    element_sections=(
        AuthzElementSectionSpec("role", "roles", "role_id", position=0),
        AuthzElementSectionSpec("database", "databases", "database_id", position=1),
        AuthzElementSectionSpec("schema", "schemas", "schema_id", position=2),
        AuthzElementSectionSpec("function", "functions", "function_id", position=3),
        AuthzElementSectionSpec("table", "tables", "table_id", position=4),
        AuthzElementSectionSpec("predicate", "predicates", "predicate_id", position=5),
        AuthzElementSectionSpec("policy", "policies", "policy_id", position=6),
        AuthzElementSectionSpec(
            "acl_expectation",
            "acl_expectations",
            "acl_id",
            position=7,
        ),
        AuthzElementSectionSpec(
            "column_acl_expectation",
            "column_acl_expectations",
            "expectation_id",
            position=8,
        ),
    ),
    operation_handlers=(),
    exact_scope_items=(
        ("status", "product_configuration"),
        ("product_schema", True),
    ),
    application_steps_path=PurePosixPath(
        "contracts/authz/product/application-steps.json"
    ),
)
