---
feature: tenant-match-metadata-contract
status: active
承認: 済(2026-10-14・山田正輝)
重さ分類: コア領域
worktree: /tmp/pitchlog-tenant-match-metadata-contract
notion: "U-F13（TSK-528）追補 C2"
branch: feature/tenant-match-metadata-contract
created: 2026-10-14
計画レビュー周回: 2
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 追補実装計画書案: C2 expected tenant と 2xx 照合証跡

## 1. 目的と所有

U-F5 が使う tenant-bound APIで、clientが保持する検証済みtenant IDとserverの`TenantContext.tenant_id`を業務operation前に照合し、照合済みの2xxだけを画面・cacheへ渡す。

- 担当: Codex D。本追補の製品実装は PR #119 統合後、専用 worktree で行う。
- U-M1 の roster DTO に `tenant_id` を追加しない。認証、health、公開APIには適用しない。
- PR #119 の `tenant_access.py` と競合するため、同PRのbranch/worktreeは変更しない。
- 詳細な実コード調査は [research.md](research.md) を正とする。

## 2. 開始条件

1. 本計画の adversarial review と人間承認が完了している。
2. PR #119 が develop に統合され、`require_tenant_access` の最終実装を再照合している。
3. C1 が検証済み tenant ID を U-F2 store に供給する契約として統合済みである。
4. PR #129・#131・#132の共有凍結資産の所有と統合順が確定している。
5. header、literal、適用route、error/ackの意味を本計画の承認対象として人間が承認している。

## 2.1 影響する正本

正本への反映なし。承認済みmetadata契約の製品追随として、要件/design/ADR/development/opsの正本は改訂しない。

正本体系外だが同じPRで更新するもの：backendのtenant_access・app応答middleware・errors・players/team-records routersとAPI/roster/auth出口の固有試験、frontendの単一client・roster・既存管理画面のretry/結果未確認境界と各spec、本計画/research・接続判断資料・未承認のC1最小追補案・PR準備資料、C1の完了記録、U-F13の依存記録、作業ログ。追補案の同梱は製品への採用ではない。共有凍結資産/認可catalog/権限・DTO・operation_idは不変で、実検査で必要が判明した差分だけを個別ゲートへ提示する。

## 3. 承認対象となる metadata 契約

以下はレビューと人間承認を受けて初めて正式契約になる。

| 項目 | 候補契約 |
| --- | --- |
| request header | `X-Pitchlog-Expected-Tenant: <canonical UUID>` |
| success ack | `X-Pitchlog-Tenant-Match: 1` |
| request challenge | `X-Pitchlog-Tenant-Challenge: <canonical UUID>`。clientが要求ごとに`crypto.randomUUID()`で生成し、tenant IDとして使わない |
| response challenge | `X-Pitchlog-Tenant-Challenge: <request challenge>`。serverがexpected tenant照合後の成功2xxだけへ返す |
| canonical UUID | ASCII lower-caseのhyphen付きUUID。`str(UUID(value)) == value` を満たす |
| server比較 | `require_tenant_access` が発行した `TenantContext.tenant_id` とheaderをexact match |
| 失敗応答 | header欠落・複数・非canonical・不一致は同一の固定404。tenant値、存在、差異を本文やlogへ出さない |
| ackの意味 | 「serverがこのrequestのexpected tenantとContextを比較済み」。tenant ID自体を応答しない |
| ack付与 | 比較通過後に業務operationも成功した2xxだけ。401/404/409/422/5xxには付けない |
| cache制御 | 対象7routeのtenant所有応答は`Cache-Control: no-store`。Aの2xxをBへ再利用させない |

対象routeは U-F5 初期分割が使う次の7件に限定する。

1. `GET /team-records`
2. `POST /team-records`
3. `PATCH /team-records/{id}`
4. `GET /players`
5. `POST /players`
6. `GET /players/{id}`
7. `PATCH /players/{id}`

## 4. server 境界

1. Cookie検証とtenant context発行を先に行う。失敗は現行401。
2. request headerを1値として厳密にparseする。routeが認識された後はbody/query validationよりこの境界を先に評価し、header欠落・複数・非canonical・不一致がbody/query不正と重なっても固定404を返す。
3. canonical UUID と `TenantContext.tenant_id` を比較する。
4. 不一致ならrepository呼出し、transaction開始、bodyに基づく業務更新より前に固定404で終了する。
5. 一致したrequestだけ業務operationを実行する。
6. operationが成功した2xxだけ固定ackとrequest challengeのexact echoを付ける。error handlerが返す非2xxにack/challengeを引き継がない。

7routeすべてで、不正headerと不正body/queryの組合せが固定404・同一本文・operation 0件になることを実測する。path自体がrouteへ一致しない要求はrouterの通常404とする。header値を監査log・例外文字列・validation本文へ出さない。

## 5. client 境界

- 共通clientにtenant-bound optionを追加し、該当7routeの正規U-F6関数だけが有効にする。一般requestのdefaultにはしない。
- request直前にauth storeを同期し、`teamId`がcanonical UUIDであることを確認する。欠落・不正ならfetch前に失敗する。
- request開始時の`authEpoch`と`teamId`を保持し、response受領時と本文読取り後に両方を再照合する。
- 非2xxは既存status処理へ渡し、ackを要求しない。401は現行の古い認証応答保護を維持する。
- 2xxは本文をparseする前にackのexact literalと、要求ごとに生成したchallengeのexact matchを検査する。欠落・不正・別要求のchallengeなら本文を画面/cacheへ渡さない。
- ack検査後も本文読取り中の認証切替を再照合する。
- 2xx ack欠落・不正、認証世代変更、teamId変更はtenant verification専用例外にする。mutationは結果未確認、queryは破棄とし、自動retry対象から外す。
- header値、tenant ID、応答本文を利用者向けエラーやlogへ埋め込まない。

## 6. error と 2xx ack の扱い

| 応答 | clientの扱い |
| --- | --- |
| 2xx + ack exact + challenge exact + epoch/teamId不変 | 本文返却、画面/cache/success notice更新を許す |
| 2xx + ack/challenge欠落・不正・別要求値 | 本文を返さず結果未確認。mutation/queryとも自動再送しない |
| response中のepoch/teamId変更 | `ApiStaleAuthError`相当で本文破棄。古い401で新sessionを失効させない |
| 401 | ack不要。現行規則でsession失効。ただし古い認証応答は破棄 |
| queryの404/409/422/5xx | ack不要。成功・cache更新を行わない。既存query retry規則を適用する場合もtenant verification errorは除外する |
| mutationの404/409/422 | ack不要。失敗として扱い、cache更新・success noticeを行わない |
| mutationの5xx | serverで処理済みの可能性がある結果未確認。success noticeを出さず、自動再送せず、送信元tenantの一覧再取得で確認する |
| network/abort | 現行分類を維持。mutationは結果未確認で自動再送しない |

## 7. 変更候補と共有資産

| 区分 | 変更候補 | 所有・統合条件 |
| --- | --- | --- |
| server | `tenant_access.py`、players/team-records routers、tests | #119統合後に実パス確定。operation前拒否を各routeで検証 |
| client | `api/client.ts`、`api/roster.ts`、spec、U-F5のretry/error境界の最小追随 | U-F6の単一clientを拡張しコピーしない |
| authz / 凍結 | route registry、HTTP route matrix、runtime authz contract、tenant boundary allowlist/history | #129・#131・#132の統合済み状態だけを基線にする。必要な受理単位を計画へ追記してから変更 |
| core paths | 上記product pathの既存登録と不足分 | 製品差分と同じ追補で扱い、core pathだけを先行登録しない |

## 8. 実装ステップ

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | server共通境界と7routeの適用、backend/fault injection試験 | expected tenant/challengeの欠落・複数・不正・不一致はbody/query不正と重なってもoperation前の固定404。2xxだけ固定ack+challenge echo。非2xxに両headerなし。全tenant所有応答はno-store。越境と不存在が同一。backend品質gateと凍結資産検査green |
| 2 | U-F6共通clientとroster関数のfail-closed検査 | fetch前teamId検査、要求ごとのchallenge生成、2xx ack+challenge、epoch/teamId二重照合。欠落/不正/別要求challengeの2xx、Aの過去応答をB要求へ注入、遅延response/mutationは本文・cache・noticeを更新せず自動retryなし。mutation 5xxは結果未確認。frontend品質gate green |

各ステップは別コミットとし、人間が承認したステップだけを実装して停止する。

## 9. DoD

- [ ] 7routeすべてで業務operation前にexpected tenantを照合する。
- [ ] mismatch時にrepository/transaction/mutationが0件である。
- [ ] success ackは比較とoperationの両方が成功した2xxだけにある。
- [ ] 2xx ack/challenge欠落・不正・別要求値を本文返却前に拒否する。
- [ ] A→B切替中のAの遅延response/mutationがBの画面/cache/noticeを変更しない。
- [ ] 結果未確認mutationを成功表示・自動再送しない。
- [ ] 7routeが`Cache-Control: no-store`を返し、要求ごとのchallenge exact matchによりAの過去2xxをB要求へ注入する故障を拒否する。
- [ ] DTOへtenant IDを追加せず、header値を表示・log出力しない。
- [ ] コア adversarial review、反対側レビュー、人間逐行確認、server/client品質gate、越境試験、凍結資産検査を通す。

## 10. 人間承認が必要な判断

1. 3節のexpected tenant header、要求ごとのchallenge header、response echo、success ack literal、canonical UUID規則を正式契約にすること。
2. 7routeだけへ適用し、login/session/logout/healthと他業務routeは後続に残すこと。
3. header欠落・不正・不一致をbody/query validationより先にoperation前の固定404、ackを成功2xx限定、対象応答を`Cache-Control: no-store`とすること。
4. 2xx ack欠落・不正を結果未確認として本文前に拒否し、自動retryしないこと。
5. #129・#131・#132の統合前には共有凍結資産を変更しないこと。
6. 承認後の開始は、#119とC1統合後の **ステップ 1/2 のみ**とすること。

## 11. レビュー状態

U-F13計画の最終P1反映と、その後に具体化したheader/ack案は未再レビューだった。2026-10-14の追補横断adversarial review第1周はP0 2 / P1 6 / P2 0（うちC2はP1 3）。全件採用し、metadata優先順位、no-store、cache再利用故障注入、mutation 5xxの結果未確認を追加した。反映差分の再レビュー後に人間承認を求める。

第2周はP0 2 / P1 2 / P2 0（うちC2はP0 1）。固定ackとno-storeだけでは過去応答注入を判別できない指摘を採用し、要求ごとのchallenge UUIDと成功2xxでのexact echoを候補契約へ追加した。P0反映だけを自動第3周で再レビューする。

第3周は第2周P0反映だけを対象とし、P0 0で可決。要求ごとのchallengeが過去応答注入を識別できることを確認した。第2周P1の追随差分は回数上限により未再レビューであり、人間承認時の確認対象とする。

## 12. 人間承認記録

2026-10-14、山田正輝が計画HEAD `e42a2ddbd2db58dd1fca642959ff4a2870299f63` の本計画を承認した。開始条件成立後も最初のステップだけを実装して停止する。U-F2・U-F6共通client、認可正本、スキーマ、凍結資産は着手前に実所有を再照合し、#129・#131・#132その他open PRの未統合差分を基線にしない。第2周P1追随の未再レビュー範囲は人間逐行確認対象として維持する。


### C1依存の更新（2026-10-17）

C1ステップ1はPR #144 / develop `3052e0db743877c7f15c0ec10daa0142cba7ab7e`へ統合済み。C1ステップ2（正規auth clientと検証済みstore）はCodex Dが同専用worktreeで実装中であり、C1全体の開始条件が成立したとは扱わない。`api/auth.ts` / `authStore.ts`と、最小追随中の`api/client.ts`はC1が一時所有し、統合後の基線から後続が再照合する。本計画の製品実装は今回開始しない。

### C1遅延Cookie追補の接続条件（2026-10-17）

山田正輝がC1の安全側への例外を承認した。旧login/logoutのCookie変更可能性を観測した場合、新世代も`verification-unknown`へ戻しcacheを破棄する。旧ユーザー/tenant/成功は採用せず、tenant-bound通信を止め、明示session GETだけで再確認する。資格情報やmutationの自動再送は行わない。UIは`stale`だけでなく新世代の`verification-unknown`も成功として扱わず、結果epochを照合する。C2はこの破棄境界を維持して業務operation前の応答tenant照合を追加する。C1が共有client/storeを一時所有し、統合後に後続が基線から引き継ぐ。今回C2/U-F3/保護routeの製品実装は行わない。

## 13. C1統合後の開始条件・所有（2026-10-18）

PR #147の実統合SHA493342be37d4383ca572f8d1c826a3f184a4d213を最新developとして再照合した。C1ステップ2の完了を確認し、C1待ちは解消した。PR #119/#129/#131/#132/#137および共有実行器Aは統合済みの資産だけを利用し、未統合PR #143の候補は基線に含めない。

山田正輝はC2/U-F3の実装・関連試験・既定レビュー・PR準備、その後のU-F13接続と専用環境の通し試験まで自律進行を指示した。各ステップ別の検証/コミットを維持し、以前の最初のステップのみという停止条件を今回の指示の範囲で解消する。人間逐行確認・正式受理・公開・マージを代行しない。U-F13の既定統合順は維持する。

C2は既存tenant_access、players/team-records router、共通app応答middleware/errorsの必要最小限とbackend固有試験、およびfrontend共通client/roster・既存TeamScreen/TeamMembersContentのretry/結果未確認境界と固有specを所有する。C1のauth.ts/authStore.ts、共有Pinia/QueryClientは変更しない。U-F3はLoginScreen/固有specだけを独立所有し、route登録はU-F13が所有する。

open PR #143はcore-areas.json/core_guard.py/test_core_guard.pyとrepository/authzの共有凍結資産を所有している。本C2は当該共有資産を変更しない。7routeのoperation_id/経路/DTO/認可対象/DB実行器/権限は不変であり、既存HTTP境界へ承認済みmetadata照合を追加する。必要な資産差分が実検査で判明した場合だけ、具体差分の正式ゲートを維持する。
