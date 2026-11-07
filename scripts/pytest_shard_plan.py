"""pytest シャードの決定的な割当を計算する。

実行時間ログから得たテスト単位の重みを使い、重いテストから順に最も空いている
シャードへ置く LPT（longest processing time）で、件数ではなく推定実行時間を均す。
重みに無い新しいテストも既定重みで必ず割り当てるため、全件被覆検査は従来どおり
欠落・重複を拒否できる。

正規化後の識別子が一意なら割当は入力順に依存しない。UUID 正規化が衝突する
場合は同じ収集順を前提とし、その順をタイブレーカーに使う。
乱数 UUID を含む node id は UUID を ``<uuid>`` に伏せて重みを引く。
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
DEFAULT_WEIGHT_SECONDS = 1.0


class InvalidShardWeight(ValueError):
    """重み定義が数値・正値の契約に反する。"""


def normalize_identifier(node_id: str) -> str:
    """乱数 UUID を伏せた比較・重み照合用の識別子を返す。

    Args:
        node_id: pytest の node id。

    Returns:
        UUID を ``<uuid>`` に置換した文字列。
    """
    return UUID_RE.sub("<uuid>", node_id)


def validated_weights(raw: object) -> dict[str, float]:
    """設定の重みを検証し、正規化した識別子の対応へ変換する。

    Args:
        raw: ``ci/pytest-shards.json`` の ``weights`` 値。

    Returns:
        正規化した node id から秒単位の重みへの対応。``None`` は空。

    Raises:
        InvalidShardWeight: マッピングでない、キーが空、値が有限の正数でない場合。
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise InvalidShardWeight("重み定義は JSON オブジェクトが必要")
    result: dict[str, float] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key:
            raise InvalidShardWeight("重みのキーは空でない文字列が必要")
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise InvalidShardWeight(f"重みが数値ではない: {key}")
        weight = float(value)
        if not math.isfinite(weight) or weight <= 0:
            raise InvalidShardWeight(f"重みは有限の正数が必要: {key}")
        normalized = normalize_identifier(key)
        # UUID だけが異なる複数の記録が同じキーへ潰れた場合は、大きい方を残す。
        result[normalized] = max(result.get(normalized, 0.0), weight)
    return result


def validated_default_weight(raw: object) -> float:
    """既定重みを検証する。

    Args:
        raw: ``default_weight_seconds`` の値。``None`` は既定値。

    Returns:
        有限の正数。

    Raises:
        InvalidShardWeight: 数値でない、または有限の正数でない場合。
    """
    if raw is None:
        return DEFAULT_WEIGHT_SECONDS
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise InvalidShardWeight("default_weight_seconds は数値が必要")
    weight = float(raw)
    if not math.isfinite(weight) or weight <= 0:
        raise InvalidShardWeight("default_weight_seconds は有限の正数が必要")
    return weight


def assign_shards(
    node_ids: Sequence[str],
    *,
    count: int,
    weights: Mapping[str, float] | None = None,
    default_weight: float = DEFAULT_WEIGHT_SECONDS,
) -> list[int]:
    """各テストのシャード番号を返す。

    重いテストから順に、その時点で推定負荷が最小のシャードへ割り当てる。
    同重量の場合は正規化 node id、収集順の順で決定的に並べる。返り値は入力と
    同じ順序で、各要素は ``0 <= shard < count`` を満たす。

    Args:
        node_ids: 全件の pytest node id。
        count: シャード数。
        weights: 正規化 node id から秒単位の重みへの対応。
        default_weight: 重みに無いテストの既定重み。

    Returns:
        入力と同じ長さのシャード番号列。

    Raises:
        ValueError: シャード数が 1 未満、または既定重みが有限の正数でない場合。
    """
    if count < 1:
        raise ValueError("count は 1 以上が必要")
    if not math.isfinite(default_weight) or default_weight <= 0:
        raise ValueError("default_weight は有限の正数が必要")
    safe_weights = weights or {}
    normalized = [normalize_identifier(node_id) for node_id in node_ids]

    def weight_at(index: int) -> float:
        return safe_weights.get(normalized[index], default_weight)

    order = sorted(
        range(len(node_ids)),
        key=lambda index: (-weight_at(index), normalized[index], index),
    )
    loads = [0.0] * count
    assignments = [0] * len(node_ids)
    for index in order:
        shard = min(range(count), key=lambda candidate: (loads[candidate], candidate))
        assignments[index] = shard
        loads[shard] += weight_at(index)
    return assignments


def estimated_loads(
    node_ids: Sequence[str],
    assignments: Sequence[int],
    *,
    count: int,
    weights: Mapping[str, float] | None = None,
    default_weight: float = DEFAULT_WEIGHT_SECONDS,
) -> list[float]:
    """割当後のシャード別推定負荷を返す。

    Args:
        node_ids: 全件の pytest node id。
        assignments: ``assign_shards`` が返したシャード番号列。
        count: シャード数。
        weights: 正規化 node id から秒単位の重みへの対応。
        default_weight: 重みに無いテストの既定重み。

    Returns:
        シャード番号順の推定負荷（秒）。

    Raises:
        ValueError: 入力長が一致しない、またはシャード番号が範囲外の場合。
    """
    if len(node_ids) != len(assignments):
        raise ValueError("node_ids と assignments の長さが一致しない")
    safe_weights = weights or {}
    loads = [0.0] * count
    for node_id, shard in zip(node_ids, assignments, strict=True):
        if not 0 <= shard < count:
            raise ValueError(f"シャード番号が範囲外: {shard}")
        loads[shard] += safe_weights.get(
            normalize_identifier(node_id),
            default_weight,
        )
    return loads
