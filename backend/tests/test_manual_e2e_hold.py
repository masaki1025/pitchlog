"""任意の手動holdをDB起動なしで検査する。"""

import manual_e2e_hold_support as support
import pytest
from manual_e2e_hold_support import hold_manual_environment, manual_hold_seconds

time = support.time


def test_manual_hold_defaults_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """既定のE2E終了時刻を延ばさない。"""
    monkeypatch.delenv("PITCHLOG_E2E_MANUAL_HOLD_SECONDS", raising=False)
    assert manual_hold_seconds() == 0
    hold_manual_environment("unused", 0)


@pytest.mark.parametrize("raw", ["0", "1", "3600"])
def test_manual_hold_accepts_only_explicit_bounded_seconds(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """0または有限の明示整数だけを読み取る。"""
    monkeypatch.setenv("PITCHLOG_E2E_MANUAL_HOLD_SECONDS", raw)
    assert manual_hold_seconds() == int(raw)


@pytest.mark.parametrize("raw", ["", "-1", "+1", "01", "3601", "1.0", " 1"])
def test_manual_hold_rejects_invalid_settings(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """無期限・補修・過大の待機を設定できない。"""
    monkeypatch.setenv("PITCHLOG_E2E_MANUAL_HOLD_SECONDS", raw)
    with pytest.raises(ValueError):
        manual_hold_seconds()


def test_manual_hold_only_prints_loopback_origin_and_propagates_interrupt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """資格の表示も割込の握り潰しも行わず、呼出元cleanupへ戻す。"""
    monkeypatch.setattr(time, "monotonic", lambda: 1.0)

    def interrupt(_seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(time, "sleep", interrupt)
    with pytest.raises(KeyboardInterrupt):
        hold_manual_environment("https://127.0.0.1:12345", 1, "fixture-team")
    assert capsys.readouterr().out == (
        "PITCHLOG_E2E_MANUAL_ORIGIN=https://127.0.0.1:12345\n"
        'PITCHLOG_E2E_MANUAL_TEAM_NAME="fixture-team"\n'
    )
    with pytest.raises(ValueError):
        hold_manual_environment("https://example.invalid", 1)
    assert capsys.readouterr().out == ""


def test_manual_hold_ends_at_monotonic_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """期限で戻り、owned contextの通常cleanupを妨げない。"""
    clock = iter([0.0, 0.5, 1.0])
    sleeps: list[float] = []
    monkeypatch.setattr(time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(time, "sleep", sleeps.append)
    hold_manual_environment("https://127.0.0.1:12345", 1)
    assert sleeps == [0.5]
