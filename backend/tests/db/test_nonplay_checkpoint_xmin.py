"""JOIN後のROWTYPE headerを物理保存印に代用しない回帰。"""

import pytest

pytestmark = pytest.mark.requires_db


def test_joined_checkpoint_uses_explicit_physical_xmin(
    admin_connection, record_property
):
    """JOIN/行lock後も、別途明示取得した物理xminを比較する。"""
    c = admin_connection
    c.execute("CREATE TEMP TABLE xmin_checkpoint (id integer, payload jsonb)")
    c.execute("CREATE TEMP TABLE xmin_generation (id integer)")
    c.execute("INSERT INTO xmin_checkpoint VALUES (1, '{}'::jsonb)")
    c.execute("INSERT INTO xmin_generation VALUES (1)")
    c.execute("""
        CREATE FUNCTION pg_temp.check_physical_xmin() RETURNS jsonb
        LANGUAGE plpgsql AS $probe$
        DECLARE cp xmin_checkpoint%ROWTYPE; expected xid; physical_xmin xid;
        BEGIN
          SELECT c.xmin INTO STRICT expected FROM xmin_checkpoint c;
          SELECT c.* INTO STRICT cp FROM xmin_checkpoint c
          JOIN xmin_generation g ON g.id=c.id FOR SHARE OF c;
          SELECT c.xmin INTO STRICT physical_xmin FROM xmin_checkpoint c
          WHERE c.id=cp.id;
          RETURN jsonb_build_object('rowtype_matches',cp.xmin=expected,
                                    'physical_matches',physical_xmin=expected,
                                    'payload_preserved',cp.payload='{}'::jsonb);
        END;
        $probe$;
    """)
    value = c.execute("SELECT pg_temp.check_physical_xmin()").fetchone()[0]
    record_property("rowtype_header_matches_physical", value["rowtype_matches"])
    assert value["physical_matches"] is True
    assert value["payload_preserved"] is True


def test_generation_chain_alias_does_not_shadow_page_record(admin_connection):
    """未初期化のpage recordとSQL別名を区別して順序付き連結を返す。"""
    c = admin_connection
    c.execute("""
        CREATE FUNCTION pg_temp.check_generation_alias() RETURNS jsonb
        LANGUAGE plpgsql AS $probe$
        DECLARE x record; chain jsonb;
        BEGIN
          SELECT jsonb_agg(chain_row.wire_d4 ORDER BY chain_row.issuance_order)
          INTO chain
          FROM (VALUES (2,'second'::text),(1,'first'::text))
            AS chain_row(issuance_order,wire_d4);
          RETURN chain;
        END;
        $probe$;
    """)
    assert c.execute("SELECT pg_temp.check_generation_alias()").fetchone()[0] == [
        "first",
        "second",
    ]
