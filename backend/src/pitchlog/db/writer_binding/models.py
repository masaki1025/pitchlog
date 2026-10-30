"""単一のwriterモデルを製品モデル走査へ登録する。"""

from pitchlog.db.writer_binding.ordinary_models import (
    OrdinaryPitchCheckpoint,
    OrdinaryPitchHistory,
    OrdinaryPitchWriteAdmission,
)
from pitchlog.sync.control_provider.writer_binding_models import (
    FirstBallWriteAdmission,
    WriterAdmission,
    WriterBinding,
)

writer_bindings = WriterBinding.__table__
writer_admissions = WriterAdmission.__table__

first_ball_write_admissions = FirstBallWriteAdmission.__table__


ordinary_pitch_checkpoints = OrdinaryPitchCheckpoint.__table__
ordinary_pitch_history = OrdinaryPitchHistory.__table__
ordinary_pitch_write_admissions = OrdinaryPitchWriteAdmission.__table__
