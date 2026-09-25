"""認可 DDL ツールチェーンが読む資産一式を不変値で指定する。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
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

    def __post_init__(self) -> None:
        """パス・列挙・要素対応を fail-closed に検証する。"""
        repository_paths = (
            self.asset_root,
            self.ddl_elements_path,
            self.body_manifest_path,
            self.body_directory,
            self.body_checker_path,
        )
        for path in repository_paths:
            if path.is_absolute() or not path.parts or ".." in path.parts:
                raise ValueError(
                    f"資産パスは正規なリポジトリ相対パスでなければならない: {path}"
                )
        for path in (
            self.ddl_elements_path,
            self.body_manifest_path,
            self.body_directory,
        ):
            try:
                path.relative_to(self.asset_root)
            except ValueError as error:
                raise ValueError(
                    f"資産パスが資産ルート外を指している: {path}"
                ) from error
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
)
