---
date: 2026-09-24
topic: 迂回検査 条件 5・条件 2 の射程判定(TSK-440)
branch: fix/tenant-boundary-scope
---

# 作業ログ: 2026-09-24 迂回検査 条件 5・条件 2 の射程判定(TSK-440)

## やったこと

- `/task-start` — TSK-440(既存カード・ステータス `着手可`)から着手。
  `fix/tenant-boundary-scope` + worktree を `origin/develop`(`bf8ba5b`)起点で作成
- `/investigate` — 調査サブエージェント 3 本(spec-checker / decision-tracer / 実装構造)+ 自分の実測
  → [research.md](../features/tenant-boundary-scope/research.md)

## 決定(調査の結論として計画へ渡すもの)

- **条件 5 と条件 2 は別の問題として扱う。** 条件 2 はこの検査器の脅威モデルのどの項目にも対応せず、
  由来は上流分割計画の「面を混ぜない」規律(`product-impl-unit-split/plan.md:270` `:258`)
- **除外の単位をモジュールにしない。** 到達可能性は母集団の導出根拠には使えるが、
  モジュール除外の形にすると U-T1 が P0 で否決した「パスで丸ごと除外」と同じになる
  (`tenant-boundary-enforcement/design.md:463` `:470-471`)
- **他タブと合意した資産の境界**: 導出規則を資産に置くのは可 / **導出結果を資産に置くのは不可**。
  除外集合は検査の実行時に毎回導出する

## 未決・次の一歩

- `/plan` で計画書。**射程を絞るときは、絞った結果として落ちてはいけないものを同時に名指しする**
  (`worklog/2026-09-17-tenant-boundary-enforcement.md:240-247`)
- **既存の未承認履歴 7 件**(`contracts/tenant_boundary/*.json` 各 `:61-64`)の扱いは人間の判断が要る

## 実装(2026-09-24〜25)

`/implement` で 10 ステップ(当初 12・うち 2 つは撤回)。**1 委任 = 1 ステップ = 1 コミット**。

| # | 内容 | 性格 |
| --- | --- | --- |
| 1 | センサスの土台(merge-base 比較・永続 golden 無し)+ CI 実経路の回帰 | 土台 |
| 2 | 検査 visitor の訪問漏れ 7 位置(現行バグ) | 厳しくする |
| 3 | flow の網羅性 + **Call 被覆の不変条件** | 厳しくする |
| 4 | 相対 import の絶対化 | 厳しくする |
| 5 | (iv) 末尾名一致 + (v) 再輸出写像 | 厳しくする |
| 6 | **既定値の反転** | **緩和** |
| 7 | 条件 2 の裁定 exact-set(候補は狭めない) | 部分緩和 |
| — | ~~コア paths 拡大~~ | **撤回** |
| 8 | 保証単位を `design.md` 6-0 / 1-1 へ逐語で置く | 文書 |
| 9 | 申し送り・起票・Notion | 文書 |
| 10 | 凍結基準の受理 | 手続 |

### 効果(現行 contract + 現行 checker を TSK-235 の `backend/src` へ当てた全文走査)

| | 適用前 | 適用後 |
| --- | --- | --- |
| **TB007** | **794** | **4** |
| **TB002** | **146** | **35** |
| TB005 | 137 | **137** |
| TB004 | 15 | **15** |

**TB001〜TB006 は不変。減ったのは TB007 と、裁定した TB002 だけ。**

### 見つけた現行検査器のバグ 3 種(緩和と無関係に利得)

1. **`_visit_function` がデフォルト引数・注釈・戻り注釈を訪問しない** →
   `def run(c=TenantContext(X))` が **0 件**
2. **PEP 695 の `type_params` を scanner も flow も訪問しない** →
   `def run[T: TenantContext(X)]()` が **0 件**(backend は Python 3.12 固定)
3. **flow 登録の漏れ 12 件** — lambda default / annotated assignment / class base /
   `except` handler type / 終端文の後。**`authz/catalog.py` が 10 件**

### 差し戻し 4 回

| 対象 | 何を直したか |
| --- | --- |
| ステップ 1 | センサスの基準が `origin/develop` の**先端**だった → **merge-base** へ。TSK-431 が同じ検査器を変えるため |
| ステップ 5 | 再輸出写像が**未供給だと (v) が黙って飛ぶ**。本番経路が必ず供給することをテストで固定 |
| ステップ 6 | **`dataclasses.replace` の `unknown` を免除に加えていた**。負例へ注釈を足して**緑になった経路を覆い隠して**いた |
| ステップ 6 | 残る 18 件のうち 6 件が `str` / `enumerate` / `dict`。**名前は読み取れている**のに拒否しており、**宣言より厳しく既存の (i) と不整合**だった |

**3 つ目は「テストを実装に合わせて緩める」型**で、本 PR で 7 周かけて潰してきたものである。

### コア paths 拡大の撤回(2026-09-25)

**設計書 6.3-⑤ の敵対レビューで承認不可(P0×1 / P1×4)。**

- **P0**: `api/**` と `services/**` は**構築可能性ではなく「置かれそうな場所」**を選んだヒューリスティック。
  保証外にした `registry[k].make_context(t)` は**配置場所に制約がない**ので釣り合わない
- **実測で否定された私の主張 3 点**:
  ① 「どちらのマージ順でも通る」→ **PR #74 の `AREA_PATH_ADDITIONS` に `tenant-isolation` が無い**ので
     #74 が先なら拒否される ② 「過剰包含ではない」→ `api/` にヘルスチェックと DTO 基盤、
     **`services/` は 0 ファイル** ③ **`services/context_issuer.py` という例は引用先に存在しない**
     (**自分で作った例を典拠つきのように書いていた**)

**したがって本 PR は「代償なしの保証縮小」**であり、**人間が残余リスクを明示的に受容する案件**である。

### TSK-235 への申し送り(実測で特定した 12 件)

**2 ファイルに集中している。**

    TB002  domainmut/engine.py:262,263,265,265,273,273,291,296,298   9 件
             局所変数 generation / missing_generation。MutationGeneration を受ける変数名
    TB007  domaingen/pregen_checks.py:582                            1 件
             _CHECKS[check_id](...) の添字呼び出し
    TB007  domainmut/operators_display.py:469,479                    2 件
             dataclasses.replace(source.invocation, ...)

**いずれも規則どおりの検出で、真の脆弱性ではない。**
TB002 9 件は**変数名の変更**で消える。TB007 3 件は**直接呼び出しへの書き換え**で消える。

### 別タスクを起票した(2026-09-25)

**[TenantContext の発行を専用モジュールへ機械的に封じ込める](https://app.notion.com/p/3e693b75e6878136891fca40b09db799)**
(優先度 高・コア領域)

**DoD は「ファイルを移す」ではなく「そこ以外では有効なインスタンスを発行できない」まで含めた。**
`TenantContext.__init__` が公開のままでは、合法な発行コードを移しただけでは閉じないためである。

- **発行専用モジュール以外から有効な `TenantContext` を作れない実行時 capability**
- **発行モジュール外からの constructor / import / registry 登録を拒否する検査**
- **その強制点・検査器・テストだけをコア paths に登録**(ディレクトリ全体を足さない)

**着手は TSK-440 のマージ後**(保証縮小が入ってから代償を作る)。
**U-A1 / TSK-217 と射程が重なりうる** — `tenant-context-allowlist.json` の
`allowed_product_modules` は**現在 0 件が機械的に強制**されており、
**製品の入口が開く時点で本タスクの機構が要る**。

### 凍結基準の受理で踏んだ罠 2 件(2026-09-25)

**どちらも機構が自分で検出したが、どちらも「先に算出した値をそのまま書く」と静かに間違う形だった。**

1. **未承認 marker が PR 番号を焼き込んだ単一定数である。**
   `scripts/check_tenant_boundary_bypass.py:64` の `PENDING_APPROVAL` は
   `"未承認(PR #72 のレビュー待ち)"` という完全一致の定数で、
   `:552` が「これ以外の `approved_on` は `YYYY-MM-DD`」を要求する。
   **後から受理する側は、自分の出所を名乗れず PR #72 の名前を借りるしかない。**
   定数を一般化する案は取れない — 既存 6 資産の merge-base 履歴が同じ文字列を使っており、
   `_validate_history_append_only` が merge-base 履歴の変更を拒否するため。
   **本 PR は marker をそのまま使い、出所が TSK-440 であることと
   marker が機構上の定数であることを各履歴の `reason` へ明記した。**

2. **凍結射影は `excluded`(`baseline_control` と `source_digest`)以外の全トップレベル欄を含むので、
   `contract_revision` / `fixture_set_revision` 自身が射影に入る。**
   よって受理履歴の `change.after` は **revision を上げた後の状態**で算出しなければならない。
   revision を上げる前の値を書くと `_validate_baseline_transition` が
   「履歴の変更後射影が実スナップショットと不一致」で落ちる。
   **`change.before` は merge-base 側の射影**であって、作業ツリーの revision 更新前の値ではない。
   `baseline_control` 自体は excluded なので、履歴を追記しても射影は動かず、1 回で収束する。

| 欄 | 何を入れるか | 間違えやすい値 |
| --- | --- | --- |
| `change.before` | **merge-base** の資産 + 外部凍結対象の射影 | 作業ツリーの revision 更新前の射影 |
| `change.after` | **revision を上げた後**の作業ツリーの射影 | revision を上げる前の射影 |

### 現在地導出が読めなくなっている(未是正 — 人間の判断待ち)

**ステップ 8 / 9(コア paths 拡大)の撤回で総数を 12 から 10 へ詰めた結果、
先行するコミット 1〜7 の件名が名乗る `/12` が計画書の総数 10 と一致しなくなった。**
`scripts/feature_status.py` の `extract_step_tokens` は
`/<N>` が総数と一致しない件名を不正形として扱うため、**ステップ 1〜7 が進捗に算入されない**。
撤回の `Revert "... (ステップ 8/12)"` 2 件も同じ理由で不正形になる。

- **実体は 10 ステップすべて完了**である
- `/pr` の現在地導出突合は**非ブロッキング**(警告が出ても中断しない)で、CI も参照していない
- 是正するなら**件名の書き換え = 履歴改変 = force-push** が要る(**人間の操作**)

**併せて、計画書のステップ 2 の行が末尾のセル区切り `|` を欠いており、
ステップ表の解析からその行だけ落ちていた**(`STEP_ROW_RE` は閉じの `|` を要求する)。
**これは本コミットで是正した。** 表の総数が 10 と正しく読めるようになった結果、
上の `/12` 不一致が表面化した。
