"""通常投球checkpointの閉値。型適合だけで真正prefix資格を発行しない。"""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, model_validator

from pitchlog.domainrt.first_ball_projection import _canonical_json, _canonical_sha256
from pitchlog.domainrt.first_pitch import (
    StateSnapshot,
    _Frozen,
    _invalid_constant,
    _unique_object,
)
from pitchlog.domainrt.first_pitch_continuation import SavedRuleWire, T2NoEndCore
from pitchlog.domainrt.initial_game_roster import CanonicalUUID
from pitchlog.domainrt.ordinary_pitch_continuation import OrdinaryT2, PrefixRef
from pitchlog.sync.idempotency import source_fingerprint


class OrdinaryPrefixError(RuntimeError):
    """閉checkpointや真正原本を確認できない固定失敗。"""

    def __init__(self) -> None:
        """不明なprefixを初期値に補完しない。"""
        super().__init__("通常投球の確定prefixを確認できません")


def _integer(value: str) -> str:
    """bigintの非負正準表現だけを保持する。"""
    if (
        type(value) is not str
        or not value.isascii()
        or not value.isdecimal()
        or (len(value) > 1 and value.startswith("0"))
        or int(value) > 2**63 - 1
    ):
        raise ValueError("非負bigint正準表現が必要")
    return value


def _positive(value: str) -> str:
    """正整数の既DB範囲を検査する。"""
    _integer(value)
    if value == "0":
        raise ValueError("正のbigintが必要")
    return value


Nonnegative = Annotated[str, AfterValidator(_integer)]
Positive = Annotated[str, AfterValidator(_positive)]
Digest = Annotated[str, AfterValidator(_canonical_sha256)]


def _fingerprint(value: str) -> str:
    """既wire-v1指紋のタグを変更せず保持する。"""
    if re.fullmatch(r"(?:wire-v1:)?[a-f0-9]{64}", value, re.ASCII) is None:
        raise ValueError("既指紋の正準形が必要")
    return value


Fingerprint = Annotated[str, AfterValidator(_fingerprint)]


class PrefixSource(_Frozen):
    """実イベントと照合する前位置の識別。"""

    id: CanonicalUUID
    tenant_id: CanonicalUUID
    game_id: CanonicalUUID
    generation: Positive
    d1: Positive
    d2: Nonnegative
    d5: CanonicalUUID
    source_fingerprint: Fingerprint
    event_fingerprint: Fingerprint


class CheckpointDocument(_Frozen):
    """候補境界の全値。別途実同TX原本と照合しない限り資格ではない。"""

    version: Literal["1"]
    id: CanonicalUUID
    revision: Positive
    history_version: Positive
    prefix_ref: PrefixRef
    wire_d4: Annotated[str, Field(min_length=1, max_length=128)]
    internal_generation: Positive
    recovery_generation: Positive
    confirmed_watermark: Nonnegative
    applied_watermark: Nonnegative
    last_source: PrefixSource | None
    history_depth: Nonnegative
    after: StateSnapshot
    rules: SavedRuleWire
    t2: T2NoEndCore | OrdinaryT2 | None
    roster_digest: Digest
    content_digest: Digest
    artifact_sha256: Digest
    state: Literal["current", "invalidated"]

    @model_validator(mode="after")
    def _positions_and_digest(self):
        """位置の相関と全内容digestだけを確認し数学を再計算しない。"""
        if (
            self.confirmed_watermark != self.applied_watermark
            or self.wire_d4 != self.prefix_ref.generation
        ):
            raise ValueError("checkpoint水位又はD4が不一致")
        if self.confirmed_watermark == "0":
            if (
                self.last_source is not None
                or self.prefix_ref.length != "0"
                or self.t2 is not None
            ):
                raise ValueError("空prefixの原本が不一致")
        else:
            source = self.last_source
            if (
                source is None
                or self.t2 is None
                or (
                    source.tenant_id != self.prefix_ref.tenant_id
                    or source.game_id != self.prefix_ref.game_id
                    or source.generation != self.internal_generation
                    or source.d1 != self.confirmed_watermark
                )
            ):
                raise ValueError("prefix最終原本が不一致")
        content = self.model_dump(mode="json", by_alias=True, exclude_unset=True)
        if (
            source_fingerprint(
                {k: v for k, v in content.items() if k != "content_digest"}
            )
            != self.content_digest
        ):
            raise ValueError("checkpoint全内容digestが不一致")
        return self


def read_checkpoint_document(raw: str) -> CheckpointDocument:
    """余剰/重複/別名/暗黙型変換を拒否し、DB照合前の閉値を返す。"""
    try:
        if type(raw) is not str:
            raise ValueError
        wire = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        value = CheckpointDocument.model_validate_json(raw)
        if _canonical_json(
            value.model_dump(mode="json", by_alias=True, exclude_unset=True)
        ) != _canonical_json(wire):
            raise ValueError
        return value
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise OrdinaryPrefixError from None


def _locked_prefix_context(handle, event, source):
    """v1/v2で同じ実game/generation/source/leaseを確認する共有核。"""
    from uuid import UUID

    from pitchlog.db.game_state.models import Game
    from pitchlog.repositories.started_snapshot import _one
    from pitchlog.repositories.sync_apply import _GENERATION_READ_COLUMNS
    from pitchlog.repositories.transaction import _TenantTransaction
    from pitchlog.sync.source_binding import _E1CoreSource
    from pitchlog.sync.tokens import (
        GameLockToken,
        GameReadToken,
        RecordingGenerationLockToken,
        RecordingGenerationReadToken,
    )

    if type(handle) is not _TenantTransaction or type(source) is not _E1CoreSource:
        raise OrdinaryPrefixError
    lifetime = handle._writer_lifetime()
    tenant = handle._bound_tenant_id
    game_id = UUID(event.game_id)
    phase = json.loads(source.bound._phase_snapshot)["phase"]

    def live():
        """実sourceとtop-level writerの失効を毎回確認する。"""
        handle._assert_writer_lifetime(lifetime)
        source.read(handle, event)

    def run(token):
        """同handleの固定token以外を受け取らない。"""
        live()
        result = handle.run(token)
        live()
        return result

    live()
    locked = _one(run(GameLockToken(game_id)), tuple(Game.__table__.c.keys()))
    game = _one(run(GameReadToken(game_id)), tuple(Game.__table__.c.keys()))
    if (
        locked != game
        or game["tenant_id"] != tenant
        or game["id"] != game_id
        or any(
            game[k] is not None for k in ("trashed_at", "hidden_at", "import_batch_id")
        )
        or game["status"] != "in_progress"
    ):
        raise OrdinaryPrefixError
    current = _one(run(RecordingGenerationReadToken(game_id)), _GENERATION_READ_COLUMNS)
    generation = current["generation"]
    same = _one(
        run(RecordingGenerationLockToken(game_id, generation)), _GENERATION_READ_COLUMNS
    )
    if (
        current != same
        or type(generation) is not int
        or not 0 < generation < 2**63
        or (
            generation != phase["internal_generation"]
            or event.d4 != phase["wire_d4"]
            or current["kind"] != "normal"
            or current["tenant_id"] != tenant
            or current["game_id"] != game_id
            or any(
                current[k] is not None
                for k in ("revoked_at", "retired_at", "import_batch_id")
            )
        )
    ):
        raise OrdinaryPrefixError
    from pitchlog.repositories.ordinary_order import OrdinaryOrderSummaryToken
    from pitchlog.repositories.ordinary_prefix_read import _function_one
    from pitchlog.sync.ordinary_pitch_execution import _ordinary_verified_epoch

    epoch = _ordinary_verified_epoch(handle, source)
    summary = _function_one(handle, OrdinaryOrderSummaryToken(game_id))
    if (
        type(summary) is not dict
        or type(summary.get("recovery_generation")) is not int
        or summary["recovery_generation"] != epoch
    ):
        raise OrdinaryPrefixError
    watermark = current["confirmed_watermark"]
    if (
        type(watermark) is not int
        or watermark < 0
        or current["applied_prefix"] != watermark
    ):
        raise OrdinaryPrefixError
    live()
    lease = source.bound._lease
    return run, live, tenant, game_id, generation, epoch, watermark, lease


def read_confirmed_ordinary_prefix(
    handle, event, source, *, artifact_sha256: str, play_prefix_compat=False
):
    """同TX原本からだけprefix/配置を取得し、自由recordを資格にしない。"""
    from dataclasses import dataclass
    from uuid import UUID, uuid4

    from pitchlog.db.sync_protocol.models import OperationEvent
    from pitchlog.domainrt.initial_game_roster import InitialRosterProjection
    from pitchlog.repositories.ordinary_prefix_operations import (
        OrdinaryCheckpointLockToken,
    )
    from pitchlog.repositories.recorded_snapshot import (
        RecordedCalculationCandidate,
        try_read_recorded_snapshot,
    )
    from pitchlog.repositories.started_snapshot import (
        _one,
        read_initial_started_snapshot,
    )
    from pitchlog.sync.tokens import (
        IdempotencyLedgerReadToken,
        OperationEventReadToken,
    )

    @dataclass(frozen=True, slots=True)
    class ReadValue:
        """原本由来の内部読取結果。単体でframe/DB資格ではない。"""

        checkpoint: CheckpointDocument
        roster: InitialRosterProjection
        bootstrap: bool
        next_play_number: int

    run, live, tenant, game_id, generation, epoch, watermark, lease = (
        _locked_prefix_context(handle, event, source)
    )
    result = handle.run_function(
        OrdinaryCheckpointLockToken(
            lease.attempt_id,
            lease.phase_id,
            lease.nonce,
            lease.device_id,
            game_id,
            generation,
        )
    )
    live()
    if result.rows:
        if (
            len(result.rows) != 1
            or len(result.rows[0]) != 1
            or type(result.rows[0][0]) is not str
        ):
            raise OrdinaryPrefixError
        row = json.loads(
            result.rows[0][0],
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
        if type(row) is not dict:
            raise OrdinaryPrefixError
        for field in ("tenant_id", "game_id", "id"):
            row[field] = UUID(row[field])
        doc = read_checkpoint_document(_canonical_json(row["content"]))
        if any(
            row[k] != expected
            for k, expected in {
                "tenant_id": tenant,
                "game_id": game_id,
                "internal_generation": generation,
                "id": UUID(doc.id),
                "revision": int(doc.revision),
                "history_version": int(doc.history_version),
                "recovery_generation": epoch,
                "confirmed_watermark": watermark,
                "applied_watermark": watermark,
                "content_digest": doc.content_digest,
                "state": "current",
            }.items()
        ) or (
            doc.prefix_ref.tenant_id != str(tenant)
            or doc.prefix_ref.game_id != str(game_id)
            or doc.wire_d4 != event.d4
            or int(doc.internal_generation) != generation
            or int(doc.recovery_generation) != epoch
            or int(doc.confirmed_watermark) != watermark
            or int(doc.applied_watermark) != watermark
            or doc.artifact_sha256 != artifact_sha256
        ):
            raise OrdinaryPrefixError
        roster_raw = row["roster"]
        if source_fingerprint(roster_raw) != doc.roster_digest:
            raise OrdinaryPrefixError
        roster = InitialRosterProjection.model_validate_json(
            _canonical_json(roster_raw)
        )
        live()
        from pitchlog.repositories.first_ball_operations import PLAY_ROW_COLUMNS
        from pitchlog.sync.first_ball_tokens import FirstBallPlayRowReadToken

        previous = doc.last_source
        if previous is None:
            raise OrdinaryPrefixError
        last_play = _one(
            run(FirstBallPlayRowReadToken(game_id, UUID(previous.id))), PLAY_ROW_COLUMNS
        )
        play_number = last_play["play_number"]
        if (
            last_play["tenant_id"] != tenant
            or last_play["game_id"] != game_id
            or last_play["source_event_id"] != UUID(previous.id)
            or type(play_number) is not int
            or not 0 < play_number < 2**63 - 1
        ):
            raise OrdinaryPrefixError
        _verify_persisted_last_source(
            run, tenant, game_id, doc, roster, last_play, row.get("last_play_row")
        )
        return ReadValue(doc, roster, False, play_number + 1)
    if watermark == 0:
        initial = read_initial_started_snapshot(handle, game_id)
        next_play_number = 1
        after, rules, roster, t2, last, length, depth = (
            initial.before,
            initial.rules,
            initial.roster,
            None,
            None,
            "0",
            "0",
        )
    elif watermark == 1:
        recorded = (
            try_read_recorded_snapshot(handle, game_id, play_prefix_compat=True)
            if play_prefix_compat
            else try_read_recorded_snapshot(handle, game_id)
        )
        if type(recorded) is not RecordedCalculationCandidate:
            raise OrdinaryPrefixError
        event_row = _one(
            run(OperationEventReadToken(game_id, generation, 1)),
            tuple(OperationEvent.__table__.c.keys()),
        )
        ledger = run(IdempotencyLedgerReadToken(recorded.d5))
        from pitchlog.db.sync_protocol.models import IdempotencyLedger

        ledger_row = _one(ledger, tuple(IdempotencyLedger.__table__.c.keys()))
        fingerprint = ledger_row["source_fingerprint"]
        from pitchlog.repositories.first_ball_operations import PLAY_ROW_COLUMNS

        saved_play = dict(
            zip(PLAY_ROW_COLUMNS, recorded.verified_play_row, strict=True)
        )
        if (
            type(saved_play["play_number"]) is not int
            or not 0 < saved_play["play_number"] < 2**63 - 1
        ):
            raise OrdinaryPrefixError
        next_play_number = saved_play["play_number"] + 1
        last = {
            "id": str(recorded.source_event_id),
            "tenant_id": str(tenant),
            "game_id": str(game_id),
            "generation": str(generation),
            "d1": "1",
            "d2": str(event_row["d2"]),
            "d5": str(recorded.d5),
            "source_fingerprint": fingerprint,
            "event_fingerprint": fingerprint,
        }
        after, rules, roster, t2, length, depth = (
            recorded.response.value.t1.after,
            recorded.request.rules,
            recorded.roster,
            recorded.response.value.t2,
            "1",
            str(len(recorded.response.value.t1.history_context)),
        )
    else:
        # 過去全件を読み直してcheckpointを捏造しない。
        raise OrdinaryPrefixError
    doc = bootstrap_checkpoint_document(
        tenant=tenant,
        game_id=game_id,
        d4=event.d4,
        generation=generation,
        epoch=epoch,
        watermark=watermark,
        last=last,
        length=length,
        depth=depth,
        after=after,
        rules=rules,
        roster=roster,
        t2=t2,
        artifact_sha256=artifact_sha256,
        anchor_id=uuid4(),
    )
    live()
    return ReadValue(doc, roster, True, next_play_number)


def _verify_persisted_last_source(
    run, tenant, game_id, doc, roster, last_play, expected_row
):
    """Private checkpointに束縛された実source/ledger/全41列を独立point照合する。"""
    from uuid import UUID

    from pitchlog.db.sync_protocol.models import IdempotencyLedger, OperationEvent
    from pitchlog.repositories.started_snapshot import _one
    from pitchlog.sync.idempotency import _json_value
    from pitchlog.sync.ordinary_pitch_payload import (
        OrdinaryPitchPlayPayload,
        select_ordinary_pitch_participants,
    )
    from pitchlog.sync.ordinary_pitch_physical import ordinary_pitch_physical_row
    from pitchlog.sync.tokens import IdempotencyLedgerReadToken, OperationEventReadToken

    previous = doc.last_source
    if previous is None or type(expected_row) is not dict:
        raise OrdinaryPrefixError
    event = _one(
        run(
            OperationEventReadToken(
                game_id, int(doc.internal_generation), int(previous.d1)
            )
        ),
        tuple(OperationEvent.__table__.c.keys()),
    )
    ledger = _one(
        run(IdempotencyLedgerReadToken(UUID(previous.d5))),
        tuple(IdempotencyLedger.__table__.c.keys()),
    )
    expected_event = {
        "tenant_id": tenant,
        "game_id": game_id,
        "id": UUID(previous.id),
        "generation": int(previous.generation),
        "d1": int(previous.d1),
        "d2": int(previous.d2),
        "d5": UUID(previous.d5),
        "ledger_kind": "accepted",
        "event_kind": "play_input",
        "is_tombstone": False,
        "replaced_at": None,
        "retired_at": None,
        "import_batch_id": None,
        "legacy_row_identifier": None,
        "migration_unverified": False,
    }
    expected_ledger = {
        "tenant_id": tenant,
        "d5": UUID(previous.d5),
        "kind": "accepted",
        "source_fingerprint": previous.source_fingerprint,
        "retired_at": None,
        "import_batch_id": None,
    }
    for actual, expected in ((event, expected_event), (ledger, expected_ledger)):
        if any(
            type(actual[k]) is not type(v) or actual[k] != v
            for k, v in expected.items()
        ):
            raise OrdinaryPrefixError
    if previous.event_fingerprint != previous.source_fingerprint:
        raise OrdinaryPrefixError
    raw = _json_value(event["payload"])
    payload = OrdinaryPitchPlayPayload.model_validate_json(_canonical_json(raw))
    if _canonical_json(
        payload.model_dump(mode="json", by_alias=True, exclude_unset=True)
    ) != _canonical_json(raw):
        raise OrdinaryPrefixError
    response = payload.calculation.response.value
    if (
        response.next_prefix_ref != doc.prefix_ref
        or response.t1.after != doc.after
        or response.t2 != doc.t2
        or payload.calculation.request.rules != doc.rules
        or payload.calculation.artifact_sha256 != doc.artifact_sha256
        or payload.participants
        != select_ordinary_pitch_participants(
            roster, payload.calculation.request.t1.before
        )
    ):
        raise OrdinaryPrefixError
    mapped = ordinary_pitch_physical_row(
        payload,
        tenant_id=tenant,
        game_id=game_id,
        source_event_id=UUID(previous.id),
        row_id=last_play["id"],
        play_number=last_play["play_number"],
    )
    actual = {
        key: str(value) if type(value) is UUID else value
        for key, value in last_play.items()
    }
    # expected_rowは実consumed admission JOINの値。数学出力で期待値を補完しない。
    if (
        set(actual) != set(expected_row)
        or set(actual) != set(mapped)
        or any(
            type(actual[k]) is not type(expected_row[k])
            or actual[k] != expected_row[k]
            or type(actual[k]) is not type(mapped[k])
            or actual[k] != mapped[k]
            for k in actual
        )
    ):
        raise OrdinaryPrefixError


def bootstrap_checkpoint_document(
    *,
    tenant,
    game_id,
    d4,
    generation,
    epoch,
    watermark,
    last,
    length,
    depth,
    after,
    rules,
    roster,
    t2,
    artifact_sha256,
    anchor_id,
):
    """未保存の候補documentを共通描画する。GETもwriter資格を発行しない。"""
    content = {
        "version": "1",
        "id": str(anchor_id),
        "revision": "1",
        "history_version": "1",
        "prefix_ref": {
            "version": "1",
            "tenantId": str(tenant),
            "gameId": str(game_id),
            "generation": d4,
            "length": length,
        },
        "wire_d4": d4,
        "internal_generation": str(generation),
        "recovery_generation": str(epoch),
        "confirmed_watermark": str(watermark),
        "applied_watermark": str(watermark),
        "last_source": last,
        "history_depth": depth,
        "after": after.model_dump(mode="json", by_alias=True),
        "rules": rules.model_dump(mode="json", by_alias=True),
        "t2": None
        if t2 is None
        else t2.model_dump(mode="json", by_alias=True, exclude_unset=True),
        "roster_digest": source_fingerprint(
            roster.model_dump(mode="json", by_alias=True)
        ),
        "artifact_sha256": artifact_sha256,
        "state": "current",
    }
    content["content_digest"] = source_fingerprint(content)
    return read_checkpoint_document(_canonical_json(content))
