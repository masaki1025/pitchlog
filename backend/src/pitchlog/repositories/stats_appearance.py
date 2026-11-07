"""D03の版付き集合を真正RR scopeへ束縛する有限read候補。未登録は拒否。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from pitchlog.repositories.tokens import TenantOperationToken
from pitchlog.stats.pitcher_appearance_source import PitcherAppearanceSourceUnavailable


@dataclass(frozen=True, slots=True)
class ReadPitcherEntryPageToken(TenantOperationToken):
    """固定readの候補値。UUIDだけでは認可資格にならない。"""

    game_id: UUID
    fact_version_id: UUID
    revision: int
    source_set_sha256: str
    after_proof_sha256: str | None = None
    page_size: int = 500

    @property
    def capability_id(self) -> str:
        """正式受理されるまで未登録の固定能力。"""
        return "CAP:pitcher_appearance:read"

    def __post_init__(self) -> None:
        """型/有限page/正準cursorを閉じ、変更済みtokenも再検査できる。"""
        if (
            type(self.game_id) is not UUID
            or type(self.fact_version_id) is not UUID
            or type(self.revision) is not int
            or not 0 < self.revision < 2**63
            or type(self.source_set_sha256) is not str
            or re.fullmatch(r"[a-f0-9]{64}", self.source_set_sha256) is None
            or type(self.page_size) is not int
            or not 1 <= self.page_size <= 500
            or (
                self.after_proof_sha256 is not None
                and (
                    type(self.after_proof_sha256) is not str
                    or re.fullmatch(r"[a-f0-9]{64}", self.after_proof_sha256) is None
                )
            )
        ):
            raise PitcherAppearanceSourceUnavailable("登板readの入力が不一致です")


def read_pitcher_entry_page(handle: object, token: ReadPitcherEntryPageToken):
    """実stats RR/ROと同handleだけを許し、未登録tokenを迂回しない。"""
    from pitchlog.repositories import transaction

    if type(token) is not ReadPitcherEntryPageToken:
        raise PitcherAppearanceSourceUnavailable("登板readのtoken型が不一致です")
    token.__post_init__()
    transaction._require_stats_primitive_read_scope(handle)
    # 正式registry/function/provider接合までは通常runが閉拒否する。直接SQLへ落とさない。
    return cast(transaction._TenantTransaction, handle).run(token)


@dataclass(frozen=True, slots=True)
class PersistStartPitcherEntryToken(TenantOperationToken):
    """真正開始actorへrootが有限登録する保存1操作の候補。"""

    attempt_id: UUID
    generation: int

    def __post_init__(self) -> None:
        """固定ownerのUUIDと正generation以外を実行へ渡さない。"""
        if (
            type(self.attempt_id) is not UUID
            or type(self.generation) is not int
            or not 0 < self.generation < 2**63
        ):
            raise PitcherAppearanceSourceUnavailable("開始entry tokenの型が不一致です")

    @property
    def capability_id(self) -> str:
        """初期権actorだけの固定能力。未登録のままでは実行不可。"""
        return "CAP:initial_right:persist_start_pitcher_entry"


def persist_start_pitcher_entry(scope: object) -> str:
    """同actor/同ownerでのみ固定保存を呼び、未登録を直接SQLで迂回しない。"""
    from pitchlog.repositories.initial_recording_right import InitialRecordingRightScope
    from pitchlog.stats.pitcher_appearance_source import capture_start_transition

    values = capture_start_transition(scope)
    actual = cast(InitialRecordingRightScope, scope)
    actual._check()
    token = PersistStartPitcherEntryToken(
        cast(UUID, values["source_id"]), cast(int, values["internal_generation"])
    )
    rows = actual._transaction.run_function(token).rows
    actual._check()
    if (
        type(rows) is not tuple
        or len(rows) != 1
        or type(rows[0]) is not tuple
        or len(rows[0]) != 1
        or type(rows[0][0]) is not str
        or re.fullmatch(r"[a-f0-9]{64}", rows[0][0]) is None
    ):
        raise PitcherAppearanceSourceUnavailable("開始entryの保存印が不一致です")
    return rows[0][0]


def candidate_start_entry_function() -> str:
    """同TX実原本から唯一projectorを再利用する開始保存候補を描画する。"""
    import hashlib

    from pitchlog.domaingen.stats_appearance import generate_appearance_bundle
    from pitchlog.domainrt.host import _product_artifact_paths, _verified_source

    artifact = hashlib.sha256(
        _verified_source(*_product_artifact_paths()).encode()
    ).hexdigest()
    bundle, _ = generate_appearance_bundle()
    query = bundle["backend/src/pitchlog/stats/generated/pitcher_entry_projection.sql"]
    return f"""CREATE FUNCTION initial_right_api.persist_start_pitcher_entry(
 p_tenant_id uuid,p_attempt_id uuid,p_generation bigint)
RETURNS TABLE(proof_sha256 text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $d03_start$
#variable_conflict use_column
DECLARE v_tenant uuid; v_game uuid; v_device uuid; v_home uuid; v_away uuid;
 v_fingerprint text; v_own_xid numeric; v_home_pitcher uuid; v_away_pitcher uuid;
 v_entry jsonb; v_proof jsonb; v_digest text;
BEGIN
 v_tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 v_own_xid:=pg_catalog.pg_current_xact_id()::text::numeric;
 IF session_user IS DISTINCT FROM 'pitchlog_initial_actor'
 OR current_user IS DISTINCT FROM 'pitchlog_initial_fn_owner'
 OR v_tenant IS NULL OR p_tenant_id IS DISTINCT FROM v_tenant
 OR p_attempt_id IS NULL OR p_generation IS NULL
 OR p_generation<1 OR pg_catalog.current_setting('transaction_read_only')<>'off'
 THEN RAISE EXCEPTION 'pitcher entry start boundary rejected'
 USING ERRCODE='42501'; END IF;
 SELECT a.game_id,a.device_id,g.home_team_record_id,g.away_team_record_id,
 pg_catalog.encode(r.request_digest,'hex')
 INTO STRICT v_game,v_device,v_home,v_away,v_fingerprint
 FROM public.game_start_attempts a
 JOIN public.game_start_requests r
 ON (r.tenant_id,r.game_id,r.start_request_id,r.device_id)=
 (a.tenant_id,a.game_id,a.start_request_id,a.device_id)
 JOIN public.games g ON g.tenant_id=a.tenant_id AND g.id=a.game_id
 JOIN public.recording_generations rg
 ON rg.tenant_id=a.tenant_id AND rg.game_id=a.game_id
 WHERE a.tenant_id=v_tenant AND a.attempt_id=p_attempt_id AND a.outcome='committed'
 AND a.xmin::text::numeric=pg_catalog.mod(v_own_xid,4294967296::numeric)
 AND rg.generation=p_generation AND rg.kind='normal' AND rg.revoked_at IS NULL
 AND rg.holder_device=a.device_id::text
 AND rg.confirmed_watermark=0 AND rg.applied_prefix=0
 AND rg.xmin::text::numeric=pg_catalog.mod(v_own_xid,4294967296::numeric)
 AND g.status='in_progress' AND g.started_at IS NOT NULL
 AND g.xmin::text::numeric=pg_catalog.mod(v_own_xid,4294967296::numeric);
 SELECT (entries.value->>'player_id')::uuid INTO STRICT v_home_pitcher
 FROM public.game_lineups l CROSS JOIN LATERAL
 pg_catalog.jsonb_array_elements(l.entries_with_uniform_number_snapshot)
 AS entries(value)
 WHERE l.tenant_id=v_tenant AND l.game_id=v_game AND l.team_record_id=v_home
 AND entries.value->'fielding_position'='{{"kind":"fielding","position":1}}'::jsonb
 AND l.xmin::text::numeric=pg_catalog.mod(v_own_xid,4294967296::numeric);
 SELECT (entries.value->>'player_id')::uuid INTO STRICT v_away_pitcher
 FROM public.game_lineups l CROSS JOIN LATERAL
 pg_catalog.jsonb_array_elements(l.entries_with_uniform_number_snapshot)
 AS entries(value)
 WHERE l.tenant_id=v_tenant AND l.game_id=v_game AND l.team_record_id=v_away
 AND entries.value->'fielding_position'='{{"kind":"fielding","position":1}}'::jsonb
 AND l.xmin::text::numeric=pg_catalog.mod(v_own_xid,4294967296::numeric);
 WITH appearance_transition AS (SELECT v_tenant AS tenant_id,v_game AS game_id,
 p_attempt_id AS source_id,'start'::text AS origin_kind,
 p_generation AS internal_generation,
 NULL::bigint AS d1,NULL::bigint AS before_inning,NULL::text AS before_half,
 1::bigint AS after_inning,'top'::text AS after_half,
 v_home_pitcher AS after_home_pitcher_id,v_away_pitcher AS after_away_pitcher_id,
 NULL::uuid AS before_home_pitcher_id,NULL::uuid AS before_away_pitcher_id,
 NULL::text AS changed_side,NULL::boolean AS half_completed,
 NULL::boolean AS end_condition_detected,NULL::boolean AS lock_further_play,
 NULL::text AS outcome,NULL::text AS x_mark,NULL::boolean AS released_end_condition,
 NULL::boolean AS half_started_before,'{artifact}'::text AS artifact_sha256,
 v_fingerprint AS source_fingerprint)
 SELECT pg_catalog.to_jsonb(projected) INTO STRICT v_entry FROM (
{query}
 ) projected;
 IF v_entry->>'state' IS DISTINCT FROM 'evaluated' OR v_entry->>'player_id' IS NULL
 THEN RAISE EXCEPTION 'pitcher entry start unavailable' USING ERRCODE='42501'; END IF;
 v_proof:=pg_catalog.jsonb_build_object('tenant_id',v_tenant,'game_id',v_game,
 'origin_kind','start','start_attempt_id',p_attempt_id,'source_event_id',NULL,
 'generation',p_generation,'d1',NULL,'slot_version',NULL,
 'player_id',(v_entry->>'player_id')::uuid,'defending_side',v_entry->>'defending_side',
 'inning',(v_entry->>'inning')::bigint,'half',v_entry->>'half',
 'proof_kind',v_entry->>'proof_kind','source_fingerprint',v_fingerprint,
 'artifact_sha256','{artifact}');
 v_digest:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(v_proof::text,'UTF8')),'hex');
 INSERT INTO sync_fence.pitcher_entry_sources(
 tenant_id,game_id,proof_sha256,origin_kind,start_attempt_id,source_event_id,
 generation,d1,slot_version,player_id,defending_side,inning,half,proof_kind,
 source_fingerprint,artifact_sha256)
 SELECT v_tenant,v_game,v_digest,'start',p_attempt_id,NULL,p_generation,NULL,NULL,
 (v_entry->>'player_id')::uuid,v_entry->>'defending_side',(v_entry->>'inning')::bigint,
 v_entry->>'half',v_entry->>'proof_kind',v_fingerprint,'{artifact}'
 ON CONFLICT (tenant_id,game_id,proof_sha256) DO NOTHING;
 IF NOT EXISTS(SELECT 1 FROM sync_fence.pitcher_entry_sources e
 WHERE e.tenant_id=v_tenant AND e.game_id=v_game AND e.proof_sha256=v_digest
 AND pg_catalog.to_jsonb(e)-'proof_sha256'=v_proof)
 THEN RAISE EXCEPTION 'pitcher entry start identity mismatch'
 USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT v_digest;
END;
$d03_start$;
"""
