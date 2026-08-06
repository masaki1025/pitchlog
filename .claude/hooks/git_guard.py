"""main/develop 保護フック(PreToolUse / Bash|PowerShell)。

設計書 6.2/8.3: 保護ブランチ上での commit/merge/rebase、保護ブランチへの push
(カレント経由・refspec 経由)、force push、ブランチ強制削除を検知してブロックする(exit 2)。
5周目レビュー対応で**トークンベース**へ作り替え: 引用符付き refspec(`'HEAD:develop'`)・
短縮クラスタ(`-fu`・`-df`)を字句解析で正規化して判定する。判定不能な git は安全側でブロック。
複合コマンドはセグメント単位で評価し、`cd`+git は判定不能として保守的にブロックする。
"""
import json
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from guard_common import basename, effective_command, shell_tokens

PROTECTED = {"main", "develop"}
VERBS = {"commit", "merge", "push", "rebase"}


def current_branch(cwd: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=cwd or None, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def short_letters(tokens: list[str]) -> set[str]:
    """短縮オプション(`-fu` 等・`--long` は除く)の文字集合。"""
    out: set[str] = set()
    for t in tokens:
        if t.startswith("-") and not t.startswith("--") and len(t) > 1:
            out |= set(t[1:])
    return out


def positionals(tokens: list[str], after: str) -> list[str]:
    """トークン列中の `after` より後ろの非オプション語(refspec 推定用)。"""
    try:
        i = tokens.index(after)
    except ValueError:
        return []
    return [t for t in tokens[i + 1:] if not t.startswith("-")]


def is_git(tokens: list[str]) -> bool:
    return any(basename(t) == "git" for t in tokens)


def block(msg: str) -> int:
    print(f"ブロック: {msg}", file=sys.stderr)
    return 2


def check_segment(seg: str, tokens: list[str] | None, cwd_default: str) -> int | None:
    """1 セグメントを検査。ブロックなら 2、問題なければ None。"""
    if tokens is None:
        # 解析不能: git の危険動詞が含まれるなら安全側でブロック
        if re.search(r"\bgit\b", seg) and re.search(r"\b(push|branch|commit|merge|rebase)\b", seg):
            return block("git コマンドを字句解析できませんでした(引用符を確認)。安全側で遮断します。")
        return None
    if not is_git(tokens):
        return None
    longs = {t for t in tokens if t.startswith("--")}
    shorts = short_letters(tokens)

    if "push" in tokens:
        # force push: --force / --force-with-lease / -f クラスタ / +refspec
        if "--force" in longs or "--force-with-lease" in longs or "f" in shorts \
           or any(p.startswith("+") for p in positionals(tokens, "push")):
            return block("force push(+refspec・-f クラスタ含む)は禁止です(設計書 8.2/8.3)。")
        # 保護ブランチ宛て push(HEAD:develop 等。引用符は除去済み)
        for p in positionals(tokens, "push"):
            dest = p.split(":", 1)[1] if ":" in p else p
            if dest.removeprefix("refs/heads/") in PROTECTED:
                return block("保護ブランチ(main/develop)への push は禁止です。PR 経由で(設計書 6.2)。")

    if "branch" in tokens:
        del_flag = "--delete" in longs or "d" in shorts
        force_flag = "--force" in longs or "f" in shorts
        if "D" in shorts or (del_flag and force_flag):
            return block("ブランチの強制削除(-D / --delete --force / -df 等)は禁止です"
                         "(未マージ履歴の喪失防止 — 設計書 8.2)。-d を使うか人間が実行してください。")

    if VERBS & set(tokens):
        m = re.search(r"-C\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))", seg)
        cwd = (m.group(1) or m.group(2) or m.group(3)) if m else cwd_default
        if current_branch(cwd) in PROTECTED:
            return block("保護ブランチへの直接操作は禁止です。develop から feature/* を切って PR 経由で(/task-start)。")
    return None


def main() -> int:
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return 0
    command = effective_command(str(data.get("tool_input", {}).get("command", "")))
    if "git" not in command:
        return 0

    cwd_default = data.get("cwd", "")
    cd_seen = False
    for seg in re.split(r"&&|\|\||\||;|\n", command):
        if re.match(r"\s*cd\b", seg):
            cd_seen = True
            continue
        tokens = shell_tokens(seg)
        has_verb = (tokens is not None and (VERBS & set(tokens))) or (
            tokens is None and re.search(r"\bgit\b.*\b(commit|merge|push|rebase)\b", seg)
        )
        # `cd` 後の git 操作はブランチ判定不能 — 保守的にブロック
        if cd_seen and has_verb:
            return block("`cd` と git 操作の複合はブランチ判定ができません。`git -C <path>` を使うか分けて実行してください(8.3)。")
        rc = check_segment(seg, tokens, cwd_default)
        if rc is not None:
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
