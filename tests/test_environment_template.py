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
        "PITCHLOG_TEST_ADMIN_DSN",
        "PITCHLOG_TEST_ROLE_DSN",
    }
)
_EXPECTED_DSN_KEYS = frozenset(
    {
        "PITCHLOG_DATABASE_URL",
        "PITCHLOG_MIGRATION_DATABASE_URL",
        "PITCHLOG_TEST_ADMIN_DSN",
        "PITCHLOG_TEST_ROLE_DSN",
    }
)
_DECLARED_KEY_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=", re.MULTILINE)
_ASSIGNMENT_PATTERN = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.MULTILINE
)


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


def _assignments(template_text: str) -> dict[str, str]:
    """テンプレートで代入されているキーと値を返す。"""
    return dict(_ASSIGNMENT_PATTERN.findall(template_text))


def _comment_block_before(template_text: str, key: str) -> str:
    """指定したキーの直前にある連続したコメントを返す。

    Args:
        template_text: 設定テンプレートの全文。
        key: コメントを取得する設定キー。

    Returns:
        コメント記号を除いたコメント本文。
    """
    lines = template_text.splitlines()
    declaration_index = lines.index(f"{key}=")
    comments: list[str] = []
    for line in reversed(lines[:declaration_index]):
        if not line.startswith("#"):
            break
        comments.append(line.removeprefix("#").strip())
    return "\n".join(reversed(comments))


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
            *(
                f"{key}="
                for key in sorted(
                    _REQUIRED_DATABASE_KEYS - {"PITCHLOG_DATABASE_URL"}
                )
            ),
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


def test_database_configuration_values_are_empty() -> None:
    """DB 設定の雛形に接続情報が含まれないことを確認する。"""
    assignments = _assignments(_ENVIRONMENT_TEMPLATE_PATH.read_text(encoding="utf-8"))

    assert {key: assignments[key] for key in _REQUIRED_DATABASE_KEYS} == {
        key: "" for key in _REQUIRED_DATABASE_KEYS
    }


def test_pitchlog_database_connection_keys_are_closed_set() -> None:
    """PITCHLOG の接続先を表す変数が契約外に増えていないことを確認する。"""
    template_text = _ENVIRONMENT_TEMPLATE_PATH.read_text(encoding="utf-8")
    connection_keys = {
        key
        for key in _DECLARED_KEY_PATTERN.findall(template_text)
        if key.startswith("PITCHLOG_")
        and (key.endswith("_URL") or key.endswith("_DSN"))
    }

    assert connection_keys == _EXPECTED_DSN_KEYS


def test_application_database_url_documents_role_and_failure_timing() -> None:
    """アプリ用 DSN の用途、形式、失敗時点が明記されていることを確認する。"""
    template_text = _ENVIRONMENT_TEMPLATE_PATH.read_text(encoding="utf-8")
    comments = _comment_block_before(template_text, "PITCHLOG_DATABASE_URL")

    assert "アプリ用ロール専用" in comments
    assert "postgresql+psycopg://..." in comments
    assert "最初の物理接続の確立時" in comments
    assert "起動" not in comments


def test_database_pooled_documents_physical_connection_failure() -> None:
    """pooler 設定の不足も最初の物理接続時に失敗すると明記する。"""
    template_text = _ENVIRONMENT_TEMPLATE_PATH.read_text(encoding="utf-8")
    comments = _comment_block_before(template_text, "PITCHLOG_DATABASE_POOLED")

    assert "最初の物理接続の確立時" in comments
    assert "起動" not in comments


@pytest.mark.parametrize(
    "key",
    ("PITCHLOG_TEST_ADMIN_DSN", "PITCHLOG_TEST_ROLE_DSN"),
)
def test_test_database_dsn_documents_libpq_format(key: str) -> None:
    """テスト用 DSN が psycopg 向け libpq 形式だと明記されていることを確認する。"""
    template_text = _ENVIRONMENT_TEMPLATE_PATH.read_text(encoding="utf-8")
    comments = _comment_block_before(template_text, key)

    assert "psycopg が直接読む" in comments
    assert "postgresql+psycopg://..." in comments
    assert "libpq URL 形式(postgresql://...)" in comments
