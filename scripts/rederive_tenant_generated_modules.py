"""tenant 境界の生成モジュールを正本資産から再導出する。

`contracts/tenant_boundary/repository-contract.json` と
`contracts/tenant_boundary/tenant-context-allowlist.json` を唯一の入力とし、
対応する生成モジュールの定数・タプルを機械的に描画する。手編集を避けるための
経路であり、値の意味や検査条件は持たない（突合は既存の試験が行う）。
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class GeneratedModule:
    """1 つの生成モジュールと資産の対応を表す。

    Attributes:
        asset: 正本資産のリポジトリ相対パス。
        module: 生成モジュールのリポジトリ相対パス。
        mapping: 資産内の値のパスからモジュール定数名への対応。
    """

    asset: str
    module: str
    mapping: tuple[tuple[str, str], ...]


REPOSITORY_CONTRACT = GeneratedModule(
    asset="contracts/tenant_boundary/repository-contract.json",
    module="backend/src/pitchlog/repositories/repository_contract.py",
    mapping=(
        ("schema_version", "SCHEMA_VERSION"),
        ("contract_revision", "CONTRACT_REVISION"),
        ("asset_kind", "ASSET_KIND"),
        ("canonicalization", "CANONICALIZATION"),
        ("source_digest", "SOURCE_DIGEST"),
        ("public_surface.repository_type", "REPOSITORY_TYPE"),
        ("public_surface.context_binding_entry", "CONTEXT_BINDING_ENTRY"),
        ("public_surface.cross_tenant_function_entry", "CROSS_TENANT_FUNCTION_ENTRY"),
        ("public_surface.operation_token_type", "OPERATION_TOKEN_TYPE"),
        ("public_surface.operation_result_type", "OPERATION_RESULT_TYPE"),
        (
            "public_surface.cross_tenant_function_registry",
            "CROSS_TENANT_FUNCTION_REGISTRY_SYMBOL",
        ),
        ("public_surface.transaction_scope_entry", "TRANSACTION_SCOPE_ENTRY"),
        ("public_surface.function_registration_type", "FUNCTION_REGISTRATION_TYPE"),
        ("public_surface.function_transaction_entry", "FUNCTION_TRANSACTION_ENTRY"),
        ("public_surface.function_operation_registry", "FUNCTION_OPERATION_REGISTRY"),
        ("executor.symbol", "EXECUTOR_SYMBOL"),
        ("executor.signature", "EXECUTOR_SIGNATURE"),
        ("function_executor.symbol", "FUNCTION_EXECUTOR_SYMBOL"),
        ("function_executor.signature", "FUNCTION_EXECUTOR_SIGNATURE"),
        ("return_contract.scalar_type_match", "SCALAR_TYPE_MATCH"),
        ("return_contract.container_type_match", "CONTAINER_TYPE_MATCH"),
        ("return_contract.allowed_dtos", "ALLOWED_DTOS"),
        ("return_contract.immutable_scalar_types", "IMMUTABLE_SCALAR_TYPES"),
        ("return_contract.immutable_container_grammar", "IMMUTABLE_CONTAINER_GRAMMAR"),
        ("return_contract.forbidden_types", "FORBIDDEN_TYPES"),
        ("operation_guards.canonical_table", "CANONICAL_TABLE"),
        ("operation_guards.update_identity", "UPDATE_IDENTITY"),
        ("operation_guards.update_bind_names", "UPDATE_BIND_NAMES"),
        ("operation_guards.tenant_primary_key_bind", "TENANT_PRIMARY_KEY_BIND"),
        ("operation_guards.row_lock", "ROW_LOCK"),
        ("operation_guards.unlocked_read", "UNLOCKED_READ"),
        ("operation_guards.sync_apply_scope", "SYNC_APPLY_SCOPE"),
        ("product_capability_ids", "PRODUCT_CAPABILITY_IDS"),
        ("product_operation_token_types", "PRODUCT_OPERATION_TOKEN_TYPES"),
        ("product_function_operation_ids", "PRODUCT_FUNCTION_OPERATION_IDS"),
        ("cross_tenant_functions", "CROSS_TENANT_FUNCTIONS"),
    ),
)

TENANT_CONTEXT_CONTRACT = GeneratedModule(
    asset="contracts/tenant_boundary/tenant-context-allowlist.json",
    module="backend/src/pitchlog/repositories/tenant_context_contract.py",
    mapping=(
        ("schema_version", "SCHEMA_VERSION"),
        ("contract_revision", "CONTRACT_REVISION"),
        ("asset_kind", "ASSET_KIND"),
        ("canonicalization", "CANONICALIZATION"),
        ("source_digest", "SOURCE_DIGEST"),
        ("constructor_symbol", "CONSTRUCTOR_SYMBOL"),
        ("forbidden_construction_symbols", "FORBIDDEN_CONSTRUCTION_SYMBOLS"),
        ("integrity_secret_symbol", "INTEGRITY_SECRET_SYMBOL"),
        ("integrity_secret_allowed_symbols", "INTEGRITY_SECRET_ALLOWED_SYMBOLS"),
        ("integrity_proof_factory_symbol", "INTEGRITY_PROOF_FACTORY_SYMBOL"),
        (
            "integrity_proof_factory_allowed_symbols",
            "INTEGRITY_PROOF_FACTORY_ALLOWED_SYMBOLS",
        ),
        ("issuance_capability_symbol", "ISSUANCE_CAPABILITY_SYMBOL"),
        ("issuance_capability_allowed_symbols", "ISSUANCE_CAPABILITY_ALLOWED_SYMBOLS"),
        ("issuance_entrypoint_symbol", "ISSUANCE_ENTRYPOINT_SYMBOL"),
        ("issuance_entrypoint_allowed_symbols", "ISSUANCE_ENTRYPOINT_ALLOWED_SYMBOLS"),
        ("allowed_test_modules", "ALLOWED_TEST_MODULES"),
        ("allowed_product_modules", "ALLOWED_PRODUCT_MODULES"),
    ),
)

GENERATED_MODULES = (REPOSITORY_CONTRACT, TENANT_CONTEXT_CONTRACT)


def _lookup(asset: dict[str, Any], dotted: str) -> Any:
    """資産のドット区切りパスをたどって値を返す。

    Args:
        asset: 正本資産。
        dotted: ``public_surface.repository_type`` 形式のパス。

    Returns:
        参照先の値。

    Raises:
        KeyError: パスが解決できない場合。
    """
    value: Any = asset
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(dotted)
        value = value[part]
    return value


def _render_value(value: Any, *, indent: int = 0) -> str:
    """値を Python リテラルへ描画する。

    Args:
        value: 文字列・整数・真偽値・文字列配列のいずれか。
        indent: 出力の基準インデント（0 は代入式の続き行）。

    Returns:
        Python リテラル文字列。
    """
    pad = " " * (indent + 4)
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        if not value:
            return "()"
        items = "".join(f"{pad}{_render_value(item, indent=indent + 4)},\n" for item in value)
        return "(\n" + items + " " * indent + ")"
    raise TypeError(f"未対応の値型: {type(value).__name__}")


def _assignment_name(node: ast.stmt) -> str | None:
    """代入文の対象名を返す。

    Args:
        node: モジュール直下の文。

    Returns:
        単純名への代入ならその名前、それ以外は ``None``。
    """
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
        if isinstance(target, ast.Name):
            return target.id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def render_module(asset: dict[str, Any], source: str, mapping: tuple[tuple[str, str], ...]) -> str:
    """資産から生成モジュール本文を描画する。

    Args:
        asset: 正本資産。
        source: 現在のモジュール本文。
        mapping: 資産パスから定数名への対応。

    Returns:
        定数を資産の値へ置き換えたモジュール本文。

    Raises:
        KeyError: 資産に必要なパスがない場合。
    """
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    replacements: list[tuple[int, int, str]] = []
    for node in tree.body:
        name = _assignment_name(node)
        if name is None:
            continue
        for dotted, constant in mapping:
            if constant != name:
                continue
            value = _lookup(asset, dotted)
            rendered_value = _render_value(value, indent=0)
            single = f"{name} = {rendered_value}"
            if "\n" not in rendered_value and len(single) <= 88:
                rendered = f"{single}\n"
            elif isinstance(value, str):
                chunks = [
                    value[index : index + 60] for index in range(0, len(value), 60)
                ]
                body = "".join(
                    f"    {json.dumps(chunk, ensure_ascii=False)}\n" for chunk in chunks
                )
                rendered = f"{name} = (\n{body})\n"
            else:
                rendered = f"{name} = {rendered_value}\n"
            replacements.append((node.lineno - 1, node.end_lineno - 1, rendered))
            break
    found = {name for _, _, text in replacements for name in [text.split(" = ", 1)[0]]}
    missing = {constant for _, constant in mapping} - found
    if missing:
        raise KeyError(f"生成モジュールに対応する定数がない: {sorted(missing)}")
    for start, end, rendered in sorted(replacements, reverse=True):
        lines[start : end + 1] = [rendered]
    return "".join(lines)


def rederive(
    root: Path,
    *,
    check: bool = False,
    specs: Sequence[GeneratedModule] = GENERATED_MODULES,
) -> list[str]:
    """生成モジュールを資産から再導出する。

    Args:
        root: リポジトリルート。
        check: 真なら書き換えず、差分のあるモジュール名だけを返す。
        specs: 対象の生成モジュール定義（既定は全対象）。

    Returns:
        更新（または差分のあった）モジュールのリポジトリ相対パス。

    Raises:
        KeyError: 資産と定数の対応が解決できない場合。
    """
    changed: list[str] = []
    for spec in specs:
        asset = json.loads((root / spec.asset).read_text(encoding="utf-8"))
        module_path = root / spec.module
        source = module_path.read_text(encoding="utf-8")
        rendered = render_module(asset, source, spec.mapping)
        if rendered == source:
            continue
        changed.append(spec.module)
        if not check:
            module_path.write_text(rendered, encoding="utf-8")
    return changed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解釈する。

    Args:
        argv: 引数列。``None`` は実プロセス。

    Returns:
        解釈済み引数。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--check",
        action="store_true",
        help="書き換えずに、資産と不一致のモジュールを表示して exit 1 を返す",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI を実行する。

    Args:
        argv: 引数列。``None`` は実プロセス。

    Returns:
        正常時 0、``--check`` で不一致なら 1。
    """
    args = parse_args(argv)
    changed = rederive(args.root.resolve(), check=args.check)
    for path in changed:
        print(path)
    if args.check and changed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
