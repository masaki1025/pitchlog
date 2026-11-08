"""閲覧者の定期照会用、非ロックの確定版ヒントを読む。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, cast
from uuid import UUID

from pitchlog.db.game_state.models import Game
from pitchlog.repositories.started_snapshot import _rows
from pitchlog.repositories.viewer_read import ViewerEffectiveVersionReadToken
from pitchlog.sync.tokens import (
    RECORDING_GENERATION_READ_COLUMNS,
    GameReadToken,
    RecordingGenerationReadToken,
)


class ViewerProbeUnavailable(RuntimeError):
    """保存原本が不完全・競合中であることを表す。"""


class ViewerProbeNotVisible(RuntimeError):
    """対象試合がこのテナントから見えないことを表す。"""


@dataclass(frozen=True, slots=True)
class ViewerProbe:
    """表示値ではなく、再取得が必要かを知るための版ヒント。"""

    status: Literal["in_progress", "finished"]
    generation: int
    watermark: int
    effective_version: str
    has_p3_head: bool = False

    @property
    def version(self) -> str:
        """APIへ同期語彙を出さない不透明な版文字列。"""
        return self.effective_version


_HEX = re.compile(r"[a-f0-9]{64}\Z")


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """JSON内の重複keyを後勝ちで採用しない。"""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ViewerProbeUnavailable("閲覧版のkeyが重複しています")
        result[key] = value
    return result


def _exact(value: object, names: tuple[str, ...]) -> dict[str, object]:
    """Point recordの未知列・欠損列を拒否する。"""
    if type(value) is not dict or set(value) != set(names):
        raise ViewerProbeUnavailable("閲覧版の列集合が不正です")
    return cast(dict[str, object], value)


def _uuid(value: object) -> bool:
    """正規UUID表記だけを許す。"""
    if type(value) is not str:
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _positive(value: object) -> bool:
    return type(value) is int and 0 < value < 2**63


def _digest(value: object) -> bool:
    return type(value) is str and _HEX.fullmatch(value) is not None


def _point_record(handle, game_id: UUID, generation: int) -> dict[str, object]:
    """有限固定関数からpoint集合1行だけを読む。"""
    rows = handle.run_function(
        ViewerEffectiveVersionReadToken(game_id, generation)
    ).rows
    if len(rows) != 1 or len(rows[0]) != 1 or type(rows[0][0]) is not str:
        raise ViewerProbeUnavailable("閲覧版のpoint行が不正です")
    try:
        value = json.loads(rows[0][0], object_pairs_hook=_unique_pairs)
    except (TypeError, ValueError) as error:
        raise ViewerProbeUnavailable("閲覧版のpoint JSONが不正です") from error
    return _exact(value, ("checkpoint", "p3", "lifecycle"))


def _validated_point(
    point: dict[str, object], status: str, watermark: int
) -> dict[str, object]:
    """物理pointerと状態の対応を検査し、版の固定入力を作る。"""
    checkpoint = point["checkpoint"]
    p3 = point["p3"]
    lifecycle = point["lifecycle"]
    if checkpoint is None:
        if watermark != 0 or p3 is not None:
            raise ViewerProbeUnavailable("現checkpointがありません")
    else:
        cp = _exact(
            checkpoint,
            (
                "id",
                "revision",
                "history_version",
                "confirmed_watermark",
                "applied_watermark",
                "content_digest",
                "state",
            ),
        )
        if not (
            _uuid(cp["id"])
            and _positive(cp["revision"])
            and _positive(cp["history_version"])
            and type(cp["confirmed_watermark"]) is int
            and cp["confirmed_watermark"] == watermark
            and type(cp["applied_watermark"]) is int
            and cp["applied_watermark"] == watermark
            and _digest(cp["content_digest"])
            and cp["state"] == "current"
        ):
            raise ViewerProbeUnavailable("現checkpointが不整合です")
    if p3 is not None:
        head = _exact(
            p3,
            ("capsule_id", "revision", "source_set_digest", "stats_version_id"),
        )
        if not (
            checkpoint is not None
            and _uuid(head["capsule_id"])
            and _positive(head["revision"])
            and _digest(head["source_set_digest"])
            and _uuid(head["stats_version_id"])
        ):
            raise ViewerProbeUnavailable("過去訂正headが不整合です")
    if lifecycle is None:
        if status == "finished":
            raise ViewerProbeUnavailable("終了版headがありません")
    else:
        lc = _exact(
            lifecycle,
            (
                "last_version",
                "is_finished",
                "active_receipt_id",
                "active_stats_version_id",
                "last_control_event_id",
            ),
        )
        finished = status == "finished"
        if not (
            _positive(lc["last_version"])
            and type(lc["is_finished"]) is bool
            and lc["is_finished"] is finished
            and _uuid(lc["last_control_event_id"])
            and (
                (
                    _uuid(lc["active_receipt_id"])
                    and _uuid(lc["active_stats_version_id"])
                )
                if finished
                else lc["active_receipt_id"] is None
                and lc["active_stats_version_id"] is None
            )
        ):
            raise ViewerProbeUnavailable("終了版headが不整合です")
    return point


def _version(
    tenant: UUID,
    game_id: UUID,
    status: str,
    generation: int,
    watermark: int,
    point: dict[str, object],
) -> str:
    """固定型のpoint列から不透明な実効版を導出する。"""
    packed = json.dumps(
        [
            "viewer-effective-v1",
            str(tenant),
            str(game_id),
            status,
            generation,
            watermark,
            point,
        ],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return "ve1_" + sha256(packed).hexdigest()


def _read_one(handle, token, columns: tuple[str, ...]) -> dict | None:
    """登録tokenの0/1行だけを採用する。"""
    rows = _rows(handle.run(token), columns)
    if len(rows) > 1:
        raise ViewerProbeUnavailable("閲覧版の行が重複しています")
    return rows[0] if rows else None


def _visible(game: dict | None, tenant: UUID, game_id: UUID) -> bool:
    """削除・非表示・移行中を公開版として扱わない。"""
    return (
        game is not None
        and game["tenant_id"] == tenant
        and game["id"] == game_id
        and game["status"] in {"in_progress", "finished"}
        and game["started_at"] is not None
        and all(
            game[key] is None for key in ("trashed_at", "hidden_at", "import_batch_id")
        )
    )


def _current(generation: dict | None, tenant: UUID, game_id: UUID) -> bool:
    """現在normal世代の確定水位だけを版に使う。"""
    return (
        generation is not None
        and generation["tenant_id"] == tenant
        and generation["game_id"] == game_id
        and generation["kind"] == "normal"
        and type(generation["generation"]) is int
        and 0 < generation["generation"] < 2**63
        and type(generation["confirmed_watermark"]) is int
        and 0 <= generation["confirmed_watermark"] < 2**63
        and type(generation["applied_prefix"]) is int
        and generation["applied_prefix"] == generation["confirmed_watermark"]
        and all(
            generation[key] is None
            for key in ("revoked_at", "retired_at", "import_batch_id")
        )
    )


def read_viewer_probe(handle, game_id: UUID) -> ViewerProbe:
    """非ロックの点読取を二度照合し、混在版を503へ閉じる。

    この値は履歴・スコアの表示原本でも記録資格でもない。版が変わったら
    RR READ ONLY のviewer本体で保存値を確認する。
    """
    if type(game_id) is not UUID or type(handle._bound_tenant_id) is not UUID:
        raise ViewerProbeUnavailable("閲覧対象が不正です")
    tenant = handle._bound_tenant_id
    game_columns = tuple(Game.__table__.c.keys())
    generation_columns = tuple(RECORDING_GENERATION_READ_COLUMNS)

    def sample() -> tuple[dict, dict, dict[str, object]]:
        game = _read_one(handle, GameReadToken(game_id), game_columns)
        if game is None or not _visible(game, tenant, game_id):
            raise ViewerProbeNotVisible("閲覧対象が見えません")
        generation = _read_one(
            handle, RecordingGenerationReadToken(game_id), generation_columns
        )
        if not _current(generation, tenant, game_id):
            raise ViewerProbeUnavailable("確定世代を確認できません")
        assert game is not None and generation is not None
        point = _validated_point(
            _point_record(handle, game_id, generation["generation"]),
            game["status"],
            generation["confirmed_watermark"],
        )
        return game, generation, point

    first_game, first_generation, first_point = sample()
    second_game, second_generation, second_point = sample()
    if (first_game, first_generation, first_point) != (
        second_game,
        second_generation,
        second_point,
    ):
        raise ViewerProbeUnavailable("閲覧版が読取中に変わりました")
    return ViewerProbe(
        cast(Literal["in_progress", "finished"], first_game["status"]),
        first_generation["generation"],
        first_generation["confirmed_watermark"],
        _version(
            tenant,
            game_id,
            first_game["status"],
            first_generation["generation"],
            first_generation["confirmed_watermark"],
            first_point,
        ),
        first_point["p3"] is not None,
    )
