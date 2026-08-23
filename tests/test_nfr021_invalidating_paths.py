"""NFR-021 失効対象パス正本の形式規約テスト。

パターンが意図どおりのパスに一致するかは検査せず、文字列比較だけを行う。
照合の実装とその検査は Phase 4-5 の責務である。
"""

import json
from pathlib import Path

REPO = Path(__file__).parent.parent
CONFIG_PATH = REPO / ".claude" / "nfr021-invalidating-paths.json"
REQUIRED_KEYS = {
    "description",
    "syntax",
    "default",
    "invalidating",
    "allowlist",
}
REQUIRED_INVALIDATING_PATTERNS = {
    "/backend/**",
    "/frontend/**",
    "/contracts/**",
    "/docs/development/onboarding.md",
    "/.env.example",
    "/docker-compose.yml",
    "/pyproject.toml",
    "/uv.lock",
    "/package.json",
    "/pnpm-lock.yaml",
    "/.python-version",
    "/mise.toml",
    "/tests/**",
    "/.claude/**",
    "/scripts/**",
    "/.github/workflows/**",
}
REQUIRED_ALLOWLIST_PATTERNS = {
    "/docs/ops/nfr021-acceptance/**",
    "/docs/worklog/**",
    "/docs/features/**",
}


def load_configuration() -> dict[str, object]:
    """実リポジトリの失効対象パス設定を読み込む。

    Returns:
        JSON を解析した設定オブジェクト。
    """
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_configuration_is_parseable_json_with_required_keys() -> None:
    configuration = load_configuration()

    assert isinstance(configuration, dict)
    assert REQUIRED_KEYS <= configuration.keys()


def test_all_patterns_are_root_relative() -> None:
    configuration = load_configuration()
    patterns = [
        *configuration["invalidating"],
        *configuration["allowlist"],
    ]

    assert all(pattern.startswith("/") for pattern in patterns)


def test_patterns_do_not_use_negation() -> None:
    configuration = load_configuration()
    patterns = [
        *configuration["invalidating"],
        *configuration["allowlist"],
    ]

    assert not any(pattern.startswith("!") for pattern in patterns)


def test_invalidating_and_allowlist_do_not_intersect() -> None:
    configuration = load_configuration()

    assert not (
        set(configuration["invalidating"])
        & set(configuration["allowlist"])
    )


def test_syntax_and_default_are_fail_closed_values() -> None:
    configuration = load_configuration()

    assert configuration["syntax"] == "gitignore-root-relative-v1"
    assert configuration["default"] == "invalidating"


def test_invalidating_includes_all_required_literal_patterns() -> None:
    """必要な失効パターンを文字列比較だけで検査する。

    パターンが意図どおりのパスに一致するかは検査しない。照合の実装と
    その検査は Phase 4-5 の責務である。
    """
    configuration = load_configuration()

    assert REQUIRED_INVALIDATING_PATTERNS <= set(configuration["invalidating"])


def test_allowlist_exactly_matches_required_literal_patterns() -> None:
    configuration = load_configuration()

    assert set(configuration["allowlist"]) == REQUIRED_ALLOWLIST_PATTERNS
