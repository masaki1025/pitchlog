# TSK-544 T1正式契約への射影候補（J5/J6）

状態: **7.7未受理・正式契約未編集の候補**。正本は要件書v2.16とADR-003 v0.9（2026-10-21の単一7.3ゲート、確定コミット`52625ed6a6d7d27a212acfee16b97c8a97d987a5`）。比較元は`origin/develop`の`contracts/state-transition/`であり、TSK-564の#153候補は未統合として直列追随する。本書は期待値の独立導出、契約所有側の受理、7.7実値の人間確認を代行しない。

## 入力と検証器の最小差分

| 変更先 | 射影する確定規則 | 未確定・停止点 |
| --- | --- | --- |
| `input_axes_descriptor_v1.json`とschema | `event.perPitch.homeTouchOrder`を別軸にし、`not-required`と順序付き`observed`をexactに区別する。同一候補集合の順序反転も別coverage値。23フラグの必要十分条件、OUT3・RBIの閉入力と相反・越境を既存8制約のT1部分へ写す | #153後の共通digest、T2参照差分、軸の値域と無限の選手IDをcoverage代表値へ射影する方法は所有側レビュー。集合だけに正規化しない |
| `state_transition_contract_v1.json`とschema | `matrixRows`/`operationRows`/`undoRows`の既存109 caseを保持し、T1の閉入力・J6の順序必須条件・OUT3→非HR上限→得点者別RBI→COLDの評価順を規範行とcaseに追加する | 完全な10列期待値、履歴差分、各行のIDと出力値はP-6独立導出・所有側受理前に固定しない。J6の入力は出力11列目にしない |
| 手動fixture・branch coverage・handoff | 追加行/caseと原典の対応、正常と拒否の双方向負例、両runnerの消費対象を追随する | 受理履歴・凍結digest・署名は7.7値確認後。既存受理行と#153のT2成果を上書きしない |

`HomeTouchOrderV1 = {kind:"not-required"} | {kind:"observed", scorers: ScorerRef[1..4]}`、`ScorerRef = {kind:"runner", runner_id: PlayerRef} | {kind:"batter", batter_id: PlayerRef}`。`PlayerRef`は正式選手IDと一時UUIDをタグで区別する。OUT3後の有効得点候補集合を順序とは独立に作り、`observed.scorers`のexact-setと照合する。順序が必須なのは、規定最終回以降の後攻勝越し局面で、**非HRかつ有効候補数が決勝点成立までの必要人数を超える場合だけ**。不要時は`not-required`または整合した`observed`を許し、観測有無で計上値を変えない。既存caseは不要variantを明示して移し、暗黙の既定値にしない。原wire・codec版・順序列の保存先と限定resolverはU-S1の公開型/認可/拒否順が決まるまで正式化しない。

## J6正常・拒否・境界caseの候補

| 候補ID | 入力分岐・原典 | 必須の比較面または拒否 | 正式化前に必要なもの |
| --- | --- | --- | --- |
| `T1-S20-ORDER-A/B` | 同じ規則snapshot・同じ有効候補A/B、非HR、観測順だけA→B/B→A（A-1、E-1） | チームの勝越し点数が同じでも個人得点・RBIの帰属とcoverage値を別にする | 正式入力座標、全10列、P-6独立期待値 |
| `T1-S20-HR` | 打者を含む3人の有効HR、規定最終回以降の後攻（A-1、RBI-06） | 非HR上限を適用せず3人を計上し、打者本人を含むRBI判定へ渡す | 正式caseとP-6比較 |
| `T1-S20-EARLY` | 規定最終回より前の後攻勝越し（FR-005、A-1） | 非HR上限を発火させず有効者全員。順序不要 | 正式caseと規則snapshot型 |
| `T1-S20-OUT3` | 接触済みだが踏み忘れアピール等でOUT3後に無効（OUT3-01〜05） | 無効者は順序列に要求せず、得点/RBI/上限へ入れない | アウト種別・対象の閉観測型 |
| `T1-S20-MISSING/EXTRA/DUP/CROSS` | 必要時に順序欠落・候補不足/余剰・重複・他scope参照（E-1） | それぞれ独立して拒否。時刻/位置/最終得点で補完しない | 拒否型と優先順のU-S1受理 |
| `T1-S20-REPLAY` | 同一D5で順序またはcodec版を変更（E-1、同期DI2） | 原wireの同一性不一致として既存再送境界で拒否。取消は保存済み差分を逆適用 | U-S1の原本保存型と実接合試験 |

負例は外形S-1と意味拒否を混同しない。参照の未解決・別試合・別テナント、無効者を含む順序、候補集合不一致、必須時の`not-required`、未知codec版を別caseにする。これらのD5消費/拒否原本/混在バッチの前方確定はU-S1の既存契約へ接続し、T1独自のACKやHTTP分割を設けない。

## P-6追加7件の正式case化の境界

旧blind v2（SHA-256 `e12ae8b589aa48971a9b7ba4a408cc4b90aaa6ae9c27df9ca328493a18df04e4`）と旧比較候補は保全する。7件の正式`caseId`は現行109件には存在せず、すべて未割当。`001/002/003/004/006`はOUT3/HRの型付き入力と全出力を新caseへ固定してから、契約commit・blob/ファイルhash・blind ID↔case ID・比較射影を別版でP-6へ渡す。`005/007`は得点面とRBI面を分け、打球種別、失策または野手選択の有無、併殺送球失策の有無、走者の継続・停止後再発進、失策がなければ得点したかという記録員観測を必要なRBI-01〜09分岐に対応付ける。原典と独立した観測が無い欄は不足のままとし、期待値から逆算しない。旧版への曝露は解消済みとしない。

## 直列統合・停止点

TSK-564の実回答（2026-10-21）では#153が`game_end_contract_v1.json`・同schema・`appendix_e_consumer_handoff_v1.json`を編集し、共通descriptorは変更していない。推奨順は**#153の正式統合→本T1の共通descriptor/schema追随**。ただし#153の統合は未確認で、合意済みの所有解除ではない。T1変更後はT2の`inputAxesDescriptor.digest`、schema const、両loaderの定数、handoff artifactsへ機械的に波及しうる。T2の意味・本人署名を代行せず、参照hashの計算法（RFC8785とファイルbytes）を区別する。

P-6段階Aの固定結果/未検証範囲、G6-S01〜S08の担当別受理、P-7の公開入力同値性・認可済み読取口・J6原入力保存型が未成立。正式契約の編集はこれらのうち計画が要求する先行条件と編集所有を満たした後、コアレビュー・所有側受理・7.7完全前後値の人間確認の順で行う。製品計算コードと正式7.7は本候補では開始しない。
