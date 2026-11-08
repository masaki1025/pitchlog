"""保存済みP3原本と旧88列から表示列だけを写す。野球再計算はしない。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from uuid import UUID

from pitchlog.exports.generated.coordinate_transform import plate_result_display
from pitchlog.exports.p3_snapshot import P3SnapshotIdentity
from pitchlog.exports.play_rows import CSV_HEADERS, PlayExportSupplyError
from pitchlog.exports.record_projection import _native_before, _native_completion, _text
from pitchlog.sync.idempotency import source_fingerprint

_HEADERS = CSV_HEADERS["plays.csv"]
_AGGREGATED = frozenset({_HEADERS[34], _HEADERS[86], _HEADERS[87]})
_RESULTS = frozenset({"batting-result.ball", "batting-result.called-strike"})
_ITEM_FIELDS = frozenset(
    {
        "d1",
        "d2",
        "state",
        "original_event_id",
        "effective_event_id",
        "original_play_row_id",
        "effective_play_row_id",
        "original_payload",
        "original_history_entry",
        "original_play_row",
        "original_play_runners",
        "payload",
        "history_entry",
        "play_row",
        "play_runners",
        "digest",
    }
)


def _need(condition: bool) -> None:
    """原本不足を推測値で埋めない。"""
    if not condition:
        raise PlayExportSupplyError("P3毎球CSVの直接表示原本が未供給です")


@dataclass(frozen=True, slots=True)
class CorrectionResultReference:
    """訂正TXの正式lookup値。単独ではlookup成功や書込資格を表さない。"""

    tenant_id: UUID
    game_id: UUID
    capsule_id: UUID
    effective_event_id: UUID
    reference_id: UUID
    key: str
    display_name: str
    captured_at: datetime

    def __post_init__(self) -> None:
        """真正DB原本から供給された値の閉形を検査する。"""
        for name in (
            "tenant_id",
            "game_id",
            "capsule_id",
            "effective_event_id",
            "reference_id",
        ):
            _need(type(getattr(self, name)) is UUID)
        _need(type(self.key) is str and self.key in _RESULTS)
        _need(type(self.display_name) is str and bool(self.display_name))
        _need(
            type(self.captured_at) is datetime
            and self.captured_at.utcoffset() is not None
        )


def _origin_value(value: object) -> None:
    """既通常版と有限P3版だけを検査し、未知資格keyを通さない。"""
    current: Any = value
    base = {
        "formatVersion",
        "operationKind",
        "sourceFormat",
        "calculationFormat",
        "calculationArtifactSha256",
        "sourceEventId",
    }
    p3 = base | {"projectionKind", "capsuleId", "itemDigest", "originalInputOrigin"}
    while type(current) is dict:
        version = current.get("formatVersion")
        _need(
            version in {"play-export-input-origin-v1", "play-export-input-origin-p3-v1"}
        )
        for field in ("calculationArtifactSha256",):
            _need(
                type(current.get(field)) is str
                and re.fullmatch(r"[a-f0-9]{64}", current[field]) is not None
            )
        _need(
            type(current.get("sourceEventId")) is str
            and str(UUID(current["sourceEventId"])) == current["sourceEventId"]
        )
        if version == "play-export-input-origin-p3-v1":
            _need(
                set(current) == p3
                and current["operationKind"] in {"play_input", "play_change"}
                and current["projectionKind"] == "p3-current"
            )
            _need(
                type(current["capsuleId"]) is str
                and str(UUID(current["capsuleId"])) == current["capsuleId"]
            )
            _need(
                type(current["itemDigest"]) is str
                and re.fullmatch(r"[a-f0-9]{64}", current["itemDigest"]) is not None
            )
            _need(
                current["sourceFormat"] == "play-prefix-play-v3"
                and current["calculationFormat"] == "play-prefix-calculation-v3"
            )
            current = current["originalInputOrigin"]
            continue
        _need(current["operationKind"] == "play_input")
        pairs = {
            "first-ball-play-v1": "first-ball-calculation-v1",
            "ordinary-pitch-play-v1": "ordinary-pitch-calculation-v1",
            "play-prefix-play-v2": "play-prefix-calculation-v2",
            "play-prefix-play-v3": "play-prefix-calculation-v3",
        }
        source_format = current.get("sourceFormat")
        _need(type(source_format) is str and source_format in pairs)
        if current["calculationFormat"] == "nonplay-prefix-calculation-v1":
            _need(
                source_format == "play-prefix-play-v3"
                and set(current) == base | {"sourceFormatVersion"}
                and current["sourceFormatVersion"] == "nonplay-prefix-source-v1"
            )
        elif source_format in {"play-prefix-play-v2", "play-prefix-play-v3"}:
            _need(
                current["calculationFormat"] == pairs[source_format]
                and set(current) == base | {"sourceKind"}
            )
            allowed = (
                {"bridged-v1", "evaluated-prefix-v2"}
                if source_format == "play-prefix-play-v2"
                else {"started-initial-v3", "evaluated-prefix-v3"}
            )
            _need(current["sourceKind"] in allowed)
        else:
            _need(
                set(current) == base
                and current["calculationFormat"] == pairs[source_format]
            )
        return
    raise PlayExportSupplyError("P3旧入力経路の閉版が不正")


def p3_input_origin(
    original: str | None,
    payload: dict[str, Any],
    expected: P3SnapshotIdentity,
    *,
    target: bool,
) -> str:
    """実effective参照を有限P3版へ写し、旧originを監査として保持する。"""

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PlayExportSupplyError("P3旧入力経路のkeyが重複")
            result[key] = value
        return result

    _need(type(original) is str)
    assert isinstance(original, str)
    try:
        previous = json.loads(
            original,
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
        _origin_value(previous)
        # 過去P3版自体はappend-only監査に残し、新行JSONは通常originまでに閉じる。
        while previous["formatVersion"] == "play-export-input-origin-p3-v1":
            previous = previous["originalInputOrigin"]
        calculation = payload["calculation"]
        artifact = calculation["artifactSha256"]
        _need(
            type(artifact) is str
            and re.fullmatch(r"[a-f0-9]{64}", artifact) is not None
        )
        _need(
            payload["formatVersion"] == "play-prefix-play-v3"
            and calculation["formatVersion"] == "play-prefix-calculation-v3"
        )
        value = {
            "formatVersion": "play-export-input-origin-p3-v1",
            "operationKind": "play_change" if target else "play_input",
            "projectionKind": "p3-current",
            "sourceFormat": payload["formatVersion"],
            "calculationFormat": calculation["formatVersion"],
            "calculationArtifactSha256": artifact,
            "sourceEventId": str(expected.effective_event_id),
            "capsuleId": str(expected.capsule_id),
            "itemDigest": expected.item_digest,
            "originalInputOrigin": previous,
        }
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (KeyError, TypeError, ValueError, RecursionError):
        raise PlayExportSupplyError("P3入力経路の真正原本が不足") from None


def project_p3_direct(
    original_snapshot: Mapping[str, str | None],
    item: dict[str, Any],
    expected: P3SnapshotIdentity,
    *,
    target_d1: int,
    reference: CorrectionResultReference | None = None,
) -> dict[str, str | None]:
    """旧記録時参照を保持し、唯一の既表示helperへ訂正T1/T2を渡す。

    本関数は元capsule/receiptを発行しない。実producerは同TXの閉DBreaderを
    必須とし、この自由値の戻りを保存資格へ昇格させない。
    """
    _need(type(expected) is P3SnapshotIdentity)
    expected.__post_init__()
    _need(type(item) is dict and set(item) == _ITEM_FIELDS)
    _need(type(target_d1) is int and 1 <= target_d1)
    _need(set(original_snapshot) == set(_HEADERS))
    _need(
        all(value is None or type(value) is str for value in original_snapshot.values())
    )
    _need(item["digest"] == expected.item_digest)
    _need(
        source_fingerprint(
            {key: value for key, value in item.items() if key != "digest"}
        )
        == item["digest"]
    )
    for key, wanted in (
        ("d1", expected.d1),
        ("original_play_row_id", str(expected.original_play_row_id)),
        ("effective_event_id", str(expected.effective_event_id)),
        ("effective_play_row_id", str(expected.effective_play_row_id)),
    ):
        _need(type(item[key]) is type(wanted) and item[key] == wanted)
    _need(type(item["d2"]) is int and -(2**63) <= item["d2"] < 2**63)
    old, new = item["original_play_row"], item["play_row"]
    before_payload, payload = item["original_payload"], item["payload"]
    _need(all(type(value) is dict for value in (old, new, before_payload, payload)))
    _need(set(old) == set(new))
    _need(item["original_event_id"] == old.get("source_event_id"))
    _need(new.get("source_event_id") == str(expected.effective_event_id))
    _need(
        old.get("id") == str(expected.original_play_row_id)
        and new.get("id") == str(expected.effective_play_row_id)
    )
    _need(old.get("tenant_id") == new.get("tenant_id") == str(expected.tenant_id))
    _need(old.get("game_id") == new.get("game_id") == str(expected.game_id))
    _need(
        type(new.get("version")) is int and new["version"] == expected.play_row_version
    )
    target = expected.d1 == target_d1
    _need(item["state"] == ("unchanged" if expected.d1 < target_d1 else "corrected"))
    changed = {
        key
        for key in old
        if type(old[key]) is not type(new[key]) or old[key] != new[key]
    }
    _need(
        changed
        <= ({"id", "source_event_id", "batting_result_key"} if target else set())
    )
    _need(before_payload.get("participants") == payload.get("participants"))
    _need(item["original_play_runners"] == item["play_runners"])
    if target:
        _need(item["play_runners"] == [])
        _need(type(reference) is CorrectionResultReference)
        assert reference is not None
        reference.__post_init__()
        _need(
            (
                reference.tenant_id,
                reference.game_id,
                reference.capsule_id,
                reference.effective_event_id,
            )
            == (
                expected.tenant_id,
                expected.game_id,
                expected.capsule_id,
                expected.effective_event_id,
            )
        )
        _need(
            old.get("batting_result_key") in _RESULTS
            and new.get("batting_result_key") in _RESULTS
        )
        _need(reference.key == new["batting_result_key"])
        old_observed, new_observed = (
            before_payload.get("observations"),
            payload.get("observations"),
        )
        _need(
            type(old_observed) is dict
            and type(new_observed) is dict
            and set(old_observed) == set(new_observed)
        )
        _need(
            all(
                old_observed[key] == new_observed[key]
                for key in old_observed
                if key != "resultId"
            )
        )
        _need(old_observed.get("resultId") == old["batting_result_key"])
        _need(new_observed.get("resultId") == new["batting_result_key"])
    else:
        _need(reference is None)
        _need(before_payload.get("observations") == payload.get("observations"))
    # 元の表示/名簿/背番号/時刻/観測列を保持。生成集計の3列は同じSのSQLで供給する。
    values = {
        key: value for key, value in original_snapshot.items() if key not in _AGGREGATED
    }
    for column, value in {
        **_native_before(before_payload),
        **_native_completion(before_payload, old),
    }.items():
        _need(original_snapshot[column] == value)
    values.update(_native_before(payload))
    values.update(_native_completion(payload, new))
    values[_HEADERS[72]] = p3_input_origin(
        original_snapshot[_HEADERS[72]], payload, expected, target=target
    )
    if target:
        assert reference is not None
        values[_HEADERS[45]] = reference.display_name
    ended = payload["calculation"]["response"]["value"]["t1"]["plateAppearanceEnded"]
    _need(type(ended) is bool)
    label = plate_result_display(
        values[_HEADERS[45]],
        ended,
        _text(new["raw_error_position"]),
        original_snapshot[_HEADERS[48]],
    )
    values[_HEADERS[61]] = label
    values[_HEADERS[62]] = label
    _need(set(values) == set(_HEADERS) - _AGGREGATED)
    return values
