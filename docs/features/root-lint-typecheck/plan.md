---
feature: root-lint-typecheck
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-08-23・山田正輝)   # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: 通常            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3c593b75e68781c8921cf42b940afbcf
branch: feature/root-lint-typecheck
created: 2026-08-23
計画レビュー周回: 1        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: ルートへの ruff・ty 導入(F4)

## 1. 背景・目的

Notion タスク: [ルートへの ruff・ty 導入(F4 — scripts/ と tests/ の未検査を解消)](https://app.notion.com/p/3c593b75e68781c8921cf42b940afbcf)

ルートの `pyproject.toml` は `dev = ["pytest>=8"]` だけで、**ruff・ty が入っていない**。そのため **`scripts/`(約 5,000 行)と `tests/`(約 3,100 行)が一度もリント・型検査されていない**。`backend/` には両方入っており(`backend/pyproject.toml:16-17`)、**層による非対称**になっている。

**この非対称は実害を生んでいた。** ty を試験的に走らせたところ、**マージ済みのコードに型の欠陥が 8 件**見つかった。うち 1 件は Phase 4-5(PR #24)で PR 作成者がレビューして通した**テストの実バグ**である:

```
tests/test_nfr021_append_only.py:1185・1198
  attempt_id(3, timestamp=...)  →  '3-001-20260820T101501Z'
  意図した値                    →  'phase4-003-20260820T101501Z'
```

`attempt_id` の第 1 引数は `gate_key` なので(`attempt_id(gate_key: str = "phase4", attempt_seq: int = 1, ...)`)、`3` が `gate_key` に入り **`record_id` にだけ不正な値**が渡っている。

**レコードの `gate_key` 自体は `phase4` のまま**である(`write_reservation` は自前の `gate_key="phase4"` 既定でレコード本文を作る — `test_nfr021_append_only.py:411`)。したがって当初「ゲートキーが `"3"` になるため別ゲートになる」と説明したのは**誤り**で、実際に起きているのは **`attempt_id` がゲートキーと `attempt_seq` に対応しない不正形**になることである。スキーマ検査は `attempt_id` の字句とゲートキー・連番の対応を要求するため、**このレコードは解析不能として `tree_records` の列挙から落ちる**と考えられる。

当該テストは「**既存の欠番・重複が新規予約を妨げない**」ことを検査する正例だが、**「既存の重複」として置いたレコードが解析不能で列挙されない**なら、検査したい状態が作られていない。**空転している疑いは残る**が、**断定はステップ 6 の実測で確かめる**。**PR #24 で実施した 25 件の変異テストでは検出できなかった**(このテストの空転は他のテストの成否に現れないため)。

**期限がある。** `/pyproject.toml`・`/uv.lock`・`/tests/**`・`/scripts/**`・`/.claude/**`・`/.github/workflows/**` はすべて **NFR-021 の失効対象パス**(`.claude/nfr021-invalidating-paths.json`)。

**正確な順序条件**: 検証器は **`tested_commit_sha`(T)から候補 SHA(C)までの変更パス集合**を見る(`verify_nfr021_evidence.py:2247`)ので、**「証跡ファイルを作る前」では足りない**。**T を採った後に本 PR を統合すると、失効対象の変更が T..C に入って証跡が失効する**。

> **本 PR は「Phase 4-6 の `tested_commit_sha` を採る前に develop へ統合し、その後は失効対象パスを変更しない」ことを満たす必要がある。**

台帳上の参照は **F4**。

## 2. スコープ

### やること

1. ルート `pyproject.toml` へ **ruff・ty を backend と同版で固定**して追加し、`[tool.ruff]` / `[tool.ruff.lint]` / `per-file-ignores` / `pydocstyle` / `[tool.ty.*]` を設定する
2. **`uv.lock` を更新**する(**`uvx uv@0.8.13 lock`** で生成 — 下記リスク)
3. **ruff の残件 27 件を解消**する(自動修正 11・手動 16)
4. **ty の残件 40 件を解消**する(`scripts/` 8 ・`tests/` 32)。**`# ty: ignore` は使わない**
5. **CI の `harness` ジョブへ `ruff check` と `ty check` を追加**する
6. **`.claude/skills/check/SKILL.md` の harness 節**・**`AGENTS.md` のコマンド節**・**設計書 10.1** を追随させる

### やらないこと

| 除外するもの | 理由 |
| --- | --- |
| **`.claude/**` の検査**(hooks 7 本 + `codex_run.py`) | ruff 73 件 / ty 17 件あり、本タスクに混ぜると差分がレビュー不能になる。とくに **`codex_run.py` の 5 件は実バグ疑い**なので**別 follow-up・優先度「高」相当**で扱う。**台帳 H-13 は「部分対応」に留める**(「対応済み」にしない) |
| **`ruff format` の導入** | 行長 100 で **17 ファイル中 14 が reformat 対象**(数千行規模)。lint 導入と同一 PR に混ぜると合格条件が読めなくなる。**独立した機械的 PR** |
| **`onboarding.md:72` の陳腐化した件数**(「103 件」だが実際は 406) | 正本の改訂なので `/finalize-doc` を要する。同ファイルは現在 `status: draft` で **4-6 の前提として approved 化が必要**なので、**その approved 化タスクに含めるのが筋** |
| **新規テストの追加** | 本タスクの「テスト」は CI ジョブそのものとステップ 7 の変異テスト。テストを増やすと `onboarding.md` の件数記述に波及し、失効対象パスを不必要に触る |
| **`scripts/` のパッケージ化(静的 import 化)** | ルートは `[build-system]` を持たない仮想プロジェクトで、`scripts/*.py` の「直接実行 + モジュール」二重設計と衝突する。しかも **ty 側の得は 0**(二重 import は診断ゼロと実測) |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/development/dev-harness-design-2026-08-07.md` | **10.1 の CI ジョブ表の `harness` 行を現行化**(pytest だけでなく ruff・ty を実行することを反映)+ **実装追随の箇条**を追加 + 変更履歴表に追記。**規範は変更しない** | **PR レビュー**(実装追随の節更新 — 設計書 7.6-3 前段) |
| `docs/README.md`(索引) | 設計書の行の最終更新日を現行化 | PR レビュー |
| `docs/development/harness-evaluation.md`(運用評価台帳) | クローズ処理で判断する。**H-13 を「部分対応」として更新**(`.claude/**` が残るため「対応済み」にしない)+ **本タスクで得た知見**(型検査の欠落がレビューを通ったテストの実バグを隠していた) | PR レビュー(クローズ処理で実施) |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし** — 要件の改訂を伴わない | — |
| `docs/ops/nfr021-acceptance/README.md` | **反映なし** — 受入証跡の規範に触れない(失効対象パスを触るが、それは規範の変更ではない) | — |

**正本体系外だが同一 PR で更新するもの**(突合の対象外 — `check_plan_docs_sync.py` の除外集合): `AGENTS.md` / `.claude/skills/check/SKILL.md` / `.github/workflows/ci.yml` / `pyproject.toml` / `uv.lock` / `scripts/**` / `tests/**`。

## 4. 実装方針

### 重さ分類の根拠 = **通常**

**コア領域には該当しない。** `.claude/core-areas.json` の各領域 `paths` はすべて空で、**同期プロトコル / 状況計算 / 記録権 / テナント分離 / データ移行**のいずれの意味範囲にも触れない。

ただし **`.github/workflows/ci.yml` は `guard_paths` に含まれる**ため、**本 PR は人間の逐行確認が必須**である(設計書 6.3・`github-setup.md` 2 章手続 3)。

### 人間の裁定(確定済み・変更不可)

| # | 論点 | 裁定 |
| --- | --- | --- |
| 1 | `E501` の行長 | **ルートだけ 100**(backend は 88)。理由を設定にコメントで書く |
| 2 | `tests/` の `D103` 164 件 | **`tests/` だけ除外**(`scripts/` には `D` を効かせたまま) |
| 3 | CI への組み込み | **既存の `harness` ジョブへ追加**(別ジョブにしない) |
| 4 | `I001` の自動修正 | **ruff 既定のまま受ける**(空行 11 行の削除。backend と同一規則) |
| 5 | `attempt_id` の実バグ | **本タスクで直す**。ただし**修正して赤くなったら止めて裁定を仰ぐ** |

`D403`(先頭語を大文字に)は**日本語 docstring への誤検知**なので、既に除外されている `D415`(`backend/pyproject.toml:32`)と同じ理由で除外する。

### 実測値(裁定後の設定での残件)

| 検査 | scripts/ | tests/ | 計 |
| --- | --- | --- | --- |
| **ruff** | 6(I001 3・D301 2・E501 1) | 21(E501 11・I001 8・D301 2) | **27**(うち I001 11 は `--fix` で自動) |
| **ty** | 8 | 32 | **40** |

**行長の裁定の効果**: `E501` は **88 で 160 件 → 100 で 12 件**。ruff の `E501` は文字数ではなく**表示幅**で測り、日本語は全角 1 文字 = 2 桁で数えるため。

**`scripts/` は `F`(未使用 import・未定義変数などの実バグ系)が 0 件で、全関数に docstring がある。** 問題は ty 側に集中していた。

### `tests/` にも ty を掛ける(除外しない)

当初「テストが動的にモジュールを読み込むので ty が効かない」と見立てたが、**これは誤りだった**。typeshed の `ModuleType` は `__getattr__ -> Any` を持つため、`verify.foo` のような動的属性アクセス(**約 266 箇所**)は **1 件もエラーになっていない**。

32 件の真因は **6 ファイル・約 11 行**に閉じる:

| 真因 | 件数 | 該当 |
| --- | --- | --- |
| `spec_from_file_location` の `ModuleSpec \| None` を assert で絞っていないローダー 4 つ | 14 | `test_core_guard.py:334`・`test_hooks.py:421,1032,1163` |
| `**kwargs: object` の展開 | 5 | `test_feature_status.py:136` |
| `dict[str, object]` の値を unpack / `set()` | 8 | `test_nfr021_invalidating_paths.py:44` |
| ヘルパの戻り注釈が `-> object` | 3 | `test_verify_nfr021_evidence.py:1080,1097` |
| **テストの実引数誤り(実バグ)** | 2 | `test_nfr021_append_only.py:1185,1198` |

**`# ty: ignore` は 1 個も要らない。** 同じファイル内の `load_module` は既に `assert spec is not None and spec.loader is not None` を持ちエラーゼロなので、**既存イディオムを 4 箇所へ揃えるだけ**である。

**除外案を採らない理由**: 2026-08-19 の人間裁定「**`ty check` が緑にならない場合は除外設定で回避せず作業を止めて裁定を仰ぐ**」(`docs/worklog/2026-08-19-backend-skeleton.md:19`)。また backend は `include = ["src", "tests"]` で tests を検査しており、ルートだけ外すと「backend と違える理由」が 2 つ目になる(裁定済みの相違点は**行長だけ**)。

### `scripts/` の ty 8 件の直し方

- **7 件**: `parse_acceptance_path`(`verify_nfr021_evidence.py:571`)/ `parse_acceptance_record`(同 `:740`)の注釈を **`str | Path` → `str | PurePath`** へ広げる。両関数は本体で `PurePosixPath(str(...))` しかしておらず、**`str | PurePath` が `str`・`Path`・`PurePosixPath` をすべて含む最小の正しい型**(`Path` も `PurePosixPath` も `PurePath` の派生)。呼び出し側を `str()` に変える案は 7 箇所 × 2 ファイルを触り情報も落とすため劣る
- **1 件**(`feature_status.py:1611`): **実質バグではない**。`expected_feature_slug` が `branch is None` で必ず `None` を返し(`:1497`)`:1576` で抜けるため、到達時は非 None が保証される。ただし**同じ関数の他 3 箇所(`:1559`・`:1579`)は `worktree.branch or worktree.path.name` を使っており**、ここだけ素の `worktree.branch`。**そのイディオムへ揃える**(実行時の値は不変)
  - **`expected_slug` に差し替えてはいけない** — `tests/test_feature_status.py:803-804` がブロック名を**フルブランチ名**で引いており、`docs/features/feature-status/design.md:38` も表示仕様を規定している

### `pyproject.toml` に置く設定(**対象の限定を含む**)

**`.claude/**` を対象から外す設定が要る**(3 周目レビュー P1-1)。これが無いと `ruff check .` / `ty check` が
`.claude` を走査し、**合格条件の 27 件・40 件が成立しない**(実測: `.claude` に ruff 73 件・ty 19 件)。

```toml
[dependency-groups]
# ruff・ty の版は backend/pyproject.toml と同一に固定する。層ごとに版が割れると
# 同じコードへの CI の判定が層で食い違い、どちらが正か決められなくなる。
dev = ["pytest>=8", "ruff==0.16.3", "ty==0.0.73"]

[tool.ruff]
# 行長だけ backend(88)と違え 100 にする。
# 理由: ruff の E501 は文字数ではなく表示幅で測り、日本語は全角 1 文字 = 2 桁で数える。
# scripts/ と tests/ はコメント・docstring・アサーション文言が日本語主体のため、
# 88 では 1 行に入る日本語の情報量が英語の半分になり不自然な折り返しを強いる。
# 実測(2026-08-23): 幅 88 超 = 160 行 / 幅 100 超 = 12 行。
line-length = 100
target-version = "py312"
# backend/ は自前の pyproject.toml と CI の backend ジョブで検査済み(二重検査を避ける)。
# .claude/ の hooks・ラッパーは venv を使わず /usr/bin/python3 で起動される別系統で、
# 未検査の残件が 73 件あるため本タスクの対象外とする(H-13 の残余 — follow-up)。
extend-exclude = ["backend", ".claude"]

[tool.ruff.lint]
select = ["E", "F", "I", "D"]
# D415 は日本語の句点「。」を要約行の終端記号として認識しないため除外する。
# D403 も同じ理由(日本語の要約行の先頭語に英語の大文字化規則を当てる)。
ignore = ["D403", "D415"]

[tool.ruff.lint.per-file-ignores]
# テストは関数名そのものが仕様の記述であり、docstring の重複強制は情報を増やさない。
# scripts/ 側は D103 を効かせたままにする(公開関数の契約を docstring で持つため)。
"tests/**" = ["D103"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ty.environment]
python-version = "3.12"

[tool.ty.src]
# 検査対象を scripts/ と tests/ に限る(backend・.claude は上と同じ理由で対象外)。
include = ["scripts", "tests"]
```

**backend と違える設定は次の 3 つだけ**(それ以外は揃える):

| 相違点 | 値 | 理由 |
| --- | --- | --- |
| **行長** | 100(backend は 88) | 日本語の表示幅(上記の定量根拠) |
| **`D403` の除外** | ignore に追加 | 日本語 docstring への誤検知(`D415` と同型) |
| **`tests/**` の `D103` 除外** | per-file-ignores | 人間の裁定 2 |

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | ルート `pyproject.toml` へ ruff/ty の dev 依存(**backend と同版ピン** — ruff 0.16.3 / ty 0.0.73)と上記の設定ブロック(**`extend-exclude` と `[tool.ty.src] include` を含む**)を追加し、**`uvx uv@0.8.13 lock`** で `uv.lock` を更新する | **`uvx uv@0.8.13 sync --locked --dev` が成功**(CI と同じ版で検証する)/ **`uv.lock` の `version` と `revision` が不変** / **対象集合の確認**: `uv run ruff check . --statistics` と `uv run ty check` の出力に **`.claude/` と `backend/` のパスが 1 件も現れない** / `uv run ruff check .` が **27 件**(E501 12・I001 11・D301 4)/ `uv run ty check` が **40 件**(scripts 8・tests 32)/ `uv run pytest tests/` **652 件全緑**(件数不変) |
| 2 | ruff 自動修正の適用(`uv run ruff check --fix .` — I001 11 件) | `git diff --stat` が **11 ファイル・削除 11 行・挿入 0**(空行のみ)/ `uv run ruff check --select I .` が All checks passed / pytest 全緑 |
| 3 | ruff 手動残件: **E501 12 行の折り返し** + **D301 4 件の `r"""` 化** | `uv run ruff check .` が **All checks passed** / pytest 全緑 / **D301 の 4 箇所は docstring の文字列値が不変**(`\\|`→`\|` 等の脱エスケープを伴うため逐行確認)/ **`test_hooks.py` の heredoc・改行入りリテラルは 1 文字も変えない**(ガードの入力そのもの) |
| 4 | ty(scripts 8 件): 注釈を `str \| PurePath` へ広げ `PurePath` を import / `feature_status.py:1611` を `worktree.branch or worktree.path.name` へ | `uv run ty check` の **scripts/ 分が 0**(全体 32 件 = tests のみ)/ ruff 緑 / pytest 全緑 / `test_worktree_plan_resolution_failures_are_visible_in_text_and_hook` が緑(**表示値が不変であることの実測**) |
| 5 | ty(tests 機械的 30 件): ① 4 ローダーへ `assert spec is not None and spec.loader is not None` ② `test_feature_status.py:136` の `**kwargs: Any` ③ `test_nfr021_invalidating_paths.py:44` の `-> dict[str, Any]` ④ `test_verify_nfr021_evidence.py:1080,1097` の `-> Any`。②〜④ には「動的読み込みで静的型が付かない」旨の 1 行コメントを添える | `uv run ty check` の残りが **`test_nfr021_append_only.py` の 2 件だけ** / `from typing import Any` 追加後も ruff 緑(**I001 を再確認**)/ pytest 全緑 |
| 6 | **ty(tests 実バグ 2 件)**: `attempt_id(3, timestamp=...)` を `attempt_id(attempt_seq=3, timestamp=...)` へ(`test_nfr021_append_only.py:1185,1198`) | `uv run ty check` が **All checks passed** / `uv run pytest tests/` 全緑。**赤くなったら止めて報告する** — `check_nfr021_append_only.py` の欠陥を露出させた可能性があり、**除外や ignore で回避しない**(2026-08-19 の人間裁定) |
| 7 | 機構への接続と正本追随: ① `ci.yml` の `harness` ジョブへ `uv run ruff check .` と `uv run ty check` を `pytest` の**前に** 2 行追加 ② `.claude/skills/check/SKILL.md` の harness 節を 3 手順へ ③ `AGENTS.md` のコマンド節へハーネス行 ④ 設計書 10.1 の `harness` 行と実装追随の箇条 ⑤ `docs/README.md` の最終更新 ⑥ **台帳の H-13 を「部分対応」へ更新**(`.claude/**` の残余を明記し、**残余の follow-up の F-ID と worklog リンク**を `対応案` へ書く)+ 台帳の変更履歴 + 索引の台帳行の日付 | PR 上で **`harness` ジョブが緑** / **`ci.yml` の差分が `harness` の 2 行追加のみ**(他 8 ジョブ・`on`・`concurrency`・`permissions` が不変であることを base と構造比較)/ `uv run python scripts/check_docs_status.py` 緑 / `uv run python scripts/check_plan_docs_sync.py` 緑 / **変異テスト 2 件**(下記)/ **最新 PR HEAD で必須 5 ジョブがすべて green** (`github-setup.md` 2 章手続 2 — 古い green で判断しない) |

**委任の方針**: ステップ 1〜6 は Codex へ委任(`codex_run.py implement`・重さ分類 通常 → terra / max)。**ステップ 7 は `ci.yml` が `guard_paths` のため Claude が起草し、人間の逐行確認を受ける**。**各ステップ完了後、変異テストを PR 作成者(Claude)が自分で再現する**(委任先の自己申告で代替しない — 台帳 H-49)。

**CI 接続を最後に置く理由**: 途中のステップで CI を赤にしないため(`backend-skeleton` の前例と同じ)。

## 5. DoD(受け入れ基準)

- [ ] ルート `pyproject.toml` に **ruff・ty が backend と同版で固定**されている(ruff 0.16.3 / ty 0.0.73)
- [ ] **`uv.lock` の `version` と `revision` が不変**で、`uv sync --locked --dev` が成功する
- [ ] `uv run ruff check .` / `uv run ty check` / `uv run pytest tests/` が**ルートですべて緑**
- [ ] **`# ty: ignore` を 1 個も使っていない**(除外設定で回避していない — 2026-08-19 の人間裁定)
- [ ] **backend と違える設定が 3 つ(行長 100 / `D403` の除外 / `tests/**` の `D103` 除外)に限られ**、**それぞれの理由が設定のコメントに書かれている**(行長は定量根拠つき)
- [ ] **CI の `harness` ジョブ**で ruff・ty が実行され、**`ci.yml` の差分が `harness` の 2 行追加のみ**である
- [ ] **`.claude/skills/check/SKILL.md`・`AGENTS.md`・設計書 10.1・`docs/README.md` が追随**している
- [ ] **変異テスト 2 件を PR 作成者が再現**した(幅 101 桁の行で `ruff check` が落ちる / `str` 引数へ `None` を渡して `ty check` が落ちる)
- [ ] **`.github/workflows/ci.yml` について人間の逐行確認**を受けた(`guard_paths`)
- [ ] **台帳の H-13 が「部分対応」へ更新**され、**`.claude/**` の残余に F-ID と worklog リンク(または日付つき PO 見送り裁定)が付いている**(**`高` の項目の必須要件** — 台帳「追跡優先度の判定条件」節)。**「対応済み」にしない**
- [ ] **範囲外の 4 件が申し送りとして記録**されている(`.claude/**` の検査 / `ruff format` / `onboarding.md` の件数 / 新規テスト)
- [ ] **`attempt_id` の実バグの顛末が記録**されている(修正して緑なら「空転していたが結論は変わらない」、赤なら**止めて裁定を仰いだ**旨)

## 6. テスト計画

NFR-019 の対象種別: **該当なし**。本タスクは**検査機構の導入**であり、製品のドメイン計算・認可行列・E2E・同期プロトコルのいずれにも触れない。

| 種別 | 追加するもの |
| --- | --- |
| **既存テストの維持** | `uv run pytest tests/` **652 件**が全ステップで緑であり続けること。**件数を増減させない**(`onboarding.md` の件数記述に波及するため) |
| **CI ジョブ** | `harness` ジョブでの `ruff check` / `ty check` の実行そのものが本タスクの「テスト」 |
| **変異テスト**(PR 作成者が再現) | ① **幅 101 桁の行**を 1 箇所入れ `ruff check` が非 0 で落ちる ② **`str` 引数へ `None` を渡す行**を 1 箇所入れ `ty check` が非 0 で落ちる。**いずれも実測後に戻す**(合格条件が実効性を持つことの確認 — 台帳 H-48 の型の予防) |
| **表示値の不変**(ステップ 4) | `test_worktree_plan_resolution_failures_are_visible_in_text_and_hook` が緑であること(`feature_status.py:1611` の変更が表示を変えていないことの実測) |
| **docstring の不変**(ステップ 3) | D301 の `r"""` 化で**文字列値が変わらない**ことを逐行確認 |

## 7. リスク

| 度合い | 内容 |
| --- | --- |
| **高** | **`uv.lock` の revision ドリフト** — ローカル uv は 0.11.21、CI の setup-uv は **0.8.13 ピン**、現行 lock は `version = 1 / revision = 3`。素の `uv lock` で revision が上がると **`harness` ジョブが `uv sync --locked` で落ちる**。**ルートの lock を使うのは `harness` だけ**(`ci.yml:80`)で、backend は `working-directory: backend` の別 lock(`ci.yml:181,193`)— 当初「CI 5 ジョブ全部」と書いたのは誤りだった(レビュー P1-3 で是正)。**`uvx uv@0.8.13 lock` を使い、lock ヘッダの不変と 0.8.13 での同期成功を合格条件に含める** |
| **高** | **`ci.yml` は `guard_paths`** — PR 本文の逐行確認チェックを ON にしないと `core-guard` が落ちる。**実際に人間の逐行確認が必要**であり、チェックを付けた人 = 確認した人の運用規律で担保される |
| **中** | **ステップ 6 が赤くなる可能性** — 実引数の是正で `check_nfr021_append_only.py` の欠陥が露出しうる。露出したら **NFR-021 の機構修正**となり本タスク(重さ「通常」)を超える。**止めて裁定を仰ぐ** |
| **低** | **`ruff format` 未導入のドリフト** — フォーマッタを入れないまま lint だけ入れるため、整形は各自の裁量のままになる。`/check` の harness 節に「**`ruff format` を走らせない**」旨を明記して誤用を防ぐ |
