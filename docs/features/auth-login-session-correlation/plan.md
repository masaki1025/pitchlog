---
feature: auth-login-session-correlation
status: active
承認: 済(2026-10-18・本会話)
重さ分類: コア領域
branch: feature/auth-login-session-correlation
created: 2026-10-18
計画レビュー周回: 3
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# C1 login/session相関追補

## 承認と基線

2026-10-18、本会話で04ecb061の比較資料に示す追補、計画追加、実装・検証が承認された。元比較資料SHA-256は`592d733a4986c02daba9d03f3a2d894a1dc05a6a78c078f81aaf453d158c84a2`。原資料の「未承認」は当時の状態であり、その固定履歴を書き換えない。基線は最新origin/develop `5bb1ff89306712c1de61c3a0152141c8f771b3a0`。#148の同期正本追随は認証製品ファイルと重複しない。

既C1完了・本人確認を取り消さず、局所1ステップ・追加PR1本。元候補のレビューは第2周両経路の指摘を採用、第3周CodexはP0限定pass。最終P1/P2と局所PR構成は未再レビューだったことを保持する。製品実装レビューは今回の新しい相関差分について通常枠（全文1＋差分1）を使用し、既C2/U-F3/U-F13の消費済み枠をリセットしない。

## 契約と対象

- login 2xxを厳密2項目`status: authenticated`とサーバー検証済みcanonical UUIDの`tenant_id`へ変更。既存verify_tenant_idでCookieのHTTP発行前に照合し、失敗は固定汎用503・成功Cookieなし。token発行transactionまで全取消とは主張しない。
- session DTO不変。DTOの構造、期待tenant、認証意図、世代が全て一致した場合だけ認証済み。storageは相関制約でありサーバー認証・認可の代用ではない。
- `bb.auth.intent`はversion/intentId/phase/tenantIdだけ。phaseはpending、expected、verification-required、signed-out。全更新と比較・採用はnative Web Locks `pitchlog.auth.intent`のexclusive/ifAvailableで同期的に直列化し、HTTPはlock外。
- login前に旧store/cacheを破棄、拒否後も非復元。結果不明は未確認、資格情報・変更要求の自動再送なし。旧Cookie変更可能応答は現在意図を未確認へ無効化するだけで旧tenant/成功を採らない。同一要求の通知は一度。Web LocksはCookie適用自体を防がない。
- 同tenant別タブでsession確認するだけでは共有意図を変更しない。別タブの意図変更で旧タブは認証を破棄し、新tenantへ自動復帰しない。これをU-F13残余P1の2件へ対応付ける。
- storage/lockが利用不可なら通信・採用拒否。画面へ理由と環境回復の手順を表示し、機能しない再loginの循環を作らない。secure context、Web Locks、localStorageが利用可能なブラウザを必要とし、旧Cookieだけの初回自動復帰は廃止する。

## 編集所有・PR境界

Codex Dが本枝のbackend auth router/schema/caller完全一致試験、frontend api/auth・意図管理・authStoreと固有試験を編集する。#150のC2 client、#151のLoginScreenは同じDだが既存候補を保全し、接合差分は固定元HEADと別記する。U-F13のrouter/App/JSONは既存専用枝で編集する。LoginScreen*の宣言→JSONの承認済み順序を保持し、未登録のままゲートを迂回しない。他担当の未統合枝は取り込まない。結合は許可済みの専用検証枝だけで行い、単独検査と混同しない。

## 影響する正本

正本への反映なし。承認済み04ecb061の局所追補を実装し、既存の認可・凍結資産・route matrix・DB権限は変更しない。新たな正式資産差分が必要になった場合は7.7を含む個別ゲートへ具体値を提示する。

正本体系外だが同一PRで更新するもの: 本計画・固有worklog・追加判断資料、backend auth router/schemaとcaller/HTTP/DB試験、frontend auth/authIntent/authStore/clientと固有・consumer試験。U-F3とU-F13の製品差分は既定の別PR境界を維持する。

## 実装ステップ

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 相関DTO・意図管理・store/client・必須UI追随と単体試験 | 不一致/旧応答/意図変更拒否、旧cache非復元、自動再送なし。両P1解消、失敗回復UI。単独と結合の全品質gate、既定レビュー、専用実DB/API/画面の通し試験。未確認・失敗・別tenant複数タブ・遅延・storage/lock拒否を含む。 |

## 検証と人間ゲート

root Ruff/ty/全pytest、backend format/Ruff/ty/全pytest、frontend Prettier/ESLint/vue-tsc/全Vitest/build、既存契約検査を実施する。隔離DB・検証環境だけを使用し共有環境を破壊しない。実画面ログイン→session→選手一覧→追加・編集→reloadは別途実測する。正式資産/7.7に変化があれば具体値を別提示する。通常push・Draftは許可済み。本人逐行確認、公開、Draft解除、マージは未許可・未実施。
