"""codex_run.py の実装ステップ表判定の単体テスト。"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / ".claude" / "scripts" / "codex_run.py"
REPO = Path(__file__).parent.parent
ADR_PATH = REPO / "docs" / "adr" / "ADR-001-codex-model-selection.md"

ADR_TABLE_HEADER = "| 作業 | モデル(明示 ID 固定) | effort |"
ADR_ROW_KEYS = (
    "通常実装",
    "軽微な修正",
    "コア領域の実装",
    "機械的軽作業",
    "一次コードレビュー",
    "敵対レビュー・コア領域 PR・正本確定ゲート",
    "Web 調査",
    "Web 調査(深い技術検証 `--deep`)",
)
ALLOWED_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
MODEL_ID_RE = re.compile(r"gpt-[a-z0-9]+(?:[.-][a-z0-9]+)*")


def load_codex_run():
    """テスト対象スクリプトをモジュールとして読み込む。"""
    spec = importlib.util.spec_from_file_location("codex_run_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


codex_run = load_codex_run()


def test_step_table_under_deeper_heading_is_ok():
    plan_text = """\
### 実装ステップ

この節では実装を群ごとに説明する。

#### 第 1 群: 基盤

| 番号 | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 判定を実装する | 単体テストが通る |
"""

    assert codex_run.step_table_status(plan_text) is codex_run.StepTableStatus.OK
    assert codex_run.has_filled_step_row(plan_text) is True


@pytest.mark.parametrize("closing_heading", ["### 別の節", "## 上位の節"])
def test_same_or_upper_heading_ends_step_scope(closing_heading: str):
    plan_text = f"""\
### 実装ステップ
#### 第 1 群
説明。
{closing_heading}
| 1 | スコープ外の作業 | テストが通る |
"""

    assert (
        codex_run.step_table_status(plan_text)
        is codex_run.StepTableStatus.TABLE_OUTSIDE_SCOPE
    )


def test_numeric_table_under_unrelated_heading_is_outside_scope():
    plan_text = """\
## 人間の裁定

| 1 | 採用 | 理由あり |
"""

    assert (
        codex_run.step_table_status(plan_text)
        is codex_run.StepTableStatus.TABLE_OUTSIDE_SCOPE
    )
    assert codex_run.has_filled_step_row(plan_text) is False


@pytest.mark.parametrize(
    ("opening_fence", "closing_fence"),
    [("   ```markdown", "   ```"), ("\t~~~markdown", "\t~~~")],
    ids=["backtick-indented", "tilde-indented"],
)
def test_pseudo_heading_and_table_in_fenced_code_are_ignored(
    opening_fence: str, closing_fence: str
):
    plan_text = f"""\
{opening_fence}
### 実装ステップ
| 1 | 疑似ステップ | 疑似合格条件 |
{closing_fence}
"""

    assert (
        codex_run.step_table_status(plan_text)
        is codex_run.StepTableStatus.TABLE_IN_FENCED_CODE
    )
    assert codex_run.has_filled_step_row(plan_text) is False


@pytest.mark.parametrize(
    "heading",
    [
        "### 4. **実装ステップ**(コミット単位 — 設計書 6.1)",
        "### (1) _実装ステップ_（コミット単位）",
        "### 4-3. 実装ステップ",
    ],
)
def test_normalized_step_heading_is_recognized(heading: str):
    plan_text = f"{heading}\n| 1 | 実装する | テストが通る |\n"

    assert codex_run.step_table_status(plan_text) is codex_run.StepTableStatus.OK


@pytest.mark.parametrize("heading", ["### 実装ステップではない", "### 非実装ステップ"])
def test_negative_or_unrelated_heading_is_not_recognized(heading: str):
    plan_text = f"{heading}\n| 1 | 対象外の作業 | テストが通る |\n"

    assert (
        codex_run.step_table_status(plan_text)
        is codex_run.StepTableStatus.TABLE_OUTSIDE_SCOPE
    )


@pytest.mark.parametrize(
    ("plan_text", "expected"),
    [
        ("### 実装ステップ\n| 1 | 実装する | テストが通る |\n", "OK"),
        ("# 計画\n表はまだない。\n", "NO_TABLE"),
        ("### 実装ステップ\n| 1 |  |  |\n", "NO_FILLED_ROW"),
        ("## 別の節\n| 1 | 実装する | テストが通る |\n", "TABLE_OUTSIDE_SCOPE"),
        (
            "```markdown\n### 実装ステップ\n| 1 | 実装する | テストが通る |\n```\n",
            "TABLE_IN_FENCED_CODE",
        ),
    ],
)
def test_step_table_statuses_are_mutually_exclusive(plan_text: str, expected: str):
    status = codex_run.step_table_status(plan_text)

    assert status is getattr(codex_run.StepTableStatus, expected)


@pytest.mark.parametrize(
    ("plan_text", "expected"),
    [
        ("### 実装ステップ\n| 1 | 実装する | テストが通る |\n", True),
        ("# 計画\n", False),
        ("### 実装ステップ\n| 1 |  |  |\n", False),
        ("## 別の節\n| 1 | 実装する | テストが通る |\n", False),
        ("```\n### 実装ステップ\n| 1 | 実装する | テストが通る |\n```\n", False),
    ],
)
def test_has_filled_step_row_is_true_only_for_ok(plan_text: str, expected: bool):
    assert codex_run.has_filled_step_row(plan_text) is expected


def test_crlf_plan_has_same_result():
    lf_text = "### 実装ステップ\n#### 第 1 群\n| 1 | 実装する | テストが通る |\n"
    crlf_text = lf_text.replace("\n", "\r\n")

    assert codex_run.step_table_status(lf_text) is codex_run.StepTableStatus.OK
    assert codex_run.step_table_status(crlf_text) is codex_run.StepTableStatus.OK


def extract_first_decision_table(markdown: str) -> str:
    """ADR の「決定」節にある最初の Markdown 表を取り出す。"""
    decision_match = re.search(r"^## 決定[ \t]*$", markdown, re.MULTILINE)
    assert decision_match is not None
    section = markdown[decision_match.end() :]
    next_heading = re.search(r"^## [^#]", section, re.MULTILINE)
    if next_heading is not None:
        section = section[: next_heading.start()]

    lines = section.splitlines()
    table_start = next(
        (index for index, line in enumerate(lines) if line.startswith("|")),
        None,
    )
    assert table_start is not None

    table_lines: list[str] = []
    for line in lines[table_start:]:
        if not line.startswith("|"):
            break
        table_lines.append(line)
    return "\n".join(table_lines)


def parse_adr_model_table(table_text: str) -> list[tuple[str, str, str]]:
    """固定構文の ADR-001 決定表を解析する。"""
    lines = table_text.splitlines()
    assert len(lines) == len(ADR_ROW_KEYS) + 2
    assert lines[0] == ADR_TABLE_HEADER
    assert lines[1] == "| --- | --- | --- |"

    rows: list[tuple[str, str, str]] = []
    for line in lines[2:]:
        assert line.startswith("|") and line.endswith("|")
        cells = [cell.strip() for cell in line[1:-1].split("|")]
        assert len(cells) == 3
        work, model_cell, effort = cells
        code_spans = re.findall(r"`([^`]*)`", model_cell)
        assert len(code_spans) == 1
        assert model_cell == f"`{code_spans[0]}`"
        assert MODEL_ID_RE.fullmatch(code_spans[0]) is not None
        assert effort in ALLOWED_EFFORTS
        rows.append((work, code_spans[0], effort))

    assert tuple(row[0] for row in rows) == ADR_ROW_KEYS
    return rows


def expected_adr_model_rows() -> list[tuple[str, str, str]]:
    """ADR の行キーからラッパー定数へ対応付けた期待行を返す。"""
    normal_model, normal_effort = codex_run.MODEL_MAP["通常"]
    light_model, light_effort = codex_run.MODEL_MAP["軽微"]
    core_model, core_effort = codex_run.MODEL_MAP["コア領域"]
    mechanical_model, mechanical_effort = codex_run.MODEL_MAP["機械的軽作業"]
    review_model, review_effort = codex_run.REVIEW_NORMAL
    adversarial_model, adversarial_effort = codex_run.REVIEW_ADVERSARIAL
    research_model, research_effort = codex_run.RESEARCH
    deep_model, deep_effort = codex_run.RESEARCH_DEEP
    return [
        ("通常実装", normal_model, normal_effort),
        ("軽微な修正", light_model, light_effort),
        ("コア領域の実装", core_model, core_effort),
        ("機械的軽作業", mechanical_model, mechanical_effort),
        ("一次コードレビュー", review_model, review_effort),
        (
            "敵対レビュー・コア領域 PR・正本確定ゲート",
            adversarial_model,
            adversarial_effort,
        ),
        ("Web 調査", research_model, research_effort),
        ("Web 調査(深い技術検証 `--deep`)", deep_model, deep_effort),
    ]


def assert_adr_table_matches_wrapper_constants(table_text: str) -> None:
    """固定構文表とラッパー定数が一致することを確認する。"""
    assert parse_adr_model_table(table_text) == expected_adr_model_rows()


def make_adr_table() -> str:
    """負例の基点となる正しい固定構文表を構築する。"""
    lines = [ADR_TABLE_HEADER, "| --- | --- | --- |"]
    lines.extend(
        f"| {work} | `{model}` | {effort} |"
        for work, model, effort in expected_adr_model_rows()
    )
    return "\n".join(lines)


def test_adr_decision_table_is_synchronized_with_wrapper_constants():
    """approved ADR-001 の決定表とラッパー定数を構造的に同期する。"""
    table = extract_first_decision_table(ADR_PATH.read_text(encoding="utf-8"))

    assert_adr_table_matches_wrapper_constants(table)


@pytest.mark.parametrize(
    "violation",
    [
        "model-mismatch",
        "effort-mismatch",
        "missing-row",
        "two-code-spans",
        "unknown-effort",
        "reversed-order",
        "duplicate-row-key",
    ],
)
def test_adr_decision_table_negative_examples_are_rejected(violation: str):
    """ADR の固定構文・対応表の負例 6 種を実際に拒否する。"""
    lines = make_adr_table().splitlines()
    if violation == "model-mismatch":
        lines[2] = lines[2].replace("gpt-6-sol", "gpt-6-luna", 1)
    elif violation == "effort-mismatch":
        lines[2] = lines[2].replace("| max |", "| high |", 1)
    elif violation == "missing-row":
        del lines[-1]
    elif violation == "two-code-spans":
        lines[2] = lines[2].replace(
            "`gpt-6-sol`",
            "`gpt-6-sol` `gpt-6-sol`",
            1,
        )
    elif violation == "unknown-effort":
        lines[2] = lines[2].replace("| max |", "| extreme |", 1)
    elif violation == "reversed-order":
        lines[2], lines[3] = lines[3], lines[2]
    else:
        lines[3] = lines[3].replace("軽微な修正", "通常実装", 1)

    with pytest.raises(AssertionError):
        assert_adr_table_matches_wrapper_constants("\n".join(lines))


def model_and_effort(argv: list[str]) -> tuple[str, str]:
    """Codex argv からモデルと effort の組を取り出す。"""
    model_index = argv.index("-m")
    effort = next(
        value.removeprefix("model_reasoning_effort=")
        for value in argv
        if value.startswith("model_reasoning_effort=")
    )
    return argv[model_index + 1], effort


def write_implementation_plan(tmp_path: Path, weight: str | None) -> Path:
    """implement 経路用の最小計画書を作成する。"""
    worktree = tmp_path / "pitchlog-worktrees" / "feature-foo"
    plan = worktree / "docs" / "features" / "foo" / "plan.md"
    plan.parent.mkdir(parents=True)
    lines = [
        "---",
        "status: active",
        "承認: 済",
        "worktree: ../../..",
        "branch: feature/foo",
    ]
    if weight is not None:
        lines.append(f"重さ分類: {weight}")
    lines.extend(
        [
            "---",
            "# 計画",
            "### 実装ステップ",
            "| # | ステップ | 合格条件 |",
            "| --- | --- | --- |",
            "| 1 | 実装 | pytest |",
        ]
    )
    plan.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return plan


def test_implement_routes_use_each_weight_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """implement は 4 分類それぞれの定数を argv に組み立てる。"""
    calls: list[tuple[list[str], str]] = []

    def fake_run_codex(
        argv: list[str],
        prompt: str,
        capture_session_to: Path | None = None,
    ) -> int:
        del capture_session_to
        calls.append((argv, prompt))
        return 0

    monkeypatch.setattr(codex_run, "worktree_branch", lambda _: "feature/foo")
    monkeypatch.setattr(codex_run, "require_same_repo", lambda _: None)
    monkeypatch.setattr(codex_run, "read_prompt", lambda _: "implement prompt")
    monkeypatch.setattr(codex_run, "run_codex", fake_run_codex)

    for index, (weight, expected_pair) in enumerate(codex_run.MODEL_MAP.items()):
        plan = write_implementation_plan(tmp_path / str(index), weight)
        assert codex_run.cmd_implement([str(plan)]) == 0
        assert model_and_effort(calls[-1][0]) == expected_pair
        assert calls[-1][1] == "implement prompt"


@pytest.mark.parametrize("weight", [None, "", "想定外"])
def test_implement_rejects_missing_empty_or_invalid_weight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    weight: str | None,
):
    """重さ分類は通常への既定なしで fail-closed にする。"""
    plan = write_implementation_plan(tmp_path, weight)
    monkeypatch.setattr(codex_run, "worktree_branch", lambda _: "feature/foo")
    monkeypatch.setattr(codex_run, "require_same_repo", lambda _: None)

    with pytest.raises(SystemExit) as raised:
        codex_run.cmd_implement([str(plan)])

    assert raised.value.code == 2
    stderr = capsys.readouterr().err
    for expected_weight in codex_run.MODEL_MAP:
        assert expected_weight in stderr


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """一時リポジトリに Git コマンドを実行する。"""
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )


def init_fast_repository(tmp_path: Path) -> tuple[Path, Path]:
    """fast 経路用の develop と feature worktree を持つ一時リポジトリを作る。"""
    parent = tmp_path / "pitchlog-worktrees"
    root = parent / "repository"
    root.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "develop", str(root)],
        check=True,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "test")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-qm", "chore: base")

    worktree = parent / "feature-foo"
    git(root, "worktree", "add", "-q", "-b", "feature/foo", str(worktree))
    return root, worktree


def fast_plan_text(
    *,
    status: str = "active",
    weight: str = "軽微",
    execution_mode: str = "fast",
    branch: str = "feature/foo",
    omitted_keys: frozenset[str] = frozenset(),
    extra_frontmatter: tuple[str, ...] = (),
) -> str:
    """fast 経路用の最小計画書本文を作る。"""
    fields = (
        ("status", status),
        ("承認", "済"),
        ("worktree", "../../.."),
        ("branch", branch),
        ("重さ分類", weight),
        ("計画レビュー周回", "0"),
        ("確定ゲート周回", "0"),
        ("実行方式", execution_mode),
        ("反映周コミット", "適用"),
    )
    lines = ["---", "feature: foo"]
    lines.extend(f"{key}: {value}" for key, value in fields if key not in omitted_keys)
    lines.extend(extra_frontmatter)
    lines.extend(["---", "# fast plan"])
    return "\n".join(lines) + "\n"


def write_fast_plan(worktree: Path, content: str | bytes, slug: str = "foo") -> Path:
    """指定位置に fast 経路用の plan.md を書く。"""
    path = worktree / "docs" / "features" / slug / "plan.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def prepare_fast_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: str | bytes | None = None,
) -> tuple[Path, Path, list[tuple[list[str], str]]]:
    """fast 実行の一時 worktree と run_codex 捕捉器を準備する。"""
    root, worktree = init_fast_repository(tmp_path)
    if content is not None:
        write_fast_plan(worktree, content)
    calls: list[tuple[list[str], str]] = []

    def fake_run_codex(
        argv: list[str],
        prompt: str,
        capture_session_to: Path | None = None,
    ) -> int:
        del capture_session_to
        calls.append((argv, prompt))
        return 0

    monkeypatch.setattr(codex_run, "REPO_ROOT", root)
    monkeypatch.setattr(codex_run, "read_prompt", lambda _: "fast prompt")
    monkeypatch.setattr(codex_run, "run_codex", fake_run_codex)
    monkeypatch.chdir(worktree)
    return root, worktree, calls


def test_fast_accepts_only_the_normal_position_three_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """fast は正規位置の active・軽微・fast を満たす plan だけを通す。"""
    _, _, calls = prepare_fast_command(tmp_path, monkeypatch, fast_plan_text())

    assert codex_run.cmd_fast([]) == 0
    assert len(calls) == 1
    assert model_and_effort(calls[0][0]) == codex_run.MODEL_MAP["軽微"]
    assert calls[0][1] == "fast prompt"


def test_fast_rejects_missing_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """fast は正規位置の計画書がなければ停止する。"""
    prepare_fast_command(tmp_path, monkeypatch)

    with pytest.raises(SystemExit) as raised:
        codex_run.cmd_fast([])

    assert raised.value.code == 2


def test_fast_rejects_unreadable_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """fast は計画書を読めない場合に停止する。"""
    prepare_fast_command(tmp_path, monkeypatch, fast_plan_text())
    monkeypatch.setattr(codex_run, "read_fast_frontmatter", lambda _: None)

    with pytest.raises(SystemExit) as raised:
        codex_run.cmd_fast([])

    assert raised.value.code == 2


@pytest.mark.parametrize(
    ("content", "case"),
    [
        ("\n" + fast_plan_text(), "開始区切りが1行目でない"),
        ("---\nstatus: active\nbranch: feature/foo\n", "非閉止"),
        (
            "---\nstatus: active\nbranch: feature/foo\nnote: "
            + "x" * (8 * 1024)
            + "\n---\n",
            "8KiB超過",
        ),
        (
            fast_plan_text()
            .encode("utf-8")
            .replace(b"---\n# fast plan", b"invalid: \xff\n---\n# fast plan"),
            "UTF-8不正",
        ),
        (fast_plan_text(status="active extra"), "厳密status不適合"),
    ],
)
def test_fast_rejects_invalid_frontmatter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: str | bytes,
    case: str,
):
    """fast は feature_status.py と同じ frontmatter 負例で停止する。"""
    del case
    prepare_fast_command(tmp_path, monkeypatch, content)

    with pytest.raises(SystemExit) as raised:
        codex_run.cmd_fast([])

    assert raised.value.code == 2


@pytest.mark.parametrize("key", sorted(codex_run.MACHINE_READ_FRONTMATTER_KEYS))
def test_fast_rejects_duplicate_machine_read_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    key: str,
):
    """fast は全機構読取キーの重複を後勝ちにせず停止する。"""
    content = fast_plan_text(extra_frontmatter=(f"{key}: 重複",))
    prepare_fast_command(tmp_path, monkeypatch, content)

    with pytest.raises(SystemExit) as raised:
        codex_run.cmd_fast([])

    assert raised.value.code == 2


def test_fast_rejects_plan_branch_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """fast は正規位置の plan に書かれた branch 不一致を停止する。"""
    prepare_fast_command(tmp_path, monkeypatch, fast_plan_text(branch="feature/other"))

    with pytest.raises(SystemExit) as raised:
        codex_run.cmd_fast([])

    assert raised.value.code == 2


def test_fast_rejects_same_branch_plan_at_another_position(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """fast は同一 branch を持つ別位置の plan があれば停止する。"""
    _, worktree, _ = prepare_fast_command(tmp_path, monkeypatch, fast_plan_text())
    write_fast_plan(worktree, fast_plan_text(), slug="duplicate")

    with pytest.raises(SystemExit) as raised:
        codex_run.cmd_fast([])

    assert raised.value.code == 2


@pytest.mark.parametrize(
    ("status", "weight", "execution_mode"),
    [
        ("in-review", "軽微", "fast"),
        ("active", "通常", "fast"),
        ("active", "軽微", "通常"),
        ("", "軽微", "fast"),
        ("active", "", "fast"),
        ("active", "軽微", ""),
    ],
)
def test_fast_rejects_nonmatching_or_empty_three_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    weight: str,
    execution_mode: str,
):
    """fast は status・重さ分類・実行方式の空値と不一致を停止する。"""
    prepare_fast_command(
        tmp_path,
        monkeypatch,
        fast_plan_text(status=status, weight=weight, execution_mode=execution_mode),
    )

    with pytest.raises(SystemExit) as raised:
        codex_run.cmd_fast([])

    assert raised.value.code == 2


@pytest.mark.parametrize("key", ["status", "重さ分類", "実行方式"])
def test_fast_rejects_missing_three_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    key: str,
):
    """fast は必須の 3 値が欠落しても停止する。"""
    prepare_fast_command(
        tmp_path,
        monkeypatch,
        fast_plan_text(omitted_keys=frozenset({key})),
    )

    with pytest.raises(SystemExit) as raised:
        codex_run.cmd_fast([])

    assert raised.value.code == 2


def test_research_and_review_routes_use_approved_model_pairs(
    monkeypatch: pytest.MonkeyPatch,
):
    """research と review の各経路が対応表の定数を argv に組み立てる。"""
    calls: list[tuple[list[str], str]] = []

    def fake_run_codex(
        argv: list[str],
        prompt: str,
        capture_session_to: Path | None = None,
    ) -> int:
        del capture_session_to
        calls.append((argv, prompt))
        return 0

    monkeypatch.setattr(codex_run, "find_env_files", lambda _: [])
    monkeypatch.setattr(codex_run, "read_prompt", lambda _: "route prompt")
    monkeypatch.setattr(codex_run, "run_codex", fake_run_codex)

    assert codex_run.cmd_research([]) == 0
    assert codex_run.cmd_research(["--deep"]) == 0
    assert codex_run.cmd_review(["normal"]) == 0
    assert codex_run.cmd_review(["adversarial"]) == 0

    assert [model_and_effort(argv) for argv, _ in calls] == [
        codex_run.RESEARCH,
        codex_run.RESEARCH_DEEP,
        codex_run.REVIEW_NORMAL,
        codex_run.REVIEW_ADVERSARIAL,
    ]


class ExplodingStdin:
    """読み取りが行われた場合にテストを失敗させる stdin スタブ。"""

    @property
    def buffer(self):
        """バイト読み取り要求を検出する。"""
        raise AssertionError("probe が stdin を読んだ")

    def read(self, *_: object) -> str:
        """文字列読み取り要求を検出する。"""
        raise AssertionError("probe が stdin を読んだ")


def test_probe_uses_fixed_prompt_and_read_only_cached_search(
    monkeypatch: pytest.MonkeyPatch,
):
    """probe は stdin を読まず、全 5 組を安全な argv で実行する。"""
    calls: list[tuple[list[str], str]] = []

    def fake_run_codex(
        argv: list[str],
        prompt: str,
        capture_session_to: Path | None = None,
    ) -> int:
        del capture_session_to
        calls.append((argv, prompt))
        return 0

    monkeypatch.setattr(codex_run, "run_codex", fake_run_codex)
    monkeypatch.setattr(codex_run.sys, "stdin", ExplodingStdin())

    assert codex_run.cmd_probe([]) == 0
    assert len(calls) == 5
    assert [model_and_effort(argv) for argv, _ in calls] == list(
        codex_run.configured_model_pairs()
    )
    assert [prompt for _, prompt in calls] == [codex_run.PROBE_PROMPT] * 5
    for argv, _ in calls:
        assert "--skip-git-repo-check" in argv
        assert "read-only" in argv
        assert 'web_search="cached"' in argv
        assert "workspace-write" not in argv
        assert 'web_search="live"' not in argv


def test_probe_reports_every_exit_code_and_fails_if_one_call_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """probe は途中失敗後も全組を報告し、全体を非 0 にする。"""
    exit_codes = iter([0, 7, 0, 0, 0])

    def fake_run_codex(
        argv: list[str],
        prompt: str,
        capture_session_to: Path | None = None,
    ) -> int:
        del argv, prompt, capture_session_to
        return next(exit_codes)

    monkeypatch.setattr(codex_run, "run_codex", fake_run_codex)

    assert codex_run.cmd_probe([]) == 1
    assert capsys.readouterr().err.count("終了コード") == 5


def test_main_accepts_supported_codex_version_once_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
):
    """main は対応版を 1 回だけ確認してから対象モードへ進む。"""
    version_calls: list[None] = []
    dispatched: list[list[str]] = []
    monkeypatch.setattr(
        codex_run,
        "codex_version_text",
        lambda: (version_calls.append(None) or "codex-cli 0.157.1"),
    )
    monkeypatch.setattr(codex_run, "cmd_probe", lambda args: (dispatched.append(args) or 0))
    monkeypatch.setattr(codex_run.sys, "argv", ["codex_run.py", "probe"])

    assert codex_run.main() == 0
    assert version_calls == [None]
    assert dispatched == [[]]


def test_main_rejects_older_codex_version_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """0.157.0 未満ではモデル実行前に onboarding 更新へ誘導する。"""
    monkeypatch.setattr(codex_run, "codex_version_text", lambda: "codex-cli 0.153.4")
    monkeypatch.setattr(
        codex_run,
        "cmd_probe",
        lambda _: (_ for _ in ()).throw(AssertionError("dispatch された")),
    )
    monkeypatch.setattr(codex_run.sys, "argv", ["codex_run.py", "probe"])

    with pytest.raises(SystemExit) as raised:
        codex_run.main()

    assert raised.value.code == 2
    assert "onboarding.md の 1-6" in capsys.readouterr().err


@pytest.mark.parametrize("version_text", ["", "Codex version is current"])
def test_main_rejects_unparseable_codex_version_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    version_text: str,
):
    """空文字列と想定外の版出力は fail-closed にする。"""
    monkeypatch.setattr(codex_run, "codex_version_text", lambda: version_text)
    monkeypatch.setattr(
        codex_run,
        "cmd_probe",
        lambda _: (_ for _ in ()).throw(AssertionError("dispatch された")),
    )
    monkeypatch.setattr(codex_run.sys, "argv", ["codex_run.py", "probe"])

    with pytest.raises(SystemExit) as raised:
        codex_run.main()

    assert raised.value.code == 2
