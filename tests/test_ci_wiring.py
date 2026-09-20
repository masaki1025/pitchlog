"""CI が文書検査と DB 必須テストを欠落なく実行する配線を検証する。

検査を CI に載せても選択用引数が付いていると、一部だけの実行で green になり得る。
そのため、YAML の構造とコマンドの禁止オプションを同時に検査する。
"""

import copy
import json
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
COMPOSE_PATH = REPOSITORY_ROOT / "docker-compose.yml"
EXPECTATIONS_PATH = (
    REPOSITORY_ROOT / "backend" / "tests" / "db" / "environment-expectations.json"
)
BACKEND_PYPROJECT_PATH = REPOSITORY_ROOT / "backend" / "pyproject.toml"
BACKEND_LOCK_PATH = REPOSITORY_ROOT / "backend" / "uv.lock"
DB_CONFTEST_PATH = REPOSITORY_ROOT / "backend" / "tests" / "db" / "conftest.py"
STEPS_PATH = REPOSITORY_ROOT / "docs" / "features" / "domain-calc-dsl" / "steps.json"
REQUIRED_FULL_CHECKS = ("check_design_propagation", "check_doc_coverage")
FORBIDDEN_SELECTORS = ("--defects", "--checks")
ALEMBIC_CI_COMMANDS = (
    "uv run alembic upgrade head",
    "uv run alembic current --check-heads",
    "uv run alembic check",
)
CHECKOUT_SHA_RE = re.compile(r"[0-9a-f]{40}")
# ci.yml には履歴を要するジョブを機械導出できる標識がなく、履歴依存は
# source_commit 検査や三点差分へ推移した先にあるため、ジョブ名を列挙する。
# 片方だけでは新設ジョブが素通りするので、あり・なしの両集合を exact-set 固定する。
CHECKOUT_JOBS_WITH_FETCH_DEPTH_ZERO = frozenset(
    {
        "secrets",
        "core-guard",
        "harness",
        "nfr021-append-only",
        "frontend-changes",
        "backend-changes",
        "backend",
        "consistency",
        "mutation",
    }
)
CHECKOUT_JOBS_WITHOUT_FETCH_DEPTH_ZERO = frozenset({"docs-lint", "frontend"})
LEGACY_JOB_IDS = frozenset(
    {
        "secrets",
        "docs-lint",
        "core-guard",
        "harness",
        "nfr021-append-only",
        "frontend-changes",
        "backend-changes",
        "frontend",
        "backend",
    }
)
NEW_JOB_IDS = frozenset({"consistency", "mutation"})
CONSISTENCY_TIMEOUT_MINUTES = 20
MUTATION_TIMEOUT_MINUTES = 40
HARNESS_PYTEST_COMMAND = (
    "uv run pytest -c pyproject.toml tests/ "
    "--ignore=tests/domain/boot "
    "--ignore=tests/domain/mut "
    "--ignore=tests/test_plan_generation.py "
    "--ignore=tests/test_step_history_audit.py"
)
CONSISTENCY_PYTEST_COMMAND = (
    "uv run pytest -c pyproject.toml "
    "tests/domain/boot/ "
    "tests/test_plan_generation.py "
    "tests/test_step_history_audit.py"
)
MUTATION_PYTEST_COMMAND = "uv run pytest -c pyproject.toml tests/domain/mut/"
# 全葉への値変異と削除変異を一度ずつ行う契約値。木を広げた場合は意図的に更新する。
EXPECTED_CI_CONTRACT_MUTATION_ATTEMPTS = 106
PathSegment = str | int
NodePath = tuple[PathSegment, ...]


def _load_workflow(text: str) -> dict[str, Any]:
    workflow = yaml.safe_load(text)
    assert isinstance(workflow, dict), "ci.yml のルートはマッピングでなければならない"
    return workflow


def _docs_lint_commands(workflow: dict[str, Any]) -> list[str]:
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "ci.yml に jobs がなければならない"

    docs_lint = jobs.get("docs-lint")
    assert isinstance(docs_lint, dict), "docs-lint ジョブがなければならない"

    steps = docs_lint.get("steps")
    assert isinstance(steps, list), "docs-lint.steps は配列でなければならない"
    return [
        command
        for step in steps
        if isinstance(step, dict)
        and isinstance((command := step.get("run")), str)
    ]


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    """YAML ファイルをマッピングとして読み込む。

    Args:
        path: 読み込む YAML ファイル。

    Returns:
        YAML ルートのマッピング。
    """
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"{path}: YAML ルートはマッピングが必要"
    return loaded


def _load_expectations() -> dict[str, Any]:
    """凍結済み DB 環境期待値資産を読み込む。

    Returns:
        JSON ルートのオブジェクト。
    """
    loaded = json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _backend_job(workflow: dict[str, Any]) -> dict[str, Any]:
    """workflow から既存 backend ジョブを取得する。

    Args:
        workflow: CI workflow の構造。

    Returns:
        backend ジョブのマッピング。
    """
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "ci.yml に jobs が必要"
    backend = jobs.get("backend")
    assert isinstance(backend, dict), "既存 backend ジョブが必要"
    return backend


def _harness_job(workflow: dict[str, Any]) -> dict[str, Any]:
    """workflow から harness ジョブを取得する。

    Args:
        workflow: CI workflow の構造。

    Returns:
        harness ジョブのマッピング。
    """
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "ci.yml に jobs が必要"
    harness = jobs.get("harness")
    assert isinstance(harness, dict), "harness ジョブが必要"
    return harness


def _named_job(workflow: dict[str, Any], name: str) -> dict[str, Any]:
    """workflow から名前でジョブを取得する。

    Args:
        workflow: CI workflow の構造。
        name: 取得するジョブ ID。

    Returns:
        指定したジョブのマッピング。
    """
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "ci.yml に jobs が必要"
    job = jobs.get(name)
    assert isinstance(job, dict), f"{name} ジョブが必要"
    return job


def _mapping_at(node: object, path: NodePath) -> Any:
    """マッピングまたは配列の指定パスをたどる。

    Args:
        node: 起点となる JSON 互換値。
        path: キーまたは配列 index の並び。

    Returns:
        パス終端の値。欠落時は ``None``。
    """
    current: Any = node
    for segment in path:
        if isinstance(segment, str):
            if not isinstance(current, dict) or segment not in current:
                return None
            current = current[segment]
        else:
            if not isinstance(current, list) or not 0 <= segment < len(current):
                return None
            current = current[segment]
    return current


def _is_pinned_checkout_action(uses: object) -> bool:
    """uses が公式 checkout の SHA 固定参照なら真を返す。

    action ID を固定しなければジョブ名の exact-set が意味を持たないため、
    候補の件数検査とは分けて action ID と ref の双方を厳格に検査する。

    Args:
        uses: CI ステップの ``uses`` 値。

    Returns:
        ``actions/checkout@<40桁SHA>`` と完全一致する場合は真。
    """
    if not isinstance(uses, str):
        return False
    action_id, separator, ref = uses.partition("@")
    return (
        separator == "@"
        and action_id == "actions/checkout"
        and CHECKOUT_SHA_RE.fullmatch(ref) is not None
    )


def _checkout_step(job_name: str, job: object) -> dict[str, Any]:
    """広く抽出した候補から唯一かつ正規の checkout ステップを取得する。

    候補抽出では大小文字を無視した部分一致を使い、偽装を件数へ含める。
    その後で唯一の候補が公式 action の SHA 固定参照であることを別に主張する。
    ``checkout`` を名前に含まない浅い clone action は見逃す一方、Git を変更しない
    ``checkout-metadata`` なども候補になる。後者が生じた場合は宣言を見直すか、
    候補判定を精緻化する必要があるという fail-closed の選択である。

    Args:
        job_name: CI ジョブ名。
        job: CI ジョブの構造。

    Returns:
        唯一の actions/checkout ステップ。

    Raises:
        AssertionError: 候補が 0 件・複数件、または正規の SHA 固定参照でない場合。
    """
    steps = _mapping_at(job, ("steps",))
    assert isinstance(steps, list), f"{job_name}.steps は配列でなければならない"
    checkout_candidates = [
        step
        for step in steps
        if isinstance(step, dict)
        and isinstance((uses := step.get("uses")), str)
        and "checkout" in uses.lower()
    ]
    if not checkout_candidates:
        raise AssertionError(f"{job_name} に checkout ステップが無い")
    if len(checkout_candidates) > 1:
        candidate_uses = [candidate["uses"] for candidate in checkout_candidates]
        raise AssertionError(
            f"{job_name} に checkout ステップが複数ある: uses={candidate_uses}"
        )

    checkout = checkout_candidates[0]
    uses = checkout["uses"]
    assert _is_pinned_checkout_action(uses), (
        f"{job_name} の checkout は actions/checkout@<40桁SHA> でない: "
        f"actual={uses!r}"
    )
    return checkout


def _assert_checkout_fetch_depth_contract(
    workflow: dict[str, Any],
    *,
    with_fetch_depth_zero: frozenset[str] = CHECKOUT_JOBS_WITH_FETCH_DEPTH_ZERO,
    without_fetch_depth_zero: frozenset[str] = (
        CHECKOUT_JOBS_WITHOUT_FETCH_DEPTH_ZERO
    ),
) -> None:
    """全ジョブの checkout 件数と fetch-depth 分類を exact-set 検査する。

    Args:
        workflow: CI workflow の構造。
        with_fetch_depth_zero: ``fetch-depth: 0`` が必要なジョブ集合。
        without_fetch_depth_zero: ``fetch-depth: 0`` を持たないジョブ集合。
    """
    jobs = _mapping_at(workflow, ("jobs",))
    assert isinstance(jobs, dict), "ci.yml に jobs が必要"
    observed_with: set[str] = set()
    observed_without: set[str] = set()
    for job_name, job in jobs.items():
        assert isinstance(job_name, str), "CI ジョブ名は文字列でなければならない"
        checkout = _checkout_step(job_name, job)
        fetch_depth = _mapping_at(checkout, ("with", "fetch-depth"))
        if fetch_depth == 0:
            observed_with.add(job_name)
        else:
            observed_without.add(job_name)

    assert observed_with == with_fetch_depth_zero, (
        "fetch-depth: 0 を持つジョブが宣言と一致しない: "
        f"actual={sorted(observed_with)}, expected={sorted(with_fetch_depth_zero)}"
    )
    assert observed_without == without_fetch_depth_zero, (
        "fetch-depth: 0 を持たないジョブが宣言と一致しない: "
        f"actual={sorted(observed_without)}, "
        f"expected={sorted(without_fetch_depth_zero)}"
    )


def _leaf_paths(node: object, path: NodePath = ()) -> list[NodePath]:
    """JSON 互換ツリーの全葉パスを内容で選ばず列挙する。

    Args:
        node: 走査対象の JSON 互換値。
        path: 現在位置のパス。

    Returns:
        深さ優先順の全葉パス。
    """
    if isinstance(node, dict):
        return [
            leaf
            for key, value in node.items()
            for leaf in _leaf_paths(value, (*path, key))
        ]
    if isinstance(node, list):
        return [
            leaf
            for index, value in enumerate(node)
            for leaf in _leaf_paths(value, (*path, index))
        ]
    return [path]


def _format_path(path: NodePath) -> str:
    """葉パスを失敗報告用文字列へ変換する。

    Args:
        path: キーまたは配列 index の並び。

    Returns:
        人間が追跡できるパス文字列。
    """
    rendered = "$"
    for segment in path:
        rendered += f"[{segment}]" if isinstance(segment, int) else f".{segment}"
    return rendered


def _backend_commands(backend: dict[str, Any]) -> list[str]:
    """backend ジョブの run コマンドを順序どおり返す。

    Args:
        backend: backend ジョブの構造。

    Returns:
        ``run`` を持つ step のコマンド。
    """
    steps = backend.get("steps")
    if not isinstance(steps, list):
        return []
    return [
        command
        for step in steps
        if isinstance(step, dict)
        and isinstance((command := step.get("run")), str)
    ]


def _alembic_command_locations(
    workflow: dict[str, Any],
) -> list[tuple[str, str]]:
    """全ジョブから Alembic 実行コマンドと所属ジョブを順序どおり得る。

    Args:
        workflow: CI workflow の構造。

    Returns:
        ジョブ宣言順・step 宣言順の ``(job 名, run コマンド)``。
    """
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return []
    locations: list[tuple[str, str]] = []
    for job_name, job in jobs.items():
        if not isinstance(job_name, str) or not isinstance(job, dict):
            continue
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            command = step.get("run")
            if isinstance(command, str) and "alembic" in shlex.split(command):
                locations.append((job_name, command))
    return locations


def _canonical_distribution_name(specification: str) -> str:
    """依存指定の先頭から正規化済み distribution 名を得る。

    Args:
        specification: PEP 508 形式の依存指定。

    Returns:
        正規化済みの distribution 名。名前を取得できなければ空文字列。
    """
    match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", specification)
    if match is None:
        return ""
    return re.sub(r"[-_.]+", "-", match[0]).lower()


def _orm_stack_dependency_errors(
    project: dict[str, Any],
    lock: dict[str, Any],
) -> list[str]:
    """ORM スタックの直接依存と lock の違反を返す。

    Args:
        project: backend/pyproject.toml を読み込んだマッピング。
        lock: backend/uv.lock を読み込んだマッピング。

    Returns:
        検出した違反。空配列なら契約を満たす。
    """
    errors: list[str] = []
    project_section = project.get("project")
    if not isinstance(project_section, dict):
        return ["pyproject に project テーブルが必要"]
    dependencies = project_section.get("dependencies")
    if not isinstance(dependencies, list):
        return ["project.dependencies は配列が必要"]

    required_dependencies = (
        (
            "psycopg",
            r"psycopg\[binary\]==(\d+\.\d+\.\d+)",
            "psycopg[binary] は製品依存で厳密固定する",
        ),
        (
            "sqlalchemy",
            r"sqlalchemy==(\d+\.\d+\.\d+)",
            "sqlalchemy は直接依存で X.Y.Z 形式に厳密固定する",
        ),
        (
            "alembic",
            r"alembic==(\d+\.\d+\.\d+)",
            "alembic は直接依存で X.Y.Z 形式に厳密固定する",
        ),
    )
    exact_versions: dict[str, str] = {}
    for name, pattern, invalid_message in required_dependencies:
        specifications = [
            dependency
            for dependency in dependencies
            if isinstance(dependency, str)
            and _canonical_distribution_name(dependency) == name
        ]
        if len(specifications) != 1:
            errors.append(f"{name} の直接依存はちょうど 1 件必要")
            continue
        match = re.fullmatch(pattern, specifications[0])
        if match is None:
            errors.append(invalid_message)
            continue
        exact_versions[name] = match[1]

    sqlalchemy_version = exact_versions.get("sqlalchemy")
    if sqlalchemy_version is not None and sqlalchemy_version.split(".", maxsplit=1)[0] != "2":
        errors.append("SQLAlchemy の major は 2 が必要")

    packages = lock.get("package")
    if not isinstance(packages, list):
        errors.append("lock の package は配列が必要")
        return errors
    locked_versions = {
        _canonical_distribution_name(name): version
        for package in packages
        if isinstance(package, dict)
        and isinstance((name := package.get("name")), str)
        and isinstance((version := package.get("version")), str)
    }
    lock_expectations = (
        ("psycopg", exact_versions.get("psycopg")),
        ("psycopg-binary", exact_versions.get("psycopg")),
        ("sqlalchemy", sqlalchemy_version),
        ("alembic", exact_versions.get("alembic")),
    )
    for name, expected_version in lock_expectations:
        if (
            expected_version is not None
            and locked_versions.get(name) != expected_version
        ):
            errors.append(f"lock の {name} が pyproject の固定版と一致しない")
    return errors


def _harness_commands(harness: dict[str, Any]) -> list[str]:
    """harness ジョブの run コマンドを順序どおり返す。

    Args:
        harness: harness ジョブの構造。

    Returns:
        ``run`` を持つ step のコマンド。
    """
    steps = harness.get("steps")
    if not isinstance(steps, list):
        return []
    return [
        command
        for step in steps
        if isinstance(step, dict)
        and isinstance((command := step.get("run")), str)
    ]


def _pytest_commands(job: dict[str, Any]) -> list[str]:
    """ジョブが直接起動する pytest コマンドを返す。

    Args:
        job: CI ジョブの構造。

    Returns:
        token として ``pytest`` を含む run コマンド。
    """
    steps = job.get("steps")
    if not isinstance(steps, list):
        return []
    return [
        command
        for step in steps
        if isinstance(step, dict)
        and isinstance((command := step.get("run")), str)
        and "pytest" in shlex.split(command)
    ]


def _compose_database(compose: dict[str, Any]) -> dict[str, Any]:
    """開発用 Compose の db サービスを取得する。

    Args:
        compose: docker-compose.yml の構造。

    Returns:
        db サービスのマッピング。
    """
    services = compose.get("services")
    assert isinstance(services, dict), "Compose に services が必要"
    database = services.get("db")
    assert isinstance(database, dict), "Compose に db サービスが必要"
    return database


def _service_options(options: object) -> dict[str, object]:
    """GitHub service options を option 単位の木へ展開する。

    Args:
        options: ``services.postgres.options`` の値。

    Returns:
        option 名をキーとする木。health command はさらに全 token へ展開する。
    """
    if not isinstance(options, str):
        return {}
    try:
        tokens = shlex.split(options)
    except ValueError:
        return {}

    parsed: dict[str, object] = {}
    index = 0
    while index < len(tokens):
        option = tokens[index]
        if not option.startswith("--") or index + 1 >= len(tokens):
            return {}
        value: object = tokens[index + 1]
        if option == "--health-cmd":
            try:
                value = shlex.split(str(value))
            except ValueError:
                return {}
        if option in parsed:
            return {}
        parsed[option] = value
        index += 2
    return parsed


def _health_command(options: object) -> list[str]:
    """GitHub service options から health command の全 token を得る。

    Args:
        options: ``services.postgres.options`` の値。

    Returns:
        health command の token 配列。構文不正なら空配列。
    """
    command = _service_options(options).get("--health-cmd")
    if not isinstance(command, list) or not all(
        isinstance(token, str) for token in command
    ):
        return []
    return command


def _backend_ci_contract_tree(backend: dict[str, Any]) -> dict[str, Any]:
    """backend ジョブの services から defaults 手前までを全数採取する。

    ``options`` は folded scalar のままでは内部の option が葉にならないため、
    shell 構文を機械的に option と command token の木へ展開する。

    Args:
        backend: backend ジョブの構造。

    Returns:
        全数変異の母集合となる JSON 互換ツリー。
    """
    tree: dict[str, Any] = {}
    collecting = False
    for key, value in backend.items():
        if key == "services":
            collecting = True
        if key == "defaults":
            break
        if collecting:
            tree[key] = copy.deepcopy(value)
    if not tree or "services" not in tree:
        raise AssertionError("backend の services〜defaults ブロックがない")

    options_path = ("services", "postgres", "options")
    options = _mapping_at(tree, options_path)
    parsed_options = _service_options(options)
    if not parsed_options:
        raise AssertionError("postgres service options を構造化できない")
    _set_node_at(tree, options_path, parsed_options)
    return tree


def _render_service_options(options: object) -> str:
    """構造化した service options を GitHub Actions の文字列へ戻す。

    Args:
        options: option 名と値の木。

    Returns:
        ``shlex`` で再解析可能な options 文字列。
    """
    if not isinstance(options, dict):
        return ""
    tokens: list[str] = []
    for option, value in options.items():
        if not isinstance(option, str):
            continue
        tokens.append(option)
        if option == "--health-cmd" and isinstance(value, list):
            tokens.append(shlex.join(str(token) for token in value))
        else:
            tokens.append(str(value))
    return shlex.join(tokens)


def _workflow_from_ci_contract_tree(
    workflow: dict[str, Any], tree: dict[str, Any]
) -> dict[str, Any]:
    """変異した CI 契約木を workflow 構造へ戻す。

    Args:
        workflow: 変異前の workflow。
        tree: services から defaults 手前までの変異済み木。

    Returns:
        検査器へ渡せる workflow のコピー。
    """
    mutated = copy.deepcopy(workflow)
    original_backend = _backend_job(mutated)
    rebuilt_backend: dict[str, Any] = {}
    skipping_contract_block = False
    inserted = False
    for key, value in original_backend.items():
        if key == "services":
            skipping_contract_block = True
            if not inserted:
                rebuilt_backend.update(copy.deepcopy(tree))
                inserted = True
        if key == "defaults":
            skipping_contract_block = False
        if not skipping_contract_block:
            rebuilt_backend[key] = value

    jobs = mutated["jobs"]
    assert isinstance(jobs, dict)
    jobs["backend"] = rebuilt_backend

    options_path = ("services", "postgres", "options")
    options = _mapping_at(rebuilt_backend, options_path)
    _set_node_at(
        rebuilt_backend,
        options_path,
        _render_service_options(options),
    )
    return mutated


def _ci_contract_tree(workflow: dict[str, Any]) -> dict[str, Any]:
    """既存 DB 配線と新設ジョブを含む CI 契約木を返す。

    Args:
        workflow: CI workflow の構造。

    Returns:
        全葉変異の対象となる JSON 互換木。
    """
    harness_commands = _pytest_commands(_harness_job(workflow))
    assert len(harness_commands) == 1, "harness の pytest は 1 回でなければならない"
    return {
        "backend": _backend_ci_contract_tree(_backend_job(workflow)),
        "harness": {"pytest": harness_commands[0]},
        "consistency": copy.deepcopy(_named_job(workflow, "consistency")),
        "mutation": copy.deepcopy(_named_job(workflow, "mutation")),
    }


def _workflow_from_contract_tree(
    workflow: dict[str, Any], tree: dict[str, Any]
) -> dict[str, Any]:
    """一般化した CI 契約木を workflow へ戻す。

    Args:
        workflow: 変異前の workflow。
        tree: 変異済みの CI 契約木。

    Returns:
        静的検査へ渡せる workflow のコピー。
    """
    backend_tree = tree.get("backend")
    assert isinstance(backend_tree, dict)
    mutated = _workflow_from_ci_contract_tree(workflow, backend_tree)
    jobs = mutated.get("jobs")
    assert isinstance(jobs, dict)

    harness_tree = tree.get("harness")
    assert isinstance(harness_tree, dict)
    replacement = harness_tree.get("pytest")
    harness = _harness_job(mutated)
    steps = harness.get("steps")
    assert isinstance(steps, list)
    replaced = 0
    for step in steps:
        if not isinstance(step, dict):
            continue
        command = step.get("run")
        if isinstance(command, str) and "pytest" in shlex.split(command):
            if replacement is None:
                step.pop("run")
            else:
                step["run"] = replacement
            replaced += 1
    assert replaced == 1

    for job_name in NEW_JOB_IDS:
        replacement_job = tree.get(job_name)
        assert isinstance(replacement_job, dict)
        jobs[job_name] = copy.deepcopy(replacement_job)
    return mutated


def _dsn_template_parts(value: object) -> tuple[str, str, str, str] | None:
    """CI の DSN template からユーザー・password・host・DB 名を得る。

    Args:
        value: job env の値。

    Returns:
        構文が限定した PostgreSQL DSN なら 4 要素。その他は ``None``。
    """
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"postgresql://([^:/]+):([^@]+)@([^:/]+):5432/([^/?#]+)", value
    )
    if match is None:
        return None
    return match[1], match[2], match[3], match[4]


def _ci_wiring_errors(
    workflow: dict[str, Any],
    expectations: dict[str, Any],
    compose: dict[str, Any],
) -> list[str]:
    """backend の DB 配線と期待値資産の差分を列挙する。

    Args:
        workflow: 検査対象 workflow。
        expectations: 凍結済み期待値。
        compose: 開発 DB の Compose 設定。

    Returns:
        構造上の不一致。完全一致なら空配列。
    """
    backend = _backend_job(workflow)
    compose_database = _compose_database(compose)
    database = expectations["database_environment"]
    health = expectations["healthcheck"]
    execution = expectations["test_execution"]
    variables = expectations["dsn_environment_variables"]
    errors: list[str] = []

    service = _mapping_at(backend, ("services", "postgres"))
    if not isinstance(service, dict):
        return ["backend.services.postgres がない"]
    image = service.get("image")
    if image != database["image"]["expected"] or image != compose_database.get(
        "image"
    ):
        errors.append("postgres image が期待値・開発 DB と一致しない")

    service_environment = service.get("env")
    compose_environment = compose_database.get("environment")
    if not isinstance(service_environment, dict) or not isinstance(
        compose_environment, dict
    ):
        errors.append("postgres service env がない")
    else:
        initdb_args = service_environment.get("POSTGRES_INITDB_ARGS")
        if initdb_args != database["initdb_args"]["expected"] or initdb_args != (
            compose_environment.get("POSTGRES_INITDB_ARGS")
        ):
            errors.append("POSTGRES_INITDB_ARGS が期待値・開発 DB と一致しない")

    ports = service.get("ports")
    if not isinstance(ports, list) or not any(
        isinstance(port, str) and port.rsplit(":", maxsplit=1)[-1] == "5432"
        for port in ports
    ):
        errors.append("PostgreSQL の TCP port 5432 が公開されていない")

    service_options = _service_options(service.get("options"))
    health_tokens = _health_command(service.get("options"))
    required_tokens = health["host"]["required_command_tokens"]
    if not all(token in health_tokens for token in required_tokens):
        errors.append("health command が期待値の TCP host を明示していない")
    compose_health = compose_database.get("healthcheck")
    compose_test = compose_health.get("test") if isinstance(compose_health, dict) else []
    compose_command = " ".join(compose_test) if isinstance(compose_test, list) else ""
    if not all(token in compose_command for token in required_tokens):
        errors.append("health command が開発 DB の TCP 性質と一致しない")

    service_user = (
        service_environment.get("POSTGRES_USER")
        if isinstance(service_environment, dict)
        else None
    )
    service_password = (
        service_environment.get("POSTGRES_PASSWORD")
        if isinstance(service_environment, dict)
        else None
    )
    service_database = (
        service_environment.get("POSTGRES_DB")
        if isinstance(service_environment, dict)
        else None
    )
    expected_health_command = [
        "pg_isready",
        "-h",
        health["host"]["expected"],
        "-U",
        service_user,
        "-d",
        service_database,
    ]
    if health_tokens != expected_health_command:
        errors.append("health command が service のユーザー・DB と一致しない")

    health_option_contract = {
        "--health-interval": ("interval", "interval"),
        "--health-timeout": ("timeout", "timeout"),
        "--health-retries": ("retries", "retries"),
        "--health-start-period": ("start_period", "start_period"),
    }
    expected_option_names = {"--health-cmd", *health_option_contract}
    if set(service_options) != expected_option_names:
        errors.append("health options の集合が期待値と一致しない")
    for option, (expectation_key, compose_key) in health_option_contract.items():
        expected = health[expectation_key]["expected"]
        ci_value: object = service_options.get(option)
        if isinstance(expected, int) and isinstance(ci_value, str) and ci_value.isdigit():
            ci_value = int(ci_value)
        compose_value = (
            compose_health.get(compose_key)
            if isinstance(compose_health, dict)
            else None
        )
        if ci_value != expected or compose_value != expected:
            errors.append(f"{option} が期待値・開発 DB と一致しない")

    job_environment = backend.get("env")
    if not isinstance(job_environment, dict):
        errors.append("backend job env がない")
    else:
        admin_name = variables["admin_connection"]["expected_name"]
        role_name = variables["tested_role_connection"]["expected_name"]
        admin_dsn = job_environment.get(admin_name)
        role_dsn = job_environment.get(role_name)
        migration_dsn = job_environment.get("PITCHLOG_MIGRATION_DATABASE_URL")
        admin_parts = _dsn_template_parts(admin_dsn)
        role_parts = _dsn_template_parts(role_dsn)
        migration_parts = _dsn_template_parts(migration_dsn)
        if admin_parts is None:
            errors.append("管理接続 DSN の job env がない")
        if role_parts is None:
            errors.append("被検査ロール DSN の job env がない")
        if migration_parts is None:
            errors.append("migration direct URL の job env がない")
        if admin_parts is not None and role_parts is not None:
            expected_admin_parts = (
                service_user,
                service_password,
                "127.0.0.1",
                service_database,
            )
            if admin_parts != expected_admin_parts:
                errors.append("管理接続 DSN が service の資格情報・DB と一致しない")
            if role_parts[0] == admin_parts[0] or role_parts[2:] != admin_parts[2:]:
                errors.append("被検査ロール DSN の認証ユーザー分離が不正")
        if migration_parts is not None:
            expected_migration_parts = (
                service_user,
                service_password,
                "127.0.0.1",
                service_database,
            )
            if migration_parts != expected_migration_parts:
                errors.append("migration direct URL が service の管理接続と一致しない")
        if admin_name == role_name or admin_dsn == role_dsn:
            errors.append("管理接続と被検査ロール接続が分離されていない")
        for value in (admin_dsn, role_dsn, migration_dsn):
            if isinstance(value, str) and (":-" in value or ":+" in value):
                errors.append("DSN 変数間の fallback がある")

    defaults = _mapping_at(backend, ("defaults", "run", "working-directory"))
    if defaults != "backend":
        errors.append("backend working-directory が維持されていない")
    if backend.get("needs") != "backend-changes":
        errors.append("backend-changes の発火制御が維持されていない")

    jobs = workflow.get("jobs")
    backend_changes = jobs.get("backend-changes") if isinstance(jobs, dict) else None
    filter_steps = backend_changes.get("steps") if isinstance(backend_changes, dict) else []
    filter_definition: object = None
    if isinstance(filter_steps, list):
        for step in filter_steps:
            if isinstance(step, dict) and step.get("id") == "filter":
                step_with = step.get("with")
                if isinstance(step_with, dict):
                    filter_definition = step_with.get("filters")
    if not isinstance(filter_definition, str):
        errors.append("backend-changes の paths-filter がない")
    else:
        parsed_filter = yaml.safe_load(filter_definition)
        backend_paths = (
            parsed_filter.get("backend") if isinstance(parsed_filter, dict) else None
        )
        if backend_paths != [
            "backend/**",
            "contracts/**",
            ".github/workflows/ci.yml",
        ]:
            errors.append("backend-changes の既存 paths-filter が変わっている")

    commands = _backend_commands(backend)
    required_backend_commands = [
        "uv python install",
        "uv sync --locked --dev",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run ty check",
        execution["single_command"]["expected"],
        *ALEMBIC_CI_COMMANDS,
    ]
    if commands != required_backend_commands:
        errors.append("backend の既存 6 件 + Alembic 3 段が順序どおりでない")
    expected_alembic_locations = [
        ("backend", command) for command in ALEMBIC_CI_COMMANDS
    ]
    if _alembic_command_locations(workflow) != expected_alembic_locations:
        errors.append("Alembic 3 段は既存 backend ジョブだけで一度ずつ実行する")
    pytest_commands = [command for command in commands if "pytest" in shlex.split(command)]
    single_command = execution["single_command"]
    if pytest_commands != [single_command["expected"]]:
        errors.append("pytest の単一実行コマンドが期待値と一致しない")
    if any("-m" in shlex.split(command) for command in pytest_commands):
        errors.append("DB テストを marker 選択で別実行している")
    if len(pytest_commands) != single_command["expected_backend_pytest_invocation_count"]:
        errors.append("pytest の実行回数が期待値と一致しない")
    return errors


def _expected_new_job_steps(
    workflow: dict[str, Any], pytest_command: str
) -> list[dict[str, Any]]:
    """harness と同じ準備を行う新設ジョブの期待 steps を返す。

    Args:
        workflow: CI workflow の構造。
        pytest_command: 所有する pytest コマンド。

    Returns:
        checkout・uv 準備・所有テスト実行の厳密な配列。
    """
    harness_steps = _harness_job(workflow).get("steps")
    assert isinstance(harness_steps, list)
    assert len(harness_steps) >= 4
    return [
        *copy.deepcopy(harness_steps[:4]),
        {"run": pytest_command},
    ]


def _job_invokes_backend_tests(job_name: str, job: dict[str, Any]) -> bool:
    """ジョブが PostgreSQL を要する backend テストを起動するか判定する。

    SQL 生成物を含む変異スイートは設計上 PostgreSQL を使うため、専用ジョブも
    backend 全件実行と同じ DB 利用ジョブとして扱う。

    Args:
        job_name: ジョブ ID。
        job: CI ジョブの構造。

    Returns:
        DB image を事前取得すべきテストを起動する場合は真。
    """
    if job_name == "mutation":
        return True
    job_directory = _mapping_at(job, ("defaults", "run", "working-directory"))
    steps = job.get("steps")
    if not isinstance(steps, list):
        return False
    for step in steps:
        if not isinstance(step, dict):
            continue
        command = step.get("run")
        if not isinstance(command, str):
            continue
        tokens = shlex.split(command)
        if "pytest" not in tokens:
            continue
        step_directory = step.get("working-directory", job_directory)
        if isinstance(step_directory, str) and (
            step_directory == "backend" or step_directory.startswith("backend/")
        ):
            return True
        if any(
            token == "backend" or token.startswith("backend/tests") for token in tokens
        ):
            return True
    return False


def _domain_ci_wiring_errors(
    workflow: dict[str, Any],
    expectations: dict[str, Any],
    compose: dict[str, Any],
) -> list[str]:
    """ドメイン計算ジョブの所有・予算・DB 配線違反を返す。

    Args:
        workflow: 検査対象 workflow。
        expectations: 凍結済み DB 環境期待値。
        compose: 開発 DB の Compose 設定。

    Returns:
        検出した違反。空配列なら契約を満たす。
    """
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return ["ci.yml に jobs がない"]
    errors: list[str] = []
    job_ids = {name for name in jobs if isinstance(name, str)}
    if not LEGACY_JOB_IDS <= job_ids:
        errors.append("既存 9 ジョブがすべて維持されていない")
    if not NEW_JOB_IDS <= job_ids:
        errors.append("consistency と mutation が揃っていない")

    try:
        _assert_checkout_fetch_depth_contract(workflow)
    except AssertionError as exc:
        errors.append(str(exc))

    harness = jobs.get("harness")
    backend = jobs.get("backend")
    if not isinstance(harness, dict) or not isinstance(backend, dict):
        return [*errors, "harness または backend ジョブがない"]
    expected_harness_commands = [
        "uv python install",
        "uv sync --locked --dev",
        "uv run ruff check .",
        "uv run ty check",
        HARNESS_PYTEST_COMMAND,
    ]
    if _harness_commands(harness) != expected_harness_commands:
        errors.append("harness の単体テスト所有または既存検査コマンドが不正")

    expected_jobs: dict[str, dict[str, Any]] = {
        "consistency": {
            "runs-on": harness.get("runs-on"),
            "timeout-minutes": CONSISTENCY_TIMEOUT_MINUTES,
            "steps": _expected_new_job_steps(workflow, CONSISTENCY_PYTEST_COMMAND),
        },
        "mutation": {
            "runs-on": harness.get("runs-on"),
            "timeout-minutes": MUTATION_TIMEOUT_MINUTES,
            "services": copy.deepcopy(backend.get("services")),
            "env": copy.deepcopy(backend.get("env")),
            "steps": _expected_new_job_steps(workflow, MUTATION_PYTEST_COMMAND),
        },
    }
    for job_name, expected_job in expected_jobs.items():
        if jobs.get(job_name) != expected_job:
            errors.append(f"{job_name} の契約木が期待値と一致しない")

    compose_database = _compose_database(compose)
    expected_image = expectations["database_environment"]["image"]["expected"]
    compose_image = compose_database.get("image")
    for job_name, candidate in jobs.items():
        if not isinstance(job_name, str) or not isinstance(candidate, dict):
            continue
        if not _job_invokes_backend_tests(job_name, candidate):
            continue
        service = _mapping_at(candidate, ("services", "postgres"))
        if not isinstance(service, dict):
            errors.append(f"{job_name} は DB テストを呼ぶが postgres service がない")
            continue
        if service.get("image") != expected_image or service.get("image") != compose_image:
            errors.append(f"{job_name} の postgres image が 3 者一致しない")
    return errors


def _combined_ci_wiring_errors(
    workflow: dict[str, Any],
    expectations: dict[str, Any],
    compose: dict[str, Any],
) -> list[str]:
    """既存契約とドメイン計算ジョブ契約の違反をまとめる。

    Args:
        workflow: 検査対象 workflow。
        expectations: 凍結済み DB 環境期待値。
        compose: 開発 DB の Compose 設定。

    Returns:
        両検査が検出した違反。
    """
    return [
        *_ci_wiring_errors(workflow, expectations, compose),
        *_domain_ci_wiring_errors(workflow, expectations, compose),
    ]


def _pytest_selection(command: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """pytest コマンドから対象と除外対象を得る。

    Args:
        command: ``pytest`` を含む run コマンド。

    Returns:
        ``(選択 path, ignore path)`` の組。
    """
    tokens = shlex.split(command)
    pytest_index = tokens.index("pytest")
    selectors: list[str] = []
    ignored: list[str] = []
    index = pytest_index + 1
    while index < len(tokens):
        token = tokens[index]
        if token == "-c":
            index += 2
            continue
        if token.startswith("--ignore="):
            ignored.append(token.split("=", maxsplit=1)[1].rstrip("/"))
        elif not token.startswith("-"):
            selectors.append(token.rstrip("/"))
        index += 1
    return tuple(selectors), tuple(ignored)


def _selector_contains(selector: str, test_path: str) -> bool:
    """pytest の path selector がテストファイルを含むか返す。"""
    return test_path == selector or test_path.startswith(f"{selector}/")


def _selected_root_test_jobs(
    workflow: dict[str, Any], test_path: str
) -> set[str]:
    """指定したルートテストを直接所有するジョブ集合を返す。

    Args:
        workflow: CI workflow の構造。
        test_path: リポジトリルートからのテスト path。

    Returns:
        対象に含み、かつ ignore していないジョブ ID 集合。
    """
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict)
    selected: set[str] = set()
    for job_name, job in jobs.items():
        if not isinstance(job_name, str) or not isinstance(job, dict):
            continue
        job_directory = _mapping_at(job, ("defaults", "run", "working-directory"))
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            command = step.get("run")
            if not isinstance(command, str) or "pytest" not in shlex.split(command):
                continue
            working_directory = step.get("working-directory", job_directory)
            if working_directory not in (None, "."):
                continue
            selectors, ignored = _pytest_selection(command)
            if any(_selector_contains(path, test_path) for path in ignored):
                continue
            if any(_selector_contains(path, test_path) for path in selectors):
                selected.add(job_name)
    return selected


def _step_test_paths(first: int, last: int) -> tuple[str, ...]:
    """steps.json の指定範囲から pytest 対象 path を導出する。

    Args:
        first: 最初のステップ ID。
        last: 最後のステップ ID。

    Returns:
        各ステップの command が指すテスト path。
    """
    source = json.loads(STEPS_PATH.read_text(encoding="utf-8"))
    steps = source.get("steps")
    assert isinstance(steps, list)
    paths: list[str] = []
    for step in steps:
        if not isinstance(step, dict) or not first <= step.get("id", 0) <= last:
            continue
        command = step.get("command")
        assert isinstance(command, str)
        test_paths = [
            token
            for token in shlex.split(command.strip("`"))
            if token.startswith("tests/")
        ]
        assert len(test_paths) == 1
        paths.append(test_paths[0])
    return tuple(paths)


def _derive_asset_actuals(
    workflow: dict[str, Any], compose: dict[str, Any]
) -> dict[NodePath, object]:
    """期待値属性に対応する実装・開発 DB 側の値を構造から導出する。

    Args:
        workflow: CI workflow の構造。
        compose: 開発 DB の Compose 設定。

    Returns:
        期待値資産内の属性パスと、実装側から導出した値。
    """
    backend = _backend_job(workflow)
    service = _mapping_at(backend, ("services", "postgres"))
    assert isinstance(service, dict)
    compose_database = _compose_database(compose)
    compose_environment = compose_database["environment"]
    assert isinstance(compose_environment, dict)
    initdb_args = compose_environment["POSTGRES_INITDB_ARGS"]
    assert isinstance(initdb_args, str)
    image = compose_database["image"]
    assert isinstance(image, str)
    version_match = re.fullmatch(r"postgres:(\d+)\.(\d+)-bookworm", image)
    assert version_match is not None
    server_version_num = int(version_match[1]) * 10000 + int(version_match[2])
    image_version = f"{version_match[1]}.{version_match[2]}"

    init_tokens = shlex.split(initdb_args)
    init_values = dict(token[2:].split("=", maxsplit=1) for token in init_tokens)
    health_tokens = _health_command(service["options"])
    health_host = health_tokens[health_tokens.index("-h") + 1]
    compose_health = compose_database["healthcheck"]
    assert isinstance(compose_health, dict)
    commands = _backend_commands(backend)
    pytest_commands = [command for command in commands if "pytest" in shlex.split(command)]
    marker_config = tomllib.loads(BACKEND_PYPROJECT_PATH.read_text(encoding="utf-8"))
    marker_entries = marker_config["tool"]["pytest"]["ini_options"]["markers"]
    marker_name = str(marker_entries[0]).split(":", maxsplit=1)[0]
    conftest_text = DB_CONFTEST_PATH.read_text(encoding="utf-8")
    job_environment = backend["env"]
    assert isinstance(job_environment, dict)
    admin_names = [name for name in job_environment if "ADMIN" in name]
    role_names = [name for name in job_environment if "ROLE" in name]
    assert len(admin_names) == 1 and len(role_names) == 1
    admin_name = admin_names[0]
    role_name = role_names[0]
    admin_value = job_environment[admin_name]
    role_value = job_environment[role_name]
    assert isinstance(admin_value, str) and isinstance(role_value, str)

    exact = "exact"
    actuals: dict[NodePath, object] = {
        ("oracle_policy", "expectations_must_precede_observation_code"): True,
        ("oracle_policy", "observed_values_must_not_reseal_this_asset"): True,
        ("database_environment", "image", "expected"): image,
        ("database_environment", "image", "comparison"): exact,
        ("database_environment", "initdb_args", "expected"): initdb_args,
        ("database_environment", "initdb_args", "comparison"): exact,
        (
            "database_environment",
            "server_version_num",
            "expected",
        ): server_version_num,
        ("database_environment", "server_version_num", "comparison"): exact,
        (
            "database_environment",
            "server_version_num",
            "observed_type",
        ): "integer",
        (
            "database_environment",
            "server_version_num",
            "derivation",
            "image_version",
        ): image_version,
        (
            "database_environment",
            "server_version_num",
            "derivation",
            "rule",
        ): "PostgreSQL 10以降の server_version_num = major * 10000 + minor",
        (
            "database_environment",
            "server_version_num",
            "derivation",
            "calculation",
        ): f"{version_match[1]} * 10000 + {version_match[2]} = {server_version_num}",
        (
            "database_environment",
            "server_version_num",
            "derivation",
            "exact_match_reason",
        ): f"イメージタグがメジャー版だけでなく {image_version} まで固定されているため",
        (
            "database_environment",
            "locale_provider",
            "expected",
        ): init_values["locale-provider"],
        ("database_environment", "locale_provider", "comparison"): exact,
        ("database_environment", "collate", "expected"): init_values["locale"],
        ("database_environment", "collate", "comparison"): exact,
        ("database_environment", "ctype", "expected"): init_values["locale"],
        ("database_environment", "ctype", "comparison"): exact,
        ("database_environment", "encoding", "expected"): init_values["encoding"],
        ("database_environment", "encoding", "comparison"): exact,
        ("healthcheck", "transport", "expected"): "tcp",
        ("healthcheck", "transport", "comparison"): exact,
        ("healthcheck", "host", "expected"): health_host,
        ("healthcheck", "host", "comparison"): exact,
        ("healthcheck", "host", "required_command_tokens"): ["-h", health_host],
        ("healthcheck", "implicit_unix_socket_allowed", "expected"): False,
        ("healthcheck", "implicit_unix_socket_allowed", "comparison"): exact,
        ("healthcheck", "interval", "expected"): compose_health["interval"],
        ("healthcheck", "interval", "comparison"): exact,
        ("healthcheck", "timeout", "expected"): compose_health["timeout"],
        ("healthcheck", "timeout", "comparison"): exact,
        ("healthcheck", "retries", "expected"): compose_health["retries"],
        ("healthcheck", "retries", "comparison"): exact,
        ("healthcheck", "start_period", "expected"): compose_health[
            "start_period"
        ],
        ("healthcheck", "start_period", "comparison"): exact,
        ("test_execution", "required_marker", "expected"): marker_name,
        ("test_execution", "required_marker", "comparison"): exact,
        (
            "test_execution",
            "required_path",
            "expected_repository_prefix",
        ): "backend/tests/db/",
        ("test_execution", "required_path", "comparison"): "path_prefix",
        ("test_execution", "single_command", "expected"): pytest_commands[0],
        ("test_execution", "single_command", "comparison"): exact,
        (
            "test_execution",
            "single_command",
            "db_tests_included_in_existing_invocation",
        ): len(pytest_commands) == 1 and "-m" not in shlex.split(pytest_commands[0]),
        (
            "test_execution",
            "single_command",
            "marker_selection_argument_allowed",
        ): any("-m" in shlex.split(command) for command in pytest_commands),
        (
            "test_execution",
            "single_command",
            "additional_db_test_invocation_allowed",
        ): len(pytest_commands) > 1,
        (
            "test_execution",
            "single_command",
            "expected_backend_pytest_invocation_count",
        ): len(pytest_commands),
        ("test_execution", "missing_dsn_policy", "expected"): "fail",
        ("test_execution", "missing_dsn_policy", "skip_allowed"): (
            "pytest.skip" in conftest_text
        ),
        ("test_execution", "missing_dsn_policy", "comparison"): exact,
        ("dsn_environment_variables", "admin_connection", "expected_name"): (
            admin_name
        ),
        (
            "dsn_environment_variables",
            "admin_connection",
            "value_must_not_be_stored_in_repository",
        ): "${{" in admin_value,
        (
            "dsn_environment_variables",
            "tested_role_connection",
            "expected_name",
        ): role_name,
        (
            "dsn_environment_variables",
            "tested_role_connection",
            "value_must_not_be_stored_in_repository",
        ): "${{" in role_value,
        (
            "dsn_environment_variables",
            "separation",
            "distinct_variable_names_required",
        ): admin_name != role_name,
        (
            "dsn_environment_variables",
            "separation",
            "fallback_between_variables_allowed",
        ): any(":-" in value or ":+" in value for value in (admin_value, role_value)),
        (
            "dsn_environment_variables",
            "separation",
            "role_identity_check_required",
        ): all(token in conftest_text for token in ("session_user", "current_user")),
    }
    return actuals


def _asset_contract_errors(
    expectations: dict[str, Any], actuals: dict[NodePath, object]
) -> list[str]:
    """期待値資産と実装値・典拠の差分を列挙する。

    Args:
        expectations: 検査対象の期待値資産。
        actuals: 構造から導出した実装側の値。

    Returns:
        属性単位の差分。完全一致なら空配列。
    """
    errors: list[str] = []
    for path, actual in actuals.items():
        expected = _mapping_at(expectations, path)
        if expected != actual:
            errors.append(
                f"{_format_path(path)}: expected={expected!r}, actual={actual!r}"
            )

    if expectations.get("schema_version") != 1:
        errors.append("schema_version は 1 が必要")
    if expectations.get("asset_kind") != "db_environment_expectations":
        errors.append("asset_kind が不正")
    source_revision = expectations.get("source_revision")
    if not isinstance(source_revision, str) or re.fullmatch(
        r"[0-9a-f]{40}", source_revision
    ) is None:
        errors.append("source_revision は 40 桁の commit ID が必要")

    errors.extend(_provenance_errors(expectations))
    return errors


def _provenance_errors(node: object) -> list[str]:
    """資産内の全 provenance を再帰走査して逐語一致を検査する。

    Args:
        node: 検査対象の JSON 互換値。

    Returns:
        path 実在性・逐語一致・構造の違反。
    """
    errors: list[str] = []
    if isinstance(node, list):
        for value in node:
            errors.extend(_provenance_errors(value))
        return errors
    if not isinstance(node, dict):
        return errors

    if "provenance" in node:
        raw_entries = node["provenance"]
        if isinstance(raw_entries, dict):
            entries = [raw_entries]
        elif isinstance(raw_entries, list) and raw_entries:
            entries = raw_entries
        else:
            entries = []
            errors.append("provenance は空でないオブジェクトまたは配列が必要")
        for entry in entries:
            if not isinstance(entry, dict):
                errors.append("provenance の要素はオブジェクトが必要")
                continue
            path_text = entry.get("path")
            extracted_text = entry.get("extracted_text")
            if not isinstance(path_text, str) or not path_text:
                errors.append("provenance.path は空でない文字列が必要")
                continue
            source_path = (REPOSITORY_ROOT / path_text).resolve()
            try:
                source_path.relative_to(REPOSITORY_ROOT)
            except ValueError:
                errors.append(f"provenance.path がリポジトリ外: {path_text}")
                continue
            if not source_path.is_file():
                errors.append(f"provenance.path が実在しない: {path_text}")
                continue
            if not isinstance(extracted_text, str) or not extracted_text:
                errors.append("provenance.extracted_text は空でない文字列が必要")
                continue
            normalized_source = "".join(
                source_path.read_text(encoding="utf-8").split()
            )
            if "".join(extracted_text.split()) not in normalized_source:
                errors.append(f"provenance が逐語一致しない: {path_text}")

    for value in node.values():
        errors.extend(_provenance_errors(value))
    return errors


def _mutate_contract_value(value: object) -> object:
    """型を保った機械的な 1 属性変異を作る。

    Args:
        value: 変異する属性値。

    Returns:
        元値と異なる値。
    """
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        return f"{value}-mutated"
    if isinstance(value, list):
        return [*value, "mutated"]
    raise AssertionError(f"未対応の変異型: {type(value).__name__}")


def _set_node_at(node: object, path: NodePath, value: object) -> None:
    """JSON 互換ツリーの既存パス終端を書き換える。

    Args:
        node: 書き換える JSON 互換値。
        path: 既存キーまたは配列 index の並び。
        value: 新しい値。
    """
    current: Any = node
    for segment in path[:-1]:
        if isinstance(segment, str):
            assert isinstance(current, dict) and segment in current
            current = current[segment]
        else:
            assert isinstance(current, list) and 0 <= segment < len(current)
            current = current[segment]
    final = path[-1]
    if isinstance(final, str):
        assert isinstance(current, dict) and final in current
        current[final] = value
    else:
        assert isinstance(current, list) and 0 <= final < len(current)
        current[final] = value


def _delete_node_at(node: object, path: NodePath) -> None:
    """JSON 互換ツリーの既存葉をキーまたは要素ごと削除する。

    Args:
        node: 書き換える JSON 互換値。
        path: 削除対象の葉パス。
    """
    current: Any = node
    for segment in path[:-1]:
        if isinstance(segment, str):
            assert isinstance(current, dict) and segment in current
            current = current[segment]
        else:
            assert isinstance(current, list) and 0 <= segment < len(current)
            current = current[segment]
    final = path[-1]
    if isinstance(final, str):
        assert isinstance(current, dict) and final in current
        del current[final]
    else:
        assert isinstance(current, list) and 0 <= final < len(current)
        current.pop(final)


def _assert_full_docs_lint_wiring(text: str) -> None:
    commands = _docs_lint_commands(_load_workflow(text))
    assert any("check_docs_status" in command for command in commands), (
        "check_docs_status.py の既存配線を残さなければならない"
    )

    matched_indexes: list[int] = []
    for check_name in REQUIRED_FULL_CHECKS:
        matches = [
            (index, command)
            for index, command in enumerate(commands)
            if check_name in command
        ]
        assert len(matches) == 1, f"{check_name} を走らせる step は 1 件必要"
        index, command = matches[0]
        assert not any(selector in command for selector in FORBIDDEN_SELECTORS), (
            f"{check_name} は選択実行にせず、引数なしで全検査を走らせる"
        )
        matched_indexes.append(index)

    assert len(set(matched_indexes)) == len(REQUIRED_FULL_CHECKS), (
        "2 つの文書検査は別々の step として配線しなければならない"
    )


def test_docs_lint_runs_all_document_checks_without_selectors() -> None:
    _assert_full_docs_lint_wiring(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_docs_lint_rejects_selective_check_option() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    selective = workflow.replace(
        "scripts/check_doc_coverage.py",
        "scripts/check_doc_coverage.py --checks attribution",
        1,
    )
    assert selective != workflow

    with pytest.raises(AssertionError, match="選択実行"):
        _assert_full_docs_lint_wiring(selective)


def test_frontend_paths_filter_includes_sync_protocol_oracle() -> None:
    """同期プロトコルのオラクル変更で frontend 検査が発火することを確認する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "ci.yml に jobs が必要"
    frontend_changes = jobs.get("frontend-changes")
    assert isinstance(frontend_changes, dict), "frontend-changes ジョブが必要"
    steps = frontend_changes.get("steps")
    assert isinstance(steps, list), "frontend-changes.steps は配列が必要"
    filter_step = next(
        (
            step
            for step in steps
            if isinstance(step, dict) and step.get("id") == "filter"
        ),
        None,
    )
    assert isinstance(filter_step, dict), "frontend の paths-filter が必要"
    filter_with = filter_step.get("with")
    assert isinstance(filter_with, dict), "frontend の paths-filter.with が必要"
    filter_definition = filter_with.get("filters")
    assert isinstance(filter_definition, str), "frontend の filters 定義が必要"
    parsed_filter = yaml.safe_load(filter_definition)
    assert isinstance(parsed_filter, dict), "frontend の filters はマッピングが必要"
    frontend_paths = parsed_filter.get("frontend")
    assert isinstance(frontend_paths, list), "frontend filter は配列が必要"
    assert "scripts/design_relations/sync-protocol.json" in frontend_paths


def test_checkout_fetch_depth_is_exact_for_every_job() -> None:
    """全ジョブの checkout と fetch-depth の両集合を固定する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    _assert_checkout_fetch_depth_contract(workflow)


def test_checkout_fetch_depth_rejects_step_three_rollback() -> None:
    """harness の完全履歴設定を外すと拒否する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(workflow)
    checkout = _checkout_step("harness", _harness_job(mutated))
    _delete_node_at(checkout, ("with", "fetch-depth"))

    with pytest.raises(AssertionError, match="fetch-depth: 0 を持つジョブ"):
        _assert_checkout_fetch_depth_contract(mutated)


def test_checkout_fetch_depth_rejects_fictitious_declared_job() -> None:
    """宣言へ架空ジョブを足すと拒否する。"""
    declared_with = CHECKOUT_JOBS_WITH_FETCH_DEPTH_ZERO | {"fictitious-job"}
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))

    with pytest.raises(AssertionError, match="fetch-depth: 0 を持つジョブ"):
        _assert_checkout_fetch_depth_contract(
            workflow,
            with_fetch_depth_zero=declared_with,
        )


def test_checkout_fetch_depth_rejects_missing_declared_job() -> None:
    """宣言から既存ジョブを外すと拒否する。"""
    declared_with = CHECKOUT_JOBS_WITH_FETCH_DEPTH_ZERO - {"backend"}
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))

    with pytest.raises(AssertionError, match="fetch-depth: 0 を持つジョブ"):
        _assert_checkout_fetch_depth_contract(
            workflow,
            with_fetch_depth_zero=declared_with,
        )


def test_checkout_fetch_depth_rejects_new_shallow_job() -> None:
    """完全履歴を持たない新設ジョブが宣言外なら拒否する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(workflow)
    jobs = _mapping_at(mutated, ("jobs",))
    assert isinstance(jobs, dict)
    jobs["new-shallow-job"] = copy.deepcopy(jobs["docs-lint"])

    with pytest.raises(AssertionError, match="fetch-depth: 0 を持たないジョブ"):
        _assert_checkout_fetch_depth_contract(mutated)


@pytest.mark.parametrize(
    "forged_action_id",
    (
        pytest.param("evil/actions/checkout", id="owner-prefix"),
        pytest.param("actions/checkout-fake", id="repository-suffix"),
    ),
)
def test_checkout_fetch_depth_rejects_forged_checkout_action_id(
    forged_action_id: str,
) -> None:
    """公式 checkout に似せた action ID を拒否する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(workflow)
    checkout = _checkout_step("harness", _harness_job(mutated))
    uses = _mapping_at(checkout, ("uses",))
    assert isinstance(uses, str)
    _, separator, ref = uses.partition("@")
    assert separator == "@" and ref
    forged_uses = f"{forged_action_id}@{ref}"
    _set_node_at(checkout, ("uses",), forged_uses)

    with pytest.raises(
        AssertionError,
        match=re.escape("actions/checkout@<40桁SHA> でない"),
    ) as raised:
        _assert_checkout_fetch_depth_contract(mutated)
    assert forged_uses in str(raised.value)


def test_checkout_fetch_depth_rejects_additional_forged_checkout_step() -> None:
    """本物と偽装 checkout の重複を候補件数で拒否する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(workflow)
    harness = _harness_job(mutated)
    checkout = _checkout_step("harness", harness)
    uses = _mapping_at(checkout, ("uses",))
    assert isinstance(uses, str)
    _, separator, ref = uses.partition("@")
    assert separator == "@" and ref
    forged_uses = f"evil/actions/checkout@{ref}"
    forged_checkout = copy.deepcopy(checkout)
    _set_node_at(forged_checkout, ("uses",), forged_uses)
    _set_node_at(forged_checkout, ("with", "fetch-depth"), 1)
    steps = _mapping_at(harness, ("steps",))
    assert isinstance(steps, list)
    steps.append(forged_checkout)

    with pytest.raises(AssertionError, match="checkout ステップが複数ある") as raised:
        _assert_checkout_fetch_depth_contract(mutated)
    message = str(raised.value)
    assert uses in message
    assert forged_uses in message


def test_checkout_fetch_depth_rejects_tagged_checkout() -> None:
    """checkout のタグ固定を SHA 固定違反として拒否する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(workflow)
    checkout = _checkout_step("harness", _harness_job(mutated))
    tagged_uses = "actions/checkout@v5"
    _set_node_at(checkout, ("uses",), tagged_uses)

    with pytest.raises(
        AssertionError,
        match=re.escape("actions/checkout@<40桁SHA> でない"),
    ) as raised:
        _assert_checkout_fetch_depth_contract(mutated)
    assert tagged_uses in str(raised.value)


def test_checkout_fetch_depth_rejects_additional_mixed_case_checkout_step() -> None:
    """大小文字違いの偽装 checkout 追加を候補件数で拒否する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(workflow)
    harness = _harness_job(mutated)
    checkout = _checkout_step("harness", harness)
    uses = _mapping_at(checkout, ("uses",))
    assert isinstance(uses, str)
    _, separator, ref = uses.partition("@")
    assert separator == "@" and ref
    forged_uses = f"evil/actions/CheckOut@{ref}"
    forged_checkout = copy.deepcopy(checkout)
    _set_node_at(forged_checkout, ("uses",), forged_uses)
    _set_node_at(forged_checkout, ("with", "fetch-depth"), 1)
    steps = _mapping_at(harness, ("steps",))
    assert isinstance(steps, list)
    steps.append(forged_checkout)

    with pytest.raises(AssertionError, match="checkout ステップが複数ある") as raised:
        _assert_checkout_fetch_depth_contract(mutated)
    message = str(raised.value)
    assert uses in message
    assert forged_uses in message


def test_checkout_fetch_depth_rejects_uppercase_forged_checkout_action() -> None:
    """大文字の偽装 checkout を同一性違反として拒否する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(workflow)
    checkout = _checkout_step("harness", _harness_job(mutated))
    uses = _mapping_at(checkout, ("uses",))
    assert isinstance(uses, str)
    _, separator, ref = uses.partition("@")
    assert separator == "@" and ref
    forged_uses = f"evil/actions/CHECKOUT@{ref}"
    _set_node_at(checkout, ("uses",), forged_uses)

    with pytest.raises(
        AssertionError,
        match=re.escape("actions/checkout@<40桁SHA> でない"),
    ) as raised:
        _assert_checkout_fetch_depth_contract(mutated)
    assert forged_uses in str(raised.value)


def _staging_profile_registry(tmp_path: Path, *, include_second: bool) -> Path:
    """サンプルプロファイル1〜2件のstagingレジストリを作る。"""
    source = REPOSITORY_ROOT / "tests" / "fixtures" / "profile-sample" / "profiles"
    destination = tmp_path / "profiles"
    destination.mkdir(parents=True, exist_ok=True)
    source_registry = json.loads(
        (source / "registry.json").read_text(encoding="utf-8")
    )
    entries = source_registry["profiles"][: 2 if include_second else 1]
    filenames = ("profile.json", "data-model-like.json")[: len(entries)]
    for entry, filename in zip(entries, filenames, strict=True):
        profile_path = destination / filename
        profile_path.write_text(
            (source / filename).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        entry["file"] = str(profile_path)
    registry = {"schema_version": 1, "profiles": entries}
    registry_path = destination / "registry.json"
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False),
        encoding="utf-8",
    )
    return registry_path


def _run_document_checker(script: str, registry: Path) -> subprocess.CompletedProcess[str]:
    """文書検査をstagingレジストリ指定で実行する。"""
    return subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "scripts" / script), "--registry", str(registry)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "script",
    ("check_design_propagation.py", "check_doc_coverage.py"),
)
def test_registry_addition_makes_both_document_checkers_enumerate_all_profiles(
    tmp_path: Path,
    script: str,
) -> None:
    """レジストリへ1件足すと両検査が2プロファイルを識別して検査する。"""
    single = _staging_profile_registry(tmp_path / "single", include_second=False)
    assert _run_document_checker(script, single).returncode in {0, 1}

    doubled = _staging_profile_registry(tmp_path / "doubled", include_second=True)
    result = _run_document_checker(script, doubled)

    assert result.returncode == 1
    assert "[sample-minimal]" in result.stderr
    assert "[data-model-like]" in result.stderr


@pytest.mark.parametrize(
    "mutation",
    ("unregistered", "missing", "duplicate-name", "duplicate-document", "zero"),
)
def test_document_checker_registry_enumeration_is_fail_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    """列挙集合不一致・重複・0件を両スクリプトで終了2にする。"""
    registry_path = _staging_profile_registry(tmp_path, include_second=True)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    profile_dir = registry_path.parent
    if mutation == "unregistered":
        (profile_dir / "orphan.json").write_text(
            (profile_dir / "profile.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    elif mutation == "missing":
        (profile_dir / "data-model-like.json").unlink()
    elif mutation == "duplicate-name":
        registry["profiles"][1]["name"] = registry["profiles"][0]["name"]
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
    elif mutation == "duplicate-document":
        registry["profiles"][1]["document"] = registry["profiles"][0]["document"]
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
    else:
        registry["profiles"] = []
        (profile_dir / "profile.json").unlink()
        (profile_dir / "data-model-like.json").unlink()
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

    for script in ("check_design_propagation.py", "check_doc_coverage.py"):
        result = _run_document_checker(script, registry_path)
        assert result.returncode == 2, (script, mutation, result.stderr)


def test_pytest_commands_and_working_directories_are_exact() -> None:
    """pytest コマンドと harness/backend の実行ディレクトリを固定する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    harness = _harness_job(workflow)
    harness_pytest_commands = [
        command
        for command in _harness_commands(harness)
        if "pytest" in shlex.split(command)
    ]
    assert harness_pytest_commands == [HARNESS_PYTEST_COMMAND]

    assert _mapping_at(harness, ("defaults", "run", "working-directory")) is None
    harness_steps = harness.get("steps")
    assert isinstance(harness_steps, list), "harness.steps は配列でなければならない"
    assert all(
        "working-directory" not in step
        for step in harness_steps
        if isinstance(step, dict)
    ), "harness の各 step はリポジトリルートで実行しなければならない"

    backend = _backend_job(workflow)
    assert _mapping_at(backend, ("defaults", "run", "working-directory")) == "backend"


def test_backend_postgres_wiring_matches_asset_and_development_database() -> None:
    """backend ジョブの PostgreSQL 配線が期待値と開発 DB に一致する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert _ci_wiring_errors(
        workflow,
        _load_expectations(),
        _load_yaml_mapping(COMPOSE_PATH),
    ) == []


def test_database_jobs_match_asset_and_development_database() -> None:
    """DB 利用ジョブすべての PostgreSQL image を 3 者一致させる。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert _combined_ci_wiring_errors(
        workflow,
        _load_expectations(),
        _load_yaml_mapping(COMPOSE_PATH),
    ) == []


def test_new_jobs_accept_valid_wiring_with_explicit_timeouts() -> None:
    """所有分離・DB 配線・二段目の時間上限を持つ実配線を受理する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))

    assert _domain_ci_wiring_errors(
        workflow,
        _load_expectations(),
        _load_yaml_mapping(COMPOSE_PATH),
    ) == []
    assert (
        _named_job(workflow, "consistency")["timeout-minutes"]
        == CONSISTENCY_TIMEOUT_MINUTES
    )
    assert _named_job(workflow, "mutation")["timeout-minutes"] == MUTATION_TIMEOUT_MINUTES


def test_missing_postgres_service_from_new_db_job_is_red() -> None:
    """新設した DB 利用ジョブの postgres service 書き忘れを拒否する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(workflow)
    _named_job(mutated, "mutation").pop("services")

    errors = _domain_ci_wiring_errors(
        mutated,
        _load_expectations(),
        _load_yaml_mapping(COMPOSE_PATH),
    )

    assert "mutation は DB テストを呼ぶが postgres service がない" in errors


def test_services_less_job_cannot_invoke_backend_tests() -> None:
    """service を持たないジョブから backend テストを呼ぶ経路を拒否する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(workflow)
    consistency = _named_job(mutated, "consistency")
    steps = consistency.get("steps")
    assert isinstance(steps, list)
    steps[-1] = {"run": "uv run pytest backend/tests/"}

    errors = _domain_ci_wiring_errors(
        mutated,
        _load_expectations(),
        _load_yaml_mapping(COMPOSE_PATH),
    )

    assert "consistency は DB テストを呼ぶが postgres service がない" in errors


def test_all_database_job_images_match_the_three_sources() -> None:
    """DB 利用ジョブごとに image の 3 者一致を要求する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(workflow)
    mutation_service = _mapping_at(
        _named_job(mutated, "mutation"), ("services", "postgres")
    )
    assert isinstance(mutation_service, dict)
    mutation_service["image"] = "postgres:16.0-bookworm"

    errors = _domain_ci_wiring_errors(
        mutated,
        _load_expectations(),
        _load_yaml_mapping(COMPOSE_PATH),
    )

    assert "mutation の postgres image が 3 者一致しない" in errors


def test_group_four_and_plan_history_audits_belong_only_to_consistency() -> None:
    """第 4 群とステップ 51・52 を consistency だけへ配線する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    group_four = _step_test_paths(17, 25)
    structural_audits = _step_test_paths(51, 52)

    assert len(group_four) == 9
    assert len(structural_audits) == 2
    for test_path in (*group_four, *structural_audits):
        assert _selected_root_test_jobs(workflow, test_path) == {"consistency"}


def test_root_tests_have_exactly_one_owner_job() -> None:
    """ルート pytest の同一テストを複数ジョブで直接実行しない。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    test_paths = sorted(
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in (REPOSITORY_ROOT / "tests").rglob("test_*.py")
    )
    violations = {
        path: sorted(_selected_root_test_jobs(workflow, path))
        for path in test_paths
        if len(_selected_root_test_jobs(workflow, path)) != 1
    }

    assert test_paths
    assert violations == {}


@pytest.mark.parametrize(
    "mutation",
    (
        "missing-upgrade",
        "missing-current",
        "missing-check",
        "duplicate",
        "wrong-order",
        "separate-job",
    ),
)
def test_alembic_ci_command_negative_cases_are_red(mutation: str) -> None:
    """Alembic 3 段の欠落・重複・順序違い・別ジョブ追加を拒否する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(workflow)
    backend = _backend_job(mutated)
    steps = backend.get("steps")
    assert isinstance(steps, list)
    alembic_indexes = [
        index
        for index, step in enumerate(steps)
        if isinstance(step, dict)
        and isinstance((command := step.get("run")), str)
        and command in ALEMBIC_CI_COMMANDS
    ]
    assert len(alembic_indexes) == len(ALEMBIC_CI_COMMANDS)

    if mutation.startswith("missing-"):
        missing_command = {
            "missing-upgrade": ALEMBIC_CI_COMMANDS[0],
            "missing-current": ALEMBIC_CI_COMMANDS[1],
            "missing-check": ALEMBIC_CI_COMMANDS[2],
        }[mutation]
        steps.pop(alembic_indexes[ALEMBIC_CI_COMMANDS.index(missing_command)])
    elif mutation == "duplicate":
        steps.insert(
            alembic_indexes[0],
            copy.deepcopy(steps[alembic_indexes[0]]),
        )
    elif mutation == "wrong-order":
        first, second = alembic_indexes[:2]
        steps[first], steps[second] = steps[second], steps[first]
    else:
        jobs = mutated.get("jobs")
        assert isinstance(jobs, dict)
        jobs["detached-alembic"] = {
            "runs-on": "ubuntu-latest",
            "steps": [{"run": command} for command in ALEMBIC_CI_COMMANDS],
        }

    errors = _ci_wiring_errors(
        mutated,
        _load_expectations(),
        _load_yaml_mapping(COMPOSE_PATH),
    )

    assert "Alembic 3 段は既存 backend ジョブだけで一度ずつ実行する" in errors


def test_every_ci_contract_leaf_value_and_deletion_mutation_is_red() -> None:
    """CI 契約ブロックの全葉を機械列挙し、値改変・削除を拒否する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    expectations = _load_expectations()
    compose = _load_yaml_mapping(COMPOSE_PATH)
    contract_tree = _ci_contract_tree(workflow)
    leaf_paths = _leaf_paths(contract_tree)
    escaped: list[str] = []
    attempts = 0

    for path in leaf_paths:
        for operation in ("value", "deletion"):
            attempts += 1
            mutated_tree = copy.deepcopy(contract_tree)
            if operation == "value":
                current = _mapping_at(mutated_tree, path)
                _set_node_at(
                    mutated_tree,
                    path,
                    _mutate_contract_value(current),
                )
            else:
                _delete_node_at(mutated_tree, path)
            mutated_workflow = _workflow_from_contract_tree(
                workflow,
                mutated_tree,
            )
            if not _combined_ci_wiring_errors(mutated_workflow, expectations, compose):
                escaped.append(f"{operation}:{_format_path(path)}")

    assert attempts == EXPECTED_CI_CONTRACT_MUTATION_ATTEMPTS
    assert escaped == [], f"CI 配線変異がすり抜けた: {escaped}"


def test_every_expectation_leaf_value_and_deletion_mutation_is_red() -> None:
    """期待値資産の全葉を機械列挙し、値改変・削除を拒否する。"""
    workflow = _load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8"))
    compose = _load_yaml_mapping(COMPOSE_PATH)
    expectations = _load_expectations()
    actuals = _derive_asset_actuals(workflow, compose)
    assert _asset_contract_errors(expectations, actuals) == []
    leaf_paths = _leaf_paths(expectations)
    escaped: list[str] = []

    for path in leaf_paths:
        for operation in ("value", "deletion"):
            mutated = copy.deepcopy(expectations)
            if operation == "value":
                current = _mapping_at(mutated, path)
                _set_node_at(mutated, path, _mutate_contract_value(current))
            else:
                _delete_node_at(mutated, path)
            if not _asset_contract_errors(mutated, actuals):
                escaped.append(f"{operation}:{_format_path(path)}")

    assert leaf_paths, "期待値資産の葉が 1 件もない"
    assert escaped == [], f"期待値属性変異がすり抜けた: {escaped}"


def test_db_marker_zero_execution_guard_and_single_invocation_are_wired() -> None:
    """専用 marker・0 件失敗・単一 pytest 実行を構造で確認する。"""
    expectations = _load_expectations()
    marker = expectations["test_execution"]["required_marker"]["expected"]
    project = tomllib.loads(BACKEND_PYPROJECT_PATH.read_text(encoding="utf-8"))
    marker_entries = project["tool"]["pytest"]["ini_options"]["markers"]
    assert any(str(entry).split(":", maxsplit=1)[0] == marker for entry in marker_entries)

    db_test_files = sorted(
        path
        for path in (REPOSITORY_ROOT / "backend" / "tests" / "db").glob(
            "test_*.py"
        )
        if path.name != "test_environment_expectations.py"
    )
    assert db_test_files, "DB 必須テストが 1 件もない"
    for path in db_test_files:
        text = path.read_text(encoding="utf-8")
        assert f"pytestmark = pytest.mark.{marker}" in text, (
            f"{path}: DB 必須 marker がない"
        )

    conftest = DB_CONFTEST_PATH.read_text(encoding="utf-8")
    assert "def pytest_sessionfinish(" in conftest
    assert "_required_db_execution_error(" in conftest
    assert "_COLLECTED_DB_TESTS," in conftest
    assert "_EXECUTED_DB_TESTS," in conftest
    assert "if not executed:" in conftest
    assert "pytest.ExitCode.TESTS_FAILED" in conftest
    assert "SET ROLE" not in conftest

    backend = _backend_job(_load_workflow(WORKFLOW_PATH.read_text(encoding="utf-8")))
    pytest_commands = [
        command
        for command in _backend_commands(backend)
        if "pytest" in shlex.split(command)
    ]
    assert pytest_commands == [
        expectations["test_execution"]["single_command"]["expected"]
    ]


def test_orm_stack_is_exact_product_dependency() -> None:
    """ORM スタックの厳密製品依存を実ファイルで確認する。"""
    project = tomllib.loads(BACKEND_PYPROJECT_PATH.read_text(encoding="utf-8"))
    lock = tomllib.loads(BACKEND_LOCK_PATH.read_text(encoding="utf-8"))
    assert _orm_stack_dependency_errors(project, lock) == []


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("sqlalchemy-major", "SQLAlchemy の major は 2 が必要"),
        (
            "sqlalchemy-range",
            "sqlalchemy は直接依存で X.Y.Z 形式に厳密固定する",
        ),
        (
            "lock-mismatch",
            "lock の sqlalchemy が pyproject の固定版と一致しない",
        ),
        ("alembic-missing", "alembic の直接依存はちょうど 1 件必要"),
        ("psycopg-extra", "psycopg[binary] は製品依存で厳密固定する"),
    ],
)
def test_orm_stack_dependency_negative_cases_are_red(
    mutation: str,
    expected_error: str,
) -> None:
    """ORM 依存契約の負例 5 種を純関数が拒否する。"""
    project = tomllib.loads(
        """
[project]
dependencies = [
    "psycopg[binary]==3.3.4",
    "sqlalchemy==2.0.52",
    "alembic==1.19.2",
]
"""
    )
    lock: dict[str, Any] = {
        "package": [
            {"name": "psycopg", "version": "3.3.4"},
            {"name": "psycopg-binary", "version": "3.3.4"},
            {"name": "sqlalchemy", "version": "2.0.52"},
            {"name": "alembic", "version": "1.19.2"},
        ]
    }
    project_section = project["project"]
    assert isinstance(project_section, dict)
    dependencies = project_section["dependencies"]
    assert isinstance(dependencies, list)
    lock_packages = lock["package"]
    assert isinstance(lock_packages, list)

    if mutation == "sqlalchemy-major":
        dependencies[1] = "sqlalchemy==3.0.0"
        lock_packages[2] = {"name": "sqlalchemy", "version": "3.0.0"}
    elif mutation == "sqlalchemy-range":
        dependencies[1] = "sqlalchemy>=2,<3"
    elif mutation == "lock-mismatch":
        lock_packages[2] = {"name": "sqlalchemy", "version": "2.0.51"}
    elif mutation == "alembic-missing":
        dependencies.pop(2)
    else:
        dependencies[0] = "psycopg[binary,pool]==3.3.4"

    errors = _orm_stack_dependency_errors(project, lock)

    assert expected_error in errors
