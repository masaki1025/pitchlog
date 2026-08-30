"""認可要件主張母集合の全数採取と閉じた分類を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_authz_catalog.py"
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "authz_claims"


def _load_checker() -> Any:
    """テスト対象を sys.path の変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location("check_authz_catalog_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def _make_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    shutil.copytree(FIXTURE_ROOT, root)
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
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "total=1062 auth_claim=184 out_of_scope=878" in result.stdout


def test_fixture_has_a_valid_multi_layer_claim(tmp_path: Path) -> None:
    root = _make_repository(tmp_path)
    catalog = _read_catalog(root)
    claim = _auth_claim(catalog)

    assert [decision["location"] for decision in claim["decidable_at"]] == ["db", "http"]
    assert all(decision["test_owner"]["status"] == "planned" for decision in claim["decidable_at"])
    assert _run_cli(root).returncode == 0


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
    """184主張と5規則の全920通りで分類決定を守る。"""
    catalog, lock = _repository_catalog_and_lock()
    auth_claims = [
        claim for claim in catalog["claims"] if claim["classification"] == "auth_claim"
    ]
    out_rule_ids = sorted(
        rule_id
        for rule_id, rule in catalog["classification_rules"].items()
        if rule["classification"] == "out_of_scope"
    )
    escaped: list[tuple[str, str]] = []
    attempts = 0
    for claim in auth_claims:
        original = copy.deepcopy(claim)
        for out_rule_id in out_rule_ids:
            claim.clear()
            claim.update(copy.deepcopy(original))
            claim["classification"] = "out_of_scope"
            claim["classification_rule_id"] = out_rule_id
            del claim["layer"]
            del claim["decidable_at"]
            _refresh_decision_digest(claim)
            differences = checker.decision_lock_differences(catalog, lock)
            if not any(
                difference.startswith(f"{claim['source_id']}:")
                for difference in differences
            ):
                escaped.append((claim["source_id"], out_rule_id))
            attempts += 1
        claim.clear()
        claim.update(original)

    assert len(auth_claims) == 184
    assert len(out_rule_ids) == 5
    assert attempts == 184 * 5 == 920
    assert escaped == []


def test_all_decidable_locations_removed_one_at_a_time_are_red() -> None:
    """db/http/cache を含む全主張の全378ロケーションを守る。"""
    catalog, lock = _repository_catalog_and_lock()
    escaped: list[tuple[str, str]] = []
    attempts = Counter[str]()
    for claim in catalog["claims"]:
        if claim["classification"] != "auth_claim":
            continue
        original = copy.deepcopy(claim)
        for decision in original["decidable_at"]:
            location = decision["location"]
            claim.clear()
            claim.update(copy.deepcopy(original))
            claim["decidable_at"] = [
                item for item in claim["decidable_at"] if item["location"] != location
            ]
            _refresh_decision_digest(claim)
            differences = checker.decision_lock_differences(catalog, lock)
            if not any(
                difference.startswith(f"{claim['source_id']}:")
                for difference in differences
            ):
                escaped.append((claim["source_id"], location))
            attempts[location] += 1
        claim.clear()
        claim.update(original)

    assert attempts == Counter({"http": 184, "db": 177, "cache": 17})
    assert sum(attempts.values()) == 378
    assert escaped == []


def test_all_auth_claim_layers_changed_to_every_other_layer_are_red() -> None:
    """184主張の layer を他の4値へ変える全736通りを守る。"""
    catalog, lock = _repository_catalog_and_lock()
    layer_ids = catalog["layer_ids"]
    auth_claims = [
        claim for claim in catalog["claims"] if claim["classification"] == "auth_claim"
    ]
    escaped: list[tuple[str, str]] = []
    attempts = 0
    for claim in auth_claims:
        original = copy.deepcopy(claim)
        for layer_id in layer_ids:
            if layer_id == original["layer"]:
                continue
            claim["layer"] = layer_id
            _refresh_decision_digest(claim)
            differences = checker.decision_lock_differences(catalog, lock)
            if not any(
                difference.startswith(f"{claim['source_id']}:")
                for difference in differences
            ):
                escaped.append((claim["source_id"], layer_id))
            claim.clear()
            claim.update(copy.deepcopy(original))
            attempts += 1

    assert len(auth_claims) == 184
    assert len(layer_ids) == 5
    assert attempts == 184 * 4 == 736
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

    assert len(out_claims) == 878
    assert attempts == 878
    assert escaped == []


def test_all_basis_rules_changed_one_at_a_time_are_red() -> None:
    """全378 location の basis_rule_id も決定の一部として守る。"""
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
    escaped: list[tuple[str, str]] = []
    attempts = 0
    for claim in catalog["claims"]:
        if claim["classification"] != "auth_claim":
            continue
        original = copy.deepcopy(claim)
        for index, decision in enumerate(original["decidable_at"]):
            alternatives = [
                basis_id
                for basis_id in basis_by_location[decision["location"]]
                if basis_id != decision["basis_rule_id"]
            ]
            assert alternatives
            claim["decidable_at"][index]["basis_rule_id"] = alternatives[0]
            _refresh_decision_digest(claim)
            differences = checker.decision_lock_differences(catalog, lock)
            if not any(
                difference.startswith(f"{claim['source_id']}:")
                for difference in differences
            ):
                escaped.append((claim["source_id"], decision["location"]))
            claim.clear()
            claim.update(copy.deepcopy(original))
            attempts += 1

    assert attempts == 177 + 184 + 17 == 378
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
