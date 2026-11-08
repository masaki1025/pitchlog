"""固定済み凡打profileへ、打球群の原観測と物理行の照合を接合する。"""

import hashlib

from pitchlog.authz.batted_out_evidence_sql import (
    _NEW_OBSERVATION as _PARENT_OBSERVATION,
)
from pitchlog.authz.batted_out_evidence_sql import (
    FUNCTION_ID,
    PARENT_DECLARATION_HASH,
)
from pitchlog.domaingen.core import _canonical_hash
from pitchlog.sync.runner_physical_labels import OUT_STATUS_BY_OBSERVED_KIND

PARENT_SHA256 = "4585f18ac1506baf5e8cf2f8c6ed3c4c5dfd00974c18f1da5495365f83684f47"
_START = " -- 新安打だけの閉分岐。旧writer/原本/nonce検査は変更しない。"
_END = "  THEN RAISE EXCEPTION 'batted hit physical source rejected'"
_TAIL = "'batting-result.home-run','batting-result.batted-out')"
_RESULTS = (
    "batting-result.batted-reach",
    "batting-result.fielders-choice",
    "batting-result.sacrifice-bunt",
    "batting-result.sacrifice-fly",
    "batting-result.double-play",
    "batting-result.sacrifice-bunt-error",
    "batting-result.error",
)
_NO_ERROR = """  OR batted_obs->'officialScoringPayload' IS DISTINCT FROM
  '{"kind":"no-error","errorCount":"0","fielders":[]}'::jsonb"""
_SCORING = """  OR batted_obs->'officialScoringPayload' IS DISTINCT FROM
   (CASE WHEN batted_obs->>'resultId' IN
    ('batting-result.sacrifice-bunt-error','batting-result.error')
    THEN pg_catalog.jsonb_build_object('kind','error-recorded','errors',
     pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
      'fielder',pg_catalog.jsonb_build_object('kind','official',
       'player_id',p->'play_row'->>'resolved_error_player_id'),'count',1)))
    ELSE '{"kind":"no-error","errorCount":"0","fielders":[]}'::jsonb END)"""
_TAG_PREFIX = (
    "  OR source_row.payload->'calculation'->'request'->'t1'->>"
    "'officialScoringPayload'\n"
)
_OLD_TAG = _TAG_PREFIX + "  IS DISTINCT FROM 'no-error'"
_TAG = (
    _TAG_PREFIX
    + """  IS DISTINCT FROM (CASE
   WHEN batted_obs->>'resultId' IN
    ('batting-result.sacrifice-bunt-error','batting-result.error')
   THEN 'error-recorded' ELSE 'no-error' END)"""
)
_OBSERVATION = """  OR (batted_obs->>'resultId'='batting-result.batted-out' AND
   before_cp->'after'->'stateFields'->>'state.outs' NOT IN ('0','1','2'))
  OR batted_obs->'thirdOutObservation' IS DISTINCT FROM
   (CASE WHEN batted_obs->>'resultId'='batting-result.batted-out'
    AND before_cp->'after'->'stateFields'->>'state.outs'='2'
   THEN pg_catalog.jsonb_build_object('kind','batter-before-first',
    'batter',pg_catalog.jsonb_build_object('kind','official',
      'player_id',p->'play_row'->>'batter_id'))
   ELSE '{"kind":"none"}'::jsonb END)"""
_EXTRA = """
  OR (batted_obs ? 'outRunner') IS DISTINCT FROM
     (batted_obs->>'resultId'='batting-result.double-play')
  OR batted_obs->'outRunner' IS DISTINCT FROM
     source_row.payload->'calculation'->'request'->'t1'->'outRunner'
  OR (batted_obs ? 'outRunner' AND batted_obs->'outRunner' IS DISTINCT FROM
   pg_catalog.jsonb_build_object('base','1','outKind','force-out','runnerId',
    (SELECT r->>'runnerId' FROM pg_catalog.jsonb_array_elements(
     before_cp->'runners') r WHERE r->>'base'='1')))
  OR (batted_obs ? 'outRunner' AND NOT EXISTS(SELECT 1
   FROM pg_catalog.jsonb_array_elements(before_cp->'runners') r
   WHERE r->>'base'='1' AND r->>'runnerId' IS NOT NULL))
  OR batted_obs->'rbiRulingByRunner' IS DISTINCT FROM
     source_row.payload->'calculation'->'request'->'t1'->'rbiRulingByRunner'
  OR (batted_obs ? 'rbiRulingByRunner' AND (
   pg_catalog.jsonb_typeof(batted_obs->'rbiRulingByRunner') IS DISTINCT FROM 'object'
   OR batted_obs->'rbiRulingByRunner'='{}'::jsonb
   OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_each_text(CASE
    WHEN pg_catalog.jsonb_typeof(batted_obs->'rbiRulingByRunner')='object'
    THEN batted_obs->'rbiRulingByRunner' ELSE '{}'::jsonb END) r
    WHERE r.key NOT IN ('1','2','3')
     OR r.value IS NULL
     OR r.value NOT IN ('ordinary-play','kept-running','stopped-and-restarted'))))
  OR (batted_obs ? 'rbiRulingByRunner' AND
   (SELECT pg_catalog.array_agg(k ORDER BY k)
    FROM pg_catalog.jsonb_object_keys(CASE
     WHEN pg_catalog.jsonb_typeof(batted_obs->'rbiRulingByRunner')='object'
     THEN batted_obs->'rbiRulingByRunner' ELSE '{}'::jsonb END) k)
   IS DISTINCT FROM
   (SELECT pg_catalog.array_agg(e->>'base' ORDER BY e->>'base')
    FROM pg_catalog.jsonb_array_elements(CASE
     WHEN pg_catalog.jsonb_typeof(source_row.payload->'calculation'->'response'
      ->'value'->'runnerScoreEffects')='array'
     THEN source_row.payload->'calculation'->'response'->'value'->'runnerScoreEffects'
     ELSE '[]'::jsonb END) e WHERE e->'validRun'='true'::jsonb))
  OR (batted_obs->>'resultId'<>'batting-result.home-run'
   AND before_cp->'after'->'stateFields'->'state.score' IS DISTINCT FROM
    source_row.payload->'calculation'->'response'->'value'->'t1'
     ->'after'->'stateFields'->'state.score'
   AND NOT (batted_obs ? 'rbiRulingByRunner'))
  OR (batted_obs->>'resultId' IN
   ('batting-result.sacrifice-bunt-error','batting-result.error') AND (
   p->'play_row'->>'resolved_error_player_id' IS NULL
   OR p->'play_row'->'error_type' IS DISTINCT FROM 'null'::jsonb
   OR p->'play_row'->'raw_error_position' IS DISTINCT FROM 'null'::jsonb
   OR NOT EXISTS(SELECT 1
    FROM pg_catalog.jsonb_array_elements(p->'roster'->'teams') team,
    LATERAL pg_catalog.jsonb_array_elements(team->'participants') player
    WHERE team->>'side'=(CASE before_cp->'after'->'stateFields'->>'state.half'
     WHEN 'top' THEN 'home' WHEN 'bottom' THEN 'away' ELSE '' END)
     AND player->'player'->>'player_id'=p->'play_row'->>'resolved_error_player_id'
     AND EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(player->'roles') role
      WHERE role->>'kind'='fielding'))))
  OR (batted_obs->>'resultId' NOT IN
   ('batting-result.sacrifice-bunt-error','batting-result.error') AND
   p->'play_row'->'resolved_error_player_id' IS DISTINCT FROM 'null'::jsonb)
"""

_EFFECT = """source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)"""
_DP = """(source_row.payload->>'formatVersion'='play-prefix-play-v3'
 AND source_row.payload->'observations'->>'resultId'='batting-result.double-play'
 AND before_cp->'after'->'stateFields'->>'state.outs'='0'
 AND before_cp->'after'->'stateFields'->>'state.runners'='first'
 AND source_row.payload->'calculation'->'response'->'value'->'t1'->'outEffect'
  ='{"count":"2","targets":["batter",{"runner":"1"}]}'::jsonb)"""
_DP_ROW = (
    _DP
    + """ AND m->>'base'='1' AND m->>'runnerId'=
 source_row.payload->'observations'->'outRunner'->>'runnerId'"""
)
_HOLD = (
    """source_row.payload->>'formatVersion'='play-prefix-play-v3'
 AND source_row.payload->'observations' ? 'battedBall'
 AND source_row.payload->'calculation'->'request'->'t1'
  ->'runnerAdvanceOverrides'->>'kind'='applied'
 AND o->>'runnerBase'=m->>'base' AND o->>'destination'=m->>'base'
 AND """
    + _EFFECT
    + "->>'modality'='hold'\n AND "
    + _EFFECT
    + "->'destination'='null'::jsonb"
)


def _physical_replacements() -> tuple[tuple[str, str], ...]:
    """同塁の明示観測と、唯一T1で確定した一塁封殺だけを旧照合へ足す。"""
    status = " AND r->>'status'=(CASE\n"
    manual = " AND r->>'status_source'=(CASE WHEN EXISTS(SELECT 1 FROM\n"
    equal = (
        " WHERE o->>'runnerBase'=m->>'base' AND o->>'destination'=\n "
        + _EFFECT
        + "->>'destination')"
    )
    different = (
        " WHERE o->>'runnerBase'=m->>'base' AND o->>'destination' IS DISTINCT FROM\n "
        + _EFFECT
        + "->>'destination')"
    )
    targets = """ OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(
 source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'outEffect'->'targets') target WHERE pg_catalog.jsonb_typeof(target)='object'
 AND target ? 'runner')"""
    label = OUT_STATUS_BY_OBSERVED_KIND["force-out"]
    if any(char in label for char in ("'", "\\", "\x00")):
        raise ValueError("封殺の保存ラベルが閉集合外")
    return (
        (status, status + " WHEN (" + _DP_ROW + ") THEN '" + label + "'\n"),
        (
            manual,
            " AND r->>'status_source'=(CASE WHEN ("
            + _DP_ROW
            + ") OR EXISTS(SELECT 1 FROM\n",
        ),
        (
            equal,
            " WHERE o->>'runnerBase'=m->>'base' AND (o->>'destination'=\n "
            + _EFFECT
            + "->>'destination' OR ("
            + _HOLD
            + ")))",
        ),
        (different, different[:-1] + " AND NOT (" + _HOLD + "))"),
        (
            targets,
            targets.replace(" OR EXISTS(", " OR (EXISTS(", 1) + " AND NOT " + _DP + ")",
        ),
    )


def overlay_prepared_parent(parent: str, declaration: dict[str, object]) -> str:
    """同じ宣言と固定親だけを変換し、観測範囲外の本文を保持する。"""
    if (
        hashlib.sha256(parent.encode()).hexdigest() != PARENT_SHA256
        or declaration.get("function_id") != FUNCTION_ID
        or _canonical_hash(declaration) != PARENT_DECLARATION_HASH
        or parent.count(_START) != 1
        or parent.count(_END) != 1
    ):
        raise ValueError("打球群の親本文または宣言が不一致")
    physical = parent
    for old, new in _physical_replacements():
        if physical.count(old) != 3:
            raise ValueError("打球群の親物理条件が不一致")
        physical = physical.replace(old, new)
    start, end = physical.index(_START), physical.index(_END)
    section = physical[start:end]
    replacements = (
        (_TAIL, _TAIL[:-1] + "," + ",".join(repr(v) for v in _RESULTS) + ")", 2),
        (
            "pg_catalog.jsonb_object_keys(batted_obs) k)",
            "pg_catalog.jsonb_object_keys("
            "batted_obs - 'outRunner' - 'rbiRulingByRunner') k)",
            1,
        ),
        (_PARENT_OBSERVATION, _OBSERVATION, 1),
        (_NO_ERROR, _SCORING, 1),
        (_OLD_TAG, _TAG, 1),
    )
    for old, new, count in replacements:
        if section.count(old) != count:
            raise ValueError("打球群の親観測条件が不一致")
        section = section.replace(old, new)
    return physical[:start] + section + _EXTRA + physical[end:]
