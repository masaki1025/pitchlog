---
date: 2026-08-17
topic: Phase 4-3 開発用 PostgreSQL(docker-compose)+ contracts/ 雛形
branch: feature/dev-db-contracts
---

# 作業ログ: 2026-08-17 Phase 4-3 開発用 PostgreSQL + contracts/ 雛形

## やったこと

- /task-start: 引数 `4-3` を既存 Notion タスク TSK-222「Phase 4-3: docker-compose(開発用 PostgreSQL) + contracts/ 雛形」と同定(新規起票はしていない)→ `feature/dev-db-contracts` ブランチ + worktree 作成(origin/develop = 5164c4d 起点)→ 計画書雛形・本 worklog 作成 → Notion を 進行中 へ

- /investigate: 調査サブエージェント 3 本(spec-checker / legacy-analyst / decision-tracer)を並列実行 → 決定的な引用を原典で再確認 → `docs/features/dev-db-contracts/research.md` へ統合。計画書 1 節・4 節から参照

## 決定

- slug は `dev-db-contracts`(Phase 4-1 = `frontend-skeleton` に倣い、内容が分かる英小文字ハイフン)
- **(人間判断 2026-08-17)** 論点 A は **A-1** — 4-3 は「`contracts/` の置き場 + 最小規約(README)+ 座標 JSON の移設」に限定し、ゴールデンベクタの中身(付録E・付録A)と NFR-018 の実現方式は**別タスクの ADR へ送る**。4-3 は通常 PR 要件のまま保つ
- **(人間判断 2026-08-17)** 論点 B は **/research で Supabase の現行 PostgreSQL 版を確認してから決める** → 実施済み。**Supabase Platform の既定は PostgreSQL 17**(changelog 原文を Claude が確認)、`postgres` 公式イメージの 17 系現行パッチは **17.11**(manifest を直接確認)。**`postgres:17.11-bookworm` を計画書で提案**(alpine は musl でロケール差、`postgres:17` は mutable tag のため再現性で劣る)
- **(人間判断 2026-08-17)** 4-3 のスコープに含める: **CI の paths filter への `contracts/` 追加**(設計書 `:603-604` への実装追随)/ **`.env.example` の初版作成** / **porting-rules.md への移設の追記**。`core-areas.json` の paths 充填は**含めない**(別タスク H-12 へ)

- /plan: 6 節すべてを記入 → Codex レビュー(通常)1 周 → 承認(2026-08-17・山田正輝)。P0 として「`docker compose config` が補間後のパスワードを標準出力へ出す」を検出し `--quiet` へ修正。「`postgres:17.11-bookworm` は存在しない」との 2 周目の指摘は Docker Hub の tag API と official-images manifest で実在を確認し不採用
- /implement: 5 ステップを順に委任・検証・コミット

## 実装の実測メモ

- **alias 配線は成立した**(計画で唯一の未検証点)。`tsconfig.app.json` の `paths` + `vite.config.ts` の `resolve.alias`(絶対パス)と `server.fs.allow`(frontend と contracts の両方)+ `vitest.config.ts` の `mergeConfig` 化。dev サーバが `/@fs/.../contracts/display_geometry_263_v1.json` を **200 で配信**することを実測。`vue-tsc` / Vitest(9 件)/ ESLint / Prettier / `vite build` すべて緑
- **バイト等価は 3 経路で照合**: 移設前後の Git blob 比較・旧リポ archive の `dd03160` の `shared/` 版との `cmp`・複製不在の `test ! -e`。sha256 は `e0c4d336…8901f6` で一致。git も rename(内容差分 0)として認識
- **`SHOW lc_collate` は PostgreSQL 17 では使えない**(PG 16 で GUC が廃止され `unrecognized configuration parameter` になる)。計画書の合格条件に書いていたので実装時に訂正し、確認先を `pg_database` の `datcollate` / `datctype` / `encoding` に変更した。実測値は `C.UTF-8` / `C.UTF-8` / `UTF8` で DoD 自体は充足
- **開発 DB は実際に起動して検証した**。Docker はクリーンな状態(volume・コンテナ 0)だったため初回初期化が保証され、`POSTGRES_INITDB_ARGS` が確実に効く条件だった。使い捨てではなく実際の開発 DB として立てている(コンテナ名 `feature-dev-db-contracts-db-1`・ボリューム `feature-dev-db-contracts_postgres_data`)。ポートは `127.0.0.1:5432` のみでループバック限定
- env 未設定時に `:?required` がエラーで停止することも確認済み

## 結果サマリ(/pr クローズ処理)

**実装したもの**(5 ステップ・全 5 コミット): `contracts/` 新設と README(位置づけのみ・規約は書かない)/ CI の frontend paths filter へ `contracts/**` 追加 / 座標定義 JSON の `contracts/` 移設と alias 配線・契約固定テスト / `docker-compose.yml` と `.env.example` / 非正本ドキュメントの追随。

**正本への反映**: 当初の宣言は全項目「反映なし」で、実装後の差分でも**正本の変更はゼロ**だった(要件書・設計書・ADR・onboarding・索引のいずれも不変)。CI の filter 追加は設計書 10.1 が既に定めた内容への実装追随であり、**設計書が現実に追いついた側**なので設計書の変更は不要。

**ただし評価台帳のみ「反映あり」へ変更した**(下記)。

**検証**: harness pytest 354 passed / frontend は prettier・eslint・vue-tsc・vitest(9 件)・build すべて緑 / 開発 DB は `up -d --wait` で healthy 到達しロケール `C.UTF-8` / `C.UTF-8` / `UTF8` を実測 / 変更 markdown のリンク切れ 0 / `check_docs_status.py` 緑。

## 評価台帳への追記判断(/pr 手順 1-3)

**該当する → H-61 を追記した。**

総合検証の差分レビューで、`frontend/src/lib/courseInputView.ts:4` の `COURSE_COORDINATE_SIZE = 263` が `contracts/` の契約値と二重管理になっていることを検出した。このファイルは逐語移植対象(バイト等価が受入条件)なので直せず、一方 AGENTS.md の Code Review Rules は NFR-018 違反を P0 と定める。**規約がこの衝突に沈黙している**ため、ハーネス側の知見として起票した。分類はプロセス設計(文書・レビュー運用の設計に起因し機構の実体を伴わない)、追跡優先度は通常固定。

**本 PR では当該ファイルを直していない** — 直すと逐語性の受入条件を壊し、かつ計画スコープ外のため。

なお実装中に見つかった「`SHOW lc_collate` が PostgreSQL 17 で使えない」は、計画書の合格条件を訂正して解消済みであり、**台帳には起票していない**(単発の事実誤りで、実装段階の検証が正しく捕捉したため傾向として確定していない)。

**あわせて `## 候補` へ 1 件追記した。** `/pr` 手順 2-2 の機械突合(`check_plan_docs_sync.py`)を実行したところ exit 1 になり、原因は同スクリプトの `extract_declarations` が**行全体に対する `"反映なし" in line` の部分文字列一致**で宣言を分類していることだった。台帳の行を「反映あり」へ変更する際、経緯として『当初は「反映なし」宣言だった』と書いたために、その行が「反映なし」宣言と判定された。文言から当該語を除いて解消。**fail-closed(誤って通すのではなく誤って止める)で回避も文言変更だけ**のため、`H-*` は与えず候補に留めた。

## 未決・次の一歩

調査で出た論点(詳細は research.md):

- **論点 A**: 設計書 `:177`・要件書 `:856` が「Phase 4 着手前に確定する」と定めた **NFR-018 実現方式 ADR が未起票**。4-3 は `contracts/` の中身を初めて決める PR なのでこの空白の上に立つ。推奨は A-1(4-3 は置き場 + 最小規約 + 座標 JSON 移設に限定し、ベクタの中身と実現方式は ADR へ送る)— **人間判断待ち**
- **論点 B**: PostgreSQL のメジャー版がどの正本にも未規定。/research(Codex)で Supabase の現行版と公式イメージのタグを確認してから決める
- **論点 C**: 設計書 `:603-604` は CI の paths filter に `contracts/` を含めると定めるが現行 `ci.yml:99-104` に無い。4-3 で追随する場合、`ci.yml` は guard_paths なので core-guard 発火 + 人間の逐行確認が必須
- **論点 D**: `core-areas.json` の paths 充填は 4-3 ではやらない(敵対レビュー + 人間承認が要り、13 章が 4-3 に与えたマージ条件で通らない)
- **論点 E**: `.env.example` の初版作成を 4-3 のスコープに入れるか
- **論点 F**: 移設後の逐語性(バイト等価)の担保先
- **論点 G**: TS/Vite/Vitest で frontend 外の JSON を import する実現可否 — 実装ステップ 1 で実測

次の一歩: 論点 A・B の判断を得てから /plan で計画書を確定する
