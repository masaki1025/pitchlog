"""認可要件主張母集合の全数採取と閉じた分類を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import itertools
import json
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_authz_catalog.py"
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "authz_claims"
DERIVED_ASSET_FILES = {
    "route_registry": "route-registry.json",
    "auth_catalog": "auth-catalog.json",
    "http_matrix": "http-route-matrix.json",
}
ORACLE_ASSET_FILES = {
    "ddl_elements": "ddl-elements.json",
    "rejected_configs": "rejected-configs.json",
    "claim_mutant_map": "claim-mutant-map.json",
    "attack_tree": "attack-tree.json",
    "boundary_proposal": "boundary-proposal.json",
    "verification_evidence": "verification-evidence.json",
}
ORACLE_SEAL_FILE = "oracle-seal.lock.json"
AUTHZ_STEP2_BASE_REVISION = "56c281c409e972927940fad830aa38352df32f1e"
IMPLEMENTED_CATALOG_TEST_ID = (
    "tests/test_check_authz_catalog.py::test_repository_derived_assets_are_valid"
)
IMPLEMENTED_ORACLE_TEST_ID = (
    "tests/test_check_authz_catalog.py::test_repository_oracle_assets_are_valid"
)


def _load_checker() -> Any:
    """テスト対象を sys.path の変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location("check_authz_catalog_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def _run_git(root: Path, *arguments: str) -> str:
    """一時repositoryでGitを実行し、成功時の標準出力を返す。"""
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _make_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    shutil.copytree(FIXTURE_ROOT, root)
    _run_git(root, "init", "--quiet")
    _run_git(root, "add", "--", "requirements.md")
    _run_git(
        root,
        "-c",
        "user.name=pitchlog tests",
        "-c",
        "user.email=pitchlog-tests@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "--message",
        "test: 入力要件書の履歴を作成",
    )
    catalog = _read_catalog(root)
    catalog["input_manifest"]["commit"] = _run_git(root, "rev-parse", "HEAD")
    _write_catalog(root, catalog)
    return root


def _read_catalog(root: Path) -> dict[str, Any]:
    raw = json.loads((root / "requirement-claims.json").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _read_lock(root: Path) -> dict[str, Any]:
    raw = json.loads((root / "requirement-claims.lock.json").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _write_catalog(root: Path, catalog: dict[str, Any]) -> None:
    (root / "requirement-claims.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_lock(root: Path, lock: dict[str, Any]) -> None:
    (root / "requirement-claims.lock.json").write_text(
        json.dumps(lock, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_requirements(root: Path, text: str) -> None:
    (root / "requirements.md").write_text(text, encoding="utf-8")


def _refresh_manifest(root: Path, *, update_headings: bool = True) -> None:
    """文書変異後の blob・構造件数を更新し、別の述語だけを攻撃する。"""
    path = root / "requirements.md"
    source = path.read_bytes()
    extraction = checker.extract_source(source.decode("utf-8"))
    catalog = _read_catalog(root)
    manifest = catalog["input_manifest"]
    manifest["source_blob_digest"] = checker.git_blob_digest(source)
    counts = Counter(item.kind for item in extraction.items)
    manifest["item_counts_by_kind"] = {
        kind: counts[kind] for kind in sorted(checker.SOURCE_KINDS)
    }
    if update_headings:
        manifest["heading_ids"] = list(extraction.heading_ids)
        manifest["scan_start_heading_id"] = extraction.heading_ids[0]
        manifest["scan_end_heading_id"] = extraction.heading_ids[-1]
    _write_catalog(root, catalog)


def _run_cli(root: Path, *, reseal: bool = False) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(SCRIPT),
        "--root",
        str(root),
        "--requirements",
        "requirements.md",
        "--claims",
        "requirement-claims.json",
        "--lock",
        "requirement-claims.lock.json",
        "--skip-derived",
        "--skip-oracle",
    ]
    if reseal:
        command.append("--reseal")
    return subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _read_repository_json(relative_path: str) -> dict[str, Any]:
    """リポジトリの JSON オブジェクトを読む。"""
    raw = json.loads((REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _repository_derived_assets() -> tuple[
    dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]
]:
    """ステップ4の3資産・3 lock・相対パスを読む。"""
    assets: dict[str, dict[str, Any]] = {}
    locks: dict[str, dict[str, Any]] = {}
    paths: dict[str, str] = {}
    for name, filename in DERIVED_ASSET_FILES.items():
        path = f"contracts/authz/{filename}"
        lock_path = f"contracts/authz/{filename.removesuffix('.json')}.lock.json"
        assets[name] = _read_repository_json(path)
        locks[name] = _read_repository_json(lock_path)
        paths[name] = path
    return assets, locks, paths


def _repository_oracle_assets() -> tuple[
    dict[str, dict[str, Any]], dict[str, Any], dict[str, str]
]:
    """ステップ5の6資産・oracle seal・相対パスを読む。"""
    assets: dict[str, dict[str, Any]] = {}
    paths: dict[str, str] = {}
    for name, filename in ORACLE_ASSET_FILES.items():
        path = f"contracts/authz/{filename}"
        assets[name] = _read_repository_json(path)
        paths[name] = path
    seal = _read_repository_json(f"contracts/authz/{ORACLE_SEAL_FILE}")
    return assets, seal, paths


class FrozenJsonMultiplicityError(AssertionError):
    """凍結 JSON のキーまたは配列要素の重複を表す。"""


ArrayPath = tuple[str | int, ...]
ArrayWalker = Callable[[object, ArrayPath], list[tuple[ArrayPath, list[Any]]]]
GDecision = tuple[str, ArrayPath, int, bool]
GDecisionRecorder = Callable[[], None]
GDecisionDispatcher = Callable[[str, ArrayPath, int, GDecisionRecorder], None]


def _base_json(relative_path: str) -> dict[str, Any]:
    """固定基準版の JSON オブジェクトを Git から読む。"""
    result = subprocess.run(
        ["git", "show", f"{AUTHZ_STEP2_BASE_REVISION}:{relative_path}"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert isinstance(value, dict)
    return value


@lru_cache(maxsize=1)
def _receiving_task_base_revision() -> str:
    """受取先置換の基準版を origin/develop と HEAD から導出する。"""
    result = subprocess.run(
        ["git", "merge-base", "origin/develop", "HEAD"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _receiving_task_revision_text(revision: str, relative_path: str) -> str:
    """受取先置換の指定スナップショットからファイル本文を読む。"""
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def _receiving_task_base_text(relative_path: str) -> str:
    """受取先置換の merge-base からファイル本文を読む。"""
    return _receiving_task_revision_text(
        _receiving_task_base_revision(), relative_path
    )


def _receiving_task_head_text(relative_path: str) -> str:
    """受取先置換の HEAD からファイル本文を読む。"""
    return _receiving_task_revision_text("HEAD", relative_path)


def _receiving_task_base_json(relative_path: str) -> dict[str, Any]:
    """受取先置換の merge-base から JSON オブジェクトを読む。"""
    value = json.loads(_receiving_task_base_text(relative_path))
    assert isinstance(value, dict)
    return value


def _receiving_task_head_json(relative_path: str) -> dict[str, Any]:
    """受取先置換の HEAD から JSON オブジェクトを読む。"""
    value = json.loads(_receiving_task_head_text(relative_path))
    assert isinstance(value, dict)
    return value


def _json_text(value: object) -> str:
    """テスト用 JSON 本文をリポジトリ資産と同じ体裁で返す。"""
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


@lru_cache(maxsize=1)
def _base_checker() -> ModuleType:
    """固定基準版の検査器を作業コピーから独立して読み込む。"""
    result = subprocess.run(
        [
            "git",
            "show",
            f"{AUTHZ_STEP2_BASE_REVISION}:scripts/check_authz_catalog.py",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    name = "check_authz_catalog_step2_base"
    module = ModuleType(name)
    module.__file__ = f"{AUTHZ_STEP2_BASE_REVISION}:scripts/check_authz_catalog.py"
    sys.modules[name] = module
    exec(compile(result.stdout, module.__file__, "exec"), module.__dict__)
    return module


def _base_frozen_asset_paths() -> tuple[str, ...]:
    """固定基準版の seal から凍結 15 パスを導出する。"""
    seal = _base_json(f"contracts/authz/{ORACLE_SEAL_FILE}")
    return _frozen_asset_paths_from_seal(seal)


def _frozen_asset_paths_from_seal(
    seal: dict[str, Any], *, include_seal: bool = True
) -> tuple[str, ...]:
    """seal の2資産区分と seal 自身から凍結対象パスを導く。"""
    paths = tuple(
        str(row["path"])
        for key in ("input_assets", "sealed_assets")
        for row in seal[key]
    )
    if include_seal:
        paths += (f"contracts/authz/{ORACLE_SEAL_FILE}",)
    assert len(paths) == len(set(paths))
    return paths


def _oracle_meaning_body(asset: dict[str, Any]) -> dict[str, Any]:
    """oracle資産から可動ポインタだけを除いた意味本文を返す。"""
    body = copy.deepcopy(asset)
    context = body["oracle_context"]
    assert isinstance(context, dict)
    oracle_commit = context.pop("oracle_commit")
    assert isinstance(oracle_commit, str) and oracle_commit
    return body


def _oracle_seal_meaning_body(seal: dict[str, Any]) -> dict[str, Any]:
    """sealから入力ポインタとポインタ由来digestだけを除いて返す。"""
    body = copy.deepcopy(seal)
    oracle_commit = body.pop("oracle_commit")
    assert isinstance(oracle_commit, str) and oracle_commit
    for row in body["input_assets"]:
        digest = row.pop("git_blob_digest")
        assert isinstance(digest, str) and digest
    for row in body["sealed_assets"]:
        digest = row.pop("canonical_sha256")
        assert isinstance(digest, str) and digest
    return body


def _git_object_id(arguments: list[str]) -> str:
    """repositoryでGitコマンドが返す単一object IDを取得する。"""
    result = subprocess.run(
        ["git", *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    object_id = result.stdout.strip()
    assert object_id
    return object_id


def _assert_oracle_input_baseline_matches_seal(seal: dict[str, Any]) -> None:
    """入力8資産の作業ツリー・基準commit・seal blobを三者照合する。"""
    oracle_commit = seal["oracle_commit"]
    assert isinstance(oracle_commit, str) and oracle_commit
    rows = seal["input_assets"]
    assert isinstance(rows, list)
    assert len(rows) == len({row["path"] for row in rows}) == 8
    for row in rows:
        path = row["path"]
        recorded = row["git_blob_digest"]
        assert _git_object_id(["hash-object", "--", path]) == recorded
        assert _git_object_id(["rev-parse", f"{oracle_commit}:{path}"]) == recorded


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """object_pairs_hook で解析前の重複キーを拒否する。"""
    keys = [key for key, _value in pairs]
    if len(keys) != len(set(keys)):
        raise FrozenJsonMultiplicityError("JSON オブジェクトのキーが重複している")
    return dict(pairs)


def _walk_json_arrays(
    value: object, path: ArrayPath = ()
) -> list[tuple[ArrayPath, list[Any]]]:
    """JSON の全分岐を再帰し、到達した配列とパスを返す。"""
    arrays: list[tuple[ArrayPath, list[Any]]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            arrays.extend(_walk_json_arrays(child, (*path, key)))
    elif isinstance(value, list):
        arrays.append((path, value))
        for index, child in enumerate(value):
            arrays.extend(_walk_json_arrays(child, (*path, index)))
    return arrays


def _independent_json_array_paths(value: object) -> set[ArrayPath]:
    """被検査走査と別の反復実装で全配列パスを列挙する。"""
    paths: set[ArrayPath] = set()
    pending: list[tuple[ArrayPath, object]] = [((), value)]
    while pending:
        path, current = pending.pop()
        if isinstance(current, list):
            paths.add(path)
            pending.extend(
                ((*path, index), child) for index, child in enumerate(current)
            )
        elif isinstance(current, dict):
            pending.extend(
                ((*path, key), child) for key, child in current.items()
            )
    return paths


def _validate_frozen_json_text(
    text: str,
    array_walker: ArrayWalker = _walk_json_arrays,
) -> set[ArrayPath]:
    """1 JSON の全キー対・全配列を多重度と到達範囲込みで検査する。"""
    value = json.loads(text, object_pairs_hook=_strict_json_object)
    arrays = array_walker(value, ())
    reached = {path for path, _array in arrays}
    independent = _independent_json_array_paths(json.loads(text))
    if reached != independent:
        raise FrozenJsonMultiplicityError("配列パスの到達集合が独立走査と不一致")
    for path, array in arrays:
        signatures = [
            json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for item in array
        ]
        if len(signatures) != len(set(signatures)):
            raise FrozenJsonMultiplicityError(f"配列要素が重複している: {path}")
    return reached


def _validate_frozen_asset_set(root: Path, relative_paths: tuple[str, ...]) -> int:
    """同じ入口から対象 JSON 全件の多重度を検査する。"""
    return sum(
        len(
            _validate_frozen_json_text(
                (root / relative_path).read_text(encoding="utf-8")
            )
        )
        for relative_path in relative_paths
    )


def _copy_frozen_assets(tmp_path: Path) -> Path:
    """実資産を変えずに負例を作るため凍結 15 パスを複製する。"""
    root = tmp_path / "frozen-assets"
    for relative_path in _base_frozen_asset_paths():
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT / relative_path, destination)
    return root


def _duplicate_array_element(
    value: dict[str, Any], path: ArrayPath, index: int
) -> dict[str, Any]:
    """指定配列の要素を直後へ複製した深いコピーを返す。"""
    mutated = copy.deepcopy(value)
    target: object = mutated
    for part in path:
        if isinstance(target, dict):
            assert isinstance(part, str)
            target = target[part]
        else:
            assert isinstance(target, list) and isinstance(part, int)
            target = target[part]
    assert isinstance(target, list)
    target.insert(index + 1, copy.deepcopy(target[index]))
    return mutated


def _g_entry_partition_from_seal(
    seal: dict[str, Any],
) -> tuple[frozenset[str], frozenset[str]]:
    """seal の資産行の型から g の対象入口と対象外入力を分ける。"""
    seal_path = f"contracts/authz/{ORACLE_SEAL_FILE}"
    included = {seal_path}
    excluded: set[str] = set()
    asset_tables = [
        value
        for value in seal.values()
        if isinstance(value, list)
        and value
        and all(isinstance(row, dict) and "path" in row for row in value)
    ]
    assert asset_tables
    for rows in asset_tables:
        for row in rows:
            assert isinstance(row, dict)
            path = str(row["path"])
            is_semantic_asset = {
                "asset_kind",
                "asset_role",
                "canonical_sha256",
            } <= set(row)
            is_input_asset = set(row) == {"path", "git_blob_digest"}
            assert is_semantic_asset is not is_input_asset
            (included if is_semantic_asset else excluded).add(path)

    frozen_paths = frozenset(_frozen_asset_paths_from_seal(seal))
    assert included.isdisjoint(excluded)
    assert included | excluded == frozen_paths
    return frozenset(included), frozenset(excluded)


def _record_g_decision(
    _entry_path: str,
    _array_path: ArrayPath,
    _index: int,
    validate_and_record: GDecisionRecorder,
) -> None:
    """通常経路では validator の実行と判定記録を省略しない。"""
    validate_and_record()


def _derive_g_multiplicity_with_dispatcher(
    dispatch: GDecisionDispatcher,
) -> tuple[tuple[tuple[str, ArrayPath], ...], tuple[GDecision, ...]]:
    """固定基準版へ g を実行し、出力と validator の判定証跡を返す。"""
    base_checker = _base_checker()
    seal_path = f"contracts/authz/{ORACLE_SEAL_FILE}"
    seal = _base_json(seal_path)
    names_by_path = {
        f"contracts/authz/{filename}": name
        for name, filename in ORACLE_ASSET_FILES.items()
    }
    sealed_paths = tuple(str(row["path"]) for row in seal["sealed_assets"])
    assert len(sealed_paths) == len(set(sealed_paths))
    assert set(sealed_paths) == set(names_by_path)
    assets = {
        names_by_path[path]: _base_json(path)
        for path in sealed_paths
    }
    paths = {names_by_path[path]: path for path in sealed_paths}
    requirement_catalog = _base_json("contracts/authz/requirement-claims.json")
    route_registry = _base_json("contracts/authz/route-registry.json")
    auth_catalog = _base_json("contracts/authz/auth-catalog.json")
    http_matrix = _base_json("contracts/authz/http-route-matrix.json")
    implemented_test_ids = frozenset(
        {IMPLEMENTED_CATALOG_TEST_ID, IMPLEMENTED_ORACLE_TEST_ID}
    )
    decisions: list[GDecision] = []

    def dispatch_asset_mutation(
        name: str,
        path: ArrayPath,
        index: int,
        outcomes: list[bool],
    ) -> None:
        entry_path = paths[name]

        def validate_and_record() -> None:
            mutated_assets = dict(assets)
            mutated_assets[name] = _duplicate_array_element(
                assets[name], path, index
            )
            try:
                base_checker.validate_oracle_assets(
                    requirement_catalog,
                    route_registry,
                    auth_catalog,
                    http_matrix,
                    mutated_assets,
                    seal,
                    paths,
                    REPOSITORY_ROOT,
                    implemented_test_ids,
                    verify_seal=False,
                )
            except base_checker.CatalogError:
                green = False
            else:
                green = True
            decisions.append((entry_path, path, index, green))
            outcomes.append(green)

        dispatch(entry_path, path, index, validate_and_record)

    output: list[tuple[str, ArrayPath]] = []
    for relative_path in sealed_paths:
        name = names_by_path[relative_path]
        for path, array in _walk_json_arrays(assets[name]):
            outcomes: list[bool] = []
            for index in range(len(array)):
                dispatch_asset_mutation(name, path, index, outcomes)
            if any(outcomes):
                output.append((name, path))

    for path, array in _walk_json_arrays(seal):
        outcomes: list[bool] = []
        for index in range(len(array)):
            mutated = _duplicate_array_element(seal, path, index)

            def validate_and_record(
                *,
                mutated: dict[str, Any] = mutated,
                path: ArrayPath = path,
                index: int = index,
            ) -> None:
                try:
                    base_checker.validate_oracle_seal(
                        mutated, assets, paths, REPOSITORY_ROOT
                    )
                except base_checker.CatalogError:
                    green = False
                else:
                    green = True
                decisions.append((seal_path, path, index, green))
                outcomes.append(green)

            dispatch(seal_path, path, index, validate_and_record)
        if any(outcomes):
            output.append(("oracle_seal", path))

    return tuple(output), tuple(decisions)


@lru_cache(maxsize=1)
def _derive_g_multiplicity() -> tuple[
    tuple[tuple[str, ArrayPath], ...], tuple[GDecision, ...]
]:
    """通常の判定実行器で固定基準版の g を導出する。"""
    return _derive_g_multiplicity_with_dispatcher(_record_g_decision)


def _derive_g_multiplicity_array_paths() -> tuple[tuple[str, ArrayPath], ...]:
    """g が出力した配列パスだけを返す。"""
    return _derive_g_multiplicity()[0]


def _assert_g_entry_population(
    actual: frozenset[str], seal: dict[str, Any]
) -> None:
    """実測入口を seal の資産区分から導出した期待集合と突合する。"""
    expected, excluded = _g_entry_partition_from_seal(seal)
    assert actual == expected, (
        "g の入口集合が不一致: "
        f"不足={sorted(expected - actual)}, 余分={sorted(actual - expected)}"
    )
    assert actual.isdisjoint(excluded)


def _expected_g_decision_counts(seal: dict[str, Any]) -> Counter[str]:
    """各入口の期待判定数を、その BASE 資産の配列要素数から導出する。"""
    included, _excluded = _g_entry_partition_from_seal(seal)
    return Counter(
        {
            entry_path: sum(
                len(array)
                for _path, array in _walk_json_arrays(_base_json(entry_path))
            )
            for entry_path in included
        }
    )


def _expected_g_decision_keys(
    seal: dict[str, Any],
) -> frozenset[tuple[str, ArrayPath, int]]:
    """各入口で判定すべき全要素を BASE 資産から導出する。"""
    included, _excluded = _g_entry_partition_from_seal(seal)
    return frozenset(
        (entry_path, path, index)
        for entry_path in included
        for path, array in _walk_json_arrays(_base_json(entry_path))
        for index in range(len(array))
    )


def _actual_g_decision_counts(decisions: tuple[GDecision, ...]) -> Counter[str]:
    """validator が判定を返した要素だけを入口別に数える。"""
    return Counter(entry_path for entry_path, _path, _index, _green in decisions)


def _assert_g_decision_counts(
    actual: Counter[str], expected: Counter[str]
) -> None:
    """入口別の実判定数を資産由来の期待数と突合する。"""
    assert actual == expected, (
        "g の入口別判定件数が不一致: "
        f"不足={dict(expected - actual)}, 余分={dict(actual - expected)}"
    )


def _container_metrics(value: object, depth: int = 0) -> tuple[int, int]:
    """JSON コンテナの最大幅と最大深さを返す。"""
    if not isinstance(value, dict | list):
        return 0, depth
    width = len(value)
    maximum_depth = depth + 1
    children = value.values() if isinstance(value, dict) else value
    for child in children:
        child_width, child_depth = _container_metrics(child, depth + 1)
        width = max(width, child_width)
        maximum_depth = max(maximum_depth, child_depth)
    return width, maximum_depth


def _frozen_container_limits() -> tuple[int, int]:
    """固定基準版の凍結資産から探針の幅 w と深さ d を導出する。"""
    metrics = [
        _container_metrics(_base_json(relative_path))
        for relative_path in _base_frozen_asset_paths()
    ]
    return max(width for width, _depth in metrics), max(
        depth for _width, depth in metrics
    )


def _wrap_with_wide_container(
    sequence: tuple[str, ...],
    widened_index: int,
    value: object,
    width: int,
) -> object:
    """型列の指定段だけを幅 w にし、全兄弟へ同じ探針を置く。"""
    assert 0 <= widened_index < len(sequence)

    def wrap(index: int) -> object:
        if index == len(sequence):
            return copy.deepcopy(value)
        child = wrap(index + 1)
        if index != widened_index:
            return {"branch": child} if sequence[index] == "dict" else [child]
        if sequence[index] == "dict":
            return {
                f"branch_{sibling}": copy.deepcopy(child)
                for sibling in range(width)
            }
        return [copy.deepcopy(child) for _sibling in range(width)]

    return wrap(0)


def _iter_matching_key_paths(
    value: object, path: ArrayPath = ()
) -> list[ArrayPath]:
    """owner または task_id を含む全キーのパスを再帰導出する。"""
    matches: list[ArrayPath] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, key)
            if "owner" in key or "task_id" in key:
                matches.append(child_path)
            matches.extend(_iter_matching_key_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(_iter_matching_key_paths(child, (*path, index)))
    return matches


def _iter_leaf_paths(
    value: object, path: tuple[str | int, ...] = ()
) -> list[tuple[str | int, ...]]:
    """JSON を再帰走査し、空コンテナを含む全葉のパスを返す。"""
    if isinstance(value, dict):
        if not value:
            return [path]
        paths: list[tuple[str | int, ...]] = []
        for key, child in value.items():
            paths.extend(_iter_leaf_paths(child, (*path, key)))
        return paths
    if isinstance(value, list):
        if not value:
            return [path]
        paths = []
        for index, child in enumerate(value):
            paths.extend(_iter_leaf_paths(child, (*path, index)))
        return paths
    return [path]


def _parent_and_key(
    value: object, path: tuple[str | int, ...]
) -> tuple[dict[str, Any] | list[Any], str | int]:
    """葉の親コンテナとキーを返す。"""
    assert path
    current: object = value
    for part in path[:-1]:
        if isinstance(current, dict):
            assert isinstance(part, str)
            current = current[part]
        else:
            assert isinstance(current, list) and isinstance(part, int)
            current = current[part]
    assert isinstance(current, dict | list)
    return current, path[-1]


def _value_at_path(value: object, path: tuple[str | int, ...]) -> object:
    """JSON パスが指す値を型安全に返す。"""
    current = value
    for part in path:
        if isinstance(current, dict):
            assert isinstance(part, str)
            current = current[part]
        else:
            assert isinstance(current, list) and isinstance(part, int)
            current = current[part]
    return current


def _changed_leaf_value(value: object) -> object:
    """JSON の型を可能な限り保って葉値を壊す。"""
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        return value + ":MUTATED"
    if isinstance(value, list):
        assert not value
        return ["MUTATED"]
    if isinstance(value, dict):
        assert not value
        return {"MUTATED": True}
    assert value is None
    return "MUTATED"


def _mutate_leaf(
    value: dict[str, Any], path: tuple[str | int, ...], *, delete: bool
) -> dict[str, Any]:
    """指定葉を値改変または削除した深いコピーを返す。"""
    mutated = copy.deepcopy(value)
    parent, key = _parent_and_key(mutated, path)
    if delete:
        if isinstance(parent, dict):
            assert isinstance(key, str)
            del parent[key]
        else:
            assert isinstance(key, int)
            parent.pop(key)
    else:
        if isinstance(parent, dict):
            assert isinstance(key, str)
            parent[key] = _changed_leaf_value(parent[key])
        else:
            assert isinstance(key, int)
            parent[key] = _changed_leaf_value(parent[key])
    return mutated


def _auth_claim(catalog: dict[str, Any]) -> dict[str, Any]:
    return next(
        claim
        for claim in catalog["claims"]
        if claim["source_id"] == "FR-900/list_item-001"
    )


def _repository_catalog_and_lock() -> tuple[dict[str, Any], dict[str, Any]]:
    catalog = json.loads(
        (REPOSITORY_ROOT / "contracts/authz/requirement-claims.json").read_text(
            encoding="utf-8"
        )
    )
    lock = json.loads(
        (REPOSITORY_ROOT / "contracts/authz/requirement-claims.lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(catalog, dict)
    assert isinstance(lock, dict)
    return catalog, lock


def _auth_decision_units(
    catalog: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any], str]]:
    """非分割行と全 atomic claim を認可判定単位として列挙する。"""
    units: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for claim in catalog["claims"]:
        if claim["classification"] != "auth_claim":
            continue
        atomic_claims = claim.get("atomic_claims")
        if isinstance(atomic_claims, list):
            units.extend(
                (claim, atomic_claim, atomic_claim["atomic_id"])
                for atomic_claim in atomic_claims
            )
        else:
            units.append((claim, claim, claim["source_id"]))
    return units


def _decision_unit(claim: dict[str, Any], unit_id: str) -> dict[str, Any]:
    """親行を復元した後の認可判定単位を ID で再取得する。"""
    if claim["source_id"] == unit_id:
        return claim
    return next(
        atomic_claim
        for atomic_claim in claim["atomic_claims"]
        if atomic_claim["atomic_id"] == unit_id
    )


def _refresh_decision_digest(claim: dict[str, Any]) -> None:
    """変異側も行 digest を更新し、別 lock だけを防御線にする。"""
    claim["decision_digest"] = checker.compute_decision_digest(claim)


def _assert_lock_rejects(
    catalog: dict[str, Any], lock: dict[str, Any], source_id: str
) -> None:
    differences = checker.decision_lock_differences(catalog, lock)
    assert differences, source_id
    assert any(difference.startswith(f"{source_id}:") for difference in differences)


def test_repository_catalog_covers_the_entire_requirements_file() -> None:
    derived_locks_before = {
        path: (REPOSITORY_ROOT / path).read_bytes()
        for path in (
            "contracts/authz/route-registry.lock.json",
            "contracts/authz/auth-catalog.lock.json",
            "contracts/authz/http-route-matrix.lock.json",
        )
    }
    oracle_seal_path = "contracts/authz/oracle-seal.lock.json"
    oracle_seal_before = (REPOSITORY_ROOT / oracle_seal_path).read_bytes()
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "total=1083 auth_claim=184 out_of_scope=899" in result.stdout
    assert {
        path: (REPOSITORY_ROOT / path).read_bytes() for path in derived_locks_before
    } == derived_locks_before
    assert (REPOSITORY_ROOT / oracle_seal_path).read_bytes() == oracle_seal_before


def test_fixture_has_a_valid_multi_layer_claim(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    catalog = _read_catalog(root)
    claim = _auth_claim(catalog)

    assert [decision["location"] for decision in claim["decidable_at"]] == ["db", "http"]
    assert all(decision["test_owner"]["status"] == "planned" for decision in claim["decidable_at"])
    assert _run_cli(root).returncode == 0


def test_oracle_seal_is_red_when_rev_parse_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """oracle commit 上の入力blobを解決できなければredにする。"""
    assets, seal, paths = _repository_oracle_assets()
    target_path = seal["input_assets"][0]["path"]

    def fail_rev_parse(
        command: list[str], **_kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        assert command == [
            "git",
            "rev-parse",
            f"{seal['oracle_commit']}:{target_path}",
        ]
        return subprocess.CompletedProcess(
            command,
            128,
            stdout="",
            stderr="fatal: oracle input blob is unavailable\n",
        )

    monkeypatch.setattr(checker.subprocess, "run", fail_rev_parse)

    with pytest.raises(checker.CatalogError) as captured:
        checker.validate_oracle_seal(seal, assets, paths, REPOSITORY_ROOT)

    assert target_path in str(captured.value)
    assert "fatal: oracle input blob is unavailable" in str(captured.value)


def test_oracle_seal_is_red_without_git_history(tmp_path: Path) -> None:
    """oracle sealの履歴照合は.git不在をredにする。"""
    assets, seal, paths = _repository_oracle_assets()
    root = tmp_path / "repository"
    for row in seal["input_assets"]:
        source = REPOSITORY_ROOT / row["path"]
        destination = root / row["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    target_path = seal["input_assets"][0]["path"]

    with pytest.raises(checker.CatalogError) as captured:
        checker.validate_oracle_seal(seal, assets, paths, root)

    assert target_path in str(captured.value)
    assert "git repository がない" in str(captured.value)
    assert "git stderr: <stderr なし>" in str(captured.value)


def test_manifest_commit_is_red_without_git_history(tmp_path: Path) -> None:
    """input manifestの履歴照合は.git不在をredにする。"""
    commit = "a" * 40
    source_path = "requirements.md"
    raw = {"input_manifest": {"commit": commit, "source_path": source_path}}

    with pytest.raises(checker.CatalogError) as captured:
        checker._verify_manifest_commit(tmp_path, raw)

    assert commit in str(captured.value)
    assert source_path in str(captured.value)
    assert "git repository がない" in str(captured.value)
    assert "git stderr: <stderr なし>" in str(captured.value)


def test_manifest_commit_is_red_when_cat_file_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """input commitを取得できなければredにする。"""
    commit = "a" * 40
    source_path = "requirements.md"
    raw = {"input_manifest": {"commit": commit, "source_path": source_path}}
    (tmp_path / ".git").mkdir()

    def fail_cat_file(
        command: list[str], **_kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        assert command == ["git", "cat-file", "-e", f"{commit}^{{commit}}"]
        return subprocess.CompletedProcess(
            command,
            128,
            stdout="",
            stderr="fatal: input commit is unavailable\n",
        )

    monkeypatch.setattr(checker.subprocess, "run", fail_cat_file)

    with pytest.raises(checker.CatalogError) as captured:
        checker._verify_manifest_commit(tmp_path, raw)

    assert commit in str(captured.value)
    assert source_path in str(captured.value)
    assert "fatal: input commit is unavailable" in str(captured.value)


def test_indented_table_rows_are_extracted_by_kind() -> None:
    path = FIXTURE_ROOT / "indented-tables.md"
    source_text = path.read_text(encoding="utf-8")
    source_lines = [line for line in source_text.splitlines() if line]
    indents = (" ", "    ", "\t")
    expected_kinds = ("table_header", "table_delimiter", "table_row")

    assert [line[: line.index("|")] for line in source_lines] == [
        indent for indent in indents for _ in expected_kinds
    ]

    items = checker.extract_source(source_text).items

    assert [item.kind for item in items] == [
        kind for _ in indents for kind in expected_kinds
    ]
    assert [item.text for item in items] == source_lines


def test_mutation_1_deleted_known_clause_is_red(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    text = (root / "requirements.md").read_text(encoding="utf-8")
    line = "- Given 一般利用者 / When 管理画面を開く / Then 管理者のみが閲覧できる\n"
    assert line in text
    _write_requirements(root, text.replace(line, "", 1))
    _refresh_manifest(root)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "exact-set 不一致" in result.stderr


def test_mutation_2_unregistered_authorization_clause_is_red(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    text = (root / "requirements.md").read_text(encoding="utf-8")
    marker = "| 資源 | 読める者 |\n"
    inserted = "- Given 監査担当 / When 設定を開く / Then 管理者のみが操作できる\n\n"
    assert marker in text
    _write_requirements(root, text.replace(marker, inserted + marker, 1))
    _refresh_manifest(root)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "exact-set 不一致" in result.stderr


def test_mutation_3_added_table_row_is_red(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    text = (root / "requirements.md").read_text(encoding="utf-8")
    marker = "| 監査ログ | 管理者 |\n"
    assert marker in text
    _write_requirements(root, text.replace(marker, marker + "| 秘密設定 | 管理者 |\n", 1))
    _refresh_manifest(root)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "exact-set 不一致" in result.stderr


def test_mutation_4_added_layer_without_test_owner_is_red(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    catalog = _read_catalog(root)
    _auth_claim(catalog)["decidable_at"].append({"location": "cache"})
    _write_catalog(root, catalog)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "キー不一致" in result.stderr


def test_mutation_5_auth_claim_moved_to_out_of_scope_is_red(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    catalog = _read_catalog(root)
    claim = _auth_claim(catalog)
    claim["classification"] = "out_of_scope"
    claim["classification_rule_id"] = "OUT_NON_AUTH_REQUIREMENT"
    del claim["layer"]
    del claim["decidable_at"]
    _write_catalog(root, catalog)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "適用できない" in result.stderr or "対象外にできない" in result.stderr


def test_mutation_6_deleted_whole_section_is_red_by_heading_manifest(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    text = (root / "requirements.md").read_text(encoding="utf-8")
    start = text.index("## 1. 認可")
    end = text.index("## 2. 一般機能")
    _write_requirements(root, text[:start] + text[end:])
    _refresh_manifest(root, update_headings=False)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "走査見出し集合が不一致" in result.stderr


def test_additional_mutation_unregistered_plain_paragraph_is_red(tmp_path: Path) -> None:
    """指定3種以外の通常段落も全数採取する。"""
    root = _make_repository(tmp_path)
    text = (root / "requirements.md").read_text(encoding="utf-8")
    marker = "## 2. 一般機能\n"
    assert marker in text
    mutated = text.replace(marker, "認可対象は監査ログ全件である。\n\n" + marker, 1)
    _write_requirements(root, mutated)
    _refresh_manifest(root)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "exact-set 不一致" in result.stderr


def test_missing_classification_is_red(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    catalog = _read_catalog(root)
    del _auth_claim(catalog)["classification"]
    _write_catalog(root, catalog)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "classification が閉じた値域にない" in result.stderr


def test_free_form_classification_reason_is_red(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    catalog = _read_catalog(root)
    claim = next(claim for claim in catalog["claims"] if claim["classification"] == "out_of_scope")
    claim["classification_rule_id"] = "今回は対象外と判断"
    _write_catalog(root, catalog)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "未知の classification_rule_id" in result.stderr


def test_empty_auth_rule_applicability_is_red(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    catalog = _read_catalog(root)
    invalid_rule = json.loads(
        (FIXTURE_ROOT / "empty-auth-rule.json").read_text(encoding="utf-8")
    )
    catalog["classification_rules"]["AUTH_ACCESS_SCOPE"] = invalid_rule
    _write_catalog(root, catalog)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "AUTH 分類規則は適用条件を少なくとも1つ持たねばならない" in result.stderr


def test_invalid_closed_world_declarations_are_red(tmp_path: Path) -> None:
    cases = json.loads(
        (FIXTURE_ROOT / "invalid-closed-world.json").read_text(encoding="utf-8")
    )
    expected_errors = {
        "missing_member": "closed_world.member_source_ids と claims の exact-set 不一致",
        "empty_universe": "closed_world.member_source_ids は空にできない",
        "unknown_universe_kind": "closed_world.universe_kind が閉じた値域にない",
    }
    failures: list[tuple[str, int, str]] = []

    for case_name, closed_world in cases.items():
        root = _make_repository(tmp_path / case_name)
        catalog = _read_catalog(root)
        claim = _auth_claim(catalog)
        claim["closed_world"] = closed_world
        claim["decision_digest"] = checker.compute_decision_digest(claim)
        _write_catalog(root, catalog)

        result = _run_cli(root)
        if result.returncode != 1 or expected_errors[case_name] not in result.stderr:
            failures.append((case_name, result.returncode, result.stderr))

    assert failures == []


def test_scalar_decidable_at_is_red(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    catalog = _read_catalog(root)
    _auth_claim(catalog)["decidable_at"] = "db"
    _write_catalog(root, catalog)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "decidable_at は空でない配列" in result.stderr


def test_missing_layer_is_red(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    catalog = _read_catalog(root)
    del _auth_claim(catalog)["layer"]
    _write_catalog(root, catalog)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "キー不一致" in result.stderr


def test_line_number_based_stable_id_is_red(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    catalog = _read_catalog(root)
    _auth_claim(catalog)["source_id"] = "FR-900/REQ:7"
    _write_catalog(root, catalog)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "安定 ID に REQ:<行番号>" in result.stderr


def test_source_text_digest_drift_is_red(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    catalog = _read_catalog(root)
    _auth_claim(catalog)["source_text_digest"] = "0" * 64
    _write_catalog(root, catalog)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "source_text_digest が原文と一致しない" in result.stderr


def test_source_blob_digest_drift_is_red(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    text = (root / "requirements.md").read_text(encoding="utf-8")
    _write_requirements(root, text + "\n")

    result = _run_cli(root)

    assert result.returncode == 1
    assert "source blob digest が不一致" in result.stderr


def test_manifest_start_and_end_must_match_closed_heading_set(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    catalog = _read_catalog(root)
    catalog["input_manifest"]["scan_start_heading_id"] = "SECTION-1"
    _write_catalog(root, catalog)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "scan_start_heading_id" in result.stderr


def test_all_auth_claims_moved_to_each_out_rule_are_red() -> None:
    """全認可判定単位と全 OUT 規則の直積で分類決定を守る。"""
    catalog, lock = _repository_catalog_and_lock()
    decision_units = _auth_decision_units(catalog)
    out_rule_ids = sorted(
        rule_id
        for rule_id, rule in catalog["classification_rules"].items()
        if rule["classification"] == "out_of_scope"
    )
    escaped: list[tuple[str, str]] = []
    attempts = 0
    for claim, _unit, unit_id in decision_units:
        original = copy.deepcopy(claim)
        for out_rule_id in out_rule_ids:
            claim.clear()
            claim.update(copy.deepcopy(original))
            unit = _decision_unit(claim, unit_id)
            unit["classification"] = "out_of_scope"
            unit["classification_rule_id"] = out_rule_id
            if unit is claim:
                del unit["layer"]
                del unit["decidable_at"]
            _refresh_decision_digest(claim)
            differences = checker.decision_lock_differences(catalog, lock)
            if not any(
                difference.startswith(f"{claim['source_id']}:")
                for difference in differences
            ):
                escaped.append((unit_id, out_rule_id))
            attempts += 1
        claim.clear()
        claim.update(original)

    assert attempts == len(decision_units) * len(out_rule_ids)
    assert escaped == []


def test_all_decidable_locations_removed_one_at_a_time_are_red() -> None:
    """全認可判定単位の db/http/cache ロケーションを守る。"""
    catalog, lock = _repository_catalog_and_lock()
    decision_units = _auth_decision_units(catalog)
    expected_attempts = Counter(
        decision["location"]
        for _claim, unit, _unit_id in decision_units
        for decision in unit["decidable_at"]
    )
    escaped: list[tuple[str, str]] = []
    attempts = Counter[str]()
    for claim, unit, unit_id in decision_units:
        original = copy.deepcopy(claim)
        original_unit = _decision_unit(original, unit_id)
        for decision in original_unit["decidable_at"]:
            location = decision["location"]
            claim.clear()
            claim.update(copy.deepcopy(original))
            mutated_unit = _decision_unit(claim, unit_id)
            mutated_unit["decidable_at"] = [
                item
                for item in mutated_unit["decidable_at"]
                if item["location"] != location
            ]
            _refresh_decision_digest(claim)
            differences = checker.decision_lock_differences(catalog, lock)
            if not any(
                difference.startswith(f"{claim['source_id']}:")
                for difference in differences
            ):
                escaped.append((unit_id, location))
            attempts[location] += 1
        claim.clear()
        claim.update(original)

    assert attempts == expected_attempts
    assert sum(attempts.values()) == sum(expected_attempts.values())
    assert escaped == []


def test_all_auth_claim_layers_changed_to_every_other_layer_are_red() -> None:
    """全認可判定単位の layer を他の全値へ変えて守る。"""
    catalog, lock = _repository_catalog_and_lock()
    layer_ids = catalog["layer_ids"]
    decision_units = _auth_decision_units(catalog)
    escaped: list[tuple[str, str]] = []
    attempts = 0
    for claim, unit, unit_id in decision_units:
        original = copy.deepcopy(claim)
        original_layer = unit["layer"]
        for layer_id in layer_ids:
            if layer_id == original_layer:
                continue
            mutated_unit = _decision_unit(claim, unit_id)
            mutated_unit["layer"] = layer_id
            _refresh_decision_digest(claim)
            differences = checker.decision_lock_differences(catalog, lock)
            if not any(
                difference.startswith(f"{claim['source_id']}:")
                for difference in differences
            ):
                escaped.append((unit_id, layer_id))
            claim.clear()
            claim.update(copy.deepcopy(original))
            attempts += 1

    assert attempts == len(decision_units) * (len(layer_ids) - 1)
    assert escaped == []


def test_all_out_of_scope_rows_moved_to_auth_claim_are_red() -> None:
    """878行すべての AUTH への逆方向変異を守る。"""
    catalog, lock = _repository_catalog_and_lock()
    out_claims = [
        claim for claim in catalog["claims"] if claim["classification"] == "out_of_scope"
    ]
    escaped: list[str] = []
    attempts = 0
    for claim in out_claims:
        original = copy.deepcopy(claim)
        claim["classification"] = "auth_claim"
        claim["classification_rule_id"] = "AUTH_ACCESS_SCOPE"
        claim["layer"] = "access_control"
        claim["decidable_at"] = [
            {
                "location": "db",
                "basis_rule_id": "DB_ROW_VISIBILITY_PREDICATE",
                "test_owner": {
                    "id": "MUTATION.out-to-auth.db",
                    "status": "planned",
                },
            },
            {
                "location": "http",
                "basis_rule_id": "HTTP_RESPONSE_VISIBILITY",
                "test_owner": {
                    "id": "MUTATION.out-to-auth.http",
                    "status": "planned",
                },
            },
        ]
        _refresh_decision_digest(claim)
        differences = checker.decision_lock_differences(catalog, lock)
        if not any(
            difference.startswith(f"{claim['source_id']}:") for difference in differences
        ):
            escaped.append(claim["source_id"])
        claim.clear()
        claim.update(original)
        attempts += 1

    assert len(out_claims) == 899
    assert attempts == 899
    assert escaped == []


def test_all_basis_rules_changed_one_at_a_time_are_red() -> None:
    """全認可判定単位の basis_rule_id も決定の一部として守る。"""
    catalog, lock = _repository_catalog_and_lock()
    basis_rules = catalog["basis_rules"]
    basis_by_location: dict[str, list[str]] = {
        location: sorted(
            basis_id
            for basis_id, rule in basis_rules.items()
            if rule["location"] == location
        )
        for location in checker.DECIDABLE_LOCATIONS
    }
    decision_units = _auth_decision_units(catalog)
    expected_attempts = sum(
        len(unit["decidable_at"]) for _claim, unit, _unit_id in decision_units
    )
    escaped: list[tuple[str, str]] = []
    attempts = 0
    for claim, unit, unit_id in decision_units:
        original = copy.deepcopy(claim)
        original_unit = _decision_unit(original, unit_id)
        for index, decision in enumerate(original_unit["decidable_at"]):
            alternatives = [
                basis_id
                for basis_id in basis_by_location[decision["location"]]
                if basis_id != decision["basis_rule_id"]
            ]
            assert alternatives
            mutated_unit = _decision_unit(claim, unit_id)
            mutated_unit["decidable_at"][index]["basis_rule_id"] = alternatives[0]
            _refresh_decision_digest(claim)
            differences = checker.decision_lock_differences(catalog, lock)
            if not any(
                difference.startswith(f"{claim['source_id']}:")
                for difference in differences
            ):
                escaped.append((unit_id, decision["location"]))
            claim.clear()
            claim.update(copy.deepcopy(original))
            attempts += 1

    assert attempts == expected_attempts
    assert escaped == []


def test_basis_rule_id_is_a_closed_required_value(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    catalog = _read_catalog(root)
    decision = _auth_claim(catalog)["decidable_at"][0]
    decision["basis_rule_id"] = "自由文の根拠"
    _write_catalog(root, catalog)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "basis_rule_id が閉じた値域にない" in result.stderr


def test_decision_lock_reports_source_id_and_changed_field(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    catalog = _read_catalog(root)
    claim = _auth_claim(catalog)
    claim["layer"] = "authentication_boundary"
    _refresh_decision_digest(claim)
    _write_catalog(root, catalog)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "FR-900/list_item-001: layer が変更" in result.stderr
    assert "lock='operation_authorization'" in result.stderr
    assert "catalog='authentication_boundary'" in result.stderr


def test_normal_validation_never_reseals_a_changed_decision(tmp_path: Path) -> None:
    """通常検査は自己 digest が更新済みでも lock を更新しない。"""
    root = _make_repository(tmp_path)
    catalog = _read_catalog(root)
    claim = _auth_claim(catalog)
    claim["layer"] = "authentication_boundary"
    _refresh_decision_digest(claim)
    _write_catalog(root, catalog)
    claims_before = (root / "requirement-claims.json").read_bytes()
    lock_before = (root / "requirement-claims.lock.json").read_bytes()

    result = _run_cli(root)

    assert result.returncode == 1
    assert "decision lock と不一致" in result.stderr
    assert (root / "requirement-claims.json").read_bytes() == claims_before
    assert (root / "requirement-claims.lock.json").read_bytes() == lock_before


def test_normal_validation_does_not_create_a_missing_lock(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    lock_path = root / "requirement-claims.lock.json"
    lock_path.unlink()

    result = _run_cli(root)

    assert result.returncode == 1
    assert "decision lockを読めない" in result.stderr
    assert not lock_path.exists()


def test_reseal_updates_decisions_only_with_the_explicit_flag(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    catalog = _read_catalog(root)
    claim = _auth_claim(catalog)
    claim["layer"] = "authentication_boundary"
    _refresh_decision_digest(claim)
    _write_catalog(root, catalog)
    lock_before = (root / "requirement-claims.lock.json").read_bytes()

    reseal_result = _run_cli(root, reseal=True)
    validation_result = _run_cli(root)

    assert reseal_result.returncode == 0, reseal_result.stderr
    assert "resealed" in reseal_result.stdout
    assert (root / "requirement-claims.lock.json").read_bytes() != lock_before
    assert validation_result.returncode == 0, validation_result.stderr


def test_aggregate_decision_digest_detects_a_changed_lock_entry(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    lock = _read_lock(root)
    lock["decisions"][0]["classification_rule_id"] = "OUT_NON_AUTH_REQUIREMENT"
    _write_lock(root, lock)

    result = _run_cli(root)

    assert result.returncode == 1
    assert "lock 内の decision_digest" in result.stderr


def test_document_specific_traps_live_in_catalog_data() -> None:
    script_text = SCRIPT.read_text(encoding="utf-8")
    catalog, _lock = _repository_catalog_and_lock()
    out_rule = catalog["classification_rules"]["OUT_NON_AUTH_REQUIREMENT"]

    assert "AUTHZ_CONTEXT_HEADING_IDS" not in script_text
    assert "SECURITY_NON_AUTHZ_HEADING_IDS" not in script_text
    assert "NORMATIVE_AUTHZ_RE" not in script_text
    assert catalog["classification_rules"]["OUT_AUTHZ_CONTEXT_ONLY"][
        "allowed_heading_ids"
    ]
    assert out_rule["forbidden_source_text_patterns"]


def test_invalid_claim_dispositions_are_red() -> None:
    catalog = _read_catalog(FIXTURE_ROOT)
    registry = json.loads(
        (FIXTURE_ROOT / "route-registry.json").read_text(encoding="utf-8")
    )
    cases = json.loads(
        (FIXTURE_ROOT / "invalid-claim-dispositions.json").read_text(encoding="utf-8")
    )
    expected_errors = {
        "missing_http": "HTTP/cache 主張の逆向き exact-set 不一致",
        "double_registered": "HTTP/cache 主張の逆向き exact-set 不一致",
        "unknown_reason": "reason_codeが閉じた値域にない",
    }
    failures: list[tuple[str, str]] = []

    for case_name, claim_dispositions in cases.items():
        mutated = copy.deepcopy(registry)
        mutated["claim_dispositions"] = claim_dispositions
        try:
            checker.validate_route_registry(
                mutated,
                catalog,
                FIXTURE_ROOT,
                frozenset(),
            )
        except checker.CatalogError as error:
            message = str(error)
            if expected_errors[case_name] not in message:
                failures.append((case_name, message))
        else:
            failures.append((case_name, "検査が成功した"))

    assert failures == []


def test_fixture_route_registry_closes_http_and_cache_claims() -> None:
    catalog = _read_catalog(FIXTURE_ROOT)
    registry = json.loads(
        (FIXTURE_ROOT / "route-registry.json").read_text(encoding="utf-8")
    )

    result = checker.validate_route_registry(
        registry,
        catalog,
        FIXTURE_ROOT,
        frozenset(),
    )

    assert set(result["routed_http_claim_ids"]) == {"FR-900/list_item-001"}
    assert set(result["claim_dispositions_by_key"]) == {
        ("FR-900/table_row-001", "http"),
        ("FR-900/table_row-001", "cache"),
    }
    lock = json.loads(
        (FIXTURE_ROOT / "route-registry.lock.json").read_text(encoding="utf-8")
    )
    checker.validate_derived_lock(registry, lock, "route-registry.json")


def test_legacy_routes_require_requirement_origin_and_source_claims() -> None:
    """legacy route の design 帰属と要件主張の無結線を拒否する。"""
    catalog = _read_catalog(FIXTURE_ROOT)
    registry = json.loads(
        (FIXTURE_ROOT / "route-registry.json").read_text(encoding="utf-8")
    )
    cases = {
        "design_origin": {
            "origin": "design",
            "source_claim_ids": [],
            "expected_error": "legacy route は requirement origin が必要",
        },
        "unlinked_requirement": {
            "origin": "requirement",
            "source_claim_ids": [],
            "expected_error": "source_claim_idsは1件以上必要",
        },
    }
    failures: list[tuple[str, str]] = []

    for case_name, case in cases.items():
        mutated = copy.deepcopy(registry)
        legacy_route = next(
            route
            for route in mutated["routes"]
            if route["route_kind"] == "legacy_route"
        )
        legacy_route["origin"] = case["origin"]
        legacy_route["source_claim_ids"] = case["source_claim_ids"]
        try:
            checker.validate_route_registry(
                mutated,
                catalog,
                FIXTURE_ROOT,
                frozenset(),
            )
        except checker.CatalogError as error:
            expected_error = case["expected_error"]
            assert isinstance(expected_error, str)
            if expected_error not in str(error):
                failures.append((case_name, str(error)))
        else:
            failures.append((case_name, "検査が成功した"))

    assert failures == []


def _ddl_elements_semantics_fixture() -> dict[str, Any]:
    """ステップ7の最小 DDL fixture を返す。"""
    return json.loads(
        (FIXTURE_ROOT / "ddl-elements.json").read_text(encoding="utf-8")
    )


def test_invalid_ddl_elements_semantics_are_red() -> None:
    """policy・owner ACL・caller schema USAGE の既知負例を全て拒否する。"""
    cases = json.loads(
        (FIXTURE_ROOT / "invalid-ddl-elements.json").read_text(encoding="utf-8")
    )
    failures: list[tuple[str, str]] = []

    for case_name, case in cases.items():
        mutated = _ddl_elements_semantics_fixture()
        if case["operation"] == "replace":
            parent, key = _parent_and_key(mutated, tuple(case["path"]))
            assert isinstance(parent, dict) and isinstance(key, str)
            parent[key] = case["value"]
        elif case["operation"] == "remove_acl":
            mutated["acl_expectations"] = [
                acl
                for acl in mutated["acl_expectations"]
                if acl["acl_id"] != case["acl_id"]
            ]
        else:
            schema = next(
                schema
                for schema in mutated["schemas"]
                if schema["schema_id"] == case["schema_id"]
            )
            schema["usage_role_ids"].remove(case["role_id"])

        try:
            checker.validate_ddl_elements(mutated, REPOSITORY_ROOT)
        except checker.CatalogError as error:
            message = str(error)
            if case["expected_error"] not in message:
                failures.append((case_name, message))
        else:
            failures.append((case_name, "検査が成功した"))

    assert failures == []


def test_fixture_ddl_elements_semantics_are_valid() -> None:
    """policy 対応表と関数 ACL/schema 依存の最小正例を受理する。"""
    result = checker.validate_ddl_elements(
        _ddl_elements_semantics_fixture(), REPOSITORY_ROOT
    )

    assert result["predicate_ids"] == frozenset(
        {"PREDICATE:CURRENT_TENANT_OWNS_ROW"}
    )


def _atomic_claim_catalog() -> dict[str, Any]:
    """表行1件を2件の atomic claim に置換した母集合を返す。"""
    catalog = _read_catalog(FIXTURE_ROOT)
    atomic_claim = json.loads(
        (FIXTURE_ROOT / "atomic-claim.json").read_text(encoding="utf-8")
    )
    index = next(
        index
        for index, claim in enumerate(catalog["claims"])
        if claim["source_id"] == atomic_claim["source_id"]
    )
    catalog["claims"][index] = atomic_claim
    return catalog


def _validate_atomic_claim_catalog(
    catalog: dict[str, Any], *, verify_decision_digests: bool = False
) -> None:
    """fixture 母集合を検証する。"""
    requirements_path = FIXTURE_ROOT / "requirements.md"
    source_bytes = requirements_path.read_bytes()
    checker.validate_catalog(
        catalog,
        checker.extract_source(source_bytes.decode("utf-8")),
        source_bytes,
        requirements_path,
        FIXTURE_ROOT,
        verify_decision_digests=verify_decision_digests,
    )


def _atomic_route_registry() -> dict[str, Any]:
    """atomic claim を route と disposition から参照する registry を返す。"""
    registry = json.loads(
        (FIXTURE_ROOT / "route-registry.json").read_text(encoding="utf-8")
    )
    references = json.loads(
        (FIXTURE_ROOT / "atomic-route-references.json").read_text(encoding="utf-8")
    )
    route_reference = references["route_reference"]
    route = next(
        route
        for route in registry["routes"]
        if route["route_id"] == route_reference["route_id"]
    )
    route["source_claim_ids"] = route_reference["source_claim_ids"]
    registry["claim_dispositions"] = references["claim_dispositions"]
    return registry


def _point_derived_asset_at_catalog(asset: dict[str, Any], root: Path) -> None:
    """derived fixture の入力 digest を一時 atomic 母集合へ合わせる。"""
    manifest = asset["input_manifest"]
    manifest["requirement_claims_blob_digest"] = checker.git_blob_digest(
        (root / "requirement-claims.json").read_bytes()
    )
    manifest["requirement_claims_lock_blob_digest"] = checker.git_blob_digest(
        (root / "requirement-claims.lock.json").read_bytes()
    )


def test_invalid_atomic_claims_are_red() -> None:
    """atomic ID・layer・親決定・下流参照の既知負例を全て拒否する。"""
    cases = json.loads(
        (FIXTURE_ROOT / "invalid-atomic-claims.json").read_text(encoding="utf-8")
    )
    failures: list[tuple[str, str]] = []

    for case_name, case in cases.items():
        catalog = _atomic_claim_catalog()
        atomic_claim = next(
            claim
            for claim in catalog["claims"]
            if claim["source_id"] == "FR-900/table_row-001"
        )
        try:
            if case["operation"] == "replace":
                parent, key = _parent_and_key(atomic_claim, tuple(case["path"]))
                assert isinstance(parent, dict) and isinstance(key, str)
                parent[key] = case["value"]
                _validate_atomic_claim_catalog(catalog)
            elif case["operation"] == "add_parent_layer":
                atomic_claim["layer"] = case["value"]
                _validate_atomic_claim_catalog(catalog)
            else:
                _validate_atomic_claim_catalog(catalog)
                registry = _atomic_route_registry()
                route = next(
                    route
                    for route in registry["routes"]
                    if route["route_id"]
                    == "ROUTE:SHARED:shared_screen:team_metrics:screen"
                )
                route["source_claim_ids"] = [case["value"]]
                checker.validate_route_registry(
                    registry, catalog, FIXTURE_ROOT, frozenset()
                )
        except checker.CatalogError as error:
            message = str(error)
            if case["expected_error"] not in message:
                failures.append((case_name, message))
        else:
            failures.append((case_name, "検査が成功した"))

    assert failures == []


def test_atomic_claim_fixture_is_valid_and_referenced_downstream(
    tmp_path: Path,
) -> None:
    """2 atomic の決定投影・lock・registry・catalog 参照を検証する。"""
    catalog = _atomic_claim_catalog()
    atomic_claim = next(
        claim
        for claim in catalog["claims"]
        if claim["source_id"] == "FR-900/table_row-001"
    )
    atomic_claim["decision_digest"] = checker.compute_decision_digest(atomic_claim)
    _validate_atomic_claim_catalog(catalog, verify_decision_digests=True)
    changed_atomic_claim = copy.deepcopy(atomic_claim)
    changed_atomic_claim["atomic_claims"][1]["layer"] = "access_control"
    assert checker.compute_decision_digest(changed_atomic_claim) != atomic_claim[
        "decision_digest"
    ]

    lock = checker.build_decision_lock(catalog, "requirement-claims.json")
    checker.validate_decision_lock(catalog, lock, "requirement-claims.json")
    locked = next(
        entry
        for entry in lock["decisions"]
        if entry["source_id"] == "FR-900/table_row-001"
    )
    assert "atomic_claims" in locked
    assert "layer" not in locked and "decidable_at" not in locked

    root = _make_repository(tmp_path)
    _write_catalog(root, catalog)
    _write_lock(root, lock)
    registry = _atomic_route_registry()
    _point_derived_asset_at_catalog(registry, root)
    registry_result = checker.validate_route_registry(
        registry, catalog, root, frozenset()
    )
    auth_catalog = json.loads(
        (FIXTURE_ROOT / "auth-catalog-atomic.json").read_text(encoding="utf-8")
    )
    _point_derived_asset_at_catalog(auth_catalog, root)
    auth_result = checker.validate_auth_catalog(
        auth_catalog,
        catalog,
        registry_result,
        root,
        frozenset(),
    )

    assert set(registry_result["claim_dispositions_by_key"]) == {
        ("FR-900/table_row-001#delivery-policy", "cache"),
    }
    assert "FR-900/table_row-001#delivery-policy" in registry_result[
        "routed_http_claim_ids"
    ]
    assert set(auth_result["entry_by_requirement"]) == {
        "FR-900/list_item-001",
        "FR-900/table_row-001#row-policy",
    }


def _claim_mutant_map_with_execution_support() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    """全 probe/contract に実行対象または理由を宣言した入力を返す。"""
    oracle_assets, _seal, _paths = _repository_oracle_assets()
    mapping = copy.deepcopy(oracle_assets["claim_mutant_map"])
    route_registry = copy.deepcopy(_repository_derived_assets()[0]["route_registry"])
    fixture = json.loads(
        (FIXTURE_ROOT / "claim-execution-support.json").read_text(encoding="utf-8")
    )
    unsupported = fixture["unsupported_contract"]
    unsupported_claim_id = unsupported["claim_id"]
    mapping["classification_rules"]["CONTRACT_ONLY_RUNTIME_TARGET_PENDING"] = {
        "execution_class": "contract_only",
        "requires_db_decision": True,
        "management_claim": False,
    }

    requirement_catalog = _repository_catalog_and_lock()[0]
    atomic_claims_by_parent = {
        claim["source_id"]: claim["atomic_claims"]
        for claim in requirement_catalog["claims"]
        if "atomic_claims" in claim
    }
    mutant_by_id = {
        mutant["mutant_id"]: mutant for mutant in mapping["mutants"]
    }
    mutant_replacements: dict[str, list[tuple[str, str, bool]]] = {}
    expanded_claims: list[dict[str, Any]] = []
    for claim in mapping["claims"]:
        parent_id = claim["claim_id"]
        atomic_claims = atomic_claims_by_parent.get(parent_id)
        if atomic_claims is None:
            expanded_claims.append(claim)
            continue
        parent_mutant_id = claim["mutant_ids"][0]
        assert parent_mutant_id in mutant_by_id
        mutant_prefix, mutant_operator = parent_mutant_id.rsplit(":", maxsplit=1)
        replacements: list[tuple[str, str, bool]] = []
        for atomic_claim in atomic_claims:
            atomic_id = atomic_claim["atomic_id"]
            atomic_suffix = atomic_id.split("#", maxsplit=1)[1]
            atomic_mutant_id = f"{mutant_prefix}:{atomic_suffix}:{mutant_operator}"
            has_db_decision = checker._has_db_decision(atomic_claim)
            atomic_mapping = copy.deepcopy(claim)
            atomic_mapping["claim_id"] = atomic_id
            atomic_mapping["mutant_ids"] = [atomic_mutant_id]
            if not has_db_decision:
                atomic_mapping.update(
                    {
                        "execution_class": "contract_only",
                        "classification_rule_id": (
                            "CONTRACT_ONLY_NO_DB_DECISION_POINT"
                        ),
                        "runtime_kill_required": False,
                        "runtime_evidence_kind": "handoff_runtime_test",
                        "contract_only_reason_code": "no_db_decision_point",
                    }
                )
            expanded_claims.append(atomic_mapping)
            replacements.append((atomic_id, atomic_mutant_id, has_db_decision))
        mutant_replacements[parent_mutant_id] = replacements
    mapping["claims"] = expanded_claims

    expanded_mutants: list[dict[str, Any]] = []
    for mutant in mapping["mutants"]:
        mutant_atomic_replacements = mutant_replacements.get(mutant["mutant_id"])
        if mutant_atomic_replacements is None:
            expanded_mutants.append(mutant)
            continue
        parent_id = mutant["claim_ids"][0]
        for atomic_id, atomic_mutant_id, has_db_decision in mutant_atomic_replacements:
            atomic_mutant = copy.deepcopy(mutant)
            atomic_mutant["mutant_id"] = atomic_mutant_id
            atomic_mutant["claim_ids"] = [atomic_id]
            atomic_mutant["target_element_ids"] = [
                atomic_id if target_id == parent_id else target_id
                for target_id in atomic_mutant["target_element_ids"]
            ]
            if not has_db_decision:
                atomic_mutant.update(
                    {
                        "runtime_kill_required": False,
                        "runtime_kill_waiver_reason": "contract_only_handoff",
                        "expected_runtime_outcome": "handoff",
                        "expected_positive_outcome": "handoff",
                        "positive_kill_required": False,
                        "positive_case_scope_id": None,
                    }
                )
            expanded_mutants.append(atomic_mutant)
    mapping["mutants"] = expanded_mutants

    ddl = oracle_assets["ddl_elements"]
    provisioning_claim_id = ddl["provisioning_claim"]["claim_id"]
    management_probe_claim_ids = set(
        ddl["representative_management_probe"]["claim_ids"]
    )
    management_function_id = ddl["representative_management_probe"]["function_id"]
    for claim in mapping["claims"]:
        claim_id = claim["claim_id"]
        if claim_id == unsupported_claim_id:
            claim.update(
                {
                    "execution_class": "contract_only",
                    "classification_rule_id": unsupported["classification_rule_id"],
                    "runtime_kill_required": False,
                    "runtime_evidence_kind": "handoff_runtime_test",
                    "contract_only_reason_code": unsupported[
                        "contract_only_reason_code"
                    ],
                }
            )
        elif claim["execution_class"] == "contract_only":
            claim["contract_only_reason_code"] = (
                "no_db_decision_point"
                if claim["classification_rule_id"]
                == "CONTRACT_ONLY_NO_DB_DECISION_POINT"
                else "route_universe_pending"
            )
        elif claim_id == provisioning_claim_id:
            claim["runtime_target"] = {
                "target_kind": "ddl_provisioning",
                "target_ids": [provisioning_claim_id],
            }
        elif claim_id in management_probe_claim_ids:
            claim["runtime_target"] = {
                "target_kind": "ddl_function",
                "target_ids": [management_function_id],
            }
        else:
            route_id = f"ROUTE:RUNTIME:{claim_id}"
            claim["runtime_target"] = {
                "target_kind": "route",
                "target_ids": [route_id],
            }
            route_registry["routes"].append(
                {"route_id": route_id, "source_claim_ids": [claim_id]}
            )

    unsupported_mutant_id = next(
        claim["mutant_ids"][0]
        for claim in mapping["claims"]
        if claim["claim_id"] == unsupported_claim_id
    )
    unsupported_mutant = next(
        mutant
        for mutant in mapping["mutants"]
        if mutant["mutant_id"] == unsupported_mutant_id
    )
    unsupported_mutant.update(
        {
            "runtime_kill_required": False,
            "runtime_kill_waiver_reason": "contract_only_handoff",
            "expected_runtime_outcome": "handoff",
            "expected_positive_outcome": "handoff",
            "positive_kill_required": False,
            "positive_case_scope_id": None,
        }
    )
    ddl_result = checker.validate_ddl_elements(ddl, REPOSITORY_ROOT)
    return mapping, route_registry, ddl_result


def _validate_claim_mutant_map_with_execution_support(
    mapping: dict[str, Any],
    route_registry: dict[str, Any],
    ddl_result: dict[str, Any],
) -> dict[str, Any]:
    """実資産を読み取り専用の参照集合として mutant map を検査する。"""
    derived_assets, _locks, _paths = _repository_derived_assets()
    return checker.validate_claim_mutant_map(
        mapping,
        _repository_catalog_and_lock()[0],
        route_registry,
        derived_assets["http_matrix"],
        ddl_result,
        REPOSITORY_ROOT,
        frozenset({IMPLEMENTED_CATALOG_TEST_ID, IMPLEMENTED_ORACLE_TEST_ID}),
    )


def test_invalid_claim_execution_support_is_red() -> None:
    """裏付けなし probe と理由不備 contract の既知負例を拒否する。"""
    cases = json.loads(
        (FIXTURE_ROOT / "invalid-claim-execution-support.json").read_text(
            encoding="utf-8"
        )
    )
    failures: list[tuple[str, str]] = []

    for case_name, case in cases.items():
        mapping, route_registry, ddl_result = (
            _claim_mutant_map_with_execution_support()
        )
        claim = next(
            claim
            for claim in mapping["claims"]
            if claim["claim_id"] == case["claim_id"]
        )
        if case["operation"] == "remove_runtime_target":
            del claim["runtime_target"]
        elif case["operation"] == "remove_contract_reason":
            del claim["contract_only_reason_code"]
        else:
            claim["contract_only_reason_code"] = case["value"]
        try:
            _validate_claim_mutant_map_with_execution_support(
                mapping, route_registry, ddl_result
            )
        except checker.CatalogError as error:
            if case["expected_error"] not in str(error):
                failures.append((case_name, str(error)))
        else:
            failures.append((case_name, "検査が成功した"))

    assert failures == []


def test_claim_execution_support_fixture_is_valid() -> None:
    """route 裏付け probe と理由つき contract の正例を受理する。"""
    mapping, route_registry, ddl_result = _claim_mutant_map_with_execution_support()

    result = _validate_claim_mutant_map_with_execution_support(
        mapping, route_registry, ddl_result
    )
    fixture = json.loads(
        (FIXTURE_ROOT / "claim-execution-support.json").read_text(encoding="utf-8")
    )
    claim_by_id = {claim["claim_id"]: claim for claim in mapping["claims"]}

    assert claim_by_id[fixture["supported_probe"]["claim_id"]][
        "runtime_target"
    ] == fixture["supported_probe"]["runtime_target"]
    assert claim_by_id[fixture["unsupported_contract"]["claim_id"]][
        "contract_only_reason_code"
    ] == "route_universe_pending"
    assert result["execution_counts"] == Counter(
        {"contract_only": 165, "probe_executable": 33}
    )


def _validate_one_derived_asset(
    name: str,
    mutated: dict[str, Any],
    assets: dict[str, dict[str, Any]],
    requirement_catalog: dict[str, Any],
    implemented_test_ids: frozenset[str],
) -> None:
    """対象資産だけを意味検査し、他資産は正しい参照先として使う。"""
    if name == "route_registry":
        checker.validate_route_registry(
            mutated,
            requirement_catalog,
            REPOSITORY_ROOT,
            implemented_test_ids,
        )
        return
    registry_result = checker.validate_route_registry(
        assets["route_registry"],
        requirement_catalog,
        REPOSITORY_ROOT,
        implemented_test_ids,
    )
    if name == "auth_catalog":
        checker.validate_auth_catalog(
            mutated,
            requirement_catalog,
            registry_result,
            REPOSITORY_ROOT,
            implemented_test_ids,
        )
        return
    assert name == "http_matrix"
    checker.validate_http_route_matrix(
        mutated,
        registry_result,
        REPOSITORY_ROOT,
        implemented_test_ids,
    )


def _implemented_owner_paths(value: object) -> list[tuple[str | int, ...]]:
    """資産自身から implemented test owner のパスを全数列挙する。"""
    paths: list[tuple[str | int, ...]] = []

    def visit(current: object, path: tuple[str | int, ...]) -> None:
        if isinstance(current, dict):
            if set(current) == {"id", "status"} and current["status"] == "implemented":
                paths.append(path)
            for key, child in current.items():
                visit(child, (*path, key))
        elif isinstance(current, list):
            for index, child in enumerate(current):
                visit(child, (*path, index))

    visit(value, ())
    return paths


def test_repository_derived_assets_are_valid() -> None:
    """177主張・全route・12セルと実収集テストIDを統合検査する。"""
    requirement_catalog, _requirement_lock = _repository_catalog_and_lock()
    assets, locks, paths = _repository_derived_assets()
    implemented_test_ids = checker.collect_pytest_node_ids(REPOSITORY_ROOT)

    result = checker.validate_derived_assets(
        requirement_catalog,
        assets["route_registry"],
        assets["auth_catalog"],
        assets["http_matrix"],
        locks,
        paths,
        REPOSITORY_ROOT,
        implemented_test_ids,
    )

    assert IMPLEMENTED_CATALOG_TEST_ID in implemented_test_ids
    assert result["catalog"]["db_claim_count"] == 187
    assert len(result["registry"]["route_by_id"]) == len(
        assets["route_registry"]["routes"]
    )
    assert result["matrix"]["cell_count"] == 12
    assert result["matrix"]["result_counts"] == Counter({"allow": 6, "deny": 6})


def test_all_recursively_enumerated_asset_leaves_reject_change_and_deletion() -> None:
    """3資産自身から得た全葉で、値改変と削除を1件ずつ必ず red にする。"""
    assets, locks, paths = _repository_derived_assets()
    leaf_counts = {name: len(_iter_leaf_paths(asset)) for name, asset in assets.items()}
    escaped: list[tuple[str, tuple[str | int, ...], str]] = []
    attempts = 0

    for name, asset in assets.items():
        for leaf_path in _iter_leaf_paths(asset):
            for mutation in ("change", "delete"):
                mutated = _mutate_leaf(asset, leaf_path, delete=mutation == "delete")
                try:
                    checker.validate_derived_lock(mutated, locks[name], paths[name])
                except checker.CatalogError:
                    pass
                else:
                    escaped.append((name, leaf_path, mutation))
                attempts += 1

    assert all(count > 0 for count in leaf_counts.values())
    assert attempts == sum(leaf_counts.values()) * 2
    assert escaped == []


def test_derived_lock_reports_stable_id_and_changed_field() -> None:
    """lock 差分は変更行の安定 ID と変更フィールドを名指しする。"""
    assets, locks, paths = _repository_derived_assets()
    mutated = copy.deepcopy(assets["auth_catalog"])
    entry = mutated["entries"][0]
    entry["origin"] = "design"

    try:
        checker.validate_derived_lock(
            mutated,
            locks["auth_catalog"],
            paths["auth_catalog"],
        )
    except checker.CatalogError as error:
        message = str(error)
    else:
        raise AssertionError("decision lock の差分を検出しなかった")

    assert entry["catalog_entry_id"] in message
    assert "変更フィールド=['origin']" in message


def test_all_origin_assignments_reject_the_opposite_origin() -> None:
    """資産から列挙した全 origin 決定を1件ずつ反転して red にする。"""
    requirement_catalog, _requirement_lock = _repository_catalog_and_lock()
    assets, _locks, _paths = _repository_derived_assets()
    implemented = frozenset({IMPLEMENTED_CATALOG_TEST_ID})
    escaped: list[tuple[str, tuple[str | int, ...]]] = []
    attempts = 0

    for name in ("route_registry", "auth_catalog"):
        asset = assets[name]
        origin_paths = [
            path for path in _iter_leaf_paths(asset) if path[-1] == "origin"
        ]
        for path in origin_paths:
            mutated = copy.deepcopy(asset)
            parent, key = _parent_and_key(mutated, path)
            assert isinstance(parent, dict) and isinstance(key, str)
            parent[key] = "design" if parent[key] == "requirement" else "requirement"
            try:
                _validate_one_derived_asset(
                    name, mutated, assets, requirement_catalog, implemented
                )
            except checker.CatalogError:
                pass
            else:
                escaped.append((name, path))
            attempts += 1

    expected_attempts = sum(
        1
        for name in ("route_registry", "auth_catalog")
        for path in _iter_leaf_paths(assets[name])
        if path[-1] == "origin"
    )
    assert attempts == expected_attempts
    assert escaped == []


def test_all_route_class_values_reject_an_unregistered_value() -> None:
    """資産から列挙した全 route_class を許可外値へ変えて red にする。"""
    requirement_catalog, _requirement_lock = _repository_catalog_and_lock()
    assets, _locks, _paths = _repository_derived_assets()
    implemented = frozenset({IMPLEMENTED_CATALOG_TEST_ID})
    escaped: list[tuple[str, tuple[str | int, ...]]] = []
    attempts = 0

    for name in ("route_registry", "http_matrix"):
        asset = assets[name]
        class_paths = [
            path
            for path in _iter_leaf_paths(asset)
            if path[-1] == "route_class"
            or (len(path) >= 2 and path[-2] == "route_classes")
        ]
        for path in class_paths:
            mutated = copy.deepcopy(asset)
            parent, key = _parent_and_key(mutated, path)
            if isinstance(parent, dict):
                assert isinstance(key, str)
                parent[key] = "unregistered_route_class"
            else:
                assert isinstance(key, int)
                parent[key] = "unregistered_route_class"
            try:
                _validate_one_derived_asset(
                    name, mutated, assets, requirement_catalog, implemented
                )
            except checker.CatalogError:
                pass
            else:
                escaped.append((name, path))
            attempts += 1

    assert attempts == sum(
        1
        for name in ("route_registry", "http_matrix")
        for path in _iter_leaf_paths(assets[name])
        if path[-1] == "route_class"
        or (len(path) >= 2 and path[-2] == "route_classes")
    )
    assert escaped == []


def test_all_product_cells_reject_allow_deny_reversal() -> None:
    """直積から列挙した全セルで allow と deny を反転して red にする。"""
    requirement_catalog, _requirement_lock = _repository_catalog_and_lock()
    assets, _locks, _paths = _repository_derived_assets()
    implemented = frozenset({IMPLEMENTED_CATALOG_TEST_ID})
    cells = assets["http_matrix"]["cells"]
    escaped: list[str] = []

    for index, cell in enumerate(cells):
        mutated = copy.deepcopy(assets["http_matrix"])
        mutated_cell = mutated["cells"][index]
        mutated_cell["expected_result"] = (
            "deny" if cell["expected_result"] == "allow" else "allow"
        )
        try:
            _validate_one_derived_asset(
                "http_matrix", mutated, assets, requirement_catalog, implemented
            )
        except checker.CatalogError:
            pass
        else:
            escaped.append(cell["cell_id"])

    assert len(cells) == len(
        {
            (cell["route_class"], cell["resource_kind"], cell["channel"])
            for cell in cells
        }
    )
    assert escaped == []


def test_all_implemented_test_owners_reject_planned_status() -> None:
    """全 implemented 所有決定を planned へ移しても lock が必ず red にする。"""
    assets, locks, paths = _repository_derived_assets()
    escaped: list[tuple[str, tuple[str | int, ...]]] = []
    attempts = 0

    for name, asset in assets.items():
        owner_paths = _implemented_owner_paths(asset)
        for owner_path in owner_paths:
            mutated = copy.deepcopy(asset)
            owner = _value_at_path(mutated, owner_path)
            assert isinstance(owner, dict)
            owner["status"] = "planned"
            try:
                checker.validate_derived_lock(mutated, locks[name], paths[name])
            except checker.CatalogError:
                pass
            else:
                escaped.append((name, owner_path))
            attempts += 1

    assert attempts == sum(
        len(_implemented_owner_paths(asset)) for asset in assets.values()
    )
    assert attempts > 0
    assert escaped == []


def test_all_implemented_test_ids_must_exist_in_collection() -> None:
    """資産内の全 implemented owner を未収集IDへ変えて red にする。"""
    requirement_catalog, _requirement_lock = _repository_catalog_and_lock()
    assets, _locks, _paths = _repository_derived_assets()
    implemented = frozenset({IMPLEMENTED_CATALOG_TEST_ID})
    escaped: list[tuple[str, tuple[str | int, ...]]] = []
    attempts = 0

    for name, asset in assets.items():
        for owner_path in _implemented_owner_paths(asset):
            mutated = copy.deepcopy(asset)
            owner = _value_at_path(mutated, owner_path)
            assert isinstance(owner, dict)
            owner["id"] = "tests/missing.py::test_not_collected"
            try:
                _validate_one_derived_asset(
                    name, mutated, assets, requirement_catalog, implemented
                )
            except checker.CatalogError:
                pass
            else:
                escaped.append((name, owner_path))
            attempts += 1

    assert attempts == sum(
        len(_implemented_owner_paths(asset)) for asset in assets.values()
    )
    assert attempts > 0
    assert escaped == []


def test_all_db_claim_correspondences_reject_one_entry_removal() -> None:
    """母集合から機械抽出した全DB主張を1件ずつ未対応にして red にする。"""
    requirement_catalog, _requirement_lock = _repository_catalog_and_lock()
    assets, _locks, _paths = _repository_derived_assets()
    implemented = frozenset({IMPLEMENTED_CATALOG_TEST_ID})
    registry_result = checker.validate_route_registry(
        assets["route_registry"],
        requirement_catalog,
        REPOSITORY_ROOT,
        implemented,
    )
    entries = assets["auth_catalog"]["entries"]
    db_claim_ids = set(checker._db_claims_by_id(requirement_catalog))
    escaped: list[str] = []

    for index, entry in enumerate(entries):
        mutated = copy.deepcopy(assets["auth_catalog"])
        mutated["entries"].pop(index)
        try:
            checker.validate_auth_catalog(
                mutated,
                requirement_catalog,
                registry_result,
                REPOSITORY_ROOT,
                implemented,
            )
        except checker.CatalogError:
            pass
        else:
            escaped.append(entry["requirement_claim_id"])

    assert {entry["requirement_claim_id"] for entry in entries} == db_claim_ids
    assert len(entries) == len(db_claim_ids)
    assert escaped == []


def test_all_registry_matrix_links_reject_either_side_removal() -> None:
    """ファイルから列挙した全 route を両側で1件ずつ外して exact-set を守る。"""
    requirement_catalog, _requirement_lock = _repository_catalog_and_lock()
    assets, _locks, _paths = _repository_derived_assets()
    implemented = frozenset({IMPLEMENTED_CATALOG_TEST_ID})
    registry_routes = assets["route_registry"]["routes"]
    matrix_routes = assets["http_matrix"]["routes"]
    escaped: list[tuple[str, str]] = []

    for index, route in enumerate(registry_routes):
        mutated_registry = copy.deepcopy(assets["route_registry"])
        mutated_registry["routes"].pop(index)
        try:
            registry_result = checker.validate_route_registry(
                mutated_registry,
                requirement_catalog,
                REPOSITORY_ROOT,
                implemented,
            )
            checker.validate_http_route_matrix(
                assets["http_matrix"],
                registry_result,
                REPOSITORY_ROOT,
                implemented,
            )
        except checker.CatalogError:
            pass
        else:
            escaped.append(("registry", route["route_id"]))

    registry_result = checker.validate_route_registry(
        assets["route_registry"],
        requirement_catalog,
        REPOSITORY_ROOT,
        implemented,
    )
    for index, route in enumerate(matrix_routes):
        mutated_matrix = copy.deepcopy(assets["http_matrix"])
        mutated_matrix["routes"].pop(index)
        try:
            checker.validate_http_route_matrix(
                mutated_matrix,
                registry_result,
                REPOSITORY_ROOT,
                implemented,
            )
        except checker.CatalogError:
            pass
        else:
            escaped.append(("matrix", route["route_id"]))

    assert {route["route_id"] for route in registry_routes} == {
        route["route_id"] for route in matrix_routes
    }
    assert escaped == []


def test_forbidden_import_and_nonshareable_resources_are_absent() -> None:
    """射程外取り込みと常時404資源が3資産の値域に0件であることを確認する。"""
    assets, _locks, _paths = _repository_derived_assets()
    serialized = json.dumps(assets, ensure_ascii=False)
    forbidden_terms = checker.FORBIDDEN_EVACUATED_IMPORT_TERMS
    registry_resources = set(assets["route_registry"]["enums"]["resource_kinds"])
    matrix_resources = set(assets["http_matrix"]["resource_kinds"])

    assert sum(serialized.count(term) for term in forbidden_terms) == 0
    assert checker.FORBIDDEN_RESOURCE_KINDS.isdisjoint(registry_resources)
    assert checker.FORBIDDEN_RESOURCE_KINDS.isdisjoint(matrix_resources)


def _validate_repository_oracle(
    assets: dict[str, dict[str, Any]],
    seal: dict[str, Any],
    paths: dict[str, str],
    *,
    verify_seal: bool = True,
) -> dict[str, dict[str, Any]]:
    """ステップ1・4の正本を入力に oracle 資産を統合検査する。"""
    requirement_catalog, _requirement_lock = _repository_catalog_and_lock()
    derived_assets, _derived_locks, _derived_paths = _repository_derived_assets()
    result = checker.validate_oracle_assets(
        requirement_catalog,
        derived_assets["route_registry"],
        derived_assets["auth_catalog"],
        derived_assets["http_matrix"],
        assets,
        seal,
        paths,
        REPOSITORY_ROOT,
        frozenset({IMPLEMENTED_CATALOG_TEST_ID, IMPLEMENTED_ORACLE_TEST_ID}),
        verify_seal=verify_seal,
    )
    assert isinstance(result, dict)
    return result


def _validate_mutant_map(mutated: dict[str, Any]) -> None:
    """変異した対応表を、資産から導出した入力集合に対して意味検査する。"""
    requirement_catalog, _requirement_lock = _repository_catalog_and_lock()
    derived_assets, _derived_locks, _derived_paths = _repository_derived_assets()
    oracle_assets, _seal, _paths = _repository_oracle_assets()
    ddl_result = checker.validate_ddl_elements(
        oracle_assets["ddl_elements"], REPOSITORY_ROOT
    )
    checker.validate_claim_mutant_map(
        mutated,
        requirement_catalog,
        derived_assets["route_registry"],
        derived_assets["http_matrix"],
        ddl_result,
        REPOSITORY_ROOT,
        frozenset({IMPLEMENTED_CATALOG_TEST_ID, IMPLEMENTED_ORACLE_TEST_ID}),
    )


def test_receiving_task_four_layers_accept_the_repository_assets() -> None:
    """受取先の文法・参照・owner・規則導出と差分閉包の正例を検査する。"""
    assets, seal, _paths = _repository_oracle_assets()
    mapping = assets["claim_mutant_map"]
    claims = mapping["claims"]
    requirement_text = (
        REPOSITORY_ROOT / "docs/requirements/requirements-pitchlog-2026-07-22.md"
    ).read_text(encoding="utf-8")
    requirement_ids = checker.requirement_reference_ids(requirement_text)
    independently_extracted = frozenset(
        line.split(maxsplit=2)[1].removesuffix(":")
        for line in requirement_text.splitlines()
        if line.startswith(("#### FR-", "#### NFR-"))
    )

    assert requirement_ids == independently_extracted
    for index, claim in enumerate(claims):
        checker._validate_receiving_task_id_syntax(
            claim["receiving_task_id"], f"claims[{index}].receiving_task_id"
        )
    checker._validate_receiving_task_references(claims, requirement_ids)
    checker._validate_receiving_task_owner_consistency(claims)
    checker._validate_receiving_task_assignments(claims)

    handoff_owners = {
        claim["runtime_test_owner"]["id"]
        for claim in claims
        if claim["runtime_test_owner"]["id"].startswith(
            checker.RUNTIME_HANDOFF_OWNER_PREFIX
        )
    }
    assert set(checker._derive_receiving_task_targets(claims)) == handoff_owners
    assert all(
        claim["receiving_task_id"] != "TSK-270-GROUP-2"
        and not claim["receiving_task_id"].startswith("PENDING:TASK-")
        for claim in claims
    )

    mixed_reason_rows = [
        claim
        for claim in claims
        if claim["runtime_test_owner"]["id"]
        == "TSK-270.group2.runtime.FR-041/list_item-014"
    ]
    assert len({claim["contract_only_reason_code"] for claim in mixed_reason_rows}) > 1
    assert len({claim["receiving_task_id"] for claim in mixed_reason_rows}) == 1

    base_mapping = _receiving_task_base_json(
        "contracts/authz/claim-mutant-map.json"
    )
    base_seal = _receiving_task_base_json(f"contracts/authz/{ORACLE_SEAL_FILE}")
    base_mcdc_map_text = _receiving_task_base_text("contracts/authz/mcdc-map.json")
    mcdc_map_text = _receiving_task_head_text("contracts/authz/mcdc-map.json")
    checker.validate_receiving_task_change_closure(
        base_mapping,
        mapping,
        base_seal,
        seal,
        base_mcdc_map_text,
        mcdc_map_text,
        checker._receiving_task_changed_contract_paths(REPOSITORY_ROOT),
    )


@pytest.mark.parametrize(
    "invalid_receiving_task_id",
    ["TSK-270-GROUP-2", "PENDING:TASK-ANYTHING", "TSK-1234"],
)
def test_receiving_task_syntax_rejects_values_outside_the_final_grammar(
    invalid_receiving_task_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """旧群・タスク別名・4桁IDを層①だけで拒否する。"""
    with pytest.raises(checker.CatalogError):
        checker._validate_receiving_task_id_syntax(
            invalid_receiving_task_id, "receiving_task_id"
        )

    assets, _seal, _paths = _repository_oracle_assets()
    mapping = copy.deepcopy(assets["claim_mutant_map"])
    claim = next(
        row
        for row in mapping["claims"]
        if row["runtime_test_owner"]["id"].startswith("TSK-217.runtime.")
    )
    claim["receiving_task_id"] = invalid_receiving_task_id
    with pytest.raises(checker.CatalogError):
        _validate_mutant_map(mapping)

    monkeypatch.setattr(
        checker,
        "_validate_receiving_task_id_syntax",
        lambda value, _label: str(value),
    )
    _validate_mutant_map(mapping)


def test_pending_requirement_reference_must_exist_in_requirement_headings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PENDING:FR-999 を層②だけで拒否し、NFR の実在参照は許す。"""
    assets, _seal, _paths = _repository_oracle_assets()
    mapping = copy.deepcopy(assets["claim_mutant_map"])
    claims = mapping["claims"]
    requirement_text = (
        REPOSITORY_ROOT / "docs/requirements/requirements-pitchlog-2026-07-22.md"
    ).read_text(encoding="utf-8")
    requirement_ids = checker.requirement_reference_ids(requirement_text)
    checker._validate_receiving_task_references(
        [
            {
                "execution_class": "contract_only",
                "receiving_task_id": "PENDING:NFR-019",
            }
        ],
        requirement_ids,
    )

    claim = next(
        row
        for row in claims
        if row["runtime_test_owner"]["id"].startswith("TSK-217.runtime.")
    )
    claim["receiving_task_id"] = "PENDING:FR-999"
    with pytest.raises(checker.CatalogError):
        checker._validate_receiving_task_references(claims, requirement_ids)
    with pytest.raises(checker.CatalogError):
        _validate_mutant_map(mapping)

    monkeypatch.setattr(
        checker, "_validate_receiving_task_references", lambda *_args: None
    )
    _validate_mutant_map(mapping)


def test_probe_executable_rejects_a_pending_receiving_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """確定済み probe の PENDING 受取先を層②だけで拒否する。"""
    assets, _seal, _paths = _repository_oracle_assets()
    mapping = copy.deepcopy(assets["claim_mutant_map"])
    claims = mapping["claims"]
    owner_counts = Counter(
        claim["runtime_test_owner"]["id"] for claim in claims
    )
    claim = next(
        row
        for row in claims
        if row["execution_class"] == "probe_executable"
        and not row["runtime_test_owner"]["id"].startswith(
            checker.RUNTIME_HANDOFF_OWNER_PREFIX
        )
        and owner_counts[row["runtime_test_owner"]["id"]] == 1
    )
    claim["receiving_task_id"] = "PENDING:FR-041"
    requirement_ids = checker.requirement_reference_ids(
        (
            REPOSITORY_ROOT
            / "docs/requirements/requirements-pitchlog-2026-07-22.md"
        ).read_text(encoding="utf-8")
    )
    with pytest.raises(checker.CatalogError):
        checker._validate_receiving_task_references(claims, requirement_ids)
    with pytest.raises(checker.CatalogError):
        _validate_mutant_map(mapping)

    monkeypatch.setattr(
        checker, "_validate_receiving_task_references", lambda *_args: None
    )
    _validate_mutant_map(mapping)


def test_shared_runtime_owner_rejects_different_receiving_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """共有 owner の片方だけを変え、層③だけで拒否する。"""
    assets, _seal, _paths = _repository_oracle_assets()
    mapping = copy.deepcopy(assets["claim_mutant_map"])
    claims = mapping["claims"]
    shared_owner = "TSK-250.runtime.FR-041/list_item-006"
    shared_rows = [
        claim for claim in claims if claim["runtime_test_owner"]["id"] == shared_owner
    ]
    assert len(shared_rows) > 1
    shared_rows[0]["receiving_task_id"] = "TSK-217"
    with pytest.raises(checker.CatalogError):
        checker._validate_receiving_task_owner_consistency(claims)
    with pytest.raises(checker.CatalogError):
        _validate_mutant_map(mapping)

    monkeypatch.setattr(
        checker, "_validate_receiving_task_owner_consistency", lambda *_args: None
    )
    _validate_mutant_map(mapping)


@pytest.mark.parametrize("execution_class", ["contract_only", "probe_executable"])
def test_receiving_task_rule_derivation_rejects_a_valid_but_wrong_task_id(
    execution_class: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """文法上有効な誤宛先を規則導出との exact-set 突合だけで拒否する。"""
    assets, _seal, _paths = _repository_oracle_assets()
    mapping = copy.deepcopy(assets["claim_mutant_map"])
    claims = mapping["claims"]
    owner_counts = Counter(
        claim["runtime_test_owner"]["id"] for claim in claims
    )
    claim = next(
        row
        for row in claims
        if row["execution_class"] == execution_class
        and row["runtime_test_owner"]["id"].startswith(
            checker.RUNTIME_HANDOFF_OWNER_PREFIX
        )
        and owner_counts[row["runtime_test_owner"]["id"]] == 1
        and row["receiving_task_id"] != "TSK-250"
    )
    claim["receiving_task_id"] = "TSK-250"
    with pytest.raises(checker.CatalogError):
        checker._validate_receiving_task_assignments(claims)
    with pytest.raises(checker.CatalogError):
        _validate_mutant_map(mapping)

    monkeypatch.setattr(
        checker, "_validate_receiving_task_assignments", lambda *_args: None
    )
    _validate_mutant_map(mapping)


class _ReceivingTaskChangeClosureInputs(NamedTuple):
    """差分閉包へ渡す7入力を型付きで保持する。"""

    base_mapping: dict[str, Any]
    current_mapping: dict[str, Any]
    base_seal: dict[str, Any]
    current_seal: dict[str, Any]
    base_mcdc_map_text: str
    current_mcdc_map_text: str
    changed_paths: set[str]


def _receiving_task_change_closure_inputs(
    *, base_has_placeholder: bool
) -> _ReceivingTaskChangeClosureInputs:
    """差分閉包ゲート用に置換前後または置換済みの入力一式を作る。"""
    assets, seal, _paths = _repository_oracle_assets()
    base_mapping = copy.deepcopy(assets["claim_mutant_map"])
    current_mapping = copy.deepcopy(base_mapping)
    if base_has_placeholder:
        base_mapping["claims"][0]["receiving_task_id"] = "TSK-270-GROUP-2"
    mcdc_map_text = _receiving_task_head_text("contracts/authz/mcdc-map.json")
    changed_paths = {
        str(checker.DEFAULT_CLAIM_MUTANT_MAP),
        str(checker.DEFAULT_ORACLE_SEAL),
        str(checker.DEFAULT_MCDC_MAP),
    }
    return _ReceivingTaskChangeClosureInputs(
        base_mapping,
        current_mapping,
        copy.deepcopy(seal),
        copy.deepcopy(seal),
        mcdc_map_text,
        mcdc_map_text,
        changed_paths,
    )


@pytest.mark.parametrize(
    ("stage", "expected_error"),
    [
        ("changed_paths", "変更できない contracts パス"),
        ("mutant_map", "対象行の receiving_task_id 以外"),
        ("oracle_seal", "canonical_sha256 以外"),
        ("mcdc_map", "blob_digest 以外"),
    ],
)
def test_receiving_task_change_closure_gate_preserves_all_four_stages(
    stage: str, expected_error: str
) -> None:
    """基準版に対象行がある場合は入口経由で段1〜4の違反を拒否する。"""
    (
        base_mapping,
        current_mapping,
        base_seal,
        current_seal,
        base_mcdc_map_text,
        current_mcdc_map_text,
        changed_paths,
    ) = _receiving_task_change_closure_inputs(base_has_placeholder=True)
    if stage == "changed_paths":
        changed_paths.add("contracts/authz/unapproved.json")
    elif stage == "mutant_map":
        current_mapping["unapproved_leaf"] = True
    elif stage == "oracle_seal":
        current_seal["unapproved_leaf"] = True
    else:
        current_mcdc_map = json.loads(current_mcdc_map_text)
        current_mcdc_map["unapproved_leaf"] = True
        current_mcdc_map_text = _json_text(current_mcdc_map)

    with pytest.raises(checker.CatalogError, match=expected_error):
        checker.validate_receiving_task_change_closure(
            base_mapping,
            current_mapping,
            base_seal,
            current_seal,
            base_mcdc_map_text,
            current_mcdc_map_text,
            changed_paths,
        )


def test_receiving_task_change_closure_gate_runs_all_stages_for_legacy_base() -> None:
    """基準版に対象行がある正例では入口から既存4段を完走する。"""
    checker.validate_receiving_task_change_closure(
        *_receiving_task_change_closure_inputs(base_has_placeholder=True)
    )


def test_receiving_task_change_closure_gate_skips_paths_after_replacement() -> None:
    """置換済みの両版では別 contracts/authz パスが段1に拒否されない。"""
    inputs = _receiving_task_change_closure_inputs(base_has_placeholder=False)
    inputs.changed_paths.add("contracts/authz/frozen-baselines.json")
    checker.validate_receiving_task_change_closure(*inputs)


def test_receiving_task_change_closure_gate_rejects_restored_placeholder() -> None:
    """置換済み基準に対して HEAD へ旧プレースホルダを復活できない。"""
    inputs = _receiving_task_change_closure_inputs(base_has_placeholder=False)
    inputs.current_mapping["claims"][0]["receiving_task_id"] = "TSK-270-GROUP-2"
    with pytest.raises(checker.CatalogError, match="対象行が復活"):
        checker.validate_receiving_task_change_closure(*inputs)


@pytest.mark.parametrize("side", ["base", "head"])
@pytest.mark.parametrize(
    ("invalid_kind", "invalid_claims"),
    [
        ("missing", None),
        ("not_array", {}),
        ("empty", []),
        ("non_object", [None]),
    ],
)
def test_receiving_task_change_closure_gate_rejects_invalid_claims_shape(
    side: str, invalid_kind: str, invalid_claims: object
) -> None:
    """両版の claims 欠落・非配列・空配列・非オブジェクト要素を拒否する。"""
    inputs = _receiving_task_change_closure_inputs(base_has_placeholder=False)
    mutant_map = inputs.base_mapping if side == "base" else inputs.current_mapping
    if invalid_kind == "missing":
        mutant_map.pop("claims")
    else:
        mutant_map["claims"] = invalid_claims
    with pytest.raises(checker.CatalogError):
        checker.validate_receiving_task_change_closure(*inputs)


@pytest.mark.parametrize("side", ["base", "head"])
@pytest.mark.parametrize(
    ("invalid_kind", "invalid_value"),
    [
        ("missing", None),
        ("not_string", 270),
        ("empty", ""),
        ("invalid_syntax", "INVALID"),
    ],
)
def test_receiving_task_change_closure_gate_rejects_invalid_receiving_task_id(
    side: str, invalid_kind: str, invalid_value: object
) -> None:
    """両版の受取先欠落・非文字列・空文字列・文法外文字列を拒否する。"""
    inputs = _receiving_task_change_closure_inputs(base_has_placeholder=False)
    mutant_map = inputs.base_mapping if side == "base" else inputs.current_mapping
    claim = mutant_map["claims"][0]
    if invalid_kind == "missing":
        claim.pop("receiving_task_id")
    else:
        claim["receiving_task_id"] = (
            "TSK-270-GROUP-2"
            if side == "head" and invalid_kind == "invalid_syntax"
            else invalid_value
        )
    with pytest.raises(checker.CatalogError):
        checker.validate_receiving_task_change_closure(*inputs)


def test_receiving_task_change_closure_gate_bypasses_the_legacy_four_stages() -> None:
    """同じ対象0件入力で入口は成功し、内側の段2は既存エラーになる。"""
    inputs = _receiving_task_change_closure_inputs(base_has_placeholder=False)
    checker.validate_receiving_task_change_closure(*inputs)

    with pytest.raises(checker.CatalogError, match="基準版に受取先置換の対象行がない"):
        checker._validate_receiving_task_mutant_map_change(
            inputs.base_mapping, inputs.current_mapping
        )


def test_receiving_task_change_scope_rejects_another_contract_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """差分閉包の段1で許可3本以外の contracts パスを拒否する。"""
    assets, seal, _paths = _repository_oracle_assets()
    base_mapping = _receiving_task_base_json(
        "contracts/authz/claim-mutant-map.json"
    )
    base_seal = _receiving_task_base_json(f"contracts/authz/{ORACLE_SEAL_FILE}")
    base_mcdc_map_text = _receiving_task_base_text("contracts/authz/mcdc-map.json")
    mcdc_map_text = _receiving_task_head_text("contracts/authz/mcdc-map.json")
    changed_paths = checker._receiving_task_changed_contract_paths(REPOSITORY_ROOT)
    forbidden_paths = changed_paths | {"contracts/authz/auth-catalog.json"}
    with pytest.raises(checker.CatalogError):
        checker._validate_receiving_task_changed_paths(forbidden_paths)

    monkeypatch.setattr(
        checker, "_validate_receiving_task_changed_paths", lambda *_args: None
    )
    checker.validate_receiving_task_change_closure(
        base_mapping,
        assets["claim_mutant_map"],
        base_seal,
        seal,
        base_mcdc_map_text,
        mcdc_map_text,
        forbidden_paths,
    )


def test_receiving_task_repository_closure_uses_merge_base_and_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """差分閉包の4段が動的 merge-base と HEAD のスナップショットだけを読む。"""
    expected_base = _receiving_task_base_revision()
    assert checker._receiving_task_merge_base(REPOSITORY_ROOT) == expected_base
    assert not hasattr(checker, "RECEIVING_TASK_CHANGE_BASE_REVISION")

    text_reads: list[tuple[str, str]] = []
    changed_path_bases: list[str | None] = []
    original_text_reader = checker._git_text_at_revision
    original_changed_paths = checker._receiving_task_changed_contract_paths

    def recording_text_reader(root: Path, revision: str, path: str) -> str:
        text_reads.append((revision, path))
        return original_text_reader(root, revision, path)

    def recording_changed_paths(
        root: Path, base_revision: str | None = None
    ) -> set[str]:
        changed_path_bases.append(base_revision)
        return original_changed_paths(root, base_revision)

    monkeypatch.setattr(checker, "_git_text_at_revision", recording_text_reader)
    monkeypatch.setattr(
        checker, "_receiving_task_changed_contract_paths", recording_changed_paths
    )
    checker._validate_receiving_task_repository_change_closure(REPOSITORY_ROOT)

    expected_paths = {
        "contracts/authz/claim-mutant-map.json",
        f"contracts/authz/{ORACLE_SEAL_FILE}",
        "contracts/authz/mcdc-map.json",
    }
    assert set(text_reads) == {
        (revision, path)
        for revision in (expected_base, "HEAD")
        for path in expected_paths
    }
    assert changed_path_bases == [expected_base]


def test_mutant_map_change_closure_rejects_every_unapproved_change() -> None:
    """差分閉包の段2で非対象・別field・集合・未知keyの変更を拒否する。"""
    assets, _seal, _paths = _repository_oracle_assets()
    current = assets["claim_mutant_map"]
    base = _receiving_task_base_json("contracts/authz/claim-mutant-map.json")
    mutations: list[dict[str, Any]] = []

    non_target = copy.deepcopy(current)
    next(
        claim
        for claim in non_target["claims"]
        if claim["runtime_test_owner"]["id"].startswith("TSK-250.runtime.")
    )["receiving_task_id"] = "TSK-217"
    mutations.append(non_target)

    other_field = copy.deepcopy(current)
    next(
        claim
        for claim in other_field["claims"]
        if claim["execution_class"] == "contract_only"
        and claim["runtime_test_owner"]["id"].startswith(
            checker.RUNTIME_HANDOFF_OWNER_PREFIX
        )
    )["contract_only_reason_code"] = "ddl_target_pending"
    mutations.append(other_field)

    unknown_key = copy.deepcopy(current)
    unknown_key["unapproved_leaf"] = True
    mutations.append(unknown_key)

    removed = copy.deepcopy(current)
    removed["claims"].pop()
    mutations.append(removed)

    reordered = copy.deepcopy(current)
    reordered["claims"][0], reordered["claims"][1] = (
        reordered["claims"][1],
        reordered["claims"][0],
    )
    mutations.append(reordered)

    for mutated in mutations:
        with pytest.raises(checker.CatalogError):
            checker._validate_receiving_task_mutant_map_change(base, mutated)


def test_mutant_map_unapproved_change_passes_without_stage_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """段2の負例が追加した完全一致検査だけにより落ちると示す。"""
    assets, seal, _paths = _repository_oracle_assets()
    current = copy.deepcopy(assets["claim_mutant_map"])
    next(
        claim
        for claim in current["claims"]
        if claim["runtime_test_owner"]["id"].startswith("TSK-250.runtime.")
    )["receiving_task_id"] = "TSK-217"
    base_mapping = _receiving_task_base_json(
        "contracts/authz/claim-mutant-map.json"
    )
    base_seal = _receiving_task_base_json(f"contracts/authz/{ORACLE_SEAL_FILE}")
    base_mcdc_map_text = _receiving_task_base_text("contracts/authz/mcdc-map.json")
    mcdc_map_text = _receiving_task_head_text("contracts/authz/mcdc-map.json")
    monkeypatch.setattr(
        checker, "_validate_receiving_task_mutant_map_change", lambda *_args: None
    )
    checker.validate_receiving_task_change_closure(
        base_mapping,
        current,
        base_seal,
        seal,
        base_mcdc_map_text,
        mcdc_map_text,
        checker._receiving_task_changed_contract_paths(REPOSITORY_ROOT),
    )


def test_oracle_seal_change_closure_rejects_every_unapproved_change() -> None:
    """差分閉包の段3で対象digest以外の値・集合・順序変更を拒否する。"""
    _assets, current, _paths = _repository_oracle_assets()
    base = _receiving_task_base_json(f"contracts/authz/{ORACLE_SEAL_FILE}")
    mutations: list[dict[str, Any]] = []

    unknown_key = copy.deepcopy(current)
    unknown_key["unapproved_leaf"] = True
    mutations.append(unknown_key)

    oracle_commit = copy.deepcopy(current)
    oracle_commit["oracle_commit"] = "0" * 40
    mutations.append(oracle_commit)

    input_digest = copy.deepcopy(current)
    input_digest["input_assets"][0]["git_blob_digest"] = "0" * 40
    mutations.append(input_digest)

    other_sealed_digest = copy.deepcopy(current)
    next(
        row
        for row in other_sealed_digest["sealed_assets"]
        if row["path"] != "contracts/authz/claim-mutant-map.json"
    )["canonical_sha256"] = "0" * 64
    mutations.append(other_sealed_digest)

    reordered = copy.deepcopy(current)
    reordered["sealed_assets"][0], reordered["sealed_assets"][1] = (
        reordered["sealed_assets"][1],
        reordered["sealed_assets"][0],
    )
    mutations.append(reordered)

    for mutated in mutations:
        with pytest.raises(checker.CatalogError):
            checker._validate_receiving_task_oracle_seal_change(base, mutated)


def test_oracle_seal_unapproved_change_passes_without_stage_three(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """段3の負例が追加した完全一致検査だけにより落ちると示す。"""
    assets, current, _paths = _repository_oracle_assets()
    mutated = copy.deepcopy(current)
    mutated["review_policy"] = "unapproved"
    base_mapping = _receiving_task_base_json(
        "contracts/authz/claim-mutant-map.json"
    )
    base_seal = _receiving_task_base_json(f"contracts/authz/{ORACLE_SEAL_FILE}")
    base_mcdc_map_text = _receiving_task_base_text("contracts/authz/mcdc-map.json")
    mcdc_map_text = _receiving_task_head_text("contracts/authz/mcdc-map.json")
    monkeypatch.setattr(
        checker, "_validate_receiving_task_oracle_seal_change", lambda *_args: None
    )
    checker.validate_receiving_task_change_closure(
        base_mapping,
        assets["claim_mutant_map"],
        base_seal,
        mutated,
        base_mcdc_map_text,
        mcdc_map_text,
        checker._receiving_task_changed_contract_paths(REPOSITORY_ROOT),
    )


def test_mcdc_map_change_closure_rejects_every_unapproved_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """段4で claim mutant map の digest 以外を拒否し、専用検査の因果を示す。"""
    assets, seal, _paths = _repository_oracle_assets()
    current = _receiving_task_head_json("contracts/authz/mcdc-map.json")
    base_text = _receiving_task_base_text("contracts/authz/mcdc-map.json")
    mutations: list[str] = []

    decision = copy.deepcopy(current)
    decision["decisions"][0]["decision_form"] = "OR"
    mutations.append(_json_text(decision))

    body_manifest = copy.deepcopy(current)
    body_manifest["sources"]["body_manifest"]["blob_digest"] = "0" * 40
    mutations.append(_json_text(body_manifest))

    unknown_key = copy.deepcopy(current)
    unknown_key["unapproved_leaf"] = True
    mutations.append(_json_text(unknown_key))

    reordered_sources = copy.deepcopy(current)
    sources = reordered_sources["sources"]
    reordered_sources["sources"] = {
        "claim_mutant_map": sources["claim_mutant_map"],
        "body_manifest": sources["body_manifest"],
    }
    mutations.append(_json_text(reordered_sources))

    for mutated_text in mutations:
        with pytest.raises(checker.CatalogError):
            checker._validate_receiving_task_mcdc_map_change(base_text, mutated_text)

    base_mapping = _receiving_task_base_json(
        "contracts/authz/claim-mutant-map.json"
    )
    base_seal = _receiving_task_base_json(f"contracts/authz/{ORACLE_SEAL_FILE}")
    monkeypatch.setattr(
        checker, "_validate_receiving_task_mcdc_map_change", lambda *_args: None
    )
    for mutated_text in mutations:
        checker.validate_receiving_task_change_closure(
            base_mapping,
            assets["claim_mutant_map"],
            base_seal,
            seal,
            base_text,
            mutated_text,
            checker._receiving_task_changed_contract_paths(REPOSITORY_ROOT),
        )


def test_mcdc_map_change_closure_rejects_duplicate_keys_in_base_and_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """段4が基準版とHEADの decisions 重複を拒否し、専用検査の因果を示す。"""
    path = "contracts/authz/mcdc-map.json"
    base_text = _receiving_task_base_text(path)
    head_text = _receiving_task_head_text(path)

    def inject_duplicate_decisions(text: str) -> str:
        mutated = text.replace(
            '  "decisions": [', '  "decisions": [],\n  "decisions": [', 1
        )
        assert mutated != text
        assert len(json.loads(mutated)["decisions"]) == len(
            json.loads(text)["decisions"]
        )
        return mutated

    duplicate_base_text = inject_duplicate_decisions(base_text)
    duplicate_head_text = inject_duplicate_decisions(head_text)
    mutations = (
        (duplicate_base_text, head_text),
        (base_text, duplicate_head_text),
    )
    for mutated_base_text, mutated_head_text in mutations:
        with pytest.raises(checker.CatalogError, match="JSON キーが重複"):
            checker._validate_receiving_task_mcdc_map_change(
                mutated_base_text, mutated_head_text
            )

    assets, seal, _paths = _repository_oracle_assets()
    base_mapping = _receiving_task_base_json(
        "contracts/authz/claim-mutant-map.json"
    )
    base_seal = _receiving_task_base_json(f"contracts/authz/{ORACLE_SEAL_FILE}")
    monkeypatch.setattr(
        checker, "_validate_receiving_task_mcdc_map_change", lambda *_args: None
    )
    for mutated_base_text, mutated_head_text in mutations:
        checker.validate_receiving_task_change_closure(
            base_mapping,
            assets["claim_mutant_map"],
            base_seal,
            seal,
            mutated_base_text,
            mutated_head_text,
            checker._receiving_task_changed_contract_paths(REPOSITORY_ROOT),
        )


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_mcdc_map_change_closure_rejects_nonstandard_constants_in_base_and_head(
    constant: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """段4が基準版とHEADの標準外数値定数を拒否し、parse_constantの因果を示す。"""
    path = "contracts/authz/mcdc-map.json"
    base_text = _receiving_task_base_text(path)
    head_text = _receiving_task_head_text(path)

    def inject_nonstandard_digest(text: str) -> str:
        parsed = json.loads(text)
        digest = parsed["sources"]["claim_mutant_map"]["blob_digest"]
        mutated = text.replace(
            f'"blob_digest": "{digest}"', f'"blob_digest": {constant}', 1
        )
        assert mutated != text
        return mutated

    mutations = (
        (inject_nonstandard_digest(base_text), head_text),
        (base_text, inject_nonstandard_digest(head_text)),
    )
    for mutated_base_text, mutated_head_text in mutations:
        with pytest.raises(checker.CatalogError, match=constant):
            checker._validate_receiving_task_mcdc_map_change(
                mutated_base_text, mutated_head_text
            )

    def parse_without_constant_rejection(text: str, _label: str) -> dict[str, Any]:
        value = json.loads(
            text, object_pairs_hook=checker._reject_duplicate_json_object
        )
        assert isinstance(value, dict)
        return value

    monkeypatch.setattr(
        checker, "_parse_unique_mcdc_map_json", parse_without_constant_rejection
    )
    for mutated_base_text, mutated_head_text in mutations:
        checker._validate_receiving_task_mcdc_map_change(
            mutated_base_text, mutated_head_text
        )


def _generalized_table_privilege_mapping() -> dict[str, Any]:
    """複数 target 対を宣言した実資産の独立 copy を返す。"""
    assets, _seal, _paths = _repository_oracle_assets()
    mapping = copy.deepcopy(assets["claim_mutant_map"])
    assert "target_pairs" in mapping["table_privilege_mutation_rule"]
    return mapping


def test_table_privilege_mutation_targets_are_closed_and_unique() -> None:
    """宣言外 target の mutant と target 対の重複を拒否する。"""
    undeclared = _generalized_table_privilege_mapping()
    template = next(
        mutant
        for mutant in undeclared["mutants"]
        if mutant["mutant_id"]
        == "MUT:CONFIG:CFG_GRANT_MANAGEMENT_EXECUTE_TO_APP"
    )
    unexpected = copy.deepcopy(template)
    unexpected["mutant_id"] = (
        "MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_BUSINESS_ROWS_DML"
    )
    unexpected["operator_id"] = "grant_app_role_control_table_dml"
    unexpected["target_element_ids"] = [
        "TABLE-PRIVILEGE:probe_business_rows:app_role:INSERT",
        "TABLE-PRIVILEGE:probe_business_rows:app_role:UPDATE",
        "TABLE-PRIVILEGE:probe_business_rows:app_role:DELETE",
    ]
    undeclared["mutants"].append(unexpected)
    for claim_id in unexpected["claim_ids"]:
        claim = next(
            claim for claim in undeclared["claims"] if claim["claim_id"] == claim_id
        )
        claim["mutant_ids"].append(unexpected["mutant_id"])

    duplicate = _generalized_table_privilege_mapping()
    target_pairs = duplicate["table_privilege_mutation_rule"]["target_pairs"]
    target_pairs.append(copy.deepcopy(target_pairs[0]))

    failures: list[tuple[str, str]] = []
    for case_name, mapping, expected_error in (
        (
            "undeclared_target",
            undeclared,
            "構成軸 mutant が基礎集合+表権限派生集合と exact-set 不一致",
        ),
        ("duplicate_target", duplicate, "表権限 mutant の target pair が重複"),
    ):
        try:
            _validate_mutant_map(mapping)
        except checker.CatalogError as error:
            if expected_error not in str(error):
                failures.append((case_name, str(error)))
        else:
            failures.append((case_name, "検査が成功した"))

    assert failures == []


def test_required_table_privilege_targets_reject_self_consistent_shrinkage() -> None:
    """必須 target の権限縮小と pair 削除を外部固定集合で拒否する。"""
    shrink = _generalized_table_privilege_mapping()
    groups_target = next(
        target
        for target in shrink["table_privilege_mutation_rule"]["target_pairs"]
        if target["target_role_id"] == "app_role"
        and target["target_table_id"] == "probe_groups"
    )
    groups_target["privilege_groups"][0]["grant_privilege_ids"] = ["INSERT"]
    groups_mutant = next(
        mutant
        for mutant in shrink["mutants"]
        if mutant["mutant_id"]
        == "MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML"
    )
    groups_mutant["target_element_ids"] = [
        "TABLE-PRIVILEGE:probe_groups:app_role:INSERT"
    ]

    missing_pair = _generalized_table_privilege_mapping()
    missing_target = next(
        target
        for target in missing_pair["table_privilege_mutation_rule"]["target_pairs"]
        if target["target_role_id"] == "app_role"
        and target["target_table_id"] == "probe_invitations"
    )
    missing_pair["table_privilege_mutation_rule"]["target_pairs"].remove(
        missing_target
    )
    missing_mutant_id = "MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML"
    missing_pair["mutants"] = [
        mutant
        for mutant in missing_pair["mutants"]
        if mutant["mutant_id"] != missing_mutant_id
    ]
    for claim in missing_pair["claims"]:
        if missing_mutant_id in claim["mutant_ids"]:
            claim["mutant_ids"].remove(missing_mutant_id)
    missing_pair["two_factor_interactions"] = [
        interaction
        for interaction in missing_pair["two_factor_interactions"]
        if missing_mutant_id not in interaction["factor_mutant_ids"]
    ]

    escaped: list[str] = []
    for case_name, mapping in (
        ("shrunken_grants", shrink),
        ("missing_target_pair", missing_pair),
    ):
        try:
            _validate_mutant_map(mapping)
        except checker.CatalogError:
            pass
        else:
            escaped.append(case_name)

    assert escaped == []


def test_legacy_table_privilege_mutation_rule_remains_compatible() -> None:
    """従来の management target 1対から同じ8 mutant を導出する。"""
    assets, _seal, _paths = _repository_oracle_assets()
    ddl_result = checker.validate_ddl_elements(
        assets["ddl_elements"], REPOSITORY_ROOT
    )
    legacy_rule = {
        "source_asset_path": "contracts/authz/ddl-elements.json",
        "source_json_pointer": "/enums/table_privilege_ids",
        "mutant_id_template": (
            f"{checker.TABLE_PRIVILEGE_MUTANT_PREFIX}{{privilege_id}}"
        ),
        "target_role_id": "management_caller",
        "target_table_id": "probe_management_effects",
        "claim_ids": sorted(checker.MANAGEMENT_PROBE_CLAIM_IDS),
    }

    targets = checker._table_privilege_mutation_targets(
        legacy_rule,
        ddl_result,
        frozenset(checker.MANAGEMENT_PROBE_CLAIM_IDS),
    )

    assert len(targets) == 1
    target = targets[0]
    assert target["target_role_id"] == "management_caller"
    assert target["target_table_id"] == "probe_management_effects"
    assert target["claim_ids"] == checker.MANAGEMENT_PROBE_CLAIM_IDS
    assert {
        group["privilege_id"] for group in target["privilege_groups"]
    } == ddl_result["table_privilege_ids"]
    assert all(
        group["grant_privilege_ids"] == (group["privilege_id"],)
        for group in target["privilege_groups"]
    )


def test_app_role_control_dml_regrant_mutants_are_red() -> None:
    """制御4表の app_role DML 再付与を既存の kill 契約で拒否する。"""
    requirement_catalog, _requirement_lock = _repository_catalog_and_lock()
    derived_assets, _derived_locks, _derived_paths = _repository_derived_assets()
    oracle_assets, _seal, _paths = _repository_oracle_assets()
    mapping = oracle_assets["claim_mutant_map"]
    targets = [
        target
        for target in mapping["table_privilege_mutation_rule"]["target_pairs"]
        if target["target_role_id"] == "app_role"
    ]
    mutant_by_id = {
        mutant["mutant_id"]: mutant for mutant in mapping["mutants"]
    }
    failures: list[tuple[str, str]] = []

    for target in targets:
        table_id = target["target_table_id"]
        group = target["privilege_groups"][0]
        mutant_id = target["mutant_id_template"].replace(
            "{privilege_id}", group["privilege_id"]
        )
        mutant = mutant_by_id[mutant_id]
        if (
            mutant["axis"] != "configuration"
            or mutant["expected_drift_outcome"] != "red"
            or mutant["runtime_kill_required"] is not True
            or mutant["expected_runtime_outcome"] != "kill"
            or mutant["runtime_kill_waiver_reason"] is not None
        ):
            failures.append((mutant_id, "kill 契約が不正"))
            continue

        mutated_ddl = copy.deepcopy(oracle_assets["ddl_elements"])
        acl = next(
            acl
            for acl in mutated_ddl["acl_expectations"]
            if acl["object_kind"] == "table"
            and acl["object_id"] == table_id
            and acl["grantee_role_id"] == "app_role"
        )
        acl["privilege_ids"] = sorted(
            set(acl["privilege_ids"]) | set(group["grant_privilege_ids"])
        )
        try:
            ddl_result = checker.validate_ddl_elements(mutated_ddl, REPOSITORY_ROOT)
            checker.validate_claim_mutant_map(
                mapping,
                requirement_catalog,
                derived_assets["route_registry"],
                derived_assets["http_matrix"],
                ddl_result,
                REPOSITORY_ROOT,
                frozenset(
                    {IMPLEMENTED_CATALOG_TEST_ID, IMPLEMENTED_ORACLE_TEST_ID}
                ),
            )
        except checker.CatalogError as error:
            expected_error = (
                f"app_role/{table_id}/DML: "
                "表権限 mutant の再付与対象が基準ACLですでに許可されている"
            )
            if expected_error not in str(error):
                failures.append((mutant_id, str(error)))
        else:
            failures.append((mutant_id, "検査が成功した"))

    assert len(targets) == 4
    assert failures == []


def test_repository_oracle_assets_are_valid() -> None:
    """全claim・mutant・cut set・境界・証跡と封印を統合検査する。"""
    assets, seal, paths = _repository_oracle_assets()

    result = _validate_repository_oracle(assets, seal, paths)
    mutant_result = result["mutants"]

    assert mutant_result["execution_counts"] == Counter(
        {"contract_only": 165, "probe_executable": 33}
    )
    assert mutant_result["axis_counts"] == Counter(
        {"authorization_predicate": 205, "configuration": 24, "r8_provisioning": 2}
    )
    assert mutant_result["positive_case_count"] == 6
    assert len(mutant_result["positive_kill_mutant_ids"]) == 2
    assert result["attack"]["cut_set_count"] == 24
    assert result["attack"]["multi_factor_cut_set_count"] == 3
    assert result["rejected"]["rejection_count"] == 3
    assert result["boundary"]["all_logical_count"] == 29


def test_oracle_reseal_is_only_enabled_by_the_dedicated_flag() -> None:
    """通常引数は再封印せず、専用フラグだけが明示更新を有効にする。"""
    normal = checker.parse_args([])
    explicit = checker.parse_args(["--reseal-oracle"])

    assert normal.reseal_oracle is False
    assert explicit.reseal_oracle is True
    assert explicit.reseal is False
    assert explicit.reseal_derived is False


def _validate_boundary_asset(boundary: dict[str, Any]) -> None:
    """境界資産だけを当該 semantic validator へ直接渡す。"""
    derived_assets, _locks, _paths = _repository_derived_assets()
    checker.validate_boundary_proposal(
        boundary, derived_assets["auth_catalog"], REPOSITORY_ROOT
    )


def test_boundary_owner_population_and_final_values_are_closed() -> None:
    """基準版から導出した owner 5 箇所を裁定後の値で閉じる。"""
    base = _base_json("contracts/authz/boundary-proposal.json")
    current = _read_repository_json("contracts/authz/boundary-proposal.json")
    owner_paths = _iter_matching_key_paths(base)
    expected_base_values: dict[ArrayPath, str] = {
        ("boundaries", 0, "aggregation_owner_task_id"): "TSK-235",
        ("boundaries", 1, "aggregation_owner_task_id"): "TSK-235",
        ("boundaries", 2, "aggregation_owner_task_id"): "TSK-250",
        ("deferred_equivalence_contract", "owner_task_id"): "TSK-235",
        ("trust_boundary", "verification_owner_task_id"): "TSK-217",
    }
    assert {path: _value_at_path(base, path) for path in owner_paths} == (
        expected_base_values
    )
    _validate_boundary_asset(current)

    mutations: list[tuple[str, dict[str, Any]]] = []
    control_path = ("boundaries", 1, "aggregation_owner_task_id")
    for path in owner_paths:
        mutated = copy.deepcopy(current)
        parent, key = _parent_and_key(mutated, path)
        assert isinstance(parent, dict) and isinstance(key, str)
        for replacement in ("TSK-SIMILAR-BUT-WRONG", ""):
            candidate = copy.deepcopy(mutated)
            candidate_parent, candidate_key = _parent_and_key(candidate, path)
            assert isinstance(candidate_parent, dict)
            assert isinstance(candidate_key, str)
            candidate_parent[candidate_key] = replacement
            mutations.append((f"{path}:{replacement!r}", candidate))
        if path != control_path:
            removed = copy.deepcopy(mutated)
            removed_parent, removed_key = _parent_and_key(removed, path)
            assert isinstance(removed_parent, dict)
            assert isinstance(removed_key, str)
            del removed_parent[removed_key]
            mutations.append((f"{path}:deleted", removed))
        base_value = expected_base_values[path]
        if path == control_path or _value_at_path(current, path) != base_value:
            old_value = copy.deepcopy(current)
            old_parent, old_key = _parent_and_key(old_value, path)
            assert isinstance(old_parent, dict) and isinstance(old_key, str)
            old_parent[old_key] = base_value
            mutations.append((f"{path}:base-value", old_value))

    escaped: list[str] = []
    for label, mutated in mutations:
        try:
            _validate_boundary_asset(mutated)
        except checker.CatalogError:
            pass
        else:
            escaped.append(label)
    assert escaped == []


def test_owner_mutations_pass_when_the_owner_check_is_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """owner 5箇所の負例が追加した専用検査だけにより落ちると示す。"""
    base = _base_json("contracts/authz/boundary-proposal.json")
    current = _read_repository_json("contracts/authz/boundary-proposal.json")
    mutations: list[dict[str, Any]] = []
    for path in _iter_matching_key_paths(base):
        mutated = copy.deepcopy(current)
        parent, key = _parent_and_key(mutated, path)
        assert isinstance(parent, dict) and isinstance(key, str)
        parent[key] = "TSK-WITHOUT-OWNER-CHECK"
        mutations.append(mutated)

    monkeypatch.setattr(
        checker, "_validate_boundary_owner_assignments", lambda *_args: None
    )
    for mutated in mutations:
        _validate_boundary_asset(mutated)


def test_boundary_and_review_ids_reject_duplicate_rows_before_folding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """境界・裁定行の重複を索引化前に拒否し、専用検査の因果も示す。"""
    boundary = _read_repository_json("contracts/authz/boundary-proposal.json")
    mutations: list[dict[str, Any]] = []
    for key in ("boundaries", "pending_human_reviews"):
        mutated = copy.deepcopy(boundary)
        rows = mutated[key]
        assert isinstance(rows, list) and rows
        rows.append(copy.deepcopy(rows[0]))
        mutations.append(mutated)
        with pytest.raises(checker.CatalogError):
            _validate_boundary_asset(mutated)

    monkeypatch.setattr(
        checker,
        "_index_unique_object_rows",
        lambda rows, key, _label: {str(row.get(key)): row for row in rows},
    )
    for mutated in mutations:
        _validate_boundary_asset(mutated)


def test_boundary_proposal_base_leaves_follow_the_approved_classification() -> None:
    """可動ポインタを除く全葉を変更・不変・削除へ分ける。"""
    base = _base_json("contracts/authz/boundary-proposal.json")
    current = _read_repository_json("contracts/authz/boundary-proposal.json")
    seal = _read_repository_json(f"contracts/authz/{ORACLE_SEAL_FILE}")
    pointer_path = ("oracle_context", "oracle_commit")
    removed = {("boundaries", 1, "aggregation_owner_task_id")}
    changed = {
        ("proposal_status",): "tsk_235_confirmed",
        (
            "boundaries",
            0,
            "aggregation_owner_task_id",
        ): "3d993b75-e687-818d-8cb8-ec57508e73e0",
        (
            "deferred_equivalence_contract",
            "owner_task_id",
        ): "3d993b75-e687-818d-8cb8-ec57508e73e0",
        ("pending_human_reviews", 0, "status"): "human_decided",
        ("pending_human_reviews", 1, "status"): "human_decided",
    }
    base_paths = set(_iter_leaf_paths(base))
    current_paths = set(_iter_leaf_paths(current))

    assert current_paths == base_paths - removed
    assert _value_at_path(current, pointer_path) == seal["oracle_commit"]
    for path in base_paths - removed - {pointer_path}:
        expected = changed.get(path, _value_at_path(base, path))
        assert _value_at_path(current, path) == expected

    unexpected = copy.deepcopy(current)
    unexpected["unapproved_leaf"] = True
    with pytest.raises(checker.CatalogError):
        _validate_boundary_asset(unexpected)


def test_s5_mutations_pass_when_the_decision_check_is_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S-5 の状態・凍結値・代替値・安定 ID が専用検査で落ちると示す。"""
    boundary = _read_repository_json("contracts/authz/boundary-proposal.json")
    mutations: list[dict[str, Any]] = []
    for path, value in (
        (("proposal_status",), "pending_tsk_235_confirmation"),
        (("pending_human_reviews", 0, "status"), "pending_human_decision"),
        (("pending_human_reviews", 1, "status"), "pending_human_review"),
        (("pending_human_reviews", 0, "frozen_value"), 7),
        (("pending_human_reviews", 1, "frozen_value"), 28),
        (("pending_human_reviews", 0, "alternative_value"), 8),
        (("pending_human_reviews", 1, "alternative_value"), 7),
        (("pending_human_reviews", 0, "review_id"), "RENAMED-COUNT"),
        (("pending_human_reviews", 1, "review_id"), "RENAMED-SCOPE"),
    ):
        mutated = copy.deepcopy(boundary)
        parent, key = _parent_and_key(mutated, path)
        if isinstance(parent, dict):
            assert isinstance(key, str)
            parent[key] = value
        else:
            assert isinstance(key, int)
            parent[key] = value
        mutations.append(mutated)

    missing_alternative = copy.deepcopy(boundary)
    del missing_alternative["pending_human_reviews"][0]["alternative_value"]
    mutations.append(missing_alternative)

    monkeypatch.setattr(
        checker,
        "_validate_boundary_decisions",
        lambda raw, _expected: raw["pending_human_reviews"],
    )
    for mutated in mutations:
        _validate_boundary_asset(mutated)


def test_every_boundary_leaf_mutation_reaches_the_semantic_validator() -> None:
    """裁定後の境界資産の全葉を直接変異し、意味検査で red にする。"""
    boundary = _read_repository_json("contracts/authz/boundary-proposal.json")
    escaped: list[tuple[ArrayPath, str]] = []

    for path in _iter_leaf_paths(boundary):
        for mutation in ("change", "delete"):
            mutated = _mutate_leaf(boundary, path, delete=mutation == "delete")
            try:
                _validate_boundary_asset(mutated)
            except checker.CatalogError:
                pass
            else:
                escaped.append((path, mutation))

    assert escaped == []


def test_ddl_scope_has_four_exact_final_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """scope の4キーを直接変異し、専用意味検査だけが拒否すると示す。"""
    assets, _seal, _paths = _repository_oracle_assets()
    ddl = assets["ddl_elements"]
    expected = {
        "status": "verified_probe_configuration",
        "product_schema": False,
        "contains_sql_body": False,
        "second_group_approval_required": False,
    }
    assert ddl["scope"] == expected

    mutations: list[dict[str, Any]] = []
    for key, value in expected.items():
        mutated = copy.deepcopy(ddl)
        mutated["scope"][key] = _changed_leaf_value(value)
        mutations.append(mutated)
        missing = copy.deepcopy(ddl)
        del missing["scope"][key]
        mutations.append(missing)

    for mutated in mutations:
        with pytest.raises(checker.CatalogError):
            checker.validate_ddl_elements(mutated, REPOSITORY_ROOT)

    mutated = copy.deepcopy(ddl)
    mutated["scope"]["status"] = "candidate_probe_only"
    monkeypatch.setattr(checker, "_validate_ddl_scope", lambda _raw: None)
    checker.validate_ddl_elements(mutated, REPOSITORY_ROOT)


def test_g_entry_population_matches_the_seal_derived_partition() -> None:
    """g の全入口・全要素が validator の判定を返したと示す。"""
    seal = _base_json(f"contracts/authz/{ORACLE_SEAL_FILE}")
    _output, decisions = _derive_g_multiplicity()
    actual_counts = _actual_g_decision_counts(decisions)
    expected, excluded = _g_entry_partition_from_seal(seal)

    _assert_g_entry_population(frozenset(actual_counts), seal)
    _assert_g_decision_counts(actual_counts, _expected_g_decision_counts(seal))
    actual_keys = tuple(
        (entry_path, path, index)
        for entry_path, path, index, _green in decisions
    )
    assert len(actual_keys) == len(set(actual_keys))
    assert frozenset(actual_keys) == _expected_g_decision_keys(seal)
    assert excluded == frozenset(_base_frozen_asset_paths()) - expected


def test_g_deriver_rejects_a_skipped_entry() -> None:
    """導出器内で1入口の validator を全省略すると入口検査が red になる。"""
    seal = _base_json(f"contracts/authz/{ORACLE_SEAL_FILE}")
    expected_counts = _expected_g_decision_counts(seal)
    omitted_entry = min(
        expected_counts, key=lambda entry: (expected_counts[entry], entry)
    )

    def skip_inside_deriver(
        entry_path: str,
        _array_path: ArrayPath,
        _index: int,
        validate_and_record: GDecisionRecorder,
    ) -> None:
        if entry_path == omitted_entry:
            return
        validate_and_record()

    _output, decisions = _derive_g_multiplicity_with_dispatcher(
        skip_inside_deriver
    )
    actual_counts = _actual_g_decision_counts(decisions)
    with pytest.raises(AssertionError, match="g の入口集合が不一致"):
        _assert_g_entry_population(frozenset(actual_counts), seal)


def test_g_deriver_rejects_one_skipped_decision() -> None:
    """導出器内で1要素の validator を省略すると判定件数が red になる。"""
    seal = _base_json(f"contracts/authz/{ORACLE_SEAL_FILE}")
    expected_counts = _expected_g_decision_counts(seal)
    partial_entry = min(
        expected_counts, key=lambda entry: (expected_counts[entry], entry)
    )
    decision_skipped = False

    def skip_inside_deriver(
        entry_path: str,
        _array_path: ArrayPath,
        _index: int,
        validate_and_record: GDecisionRecorder,
    ) -> None:
        nonlocal decision_skipped
        if entry_path == partial_entry and not decision_skipped:
            decision_skipped = True
            return
        validate_and_record()

    _output, decisions = _derive_g_multiplicity_with_dispatcher(
        skip_inside_deriver
    )
    actual_counts = _actual_g_decision_counts(decisions)
    assert decision_skipped
    _assert_g_entry_population(frozenset(actual_counts), seal)
    with pytest.raises(AssertionError, match="g の入口別判定件数が不一致"):
        _assert_g_decision_counts(actual_counts, expected_counts)


def test_g_arrays_reject_every_element_duplication_at_the_semantic_entry() -> None:
    """基準版へ g を実行し、出力した全配列・全要素の複製を拒否する。"""
    assets, seal, paths = _repository_oracle_assets()
    g_paths = _derive_g_multiplicity_array_paths()
    escaped: list[tuple[str, ArrayPath, int]] = []
    attempts = 0
    expected_attempts = 0

    for name, path in g_paths:
        source = seal if name == "oracle_seal" else assets[name]
        target = _value_at_path(source, path)
        assert isinstance(target, list) and target
        expected_attempts += len(target)
        for index in range(len(target)):
            mutated = _duplicate_array_element(source, path, index)
            try:
                if name == "oracle_seal":
                    checker.validate_oracle_seal(
                        mutated, assets, paths, REPOSITORY_ROOT
                    )
                else:
                    mutated_assets = copy.deepcopy(assets)
                    mutated_assets[name] = mutated
                    _validate_repository_oracle(
                        mutated_assets, seal, paths, verify_seal=False
                    )
            except checker.CatalogError:
                pass
            else:
                escaped.append((name, path, index))
            attempts += 1

    assert g_paths
    assert attempts == expected_attempts
    assert escaped == []


def test_g_duplicates_pass_when_the_new_multiplicity_checks_are_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """g の負例が既存検査でなく追加した多重度検査により落ちると示す。"""
    assets, seal, paths = _repository_oracle_assets()
    monkeypatch.setattr(
        checker, "_validate_json_array_multiplicity", lambda *_args: None
    )
    monkeypatch.setattr(
        checker, "_validate_object_path_uniqueness", lambda *_args: None
    )
    monkeypatch.setattr(
        checker,
        "_index_unique_object_rows",
        lambda rows, key, _label: {str(row.get(key)): row for row in rows},
    )
    escaped: list[tuple[str, ArrayPath]] = []

    for name, path in _derive_g_multiplicity_array_paths():
        source = seal if name == "oracle_seal" else assets[name]
        mutated = _duplicate_array_element(source, path, 0)
        try:
            if name == "oracle_seal":
                checker.validate_oracle_seal(
                    mutated, assets, paths, REPOSITORY_ROOT
                )
            else:
                mutated_assets = copy.deepcopy(assets)
                mutated_assets[name] = mutated
                _validate_repository_oracle(
                    mutated_assets, seal, paths, verify_seal=False
                )
        except checker.CatalogError:
            escaped.append((name, path))

    assert escaped == []


def test_frozen_assets_have_no_duplicates() -> None:
    """固定基準版の seal が導く凍結 15 パスを同じ入口で恒久検査する。"""
    paths = _base_frozen_asset_paths()
    array_count = _validate_frozen_asset_set(REPOSITORY_ROOT, paths)

    assert len(paths) == 15
    assert array_count > 0


def test_frozen_path_derivation_covers_both_asset_tables_and_the_seal() -> None:
    """sealed/input の追加と seal 自身の3入口を独立した探針で検査する。"""
    seal = _base_json(f"contracts/authz/{ORACLE_SEAL_FILE}")
    baseline = _frozen_asset_paths_from_seal(seal)

    added_sealed = copy.deepcopy(seal)
    sealed_probe = copy.deepcopy(added_sealed["sealed_assets"][0])
    sealed_probe["path"] = "contracts/authz/sealed-probe.json"
    added_sealed["sealed_assets"].append(sealed_probe)

    added_input = copy.deepcopy(seal)
    input_probe = copy.deepcopy(added_input["input_assets"][0])
    input_probe["path"] = "contracts/authz/input-probe.json"
    added_input["input_assets"].append(input_probe)

    assert len(_frozen_asset_paths_from_seal(added_sealed)) == len(baseline) + 1
    assert len(_frozen_asset_paths_from_seal(added_input)) == len(baseline) + 1
    assert len(_frozen_asset_paths_from_seal(seal, include_seal=False)) == (
        len(baseline) - 1
    )


def test_each_frozen_asset_is_individually_required_by_the_multiplicity_scan(
    tmp_path: Path,
) -> None:
    """15パスを1件ずつ攻撃し、対象集合を狭めるとその1件だけ逃げると示す。"""
    root = _copy_frozen_assets(tmp_path)
    paths = _base_frozen_asset_paths()
    escaped: list[str] = []

    for relative_path in paths:
        source = _read_repository_json(relative_path)
        array_path, array = next(
            (path, candidate)
            for path, candidate in _walk_json_arrays(source)
            if candidate
        )
        mutated = _duplicate_array_element(source, array_path, len(array) - 1)
        destination = root / relative_path
        destination.write_text(
            json.dumps(mutated, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            _validate_frozen_asset_set(root, paths)
        except FrozenJsonMultiplicityError:
            pass
        else:
            escaped.append(relative_path)

        narrowed = tuple(path for path in paths if path != relative_path)
        _validate_frozen_asset_set(root, narrowed)
        shutil.copy2(REPOSITORY_ROOT / relative_path, destination)

    assert escaped == []


def test_duplicate_scan_negative_cases_are_all_rejected() -> None:
    """再帰・全要素・生キー・有効化・深さ・分岐到達の欠陥を負例で閉じる。"""
    nested_duplicate = '{"outer":{"rows":[{"id":1},{"id":1}]}}'

    def top_level_only(
        value: object, path: ArrayPath = ()
    ) -> list[tuple[ArrayPath, list[Any]]]:
        if isinstance(value, list):
            return [(path, value)]
        return []

    with pytest.raises(FrozenJsonMultiplicityError):
        _validate_frozen_json_text(nested_duplicate, top_level_only)
    assert json.loads(nested_duplicate)

    values = [{"id": 1}, {"id": 2}, {"id": 3}]
    for index in range(len(values)):
        mutated = copy.deepcopy(values)
        mutated.insert(index + 1, copy.deepcopy(mutated[index]))
        with pytest.raises(FrozenJsonMultiplicityError):
            _validate_frozen_json_text(json.dumps({"rows": mutated}))

    later_duplicate = '{"rows":[{"id":1},{"id":2},{"id":2}]}'
    parsed_later = json.loads(later_duplicate)
    assert parsed_later["rows"][0] not in parsed_later["rows"][1:]
    with pytest.raises(FrozenJsonMultiplicityError):
        _validate_frozen_json_text(later_duplicate)

    duplicate_key = '{"outer":{"same":1,"same":2}}'
    assert json.loads(duplicate_key)["outer"]["same"] == 2
    with pytest.raises(FrozenJsonMultiplicityError):
        _validate_frozen_json_text(duplicate_key)

    branched = '{"kept":{"rows":[1]},"swallowed":{"rows":[2]}}'

    def swallow_one_branch(
        value: object, path: ArrayPath = ()
    ) -> list[tuple[ArrayPath, list[Any]]]:
        if isinstance(value, dict):
            return [
                item
                for key, child in value.items()
                if key != "swallowed"
                for item in swallow_one_branch(child, (*path, key))
            ]
        if isinstance(value, list):
            return [(path, value)] + [
                item
                for index, child in enumerate(value)
                for item in swallow_one_branch(child, (*path, index))
            ]
        return []

    with pytest.raises(FrozenJsonMultiplicityError):
        _validate_frozen_json_text(branched, swallow_one_branch)


def test_multiplicity_scanner_reaches_the_actual_deepest_array() -> None:
    """固定基準版の最大深度を導出し、深さ制限では届かない配列を拒否する。"""
    _width, maximum_depth = _frozen_container_limits()
    candidates = [
        (len(path), relative_path, path, array)
        for relative_path in _base_frozen_asset_paths()
        for path, array in _walk_json_arrays(_base_json(relative_path))
        if array
    ]
    path_depth, relative_path, array_path, array = max(candidates)
    mutated = _duplicate_array_element(
        _read_repository_json(relative_path), array_path, len(array) - 1
    )
    mutated_text = json.dumps(mutated, ensure_ascii=False)

    def depth_limited(
        value: object, path: ArrayPath = ()
    ) -> list[tuple[ArrayPath, list[Any]]]:
        if len(path) >= path_depth:
            return []
        if isinstance(value, dict):
            return [
                item
                for key, child in value.items()
                for item in depth_limited(child, (*path, key))
            ]
        if isinstance(value, list):
            return [(path, value)] + [
                item
                for index, child in enumerate(value)
                for item in depth_limited(child, (*path, index))
            ]
        return []

    with pytest.raises(FrozenJsonMultiplicityError):
        _validate_frozen_json_text(mutated_text)
    with pytest.raises(FrozenJsonMultiplicityError):
        _validate_frozen_json_text(mutated_text, depth_limited)
    assert maximum_depth > path_depth


def test_recursive_derivers_cover_generated_container_sequences_and_siblings() -> None:
    """深さ d の全容器列・述語分岐・葉型と幅 w の全兄弟を探針で覆う。"""
    maximum_width, maximum_depth = _frozen_container_limits()
    leaf_values: tuple[object, ...] = ("text", 1, True, None, {}, [])
    sequences = tuple(
        sequence
        for depth in range(1, maximum_depth + 1)
        for sequence in itertools.product(("dict", "list"), repeat=depth)
    )
    leaf_probe_value = {
        f"{predicate}_probe_{index}": copy.deepcopy(leaf)
        for index, leaf in enumerate(leaf_values)
        for predicate in ("owner", "task_id")
    }
    expected_leaf_count = len(leaf_probe_value) * maximum_width

    for sequence in sequences:
        for widened_index in range(len(sequence)):
            array_probe = _wrap_with_wide_container(
                sequence, widened_index, ["array-probe"], maximum_width
            )
            terminal_arrays = [
                array
                for _path, array in _walk_json_arrays(array_probe)
                if array == ["array-probe"]
            ]
            assert len(terminal_arrays) == maximum_width

            leaf_probe = _wrap_with_wide_container(
                sequence,
                widened_index,
                leaf_probe_value,
                maximum_width,
            )
            assert len(_iter_matching_key_paths(leaf_probe)) == expected_leaf_count
            assert len(_iter_leaf_paths(leaf_probe)) == expected_leaf_count


def test_normal_validation_never_reseals_a_semantically_valid_drift(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """意味検査を通る digest 差分でも通常実行が seal を書き換えないと示す。"""
    root = tmp_path / "repository"
    clone = subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--no-hardlinks",
            str(REPOSITORY_ROOT),
            str(root),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert clone.returncode == 0, clone.stderr
    baseline_result = checker.main(["--root", str(root)])
    baseline_output = capsys.readouterr()
    assert baseline_result == 0, baseline_output.err

    evidence_path = root / "contracts/authz/verification-evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["provenance"][0]["extracted_text"] += " "
    checker.validate_verification_evidence(evidence, root)
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    seal_path = root / f"contracts/authz/{ORACLE_SEAL_FILE}"
    seal_before = seal_path.read_bytes()

    result = checker.main(["--root", str(root)])
    output = capsys.readouterr()

    assert result == 1
    assert (
        "contracts/authz/verification-evidence.json: "
        "canonical digest が oracle seal と不一致"
    ) in output.err
    assert seal_path.read_bytes() == seal_before


def test_oracle_reseal_preserves_inputs_and_expected_asset_digests() -> None:
    """入力baselineを三者照合し、意味が変わる資産を予定した集合に限る。"""
    relative_path = f"contracts/authz/{ORACLE_SEAL_FILE}"
    base = _base_json(relative_path)
    current = _read_repository_json(relative_path)
    assets, _seal, paths = _repository_oracle_assets()

    assert current["oracle_commit_semantics"] == base["oracle_commit_semantics"]
    assert _oracle_seal_meaning_body(current) == _oracle_seal_meaning_body(base)
    _assert_oracle_input_baseline_matches_seal(current)
    current_by_path = {paths[name]: asset for name, asset in assets.items()}
    base_by_path = {path: _base_json(path) for path in current_by_path}
    changed = {
        path
        for path, asset in current_by_path.items()
        if _oracle_meaning_body(asset) != _oracle_meaning_body(base_by_path[path])
    }
    assert changed == {
        "contracts/authz/boundary-proposal.json",
        "contracts/authz/claim-mutant-map.json",
        "contracts/authz/ddl-elements.json",
    }
    assert {
        asset["oracle_context"]["oracle_commit"] for asset in assets.values()
    } == {current["oracle_commit"]}
    checker.validate_oracle_seal(current, assets, paths, REPOSITORY_ROOT)


def test_all_recursively_enumerated_oracle_leaves_reject_change_and_deletion() -> None:
    """6資産とsealから全葉を再帰列挙し、値改変・削除を全数 red にする。"""
    assets, seal, paths = _repository_oracle_assets()
    leaf_counts = {name: len(_iter_leaf_paths(asset)) for name, asset in assets.items()}
    leaf_counts["oracle_seal"] = len(_iter_leaf_paths(seal))
    escaped: list[tuple[str, tuple[str | int, ...], str]] = []
    attempts = 0

    for name, asset in assets.items():
        for leaf_path in _iter_leaf_paths(asset):
            for mutation in ("change", "delete"):
                mutated = _mutate_leaf(asset, leaf_path, delete=mutation == "delete")
                try:
                    checker.validate_oracle_asset_seal(mutated, paths[name], seal)
                except checker.CatalogError:
                    pass
                else:
                    escaped.append((name, leaf_path, mutation))
                attempts += 1
    for leaf_path in _iter_leaf_paths(seal):
        for mutation in ("change", "delete"):
            mutated_seal = _mutate_leaf(seal, leaf_path, delete=mutation == "delete")
            try:
                checker.validate_oracle_seal(
                    mutated_seal, assets, paths, REPOSITORY_ROOT
                )
            except checker.CatalogError:
                pass
            else:
                escaped.append(("oracle_seal", leaf_path, mutation))
            attempts += 1

    assert all(count > 0 for count in leaf_counts.values())
    assert attempts == sum(leaf_counts.values()) * 2
    assert escaped == []


def test_all_claim_execution_classes_reject_the_opposite_class() -> None:
    """対応表自身の全claimを列挙し、probe/contract 反転を全数 red にする。"""
    assets, _seal, _paths = _repository_oracle_assets()
    claims = assets["claim_mutant_map"]["claims"]
    escaped: list[str] = []

    for index, claim in enumerate(claims):
        mutated = copy.deepcopy(assets["claim_mutant_map"])
        mutated_claim = mutated["claims"][index]
        if claim["execution_class"] == "probe_executable":
            mutated_claim.update(
                {
                    "execution_class": "contract_only",
                    "classification_rule_id": "CONTRACT_ONLY_NO_DB_DECISION_POINT",
                    "runtime_kill_required": False,
                    "runtime_evidence_kind": "handoff_runtime_test",
                    "receiving_task_id": "TSK-217",
                }
            )
        else:
            mutated_claim.update(
                {
                    "execution_class": "probe_executable",
                    "classification_rule_id": "PROBE_EXECUTABLE_DB_DECISION_POINT",
                    "runtime_kill_required": True,
                    "runtime_evidence_kind": "runtime_cross_tenant_assertion",
                    "receiving_task_id": "TSK-270-GROUP-2",
                }
            )
        try:
            _validate_mutant_map(mutated)
        except checker.CatalogError:
            pass
        else:
            escaped.append(claim["claim_id"])

    assert len(claims) == sum(
        1 for _claim in assets["claim_mutant_map"]["claims"]
    )
    assert escaped == []


def test_all_mutant_rows_reject_one_row_removal() -> None:
    """対応表から全mutant行を列挙し、1行ずつの削除を全数 red にする。"""
    assets, _seal, _paths = _repository_oracle_assets()
    mutants = assets["claim_mutant_map"]["mutants"]
    escaped: list[str] = []

    for index, mutant in enumerate(mutants):
        mutated = copy.deepcopy(assets["claim_mutant_map"])
        mutated["mutants"].pop(index)
        try:
            _validate_mutant_map(mutated)
        except checker.CatalogError:
            pass
        else:
            escaped.append(mutant["mutant_id"])

    assert len(mutants) > 0
    assert escaped == []


def _expected_test_id_paths(value: object) -> list[tuple[str | int, ...]]:
    """資産自身から期待テストIDの全葉パスを機械抽出する。"""
    paths: list[tuple[str | int, ...]] = []
    for path in _iter_leaf_paths(value):
        key = path[-1]
        if key in {"schema_drift_test_id", "runtime_test_id"}:
            paths.append(path)
            continue
        if key != "id" or len(path) < 2:
            continue
        parent = _value_at_path(value, path[:-1])
        if isinstance(parent, dict) and set(parent) == {"id", "status"}:
            paths.append(path)
    return paths


def test_all_expected_test_ids_reject_replacement() -> None:
    """対応表から期待テストIDを全数抽出し、差し替えをsealで全数 red にする。"""
    assets, seal, paths = _repository_oracle_assets()
    asset = assets["claim_mutant_map"]
    test_id_paths = _expected_test_id_paths(asset)
    escaped: list[tuple[str | int, ...]] = []

    for path in test_id_paths:
        mutated = copy.deepcopy(asset)
        parent, key = _parent_and_key(mutated, path)
        assert isinstance(parent, dict) and isinstance(key, str)
        parent[key] = "tests/receiving_task.py::test_replaced_expectation"
        try:
            checker.validate_oracle_asset_seal(
                mutated, paths["claim_mutant_map"], seal
            )
        except checker.CatalogError:
            pass
        else:
            escaped.append(path)

    assert len(test_id_paths) > 0
    assert escaped == []


def test_all_cut_set_elements_reject_one_element_removal() -> None:
    """attack treeから全cut set要素を列挙し、1要素ずつ削除して red にする。"""
    assets, _seal, _paths = _repository_oracle_assets()
    attack_tree = assets["attack_tree"]
    mutant_map = assets["claim_mutant_map"]
    requirement_catalog, _requirement_lock = _repository_catalog_and_lock()
    derived_assets, _derived_locks, _derived_paths = _repository_derived_assets()
    ddl_result = checker.validate_ddl_elements(
        assets["ddl_elements"], REPOSITORY_ROOT
    )
    mutant_result = checker.validate_claim_mutant_map(
        mutant_map,
        requirement_catalog,
        derived_assets["route_registry"],
        derived_assets["http_matrix"],
        ddl_result,
        REPOSITORY_ROOT,
        frozenset({IMPLEMENTED_CATALOG_TEST_ID, IMPLEMENTED_ORACLE_TEST_ID}),
    )
    escaped: list[tuple[str, str]] = []
    attempts = 0

    for cut_index, cut_set in enumerate(attack_tree["minimal_cut_sets"]):
        for mutant_index, mutant_id in enumerate(cut_set["mutant_ids"]):
            mutated = copy.deepcopy(attack_tree)
            mutated["minimal_cut_sets"][cut_index]["mutant_ids"].pop(mutant_index)
            try:
                checker.validate_attack_tree(mutated, mutant_result, REPOSITORY_ROOT)
            except checker.CatalogError:
                pass
            else:
                escaped.append((cut_set["cut_set_id"], mutant_id))
            attempts += 1

    assert attempts == sum(
        len(cut_set["mutant_ids"])
        for cut_set in attack_tree["minimal_cut_sets"]
    )
    assert escaped == []


def test_all_table_privilege_mutants_require_singleton_cut_sets() -> None:
    """app_role 表権限 mutant の単独 cut set 結線欠落を拒否する。"""
    assets, _seal, _paths = _repository_oracle_assets()
    attack_tree = assets["attack_tree"]
    mutant_map = assets["claim_mutant_map"]
    requirement_catalog, _requirement_lock = _repository_catalog_and_lock()
    derived_assets, _derived_locks, _derived_paths = _repository_derived_assets()
    ddl_result = checker.validate_ddl_elements(
        assets["ddl_elements"], REPOSITORY_ROOT
    )
    mutant_result = checker.validate_claim_mutant_map(
        mutant_map,
        requirement_catalog,
        derived_assets["route_registry"],
        derived_assets["http_matrix"],
        ddl_result,
        REPOSITORY_ROOT,
        frozenset({IMPLEMENTED_CATALOG_TEST_ID, IMPLEMENTED_ORACLE_TEST_ID}),
    )
    app_role_mutant_ids = {
        target["mutant_id_template"].replace(
            "{privilege_id}", group["privilege_id"]
        )
        for target in mutant_map["table_privilege_mutation_rule"]["target_pairs"]
        if target["target_role_id"] == "app_role"
        for group in target["privilege_groups"]
    }
    escaped: list[str] = []

    for mutant_id in sorted(app_role_mutant_ids):
        mutated = copy.deepcopy(attack_tree)
        removed_cut = next(
            cut
            for cut in mutated["minimal_cut_sets"]
            if cut["mutant_ids"] == [mutant_id]
        )
        mutated["minimal_cut_sets"].remove(removed_cut)
        for interaction in mutated["two_factor_interactions"]:
            if removed_cut["cut_set_id"] in interaction["activated_cut_set_ids"]:
                interaction["activated_cut_set_ids"].remove(removed_cut["cut_set_id"])
                interaction["expected_attack_established"] = bool(
                    interaction["activated_cut_set_ids"]
                )
        try:
            checker.validate_attack_tree(mutated, mutant_result, REPOSITORY_ROOT)
        except checker.CatalogError:
            pass
        else:
            escaped.append(mutant_id)

    assert len(app_role_mutant_ids) == 4
    assert escaped == []


def test_table_privilege_cut_contracts_reject_swap_and_goal_reassignment() -> None:
    """表権限 mutant の期待 cut ID・goal からの付け替えを拒否する。"""
    assets, _seal, _paths = _repository_oracle_assets()
    attack_tree = assets["attack_tree"]
    requirement_catalog, _requirement_lock = _repository_catalog_and_lock()
    derived_assets, _derived_locks, _derived_paths = _repository_derived_assets()
    ddl_result = checker.validate_ddl_elements(
        assets["ddl_elements"], REPOSITORY_ROOT
    )
    mutant_result = checker.validate_claim_mutant_map(
        assets["claim_mutant_map"],
        requirement_catalog,
        derived_assets["route_registry"],
        derived_assets["http_matrix"],
        ddl_result,
        REPOSITORY_ROOT,
        frozenset({IMPLEMENTED_CATALOG_TEST_ID, IMPLEMENTED_ORACLE_TEST_ID}),
    )

    swapped = copy.deepcopy(attack_tree)
    app_cut = next(
        cut
        for cut in swapped["minimal_cut_sets"]
        if cut["cut_set_id"] == "CUT-APP-ROLE-DIRECT-GROUPS-DML"
    )
    management_cut = next(
        cut
        for cut in swapped["minimal_cut_sets"]
        if cut["cut_set_id"] == "CUT-MANAGEMENT-DIRECT-SELECT"
    )
    app_cut["mutant_ids"], management_cut["mutant_ids"] = (
        management_cut["mutant_ids"],
        app_cut["mutant_ids"],
    )
    for interaction in swapped["two_factor_interactions"]:
        factor_set = set(interaction["factor_mutant_ids"])
        interaction["activated_cut_set_ids"] = sorted(
            cut["cut_set_id"]
            for cut in swapped["minimal_cut_sets"]
            if set(cut["mutant_ids"]) <= factor_set
        )
        interaction["expected_attack_established"] = bool(
            interaction["activated_cut_set_ids"]
        )

    reassigned = copy.deepcopy(attack_tree)
    reassigned_cut = next(
        cut
        for cut in reassigned["minimal_cut_sets"]
        if cut["cut_set_id"] == "CUT-APP-ROLE-DIRECT-GROUPS-DML"
    )
    reassigned_cut["attack_goal_id"] = (
        "ATTACK:MANAGEMENT-CALLER-DIRECT-TABLE-PRIVILEGE"
    )

    escaped: list[str] = []
    for case_name, mutated in (
        ("mutant_swap", swapped),
        ("goal_reassignment", reassigned),
    ):
        try:
            checker.validate_attack_tree(mutated, mutant_result, REPOSITORY_ROOT)
        except checker.CatalogError:
            pass
        else:
            escaped.append(case_name)

    assert escaped == []


def test_all_initial_rejections_reject_one_row_removal() -> None:
    """不採用構成表から初期行を全数列挙し、1行ずつ削除して red にする。"""
    assets, _seal, _paths = _repository_oracle_assets()
    rejected = assets["rejected_configs"]
    escaped: list[str] = []

    for index, row in enumerate(rejected["rejections"]):
        mutated = copy.deepcopy(rejected)
        mutated["rejections"].pop(index)
        try:
            checker.validate_rejected_configs(mutated, REPOSITORY_ROOT)
        except checker.CatalogError:
            pass
        else:
            escaped.append(row["rejection_id"])

    assert len(rejected["rejections"]) == len(
        rejected["required_initial_rejection_ids"]
    )
    assert escaped == []


def test_all_contract_only_claims_reject_runtime_kill_requirement() -> None:
    """全contract_onlyへruntime killを要求するR-7違反を全数 red にする。"""
    assets, _seal, _paths = _repository_oracle_assets()
    claims = assets["claim_mutant_map"]["claims"]
    contract_indexes = [
        index
        for index, claim in enumerate(claims)
        if claim["execution_class"] == "contract_only"
    ]
    escaped: list[str] = []

    for index in contract_indexes:
        mutated = copy.deepcopy(assets["claim_mutant_map"])
        mutated["claims"][index]["runtime_kill_required"] = True
        try:
            _validate_mutant_map(mutated)
        except checker.CatalogError:
            pass
        else:
            escaped.append(claims[index]["claim_id"])

    assert len(contract_indexes) > 0
    assert escaped == []


def test_all_allow_cells_have_one_positive_case_test_id() -> None:
    """HTTP行列から許可セルを全数導出し、正例テストIDとone-to-one照合する。"""
    derived_assets, _locks, _paths = _repository_derived_assets()
    oracle_assets, _seal, _oracle_paths = _repository_oracle_assets()
    allow_cell_ids = {
        cell["cell_id"]
        for cell in derived_assets["http_matrix"]["cells"]
        if cell["expected_result"] == "allow"
    }
    positive_cases = oracle_assets["claim_mutant_map"]["positive_cases"]["cases"]
    positive_by_cell = {row["cell_id"]: row["test_owner"]["id"] for row in positive_cases}

    assert len(allow_cell_ids) == 6
    assert set(positive_by_cell) == allow_cell_ids
    assert len(set(positive_by_cell.values())) == len(allow_cell_ids)
    assert all(positive_by_cell.values())


def test_table_privilege_matrix_and_mutants_derive_from_one_asset_set() -> None:
    """DDL資産の単一8権限集合から実行行列とmutationをexact-set導出する。"""
    assets, _seal, _paths = _repository_oracle_assets()
    ddl = assets["ddl_elements"]
    mapping = assets["claim_mutant_map"]
    privilege_ids = set(ddl["enums"]["table_privilege_ids"])
    matrix_ids = {
        row["privilege_id"] for row in ddl["table_privilege_probe_matrix"]
    }
    prefix = checker.TABLE_PRIVILEGE_MUTANT_PREFIX
    mutant_ids = {
        mutant["mutant_id"]
        for mutant in mapping["mutants"]
        if mutant["mutant_id"].startswith(prefix)
    }

    assert "TABLE_PRIVILEGE_IDS" not in SCRIPT.read_text(encoding="utf-8")
    assert len(privilege_ids) == 8
    assert matrix_ids == privilege_ids
    assert mutant_ids == {f"{prefix}{privilege_id}" for privilege_id in privilege_ids}
    assert ddl["column_acl_expectations"][0]["expected_entries"] == []


def test_management_probe_claims_have_acl_and_atomicity_kills() -> None:
    """代表管理probeの2 claimへ表権限8件と原子性1件を対応させる。"""
    assets, _seal, _paths = _repository_oracle_assets()
    ddl = assets["ddl_elements"]
    mapping = assets["claim_mutant_map"]
    expected_claim_ids = set(ddl["representative_management_probe"]["claim_ids"])
    claim_by_id = {claim["claim_id"]: claim for claim in mapping["claims"]}
    prefix = checker.TABLE_PRIVILEGE_MUTANT_PREFIX
    privilege_mutants = [
        mutant
        for mutant in mapping["mutants"]
        if mutant["mutant_id"].startswith(prefix)
    ]
    atomic_mutant = next(
        mutant
        for mutant in mapping["mutants"]
        if mutant["mutant_id"]
        == "MUT:CONFIG:CFG_SPLIT_MANAGEMENT_AUTHORIZATION_AND_SIDE_EFFECT"
    )

    assert expected_claim_ids == checker.MANAGEMENT_PROBE_CLAIM_IDS
    assert all(
        claim_by_id[claim_id]["execution_class"] == "probe_executable"
        and claim_by_id[claim_id]["runtime_kill_required"] is True
        for claim_id in expected_claim_ids
    )
    assert len(privilege_mutants) == len(ddl["enums"]["table_privilege_ids"])
    assert all(
        set(mutant["claim_ids"]) == expected_claim_ids
        and mutant["runtime_kill_required"] is True
        for mutant in privilege_mutants
    )
    assert atomic_mutant["claim_ids"] == [
        "ORACLE:MANAGEMENT-PROBE:ATOMIC-AUTHORIZATION-SIDE-EFFECT"
    ]
    assert atomic_mutant["runtime_kill_required"] is True


def test_all_runtime_kill_waivers_have_a_closed_machine_checked_reason() -> None:
    """runtime kill不要の全mutantを資産から抽出し、閉じた根拠で被覆する。"""
    assets, _seal, _paths = _repository_oracle_assets()
    mutants = assets["claim_mutant_map"]["mutants"]
    waived = [mutant for mutant in mutants if not mutant["runtime_kill_required"]]
    reasons = Counter(mutant["runtime_kill_waiver_reason"] for mutant in waived)

    assert reasons == Counter(
            {
                "contract_only_handoff": 173,
                "covered_by_two_factor_cut_set": 3,
            "positive_case_kill_only": 2,
            "application_expected_to_fail": 1,
        }
    )
    assert {
        mutant["mutant_id"]
        for mutant in waived
        if mutant["runtime_kill_waiver_reason"] == "positive_case_kill_only"
    } == checker.POSITIVE_KILL_MUTANT_IDS


def test_all_positive_cases_and_positive_kill_flags_reject_removal() -> None:
    """正例6件と正例kill全件を資産から列挙し、削除・解除を全数 red にする。"""
    assets, _seal, _paths = _repository_oracle_assets()
    mapping = assets["claim_mutant_map"]
    positive_cases = mapping["positive_cases"]["cases"]
    positive_mutant_indexes = [
        index
        for index, mutant in enumerate(mapping["mutants"])
        if mutant["positive_kill_required"]
    ]
    escaped: list[str] = []

    for index, positive_case in enumerate(positive_cases):
        mutated = copy.deepcopy(mapping)
        mutated["positive_cases"]["cases"].pop(index)
        try:
            _validate_mutant_map(mutated)
        except checker.CatalogError:
            pass
        else:
            escaped.append(positive_case["cell_id"])
    for index in positive_mutant_indexes:
        mutated = copy.deepcopy(mapping)
        mutant = mutated["mutants"][index]
        mutant["positive_kill_required"] = False
        mutant["expected_positive_outcome"] = "pass"
        mutant["runtime_kill_waiver_reason"] = "covered_by_two_factor_cut_set"
        try:
            _validate_mutant_map(mutated)
        except checker.CatalogError:
            pass
        else:
            escaped.append(mutant["mutant_id"])

    assert len(positive_cases) == 6
    assert len(positive_mutant_indexes) > 0
    assert escaped == []
