"""段階起動のDB API許可を既登録11関数の最小集合に限定する。"""

import ast
from pathlib import Path

from scripts import check_tenant_boundary_bypass as checker

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/src/pitchlog/db/stage_a_startup.py"


def test_stage_a_allowlist_is_exact() -> None:
    """関数・APIの集合に余分な許可がないことを確認する。"""
    contract = checker.load_contract(ROOT)
    actual = {
        item.symbol.rsplit(".", 1)[-1]: item.allowed_api_ids
        for item in contract.allowed_symbols
        if item.symbol.startswith("pitchlog.db.stage_a_startup.")
    }
    psycopg_sql = frozenset(
        {"PSYCOPG_CONNECT", "PSYCOPG_CONNECTION_CURSOR", "PSYCOPG_CURSOR_EXECUTE"}
    )
    assert actual == {
        "_require_same_database": psycopg_sql,
        "_require_s0": psycopg_sql,
        "_apply_placement": frozenset({"SQLA_CREATE_ENGINE", "SQLA_ENGINE_BEGIN"}),
        "_apply_epoch": frozenset({"SQLA_CREATE_ENGINE", "SQLA_ENGINE_BEGIN"}),
        "_apply_initial_storage": frozenset({"SQLA_CREATE_ENGINE", "SQLA_ENGINE_BEGIN"}),
        "_require_initial_state": psycopg_sql,
        "_require_s3": psycopg_sql,
        "_require_epoch_state": psycopg_sql,
        "_require_placed_state": psycopg_sql,
        "resume_stage_a_after_placement": psycopg_sql,
        "advance_stage_a_from_s0": frozenset({"PSYCOPG_CONNECT"}),
    }


def test_stage_a_unlisted_function_is_rejected() -> None:
    """同じファイル内の未登録関数へのDB API移動を拒否する。"""
    contract = checker.load_contract(ROOT)
    source = SOURCE.read_text(encoding="utf-8")
    mutated = source + (
        "\n\ndef _unlisted_startup(owner_dsn: str) -> None:\n"
        "    psycopg.connect(owner_dsn)\n"
    )
    lines = frozenset(range(source.count("\n") + 1, mutated.count("\n") + 2))
    violations = checker.scan_source(
        mutated,
        path="pitchlog/db/stage_a_startup.py",
        contract=contract,
        changed_lines=lines,
    )
    assert any(item.code == "TB005" and item.symbol == "psycopg.connect" for item in violations)


def test_stage_a_unlisted_api_and_signature_are_rejected() -> None:
    """登録関数でも追加APIと署名の変化は拒否する。"""
    contract = checker.load_contract(ROOT)
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "_apply_placement"
    )
    assert node.end_lineno is not None
    lines = frozenset(range(node.lineno, node.end_lineno + 1))
    mutated = source.replace(
        "engine = create_engine(_owner_url(owner_dsn))",
        "engine = create_engine(_owner_url(owner_dsn))\n    psycopg.connect(owner_dsn)",
        1,
    )
    violations = checker.scan_source(
        mutated,
        path="pitchlog/db/stage_a_startup.py",
        contract=contract,
        changed_lines=lines,
    )
    assert any(item.code == "TB005" and item.symbol == "psycopg.connect" for item in violations)
    renamed = source.replace(
        "def _apply_placement(owner_dsn: str)",
        "def _apply_placement(owner_dsn: str, extra: str)",
        1,
    )
    violations = checker.scan_source(
        renamed,
        path="pitchlog/db/stage_a_startup.py",
        contract=contract,
        changed_lines=frozenset({node.lineno}),
    )
    assert any(item.code == "TB005" and "_apply_placement" in item.symbol for item in violations)


def test_stage_a_permission_does_not_extend_to_another_module() -> None:
    """同名関数を別モジュールへ移してもDB APIを許可しない。"""
    contract = checker.load_contract(ROOT)
    source = (
        "import psycopg\n\n"
        "def _require_s0(owner_dsn: str) -> None:\n"
        "    psycopg.connect(owner_dsn)\n"
    )
    violations = checker.scan_source(
        source,
        path="pitchlog/db/other_startup.py",
        contract=contract,
        changed_lines=frozenset(range(1, 5)),
    )
    assert any(item.code == "TB005" and item.symbol == "psycopg.connect" for item in violations)


def test_stage_a_epoch_functions_reject_extra_apis() -> None:
    """追加したepochの2許可も、各関数の登録外APIへ拡張しない。"""
    contract = checker.load_contract(ROOT)
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for name, extra in (
        ("_apply_epoch", "    psycopg.connect(owner_dsn)\n"),
        ("_require_epoch_state", "    create_engine(_owner_url(applicator_dsn))\n"),
    ):
        node = next(
            item for item in tree.body
            if isinstance(item, ast.FunctionDef) and item.name == name
        )
        assert node.end_lineno is not None
        lines = source.splitlines(keepends=True)
        lines.insert(node.end_lineno, extra)
        violations = checker.scan_source(
            "".join(lines),
            path="pitchlog/db/stage_a_startup.py",
            contract=contract,
            changed_lines=frozenset({node.end_lineno + 1}),
        )
        assert any(item.code == "TB005" for item in violations), name
