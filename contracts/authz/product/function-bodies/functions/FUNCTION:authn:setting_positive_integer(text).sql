-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:authn:setting_positive_integer(text)

CREATE OR REPLACE FUNCTION authn.setting_positive_integer(p_key text)
RETURNS bigint
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $authn_function$
DECLARE
    setting_value jsonb;
    integer_text text;
    result bigint;
BEGIN
    SELECT setting.value INTO setting_value
    FROM public.system_settings AS setting WHERE setting.key = p_key;
    IF setting_value IS NULL OR pg_catalog.jsonb_typeof(setting_value) <> 'number' THEN
        RETURN NULL;
    END IF;
    integer_text := setting_value::text;
    IF integer_text !~ '^[0-9]+$' THEN
        RETURN NULL;
    END IF;
    BEGIN
        result := integer_text::bigint;
    EXCEPTION WHEN numeric_value_out_of_range THEN
        RETURN NULL;
    END;
    IF result < 1 THEN
        RETURN NULL;
    END IF;
    RETURN result;
END;
$authn_function$;
ALTER FUNCTION authn.setting_positive_integer(text) OWNER TO pitchlog_auth_fn_owner;
REVOKE ALL PRIVILEGES ON FUNCTION authn.setting_positive_integer(text) FROM PUBLIC;
