"""付録 E の読み込みと写像を共通変異で検証する。"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).parent / "fixtures/handoff-loader/mutations.json"
sys.path.insert(0, str(ROOT / "backend/src"))
HANDOFF = importlib.import_module("pitchlog.domaincheck.runners.handoff")


def _json(path: str) -> Any:
    """リポジトリにある契約を試験で読む。"""
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _mutated_bytes(scenario: dict[str, Any]) -> bytes:
    """共通 fixture の一箇所だけを変更したバイト列を返す。"""
    if scenario["operation"] == "directCases":
        source = _json(
            "contracts/state-transition/state_transition_contract_v1.json"
        )["cases"]
        return json.dumps(source, ensure_ascii=False).encode()
    raw = (ROOT / scenario["target"]).read_bytes()
    if scenario["operation"] in {"unsafeInteger", "duplicateField", "negativeZero"}:
        assert b'"schemaVersion": 1' in raw
        replacement = {
            "unsafeInteger": b'"schemaVersion": 9007199254740993',
            "duplicateField": b'"schemaVersion": 1, "schemaVersion": 1',
            "negativeZero": b'"schemaVersion": -0',
        }[scenario["operation"]]
        return raw.replace(b'"schemaVersion": 1', replacement, 1)
    document = json.loads(raw)
    tokens = scenario["pointer"].split("/")[1:]
    item = document
    for token in tokens[:-1]:
        item = item[int(token)] if isinstance(item, list) else item[token]
    final = tokens[-1]
    if isinstance(item, list):
        item[int(final)] = scenario["value"]
    else:
        item[final] = scenario["value"]
    return json.dumps(document, ensure_ascii=False).encode()


def test_loads_all_cases_from_both_contracts() -> None:
    """実契約の件数を動的に数え、宣言された写像だけを適用する。"""
    loaded = HANDOFF.load_handoff(ROOT)
    for calculation_id, filename, source_field in (
        (
            "state-transition",
            "contracts/state-transition/state_transition_contract_v1.json",
            "expected",
        ),
        (
            "game-end",
            "contracts/state-transition/game_end_contract_v1.json",
            "decision",
        ),
    ):
        source_cases = _json(filename)["cases"]
        result = loaded.by_calculation[calculation_id]
        assert len(result.cases) == len(source_cases)
        assert [case["caseId"] for case in result.cases] == [
            case["caseId"] for case in source_cases
        ]
        for source, mapped in zip(source_cases, result.cases, strict=True):
            assert set(mapped) == {"caseId", "raw", "normalized", "expected"}
            assert mapped["expected"] == source[source_field]
            assert mapped["raw"] == source["raw"]
            assert mapped["normalized"] == source["normalized"]


@pytest.mark.parametrize(
    "scenario",
    json.loads(FIXTURE.read_text(encoding="utf-8")),
    ids=lambda scenario: scenario["id"],
)
def test_rejects_shared_mutations(scenario: dict[str, Any]) -> None:
    """直読、版差異、未知 field、精度欠落を規則 ID で拒否する。"""
    changed = _mutated_bytes(scenario)

    def reader(path: str) -> bytes:
        """一つの契約ファイルだけを差し替えて読む。"""
        return changed if path == scenario["target"] else (ROOT / path).read_bytes()

    with pytest.raises(HANDOFF.HandoffLoadError) as error:
        HANDOFF.load_handoff(ROOT, reader)
    assert error.value.code == scenario["code"]
