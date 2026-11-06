"""型別名だけを正規化し、不正な型の変更は保持して検出する。"""

from db.test_schema_audit import _manifest_columns


def _columns(kind: str):
    return _manifest_columns(
        {
            "tables": [
                {
                    "name": "example",
                    "columns": [
                        {
                            "name": "saved_at",
                            "type": kind,
                            "nullable": False,
                            "default": None,
                        }
                    ],
                }
            ]
        }
    )


def test_timestamptz_alias_has_the_same_column_contract():
    """PostgreSQLの同じOIDの別名だけを同一化する。"""
    assert _columns("timestamptz") == _columns("timestamp with time zone")


def test_timezone_and_precision_changes_are_not_normalized_away():
    """タイムゾーンや精度の喪失を別名扱いで隠さない。"""
    expected = _columns("timestamp with time zone")
    assert _columns("timestamp without time zone") != expected
    assert _columns("timestamp(3) with time zone") != expected
