---
feature: backend-skeleton
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-08-19・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: 通常            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3bf93b75e6878124adfbd7d81eb1d9a1
branch: feature/backend-skeleton
created: 2026-08-19
計画レビュー周回: 2        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: Phase 4-2 backend 骨格(uv / ruff / ty / pytest)+ CI の backend ジョブ

## 1. 背景・目的

- **Notion タスク**: [TSK-223](https://app.notion.com/p/3bf93b75e6878124adfbd7d81eb1d9a1)
- **位置づけ**: ハーネス設計書 13 章「Phase 4 の分割」の論理スロット **4-2**。4-1(frontend 骨格 / TSK-219)と 4-3(docker-compose + contracts 雛形 / TSK-222)はマージ済みで、**現時点で着手可能な次のスロットは 4-2 のみ**(4-4〜4-6 も未着手だが、設計書 13 章の順序上 4-2 の後になる)。
- **目的**: アプリ本体のバックエンドを置く場所と、その品質ゲートを CI 上に成立させる。要件書 NFR-019 が「バックエンドのテストランナー = pytest・PR ごとに CI で自動実行・全グリーンでないとマージ不可」を課しており、**その実行経路をコードより先に用意する**(旧システムは「pytest 形式テスト 74 件超が未実行」の状態だった)。
- **関係する要件**: 7.1 技術スタック(Python / FastAPI)/ NFR-019(テストランナー標準化)/ NFR-021(WSL2 完結・Phase 4 完了時の合格項目に「backend の pytest が成功し、backend が起動して疎通確認できること」)/ NFR-014(シークレットを環境変数で管理)。
- **後続の依存**: TSK-235(ドメイン計算の宣言モデル・生成器・検査基盤 — ADR-003 D-1/D-11)は `backend/` の存在が前提。
- **調査**: [research.md](research.md)(調査サブエージェント 3 本 + Web 調査を統合。以下の典拠は同メモが正)。

## 2. スコープ

### やること

1. **`backend/` プロジェクトの新設** — uv による版の完全固定(`backend/pyproject.toml` + `backend/uv.lock` + `backend/.python-version`)、`src/pitchlog/` + `tests/` のレイアウト、ruff / ty / pytest の設定。
2. **最小 FastAPI アプリ** — `app` と `GET /health`、および AnyIO による pytest。**PO 裁定(2026-08-19)**: どのスロットが作るかを定めた決定が正本に無く、4-1・4-3 が閉じている以上 4-2 か 4-6 の二択だったため、**4-2 で DB 非依存の起動基盤と `/health` を作る**。**本タスクは NFR-021 の受入判定も証跡化も行わない**。4-6 は引き続き **approved な `onboarding.md` による実依存の導入・DB 初期化・backend / frontend の起動と疎通確認・Phase 4 の受入**を担当する(設計書 13 章)。
3. **CI の backend ジョブ** — `backend-changes`(paths-filter)+ `backend` の二段構成を既存 `ci.yml` へ追加する。
4. **ハーネス設計書 5.1 の実装追随** — 非同期テストを AnyIO 方式で実装するため、テストツールの列挙を `pytest-asyncio` から `anyio` へ改める(**版は上げない** — 設計書 7.6-3 前段の「実装追随の節更新」)。

### やらないこと

| 除外するもの | 根拠 |
| --- | --- |
| **ドメイン計算コード(状況計算・集計・座標変換・成績公式)を 1 行でも置くこと** | 対象計算コードの追加は、宣言モデル正本・生成物・製品経路の呼び出し部・3 層検査を**同一の変更**として要求する(要件書 NFR-018 達成条件・ADR-003「この段階では対象計算のコードを追加しない」)。置いた時点で本タスクは TSK-235 に化ける |
| NFR-019 (a) 一致性 /(b) 越境 /(c) E2E /(d) 同期故障系のテスト実体 | 要件書 NFR-021 の測定方法が **Phase 4 完了時の対象外**と明文化。正解ベクタ未完成の間は (a) を合格判定してはならない |
| `backend/domain/manifest.json`・生成器・検査基盤・ゴールデンベクタ本体 | ADR-003 が後続タスクへ送るものとして明記(TSK-235〜239) |
| DB 接続・ドライバ(psycopg / asyncpg)・SQLAlchemy・Alembic | 設計書 5.1 が Alembic を「設計フェーズで最終確定」としており、未使用ドライバを骨格に入れる根拠がない。骨格では DB へ接続しない |
| ルート `pyproject.toml` への ruff / ty 導入 | F4(TSK-211)・台帳 H-13 の担当。本タスクで入れると別タスクのスコープを食う |
| `.claude/core-areas.json` の `areas[].paths` 充填 | 設計書 6.3 の落とし込み規則 ⑤ が敵対レビュー + 人間承認を要求しており、4-2 のマージ条件では通せない(TSK-228。4-3 も同じ理由で除外した) |
| `.claude/rules/backend.md` / `testing.md` の新設 | PO 裁定(2026-08-19)で対象外。4-1 も `frontend.md` を作らなかった |
| 設計書 CI ジョブ表への NFR-019 (b)(d) 行の追記(台帳 H-57) | PO 裁定(2026-08-19)で対象外 |
| `.env.example` が読めないガード不整合の是正・台帳への `H-*` 起票 | 是正は PO 裁定(2026-08-19)で対象外。**起票も行わない** — 台帳は本件を既に「候補 (1)」として記録しており、昇格条件は「`.env.example` を読めないことで作業が止まる事例が出た場合」。本タスクは同ファイルを読まず DB 設定も対象外のため**条件を満たさない**。実装中に実害で停止した場合のみ、3 節を先に更新してから追記する |
| 本番 DB への誤接続を機構的に止める仕組み | 接続実装そのものが本タスクの対象外のため、接続を入れるタスクへ送る(4-3 からの申し送りを引き継ぐ) |
| 旧システム由来の構造示唆(センチネル正規化層・所有権の必須引数化・冪等キー・リプレイ整合性検証・成績公式の定数モジュール) | いずれも対象計算またはデータ層の実装であり、上 2 行の理由で骨格に入れられない。**申し送りとして 4 節に記録するにとどめる** |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/development/dev-harness-design-2026-08-07.md` | 5.1 のテストツール行を anyio 方式へ実装追随。変更履歴表に 1 行追記(版は上げない) | PRレビュー |
| `docs/README.md` | 索引の設計書行の最終更新日を現行化 | PRレビュー |
| `docs/development/harness-evaluation.md` | 反映なし | — |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | 反映なし | — |
| `docs/adr/ADR-003-domain-calc-method.md` | 反映なし | — |
| `contracts/README.md` | 反映なし | — |

## 4. 実装方針

### 重さ分類の根拠(= 通常)

- **コア領域に触れない**。CLAUDE.md が列挙する 5 領域(同期プロトコル / 状況計算 / 記録権 / テナント分離 / データ移行)のいずれの実装も本タスクには含まれない(2 節「やらないこと」)。
- `.claude/core-areas.json` の `areas[].paths` は**全 5 領域とも空**のため、領域ガードはそもそも発火しない(台帳 H-12)。
- ただし **`.github/workflows/ci.yml` は `guard_paths`** に含まれるため `core-guard` が発火し、**PR 本文の「コア領域/検査経路の変更: 人間による逐行確認を実施した」チェックが必須**になる。これは**ガード設定ファイルの保護によるもので、重さ分類を「コア領域」へ引き上げる根拠にはならない**(前例: 4-1・4-3 とも同じ経路で `ci.yml` に触れ、通常分類で通している)。逐行確認は検出パスの和集合に対して PR 全体で 1 個のチェックで足りる。

### 版固定とレイアウト

- `backend/pyproject.toml`(宣言)+ `backend/uv.lock`(解決結果)+ `backend/.python-version`(3.12.3)。
- **`backend/.python-version` を置く理由**: `.python-version` は uv のプロジェクト境界を越えて探索されないため、**ルートの `3.12.3` は `backend/` から起動した uv には効かない**(research 6-2)。CI 側でも Python 版を明示する。
- `src/pitchlog/` レイアウトを配布可能にするため `[build-system]` を明示する(build system が無いと `uv sync` がプロジェクト自身を install せず、`from pitchlog...` が解決できない)。**build backend は setuptools を採る**(`requires = ["setuptools>=..."]` / `build-backend = "setuptools.build_meta"` / `[tool.setuptools.packages.find] where = ["src"]`)。理由: 追加の学習コストが無く、`src` レイアウトの検出が定型で済むため。
- 依存は**すべて確定版で lock** し、範囲指定を残さない(4-1 の前例: 依存 16 件すべて確定版)。**「確定版」の対象は `project.dependencies` と `[dependency-groups]`** であり、**`[build-system] requires` は `uv.lock` の対象外**のため下限指定でよい(ビルド時のみ使用)。
  - 本体: `fastapi[standard]`(`fastapi dev` による起動確認に ASGI サーバーが要るため)
  - dev: `pytest` / `pytest-cov`(CI が `pytest --cov`)/ `httpx` / `anyio` / `ruff` / `ty`
- **ty は beta・`0.0.x` で破壊的変更があり得ると公式が明記**しており、リリース間隔は数日単位。**`uv.lock` による固定が「今日緑なら明日も緑」の唯一の担保**になる(research 6-1)。

### 品質ツールの設定

- **ruff**: `line-length` / `target-version` を明示し、**`[tool.ruff.lint] select` に `D` を含めた上で** `[tool.ruff.lint.pydocstyle] convention = "google"` を設定する(設計書 5.1 の要求。`select` に `D` が無いと convention が空回りする可能性が research 6-4 で指摘されており、**実測して確かめる**)。docstring・コメントは日本語(AGENTS.md)。
- **ty**: 検査対象の Python 版を明示する(`requires-python` か `[tool.ty.environment]`。未指定だと既定ターゲットが 3.14 になる)。
- **pytest**: 非同期テストは **AnyIO 方式**(`pytest.mark.anyio` + `httpx` の `ASGITransport`)。FastAPI 公式の async テストが AnyIO を使うため(PO 裁定 2026-08-19)。**この選択に伴い設計書 5.1 を実装追随で更新する**(3 節)。

### CI ジョブ

- 既存の frontend と**同型の二段構成**にする: `backend-changes`(`dorny/paths-filter` を SHA pin した判定専用ジョブ)→ `backend`(`needs` + `if` で `workflow_dispatch` か filter 真のときだけ起動)。
- **paths filter は `backend/**`・`contracts/**`・`.github/workflows/ci.yml` 自身**を含める。`contracts/**` は 4-3 からの明示的な申し送り(設計書 10.1 との乖離を後から直す手戻りが 4-1 → 4-3 で実際に起きている)。`ci.yml` 自身は 4-1 の計画レビュー由来。
- **`backend` ジョブには `defaults.run.working-directory: backend` を置く**(frontend ジョブと同型)。リポジトリルートには**ハーネス用の別 `pyproject.toml`** があり、ルートで実行すると backend ではなくハーネス側を対象にしてしまうため。
- コマンドは設計書 10.1 が正: `uv sync` → `ruff check` + `ruff format --check` → `ty check` → `pytest --cov`。**同期は `uv python install` → `uv sync --locked --dev` に固定する**(既存 `harness` ジョブと同じ形。裸の `uv sync` だと古い lock を失敗として検出せず runner 内で更新し得る)。
- **追加する Action はすべてコミット SHA pin**(コメントで版を併記)。`astral-sh/setup-uv` は既存 CI と同じ pin(v9.0.0・uv 0.8.13)を再利用し、**`cache-dependency-glob` に `backend/pyproject.toml` と `backend/uv.lock` を指定する**(backend 側 lock の変更をキャッシュキーに含めるため)。
- **既存 6 ジョブ(`secrets` / `docs-lint` / `core-guard` / `harness` / `frontend-changes` / `frontend`)の定義を変更しない**。判定は **PR の base SHA の `ci.yml` との構造比較**で行い、**許容する差分は `backend-changes` と `backend` の 2 ジョブの追加のみ**(既存 6 ジョブのブロックとワークフロー共通設定〔`on` / `concurrency` / `permissions`〕は不変)。
- **これは「frontend が動かないこと」を意味しない**。`frontend-changes` の filter は `.github/workflows/ci.yml` を監視しているため、**本 PR でも frontend ジョブは従来どおり起動して成功する**のが期待挙動であり、定義の不変とは別の合格条件として確認する。

### 実装中の判断規律

- **`ty check` が緑にならない場合は、除外設定で回避せず作業を止めて原因を報告し、PO の裁定を仰ぐ**(PO 裁定 2026-08-19)。mypy への切替は設計書 5.1・論点E により ADR 起票を要するため、4-2 の中で勝手に方式を変えない。
- **`backend/pyproject.toml` を置いた瞬間に `/check` の backend 層 4 種が必須化され、`.py` 保存時の ruff 自動実行も始まる**。したがって**ステップ 1 の時点で 4 種すべてを緑にする**(テストが 0 件だと pytest が失敗するため、ステップ 1 にテストを 1 件含める)。
- 計画書に列挙したディレクトリ・依存が**実物より狭くなる**前例がある(4-1)。**計画外の変更には進まない**(AGENTS.md 絶対規則 5): **直接依存の追加・ソースディレクトリの追加・CI 設定の追加・正本の追加**が必要と判明した場合は、**実装を止めて計画書を更新し再承認を得てから続ける**。**worklog への記録だけで済ませてよいのは、`uv.lock` に現れる推移的依存の差分**(直接依存の解決結果)に限る。
- 依存取得にはネットワーク例外(`PITCHLOG_ALLOW_NET=1` + 理由)と PO への事前報告が要る。サンドボックスで uv のキャッシュが書けない場合は `UV_CACHE_DIR` を書き込み可能領域へ退避する(4-1 の `COREPACK_HOME` と同型の対処)。

### 後続タスクへの申し送り(本タスクでは実装しない)

旧システムで実際に壊れた箇所として調査で確認できたもの。**置き場を決める段階で参照する**(典拠は research 4 節):

- 所有権(テナント)ガードが全関数でオプショナル引数であり、省略すると全データにアクセスできた → リポジトリ層では**必須引数**にする。
- `プレイの番号` に UNIQUE 制約が無く、リトライで重複挿入が起き得た → 冪等キー(game_id + プレイの番号)の API 契約化。
- センチネル(`0` / `"0"` / 空文字 / NULL)の同居と、列名と実体の乖離 → 正規化層の単一入口。
- 遅延マイグレーションが読み書きのたびに DDL を実行していた → マイグレーションは起動時 / CLI に置き、リクエストパスに DDL を混ぜない。
- 集計が二重実装で崩れた(同一指標が 2 箇所)→ NFR-018 と ADR-003 の背景。ドメイン計算の置き場の正は ADR-003。

**本タスクのテストが検証しないこと(誤認防止)**:

- `ASGITransport` 経由の health テストは **lifespan(startup / shutdown)を実行しない**。将来 DB プール等を lifespan で開閉しても、このテストは起動・終了処理を検証しない。**lifespan を導入するタスクで start / stop を含むテストを追加する**。
- ステップ 2 の `fastapi dev` による手動確認は**開発者の目視確認**であり、**`/check` や NFR-021 の受入判定の代替にはならない**。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | `backend/` プロジェクトの新設: `pyproject.toml`(依存・`[build-system]` = setuptools・ruff・ty・pytest 設定)・`.python-version`・`uv.lock`・`src/pitchlog/__init__.py`・`tests/` と、パッケージ import を確かめるテスト 1 件 | `backend/` で `uv sync --locked` が成功する / `/check` の backend 層 4 種(`ruff format --check` / `ruff check` / `ty check` / `pytest`)がすべて緑 / **リポジトリルートで `uv run pytest tests/` が緑**(root の harness ジョブが backend 追加の影響を受けないことの実測) |
| 2 | 最小 FastAPI アプリ: `src/pitchlog/main.py` に `app` と `GET /health`、`tests/test_health.py`(AnyIO + `ASGITransport`)、`[tool.fastapi] entrypoint` の設定 | `uv run pytest` で health テストが緑(**ステータス `200` かつ本文が `{"status": "ok"}`**)/ `uv run fastapi dev` で起動し `/health` が**同じ値**を返すことを手動で確認し worklog へ記録 / `/check` の backend 層 4 種が緑 |
| 3 | CI への backend ジョブ追加: `backend-changes`(paths-filter: `backend/**`・`contracts/**`・`.github/workflows/ci.yml`)と `backend`(`working-directory: backend`・`uv python install` → `uv sync --locked --dev` → `ruff check` + `ruff format --check` → `ty check` → `pytest --cov`) | PR 上で `backend` ジョブが緑 / **base SHA の `ci.yml` との差分が `backend-changes` と `backend` の 2 ジョブ追加のみ**(既存 6 ジョブのブロックと `on` / `concurrency` / `permissions` が不変)/ **`frontend` ジョブが本 PR でも起動して成功する** / 追加した Action がすべて SHA pin されている |
| 4 | 正本の追随: 設計書 5.1 のテストツール行を anyio 方式へ更新 + 変更履歴 1 行、`docs/README.md` の設計書行の最終更新日を現行化 | `uv run python scripts/check_docs_status.py` が緑 / CI の `docs-lint` が緑 / 3 節の宣言と PR 内容が一致する |

**PR 完了ゲート**(ステップ外): 最新 HEAD で CI 全ジョブ緑 + PR 本文の人間逐行確認チェック済み。`core_guard.py` はローカル実行では PR イベント外のため skip される(合格条件に使わない)。

## 5. DoD(受け入れ基準)

- [ ] `backend/` に uv 管理のプロジェクトが存在し、`pyproject.toml` / `uv.lock` / `.python-version` で版が完全固定されている
- [ ] `/check` の backend 層 4 種(ruff format / ruff check / ty check / pytest)がすべて緑
- [ ] 最小 FastAPI アプリが起動し、`/health` が `200` と `{"status": "ok"}` を返す(手動確認を worklog へ記録)
- [ ] CI の `backend` ジョブが緑で、paths filter に `backend/**`・`contracts/**`・`ci.yml` 自身が含まれている
- [ ] `ci.yml` の差分が **`backend-changes` と `backend` の 2 ジョブ追加のみ**で、既存 6 ジョブのブロックとワークフロー共通設定が base SHA から不変
- [ ] `frontend` ジョブが本 PR でも従来どおり起動して成功する
- [ ] 3 節の正本反映が完了し、`check_docs_status.py` と `docs-lint` が緑
- [ ] PR 本文の人間逐行確認チェックが済んでいる

## 6. テスト計画

NFR-019 のテスト種別との対応:

| 種別 | 本タスクで足すもの |
| --- | --- |
| **単体** | `tests/test_health.py`(AnyIO + `ASGITransport` で `/health` を検証)、およびパッケージ import を確かめるテスト。**backend のテストは pytest のみ**(NFR-019 のランナー標準化) |
| 一致性(a) | 足さない。正解ベクタが未整備で、要件書が Phase 4 完了時の対象外と定めている |
| 越境(b) | 足さない。認可・テナント分離の実装が本タスクの対象外 |
| E2E(c) | 足さない。画面・API の実装が無い |
| 同期故障系(d) | 足さない。同期プロトコルの実装が無い |

- カバレッジは CI で `pytest --cov` として取得する(設計書 10.1)。**閾値による失敗条件は設けない**(骨格段階で意味のある下限を決められないため。導入は実装期のタスクへ送る)。
- テストは**アプリ起動・外部 DB 接続なしで完走する**こと(旧システムのテスト運用でも守られていた性質)。
- **本タスクのテストが検証しない範囲**(lifespan の start / stop、DB 接続、`fastapi dev` の手動確認が代替にならないこと)は 4 節の申し送りに記載した。
