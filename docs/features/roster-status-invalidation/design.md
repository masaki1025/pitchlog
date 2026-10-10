---
feature: roster-status-invalidation
type: design
date: 2026-10-10
---

# 詳細設計: 在籍区分の入口とキャッシュ無効化の発火点(TSK-447)

事実の典拠は [research.md](research.md)。人間の裁定(2026-10-10・山田正輝 — 計画書 8 節)は次の 4 点:

| # | 論点 | 裁定 |
| --- | --- | --- |
| J1 | 同期を通らないトリガーの規則の置き場 | **`data-model.md` 11-2 節に新設**(9 トリガー共通の一般則。実装は本 PR ではトリガー 14 だけ)。sync-protocol は改訂しない |
| J2 | 改訂のゲート | **確定ゲート**(/finalize-doc) |
| J3 | 意図の粒度 | **粗い 1 行**(対象テナント単位の共有集計の鍵)。グループ・要求元への展開は配信側 |
| J4 | 配信の所有 | **その範囲のキャッシュ本体を初めて導入する単位**。本 PR は記録まで |

## 1. 正本 11-2 節の改訂案(ステップ 1・確定ゲートの対象)

版は v0.6 → **v0.7**。下は改訂の骨子で、条文はステップ 1 で書いて確定ゲートにかける。

### 1-1. 「発火条件の正」の節(`data-model.md:2198-2210`)の書き換え

- 現行の「**本書は発火条件を再記述しない**」を「**同期経路(D1 付き経路・`I5`)の発火条件は再記述しない**」へ狭める
- 理由を併記する: 同 8-5 は同期側の責務に限ると明記し(`sync-protocol.md:1354` 付近)、FR-017 を対象外にしている(`:1893`)。**同期を通らないトリガーの発火条件はどの正本にも無かった**。二重定義にはならない
- 経路の表に 3 行目「**同期を通らないトリガー**(5・7〜14)→ 本書 `B06`」を足す

### 1-2. 新設 `B06`「同期を通らないトリガーの発火・原子性・意図 ID」

(`B05` は既存の「事前集計を持たない場合の契約」— `data-model.md:2245`。計画レビュー 1 周目 P1)

| 事項 | 規則 |
| --- | --- |
| **適用範囲** | トリガー **5・7・8・9・10・11・12・13・14**(同期イベントの `V10` を持たない操作)。**1・2・3・4・6 は従来どおり** 8-5 と `B03` |
| **発火条件** | トリガーが名指す状態の変更が**確定**したとき。**値が変わらない要求は発火しない**(例: 現役の選手を現役にする) |
| **原子性の錨** | **その状態変更と同一の DB トランザクションで意図を書く**。どちらかが失敗したら両方を巻き戻す。状態だけ確定して意図が無い、またはその逆の状態を作らない |
| **意図 ID(共通の骨格)** | **`<トリガーの ID>:<操作 ID>:<行の識別子>`**。操作 ID は**状態を変える 1 要求ごとにサーバーが採番する UUID**(**一括変更は 1 要求 = 1 操作 ID**)。**行の識別子は同じ操作の中で行ごとに一意**にする。何を行の識別子にするか(範囲・物理鍵など)と行の数は、トリガーごとに下の個別規則で定める(計画レビュー 2 周目 P0 — 同じテナント・同じ範囲に複数の鍵が要るトリガー〔5・7 など〕と、複数テナントへ波及する 8・10〜13 があるため、行の単位を共通則に置かない) |
| **行の数と行の識別子(トリガー 14 の個別規則)** | **1 操作につき 1 行**。鍵は 1-3 の対象テナント単位の④の鍵、行の識別子は `shared_aggregate`。**他の 8 件の個別規則は、所有単位が発火点を作るときに本節へ足す** |
| **一意性** | `UNIQUE (tenant_id, 意図 ID)`(`B03` の制約をそのまま使う)。操作 ID が要求ごとに新しく、行の識別子が操作の中で一意なので、**同じ選手を 2 回変えても 2 行になり、配信完了後の変更を取りこぼさない**(Notion TSK-447 の帰結 2) |
| **再試行と重複** | 同期経路の「保存済み結果の再掲」は無い。HTTP 要求の再送は新しい操作として扱い、値が変わらなければ発火しない(上の発火条件) |
| **帰属(自テナントの状態変更 — 5・7・9・14)** | 状態を変えたテナントの文脈で、`tenant_id` = そのテナント。鍵は `B02` の表の単位(④は 1-3 の対象テナント単位の鍵を使ってよい)。行の数は個別規則(上)。いずれも波及規則は「範囲ごと」(①〜③・⑤ = 所有テナント、④ = グループの実効参加 — `data-model.md:2176-2179`) |
| **帰属・行の数・鍵(8・10〜13)— 本改訂では定めない** | **8**(設定値・固定語彙の変更)は自テナントが無く全テナントへ波及し(`:2181-2187`)、**10〜13** は操作前後の実効参加の和集合へ波及する(`:2189-2196`)。意図をどのテナントに帰属させ何行書くかは、波及規則と RLS の書き手の両方に掛かるので、**所有単位が自分の発火点を作るときに本節へ足す**(8・12・13 = U-A2、10・11 = U-C1)。**発火条件・原子性の錨・意図 ID の共通の骨格はこれらにも掛かる**(計画レビュー 1 周目 P0) |
| **配信(`B04` の補足)** | **その対象範囲のキャッシュ本体を初めて導入する単位が配信を作る**。それまで意図は未配信のまま残り、`(tenant_id, 配信状態)` の索引で引ける。**意図を書く単位は配信を持たない** |

### 1-3. 物理的な無効化先(`B02`・`data-model.md:2212-2222`)への追加

④共有集計に「**対象テナント単位の鍵**」を足す:

| 対象範囲 | 物理的な無効化先 | 単位 |
| --- | --- | --- |
| ④ 共有集計(対象テナント単位) | **対象テナントが同じ④の鍵すべて**(グループ・要求元・期間を問わない) | **`(対象テナント)`** |

- **使うのは同期を通らないトリガーの記録だけ**。書く側が実効参加(3-0 節の共通述語)を評価せずに済む。**展開は配信側**が行う(J3)
- **広めに消す向き**なので、消し漏れは起きない。消しすぎの費用は配信側の展開で決まる
- **鍵の先頭がテナント**なので「無効化先の鍵は必ず `tenant_id`(または グループ)を先頭に含める」(`:2224`)を満たす。書く主体のテナントと鍵のテナントは一致する(他テナントの鍵を名指して消す経路にはならない)

### 1-4. 改訂しない事項(本 PR の外へ送る)

- **同期経路の 1・3・4(記録側)も `B03` の導出規則に当てはまらない**(`V10` か `V11` が欠ける — research.md 1 節)。本 PR は同期経路を改訂しない(J1)。TSK-330(T7 の保存・配信)へ申し送る
- **`rows_per_trigger: 1` と、複数の対象範囲を持つトリガー**(例: 2 は 5 範囲)の関係は、`B03`(同期経路)では未定義のまま。表は 1 行に 1 範囲しか持てない。TSK-330 へ申し送る
- 契約と DDL の語彙の食い違い(2 節)は正本の問題ではない(11-2 は①〜⑤の日本語名で書いている)

## 2. 契約 `cache-invalidation-contract.json`(revision 10 → 11)

凍結資産(`contracts/tenant_boundary/`)。7.7 の受理記録は本 PR で 1 件(計画書 4 節 ステップ 5)。

- **`physical_key_adt.variants`** に 1 件追加:
  - `kind: "shared_aggregate_of_tenant"`・`scope_id: "shared_aggregate"`・`python_type: pitchlog.repositories.cache_invalidation.SharedAggregateOfTenantCacheKey`・`fields: [["tenant_id","uuid.UUID"]]`・`source_unit: "(対象テナント)"`
  - フィールド名を `tenant_id` にするのは `tenant_or_group_prefix_required: true` を満たすため
- **`durable_intent`** の中に、**同期側と同期を通らない側の規則の適用範囲を両方とも明示する**(**最上位キーは変えない** — 迂回検査器は最上位キーの完全一致を見る `scripts/check_tenant_boundary_bypass.py:1253-1272`。計画レビュー 1 周目 P1):
  - 既存の直下の規則(`same_transaction_with: "T7"`・`intent_id_derivation: [target_event_v10, target_confirmed_version]` ほか)に **`applies_to_trigger_ids`**(1・2・3・4・6 の 5 件)を足し、**同期経路の規則**であることを機械可読にする
  - 新しい入れ子 `non_sync_triggers`(下)を足す
  - **テストで、2 つの `trigger_ids` 集合が互いに素で、和が `triggers` の 14 件と一致すること**を固定する(どちらの規則も掛からない、または両方が掛かるトリガーを作らない)。`attribution` の値域は 2 値(`self_tenant` = 5・7・9・14 / `defined_by_owner_unit` = 8・10〜13 — 1-2 節)
  ```json
  "non_sync_triggers": {
    "trigger_ids": ["game_delete_restore_or_resume", "player_merge_or_split", "setting_change",
                    "grant_flag_change", "group_departure", "group_end",
                    "tenant_disable", "tenant_reenable", "roster_status_change"],
    "firing": "committed_state_change_with_value_change",
    "same_transaction_with": "triggering_state_change",
    "intent_id_derivation": ["trigger_id", "operation_id", "row_discriminator"],
    "row_rules": {
      "roster_status_change": {"rows_per_operation": 1, "key_kind": "shared_aggregate_of_tenant", "row_discriminator": "scope_id"}
    },
    "row_rules_for_other_triggers": "defined_by_owner_unit",
    "attribution": {
      "self_tenant": ["game_delete_restore_or_resume", "player_merge_or_split",
                      "grant_flag_change", "roster_status_change"],
      "defined_by_owner_unit": ["setting_change", "group_departure", "group_end",
                                "tenant_disable", "tenant_reenable"]
    },
    "delivery_owner": "unit_that_introduces_the_scope_cache"
  }
  ```
  キーの綴りは実装時に原典で確定する(N2)
- **`api.public_symbols`** と **`api.condition4_allowed_call_symbols`** の両方に `SharedAggregateOfTenantCacheKey` を足す(TB004 は呼び出しを後者で判定する — `scripts/check_tenant_boundary_bypass.py:5232`。計画レビュー 1 周目 P1)。発火点(ステップ 4)が呼ぶのは `build_cache_invalidation_request` と新しい鍵のコンストラクタだけで、どちらも後者に載る
- **`source_digest`** を再計算する
- `trigger_emission`・`api` の 3 フラグ(`owns_trigger_emission` ほか)は**変えない** — 純粋な要求生成器の性格は保つ。発火は本 PR のリポジトリ層が持つ

## 3. 純粋な要求生成器(`repositories/cache_invalidation.py`)

- `SharedAggregateOfTenantCacheKey(tenant_id: UUID)` を足し、`_KEY_SCOPES` で④へ写す
- `build_cache_invalidation_request(ROSTER_STATUS_CHANGE, (SharedAggregateOfTenantCacheKey(T),))` が通ること。既存の `SharedAggregateCacheKey` も引き続き④として通る
- 参加変更トリガー(10〜13)の和集合の検査は `SharedAggregateCacheKey` にだけ掛かる。**10〜13 に粗い鍵を渡したときの扱い**は、それらのトリガーの所有単位が決める。本 PR では**拒否する**(既存の検査を弱めない)
- **DB・キャッシュを import しない**性質は保つ(`backend/tests/test_authz_cache_invalidation.py:415-430`)

## 4. 意図の記録(新規 `repositories/invalidation_intents.py`)

- **operation token** `InvalidationIntentInsertToken`(`CAP:invalidation_intents:insert` — カタログ登録済み `contracts/authz/product/capability-catalog.json:96-100`)
- **入力**: 検証済みの `CacheInvalidationRequest` と操作 ID。要求の各鍵から 1 行を作る
- **語彙の写像**(契約 → DDL)を**このモジュールに 1 つだけ**置く:

  | 契約の `scope_id` | DDL の `scope_kind` |
  | --- | --- |
  | match | game |
  | player_career | player_total |
  | team_aggregate | team_total |
  | shared_aggregate | shared_total |
  | analytics_chart | chart |

  テストで、**契約の 5 範囲と DDL の CHECK の 5 値の両方を全単射で覆う**ことを固定する(片側だけ増えたら赤)
- **列の埋め方**(トリガー 14): `tenant_id` = 文脈のテナント・`intent_id` = 1-2 の形・`scope_kind = 'shared_total'`・`target_tenant_id` = 文脈のテナント・`group_id`/`requesting_tenant_id`/`period`/`chart_kind`/`game_id`/`player_id` = NULL・`delivery_status` は既定の `'pending'`
  - 「NULL = 全体」の読みは 1-3 の鍵の定義が正。DDL は変えない(列はすでに NULL 可)
- 配信状態の語彙(`completed` と `delivered`)は、本 PR では書かないので写像しない(既定値に任せる)。食い違いは台帳と申し送りで記録する

## 5. 在籍区分の入口(`api/routers/players.py`・`repositories/roster.py`)

経路は U-M1 の設計(`../um1-player-roster-opponent/design.md:67-68`)どおり:

| # | method | path | operation_id | 要求 | 応答 | 認可の経路 |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | POST | `/players/status-preview` | `roster_player_status_preview` | `PlayerStatusBulkRequest` | `PlayerStatusPreview` | `ROUTE:RECORD:players:read` |
| 6 | POST | `/players/status-apply` | `roster_player_status_apply` | `PlayerStatusBulkRequest` | `PlayerStatusApplied` | `ROUTE:RECORD:players:update` |

- **DTO は #95 で定義済み**(`api/schemas/roster.py:141-192`)。上限 50・重複不可
- **既存の 1 行 token を繰り返す**(計画レビュー 1 周目 P1): 操作の登録検査は UPDATE に `id = :where_id` を必須とし(`backend/src/pitchlog/repositories/base.py:173`)、`RETURNING` を拒否し(`backend/src/pitchlog/authz/capability_registration.py:969`)、`run()` は更新件数を返す(`base.py:335`)。一括の UPDATE は書かず、**1 トランザクションの中で 1 件ずつ**(上限 50)実行する。新しい読み取り token は作らない
- **プレビュー**: 読み取りだけ。指定 ID ごとに既存の `PlayerReadToken`(単一 `record_id`)で引き、`changes`(区分が変わる選手)・`unchanged_player_ids`・`not_found_player_ids` に分ける。**副作用なし**(意図も書かない)
- **適用**: `tenant_transaction_scope` の 1 トランザクションで:
  1. 指定 ID ごとに `PlayerReadToken` で現在の区分を読み、見つからない・区分が同じ・区分が変わるに分ける
  2. 区分が変わる行を 1 件ずつ `PlayerRosterStatusUpdateToken` で更新する。文は `UPDATE … WHERE tenant_id … AND id = :where_id AND roster_status_key <> :new`(**区分が実際に違うことを UPDATE の述語に置く** — 登録検査は最上位の AND に `id = :where_id` があることを求めるだけで、他の条件を足せる — `_has_required_bound_equality` `base.py:110` 以降)。ラベルの指定があれば同じ文で書く
  3. 2 の更新件数が 0 の行(読み取りの後に別の要求が同じ区分へ変えた)と、ラベルだけ変える行は、ラベルだけを更新する文で 1 件ずつ更新する
  4. **2 の更新件数の合計が 1 以上**なら、トリガー 14 の要求を作り(3 節)、意図を 1 行書く(4 節)
  5. 応答は更新後の行と `not_found_player_ids`
  - **読み取りと更新の間の競合**: 同時に 2 つの要求が同じ選手を同じ区分へ変えると、後の UPDATE は行ロックを待ち、先の確定後に述語を評価し直して 0 件になる(READ COMMITTED)。**発火するのは区分を実際に変えたトランザクションだけ**で、漏れも余分も起きない(計画レビュー 2 周目 P1)
- **見つからない ID**: 存在しない・他テナント・論理削除済みは区別せず `not_found_player_ids` に入れる(存在を漏らさない — 他テナントは存在しない ID と同じ扱い)
- **ラベルだけの変更は発火しない**: 共有の対象は区分(`active`)で決まり(`requirements-pitchlog-2026-07-22.md:1040`)、ラベルは挙動を持たない(`:397`)
- **相手チームの選手も同じに扱い、発火する**: 相手チームの選手は共有の対象外だが(`data-model.md:1372`)、トリガー表は区別しない。消しすぎは安全側
- **確認の手順**(プレビューと適用の間)は画面の責務(TSK-537)。適用は要求時点の値で冪等に動き、プレビュー時の値との照合はしない(区分は可逆で、競合しても再適用で戻せる)
- **token の分離**:
  - 新規 `PlayerRosterStatusUpdateToken`(`CAP:players:update`・許可列 = `roster_status_key`・`roster_label_key`)
  - **`PlayerUpdateToken` の許可列から在籍区分の 2 列を外す**(#95 は token の段階で書けてしまい、ルーターの 422 だけが止めていた — research.md 3 節)。PATCH の 422 は残す
- **TB004**(迂回検査 条件 4): 発火点のコードは `CacheInvalidationTrigger.ROSTER_STATUS_CHANGE` を import して参照する(`../um1-player-roster-opponent/design.md:42-44` の救済経路)。識別子に `roster_status_change` を直に書かない

## 6. 凍結資産と受理記録(計画書 4 節 ステップ 2・3・5)

- 動く資産(すべて `contracts/tenant_boundary/` の権威履歴に載る):
  - `cache-invalidation-contract.json`(ステップ 2)
  - `repository-contract.json`(`product_capability_ids` に `CAP:invalidation_intents:insert`、`product_operation_token_types` に 2 token — ステップ 3)
  - `base-allowlist.json` の `allowed_symbols`(文の組み立て関数 — ステップ 3)
- 生成モジュール `repositories/repository_contract.py` を同期する
- **受理記録は本 PR で 1 件**(`intermediate_commits_are_records: false`)。資産を動かすコミット(ステップ 2・3)には毎回その時点の記録を置き、ステップ 5 で base に対して 1 件へ導出し直す(#95 の内訳 5・10 の手順を準用 — `../um1-player-roster-opponent/plan.md:536-620`)
- **比較 corpus の再封印も資産を動かすコミットごとに行う**: `contracts/tenant_boundary` は比較 corpus の入力 tree で、`tests/test_frozen_archive_case_runner.py` が固定 digest を照合する(`tests/fixtures/frozen-archive-cases/manifest.json:16-18`)。ステップ 2・3 で `history-snapshots/` と manifest の `corpus_inputs.digest` を再 pin し、ステップ 5 で base に対して再度行う(計画レビュー 1 周目 P1)
- **固定値を持つ既存テストの更新**(ステップ 3): `backend/tests/test_authz_repository_contract.py:481` 付近(token 型の組)・`backend/tests/test_authz_capability_registration.py:1100` 付近(登録数 8)を、追加する capability 1 件・token 2 件に合わせる(計画レビュー 1 周目 P1)
- **認可カタログ(`contracts/authz/`)は動かさない**: 新しい token に経路は要らない(先例: `CAP:games:read` の `GameTeamLinkReadToken` は経路なしで登録済み)。HTTP の 2 経路は既存の `players:read`/`players:update` に載る

## 未解決・検討メモ

- **N1** acceptance_id 用の draft PR はステップ 2 の前に作る(#95 の N3 と同じ)
- **N2** 契約の入れ子キーの綴りと値域(2 節の JSON は案)
- **N3** 文の組み立て関数の名前と数(`allowed_symbols` は 1 シンボル 1 正例 fixture)
- **N4** base が `contracts/tenant_boundary/` ごと進んだときの再導出(#95 の N4 の tenant_boundary 系列と同じ — `(ステップ 5 再導出)`)。**δ(TSK-470)が同じ権威履歴を触る**ので、マージ順は master と調整する
