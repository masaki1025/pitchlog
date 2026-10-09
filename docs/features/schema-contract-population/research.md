---
feature: schema-contract-population
type: research
date: 2026-10-09
---

# 調査メモ: スキーマ契約テスト母集団の規則の是正

## 問い

1. 母集団の規則(`SCHEMA_CONTRACT_TOKENS` による文字列一致)は**なぜ今の形なのか**。`ast` による import 解析は検討されたか
2. この機構は**何を守っているのか**。要件書のどの FR/NFR に紐づくか
3. 規則を狭めると**何が弱まるか**。弱まらないことをどう測るか
4. 規則の変更に**どのゲート**が掛かるか(確定ゲート・敵対レビュー・逐行確認・凍結基準)
5. **偽陽性は何件あるか**

## 結論(要約)

- **偽陽性は develop 上で 2 件**(`test_runtime_contract_product_integration.py` / `test_authz_connection_guard.py`)。PR #100 の新設分を入れて **3 件**。**他タブの申し送りは 1 件(+#100 で 2 件)としており、`backend/tests/` 直下の 1 件を取り逃がしている**
- **`ast` の import 解析だけに替える案は 2026-09-12 に検討され、退けられている**(14 件・6 件取りこぼし)。**トークンは残したまま `pitchlog.db` の判定だけを精密化する**のが筋
- **規則を狭めても要件の充足は弱まらない**。3 件とも `areas[].paths` の別パターンで独立に一致しており、**逐行確認の経路から外れない**(実測)
- **確定ゲート(7.3/7.6)は掛からない**(正本の文書を変えないため)。**凍結基準(7.7)にも当たらない**。**逐行確認は必須**(`guard_paths`)
- **`backend/tests/` の編集禁止には抵触しない**。TSK-344 の計画が「例外は `tests/test_core_guard.py` の改修 1 件で、これは `backend/tests/` ではない」と明示している

## 詳細と典拠

### 1. 現行の規則と、その成立の経緯

**規則の実体**: `tests/test_core_guard.py:1038` の `SCHEMA_CONTRACT_TOKENS = ("pitchlog.db", "schema-manifest", "migrations")` を**本文に文字列として含む**ファイル(`:1082-1085`)+ **それらが import する補助モジュールの推移閉包**(`:1088-1097`。閉包側は `_local_module_dependencies` が `ast.parse` を使う — `:1053`)。

**2 段構えになっている理由**: 起点は文字列一致、広がりは `ast`。**import だけでは「migration のパスを読むだけのテスト」が拾えない**ため(下の比較表)。

**成立**: PR #56(2026-09-12・fast path)。直前の PR #55 が母集団を `changed_paths(REPO, "origin/develop", "HEAD")` で切ったところ、**マージ後の develop で `backend/tests/` の母集団が 20 件 → 0 件になり検査が空洞化**した(`docs/worklog/2026-09-12-core-area-population-base.md:29-44`)。その是正である。`tests/test_core_guard.py:1065-1067` の docstring がこの経緯を書いている。

**検討して退けた 5 案**(`docs/worklog/2026-09-12-core-area-population-base.md:67-75`):

| 案 | 当時の件数 | 却下理由 |
| --- | --- | --- |
| **`pitchlog.db` の import のみ** | 14 | `test_migration_hygiene.py` など **6 件を取りこぼす** |
| 文字列参照のみ | 17 | 3 件取りこぼす |
| 参照 + importer の推移閉包 | 19 | 補助モジュール `type_boundary_contract.py` を取りこぼす |
| 参照 + **双方向**の推移閉包 | 41 | **`conftest.py` 経由で authz 一式まで巻き込む** |
| **参照 + import 先の推移閉包(採用)** | 22 | 20 件をすべて含む |

**`test_authz_` 接頭辞を禁じる表明(`:1871-1873`)の出所は、この表の「双方向の推移閉包 = 41 件」である。** 過剰包含への退行を防ぐ固定であって、**「認可テストは母集団に入ってはならない」という原理ではない**(後述)。

### 2. 機構が守っているもの

**要件書には根拠条項が無い。** 「スキーマ契約」「core-areas」「コア領域」で全文探索した結果、要件書で当たるのは `requirements-pitchlog-2026-07-22.md:892` の 1 件だけで、内容は「NFR-018 の区分はコア領域の境界には用いない」という**切り離しの規定**。改善台帳は 0 件。

**実際の典拠はハーネス設計書 6.3 の paths 規則①** — 「コアの不変条件・強制点・契約(ベクタ・スキーマ・テスト)を変え得るファイルを含める」(`docs/development/dev-harness-design-2026-08-07.md:404`)。

**守ろうとしている失敗の形**: スキーマ契約の資産が増えたとき、`areas[].paths` に登録されないまま **core-guard が発火しない**こと(台帳 `H-12`「コア領域ガードは実質空」— `docs/development/harness-evaluation.md:548-554`)。

**NFR との接点は間接的なものだけ** — NFR-021 の「Phase 4 完了時: ハーネスの pytest が成功」(`requirements-pitchlog-2026-07-22.md:961`)。求めているのは成功だけで、検査の中身は定めていない。

### 3. 偽陽性の実測(2026-10-09・本タブ・develop `7167c182`)

**母集団は 42 件**(直接ヒット 36 + 推移閉包 6)。

`pitchlog.db` **だけ**で入っているのは 6 件。うち**実スキーマに触れていないのは 2 件**:

| ファイル | 参照 | 判定 |
| --- | --- | --- |
| `backend/tests/db/test_runtime_contract_product_integration.py` | bare な `pitchlog.db`(`from pitchlog.db import engine`) | **偽陽性** |
| **`backend/tests/test_authz_connection_guard.py`** | **`pitchlog.db.engine` のみ** | **偽陽性** |
| `test_authz_capability_registration.py` | `pitchlog.db.base` | 正しく母集団 |
| `test_authz_tenant_binding.py` | `pitchlog.db.config` ほか | 正しく母集団 |
| `test_database_url.py` | `pitchlog.db.url` ほか | 正しく母集団 |
| `test_model_mixins.py` | `pitchlog.db.mixins` ほか | 正しく母集団 |

**他の 2 トークンに偽陽性は無い** — `schema-manifest` だけで入る 5 件はすべて `contracts/db/schema-manifest.json` を実際に読み、`migrations` だけで入る 5 件はすべて `backend/migrations` か `contracts/migrations` を実際に参照している(実測)。**是正の対象は `pitchlog.db` トークンだけ**である。

**表明の守備範囲は狭い**: `:1871-1873` が禁じているのは **`backend/tests/db/test_authz_` 接頭辞だけ**で、**`backend/tests/test_authz_*` は既に 10 件以上が母集団に入っている**。PR #100 の新設ファイルが特異なのではなく、**接頭辞が当たる位置に置かれた最初の例**である。

### 4. 規則を狭めても保護範囲は狭まらない(実測)

**3 件とも `areas[].paths` のパターンで独立に一致する**(`core_guard.matched_paths` を `guard_paths` を空にして実行):

- `backend/tests/db/*` → 5 領域すべて(`.claude/core-areas.json:139,200,282,333,402`)
- `backend/tests/test_authz*.py` → tenant-isolation(`:327`)

**母集団から外れても、core-guard の発火と逐行確認の要求は残る。**

**候補規則で差分を実測した**(`pitchlog.db.engine` だけを参照する試験を起点から外す):

```
旧 42 件 → 新 40 件
外れる: backend/tests/db/test_runtime_contract_product_integration.py
        backend/tests/test_authz_connection_guard.py
増える: なし
```

**推移閉包の連鎖で巻き添えに外れるものは無い**(両者の依存先は他のファイルからも参照されているため)。

### 5. 掛かるゲート

| ゲート | 判定 | 典拠 |
| --- | --- | --- |
| **逐行確認** | **必須** | `tests/test_core_guard.py` は `guard_paths` にある(`.claude/core-areas.json:51`)。手続 3・4 は `docs/development/github-setup.md:60-61`・設計書 `:390-391` |
| 確定ゲート(7.3 / 7.6) | **掛からない** | 対象は正本の文書(設計書 `:526-532`)。本作業は正本を変えない |
| 凍結基準(7.7) | **当たらない** | 7.7 の対象はコミット・版・digest の基準(設計書 `:537-598`)。母集団の走査規則を凍結基準として扱った文書は 0 件。`tests/test_core_guard.py` は `census-baseline.json` の `external_files` に無い |
| 6.3-⑤(paths の追加・削除・縮小) | **字義上は掛からない** | `.claude/core-areas.json` を変えないため。ただし「母集団を狭めること」が⑤の「縮小」に当たるかは条文に無く**不明** — 人間の判断事項 |
| 敵対レビュー | **要判断** | 6.3 の表で必須なのは「コア領域」のコード(設計書 `:383`)。`guard_paths` だけに当たる本ファイルが対象かは明文が無い。**先例では「検査経路だが fast で可」と人間が判断している**(`docs/features/core-area-population-base/plan.md:25`) |

**`backend/tests/` の編集禁止(裁定 2026-09-28)との境界**: 抵触しない。TSK-344 の計画が「**例外は `tests/test_core_guard.py` の改修 1 件だけで、これはハーネス側の既存試験であり `backend/tests/` ではない**」と明示している(`docs/features/product-rls-boundary-tests/plan.md:524`)。規則の実体は `tests/test_core_guard.py` にあるので、**`backend/tests/` を 1 行も触らずに是正できる**。

### 6. 前提の訂正 2 件(他タブの申し送りとの差)

1. **NFR-014 の条文に「ログ出力しない」は無い** — 条文は「DB接続情報・JWT署名鍵・管理者パスワード・チーム初期パスワードはリポジトリに含めず環境変数で管理する」だけ(`requirements-pitchlog-2026-07-22.md:869`)。「ログに出さない」の典拠は**設計正本** `docs/design/data-model.md:1549,1676-1677`(NFR-011・NFR-014 を根拠に具体化したもの)と、AGENTS.md のレビュー規則である
2. **`hide_parameters=True` を検査しているのは非 DB 版** `backend/tests/test_authz_log_safety.py`。**`backend/tests/db/` 版は属性を見ておらず**、実 DB で SQLAlchemy INFO と psycopg DEBUG のログに認証素材 4 種が出ないことを検査している。**どちらも壊してはいけない点は変わらない**が、「工場を呼ばないと検証にならない」という説明は db 版には当たらない

## 未解決・申し送り

- **採る実装方式は未確定**。`ast` で `pitchlog.db.*` の import を取り、`pitchlog.db.engine` だけを除外する案で差分を実測したが、**文字列だけの言及(import しない形)の扱い**を計画で決める必要がある
- **敵対レビューの要否**(`guard_paths` だけに当たるファイル)は明文が無い。**先例は fast で可**だが、本件は PR #100 の律速を解く変更なので、**通常計画 + 敵対レビューで通すほうが安全**という判断もありうる
- **`schema-manifest` / `migrations` のトークンは触らない**。偽陽性が 0 件であることを実測済み
- **却下された「文字列参照のみ」案のトークン**(`schema-manifest.json` / `backend/migrations`)と採用トークン(`schema-manifest` / `migrations`)の字面が違う。**広げた理由はどこにも書かれていない**(decision-tracer が全文探索して 0 件)
