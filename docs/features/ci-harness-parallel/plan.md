---
feature: ci-harness-parallel
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: 通常            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3f293b75e6878195a980c5cf8ca32e4a
branch: feature/ci-harness-parallel
created: 2026-10-08
計画レビュー周回: 0        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: CI 短縮① — harness pytest の並列化(xdist)と巨大変異テストの分割、backend の計測

## 1. 背景・目的

- Notion: [TSK-501](https://app.notion.com/p/3f293b75e6878195a980c5cf8ca32e4a)。PO 指示(2026-10-07〜08): 「CI の長さを短縮したい。ローカルでできるテストはローカルで。並列も実施したい。ローカルは 8 上限で」
- 実測([research.md](research.md) §1〜§2): CI の壁時計 25〜28 分のうち **harness ジョブの pytest が 24〜27 分**。手元計測では 2,620 件・974 秒のうち上位 40 件が約 82% を占め、`tests/test_check_authz_catalog.py` の全数変異テスト 2 件(111.5 秒・98.8 秒 — プロセス内ループ)と `tests/test_census_baseline_check.py`(約 310 秒 — アンカーの実体化と現行センサスの全文走査をテストごとに再計算)が大半。pytest は 1 プロセス直列で 4 vCPU の 1 コアしか使っていない
- 関連要件: NFR-019 柱書(PR ごとに CI を実行し全グリーン必須)は維持する。レビュー・テストの網羅性を落とさずに所要時間だけを下げる。直接該当する FR はない
- 関連正本・決定: 設計書 10.1(CI ジョブ表 — harness/backend 行は実装追随の節更新)/ 10.2(必須チェック 10 コンテキスト — 不変)/ 台帳候補「検査が無関係な PR を巻き込んで赤にする」(所要時間とは別問題 — 後続タスク B の入力選択で扱う)
- 後続タスク B(PR #99 マージ後): 入力に基づくテスト選択 + develop/nightly 全件実行(10.1 の構造変更 → v1.20)。本タスクはその前段で、構造を変えずに時間を削る

## 2. スコープ

### やること

1. **pytest-xdist の導入**: ルート `pyproject.toml` の dev 依存に `pytest-xdist` を追加(`uv.lock` 更新)。`ci.yml` の harness ジョブの pytest に `-n auto`(ランナー = 4 vCPU → 4 ワーカー)。`tests/test_ci_wiring.py` の `HARNESS_PYTEST_COMMAND` を同期。`.claude/skills/check/SKILL.md` の harness pytest を **`-n 8`**(ローカル上限 — PO 決定 2026-10-08)に
2. **巨大 2 テストのパラメトライズ分割**(`tests/test_check_authz_catalog.py:4983` `test_recursive_derivers_cover_generated_container_sequences_and_siblings`・`:5141` `test_all_recursively_enumerated_oracle_leaves_reject_change_and_deletion`): 容器列 / (資産, 葉, 変異) を収集時に列挙して `parametrize` に展開し、xdist で分散できる粒度にする。**全数性は維持**する(展開件数が旧ループの試行数と一致することを別テストで固定し、各資産の葉数 > 0 の検査も残す)
3. **census 系の重複準備の共有**(`tests/test_census_baseline_check.py`): 宣言アンカーの実体化(`_declared_anchor_checker`・9 箇所)と現行センサス(`_checker_census`・15 箇所)のうち**入力が同一のもの**を module スコープの fixture またはメモ化で共有する。変異ごとの計算と、宣言と実装の対応監査(`_audit_declaration_implementation` の母集団)は変えない
4. **backend ジョブの計測**: `ci.yml` の backend pytest に `--durations=25`、ジョブ `env` に `COVERAGE_CORE: sysmon`(Python 3.12 + coverage 7.15.4)。`tests/test_ci_wiring.py` の該当固定があれば同期。PR の run で内訳を取り worklog に記録(次の打ち手の判断材料)
5. **文書の追随**(Claude): 設計書 10.1 の harness 行(`-n auto` 並列・ローカル 8)と backend 行(`--durations=25`・`COVERAGE_CORE=sysmon`)を節更新し変更履歴に 1 行(版は上げない — 7.6-3 前段)、`docs/README.md` を現行化

### やらないこと

- **ジョブ構成・必須チェック・path filter の変更**(10.1 の構造 — 後続タスク B。10.1 が fail-closed の理由で filter を付けない nfr021 / tenant-boundary には触れない)
- **backend テストの並列化・`--cov` の省略・DB テストの worker 分離**(内訳の計測後に判断 — 次タスク)
- **テストの網羅性の削減**(葉・変異・述語の母集団は不変)、**検査器(`scripts/*.py`)本体の変更**(テスト側の呼び方だけを変える)
- 手元環境固有の赤(research.md §6)の是正
- GitHub の larger runner(有料)の採用

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/development/dev-harness-design-2026-08-07.md` | 10.1 ジョブ表の harness 行に「pytest は `-n auto` で並列(ランナー 4 vCPU → 4 ワーカー)。ローカルは `/check` が `-n 8` 上限」、backend 行に「`--durations=25`・`COVERAGE_CORE=sysmon`」を追記。変更履歴 1 行(**版は上げない** — 実装追随の節更新・7.6-3 前段) | PR レビュー |
| `docs/README.md` | 設計書行の最終更新日を現行化 | PR レビュー |
| `docs/development/harness-evaluation.md` | `/pr` クローズ処理で判断(該当すれば候補へ: xdist 導入前後の実測・backend 内訳) | PR レビュー |
| 要件書・ADR-001〜004・github-setup.md・onboarding.md・`docs/ops/**` | **反映なし** | — |

**正本体系外だが同一 PR で更新するもの**: `.github/workflows/ci.yml`(**guard_paths** — 人間の逐行確認・実施記録行)・`tests/test_ci_wiring.py`・`tests/test_check_authz_catalog.py`・`tests/test_census_baseline_check.py`・`pyproject.toml`・`uv.lock`・`.claude/skills/check/SKILL.md`・`docs/features/ci-harness-parallel/{plan,research}.md`・`docs/worklog/2026-10-08-ci-harness-parallel.md`。

## 4. 実装方針

- **重さ分類 = 通常** の根拠: 変更対象は CI 設定・ハーネスのテスト・依存・スキル本文・設計書の節更新で、コア領域 5 領域の `paths` には該当しない(`ci.yml` は guard_paths だが ADR-001 の重さ分類上のコア領域ではない)。軽微でもない(CI の実行形態と 50 行超の差分)。機械的軽作業でもない(テストの分割・共有の設計判断を伴う)。**コードとテスト(ステップ 1〜4)は Codex へ委任**、文書(ステップ 5)は Claude が編集する(設計書 3 章)
- **ワーカー数**: CI = `-n auto`(ランナーの 4 vCPU に追随。`-n 4` 固定にしない — ランナー変更時に自動で追随)/ ローカル = `-n 8`(PO 決定。24 コア機でも子プロセスを多数起動するテストのため過負荷を避ける)。`pyproject.toml` の `addopts` には書かない(CI と手元で値が違うため、コマンド側で指定する)
- **分割の方針(ステップ 2)**: 収集時の列挙はリポジトリ資産を読む(`_repository_oracle_assets()`)。収集コストは数十 ms 級で許容。ID は `資産名-葉パス-変異` の形で可読にし、xdist の `load` 分配に任せる。「全数」の保証は、① パラメータ列の件数 = 旧ループの `attempts` と一致、② 各資産の葉数 > 0、を独立のテストで固定する(分割で母集団が黙って減る経路を閉じる)
- **共有の方針(ステップ 3)**: 共有してよいのは「同一入力(同一 revision のアンカー・同一 `backend/src` ツリー・同一検査器)」の計算だけ。変異テスト(述語の除去・入力の改変)は個別に計算する。宣言と実装の対応監査(`_audit_declaration_implementation`)が数える呼び出し母集団が変わらないことを、既存テストが red/green で示すこと(監査が検出する「結線が外れた」型 — 台帳の実例 — を再生産しない)
- **xdist の揺れへの備え**: ステップ 1 の合格条件で `-n 8` を 2 回連続 green とし、順序依存が出たファイルは当該ファイルだけ同一 worker にまとめる(`pytest-xdist` の `--dist loadfile` 相当・`xdist_group`)。原因不明のまま `-n 1` へ戻さない
- **計測の記録**: ステップ 1 の前後で手元(`-n 8`)の所要時間、PR の run で CI の harness/backend の所要時間と `--durations` 出力を worklog に記録する(DoD の「25 分 → 8 分以内」の判定材料)
- **ステップの担当**: ステップ 1〜4 = Codex(`/implement` でステップ単位)。ステップ 5 = Claude(文書)。Codex はコミットしない(Claude が 1 ステップ 1 コミット)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **xdist 導入**(Codex): ルート `pyproject.toml` dev 依存に `pytest-xdist` + `uv.lock` 更新 / `ci.yml` harness の pytest に `-n auto` / `tests/test_ci_wiring.py` の `HARNESS_PYTEST_COMMAND` 同期 / `.claude/skills/check/SKILL.md` の harness pytest を `-n 8` に | `uv run pytest -c pyproject.toml -n 8 tests/ --ignore=tests/domain/boot --ignore=tests/domain/mut --ignore=tests/test_plan_generation.py --ignore=tests/test_step_history_audit.py` が **2 回連続**で green(research.md §6 の手元固有の赤を除く)/ `uv run pytest tests/test_ci_wiring.py` green / `uv run ruff check .`・`uv run ty check` green / 所要時間を worklog に記録 |
| 2 | **巨大 2 テストのパラメトライズ分割**(Codex): `tests/test_check_authz_catalog.py:4983,5141` を収集時列挙の `parametrize` へ展開し、件数一致(= 旧 `attempts`)と葉数 > 0 を固定する独立テストを追加 | `uv run pytest tests/test_check_authz_catalog.py -n 8 --durations=10` で green・**最長単体テスト < 30 秒**・展開件数が旧ループの試行数と一致(テストで固定)/ `-n 1` でも green(順序非依存) |
| 3 | **census 系の重複準備の共有**(Codex): `tests/test_census_baseline_check.py` の同一入力のアンカー実体化・現行センサスを module スコープ fixture / メモ化で共有(変異計算と監査母集団は不変) | `uv run pytest tests/test_census_baseline_check.py -n 8 --durations=10` で green・ファイル合計時間が導入前(≈ 310 秒 / 直列)の **半分以下** / `uv run python tests/test_census_baseline_check.py`(CI の直接実行経路)が従来どおり `census-baseline: OK` / 監査 wiring のテストが不変で green |
| 4 | **backend ジョブの計測**(Codex): `ci.yml` backend の pytest に `--durations=25`・ジョブ `env` に `COVERAGE_CORE: sysmon` / `tests/test_ci_wiring.py` の該当固定があれば同期 | `uv run pytest tests/test_ci_wiring.py` green / YAML が `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"` で読める / (PR 作成後)backend ジョブの run に durations 出力が出る |
| 5 | **文書の追随**(Claude): 設計書 10.1 の harness/backend 行・変更履歴 1 行(版は上げない)・`docs/README.md`・worklog に実測(手元 `-n 8` の前後・CI の前後) | `uv run python scripts/check_docs_status.py` 0 違反 / `uv run python scripts/check_plan_docs_sync.py --plan docs/features/ci-harness-parallel/plan.md --base origin/develop` exit 0 |

## 5. DoD(受け入れ基準)

- [ ] harness ジョブの pytest が `-n auto` で並列実行され、CI の harness 所要時間が **8 分以内**(PR の run で実測・worklog に記録)。ローカル `/check` は `-n 8`
- [ ] `test_check_authz_catalog` の全数変異 2 テストがパラメトライズで分割され、網羅性(件数一致・葉数 > 0)をテストで固定したまま最長単体テストが 30 秒未満
- [ ] census 系テストの同一入力の準備が共有され、ファイル合計時間が半分以下。CI の直接実行経路と監査母集団は不変
- [ ] backend ジョブに `--durations=25` と `COVERAGE_CORE=sysmon` が入り、所要時間の内訳が worklog に記録されている
- [ ] 設計書 10.1 の harness/backend 行と `/check` スキルが追随し、docs-lint・plan/docs 突合が green。PR は guard_paths(`ci.yml`)の逐行確認を経る

## 6. テスト計画

- 本タスクの変更はテスト基盤そのものなので、検証 = ハーネステスト全件(`-n 8` と `-n 1` の両方で green — 順序非依存の確認)+ `tests/test_ci_wiring.py`(CI 配線の固定)+ 分割テストの件数一致テスト(新設)。NFR-019 の種別追加はない(製品コードの変更なし)
- 計測: 手元 `-n 8` の所要時間(導入前 974 秒・直列)/ CI の harness と backend の所要時間と `--durations` 出力(PR の run)を worklog に記録し、DoD の判定に使う
