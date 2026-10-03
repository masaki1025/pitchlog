---
feature: pg-fixture-volume-leak
type: research
date: 2026-09-30
---

# 調査メモ: 使い捨てクラスタへ `--rm` / `--volumes` を足すことの整合

## 問い

1. `disposable_postgres_cluster` の `docker run` に `--rm`、破棄の `docker rm --force` に `--volumes` を足すことが、過去の決定・正本・既存の検査と衝突しないか
2. `--rm` の自動削除と `rm --force` が競合して、直後の「コンテナ残存なし」assert が不安定にならないか

## 結論(要約)

- 衝突する決定・正本の記述・固定参照の検査はない。正本は起動引数も破棄手順も規定していないため、計画書 3 節の「反映なし」は正しい
- 既存の記録はすべて「利用後はコンテナごと破棄する」を前提にしており、失敗時にコンテナを残して調べる運用はない。今回の修正はこの前提を強める
- `--rm` と `rm --force --volumes` の競合は、実機で 12 回試して 0 回だった。`rm` は毎回同期で終わり(終了コード 0)、直後の `docker inspect` でコンテナもボリュームも消えていた。`docker stop` で止めた場合も、`--rm` によってコンテナと匿名ボリュームが回収された
- 追加する単体テストは独立ファイルに置き、`pytest.skip` と 40 桁・64 桁の hex 定数を使わない(既存の検査に掛かるため)

## 詳細と典拠

### 過去の決定(decision-tracer)

- 使い捨てクラスタの導入(TSK-270・2026-08-31)で決まったのは使う理由だけ。「ロールはクラスタ全域にあるので、ロール変異は使い捨てクラスタで行う」(`docs/development/dev-harness-design-2026-08-07.md:70`・`:865`、`docs/features/pg-authz-verification/plan.md:388`・`:484-485`)。`--rm` / `--volumes` / `--pull` への言及はない
- g3 設計は現行の方式を事実として書いているだけで、`--rm` を付けない理由は書いていない(`docs/features/pg-authz-verification-g3/design.md:212-215`)
- 導入コミットは `3b731bae`(2026-08-31「DB テスト基盤の配線と実接続フィクスチャ」)。関数の最終変更は `c00accf0`(2026-09-18、通常モジュールへの抽出)(`git log -S 'pitchlog-authz-'`)。匿名ボリュームの累積が始まった日(Notion TSK-465 の背景「8/31〜」)と一致する
- 事後調査のためにコンテナを残す運用はない。`docker logs` はリポジトリ内に 0 件。残ったコンテナは障害の残骸として消している(`docs/development/harness-evaluation.md:2712-2735`、`docs/worklog/2026-09-09-pg-authz-verification-g2.md:200-214`、`docs/worklog/2026-09-25-product-authz-apply.md:122`)
- 名前付きボリュームとの関係: 開発 DB は compose の名前付きボリューム `postgres_data` を使う(`docker-compose.yml:15`・`:25`)。`docker compose down -v` の禁止は `.claude/settings.json:58-59` の permissions deny にある(`dev-harness-design-2026-08-07.md:33`)。使い捨てクラスタは compose を経由しない `docker run` で起動するので、この deny とも名前付きボリュームとも経路が交わらない
- コア領域への登録: TSK-390(`docs/features/tenant-boundary-enforcement/plan.md:128`・PR #72)で `backend/tests/db_fixtures.py` を tenant-isolation の paths に exact path で登録した(`.claude/core-areas.json:364`・`tests/test_core_guard.py:127`)。本計画の重さ分類「コア領域」はこの登録と整合する

### 正本・検査との突合(spec-checker)

- 正本で使い捨てクラスタに触れているのは設計書の 2 箇所と data-model.md の状態記録だけで、ライフサイクルは規定していない(`dev-harness-design-2026-08-07.md:70`・`:865`、`docs/design/data-model.md:10`・`:2847`)。`docs/requirements`・`docs/adr` には記述がない
- NFR-019・NFR-021 は、コンテナやログを残すことを求めていない(`docs/requirements/requirements-pitchlog-2026-07-22.md:923-938`・`:963`)
- db_fixtures.py のハッシュ・行番号・引数文字列を記録している検査はない。ただし次の 2 つの検査に注意する
  - `tests/test_ci_wiring.py:1075-1077`・`:1193` は db_fixtures.py 全文に `pytest.skip` が無いことを検査している
  - `scripts/check_frozen_baselines.py:1888` は `backend/tests/` 配下の 40 桁・64 桁の hex を走査している
- 既存テスト `backend/tests/db/test_database_environment.py:96-104` は、コンテキストを抜けた直後に `docker inspect` を実行して、コンテナが残っていないことを assert している

### 実機確認(本調査で実施・2026-09-30・Docker 29.1.3)

- 競合の検証: `postgres:17.11-bookworm` を `--rm --detach` で起動し、2 秒後に `docker rm --force --volumes` を実行、直後に `docker inspect` とボリュームの inspect を行った。12 回とも `rm` は終了コード 0、コンテナもボリュームも消えていた
- 停止時の回収: `--rm` 付きのコンテナを `docker stop` で止めると、コンテナも匿名ボリュームも消えた
- 名前付きボリュームは `pitchlog_postgres_data` と `feature-onboarding-approval_postgres_data` の 2 個。匿名ボリュームは `com.docker.volume.anonymous` ラベルで区別できる

## 未解決・申し送り

- ハーネス評価台帳の候補(`harness-evaluation.md:2712-2735`)の復旧手順 `docker ps -aq --filter 'name=<prefix>' | xargs -r docker rm -f`(`:2722`)には `-v` が無い。この手順どおりに復旧すると匿名ボリュームが残る。台帳の編集は本計画のスコープ外なので、follow-up として扱う(PO 判断)
- SIGKILL で pytest が終わると、孤児コンテナは動き続ける(ボリュームは使用中のまま)。`--rm` で回収されるのは、そのコンテナが停止した時点(手動の `docker stop` や Docker デーモンの再起動)。台帳の対応案 (a)「開始時の残骸自動除去」は PO の採番待ちで、本計画では扱わない
