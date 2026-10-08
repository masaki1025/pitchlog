---
feature: schema-contract-population
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-10-09・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3f393b75e68781a8a2aef916963fa537
branch: fix/schema-contract-population
created: 2026-10-09
計画レビュー周回: 2        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---
# 実装計画書: `test_authz_` 接頭辞の表明を、本来守るべき退行の固定へ置き換える

## 1. 背景・目的

**Notion**: [スキーマ契約テスト母集団の規則を是正する](https://app.notion.com/p/3f393b75e68781a8a2aef916963fa537)
**調査メモ**: [research.md](research.md) — **典拠集**(正本ではない)。本書が事実を述べるときは正本か実測を直接引く。

**`tests/test_core_guard.py:1871-1873` の表明が、本来守るべきものより広く禁じている。**

```python
assert not any(
    name.startswith("backend/tests/db/test_authz_") for name in population
), "認可検証の資産まで巻き込んでいる"
```

**この表明が守っているのは、2026-09-12 に退けた「双方向の推移閉包」案の退行**である。当時その案は `conftest.py` を経由して認可検証の資産まで引き込み、母集団が 22 件 → 41 件に膨らんだ(`../../worklog/2026-09-12-core-area-population-base.md:67-75`)。**ところが表明は「逆向きの閉包をしない」ではなく「`backend/tests/db/test_authz_` で始まる名前を含まない」という形で書かれている。**

**その結果、逆向きの閉包とは無関係に、正当な経路で母集団へ入った試験までが禁じられる。** PR #100 が新設する `backend/tests/db/test_authz_log_safety.py` が `from pitchlog.db.engine import create_database_engine` の 1 行で母集団へ入り、この表明だけで CI が赤になっている。

**いま全体の律速がここ 1 点にある。** #100 が緑にならないと #95 のステップ 9 が始まらず、#95 が止まると #81 も U-S1 も動かない。**#100 の計画書 3 節が `tests/test_core_guard.py` を射程外と宣言済みで、#100 の中では直せない。**

**表明は守備範囲が狭くもある** — 禁じているのは `backend/tests/db/test_authz_` 接頭辞だけで、**`backend/tests/test_authz_*` は既に 10 件以上が母集団にいる**(実測)。双方向閉包の退行は、この表明では半分しか捕まえられない。

**要件との関係**: 要件書にこの機構の根拠条項は無い(全文探索で 0 件)。典拠は**ハーネス設計書 6.3 の paths 規則①**(`../../development/dev-harness-design-2026-08-07.md:404`)と台帳 `H-12`(`../../development/harness-evaluation.md:548-554`)。間接的な接点は **NFR-021** の「Phase 4 完了時: ハーネスの pytest が成功」(`../../requirements/requirements-pitchlog-2026-07-22.md:961`)のみ。

## 2. スコープ

### やること

1. **前方(import 先)の閉包だけであることを固定する挙動試験を新設する** — 双方向閉包の退行を、名前ではなく**挙動**で捕まえる
2. **その後に `:1871-1873` の接頭辞禁止を撤去し、docstring を現況へ改める**

**順序は入れ替えない** — 置き換える側を先に入れ、保護に穴が開く瞬間を作らない。

### やらないこと

| 項目 | 理由 |
| --- | --- |
| **母集団の規則(`SCHEMA_CONTRACT_TOKENS` と判定)の変更** | **1 文字も変えない**。`pitchlog.db` の判定を `ast` で精密にする案は**退けた** — 工場だけを参照する試験のうち `backend/tests/db/test_runtime_contract_product_integration.py` は**実 PostgreSQL のカタログに対して schema・table・function の実在を照合しており**(`:89` 付近)、**import の形では正当なものと見分けられない**(敵対レビュー 1 周目 P1-1・原典で確認)。**母集団は 1 件も減らさない** |
| `backend/tests/` の編集 | **1 行も触らない**。TSK-344 の計画が「例外は `tests/test_core_guard.py` の改修 1 件で、これは `backend/tests/` ではない」と明示(`../product-rls-boundary-tests/plan.md:524`) |
| `.claude/core-areas.json` の変更 | **変えない**。変えると 6.3-⑤ の敵対レビュー + 人間承認が別途掛かる(設計書 `:404`) |
| 母集団の過剰包含の是正 | **別カードへ送る**。工場だけを参照する試験が母集団に入ることの費用(将来 `backend/tests/db/*` の glob が覆わない位置に同種の試験が置かれたとき、`core-areas.json` への登録が要る)は残る。**見分け方の設計が要るので本 PR の射程外** |
| PR #100 側の修正 | **触らない**。#100 は取り込み側 |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし** | — |
| `docs/design/*` | **反映なし** | — |
| `docs/adr/*` | **反映なし** | — |
| `docs/development/dev-harness-design-2026-08-07.md` | **反映なし**(6.3 の規則①は変えない。母集団の走査規則は設計書に書かれていない) | — |
| `docs/development/harness-evaluation.md` | **反映なし** — 台帳への追記は **`/pr` のクローズ処理で判断**する。**追記すると判断した場合は、突合の前に本節を「追記する」へ書き換える**(`check_plan_docs_sync.py` は本節を反映宣言として読む) | PR レビュー |
| `docs/README.md` | **反映なし** — 上記で台帳へ追記したときだけ索引を現行化し、本節も同時に書き換える | PR レビュー |
| `.claude/core-areas.json` | **反映なし**(変更しない) | — |

**正本体系外だが同一 PR で更新するもの**: `tests/test_core_guard.py` / `docs/features/schema-contract-population/{plan,research}.md` / `docs/worklog/2026-10-09-schema-contract-population.md`

## 4. 実装方針

**重さ分類 = コア領域**(人間の決定 2026-10-09)。根拠: `tests/test_core_guard.py` は `.claude/core-areas.json` の **`guard_paths`(`:51`)**にあり、**検査経路そのもの**である。`areas[].paths` には入っていないため機械判定ではコア領域に当たらないが、**PR が検査を書き換えられる循環は機械では防げない**(設計書 `:390`)。**敵対レビュー + 人間の逐行確認**で通す。

**実装は Codex へ委任する**(`/implement` — 1 ステップ = 1 委任 = 1 コミット)。

### 置き換え後に守るもの

**退行の本体は「閉包の向き」である。** 現行の `schema_contract_test_paths()`(`:1088-1097`)は、母集団メンバが **import する先**だけを足す。双方向にすると、**メンバを import している側**まで足さり、`conftest.py` 経由で認可検証の資産が雪崩れ込む。

**新しい試験はこれを合成ツリーで固定する** — `tests/test_core_guard.py` の `REPO` を `monkeypatch` で `tmp_path` へ差し替え、次の 3 ファイルを置く:

| 合成ファイル | 中身 | 期待 |
| --- | --- | --- |
| `backend/tests/test_seed.py` | `migrations` トークンを含み `helper` を import | **母集団に入る**(直接ヒット) |
| `backend/tests/helper.py` | トークンなし | **母集団に入る**(前方の閉包) |
| `backend/tests/test_importer.py` | トークンなし。`helper` を import するだけ | **母集団に入らない**(逆向きの閉包はしない) |

**実リポジトリにも同じ形が現に存在する**(裏付け): `backend/tests/db/conftest.py` は母集団にいる一方、それを import する `backend/tests/db/test_authz_catalog.py` ほか **30 件以上は母集団にいない**(実測)。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **前方の閉包だけであることを固定する挙動試験を新設する** — 上表の合成ツリーを `tmp_path` に作り、`REPO` を差し替えて `schema_contract_test_paths()` を呼ぶ | 新試験が green。**逆向きの閉包を足す改変を入れると red になる**ことを実測で確かめる(確かめた結果を worklog に書く。改変自体はコミットしない)。既存の `tests/test_core_guard.py` が全件 green |
| 2 | **`:1871-1873` の接頭辞禁止を撤去し、docstring を現況へ改める** — 残す 2 つの assert(母集団が空でない / 既知のファイルを含む)はそのまま。**なぜ接頭辞禁止を外したかを docstring に残す** | `test_schema_contract_test_population_does_not_depend_on_branch` が green。`test_unregistered_schema_contract_test_is_rejected`(`:1876-1893`)が green。**母集団の「パス集合そのもの」が base と exact 一致** — 比較元は**コミットを固定**して `7167c182`(本ブランチの起点)とし、**件数ではなくソート済みのパス一覧を保存して差分を取る**(本日の実測値は 42 件。件数だけの一致では中身の入れ替わりを見逃す) |

## 5. DoD(受け入れ基準)

- [ ] **前方の閉包だけであることを、名前ではなく挙動で固定した**(合成ツリーの試験)
- [ ] **逆向きの閉包を足すと新試験が red になる**ことを実測し、**どの表明で落ちたかと、改変を戻した後の green** を worklog に記録した
- [ ] `:1871-1873` の接頭辞禁止を撤去し、**撤去の理由を docstring に残した**
- [ ] `test_schema_contract_test_population_does_not_depend_on_branch` が green
- [ ] `test_unregistered_schema_contract_test_is_rejected`(`:1876-1893`)が green
- [ ] **母集団のパス集合が base `7167c182` と exact 一致**(件数ではなくパス一覧で比較。本日の実測は 42 件)— **保護範囲を 1 件も狭めていない**
- [ ] `SCHEMA_CONTRACT_TOKENS` と母集団の判定を**変えていない**
- [ ] **`backend/tests/` の差分が 0 行**
- [ ] **`.claude/core-areas.json` の差分が 0 行**
- [ ] ハーネス `uv run pytest tests/` が green・`ruff check` / `ty check` が green
- [ ] **backend の `--collect-only` が本 PR の前後で exact 一致**(CI の実行内容を変えていない)
- [ ] 敵対レビューを通した / **逐行確認のチェックと実施記録**を PR 本文に記入した
- [ ] **母集団の過剰包含(工場だけを参照する試験が入る件)を別カードへ起票した**
- [ ] **マージ後に PR #100 の `harness` が緑になることを確かめた**

## 6. テスト計画

**NFR-019 の種別で言うと、足すのは単体と故障系(負例)である。** 越境・一致性・E2E には足さない(本件は検査器の表明であり、製品の経路を触らない)。

| 対象 | 種別 | 置き場 | 確認すること |
| --- | --- | --- | --- |
| 閉包の向き | **単体** | `tests/test_core_guard.py` | 直接ヒットと前方の閉包は入る / 逆向きは入らない(合成ツリー) |
| 退行 | **故障系(負例)** | 同上(実測のみ・コミットしない) | 逆向きの閉包を足すと新試験が red |
| 既存の表明 | **単体** | 同上 | `:1876-1893` が引き続き red を出す |

**`backend/tests/` には 1 ファイルも置かない。**

### 検証方法

```
# ハーネス(worktree で)
uv run ruff check . && uv run ty check
PYTEST_XDIST_AUTO_NUM_WORKERS=8 uv run pytest tests/

# 母集団のパス集合の比較(件数ではなく一覧。base は 7167c182 に固定する)
#   base 側: git worktree などで 7167c182 を取り出し、下の 1 行で一覧を保存する
#   head 側: 同じ 1 行で保存し、diff が 0 行であることを確かめる
uv run python -c "import importlib.util;s=importlib.util.spec_from_file_location('t','tests/test_core_guard.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print('\\n'.join(sorted(m.schema_contract_test_paths())))" > population.txt

# CI の実行内容を変えていないことの確認(backend で)
uv run pytest -c pyproject.toml --collect-only -q   # :: を含む行の集合を前後で比較
```

**マージ後**: PR #100 に develop を取り込ませ、`harness` が緑になることを確かめる(#100 の担当タブへ連絡する)。

## 7. 申し送り

- **母集団の過剰包含は残る** — `pitchlog.db` の素朴な文字列一致により、接続の工場だけを参照する試験も母集団に入る。**`backend/tests/db/*` と `backend/tests/test_authz*.py` の glob が覆う間は実害が出ない**が、覆わない位置に同種の試験が置かれると `core-areas.json` への登録が要る。**見分け方の設計が要るので別カードへ**
- **却下された「文字列参照のみ」案のトークン**(`schema-manifest.json` / `backend/migrations`)と採用トークン(`schema-manifest` / `migrations`)の字面が違い、**広げた理由はどこにも記録されていない**(全文探索で 0 件)
