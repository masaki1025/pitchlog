# U-R1 新ステップ2: 追補・資産・受理の判断資料

2026-10-15。対象はRG1の新2だけ。詳細は[受理順序追補案](step2-acceptance-order-addendum-proposal.md)・[個別承認資料](rg1-individual-approval-packet.md)・[承認済み最小追補](step2-minimal-addendum-proposal.md)。本資料は5件の設計方針を再審査せず、最終計画承認・正確な資産承認・候補作成許可・7.7正式受理を区別する。

## 現在地と計画の具体差分

`origin/develop`は`3f6a935a`。TSK-550の共有実行器Aは別worktreeの未コミット候補であり、developには未統合。したがってU-R1の実revision/digest/snapshotは**未確定**。Aの候補には`FunctionOperationRegistration`、固定registry、`_TenantTransaction.run_function`、`repository-contract.json`の公開面がある。U-R1はAの登録形式を再利用してRG1の固定読取2登録だけを後載せし、Bのresolver登録完了やTSK-550全体の完了を待たない。

| 判断対象 | 現行 | 提案 |
| --- | --- | --- |
| PR・7.7単位 | 新2〜6を同じPRの単一記録afterへ順次反映し、PR最終HEADを1回正式受理 | **新2を独立PRの最終製品ステップ**としてその最終候補状態を1回受理。新3以降は別PRとし各PRでbefore・番号・記録を持つ。7.7条文・`single_review_acceptance`は維持 |
| 新2の候補作成 | 正式受理を実装開始前に要求するためafterを算出できない | A統合と具体資産の個別承認、候補作成の明示許可後、ローカルで候補作成。正式台帳にはまだ記入しない |
| 検査 | 各ステップをgreenとするが未受理期間の履歴不一致を未定義 | 候補時の履歴不一致は**不合格のまま**記録・提示。受理記録反映後のステップコミット前に履歴/archive/全品質ゲートをgreenにする。検査器の緩和・skipなし |
| PR番号・snapshot | 実番号・実blobが必要 | 計画/作業ログのみの準備push/Draftは別Git許可を得る。snapshotに中間コミットが不可欠なら例外を事前提示。受理前に実承認者・日付を仮置きしない |

この変更は**実装計画のPR境界と新2/9の合格条件**に及ぶ。凍結契約の受理単位、検査器、正本7.7自体の変更は提案しない。後続PR数とレビュー負荷は増える。最終候補受理後に差分が動く場合は再提示・再受理する。

## 資産の候補集合と確認点

次は**設計方針から導いた審査対象**であり、正確なDDL/JSON承認値ではない。A統合後の実形式で全行差分を固定してから個別承認を受ける。

| 資産 | 提案する具体的な差分 | 未確定・拒否条件 |
| --- | --- | --- |
| DB DDL | `public.rg1_restore_gate(singleton_id smallint PRIMARY KEY CHECK(singleton_id=1), state text NOT NULL CHECK(state IN ('closed','open')))`の1行`(1,'closed')`、`ENABLE/FORCE ROW LEVEL SECURITY`。`rg1_api` schema、`pitchlog_rg1_fn_owner`=`NOLOGIN/NOBYPASSRLS`。同ownerだけ`SELECT(singleton_id,state)`と`UPDATE(singleton_id)`、singleton限定SELECT/UPDATE policy。読取2関数は`SECURITY DEFINER`・固定search_path・PUBLIC EXECUTE剥奪、appには2件だけEXECUTE | 正確なSQL・seed/RLS適用順、role/schema/列ACLの実効値と既存policy合成は実DBで検証。app表ACL、INSERT/DELETE policy、復元開始関数、製品openを追加しない |
| 関数・固定登録 | `rg1_api.rg1_read_open()`は③-a非ロック、`rg1_api.rg1_assert_open_before_commit()`は⑧`FOR SHARE NOWAIT`。両者は新2では古いopen行でも常にfalse。Aの固定関数registryへtoken/operation ID各2件、固定SQL、exact bool結果、0/複数行・未知token拒否 | function bodyとTSK-550実登録schemaの最終形はA統合後に確定。任意SQL、Session、汎用FOR SHARE、DML実行器の緩和なし |
| JSON/正本 | `data-model.md`§3-2の専用roleとRG1の非テナント制御事実、`table-classification.json`のRG1 1表`function_only`/`owner_unit: U-R1`、露出事実・owner許可集合、`ddl-elements.json`/function-bodies/manifest/認可runtimeの1表・2関数・ACL/policy、repository-contractの2登録と必要な最小SQLA_SELECT symbol/正負fixtureを差分化 | 現行分類器は非テナント`function_only`を拒否するため、正本7.6・必要な7.3と認可担当のゲートが必要。既存分類・既存関数/allowlist symbolの権限拡大なし。実JSON key、revision、digestはA統合後に提示 |
| 派生・履歴 | 変化した入力に限りlock/oracle、archive、7資産のsnapshotを追随。authorityは`base-allowlist.json`。新2PR番号の単一記録を候補afterと照合して正式受理後に追記 | 既受理済み履歴・before・PR #72 markerは不変。A統合後の実before/after、blob、movement_fact/reasonと人間の受理記録が必要 |

## 試験と7.7の停止点

1. **候補段階**: PostgreSQL実DBでowner属性、FORCE RLS、policy/ACL exact-set、app表4操作・PUBLIC/未知関数EXECUTE拒否、他policyとの合成、`FOR SHARE NOWAIT`競合、欠損/不正状態/読取例外のfail-closedを確認する。隔離DBの開状態行に対する直接行ロック正常系と、製品2関数の常閉拒否を**別試験**にする。P3はB10、全scope取消、隠れた自動再送なし。
2. **固定実行器**: Aの2登録についてtoken偽造・失効・余計なbind・未知kind・型違い・SQL束縛値/同一scopeを検証し、既存DMLやテナント境界の負例を維持する。U-G1/U-S1実経路の結合は新6。
3. **7.7候補提示**: 実before/after revision・canonical digest・snapshot/blob・全変更ファイル・movement_fact/reason・PR番号と独立レビューを人間へ提示する。履歴検査の予期した赤を明示し、受理済みとは記録しない。
4. **正式受理後**: 実承認者/日付を転記してauthority台帳1件、派生資産/archiveを整合させる。履歴・契約・DB/認可・pytest/ruff/tyをgreenにしてから新2コミットとPR最終HEADを照合する。CIと人間逐行確認は別の完了ゲート。未受理の候補をpush・mergeしない。

## 残る人間判断の順序

1. 本[順序追補案](step2-acceptance-order-addendum-proposal.md)の**最終計画承認**。追加独立レビューでP0/P1が残れば修正案・影響を再提示する。
2. A統合後、正確なDDL/JSON・必要正本、候補作成の限定許可、必要なら準備push/Draftまたはsnapshot中間コミットのGit操作を個別に判断する。
3. 候補の実revision/digest/snapshot/全差分に対し、PR最終候補状態の7.7正式受理を判断する。

D4方式・製品open/復元開始は新5側、新6実経路結合は別ゲート。mergeは本資料の射程外。
