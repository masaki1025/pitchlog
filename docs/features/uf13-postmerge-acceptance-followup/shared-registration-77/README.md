# #165 自チーム取得・7.7正式受理用固定資料

**状態: 未受理。承認者・承認日未入力。本人逐行確認未実施。**

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
- 変更資産はrepository-contract.jsonのみ。外部4実装は同一、他8射影と既存23履歴は同一、#165記録の重複なし、追加型はself1型のみ。全snapshot参照を既存archive＋候補bytesで解決・照合した。
- 候補snapshotは本資料配下にのみ置く。正式history-snapshotsへの追加、base allowlistへの履歴反映は正式受理後に行う。
- backend関連は最初の161件に加え、API/tenant/route影響を含む統合選択200件（2.08秒）が成功。Ruff format/check、ty成功。全件検査・最終HEAD CIは正式反映後に再実行する。frontend製品・試験は本限定差分で変更なし。
- tenant-boundary実検査は受理記録未反映のため「履歴末尾と7資産の識別値が不一致」で拒否。期待どおりの未通過として保持し、緩和しない。core-guard本人チェックも未実施のまま維持する。

## レビューと人間判断

- 実装の反対側・敵対レビューは各2/2使用済み。本限定差分・記録案はその後発差分であり未再レビュー。旧レビューを流用しない。6.3上限を超えて自動追加せず、本限定差分＋影響箇所に限る追加1回が必要ならPO裁定対象とする。
- 正式7.7受理は本資料の完全値を対象に別回答が必要。今回のD先行指定は新実値の受理ではない。
- 正式受理後の反映・必要全検査・通常push・最終CI回収は許可済み。本人逐行確認、Draft解除、公開、マージは未実施・対象外。

## 後続担当への引渡し

- #152・#156・#161へD先行を通知済み。通知を担当受理・所有解除と混同しない。他担当worktreeには変更しない。
- 先行内容はrepository_contract.py公開型／source digest、repository-contract.json revision22、base-allowlist.jsonの#165単一履歴（正式反映後）。同じrevision22の別候補を同一視しない。
- 後続はDの統合後の実developを基線として、自身の型・関数登録・受理前後値を再導出する。未統合D枝を正式基線にしない。
- 正式履歴は反映前なのでbase allowlistの引渡しは未了。現在の3パスのD編集順は維持する。
