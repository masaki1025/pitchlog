"""P3構造検査が新しい制約を解釈できることをDB起動前に確かめる。"""

from sqlalchemy import CheckConstraint

from pitchlog.db.all_models import IMPORTED_MODEL_MODULE_NAMES
from pitchlog.db.current_product_startup import _expected_constraints, _expression
from pitchlog.db.past_correction.models import P3_STORAGE_MODELS


def test_every_p3_check_can_be_compared_before_database_startup():
    """parser未対応の式で正規配置が常に閉じる退行を先に検出する。"""
    assert IMPORTED_MODEL_MODULE_NAMES
    checked = 0
    for model in P3_STORAGE_MODELS:
        table = model.__table__
        rows = _expected_constraints(table)
        assert len(rows) == len(table.constraints)
        for constraint in table.constraints:
            if isinstance(constraint, CheckConstraint):
                assert _expression(str(constraint.sqltext)) is not None
                checked += 1
    assert checked == 64


def test_progress_state_index_keeps_text_collation():
    """uuidだけの索引と異なりstate列のcollationを落とさない。"""
    from pitchlog.db.past_correction.models import ix_p3_page_progress_attempt
    from pitchlog.db.past_correction.startup import _expected_index

    signature = _expected_index(ix_p3_page_progress_attempt)
    assert signature[8] == ("tenant_id", "attempt_id", "phase_id", "state")
    assert signature[9] == (None, None, None, "default")
    assert signature[14] == ("uuid_ops", "uuid_ops", "uuid_ops", "text_ops")
