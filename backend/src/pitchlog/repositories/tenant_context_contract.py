"""テナント文脈の生成元 allowlist を提供する生成モジュール。"""

SCHEMA_VERSION = 1
CONTRACT_REVISION = 1
ASSET_KIND = "tenant_context_construction_allowlist"
CANONICALIZATION = "json-sort-keys-utf8-v1"
SOURCE_ASSET = "contracts/tenant_boundary/tenant-context-allowlist.json"
SOURCE_DIGEST = "69b2b6ad859a901c7e7582f5f408a2af16fcbe850562b6ea79eb5a68e18fe754"
CONSTRUCTOR_SYMBOL = "pitchlog.repositories.context.TenantContext"
ALLOWED_TEST_MODULES = ("test_authz_tenant_context",)
ALLOWED_PRODUCT_MODULES: tuple[str, ...] = ()
