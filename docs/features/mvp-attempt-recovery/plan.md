---
feature: mvp-attempt-recovery
status: active
承認: PO委任によるCodex主担当/root技術具体化（2026-11-07、sync-protocol 6-3-A の既決実接合）
重さ分類: コア領域
branch: feature/mvp-attempt-recovery
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-attempt-recovery
created: 2026-11-07
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
---

# 結果不明の同期試行を権威照会で終結する

## 既契約と対象

正本 `docs/design/sync-protocol.md` 6-3-A、DI1〜DI5 と既 E-1 を唯一の意味契約とする。a0c192a0 の真正申告敬遠と通常投球を実証入口として、HTTP 応答不明の元 attempt を同じ tenant/game/device・D4・codec・要求全体指紋で照会する。照会は実認証/C2 と同端末資格を通し、同じ排他境界で旧試行の終了と遅着適用の禁止を耐久確定する。業務側の T1〜T9 結果と D5 台帳は別々の権威証拠で確認する。`retry_allowed` は ACK ではなく、元本文/D5/V12を保持し新 attempt で E-1 に再送する許可だけとする。確定済みは DI2 の実応答を再受信するまで同期済みにしない。進行中・commit 不明・証拠不一致・別 tenant/device・旧原本破損は未解決で止める。

業務 DB 外側から見た行数 0 や Python の例外捕捉だけで取消成功を認定しない。本人署名・P6 blind・正式 7.7 はこの候補の成果ではない。

2026-11-07、root の非作者読取と PO 委任判断で本計画の step 1 着手を採用した。`business` 行が無い場合も、既発行参照・borrow・進行中 RPC の遅着適用を同じ業務鍵の遮断で排除してから判断する。control 側 register の遮断と business binding 作成の間の競合を、journal の intent/terminal と実 PG の txid 終結で別々に否定する。live/UNKNOWN を `retry_allowed` にしない。この判断は人間逐行確認・P6 blind・製品成功ではない。

step 1 の実装読取で、既 epoch fence は `FOR SHARE` であって旧 binding RPC を排出しないと判明した。root の指摘を採用し、業務 PG 側にも同 attempt の永続 tombstone を置く。業務 `publish_writer_binding` と `retire_sync_attempt` は同一 `(tenant,attempt)` advisory transaction lock で直列化し、遮断後の旧 publish を固定関数で拒否する。既 binding がある場合は全行の原識別、close 状態、実 xid 観測の closed outcome を再確認し、open/UNKNOWN は未解決のままにする。業務 tombstone commit を control retirement より先に置き、後者失敗と ACK 消失時も同原本の再照会で完結する。候補 migration `0046_sync_attempt_retirement` は本専用 WT の番号であり、他作者の正式番号と衝突すれば root が直列確定時に調整する。候補と正式受理は分離する。

業務 tombstone と固定関数の配備には正式 product authz の候補宣言、SQL body、列 ACL、body manifest が必要である。step 1 の範囲にこれらの公式 generator 由来候補を加える。既表・既ロールの余分な権限や再適用時の定義衝突を隠さず、候補の配備後に同一 owned PG で publish と retire の競合を測る。正式 7.7 の受理・記録は root の別ゲートとする。

## 所有と接合境界

担当の新規 WT `feature/mvp-attempt-recovery` は固定 `a0c192a0e282479790eb8daae6b025a4952022fc` 起点。候補編集は backend `sync/attempt_recovery.py`、`sync/stop_contract.py`、`sync/control_provider/{evidence.py,binding_control.py,sql/control-phase-schema.sql,sql/writer-binding-control.sql,sql/writer-binding-functions.sql}`、`durable_rights_ledger/adapter.py`、`api/routers/sync.py`、実 C2 route 宣言 `api/tenant_access.py`、必要な `sync/{apply.py,source_binding.py}`、frontend `api/{client.ts,client.syncEvents.ts,syncAttemptRecovery.ts,recoverableSyncPost.ts,gameLifecycle.ts,substitutionWire.ts,nativeUndoWire.ts}`、専用耐久 barrier と既 attempt persistence・必要な controller、専用試験・E2E。専用 control/business schema の migration/DDL、同 token 更新 route の `contracts/authentication/cookie_identity_v1.json`、公開 DTO/contract/登録は本 WT の未受理候補差分または cache patch とし、root が共有本体へ直列接合する。正本、数学、唯一 artifact、旧業務保存は変更しない。権限・DDL の一般緩和や固定成功 Port は作らない。

## 段階

| # | 実装単位 | 完了条件 |
|---|---|---|
| 1 | 既 control attempt/phase、business writer admission、耐久 ledger journal を同じ recovery fence で束ねる照会・旧試行遮断 | 旧 live 待機、同 identity 全値、未到達 attempt の遅着遮断、rollback/commit/unknown、結果と D5 の不一致拒否、再起動後不変を純試験と隔離 DB で確認。候補 DDL/最小権限を閉じる |
| 2 | 実認証/C2 の照会 HTTP と端末バリア・新 attempt 再送 | 元 wire/D5/V12/codec 不変、`retry_allowed` のみ新 attempt、同一許可の並行二重適用拒否、認証/tenant/device/世代/原本不一致は閉じる。旧 DI2〜DI5・B5/B6/B7順を維持 |
| 3 | owned PG/HTTPS と冷再起動の縦断・固定候補 | T4故障、ACK喪失、旧live、他tenant/device、照会排除、同本文/D5新attempt、二重加算なしを実値で照合。未成立の条件を別記し、全source SHA/patch/検査を封印して別非作者へ渡す |

各 step は成果と関連試験を固定 commit する。共通 owned PG/browser lock を全寿命使い、共有 DB/運用秘密を使わない。root の正式受理と独立レビューを候補自身の成功へ代記しない。
