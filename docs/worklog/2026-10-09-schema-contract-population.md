---
date: 2026-10-09
topic: スキーマ契約テスト母集団の規則の是正(PR #100 の律速)
branch: fix/schema-contract-population
---

# 作業ログ: 2026-10-09 スキーマ契約テスト母集団の規則の是正(PR #100 の律速)

## やったこと

**`tests/test_core_guard.py:1871-1873` の表明(`backend/tests/db/test_authz_` 接頭辞を母集団から
禁じる)を、本来守るべき退行の固定へ置き換えた。**

| ステップ | 内容 |
| --- | --- |
| 1 | **前方(import 先)の閉包だけであることを挙動で固定する試験を新設**(`test_schema_contract_population_closes_forward_only`) |
| 2 | **接頭辞禁止の assert を撤去**し、docstring へ「なぜ名前ではなく挙動で固定するか」を書いた |

**順序を入れ替えていない** — 置き換える側を先に入れ、保護に穴が開く瞬間を作らなかった。

**母集団の規則(`SCHEMA_CONTRACT_TOKENS` と判定)は 1 文字も変えていない。**

## 決定

- **母集団の規則を変える案を、射程から全部落とした**(人間の決定 2026-10-09)。
  当初は `pitchlog.db` の判定を `ast` で精密にし、接続の工場だけを参照する試験を外す計画だった
- **重さ分類 = コア領域**(人間の決定 2026-10-09)。`tests/test_core_guard.py` は
  `.claude/core-areas.json` の `guard_paths`(`:51`)にあり**検査経路そのもの**で、
  **PR が検査を書き換えられる循環は機械では防げない**(設計書 `:390`)
- **過剰包含の是正は別カードへ切り出した**(`3f393b75-e687-810b-bf2e-e831cb66e126`・`未着手`・優先度 低)

### レビューが潰した、こちらの誤り

**【P1・方針ごと覆った】偽陽性と判定した 2 件のうち 1 件は、正当なスキーマ契約試験だった。**

`backend/tests/db/test_runtime_contract_product_integration.py` は `pitchlog.db` の参照が
**bare な `from pitchlog.db import engine` だけ**だが、**実 PostgreSQL のカタログに対して
schema・table・function の実在を照合している**(`:89` 付近)。原典で確認した。

**import の形だけでは、工場を使うだけの試験と、実スキーマを検証する試験を見分けられない。**
これが規則変更を射程から落とした理由である。

**【P1】3 節の条件付き更新では `check_plan_docs_sync.py` が止まる** — 台帳と `docs/README.md` を
「追記したときだけ」と書いていたが、検査器は**両行を反映宣言として読む**。
`反映なし` へ確定し、追記する場合の手順を明記した。

**【P1】合格条件を件数で書いていた** — 「母集団が 42 件」では**中身の入れ替わりを見逃す**。
比較元を `7167c182` に固定し、**ソート済みのパス一覧**で比較する形へ改めた。

### 自分の誤り(他タブへ訂正を送ったもの)

- **偽陽性の数え方** — 469 master は `backend/tests/db/` しか走査しておらず
  `backend/tests/test_authz_connection_guard.py` を取り逃がしていた。こちらも最初は
  その数字を引いていた
- **「ファイル名を変えると `core-areas.json` への登録が必須になる」は `backend/tests/db/` 配下では
  成り立たない** — 既存の `backend/tests/db/*` glob が覆うため登録は自動で満たされる。
  **実際に赤を出していたのは登録検査ではなく、接頭辞禁止の表明だけだった**

## 負例の実測(ステップ 1 の合格条件)

**`schema_contract_test_paths()` の閉包を一時的に双方向へ改変して実測した。**
改変は**コミットしていない**(`git checkout -- tests/test_core_guard.py` で復元)。

| | 結果 |
| --- | --- |
| 落ちた表明 | **`test_schema_contract_population_closes_forward_only` の非包含の表明** — `assert "backend/tests/test_importer.py" not in population`(メッセージ「逆向きの閉包は認可検証の資産を巻き込む」) |
| 母集団(合成ツリー) | 期待 2 件 → **3 件**(`test_importer.py` が混入) |
| 同時に落ちた既存試験 | `test_all_schema_contract_assets_match_an_actual_core_area_path` / `test_schema_contract_test_population_does_not_depend_on_branch`(**改変前の、まだ撤去していない接頭辞の assert**) |
| 改変を戻した後 | **215 passed**(`tests/test_core_guard.py`) |

**双方向の閉包は、新しい試験・登録検査の両方から赤になる。**

## 検証

| 検査 | 結果 |
| --- | --- |
| 母集団のパス集合(base `7167c182` との比較) | **42 件・ソート済み一覧の diff 0 行** |
| `tests/test_core_guard.py` | **215 passed** |
| `ruff check` / `ty check`(ハーネス) | All checks passed |
| backend の差分 | **0 ファイル**(`git diff --name-only origin/develop...HEAD` に `backend/` が 1 件も無い) |
| backend `--collect-only` | **1340 件**(head)。**backend に差分が無いので base と一致する** |

## 未決・次の一歩

- **母集団の過剰包含**(接続の工場だけを参照する試験が入る)は**直していない**。
  `backend/tests/db/*` と `backend/tests/test_authz*.py` の glob が覆う間は実害が出ない。
  **別カードへ切り出し済み**
- **マージ後に PR #100 の `harness` が緑になることを確かめる**(#100 の担当タブへ連絡する)
- **却下された「文字列参照のみ」案のトークン**(`schema-manifest.json` / `backend/migrations`)と
  採用トークン(`schema-manifest` / `migrations`)の字面が違い、**広げた理由はどこにも記録がない**
