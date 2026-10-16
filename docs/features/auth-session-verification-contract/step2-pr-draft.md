# PR準備: C1ステップ2 検証済みsessionの認証供給

## 概要

既存の共有Pinia・QueryClient・共通APIを利用し、sessionの2xxと厳密なDTO検証が成功した場合だけtenant IDと正規表示名を認証storeへ採用する。保存値だけでは認証せず、未確認中のtenant-bound通信を拒否する。

loginの確定拒否、サーバー未認証、結果未確認を区別し、資格情報やmutationを自動再送しない。旧login/logoutのCookie変更可能性だけは、承認済みの安全側への例外として新世代も未確認へ戻しcacheを破棄する。旧応答のユーザー・tenant・成功状態は採用しない。

## 関連・範囲

- U-F13 / TSK-528追補C1。[承認済み計画](plan.md)、[判断・検査資料](step2-review-material.md)。
- C1ステップ1はPR #144、統合SHA `3052e0db743877c7f15c0ec10daa0142cba7ab7e`。
- 今回はC1ステップ2のみ。TSK-528全体、U-F5/TSK-520の実API受入、U-F13残部は未完了。
- C2の応答tenant照合、U-F3の/login画面、U-F13の認証guard・/team公開・実APIブラウザ受入・15経路＋catch-allは含めない。
- 認可、ACL、wire API/DTO、migration、共有凍結資産は変更しない。ステップ1の7.7正式受理を今回の本人確認へ流用しない。

## 正本への反映（7.6）

- [x] 正本影響を確認した（反映なし。計画§2.1）。
- 正本の変更履歴・索引への更新は対象外。関連計画とコミット済みworklogへ接続条件・承認・レビュー結果を反映する。

## テスト・レビュー

最終結果は判断資料へ固定してから、PR本文として利用する。未完了の項目はチェックしない。

- [ ] /check 全グリーン。
- [ ] C1ステップ2の実装・単体検証DoDを満たした。
- [x] Claude反対側一次レビューの指摘対応・採否を記録した。
- [x] codex_run.py review adversarial 済み（第1周全差分、第2周修正差分と影響）。
- [ ] コア領域/検査経路の変更: 人間による逐行確認を実施した
- 実施記録: 対象= 範囲= 方法=

実施記録の値と必須チェックは、確認した本人が記入する。作成者が代記しない。

## コア検出・本人確認の準備対象

意味範囲はtenant分離。機械検出は既登録の`frontend/src/api/*`、`frontend/src/stores/authStore*`等へ突合する。guard_pathsの変更はない。登録追加・検査緩和は不要。

予定対象は`api/auth.ts`、`api/client.ts`、`stores/authStore.ts`と関連6 spec、計画・判断資料・worklog。最終HEADの`origin/develop...HEAD`を、DTO採用、Cookie副作用、epoch、確定拒否、未確認、singleflight、保存値/別タブ、cache破棄、資格情報非再送の試験と突合して逐行確認する。

## 後続の接続条件・制約

- C1がauth/client/storeを一時所有し、C1統合後にC2/U-F3が実基線から引き継ぐ。共有ファイルを並行編集しない。
- C2はC1の破棄境界を維持して応答tenantの照合を追加する。C1だけでtenant応答の一致まで証明済みとは扱わない。
- U-F3は結果のauthEpochを照合し、`stale`/`verification-unknown`を成功表示しない。明示session GETとlogout未確認を扱う。同じepochの未確認結果で重複通知しない。
- 保存値は変更検出候補であり認証根拠ではない。別タブで確認・保存すると他タブも未確認となり得る。共有sessionの最初の呼出元signalを中断すると、待機者も結果未確認となり、明示再確認が必要。
- 実ブラウザの複数タブCookie受入、認証guard・/team接続、実API一覧・登録・編集・再読込の受入は後続。仮tenant・認証迂回で公開しない。

## 現在地導出

最終コミット後の`uv run python scripts/feature_status.py`出力をここへ記録する。

このファイルはPR準備資料。今回push・PR作成・Draft解除・公開・マージは実施しない。

## 品質ゲート未通過・作成前条件

本候補はコード/既定レビューの準備済みであり、全品質ゲートgreenではない。共有環境では既存試験のsubprocess timeout、worker起動・終了timeout、PostgreSQL起動期限を観測した。C1対象の再検査も177試験成功・境界試験worker起動エラーで、全件成功とは扱わない。

現在の規約ではローカル/check未通過でPR作成を進めない。CIで全件検証するためのDraft先行を行う場合は、ローカル全件green前のDraft作成例外とpush/作成の明示承認が必要。既定ゲートを独断でCIへ移さない。本人確認チェック・実施記録は未記入のまま、Draft解除・公開・マージは禁止を維持する。
