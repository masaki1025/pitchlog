"""先置き審査済み7列/2policyのcanonical producerを全値で照合する。"""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from pitchlog.authz.terminal_pitch_product import (
    FUNCTIONS,
    candidate_declarations,
    require_registered_product,
)
from pitchlog.authz.terminal_pitch_write_stamp import candidate_function_bodies
from pitchlog.repositories.ordinary_prefix import OrdinaryPrefixError

# sourceではなく、実装前に非作者が確認した有限宣言/SQLを独立期待として保持する。
# fmt: off
EXPECTED_ADDITIONS = {
    'column_acl_expectations': [
        {
            'expectation_id': (
                'COLUMN-ACL:public:admin_vocabularies:key:pitc'
                'hlog_sync_right_fn_owner'
            ),
            'object_kind': 'column',
            'object_schema': 'public',
            'object_id': 'admin_vocabularies',
            'column_id': 'key',
            'grantee_role_id': 'pitchlog_sync_right_fn_owner',
            'privilege_ids': [
                'SELECT',
            ],
            'grant_option': False,
        },
        {
            'expectation_id': (
                'COLUMN-ACL:public:admin_vocabularies:category'
                ':pitchlog_sync_right_fn_owner'
            ),
            'object_kind': 'column',
            'object_schema': 'public',
            'object_id': 'admin_vocabularies',
            'column_id': 'category',
            'grantee_role_id': 'pitchlog_sync_right_fn_owner',
            'privilege_ids': [
                'SELECT',
            ],
            'grant_option': False,
        },
        {
            'expectation_id': (
                'COLUMN-ACL:public:admin_vocabularies:disabled'
                ':pitchlog_sync_right_fn_owner'
            ),
            'object_kind': 'column',
            'object_schema': 'public',
            'object_id': 'admin_vocabularies',
            'column_id': 'disabled',
            'grantee_role_id': 'pitchlog_sync_right_fn_owner',
            'privilege_ids': [
                'SELECT',
            ],
            'grant_option': False,
        },
        {
            'expectation_id': (
                'COLUMN-ACL:public:tenant_vocabularies:tenant_'
                'id:pitchlog_sync_right_fn_owner'
            ),
            'object_kind': 'column',
            'object_schema': 'public',
            'object_id': 'tenant_vocabularies',
            'column_id': 'tenant_id',
            'grantee_role_id': 'pitchlog_sync_right_fn_owner',
            'privilege_ids': [
                'SELECT',
            ],
            'grant_option': False,
        },
        {
            'expectation_id': (
                'COLUMN-ACL:public:tenant_vocabularies:key:pit'
                'chlog_sync_right_fn_owner'
            ),
            'object_kind': 'column',
            'object_schema': 'public',
            'object_id': 'tenant_vocabularies',
            'column_id': 'key',
            'grantee_role_id': 'pitchlog_sync_right_fn_owner',
            'privilege_ids': [
                'SELECT',
            ],
            'grant_option': False,
        },
        {
            'expectation_id': (
                'COLUMN-ACL:public:tenant_vocabularies:categor'
                'y:pitchlog_sync_right_fn_owner'
            ),
            'object_kind': 'column',
            'object_schema': 'public',
            'object_id': 'tenant_vocabularies',
            'column_id': 'category',
            'grantee_role_id': 'pitchlog_sync_right_fn_owner',
            'privilege_ids': [
                'SELECT',
            ],
            'grant_option': False,
        },
        {
            'expectation_id': (
                'COLUMN-ACL:public:tenant_vocabularies:disable'
                'd:pitchlog_sync_right_fn_owner'
            ),
            'object_kind': 'column',
            'object_schema': 'public',
            'object_id': 'tenant_vocabularies',
            'column_id': 'disabled',
            'grantee_role_id': 'pitchlog_sync_right_fn_owner',
            'privilege_ids': [
                'SELECT',
            ],
            'grant_option': False,
        },
    ],
    'policies': [
        {
            'policy_id': (
                'POLICY:admin_vocabularies:batted_hit_select_a'
                'dmin_vocabularies'
            ),
            'table_id': 'admin_vocabularies',
            'profile': 'function_only',
            'policy_name': 'batted_hit_select_admin_vocabularies',
            'command': 'SELECT',
            'policy_mode': 'permissive',
            'role_ids': [
                'pitchlog_sync_right_fn_owner',
            ],
            'using_predicate_id': None,
            'using_column': None,
            'using_expression': "session_user = 'pitchlog_app'",
            'with_check_predicate_id': None,
            'with_check_column': None,
            'with_check_expression': None,
        },
        {
            'policy_id': (
                'POLICY:tenant_vocabularies:batted_hit_select_'
                'tenant_vocabularies'
            ),
            'table_id': 'tenant_vocabularies',
            'profile': 'function_only',
            'policy_name': 'batted_hit_select_tenant_vocabularies',
            'command': 'SELECT',
            'policy_mode': 'permissive',
            'role_ids': [
                'pitchlog_sync_right_fn_owner',
            ],
            'using_predicate_id': None,
            'using_column': None,
            'using_expression': (
                'tenant_id = NULLIF(pg_catalog.current_setting'
                "('app.tenant_id',true),'')::uuid AND session_"
                "user = 'pitchlog_app'"
            ),
            'with_check_predicate_id': None,
            'with_check_column': None,
            'with_check_expression': None,
        },
    ],
}

EXPECTED_BODIES = {
    (
        'column_acl_expectation|COLUMN-ACL:public:admi'
        'n_vocabularies:key:pitchlog_sync_right_fn_own'
        'er'
    ): (
        'GRANT SELECT (key) ON public.admin_vocabulari'
        'es TO pitchlog_sync_right_fn_owner;\n'
    ),
    (
        'column_acl_expectation|COLUMN-ACL:public:admi'
        'n_vocabularies:category:pitchlog_sync_right_f'
        'n_owner'
    ): (
        'GRANT SELECT (category) ON public.admin_vocab'
        'ularies TO pitchlog_sync_right_fn_owner;\n'
    ),
    (
        'column_acl_expectation|COLUMN-ACL:public:admi'
        'n_vocabularies:disabled:pitchlog_sync_right_f'
        'n_owner'
    ): (
        'GRANT SELECT (disabled) ON public.admin_vocab'
        'ularies TO pitchlog_sync_right_fn_owner;\n'
    ),
    (
        'policy|POLICY:admin_vocabularies:batted_hit_s'
        'elect_admin_vocabularies'
    ): (
        'CREATE POLICY batted_hit_select_admin_vocabul'
        'aries ON public.admin_vocabularies AS PERMISS'
        'IVE FOR SELECT TO pitchlog_sync_right_fn_owne'
        "r USING (session_user = 'pitchlog_app');\n"
    ),
    (
        'column_acl_expectation|COLUMN-ACL:public:tena'
        'nt_vocabularies:tenant_id:pitchlog_sync_right'
        '_fn_owner'
    ): (
        'GRANT SELECT (tenant_id) ON public.tenant_voc'
        'abularies TO pitchlog_sync_right_fn_owner;\n'
    ),
    (
        'column_acl_expectation|COLUMN-ACL:public:tena'
        'nt_vocabularies:key:pitchlog_sync_right_fn_ow'
        'ner'
    ): (
        'GRANT SELECT (key) ON public.tenant_vocabular'
        'ies TO pitchlog_sync_right_fn_owner;\n'
    ),
    (
        'column_acl_expectation|COLUMN-ACL:public:tena'
        'nt_vocabularies:category:pitchlog_sync_right_'
        'fn_owner'
    ): (
        'GRANT SELECT (category) ON public.tenant_voca'
        'bularies TO pitchlog_sync_right_fn_owner;\n'
    ),
    (
        'column_acl_expectation|COLUMN-ACL:public:tena'
        'nt_vocabularies:disabled:pitchlog_sync_right_'
        'fn_owner'
    ): (
        'GRANT SELECT (disabled) ON public.tenant_voca'
        'bularies TO pitchlog_sync_right_fn_owner;\n'
    ),
    (
        'policy|POLICY:tenant_vocabularies:batted_hit_'
        'select_tenant_vocabularies'
    ): (
        'CREATE POLICY batted_hit_select_tenant_vocabu'
        'laries ON public.tenant_vocabularies AS PERMI'
        'SSIVE FOR SELECT TO pitchlog_sync_right_fn_ow'
        'ner USING (tenant_id = NULLIF(pg_catalog.curr'
        "ent_setting('app.tenant_id',true),'')::uuid A"
        "ND session_user = 'pitchlog_app');\n"
    ),
}

PRESERVED_FUNCTION_BODIES = {
    (
        'function|FUNCTION:sync_right_api:read_lineup_'
        'started_origin(uuid, uuid, bigint)'
    ): (
        '1c3755d7959429abc1282693ff9a497422bfe64608102'
        'cc418abf638320dabf5'
    ),
    (
        'function|FUNCTION:sync_right_api:read_play_pr'
        'efix_checkpoint(uuid, uuid, bigint)'
    ): (
        'b3cc18fe1d24ebb432d3228abacfd46f83464bcd90a66'
        '17b736392b1568fb9df'
    ),
    (
        'function|FUNCTION:sync_right_api:lock_play_pr'
        'efix_checkpoint(uuid, uuid, uuid, bytea, uuid'
        ', uuid, bigint)'
    ): (
        'd6257ae4c4c778b028cdb0e395f3c2a691569a465ccb5'
        '12eed91fb454a6eda32'
    ),
    (
        'function|FUNCTION:sync_right_api:read_play_pr'
        'efix_history_page(uuid, uuid, bigint, bigint,'
        ' uuid, bigint, bigint, bigint, bigint, bigint'
        ', uuid, integer)'
    ): (
        'fe44ccec97decdecf75b0ed27b06cfb0c8b1c09fdb005'
        '11b1d3bf3f6233f58b1'
    ),
    (
        'function|FUNCTION:sync_right_api:prepare_play'
        '_prefix_projection(uuid, uuid, uuid, bytea, u'
        'uid, uuid, text)'
    ): (
        '8bad44e2d4047504ef19e1a48b777d9540d9bc4275441'
        '0bfe36c2f7b271faddb'
    ),
    (
        'function|FUNCTION:sync_right_api:assert_play_'
        'prefix_projection(jsonb)'
    ): (
        'f0dbbd962cd4599da2e1f2d97b176df580a83b7c5cbce'
        'f04932fee476a374a23'
    ),
    (
        'function|FUNCTION:sync_right_api:finish_play_'
        'prefix_projection()'
    ): (
        '54995cbd181d5593e81196334e5574b1ad2284ab5c9a7'
        'a9a317084062625b2d8'
    ),
    (
        'function|FUNCTION:sync_right_api:guard_play_p'
        'refix_runner_insert()'
    ): (
        '5a7b8c541d9ace59d62206c3a3194b6b588a1ef81ec10'
        '74991897358c835c43e'
    ),
}
# fmt: on


def _hash(value):
    """宣言の全値を正準化し、部分一致へ逃がさない。"""
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _identifiers(section):
    """有限既存assetのIDキーを返す。"""
    return {"column_acl_expectations": "expectation_id", "policies": "policy_id"}[
        section
    ]


def test_batted_hit_declarations_match_preaccepted_nine_elements_exactly():
    """旧全値を保持して7SELECT列/2SELECT policyだけを追加する。"""
    actual, _ = candidate_declarations()
    restored = copy.deepcopy(actual)
    for section, expected in EXPECTED_ADDITIONS.items():
        key = _identifiers(section)
        identifiers = {r[key] for r in expected}
        assert [r for r in actual[section] if r[key] in identifiers] == expected
        restored[section] = [r for r in restored[section] if r[key] not in identifiers]
    assert (
        _hash(restored)
        == "1ecaad379aa2b844d15659e915ec7da6e9d5651a458e2e9c6121ed0b58bcaaf8"
    )
    assert len(actual["functions"]) == 8
    assert len(actual["column_acl_expectations"]) == 26
    assert len(actual["policies"]) == 6


def test_batted_hit_sql_and_existing_activation_are_exact():
    """同じ既installer/BODIESへ有限SQLを接合し、旧8bodyを保持する。"""
    from pitchlog.authz.first_ball_product import body

    _, bodies = candidate_declarations()
    assert {k: v for k, v in bodies.items() if k in EXPECTED_BODIES} == EXPECTED_BODIES
    assert len(EXPECTED_BODIES) == 9
    for key, expected in EXPECTED_BODIES.items():
        kind, identifier = key.split("|", 1)
        assert body(kind, identifier) == (
            f"-- ELEMENT-TYPE: {kind}\n-- ELEMENT-ID: {identifier}\n\n" + expected
        )
    assert {
        k: hashlib.sha256(v.encode()).hexdigest()
        for k, v in bodies.items()
        if k.startswith("function|")
    } == PRESERVED_FUNCTION_BODIES
    assert (
        hashlib.sha256(
            candidate_function_bodies()["prepare_play_prefix_projection"].encode()
        ).hexdigest()
        == "9028e9079a826c8b7445c07611c8941f883580b8b00f8fdb4d0d95707cb09642"
    )


def test_batted_hit_producer_reads_no_runtime_cache_and_returns_fresh_values(
    monkeypatch,
):
    """配置外JSONを読まず、呼出者が返り値を変えても次のgrantへ伝播しない。"""

    def unexpected_read(*_args, **_kwargs):
        raise AssertionError("canonical producerは実行時fileを読まない")

    monkeypatch.setattr(Path, "read_text", unexpected_read)
    first, bodies = candidate_declarations()
    first["policies"][-1]["role_ids"] = ["pitchlog_app"]
    bodies[next(iter(EXPECTED_BODIES))] = "GRANT ALL TO PUBLIC;"
    again, actual = candidate_declarations()
    for section, expected in EXPECTED_ADDITIONS.items():
        key = _identifiers(section)
        ids = {r[key] for r in expected}
        assert [r for r in again[section] if r[key] in ids] == expected
    assert {k: actual[k] for k in EXPECTED_BODIES} == EXPECTED_BODIES


def _fixture_registered_metadata(monkeypatch, ddl):
    """metadata比較だけの陽性/対向fixture。DB/認可/製品成功の代用品ではない。"""
    operations = [
        "SYNC_LINEUP_PREFIX:read_lineup_started_origin"
        if name == "read_lineup_started_origin"
        else "SYNC_PLAY_PREFIX:" + name
        for name, (_, _, app) in FUNCTIONS.items()
        if app
    ]
    documents = {
        "ddl-elements.json": ddl,
        "repository-contract.json": {"product_function_operation_ids": operations},
        "lineup-prefix-manifest.json": {
            "propertyCatalog": {
                "path": "backend/domain/lineup-prefix-property-catalog.json",
                "schema": "backend/domain/lineup-prefix-property-catalog.schema.json",
            },
            "calculations": [
                {
                    "calculation": "lineup-play-prefix-v3",
                    "source": {
                        "path": "frontend/src/domain/lineupPlayPrefixContinuation.ts"
                    },
                    "directTargets": [
                        {
                            "hash": "sha256:" + "a" * 64,
                            "invocation": {
                                "operation": "deriveLineupPlayPrefixWithContinuation"
                            },
                        }
                    ],
                }
            ],
        },
        "lineup-prefix-property-catalog.json": {"schemaVersion": 1},
        "lineup-prefix-property-catalog.schema.json": {
            "type": "object",
            "properties": {"schemaVersion": {"const": 1}},
            "required": ["schemaVersion"],
            "additionalProperties": False,
        },
    }

    def read(path, *_args, **_kwargs):
        assert path.name in documents, "想定外metadataを読まない"
        return json.dumps(documents[path.name])

    monkeypatch.setattr(Path, "read_text", read)


@pytest.mark.parametrize(
    "mutation",
    [
        "role",
        "privilege",
        "grant-option",
        "column",
        "schema",
        "command",
        "policy-role",
        "using",
        "with-check",
        "duplicate",
        "missing",
    ],
)
def test_batted_hit_known_registration_mutation_stays_closed(monkeypatch, mutation):
    """既知IDのrole/権限/述語/対象/欠落を変えても登録成功へ上げない。"""
    ddl, _ = candidate_declarations()
    _fixture_registered_metadata(monkeypatch, ddl)
    require_registered_product(artifact_sha256="a" * 64, mode="play-prefix-play-v3")
    column = next(
        r
        for r in ddl["column_acl_expectations"]
        if r["expectation_id"]
        == EXPECTED_ADDITIONS["column_acl_expectations"][0]["expectation_id"]
    )
    policy = next(
        r
        for r in ddl["policies"]
        if r["policy_id"] == EXPECTED_ADDITIONS["policies"][1]["policy_id"]
    )
    if mutation == "role":
        column["grantee_role_id"] = "pitchlog_app"
    elif mutation == "privilege":
        column["privilege_ids"] = ["SELECT", "INSERT"]
    elif mutation == "grant-option":
        column["grant_option"] = True
    elif mutation == "column":
        column["column_id"] = "unapproved"
    elif mutation == "schema":
        column["object_schema"] = "sync_fence"
    elif mutation == "command":
        policy["command"] = "INSERT"
    elif mutation == "policy-role":
        policy["role_ids"] = ["pitchlog_app"]
    elif mutation == "using":
        policy["using_expression"] = "TRUE"
    elif mutation == "with-check":
        policy["with_check_expression"] = "TRUE"
    elif mutation == "duplicate":
        ddl["column_acl_expectations"].append(copy.deepcopy(column))
    else:
        ddl["policies"].remove(policy)
    with pytest.raises(OrdinaryPrefixError):
        require_registered_product(artifact_sha256="a" * 64, mode="play-prefix-play-v3")
