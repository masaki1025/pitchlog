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
| 1.0 | 2026-08-25 | **Phase 4 完了時受入の前提として本文を完成させ approved 化へ(起案)**: **① 陳腐化した固定テスト件数を除去**(「正負テスト 103 件」— 実測は 652。設計書 8.3「固定件数は腐るため書かない」への追随。設計書 13 章の同じ「103件」は 2026-08-16 に除去済みで本書が取り残されていた — 台帳 H-79 の実例)+ **射程の是正**(`tests/` のうち hooks は `test_hooks.py` のみで残りは `scripts/` の検査)+ **動作確認章を CI harness ジョブの現行へ追随**(`ruff check`・`ty check` を追加)。**② 受入プロファイル(要件書 NFR-021)との整合**: 受入保証対象を **`Ubuntu-26.04`(番号付き x64 WSL イメージ)に固定**(既定名 `Ubuntu` は別識別子のため対象外)/ **新規ディストリビューションの作成手順**を追加 / **Docker Desktop への言及を除去**し WSL 内 Docker Engine 一本へ(同書は事前導入を前提としない)/ 用語を「標準」「必須」の混在から**「受入保証対象」へ統一** / Node・Python の版表記を `mise.toml`・`backend/pyproject.toml` の実体へ(**版は直書きせずリポジトリを正として参照**)。**③ 本文の完成**(設計書 13 章が approved 化の要件とする「実際の依存導入・DB 初期化・起動・疎通確認まで」): **6 章に依存の導入と検証**(NFR-021 の合格項目と CI 相当の品質検査を**別節に書き分け**)、**7 章に開発 DB と起動疎通**(環境変数の区分・`docker compose up -d --wait`・コンテナ内での接続確認・backend/frontend の起動疎通と終了手順)を新設。これにより **Phase 4 の合格 5 項目すべてに対応する手順**が揃った(従来は 4 項目が完走不可)。**確定ゲート 1 周目の反映(P0×3・P1×5 を全件採用・不採用 0 件)**: **P0-1 導入手順が一切なかった** — 前提ツール表は確認方法だけで Git・gh・uv・Docker・mise・Claude Code・Codex の導入コマンドが無く、`git clone` すら書かずに「リポジトリ直下で `mise install`」を要求していて**順序が成立していなかった**。**0〜3 章を書き直し**(ホスト側の WSL 準備 → 基礎パッケージと単体ツール → リポジトリ取得 → Node・pnpm・Claude Code)、公式手順を典拠に導入コマンドを明記した。**P0-2 WSL 本体の準備が無かった** — `wsl --version`・`wsl --update`・`--set-default-version`・`VERSION=1` からの変換・初回起動のユーザー作成・`wsl -d` での入り方を追加。**P0-3 Python の版が要求と食い違っていた** — Ubuntu 26.04 の `python3` は **3.14 系**で `python-is-python3` は `/usr/bin/python` の symlink を作るだけなので、従来の案内では backend の `>=3.12,<3.13` を満たせなかった。**hooks(`/usr/bin/python3` 絶対パス)・codex ラッパー(PATH の `python`)・backend(uv が `.python-version` から自動取得)の 3 つの役割を分離**して記述した(**uv が自動でダウンロードするためシステムへ 3.12 を入れる必要はない**)。**P1**: `/setup-dev` の守備範囲を実体へ / ガード確認は **Claude Code のセッション内で行う**ことと合否の見方を明記 / 起動疎通に**待機と上限**を入れ**合否は `curl` の終了コードで判定**(サーバーは `Ctrl-C` で止めるため終了コードを用いない)/ 「この 3 つだけ」を実体の 2 項目へ是正し**合格項目の定義は要件書を正として複製しない** / **固定版の切替 3 条件の複製を除去**(要件書 NFR-021 が正 — 7.1-1)/ **bubblewrap は同梱 helper に頼らず明示導入**(OpenAI 公式が Linux/WSL2 でパッケージ導入を案内)/ **`pnpm --version` は `frontend/` で実行**(corepack は最も近い `package.json` を読む)。**版・件数は本文へ直書きせず**リポジトリの定義を正として参照する。調査の典拠は `docs/features/onboarding-approval/research.md`。**確定ゲート 2 周目の反映(P0×1・P1×7 を全件採用・不採用 0 件)**: **P0 Docker の導入手順が公式へのリンクだけだった** — 公式には apt / 手動 / スクリプトの複数経路があり一意でなく、**外部ページの変更は `onboarding_blob_sha` に含まれないため証跡が手順を固定できない**。**apt リポジトリ方式 1 つに固定して本文へ収めた**(daemon 起動の分岐も検出付きで明記)。**P1**: ① WSL の順序を是正(`wsl --install` はそのまま Linux セッションへ入るため、**ユーザー作成 → `exit` → PowerShell で VERSION 確認 → 最後に `wsl -d`** へ分離)+ **`wsl` は WSL の中からは見えないことがある**旨を追記(実測)/ ② **Notion MCP の前提を明記**(`/setup-dev` は `get-users` を使うため未接続だと完了できない。リポジトリに MCP 設定は置かない)/ ③ **git の author 設定**を追加(`gh auth login` はこれを代替しない)/ ④ 6 章を**実行主体つきの表**へ改め、**ガード確認を決定的にした**(変更が無いと Git 自身の「nothing to commit」で止まり、**ガードが壊れていても合格に見える** — 変更を作り、事前/事後の SHA 一致とガード固有の拒否メッセージを合格条件にした)/ ⑤ Python の説明を「2 つ」→**3 つ**へ是正し、**「PATH の `python` が壊れると hooks 全体が fail-open」という注記の射程を訂正**(hooks は全て `/usr/bin/python3` 絶対起動になっており、現在影響するのは codex ラッパーだけ)/ ⑥ **実装値の複製を除去**(backend の版制約・ディストリの Python 系列・環境変数の一覧と分類 → `backend/pyproject.toml`・`.python-version`・`.env.example`・`docker-compose.yml` を正として参照)/ ⑦ frontend の起動待機を **`&&` で連結**(分けると待機が時間切れでも直後の確認が 0 になり**合格に見える**)。計画: `docs/features/onboarding-approval/plan.md` | in-review |

pitchlog の開発に参加する開発者の初期設定手順。**開発環境は Windows 11 上の WSL2 で完結する。受入保証対象は WSL2 のみ**(Windows ネイティブでの開発は保証対象外 — 受入条件の正は要件書 NFR-021)。

**本書は「WSL2 を有効化しただけの Windows 11」から出発して 8 章まで到達できる形で書く。** 前提として求めるのは WSL2 の有効化だけで、その他のツールはすべて本書の手順内で導入する(要件書 NFR-021 の受入プロファイル)。

> `/setup-dev` は **4 章(Codex の設定)・5 章(Notion 紐づけ)と、ツールの疎通確認・permissions 構文検証**を対話で進める。**導入そのもの・6 章のガード実地確認・7〜8 章は行わない。**

## 0. WSL2 環境の用意(Windows ホスト側)

**受入保証対象のディストリビューションは `Ubuntu-26.04`(番号付き x64 WSL イメージ)に固定する。** 既定名 `Ubuntu` は WSL 上で**別の識別子**として扱われ、安定版 LTS を自動追随するため保証対象としない。他ディストリビューション・他版も保証対象外(要件書 NFR-021 の受入プロファイル。**切替規則も同要件が正** — 本書では規定しない)。

**この章は Windows の PowerShell(管理者)で実行する。** `wsl` は Windows 側のコマンドで、**WSL のシェルの中からは見えないことがある**(`appendWindowsPath` の設定による — 実測 2026-08-25)。

**① WSL 本体を整えて、ディストリを作る**(PowerShell):

```powershell
wsl --version                    # 表示されない場合は WSL 本体が古い
wsl --update                     # 新しい配布形式に対応させる
wsl --set-default-version 2      # 新規ディストリを WSL2 で作る
wsl --list --online              # `Ubuntu-26.04` が一覧にあることを確認
wsl --install -d Ubuntu-26.04    # 番号付きイメージを指定する(`Ubuntu` ではない)
```

**② 初回起動で Linux のユーザー名とパスワードを対話的に作成する。** `wsl --install` はそのまま Linux セッションへ入るので、作成が済んだら **`exit` で PowerShell へ戻る**。作成したアカウントがそのディストリの既定ユーザーになる。

**③ WSL2 であることを確認する**(PowerShell):

```powershell
wsl --list --verbose             # 対象が VERSION=2 であることを確認
```

**VERSION が 1 だったら**変換する(Codex の Linux sandbox〔bubblewrap〕は **WSL1 非対応**):

```powershell
wsl --shutdown
wsl --set-version Ubuntu-26.04 2
wsl --list --verbose             # VERSION=2 になったことを再確認
```

**④ 作業用のシェルへ入る**(以降 1 章からはすべてこの中で実行する):

```powershell
wsl -d Ubuntu-26.04
```

- **リポジトリは WSL 側ファイルシステム**(`~/` 配下)に置く。`/mnt/c` 配下は I/O 性能・ファイル監視の面で非推奨
- worktree 置き場も WSL 側の兄弟ディレクトリ(例: `~/dev/pitchlog-worktrees/`)

## 1. 基礎パッケージと単体ツールの導入(WSL 内)

**1-1. 基礎パッケージ**

```bash
sudo apt update
sudo apt install -y ca-certificates curl git gnupg bubblewrap python-is-python3
```

- `bubblewrap` は Codex の Linux sandbox が使う。**同梱 helper に頼らず明示的に導入する**(公式は Linux/WSL2 でパッケージ導入を案内している。同梱 helper は `bwrap` が PATH に無いときのフォールバックで、unprivileged user namespace を作れることが条件)
- `python-is-python3` は **`python` → `python3` の symlink を作る**。`/usr/bin/python3` の版は変えない

> **この環境には役割の違う Python が 3 つある。** 版の要求はそれぞれの定義ファイルが正なので、本書には書かない。
> - **hooks**: `.claude/settings.json` が **`/usr/bin/python3` を絶対パスで**起動する。ディストリの python3 でよく、標準ライブラリのみで動く。**PATH の `python` には依存しない**
> - **codex ラッパー**: PATH 上の `python` を使う(`.claude/settings.json` の許可も `python .claude/scripts/codex_run.py`)。上記 symlink で満たされる
> - **backend**: 版の要求は `backend/pyproject.toml` の `requires-python` と `.python-version` が正。**uv がそれを読んで自動で用意する**(7 章)ので、**ディストリの python3 が要求と違っていても別途導入する必要はない**

> **罠(実例 2026-08-07)**: Windows 側の pyenv 等のシムが WSL の PATH に紛れ、`python` が「見つかるが実行できない」状態になることがある。**現在この影響を受けるのは codex ラッパーで、hooks は絶対パス起動なので影響しない**(2026-08-07 当時は hooks も PATH 解決だったため fail-open した — その後の是正で射程が狭まった)。`which python` が `/mnt/c/...` を指すなら、`ln -s /usr/bin/python3 ~/.local/bin/python` 等で WSL 側解決を先行させ、`python --version` が通ることを必ず確認する。

**1-2. uv**(Python・依存管理)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv --version
```

**1-3. GitHub CLI**

```bash
sudo mkdir -p -m 755 /etc/apt/keyrings
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null
sudo chmod 644 /etc/apt/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
sudo apt update && sudo apt install -y gh
gh auth login          # WSL からブラウザが開けなければデバイスコードで完了できる
gh auth status
```

**コミット作成者の設定**(新規ディストリでは未設定。`gh auth login` はこれを代替しない):

```bash
git config --global user.name    # 空なら設定する
git config --global user.email   # 空なら設定する
git config --global user.name "<氏名>"
git config --global user.email "<コミットに使うメールアドレス>"
```

**1-4. mise**(Node の版を `mise.toml` から解決する — 版はリポジトリが正。CI も同じ)

```bash
curl https://mise.run | sh
echo 'eval "$($HOME/.local/bin/mise activate bash)"' >> ~/.bashrc
source ~/.bashrc
mise --version
```

**1-5. Docker Engine + Compose plugin**(開発 DB。**Docker Desktop は使わない** — 受入プロファイルは Windows ホスト側の事前導入を WSL2 の有効化のみに限る)

**apt リポジトリ方式を採る**([Docker 公式](https://docs.docker.com/engine/install/ubuntu/)の複数経路のうち、本書はこれ 1 つに固定する)。

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

**daemon を起動する。** WSL2 では systemd が既定で無効なことがあるので、まず確認する。

```bash
if [ -d /run/systemd/system ]; then sudo systemctl start docker; else sudo service docker start; fi
```

- systemd を使いたい場合は `/etc/wsl.conf` に `[boot]` の `systemd=true` を書き、PowerShell から `wsl --shutdown` して入り直す
- **WSL を停止すると WSL 内の daemon も止まる**(Docker Desktop の常駐 daemon とは別物)。WSL を起動し直したら上記の起動確認をやり直す

`docker` グループへ入り、**sudo なしで**動くことを確認する。

```bash
sudo usermod -aG docker "$USER"
newgrp docker                    # または一度シェルを開き直す
docker compose version
docker run --rm hello-world
```

**1-6. Codex CLI**

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
codex                            # 初回にサインイン
codex --version
```

## 2. リポジトリ取得

```bash
mkdir -p ~/dev && cd ~/dev
gh repo clone masaki1025/pitchlog
cd pitchlog
```

`develop` が統合先。main/develop への直接コミットは hooks(Claude Code 経由の操作)で拒否される(作業は必ず /task-start から)。**GitHub 側のブランチ保護は現在未適用**(プラン制約 — 正は [github-setup.md](github-setup.md) 1〜2 章)のため、人間の端末からの直接 push は機構的には止まらない — 同 2 章の管理手続(PR 経由のみ・マージ前の CI 確認)を遵守する。

## 3. Node・pnpm・Claude Code(リポジトリ取得後)

Node の版は `mise.toml` が正なので、**リポジトリ直下で**解決させる。

```bash
mise install                     # リポジトリ直下で実行(mise.toml を読む)
node --version                   # mise.toml の固定版と一致すること
corepack enable
(cd frontend && pnpm --version)  # frontend/ で実行する(理由は下記)
```

> **`pnpm --version` は `frontend/` で実行する。** corepack は**起点から親へ遡って最も近い `package.json`** の `packageManager` を読む。リポジトリ直下に `package.json` は無く、`frontend/package.json` にだけ指定があるため、直下で実行すると意図した版が選ばれる保証がない。

Claude Code は Node が入ってから導入する(`sudo npm` は使わない)。

```bash
npm install -g @anthropic-ai/claude-code
claude doctor                    # 導入状態の確認
```

## 4. Codex の設定(個人・必須)

`~/.codex/config.toml` に追記:

```toml
# このリポジトリを信頼する(プロジェクト設定 .codex/config.toml を読み込むため)
[projects."<このリポジトリの WSL 上の絶対パス>"]
trust_level = "trusted"
```

- 既存の config が `projects = { ... }` の**インライン表形式**の場合は、その表の中にエントリを追記する(`[projects."..."]` セクションを併記すると TOML の重複定義でパースエラーになる)
- WSL2 では Codex sandbox に Linux 実装(bubblewrap)が自動適用される。`[windows]` セクションは不要
- Codex の起動は `.claude/scripts/codex_run.py` ラッパー経由のみ(生実行は codex_guard がブロック — 設計書 12.1)

## 5. Notion ユーザー紐づけ(個人・必須)

**前提: Claude Code から Notion MCP が使えること。** `/setup-dev` は Notion のユーザー一覧(`get-users`)を取得して候補を提示するため、未接続だとこの章を完了できない。**リポジトリに MCP 設定は置いていない**(個人のアカウント接続)。

1. Claude Code で `/mcp` を実行し、**Notion が接続済み**であることを確認する
2. 未接続なら Claude Code の MCP 設定から Notion を追加して認証する
3. `/setup-dev` を実行する

手動で設定する場合は `.claude/settings.local.json`(gitignore 済み)に:

```json
{
  "env": {
    "PITCHLOG_NOTION_USER_ID": "<自分の Notion ユーザー ID>",
    "PITCHLOG_NOTION_USER_NAME": "<表示名>"
  }
}
```

## 6. ハーネスの動作確認

**実行主体が項目ごとに違う。** hooks は Claude Code の PreToolUse として動くので、**通常のシェルで試しても再現しない**。

| # | 実行主体 | 確認 | 期待 |
| --- | --- | --- | --- |
| 1 | Claude Code | 起動する | SessionStart フックが「現在ブランチ…」を表示する |
| 2 | **Claude Code** | `/permissions` | `.claude/settings.json` のルールが有効に見える(Bash パターン構文が現行仕様か確認) |
| 3 | WSL のシェル | `uv run pytest tests/` | 終了コード 0(hooks・codex ラッパー・`scripts/` の検査に対する正負テスト。**件数は CI の harness ジョブの実行結果を正とする** — 固定件数は腐るため書かない〔[ハーネス設計書](dev-harness-design-2026-08-07.md) 8.3〕) |
| 4 | WSL のシェル | `uv run ruff check .` と `uv run ty check` | いずれも終了コード 0(CI の harness ジョブと同じ検査。**`ruff format` は未導入 — 走らせない**) |
| 5 | **Claude Code** | 下記のガード確認(git_guard) | git_guard 固有の拒否メッセージが出て、**HEAD が動かない** |
| 6 | **Claude Code** | 下記のガード確認(codex_guard) | codex_guard がブロックし、**ラッパー経由の案内**が出る |

**項目 5 の手順**(Claude Code に実行させる)。**コミットすべき変更が無いと Git 自身の「nothing to commit」で止まり、ガードが壊れていても合格に見える**ため、必ず変更を作ってから試す。

```bash
git switch main
git rev-parse HEAD                      # 事前 SHA を記録
echo "guard check" >> /tmp/guard-check && git add -A
git commit -m "guard check"             # ← git_guard がここで拒否するはず
git rev-parse HEAD                      # 事前と同じであること
git restore --staged . 2>/dev/null; git switch -
```

合格条件: **git_guard の拒否メッセージが出る**(Git の「nothing to commit」ではない)**かつ事前・事後の SHA が一致する**。

**項目 6 の手順**(同上): Claude Code に `codex exec "test"` を実行させる。合格条件は **codex_guard がブロックし、`codex_run.py` ラッパー経由の案内が出る**こと。

## 7. 依存の導入と検証(backend / frontend)

6 章まででハーネスは動く。ここから pitchlog 本体の依存を入れる。

### 7-1. NFR-021 の合格項目

**この節で確認するのは backend と frontend の 2 つ**(ハーネスの pytest は 6 章の項目 3)。合格項目の定義は要件書 NFR-021 の測定方法が正であり、本書では複製しない。

**backend**(まずリポジトリ直下で Python を用意してから `backend/` で):

```bash
uv python install                # リポジトリ直下で実行(.python-version を読む)
cd backend
uv sync --locked --dev
uv run pytest
```

> ディストリの python3 が要求と違っていても、**uv が `.python-version` の版を自動で取得する**ので別途導入する必要はない。

**frontend**(3 章で `mise install` と `corepack enable` を済ませてから `frontend/` で):

```bash
pnpm install --frozen-lockfile
pnpm test
```

いずれも**全グリーン**であること。**件数は書かない** — 実行結果を正とする([ハーネス設計書](dev-harness-design-2026-08-07.md) 8.3)。

### 7-2. CI 相当の品質検査

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

> リポジトリルートのハーネス(`scripts/`・`tests/`)は検査の構成が違う — **`ruff format` は未導入なので走らせない**(6 章の項目 4 が正)。

## 8. 開発 DB と起動疎通

### 8-1. 環境変数ファイル

リポジトリ直下の `.env.example` をコピーして `.env` を作る(`.env` は gitignore 済み。**コミットしない・値をログへ出さない** — NFR-014)。

```bash
cp .env.example .env
```

**変数の一覧と既定値は `.env.example` が正**であり、本書では複製しない。**どれが必須かは `docker-compose.yml` が `:?required` で宣言している**ので、`.env.example` をそのままコピーすれば起動に必要なものは揃う。

パスワードを変えたときは、`.env.example` のコメントに従って関連する値も同時に更新する(URL に含める値は percent-encode する)。

### 8-2. 開発 DB の起動と接続確認

```bash
docker compose up -d --wait --wait-timeout 120
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select 1"'
```

- `--wait` が healthcheck の healthy を待つ(`docker compose ps` は待機しない)
- **変数はコンテナ内で展開する**。`.env` は compose の変数展開に使われるだけで**呼び出し元のシェルへは export されない**ため、ホスト側で `$POSTGRES_USER` と書くと空になる
- 期待値: **終了コード 0**・標準出力が **`1`**

> やり直すときは `docker compose down -v` でボリュームごと消す。`POSTGRES_INITDB_ARGS` は**空の PGDATA の初回だけ**有効で、既存ボリュームには再適用されない。

### 8-3. backend・frontend の起動疎通

サーバーは**別のシェルで前景起動**し、確認は元のシェルから行う。**合否はサーバーの終了コードではなく `curl` の終了コードで判定する**(サーバーは `Ctrl-C` で止めるため終了コードが非ゼロになりうる)。

**backend**(`backend/` で):

```bash
uv run fastapi dev src/pitchlog/main.py --port 8800
```

起動を待って確認する(最大 30 秒):

```bash
timeout 30 sh -c 'until curl -fsS --max-time 3 http://127.0.0.1:8800/health; do sleep 1; done'
```

期待値: **終了コード 0**・出力が **`{"status":"ok"}`**。ポート **8800** は frontend の proxy 先(`frontend/vite.config.ts`)に合わせる。

**frontend**(`frontend/` で):

```bash
pnpm dev --host 127.0.0.1 --port 5173 --strictPort
```

起動を待って確認する(最大 30 秒):

```bash
timeout 30 sh -c 'until curl -fsS --max-time 3 -o /dev/null http://127.0.0.1:5173/; do sleep 1; done' \
  && curl -fsS -o /dev/null -w '%{http_code}\n' --max-time 3 http://127.0.0.1:5173/
```

> **`&&` で連結する。** 分けて書くと、待機が時間切れ(終了コード 124)でも直後にサーバーが立ち上がれば 2 本目が 0 になり、**最後の終了コードだけを見ると合格に見えてしまう**。

期待値: **終了コード 0**・HTTP **`200`**。`--strictPort` を付けないとポートが埋まっているとき Vite が別ポートへ移り、確認先が一意にならない。

> **`--` を挟まない。** `pnpm dev -- --port …` と書くと Vite は `--` 以降を解釈せず、フラグが**黙って無視される**(実測: `--port 5199` を渡しても既定の 5173 で起動した)。`pnpm test -- --run`(7-2)は CI の記述に合わせたもので、あちらは script が既に `vitest run` のため無害。

> **`/api/health` は使わない。** Vite の proxy は `/api` を**接頭辞を残したまま**転送するので、backend 側に `/api/health` は存在せず 404 になる。

**終了**: 各シェルで `Ctrl-C`(サーバーの終了コードは合否に用いない)→ `docker compose down`。

## 9. 開発フロー(要約)

`/task-start` → `/investigate`・`/research` → `/plan`(レビュー→人間承認)→ `/implement` → `/check` → `/sync-docs` → `/pr` → 人間マージ → `/task-done`。詳細は[ハーネス設計書](dev-harness-design-2026-08-07.md) 6 章。
