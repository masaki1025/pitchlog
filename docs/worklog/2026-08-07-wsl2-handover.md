---
date: 2026-08-07
topic: WSL2 移行の引継ぎとハーネス実地整備
branch: feature/dev-harness
---

# 作業ログ: 2026-08-07 WSL2 移行の引継ぎとハーネス実地整備

## やったこと

- **環境実査(WSL2・Ubuntu)**: リポジトリは WSL 側 FS(`~/projects/pitchlog`)に配置済みを確認。gh は認証済み(HellsingWalter)・Codex は ChatGPT ログイン済み
- **python 修復(重大)**: `python` が Windows 側 pyenv-win の壊れたシム(`/mnt/c/.../pyenv-win/shims/python`)に解決され、**hooks 全体が fail-open していた**。PATH 先頭の `~/.local/bin` に `python → /usr/bin/python3` のシムリンクを作成して解消(sudo 不要の代替。onboarding v0.3 に罠として記録)
- **git ユーザー設定**: WSL 側が未設定だったため、リポジトリローカルに過去コミットと同一の作者(`walter97 <168tokumitsu@gmail.com>`)を設定
- **テスト**: `uv sync` → `uv run pytest tests/` **44 件全グリーン**(0.77s)
- **hooks 実地確認(onboarding §5 相当・10 項目 OK)**: main 上 commit ブロック / feature 上 commit 許可 / refspec 経由 develop push ブロック / 生 `codex exec` ブロック / ラッパー経由許可 / 危険フラグ無条件ブロック / `.env` 参照ブロック / `.env.example` 許可 / `docs/legacy` 書込ブロック / 通常 docs 書込許可。SessionStart(session_context)の文脈注入も正常
- **Codex 整備**: CLI を 0.144.0 → **0.146.1**(設計書・ADR-001 の検証済みベースライン)へ更新。`~/.codex/config.toml` に本リポジトリの trust を追記(既存が `projects = { ... }` インライン表形式だったため表内に追記 — セクション併記は TOML 重複でエラー)
- **ラッパー疎通**: `codex_run.py review normal` で一気通貫確認 — read-only sandbox 適用・`model_reasoning_effort=max` 受理・日本語 stdin 正常・セッション ID 捕捉。bubblewrap はシステム未導入でも codex 同梱版で動作(警告のみ)
- **文書更新**: onboarding v0.3(python シムの罠・インライン表・bubblewrap)/ docs/README.md 索引の設計書版数を 0.9 → 0.11 に現行化
- **敵対レビュー2周目を実行**(設計書 v0.11 の宣言事項「WSL 移行後に実施」): `codex_run.py review adversarial`(sol xhigh)— 結果は本ログ末尾・チャット報告参照

## 決定

- python の PATH 修復は `~/.local/bin/python` シムリンク方式(sudo 不要・`python-is-python3` と同効果)。onboarding に両方式を記載
- Codex CLI は検証済みベースライン 0.146.1 に固定して更新(latest 追従はしない)
- git 作者設定はリポジトリローカル(グローバルは未設定のまま — 他プロジェクトに影響させない)

## 未決・次の一歩

- **セッション再起動が必要**: 本セッションは main(settings 無し)で起動したため hooks/permissions が未ロード。次回起動時に SessionStart 注入と /permissions を確認(onboarding §5-1/5-2)
- **Notion 紐づけ未設定**: `/setup-dev` の対話が必要(PITCHLOG_NOTION_USER_ID)
- **Docker WSL 統合が無効**: Docker Desktop → Settings → Resources → WSL integration で有効化(Phase 4 の開発 DB まで不要)
- **openai-codex プラグイン未導入**(WSL 側 Claude Code): レビュー実行はラッパーで完結するため必須ではない。stop-review-gate(Claude 直接実装時の保険)を使う場合のみ導入
- **敵対レビュー2周目の指摘反映 → 収束 → 人間承認**(/finalize-doc 手順の続き)。approved 化は PO 承認後のみ
- 任意: `sudo apt install python-is-python3 bubblewrap`(現状はシムリンク+同梱版で充足)
