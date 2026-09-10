"""認可 body 由来の MC/DC 写像と独立影響テスト対を静的照合する。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

try:
    from check_authz_catalog import git_blob_digest
    from check_authz_function_bodies import FunctionBodyCheckError
    from check_authz_function_bodies import validate_repository as validate_function_bodies
except ModuleNotFoundError:  # pragma: no cover - モジュールとして読む場合だけ通る。
    from scripts.check_authz_catalog import git_blob_digest
    from scripts.check_authz_function_bodies import FunctionBodyCheckError
    from scripts.check_authz_function_bodies import (
        validate_repository as validate_function_bodies,
    )


ASSET_PATH = PurePosixPath("contracts/authz/mcdc-map.json")
BODY_MANIFEST_PATH = PurePosixPath("contracts/authz/function-bodies/manifest.json")
CLAIM_MUTANT_MAP_PATH = PurePosixPath("contracts/authz/claim-mutant-map.json")
ASSET_KIND = "authz_mcdc_map"
DECISION_RE = re.compile(r"^[ \t]*-- DECISION: ([A-Z0-9_-]+)$")
BLOB_DIGEST_RE = re.compile(r"^[0-9a-f]{40}$")
WORD_AND_RE = re.compile(r"\bAND\b", re.IGNORECASE)
WORD_OR_RE = re.compile(r"\bOR\b", re.IGNORECASE)
LEADING_NOT_RE = re.compile(r"^\(*\s*NOT\b", re.IGNORECASE)
ATOMIC_FORM = "ATOMIC"


class McdcMapCheckError(Exception):
    """検査を開始できない入力不正を表す。"""


@dataclass(frozen=True)
class SourceAsset:
    """写像の入力資産と期待する Git blob digest を表す。"""

    path: PurePosixPath
    blob_digest: str


@dataclass(frozen=True)
class DecisionLocation:
    """body にある判定注記の位置を表す。"""

    path: str
    line: int


@dataclass(frozen=True)
class Condition:
    """判定を構成する個別条件と body 上の根拠を表す。"""

    condition_id: str
    source_terms: tuple[str, ...]


@dataclass(frozen=True)
class IndependencePair:
    """個別条件の独立影響を示す二つの観測を表す。"""

    condition_id: str
    test_ids: tuple[str, str]
    input_a: tuple[bool, ...]
    input_b: tuple[bool, ...]
    observed_results: tuple[bool, bool]


@dataclass(frozen=True)
class Decision:
    """判定 1 件の構造、条件、および MC/DC テスト対を表す。"""

    decision_id: str
    source_path: str
    source_line: int
    expression_end_line: int
    decision_form: str
    conditions: tuple[Condition, ...]
    independence_pairs: tuple[IndependencePair, ...]


@dataclass(frozen=True)
class ValidationResult:
    """静的照合の違反、件数、および body 由来の位置を表す。"""

    findings: tuple[str, ...]
    decision_count: int
    locations: tuple[tuple[str, DecisionLocation], ...]


def _read_bytes(path: Path, label: str) -> bytes:
    """ファイルを生バイト列で読む。"""
    try:
        return path.read_bytes()
    except OSError as error:
        raise McdcMapCheckError(f"{label}を読めない: {path}: {error}") from error


def _read_text(path: Path, label: str) -> str:
    """UTF-8 ファイルを読む。"""
    data = _read_bytes(path, label)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise McdcMapCheckError(f"{label}がUTF-8でない: {path}: {error}") from error


def _read_json(path: Path, label: str) -> object:
    """JSON ファイルを読む。"""
    try:
        return json.loads(_read_text(path, label))
    except json.JSONDecodeError as error:
        raise McdcMapCheckError(f"{label}がJSONでない: {path}: {error}") from error


def _expect_object(value: object, label: str) -> dict[str, object]:
    """値が JSON object であることを検査する。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise McdcMapCheckError(f"{label}は文字列keyのobjectでなければならない")
    return value


def _expect_list(value: object, label: str) -> list[object]:
    """値が JSON array であることを検査する。"""
    if not isinstance(value, list):
        raise McdcMapCheckError(f"{label}はarrayでなければならない")
    return value


def _expect_string(value: object, label: str) -> str:
    """値が空でない文字列であることを検査する。"""
    if not isinstance(value, str) or not value:
        raise McdcMapCheckError(f"{label}は空でない文字列でなければならない")
    return value


def _expect_positive_int(value: object, label: str) -> int:
    """値が 1 始まりの整数であることを検査する。"""
    if type(value) is not int or value < 1:
        raise McdcMapCheckError(f"{label}は正の整数でなければならない")
    return value


def _expect_bool_list(value: object, label: str) -> tuple[bool, ...]:
    """値が bool だけの JSON array であることを検査する。"""
    items = _expect_list(value, label)
    values: list[bool] = []
    for item in items:
        if type(item) is not bool:
            raise McdcMapCheckError(f"{label}はboolだけのarrayでなければならない")
        values.append(item)
    return tuple(values)


def _expect_keys(value: dict[str, object], expected: set[str], label: str) -> None:
    """JSON object の key 集合を完全照合する。"""
    if set(value) != expected:
        raise McdcMapCheckError(f"{label}のkey集合が不正")


def _parse_source_asset(
    raw: object,
    expected_path: PurePosixPath,
    label: str,
) -> SourceAsset:
    """入力資産の固定パスと blob digest を読む。"""
    source = _expect_object(raw, label)
    _expect_keys(source, {"path", "blob_digest"}, label)
    path = PurePosixPath(_expect_string(source["path"], f"{label}.path"))
    if path != expected_path:
        raise McdcMapCheckError(f"{label}.pathが期待する入力資産でない")
    digest = _expect_string(source["blob_digest"], f"{label}.blob_digest")
    if not BLOB_DIGEST_RE.fullmatch(digest):
        raise McdcMapCheckError(f"{label}.blob_digestがGit blob SHA-1でない")
    return SourceAsset(path=path, blob_digest=digest)


def _parse_condition(raw: object, label: str) -> Condition:
    """個別条件と body 上の照合語を読む。"""
    condition = _expect_object(raw, label)
    _expect_keys(condition, {"condition_id", "source_terms"}, label)
    condition_id = _expect_string(condition["condition_id"], f"{label}.condition_id")
    terms = tuple(
        _expect_string(term, f"{label}.source_terms[{index}]")
        for index, term in enumerate(
            _expect_list(condition["source_terms"], f"{label}.source_terms")
        )
    )
    if not terms:
        raise McdcMapCheckError(f"{label}.source_termsが空")
    return Condition(condition_id=condition_id, source_terms=terms)


def _parse_pair(raw: object, label: str) -> IndependencePair:
    """独立影響テスト対を読む。"""
    pair = _expect_object(raw, label)
    _expect_keys(
        pair,
        {
            "condition_id",
            "test_ids",
            "input_a",
            "input_b",
            "observed_results",
        },
        label,
    )
    test_ids = tuple(
        _expect_string(item, f"{label}.test_ids[{index}]")
        for index, item in enumerate(_expect_list(pair["test_ids"], f"{label}.test_ids"))
    )
    observed_results = _expect_bool_list(
        pair["observed_results"], f"{label}.observed_results"
    )
    if len(test_ids) != 2 or len(observed_results) != 2:
        raise McdcMapCheckError(f"{label}は2件のtest IDと観測結果を持たなければならない")
    return IndependencePair(
        condition_id=_expect_string(pair["condition_id"], f"{label}.condition_id"),
        test_ids=(test_ids[0], test_ids[1]),
        input_a=_expect_bool_list(pair["input_a"], f"{label}.input_a"),
        input_b=_expect_bool_list(pair["input_b"], f"{label}.input_b"),
        observed_results=(observed_results[0], observed_results[1]),
    )


def _parse_decision(raw: object, label: str) -> Decision:
    """判定 1 件を厳密に読む。"""
    decision = _expect_object(raw, label)
    _expect_keys(
        decision,
        {
            "decision_id",
            "source",
            "decision_form",
            "conditions",
            "independence_pairs",
        },
        label,
    )
    source = _expect_object(decision["source"], f"{label}.source")
    _expect_keys(source, {"path", "line", "expression_end_line"}, f"{label}.source")
    conditions = tuple(
        _parse_condition(item, f"{label}.conditions[{index}]")
        for index, item in enumerate(
            _expect_list(decision["conditions"], f"{label}.conditions")
        )
    )
    pairs = tuple(
        _parse_pair(item, f"{label}.independence_pairs[{index}]")
        for index, item in enumerate(
            _expect_list(
                decision["independence_pairs"], f"{label}.independence_pairs"
            )
        )
    )
    if not conditions or not pairs:
        raise McdcMapCheckError(f"{label}は個別条件とテスト対を持たなければならない")
    return Decision(
        decision_id=_expect_string(decision["decision_id"], f"{label}.decision_id"),
        source_path=_expect_string(source["path"], f"{label}.source.path"),
        source_line=_expect_positive_int(source["line"], f"{label}.source.line"),
        expression_end_line=_expect_positive_int(
            source["expression_end_line"], f"{label}.source.expression_end_line"
        ),
        decision_form=_expect_string(
            decision["decision_form"], f"{label}.decision_form"
        ),
        conditions=conditions,
        independence_pairs=pairs,
    )


def _parse_asset(
    raw: object,
) -> tuple[SourceAsset, SourceAsset, tuple[Decision, ...]]:
    """MC/DC 写像の全体構造を厳密に読む。"""
    asset = _expect_object(raw, "mcdc-map")
    _expect_keys(
        asset,
        {"schema_version", "asset_kind", "sources", "decisions"},
        "mcdc-map",
    )
    if asset["schema_version"] != 1 or asset["asset_kind"] != ASSET_KIND:
        raise McdcMapCheckError("mcdc-mapのschema_versionまたはasset_kindが不正")
    sources = _expect_object(asset["sources"], "mcdc-map.sources")
    _expect_keys(sources, {"body_manifest", "claim_mutant_map"}, "mcdc-map.sources")
    body_manifest = _parse_source_asset(
        sources["body_manifest"], BODY_MANIFEST_PATH, "mcdc-map.sources.body_manifest"
    )
    claim_mutant_map = _parse_source_asset(
        sources["claim_mutant_map"],
        CLAIM_MUTANT_MAP_PATH,
        "mcdc-map.sources.claim_mutant_map",
    )
    decisions = tuple(
        _parse_decision(item, f"mcdc-map.decisions[{index}]")
        for index, item in enumerate(_expect_list(asset["decisions"], "mcdc-map.decisions"))
    )
    return body_manifest, claim_mutant_map, decisions


def _manifest_body_paths(raw: object) -> tuple[str, ...]:
    """body manifest から SQL body のパスを導出する。"""
    manifest = _expect_object(raw, "body manifest")
    entries = _expect_list(manifest.get("entries"), "body manifest.entries")
    paths: list[str] = []
    for index, raw_entry in enumerate(entries):
        entry = _expect_object(raw_entry, f"body manifest.entries[{index}]")
        path = _expect_string(entry.get("path"), f"body manifest.entries[{index}].path")
        if path.endswith(".sql"):
            paths.append(path)
    return tuple(paths)


def _extract_decision_locations(
    root: Path,
    body_paths: Sequence[str],
) -> tuple[dict[str, DecisionLocation], list[str]]:
    """body の注記を行単位で抽出し、ID と位置を返す。"""
    locations: dict[str, DecisionLocation] = {}
    findings: list[str] = []
    for path_text in sorted(body_paths):
        text = _read_text(root / path_text, path_text)
        for line_number, line in enumerate(text.splitlines(), start=1):
            if "-- DECISION:" not in line:
                continue
            match = DECISION_RE.fullmatch(line)
            if match is None or line.count("-- DECISION:") != 1:
                findings.append(f"{path_text}:{line_number}: DECISION注記の構文が不正")
                continue
            decision_id = match.group(1)
            if decision_id in locations:
                previous = locations[decision_id]
                findings.append(
                    f"DECISION IDが重複: {decision_id}: "
                    f"{previous.path}:{previous.line}, {path_text}:{line_number}"
                )
                continue
            locations[decision_id] = DecisionLocation(path=path_text, line=line_number)
    return locations, findings


def _normalize_sql_fragment(lines: Sequence[str]) -> str:
    """注記と空白差を除いて構造照合用の SQL 断片へ正規化する。"""
    code = " ".join(
        line.split("--", maxsplit=1)[0]
        for line in lines
        if not line.lstrip().startswith("--")
    )
    return " ".join(code.split())


def _is_table_driven_case(fragment: str, body_text: str) -> bool:
    """判別表の真偽列で分岐する CASE 相当の式かを構文から判定する。"""
    branch_match = re.search(
        r"^\(\s*NOT\s+([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\s+"
        r"OR\s+EXISTS\s*\(",
        fragment,
        re.IGNORECASE,
    )
    if branch_match is None:
        return False
    alias, flag_column = branch_match.groups()
    matrix_match = re.search(
        rf"\bWITH\s+{re.escape(alias)}\s*\(\s*"
        rf"([a-z_][a-z0-9_]*)\s*,\s*{re.escape(flag_column)}\s*\)\s*"
        rf"AS\s*\(\s*VALUES\s*(.*?)\)\s*,\s*[a-z_][a-z0-9_]*\s+AS\s*\(",
        body_text,
        re.IGNORECASE | re.DOTALL,
    )
    if matrix_match is None:
        return False
    discriminator_column, rows = matrix_match.groups()
    discriminator_values = set(re.findall(r"'([^']+)'\s*::", rows))
    truth_values = set(re.findall(r"\b(TRUE|FALSE)\b", rows, re.IGNORECASE))
    return (
        discriminator_column.lower() != flag_column.lower()
        and len(discriminator_values) >= 2
        and {value.upper() for value in truth_values} == {"TRUE", "FALSE"}
    )


def _derive_decision_form(fragment: str, body_text: str) -> str:
    """body の式構造から判定形を導出する。"""
    if _is_table_driven_case(fragment, body_text):
        return "CASE"
    if LEADING_NOT_RE.search(fragment):
        return "NOT"
    if WORD_OR_RE.search(fragment):
        return "OR"
    if WORD_AND_RE.search(fragment):
        return "AND"
    return ATOMIC_FORM


def _required_decision_forms(raw: object) -> frozenset[str]:
    """変異資産から MC/DC が要求する複合判定形の閉じた語彙を読む。"""
    claim_map = _expect_object(raw, "claim-mutant-map")
    values = _expect_list(
        claim_map.get("mcdc_decision_forms"), "claim-mutant-map.mcdc_decision_forms"
    )
    forms = tuple(
        _expect_string(value, f"claim-mutant-map.mcdc_decision_forms[{index}]")
        for index, value in enumerate(values)
    )
    if len(set(forms)) != len(forms) or not forms:
        raise McdcMapCheckError("mcdc_decision_formsが空または重複している")
    return frozenset(forms)


def _evaluate(form: str, values: Sequence[bool]) -> bool:
    """判定形と入力ベクタから判定結果を計算する。"""
    if form == ATOMIC_FORM:
        if len(values) != 1:
            raise McdcMapCheckError("ATOMIC判定の条件数が1でない")
        return values[0]
    if form == "AND":
        if len(values) < 2:
            raise McdcMapCheckError("AND判定の条件数が2未満")
        return all(values)
    if form == "OR":
        if len(values) < 2:
            raise McdcMapCheckError("OR判定の条件数が2未満")
        return any(values)
    if form == "NOT":
        if len(values) != 1:
            raise McdcMapCheckError("NOT判定の条件数が1でない")
        return not values[0]
    if form == "CASE":
        if len(values) != 2:
            raise McdcMapCheckError("CASE判定の条件数が2でない")
        requirement_applies, required_branch_allows = values
        return not requirement_applies or required_branch_allows
    raise McdcMapCheckError(f"未知の判定形: {form}")


def _validate_pair(
    decision: Decision,
    pair: IndependencePair,
    condition_ids: tuple[str, ...],
    label: str,
) -> list[str]:
    """一つの独立影響テスト対の入力差分と観測結果を検査する。"""
    findings: list[str] = []
    if pair.condition_id not in condition_ids:
        findings.append(f"{label}: 対象条件がconditionsに存在しない")
        return findings
    if pair.test_ids[0] == pair.test_ids[1]:
        findings.append(f"{label}: テスト対の2つのIDが同一")
    if len(pair.input_a) != len(condition_ids) or len(pair.input_b) != len(condition_ids):
        findings.append(f"{label}: 入力ベクタ長が条件数と不一致")
        return findings
    target_index = condition_ids.index(pair.condition_id)
    changed = {
        index
        for index, (value_a, value_b) in enumerate(zip(pair.input_a, pair.input_b))
        if value_a != value_b
    }
    if target_index not in changed:
        findings.append(f"{label}: 対象条件が反転していない")
    if changed - {target_index}:
        findings.append(f"{label}: 対象条件以外の入力も変化している")
    if pair.observed_results[0] == pair.observed_results[1]:
        findings.append(f"{label}: 実測した判定結果が反転していない")
    expected_results = (
        _evaluate(decision.decision_form, pair.input_a),
        _evaluate(decision.decision_form, pair.input_b),
    )
    if pair.observed_results != expected_results:
        findings.append(f"{label}: 実測した判定結果が入力と判定形に一致しない")
    return findings


def _format_ids(values: Collection[str]) -> str:
    """ID 集合を安定順の表示文字列にする。"""
    return ", ".join(sorted(values)) or "(なし)"


def validate_repository(root: Path) -> ValidationResult:
    """リポジトリの MC/DC 写像、body、入力資産を静的照合する。"""
    root = root.resolve()
    if not root.is_dir():
        raise McdcMapCheckError(f"リポジトリルートがない: {root}")
    raw_asset = _read_json(root / ASSET_PATH, "mcdc-map")
    body_manifest_source, claim_map_source, decisions = _parse_asset(raw_asset)
    body_manifest_bytes = _read_bytes(root / body_manifest_source.path, "body manifest")
    claim_map_bytes = _read_bytes(root / claim_map_source.path, "claim-mutant-map")
    body_manifest_raw = _read_json(root / body_manifest_source.path, "body manifest")
    claim_map_raw = _read_json(root / claim_map_source.path, "claim-mutant-map")
    findings: list[str] = []

    if git_blob_digest(body_manifest_bytes) != body_manifest_source.blob_digest:
        findings.append("body manifestのdigest連鎖が不一致")
    if git_blob_digest(claim_map_bytes) != claim_map_source.blob_digest:
        findings.append("claim-mutant-mapのdigest連鎖が不一致")
    try:
        body_findings = validate_function_bodies(root)
    except FunctionBodyCheckError as error:
        raise McdcMapCheckError(f"body manifest照合を開始できない: {error}") from error
    findings.extend(f"body manifest照合: {finding}" for finding in body_findings)

    body_paths = _manifest_body_paths(body_manifest_raw)
    locations, location_findings = _extract_decision_locations(root, body_paths)
    findings.extend(location_findings)
    decision_counts = Counter(decision.decision_id for decision in decisions)
    for decision_id, count in sorted(decision_counts.items()):
        if count > 1:
            findings.append(f"mcdc-mapのdecision_idが重複: {decision_id}")
    mapped_ids = set(decision_counts)
    body_ids = set(locations)
    missing_ids = body_ids - mapped_ids
    extra_ids = mapped_ids - body_ids
    if missing_ids or extra_ids:
        findings.append(
            "判定ID集合がbody由来の集合とexact-set不一致: "
            f"不足={_format_ids(missing_ids)}; 余分={_format_ids(extra_ids)}"
        )

    required_forms = _required_decision_forms(claim_map_raw)
    allowed_body_paths = set(body_paths)
    declared_forms: set[str] = set()
    all_test_ids: list[str] = []
    for index, decision in enumerate(decisions):
        label = f"mcdc-map.decisions[{index}]({decision.decision_id})"
        declared_forms.add(decision.decision_form)
        location = locations.get(decision.decision_id)
        if location is not None and (
            decision.source_path != location.path or decision.source_line != location.line
        ):
            findings.append(f"{label}: source位置がbody注記と不一致")
        if decision.source_path not in allowed_body_paths:
            findings.append(f"{label}: source.pathがbody manifestの対象外")
            continue
        body_path = root / decision.source_path
        if not body_path.is_file():
            findings.append(f"{label}: source.pathが存在しない")
            continue
        body_lines = _read_text(body_path, decision.source_path).splitlines()
        if (
            decision.expression_end_line <= decision.source_line
            or decision.expression_end_line > len(body_lines)
        ):
            findings.append(f"{label}: expression_end_lineが不正")
            continue
        fragment = _normalize_sql_fragment(
            body_lines[decision.source_line : decision.expression_end_line]
        )
        derived_form = _derive_decision_form(fragment, "\n".join(body_lines))
        if decision.decision_form != derived_form:
            findings.append(
                f"{label}: 判定形がbody構造由来と不一致: "
                f"宣言={decision.decision_form}; 導出={derived_form}"
            )
        if derived_form != ATOMIC_FORM and derived_form not in required_forms:
            findings.append(f"{label}: body由来の複合判定形が閉じた語彙にない: {derived_form}")

        condition_ids = tuple(condition.condition_id for condition in decision.conditions)
        duplicate_conditions = {
            condition_id
            for condition_id, count in Counter(condition_ids).items()
            if count > 1
        }
        if duplicate_conditions:
            findings.append(
                f"{label}: condition_idが重複: {_format_ids(duplicate_conditions)}"
            )
        for condition in decision.conditions:
            for term in condition.source_terms:
                normalized_term = " ".join(term.split())
                if normalized_term not in fragment:
                    findings.append(
                        f"{label}: {condition.condition_id}のsource termが式spanにない: "
                        f"{normalized_term}"
                    )
        pair_counts = Counter(pair.condition_id for pair in decision.independence_pairs)
        missing_pairs = set(condition_ids) - set(pair_counts)
        extra_pairs = set(pair_counts) - set(condition_ids)
        duplicate_pairs = {
            condition_id for condition_id, count in pair_counts.items() if count > 1
        }
        if missing_pairs or extra_pairs or duplicate_pairs:
            findings.append(
                f"{label}: 条件とテスト対がexact-set不一致: "
                f"不足={_format_ids(missing_pairs)}; 余分={_format_ids(extra_pairs)}; "
                f"重複={_format_ids(duplicate_pairs)}"
            )
        for pair_index, pair in enumerate(decision.independence_pairs):
            pair_label = f"{label}.independence_pairs[{pair_index}]"
            findings.extend(_validate_pair(decision, pair, condition_ids, pair_label))
            all_test_ids.extend(pair.test_ids)

    missing_forms = required_forms - declared_forms
    if missing_forms:
        findings.append(
            "mcdc_decision_formsの判定形を覆っていない: " f"{_format_ids(missing_forms)}"
        )
    duplicate_test_ids = {
        test_id for test_id, count in Counter(all_test_ids).items() if count > 1
    }
    if duplicate_test_ids:
        findings.append(f"テストIDが写像全体で重複: {_format_ids(duplicate_test_ids)}")

    ordered_locations = tuple(
        sorted(locations.items(), key=lambda item: (item[1].path, item[1].line))
    )
    return ValidationResult(
        findings=tuple(findings),
        decision_count=len(locations),
        locations=ordered_locations,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解釈する。"""
    parser = argparse.ArgumentParser(description="認可 MC/DC 写像を静的照合する")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="リポジトリルート")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """静的照合を実行して終了コードを返す。"""
    try:
        args = parse_args(argv)
        result = validate_repository(args.root)
    except McdcMapCheckError as error:
        print(f"authz-mcdc-map: 入力不正: {error}", file=sys.stderr)
        return 2
    if result.findings:
        for finding in result.findings:
            print(f"authz-mcdc-map: 違反: {finding}", file=sys.stderr)
        return 1
    print(f"authz-mcdc-map: OK ({result.decision_count} decisions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
