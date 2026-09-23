"""条件 5 の transaction-local でない set_config を表す負例。"""

from pitchlog.repositories.guc import set_config  # ty: ignore


def bind(tenant_id: str) -> None:
    set_config("app.tenant_id", tenant_id, False)
