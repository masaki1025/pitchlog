# 実機通しチェックリスト(onboarding v1.0 — 確定ゲート前)

**目的**: `docs/development/onboarding.md` を **新規 Ubuntu 26.04 環境で実際に通し**、机上では出ない差分を採取する。裁定 5(2026-08-24)の後半。

**これは NFR-021 の受入ではない。** 受入は 4-6 で、approved 版を使って行う。本通しは**その前に本文を直すための予行**であり、証跡にはならない。

---

## 記録の仕方

各項目で **OK / 詰まった / 違った** のいずれかを記録してください。詰まった・違った場合は次の 3 つがあると直せます。

1. **実行したコマンド**(コピーでよい)
2. **出た結果**(エラーメッセージの全文が理想。長ければ末尾数行)
3. **どう解決したか**(追加で入れたもの・変えたコマンド・調べた先)

> 「よく分からないまま進んだ」も貴重な記録です。**手順が一意でない**という指摘そのものなので、そのまま書いてください。

---

## 0 章 WSL2 環境の用意(Windows の PowerShell)

- [ ] `wsl --version` が表示される(されない場合は `wsl --update`)
- [ ] `wsl --set-default-version 2` が通る
- [ ] `wsl --list --online` に `Ubuntu-26.04` がある **← 2026-08-25 に確認済み**
- [ ] `wsl --install -d Ubuntu-26.04` が完了する
- [ ] 初回対話でユーザー名・パスワードを作成できる
- [ ] **Ubuntu Insights の同意画面が出たか**(本文はこれを想定して書いた。出なければ教えてください)
- [ ] `exit` で PowerShell へ戻れる
- [ ] `wsl --list --verbose` で `Ubuntu-26.04` が **VERSION=2**
- [ ] `wsl -d Ubuntu-26.04` で作業シェルへ入れる

**この章で特に見てほしいこと**: 本文に書いていない対話・確認・待ち時間がなかったか。

---

## 1 章 基礎パッケージと単体ツール(WSL 内)

- [ ] 1-1 `apt update` と基礎パッケージ(`ca-certificates curl git gnupg bubblewrap python-is-python3`)
- [ ] 1-2 uv(`curl ... | sh` → `source` → `uv --version`)
- [ ] 1-3 GitHub CLI(keyring → sources → `apt install gh` → `gh auth login` → `gh auth status`)
- [ ] 1-3 コミット作成者の設定(`user.name` / `user.email`)
- [ ] 1-4 mise(`curl https://mise.run | sh` → `~/.bashrc` へ activate 追記 → `source` → `mise --version`)
- [ ] 1-5 **Docker Engine**(keyring → `docker.sources` → `apt install docker-ce ...`)
- [ ] 1-5 daemon 起動(`/run/systemd/system` の有無で分岐)
- [ ] 1-5 `docker` グループ → **sudo なしで** `docker compose version` と `docker run --rm hello-world`
- [ ] 1-6 Codex CLI(インストーラ → `codex` でサインイン → 終了 → `codex --version`)

**この章で特に見てほしいこと**:

- **`docker.sources` のヒアドキュメント**が意図どおり展開されるか(`Suites:` と `Architectures:` の行に実際の値が入るか)。`cat /etc/apt/sources.list.d/docker.sources` で確認できます
- daemon の分岐がどちらに転んだか(systemd か `service` か)
- `newgrp docker` で足りたか、シェルを開き直す必要があったか
- `gh auth login` がブラウザで通ったか、デバイスコードになったか

---

## 2 章 リポジトリ取得

- [ ] `gh repo clone masaki1025/pitchlog`
- [ ] **`git switch develop`** と `git branch --show-current` が `develop`

**この章で特に見てほしいこと**: clone 先のパス(`~/dev/pitchlog`)で問題ないか。

---

## 3 章 Node・pnpm・Claude Code

- [ ] `mise install`(リポジトリ直下)
- [ ] `node --version` が `mise.toml` の固定版と一致
- [ ] `corepack enable`
- [ ] `(cd frontend && pnpm --version)` が `packageManager` の版と一致
- [ ] `npm install -g @anthropic-ai/claude-code` → `claude doctor`
- [ ] **リポジトリ直下で `claude` を起動し、初回認証を完了**

**この章で特に見てほしいこと**: `mise install` に `mise trust` 等の追加操作が要らなかったか。`npm install -g` が sudo なしで通ったか。

---

## 4 章 Codex の設定

- [ ] `~/.codex/config.toml` に `[projects."<絶対パス>"] trust_level = "trusted"` を追記
- [ ] 既存 config がインライン表形式だった場合の扱い(該当したか)

---

## 5 章 Notion ユーザー紐づけ

- [ ] Claude Code で `/mcp` → Notion の接続状態を確認
- [ ] 未接続なら **WSL のシェル**で `claude mcp add --transport http notion https://mcp.notion.com/mcp`
- [ ] `/mcp` から OAuth 認証を完了
- [ ] `/setup-dev` が完走し、`PITCHLOG_NOTION_USER_ID` が設定される

**この章で特に見てほしいこと**: `claude mcp add` を Claude Code のセッション内から実行してしまう混乱が起きなかったか。セッションの再起動が要ったか。

---

## 6 章 ハーネスの動作確認

- [ ] 1 Claude Code 起動 → SessionStart フックが「現在ブランチ…」を表示
- [ ] 2 `/permissions` でルールが有効に見える
- [ ] 3 `uv run pytest tests/` が終了コード 0
- [ ] 4 `uv run ruff check .` と `uv run ty check` が終了コード 0
- [ ] 5 **git_guard の確認**(8 行を **1 行ずつ別々に**実行。**`develop` のまま** — `main` へ切り替えると旧版のガードを試すことになる)— 拒否メッセージが出て SHA が変わらない
- [ ] 6 **codex_guard の確認** — ブロックされてラッパー経由の案内が出る

**この章で特に見てほしいこと**: 項目 5 の「1 行ずつ」が実際に守れたか。**まとめて実行してしまった場合に何が起きたか**も貴重です。

---

## 7 章 依存の導入と検証(合格項目 2・3)

- [ ] `uv python install`(リポジトリ直下)
- [ ] `(cd backend && uv sync --locked --dev && uv run pytest)` が **全グリーン**
- [ ] `(cd frontend && pnpm install --frozen-lockfile && pnpm test)` が **全グリーン**

**この章で特に見てほしいこと**: **uv が Python を自動ダウンロードしたか**(ここが P0-3 の核心。ディストリの python3 は 3.14 系で、backend は別の版を要求する)。ダウンロードのログが出たかどうかを教えてください。

---

## 8 章 開発 DB と起動疎通(合格項目 4・5)

- [ ] 8-1 `cp .env.example .env`(リポジトリ直下)
- [ ] 8-2 `docker compose up -d --wait --wait-timeout 120` が終了コード 0
- [ ] 8-2 `psql` の確認が終了コード 0 で標準出力 `1`
- [ ] 8-3 backend 起動 → `curl .../health` が `{"status":"ok"}`
- [ ] 8-3 frontend 起動 → `curl .../` が **200**
- [ ] 8-3 終了手順(`Ctrl-C` → `docker compose down`)

**この章で特に見てほしいこと**: `--wait` が何秒かかったか(本文は上限 120 秒)。ポート 8800・5173 が既に埋まっていなかったか。

---

## 通し終えたら

- [ ] **合格 5 項目すべてに到達できたか**(ハーネス pytest / backend pytest / frontend Vitest / DB 接続 / 起動疎通)
- [ ] 所要時間(おおよそで構いません)
- [ ] **本文に書いていなくて必要だったもの**の一覧
- [ ] **本文と違ったコマンド・出力**の一覧

これらを教えていただければ本文へ反映し、最終のレビュー 1 周 → 承認 → **approved 化** へ進みます。

> **注意**: 本通しで作った環境は、**そのまま 4-6 の受入には使えません**。受入は「新規に作成した環境」で「approved 版の手順」を完走する必要があるため(要件書 NFR-021)。受入時はもう一度新規に作ります。
