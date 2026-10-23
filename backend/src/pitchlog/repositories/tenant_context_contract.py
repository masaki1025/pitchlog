"""テナント文脈の生成元 allowlist を提供する生成モジュール。"""

SCHEMA_VERSION = 1
CONTRACT_REVISION = 18
ASSET_KIND = "tenant_context_construction_allowlist"
CANONICALIZATION = "json-sort-keys-utf8-v1"
SOURCE_ASSET = "contracts/tenant_boundary/tenant-context-allowlist.json"
SOURCE_DIGEST = "e8ddab1d4ae8a0f3714f420452af47fe2d12383eaa1a4d285169d7046385369f"
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
ISSUANCE_CAPABILITY_SYMBOL = "pitchlog.repositories.context._ISSUANCE_CAPABILITY"
ISSUANCE_CAPABILITY_ALLOWED_SYMBOLS = (
    "pitchlog.repositories.context.TenantContext.__init__",
)
ISSUANCE_ENTRYPOINT_SYMBOL = (
    "pitchlog.repositories.tenant_context_issuance."
    "issue_tenant_context_from_presented_token"
)
ISSUANCE_ENTRYPOINT_ALLOWED_SYMBOLS = (
    "pitchlog.api.tenant_access.require_tenant_access",
)
ALLOWED_TEST_MODULES = ("test_authz_tenant_context",)
ALLOWED_PRODUCT_MODULES = ("pitchlog.repositories.tenant_context_issuance",)
