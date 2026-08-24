---
status: in-review
---

# 開発者オンボーディング

| 版 | 日付 | 変更内容 | 状態 |
| --- | --- | --- | --- |
| 0.1 | 2026-08-07 | 初版(ハーネス設計書 Phase 1) | draft |
| 0.2 | 2026-08-07 | **WSL2 前提に改稿**(設計書 論点C改訂 — PO 決定) | draft |
| 0.3 | 2026-08-07 | WSL 実地セットアップの知見を反映: python は Windows 側シムの罠に注意(sudo 不要の代替手順を追記)/ trust 設定はインライン表形式への追記に注意 / bubblewrap は同梱版で動作 | draft |
| 0.4 | 2026-08-10 | 冒頭に frontmatter(status: draft)を追加 — 状態の機械可読化(ci-foundation / docs-lint) | draft |
| 0.5 | 2026-08-10 | 2 章の「ブランチ保護で拒否される」を現実に整合(保護は未適用 — 縮退状態の明記。正は github-setup.md。設計書 v1.1 ゲート P0-3 の伝播) | draft |
| 1.0 | 2026-08-25 | **Phase 4 完了時受入の前提として本文を完成させ approved 化へ(起案)**: **① 陳腐化した固定テスト件数を除去**(「正負テスト 103 件」— 実測は 652。設計書 8.3「固定件数は腐るため書かない」への追随。設計書 13 章の同じ「103件」は 2026-08-16 に除去済みで本書が取り残されていた — 台帳 H-79 の実例)+ **射程の是正**(`tests/` のうち hooks は `test_hooks.py` のみで残りは `scripts/` の検査)+ **動作確認章を CI harness ジョブの現行へ追随**(`ruff check`・`ty check` を追加)。**② 受入プロファイル(要件書 NFR-021)との整合**: 受入保証対象を **`Ubuntu-26.04`(番号付き x64 WSL イメージ)に固定**(既定名 `Ubuntu` は別識別子のため対象外)/ **新規ディストリビューションの作成手順**を追加 / **Docker Desktop への言及を除去**し WSL 内 Docker Engine 一本へ(同書は事前導入を前提としない)/ 用語を「標準」「必須」の混在から**「受入保証対象」へ統一** / Node・Python の版表記を `mise.toml`・`backend/pyproject.toml` の実体へ(**版は直書きせずリポジトリを正として参照**)。**③ 本文の完成**(設計書 13 章が approved 化の要件とする「実際の依存導入・DB 初期化・起動・疎通確認まで」): **6 章に依存の導入と検証**(NFR-021 の合格項目と CI 相当の品質検査を**別節に書き分け**)、**7 章に開発 DB と起動疎通**(環境変数の区分・`docker compose up -d --wait`・コンテナ内での接続確認・backend/frontend の起動疎通と終了手順)を新設。これにより **Phase 4 の合格 5 項目すべてに対応する手順**が揃った(従来は 4 項目が完走不可)。計画: `docs/features/onboarding-approval/plan.md` | in-review |

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
| mise | Node の版を `mise.toml` から解決する(版はリポジトリが正 — CI も同じ) | 導入: `curl https://mise.run \| sh` → シェル設定へ `eval "$(~/.local/bin/mise activate bash)"` を追加して開き直す → `mise --version` |
| Node.js | フロントエンド | リポジトリ直下で `mise install` → `node --version` が `mise.toml` の固定版と一致すること(**版を手で指定しない**)。既存環境で nvm 等を使っている場合も、**固定版と一致していることを確認する** |
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

## 6. 依存の導入と検証(backend / frontend)

5 章まででハーネスは動く。ここから pitchlog 本体の依存を入れる。

### 6-1. NFR-021 の合格項目

**受入(NFR-021)で確認するのはこの 3 つだけ**(ハーネスの pytest は 5 章の項目 3)。合格条件の正は要件書 NFR-021 の測定方法。

**backend**(`backend/` で):

```bash
uv sync --locked --dev
uv run pytest
```

**frontend**(まずリポジトリ直下で `mise install`・`corepack enable` を済ませてから `frontend/` で):

```bash
pnpm install --frozen-lockfile
pnpm test
```

いずれも**全グリーン**であること。**件数は書かない** — 実行結果を正とする([ハーネス設計書](dev-harness-design-2026-08-07.md) 8.3)。

### 6-2. CI 相当の品質検査

**受入の合格項目ではない**が、PR を出す前に手元で通しておくと CI の往復が減る。CI(`.github/workflows/ci.yml`)の backend / frontend ジョブと同じコマンド列:

**backend**(`backend/` で):

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest --cov
```

**frontend**(`frontend/` で):

```bash
pnpm exec eslint .
pnpm exec prettier --check .
pnpm exec vue-tsc --noEmit
pnpm test -- --run
```

> リポジトリルートのハーネス(`scripts/`・`tests/`)は検査の構成が違う — **`ruff format` は未導入なので走らせない**(5 章の項目 4 が正)。

## 7. 開発 DB と起動疎通

### 7-1. 環境変数ファイル

リポジトリ直下の `.env.example` をコピーして `.env` を作る(`.env` は gitignore 済み。**コミットしない・値をログへ出さない** — NFR-014)。

```bash
cp .env.example .env
```

`docker-compose.yml` が要求する変数の区分:

| 区分 | 変数 |
| --- | --- |
| **必須**(未設定なら起動しない) | `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` |
| 既定値あり | `POSTGRES_PORT`(既定 5432) |
| **現時点では未使用** | `DATABASE_URL`(backend からまだ参照されていない。将来 backend が使う前提の予約) |

パスワードを変えたときは `DATABASE_URL` も同時に更新し、URL に含める値は percent-encode する。

### 7-2. 開発 DB の起動と接続確認

```bash
docker compose up -d --wait --wait-timeout 120
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select 1"'
```

- `--wait` が healthcheck の healthy を待つ(`docker compose ps` は待機しない)
- **変数はコンテナ内で展開する**。`.env` は compose の変数展開に使われるだけで**呼び出し元のシェルへは export されない**ため、ホスト側で `$POSTGRES_USER` と書くと空になる
- 期待値: `psql` の標準出力が **`1`**

> やり直すときは `docker compose down -v` でボリュームごと消す。`POSTGRES_INITDB_ARGS` は**空の PGDATA の初回だけ**有効で、既存ボリュームには再適用されない。

### 7-3. backend・frontend の起動疎通

**backend**(`backend/` で。別のシェルを開く):

```bash
uv run fastapi dev src/pitchlog/main.py --port 8800
```

別のシェルから:

```bash
curl -fsS http://127.0.0.1:8800/health
```

期待値: **`{"status":"ok"}`**。ポート **8800** は frontend の proxy 先(`frontend/vite.config.ts`)に合わせる。

**frontend**(`frontend/` で。別のシェルを開く):

```bash
pnpm dev --host 127.0.0.1 --port 5173 --strictPort
```

別のシェルから:

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5173/
```

期待値: **`200`**。`--strictPort` を付けないとポートが埋まっているとき Vite が別ポートへ移り、確認先が一意にならない。

> **`--` を挟まない。** `pnpm dev -- --port …` と書くと Vite は `--` 以降を解釈せず、フラグが**黙って無視される**(実測: `--port 5199` を渡しても既定の 5173 で起動した)。`pnpm test -- --run`(6-2)は CI の記述に合わせたもので、あちらは script が既に `vitest run` のため無害。

> **`/api/health` は使わない。** Vite の proxy は `/api` を**接頭辞を残したまま**転送するので、backend 側に `/api/health` は存在せず 404 になる。

**終了**: 各シェルで `Ctrl-C` → `docker compose down`。

## 8. 開発フロー(要約)

`/task-start` → `/investigate`・`/research` → `/plan`(レビュー→人間承認)→ `/implement` → `/check` → `/sync-docs` → `/pr` → 人間マージ → `/task-done`。詳細は[ハーネス設計書](dev-harness-design-2026-08-07.md) 6 章。
