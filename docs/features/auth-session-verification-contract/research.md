# C1 調査記録: 認証 session 確認

## 2026-10-15 の基線

- `origin/develop`: `e6e1a867f88bbdac90f2be9bed20dff900eec866`。C1専用branchにはmerge `5c8959aa`で取り込み済み。既存方針どおりmergeを用い、rebaseを自動前提にしない。
- PR #119: `8294a1b6`で統合済み。login / logout / password、HttpOnly Cookie、`tenant_access.py`を再利用する。
- develop の U-F2 auth store は `teamName` が非nullなら認証済みとし、`signIn` / `signOut` / `expireSession` が QueryClient clear と `authEpoch` 増分を行う。検証待ち状態はない。
- develop の U-F6 client は `credentials: include`、応答前後の `authEpoch` 照合、401時の `expireSession()` を持つ。

## 問題

login 2xx の後に session がnetwork / 5xx / DTO不正で失敗した場合、Cookie は有効な可能性がある。その失敗を401と同一にすると、サーバー認証状態を誤表示する。逆に旧store/cacheを維持すると、Cookieは新tenant、画面は旧tenantという組合せが生じる。

このため、Cookieが変わり得る時点で旧client状態を破棄し、session 2xxだけを認証済み、session 401だけをサーバー未認証、その他を結果未確認として保持する。

## 共有資産

- PR #129は`93e1482a`で統合済み。
- PR #131はopen Draftで、`.claude/core-areas.json`とtenant boundaryの複数凍結資産を変更中。
- PR #132はopen Draftで、`operation_registry.py`、repository契約試験、tenant boundary凍結資産を変更中。
- PR #137はopen Draftで、auth route registry / HTTP matrixの本体・lock、authz凍結資産、checker試験を変更中。
- 未統合差分はC1の基線にしない。Claude調整役にrepository側と認証経路側を分けて先行順の判断を依頼済み。返信なしを不受理・所有移管とは扱わない。

## tenant read operation の具体案

| 項目 | 契約 |
| --- | --- |
| token | `TenantProfileReadToken()`。callerが設定できるフィールドを持たないfrozen dataclass |
| capability | 既存`CAP:tenants:read`だけを返す |
| table / tenant列 | `public.tenants` / `tenants.id` |
| SQL | `SELECT tenants.id, tenants.name WHERE tenants.id = :tenant_id`。`tenant_id`は`TenantContext`から既存実行器が束縛する |
| 内部結果 | `TenantOperationResult.rows`の0または1行。成功行はexact `(UUID, str)` |
| 禁止 | caller指定tenant ID、一覧、書込、cross-tenant、任意statement、Callable、Session公開、team nameによる検索 |

`backend/src/pitchlog/repositories/tenant_profile.py`はtoken、固定statementのprepare、`TENANT_PROFILE_OPERATIONS`だけを公開候補とする。endpointは既存`tenant_transaction_scope(context)`でtokenを実行し、行数と各値のexact型を検査してAPI DTOへ写す。別のDB接続や直接SQLをrouterへ追加しない。

## session endpoint の入出力

| 項目 | 契約 |
| --- | --- |
| method / path | `GET /auth/session` |
| operation ID | `auth_session_read` |
| 入力 | `__Host-pitchlog_token` Cookieだけ。body、path、query、headerからtenant IDまたはteam nameを受け取らない |
| 認証 | `require_tenant_access`が返す検証済み`TenantContext`だけを利用する |
| 成功応答 | HTTP 200、`AuthSessionResponse {tenant_id: UUID, team_name: str}`。余分なfieldなし |
| `tenant_id` | Cookie検証から発行された`TenantContext.tenant_id`とrepository行IDのexact一致を再確認する |
| `team_name` | 同じtenant行の`public.tenants.name`。表示だけに使い、認可・tenant照合キーにしない |
| Cookie | #119の`require_tenant_access`が行う期限延長と属性をそのまま維持する |

queryや任意headerにtenant IDを付けても入力として解釈せず、Cookie由来tenant以外の結果を返さない。request値と応答値を比較して認可する経路も作らない。

## 失敗境界

| 条件 | 外部応答 | 内部扱い |
| --- | --- | --- |
| Cookieなし、署名不正、失効・取消済みtoken | 401の固定error envelope | #119のcredential拒否を再利用 |
| disabled / retired / 不在tenant | 401の固定error envelope | tenantの存在・状態を本文へ出さない |
| Cookie検証後にtenant行が0件 | 401の同じ固定error envelope | 認証成立を取り消し、名前やIDを返さない |
| repository結果が複数行、列数不正、ID不一致、型不正、空のteam name | 500の固定error envelope | 契約破損。成功へ縮退しない |
| DB接続・実行失敗 | 500の固定error envelope | 結果未確認。値やSQLを応答へ出さない |
| 正常な1行 | 200 | DTO構築後だけ成功 |

401同士はstatusと本文を同一にし、token、tenant ID、team name、存在・無効理由をログや応答へ含めない。500も共通未捕捉例外ハンドラの固定文言だけを返す。

## ステップ1の試験項目

### repository契約

1. tokenが引数なし・frozen・exact capabilityである。
2. statementが`tenants.id = :tenant_id`と2列選択だけを持ち、LIMITなしでも主キーにより最大1行である。
3. prepared parameterへcaller由来tenant IDを渡せない。
4. 未登録・偽造token、capability差替え、tenant predicate欠落、可変・遅延結果を既存実行器が拒否する。
5. AのcontextはAの`id`/`name`だけ、BのcontextはBだけを返し、相手tenantの値を指定する入力面がない。
6. 0行、複数行、列数不正、UUID/string以外、contextと異なる行IDを成功DTOへ変換しない。

### HTTP API

1. 有効Cookieで200とexact `{tenant_id, team_name}`、token非露出、更新Cookie属性維持。
2. Cookieなし、署名不正、期限切れ、取消済み、disabled、retired、不在tenantを同じ401本文へ写す。
3. query/header/bodyに別tenant IDやteam nameを注入しても、Cookie由来tenant以外を返さない。
4. Cookie A/Bそれぞれで対応する正規名を返し、Aの入力値をBの名前取得に使わない。
5. 認証とprofile readの間で行が消える場合を401、DB障害と結果shape破損を固定500へ写す。
6. route登録とoperation IDのexact集合を更新し、既存login/logout/password経路を保持する。

### 凍結・7.7

1. repository contractのcapability/token exact-setとcontract revisionを更新し、直前射影のsnapshotをappend-onlyで保存する。
2. route registry / HTTP matrix本体とlockを再導出し、session 1件以外の意味差分がないことを検査する。
3. authz oracle入力の変更は`frozen-baselines.json`へ一行為一記録で追記し、seal連鎖を正規コマンドで再導出する。
4. 基準値をcheckerへ直書きせず、snapshot欠落、digest不一致、履歴欠落、未登録route、人間逐行確認未記入の拒否を弱めない。

## 2026-10-15 統合待ちの分解

Claude調整役から、共有凍結資産は既存PR先行を維持し、#137とは意味衝突がないとの中継を受けた。実差分との照合結果は次のとおり。

| PR | C1と重なる実差分 | C1への影響 | 待ちの種類 |
| --- | --- | --- | --- |
| #131 / TSK-538 | `repository-contract.json`はrevision 16→17とsource digestだけ。product capability/token集合、executor、return contractは不変 | C1のtoken形を変えない。#131のtenant-boundary封印を先に着地させる | #132がこの先行資産へ追随するための間接順序。C1製品コードの直接開始条件ではない |
| #132 / TSK-391 | `PRODUCT_OPERATIONS`へsync operationを追加し、repository contractに`operation_guards`とcapability/token exact-setを追加 | C1 token/operation tupleを公開集合へ含める場所と検査方法を決める | **唯一の直接回答待ち**。公開面判定後、非共有の製品コード・単体試験を開始できる |
| #137 / TSK-238 | route / matrixのrequirement digest、lock、oracle封印を更新。AUTH 3行とdispositionはdevelopと同一 | session routeの意味と衝突しない。C1のroute 1件追加は#137統合後の資産へ積む | authz凍結差分と7.7履歴を作る前の順序。endpointコード・固有試験の直接開始条件ではない |

したがって「残る待ちは#132だけ」は、**非共有のC1製品コードと固有試験を開始する条件**として成立する。ステップ1全体の完了・単一コミットには、#131→#132後のtenant-boundary資産と#137後のauthz資産へ追随し、両方の7.7検査を通すことが必要である。

TSK-391へ、`TenantProfileReadToken`と`TENANT_PROFILE_OPERATIONS`が公開面・exact-setへ乗るか、`operation_guards`と意味衝突しないかを[確認中](https://github.com/masaki1025/pitchlog/pull/132#issuecomment-6171748012)。2026-10-15 00:20 JST時点では回答未着であり、未回答を不受理とは扱わない。

必要な計画追補は、TSK-391回答後に次の2点だけとする。

1. 開始条件3を「共有資産の所有と先行順が確定済みなら、未統合資産を変更せず非共有コード・試験を開始できる。公開面の意味を決める#132回答まではrepository実装を開始しない」へ明確化する。
2. ステップ1の内部順を「非共有コード・固有試験 → 既存PR統合後のlatest developをmerge → tenant-boundary/authz凍結差分と7.7履歴 → 全検査 → 単一の`(ステップ 1/2)`コミット」と追記する。ステップ数、DoD、endpoint/DTO/認可、正式コミット単位は変えない。
