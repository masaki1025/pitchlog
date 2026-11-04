"""実source集約不足や自己申告でbridge/責任資格を発行しない。"""

import copy

import pytest

from pitchlog.repositories.ordinary_prefix import OrdinaryPrefixError
from pitchlog.repositories.play_prefix import (
    _require_legacy_compatibility,
    _verify_source_evidence,
)


def evidence():
    """全3play/履歴3の仮原本。真正DB証拠ではない。"""
    return {
        "content": {"prefix_ref": {"length": "3"}, "history_depth": "3"},
        "source_evidence": {
            "all_play_count": 3,
            "ordinary_play_count": 3,
            "invalid_count": 0,
            "non_play_count": 0,
            "history_count": 3,
            "pa_change_count": 0,
        },
    }


def test_exact_real_aggregate_needed_for_bridge_and_no_change():
    """ordinary長を全play長へ無言で読み替えず、PA交代を拒否する。"""
    row = evidence()
    _verify_source_evidence(row, bridge=True)
    for field in row["source_evidence"]:
        changed = copy.deepcopy(row)
        changed["source_evidence"][field] += 1
        with pytest.raises(OrdinaryPrefixError):
            _verify_source_evidence(changed, bridge=True)
    with pytest.raises(OrdinaryPrefixError):
        _verify_source_evidence({"content": row["content"]}, bridge=True)
    with pytest.raises(OrdinaryPrefixError):
        _require_legacy_compatibility("0" * 64, "1" * 64)
