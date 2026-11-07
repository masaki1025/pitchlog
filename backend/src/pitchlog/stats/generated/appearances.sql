-- 生成元: backend/domain/stats-appearance.model.json。真正scope/member CTEの供給前は製品提供不可。
SELECT 'appearances' AS metric_id,
 CASE WHEN invalid_supply THEN 'source_unavailable' ELSE 'available' END AS state,
 CASE WHEN invalid_supply THEN NULL ELSE (
   SELECT COUNT(DISTINCT m.game_id) FROM appearance_members m
   JOIN appearance_scope s ON m.tenant_id=s.tenant_id AND m.game_id=s.game_id AND m.fact_version_id=s.fact_version_id AND m.revision=s.revision AND m.source_set_sha256=s.source_set_sha256
   WHERE m.tenant_id=:tenant_id AND m.player_id=:player_id
 ) END AS value
FROM (SELECT
 :expected_game_count IS NULL OR :expected_game_count<0
 OR (SELECT COUNT(*) FROM appearance_scope s WHERE s.tenant_id=:tenant_id)
    <>:expected_game_count
 OR EXISTS(SELECT 1 FROM appearance_scope s WHERE s.tenant_id=:tenant_id
   AND (s.supply_complete IS NOT TRUE OR s.tenant_id IS NULL OR s.game_id IS NULL OR s.fact_version_id IS NULL OR s.revision IS NULL OR s.source_set_sha256 IS NULL
     OR s.revision<=0 OR s.member_count IS NULL OR s.member_count<0
     OR s.member_count<>(SELECT COUNT(*) FROM appearance_members m WHERE m.tenant_id=s.tenant_id AND m.game_id=s.game_id AND m.fact_version_id=s.fact_version_id AND m.revision=s.revision AND m.source_set_sha256=s.source_set_sha256)))
 OR EXISTS(SELECT 1 FROM appearance_scope s WHERE s.tenant_id=:tenant_id
   GROUP BY s.tenant_id,s.game_id HAVING COUNT(*)<>1)
 OR EXISTS(SELECT 1 FROM appearance_members m WHERE m.tenant_id=:tenant_id
   AND (m.proof_kind NOT IN ('defensive-half-entry','pitcher-defensive-entry') OR m.proof_kind IS NULL
     OR m.player_id IS NULL OR m.proof_source_id IS NULL
     OR NOT EXISTS(SELECT 1 FROM appearance_scope s WHERE m.tenant_id=s.tenant_id AND m.game_id=s.game_id AND m.fact_version_id=s.fact_version_id AND m.revision=s.revision AND m.source_set_sha256=s.source_set_sha256)))
 AS invalid_supply) supply
