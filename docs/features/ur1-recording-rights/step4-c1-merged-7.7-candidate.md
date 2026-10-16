# U-R1 新4: C1統合後の7.7受理候補（2026-10-17）

## 比較元と範囲

- C1 / PR #144 は `3052e0db743877c7f15c0ec10daa0142cba7ab7e` で `develop` に統合済み。U-R1へ `origin/develop` をmergeで取り込んだ。2026-10-17の再fetchでも`origin/develop`は同SHA。RG1候補は保全後に再適用し、C1の受理済み履歴と全before側を保持した。
- `base-allowlist.json` の履歴末尾は `masaki1025/pitchlog#144`、承認者 `山田正輝`、承認日 `2026-10-16`。U-R1の受理ID候補は `masaki1025/pitchlog#143`。本資料は**受理待ち**であり、承認者・承認日を仮記入しない。
- 変更内容はRG1固定SELECTビルダー1件、固定function operation 2件、RG1専用の表・owner・2関数の認可宣言。既存のC1登録、既存受理履歴、他6凍結資産は変更しない。C1→U-R1→TSK-550本体Bの順序を維持する。T1/T2担当の現未コミット差分は同担当のplan/design/worklogだけでRG1新4の製品・認可候補と重複しないため、返信を停止条件にしない。後に実際の共有ファイルを編集するときだけ再照合する。

## 実基線から再導出した識別値

`scripts/frozen_history.py` の `frozen_projection_content` で、beforeをmerge後HEAD、afterを現ローカル候補として算出した。snapshot参照先は `contracts/tenant_boundary/history-snapshots/<sha256>`。afterファイルは正式受理前には台帳へ追加しない。

9資産すべての宣言・識別値・snapshot参照とseedの正確なbefore/afterは[機械可読の受理待ち案](step4-c1-merged-7.7-record-proposal.json)に収めた。承認情報フィールドは未記入であり、このJSON自体を正式台帳として扱わない。

| 資産 | before revision / snapshot SHA-256 | 受理待ちafter revision / snapshot SHA-256 |
| --- | --- | --- |
| `base-allowlist.json` | 32 / `20c8f0f71734d244e8734a0ded0903d380cfcae79315549ccd318a8a6e6ebabf` | 33 / `18934cf78b6621bb43cbce93581e31d1f117e9ced21b24a23f1bd4bec68091d6` |
| `cache-invalidation-contract.json` | 15 / `161d2815a06778fbac0bb679b5a5aa1d1295db2e7e0ed971d2b343a654daf32f` | 15 / 同左 |
| `census-baseline.json` | 14 / `c717da79aee3504ab5176f88cd502ad40170389df7ad1aa60d4fb5c86e5f241f` | 14 / 同左 |
| `db-api-inventory.json` | 15 / `66ec5e8410adeab61f78bcb4ce72ec4ea55b32588d96e95d172013b2a8658999` | 15 / 同左 |
| `frozen-inputs.json` | 4 / `c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63` | 4 / 同左 |
| `negative-fixtures.json` | 17 / `3513677e5ea3dff4db6471ef2b4ade93c91095ef5a3f43e085a5b8ee59c43d82` | 17 / 同左 |
| `repository-contract.json` | 20 / `71cb7a8bba95d335571411198044da40b1ac05d06707a9c34a9fb396bf6c2a00` | 21 / `0daf9ec4b9d5dc7eea364a0001804ba187f3bed87e02850f2da5b21613dc0e11` |
| `runtime-authz-contract.json` | 16 / `a335d85ba04eb9d7f002009ecaf2f7229f410c2a5335929b8d2ddf960af0a53a` | 17 / `061eeb9e96f110e059ad51bf3026d9b420f7c636a24045809afa33e7a0f6b393` |
| `tenant-context-allowlist.json` | 16 / `16e7a9a6a263f00381a327d8f05bce597dd036d67333ebfc55e035f1e8f9e2c2` | 16 / 同左 |

残る6資産はbefore/afterの識別値とsnapshot SHA-256が完全一致。`repository-contract.json` のafter `source_digest` は `117c924bf5c0174b4846c301d3a6fbb0e2457283fccd2edbf7de7a3139baedae` で、生成定数も同値。`runtime-authz-contract.json` のafter `source_digest` は `13eeb95f54a8a713620a12c369505311349e72148c521141ed524ece91b0f62d`。`base-allowlist.json` に `source_digest` フィールドはない。

## 7.7受理記録案

- authority: `contracts/tenant_boundary/base-allowlist.json`。同台帳へPR #143の**単一未マージ記録1件**を末尾追加する案。既存22件、PR #72 marker、PR #144の受理記録を改変しない。
- `previous_baseline_identifiers` と `change.before` はC1統合済みHEADから取得する。`new_baseline_identifiers` と `change.after` は上表の3件だけを更新し、他6件はbeforeを保持する。`aspect` は `asset_snapshots` と `declaration`。
- `movement_fact` 案: 「RG1固定SELECTビルダー1件、固定function operation 2件、RG1専用の表・owner・関数により、base-allowlist 32→33、repository-contract 20→21、runtime-authz 16→17へ移動。他6資産の識別値は不変。」
- `reason` 案: 「復元開始時に通常書込みを止めるRG1の固定読取境界を設け、既存DMLとテナント権限を拡大せず検証するため。」
- snapshotはafter 3件だけを新規作成し、既存snapshotを保持する。導出済み内容はそれぞれ11,868・7,560・6,550バイト（合計25,978バイト）。新規3件はすべて提案記録から参照され、孤児を増やさない。archiveの参照・digestは正式記録と同じ最終HEADの内容から追随する。承認者・日付は正式受理後の実記録から転記する。

## seed別系列

- `contracts/migrations/seed-allowlist.json` の既存2系列・履歴2件はbeforeとして保持。`rg1_closed_seed` はbeforeで不存在。
- after宣言のcanonical SHA-256は `d6d05be6344a266d4ec63e2750694aa4b71341c119e03fbd3460f73cab1b7fb0`。`0032_rg1_restore_gate.py` の `bulk_insert`、`rg1_restore_gate` 1行、`singleton_id=1, state=closed` の完全一致だけを許可する。
- 記録案は `series=rg1_closed_seed`、`prior_identity={present:false,values:[]}`、`new_identity={present:true,values:[{kind:sha256_canonical_json,value:<上記SHA>}]}`、`changes=[{aspect:declaration,before:{absent:true},after:<上記宣言>}]`。factは「RG1単一closed初期行だけを投入」、reasonは「通常書込みを既定閉鎖するため」。`approved_by`・`approved_at` は正式受理後に記入する。

## 保留する境界

ローカル候補のbackend関連pytest155件、C1 repository/capability149件、専用DBでの製品認可3件、root認可catalog全数25,820件、backend/root Ruff・ty、製品authz catalog・function bodies・docs-statusが成功した。C1統合の影響差分に限る独立レビューは、stash再適用後のstage旧revisionを是正してP0/P1/P2=0。検査の詳細は[作業ログ](../../worklog/2026-10-15-ur1-recording-rights.md)に記す。未受理期間は凍結履歴検査と正式seed台帳を使うmigration衛生検査が失敗する設計であり、検査器を緩めない。公開中のDraft PR #143は準備HEADであり、未push候補のローカル検査をCI greenと扱わない。7.7正式受理、本人逐行確認、Draft解除、マージ、D4方式、運用openはこの資料で成立しない。

## 候補の固定と正式受理後の順序

- 公開中のDraft PR #143のHEADは`cd03ddcb028878ac5c43dc9823463974040a29eb`（準備文書のみ）。ローカルのC1取り込み・判断資料コミットを親とするRG1新4候補は、**製品・認可・テスト40ファイル**である。`docs/features/ur1-recording-rights/claude-handoff.md`は古い未追跡申し送りで、この候補には含めない。一時indexで`HEAD`に40ファイルを重ねたbinary patch SHA-256は`779a5bf69b793fae10735e1383c40fcb9f5c130b360c7afa9061fe796d2db604`、変更パスmanifest SHA-256は`dd2c4225456718b357fa90b7d52f06cddbaf03f4afa2a7af3623e40fc33f0f31`。実indexにはstageしていない。
- **正式受理の対象**は、PR #143に入れるこの固定候補内容と上記9資産のafter、3 snapshot、seed記録案の**単一の最終候補状態**である。承認者・日時と後続のGit commit SHAを先に埋めない。正式受理後、実際の承認情報だけを権威台帳1件とseed別系列1件へ転記し、3 snapshotを追加してarchiveを追随させ、製品・契約・履歴を新4の1コミットにまとめる。
- その**履歴反映コミットがPR #143の最終HEAD**となる。候補受理とコミットは別時点なので、コミット後に実HEAD・PR番号・before/after・snapshot・seed・全差分が承認候補と一致することを再照合する。実HEAD SHAはコミット後に初めて報告する。候補内容や比較元が変われば、既受理を流用せず差分を再提示する。作業ツリー検査の後、HEADを読む凍結履歴/archive/契約検査を実コミットで通し、許可されたpush後のCIを確認する。本人逐行確認欄は未チェックのまま維持する。
