---
status: active
---
# 過去訂正CSVの共有保存接合

- 起点: `1f08dad11e054a29cc44e770ccc22f5438fbdc93`
- 承認: PO委任によるCodex主担当判断、2026-11-09 JST。既承認の訂正・CSVの同一TX保存を具体化する。意味仕様の追加、人間署名の代記ではない。
- 供給元: `mvp-p3-play-csv-producer-20261108` の保存宣言（9710f6ab）。公開handle.session誤用の修復92eeb229以降を接合対象とし、9710の実行成功は主張しない。
- 編集: 新規 `db/play_export_p3/`、migration0050、専用試験。後段の固定点が揃うまで既存startup・認可catalog・同期hookは変更しない。
- PG所有者はRecovery。ここではPGを起動しない。

| ステップ | 内容 | 完了条件 |
|---|---|---|
| 1 | 17列のappend-only型元と0050の固定DDL | 正規外部キー・JSON/hash制約、RLS強制、全ロールdefault-deny、型元とDDL一致、物理削除拒否 |
| 2 | producer/read/helperと正式ACL接合 | 実scope束縛、同TX原子性、全D1有限keyset、許可された列権限のみ。別担当固定候補をレビューして採用 |
| 3 | 起動版追随・実画面訂正後CSV | owned PGで実訂正→追加球→終了/再開→再終了→CSVを保存原本と照合。途中故障・越境・再送を含む |

独立レビュー・正式認可受理・CIは候補固定後に行う。純検査や未登録migrationを製品提供済みと数えない。

## ステップ2の候補固定（2026-11-09）

25268f69の5関数（writer3/read1/監査guard1）・36宣言を採用候補へ接合。新表17列のright-owner限定SELECT/INSERT、既normal9列はINSERTを保持してSELECT追加、vocab display_nameのみ既権限へ追加。app/actorの表DMLと新表xminは許可しない。rootは正式generatorから36行/36本文とmanifestを導出しDDL1221文を検査、再封印/7.7は未実施。CURRENT0050の22表と2guardを全属性比較し、clock_timestampの既知PG描画だけを照合する。readerは同RR専用、writerは既実private scope・P3 frame/nonce/実SessionをSQL前後で検証する。

検査: 新writer/read/coverage/宣言/構造92passed、追加storage/guard/xmin対向17passed、旧startup169成功に対する4失敗（新表数/default/新guardのfixture不足）を修復して該当4passed。root全Tyの既main由来7診断は別枝5461790aで修復済み、接合後に全検査する。実PG・実P3後CSV成功は未成立。source固定後の独立レビュー/実current0050配置/故障注入をステップ3で行う。共有DBへ適用しない。
