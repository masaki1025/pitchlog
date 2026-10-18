# C1ステップ2 実装候補・レビュー判断資料

## 対象と現状

- 基線: `3052e0db743877c7f15c0ec10daa0142cba7ab7e`（C1ステップ1 / PR #144統合）。
- 専用worktree: `/tmp/pitchlog-auth-session-verification-contract`。
- 製品候補: 正規auth client、厳密なsession DTO検証、起動時未検証、tenant APIの確認前拒否、世代照合、singleflight、login確定拒否と結果未確認の分離、明示再確認/logout。
- C2・U-F3・U-F13の製品コード、共有凍結資産、ACL、migration、routeは変更していない。
- **実装・契約追補は反映済み**。第2周の正式レビューは両系列可決。最終検査と本人逐行確認は別であり、現候補を公開・マージ可能とは扱わない。

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
- P2-1〜4のうち、結果epoch照合、login後session待ちでのsession/logout拒否、loginの壊れたJSON、401/logout後のensure自動再送禁止を試験へ追加。当時のauth固有試験は**42件成功**。これは全件1,220成功後の試験追加であり、最終全件完走数を更新したとは扱わない。
- P2-5（signal中断の共有影響）は承認済みの結果未確認/明示再確認契約として記録。P2-6（sessionExpired）はU-F3が公開結果statusと発生操作で表示を区別する。
- P2-7（公開signIn）は既存のtrusted store入口を維持。実製品の呼出元はstrict DTO検証後のauth.tsだけ。未検証tenant-bound通信はclientでも拒否し、任意IDを認証根拠にする新規呼出元を追加しない。
- P2-8のpath記載はauth操作呼出しと通信許可listの異なる責任で、ドメイン計算コピーではない。P2-9のstore生成時cache破棄は確認前に旧データを残さないため意図した境界。P2-10は/team未接続、公開トップはtenant APIを取得しない既存構成を維持し、C1単体で業務画面公開を進めない。
- 指摘反映後の正式差分レビューは未実施。P0の方針承認を受け、修正差分と上記照合を第2周へまとめる。

## 最小追補（承認済み・2026-10-17）

§7の遅延認証操作に対する条件へ、次の例外だけを追加する。

> 旧login/logoutの成功、またはCookie変更の有無を確定できない結果が新世代より遅れて観測された場合、旧tenant情報は採用せず、Cookieと検証済みtenantの一致が失われた可能性として、新世代も認証未確認にしcacheを破棄する。資格情報の自動再送・sessionの自動再確認はせず、利用者の明示再確認へ進める。Cookie変更のない確定非2xxはこの例外に含めない。

- 新API・DTO・header・ACL・保存形式を追加しない。旧storeの復元も行わない。
- 共通clientの旧応答チェックより前に認証Cookie副作用を扱い、logoutと不確定失敗も同じ境界で検証する案。承認に基づき実装した。
- Cookie副作用の順序を模擬する遅延login/logout試験と、確定拒否が新世代を消さない試験を追加する。実ブラウザ受入はU-F13へ残す。
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

## 承認反映・差分レビュー候補

2026-10-17、山田正輝が上記例外を承認。旧login/logoutから新世代へ採用する情報は「認証未確認」の無効化だけとする。実装は`onAuthCookieUncertain`をlogin/logout専用に制限し、2xx headers/HTTP未確認失敗で一回だけ呼ぶ。旧世代の判定は無効化前に確定し、旧成功へ昇格させない。logoutは現世代が既に確認待ちなら同じ応答で再破棄しない。正式第2周・最終検査結果は後記する。

## 正式第2周・採否（2026-10-17）

- 指定wrapperの敵対差分レビュー: **可決 P0=0 / P1=0 / P2=0**。修正差分と影響範囲を静的確認。実テストはレビュア未実施。
- Claude反対側差分レビュー: **可決 P0=0 / P1=0 / P2=2**。2指摘とも採用。
  - P2-1: 旧応答は本文を読まないことを試験名とassertで明示し、別に現世代login/logoutのheaders成功後本文失敗でも破棄が一回である試験を追加した。
  - P2-2: 本資料冒頭の古い未承認状態・最新件数という表現を修正。過去の成功件数は履歴として保持し、最終結果は別に固定する。
- 第2周の件数外参考（世代照合の二箇所・mutation mapの単一entry）は静的に照合した。request開始前のauth epoch取得にawaitはなく、現行のprod経路では一致する。map上書きがあっても旧Cookie変更は各entryで無効化し、sessionの世代照合・未確認記憶が旧tenantの採用を拒否する。製品を変更せず、複数世代試験で境界を確認する。
- 第3周は行わない。P2反映は試験・記録だけで製品コードに変更なし。既定のレビュー枠内で収束し、未解決P0/P1や新しい仕様裁定はない。本人逐行確認は未実施。

## 全件検査の未通過（候補保全時点）

- 製品3ファイルは第2周manifestと一致。コード・試験は候補としてコミット保全するが、計画はactive、ステップ2の全DoD成立・統合可能とは宣言しない。
- rootの全件第1実行: 25,605 passed / 2 skipped / 1 subprocess timeoutで中断。該当core-guard1件の単独再検査は成功。第2実行（2並列）は12,684 passed / 2 skippedで直列化のため中断。どちらも全件完走ではない。
- backend専用DB全件: 2 failed / 12 passedで中断。game_state/authentication migrationの使い捨てPostgreSQLが既存60秒起動期限に達した。単独診断でも同じ起動期限。共有試験ロールの既存状態にも依存できないため、他担当のDB/ロールを変更しなかった。backendソース・試験は基線と同一。
- frontend全件: 1 failed / 1,156 passed / worker起動4 errors。StrikeZoneの既存timeoutとworker起動/終了エラー。対象6ファイル再検査は5ファイル177 passed / authStore境界worker起動1 error。直列再実行でも既存domain-sql試験のtimeoutを観測し、全greenは未達。
- `/check`成功・CI成功・本人確認済みとは記録しない。PR準備本文は`step2-pr-draft.md`。ローカルgreen前のDraft先行例外は未承認で、push/PR作成は行わない。

## 本人確認用の固定対象

製品コミットは`1fea2c60f04f9c50c882298042b5a0458dd5879a`（検証待ち）。製品3ファイルのSHA-256は`step2-review-manifest.json`と一致し、正式第2周後の製品コード変更はない。全検査待ちを隠すための完了宣言はしない。

機械検出は基線JSONと一致し、`api/client*`はsync-protocol/recording-rights/tenant-isolation、残るauth/roster/storeの差分はtenant-isolationに該当。製品・試験9ファイルすべてを検出し、guard_paths変更なし。production core_guardを実HEAD/基線・本人チェック未記入のPR本文で実行し、9ファイルすべてを拒否することを確認した。領域別基線検査は成功。人間のチェックを代記して成功させていない。

wire API/DTO・認可・registry・凍結資産に差分がないため、今回の新しい7.7正式受理対象はない。契約追補の承認やレビュー可決は本人逐行確認の実施記録ではない。PR作成も未実施。

## 最新の検証結果と停止点

- frontend直列全件: **68ファイル、1,236 passed / 1 failed**。失敗はC1対象外のdomain-sql再帰拒否試験の既存timeout。この実行ではC1対象6ファイル・184試験も成功した。失敗した1件の単独再検査は成功（1 passed / 非対象14 skipped、3.68秒）。これは単一の全件green実行ではない。
- 最新auth.specのPrettier/ESLintは成功。型・全体lint/format・dependency-cruiser（81 modules/142 edges）・build/closureは前記成功を維持し、製品コードに変更なし。
- 更なるfrontend全件でもGameScreen/sync等のworker終了timeoutが繰り返されたため中断した。実行を完走・成功に数えない。他担当のプロセスは停止せず、C1の追加全件実行は止めて記録を保全した。
- 最終fetchでもdevelopは`3052e0db743877c7f15c0ec10daa0142cba7ab7e`。製品コミットは`1fea2c60`、後続は検査記録だけ。本人確認の対象は最終HEADの基線からの17ファイル全差分（製品3・spec6・計画/記録8）。
- 未解決はローカル/checkの単一全green未達と本人確認。Draft先行例外の承認待ちであり、push/PR作成・公開・マージは未実施。必要なCI検証を承認なしに省略・移設しない。

## 2026-10-18 Draft先行の正式承認と新基線

山田正輝がC1ステップ2に限るpr手順2.4のDraft先行例外、通常push・Draft PR・CI・資料更新を承認した。これにより前日の「未承認」の停止条件だけを解消する。本人確認・全品質ゲート通過・ステップ2完了ではない。

最新基線は#146の実統合SHA ce0c0e8697252a89bce0c57e69b4821e0a6cac2b（#145も含む）。merge追随の競合はなく、正式第2周製品hashと一致。新基線の正本/受理資産をC1独自に変更しない。

#146はroot/backend conftestで起動する。明示TMPDIR/--basetempによる手動配置の成功だけを#146適用証跡にはせず、専用PITCHLOG_PYTEST_TMPDIRから実pytestのtmp_pathを照合する。backend配線1件は成功し、実体はhome側ディスクの`.../backend/pytest-of-ymdms/pytest-1/test_tmp_path_is_under_bootstr0`に作成された。root全件は専用領域・4 worker（子のautoも4）で進める。

環境timeoutと製品不具合を区別して記録し、試験除外や既存timeout変更はしない。Draft提出に合わせたin-reviewは検査待ち状態を示すもので、完了宣言ではない。

## Draft #147提出後の検査状況

初回PR CI 39094298692のfrontendは68ファイル・1,237 passed、型/lint/dependency/build/closureも成功。旧環境のtimeoutは再現していない。ローカルroot全件は専用領域・4 workerで実行中、backend配線試験は1 passed。通常PR CIのbackend skipは全件検証の成功ではないため、最終HEADで既存workflow_dispatchを使用する。

secrets検出2件は公開ソースhashであり、同一コミットのblobから機械照合済み。人間判定が必要な限定登録の候補は[判断資料](step2-gitleaks-decision.md)へ分離した。判定待ちのまま秘密検査の設定を変更しない。core-guardによる本人未チェックの9ファイル拒否は別の必須条件として保持する。最終確認対象は基線からの18ファイル全差分（製品3・spec6・計画/資料/作業ログ9）。

レビュー採否は第2周から変わらず、製品3ファイルhashも一致。検査途中の状態をステップ2完了とは扱わず、最終HEADのCIリンク・完走件数・未通過はPR本文とコメントへ固定する。

## 本人確認完了回答と追加差分

山田正輝がHEAD a3934fb7283f194ba5544e542bbddc056ff9645bの全18ファイルを本人逐行確認済みと回答した。対象・範囲は同HEADの全差分、方法は未申告（推定記入なし）。本文の過去の未実施記録は履歴として保持し、現時点の未完了条件には戻さない。

同回答による追加は、公開ソースhash2 fingerprintの限定登録と理由コメント、および計画/判断資料/作業ログ/PR資料の追随のみ。製品3ファイルとspec6ファイルは本人確認HEADから不変で、既済みレビューの採否も維持する。追加登録差分は元の18ファイルの本人確認には含まれない。既存履歴由来の別1件は判断資料へ根拠を提示し未登録を維持する。
