---
feature: tenant-boundary-enforcement
status: in-review         # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-17・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3da93b75e68781fc87d7f04a12ff6ad8
branch: feature/tenant-boundary-enforcement
created: 2026-09-17
計画レビュー周回: 6        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: U-T1 テナント境界の強制点

## 1. 背景・目的

**計画段階の調査**: [research.md](./research.md)。**詳細設計**: [design.md](./design.md)。
本書は**契約と実装ステップ表**のみを持つ(内容を複製しない — 設計書 7.1-1)。

- Notion タスク: [TSK-390 U-T1 テナント境界の強制点(コア・本設計の要)](https://app.notion.com/p/3da93b75e68781fc87d7f04a12ff6ad8)
- 主所有 FR: [FR-034 データ所有権制御](../../requirements/requirements-pitchlog-2026-07-22.md#FR-034)
- **分担**: [FR-019](../../requirements/requirements-pitchlog-2026-07-22.md#FR-019) の**キャッシュ無効化契約**(主所有は U-D1)
- 関連 NFR: [NFR-010](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-010)(チーム間データ分離・測定は「API直叩き含む」)/
  [NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-019)(b)(越境アクセステスト・**経路ごとの発効条項**)/
  [NFR-014](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-014)(シークレット)/
  [NFR-005](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-005)(選択されていないテナントを走査しない)

**本単位の目的は、テナント越境の強制点を 1 本に集約し、後続実装がその強制点を経由することを
機械的に保証し続けることである。**

### 射程の縮小(**2026-09-17・山田正輝の裁定**)

2026-09-17 に「[TSK-418 U-T1 の入力を確定する](https://app.notion.com/p/3db93b75e687813a9386f3b1f1e682ed)を
U-T1 に取り込む」と決めたが、**計画レビュー 4 周(敵対・sol xhigh)で P0 が 5 → 5 → 3 → 3 と収束しなかった**。
残った P0 はいずれも**製品の認可面ぜんたい(45 表 × 許可プロファイル × 所有単位)を確定する作業**で、
**U-C1 / U-C2 / U-C3 / U-A1 / U-A2 にまたがる**ことが判明した。

→ **取り込み決定をこの範囲について撤回**し、
**[TSK-424 製品認可面の確定](https://app.notion.com/p/3de93b75e6878172a4b4d2f6edd663fc)** へ分離した。
**本単位はカード本来の射程(ランタイムの強制点 + 迂回検査)に戻る。**

**「葉の非コア判定の根拠」ではない**(計画レビュー 1 周目 P2 の是正): 現行の分割計画で
非コアで通せる対象は**器 3 本(`U-00`/`U-01`/`U-02`)だけ**で、**葉 6 本は既にコア確定**
(`../product-impl-unit-split/plan.md:254-257`)。迂回検査の目的は**継続保証**である。

**要件との関係の注意**: U-T1 のスコープ 5 要素は**いずれも FR-034 に直接の根拠がない**。
FR-034 が定めるのは越境の*結果*で、*機構*は `docs/design/data-model.md` 3 章が正。
**FR-034 の「既定拒否の原則」を fail-closed の根拠に使わない**(要件書 `:608` が射程を限定)。
**ただし観測可能な拒否結果の根拠は引き続き FR-034 / NFR-010 であり、追跡を切らない。**

## 2. スコープ

### やること

1. **迂回検査の検査契約の確定**(実装前)と、**実装への適用・CI 常時実行**
2. **アプリ用ロール接続の専用化と真正性検査**(ロール名の完全一致 + `pg_auth_members` の推移閉包)
3. **`TenantContext` と生成箇所 allowlist**(真正性の引き渡しの機械化)
4. **`set_config` による文脈束縛** — 正本の規律 5 項**すべて**を検査 / **アプリ層の fail-closed**
   (**`TenantContext` が無ければ業務 SQL を 1 文も発行せず `TenantBindingError`**)
5. **越境関数経由のリポジトリ基底** — 二重構成(RLS + 明示的なテナント条件)
6. **コア領域 paths とチェック配線の追加**(`repositories/*` + 検査器・allowlist・fixture)
7. **DB fixture の通常モジュールへの抽出**(平場テストから使えるようにする)
8. **FR-019 のキャッシュ無効化契約**(**分担** — 主所有は U-D1。`../product-impl-unit-split/plan.md:216` /
   同 `design.md:91` の重複帰属表が **U-T1 の分担**と明記。**迂回検査の条件 4 が葉に禁止する以上、
   本単位が提供しないと誰も実装できない**)

### やらないこと

| 除外するもの | 理由・受け取り先 |
| --- | --- |
| **全 45 表の許可プロファイル / 製品 authz DDL 資産 / probe↔製品写像 / 移行バッチロールのライフサイクル / authz ツールチェーンの一般化** | **[TSK-424](https://app.notion.com/p/3de93b75e6878172a4b4d2f6edd663fc)** へ分離(1 節の裁定)。**本単位と並行可能**。衝突面は `contracts/authz/product/` と `backend/tests/db/conftest.py` |
| **テナント文脈の値の真正性の検証** | **DB 層では守れない**。`contracts/authz/boundary-proposal.json:43-47` が検証所有者を **TSK-217** と宣言。ただし**引き渡しは機械化する**([design.md](./design.md) 1-1) |
| **製品の越境関数・関数 ACL・`search_path`、および最低要求 ②③④** | 共有・グループ経路 = **U-C1 / U-C3**、制御情報読み取り = **U-C2**、システム管理経路 = **U-A2**(`../product-impl-unit-split/plan.md:223` `:225` `:226` `:227`)。**射程の重複を避ける**(NFR-018 ではない — [design.md](./design.md) 8-1) |
| **実スキーマへの適用と越境テスト再実行** | **TSK-344**(裁定 `A-2`・`docs/design/data-model.md:2846`) |
| **`docs/design/data-model.md` 12-8 節の実装追随** | **TSK-424** が持つ(製品 DDL 資産を確定する側が記録するのが筋) |
| **HTTP の入口・API 経路** | **U-T1 は入口を 1 つも開かない**(`../product-impl-unit-split/plan.md:433-443`)。12-4 マージゲートの対象外 |
| **`contracts/authz/` の probe 資産の変更** | `oracle-seal.lock.json:40-77` で封印済み。**差分 0 行** |
| **alembic migration への RLS/ロール DDL の追加** | 裁定 `A-2` / `D7` で **0 件**を維持 |
| **`backend/src/pitchlog/db/` へのファイル追加** | `../product-impl-unit-split/plan.md:466`。新規は `repositories/` へ |
| **依存の追加** | **`backend/pyproject.toml` と `uv.lock` の差分 0 行**(同 `:462`) |
| **一覧 API・ページング** | 本単位は**一覧経路を 1 つも公開しない**。ページング契約は **U-01**(DTO 基盤)の所有であり、U-T1 の依存は `U-00` のみ(`../product-impl-unit-split/plan.md:204`)。**U-01 への隠れ依存を作らない**(計画レビュー 5 周目 P1 の是正) |
| **製品 RLS の述語構造・未束縛の直接 SQL が 0 行・不正 UUID の `22P02`** | **TSK-424**(計画レビュー 5 周目 P0 の是正)。これらは**製品 RLS ポリシーが無いと成立しない**。現存資産は `product_schema: false` の probe で述語も `::BIGINT`(`contracts/authz/ddl-elements.json:8` / `function-bodies/predicates/PREDICATE:CURRENT_TENANT_OWNS_ROW.sql:7`)であり、製品は UUID。**probe の流用も、製品述語のテスト内コピーも、製品契約を検証しない**。→ **U-T1 の fail-closed はアプリ層に限定する** |
| **製品表向けの汎用 CRUD の公開** | **TSK-424 の表分類が確定するまで公開しない**(同 P0 の是正)。**`TenantMixin` から公開操作を導くと `GroupMembership`(制御資源)を誤って一般テナント表として開く**。U-T1 単独試験は**テスト専用のテナント表**で行う |
| **キャッシュ無効化の*発火*(トリガー側)** | 本単位が持つのは**契約と API** まで。`試合の削除/復元/再開` などトリガーの発火は **U-D1** ほか各単位(`docs/design/data-model.md` 11-2 の 14 トリガー × 5 範囲の表が正) |

### TSK-424 との境界(**この 1 点だけ順序依存がある**)

本単位のステップ 6(接続の真正性検査)は**期待アプリロール名**を要する。
**TSK-424 が製品資産を確定するまでは、ロール名を本単位の資産として暫定定義し、
TSK-424 完了時に製品資産からの導出へ差し替える。**
→ 暫定定義であることを**資産に明示**し、**差し替え漏れが検出できる形**にする([design.md](./design.md) 3-5)。

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし**。要件の条項を動かさない | — |
| `docs/design/data-model.md` | **反映なし**。3-1〜3-6・12-4 の契約に**従う**側。**12-8 節の追随は TSK-424 が持つ** | — |
| `docs/design/sync-protocol.md` | **反映なし** | — |
| `docs/adr/` | **新設なし**。既決の制約の適用であり新しい決定を持たない | — |
| **`.claude/core-areas.json`** | `tenant-isolation` の `paths` へ **`backend/src/pitchlog/repositories/*` + `backend/tests/db_fixtures.py`(exact path)+ 迂回検査器・allowlist・正負 fixture・検査テスト**を追加(設計書 6.3-⑤ / `dev-harness-design-2026-08-07.md:393`) | **敵対レビュー + 人間の逐行確認**(`guard_paths` 対象。**PR レビューのゲートであって、コミット単位の合格条件ではない**) |
| **`.github/workflows/ci.yml`** | 迂回検査器だけを変更した PR でも走るジョブの配線(現行の backend フィルタは `backend/**` と `contracts/**` しか拾わない — `:176`) | PR レビュー(`tests/test_ci_wiring.py` の期待列更新を伴う) |
| **`.env.example`** | アプリ用 DSN の記述を専用化(**値は書かない** — NFR-014)。`PITCHLOG_DATABASE_URL` の説明を「最初の物理接続時に失敗」へ同期 | PR レビュー |
| **`docs/development/harness-evaluation.md`** | **`## 候補` へ新規 1 件 + 既存候補 2 件へ事例追記**(/pr のクローズ処理で判断)。**`H-*` の新規採番はしない・版は上げない**(7.6-3 前段) | PR レビュー |

## 4. 実装方針

**重さ分類 = コア領域。** 根拠は 2 つで、いずれも単独で成立する:

1. **意味範囲**(設計書 6.3): 本単位は**テナント分離**そのもの。
   `../product-impl-unit-split/plan.md:341` が核 3 + 帯 3 を「**読みに依存せずコア**」と判定
2. **paths**: 本単位が触る `backend/src/pitchlog/db/engine.py` / `backend/tests/test_authz*.py` /
   `backend/tests/db/*` はすべて登録済み(`scripts/core_guard.py:226` の `fnmatch.fnmatchcase`)

→ **実装は sol xhigh・敵対レビュー必須・人間の逐行確認必須**(CLAUDE.md / ADR-001)。

詳細設計は [design.md](./design.md)。**TSK-424 へ移した内容**(許可プロファイル・製品 DDL 資産・写像・
移行ロール・ツールチェーン一般化)は design.md 2〜4 節に残してあり、**TSK-424 の計画の入力として引き継ぐ**。

### 全ステップに掛かる差分不変条件

**`backend/pyproject.toml` 差分 0 行 / `uv.lock` 差分 0 行 / `backend/tests/conftest.py` 差分 0 行 /
`contracts/authz/` の probe 資産の差分 0 行 / `backend/migrations/` に `CREATE POLICY`・`CREATE ROLE`・
`ALTER ROLE` が 0 件 / `backend/src/pitchlog/db/` への新規ファイル 0 件。**

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **迂回検査の検査契約を資産として確定する**(検査器骨格 + 正例/負例 fixture) | **次のパスを計画時に固定する**: 検査器 `scripts/check_tenant_boundary_bypass.py` / DB 到達 API の inventory `contracts/tenant_boundary/db-api-inventory.json` / allowlist `contracts/tenant_boundary/base-allowlist.json` / 正例 `tests/fixtures/tenant_boundary/positive/` / 負例 `tests/fixtures/tenant_boundary/negative/` / 検査テスト `tests/test_check_tenant_boundary_bypass.py`。**検査対象の diff 基準は `git diff -U0 origin/develop...HEAD -- backend/src`**(`../product-impl-unit-split/plan.md:263-265`)。**CI のジョブ名と実行コマンドを `ci.yml` に固定**。**DB 到達 API の閉じた集合**が inventory にあり(**「ほか」で開かない — 全列挙**)、集合外の API 追加が red。**正例 fixture**(許可されるべき完全修飾シンボルと署名)が**通る**こと。**負例 fixture の `{id, path, condition, mutation, expected_error}` の全数表**が資産にあり exact-set。**条件ごとに変異軸が違う**([design.md](./design.md) 6 節)。**全拒否の検査器では正例が落ちて red** |
| 2 | **DB fixture を通常モジュールへ抽出する**(`backend/tests/db_fixtures.py`) | `backend/tests/db/conftest.py` の fixture が**通常モジュール**へ移り、**平場テストと `db/` 配下の双方から明示 import で使える**。**`backend/tests/conftest.py` の差分 0 行**。既存の `db/` 配下テストが無改変で green |
| 3 | **`backend/tests/test_authz_tenant_binding.py` の骨格を置く** | **意図的にこの名前**で機械判定を効かせる。`backend/tests/db_fixtures.py` を明示 import し、**以降のステップが試験をここへ足せる**状態。この時点では表明済みの契約のみ green |
| 4 | **コア領域 paths とチェック配線を足す**(`.claude/core-areas.json` + `.github/workflows/ci.yml`) | `scripts/core_guard.py` の既存テストが green。**`repositories/*`・`backend/tests/db_fixtures.py`・迂回検査器・allowlist・正負 fixture・検査テスト**がコア判定に入ることを負例つきで検証(**`db_fixtures.py` は現行 paths のどれにも一致しない** — `backend/tests/db/*` にも `backend/tests/test_authz*.py` にも `backend/*conftest.py` にも当たらない)。`tests/test_core_guard.py` に**同パスの正例と、paths から外すと red になる負例**を追加。**検査器だけを変更した PR でも走るジョブ**があり、`tests/test_ci_wiring.py` の期待列が更新され、**負例 4 種(欠落・重複・順序違い・別ジョブ追加)で red** |
| 5 | **`.env.example` のアプリ用 DSN 記述を専用化する** | 差分に**値が含まれない**。`PITCHLOG_DATABASE_URL` の説明が**「最初の物理接続時に失敗」へ同期**されている(「未設定なら起動失敗」相当の記述を残さない) |
| 6 | **アプリ用ロール接続の専用化と真正性検査**(`backend/src/pitchlog/db/engine.py`) | **新しい DSN 変数を足していない**。**最初の物理接続の確立時に**、`session_user` と `current_user` の**両方が期待アプリロール名と完全一致**(暫定定義であることが資産に明示され、差し替え漏れが検出できる)、`rolcanlogin`=true / `rolsuper`=false / `rolbypassrls`=false、かつ **`pg_auth_members` の推移閉包で危険ロールへ到達不能**(危険終点は `backend/src/pitchlog/authz/catalog.py:808` の `_dangerous_role_ids` と同じ exact-set)。**名前で落ちる負例**: `table_owner` / 通常 `LOGIN` ロール / 共有関数所有ロール / 管理関数所有ロール / 移行バッチロール / superuser / `SET ROLE` 偽装。**属性検査でしか落ちない負例**(5 周目 P1 の是正 — 上の負例はすべて名前不一致で落ちるため、属性検査を実装しなくても green になる): **期待ロール名を保ったまま `SUPERUSER` にした fixture**・**同じく `BYPASSRLS` にした fixture**。**推移閉包でしか落ちない負例**: 期待ロール名のまま `app_role → 中間 → 危険ロール` の**直接所属**と**多段所属**を **`set_option` と `inherit_option` 別 fixture** で。**混合辺の閉包**(6 周目 P0 の是正): **`SET*` で到達できる各ロールからさらに `INHERIT*` 閉包を取り**、危険終点との交差を検査する(**`app_role --SET→ 中間 --INHERIT→ 危険ロール` は、辺の種類ごとに別々に閉包を取るだけでは検出できない**)。**`admin_option` を独立した拒否条件**にする(`ADMIN OPTION=true / SET=false / INHERIT=false` でも**メンバーシップを自ら再付与して昇格できる**)。**期待ロール属性は資産と完全一致**で検査する(`rolsuper` / `rolbypassrls` / `rolcanlogin` / **`rolcreaterole`** / `rolcreatedb` / `rolreplication` / `rolinherit`)。**`CREATEROLE` の独立負例**を置く。**危険終点の各カテゴリ**(superuser / `BYPASSRLS` 保持 / スキーマ所有者 / テーブル所有者 / 関数所有者)が**最低 1 回は終点になる exact-set 表**を資産に持つ。**`rolcanlogin=false` は直接接続できない**ので、カタログ検査関数の単体試験として分離する。いずれも **`pitchlog.db.config.DatabaseConfigurationError`** で拒否。未設定時 fail-closed |
| 7 | **`TenantContext` と生成箇所 allowlist**(`backend/src/pitchlog/repositories/`) | 基底が**生の `UUID` を受け取らない**(型で強制)。`TenantContext` の構築が **allowlist 内のモジュールに限られる**ことの検査が green、allowlist 外からの構築が red。**allowlist に製品モジュールが 0 件**(U-A1 / TSK-217 待ち) |
| 8 | **テナント文脈の束縛とアプリ層 fail-closed**(`backend/src/pitchlog/repositories/`) | 規律 5 項すべて: ① **業務トランザクション内の発行 SQL 列の先頭が束縛文**(観測窓は `Session.begin()` 以降。**物理接続初期化 SQL〔ステップ 6〕は別イベントとして識別する**)② `set_config(...,false)`・`SET app.tenant_id` が 0 件 ③ **commit 後に `current_setting('app.tenant_id', true)` が空文字**(**GUC の transaction-local 性の確認であり、製品 RLS の代替検証ではない**。**テスト専用のテナント表**を使う)④ **autocommit 接続で基底を使うと `TenantBindingError`** ⑤ **同一 `Session` の再束縛が拒否**され、**並行 2 `Session` 間で GUC が漏れない**。**`TenantContext` が無ければ業務 SQL を 1 文も発行せず `TenantBindingError`**(SQL observer で発行 0 件を観測 — **「0 行が返る」ではない**)。**製品 RLS の述語構造・未束縛の直接 SQL が 0 行・不正 UUID の `22P02` は TSK-424 の受入条件**(2 節) |
| 9 | **越境関数経由のリポジトリ基底**(`backend/src/pitchlog/repositories/`) | 基底の**公開シンボルが exact-set**(生の `Session`・任意クエリを公開しない)。**製品表向けの汎用 CRUD を公開しない**(5 周目 P0 の是正)。**実行器の署名を固定する**(6 周目 P0 の是正 — 「封印」の定義が無いと汎用 CRUD の迂回口になる): **実行器は非公開**とし、公開面は**生成済みの閉じた operation token だけを受ける署名**に限る。**`Any` / callable / SQLAlchemy の statement・model・table を引数に取らない**ことを合格条件にし、**任意 statement・任意 callable・偽造 token を渡す変異で red**。**製品 capability 集合と越境関数 registry は初期値ともに空集合**とし、**テスト専用 token を製品パッケージへ収載しない**。公開面は**文脈束縛・実行器の token 入口・空の越境関数 registry**まで。製品表操作は TSK-424 の表分類から生成する capability を受けて初めて有効化する)。**公開メソッドの戻り値が完全実体化済みの immutable な値/DTO に限られる**(同 P0 — **接続中の ORM instance / SQLAlchemy `Result`・`ScalarResult` / query / 遅延 generator を公開 exact-set から除外**。これらを返すと**呼び出し元の属性参照・反復・expire 後の再読込で SQL が発行され**、呼び出し元の AST に `Session.execute` が現れないので**迂回検査で捕捉できない**)。**負例**: 接続中 ORM instance を返す / `Result` を外側で反復する。**一覧経路を公開しない**(ページング契約は U-01 の所有。本単位は U-01 に依存しない)。越境手段が**関数呼び出しのみ**(現時点では関数 0 件なので**呼び出し口が存在し空であること**) |
| 10 | **キャッシュ無効化契約の資産と API**(`backend/src/pitchlog/repositories/` + `contracts/`) | **`docs/design/data-model.md` 11-2 の 14 トリガー × 5 範囲の対応表**が機械可読資産として存在し、**同節との両方向 exact-set**(トリガー 14 件・範囲 5 区分・● の配置まで。**招待の失効が含まれていない**ことも検査)。無効化 API の**公開シンボルが exact-set**。**迂回検査の条件 4 の許可側が「本 API の呼び出しのみ」**として資産に書かれている(葉が直接無効化を書くと red)。**発火は持たない**ことを表明 |
| 11 | **迂回検査を実装へ適用する** | ステップ 1 の検査契約を**自 PR の `backend/src` 追加行**へ適用して**一致 0**。**正例(基底の許可シンボル)が通る**。**基底へ直接 SQL を足す変異で red**。CI で常時実行されている |

**ステップ 4 は `.claude/core-areas.json` を触る**(設計書 6.3-⑤)。人間の逐行確認は **PR レビューのゲート**として受ける。

## 5. DoD(受け入れ基準)

- [ ] **越境の強制点が 1 本に集約されている**(基底の公開シンボルが exact-set・生の `Session` を公開しない)
- [ ] **迂回していないことの機械検査を同梱している**(AST / シンボル粒度・正例と負例の両方・基底自身も対象・CI 常時実行)
- [ ] **テストを `backend/tests/test_authz_tenant_binding.py` と命名する**
- [ ] **アプリ層 fail-closed の故障系テスト** — **`TenantContext` が無ければ業務 SQL の発行件数が 0**(SQL observer で観測。**「0 行が返る」ではない** — DB 層の 0 行は TSK-424 の受入条件)
- [ ] **テナント文脈の束縛のうち規律 1・3・4・5 を満たす**(`docs/design/data-model.md:317-329`)。**規律 2(ポリシー側が `current_setting` を読む)は製品 RLS の話なので TSK-424**
- [ ] **アプリ用ロール接続がロール名の完全一致と `pg_auth_members` の推移閉包で検査されている**(`table_owner` で拒否され、**期待ロール名のまま危険ロールへ所属させた負例でも拒否される**)
- [ ] **`TenantContext` の生成箇所が allowlist で機械的に制限されている**(製品モジュールは 0 件)
- [ ] **`backend/pyproject.toml` / `uv.lock` / `backend/tests/conftest.py` の差分がいずれも 0 行**
- [ ] pytest / ruff / ty green

### Notion カードとの食い違い(**人間の判断を求める 3 件**)

| # | カードの記述 | 本書の提案 | 根拠 |
| --- | --- | --- | --- |
| 1 | DoD「**NFR-019 の越境テスト(API 直叩き)**」 | **「対象入口なし」と記録**する。**12-4 の最低要求 4 件は本単位の義務ではない** | 4 件は**ゲートの通過条件②の中身**で、**ゲートの対象は入口を開く PR**(`data-model.md:2528`)。**U-T1 は入口を開かないので対象外**。12-7 (1) の実機確定要求としての 4 件は、**① が TSK-424、②③④ が U-C1 / U-C2 / U-C3 / U-A2** に帰属する([design.md](./design.md) 8-1) |
| 2 | 「**マージの条件(着手とは別)**」節 | **「対象入口なし / TSK-344 は本 PR のマージ条件ではない / PR に判定記録を残す」へ書き換える**(節の削除や単なる「対象外」表記にはしない) | ADR-004 approved で適用単位が精密化され TSK-344 を待たない(`../product-impl-unit-split/plan.md:433-443`)。**一方 12-4 の「判定の記録」(`data-model.md:2534`)は、入口を開かない PR にも「対象入口なし」と書くことを要求**している |
| 3 | スコープ「**越境関数経由のリポジトリ基底**」の前提 | **製品認可面(45 表の許可プロファイル・製品 DDL 資産・写像・移行ロール)を [TSK-424](https://app.notion.com/p/3de93b75e6878172a4b4d2f6edd663fc) へ分離**したことをカードに追記する | 2026-09-17 の裁定(1 節)。**TSK-418 の取り込み決定をこの範囲について撤回**した |

### 承認時点の残件(**実装ステップの中で閉じる** — 計画レビュー 6 周目の P1)

**7 周目は回さない**(残滓ではないが、計画書だけで完全性を目指すより実装ステップで閉じるほうが実際的)。
**各項目は該当ステップの合格条件に含める。**

| # | 残件 | 閉じるステップ |
| --- | --- | --- |
| R-1 | **「immutable」の機械判定が閉じていない** — 許可する DTO の完全修飾名と immutable scalar / container の型文法を資産化し、`Any`・`object`・Iterator 系・非 frozen DTO を拒否する。`ScalarResult` / `Query` / generator / 独自の遅延 Iterable / mutable DTO の負例を足す | **9** |
| R-2 | **キャッシュ無効化契約が 14×5 表だけに縮んでいる** — 正本 11-2 には**波及先・参加変更前後の和集合・全テナント波及・5 種類の物理キー形・無効化意図の永続化と再試行**もある(`docs/design/data-model.md:2082` `:2121`)。**API が純粋な要求生成器か、無効化意図を書き込む repository か**を確定し、後者なら TSK-424 capability への依存を明記する | **10** |
| R-3 | **`db-api-inventory.json` ほかがコア paths から漏れる** — **`contracts/tenant_boundary/**` 全体**をコア paths に入れるか、inventory・base allowlist・キャッシュ契約資産を exact path で全列挙し、各パスを外す変異を red にする | **4** |
| R-4 | **接続時検査と GUC の異常終了境界** — 接続検査終了時の transaction status が idle / 例外 rollback 後の同一物理接続の再利用 / 接続開始時に `app.tenant_id` が非空なら拒否 | **6**・**8** |

## 6. テスト計画

### 6-1. NFR-019 の分類への割り当て

| NFR-019 の項 | 割り当て |
| --- | --- |
| **(a) 一致性** | **該当なし**(本単位はドメイン計算を持たない。NFR-018 の対象列挙に認可機構は入らない — 要件書 `:887`) |
| **(b) 越境アクセステスト** | **入口が未発効**(本単位は入口を開かない)。**要求を当てる対象が無い**(`data-model.md:2532`)。**設計契約の DB 試験は 6-2 で別途足す** |
| **(c) E2E** | **該当なし**(HTTP 経路を持たない) |
| **(d) 故障系** | **該当なし** — (d) は**同期プロトコル固有**(要件書 `:933`)。本単位の `set_config` 未発行・不正 UUID は **(d) ではない** |

### 6-2. 本単位が足すテスト(NFR-019 の分類とは別表)

| 区分 | 内容 | 置き場 |
| --- | --- | --- |
| **単体** | 基底の公開シンボル exact-set / `TenantContext` allowlist / 迂回検査の正例・負例の全数表 | `backend/tests/test_authz_*.py`(平場) |
| **構成検査** | 接続ロールの名前一致と `pg_auth_members` の推移閉包 | **`backend/tests/test_authz_tenant_binding.py`** |
| **DB 統合** | commit 後の GUC 消失 / 並行 2 Session 間の非漏洩 / 基底の発行 SQL にテナント条件が含まれること | 同上 |
| **故障注入**(NFR-019(d) ではない) | **`TenantContext` 無しで業務 SQL の発行 0 件** / autocommit 拒否(`TenantBindingError`)/ 同一 Session の再束縛拒否 / 誤ロール DSN で接続拒否(`DatabaseConfigurationError`)/ `SET ROLE` 偽装 / 昇格経路の負例 / **接続検査後の transaction status が idle** / **例外 rollback 後の同一物理接続の再利用** / **接続開始時に `app.tenant_id` が非空なら拒否**。**「未束縛で 0 行」「不正 UUID の `22P02`」は TSK-424** | 同上 |
| **変異検査** | 迂回検査の有効性(基底へ直接 SQL を足す・条件ごとの綴り違いを注入して red)。**正例が落ちないこと**も同時に検証 | `backend/tests/test_authz_*.py` |

**DB を要するテストは `pytest.mark.requires_db`**。
**DB fixture は `backend/tests/db_fixtures.py`**(ステップ 2 で抽出)を明示 import して共有する。
**`backend/tests/conftest.py` は触らない**(差分 0 行が DoD)。
