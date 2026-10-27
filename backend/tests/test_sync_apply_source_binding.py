"""source選択のpure登録double/未発行拒否。実受付/同writer証明ではない。"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from pitchlog.repositories.context import _ISSUANCE_CAPABILITY, TenantContext
from pitchlog.sync import source_binding as api
from pitchlog.sync.idempotency import operation_fingerprint
from pitchlog.sync.model import SyncEvent, SyncRequest
from pitchlog.sync.wire_source import freeze_wire_source

_ROOT = Path(__file__).resolve().parents[2]
_VECTORS = json.loads(
    (_ROOT / "contracts/state-transition/wire_fingerprint_vectors_v1.json").read_text()
)
_TENANT = UUID("30000000-0000-0000-0000-000000000001")
_ERROR = "E-1又はlegacyの発行済みsourceを利用できません"


def _raw() -> dict[str, Any]:
    return json.loads(_VECTORS["event_cases"][0]["raw_json"])


def _event(raw: dict[str, Any]) -> SyncEvent:
    fields = {
        "event_kind": "v5",
        "d2": "v6",
        "payload": "v7",
        "state_diff": "v8",
        "replacement_state": "v9",
        "target_reference": "v10",
        "expected_version": "v11",
    }
    return SyncEvent(
        raw["d5"],
        raw["game_id"],
        raw.get("d1"),
        raw.get("d4"),
        **{attr: raw[key] for key, attr in fields.items() if key in raw},
    )


def _request(raw: dict[str, Any]) -> SyncRequest:
    return SyncRequest("P1", raw["game_id"], (_event(raw),), d4=raw["d4"])


@pytest.fixture(autouse=True)
def registry_isolation() -> Any:
    """実装は未発行のまま、pure testの直接登録だけを隔離する。"""
    assert not api._LEGACY and not api._RECEIPTS and not api._SELECTIONS
    yield
    api._LEGACY.clear()
    api._RECEIPTS.clear()
    api._SELECTIONS.clear()


def _legacy_double(
    request: SyncRequest, registration: Any = None
) -> api.LegacyEntryScope:
    # 実issuerではない。私有stateの関係を検査するためtest内だけで登録する。
    owner = object.__new__(api.LegacyEntryScope)
    api._LEGACY[owner] = api._LegacyState(
        request,
        api._request_json(request),
        (registration,),
        (operation_fingerprint(request.events[0], request.path, registration),),
        True,
    )
    return owner


def _receipt_double(raw: dict[str, Any]) -> tuple[api.E1Receipt, SyncRequest]:
    # context証跡は既型を使うが、HTTP認証を通った受付の証明ではない。
    request = _request(raw)
    receipt = object.__new__(api.E1Receipt)
    api._RECEIPTS[receipt] = api._ReceiptState(
        TenantContext(_TENANT, _ISSUANCE_CAPABILITY),
        _TENANT,
        request,
        api._request_json(request),
        freeze_wire_source(
            game_id=raw["game_id"],
            d4=raw["d4"],
            raw_events=(raw,),
        ),
        True,
    )
    return receipt, request


@pytest.mark.parametrize("row", _VECTORS["event_cases"], ids=lambda r: r["case_id"])
def test_pure_e1_correspondence_fixed_vectors(row: dict[str, Any]) -> None:
    """直接登録doubleが原event専用hashを返す対応だけを検査する。"""
    receipt, request = _receipt_double(json.loads(row["raw_json"]))
    binding = api.e1_event_source(receipt, 1)
    assert (
        api.selected_event_fingerprint(binding, request.events[0])
        == row["expected_fingerprint"]
    )
    assert not hasattr(binding, "fingerprint")
    assert not hasattr(binding, "origin")


@dataclass(frozen=True)
class _Registration:
    temporary_id: UUID
    team_record_id: UUID
    name: str
    roster_status_key: str


@pytest.mark.parametrize(
    "registration", [None, _Registration(_TENANT, _TENANT, "秘密名", "active")]
)
def test_legacy_formula_and_same_registration_identity(registration: Any) -> None:
    """既式/引数を変更せず、同値の自由registrationへの置換も拒否する。"""
    request = _request(_raw())
    expected = operation_fingerprint(request.events[0], request.path, registration)
    owner = _legacy_double(request, registration)
    binding = api.legacy_dto_source(owner, request, request.events[0], registration)
    assert api.selected_event_fingerprint(binding, request.events[0]) == expected
    assert not expected.startswith("wire-")
    if registration is not None:
        other = _Registration(_TENANT, _TENANT, "秘密名", "active")
        with pytest.raises(api.SourceBindingError):
            api.legacy_dto_source(owner, request, request.events[0], other)


@pytest.mark.parametrize(
    "kind", [api.LegacyEntryScope, api.E1Receipt, api.EventSourceBinding]
)
def test_no_public_constructor(kind: Any) -> None:
    """直接生成や同型未登録を成功資格にしない。"""
    with pytest.raises(api.SourceBindingError, match=f"^{_ERROR}$"):
        kind()


@pytest.mark.parametrize("candidate", [None, False, "E1", {}, object()])
def test_no_issuer_no_fallback(
    candidate: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """origin自己申告・pure source・未登録は旧式呼出し0で拒否する。"""

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("未発行から旧指紋へ到達")

    monkeypatch.setattr(api, "operation_fingerprint", forbidden)
    raw = _raw()
    request = _request(raw)
    pure = freeze_wire_source(game_id=raw["game_id"], d4=raw["d4"], raw_events=(raw,))
    for fake in (
        candidate,
        pure,
        object.__new__(api.E1Receipt),
        object.__new__(api.LegacyEntryScope),
    ):
        with pytest.raises(api.SourceBindingError, match=f"^{_ERROR}$"):
            cast(Any, api.e1_event_source)(fake, 1)
        with pytest.raises(api.SourceBindingError, match=f"^{_ERROR}$"):
            cast(Any, api.legacy_dto_source)(fake, request, request.events[0], None)
    assert not api._SELECTIONS


@pytest.mark.parametrize("position", [None, False, True, 0, -1, 2, 1.0, "1"])
def test_position_strict(position: Any) -> None:
    """原位置はstrict整数1始まりとしD1順へ並び替えない。"""
    receipt, _ = _receipt_double(_raw())
    with pytest.raises(api.SourceBindingError):
        api.e1_event_source(receipt, position)


@pytest.mark.parametrize("mode", ["e1", "legacy"])
@pytest.mark.parametrize(
    "change",
    [
        "expire",
        "remove-owner",
        "replace-state",
        "other-event",
        "other-request",
        "event-value",
        "request-value",
        "origin",
        "digest",
        "position",
        "binding-fake",
    ],
)
def test_selected_binding_revalidates_full_state(mode: str, change: str) -> None:
    """選択後の変更/失効/同値他参照/自由digestを再使用させない。"""
    if mode == "e1":
        owner, request = _receipt_double(_raw())
        binding = api.e1_event_source(owner, 1)
        registry = cast(Any, api._RECEIPTS)
    else:
        request = _request(_raw())
        owner = _legacy_double(request)
        binding = api.legacy_dto_source(owner, request, request.events[0], None)
        registry = cast(Any, api._LEGACY)
    state = registry[owner]
    event = request.events[0]
    selected = api._SELECTIONS[binding]
    if change == "expire":
        state.active = False
    elif change == "remove-owner":
        del registry[owner]
    elif change == "replace-state":
        registry[owner] = object()
    elif change == "other-event":
        event = _event(_raw())
    elif change == "other-request":
        state.request = _request(_raw())
    elif change == "event-value":
        object.__setattr__(event, "v7", {"secret-value": 1})
    elif change == "request-value":
        object.__setattr__(request, "v12", "secret-value")
    elif change == "origin":
        object.__setattr__(
            selected,
            "owner",
            object.__new__(api.LegacyEntryScope if mode == "e1" else api.E1Receipt),
        )
    elif change == "digest":
        object.__setattr__(selected, "fingerprint", "wire-v1:" + "0" * 64)
    elif change == "position":
        object.__setattr__(selected, "position", True)
    else:
        binding = object.__new__(api.EventSourceBinding)
    with pytest.raises(api.SourceBindingError, match=f"^{_ERROR}$") as error:
        api.selected_event_fingerprint(binding, event)
    assert error.value.__cause__ is None
    assert "secret-value" not in str(error.value)


@pytest.mark.parametrize(
    "change",
    ["context", "proof", "tenant", "source", "dto-content", "raw-registration"],
)
def test_receipt_context_and_raw_all_values_revalidated(change: str) -> None:
    """context証跡/tenant/原全値とDTO共有全値の変更を閉じる。"""
    raw = _raw()
    receipt, request = _receipt_double(raw)
    binding = api.e1_event_source(receipt, 1)
    state = api._RECEIPTS[receipt]
    if change == "context":
        cast(Any, state).context = object()
    elif change == "proof":
        object.__setattr__(state.context, "_integrity_proof", b"bad")
    elif change == "tenant":
        state.tenant_id = UUID("40000000-0000-0000-0000-000000000001")
    elif change == "source":
        object.__setattr__(
            state.source, "request_fingerprint", "wire-request-v1:" + "0" * 64
        )
    elif change == "dto-content":
        object.__setattr__(request.events[0], "v5", "other")
        state.request_json = api._request_json(request)
    else:
        raw["registration"] = {"name": "secret-value"}
        state.source = freeze_wire_source(
            game_id=raw["game_id"], d4=raw["d4"], raw_events=(raw,)
        )
    with pytest.raises(api.SourceBindingError):
        api.selected_event_fingerprint(binding, request.events[0])


def test_no_issuer_registration_api_and_no_mutation_of_old_paths() -> None:
    """本体に真正参照の発行/登録APIを追加していない。"""
    source = inspect.getsource(api)
    assert "_LEGACY[" not in source.replace("state = _LEGACY[owner]", "")
    assert "_RECEIPTS[" not in source.replace("state = _RECEIPTS[owner]", "")
    assert all("issuer" not in name for name in vars(api) if not name.startswith("_"))
    assert set(inspect.signature(api.e1_event_source).parameters) == {
        "receipt",
        "position",
    }
    assert set(inspect.signature(api.selected_event_fingerprint).parameters) == {
        "binding",
        "event",
    }


@pytest.mark.parametrize("row", _VECTORS["request_cases"], ids=lambda r: r["case_id"])
def test_request_vectors_keep_raw_positions(row: dict[str, Any]) -> None:
    """D1順hashと原位置を混同せず、列の全memberを消費する。"""
    raw = json.loads(row["raw_events_json"])
    events = tuple(_event(value) for value in raw)
    request = SyncRequest("P1", row["game_id"], events, d4=row["d4"])
    source = freeze_wire_source(
        game_id=row["game_id"], d4=row["d4"], raw_events=tuple(raw)
    )
    receipt = object.__new__(api.E1Receipt)
    api._RECEIPTS[receipt] = api._ReceiptState(
        TenantContext(_TENANT, _ISSUANCE_CAPABILITY),
        _TENANT,
        request,
        api._request_json(request),
        source,
        True,
    )
    assert source.request_fingerprint == row["expected_fingerprint"]
    ordered = sorted(value["d1"] for value in raw)
    for position, (value, event) in enumerate(zip(raw, events, strict=True), 1):
        selected = api.e1_event_source(receipt, position)
        assert (
            api.selected_event_fingerprint(selected, event)
            == row["expected_event_fingerprints_d1_order"][ordered.index(value["d1"])]
        )


@pytest.mark.parametrize("change", ["request", "source", "context"])
def test_same_value_other_identity_is_not_same_receipt(change: str) -> None:
    """同値の別request/source/contextでも選択後に置換できない。"""
    raw = _raw()
    owner, request = _receipt_double(raw)
    selected = api.e1_event_source(owner, 1)
    state = api._RECEIPTS[owner]
    if change == "request":
        state.request = SyncRequest(
            request.path, request.game_id, request.events, d4=request.d4
        )
    elif change == "source":
        state.source = freeze_wire_source(
            game_id=raw["game_id"], d4=raw["d4"], raw_events=(raw,)
        )
    else:
        state.context = TenantContext(_TENANT, _ISSUANCE_CAPABILITY)
    with pytest.raises(api.SourceBindingError):
        api.selected_event_fingerprint(selected, request.events[0])


def test_legacy_registration_changed_after_selection() -> None:
    """旧式が同じでも登録DTOの別参照へ後から変更しない。"""
    first = _Registration(_TENANT, _TENANT, "秘密名", "active")
    other = _Registration(_TENANT, _TENANT, "秘密名", "active")
    request = _request(_raw())
    owner = _legacy_double(request, first)
    binding = api.legacy_dto_source(owner, request, request.events[0], first)
    api._LEGACY[owner].registrations = (other,)
    with pytest.raises(api.SourceBindingError):
        api.selected_event_fingerprint(binding, request.events[0])


@pytest.mark.parametrize("origin", ["legacy", "e1"])
def test_cross_origin_even_with_injected_state_is_rejected(origin: str) -> None:
    """pure私有stateを他型keyへ転用してもoriginを変更できない。"""
    receipt, request = _receipt_double(_raw())
    legacy = _legacy_double(request)
    if origin == "legacy":
        cast(Any, api._LEGACY)[receipt] = api._LEGACY[legacy]
        with pytest.raises(api.SourceBindingError):
            cast(Any, api.legacy_dto_source)(receipt, request, request.events[0], None)
    else:
        cast(Any, api._RECEIPTS)[legacy] = api._RECEIPTS[receipt]
        with pytest.raises(api.SourceBindingError):
            cast(Any, api.e1_event_source)(legacy, 1)


@pytest.mark.parametrize(
    "kind", [api.LegacyEntryScope, api.E1Receipt, api.EventSourceBinding]
)
def test_subclass_references_are_not_registered_exact_types(kind: Any) -> None:
    """派生参照を本物と同じregistryへ載せても実型を拒否する。"""
    child = type("ChildReference", (kind,), {"__slots__": ()})
    fake = object.__new__(child)
    receipt, request = _receipt_double(_raw())
    legacy = _legacy_double(request)
    if kind is api.LegacyEntryScope:
        cast(Any, api._LEGACY)[fake] = api._LEGACY[legacy]
        with pytest.raises(api.SourceBindingError):
            api.legacy_dto_source(fake, request, request.events[0], None)
    elif kind is api.E1Receipt:
        cast(Any, api._RECEIPTS)[fake] = api._RECEIPTS[receipt]
        with pytest.raises(api.SourceBindingError):
            api.e1_event_source(fake, 1)
    else:
        binding = api.e1_event_source(receipt, 1)
        cast(Any, api._SELECTIONS)[fake] = api._SELECTIONS[binding]
        with pytest.raises(api.SourceBindingError):
            api.selected_event_fingerprint(fake, request.events[0])
