---
feature: roster-status-invalidation
type: research
date: 2026-10-10
---

# 調査メモ: 在籍区分の入口とキャッシュ無効化の発火点(TSK-447)

## 問い

1. 在籍区分の変更(FR-017・トリガー 14)で、無効化の**発火条件**・**原子性の錨**・**意図 ID** を正本・契約はどう定めているか
2. 意図表へ書く経路・配信・キャッシュ本体は、いまどこまで実在するか
3. FR-017 の受け入れ条件のうち、API で判定できるものは何か。旧システムから引き継ぐ挙動はあるか
4. 誰が何を所有するか(TSK-447・U-T1・TSK-330・各トリガーの所有単位)。正本の改訂はどのゲートを通るか

調査: 2026-10-10・調査サブエージェント 6 本(decision-tracer 2・spec-checker 1・legacy-analyst 1・Explore 2)。下の「原典で確認」は作成者が自分で原典を開いて確認したもの。

## 結論(要約)

- **正本 11-2 節の意図の永続化(`B03`・`B04`)は、`I5`(P3 の無効化発火)の永続化先として書かれている**(原典で確認 — `docs/design/data-model.md:2232-2243`「同 `I5`(同 8-5・8-1 の `T7`)は…要求する。本書はその永続化先を決める」)。発火条件は sync-protocol 8-5 が正だが(`data-model.md:2198-2210`)、8-5 の行は **D1 付き経路と I5 の 2 つだけ**で(原典で確認 — `docs/design/sync-protocol.md:1356-1361`)、**同期を通らないトリガーの発火条件の正はどこにも無い**。在籍区分は「同期側が発火させるトリガーではない」と明記されている(`sync-protocol.md:1893`)
- **契約 `cache-invalidation-contract.json` の `durable_intent` は、P3 用の規則(`same_transaction_with: "T7"`・`intent_id_derivation: [target_event_v10, target_confirmed_version]`)を 14 トリガーすべてに分岐なしで掛けている**(原典で確認 — `:459-487`)。**イベント由来でないトリガーは 9 件**(5 と 7〜14)。**対象行にはどれも版の列が無い**(下表)
- **キャッシュ本体・配信先・意図表へ書くコードは、どれもまだ無い**。Redis 等の依存も無い。あるのは純粋な要求生成関数(`backend/src/pitchlog/repositories/cache_invalidation.py`)と意図表(migration 0015)だけ
- **契約と意図表(DDL)の語彙が食い違っている**(範囲名・配信状態の値と列名・キーの列名)。両者をつなぐ層も、食い違いを指摘した記録も無い
- **旧システムに在籍区分は無い** — FR-017 はすべて新しい機能で、旧挙動として引き継ぐものは無い

## 詳細と典拠

### 1. トリガーの分類(イベント由来か)

前提: `V10` は undo・墓標・改訂・変更イベントに限る対象参照(原典で確認 — `sync-protocol.md:274`)。`V11`(期待版)は変更イベントに限る(同 `:275`)。P3 は #10 プレイ修正・#11 プレイ行の論理削除・#12 交代イベントの修正(`sync-protocol.md:1264`, `:1296-1298`)。所有単位は `docs/features/product-impl-unit-split/design.md:71-92`。

| # | トリガー(契約の行) | 区分 | 発生元(FR → 単位) | 対象行の版列 |
| --- | --- | --- | --- | --- |
| 1 | restored_sync(`:160`) | 同期(D1 経路・D3 の前進で発火)。V10・V11 は一般に無い | FR-012 → U-S1 | event_slots.confirmed_version はあるが D1 経路は進めない(`backend/src/pitchlog/db/sync_protocol/models.py:101`) |
| 2 | play_correction(`:172`) | 同期・P3(V10 + V11) | FR-007 → U-G2 | あり |
| 3 | undo(`:184`) | 同期・P1(V10 はあるが V11・T7 は無い — `sync-protocol.md:1288`) | FR-006 → U-X1 | 進めない |
| 4 | substitution_record_or_correction(`:196`) | 混在(記録は P2 で V10 無し、修正は P3) | FR-011 → U-G2 | 修正側だけ |
| 5 | game_delete_restore_or_resume(`:208`) | **イベント由来でない**(削除・復元は論理削除、再開はイベントを生成しない — `sync-protocol.md:313`) | FR-019 → U-D1 / FR-008 → U-G1 | 無い(games は status・trashed_at — `db/game_state/models.py:137,144`) |
| 6 | postgame_correction(`:220`) | 同期・P3 | FR-007 → U-G2 | あり |
| 7 | player_merge_or_split(`:232`) | **イベント由来でない** | FR-035 → U-A2 | 無い(`db/tenant_isolation/models.py:771-780`) |
| 8 | setting_change(`:244`) | **イベント由来でない**(システム管理者) | FR-037 → U-A2 | 無い(`:1281-1283`) |
| 9 | grant_flag_change(`:255`) | **イベント由来でない** | FR-041 → U-C1 | 無い(`:1065`) |
| 10 | group_departure(`:263`) | **イベント由来でない** | FR-041 → U-C1 | 無い(`:1020,1028`) |
| 11 | group_end(`:271`) | **イベント由来でない** | FR-041 → U-C1 | 無い(`:948,951`) |
| 12 | tenant_disable(`:279`) | **イベント由来でない** | FR-035 → U-A2 | 無い(`:83,86`) |
| 13 | tenant_reenable(`:287`) | **イベント由来でない** | FR-035 → U-A2 | 同上 |
| 14 | roster_status_change(`:295`) | **イベント由来でない** | FR-017 → U-M1(本タスク) | 無い(players は roster_status_key のみ・updated_at も無い — `:215-216`) |

- **件数の食い違い**: U-M1 計画書は「イベント由来でない **7** トリガー」(`docs/features/um1-player-roster-opponent/plan.md:121` — 内訳なし)、Notion TSK-447 本文は「少なくとも 6 種」と書く。上表では **9 件**(5・7〜14)。さらに 1・3・4(記録側)は同期由来だが V10 か V11 が欠け、現行の導出規則をそのまま当てられない
- 契約の `trigger_emission.downstream_owners` は「U-D1 and the units that own each triggering operation」(原典で確認 — `:488-492`)

### 2. 正本・契約・DDL の現状

- **11-2 節**: 意図表は「5-4 節の `T7` と同一トランザクションで 1 件書く」・意図 ID は「対象イベントの `V10` + 対象の確定版」(原典で確認 — `data-model.md:2238-2239`)。`B03` は 2026-09-08 に単一案で決定(`docs/worklog/2026-09-08-data-model-schema-orm.md:765-772`)。11-2 節は v0.1 以後改訂されていない(`data-model.md:29`)
- **トリガー 14 の範囲**: ④共有集計のみ(`data-model.md:2160`)。前後の和集合の規則は 10〜13 だけ(`:2192-2196`)。④のキーは `(グループ, 要求元テナント, 対象テナント, 期間)`(原典で確認 — `:2221`)
- **契約の固定**: `backend/tests/test_authz_cache_invalidation.py:327-359` が `durable_intent` を完全一致で固定し、正本の文言とも照合する。迂回検査器は最上位キーの完全一致・`source_digest`・`api` の 3 フラグだけを検査する(`scripts/check_tenant_boundary_bypass.py:1238-1359`)。負例 `C4_TRIGGER_ROSTER_STATUS` → TB004(`contracts/tenant_boundary/negative-fixtures.json:348-352`)
- **意図表(migration 0015)**: `backend/migrations/versions/0015_invalidation_intents.py:20-113`・ORM `db/sync_protocol/models.py:463-531`
  - 列: tenant_id / intent_id(text)/ scope_kind / game_id / player_id / group_id / requesting_tenant_id / target_tenant_id / period(jsonb)/ chart_kind / delivery_status(既定 'pending')/ delivered_at
  - 主キー `(tenant_id, intent_id)`・索引 `(tenant_id, delivery_status)`
  - 対象列 10 本は書き換え不可(トリガ・ERRCODE 23514)。更新を許すのは delivery_status・delivered_at だけ
  - **無いもの**: トリガー識別列・作成時刻・範囲ごとの必須列の CHECK・intent_id の形式の拘束
- **語彙の食い違い**:

  | 項目 | 契約(`cache-invalidation-contract.json`・`cache_invalidation.py:54-61`) | DDL(0015・ORM・`contracts/db/schema-manifest.json:1068`) |
  | --- | --- | --- |
  | 範囲名 | match / player_career / team_aggregate / shared_aggregate / analytics_chart | game / player_total / team_total / shared_total / chart |
  | 配信状態 | 値 pending/completed・列 delivery_state | 値 pending/delivered・列 delivery_status |
  | キーの列 | match_id・requester_tenant_id | game_id・requesting_tenant_id |

  対応づけ層は無い。契約側(`test_authz_cache_invalidation.py:327-350`)と DDL 側(`backend/tests/test_sync_protocol_models.py:504-514`・`tests/db/test_alembic_migrations.py:6418-`)が別々にリテラルを固定している。**食い違いを指摘した既存の記録は無い**
- **行の単位**: 契約は `rows_per_trigger: 1`(原典で確認 — `:462`)。表は 1 行に scope_kind を 1 つ持つ。トリガー 14 の④は鍵にグループと要求元を含むため、1 回の変更で複数の鍵に当たりうる。1 行で表す方法(NULL を「全体」と読むか等)は定義されていない(推論)

### 3. 実装の現状

- **キャッシュ本体・配信先: 無い**。`docker-compose.yml` は postgres 2 本だけ、`backend/pyproject.toml:5-10` に Redis 等なし、集計エンドポイントも無い(ルータは meta・players・team_records の 3 本)
- **要求生成**: `repositories/cache_invalidation.py` は純粋な値の factory(`:1-6`, `:321-323`)。src 内に呼び出し元は無い
- **意図表へ書く経路: 無い**。capability `CAP:invalidation_intents:read/insert/update` はカタログ登録済み(`contracts/authz/product/capability-catalog.json:91-103`)
- **発火点の先例: 無い**(トリガー 1〜14 のどれも)
- **#95 の在籍区分の扱い**: PATCH は `roster_status_key`・`roster_label_key` を 422 で拒否する(`api/routers/players.py:193-194`)。ただし `PlayerUpdateToken`(`repositories/roster.py:198-232`)の許可列は `PlayerUpdate` の全フィールドから作られ(`:93`)、**token の段階では在籍区分を書ける**。拒否はルーター層だけ。一括変更の DTO(`api/schemas/roster.py:141-192`)は定義済みでルータは無い
- **トランザクション**: `repositories/transaction.py` の `tenant_transaction_scope` が 1 Session の束縛・確定を持つ。複数 operation を 1 トランザクションで実行する単位は TSK-444(#82)で着地済み(`docs/features/um1-player-roster-opponent/plan.md:120`)

### 4. 要件(FR-017・6.2)

- **FR-017**(`docs/requirements/requirements-pitchlog-2026-07-22.md:390-399`)
  - 区分 3 つ(Must)・ラベル自由化(Should)
  - OB はスタメン・交代候補から完全に除外し、過去の成績は閲覧できる
  - 「その他」は初期表示に出ないが、明示操作で選べる
  - 全区分は可逆
  - 一括変更はプレビュー → 確認 → 実行
  - 相手チームの選手にも適用する
  - カルテ・試合準備の画面からも変更できる
  - 在籍区分の変更はキャッシュ無効化のトリガー
- **6.2**(`:1040`): 対応表を「各操作の受け入れテストに含める」(無条件)。NFR-019(b)(`:977`)の越境テストには「OB 化した選手が共有結果に現れないこと」があり、未実装経路の組合せは不合格の理由にしない
- **API で判定できるもの(推論)**: 値域・可逆性・プレビューに副作用が無いこと・適用が別の入口であること・相手チームの選手への適用・テナント外は 404・意図の記録・物理削除しないこと。**画面でしか判定できないもの**: 初期表示・確認の手順・カルテや試合準備からの導線(UI 要求は TSK-537 へ申し送り済み)
- **正本に無い事項**: ラベルだけの変更で発火するか / 作成時の初期区分 / 相手チームの選手(`kind='opponent'` は共有対象外 — `data-model.md:1372`)で発火を省けるか / ラベルと区分の対応の表し方 / 初期ラベルの seed
- **語彙**: 区分のキー active / other / ob(`contracts/seeds/roster-status.json`・`data-model.md:2022-2025`)。roster_label_key は tenant_vocabularies を MATCH SIMPLE で参照し、カテゴリ拘束が無い(`data-model.md:2036` → TSK-489)
- **U-M1 の DoD**: FR-017 行(`um1-player-roster-opponent/plan.md:650`)・6 節のキャッシュ失効の受け入れテスト(`:690`)・12-4 の route の組(`:680`)を本 PR へ送っている

### 5. 旧システム

- 在籍区分は**存在しない**。player は id / チーム_id / 背番号 / 名前 / 左右 だけ(`docs/legacy/research/data-layer.md:31-39`・`docs/legacy/baseball-scoring-db-structure.md:169`)。整理は物理削除だけ(`docs/improvements-from-baseball-scoring.md:125`)
- 旧要件 v0.2 の在籍は OB / 現役の 2 値で「新規」扱い(`docs/legacy/requirements-tsukuba-pss-v0.2.md:196-203`)
- 移行は全員「現役」で取り込み、移行後に棚卸しする(`docs/legacy/baseball-scoring-db-structure.md:309`)
- 旧システムのスタメン入力は候補のプルダウンではなく、名簿を表示して背番号で引く方式だった(`docs/legacy/research/services-shell.md:182-190`)。改善台帳の「候補に出続ける」はこの違いを踏まえて読む

### 6. 所有と改訂ゲート

- **U-T1** は契約と純粋な API まで。発火は持たず、「受け入れテストへの組み込みは各トリガーの所有単位が負う」(`docs/features/tenant-boundary-enforcement/plan.md:89,95`)。組み込み方の規定は無い
- **TSK-444** は実行単位。**TSK-447** は意図 ID と原子性の錨(`um1-player-roster-opponent/plan.md:134`)
- **T7(P3)の保存・配信**は TSK-330 へ送られている(`docs/features/sync-server-apply/plan.md:65` — これは TSK-321 の計画)。TSK-330 には計画書が無い
- **配信の所有**: 決めた記録は無い。保留・送付の記録だけ(`docs/features/product-authz-surface/design.md:674`「11-2 節を持つ単位の射程」)。U-M1 第 10 改訂が TSK-447 の PR の射程に「配信の仕組みの所有単位の決定」を入れた(`um1-player-roster-opponent/plan.md:463`)
- **他のイベント由来でないトリガーの所有単位**(U-D1・U-C1・U-A2)は計画書が無く、意図 ID・原子性・配信の想定は書かれていない
- **改訂ゲート**: 7.6-3 は「版繰り上げを伴う構造的変更は 7.3 の確定ゲート、実装追随の節更新は PR レビュー」(`docs/development/dev-harness-design-2026-08-07.md:526,532`)
  - data-model を実装追随で通した先例: TSK-480(人間の裁定 — `docs/features/vocab-category-fk/plan.md:65`)・TSK-475・12-8 節
  - 確定ゲートの先例: v0.3〜v0.6
  - 判定基準の先例: 「未実装の他単位の命名を正本で固定すると新しい共通設計規則になり、7.3 の確定ゲートへ入る」(`docs/features/roster-status-vocabulary-seed/plan.md:139-140`)
  - sync-protocol は改訂がすべて確定ゲート

## 未解決・申し送り

計画(/plan)で決める・人間の裁定に上げる論点:

1. **同期を通らないトリガーの発火条件の正をどこに置くか** — 8-5 は同期側の責務に限ると明記しており(`data-model.md:2207`)、11-2 は発火条件を写さない規律を持つ(`:2200`, `:2209`)。どちらの正本に置くかで改訂の範囲が変わる
2. **意図 ID の導出規則**(イベント由来でない 9 トリガー)— 例: 操作ごとに採番する ID・対象の識別子 + 単調な通番
3. **原子性の錨** — 候補「トリガーを起こした状態変更と同一トランザクション」(Notion TSK-447 本文)
4. **契約の書き方** — トリガー別の分岐か、`same_transaction_with` の値域を広げるか。テストの完全一致・7.7 の受理記録が追随する
5. **1 トリガー 1 行と、複数の鍵への波及** — ④の鍵の展開を書き込み時にするか配信時にするか
6. **契約と DDL の語彙の食い違い** — 本 PR で揃えるか、記録して送るか
7. **配信の所有** — キャッシュ本体が無い現状で、配信を誰がいつ作るか
8. **在籍区分を PATCH でも受けるか**(`um1-player-roster-opponent/design.md:167`)と、`PlayerUpdateToken` から在籍区分の列を外すこと
9. **正本の改訂ゲート** — 11-2 節(と 8-5)の改訂を確定ゲートにするか(新しい共通規則にあたる見込み)
10. **件数の訂正** — U-M1 計画書の「7 トリガー」と Notion の「少なくとも 6 種」は 9 件が正(本調査の表)
