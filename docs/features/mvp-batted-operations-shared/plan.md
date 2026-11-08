---
feature: mvp-batted-operations-shared
status: active
承認: PO委任によるCodex主担当/root判断（2026-11-08 20:34 JST、対象版9dfd4971の本文を時刻訂正。旧記載20:45は誤記）
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

## ステップ1候補の固定（2026-11-08 20:37 JST）

rootによるPO委任の範囲採用。計画初版9dfd4971は時刻を20:45と誤記したため20:34へ訂正した。独立計画レビュー未実施を0周のまま保持する。候補のSQLは生成だけで製品未登録、実PG未実施。T5は実T1効果の射影で、射影単位試験の手定入力を実計算/認可/保存の証拠としない。対象3suiteは162 passed/8.34s、Ruff/Ty成功。旧127検査から、SQL保存外不変5・新走者効果10・12物理結果と失策ID対向を含む。初回保存外比較テスト1赤/新射影fixtureのrunner status不足3赤はそれぞれテストを正しい新差分・厳密型へ直して解消した。検査条件や数学期待を弱めていない。

## ステップ2の候補接合途中（2026-11-08 20:47 JST）

842eff16をdb25f9e6へ通常merge後、v4旧実host/現v5を含む互換38件は311.61秒で成功、Ty0。旧53計算全値/旧11資産byteを保持し、4自己識別値以外の差分を拒否する。5bf664a1の後続4安打訂正を原観測へ再束縛する候補も通常mergeしたが、実P3成功とはしない。

first_ball_productの固定親overlayを登録し、公式BODIESからprepare1関数を生成（SHA9046f9bbcacb30f476a77c8fcd49a5c2f8721919aa076e45b4bd43c82d8ed665/85,023bytes）。owner/ACL/署名/nonce/他関数は変更せず、旧overlay親の検査も新overlayを経てactivebody全値照合する形で維持。生成正負8passed4.60秒、静的authz-function-bodies product OK、Ruff/Ty0。これは候補内の登録であり、正式受理/seal/CI/実PGは未了。

T5後発は、明示effects付きで射影失敗した入力をRBI観測無しでも旧一括算入へfallbackさせない。手定対向11passed0.45秒、旧fixture/数学期待を緩めない。step1の独立レビュー後にこの後発も対照する。schema/head担当候補と59球driverの接合は次であり、ステップ2全体を完了にしない。
