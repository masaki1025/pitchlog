"""通常投球の全41列INSERT宣言。実frameとDB印は核とtriggerが別に要求する。"""

from __future__ import annotations

import json
import math
import re
from typing import cast
from uuid import UUID

from sqlalchemy import Table, bindparam, insert
from sqlalchemy.sql.dml import Insert

from pitchlog.db.game_state.models import PlayRow
from pitchlog.db.sync_protocol.models import IdempotencyLedger, OperationEvent
from pitchlog.domainrt.first_pitch import _invalid_constant, _unique_object
from pitchlog.repositories.first_ball_operations import _NULL_COLUMNS, _one
from pitchlog.repositories.operation_registration import (
    OperationPreflight,
    OperationRegistration,
)
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.first_ball_tokens import FirstBallPlayRowReadToken
from pitchlog.sync.ordinary_pitch_tokens import OrdinaryPlayRowInsertToken
from pitchlog.sync.terminal_pitch_tokens import PlayPrefixPlayRowInsertToken
from pitchlog.sync.tokens import IdempotencyLedgerReadToken, OperationEventReadToken

_PLAY = cast(Table, PlayRow.__table__)
_BATTED_COLUMNS = frozenset(
    {
        "raw_fielder_position",
        "resolved_fielder_id",
        "batted_ball_type",
        "batted_ball_strength",
        "hit_x",
        "hit_y",
    }
)
_BATTED_RESULTS = frozenset(
    f"batting-result.{result}"
    for result in ("single", "double", "triple", "home-run", "batted-out")
)
_INTENTIONAL_WALK = "batting-result.intentional-walk"
_NONPITCH_NULL_COLUMNS = frozenset(
    ("pitch_type_key", "course_x", "course_y", "pitch_speed", "stance", "batting_side")
)


_RUNNER_NONPITCH_COLUMNS = frozenset(
    ("pickoff_type", "pickoff_detail", "secondary_batting_result_key")
)
_RUNNER_PITCH_SECONDARY = frozenset(
    ("secondary-result.wild-pitch", "secondary-result.passed-ball")
)
_RUNNER_PITCH_PRIMARY = frozenset(
    (
        "batting-result.ball",
        "batting-result.called-pitch",
        "batting-result.swinging-strike",
    )
)


def _runner_nonpitch_shape(token, row):
    """候補物理形だけを絞る。原操作の成立はINSERT前preflightが必須。"""
    if (
        type(token) is not PlayPrefixPlayRowInsertToken
        or row["event_kind"] != "non_pitch"
        or row["batting_result_key"] is not None
    ):
        return False
    pickoff = (row["pickoff_type"], row["pickoff_detail"])
    secondary = row["secondary_batting_result_key"]
    if secondary == "secondary-result.balk":
        return pickoff == (None, None)
    return secondary is None and (
        pickoff == (None, None)
        or (
            pickoff[0] in ("pitcher", "catcher")
            and pickoff[1] in ("first", "second", "third")
        )
    )


def _runner_pitch_secondary_shape(token, row):
    """既核で許された投球主結果とWP/PB副結果だけを有限識別する。"""
    return (
        type(token) is PlayPrefixPlayRowInsertToken
        and row["event_kind"] == "pitch"
        and row["batting_result_key"] in _RUNNER_PITCH_PRIMARY
        and row["secondary_batting_result_key"] in _RUNNER_PITCH_SECONDARY
    )


def _validate_runner_source(token, row, event):
    """原eventが走者観測なら既唯一mapperの全41列へ必ず再束縛する。"""
    from pitchlog.domainrt.lineup_play_prefix_continuation import RunnerEventT1Input
    from pitchlog.sync.idempotency import _json_value
    from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
    from pitchlog.sync.terminal_pitch_payload import (
        LineupPitchCalculation,
        LineupPitchPlayPayload,
        RunnerNonpitchPlayObservations,
        RunnerPitchPlayObservations,
    )

    try:
        original = _json_value(event["payload"])
        if type(original) is not dict:
            if _runner_nonpitch_shape(token, row) or _runner_pitch_secondary_shape(
                token, row
            ):
                raise OrdinaryPlayRowError
            return
        observations = original.get("observations")
        calculation = original.get("calculation")
        request = calculation.get("request") if type(calculation) is dict else None
        t1 = request.get("t1") if type(request) is dict else None
        runner_tagged = (
            type(observations) is dict and "runnerObservation" in observations
        ) or (type(t1) is dict and "runnerObservation" in t1)
        if not (
            runner_tagged
            or _runner_nonpitch_shape(token, row)
            or _runner_pitch_secondary_shape(token, row)
        ):
            return
        payload = LineupPitchPlayPayload.model_validate_json(
            json.dumps(original, allow_nan=False)
        )
        if type(payload.calculation) is not LineupPitchCalculation:
            raise OrdinaryPlayRowError
        q = payload.calculation.request
        observed = payload.observations
        if (
            type(q.t1) is not RunnerEventT1Input
            or type(observed)
            not in (RunnerNonpitchPlayObservations, RunnerPitchPlayObservations)
        ):
            raise OrdinaryPlayRowError
        observed = cast(
            RunnerNonpitchPlayObservations | RunnerPitchPlayObservations, observed
        )
        nonpitch = type(observed) is RunnerNonpitchPlayObservations
        if (
            row["event_kind"] != ("non_pitch" if nonpitch else "pitch")
            or observed.runner_observation != q.t1.runner_observation
            or q.prefix_ref.tenant_id != str(row["tenant_id"])
            or q.prefix_ref.game_id != str(token.game_id)
            or q.play_identity.event_id != str(event["id"])
            or q.play_identity.play_id != str(row["id"])
            or q.play_identity.d5 != str(token.d5)
        ):
            raise OrdinaryPlayRowError
        per = observed.runner_observation.per_pitch
        if per.pitch_event_kind != (
            "non-pitch-event" if nonpitch else "pitch-event"
        ):
            raise OrdinaryPlayRowError
        if nonpitch:
            if observed.runner_observation.primary_result_id is not None:
                raise OrdinaryPlayRowError
            runner_event = per.runner_event_payload
            if per.kind == "runner-event":
                if (
                    runner_event.kind != "runner-event"
                    or per.result_id != runner_event.event_kind
                    or per.runner_advance_overrides.kind != "not-applied"
                ):
                    raise OrdinaryPlayRowError
            elif per.kind == "secondary-result":
                if (
                    per.result_id != "secondary-result.balk"
                    or runner_event.kind != "not-applicable"
                    or per.runner_advance_overrides.kind != "overridden"
                ):
                    raise OrdinaryPlayRowError
            else:
                raise OrdinaryPlayRowError
        elif per.kind == "secondary-result" and (
            per.result_id not in _RUNNER_PITCH_SECONDARY
            or observed.runner_observation.primary_result_id
            not in _RUNNER_PITCH_PRIMARY
            or per.runner_event_payload.kind != "not-applicable"
            or per.runner_advance_overrides.kind != "overridden"
        ):
            raise OrdinaryPlayRowError
        expected = pitch_physical_row(
            observed,
            payload.participants,
            q.t1.result_id,
            tenant_id=row["tenant_id"],
            game_id=token.game_id,
            source_event_id=event["id"],
            row_id=row["id"],
            play_number=row["play_number"],
        )
        canonical = {k: str(v) if type(v) is UUID else v for k, v in row.items()}
        if canonical != expected:
            raise OrdinaryPlayRowError
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
        raise OrdinaryPlayRowError from None


def _ordinary_play_row_insert_statement() -> Insert:
    """全41列INSERTだけを固定表/閉bindから描画するSQL窓口。"""
    return insert(_PLAY).values({name: bindparam(name) for name in _PLAY.c.keys()})


_INSERT = _ordinary_play_row_insert_statement()


class OrdinaryPlayRowError(RuntimeError):
    """原入力や資格を例外に含めない固定失敗。"""

    def __init__(self):
        """型不正を補修しない。"""
        super().__init__("通常PlayRowの投影値/原本が不一致です")


def _row(token):
    """全列と実型を照合し、観測を生成/補修しない。"""
    if (
        type(token) not in {OrdinaryPlayRowInsertToken, PlayPrefixPlayRowInsertToken}
        or type(token.row_json) is not str
    ):
        raise OrdinaryPlayRowError
    try:
        row = json.loads(
            token.row_json,
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
        if type(row) is not dict or set(row) != set(_PLAY.c.keys()):
            raise OrdinaryPlayRowError
        for column in _PLAY.c:
            value = row[column.name]
            if value is None:
                if not column.nullable:
                    raise OrdinaryPlayRowError
                continue
            expected = column.type.python_type
            if expected is UUID:
                if type(value) is not str or str(UUID(value)) != value:
                    raise OrdinaryPlayRowError
                row[column.name] = UUID(value)
            elif type(value) is not expected:
                raise OrdinaryPlayRowError
            if expected is float and not math.isfinite(value):
                raise OrdinaryPlayRowError
        batted = (
            type(token) is PlayPrefixPlayRowInsertToken
            and row["batting_result_key"] in _BATTED_RESULTS
        )
        runner_nonpitch = _runner_nonpitch_shape(token, row)
        runner_pitch_secondary = _runner_pitch_secondary_shape(token, row)
        nonpitch = runner_nonpitch or (
            type(token) is PlayPrefixPlayRowInsertToken
            and row["event_kind"] == "non_pitch"
            and row["batting_result_key"] == _INTENTIONAL_WALK
        )
        required_null = (
            set(_NULL_COLUMNS) - _BATTED_COLUMNS if batted else _NULL_COLUMNS
        )
        if runner_nonpitch:
            required_null = set(_NULL_COLUMNS) - _RUNNER_NONPITCH_COLUMNS
        elif runner_pitch_secondary:
            required_null = set(_NULL_COLUMNS) - {"secondary_batting_result_key"}
        if batted and (
            any(
                row[name] is not None and not 0 <= row[name] <= 1
                for name in ("hit_x", "hit_y")
            )
            or any(
                row[name] is not None and not row[name]
                for name in (
                    "batted_ball_type",
                    "batted_ball_strength",
                    "raw_fielder_position",
                )
            )
        ):
            raise OrdinaryPlayRowError
        if (
            type(token.game_id) is not UUID
            or type(token.d5) is not UUID
            or any(
                type(x) is not int or not 0 < x < 2**63
                for x in (token.generation, token.d1)
            )
            or type(token.d2) is not int
            or not -(2**63) <= token.d2 < 2**63
            or type(token.source_fingerprint) is not str
            or re.fullmatch(r"(?:wire-v1:)?[a-f0-9]{64}", token.source_fingerprint)
            is None
            or row["game_id"] != token.game_id
            or (row["event_kind"] != "pitch" and not nonpitch)
            or (row["batting_result_key"] == _INTENTIONAL_WALK and not nonpitch)
            or type(row["play_number"]) is not int
            or not 0 < row["play_number"] < 2**63
            or type(row["batting_order"]) is not int
            or not 1 <= row["batting_order"] <= 9
            or row["version"] != 1
            or row["migration_unverified"] is not False
            or any(row[name] is not None for name in required_null)
            or row["batter_id"] is None
            or row["pitcher_id"] is None
            or row["catcher_id"] is None
            or (
                not runner_nonpitch
                and (
                    type(row["batting_result_key"]) is not str
                    or not row["batting_result_key"]
                )
            )
            or (
                row["batting_side"] is not None
                and row["batting_side"] not in ("右", "左")
            )
            or (
                row["stance"] is not None
                and re.fullmatch(r"(?:[1-9]|1[0-9]|2[0-5])", row["stance"]) is None
            )
        ):
            raise OrdinaryPlayRowError
        if nonpitch:
            if any(row[name] is not None for name in _NONPITCH_NULL_COLUMNS):
                raise OrdinaryPlayRowError
        elif (
            type(row["pitch_type_key"]) is not str
            or not row["pitch_type_key"]
            or type(row["course_x"]) is not float
            or not 0 <= row["course_x"] <= 1
            or type(row["course_y"]) is not float
            or not 0 <= row["course_y"] <= 1
        ):
            raise OrdinaryPlayRowError
        return row
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
        raise OrdinaryPlayRowError from None


def _prepare(token):
    """tenantだけはexecutorから補い、原値を全列へ写す。"""
    row = _row(token)
    return _INSERT, {k: v for k, v in row.items() if k != "tenant_id"}


def _preflight(token, parameters):
    """同handleの原event/ledger/既投影と全物理値を照合する。"""
    row = _row(token)
    if set(parameters) != set(row) or any(
        type(parameters[k]) is not type(v) or parameters[k] != v for k, v in row.items()
    ):
        raise OrdinaryPlayRowError

    def validate(results):
        """別の原本や二重投影をINSERTへ渡さない。"""
        if type(results) is not tuple or len(results) != 3:
            raise OrdinaryPlayRowError
        event = _one(results[0], tuple(OperationEvent.__table__.c.keys()))
        ledger = _one(results[1], tuple(IdempotencyLedger.__table__.c.keys()))
        for actual, wanted in (
            (
                event,
                {
                    "tenant_id": row["tenant_id"],
                    "id": row["source_event_id"],
                    "game_id": token.game_id,
                    "generation": token.generation,
                    "d1": token.d1,
                    "d2": token.d2,
                    "d5": token.d5,
                    "event_kind": "play_input",
                    "ledger_kind": "accepted",
                    "is_tombstone": False,
                    "replaced_at": None,
                    "retired_at": None,
                    "import_batch_id": None,
                    "legacy_row_identifier": None,
                    "migration_unverified": False,
                    "target_generation": None,
                    "target_d1": None,
                    "expected_version": None,
                    "change_order": None,
                },
            ),
            (
                ledger,
                {
                    "tenant_id": row["tenant_id"],
                    "d5": token.d5,
                    "kind": "accepted",
                    "source_fingerprint": token.source_fingerprint,
                    "retired_at": None,
                },
            ),
        ):
            if any(
                type(actual[k]) is not type(v) or actual[k] != v
                for k, v in wanted.items()
            ):
                raise OrdinaryPlayRowError
        if type(token) is PlayPrefixPlayRowInsertToken:
            _validate_runner_source(token, row, event)
        if (
            type(results[2]) is not TenantOperationResult
            or type(results[2].rows) is not tuple
            or results[2].rows != ()
        ):
            raise OrdinaryPlayRowError

    return OperationPreflight(
        (
            OperationEventReadToken(token.game_id, token.generation, token.d1),
            IdempotencyLedgerReadToken(token.d5),
            FirstBallPlayRowReadToken(token.game_id, row["source_event_id"]),
        ),
        validate,
    )


ORDINARY_PLAY_OPERATIONS = (
    OperationRegistration(
        OrdinaryPlayRowInsertToken,
        "CAP:play_rows:insert",
        _INSERT,
        _PLAY.c.tenant_id,
        _prepare,
        preflight=_preflight,
    ),
)

PLAY_PREFIX_PLAY_OPERATIONS = (
    OperationRegistration(
        PlayPrefixPlayRowInsertToken,
        "CAP:play_rows:insert",
        _INSERT,
        _PLAY.c.tenant_id,
        _prepare,
        preflight=_preflight,
    ),
)
