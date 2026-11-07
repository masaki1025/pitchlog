-- 生成元: backend/domain/stats-appearance.model.json。真正TX原本のappearance_transitionだけを供給する。
WITH observed AS (
 SELECT e.*,
  CASE e.after_half WHEN 'top' THEN 'home' WHEN 'bottom' THEN 'away' END AS defender,
  CASE e.after_half WHEN 'top' THEN e.after_home_pitcher_id
       WHEN 'bottom' THEN e.after_away_pitcher_id END AS pitcher,
  CASE e.after_half WHEN 'top' THEN e.before_home_pitcher_id
       WHEN 'bottom' THEN e.before_away_pitcher_id END AS previous_pitcher,
  CASE
   WHEN e.origin_kind='start' THEN 1
   WHEN e.origin_kind='play' AND e.half_completed IS TRUE
        AND e.end_condition_detected IS FALSE AND e.lock_further_play IS FALSE
        AND e.outcome IN ('no-end','extra-continue','tiebreak-continue') THEN 1
   WHEN e.origin_kind='substitution' AND e.changed_side=
        CASE e.after_half WHEN 'top' THEN 'home' WHEN 'bottom' THEN 'away' END
        AND (CASE e.after_half WHEN 'top' THEN e.after_home_pitcher_id
              WHEN 'bottom' THEN e.after_away_pitcher_id END) IS DISTINCT FROM
            (CASE e.after_half WHEN 'top' THEN e.before_home_pitcher_id
              WHEN 'bottom' THEN e.before_away_pitcher_id END) THEN 1
   WHEN e.origin_kind='reopen' AND e.half_completed IS TRUE
        AND e.released_end_condition IS TRUE AND e.half_started_before IS FALSE
        THEN 1
   ELSE 0 END AS emits_entry
 FROM appearance_transition e
), checked AS (
 SELECT o.*, CASE WHEN o.origin_kind IS NULL OR o.origin_kind NOT IN ('start','play','substitution','reopen')
  OR o.tenant_id IS NULL OR o.game_id IS NULL OR o.source_id IS NULL
  OR o.internal_generation IS NULL OR o.internal_generation<=0
  OR o.artifact_sha256 IS NULL OR o.source_fingerprint IS NULL
  OR o.after_half IS NULL OR o.after_half NOT IN ('top','bottom')
  OR o.after_inning IS NULL OR o.after_inning<=0
  OR (o.origin_kind='start' AND (o.d1 IS NOT NULL OR o.after_inning<>1
       OR o.after_half<>'top'))
  OR (o.origin_kind<>'start' AND (o.d1 IS NULL OR o.d1<=0
       OR o.before_half IS NULL OR o.before_half NOT IN ('top','bottom')
       OR o.before_inning IS NULL OR o.before_inning<=0))
  OR (o.origin_kind='play' AND (o.half_completed IS NULL
       OR o.end_condition_detected IS NULL OR o.lock_further_play IS NULL
       OR o.outcome IS NULL OR o.x_mark IS NULL
       OR o.outcome NOT IN ('no-end','normal-end','extra-continue','limit-draw','tiebreak-continue','cold-end','walk-off') OR o.x_mark NOT IN ('recorded-score','x-mark')
       OR o.end_condition_detected IS DISTINCT FROM o.lock_further_play
       OR (o.half_completed IS TRUE AND o.before_half=o.after_half)
       OR (o.half_completed IS FALSE AND (o.before_half<>o.after_half
           OR o.before_inning<>o.after_inning))
       OR (o.end_condition_detected IS FALSE AND o.lock_further_play IS FALSE
           AND (o.outcome NOT IN ('no-end','extra-continue','tiebreak-continue') OR o.x_mark<>'recorded-score'))
       OR (o.end_condition_detected IS TRUE AND o.outcome IN ('no-end','extra-continue','tiebreak-continue'))))
  OR (o.origin_kind='substitution' AND (o.changed_side IS NULL
       OR o.changed_side NOT IN ('home','away') OR o.before_half<>o.after_half
       OR o.before_inning<>o.after_inning))
  OR (o.origin_kind='reopen' AND (o.half_completed IS NULL
       OR o.released_end_condition IS NULL OR o.half_started_before IS NULL))
  OR (o.emits_entry=1 AND o.pitcher IS NULL)
 THEN 'source_unavailable' ELSE 'evaluated' END AS state
 FROM observed o
)
SELECT state,tenant_id,game_id,origin_kind,source_id,internal_generation,d1,
 CASE WHEN state='evaluated' AND emits_entry=1 THEN pitcher END AS player_id,
 CASE WHEN state='evaluated' AND emits_entry=1 THEN defender END AS defending_side,
 CASE WHEN state='evaluated' AND emits_entry=1 THEN after_inning END AS inning,
 CASE WHEN state='evaluated' AND emits_entry=1 THEN after_half END AS half,
 CASE WHEN state='evaluated' AND emits_entry=1 THEN
  CASE WHEN origin_kind='substitution' THEN 'pitcher-defensive-entry' ELSE 'defensive-half-entry' END
 END AS proof_kind,artifact_sha256,source_fingerprint
FROM checked
