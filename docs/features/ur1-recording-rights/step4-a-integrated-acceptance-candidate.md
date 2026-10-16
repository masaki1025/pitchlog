# U-R1 新4: A統合後のローカル候補と受理判断（2026-10-16）

## 比較元と現在地

- 共有実行器Aは [PR #141](https://github.com/masaki1025/pitchlog/pull/141) で統合済み。実統合SHAは `e7e8d3a4324687ada828b1e4b49692c087af5c44`。U-R1専用ブランチへ `git merge --no-edit origin/develop` で取り込み、ローカルmerge SHAは `9fa6415b713e5ce216ec325f02b07b014288e618`。rebase、push、PR作成、mergeはしていない。
- [Draft PR #143](https://github.com/masaki1025/pitchlog/pull/143)を既コミットの新2・新3と準備文書だけで作成した。準備HEADは`ca37bfc25d1b89660c6bb9dc622c43c74c358316`。新4の製品・認可・seed・凍結宣言は**未コミット・未pushのローカル候補**。正式台帳、history-snapshots、archiveの受理済み記録は変更していない。候補確認とPR最終HEADの7.7正式受理は別の判断である。
- U-S1のPort署名と呼出位置は既受理の接続契約を維持する。U-G1/U-S1の実入口への接合は新8、D4発行は新5以降、復元開始・製品openは新7であり、新4の完了に含めない。

## A接続と権限候補

- `RG1:precheck`と`RG1:commit_check`の2登録だけをAの静的`PRODUCT_FUNCTION_OPERATIONS`に追加。各tokenは入力フィールド0件。`tenant_id`はAが検証済みscopeから注入し、SQLは`rg1_api.rg1_read_open(uuid)`または`rg1_api.rg1_assert_open_before_commit(uuid)`の単一SELECTだけ。呼出側が任意tenantを指定する口はない。
- 2関数はGUCとのtenant一致をDB側でも検証し、現段階では状態行がopenでも必ずfalse。③-aは非ロック、⑧は`FOR SHARE NOWAIT`。呼出し側はfalseを`RG1Unavailable`に変え、同一scopeを全取消する。製品openの成功経路をこの候補に含めない。
- `rg1_restore_gate`は`singleton_id=1`の1行だけをmigration `0032`で`closed`投入。専用`NOLOGIN/NOBYPASSRLS` owner、FORCE RLS、ownerに`SELECT(singleton_id,state)`と`UPDATE(singleton_id)`だけ、SELECT/UPDATEとも単一行policy。`rg1_api`のapp権限はUSAGEと2関数EXECUTEだけで、PUBLIC EXECUTEとapp CREATEを拒否する。
- `check_authz_catalog.py`はRG1専用schema、2 policy、列UPDATEのexact tuple、46表集合だけを追加。汎用FOR SHARE、任意SQL、表UPDATE、他列/owner/関数のUPDATE許可は追加しない。

## 7.7 候補前後値（正式受理待ち）

次の値は、上記A統合SHAを比較元とした**C1統合前の現作業ツリー候補値**。受理ID候補は実PR番号に基づく`masaki1025/pitchlog#143`。新4の最終HEAD・承認者・承認日はまだない。受理記録やsnapshotファイルを正式台帳へ先行追加しない。C1を先行統合する順序が受理されれば、その受理済み履歴をbeforeに再算出する。

| 凍結資産 | before revision / snapshot SHA-256 | 候補after revision / snapshot SHA-256 |
| --- | --- | --- |
| `base-allowlist.json` | 31 / `0642f1ce39b037248e2fcc32ecc44950887d379d563a564bdcd9d97b31d4b515` | 32 / `699ee0ed84cd98ff5dbf83c6f8bb474b33db372be438136f38417a0a166cae23` |
| `cache-invalidation-contract.json` | 15 / `161d2815a06778fbac0bb679b5a5aa1d1295db2e7e0ed971d2b343a654daf32f` | 15 / `161d2815a06778fbac0bb679b5a5aa1d1295db2e7e0ed971d2b343a654daf32f` |
| `census-baseline.json` | 14 / `c717da79aee3504ab5176f88cd502ad40170389df7ad1aa60d4fb5c86e5f241f` | 14 / `c717da79aee3504ab5176f88cd502ad40170389df7ad1aa60d4fb5c86e5f241f` |
| `db-api-inventory.json` | 15 / `66ec5e8410adeab61f78bcb4ce72ec4ea55b32588d96e95d172013b2a8658999` | 15 / `66ec5e8410adeab61f78bcb4ce72ec4ea55b32588d96e95d172013b2a8658999` |
| `frozen-inputs.json` | 4 / `c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63` | 4 / `c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63` |
| `negative-fixtures.json` | 17 / `3513677e5ea3dff4db6471ef2b4ade93c91095ef5a3f43e085a5b8ee59c43d82` | 17 / `3513677e5ea3dff4db6471ef2b4ade93c91095ef5a3f43e085a5b8ee59c43d82` |
| `repository-contract.json` | 19 / `15c416e962e559312bc26502895d2718e508299459bbb6df3258758edf5c1004` | 20 / `fe307e0cd718fbc505549681c80459ee0413c4a09bd99400a56fdd3df7bba925` |
| `runtime-authz-contract.json` | 16 / `a335d85ba04eb9d7f002009ecaf2f7229f410c2a5335929b8d2ddf960af0a53a` | 17 / `061eeb9e96f110e059ad51bf3026d9b420f7c636a24045809afa33e7a0f6b393` |
| `tenant-context-allowlist.json` | 16 / `16e7a9a6a263f00381a327d8f05bce597dd036d67333ebfc55e035f1e8f9e2c2` | 16 / `16e7a9a6a263f00381a327d8f05bce597dd036d67333ebfc55e035f1e8f9e2c2` |

他の凍結6資産は識別値と射影digestがbefore/候補afterで一致する。上表のsnapshot参照はそれぞれ`contracts/tenant_boundary/history-snapshots/<SHA-256>`となる**予定**であり、まだ作成していない。権威台帳は`base-allowlist.json`。受理単位は先行PR最終HEADの単一未マージ記録1件で、既受理済み履歴、PR #72 marker、before側を維持する。movement_factは「A統合後のRG1固定SELECTシンボル1件、固定関数operation 2件、RG1専用認可表・関数により3資産のbaseline_valueが移動」、reasonは「復元ゲートの通常書込み停止を専用固定境界で実装し、既存DMLとテナント権限を広げず検証するため」とする案。PR番号取得用push/Draftだけは2026-10-16に許可されたが、acceptance_idを仮置きしない。

seed許可台帳の別系列`rg1_closed_seed`はbeforeで不存在、候補afterの宣言canonical SHA-256は`d6d05be6344a266d4ec63e2750694aa4b71341c119e03fbd3460f73cab1b7fb0`。対象migrationは`0032_rg1_restore_gate.py`、許可は`bulk_insert`の`rg1_restore_gate` 1行`{"singleton_id":1,"state":"closed"}`完全一致のみ。記録案は`series=rg1_closed_seed`、`prior_identity={present:false,values:[]}`、`new_identity={present:true,values:[{kind:sha256_canonical_json,value:<上記SHA>}]}`、変更面`declaration`のbefore不在→after上記exact宣言、fact=RG1単一closed初期行だけのmigration投入を許可、reason=通常書込を既定閉鎖するため。既存語彙2系列・履歴は不変。正式7.7-2記録の承認者・日付は受理後に実記録から転記する。

## 検査と残るゲート

- 隔離PostgreSQLの直接行ロック正常系と製品2関数の常閉試験は別に実施。正式`function-bodies` SQLを試験から直接読み、Aの実`tenant_transaction_scope`経由で③-a/⑧の閉鎖拒否と同一transactionの検証用DML全取消を2口で確認した。試験用openは運用解除ではない。
- RG1・認可・migrationの関連試験266件、repository/capability関連200件、schema manifest14件、core guard262件が成功。backend/root Ruff・ty、製品authz catalog、function bodies検査も成功。独立レビュー指摘のモデル欠落、PK自動採番、正式bodyとfixtureの乖離、A実接続試験不足、schema ACL固定不足を候補へ反映した。同一独立レビュアの最終再照合は**P0/P1/P2とも0件**、関連65件成功。最終差分の7.7正式受理・人間逐行確認は別ゲート。
- 未受理期間の`check_tenant_boundary_bypass.py`は履歴末尾とrevision不一致で失敗する。migration衛生全件も正式seed台帳に新系列がないため1件拒否する。この赤を検査器の緩和で消さない。PR最終HEADの正式受理後にauthority履歴・snapshot・archive・seed台帳へ実承認者/日付を反映し、同HEADで再検査する。
- 製品認可全資産の試験は、共有DBの既存test roleと衝突したため、管理接続を別コンテナへ向けた専用使い捨てクラスタで再実行した。初回適用ではRG1を含む全資産のcatalog照合が成功し、取り外し時にRG1列UPDATEの権限が残る不具合を発見した。RG1 exact tupleのSELECT/UPDATE両方をREVOKEする最小修正後、適用・取り外し・migration往復・再適用の3件、適用器単体49件が成功した。共有ロールは変更していない。追加独立レビューはHEAD`ca37bfc2`の候補差分識別値（tracked binary diff SHA-256=`b32c7aa2f6e5e7541c49008e5d37fe5f32a72946786f7fa565c7cb45e3e0d805`、未追跡ファイル列SHA集約=`d21c69b3cc5ee4b50f860878430406bbcbb058fb9c5ba4288973f26f77201f00`）で**P0/P1/P2=0**。
- rootの`test_check_authz_catalog.py`全数試験は大規模な変異集合の途中までで停止した。旧未発効fixtureが45表を前提にする既存試験をRG1候補の46表から隔離する修正を加え、該当1件は成功。全数greenと記録しない。
- PR #143の準備HEAD CIはcore guardで、**人間逐行確認欄が未チェック**のため失敗した。チェックを偽って通さない。本文には正式な未チェック行を置き、人間確認後の別ゲートで再実行する。
- `TenantProfileReadToken`のC1は独立カードではなく**TSK-528の追補C1**（`docs/features/auth-session-verification-contract/plan.md`）と確認した。U-C1/TSK-401のグループ管理操作とは別である。C1の第1段`d5ccc18e`・第2段`7731070a`もA統合後の同じ`repository-contract`19→20、`base-allowlist`31→32を候補に持つため、C1正式受理・統合を先行し、その受理済み履歴をU-R1の新beforeにする順序をC1担当へ提示した。担当回答までは合意済みと扱わず、同時編集や未統合ブランチ基線による受理をしない。C1全体の完成はU-R1の着手条件にしない。
- guard3ファイルのU-R1差分は既存コミットに固定、未コミット差分0、今後の既知編集予定0。TSK-506へ編集所有を解除し、正式Notionカードへ引き渡した（コメント`3fb93b75-e687-8133-81a0-001d15c6c17d`）。TSK-506は最新developを基線にし、U-R1未統合ブランチを基線にしない。登録済み層、段階登録、実経路試験を統合時に維持する。

## 次の人間判断

1. 新4の候補と正本`data-model.md`§3-2の節更新、専用DDL/JSON、seed系列、限定検査器差分に対する必要な正本・認可レビューを確認する。
2. 許可済みのPR番号取得用push/Draftでは、既コミットの宣言・登録と準備文書だけを公開する。新4製品・凍結候補は正式7.7手順に沿った受理単位まで未コミット・未pushとする。PR最終候補HEADが固定した後、C1先行側の受理済み履歴から再導出した3資産とseed系列の**実値**、完全差分、独立レビュー・検査結果を使って7.7正式受理を判断する。今回の候補値を承認済み履歴に転記しない。
