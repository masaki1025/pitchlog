"""E-1 のその場登録イベントから選手作成値を取り出す。

wire 3-2 の追補候補 `registration`（登録側原入力）を閉じた形で読み、P1 の
`PlayerRegistration` へ写す。値の意味判定は行わず、型・欠落・一時 ID と V7 の
一致だけを S-1 外形として検査する。
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from pitchlog.sync.model import RequestShapeError, _canonical_uuid
from pitchlog.sync.prefix_path import PlayerRegistration

PLAYER_REGISTRATION_EVENT_KIND = "player_registration"

_REQUIRED_KEYS = frozenset(
    {"temporary_id", "team_record_id", "name", "roster_status_key"}
)
_OPTIONAL_KEYS = frozenset({"throws", "bats", "uniform_number"})
_PAYLOAD_KEYS = frozenset({"player_id"})


def _text(value: object, field: str) -> str:
    """空・空白だけ・非文字列を選手作成値へ通さない。"""
    if type(value) is not str or not value or value.strip() != value:
        raise RequestShapeError(f"S-1: その場登録の {field} が不正")
    return value


def _uuid_text(value: object, field: str) -> str:
    """UUID の正規形だけを受理する。"""
    if not _canonical_uuid(value):
        raise RequestShapeError(f"S-1: その場登録の {field} が UUID 正規形ではない")
    assert type(value) is str
    # 正規形判定後に UUID として読めることを再確認する。
    if str(UUID(value)) != value:
        raise RequestShapeError(f"S-1: その場登録の {field} が UUID 正規形ではない")
    return value


def _optional_choice(value: object, field: str, allowed: frozenset[str]) -> str | None:
    """任意の選択値を欠落または許可値に閉じる。"""
    if value is None:
        return None
    if type(value) is not str or value not in allowed:
        raise RequestShapeError(f"S-1: その場登録の {field} が不正")
    return value


def _read_registration(value: object) -> PlayerRegistration:
    """1 件の登録側原入力を閉じた値へ写す。"""
    if not isinstance(value, Mapping):
        raise RequestShapeError("S-1: その場登録の registration が object ではない")
    keys = frozenset(value)
    if not _REQUIRED_KEYS <= keys or not keys <= _REQUIRED_KEYS | _OPTIONAL_KEYS:
        raise RequestShapeError("S-1: その場登録の registration のキーが不正")
    temporary_id = _uuid_text(value["temporary_id"], "temporary_id")
    team_record_id = _uuid_text(value["team_record_id"], "team_record_id")
    uniform_number = value.get("uniform_number")
    if uniform_number is not None and (
        type(uniform_number) is not str or not uniform_number
    ):
        raise RequestShapeError("S-1: その場登録の uniform_number が不正")
    return PlayerRegistration(
        temporary_id=UUID(temporary_id),
        team_record_id=UUID(team_record_id),
        name=_text(value["name"], "name"),
        roster_status_key=_text(value["roster_status_key"], "roster_status_key"),
        throws=_optional_choice(
            value.get("throws"), "throws", frozenset({"right", "left"})
        ),
        bats=_optional_choice(
            value.get("bats"), "bats", frozenset({"right", "left", "both"})
        ),
        uniform_number=uniform_number,
    )


def _payload_player_id(event: Mapping[str, object]) -> str:
    """V7 が登録する一時 ID だけを持つことを確認する。"""
    payload = event.get("payload")
    if not isinstance(payload, Mapping) or frozenset(payload) != _PAYLOAD_KEYS:
        raise RequestShapeError("S-1: その場登録の payload が閉じていない")
    return _uuid_text(payload["player_id"], "payload.player_id")


def read_player_registrations(
    raw_events: tuple[Mapping[str, object], ...],
) -> dict[str, PlayerRegistration]:
    """登録イベントごとに D5 から選手作成値への写像を返す。

    Args:
        raw_events: E-1 の原イベント列。

    Returns:
        D5 をキーにした選手作成値。登録イベントが無ければ空。

    Raises:
        RequestShapeError: registration と payload の外形が一致しない場合。
    """
    registrations: dict[str, PlayerRegistration] = {}
    for event in raw_events:
        kind = event.get("event_kind")
        has_registration = "registration" in event
        if kind != PLAYER_REGISTRATION_EVENT_KIND:
            if has_registration:
                raise RequestShapeError(
                    "S-1: その場登録以外に registration を指定できない"
                )
            continue
        if not has_registration:
            raise RequestShapeError("S-1: その場登録の registration がない")
        registration = _read_registration(event.get("registration"))
        player_id = _payload_player_id(event)
        if player_id != str(registration.temporary_id):
            raise RequestShapeError("S-1: その場登録の一時 ID が payload と一致しない")
        d5 = event.get("d5")
        if not _canonical_uuid(d5):
            raise RequestShapeError("S-1: その場登録の D5 が不正")
        assert type(d5) is str
        registrations[d5] = registration
    return registrations
