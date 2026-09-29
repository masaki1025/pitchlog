---
feature: pg-fixture-volume-leak
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域         # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3ea93b75e687816d981ef92628c2e6b8
branch: fix/pg-fixture-volume-leak
created: 2026-09-30
計画レビュー周回: 0        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: pytest の使い捨て Postgres が Docker 匿名ボリュームを回収しない問題の修正

## 1. 背景・目的

- Notion: [TSK-465](https://app.notion.com/p/3ea93b75e687816d981ef92628c2e6b8)
- 2026-09-29、WSL2 の `ext4.vhdx` が 661GB まで膨張し Windows の C: が満杯になった。内訳は Docker の匿名ボリューム 14,140 個(≈670GB)で、生成元は `backend/tests/db_fixtures.py` の `disposable_postgres_cluster`
- postgres イメージは `VOLUME /var/lib/postgresql/data` を宣言しているため、`docker run` のたびに匿名ボリュームが生成される。フィクスチャの破棄が `docker rm --force <name>` だけで `--volumes` を付けていないため、コンテナ削除後もボリュームが残る
- 暫定対処(2026-09-29 の prune)後も、テスト実行のたびに再び増えている(2026-09-30 着手時点で dangling 85 個)
- 要件との対応: 製品要件の変更なし。NFR-019(テスト必須)のテスト基盤の保守

## 2. スコープ

### やること

- `disposable_postgres_cluster` の破棄で匿名ボリュームも削除する(`docker rm --force --volumes`)
- `docker run` に `--rm` を付ける(pytest が破棄処理を実行できずに終わった場合も、コンテナが停止した時点でコンテナと匿名ボリュームが自動回収される)
- 上記の引数を検査する単体テストを追加する
- 本ブランチのマージ後、既存の dangling 匿名ボリュームを `docker volume prune`(匿名のみ — Docker 23 以降の既定)で削除する(運用作業・コード変更なし)

### やらないこと

- 起動済みの孤児コンテナを自動で掃除する仕組み(別 worktree の並行テストのコンテナを誤って消す危険があるため入れない)
- 使い捨てクラスタの起動方法そのもの(イメージ・initdb 引数・ポート公開・待機処理)の変更
- 各 worktree への個別適用(develop へのマージ後、各ブランチが develop を取り込んだ時点で横展開される)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| 反映なし | テスト用フィクスチャの資源回収のみで、要件・設計・ADR・開発規約・運用手順に記述の変更はない | — |

## 4. 実装方針

**重さ分類の根拠**: 変更対象の `backend/tests/db_fixtures.py` は `.claude/core-areas.json` でコア領域「テナント分離」の paths に登録されている。変更内容は Docker 資源の回収だけで認可判定には触れないが、ADR-001 の優先順位(コア領域 > 軽微 — 迷う場合は含む側に倒す)に従い **コア領域** とする。したがって fast path(非コア領域が条件)は使えない。

変更点(`backend/tests/db_fixtures.py` の `disposable_postgres_cluster` 内の 2 箇所のみ):

1. `_run_docker("run", "--detach", ...)` の引数に `"--rm"` を加える
2. `finally` の `_run_docker("rm", "--force", container_name, check=False)` を `_run_docker("rm", "--force", "--volumes", container_name, check=False)` にする

`--rm` と `rm --force --volumes` を併用しても、実機では削除が競合せず、`rm` は同期で完了する(12 回試して 12 回とも。直後の `docker inspect` でコンテナもボリュームも消えていた)。既存の「コンテナ残存なし」の assert(`backend/tests/db/test_database_environment.py:96-104`)とも整合する。仮に競合しても `check=False` なので失敗にはならない。認可・テナント分離の試験で使うクラスタの中身(ロール・DB・DSN)は変わらない。過去の決定・正本・既存の検査との整合は [research.md](research.md) を参照。

単体テストは独立ファイル `backend/tests/test_disposable_cluster_cleanup.py` に置き、`pytest.skip` と 40 桁・64 桁の hex 定数を使わない。`tests/test_ci_wiring.py:1193`(db_fixtures.py 全文に対する `pytest.skip` の禁止)と `scripts/check_frozen_baselines.py:1888`(hex の走査)に掛からないようにするため(research.md)。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | `disposable_postgres_cluster` の `docker run` に `--rm`、破棄の `docker rm` に `--volumes` を加え、`_run_docker` を差し替えて両引数を検査する単体テストを追加する | 追加テストが green(backend/ で `uv run pytest` の該当ケース)・`uv run ruff check`・`uv run ty check` が通る |

## 5. DoD(受け入れ基準)

- [ ] フィクスチャを 1 回回した前後で `docker volume ls -q -f dangling=true | wc -l` が増えないことを実測で示した(並行セッションの影響を除くため、自分のコンテナ名に紐づくボリューム ID を追跡して判定する)
- [ ] 異常終了でもボリュームが残らないことを確認した(SIGINT = 破棄処理が走る / SIGKILL = 孤児コンテナが残り、停止した時点で `--rm` によりコンテナとボリュームが回収される)
- [ ] 名前付きボリューム(`pitchlog_postgres_data` ほか)に影響しないことを確認した
- [ ] 同種の使い捨てコンテナを起動する箇所が他に無いか grep で確認した(着手時の調査で `docker run` はこの 1 箇所のみ)
- [ ] マージ後に既存の dangling 匿名ボリュームを削除し、名前付きボリュームが残っていることを確認した

## 6. テスト計画

- 単体: `_run_docker` を monkeypatch で記録器に差し替え、`docker port` の出力と `_wait_for_postgres` をスタブして factory を 1 回通し、`run` の引数に `--rm`、`rm` の引数に `--force` と `--volumes` が含まれることを検査する(Docker 不要)
- 実機(DoD の実測・手動): 実 Docker で `disposable_postgres_cluster` を使う既存テスト(`backend/tests/db/test_database_environment.py` の残存検査を含む)を実行し、コンテナの匿名ボリューム ID が実行後に存在しないことを確認する。SIGINT / SIGKILL の 2 通りも同様に確認する
