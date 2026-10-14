"""署名済み提示値から実 DB の無効状態を拒否する。"""

import base64
import secrets
from uuid import UUID, uuid4

import pytest
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from pitchlog.api.app import create_app
from pitchlog.authz.token_presentation import TokenPresentation
from pitchlog.authz.verified_tenant import logout_token, verify_tenant_id

from .conftest import ProvisionedProductCatalog
from .test_product_authz_authn_app import (
    _app_dsn,
    _login,
    _seed_identity,
    _seed_settings,
    _token,
)

pytestmark = pytest.mark.requires_db


@pytest.mark.parametrize(
    "invalid",
    ("logged_out", "stale_credential", "disabled", "wrong_tenant", "expired"),
)
def test_signed_invalid_token_returns_no_tenant(
    provisioned_product_catalog: ProvisionedProductCatalog,
    invalid: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """失効・認証情報更新・無効化・所属不一致・期限切れを実 DB で拒否する。"""
    catalog = provisioned_product_catalog
    _seed_settings(catalog)
    app_dsn = _app_dsn(catalog)
    identity = _seed_identity(catalog, app_dsn)
    token = _login(identity)
    assert isinstance(token, UUID)
    monkeypatch.setenv(
        "PITCHLOG_TOKEN_SIGNING_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )
    signer: TokenPresentation = create_app().state.token_presentation
    connection_options = conninfo_to_dict(app_dsn)
    engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username=str(connection_options["user"]),
            password=str(connection_options["password"]),
            host=str(connection_options["host"]),
            port=int(str(connection_options["port"])),
            database=str(connection_options["dbname"]),
        ),
        connect_args={"sslmode": "disable", "gssencmode": "disable"},
    )
    try:
        valid_before = _token(catalog, token)
        verified = verify_tenant_id(signer.encode(token), signer, engine)
        assert verified is not None
        assert verified[0] == identity.tenant_id
        valid_after = _token(catalog, token)
        assert valid_after[0] >= valid_before[0]
        assert valid_after[0] == verified[1]
        assert valid_after[1] >= valid_before[1]
        target = token
        if invalid == "wrong_tenant":
            other = _seed_identity(catalog, app_dsn)
            target = uuid4()
            with catalog.applicator.cursor() as cursor:
                cursor.execute(
                    "ALTER TABLE public.tenant_tokens "
                    "DROP CONSTRAINT fk_tenant_tokens_subject"
                )
                cursor.execute(
                    """
                    INSERT INTO public.tenant_tokens
                        (id, tenant_id, auth_subject_id, credential_generation,
                         expires_at, last_used_at)
                    VALUES (%s, %s, %s, 1,
                            pg_catalog.clock_timestamp() + interval '1 hour',
                            pg_catalog.clock_timestamp())
                    """,
                    (target, other.tenant_id, identity.subject_id),
                )
            catalog.applicator.commit()
        elif invalid == "logged_out":
            before_logout = _token(catalog, token)
            assert logout_token(signer.encode(token), signer, engine) is None
            after_logout = _token(catalog, token)
            assert after_logout[0] < before_logout[0]
            assert after_logout[1] == before_logout[1]
        else:
            with catalog.applicator.cursor() as cursor:
                if invalid == "stale_credential":
                    cursor.execute(
                        "UPDATE public.tenant_credentials "
                        "SET generation = generation + 1 WHERE auth_subject_id = %s",
                        (identity.subject_id,),
                    )
                elif invalid == "disabled":
                    cursor.execute(
                        "UPDATE public.tenants SET enabled = false, "
                        "disabled_at = pg_catalog.clock_timestamp() WHERE id = %s",
                        (identity.tenant_id,),
                    )
                elif invalid == "expired":
                    cursor.execute(
                        "UPDATE public.tenant_tokens "
                        "SET last_used_at = pg_catalog.clock_timestamp() "
                        "- interval '2 seconds', "
                        "expires_at = pg_catalog.clock_timestamp() "
                        "- interval '1 second' WHERE id = %s",
                        (token,),
                    )
            catalog.applicator.commit()

        before = _token(catalog, target)
        assert verify_tenant_id(signer.encode(target), signer, engine) is None
        assert _token(catalog, target) == before
    finally:
        engine.dispose()
