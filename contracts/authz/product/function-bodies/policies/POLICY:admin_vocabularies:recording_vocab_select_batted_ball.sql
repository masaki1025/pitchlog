-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:admin_vocabularies:recording_vocab_select_batted_ball

CREATE POLICY recording_vocab_select_batted_ball ON public.admin_vocabularies AS PERMISSIVE FOR SELECT TO pitchlog_recording_vocab_fn_owner USING (category = 'batted_ball' AND disabled = false AND session_user = 'pitchlog_app' AND NULLIF(pg_catalog.current_setting('app.tenant_id', true), '') IS NOT NULL);
