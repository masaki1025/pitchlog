# TSK-479 ステップ3: 製品 RLS 下の seed 投入方式（承認済み）

本案は実装担当の Codex が起案した。Claude CLI は 2026-10-13 の試行時に週次利用上限を返した。利用者の同日の明示的な代替許可に基づき、実装担当とは別の Codex セッションでコア領域の計画レビューを実施した。この例外はレビュアの指定だけに適用し、計画・正本改訂・認可資産変更への人間承認を兼ねない。

## 原因と守る条件

Alembic は `PITCHLOG_MIGRATION_DATABASE_URL` の direct connection で実行する。製品では接続主体が `pitchlog_owner` であり、`system_vocabularies` も同ロールの所有物である。製品認可適用後は同表の `relrowsecurity` と `relforcerowsecurity` がともに真で、ポリシーは `pitchlog_app` の SELECT のみである。所有者にも FORCE RLS が掛かり、0030 の INSERT は default-deny で失敗する。RLS を無効化せず、アプリ用ロールの表 ACL を SELECT のまま維持する。

## 方式比較

| 方式 | 利点 | 採否と理由 |
| --- | --- | --- |
| **A. `pitchlog_owner` に固定5行だけの製品ポリシーを付ける** | 既存の migration 接続と DDL/DML 分離を維持する。RLS と FORCE RLS は継続する。アプリ権限を増やさない | **採用・承認済み**。INSERT は `(key, category, display_name, disabled)` の承認済み5組だけを `WITH CHECK` で許可。SELECT/DELETE はこの5キーだけを `USING` で許可。UPDATE ポリシーは置かない。既存の認可資産・適用器・静的検査・カタログ検査を変更し、恒久的な所有者書き込み経路が残る |
| B. 0030 内で所有者向けポリシーを作成・削除 | コミット後に追加ポリシーが残らず、成功・失敗とも同じトランザクションで閉じる | 12-4 の DDL/DML 分離と seed revision の DML 検査に限定例外が必要。凍結 DML 許可台帳の変更を伴い、認可 DDL が Alembic に分散する。承認なしでは採れない |
| C. 既存の移行バッチ用 BYPASSRLS ロールを使う | FORCE RLS 下でも投入できる | 同ロールの対象19表にシステム語彙はなく、DDL 不可で Alembic 用でもない。対象・ライフサイクル・カタログ契約の変更が大きいため不採用 |
| D. 外部 superuser で Alembic を実行する | 使い捨てDBでは技術的に成功 | 承認済み製品認可計画の「migration は `pitchlog_owner`」と、データモデル 3-2 の一括投入に superuser を使わない判断に反するため不採用 |
| E. FORCE RLS の解除またはアプリへの INSERT 付与 | 実装は単純 | セキュリティ境界を弱めるため不採用 |

## A 案の具体的な変更

`contracts/authz/product/` の製品 DDL 資産に、`public.system_vocabularies` の `pitchlog_owner` 専用ポリシーを3件追加する。INSERT ポリシーの `WITH CHECK` は `category = 'game_type'`、`disabled IS FALSE` と5つの `(key, display_name)` の組を厳密に照合する。SELECT と DELETE ポリシーの `USING` は同じ category と5キーに限定する。PostgreSQL では WHERE を伴う DELETE に SELECT ポリシーも掛かるため、DELETE だけでは downgrade が0行になる。全ポリシーは `TO pitchlog_owner`、`AS PERMISSIVE` とし、`PUBLIC`・`pitchlog_app`・UPDATE は対象外にする。0030 の `op.bulk_insert()` と限定 DELETE、および seed 許可台帳は変更しない。

**実装上の追加影響（事前点検で判明）**: 現行の `product_provisioning.py` はポリシー名を常に `pitchlog_app_{profile}` として drop/reapply し、`product_catalog.py` も同じ名前を期待する。`scripts/check_authz_catalog.py` は全5プロファイルから導出したポリシー集合への exact-set 一致を要求する。このため資産を3件足すだけでは不合格になる。所有者専用ポリシーを独立した名前で受理するよう、この3か所を限定拡張し、生成・適用・取り外し・カタログ検査に同じ期待集合を使う。既存のアプリ用プロファイル導出は変更しない。`backend/tests/test_product_authz_catalog.py` など件数と名前を固定するテストも追随させる。検査を無条件に緩めず、owner用3件以外の追加ポリシーは引き続き拒否する。

owner用の要素 ID と実ポリシー名は `POLICY:system_vocabularies:owner_game_type_seed_{select,insert,delete}` / `pitchlog_owner_game_type_seed_{select,insert,delete}` に固定する。既存の `profile` からアプリ用ポリシー名を導く規則は残し、この3件だけを静的検査が別系列として認識する。owner用の宣言を `global_read_only` プロファイルの派生集合へ混ぜず、役割と用途を明示する。

レビュー対象となる述語は次に固定する。製品資産へは既存の要素 ID・SQL body 分離形式で登録する。

```sql
-- INSERT の WITH CHECK
category = 'game_type' AND disabled IS FALSE AND (key, display_name) IN (
    ('game_official', '公式戦'),
    ('game_semi_official', '準公式戦'),
    ('game_open', 'オープン戦'),
    ('game_intrasquad', '紅白戦'),
    ('game_other', 'その他')
)

-- SELECT と DELETE の USING
category = 'game_type' AND key IN (
    'game_official', 'game_semi_official', 'game_open',
    'game_intrasquad', 'game_other'
)
```

ポリシーは恒久的に残り、信頼された migration 所有者は対象5キーを後から再投入・削除できる。これは A 案の残余リスクとして人間承認の対象に含める。既存の所有者は同表の DDL 権限を持つが、この追加は DDL を使わない書き込み経路を明示的に増やすため、単なる実装追随とは扱わない。アプリ用ロールへのロール所属は既存の exact-set 検査どおり空に保つ。

`docs/design/data-model.md` の 3-2・12-4 に、この owner 限定ポリシー、正確な5行の範囲、製品 RLS 適用済み DB での適用順を規範として確定する。正本のセキュリティ設計を拡張するため、7.6 の構造的変更として版を繰り上げ、7.3 の敵対レビューと人間承認を**ステップ3の認可資産変更前に**通す。10-3 の実装現況はステップ4で追随する。`docs/features/game-type-seed/plan.md` は認可資産・正本改訂・検証をステップ3の射程に追加し、コア領域計画レビューと人間承認を取り直す。承認前は製品の認可資産・正本・migration を変更しない。

既存の RLS 適用済み DB では、**更新済み製品認可 DDL を外部適用者の既存経路で再適用し、カタログを確認してから、`pitchlog_owner` で 0030 を適用する**。空 DB では従来どおり migration を head にした後に製品認可 DDL を適用できる。順序を本番手順へ反映する前に、専用DBで両経路を検査する。

## ステップ3の検証計画

1. 使い捨て製品DBを 0029 まで `pitchlog_owner` で作り、更新済み製品認可 DDL を適用する。所有者・`relrowsecurity`・`relforcerowsecurity`・ポリシー exact-set・ACL を検査する。
2. 同 DB に `pitchlog_owner` で 0030 を適用し、5行の完全一致、重複適用の no-op、0029 への downgrade と再 upgrade を確認する。無関係な既存行は残す。
3. 同じ構成でキー衝突を起こし、原子性と `alembic_version` の不変を確認する。正しい5キーでの `games` FK 正例、在籍キーでの異区分負例を確認する。
4. `pitchlog_app` のシステム語彙 INSERT/DELETE/UPDATE を拒否し、別テナントの試合アクセスも従来どおり拒否する。`pitchlog_owner` でも5組以外と `disabled=true` の INSERT は例外、5キー以外の DELETE と UPDATE は**影響行0かつ元行不変**を確認する。RLS の `USING` による非表示は例外にならないため、例外の有無だけを合格条件にしない。
5. 製品カタログ exact-set、認可適用器の再適用・原子性、migration hygiene、関連 DB テスト、Ruff、ty を再実行する。
6. 認可資産の静的検査に対し、owner専用3件の正例と、`PUBLIC`/アプリへの付与・余分な行・名称のすり替え・不要な4件目の負例を追加する。適用器の drop/reapply/unapply とカタログ検査が同じ3件を扱うことを検証する。

## コア領域レビューで確認する点

- `WITH CHECK` が5つのキーと表示名の対応および `disabled=false` を固定し、余分なカテゴリ・値・無効化属性を通さないこと。
- SELECT/DELETE ポリシーが downgrade に必要な最小の行だけを許し、UPDATE やアプリへの書き込み経路を作らないこと。
- 既存のアプリ用 SELECT ポリシーとの `PERMISSIVE` 合成とロール所属0件を確認し、owner用ポリシーが `pitchlog_app` や `PUBLIC` に適用されないこと。将来の追加ポリシーは exact-set 検査で拒否すること。
- 製品認可 DDL の再適用が 0029 の DB で成功し、0030 適用後のカタログが正規の exact-set と一致すること。
- 新規DBと既存RLS適用済みDBの両方で、承認済み順序が一意であること。
