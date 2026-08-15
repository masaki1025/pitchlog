"""main/develop 保護フック(PreToolUse / Bash|PowerShell)。

設計書 6.2/8.3: 保護ブランチ上での commit/merge/rebase、保護ブランチ宛ての push、
force push、ブランチ強制削除を検知してブロックする(exit 2)。
Git のグローバルオプションを解釈して実サブコマンドを特定し、呼び出し解析不能な Git は
安全側でブロックする。複合コマンドは引用符を考慮したセグメント単位で評価し、`cd`+git は
カレントブランチを判定できないため保守的にブロックする。
"""
from dataclasses import dataclass
import json
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from guard_common import basename, effective_command, shell_segments, shell_tokens

PROTECTED = {"main", "develop"}
CURRENT_BRANCH_VERBS = {"commit", "merge", "rebase"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
COMMAND_PREFIXES = {
    "env", "command", "builtin", "sudo", "time", "nice", "nohup", "stdbuf", "setsid",
}

# Git の組み込みサブコマンド。alias や外部 git-foo は解決しないため、ここには含めない。
KNOWN_SUBCOMMANDS = frozenset({
    "add", "am", "annotate", "apply", "archimport", "archive", "backfill", "bisect", "blame",
    "branch", "bugreport", "bundle", "cat-file", "check-attr", "check-ignore", "check-mailmap",
    "check-ref-format", "checkout", "checkout-index", "cherry", "cherry-pick", "citool", "clean",
    "clone", "column", "commit", "commit-graph", "commit-tree", "config", "count-objects",
    "credential", "credential-cache", "credential-store", "cvsexportcommit", "cvsimport", "cvsserver",
    "daemon", "describe", "diagnose", "diff", "diff-files", "diff-index", "diff-pairs", "diff-tree",
    "difftool", "fast-export", "fast-import", "fetch", "fetch-pack", "filter-branch", "fmt-merge-msg",
    "for-each-ref", "for-each-repo", "format-patch", "fsck", "gc", "get-tar-commit-id", "gitk", "gitweb",
    "grep", "gui",
    "hash-object", "help", "hook", "http-backend", "imap-send", "index-pack", "info-path", "init",
    "instaweb", "interpret-trailers", "last-modified", "log", "ls-files", "ls-remote", "ls-tree",
    "mailinfo", "mailsplit", "maintenance", "merge", "merge-base", "merge-file", "merge-index",
    "merge-one-file", "merge-tree", "mergetool", "mktag", "mktree", "multi-pack-index", "mv", "name-rev",
    "notes", "pack-objects", "pack-refs", "pack-redundant", "p4", "prune", "prune-packed", "pull", "push",
    "quiltimport", "range-diff", "read-tree", "rebase", "reflog", "refs", "remote", "repack", "replace",
    "repo", "replay", "request-pull", "reset", "restore", "revert", "rerere", "rev-list", "rev-parse", "rm",
    "scalar",
    "send-email", "send-pack", "sh-i18n", "sh-setup", "shortlog", "show", "show-branch", "show-index", "show-ref",
    "sparse-checkout", "split-index", "stash", "status", "stripspace", "submodule", "svn", "switch", "symbolic-ref",
    "tag", "unpack-file",
    "unpack-objects", "update-index", "update-ref", "update-server-info", "var", "verify-commit", "verify-pack",
    "verify-tag", "version", "whatchanged", "worktree", "write-tree",
})

# サブコマンドより前で認める Git グローバルオプション。値を取る形式は別に扱う。
GLOBAL_VALUE_OPTIONS = {
    "--attr-source", "--config-env", "--exec-path", "--git-dir", "--list-cmds", "--namespace",
    "--super-prefix", "--work-tree",
}
GLOBAL_FLAG_OPTIONS = {
    "--bare", "--glob-pathspecs", "--icase-pathspecs", "--literal-pathspecs", "--no-advice",
    "--no-lazy-fetch", "--no-optional-locks", "--no-pager", "--no-replace-objects", "--noglob-pathspecs",
    "--paginate", "-p", "-P",
}
GLOBAL_INFO_OPTIONS = {
    "--help": "help", "-h": "help", "--html-path": "html-path", "--info-path": "info-path",
    "--man-path": "man-path", "--version": "version", "-v": "version",
}

PUSH_ALLOWED = "allowed"
PUSH_FORCE = "force"
PUSH_PROTECTED = "protected"
PUSH_UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class GitInvocation:
    """解析済みの Git 呼び出し。

    Attributes:
        subcommand: 実サブコマンド。解析不能なら None。
        cwd: `-C` を順に適用した有効 cwd。
        args: 実サブコマンドより後ろの引数。
    """

    subcommand: str | None
    cwd: str
    args: list[str]


def current_branch(cwd: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=cwd or None, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def command_index(tokens: list[str]) -> int | None:
    """環境変数代入・コマンド接頭辞を飛ばしたコマンド語の位置を返す。"""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", token):
            index += 1
            continue
        if basename(token).lower() in COMMAND_PREFIXES:
            index += 1
            continue
        return index
    return None


def apply_dash_c(cwd: str, path: str) -> str:
    """Git の `-C` を 1 回適用した cwd を返す。"""
    base = os.path.abspath(cwd or os.getcwd())
    if os.path.isabs(path):
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(base, path))


def unknown_invocation(cwd: str) -> GitInvocation:
    """解析不能を表す Git 呼び出しを返す。"""
    return GitInvocation(subcommand=None, cwd=cwd, args=[])


def is_config_assignment(value: str) -> bool:
    """`-c` / `--config-env` の `name=value` 形式かを返す。"""
    name, separator, _ = value.partition("=")
    return bool(name) and bool(separator)


def parse_git_invocation(tokens: list[str], cwd_default: str) -> GitInvocation | None:
    """Git のグローバルオプションを解釈して実サブコマンドを特定する。

    Args:
        tokens: 1 セグメント分の字句解析済みトークン。
        cwd_default: `-C` がないときの cwd。

    Returns:
        Git 呼び出しでなければ None。Git 呼び出しで解析不能な場合は、
        subcommand が None の GitInvocation。
    """
    command = command_index(tokens)
    if command is None:
        return None
    if basename(tokens[command]).lower() not in {"git", "git.exe"}:
        # コマンド語を特定できない形も、従来どおり Git を含めば安全側に倒す。
        if any(basename(token).lower() in {"git", "git.exe"} for token in tokens):
            return unknown_invocation(cwd_default)
        return None

    cwd = cwd_default
    index = command + 1
    while index < len(tokens):
        token = tokens[index]

        if token in GLOBAL_INFO_OPTIONS:
            return GitInvocation(GLOBAL_INFO_OPTIONS[token], cwd, tokens[index + 1:])

        if token in {"-c", "-C"}:
            if index + 1 >= len(tokens):
                return unknown_invocation(cwd)
            value = tokens[index + 1]
            if token == "-C":
                cwd = apply_dash_c(cwd, value)
            elif not is_config_assignment(value):
                return unknown_invocation(cwd)
            index += 2
            continue

        if token.startswith("-c") and len(token) > 2:
            if not is_config_assignment(token[2:]):
                return unknown_invocation(cwd)
            index += 1
            continue
        if token.startswith("-C") and len(token) > 2:
            cwd = apply_dash_c(cwd, token[2:])
            index += 1
            continue

        if token.startswith("--"):
            option, separator, value = token.partition("=")
            if option in GLOBAL_VALUE_OPTIONS:
                if not separator:
                    if index + 1 >= len(tokens):
                        return unknown_invocation(cwd)
                    value = tokens[index + 1]
                    index += 2
                elif not value:
                    return unknown_invocation(cwd)
                else:
                    index += 1
                if option == "--config-env" and not is_config_assignment(value):
                    return unknown_invocation(cwd)
                continue
            if option in GLOBAL_FLAG_OPTIONS and not separator:
                index += 1
                continue
            return unknown_invocation(cwd)

        if token.startswith("-"):
            return unknown_invocation(cwd)
        if token not in KNOWN_SUBCOMMANDS:
            return unknown_invocation(cwd)
        return GitInvocation(token, cwd, tokens[index + 1:])

    return unknown_invocation(cwd)


def shell_c_body(tokens: list[str], depth: int) -> str | None:
    """1 段目の shell `-c` 本文を返す。対象外なら None。"""
    command = command_index(tokens)
    if command is None or depth >= 1 or basename(tokens[command]).lower() not in SHELLS:
        return None
    for index in range(command + 1, len(tokens)):
        token = tokens[index]
        if token.startswith("-") and not token.startswith("--") and "c" in token[1:]:
            return tokens[index + 1] if index + 1 < len(tokens) else None
    return None


def short_letters(tokens: list[str]) -> set[str]:
    """短縮オプション(`-fu` 等・`--long` は除く)の文字集合。"""
    out: set[str] = set()
    for t in tokens:
        if t.startswith("-") and not t.startswith("--") and len(t) > 1:
            out |= set(t[1:])
    return out


def block(msg: str) -> int:
    print(f"ブロック: {msg}", file=sys.stderr)
    return 2


def is_protected_ref(ref: str) -> bool:
    """ref が保護ブランチを指すかを返す。"""
    return ref.removeprefix("refs/heads/") in PROTECTED


def has_ref_pattern(ref: str) -> bool:
    """ref に静的な宛先を確定できないワイルドカードがあるかを返す。"""
    return any(char in ref for char in "*?[")


def push_target_status(args: list[str]) -> str:
    """push 引数から宛先の安全性を三値+forceで判定する。

    Returns:
        allowed: すべての宛先が明示的な非保護 ref。
        protected: 保護ブランチ宛ての ref がある。
        force: force push または +refspec がある。
        unresolved: 宛先を静的に確定できない。
    """
    positionals: list[str] = []
    delete = False
    all_or_mirror = False
    index = 0

    while index < len(args):
        token = args[index]
        if token == "--":
            positionals.extend(args[index + 1:])
            break
        if token == "--force" or token == "--force-with-lease" or token.startswith("--force-with-lease="):
            return PUSH_FORCE
        if token == "--force-if-includes":
            return PUSH_FORCE
        if token == "--delete":
            delete = True
            index += 1
            continue
        if token in {"--all", "--mirror"}:
            all_or_mirror = True
            index += 1
            continue
        if token in {
            "--atomic", "--dry-run", "--follow-tags", "--no-progress", "--no-signed", "--no-thin",
            "--no-verify", "--porcelain", "--progress", "--quiet", "--recurse-submodules", "--set-upstream",
            "--signed", "--thin", "--verbose", "--verify",
        }:
            index += 1
            continue
        if token.startswith("--"):
            option, separator, value = token.partition("=")
            if option in {"--exec", "--push-option", "--receive-pack", "--repo", "--recurse-submodules"}:
                if separator:
                    if not value:
                        return PUSH_UNRESOLVED
                    index += 1
                    continue
                if index + 1 >= len(args):
                    return PUSH_UNRESOLVED
                index += 2
                continue
            return PUSH_UNRESOLVED
        if token.startswith("-"):
            letters = token[1:]
            if not letters:
                return PUSH_UNRESOLVED
            if "f" in letters:
                return PUSH_FORCE
            if letters.startswith("o"):
                if len(letters) > 1:
                    index += 1
                    continue
                if index + 1 >= len(args):
                    return PUSH_UNRESOLVED
                index += 2
                continue
            if not set(letters) <= {"4", "6", "d", "n", "q", "u", "v"}:
                return PUSH_UNRESOLVED
            delete = delete or "d" in letters
            index += 1
            continue

        positionals.append(token)
        index += 1

    if all_or_mirror or len(positionals) < 2:
        return PUSH_UNRESOLVED

    refspecs = positionals[1:]
    if delete:
        for ref in refspecs:
            if ref.startswith("+"):
                return PUSH_FORCE
            if ":" in ref or has_ref_pattern(ref):
                return PUSH_UNRESOLVED
            if is_protected_ref(ref):
                return PUSH_PROTECTED
        return PUSH_ALLOWED

    for refspec in refspecs:
        if refspec.startswith("+"):
            return PUSH_FORCE
        if refspec == "HEAD":
            # HEAD は参照先ブランチを静的に確定できない。
            return PUSH_UNRESOLVED
        destination = refspec if ":" not in refspec else refspec.split(":", 1)[1]
        if not destination or has_ref_pattern(destination):
            return PUSH_UNRESOLVED
        if is_protected_ref(destination):
            return PUSH_PROTECTED
    return PUSH_ALLOWED


def check_git_invocation(invocation: GitInvocation, cd_seen: bool) -> int | None:
    """解析済みの Git 呼び出しを検査する。ブロック時は 2 を返す。"""
    if invocation.subcommand is None:
        return block("git のグローバルオプションまたはサブコマンドを解析できませんでした。安全側で遮断します。")

    if invocation.subcommand == "push":
        status = push_target_status(invocation.args)
        if status == PUSH_FORCE:
            return block("force push(+refspec・-f クラスタ含む)は禁止です(設計書 8.2/8.3)。")
        if status == PUSH_PROTECTED:
            return block("保護ブランチ(main/develop)宛ての push は禁止です。PR 経由で(設計書 6.2)。")
        if status == PUSH_UNRESOLVED:
            return block("push の宛先を静的に解決できません。明示的な非保護 refspec または "
                         "--delete <branch> を指定してください。安全側で遮断します。")
        return None

    if invocation.subcommand == "branch":
        longs = {token for token in invocation.args if token.startswith("--")}
        shorts = short_letters(invocation.args)
        delete = "--delete" in longs or "d" in shorts
        force = "--force" in longs or "f" in shorts
        if "D" in shorts or (delete and force):
            return block("ブランチの強制削除(-D / --delete --force / -df 等)は禁止です"
                         "(未マージ履歴の喪失防止 — 設計書 8.2)。-d を使うか人間が実行してください。")

    if invocation.subcommand in CURRENT_BRANCH_VERBS:
        if cd_seen:
            return block("`cd` と git 操作の複合はブランチ判定ができません。`git -C <path>` を使うか分けて実行してください(8.3)。")
        if current_branch(invocation.cwd) in PROTECTED:
            return block("保護ブランチへの直接操作は禁止です。develop から feature/* を切って PR 経由で(/task-start)。")
    return None


def check_segments(
    segments: list[str],
    cwd_default: str,
    depth: int = 0,
    cd_seen: bool = False,
) -> int | None:
    """セグメント列を検査する。shell `-c` 本文は 1 段だけ再帰評価する。"""
    current_cd_seen = cd_seen
    for segment in segments:
        if re.match(r"\s*cd\b", segment):
            current_cd_seen = True
            continue

        tokens = shell_tokens(segment)
        if tokens is None:
            if "git" in segment.lower():
                return block("git コマンドを字句解析できませんでした(引用符を確認)。安全側で遮断します。")
            continue

        body = shell_c_body(tokens, depth)
        if body is not None:
            inner_segments = shell_segments(body)
            if inner_segments is None:
                return block("shell -c 内の git コマンドを字句解析できませんでした。安全側で遮断します。")
            rc = check_segments(inner_segments, cwd_default, depth + 1, current_cd_seen)
            if rc is not None:
                return rc

        invocation = parse_git_invocation(tokens, cwd_default)
        if invocation is not None:
            rc = check_git_invocation(invocation, current_cd_seen)
            if rc is not None:
                return rc
    return None


def main() -> int:
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return 0
    command = effective_command(str(data.get("tool_input", {}).get("command", "")))
    if "git" not in command:
        return 0

    segments = shell_segments(command)
    if segments is None:
        return block("git を含むコマンドを字句解析できませんでした(引用符を確認)。安全側で遮断します。")

    rc = check_segments(segments, str(data.get("cwd", "")))
    return rc if rc is not None else 0


if __name__ == "__main__":
    sys.exit(main())
