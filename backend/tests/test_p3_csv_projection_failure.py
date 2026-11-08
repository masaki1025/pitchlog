"""新CSV helperの非成功を既P3閉応答へ限定写像する。"""

import pytest

from pitchlog.sync import past_correction_projection as projection
from pitchlog.sync.play_export_producer import PlayExportWriterUnavailable


@pytest.mark.parametrize("stage", ["prepare", "persist"])
@pytest.mark.parametrize("known", [True, False])
def test_only_csv_unavailable_is_translated_without_swallowing_original(
    monkeypatch, stage, known
):
    """既core拒否の分類を変えず、CSV不足は同TXを例外で中断する。"""
    error = (
        PlayExportWriterUnavailable("test-only") if known else RuntimeError("test-only")
    )
    calls = []

    def fail(*args):
        calls.append(args)
        raise error

    if stage == "prepare":
        monkeypatch.setattr(projection, "prepare_p3_play_export_anchor", fail)
        invoke, args = projection._prepare_p3_csv_prior, (object(), object(), object())
    else:
        monkeypatch.setattr(projection, "persist_p3_play_exports", fail)
        invoke, args = (
            projection._persist_p3_csv,
            (object(), object(), object(), object()),
        )
    expected = projection.PastCorrectionProjectionError if known else RuntimeError
    with pytest.raises(expected) as caught:
        invoke(*args)
    assert calls == [args]
    if known:
        assert caught.value.__cause__ is error
    else:
        assert caught.value is error
