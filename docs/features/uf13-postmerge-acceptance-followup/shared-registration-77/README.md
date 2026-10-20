# #165 自チーム取得・7.7正式受理用固定資料

**現在: 2026-10-21に山田正輝が7.7正式受理。本人逐行確認は未実施。以下のJSON・記録案・候補snapshotは承認時の固定資料として変更しない。**

実develop基線: `8e4698f6dc254439b7d5e0c273cc2aef70cda657`。製品候補: `0ffe83b6bb89d92a9922bddfe21eae95ab08b50b`。既存PR #165を再利用する。

## 判断対象

- 受理単位は `masaki1025/pitchlog#165` の1件。既存単一履歴23件に同IDは存在しない。既存履歴は変更・削除せず正式受理後に1件だけ追記する。
- repository公開型へSelfTeamRecordReadTokenを追加し、JSONのcontract_revisionを21から22へ更新する。45型・全capability対応は実registryと厳密一致する。既存CAP:team_records:readを再利用し、拒否境界は縮小しない。
- base allowlistのrevision33・許可symbol・凍結射影は不変。同ファイルは正式受理後の唯一の履歴追記先として対象に含む。authz・ACL・migration・共有検査器は変更しない。

## SHA-256と完全値

- [判断資料JSON](decision-packet.json): `2e20c20e16bb8d0a0566405b3592a55892f83462716afe5b4322c031a273ff8c`
- [受理記録案](record-proposal.json): `f35b6bf0230064ec8817302f05c3e752972e3d90807067eab70b81a4656439a9`

判断資料JSONは全9資産の前後識別値・宣言・movement policy・全asset/external snapshot参照、変更する射影の全内容、3パスの前後Git blobとSHA-256、既存履歴のhashを収録する。受理記録案のapproved_by/approved_onはnullであり、そのまま正式記録として合格しない。

| 項目 | before | after |
| --- | --- | --- |
| repository source_digest | `117c924bf5c0174b4846c301d3a6fbb0e2457283fccd2edbf7de7a3139baedae` | `938a704da00d506487831c06785aadec549071110bb7b67f3a8b9b3cfb25db38` |
| repository凍結snapshot (before) | [0daf9ec4b9d5dc7eea364a0001804ba187f3bed87e02850f2da5b21613dc0e11](candidate-snapshots/0daf9ec4b9d5dc7eea364a0001804ba187f3bed87e02850f2da5b21613dc0e11) | 完全bytes、SHA-256はファイル名と一致 |
| repository凍結snapshot (after) | [9872b2b0d5233193b3e3d76b37b144599d5d2ea8c14a93f1df6cd20a834bd3b0](candidate-snapshots/9872b2b0d5233193b3e3d76b37b144599d5d2ea8c14a93f1df6cd20a834bd3b0) | 完全bytes、SHA-256はファイル名と一致 |

## 機械照合と未通過検査

- 実baselineからgit showでbeforeを取得し、製品候補の実ファイルからafterを取得した。既存frozen_historyの射影・snapshot・movement導出関数を使用し、独自の凍結定義や検査器変更は追加しない。
- 変更資産はrepository-contract.jsonのみ。外部凍結対象8ファイル（完全値JSONの全列挙）は同一、他8射影と既存23履歴は同一、#165記録の重複なし、追加型はself1型のみ。全snapshot参照を既存archive＋候補bytesで解決・照合した。
- 候補snapshotは本資料配下にのみ置く。正式history-snapshotsへの追加、base allowlistへの履歴反映は正式受理後に行う。
- backend関連は最初の161件に加え、API/tenant/route影響を含む統合選択200件（2.08秒）が成功。Ruff format/check、ty成功。全件検査・最終HEAD CIは正式反映後に再実行する。frontend製品・試験は本限定差分で変更なし。
- tenant-boundary実検査は受理記録未反映のため「履歴末尾と7資産の識別値が不一致」で拒否。期待どおりの未通過として保持し、緩和しない。core-guard本人チェックも未実施のまま維持する。

## レビューと人間判断

- 実装の反対側・敵対レビューは各2/2使用済みの履歴を保持。POが2026-10-21に限定追加1回を許可し、HEAD `5295956f9b883d20776f27bb4acfe47fc15a756d` の共有3パス・直接影響箇所・記録案・完全値資料を敵対レビューした。結果はP0/P1/P2各0件、修正不要。基本枠をリセットせず、敵対レビューは基本2回＋PO限定追加1回、反対側は基本2回のまま。
- 正式7.7受理は本資料の完全値を対象に別回答が必要。今回のD先行指定は新実値の受理ではない。
- 正式受理後の反映・必要全検査・通常push・最終CI回収は許可済み。本人逐行確認、Draft解除、公開、マージは未実施・対象外。

## 後続担当への引渡し

- #152・#156・#161へD先行を通知済み。通知を担当受理・所有解除と混同しない。他担当worktreeには変更しない。
- 先行内容はrepository_contract.py公開型／source digest、repository-contract.json revision22、base-allowlist.jsonの#165単一履歴（正式反映後）。同じrevision22の別候補を同一視しない。
- 後続はDの統合後の実developを基線として、自身の型・関数登録・受理前後値を再導出する。未統合D枝を正式基線にしない。
- 正式履歴は反映前なのでbase allowlistの引渡しは未了。現在の3パスのD編集順は維持する。

## 限定追加レビューの終結（2026-10-21）

9資産の実前後値・2 snapshot・source digest・既存23履歴・45型の順序と全capability対応を独立照合し、指摘なし。資料JSON・記録案・製品/試験・受理対象値は変更せず、上記のSHA-256をそのまま使う。関連200件は前回の成功結果であり、このレビューで再実行したとは扱わない。

レビュー後の未再レビュー差分は、このレビュー結果記録と計画・作業ログへの同じ事実の追記だけ。製品・契約・snapshot・記録案の是正差分はない。仮の承認値を用いたメモリ上の構造照合は正式受理・実履歴反映・最終CIの代用にしない。正式受理、本人逐行確認、Draft解除、公開、マージは未実施。

## 7.7正式受理・正式反映（2026-10-21）

承認者は山田正輝、承認日は2026-10-21、対象HEADはba23630a1772bd3595e3042a434376175d3aa56b。上記SHA-256の完全前後値をmasaki1025/pitchlog#165の単一受理として受領した。固定JSON/記録案のnullは承認前資料のまま保持し、正式記録には本人から指定された承認者・日付だけを反映する。正式記録の正規化整形JSON SHA-256は `06a48c1ed6bbae5aed4ef0effdd60c283edef997a243477dbfa3b8fe09651639`（sort_keys/indent2/末尾改行）である。

base allowlistの既受理23履歴をそのまま保持して#165を1件追記し、正式history-snapshotsへafterの9872b2…を1件追加した。beforeの0daf9e…は既存bytes一致を確認して再追加しない。base allowlist33/許可symbol/射影、他8資産・authzは不変。正式反映後のtenant-boundary検査は成功。必要全検査・最終CIは別途実行記録へ残し、旧成功を今回の成功へ読み替えない。

レビュー履歴は基本2回＋限定追加1回を維持する。旧レビュー後の結果記録3ファイルと、本正式反映/記録は未再レビューのまま最終本人確認対象へ含める。本受理は本人逐行確認・Draft解除・マージ・公開を含まない。

## manifest参照digestの限定追随

第4共有パスはtests/fixtures/frozen-archive-cases/manifest.jsonのcorpus_inputs.digestのみ。正式反映済みrepository契約に対応し、旧b3accebe…からf50b17a2…へ1値だけ追随する。比較manifestの正規化内容・case/期待値/prefix/snapshot集合・runnerは不変。全9資産の射影、完全値JSONに列挙された全8外部参照、全24履歴、承認資料2件を照合し、7.7受理値への影響なし。旧説明の外部対象数「4」は「8」へ訂正したが、受理済みJSONはもともと全8件を収録しており変更しない。

旧失敗33件を含む関連65試験は成功。固定前版ec02a0dのowner_paths非対応による既存残余は維持し、前版の再実行成功とはしない。新しい7.7記録や同じ#165の重複記録は追加しない。PO指定の限定追加レビューは追加2回目であり基本2周＋前回追加1回を保持する。
