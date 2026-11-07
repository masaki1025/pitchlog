---
feature: mvp-recovery-response-model
status: active
branch: fix/mvp-recovery-response-model
承認: PO委任によるCodex/root判断（対象569014ba全文、2026-11-07T18:27:33.054930+09:00記録）
重さ分類: コア領域（既復旧HTTP境界の型欠落修復）
計画レビュー周回: 1
確定ゲート周回: 0
---

# 旧試行照会の既応答を閉DTOへ接合する

起点b7c0b64c65c31a76976f4bde436d86410749804f。既PO委任による不具合修正であり、復旧状態・ACK・A5・再送/認可/停止の意味を変更しない。編集はsync router、新schema recovery_response.py、専用focused pytest、本計画/進捗だけ。正式asset/共有台帳/他WT/test_api_conventions.pyは非編集。

既 `sync.attempt_recovery.RecoveryResult` はB5/B6/B7をHTTP401/404/503へ写し、HTTP200はBindingControl.recover_attemptとfrontend/api/syncAttemptRecovery.tsで一致するretry_allowed/unresolvedの二値だけを返す。sync-protocol 6.3のAttemptResolutionにある他の停止照会状態をこの入口へ追加しない。これらはACKではなく、既RecordingAckResponseを内包/捏造せず再送後の既入口だけが既ACKを返す。

| # | 実装単位 | 検査/成立条件 |
|---|---|---|
| 1 | 既二値resolutionだけのstrict/extra-forbid DTOを宣言しrecover routeのresponse_modelと実返却へ接続 | 二値の実serialized形保持、未知/B5等/ACK/余剰/null/型不正拒否。既HTTP error分岐不変、公開replyへ新値を足さない |
| 2 | focused schema/route試験とconventions exactを照合し固定 | ルートresponse_model/openapi/実出力の閉検証、元downloads-only response_model=None集合を維持。基線のroute数/配列がrecover登録へ未追随なら、その既赤を残してrootへ報告し検査を除外しない。DB新起動なし。最終HEAD/差分SHA/残る独立確認点をcacheへ固定 |

限定計画確認後にrootのPO委任判断でactiveとし、必要範囲を実装する。型検査/影響pytestで検証し、実DB/新しい復旧認可の成功証拠とは記録しない。旧応答の真正性は既実portの範囲のまま、sourceやissuerを自由stubで肯定しない。


root非作者確認により対象569014ba/plan SHA9a5341e5042d5b9ae9e4850d0de7c21a9908b5d445cf3bb37cad1c712af3214fを既二値/既error分岐だけの修復としてPO委任採用。本人確認/署名を代記しない。最小範囲追補としてtest_api_conventions.pyのroute exact件数34→35とrecoverの既登録route期待配列への有限追加だけをrootが承認。元downloads-only response_model=None集合と全route型検査は不変更、除外・期待削除はしない。実装最終版の非作者レビューは別工程。
