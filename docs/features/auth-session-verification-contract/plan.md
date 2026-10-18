---
feature: auth-session-verification-contract
status: in-review
承認: 済(2026-10-14・山田正輝)
重さ分類: コア領域
worktree: /tmp/pitchlog-auth-session-verification-contract
notion: "U-F13（TSK-528）追補 C1"
branch: feature/auth-session-verification-contract
created: 2026-10-14
計画レビュー周回: 2
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 追補実装計画書案: C1 認証 session 確認と検証済み tenant 供給

## 1. 目的と所有

PR #119 の login Cookie 発行後に、サーバーが検証した tenant 情報を U-F2 の auth store へ供給する。login の成功応答だけでは画面を認証済みにせず、session 確認の結果を「認証済み」「サーバー未認証」「結果未確認」に分ける。

- 担当: Codex D。本追補の製品実装は PR #119 統合後、専用 worktree で行う。
- PR #119 の branch / worktree は変更しない。`LoginResponse={status:"authenticated"}` を本追補で拡張しない。
- 共有凍結資産はPR #129・#131・#132の所有範囲を先に確認し、未統合branchをdevelop基線にしない。
- 本計画の調査根拠は [research.md](research.md) とする。

## 2. 開始条件

1. 本計画の adversarial review と人間承認が完了している。
2. PR #119 が develop に統合され、最新 `origin/develop` で login / logout / tenant context の実コードを再照合している。
3. PR #129・#131・#132と認証経路側PR #137について、本追補が触れる凍結資産・検査コードの所有と先行順が確定している。未統合の共有資産は変更しないが、所有と先行順が確定済みなら非共有コード・固有試験を開始できる。repository実装は、#132担当が`TenantProfileReadToken`と`TENANT_PROFILE_OPERATIONS`の公開面・exact-set上の扱いを回答した後に開始する。
4. 具体的 endpoint、DTO、認可、凍結資産の変更が本計画の承認対象として人間承認されている。

## 2.1 影響する正本

正本への反映なし。本追補は承認済みの認証・tenant分離契約に対する製品実装追随であり、`docs/requirements`・`docs/design`・`docs/adr`・`docs/development`・`docs/ops`は変更しない。

**正本体系外だが同一PRで更新するもの**: frontendの`api/auth.ts`・`api/client.ts`・`stores/authStore.ts`と各spec、C2/U-F3/U-F13の依存・所有状態、backendのsession endpoint・DTO・tenant profile固定operationと試験、`contracts/authz/*`のroute/matrix・oracle資産、`contracts/tenant_boundary/{base-allowlist.json,repository-contract.json}`、authz/tenant-boundaryの検査fixture・検査コード、本計画・関連調査/申し送り・作業ログ。

## 3. 認証状態と失敗時の契約

### 3.1 状態

| 状態 | auth store / cache | UI と通信 |
| --- | --- | --- |
| `unauthenticated` | tenant 情報なし、tenant query cache なし | 資格情報入力を許す |
| `submitting` | login 要求前の状態を維持 | 二重送信しない |
| `verifying` | login が 2xx、または login 応答自体が結果未確認になった時点で、旧 tenant の store 永続値と query cache を破棄し `authEpoch` を進める。認証済みにはしない | session 確認以外の tenant-bound request を開始しない |
| `authenticated` | session の 2xx DTOを厳密検査した後だけ、検証済み tenant ID と正規表示名を一度に保存する | `authenticated` event を発行できる |
| `verification-unknown` | `verifying` と同じく未認証・空 cache を維持する。`sessionExpired` と同一にしない | 資格情報を自動再送しない。session の明示再確認か logout を選べる |
| `server-unauthenticated` | store / cache を空にし、サーバー未認証として扱う | generic な認証失敗または session 失効を表示する |

`verifying` / `verification-unknown` は U-F3 の画面状態とし、U-F2 の認証済み状態へ保存しない。ただし旧 tenant を同期的に破棄する U-F2 操作は一つの正規メソッドへ置き、画面から QueryClient を直接操作しない。

起動時は`bb.auth`の有無にかかわらずsession未検証とする。保存値は確認候補としてだけ読み、`isAuthenticated`を真にせず、tenant-bound APIと保護routeを開始しない。C1の共有`ensureSessionVerified()`が同時呼出しを1要求へ集約し、U-F13 guardとU-F3初期表示のどちらからも利用できる。session 2xx後だけ認証済みへ移り、401は保存候補を破棄して未認証、非401失敗は旧store/cacheを空にした結果未確認へ移る。

### 3.2 login と session の結果

| 結果 | 処理 |
| --- | --- |
| login の 401 / 429 / 確定した非 2xx | `noAuthExpiry`相当の正規optionで共通clientの401自動失効を抑止する。Cookieが発行されていない契約を#119統合後に確認し、既存認証がある場合はそのstore/cacheを変更しない。存在を推測できない固定表示にする |
| login の 2xx | Cookie が切り替わったものとして直ちに旧 store / cache を破棄し、session を 1 回確認する |
| login の network / abort / 応答解釈失敗 | Cookie 発行の有無が不明なので旧 store / cache を破棄し `verification-unknown`。login を自動再送しない |
| session の 2xx + DTO妥当 | `authenticated`。DTOの全項目と形式を検証した場合だけ遷移する。tenant IDはサーバー応答だけを正とし、入力値・localStorage・route queryから作らない。`team_name`はサーバーの認可済みデータから取得し、認可・tenant照合のキーに使わない |
| session の 401 | `server-unauthenticated`。この場合だけサーバー未認証と扱う |
| session の 404 / 422 / 5xx / network / abort / DTO不正 | `verification-unknown`。2xxでもDTO検証に失敗した場合を含む。401と同一扱いにせず、login成功・失敗のどちらも断定しない |

### 3.3 再確認と logout

- 自動再確認を行わない。「ログイン状態を再確認」は idempotent な session GET だけを利用者操作で再実行する。資格情報と login POST は再送しない。
- `verification-unknown` での「ログアウトしてやり直す」は正規 logout API を 1 回だけ呼ぶ。2xx または契約上の未認証応答を確認した場合だけ完了表示へ進む。
- logout の network / 5xx はサーバー状態未確認のままとし、「ログアウト済み」と表示しない。store / cache は空のまま保ち、session 再確認または logout 再試行を利用者が選ぶ。
- reload後も有効Cookieを復元できるよう、C1の共有session確認をU-F13 guardとU-F3初期表示が利用する。C1では保存候補A + Cookie B相当、保存候補あり + session network失敗をstore/client単体で試験する。実`/team`でTeamScreenとtenant APIが確認前に開始しない受入はU-F13が所有する。

## 4. 承認対象となる具体契約

以下は本計画のレビューと人間承認を受けて初めて正式契約になる。

1. **endpoint**: `GET /auth/session`。
2. **DTO**: `AuthSessionResponse { tenant_id: UUID, team_name: string }`。`team_name` はサーバーが認証済み tenant から読み出す正規表示値で、認可判断には使わない。
3. **認可**: PR #119 の Cookie 検証と `require_tenant_access` で発行した `TenantContext.tenant_id` だけを入口にする。request から tenant ID を受け取らない。
4. **成功境界**: Cookie 検証、tenant の有効性、正規表示名の取得まで成功したときだけ 2xx。失効 Cookie は 401、tenant 所有値や存在理由をエラー本文へ出さない。
5. **client API**: `frontend/src/api/auth.ts`のlogin/session/logoutと共有`ensureSessionVerified()`は既存共通clientを利用し、`credentials: include`、認証世代照合、既存error envelopeを維持する。loginの401は自動`expireSession()`を抑止する。
6. **U-F2 追随**: 起動時のsession未検証状態と、旧認証を破棄して検証待ちへ入る正規操作をauth storeに追加する。QueryClient clear、`authEpoch`増分、`bb.auth`除去を一度に行い、`sessionExpired=true`にはしない。`isAuthenticated`はsession検証済みの場合だけ真にする。

`team_name` を DTO に含めない案は、reload / 結果未確認後の再確認で検証済み表示名を復元できないため採用しない。login 入力を認可・tenant 照合・永続復元の正にしない。

## 5. 変更候補と共有資産の統合順

| 区分 | 変更候補 | 所有・統合条件 |
| --- | --- | --- |
| backend | auth router / schema、session endpoint、backend tests | #119 統合後の実パスから確定する。#119 の変更をコピーしない |
| frontend | `api/auth.ts`、`authStore.ts` と各 spec | U-F3 と同じ branch に混ぜず、C1 の先行追補として統合する |
| authz / 凍結 | route registry、HTTP route matrix、runtime authz contract、tenant boundary allowlist / history | #129・#131・#132の所有差分を先に確定する。共有実行器A（PR #141）と重なるrepository契約・base allowlistはA→C1の順に統合し、Aの実統合SHAを含む最新developからC1の識別値・履歴・snapshotを再導出する |
| core paths | auth router/schema/client/store の既存登録と不足分 | 製品差分と同じ追補で扱う。core pathだけを先行登録しない |

## 6. 実装ステップ

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | #119 統合後の server に session endpoint / DTO / authz を追加する | 2xx は Cookie 由来の tenant ID と正規表示名だけを返す。401、失効、無効 tenant、存在秘匿、request tenant 注入拒否、凍結資産検査、backend 品質 gate が green |
| 2 | U-F2 store と正規auth clientに起動時/session verification境界を追加する | store/client単体で、保存値だけでは認証済みにせずtenant-bound requestを開始できない。login 2xxと結果未確認で旧store/cacheを破棄。login 401は既存認証を失効させない。session 2xxかつDTO検証成功時だけ認証済み。401とnetwork/5xx/DTO不正が別状態。資格情報の自動再送なし。保存値A + Cookie Bの候補、遅延session、並行確認を試験。実`/team`直接reloadのguard/画面/API受入はU-F13ステップ2/3で行う。frontend品質gate green |

各ステップは別コミットとし、人間が承認したステップだけを実装して停止する。ステップ1だけは、authz入力commitと実PR番号の自己参照を閉じるため、次の3段・3コミットをC1限定例外として用いる。planは第3段と全合格条件が完了するまで`active`に保つ。

1. **第1段**: 非共有コード・固有試験を保全し、共有実行器A（PR #141）の実統合後にそのSHAを含む最新`origin/develop`をmergeする。Aが確定したrevision・履歴をbeforeとして、C1のrepository契約、base allowlist、source digest、snapshot、7.7 previous/newを再導出する。異なるbranchの同じrevision番号や旧snapshotを同一内容として流用しない。製品・共有契約・route/matrix・derived lock・隔離DB試験と、正式受理前に実行可能な検査を`(ステップ 1/2 第1段)`へまとめる。PR番号・oracle commitに依存する検査は緩和せずfail-closedの未完了として記録する。
2. **第2段**: 第1段の実コミットSHAをauthzの`oracle_commit` 7箇所へ反映し、対応する入力digestだけを追随する。履歴・seal・tenant-boundary snapshotを仮値で受理せず、`(ステップ 1/2 第2段)`とする。
3. 第2段までをpushし、実PR番号取得用のDraft PRを作る。PR本文に3段の内容、C1ステップ1未完了、7.7第3段待ち、レビュー・人間逐行確認未完了を明記する。Draft解除・マージを行わない。
4. **第3段**: 実PR番号を用いたtenant-boundary v2受理記録・snapshotとauthz `oracle_input`追記の完全な前後差分を提示する。正式な7.7人間受理後だけ履歴、seal、archive corpusを再封印し、`(ステップ 1/2 第3段)`とする。正式な承認者・承認日を先行入力しない。
5. 第3段後に全品質gate、反対側レビュー、コア敵対レビュー、人間逐行確認を完了して初めてステップ1合格とする。rebaseを自動前提にせず、未統合branchを基線にしない。ステップ数、DoD、endpoint / DTO / 認可は変更しない。

## 7. DoD とレビュー

- [ ] login Cookie 発行後、session 失敗を一律にサーバー未認証へ畳み込まない。
- [ ] 旧 tenant の store / cache は Cookie が変わり得る時点で破棄され、新 tenant の session 2xx 前に再表示されない。
- [ ] session の明示再確認は login POSTを再送しない。
- [ ] logout の結果未確認を成功表示しない。
- [ ] delayed sessionとCookie変更のない旧認証応答は新世代を変更しない。旧login/logoutがCookieを変更し得る場合だけ、新世代も認証未確認へ戻しcacheを破棄する。旧応答からユーザー・tenant・成功状態を採用しない。
- [ ] tenant ID と正規表示名を利用者入力から生成しない。
- [ ] 共有実行器Aの実統合後のdevelopからC1のrepository契約・base allowlist・7.7前後値を再導出し、異なるbranchの同じrevisionを流用していない。
- [ ] 第1・第2段では未受理履歴・sealをfail-closedのまま維持し、第3段の正式受理前に承認者・承認日を入力していない。
- [ ] コア adversarial review、反対側レビュー、人間逐行確認、backend / frontend 品質 gate、凍結資産検査を通す。

## 8. 人間承認が必要な判断

1. 4節の endpoint、DTO、認可、成功境界を正式契約にすること。
2. 3節の状態遷移、旧 store/cache の破棄時点、明示再確認、logout 未確認時の扱いを採用すること。
3. U-F2 に検証待ち開始操作を追加し、C1 のステップ2で所有すること。
4. #129・#131・#132の統合前には共有凍結資産を変更せず、統合後のdevelopから必要差分を作ること。
5. 承認後の開始は、#119 統合後の **ステップ 1/2 のみ**とすること。

## 9. レビュー状態

U-F13計画の最終P1反映と、その後に具体化した本契約案は未再レビューだった。2026-10-14の追補横断adversarial review第1周はP0 2 / P1 6 / P2 0（うちC1はP0 1、P1 1）。全件採用し、起動時未検証、guard/API待機、login 401の自動失効抑止、直接reloadとA保存値/B Cookie試験を追加した。反映差分の再レビュー後に人間承認を求める。

第2周はP0 2 / P1 2 / P2 0（うちC1はP0 1）。採用し、C1の合格条件をstore/client単体へ閉じ、実`/team` reload受入をU-F13ステップ2/3へ移した。P0反映だけを自動第3周で再レビューする。

第3周は第2周P0反映だけを対象とし、P0 0で可決。第2周P1の追随差分は回数上限により未再レビューであり、人間承認時の確認対象とする。

2026-10-16、POが追補差分と影響節に限定した追加独立レビュー1回を許可した。追加独立レビューはP0 0 / P1 2 / P2 0。P1は、A→C1順を計画へ固定してA統合後に受理値を再導出することと、API規約試験で従来の禁止DB語彙の部分一致検出を維持し`AuthSessionResponse`だけを厳密に除外すること。いずれも承認済み範囲内で採用した。追加仕様・権限・承認範囲の変更はない。

## 10. 人間承認記録

2026-10-14、山田正輝が計画HEAD `e42a2ddbd2db58dd1fca642959ff4a2870299f63` の本計画を承認した。sessionは2xxかつDTO検証成功時だけ認証済みとし、2xxのDTO不正は結果未確認とする。`team_name`はサーバーの認可済みデータから取得し、認可・tenant照合のキーに使わない。開始条件成立後も最初のステップだけを実装して停止する。第2周P1追随の未再レビュー範囲は人間逐行確認対象として維持する。

2026-10-15、山田正輝が開始条件3の分解とステップ1内部順の最小追補を承認した。共有凍結資産は既存PR先行を維持し、#132の公開面回答後は未統合共有資産を変更せず非共有実装・固有試験を開始できる。ステップ1完了は、既存PR統合後の凍結資産追随、7.7確認、全検査を終えた後とする。

2026-10-16、山田正輝がC1ステップ1限定の3段・3コミット、Draft中のplan `active`維持、品質gate分割を承認した。追加独立レビューが承認範囲内の修正で収束した場合、第1・第2段のコミット、push、実番号取得用Draft PR作成まで再確認なく進める。共有実行器Aと重なる資産はA→C1を基本順とし、Aの実統合後の基線から受理値・履歴を再導出する。第3段の正式7.7受理、人間逐行確認、Draft解除、マージは承認範囲外である。

2026-10-16、山田正輝が判断資料SHA-256 `75b65bf4f9f92a97e771e305bcd0c9a9b270d39467f71b5f25280562033d1f69`、受理記録案SHA-256 `43acdfa1b1e88ad235af019fd230615a702a191d91c3c158ca7b1466b4a0e141`に固定したtenant-boundary・authz両系列の7.7記録案、2 snapshot、8入力blob、6 sealed digestを正式受理した。承認者は山田正輝、承認日は2026-10-16。第3段の履歴・snapshot反映、oracle再封印、コミット、検査、push、CI、PR本文更新を許可した。この受理はPR全体の本人逐行確認、Draft解除、マージ、C2、U-F3、公開を含まない。


## 11. ステップ2再開記録（2026-10-17）

山田正輝がC1ステップ1統合後、承認済み計画のステップ2の実装・試験・レビュー・指摘対応・コミット・PR準備を承認した。最新develop `3052e0db743877c7f15c0ec10daa0142cba7ab7e`へ専用worktreeをfast-forwardし、開始条件を再照合した。login/session/logoutの既存endpoint/DTO、U-F6共通client、共有Pinia/QueryClientを利用する。C2・U-F3・公開・マージへは進まない。

| 編集対象 | 今回の一時所有 | 後続への引渡し条件 |
|---|---|---|
| `api/auth.ts` / `authStore.ts` / 各spec | C1（Codex D） | session DTO検証、確認前の空状態、結果未確認、世代照合の検査と統合後にU-F3が呼ぶ |
| `api/client.ts` / 各spec | C1（Codex D） | tenant通信の確認前拒否とlogin成功headers直後の旧認証破棄だけを追随。C2はC1統合後からmetadata照合を追加 |
| `api/roster.spec.ts` | C1（Codex D） | 単体試験の前提を検証済み認証へ明示する。roster製品API/DTOは変更しない |
| `LoginScreen` / router / App | U-F3 / U-F13（Codex D） | 今回変更せず、C1全体の統合後に各計画・指示に従い着手 |

worktree一覧とopen PR（#138/#142/#143）にC2/U-F3/U-F2/U-F6の並行編集はない。既存承認済みの同一担当内でC1→C2→U-F3/U-F13の順を維持する。共有凍結資産は変更しない。`bb.auth`の旧形は候補として検査するが認証済みへ戻さず、保存形式を独自に追加しない。

## 12. 遅延Cookie副作用の最小追補（承認済み・2026-10-17）

山田正輝が第1周敵対/反対側レビューのCookie競合に対する追補を承認した。§7の旧認証応答に対する条件には次の安全側への例外を適用する。

- 遅延した旧login/logoutがCookieを変更し得る場合に限り、新世代も認証未確認へ戻し、store/cacheを破棄して明示session再確認を要求する。旧応答から新世代のユーザー・tenant・成功状態を採用する許可ではない。
- Cookie変更可能性はlogin/logoutの2xx headers到着、またはHTTP応答を得られないnetwork/abortで判断する。確定した非2xxには適用せず、旧session GETにも適用しない。2xx後に本文が遅延・失敗しても同じ応答による無効化を再通知しない。
- 本文や世代を解釈する前にCookie変更可能性を一度だけ扱う。旧要求であるという情報を保持し、無効化によってepochが進んでも旧要求を現世代の成功へ昇格させない。
- 資格情報・mutationの自動再送、sessionの自動再確認は禁止。未確認中のtenant-bound通信は共通clientで拒否する。session確認中に別のCookie変更可能応答を観測した場合、そのsession結果も旧世代として採用しない。
- 遅延login/logout、複数世代、sessionとの前後競合、確定拒否、同一応答の通知/cache破棄の重複を固有試験で検証する。別タブの確認/保存により他タブも未確認になる保守的な既存契約は維持する。

本追補は新API・DTO・header・ACL・保存形式・共有凍結資産を追加しない。C2/U-F3の接続条件へ同期する。本人逐行確認・公開・マージの承認とは扱わない。既定の第2周は修正差分と影響範囲の確認に用い、計画全体を再審査しない。

## 13. ステップ2限定Draft先行例外（2026-10-18・承認済み）

山田正輝がpr手順2.4に対するC1ステップ2限定の例外として、通常pushとDraft PR作成を承認した。ローカル全件/check未通過を本文へ明記し、CIと専用領域で残る検査を進める。全品質ゲート通過・ステップ2完了・本人逐行確認済みとは記録しない。Draft提出用にstatusをin-reviewへ移すが、検査待ちDoDとTSK-528全体未完了を維持する。

最新developはPR #146（TSK-565）の統合SHA `ce0c0e8697252a89bce0c57e69b4821e0a6cac2b`。PR #145・#146をmergeで取り込み、競合なし。製品3ファイルは正式第2周review manifestのhashと一致し、C1の認証/API/DTO/ACL/凍結資産の候補差分は追加しない。#145の受理済み資産は基線として保持し、C1で再封印や履歴追加を行わない。

#146の移送はroot/backendのconftestで起動する。以前の明示TMPDIR/--basetempは移送や掃除の実証にならないため、今回はTMPDIR/PYTEST_DEBUG_TEMPROOTを外してC1専用PITCHLOG_PYTEST_TMPDIRを指定し、配線試験と実basetempを照合する。root全件は4 worker上限（子pytestのautoも4）とし、backendのローカル配線確認・frontendと重ねた高負荷の全層実行は避ける。試験除外・timeout緩和は行わない。

C2/U-F3・公開・Draft解除・マージには進まない。既定の2周レビューとP2反映記録を維持し、必要な追加レビュー裁定が判明した場合だけ差分を提示する。
