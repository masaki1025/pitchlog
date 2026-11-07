# CI pytest 8 分割候補の報告

## 1. 対象

- リポジトリ: `/home/ymdms/projects/pitchlog`
- 固定 HEAD: `12cc636dfaaea2ef6ecba2985492d3acb3f1dc30`
- 作業 worktree: `/home/ymdms/projects/pitchlog-worktrees/feature-ci-pytest-throughput`
- ブランチ: `feature/ci-pytest-throughput`（固定 HEAD から作成）
- 製品コード・共有台帳・正式な凍結資産・受理 record・seal は変更していない。

## 2. 変更前の構成

### 2.1 CI の分割

| ジョブ | 変更前 |
| --- | --- |
| `harness-shard` | 4 シャード。収集順の剰余で割当。 |
| `harness` | `harness-static` と `harness-shard` を集約する必須チェック。`if: always()` と `toJSON(needs)` で success 以外を拒否。 |
| `backend-shard` | 4 シャード。各ジョブが独立した PostgreSQL service を持つ。`--cov` で計測。 |
| `backend` | `backend-changes` / `backend-static` / `backend-shard` を集約する必須チェック。同じく success 以外を拒否。 |

- カバレッジは各 backend シャードで `--cov` / `coverage report` / `coverage json` を実行し、
  `backend-coverage-<shard>` artifact を upload する構成を維持した。
- 集約ジョブ名 `harness` / `backend` と必須チェック名は変更していない。

### 2.2 実 CI ログ（変更前の実測）

主な基準は、成功した CI run `42095289008`（head `9ddcd5c332a4778ffd5a2979492cf17912a34350`、
2026-11-05）のジョブ所要と pytest `--durations=25` ログである。

| スイート | シャード所要（実測） | テスト数（4 シャード合計） |
| --- | --- | --- |
| backend | 25:17 / 23:25 / 30:26 / 35:08 | 13,160 件（3,290 + 3,290 + 3,288 + 3,288） |
| harness | 23:00 / 16:42 / 9:18 / 8:28 | 32,604 件（8,151 + 8,152 + 8,150 + 8,152） |

- 同じ run の workflow 全体は 19:35:09 から 20:22:27 までで **47 分 18 秒**。
- 参考: develop の成功 run `42103165175` は backend が 23:14 / 24:23 / 23:46 / 26:00、
  workflow 全体が 27 分 58 秒だった。テスト構成・キャッシュ・runner の差でばらつく。
- 固定 HEAD のローカル収集では backend **15,182 件**、harness **32,952 件**
  （本タスクの新規テスト追加前）。ログの run より backend が多いため、短縮見込みは
  件数比も加味した推定にしている。

### 2.3 8 分割を選んだ理由

- backend は 4 シャードの最大が 35:08 で、合計所要を 4 で割った値（約 28 分）より遅い。
- harness は 4 シャードの最大が 23:00 で、合計所要を 4 で割った値（約 14.5 分）より
  大幅に遅い。backend だけ 8 分割しても harness が 23 分のクリティカルパスに残るため、
  harness も 8 分割する場合にのみ backend の短縮が全体へ効く。
- 単純な収集順の 8 剰余ではなく、既存ログの `--durations=25` から重いテストを抽出し、
  重い順に最も空いているシャードへ置く LPT 割当にした。これにより、特定の重い
  テストが同じシャードへ固まる偏りを避ける。

## 3. 変更後の構成

### 3.1 シャードと割当

- `harness-shard` / `backend-shard` をそれぞれ **8 シャード**へ変更。
- `ci/pytest-shards.json` に `shards: 8` と実行時間重みを追加。
  - harness: CI run `42095289008` の `--durations=25` から **94 件**の重み。
  - backend: 同じログから **74 件**の重み。
  - 既定重みは harness `0.2` 秒、backend `0.4` 秒。重みに無い新規テストも
    この既定値で必ず 1 つのシャードへ割り当てる。
  - 乱数 UUID を含む node id は `<uuid>` に正規化して重みを引く。
- 割当計算は `scripts/pytest_shard_plan.py` の単一実装。重い順 → 正規化 node id 順 →
  収集順のタイブレーカーで決定的に決める。各シャードは全件集合から同じ割当を計算する。
- 新しいテストは重みに無くても既定重みで割り当てられ、`pytest_shards.py verify` の
  全件比較で取りこぼしを拒否する。重みキーが収集集合から消えた場合も拒否する。

### 3.2 検査の維持

- `harness` / `backend` の集約ジョブと必須チェック名は不変。
  `if: always()` と `needs` の `result != 'success'` 拒否も不変。
- backend はシャードごとに独立した PostgreSQL service を持ち、DB を共有しない。
- 各 backend シャードの `--cov` / `coverage report` / `coverage json` /
  `backend-coverage-<shard>` artifact を維持。
- テストの `--ignore`、`-m` 条件、`fetch-depth`、対象パスは変更していない。

### 3.3 被覆検査の実測（固定 HEAD・作業ツリー）

実行コマンド:

```text
uv run python scripts/pytest_shards.py verify --suite harness
cd backend && uv run python ../scripts/pytest_shards.py verify --suite backend --require-db
```

結果:

```text
harness: 32973 tests / 8 shards / sizes=[4109, 4157, 4120, 4118, 4122, 4122, 4112, 4113] / estimated_loads=[1678.3, 1678.2, 1678.2, 1678.1, 1678.2, 1678.3, 1678.3, 1678.2]
backend: 15182 tests / 8 shards / sizes=[1802, 1920, 1902, 1910, 1901, 1904, 1921, 1922] / estimated_loads=[988.5, 988.6, 988.5, 988.7, 988.3, 988.4, 988.4, 988.6]
```

- `sizes` は各シャードの収集件数、`estimated_loads` は設定重みによる推定負荷（秒）で、
  実測の壁時計ではない。
- harness の件数は、本タスクで追加した `tests/test_pytest_shards.py` の 21 件を含む。

## 4. 短縮見込み（推定）

実 CI の 8 分割 run は未取得（PR を作成しないため）。以下はすべて**推定**であり、
実測値ではない。

| 対象 | 変更前の実測 | 8 分割の推定 | 根拠 |
| --- | --- | --- | --- |
| backend の遅いシャード | 35:08 | **約 18〜22 分** | 4 シャード実測の最大 2,108 秒に、重み付き推定負荷の比（約 0.44）と固定 HEAD の件数比（15,182 / 13,160 ≒ 1.15）を掛け、セットアップ・集約を加算 |
| harness の遅いシャード | 23:00 | **約 10〜14 分** | 4 シャード実測の最大 1,380 秒に、重み付き推定負荷の比（約 0.42）を掛け、xdist・セットアップ・集約を加算 |
| workflow 全体 | 47:18 | **約 22〜26 分** | backend の推定 18〜22 分をクリティカルパスとし、集約・静的・frontend の並走分を加算 |

- 推定短縮は **約 21〜25 分（約 45〜53%）**。ただし runner の queue、キャッシュ、
  テスト内容の変化で変動する。
- backend だけ 8 分割して harness を 4 のままにすると、harness の 23 分が残るため
  全体の短縮は限定的になる。harness 8 分割はこの理由で採用候補に含めた。

## 5. 実行した検査

| 検査 | 結果 |
| --- | --- |
| `uv run ruff check .` | 成功 |
| `uv run ty check` | 成功 |
| `uv run pytest tests/test_pytest_shards.py -q` | 21 passed |
| `uv run pytest tests/test_ci_wiring.py -q -k 'not every_expectation_leaf_value_and_deletion_mutation_is_red'` | 115 passed |
| `uv run python scripts/pytest_shards.py verify --suite harness` | 成功（上記） |
| `cd backend && uv run python ../scripts/pytest_shards.py verify --suite backend --require-db` | 成功（上記） |
| `uv run python scripts/check_frozen_baselines.py --invariants-only` | OK（受理 hash の再導出は別） |

`uv run pytest tests/test_ci_wiring.py -q` は **115 passed / 1 failed**。失敗は
`test_every_expectation_leaf_value_and_deletion_mutation_is_red` で、理由は凍結済みの
`backend/tests/db/environment-expectations.json` がまだ
`--shard-count 4` と `pytest (shard .../4)` を期待しているためである。
この資産は本タスクでは変更していない。主担当の正式追随後に解消する。

なお、backend の `pytest_shards.py verify` はリポジトリルートの venv ではなく
`backend` ディレクトリで実行する必要がある（CI の `backend` 集約ジョブと同じ
`uv run` プロジェクトを使うため）。ルートから実行すると backend の依存が無く
収集に失敗する。

## 6. 変更パス

| パス | 内容 |
| --- | --- |
| `.github/workflows/ci.yml` | 4 → 8 シャード、`--shard-count 8`、表示・コメント更新 |
| `ci/pytest-shards.json` | 8 分割、重み 94 + 74 件、既定重み |
| `scripts/pytest_shard_plan.py` | 重み検証・LPT 割当・推定負荷の単一実装（新規） |
| `scripts/pytest_shard_plugin.py` | 設定読込・重み付き割当・分割数一致検証 |
| `scripts/pytest_shards.py` | 重みの検証、全件被覆、重み陳腐化拒否、推定負荷表示 |
| `tests/test_ci_wiring.py` | 8 分割の配線契約、カバレッジ維持の検査 |
| `tests/test_pytest_shards.py` | 割当・新規テスト・UUID・不正重みの単体検査（新規） |
| `docs/features/ci-pytest-throughput/plan.md` | 本タスクの計画 |
| `docs/features/ci-pytest-throughput/report.md` | 本報告 |

参考 hash（作業ツリー）:

```text
b6c8014b6b5e8a613ac98cdb2518b9f0306d221d49f3e7c6a13ef32b7e3fd5e6  .github/workflows/ci.yml
027c96582280f7a66dd2e09900d8bde6eeaeba21909b622ac725e57706245768  ci/pytest-shards.json
b410b6d95349a88804cff099446257a8a23bd373946379f53b54584b1c113c66  scripts/pytest_shard_plan.py
925975439465af9b7f416769b72d1069dd4bebba022b9398cc131f83c350baea  scripts/pytest_shard_plugin.py
c804c625929af7162488c0df425e7a30f7e1e0e836cf5881ddaf7cb3fb397df0  scripts/pytest_shards.py
cea6c8f2c46ff23915add56be12f76c58d3b68d76254ae333ad213c7eea8db30  tests/test_ci_wiring.py
2f3d59eed73c1481146be119ea943cace6430a70ad7929e43bac8fa6b15a813e  tests/test_pytest_shards.py
```

## 7. 主担当が必要な正式追随

以下は本タスクでは変更していない。CI 変更に伴う正式資産の再導出を主担当が直列で行う。

1. `backend/tests/db/environment-expectations.json`
   - `test_execution.single_command.expected` の `--shard-count 4` を `8` へ。
   - provenance の `.github/workflows/ci.yml` の
     `- name: pytest (shard ${{ matrix.shard }}/4)` を `/8` へ。
   - 同資産の `source_revision` と受理 record を更新。
2. `tests/test_ci_wiring.py`
   - `contracts/tenant_boundary/frozen-inputs.json` の `external_files` に含まれる。
   - 変更前 hash `8d428e6a683d367535fded5256b4d62e4c6e769e9f1903ce72b8e7f90769b7a3`
     → 変更後 `cea6c8f2c46ff23915add56be12f76c58d3b68d76254ae333ad213c7eea8db30`。
   - 凍結 projection・受理 record・比較 corpus digest の再導出が必要。
3. `.github/workflows/ci.yml`
   - CI ファイルを対象とする受理 record / history snapshot / corpus digest の再導出。
4. `docs/development/dev-harness-design-2026-08-07.md`
   - 10.1 の「`harness-shard` 4 分割」「`backend-shard` 4 分割」と変更履歴を 8 分割・
     重み付き割当へ追随（7.6-3 前段）。
5. `docs/development/github-setup.md`
   - 「実体は `harness`/`backend` が 4 分割の集約」を 8 分割へ追随。
6. `contracts/tenant_boundary/base-allowlist.json` / `history-snapshots` 等のうち、
   CI ファイル・`tests/test_ci_wiring.py`・`backend/tests/db/environment-expectations.json`
   を宣言・hash 対象にしている受理 record と snapshot。

## 8. 未検証点

- **8 分割の実 CI 所要時間は未実測**。本ブランチの push では CI は発火しない
  （`ci.yml` の発火は develop/main への push と pull_request、workflow_dispatch）。
  PR を作成していないため、短縮時間はすべて推定である。
- GitHub Actions の同時実行枠に対する 8 + 8 シャードの queue 影響は未測定。
- 重みは head `9ddcd5c` の CI ログ由来で、固定 HEAD の全テスト時間を再計測したものでは
  ない。固定 HEAD で増えたテストは既定重み、将来の重いテスト追加時は重みの更新が望ましい
  （更新しなくても被覆は保たれる）。
- harness は各シャード内で xdist（`-n auto`）を使うため、8 シャード化の wall-clock 効果は
  重み付き推定負荷の比だけでは正確に表せない。実 CI での再計測が必要。
- backend / harness の全テスト実行そのものは、本タスクでは時間と環境の都合で
  再実行していない。全件被覆は収集 ID で検証したが、実行結果の green は CI で確認する。
- カバレッジは従来どおりシャード単位の計測・artifact で、8 シャード分を 1 本へ
  結合する処理は追加していない（変更前の構成を維持）。
- 凍結資産の受理 hash は再導出していないため、`tests/test_ci_wiring.py` の
  期待値検査 1 件は意図的に未解消である。
