---
status: approved
---

# 開発者オンボーディング

| 版 | 日付 | 変更内容 | 状態 |
| --- | --- | --- | --- |
| 0.1 | 2026-08-07 | 初版(ハーネス設計書 Phase 1) | draft |
| 0.2 | 2026-08-07 | **WSL2 前提に改稿**(設計書 論点C改訂 — PO 決定) | draft |
| 0.3 | 2026-08-07 | WSL 実地セットアップの知見を反映: python は Windows 側シムの罠に注意(sudo 不要の代替手順を追記)/ trust 設定はインライン表形式への追記に注意 / bubblewrap は同梱版で動作 | draft |
| 0.4 | 2026-08-10 | 冒頭に frontmatter(status: draft)を追加 — 状態の機械可読化(ci-foundation / docs-lint) | draft |
| 0.5 | 2026-08-10 | 2 章の「ブランチ保護で拒否される」を現実に整合(保護は未適用 — 縮退状態の明記。正は github-setup.md。設計書 v1.1 ゲート P0-3 の伝播) | draft |
| 1.0 | 2026-08-25 | **Phase 4 完了時受入の前提として本文を完成させ approved 化へ(起案)**: **① 陳腐化した固定テスト件数を除去**(「正負テスト 103 件」— 実測は 652。設計書 8.3「固定件数は腐るため書かない」への追随。設計書 13 章の同じ「103件」は 2026-08-16 に除去済みで本書が取り残されていた — 台帳 H-79 の実例)+ **射程の是正**(`tests/` のうち hooks は `test_hooks.py` のみで残りは `scripts/` の検査)+ **動作確認章を CI harness ジョブの現行へ追随**(`ruff check`・`ty check` を追加)。**② 受入プロファイル(要件書 NFR-021)との整合**: 受入保証対象を **`Ubuntu-26.04`(番号付き x64 WSL イメージ)に固定**(既定名 `Ubuntu` は別識別子のため対象外)/ **新規ディストリビューションの作成手順**を追加 / **Docker Desktop への言及を除去**し WSL 内 Docker Engine 一本へ(同書は事前導入を前提としない)/ 用語を「標準」「必須」の混在から**「受入保証対象」へ統一** / Node・Python の版表記を `mise.toml`・`backend/pyproject.toml` の実体へ(**版は直書きせずリポジトリを正として参照**)。**③ 本文の完成**(設計書 13 章が approved 化の要件とする「実際の依存導入・DB 初期化・起動・疎通確認まで」): **6 章に依存の導入と検証**(NFR-021 の合格項目と CI 相当の品質検査を**別節に書き分け**)、**7 章に開発 DB と起動疎通**(環境変数の区分・`docker compose up -d --wait`・コンテナ内での接続確認・backend/frontend の起動疎通と終了手順)を新設。これにより **Phase 4 の合格 5 項目すべてに対応する手順**が揃った(従来は 4 項目が完走不可)。**確定ゲート 1 周目の反映(P0×3・P1×5 を全件採用・不採用 0 件)**: **P0-1 導入手順が一切なかった** — 前提ツール表は確認方法だけで Git・gh・uv・Docker・mise・Claude Code・Codex の導入コマンドが無く、`git clone` すら書かずに「リポジトリ直下で `mise install`」を要求していて**順序が成立していなかった**。**0〜3 章を書き直し**(ホスト側の WSL 準備 → 基礎パッケージと単体ツール → リポジトリ取得 → Node・pnpm・Claude Code)、公式手順を典拠に導入コマンドを明記した。**P0-2 WSL 本体の準備が無かった** — `wsl --version`・`wsl --update`・`--set-default-version`・`VERSION=1` からの変換・初回起動のユーザー作成・`wsl -d` での入り方を追加。**P0-3 Python の版が要求と食い違っていた** — Ubuntu 26.04 の `python3` は **3.14 系**で `python-is-python3` は `/usr/bin/python` の symlink を作るだけなので、従来の案内では backend の `>=3.12,<3.13` を満たせなかった。**hooks(`/usr/bin/python3` 絶対パス)・codex ラッパー(PATH の `python`)・backend(uv が `.python-version` から自動取得)の 3 つの役割を分離**して記述した(**uv が自動でダウンロードするためシステムへ 3.12 を入れる必要はない**)。**P1**: `/setup-dev` の守備範囲を実体へ / ガード確認は **Claude Code のセッション内で行う**ことと合否の見方を明記 / 起動疎通に**待機と上限**を入れ**合否は `curl` の終了コードで判定**(サーバーは `Ctrl-C` で止めるため終了コードを用いない)/ 「この 3 つだけ」を実体の 2 項目へ是正し**合格項目の定義は要件書を正として複製しない** / **固定版の切替 3 条件の複製を除去**(要件書 NFR-021 が正 — 7.1-1)/ **bubblewrap は同梱 helper に頼らず明示導入**(OpenAI 公式が Linux/WSL2 でパッケージ導入を案内)/ **`pnpm --version` は `frontend/` で実行**(corepack は最も近い `package.json` を読む)。**版・件数は本文へ直書きせず**リポジトリの定義を正として参照する。調査の典拠は `docs/features/onboarding-approval/research.md`。**確定ゲート 2 周目の反映(P0×1・P1×7 を全件採用・不採用 0 件)**: **P0 Docker の導入手順が公式へのリンクだけだった** — 公式には apt / 手動 / スクリプトの複数経路があり一意でなく、**外部ページの変更は `onboarding_blob_sha` に含まれないため証跡が手順を固定できない**。**apt リポジトリ方式 1 つに固定して本文へ収めた**(daemon 起動の分岐も検出付きで明記)。**P1**: ① WSL の順序を是正(`wsl --install` はそのまま Linux セッションへ入るため、**ユーザー作成 → `exit` → PowerShell で VERSION 確認 → 最後に `wsl -d`** へ分離)+ **`wsl` は WSL の中からは見えないことがある**旨を追記(実測)/ ② **Notion MCP の前提を明記**(`/setup-dev` は `get-users` を使うため未接続だと完了できない。リポジトリに MCP 設定は置かない)/ ③ **git の author 設定**を追加(`gh auth login` はこれを代替しない)/ ④ 6 章を**実行主体つきの表**へ改め、**ガード確認を決定的にした**(変更が無いと Git 自身の「nothing to commit」で止まり、**ガードが壊れていても合格に見える** — 変更を作り、事前/事後の SHA 一致とガード固有の拒否メッセージを合格条件にした)/ ⑤ Python の説明を「2 つ」→**3 つ**へ是正し、**「PATH の `python` が壊れると hooks 全体が fail-open」という注記の射程を訂正**(hooks は全て `/usr/bin/python3` 絶対起動になっており、現在影響するのは codex ラッパーだけ)/ ⑥ **実装値の複製を除去**(backend の版制約・ディストリの Python 系列・環境変数の一覧と分類 → `backend/pyproject.toml`・`.python-version`・`.env.example`・`docker-compose.yml` を正として参照)/ ⑦ frontend の起動待機を **`&&` で連結**(分けると待機が時間切れでも直後の確認が 0 になり**合格に見える**)。**確定ゲート 3 周目の反映(P0×1・P1×3 を全件採用・不採用 0 件)**: **P0 clone 後に `develop` へ切り替えていなかった** — リモートの既定ブランチは `main` で、**`main` には `mise.toml`・`backend/`・`frontend/`・`docker-compose.yml` がまだ無い**(実測)。切り替えずに進むと次章の `mise install` で止まり、**合格 5 項目のどれにも到達できなかった**。`git switch develop` と確認を 2 章へ追加した。**P1**: ① ガード確認がまだ決定的でなかった — `/tmp` 配下は**ワークツリー外**で `git add` の対象にならず、また **git_guard は Bash 実行の前に現在ブランチを判定する**ためブランチ切替と `commit` を 1 回にまとめると基準がずれる。**ワークツリー内に変更を作り、1 行ずつ別々に実行させる**形へ是正 / ② **Notion MCP の追加コマンドを具体化**(`claude mcp add --transport http notion https://mcp.notion.com/mcp` → `/mcp` で OAuth。公式で確認)/ ③ **章を順に実行したときの cwd 遷移**が成立していなかった(`cd backend` が持続し frontend 側に `cd ../frontend` が無い等)。**すべてのコードブロックを subshell に閉じ、リポジトリ直下からの実行に統一**した。**確定ゲート 4 周目の反映(P0 なし・P1×3 を全件採用・不採用 0 件)**: ① **Ubuntu for WSL の初回導入では Ubuntu Insights の収集可否を尋ねる対話も出る**ため、初回対話の説明へ追記(選択は任意で以降に影響しない)/ ② **4〜6 章の前提を明示** — `claude doctor` は診断だけで認証もセッション開始もしない。**リポジトリ直下で `claude` を起動して初回認証する**こと、**hooks はセッションの起動場所で決まる**(リポジトリ外から起動すると 6 章のガード確認にならない)こと、`claude mcp add` は **WSL のシェル**で実行することを追記。Codex も対話セッションが続くため、サインイン後に終了して次へ進む境界を明記 / ③ **DB 疎通の射程を注記**(承認済み計画 4 節の指定の実装漏れ)— 8-2 の確認は **DB コンテナへ直接つないだもの**で backend 経由ではない。backend は `DATABASE_URL` を参照せず `/health` も DB に依存しないため、**「DB へ接続」と「backend が起動して疎通」は独立した 2 項目**であり、本手順は backend から DB まで疎通した証跡にはならない。**4 周目で 3 周目の指摘 4 件すべてが閉鎖**(develop 切替・git_guard の決定性・Notion MCP・cwd/subshell)。**確定ゲート 5 周目の反映(P0 なし・P1×3 を全件採用・不採用 0 件)**: ① **ガード確認が確定対象ではなく旧版を試していた** — hooks は**ワークツリー上のファイル**を実行するため、`git switch main` した時点で `git_guard.py` も `main` 版に入れ替わる(実測: blob が別物で 469 行追加・68 行削除の差)。拒否されても**確定しようとしている `develop` 版の証跡にならない**。`PROTECTED` は `main` と `develop` の両方なので、**切り替えず `develop` のまま確認する**形へ是正 / ② **Claude Code の初回起動には「リポジトリを信頼する」選択がある**。承認しないとプロジェクト設定と hooks が読み込まれず、4〜6 章の前提が成立しないため追記 / ③ **corepack の初回取得には承認入力がある**(新規環境はキャッシュが無い)。拒否すると 3 章で止まり frontend の Vitest へ到達できないため、承認することと合格条件(終了コード 0・表示版が `packageManager` と一致)を追記。**実機通しの反映(2026-08-25 — 新規 `Ubuntu-26.04` で 0〜8 章を通し、合格 5 項目すべてに到達して完走。差分 15 件)**: **本文の誤り** — `newgrp` は Ubuntu 26.04 の WSL イメージに存在せず(`util-linux-extra` に分離)手順が動かなかったため**シェルの開き直しを唯一の手順**へ / `~/.codex/config.toml` は新規環境に無いので**「追記」ではなく「作成」** / **Ubuntu Insights の同意画面は出なかった**ため「環境によっては出る」へ弱めた / Codex のインストーラが `Start Codex now?` と聞くため**手順の二重を解消** / **`claude mcp add` は不要**だった(claude.ai のコネクタとしてサインインだけで接続済み)ため「未接続の場合のみ」へ / `/setup-dev` は `uv run pytest tests/`・`notion-map.json` の実 DB 突合・WSL 版確認まで行うため**守備範囲を実体へ**。**私が書いた注記の誤り** — `wsl` が WSL 内で見つからないのは `appendWindowsPath` ではなく**実行ファイル名が `wsl.exe` である**ため(`wsl.exe --version` は通る)/ **`wsl --update` は実際には更新していなかった**ため無条件必須から**条件付き**へ。**手順の不足** — `wsl -d` で入ると `/mnt/c/...` に降りるため**入り直すたび `cd ~` が要る**(本文が自ら非推奨とする場所に立つ導線だった)/ `gh auth login` の**対話 4 問**と**ブラウザが開けないのが既定**であること / 8-3 は**シェルを 3 枚**使うこと / backend の `curl` 出力に改行が無いこと。**実測で裏付けられ変更しなかった設計**: uv が `.python-version` を読んで `cpython-3.12.3` を自動取得し(ディストリの python3 は 3.14.4)backend が 3.12.3 で動くこと / `git switch develop` / ガード確認の決定性(`develop` のまま・1 行ずつ・ワークツリー内の変更で、拒否メッセージと SHA 不変を確認)/ corepack の取得確認 / Claude Code の信頼確認 / コンテナ内での変数展開。**確定ゲート 6 周目の反映(P0 なし・P1×5 を全件採用・不採用 0 件)**: **うち 3 件は実機通しの反映で新たに入れた欠陥だった** — ① **`echo` を別行にしたため待機の失敗コードが 0 に上書きされていた**(実測: 分けると `0`・`&&` で連結すると `124`)。**5 周目 P1-7 で frontend 側に同じ指摘を受けて直した罠を、backend 側で作り直していた**(H-79 の再発)/ ② **`wsl --update` の条件判定を `wsl --install` より後に置いていた** — まさに分岐が必要な古い WSL では回復手順を読む前に install が失敗する。判定と再確認を install の前へ移した / ③ **Docker 後の入り直し先を `cd ~/dev` と書いたが、`~/dev` を作るのは後続の 2 章**で新規環境には存在しない。0 章の規則どおり `cd ~` へ是正。残る 2 件 — ④ `/setup-dev` の守備範囲に **WSL2 であることの確認**が欠けていた / ⑤ **ガード確認の範囲を明記**した(hooks は 4 本あるが、項目 3 の pytest が全ガードのロジックを単体検査し、項目 5・6 は**安全に実施できる代表的な 2 経路**の実地確認である。**`secret_guard`・`protect_paths` の実配線までは本章では証明しない** — 実地の負例はガードが壊れていた場合に秘密の読み取りや禁止パスへの書き込みを実際に行ってしまうため)。**確定ゲート 7 周目の反映(P0 なし・P1×2 を全件採用・不採用 0 件)**: ① **待機の失敗が上書きされる経路が DB に残っていた** — 6 周目 P1-1 を backend・frontend では閉じたが、**`docker compose up --wait` も待機である**ことを見落としていた。`--wait` が失敗しても後から DB が起動すれば次の `psql` が成功し、最後の終了コードだけを見ると合格に見える。**`&&` で連結**した。**「`timeout` を含む行」で探したため同じ概念の別表現(`--wait`)が漏れた** — H-79 を潰そうとした検索そのもので H-79 を踏んだ / ② **6 周目で足した保証範囲の追記が、新しい 7.1-1 違反だった** — 「hooks は 4 本(…)」という**固定列挙**は `.claude/settings.json` と設計書 8.3 の複製であり、ガードの増減で腐る。**ガード構成の正を参照する形へ改め、本書では列挙しない**。**本タスクは一貫して固定件数の除去を進めてきたのに、保証範囲を書くときに自ら新しい固定件数を作っていた**。計画: `docs/features/onboarding-approval/plan.md` | in-review |
| 1.0 | 2026-08-25 | **確定ゲート通過(approved)**: 敵対レビュー **8 周**(sol xhigh — 1 周目 P0×3/P1×5・2 周目 P0×1/P1×7・3 周目 P0×1/P1×3・4 周目 P1×3・5 周目 P1×3・6 周目 P1×5・7 周目 P1×2・**8 周目で収束**)+ **実機通し 1 回**(2026-08-25 — PO が新規 `Ubuntu-26.04` を作成し 0〜8 章を通し、**合格 5 項目すべてに到達して完走**。採取 15 件)。**P0×5・P1×28・実機 15 件をすべて採用し、不採用 0 件**。P0 は 1〜3 周目に集中し(導入手順の欠落・WSL 本体の準備の欠落・Python の版の食い違い)、**4 周目以降は P0 なし**。6〜7 周目の指摘は**すべて「直前の周の反映が新たに入れた欠陥・閉じきらなかった反映」**で、8 周目にその再発も止まった。**待機の失敗コードが後続コマンドで上書きされる罠**(`&&` 連結)と**別正本を複製する固定件数・固定列挙**(7.1-1)が、本書で最も繰り返し現れた 2 系統。本版により **Phase 4 完了時受入(NFR-021)の合格 5 項目すべてに到達する手順**が揃い、実機で完走が確認された(従来は 4 項目が完走不可)。**受入プロファイルの arm64 / x64 の不整合は本ゲートの対象外**とし、要件書 NFR-021 の改訂として別タスクで扱う(PO 裁定)。承認: 2026-08-25・山田正輝。計画: `docs/features/onboarding-approval/plan.md` | **approved** |
| 1.1 | 2026-08-26 | **2 章へ「NFR-021 の受入判定を実施する場合」の節を新設(起案 — Phase 4-6)**: 受入判定では `develop` の先端ではなく**判定対象の候補コミット**を試験するため、**feature ブランチを明示 fetch し、ローカル `develop` を候補コミットの位置へ作り直して切り替える**手順を本文へ組み込んだ。**既存の不整合の解消である** — 本章は `develop` への切り替えを要求する一方、受入証跡の運用(`docs/ops/nfr021-acceptance/README.md`)は「**予約を含む候補ツリー**で完走」と定めており、両者は一般に一致しない。**手順を持たないままでは、受入の実施者が本書を逐語どおり実行できず、要件書 NFR-021 の測定方法が課す『approved な本書の手順を完走』という Must を満たせなかった**(確定ゲート 1 周目 P0 — 判定者に合否判断権はあっても approved 手順の変更権・Must の免除権は無い)。**ブランチ名を `develop` に保つことを必須とし理由も明記**した — 6 章 項目 5 は `develop` 上で git_guard が拒否することを合格条件とするが、同ガードは現在ブランチを `git rev-parse --abbrev-ref HEAD` で判定するため、**detached HEAD では文字列 `HEAD` が返り保護ブランチとも解決不能とも判定されずガードが発火しない**(実装で確認)。**受入判定以外の通常のセットアップでは本節を実行しない**ことと、`git switch -C` の影響がローカル `develop` に限られることも明記した。計画: `docs/features/phase4-6-acceptance/plan.md` | in-review |
| **1.1** | 2026-08-26 | **確定ゲート通過(approved)**: 設計書 v1.10・受入証跡 README v1.2 と**同一ゲート**(敵対レビュー 5 周・全件採用・不採用 0 件)→ **PO 承認(2026-08-26・山田正輝)**。**確定内容**: 2 章へ 2-1 節を新設し、受入判定時は**候補コミットの完全 40 桁 OID で固定して取得する**手順を本文へ組み込んだ(feature ブランチを明示 fetch → ローカル `develop` を候補コミットの位置へ作り直す)。**ブランチ名を `develop` に保つことを必須とした** — detached HEAD では git_guard が保護ブランチとして判定せず **6 章 項目 5 の負例試験が成立しない**(実装で確認)。**受入判定以外の通常セットアップでは 2-1 を実行しない**。**0〜8 章の手順そのもの・合格項目・実施主体は変更していない**。計画: `docs/features/phase4-6-acceptance/plan.md` | **approved** |
| 1.2 | 2026-08-27 | **受入プロファイルの複製を解消し、アーキテクチャの採取手順を新設**(前提 PR 第 3 号): 0 章の「番号付き **x64** WSL イメージ」を**要件書 NFR-021 への参照へ寄せた**(要件の複製であり、同要件の x64 / arm64 両対応化で approved 正本間の矛盾になるため)/ **2-2 節「アーキテクチャの採取」を新設** — `host` / `wsl_uname` / `wsl_dpkg` の 3 値の採取コマンド・正規化の対応表・生出力と正規化結果の両方をログへ残す規定・**欠落/表外の値/3 値の不一致を不適合とする判定**(要件書 v2.3 が証跡のログ参照欄にアーキテクチャの識別を要求したことへの追随)（**確定ゲート 1 周目の反映**: 2 章冒頭に通常セットアップと受入判定の分岐を明示し、2-1 節末尾が 2-2 節を飛ばしていた導線を是正 / 2-2 節を**実行可能な単一ブロック**へ〔3 値の採取・`case` による正規化・6 ラベルの固定書式出力・終了コードの記録・不適合で非 0 終了〕/ 出力先を `docs/worklog/acceptance-arch.log`(**リポジトリ内**・受入証跡と同じコミットに含める)へ / **arm64 実機で正常系と不適合 3 系統を実測**）（**確定ゲート 2 周目の反映**: `cmd.exe` の終了コードを**パイプを挟まずに捕捉**（`| tr` を挟むと非 0 終了を 0 と読む）/ ブロックを**サブシェル**にして `errexit` を呼び出し元へ残さない / **固定パスのログを廃止**し 6 ラベルを**証跡本文へ直接記載**する形へ（参照先ファイルは後続試行で上書きされうる）/ 「実施した arch のみ保証」の根拠として **apt ソースの arch 依存分岐**を明記 / **非 0 終了する `cmd.exe` 代替**を含む不適合 4 系統を実測）（**確定ゲート 3 周目の反映**: 証跡セルへ貼る形式を **`; ` 区切りの 1 物理行**に固定し、ブロックがその 1 行を明示出力する形へ（Markdown 表の 1 セルに改行を入れると⑩の表抽出が打ち切られる。`<br>` はプレースホルダ検査に掛かる））（**確定ゲート 4 周目の反映**: 「1 行」と「1 物理行」の表記ゆれを**「1 物理行」へ逐語統一**し、要件書・受入証跡 README と同一表現に揃えた） | **draft**(確定ゲート中) |
| **1.2** | 2026-08-27 | **確定ゲート通過(approved)**: 敵対レビュー **9 周**(sol xhigh — 1 周目 P0×1/P1×5/P2×2・2 周目 P0×1/P1×4/P2×1・3 周目 P0×1/P1×3/P2×1・4 周目 P1×4/P2×2・5 周目 P0×2/P1×1/P2×2・6 周目 P0×1/P1×1・7 周目 P0×1/P1×1・8 周目 P0×1/P1×1/P2×1・9 周目 P0×1/P1×1/P2×1 を**全件採用・不採用 0 件**)。**5〜9 周目の P0 はいずれも「判定」と「正式受入の成立」の混同が根**で、9 周目に別名を含む一括同期で収束させた(経緯は台帳 H-79 の 5 件目)。**PO 判断 2026-08-27 で 9 周をもって確定ゲートを閉じた**。計画: `docs/features/nfr021-profile-arm64/plan.md`(計画レビュー 4 周 → 承認 2026-08-27・山田正輝) | **approved** |
| 1.2 | 2026-09-21 | **ブランチ保護の適用への追随(版は上げない — 設計書 7.6-3 前段の実装追随)**(TSK-429): 2 章の「GitHub 側のブランチ保護は現在未適用(プラン制約)」を現況へ。**2026-09-19 に適用済み**で直接 push・force push・ブランチ削除はリモートで拒否される(管理者にも適用)。あわせて**所有者は Ruleset の設定自体を変更できる**という限界と、**2 章の手続 3・4(コア領域 ∪ guard_paths の人間逐行確認)は継続する**ことを明記した(保護は検査ロジック自体の改変を防げないため)。 | **approved** |

pitchlog の開発に参加する開発者の初期設定手順。**開発環境は Windows 11 上の WSL2 で完結する。受入保証対象は WSL2 のみ**(Windows ネイティブでの開発は保証対象外 — 受入条件の正は要件書 NFR-021)。

**本書は「WSL2 を有効化しただけの Windows 11」から出発して 8 章まで到達できる形で書く。** 前提として求めるのは WSL2 の有効化だけで、その他のツールはすべて本書の手順内で導入する(要件書 NFR-021 の受入プロファイル)。

> `/setup-dev` は **ツールの疎通確認・WSL2 であることの確認・4 章(Codex の設定)の確認・5 章(Notion 紐づけ)・`.claude/notion-map.json` と実 DB の突合・permissions 構文検証の案内**を対話で進め、**6 章の項目 3(`uv run pytest tests/`)も実行する**。**ツールの導入そのもの・6 章のガード実地確認・7〜8 章は行わない。**

## 0. WSL2 環境の用意(Windows ホスト側)

**受入保証対象のディストリビューションは `Ubuntu-26.04` の番号付き WSL イメージに固定する。** 既定名 `Ubuntu` は WSL 上で**別の識別子**として扱われ、安定版 LTS を自動追随するため保証対象としない。他ディストリビューション・他版も保証対象外。**イメージのアーキテクチャはホストに対応するものを使う**(`wsl --install -d Ubuntu-26.04` はホストのアーキテクチャに応じたイメージを取得する)。**保証対象のアーキテクチャの範囲・切替規則・1 回の受入で一意化する単位は、いずれも要件書 NFR-021 の受入プロファイルが正** — 本書では規定しない(v1.2: 従来ここに「番号付き x64 WSL イメージ」と書いていたが、**要件の複製であり同要件の改訂で矛盾する**ため参照へ寄せた)。

**この章は Windows の PowerShell(管理者)で実行する。** `wsl` は Windows 側のコマンドなので、**WSL のシェルの中から呼ぶときは `wsl.exe` と拡張子まで書く**(拡張子なしの `wsl` は見つからない — 実測 2026-08-25)。

**① WSL 本体を整えて、ディストリを作る**(PowerShell):

**まず前提を確認する**:

```powershell
wsl --version                    # 版が表示されるか
wsl --list --online              # `Ubuntu-26.04` が一覧にあるか
```

> **どちらかが満たされない場合のみ `wsl --update` を実行する**(版が表示されない = WSL 本体が古い / 一覧に `Ubuntu-26.04` が無い)。**数分かかることがあり、完了してもプロンプトが戻るだけで版が上がらない場合もある**(実測 2026-08-25)。実行したら**上の 2 つを再確認してから**次へ進む。両方満たされていれば `--update` は**不要**。

**ディストリを作る**:

```powershell
wsl --set-default-version 2      # 新規ディストリを WSL2 で作る
wsl --install -d Ubuntu-26.04    # 番号付きイメージを指定する(`Ubuntu` ではない)
```

**② 初回起動で Linux のユーザー名とパスワードを対話的に作成する。** `wsl --install` はそのまま Linux セッションへ入る。環境によっては Ubuntu Insights のデータ収集に同意するかの選択も出る(任意 — どちらを選んでも以降の手順に影響しない。**2026-08-25 の実測では出なかった**)。初期設定が済んだら **`exit` で PowerShell へ戻る**。作成したアカウントがそのディストリの既定ユーザーになる。

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

```bash
cd ~
pwd                              # /home/<ユーザー名> であること
```

> **必ず `cd ~` する。** PowerShell から入ると `/mnt/c/...` に降りるため、そのまま作業すると下記の「WSL 側ファイルシステムに置く」に反する。**入り直すたびに必要**。

> `wsl: Failed to start the systemd user session for '<ユーザー名>'` という警告が出ることがあるが、**システム側の systemd は動いており以降の手順に影響しない**(`ls -d /run/systemd/system` で確認できる — 実測 2026-08-25)。

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
gh auth login
gh auth status
```

> **`gh auth login` は 4 つ質問する。** GitHub.com / **HTTPS** / Git 認証を委ねる **Yes** / **Login with a web browser** を選ぶ。**WSL からブラウザは開けない**(`wslview` 等が無く `Failed opening a web browser` が出る)ので、**表示されたワンタイムコードを控え、Windows 側のブラウザで `https://github.com/login/device` を開いて入力する**。

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
```

**ここでいったんシェルを開き直す**(`exit` して PowerShell から `wsl -d Ubuntu-26.04` で入り直し、**`cd ~`** で戻る — 0 章の規則どおり)。**`newgrp` は使わない** — Ubuntu 26.04 の WSL イメージには含まれていない(`util-linux-extra` に分離。実測 2026-08-25)。

入り直したら:

```bash
id -nG                           # `docker` が含まれること
docker compose version
docker run --rm hello-world
```

**1-6. Codex CLI**

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
```

インストーラが **`Start Codex now? [y/N]`** と聞くので `y` で起動し、**初回のサインインを完了する**(別途 `codex` を叩く必要はない)。終了後:

```bash
codex --version
```

## 2. リポジトリ取得

> **分岐はここで一度だけ示す**: **通常のセットアップ**は本章の手順を実行して 3 章へ進む(2-1・2-2 は不要)。**NFR-021 の受入判定を実施する場合**は本章 → **2-1**(候補コミットの固定)→ **2-2**(アーキテクチャの採取)→ 3 章の順に実行する。

```bash
mkdir -p ~/dev && cd ~/dev
gh repo clone masaki1025/pitchlog
cd pitchlog
git switch develop
git branch --show-current        # `develop` であること
```

> **必ず `develop` へ切り替える。** リモートの既定ブランチは `main` なので、clone 直後は `main` が checkout される。**`main` には `mise.toml`・`backend/`・`frontend/`・`docker-compose.yml` がまだ無い**ため、切り替えずに進むと次章の `mise install` で止まり、以降の合格項目へ到達できない。

### 2-1. NFR-021 の受入判定を実施する場合(v1.1)

**受入判定では `develop` の先端ではなく「判定対象の候補コミット」を試験する。** 受入証跡の運用([README](../ops/nfr021-acceptance/README.md))が「**予約を含む候補ツリー**で本章以降の手順を完走する」と定めており、候補ツリーは `develop` の先端と一般には一致しない(受入を実施する PR 上で作られるため)。**受入判定以外の通常のセットアップでは本節を実行しない。**

上の `git switch develop` の代わりに、**候補コミットの完全な小文字 40 桁 commit OID**(受入の実施者から渡される)を用いて次を行う。

```bash
git fetch origin <候補コミットを含むブランチ名>
git switch -C develop <候補コミットの完全 40 桁 OID>
git branch --show-current        # `develop` であること
git rev-parse HEAD               # 候補コミットの OID と完全一致すること
```

> **ブランチ名を `develop` のままにするのは必須。** 6 章 項目 5 は **`develop` 上で git_guard が拒否すること**を合格条件とするが、git_guard は現在ブランチを `git rev-parse --abbrev-ref HEAD` で判定するため、**detached HEAD では文字列 `HEAD` が返り、保護ブランチとも解決不能とも判定されずガードが発火しない**。detached checkout で進めると**当該項目が成立しない**。
>
> `git switch -C` が書き換えるのは**この clone のローカル `develop` だけ**であり、`origin/develop` には影響しない。受入は新規環境で行うため、既存の作業を壊すことはない。

**受入判定を実施する場合は、続けて 2-2 節(アーキテクチャの採取)を実行してから 3 章へ進む。** 通常のセットアップでは 2-1・2-2 を飛ばして 3 章へ進む。

`develop` が統合先。main/develop への直接コミットは hooks(Claude Code 経由の操作)で拒否される(作業は必ず /task-start から)。**GitHub 側のブランチ保護は 2026-09-19 に適用済み**(正は [github-setup.md](github-setup.md) 3 章)。直接 push・force push・ブランチ削除は**設定上はリモートで拒否される**(管理者にも適用)(**設定上は拒否される — API 実測で Ruleset は `active`。ただし拒否動作そのものの実測は未実施**。`gh ruleset check` は適用対象の列挙にすぎず拒否を実証しない → `TSK-433`)。ただし**所有者は Ruleset の設定自体を変更できる**ため、保護は所有者からも逃れられる統制ではない。**同 2 章の管理手続のうち手続 3・4(コア領域 ∪ guard_paths の人間逐行確認)は継続**する — 保護は検査ロジック自体の改変を防げないため。

### 2-2. アーキテクチャの採取(受入判定を実施する場合・v1.2)

**要件書 NFR-021 は、証跡の「標準出力またはログ成果物への参照」欄に、6 ラベルの実値を **`; ` 区切りの 1 物理行**として証跡本文へ直接記載することを要求する**(実施したアーキテクチャの識別)。本節はその 1 物理行を作る手順である(**受入判定を実施する場合のみ必須**。通常のセットアップでは省略してよい)。

> **なぜ必要か**: 受入保証の範囲は**受入を実施したアーキテクチャに限る**(要件書 NFR-021)。本書の手順は 1-3 章の GitHub CLI・Docker の apt ソースで `dpkg --print-architecture` により分岐するため、**未実施のアーキテクチャの完走可能性は担保されない**。どの環境で完走したかが証跡から一意に定まる必要がある。

**次のブロックをそのまま実行する**(サブシェルで実行するので `errexit` は呼び出し元に残らない。**不適合なら非 0 で終了する** — その場合は受入を続行しない):

```bash
(
  host_out=$(cmd.exe /C 'echo %PROCESSOR_ARCHITECTURE%' 2>/dev/null); host_rc=$?
  host_raw=${host_out%$'\r'}
  wsl_uname_raw=$(uname -m); uname_rc=$?
  wsl_dpkg_raw=$(dpkg --print-architecture); dpkg_rc=$?

  norm() {
    case "$1" in
      AMD64|x86_64|amd64) echo x64 ;;
      ARM64|aarch64|arm64) echo arm64 ;;
      *) echo UNKNOWN ;;
    esac
  }
  host=$(norm "$host_raw"); wsl_uname=$(norm "$wsl_uname_raw"); wsl_dpkg=$(norm "$wsl_dpkg_raw")

  printf '証跡セルへ貼る 1 物理行: host_raw=%s; host=%s; wsl_uname_raw=%s; wsl_uname=%s; wsl_dpkg_raw=%s; wsl_dpkg=%s\n' \
    "$host_raw" "$host" "$wsl_uname_raw" "$wsl_uname" "$wsl_dpkg_raw" "$wsl_dpkg"

  fail=0
  [ "$host_rc" -eq 0 ] && [ -n "$host_raw" ] || { echo "不適合: host を採取できない(rc=$host_rc)" >&2; fail=1; }
  [ "$uname_rc" -eq 0 ] && [ -n "$wsl_uname_raw" ] || { echo "不適合: wsl_uname を採取できない(rc=$uname_rc)" >&2; fail=1; }
  [ "$dpkg_rc" -eq 0 ] && [ -n "$wsl_dpkg_raw" ] || { echo "不適合: wsl_dpkg を採取できない(rc=$dpkg_rc)" >&2; fail=1; }
  case "$host$wsl_uname$wsl_dpkg" in *UNKNOWN*) echo "不適合: 許容表にない生出力がある" >&2; fail=1 ;; esac
  [ "$host" = "$wsl_uname" ] && [ "$wsl_uname" = "$wsl_dpkg" ] || { echo "不適合: 3 値の正規化結果が一致しない" >&2; fail=1; }
  [ "$fail" -eq 0 ] || { echo "受入を続行しない(要件書 NFR-021 の受入プロファイル外)" >&2; exit 1; }
  echo "適合: arch=$host"
)
```

**`cmd.exe` の終了コードはパイプを挟まずに捕捉する**(`| tr` を挟むとパイプライン全体の終了状態になり、`cmd.exe` が非 0 で終わっても 0 と読めてしまう)。CR の除去はシェルのパラメータ展開で行う。

**正規化の対応表**(この表に無い生出力は `UNKNOWN` になり不適合):

| 正規化後 | 許容する生出力 |
| --- | --- |
| `x64` | `AMD64`(Windows) / `x86_64`(`uname -m`) / `amd64`(`dpkg`) |
| `arm64` | `ARM64`(Windows) / `aarch64`(`uname -m`) / `arm64`(`dpkg`) |

**不適合の判定**(いずれかに該当したら上記ブロックが非 0 で終了する):

1. 3 値のいずれかが**採取できない**(コマンドが非 0 終了・出力が空)
2. いずれかの生出力が**許容表のどの行にも一致しない**(`UNKNOWN`)
3. **`host` / `wsl_uname` / `wsl_dpkg` の正規化結果が 3 値そろって一致しない**(WSL2 はホストと同一アーキテクチャの VM で動くため、不一致は環境の異常を意味する)

**出力された「証跡セルへ貼る 1 物理行」の `host_raw=…; wsl_dpkg=…` の部分を、結果証跡の「標準出力またはログ成果物への参照」欄へそのまま記載する。** **6 ラベルの実値を、`; ` 区切りの 1 物理行として証跡本文へ直接記載する** — **当該欄は Markdown 表の 1 セル**であり、**改行を含めると検証器の表抽出がそこで打ち切られ、当該欄と後続の「判定者」欄が完全性検査(⑩)で欠落扱いになる**(確定ゲート 3 周目 P0 で実測)。**`<br>` も使わない** — プレースホルダ正規表現 `<...>` に一致して拒否される。別ファイルへの参照だけにもしない — **証跡本文は改変禁止・append-only の保護下にあるが、参照先のファイルは後続の試行で上書きされうる**ため(要件書 NFR-021)。

**本ブロックは arm64 実機で実測済み**(2026-08-27): 正常系は `host_raw=ARM64` / `wsl_uname_raw=aarch64` / `wsl_dpkg_raw=arm64` → 3 値とも `arm64` に正規化され `適合: arch=arm64`・終了コード 0。不適合 3 系統(採取できない / 許容表にない値 / 3 値の不一致)と、**既知の値を出力しつつ非 0 終了する `cmd.exe` 代替**はいずれも**終了コード 1**。

## 3. Node・pnpm・Claude Code(リポジトリ取得後)

Node の版は `mise.toml` が正なので、**リポジトリ直下で**解決させる。

```bash
mise install                     # リポジトリ直下で実行(mise.toml を読む)
node --version                   # mise.toml の固定版と一致すること
corepack enable
(cd frontend && pnpm --version)  # frontend/ で実行する(理由は下記)
                                 # 初回は pnpm の取得確認が出るので承認する
```

> **初回は corepack が pnpm を取得する。** キャッシュが無い新規環境では TTY 上で取得確認が出るので**承認する**(拒否すると本章で止まり frontend の Vitest へ到達できない)。合格条件は**終了コード 0** かつ**表示された版が `packageManager` と一致**すること。

> **`pnpm --version` は `frontend/` で実行する。** corepack は**起点から親へ遡って最も近い `package.json`** の `packageManager` を読む。リポジトリ直下に `package.json` は無く、`frontend/package.json` にだけ指定があるため、直下で実行すると意図した版が選ばれる保証がない。

Claude Code は Node が入ってから導入する(`sudo npm` は使わない)。

```bash
npm install -g @anthropic-ai/claude-code
claude doctor                    # 導入状態の確認
```

> **以降 4〜6 章は「リポジトリ直下で起動した Claude Code のセッション」を前提とする。**
> - **リポジトリ直下で** `claude` を実行する。初回は **表示されたパスがリポジトリ直下であることを確認して「信頼する」を選び**、続けて**ブラウザ認証を完了する**(信頼しないとプロジェクト設定と hooks が読み込まれない)
> - プロジェクトの hooks はセッションの起動場所で決まる。**リポジトリ外から起動すると 6 章のガード確認にならない**
> - 5 章の `claude mcp add` は **WSL のシェル**で実行する。Claude Code のセッション内からではなく、別のシェルを開くか、いったん終了してから実行してセッションを開き直す

## 4. Codex の設定(個人・必須)

`~/.codex/config.toml` に書く。**新規環境には同ファイルが無い**ので作成する(実測 2026-08-25)。既にある場合は追記する。

```toml
# このリポジトリを信頼する(プロジェクト設定 .codex/config.toml を読み込むため)
[projects."<このリポジトリの WSL 上の絶対パス>"]
trust_level = "trusted"
```

- **既存の config を持っている人向けの注意**: それが `projects = { ... }` の**インライン表形式**なら、その表の中にエントリを追記する(`[projects."..."]` セクションを併記すると TOML の重複定義でパースエラーになる)
- WSL2 では Codex sandbox に Linux 実装(bubblewrap)が自動適用される。`[windows]` セクションは不要
- Codex の起動は `.claude/scripts/codex_run.py` ラッパー経由のみ(生実行は codex_guard がブロック — 設計書 12.1)

## 5. Notion ユーザー紐づけ(個人・必須)

**前提: Claude Code から Notion MCP が使えること。** `/setup-dev` は Notion のユーザー一覧(`get-users`)を取得して候補を提示するため、未接続だとこの章を完了できない。**リポジトリに MCP 設定は置いていない**(個人のアカウント接続)。

1. Claude Code で `/mcp` を実行し、**Notion が接続済み**であることを確認する。**claude.ai のコネクタとして既に接続済みのことが多い**(サインインだけで使える — 実測 2026-08-25)。その場合は 3 へ進む
2. **未接続の場合のみ**追加する(WSL のシェルで):

   ```bash
   claude mcp add --transport http notion https://mcp.notion.com/mcp
   ```

   その後 Claude Code 内で `/mcp` を開き、**OAuth 認証を完了する**
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

> **本章が保証する範囲。** ガード構成の正は `.claude/settings.json`(役割は[ハーネス設計書](dev-harness-design-2026-08-07.md) 8.3)であり、本書では列挙しない。**項目 3 の pytest が各ガードのロジックを単体検査**し、**項目 5・6 は安全に実施できる代表的な 2 経路の実地確認**である。**項目 5・6 以外のガードの実配線は本章では証明しない** — 実地の負例は、ガードが壊れていた場合に**秘密の読み取りや禁止パスへの書き込みを実際に行ってしまう**ため。

| # | 実行主体 | 確認 | 期待 |
| --- | --- | --- | --- |
| 1 | Claude Code | 起動する | SessionStart フックが「現在ブランチ…」を表示する |
| 2 | **Claude Code** | `/permissions` | `.claude/settings.json` のルールが有効に見える(Bash パターン構文が現行仕様か確認) |
| 3 | WSL のシェル | `uv run pytest tests/` | 終了コード 0(hooks・codex ラッパー・`scripts/` の検査に対する正負テスト。**件数は CI の harness ジョブの実行結果を正とする** — 固定件数は腐るため書かない〔[ハーネス設計書](dev-harness-design-2026-08-07.md) 8.3〕) |
| 4 | WSL のシェル | `uv run ruff check .` と `uv run ty check` | いずれも終了コード 0(CI の harness ジョブと同じ検査。**`ruff format` は未導入 — 走らせない**) |
| 5 | **Claude Code** | 下記のガード確認(git_guard) | git_guard 固有の拒否メッセージが出て、**HEAD が動かない** |
| 6 | **Claude Code** | 下記のガード確認(codex_guard) | codex_guard がブロックし、**ラッパー経由の案内**が出る |

**項目 5 の手順**(Claude Code に実行させる)。次の 2 点に注意する。

- **コミットすべき変更が無いと Git 自身の「nothing to commit」で止まり、ガードが壊れていても合格に見える**。**ワークツリー内**に変更を作ってから試す(`/tmp` 配下はワークツリー外なので `git add` の対象にならない)
- **git_guard は Bash 実行の前に現在ブランチを判定する**。ブランチ切り替えと `commit` を**1 回の実行にまとめると判定の基準がずれる**ため、**下記は 1 行ずつ別々に実行させる**
- **`develop` のまま試す。`main` へ切り替えてはいけない。** hooks は**ワークツリー上のファイル**を実行するので、ブランチを切り替えると**そのブランチ版のガードを試すことになる**。`develop` も保護対象なので、切り替えずに確認できる

```bash
git branch --show-current               # ① `develop` であることを確認
git rev-parse HEAD                      # ② 事前 SHA を記録
echo "guard check" > guard-check.tmp    # ③ ワークツリー内に変更を作る
git add guard-check.tmp                 # ④
git commit -m "guard check"             # ⑤ ← git_guard がここで拒否するはず
git rev-parse HEAD                      # ⑥ ② と同じ SHA であること
git restore --staged guard-check.tmp    # ⑦ 後始末
rm -f guard-check.tmp                   # ⑧
```

合格条件: **⑤ で git_guard の拒否メッセージが出る**(Git の「nothing to commit」ではない)**かつ ② と ⑥ の SHA が一致する**。

**項目 6 の手順**(同上): Claude Code に `codex exec "test"` を実行させる。合格条件は **codex_guard がブロックし、`codex_run.py` ラッパー経由の案内が出る**こと。

## 7. 依存の導入と検証(backend / frontend)

6 章まででハーネスは動く。ここから pitchlog 本体の依存を入れる。

### 7-1. NFR-021 の合格項目

**この節で確認するのは backend と frontend の 2 つ**(ハーネスの pytest は 6 章の項目 3)。合格項目の定義は要件書 NFR-021 の測定方法が正であり、本書では複製しない。

**backend**(**リポジトリ直下から**):

**リポジトリ直下から**実行する(以降のコードブロックも同じ。`cd` は subshell に閉じてあるので**カレントディレクトリは移動しない**):

```bash
uv python install                          # .python-version を読む
(cd backend && uv sync --locked --dev && uv run pytest)
```

> ディストリの python3 が要求と違っていても、**uv が `.python-version` の版を自動で取得する**ので別途導入する必要はない。

**frontend**(3 章で `mise install` と `corepack enable` を済ませてから、**リポジトリ直下から**):

```bash
(cd frontend && pnpm install --frozen-lockfile && pnpm test)
```

いずれも**全グリーン**であること。**件数は書かない** — 実行結果を正とする([ハーネス設計書](dev-harness-design-2026-08-07.md) 8.3)。

### 7-2. CI 相当の品質検査

**受入の合格項目ではない**が、PR を出す前に手元で通しておくと CI の往復が減る。CI(`.github/workflows/ci.yml`)の backend / frontend ジョブと同じコマンド列:

**backend**:

```bash
(cd backend && uv run ruff check . && uv run ruff format --check . \
  && uv run ty check && uv run pytest --cov)
```

**frontend**:

```bash
(cd frontend && pnpm exec eslint . && pnpm exec prettier --check . \
  && pnpm exec vue-tsc --noEmit && pnpm test -- --run)
```

> リポジトリルートのハーネス(`scripts/`・`tests/`)は検査の構成が違う — **`ruff format` は未導入なので走らせない**(6 章の項目 4 が正)。

## 8. 開発 DB と起動疎通

### 8-1. 環境変数ファイル

**リポジトリ直下で**、`.env.example` をコピーして `.env` を作る(`.env` は gitignore 済み。**コミットしない・値をログへ出さない** — NFR-014)。

```bash
cp .env.example .env
```

**変数の一覧と既定値は `.env.example` が正**であり、本書では複製しない。**どれが必須かは `docker-compose.yml` が `:?required` で宣言している**ので、`.env.example` をそのままコピーすれば起動に必要なものは揃う。

パスワードを変えたときは、`.env.example` のコメントに従って関連する値も同時に更新する(URL に含める値は percent-encode する)。

### 8-2. 開発 DB の起動と接続確認

```bash
docker compose up -d --wait --wait-timeout 120 \
  && docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select 1"'
```

- `--wait` が healthcheck の healthy を待つ(`docker compose ps` は待機しない)
- **`&&` で連結する** — 分けて書くと、**`--wait` が失敗しても後から DB が起動すれば `psql` が成功し、最後の終了コードだけを見ると合格に見えてしまう**(8-3 の起動疎通と同じ理由)
- **変数はコンテナ内で展開する**。`.env` は compose の変数展開に使われるだけで**呼び出し元のシェルへは export されない**ため、ホスト側で `$POSTGRES_USER` と書くと空になる
- 期待値: **終了コード 0**・標準出力が **`1`**
- **これは DB コンテナへ直接つないだ確認であり、backend 経由ではない。** backend は現時点で `DATABASE_URL` を参照しておらず(8-1)、`/health` も DB に依存しない。**「DB へ接続」と「backend が起動して疎通」は独立した 2 項目**であり、本手順は backend から DB まで疎通した証跡にはならない

> やり直すときは `docker compose down -v` でボリュームごと消す。`POSTGRES_INITDB_ARGS` は**空の PGDATA の初回だけ**有効で、既存ボリュームには再適用されない。

### 8-3. backend・frontend の起動疎通

**シェルを 3 枚使う**(backend 用・frontend 用・確認用)。サーバーは**それぞれ別のシェルで前景起動**し、確認は 3 枚目から行う。新しいシェルは PowerShell から `wsl -d Ubuntu-26.04` で開き、`cd ~/dev/pitchlog` へ移動する。**合否はサーバーの終了コードではなく `curl` の終了コードで判定する**(サーバーは `Ctrl-C` で止めるため終了コードが非ゼロになりうる)。

**backend**(別のシェルを開き、**リポジトリ直下から**):

```bash
(cd backend && uv run fastapi dev src/pitchlog/main.py --port 8800)
```

起動を待って確認する(最大 30 秒):

```bash
timeout 30 sh -c 'until curl -fsS --max-time 3 http://127.0.0.1:8800/health; do sleep 1; done' && echo
```

期待値: **終了コード 0**・出力が **`{"status":"ok"}`**。**`echo` は `&&` で連結する** — 改行を足すためだが、行を分けると**待機が失敗しても `echo` の成功で終了コードが 0 に上書きされる**。ポート **8800** は frontend の proxy 先(`frontend/vite.config.ts`)に合わせる。

**frontend**(別のシェルを開き、**リポジトリ直下から**):

```bash
(cd frontend && pnpm dev --host 127.0.0.1 --port 5173 --strictPort)
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
