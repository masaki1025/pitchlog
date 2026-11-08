"""旧数学/SQLを不変に保ち、閉取消選択だけを唯一backendで生成する。"""

import copy
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]
BACKEND_SRC = ROOT / "backend/src"
sys.path.insert(0, str(BACKEND_SRC))

CORE = importlib.import_module("pitchlog.domaingen.core")
PRECHECKS = importlib.import_module("pitchlog.domaingen.pregen_checks")
generate_native_primitive_sql_bundle = CORE.generate_native_primitive_sql_bundle
generate_primitive_sql_bundle = CORE.generate_primitive_sql_bundle
validate_undo_selection_profile = PRECHECKS.validate_undo_selection_profile


def inputs():
    """正式数学原本と数式を含まない独立selectorを読む。"""
    return tuple(
        json.loads((ROOT / "backend/domain" / name).read_text())
        for name in (
            "play-export.model.json",
            "stats.model.json",
            "play-export-undo-selection.model.json",
        )
    )


def test_old_generated_sql_all_bytes_and_new_native_three_are_deterministic():
    """旧3SQL/数学入力を再刻印せず、新3SQLだけを同modelから公式生成する。"""
    common, consumer, profile = inputs()
    old = generate_primitive_sql_bundle(common, consumer)
    assert old == {path: (ROOT / path).read_text() for path in old}
    native = generate_native_primitive_sql_bundle(common, consumer, profile)
    assert native == {path: (ROOT / path).read_text() for path in native}
    assert len(native) == 3 and not (set(old) & set(native))
    for text in native.values():
        assert "canonical_undos AS" in text
        for key in profile["bindingIdentity"]:
            assert "n." + key + " IS NOT DISTINCT FROM ub." + key in text
        assert "u.ledger_kind='accepted'" in text and "n.state='consumed'" in text
        assert "THEN 'excluded_undo'" in text
        assert "accepted-play-slot-v1:empty" in text
        assert "NULL::uuid /* restore-undo-event */" in text
        assert "source_unavailable" in text and "p.hidden_at IS NOT NULL" in text
    assert "-- pitchlog-query: canonical_source_members" in next(iter(native.values()))
    assert "metrics" not in profile


@pytest.mark.parametrize("key", list(inputs()[2]))
def test_every_selector_field_missing_or_mutated_is_rejected(key):
    """自由SQL/表/式や未宣言selectorへ生成対象を広げない。"""
    profile = inputs()[2]
    missing = copy.deepcopy(profile)
    del missing[key]
    with pytest.raises(ValueError):
        validate_undo_selection_profile(missing)
    changed = copy.deepcopy(profile)
    changed[key] = True
    with pytest.raises(ValueError):
        validate_undo_selection_profile(changed)
    changed = copy.deepcopy(profile)
    changed["expression"] = "true"
    with pytest.raises(ValueError):
        validate_undo_selection_profile(changed)
