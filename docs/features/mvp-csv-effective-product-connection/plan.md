---
feature: mvp-csv-effective-product-connection
status: active
branch: feature/mvp-csv-effective-product-connection
承認: PO委任によるCodex主担当/root判断（2026-11-07、既毎球CSVの実接合）
計画レビュー周回: 0
確定ゲート周回: 0
---

# 有効版の毎球CSVを唯一Sの実readへ接続する

既ud2-csv-export/mvp-play-csv-deliveryの未完接合を具体化する。root候補c181166cを起点とし、作者42d8924cの13pathと共有3path patchを再利用する。非作者REPORT d05b3661e00a431111857a987dd718aa8dca2d2b88e29a58d1f095c7352a2b2aで新P0/P1/P2なし、独立127試験/登録・codec拒否probeを照合済み。作者r13の実画面取消→全取消→再入力→reload/T5 source一致、r14の真正3球とRR/RO読取を、まだ製品接合成功とは扱わない。P3/復旧の枝を一括移植しない。

1. rootが13pathを通常mergeし、共有registry/transaction/read operationsの3path patchを現在の型・登録へ直列接合する。正式assets/生成module/history/seal/7.7はrootだけが編集し、公式helper・別非作者値確認・実base確定後に扱う。
2. 接合作者は本WTのrepositories/play_export.py、play_export_source_*、authz/play_export_source_read_product.py、exports/play_export_csv.pyと対応専用testsだけを編集し、CSV repositoryの有効行選択を唯一canonical S由来の閉source pageへつなぐ。500keysetと版/health/source集合を同じRR/RO内で検査し、source_event/play_row/generation/D1/D2/slot版を全結合する。全監査と有効集合を分け、取消前のsnapshotを消さない。生成元が欠けるP3等は409のまま。現在roster/0/NULLによる補完や別の野球計算をしない。
3. 同じ候補・owned実PG/実HTTP/実画面で2球→取消→全取消→再入力→reloadのZIP/T5同一性と、越境/不正scope/部分ZIPを拒否する。P3の88列producer、終了再開との結合、正式受理/全CI/通常統合/実機/負荷は別残件を維持する。仮Port/fixtureの88列投入だけを製品成功とはしない。

owned実行は全寿命で共通lock `/home/ymdms/.cache/pitchlog/test-coordination/owned-pg-browser-network.lock` を保持し、共有DSNをunset、実行中sourceを固定する。root共有台帳だけを更新し、作者は専用planへ検査/固定版/未達を追記する。主担当台帳/他WT/公開環境/秘密は非編集。sourceの実装は正式値の受理とは分離し、本人署名/P6blindを記録しない。

接合時の固定点差を確認: source base2dbaはroot c181の祖先ではなく、既CSV delivery/88列producer/単一生成器/IBB対応と関連資産がrootへ未接合だった。通常merge 0f79fcf1ca135cac13514baf24d505b1af00dfe1 は13pathではなく実130path（diffSHA 73d2598a40a9744c44a86e5c608ac060547b33e3d621fb76036b93a12fb5f5ae）で、cache csv-effective-root-connection-20261107/dependency-merge.jsonへ全パスを固定。新13pathの独立確認はこの依存基線全体の採用根拠にはしない。原枝・各成果/レビューを維持し、専用CSV枝だけで依存を照合/試験し、認可・artifact/pin/契約候補を未検証のまま正式統合しない。root現在木の既P0修復・起動0045/27キー・取消/終了再開/認証を失わないことを接合検査する。必要な単一artifactは合成sourceから公式builderで再生成し、旧期待値を出力から作り直さない。P3/復旧をまとめて移植する範囲拡張はせず、CSVの供給不足を閉じるための既依存再利用に限定する。


## ステップ1・現基線への接合（2026-11-07、接合作者記録）

f8ed7f1cを実HEAD/cleanで引受。共有patchのfunction_operations/operation_registryはbefore一致で適用、transactionだけ既基線差を保ったまま真正TenantContext/handle検査直後へ新CSV source1型のdispatcherを接合した。初回preflightは271passed/1failedで、旧43登録のexact期待が既merge依存のwriter1件と今回source reader1件を欠いていた。旧43全順序を保持したまま既writerと今回readerの2固定ID/実token型だけをexact tuple/setへ追記し、subsetや件数だけの比較へ緩めない。対応するtests/test_function_operations_boundary.pyを本stepの接合検査対象へ明示追加する。Ty成功、Ruffのcache生成patch由来import順1箇所はbackend設定で修復する。正式catalog/7.7は未受理のまま。


## ステップ2・有効CSVの唯一S読取（2026-11-07）

CSV repositoryは可視gameを同handleで確認後、ReadPlayExportSourcesの真正同RR/RO source pageを全消費する。従前の独立raw hidden走査を撤去し、page内の最大500 physical IDをtenant/game/accepted source/event/play版へ実SQLで一括結合する。全会員数とreceipt source_countを完全比較し、旧監査行/snapshotは別の同RR集合へ全量保持する。ディスク退避中のphysical indexもDiskRows.index_byを用い、500件の巨大行dictを一括保持しない。

bundleへsource版/identityを保存し、manifestのsource digestへfact_version/revision/S/count/completionと全identityを追加束縛する。同一値のRR開始番号は意味版に混ぜず、同版の再取得を無関係なtransaction snapshotで別版へ変えない。source/physical不一致は共通PlayExportSupplyError系へ閉じて既APIの409を維持する。真正scope/未登録関数等の技術失敗を成功や409へ一律変換せず、既503のまま。P3の88列/sidecar producer未供給の409は維持する。

初回純選択検査は84passed/3failedでDiskRowsにappendが無いことを検出し、単行extendへ修正。SQLite実SQLの1/500/501件・ディスク有無・越境/別event/版/退避/不足・P3非hidden旧行の誤選択なし・版digest束縛を含めて87passed4.26秒、CSV/表示/単一生成器の全対象245passed8.79秒。旧DB資格の成功を模倣する試験ではなく、合成S入力から後段SQLの結合を確認した単位証拠として扱う。真正S/token/CSV製品routeの実PG/画面はstep3で検査する。


## ステップ3の実経路検査開始（2026-11-07）

既owned画面wrapperのセットアップだけへ、同じ候補生成器が返すsource read1関数の実SQL配置を追加する。既真正current起動/全catalog検査・実writer/88列producerの後に候補readを配置し、固定応答や事前88列投入はしない。画面ZIP routeの真正TenantContext→play_export_read_scope→新登録token/同Session関数→S原本/物理行→完成ZIPへ初めて接続する実証が対象。候補SQLの局所配置と正式catalog/7.7受理は区別する。P3未供給は409を維持し、必要な正式差分はrootへ別packetで渡す。


screen1-single-sは **1passed131.12秒/source前後SHA一致/owned cleanup**。同じ候補・実画面・実PGで新規作成/開始→通常2球→1取消/原文重複→ZIP1行→全取消ZIP0行→再入力ZIP1行→reload ZIP1行を完走し、全段階の真正T5 current/source count1/0/1/1・revision3/4/5/5とCSV linksのsource/play/generation/D2/play版を完全照合した。今回は製品CSV routeの真正TenantContextと新登録token/同RR source関数を実際に通過した。隔離候補read SQLの局所配置であり正式提供・P3/終了再開CSV・実機とは区別する。

依存130の旧T5 flush単位8failは旧42dでも同じ8fail/204passを再現。無DBの旧T5単位fixtureに、新88列producerを成功済みと偽装せず「同scope/session/保存receipt/1回の呼出し」を記録する単位境界を置き、後段故障が成功へ変わらない4mode対向を追加する。cache候補は216passed33.37秒で確認後に本WTへ適用。製品hook・producer・認可・保存は変更しない。追加編集対象は既tests/test_stats_native_flush.pyのみ、実88列producerの証拠は上記owned画面で分離する。

同じ候補read関数を必要とする既CSV DB/画面fixtureの4path（test_play_export_v3_product_http/test_play_export_screen_e2e/test_nonpitch_play_export_screen_e2e/test_play_export_substitution_http）へ、既writer候補SQL配置直後のsource read候補SQL配置だけを追随する。初回実証wrapperと同じ実体であり、88列の事前fixture投入や成功応答stubを追加しない。これら全DBケースの成功は未実行のまま保持し、実HTTPの越境/無cookie等の対象を追加確認する。

本WT適用後のT5単位境界は実 `api._assert_scope` を記録前にも再確認し、216passed33.77秒、Ty/Ruff成功。CSV source/collector/単一生成器側の成功245件と合わせても、未実施のDB fixture全件や全MVP成功へは広げない。root c181の既起動0045/27キー、共有UIのsource差分は0を保持する。
