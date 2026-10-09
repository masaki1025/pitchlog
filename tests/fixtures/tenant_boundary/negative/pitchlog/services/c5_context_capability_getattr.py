"""許可外モジュールが getattr で発行能力を取り出す負例。"""

import pitchlog.repositories.context as context_module  # ty: ignore

capability = getattr(context_module, "_ISSUANCE_CAPABILITY")
