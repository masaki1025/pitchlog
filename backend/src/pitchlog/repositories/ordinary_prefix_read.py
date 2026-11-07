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


def read_ordinary_prefix(
    handle, game_id, *, limit=25, cursor=None, _play_prefix=False, _lineup_prefix=False
):
    """現在世代の実point原本と有限pageだけを返す。0/旧1も暗黙書込しない。"""
    if (
        type(handle) is not _TenantTransaction
        or type(game_id) is not UUID
        or type(limit) is not int
        or not 1 <= limit <= 100
    ):
        raise OrdinaryPrefixError
    tenant = handle._bound_tenant_id
    from pitchlog.repositories.transaction import started_snapshot_read_mode

    readonly = started_snapshot_read_mode(handle)

    def run(token):
        return handle.run(token)

    columns = tuple(Game.__table__.c.keys())
    locked = None if readonly else _rows(run(GameLockToken(game_id)), columns)
    games = _rows(run(GameReadToken(game_id)), columns)
    if not games and (readonly or not locked):
        return StartedReadNotVisible()
    if len(games) != 1 or (not readonly and locked != games):
        raise OrdinaryPrefixError
    game = games[0]
    if game["tenant_id"] != tenant or game["id"] != game_id:
        raise OrdinaryPrefixError
    from pitchlog.repositories.game_lifecycle import _finished_lifecycle_read_allowed

    if (
        game["status"] != "in_progress"
        and not (
            game["status"] == "finished"
            and _finished_lifecycle_read_allowed(handle, game_id)
        )
    ) or any(
        game[key] is not None for key in ("trashed_at", "hidden_at", "import_batch_id")
    ):
        return StartedReadNotVisible()
    current = _one(run(RecordingGenerationReadToken(game_id)), _GENERATION_READ_COLUMNS)
    generation = current["generation"]
    if type(generation) is not int or not 0 < generation < 2**63:
        raise OrdinaryPrefixError
    locked_generation = (
        None
        if readonly
        else _one(
            run(RecordingGenerationLockToken(game_id, generation)),
            _GENERATION_READ_COLUMNS,
        )
    )
    n = current["confirmed_watermark"]
    if (
        (not readonly and locked_generation != current)
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
    if _lineup_prefix:
        probe = _function_one(handle, OrdinaryCheckpointReadToken(game_id, generation))
        if (
            type(probe) is dict
            and probe.get("kind") == "checkpoint"
            and probe.get("row", {}).get("content", {}).get("formatVersion")
            == "nonplay-prefix-checkpoint-v1"
        ):
            return _read_nonplay_projection(
                handle,
                game_id,
                tenant,
                game,
                generation,
                epoch,
                n,
                d4,
                probe["row"],
                tail,
                limit,
                cursor,
            )
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
    if _play_prefix or _lineup_prefix:
        from pitchlog.authz.terminal_pitch_product import require_registered_product
        from pitchlog.sync.terminal_pitch_tokens import PlayPrefixCheckpointReadToken

        require_registered_product(
            mode="play-prefix-play-v3" if _lineup_prefix else "play-prefix-play-v2"
        )
        read_token = PlayPrefixCheckpointReadToken(game_id, generation)
    else:
        read_token = OrdinaryCheckpointReadToken(game_id, generation)
    stored = _function_one(handle, read_token)
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
    if _lineup_prefix:
        return _read_lineup_projection(
            handle,
            game_id,
            tenant,
            game,
            generation,
            epoch,
            n,
            d4,
            stored,
            projection,
            limit,
            cursor,
        )
    if stored is None or stored.get("kind") == "first-ball-save":
        if cursor is not None or n > 1:
            return StartedReadRecorded()
        original = (
            None if _play_prefix and n == 1 else read_started_game(handle, game_id)
        )
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
            if _play_prefix:
                _add_bridge_preview(
                    handle,
                    tenant,
                    game_id,
                    generation,
                    epoch,
                    n,
                    projection,
                    original,
                    None,
                )
            return OrdinaryPrefixView(original, projection)
        candidate = (
            try_read_recorded_snapshot(handle, game_id, play_prefix_compat=True)
            if _play_prefix
            else try_read_recorded_snapshot(handle, game_id)
        )
        if (
            type(candidate) is not RecordedCalculationCandidate
            or type(stored) is not dict
            or set(stored) != {"kind", "source_event_id", "saved_at"}
            or stored["source_event_id"] != str(candidate.source_event_id)
            or not stored["saved_at"]
        ):
            raise OrdinaryPrefixError
        from dataclasses import fields

        if _play_prefix:
            metadata = _prefix_metadata(
                game, game_id, d4, candidate.lineups, candidate.roster
            )
        else:
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
        if _play_prefix:
            _add_bridge_preview(
                handle,
                tenant,
                game_id,
                generation,
                epoch,
                n,
                projection,
                metadata,
                candidate,
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
    is_v2 = _play_prefix and row["content"].get("version") == "2"
    if is_v2:
        from pitchlog.repositories.play_prefix import (
            _verify_source_evidence,
            read_play_prefix_document,
        )

        doc = read_play_prefix_document(_canonical_json(row["content"]))
        _verify_source_evidence(row, bridge=False)
    else:
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
    if is_v2:
        _verify_v2_read_last(handle, tenant, game_id, doc, last_play, row)
    else:
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
    metadata = _prefix_metadata(game, game_id, d4, sides, roster)
    anchor = {
        "id": doc.id,
        "revision": doc.revision,
        "history_version": doc.history_version,
    }
    position = (0, 0, UUID(int=0))
    cursor_scope = {
        "version": "2" if is_v2 else "1",
        "tenant": str(tenant),
        "game": str(game_id),
        "anchor": anchor,
        "watermark": str(n),
    }
    if is_v2:
        cursor_scope["wire_head"] = doc.prefix_ref.model_dump(
            mode="json", by_alias=True
        )
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
    if is_v2:
        from pitchlog.repositories.play_prefix import PlayPrefixDocument

        assert isinstance(doc, PlayPrefixDocument)
        from pitchlog.repositories.started_snapshot_read_operations import (
            StartedPlayPrefixHistoryPageToken,
        )
        from pitchlog.sync.terminal_pitch_tokens import PlayPrefixHistoryPageToken

        page_token_type = (
            StartedPlayPrefixHistoryPageToken
            if readonly
            else PlayPrefixHistoryPageToken
        )
        page_token = page_token_type(
            game_id,
            generation,
            int(doc.history_version),
            UUID(doc.prefix_ref.checkpoint.id),
            int(doc.revision),
            int(doc.prefix_ref.history_version),
            n,
            *position,
            limit,
        )
        page_rows = handle.run_function(page_token).rows
    else:
        from pitchlog.repositories.started_snapshot_read_operations import (
            StartedOrdinaryHistoryPageToken,
        )

        page_token_type = (
            StartedOrdinaryHistoryPageToken if readonly else OrdinaryHistoryPageToken
        )
        page_rows = handle.run_function(
            page_token_type(
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
            *({"play_runners", "expected_play_runners"} if is_v2 else set()),
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
        if e["payload"].get("formatVersion") == "play-prefix-play-v2" and is_v2:
            payload = _verify_v2_read_packet(item, tenant, game_id)
            course = payload.observations.course
        elif (
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
        value = {"play_row": _public_play(p, course), "history_entry": h["entry"]}
        if _play_prefix:
            value["play_runners"] = item.get("play_runners", [])
        items.append(value)
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

    if is_v2:
        from pitchlog.sync.terminal_pitch_payload import TerminalPitchPlayPayload

        last_type = TerminalPitchPlayPayload
    else:
        last_type = OrdinaryPitchPlayPayload
    last_payload = last_type.model_validate_json(
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
    if _play_prefix and not is_v2:
        projection["last_source"] = {
            "eventId": doc.last_source.id,
            "d5": doc.last_source.d5,
            "playId": str(last_play["id"]),
        }
        projection["prior_artifact_sha256"] = doc.artifact_sha256
        projection["pa_start_source"] = {"kind": "started-game", "id": str(game_id)}
        projection["bridge_checkpoint"] = {
            "id": doc.id,
            "revision": doc.revision,
            "digest": doc.content_digest,
        }
    if is_v2:
        from pitchlog.repositories.play_prefix import PlayPrefixDocument

        assert isinstance(doc, PlayPrefixDocument)
        projection.update(
            runners=doc.runners,
            participants=doc.participants,
            storage_anchor=doc.storage_anchor,
            bridge_origin=doc.bridge_origin,
            last_source={
                "eventId": doc.last_source.id,
                "d5": doc.last_source.d5,
                "playId": str(last_play["id"]),
            },
            prior_artifact_sha256=doc.artifact_sha256,
            pa_start_source=doc.pa_start_source,
        )
    return OrdinaryPrefixView(metadata, projection)


def read_play_prefix(handle, game_id, *, limit=25, cursor=None):
    """既GETの別projectionだけを新modeへ結線し、v1応答は保持する。"""
    return read_ordinary_prefix(
        handle, game_id, limit=limit, cursor=cursor, _play_prefix=True
    )


def _evaluate_v2_payload(raw):
    """保存済要求を独立実artifactへ一回渡し全応答/差分を照合する。"""
    from pitchlog.domainrt.play_prefix_continuation import (
        PlayPrefixSuccess,
        evaluate_play_prefix_continuation,
    )
    from pitchlog.sync.terminal_pitch_payload import (
        TerminalPitchPlayPayload,
        verify_play_prefix_seal,
    )

    payload = TerminalPitchPlayPayload.model_validate_json(_canonical_json(raw))
    verify_play_prefix_seal(payload.calculation)
    actual = evaluate_play_prefix_continuation(payload.calculation.request)
    if type(actual) is not PlayPrefixSuccess or actual != payload.calculation.response:
        raise OrdinaryPrefixError
    return payload


def _verify_v2_read_packet(item, tenant, game_id, *, lineup=False):
    """独立再評価/取消差分/41列/runner10列を全値比較する。"""
    from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
    from pitchlog.sync.terminal_pitch_projection import runner_physical_rows

    h, e, p = item["history"], item["event"], item["play_row"]
    payload = (
        _evaluate_lineup_payload(e["payload"])
        if lineup
        else _evaluate_v2_payload(e["payload"])
    )
    q, value = payload.calculation.request, payload.calculation.response.value
    expected = pitch_physical_row(
        payload.observations,
        payload.participants,
        q.t1.result_id,
        tenant_id=tenant,
        game_id=game_id,
        source_event_id=UUID(e["id"]),
        row_id=UUID(p["id"]),
        play_number=p["play_number"],
    )
    runners = runner_physical_rows(
        q.source.runners,
        t1=value.t1,
        t1_input=q.t1,
        tenant_id=tenant,
        play_id=UUID(p["id"]),
    )
    if (
        p != expected
        or item["expected_play_row"] != expected
        or q.play_identity.event_id != e["id"]
        or q.play_identity.play_id != p["id"]
        or q.play_identity.d5 != e["d5"]
        or h["entry"]
        != value.new_history_entry.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        )
        or e["state_diff"]
        != value.new_history_entry.difference.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        )
        or item["play_runners"] != runners
        or item["expected_play_runners"] != runners
    ):
        raise OrdinaryPrefixError
    return payload


def _verify_v2_read_last(handle, tenant, game_id, doc, play, row):
    """現pointの実原本/ledger/消費印と独立再評価を結合する。"""
    from pitchlog.db.sync_protocol.models import IdempotencyLedger
    from pitchlog.sync.tokens import IdempotencyLedgerReadToken

    event = _one(
        handle.run(
            OperationEventReadToken(
                game_id, int(doc.internal_generation), int(doc.last_source.d1)
            )
        ),
        tuple(OperationEvent.__table__.c.keys()),
    )
    ledger = _one(
        handle.run(IdempotencyLedgerReadToken(UUID(doc.last_source.d5))),
        tuple(IdempotencyLedger.__table__.c.keys()),
    )
    from pitchlog.sync.idempotency import _json_value

    payload = _evaluate_v2_payload(_json_value(event["payload"]))
    value = payload.calculation.response.value
    expected = doc.projection_snapshot.play_row
    actual = {k: str(v) if type(v) is UUID else v for k, v in play.items()}
    if (
        event["tenant_id"] != tenant
        or event["game_id"] != game_id
        or event["id"] != UUID(doc.last_source.id)
        or event["d5"] != UUID(doc.last_source.d5)
        or event["ledger_kind"] != "accepted"
        or event["is_tombstone"]
        or event["replaced_at"] is not None
        or event["retired_at"] is not None
        or ledger["tenant_id"] != tenant
        or ledger["kind"] != "accepted"
        or ledger["source_fingerprint"] != doc.last_source.source_fingerprint
        or ledger["retired_at"] is not None
        or ledger["import_batch_id"] is not None
        or actual != expected
        or row["last_play_row"] != expected
        or row["last_play_runners"] != list(doc.projection_snapshot.play_runners)
        or value.next_prefix_ref != doc.prefix_ref
        or value.t1.after != doc.after
        or value.t2 != doc.t2
        or value.runners != doc.runners
        or value.participants != doc.participants
        or _json_value(event["state_diff"])
        != value.new_history_entry.difference.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        )
    ):
        raise OrdinaryPrefixError


def _add_bridge_preview(
    handle, tenant, game_id, generation, epoch, n, projection, metadata, candidate
):
    """実読取だけから未保存anchor提案を描画する。保存資格/一回消費は別に必要。"""
    from uuid import uuid5

    from pitchlog.db.sync_protocol.models import IdempotencyLedger
    from pitchlog.domainrt.first_pitch_continuation import SavedRuleWire
    from pitchlog.domainrt.host import open_domain_host
    from pitchlog.repositories.ordinary_prefix import bootstrap_checkpoint_document
    from pitchlog.sync.tokens import IdempotencyLedgerReadToken

    last = None
    if candidate is not None:
        event = _one(
            handle.run(OperationEventReadToken(game_id, generation, 1)),
            tuple(OperationEvent.__table__.c.keys()),
        )
        ledger = _one(
            handle.run(IdempotencyLedgerReadToken(candidate.d5)),
            tuple(IdempotencyLedger.__table__.c.keys()),
        )
        last = {
            "id": str(candidate.source_event_id),
            "tenant_id": str(tenant),
            "game_id": str(game_id),
            "generation": str(generation),
            "d1": "1",
            "d2": str(event["d2"]),
            "d5": str(candidate.d5),
            "source_fingerprint": ledger["source_fingerprint"],
            "event_fingerprint": ledger["source_fingerprint"],
        }
        digest = candidate.payload.v7.calculation.artifact_sha256
    else:
        with open_domain_host() as host:
            digest = host.artifact_sha256
    rules = projection["rules"]
    if type(rules) is not SavedRuleWire:
        rules = SavedRuleWire.model_validate_json(_canonical_json(rules))
    doc = bootstrap_checkpoint_document(
        tenant=tenant,
        game_id=game_id,
        d4=metadata.current_d4,
        generation=generation,
        epoch=epoch,
        watermark=n,
        last=last,
        length=str(n),
        depth=str(n),
        after=projection["after"],
        rules=rules,
        roster=metadata.roster,
        t2=projection["t2"],
        artifact_sha256=digest,
        anchor_id=uuid5(game_id, "play-prefix-bootstrap:" + metadata.current_d4),
    )
    projection["last_source"] = (
        None
        if candidate is None
        else {
            "eventId": str(candidate.source_event_id),
            "d5": str(candidate.d5),
            "playId": str(
                dict(
                    zip(
                        RECORDED_PLAY_ROW_COLUMNS,
                        candidate.verified_play_row,
                        strict=True,
                    )
                )["id"]
            ),
        }
    )
    projection["prior_artifact_sha256"] = doc.artifact_sha256
    projection["pa_start_source"] = {"kind": "started-game", "id": str(game_id)}
    projection["bridge_checkpoint"] = {
        "id": doc.id,
        "revision": doc.revision,
        "digest": doc.content_digest,
    }


def _prefix_metadata(game, game_id, d4, sides, roster):
    """実game/保存lineupから共通DTO値を写す。数学/現在名簿の補完はしない。"""
    return StartedGameView(
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


def read_lineup_prefix(handle, game_id, *, limit=25, cursor=None):
    """旧DTO/旧readerを拡張せず、実v3だけを別projectionで読む。"""
    return read_ordinary_prefix(
        handle, game_id, limit=limit, cursor=cursor, _lineup_prefix=True
    )


def _evaluate_lineup_payload(raw):
    """実保存要求を一回評価し、自己seal/V7/V8全値と照合する。"""
    from pitchlog.domainrt.lineup_play_prefix_continuation import (
        evaluate_lineup_prefix_continuation,
    )
    from pitchlog.sync.terminal_pitch_payload import (
        LineupPitchPlayPayload,
        read_lineup_pitch_payload,
    )

    payload = LineupPitchPlayPayload.model_validate_json(_canonical_json(raw))
    from pitchlog.sync.terminal_pitch_payload import LineupPitchCalculation

    if type(payload.calculation) is not LineupPitchCalculation:
        raise OrdinaryPrefixError
    actual = evaluate_lineup_prefix_continuation(payload.calculation.request)
    if _canonical_json(
        actual.model_dump(mode="json", by_alias=True, exclude_unset=True)
    ) != _canonical_json(
        payload.calculation.response.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        )
    ):
        raise OrdinaryPrefixError
    difference = payload.calculation.response.value.new_history_entry.difference
    return read_lineup_pitch_payload(
        _canonical_json(raw),
        difference.model_dump_json(by_alias=True, exclude_unset=True),
        expected_calculation=payload.calculation,
    )


def _read_lineup_projection(
    handle,
    game_id,
    tenant,
    game,
    generation,
    epoch,
    n,
    d4,
    stored,
    projection,
    limit,
    cursor,
):
    """Actual zero/native v3に限定し、最後の原本と有界pageを別々に確認する。"""
    from pitchlog.domainrt.host import open_domain_host
    from pitchlog.domainrt.lineup_play_prefix_continuation import SourcePosition
    from pitchlog.domainrt.lineup_prefix_source import lineup_from_actual_roster
    from pitchlog.repositories.play_prefix import (
        _initial_lineup_document,
        _lineup_started_origin,
        _read_native_lineup_head,
        read_lineup_prefix_document,
    )
    from pitchlog.repositories.started_snapshot import read_initial_started_snapshot
    from pitchlog.sync.terminal_pitch_tokens import PlayPrefixHistoryPageToken

    origin = _lineup_started_origin(handle, game_id, generation)
    position = SourcePosition(
        d1=projection["next_position"]["d1"],
        d2=projection["next_position"]["d2"],
        appliedWatermark=str(n),
    )
    if n == 0:
        if stored is not None or cursor is not None:
            raise OrdinaryPrefixError
        initial = read_initial_started_snapshot(handle, game_id)
        with open_domain_host() as host:
            doc, source = _initial_lineup_document(
                initial, origin, d4, epoch, host.artifact_sha256, position
            )
        metadata = read_started_game(handle, game_id)
        if type(metadata) is not StartedGameView:
            raise OrdinaryPrefixError
        projection.update(
            after=doc.after,
            prefix_ref=doc.prefix_ref,
            rules=doc.rules,
            t2=None,
            last_entry=None,
            last_source=None,
            prior_artifact_sha256=doc.artifact_sha256,
            pa_start_source=doc.pa_start_source,
            lineup=doc.lineup,
            roster_digest=doc.roster_digest,
            runners=doc.runners,
            participants=doc.participants,
            checkpoint_anchor=None,
            storage_anchor=None,
            last_saved_at=initial.started_at,
            page={"items": [], "next_cursor": None},
        )
        return OrdinaryPrefixView(metadata, projection)
    if (
        type(stored) is not dict
        or set(stored) != {"kind", "row"}
        or stored["kind"] != "checkpoint"
        or type(stored["row"]) is not dict
        or stored["row"].get("content", {}).get("version") != "3"
    ):
        raise OrdinaryPrefixError
    row = stored["row"]
    doc = read_lineup_prefix_document(_canonical_json(row["content"]))
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
        if type(row.get(key)) is not type(expected) or row[key] != expected:
            raise OrdinaryPrefixError
    if (
        doc.source_origin.event_id != origin
        or doc.wire_d4 != d4
        or doc.prefix_ref.tenant_id != str(tenant)
        or doc.prefix_ref.game_id != str(game_id)
        or row.get("saved_at") is None
        or source_fingerprint(row["roster"]) != doc.roster_source_digest
    ):
        raise OrdinaryPrefixError
    roster = InitialRosterProjection.model_validate_json(_canonical_json(row["roster"]))
    if lineup_from_actual_roster(roster) != doc.lineup:
        raise OrdinaryPrefixError
    from pitchlog.repositories.past_correction_current import (
        PastCorrectionCurrentUnavailable,
        verify_p3_current_packet,
    )
    from pitchlog.repositories.past_correction_current_paged import (
        read_verified_p3_paged_current,
    )
    from pitchlog.repositories.past_correction_right import _ReadP3CurrentToken

    after_d1 = 0
    if cursor is not None:
        supplied = _cursor(cursor)
        if type(supplied) is dict and "after_d1" in supplied:
            if type(supplied["after_d1"]) is not int:
                raise OrdinaryPrefixError
            after_d1 = supplied["after_d1"]
    try:
        paged = read_verified_p3_paged_current(
            handle,
            game_id,
            generation,
            selected_after_d1=after_d1,
            selected_limit=min(limit, 25),
        )
    except PastCorrectionCurrentUnavailable:
        raise OrdinaryPrefixError from None
    p3_packet = (
        None
        if paged is not None
        else _function_one(handle, _ReadP3CurrentToken(game_id, generation))
    )
    if paged is None and (
        p3_packet is None or p3_packet.get("kind") not in {"none", "p3-current"}
    ):
        raise OrdinaryPrefixError
    if paged is not None or (
        p3_packet is not None and p3_packet["kind"] == "p3-current"
    ):
        from pitchlog.repositories.play_prefix import _verify_source_evidence

        _verify_source_evidence(row, bridge=False)
        if row["source_evidence"]["non_play_count"] != 0:
            raise OrdinaryPrefixError
        try:
            verified = (
                paged
                if paged is not None
                else verify_p3_current_packet(
                    p3_packet, tenant=tenant, game=game_id, generation=generation
                )
            )
        except PastCorrectionCurrentUnavailable:
            raise OrdinaryPrefixError from None
        if verified.checkpoint != doc:
            raise OrdinaryPrefixError
        saved = _rows(handle.run(StartedLineupsReadToken(game_id)), LINEUP_COLUMNS)
        if len(saved) != 2 or any(
            item["tenant_id"] != tenant or item["game_id"] != game_id for item in saved
        ):
            raise OrdinaryPrefixError
        lineups = tuple(_saved_lineup(item) for item in saved)
        sides = tuple(
            next(item for item in lineups if item.team_id == game[key])
            for key in ("away_team_record_id", "home_team_record_id")
        )
        metadata = _prefix_metadata(game, game_id, d4, sides, roster)
        return _read_p3_lineup_projection(
            verified, metadata, projection, row, limit=limit, cursor=cursor
        )
    last_payload, _ = _read_native_lineup_head(handle, game_id, tenant, row, doc)
    _evaluate_lineup_payload(
        last_payload.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )
    saved = _rows(handle.run(StartedLineupsReadToken(game_id)), LINEUP_COLUMNS)
    if len(saved) != 2 or any(
        item["tenant_id"] != tenant or item["game_id"] != game_id for item in saved
    ):
        raise OrdinaryPrefixError
    lineups = tuple(_saved_lineup(item) for item in saved)
    sides = tuple(
        next(item for item in lineups if item.team_id == game[key])
        for key in ("away_team_record_id", "home_team_record_id")
    )
    metadata = _prefix_metadata(game, game_id, d4, sides, roster)
    anchor = {
        "id": doc.id,
        "revision": doc.revision,
        "history_version": doc.history_version,
    }
    scope = {
        "version": "3",
        "tenant": str(tenant),
        "game": str(game_id),
        "anchor": anchor,
        "wire_head": doc.prefix_ref.model_dump(mode="json", by_alias=True),
        "watermark": str(n),
        "recovery_generation": str(epoch),
    }
    point = (0, 0, UUID(int=0))
    if cursor is not None:
        supplied = _cursor(cursor)
        if (
            type(supplied) is not dict
            or set(supplied) != {*scope, "position"}
            or any(
                _canonical_json(supplied[key]) != _canonical_json(value)
                for key, value in scope.items()
            )
        ):
            raise OrdinaryPrefixError
        raw = supplied["position"]
        if (
            type(raw) is not list
            or len(raw) != 3
            or any(type(x) is not str for x in raw)
        ):
            raise OrdinaryPrefixError
        point = (int(raw[0]), int(raw[1]), UUID(raw[2]))
        if [str(x) for x in point] != raw:
            raise OrdinaryPrefixError
    from pitchlog.repositories.started_snapshot_read_operations import (
        StartedPlayPrefixHistoryPageToken,
    )
    from pitchlog.repositories.transaction import started_snapshot_read_mode

    page_token_type = (
        StartedPlayPrefixHistoryPageToken
        if started_snapshot_read_mode(handle)
        else PlayPrefixHistoryPageToken
    )
    token = page_token_type(
        game_id,
        generation,
        int(doc.history_version),
        UUID(doc.prefix_ref.checkpoint.id),
        int(doc.revision),
        int(doc.prefix_ref.history_version),
        n,
        *point,
        limit,
    )
    from pitchlog.sync.nonpitch_payload import IntentionalWalkObservations

    packets = handle.run_function(token).rows
    if len(packets) > limit + 1:
        raise OrdinaryPrefixError
    items = []
    last_point = None
    for packet in packets[:limit]:
        if len(packet) != 1:
            raise OrdinaryPrefixError
        item = _json(packet[0])
        if type(item) is not dict or set(item) != {
            "history",
            "event",
            "play_row",
            "expected_play_row",
            "play_runners",
            "expected_play_runners",
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
            or e["payload"].get("formatVersion") != "play-prefix-play-v3"
        ):
            raise OrdinaryPrefixError
        payload = _verify_v2_read_packet(item, tenant, game_id, lineup=True)
        current = (h["d1"], h["d2"], UUID(h["source_event_id"]))
        if current <= point or last_point is not None and current <= last_point:
            raise OrdinaryPrefixError
        last_point = current
        items.append(
            {
                "play_row": _public_play(
                    p,
                    None
                    if type(payload.observations) is IntentionalWalkObservations
                    else payload.observations.course,
                ),
                "history_entry": h["entry"],
                "play_runners": item["play_runners"],
            }
        )
    next_cursor = None
    if len(packets) > limit:
        if last_point is None:
            raise OrdinaryPrefixError
        next_cursor = (
            base64.urlsafe_b64encode(
                _canonical_json(
                    {**scope, "position": [str(x) for x in last_point]}
                ).encode()
            )
            .decode()
            .rstrip("=")
        )
    value = last_payload.calculation.response.value
    projection.update(
        after=doc.after,
        prefix_ref=doc.prefix_ref,
        rules=doc.rules,
        t2=doc.t2,
        last_entry=value.new_history_entry,
        last_source=value.play_identity,
        prior_artifact_sha256=doc.artifact_sha256,
        pa_start_source=doc.pa_start_source,
        lineup=doc.lineup,
        roster_digest=doc.roster_digest,
        runners=doc.runners,
        participants=doc.participants,
        checkpoint_anchor=anchor,
        storage_anchor=doc.storage_anchor,
        last_saved_at=row["saved_at"],
        page={"items": items, "next_cursor": next_cursor},
    )
    return OrdinaryPrefixView(metadata, projection)


def _read_p3_lineup_projection(verified, metadata, projection, row, *, limit, cursor):
    """全値検証済みP3有効版から同じv3 page形を有限に切り出す。"""
    from pitchlog.repositories.past_correction_current_paged import (
        VerifiedP3PagedCurrent,
    )

    doc = verified.checkpoint
    scope = {
        "version": "p3-current-v1",
        "tenant": doc.prefix_ref.tenant_id,
        "game": doc.prefix_ref.game_id,
        "capsule_id": str(verified.capsule_id),
        "head": doc.prefix_ref.model_dump(mode="json", by_alias=True),
        "watermark": doc.confirmed_watermark,
        "recovery_generation": doc.recovery_generation,
    }
    after = 0
    if cursor is not None:
        supplied = _cursor(cursor)
        if (
            type(supplied) is not dict
            or set(supplied) != {*scope, "after_d1"}
            or any(
                _canonical_json(supplied[key]) != _canonical_json(value)
                for key, value in scope.items()
            )
            or type(supplied["after_d1"]) is not int
            or not 0
            < supplied["after_d1"]
            < (
                verified.source_count
                if type(verified) is VerifiedP3PagedCurrent
                else len(verified.items)
            )
        ):
            raise OrdinaryPrefixError
        after = supplied["after_d1"]
    if type(verified) is VerifiedP3PagedCurrent:
        if after != verified.selected_after_d1:
            raise OrdinaryPrefixError
        selected = verified.selected_items
        selected_payloads = verified.selected_payloads
        source_count = verified.source_count
        last_payload = verified.last_payload
    else:
        selected = verified.items[after : after + limit]
        selected_payloads = verified.payloads[after : after + limit]
        source_count = len(verified.items)
        last_payload = verified.payloads[-1]
    page_items = [
        {
            "play_row": _public_play(item["play_row"], payload.observations.course),
            "history_entry": item["history_entry"],
            "play_runners": item["play_runners"],
        }
        for item, payload in zip(selected, selected_payloads, strict=True)
    ]
    next_d1 = after + len(page_items)
    next_cursor = None
    if next_d1 < source_count:
        next_cursor = (
            base64.urlsafe_b64encode(
                _canonical_json({**scope, "after_d1": next_d1}).encode()
            )
            .decode()
            .rstrip("=")
        )
    last_value = last_payload.calculation.response.value
    projection.update(
        after=doc.after,
        prefix_ref=doc.prefix_ref,
        rules=doc.rules,
        t2=doc.t2,
        last_entry=last_value.new_history_entry,
        last_source=last_value.play_identity,
        prior_artifact_sha256=doc.artifact_sha256,
        pa_start_source=doc.pa_start_source,
        lineup=doc.lineup,
        roster_digest=doc.roster_digest,
        runners=doc.runners,
        participants=doc.participants,
        checkpoint_anchor={
            "id": doc.id,
            "revision": doc.revision,
            "history_version": doc.history_version,
        },
        storage_anchor=doc.storage_anchor,
        last_saved_at=row["saved_at"],
        page={"items": page_items, "next_cursor": next_cursor},
    )
    return OrdinaryPrefixView(metadata, projection)


def _read_nonplay_projection(
    handle, game_id, tenant, game, generation, epoch, n, d4, row, tail, limit, cursor
):
    """非play後D3を実head/active/物理採番と分離したreadonly projection。"""
    from pitchlog.domainrt.initial_game_roster import InitialRosterProjection
    from pitchlog.repositories.nonplay_prefix_read import (
        check_storage_row,
        checked_checkpoint,
        read_active_page,
    )

    cp = checked_checkpoint(
        row["content"], tenant=tenant, game=game_id, generation=d4, d3=n
    )
    check_storage_row(
        row, cp, tenant=tenant, game=game_id, generation=generation, epoch=epoch, d3=n
    )
    if (
        type(tail) is not dict
        or tail.get("tenant_id") != str(tenant)
        or tail.get("game_id") != str(game_id)
        or type(tail.get("d2")) is not int
        or not 0 <= tail["d2"] < 2**63 - 1000
    ):
        raise OrdinaryPrefixError
    page = read_active_page(
        handle,
        cp,
        generation=generation,
        limit=limit,
        cursor=cursor,
        checkpoint_row=row,
    )
    roster = InitialRosterProjection.model_validate_json(_canonical_json(row["roster"]))
    saved = _rows(handle.run(StartedLineupsReadToken(game_id)), LINEUP_COLUMNS)
    if len(saved) != 2 or any(
        x["tenant_id"] != tenant or x["game_id"] != game_id for x in saved
    ):
        raise OrdinaryPrefixError
    lineups = tuple(_saved_lineup(x) for x in saved)
    sides = tuple(
        next(x for x in lineups if x.team_id == game[k])
        for k in ("away_team_record_id", "home_team_record_id")
    )
    metadata = _prefix_metadata(game, game_id, d4, sides, roster)
    return OrdinaryPrefixView(
        metadata,
        {
            "profile": "nonplay-prefix-read-v1",
            "checkpoint": cp,
            "after": cp.content.restored.current,
            "next_position": {"d1": str(n + 1), "d2": str(tail["d2"] + 1000)},
            "recovery_generation": str(epoch),
            "last_saved_at": row["saved_at"],
            "page": page,
            "append_policy": {
                "version": "ordinary-append-v1",
                "first_d2": "1",
                "d2_gap": "1000",
                "max_d2": "9007199254740991",
            },
        },
    )
