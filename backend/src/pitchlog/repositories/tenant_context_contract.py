"""テナント文脈の生成元 allowlist を提供する生成モジュール。"""

SCHEMA_VERSION = 1
CONTRACT_REVISION = 2
ASSET_KIND = "tenant_context_construction_allowlist"
CANONICALIZATION = "json-sort-keys-utf8-v1"
SOURCE_ASSET = "contracts/tenant_boundary/tenant-context-allowlist.json"
SOURCE_DIGEST = "95866ef7d9d76d915b78ab22c5dd4f00f7a0bed6222d0f029b53b1a5f1d5634e"
CONSTRUCTOR_SYMBOL = "pitchlog.repositories.context.TenantContext"
FORBIDDEN_CONSTRUCTION_SYMBOLS = ("builtins.object.__new__",)
ALLOWED_TEST_MODULES = ("test_authz_tenant_context",)
ALLOWED_PRODUCT_MODULES: tuple[str, ...] = ()
