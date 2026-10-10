---
feature: um1-player-roster-opponent
status: in-review
承認: 済(2026-10-10・山田正輝 / 第 11 改訂 — 第 10 改訂 2026-10-10・第 9 改訂 2026-10-09・第 8 改訂 2026-10-09・第 7 改訂 2026-10-09・第 6 改訂 2026-10-08・第 5 改訂 2026-10-08・第 4 改訂 2026-10-08・第 3 改訂 2026-10-07・第 2 改訂・第 1 改訂 2026-10-05・初版 2026-09-24)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..
notion: https://app.notion.com/p/3da93b75e687812eb946c4a8cf5fc1a7
branch: feature/um1-player-roster-opponent
created: 2026-09-24
計画レビュー周回: 30       # 敵対レビュー 1 周目(判定 否決・P0 16 / P1 6 / P2 1)/ 改訂 2026-10-05 の 1 周目(否決・P1 3 / P2 2)・2 周目(否決・P1 3 / P2 3)・3 周目(否決・P1 2 / P2 4)・4 周目(否決・P1 3 — PO 裁定で N1〜N4 へ)・5 周目(否決・P1 1〔N3〕/ P2 1)/ 第 2 改訂の 1 周目(否決・P1 4 / P2 1)・2 周目(否決・P1 1 / P2 1)/ 第 3 改訂の 1 周目(否決・P0 2 / P1 2)・2 周目(否決・P1 2)/ 第 4 改訂の 1 周目(否決・P1 4)・2 周目(可決・P2 1)/ 第 5 改訂の 1 周目(可決・P2 1)/ 第 6 改訂の 1 周目(否決・P1 1)/ 第 7 改訂の 1 周目(否決・P0 1 / P1 5 / P2 1)・2 周目(否決・P1 4)・3 周目(否決・P1 1)・4 周目(否決・P1 2)/ 第 8 改訂の 1 周目(否決・P1 1 / P2 2)/ 第 9 改訂の 1 周目(否決・P1 2 — 1 件採用)・2 周目(否決・P1 1 / P2 1)/ 第 10 改訂の 1〜7 周目(すべて否決 — 1 周目 P0 1 を含む。7 周目の反映後に打ち切り)/ 第 11 改訂の 1・2 周目(否決・P1 2・P1 1)の反映を含む
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: U-M1 選手・在籍・対戦相手チーム

> **現行の正(第 10 改訂 2026-10-10)**: **4 節のステップ表・5 節の DoD・6 節のテスト計画・第 10 改訂ブロック・第 11 改訂ブロック**が現行の正である(第 10 改訂と第 11 改訂が食い違う箇所 — UI 設計正本の扱い — は第 11 改訂が正)。それより前の改訂ブロック・承認後の追記・本文の旧記述は、それぞれの時点の記録として残している。両者が食い違うときは現行の正に従う。**#95 の射程はステップ 1〜11**(在籍区分の入口は TSK-447 と同じ後続 PR・選手の削除は TSK-459 の後の PR)。

## 1. 背景・目的

**Notion**: [TSK-393](https://app.notion.com/p/3da93b75e687812eb946c4a8cf5fc1a7)
**出所**: TSK-363 / [`../product-impl-unit-split/plan.md`](../product-impl-unit-split/plan.md)`:212`(承認済 2026-09-13)
**調査メモ**: [research.md](research.md) — **典拠集**(正本ではない。`docs/features/` は作業ディレクトリ)。
本書が事実を述べるときは**正本を直接引く**。research.md は調査の経緯をたどるための索引として参照する。

U-M1 は pitchlog **最初の製品コード**。主所有 FR は 4 件、**分担先なしの単独主所有**
([`../product-impl-unit-split/design.md`](../product-impl-unit-split/design.md)`:75` 帰属表 / `:86-92` 分担表に U-M1 の行なし)。

| FR | 必須度 | 要求の骨子 |
| --- | --- | --- |
| [FR-015](../../requirements/requirements-pitchlog-2026-07-22.md#FR-015)(`:356-364`) | Must | 不変の内部 ID / 名前・投・打 / 背番号は任意・**一意制約を張らない**(同番号は**警告のみで登録続行可**)/ **記録時点の背番号で過去試合を表示** / **試合画面を離れずその場登録**(断中は一時 UUID → 同期時に正式 ID へ置換)/ 入部年度・学年を持たない |
| [FR-017](../../requirements/requirements-pitchlog-2026-07-22.md#FR-017)(`:374-383`) | Must(区分 3 つ)/ ラベルは Should | 3 区分固定 / **OB は候補から完全除外** / **「その他」は初期表示に出ないが明示操作で選択可** / **全区分可逆** / 一括変更は**プレビュー→確認→実行** / **相手チームレコードの選手にも適用** / **カルテ・試合準備画面からも変更できる** / **初期ラベル同梱** / 変更はキャッシュ無効化トリガー |
| [FR-018](../../requirements/requirements-pitchlog-2026-07-22.md#FR-018)(`:385-392`) | **Should** | プレイ紐づけゼロ → **確認の上で非表示化**(ゴミ箱 UI を経ない)/ 紐づく選手は **OB 化へ誘導** / **競合挿入を含めて紐づけ判定と削除が同一トランザクション** / **進行中(未終了)試合があると削除不可で OB 化へ誘導** |
| [FR-039](../../requirements/requirements-pitchlog-2026-07-22.md#FR-039)(`:405-414`) | Must | テナント内レコード・テナント間で共有されない / **試合作成を中断せず登録・選択** / **類似名は重複警告(意図的なら登録可)** / **試合または選手が紐づくチームは削除不可でリネームへ誘導** / **付与によらず 404** |

### 着手時点の与件が覆った点

> **U-M1 はコア領域(機械判定で確定)であり、降格条件は存在しない。**
> Notion カードの「コア判定(機械): 非コア」「降格条件: 6.3 の確定ゲートで (i) が確定すること」は
> [`../product-impl-unit-split/plan.md`](../product-impl-unit-split/plan.md)`:292-315`【承認後の是正】より前のスナップショット。
> **TSK-394 でも同一記述を確認済み**(葉 6 本が同型と見られる)。カード一括訂正の要否は PO 判断。

> **U-T1 の公開面は空で、現時点では DB に到達できない。** 実効依存に **TSK-424** を含む(4 節)。

## 2. スコープ

### やること

- **バックエンド実装** — 選手・在籍区分・対戦相手チームレコードの HTTP 入口とリポジトリ操作、越境テスト。**第 10 改訂: #95 で開く HTTP 入口は選手の作成・一覧・取得・更新(ステップ 9)と対戦相手チームレコード(新ステップ 11)に限る**。在籍区分の入口(プレビューと適用・キャッシュ無効化の発火点)は TSK-447 と同じ後続 PR、選手の削除の入口(FR-018)は TSK-459 の後の PR へ送る(リポジトリ操作はステップ 5 で在籍区分・削除の分も置いた)
- ~~**自 FR の UI 設計正本を書く**~~ **#95 の射程外(第 11 改訂)** — UI 設計書は実在せず(`docs/design/` は `data-model.md`・`sync-protocol.md` だけ)、新設は確定ゲートの対象。UI 設計書を新設するタスク(未起票)へ U-M1 の入口の UI の要求を申し送る。旧記述: 自 FR の UI 設計正本を書く(`../product-impl-unit-split/plan.md:60`「API / UI / データモデルの設計正本を書く = 各単位のタスク」)
- **`.claude/core-areas.json` への paths 登録**(同 `:61`「**各核単位が自 PR で行う**」)

### やらないこと

| 項目 | 理由・送り先 |
| --- | --- |
| **フロントエンド実装(Vue)と Vitest** | **現況(2026-10-10 実測 — 第 10 改訂)**: TSK-508 / PR #110 がフロントエンドの実装単位を定めた(選手・チームの画面は **U-F5** — `../frontend-impl-units/design.md`)。本単位の射程外であることは変わらない。以下は当時の記録 — **正本が帰属を定めていない。**`../product-impl-unit-split/` の plan.md・design.md に「フロントエンド」「Vitest」「Vue」の語が **1 件も無い**(実測)。`:60` が各単位へ送るのは **UI の「設計正本」**であって実装ではない。**受け皿が正本上空席**である事実を 8 節で申し送る |
| **`system_vocabularies` の seed と在籍区分キーの値の決定** | **別タスクへ切り出す**(8 節)。migration は **5 領域すべてのコア paths** で、契約 3(`:181`)の「2 領域以上は例外として明示列挙」に **U-M1 は含まれない**。コミットを分けても PR の変更 path は変わらない。値は U-M2・U-C 系も使う**共有語彙** |
| スタメンの記憶・復元(FR-016) | **U-M2** |
| 試合作成時の相手チーム選択(FR-001) | **U-G1** |
| 試合の削除とゴミ箱(FR-019) | **U-D1** |
| キャッシュ無効化**契約** | **U-T1**(**発火点のみ U-M1** — 同書が「発火は各トリガー所有単位が負う」と申し送り。**第 10 改訂: 在籍区分の入口と発火点は、#95 のマージ後に本タブが TSK-447 と同じ PR で開く(旧ステップ 11)**) |
| 選手統合・分割(FR-035/037) | **U-A2** |
| 移行のファンアウト・在籍棚卸し・名寄せ(FR-038) | **U-X5** |

### 契約 4 — 主所有 FR × 5 コア領域の突合(`:182` が各単位へ要求)

| FR | 同期プロトコル | 状況計算 | 記録権 | テナント分離 | データ移行 |
| --- | --- | --- | --- | --- | --- |
| **FR-015** | **触れる** — 断中の一時 ID → 正式 ID の置換。**機構は U-S1 が持つ**(下記) | 触れない | 触れない | **触れる** — 選手はテナントデータ。全出力経路の越境 | **触れる** — 88 列 63-71 が「移行時に使用」。**機構は U-X5** |
| **FR-017** | 触れない | 触れない | 触れない | **触れる** — 在籍区分の変更が**キャッシュ無効化トリガー 14**(共有集計のみ) | **触れる** — 移行後の在籍棚卸し。**機構は U-X5** |
| **FR-018** | 触れない(下記の判定) | 触れない | 触れない | **触れる** — 削除もテナント境界内 | 触れない |
| **FR-039** | 触れない | 触れない | 触れない | **触れる** — 第三者データは**付与によらず 404**(要件書 `:641`) | **触れる** — チームのファンアウト複製。**機構は U-X5** |

**FR-018 が同期プロトコルに触れないことの判定**(条文の逐語読解):
受入基準(要件書 `:392`)の条件は「**当該チームに進行中(未終了)の試合が存在する**」という**状態の問い合わせ**であり、
括弧内の「断中端末の未同期キューが当該選手を参照している可能性があり、サーバー側のトランザクションでは検知できないため」は
**この保守的な規則を採った理由の説明**である。**未同期キューを読む機構は要求されていない。**
必要なのは ① プレイ紐づけゼロの判定 ② 進行中試合の存在判定 ③ ①②と削除の同一トランザクション化 の 3 つで、いずれも読み取りで閉じる。

**FR-015 の同期面の帰属** — `../product-impl-unit-split/design.md:86-92` の分担表に FR-015 の行が無く、
`../product-impl-unit-split/plan.md:240-252` の「面が切れなかったときの手順」も**対象を FR-007/010/011/019 に限定している**ため、
**FR-015 はその手順の適用対象外**である。したがって本書は手順を代用せず、**8 節で人間の判断を仰ぐ**。
正本上 FR-015 は依然 **U-M1 の単独主所有**であり、帰属表を更新しない限り U-S1 へ移らない。

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/design/data-model.md` / 要件書 / `docs/adr/` | **反映なし**(既決事項に従うのみ。再決定しない) | — |
| **`.claude/core-areas.json`** | **paths を追加**(glob 2 件 — 越境テストの `backend/tests/test_*_boundary.py` とリポジトリのテストの `backend/tests/test_*_repository.py`。本単位の `backend/tests/test_roster_boundary.py`・`backend/tests/test_roster_repository.py` と後続単位の同名規約のテストを覆う。**第 5 改訂で 1 ファイル名から glob へ・第 6 改訂でリポジトリのテストの glob を追加**。新規リポジトリは既存 glob が覆う。**第 7 改訂で API 層の 2 ファイルを追加し、第 8 改訂で API 層全体の glob `backend/src/pitchlog/api/*` へ替え、第 9 改訂で API 層を検証するテスト `backend/tests/test_api_*.py`・`backend/tests/test_roster_*.py`・`backend/tests/test_request_presentation.py` とセンサスのテスト `tests/test_census_baseline_check.py` を追加**)。`:61` が「各核単位が自 PR で行う」と定める。**6.3-⑤ の敵対レビュー + 人間承認の対象** | PR レビュー(6.3-⑤) |
| `scripts/core_guard.py` / `tests/test_core_guard.py`(**改訂 2026-10-05 で追加**) | `AREA_PATH_ADDITIONS["tenant-isolation"]` の宣言と表明の更新(4 節 ステップ 6)。`BASELINE_DEFINITION_PATHS` のため `core-areas.json` と別コミット | PR レビュー |
| `contracts/authz/route-registry.json` / `http-route-matrix.json` (+ lock) | **追記**(`route_kind` の値域は PR #77 で決定済み — `record_and_aggregate`) | PR レビュー |
| `contracts/authz/oracle-seal.lock.json` / oracle 資産(`oracle_commit` 7 箇所)/ `contracts/authz/frozen-baselines.json` / `scripts/check_authz_catalog.py` / `tests/test_check_authz_catalog.py`(**第 2 改訂で追加**) | route-registry と HTTP 行列が oracle 封印の入力資産のため、oracle の追随・凍結基準の記録(series `oracle_input`)・`--reseal-oracle` による再封印。検査器の期待集合の更新(4 節 ステップ 2〜4) | 7.7 の更新経路・**人間の確認**(`reseal_policy`) |
| `contracts/tenant_boundary/census-baseline.json` / `tests/test_census_baseline_check.py`(**第 7 改訂で追加**) | ステップ 9 の登録で消える TB007 の減分を、センサスの緩和の判定で説明する(発行入口・許可モジュール・構築シンボルが資産と一致するものだけ。TSK-457 の裁定 6 に従い anchor は進めない)。`census-baseline.json` は凍結資産で、ステップ 10 の受理記録で識別値を繰り上げる | 7.7 の更新経路(受理記録はステップ 10 の 1 件)・**人間の逐行確認** |
| `contracts/tenant_boundary/repository-contract.json` | **capability 登録**。**`FROZEN_BASELINE_ASSETS` の 1 つ**(`scripts/check_tenant_boundary_bypass.py:41`)なので**設計書 7.7-2 の記録が要る** | 7.7 の更新経路 |
| `contracts/tenant_boundary/base-allowlist.json`(権威履歴)/ 履歴 snapshot / `tests/fixtures/frozen-archive-cases/manifest.json`(**改訂 2026-10-05 で追加**) | 7.7-2 の記録 1 件・snapshot・比較 corpus の digest 再封印(4 節 ステップ 5 の内訳)。**第 4 改訂で追加**: `base-allowlist.json` の `allowed_symbols` へ文の組み立て関数を登録し、シンボルごとの正例 fixture を `tests/fixtures/tenant_boundary/positive/pitchlog/repositories/` に置く(内訳 5 の是正) | 7.7 の更新経路 |
| `contracts/tenant_boundary/tenant-context-allowlist.json` / 配布モジュール `backend/src/pitchlog/repositories/tenant_context_contract.py` / `scripts/check_tenant_boundary_bypass.py` / `tests/test_check_tenant_boundary_bypass.py`(**第 3 改訂で追加**) | 発行専用モジュールの登録と発行入口の 2 欄・0 件必須の分岐の置き換え・テストの改訂(4 節 ステップ 9)。受理記録はステップ 10。allowlist は凍結資産で、検査器は `frozen_projection.external_files` に入る | 7.7 の更新経路(受理記録はステップ 5 の分と合わせて 1 件)・**人間の逐行確認** |
| `.env.example`(**第 3 改訂で追加・該当するときだけ**) | リクエストの認証の設定値を持つ場合に、名前と説明だけを足す(実値なし — NFR-014。N6) | PR レビュー |
| `docs/design/data-model.md` / `docs/features/ua1-team-auth/design.md`(**第 3 改訂で確認 — 反映なし**) | **反映なし**。12-8 節の残件の行は δ を「認証の HTTP の入口」の受け取り先としており、データへ届く入口のリクエストの認証を名指していない。`../ua1-team-auth/design.md` 3 節の δ の行(Cookie と CSRF)は作業ディレクトリの記録で、正本ではない。**帰属の変更(依存表 12)は本書と Notion(TSK-470 へのコメント)に記録する** | — |
| `docs/features/um1-player-roster-opponent/design.md` | **新設**(暫定規約・入口表・DTO 定義)。**第 3 改訂で追記**: リクエストの認証の細部(N6)・発行専用モジュールの名前と置き場(N7) | PR レビュー |
| `docs/development/harness-evaluation.md` / `docs/README.md`(**`/pr` のクローズ処理で追加**) | 台帳の `## 候補` へ 3 件追記・既存候補 4 件へ実測を追記・変更履歴表に 1 行(版は上げない — 7.6-3 前段)/ `docs/README.md` の台帳行の候補件数(129 — develop `24c023e4` 取り込み後に走査で実測)と最終更新日 | PR レビュー(7.6-3 前段) |

## 4. 実装方針

**重さ分類 = コア領域**(機械判定の確定。降格の道は無い)。詳細設計は [design.md](design.md) を正とし本節で複製しない。

### 外部依存(**状態欄は 2026-10-10 に原典で実測し直した — 第 10 改訂**。入口ごとの着手条件は 4 節末の「着手の拘束」と第 10 改訂ブロック。**#95 で開く入口〔ステップ 9・新 11〕の着手条件は満たされている**。依存 9 は在籍区分の入口〔後続 PR〕だけに掛かる)

| # | 要るもの | 所有 | 状態 |
| --- | --- | --- | --- |
| 1 | **capability カタログ**(`contracts/authz/product/capability-catalog.json`) | **TSK-424 PR A** ステップ 21 | **✅ 着地済み(2026-10-10 実測)** — PR #79(TSK-424 PR A1)で `contracts/authz/product/capability-catalog.json` が develop にある。旧記述: 計画レビュー中 |
| 2 | **capability の登録** | **U-M1 自身** | **✅ 済(ステップ 2〜5・10)** — 凍結基準を動かし、7.7-2 の記録を #95 で 1 件にまとめた。旧記述: 凍結基準を動かす(上記 3 節)→ 7.7-2 の記録 + TSK-431 との順序調整 |
| 3 | **Session 供給**(`TenantRepositoryBase._session`) | **TSK-424 PR C** | **✅ 着地済み(2026-10-10 実測)** — TSK-444 / PR #82(2026-10-03 マージ)の `tenant_transaction_scope` がリクエスト専用 Session を供給する(ステップ 9 はこれで結線した)。旧記述: 未着手(PO 裁定 2026-09-24)。供給形式は U-M1 で決めない |
| 4 | **RLS DDL の実スキーマ適用**(12-4 通過条件①) | **TSK-344** | **✅ 適用済み・通過判定の記録は保留(2026-10-10 実測)** — PR #97(2026-10-07 マージ)が製品 authz DDL を実スキーマへ適用し、越境テスト 48 node を再実行して green。**12-4 のゲート通過の判定と記録は保留**(`data-model.md` 12-6・12-8 — 受け取り先未確定)。#95 の 12-4 の判定記録は DoD のとおり #95 が自分の入口について行う。旧記述: 未着手 |
| 5 | ~~**`route_kind` の値域決定**~~ | **✅ 解消済み(2026-10-04 訂正)** — TSK-446 / **PR #77**(2026-09-25 マージ)。`record_and_aggregate` が `ROUTE_KINDS` に入っている。**本表の「空席」は誤記で、本書作成の翌日に解決していた** | **現況: ✅ 解消済み — PR #77 で `record_and_aggregate` が値域に入り、本単位の経路 6 本はステップ 2 で登録済み**。以下は旧記述(当時の記録) — `route-registry.json` と `http-route-matrix.json` は exact-set(`scripts/check_authz_catalog.py:2437-2442`)。`route_kinds` は検査器の定数 `ROUTE_KINDS`(同 `:92`)に固定で、**選手 CRUD を表す種別が無い**。**TSK-380 の射程は既存 37 経路の `test_owner` 再割り当てであって値域拡張ではない** |
| 6 | **検証済みのテナント ID を返す公開入口**(署名照合 → `authn.verify_token()` → 非 NULL の `tenant_id`) | **U-A1 γ(TSK-469)** | **現況: ✅ 着地済み(2026-10-10 実測)— PR #100(2026-10-09 マージ)。ステップ 9 で結線した**。以下は旧記述(当時の記録) — **ステップ 9 の着手条件 — develop に着地済みであること**。**第 3 改訂で書き換え**: 旧記述「`TenantContext` の生成 = U-A1」は裁定 b'(2026-10-05)で分かれた — γ は**検証済みのテナント ID を返すところまで**、`TenantContext` の生成箇所は U-M1 ステップ 9(発行専用モジュールが γ の公開入口を内部で呼ぶ — 内訳 9)(`../ua1-auth-app-layer/plan.md` 4-7 節 — 未マージのブランチ上)。**ログアウトの保護された入口は γ が持つ**(裁定 ⑫・利用者の裁定 (ア) 2026-10-07 — U-M1 はログアウトの入口を持たない) |
| 7 | **在籍区分キーの値と seed** | **別タスク**(8 節) | **✅ 着地済み(第 10 改訂で訂正)** — TSK-475 / PR #94(2026-10-05 マージ・migration `0027_seed_roster_status`)。旧記述: 未起票 |
| 8 | **複数表の不変条件の実行単位** — 入口 **#7**(FR-018 の削除ガード)・**#11**(FR-039 の削除ガード)・**#6**(FR-017 の一括変更)は**複数表にまたがる判定を 1 トランザクションで**行う必要がある | **TSK-444(PR C)** | **✅ 着地済み(第 10 改訂で訂正)** — PR #82(2026-10-03 マージ)が束縛済みトランザクションで複数 operation を実行する単位を足した。旧記述: 未着手。2026-09-24 に当方の指摘を受けて射程へ取り込まれた |
| 9 | **無効化意図の ID 導出規則と原子性の錨** — `contracts/tenant_boundary/cache-invalidation-contract.json` の `durable_intent` は `intent_id_derivation: ["target_event_v10","target_confirmed_version"]` と `same_transaction_with: "T7"` を**トリガー別の分岐なしで 14 件すべてに掛けており**、**イベント由来でない 7 トリガー**(在籍区分の変更を含む)に適用できない | **TSK-447** | 未着手(2026-10-10 実測 — Notion「未着手」・ブランチなし)。**U-M1 側で暫定規約を決めない**(他のトリガー所有単位と割れるため)。**第 10 改訂: 旧ステップ 11(在籍区分の入口)を #95 から外し、#95 のマージ後に本タブが TSK-447 と在籍区分の入口を 1 つの PR で引き取る** |
| 10 | **`system_vocabularies` を参照する FK への category の拘束**(`fk_players_roster_status` ほか 2 本 — 計 3 本) — 着地前に選手の入口を開くと、在籍区分の列に試合区分のキーが入りうる状態になり、入口を開いた後からは回復できない | **TSK-480**(ブランチ `feature/vocab-category-fk`・正本は実装追随の PR レビューで版据え置き — 【裁定 2026-10-06・山田正輝】`../vocab-category-fk/plan.md` 3 節。**第 3 改訂で訂正**: 旧記述「確定ゲートの対象」は同裁定の前の記述) | **現況: ✅ 着地済み(2026-10-10 実測)— PR #104(2026-10-08 マージ)**。以下は旧記述(当時の記録) — **ステップ 9 の着手条件 — develop に着地済みであること**(480 タブの依頼 2026-10-06。第 3 改訂の番号)。U-M1 側のコード変更は要らない見込み(新しい列は既定値付き・FK は同名で張り替え・migration `0029_system_vocab_category_fk`) |
| 11 | **TenantContext の発行の機構と検査器**(公開 constructor の封じ・capability 型・検査器の新しい規則・負例) | **TSK-457**(235 タブ) | **現況: ✅ 着地済み(2026-10-10 実測)— PR #101(2026-10-09 マージ)。ステップ 9・10 で登録と受理記録を行った**。以下は旧記述(当時の記録) — **ステップ 9 の着手条件 — develop に着地済みであること**(第 3 改訂の番号)。人間の裁定(2026-10-05)で、発行専用モジュールの実体・生成許可への登録・生成箇所・7.7 の受理記録は U-M1 に残る。**第 3 改訂でステップ 9(発行・登録・生成箇所)と 10(受理記録)に取り込んだ**(受け取る項目の一覧は TSK-457 の計画書 4-3 節「U-M1 ステップ 8 に渡るもの」— 未マージのブランチ上・同書の「ステップ 8」は第 2 改訂の番号) |
| 12 | **リクエストの認証**(Cookie から提示値を取り出す・CSRF の検査 — 方式は H-2 で決定済み: Cookie は `HttpOnly`・`Secure`・`SameSite=Strict`、CSRF はカスタムヘッダの必須化 + `Origin` の検査。`../ua1-team-auth/design.md` C-4 末尾・3 節) | **U-M1 自身(ステップ 8)** — **【裁定 2026-10-07・山田正輝】δ(TSK-470)から U-M1 へ移す** | **現況: ✅ 済(ステップ 8 — `5899b9c2`)**。以下は旧記述(当時の記録) — **第 3 改訂で追加**。旧来の受け取り先は δ だったが、δ は γ と TSK-344 の後で、しかもレート制限の具体設計(要件書 10 章の相談)を待つ。最初にデータへ届く入口はステップ 9 なので、U-M1 が先に持つ。**Cookie の名前など、H-2 の決定に含まれない細部も U-M1 が先に決め、δ が後から合わせる**(R7) |

> **【承認後の追記 — 2026-09-24】** 上表の **8・9 は承認(2026-09-24)後に判明した外部依存**である。
> **射程・DoD・実装ステップは変えていない**(依存の記録のみ)。
>
> **経緯**: `TenantRepositoryBase._execute_operation` は `_tenant_transaction` の中で 1 文だけ実行し、
> `repositories/binding.py` が「**同一 Session へテナント文脈を再束縛できない**」を課すため、
> **同一 Session では `execute()` を 2 回呼べない**(実測)。
> 一方 TSK-424 の capability カタログ(74 件・`CAP:<table>:<operation>`)は **1 operation = 1 表**を強制する。
> この 2 つが重なると **FR-018 と FR-039 の削除ガードが構造的に実装できない**。
> **TSK-444 が実行単位を、TSK-447 が意図 ID と原子性の錨を引き取った**(2026-09-24・セッション間の調整)。

> **【承認後の追記 — 2026-10-06】** 上表の **10・11 は第 2 改訂の承認(2026-10-05)後に判明した外部依存**である。
> **射程・DoD・実装ステップは変えていない**(依存の記録のみ)。ステップ 8 の射程の変化(裁定 b' と TSK-457 の射程の裁定)は**第 3 改訂**で扱う(作業ログ 2026-10-05 夜の節)。

**製品 operation token 型は TSK-424 の着地前に定義しない。**
[`../tenant-boundary-enforcement/plan.md`](../tenant-boundary-enforcement/plan.md)`:174`(ステップ 9)が
「**製品 capability 集合と越境関数 registry は初期値ともに空集合**とし…**製品表操作は TSK-424 の表分類から生成する capability を受けて初めて有効化する**」と定め、
同 [`design.md`](../tenant-boundary-enforcement/design.md)`:321` が「**ステップ 9 の製品 capability も TSK-424 の出力契約に含める**」と定めているため、
先行定義すると型名・capability ID が生成物と分岐する。

### 非コアで通せる 5 条件 — 本単位には適用されないが「面を混ぜない」規律として守る

`../product-impl-unit-split/plan.md:254-258` が「**葉 6 本は機械判定でコアが確定したので本節の条件では通せない。
ただし 5 条件そのものは葉の計画書でも『面を混ぜない』規律として有効なので下表は残す。**」と定める。
**検査対象 = `git diff -U0 origin/develop...HEAD -- backend/src` の追加行。各式の一致 0 が合格。**

| # | 条件 | 確定した検索式 | 許可側 |
| --- | --- | --- | --- |
| 1 | 新たな認可判定を追加しない | `\b(can_\|may_\|is_allowed\|has_permission\|check_.*_access\|require_role\|assert_.*_owner)` | U-T1 の公開関数の呼び出しのみ |
| 2 | 同期セマンティクスを扱わない | `\b(idempotenc\|idempotent_key\|seq_no\|sequence_no\|tombstone\|revision_no\|generation)\b` | — |
| 3 | NFR-018 の対象計算を含まない | `responsible_pitcher\|earned_run\|at_bat_result\|inning_state\|rbi\|era\|avg\|obp\|slg` | — |
| 4 | キャッシュ無効化契約に触れない | `\b(invalidate\|cache_clear\|evict\|purge_cache)` | `pitchlog.repositories.cache_invalidation` の公開シンボルの import / 参照 / 呼び出しのみ |
| 5 | テナントデータは U-T1 の越境関数経由だけ | `\b(session\.(execute\|query\|scalars)\|select\(\|text\(\|engine\.\|raw_connection)` | U-T1 のリポジトリ基底の継承・呼び出し。**および `base-allowlist.json` の `allowed_symbols` に登録した文の組み立て関数の中の組み立て API(`select(` / `insert(` / `update(`)**(第 4 改訂 — 裁定 2026-10-08)。実行系(`session.execute` ほか)は従来どおり基底だけ |

**条件 3 の注意**: `era` は `operation` の部分文字列に一致する(`../u01-dto-base/plan.md:150` の先例)。**差分行限定**で当てる。
**条件 4 の注意**: `_normalize_identifier`(`scripts/check_tenant_boundary_bypass.py:1440-1445`)が**最後に `.lower()` する**ため、
**`ROSTER_STATUS_CHANGE` という大文字の識別子も TB004 に一致する**。
→ **`from pitchlog.repositories.cache_invalidation import CacheInvalidationTrigger` して `.ROSTER_STATUS_CHANGE` を参照する。
文字列リテラルも同名の自前定数も書かない。**(救済経路 = `allow_condition4`・同 `:3118`・`:3250`・`:3260`)

### 実装ステップ(コミット単位 — 設計書 6.1)

> ## 【改訂 2026-10-04・改訂承認: 山田正輝】着手の拘束をステップ 5 以降へ縮める
>
> **旧**: 「着手は外部依存 1・3・4・5・7 の着地後(**着地前に着手しない**ことを本書の拘束とする)」
>
> **新**: **ステップ 1〜4 は外部依存の着地を待たずに着手する。ステップ 5 以降が 4・6・7 の着地を待つ。**
>
> ### 改訂の理由
>
> **旧の拘束は本書が自分に課したもので、正本から導かれたものではない**(「**本書の拘束とする**」)。
> **2026-09-24 に、当時 5 本すべてが未充足だった前提で書かれている。**
>
> **2026-10-04 の実測で 3 本が着地済み**:
>
> | dep | 状態 |
> | --- | --- |
> | 1 capability カタログ | **✅ develop**(`contracts/authz/product/capability-catalog.json`) |
> | 3 Session 供給 | **✅ develop**(`TenantRepositoryBase._session` — PR #82) |
> | 5 `route_kind` の値域 | **✅ 解消済み**(TSK-446 / **PR #77**・2026-09-25。`record_and_aggregate`)。**本書の「空席」は誤記** |
> | 4 RLS DDL の実適用 | ❌ TSK-344 |
> | 7 在籍区分キーと seed | ❌ TSK-475(2026-10-03 起票・進行中) |
>
> **残る 4・7 は、ステップ 1〜4 の合格条件に現れない**(2026-10-04 実測):
>
> | ステップ | 合格条件 | 4・7 を要するか |
> | --- | --- | --- |
> | 1 `core-areas.json` へ paths 登録 | core-guard が green | **要らない** |
> | 2 DTO を追加 | `test_roster_schemas.py` green + lint/type | **要らない**(純粋なスキーマ定義) |
> | 3 契約資産へ入口を登録(**`test_owner.status` は `planned`**) | `test_check_authz_catalog.py` green・registry と matrix が exact-set | **要らない**(dep 5 のみで、着地済み) |
> | 4 リポジトリと operation token | 契約テスト green + 7.7-2 の記録 | **要らない**(dep 1 のみで、着地済み) |
> | **5 選手の入口を開く** | `ROUTERS` へ登録 | **ここから要る**(**4・6・7**) |
>
> **dep 4 は 12-4 の通過条件①であり、`data-model.md` 12-4 は「マージ条件」であって「着手条件」ではない**
> (`../product-impl-unit-split/plan.md:40`「**最重要の発見**」)。
>
> **ステップ 3 が `test_owner.status = planned` で登録する設計**であることも、
> **入口を「登録するが開かない」段階が最初から想定されていた**ことを示している。

> ### 【2026-10-04 追補】**dep 6 の落としを是正**
>
> **初版の改訂は「ステップ 5 以降が 4・7 を待つ」と書き、`dep 6`(`TenantContext` の生成 = U-A1)を落としていた。**
> **ステップ 5 で入口を開くには、リクエストの認証からテナント文脈を作る γ(`TSK-469`)が要る**
> (本書の依存表 6 番 と R1 は U-A1 を挙げたまま)。**`TSK-469`(γ)は `TSK-468`(β)の後で、β は PR #87 の後。**
> **入口までの最長の系統はこれ**(U-A1 担当の指摘・2026-10-04)。
>
> **したがってステップ 5 以降が待つのは `dep 4`・`dep 6`・`dep 7` の 3 本。**

> ## 【改訂 2026-10-05・改訂承認: 山田正輝】paths 登録を入口の直前へ移し、追加層の宣言ステップを足す
>
> **ステップ番号はこの改訂で付け替えた。上の 2026-10-04 の改訂ブロックの番号は旧番号**
> (旧 1 → 新 5 / 旧 2〜4 → 新 1〜3 / 旧 5〜8 → 新 6〜9 / **新 4 は追加**)。
>
> ### 何が起きたか(2026-10-05 実測)
>
> **旧ステップ 1(`core-areas.json` へ paths を足すだけ)は core-guard を通らない。**
>
> - `scripts/core_guard.py:31` の `AREA_PATH_ADDITIONS`(領域別の追加層)のキーは **`game-state` と `data-migration` だけ**。
>   `validate_area_path_layers()`(`:302-314`)は、宣言の無い領域に `{merge-base の paths}` しか許さないので、
>   **`tenant-isolation` へ 1 件足すだけで `GuardError`**
> - 宣言は `core-areas.json` より**前の別コミット**で入れる必要がある(`verify_area_path_baseline()` `:362-371` が
>   `core-areas.json` と `BASELINE_DEFINITION_PATHS` = `scripts/core_guard.py`・`tests/test_core_guard.py` の**同一コミット変更を拒否**)
> - `tests/test_core_guard.py:1617-1623` が「追加層を持つのは domain-calc の 2 領域だけ・他 3 領域は merge-base と同一」を表明しており、
>   宣言を足すとこれも破れる
>
> 旧 R6 は「同一コミットにしない」までは書いていたが、**宣言のコミットをステップ表に置いていなかった**(#74 の二層方式は本書の承認〔2026-09-24〕より後に着地)。
>
> ### 何を変えたか
>
> 1. **追加層の宣言をステップ 4 として足す**(`core_guard.py` / `test_core_guard.py` — 本書の変更範囲を広げる。**本表直後の「第 2 群を後から足すときの再承認」により敵対レビュー + 人間承認の対象**)
> 2. **paths 登録(旧 1)を新 5 へ移し、入口を開く直前に置く**。登録対象 `backend/tests/test_roster_boundary.py` を作るのは新 6 なので、前倒しする利点が無い
> 3. **新 4・5 は TSK-344 のマージと develop の取り込みの後に行う(本書の拘束)**。TSK-344 も `tenant-isolation` へ paths を足す予定で、
>    **同じ `AREA_PATH_ADDITIONS["tenant-isolation"]` の行を書く**。`validate_area_path_layers()`(`:303-314`)は**宣言の一部だけが merge-base に取り込まれた状態を拒否する**ので、
>    **先着の宣言に U-M1 の 1 件を累積すると新 4 の時点で落ちる**(敵対レビュー 2 周目 P1-2 — 仮の基線・候補で実測済み)。
>    **通る手順は「develop を取り込む → 宣言を U-M1 の未取り込み分だけに置き換える → 新 5 で JSON を merge-base ＋ その分にする」**。
>    TSK-344 以外にも同じ領域の宣言・paths を変えるブランチ(`feature/ua1-auth-db-layer` — 同計画書 `:89-90` が条件付きで変更)があるので、
>    **新 4 の着手時に、`AREA_PATH_ADDITIONS` または `tenant-isolation.paths` を変える未マージのブランチを確認し(対象 ref の範囲は内訳 4)、先着分を取り込んでから行う**
>
> ### 新 1・2 と新 6〜9 は旧 2・3 と旧 5〜8 から番号だけ変えた。新 3(旧 4)は「ステップ 3〜5 の内訳」の 3 を追加した(承認後に着地した登録機構・凍結履歴・比較 corpus への追随)

> ## 【第 2 改訂 2026-10-05・改訂承認: 山田正輝】ステップ 2 を 3 本に分け、oracle の追随と再封印を足す
>
> **番号は第 1 改訂(上のブロック)からさらに付け替えた**: 第 1 改訂の 3 → 5 / 4 → 6 / 5 → 7 / 6〜9 → 8〜11。**新 3・4 は追加**。
> 上の 2 つの改訂ブロックの番号はそれぞれの時点の番号である。
>
> ### 何が起きたか(2026-10-05 実測 — 検査を実際に当てて確認)
>
> `contracts/authz/route-registry.json` と `http-route-matrix.json` は **oracle 封印(`contracts/authz/oracle-seal.lock.json`)の入力資産**で、
> blob digest で固定されている(`input_assets` 8 件)。**経路を 1 本足し、検査器の期待集合と HTTP 行列を合わせ、`--reseal-derived --skip-oracle` で派生 lock を作り直しても、
> 通常の検査は `contracts/authz/route-registry.json: oracle input blob が不一致` で落ちる**(作業ツリーで一時的に変更して実測し、元に戻した)。
> 封印の作り直しは `--reseal-oracle` 専用で人間の確認が要る(`reseal_policy`: `normal_validation_reseals: false` / `human_review_required: true`)。
> **前例は #77(TSK-446)**: 派生 lock の再封印 → oracle の内容追随と 7 箇所の `oracle_commit` 差し替え → 敵対レビューと人間確認 → `contracts/authz/frozen-baselines.json` への記録(series `oracle_input`・`acceptance_id` = PR 番号)と再封印、を別ステップで行った(`../route-kind-vocabulary/plan.md:170-173`・コミット `fb71c300`)。
>
> ### 何を変えたか
>
> 1. **ステップ 2 を「契約資産・検査器・派生 lock」にまとめ、oracle の追随(新 3)と記録・再封印(新 4)を足す**。新 3 は前段(新 2)のコミット SHA を `oracle_commit` に書くので、新 2 と同じコミットにできない
> 2. **PR 番号が要る時点が新 4 へ早まった**(oracle_input の記録の `acceptance_id`)。N3 の判断はステップ 4 の前に行う。新 5(リポジトリ)の tenant_boundary の記録も同じ PR 番号を使う
> 3. **N1・N2 を決めた**(下の N 表と [design.md](design.md) 3 節)
> 4. 登録したパスに実ファイルが当たる確認を、**ファイルを作るステップ(新 8)の合格条件**に置く(TSK-344 の計画レビューで見つかった型 — 登録だけ先に入ると空振りの glob のまま進む窓が空く)

> ## 【第 3 改訂 2026-10-07・改訂承認: 山田正輝】第 2 改訂のステップ 8 を 3 本に分け、リクエストの要求面・`TenantContext` の発行と入口の開放・受理記録の 1 件化を置く
>
> **番号は第 2 改訂からさらに付け替えた**: 第 2 改訂の 8 → 9(発行の追加とあわせて) / 9〜11 → 11〜13。**新 8・10 は追加**。ステップ 1〜7 は番号も内容も変えない。
> 上の 3 つの改訂ブロック・承認後の追記・作業ログの「ステップ 8」は、それぞれの時点の番号である(第 2 改訂の 8 = 本改訂の 9)。
>
> ### 何が起きたか
>
> 第 2 改訂の承認(2026-10-05)の後に、ステップ 8(選手の入口を開く)の射程を変える裁定が 3 つ出た。
>
> | | 裁定 | ステップ 8 への効き方 |
> | --- | --- | --- |
> | 1 | **裁定 b'(2026-10-05・山田正輝)** — `TenantContext` の生成箇所・`allowed_product_modules` への登録・7.7 の受理記録・検査器の 0 件必須の解除を、γ(TSK-469)から**最初の入口を開く U-M1** へ移す(`../ua1-auth-app-layer/plan.md` 冒頭の裁定ブロック・4-7 節) | 生成箇所・登録・記録・0 件必須の解除が増える |
> | 2 | **TSK-457 の射程の裁定(2026-10-05・山田正輝)** — 発行の機構と検査器の新しい規則は TSK-457、発行専用モジュールの実体・登録・生成箇所・7.7 の受理記録は U-M1(TSK-457 計画書 3 節「やらないこと」・4-3 節) | 発行専用モジュールを U-M1 が作る。0 件必須の分岐の置き換えとそのテストの改訂も U-M1(同 4-3 節の 1〜5) |
> | 3 | **リクエストの認証の帰属(2026-10-07・山田正輝)** — Cookie から提示値を取り出し CSRF を検査する部分を、δ(TSK-470)から **U-M1** へ移す(依存表 12) | 要求面(Cookie・CSRF)を U-M1 が作る |
>
> あわせて、**ログアウトの入口は γ が持つ**(利用者の裁定 (ア) 2026-10-07)ので U-M1 の射程に入らない(依存表 6)。
>
> **受理記録は 1 PR につき 1 件**(`contracts/tenant_boundary/base-allowlist.json` の `intermediate_commits_are_records: false`)。#95 はステップ 5 で 1 件持っている。
> ステップ 9 で `tenant-context-allowlist.json` と検査器が動くので、**ステップ 5 の記録を、ステップ 5 と 9 の両方の変更を覆う 1 件へ導出し直す**(2 件目を足すと red)。
>
> **data-model.md v0.6(TSK-382・2026-10-06 承認・PR #98 で develop へ着地)が 12-4 の「実スキーマ」を定義した**。入口を開く本 PR の 12-4 の判定記録(通過条件 ①②)を、v0.6 の 4 要件と「判定の記録」行の必須項目に照らして書けるようになったので、DoD に足す。
>
> ### 何を変えたか
>
> 1. **新 8 = リクエストの要求面**。Cookie(H-2 の属性)から提示値を**不透明な値のまま**取り出し、状態を変える要求で CSRF(カスタムヘッダの必須化 + `Origin` の検査)を検査する。**提示値を分解せず、γ も呼ばず、`TenantContext` も作らない**。外部依存を待たない
> 2. **新 9 = `TenantContext` の発行と選手の入口の開放(1 コミット)**。発行専用モジュールの発行関数が**提示値を受け取り、モジュールの中で γ の公開入口を呼び**、照合を通ったテナント ID からだけ `TenantContext` を作る。`tenant-context-allowlist.json` への登録・検査器の 0 件必須の分岐の置き換え・配布モジュールの追随と、選手の入口(作成・一覧・取得・更新)の配線・`ROUTERS` への登録を**同じコミット**に置く。DTO の `name` の空文字の扱いを token と揃える(ステップ 5 の持ち越し P2)
> 3. **新 10 = 受理記録の 1 件化と比較 corpus の再封印**。ステップ 9 の SHA を受けて、#95 の記録を導出し直す
> 4. **外部依存の表**: 6 を γ の公開入口へ書き換え、10(TSK-480)の正本ゲートの記述を訂正し、12(リクエストの認証)を足す。**着手条件の番号を付け替えた**
> 5. **N6・N7 を足した**(Cookie の名前など δ が決めるはずだった細部 / 発行専用モジュールと発行関数の名前)
>
> ### 区切り方の理由(計画レビュー 1 周目の反映)
>
> - **発行関数が提示値を受け、γ を内部で呼ぶ**: γ の公開入口 `verify_tenant_id` は通常の `UUID | None` を返す(`../ua1-auth-app-layer/` の実装 — 未マージのブランチ)。発行関数がその戻り値を受ける形では、**生の UUID と区別できず、署名を照合していない ID を発行関数へ渡せてしまう**(1 周目 P0)。**提示値 → γ → `TenantContext` を発行専用モジュールの中で閉じれば、発行関数の外に検証済みのテナント ID が現れない**。γ の戻り値の型を変える必要もない
> - **登録と入口の開放を同じコミットにする**: U-T1 は「製品の入口が開く前に allowlist へ製品モジュールが入ることを禁じる」(`../tenant-boundary-enforcement/design.md` 2 節の機構表「未検証の明示」行)。**この規律は受理記録の数え方とは別で、途中コミットにも掛かる**(1 周目 P0)。したがって**登録した製品モジュールが入口より先に存在するコミットを作らない**
> - **受理記録を別ステップに分ける**: 前例はステップ 2〜4(資産の変更 → oracle の追随 → 記録と再封印)。記録は確定した SHA を参照するので、変更と同じコミットに置くと作り直しが要る。ステップ 9 の SHA では凍結履歴の検査が期待どおり落ち、ステップ 10 で解消する
> - **新 8 を分ける**: 新 8 は外部依存を待たない。新 9 と同じコミットにすると、γ・TSK-457・TSK-480 を待つ間、新 8 も止まる

> ## 【第 4 改訂 2026-10-08・改訂承認: 山田正輝】ステップ 5 の是正 — 文の組み立てを許可シンボルへ登録し、検証を確定した状態で当てる
>
> **ステップの番号と表は変えない**。ステップ 5 の是正コミット 1 本(`(ステップ 5 是正)` — 変更と受理記録を同じコミットに置く)を足し、4 節の「5 条件」表の条件 5・3 節・内訳 5・6 節の実行手順を書き換える。
>
> ### 何が起きたか(2026-10-08 実測)
>
> - **ステップ 5 のコミット `3a4a7297` は、迂回検査の条件 5(TB005)で 9 件落ちる**。`backend/src/pitchlog/repositories/roster.py` が `sqlalchemy.select` / `insert` / `update` で文を組み立てているが、`contracts/tenant_boundary/base-allowlist.json` の `allowed_symbols` に、これらの API を許すシンボルが 1 つも無い。**develop の取り込み(`8ada3d9d`)とは無関係** — `3a4a7297` を当時の base `85fce8a7` に対して検査しても同じ 9 件が出る
> - **当時の検証が空振りした理由は 2 つ**
>   - 迂回検査は `git diff {base_ref}...HEAD` の**コミット済みの差分**だけを見る(`base-allowlist.json` の `diff.command`)。ステップ 5 の検証(worklog「`check_tenant_boundary_bypass` ok」)は**コミット前**に行い、`roster.py` は未追跡の新規ファイルだったので検査の母集団に入らなかった(台帳の既存候補「検査器がコミット済みの差分だけを見ると未追跡の新規ファイルがローカルの検証をすり抜ける」と同型)
>   - **PR #95 の CI は 1 度も走っていない**(`gh pr checks 95` が `no checks reported`)。draft 作成後の push で検査が回る前提が成り立っていなかった
> - **根は 2 つの設計の継ぎ目**: TSK-424 の capability 登録は、各単位が SQLAlchemy の公開 API で組み立てた文を token に載せる前提(`../product-authz-surface/design.md` 10 節の登録の検査の保証範囲)。U-T1 の条件 5 は、DB 到達 API(`contracts/tenant_boundary/db-api-inventory.json` は `select` / `insert` / `update` を含む)を `allowed_symbols` の内側だけに許す。**製品のリポジトリは U-M1 が最初なので、この継ぎ目に最初に当たった**。本書の 4 節「5 条件」の条件 5(`select\(` の一致 0)にもステップ 5 は反していた
>
> ### 裁定(2026-10-08・山田正輝)
>
> **文を組み立てる関数を `roster.py` に置き、`base-allowlist.json` の `allowed_symbols` に登録する**(選択肢: 許可シンボルに登録〔採用〕/ 組み立てを基底へ移す / 組み立て API を目録の対象外にする)。
> `allowed_symbols` は基底以外のシンボルにも使われている(`pitchlog.authz.product_provisioning._run_product_operation`・`pitchlog.authz.product_catalog._fetch_catalog_rows`)ので、既存の拡張点の範囲で閉じる。
>
> ### 何を変えたか
>
> 1. **`(ステップ 5 是正)` を足す**(内訳 5 の末尾「是正 — 第 4 改訂」)。`roster.py` の文の組み立てを**少数の組み立て関数**へ集め、各関数を `allowed_symbols` へ登録する。**許す API は文の組み立て(`SQLA_SELECT` / `SQLA_INSERT` / `SQLA_UPDATE`)のうち、その関数が使うものだけ**。文の実行は従来どおり基底(`TenantRepositoryBase._execute_operation` / `_TenantTransaction.run`)だけが行い、capability 検査器の実行直前の検査(単一の実表・テナント条件ほか — ステップ 5)も変えない
> 2. **同じコミットで #95 の受理記録を 1 件追記する**。**現 HEAD の履歴に #95 の記録は無い**(取り込み `8ada3d9d` で権威履歴の衝突を develop 側で解いた。第 3 改訂の「#95 はステップ 5 で 1 件持っている」は取り込み前の状態)。#96 までの履歴を保ち、ステップ 5 と是正の両方の変更(`repository-contract.json` と `base-allowlist.json` の `allowed_symbols`)を覆う 1 件を末尾へ足す。`base-allowlist.json` 自身の `contract_revision` と `current_identifiers` も更新する。**変更と記録を別コミットにしない** — 間のコミットでは検査器が履歴の検証で止まり、TB005 の有無まで到達しない(計画レビュー 1 周目 P1)
> 3. **4 節「5 条件」の条件 5 の許可側**を「U-T1 のリポジトリ基底の継承・呼び出し、**および `allowed_symbols` に登録した文の組み立て関数の中の組み立て API**」へ書き換える
> 4. **検証を確定した状態で当てる**(6 節): 迂回検査と凍結履歴の検査は、**ステップのコミットを作った後に、作業ツリーが清潔で HEAD がそのコミットであることを確かめてから**実行する(検査器はソースを HEAD から、契約資産を作業ツリーから読む)。コミット前に当てた結果を合格の根拠にしない。あわせて、**draft PR の CI が実際に走ったこと**(`gh pr checks 95` に検査が並ぶこと)を、push のたびに確かめる
> 5. **ステップ 10 以降の扱い**: ステップ 10 は #95 の記録を 1 件にまとめる。**ステップ 10 より後(11〜13)に凍結資産を動かすステップは、そのステップの中で記録を導出し直し、1 件のまま保つ**(文を足すなら、既存の組み立て関数を使うか、同じ方式で `allowed_symbols` に登録する)
>
> **ステップ 6・7 はこの是正と独立**(`scripts/core_guard.py` と `.claude/core-areas.json` だけ)なので、是正の前後どちらで行ってもよい。

> ## 【第 5 改訂 2026-10-08・改訂承認: 山田正輝】ステップ 6・7 の paths 登録を、1 ファイル名から越境テストの glob へ替える
>
> **ステップの番号と表の行数は変えない**。ステップ 6・7 の宣言値と合格条件、3 節の `core-areas.json` の行を書き換える。
>
> ### 何が起きたか
>
> - `scripts/core_guard.py` の `AREA_PATH_ADDITIONS` は**累積台帳ではなく、いま追加中のものだけを載せる回転式の窓口**で、宣言の一部だけが基線へ取り込まれた状態を拒否する(`validate_area_path_layers()`)。**同じ領域へ paths を足す単位は 1 本ずつしか通れない**
> - `tenant-isolation` は既存の glob で、後続単位のリポジトリ(`backend/src/pitchlog/repositories/*`)・migration・DB テストを覆っている。**覆わないのは越境テストだけ**で、後続 17 単位も同じ形の越境テストを 1 本ずつ持つ(469 master の実測と提案 — 2026-10-08)
> - 1 ファイル名で登録すると、後続 17 単位がそれぞれ窓口を通る。**glob `backend/tests/test_*_boundary.py` で登録すれば、窓口の通過は本単位の 1 回で済む**
>
> ### 裁定(2026-10-08・山田正輝)
>
> **glob で登録する**(選択肢: glob へ替える〔採用〕/ 1 ファイル名のまま)。
>
> ### 何を変えたか
>
> 1. **宣言値**(内訳 6)と**登録値**(ステップ 7・内訳 7)を `backend/tests/test_*_boundary.py` にする。照合は `fnmatch.fnmatchcase`(`*` は `/` を跨ぐ)なので `backend/tests/test_roster_boundary.py` に当たる
> 2. **遡及の確認を合格条件に足す**(内訳 7): ステップ 7 の時点でこの glob に当たる追跡ファイルが 0 件であること。既存の `backend/tests/test_type_boundary_contract.py` は末尾が `_contract.py` なので当たらない(2026-10-08 の実測 — ステップ 7 で取り直す)
> 3. **空振りの扱いは 1 ファイル名のときと同じ**: ステップ 7 の時点では 1 ファイル名でも実ファイルは 0 件で、作るのはステップ 9。当たるファイルが 0 件の登録は develop にすでにある(`backend/src/pitchlog/generated/*` が `game-state`・`data-migration` に登録され、ディレクトリは無い — 469 master の実測 2026-10-08)。ステップ 9 の合格条件(登録したパスが実ファイルに当たる)はそのまま効く
> 4. **命名規約の受け取り先**: glob が後続単位に効くのは、後続が越境テストを `backend/tests/test_<単位>_boundary.py` と名付けるときだけ。**規約を書く場所は本単位の射程の外**(単位分割の正本 `../product-impl-unit-split/` は U-M1 の所有でない)。**[TSK-485](https://app.notion.com/p/3f093b75e68781af9bd4fc3d31b536c5)(コア領域の paths を足す手順の文書化 — 未着手)の射程に乗るので、同タスクへ申し送る**(8 節 13)。本単位は自分の越境テストをこの名前で作る。**後続が揃わなければ、その単位の越境テストには当たらず、その単位は自分で窓口を通る**。**逆に、`fnmatch` の `*` は `/` を跨ぐので、規約外のファイル(例: `backend/tests/` の下位ディレクトリにある `test_*_boundary.py`)が将来この glob に当たりうる**。当たった場合はコア領域が広がる側(強化レビューの対象が増える側)に倒れ、保護が抜ける側には倒れない。**TSK-485 への申し送りには、後続単位が越境テストを足すときに、この glob に当たる実パスを照合して意図どおりかを確かめることを含める**(計画レビュー 1 周目 P2)
> 5. **ステップ 6 のテストの注意**: TSK-344(#97)が `tenant-isolation` の宣言を置き、`tests/test_core_guard.py` にその宣言を名指しで固定するテスト(`test_product_rls_declaration_matches_planned_and_tracked_paths` ほか)を足した。取り込み後は 344 の paths が merge-base 側に入り、ステップ 6 で宣言を本単位の分へ置き換えるので、**344 の宣言を固定する表明も同じコミットで、取り込み後の状態に合わせて直す**(内訳 6 の行番号の参照は第 1 改訂時点のもの — 着手時に原典で取り直す)

> ## 【第 6 改訂 2026-10-08・改訂承認: 山田正輝】ステップ 6・7 の宣言値・登録値にリポジトリのテストの glob を足し、ステップ 2 の取りこぼしを是正する
>
> **ステップの番号と表の行数は変えない**。ステップ 6・7 の宣言値と合格条件・3 節の `core-areas.json` の行を書き換え、ステップ 2 の是正を 1 コミット足す。
>
> ### 何が起きたか
>
> - **PR #95 の CI(`2040ed8d`)で harness が 2 件落ちた**。どちらも本単位の過去のステップに起因し、ローカルではルートの全件を回していなかったため取り逃がした
> - **① ステップ 5 のテストがコア領域の外にある**: `tests/test_core_guard.py` の `test_all_schema_contract_assets_match_an_actual_core_area_path` は、`backend/tests/` のうちスキーマ契約に触れるテスト(本文に `pitchlog.db` などを含むもの)がいずれかの領域の paths に当たることを要求する。ステップ 5 で足した `backend/tests/test_roster_repository.py` は ORM を import するが、どの paths にも当たらない。**後続単位もリポジトリのテストを 1 本ずつ持つので、同じ形が繰り返し出る**
> - **② ステップ 2 のテスト用 fixture の取りこぼし**: ステップ 2(`98ad97de`)で `scripts/check_authz_catalog.py` の `record_and_aggregate` の期待集合を本単位の 6 本にしたが、`tests/test_check_authz_catalog.py::test_atomic_claim_fixture_is_valid_and_referenced_downstream` が使う `tests/fixtures/authz_claims/route-registry.json`(09-03 から develop にある)には 6 本が無く、「不足 = 6 本」で落ちる
>
> ### 裁定(2026-10-08・山田正輝)
>
> **①はリポジトリのテストの glob を足して 2 本にする**(選択肢: glob を 2 本にする〔採用〕/ 1 ファイル名 `backend/tests/test_roster_repository.py` を足す)。
>
> ### 何を変えたか
>
> 1. **宣言値**(内訳 6)と**登録値**(ステップ 7・内訳 7)を **`("backend/tests/test_*_boundary.py", "backend/tests/test_*_repository.py")`** の 2 本(この順)にする
> 2. **遡及の確認を書き換える**(内訳 7): ステップ 7 の時点で、`test_*_boundary.py` に当たる追跡ファイルは 0 件、`test_*_repository.py` に当たる追跡ファイルは **`backend/tests/test_roster_repository.py`(本単位のステップ 5)と `backend/tests/test_authz_runtime_contract_repository.py`(develop の既存 — `backend/tests/test_authz*.py` ですでに `tenant-isolation` に入っている)の 2 件だけ**であること(2026-10-08 の実測 — ステップ 7 で取り直す)。**本単位のもの以外で当たるファイルは、ステップ 7 の前から `tenant-isolation` に入っているものに限る**(新たにコア領域へ入るのは本単位のファイルだけ)
> 3. **ステップ 6 の合格条件の例外**: `test_all_schema_contract_assets_match_an_actual_core_area_path` はステップ 5 から赤のままで、**JSON へ登録するステップ 7 で緑になる**(宣言だけのステップ 6 では赤のまま — 検査器は宣言後も JSON が merge-base のままの状態を許す)。ステップ 6 の合格条件は「この 1 件を除いて `tests/test_core_guard.py` が green」、ステップ 7 の合格条件は「この 1 件を含めて green」とする
> 4. **空振りの扱い**: `test_*_boundary.py` は第 5 改訂のとおりステップ 9 まで空振りを許す。`test_*_repository.py` は登録の時点で当たる
> 5. **TSK-485 への申し送りに足す**: リポジトリのテストの命名 `backend/tests/test_<単位>_repository.py` も同じ規約に含める。`*` が `/` を跨ぐ注意と、後続単位が実パスを照合することは第 5 改訂の 4 と同じ
> 6. **②はステップ 2 の是正を 1 コミット足す**(件名に `(ステップ 2 是正)`): `tests/fixtures/authz_claims/route-registry.json` に本単位の 6 本を足し(`contracts/authz/route-registry.json` の 6 行と同じ内容を基本にし、fixture の他の行の書き方に合わせる)、`test_atomic_claim_fixture_is_valid_and_referenced_downstream` を緑にする。**同じ fixture を使う他のテストの期待を壊さない**。fixture に付随する digest・lock があれば同じコミットで追随させる。**検査器の期待集合と契約資産には触れない**。ステップ 6 の前に行う
> 7. **検証の規律を足す**(第 4 改訂の「検証を確定した状態で当てる」に追加): **push の前に、清潔な HEAD でルートの `uv run pytest tests/` の全件と `scripts/check_frozen_baselines.py --ci`(`GITHUB_EVENT_NAME=push`)を回す**。全件の失敗は、取り込みのトポロジーに由来する既知の偽陽性(「HEAD の履歴に staged 製品資産がありません」— worklog 2026-10-08)だけであることを確かめ、それ以外の失敗が 1 件でもあれば push しない。**push の後は CI の core-guard 以外の全ジョブ(harness を含む)が合格したことを確かめる**(core-guard は draft の間、逐行確認の欄が未記入で赤のまま)


> ## 【第 7 改訂 2026-10-09・改訂承認: 山田正輝】比較 corpus の前版照合を現版だけにし、ステップ 10 にセンサス基準の更新を足し、API 層の 2 ファイルを `tenant-isolation` に登録し、取り込み後の宣言の張り替えを記録する
>
> **ステップの番号と表の行数は変えない**。内訳 5・10 の合格条件「前版・現版の全ケース一致」を書き換え、ステップ 10 の変更範囲にセンサス基準の判定を足し、ステップ 6・7 の宣言値・登録値に API 層の 2 ファイルを足す是正を 2 コミット置き、2 回目の取り込みで行った宣言の張り替えを N4 の再導出の一つとして記録する。
>
> ### 何が起きたか
>
> - **① 前版の照合が実行できない**: 内訳 5(`:431`)は、比較 corpus の runner を `--checker previous=<前版> --checker current=<現版>` で当て、全ケースで manifest の期待値と一致することを求める。前版は manifest の `comparison_revision`(develop と同じ `ec02a0d2`)だが、**TSK-457(#101)が tenant-context-allowlist に足した契約のキーを `ec02a0d2` の検査器は読めず、前版の実行そのものが失敗する**。契約を読める版(ステップ 9 の `c0aac005`)を前版にすると、#101 以降の検査強化で 5 ケース(4・5・6・7・11)が manifest の前版の期待値と食い違う(6/11)。**#101(develop への統合 `8164c87a`。#101 のブランチ側の取り込み `496a3c48`)と #81 も corpus の digest を張り直しただけで、前版の照合はしていない** — develop 自身がこの条件を満たしていない。現版は 11/11 で一致する(本単位の取り込み 1 回目は `9b006eed`)
> - **② センサス基準がステップ 9 で落ちた**: ステップ 9 の SHA の全件で `tests/test_census_baseline_check.py` の 5 件が落ちた。発行モジュールを `allowed_product_modules` に登録したことで、`tenant_context_issuance.py` の `TenantContext` 構築の TB007 が消え、その減分が宣言済みの緩和(`removed_tb007_matches_declared_relaxations`)で説明できない。センサスの一般化(TSK-457 の裁定 6 — 2026-10-07)は本書の第 3 改訂より後に着地したので、本書は扱っていない
> - **④ API 層の 2 ファイルがコア領域の外にある**: ステップ 9 で足した `backend/src/pitchlog/api/tenant_access.py`(提示値の照合に失敗したら拒否する強制点)と `backend/src/pitchlog/api/routers/players.py`(テナントのデータを返す API の入口)は、どの領域の paths にも当たらない(API 層はもともとどの領域にも入っていない)。**ハーネス設計書 6.3 の境界定義表は、テナント分離に「テナント境界の認可判定すべて」と出力経路の「API 直叩き」を含め、paths の落とし込み規則 ① は強制点を変え得るファイルを含め、迷えば含む側に倒す(fail-closed)と定める**(`../../development/dev-harness-design-2026-08-07.md` 6.3)。第 7 改訂の計画レビュー 1 周目の P0
> - **③ 取り込み後の宣言の張り替え**: #81 の取り込み(2 回目)で merge-base が進み、#81 の宣言が merge-base の JSON に入った。`AREA_PATH_ADDITIONS` を本単位の 2 glob だけへ張り替えるコミット(`04058d29`・件名 `(ステップ 6 再導出)`)を、JSON を触らずに置いた。N4 は再導出のコミット先を authz(ステップ 2〜4)と tenant_boundary(ステップ 5)だけ定めていた
>
> ### 裁定(2026-10-09・山田正輝)
>
> **①は現版だけで判定する**(選択肢: 現版だけで判定〔採用〕/ 前版を契約を読める版へ付け替えて manifest の前版の期待値を取り直す — 他の PR も使う共有の基準を本単位が動かすことになるので不採用)。**④は 2 ファイルを `tenant-isolation` に登録する**(当初「登録しない」と裁定したが、正本の境界定義に反するとの計画レビューの P0 を受けて改めた)。
>
> ### 何を変えたか
>
> 1. **内訳 5・10 の合格条件**: 「前版・現版の全ケース一致」を「**現版の全ケース一致**。前版(`comparison_revision`)と manifest の前版の期待値・`recorded_exit_codes` は develop と同じ値のまま変えない」へ書き換える。ステップ 11〜13 で凍結資産を動かすときの再導出(第 4 改訂の 5)も同じ。**残る保証**: 現版の検査器が corpus の全ケースで manifest の green/red の期待どおりに判定すること、corpus の入力 digest が再 pin した値と一致すること。**失う保証**: 前版の判定の再現・版間の判定の遷移(前版で green だったケースが現版で黙って red になる、またはその逆)の検出・現版の厳密な終了コード(runner の現版の終了コードの期待値は `null` — `tests/fixtures/frozen-archive-cases/runner.py:136`)。**manifest の前版の値は、以後は検証されない履歴値になる**
> 2. **ステップ 10 の変更範囲にセンサス基準を足す**: `contracts/tenant_boundary/census-baseline.json`(受理記録で識別値を繰り上げる 8 資産の 1 つ)と `tests/test_census_baseline_check.py` の緩和の判定。TSK-457 の裁定 6 に従い **anchor は進めない**。判定に足す説明は「**発行入口のシンボル・許可モジュール・構築シンボルがすべて資産の値と一致する TB007 の減分**」だけで、別の範囲(発行入口以外の関数・許可外のモジュール)の減分は説明しない負例を同じコミットに置く。検査を緩めて通さない
> 3. **N4 に宣言の張り替えを足す**(N4 の表にも同じ行を書く): 取り込みで merge-base が進み、他単位の宣言が merge-base の JSON に入ったときは、`scripts/core_guard.py` と `tests/test_core_guard.py` だけを変える 1 コミット `(ステップ 6 再導出)` で宣言を本単位の分へ張り替える。**取り込みのマージでは、基線定義(`core_guard.py`・`test_core_guard.py`)は develop の版をそのまま採り(著者の手を入れない)、著者が解決するのは JSON の合成だけにする**。マージコミットは検査の母集団から抜ける(台帳の候補「検査器の母集団からマージコミットが抜ける」)ので、その穴に頼らないよう、**マージの各親との差分を独立に確かめ、著者が解決した変更が JSON の合成だけであることを worklog に記録する**。2 回目の取り込み `b7e108f1` はこの形で作った(基線定義は develop の版・JSON は develop の `tenant-isolation.paths` の末尾に本単位の 2 glob を残した合成)。履歴は作り直さない(後続の `(ステップ 3 再導出)` が SHA で参照し、人間の再確認が済んでいる)
> 4. **API 層の 2 ファイルを登録する**(④): ステップ 6・7 の是正を 2 コミット置く。`(ステップ 6 是正)` で宣言値を **`("backend/tests/test_*_boundary.py", "backend/tests/test_*_repository.py", "backend/src/pitchlog/api/tenant_access.py", "backend/src/pitchlog/api/routers/players.py")`**(この順)にし、`tests/test_core_guard.py` の独立の期待値と 4 負例を追随させる(JSON は触らない)。`(ステップ 7 是正)` で `.claude/core-areas.json` の `tenant-isolation.paths` の末尾に 2 ファイルを足す(基線定義は触らない)。どちらも 1 ファイル名なので遡及の確認は不要で、登録の時点で実ファイルに当たる。**本改訂の承認は paths を追加する方針の承認**であり、**実際の JSON と宣言の差分は、6.3-⑤ に従い 2 コミットそれぞれの敵対レビューと、PR の人間の逐行確認で審査する**(計画の承認では代えない)。後続単位が API の入口を足すときの登録の規約は TSK-485 への申し送りに足す
>

> ## 【第 8 改訂 2026-10-09・改訂承認: 山田正輝】API 層の登録を 2 ファイル名から `backend/src/pitchlog/api/*` の glob 1 本へ替える
>
> **ステップの番号と表の行数は変えない**。第 7 改訂の 4(API 層の 2 ファイルの登録)の宣言値・登録値だけを書き換える。第 7 改訂の他の項目は変えない。
>
> ### 何が起きたか
>
> - 第 7 改訂の 4 に沿って作った `(ステップ 6 是正)`(`e22b141d`)・`(ステップ 7 是正)`(`1e45c107`)の敵対レビューで、`1e45c107` が否決(P1 1)。**同じ PR で足し・変えた API 層の強制点 3 ファイルがどのコア領域にも当たらない**: `backend/src/pitchlog/api/request_presentation.py`(ステップ 8 — Cookie・CSRF の検査)・`api/errors.py`(拒否の応答 — 401・403 と認可の 403→404)・`api/app.py`(入口〔ルータ〕の登録)。ハーネス設計書 6.3 の境界定義(テナント分離 — 認可判定・API 直叩き)と paths の落とし込み規則 ①(強制点を変え得るファイル)に当たる。第 7 改訂で 2 ファイルに絞ったのは見落とし
> - 2 コミットは未 push
>
> ### 裁定(2026-10-09・山田正輝)
>
> **API 層全体を glob `backend/src/pitchlog/api/*` 1 本で登録する**(選択肢: glob 1 本〔採用〕/ 3 ファイルを個別に足して 7 件)。規則の「迷えば含む側に倒す(fail-closed)」「過剰包含は PR 単位の例外で外さず、モジュール分割で境界を切ってから paths を狭める」(6.3 の規則 ④)に沿う。後続単位が足す API の入口も自動で覆う。**代わりに、DTO(`api/schemas/*`)や `/health`・`/version`(`api/routers/meta.py`)だけを触る PR もコア領域の扱い(敵対レビュー・人間の逐行確認)になる**ことを受け入れる
>
> ### 何を変えたか
>
> 1. **宣言値・登録値**: 第 7 改訂の 4 の 4 件を **`("backend/tests/test_*_boundary.py", "backend/tests/test_*_repository.py", "backend/src/pitchlog/api/*")`**(この順・3 件)へ替える。`fnmatch.fnmatchcase` の `*` は `/` を跨ぐので `api/routers/*`・`api/schemas/*` も覆う
> 2. **コミットの作り直し**: 未 push の `e22b141d`・`1e45c107` は捨て、`(ステップ 6 是正)`・`(ステップ 7 是正)` を 3 件の値で作り直す。合格条件は内訳「6・7 の是正(第 7 改訂)」と同じ形(1 本目の SHA は期待どおり赤 — JSON の追加 2 件に対し宣言 3 件。2 本目で ①〜⑤)。② は「`backend/src/pitchlog/api/*` に当たる追跡ファイルが、`tenant-isolation` のパターンだけを渡した `matched_paths()` ですべて返る」へ読み替える
> 3. **遡及の確認**(2 本目の SHA): `backend/src/pitchlog/api/*` に当たる追跡ファイルが API 層の 11 件だけであること(2026-10-09 の実測 — `api/__init__.py`・`app.py`・`errors.py`・`request_presentation.py`・`tenant_access.py`・`routers/{__init__,meta,players}.py`・`schemas/{__init__,base,roster}.py`)。API 層の外のファイルが当たらないこと
> 4. **TSK-485 への申し送り**(8 節 13 行)を「API 層は glob で `tenant-isolation` に入っているので、後続単位の入口は自動で覆われる。API 層の外に強制点を置くときは実パスを照合して登録する」へ書き換える
> 5. DoD・3 節・6 節の 4 件の記述を 3 件へ追随させる
>

> ## 【第 9 改訂 2026-10-09・改訂承認: 山田正輝】API 層を検証するテストとセンサスのテストを `tenant-isolation` に足す
>
> **ステップの番号と表の行数は変えない**。第 8 改訂の宣言値・登録値(3 件)に 4 件を足して 7 件にする。第 8 改訂の他の項目は変えない。
>
> ### 何が起きたか
>
> - 第 8 改訂に沿って作った `(ステップ 6 是正)`(`9300ff48`)は可決、`(ステップ 7 是正)`(`37b282fb`)は否決(P1 1)。**同じ PR で足し・変えた API 層の契約を検証するテスト 4 本がどの領域にも当たらない**: `backend/tests/test_request_presentation.py`(Cookie・CSRF)・`test_api_conventions.py`(規約・403→404)・`test_api_app.py`(入口の登録)・`test_roster_schemas.py`(応答の項目)。ハーネス設計書 6.3 の paths の落とし込み規則 ①「コアの不変条件・強制点・契約(ベクタ・スキーマ・**テスト**)を変え得るファイルを含める」に当たる
> - 第 7 改訂から周を追うごとに登録が外側へ広がった(2 ファイル → API 層全体 → そのテスト)。打ち切り(テストの登録を TSK-485 へ申し送る)・テスト全体の glob も選択肢として示した
> - `9300ff48`・`37b282fb` の後ろに develop の取り込み(3 回目 `b180f647`)と `7aa721cd` を積んだので、作り直しはせず、**是正 2 コミットを足す**
>
> - 計画レビュー 1 周目で、`origin/develop...HEAD` の変更 78 ファイルの全数照合から、**`tests/test_census_baseline_check.py`**(ステップ 10 で変更 — 許可された発行入口だけに `TenantContext` の構築を認める契約を検証する)もどの領域にも当たらないと出た。テナント境界の他の検査テスト(`tests/test_check_tenant_boundary_bypass.py`・`tests/test_frozen_history.py` ほか)は登録済みなので揃える。同じ照合で feature 文書(`design.md`・`plan.md`)の登録も指摘されたが、**不採用**(現行の `core-areas.json` が登録する文書は正本〔`docs/design`・`docs/requirements`・`docs/adr`・`docs/ops`〕だけで `docs/features` は 1 件も無い。計画書は計画レビューと人間承認のゲートを別に通る)。残る未登録は `guard_paths`(`core-areas.json`・`core_guard.py`)と調査・作業記録(`research.md`・worklog)だけ
>
> ### 裁定(2026-10-09・山田正輝)
>
> **glob 2 本と 1 ファイルを足す**(選択肢: 足す〔採用〕/ 打ち切って TSK-485 へ申し送る / `backend/tests/test_*.py` で backend のテスト全体を覆う)。
>
> ### 何を変えたか
>
> 1. **宣言値・登録値**: **`("backend/tests/test_*_boundary.py", "backend/tests/test_*_repository.py", "backend/src/pitchlog/api/*", "backend/tests/test_api_*.py", "backend/tests/test_roster_*.py", "backend/tests/test_request_presentation.py", "tests/test_census_baseline_check.py")`**(この順・7 件 — 最後の 1 件は計画レビュー 1 周目の採用)。`test_roster_*.py` は `test_roster_boundary.py`・`test_roster_repository.py` にも当たる(先頭 2 本の glob と重なる — 同じ領域の中の重なりで、検査器は paths の列を比べるので影響しない)
> 2. **コミット**: 内訳「6・7 の是正」と同じ形で 2 コミットを足す。`(ステップ 6 是正)` で宣言を 7 件にし(JSON は触らない — この SHA は期待どおり赤: 宣言 7 件に対して JSON の追加 3 件)、`(ステップ 7 是正)` で JSON の `tenant-isolation.paths` の末尾に 4 件を足す。2 本目の合格条件は内訳「6・7 の是正」の ①〜⑤ を 7 件で読み替え、② は「新しい 4 件に当たる追跡ファイルが `tenant-isolation` のパターンだけを渡した `matched_paths()` ですべて返る」
> 3. **遡及の確認**(2 本目の SHA): 新しい 4 件に当たる追跡ファイルが次の 9 件だけであること(2026-10-09 の実測): `tests/test_census_baseline_check.py`・ `backend/tests/test_api_app.py`・`test_api_conventions.py`・`test_api_errors.py`・`test_api_schemas.py`(develop の既存 3 件を含む — U-00 の API 規約のテストで、新たにコア領域へ入る)・`test_roster_boundary.py`・`test_roster_repository.py`(既に登録済み)・`test_roster_schemas.py`・`test_request_presentation.py`
> 4. **TSK-485 への申し送り**(8 節 13 行): 後続単位のテストは `backend/tests/test_<単位>_*.py` の命名なら、単位ごとの glob を足す必要がある(本単位は `test_roster_*.py`)。API 層の規約のテストは `test_api_*.py` で覆われる
> 5. DoD・3 節の 3 件の記述を 7 件へ追随させる
>

> ## 【第 10 改訂 2026-10-10・改訂承認: 山田正輝】ステップ 11(在籍区分の入口)と 12(選手の削除)を #95 の射程から外し、後続 PR へ移す
>
> **ステップ表を付け替える**: 旧 11(在籍区分)・旧 12(選手の削除)の行を外し、**旧 13(対戦相手チーム)を新 11 とする**。ステップ 1〜10 は番号も内容も変えない。上の改訂ブロック・承認後の追記・作業ログの「ステップ 11〜13」は、それぞれの時点の番号である。あわせて DoD の FR-017 行と FR-018 行と 12-4 の判定対象の入口・6 節の「在籍区分変更後のキャッシュ失効」行・3 節(分担)の発火点の行・依存表 8・9 の状態欄を書き換える。
>
> ### 何が起きたか
>
> - **ステップ 11(在籍区分の入口 — プレビューと適用・キャッシュ無効化の発火点)は 2 つを待つ**(2026-10-10 の実測): ① **TSK-447**(無効化意図の ID の導出規則と原子性の錨を、イベント由来でないトリガーへ定義する — 依存表 9)— Notion は「未着手」・最終更新 2026-09-24、ブランチ・worktree・計画書なし。`invalidation_intents` 表(migration `0015_invalidation_intents`)は `UNIQUE (tenant_id, intent_id)` で、導出規則は `target_event_v10` ＋ 確定版だけ。在籍区分の変更には ID を作る規則が無い。本書(依存表 9)と TSK-447 のカードの両方が「U-M1 だけで暫定の規則を決めない」とする ② **無効化の記録・配信の仕組み** — `backend/src/pitchlog/repositories/cache_invalidation.py` は要求の値を組み立てるだけで「永続化・配信・発火は後続の所有単位」と明記する
> - **発火点だけを切り離して入口を先に開く案は、正本に反する**(第 10 改訂の計画レビュー 1 周目の P0): 正本 `docs/design/data-model.md` 11-2 節(`:2160-2168`)は在籍区分の変更をトリガー 14 とし(OB 化した選手のデータが失効前のキャッシュから返り得るため)、要件書 6.2 は対応表を「**各操作の受け入れテストに含める**」と無条件に要求し、「**事前集計を採らない場合も必要**」と明記する。FR-017 の受け入れ基準(要件書 `:390-399`)に無効化が書かれていなくても、在籍区分の変更そのものの受け入れ条件として無効化が掛かる
> - **依存表 8(複数表の不変条件の実行単位)は着地済み**: TSK-444 の PR #82(2026-10-03 マージ)が束縛済みトランザクションで複数 operation を実行する単位を足した。依存表の「未着手」は古い記述。旧ステップ 13(新 11 — 対戦相手チーム)はこの単位で着手できる
> - **ステップ 12(選手の削除 — FR-018)は TSK-459 を待つ**(第 10 改訂の計画レビュー 2 周目の P1): 要件書 FR-018(`:407`)は「削除と同時に別端末がプレイを記録しても、判定後に紐づいた場合は削除が失敗する」を求め、ステップ 12 の合格条件はその競合テストを含む。#82 は複数 operation の実行単位を足しただけで、この保証は**TSK-459**(選手が非表示のときに紐づけを作れないことを保証する機構 — 紐づけを作るのは同期適用経路で U-M1 単独では閉じない — `../tenant-session-supply/design.md` 5 節)へ送られている。TSK-459 は Notion「着手可」・最終更新 2026-09-26・ブランチなし(2026-10-10 実測)。FR-018 はリハーサルの最小集合の外(469 master の実測)
>
> ### 裁定(2026-10-10・山田正輝)
>
> **ステップ 11 を丸ごと #95 から外す**(選択肢: 丸ごと外す〔採用〕/ #95 の中で TSK-447 を吸収する — 正本 11-2 節の改訂〔確定ゲート〕と凍結資産の変更で #95 が数日遅れ、U-F5・U-F8 の入口が遅れる / 先行開放の例外を正本の確定ゲートで承認する — 吸収とほぼ同じ費用)。当初の「発火点だけを切り離して入口を #95 で開く」裁定は、上の P0 を受けて改めた。**ステップ 12 も #95 から外す**(選択肢: 外す〔採用〕/ 競合の保証なしで先に開く — 要件書の受け入れ基準を満たさないまま入口を開く / #95 の中で TSK-459 も吸収する — 同期適用経路〔U-S1 の領域〕まで射程が広がる)。
>
> ### 何を変えたか
>
> 1. **旧ステップ 11・12 は #95 の射程外**: #95 は新ステップ 11(旧 13 — 対戦相手チーム)の後に閉じる。**連番に付け替える理由**: 欠番のまま `(ステップ 13)` をコミットすると、現在地導出が「完了ステップに欠番がある」と判定する(`scripts/feature_status.py` — 計画レビュー 3 周目の P1)。後続の在籍区分・選手の削除は、それぞれの後続 PR の計画書のステップとして管理する。**ステップ 12(選手の削除)は TSK-459 の機構が着地してから別 PR で開く**(FR-018 の述語 SQL と入口は U-M1 の所有のまま — TSK-459 のカードの「やらないこと」)。**在籍区分の入口(プレビューと適用)と発火点は、#95 のマージ後に本タブが TSK-447 と同じ 1 つの PR で開く**(TSK-447 の規則〔正本 11-2 節の改訂 — 確定ゲート / `cache-invalidation-contract.json` の 7.7 の記録〕・在籍区分の適用〔単一・一括〕と同じトランザクションでの無効化意図の記録・配信の仕組みの所有単位の決定)。その PR の計画書は TSK-447 として新たに起こす
> 2. **DoD の FR-017 行・FR-018 行**と **6 節の「在籍区分変更後のキャッシュ失効」行**は、#95 の判定対象から外し、後続 PR(FR-017 は TSK-447 と同じ PR・FR-018 は TSK-459 の後の PR)へ申し送る。**DoD の 12-4 の判定対象の入口**は、#95 ではステップ 9 と新 11 で開く入口に限る(旧 11・12 の入口は後続 PR の判定対象)。**6 節の「削除の競合」行**も #95 の判定対象外(TSK-459 の後の選手削除 PR へ)。#95 で FR-017 に関わるのは、ステップ 9 の PATCH が在籍区分とラベルを受けないこと(422)だけ
> 3. **2 節(スコープ)の「やること」**を #95 で開く入口に絞り、外した 2 つの送り先を書く。**依存表 7**(在籍区分キーと seed)を着地済み(TSK-475 / #94)へ訂正する — **新ステップ 11 の着手条件(本節末の「ステップ 9 以降は dep 4・6・7・10・11 の着地後」)はすべて満たされている**。依存表 9 は #95 の新ステップ 11 の着手条件ではない(後続 PR の着手条件)
> 4. **現在地導出の既知の不整合**: 既存のコミット 3 本の件名がステップ記法の文法に合わない — `64858d6a`(1 件名に完全トークン 2 個 — 「(ステップ 2 再導出) のコミットへ…(ステップ 3 再導出)」)・`086ef80a`(計画系の件名の括弧「(ステップ 6・7 の…)」)・`638b796f`(「(ステップ 3・4 が要る…)」)。`scripts/feature_status.py` は「1 件名に複数のステップ記法」で不整合を出し、新ステップ 11 のコミット後も 11/11 と導出しない。**履歴は書き換えない**(後続の再導出コミット・受理記録・人間の再確認が SHA を参照する)。現在地導出は非ブロッキング(`/pr` 手順 2-3)なので、PR 本文に出力を転記し、本記録を根拠として示す
> 5. **3 節(分担)の発火点の行**と**依存表 8・9 の状態**を現況へ。
> 6. **依存表 1〜12 の状態欄と見出し・8 節の未決行を一括で現行化する**(2026-10-10 に原典で実測 — 計画レビュー 4・5 周目で古い状態欄が 1 行ずつ見つかったため、裁定〔2026-10-10・山田正輝〕で一括にした): 1 = #79・2 = 済(ステップ 2〜5・10)・3 = #82・4 = #97(適用済み・通過判定の記録は保留)・6 = #100・7 = #94・8 = #82・9 = 未着手(後続 PR だけに掛かる)・10 = #104・11 = #101・12 = 済(ステップ 8)。8 節 1(フロントエンドの帰属)= #110 で解消・4(seed の起票)= #94 で解消・2(FR-015 の同期面)= 未決のまま(#95 の射程外)。各行の旧記述は残す依存表 8 = 着地済み(#82)/ 依存表 9 = 未着手(2026-10-10 実測)・#95 の後に本タブが引き取る
> 7. **最終全文確認周(6 周目)の反映**: 依存表 5・6・10・11・12 の状態欄を「現況 → 旧記述」の順に一意化 / 2 節のフロントエンドの帰属と 7 節 R1 を現況へ / design.md 4 節(`PlayerUpdate`)の「ステップ 11」を旧番号と後続 PR の担当へ / DoD の FR-039 行で #95 が判定する API 面と、試合作成中の操作(U-G1・U-F8)を分ける / 依存表 10 の FK 本数(ほか 2 本 — 計 3 本)
> 8. **7 周目の反映とレビューの打ち切り**(裁定 2026-10-10・山田正輝 — 7 周とも否決で、7 周目は初版からの穴が出始めたため): 本文冒頭に「現行の正」(ステップ表・DoD・6 節・本改訂ブロック)を明記 / 2 節・7 節 R1・8 節 1・4 を現況から書き旧状態を「当時の記録」と明示 / ~~UI 設計正本は実装ステップでなく `/sync-docs` で書き~~(当時の記録 — **第 11 改訂で取消**: UI 設計正本は #95 の射程外)、画面の操作は U-F5・U-F8 で判定 / 新ステップ 11 の合格条件に削除不可の理由を見分けられる応答(リネーム誘導の材料)を足し、誘導の表示は U-F5 で判定 / `/<N>` を書かない理由を現行化。**初版からの穴は `/pr` の DoD 突合でもう一度当たる**
>

> ## 【第 11 改訂 2026-10-10・改訂承認: 山田正輝】UI 設計正本の執筆を #95 の射程から外し、申し送る
>
> **ステップ表は変えない**。2 節「やること」の UI 設計正本の行・DoD の FR-015・FR-017 行の画面の判定・冒頭の「現行の正」・第 10 改訂ブロックの該当文(取消線)を書き換える。
>
> ### 何が起きたか
>
> - `/pr` のクローズ処理で正本反映を突合したところ、2 節「やること」は初版(2026-09-24)から「**自 FR の UI 設計正本を書く**」を挙げているのに、**3 節(影響する正本)に宣言が無い**(第 10 改訂の計画レビュー 7 周目でも指摘 — 初版からの穴)
> - **UI 設計書は実在しない**(`docs/design/` は `data-model.md`・`sync-protocol.md` だけ)。ADR-002 は「コンポーネント設計規約は設計フェーズの UI 設計書で確定する」とするが、フロントエンドの実装単位を定めた TSK-508(PR #110)は**UI 設計書の新設を射程外として申し送った**(`../frontend-impl-units/plan.md` の 3 節・申し送り)。送り先は未確定
> - #95 で書くと**正本の新設**(確定ゲート — 敵対レビュー + 人間承認)になり、コンポーネント規約の無いまま U-M1 の分だけを先に書くと、全体を作るときに作り直しになる
>
> ### 裁定(2026-10-10・山田正輝)
>
> **#95 から外して申し送る**(選択肢: 外して申し送る〔採用〕/ #95 で UI 設計書を新設して確定ゲートを通す)。
>
> ### 何を変えたか
>
> 1. **2 節「やること」の UI 設計正本の行**を「#95 の射程外。UI 設計書を新設するタスク(未起票 — 起票を山田正輝へ提案する)へ、U-M1 の入口(選手の作成・一覧・取得・更新・対戦相手チーム・のちの在籍区分と選手の削除)の UI の要求を申し送る」へ替える(第 10 改訂の「`/sync-docs` で書く」を取り消す)
> 2. **DoD の FR-015・FR-017 行に判定の分担を書く**: #95 = API 面(FR-017 の API 面は TSK-447 と同じ後続 PR)/ **画面の操作 = `../frontend-impl-units/design.md` の FR と画面の対応表が割り当てる単位**(本書は担当を書き下ろさない — 計画レビュー 2 周目の P1: 書き下ろした割り当てが対応表と食い違った)/ UI の要求 = UI 設計書(新設タスク)。第 10 改訂ブロックの「UI 設計正本は `/sync-docs` で書く」は当時の記録として取消線を引く
> 3. 冒頭の「現行の正」に本改訂ブロックを足す
>

**着手の拘束**: **ステップ 1〜3 は外部依存の着地を待たない。ステップ 4 の前に PR 番号を確定する(N3 — 人間の判断を経てから PR を作る)。ステップ 5 はステップ 4 と同じ PR 番号を使う。ステップ 6・7 は TSK-344 のマージと develop の取り込みの後(第 1 改訂の 3 — 本書の拘束)。**
**第 3 改訂の番号で: ステップ 8 は外部依存を待たない(ステップ 7 の後)。ステップ 9 以降は dep 4・6(γ)・7・10(TSK-480)・11(TSK-457)の develop 着地後**
(`/implement` は承認済み計画書を要求する)。
**ステップ記法に `/<N>` を書かない**(設計書 6.1 の厳密文法③)。当初は総数を確定できなかったため。第 10 改訂で #95 のステップは 11 に確定したが、既存のコミットを `/<N>` なしで書いてきたので、揃えるため引き続き書かない。

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **DTO を追加する** — `backend/src/pitchlog/api/schemas/roster.py`。[design.md](design.md) 4 節の全 DTO(`PlayerStatusPreview` を含む)を定義する | `backend/tests/test_roster_schemas.py` が green。値域・省略と明示 null の区別・空配列と重複 ID の扱いをテストで確認。`ruff check` / `ruff format --check` / `ty check` green |
| 2 | **入口の契約資産を追記する** — `route-registry.json` と `http-route-matrix.json` へ本単位の経路 6 本を登録し、**派生 lock を `--reseal-derived --skip-oracle` で作り直す**(oracle 封印には触れない)。**既存行の `test_owner` は書き換えない**。新規行の `test_owner.status` は **`planned`** とする。**あわせて検査器の期待集合を更新する**(`scripts/check_authz_catalog.py:2175-2186` は `record_and_aggregate` の経路を空集合で固定している — 「経路 0 件なので空集合」は登録する単位が更新する設計 — `../route-kind-vocabulary/plan.md:88`・`:150`)。`route_id` は導出規則(`:2412-2421` — `ROUTE:RECORD:<資源>:<操作>`)と操作の閉じた値域(`:2407-2411` — read / insert / update)に従う。**`route_id` と期待集合は N1・N2(決定済み)** | `uv run pytest -c pyproject.toml tests/test_check_authz_catalog.py` のうち oracle 封印に依存しない検査が green。**封印入力の許容差分を固定列挙しているテスト(`tests/test_check_authz_catalog.py:4997-5025`)へ `http-route-matrix.json` とその lock を加える**。**期待失敗の集合は全件実行で確定して worklog に列挙し、ステップ 3・4 で解消されることを各ステップで確かめる**(封印の不一致が中心 — 事前に列挙しきらない)。派生 lock の `entries` が追加 6 行だけ増え、既存行の判定が不変。registry と matrix が exact-set で一致。期待集合が本単位の `route_id` と exact-set で一致 |
| 3 | **oracle の内容を追随させ、人間の確認を受ける** — ステップ 2 のコミット SHA を `oracle_commit`(封印 1 + oracle 資産 6 — 前例 `../route-kind-vocabulary/plan.md:171`)へ差し替え、経路の追加に伴う oracle 資産の内容の追随を行う(範囲は**内訳 3**)。**`oracle_commit` の変更で blob が変わる `ddl-elements.json`・`claim-mutant-map.json` を参照する `failure-injection-points.json`・`mcdc-map.json` の digest も追随させる**(`--reseal-oracle` は両資産を更新しない — 前例 `../route-kind-vocabulary/plan.md:172` の 5b)。**このステップで敵対レビューと人間の確認を受ける**(`review_policy` `ORACLE_STEP5_REREVIEW`) | 差分が人間の確認を受けた記録が worklog にある。`scripts/check_failure_injection_points.py`・`scripts/check_mcdc_map.py` が green。**期待失敗は封印の不一致と、`boundary-proposal` 検査による凍結台帳の最新 `oracle_input` との不一致(`scripts/check_authz_catalog.py:6520-6531`)** — いずれもステップ 4 で解消 |
| 4 | **凍結基準の記録と oracle の再封印** — `contracts/authz/frozen-baselines.json` へ series `oracle_input` の記録を 1 件(`acceptance_id` = 本 PR — **ステップ 4 の前に N3**)追記し、`--reseal-oracle` で再封印する。前例 `fb71c300` | `uv run python scripts/check_authz_catalog.py` が ok。`tests/test_check_authz_catalog.py`・`tests/test_check_authz_catalog_spec.py`・`tests/test_frozen_baseline_*.py`・`tests/frozen_negatives/` が green |
| 5 | **リポジトリと operation token を追加する** — TSK-424 の capability カタログから token 型を導き、registry へ登録する。**7.7-2 の記録と比較 corpus の再封印**を同時に行う。**内訳は表の下「ステップ 5〜7 の内訳」の 3** | 内訳 5 の合格条件をすべて満たす |
| 6 | **`tenant-isolation` の追加層を宣言する** — `scripts/core_guard.py` の `AREA_PATH_ADDITIONS` と `tests/test_core_guard.py`。**`.claude/core-areas.json` を同一コミットに入れない**。**内訳 6** | 内訳 6 の合格条件をすべて満たす |
| 7 | **`.claude/core-areas.json` へ本単位の paths を登録する** — 越境テストの glob `backend/tests/test_*_boundary.py` とリポジトリのテストの glob `backend/tests/test_*_repository.py` をこの順で `tenant-isolation` の末尾へ追加する(第 5・第 6 改訂。新規リポジトリは既存の `backend/src/pitchlog/repositories/*` が覆う — `fnmatch` の `*` は `/` を跨ぐ)。**ステップ 6 の宣言と完全一致させる**。単独コミット。**内訳 7** | 内訳 7 の合格条件をすべて満たす |
| 8 | **リクエストの要求面を足す**(第 3 改訂で追加) — Cookie(H-2 の属性)から提示値を不透明な値のまま取り出し、**状態を変える要求**ではカスタムヘッダの必須化と `Origin` の検査で CSRF を拒否する依存関数を API 層に置く。**提示値を分解せず、γ を呼ばず、`TenantContext` を作らない**。どの入口にもまだ結線しない。**内訳 8** | 内訳 8 の合格条件をすべて満たす |
| 9 | **`TenantContext` の発行と選手の入口を、同じコミットで開く**(第 3 改訂 — 第 2 改訂の 8 に発行を足した) — 発行専用モジュールの発行関数が提示値を受けて γ の公開入口を呼び、照合を通ったテナント ID からだけ `TenantContext` を作る(**生成箇所** — 8-3 節「検証の手順」⑤)。`tenant-context-allowlist.json` へ登録し、検査器の 0 件必須の分岐を置き換え、配布モジュールを追随させる。選手の入口(作成・一覧・取得・更新)をステップ 8 の依存関数 → 発行関数 → リポジトリの順に結線し、`ROUTERS` へ登録し、`test_api_conventions.py` の述語 4(経路数)の期待値を更新する。**DTO の `name` の空文字の扱いを token と揃える**(ステップ 5 の持ち越し P2)。**内訳 9** | `test_roster_boundary.py` の当該入口ぶんが green(認可行列どおりに通り行列外は 404)。`/health` `/version` を含む既存テストが green。**`backend/tests/test_roster_boundary.py` を作るこのステップで、ステップ 7 で登録した `tenant-isolation` のパスが実ファイルに当たることを確かめる**(登録が先行するため — 第 2 改訂の 4)。内訳 9 の合格条件をすべて満たす |
| 10 | **受理記録を 1 件にまとめ、比較 corpus を再封印する**(第 3 改訂で追加) — ステップ 9 の SHA を受けて、#95 の 7.7 の受理記録を、ステップ 5 と 9 の両方の変更を覆う 1 件へ導出し直す。センサス基準(`census-baseline.json`・`tests/test_census_baseline_check.py` の緩和の判定)を同じコミットで更新する(第 7 改訂)。**内訳 10** | 内訳 10 の合格条件をすべて満たす |
| 11 | **対戦相手チームレコードの入口を開く**(FR-039 — **第 10 改訂で 13 から付け替え**) — 作成・一覧・更新・削除。類似名の警告と削除拒否の誘導 | 試合または選手が紐づくチームの削除が拒否されること・**削除不可の応答が理由(試合の紐づき・選手の紐づき)を見分けられる形で返る**こと(リネーム誘導の材料 — 第 10 改訂)・類似名が警告で登録続行できることを確認 |


#### ステップ 2〜4 の内訳(第 2 改訂 2026-10-05)

**2. 契約資産・検査器・派生 lock**

- 封印入力の許容差分の固定列挙(`tests/test_check_authz_catalog.py:4997-5025`)を更新する
- 経路 6 本(N1)を `route-registry.json` に足す: `route_kind: record_and_aggregate` / `origin: design` / `source_claim_ids: []` / `provenance_ids` に `PLAN-TSK446-RECORD-AND-AGGREGATE` を含む / `operation`(検査器 `scripts/check_authz_catalog.py:2346-2429`)
- `http-route-matrix.json` に 6 行(`disposition: conditional` — 同 `:2729`。`test_owner.status: planned`)
- 検査器の期待集合を 6 本の独立リテラルへ(N2)。`tests/test_check_authz_catalog.py` の表明と負例(期待集合外の `route_id`・導出規則違反・専用 provenance 欠落)を更新・追加
- 派生 lock を `--reseal-derived --skip-oracle` で作り直す。**fixture 側の lock(`tests/fixtures/authz_claims/route-registry.lock.json` など)は CLI が触らない**ので、前例どおり手で揃えるかを原典で確かめる(`../route-kind-vocabulary/plan.md:170`)

**3. oracle の追随と人間の確認**

- **`failure-injection-points.json`・`mcdc-map.json` の digest 追随**(上の表のステップ 3)を含める
- `oracle_commit` をステップ 2 のコミット SHA へ差し替える箇所と、経路の追加に伴って内容の追随が要る oracle 資産(`attack-tree.json`・`boundary-proposal.json`・`claim-mutant-map.json` など)は、**前例 `a1e2a8be`・`e01926ec`(#77 のステップ 5)を当てて原典で確定する**(N5)
- **敵対レビューと人間の確認をこのステップで受ける**。確認の記録を worklog に残す

**4. 凍結基準の記録と再封印**

- `frozen-baselines.json` の `history` へ 1 件(前例 `fb71c300` — 10 キー: `acceptance_id` / `series` / `new_identity` / `prior_identity` / `changes` / `placement_change` / `moved` / `reason` / `approved_by` / `approved_at`)。`approved_by` / `approved_at` は人間に確認した値
- `--reseal-oracle` で再封印する(`human_review_required: true` — ステップ 3 の確認を経た後)
- **PR の base が進んだら再導出する**(N4)

#### ステップ 5〜7 の内訳(改訂 2026-10-05 — 敵対レビュー 4 周の反映)

**5. リポジトリと operation token**

- **着手条件: ステップ 4 で確定した PR 番号を `acceptance_id` に使う**(PR を作るのはステップ 4 の前 — N3)。`acceptance_id` は実際の PR 番号から導出され、PR 受理検査でイベント値との一致を要求される(`scripts/frozen_history.py:672`・`:685`)ので、番号を知らないままでは記録を完成できない(仮の番号はローカルで green でも受理時に落ちる)。前例は TSK-443(`../runtime-contract-switch/plan.md:80`「draft PR を作って `acceptance_id` を確定する」)。**作り方と `/pr` との両立は N3**

- **契約と生成物**: `contracts/tenant_boundary/repository-contract.json` の `product_capability_ids` / `product_operation_token_types`(`:127-128`)へ本単位の分を登録し、生成モジュール `backend/src/pitchlog/repositories/repository_contract.py`(`PRODUCT_CAPABILITY_IDS` / `PRODUCT_OPERATION_TOKEN_TYPES`)を同期する。**`cross_tenant_functions` は空のまま**
- **実行 registry**: `repositories/base.py` の `_OPERATION_REGISTRY` を契約と exact-set で一致させる
- **登録文の検証**: `backend/src/pitchlog/authz/capability_registration.py`(`:1195-1269` — カタログの ID・表・操作との照合)に通す
- **空を表明する既存テストの更新**: `backend/tests/test_authz_capability_registration.py:1022-1027`(`test_product_registries_remain_empty`)・`backend/tests/test_authz_repository_contract.py:407-417`
- **凍結基準の記録(7.7-2)**: `repository-contract.json` 側は `baseline_control` の `contract_revision` と `current_identifiers` を同期し、**既存 history は保持する**(非権威資産への履歴の追記は拒否される — `scripts/frozen_history.py:492-519`)。
  **追加の記録は権威履歴(`contracts/tenant_boundary/base-allowlist.json` の `baseline_control.history`)へ 1 件だけ**置き、影響を受ける凍結資産の全件・変更前後の snapshot・生成モジュールの digest を同期する(様式は設計書 `:584-608`)。
  **記録はステップ 5 のコミット時点で、draft PR の番号とその時点の比較元に対して完全に書く**(識別値を未記入にする・revision だけ動かす形は検査が通らない)
- **比較 corpus の再封印**: `contracts/tenant_boundary` は比較 corpus の入力 tree(`tests/fixtures/frozen-archive-cases/manifest.json:16-18`)なので、`history-snapshots/` と manifest の digest を再導出する
- **再導出の時点**: PR の受理検査は event の `base.sha` と二親 merge で評価する(`scripts/check_tenant_boundary_bypass.py:6163`・`scripts/frozen_history.py:1185`)。**PR 直前の develop 取り込み時に再導出・再検証し、PR 作成後に base が進んだら再度行う(コミット先は N4)**
- **現版の結果照合**(**第 7 改訂で前版の照合を外した** — #101 の契約拡張以後、前版 `ec02a0d2` は契約を読めず実行できない。前版の値と期待値は develop のまま変えない。残る保証と失う保証は第 7 改訂ブロックの 1): 再封印時に `tests/test_frozen_archive_case_runner.py` を実行し(現版だけを実行する — `:414`)、**全ケースで manifest の現版の期待値と一致する**ことを確かめる。`corpus_inputs.digest` だけを再 pin し、`comparison_revision` と前版の期待値・`recorded_exit_codes` が develop と同一であることを確かめる
- **合格条件**: **現版**の全ケース一致(上 — **第 7 改訂で前版の照合を外した**)。`backend/tests/test_authz_repository_contract.py`(資産と生成モジュールの一致 `:303-309` を含む)・`backend/tests/test_authz_capability_registration.py`・`tests/test_check_tenant_boundary_bypass.py`・`tests/test_frozen_history.py`・`tests/test_frozen_archive.py`・`tests/test_frozen_archive_case_runner.py` が green。カタログ外の ID・表・操作が拒否される負例が green

**5 の是正 — 第 4 改訂 2026-10-08(`(ステップ 5 是正)` の 1 コミット)**

- **前提(現 HEAD の状態)**: develop の取り込み(`8ada3d9d`)で権威履歴の衝突を develop 側で解いたので、**現 HEAD の `base-allowlist.json` の履歴に #95 の記録は無い**(末尾は develop が足した #96 の記録)。旧記録の snapshot も外した。比較元(merge-base)の履歴 prefix は変更・削除できない(`scripts/frozen_history.py`)ので、**#96 までの履歴をそのまま保ち、#95 の記録を末尾へ 1 件追記する**
- **1 コミットに入れるもの**(ステップ 5 と同じく、変更と記録を同じコミットに置く — 記録を別コミットにすると、間のコミットでは検査器が履歴の検証で止まり、ソースの違反〔TB005〕の有無まで到達しない。検査器は履歴を先に検証し、その後にソースの違反を集める)
  - `roster.py` の文の組み立てを、**少数の組み立て関数**へ集める。モジュール直下の文の定数は置かない(条件 5 は「許可シンボルの内側」で判定するので、関数の外の組み立ては常に TB005)。関数の数は最小にする — `allowed_symbols` は 1 シンボルにつき 1 つの正例 fixture を要求し、fixture は一意で、正例 fixture のディレクトリと exact-set で一致しなければならない(`scripts/check_tenant_boundary_bypass.py` の allowlist の読み込み)
  - 各関数を `contracts/tenant_boundary/base-allowlist.json` の `allowed_symbols` へ登録する: `symbol`・`signature`(関数の実際の署名と一致)・`allowed_api_ids`(**その関数が使う組み立て API だけ** — `SQLA_SELECT` / `SQLA_INSERT` / `SQLA_UPDATE` の部分集合。**実行系の API〔`SQLA_SESSION_EXECUTE` ほか〕は入れない**)・`fixture`(`tests/fixtures/tenant_boundary/positive/pitchlog/repositories/` 配下にシンボルごとの正例 fixture)
  - **`base-allowlist.json` 自身の凍結射影が動く**ので、その `contract_revision` の繰り上げと `baseline_control.current_identifiers` の更新を行う
  - **#95 の受理記録を 1 件追記する**。覆う変更は、ステップ 5 の `repository-contract.json` と、本是正の `base-allowlist.json`(`allowed_symbols`)の両方。影響する凍結資産の全件・前後の snapshot・生成モジュールの digest・比較 corpus の再封印は内訳 5 の手順を準用し、新しい base(`origin/develop`)に対して導出する。`approved_by` / `approved_on`(tenant_boundary の権威履歴のキー — authz の `frozen-baselines.json` は `approved_at`) は人間に確認した値
  - **文の中身・token・capability 検査器の実行直前の検査は変えない**(登録型・`_prepare_operation`・単一の実表ほか — ステップ 5)
- **合格条件**(**すべて、コミットした後に、作業ツリーが清潔で HEAD がそのコミットであることを確かめてから実行する** — 検査器はソースを HEAD から読み、契約資産を作業ツリーから読むので、未コミットの資産が残ると混合状態を検査する)
  - `uv run python scripts/check_tenant_boundary_bypass.py --base-ref origin/develop` が ok(TB005 が 0 件で、履歴の検証も通る)
  - 登録した関数に実行系の API を書くと TB005 になる / 登録外のモジュールに同じ組み立てを書くと TB005 になる(既存の負例の仕組みで足りるかを原典で確かめ、足りなければ検査器のテストに足す)
  - 権威履歴の #95 の記録が 1 件だけで、#96 までの prefix が merge-base と一致
  - 内訳 5 の合格条件(現版の全ケース一致を含む — 第 7 改訂)
  - `backend/` の `tests/test_authz_repository_contract.py`・`tests/test_authz_capability_registration.py`・`tests/test_roster_repository.py` が green
  - 実行時の HEAD SHA・作業ツリーが清潔だったこと・各コマンドの結果を worklog に記録する
- **push の後**: `gh pr checks 95` に検査が並び、`tenant-boundary-bypass` が実際に走ったことを確かめる

**6. 追加層の宣言**

- **着手条件**: TSK-344 のマージ後、develop を取り込んでから行う(上の改訂 3)。着手時に `git fetch origin` し、**`origin/feature/*`・`origin/fix/*` とローカルの `refs/heads/*`(`git worktree list` の全 worktree を含む — 未 push の競合を落とさないため)のうち、`scripts/core_guard.py` の `AREA_PATH_ADDITIONS` または `.claude/core-areas.json` の `tenant-isolation.paths` を変える未マージの ref とその SHA を worklog に記録する**。未マージの競合は順序調整の対象(該当タブへ連絡)であり、宣言の基線へ取り込むのは **develop に着地した変更だけ**。ステップ 7 と PR の前に同じ確認を繰り返す
- **逐行確認**: `scripts/core_guard.py`・`tests/test_core_guard.py`・`.claude/core-areas.json` はいずれも最上位 `guard_paths` に該当する(`:466`)。本単位の PR は元から逐行確認が必須なので、ステップ 6・7 で手続きは増えない
- **宣言**: `AREA_PATH_ADDITIONS["tenant-isolation"]` を **U-M1 の未取り込み分だけ**(`("backend/tests/test_*_boundary.py", "backend/tests/test_*_repository.py")` — 第 5・第 6 改訂)にする。先着ブランチの宣言は**累積せず置き換える**(部分取り込みは `scripts/core_guard.py:303-314` が拒否)
- **テスト**: `tests/test_core_guard.py` の「宣言領域・未宣言領域」を固定する表明(`:1497`・`:1544`・`:1617-1623`)を更新する。**意図した宣言の exact-set をテスト側に独立して残す**(`set(AREA_PATH_ADDITIONS)` を実装から読んで許す形にしない)。**部分追加・並べ替え・削除・未宣言の追加の 4 種を直接試す負例**を足す(部分追加・並べ替えは複数パスを宣言した合成例で試す)
- **検査器の性質の正確な記述**: 宣言後も、JSON が merge-base のままの状態は検査器が許す(`:310`)。**登録の欠落は検査器では検出しない** — ステップ 7 の独立確認で検出する
- **合格条件**: `uv run pytest tests/test_core_guard.py` が green(**`test_all_schema_contract_assets_match_an_actual_core_area_path` の 1 件だけはステップ 7 で緑になるので除く** — 第 6 改訂の 3)。**ステップ 6 のコミット SHA に対して `uv run python -c "import sys; from pathlib import Path; sys.path.insert(0, 'scripts'); import core_guard; print(core_guard.verify_area_path_baseline(Path('.'), '<origin/develop の SHA>', '<ステップの SHA>'))"`(リポジトリルートで。base SHA・ステップ SHA・戻り値〔merge-base の OID〕を worklog に記録) を実行し、例外なく戻ることを確かめる**(PR の CI は最終 head しか検査せず、ローカルの `core_guard.py` は PR event が無いと skip するため — `.github/workflows/ci.yml:55`・`scripts/core_guard.py:499`)

**6・7 の是正(第 7 改訂・第 8 改訂で値を替えた)**: ステップ 6・7 の合格条件(宣言値・登録値が 2 件)は**実施済みのステップ 6・7 の時点の状態**を表す。是正 2 コミットの後の状態は 3 件で、DoD はこちらを要求する。

- **`(ステップ 6 是正)`**: 宣言値を 3 件(`backend/tests/test_*_boundary.py`・`backend/tests/test_*_repository.py`・`backend/src/pitchlog/api/*` の順 — 第 8 改訂)にし、`tests/test_core_guard.py` の独立の期待値と 4 負例(部分追加・順序入れ替え・baseline の削除・未宣言の追加)を追随させる。`core-areas.json` は触らない。**このコミットの SHA は期待どおり赤になる**: 検査器が受け入れるのは「JSON が merge-base のまま」か「merge-base ＋ 宣言の全件」だけで(`scripts/core_guard.py` の `validate_area_path_layers`)、既登録の 2 件だけがある中間状態は `verify_area_path_baseline()` が `GuardError` を返し、`tests/test_core_guard.py` の登録数と宣言値の一致の表明も落ちる(JSON と基線定義を同じコミットで変えられないので、中間の赤は避けられない)。**合格条件**: 期待失敗が「宣言 3 件に対して JSON の追加が 2 件」に由来するものだけであること(`verify_area_path_baseline()` のメッセージと `tests/test_core_guard.py` の失敗の一覧を worklog に記録)/ 敵対レビュー。CI は PR の先頭だけを見るので、次のコミットと同じ push で送る
- **`(ステップ 7 是正)`**: `core-areas.json` の `tenant-isolation.paths` の末尾に `backend/src/pitchlog/api/*` を足す。基線定義は触らない。**合格条件**(内訳 7 の確認はステップ 7 の時点〔追加 2 件・越境テストの一致 0 件〕のもので、ここでは使わない): このコミットの SHA に対して ① 実際の `tenant-isolation.paths` が「merge-base の列 ＋ 3 件(上の順)」と完全一致し、他の領域・キーが不変 ② `backend/src/pitchlog/api/*` に当たるこの SHA の追跡ファイル(`git ls-files`)が、`tenant-isolation` のパターンだけを渡した `matched_paths()` ですべて返る ③ 遡及の確認 — `backend/src/pitchlog/api/*` に当たる追跡ファイルが API 層のファイルだけ(2026-10-09 の実測で 11 件 — 第 8 改訂の 3)④ `verify_area_path_baseline()` が例外なく戻る ⑤ `uv run pytest tests/test_core_guard.py` が green(前のコミットの期待失敗がすべて解消)/ 結果を worklog に記録 / 敵対レビュー

**7. paths の登録**

- **合格条件**: 内訳 6 と同じコマンドをステップ 7 の SHA に対して実行し、例外なく戻る(worklog に記録)。**独立確認として、実際の `tenant-isolation.paths` が「merge-base の列 ＋ `backend/tests/test_*_boundary.py`・`backend/tests/test_*_repository.py` の 2 件(この順)」に一致することを確かめる**。**あわせて、ステップ 7 の時点で `test_*_boundary.py` に当たる追跡ファイルが 0 件、`test_*_repository.py` に当たる追跡ファイルが本単位の `backend/tests/test_roster_repository.py` と、ステップ 7 の前から `tenant-isolation` に入っている `backend/tests/test_authz_runtime_contract_repository.py` の 2 件だけであること**(本単位のもの以外を遡って新たにコア領域へ入れていないこと — `git ls-files` を `fnmatch.fnmatchcase` で照合し、merge-base の `tenant-isolation.paths` に当たるかを確かめる — 第 6 改訂の 2)を確かめ、worklog に記録する。`uv run pytest tests/test_core_guard.py` が green(`test_all_schema_contract_assets_match_an_actual_core_area_path` を含む)。PR 本文に 6.3-⑤ の審査対象として明示する

#### ステップ 8〜10 の内訳(第 3 改訂 2026-10-07)

**8. リクエストの要求面**

- **着手条件**: ステップ 7 の後。外部依存を待たない
- **置き場**: `backend/src/pitchlog/api/` 配下。**API 層の全ソース連結に対する部分一致検査**(R5 — `Session`・`generation` を docstring・コメントを含めて書けない)を受ける
- **Cookie**: H-2 の属性(`HttpOnly`・`Secure`・`SameSite=Strict`)を前提に、提示値を取り出す。名前などの細部は **N6**
- **CSRF**: 状態を変える要求では、**カスタムヘッダの必須化と `Origin` の検査**を両方行う(H-2)。対象とする HTTP メソッドの範囲・`Origin` の許可値の出所は **N6**
- **信頼境界**(8-3 節「検証の手順」②): **提示値を不透明な値として扱い、分解しない**。ID を取り出すのも署名を照合するのも γ の公開入口であり、その呼び出しはステップ 9 の発行専用モジュールの中だけに置く。**このステップの依存関数は γ も認証関数も呼ばない**
- **秘密性**(NFR-014): 提示値をログ・例外のメッセージ・応答に出さない
- **拒否の応答**: 既存のエラー規約(`backend/src/pitchlog/api/errors.py`)に従う。**応答の内容が、拒否の理由以外の事実(テナントや認証主体の存在など)で変わらない**
- **合格条件**: 単体テストで、Cookie の欠落と空の値が拒否される / 状態を変える要求で、カスタムヘッダの欠落・`Origin` の欠落・`Origin` の不一致がいずれも拒否される / 正しい要求で提示値がそのまま返る / 提示値がログ・例外のメッセージ・応答に出ない / **依存関数が γ・認証関数・`TenantContext` のいずれも import しない**(構造テスト)/ `ruff check`・`ruff format --check`・`ty check`・`backend/tests/test_api_conventions.py` が green

**9. `TenantContext` の発行と選手の入口の開放**

- **着手条件**: dep 4・6(γ)・7・10(TSK-480)・11(TSK-457)が develop に着地していること。着手時に、γ の公開入口(`verify_tenant_id` — 名前・引数・戻り値)と、TSK-457 計画書 4-3 節「U-M1 ステップ 8 に渡るもの」の 1〜5・「U-M1 への制約」を、**着地した版の原典**で再確認し、worklog に記録する
- **発行専用モジュール**: 発行関数を **1 つだけ**公開する。**入力は提示値**とし、**γ の公開入口の呼び出しはこのモジュールの中だけ**に置く。照合を通ったテナント ID からだけ `TenantContext` を作り、照合を通らなければ作らない。**検証済みのテナント ID を発行関数の外へ返さない**。置き場・モジュール名・発行関数の名前は **N7**。**発行関数の名前はリポジトリ内で一意にし、全行走査で衝突 0 件を確かめる**(TSK-457 の照合は末尾名でも一致する)
- **資産**: `contracts/tenant_boundary/tenant-context-allowlist.json` の `allowed_product_modules` に発行専用モジュールを 1 件入れ、発行入口の 2 欄(シンボルと許可シンボル)を設定する。`source_digest` の再計算・`contract_revision` の繰り上げ・配布モジュール `backend/src/pitchlog/repositories/tenant_context_contract.py` の追随
- **検査器**: `scripts/check_tenant_boundary_bypass.py` の `_load_tenant_context_contract` にある 0 件必須の分岐を、**「`allowed_product_modules` が、資産の発行入口のシンボルが属するモジュール 1 件と exact-set で一致する」へ置き換える**。**期待値は資産から導出し、検査器にモジュールの完全修飾名を直書きしない**(凍結基準の値を検査器へ直書きしない — 設計書 7.7-1)。**解除して無制限にしない** — 以後に製品モジュールを足すには発行入口の設定と規則の両方を変える必要があり、それは 7.7 を通る(`movement_triggers` の `pass_fail_mapping`)
- **テスト**: `tests/test_check_tenant_boundary_bypass.py` の `test_product_module_cannot_be_added_before_authenticated_entry_exists` を新しい規則へ改訂する。**負例**: 別のモジュールを 1 件足す・2 件にする・空にする・発行入口の 2 欄を空のまま登録する、のいずれも `ContractError`。**検査器のソースに発行専用モジュールの完全修飾名が現れないこと**を確かめる。`PRODUCT_APPLICATION_PATHS` に発行専用モジュールを足し、`test_tenant_repository_product_definition_passes_bypass_scan` で violation 0
- **生成箇所の一意性と ② の後半**: 発行関数の呼び出し元を**入口の依存関数の 1 箇所**に限り、構造テストで exact-set を固定する。**γ の公開入口の呼び出し元が発行専用モジュールだけ**であることも構造テストで固定する。**γ のテスト `backend/tests/test_authz_app_layer_surface.py` は製品コードからの呼び出し元を期待集合(`_PUBLIC_CALLERS` ほか — 着地した版で確認)で固定しているので、発行関数を呼び出し元として 1 件足す**。**γ の公開操作の集合(`_PUBLIC_OPERATIONS`)は増やさない**。ログアウトの入口は γ の所有で、U-M1 はその呼び出しを足さない。これで 8-3 節「検証の手順」② の後半(署名を照合していない ID をテナント文脈の生成へ渡す経路を作らない)が閉じる — γ の計画書 4-7 節の残余リスクの後半
- **入口**: ステップ 8 の依存関数 → 発行関数 → リポジトリの順に結線する。入口ごとに、**他テナントの提示値・Cookie の欠落・CSRF の欠落で拒否される**ことを、**外から直接叩く形**で確かめる(`data-model.md` 12-4 節「測定経路」行 — 入口を開く PR は同一 PR に直接叩くテストを含む)
- **DTO の `name`**: 空文字を DTO で拒否し、token の値域に揃える
- **期待失敗**: このステップの SHA では、テナント境界の凍結履歴の検査が、資産と記録の不一致で落ちる(ステップ 10 で解消)。**期待失敗の集合は全件実行で確定して worklog に列挙する**
- **合格条件**: 上の表のステップ 9 の合格条件 / 発行関数が提示値以外(生の UUID・文字列化した ID)からは `TenantContext` を作れないことの負例 / 許可外のモジュールから発行能力・発行入口を名指すと TB007 になる(TSK-457 の機構が本単位の登録値で効いていることの確認)/ 発行関数と γ の公開入口の呼び出し元の exact-set が green(γ の `test_authz_app_layer_surface.py` を含む — 公開操作の集合は不変)/ `name` の空文字が 422 で拒否される / 衝突 0 件の走査コマンドと結果が worklog にある / 期待失敗の集合が worklog にあり、それ以外が green

**10. 受理記録の 1 件化**

- **センサス基準**(第 7 改訂): ステップ 9 の登録で消える TB007(発行専用モジュールの `TenantContext` 構築)を、`tests/test_census_baseline_check.py` の緩和の判定で説明する。説明できるのは**発行入口のシンボル・許可モジュール・構築シンボルがすべて資産の値と一致する減分だけ**。TSK-457 の裁定 6 に従い anchor は進めない。`census-baseline.json` は受理記録で識別値を繰り上げる
- **手順**: 権威履歴(`contracts/tenant_boundary/base-allowlist.json` の `baseline_control.history`)の #95 の記録を、**ステップ 5 とステップ 9 の両方の変更を覆う 1 件へ導出し直す**。影響する凍結資産・前後の snapshot・生成モジュールの digest・比較 corpus の再封印は内訳 5 の手順を準用する。`frozen_projection.external_files` に検査器自身が入っていることを踏まえる。`approved_by` / `approved_on`(tenant_boundary の権威履歴のキー — authz の `frozen-baselines.json` は `approved_at`) は人間に確認した値
- **合格条件**: 内訳 5 の合格条件をこのステップの状態で再度満たす(現版の全ケース一致を含む — 第 7 改訂)/ **権威履歴にある #95 の記録が 1 件だけ** / ステップ 9 の期待失敗がすべて解消 / `uv run python scripts/check_tenant_boundary_bypass.py --base-ref origin/develop` が ok / `tests/test_check_tenant_boundary_bypass.py`・`tests/test_frozen_history.py`・`tests/test_frozen_archive.py`・`tests/test_frozen_archive_case_runner.py`・`tests/test_census_baseline_check.py`・`backend/tests/test_authz_tenant_context.py` が green / **センサスの負例**: 発行入口以外の関数・許可外のモジュール・別の構築シンボルの TB007 の減分が、緩和として説明されず落ちる(第 7 改訂)



#### 実装時に原典で決める事項(N1〜N7 — 改訂 2026-10-05・PO 裁定「ステップ 2・3 の詳細は実装時に詰める」。N6・N7 は第 3 改訂で追加)

**計画書では方針だけを固定し、手順の細部は当該ステップの委任時に原典で決めて design.md と worklog に記録する。**
**計画時に固定しない理由**: 対象の検査器・凍結履歴の機構は他タスク(TSK-431・TSK-344 ほか)が並行して動かしており、
2026-09-24 の計画書が承認後 11 日で 3 箇所陳腐化した(capability の登録機構・`core_guard.py` の二層方式・`record_and_aggregate` の期待集合)。
**手順を今固定すると実装時にはずれている見込みが高く、固定した手順の正しさは計画レビューでは閉じない**(敵対レビュー 4 周で毎周新種が出た)。

| # | 事項 | 方針(本書で固定) | 決める時点 | 受入証跡 |
| --- | --- | --- | --- | --- |
| **N1** | **経路ごとの `route_id` と、入口から経路への対応** | **決定済み(第 2 改訂)**: 経路は**資源 × 操作**で切る 6 本 — `ROUTE:RECORD:players:read` / `:insert` / `:update`・`ROUTE:RECORD:team_records:read` / `:insert` / `:update`。**経路 = 同じ `route_id` を持つ入口の集合**(design.md `:51-52` — 入口と経路は 1 対 1 でない)なので、一覧と取得が同じ `read` 経路に入るのは定義どおりで衝突ではない。資源名は capability カタログの表名(`CAP:players:*`・`CAP:team_records:*`)に揃える。入口 11 本の対応は design.md 3 節(作成 → insert / 一覧・取得・在籍区分のプレビュー → read / 更新・在籍区分の適用・削除 → update — **削除は論理削除なので update**、`../route-kind-vocabulary/plan.md:130`)。経路 6 本は分割検討の閾値「経路 10 本超」に掛からない | ステップ 2 | design.md 3 節に経路 6 本と入口の対応が載り、ステップ 2 の検査が(封印の不一致を除き)green |
| **N2** | **検査器の期待集合の更新範囲**(**決定済み**) | `scripts/check_authz_catalog.py` の `_validate_record_and_aggregate_route_ids` の期待集合と、対応する `tests/test_check_authz_catalog.py` の表明・負例を、ステップ 2 のコミットで本単位の `route_id` へ更新する。**期待集合を registry から読む形にしない**(独立した exact-set を残す)。両ファイルは `.claude/core-areas.json` の**最上位 `guard_paths`** に該当し(`scripts/core_guard.py:466` の完全一致)、PR 本文の逐行確認チェックを要求する(本単位はコア領域なので要求は元から掛かる — 追加の手続きは生じない) | ステップ 2 | ステップ 2 の差分に検査器とテストが含まれ、期待集合外の `route_id` が拒否される負例が green |
| **N3** | **`acceptance_id` を得るための早期 PR の作り方と、`/pr` との両立** | **【決定 2026-10-05・山田正輝】(a) #87 の前例どおり draft PR を先に作る — 確定した番号 = `masaki1025/pitchlog#95`**(ステップ 3 の後に作成。ステップ 4・5 の `acceptance_id` はこの番号から導出する。完了時に `/pr` のクローズ処理を行ってから ready)。以下は決定前の記述: **ステップ 4 の前に PR 番号を確定する**(内訳 4 — 第 2 改訂で早まった。ステップ 5 も同じ番号を使う)。**前例は #87(TSK-443)**: 2026-09-29 に PR を先に作り(ステップ 5/8 の時点)、2026-10-04 に `/pr` のクローズ処理を行ってから ready 化した(`docs/worklog/2026-09-26-runtime-contract-switch.md:60-76`)。ただし **`/pr` の文面は「PR 作成の唯一の入口」で、既存 OPEN PR の扱いを差し戻し後の再レビューに限っている**(`.claude/skills/pr/SKILL.md:2`・`:53`)ので、前例の流れは文面上の規定外である(敵対レビュー 5 周目 P1)。**ステップ 4 の前に人間へ確認し、(a) 前例どおり進めてよいか (b) `/pr` 側の改訂が要るか(要るならハーネスのタスクとして別に起票し、本単位では `/pr` を改訂しない)を決める**。draft 中は core-guard が逐行確認欄の未記入で red になる(想定内 — 確認は最新 HEAD に対して最後に行う。`docs/development/github-setup.md:60-61`) | ステップ 4 の前(**人間の判断を経てから PR を作る** — PR の作成は外部へ出る操作) | 人間の判断(a / b)と、PR 番号・作成時の base SHA が worklog にある。ステップ 4・5 の記録の `acceptance_id` が実番号と一致。**最終のクローズ処理が同じ PR で完了している** |
| **N4** | **base が凍結資産ごと進んだときの再封印のコミット先** | **系列ごとに元のステップの是正コミット**として行う — tenant_boundary は `(ステップ 5 再導出)`。**authz は場合を分ける**: (i) base が凍結台帳だけを進めた → `(ステップ 4 再導出)` で履歴と seal を再導出 (ii) **base が封印入力(route-registry・HTTP 行列・lock ほか `input_assets`)を変えた** → 封印は作業ツリーの blob と `oracle_commit` 上の blob の両方を照合する(`scripts/check_authz_catalog.py:6791-6814`)ので、`(ステップ 2 再導出)` で入力と lock を確定 → `(ステップ 3 再導出)` で SHA 差し替えと人間の再確認 → `(ステップ 4 再導出)` で履歴と seal (iii) **base が封印対象の oracle 資産(`sealed_assets` — `claim-mutant-map.json` ほか。入力 8 資産とは別 — `scripts/check_authz_catalog.py:6827`)だけを変えた** → `(ステップ 3 再導出)` で差分を再レビューし**人間の再確認を受けてから** `(ステップ 4 再導出)` で再封印する(`human_review_required` は宣言値の照合で確認の実施を検証しない — `:6855`)(付記つきの完全トークン — 付記つきの完全トークン。前例 `134bd39b`「(ステップ 4/8 是正)」)。記録・snapshot・corpus の digest を新しい base に対して再導出し、内訳 5 の合格条件を再度満たす。**TSK-431 など同じ資産群を触るタスクの着地を検知したら必ず行う**。**第 7 改訂で追加**: base が他単位の追加層の宣言ごと進み、その宣言が merge-base の JSON に入ったときは、`(ステップ 6 再導出)` で `scripts/core_guard.py`・`tests/test_core_guard.py` だけを変えて宣言を本単位の分へ張り替える。取り込みのマージでは基線定義を develop の版のまま採り、著者が解決するのは JSON の合成だけにし、各親との差分を確かめて worklog に記録する | PR 作成後に base が進むたび | 再導出コミットと、そのときの base SHA・合格条件の結果が worklog にある |
| **N5** | **oracle 資産の内容追随の範囲** | `oracle_commit` の差し替え 7 箇所に加え、経路の追加で内容が変わる oracle 資産があるかを、#77 のステップ 5(`a1e2a8be`・`e01926ec`)と各資産の検査器を当てて確定する。**範囲を推測で決めない** | ステップ 3 | 差し替え・追随した資産の一覧と根拠が worklog にあり、人間の確認を受けている |
| **N6** | **リクエストの認証の細部**(第 3 改訂で追加): Cookie の名前・パス・有効期限の表現、CSRF の対象とする HTTP メソッドの範囲、カスタムヘッダの名前、`Origin` の許可値の出所 | **H-2 の決定(属性と方式)は変えない**。決定に含まれない細部だけを U-M1 が先に決め、[design.md](design.md) に書く。**δ は後からこの値に合わせる**(R7)。設定値で持つものは `.env.example` へ実値なしで足す(NFR-014) | ステップ 8 | design.md に値と理由があり、δ の担当(Notion TSK-470)へ値を連絡した記録が worklog にある |
| **N7** | **発行専用モジュールと発行関数の名前・置き場**(第 3 改訂で追加) | 発行関数の名前はリポジトリ内で一意(TSK-457 計画書 4-3 節「U-M1 への制約」)。**API 層には置かない**(R5 の部分一致検査と、発行能力を名指せる場所を最小にするため)。置き場は TSK-457 が着地させた機構の位置を見て決める | ステップ 9 | design.md にモジュール名・関数名・置き場と、衝突 0 件の走査結果がある |


**第 2 群を後から足すときの再承認**: 本表へステップを追加する場合は、**追加分について敵対レビューと人間承認を再度受ける**。
承認済みステップの続きとして無審査で追加しない。

## 5. DoD(受け入れ基準)

### 主所有 FR の受入基準(要件書の条文と 1 対 1)

- [ ] **FR-015**: 同番号の警告が出て**警告後も登録を続行できる** / **記録時点の背番号**で過去試合が表示される(**正本はイベント側** — `data-model.md:1430-1462`。本単位は選手側に当時値を持たせないことの確認に留まる) / **試合画面を離れずに登録できる**(#95 では API 面〔作成の入口・同番号の警告を応答に載せる〕で判定する。UI の判定は U-F8 と UI 設計書へ申し送る — 第 11 改訂) / 内部 ID が不変 / 入部年度・学年を持たない — **判定の分担(第 11 改訂)**: #95 = API 面(作成の入口・同番号の警告を応答に載せる・内部 ID が不変・入部年度と学年を持たない)/ **画面の操作は、`../frontend-impl-units/design.md` の FR と画面の対応表が割り当てる単位**で判定する(本書は担当を書き下ろさない)/ UI の要求 = UI 設計書(新設タスク — 未起票)
- [ ] **FR-017**: **OB が候補から完全除外** / **「その他」は初期表示に出ないが明示操作で選択可** / **全区分可逆** / **プレビュー→確認→実行** / **相手チームレコードの選手にも適用** / **カルテ・試合準備画面からも変更できる**(UI 設計正本)/ **初期ラベル同梱**(別タスクの seed と整合)/ **キャッシュ無効化が発火する** — **第 10 改訂: FR-017 の行は #95 の判定対象外**。在籍区分の入口と発火点は、#95 のマージ後に本タブが TSK-447 と同じ PR で開き、そこで判定する — **判定の分担(第 11 改訂)**: API 面(プレビュー・適用・無効化の発火)= TSK-447 と同じ後続 PR / **画面の操作は、`../frontend-impl-units/design.md` の FR と画面の対応表が割り当てる単位**で判定する(本書は担当を書き下ろさない)/ UI の要求 = UI 設計書(新設タスク)
- [ ] **FR-018**: **確認 UI** / **OB 化へ誘導** / **競合挿入を含む同一トランザクション** / **進行中試合があると拒否して誘導** — **第 10 改訂: #95 の判定対象外**(TSK-459 の後の PR で判定する)
- [ ] **FR-039**: **試合作成を中断しない登録・選択** / **類似名の警告** / **試合または選手が紐づくチームの削除拒否とリネーム誘導** / **付与によらず 404** — **第 10 改訂で判定の分担を明記**: #95(新ステップ 11)が判定するのは API 面(作成・一覧・更新・削除・類似名の警告・紐づくチームの削除拒否と、その理由を見分けられる応答・付与によらず 404)。**リネームへの誘導の表示**は画面(U-F5)で判定する。「試合作成を中断しない登録・選択」の画面の操作は、試合作成時の相手チーム選択の担当(**U-G1** — 3 節の分担表)と画面(**U-F8**)で判定する

### 横断要求(`../product-impl-unit-split/design.md:109-121` が「破っていない」として入れることを要求)

- [ ] **物理削除しない** / **テナント分離を全機能に適用** / **自動エスケープ**(NFR-023)
- [ ] **趣旨の宣言** / **テナントの用語定義**に反していない
- [ ] **一覧はページングする**(NFR-005 — 全件読み込み型の集計を書かない)
- [ ] **NFR-019**: pytest を伴う。**越境テストは FR-034 の認可行列で合否判定**(要件書 `:933`)

### 機構

- [ ] **`backend/tests/conftest.py` の差分が 0 行**(`.claude/core-areas.json:326` の `backend/*conftest.py` に一致するため。fixture は `backend/tests/api_fixtures.py` へ置き明示 import — U-00 の先例 `test_api_errors.py:7`)
- [ ] **`test_authz*` の命名を使わない**(同 `:319` に一致するため。**越境テストは名前ではなく paths 登録でコア化する** — 3 節)
- [ ] **5 条件すべてで、許可側を除いた違反が 0**(4 節の式で実測。**条件 5 は第 4 改訂の許可側〔`allowed_symbols` に登録した組み立て関数の中の組み立て API〕を除く** — その判定は、登録シンボル・署名・`allowed_api_ids` の照合と `check_tenant_boundary_bypass.py --base-ref origin/develop` の合格で行う)
- [ ] pytest / ruff / **ruff format** / ty green
- [ ] **契約 4 の 5 領域突合**(2 節)を書いた
- [ ] **凍結基準の記録(7.7-2)が権威履歴に 1 件あり、PR の base に対して再導出・再検証済み**。比較 corpus の digest が再封印済み(4 節 内訳 5 — 改訂 2026-10-05)
- [ ] **oracle 封印の再封印と凍結基準(series `oracle_input`)の記録が 1 件あり、人間の確認(ステップ 3)を経ている**。PR の base に対して再導出・再検証済み(第 2 改訂)
- [ ] **追加層の宣言(ステップ 6)と paths 登録(ステップ 7)が別コミット**で、ステップ 6・7 と `(ステップ 7 是正)` の各 SHA に対する `verify_area_path_baseline()` の green と、`(ステップ 6 是正)` の各 SHA の所定の期待失敗(第 8 改訂: 宣言 3 件に対し JSON の追加 2 件 / 第 9 改訂: 宣言 7 件に対し JSON の追加 3 件 — 内訳「6・7 の是正」)が worklog にある。`tenant-isolation.paths` が「merge-base ＋ 7 件(`backend/tests/test_*_boundary.py`・`backend/tests/test_*_repository.py`・`backend/src/pitchlog/api/*`・`backend/tests/test_api_*.py`・`backend/tests/test_roster_*.py`・`backend/tests/test_request_presentation.py`・`tests/test_census_baseline_check.py` の順)」に一致(内訳 6・7 — 第 6〜第 9 改訂)。ステップ 7 の時点の遡及の確認(内訳 7)の記録が worklog にある
- [ ] **同領域の宣言・paths を変える未マージ ref の確認記録**(確認した ref と SHA)がステップ 6・7・PR 前の 3 時点で worklog にある
- [ ] **リクエストの認証**(第 3 改訂): Cookie は H-2 の属性・状態を変える要求はカスタムヘッダと `Origin` の両方を検査・提示値を分解しない・提示値がログ・例外・応答に出ない(内訳 8)。N6 の値を δ の担当へ連絡済み
- [ ] **`TenantContext` の発行**(第 3 改訂): 発行専用モジュールが `allowed_product_modules` と exact-set で一致し、検査器は 0 件必須を解除せず「資産の発行入口が属するモジュール 1 件」へ置き換えた(期待値は資産から導出し、検査器に直書きしない)。発行関数の名前の衝突が 0 件。**発行関数の入力は提示値で、γ の公開入口は発行専用モジュールの中だけで呼ぶ**(内訳 9)
- [ ] **8-3 節「検証の手順」② の後半が閉じている**: 発行関数の呼び出し元が 1 箇所・γ の公開入口の呼び出し元が発行専用モジュールだけで、生の UUID や文字列化した ID からは `TenantContext` を作れない(内訳 9 — γ の計画書 4-7 節の残余リスクの後半)
- [ ] **テナント境界の受理記録が #95 について 1 件だけ**で、ステップ 5 と 9 の変更を覆い、PR の base に対して再導出・再検証済み(`intermediate_commits_are_records: false` — 内訳 10)
- [ ] **製品モジュールの登録と入口の開放が同じコミット(ステップ 9)にある**。登録した製品モジュールが入口より先に存在するコミットが無い(U-T1 の「製品の入口が開く前に allowlist へ製品モジュールが入ることを禁じる」— 途中コミットにも掛かる)
- [ ] **12-4 の判定記録**(PR に記録する — `data-model.md` v0.6 12-4 節のゲート表「判定の記録」行と「実スキーマ」小見出し): 入口を開く本 PR について、v0.6 の「実スキーマ」(4 要件)に当たる対象で RLS の DDL が適用され(通過条件 ①)、越境テストが green(同 ②)であることを、次の項目を**省かず**に書いた
  - **誰が・いつ**確認したか
  - **どの実スキーマに対して**: **接続先の識別**(クラスタとデータベースから導いた要約値でよい — 接続情報の実値は書かない)と**作り直した世代の識別**(実行の採番)。書式は運用の正本 `docs/ops/product-rls-real-schema.md` に従い、その版を記す
  - **どの入口について**: 開いた入口ごとに **`route_id` と method / path の組**(**本 PR が開く全入口** — [design.md](design.md) 3 節の入口表のうち、#95 で開くもの。**第 10 改訂: ステップ 9 と新 11〔対戦相手チーム — 旧 13〕で開く入口に限る**(在籍区分・選手の削除の入口は後続 PR の判定対象)。一覧と取得のように同じ経路に入る入口があるので、`route_id` だけでは区別できない — N1)
  - **1 回の実行の妥当性**: 運用の正本の手順が未整備の項目は、v0.6「1 回の実行の妥当性」の暫定の記録(出所・各実行の連番と開始・終了時刻・比較の結果)で書く
- [ ] **ログアウトの入口を持たない**(γ の所有 — 裁定 (ア))

## 6. テスト計画

| 対象 | 種別 | ファイル | 確認すること |
| --- | --- | --- | --- |
| DTO のバリデーション | 単体 | `backend/tests/test_roster_schemas.py` | 値域 / `extra="forbid"` / PATCH の省略と明示 null / bulk の空配列・重複 ID / ページ上限の境界 |
| 越境 | 越境 | `backend/tests/test_roster_boundary.py` | **認可行列どおりに通り、行列外はすべて 404**。**API 直叩きを含む**(`data-model.md:2532` — 入口を開く PR は同一 PR に外から直接叩くテストを含む) |
| 在籍区分変更後のキャッシュ失効 | 受入 | 同上 | **OB 化した選手が共有結果に現れない**(要件書 `:977` の (b) 列挙)— **第 10 改訂: #95 の判定対象外**(在籍区分の入口とともに TSK-447 の PR へ) |
| 削除の競合 | 故障系 | 同上 | 判定後に紐づいた場合に失敗する / 進行中試合があると拒否 — **第 10 改訂: #95 の判定対象外**(選手の削除の入口とともに TSK-459 の後の PR へ) |
| 同番号の警告後の登録続行 | 受入 | 同上 | 警告が出たうえで登録できる |
| リクエストの認証(第 3 改訂) | 単体・故障系 | `backend/tests/` 直下(名前は `test_authz*` を避ける — DoD「機構」) | Cookie の欠落・空の値 / CSRF のヘッダ欠落・`Origin` の欠落と不一致 / 提示値がログ・例外・応答に出ない / 依存関数が γ・認証関数・`TenantContext` を import しない(内訳 8) |
| `TenantContext` の発行(第 3 改訂) | 単体・負例 | `tests/test_check_tenant_boundary_bypass.py` / `backend/tests/` | `allowed_product_modules` の exact-set(別モジュール・2 件・空・発行入口が空のままの登録が `ContractError`)/ 検査器のソースに発行専用モジュールの名前が無い / 許可外からの発行能力・発行入口の名指しが TB007 / 生の UUID・文字列化した ID から `TenantContext` を作れない(内訳 9) |
| 生成箇所の一意性(第 3 改訂) | 構造 | `backend/tests/` | 発行関数の呼び出し元が 1 箇所・γ の公開入口の呼び出し元が発行専用モジュールだけ(内訳 9) |
| 12-4 の判定(第 3 改訂) | 越境 | `backend/tests/test_roster_boundary.py` | 実スキーマ(v0.6 の 4 要件)の上で越境テストが green であることを記録する(DoD) |

**実行手順**(`backend/` で。CI と同じ順 — `.github/workflows/ci.yml:255-262`):

```
docker compose up -d                    # backend/tests/db/conftest.py が DB 必須テスト 0 件を失敗扱いにする
uv run ruff check .
uv run ruff format --check .            # backend では CI が強制する(AGENTS.md の注記はハーネス側のもの)
uv run ty check
uv run pytest -c pyproject.toml
```

**ハーネス側(リポジトリルートで — 改訂 2026-10-05 で追加)**: ステップ 2〜4 で `uv run python scripts/check_authz_catalog.py` と `uv run pytest tests/test_check_authz_catalog.py tests/test_check_authz_catalog_spec.py tests/test_frozen_baseline_acceptance_rules.py tests/test_frozen_baseline_declarations.py tests/frozen_negatives/`(第 2 改訂で追加)。ステップ 5〜7 で `uv run pytest tests/test_core_guard.py tests/test_check_tenant_boundary_bypass.py tests/test_frozen_history.py tests/test_frozen_archive.py tests/test_frozen_archive_case_runner.py`。ステップ 10 ではこれに `tests/test_census_baseline_check.py` を足す(第 7 改訂)。第 7 改訂の `(ステップ 6 是正)`・`(ステップ 7 是正)` では `tests/test_core_guard.py` と各 SHA に対する `verify_area_path_baseline()` を当てる(内訳「6・7 の是正」)。ステップ 6・7 は各コミット SHA に対する `verify_area_path_baseline()` の結果を worklog に記録する(4 節 内訳 6・7)

**迂回検査は実装スケルトンの段階で当てる**:
`uv run python scripts/check_tenant_boundary_bypass.py --base-ref origin/develop`

**検証は確定した状態で当てる**(第 4 改訂): 迂回検査と凍結履歴の検査は `git diff {base_ref}...HEAD` のコミット済みの差分しか見ない。**ステップのコミットを作った後に、作業ツリーが清潔で HEAD がそのコミットであることを確かめてから実行した結果だけを合格の根拠にする**(コミット前は未追跡の新規ファイルが母集団から落ちる — ステップ 5 で実際に起きた。また検査器はソースを HEAD から、契約資産を作業ツリーから読むので、未コミットの資産が残ると混合状態を検査する)。**push のたびに `gh pr checks 95` で CI が実際に走ったことを確かめる**

## 7. リスク

| # | リスク | 対応 |
| --- | --- | --- |
| **R1** | **現況(2026-10-10 実測 — 第 10 改訂)**: 下記の外部所有者はすべて着地済み(#79・#82・#97・#77・#100・#94)で、#95 で開く入口の依存は残っていない。後続 PR(在籍区分・選手の削除)の依存は TSK-447・TSK-459。以下は当時の記録 — 入口を開くのに**外部所有者が 5 者**(TSK-424 PR A / PR C・TSK-344・`route_kind` 値域〔**解消済み** — PR #77〕・**U-A1**(ブロック中)・在籍区分キーの別タスク)。1 つでも動かないとマージできない | 着地状況を /pr の前に再確認する。空席の所有者は 8 節で人間へ上げる |
| **R2** | `test_owner.status: "implemented"` は**ハーネス側 `tests/` の node ID** としか照合されない(`scripts/check_authz_catalog.py:2674-2685`) | 新規行は **`planned` 止まり**(ステップ 2 の合格条件) |
| **R3** | `players.team_record_id` は immutability の**未分類列**(handoff `TSK-372`)。所属チーム変更の可否がコードから読めない | `PlayerUpdate` の更新対象に含めない。必要になれば TSK-372 へ上げる |
| **R4** | **capability 登録は凍結基準を動かす**(`repository-contract.json` が `FROZEN_BASELINE_ASSETS`)。**TSK-431 が同じファイル群を触る** | ステップ 5 で **7.7-2 の記録**(権威履歴へ 1 件)と比較 corpus の再封印を同時に行い、**PR 直前の取り込みと base の前進のたびに再導出する**(4 節 内訳 5)。TSK-431 と順序を調整する |
| **R5** | API 層は `api/**` の**全ソース連結**に対する部分一致検査を受け、**`Session`・`generation` を docstring・コメント含め書けない**(`backend/tests/test_api_conventions.py:22-37`)。**TB004 は AST 上の識別子検査**で範囲が異なる(`scripts/check_tenant_boundary_bypass.py:2672`) | [design.md](design.md) D5 で 2 つの検査を**分けて**記述し、命名を実装前に固定する |
| **R6** | **`core-areas.json` を編集する**ため **#74 の `verify_area_path_baseline()`** が掛かる。`core_guard.py` / `test_core_guard.py` と同一コミットにすると、**後から revert しても打ち消せず force-push も `git_guard.py` が拒否する** | **追加層の宣言(ステップ 6)と paths 登録(ステップ 7)を別コミットにする**。旧版は宣言のステップを置いていなかった(改訂 2026-10-05) |
| **R7** | **リクエストの認証の細部(Cookie の名前など)を、本来の受け取り先の δ より先に U-M1 が決める**(第 3 改訂 — 依存表 12)。δ が後から別の値を選ぶと、Cookie を発行する側と読む側が食い違う | N6 の値を design.md に書き、**δ の担当へ連絡し、Notion の TSK-470 へコメントで残す**。H-2 の決定(属性と方式)は変えない。δ が値を変える必要が出たら、δ の PR で U-M1 の読み取り側も同時に変える |
| **R8** | **ステップ 9 の依存が 3 本(γ・TSK-457・TSK-480)増え、受理記録の再導出の機会も増える**(TSK-457 は `contracts/tenant_boundary/` と検査器を変える) | 凍結資産の取り込みは回数で費用がかかるので、**ステップ 9 の直前に 1 回取り込み、ステップ 10 でまとめて再導出する**(内訳 10)。それより前の取り込みで base が凍結資産ごと進んだら、N4 の手順で行う |

## 8. 人間の判断を仰ぐ事項

| # | 事項 | 本書の扱い |
| --- | --- | --- |
| **1** | **フロントエンド実装の帰属** — 単位分割の正本に「フロントエンド」「Vitest」「Vue」の語が **1 件も無い**(実測)。`:60` が各単位へ送るのは **UI の「設計正本」**であって実装ではない。**FR-015/017/018/039 の UI 面の受け皿が正本上空席** | **現況: 解消(2026-10-10 実測)**: TSK-508 / PR #110 がフロントエンドの実装単位(U-F1〜)を定めた(`../frontend-impl-units/design.md` — 選手・チームの画面は U-F5)。以下は当時の記録 — **U-M1 は射程外**として線を引いた。受け皿の決定を仰ぐ |
| **2** | **FR-015 の同期面の帰属** — 分担表に FR-015 の行が無く、「面が切れなかったときの手順」の対象外。正本上は **U-M1 の単独主所有**のまま | 帰属表を更新せずに U-S1 へ移さない。判断を仰ぐ **→ 未決のまま(2026-10-10 実測 — 裁定の記録は見当たらない)**。#95 の射程外(#95 は同期面を持たない) |
| **3** | **`route_kind` の値域決定の所有者** — `TSK-380` の射程は既存 37 経路の `test_owner` 再割り当てであり、**値域拡張は空席**(**2026-09-24 時点の記述**) | **解消済み(2026-10-04 訂正 — 4 節の外部依存 5)**。TSK-446 / PR #77 が 2026-09-25 にマージ済み |
| **4** | **在籍区分キーの値と seed の別タスク起票** — `active` のみ `data-model.md:524` に典拠。`other`/`ob` はリポジトリ内に文字列が存在しない。seed は **5 領域すべてのコア paths** で契約 3 の例外に U-M1 は含まれない | **現況: 解消(2026-10-10 実測)**: TSK-475 / PR #94(2026-10-05 マージ・migration `0027_seed_roster_status`)。以下は当時の記録 — 別タスクへ切り出す前提で本書から外した。起票の可否を仰ぐ |
| **5** | **Notion カードのコア判定が正本より古い** — **葉 6 本すべてが同型**と見られる(TSK-394 で確認) | TSK-393 のカードには訂正コメントを入れる。**他タスクのカードには触れない** |
| **6** | **改訂 2026-10-05 の承認**(ステップ 4 の追加と番号の付け替え — 4 節の改訂ブロック)。あわせて **7.7-2 の記録の承認値**(承認者・承認日)はステップ 5 の実装時に人間へ確認する | **第 1 改訂は 2026-10-05 に承認済み。ステップ 1 は実装済み(3a3aaa53)**。以後の停止位置は 7 による。**N1〜N4 は各時点で決めて記録する(PO 裁定 2026-10-05)** |
| **7** | **第 2 改訂 2026-10-05 の承認**(ステップ 2 の分割と新 3・4 の追加・番号の付け替え・N1/N2 の決定・N5 の追加)。あわせてステップ 3 の **oracle の追随の人間確認**と、ステップ 4 の記録の承認値 | **2026-10-05 に承認済み(山田正輝)**。ステップ 3 の oracle 追随の人間確認とステップ 4 の記録の承認値は各ステップの実装時に仰ぐ |
| **8** | **リクエストの認証の帰属**(Cookie から提示値を取り出す・CSRF の検査) | **【裁定 2026-10-07・山田正輝】U-M1 ステップ 8 が持つ**(δ から移す — 依存表 12・R7) |
| **9** | **第 3 改訂 2026-10-07 の承認**(ステップ 8 を 3 本に分割・新 8・10 の追加・番号の付け替え・依存表 6・10・12・N6・N7・DoD と R7・R8 の追加)。あわせてステップ 10 の受理記録の承認値 | **2026-10-07 に承認済み(山田正輝)**。ステップ 10 の承認値は実装時に仰ぐ |
| **10** | **ステップ 5 の文の組み立てが迂回検査の条件 5(TB005)に反する件の直し方** | **【裁定 2026-10-08・山田正輝】文の組み立て関数を `allowed_symbols` に登録する**(第 4 改訂 — 他の選択肢: 組み立てを基底へ移す / 組み立て API を目録の対象外にする) |
| **11** | **第 4 改訂 2026-10-08 の承認**(ステップ 5 の是正 1 コミット〔変更と記録〕・条件 5 の許可側・検証を確定した状態で当てる規律・ステップ 10 以降の記録の扱い) | **2026-10-08 に承認済み(山田正輝)** |
| **12** | **ステップ 7 の paths 登録を 1 ファイル名から越境テストの glob へ替えるか**(469 master の提案) | **【裁定 2026-10-08・山田正輝】glob `backend/tests/test_*_boundary.py` で登録する**(第 5 改訂) |
| **13** | **越境テストの命名規約 `backend/tests/test_<単位>_boundary.py` の置き場** | **本単位の射程の外**。**TSK-485**(コア領域の paths を足す手順の文書化)へ申し送る(Notion にコメント)。本単位は自分の越境テストをこの名前で作る。**第 8 改訂で申し送りに足す**: API 層は glob `backend/src/pitchlog/api/*` で `tenant-isolation` に入っているので、後続単位が足す API の強制点・入口は自動で覆われる。**第 9 改訂で足す**: API 層の規約のテストは `backend/tests/test_api_*.py` で覆われるが、単位ごとのテスト(本単位は `backend/tests/test_roster_*.py`)は単位ごとに glob を足す必要がある。**API 層の外に強制点(提示値の照合・拒否・テナント文脈の受け渡し)を置くときは、実パスを照合して登録する**(ハーネス設計書 6.3 の境界定義表と paths の落とし込み規則 ①) |
| **14** | **第 5 改訂 2026-10-08 の承認**(ステップ 6・7 の宣言値と登録値を glob へ・遡及の確認・344 の宣言を固定する表明の扱い) | **承認 2026-10-08・山田正輝** |
| **15** | **ステップ 5 のリポジトリのテストがコア領域の paths に当たらない件の直し方**(PR #95 の CI) | **【裁定 2026-10-08・山田正輝】リポジトリのテストの glob `backend/tests/test_*_repository.py` を足して 2 本にする**(第 6 改訂 — 他の選択肢: 1 ファイル名を足す) |
| **16** | **第 6 改訂 2026-10-08 の承認**(ステップ 6・7 の宣言値・登録値を glob 2 本へ・遡及の確認とステップ 6 の合格条件の例外・ステップ 2 の是正・push 前の全件実行) | **承認 2026-10-08・山田正輝** |
| **17** | **第 7 改訂 2026-10-09 の承認**(比較 corpus の前版照合を外す・ステップ 10 のセンサス基準・API 層の 2 ファイルの登録〔ステップ 6・7 の是正 2 コミット〕・N4 に宣言の張り替え) | **承認 2026-10-09・山田正輝** |
| **18** | **第 8 改訂 2026-10-09 の承認**(API 層の登録を 2 ファイル名から glob `backend/src/pitchlog/api/*` へ・未 push の是正 2 コミットの作り直し) | **承認 2026-10-09・山田正輝** |
| **19** | **第 9 改訂 2026-10-09 の承認**(API 層を検証するテストの glob 2 本と 1 ファイル・センサスのテストを追加・是正 2 コミットを足す) | **承認 2026-10-09・山田正輝** |
| **20** | **第 10 改訂 2026-10-10 の承認**(旧ステップ 11〔在籍区分〕・12〔選手の削除〕を #95 から外し旧 13 を新 11 へ・依存表と 8 節の一括現行化・現行の正の明記・判定の分担) | **承認 2026-10-10・山田正輝** |
| **21** | **第 11 改訂 2026-10-10 の承認**(UI 設計正本の執筆を #95 の射程から外し申し送る) | **承認 2026-10-10・山田正輝** |
