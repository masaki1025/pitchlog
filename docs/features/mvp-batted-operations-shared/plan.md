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

first_ball_productの固定親overlayを登録し、公式BODIESからprepare1関数を生成（SHA9046f9bbcacb30f476a77c8fcd49a5c2f8721919aa076e45b4bd43c82d8ed665/85,023文字）。owner/ACL/署名/nonce/他関数は変更せず、旧overlay親の検査も新overlayを経てactivebody全値照合する形で維持。生成正負8passed4.60秒、静的authz-function-bodies product OK、Ruff/Ty0。これは候補内の登録であり、正式受理/seal/CI/実PGは未了。

T5後発は、明示effects付きで射影失敗した入力をRBI観測無しでも旧一括算入へfallbackさせない。手定対向11passed0.45秒、旧fixture/数学期待を緩めない。step1の独立レビュー後にこの後発も対照する。schema/head担当候補と59球driverの接合は次であり、ステップ2全体を完了にしない。

## 共有schemaと実計算→T5の接合（2026-11-08 20:56 JST）

82c98b9eの閉4schema/d.ts、BE/FE head・専用10実入力helperを通常mergeした候補。rootは既defs差分がT1と打球観測だけ/Value・Success2variant不変を構造照合し、BE/FE headの全差分を静読した。新NoRun headは実凡打/犠打のApplied override・空typed effects・得点/打点/失点False・score不変だけで、他結果へ自動拡張しない。正式ゲート/全候補の非作者最終採用は別に残る。

独立SQL限定REPORT3150562d…のP2（NULLの許可述語がNOTでUNKNOWNへ落ちる）を採用し、mismatch/targetの2pattern×3箇所をIS NOT TRUEへ是正。CSV担当のread-only追補が全文を旧生成の6箇所だけの置換として照合、owner/署名/role不変。新canonical/公式生成SQL SHA c2758d69d452fba961fc63459e84e951a2600129a4cf65c03aedaa44f5afc55f、PG compileは未実施。

rootは実host71f→閉schema/head→V7/V8/current codec→既生成T5へ10入力を通し、全10件で原始27項目available、RBI-04の得点1/打点0、犠飛1/1、公式失策/犠打失策各1を確認（10passed2.31秒）。公式1失策の実fielder ID供給が欠けていたので、観測countが厳密int1・実official UUIDの時だけ既T5 participantへ写す。bool Trueを1へ補修する入力は欠測のまま拒否。野球式は生成T5から複製せず、手定応答/仮frame/DB投入を使わない。この成功は数学・射影接続であって実DB/画面59球の成功ではない。

接合後BE生成/旧得点/新実接続4suite151passed7.72秒、FE schema/wire2suite68passed2.34秒、Vue/Ty/Ruff成功。59球driver359も候補へ通常merge済み、実PGは共通lockと接続経路の確認後に実施する。root新helper/後発は非作者レビューへ渡す。

## 初回owned配置停止と機械追随（2026-11-08 21:07 JST）

固定ee8b3e52の59球run1は36.74秒でCURRENT49配置の「初球関数の適用本文が凍結値と不一致」で停止。画面作成/記録は未到達、DB business監査未実施。source不変/owned削除/共通lock解放、manifest263220a1787f915ac076069c119332429f4b0959fe1f6281c08dcaf88e1e3896。長履歴の接続Timeout/旧55の503とは別の停止である。

CSV担当が公式_selected_product_ddlとcanonical全関数を静的照合し、persist_start_pitcher_entryだけ旧0db3→71f artifact pin3箇所が追随漏れと特定。条件/権限/他byte差0。rootが公式BODIESから該当1SQLを再生成、2b82a2ea…→69853efb1ede406bdf8df0174c93e103e51cd5f7d0f433d69938d6bb35132331。PGへ進む前に全first_ball登録関数の適用本文・欠落・重複を照合し、旧3pin再導入を元の凍結ゲートで拒否するテストを追加（2passed6.48秒）。生成値追随の委任判断として採用し、照合条件は変更しない。同版の無根拠再走をせず、この新固定版で次owned実測へ進む。

記録単位の訂正: 4006生成9046f9bbの85,023は文字数（UTF-8 85,347bytes）であり、bytesと記載したのは誤り。NULL-safe修復後c2758d69は85,077文字/85,401bytes。SHAは変更していない。
