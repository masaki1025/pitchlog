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
