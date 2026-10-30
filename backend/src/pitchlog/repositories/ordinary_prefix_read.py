"""実確定prefixのreadonly再取得。writer資格・checkpointをGETで発行しない。"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from uuid import UUID

from pitchlog.db.game_state.models import Game
from pitchlog.db.game_state.rule_snapshot import (
    decode_applied_rules,
    encode_applied_rules,
)
from pitchlog.db.sync_protocol.models import OperationEvent
from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.domainrt.first_pitch import _invalid_constant, _unique_object
from pitchlog.domainrt.initial_game_roster import InitialRosterProjection
from pitchlog.repositories.game_start import _saved_start_rule_wire
from pitchlog.repositories.ordinary_order import OrdinaryOrderSummaryToken
from pitchlog.repositories.ordinary_prefix import (
    OrdinaryPrefixError,
    _verify_persisted_last_source,
    read_checkpoint_document,
)
from pitchlog.repositories.ordinary_prefix_operations import (
    OrdinaryCheckpointReadToken,
    OrdinaryHistoryPageToken,
)
from pitchlog.repositories.recorded_snapshot import (
    RecordedCalculationCandidate,
    try_read_recorded_snapshot,
)
from pitchlog.repositories.recorded_snapshot_operations import RECORDED_PLAY_ROW_COLUMNS
from pitchlog.repositories.started_read import (
    StartedGameView,
    StartedReadNotVisible,
    StartedReadRecorded,
    read_started_game,
)
from pitchlog.repositories.started_snapshot import (
    _initial_before,
    _one,
    _plain,
    _rows,
    _saved_lineup,
)
from pitchlog.repositories.started_snapshot_operations import (
    LINEUP_COLUMNS,
    StartedLineupsReadToken,
)
from pitchlog.repositories.sync_apply import _GENERATION_READ_COLUMNS
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.d4_reference import encode_d4_reference
from pitchlog.sync.first_ball_tokens import FirstBallPlayRowReadToken
from pitchlog.sync.idempotency import source_fingerprint
from pitchlog.sync.ordinary_pitch_payload import OrdinaryPitchPlayPayload
from pitchlog.sync.tokens import (
    GameLockToken,
    GameReadToken,
    OperationEventReadToken,
    RecordingGenerationLockToken,
    RecordingGenerationReadToken,
)


@dataclass(frozen=True, slots=True)
class OrdinaryPrefixView:
    """同read TXのmetadataと有限projection。HTTP型はrouterで検証する。"""

    metadata: StartedGameView
    projection: dict


def _json(raw):
    """重複/非有限/自由Python値を補修しない。"""
    if type(raw) is not str:
        raise OrdinaryPrefixError
    return json.loads(
        raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )


def _function_one(handle, token):
    """固定read関数の最大一行を厳密に取り出す。"""
    rows = handle.run_function(token).rows
    if len(rows) > 1 or any(len(row) != 1 or type(row[0]) is not str for row in rows):
        raise OrdinaryPrefixError
    return None if not rows else _json(rows[0][0])


def _public_play(row, course):
    """内部41全値確認済の行を既公開列へ写す。座標は原観測k。"""
    hidden = {
        "tenant_id",
        "hidden_at",
        "import_batch_id",
        "legacy_row_identifier",
        "migration_unverified",
        "course_x",
        "course_y",
    }
    if set(row) != set(RECORDED_PLAY_ROW_COLUMNS):
        raise OrdinaryPrefixError
    value = {key: member for key, member in row.items() if key not in hidden}
    value["course"] = course
    return value


def _cursor(value):
    """cursorは権限でなく版付き位置。正準base64urlだけ受ける。"""
    if type(value) is not str or not 1 <= len(value) <= 2048:
        raise OrdinaryPrefixError
    raw = base64.urlsafe_b64decode(value + "=" * ((-len(value)) % 4)).decode("utf-8")
    if base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=") != value:
        raise OrdinaryPrefixError
    return _json(raw)


def read_ordinary_prefix(handle, game_id, *, limit=25, cursor=None):
    """現在世代の実point原本と有限pageだけを返す。0/旧1も暗黙書込しない。"""
    if (
        type(handle) is not _TenantTransaction
        or type(game_id) is not UUID
        or type(limit) is not int
        or not 1 <= limit <= 100
    ):
        raise OrdinaryPrefixError
    tenant = handle._bound_tenant_id

    def run(token):
        return handle.run(token)

    columns = tuple(Game.__table__.c.keys())
    locked = _rows(run(GameLockToken(game_id)), columns)
    games = _rows(run(GameReadToken(game_id)), columns)
    if not locked and not games:
        return StartedReadNotVisible()
    if len(games) != 1 or locked != games:
        raise OrdinaryPrefixError
    game = games[0]
    if game["tenant_id"] != tenant or game["id"] != game_id:
        raise OrdinaryPrefixError
    if game["status"] != "in_progress" or any(
        game[key] is not None for key in ("trashed_at", "hidden_at", "import_batch_id")
    ):
        return StartedReadNotVisible()
    current = _one(run(RecordingGenerationReadToken(game_id)), _GENERATION_READ_COLUMNS)
    generation = current["generation"]
    if type(generation) is not int or not 0 < generation < 2**63:
        raise OrdinaryPrefixError
    locked_generation = _one(
        run(RecordingGenerationLockToken(game_id, generation)), _GENERATION_READ_COLUMNS
    )
    n = current["confirmed_watermark"]
    if (
        locked_generation != current
        or current["tenant_id"] != tenant
        or current["game_id"] != game_id
        or current["kind"] != "normal"
        or any(
            current[key] is not None
            for key in ("revoked_at", "retired_at", "import_batch_id")
        )
        or type(n) is not int
        or n < 0
        or current["applied_prefix"] != n
    ):
        raise OrdinaryPrefixError
    d4 = encode_d4_reference(tenant, game_id, generation)
    summary = _function_one(handle, OrdinaryOrderSummaryToken(game_id))
    if (
        type(summary) is not dict
        or set(summary) != {"tail", "duplicate", "recovery_generation"}
        or type(summary["duplicate"]) is not bool
        or summary["duplicate"]
    ):
        raise OrdinaryPrefixError
    epoch = summary["recovery_generation"]
    if type(epoch) is not int or not 0 < epoch < 2**63:
        raise OrdinaryPrefixError
    tail = summary["tail"]
    if (n == 0 and tail is not None) or (
        n > 0
        and (
            type(tail) is not dict
            or tail.get("d1") != n
            or tail.get("generation") != generation
            or tail.get("game_id") != str(game_id)
            or tail.get("tenant_id") != str(tenant)
            or type(tail.get("d2")) is not int
            or tail["d2"] < 0
        )
    ):
        raise OrdinaryPrefixError
    next_d2 = 1 if tail is None else tail["d2"] + 1000
    # DB bigintの範囲を維持。FE能力外はDTOcodecが閉じる。丸め/再採番しない。
    if next_d2 >= 2**63 or n + 1 >= 2**63:
        raise OrdinaryPrefixError
    stored = _function_one(handle, OrdinaryCheckpointReadToken(game_id, generation))
    policy = {
        "version": "ordinary-append-v1",
        "first_d2": "1",
        "d2_gap": "1000",
        "max_d2": "9007199254740991",
    }
    projection = {
        "next_position": {"d1": str(n + 1), "d2": str(next_d2)},
        "recovery_generation": str(epoch),
        "append_policy": policy,
    }
    if stored is None or stored.get("kind") == "first-ball-save":
        if cursor is not None or n > 1:
            return StartedReadRecorded()
        original = read_started_game(handle, game_id)
        if n == 0:
            if type(original) is not StartedGameView or stored is not None:
                raise OrdinaryPrefixError
            projection.update(
                after=original.before,
                prefix_ref={
                    "version": "1",
                    "tenantId": str(tenant),
                    "gameId": str(game_id),
                    "generation": d4,
                    "length": "0",
                },
                rules=_saved_start_rule_wire(original.applied_rules),
                t2=None,
                last_entry=None,
                checkpoint_anchor=None,
                last_saved_at=original.started_at,
                page={"items": [], "next_cursor": None},
            )
            return OrdinaryPrefixView(original, projection)
        candidate = try_read_recorded_snapshot(handle, game_id)
        if (
            type(candidate) is not RecordedCalculationCandidate
            or type(stored) is not dict
            or set(stored) != {"kind", "source_event_id", "saved_at"}
            or stored["source_event_id"] != str(candidate.source_event_id)
            or not stored["saved_at"]
        ):
            raise OrdinaryPrefixError
        from dataclasses import fields

        metadata = StartedGameView(
            **{
                field.name: getattr(original, field.name)
                for field in fields(StartedGameView)
            }
        )
        entry = candidate.response.value.t1.history_context[-1]
        raw_entry = entry.model_dump(mode="json", by_alias=True, exclude_unset=True)
        row = dict(
            zip(RECORDED_PLAY_ROW_COLUMNS, candidate.verified_play_row, strict=True)
        )
        projection.update(
            after=candidate.response.value.t1.after,
            prefix_ref={
                "version": "1",
                "tenantId": str(tenant),
                "gameId": str(game_id),
                "generation": d4,
                "length": "1",
            },
            rules=candidate.request.rules,
            t2=candidate.response.value.t2,
            last_entry=raw_entry,
            checkpoint_anchor=None,
            last_saved_at=stored["saved_at"],
            page={
                "items": [
                    {
                        "play_row": _public_play(
                            row, candidate.payload.v7.observations.course
                        ),
                        "history_entry": raw_entry,
                    }
                ],
                "next_cursor": None,
            },
        )
        return OrdinaryPrefixView(metadata, projection)
    if (
        type(stored) is not dict
        or set(stored) != {"kind", "row"}
        or stored["kind"] != "checkpoint"
        or type(stored["row"]) is not dict
    ):
        raise OrdinaryPrefixError
    row = stored["row"]
    doc = read_checkpoint_document(_canonical_json(row["content"]))
    for key, expected in {
        "tenant_id": str(tenant),
        "game_id": str(game_id),
        "internal_generation": generation,
        "id": doc.id,
        "revision": int(doc.revision),
        "history_version": int(doc.history_version),
        "recovery_generation": epoch,
        "confirmed_watermark": n,
        "applied_watermark": n,
        "content_digest": doc.content_digest,
        "state": "current",
    }.items():
        if type(row[key]) is not type(expected) or row[key] != expected:
            raise OrdinaryPrefixError
    if (
        doc.wire_d4 != d4
        or int(doc.confirmed_watermark) != n
        or doc.prefix_ref.tenant_id != str(tenant)
        or doc.prefix_ref.game_id != str(game_id)
        or row.get("saved_at") is None
        or source_fingerprint(row["roster"]) != doc.roster_digest
    ):
        raise OrdinaryPrefixError
    roster = InitialRosterProjection.model_validate_json(_canonical_json(row["roster"]))
    from pitchlog.repositories.first_ball_operations import PLAY_ROW_COLUMNS

    if doc.last_source is None:
        raise OrdinaryPrefixError
    last_play = _one(
        run(FirstBallPlayRowReadToken(game_id, UUID(doc.last_source.id))),
        PLAY_ROW_COLUMNS,
    )
    _verify_persisted_last_source(
        run, tenant, game_id, doc, roster, last_play, row.get("last_play_row")
    )
    if tail["id"] != doc.last_source.id or tail["d2"] != int(doc.last_source.d2):
        return StartedReadRecorded()
    saved_lineups = _rows(run(StartedLineupsReadToken(game_id)), LINEUP_COLUMNS)
    if len(saved_lineups) != 2 or any(
        item["tenant_id"] != tenant or item["game_id"] != game_id
        for item in saved_lineups
    ):
        raise OrdinaryPrefixError
    lineups = tuple(_saved_lineup(item) for item in saved_lineups)
    sides = tuple(
        next(item for item in lineups if item.team_id == game[key])
        for key in ("away_team_record_id", "home_team_record_id")
    )
    metadata = StartedGameView(
        **{
            key: game[key]
            for key in (
                "scheduled_at",
                "game_type_key",
                "tournament_key",
                "away_team_record_id",
                "home_team_record_id",
                "plate_umpire",
                "section_label",
                "week_label",
                "day_label",
                "game_number_label",
                "started_at",
            )
        },
        game_id=game_id,
        applied_rules=encode_applied_rules(
            decode_applied_rules(_plain(game["applied_rules"]))
        ),
        lineups=(sides[0], sides[1]),
        roster=roster,
        before=_initial_before(),
        current_d4=d4,
    )
    anchor = {
        "id": doc.id,
        "revision": doc.revision,
        "history_version": doc.history_version,
    }
    position = (0, 0, UUID(int=0))
    cursor_scope = {
        "version": "1",
        "tenant": str(tenant),
        "game": str(game_id),
        "anchor": anchor,
        "watermark": str(n),
    }
    if cursor is not None:
        supplied = _cursor(cursor)
        if (
            type(supplied) is not dict
            or set(supplied) != {*cursor_scope, "position"}
            or any(supplied[key] != value for key, value in cursor_scope.items())
        ):
            raise OrdinaryPrefixError
        point = supplied["position"]
        if (
            type(point) is not list
            or len(point) != 3
            or any(type(value) is not str for value in point)
        ):
            raise OrdinaryPrefixError
        position = (int(point[0]), int(point[1]), UUID(point[2]))
        if [str(value) for value in position] != point:
            raise OrdinaryPrefixError
    page_rows = handle.run_function(
        OrdinaryHistoryPageToken(
            game_id,
            generation,
            int(doc.history_version),
            UUID(doc.id),
            int(doc.revision),
            n,
            *position,
            limit,
        )
    ).rows
    if len(page_rows) > limit + 1:
        raise OrdinaryPrefixError
    items = []
    last_point = None
    for packet in page_rows[:limit]:
        if len(packet) != 1:
            raise OrdinaryPrefixError
        item = _json(packet[0])
        if type(item) is not dict or set(item) != {
            "history",
            "event",
            "play_row",
            "expected_play_row",
        }:
            raise OrdinaryPrefixError
        h, e, p = item["history"], item["event"], item["play_row"]
        if (
            h["tenant_id"] != str(tenant)
            or h["game_id"] != str(game_id)
            or h["internal_generation"] != generation
            or h["history_version"] != int(doc.history_version)
            or e["id"] != h["source_event_id"]
            or p["source_event_id"] != e["id"]
            or e["d1"] != h["d1"]
            or e["d2"] != h["d2"]
        ):
            raise OrdinaryPrefixError
        if (
            h["d1"] == 1
            and e["payload"].get("formatVersion") != "ordinary-pitch-play-v1"
        ):
            # legacy全値はbootstrap時/DBguard、pageの実stampはbridgeで確認。
            from pitchlog.sync.first_ball_payload import FirstBallPlayPayload

            legacy = FirstBallPlayPayload.model_validate_json(
                _canonical_json(e["payload"])
            )
            course = legacy.observations.course
        else:
            payload = OrdinaryPitchPlayPayload.model_validate_json(
                _canonical_json(e["payload"])
            )
            from pitchlog.sync.ordinary_pitch_physical import (
                ordinary_pitch_physical_row,
            )

            expected = ordinary_pitch_physical_row(
                payload,
                tenant_id=tenant,
                game_id=game_id,
                source_event_id=UUID(e["id"]),
                row_id=UUID(p["id"]),
                play_number=p["play_number"],
            )
            if (
                item["expected_play_row"] != expected
                or p != expected
                or h["entry"]
                != payload.calculation.response.value.new_history_entry.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                )
            ):
                raise OrdinaryPrefixError
            course = payload.observations.course
        point = (h["d1"], h["d2"], UUID(h["source_event_id"]))
        if point <= position or (last_point is not None and point <= last_point):
            raise OrdinaryPrefixError
        last_point = point
        items.append({"play_row": _public_play(p, course), "history_entry": h["entry"]})
    next_cursor = None
    if len(page_rows) > limit:
        if last_point is None:
            raise OrdinaryPrefixError
        raw = _canonical_json(
            {**cursor_scope, "position": [str(value) for value in last_point]}
        )
        next_cursor = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    last_event = _one(
        run(OperationEventReadToken(game_id, generation, n)),
        tuple(OperationEvent.__table__.c.keys()),
    )
    from pitchlog.sync.idempotency import _json_value

    last_payload = OrdinaryPitchPlayPayload.model_validate_json(
        _canonical_json(_json_value(last_event["payload"]))
    )
    projection.update(
        after=doc.after,
        prefix_ref=doc.prefix_ref,
        rules=doc.rules,
        t2=doc.t2,
        last_entry=last_payload.calculation.response.value.new_history_entry,
        checkpoint_anchor=anchor,
        last_saved_at=row["saved_at"],
        page={"items": items, "next_cursor": next_cursor},
    )
    return OrdinaryPrefixView(metadata, projection)
