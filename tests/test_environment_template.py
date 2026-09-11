"""設定正本テンプレートのデータベース設定キーを検査する。"""

import re
from collections.abc import Set as AbstractSet
from pathlib import Path

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_ENVIRONMENT_TEMPLATE_PATH = _REPOSITORY_ROOT / ".env.example"
_REQUIRED_DATABASE_KEYS = frozenset(
    {
        "PITCHLOG_DATABASE_URL",
        "PITCHLOG_DATABASE_POOLED",
        "PITCHLOG_MIGRATION_DATABASE_URL",
    }
)
_DECLARED_KEY_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=", re.MULTILINE)


def _missing_environment_keys(
    template_text: str, expected_keys: AbstractSet[str]
) -> list[str]:
    """設定テンプレートで宣言されていないキー名だけを返す。

    Args:
        template_text: 検査対象の設定テンプレート全文。
        expected_keys: 宣言を必須とするキー名集合。

    Returns:
        辞書順に並べた不足キー名。テンプレート本文は含めない。
    """
    declared_keys = set(_DECLARED_KEY_PATTERN.findall(template_text))
    return sorted(key for key in expected_keys if key not in declared_keys)


def test_environment_template_declares_required_database_keys() -> None:
    template_text = _ENVIRONMENT_TEMPLATE_PATH.read_text(encoding="utf-8")

    missing_keys = _missing_environment_keys(template_text, _REQUIRED_DATABASE_KEYS)

    assert missing_keys == []


@pytest.mark.parametrize("missing_key", sorted(_REQUIRED_DATABASE_KEYS))
def test_each_missing_database_key_is_reported(missing_key: str) -> None:
    template_text = "\n".join(
        f"{key}=" for key in sorted(_REQUIRED_DATABASE_KEYS - {missing_key})
    )

    assert _missing_environment_keys(template_text, _REQUIRED_DATABASE_KEYS) == [
        missing_key
    ]


def test_key_name_in_comment_or_value_is_not_a_declaration() -> None:
    template_text = "\n".join(
        [
            "PITCHLOG_DATABASE_POOLED=",
            "PITCHLOG_MIGRATION_DATABASE_URL=",
            "# PITCHLOG_DATABASE_URL is required",
            "UNRELATED=PITCHLOG_DATABASE_URL",
        ]
    )

    assert _missing_environment_keys(template_text, _REQUIRED_DATABASE_KEYS) == [
        "PITCHLOG_DATABASE_URL"
    ]


@pytest.mark.parametrize("unprefixed_declaration", ["", "DATABASE_URL="])
def test_unprefixed_database_url_does_not_affect_required_keys(
    unprefixed_declaration: str,
) -> None:
    template_text = "\n".join(
        [
            *(f"{key}=" for key in sorted(_REQUIRED_DATABASE_KEYS)),
            unprefixed_declaration,
        ]
    )

    assert _missing_environment_keys(template_text, _REQUIRED_DATABASE_KEYS) == []

