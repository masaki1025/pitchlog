# C1ステップ2 実装候補・レビュー判断資料

## 対象と現状

- 基線: `3052e0db743877c7f15c0ec10daa0142cba7ab7e`（C1ステップ1 / PR #144統合）。
- 専用worktree: `/tmp/pitchlog-auth-session-verification-contract`。
- 製品候補: 正規auth client、厳密なsession DTO検証、起動時未検証、tenant APIの確認前拒否、世代照合、singleflight、login確定拒否と結果未確認の分離、明示再確認/logout。
- C2・U-F3・U-F13の製品コード、共有凍結資産、ACL、migration、routeは変更していない。
- **未完了**: 敵対レビューP0への契約判断・修正・再レビュー、本人逐行確認。現候補を統合可能とは扱わない。

## 検査

2026-10-17、変更候補に対して次が成功した。

- frontend: Prettier、ESLint、vue-tsc、dependency-cruiser、build（closure conforming）。
- frontend全件: **68ファイル、1,220試験成功**。対象6ファイルは167試験成功。
- root: Ruff、ty、plan/docs同期、docs status（20件・違反0）、design propagation、doc coverage、frozen-baseline invariants、tenant-boundary（基線origin/develop）、diff-check。
- backend製品は変更なし。今回backend全件は実行しておらず、frontendの成功で代用したとは扱わない。
- 実ブラウザの複数タブCookie受入は未実施。mockによるstore/cache世代試験だけでCookie競合を証明したとは扱わない。

## 敵対レビュー第1周（指定wrapper）

`python .claude/scripts/codex_run.py review adversarial -`で静的査読。判定は否決（P0=1 / P1=1 / P2=1）。

| 指摘 | 照合と扱い |
| --- | --- |
| P0: 別タブでBをsession検証後、旧login AのSet-Cookieが到着すると、JSが旧応答を棄却してもCookieだけAへ戻る | 採用。ブラウザのCookie副作用はJS世代チェックでは取消不能。現試験はSet-Cookieを模擬していない。§7の「旧操作は新世代store/cacheを変更しない」と§3の「Cookieが変わり得る時点で破棄」が衝突するため、以下の最小追補を人間判断へ提示する。 |
| P1: 別タブの確認開始時にbb.authを除去するため、元タブの認証/cacheも破棄される | 現行§4項6の明示契約（確認開始でQueryClient clear / epoch増分 / bb.auth除去）どおり。可用性上の制約として明記し、無断で保存/通知契約を変えない。 |
| P2: 中断signal付きsessionの結果未確認が共有され、自動再確認しない | 現行§3.2/3.3のabort→結果未確認・自動再確認禁止どおり。明示session GETで復帰可能。呼出元の中断が共有確認に影響する制約をU-F3へ引き渡す。 |

## Claude反対側一次レビュー

判定は差し戻し（P0=0 / P1=2 / P2=10）。静的差分レビューで、実行検証済みとは扱わない。

- P1-1は敵対レビューP0と同じCookie競合。採用し、以下の最小追補を人間判断へ提示する。
- P1-2はタブ間で認証/cacheを破棄する可用性の指摘。§4項6の確認開始時bb.auth除去と、保存値を認証へ採らない§3.1の組合せを明記した。無断で既存通知・保存契約を変更しない。実ブラウザでの複数タブ受入は未実施。
- P2-1〜4のうち、結果epoch照合、login後session待ちでのsession/logout拒否、loginの壊れたJSON、401/logout後のensure自動再送禁止を試験へ追加。最新auth固有試験は**42件成功**。これは全件1,220成功後の試験追加であり、最終全件完走数を更新したとは扱わない。
- P2-5（signal中断の共有影響）は承認済みの結果未確認/明示再確認契約として記録。P2-6（sessionExpired）はU-F3が公開結果statusと発生操作で表示を区別する。
- P2-7（公開signIn）は既存のtrusted store入口を維持。実製品の呼出元はstrict DTO検証後のauth.tsだけ。未検証tenant-bound通信はclientでも拒否し、任意IDを認証根拠にする新規呼出元を追加しない。
- P2-8のpath記載はauth操作呼出しと通信許可listの異なる責任で、ドメイン計算コピーではない。P2-9のstore生成時cache破棄は確認前に旧データを残さないため意図した境界。P2-10は/team未接続、公開トップはtenant APIを取得しない既存構成を維持し、C1単体で業務画面公開を進めない。
- 指摘反映後の正式差分レビューは未実施。P0の方針承認後、修正差分と上記照合を第2周へまとめる。

## 人間判断を要する最小追補案（未承認）

§7の遅延認証操作に対する条件へ、次の例外だけを追加する。

> 旧login/logoutの成功、またはCookie変更の有無を確定できない結果が新世代より遅れて観測された場合、旧tenant情報は採用せず、Cookieと検証済みtenantの一致が失われた可能性として、新世代も認証未確認にしcacheを破棄する。資格情報の自動再送・sessionの自動再確認はせず、利用者の明示再確認へ進める。Cookie変更のない確定非2xxはこの例外に含めない。

- 新API・DTO・header・ACL・保存形式を追加しない。旧storeの復元も行わない。
- 共通clientの旧応答チェックより前に認証Cookie副作用を扱い、logoutと不確定失敗も同じ境界で検証する案。具体実装は承認後に行う。
- 修正後にCookie副作用の順序を模擬する遅延login/logout試験と、確定拒否が新世代を消さない試験を追加する。実ブラウザ受入はU-F13へ残す。
- C2の応答tenant照合が未統合のため、C1だけで/teamを公開しない。

## 後続の所有と開始条件

- C1: `api/auth.ts`、`stores/authStore.ts`、`api/client.ts`の確認境界と各spec。レビュー指摘収束まで一時所有。
- C2: C1統合後のclientからmetadata照合を追加。既存の承認済みC2固有条件は維持。現時点で実装しない。
- U-F3: C1統合後の`login/session/logout/ensureSessionVerified`と結果型を使う。`stale`は成功表示しない。結果のauthEpoch照合、明示session再確認、logout未確認表示、共有確認の中断影響を引き継ぐ。今回画面は実装しない。
- U-F13: C1/C2/C3成立後に保護routeと/team受入。仮tenant・ガード迂回は禁止。

## 本人逐行確認（未実施）

- [ ] tenant分離コア領域の製品差分を本人が逐行確認した。
- [ ] 試験差分と既存試験の期待値変更が検出を弱めていないことを本人が確認した。
- [ ] 最終HEADと正式レビュー・検査結果を本人が確認した。

対象: `frontend/src/api/auth.ts`、`api/client.ts`、`stores/authStore.ts`と関連6 spec、C1/C2/U-F3/U-F13計画・作業ログ。

範囲: 最終製品HEAD確定後の`origin/develop...HEAD`全差分。現段階は未コミット候補であり最終HEADではない。

方法: DTO strict検査、Cookie変更時点、確定拒否、401/結果未確認、世代・singleflight、保存値/別タブ、cache破棄を試験と突合して逐行確認。正式レビューや7.7受理を本人確認の代わりにしない。
