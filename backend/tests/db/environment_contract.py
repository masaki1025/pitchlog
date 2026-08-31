"""DB 環境期待値と実測値を突合する共通処理。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg

ASSET_PATH = Path(__file__).with_name("environment-expectations.json")
OBSERVATION_KEYS = (
    "server_version_num",
    "locale_provider",
    "collate",
    "ctype",
    "encoding",
)


def load_expectations() -> dict[str, Any]:
    """履歴に固定された期待値資産を読み込む。

    Returns:
        JSON オブジェクトとして読み込んだ期待値資産。
    """
    asset = json.loads(ASSET_PATH.read_text(encoding="utf-8"))
    if not isinstance(asset, dict):
        raise AssertionError("DB 環境期待値資産のルートはオブジェクトである必要がある")
    return asset


def observe_database_environment(
    connection: psycopg.Connection[Any],
) -> dict[str, object]:
    """接続先 DB の環境値を SQL で観測する。

    Args:
        connection: 観測対象への psycopg 接続。

    Returns:
        期待値資産のキーに対応する観測値。
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                current_setting('server_version_num')::integer,
                CASE datlocprovider
                    WHEN 'c' THEN 'libc'
                    WHEN 'i' THEN 'icu'
                    WHEN 'b' THEN 'builtin'
                    ELSE datlocprovider::text
                END,
                datcollate,
                datctype,
                pg_encoding_to_char(encoding)
            FROM pg_database
            WHERE datname = current_database()
            """
        )
        row = cursor.fetchone()
    if row is None:
        raise AssertionError("接続中データベースの環境行を取得できない")
    return dict(zip(OBSERVATION_KEYS, row, strict=True))


def environment_mismatches(
    asset: dict[str, Any], observations: dict[str, object]
) -> list[str]:
    """期待値と観測値の差分を列挙する。

    Args:
        asset: 検査対象の期待値資産。
        observations: SQL で得た観測値。

    Returns:
        キー・期待値・観測値を含む差分メッセージ。完全一致なら空配列。
    """
    database_environment = asset.get("database_environment")
    if not isinstance(database_environment, dict):
        return ["database_environment: 期待値オブジェクトがない"]

    mismatches: list[str] = []
    for key in OBSERVATION_KEYS:
        expectation = database_environment.get(key)
        if not isinstance(expectation, dict):
            mismatches.append(f"{key}: 期待値オブジェクトがない")
            continue
        if expectation.get("comparison") != "exact":
            mismatches.append(
                f"{key}.comparison: exact が必要: {expectation.get('comparison')!r}"
            )
        if key == "server_version_num" and expectation.get("observed_type") != (
            "integer"
        ):
            mismatches.append(
                "server_version_num.observed_type: integer が必要: "
                f"{expectation.get('observed_type')!r}"
            )
        expected = expectation.get("expected")
        observed = observations.get(key)
        if expected != observed:
            mismatches.append(f"{key}: expected={expected!r}, observed={observed!r}")
    return mismatches
