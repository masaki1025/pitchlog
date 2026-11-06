"""配置済みT5生成物を実行する前の固定byte束縛を検証する。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "backend/src/pitchlog/stats/facts.py"
VECTORS = ROOT / "contracts/stats/native_event_facts_d11_v2.json"


@pytest.fixture(scope="module")
def facts_module() -> Iterator[ModuleType]:
    """製品wrapperを実ファイルからロードし、同じ関数を検査する。"""
    name = "_pitchlog_stats_generated_loader_under_test"
    spec = importlib.util.spec_from_file_location(name, WRAPPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(name, None)


def _replace_generated(monkeypatch, facts_module, tmp_path, source: bytes) -> Path:
    """wrapperの実ローダーが参照する配置先だけを一時差し替えする。"""
    wrapper = tmp_path / "backend/src/pitchlog/stats/facts.py"
    generated = wrapper.parent / "generated/facts.py"
    generated.parent.mkdir(parents=True)
    generated.write_bytes(source)
    monkeypatch.setattr(facts_module, "__file__", str(wrapper))
    return generated


def _assert_rejected_before_exec(monkeypatch, facts_module) -> None:
    """拒否時にPython実行命令まで到達しないことを数える。"""
    executed = []
    monkeypatch.setattr(
        facts_module,
        "exec",
        lambda *args: executed.append(args),
        raising=False,
    )
    with pytest.raises(RuntimeError):
        facts_module._generated_api()
    assert executed == []


@pytest.mark.parametrize("mutation", ["sentinel", "model_hash", "manifest"])
def test_modified_generated_file_cannot_execute(
    monkeypatch, facts_module, tmp_path, mutation
):
    """副作用・偽モデル版・同時manifest変更を実行前に拒否する。"""
    sentinel = tmp_path / "executed.txt"
    model_hash = "sha256:" + "0" * 64 if mutation == "sentinel" else SOURCE_MODEL_HASH
    source = (
        f"SOURCE_MODEL_HASH = {model_hash!r}\n"
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('executed')\n"
        "def _pitchlog_generated(event, requested_metrics=None):\n"
        "    return {'tampered': True}\n"
    ).encode()
    _replace_generated(monkeypatch, facts_module, tmp_path, source)
    if mutation == "manifest":
        manifest = tmp_path / "backend/domain/stats-manifest.json"
        manifest.parent.mkdir(parents=True)
        payload = json.loads((ROOT / "backend/domain/stats-manifest.json").read_text())
        payload["generatedFiles"]["backend/src/pitchlog/stats/generated/facts.py"] = (
            hashlib.sha256(source).hexdigest()
        )
        manifest.write_text(json.dumps(payload))
    _assert_rejected_before_exec(monkeypatch, facts_module)
    assert not sentinel.exists()


def test_import_rejects_modified_file_without_side_effect(tmp_path):
    """本番のmodule初回importでも改竄生成物を実行しない。"""
    sentinel = tmp_path / "import-executed.txt"
    wrapper = tmp_path / "facts.py"
    shutil.copyfile(WRAPPER, wrapper)
    generated = tmp_path / "generated/facts.py"
    generated.parent.mkdir()
    generated.write_text(
        f"SOURCE_MODEL_HASH = {SOURCE_MODEL_HASH!r}\n"
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('executed')\n"
    )
    spec = importlib.util.spec_from_file_location("_pitchlog_tampered_import", wrapper)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        with pytest.raises(RuntimeError, match="固定SHA256"):
            spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    assert not sentinel.exists()


def test_missing_generated_file_rejected_before_exec(
    monkeypatch, facts_module, tmp_path
):
    """配置先が欠落しても生成コードを実行しない。"""
    wrapper = tmp_path / "backend/src/pitchlog/stats/facts.py"
    monkeypatch.setattr(facts_module, "__file__", str(wrapper))
    _assert_rejected_before_exec(monkeypatch, facts_module)


def test_non_utf8_generated_file_rejected_before_exec(
    monkeypatch, facts_module, tmp_path
):
    """不正UTF-8を生成コードの実行前に拒否する。"""
    _replace_generated(monkeypatch, facts_module, tmp_path, b"\xff\xfe")
    _assert_rejected_before_exec(monkeypatch, facts_module)


def test_non_bytes_read_rejected_before_exec(monkeypatch, facts_module):
    """読取結果がbyte列以外でも閉じて拒否する。"""
    monkeypatch.setattr(Path, "read_bytes", lambda self: "not bytes")
    _assert_rejected_before_exec(monkeypatch, facts_module)


def test_existing_model_hash_gate_remains(monkeypatch, facts_module):
    """正規byteを実行した後もtyped receiverとの版照合を維持する。"""
    monkeypatch.setattr(facts_module, "SOURCE_MODEL_HASH", "sha256:" + "0" * 64)
    with pytest.raises(RuntimeError, match="モデル版"):
        facts_module._generated_api()


def test_valid_generated_file_preserves_all_d11_results(facts_module):
    """正規生成核を全D11入力で再ロードし、全返却fieldを比較する。"""
    loaded = facts_module._generated_api()
    cases = json.loads(VECTORS.read_text(encoding="utf-8"))["cases"]
    assert len(cases) == 27
    for case in cases:
        expected = case["expected"]["expected"]
        assert loaded(case["request"]) == expected
        assert loaded(case["request"]) == facts_module._EVENT_FACTS(case["request"])
