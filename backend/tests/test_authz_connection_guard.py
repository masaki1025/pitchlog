"""アプリ用ロール真正性判定の DB 不要な変異試験。"""

from dataclasses import replace

import pytest

from pitchlog.authz.runtime_contract import (
    APPLICATION_ROLE_ATTRIBUTES,
    APPLICATION_ROLE_NAME,
)
from pitchlog.db.engine import (
    _connection_observation_violations,
    _ConnectionObservation,
    _membership_violations,
    _MembershipEdge,
    _role_attribute_violations,
)


@pytest.mark.parametrize(
    ("attribute_name", "mutated_value"),
    (
        ("rolsuper", True),
        ("rolbypassrls", True),
        ("rolcanlogin", False),
        ("rolcreaterole", True),
        ("rolcreatedb", True),
        ("rolreplication", True),
        ("rolinherit", True),
    ),
)
def test_each_role_attribute_mutation_is_red(
    attribute_name: str,
    mutated_value: bool,
) -> None:
    """期待名を維持した全7属性の単独変異を拒否する。"""
    mutated = replace(
        APPLICATION_ROLE_ATTRIBUTES,
        **{attribute_name: mutated_value},
    )

    assert _role_attribute_violations(mutated) == [
        f"ロール属性が不一致: {attribute_name}"
    ]


def test_missing_expected_role_is_red() -> None:
    """期待アプリロール自体が無いカタログを拒否する。"""
    assert _role_attribute_violations(None) == [
        f"期待アプリロールが存在しない: {APPLICATION_ROLE_NAME}"
    ]


@pytest.mark.parametrize(
    "memberships",
    (
        (
            _MembershipEdge(
                APPLICATION_ROLE_NAME,
                "danger",
                admin_option=False,
                inherit_option=False,
                set_option=True,
            ),
        ),
        (
            _MembershipEdge(
                APPLICATION_ROLE_NAME,
                "middle",
                admin_option=False,
                inherit_option=False,
                set_option=True,
            ),
            _MembershipEdge(
                "middle",
                "danger",
                admin_option=False,
                inherit_option=False,
                set_option=True,
            ),
        ),
        (
            _MembershipEdge(
                APPLICATION_ROLE_NAME,
                "danger",
                admin_option=False,
                inherit_option=True,
                set_option=False,
            ),
        ),
        (
            _MembershipEdge(
                APPLICATION_ROLE_NAME,
                "middle",
                admin_option=False,
                inherit_option=True,
                set_option=False,
            ),
            _MembershipEdge(
                "middle",
                "danger",
                admin_option=False,
                inherit_option=True,
                set_option=False,
            ),
        ),
    ),
)
def test_direct_and_multihop_set_or_inherit_reachability_is_red(
    memberships: tuple[_MembershipEdge, ...],
) -> None:
    """SET と INHERIT の直接・多段到達をそれぞれ拒否する。"""
    assert _membership_violations(memberships, frozenset({"danger"})) == [
        "危険ロールへ到達可能: danger"
    ]


def test_set_then_inherit_mixed_reachability_is_red() -> None:
    """SET 閉包の各点から INHERIT 閉包を取る混合辺を拒否する。"""
    memberships = (
        _MembershipEdge(
            APPLICATION_ROLE_NAME,
            "middle",
            admin_option=False,
            inherit_option=False,
            set_option=True,
        ),
        _MembershipEdge(
            "middle",
            "danger",
            admin_option=False,
            inherit_option=True,
            set_option=False,
        ),
    )

    assert _membership_violations(memberships, frozenset({"danger"})) == [
        "危険ロールへ到達可能: danger"
    ]


def test_admin_option_is_red_even_without_set_or_inherit() -> None:
    """SET・INHERIT と独立して ADMIN OPTION を拒否する。"""
    memberships = (
        _MembershipEdge(
            APPLICATION_ROLE_NAME,
            "ordinary_role",
            admin_option=True,
            inherit_option=False,
            set_option=False,
        ),
    )

    assert _membership_violations(memberships, frozenset()) == [
        f"ADMIN OPTION を保持: {APPLICATION_ROLE_NAME}->ordinary_role"
    ]


@pytest.mark.parametrize("tenant_id", ("tenant-a", " "))
def test_nonempty_initial_tenant_guc_is_red(tenant_id: str) -> None:
    """接続開始前から非空のテナント GUC がある接続を拒否する。"""
    observation = _ConnectionObservation(
        session_user=APPLICATION_ROLE_NAME,
        current_user=APPLICATION_ROLE_NAME,
        attributes=APPLICATION_ROLE_ATTRIBUTES,
        tenant_id=tenant_id,
        memberships=(),
        dangerous_roles=frozenset(),
    )

    assert "接続開始時から app.tenant_id が設定済み" in (
        _connection_observation_violations(observation)
    )


def test_session_and_current_user_are_independent_exact_matches() -> None:
    """SET ROLE 偽装を session_user と current_user の独立照合で拒否する。"""
    observation = _ConnectionObservation(
        session_user="cluster_admin",
        current_user=APPLICATION_ROLE_NAME,
        attributes=APPLICATION_ROLE_ATTRIBUTES,
        tenant_id=None,
        memberships=(),
        dangerous_roles=frozenset(),
    )

    assert _connection_observation_violations(observation) == [
        "session_user が期待アプリロール名と不一致"
    ]
