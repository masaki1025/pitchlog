# RG1 初期状態行と seed 許可台帳の整合調査

## 追加範囲の承認と候補（2026-10-16）

依頼者（PO）はRG1専用seed系列と限定検査器変更を追加範囲として承認した。初期投入の許可は`(singleton_id=1, state='closed')`の完全一致のみで、別ID・open/不明状態・追加行・既存行上書きは禁止。既存語彙seed系列と受理履歴は維持する。これは候補作成・隔離検証・レビューの許可であり、7.7正式受理、運用open、push/PR/mergeの許可ではない。

ローカル候補は`backend/migrations/versions/0032_rg1_restore_gate.py`、`backend/tests/fixtures/rg1/seed-allowlist-candidate.json`、`backend/tests/test_migration_hygiene.py`、`backend/tests/test_rg1_seed_migration.py`。候補JSONは`pending_7_7`の試験fixtureであり、正式台帳`contracts/migrations/seed-allowlist.json`は未変更。A統合前の暫定revision/parentで、正式なrevision・digest・snapshotはA統合後に再算出する。未受理期間はmigration衛生全件検査が新候補を拒否する状態を維持し、正式受理前に全件greenとは扱わない。

2026-10-15。新4のローカル候補を対象とする。正式な資産差分・7.7受理記録ではない。

## 結論と根拠

RG1 の物理表は承認済みの `public.rg1_restore_gate(singleton_id, state)` とし、初期行は厳密に `(1, 'closed')` だけとする。製品の2読取関数はこの行が欠損・不明でも成功せず、新4では `open` 行があっても常に `false` を返す。隔離DBでの `open` fixture はロック機構の試験だけに用い、製品解除には使わない。

既存の migration 衛生試験は、宣言のない `op.bulk_insert` と文字列 `INSERT INTO` を禁止する。現行 `contracts/migrations/seed-allowlist.json` の2系列は語彙表の `category/key` 行だけを表し、検査器 `_bulk_insert_matches` と `_delete_matches_scope` もその形を要求する。現行台帳のままRG1行を `op.bulk_insert` する最小候補を検査すると、`禁止 API bulk_insert()` で不合格になる。RG1の列を語彙表の形へ変えて検査を通すことは承認済みDDLと衝突する。DDLにDMLを紛れ込ませる方法も採らない。したがって、**RG1初期行をmigrationで投入するなら、新しい限定seed系列と検査器の形の追加が必要**である。

## 個別承認に出す最小差分

| 対象 | 追加候補 | 境界・影響 |
| --- | --- | --- |
| `backend/migrations/versions/<A統合後の次revision>_rg1_restore_gate.py` | 表・制約を作成し、同一upgradeの `op.bulk_insert` で `[{"singleton_id": 1, "state": "closed"}]` だけ投入。downgradeはそのrevisionが作った表を戻す | 復元や通常運用で `open` にする処理を含めない。migrationの実番号と親はA統合後に固定 |
| `contracts/migrations/seed-allowlist.json` | 既存2系列・履歴はそのまま、新系列 `rg1_closed_seed` に当該revision・対象表・1行の完全値と型を宣言。7.7-2の**新しい受理記録1件**は正式判断後に追記 | 他の表、行、DML API、既存系列を許可しない。承認者・承認日は事前に記入しない |
| `backend/tests/test_migration_hygiene.py` | 語彙用 `category/key` 形を維持したまま、宣言で選ぶRG1の `singleton_id/state` 完全一致形だけを検査。対象revision以外、追加行、`open`、別ID、UPDATE/DELETE、手書きSQLを拒否する試験 | 汎用DML許可や既存seedの緩和をしない。downgradeの許可は表作成と同一revisionの `drop_table` に限る |

台帳候補の許可値は `target_tables=["rg1_restore_gate"]`、`upgrade_calls=["bulk_insert"]`、`upgrade_rows.count=1`、`upgrade_rows.rows=[{"singleton_id":1,"state":"closed"}]` とする。既存の `category/key` 用 `downgrade_delete_scope` をRG1に流用せず、専用形の宣言と検査を追加する。実際のJSON key・revision path・canonical identityは、A統合後に完全差分として固定する。現段階で正式台帳へは書かない。

## 残る判断

上表のseed系列・migration衛生検査器の限定拡張は、2026-10-16に候補範囲として追加承認された。**正式台帳の実revision・digest・snapshotと7.7正式受理は別判断**。新4の候補実装・隔離試験は先行できるが、正式資産・履歴を受理済みとして扱わない。Aのdevelop統合後に実値と全差分を提示する。

## 常閉試験の現在地

| 系列 | 実測した内容 | 未了の範囲 |
| --- | --- | --- |
| 隔離行ロック | 直接 `FOR SHARE NOWAIT` が試験用open行で成功し、復元先行では即時拒否、通常側先行では復元UPDATEが待つ。列 `UPDATE(singleton_id)` は必要だが `UPDATE(state)`・INSERT・DELETEは拒否 | U-S1/U-G1の実入口と運用解除は新8/新7 |
| 製品候補2関数 | closed/open/制約を壊したunknownで常にfalse。GUC欠損・tenant不一致はfalse、GUC不正と行欠損は例外で成功しない。専用ownerはNOLOGIN/NOBYPASSRLS、表はFORCE RLS、appの表直接SELECTと第三者EXECUTEは拒否 | Aの固定関数実行器・製品registry経由のscope注入、同一scope全取消はA統合後。全経路結合は新8 |
| 関数公開 | fixtureで関数作成・PUBLIC剥奪・app付与を1 transactionにまとめ、2関数目の故障時に1関数目までrollback | 正式製品認可資産とprovisionerの実適用試験は候補資産完成後 |

これらは隔離PostgreSQLの限定試験であり、全backend/認可/凍結/archive検査や7.7正式受理の代わりにならない。`origin/develop=3f6a935a`へ共有実行器A `196f1e3d`はまだ未統合（2026-10-15確認）。
