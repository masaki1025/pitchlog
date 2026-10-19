# C1既存契約とlogin/session相関の具体差分（人間判断用・未承認）

## 対象と位置付け

実基線は156dd139a893845428a1ecab69632143f7694e0b、C1完了は#147の統合493342be37d4383ca572f8d1c826a3f184a4d213。既存C1の承認・完了・本人確認を取り消さない。本資料は固定候補379aef2585bfca95d044e09d2c387b97e1887c41（[候補本文](login-session-correlation-decision.md)、SHA-256 `8c05872d4fae6940404c3d49c98345633ddd12e0d56fb3bc03e8412b1680ae77`）の説明を具体化するもの。新しいDTO・保存・状態遷移は未承認・未実装で、今回許可された経路接続へ混ぜない。

## DTOの前後とtenantの出所

| HTTP | 現行C1 | 新候補 | 変えない点 |
| --- | --- | --- | --- |
| POST /auth/login 2xx | `{status: 'authenticated'}`だけを厳密検証 | `{status: 'authenticated', tenant_id: canonical UUID}`の2項目だけを厳密検証 | login ackだけでは認証済みにしない |
| GET /auth/session 2xx | `{tenant_id: UUID, team_name: 非空文字列}`の2項目を厳密検証し認証済みへ進む | DTO不変。login成功で得た期待tenantと一致し、認証世代と認証意図が不変の場合だけ進む | team_nameは表示用。認可/tenant照合キーにしない |
| login追加照合の失敗 | 追加照合自体なし | 固定汎用503。tenant/内部理由を返さず結果未確認 | 401の資格情報拒否と区別。資格情報POSTを自動再送しない |

サーバーはloginが発行した提示値を既存`verify_tenant_id`へ渡す。署名・DB照合を通ったIDと期限だけを返し、入力team_name・localStorage・任意UUIDを信頼しない。既存app接続のthreadpool内でCookieのHTTP発行前に照合する。DB関数/列/grant/roleを増やさず、公開caller完全一致検査に`api.routers.auth.login → authz.verified_tenant.verify_tenant_id`の1組だけを追加する候補。追加照合前のtoken発行DB transactionは既にcommitし得るため、全取消や同一transactionとは主張しない。追加照合が失敗した場合、新しい成功Cookie/2xxをHTTPへ発行しない。

このDTO変更は厳密1項目clientと後方互換でない。backend/client/必須LoginScreen追随を局所1ステップ/追加PR1本として揃え、片側だけの公開をしない。

## 認証意図の識別・保持

候補のlocalStorage keyは`bb.auth.intent`。保存構造は`version: 1`、`intentId: crypto.randomUUID()`、`phase`、`tenantId`だけ。password/token/Cookie/team_nameを保存しない。

| phase | tenantId | 寿命と通信 |
| --- | --- | --- |
| pending | null | 明示login POST前に新intentIdで保存。ack未確認ならtenantを推測せず、session自動GETも行わない |
| expected | loginでサーバー検証されたUUID | login ack後に新intentIdへ更新。起動/reloadではsession GETを1回だけ許す。DTO・期待tenant・要求前後の意図/世代が一致するまでtenant通信0 |
| verification-required | 直前の期待UUID、またはnull | 自動GETなし。期待UUIDがあるときだけ明示session GET。nullなら明示再login/logout |
| signed-out | null | logout/password変更の通知時に新intentId。keyを削除せずtombstoneとして保持。起動時のsession自動復帰なし |

意図は認証の証拠でなく採用条件を絞る制約である。他タブ/古い応答のtenantを新要求へ流用しない。更新・比較・sessionのmemory採用は同名Web Locks exclusive lock `pitchlog.auth.intent`内の同期処理として直列化する。HTTP待ちはlock外。取得できなければ待機・自動再試行せず未確認、storage/lockが使えなければ通信/認証採用を開始しない。独自mutexやlocalStorageだけのCASは作らない。

**追加の可用性判断**: keyなし・削除・破損を初回だけの特例で認証しない。既存Cookieだけの自動復帰を廃止し、旧版からの最初の明示loginを要求する。Web Locks/storage利用不可の環境はfail closedとなる。これは既存C1より強い制限であり、今回承認済みとは扱わない。

## 旧Cookie応答の順序で生じる不足

1. Aのsession/保護要求を送る。
2. Bの明示loginが成功し、ブラウザへCookie Bが適用される。
3. 旧A応答が遅着し、スライディング更新のCookie Aがブラウザへ適用される。
4. Bのloginに続くsession要求がCookie Aで送られる。
5. 現行login ackはtenantを含まないため、正しいsession DTO Aだけでは「Bを認証するための確認にAが返った」を識別できない。

現行C1の「Cookie変更可能性を観測すれば新世代も未確認へ戻す」は維持する。ただし、ブラウザのCookie適用はJSの結果処理より先行し得て、別タブではstore/storage通知にも前後差がある。無効化の観測だけを新loginとsessionのidentity相関の証拠にできない。既存の世代比較だけで上記5を排除済みとは主張しない。

新候補ではB loginの検証済みIDを期待値として固定する。A session DTOは不一致なので採用せず、store/cache/success通知へ渡さない。旧Cookie変更可能応答を観測したら、旧IDを採らず現在の意図をlock内で読み直しverification-requiredへ進める。同じ要求による通知/破棄は1回に集約する。Cookieそのものの適用/送出をJSで防ぐ保証ではない。B確定後のroster7経路では、C2のexpected B/context A比較が業務operation前の404で拒否する。

## 失敗時の利用者操作

| 事象 | 状態・画面 | 利用者が選べる操作 |
| --- | --- | --- |
| login ackを検証できない/通信断/追加照合503 | verification-required(null)、結果未確認。成功表示/旧cache復元なし | 資格情報を再入力して明示login、または明示logout。期待ID不明なのでsession GETで別tenantを採らない |
| ack Bは有効、session非401失敗/DTO不正/tenant A不一致 | verification-required(B)、cache破棄、tenant通信拒否 | 「再確認」でsession GETだけ1回。B一致で回復、不一致なら未確認継続。再login/logoutも可 |
| session401 | signed-out、サーバー未認証 | 明示login。資格情報再送は自動で行わない |
| loginの確定拒否 | verification-required(null)、固定拒否表示 | 明示login/logout。**既存C1の旧store/cache保持から、送信前破棄・拒否後も非復元へ変更する候補** |
| logout結果未確認 | signed-out維持、完了表示なし | 明示操作のみ。自動POST/保存済み資格情報再送なし |
| storage/lock失敗・意図なし | 未確認、保護画面/APIなし | 環境を利用可能にして明示login/logout。仮tenantや旧Cookieだけの復帰は不可 |

## 今回求める判断と残る証跡

推奨は、上のDTO/出所/固定503・限定caller、意図の保存/排他・初回再login/可用性低下、拒否後もcacheを復元しない変更、局所1ステップ/追加PR1本を明示して承認すること。相関追補の必要性だけの承認をこれら具体値の承認へ読み替えない。承認後も実装・全件検査・既定レビュー・人間逐行確認を省略しない。

既存Vitestと専用の実DB・既存Playwrightで、A/B切替、遅延login/logout/session/保護応答、再確認の前後競合、同一通知重複、2タブ/reload/タブ終了、意図破損/削除、lock/storage拒否を検証する。未検証のものを受入済みとしない。対象外の既存DELETE/lineup/password等のtenant通信全体や同tenantの別token識別まで保護したとは扱わない。
