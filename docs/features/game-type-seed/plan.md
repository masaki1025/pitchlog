---
feature: game-type-seed
status: active
承認: 済
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3ef93b75e6878158b61ddd4e75fe5c49
branch: feature/game-type-seed
created: 2026-10-13
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: 試合区分のシステム固定語彙を投入する (TSK-479)

## 1. 背景・目的

[TSK-479](https://app.notion.com/p/3ef93b75e6878158b61ddd4e75fe5c49) は U-G1 の前提である。要件書の 4.0-3 と FR-001 は試合区分を公式戦・準公式戦・オープン戦・紅白戦・その他の 5 件と定めるが、現行 DB の `system_vocabularies` には `game_type` が 0 行である。`games.game_type_key` は必須かつ外部キーなので、これを投入しない限り試合作成 API は動作しない。

`develop` には migration 0029 の `category` 制約が着地済みである。TSK-541・538・470・238・391 の作業範囲を変更しない。U-G1 の API は U-S1 (TSK-391) と規則の読み取り経路が揃ってから別計画で扱う。

## 2. スコープ

### やること

- 既存の `contracts/seeds/roster-status.json` と同じ二段構成で、試合区分 5 件のシード資産と seed 専用 migration を追加する。
- 5 キーを既存の `active`・`other`・`ob` と全数照合する。キーの決定は試合区分だけに効く識別子の選択とし、一般命名規則にはしない。
- migration の DML 許可を新系列として狭く宣言し、必要な受理履歴を整える。
- 実 DB で投入値・再適用・巻き戻し・衝突時の原子性を検証する。
- 製品 RLS 適用済み DB でも `pitchlog_owner` で 0030 を適用できるよう、システム語彙の固定5行に限る所有者向け認可ポリシーと適用順を追加する。詳細は [RLS 対策案](rls-resolution-proposal.md) を正とする。

### やらないこと

- 試合作成 API、規則セット、スタメン、試合の同期、旧 Kind の移行対応は扱わない。
- 進行中タスクのファイルと `docs/legacy/` は変更しない。正本の変更は本計画で宣言した `data-model.md` 3-2・12-4 の規範追加と、10-3 の実装追随に限る。

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| 要件書・ADR | 変更なし | — |
| `docs/design/data-model.md` 10-3 | ステップ4で実装現況と変更履歴を追随 | PR レビュー |
| `contracts/seeds/game-type.json` | 5 件の実装シード資産を新設 | PR レビュー |
| `contracts/migrations/seed-allowlist.json` | 新しい seed revision の限定許可と受理履歴を追加 | 設計書 7.7 の凍結基準ゲート |
| `contracts/authz/product/` | `pitchlog_owner` 専用の SELECT・INSERT・DELETE ポリシーを固定5行に限って追加し、`probe-product-map.json` の製品側のみの原子要素へ3件を登録 | コア領域レビュー＋人間承認 |
| `backend/src/pitchlog/authz/{product_provisioning,product_catalog}.py`・`scripts/check_authz_catalog.py` と関連テスト | owner専用3ポリシーの生成名・適用・取り外し・exact-set 検査を限定拡張。表アクセスの既存テストはアプリ用1表1ポリシーの範囲を保持し、owner専用3件を別集合で照合 | コア領域レビュー＋人間承認。既存アプリ用プロファイルの検査を緩めない |
| `docs/design/data-model.md` 3-2・12-4 | ステップ3の認可資産変更前に所有者向け固定語彙ポリシーと既存 RLS DB への適用順を確定 | 7.3 の確定ゲート（版繰り上げ・敵対レビュー＋人間承認） |
| `docs/README.md` | `data-model.md` v0.8 の確定状態を索引へ反映 | 正本の索引追随 |
| `contracts/db/schema-manifest.json`・`contracts/authz/shared-preconditions.json` | 10-3 節の実装追随による `data-model.md` 全文digestの機械的な取り直し（各1値のみ） | 派生資産の PR レビュー。両資産に `baseline_control` はなく、7.7 の受理記録の追加は不要 |

## 4. 実装方針

`migration 0030` は 0029 の後に置き、シード資産の値と固定した `op.bulk_insert()` の 5 行を検査で一致させる。既存の `0027_seed_roster_status.py` は変更しない。downgrade は本 revision が投入した 5 キーに限る。システム固定語彙の通常の更新禁止と、既存行を無言で上書きしない性質を保つ。製品 RLS 下の方式比較・ポリシーの範囲・適用順・安全検証は [RLS 対策案](rls-resolution-proposal.md) を参照する。

コア領域の「データ移行」に当たる。凍結基準を変えるため、設計書 7.7 の差分・受理手順を満たすまで PR をマージ対象にしない。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 試合区分 5 キーを決め、シード資産・migration 0030 と資産一致テストを追加する | 5 件の表示名が要件書 4.0-3 と一致し、在籍 3 キーとの集合積が空。migration 0029 → 0030 の投入が実 DB で成功する |
| 2 | DML 検査の新系列の限定許可と凍結基準の受理履歴を追加する | `test_migration_hygiene.py` の正例と負例、凍結履歴検査が green。別表・余分な行・追加 DML は拒否される |
| 3 | 着手前に `data-model.md` 3-2・12-4 の版繰り上げと 7.3 確定ゲートを通し、DB の往復・衝突・参照可能性と製品 RLS 下の適用経路を仕上げる | 正本の人間承認後に認可資産を変更する。更新済み認可 DDL → `pitchlog_owner` による 0030、upgrade/downgrade、既存キー衝突の原子性、`games` の FK 正例と異区分負例、アプリと所有者の書き込み制限、製品カタログ exact-set が green。owner による `disabled=true` INSERT を拒否 |
| 4 | 10-3 の実装追随と PR 準備を行う | 変更範囲と計画が一致し、backend の lint・型検査・pytest とルートの関連テストが green。7.7 の人間確認を PR に明示する |

## 5. DoD(受け入れ基準)

- [x] 試合区分 5 行がシード資産と DB で完全一致し、在籍区分 3 キーと衝突しない。
- [x] 0029 適用済みの DB で 0030 の投入と限定された downgrade が成立する。
- [x] migration の DML 許可はこの 5 行だけで、履歴を含めて検査できる。
- [x] 実 DB の参照正例・異区分負例・衝突時の原子性を検証する。
- [x] RLS と FORCE RLS を有効に保った製品 DB で `pitchlog_owner` による 0030 が成功し、アプリ用ロールと所有者の許可外書き込みが拒否される。
- [x] 進行中 5 タスクの作業ファイルと U-G1 の API に差分がない。

## 6. テスト計画

`backend/tests/db/` にシード資産と実 DB の完全一致、upgrade/downgrade、衝突時のロールバック、`games.game_type_key` の FK 正負例を追加する。製品 RLS 適用済みの専用 DB でも owner による migration と ACL・ポリシー・FK・拒否系を検証する。製品認可のカタログ exact-set と再適用のテストを再実行する。`backend/tests/test_migration_hygiene.py` で新系列の許可範囲を検査する。対象の pytest、`uv run ruff check .`、`uv run ty check` を実行する。

## 7. 着手条件と未決事項

本計画は 2026-10-13 の利用者の「了解」を承認およびステップ 1 の着手指示として受けた。5 キーの具体的な文字列はステップ 1 で決め、在籍キーとの衝突と既存契約の参照を確かめる。凍結基準の受理記録には設計書 7.7 の人間確認が必要である。

ステップ3で、製品 RLS 適用後の `pitchlog_owner` に INSERT ポリシーがなく 0030 が失敗することを実 DB で確認した。2026-10-13 の利用者指示に従い延期せず解決する。上記の射程変更は従前の承認に含まれないため、計画のコア領域レビューと人間承認、および `data-model.md` 3-2・12-4 の版繰り上げ・確定ゲートを**ステップ3の認可資産変更前に**通過する。10-3 の現況追随はステップ4で行う。それまで認可資産と migration を変更しない。

本射程変更の計画は独立 Codex セッションによる2回の敵対レビュー（第2回は可決 P0=0 P1=0 P2=0）を経て、2026-10-13 に利用者が「承認」と明示した。正本改訂の承認とは別である。
