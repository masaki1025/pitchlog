"""現行走者検査を保持した親へ、凡打死の明示観測だけを接合する。"""

import hashlib

from pitchlog.domaingen.core import _canonical_hash

FUNCTION_ID = (
    "FUNCTION:sync_right_api:prepare_play_prefix_projection("
    "uuid, uuid, uuid, bytea, uuid, uuid, text)"
)
PARENT_SHA256 = "f6c227618b469e6484b1490d1df682bb0f91068342d465130413bc13862337aa"
PARENT_DECLARATION_HASH = (
    "sha256:29e1640b9b1d35e2310a7abee23b8272abd65dc41dd848d96402aaf16788a005"
)
_START = " -- 新安打だけの閉分岐。旧writer/原本/nonce検査は変更しない。"
_END = "  THEN RAISE EXCEPTION 'batted hit physical source rejected'"
_OLD_OBSERVATION = (
    "  OR batted_obs->'thirdOutObservation' IS DISTINCT FROM "
    '\'{"kind":"none"}\'::jsonb'
)
_NEW_OBSERVATION = """  OR (
   batted_obs->>'resultId'='batting-result.batted-out' AND (
    before_cp->'after'->'stateFields'->>'state.runners' IS DISTINCT FROM 'empty'
    OR before_cp->'after'->'stateFields'->>'state.outs' NOT IN ('0','1','2')
    OR source_row.payload->'calculation'->'request'->'t1'->>'runnerAdvanceOverrides'
       IS DISTINCT FROM 'not-applied'
    OR batted_obs->'runnerAdvanceOverridesByRunner'
       IS DISTINCT FROM '{"kind":"not-applied","overrides":[]}'::jsonb
   ))
  OR batted_obs->'thirdOutObservation' IS DISTINCT FROM
   (CASE WHEN batted_obs->>'resultId'='batting-result.batted-out'
    AND before_cp->'after'->'stateFields'->>'state.outs'='2'
   THEN pg_catalog.jsonb_build_object('kind','batter-before-first',
    'batter',pg_catalog.jsonb_build_object('kind','official',
      'player_id',p->'play_row'->>'batter_id'))
   ELSE '{"kind":"none"}'::jsonb END)"""
_OLD_T1 = (
    "  OR source_row.payload->'calculation'->'request'->'t1'->>'thirdOutObservation'\n"
    "  IS DISTINCT FROM 'none'"
)
_NEW_T1 = (
    "  OR source_row.payload->'calculation'->'request'->'t1'->>'thirdOutObservation'\n"
    "  IS DISTINCT FROM batted_obs->'thirdOutObservation'->>'kind'"
)


def overlay_prepared_parent(parent: str, declaration: dict[str, object]) -> str:
    """固定親/宣言と3置換だけを許し、以前の走者・権限検査を保持する。"""
    if (
        hashlib.sha256(parent.encode()).hexdigest() != PARENT_SHA256
        or declaration.get("function_id") != FUNCTION_ID
        or _canonical_hash(declaration) != PARENT_DECLARATION_HASH
        or parent.count(_START) != 1
        or parent.count(_END) != 1
    ):
        raise ValueError("凡打の親本文または宣言が不一致")
    start, end = parent.index(_START), parent.index(_END)
    section = parent[start:end]
    if (
        section.count("'batting-result.home-run')") != 2
        or section.count(_OLD_OBSERVATION) != 1
        or section.count(_OLD_T1) != 1
    ):
        raise ValueError("凡打の親観測条件が不一致")
    section = section.replace(
        "'batting-result.home-run')",
        "'batting-result.home-run','batting-result.batted-out')",
    )
    section = section.replace(_OLD_OBSERVATION, _NEW_OBSERVATION, 1)
    section = section.replace(_OLD_T1, _NEW_T1, 1)
    return parent[:start] + section + parent[end:]
