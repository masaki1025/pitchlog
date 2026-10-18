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

## 移植4点の照合

固定旧典拠`dd03160:frontend/src/screens/LoginScreen.tsx`と現行LoginScreenを、現行計画の優先順位で照合した。

| 観点 | 維持した内容 | 現行契約に基づく差分 |
| --- | --- | --- |
| 文言 | 野球スコアリング／チームの試合記録を、1球ずつすばやく／チーム名／パスワード／例: 筑波大学／ログイン | セルフチーム登録・個人アカウント選択を除去。server detailを固定拒否/一般rate案内へ置換し、session未確認・明示再確認・logoutを追加。公開ガイド経路はU-F13所有。 |
| DOM・部品 | 中央配置の外枠→max-w-sm→form→ブランド見出し→label付き入力→Button。Vueの`v-model`/`@submit.prevent`へ変換。lucideのLogInをVue部品で使用 | チーム一覧selectは主体の存在非漏洩のため取得しない。入力のみ。登録/個人入力を除去。router import/直接遷移をemitへ置換。 |
| 主要class | min-h-dvh／items-center／justify-center／bg-slate-50／p-4／max-w-sm／rounded-3xl／border／p-6／shadow-sm／dark色、入力min-h-12／rounded-xl／px-3、Button primary w-full | 状態の固定文言に既存alert色classを継承。確認中はrole=status、formにaria-busy、必須入力とautocompleteを追加。 |
| 操作結果 | Enter/form submit、二重送信防止、入力必須、ログイン操作 | login ack・token保存・navigate成功を廃止し、C1正規session DTO検証とepoch/tenant一致後だけauthenticated emit。未確認時に自動再送せず、明示GETまたは正規logoutだけを呼ぶ。 |

team_nameは画面表示用データであり、emitの認可・tenant一致判定はC1の認証済み状態・authEpoch・tenant IDだけを用いる。UIで独自の資格情報・DTO検証・tenant供給・Cookieアクセスを行わない。未確認状態からtenant GET/POSTがfetchへ到達しないことをC1実体を通した追加試験で確認した。

## レビュー・本人逐行確認対象

- 製品: `frontend/src/screens/LoginScreen.vue`（認証状態、C1呼出し、epoch/tenant一致、固定表示、資格情報破棄、emit、HTML escape）。
- 試験: `frontend/src/screens/LoginScreen.spec.ts`（正規client/store統合、旧session/login/logout、複数世代、未確認tenant GET/POST拒否、二重操作、再生成、unmount、存在秘匿、label/autocomplete）。
- 資料: 本計画・research・`docs/worklog/2026-10-18-uf3-login-screen.md`。
- core path宣言・登録は親セッションで別コミット。未登録のまま機械検出を通過扱いにしない。
- [x] 反対側レビュー実施（2周。最終P2採用反映後は未再レビュー）。
- [x] コア敵対レビュー実施（2周。最終P2採用反映後は未再レビュー）。
- [ ] 本人逐行確認。
- 本人確認の対象: 未記入。
- 本人確認の範囲: 未記入。
- 本人確認の方法: 未記入。推定で記載しない。

## 第1周レビュー採否と影響（2026-10-18）

指定wrapper adversarialは可決P0/P1/P2=0、実Claude反対側は可決P0=0/P1=0/P2=4。両経路とも人間逐行確認の代替ではない。Claudeの4件は全採用した。

1. 明示session再確認401は、資格情報拒否と混同せず未認証のidleへ戻す。login→session401の固定拒否は維持する。
2. authenticated emit後は世代が変わるまでフォーム/submitを止め、親遷移前の再送・二重emitを抑止する。
3. status/liveを常設し、操作完了後は固定alertか入力へfocusを戻す。unmount/別操作/認証済み時はfocusを移さない。
4. pending中に入力イベントを再現して再submitし、DOM disabledだけに依存せずhandlerが拒否する試験へ強化。submitのblockedガードだけを一時除去する故障注入で当該試験が失敗し、元へ復元した。通常試験に除外・timeout変更はない。

未検証記録2点も実コードと照合した。`backend/src/pitchlog/api/schemas/auth.py`の`LoginRequest`はteam_name/passwordとも制限なしのstrであり、`authz/team_login.py`もstr型だけを検査している。旧UI由来のmaxlength50/128は契約にない制限のため除去し、51文字/129文字を切り詰めず正規clientへ渡す試験を追加した。新しい入力上限を追加したものではない。

副題の旧`text-slate-400`を`text-slate-600 dark:text-slate-400`へ変更した。Tailwind既定sRGBの明背景（白）に対するslate-400は2.56:1、slate-600は7.58:1、暗背景slate-900に対するslate-400は6.96:1（WCAG相対輝度式）。この可読性差分を移植4点のclass例外として記録する。

## 第2周採用反映と未再レビュー範囲

親セッションが第2周の4件（adversarial P2 1・Claude P2 3）を全採用した。常設statusをbusy formの外へ移し、認証済みsubmit試験もdisabledを除いた遅延入力からhandlerの拒否を確認する。暗色ラベルへ`dark:text-slate-400`を追加し、空チーム名でidleへ戻る場合のfocus先をチーム名へ修正した。認証済みsubmitガードを一時除去した故障注入で追加試験が失敗し、元へ復元した。

第2周後の製品差分はstatus位置、ラベル2箇所のdark色、focus先条件のみ。C1呼出し・epoch/tenant一致・旧Cookie安全側無効化・自動再送禁止は不変である。固有試験は30件成功。第3周は実施せず、これら最終差分と試験・記録を未再レビューとして本人逐行確認対象へ残す。常設statusをform外へ置くDOM差と、その空状態の余白は移植4点のアクセシビリティ例外に含める。実支援技術での読み上げは未実施であり、DOM構造試験の成功を実支援技術受入と同一視しない。
