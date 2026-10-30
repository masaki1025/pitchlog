"""Manifest と実在資産から BOOT の意味スナップショットを収集する。"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from pathlib import PurePosixPath
from typing import cast

from pitchlog.domaincheck.boot.operation_bindings import (
    PartialOperationBinding,
    validate_partial_bindings,
)
from pitchlog.domaincheck.boot.phase2 import SemanticSnapshot
from pitchlog.domaincheck.cli import CheckerExecutionError, CheckerViolation

CHECK_COMPONENTS = ("vector_checks", "property_checks", "mutation_checks")


def _object(value: object, label: str) -> dict[str, object]:
    """JSON object の形だけを受け取る。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CheckerExecutionError(f"{label}が JSON object でない")
    return cast(dict[str, object], value)


def _array(value: object, label: str) -> list[object]:
    """JSON array の形だけを受け取る。"""
    if not isinstance(value, list):
        raise CheckerExecutionError(f"{label}が JSON array でない")
    return cast(list[object], value)


def _path(value: object, label: str) -> str:
    """リポジトリ内の相対パスだけを受け取る。"""
    if not isinstance(value, str) or not value:
        raise CheckerExecutionError(f"{label}が空でないパスでない")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise CheckerExecutionError(f"{label}が安全な相対パスでない")
    return value


def _existing_paths(
    rows: object,
    field: str,
    label: str,
    path_exists: Callable[[str], bool],
) -> bool:
    """登録された参照先をすべて観測できるか調べる。"""
    all_exist = True
    for index, item in enumerate(_array(rows, label)):
        row = _object(item, f"{label}[{index}]")
        path = _path(row.get(field), f"{label}[{index}].{field}")
        try:
            if not path_exists(path):
                all_exist = False
        except OSError as error:
            raise CheckerExecutionError(f"参照資産を観測できない: {path}") from error
    return all_exist


def collect_semantic_snapshot(
    manifest: object | None,
    *,
    allowed_target_ids: Collection[str],
    path_exists: Callable[[str], bool],
    verified_checks: Mapping[str, frozenset[str]] | None = None,
    operation_bindings: tuple[PartialOperationBinding, ...] = (),
) -> SemanticSnapshot:
    """Manifest の六構成要素を対象 ID ごとに観測する。

    検査登録だけでは生の試験が緑だったことを証明できない。
    ``verified_checks`` がない層は ``None`` として判定不能にする。

    Args:
        manifest: 当該時点の検証済み manifest。不在は ``None``。
        allowed_target_ids: 封印集合が許す対象 ID。
        path_exists: 当該時点で参照先が実在するかを調べる関数。
        verified_checks: 実行済み検査で成功した対象 ID の層別集合。
        operation_bindings: 検証済みの有限な部分供給対応。

    Returns:
        六集合を持つ意味スナップショット。観測不能な集合は ``None``。

    Raises:
        CheckerExecutionError: Manifest の形やパスを解釈できない場合。
    """
    if manifest is None:
        return SemanticSnapshot.missing()
    root = _object(manifest, "manifest")
    calculations = _array(root.get("calculations"), "manifest.calculations")
    if not calculations:
        raise CheckerExecutionError("manifest.calculations が空である")
    declarations: set[str] = set()
    generated: set[str] = set()
    product_calls: set[str] = set()
    checks: dict[str, set[str]] = {key: set() for key in CHECK_COMPONENTS}
    observable = {
        "declarations": True,
        "generated": True,
        "product_calls": True,
        **{
            key: verified_checks is not None and key in verified_checks
            for key in CHECK_COMPONENTS
        },
    }
    seen: set[str] = set()
    allowed = frozenset(allowed_target_ids)
    validate_partial_bindings(operation_bindings, allowed)
    bindings = {binding.operation: binding for binding in operation_bindings}
    if len(bindings) != len(operation_bindings):
        raise CheckerViolation("BOOT operation bindingが重複")
    seen_targets: set[str] = set()
    for index, raw in enumerate(calculations):
        label = f"manifest.calculations[{index}]"
        calculation = _object(raw, label)
        operation = calculation.get("calculation")
        if not isinstance(operation, str) or not operation or operation in seen:
            raise CheckerExecutionError(f"{label}.calculation が不正または重複")
        binding = bindings.get(operation)
        target = binding.target_id if binding is not None else operation
        if target not in allowed:
            raise CheckerViolation(f"NFR-018 柱書: 対象欄にない宣言={target!r}")
        seen.add(operation)
        if target in seen_targets:
            raise CheckerViolation("BOOT同対象の部分供給と全体登録を混在できない")
        seen_targets.add(target)
        source = _object(calculation.get("source"), f"{label}.source")
        source_path = _path(source.get("path"), f"{label}.source.path")
        if binding is not None and source_path != binding.source:
            raise CheckerViolation("BOOT operation bindingのsourceが一致しない")
        if path_exists(source_path):
            declarations.add(target)
        else:
            observable["declarations"] = False

        artifacts = _array(calculation.get("generated"), f"{label}.generated")
        if artifacts:
            if _existing_paths(artifacts, "path", f"{label}.generated", path_exists):
                generated.add(target)
            else:
                observable["generated"] = False

        entrypoints = _array(calculation.get("entrypoints"), f"{label}.entrypoints")
        direct_targets = _array(
            calculation.get("directTargets"), f"{label}.directTargets"
        )
        entry_modules = _existing_paths(
            entrypoints, "module", f"{label}.entrypoints", path_exists
        )
        entry_adapters = _existing_paths(
            entrypoints, "adapter", f"{label}.entrypoints", path_exists
        )
        invocation_adapters = True
        for direct_index, direct in enumerate(direct_targets):
            item = _object(direct, f"{label}.directTargets[{direct_index}]")
            invocation = _object(item.get("invocation"), "invocation")
            adapter = _path(invocation.get("adapter"), "invocation.adapter")
            invocation_adapters = path_exists(adapter) and invocation_adapters
        if entrypoints and direct_targets:
            if entry_modules and entry_adapters and invocation_adapters:
                product_calls.add(target)
            else:
                observable["product_calls"] = False

        registrations = {
            "vector_checks": ("vectors", "path"),
            "property_checks": ("properties", "path"),
            "mutation_checks": ("mutation", "target"),
        }
        for component, (field, path_field) in registrations.items():
            rows = _array(calculation.get(field), f"{label}.{field}")
            if not rows:
                continue
            if not _existing_paths(rows, path_field, f"{label}.{field}", path_exists):
                observable[component] = False
            elif (
                observable[component]
                and verified_checks is not None
                and binding is None
                and target in verified_checks[component]
            ):
                checks[component].add(target)
    return SemanticSnapshot(
        declarations=frozenset(declarations) if observable["declarations"] else None,
        generated=frozenset(generated) if observable["generated"] else None,
        product_calls=frozenset(product_calls) if observable["product_calls"] else None,
        vector_checks=(
            frozenset(checks["vector_checks"]) if observable["vector_checks"] else None
        ),
        property_checks=(
            frozenset(checks["property_checks"])
            if observable["property_checks"]
            else None
        ),
        mutation_checks=(
            frozenset(checks["mutation_checks"])
            if observable["mutation_checks"]
            else None
        ),
    )


__all__ = ["collect_semantic_snapshot"]
