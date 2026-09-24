"""認可 DDL ツールチェーンが読む資産一式を不変値で指定する。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

type AuthzAssetKind = Literal["probe", "product"]


@dataclass(frozen=True, slots=True)
class AuthzElementSectionSpec:
    """DDL 要素種別と資産セクションの対応を表す。"""

    element_type: str
    section_name: str
    id_field: str

    def __post_init__(self) -> None:
        """対応を構成する値が空でないことを保証する。"""
        if not self.element_type or not self.section_name or not self.id_field:
            raise ValueError("要素セクション指定の値は空にできない")


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
        if not self.element_sections:
            raise ValueError("要素セクション指定は空にできない")
        dimensions = (
            tuple(section.element_type for section in self.element_sections),
            tuple(section.section_name for section in self.element_sections),
            tuple(section.id_field for section in self.element_sections),
        )
        if any(len(values) != len(set(values)) for values in dimensions):
            raise ValueError("要素セクション指定の各次元は一意でなければならない")


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
        AuthzElementSectionSpec("role", "roles", "role_id"),
        AuthzElementSectionSpec("schema", "schemas", "schema_id"),
        AuthzElementSectionSpec("table", "tables", "table_id"),
        AuthzElementSectionSpec("predicate", "predicates", "predicate_id"),
        AuthzElementSectionSpec("policy", "policies", "policy_id"),
        AuthzElementSectionSpec("function", "functions", "function_id"),
        AuthzElementSectionSpec(
            "acl_expectation",
            "acl_expectations",
            "acl_id",
        ),
        AuthzElementSectionSpec(
            "column_acl_expectation",
            "column_acl_expectations",
            "expectation_id",
        ),
    ),
)
