---
feature: mvp-batted-operations-shared
status: active
承認: PO委任によるCodex主担当/root判断（2026-11-08 20:45 JST、本文対象SHAは次の採用記録を参照）
重さ分類: コア領域
branch: feature/mvp-batted-operations-integration-20261108
計画レビュー周回: 0
---

# 打球群の共通保存・成績接合

既MVPと操作単位実装の委任に基づく接合追補。基点c6718e32、唯一artifact 71f2726a。新しい野球意味を採用せず、既要件A-3/RBI-01〜09と明示観測を消費する。旧batted-out親本文4585f18aと宣言29e1640b以外は拒否する。

| ステップ | 作業・所有・完了条件 |
| --- | --- |
| 1 | root: authz/batted_operations_evidence_sql.py、repositories/ordinary_pitch_operations.py、stats/facts.pyと対応試験。12結果の既観測・唯一T1の走者別算入を保存/成績へ写す。SQL生成候補は未登録のまま固定し、親・宣言・資格・nonce・他関数の不変性を検査。打点の再計算をしない。独立レビューまで製品成功としない |
| 2 | root直列: compat842eff16、schema/head担当候補、P3 following5bf664a1、59球画面35926573を固定レビューして接合。first_ball_productの生成層へSQLを登録し、正式body/manifest・認可/tenant受理を公式helperで導出。元の認可/原子性/再送/結果不明の保証を維持。未知候補を通す検査緩和はしない |
| 3 | 共通lockのowned隔離環境で実画面新規作成→開始→打球/走者/54out→終了→成績27/CSV、再送/reload/故障全取消/越境を実測。同一HEADを固定し未到達を明記。必要CI/非作者最終レビュー後に通常PR統合 |

schema4資産/BE・FE headはcsv_continue担当、妨害の別群はgame_operations担当、旧83eの26件P3実測はrecovery担当。共有台帳・正式受理はrootのみ。PGの同時変更は禁止。旧ゴールデン期待/ABI/旧互換証明を緩めない。テスト用手定射影は数学・認可・実保存の証拠ではない。実機/信頼TLS/負荷/復旧は別のMVP受入条件として維持する。

この計画は既計画の接合範囲整理であり、正式契約受理・P6 blind・人間逐行確認を成立させない。候補作成に関与しないレビューを最終差分に要求し、P0/P1未解消を統合しない。
