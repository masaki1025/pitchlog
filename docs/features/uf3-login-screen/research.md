# U-F3 / C3 調査記録

## 正式カード

- URL: <https://app.notion.com/p/3f493b75e687814ca3c7fead50df2a14>
- タスクID: TSK-518
- タイトル: U-F3 ログイン画面
- 2026-10-14取得時: 未着手、優先度高。
- 元計画: TSK-508 / `docs/features/frontend-impl-units/plan.md`。承認済み単位定義は`design.md`。
- 旧典拠: `dd03160:frontend/src/screens/LoginScreen.tsx`。
- 依存: U-F1、U-F2、U-F6、認証契約U-A1。
- Tコア。正式DoDはplan.md 1節へ転記した。

Notionの担当者プロパティには`user://32cd872b-594c-81c8-8836-0002cb32e4c3`がある。取得結果に表示名がないため氏名は推測しない。2026-10-14の会話で山田正輝がCodex DをC3担当に指名したため、製品着手時にカードとopen PR/worktreeを再照合する。

## 実コード

- `frontend/src/stores/authStore.ts`は共有QueryClient clear、`authEpoch`、`bb.auth`同期を持つ。
- `frontend/src/api/client.ts`は共有Piniaを利用し、Cookie送信と遅延認証応答破棄を持つ。
- `frontend/src/router.ts`に現存するrouteは`/`と`/help`のみ。`/login`のownerはU-F13計画に残す。
- `LoginScreen.vue`と`frontend/src/api/auth.ts`はdevelopに存在しない。

## 正式カードとの差分

従来のU-F13調査では「U-F3正式カード未確認・担当不在」としていた。正式カードは取得でき、Notion担当者プロパティも存在した。会話上のCodex D指名を採用するが、担当者の氏名は未確定であり、着手前の重複再確認を残す。

## C1統合後の再照合（2026-10-18）

基線`493342be37d4383ca572f8d1c826a3f184a4d213`にC1 `auth.ts`の`login` / `session` / `logout` / `ensureSessionVerified`と結果`authEpoch`が存在する。単独session DTOの成功でのみauthenticatedとなり、login ackでは成功を表示しない。U-F3は独自API/DTOやtenant供給を追加せず、この戻り値と共有storeを照合してemitする。

旧典拠はPitchLogの履歴にはないため、ローカル`/home/ymdms/projects/Baseball_Scoring`の固定コミット`dd03160`に対する`git show dd03160:frontend/src/screens/LoginScreen.tsx`から直接確認した。未認証チーム一覧の取得、チーム新規登録、個人アカウント、tokenのJS保存、router遷移とserver detail表示は現行承認契約と両立しないため移植しない。公開ガイドへのrouteはU-F13所有とし、本画面にはroute pathを持ち込まない。
