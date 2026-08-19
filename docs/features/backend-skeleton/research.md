---
feature: backend-skeleton
type: research
date: 2026-08-19
---

# 調査メモ: Phase 4-2 backend 骨格(uv / ruff / ty / pytest)+ CI の backend ジョブ

## 問い

TSK-223(Phase 4-2)で **何を作り、何を作らないか**。要件・設計書・ADR・前例(4-1 / 4-3)・ハーネス機構が課す制約はどこにあり、前例で実際に踏まれた落とし穴は何か。

## 結論(要約)

- **スロットの性格**: 4-2 のマージ条件は**通常の PR 要件のみ**(確定ゲート不要・**NFR-021 判定を行わない**)。4-1・4-3 は既にマージ済みで、順序上いつでも着手できる。
- **成果物の仕様は既に正本で決まっている**: `backend/` は FastAPI・`src/pitchlog/` + `tests/`・uv で版完全固定。CI backend ジョブは `uv sync` → `ruff check` + `ruff format --check` → `ty check` → `pytest --cov`、**paths filter は `backend/` と `contracts/`**(+ 前例より `.github/workflows/ci.yml` 自身)。**設計を発明する余地はほぼ無く、作業は「正本どおりに置く」こと**に閉じる。
- **骨格に入れてはいけないものが明確にある**: **ドメイン計算コードを 1 行でも置くと**、要件 NFR-018 と ADR-003 が宣言モデル正本・生成物・製品経路の呼び出し部・3 層検査を**同一変更で**要求する(= 4-2 が TSK-235 に化ける)。NFR-019 の (a) 一致性 /(b) 越境 /(c) E2E /(d) 故障系も要件書が **Phase 4 完了時の対象外**と明文化している。
- **旧システム側の示唆(センチネル正規化・所有権必須引数・冪等キー等)は「置き場と申し送り」として扱い、実体は骨格に入れない**(下記「裁定した矛盾」)。
- **最大のリスクはツールではなく機構**: `backend/pyproject.toml` を置いた瞬間に `/check` の 4 種と保存時 ruff が有効化され、`ci.yml` は `guard_paths` で core-guard が発火する。加えて `/pr` の機械突合(H-64 / H-67)が**原因の分からないエラーで止まる**前例が 2 件ある。

## 詳細と典拠

### 1. スロットの位置づけとマージ条件

| 事項 | 結論 | 典拠 |
| --- | --- | --- |
| 4-2 の定義 | 「backend 骨格(uv / ruff / ty / pytest 雛形)+ CI の backend ジョブ」 | `docs/development/dev-harness-design-2026-08-07.md:797` |
| マージ条件 | 通常の PR 要件(`/check` 全グリーン + CI 全ジョブ緑 + 反対側レビュー + 人間マージ)。**NFR-021 判定は行わない** | 同 `:796`(4-1 行を「同上」で参照)・`:804` |
| 順序 | 4-1 先行 → **4-2 / 4-3 は相互任意** → 4-4 の確定ゲート → … | 同 `:810` |
| NFR-021 判定の所在 | Phase 4 **全体に対して 1 回**、4-6 が `gate_kind: phase4` で実施 | 同 `:790`・`:801` |
| 4-6 が判定する合格項目(4-2 の成果物が対象になる) | 「backend の pytest が成功し、開発 DB へ接続でき、**backend / frontend が起動して疎通確認できること**」 | `docs/requirements/requirements-pitchlog-2026-07-22.md:921` |

### 2. 成果物の仕様(正本が既に決めているもの)

| 対象 | 決定内容 | 典拠 |
| --- | --- | --- |
| 言語・フレームワーク | **Python / FastAPI**(変更には承認を要する) | 要件書 `:974` |
| ディレクトリ | `backend/` = FastAPI・uv 管理(`pyproject.toml` / `uv.lock` / `.python-version`)、配下に `src/pitchlog/` と `tests/` | 設計書 `:159-161` |
| パッケージ管理 | uv。`backend/pyproject.toml` + `uv.lock` + `.python-version` で**完全固定** | 設計書 `:189` |
| リンタ | ruff。**`[tool.ruff.lint.pydocstyle] convention = "google"` を必須設定**・日本語コメント許容 | 設計書 `:190`、AGENTS.md:19 |
| 型検査 | ty(**プレビュー段階**。代替 mypy への切替は **ADR 起票の上**) | 設計書 `:191`・`:834`(論点E) |
| テスト | pytest(+ pytest-cov / pytest-asyncio / httpx)。**backend のテストを pytest 以外に分散させない** | 設計書 `:192`、要件書 NFR-019 `:899` |
| 実行形式 | すべて `uv run <cmd>` に統一(CI と同一コマンド) | 設計書 `:195` |
| CI backend ジョブ | `uv sync` → `ruff check` + `ruff format --check` → `ty check` → `pytest --cov`(**paths filter: `backend/` `contracts/`**) | 設計書 `:606` |
| paths filter に `contracts/` | **4-3 からの明示的な申し送り**(「backend ジョブの paths filter に `contracts/` — 4-2 で」) | `docs/features/dev-db-contracts/plan.md:154`・`:53` |
| paths filter に `ci.yml` 自身 | 4-1 の計画レビュー P1-3 由来。**同型に踏む** | `docs/features/frontend-skeleton/plan.md:168` |
| Action の pin | **全 Action をコミット SHA pin**(コメントで版併記) | 設計書 `:618`、現物 `.github/workflows/ci.yml` |
| 既存ジョブ | 発火条件を変えない(4-1 は既存 4 ジョブへ 0 行削除で追加) | `docs/worklog/2026-08-16-frontend-skeleton.md:196-197` |
| Alembic | 「SQLAlchemy 前提。**設計フェーズで最終確定**」= 4-2 では未確定 | 設計書 `:193` |

**CI の現物構造(実測)**: `frontend-changes`(`dorny/paths-filter` を SHA pin した判定専用ジョブ)→ `frontend`(`needs` + `if:` で `workflow_dispatch` か filter 真のとき起動)の二段構成。`defaults.run.working-directory` で層のディレクトリを固定している。backend も同型に置ける。

### 3. 骨格に入れないもの(要件・ADR-003 由来の境界)

| 入れないもの | 理由 | 典拠 |
| --- | --- | --- |
| **ドメイン計算コード(状況計算・集計・座標変換・成績公式)** | 対象計算コードの追加は、宣言モデル正本・生成物・製品経路の呼び出し部・3 層検査を**同一の変更**として要求する。ADR-003 も「この段階では対象計算のコードを追加しない」 | 要件書 `:872`・`:885`・`:895`、`docs/adr/ADR-003-domain-calc-method.md:374` |
| NFR-019 (a) 一致性 /(b) 越境 /(c) E2E /(d) 同期故障系のテスト実体 | 要件書が **Phase 4 完了時の対象外**と明文化。正解ベクタ未完成の間は (a) を合格判定してはならない | 要件書 `:921`・`:894` |
| `backend/domain/manifest.json`・生成器・検査基盤・ベクタ本体 | ADR-003 が**後続タスクへ送るもの**として明記(TSK-235〜239) | ADR-003 `:387-390`、`docs/worklog/2026-08-18-adr003-domain-calc-method.md:105-113` |
| `.claude/core-areas.json` の `areas[].paths` 充填 | 6.3 落とし込み規則 ⑤ で**敵対レビュー + 人間承認**が要る = 4-2 のマージ条件で通せない(TSK-228)。4-3 も同じ理由で除外した | 設計書 `:349`、`docs/features/dev-db-contracts/plan.md:48` |
| ルート `pyproject.toml` への ruff / ty 導入 | **F4(TSK-211)・台帳 H-13 の担当**。4-2 で入れると別タスクのスコープを食う | `docs/development/harness-evaluation.md:388-397` |
| `.claude/nfr021-invalidating-paths.json` | **4-4 の担当**(確定ゲート対象) | 設計書 `:799` |
| i18n / タイムゾーン切替の抽象 | 要件 2.2 の Won't(多言語・タイムゾーン対応)と衝突。日時は JST 基準 | 要件書 `:91`・`:932`・`:978` |
| 実データ | 移行実データの取り扱い統制が未整備(台帳 H-56)。4-3 も空 DB のみ | `docs/development/harness-evaluation.md:701-710` |

**骨格でも守るもの**: サーバーはステートレス(プロセス内に試合状態を持たない — 要件書 `:975`)/ シークレットは環境変数のみ・リポジトリに含めない(NFR-014 `:842-845`。測定方法がリポジトリ走査なので骨格から効く)/ pytest が**CI から実際に実行される経路**であること(旧システムは「pytest 形式 74 件超が未実行」だった — `docs/improvements-from-baseball-scoring.md:232`)。

### 4. 旧システム由来の設計示唆(実体は後続・置き場だけ意識する)

旧 Baseball_Scoring は Streamlit 単一プロセスで、`app/` / `services/` / `domain/`(純粋ルール 12 モジュール・Streamlit 依存ゼロ)/ `db/`(素の sqlite3・psycopg2、**ORM 不使用**)/ `analytics/` / `charts/` / `reports/` に分かれていた(`docs/legacy/research/domain-logic.md:21-28`・`:13`、`docs/legacy/research/tech-stack.md:17`)。**旧 FastAPI 版 API も実在したが、そのディレクトリ構成・ルーター分割は `docs/legacy/` の調査資料に記述がなく不明**(`docs/legacy/requirements-tsukuba-pss-v0.2.md:483`・`:486`、`docs/legacy/baseball-scoring-db-structure.md:24`)。**旧側の構成を骨格へ写す判断はできない。**

骨格の**構造判断に効く**旧側の事実(実装はしない):

- **集計だけが多重実装で崩れた**: 得点導出が `apply_scoreboard_event` と `update_list` で二重、同一指標(被打率・投球回)が `cal_stats` と `charts/` で二重(`docs/legacy/research/domain-logic.md:174`、`docs/legacy/research/analytics-reports.md:121`)。→ NFR-018 / ADR-003 の背景そのもの。**骨格で「ドメイン計算の置き場」を勝手に切らない**理由でもある(置き場の正は ADR-003 = `backend/domain/`)。
- **所有権ガードが全関数でオプショナル引数**で、省略すると全データにアクセスできた(`docs/legacy/research/data-layer.md:397`)。→ テナント分離はコア領域。リポジトリ層を書く段(後続)で**必須引数**にする申し送り。
- **`プレイの番号` に UNIQUE 制約が無く**、リトライで重複挿入が起き得た(同 `:402`・`:404`)。→ 冪等キーの API 契約化は後続。
- **センチネル同居**(`0` / `"0"` / 空文字 / NULL が意味的に混在)と**列名と実体の乖離**(列55「タイムの種類」= エラー選手の守備番号、列60「打席Id」= フリーコメント)(同 `:236`・`:147-148`・`:410`)。→ 正規化層の単一入口は移行・モデル層タスクの論点。
- **遅延マイグレーション**(読み書きのたび `_ensure_table()`)がリクエストパスに DDL を混ぜていた(同 `:399`)。→ マイグレーションは起動時/CLI に置く(Alembic は設計フェーズで最終確定 — 設計書 `:193`)。
- 旧テストは **unittest・38 ファイル・300 テスト**で pytest/coverage/CI 設定なし。ただし「契約テスト」(88列固定・DDL 同期・所有権ガード・成績公式・リプレイ恒等式)の運用は確立していた(`docs/legacy/research/docs-tests-ops.md:69`・`:72-81`・`:169-183`)。→ **pytest への正規化は新規に行う**。旧テストは移行の検証ベクタとして後続で再利用する。

### 5. ハーネス機構の地雷(本 PR で実際に踏みうるもの)

| # | 地雷 | 発火条件 | 典拠 |
| --- | --- | --- | --- |
| 1 | **`/check` の backend 層 4 種が一斉に必須化** | `backend/pyproject.toml` を置いた瞬間。1 つでも落ちると `/check` が赤 | `.claude/skills/check/SKILL.md:14-19`、前例 `docs/features/frontend-skeleton/plan.md:152` |
| 2 | **保存時 ruff の自動実行が始まる** | 同上(`backend/pyproject.toml` の存在が条件)。`.py` 保存のたび `ruff format` + `ruff check --fix` | `.claude/hooks/format_on_save.py:50-52` |
| 3 | **core-guard 発火 + 人間逐行確認チェック必須** | `.github/workflows/ci.yml` が `guard_paths`(完全一致 7 件のひとつ) | `.claude/core-areas.json:3-11`、`scripts/core_guard.py:17`・`:272-277`、設計書 `:335` |
| 4 | ローカル `core_guard.py` は合格条件にならない | 非 PR イベントでは skip する | `scripts/core_guard.py:256-258`、`docs/features/dev-db-contracts/plan.md:106` |
| 5 | **領域ガードは backend コードを置いても発火しない**(H-12) | `areas[].paths` が全 5 領域とも空。重さ分類の根拠として計画書に明記が要る | `.claude/core-areas.json:13-17`、`docs/development/harness-evaluation.md:377-386` |
| 6 | **`/pr` が `check_plan_docs_sync.py` で止まる(H-64)** | 計画書 3 節の**同じ行**に、その行の宣言と異なる宣言語(「反映なし」等)を書くと exit 1 | `docs/development/harness-evaluation.md:788-797` |
| 7 | **同(H-67)** | 3 節のコード span を**相対パス**で書くと未宣言扱い。**root 基準(`docs/...`)で書く**。エラーは「未宣言」としか言わない | 同 `:821-830` |
| 8 | **ステップ後の欠陥修正コミットの記法が規約に無い(H-60)** | レビュー・CI 由来の修正コミット。4-1 は「`fix:` + 記法なし」を選び理由を明記 → 以後 `ステップ進捗` が「不明」に落ちた(H-58) | 同 `:745-753`・`:723-732` |
| 9 | サンドボックスのキャッシュが EROFS に当たる | 書き込み可能領域が worktree と `/tmp` に限られる。pnpm では `COREPACK_HOME` を `/tmp` へ逃がして回避。**uv でも同種の退避が要る可能性(要実測)** | `docs/worklog/2026-08-16-frontend-skeleton.md:170-171` |
| 10 | 依存取得にネットワーク例外が必須 | `PITCHLOG_ALLOW_NET=1` + `PITCHLOG_NET_REASON`(ラッパーが理由なしを拒否)+ PO への事前報告 | 同 `:162-166` |
| 11 | 計画書の列挙が実物より狭くなる | 4-1 でディレクトリ 3 件・依存の取りこぼしが実際に発生 | 同 `:191-195` |
| 12 | 計画書の合格条件のコマンドが実環境で通らない | 4-3 の `SHOW lc_collate`(PG17 で廃止)。実装時に訂正して worklog へ記録する運用 | `docs/worklog/2026-08-17-dev-db-contracts.md:29` |

**H-68(追跡優先度 高)の適用**: 4-2 は確定ゲート不要だが、「**(A) 方式が分岐する /(B) 実装時に決めれば足りる**」の分類を計画レビューに持ち込み、**(B) を計画書で閉じようとしない**(`docs/development/harness-evaluation.md:832-841`)。

### 6. Web 調査(/research — Codex 委任、調査基準日 2026-08-19)

`codex_run.py research`(read-only + live search・terra high)へ委任。**Claude 側で一次ソースを再確認した項目には【検証済】**、Codex 報告のみで未確認のものには【未検証】を付す。

#### 6-1. ty(型検査)

- **【検証済】ty は beta。`0.0.x` 系で「安定 API を持たず、診断を含む破壊的変更が任意の版間で起こり得る」と README が明記**([astral-sh/ty README](https://github.com/astral-sh/ty))。
- **【検証済・Codex の版情報を訂正】最新は 0.0.73(2026-08-19 リリース)**([Releases](https://github.com/astral-sh/ty/releases))。Codex の報告は 0.0.65(2026-07-29)で約 3 週間古かった。**リリース間隔が数日単位**であり、**`uv.lock` による版固定が「CI が今日緑なら明日も緑」の唯一の担保**になる。
- 【未検証】設定は `pyproject.toml` の `[tool.ty]` が正式サポート。除外は `[tool.ty.src] exclude`(gitignore 形式)。終了コードは 0 = 問題なし / 1 = warning 以上 / 2 = 設定不正([設定](https://docs.astral.sh/ty/configuration/)・[除外](https://docs.astral.sh/ty/exclusions/)・[終了コード](https://docs.astral.sh/ty/reference/exit-codes/))。
- 【未検証】**`requires-python` を書かないと ty の既定ターゲットが現行 3.14 になる** → `project.requires-python` か `[tool.ty.environment] python-version` の**どちらかは必須**。
- 【未検証】**ty は mypy plugin 非対応**([typing FAQ](https://docs.astral.sh/ty/reference/typing-faq/))。Pydantic / SQLAlchemy の組込み対応は検討中。→ **後続で SQLAlchemy を入れたときが本当の分岐点**であり、骨格段階の緑は将来を保証しない。
- 【未検証】mypy への退避の最小差分: dev 依存を `ty` → `mypy` に替え、CI を `uv run mypy` に。`[tool.mypy] python_version / files / warn_unused_configs`(+ 厳格度を寄せるなら `check_untyped_defs = true`)。**設計書 `:191`・`:834` により切替には ADR 起票が要る**点は変わらない。

#### 6-2. uv(版固定・レイアウト・モノレポ)

- 【未検証】**CI は `uv sync --locked`**(lock の最新性を検証し不一致なら失敗)。`--frozen` は検証せずそのまま使う([sync 概念](https://docs.astral.sh/uv/concepts/projects/sync/))。
- 【未検証】開発依存は旧 `[tool.uv] dev-dependencies` ではなく **PEP 735 の `[dependency-groups]`**([dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/))。
- 【未検証】**`src/pitchlog/` を配るには `[build-system]` を明示する**(build system が無いと `uv sync` がプロジェクト自身を install しない)。`[build-system]` があれば `[tool.uv] package = true` は冗長([packaging ガイド](https://docs.astral.sh/uv/guides/package/)・[config](https://docs.astral.sh/uv/concepts/projects/config/))。
- 【未検証・**未解決 4 への回答**】**uv workspace を宣言しない限り root と `backend/` は独立プロジェクト**で、root の `uv sync --locked` は backend を lock / sync しない([workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/))。→ CI の `harness` ジョブへの影響は無い見込み。**ステップの合格条件として実測する**方針は維持。
- 【未検証・**新たな落とし穴**】**`.python-version` は project 境界を越えて探索されない**([Python versions](https://docs.astral.sh/uv/concepts/python-versions/))。**`backend/` から uv を起動するとルートの `3.12.3` は効かない** → `backend/.python-version` を置くか、CI で `UV_PYTHON` / `--python` を明示する必要がある(**未解決 3 に対する具体的な選択肢**)。

#### 6-3. GitHub Actions での uv

- 【未検証】`astral-sh/setup-uv` の最新は **v9.0.0**(2026-07-21)= **既存 CI の pin は現行**。**v9 で `prune-cache` の既定が false に変わった**ため、既存 CI が明示している `prune-cache: true` は意図どおり([v9.0.0 release](https://github.com/astral-sh/setup-uv/releases/tag/v9.0.0)・[caching](https://github.com/astral-sh/setup-uv/blob/main/docs/caching.md))。
- 【未検証】`cache-dependency-glob` に `backend/pyproject.toml` と `backend/uv.lock` を明示するのが推奨。`defaults.run.working-directory` は **`run:` ステップにしか効かない**(action の入力には効かない)。
- 【未検証・**地雷 9 への回答**】**`UV_CACHE_DIR`(または setup-uv の `cache-local-path`)で書き込み可能領域へ退避できる**([環境変数](https://docs.astral.sh/uv/reference/environment/)・[storage](https://docs.astral.sh/uv/reference/storage/))。pnpm の `COREPACK_HOME` 退避と同型の対処が uv でも取れる。
- **注意(Codex 出力の誤り)**: 提示された CI 例が `actions/checkout@v7` を**タグ参照**していた。**本リポジトリの規約は全 Action の SHA pin**(設計書 `:618`)なので、既存 `ci.yml` の pin をそのまま流用する。

#### 6-4. ruff

- **【検証済】既定は `line-length = 88` / `target-version = "py310"`。`target-version` 未指定時は近傍 `pyproject.toml` の `requires-python` から推論される**([Ruff configuration](https://docs.astral.sh/ruff/configuration/))。→ **未解決 3 の「ruff の設定値」は、`requires-python` を書けば推論に委ねられる**(明示するかは計画で決める)。
- 【未検証】**`convention = "google"` だけでは docstring 検査は動かず、`[tool.ruff.lint] select` に `D` を入れる必要がある**([pydocstyle settings](https://docs.astral.sh/ruff/settings/#lintpydocstyle))。**この 1 点は Claude 側で当該記述を確認できなかった(該当節が取得できず) → 実装時に実測で確認する**。設計書 `:190` が要求するのは convention の設定だが、**`select` を落とすと機構検査が空回りする**ため合格条件に含める価値がある。
- 【未検証】**日本語の docstring / コメントは ruff・Google convention の障害にならない**(Ruff は文書の言語を制限しない)。
- 【未検証】役割分担: `ruff check` = lint + import 整列 + docstring 規約 / `ruff format --check` = 整形差分の検出。**CI は両方**(設計書 `:606` と一致)。

#### 6-5. FastAPI 骨格と pytest

- **【検証済】FastAPI 公式が `pyproject.toml` の `[tool.fastapi] entrypoint = "<module>:app"` を案内している**([First Steps](https://fastapi.tiangolo.com/tutorial/first-steps/))。`fastapi dev` がこれを読む(VS Code 拡張等も参照)。
- 【未検証】最新安定版は **FastAPI 0.140.8(2026-07-28)/ Pydantic 2.13.4(2026-05-06)**。Pydantic 2.14.0a1 は pre-release のため採らない。
- 【未検証】**health エンドポイントの URL・スキーマは FastAPI が規定していない**(`/health`・`{"status": "ok"}` はプロジェクト規約としての提案)。
- 【未検証】テストは、同期のみなら公式 `TestClient` が最短。**後続で async を扱う前提なら初めから `httpx.AsyncClient` + `ASGITransport` + `pytest.mark.anyio`**(FastAPI 公式の async テストは AnyIO を使う → **pytest-asyncio は必須ではない**)([Testing](https://fastapi.tiangolo.com/tutorial/testing/)・[Async Tests](https://fastapi.tiangolo.com/advanced/async-tests/))。
  - **設計書 `:192` は pytest-asyncio を挙げている**ため、**AnyIO 方式を採るなら設計書 5.1 との差が生じる**(実装追随の節更新で足りる範囲か、計画で判断する)。
- 【未検証】`ASGITransport` では **lifespan が自動実行されない**。DB プールを lifespan で開閉するようになった時点で `asgi-lifespan` 等の明示導入が要る。

#### 6-6. PostgreSQL 接続・Alembic(骨格では入れない前提の申し送り)

- 【未検証】現行の選択肢は 同期 = psycopg 3 / 非同期 ORM = SQLAlchemy 2.x async + asyncpg or psycopg / 非同期 SQL 直書き = asyncpg。Codex の第一候補は **SQLAlchemy 2.x async + psycopg 3**。
- 【未検証】**Alembic 自体は async API を持たず**、AsyncEngine 経由で使う。非同期採用時の雛形は `alembic init --template async`([Alembic cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic))。
- **骨格 PR での帰結**: `psycopg` / `asyncpg` / `sqlalchemy` / `alembic` は**依存に入れない**(設計書 `:193` が「Alembic は設計フェーズで最終確定」としており、未使用ドライバを骨格に入れる根拠がない)。**DB URL・engine・session を `main.py` に置かず、後続で `infrastructure/db/` 等へ閉じ込められる構成**にしておく。

## 裁定した矛盾

- **旧システム側の「骨格で先に用意しておくと後で困らないもの」 vs 要件・ADR-003 の「骨格にドメイン計算を置かない」** → **後者を採る**。旧側の指摘は「旧システムで実際に壊れた箇所」という強い典拠を持つが、**成績公式の定数モジュール・ドメイン計算の単一置き場・リプレイ整合性検証**は要件書 `:872` と ADR-003 `:374` が明示的に禁じる範囲に入る(置いた時点で宣言モデル・生成器・3 層検査が同一変更で必要になる)。**採用形態を変えて活かす**: 実体は作らず、**計画書の「やらないこと」と申し送りに根拠付きで記録**し、後続タスク(TSK-235〜239・移行タスク)の入力にする。
- **旧資料内の食い違い**(テーブル数 12 / 13・`ON DELETE CASCADE` の有無・接続プールの種類とサイズ)が `docs/legacy/research/data-layer.md` と `docs/legacy/baseball-scoring-db-structure.md` の間にあるが、**いずれも 4-2 のスコープ外**(骨格は DB 接続を実装しない)。**移行タスクへの申し送り**として記録するにとどめ、本タスクでは裁定しない。
- **「backend が起動して疎通できる状態」を作るスロット** → 13 章 4-2 行の文言(「uv / ruff / ty / pytest 雛形」)には**明示がなく**、要件書 `:921` の疎通確認は 4-6 の受入判定項目。**4-1・4-3 が閉じている以上、残るのは 4-2 か 4-6 のみ**。要件書 `:974` が FastAPI を指定し、設計書 `:159-161` が `backend/` を FastAPI と定めているため、**最小アプリ(health エンドポイント)までを 4-2 に含めるのが自然**だが、**割り当てを明示した決定は存在しない** → **/plan で人間裁定を仰ぐ論点**(下記「未解決」1)。

## 未解決・申し送り

1. **【要人間裁定】最小 FastAPI アプリ(health エンドポイント + その pytest)を 4-2 に含めるか**。含めない場合、要件書 `:921` の「backend が起動して疎通確認できる」を満たすのは 4-6 になる(4-6 の負荷が増え、4-2 は「動かない骨格」で閉じる)。
2. **【要人間裁定】`ty check` が骨格で緑にならない場合の退避**。ty は **beta・`0.0.x`・破壊的変更あり得ると公式明記**で、リリースは数日単位(6-1)。mypy への切替は **ADR 起票が必要**(設計書 `:191`・`:834`)。骨格で詰まると 4-2 の中で ADR タスクが発生する。**なお本当の分岐点は SQLAlchemy を入れる後続段階**(ty は mypy plugin 非対応)。
3. **`backend/.python-version` の要否**。**`.python-version` は project 境界を越えて探索されない**(6-2)ため、**ルートの `3.12.3` は `backend/` から起動した uv には効かない**。`backend/.python-version` を置く / CI で `UV_PYTHON` を明示する / 各コマンドで `--python` を渡す の 3 択 → **実装時に決めれば足りる (B)**。ruff の `line-length` / `target-version` は **`requires-python` から推論される**ため、明示するかも (B)。
4. **ルート `uv sync --locked --dev`(CI の `harness` ジョブ)が `backend/pyproject.toml` 追加の影響を受けないか** → **uv workspace を宣言しない限り独立プロジェクトなので影響しない**(6-2)が、**どの決定文書にも記載がないため、ステップの合格条件として実測で確認する**。
4-b. **`[tool.ruff.lint] select` に `D` を入れないと `convention = "google"` が空回りする**(6-4・**Claude 側で未確認**)。設計書 `:190` の要求を実効化するため、**実測して合格条件に含めるか**を計画で決める。
4-c. **テストの非同期方式が設計書 5.1 と食い違う可能性**。設計書 `:192` は **pytest-asyncio** を挙げるが、FastAPI 公式の async テストは **AnyIO**(6-5)。AnyIO 方式を採るなら設計書 5.1 の追随更新(実装追随の節更新で足りるか)を計画で判断する。
5. **`.claude/rules/backend.md` / `testing.md`** は設計書 `:527-532` が「Phase 4 で導入」とするがスロット未指定。**4-1 も `frontend.md` を作らなかった**(実測: `.claude/rules/` は `docs.md` のみ)。4-2 で作るかは計画で決める。
6. **`docs/design/`(設計書 4 章の目標ツリーにある)が未作成**。backend のアーキテクチャ文書を要求されるかは不明(4-1 でも論点化したが決着記録なし)。
7. **H-57**(CI ジョブ表に NFR-019 (b)(d) の行が無い)に 4-2 で気づく可能性がある。追記は「実装追随の節更新」扱いで可(設計書 7.6-3 前段)。
8. **`.env.example` が読めない件は台帳に既出**(計画レビュー 1 周目 P1 の指摘で確認・当初「本調査で発見」と書いたのは誤り)。`docs/development/harness-evaluation.md` の**候補 (1)**「`.env.example` が Read deny の glob に巻き込まれる」がそれで、**昇格条件は「`.env.example` を読めないことで作業が止まる事例が出た場合」**。本タスクは同ファイルを読まず DB 設定も対象外のため**条件を満たさない** → `H-*` 起票は行わない。
   - **ただし候補 (1) の「昇格しない理由」に書かれた前提は実測と食い違う**: 同項は「**Bash 経由で実務は回る**」ため実害が小さいとするが、**2026-08-19 の実測では Bash の `cat .env.example` も拒否された**(`.claude/settings.json:42` の `Read(./.env.*)` が Bash のファイル読み取りにも照合されるため)。`.claude/hooks/secret_guard.py:35` は exact `.env.example` を明示的に許可しており、**フックの設計意図と permissions の実効が食い違っている**。**昇格判断そのものは本タスクの範囲外**として PO・別タスクへ申し送る。
9. **本番誤接続の機構的な歯止め**は 4-3 が「backend 実装時 = 4-2 以降へ」と送っている(`docs/features/dev-db-contracts/plan.md:86`・`:152`)。4-2 のスコープに含めるかを計画で判断する。
