# U-G1 向け: preparing 作成の RG1 接続受理シート

2026-10-14。U-G1 はコミット `79e3da4a549a91c6ce7937169837cf9c71ddf64c` の計画 4 節で、**作成側の接続面を項目別に受理済み**。下表の呼出し位置・入力/戻り・B7 相当の意味・ロック保持/全取消が受理範囲。具体例外型、DB 競合分類、HTTP 写像、RG1 状態行と operation 登録は製品接続前の確定事項であり、受理済みとは扱わない。試合開始時の D4/V12 発行契約は別ゲート。

| 項目 | U-G1 が受理した接続面と残る実装確認 |
| --- | --- |
| 入力と型 | **受理済み**: `read_rg1_open(scope: _TenantTransaction, *, game_id: UUID | None) -> None` と `assert_rg1_open_before_commit(scope: _TenantTransaction, *, game_id: UUID | None) -> None`。`_TenantTransaction` は既存 `tenant_transaction_scope` の不透明ハンドル（`repositories/transaction.py`）で、作成前は `game_id=None`。U-R1 は独自 commit・Session 公開をしない。私有型の import/operation token の登録方法は実装時の確認事項 |
| 実行位置 | **受理済み**: U-G1 が認可を終えた後、試合行 INSERT の前に `read_rg1_open`。試合行と規則参照に関する全変更が済んだ後、**scope の正常終了/commit の直前**に `assert_rg1_open_before_commit`。両者は同じ RG1 永続状態行を読み、前者はロックなし、後者は `FOR SHARE` で再読する |
| ロック保持期間 | **受理済み**: `FOR SHARE` 成功時から同じ U-G1 transaction の commit/rollback まで。operation 内でロックを解放・別 transaction を開始しない。復元開始側は同じ行を `UPDATE`（排他競合）して調整中へ確定する。移行の最初の transaction は RG1 行だけを更新し、ゲーム行を同時に待たない。実 U-G1 scope でのロック順・分離レベルは結合試験待ち |
| 成功・失敗結果 | **意味は受理済み**: 成功は `None`。調整中・欠損・不明・読取失敗、事前通過後の復元先行は fail-closed で B7 相当の再試行可能な結果とし、試合行を含む全変更を rollback。**未確定**: Python 例外/結果の具体型、ロック待機/DB 競合の分類、HTTP status/DTO に必要な識別情報。`RG1Unavailable` は U-R1 の仮名であり採用済み型ではない。内部理由でテナントの存在を漏らさず、接続断/ロック失敗を成功にしない |
| D4 との分離 | **受理済み**: `preparing` 作成では初期記録権世代行、D4、V12、保持端末、復旧世代を発行しない。D4 台帳の採否をこの二関数の契約受理条件にしない。ただし RG1 の実状態資源と operation が使用可能になるまで、製品の作成成功を返す実装は不可 |

## 実測証跡と限界

使い捨て `postgres:17.11-bookworm` の `rg1_probe` 状態行と `game_probe` 試合行を使い、二接続・同一 transaction 内の `SELECT`、`INSERT`、`SELECT ... FOR SHARE`、復元側 `UPDATE` を実行した（2026-10-14）。復元開始が先に `active` を commit した順序では、直前再読が拒否し、作成側 transaction の試合行は **0 件**。作成側の `FOR SHARE` が先の順序では、復元側 `UPDATE` は作成 commit まで **1.42 秒待機**し、その後 `active` を確定した。検証コンテナは停止・自動削除済み。試験スクリプトは `/tmp/pitchlog_rg1_probe.py` のローカル一時物で、製品経路や共有 fixture は変更していない。

この証跡は PostgreSQL のロック競合と rollback の確認である。**U-G1 の実 `tenant_transaction_scope`・認可・試合作成経路での結合試験は未了**。RG1 永続状態行の migration/権限/凍結契約も未承認・未実装。

**受理と未完了を分離する**: ①関数と不透明ハンドル、②事前/直前の呼出位置、③B7 相当の意味、④ロック保持、⑤試合行を含む全取消は U-G1 `79e3da4a` で受理済み。U-S1 の ③-a/⑧・復元開始直列化の担当受理、U-R1 の具体例外/operation 登録/永続状態/起動時 fail-closed、U-G1/U-S1 実経路の結合試験は未了。U-G1 からの残差分依頼は TSK-392 コメント `3f993b75-e687-81f7-8f55-001da135f25a`。
