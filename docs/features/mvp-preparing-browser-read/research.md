# 起案根拠

API b3a8ef8bは単体127成功と実HTTP/DB11成功、独立127/11成功・0指摘。正式TB0052件は残る。UIは別単位の固定供給を待つ。

既存GameScreenE2eSupport.tsはTLS鍵生成、同.pyはランダム署名素材生成を含むため、そのまま実行しない。既存fixtureの非秘密固定素材とloopback HTTPモードを限定追加する。2026-10-24 JSTに独立した非認証HTTPserverでChromium149.0.7827.0がSecure/HttpOnly/__Host Cookieを受理する能力のみ検査。実製品auth試験ではない。既存共用Processの0700/0600・所有確認・子プロセス完走/異常終了・cleanupを保つ。

本単位は計画起案だけ、製品変更/新鍵発行なし。関連既存単位の計画/コードレビュー履歴や親#175正式追加1回は変更しない。

## 第1回独立計画レビューの反映

非作者/root/o5_final_reviewがplan3f4d2c98/research1418ad4aを全文確認しP0=0/P1=2/P2=0、是正要。①frontmatter planningは現在地導出が認識しないためactiveへ是正。②採用する明示read起動方式がscope未固定だったため、薄いGameScreenPreparingReadE2eSupport.tsを追加対象へ明記し、既存default sealed-uiと分離した共用関数を呼ぶ方式に固定。wrapperが唯一の技術方式とは主張しない。全2件採用、未採用0。製品コード未変更、これが第2回差分レビュー対象。新鍵発行禁止/fixture共有/正式7.7未達の境界は不変。

第2回差分/影響レビュー: /root/o5_final_review、対象plan e9a4fc1a/research735f6702、可決0/0/0。rootはplan末尾の対象版/日時/委任根拠で限定実装を承認。

## ステップ1の実接合と失敗履歴

UI供給は83e62a17→型是正bb0973d1→caller是正9e5c59c3を個別の通常mergeで取り込んだ。現在の接合baseは12a5dbb0446e4a817ba8f4c32b602a4692ec89e1。UI原コード基本2回（最初P1=1を全採用）、caller計画限定1/コード限定1（いずれも0）と独立175成功は別単位の記録に保持。今回のdriverへUIやAPIの別実装は追加していない。

| 実行 | 結果・原因・是正 |
| --- | --- |
| 初回 | 2failed。実login POST200後、既存Appの/team固定callerで/gamesへ戻らないことを現物で確認。UI側の最小追補承認と9e5c59c3で解消。成功Cookie/state注入や期待応答の代替なし |
| caller接合後 | 3failed。Playwright cookies(HTTP URL)がloopbackでもSecure cookieを絞り落とす検査補助の誤判定。独立した非認証serverで全cookie metadataはSecure/HttpOnly/domain127.0.0.1/path=/、HTTP URL指定時count0を再現。値を出さず全cookieからexact domain/path/属性を照合する検査へ是正 |
| 属性検査是正後 | 1passed/2failed。cross-tenant/不存在/明示再試行は成功。残2件はdriverが規則wireをsnake_caseと誤認した末尾assertionで、実際は正規camelCaseの6keyが表示・再読込・回復できていた。UI/APIを変更せず、特定field名の推測を除き表示JSONと実APIの保存snapshot全値の一致へ検査を強化 |
| 最終 | 実Chromium149.0.7827.0、実uvicorn/製品FastAPI/PG17.11・既存実認可fixtureで **3 passed / 12.4秒 / exit0**（exec session7722）。trace/video/screenshot/DOM snapshotは抑止、資格は専用0700/0600領域だけ。cleanup後pitchlog-authzコンテナ0 |

最終3件は、実loginのCookieとC2/no-store→20件page/実cursor往復→詳細/保存規則の同値/再読込、越境と不存在の404/非表示/明示再試行、実通信abortで自動再送せず旧内容を破棄→利用者の明示的session確認→実read回復。応答をroute.fulfill等で作らず、fault caseは通信abortだけを注入した。gamesへのPOST/PATCH等0件を観測。seedされた保存値のread受入であり、試合作成/1球保存/記録権/1試合/実機/運用HTTPSの成功ではない。

専用setupはenvDir:falseのViteと明示HTTP loopback readモード。TLS生成器と既存ランダム署名素材生成器を呼ばず、既存非秘密固定素材をApp生成前に置く。既存sealed-ui defaultとreal-game未達sentinelは維持し、sealed-ui全件は新鍵発行器を伴うため本委任では未実行。

共用Processの最終Vitestは8passed/3.26秒。HTTP/HTTPS modeと異常port、Python実bootstrapのモード外/非loopback OriginがDB起動前に拒否される3例、0700所有、正常/異常子終了・自分の資源cleanupを検査。対象Prettier/ESLint/vue-tsc、driver Pythonのbackend Ruff format/check/tyは成功。最初のRuff import整列1件は--fixで是正した。正式登録/7.7/TB005と親175正式追加枠は本単位では成立させない。

## 独立コードレビュー第1回P1の反映

非作者/root/csv_reviewは372bc169・base12a5dbb0・diff3e590d26を確認。独立browser3成功/12.7秒・Process8成功/3.48秒・資源残存0だったが、cursor送信漏れで先頭20件が繰り返されてもページ番号だけなら通る検査不足P1を指摘。P0/P1/P2=0/1/0として採用し、成功試験数だけでページ境界成立とはしない。

同scopeのE2e1関数と検査補助だけを強化。最初20IDはfixture66〜47、次9IDは46〜41と3/2/1のexact順、送信cursor=直前応答next_cursor、ページ内/間非重複、末尾cursor null/次無効、戻りcursor nullと先頭ID集合/表示RouterLinkの完全一致を確認する。root是正後の実browser3件は全成功/12.7秒、Prettier/ESLint/vue-tsc成功。prod UI/API/DB/helper起動/署名/Processは変更せず、過去失敗・第1回指摘・留保を保持。修正後の独立差分レビューへ提出する。
