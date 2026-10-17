---
feature: pytest-tmp-disk-backed
status: active
承認: 済（2026-10-18・山田正輝）
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3fc93b75e68781d58e50f829900225b1
branch: feature/pytest-tmp-disk-backed
created: 2026-10-18
計画レビュー周回: 2
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: pytest 一時ディレクトリの /tmp 満杯対策(ディスク側への移送と掃除上限の明文化)

## 0. 承認と境界

本計画はセッション内の人間指示(2026-10-18)による事前承認で進める: **非破壊的な作業は個別承認を要さず自走してよい・マージだけはしない・最終ゴールは PR を出した状態**。したがって frontmatter の承認は「済」とし、承認者を山田正輝として記録する(経緯は worklog に残す)。計画の敵対レビュー(1 回目 = 全文 → 反映)は本来 Codex 役が担うところ、本セッションの指示により GLM 代役(opencode/glm-5.3-flash-free)で実施し、採否(受理範囲 3 種つき)を worklog に残す。

**重さ分類は「コア領域」**: 機械定義(`.claude/core-areas.json`)上、`conftest.py` は guard_paths(検査経路)の完全一致、`backend/pyproject.toml` は 5 領域すべての `paths`、`backend/tests/conftest.py` はテナント分離の `backend/*conftest.py`(fnmatch は `/` を越える)に該当する。意味範囲はテスト実行環境の変更に留まる(テナント契約・状況計算・検査内容は変えない)が、ADR-001 の「迷う場合は含む側に倒す」に従い**コア領域**として扱う。

**レビュー反映の扱い**: 指摘の採否は worklog に受理範囲(正本違反 / ステップが緑にできない / DoD と成果物の不対応)つきで記録する。P0 を採用した場合は、反映コミットの後に承認の再取得(または PO 裁定)を経てから先へ進む(1 回目は P0 0 件)。

対象は開発ハーネス(ルート)と backend の**テスト実行環境**に限る。製品コード(`backend/src`・`frontend`)と CI ワークフローは変更しない。

## 1. 背景・目的

- 共有 `/tmp`(tmpfs 7.7G)が pytest の一時ディレクトリで**3 回満杯**になり、harness の全件試験が出力を失った(2026-10-05・10-09・10-10。台帳 `docs/development/harness-evaluation.md` の候補「長時間 DB テストの強制終了が teardown を飛ばし…」と 2026-10-10 の変更履歴行)。
- 再発機構は本タスクの調査で確定した: pytest は**成功した実行だけ**が終了時に basetemp を消し、失敗・強制終了した実行は残る。古い世代の掃除は「ロックが 3 日より古い」ことを条件にするため、**直近 3 日分の失敗・中断世代は本数に関わらず消えない**(典拠と実測: [research.md](research.md))。
- 目的: **既定で**一時ディレクトリをディスク側(空き 870GB)へ移送し、**掃除の手順と上限**を明文化して再発を止める。移送の性能影響は併せて実測する(タスクの性能調査を兼ねる)。
- Notion: [TSK-565 pytest の一時ディレクトリが /tmp を満杯にする — ディスク側への移送と掃除手順・上限の明文化](https://app.notion.com/p/3fc93b75e68781d58e50f829900225b1)
- 対象 FR/NFR: **なし**(開発ハーネス運用の改善で要件書の対象外)。関連: NFR-019(実装 PR はテストを伴う)、NFR-018 の精神(同一ロジックの重複実装を作らない)。

## 2. スコープ

### やること

- 単一実装 `scripts/pytest_tmp_bootstrap.py` の新設: 解決順(`PITCHLOG_PYTEST_TMPDIR` > `PYTEST_DEBUG_TEMPROOT` > `TMPDIR` > `$XDG_CACHE_HOME/pitchlog/pytest-tmp`)、書込み不能時の退避(最後はシステム既定)、自前基底に限る日数上限付き掃除(既定 3 日)。
- ルート `conftest.py` への配線(読込み時に `TMPDIR` と `tempfile.tempdir` を向け替え + 古い世代の掃除)。
- backend `tests/conftest.py` への配線(同一実装を再利用。`backend/pyproject.toml` に ty の探索パス 1 行)。
- 単体テストの追加と実測(サブプロセスの実 pytest で basetemp がディスク側に作られること、backend の配線検証、`/tmp` に新規が作られないこと)。
- AGENTS.md のコマンド節へ既定・上書き・掃除を明文化。
- 台帳へ対応記録 + `docs/README.md` 索引の台帳行の日付現行化(クローズ処理)。
- 旧 `/tmp/pytest-of-ymdms` の残骸掃除(**自分分のみ・稼働確認後・直近 3 世代は残す**)。

### やらないこと

- pytest の保持則(失敗時に残す・ロック失効 3 日)自体の変更。
- CI ワークフローと frontend の変更。
- 他担当・他 worktree の `/tmp` 物への接触(例: `/tmp/pitchlog-c1-root-tests-20261016b`)。
- `scripts/product_rls_real_schema/runner.py` の `/tmp` 直書き(別件として申し送りのみ)。

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/development/harness-evaluation.md` | 候補「長時間 DB テストの強制終了が teardown を飛ばし…」へ対応の追記(移送 + 掃除上限)と変更履歴表 1 行(版は上げない — 7.6-3 前段) | PR レビュー(実装追随の記録追記) |
| `docs/README.md` | 索引のハーネス運用評価台帳行の最終更新日を現行化 | PR レビュー(索引の現行化) |

上記以外の正本(要件書・設計書・ADR・運用文書)は**反映なし**。

正本体系外(同一 PR で更新 — 3 節の突合対象外):

| 対象 | 変更内容 |
| --- | --- |
| `AGENTS.md` | コマンド節へ一時ディレクトリの既定・上書き・掃除を追記 |
| `docs/features/pytest-tmp-disk-backed/` | 計画書・調査メモ(本 feature) |
| `docs/worklog/2026-10-18-pytest-tmp-disk-backed.md` | 作業ログ |
| `conftest.py` / `backend/tests/conftest.py` / `backend/pyproject.toml` / `scripts/pytest_tmp_bootstrap.py` / `tests/test_pytest_tmp_bootstrap.py` / `backend/tests/test_tmp_bootstrap_wiring.py` | 実装(移送ヘルパー・配線・テスト) |

## 4. 実装方針

重さ分類の根拠(**コア領域** — 計画レビュー 1 回目の事実誤認指摘を反映):

- 機械定義(`.claude/core-areas.json`)に該当する: `conftest.py` は **guard_paths(検査経路)** の完全一致、`backend/pyproject.toml` は **5 領域すべての `paths`**、`backend/tests/conftest.py` は**テナント分離の `backend/*conftest.py` glob**(fnmatch は `/` を越える)に一致。
- 意味範囲はテスト実行環境の変更に留まる(テナント契約・状況計算・検査内容は変えない)が、ADR-001 の「**迷う場合は含む側に倒す**」に従い **コア領域** とする。
- 帰結: 計画・PR のレビューは adversarial(コア領域版)で行う。本セッションでは Codex ラッパー(`.claude/scripts/codex_run.py`)が使えないため GLM 代役で実施し、その旨を worklog と PR 本文の実施記録に明記する。`/pr` ではコア領域/検査経路の 2 項目(adversarial レビュー + 人間逐行確認)を有効化する(設計書 6.3)。fast path の対象外。

設計の要点(比較・実測の詳細は [research.md](research.md)):

- **移送層は conftest の読込み時**。basetemp は `tempfile.gettempdir()` の遅延評価で決まるため、その前に `TMPDIR` と `tempfile.tempdir` の両方を向け替える(子プロセスへも伝播させる)。`--basetemp` の明示や環境側の export は全経路を覆えない。
- **上書きは環境変数 1 つ**(`PITCHLOG_PYTEST_TMPDIR`)。利用者の `TMPDIR` と pytest 公式の `PYTEST_DEBUG_TEMPROOT` は尊重する。
- **書込み不能時は警告して退避**し、全滅時はシステム既定へ戻す(試験を止めない)。
- **掃除(prune)は自前の基底に限定**。世代の経過はディレクトリと `.lock` の mtime の新しい方で見積もり、日数上限(既定 3 日 — pytest のロック失効と同じ)超を削除する。`PITCHLOG_PYTEST_TMP_KEEP_DAYS=0` で無効化。
- **単一実装**(NFR-018 の精神): backend はルートの実装を sys.path 追加経由で import(`# noqa: E402` 1 行と ty 探索パスで検査系に適合 — 実機検証済み)。

### 実装ステップ(コミット単位 — 設計書 6.1 — 1 ステップ = 1 コミット)

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 移送ヘルパー `scripts/pytest_tmp_bootstrap.py` と単体テスト(純ロジック分)を新設する | root の `uv run ruff check .` / `uv run ty check` / `uv run pytest tests/test_pytest_tmp_bootstrap.py` が green |
| 2 | ルート `conftest.py` を配線し、配線を実測するサブプロセステストを追加する | 上記に加えて子プロセス実測テストが green。実 pytest 実行で basetemp がディスク側に作られ、`/tmp` に新規が作られない |
| 3 | backend `tests/conftest.py` を配線(移送結果を公開する fixture を含む)し、backend の配線を検証するテストと `backend/pyproject.toml` への ty 探索パス 1 行を追加する | backend で `uv run ruff format --check .` / `uv run ruff check .` / `uv run ty check` / `uv run pytest tests/test_tmp_bootstrap_wiring.py tests/test_wording_scan.py` が green。backend の basetemp もディスク側 |
| 4 | AGENTS.md のコマンド節へ既定・上書き・掃除を追記する(効かない条件 — `TMPDIR` 等の指定時 — と 3 日超の実行が掃除対象になりうる旨の 1 文を含む) | root の全検査(`uv run ruff check .` / `uv run ty check` / `uv run pytest tests/`)が green(総合検証) |

## 5. DoD(Notion TSK-565 と同期)

- [ ] pytest 実行で `/tmp` に新規 basetemp が作られないことを実測で示す(ルート・backend の両方)
- [ ] 追加テスト(NFR-019)と harness の品質ゲート(ruff / ty / pytest)green
- [ ] 正本への影響を計画書 3 節で宣言し、`/pr` で突合する
- [ ] 掃除の手順と上限が AGENTS.md と台帳に明文化されている
- [ ] 移送の性能影響(連続書込み・小ファイル作成)とルート全件の試験時間を実測し、worklog に記録する
- [ ] 旧 `/tmp` 残骸(自分分・稼働なし)を掃除し、実施内容を worklog に記録する

## 6. テスト計画

- **単体**(NFR-019): `tests/test_pytest_tmp_bootstrap.py` — 解決順・`~` 展開・退避(書込み不能 / 全滅)・`TMPDIR` と `tempfile.tempdir` の適用・prune の条件(古い世代のみ削除 / ロックが新しい世代は保持 / 自前以外の基底は非対象 / 0 で無効 / 壊れた `pytest-current` の除去)・不正値の警告。
- **故障系**: 候補が書込み不能な場合の退避と、全滅時にシステム既定のまま試験が動くこと(例外を投げない)。
- **越境(層間)**: backend が単一実装を import して配線されることを `backend/tests/test_tmp_bootstrap_wiring.py` で担保する(移送先が選ばれない環境では skip)。
- **E2E(実測)**: サブプロセスの実 pytest で basetemp が移送先に作られること(ルート)。ルート全件・backend 実行で `/tmp` 側に新規世代が作られないこと(実測値を worklog に記録)。
- **性能**: 移送の副作用(連続書込み・小ファイル作成)を実測し、全件試験時間は `/check` で確認する。
