---
feature: dev-db-contracts
status: in-review         # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-08-17・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: 通常            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3bf93b75e68781429f3cdf678adc64ce
branch: feature/dev-db-contracts
created: 2026-08-17
計画レビュー周回: 1        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: Phase 4-3 開発用 PostgreSQL(docker-compose)+ contracts/ 雛形

## 1. 背景・目的

- Notion タスク: [TSK-222 Phase 4-3](https://app.notion.com/p/3bf93b75e68781429f3cdf678adc64ce)(優先度 高・見積 3)
- 設計書 13 章「Phase 4 の分割」の論理スロット **4-3**(`../../development/dev-harness-design-2026-08-07.md` の 13 章)。4-1(frontend 骨格)はマージ済み、**4-2(backend 骨格)とは相互任意**
- 着手前調査: [research.md](research.md)(要件突合・旧システム事実・決定経緯・Web 調査。すべての事実に典拠あり)

やる理由は 2 つ。

**① 開発 DB が存在しない。** [NFR-021](../../requirements/requirements-pitchlog-2026-07-22.md)(開発環境・Must)が「開発DBもPostgreSQLを使用し、WSL2から完結して利用できること(配置方式は設計フェーズで決定する)」を要求し、設計書 5.3 がその配置方式として Docker Compose を採用済み。NFR-021 の「Phase 4完了時」の合格項目に「**開発DBへ接続でき**」が含まれる(判定自体は 4-6 で 1 回)。関連: 改善台帳 [I-6](../../improvements-from-baseball-scoring.md)(SQLite/PostgreSQL 二重運用の廃止 — 「開発と本番で DB が違うと『開発では動くが本番で壊れる』事故が構造的に発生する」)。

**② NFR-018 違反が時限式で仕込まれている。** `frontend/src/lib/display_geometry_263_v1.json` は旧リポではリポジトリ直下の `shared/` にあった frontend/backend 共有ファイルだが、Phase 4-1 の時点で `contracts/` が存在しなかったため暫定で frontend 配下に置かれている。**backend が同じ座標定義を必要とした時点で複製になり、[NFR-018](../../requirements/requirements-pitchlog-2026-07-22.md)(ドメイン計算の単一実装 — 「状況判定・**座標変換**・捕球選手推定・成績集計の前処理・終了判定」を明示列挙)違反 = AGENTS.md の Code Review Rules で P0** になる。典拠は [porting-rules.md](../frontend-skeleton/porting-rules.md) 8 節。

## 2. スコープ

### やること

(番号は 4 節の実装ステップと対応)

1. `contracts/` の新設と `contracts/README.md`(位置づけの明記のみ)
2. CI の frontend ジョブの paths filter へ `contracts/**` を追加(設計書 10.1 への実装追随)
3. `display_geometry_263_v1.json` の `contracts/` への移設、frontend からの参照切り替え、契約を固定する単体テストの追加
4. `docker-compose.yml`(開発用 PostgreSQL)と `.env.example`(接続情報の正本)の新規作成
5. 非正本ドキュメントの追随(`porting-rules.md` の予定記述を完了形へ置換・worklog)

### やらないこと

| 除外するもの | 理由 |
| --- | --- |
| **NFR-018 実現方式 ADR の起票** | 設計書 4 章が「Phase 4 着手前に ADR で確定する」と定めた未履行事項(台帳 H-55)。正本の新設は確定ゲート(/finalize-doc・敵対レビュー + 人間承認)が要り、13 章が 4-3 に与えたマージ条件(通常 PR 要件)では通らない。**別タスクへ送る**(research.md 論点 A の判断 = A-1) |
| **ゴールデンベクタの中身**(付録E マトリクス・付録A 固定ベクタ・付録B-6 領域シード・付録D 88列スキーマ) | 同上。上記 ADR のスコープ。`contracts/README.md` は索引と位置づけに留める |
| **`.claude/core-areas.json` の paths 充填** | paths の追加は敵対レビュー + 人間承認の対象(設計書 6.3 の落とし込み規則 ⑤)。担当スロットも未規定(台帳 H-12 の残余)。**別タスクへ送る**(論点 D) |
| **`docs/ops/` の新設・DB 運用文書**(接続プール上限 — 要件書 7.1) | 設計書 13 章がディレクトリ新設を 4-4 とブートストラップ監査 PR の担当と定めている |
| **`docs/development/onboarding.md` の更新** | 13 章が「onboarding.md の完成と v1.0 approved 化」を **4-6** の担当と定めている |
| **DB スキーマ・マイグレーション(Alembic)** | 設計書 5.1 が「設計フェーズで最終確定」のまま。開発 DB は空で起動するだけ。backend 側の話 |
| **旧実データの投入** | 移行実データの取り扱い統制が未整備(台帳 H-56・未対応)。**空 DB のみ**とし抵触を避ける |
| **backend ジョブの paths filter** | backend ジョブ自体が未作成(4-2)。4-2 への申し送り |
| **NFR-021 の受入判定** | 13 章が「4-1 〜 4-5 は Phase 4 の部分成果。マージは NFR-021 判定を前提としない」と定める |

## 3. 影響する正本

**正本への反映は「なし」**。本 feature が作る・変更するファイルはいずれも正本ではない。

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし** — 既存の NFR-021・NFR-018・7.1 を実装するのみで、要件の追加・変更はない | — |
| `docs/development/dev-harness-design-2026-08-07.md`(ハーネス設計書) | **反映なし** — CI の paths filter 追加は設計書 10.1 が既に定めている内容への**実装追随**であり、設計書側は現状のままで正しい。13 章の現況追随は `P4-後` の担当 | — |
| `docs/adr/`(ADR) | **反映なし** — NFR-018 実現方式 ADR は別タスク(スコープ外) | — |
| `docs/development/onboarding.md` | **反映なし** — 4-6 の担当 | — |
| `docs/development/harness-evaluation.md`(評価台帳) | **反映あり**(/pr のクローズ処理で判断。起票時の宣言から変更した) — 実装の総合検証で**逐語移植の受入条件と NFR-018 の P0 規則が同一ファイルで両立しない**事象を検出したため、**H-61 を追記**し変更履歴表に 1 行足す(`H-*` の追記なので**版は上げない** — 7.6-3 前段)。あわせて `## 候補` へ 1 件追記 | PR レビュー |
| `docs/README.md`(索引) | **反映なし** — 新設する `contracts/README.md` は `docs/` 配下ではなくコード側の案内であり、正本体系(frontmatter・変更履歴表・索引登録)の対象外。評価台帳へ H-61 を追記するが、**索引の台帳行の最終更新日は既に 2026-08-17 で現行**のため変更不要 | — |

**非正本の更新**(ゲート不要): `docs/features/frontend-skeleton/porting-rules.md`(一時作業域)・`docs/features/dev-db-contracts/*`・`docs/worklog/2026-08-17-dev-db-contracts.md`。

## 4. 実装方針

**重さ分類 = 通常。** 根拠:

- **コア領域の判定**: 意味範囲上は**触れる** — 設計書 6.3 の境界定義表が「状況計算」欄に「**座標変換・捕球選手推定**(NFR-018・NFR-019(a) の対象)」を明示的に含めており、移設する座標定義はその契約物にあたる。しかし**機構上は発火しない** — `.claude/core-areas.json` の 5 領域の `paths` はすべて `[]` で、`contracts/` も `docker-compose.yml` も guard_paths に含まれない(paths 充填は Phase 4 の別作業 = 台帳 H-12)。
- **ただしステップ 4 だけは別**: `.github/workflows/ci.yml` は **guard_paths** なので core-guard が発火し、**PR 本文に「人間逐行確認済み」の必須チェックが付く**。これは領域 paths ではなくガード設定ファイルの保護によるもので、重さ分類を「コア領域」へ引き上げる根拠にはならない(前例: Phase 4-1 でも同じ経路で ci.yml に触れている)。
- 判定に迷う場合は含む側に倒す規則(設計書 6.3)に照らしても、**本 PR は新規ファイルの追加と参照の付け替えのみでドメイン計算のロジックを 1 行も書かない**ため、通常で妥当と判断する。

**決定事項**(research.md 論点 A〜G に対する人間判断 2026-08-17):

| 論点 | 決定 | 根拠 |
| --- | --- | --- |
| A(ADR 未起票) | **A-1** — 置き場 + 最小規約 + 移設に限定 | 設計書 4 章が `contracts/` を「NFR-019a のベクタ置き場であって NFR-018 の実現方式ではない」と限定している。規約を先に書くと ADR の先取りになる |
| B(PostgreSQL の版) | **`postgres:17.11-bookworm`** | Supabase Platform の既定が PostgreSQL 17(changelog 原文を確認)。`postgres:17` は mutable tag で NFR-021 の版記録と相性が悪いためパッチ固定。alpine は musl でロケール・照合順序が glibc と異なるため避ける。**タグの実在は 2026-08-17 に一次情報 2 系統で確認済み** — Docker Hub の tag API が `17.11-bookworm` を `active`(最終更新 2026-08-13)と返し、official-images の manifest にも `Tags: 17.11-bookworm, 17-bookworm` の行がある(計画レビュー 2 周目に「17.11 は存在せず 17.10 が最新」という指摘があったが、同レビューの 1 周目は逆の回答をしており、上記 2 系統と矛盾するため**不採用**とした) |
| ロケール | **`C.UTF-8` で固定**(libc provider を明示) | `LC_COLLATE`/`LC_CTYPE` は DB 作成後に変更不可。本番 Supabase の実値は非公開かつ本番未構築で突合できないため、**コードポイント順の決定的な照合**を選ぶ。**「OS 非依存」ではない** — libc provider を使う以上 glibc の実装に依存する。得られるのは「開発環境内での決定性」と「ICU の版差を持ち込まないこと」であり、**本番との一致は本番構築時に実測して突合する**(7 節の申し送り) |
| 誤接続防御 | **`.env.example` の規約で担保** | 旧システムは `APP_DB_MODE` 既定 sqlite という多重防御(「誤って本番 Supabase を触らないための多重防御」)を持っていたが、I-6 の PostgreSQL 一本化でこの歯止めが構造的に消える。機構的な検査は backend 実装が要るため 4-2 以降へ申し送り |
| ポート | **`${POSTGRES_PORT:-5432}:5432`** | WSL2 に既存 PostgreSQL があると固定では起動できない。compose を書き換えて回避するとその変更がコミットされる事故が起きる |
| C(CI paths filter) | **本 PR に含める** | 設計書 10.1 と現行 ci.yml が乖離している。直さないと移設後の契約ファイルを変更しても frontend ジョブが起動せず、逐語性とビルドの回帰が CI で捕捉されない |

**alias の実装方針(レビュー反映)**: 移設により frontend の外にある JSON を import する形になる。以下を採る。

- `frontend/tsconfig.app.json` に `"paths": { "@contracts/*": ["../contracts/*"] }` を足す。**`baseUrl` は足さない**(TypeScript 6 では `paths` に不要)。**`include` に `../contracts/**` を足す必要もない** — `src/` 配下の TS から import されたファイルは自動的にプログラムへ入り、`resolveJsonModule` は `@vue/tsconfig` 0.9.1 から継承済み
- `frontend/vite.config.ts` に `resolve.alias`(**絶対パスで指定**)と **`server.fs.allow`** を足す。`server.fs.allow` を明示すると Vite の workspace root 自動検出が無効になるため、**`frontend/` と `contracts/` の両方を列挙する**
- `frontend/vitest.config.ts` は現状 `vite.config.ts` を**完全に上書き**している。alias を二重定義せず、**`mergeConfig(viteConfig, defineConfig({ test: ... }))` へ書き換えて一元化する**
- `frontend/.prettierignore` の当該行は frontend 起点の Prettier の射程外になるため削除する

**逐語性の維持**: 移設するファイルは旧コミット `dd03160044aa5932d3b5a025870c9a5a56d979ef` の **`shared/display_geometry_263_v1.json`** に対して**バイト等価**を受入条件とする(porting-rules.md 8 節)。**注意: 旧リポは別リポジトリ(保全アーカイブ)であり、この worktree に当該コミットは存在しない** — `git show dd03160:...` では照合できない。porting-rules.md 8 節の汎用比較コマンドも旧側パスが `frontend/src/lib/` になっており、この JSON には**そのまま使えない**。旧側パスを `shared/display_geometry_263_v1.json` に差し替えた `gh api` 経由の比較を用いる。`displayGeometry.ts` の変更は **import パス 1 行のみ**に限る(同 8 節が許した逸脱枠と同形)。照合結果は台帳 H-59 の規律に従い、**照合した項目を列挙してから合否を述べる**形で記録する。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**順序の根拠(レビュー反映)**: CI の paths filter を JSON 移設より**先**に入れる。逆順だと、移設コミット単体では `contracts/**` がフィルタに無く frontend ジョブが発火しないため、そのステップの CI フィードバックが得られない。

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | `contracts/` を新設し `contracts/README.md` に位置づけを書く(NFR-019(a) のゴールデンベクタ・契約物の置き場であること / NFR-018 の実現方式そのものではなく実現方式は ADR で確定すること / 将来収載するものは要件書の付録が正であること。**形式・命名規約は書かない**) | ファイルが存在する。設計書・要件書への相対リンクが実在ファイルを指す(lychee)。`uv run python scripts/check_docs_status.py` が緑 |
| 2 | `.github/workflows/ci.yml` の `frontend-changes` フィルタへ `contracts/**` を追加する(設計書 10.1 への実装追随。**目的は「契約ファイル変更時に frontend の型・テスト回帰を検出すること」に限定**する — frontend ジョブは `working-directory: frontend` なので `contracts/` 自体は Prettier/ESLint の対象にならない。backend 側は 4-2 の担当なので触らない) | フィルタに `contracts/**` の行が存在することを**静的に確認**(差分レビュー)。**ローカルの `uv run python scripts/core_guard.py` は合格条件にしない** — `GITHUB_EVENT_NAME != "pull_request"` で skip するため無意味(`scripts/core_guard.py:256-257`)。実効の確認は PR 完了ゲート(下記)の `core-guard` ジョブ成功で行う |
| 3 | 座標 JSON を `git mv` で `contracts/` へ移し、frontend から alias 経由で参照する(`tsconfig.app.json` の `paths` / `vite.config.ts` の `resolve.alias`(絶対パス)と `server.fs.allow`(frontend と contracts の両方)/ `vitest.config.ts` を `mergeConfig` へ書き換え / `displayGeometry.ts` の import 1 行 / `.prettierignore` の当該行削除)。**あわせて `frontend/src/lib/displayGeometry.spec.ts` を新規追加**(6 節) | ① `pnpm exec vue-tsc --noEmit`・`pnpm test -- --run`・`pnpm exec eslint .`・`pnpm exec prettier --check .`・**`pnpm build`** がすべて緑 ② `pnpm dev` 起動後 `http://localhost:5173/` を開き、ストライクゾーンの枠が描画されること(左端が 80 相当)を目視し**結果を worklog へ記録** ③ **`test ! -e frontend/src/lib/display_geometry_263_v1.json`** が成功(複製が残っていないことの明示検査) ④ 移設後のファイルが旧リポ `dd03160` の **`shared/display_geometry_263_v1.json`** とバイト等価(`gh api` で旧 blob を取得し `cmp` — 旧側パスは `frontend/src/lib/` ではない) |
| 4 | `docker-compose.yml` と `.env.example` を新規作成する。compose: `postgres:17.11-bookworm` / `version:` キーは書かない(Compose v2 では obsolete)/ 名前付きボリューム / `POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale-provider=libc --locale=C.UTF-8"` / 環境変数は `${POSTGRES_USER:?required}` 形式で**未設定を起動時エラーにする** / ポートは **`127.0.0.1:${POSTGRES_PORT:-5432}:5432`**(全 interface へ公開しない)/ healthcheck は `pg_isready -h 127.0.0.1 -U $${POSTGRES_USER} -d $${POSTGRES_DB}` / `docker-entrypoint-initdb.d` は使わない / `depends_on` は依存サービスが無いため書かない。`.env.example`: `POSTGRES_USER`・`POSTGRES_PASSWORD`・`POSTGRES_DB`・`POSTGRES_PORT`・`DATABASE_URL`。**`DATABASE_URL` は DB コンテナへ渡さずホスト側 backend 用である旨**と**本番 URL を書かない旨**をコメントで明記 | ① **使い捨てのプロジェクト名・ボリュームで初回起動を検証する**(`POSTGRES_INITDB_ARGS` は空の PGDATA の初回のみ有効なため、既存ボリュームが残っているとロケールが変わらず検証にならない) ② `docker compose up -d --wait` が成功(`up -d` 直後に `ps` を見ると race になる) ③ `docker compose exec` 経由の psql でロケールとエンコーディングが `C.UTF-8` / `C.UTF-8` / `UTF8` であること。**確認先は `pg_database` の `datcollate` / `datctype` / `encoding`**(実装時の訂正 — `SHOW lc_collate` / `SHOW lc_ctype` は **PostgreSQL 16 で GUC が廃止されており 17 では `unrecognized configuration parameter` エラーになる**) ④ **`docker compose config --quiet`** が成功(**`--quiet` 必須** — 素の `config` は補間後の `POSTGRES_PASSWORD` を標準出力へ出す) ⑤ gitleaks が緑(PR 完了ゲートで確認) |
| 5 | `docs/features/frontend-skeleton/porting-rules.md` 8 節の「Phase 4-3 で移すこと」という**予定の記述を完了形へ置換**し(追記ではなく置換)、照合した項目を列挙してから合否を述べる(台帳 H-59)。`plan.md` の DoD と worklog を現行化する | 相対リンクが実在(lychee)。`uv run python scripts/check_docs_status.py` が緑。porting-rules.md に「移す予定」の記述が残っていない。`/check` 全グリーン |

### PR 完了ゲート(ステップ外 — コミットを伴わない)

全ステップ完了後、`/pr` の前に **最新 HEAD で CI 全ジョブが緑**であることを確認する(`secrets` = gitleaks / `docs-lint` / `core-guard` / `harness` / `frontend`)。**`core-guard` は PR イベントでのみ実効判定される**ため、ここが `ci.yml` 変更の唯一の実証点になる。PR 本文には人間逐行確認チェックが自動付与されるので、**人間がチェックするまでマージしない**。

## 5. DoD(受け入れ基準)

| # | DoD | 達成するステップ | 状態 |
| --- | --- | --- | --- |
| 1 | `docker compose up -d --wait` で開発用 PostgreSQL が起動し、healthcheck が healthy になる | 4 | ✅ 実測(PostgreSQL 17.11・healthy 到達) |
| 2 | 開発 DB のロケールとエンコーディングが実測で `C.UTF-8` / `C.UTF-8` / `UTF8` である | 4 | ✅ 実測(`pg_database` で確認) |
| 3 | `contracts/` の雛形(ディレクトリと位置づけを書いた README)がある | 1 | ✅ |
| 4 | `display_geometry_263_v1.json` が `contracts/` にあり、frontend からそこを参照している(**複製が残っていないことを `test ! -e` で明示検査**) | 3 | ✅ 実測(dev サーバの `/@fs` 配信 200・複製なし) |
| 5 | 移設した座標 JSON が旧コミット `dd03160` の `shared/` 版と**バイト等価**であることを照合済み | 3 | ✅ sha256 一致 |
| 6 | `.env.example` が接続情報の正本として存在し、本番 URL を書かない旨が明記されている | 4 | ✅ |
| 7 | CI の frontend ジョブの paths filter に `contracts/**` が含まれている | 2 | ✅ |
| 8 | `/check` 全グリーン | 5 | 総合検証で確認 |
| 9 | CI 全ジョブ緑(`secrets` = gitleaks・`core-guard` を含む) | **PR 完了ゲート**(ステップ外) | PR 作成後に確認 |

## 6. テスト計画

NFR-019 のテスト種別のうち、本 feature が追加・変更するのは**単体(frontend = Vitest)のみ**。

| 種別 | 本 feature での扱い |
| --- | --- |
| **単体(Vitest)** | **既存の回帰網がそのまま検証装置になる** — `frontend/src/components/zone/StrikeZone.spec.ts` は座標 JSON 由来の値(`strike_zone.left` = 80)を期待値にしており、移設で解決が壊れれば失敗する。加えて **`frontend/src/lib/displayGeometry.spec.ts` を新規追加**(ステップ 3)し、`DISPLAY_COORDINATE_SYSTEM` が `display_263_top_left_v1`・`DISPLAY_COORD_SIZE` が `263`・`COURSE_STRIKE_ZONE` が JSON の値と一致することを固定する(契約ファイルが差し替わったことを検出するため)。**ただしこのテストは「複製の復活」を検出できない** — 同じ値を持つ複製を参照しても通るため、複製の不在は `test ! -e frontend/src/lib/display_geometry_263_v1.json` の明示検査で担保する(ステップ 3 の合格条件 ③) |
| **単体(pytest / backend)** | 追加なし — backend は未作成(4-2) |
| **単体(pytest / harness)** | 追加なし — hooks・ラッパーに変更を加えない |
| **(a) 一致性(ゴールデンベクタ)** | **追加なし** — 設計書 10.1 が `consistency` ジョブの導入時期を「実装期」と定めている。本 feature はベクタの中身を作らない(スコープ外) |
| **(b) 越境アクセス** | 追加なし — 認可の実装がない |
| **(c) E2E(Playwright)** | 追加なし — 導入時期は実装期 |
| **(d) 同期プロトコル故障系** | 追加なし — 実装がない |

**テストで担保しない検証**(手順として実施し、結果を worklog へ記録する): 開発 DB の起動・ロケール実測(ステップ 4)、`pnpm dev` での描画確認(ステップ 3)、バイト等価の照合(ステップ 3)。DB を起動するテストは CI に持ち込まない(CI に DB サービスを足すのは backend ジョブと同時 = 4-2 以降の判断)。

**実装時の禁止事項**: `.env.example` は作るが、**実 `.env` は作らない・読まない**(NFR-014。`Read(./.env.*)` は permissions で deny、`.env` の作成は `protect_paths.py` がブロックする)。開発者が `.env.example` を写して `.env` を作る手順は人間が実行する。

## 7. 申し送り(本 PR では扱わないが記録する)

- **NFR-018 実現方式 ADR の起票**(設計書 4 章が「Phase 4 着手前に確定する」と定めた未履行事項。台帳 H-55 と同時に扱う)
- **`core-areas.json` の paths 充填** — `contracts/` に座標定義を置いたことで `game-state` の paths 候補が初めて発生した(台帳 H-12)
- **ロケールの本番突合** — 本番 Supabase 構築時に `SHOW lc_collate; SHOW lc_ctype;` を確認し、開発側(`C.UTF-8`)と突合する。**DB 作成後は変更できない**ため、不一致なら本番構築の時点で決着させる
- **本番誤接続の機構的な歯止め** — backend 実装時(4-2 以降)に接続先の検査を設計する
- **接続プール上限の運用文書化**(要件書 7.1)— `docs/ops/` は 4-4 以降
- **backend ジョブの paths filter に `contracts/`**(設計書 10.1)— 4-2 で
- **onboarding.md への DB 起動・再作成手順** — 4-6 で。初期化は PGDATA が空の初回のみ実行されるため、やり直しにはボリュームの再作成が要る(`docker compose down -v` は Claude の permissions で deny のため人間が実行する)
- **イメージの digest pin** — 本 feature はパッチ固定(`17.11-bookworm`)までとし、`@sha256:` は付けない。**パッチタグもベース OS の再ビルドで動くため「完全な再現性」は主張しない**。NFR-021 の証跡で厳密な同一性が要求される段階(4-6)で、digest 固定に切り替えるかを判断する
- **`contracts/` 自体の検査層** — frontend ジョブは `working-directory: frontend` のため `contracts/` は Prettier/ESLint の対象にならない。契約ファイルの形式検査(JSON Schema 検証など)が必要になったら、その時に検査層を設計する(本 feature の paths filter 追加は「import 回帰の検出」までを目的とする)
