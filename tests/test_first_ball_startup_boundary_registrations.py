"""初球製品DB起動の既3helperだけの有限登録と拒否を検証する。"""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import check_tenant_boundary_bypass as checker

ROOT = Path(__file__).resolve().parents[1]
PATH = "pitchlog/db/stage_a_startup.py"
_REGISTRATIONS = (
    (
        "_check_writer_storage",
        "_check_writer_storage(connection: Any, revision: str) -> None",
        frozenset({"PSYCOPG_CONNECTION_CURSOR", "PSYCOPG_CURSOR_EXECUTE"}),
    ),
    (
        "_apply_writer_storage",
        "_apply_writer_storage(owner_dsn: str) -> None",
        frozenset({"SQLA_CREATE_ENGINE", "SQLA_ENGINE_BEGIN",
                   "PSYCOPG_CONNECTION_CURSOR", "PSYCOPG_CURSOR_EXECUTE"}),
    ),
    (
        "_require_writer_state",
        "_require_writer_state(applicator_dsn: str) -> None",
        frozenset({"PSYCOPG_CONNECT", "PSYCOPG_CONNECTION_CURSOR", "PSYCOPG_CURSOR_EXECUTE"}),
    ),
)


@pytest.mark.parametrize(("name", "signature", "apis"), _REGISTRATIONS)
def test_first_ball_startup_registration_is_exact_and_required(
    name: str, signature: str, apis: frozenset[str],
) -> None:
    """実3scopeだけの所見を解消し、他scopeの既所見を隠さない。"""
    contract = checker.load_contract(ROOT)
    symbol = "pitchlog.db.stage_a_startup." + name
    selected = [row for row in contract.allowed_symbols if row.symbol == symbol]
    assert len(selected) == 1
    registration = selected[0]
    assert registration.signature == signature
    assert registration.allowed_api_ids == apis
    assert registration.fixture == (
        "tests/fixtures/tenant_boundary/positive/pitchlog/db/startup_allowed/"
        f"{name}.py"
    )
    assert (ROOT / registration.fixture).is_file()
    source = (ROOT / "backend/src" / PATH).read_text(encoding="utf-8")
    actual = checker.scan_source(source, path=PATH, contract=contract)
    assert not [v for v in actual if v.scope == symbol]
    for replacement in (None, replace(registration, signature=signature + "_invalid")):
        rows = tuple(row for row in contract.allowed_symbols if row.symbol != symbol)
        if replacement is not None:
            rows = (*rows, replacement)
        violations = checker.scan_source(
            source, path=PATH, contract=replace(contract, allowed_symbols=rows),
        )
        assert any(v.code == "TB005" and v.scope == symbol for v in violations)
        signature_findings = [
            v for v in violations if v.code == "TB005" and v.symbol == symbol
            and v.scope == "pitchlog.db.stage_a_startup.<module>"
        ]
        assert len(signature_findings) == (replacement is not None)
        assert [v for v in violations if v.scope != symbol and v not in signature_findings] == [
            v for v in actual if v.scope != symbol
        ]


@pytest.mark.parametrize(("name", "signature", "apis"), _REGISTRATIONS)
@pytest.mark.parametrize("mutation", ["extra-api", "different-scope", "different-module"])
def test_first_ball_startup_registration_does_not_extend_scope_or_apis(
    name: str, signature: str, apis: frozenset[str], mutation: str,
) -> None:
    """同module別関数/別module移植と未登録executemanyを拒否する。"""
    contract = checker.load_contract(ROOT)
    symbol = "pitchlog.db.stage_a_startup." + name
    source = (ROOT / "backend/src" / PATH).read_text(encoding="utf-8")
    tree = ast.parse(source)
    target = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    if mutation == "different-scope":
        target.name = "_unlisted_first_ball_startup"
    elif mutation == "extra-api":
        target.body.append(ast.parse('cursor.executemany("SELECT 1", [])').body[0])
    path = "pitchlog/db/copied_startup.py" if mutation == "different-module" else PATH
    violations = checker.scan_source(ast.unparse(tree), path=path, contract=contract)
    expected_scope = (
        "pitchlog.db.stage_a_startup._unlisted_first_ball_startup"
        if mutation == "different-scope"
        else "pitchlog.db.copied_startup." + name
        if mutation == "different-module"
        else symbol
    )
    if mutation == "different-module":
        expected_api = {
            "_check_writer_storage": "psycopg.Cursor.execute",
            "_apply_writer_storage": "sqlalchemy.create_engine",
            "_require_writer_state": "psycopg.connect",
        }[name]
        assert any(
            v.code == "TB005" and v.scope == expected_scope
            and expected_api in v.symbol.split("|") for v in violations
        )
    else:
        assert any(v.code == "TB005" and v.scope == expected_scope for v in violations)


@pytest.mark.parametrize(("name", "signature", "apis"), _REGISTRATIONS)
def test_first_ball_startup_missing_fixture_is_rejected(
    name: str, signature: str, apis: frozenset[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """実fileを変更せず欠落列挙を模擬し、既exact-set検査の拒否を確認する。"""
    original = Path.rglob
    missing = ROOT / (
        "tests/fixtures/tenant_boundary/positive/pitchlog/db/startup_allowed/"
        f"{name}.py"
    )

    def without_target(path: Path, pattern: str):
        yield from (candidate for candidate in original(path, pattern) if candidate != missing)

    monkeypatch.setattr(Path, "rglob", without_target)
    with pytest.raises(checker.ContractError, match="正例 fixture.*exact-set"):
        checker.load_contract(ROOT)


@pytest.mark.parametrize(("name", "signature", "apis"), _REGISTRATIONS)
def test_first_ball_startup_unknown_api_declaration_is_rejected(
    name: str, signature: str, apis: frozenset[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """正式JSONを変更せず未知APIの自己申告を既閉loaderで拒否する。"""
    original = checker._read_json

    def with_unknown_api(path: Path):
        value, raw = original(path)
        if path == ROOT / checker.DEFAULT_ALLOWLIST:
            row = next(row for row in value["allowed_symbols"]
                       if row["symbol"] == "pitchlog.db.stage_a_startup." + name)
            row["allowed_api_ids"].append("UNREGISTERED_FIRST_BALL_API")
        return value, raw

    monkeypatch.setattr(checker, "_read_json", with_unknown_api)
    with pytest.raises(checker.ContractError, match="inventory 外 API"):
        checker.load_contract(ROOT)


def test_first_ball_startup_positive_fixtures_and_all_reject_mutation(tmp_path: Path) -> None:
    """新3正例の実本文を検査し、DB API全拒否変異では各fixtureを赤にする。"""
    contract = checker.load_contract(ROOT)
    positive_root = tmp_path / "positive"
    for name, _, _ in _REGISTRATIONS:
        relative = Path("pitchlog/db/startup_allowed") / f"{name}.py"
        destination = positive_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = ROOT / "tests/fixtures/tenant_boundary/positive" / relative
        destination.write_bytes(source.read_bytes())
    assert checker.scan_directory(positive_root, contract=contract) == []
    rejected = checker.scan_directory(positive_root, contract=contract, reject_all_db_calls=True)
    assert {v.path for v in rejected if v.code == "TB900"} == {
        f"pitchlog/db/startup_allowed/{name}.py" for name, _, _ in _REGISTRATIONS
    }
