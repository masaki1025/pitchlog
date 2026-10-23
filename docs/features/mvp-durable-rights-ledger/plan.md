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
