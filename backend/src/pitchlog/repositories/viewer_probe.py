"""閲覧者の定期照会用、非ロックの確定版ヒントを読む。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast
from uuid import UUID

from pitchlog.db.game_state.models import Game
from pitchlog.repositories.started_snapshot import _rows
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

    @property
    def version(self) -> str:
        """APIへ同期語彙を出さない不透明な版文字列。"""
        return str(self.generation)


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

    def sample() -> tuple[dict | None, dict | None]:
        game = _read_one(handle, GameReadToken(game_id), game_columns)
        if game is None or not _visible(game, tenant, game_id):
            raise ViewerProbeNotVisible("閲覧対象が見えません")
        generation = _read_one(
            handle, RecordingGenerationReadToken(game_id), generation_columns
        )
        if not _current(generation, tenant, game_id):
            raise ViewerProbeUnavailable("確定世代を確認できません")
        return game, generation

    first_game, first_generation = sample()
    second_game, second_generation = sample()
    if first_game != second_game or first_generation != second_generation:
        raise ViewerProbeUnavailable("閲覧版が読取中に変わりました")
    assert first_game is not None and first_generation is not None
    return ViewerProbe(
        cast(Literal["in_progress", "finished"], first_game["status"]),
        first_generation["generation"],
        first_generation["confirmed_watermark"],
    )
