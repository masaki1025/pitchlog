---
date: 2026-09-04
topic: TSK-280 同期プロトコル — イベント契約の骨格の実装(製品コードの 1 本目)
branch: feature/sync-event-contract
---

# 作業ログ: 2026-09-04 TSK-280 同期プロトコル — イベント契約の骨格の実装(製品コードの 1 本目)

## やったこと

### /task-start

- Notion タスク **TSK-280**(既存 — TSK-279 の DoD で 2026-09-01 に起票済み。**重複起票はしていない**)を取得
- worktree `../pitchlog-worktrees/feature-sync-event-contract`(ブランチ `feature/sync-event-contract`・起点 `origin/develop` = `fdda374`)を作成
- 計画書雛形 `docs/features/sync-event-contract/plan.md` と本ログを作成
- Notion のステータスを **進行中** へ・ブランチ名をタスクへコメント

### 着手に至る経緯(2026-09-04 の判断)

TSK-250(データモデル正本化)の再レビュー中に、**製品コードの着手は TSK-250 を待つ必要がないことが判明した**。

| 事実 | 典拠 |
| --- | --- |
| **製品機能の実装は Phase の対象外**であり、着手可否は 6.1 の実装計画書ゲート(人間承認)で判断する | ハーネス設計書 **v1.13** 13 章(TSK-279 / PR #36・マージ済み) |
| クライアント側は `sync-protocol.md`(approved)が完全に決めている。**サーバー側スキーマだけが TSK-250 へ送られている** | 同書 11-2 |
| 検査基盤・正解ベクタ・サーバー DB スキーマの**いずれにも依存しない** | TSK-280 のカード(実測) |

TSK-250 の先行 B・C は未完了のままだが、**本タスクはそれらに依存しない**。
B は続き(第 2 群・第 3 群)を **TSK-317** として起票済み、C(TSK-271)は未着手。

## 決定

- **射程は `sync-protocol.md` 4 章「イベント契約の骨格」のみ**とする(TSK-280 のカードどおり)。
  7-1・7-2・7-3・7-4・7-6・7-7 と 8 章は後続へ送る — **すべてイベントの型に依存する**ため、
  型を確定する本タスクが最小の前提になる
- **重さ分類はコア領域**(同期プロトコル — 設計書 6.3)。sol xhigh・敵対レビュー・**人間の逐行確認必須**
- 置き場は **`frontend/src/` 配下**。**`contracts/` には置かない**(ADR-003 D-1-b)
- **正本は写すだけで再解釈しない。** 設計の不足を見つけたら実装で埋めず、`sync-protocol.md` の改訂ゲートへ回す

### /investigate

調査サブエージェント **3 本**(spec-checker / legacy-analyst / decision-tracer)を並列で投げ、
`docs/features/sync-event-contract/research.md` へ統合した。**重い箇所は Claude が原典を直接確認**(research.md の ◎):
正本 4 章の本体(`:218-448`)・5-5 の参加区分表(`:573-591`)・`scripts/design_relations/sync-protocol.json` の
`R-EVENT-FIELD`・`.claude/core-areas.json`・`frontend/` の構成。

**エージェント間の矛盾は無かった**(NFR-019(d) が本射程では書けない点は spec-checker と decision-tracer が独立に同じ結論)。

### /plan(計画レビュー 1 周目 — 2026-09-04)

裁定 4 件を人間から得たうえで実装計画書を書き、`codex_run.py review normal` にかけた。
**P0 なし / P1 7 件 / P2 2 件 — 全 9 件を採用**(不採用 0)。`計画レビュー周回` を 0 → **1**。

| ID | 指摘 | 採否と反映先 |
| --- | --- | --- |
| P1-1 | **#9 改訂版の V6/V8 は元イベントの参加区分に依存**し(`sync-protocol.md:583`)、2 表の総称ループだけでは判定できない | **採用** — 判断 8(参加区分 **resolver の注入**)を新設。ステップ 3 の合格条件に分岐テストと**未注入で fail-closed** を追加。負例 N-7 |
| P1-2 | **V12 はイベント値でない**のに封筒の `FieldId` に含まれるか未定義。VF4〜VF6 の「現 D4・現復旧世代・保持端末との結合」は存在確認では検査できない | **採用** — 判断 7(**`EventSlotId`(V1〜V11)/ `RequestOnlyId`(V12)を単一の規則表から導出**)。ステップ 4 は**注入済み verifier の結果を B4 / B9 へ写像**する形へ |
| P1-3 | **I3 の帰結 `B13`** が合格条件で固定されていない(`:424`) | **採用** — 負例 N-15 で `B13` を固定。判定不能(N-16)とは分離 |
| P1-4 | **DoD「全項目を覆う」と未割当要素の矛盾**(C1/C4・B3a・DI1・DI5・I1・K5) | **採用** — DoD を「**イベント値・要求境界・局所的な衝突判定・一時 ID 写像の骨格**」へ限定。2 節に**受け取り先を後続 α(キュー)/ β(ACK)/ γ(サーバー適用)として要素ごとに明記**し、**未起票分は `/pr` のクローズ処理で起票**すると決めた |
| P1-5 | **英語識別子の denylist は正本にない対応表を実装が決めてしまう**(2-3 は日本語の禁止語のみ) | **採用** — **eslint denylist を撤回**(3 節から `eslint.config.js` を削除)。判断 3(ID は正本 ID をそのまま使う)と単一 locus 検査で代替し、英語対応表が要るなら**正本の改訂ゲート**へ送る |
| P1-6 | **全スロット `unknown` と識別子の非混同検査が両立しない** — 値形式で D5 と一時 ID を見分けると **D5 の形式を実質決定**する((B) 論点 17) | **採用** — 判断 1 に「**値の形式(長さ・文字種・UUID らしさ)を検査しない**」を明記。provenance は注入した `isTemporaryId` で判定し、**値形式を見ないことを raw 走査で assert** |
| P1-7 | **N-1〜N-18 が計画書に未定義**。「負例がすべて red」は全ステップ共通の test green と矛盾 | **採用** — 6 節に**負例カタログ(入力・期待結果・正本要素)を新設**。DoD を「**各負例入力が拒否され、テスト全体が green**」へ書き換え |
| P2-1 | ファイル構成表と spec ファイルの不一致 | **採用** — 構成表を**新設 14 ファイル**(production + spec)へ更新し、担当ステップ列を追加 |
| P2-2 | 変異検査が正本オラクルを作業ツリーで直接編集する前提 | **採用** — **読み込み後のオブジェクトを改変する**形へ。`git diff --exit-code -- scripts/design_relations/ docs/design/` を合格条件に追加 |

**レビューが「指摘なし」とした点**: NFR-018 の境界(V8 を不透明ペイロードとして存在確認だけに留める線引き)と、
ステップ順序(配線 → 規則表 → 検査器 → 周辺契約 → 横断検査 → ハーネス登録)。

## 逐語照合表(H-59 対策 — ステップ 7 の `[手動・外部]` 成果物)

**機械 green には数えない。** 人間の逐行確認の入力として、`pnpm test` の出力から転記した 24 行。
台帳 **H-59**(自動検査 5 種が全部通ったのに未照合の項目が残っていた前例)への対応で、
「**何をどこと照合したか**」を列挙する。生成元は `frontend/src/lib/sync/prohibitions.spec.ts`。

### V1〜V12(正本 4-3)

```
V1 べき等キーD5 → eventFieldRules.ts / EVENT_FIELD_RULES・EVENT_IDENTIFIER_SLOT_IDS
V2 イベント連番D1 → eventFieldRules.ts / EVENT_FIELD_RULES（D1 付き経路必須・P3 禁止条件）
V3 記録権世代D4 → eventFieldRules.ts / EVENT_FIELD_RULES（D1 付き経路必須・P3 禁止条件）
V4 試合の識別 → eventFieldRules.ts / EVENT_FIELD_RULES（全イベント無条件）
V5 イベント種別 → eventFieldRules.ts / EVENT_FIELD_RULES（全イベント無条件）
V6 論理位置を定める値D2 → eventFieldRules.ts / EVENT_FIELD_RULES（参加区分条件・P3 禁止条件）
V7 ペイロード → eventFieldRules.ts / EVENT_FIELD_RULES（全イベント無条件）
V8 状態差分 → eventFieldRules.ts / EVENT_FIELD_RULES（取消可能条件・P3 禁止条件）
V9 置換・墓標の状態 → eventFieldRules.ts / EVENT_FIELD_RULES（墓標・改訂条件・P3 禁止条件）
V10 対象イベントの参照 → syncEvent.ts / TargetEventReference（試合・対象の D4・対象の D1）
V11 対象の期待版 → eventFieldRules.ts / EVENT_FIELD_RULES（P3 必須条件）
V12 記録権証明 → requestBoundary.ts / RequestBoundaryEnvelope・V12_BOUNDARY_RULES
```

### 5-5 の参加区分表 #1〜#12

```
#1 毎球入力 → eventKinds.ts / EVENT_KIND_RULES（群 A・論理位置を持つ）
#2 undo → eventKinds.ts / EVENT_KIND_RULES（群 A・従属）
#3 選手交代 → eventKinds.ts / EVENT_KIND_RULES（群 A・論理位置を持つ）
#4 タイブレーク開始 → eventKinds.ts / EVENT_KIND_RULES（群 A・論理位置を持つ）
#5 試合終了宣言 → eventKinds.ts / EVENT_KIND_RULES（群 A・論理位置を持つ）
#6 選手のその場登録 → eventKinds.ts / EVENT_KIND_RULES（群 A・同期順のみ）
#7 状態補正 → eventKinds.ts / EVENT_KIND_RULES・buildSyncEventKindSet（群 A・論理位置を持つ）
#8 墓標 → eventKinds.ts / EVENT_KIND_RULES（群 A・同期順のみ）
#9 改訂版 → eventKinds.ts / EVENT_KIND_RULES（群 A・元イベントの参加区分を継承）
#10 プレイの修正 → eventKinds.ts / EVENT_KIND_RULES（群 B・従属・変更版順あり）
#11 プレイ行の論理削除 → eventKinds.ts / EVENT_KIND_RULES（群 B・従属・変更版順あり）
#12 交代イベントの修正 → eventKinds.ts / EVENT_KIND_RULES（群 B・従属・変更版順あり）
```

**確認者・日付・対象 commit はここへ追記する**(コア領域のため PR 作成者以外が行う)。

## /implement(ステップ 1〜7 — 2026-09-05)

**人間承認 2026-09-05(山田正輝)** のうえで着手。1 委任 = 1 ステップ = 1 コミット。
Codex は `sol` / effort `xhigh`(ADR-001 のコア領域)。**Codex にコミットさせず、検証後に Claude が打つ**。

| # | コミット | 内容 | テスト |
| --- | --- | --- | --- |
| 1 | `145c249` | オラクル読み出し経路(`@design-relations` alias)+ V1〜V12 規則表 + `R-EVENT-FIELD` 照合 | 21 |
| 2 | `c0c6533` | 種別集合と参加区分 + `R-PARTICIPATION` 照合 + FR-040 の条件付き要素 | 31 |
| 3 | `590ad21` | 封筒の型と実行時検査(負例 N-1〜N-12・#9 の resolver 注入) | 76 |
| 4 | `8e88312` | 要求境界(VF1〜VF6・復旧世代の結合) | 102 |
| 5 | `b0c932b` | D5 の衝突判定(負例 N-13〜N-18・`B3b`・`B13`) | 120 |
| 6 | `fda5aa7` | 一時 ID → 正式 ID の置換契約(C2・C3) | 134 |
| 7 | (本コミット) | 4-7 の禁止事項照合 + 単一 locus 検査 + U-1〜U-4 の不在 assert + 逐語照合表 | **148** |

**依存のインストールは Claude が先に実施**(`pnpm install --frozen-lockfile`)。Codex にネットワークを渡していない。

### 差し戻し 1 件(ステップ 1)

初回の実装が **`requiredness` を 3 値へ潰して経路別の条件を捨てていた**。オラクルは
`"V2:イベント連番D1+P1・P2・P4に必須+P3は持たない"` と条件を逐語で持っているのに表がそれを落としており、
**ステップ 3 の検査器が「必須の存在」と「持たない値の不在」を判定できない**状態だった。
あわせて **V-ID の値域が `canonOracle.ts` の正規表現にハードコード**されていた(単一 locus 違反)。
`--resume` で同一ステップへ差し戻し、`conditions` の逐語保持・`/^V\d+$/` への緩和・由来コメントの 3 点を是正した。
**原因は計画書の記述が粗かったこと**(「ID・必須区分・shape」までしか書いていなかった)。

### 実装中に判明した事実(計画書へ追随済み)

| 事実 | 追随コミット |
| --- | --- |
| ステップ 1 の成果物に `conditions` が必要(上記の差し戻し) | `31e934a` |
| **群 A / 群 B は `R-PARTICIPATION` に無い**(正本 5-5 の見出しが正)→ 照合対象外とし、**M5 を参加区分の改変で代替** | `31e934a` |
| **`K4` は変更版順の定義行・`K5` は射程外**(キュー遷移に属する) | `31e934a` |
| **使えるオラクル関係は 2 本ではなく 4 本**だった — `R-V12-BOUNDARY`(VF1〜VF6)・`R-TEMP-ID-MAPPING`(C1〜C4)・`R-BOUNDARY` / `R-P3-BOUNDARY`(部分照合) | `9151634` |

**`R-BOUNDARY` / `R-P3-BOUNDARY` は 15 要素ずつあり本タスクは 4 要素しか実装しない**ため、
関係全体の exact-set 照合はせず、**実装する 4 要素の右辺の逐語一致 + 射程外要素の理由つき allow-list +
未知 ID で throw** という形にした(「全部やった」と誤って主張せず、正本の変化は取りこぼさない)。

## 未決・次の一歩

- **ステップ 8**(ハーネス登録)— `.claude/core-areas.json` の `sync-protocol.paths` へ実装資産を登録し、
  `tests/test_core_guard.py` の期待集合を**同一コミットで**追随、CI の frontend paths-filter へ
  `scripts/design_relations/sync-protocol.json` を追加して **fail-open を塞ぐ**。
  **6.3 規則⑤により敵対レビュー + 人間承認が必要**
- **人間の逐行確認**(コア領域)— 上の逐語照合表 24 行と、`FORB` に相当する射程外領域の不在を対象に含める。
  **PR 作成者以外**が行う
- **後続 α(キュー実装)/ β(ACK 契約)/ γ(サーバー適用)の起票** — `/pr` のクローズ処理で行う
