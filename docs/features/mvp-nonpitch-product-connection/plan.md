---
feature: mvp-nonpitch-product-connection
status: active
承認: PO委任によるCodex主担当/root技術具体化（2026-11-07、既MVP操作単位）
重さ分類: コア領域
branch: feature/mvp-nonpitch-product-connection
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-nonpitch-product-connection
created: 2026-11-07
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
---

# 申告敬遠の真正非投球 PlayRow を同一製品経路へ接ぐ

## 単位と原典

現行要件書の毎球イベント種別・投球数境界（185行付近）、A-2/BF 帰属（1213行付近）、既 `state_transition_contract_v1.json` の `ST-MATRIX-9971ebafa8bb7fda` を正とする。最初の厳密正例は `batting-result.intentional-walk`、`non-pitch-event`、0アウト・一三塁・0-0である。打者一塁、既一塁走者二塁強制、既三塁走者保持、打席終了、四球/与四球を算入し、当該操作の投球数寄与は0とする。既累計球数を消さない。旧全golden/通常投球/交代責任を保持する。空塁や別countをこの一例だけから一般化しない。

申告敬遠の入力は投球コース・球種・球速を要求しない。観測不足の守備走塁/RBI/OUT3因果、未対応の他非投球操作を固定成功へ変換しない。5count交代時の四球責任は既採用原典と `walkResponsiblePitcher` を使い、別計算を作らない。今回T2は既 `evaluateEndCondition` の単一核へ T1 出力を渡し、終了条件を常時 false にしない。T5 は既 `native_projection`/生成 facts の非投球0 credit と四球/BF帰属を使用する。全比面と実原本照合が成立しない時は閉拒否する。

## 所有と共有接合

担当WTで編集するのは `frontend/src/domain/**` の必要差分、唯一artifactの公式ビルド候補、`backend/src/pitchlog/sync/nonpitch_payload.py`・`nonpitch_execution.py` と専用試験、この feature 文書。共有 `api/routers/sync.py`、P3 source、既 terminal/ordinary physical mapper、同期核、CSV producer、正式 contracts・pin・manifest・認可/DDL は実編集せず、前後 SHA 付き cache patch/正式追補案を root へ渡す。既計算を Python/SQL に複製せず、二つ目のartifactを作らない。既入口の拒否順・D5同本文再送・結果不明・記録権・tenant 分離・原子性を維持する。

## 段階と検証

| # | 実装単位 | 完了条件 |
|---|---|---|
| 1 | 既裁定 T1 の申告敬遠1単位を唯一核へ追加 | 上記正例の全値、既通常全golden、非投球0 credit、未知/別結果/投球入力混同/未対応状態拒否、同一artifact再ビルドと型・純試験 |
| 2 | 閉 V7/T2/T5/物理保存の接合候補 | 新閉codec/hostと既T2/T5を真正writerへ結ぶ。共有pathは cache patch。event/PlayRow/runner/receipt/checkpoint/水位の同TX保存と元D5再送、故障全取消を実 owned PG で検証 |
| 3 | 実画面から次球までと固定候補レビュー | 新規作成/開始→既球で正規一三塁→申告敬遠→次球→GET/reload、拒否/越境/旧source一致。候補の非作者確認・正式資産/7.7/統合は root 直列管理 |

既原典で未確定な member/入力例は具体票へ記載し、その箇所だけ成功にしない。全非投球・UI一般入力・訂正取消/正式統合・P6 blind/実機は本単位で完了扱いしない。owned DB/browser は共通 flock を全寿命取得する。

## 操作単位採用後の明確化

root の PO 委任による技術計画採用は cache `mvp-nonpitch-unit-adoption-root-20261107/ADOPTION.json` に元本文 SHA と判断を保持する。ここでいう「非投球 0 credit」は **投球数への今回寄与だけが 0** という意味であり、四球/与四球/BF 等の既裁定寄与を 0 としない。「全比面」は request/response、T1/T2、保存原本・receipt・checkpoint の対象全 member を同値照合する意味である。実正例は原典の一三塁座標へ真正に到達して検証し、他座標の正式成立へ拡大しない。

## 隔離縦断候補の追補

root の PO 委任による技術接合判断で、`feature/mvp-nonpitch-vertical-candidate` 専用 WT だけに、固定 shared patch（既物理mapper・V7読取・prefix reader）、v3 の閉 schema/d.ts、唯一 artifact の公式ビルド候補と従属 manifest/pin/witness/現行 fixture、v3 限定 GET 行型、既保存 PlayRow 挿入の閉分岐、投球画面の申告敬遠導線、専用試験を直列配置する。0045の27 metric CHECK追随は既採用差分の同欠落を再利用する。旧初球/v1/v2 の公開型、旧 golden の数学値、通常投球と未対応非投球の拒否は維持する。

候補 WT の source commit・実 owned PG/HTTPS 成功は正式 contracts/pin/認可資産の採用、7.7記録、独立レビュー、公開 PR の成立とは別に記録する。root が候補全 path と SHA を直列に統合・再派生し、非作者が固定候補を確認する。実画面試験は新規試合の通常2球で正規一三塁へ到達し、申告敬遠・同本文再送・次球・GET/reloadを保存41列、公開35key、T5原本27群と照合する。
