# 開発者オンボーディング

| 版 | 日付 | 変更内容 | 状態 |
| --- | --- | --- | --- |
| 0.1 | 2026-08-07 | 初版(ハーネス設計書 Phase 1) | draft |

pitchlog の開発に参加する開発者の初期設定手順。**Claude Code で `/setup-dev` を実行すると 3〜5 章は対話で完了できる。**

## 1. 前提ツール

| ツール | 用途 | 確認 |
| --- | --- | --- |
| Git / GitHub CLI(gh) | コード管理・PR | `gh auth status` |
| Claude Code | 対話・設計・オーケストレーション | — |
| Codex CLI + openai-codex プラグイン | 実装・レビュー委任 | `codex --version` |
| uv | Python・依存管理 | `uv --version` |
| Docker Desktop | 開発 DB(PostgreSQL) | `docker --version` |
| Node.js(実装フェーズからは mise + pnpm) | フロントエンド | `node --version` |

## 2. リポジトリ取得

`develop` が統合先。main/develop への直接コミットは hooks とブランチ保護で拒否される(作業は必ず /task-start から)。

## 3. Codex の設定(個人・必須)

`~/.codex/config.toml` に追記:

```toml
# このリポジトリを信頼する(プロジェクト設定 .codex/config.toml を読み込むため)
[projects."<このリポジトリの絶対パス>"]
trust_level = "trusted"

# Windows はネイティブ sandbox の elevated モードを推奨(設計書 12.1)
[windows]
sandbox = "elevated"
```

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
3. main ブランチ上で `git commit` を試みるとブロックされること(git_guard)

## 6. 開発フロー(要約)

`/task-start` → `/investigate`・`/research` → `/plan`(レビュー→人間承認)→ `/implement` → `/check` → `/sync-docs` → `/pr` → 人間マージ → `/task-done`。詳細は[ハーネス設計書](dev-harness-design-2026-08-07.md) 6 章。
