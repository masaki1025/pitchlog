"""許可外モジュールが発行能力を registry に登録する負例。"""

from pitchlog.repositories.context import _ISSUANCE_CAPABILITY  # ty: ignore

registry: dict[str, object] = {}
registry["k"] = _ISSUANCE_CAPABILITY
