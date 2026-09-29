---
date: 2026-09-30
topic: TSK-465 pytest の使い捨て Postgres が Docker 匿名ボリュームを回収しない問題の修正
branch: fix/pg-fixture-volume-leak
---

# 作業ログ: 2026-09-30 TSK-465 pytest の使い捨て Postgres が Docker 匿名ボリュームを回収しない問題の修正

## やったこと

### /task-start

- Notion `TSK-465`(既存・優先度 高)に着手。ブランチ `fix/pg-fixture-volume-leak`・worktree `../pitchlog-worktrees/fix-pg-fixture-volume-leak`(origin/develop = `ec02a0d2` 起点)
- 着手時点の dangling ボリューム 85 個(うち匿名 84 個)。2026-09-29 の prune 後も増え続けている。別セッションのテストが稼働中(`pitchlog-authz-*` コンテナ 1 個)
- 使い捨てコンテナの `docker run` はリポジトリ内で `backend/tests/db_fixtures.py` の 1 箇所のみ(grep)
- `backend/tests/db_fixtures.py` は `.claude/core-areas.json` でコア領域「テナント分離」に登録されているため、重さ分類はコア領域(fast path 不可)

### /investigate

- decision-tracer・spec-checker を並列に実行した。衝突する決定・正本・固定参照の検査はない。調査メモは `docs/features/pg-fixture-volume-leak/research.md`
- `--rm` と `rm --force --volumes` の競合を実機で 12 回試した。競合は 0 回だった

### /plan(敵対レビュー 3 周)

- 1 周目: P1 2 件・P2 2 件、全件採用(`docker run` を try の内側へ / prune をマージ後の人間了承つき運用へ / DoD からマージ後作業を外す / テストのスタブ範囲)
- 2 周目: P1 1 件を不採用(同名コンテナの衝突は token が 64 ビットの乱数のため起きない — 3 周目で妥当と確認)。P2 2 件を採用
- 3 周目: P0・P1 は 0 件。2 周目に入れた削除タイムアウトの警告化から P2 が 2 件出たため、その変更を取り下げた
- 承認: 2026-09-30・山田正輝

### /implement(ステップ 1/1 — `7476142c`)

- Codex(ADR-001 のコア領域の行)に委任した。変更は `backend/tests/db_fixtures.py`(`--rm` の追加・`run` を try の内側へ移動・`rm --force --volumes`)と、新規の `backend/tests/test_disposable_cluster_cleanup.py`(4 ケース)
- 検証: 新規テスト 4 件、ruff format/check、ty、ハーネスの `tests/test_ci_wiring.py`(58 件)が green。`check_frozen_baselines.py --ci` はローカルでは `GITHUB_EVENT_NAME` 未設定で実行不可のため、CI に任せる
- 実機での DoD の実測(docker events でボリューム作成を追跡):
  - 正常系: `tests/db/test_database_environment.py`(3 件 green)。作成されたボリューム 1 個が回収された。dangling の数は 493 → 493 で増えなかった
  - SIGINT: finally が走り、ボリュームが回収された
  - SIGKILL: 孤児コンテナが稼働したまま残り、ボリュームも残る(保証外条件のとおり)。`docker stop` で停止すると、コンテナとボリュームの両方が消えた
  - 名前付きボリューム `pitchlog_postgres_data`・`feature-onboarding-approval_postgres_data` は残っている
- 着手時 85 個だった dangling は、実装中に他セッションのテストで 493 個まで増えた(旧フィクスチャのまま動くブランチから出ている)

## 決定

- 既存の dangling 匿名ボリュームの削除は、マージ後に人間の了承を得てから行う(計画書 7 節)

## 未決・次の一歩

- /pr(コア領域: 敵対レビュー + 人間の逐行確認)→ マージ → 既存の匿名ボリュームの prune(了承を得てから)
- follow-up の候補: ハーネス評価台帳の復旧手順(`harness-evaluation.md:2722`)に `-v` が無い
