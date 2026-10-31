"""開始閉payloadの型・凍結・要求同値だけを検査し、開始成功を仮定しない。"""

from __future__ import annotations

import copy
import hashlib
import json
import traceback
from dataclasses import FrozenInstanceError, replace
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import SecretStr, ValidationError

from pitchlog.api.schemas.game_start import GameStartRequest, StartLineupInput
from pitchlog.repositories.game_start import (
    BoundInitialStartPayload,
    InitialStartLineupEntry,
    InitialStartPayload,
    InitialStartPayloadInvalid,
    StartDesignatedHitterRole,
    StartFieldingRole,
    bind_initial_start_request,
)
from pitchlog.repositories.initial_recording_right import _credential_digest
from pitchlog.sync.idempotency import source_fingerprint

_CREDENTIAL = "synthetic-start-credential-not-an-operational-secret"
_TENANT = UUID(int=1)
_GAME = UUID(int=2)
_ATTEMPT = UUID(int=3)


def _body(size: int = 10) -> dict[str, Any]:
    """公式9/10名の公開合成transport例を作る。業務検証器ではない。"""
    sides = {}
    for side, offset in (("away", 100), ("home", 200)):
        entries: list[dict[str, Any]] = [
            {
                "player_id": str(UUID(int=offset + i)),
                "batting_order": i,
                "fielding_position": {"kind": "fielding", "position": i},
            }
            for i in range(1, 10)
        ]
        if size == 10:
            entries[0]["batting_order"] = None
            entries.append(
                {
                    "player_id": str(UUID(int=offset + 10)),
                    "batting_order": 1,
                    "fielding_position": {"kind": "designated-hitter"},
                }
            )
        sides[side] = entries
    return {
        "start_request_id": str(UUID(int=4)),
        "device_id": str(UUID(int=5)),
        "device_credential": _CREDENTIAL,
        **sides,
    }


def _bind(body: dict[str, Any] | None = None, **owner: Any) -> BoundInitialStartPayload:
    """既DTOを通し、owner入力だけを検査対象へ渡す。"""
    return bind_initial_start_request(
        GameStartRequest.model_validate(_body() if body is None else body),
        tenant_id=owner.get("tenant_id", _TENANT),
        game_id=owner.get("game_id", _GAME),
        attempt_id=owner.get("attempt_id", _ATTEMPT),
    )


@pytest.mark.parametrize("size", (9, 10))
def test_closed_payload_reuses_existing_dto_roles_and_fingerprint(size: int) -> None:
    """9/10外形と既単一指紋helperの全bytes同値を確認する。"""
    bound = _bind(_body(size))
    assert len(bound.payload.away) == len(bound.payload.home) == size
    assert type(bound.payload.away[0].player_id) is UUID
    assert type(bound.payload.away[0].fielding_position) is StartFieldingRole
    if size == 10:
        assert bound.payload.away[0].batting_order is None
        assert (
            type(bound.payload.away[-1].fielding_position) is StartDesignatedHitterRole
        )
    assert _CREDENTIAL not in bound.canonical_bytes.decode("utf-8")
    assert _CREDENTIAL not in repr(bound)
    source = json.loads(bound.canonical_bytes)
    assert source["domain"] == "pitchlog.initial-game-start.v1"
    assert source["credential_digest"] == _credential_digest(_CREDENTIAL).hex()
    assert bytes.fromhex(source_fingerprint(source)) == bound.owner.request_digest
    assert hashlib.sha256(bound.canonical_bytes).digest() == bound.owner.request_digest
    bound.assert_owner(bound.owner)


def test_payload_is_detached_and_deeply_frozen() -> None:
    """元DTO/元dictを変えても内部bytesは不変で各入れ子への代入も拒否する。"""
    body = _body()
    request = GameStartRequest.model_validate(body)
    bound = bind_initial_start_request(
        request, tenant_id=_TENANT, game_id=_GAME, attempt_id=_ATTEMPT
    )
    original = bound.canonical_bytes
    body["away"][0]["fielding_position"]["position"] = 8
    role = request.away[0].fielding_position
    assert type(role) is dict
    role["position"] = 7
    request.away[0].batting_order = 8
    request.device_credential = SecretStr("changed-after-binding")
    assert bound.canonical_bytes == original
    for obj, field, value in (
        (bound, "credential_digest", b"x" * 32),
        (bound.payload, "away", ()),
        (bound.payload.away[0], "batting_order", 9),
        (bound.payload.away[0].fielding_position, "position", 9),
        (bound.owner, "device_id", UUID(int=999)),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, field, value)


def test_same_payload_and_json_key_order_have_same_bytes() -> None:
    """objectキー順を揃え、配列順や型を推測で変換しない。"""
    body = _body()
    reordered = json.loads(json.dumps(body, sort_keys=True))
    assert _bind(body).canonical_bytes == _bind(reordered).canonical_bytes
    assert (
        _bind(body).owner.request_digest
        == _bind(copy.deepcopy(body)).owner.request_digest
    )
    reordered["away"].reverse()
    assert _bind(body).owner.request_digest != _bind(reordered).owner.request_digest


@pytest.mark.parametrize(
    "change",
    (
        "player",
        "order",
        "role",
        "role-kind",
        "side",
        "request",
        "device",
        "credential",
        "tenant",
        "game",
    ),
)
def test_every_payload_or_owner_identity_change_changes_digest(change: str) -> None:
    """全side/選手/role/要求/owner/資格を指紋へ結合する。"""
    body = _body()
    owner: dict[str, Any] = {}
    if change == "player":
        body["away"][0]["player_id"] = str(UUID(int=900))
    elif change == "order":
        body["home"][0]["batting_order"] = 2
    elif change == "role":
        body["home"][0]["fielding_position"]["position"] = 2
    elif change == "role-kind":
        body["away"][0]["fielding_position"] = {"kind": "designated-hitter"}
    elif change == "side":
        body["away"], body["home"] = body["home"], body["away"]
    elif change in {"request", "device"}:
        body["start_request_id" if change == "request" else "device_id"] = str(
            UUID(int=901)
        )
    elif change == "credential":
        body["device_credential"] = "different-synthetic-credential"
    else:
        owner["tenant_id" if change == "tenant" else "game_id"] = UUID(int=902)
    changed = _bind(body, **owner)
    assert changed.owner.request_digest != _bind().owner.request_digest
    with pytest.raises(InitialStartPayloadInvalid):
        changed.assert_owner(_bind().owner)


def test_attempt_is_bound_but_not_part_of_request_fingerprint() -> None:
    """サーバーのattempt変更は同要求の指紋を変えず同scope ownerでは区別する。"""
    first, second = _bind(), _bind(attempt_id=UUID(int=99))
    assert first.canonical_bytes == second.canonical_bytes
    assert first.owner.request_digest == second.owner.request_digest
    with pytest.raises(InitialStartPayloadInvalid):
        first.assert_owner(second.owner)


@pytest.mark.parametrize(
    "role",
    (
        None,
        1,
        "1",
        [],
        {"kind": "fielding"},
        {"kind": "fielding", "position": True},
        {"kind": "fielding", "position": 1.0},
        {"kind": "fielding", "position": "1"},
        {"kind": "fielding", "position": 0},
        {"kind": "fielding", "position": 10},
        {"kind": "fielding", "position": 1, "extra": _CREDENTIAL},
        {"kind": "designated-hitter", "position": 1},
        {"kind": "unknown"},
    ),
)
def test_rejects_nonclosed_role_without_exposing_input(role: Any) -> None:
    """JsonValue通過をrole受理とせず、不正値を固定例外へ閉じる。"""
    body = _body()
    body["away"][0]["fielding_position"] = role
    with pytest.raises(InitialStartPayloadInvalid) as exc:
        _bind(body)
    assert _CREDENTIAL not in repr(exc.value)
    assert _CREDENTIAL not in "".join(traceback.format_exception(exc.value))


@pytest.mark.parametrize("value", (True, 1.0, "1", 0, 10))
def test_closed_entry_rejects_order_coercion(value: Any) -> None:
    """DTOを迂回した構築でもStrictIntを保持する。"""
    with pytest.raises(InitialStartPayloadInvalid):
        InitialStartLineupEntry(UUID(int=1), value, StartFieldingRole(1))


@pytest.mark.parametrize("value", ("not-a-uuid", str(UUID(int=1)), 1, None))
def test_closed_entry_rejects_uuid_coercion(value: Any) -> None:
    """公式UUID型の内部へ文字列表現を暗黙に混ぜない。"""
    with pytest.raises(InitialStartPayloadInvalid):
        InitialStartLineupEntry(value, 1, StartFieldingRole(1))


@pytest.mark.parametrize(
    "mutation", ("extra", "missing", "bad-uuid", "bad-order", "size")
)
def test_existing_dto_rejects_transport_errors_without_credential(
    mutation: str,
) -> None:
    """既DTOの拒否/非露出を再利用し別のDTOを定義しない。"""
    body = _body()
    if mutation == "extra":
        body["away"][0]["unexpected"] = _CREDENTIAL
    elif mutation == "missing":
        del body["home"][0]["player_id"]
    elif mutation == "bad-uuid":
        body["away"][0]["player_id"] = "bad"
    elif mutation == "bad-order":
        body["home"][0]["batting_order"] = True
    else:
        body["home"] = []
    with pytest.raises(ValidationError) as exc:
        _bind(body)
    assert _CREDENTIAL not in str(exc.value)
    assert _CREDENTIAL not in exc.value.json()


def test_noncanonical_uuid_wire_spelling_uses_existing_dto_normalization() -> None:
    """既DTOのUUID解析を変えず内部canonical文字列だけを使う。"""
    body = _body()
    body["device_id"] = "{00000000-0000-0000-0000-000000000005}"
    assert _bind(body).canonical_bytes == _bind().canonical_bytes


def test_no_dh_or_duplicate_baseball_validation_is_implemented_here() -> None:
    """同じ選手/打順/守備や9対10も形だけは保持し、TS/DB受理と混同しない。"""
    body = _body()
    body["away"] = [copy.deepcopy(body["away"][0]) for _ in range(9)]
    bound = _bind(body)
    assert len(bound.payload.away) == 9 and len(bound.payload.home) == 10
    assert len({entry.player_id for entry in bound.payload.away}) == 1
    assert not hasattr(bound, "grant")
    assert not hasattr(bound, "started_at")


def test_forged_digest_or_credential_binding_is_rejected() -> None:
    """caller指定digest/資格digestの差替えを実素材の再計算で拒否する。"""
    bound = _bind()
    for change in (b"x" * 32, b"short"):
        with pytest.raises(InitialStartPayloadInvalid):
            replace(bound, credential_digest=change)
    with pytest.raises(InitialStartPayloadInvalid):
        replace(bound, owner=replace(bound.owner, request_digest=b"x" * 32))


def test_invalid_credential_does_not_chain_original_exception() -> None:
    """既資格digest失敗を固定例外へ閉じ、原値をcontextに連鎖しない。"""
    request = GameStartRequest.model_validate(_body())
    request.device_credential = SecretStr("bad-surrogate-\ud800")
    with pytest.raises(InitialStartPayloadInvalid) as exc:
        bind_initial_start_request(
            request, tenant_id=_TENANT, game_id=_GAME, attempt_id=_ATTEMPT
        )
    assert exc.value.__context__ is None
    assert "surrogate" not in str(exc.value)


def test_direct_closed_types_reject_mutable_or_derived_values() -> None:
    """不変payloadへlist/派生role/派生entryを持ち込ませない。"""
    bound = _bind()
    with pytest.raises(InitialStartPayloadInvalid):
        InitialStartPayload(cast(Any, list(bound.payload.away)), bound.payload.home)
    with pytest.raises(InitialStartPayloadInvalid):
        InitialStartPayload((), bound.payload.home)

    class DerivedRole(StartFieldingRole):
        pass

    with pytest.raises(InitialStartPayloadInvalid):
        InitialStartLineupEntry(UUID(int=1), None, DerivedRole(1))


def test_missing_fields_or_fake_dto_and_owner_are_rejected() -> None:
    """model_construct/任意objectで閉境界を迂回できない。"""
    for request in (object(), GameStartRequest.model_construct()):
        with pytest.raises(InitialStartPayloadInvalid):
            bind_initial_start_request(
                cast(Any, request),
                tenant_id=_TENANT,
                game_id=_GAME,
                attempt_id=_ATTEMPT,
            )
    bound = _bind()
    with pytest.raises(InitialStartPayloadInvalid):
        bound.assert_owner(cast(Any, object()))
    with pytest.raises(InitialStartPayloadInvalid):
        _bind(tenant_id=str(_TENANT))
    bad = StartLineupInput.model_construct()
    request = GameStartRequest.model_validate(_body())
    request.away = (bad,) * 9
    with pytest.raises(InitialStartPayloadInvalid):
        bind_initial_start_request(
            request, tenant_id=_TENANT, game_id=_GAME, attempt_id=_ATTEMPT
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "unknown-dh-role",
        "unknown-fielding-role",
        "position-bool",
        "position-string",
        "position-out-of-range",
        "player-uuid-string",
        "player-unknown",
        "order-bool",
        "order-string",
        "order-out-of-range",
        "away-list",
        "away-short-tuple",
        "home-list",
        "unknown-entry",
        "unknown-payload",
        "owner-tenant-string",
        "owner-attempt-string",
        "owner-digest-string",
        "credential-bytearray",
    ),
)
def test_low_level_nested_changes_are_rejected_before_canonicalization(
    mutation: str,
) -> None:
    """低水準変更も閉値へ再検証し、未知roleを既存DHへ畳み込まない。"""
    bound = _bind()
    original = bound.canonical_bytes
    entry = bound.payload.away[0]
    if mutation == "unknown-dh-role":
        object.__setattr__(bound.payload.away[-1], "fielding_position", object())
    elif mutation == "unknown-fielding-role":
        object.__setattr__(entry, "fielding_position", object())
    elif mutation.startswith("position-"):
        value = {
            "position-bool": True,
            "position-string": "1",
            "position-out-of-range": 10,
        }[mutation]
        object.__setattr__(entry.fielding_position, "position", value)
    elif mutation.startswith("player-"):
        value = str(entry.player_id) if mutation == "player-uuid-string" else object()
        object.__setattr__(entry, "player_id", value)
    elif mutation.startswith("order-"):
        value = {"order-bool": True, "order-string": "1", "order-out-of-range": 10}[
            mutation
        ]
        object.__setattr__(entry, "batting_order", value)
    elif mutation in {"away-list", "home-list"}:
        side = mutation.split("-")[0]
        object.__setattr__(bound.payload, side, list(getattr(bound.payload, side)))
    elif mutation == "away-short-tuple":
        object.__setattr__(bound.payload, "away", bound.payload.away[:8])
    elif mutation == "unknown-entry":
        object.__setattr__(bound.payload, "away", (object(),) + bound.payload.away[1:])
    elif mutation == "unknown-payload":
        object.__setattr__(bound, "payload", object())
    elif mutation == "owner-tenant-string":
        object.__setattr__(bound.owner, "tenant_id", str(bound.owner.tenant_id))
    elif mutation == "owner-attempt-string":
        object.__setattr__(bound.owner, "attempt_id", str(bound.owner.attempt_id))
    elif mutation == "owner-digest-string":
        object.__setattr__(
            bound.owner, "request_digest", bound.owner.request_digest.hex()
        )
    else:
        object.__setattr__(
            bound, "credential_digest", bytearray(bound.credential_digest)
        )
    assert original
    with pytest.raises(InitialStartPayloadInvalid):
        _ = bound.canonical_bytes
    with pytest.raises(InitialStartPayloadInvalid):
        bound.assert_owner(bound.owner)


def test_entry_serializer_never_defaults_an_unknown_role_to_dh() -> None:
    """私有serializerも単独で閉roleを再確認しfallbackを持たない。"""
    from pitchlog.repositories.game_start import _entry_json

    entry = _bind().payload.away[-1]
    object.__setattr__(entry, "fielding_position", object())
    with pytest.raises(InitialStartPayloadInvalid):
        _entry_json(entry)


def _start_context(
    bound: BoundInitialStartPayload, outcome: str = "pending"
) -> dict[str, Any]:
    """純adapter試験用の明示合成DB応答。実DB証拠ではない。"""
    owner = bound.owner
    from pitchlog.db.game_state.rule_snapshot import (
        decode_applied_rules,
        encode_applied_rules,
    )

    saved_rules = encode_applied_rules(
        decode_applied_rules(
            dict(
                ruleSetId=str(UUID(int=8)),
                regulationInnings=9,
                coldConditions=[],
                extensionLimit=9,
                tiebreak=None,
                dh=len(bound.payload.away) == 10,
            )
        )
    )
    return dict(
        tenant_id=str(owner.tenant_id),
        game_id=str(owner.game_id),
        start_request_id=str(owner.start_request_id),
        device_id=str(owner.device_id),
        attempt_id=str(owner.attempt_id),
        request_digest=owner.request_digest.hex(),
        outcome=outcome,
        away_team_id=str(UUID(int=6)),
        home_team_id=str(UUID(int=7)),
        self_team_id=str(UUID(int=6)),
        applied_rules=saved_rules,
        away=[
            dict(e, uniform_number_snapshot="10")
            for e in cast(list[dict[str, Any]], bound._source()["away"])
        ],
        home=[
            dict(e, uniform_number_snapshot=None)
            for e in cast(list[dict[str, Any]], bound._source()["home"])
        ],
        started_at=None if outcome == "pending" else "2026-10-26T00:00:00+00:00",
        away_lineup_id=None if outcome == "pending" else str(UUID(int=9)),
        home_lineup_id=None if outcome == "pending" else str(UUID(int=10)),
    )


def test_start_tokens_bind_all_bytes_and_resolved_attempt() -> None:
    """解決後attemptだけを束縛し、canonical/digestは旧値のまま保つ。"""
    from pitchlog.repositories.game_start import _start_token

    bound = _bind()
    resolved = replace(bound.owner, attempt_id=UUID(int=99))
    new = BoundInitialStartPayload(bound.payload, resolved, bound.credential_digest)
    assert new.canonical_bytes == bound.canonical_bytes
    for save in (False, True):
        token = _start_token(new, save=save)
        assert token.attempt_id == resolved.attempt_id
        assert token.request_digest == bound.owner.request_digest
        assert token.typed_payload_json.encode() == bound.canonical_bytes


@pytest.mark.parametrize(
    "mutation",
    [
        "extra",
        "missing",
        "owner",
        "attempt",
        "digest",
        "team",
        "order_bool",
        "position_bool",
        "entry_extra",
        "uniform",
        "pending_stamp",
        "unknown_outcome",
        "duplicate_key",
        "nonfinite",
    ],
)
def test_start_context_rejects_wire_and_owner_mutations(mutation: str) -> None:
    """DB contextでも同値coercion/余剰/owner差替えを拒否する。"""
    from pitchlog.recording_rights.initial_grant import InitialGrantConflict
    from pitchlog.repositories.game_start import _read_start_context
    from pitchlog.repositories.tokens import TenantOperationResult

    bound = _bind()
    ctx = _start_context(bound)
    if mutation == "extra":
        ctx["extra"] = 1
    elif mutation == "missing":
        del ctx["away"]
    elif mutation == "owner":
        ctx["game_id"] = str(UUID(int=99))
    elif mutation == "attempt":
        ctx["attempt_id"] = str(UUID(int=99))
    elif mutation == "digest":
        ctx["request_digest"] = "0" * 64
    elif mutation == "team":
        ctx["self_team_id"] = str(UUID(int=99))
    elif mutation == "order_bool":
        ctx["away"][-1]["batting_order"] = True
    elif mutation == "position_bool":
        ctx["away"][0]["fielding_position"]["position"] = True
    elif mutation == "entry_extra":
        ctx["home"][0]["extra"] = 1
    elif mutation == "uniform":
        ctx["home"][0]["uniform_number_snapshot"] = 10
    elif mutation == "pending_stamp":
        ctx["started_at"] = "2026-10-26T00:00:00Z"
    elif mutation == "unknown_outcome":
        ctx["outcome"] = "unknown"
    wire = json.dumps(ctx)
    if mutation == "duplicate_key":
        wire = wire[:-1] + ',"tenant_id":"duplicate"}'
    if mutation == "nonfinite":
        wire = wire[:-1] + ',"bad":NaN}'

    class Read:
        def run_function(self, token):
            return TenantOperationResult(((wire,),))

    with pytest.raises(InitialGrantConflict):
        _read_start_context(cast(Any, Read()), bound)


@pytest.mark.parametrize("size", [9, 10])
def test_start_hook_real_artifact_before_memory_and_save(
    size: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """実TSを通す配線検査。DB/認可/commit成功とは主張しない。"""
    from datetime import datetime, timezone

    from pitchlog.repositories import transaction
    from pitchlog.repositories.game_start import _initialize_start
    from pitchlog.repositories.initial_recording_right import _PersistInitialStartToken
    from pitchlog.repositories.tokens import TenantOperationResult

    bound = _bind(_body(size))
    ctx = _start_context(bound)
    seen = []

    class ReadSave:
        def run_function(self, token):
            if type(token) is _PersistInitialStartToken:
                seen.append("save")
                return TenantOperationResult(
                    (
                        (
                            datetime(2026, 10, 26, tzinfo=timezone.utc),
                            UUID(int=9),
                            UUID(int=10),
                        ),
                    )
                )
            seen.append("read")
            return TenantOperationResult(((json.dumps(ctx),),))

    class Scope:
        _transaction = ReadSave()

        def _check(self):
            pass

    scope = Scope()

    def memory(selected, actual_bound, team, lineup):
        assert selected is scope and actual_bound is bound
        assert str(team) == ctx["self_team_id"] and len(lineup) == size
        seen.append("memory")

    monkeypatch.setattr(transaction, "_save_initial_lineup_memory", memory)
    receipt = _initialize_start(cast(Any, scope), bound)
    assert seen == ["read", "memory", "save"]
    assert receipt.owner == bound.owner and receipt.away_lineup_id == UUID(int=9)


def test_start_hook_invalid_roster_never_saves(monkeypatch: pytest.MonkeyPatch) -> None:
    """実TSの拒否を固定trueで上書きせず、UM2/saveへ到達させない。"""
    from pitchlog.recording_rights.initial_grant import InitialGrantConflict
    from pitchlog.repositories import transaction
    from pitchlog.repositories.game_start import _initialize_start
    from pitchlog.repositories.tokens import TenantOperationResult

    body = _body()
    body["away"][1]["batting_order"] = 1
    bound = _bind(body)
    seen = []

    class Read:
        def run_function(self, token):
            seen.append("read")
            return TenantOperationResult(((json.dumps(_start_context(bound)),),))

    class Scope:
        _transaction = Read()

        def _check(self):
            pass

    def forbidden(*args):
        raise AssertionError("invalid roster reached memory")

    monkeypatch.setattr(transaction, "_save_initial_lineup_memory", forbidden)
    with pytest.raises(InitialGrantConflict):
        _initialize_start(cast(Any, Scope()), bound)
    assert seen == ["read"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("started_at", None),
        ("started_at", "2026-10-26T00:00:00"),
        ("away_lineup_id", None),
        ("home_lineup_id", str(UUID(int=9))),
    ],
)
def test_start_replay_requires_saved_receipt(field: str, value: Any) -> None:
    """旧grant-only/欠損開始原本を再交付成功へ昇格しない。"""
    from pitchlog.recording_rights.initial_grant import InitialGrantConflict
    from pitchlog.repositories.game_start import _read_start_context
    from pitchlog.repositories.tokens import TenantOperationResult

    bound = _bind()
    ctx = _start_context(bound, "committed")
    ctx[field] = value

    class Read:
        def run_function(self, token):
            return TenantOperationResult(((json.dumps(ctx),),))

    with pytest.raises(InitialGrantConflict):
        _read_start_context(cast(Any, Read()), bound)


@pytest.mark.parametrize(
    "regulation,limit,cold,tiebreak",
    [
        (9, 9, [], None),
        (9, None, [], None),
        (
            7,
            None,
            [{"pointDifference": 7, "startInning": 5}],
            {
                "startInning": 8,
                "runnerPlacement": "no_out_first_second",
                "leadoffRule": "continue_lineup",
            },
        ),
    ],
)
def test_saved_start_rules_reuse_canonical_codec_and_exact_wire(
    regulation: int,
    limit: int | None,
    cold: list[dict[str, int]],
    tiebreak: dict[str, Any] | None,
) -> None:
    """既codecの6-key保存値から5-key decimal wireだけへ写す。終了は評価しない。"""
    from pitchlog.db.game_state.rule_snapshot import (
        decode_applied_rules,
        encode_applied_rules,
    )
    from pitchlog.repositories.game_start import _saved_start_rule_wire

    raw = dict(
        ruleSetId=str(UUID(int=8)),
        regulationInnings=regulation,
        coldConditions=cold,
        extensionLimit=limit,
        tiebreak=tiebreak,
        dh=True,
    )
    canonical = encode_applied_rules(decode_applied_rules(raw))
    wire = _saved_start_rule_wire(canonical).model_dump(mode="json", by_alias=True)
    assert set(canonical) == {
        "ruleSetId",
        "regulationInnings",
        "coldConditions",
        "extensionLimit",
        "tiebreak",
        "dh",
    }
    assert wire == dict(
        regulationInnings=str(regulation),
        coldConditions=[{k: str(v) for k, v in tier.items()} for tier in cold],
        extensionLimit=None if limit is None else str(limit),
        tiebreak=None
        if tiebreak is None
        else {**tiebreak, "startInning": str(tiebreak["startInning"])},
        dh=True,
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "cold_alias",
        "extension_alias",
        "both_legacy",
        "legacy_extra",
        "missing_canonical",
        "correlation",
        "bool_number",
        "unknown_tiebreak",
    ],
)
def test_start_context_rejects_legacy_rule_aliases_and_invalid_saved_rules(
    mutation: str,
) -> None:
    """旧cold/overtimeを暗黙補完せず、既codecの非成功を開始成功にしない。"""
    from pitchlog.recording_rights.initial_grant import InitialGrantConflict
    from pitchlog.repositories.game_start import _read_start_context
    from pitchlog.repositories.tokens import TenantOperationResult

    bound = _bind()
    ctx = _start_context(bound)
    rules = ctx["applied_rules"]
    if mutation in ("cold_alias", "both_legacy"):
        rules["cold"] = rules.pop("coldConditions")
    if mutation in ("extension_alias", "both_legacy"):
        rules["overtime"] = rules.pop("extensionLimit")
    if mutation == "legacy_extra":
        rules["cold"] = []
    if mutation == "missing_canonical":
        del rules["coldConditions"]
    if mutation == "correlation":
        rules["extensionLimit"] = 7
    if mutation == "bool_number":
        rules["regulationInnings"] = True
    if mutation == "unknown_tiebreak":
        rules["tiebreak"] = {
            "startInning": 10,
            "runnerPlacement": "unknown",
            "leadoffRule": "unknown",
        }

    class Read:
        def run_function(self, token):
            return TenantOperationResult(((json.dumps(ctx),),))

    with pytest.raises(InitialGrantConflict):
        _read_start_context(cast(Any, Read()), bound)
