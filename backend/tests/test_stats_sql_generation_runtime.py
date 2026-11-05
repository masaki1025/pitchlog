"""SQL実行時生成の同一性・入力拒否・開発toolchain非依存を確認する。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pitchlog.domaingen import core
from pitchlog.domaingen.backends import python as py_backend
from pitchlog.domaingen.backends import typescript as ts_backend

ROOT = Path(__file__).resolve().parents[2]
SQL_PATHS = {
    "backend/src/pitchlog/exports/generated/play_primitives.sql",
    "backend/src/pitchlog/stats/generated/stats.sql",
}


def _models():
    """実生成入力を読む。"""
    return tuple(
        json.loads((ROOT / "backend/domain" / name).read_text())
        for name in ("play-export.model.json", "stats.model.json")
    )


def test_sql_generation_has_no_formatter_or_other_language_execution(monkeypatch):
    """外部toolchainなしでも二SQL全byteを再現する。"""

    def forbidden(*args, **kwargs):
        raise AssertionError("SQL生成で他言語生成・整形を実行した")

    monkeypatch.setattr(core, "_format_typed_target", forbidden)
    monkeypatch.setattr(py_backend, "generate_typed_facts", forbidden)
    monkeypatch.setattr(py_backend, "generate_typed_receiver", forbidden)
    monkeypatch.setattr(ts_backend, "generate_typed_facts", forbidden)
    result = core.generate_primitive_sql_bundle(*_models())
    assert set(result) == SQL_PATHS
    assert result == {path: (ROOT / path).read_text() for path in SQL_PATHS}


def test_full_generation_keeps_all_seven_existing_artifacts():
    """既公開七対象の集合と全byteを保持する。"""
    manifest = json.loads((ROOT / "backend/domain/stats-manifest.json").read_text())
    result = core.generate_primitive_bundle(*_models())
    assert set(result) == set(manifest["generatedFiles"])
    assert result == {path: (ROOT / path).read_text() for path in result}


@pytest.mark.parametrize("mutation", ["extra", "hash", "refs", "cycle", "schema"])
@pytest.mark.parametrize(
    "entry", [core.generate_primitive_bundle, core.generate_primitive_sql_bundle]
)
def test_both_entries_reject_invalid_models(mutation, entry):
    """閉集合・参照hash・順序・循環・schema拒否を両入口で維持する。"""
    common, consumer = copy.deepcopy(_models())
    if mutation == "extra":
        common["unexpected"] = True
    elif mutation == "hash":
        consumer["calculations"][0]["typedProgram"]["commonModelHash"] = (
            "sha256:" + "0" * 64
        )
    elif mutation == "refs":
        consumer["calculations"][0]["typedProgram"]["refs"].reverse()
    elif mutation == "cycle":
        consumer["calculations"][0]["calculationId"] = common["calculations"][0][
            "calculationId"
        ]
    else:
        common["schemaVersion"] = 2
    with pytest.raises(core.GenerationError):
        entry(common, consumer)
