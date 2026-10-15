# TSK-543 ステップ2・TSK-424共同確定最終候補（PO代替受理待ち）

基線: `origin/develop=93e1482a6404b6ff8aecd6abfacbbaaa79e99ecf`（#129統合）。対象は承認済みB06 v0.9・計画ステップ2だけ。製品コード・正本・認可・凍結資産は本候補では更新しない。独立査読v1のP0=0/P1=2/P2=1を全採用した差分を下に示す。

## 1. 保存形と既存行判別

`public.invalidation_intents`にnullable TEXT `target_selector_kind`を1列追加する。NULLは**旧形式**という版判別だけで、ワイルドカードではない。新トリガー5行は全件非NULL。値は`concrete_game`、`tenant_scope`、`shared_target_tenant`の3種。新たなテナントUUID列は増やさない。②③⑤はNOT NULLの`tenant_id`を選択子の明示テナント成分とし、④は`target_tenant_id=tenant_id`、①は`(tenant_id, game_id)`の具体鍵とする。対応は①`game/concrete_game`、②`player_total/tenant_scope`、③`team_total/tenant_scope`、④`shared_total/shared_target_tenant`、⑤`chart/tenant_scope`。

全新行の意図IDは`game_delete_restore_or_resume:<operation UUID>:<game UUID>:<scope_id>`。scope_idは契約の`match`/`player_career`/`team_aggregate`/`shared_aggregate`/`analytics_chart`。`operation_id`は1要求につきサーバー採番1個で、一括でも共通。`game_id:scope_id`は行識別子であり、曖昧連結を避けるためUUIDをcanonical lowercase表記し、区切りはコロン、scope_idは固定語彙だけを認める。

旧`target_selector_kind IS NULL`行は新選択子へ自動変換しない。既知の在籍区分選択子は**完全な**`roster_status_change:<canonical UUID>:shared_aggregate`と、`scope_kind=shared_total`、`target_tenant_id=tenant_id`、`game_id/player_id/group_id/requesting_tenant_id/period/chart_kind`が全NULLの組でのみ旧選択子と判定する。その他NULL行はscopeごとの旧物理鍵の全必須成分を既存ADT（試合=game_id、選手通算=player_id+period、チーム=period、共有=group_id+requesting_tenant_id+target_tenant_id+period、チャート=player_idまたはgame_idの片方+chart_kind）に照らして検証する。曖昧・不正形は配信保留とし、実DBの読取調査・後続所有者の裁定へ回す。NULLを全件指定に読み替えない。この判別はステップ3で配信所有者へ引き渡す契約であり、本ステップは配信実装を作らない。

## 2. DB制約、RLS/ACL、不変性

0031 migrationで列と新行限定CHECKを追加する。CHECKは（a）判別子の3値、（b）新トリガー5のID prefixと非NULL判別子の双方向一致、（c）新IDの**完全な**`trigger:UUID:UUID:scope_id`形式、（d）scope_kind・scope_id・判別子の5通りの対応、（e）①の`game_id::text=ID内のgame UUID`、（f）各種の非NULL/NULL列形、（g）④の`target_tenant_id IS NOT DISTINCT FROM tenant_id`を保証する。prefix判定はSQL LIKEの`_`ワイルドカードを使わず、`left(intent_id, length('game_delete_restore_or_resume:')) = 'game_delete_restore_or_resume:'`とする。UUIDはcanonical lowercase正規表現、scope_idは固定語彙。②③⑤のID内game UUIDと具体鍵①の同一性は単行CHECKでは証明できないため、保存器の検証済みrequestから一度だけgame UUIDを取り、5行tokenへ配り、別UUID注入・範囲入替・重複・5行欠落の負例単体試験と実DB5行試験で閉じる。任意SQLのアプリロールが同一テナント内へ余分な意図を直接INSERTできる既存権限は残るが、他テナント成分の新選択子はCHECKとRLSで拒否する。

既存行を補完UPDATEしない。新列は`prevent_invalidation_intents_target_update()`のROW比較と`BEFORE UPDATE OF`トリガー列へ追加し、アプリロールの表全体UPDATEでも変更不可にする。新形式行がある状態でのdowngradeは値を落とすため拒否する。新形式行がない専用DBで往復を検証し、旧行の保持も確認する。

既存`pitchlog_app_tenant_owned`（PERMISSIVE FOR ALL・`tenant_id=app.tenant_id`のUSING/WITH CHECK）とFORCE RLSは維持。追加policyは作らない。`pitchlog_app`のSELECT/INSERT/UPDATEは維持し、DELETEや保守ロールの新権限を足さない。製品認可カタログと実DBのpolicy集合が対象表で**ちょうど既存1件**、FORCE RLS=true、ACLが既存値であることを検証する。別PERMISSIVE policyを追加した使い捨てDBの負例ではOR合成によって越境可能になる危険を可視化し、製品カタログのexact照合が余分なpolicyを拒否することを確認する。運用外DDLの追加そのものをRLSが防ぐわけではない残余リスクを明示し、今回独断でRESTRICTIVE policyへ設計変更しない。

## 3. 保存器とU-D1境界

U-T1保存器は、検証済み`CacheInvalidationRequest`、サーバー採番の1操作UUID、U-D1が状態UPDATE RETURNINGから得た変更済み試合IDだけを受け、同一`tenant_transaction_scope`で試合ごとに①〜⑤各1行をINSERTする。0行結果では呼ばず意図0行。5行目失敗・一意衝突で例外を伝播する。同一scopeで状態UPDATEとともに呼んだ場合は両方をrollbackする契約とし、実状態変更との統合検証はU-D1が受け持つ。一括要求は1操作ID、各試合×5行でIDが異なる。U-D1の状態更新・ロック順・同期確定・遅延イベントは本ステップでは実装せず、U-D1の統合試験とステップ3引き渡しに残す。

## 4. 変更対象と個別ゲート

- 新規`backend/migrations/versions/0031_invalidation_intent_selectors.py`、既存`backend/src/pitchlog/db/sync_protocol/models.py`、`backend/src/pitchlog/repositories/invalidation_intents.py`、`contracts/db/schema-manifest.json`（列・CHECK・protected_columns）、関連するORM/不変性検査、`backend/tests/db/test_alembic_migrations.py`、`backend/tests/test_invalidation_intents_repository.py`、必要な新規専用DB試験。
- `contracts/authz/product/`の表分類・policy・ACL・DDL要素・SQL bodyは候補上差分0。TSK-424所有側に、列追加と既存表全体権限・policyとの整合、および差分0判定の受理を依頼する。実検査で追随が必要なら具体差分を再提示する。
- 凍結oracle入力8資産と既存7.7履歴は候補上不変。実差分で凍結基準が動く場合だけ、完全な前後値を別途7.7人間確認へ出す。承認済みB06本文は変えない。`backend/tests/conftest.py`、U-D1 worktree、保守ロール/関数、既存DBは変更しない。
- 0031は現時点のworktree・開いているPRで未使用。PR #134はDB fixtureと文書だけの差分。正式着手/PR前にrevision head・番号・基線を再照合する。

## 5. 専用DB試験と未完了の引き渡し

使い捨てPostgreSQLクラスタへ製品認可DDL・FORCE RLSを適用し、0030→0031の往復、既知旧14行・旧物理共有行の保持/厳密判別、不正NULL行の保留、新5行の列値・一意ID、他テナントSELECT/INSERT/新共有対象指定拒否、新列の直接UPDATE拒否、5行目失敗・一意衝突の全rollback、policy集合とOR合成負例を検証する。対象アプリDBの旧行数・欠損は測定不能のまま、migrationを適用しない。

U-D1の実状態変更→5行/更新0行→0行/再送→0行の統合試験、共通ロック順、遅延イベント、保守用認可P0 3件は別ゲート。U-D1計画は未承認、正式引き渡しと受理はTSK-543のステップ3で行う。今回の査読・経路許可だけでTSK-424代替受理、7.7、コアレビュー、人間逐行確認を成立させない。
