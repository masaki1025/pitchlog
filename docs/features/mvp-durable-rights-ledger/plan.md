---
feature: mvp-durable-rights-ledger
status: active
承認: 済（PO委任によるCodex判断・隔離外部耐久台帳）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-durable-rights-ledger
created: 2026-10-24
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 復元外の記録権台帳adapterと同期耐久性の隔離実装

## 1. 目的・委任・供給境界

実develop `31194a39c9083bbef6c14bde19c24a3e49d09f2e`起点の新単位とする。PO4/10は、既存のbigint D4非再利用・復旧世代・外部fence保証を変えない型/API/保存/失敗の具体化と隔離環境構成を主担当/rootへ委任している。PO3の運用責任者は山田正輝。今回はその範囲で、業務DBの復元範囲外に置くPostgreSQL primary＋同期standbyを技術候補として選び、実予約・epoch・fenceを提供する最初の製品部品を計画する。旧資料の「外部台帳未承認」は過去時点の記録として保持し、今回の限定委任判断で採否を行う。人間本人の新しい署名や運用配置承認を代記しない。

本起案はplan/researchだけ。承認後も指示されたステップだけ実装する。旧`0aaa22e09d7e1a0301d03f7c63d188d9bba76844`のProtocolと旧D4裁定案は参照のみで、旧commitをmerge/cherry-pickしない。正常なinitial履歴修復候補をrootが固定供給した後は、そのProtocolとの接合を隔離状態で検査できる。実develop統合・実RecordingRightsPort全体・HTTP成功は、台帳契約準備や単体実装開始の前提に加えない。供給前は既存Protocolの署名を入力参照してadapterを独立実装し、供給後は実署名との差分を照合する。

到達点は実DBに接続するadapterと、そのDDL/ACL/manifest/故障検証である。RG1の製品open、業務DBの復旧完了遷移、開始・引き継ぎ・全旧世代fenceの完成はこの最初の単位に含めない。後続は非0件を含む全世代fence・回収/退避・新D4(D3=0)と解除の同一確定へ進む。対象0件の解除だけをMVP完成へ読み替えない。

## 2. 守る保証と実装する閉じた契約

| 項目 | 限定する製品契約 |
| --- | --- |
| 保存境界 | 業務DBと台帳は別cluster/system identifier・別data directory・別backup/restore対象。単なる同cluster内別databaseを独立保全と扱わない。起動時に接続先identityと期待manifestを照合し、同一cluster/誤接続/不明を拒否する |
| D4予約 | 正のbigint。単一高水位と予約履歴をtransactionで直列化し、範囲上限を越えない。予約成功応答前に同期保全を完了する。業務rollback・取消・応答喪失後も高水位を戻さない。D4値順と試合内issuance_orderは別 |
| 冪等性と消費 | attempt IDにtenant/game/start requestを不可分に束縛。exact再照会だけ同予約を返す。別owner・別要求への再束縛は拒否。claimは業務使用前に一度だけ耐久消費し、業務失敗でも未使用へ戻さない。応答不明時は同attemptの耐久結果を照合し、新attemptを自動発行しない。claim結果不明・既消費なら新規業務INSERTを許可しない。既存業務成功の再掲は後続の同一開始照合が担当 |
| 同期耐久性 | PostgreSQL17.11 primary＋指定standby1台、fsync/full_page_writesを有効化し、指定peerをsynchronous_standby_namesへ固定。予約/claim/epoch更新はsynchronous_commit=on。設定値だけを成功証明にせず、実peer identity・sync状態・対象commit WALのstandby flushと再読、およびprimary停止後の保全を故障試験で照合する。peer不達時に非同期へ自動降格しない |
| 復旧epoch | 復元外の正のbigint復旧世代を耐久記録し、単調前進だけ許可する。応答不明・旧epoch・枯渇・接続再確立で照合不能なら停止。業務DB側epochとの一致判定に使う値を提供するが、業務DBの現在値だけから外部epochを再作成しない |
| 外部fence | 実epoch行の共有ロックを借用contextで保持し、業務commit終了まで保持できるAPIとする。更新側は排他ロック。借用中の接続喪失/transaction終了/identity変化を検出して失敗閉鎖する。業務commitをadapterが代行したとは扱わない。後続接合ではcommit失敗/結果不明も含めて保持期間を検査する |
| 昇格・両系喪失 | 成功済み予約を含む指定standby以外を昇格しない。旧primaryの実停止/隔離を確認できない限り新primaryによる発行を拒否。local試験controllerは自分が所有する旧primary停止を実確認してから昇格する。外部から渡す単純boolや任意JSONをfence証明として採用しない。最新成功高水位を証明できない両系喪失では古いbackupからの再開を拒否 |
| 権限と非漏洩 | アプリの業務DSNを再利用しない。台帳用NOLOGIN ownerと限定実行role、PUBLIC剥奪・固定search_path・exact制限関数で予約/claim/epoch読取/fenceを限定。epoch更新は復旧制御roleだけ。owner tuple以外の予約閲覧/消費、履歴改変、直接表DML、任意SQLを拒否。資格/DSN/V12をログへ出さない |

業務DBを過去backupへ戻しても台帳の成功済み発行集合は保持する。latest高水位だけでなく予約/claimとepochの対応を照合する。接続待ち/statement/lock timeoutは有限とし、失敗は型付きで返し、成功へ縮退させない。同期commit応答喪失は「未使用」と断定しない。

## 3. 編集予定scopeとcore先行登録

現在の所有は本featureのplan/researchだけ。承認後の候補scopeは以下とし、実装前に追加pathが必要なら追補・独立確認へ返す。

| paths | 役割 |
| --- | --- |
| `scripts/core_guard.py`、`tests/test_core_guard.py` | 後述の領域別限定pattern追加層宣言・登録前/後の段階試験だけ。全判定関数/共変更拒否/委任規則不変 |
| `.claude/core-areas.json` | 宣言より後の別commitで領域別の完全追加層だけを末尾へ追加。全既存paths/順序/guard_pathsを保持 |
| `backend/src/pitchlog/durable_rights_ledger/*` | 新packageの型、接続/transaction、adapter、固定DDL SQL、機械可読manifest。業務DBへ適用しない外部台帳専用schema。manifestはschema/API/role/設定/identity・保全境界の期待形を宣言し、DSN/資格実値を含めない |
| `backend/tests/test_durable_rights_ledger_contract.py` | manifest/DDL/API/署名/exact許可と拒否、source固定、Protocol接合の構造・単体試験 |
| `backend/tests/db/test_durable_rights_ledger.py`、`backend/tests/db/durable_rights_ledger_support.py` | 所有するprimary/standby/業務DBの隔離構成、実制限関数・role・複製・復元・故障試験とcleanup。共通conftestを変えない |
| `contracts/tenant_boundary/base-allowlist.json`、`tests/fixtures/tenant_boundary/positive/pitchlog/durable_rights_ledger/*` | 外部接続/固定関数実行を行うexact関数・正確signature・必要APIだけの登録と正例。module全体/任意SQL許可はしない |
| `contracts/tenant_boundary/db-api-inventory.json`、`scripts/check_tenant_boundary_bypass.py` | 下記限定追補承認後にだけ、`psycopg.Connection.cancel_safe`のAPI ID1件と保守member `cancel_safe`を認識する検出対応。既存全API/拒否条件を保持。全scopeや任意memberを許可しない |
| `tests/test_check_tenant_boundary_bypass.py` | 上記exact登録の正負例。業務DBへの誤接続、未登録symbol/署名/動的SQLを許す例外を作らない |
| tenant-boundary既存9資産・既存生成Python3・`tests/fixtures/frozen-archive-cases/manifest.json`・必要history-snapshots | source/登録の実差分が影響するものだけ既存導出/7.7で追随。全9 before/after・既存8 external値・履歴prefix/corpusを照合し、不変資産を無用に更新しない。生成3はruntime/repository/tenant-contextの既存module |
| `docs/design/data-model.md`、`docs/README.md` | 後述の外部永続資産・role/復元境界に関する最小正本候補と索引。旧履歴/他候補を変更しない |
| `docs/features/mvp-delegated-core-review/policy.json` | 製品sourceを含むDraftで実番号を取得した後、本実PR番号と`feature/mvp-durable-rights-ledger`の1組だけをtargetsへ追加。旧targets/authority/失効/判定を保持し、データ差分も非作者最終レビュー対象 |
| 本featureのplan/research | 固定入力/差分/検証/未達/受渡し |

`backend/tests/db/*`は既存3領域で、正例fixtureはtenant-isolationだけで捕捉される。新製品packageと新contract試験は3領域とも包含されない。追加層の順序はsync-protocol/recording-rightsが`backend/src/pitchlog/durable_rights_ledger/*`、`backend/tests/test_durable_rights_ledger_contract.py`、`tests/fixtures/tenant_boundary/positive/pitchlog/durable_rights_ledger/*`の3件、tenant-isolationが前2件だけとする。このexact層を先行宣言→別JSON登録する。初回は両実行資産不在でも緑、実在後は全登録/実捕捉必須、部分登録/対象外追加/共変更/既存削除を拒否する。実baseのO5/startup等を全保持し、origin先端との混同で登録を削らない。正常initial候補を取り込む場合も、その追加層とpathsを保持した実merge-baseから本追加層だけを回転させる。

既存psycopgを使用し、新依存/業務migration/CI/共有DB設定は変更しない。外部SQLにも既存tenant-bypass検査を適用する。既存API inventoryで表現可能なexact許可を使い、検査器source/新API IDが必要と判明すれば実装を先行せず、その必要差分だけ計画へ戻す。skip/ignore/ファイル丸ごと除外で緑にしない。外部role等は専用manifestで全数検査し、既存の業務認可56関数/role集合へ外部資産を混入させない。

## 4. 影響する正本・ゲート

規範のD4 bigint非再利用・復旧epoch・RG1/B7/B10・D5未消費・全旧世代fence・解除と新D4不可分は変更しない。型をUUID/nonceへ変更したり、台帳障害時の非同期降格/保証緩和を採用しない。

data-modelの新しい外部永続資産・所有role・復元境界は構造的変更なので、最終ステップで同一PR内に最小改訂候補を作り、ハーネス7.6-3後段の7.3ゲートへ出す。旧版/既存歴史を保持し、版は実base上で再採番する。計画承認だけで正本をapprovedにしない。既存規範を変えない実装追随は7.6-3前段で扱い、sync-protocol/要件/ADR/opsの追加改訂は本単位では行わない。意味変更が必要なら具体差分を分離して主担当へ戻す。

正式凍結値は実統合時のbase/headから完全射影を固定してrootが唯一writerとして直列受理する。candidateの局所試験成功と履歴未受理による赤を分け、旧173受理や旧成功件数を流用しない。正式snapshot/履歴を受理前に書かない。正本確定と7.7は別ゲート、本人署名/P6/逐行確認を機械証跡で代替しない。

## 5. 実装ステップとDoD

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 領域別追加層と段階試験を宣言 | guard全判定関数AST/JSON byte不変、旧全paths保持、新実行資産不在。登録前/別登録/将来実在・各単独変更捕捉と共変更拒否が緑 |
| 2 | core JSONだけに先行宣言済み領域別層を別commitで登録 | 宣言/試験/製品変更0、sync/record各3件・tenant2件のexact末尾追記だけ。旧登録/guard_paths不変、将来製品/contract試験各単独変更が捕捉される |
| 3 | 外部台帳adapter・schema/ACL/manifest・局所検査候補を実装 | 予約/再照会/claim/epoch/fenceの実制限関数・最小roleで成功と拒否を検証。実同期primary/standbyの耐久保全、応答不明/同時実行/誤接続/権限逸脱を検証。正常initial供給後に実Protocol署名を照合。正式履歴未受理赤と正本候補未確定を記録して停止 |
| 4 | 実故障/復元検証・正本最小確定・正式凍結受理・最終独立レビュー | 下記故障行列を完走。最終head/source/diff/manifest/対象環境と全before/afterを固定し、7.3/7.7の各必要判断後だけ反映。実新PR/本branch1組だけのpolicy対象追加を含めて、正式checker/履歴/archive/生成/型/品質とPR合成mergeのcore検査を緑にし、非作者がpolicyデータを含む全差分を確認。運用未実施を保持 |

各ステップは`(ステップ k/4)`を1個含む別commit。指示された1件で停止する。新PR番号は製品sourceを含む候補から取得し、番号だけの文書PRを増やさない。push/PR作成/統合は主担当の別指示で扱う。

完成は隔離環境で動く本物の台帳adapterまで。RG1通常成功は後続の実epoch照合・正式制限関数・完了遷移と接合して初めて認定する。既存D4対象0件でも復元DBに行がないだけでは安全証明にならず、復元外の発行/epochと回収対象manifestによる証明が必要。非0件の全旧世代fence、新D4発行と解除の不可分性、管理者の回収/退避閲覧・書出しは親新7/8の未完条件として保持する。

## 6. 検証と未実施境界

- 単体: manifestの全field/DDL/role/function exact集合、owner tupleの束縛、bigint上下限、旧epoch/不正値、例外の資格非漏洩、借用fenceの寿命。常に成功する証明fakeを製品提供と扱わない。
- 実DB: 並列予約一意、同attempt再照会/他owner拒否、二重claim拒否、業務rollback後の不再利用、epoch共有/排他競合、接続断とtimeout、直接表DML/他role/任意SQL拒否。fenceは実ロック保持と業務commit前後の競合を検査する。
- 同期故障: standby停止/遅延・設定不一致・同期成功応答直後のprimary停止・応答喪失・旧primary未停止での昇格拒否・最新standbyだけの昇格・両保全先喪失/古いbackupの発行拒否。成功応答したD4累積集合を独立に保持し、業務DBだけの連続2回復元とその後の発行で過去集合との交差0を検査する。予約/claim/epochそれぞれ同期保全を確認する。
- 隔離構成: 既存disposable PostgreSQL fixture/cleanupの所有方式を再利用し、primary/standby/業務DBに専用tempdir・ランダムloopback portを与える。継承DSN/PITCHLOG_*を使わず既存.env/秘密を読まない。試験専用一時資格は隔離fixture内だけ。既存共有container/volumeへ触れず、生成した自分の資源だけをfinallyで停止/整理する。全故障試験は非並列、他fullbackend/browser実行と調整する。実同期複製が未構成ならskipで合格にしない。
- backendは対象`test_durable_rights_ledger_contract.py`と`tests/db/test_durable_rights_ledger.py`、Ruff/ty。rootはcore_guard/tenant-bypass関連、docs-status/局所plan同期、差分、必要な生成/凍結/archive契約を確認。最終の既存CI必須対象は省略しない。
- 運用配置/共有DB適用/有料資源/新運用秘密発行・実機・本番障害耐久性は未実施。local二台は物理的な別故障領域を提供した証明ではない。設定・adapter・故障時停止の実検証と、運用設備の提供を分ける。運用責任者は既指定の山田正輝で、未指名扱いに戻さない。

本起案後は固定SHAを返して停止し、非作者の独立レビューとroot委任判断を待つ。作者は`/root/independent_review`であり、本候補の独立レビュアーを兼ねない。

### 第1回計画レビューの採否

非作者/root/resolver_ledger_plan_reviewはplan7fdcbb2c/research7aca2f90に対してP0=0/P1=1/P2=0。P1（新PR/branchのpolicy登録scope欠落）をrootが全採用し、第3節に実番号取得後のtargets1組だけと第5節step4に非作者最終確認を追加した。旧target/根拠/拒否条件・人間確認欄は変更しない。元作者independent_reviewとrootは候補作成側であり非作者を兼ねない。前後値受理/運用配置は未成立のまま、限定反映差分の独立確認待ち。

正本順序については、既存7.6は同一PRで構造改訂を7.3へ通す規則であり、未受理候補の実装前に一律通過する要求とは記録しない。第4節/step3〜4の規範・採用内容の限定承認と正式化/7.7/提供ゲートの分離を維持する。実Port/HTTPを新たな契約着手前条件へ追加しない。

### 限定計画のPO委任承認

2026-10-23T17:35:41.606496+00:00、Codex主担当/root。PO4/5/7/8/10に基づきplan dab7fb925a5072a686bde58bcf9327fa8a6c3d5cd345580cbe5da0ce0a7aceb6 / research9a259cd2c48b11dfb505aeda1cdded760854f12a25b576716ec45720394fb9c8を承認。非作者/root/resolver_ledger_plan_reviewの全文初回P1=1を全採用し、限定反映差分第2回0/0/0を受領。指摘反映1周・レビュー実行2回を保持する。厳密D4/epoch/fence保証を維持する技術具体化と許可済み隔離実装・検証の採用判断であり、運用設備配置/共有DB/費用/秘密新発行を承認しない。指定された1ステップだけ実施し、構造正本7.3/完全値7.7/最終非作者確認・CI・後続RG1実遷移を個別に満たす。山田正輝本人の実値確認/署名を代記しない。

### 同期待機取消APIの限定追補（追加範囲をPO委任承認済み）

step3調査で、同期COMMITの待機取消がlocal commit後のWARNINGとなり得ることをPostgreSQL17の一次sourceで確認した。statement_timeoutだけをrollbackや非消費の証明にしない。有限待機にはpsycopgの明示取消口を使い、期限到来/取消発行後はCOMMITの見かけ上の戻りにかかわらずoutcome-unconfirmedとする。予約/claimが未実施/rollback済みと断定せず、同じattemptの実耐久状態を後で照合する。新attemptの自動発行へ逃げない。

追加を許可する候補は`PSYCOPG_CONNECTION_CANCEL_SAFE`という1ID（symbol=`psycopg.Connection.cancel_safe`）、inventoryの保守member `cancel_safe`1件、および既存checkerが接続種別/alias・保守名を正しく対応させる必要最小の検出差分である。未登録の同methodを検出対象に入れ、既存全API/exact-setを保持する。唯一の実行許可は本package内の固定private取消helper・正確signature・正例へ与え、当該helperの許可APIはこの1IDだけとする。製品helper名/signatureは実adapter設計と固定してresearchへ記録する。別symbol/module/署名/alias悪用、同名memberや他の接続操作を許可しない。追加の汎用除外や未知APIの素通りはしない。

`cancel_safe(timeout=...)`の有限性にはlibpq17以降が必要で、pin3.3.4の実ソースと実client capabilityを検査する。capability不成立/不明は接続・予約前に拒否し、legacy `cancel()`へのfallbackを製品で使わない。取消処理自体のtimeout/失敗/競合も不確定で閉じ、当該接続を後続要求へ再利用しない。タイマ/処理完了の競合で後続の別要求を取り消す経路を作らない。実clientはroot確認時libpq180000/has_cancel_safe=Trueだが、それを運用設備の証拠に流用しない。

既存`tests/test_check_tenant_boundary_bypass.py`で新APIの検出・正例1helper・全拒否変異・旧登録保持を検証する。backend契約/DB故障試験は同期待機停止→有限終了→未確定/旧番号再使用なしを実primary/standbyで検証する。inventoryは9資産の一つ、checkerは既存8外部対象の一つなので、影響する全射影/identifier/corpusと生成を実状態から再導出し、step4でrootの完全7.7を要する。既存受理行/before/snapshotを変えず、新実PR単一受理へ対応する。

根拠: [psycopg公式Connection.cancel_safe](https://www.psycopg.org/psycopg3/docs/api/connections.html#psycopg.Connection.cancel_safe)、[PostgreSQL17同期待機の一次source](https://github.com/postgres/postgres/blob/REL_17_STABLE/src/backend/replication/syncrep.c)、実pin3.3.4のConnection.cancel_safe本体とlibpq capabilityのroot読取。既承認step3のDDL/manifest/Protocol/support等は継続し、追加したinventory/checker/取消実行許可だけは非作者限定レビューとrootのPO委任判断後に実装する。旧計画レビュー2回・先行core限定review P1採用と中間/失敗を保持し、新追補で履歴をリセットしない。

2026-10-23T18:11:30.850638+00:00、Codex主担当/rootはPO4/5/7/8/10に基づき、追加plan SHA25620b8dc2e7e9783f3eea03edde21cfc3315ebb866f7552b1a2a274d6c05131948を承認。非作者/root/resolver_ledger_plan_reviewの追加scope限定第1回0/0/0を受領し、PG17一次source・実psycopg3.3.4とlibpq capabilityの独立確認を根拠とする。1API ID/1member検出とexact私有helper許可・既存正負例だけを追加し、契約の全既存拒否・D4/epoch保証・元4ステップを保持する。先行plan実行2回/1反映周、先行coreコードレビュー初回P1採用後の第2回確認と全中間/失敗を別系列として保持。人間本人の署名/実値逐行確認を代記しない。実装/実同期故障の成功、正式7.7/正本7.3/最終非作者確認はまだ成立していない。


### 実Protocol実装の条件2限定登録追補（追加範囲をPO委任承認済み）

承認済みstep3の実adapterは正常initialの`DurableGenerationSource`/`ReservedGeneration`/`RecoveryEpochFence`を直接再利用する。既存条件2検査がこのimport・継承・generation実装をTB002として13所見検出したため、Protocolをコピー/別名化して回避せず、既存初期付与1ファイル47所見とは独立した限定登録を追加する。参照候補はadapter SHA256 `faa1ab04e2282a8654bedffd7053cb9062d9257d6d6d58488863d6b850bd1e90`、13実identityの保全は `/home/ymdms/.cache/pitchlog/durable-ledger-tb002-faa1/findings.json`。期限競合等の承認済み不具合修正で行番号/sourceが動けば、実sourceと全13件を再実測して記録し、旧値を一致と扱わない。

追加編集scopeは既存の`base-allowlist.json`/`scripts/check_tenant_boundary_bypass.py`/`tests/test_check_tenant_boundary_bypass.py`に加え、`tests/test_census_baseline_check.py`と`tests/fixtures/tenant_boundary/census-scoped-digests.json`に限る。唯一の新source対象は`backend/src/pitchlog/durable_rights_ledger/adapter.py`であり、path・最終source SHA256・正の行番号と完全symbolの13件exact-setすべてが一致するTB002だけを許可する。初期付与47件とsource SHA/全既存拒否をそのまま保持する。module一括/接頭辞/owner追加/未知path・未知source・未知symbolの許可はしない。既存条件2ルール・検出候補・別条件/API検査は変更しない。

構造は初期付与登録を互換保持した単一のadapter専用登録とする。missing/余剰/重複・13未満/超過・不正SHA・別pathを契約読取で拒否し、source SHA不一致・行/symbol不一致は免除しない。実13件は免除なし検査で全件再導出し、独立確認と完全7.7受理の対象にする。登録を書いた文字列自体を承認証拠とは扱わない。

censusでは新adapterの実checker identityと独立AST候補の粒度を照合し、必要な限定集合とdigestだけを新しい明示キーで固定する。旧47件に対応する既存43/18集合・digestを更新/削除しない。元センサスanchorと旧差分の全拒否を維持し、新集合の欠落/余剰・digest改変・旧/新path間の移し替え・追加identity混入を拒否する回帰を追加する。件数のみの比較や無条件除外はしない。sourceを変えた場合は新集合を再導出する。

これは同一の採用済みProtocolを単一実装するための検査上の限定具体化で、D4/epoch/fence/RG1/耐久性や意味規範の変更ではない。作業中は未受理を記録し、実9射影/外部8blob/履歴・corpusの正式化をroot所有step4で実施する。全最終差分は非作者レビュー対象とする。旧計画/取消追補/core系列のレビュー回数・指摘履歴・冷起動authority未提供を保持する。

2026-10-23T18:47:39.799141+00:00、Codex主担当/rootはPO4/5/7/8/10と2026-10-24の優先指示に基づき、追補対象plan cb9ed1123abe711d879e93a5ce4a91603eee5b1a8b1e03a3969884dd9a8c83bf（HEAD d59be7f4）を承認する。非作者/root/rights_replacement_reviewの限定追加第1回0/0/0、source53bdb9d54b9fa5ab0ece6787ab4824dfc02e9afbeea2a8d14ad132779ca2758dの免除なし13identity独立再検出一致を確認した。旧faa1との差は既承認期限是正による行移動で13symbol多重集合は不変。今回の許可は登録機構・censusの限定具体化であり、旧47所見/43・18集合/拒否を保持する。正式値7.7・製品全最終差分/耐久性レビュー・cold attach・RG1成功・MVP完成は別の未完ゲートとし、本人確認/署名を代記しない。旧計画2回/反映1周と取消追補/先行coreのレビュー系列はリセットしない。

### 正常再起動authorityと復元外witnessの技術追補（PO委任承認済み）

5a321b6aは正常pair候補の保存点である。「cold attach/business identity未提供」を外部回答待ちにせず、以下を本packageが実装する製品依存とする。今回は本plan/researchだけを編集し、新sourceは独立追加レビューとrootの個別実装委任まで変更しない。元の4ステップ表/全DoD、旧全レビュー/失敗系列と正式7.3/7.7未達は維持する。

**技術選択。** ①専用の保護されたlocal journal、②別volumeのSQLite WAL、③第3PostgreSQLを比較し、MVP候補は①とする。既存sourceには起動をまたぐ耐久witness/単一writer機構は無い。`runtime_contract_generator._atomic_write`の短書込処理とfile fsyncは参考にするが、置換方式/親dir fsync不足のままwitnessへ転用しない。②は新DB API面とWAL管理を増やし、③も別の最新性保全を必要とするため、今回の最小単位に選ばない。単なるowner権限/呼出者のexpected集合/hash鎖だけを巻戻し防止としない。

**保存/authority。** 業務DB・台帳primary/standbyのdata/backup/VM復元に含めない専用volumeへ、root管理のenrollment descriptor、固定journal inode、lock fileを置く。Linuxの実`FS_APPEND_FL`でjournalの上書き/truncateと親dirのunlink/renameを禁じ、authority workerは別UIDで動き、そのflag解除権限`CAP_LINUX_IMMUTABLE`を持たない。業務app UIDにはdir/journal/台帳control資格を与えない。候補modeはdir0750(root:authority)、journal0600(authority、append-only)、descriptor0640(root:authority、immutable)、lock0600(authority)とし、workerに親dirの書込権限を与えない。固定rootから`O_NOFOLLOW`/dirfdで開き、owner/mode・regular file・link count・device/inode・mount識別・実append属性を検査する。file/dir fsyncや必要な保護を提供しないfilesystemは起動拒否。flag設定は隔離fixture/別の初回配置主体だけが所有資源へ行い、製品workerが権限を昇格したり既存host設定を変更しない。

通常`open`は既存enrollmentを要求し、欠落時の自動初期化/旧backupからのjournal再生成を持たない。初回enrollは通常APIと分離した配置操作で、新設authorityの保護領域、実識別済みの別business cluster、空の台帳（highwater0/epoch1/予約0件）を実観測して一度だけ行い、root所有descriptorと親dirを耐久化する。既存導入の復旧を「新設」へ読み替える操作は提供しない。OS/ストレージ管理主体による保護領域の巻戻しまでhash鎖で検知できるとは主張しない。保護volumeはDB/host image復元の対象外に置き、journalの連続性または全設備喪失後のenrollmentを証明できなければ発行停止のままとする。未知の媒体/旧witness imageへ無人で再enrollして再開しない。新署名鍵/運用秘密は生成しない。journalにDSN/資格/V12/Cookieを保存しない。

**単一writerと書込順序。** `flock(LOCK_EX|LOCK_NB)`を期限付き取得し、同一inode上で全mutationとattachを直列化する。journalはversion/length/sequence/previous digest/checksumを持つbounded frameを完全書込してfile fsync、初回enrollment作成は親dir fsyncも完了する。hashは欠損/破損の検出用で、署名/権限証明として使わない。失敗/ENOSPC/EIO/短書込/未知versionは成功にしない。未完末尾を勝手にtruncateせず停止する。この候補は固定journal1本を追記・保持し、自動rotation/truncate/交換を行わない。容量不足は停止し、起動時はbounded memoryで連鎖を走査する。derived index/cacheは再生成可能でauthorityの正本ではない。

予約/claim/epochの正のbigint算出は既存SQL側に一元化する。authorityは実DB transactionが返したprovisional行とowner/前後stateを`INTENT`としてfsyncしてからCOMMITを送る。COMMIT/指定standby flush・replay/実再読が成功した後に`CONFIRMED`をfsyncし、その後だけ成功応答する。INTENT前の失敗はCOMMITを送らない。INTENT後は取消/応答喪失/RESULT fsync失敗を含め未確定であり、「未使用/rollback済み」へ変えない。

**再起動/復元照合。** authority自身が保護journalから成功集合と未確定INTENTを再構成し、実primary/standbyのowner-bound予約/claim/epoch/highwaterを固定cursorのDBページで照合する。全件をメモリへ読み込まず、DBのgeneration一意索引を使う。正常process/DB再起動で実起動identityが変わっても、同じenrollment、完全journal、実同期peer、全確定集合の一致と未確定処理の完了を確認してから、新旧system/timeline/postmaster identityを`ATTACH`へfsyncして借用を発行する。`expected set`を呼出者から受け取らない。

未確定予約/claimは実両系の同一owner状態で確定できれば同じ結果を記録し、確定できなければ当該D4/attemptを使用禁止のquarantineとして耐久保持する。未使用と断定せず、新attemptや同D4の業務INSERTを自動許可しない。DBがjournalより古ければ、authorityだけの固定制御関数でjournal由来の各行をCAS照合して前進再構成する。quarantine列/固定reconcile操作で不明D4も高水位以下に留め、減算/履歴削除/別ownerへの再束縛は拒否する。witnessは別のD4 allocatorを作らない。epochの不明結果はRG1 close確定→外部epoch更新の順を保持し、任意の低い値への復元や推測によるopenをしない。証明不能な旧/未知行、分岐したjournal、指定外peer/旧primary停止未確認は停止する。

**借用と製品入口。** 別UIDのauthorityをpackage内の実Unix socket serviceとして実装し、root所有socket/設定と両方向`SO_PEERCRED`で主体を検査する。要求は閉じたoperationとowner UUID/接続に束縛されたleaseだけ。bool/任意JSON/期待集合/DSNを証明として受け取らない。`DurableLedger`は既存3 Protocolを直接再利用する入口のまま、正常public構築をこの実service接合へ移し、fresh pairを再度newして復旧検査を迂回する経路を閉じる。低層PG操作とdomain journal照合は既存adapter内、汎用frame/排他は`witness.py`、socket transportは`authority.py`に分け、ドメイン型/計算をコピーしない。

外部fenceは実共有epoch transactionをauthorityが保持し、同一接続のleaseを業務commit終了まで借用する。lease開始/終了もjournalへ残す。authority停止で失われたleaseを再起動後もheldと偽らず、未終端leaseがあれば既存RG1 close/旧writer fenceを実行・確認する後続接合まで発行を停止する。この追補で分散commit/RG1全実装を完了扱いしない。正常に全leaseが終了した再起動、および業務writerを持たないmutationのcrash/reconcileを実提供範囲として先に実装する。

**業務identity専用subject。** `business_identity.sql`で専用schema `pitchlog_ledger_observer`、NOLOGIN/NOBYPASSRLSの`pitchlog_ledger_identity_owner`、NOINHERIT/NOBYPASSRLSの限定LOGIN `pitchlog_ledger_identity_probe`、引数なし`pitchlog_ledger_observer.identity()`だけを設置する。builtin `pg_control_system()`への**追加の明示GRANT**はownerだけとし、既定PUBLIC経由の実効EXECUTEが存在することを実ACLで記録する。builtinの既存ACLは変更しない。probeだけに専用schema USAGE/専用`identity()`のEXECUTEを追加する。関数は固定`search_path=pg_catalog,pg_temp`のSECURITY DEFINERで、cluster system ID/database/実起動identity/version/recoveryだけを返す。製品表/tenant/authn関数への追加権限・membershipは0。PUBLICと既存appから剥奪する対象は新設専用schema/`identity()`であり、builtinのPUBLIC権限まで剥奪したとは扱わない。appへのpg_control_system権限拡大なし。実session_user/current_userが専用probeであることを接続外側で照合する。

MVPの実観測providerはauthority UIDに束縛したPostgreSQL Unix socket peer認証とし、隔離fixtureで実role/OS主体/拒否を検査する。新password/署名鍵/TLS証明書は発行せず、運用主体/共有DBへ適用しない。remote配置がこの既存信頼接続を提供しない場合は接続失敗として閉じる。observerは専用manifestで全数検査し、既存製品56関数集合へ黙って混入させない。既存product catalogの対象schema/role/関数は宣言集合で絞るため、独立schema/無権限probeで既存S3の判定/ACL集合を維持できることも実fixtureで検証する。実閉集合との衝突が出た時だけ具体的対象をrootへ返し、判定を弱めない。

**必要scopeと最初のコード単位。** 既存4ステップのstep3内で、追加レビュー後にrootが指示する小単位だけを実装する。

| 小単位 | exact編集候補/DoD |
| --- | --- |
| 最初: 保護journal | 新package内`witness.py`、既存`manifest.json`と`backend/tests/test_durable_rights_ledger_contract.py`、本researchだけ。実file/dir fsync・実process間lock・frame/short write/欠損/権限/未知format拒否を提供。隔離所有volumeで実append保護の成立と解除権限なしを検証し、unsupportedをskip/常時成功stubで提供済みにしない。DB/source53b/正式資産はまだ変更しない |
| 次: 実authority接合 | package内`adapter.py`/`authority.py`/`schema.sql`/`business_identity.sql`/`manifest.json`/`__init__.py`、既存contract/DB試験・DBsupport、既存base allowlist/正例/関連checker/census、research。実journal→PG→peer→journalのACK順、fixed reconcile/quarantine、実subject/IPC、正常再起動と古い両DB復元拒否/前進を接続 |
| 最終: 既存step4 | clean/crash再起動、各write/fsync/commit/peer/ACK境界のkill、2回業務復元、両台帳古い復元・witness破損/喪失/lock競合・未知peer・未終端leaseの拒否を実証。data-model/READMEへwitness/role/復元・authority境界を最小追随し、7.3/7.7/実PR/policy/全最終独立レビュー/CIを既存step4のまま満たす |

package wildcard/既存contract試験/DB試験は先行core登録済みで追加core pathは不要。file/IPC syscallはDB APIではなく、新DB API IDを予定しない。固定SELECT/制御SQL/配置だけを既存PSYCOPG APIのexact私有helper/signatureへ必要最小登録し、汎用SQL/新member包括許可はしない。domain名の条件2所見はadapter単一sourceで再実測し、更新SHA/全identityと独立AST/censusを個別確認する。旧initial47/43・18、旧53b候補と新全検出を保持し、予想件数で免除を増やさない。witness/transportに実際の追加所見や新APIが必要ならその具体差分だけ再提示する。9/8の正式値/履歴/snapshot/policyのwriterはroot、機械候補と正式受理を分ける。

一次根拠: [fileとdirectoryのfsync](https://man7.org/linux/man-pages/man2/fsync.2.html)、[実append-only属性と解除権限](https://man7.org/linux/man-pages/man2/FS_IOC_SETFLAGS.2const.html)、[Pythonのflock](https://docs.python.org/3.12/library/fcntl.html)、[PostgreSQLのcontrol情報/権限](https://www.postgresql.org/docs/17/functions-info.html)。この追補案の起案は新たな運用配置/本人署名/全設備喪失後の再発行承認ではない。


2026-10-23T19:26:15.303101+00:00、Codex主担当/rootはPO4/5/7/8/10と2026-10-24の縦断優先指示に基づき、対象0fe39b38、plan475bfc4fe51860ecaefc0db09a8408ec7cd237cf5aff5e980174abbc00d1de93/research65ccc5213790537b4d43105de63c3c914bcedabf08cea28e40e96399527ab353を限定承認。非作者rights_replacement_reviewの追加計画第1回0/0/0、独立UID/実append保護/親dir fsync/intent→PG→confirmed→ACK/peer主体・最小observerを根拠として確認した。これは既採用耐久性/非再利用/復旧世代保証を実装する技術選択であり、運用配置/新秘密・署名鍵/共有DB適用/全設備喪失後再発行を承認しない。旧4ステップ/全DoD・旧全レビュー/失敗と53b候補を保持し、最初は表の保護journal＋既存manifest/contract試験/researchだけを個別指示する。実保護・失敗閉鎖の実測をskipやstubへ代替せず、後続authority/全fault/正式7.3/7.7/最終コードレビューを完了へ拡張しない。人間本人の個別確認・署名・逐行確認を代記しない。


2026-10-23T20:46:20.091291+00:00、Codex主担当/rootはPO4/5/8/10の通常実装具体化として、業務identity専用subjectの上記対象を限定明確化する。実PG17.11でbuiltin pg_control_system()の既定PUBLIC EXECUTEが存在し、旧probe実効拒否期待1件が失敗した事実を保持する。非作者rights_replacement_reviewの限定技術確認では、builtin ACLを既存role全体へ変更することはobserver信頼性に不要で、追加明示GRANTをownerへ限定し、専用schema/identity()のPUBLIC/app拒否を保つ明確化は既存保証を維持すると判定。実効PUBLICとdirect grantを分け、probeの製品tenant表/authn/台帳DML拒否・membership0・peer/session/current主体の実証を必要とする。この判断は既存全否定試験の成功/最終sourceレビューを代替しない。旧失敗/本文/審査系列を保持し、人間の署名・確認を代記しない。

### fresh activationの最小追補（独立限定確認・PO委任前）

既存step3内の次小単位とし、4ステップ表/全DoDとstep4の正式化ゲートは増減しない。基線は`b9d5c457159a823d08f2691e3e6e16d3c63dfba4`。同版の全source独立レビュー、旧53b/exact13と候補18の採否、今回の限定計画確認は別系列で、旧全レビュー/失敗を保持する。今回はplan/researchだけを固定し、個別委任前にsourceを編集しない。

**公開する内部境界。** `DurableLedger(endpoint: Path).fresh_activation()`は`Iterator[tuple[FreshActivationAttestation, RecoveryEpochFence]]`のcontextを返す。新しい不変metadata DTOは`authority_id: UUID`、`activation_ordinal: int`、`business_system_id: str`、`database: str`、`postmaster_started_at: str`、`pair_epoch: int`、`highwater: int`、`reservation_count: int`を持つ。activation識別は保護authority_id＋実開始frame ordinalであり、新秘密/署名鍵ではない。D4型/allocator/既存RecoveryEpochFenceをコピーしない。DTOはexact型/閉field集合を検証し、bool/float/配列/未知fieldの強制変換を拒否する。型/識別値だけを証拠にせず、同じ実認証済みUnix channel上の生きたfenceと一緒にだけ利用する。

**database束縛の最小是正。** b9 descriptorはauthority/filesystem/inodeを保護しDB情報を持たない。root configはimmutableなbusiness_dsnを保持するが、そのdatabaseをgenesisへ固定していない。observerはdatabaseを実読しworker寿命中は全identityを再照合する一方、b9のENROLLED/ATTACHEDにはsystem_id/started_atだけが入り、normal再起動で当初databaseを照合できない。新enrollのbusiness genesis/attachmentに実観測databaseを加え、freshとnormal admissionの双方でsystem/database/postmasterを一致させる。locatorとしてのDSNや現在値だけから旧genesisの欠落を補わない。旧database欠落genesisは起動拒否とし、自動upgrade/再enroll/DB行0による昇格を提供しない。汎用descriptor/witness frameと既存observer SQLは変更不要。この欠落はb9レビューの具体残件として返し、fresh追加だけで旧通常保証が既に成立していたとは扱わない。

**開始と保持。** 閉RPCは引数無し`fresh_activation_open`と既存同channelのcheck/closeだけを用い、callerのexpected set/ID/bool/DSNを入力証明にしない。既存の許可済みclient UID/GIDと両方向SO_PEERCREDの認証境界を維持し、同UID内のPython呼出者識別や新ユーザー権限を主張しない。RG1更新権限を持つ実consumerはroot別単位で扱い、このmethodをHTTPへ登録しない。daemon自身が保護genesis/current business identity、実同期pairのE1/H0/予約0、全journalの過去INTENT・不明・過去activation0、未終端lease0を照合する。既存の期限付きwriter mutexと実共有epoch fenceの下で、一度限りactivation開始とlease登録を同じ耐久frameへ記録し、file/dir fsync後にだけattestation/leaseをACKする。mutexはこの不可分境界で解放し、rootcontrolの利用期間はepoch共有fenceを同channelで保持する。保持中も通常の別channel reserve/claimを許可し、epoch前進を阻止する。attestationのH0/count0は開始時点の実証であり、後続D4により増加してもfenceを偽失効させない。checkは実channel/lease/epoch/business identityの生存を再照合する。

**終了・失敗。** 正常context終了は実fenceを確認してlease終了をfsyncするだけで、RG1 open成功を自己申告で記録しない。rootconsumerは業務commit結果を確認するまでleaseを保持する。body例外・切断・不正replyは正常終了要求へ補完せず、開始後の未終端記録を保持して閉じる。ACK/終了不明でも、新freshを自動retryしない。終了fsync後のACKだけが失われた場合は既存の耐久終了記録を事実として保持し、未終端へ改ざんせずPastActivationにより新freshを拒否する。実未終端leaseの既存live/startup停止を維持する。正常終了済みを含めPastActivationがあれば新fresh開始は拒否し、同じDBを新sourceへnewして迂回しない。復元後0件は過去journalによりfreshと区別する。全設備喪失/非0復元の完成をfresh実装の着手前提へ追加せず、証明不能時はfail-closedを維持する。公開epoch advance/実closeProof/業務RG1変更は今回追加しない。

**編集scope/受入。** 次のsource委任は既存packageの`adapter.py`/`authority.py`/`manifest.json`/`__init__.py`、既存`backend/tests/test_durable_rights_ledger_contract.py`/`backend/tests/db/test_durable_rights_ledger.py`/`backend/tests/db/durable_rights_ledger_support.py`とresearchに限定する。新path/依存/DB API IDを予定せず、schema.sql/business_identity.sql/witness.py/初期付与Protocolは据置き。新sourceの免除なし全identity/独立AST/censusを再測定し、旧initial47/43・18を保持する。exact登録/必要最小の関連checker/census採用はrootの限定確認後だけ、正式9/8識別値/履歴/snapshot/policy/7.3/7.7は引き続きroot所有step4とする。実UID/peer＋実保護journal＋実同期PGで、初回成功と同channel metadata/fence、lease中の並行reserve/claim、実排他epoch lockの拒否、正常終了後の再fresh拒否、開始ACK喪失/body例外/未終端restart拒否、過去INTENT/不明/復元後0/旧genesisの拒否、同cluster内別databaseへのconfig差替え拒否を検証する。保護file/dir fsyncや認可をstub/skip成功にしない。root/business RG1成功の検査と全fault行列は別単位/既存step4へ保持する。


2026-10-23T21:27:34.197191+00:00、Codex主担当/rootはPO4/5/8/10に基づきfresh追補00d2f50d/plan1651f9d1411b118483d4bcea08117a054d2dae77a311ef6f5410db8633a539faを承認。非作者rights_replacement_reviewの限定第1回0/0/0、標準binarydiffca02bc2ef976ac971923a21e118efa1b624859961c7541634654b4bae6fba44dを照合。同channelの不変attestation/live fence・短い開始mutex・一度限りactivation・genesis database必須を既存step3内で個別実装する。旧b9の非作者レビューP1=2(database永続束縛、9関数temp-shadowing)を全採用し、通常是正を先行して固定・実検証後にfreshへ継続する。旧全レビュー/中間失敗/67・9件成功と新未達を保持し、公開advance/全域closeProof/非0復旧/全DoDを今回承認で成立としない。PO委任によるCodex判断であり、人間本人の署名/逐行確認を代記しない。


### fresh採用後の同一source登録値追随（2026-10-24）

PO委任によるCodex主担当/root判断。旧13exactの承認・拒否履歴を保持し、fresh採用済みadapter10906d157598b21f730665965c4231a64bfdfcadf057288cdd5e60e0255190e2へ同じ5path内で追随する。source候補ef39に対する非作者csv_reviewの限定0・独立再導出の実17exact/anchor除去22/独立AST1（証拠b365716ec4fbe3358a1131a31d659bad739423e347a029ed5c9dc7978ddca718）を根拠とし、旧initial47/除去43/AST18・他全登録/検出/拒否を不変保持する。17を件数だけで免除せずpath/source SHA/行/symbol全集合を固定する。意味・権限・耐久保証を変更せず、正式7.7は別ゲート。実4b2基線への通常merge89830dc1で全31guard本文ASTを保持、局所418成功/40.31秒。最終差分独立レビューと完全9/8再導出・実値受理は未成立で、今回の追随を正式提供へ昇格させない。
