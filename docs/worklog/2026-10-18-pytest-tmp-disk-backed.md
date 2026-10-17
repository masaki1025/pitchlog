---
date: 2026-10-18
topic: pytest-tmp-disk-backed
branch: feature/pytest-tmp-disk-backed
---

# 作業ログ: 2026-10-18 pytest 一時ディレクトリの /tmp 満杯対策

## やったこと

- `/tmp` の実測: 3.9G / 7.7G(tmpfs)。`/tmp/pytest-of-ymdms` は 12 世代 1.2GB で、最大は `pytest-684` の 1.1GB(2026-10-17 04:37・`popen-gw0〜7` = xdist ワーカー世代 = ルート全件試験のもの)。稼働中の pytest は無し。
- pytest 9.1.1 のソースで保持規則を確定: 成功した実行だけが終了時に basetemp を削除・失敗/強制終了は残る・古い世代の削除は「ロックが 3 日より古い」条件(`_pytest/pathlib.py` の `LOCK_TIMEOUT` = 3 日)。→ 台帳の推論を確定させた(research.md)。
- 性能の実測: 256MiB 連続書込みは tmpfs 2.1GB/s 対 ディスク 1.3GB/s、空ファイル 2000 個で 0.037s 対 0.118s。
- 実装のフィージビリティ検証(実機): `scripts/pytest_tmp_bootstrap.py` + ルート/backend conftest 配線 + 単体テスト 21 件で、ruff / ty / pytest が両層で green。basetemp がディスク側(`~/.cache/pitchlog/pytest-tmp`)に作られ `/tmp` 側に新規が作られないことを実測。
- Notion TSK-565 を「進行中」へ遷移し、branch / worktree をコメントで記録。

## 決定

- セッション指示(非破壊的な作業は承認不要・マージ禁止・最終ゴールは PR)を事前承認として記録(frontmatter 承認: 済〔2026-10-18・山田正輝〕)。
- 移送層は **conftest の読込み時**(`TMPDIR` + `tempfile.tempdir`)。`--basetemp` 明示や環境側 export では全経路(直接・uv・ラッパー・子プロセス)を覆えないため。
- 掃除は**自前の基底に限定**し、日数上限 3 日(pytest のロック失効と同じ)。`PITCHLOG_PYTEST_TMP_KEEP_DAYS=0` で無効。他者の `TMPDIR` の中は触らない。
- backend は**単一実装を再利用**(sys.path 追加 + `# noqa: E402` + ty `extra-paths = [".."]` 1 行)。重複実装を作らない(NFR-018 の精神)。
- 敵対レビューは GLM 代役(`opencode/glm-5.3-flash-free`)で実施(セッション指示: Codex 役 = GLM)。
- 重さ分類は **コア領域**(計画レビュー 1 回目の指摘を反映): 機械定義上 `conftest.py` が guard_paths(検査経路)、`backend/pyproject.toml` が 5 領域の paths、`backend/tests/conftest.py` がテナント分離の glob に該当するため(ADR-001「迷う場合は含む側に倒す」)。

## レビュー記録

### 計画レビュー 1 回目(GLM 代役・計画書全文)— P0 0 / P1 1 / P2 4

| # | 重大度 | 指摘(要約) | 受理範囲 | 採否 | 反映 |
| --- | --- | --- | --- | --- | --- |
| 1 | P1 | 「コア領域でない・guard_paths 非該当」の事実誤認(`conftest.py` は guard_paths、`backend/tests/conftest.py` はテナント分離 glob、`backend/pyproject.toml` は 5 領域 paths → 機械的にコア領域/検査経路 PR) | 1(正本違反) | **採用**(自分で該当を検証) | 4 節の根拠を訂正、重さ分類をコア領域へ、0 節に判定と PR 処理(adversarial + 逐行確認の 2 項目)を明記 |
| 2 | P2 | prune の経過判定は 3 日超の稼働世代を削除しうる(pytest 自身と同閾値で劣化なし) | 範囲外 | 採用(改善) | ステップ 4 の AGENTS.md 明文化へ 1 文併記 |
| 3 | P2 | `TMPDIR`/`PYTEST_DEBUG_TEMPROOT` 指定時は移送も掃除も効かない旨の記録がない | 範囲外 | 採用(改善) | 同上 |
| 4 | P2 | backend の配線が自動テストで担保されない | 範囲外 | 採用(改善) | ステップ 3 に backend 配線テスト(`test_tmp_bootstrap_wiring.py` + fixture)を追加 |
| 5 | P2 | 承認をレビュー前に記録しており、採用指摘の反映時の承認の扱いが未記載 | 範囲外 | 採用(改善) | 0 節に「P0 採用時は承認再取得 / PO 裁定」を追記(1 回目は P0 0 件) |

### 計画レビュー 2 回目(GLM 代役・反映差分と影響節)— P0 0 / P1 1 / P2 3

| # | 重大度 | 指摘(要約) | 受理範囲 | 採否 | 反映 |
| --- | --- | --- | --- | --- | --- |
| 1 | P1 | 計画が約束する性能実測(1・6 節)が DoD に無く、未実施でも完了判定が成立しうる | 3(DoD と成果物の不対応) | **採用** | DoD に「性能影響とルート全件の試験時間の実測・worklog 記録」を追加 |
| 2 | P2 | 成果物 `backend/tests/test_tmp_bootstrap_wiring.py` が 3 節の成果物一覧から漏れ | 範囲外 | 採用(改善) | 3 節の正本体系外表へ追記 |
| 3 | P2 | 0 節で「受理範囲」の意味が 2 通りに使われている | 範囲外 | 採用(改善) | 「採否(受理範囲 3 種つき)」へ統一 |
| 4 | P2 | 4 節の「adversarial 相当」が PR 側の義務(`codex_run.py review adversarial`)と混同しうる | 範囲外 | 採用(改善) | 「本セッションは GLM 代役で実施し worklog と PR 本文の実施記録に明記」へ精密化 |

2 回目で P0 0 件のため、設計書 6.3 の上限規則どおり 3 回目は実施しない(収束)。

## 未決・次の一歩

- 計画レビュー 2 回目(反映差分と影響節)→ 起票コミット → ステップ実装コミット → `/check` → `/pr` → Notion 確認待ち。
- 旧 `/tmp` 残骸の掃除(稼働確認後・直近 3 世代は残す)。
- 台帳への対応記録と `docs/README.md` 索引の日付現行化(クローズ処理コミットで実施)。
