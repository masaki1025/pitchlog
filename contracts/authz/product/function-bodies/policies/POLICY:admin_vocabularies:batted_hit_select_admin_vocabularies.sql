-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:admin_vocabularies:batted_hit_select_admin_vocabularies

CREATE POLICY batted_hit_select_admin_vocabularies ON public.admin_vocabularies AS PERMISSIVE FOR SELECT TO pitchlog_sync_right_fn_owner USING (session_user = 'pitchlog_app');
