"""probe ↔ 製品の原子要素写像を双方向 exact-set で検査する。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from product_authz_probe_product_map import (
    ProbeProductMapError,
    validate_probe_product_map,
)

from pitchlog.authz.runtime_contract_state import (
    evaluate_repository,
    product_asset_path_for_state,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MAP_PATH = _REPOSITORY_ROOT / "contracts/authz/product/probe-product-map.json"
_PROBE_PATH = _REPOSITORY_ROOT / "contracts/authz/ddl-elements.json"
_RG1_PRODUCT_ATOMS = frozenset(
    {
        "function:FUNCTION:rg1_api:rg1_assert_open_before_commit(uuid)",
        "function:FUNCTION:rg1_api:rg1_read_open(uuid)",
        "policy:POLICY:rg1_restore_gate:rg1_fn_lock_singleton",
        "policy:POLICY:rg1_restore_gate:rg1_fn_select_singleton",
        "role:pitchlog_rg1_fn_owner",
        "schema:rg1_api",
        "table:rg1_restore_gate",
    }
)
_STAGE_A_PRODUCT_ATOMS = frozenset(
    {
        "function:FUNCTION:public:resolve_stage_a_rule(uuid, text, text, boolean)",
        "role:pitchlog_rule_resolution_fn_owner",
    }
)

_INITIAL_START_PRODUCT_ATOMS = frozenset(
    {
        "policy:POLICY:lineup_memories:initial_start_actor_lineup_memories_update",
        "policy:POLICY:game_start_attempts:initial_right_game_start_attempts_insert",
        "function:FUNCTION:initial_right_api:lock_preparing_game(uuid, uuid)",
        "policy:POLICY:game_start_requests:initial_right_game_start_requests_insert",
        "policy:POLICY:trusted_devices:initial_right_trusted_devices_update",
        "function:FUNCTION:public:protect_initial_right_storage()",
        "policy:POLICY:game_start_requests:initial_right_game_start_requests_update",
        (
            "function:FUNCTION:initial_right_api:resolve_start_attempt(uuid, uuid"
            ", uuid, uuid)"
        ),
        "policy:POLICY:games:initial_right_games_select",
        "policy:POLICY:rg1_restore_gate:initial_right_rg1_restore_gate_select",
        "policy:POLICY:game_lineups:initial_start_owner_game_lineups_insert",
        "policy:POLICY:players:initial_start_actor_players_select",
        "policy:POLICY:players:initial_start_owner_players_select",
        "policy:POLICY:trusted_devices:initial_right_trusted_devices_insert",
        "policy:POLICY:lineup_memories:initial_start_actor_lineup_memories_select",
        "policy:POLICY:team_records:initial_start_actor_team_records_update",
        "policy:POLICY:team_records:initial_start_owner_team_records_update",
        "policy:POLICY:game_start_attempts:initial_right_game_start_attempts_update",
        "table:game_start_attempts",
        "table:game_start_requests",
        "table:recording_right_deliveries",
        "function:FUNCTION:initial_right_api:enroll_device(uuid, uuid, bytea)",
        "role:pitchlog_initial_auth_verifier",
        "schema:initial_right_api",
        (
            "function:FUNCTION:initial_right_api:begin_start_attempt(uuid, uuid, "
            "uuid, uuid, bytea, uuid)"
        ),
        (
            "function:FUNCTION:initial_right_api:persist_initial_start(uuid, uuid"
            ", uuid, uuid, bytea, text)"
        ),
        "policy:POLICY:team_records:initial_start_actor_team_records_select",
        "function:FUNCTION:initial_right_api:read_start_game(uuid, uuid)",
        "policy:POLICY:team_records:initial_start_owner_team_records_select",
        "function:FUNCTION:initial_right_api:check_business_epoch(uuid, bigint)",
        "policy:POLICY:game_start_attempts:initial_right_game_start_attempts_select",
        "policy:POLICY:game_start_requests:initial_right_game_start_requests_select",
        "function:FUNCTION:initial_right_api:lock_current_start(uuid, uuid, uuid)",
        (
            "policy:POLICY:recording_generations:initial_right_recording_generati"
            "ons_update"
        ),
        "policy:POLICY:players:initial_start_actor_players_update",
        "policy:POLICY:lineup_memories:initial_start_actor_lineup_memories_insert",
        "policy:POLICY:players:initial_start_owner_players_update",
        (
            "policy:POLICY:recording_right_deliveries:initial_right_recording_rig"
            "ht_deliveries_insert"
        ),
        "policy:POLICY:games:initial_right_games_update",
        "table:trusted_devices",
        (
            "policy:POLICY:recording_generations:initial_right_recording_generati"
            "ons_insert"
        ),
        "policy:POLICY:game_lineups:initial_start_owner_game_lineups_select",
        (
            "function:FUNCTION:initial_right_api:read_initial_start_context(uuid,"
            " uuid, uuid, uuid, bytea, text)"
        ),
        (
            "policy:POLICY:recording_right_deliveries:initial_right_recording_rig"
            "ht_deliveries_update"
        ),
        (
            "policy:POLICY:recording_generations:initial_right_recording_generati"
            "ons_select"
        ),
        (
            "function:FUNCTION:initial_right_api:lookup_existing_start_attempt(uu"
            "id, uuid, uuid, uuid, bytea)"
        ),
        (
            "policy:POLICY:recording_right_deliveries:initial_right_recording_rig"
            "ht_deliveries_select"
        ),
        "function:FUNCTION:initial_right_api:lock_device(uuid, uuid)",
        "function:FUNCTION:initial_right_api:read_existing_start(uuid, uuid, uuid)",
        "policy:POLICY:trusted_devices:initial_right_trusted_devices_select",
        (
            "function:FUNCTION:initial_right_api:insert_initial_grant(uuid, uuid,"
            " uuid, uuid, uuid, bigint, bigint, bytea, text, bytea, bytea)"
        ),
    }
)


def _product_path() -> Path:
    """共有 API が判定した状態の製品資産パスを返す。"""
    state, violations = evaluate_repository(_REPOSITORY_ROOT)
    assert not violations
    path = product_asset_path_for_state(state)
    assert path is not None
    return _REPOSITORY_ROOT / path


def _load_object(path: Path) -> dict[str, object]:
    """JSON object を読み込む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _documents() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """写像・probe・現在の製品資産を返す。"""
    return (
        _load_object(_MAP_PATH),
        _load_object(_PROBE_PATH),
        _load_object(_product_path()),
    )


def _rows(document: dict[str, object], key: str) -> list[object]:
    """変異対象の配列を返す。"""
    value = document[key]
    assert isinstance(value, list)
    return value


def _row_by_value(
    rows: list[object],
    *,
    key: str,
    value: str,
) -> dict[str, object]:
    """指定した値を持つ一意な object 行を返す。"""
    matches = tuple(
        row for row in rows if isinstance(row, dict) and row.get(key) == value
    )
    assert len(matches) == 1
    return matches[0]


def test_probe_product_map_is_bidirectionally_exact() -> None:
    """両側の母集合を資産から導き、全原子要素を一度ずつ処分する。"""
    mapping, probe, product = _documents()
    summary = validate_probe_product_map(mapping, probe, product)

    assert len(summary.probe_atoms) == 48
    assert {
        "role:pitchlog_auth_fn_owner",
        "schema:authn",
        "schema:authn_crypto",
        "function:FUNCTION:authn:login_attempt(text, text, text)",
        "function:FUNCTION:authn:observe_rate_limit_counters()",
    } <= summary.product_atoms
    assert summary.probe_atoms == (
        summary.mapped_probe_atoms | summary.explicit_non_mapping
    )
    assert not summary.mapped_probe_atoms & summary.explicit_non_mapping
    assert summary.product_atoms == summary.mapped_product_atoms | summary.product_only
    assert not summary.mapped_product_atoms & summary.product_only
    assert _RG1_PRODUCT_ATOMS <= summary.product_only
    assert _STAGE_A_PRODUCT_ATOMS <= summary.product_only
    assert {
        str(row["product"])
        for row in _rows(mapping, "product_only")
        if isinstance(row, dict)
        and row.get("product") in _RG1_PRODUCT_ATOMS
        and row.get("reason") == "product_only"
    } == _RG1_PRODUCT_ATOMS
    assert summary.one_to_many == frozenset(
        {
            "table:probe_business_rows",
            "policy:POLICY:probe_business_rows:tenant_boundary",
            "acl_privilege:ACL:probe_business_rows:app_role:SELECT",
            "acl_privilege:ACL:probe_business_rows:app_role:INSERT",
            "acl_privilege:ACL:probe_business_rows:app_role:UPDATE",
        }
    )


def test_removing_one_probe_mapping_is_red() -> None:
    """Probe 側の写像を 1 件消すと domain の不足として拒否する。"""
    mapping, probe, product = _documents()
    mutated = copy.deepcopy(mapping)
    mappings = _rows(mutated, "mappings")
    mappings.pop(0)

    with pytest.raises(ProbeProductMapError, match="probe 原子要素"):
        validate_probe_product_map(mutated, probe, product)


def test_adding_an_unclassified_product_element_is_red() -> None:
    """製品資産へ原子要素を足して処分しない変異を拒否する。"""
    mapping, probe, product = _documents()
    mutated_product = copy.deepcopy(product)
    _rows(mutated_product, "tables").append({"table_id": "unmapped_product_table"})

    with pytest.raises(ProbeProductMapError, match="製品原子要素"):
        validate_probe_product_map(mapping, probe, mutated_product)


def test_removing_one_rg1_product_only_atom_is_red() -> None:
    """RG1 の登録を 1 件消しても製品原子の欠落として検出する。"""
    mapping, probe, product = _documents()
    mutated = copy.deepcopy(mapping)
    rows = _rows(mutated, "product_only")
    rows.remove(
        _row_by_value(
            rows,
            key="product",
            value="policy:POLICY:rg1_restore_gate:rg1_fn_lock_singleton",
        )
    )

    with pytest.raises(ProbeProductMapError, match="製品原子要素"):
        validate_probe_product_map(mutated, probe, product)


@pytest.mark.parametrize("atom", sorted(_STAGE_A_PRODUCT_ATOMS))
def test_removing_stage_a_product_only_atom_is_red(atom: str) -> None:
    """段階Aのownerと固定関数のどちらの欠落も拒否する。"""
    mapping, probe, product = _documents()
    mutated = copy.deepcopy(mapping)
    rows = _rows(mutated, "product_only")
    rows.remove(_row_by_value(rows, key="product", value=atom))

    with pytest.raises(ProbeProductMapError, match="製品原子要素"):
        validate_probe_product_map(mutated, probe, product)


@pytest.mark.parametrize("atom", sorted(_STAGE_A_PRODUCT_ATOMS))
def test_unapproved_stage_a_product_only_atom_is_red(atom: str) -> None:
    """似た未登録owner・関数を写像で勝手に増やせない。"""
    mapping, probe, product = _documents()
    mutated = copy.deepcopy(mapping)
    _rows(mutated, "product_only").append(
        {"product": atom + "_outside", "reason": "product_only"}
    )

    with pytest.raises(ProbeProductMapError, match="製品原子要素"):
        validate_probe_product_map(mutated, probe, product)


def test_unknown_reason_code_is_red() -> None:
    """閉じた列挙に無い理由コードを拒否する。"""
    mapping, probe, product = _documents()
    mutated = copy.deepcopy(mapping)
    row = _row_by_value(
        _rows(mutated, "explicit_non_mapping"),
        key="probe",
        value="role:outsider_role",
    )
    row["reason"] = "unknown_reason"

    with pytest.raises(ProbeProductMapError, match="未知の非写像理由コード"):
        validate_probe_product_map(mutated, probe, product)


def test_reason_code_for_the_wrong_element_kind_is_red() -> None:
    """schema・table・policy 用の理由を role へ使う変異を拒否する。"""
    mapping, probe, product = _documents()
    mutated = copy.deepcopy(mapping)
    row = _row_by_value(
        _rows(mutated, "explicit_non_mapping"),
        key="probe",
        value="role:provisioner",
    )
    row["reason"] = "probe_schema_only"

    with pytest.raises(ProbeProductMapError, match="role に使えない"):
        validate_probe_product_map(mutated, probe, product)


def test_read_control_resources_owner_other_than_u_c2_is_red() -> None:
    """制御資源読み取り関数の受け取り先を U-C2 以外へ変えられない。"""
    mapping, probe, product = _documents()
    mutated = copy.deepcopy(mapping)
    row = _row_by_value(
        _rows(mutated, "explicit_non_mapping"),
        key="probe",
        value="function:read_control_resources",
    )
    row["owner_unit"] = "U-C3"

    with pytest.raises(ProbeProductMapError, match="owner_unit は U-C2"):
        validate_probe_product_map(mutated, probe, product)


def test_unapproved_one_to_many_mapping_is_red() -> None:
    """Exact-set を保っても許可集合外の 1 対多は拒否する。"""
    mapping, probe, product = _documents()
    mutated = copy.deepcopy(mapping)
    table_mapping = _row_by_value(
        _rows(mutated, "mappings"),
        key="probe",
        value="table:probe_groups",
    )
    products = table_mapping["products"]
    assert isinstance(products, list)
    products.append("table:tenants")
    product_only = _rows(mutated, "product_only")
    product_only.remove(
        _row_by_value(product_only, key="product", value="table:tenants")
    )

    with pytest.raises(ProbeProductMapError, match="許可した 1 対多"):
        validate_probe_product_map(mutated, probe, product)


def test_app_role_delete_is_forbidden_by_canon() -> None:
    """Probe にある app_role の DELETE を正本禁止として全件処分する。"""
    mapping, probe, product = _documents()
    validate_probe_product_map(mapping, probe, product)
    rows = _rows(mapping, "explicit_non_mapping")
    delete_rows = tuple(
        row
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("probe"), str)
        and row["probe"].endswith(":app_role:DELETE")
    )

    assert len(delete_rows) == 2
    assert {row.get("reason") for row in delete_rows} == {"forbidden_by_canon"}


def test_initial_start_atoms_and_removed_direct_grants_are_exact() -> None:
    """採用済初期権/開始の有限51原子と旧直ACL不在を閉集合で照合する。"""
    mapping, probe, product = _documents()
    summary = validate_probe_product_map(mapping, probe, product)
    assert len(_INITIAL_START_PRODUCT_ATOMS) == 51
    assert _INITIAL_START_PRODUCT_ATOMS <= summary.product_only
    for privilege in ("SELECT", "INSERT", "UPDATE"):
        atom = f"acl_privilege:ACL:recording_generations:pitchlog_app:{privilege}"
        assert atom not in summary.product_atoms
        assert atom not in summary.mapped_product_atoms
    for atom in _INITIAL_START_PRODUCT_ATOMS:
        mutated = copy.deepcopy(mapping)
        rows = _rows(mutated, "product_only")
        rows.remove(_row_by_value(rows, key="product", value=atom))
        with pytest.raises(ProbeProductMapError):
            validate_probe_product_map(mutated, probe, product)
