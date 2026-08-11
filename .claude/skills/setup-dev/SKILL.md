---
description: 開発者の初回セットアップ。Notion ユーザー紐づけ・Codex trust/sandbox 設定確認・ツール疎通を行う
disable-model-invocation: true
---

# 初回セットアップ(設計書 11.2 / onboarding.md)

以下を順に実行し、最後に OK/NG の表で報告する。

## 1. ツール疎通

git / uv / **python**(PATH 必須 — 無いと hooks の保護が fail-open する) / docker / codex / gh / node の `--version` を確認。欠けるものは `docs/development/onboarding.md` の導入手順を案内する。

続けて hooks の正負テストを実行する: `uv run pytest tests/`(全グリーンでなければ保護が機能していない — 修正するまで作業を始めない)。

## 2. Codex 設定確認

- `~/.codex/config.toml` を確認し、このリポジトリの trust 設定(`[projects."<リポジトリ絶対パス>"] trust_level = "trusted"`)があるか確認。なければユーザー承認の上で追記する(プロジェクトの `.codex/config.toml` はこれがないと読み込まれない)
- **WSL2 が唯一の受入保証対象**(要件書 NFR-021・onboarding.md 0章)。`uname -r` に microsoft が含まれるか等で WSL を確認し、WSL1 なら WSL2 への変換を案内する(Codex の Linux sandbox は WSL1 非対応)。**Windows ネイティブでの開発は認めない**(`[windows] sandbox` の設定は不要 — 設計書 12.1)

## 3. Notion ユーザー紐づけ(必須)

1. Notion MCP のユーザー一覧(get-users)を取得し、プロジェクトページ「⚾ baseball_scorering」のメンバーと突合する(person のみ。bot は除外)
2. AskUserQuestion で「あなたはどの Notion ユーザーですか」を候補提示する
3. 選択結果を `.claude/settings.local.json` の `env` に保存する(ファイルがなければ作成、あれば既存キーを保持してマージ):
   - `PITCHLOG_NOTION_USER_ID` = 選択ユーザーの ID
   - `PITCHLOG_NOTION_USER_NAME` = 表示名
4. **notion-map.json 突合**: タスク DB(`.claude/notion-map.json` の data_source)のステータス選択肢を取得し、map の `status_options` と突合する。不一致(改名・追加・削除)があれば map の更新を提案する(綴りの正は常に実 DB — 設計書 11.1)

## 4. permissions 構文検証

`.claude/settings.json` の Bash パターン(`Bash(git status:*)` 形式)が現行の Claude Code で有効かを /permissions 画面で確認するようユーザーに案内する。構文が変わっていれば settings.json を現行仕様に合わせて修正する。

## 報告

各項目の OK/NG と、NG の解消手順。すべて OK なら「/task-start で作業を開始できます」と案内する。
