"""常駐 Node と vm adapter の合成出力を同じ正規形で照合する。"""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).parent / "fixtures/artifact-adapter"
ARTIFACT = FIXTURE / "pitchlog-domain.js"
DECLARATION = FIXTURE / "pitchlog-domain.json"
VECTOR = FIXTURE / "vector.json"
VM_RUNNER = FIXTURE / "vm-runner.mjs"
CANONICAL = FIXTURE / "canonical-json.mjs"
sys.path.insert(0, str(ROOT / "backend/src"))
ADAPTER = importlib.import_module("pitchlog.domaincheck.runners.artifact_adapter")
HOST = importlib.import_module("pitchlog.domainrt.host")


def _node_calls() -> list[dict[str, str]]:
    """検証済み常駐 Node の adapter から生の送受信を集める。"""
    vector = json.loads(VECTOR.read_text(encoding="utf-8"))
    digest = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
    with HOST.NodeDomainHost(ARTIFACT, DECLARATION) as host:
        adapter = ADAPTER.NodeArtifactAdapter(
            host, vector["generatedId"], f"sha256:{digest}"
        )
        for item in vector["cases"]:
            normalized = adapter.normalize(item["raw"])
            adapter.execute(item["caseId"], normalized)
    return [
        {
            "operation": item.operation,
            "requestJson": item.request_json,
            "responseJson": item.response_json,
        }
        for item in adapter.calls
    ]


def _vm_calls(artifact: Path) -> list[dict[str, str]]:
    """Vitest が使う vm adapter を Node から呼んで生の送受信を返す。"""
    completed = subprocess.run(
        ["node", str(VM_RUNNER), str(artifact), str(VECTOR)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return json.loads(completed.stdout)


def _canonical_bytes(calls: list[dict[str, str]]) -> bytes:
    """唯一の JS 正規化器で要求・応答の JSON を UTF-8 にする。"""
    values: list[dict[str, Any]] = [
        {
            "operation": item["operation"],
            "request": json.loads(item["requestJson"]),
            "response": json.loads(item["responseJson"]),
        }
        for item in calls
    ]
    return subprocess.run(
        ["node", str(CANONICAL)],
        input=json.dumps(values, ensure_ascii=False).encode(),
        check=True,
        capture_output=True,
        timeout=10,
    ).stdout


def _assert_same_bytes(left: list[dict[str, str]], right: list[dict[str, str]]) -> None:
    """両経路の正規形バイト列が完全一致することを要求する。"""
    assert _canonical_bytes(left) == _canonical_bytes(right)


def test_canonical_json_sorts_keys_and_keeps_array_order() -> None:
    """比較の正規形をキー順・配列順・UTF-8 で固定する。"""
    calls = [
        {
            "operation": "probe",
            "requestJson": '{"z":"あ","a":[{"b":"2","a":"1"}],"2":"二","10":"十"}',
            "responseJson": '{"value":"3"}',
        }
    ]
    assert _canonical_bytes(calls) == (
        '[{"operation":"probe","request":{"10":"十","2":"二",'
        '"a":[{"a":"1","b":"2"}],'
        '"z":"あ"},"response":{"value":"3"}}]'
    ).encode()


def test_same_artifact_has_identical_bytes_on_both_routes() -> None:
    """同一 artifact・同一 case の両経路がバイト一致する。"""
    _assert_same_bytes(_node_calls(), _vm_calls(ARTIFACT))


def test_changed_vm_artifact_is_detected(tmp_path: Path) -> None:
    """vm 側だけ計算結果を変えるとバイト不一致になる。"""
    original = ARTIFACT.read_text(encoding="utf-8")
    assert "+ 1n" in original
    changed = tmp_path / "pitchlog-domain.js"
    changed.write_text(original.replace("+ 1n", "+ 2n", 1), encoding="utf-8")
    with pytest.raises(AssertionError):
        _assert_same_bytes(_node_calls(), _vm_calls(changed))
