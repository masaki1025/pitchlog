-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:public:authn_normalize_team_name(text)

REVOKE EXECUTE ON FUNCTION public.authn_normalize_team_name(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.authn_normalize_team_name(text) FROM pitchlog_app;
GRANT EXECUTE ON FUNCTION public.authn_normalize_team_name(text) TO pitchlog_auth_fn_owner;
