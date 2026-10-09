---
type: investigation-record
date: 2026-10-03
agent: decision-tracer
---

# 調査報告(原文): DSL の表現力は検討されたか

> **本ファイルは 2026-10-03 の `/investigate`(TSK-405)でサブエージェント `decision-tracer` が返した報告の原文である。**
> 2026-10-09 にセッションの記録から取り出し、**内容を変えずに**収載した(候補基準一覧〔[../research.md](../research.md) §9〕の出典を再現できるようにするため)。
> **報告の主張は当方未検証。** 行番号は報告時点の版(develop `f20323cb`、または `feature/domain-calc-dsl` の worktree)のものであり、現在の行とずれている場合がある。検証は計画書のステップ 2〜3 で行う。

---

## 結論(計画に直接効くもの)

1. **ADR-003 v0.1 の確定ゲート 25 周では、DSL の式の表現力(書ききれない計算・上限・手続き的記述・エスケープハッチ)は論点として出ていない。** DSL で足りるかどうかは、「理由」節の前提(テーブル駆動の状態遷移 + 単純な算術集計)として置かれただけで、検証されていない。
2. **確定ゲートを通ったのは「射程の要素一覧」(D-1)まで。式の具体的な文法(8 種の式ノード、ガード = 比較 1 個、reducer のフィールド構成)を決めたのは TSK-235 のステップ 13 の `model.schema.json`。** この文法は ADR の確定ゲートを通っていない。
3. **TSK-235 は、本物の対象計算を 1 件も DSL で書いていない**(計画で明示的に除外)。書いたのは合成 fixture 1 件(おもちゃの計算)だけ。表現力について計画レビューで出た指摘は「表示書式」の 1 件だけで、状況計算の式の表現力に対する指摘は見つからなかった。**これが U-X1 の最大のリスク。**
4. **書けない計算が見つかったときの経路は「D-1 の見直しトリガー → 停止 → ADR 改訂ゲート」の一本だけ。実装側の裁量で使える逃げ道はない**(手書きの経路は ADR が閉じている)。前例が 1 件ある(TSK-235 → ADR v0.2、確定ゲート 27 周)。

---

## 1. 確定ゲート 25 周で表現力の議論はあったか

**事実**: 25 周ぶんの変更履歴(`docs/adr/ADR-003-domain-calc-method.md:16-40`)と、ゲートの要所をまとめた worklog(`docs/worklog/2026-08-18-adr003-domain-calc-method.md:57-75`)を通読した。ご指定の 4 論点(書ききれない計算 / 上限 / 手続き的記述 / エスケープハッチ)は、**どの周にも出ていない**。

議論が動いた要所は次のとおりで、どれも式の表現力の話ではない(worklog `:57-65`)。
- (b)② は実現不能という結論
- 防御 3 案の否定
- 経路一致検査
- FIP の非負矛盾
- undo の履歴の持ち方
- 表示名をどこまで正本に入れるか

**近いが別の論点が 2 件ある**:
- 17 周目(`ADR-003:32`): 表示規則では条件分岐・部分文字列操作・数値整形を**意図的に書けなくした**。表示の射程を絞る決定であり、状況計算の式の話ではない。
- 19 周目 P0①(`ADR-003:34`): 「種別だけでは連続 undo を実行できない…製品経路が DSL の外に履歴解決ロジックを持つことになる」。DSL の外にロジックが漏れる懸念は出ている。ただし対処は**入出力の設計変更**(履歴スタックに差分を持たせる)で、文法の拡張ではない。

**表現力について確定ゲートの外で残っている記述**:
- 前提: 「本ドメインの計算はテーブル駆動の状態遷移と単純な算術集計」(`ADR-003:425-426` 理由節)。検証の記録はない。
- 調査段階では表現力不足がリスクとして挙がっていた。
  - `docs/features/nfr018-domain-calc-adr/research.md:74`: DSL 方式の主な破綻点として「DSL の表現力不足」と明記。
  - `docs/features/adr003-domain-calc-method/research.md:89`: 次点案(QuickJS)の採用条件を「DSL で表せないロジックが増えた場合」としている。
- v0.2 の断定: 「状態遷移・有限の算術という中核の射程は現行のまま足りており」(`ADR-003:125`)。出典の `docs/features/adr003-display-primitives/design.md:67` にも根拠の記載はない(典拠なし)。

## 2. ADR が確定した範囲と、実装へ送り出した範囲

- **ADR が確定した範囲**(`ADR-003:251`): 方式 = 制約 DSL からの生成 / 3 層 + 経路一致検査 / 契約の 2 分類・置き場・CI 配線 / 対象と契約の 1 対 1 対応 / 入力範囲の閉じ方 / 比較面 / (b)①③ の検査方式 / 着手順序。
- **送り出した範囲**: 「契約 schema のフィールドレベルの細部」。例示は履歴上限 `D` の値・語彙スナップショットの粒度・正規化規則の識別子体系・証跡ファイルの形式で、**式の文法は例示に入っていない**。v0.2 の追記(`ADR-003:253`)も同じ扱い。
- **D-1 が確定した射程の要素一覧**(`ADR-003:101`): 状態 / イベント / ガード / 次状態 / 整数・boolean・enum / 四則・比較・min・max / 明示的な丸め / 有限の reducer / 入出力の型・範囲・単位・scale / nullable / 表示規則 3 類。続けて「これ以外の計算を正本に書かない」。**論理演算(and/or/not)、条件式、ループ、関数呼び出しは一覧にない。** つまり「条件分岐の入れ子・ループ・関数呼び出しが無い」こと自体は、ADR の閉じた一覧から直接出てくる帰結。
- **具体的な文法を決めたのは TSK-235**(worktree `/home/ymdms/projects/pitchlog-worktrees/feature-domain-calc-dsl`):
  - `backend/domain/model.schema.json:529-555`: `Expression` は 8 種の oneOf(数値/真偽/列挙リテラル・参照・四則・比較・最大最小・丸め)。
  - `:424-442`: `GuardRule.expression` は `ComparisonExpression` 1 個だけ。
  - `:444-479`: 遷移は `guardRefs[]` で複数ガードを参照する。
  - `:480-511`: `ReducerRule` のフィールドは `sourceRef`・`maximumItems`・`initial`・`expression` だけ(`additionalProperties: false`)。
  - `:760-` `x-pitchlog.scopeElements`: D-1 の要素一覧を schema 上の位置へ 1 対 1 に対応づけている。
  - 合格条件は `docs/features/domain-calc-dsl/plan.md:602`(ステップ 13)。「D-1 射程行の全要素が schema に現れる」「『これ以外は書けない』が閉じている(条件分岐を拒否する負例)」と、要素が揃っていることと射程の外を拒否することだけを検査しており、**本物の計算が書けることは検査していない**。
- **判定**: ADR の要素一覧はゲートを通った。それを式の文法にどう落とすかは TSK-235 の実装判断で、**ADR の確定ゲートを通っていない**。

## 3. TSK-235(PR #74)で表現力は検証されたか

- **本物の対象計算は書かれていない。** `plan.md:494`「製品ドメインではない合成 DSL で行う」、`:138` と `:656` で対象ごとの DSL 正本・製品生成物を作らないと明記している。
- **合成 fixture は 1 計算だけ**: `backend/tests/domain/fixtures/synthetic_dsl/model.json`。`syntheticMatrix`、ガード `nonnegativeAmount`(比較 1 個、`:103-118`)、遷移 `applyAdvance`(状態 + イベント値の加算、`:122-145`)、reducer `sumSeries`(累積 + 要素の加算、`:149-170`)。野球のロジックは含まない。
- **「書き切れることを実測した」という記録の射程**(`docs/features/domain-calc-dsl/design.md:1532-1544`、トリガー 1 の裁定): 検証したのは**型語彙の置き場**(履歴スタック・規則配列・語彙 snapshot・スコアボード欄・NumericValue/DisplayAtom)が表現できるかどうか。計算ロジックの表現力ではない。同じ箇所に「合成 DSL での確認であり、製品データではない」という限界も記録されている。
- **表示側は検証済み**: 付録A の書式 binding 全 36 件が D-1 の 3 類で表現できることを確認している(`research.md:1222`)。
- **レビューで出た表現力の指摘は表示の 1 件だけ**: 敵対レビュー 2 周目 P0-2 の「数値表示を D-1 で表現できない」(`docs/worklog/2026-09-01-domain-calc-dsl.md:15-50`)。worklog 3 本・plan・design・research をキーワードで検索した範囲では、状況計算の式の表現力に関する指摘は見つからなかった。レビュー全文(`rev235b-full.txt`、スクラッチパッドにありリポジトリ外)は未確認なので、そこに記載があるかは**不明**。
- **補足**:
  - 「13」が 2 種類ある。U-X1 の主所有 FR が 13 件(`docs/features/product-impl-unit-split/design.md:73`)、ADR の対象計算 (α)5 + (β)8 も 13 件(`research.md:1223`)。数は同じだが別の集合。
  - PR #74 の成果物は develop(`f20323cb`)に無い(`backend/domain/` が develop に存在しない)。

## 4. 書けない計算が見つかったときの経路

- **手順の決定**:
  - `ADR-003:101`「表せないものが出たら D-1 の見直しトリガー」
  - `:461` 見直しトリガー 1「DSL の射程で表せないドメイン計算が現れたとき…次点は D-2 の QuickJS / 常駐 Node」
  - `:251` 末尾: 細部の確定が「特に D-1 の射程」と両立しないと分かった時点で、ADR を改訂ゲートへ戻す
  - → **ADR 改訂(確定ゲート 7.3 + 人間承認)が必要**。
- **エスケープハッチはない**:
  - `:101` これ以外を正本に書かない
  - `:111` D-1-c: 手書きの interpreter は採らない
  - `:132` D-3: 手で直した生成物は CI で fail
  - `:446`: 手書きの Python / TypeScript でドメイン計算を書く経路は閉じる
  - 実装側の裁量で逃げ道を作ることを認めた決定は見当たらない(典拠なし)。
- **前例**: TSK-235 でトリガーが発火し、停止 → TSK-276 起票 → ADR v0.2(TSK-278、確定ゲート 27 周)という流れをたどった(worklog `2026-09-01-domain-calc-dsl.md:52-77`、`ADR-003:11-12`)。v0.2 は、QuickJS(D-2)へ切り替えるより「射程の意味を変えずに端を広げる最小の改訂」を優先している(`ADR-003:122-128`)。
- **TSK-235 の停止規定**: `plan.md:155`「発火したら本タスクを停止し、ADR 改訂・再承認後に計画を作り直す」。トリガー 16 件の表は `design.md:1495-1512`。ただしこれは TSK-235 の計画に固有の規定で、**TSK-405 には自分で停止手順を持つ必要がある**(段階 2 全体に適用される規定は ADR の `:461` / `:251` だけ)。
- **U-X1 向けの申し送り**(`design.md:1863-1881`、PO 裁定 2026-09-18): 結果表示名の合成規則は打撃結果で分岐する必要があり、D-1 の 3 類のどれにも置けない。そのため、U-X1 が結果表示名を実装する時点で前提ゲート 3 とトリガー 2 が同時に発火し、**要件書と ADR の両方の改訂ゲートへ止まる**と明記されている。根拠資料は `research.md:1395-1451`。

## 関連ファイル
- /home/ymdms/projects/pitchlog/docs/adr/ADR-003-domain-calc-method.md
- /home/ymdms/projects/pitchlog/docs/worklog/2026-08-18-adr003-domain-calc-method.md
- /home/ymdms/projects/pitchlog/docs/features/nfr018-domain-calc-adr/research.md
- /home/ymdms/projects/pitchlog/docs/features/adr003-domain-calc-method/research.md
- /home/ymdms/projects/pitchlog/docs/features/adr003-display-primitives/design.md
- /home/ymdms/projects/pitchlog-worktrees/feature-domain-calc-dsl/backend/domain/model.schema.json
- /home/ymdms/projects/pitchlog-worktrees/feature-domain-calc-dsl/backend/tests/domain/fixtures/synthetic_dsl/model.json
- /home/ymdms/projects/pitchlog-worktrees/feature-domain-calc-dsl/docs/features/domain-calc-dsl/plan.md
- /home/ymdms/projects/pitchlog-worktrees/feature-domain-calc-dsl/docs/features/domain-calc-dsl/design.md
- /home/ymdms/projects/pitchlog-worktrees/feature-domain-calc-dsl/docs/features/domain-calc-dsl/research.md
- /home/ymdms/projects/pitchlog-worktrees/feature-domain-calc-dsl/docs/worklog/2026-09-01-domain-calc-dsl.md
