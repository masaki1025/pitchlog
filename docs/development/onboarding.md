# 開発者オンボーディング

| 版 | 日付 | 変更内容 | 状態 |
| --- | --- | --- | --- |
| 0.1 | 2026-08-07 | 初版(ハーネス設計書 Phase 1) | draft |
| 0.2 | 2026-08-07 | **WSL2 前提に改稿**(設計書 論点C改訂 — PO 決定) | draft |
| 0.3 | 2026-08-07 | WSL 実地セットアップの知見を反映: python は Windows 側シムの罠に注意(sudo 不要の代替手順を追記)/ trust 設定はインライン表形式への追記に注意 / bubblewrap は同梱版で動作 | draft |

pitchlog の開発に参加する開発者の初期設定手順。**開発環境は WSL2(Ubuntu 推奨)を標準とする**。Claude Code で `/setup-dev` を実行すると 3〜5 章は対話で完了できる。

## 0. WSL2(必須)

- **WSL2 であること**: `wsl -l -v` で VERSION=2 を確認(Codex の Linux sandbox〔bubblewrap〕は **WSL1 非対応**)
- **リポジトリは WSL 側ファイルシステム**(`~/` 配下)に置く。`/mnt/c` 配下は I/O 性能・ファイル監視の面で非推奨
- worktree 置き場も WSL 側の兄弟ディレクトリ(例: `~/dev/pitchlog-worktrees/`)

## 1. 前提ツール(WSL 内に導入)

| ツール | 用途 | 確認 |
| --- | --- | --- |
| Git / GitHub CLI(gh) | コード管理・PR | `gh auth status` |
| Claude Code | 対話・設計・オーケストレーション | `claude --version` |
| Codex CLI + openai-codex プラグイン | 実装・レビュー委任 | `codex --version`・ログイン済みであること |
| uv | Python・依存管理 | `uv --version` |
| Python 3.12+(`python` コマンド) | hooks・codex ラッパーの実行(無いと保護が fail-open する) | `python --version`(Ubuntu は `sudo apt install python-is-python3`。sudo を使わない代替: `ln -s /usr/bin/python3 ~/.local/bin/python`) |
| Docker | 開発 DB(PostgreSQL) | `docker --version`(Docker Desktop の WSL2 統合、または WSL 内ネイティブ導入) |
| Node.js 20+(実装フェーズからは mise + pnpm) | フロントエンド | `node --version` |

> **罠(実例 2026-08-07)**: Windows 側の pyenv 等のシムが WSL の PATH に紛れ、`python` が「見つかるが実行できない」状態になることがある — この場合 **hooks 全体が fail-open する**。`which python` が `/mnt/c/...` を指すなら、上記いずれかの導入で WSL 側解決を先行させ、`python --version` が通ることを必ず確認する。

## 2. リポジトリ取得

`develop` が統合先。main/develop への直接コミットは hooks とブランチ保護で拒否される(作業は必ず /task-start から)。

## 3. Codex の設定(個人・必須)

`~/.codex/config.toml` に追記:

```toml
# このリポジトリを信頼する(プロジェクト設定 .codex/config.toml を読み込むため)
[projects."<このリポジトリの WSL 上の絶対パス>"]
trust_level = "trusted"
```

- 既存の config が `projects = { ... }` の**インライン表形式**の場合は、その表の中にエントリを追記する(`[projects."..."]` セクションを併記すると TOML の重複定義でパースエラーになる)
- WSL2 では Codex sandbox に Linux 実装(bubblewrap)が自動適用される。`[windows]` セクションは不要。システムに bubblewrap が無くても codex 同梱版で動作する(警告を消すには任意で `sudo apt install bubblewrap`)
- Codex の起動は `.claude/scripts/codex_run.py` ラッパー経由のみ(生実行は codex_guard がブロック — 設計書 12.1)

## 4. Notion ユーザー紐づけ(個人・必須)

`/setup-dev` が対話で設定する。手動の場合は `.claude/settings.local.json`(gitignore 済み)に:

```json
{
  "env": {
    "PITCHLOG_NOTION_USER_ID": "<自分の Notion ユーザー ID>",
    "PITCHLOG_NOTION_USER_NAME": "<表示名>"
  }
}
```

## 5. 動作確認

1. Claude Code を起動 → SessionStart フックが「現在ブランチ…」を表示すること
2. `/permissions` で `.claude/settings.json` のルールが有効に見えること(Bash パターン構文が現行仕様か確認)
3. `uv run pytest tests/` が全グリーンであること(hooks・ラッパーの正負テスト 59 件)
4. main ブランチ上で `git commit` を試みるとブロックされること(git_guard の実地確認)
5. 生の `codex exec` がブロックされ、ラッパー経由の案内が出ること(codex_guard の実地確認)

## 6. 開発フロー(要約)

`/task-start` → `/investigate`・`/research` → `/plan`(レビュー→人間承認)→ `/implement` → `/check` → `/sync-docs` → `/pr` → 人間マージ → `/task-done`。詳細は[ハーネス設計書](dev-harness-design-2026-08-07.md) 6 章。
