"""Claude 調査エージェントの frontmatter を固定するテスト。"""

from pathlib import Path

REPO = Path(__file__).parent.parent
AGENT_NAMES = ("spec-checker", "legacy-analyst", "decision-tracer")


def read_frontmatter(path: Path) -> dict[str, str]:
    """Markdown ファイル先頭の frontmatter を辞書として読む。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0] == "---"
    end = next(index for index, line in enumerate(lines[1:], start=1) if line == "---")
    values: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return values


def test_research_agent_frontmatter_is_fixed_to_opus_high_and_read_tools():
    """ステップ 2 で同期した 3 エージェントのモデル・effort・tools を固定する。"""
    for name in AGENT_NAMES:
        frontmatter = read_frontmatter(REPO / ".claude" / "agents" / f"{name}.md")

        assert frontmatter["model"] == "claude-opus-5-5"
        assert frontmatter["effort"] == "high"
        assert "effortLevel" not in frontmatter
        assert frontmatter["tools"] == "Read, Grep, Glob"
