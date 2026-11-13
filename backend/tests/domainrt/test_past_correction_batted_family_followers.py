"""P3の後続打球群を実71f核と既V7・物理・T5へ順次束縛する。"""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import get_args
from uuid import UUID

import pytest
from domainrt.test_past_correction_batted_followers import _hit
from domainrt.test_past_correction_lineup import _host, _two_saved
from test_batted_hit_prefix_payload import observations
from test_lineup_play_prefix_continuation import ACTUAL

from pitchlog.domainrt.lineup_play_prefix_continuation import (
    BattedHitT1Input,
    LineupPrefixProtocolError,
    LineupPrefixSuccess,
    RunnerValue,
    decode_lineup_prefix_request,
    decode_lineup_prefix_response,
    seal_lineup_wire,
)
from pitchlog.domainrt.past_correction_lineup import (
    _BATTED_FOLLOWER_RESULTS,
    LineupCorrectionUnsupported,
    SavedLineupPitch,
    _bound_original,
    _evaluate,
    _next_corrected_request,
    build_corrected_lineup_payloads,
)
from pitchlog.stats.facts import evaluate_native_projection
from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.past_correction_physical import prepare_corrected_physical_pitches
from pitchlog.sync.terminal_pitch_payload import (
    BattedHitPlayObservations,
    LineupPitchCalculation,
    format_batted_hit_prefix_payload,
    read_lineup_pitch_payload,
)
from pitchlog.sync.terminal_pitch_projection import runner_physical_rows

_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE = json.loads(
    (_ROOT / "contracts/state-transition/batted_hit_prefix_cases_v1.json").read_text()
)["cases"][0]["request"]
_RESULTS = (
    ("batted-out", "empty", None, False, False),
    ("batted-reach", "first", "2", False, False),
    ("fielders-choice", "first", "2", False, False),
    ("sacrifice-bunt", "first", "2", False, False),
    ("sacrifice-fly", "third", "4", False, True),
    ("double-play", "first", None, False, False),
    ("error", "first", "2", True, False),
    ("sacrifice-bunt-error", "first", "2", True, False),
)


def test_follower_set_is_exactly_the_closed_current_batted_input_family():
    """打球の未知resultや欠落resultを後続資格へ混入させない。"""
    allowed = BattedHitT1Input.model_fields["result_id"].annotation
    assert set(get_args(allowed)) == _BATTED_FOLLOWER_RESULTS


def _follower(
    host,
    previous,
    result,
    *,
    base=None,
    destination=None,
    error=False,
    rbi=None,
    hold=False,
):
    """原結果/観測を明示して実hostで旧計算を作る。期待値は計算しない。"""
    d1 = previous.d1 + 1
    raw = deepcopy(_TEMPLATE)
    t1 = raw["t1"]
    t1["resultId"] = "batting-result." + result
    if error:
        t1["officialScoringPayload"] = "error-recorded"
    if base is not None and destination is not None:
        t1["runnerAdvanceOverrides"] = {
            "kind": "applied",
            "overrides": [{"runnerBase": base, "destination": destination}],
        }
    if hold:
        t1["runnerAdvanceOverrides"] = {
            "kind": "applied",
            "overrides": [{"runnerBase": "1", "destination": "1"}],
        }
    if rbi is not None:
        t1["rbiRulingByRunner"] = {base: rbi}
    if result == "double-play":
        runners = previous.calculation.response.value.runners
        assert len(runners) == 1 and runners[0].base == "1"
        t1["outRunner"] = {
            "base": "1",
            "runnerId": runners[0].runner_id,
            "outKind": "force-out",
        }
    raw["playIdentity"] = {
        "eventId": str(UUID(int=32000 + d1 * 3)),
        "d5": str(UUID(int=32001 + d1 * 3)),
        "playId": str(UUID(int=32002 + d1 * 3)),
    }
    raw["source"]["position"] = {
        "d1": str(d1),
        "d2": str(d1),
        "appliedWatermark": str(d1 - 1),
    }
    raw["nextCheckpoint"]["revision"] = str(d1 + 1)
    q = _next_corrected_request(
        decode_lineup_prefix_request(json.dumps(raw)),
        previous.calculation.response,
        None,
        UUID(int=33000 + d1),
        host.artifact_sha256,
    )
    r = decode_lineup_prefix_response(
        host.call(
            "deriveLineupPlayPrefixWithContinuation",
            q.model_dump_json(by_alias=True, exclude_unset=True),
        )
    )
    assert type(r) is LineupPrefixSuccess, r
    q, r = seal_lineup_wire(q, r)
    calc = LineupPitchCalculation.model_validate_json(
        json.dumps(
            {
                "formatVersion": "play-prefix-calculation-v3",
                "artifactSha256": host.artifact_sha256,
                "request": q.model_dump(mode="json", by_alias=True, exclude_unset=True),
                "response": r.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                ),
            }
        )
    )
    observed = observations({"request": raw})
    if error:
        fielder = q.source.lineup.home.pitcher_id
        observed["officialScoringPayload"] = {
            "kind": "error-recorded",
            "errors": [
                {"fielder": {"kind": "official", "player_id": fielder}, "count": 1}
            ],
        }
    if base is not None and destination is not None:
        observed["runnerAdvanceOverridesByRunner"] = t1["runnerAdvanceOverrides"]
    if hold:
        observed["runnerAdvanceOverridesByRunner"] = t1["runnerAdvanceOverrides"]
    if result == "double-play":
        observed["outRunner"] = t1["outRunner"]
    if rbi is not None:
        observed["rbiRulingByRunner"] = t1["rbiRulingByRunner"]
    obs = BattedHitPlayObservations.model_validate_json(json.dumps(observed))
    v7, v8 = format_batted_hit_prefix_payload(obs, calc)
    payload = read_lineup_pitch_payload(v7, v8, expected_calculation=calc)
    return SavedLineupPitch(UUID(q.play_identity.event_id), d1, d1, calc, payload)


def _physical(row):
    """旧原本の41列と走者行を製品mapperで作る。"""
    assert row.payload is not None
    q = row.calculation.request
    tenant = UUID(q.prefix_ref.tenant_id)
    game = UUID(q.prefix_ref.game_id)
    play = UUID(q.play_identity.play_id)
    return replace(
        row,
        play_row=pitch_physical_row(
            row.payload.observations,
            row.payload.participants,
            q.t1.result_id,
            tenant_id=tenant,
            game_id=game,
            source_event_id=row.source_event_id,
            row_id=play,
            play_number=row.d1,
        ),
        play_runners=tuple(
            runner_physical_rows(
                q.source.runners,
                t1=row.calculation.response.value.t1,
                t1_input=q.t1,
                tenant_id=tenant,
                play_id=play,
            )
        ),
    )


def _scenario(
    host, result, prior, destination, error, scoring, *, hold=False, rbi="ordinary-play"
):
    first = _two_saved(host)[0]
    if prior == "first":
        prefix = (first, _hit(host, first, "single"))
        base = "1"
    elif prior == "third":
        prefix = (first, _hit(host, first, "triple"))
        base = "3"
    else:
        prefix = (first,)
        base = None
    follower = _follower(
        host,
        prefix[-1],
        result,
        base=base,
        destination=destination,
        error=error,
        rbi=rbi if scoring else None,
        hold=hold,
    )
    return tuple(_physical(row) for row in (*prefix, follower))


def _verify_current_physical_and_t5(rows, corrected, payloads):
    """既41列mapperと唯一T5の元/有効全値を比較する。"""
    q = rows[0].calculation.request
    physical = prepare_corrected_physical_pitches(
        rows,
        corrected,
        payloads,
        tenant_id=UUID(q.prefix_ref.tenant_id),
        game_id=UUID(q.prefix_ref.game_id),
        capsule_id=UUID(int=35000),
        change_event_id=UUID(int=35001),
    )
    saved = rows[-1]
    candidate = physical[-1]
    assert saved.payload is not None
    assert candidate.play_row == saved.play_row
    assert candidate.play_runners == saved.play_runners
    assert candidate.effective_event_id == saved.source_event_id
    assert payloads[-1].observations == saved.payload.observations
    assert (
        corrected[-1].corrected_request.play_identity
        == saved.calculation.request.play_identity
    )
    expected = evaluate_native_projection(
        saved.payload.model_dump(mode="json", by_alias=True, exclude_unset=True),
        source_event_id=saved.source_event_id,
    )
    actual = evaluate_native_projection(
        payloads[-1].model_dump(mode="json", by_alias=True, exclude_unset=True),
        source_event_id=candidate.effective_event_id,
    )
    assert actual == expected
    assert actual["selected"] is True
    return actual


@pytest.mark.parametrize("result,prior,destination,error,scoring", _RESULTS)
def test_eight_new_batted_followers_keep_actual_payload_physical_and_t5(
    result,
    prior,
    destination,
    error,
    scoring,
):
    """旧原本を現行artifactで再生し、訂正後も同観測・41列・唯一T5へ帰着する。"""
    with _host() as host:
        assert host.artifact_sha256 == ACTUAL
        rows = _scenario(host, result, prior, destination, error, scoring)
        corrected = _evaluate(
            rows,
            "batting-result.ball",
            tuple(UUID(int=34000 + i) for i in range(len(rows))),
            host,
        )
        assert rows[0].payload is not None
        payloads = build_corrected_lineup_payloads(
            rows,
            corrected,
            rows[0].payload.observations,
        )
        _verify_current_physical_and_t5(rows, corrected, payloads)


def test_hold_and_rbi04_remain_explicit_in_follower():
    """確認済holdと停止後再発進RBI不算入を元観測から保つ。"""
    with _host() as host:
        rows = _scenario(host, "batted-out", "first", None, False, False, hold=True)
        corrected = _evaluate(
            rows,
            "batting-result.ball",
            tuple(UUID(int=36000 + i) for i in range(len(rows))),
            host,
        )
        assert rows[-1].payload is not None and rows[0].payload is not None
        payloads = build_corrected_lineup_payloads(
            rows,
            corrected,
            rows[0].payload.observations,
        )
        assert payloads[-1].observations == rows[-1].payload.observations
        _verify_current_physical_and_t5(rows, corrected, payloads)
        assert (
            corrected[-1].corrected_response.value.t1.after.state_fields.runners
            == "first"
        )
        rows = _scenario(
            host, "single", "third", "4", False, True, rbi="stopped-and-restarted"
        )
        corrected = _evaluate(
            rows,
            "batting-result.ball",
            tuple(UUID(int=37000 + i) for i in range(len(rows))),
            host,
        )
        assert rows[0].payload is not None and rows[-1].payload is not None
        payloads = build_corrected_lineup_payloads(
            rows,
            corrected,
            rows[0].payload.observations,
        )
        value = corrected[-1].corrected_response.value
        assert type(value) is RunnerValue
        effect = value.runner_score_effects
        assert [(item.base, item.valid_run, item.rbi_credited) for item in effect] == [
            ("3", True, False)
        ]
        assert payloads[-1].observations == rows[-1].payload.observations
        native = _verify_current_physical_and_t5(rows, corrected, payloads)
        assert native["metrics"]["rbi"]["value"] == "0"


def test_original_scope_still_rejects_batted_target_and_cross_source():
    """後続拡張をtargetや別event原本の許可へ読み替えない。"""
    with _host() as host:
        rows = _scenario(host, "batted-out", "empty", None, False, False)
        with pytest.raises(LineupCorrectionUnsupported):
            _evaluate(
                rows, "batting-result.ball", (UUID(int=38000),), host, target_d1=2
            )
        previous = rows[-2].calculation.response
        with pytest.raises(LineupCorrectionUnsupported):
            _bound_original(
                replace(rows[-1], source_event_id=UUID(int=38001)),
                previous,
                host,
                allow_batted=True,
            )
        with pytest.raises(LineupCorrectionUnsupported):
            _bound_original(
                replace(rows[-1], payload=None),
                previous,
                host,
                allow_batted=True,
            )
        saved = rows[-1]
        assert saved.payload is not None
        q = saved.calculation.request
        other_team = q.source.lineup.away.team_id
        changed_lineup = q.source.lineup.model_copy(
            update={
                "home": q.source.lineup.home.model_copy(update={"team_id": other_team})
            }
        )
        changed_source = q.source.model_copy(update={"lineup": changed_lineup})
        changed_q = q.model_copy(update={"source": changed_source})
        changed_calc = saved.calculation.model_copy(update={"request": changed_q})
        changed_payload = saved.payload.model_copy(update={"calculation": changed_calc})
        with pytest.raises(LineupPrefixProtocolError):
            _bound_original(
                replace(saved, calculation=changed_calc, payload=changed_payload),
                previous,
                host,
                allow_batted=True,
            )


def test_batted_out_before_target_carries_original_but_target_stays_ordinary():
    """対象前の凡打原本は再生だけに使い、打球訂正へ昇格させない。"""
    with _host() as host:
        first, ordinary_template = _two_saved(host)
        out = _follower(host, first, "batted-out")
        raw = ordinary_template.calculation.request.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        )
        raw["source"]["position"] = {"d1": "3", "d2": "3", "appliedWatermark": "2"}
        raw["playIdentity"] = {
            "eventId": str(UUID(int=39000)),
            "d5": str(UUID(int=39001)),
            "playId": str(UUID(int=39002)),
        }
        raw["nextCheckpoint"]["revision"] = "4"
        q = _next_corrected_request(
            decode_lineup_prefix_request(json.dumps(raw)),
            out.calculation.response,
            None,
            UUID(int=39003),
            host.artifact_sha256,
        )
        r = decode_lineup_prefix_response(
            host.call(
                "deriveLineupPlayPrefixWithContinuation",
                q.model_dump_json(by_alias=True, exclude_unset=True),
            )
        )
        assert type(r) is LineupPrefixSuccess
        q, r = seal_lineup_wire(q, r)
        calc = LineupPitchCalculation.model_validate_json(
            json.dumps(
                {
                    "formatVersion": "play-prefix-calculation-v3",
                    "artifactSha256": host.artifact_sha256,
                    "request": q.model_dump(
                        mode="json", by_alias=True, exclude_unset=True
                    ),
                    "response": r.model_dump(
                        mode="json", by_alias=True, exclude_unset=True
                    ),
                }
            )
        )
        target = SavedLineupPitch(UUID(q.play_identity.event_id), 3, 3, calc)
        result = _evaluate(
            (first, out, target),
            "batting-result.ball",
            (UUID(int=39004),),
            host,
            target_d1=3,
        )
        assert len(result) == 1
        assert result[0].d1 == 3
        assert result[0].corrected_request.t1.result_id == "batting-result.ball"


@pytest.mark.parametrize("boundary", ["saved-seal", "saved-payload"])
def test_saved_protocol_failure_keeps_original_exception_identity(
    monkeypatch, boundary
):
    """既保存原本の故障を、利用者の変更内容拒否へ再分類しない。"""
    from pitchlog.domainrt import past_correction_lineup as module

    with _host() as host:
        saved = _two_saved(host)[0]
        assert saved.payload is not None
        failure = LineupPrefixProtocolError("source-integrity-fixture")
        calls = []

        def rejected(*args, **kwargs):
            calls.append(True)
            raise failure

        symbol = (
            "verify_lineup_wire_seal"
            if boundary == "saved-seal"
            else "read_lineup_pitch_payload"
        )
        monkeypatch.setattr(module, symbol, rejected)
        with pytest.raises(LineupPrefixProtocolError) as caught:
            if boundary == "saved-seal":
                _bound_original(saved, None, host)
            else:
                module._read_payload(saved.payload, require_current_rbi=False)
        assert caught.value is failure
        assert calls == [True]
