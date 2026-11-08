"""固定済み打球群prepareに、妨害の原裁定と物理行の証拠を接ぐ。"""

import hashlib

from pitchlog.authz.batted_operations_evidence_sql import (
    _DP,
    FUNCTION_ID,
    PARENT_DECLARATION_HASH,
)
from pitchlog.domaingen.core import _canonical_hash
from pitchlog.sync.runner_physical_labels import INTERFERENCE_OUT_STATUS

PARENT_SHA256 = "c2758d69d452fba961fc63459e84e951a2600129a4cf65c03aedaa44f5afc55f"

_T1 = "source_row.payload->'calculation'->'request'->'t1'"
_RULING = _T1 + "->'interferenceRuling'"
_OBS = "source_row.payload->'observations'"
_EFFECT = "source_row.payload->'calculation'->'response'->'value'->'t1'"
_OUT_LABEL = INTERFERENCE_OUT_STATUS
_PERSON = "pg_catalog.jsonb_build_object('kind','runner','runner_id'," \
    "pg_catalog.jsonb_build_object('kind','official','player_id',m->>'runnerId'))"
_ADJUDICATED = (
    "(source_row.payload->>'formatVersion'='play-prefix-play-v3'"
    " AND " + _T1 + "->>'eventKind'='secondary-result'"
    " AND " + _T1 + "->>'resultId' IN"
    " ('secondary-result.obstruction','secondary-result.offensive-interference')"
    " AND " + _RULING + " IS NOT DISTINCT FROM " + _OBS + "->'interferenceRuling')"
)
_OUT = (
    "(" + _ADJUDICATED + " AND EXISTS(SELECT 1 FROM"
    " pg_catalog.jsonb_array_elements(" + _EFFECT + "->'outEffect'->'targets') target"
    " WHERE target=pg_catalog.jsonb_build_object('runner',m->>'base'))"
    " AND EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements("
    + _RULING + "->'out_targets') person WHERE person=" + _PERSON + "))"
)


def _admission_out(source_runners: str) -> str:
    """外側admissionで、全アウト走者を元原本・物理行・裁定へ束縛する。"""
    return (
        "(" + _ADJUDICATED
        + " AND NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements("
        + _EFFECT + "->'outEffect'->'targets') out_target"
        " WHERE pg_catalog.jsonb_typeof(out_target)='object'"
        " AND out_target ? 'runner' AND NOT EXISTS(SELECT 1 FROM"
        " pg_catalog.jsonb_array_elements(" + source_runners + ") m,"
        " pg_catalog.jsonb_array_elements(after_cp->'projection_snapshot'"
        "->'play_runners') r WHERE out_target="
        "pg_catalog.jsonb_build_object('runner',m->>'base')"
        " AND m->>'base' IN ('1','2','3')"
        " AND r->>'base'=m->>'base'"
        " AND r->>'runner_id'=m->>'runnerId'"
        " AND r->>'responsible_pitcher_id'=m->>'responsiblePitcherId'"
        " AND r->>'tenant_id'=p_tenant_id::text"
        " AND r->>'play_id'=p->'play_row'->>'id'"
        " AND r->'retired_at'='null'::jsonb"
        " AND r->>'status'='" + _OUT_LABEL + "'"
        " AND r->>'status_source'='manual'"
        " AND EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements("
        + _RULING + "->'out_targets') person WHERE person="
        + _PERSON + "))))"
    )


_OUT_ADMISSIONS = (
    _admission_out("before_cp->'content'->'restored'->'runners'"),
    _admission_out("source_row.payload->'calculation'->'request'->'source'->'runners'"),
    _admission_out("source_row.payload->'calculation'->'request'->'source'->'runners'"),
)
_PLACEMENT = (
    "(" + _ADJUDICATED + " AND EXISTS(SELECT 1 FROM"
    " pg_catalog.jsonb_array_elements(CASE WHEN " + _RULING
    + "->>'kind'='obstruction' THEN " + _RULING
    + "->'awarded_destinations' ELSE " + _RULING
    + "->'return_bases' END) placement WHERE placement->'person'=" + _PERSON
    + " AND (CASE placement->>'destination' WHEN 'first' THEN '1'"
    " WHEN 'second' THEN '2' WHEN 'third' THEN '3' WHEN 'home' THEN '4'"
    " ELSE NULL END)=COALESCE(" + _EFFECT
    + "->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'"
    " WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'destination',"
    " m->>'base')))"
)
_PENALTY_THIRD = (
    "(source_row.payload->>'formatVersion'='play-prefix-play-v3'"
    " AND " + _T1 + "->>'resultId'='secondary-result.batting-interference'"
    " AND " + _RULING + " IS NOT DISTINCT FROM " + _OBS
    + "->'interferenceRuling' AND m->>'base'='3' AND " + _RULING
    + "->'third_base_scoring_attempt'->>'value' IN ('squeeze','steal-home')"
    " AND " + _EFFECT
    + "->'runnerDefaultAdvance'->'third'->>'destination'='4')"
)
_BATTED_RULING = """  OR (
   (batted_obs->'interferenceRuling' IS DISTINCT FROM '{"kind":"not-required"}'::jsonb
    OR source_row.payload->'calculation'->'request'->'t1'->>'interferenceRuling'
       IS DISTINCT FROM 'not-required') AND (
    batted_obs->'interferenceRuling' IS NOT DISTINCT FROM
     source_row.payload->'calculation'->'request'->'t1'->'interferenceRuling'
    AND batted_obs->'interferenceRuling'->>'kind'='batting-interference'
    AND batted_obs->'interferenceRuling'->'adopted'=
     pg_catalog.jsonb_build_object('kind','play-result','resultId',batted_obs->>'resultId'))
     IS NOT TRUE)"""

_SECONDARY_GUARD = """
 IF source_row.payload->'calculation'->'request'->'t1'->>'resultId'
 IN ('secondary-result.batting-interference','secondary-result.obstruction',
     'secondary-result.offensive-interference')
 OR batted_obs->>'resultId' IN
 ('secondary-result.batting-interference','secondary-result.obstruction',
  'secondary-result.offensive-interference') THEN
  IF source_row.payload->>'formatVersion' IS DISTINCT FROM 'play-prefix-play-v3'
  OR source_row.payload->'calculation'->'request'->'t1'->>'eventKind'
   IS DISTINCT FROM 'secondary-result'
  OR source_row.payload->'calculation'->'request'->'t1'->>'pitchEventKind'
   IS DISTINCT FROM 'pitch-event'
  OR batted_obs->>'resultId' IS DISTINCT FROM
   source_row.payload->'calculation'->'request'->'t1'->>'resultId'
  OR batted_obs->'interferenceRuling' IS DISTINCT FROM
   source_row.payload->'calculation'->'request'->'t1'->'interferenceRuling'
  OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
   pg_catalog.jsonb_object_keys(batted_obs) k) IS DISTINCT FROM
   ARRAY['battingSide','course','interferenceRuling','pitchSpeed',
    'pitchTypeKey','resultId','stance']::text[]
  OR p->'play_row'->>'event_kind' IS DISTINCT FROM 'pitch'
  OR p->'play_row'->'batting_result_key' IS DISTINCT FROM 'null'::jsonb
  OR p->'play_row'->>'secondary_batting_result_key' IS DISTINCT FROM
   batted_obs->>'resultId'
  OR p->'play_row'->>'pitch_type_key' IS DISTINCT FROM batted_obs->>'pitchTypeKey'
  OR p->'play_row'->'raw_fielder_position' IS DISTINCT FROM 'null'::jsonb
  OR p->'play_row'->'resolved_fielder_id' IS DISTINCT FROM 'null'::jsonb
  OR p->'play_row'->'resolved_error_player_id' IS DISTINCT FROM 'null'::jsonb
  OR p->'play_row'->'batted_ball_type' IS DISTINCT FROM 'null'::jsonb
  OR p->'play_row'->'batted_ball_strength' IS DISTINCT FROM 'null'::jsonb
  OR p->'play_row'->'hit_x' IS DISTINCT FROM 'null'::jsonb
  OR p->'play_row'->'hit_y' IS DISTINCT FROM 'null'::jsonb
  OR (batted_obs->>'resultId'='secondary-result.batting-interference'
   AND (batted_obs->'interferenceRuling'->>'kind' IS DISTINCT FROM
    'batting-interference' OR batted_obs->'interferenceRuling'->'adopted'
    IS DISTINCT FROM '{"kind":"penalty-award"}'::jsonb))
  OR (batted_obs->>'resultId'='secondary-result.obstruction' AND
   batted_obs->'interferenceRuling'->>'kind' IS DISTINCT FROM 'obstruction')
  OR (batted_obs->>'resultId'='secondary-result.offensive-interference' AND
   batted_obs->'interferenceRuling'->>'kind' IS DISTINCT FROM
    'offensive-interference')
  THEN RAISE EXCEPTION 'interference physical source rejected'
   USING ERRCODE='42501'; END IF;
 END IF;
"""


def overlay_prepared_parent(parent: str, declaration: dict[str, object]) -> str:
    """親全byte/宣言を固定し、現行prepareの妨害証拠だけを追補する。"""
    if (
        hashlib.sha256(parent.encode()).hexdigest() != PARENT_SHA256
        or declaration.get("function_id") != FUNCTION_ID
        or _canonical_hash(declaration) != PARENT_DECLARATION_HASH
        or any(char in _OUT_LABEL for char in ("'", "\\", "\x00"))
    ):
        raise ValueError("妨害prepareの固定親または宣言が不一致")
    old_status = " AND r->>'status'=(CASE\n"
    old_source = " AND r->>'status_source'=(CASE WHEN (("
    old_dp = " AND (" + _DP + ") IS NOT TRUE"
    old_ruling = (
        "  OR batted_obs->'interferenceRuling' IS DISTINCT FROM "
        "'{\"kind\":\"not-required\"}'::jsonb"
    )
    old_t1 = (
        "  OR source_row.payload->'calculation'->'request'->'t1'->>"
        "'interferenceRuling'\n  IS DISTINCT FROM 'not-required'"
    )
    old_second = (
        "  OR p->'play_row'->>'batting_result_key' IS DISTINCT FROM"
        " batted_obs->>'resultId'"
    )
    end = (
        "THEN RAISE EXCEPTION 'batted hit physical source rejected'\n"
        "  USING ERRCODE='42501'; END IF;\n END IF;\n"
        " SELECT c.* INTO current_cp"
    )
    if (
        parent.count(old_status) != 3
        or parent.count(old_source) != 3
        or parent.count(old_dp) != 3
        or parent.count(old_ruling) != 1
        or parent.count(old_t1) != 1
        or parent.count(old_second) != 1
        or parent.count(end) != 1
    ):
        raise ValueError("妨害prepareの有限置換位置が不一致")
    changed = parent.replace(
        old_status,
        old_status + " WHEN " + _OUT + " THEN '" + _OUT_LABEL + "'\n",
    )
    changed = changed.replace(
        old_source,
        " AND r->>'status_source'=(CASE WHEN ("
        + _OUT + " OR " + _PLACEMENT + " OR " + _PENALTY_THIRD
        + ") OR ((",
    )
    outer_parts = changed.split(old_dp)
    if len(outer_parts) != 4:
        raise ValueError("妨害prepareの外側証拠位置が不一致")
    changed = outer_parts[0]
    for expression, remainder in zip(_OUT_ADMISSIONS, outer_parts[1:], strict=True):
        changed += " AND ((" + _DP + " OR " + expression + ")) IS NOT TRUE"
        changed += remainder
    changed = changed.replace(old_ruling, _BATTED_RULING)
    changed = changed.replace(old_t1, "")
    changed = changed.replace(
        old_second,
        old_second
        + "\n  OR p->'play_row'->'secondary_batting_result_key' IS DISTINCT FROM"
        " (CASE WHEN batted_obs->'interferenceRuling'->>'kind'="
        "'batting-interference' THEN '" + '"secondary-result.batting-interference"'
        + "'::jsonb ELSE 'null'::jsonb END)",
    )
    return changed.replace(
        end,
        end.replace(
            " SELECT c.* INTO current_cp",
            _SECONDARY_GUARD + " SELECT c.* INTO current_cp",
        ),
    )
