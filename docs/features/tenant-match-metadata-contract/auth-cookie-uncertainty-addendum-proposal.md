# C1 Cookie不確実性の最小追補案（未承認・未実装）

## 対象と変更しない既済み事項

基線はPR #147統合SHA `493342be37d4383ca572f8d1c826a3f184a4d213`。C1ステップ2は当時の承認済み契約を満たして完了しており、その受理・本人確認を再審査に戻さない。本案は既存計画への局所追補候補であり、新しい全体計画ではない。Cookieを更新し得る旧session/保護応答の競合だけを扱い、認証期限・backendのCookie規則・API/DTO・ACL・凍結資産は変更しない。

## 原因と新たな許可が必要な差分

`require_tenant_access`は提示値を再度Set-Cookieへ設定する。ブラウザはJSの世代検査より前にCookieを適用するため、Aの旧応答がB login後・B session確認前に届くと、Bの確認がCookie Aを使う場合がある。現在のC1の例外は旧login/logoutに限られ、C2の7経路の本文/operation拒否だけではこの順序を解消しない。

**追加する許可は安全側の無効化だけ**。旧tenant/user/本文/成功を新世代へ採用しない。資格情報・mutation・sessionの自動再送を行わない。

## 候補契約

| 項目 | 確定候補 |
| --- | --- |
| 追加対象 | `GET /auth/session`とC2の正規roster関数が使う7tenant-bound経路だけ。その他業務APIへ拡張しない |
| 検出点 | response headers受領時、またはfetchがHTTP結果未確認で終了した時。JSからSet-Cookieを読める前提にしない |
| 世代条件 | 要求開始時epochと、当該検出点でstorage同期後のepochが異なる場合だけ。現世代session/rosterの正常応答を自分で未確認化しない |
| Cookie変更なしの確定応答 | 401は既存middlewareが更新Cookieを付けず、既存error handlerもCookieを付けないため対象外。その他statusは、対象経路ではCookie更新の可能性があるものとして保守的に扱う。旧401で新sessionを失効させない既存規則を維持する |
| 本文遅延 | headers観測時には同世代で、その後の本文読取り中だけ世代が変わった場合、旧本文を破棄する。Cookieはheaders以前に適用済みであり、この本文遅延だけで新世代を追加無効化しない |
| 通信結果未確認 | 対象fetchのnetwork/abort失敗で開始epochが古ければ、Cookie変更の有無を証明できないため未確認化する。変更要求は自動再送しない |
| 状態変更 | 新世代のteamId/teamName/sessionVerifiedと共有query cacheを破棄し、epochを更新して認証未確認にする。旧応答の確定情報を流用しない |
| 明示再確認 | C1の明示`session()`だけで再確認する。route guard/画面mountの`ensureSessionVerified()`から自動GETへ進ませない |
| 冪等性 | 同一HTTP要求がheaders/本文失敗など複数経路から観測されても通知・cache破棄は1回。同じ要求の重複観測と、別要求が後からCookieを再変更する可能性を混同しない |
| 例外 | 旧sessionは既存ApiStaleAuthError、旧rosterはC2のApiTenantVerificationErrorとして棄却。結果未確認を成功へ昇格させない |

## 実装境界案

所有はCodex D。C2が単一clientを所有し、U-F3はLoginScreenを所有する。共通auth client/storeは統合済みC1を再利用し、コピーしない。

- `api/client.ts`：追加対象と検出点を固定し、要求単位の通知済みフラグを持つ。C1の既存login/logoutフックは保持し、一般呼出し側が認可規則を上書きするoptionを作らない。
- `authStore.ts`：安全側無効化の専用actionと、明示再確認が必要であることを保持するruntime状態を最小追加する。team/成功は引数として受け取らない。storageに検証済み認証を新規保存しない。
- `api/auth.ts`：上のruntime状態では`ensureSessionVerified()`がverification-unknownを返し、明示`session()`だけが確認を開始する。進行中session/login/logoutは元のepochに結び付け、後着旧結果を採用しない。
- 固有spec：client/auth/store、TeamScreen/TeamMembersContent、LoginScreenの接続試験へ必要最小限を追随する。router/AppはU-F13の所有を維持する。
- C1/C2/U-F3/U-F13の接続記録と作業ログへ採否・所有・検査結果を同期する。backend製品・共有core3ファイル・認可資産は本案で変更しない。

## 合格条件

1. Aのsession/7経路応答headersをB login前・login後session前・session確認後へ動かし、Cookie変更可能な旧応答では未確認化、旧情報採用0、cache/tenant通信0になる。
2. 現世代headers後の本文だけの遅延では追加無効化せず旧本文だけを棄却する。旧401では新sessionを維持する。
3. network/abort、複数世代、session再確認との前後競合を検査する。同じ要求の通知/破棄1回、異なる旧要求が後から到着した場合の安全性を両立する。
4. 未確認のguard/mount/明示再確認を分け、自動session GET・資格情報/変更要求の自動再送0、明示GETのみで回復する。
5. frontendの全型/lint/format/Vitest/build、既存core/frozen検査、反対側・敵対レビュー、人間逐行確認を維持する。既存の本人回答を新差分の確認へ流用しない。

本案の正式採否前には製品へ反映しない。U-F13の実画面/API/DB競合受入は、本案の採否と接続条件が確定した後に行う。
