-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:public:protect_recording_generations_updates()


        CREATE OR REPLACE FUNCTION public.protect_recording_generations_updates()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(
                NEW.generation,
                NEW.kind,
                NEW.issuance_order,
                NEW.holder_device,
                NEW.granted_at,
                NEW.proof_digest,
                NEW.recovery_generation
            ) IS DISTINCT FROM ROW(
                OLD.generation,
                OLD.kind,
                OLD.issuance_order,
                OLD.holder_device,
                OLD.granted_at,
                OLD.proof_digest,
                OLD.recovery_generation
            ) THEN
                RAISE EXCEPTION 'recording generation identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.confirmed_watermark < OLD.confirmed_watermark THEN
                RAISE EXCEPTION 'recording generation D3 cannot move backward'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        ;
REVOKE EXECUTE ON FUNCTION public.protect_recording_generations_updates() FROM PUBLIC, pitchlog_app;
