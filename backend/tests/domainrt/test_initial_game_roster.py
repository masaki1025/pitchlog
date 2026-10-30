"""開始名簿の実artifact照合と表現境界の故障を分けて検査する。"""

from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from pitchlog.domainrt import initial_game_roster as caller
from pitchlog.domainrt.host import DomainRuntimeError, open_domain_host

_ROOT = Path(__file__).resolve().parents[3]
_BASE = _ROOT / "contracts/state-transition"
_CASES = json.loads((_BASE / "initial_game_roster_cases_v1.json").read_text())["cases"]
_SCHEMA = json.loads((_BASE / "initial_game_roster_schema_v1.json").read_text())


def _request() -> caller.InitialGameRosterRequest:
    """契約の正常要求を表現DTOへ読む。計算しない。"""
    return caller.InitialGameRosterRequest.model_validate_json(
        json.dumps(_CASES[0]["request"])
    )


def _set_at(document: Any, path: tuple[str | int, ...], value: Any) -> None:
    """局所故障を注入する。"""
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["id"])
def test_real_fixed_host_and_typed_caller_preserve_contract(
    case: dict[str, Any],
) -> None:
    """19実入力は固定hostへ、DTOで表現可能な入力は製品callerにも渡す。"""
    assert len(_CASES) == 19
    raw = json.dumps(case["request"])
    try:
        with open_domain_host() as host:
            response = host.call("validateInitialGameRoster", raw)
    except DomainRuntimeError as error:
        # 数値の既host先行拒否はartifactの拒否結果と区別する。
        assert error.code == "INVALID_BOUNDARY"
        assert case["id"] == "JSON-NUMBER"
        assert case["expected"] == {
            "ok": False,
            "error": {"code": "INVALID_DECIMAL_INTEGER"},
        }
        with pytest.raises(ValidationError):
            caller.InitialGameRosterRequest.model_validate_json(raw)
        return
    actual = json.loads(response)
    Draft202012Validator(_SCHEMA).validate(actual)
    assert actual == case["expected"]
    assert (
        caller.decode_initial_roster_response(response).model_dump(mode="json")
        == actual
    )
    try:
        request = caller.InitialGameRosterRequest.model_validate_json(raw)
    except ValidationError:
        assert actual["ok"] is False
    else:
        assert (
            caller.evaluate_initial_game_roster(request).model_dump(mode="json")
            == actual
        )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("dh",), 1),
        (("dh",), "true"),
        (("away", "team_id"), "AAAAAAAA-0000-0000-0000-000000000001"),
        (("away", "team_id"), "00000000-0000-0000-0000-000000000001\n"),
        (("home", "team_id"), None),
        (("away", "entries"), []),
        (("away", "entries", 0, "batting_order"), 1),
        (("away", "entries", 0, "batting_order"), True),
        (("away", "entries", 0, "batting_order"), "01"),
        (("away", "entries", 0, "player_id"), "unknown"),
        (("home", "entries", 0, "fielding_position"), {"kind": "unknown"}),
        (
            ("home", "entries", 0, "fielding_position"),
            {"kind": "fielding", "position": "10"},
        ),
    ],
)
def test_request_rejects_coercion_and_outside_closed_shape(
    path: tuple[str | int, ...], value: Any
) -> None:
    """表現の拒否だけを検査し、配置の別実装を作らない。"""
    raw = copy.deepcopy(_CASES[0]["request"])
    _set_at(raw, path, value)
    with pytest.raises(ValidationError):
        caller.InitialGameRosterRequest.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("ok",), 1),
        (("value", "teams"), []),
        (("value", "teams", 0, "side"), "home"),
        (("value", "teams", 1, "side"), "away"),
        (("value", "teams", 0, "participants"), []),
        (("value", "teams", 0, "participants", 0, "roles"), []),
        (
            ("value", "teams", 0, "participants", 0, "roles"),
            [{"kind": "designated-hitter"}] * 2,
        ),
        (
            ("value", "teams", 0, "participants", 0, "entry_origin"),
            {"kind": "substitution"},
        ),
        (("value", "teams", 0, "participants", 0, "player", "kind"), "temporary"),
        (
            ("value", "teams", 0, "participants", 0, "batting_slot"),
            {"kind": "slot", "slot": 1},
        ),
    ],
)
def test_response_rejects_incomplete_and_coerced_wire(
    path: tuple[str | int, ...], value: Any
) -> None:
    """未知の射影を保存可能な成功へ補完しない。"""
    raw = copy.deepcopy(_CASES[0]["expected"])
    _set_at(raw, path, value)
    with pytest.raises(caller.InitialRosterProtocolError):
        caller.decode_initial_roster_response(json.dumps(raw))


@pytest.mark.parametrize(
    "raw",
    [
        '{"ok":false,"ok":false,"error":{"code":"INVALID_REQUEST"}}',
        '{"ok":false,"error":{"code":"UNKNOWN"}}',
        '{"ok":false,"error":{"code":"INVALID_REQUEST","extra":null}}',
        '{"ok":false,"error":{"code":"INVALID_REQUEST"},"value":null}',
        '{"ok":false,"error":{"code":"INVALID_REQUEST"},"extra":NaN}',
        '{"ok":true}',
        "null",
        "[]",
        "",
    ],
)
def test_decoder_rejects_duplicate_unknown_and_nonfinite(raw: str) -> None:
    """非JSON/余剰/未知コードを固定protocol故障へ閉じる。"""
    with pytest.raises(caller.InitialRosterProtocolError) as caught:
        caller.decode_initial_roster_response(raw)
    assert str(caught.value) == "開始名簿応答が固定ABIに適合しません"
    assert caught.value.__suppress_context__ is True


@pytest.mark.parametrize("case", _CASES[:3], ids=lambda case: case["id"])
def test_models_are_deeply_frozen(case: dict[str, Any]) -> None:
    """JSON配列を不変tupleへ写し、入れ子の書換えも拒否する。"""
    request = caller.InitialGameRosterRequest.model_validate_json(
        json.dumps(case["request"])
    )
    with pytest.raises(ValidationError):
        setattr(request.away.entries[0], "player_id", request.home.entries[0].player_id)
    assert type(request.away.entries) is tuple
    decoded = caller.decode_initial_roster_response(json.dumps(case["expected"]))
    assert isinstance(decoded, caller.InitialRosterSuccess)
    assert type(decoded.value.teams) is tuple
    assert type(decoded.value.teams[0].participants[0].roles) is tuple
    with pytest.raises(ValidationError):
        setattr(decoded.value.teams[0].participants[0].entry_origin, "kind", "changed")


@pytest.mark.parametrize(
    "mode", ("extra", "missing", "wrong_type", "wrong_request_type")
)
def test_forced_invalid_members_are_rejected_before_host(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """model_construct等の改変がhostへ届かないことを検査する。"""
    request: Any = _request()
    if mode == "extra":
        object.__setattr__(request.away.entries[0], "unknown", None)
    elif mode == "missing":
        object.__delattr__(request.away.entries[0], "player_id")
    elif mode == "wrong_type":
        object.__setattr__(request.away.entries[0], "batting_order", 1)
    else:
        request = request.model_dump(mode="json")

    def forbidden() -> Any:
        raise AssertionError("不正要求でhostを開いてはならない")

    monkeypatch.setattr(caller, "open_domain_host", forbidden)
    with pytest.raises((ValidationError, TypeError)):
        caller.evaluate_initial_game_roster(request)


def test_caller_uses_fixed_single_operation_and_propagates_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """固定host呼出し一回と故障伝播をspiesで検査し、実hostとは別記する。"""
    calls: list[tuple[str, str]] = []
    request = _request()

    class Host:
        def call(self, operation: str, raw: str) -> str:
            calls.append((operation, raw))
            return json.dumps(_CASES[0]["expected"])

    @contextmanager
    def fake_host() -> Any:
        yield Host()

    monkeypatch.setattr(caller, "open_domain_host", fake_host)
    actual = caller.evaluate_initial_game_roster(request)
    assert actual.model_dump(mode="json") == _CASES[0]["expected"]
    assert calls == [
        ("validateInitialGameRoster", request.model_dump_json(by_alias=True))
    ]

    @contextmanager
    def failed_host() -> Any:
        raise DomainRuntimeError("SYNTHETIC_UNAVAILABLE", "synthetic host unavailable")
        yield

    monkeypatch.setattr(caller, "open_domain_host", failed_host)
    with pytest.raises(
        DomainRuntimeError, match="synthetic host unavailable"
    ) as caught:
        caller.evaluate_initial_game_roster(request)
    assert caught.value.code == "SYNTHETIC_UNAVAILABLE"
