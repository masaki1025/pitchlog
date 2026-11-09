"""通常とP3の全監査coverage。fixtureは値境界で実DB成功ではない。"""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from uuid import UUID

import pytest
from test_play_export_p3_read import _page

from pitchlog.exports.p3_coverage import resolve_p3_snapshots
from pitchlog.exports.play_export_csv import (
    _plays_rows,
    _projection_rows,
    missing_supply_columns,
    snapshot_id_for,
)
from pitchlog.exports.play_rows import CSV_HEADERS, PlayExportSupplyError
from pitchlog.repositories.play_export import PlayExportBundle
from pitchlog.repositories.play_export_source_codec import SourceIdentity


def _physical(value, hidden_at=None):
    """保存JSONのUUID表現だけを元DB型へ戻す試験データ補助。"""
    value = deepcopy(value)
    for field in (
        "id",
        "tenant_id",
        "game_id",
        "source_event_id",
        "batter_id",
        "pitcher_id",
        "catcher_id",
        "resolved_fielder_id",
    ):
        if value.get(field) is not None:
            value[field] = UUID(value[field])
    value["hidden_at"] = hidden_at
    return value


def _bundle():
    row, version = _page()
    row["capsule_watermark"] = 1
    item = row["item_json"]
    now = datetime(2026, 11, 9, tzinfo=timezone.utc)
    old = _physical(item["original_play_row"], now)
    current = _physical(item["play_row"])
    common = {
        "tenant_id": row["tenant_id"],
        "game_id": row["game_id"],
        "generation": 1,
        "is_tombstone": False,
        "ledger_kind": "accepted",
    }
    source = SourceIdentity(
        1,
        1,
        item["d2"],
        row["effective_event_id"],
        row["effective_play_row_id"],
        2,
        1,
        UUID(item["original_event_id"]),
        "a" * 64,
    )
    bundle = PlayExportBundle(
        game={"id": row["game_id"], "tenant_id": row["tenant_id"]},
        plays=(current,),
        audit_plays=(old, current),
        events=(
            {
                **common,
                "id": old["source_event_id"],
                "d2": item["d2"],
                "event_kind": "play_input",
                "replaced_at": now,
            },
            {
                **common,
                "id": row["effective_event_id"],
                "d2": None,
                "event_kind": "play_change",
            },
        ),
        snapshots=(
            {
                "tenant_id": row["tenant_id"],
                "game_id": row["game_id"],
                "play_row_id": old["id"],
                "source_event_id": old["source_event_id"],
                "play_version": 1,
                "recording_generation": 1,
                "event_sequence": item["d2"],
                "plays_csv_json": dict.fromkeys(CSV_HEADERS["plays.csv"], "旧記録値"),
                "full_innings_json": [],
            },
        ),
        runners=(),
        lineups=(),
        participations=(),
        players=(),
        teams=(),
        tenant_vocabularies=(),
        admin_vocabularies=(),
        runner_snapshots=(),
        snapshot_available=True,
        source_version=replace(version, source_count=1),
        source_identities=(asdict(source),),
        p3_snapshots=(row,),
    )
    return replace(bundle, effective_snapshots=resolve_p3_snapshots(bundle))


def test_current_uses_effective_overlay_and_keeps_old_snapshot_in_sidecar():
    """P3 targetの新physicalに旧88列を流用せず、両監査値を保持する。"""
    bundle = _bundle()
    assert missing_supply_columns(bundle) == ()
    assert resolve_p3_snapshots(bundle) == bundle.effective_snapshots
    values = list(_plays_rows(bundle, "snapshot"))
    assert len(values) == 1
    assert values[0].values == bundle.p3_snapshots[0]["plays_csv_json"]
    projections = list(_projection_rows(bundle, "snapshot"))
    assert len(projections) == 2
    assert {row.values["projection_kind"] for row in projections} == {
        "plays_csv_v1",
        "plays_csv_p3_v1",
    }
    assert (
        bundle.snapshots[0]["plays_csv_json"][CSV_HEADERS["plays.csv"][45]]
        == "旧記録値"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "no-p3",
        "no-effective",
        "no-normal",
        "missing-audit",
        "extra-audit",
        "duplicate-cap",
        "tail-missing",
        "old-head",
        "wrong-source",
        "wrong-current-json",
        "wrong-snapshot-tenant",
    ],
)
def test_any_missing_extra_or_unbound_source_stays_unavailable(mutation):
    """先頭guardを外すだけでは200にならず全物理/原本1:1を必要とする。"""
    bundle = _bundle()
    if mutation == "no-p3":
        bundle = replace(bundle, p3_snapshots=None)
    elif mutation == "no-effective":
        bundle = replace(bundle, effective_snapshots=None)
    elif mutation == "no-normal":
        bundle = replace(bundle, snapshots=())
    elif mutation == "missing-audit":
        bundle = replace(bundle, audit_plays=bundle.audit_plays[:1])
    elif mutation == "extra-audit":
        bundle = replace(
            bundle,
            audit_plays=(
                *bundle.audit_plays,
                {**bundle.audit_plays[0], "id": UUID(int=9999)},
            ),
        )
    elif mutation == "duplicate-cap":
        bundle = replace(
            bundle, p3_snapshots=(*bundle.p3_snapshots, *bundle.p3_snapshots)
        )
    elif mutation == "tail-missing":
        bundle = replace(
            bundle, p3_snapshots=({**bundle.p3_snapshots[0], "capsule_watermark": 2},)
        )
    elif mutation == "old-head":
        bundle = replace(
            bundle, p3_snapshots=({**bundle.p3_snapshots[0], "current_head": False},)
        )
    elif mutation == "wrong-source":
        bundle = replace(
            bundle,
            source_identities=(
                {**bundle.source_identities[0], "source_event_id": UUID(int=99999)},
            ),
        )
    elif mutation == "wrong-current-json":
        row = deepcopy(bundle.effective_snapshots[0])
        row["plays_csv_json"][CSV_HEADERS["plays.csv"][0]] = "偽の値"
        bundle = replace(bundle, effective_snapshots=(row,))
    else:
        row = {**bundle.snapshots[0], "tenant_id": UUID(int=900)}
        bundle = replace(bundle, snapshots=(row,))
    assert missing_supply_columns(bundle) == tuple(range(88))


def test_capsule_reference_changes_export_digest_without_changing_current_math():
    """同じcurrent表示でも原本参照の変化をmanifestから隠さない。"""
    bundle = _bundle()
    row = deepcopy(bundle.p3_snapshots[0])
    row["reference_json"]["priorNativeVersionId"] = str(UUID(int=999))
    changed = replace(bundle, p3_snapshots=(row,))
    assert snapshot_id_for(changed) != snapshot_id_for(bundle)


def test_missing_all_overlay_is_not_empty_success():
    """P3 eventがある試合で空overlayを完成0行としない。"""
    with pytest.raises(PlayExportSupplyError):
        resolve_p3_snapshots(replace(_bundle(), p3_snapshots=()))


def test_two_capsules_with_identical_follower_values_select_only_real_current_head():
    """同値followersが歴代capsuleに存在しても内容の最新推測で選ばない。"""
    from pitchlog.exports.p3_projection import p3_input_origin
    from pitchlog.exports.p3_snapshot import P3SnapshotIdentity
    from pitchlog.sync.idempotency import source_fingerprint

    first = _bundle()
    target1 = deepcopy(first.p3_snapshots[0])
    target1["capsule_watermark"] = 2
    target1["current_head"] = False
    follower = deepcopy(target1)
    follower_id, follower_event = UUID(int=30002), UUID(int=30001)
    follower["d1"] = 2
    follower["original_play_row_id"] = follower_id
    follower["effective_play_row_id"] = follower_id
    follower["effective_event_id"] = follower_event
    follower["reference_json"]["replacementResult"] = None
    item = follower["item_json"]
    item.update(
        d1=2,
        d2=2000,
        original_event_id=str(follower_event),
        effective_event_id=str(follower_event),
        original_play_row_id=str(follower_id),
        effective_play_row_id=str(follower_id),
    )
    physical = {
        **item["play_row"],
        "id": str(follower_id),
        "source_event_id": str(follower_event),
        "play_number": 2,
    }
    item["original_play_row"] = deepcopy(physical)
    item["play_row"] = deepcopy(physical)
    item["original_payload"] = deepcopy(item["payload"])
    item["item_digest"] = source_fingerprint(
        {
            k: v
            for k, v in item.items()
            if k
            not in {
                "tenant_id",
                "game_id",
                "internal_generation",
                "capsule_id",
                "item_digest",
            }
        }
    )
    follower["item_digest"] = item["item_digest"]
    identity = P3SnapshotIdentity(
        **{name: follower[name] for name in P3SnapshotIdentity.__dataclass_fields__}
    )
    follower["plays_csv_json"][CSV_HEADERS["plays.csv"][72]] = p3_input_origin(
        follower["plays_csv_json"][CSV_HEADERS["plays.csv"][72]],
        item["payload"],
        identity,
        target=False,
    )
    target2 = deepcopy(target1)
    capsule2, target2_id, target2_event = UUID(int=9000), UUID(int=9001), UUID(int=9002)
    target2.update(
        capsule_id=capsule2,
        capsule_stats_version_id=UUID(int=9003),
        original_play_row_id=target1["effective_play_row_id"],
        effective_play_row_id=target2_id,
        effective_event_id=target2_event,
        current_head=True,
    )
    item2 = target2["item_json"]
    item2.update(
        capsule_id=str(capsule2),
        original_event_id=str(target1["effective_event_id"]),
        original_play_row_id=str(target1["effective_play_row_id"]),
        effective_event_id=str(target2_event),
        effective_play_row_id=str(target2_id),
    )
    item2["original_play_row"] = deepcopy(item2["play_row"])
    item2["original_payload"] = deepcopy(item2["payload"])
    item2["play_row"].update(id=str(target2_id), source_event_id=str(target2_event))
    item2["item_digest"] = source_fingerprint(
        {
            k: v
            for k, v in item2.items()
            if k
            not in {
                "tenant_id",
                "game_id",
                "internal_generation",
                "capsule_id",
                "item_digest",
            }
        }
    )
    target2["item_digest"] = item2["item_digest"]
    target2["reference_json"]["priorCapsuleId"] = str(target1["capsule_id"])
    target2["reference_json"]["replacementResult"].update(
        capsuleId=str(capsule2), effectiveEventId=str(target2_event)
    )
    follower2 = deepcopy(follower)
    follower2.update(
        capsule_id=capsule2, capsule_stats_version_id=UUID(int=9003), current_head=True
    )
    follower2["item_json"]["capsule_id"] = str(capsule2)
    follower2["reference_json"]["priorCapsuleId"] = str(target1["capsule_id"])
    for snapshot in (target2, follower2):
        identity = P3SnapshotIdentity(
            **{name: snapshot[name] for name in P3SnapshotIdentity.__dataclass_fields__}
        )
        column = CSV_HEADERS["plays.csv"][72]
        snapshot["plays_csv_json"][column] = p3_input_origin(
            snapshot["plays_csv_json"][column],
            snapshot["item_json"]["payload"],
            identity,
            target=snapshot["d1"] == snapshot["capsule_target_d1"],
        )
    # 同じfollower実値/物理/観測/hashを二つの歴代capsuleが持つ正規配置。
    assert follower2["item_json"]["item_digest"] == follower["item_json"]["item_digest"]
    assert {
        k: v
        for k, v in follower2["plays_csv_json"].items()
        if k != CSV_HEADERS["plays.csv"][72]
    } == {
        k: v
        for k, v in follower["plays_csv_json"].items()
        if k != CSV_HEADERS["plays.csv"][72]
    }
    assert (
        follower2["plays_csv_json"][CSV_HEADERS["plays.csv"][72]]
        != follower["plays_csv_json"][CSV_HEADERS["plays.csv"][72]]
    )
    current_follower = _physical(item["play_row"])
    now = datetime(2026, 11, 9, tzinfo=timezone.utc)
    target1_physical = {**first.plays[0], "hidden_at": now}
    current_target = _physical(item2["play_row"])
    common = {
        "tenant_id": first.game["tenant_id"],
        "game_id": first.game["id"],
        "generation": 1,
        "is_tombstone": False,
        "ledger_kind": "accepted",
    }
    follower_normal = {
        **first.snapshots[0],
        "play_row_id": follower_id,
        "source_event_id": follower_event,
        "event_sequence": 2000,
    }
    identities = (
        {
            **first.source_identities[0],
            "source_event_id": target2_event,
            "play_row_id": target2_id,
        },
        {
            **first.source_identities[0],
            "source_event_id": follower_event,
            "play_row_id": follower_id,
            "base_event_id": follower_event,
            "d1": 2,
            "d2": 2000,
            "slot_version": 1,
        },
    )
    bundle = replace(
        first,
        plays=(current_target, current_follower),
        audit_plays=(
            first.audit_plays[0],
            target1_physical,
            current_target,
            current_follower,
        ),
        events=(
            *first.events,
            {**common, "id": target2_event, "event_kind": "play_change", "d2": None},
            {**common, "id": follower_event, "event_kind": "play_input", "d2": 2000},
        ),
        snapshots=(*first.snapshots, follower_normal),
        source_version=replace(first.source_version, source_count=2),
        source_identities=identities,
        p3_snapshots=(target1, follower, target2, follower2),
        effective_snapshots=None,
    )
    current = resolve_p3_snapshots(bundle)
    assert [row["play_row_id"] for row in current] == [target2_id, follower_id]
    assert current[1]["plays_csv_json"] == follower2["plays_csv_json"]
    assert missing_supply_columns(replace(bundle, effective_snapshots=current)) == ()
    # 旧capsuleをcurrentと詐称した対向は重複current physicalか現source不一致になる。
    wrong = replace(
        bundle,
        p3_snapshots=(
            {**target1, "current_head": True},
            {**follower, "current_head": True},
            target2,
            follower2,
        ),
    )
    with pytest.raises(PlayExportSupplyError):
        resolve_p3_snapshots(wrong)


def test_two_eligible_generations_keep_both_current_capsules():
    """同gameの二世代Sが有効なら、世代毎のheadを両方残す。"""
    import json

    from pitchlog.exports.p3_projection import p3_input_origin
    from pitchlog.exports.p3_snapshot import P3SnapshotIdentity
    from pitchlog.sync.idempotency import source_fingerprint

    first = _bundle()
    tenant, game = first.game["tenant_id"], first.game["id"]

    def remap(value):
        if type(value) is UUID:
            return value if value in (tenant, game) else UUID(int=value.int + 10000)
        if type(value) is str:
            try:
                identifier = UUID(value)
            except ValueError:
                try:
                    obj = json.loads(value)
                except (ValueError, TypeError):
                    return value
                if type(obj) in (dict, list):
                    return json.dumps(
                        remap(obj),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                return value
            return str(remap(identifier))
        if type(value) is dict:
            return {
                key: 2
                if key in ("generation", "internal_generation", "recording_generation")
                else remap(child)
                for key, child in value.items()
            }
        if type(value) in (list, tuple):
            return type(value)(remap(v) for v in value)
        return value

    row = remap(first.p3_snapshots[0])
    item = row["item_json"]
    row["item_digest"] = item["item_digest"] = source_fingerprint(
        {
            k: v
            for k, v in item.items()
            if k
            not in {
                "tenant_id",
                "game_id",
                "internal_generation",
                "capsule_id",
                "item_digest",
            }
        }
    )
    identity = P3SnapshotIdentity(
        **{name: row[name] for name in P3SnapshotIdentity.__dataclass_fields__}
    )
    origin = CSV_HEADERS["plays.csv"][72]
    row["plays_csv_json"][origin] = p3_input_origin(
        row["plays_csv_json"][origin], item["payload"], identity, target=True
    )
    second_normal = remap(first.snapshots)
    second_plays = remap(first.plays)
    bundle = replace(
        first,
        plays=(*first.plays, *second_plays),
        audit_plays=(*first.audit_plays, *remap(first.audit_plays)),
        events=(*first.events, *remap(first.events)),
        snapshots=(*first.snapshots, *second_normal),
        source_version=replace(first.source_version, source_count=2),
        source_identities=(*first.source_identities, *remap(first.source_identities)),
        p3_snapshots=(*first.p3_snapshots, row),
        effective_snapshots=None,
    )
    result = resolve_p3_snapshots(bundle)
    assert [r["recording_generation"] for r in result] == [1, 2]
    assert [r["play_row_id"] for r in result] == [
        first.plays[0]["id"],
        second_plays[0]["id"],
    ]
    # 世代だけを偽装して元世代headへ混ぜると、item/source全値比較で拒否する。
    with pytest.raises(PlayExportSupplyError):
        resolve_p3_snapshots(
            replace(
                bundle,
                p3_snapshots=(first.p3_snapshots[0], {**row, "internal_generation": 1}),
            )
        )


def test_disk_spool_coverage_uses_disk_rows_api():
    """実ZIP経路のDiskRowsでappend不在のcoverageを再発させない。"""
    from pitchlog.repositories.play_export_spool import ExportRowStore

    with ExportRowStore() as store, store.capture():
        bundle = _bundle()
        assert missing_supply_columns(bundle) == ()
        assert type(bundle.effective_snapshots).__name__ == "DiskRows"
