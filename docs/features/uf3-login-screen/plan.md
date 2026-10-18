---
feature: uf3-login-screen
status: active
承認: 済(2026-10-14・山田正輝)
重さ分類: コア領域
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-uf3-login-screen
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

### 3.1 影響する正本

要件・設計・ADR・開発・運用の正本は反映なし。本PRは承認済み認証契約を画面へ接続する実装追随であり、API/DTO/権限/共有凍結資産を変更しない。

正本体系外だが同一PRで更新するもの: `frontend/src/screens/LoginScreen.vue`、固有spec、本計画・research・pr-preparation、固有worklog。core pathの宣言/登録はU-F13側の承認済み統合順で扱い、本PRに無断追加しない。

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


### C1依存の更新（2026-10-17）

C1ステップ1はPR #144 / develop `3052e0db743877c7f15c0ec10daa0142cba7ab7e`へ統合済み。C1ステップ2（正規auth clientと検証済みstore）はCodex Dが同専用worktreeで実装中であり、C1全体の開始条件が成立したとは扱わない。`api/auth.ts` / `authStore.ts`と、最小追随中の`api/client.ts`はC1が一時所有し、統合後の基線から後続が再照合する。本計画の製品実装は今回開始しない。

### C1遅延Cookie追補の接続条件（2026-10-17）

山田正輝がC1の安全側への例外を承認した。旧login/logoutのCookie変更可能性を観測した場合、新世代も`verification-unknown`へ戻しcacheを破棄する。旧ユーザー/tenant/成功は採用せず、tenant-bound通信を止め、明示session GETだけで再確認する。資格情報やmutationの自動再送は行わない。UIは`stale`だけでなく新世代の`verification-unknown`も成功として扱わず、結果epochを照合する。C2はこの破棄境界を維持して業務operation前の応答tenant照合を追加する。C1が共有client/storeを一時所有し、統合後に後続が基線から引き継ぐ。今回C2/U-F3/保護routeの製品実装は行わない。

### C1統合後の実装再開（2026-10-18）

山田正輝がPR #147統合後のC2/U-F3実装・関連試験・既定レビュー・PR準備を承認した。開始基線は実統合SHA `493342be37d4383ca572f8d1c826a3f184a4d213`。以前の最初のステップのみという停止条件は今回の指示に従い更新し、各ステップの検証とコミット分離は維持する。本人逐行確認・公開・マージは含まない。

U-F3編集所有は`LoginScreen.vue`、固有spec、本計画・research・固有作業ログ。C2が共通clientを所有し、C1の`auth.ts`・storeと共有providerは再利用する。route登録・redirectはU-F13所有であり、U-F3にはrouter依存を追加しない。新規画面のcore path登録は親セッションの承認順序で扱い、未登録の機械検出を合格扱いにしない。

ステップ1は正規auth clientを接続した画面と基本・境界18試験を実装した。検査結果は固有作業ログへ記録する。ステップ2では追加の遅延logout・複数世代・存在秘匿・移植4点とアクセシビリティを確認し、レビューおよび本人確認の対象欄を用意する。正式DoD・人間確認は未完了のまま維持する。

### U-F3ステップ2の候補成果（2026-10-18）

製品の認証成功条件をauthEpoch・C1認証済み状態・tenant ID一致に限定し、team_nameを認可キーにしない。正規client/storeを通す固有24試験、全frontend 69 files / 1,261 testsが成功した。型・ESLint・Prettier・buildも成功。旧典拠の移植4点と正式レビュー/本人確認の対象をresearchへ記録した。正式レビュー・本人逐行確認・親のcore path登録とU-F13実API/DB接続受入は残るため、本計画全体・TSK-518の完了とは記録しない。

### 正式コードレビューと最終追随（2026-10-18）

正式2経路を各2周実施。第1周P2 4件・第2周P2 4件は全採用した。第2周後の最終差分はstatusのbusy対象外配置、darkラベル、focus先、handler感度試験と資料に限定する。固有試験数は24→28→30件へ増えた。各時点の全件数は作業ログへ保持し、古い検査結果を最終候補成功の代用にしない。第3周は行わず、最後の採用反映は未再レビューとして本人逐行確認対象に残す。


### 最新developでの全件再検証と残条件（2026-10-18）

PR #143実統合`156dd139a893845428a1ecab69632143f7694e0b`を通常mergeし、固定検査HEADは`a4b982441b25b260a4532b5148bc8fb1c08166d7`。消失した旧/tmp worktreeのコミット済み成果をディスク側へ復元した。C1/#119/#143と共有資産の統合待ちは解消済みで、550/D4/544/545は本画面の依存ではない。

最新基線でfrontend69ファイル1,267成功、root全29,670成功/2 skip、backend全2,574成功/4 skip。root/backendは別々の専用使い捨てPostgreSQLで実行しcleanupを確認、型/lint/整形/build、境界/凍結不変量/認可catalog/文書同期も成功。製品/specの2blobをSHA-256で固定しており、以後の記録追随で変更しない。

既定2経路各2周の採否と最終反映未再レビューは保持する。意味範囲Tに対するLoginScreen*の機械未登録は残っているため、全品質ゲート通過・TSK-518全体完了・本人確認実施済みと記録しない。追加1パターンの最小追補は依頼者回答待ち。共通clientはC2、router/App/登録資産はU-F13で順次編集し、本U-F3の画面/specと二重編集しない。C1相関の新候補は別の未承認局所追補であり、本PRの既存UIへ無断実装しない。


## LoginScreenコア登録の承認追補（2026-10-18）

山田正輝が`frontend/src/screens/LoginScreen*`をtenant-isolationへ登録すること、D自身の固定C2/U-F3候補を専用検証worktreeで結合すること、現承認範囲の通常push/Draft PR作成を承認した。既存対象の削除・本人確認代記・公開・マージは含まない。login/session相関の新契約は未承認のまま。

コア3ファイルの一時編集所有はU-F3→U-F13。U-F3の本PRに宣言/固有試験を先行コミットし、その後JSON登録を別コミットで行う。既存の回転式追加層と登録済みRG1/U-F5/U-F6/U-F8の履歴検証を再利用する。登録後はLoginScreen製品/spec2件の検出、本人未記入拒否、基線・全core試験を確認する。既定レビュー周回は増やさず、追加登録/試験差分は未再レビューの本人対象として明示する。

正本変更なし。正本外の同梱追加対象は`.claude/core-areas.json`、`scripts/core_guard.py`、`tests/test_core_guard.py`。承認済み2ステップのうちレビュー準備の追補として扱い、別の製品機能を増やさない。


## 登録後の全件完走とDraft提出（2026-10-18）

固定候補ea1b3bda681b689c9b8fe1b56fae7dce8f9d5d7fのroot全件は29,672成功/2 skip、1500.71秒、exit0で完走し専用clusterを撤去。Ruff/ty、core264、基線/2製品検出/本人未記入拒否も成功。製品2blobとbackendは従来の最新基線検査から不変のため、frontend1,267成功/backend2,574成功4 skip・型/lint/整形/buildの結果を保持し理由なく再実行しない。

承認済み部分のDraft提出準備としてin-reviewへ移す。既定レビュー上限後のcore3ファイル/試験とUI最終反映は未再レビューの本人対象。全差分9ファイルの対象/範囲/方法欄を空で提示し、C1の本人確認は流用しない。経路接続・実画面/API/DB受入・TSK-518全体・公開・マージは未完了。新C1相関契約は未承認。台帳への追記なし（既存追加層の承認済み登録と局所是正で、確定した新運用傾向/新ハーネスなし）。


## 2026-10-18 承認済み相関追補へのUI追随

04ecb061比較資料の本会話承認に従い、認証相関の失敗理由と回復方法を追加する。storage/lock非対応では資格情報操作を止め、保存許可/対応ブラウザ/HTTPSで開き直してreloadする案内を表示する。lock busyは操作終了後の明示操作だけ。別タブで意図が変わった旧タブは明示再loginを要求し、sessionだけで新tenantを自動採用しない。本候補単独の旧C1には相関保証を主張せず、新相関clientと結合した検査を別に記録する。旧レビュー各2回は消費済みのまま、今回差分は新相関追補のレビュー対象として明記する。
