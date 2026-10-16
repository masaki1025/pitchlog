# 調査メモ: U-G2 の面切りと、ProjectionPort・ContentValidationPort の帰属(TSK-396)

- 基準: develop `e7e8d3a4`(2026-10-16)。行番号はこの時点の実測
- 依頼: PO 指示 2026-10-16(master 経由)— ① カードのステップ 1「修正イベントの受理・永続化と下流再計算が同一トランザクションで不可分でないこと」の確認 ② ProjectionPort・ContentValidationPort を TSK-396 で扱える範囲と U-X1 の凍結領域との境界(**凍結中の計算核を複製・迂回しない**)

## 1. 結論

| 問い | 結論 | 決め手(典拠) |
| --- | --- | --- |
| 面切り(リスク③) | **不可分**。修正の受理・永続化と下流再計算は、現行の正本では同一トランザクションに入ることが規範 | 要件書 FR-012 の受け入れ基準「べき等キーの記録・イベント保存・prefix 更新・**状態遷移**が単一の DB トランザクションで確定する」(`requirements-pitchlog-2026-07-22.md:328`)/ サーバー側の T4(状態遷移)= 投影の更新(`data-model.md:1055`・`:1064`)/ **下流再計算は投影を作り直す**(`data-model.md:665`)/ 再計算の起点は変更されたイベントの D2 以降(`sync-protocol.md:1322`)/ P3(プレイ修正・交代修正)は T1・T2・T4・T6・T7 を 1 トランザクションで確定(`sync-protocol.md:1269`・`backend/src/pitchlog/sync/change_path.py:271`) |
| ProjectionPort(T4) | **U-X1 の凍結領域**。TSK-396 では扱えない | 投影の作り直しのうち「状態と帰属の再導出」は (α) 状況判定 = 対象計算(`ADR-003:1120-1122`)。投影の列が状況計算の結果を NOT NULL で要求する(`play_runners.status`・`responsible_pitcher_id` — `backend/src/pitchlog/db/game_state/models.py:796-798`)。U-S1 の設計もポートの所有単位を U-X1(凍結中)としている(`docs/features/us1-sync-apply-core/design.md:38`) |
| ContentValidationPort(⑦ / P3 ⑥) | **状態に依存する判定は U-X1 の凍結領域**。状態に依存しない判定は、正本が中身を定めていないので、TSK-396 が書けるものが無い | 状況判定ベクタの出力に `rejected-precondition` / `rejected-invalid-payload` がある(`contracts/state-transition/state_transition_contract_schema_v1.json:1502-1507`)・NFR-018 の状況判定の出力に「操作結果の区分」(`requirements-pitchlog-2026-07-22.md:981`)/ ⑦・⑥ の中身は sync-protocol が列挙していない(`sync-protocol.md:701`・`:727`・B14 は「意味規則・入力制約」だけ `:794`)/ 形式検査は U-S1 の適用核がポートの手前で済ませている(`prefix_path.py:611-639`・`change_path.py:173-190`) |

## 2. 面切りの判断の筋道

1. ADR-003 D-14-l は下流再計算を 3 つに分ける(`ADR-003:1120-1124`): ① 状態と帰属の再導出 = (α) 状況判定 / ② 再集計 = (α)(β) / ③ **イベント列の編集そのもの = 対象計算ではない**。U-X1 の設計も「U-G2 が主所有するのは ③(受理)、U-X1 が分担するのは ①②」とする(`docs/features/ux1-state-calc/design.md:37`)
2. **③(受理・永続化)だけを先に確定し、①(再導出)を後で行う形は、FR-012 に反する**。FR-012 は状態遷移(= サーバー側の T4 = 投影の更新)を、イベント保存と同じトランザクションで確定することを求める。sync-protocol 8-1 も、T4 が欠けた状態を「イベントは残るのに状態が古いまま。確定記録が一時的に矛盾する」という障害として扱う(`sync-protocol.md:1225`)
3. 投影を「イベントの材料化だけ」(③)と「状態の導出」(①)に分けて、前者だけを書くこともできない。走者の行は状況計算の結果そのもの(どの塁に誰がいるか・責任投手)で、列が NOT NULL(`models.py:796-798`)
4. したがって、**単位分割の計画書が予定した場合(リスク③)が実現した**(`docs/features/product-impl-unit-split/plan.md:480`)。同計画書の手順は「当該単位の実装を止める → カードを凍結へ移し U-X1 へ依存を張り直す → 下流単位の着手可否を更新 → design.md 4 節の帰属表へ移動を追記」(`:240-252`)

## 3. 影響 — 何が止まるか(PO 指示「凍結中の計算核を複製・迂回しない」の帰結)

- **ProjectionPort は T4 を含むすべての経路で必要**(P1・P2・P3 — `sync-protocol.md:1267-1269`)。**新しいプレイの記録(毎球入力)は D2 の採番を伴うので P2**(T1・T2・T3・T4・T5・T6 — `:1268`。D2 = 論理順序 `:37`)。**訂正(2026-10-16)**: 初版は「P1 は通常の 1 球の記録」と書いたが誤り(master の実測で訂正)。T4 は P1・P2・P3 のすべてに含まれるので、結論と影響の範囲は変わらない。本物の ProjectionPort が無い間は、`PORT_IMPLEMENTATIONS` に登録できる実装が揃わず(`backend/src/pitchlog/sync/ports.py:133-143`)、**「1 球保存」は U-X1 の凍結が解けるまで通らない**。これは U-G2 に限らない、MVP の最短路の制約である
- **複製・迂回にならない代替は無い**: 状態を導出しない投影(③ だけ)は FR-012 の原子性を破り、確定記録を矛盾させる(= 迂回)。状態依存の内容判定を省く validator(全部受理)も迂回。状態依存の判定を別に書くのは複製(NFR-018 の P0)
- **凍結の解除条件**: ADR-003 段階① の完了(`product-impl-unit-split/plan.md:386`・PO 裁定 2026-10-10 `docs/worklog/2026-10-10-adr003-stage2-owner.md:110`)と、U-X1 の着手条件 P-1〜P-9(`docs/features/ux1-state-calc/design.md:70-79` — 段階 1 の TSK-237〜239 は計画書なし・未了、D-2 の発効)

## 4. カードの扱い(提案 — PO の判断)

- **TSK-396**: 単位分割の手順どおり、**実装を止め、凍結側へ移して U-X1 へ依存を張り直す**。受理の主所有(③)は U-G2 に残る(FR-007/011 の「編集そのもの」)が、単独では緑にできない。Notion の状態語彙に「凍結」は無い(`.claude/notion-map.json` — 近いのは「ブロック中」「保留中」)ので、どれにするかは PO の判断
- **ProjectionPort・ContentValidationPort は新規カードにしない**。両者の本物は U-X1 の成果物であり、**U-X1 のカード(TSK-544 状況判定 / TSK-545 終了判定)への最小追補**を提案する: 「同期核の ProjectionPort(T4)と ContentValidationPort(⑦・P3 ⑥ のうち状態依存の判定)の実装、および投影表に適用核の印を要求する DB トリガ(U-S1 の申し送り R-12 — `docs/features/us1-sync-apply-core/plan.md:37`)」
- **正本の空白**(提案 — 別途): sync-protocol 9-2 の境界表に、T4 と ⑦/⑥ の「意味規則の正本・強制点・所有単位」の行が無い(`sync-protocol.md:1406-1429`)。ポートの所有単位は feature 文書(U-S1 の design)にしか無い

## 5. PO が別の道を選ぶ場合(538 は推奨しない)

- **FR-012 の「状態遷移」の解釈を改め、T4 を「材料化」と「導出」に分ける**: 材料化だけを今の製品経路に入れ、導出を U-X1 の解凍後に後追いさせる。**要件書・sync-protocol・data-model の改訂(確定ゲート)が要り**、走者の行の NOT NULL 制約の見直し(DDL)も要る。確定記録が一時的に矛盾する期間を製品として受け入れる判断になる
- 538 が推奨しない理由: FR-012 が防ごうとしている事故(途中クラッシュでプレイが消える・二重適用)と、sync-protocol 8-1 が障害として扱う状態(イベントは残るのに状態が古い)を、設計として常態にするため

## 6. 依存の現況

- U-S1(TSK-391・#132): develop にマージ済み(`966d7a38`)
- U-R1(TSK-392・#143): draft。D4 方式は現公開範囲外 — 本調査では決め打ちしない
