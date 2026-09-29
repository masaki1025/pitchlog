---
feature: pg-fixture-volume-leak
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域         # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3ea93b75e687816d981ef92628c2e6b8
branch: fix/pg-fixture-volume-leak
created: 2026-09-30
計画レビュー周回: 3        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
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
- `docker run` を `try` の内側へ移し、起動の途中で失敗・中断した場合(CLI の 90 秒タイムアウト・起動中の SIGINT)も、`finally` がコンテナ名を指定して削除する
- 上記を検査する単体テストを追加する

### やらないこと

- 起動済みの孤児コンテナを自動で掃除する仕組み(別 worktree の並行テストのコンテナを誤って消す危険があるため入れない)
- 使い捨てクラスタの起動方法そのもの(イメージ・initdb 引数・ポート公開・待機処理)の変更
- 各 worktree への個別適用(develop へのマージ後、各ブランチが develop を取り込んだ時点で横展開される)
- 既存の dangling 匿名ボリュームの削除(コード変更ではない運用作業のため、DoD から外して 7 節のマージ後フォローアップで扱う)

### 保証外の条件(DoD の対象外)

- **SIGKILL**(`kill -9`・OOM killer): Python の `finally` は走らない。孤児コンテナは動き続け、ボリュームは使用中のまま残る。コンテナが停止した時点(手動の `docker stop`・Docker デーモンの再起動)で、`--rm` によりコンテナと匿名ボリュームが回収される。回復手順は、`docker ps --filter name=pitchlog-authz-` で孤児を特定し、**実行中の別セッションのテストでないことを確かめたうえで** `docker rm --force --volumes <名前>` を実行する
- **Docker 側の部分失敗**(デーモンがコンテナを作成したが、CLI へ応答を返せなかった場合など): `finally` の名前指定の削除で回収を試みる。削除も失敗した場合は `check=False` のまま握りつぶされるので、上記の回復手順で扱う

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| 反映なし | テスト用フィクスチャの資源回収のみで、要件・設計・ADR・開発規約・運用手順に記述の変更はない | — |

## 4. 実装方針

**重さ分類の根拠**: 変更対象の `backend/tests/db_fixtures.py` は `.claude/core-areas.json` でコア領域「テナント分離」の paths に登録されている。変更内容は Docker 資源の回収だけで認可判定には触れないが、ADR-001 の優先順位(コア領域 > 軽微 — 迷う場合は含む側に倒す)に従い **コア領域** とする。したがって fast path(非コア領域が条件)は使えない。

変更点(`backend/tests/db_fixtures.py` の `disposable_postgres_cluster` の factory 内だけ):

1. `_run_docker("run", "--detach", ...)` の引数に `"--rm"` を加える(イメージ名より前)
2. `finally` の `_run_docker("rm", "--force", container_name, check=False)` を `_run_docker("rm", "--force", "--volumes", container_name, check=False)` にする
3. `docker run` の呼び出しを `try` の内側へ移す。起動に失敗してコンテナが存在しない場合、`finally` の削除は `check=False` で無害に失敗する

**不採用とした案(計画レビュー 2 周目 P1)**: 「`docker run` が同名の既存コンテナとの衝突で失敗した場合、`finally` が他セッションのコンテナを名前で削除してしまう」ため、コンテナ ID かラベルで所有を確かめてから削除する案。コンテナ名 `pitchlog-authz-<token>` の `<token>` は呼び出しごとに `secrets.token_hex(8)`(64 ビットの乱数)で生成される(`db_fixtures.py:633-634`)ので、既存コンテナとの名前衝突は実際上起きない。所有確認を足す複雑さに見合わないと判断した(3 周目で妥当と確認)

**取り下げた変更(計画レビュー 2 周目 P2 → 3 周目 P2 2 件)**: 2 周目で「`finally` の削除が 90 秒でタイムアウトすると、その例外が元の例外を覆う」との指摘を受け、削除の `TimeoutExpired` を捕捉して警告にする変更を一度入れた。3 周目で、その変更が別の問題を生むと指摘された(`-W error` では警告が例外化して元の例外を覆う / 正常終了時の削除失敗が成功扱いになる)。Python は `finally` 内で送出された例外に元の例外を `__context__` として連結して表示するので、元の例外の情報は失われない。また、この挙動は修正前から同じで、本タスク(匿名ボリュームの回収)の範囲外である。以上から変更を取り下げ、削除のタイムアウトは現行どおり例外として送出する

`--rm` と `rm --force --volumes` を併用しても、実機では削除が競合せず、`rm` は同期で完了する(12 回試して 12 回とも。直後の `docker inspect` でコンテナもボリュームも消えていた)。既存の「コンテナ残存なし」の assert(`backend/tests/db/test_database_environment.py:96-104`)とも整合する。仮に競合しても `check=False` なので失敗にはならない。認可・テナント分離の試験で使うクラスタの中身(ロール・DB・DSN)は変わらない。過去の決定・正本・既存の検査との整合は [research.md](research.md) を参照。

単体テストは独立ファイル `backend/tests/test_disposable_cluster_cleanup.py` に置く。テスト内で必須ロール DSN の環境変数(`_dsn_names()` が返す名前)にダミー値を設定し、実 Docker・実 Postgres・実環境変数に依存させない。`pytest.skip` と 40 桁・64 桁の hex 定数を使わない。`tests/test_ci_wiring.py:1193`(db_fixtures.py 全文に対する `pytest.skip` の禁止)と `scripts/check_frozen_baselines.py:1888`(hex の走査)に掛からないようにするため(research.md)。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | `disposable_postgres_cluster` の `docker run` に `--rm` を加えて `try` の内側へ移し、破棄の `docker rm` に `--volumes` を加える。`_run_docker` を差し替えて、正常系と失敗系(`run` 失敗・`port` 失敗・待機タイムアウト)を検査する単体テストを追加する | 追加テストが green(backend/ で `uv run pytest` の該当ケース)・`uv run ruff check`・`uv run ty check` が通る |

## 5. DoD(受け入れ基準)

- [ ] フィクスチャを 1 回回した前後で `docker volume ls -q -f dangling=true | wc -l` が増えないことを実測で示した(並行セッションの影響を除くため、自分のコンテナ名に紐づくボリューム ID を追跡して判定する)
- [ ] 異常終了でもボリュームが残らないことを確認した(SIGINT = 破棄処理が走る。SIGKILL は 2 節の保証外条件のとおりで、孤児コンテナを停止すると `--rm` によりコンテナとボリュームが回収されることを実測する)
- [ ] 名前付きボリューム(`pitchlog_postgres_data` ほか)に影響しないことを確認した
- [ ] 同種の使い捨てコンテナを起動する箇所が他に無いか grep で確認した(着手時の調査で `docker run` はこの 1 箇所のみ)

## 6. テスト計画

- 単体(Docker 不要): `_run_docker` を monkeypatch で記録器に差し替え、`_wait_for_postgres` をスタブし、ロール DSN の環境変数にダミー値を入れる。次の 4 通りで factory を通す
  - 記録器は `port` に `127.0.0.1:54321` の形の stdout を返し、それ以外の呼び出しは空の成功を返す
  - 正常系: `run` の引数に `--rm` があり、イメージ名より前にある。`rm` が `--force --volumes <run と同じコンテナ名>` で 1 回呼ばれる
  - `run` が例外を送出: 同じコンテナ名で `rm --force --volumes` が呼ばれ、元の例外が送出される
  - `port` が例外を送出: 同上
  - 待機がタイムアウト(`_wait_for_postgres` が例外を送出): 同上
- 実機(DoD の実測・手動): 実 Docker で `disposable_postgres_cluster` を使う既存テスト(`backend/tests/db/test_database_environment.py` の残存検査を含む)を実行し、コンテナの匿名ボリューム ID が実行後に存在しないことを確認する。SIGINT / SIGKILL の 2 通りも同様に確認する

## 7. マージ後フォローアップ(運用作業 — DoD 外)

- 既存の dangling 匿名ボリュームを削除する。`docker volume prune`(Docker 23 以降の既定では匿名ボリュームだけが対象で、使用中のボリュームと名前付きボリュームは対象外)は**ホスト全体に作用し、本フィクスチャ以外の用途の未使用匿名ボリュームも消す**。実行前に対象の件数と一覧、名前付きボリュームの一覧、稼働中のコンテナを提示し、**人間(PO)の了承を得てから** Claude が実行する。実行後、名前付きボリュームが残っていることを確認する
- 他の worktree のブランチは、develop を取り込むまで旧フィクスチャのままでボリュームを出し続ける。削除後も増える分は、各ブランチが develop を取り込んだ時点で止まる
