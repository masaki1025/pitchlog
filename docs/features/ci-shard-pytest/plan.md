---
feature: ci-shard-pytest
status: active
承認: 済（ユーザー指示 2026-10-31・CI短縮の5条件を反映）
重さ分類: 通常
branch: feature/ci-shard-pytest
created: 2026-10-31
計画レビュー周回: 0
確定ゲート周回: 0
---

# CI の pytest 分割と本文検査の分離

## 目的

backend / harness の壁時計を、検査範囲を変えずに短縮する。現行の実測は
backend 59分31秒(pytest 58分32秒・単一プロセス)、harness 43分20秒(pytest 40分35秒)で、
クリティカルパスはほぼ pytest のみである。

## 制約(ユーザー指示)

1. 必須チェック名は維持する。`backend` / `harness` は各シャードの集約ジョブとして残し、
   `always()` で起動して失敗・キャンセル・予期しない skip を拒否する。`core-guard` も維持する。
2. 本文編集はワークフロー単位で分離する。重いワークフローから `edited` を外し、
   本文検査を別ワークフローへ移す。concurrency も分離し、本文編集で進行中の検査を
   キャンセルしない。
3. 取りこぼしは収集したテスト ID で確認する。全体の収集結果と各シャードの和集合が一致し、
   重複・欠落・意図しない 0 件が無いことを検査する。DB 必須テストの 0 件拒否とも整合させる。
4. カバレッジと履歴取得の削減は初回に混ぜない。カバレッジは全シャードで計測して結合し、
   `fetch-depth` は変更しない。
5. 短縮見込みは実測前の目標値として扱い、時間計測と実 CI で確定する。

## 実装

- `ci/pytest-shards.json`: スイートごとの対象・除外・分割数。
- `scripts/pytest_shard_plugin.py`: 収集順の剰余で決定的に分割する pytest プラグイン。
- `scripts/pytest_shards.py`: 全体収集と各シャード収集を突き合わせる被覆検査。
- `.github/workflows/ci.yml`: `harness-static` / `harness-shard`(4分割) / `harness`(集約)、
  `backend-static` / `backend-shard`(4分割) / `backend`(集約・カバレッジ結合・段階A起動)。
- `.github/workflows/pr-body.yml`: `core-guard` を移設し、`edited` をここだけで受ける。
- `backend/tests/db/conftest.py`: 収集専用実行に限り 0 件実行の判定を外す
  (通常実行の判定は不変)。

## 未了(このPRで続ける)

- `tests/test_ci_wiring.py` の構造契約を新配線へ追随させる(ジョブ順・fetch-depth 集合・
  既知コマンド許可・契約葉の変異回数・段階A/配布イメージの対象ジョブ)。
- `.github/workflows/ci.yml` と `tests/test_ci_wiring.py` は tenant 契約の外部凍結入力のため、
  v2 受理record の再導出と凍結比較 corpus の digest 追随が必要。
- 実 CI の時間計測と目標値の確定。
