"""過去訂正pageの固定型・正式通常case値との境界検査。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from pitchlog.domainrt import past_correction_replay as replay
from pitchlog.domainrt.past_correction_replay import (
    ReplayPageProtocolError,
    ReplayPageRequest,
    ReplayPageSuccess,
    decode_replay_page_response,
)

_ROOT = Path(__file__).resolve().parents[3]
_VECTORS = json.loads(
    (_ROOT / "contracts/state-transition/ordinary_pitch_vectors_v1.json").read_text(
        encoding="utf-8"
    )
)
_CASES = {row["caseId"]: row for row in _VECTORS["cases"]}
_ID1 = "11111111-1111-4111-8111-111111111111"
_ID2 = "22222222-2222-4222-8222-222222222222"


def _event(case: str) -> dict[str, object]:
    request = _CASES[case]["request"]
    return {key: request[key] for key in ("eventKind", "resultId", "pitchEventKind")}


def _request() -> dict[str, Any]:
    return deepcopy(
        {
            "version": "past-correction-ordinary-page-v1",
            "originalBefore": _CASES["ORDINARY-PITCH-25"]["request"]["before"],
            "correctedBefore": _CASES["ORDINARY-PITCH-25"]["request"]["before"],
            "previousD2": "0",
            "targetIncluded": True,
            "records": [
                {
                    "sourceEventId": _ID1,
                    "sourceD2": "1",
                    "original": _event("ORDINARY-PITCH-25"),
                    "storedAfter": _CASES["ORDINARY-PITCH-25"]["expected"]["value"][
                        "after"
                    ],
                    "replacement": _event("ORDINARY-PITCH-01"),
                },
                {
                    "sourceEventId": _ID2,
                    "sourceD2": "2",
                    "original": _event("ORDINARY-PITCH-28"),
                    "storedAfter": _CASES["ORDINARY-PITCH-28"]["expected"]["value"][
                        "after"
                    ],
                    "replacement": None,
                },
            ],
        }
    )


def _success() -> dict[str, Any]:
    return deepcopy(
        {
            "ok": True,
            "value": {
                "originalAfter": _CASES["ORDINARY-PITCH-28"]["expected"]["value"][
                    "after"
                ],
                "correctedAfter": _CASES["ORDINARY-PITCH-26"]["expected"]["value"][
                    "after"
                ],
                "lastD2": "2",
                "frames": [
                    {
                        "sourceEventId": _ID1,
                        "sourceD2": "1",
                        "original": _CASES["ORDINARY-PITCH-25"]["expected"]["value"],
                        "corrected": _CASES["ORDINARY-PITCH-01"]["expected"]["value"],
                    },
                    {
                        "sourceEventId": _ID2,
                        "sourceD2": "2",
                        "original": _CASES["ORDINARY-PITCH-28"]["expected"]["value"],
                        "corrected": _CASES["ORDINARY-PITCH-26"]["expected"]["value"],
                    },
                ],
            },
        }
    )


def test_formal_two_pitch_candidate_is_full_typed_wire() -> None:
    """正式caseを元のまま組み、全fieldを型付き境界で保持する。"""
    request = ReplayPageRequest.model_validate_json(json.dumps(_request()))
    assert len(request.records) == 2
    response = decode_replay_page_response(json.dumps(_success()))
    assert type(response) is ReplayPageSuccess
    assert (
        response.model_dump(mode="json", by_alias=True, exclude_unset=True)
        == _success()
    )


@pytest.mark.parametrize(
    "mutation",
    ["numeric-d2", "numeric-bool", "second-replacement", "unknown-field"],
)
def test_request_cannot_silently_normalize(mutation: str) -> None:
    """入力の数値/真理値/対象外置換/余剰を補修しない。"""
    request = _request()
    if mutation == "numeric-d2":
        request["previousD2"] = 0
    elif mutation == "numeric-bool":
        request["targetIncluded"] = 1
    elif mutation == "second-replacement":
        request["records"][1]["replacement"] = _event("ORDINARY-PITCH-01")
    else:
        request["extra"] = True
    with pytest.raises(ValueError):
        ReplayPageRequest.model_validate_json(json.dumps(request))


@pytest.mark.parametrize("mutation", ["extra", "numeric", "wrong-flags"])
def test_response_cannot_silently_normalize(mutation: str) -> None:
    """hostの全値欠落・余剰・数値化を成功にしない。"""
    response = _success()
    if mutation == "extra":
        response["value"]["frames"][0]["extra"] = None
    elif mutation == "numeric":
        response["value"]["lastD2"] = 2
    else:
        response["value"]["frames"][0]["corrected"]["statFlags"]["投球数"] = False
    with pytest.raises(ReplayPageProtocolError):
        decode_replay_page_response(json.dumps(response))


def test_duplicate_json_key_is_rejected() -> None:
    """重複keyを後勝ちのwireとして受け入れない。"""
    with pytest.raises(ReplayPageProtocolError):
        decode_replay_page_response(
            '{"ok":true,"ok":false,"error":{"code":"INVALID_REQUEST"}}'
        )


def test_fixed_host_operation_is_called_once_with_full_request(monkeypatch) -> None:
    """保存成功を作らず、唯一のhost操作へ閉本文全体を一度だけ渡す。"""
    calls: list[tuple[str, str]] = []

    class _Host:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def call(self, operation: str, body: str) -> str:
            calls.append((operation, body))
            return json.dumps(_success())

    monkeypatch.setattr(replay, "open_domain_host", _Host)
    request = ReplayPageRequest.model_validate_json(json.dumps(_request()))
    result = replay.evaluate_replay_page(request)
    assert type(result) is ReplayPageSuccess
    assert len(calls) == 1
    assert calls[0][0] == "replayPastCorrectionPage"
    assert json.loads(calls[0][1]) == _request()


@pytest.mark.parametrize(
    "mutation",
    ["source-id", "source-d2", "source-after", "frame-count", "last-d2", "last-after"],
)
def test_host_success_must_bind_to_exact_page(monkeypatch, mutation: str) -> None:
    """型だけ正しい別pageの成功を入力pageの結果へすり替えない。"""
    forged = _success()
    value = forged["value"]
    if mutation == "source-id":
        value["frames"][0]["sourceEventId"] = _ID2
    elif mutation == "source-d2":
        value["frames"][0]["sourceD2"] = "3"
    elif mutation == "source-after":
        value["frames"][0]["original"]["after"] = _CASES["ORDINARY-PITCH-26"][
            "expected"
        ]["value"]["after"]
    elif mutation == "frame-count":
        value["frames"] = value["frames"][:1]
    elif mutation == "last-d2":
        value["lastD2"] = "3"
    else:
        value["correctedAfter"] = _CASES["ORDINARY-PITCH-25"]["expected"]["value"][
            "after"
        ]

    class _Host:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def call(self, _operation: str, _body: str) -> str:
            return json.dumps(forged)

    monkeypatch.setattr(replay, "open_domain_host", _Host)
    request = ReplayPageRequest.model_validate_json(json.dumps(_request()))
    with pytest.raises(ReplayPageProtocolError):
        replay.evaluate_replay_page(request)
