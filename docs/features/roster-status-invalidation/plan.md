---
feature: roster-status-invalidation
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-10-10・山田正輝)                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域         # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e593b75e6878116ab33fc7eaadd64d9
branch: feature/roster-status-invalidation
created: 2026-10-10
計画レビュー周回: 2        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 2          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: 在籍区分の入口とキャッシュ無効化の発火点(無効化意図の ID 導出規則と原子性の錨 — TSK-447)

調査: [research.md](research.md) / 詳細設計: [design.md](design.md)

## 1. 背景・目的

- Notion: [TSK-447 無効化意図の ID の導出規則を、イベント由来でないトリガーへ定義する](https://app.notion.com/p/3e593b75e6878116ab33fc7eaadd64d9)
- 要件: [FR-017](../../requirements/requirements-pitchlog-2026-07-22.md)(在籍区分 — `:390-399`)/ 6.2(キャッシュ無効化 — `:1040`「各操作の受け入れテストに含める」)/ NFR-019(b)(`:977`)/ NFR-005 / NFR-010
- **U-M1 の第 10 改訂で #95 から外した在籍区分の入口**(旧ステップ 11)を、その前提である TSK-447 と 1 つの PR で着地させる(`../um1-player-roster-opponent/plan.md:446-470`)。**FR-017 はリハーサル最小集合 26 件に入り、#95 では判定対象外なので、本 PR でしか着地しない**
- **穴の実体**(research.md 結論): 11-2 節の意図の永続化は P3(`I5`)の永続化先として書かれ、発火条件の正(sync-protocol 8-5)は同期経路の 2 行しか持たない。**同期を通らない 9 トリガーには発火条件・原子性の錨・意図 ID の定義がどこにも無い**。契約は P3 の規則を 14 件すべてに分岐なしで掛けている

## 2. スコープ

### やること

1. **正本 `data-model.md` 11-2 節の改訂**(v0.7・確定ゲート): 同期を通らない 9 トリガー共通の一般則 `B06`(発火条件・原子性の錨・意図 ID・行の単位・配信の所有。意図の帰属と鍵は自テナントの状態変更 5・7・9・14 だけを定め、8・10〜13 は所有単位へ送る)と、④共有集計の「対象テナント単位の鍵」— [design.md](design.md) 1 節
2. **契約 `cache-invalidation-contract.json` の追随**(revision 11)と純粋な要求生成器への鍵の型の追加 — design.md 2・3 節
3. **意図の記録**(新規 `repositories/invalidation_intents.py`)と、契約 → DDL の範囲名の写像 — design.md 4 節
4. **在籍区分の入口**(`POST /players/status-preview`・`POST /players/status-apply`)と**トリガー 14 の発火点** — design.md 5 節
5. **`PlayerUpdateToken` から在籍区分の 2 列を外し**、在籍区分専用の token に分ける
6. テナント境界の凍結資産の受理記録 1 件 — design.md 6 節

### やらないこと

- **選手の削除(FR-018)** — TSK-459 の後の PR
- **他の 8 トリガー(5・7〜13)の発火点の実装** — 各所有単位(U-D1・U-G1・U-A2・U-C1)。本 PR は一般則を正本に置くだけ
- **配信**(未配信の意図を取り出して消す処理)— その範囲のキャッシュ本体を初めて導入する単位(裁定 J4)
- **同期経路(1・2・3・4・6)の規則の改訂** — 1・3・4 も `B03` に当てはまらない穴と、`rows_per_trigger: 1` と複数範囲の関係は TSK-330 へ申し送る(design.md 1-4)
- **契約と DDL の配信状態の語彙**(`completed` / `delivered`)の統一 — 本 PR は配信状態を書かない。台帳と申し送りで記録する
- **画面**(確認の手順・カルテや試合準備からの導線・「その他」の初期表示)— UI 要求は TSK-537、画面は frontend の実装単位
- **候補一覧から OB を除く入口**(スタメン・交代候補)— 試合準備の単位。本 PR の API は一覧の `roster_status_key` 絞り込み(#95 で着地済み)まで
- **初期ラベルの同梱・ラベル語彙の管理**(FR-017 の Should)— 別タスク(語彙の層は TSK-489)
- **`.claude/core-areas.json`・`scripts/core_guard.py` の変更** — 新規ファイルはすべて既存の glob(`backend/src/pitchlog/repositories/*`・`backend/src/pitchlog/api/*`・`backend/tests/test_*_boundary.py`・`backend/tests/test_*_repository.py`・`contracts/tenant_boundary/*`)で覆われる名前にする(2026-10-10 に fnmatch で 18 ファイルを実測)
- **認可カタログ(`contracts/authz/`)の変更** — 新しい token は経路を要さず(先例 `GameTeamLinkReadToken`)、HTTP の 2 経路は既存の `ROUTE:RECORD:players:read` / `:update` に載る

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/data-model.md` | 11-2 節: 発火条件の節の適用範囲を同期経路に狭め、`B06`(同期を通らないトリガー)を新設、④の対象テナント単位の選択子を `B06` の中に追加し、`B02` に ④ の例外の境界を足す。版 v0.6 → v0.7・変更履歴 | **finalize-doc**(確定ゲート — 裁定 J2) |
| `docs/README.md` | data-model 行の版・概要・最終更新日 / 台帳行の候補件数(クローズ処理) | PR レビュー |
| `docs/development/harness-evaluation.md` | クローズ処理での候補・実測の追記(版は上げない) | PR レビュー(7.6-3 前段) |
| `docs/design/sync-protocol.md` | **反映なし**(8-5 は同期側の責務に限ると明記しており、同期を通らないトリガーは 11-2 が持つ — 裁定 J1) | — |
| 要件書・ADR | **反映なし** | — |

## 4. 実装方針

- **重さ分類 = コア領域**: テナント分離(`backend/src/pitchlog/repositories/*`・`api/*`・`contracts/tenant_boundary/*`)と、U-T1 の凍結資産に触る。実装は ADR-001 のコア領域の行・各ステップで `codex_run.py review adversarial`・PR で人間の逐行確認
- 設計の詳細は [design.md](design.md)。人間の裁定 J1〜J4 は 8 節
- **着手の拘束**: ステップ 2 以降は**ステップ 1 の確定ゲートの PO 承認の後**に着手する(実装が正本の条文に先行しない)
- **新規ファイルの名前**: `backend/tests/test_roster_status_boundary.py`(実 DB の越境)・`backend/tests/test_invalidation_intents_repository.py`(実 DB のリポジトリ)。`test_authz*` を使わない(既存の `backend/tests/test_authz_cache_invalidation.py` の修正は除く)。`backend/tests/conftest.py` は変えない
- **DB テスト**: 共有 DB(5 タブ共用)で長い DB テストを回すときは事前に告知する。全件は CI に任せる

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **正本 11-2 節の改訂案を書く**(design.md 1 節)— `docs/design/data-model.md` の発火条件の節・`B06` 新設・`B02` の表・変更履歴(v0.7)と `docs/README.md` の data-model 行。**このあと /finalize-doc で確定ゲートを回す**(反映周のコミットはステップ記法を付けず `反映<r>周目`) | `uv run python scripts/check_plan_docs_sync.py` が exit 0・docs-lint が green・`backend/tests/test_authz_cache_invalidation.py` が green(正本の文言照合が既存の規則を失わない)。**確定ゲートの PO 承認**(frontmatter `確定ゲート周回`・worklog に記録) |
| 2 | **契約と純粋な要求生成器を追随させる** — `cache-invalidation-contract.json` を revision 11 へ(`durable_intent` に同期経路の `applies_to_trigger_ids` と `non_sync_triggers`〔`selectors` に対象テナント単位の選択子 — `physical_key_adt` には足さない〕・`api.public_symbols` と `api.condition4_allowed_call_symbols` に選択子の型・`source_digest`)、`repositories/cache_invalidation.py` に `SharedAggregateTargetSelector`、`test_authz_cache_invalidation.py` を改訂後の正本と契約に合わせる(`B02` の表と `physical_key_adt` の照合はそのまま、`B06` の選択子の表と `selectors` の照合を足す — design.md 1-3・2・3 節)。**テナント境界の受理記録をこの時点の比較元に対して 1 件置き、比較 corpus(`history-snapshots/`・manifest の `corpus_inputs.digest`)を同じコミットで再封印する**(acceptance_id 用の draft PR はこのステップの前に作る — design.md N1) | `backend/tests/test_authz_cache_invalidation.py` green(選択子がトリガー 14 で通る・10〜13 では拒否・2 つの `trigger_ids` が互いに素で和が 14 件・純粋性の検査)/ `uv run python scripts/check_tenant_boundary_bypass.py --base-ref origin/develop` が ok / `tests/test_check_tenant_boundary_bypass.py`・`tests/test_frozen_history.py`・`tests/test_frozen_archive.py`・`tests/test_frozen_archive_case_runner.py`(現版の全ケース一致・corpus の digest 一致)green / ruff・ruff format・ty green |
| 3 | **意図の記録と在籍区分の token を足す** — 新規 `repositories/invalidation_intents.py`(`InvalidationIntentInsertToken`・範囲名の写像・意図 ID の組み立て)、`repositories/roster.py` に `PlayerRosterStatusUpdateToken`(`id = :where_id` の 1 行更新)、`PlayerUpdateToken` の許可列から在籍区分の 2 列を外す。`repository-contract.json`・生成モジュール・`_OPERATION_REGISTRY`・`base-allowlist.json` の `allowed_symbols` と正例 fixture。**固定値を持つ既存テスト**(`backend/tests/test_authz_repository_contract.py` の token 型の組・`backend/tests/test_authz_capability_registration.py` の登録数)を capability 1 件・token 2 件の追加に合わせる。**受理記録を 1 件のまま導出し直し、比較 corpus を再封印する** | `backend/tests/test_invalidation_intents_repository.py`(実 DB: 1 行の列の値・意図 ID の形・RLS で他テナントの行を書けない)green / 写像が契約の 5 範囲と DDL の CHECK の 5 値を全単射で覆うテスト green / `PlayerUpdateToken` に在籍区分の列を渡すと拒否される負例 green(`backend/tests/test_roster_repository.py`)/ `backend/tests/test_authz_repository_contract.py`・`backend/tests/test_authz_capability_registration.py`・ステップ 2 の検査一式 green |
| 4 | **在籍区分の入口と発火点を開く** — `api/routers/players.py` に `status-preview`・`status-apply`。適用は 1 トランザクションで、指定 ID ごとに既存の `PlayerReadToken` で読み、区分の変わる行を `PlayerRosterStatusUpdateToken` で 1 件ずつ更新し、1 件以上なら意図を 1 行書く(design.md 5 節)。`backend/tests/test_api_app.py` の経路の固定を更新。**12-4 の判定**: 実スキーマ(`docs/ops/product-rls-real-schema.md` の手順)で `test_roster_status_boundary.py` を実行し、2 入口の `route_id`・method / path・実スキーマの識別・実行の記録を worklog に残す(PR 本文へは /pr で転記) | `backend/tests/test_roster_status_boundary.py`(実 DB・6 節の表)green / `backend/tests/test_roster_boundary.py`・`test_api_app.py` green / `check_tenant_boundary_bypass.py --base-ref origin/develop` が ok(TB004 は `CacheInvalidationTrigger.ROSTER_STATUS_CHANGE` の import と、`condition4_allowed_call_symbols` に載った呼び出しだけで通す)/ **実スキーマでの実行記録が worklog にある**(12-4 の記録項目を省かない) |
| 5 | **受理記録を base に対して 1 件へ導出し直し、比較 corpus を再封印する** — #95 の内訳 10 の手順を準用(`../um1-player-roster-opponent/plan.md:610-620`)。センサス基準が動けば同じコミットで更新する | 権威履歴に本 PR の記録が 1 件だけ / ステップ 2 の検査一式と `tests/test_census_baseline_check.py` green / CI の backend ジョブ green(`source_digest` と配布モジュールの stale はここで初めて出る) |

## 5. DoD(受け入れ基準)

### 正本と契約

- [ ] `data-model.md` v0.7(11-2 節の `B06`・発火条件の節・対象テナント単位の選択子・`B02` の ④ の境界)が確定ゲートを通り、PO 承認を得た
- [ ] `cache-invalidation-contract.json` が改訂後の正本と一致する(`test_authz_cache_invalidation.py` の照合)
- [ ] テナント境界の受理記録が本 PR について 1 件だけで、PR の base に対して再導出・再検証済み

### FR-017(API 面 — 画面は TSK-537 と frontend の単位)

- [ ] 3 区分(現役・その他・OB)のどれからどれへも変えられる(全区分可逆)
- [ ] プレビューは副作用が無く(区分も意図も書かない)、適用は別の入口
- [ ] 一括は 1〜50 件・重複不可(#95 の DTO)。存在しない・他テナント・論理削除済みの ID は区別なく `not_found_player_ids`
- [ ] 相手チームの選手にも適用できる
- [ ] PATCH は在籍区分を 422 で拒否し続け、`PlayerUpdateToken` は在籍区分の列を書けない

### 6.2(トリガー 14)

- [ ] 区分が実際に変わった適用で、同じトランザクションに意図が 1 行書かれる(`scope_kind = 'shared_total'`・`target_tenant_id` = 自テナント・`delivery_status = 'pending'`・意図 ID = `B06` の形)
- [ ] 値が変わらない適用・ラベルだけの適用では意図を書かない
- [ ] 意図の記録が失敗すると区分の変更も巻き戻る(故障系)
- [ ] 同じ選手を 2 回変えると意図が 2 行になる
- [ ] 「OB 化した選手が共有結果に現れない」(NFR-019(b) の列挙)は共有結果の経路が未実装のため本 PR の判定外(同条の未実装経路の扱い)。U-C1 へ申し送る

### 横断・機構

- [ ] 物理削除しない / テナント分離 / 一覧と一括は上限つき(NFR-005)
- [ ] pytest・ruff・ruff format・ty green。`backend/tests/conftest.py` の差分 0 行
- [ ] `.claude/core-areas.json`・`scripts/core_guard.py`・`contracts/authz/` の差分 0 行
- [ ] 12-4 の判定記録(入口を開く PR — U-M1 の DoD と同じ項目): 本 PR が開く 2 入口の `route_id` と method / path の組・実スキーマの識別・確認者と日時(ステップ 4 で実行して worklog に記録し、/pr で PR 本文へ転記)

## 6. テスト計画

| 対象 | 種別 | ファイル | 確認すること |
| --- | --- | --- | --- |
| 鍵の型と要求生成器 | 単体 | `backend/tests/test_authz_cache_invalidation.py` | 新しい鍵がトリガー 14 で通る / 10〜13 では拒否 / 純粋性(DB・キャッシュを import しない) |
| 契約と正本の一致 | 一致性 | 同上 | `durable_intent.non_sync_triggers` と 11-2 節 `B06` の文言・トリガー集合(9 件)の一致 |
| 範囲名の写像 | 単体 | `backend/tests/test_invalidation_intents_repository.py` | 契約の 5 範囲と DDL の CHECK の 5 値を全単射で覆う |
| 意図の記録 | 越境(実 DB) | 同上 | 1 行の列の値・意図 ID の形・他テナントの `tenant_id` では書けない(RLS) |
| token の分離 | 単体・負例 | `backend/tests/test_roster_repository.py` | `PlayerUpdateToken` に在籍区分の列を渡すと拒否 / 在籍区分 token は在籍区分の 2 列だけ |
| 入口(プレビュー・適用) | 越境(実 DB) | `backend/tests/test_roster_status_boundary.py` | 3 × 3 の可逆 / プレビューの副作用なし / 他テナント・存在しない・論理削除済みの ID が `not_found` / 相手チームの選手 / 上限 50 / Cookie 欠落 401・CSRF 欠落 403 |
| 発火点 | 受入(6.2) | 同上 | 区分の変更で 1 行・値の変わらない適用とラベルだけの適用で 0 行・2 回の変更で 2 行 |
| 原子性 | 故障系 | 同上 | 意図の INSERT を失敗させると区分も変わらない |
| 競合 | 故障系 | `backend/tests/test_roster_repository.py`(実 DB) | すでに目的の区分になっている行への在籍区分 token の更新が 0 件になる(読み取りの後に別の要求が同じ区分へ変えた場合と同じ状態)。その場合は意図を書かない |
| 凍結資産 | 機構 | `tests/test_check_tenant_boundary_bypass.py` ほか(ステップ 2 の一式) | 受理記録 1 件・現版の全ケース一致 |

E2E は無い(画面は frontend の単位)。

## 7. リスク

| # | リスク | 対処 |
| --- | --- | --- |
| R1 | 確定ゲートが長引き、実装の着手が遅れる | ステップ 1 の条文を design.md 1 節の骨子に限り、他単位の発火点の詳細は書かない。レビュー回数は設計書 6.3 の上限に従う |
| R2 | δ(TSK-470)が同じ権威履歴(`contracts/tenant_boundary/base-allowlist.json`)を触り、`contract_revision` がマージ順で直列化する | マージ順を master と調整する。base が進んだら N4 の手順(`(ステップ 5 再導出)`)で 1 回だけ取り込む |
| R3 | 粗い鍵は消しすぎになる | 配信側の展開で費用が決まる(J3)。消し漏れは起きない |
| R4 | 未配信の意図が配信の実装まで溜まる | 索引 `(tenant_id, delivery_status)` で引ける。件数は在籍区分の変更回数に比例し、上限 50 件の一括でも 1 行 |
| R5 | 共有 DB の残骸ロールで DB テストが大量に error になる(#95 で実測) | 共有 DB に手を入れない。CI の backend で判定する |

## 8. 人間の判断を仰ぐ事項

裁定済み(2026-10-10・山田正輝 — AskUserQuestion):

| # | 事項 | 裁定 |
| --- | --- | --- |
| J1 | 同期を通らないトリガーの規則の置き場 | `data-model.md` 11-2 に新設(9 件共通の一般則。実装はトリガー 14 だけ) |
| J2 | 正本改訂のゲート | 確定ゲート |
| J3 | 意図の粒度 | 粗い 1 行(対象テナント単位)。展開は配信側 |
| J4 | 配信の所有 | その範囲のキャッシュ本体を初めて導入する単位 |

計画の承認で併せて確認する作成者の判断(design.md 5 節):

| # | 事項 | 作成者の判断 | 理由 |
| --- | --- | --- | --- |
| A1 | ラベルだけの変更は発火しない | 発火しない | 共有の対象は区分で決まり、ラベルは挙動を持たない(要件書 `:397`・`:1040`) |
| A2 | 相手チームの選手の区分変更も発火する | 発火する | トリガー表は区別しない。消しすぎは安全側 |
| A3 | 適用でプレビュー時の値と照合しない | 照合しない | 区分は可逆で、競合しても再適用で戻せる。発火は UPDATE の述語「区分が実際に違う」の更新件数で決めるので、競合しても漏れも余分も起きない(計画レビュー 2 周目 P1) |
| A5 | 9 件共通にするのは発火条件・原子性の錨・意図 ID の骨格(操作 ID を含み、操作の中で行ごとに一意)だけ。行の数と行の識別子はトリガー 14 だけ定め、8・10〜13 の帰属と他の 8 件の行の規則は所有単位(U-A2・U-C1・U-D1 ほか)へ送る | 送る | 波及規則が「範囲ごと」と違い(全テナント・前後の和集合)、帰属を状態を変えたテナントにできない(計画レビュー 1 周目 P0)。J1 の「9 件共通の一般則」のうち帰属だけを狭める |
| A4 | 同期経路の 2 つの穴(1・3・4 の意図 ID・複数範囲と 1 行)は TSK-330 へ送る | 送る | J1 の射程外 |
