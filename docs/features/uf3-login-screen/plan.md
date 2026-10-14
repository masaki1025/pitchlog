---
feature: uf3-login-screen
status: active
承認: 済(2026-10-14・山田正輝)
重さ分類: コア領域
worktree: /tmp/pitchlog-uf3-login-screen
notion: https://app.notion.com/p/3f493b75e687814ca3c7fead50df2a14
branch: feature/uf3-login-screen
created: 2026-10-14
計画レビュー周回: 2
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書案: U-F3 ログイン画面（TSK-518 / C3）

## 1. 正式カード照合

- 正式カード: [TSK-518 U-F3 ログイン画面](https://app.notion.com/p/3f493b75e687814ca3c7fead50df2a14)
- 2026-10-14取得時の状態: 未着手、優先度高。Notionの担当者プロパティにはユーザー識別子があるが、表示名は取得結果から確定できないため推測しない。
- 本会話で山田正輝がCodex DをC3担当に指名した。カードの担当表示との差異は製品着手前に再確認し、他担当worktree/PRがあれば競合を避ける。
- 正式依存: U-F1、U-F2、U-F6、認証契約U-A1。
- コア判定: T（テナント分離）。S/G/R/Dは非該当。

正式DoDは次の7点である。

1. FR-033に従い、拒否理由からチーム名・認証主体の存在を推測できない。
2. React→Vue移植規則と逐語性の4点判定に従う。
3. 利用者入力は自動escapeし、生HTMLを使わない（NFR-023）。
4. 計画で5コア領域を判定する。
5. 横断要件をDoDに含める。
6. コア領域として反対側/adversarial reviewと人間逐行確認を行う。
7. Vitestを伴う（NFR-019）。

## 2. 目的と経路所有

C1の正規auth clientを使い、チーム名・パスワードの入力、認証状態の遷移、失敗表示を持つ`LoginScreen.vue`を経路未登録で実装する。

- C1所有: `frontend/src/api/auth.ts`、起動/session verification、U-F2 store追随。
- U-F3所有: `LoginScreen.vue`、認証状態/失敗表示、Vitest、成功時の`authenticated` emit。C1の正規auth clientを呼び、通信契約を重複実装しない。
- U-F13所有: `/login`と`/team`のroute、safe redirect query、global guard、`RouterView`の`authEpoch` key、成功emit後の遷移。
- `LoginScreen.vue`はvue-routerをimportせず、route pathやredirect queryを解釈しない。
- U-F13の15経路+catch-allは本計画に含めない。

## 3. 開始条件

1. 本計画のadversarial reviewと人間承認が完了している。
2. PR #119とC1がdevelopへ統合されている。
3. 最新developで正式カードの担当重複、C1 client/store API、U-F1 UI部品、U-F6 error型を再照合している。
4. U-F13のrouteはまだ接続しない。C3の製品PRは経路未登録で完結する。

## 4. 認証状態と表示

| 画面状態 | 表示・操作 |
| --- | --- |
| idle | チーム名・パスワード、送信。passwordを保存・log出力しない |
| submitting | 二重送信を止め、結果を断定する表示を出さない |
| verifying | Cookie発行後のsession確認中。tenant画面へ遷移せず、旧store/cacheはC1契約で破棄済み |
| rejected | 401/認証拒否を固定文言で表示。チーム名の有無、パスワード誤り、tenant状態を区別しない |
| rate-limited | 契約済みの一般案内だけを表示し、存在を推測できる情報を出さない |
| verification-unknown | session/network/DTO不正等。ログイン成功・失敗を断定せず、「状態を再確認」「ログアウトしてやり直す」を提示 |
| authenticated | C1のsession 2xx後だけ`authenticated` emit。遷移はU-F13が所有 |

資格情報の自動再送を行わない。sessionの明示再確認とlogoutはC1の正規操作だけを呼ぶ。logout結果未確認を完了表示しない。遅延応答が新しい`authEpoch`を変更した場合は旧結果を表示しない。

## 5. 移植とUI境界

- 旧`LoginScreen.tsx`の情報構造、ラベル、主要Tailwind class、form submit挙動を固定コミットと照合する。
- Vue変換は`@submit.prevent`、`v-model`、型付きemitを用いる。旧React固有コードをコピーしない。
- 逐語性の4点は、文言、DOM/部品構造、主要class、操作結果を旧典拠・現行要件・Vue変換規則の3者で照合する。認証契約と存在秘匿に反する旧挙動は現行契約を優先し差分を記録する。
- 利用者入力はVue補間/value bindingだけで扱い、`v-html`、生HTML、passwordの永続化、Cookie/tokenのJavaScript露出を行わない。
- U-F1の既存UI部品と共有Pinia/QueryClientを再利用する。

## 6. 実装ステップ

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 正規auth clientを接続した経路未登録`LoginScreen.vue`、状態遷移、基本Vitestを実装する | login→session 2xxだけauthenticated emit。401は固定拒否、sessionの非401失敗は結果未確認。二重送信・自動資格情報再送なし。遅延応答は新認証を変更しない。旧store/cache破棄はC1だけを利用。router import/仮tenant/独自DTOなし。型検査・lint・format・Vitest・build green |
| 2 | 正式DoD、移植4点、失敗・遅延境界のVitestとUI調整 | LoginScreenの直接mount/再生成時のsession再確認、存在秘匿、NFR-023、明示再確認、logout未確認、A→B遅延応答、accessibilityを試験。実`/team` reloadはU-F13所有。frontend品質gate green。反対側/adversarial reviewと人間逐行確認記録欄を用意 |

各ステップは別コミットとし、人間が承認したステップだけを実装して停止する。

## 7. DoD

- [ ] 正式カードの7 DoDを満たす。
- [ ] 認証拒否からチーム名・主体・tenant状態の存在を推測できない。
- [ ] session非401失敗を未認証と同一表示にせず、成功とも表示しない。
- [ ] 検証済みtenant情報はC1だけから取得し、入力値をtenant IDへ変換しない。
- [ ] 遅延login/session/logoutが新しい認証状態・cache・表示を変更しない。
- [ ] route登録とredirect処理を含まず、U-F13所有境界を守る。
- [ ] password、Cookie、token、header値を保存・表示・log出力しない。
- [ ] Vitest、型検査、ESLint、Prettier、build、コアレビュー、人間逐行確認を通す。

## 8. 人間承認が必要な判断

1. U-F3をCodex Dの経路未登録先行分割として所有し、U-F13がroute/redirectを所有すること。
2. 4節の状態と失敗表示を採用し、C1の401と結果未確認の区別を画面へ反映すること。
3. 成功境界をlogin 2xxではなくC1 session 2xx後の`authenticated` emitとすること。
4. 逐語性の4点を5節の方法で照合し、現行認証契約を旧挙動より優先すること。
5. 承認後の開始は、#119とC1統合後の **ステップ 1/2 のみ**とすること。

## 9. レビュー状態

正式カードは取得済み。U-F13計画の最終P1反映と後追加のC1/C2/C3契約案は未再レビューだった。2026-10-14の追補横断adversarial review第1周はP0 2 / P1 6 / P2 0（うちC3はP1 1）。採用し、ステップ1へ基本Vitestと品質gateを移した。反映差分の再レビュー後に人間承認を求める。

第2周はP0 2 / P1 2 / P2 0。C3固有の新規指摘はなく、C1/U-F13との境界追随としてreload試験をLoginScreen直接mountへ限定した。P1追随差分は回数上限により未再レビューのまま人間確認へ出す。

第3周はC1/C2のP0反映限定でP0 0。C3は対象外であり、第2周P1追随差分が未再レビューである残余を維持する。

## 10. 人間承認記録

2026-10-14、山田正輝が計画HEAD `e42a2ddbd2db58dd1fca642959ff4a2870299f63` の本計画とCodex D担当を承認した。#119とC1がdevelopへ統合され、所有重複を再確認した後も最初のステップだけを実装して停止する。第2周P1追随の未再レビュー範囲は人間逐行確認対象として維持する。
