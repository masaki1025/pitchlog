-- ELEMENT-TYPE: table
-- ELEMENT-ID: temporary_player_id_mappings

ALTER TABLE public.temporary_player_id_mappings
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.temporary_player_id_mappings
    FORCE ROW LEVEL SECURITY;
