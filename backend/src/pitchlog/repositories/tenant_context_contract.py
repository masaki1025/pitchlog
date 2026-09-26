"""テナント文脈の生成元 allowlist を提供する生成モジュール。"""

SCHEMA_VERSION = 1
CONTRACT_REVISION = 7
ASSET_KIND = "tenant_context_construction_allowlist"
CANONICALIZATION = "json-sort-keys-utf8-v1"
SOURCE_ASSET = "contracts/tenant_boundary/tenant-context-allowlist.json"
SOURCE_DIGEST = "d3f8286856278af95946293cf66d38d89eafc94a8d8657e8227a9b5ae03bd0b3"
CONSTRUCTOR_SYMBOL = "pitchlog.repositories.context.TenantContext"
FORBIDDEN_CONSTRUCTION_SYMBOLS = (
    "builtins.object.__new__",
    "builtins.object.__setattr__",
    "builtins.type",
    "dataclasses.replace",
)
INTEGRITY_SECRET_SYMBOL = "pitchlog.repositories.context._TENANT_CONTEXT_SECRET"
INTEGRITY_SECRET_ALLOWED_SYMBOLS = (
    "pitchlog.repositories.context._tenant_context_proof",
)
INTEGRITY_PROOF_FACTORY_SYMBOL = "pitchlog.repositories.context._tenant_context_proof"
INTEGRITY_PROOF_FACTORY_ALLOWED_SYMBOLS = (
    "pitchlog.repositories.context.TenantContext.__init__",
    "pitchlog.repositories.context.TenantContext._has_valid_integrity_proof",
)
ALLOWED_TEST_MODULES = ("test_authz_tenant_context",)
ALLOWED_PRODUCT_MODULES: tuple[str, ...] = ()
