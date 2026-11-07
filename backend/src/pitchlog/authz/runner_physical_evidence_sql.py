"""現行v3走者操作の明示観測と物理保存行を結ぶ限定SQL overlay。"""

import hashlib

from pitchlog.domaingen.core import _canonical_hash
from pitchlog.sync.runner_physical_labels import (
    ADVANCE_STATUS_BY_BASE_DESTINATION,
    AUTO_STATUS_SOURCE,
    HOLD_STATUS,
    MANUAL_STATUS_SOURCE,
    OUT_STATUS_BY_OBSERVED_KIND,
)

FUNCTION_ID = (
    "FUNCTION:sync_right_api:prepare_play_prefix_projection("
    "uuid, uuid, uuid, bytea, uuid, uuid, text)"
)
PARENT_SHA256 = "cb25ab6f9e8ab9906d69821f452521dbc9e2e2a917e3630689307d862860f917"
PARENT_DECLARATION_HASH = (
    "sha256:29e1640b9b1d35e2310a7abee23b8272abd65dc41dd848d96402aaf16788a005"
)
_OLD_RUNNER_START = (
    "\n OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(\n "
    "after_cp->'projection_snapshot'->'play_runners') r WHERE"
)
_OLD_RUNNER_END = (
    "\n THEN RAISE EXCEPTION 'lineup physical source rejected' "
    "USING ERRCODE='42501'; END IF;"
)
_REJECT = "RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501';"


def _quoted(value: str) -> str:
    """静的保存ラベルだけをSQL文字列へ描画する。"""
    if not value or any(ch in value for ch in ("'", "\\", "\x00")):
        raise ValueError("走者物理ラベルが閉集合外です")
    return "'" + value + "'"


def _out_status_case() -> str:
    """Python物理投影と同じ保存ラベル宣言を一度だけ使用する。"""
    return (
        "CASE rp_observed->>'out_kind' "
        + " ".join(
            f"WHEN {_quoted(kind)} THEN {_quoted(label)}"
            for kind, label in OUT_STATUS_BY_OBSERVED_KIND.items()
        )
        + " ELSE NULL END"
    )


def _advance_status_case() -> str:
    """起点/唯一T1到達先から既保存ラベルだけを選ぶ。"""
    cases = []
    for base, destinations in ADVANCE_STATUS_BY_BASE_DESTINATION.items():
        choice = (
            "CASE rp_effect->>'destination' "
            + " ".join(
                f"WHEN {_quoted(destination)} THEN {_quoted(label)}"
                for destination, label in destinations.items()
            )
            + " ELSE NULL END"
        )
        cases.append(f"WHEN {_quoted(base)} THEN ({choice})")
    return "CASE rp_before->>'base' " + " ".join(cases) + " ELSE NULL END"


def _runner_evidence_block() -> str:
    """原観測/唯一T1/保存10列を1～3走者の有界ループで照合する。"""
    return f"""
 IF source_row.payload->'calculation'->'request'->'t1' ? 'runnerObservation' THEN
  DECLARE rp_t1 jsonb; rp_per jsonb; rp_by jsonb; rp_before_set jsonb;
   rp_rows jsonb; rp_targets jsonb; rp_before jsonb; rp_observed jsonb;
   rp_record jsonb; rp_effect jsonb; rp_slot text; rp_status text;
   rp_target_count bigint; rp_out_count bigint:=0;
  BEGIN
   rp_t1:=source_row.payload->'calculation'->'request'->'t1';
   rp_per:=rp_t1->'runnerObservation'->'perPitch';
   rp_before_set:=source_row.payload->'calculation'->'request'->'source'->'runners';
   rp_rows:=after_cp->'projection_snapshot'->'play_runners';
   rp_targets:=source_row.payload->'calculation'->'response'->'value'->'t1'
    ->'outEffect'->'targets';
   IF pg_catalog.jsonb_typeof(rp_t1->'runnerObservation') IS DISTINCT FROM 'object'
    OR rp_t1->'runnerObservation' IS DISTINCT FROM
     source_row.payload->'observations'->'runnerObservation'
    OR pg_catalog.jsonb_typeof(rp_per) IS DISTINCT FROM 'object'
    OR rp_t1->>'eventKind' IS DISTINCT FROM rp_per->>'kind'
    OR rp_t1->>'resultId' IS DISTINCT FROM rp_per->>'resultId'
    OR rp_t1->>'pitchEventKind' IS DISTINCT FROM rp_per->>'pitchEventKind'
    OR pg_catalog.jsonb_typeof(rp_before_set) IS DISTINCT FROM 'array'
    OR pg_catalog.jsonb_typeof(rp_rows) IS DISTINCT FROM 'array'
    OR pg_catalog.jsonb_typeof(rp_targets) IS DISTINCT FROM 'array'
    THEN {_REJECT} END IF;
   IF pg_catalog.jsonb_array_length(rp_before_set) NOT BETWEEN 1 AND 3
    OR pg_catalog.jsonb_array_length(rp_rows)<>
     pg_catalog.jsonb_array_length(rp_before_set)
    OR (SELECT pg_catalog.count(DISTINCT m->>'base') FROM
     pg_catalog.jsonb_array_elements(rp_before_set) m)<>
     pg_catalog.jsonb_array_length(rp_before_set)
    THEN {_REJECT} END IF;
   IF rp_per->'runnerEventPayload'->>'kind'='runner-event'
    AND rp_per->'runnerAdvanceOverridesByRunner'->>'kind'='not-applied'
    AND rp_per->'runnerEventPayload'->>'event_kind' IN
     ('strategy-category.steal','pitcher-pickoff-destination.first',
      'pitcher-pickoff-destination.second','pitcher-pickoff-destination.third',
      'catcher-pickoff-destination.first','catcher-pickoff-destination.second',
      'catcher-pickoff-destination.third') THEN
    rp_by:=rp_per->'runnerEventPayload'->'by_runner';
    IF (rp_per->'runnerEventPayload'->>'event_kind'='strategy-category.steal'
      AND ((rp_per->>'kind'='runner-event' AND
       rp_per->>'resultId'='strategy-category.steal' AND
       rp_per->>'pitchEventKind'='non-pitch-event') OR
       (rp_per->>'kind'='batting-result' AND
       rp_per->>'resultId' IN ('batting-result.ball',
        'batting-result.called-pitch','batting-result.swinging-strike',
        'batting-result.walk','batting-result.hit-by-pitch',
        'batting-result.called-strikeout','batting-result.swinging-strikeout',
        'batting-result.k3','batting-result.foul') AND
       rp_per->>'resultId' IS NOT DISTINCT FROM
        rp_t1->'runnerObservation'->>'primaryResultId' AND
       rp_per->>'pitchEventKind'='pitch-event')))
     OR (rp_per->'runnerEventPayload'->>'event_kind'<>'strategy-category.steal'
      AND rp_per->>'kind'='runner-event' AND
      rp_per->>'resultId'=rp_per->'runnerEventPayload'->>'event_kind' AND
      rp_per->>'pitchEventKind'='non-pitch-event') THEN
     NULL;
    ELSE {_REJECT} END IF;
   ELSIF rp_per->'runnerEventPayload'->>'kind'='not-applicable'
    AND rp_per->'runnerAdvanceOverridesByRunner'->>'kind'='overridden'
    AND ((rp_per->>'kind'='batting-result' AND
     rp_per->>'resultId'='batting-result.strikeout-double-play' AND
     rp_per->>'pitchEventKind'='pitch-event') OR
     (rp_per->>'kind'='secondary-result' AND
      ((rp_per->>'resultId' IN
       ('secondary-result.wild-pitch','secondary-result.passed-ball')
       AND rp_per->>'pitchEventKind'='pitch-event') OR
       (rp_per->>'resultId'='secondary-result.balk' AND
        rp_per->>'pitchEventKind'='non-pitch-event')))) THEN
    rp_by:=rp_per->'runnerAdvanceOverridesByRunner'->'by_runner';
   ELSE {_REJECT} END IF;
   IF pg_catalog.jsonb_typeof(rp_by) IS DISTINCT FROM 'object'
    OR (SELECT pg_catalog.count(*) FROM pg_catalog.jsonb_object_keys(rp_by))<>
     pg_catalog.jsonb_array_length(rp_before_set)
    THEN {_REJECT} END IF;
   FOR rp_before IN SELECT value FROM pg_catalog.jsonb_array_elements(rp_before_set)
   LOOP
    rp_slot:=CASE rp_before->>'base' WHEN '1' THEN 'first'
     WHEN '2' THEN 'second' WHEN '3' THEN 'third' ELSE NULL END;
    IF rp_slot IS NULL OR pg_catalog.jsonb_typeof(rp_before) IS DISTINCT FROM 'object'
     THEN {_REJECT} END IF;
    rp_observed:=rp_by->rp_slot;
    rp_effect:=source_row.payload->'calculation'->'response'->'value'->'t1'
     ->'runnerDefaultAdvance'->rp_slot;
    SELECT pg_catalog.count(*),(pg_catalog.jsonb_agg(value))->0
    INTO rp_target_count,rp_record
    FROM pg_catalog.jsonb_array_elements(rp_rows) value
    WHERE value->>'base'=rp_before->>'base';
    IF rp_target_count<>1 OR pg_catalog.jsonb_typeof(rp_observed) IS DISTINCT FROM
     'object' OR pg_catalog.jsonb_typeof(rp_effect) IS DISTINCT FROM 'object'
     OR rp_observed->'runner' IS DISTINCT FROM pg_catalog.jsonb_build_object(
      'kind','official','player_id',rp_before->>'runnerId')
     OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
      pg_catalog.jsonb_object_keys(rp_record) k) IS DISTINCT FROM
      ARRAY['base','id','import_batch_id','play_id','responsible_pitcher_id',
       'retired_at','runner_id','status','status_source','tenant_id']::text[]
     OR rp_record->>'tenant_id' IS DISTINCT FROM p_tenant_id::text
     OR rp_record->>'play_id' IS DISTINCT FROM p->'play_row'->>'id'
     OR rp_record->>'runner_id' IS DISTINCT FROM rp_before->>'runnerId'
     OR rp_record->>'responsible_pitcher_id' IS DISTINCT FROM
      rp_before->>'responsiblePitcherId'
     OR rp_record->'retired_at' IS DISTINCT FROM 'null'::jsonb
     OR rp_record->'import_batch_id' IS DISTINCT FROM 'null'::jsonb
     OR rp_record->>'id' IS NULL
     THEN {_REJECT} END IF;
    SELECT pg_catalog.count(*) INTO rp_target_count FROM
     pg_catalog.jsonb_array_elements(rp_targets) target
     WHERE target=pg_catalog.jsonb_build_object('runner',rp_before->>'base');
    IF rp_observed->>'kind'='hold' THEN
     IF rp_target_count<>0 OR rp_effect->>'modality' IS DISTINCT FROM 'hold'
      OR rp_effect->'destination' IS DISTINCT FROM 'null'::jsonb
      OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
       pg_catalog.jsonb_object_keys(rp_observed) k) IS DISTINCT FROM
       ARRAY['kind','runner']::text[]
      THEN {_REJECT} END IF;
     rp_status:={_quoted(HOLD_STATUS)};
     IF rp_record->>'status_source' IS DISTINCT FROM {_quoted(AUTO_STATUS_SOURCE)}
      THEN {_REJECT} END IF;
    ELSIF rp_observed->>'kind'='safe-advance' THEN
     IF rp_target_count<>0 OR (rp_effect->>'modality' IS DISTINCT FROM 'optional'
      AND rp_effect->>'modality' IS DISTINCT FROM 'forced')
      OR rp_effect->>'destination' IS DISTINCT FROM
       CASE rp_observed->>'destination' WHEN 'second' THEN '2'
        WHEN 'third' THEN '3' WHEN 'home' THEN '4' ELSE NULL END
      OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
       pg_catalog.jsonb_object_keys(rp_observed) k) IS DISTINCT FROM
       ARRAY['destination','kind','runner']::text[]
      THEN {_REJECT} END IF;
     rp_status:={_advance_status_case()};
     IF rp_record->>'status_source' IS DISTINCT FROM {_quoted(MANUAL_STATUS_SOURCE)}
      THEN {_REJECT} END IF;
    ELSIF rp_observed->>'kind'='out' THEN
     IF rp_target_count<>1 OR rp_observed->>'attempted_base' IS NULL
      OR rp_observed->>'attempted_base' NOT IN
      ('first','second','third','home')
      OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
       pg_catalog.jsonb_object_keys(rp_observed) k) IS DISTINCT FROM
       ARRAY['attempted_base','kind','out_kind','runner']::text[]
      THEN {_REJECT} END IF;
     rp_status:={_out_status_case()};
     rp_out_count:=rp_out_count+1;
     IF rp_record->>'status_source' IS DISTINCT FROM {_quoted(MANUAL_STATUS_SOURCE)}
      THEN {_REJECT} END IF;
    ELSE {_REJECT} END IF;
    IF rp_status IS NULL OR rp_record->>'status' IS DISTINCT FROM rp_status
     THEN {_REJECT} END IF;
   END LOOP;
   IF rp_out_count IS DISTINCT FROM (SELECT pg_catalog.count(*) FROM
    pg_catalog.jsonb_array_elements(rp_targets) target
    WHERE pg_catalog.jsonb_typeof(target)='object')
    OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(rp_targets) target
     WHERE pg_catalog.jsonb_typeof(target)='object' AND
     (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
      pg_catalog.jsonb_object_keys(target) k) IS DISTINCT FROM ARRAY['runner']::text[])
    THEN {_REJECT} END IF;
  END;
 END IF;
"""


def overlay_prepared_parent(parent_body: str, declaration: dict[str, object]) -> str:
    """親完全値と登録宣言を照合してv3 RunnerEvent部だけを置換する。"""
    if (
        hashlib.sha256(parent_body.encode()).hexdigest() != PARENT_SHA256
        or declaration.get("function_id") != FUNCTION_ID
        or _canonical_hash(declaration) != PARENT_DECLARATION_HASH
    ):
        raise ValueError("走者物理証拠の親本文または宣言が不一致")
    marker = _OLD_RUNNER_END
    if parent_body.count(marker) != 1:
        raise ValueError("v3走者検査の終端が不一致")
    end = parent_body.index(marker)
    begin = parent_body.rfind(_OLD_RUNNER_START, 0, end)
    if begin < 0:
        raise ValueError("v3走者検査の始点が不一致")
    old_checks = parent_body[begin:end]
    if (
        not old_checks.startswith("\n OR ")
        or old_checks.count("runnerAdvanceOverrides") != 4
    ):
        raise ValueError("旧走者検査の構造が不一致")
    guarded = (
        "\n OR (CASE WHEN source_row.payload->'calculation'->'request'->'t1' "
        "? 'runnerObservation' THEN false ELSE ("
        + old_checks.removeprefix("\n OR ")
        + ") END)"
    )
    replaced = parent_body[:begin] + guarded + parent_body[end:]
    insertion = replaced.index(marker) + len(marker)
    return replaced[:insertion] + _runner_evidence_block() + replaced[insertion:]
