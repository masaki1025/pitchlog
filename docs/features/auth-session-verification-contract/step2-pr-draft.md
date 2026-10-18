# Draft PR: C1ステップ2 検証済みsessionの認証供給

## 概要・状態

既存の共有Pinia・QueryClient・共通APIを利用し、sessionの2xxと厳密DTO検証が成功した場合だけtenant IDと正規表示名を認証storeへ採用する。保存値だけでは認証せず、未確認中のtenant-bound通信を拒否する。

loginの確定拒否、サーバー未認証、結果未確認を分ける。Cookie変更可能性のある遅延login/logoutだけは、新世代も未確認へ戻しcacheを破棄する安全側の例外を適用する。旧ユーザー/tenant/成功を採用せず、資格情報・mutation・session確認を自動再送しない。

**Draft・検査待ち。全品質ゲート通過・C1ステップ2完了・本人逐行確認済みではない。** 2026-10-18の山田正輝承認により、pr手順2.4に対するC1ステップ2限定のDraft先行例外で提出する。Draft解除・公開・マージは禁止を維持する。

## 関連と基線

- U-F13 / TSK-528追補C1。[計画](plan.md)、[検査・レビュー・本人確認資料](step2-review-material.md)、[review hash](step2-review-manifest.json)。
- TSK-528全体、TSK-520実API受入、U-F13残部は未完了。C2/U-F3・認証guard・/team接続・実APIブラウザ受入・15経路＋catch-allは今回含めない。
- ステップ1はPR #144、統合SHA `3052e0db743877c7f15c0ec10daa0142cba7ab7e`。製品コミットは`1fea2c60f04f9c50c882298042b5a0458dd5879a`。
- 現基線は#145/#146統合後の`ce0c0e8697252a89bce0c57e69b4821e0a6cac2b`。mergeで追随し競合なし。製品3ファイルは第2周review hashと一致。
- 最終HEADは実際のPR本文へ機械取得した完全SHAを記載する。認可・ACL・wire API/DTO・migration・共有凍結資産にC1差分はない。新しい7.7対象はない。

## 成功済み検査と未通過

| 検査 | 結果 |
| --- | --- |
| 製品候補のformat / lint / 型 / dependency-cruiser / build・closure | 成功済み。製品3ファイルはreview後変更なし |
| C1対象6ファイル | 直列全件実行内で184試験成功 |
| frontend直列全件（2026-10-17） | 68ファイル、1,236 passed / 既存domain-sql試験1 timeout |
| 当該timeoutの単独再試験 | 1 passed / 非対象14 skipped（3.68秒）。全件greenの代用とはしない |
| frontendの他の全件実行 | worker起動/終了timeout等で未完了・失敗。試験除外・timeout緩和なし |
| root全件（前回） | 25,605 passed / 2 skipped / 1 subprocess timeoutで中断。後の実行も12,684 passed / 2 skippedで中断。未完走 |
| backend全件（前回） | 専用DBでも2 failed / 12 passedで中断。子PostgreSQLの既存60秒起動期限。未完走 |
| #146の実適用 | root/backend conftestの配線を確認。今回はTMPDIR/PYTEST_DEBUG_TEMPROOT/--basetempで迂回せず、専用PITCHLOG_PYTEST_TMPDIRで検証中 |
| 最終HEADの全検査/CI | 実行後にPR資料へ更新。未通過を先行チェックしない |

## レビューとレビュー後の修正

- 指定wrapper敵対レビュー第2周: **可決 P0=0 / P1=0 / P2=0**。
- Claude反対側第2周: **可決 P0=0 / P1=0 / P2=2**。両P2を採用。
- レビュー後は、現世代headers後本文失敗の一回破棄試験、旧応答の本文非読取assert、sessionとの前後競合試験、資料の現在状態・件数表現を補正した。製品3ファイルのhashは変わっていない。
- 静的レビューの可決を実行試験・本人逐行確認の代わりにしない。既定2周を維持する。

## 正本反映・品質・本人確認

- [x] 正本影響を確認した（計画§2.1の反映なしと一致）。
- [ ] /check 全グリーン。
- [ ] C1ステップ2の全DoDを満たした。
- [x] 反対側レビュー済み（Claude一次レビュー・採否は上記）。
- [x] codex_run.py review adversarial 済み（第1周全差分、第2周修正差分と影響）。
- [ ] コア領域/検査経路の変更: 人間による逐行確認を実施した
- 実施記録: 対象= 範囲= 方法=

本人欄は未記入のまま。契約追補承認・ステップ1の7.7受理を流用しない。

確認準備対象: 最終HEADの基線からの17ファイル全差分。製品3ファイル（api/auth.ts・api/client.ts・stores/authStore.ts）、spec6、計画/記録8。DTO厳密検証、Cookie副作用、epoch、確定拒否/未確認、singleflight、保存値/別タブ、cache破棄、非再送を試験と突合して逐行確認する。

意味範囲はtenant分離。機械検出は製品/spec9ファイルすべてに該当（client系はsync-protocol/recording-rightsにも該当）。guard_paths変更なし。本人未チェックではproduction guardが9ファイルを拒否することを確認済み。チェックを代記して通さない。

## 後続への接続

C1がauth/client/storeを一時所有し、統合後にC2/U-F3が実基線から引き継ぐ。C2は応答tenant照合、U-F3は結果epoch照合と未確認表示・明示GET再確認を担う。同じepochの未確認結果で通知を重複しない。共有sessionのsignal中断は待機者へ影響し、別タブの確認・保存で他タブも未確認になり得る保守的な契約を維持する。

## 現在地導出

PR作成前に実行したfeature_status.pyの全出力を実PR本文へ転記する。基線に統合済みのステップ1を新差分が含まないため、C1の欠番警告が出る場合も非ブロッキングの導出限界として記録する。警告を消すための履歴・ハーネス変更は行わない。
