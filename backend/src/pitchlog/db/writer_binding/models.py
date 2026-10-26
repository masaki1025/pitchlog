"""単一のwriterモデルを製品モデル走査へ登録する。"""

from pitchlog.sync.control_provider.writer_binding_models import (
    WriterAdmission,
    WriterBinding,
)

writer_bindings = WriterBinding.__table__
writer_admissions = WriterAdmission.__table__
