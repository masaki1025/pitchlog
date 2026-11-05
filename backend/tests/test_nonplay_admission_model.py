"""取消印の有限schemaと旧モデル不変を検査する。"""

from sqlalchemy import CheckConstraint, ForeignKeyConstraint

from pitchlog.db.writer_binding.nonplay_models import NonplayWriteAdmission
from pitchlog.db.writer_binding.ordinary_models import OrdinaryPitchWriteAdmission
from pitchlog.sync.control_provider.writer_binding_models import WriterBinding


def test_admission_exact43_columns_no_own_d2_or_fake_play():
    """資格は既binding27列と取消固有16列だけへ閉じる。"""
    table = NonplayWriteAdmission.__table__
    identity = set(WriterBinding.__table__.c.keys()) - {"state", "close_id"}
    extra = {
        "state",
        "frame_id",
        "frame_digest",
        "artifact_sha256",
        "source_event_id",
        "source_d1",
        "target_event_id",
        "target_generation",
        "target_d1",
        "target_play_id",
        "checkpoint_id",
        "checkpoint_revision",
        "checkpoint_digest",
        "preparation_json",
        "preparation",
        "consumed_at",
    }
    assert len(identity) == 27
    assert set(table.c.keys()) == identity | extra
    assert len(table.c) == 43
    assert not {"d2", "source_d2", "play_row_id"} & set(table.c.keys())
    for name in identity:
        assert table.c[name] is not WriterBinding.__table__.c[name]
        assert type(table.c[name].type) is type(WriterBinding.__table__.c[name].type)
        assert table.c[name].nullable is False


def test_old_ordinary_evaluated_constraint_keeps_all_required_values():
    """既CHECKのoptional化で非playを通さない。"""
    old = next(
        x
        for x in OrdinaryPitchWriteAdmission.__table__.constraints
        if isinstance(x, CheckConstraint)
        and "evaluated" in str(x.name)
        and "source_d2" in str(x.sqltext)
    )
    assert "source_d2 IS NOT NULL" in str(old.sqltext)
    assert "play_row_id IS NOT NULL" in str(old.sqltext)


def test_tenant_compound_foreign_keys_and_evaluated_shape():
    """越境参照と不完全評価を禁止する。"""
    table = NonplayWriteAdmission.__table__
    assert tuple(table.primary_key.columns.keys()) == (
        "tenant_id",
        "attempt_id",
        "phase_id",
    )
    foreign = [x for x in table.constraints if isinstance(x, ForeignKeyConstraint)]
    assert len(foreign) == 8
    assert all(
        tuple(x.column_keys)[0] == "tenant_id" and x.ondelete == "NO ACTION"
        for x in foreign
    )
    evaluated = next(
        str(x.sqltext)
        for x in table.constraints
        if isinstance(x, CheckConstraint) and str(x.name).endswith("evaluated")
    )
    for field in [
        "frame_id",
        "frame_digest",
        "source_event_id",
        "target_event_id",
        "target_play_id",
        "checkpoint_revision",
        "preparation_json",
        "preparation",
    ]:
        assert field + " IS NOT NULL" in evaluated
    consumed = next(
        str(x.sqltext)
        for x in table.constraints
        if isinstance(x, CheckConstraint) and str(x.name).endswith("consumed")
    )
    assert consumed == "(state='consumed')=(consumed_at IS NOT NULL)"
