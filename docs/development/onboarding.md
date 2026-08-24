---
status: draft
---

# 開発者オンボーディング

| 版 | 日付 | 変更内容 | 状態 |
| --- | --- | --- | --- |
| 0.1 | 2026-08-07 | 初版(ハーネス設計書 Phase 1) | draft |
| 0.2 | 2026-08-07 | **WSL2 前提に改稿**(設計書 論点C改訂 — PO 決定) | draft |
| 0.3 | 2026-08-07 | WSL 実地セットアップの知見を反映: python は Windows 側シムの罠に注意(sudo 不要の代替手順を追記)/ trust 設定はインライン表形式への追記に注意 / bubblewrap は同梱版で動作 | draft |
| 0.4 | 2026-08-10 | 冒頭に frontmatter(status: draft)を追加 — 状態の機械可読化(ci-foundation / docs-lint) | draft |
| 0.5 | 2026-08-10 | 2 章の「ブランチ保護で拒否される」を現実に整合(保護は未適用 — 縮退状態の明記。正は github-setup.md。設計書 v1.1 ゲート P0-3 の伝播) | draft |

pitchlog の開発に参加する開発者の初期設定手順。**開発環境は Windows 11 上の WSL2 で完結する。受入保証対象は WSL2 のみ**(Windows ネイティブでの開発は保証対象外 — 受入条件の正は要件書 NFR-021)。Claude Code で `/setup-dev` を実行すると 3〜5 章は対話で完了できる。

## 0. WSL2(受入保証対象の環境)

**受入保証対象のディストリビューションは `Ubuntu-26.04`(番号付き x64 WSL イメージ)に固定する。** 既定名 `Ubuntu` は WSL 上で**別の識別子**として扱われ、安定版 LTS を自動追随するため保証対象としない。他ディストリビューション・他版も保証対象外(要件書 NFR-021 の受入プロファイル)。

Windows ホスト側の事前導入は **WSL2 の有効化のみ**を前提とし、その他の開発ツールは**すべて本書の手順内で導入する**。

新規に作成する場合(PowerShell):

```powershell
wsl --list --online          # 提供中のディストリビューション識別子を確認
wsl --install Ubuntu-26.04   # 番号付きイメージを指定する(`Ubuntu` ではない)
```

- **WSL2 であること**: `wsl -l -v` で VERSION=2 を確認(Codex の Linux sandbox〔bubblewrap〕は **WSL1 非対応**)
- **リポジトリは WSL 側ファイルシステム**(`~/` 配下)に置く。`/mnt/c` 配下は I/O 性能・ファイル監視の面で非推奨
- worktree 置き場も WSL 側の兄弟ディレクトリ(例: `~/dev/pitchlog-worktrees/`)

> 固定版を新しい Ubuntu LTS へ切り替えるには、(1) WSL 向けの正式提供開始 (2) 本書の更新 (3) 新版での受入再実施 の 3 点が要る(要件書 NFR-021。「最新」を都度判定する運用はとらない)。

## 1. 前提ツール(WSL 内に導入)

| ツール | 用途 | 確認 |
| --- | --- | --- |
| Git / GitHub CLI(gh) | コード管理・PR | `gh auth status` |
| Claude Code | 対話・設計・オーケストレーション | `claude --version` |
| Codex CLI | 実装・レビュー委任(`codex_run.py` ラッパー経由。プラグインは不要) | `codex --version`・ログイン済みであること |
| uv | Python・依存管理 | `uv --version` |
| Python 3.12 系(`python` コマンド) | hooks・codex ラッパーの実行(無いと保護が fail-open する) | `python --version`(Ubuntu は `sudo apt install python-is-python3`。sudo を使わない代替: `ln -s /usr/bin/python3 ~/.local/bin/python`)。**backend は `>=3.12,<3.13`**(`backend/pyproject.toml`)なので 3.13 系は使わない |
| Docker Engine + Compose plugin | 開発 DB(PostgreSQL) | `docker compose version`。**WSL 内に Docker Engine を導入する**(受入プロファイルは Windows ホスト側の事前導入を WSL2 の有効化のみに限る — 要件書 NFR-021)。導入後 `sudo usermod -aG docker $USER` を行い、シェルを開き直して **sudo なしで `docker ps` が通る**ことを確認する |
| mise | Node の版を `mise.toml` から解決する(版はリポジトリが正) | `mise --version` → リポジトリ直下で `mise install` |
| Node.js | フロントエンド | `node --version` が `mise.toml` の固定版と一致すること(版を手で指定しない) |
| pnpm | フロントエンドのパッケージ管理 | `corepack enable` → `pnpm --version` が `frontend/package.json` の `packageManager` の版と一致すること |

> **罠(実例 2026-08-07)**: Windows 側の pyenv 等のシムが WSL の PATH に紛れ、`python` が「見つかるが実行できない」状態になることがある — この場合 **hooks 全体が fail-open する**。`which python` が `/mnt/c/...` を指すなら、上記いずれかの導入で WSL 側解決を先行させ、`python --version` が通ることを必ず確認する。

## 2. リポジトリ取得

`develop` が統合先。main/develop への直接コミットは hooks(Claude Code 経由の操作)で拒否される(作業は必ず /task-start から)。**GitHub 側のブランチ保護は現在未適用**(プラン制約 — 正は [github-setup.md](github-setup.md) 1〜2 章)のため、人間の端末からの直接 push は機構的には止まらない — 同 2 章の管理手続(PR 経由のみ・マージ前の CI 確認)を遵守する。

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
3. `uv run pytest tests/` が全グリーンであること(hooks・codex ラッパー・`scripts/` の検査に対する正負テスト。**件数は CI の harness ジョブの実行結果を正とする** — 固定件数は腐るため書かない〔[ハーネス設計書](dev-harness-design-2026-08-07.md) 8.3〕)
4. `uv run ruff check .` と `uv run ty check` がいずれもエラーなしであること(CI の harness ジョブと同じ検査。**`ruff format` は未導入 — 走らせない**)
5. main ブランチ上で `git commit` を試みるとブロックされること(git_guard の実地確認)
6. 生の `codex exec` がブロックされ、ラッパー経由の案内が出ること(codex_guard の実地確認)

## 6. 開発フロー(要約)

`/task-start` → `/investigate`・`/research` → `/plan`(レビュー→人間承認)→ `/implement` → `/check` → `/sync-docs` → `/pr` → 人間マージ → `/task-done`。詳細は[ハーネス設計書](dev-harness-design-2026-08-07.md) 6 章。
