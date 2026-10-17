---
feature: pytest-tmp-disk-backed
type: research
date: 2026-10-18
---

# 調査メモ: pytest 一時ディレクトリの /tmp 満杯(再発機構の確定と移送先の検証)

## 問い

- 共有 `/tmp`(tmpfs 7.7G)が pytest の一時ディレクトリで繰り返し満杯になる**再発機構**は何か(pytest の保持規則のどこが効いていないのか)。
- どの層を直せば「既定」でディスク側へ移り、掃除の上限を保証できるか。
- 移送による性能影響はどの程度か(タスクの性能調査を兼ねる)。

## 結論(要約)

- **再発機構(ソースと実測で確定)**: pytest の basetemp は `tempfile.gettempdir()` 由来で既定は `/tmp` 配下。**成功した実行だけ**が終了時に basetemp を丸ごと消し、失敗・強制終了した実行は残る。古い世代の掃除は「ロックが 3 日より古いこと」を条件とするため、**直近 3 日分の失敗・中断世代は本数に関わらず消えない**(keep=3 の本数制限は事実上効かない)。→ 全タブの実行量に比例して数日で GB 単位が蓄積(実測: 12 世代 1.2GB、最大 1 世代 1.1GB)。台帳の「並行実行が新しい番号を取り合うので古い分が消えない」という推論は、この 3 日ロック条件と成功時全削除で説明できる。
- **移送層の決定**: basetemp は `tempfile.gettempdir()` の遅延評価で決まるので、**conftest の読込み時**に `TMPDIR` と `tempfile.tempdir` を向け替えるのが、全経路(直接実行・`uv run`・ラッパー経由・子プロセス)に既定で効く唯一の層。
- **掃除の上限**: pytest 自身のロック失効と同じ **3 日**を既定に、自前の基底だけを実行時に掃除(prune)。上書きは `PITCHLOG_PYTEST_TMPDIR`、掃除は `PITCHLOG_PYTEST_TMP_KEEP_DAYS=0` で無効化。書込み不能時は警告して退避し、最後はシステム既定(試験を止めない)。
- **性能**: tmpfs 2.1GB/s 対 ディスク 1.3GB/s(256MiB 連続書込み)、空ファイル 2000 個で 0.037s 対 0.118s。ディスク側の空きは 870GB。全件試験の実行時間は移送後を `/check` で実測し worklog に記録する。
- **backend への適用**: 単一実装(root の `scripts/pytest_tmp_bootstrap.py`)を sys.path 追加で再利用し、ruff(`# noqa: E402`)・ty(`[tool.ty.environment] extra-paths = [".."]`)とも green(実機確認済み)。

## 詳細と典拠

### 1. 現状の実測(2026-10-18)

- `/tmp` 全体: 3.9G / 7.7G(tmpfs)。`df -h`。ホーム側(`/`)は 1007G 中 870G 空き。
- `/tmp/pytest-of-ymdms`: **12 世代 1.2GB**。最大は `pytest-684` の **1.1GB**(2026-10-17 04:37。中身は `popen-gw0〜7` = pytest-xdist のワーカー世代。ルート全件試験のもの)。
- 他担当の大型残骸(本タスクでは触らない): `/tmp/pitchlog-c1-root-tests-20261016b` 1.5GB ほか。
- 稼働中の pytest プロセスは無し(掃除の安全性確認)。

### 2. pytest の保持規則(pytest 9.1.1 のソース確認による)

- **basetemp の決定**: `_pytest/tmpdir.py:getbasetemp` — `PYTEST_DEBUG_TEMPROOT` または `tempfile.gettempdir()` を使い、`pytest-of-<user>/pytest-<N>` を作る。`tempfile.gettempdir()` は初回だけ環境(`TMPDIR`)から決めてプロセス内にキャッシュする遅延評価。実測でも `TMPDIR` の指定が basetemp へ反映されることを確認(probe)。
- **成功時の削除**: `_pytest/tmpdir.py:pytest_sessionfinish` — 終了ステータス 0・保持方針 `failed`・ユーザー指定なしの場合、basetemp を丸ごと削除する。
- **失敗時の保持**: 同 — 失敗(非 0)なら残す。**強制終了(kill)では `pytest_sessionfinish` 自体が走らない**ため残る。
- **テスト単位**: `_pytest/tmpdir.py:tmp_path` — 合格したテストの分はテスト終了時に削除(best effort)。失敗したテストの分は残る。
- **古い世代の掃除**: `_pytest/pathlib.py:cleanup_numbered_dir` / `ensure_deletable` / `make_numbered_dir_with_cleanup` — 新規世代の作成時に keep=3 を超える古い世代を消すが、`ensure_deletable` は「ロックの mtime が*新規世代の mtime − LOCK_TIMEOUT* より古い」場合のみ削除可。`LOCK_TIMEOUT = 60 * 60 * 24 * 3`(3 日)。
- **帰結**: 「/tmp を使う既定」と「失敗・中断世代が 3 日窓で本数無制限に積み上がる」の 2 点が再発機構。台帳(2026-10-05・10-09・10-10 に 3 回の満杯)の記録と整合する。

### 3. 移送層の候補比較

| 案 | 内容 | 評価 |
| --- | --- | --- |
| (a) 各コマンドへ `--basetemp` を明示 | 台帳の対応案 (e) | 全経路(直接・uv・ラッパー・子プロセス)の書き漏らしで破れる。人間の設定依存 |
| (b) シェル等で `TMPDIR` を export | 環境側で対応 | セッション限り・端末依存で、CI とローカルに差が出る |
| (c) conftest 読込み時に `TMPDIR` と `tempfile.tempdir` を向け替え + 実行時 prune | **採用** | pytest の遅延評価より前に確実に効く唯一の層。root/backend で単一実装を再利用できる |

### 4. 採用設計の実測検証(2026-10-18、worktree 内)

- 解決順: `PITCHLOG_PYTEST_TMPDIR` > `PYTEST_DEBUG_TEMPROOT` > `TMPDIR` > `$XDG_CACHE_HOME/pitchlog/pytest-tmp`(未設定時 `~/.cache/...`)。空値は飛ばし、`~` は自前で展開(テスト差し替え可能)。書込み不能なら警告して次へ、全滅時はシステム既定のまま(試験は動く)。
- ルート: `uv run pytest tests/test_pytest_tmp_bootstrap.py` で basetemp が `~/.cache/pitchlog/pytest-tmp/pytest-of-ymdms/pytest-0`(xdist ワーカー `popen-gw0〜3` も同配下)に作られることを実測。`/tmp` 側に新規なし。
- backend: `uv run pytest tests/test_wording_scan.py` でも同様に実測(`pytest-0` がディスク側、`/tmp` 側に新規なし)。
- 検査: root = `uv run ruff check .` / `uv run ty check` green。backend = `uv run ruff check tests/conftest.py` / `uv run ty check` green。backend からの `scripts/` import は conftest の sys.path 追加 + `# noqa: E402`、ty は `[tool.ty.environment] extra-paths = [".."]`(いずれも実機で確認)。

### 5. 性能(移送の副作用)

- 連続書込み 256MiB(`dd ... conv=fsync`): tmpfs **2.1GB/s** → ディスク **1.3GB/s**。
- 空ファイル 2000 個の作成: tmpfs **0.037s** → ディスク **0.118s**。
- 参照: 台帳にルート全件 30 分の記録。移送後の実測は `/check` 実行で取得し worklog に追記する。

## 未解決・申し送り

- `scripts/product_rls_real_schema/runner.py:593` が `tempfile.mkdtemp(prefix=..., dir="/tmp")` と `/tmp` 直書きで残る(本件の対象外 — 別タスク候補として申し送り)。
- 旧 `/tmp/pytest-of-ymdms` の残骸は移送後の自動掃除の対象ではない。本タスクで「稼働なしを確認し、直近 3 世代を残して削除」を実施し、再発時の手順を AGENTS.md に明文化する。
- pytest の保持則(失敗世代を残す・3 日ロック)自体は変更しない — 「消えない上限」は prune で担保する。
