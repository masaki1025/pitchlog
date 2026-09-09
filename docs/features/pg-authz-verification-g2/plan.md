---
feature: pg-authz-verification-g2
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2
branch: feature/pg-authz-verification-g2
created: 2026-09-09
計画レビュー周回: 0        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: PostgreSQL 認可構成の実機検証 第 2 群・第 3 群(TSK-270 計画の改訂 2)

## 1. 背景・目的

**Notion タスク**: [TSK-317](https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2)(高)
**前タスク**: [TSK-270](https://app.notion.com/p/3cc93b75e687816a9230e1c1b0ded0e7)(**第 1 群のみ完了** — [PR #33](https://github.com/masaki1025/pitchlog/pull/33) マージ済み `1ab778f`)
**前計画書**: [../pg-authz-verification/plan.md](../pg-authz-verification/plan.md) —
**本書はその 5 節「改訂 2 で確定する(第 2 群・第 3 群)」が予告した改訂 2 である**。
第 1 群の実測・凍結 oracle・満たすべき要件 `R-1`〜`R-8` は同書が正で、**本書へ内容を複製しない**(設計書 7.1-1)。
**受け取り先**: [TSK-344](https://app.notion.com/p/3d593b75e687811f8ad5f5da4a8af046)(実スキーマ適用後の越境テスト再実行)
**下調べ**: [research.md](research.md)(401 行 — 調査サブエージェント 3 本 + 原典の直接確認。全事実に典拠)
**詳細設計**: [design.md](design.md)(DDL 生成器の入力契約・検査 ID 一覧・変異軸と kill 判定の写像・fixture 構造)

**要件**: [`NFR-010`](../../requirements/requirements-pitchlog-2026-07-22.md)(テナント分離)/ `NFR-019`(b)(越境アクセステスト)/
`NFR-014`(シークレット)/ `NFR-018`(b)②(変異テスト — **本タスクは対象外。3-3 節参照**)/ `FR-034`(認可行列・既定拒否)/
`FR-035`・`FR-037`(管理経路)/ `FR-041`(共有と 7 操作)

### なぜやるか

**`docs/design/data-model.md` 12-4 節(approved v0.1)がマージゲートを正本として定めている。**

> **RLS のポリシー / ロール DDL の適用と、実スキーマに対する越境テストが green になるまで、
> DB を利用する製品機能をマージまたは有効化しない**(`:2421-2425`。暫定的にアプリ層分離で
> 先行する場合も同じ越境テストの green を条件とする)

通過条件①(RLS ポリシーとロール DDL が実スキーマへ適用されている)と**越境テストの作成・実行が
本タスクの所有**(同 `:2750`)。**backend の製品機能を出す上のクリティカルパスそのものである。**

**いまの実体**(research.md 4 節の実測): `contracts/authz/auth-catalog.json` の 187 entries は
`enforcement_test_owner.status` が**全件 `planned`**。`backend/src/pitchlog/` は `__init__.py` と `main.py` のみ。
**候補 DDL の SQL 実体がどこにも無い**(`ddl-elements.json` は `contains_sql_body: false`)。
**RLS を実 SQL で検査するテストは 1 本も無い。**

### なぜ改訂 2 か

TSK-270 の計画レビューが 3 周連続で否決され、**人間の裁定 2026-08-31** で第 1 群(契約と前提の凍結・
旧ステップ 1〜5)だけを承認範囲とした(台帳 `H-68`「実体のない段階での設計」)。第 1 群は PR #33 で完了し、
**oracle 15 資産が凍結済み**。本書はその実測を踏まえて第 2 群・第 3 群を確定する。

### PO 裁定(2026-09-09 取得済み)

| # | 論点 | 裁定 |
| --- | --- | --- |
| **D-1** | 第 2 群の射程 | **凍結資産の全量をやる** — 187 enforcement + 231 変異 + 276 相互作用 + MC/DC。cut set だけに絞らない |
| **D-2** | `data-model.md` の `search_path` 契約(P0) | **本タスクの先頭ステップで直す**。第 2 群全体がこの契約の上に建つため先に一致させる |
| **D-3** | DDL 適用器の実装手段 | **psycopg 直書き**。TSK-343 を待たない(`tests/test_ci_wiring.py:1272` に触れない) |
| **D-4** | oracle の裁定待ち 2 件 | **frozen 値を確定として承認** — 管理コマンド **8**・`SCOPE:ALL_LOGICAL` **29**。要件書の「7 操作」との **1:N 写像を明示**して食い違いを解消する |

**`D-4` の根拠(実測)**: `issue_invitation` と `revoke_invitation` は **4 つ目の前提条件が違う**
(`participant_capacity` vs `invitation_active` — `contracts/authz/route-registry.json`)。1 つの ID に統合すると
和集合か片方採用になり、**失効が定員に縛られる**(定員超過を解消できず詰む)か
**最初の招待が発行できない**。要件書の「7」は条項の数え方(`FR-041/list_item-006` に発行と失効が同居)で、
**認可上は別条件の 2 操作**である。`SCOPE:ALL_LOGICAL` 29 件は全 37 経路に掛かる横断的主張
(`authentication_boundary` 19 / `verification_contract` 7 / `cache_authorization` 3)で、縮めると
`NFR-019`(b) の「無効化中に構築された除外キャッシュが残らないこと」を落とす。

## 2. スコープ

### やること

1. **正本の `search_path` 契約の是正**(P0 — `D-2`)
2. **候補 DDL の SQL 実体化**(資産を単一の入力として生成する。手打ちしない)
3. **DDL 適用器**(1 トランザクション・`ordered_steps` 5 件の順序を契約として持つ・冪等)
4. **4 ロール実接続の行列**(`table_owner` / `app_role` / `management_caller` / `outsider_role`)
5. **カタログ検査**(構成そのもの — `R-1`・`R-2`・`R-8` を含む)
6. **越境テスト**(正例 6 セル / 拒否例 / 書き込み / 管理経路 probe / TOCTOU / 適用原子性 / 信頼境界)
7. **mutation の全量**(231 変異 + 276 相互作用 + 最小 cut set 24 + MC/DC・kill 5 条件)
8. **enforcement テスト 187 件の実在化**(`planned` → `implemented`)
9. **第 3 群**: 裁定の反映と oracle の再封印 / `scope` の消化 / 引き渡し 3 資産の確定 /
   `core-areas.json` 登録 / `test_ci_wiring.py`・`test_core_guard.py` の追記 / 設計書 10.1 の追随 /
   期待件数のハードコード撤去

### やらないこと(**`H-68` 対策 — 隣接規範を引き込む要求を書かない**)

| 項目 | 送り先 | 理由 |
| --- | --- | --- |
| HTTP 経路の判定(`404` / `400` / 存在秘匿の同値性) | **TSK-217** | `NFR-010` の測定方法が「**API 直叩き含む**」と定める。DB 層は「0 行」と「権限拒否」を区別してしまう。**本タスクの成果を「`NFR-010` 適合」と主張しない** |
| `NFR-019`(b) の 13 組合せクラスのうち残り 12 | **TSK-217** | 本タスクが届くのは「資源種別ごと」の**常に 404 の 4 資源分のみ**(research.md 3-1 節) |
| 実スキーマ上での越境テスト再実行 | **TSK-344** | 通過条件①の実スキーマは TSK-343 の成果。**本タスクは probe クラスタ上での作成・実行まで** |
| 移行バッチ用ロール(`LOGIN` + `BYPASSRLS`・期間限定)の実機検証 | **申し送り(新規起票)** | `data-model.md` の本タスク宛の列挙(`:2631`・`:2750`)に無い。入れると oracle 変更 + 母集合の `FR-038` 判定(全 18 行 `out_of_scope`)の見直し = `H-85` 連鎖 |
| `contracts/authz/` を ADR-003 `D-12` へ位置づける(領域列挙・命名・`"version"`) | **申し送り(新規起票)** | ADR 改訂は確定ゲート 1 本。**触ると `H-68` の型** |
| アプリ用ロールへの `DELETE` の可否 | **申し送り(新規起票)** | probe の ACL は凍結資産。製品スキーマの判断は正本側(`4.0-2`「物理削除しない」との関係) |
| `H-85` 対応案②(digest 連鎖の 1 段化) | **TSK-312 が別起票済み** | 台帳と TSK-312 計画が矛盾(research.md 5-U-6)。**③ だけを本タスクの射程**とする |
| 設計書 10.1 への `NFR-019`(b)(d) の**新ジョブ行**の新設 | **申し送り(`H-57`)** | TSK-270 の「新ジョブを起こさない」と字面衝突。**`backend` 行の現行化に留める**(新設は `H-19` 型で確定ゲートへ覆るリスク) |
| ORM / `models` / `migration` / 設計書 5.1 の改訂 | **TSK-343** | `data-model.md:2752` |
| 母集合(`requirement-claims.json`)の再分類 | — | 第 1 群で凍結済み。`R-6`・`R-7` も第 1 群で部分履行済み |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PR レビュー / finalize-doc) |
| --- | --- | --- |
| [`docs/design/data-model.md`](../../design/data-model.md) | **3-2 節の `search_path` 契約 1 行を是正**(`pg_temp` を末尾に明示)+ 変更履歴 1 行 | **PR レビュー(節更新 — 7.6-3 前段)**。根拠: 正しい値は既に凍結資産 `REJ-003` の `corrected_expectation` にあり、**新規の設計判断を含まない欠陥是正**である。**敵対レビューが「新規範」と判定したら別タスクへ切り出す** |
| [`docs/development/dev-harness-design-2026-08-07.md`](../../development/dev-harness-design-2026-08-07.md) | 10.1 の `backend` 行の現行化(使い捨てクラスタ)+ 実装追随の箇条 1 件 + 変更履歴 1 行。**版は上げない** | PR レビュー(7.6-3 前段。先例 `:695` が同一系列で「規範・受入条件は変更していない」と宣言して版を上げていない) |
| [`docs/README.md`](../../README.md) | 索引の最終更新日を現行化 | —(常に現行化 — 7.2) |
| `.claude/core-areas.json` | `tenant-isolation.paths` へ新設パスを登録 + description 現行化 | **6.3 規則⑤(敵対レビュー + 人間承認)** |
| [`docs/development/harness-evaluation.md`](../../development/harness-evaluation.md) | **追記の判断は /pr のクローズ処理で行う**(該当時は 3 節へ宣言を先に追記してから台帳へ) | PR レビュー(`H-*` の追記では版を上げない — 7.6-3 前段) |
| `docs/requirements/**` / `docs/adr/**` / `docs/ops/**` / `frontend/**` | **反映なし** | — |

### 正本体系外だが同一 PR で運ぶもの(/pr 突合の別枠宣言)

| ファイル | 変更内容 |
| --- | --- |
| `contracts/authz/boundary-proposal.json` / `ddl-elements.json` / `oracle-seal.lock.json` ほか | ステップ 17〜19(裁定の反映・`scope` 消化・3 資産の確定)。**`frozen_value` は変えない** |
| `backend/src/pitchlog/authz/**` | **新設** — DDL 生成器・適用器・カタログ検査 |
| `backend/tests/db/**` | 4 ロール fixture の拡張・越境テスト・mutation ランナー |
| `scripts/check_authz_catalog.py` / `tests/test_check_authz_catalog.py` | 検査の追加と期待件数の撤去 |
| `tests/test_ci_wiring.py` / `tests/test_core_guard.py` | 配線と発火の固定 |
| `docs/features/pg-authz-verification-g2/{plan,research,design}.md` | feature 作業ディレクトリ(記録・正本ではない) |

## 4. 実装方針

### 重さ分類の根拠 — **コア領域(テナント分離)**

設計書 6.3 の境界定義表がテナント分離に「**テナント境界の認可判定すべて** = `FR-034` の認可行列・既定拒否を
中心に、`FR-033`/`FR-035`/`FR-037` の認可源・管理経路、`FR-041` の共有操作…+ `NFR-010` の越境防止」を含める。
本タスクの成果は**その認可判定の物理構成そのもの**である。
→ **`sol xhigh`・敵対レビュー必須・人間の逐行確認必須**(PR 作成者以外)。

**core-guard は発火する** — `contracts/authz/*`・`backend/tests/db/*`・`scripts/check_authz_catalog.py`・
`tests/test_check_authz_catalog.py`・`backend/pyproject.toml`・`backend/uv.lock`・`backend/*conftest.py`・
`docker-compose.yml` が `tenant-isolation.paths`(22 件)に登録済み(導入 `d4373ec`)。
**未登録は `backend/src/**`** で、これがステップ 20 の対象。

### 合格条件の書き方(3 つの規律)

1. **`[機械]`**(コマンドで判定できる)と **`[手動・外部]`**(人間が確認して worklog へ記録する)に
   **書き分ける**。**`[手動・外部]` を機械 green の一部として数えない**
2. **合格条件を「検査が green」に置かず「割り当てが正しい」に置く** — 検査は literal 一致で通るため、
   literal を置くだけで green にできる(7.3-3 が P1 と定める「文言は直したが実効がない」型)
3. **件数を定数で持たない**(`H-53`)— 母集合は資産から導出し、**ID 集合の sha256 で exact-set 突合**する

### 実機検証の実施主体

**CI が機械判定の主体**。`backend` ジョブに `postgres:17.11-bookworm` サービスと
`PITCHLOG_TEST_ADMIN_DSN` / `PITCHLOG_TEST_ROLE_DSN` が配線済みで、使い捨てクラスタは Docker CLI 経由なので
CI でも動く。**ローカル実行は再現手順として文書化する**(環境変数の実値の用意は人間の作業 — `NFR-014`・設計書 12.1。
実測: `docker compose config` が `POSTGRES_USER` 欠落で失敗・`psql` は未導入)。
**ソケット bind を伴う起動確認は委任先へ出せない**ので、そこは `[手動・外部]` に書き分ける(`H-79` 対応案 (b))。

### oracle を触る点を 1 箇所に集約する

`contracts/authz/oracle-seal.lock.json` の `ORACLE_STEP5_REREVIEW` は **6 資産の canonical digest 全体**を
封印しており、**追加でも発火する**。reseal は `--reseal-oracle` + 人間査読が必須。
→ **ステップ 17〜18 の 1 回だけに集約する**。`frozen_value` は変えず `status` のみ更新するので差分は最小。
**再レビューの周回は 3 周を目安**とし、超えたら PO 裁定を起動する(7.3-6 の 6 周警告に倣う)。

### ステップ番号の規律(枝番を作らない)

**総数が変わり得るため、ステップコミット件名には総数接尾辞 `/N` を付けず `(ステップ k)` のみを使う。**
分割で単位が増えた場合も**整数連番のまま振り直す計画改訂**で扱う(`scripts/feature_status.py` は
整数連番のみ認識し `4a`・`4b` 等の枝番を認識しない)。

### 規模の申し送り

**`D-1`(全量)により本計画は 23 ステップになる。** コア領域なので全ステップに人間の逐行確認が掛かり、
**スループットの上限は逐行確認**である(TSK-317 のカード自身が「逐行確認は並列化できない人的資源」と警告)。
停滞した場合の**自然な分割点はステップ 16/17 の境界**(第 2 群の完了 = マージゲートの通過条件①が揃う点)。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

> **見出しに「実装ステップ」を含めるのは機構要件**。`.claude/scripts/codex_run.py` はステップ表を
> **見出しスタックで判定する**ため、小見出しは本見出しの配下に置くこと(祖先に「実装ステップ」があれば射程内)。

#### 実装ステップ — 第 2 群: 実機検証(1〜16)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **正本の `search_path` 契約の是正**(P0・`D-2`)— `data-model.md` 3-2 節の当該行を `pg_temp` の末尾明示へ。変更履歴 1 行 + `docs/README.md` 現行化。**oracle と probe は触らない** | `[機械]` 正本に「一時スキーマを `search_path` から外す」相当の記述が 0 件・`pg_temp` の末尾明示が本文にある・`uv run python scripts/check_docs_status.py` green。`[手動・外部]` **`REJ-003` の `corrected_expectation`(`place_pg_temp_explicitly_last`)と逐語で一致している** |
| 2 | **候補 DDL の SQL 実体化** — `ddl-elements.json`(ロール 7・スキーマ 3・表 6・ポリシー 6・関数 3・ACL 17)を**単一の入力として SQL を生成**する | `[機械]` **資産の全要素 ID が生成物に現れる**(ID 集合の sha256 で exact-set 突合)・**資産を参照しない SQL リテラルが 0 件**・**負例: 資産から 1 要素を削ると生成物が変わる**。`[手動・外部]` 生成された DDL が `ddl-elements.json` の属性(`force_rls`・`public_execute: false`・`search_path`)を落としていない |
| 3 | **DDL 適用器**(psycopg 直書き・1 トランザクション)— `provisioning_claim.ordered_steps` 5 件(`PROVISION-01-CREATE-OWNER`〜`PROVISION-05-CLOSE-SET-PATH`)の**順序を契約として持つ**。冪等(`CREATE OR REPLACE` + `ALTER OWNER` + ACL の全正規化) | `[機械]` 空クラスタへ 2 回適用してカタログが一致(冪等)・**古い直接 `GRANT` が 1 回目と 2 回目の双方で消えている**・順序が資産から導出されている(定数で並べていない)・**負例: 手順 2 を手順 3 の後ろへ移すと適用そのものが失敗する**(`R-8`)・**負例: 手順 5 の `REVOKE` を省略すると red** |
| 4 | **4 ロール実接続 fixture** — `table_owner` / `app_role` / `management_caller` / `outsider_role`。**`SET ROLE` を使わない**。各テストの冒頭で `session_user` / `current_user` を照合 | `[機械]` 4 本すべてが別ユーザーで接続する・`tests/test_ci_wiring.py` の `assert "SET ROLE" not in conftest` が維持される・**照合を外すと red**・`requires_db` の 0 件収集 / 0 件実行ガードが維持される・DSN 未設定は skip ではなく fail |
| 5 | **カタログ検査(構成そのもの)** — `pg_policy` の `polcmd`/`polroles`/`polpermissive`/`polqual`/`polwithcheck` を正規化して exact 比較 / **`pg_get_functiondef`・owner・language・security・volatility・leakproof・strict・parallel・`proconfig`・ACL の digest**(`R-1`)/ **危険終点 = `rolsuper OR rolbypassrls OR 保護 relation/schema/routine の owner` と `SET` 到達集合の交差が空**(`R-2`)/ 列 ACL・schema ACL・default ACL / `search_path` 末尾 `pg_temp` が 1 回 / `CATALOG:PROVISIONER-CANNOT-SET-OWNER` と `CATALOG:PROVISIONER-CANNOT-USE-OWNER` | `[機械]` **負例 6 種で red**: 既存関数の body へ禁止 relation の SELECT を追加 / superuser への間接所属 / 表 owner への所属 / アプリ自身の `SUPERUSER` 化 / 採用構成外の関数が 1 件増える / `PUBLIC` の `EXECUTE` を残す。`[手動・外部]` **`R-1`・`R-2`・`R-8` の各要求と検査項目の対応が全件ある**(対応表を worklog へ) |
| 6 | **越境テスト(正例)** — `claim-mutant-map.json` の `positive_cases.cases` 6 件(許可セル) | `[機械]` `http-route-matrix.json` の allow セルと**正例テスト ID が 1:1**(sha256 で exact-set)・**許可された行だけが返る**(全件返す実装では red)・**関数が返す列が集計値に限られている**(生記録・所見を返す経路が構造的に無い) |
| 7 | **越境テスト(拒否例)** — 常に 404 の 4 資源 / **対象側が非共有なら要求元が付与していても返らない** / `PUBLIC` が越境関数を実行できない / `search_path` の乗っ取りが効かない / アプリ用ロールが関数を経由せず他テナント行を読めない | `[機械]` `data-model.md` 12-4 節の**最低要求 4 件がすべて実行可能なテストとして存在**・deny セルと 1:1・**`REJ-001`/`REJ-002`/`REJ-003` の各構成に戻すと red になる**。`[手動・外部]` **`data-model.md:239` のスキーマ検査・`:544` の「6 前提と認可行列の各行それぞれ」の網羅を概念名で全節列挙して確認した**(`H-79` 対策) |
| 8 | **書き込みの検証** — 表権限 **8 種**(`SELECT`/`INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`/`REFERENCES`/`TRIGGER`/`MAINTAIN` — `R-6`)× ロール。`table_privilege_probe_matrix` 8 行。**共有行は SELECT のみ正例・全 DML は拒否** | `[機械]` 8 種が**単一の機械可読集合から**カタログ検査・実行行列・mutation へ生成されている・**「6 権限」という記述が 0 件**・`table_privilege_probe_matrix` と exact-set・**1 権限を落とすと red** |
| 9 | **管理経路の代表 probe 1 件** — `representative_management_probe`。**呼び出しロールに基表 DML が無い** + **関数内で認可と副作用が原子的** | `[機械]` `management_caller` の `probe_management_effects` への直接アクセスが 8 権限すべてで deny・関数経由のみ成功・**それ以上の管理操作を実装していない**(実装した操作の集合が資産と一致) |
| 10 | **TOCTOU の 2 接続試験**(`R-3`)— 認可確認の直後に barrier を置き、別トランザクションが認可状態を変える | `[機械]` **barrier を外すと red**・**認可行を lock するか認可条件を副作用 DML の同一文へ埋め込む**ことで linearization point が一意であることを示す・`VOLATILE` 関数が内部クエリごとに新しい snapshot を取る前提を試験が明示する |
| 11 | **適用原子性の失敗点 5 種**(`R-5`)— ロール作成後 / policy 変更後 / body 置換後 / owner 変更後 / ACL 正規化途中 | `[機械]` 5 点それぞれで注入して**全対象 catalog・membership・default ACL・fixture data** が適用前と一致・**注入位置が資産から導出されている**(最初の文より前に失敗させるだけでは合格しない) |
| 12 | **信頼境界の残余リスク試験** — **アプリ用実接続から `set_config()` で他テナント ID を設定できる**ことを試験し、結果を残余リスクとして記録する(隠さない) | `[機械]` 試験が存在し**「設定できてしまう」ことを期待値として持つ**(将来塞がれたら red になる)。`[手動・外部]` 残余リスクを worklog と `verification-evidence.json` へ**申し送り先つき**で記録した(トークン → GUC の結合の検証は TSK-217) |
| 13 | **mutation ランナーと kill 判定 5 条件** — `KILL-01-TARGETED-CATALOG-DELTA` / `KILL-02-TEST-EXECUTED` / `KILL-03-EXPECTED-FAILURE` / `KILL-04-NO-FIXTURE-FAILURE` / `KILL-05-GLOBAL-STATE-ISOLATION`(**使い捨てクラスタ**) | `[機械]` 5 条件が資産から導出されている・**`KILL-04` の負例(setup 失敗を kill に数える)で red**・**`KILL-05` の負例(共有クラスタでロール属性を変異させる)で red**・**変異ごとに新しい DB を作る**(製品適用器を巻き戻し装置にしない) |
| 14 | **変異の全量実行** — 231 変異(`authorization_predicate` 205 / `configuration` 24 / `r8_provisioning` 2) | `[機械]` **非等価変異の生存 0**・変異集合が資産から導出され**件数を定数で持たない**(sha256 で exact-set)・等価変異は人手判定で分母から除外し**除外の記録がある**。`[手動・外部]` 等価判定の根拠を変異ごとに記録した |
| 15 | **2 因子相互作用 276 件 + 最小 cut set 24 件 + MC/DC** | `[機械]` 276 件と 24 件が資産と exact-set・`mcdc_decision_forms` の各判定形で MC/DC を満たす・**1 相互作用を落とすと red**・**cut set の 1 要素を落とすと red** |
| 16 | **enforcement テストの実在化** — `auth-catalog.json` の 187 entries を `planned` → `implemented`。**`H-85` の追随はステップ 22 で行う**(本ステップでは期待件数を触らない) | `[機械]` **187 件すべての `enforcement_test_owner.id` が `collect_pytest_node_ids` の結果に実在する**・`planned` のまま残った件が 0 件・**件数は資産から導出**。`[手動・外部]` 各 claim の `layer` と `db_basis_rule_id` に対して検査内容が対応している(5 層 × 5 規則の対応表を worklog へ) |

#### 実装ステップ — 第 3 群: 引き渡し(17〜23)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 17 | **裁定の反映と oracle の再封印**(`D-4`)— `boundary-proposal.json` の `pending_human_reviews` 2 件を裁定済みへ。**`frozen_value` は変えない**。`--reseal-oracle` を **1 回だけ**回す | `[機械]` `frozen_value` の差分が 0(`8` と `29` のまま)・`status` 以外の差分が 0・reseal 後に `check_authz_catalog.py` が rc=0・**通常検証では reseal されない**(`--reseal-oracle` なしで差分が出ない)。`[手動・外部]` **`ORACLE_STEP5_REREVIEW` の差分敵対レビューと人間査読を通した**(`reseal_policy.human_review_required: true`) |
| 18 | **`scope` の消化** — `ddl-elements.json` の `status: candidate_probe_only` を通った構成へ。`second_group_approval_required` を解消。**ステップ 17 と同じ reseal 内で行う**(2 度 reseal しない) | `[機械]` `product_schema` の扱いが明記されている・**「通った構成」の根拠が実行結果への参照を持つ**(主張だけでない)・`oracle_commit` が更新され全 6 資産の digest が整合 |
| 19 | **引き渡し 3 資産の確定** — スキーマ版・安定 ID・共通正規化 ID・元 commit・blob digest。**`AUTH-*` が成果 ID + blob digest で特定できる形**にする | `[機械]` 3 資産に版と digest がある・`git_blob_digest` で照合が通る・**受け手が exact-set で突合できる**(ID 集合の sha256 を資産に持つ)。`[手動・外部]` `R-4` の受取契約のテスト ID が資産の文字列と一致している(**受け手のタスク再編は本タスクの射程外** — research.md 5-U-7) |
| 20 | **`core-areas.json` へ新設パスを登録**(6.3 規則⑤)+ `tests/test_core_guard.py` の発火試験 | `[機械]` `scripts/core_guard.py` の `matched_paths` が新設パスにマッチ・`uv run pytest tests/test_core_guard.py` green・**登録を外すと発火しないことを負例で示す**。`[手動・外部]` **paths 追加の敵対レビュー + 人間承認**(逐行確認は PR 作成者以外) |
| 21 | **`tests/test_ci_wiring.py` の追記 + 設計書 10.1 の追随** — 使い捨てクラスタの配線を固定。**`backend` 行の現行化と実装追随箇条 1 件に留め、新ジョブ行を作らない** | `[機械]` `uv run pytest tests/test_ci_wiring.py` green・**pytest の実行回数が 1 のまま**・`-m` を含むコマンドが 0 件・設計書の版が不変で追記が 1 箇条 + 変更履歴 1 行・`backend` の run コマンド列が完全一致で維持される |
| 22 | **期待件数のハードコード撤去**(`H-85` 対応案③ の射程内分)— 本タスクが作るテストの期待件数を**資産由来の導出**へ。**追随は独立コミット**(対応案①) | `[機械]` 新設テストに件数リテラルが 0 件・**資産を 1 要素増やすとテストが自動追随する**・既存 20 箇所のうち本タスクが触った分が撤去されている。`[手動・外部]` 撤去しなかった箇所とその理由を記録した |
| 23 | **成果物の敵対レビューと反映** — 対象 = 適用器・カタログ検査・越境テスト・mutation・引き渡し 3 資産。**途中の反映コミットにはステップ記法を付けない**。収束後の最終反映 1 件のみに `(ステップ 23)` を付ける | `[機械]` 最終周 P0/P1 = 0 で収束。`[手動・外部]` 採否記録が worklog に周ごとにある(**指摘ゼロの周も採否記録を残す**) |

## 5. DoD(受け入れ基準)

- [ ] **`data-model.md` の `search_path` 契約が `REJ-003` の `corrected_expectation` と一致している**(P0 是正)
- [ ] **候補 DDL の SQL 実体があり、`ddl-elements.json` を単一の入力として生成されている**(資産を参照しない SQL リテラル 0 件)
- [ ] **DDL 適用器が 1 トランザクションで、`ordered_steps` 5 件の順序を契約として持ち、冪等である**
- [ ] **4 ロールの実接続の行列がある**(`SET ROLE` の模擬を使っていない・各テストで `session_user` を照合)
- [ ] **カタログ検査が `R-1`・`R-2`・`R-8` の要求を満たし、負例 6 種で red になる**
- [ ] **12-4 節の越境テスト最低要求 4 件すべてが実行可能なテストとして存在する**。あわせて **`data-model.md:239` のスキーマ検査・`:544` の 6 前提と認可行列の各行**を網羅した
- [ ] **表権限 8 種が単一の機械可読集合から生成されている**(「6 権限」の記述が 0 件)
- [ ] **TOCTOU・適用原子性 5 点・信頼境界の残余リスク試験がある**
- [ ] **231 変異・276 相互作用・最小 cut set 24・MC/DC を実行し、非等価変異の生存が 0 件**。**件数を定数で持っていない**
- [ ] **`auth-catalog.json` の 187 件が `implemented` で、テスト ID が収集結果に実在する**(`planned` 残 0 件)
- [ ] **oracle の裁定 2 件を反映し、`frozen_value` を変えずに 1 回だけ reseal した**(差分敵対レビュー + 人間査読を通した)
- [ ] **要件書の「7 操作」と資産の `operation_ids`(8)の 1:N 写像を明示した**(`D-4`)
- [ ] **引き渡し 3 資産が成果 ID + blob digest で特定できる**
- [ ] **`core-areas.json` へ新設パスを登録した**(6.3 規則⑤の敵対レビュー + 人間承認)
- [ ] **設計書 10.1 の追随は `backend` 行の現行化に留め、新ジョブ行を作っていない**(版は上げない)
- [ ] **本タスクの成果を「`NFR-010` 適合」と主張していない**。HTTP 経路の判定は TSK-217 へ送った
- [ ] **mutation を `NFR-019` のテスト種別として計上せず、`NFR-018`(b)② を根拠に引いていない**(6 節)
- [ ] **申し送りを起票した** — 移行バッチ用ロール / ADR-003 `D-12` と `contracts/authz/` / アプリ用ロールの `DELETE` / `H-57` のジョブ行 / `closure-handoff-data-model.json` の「作成」と正本の「作成・実行」の差
- [ ] **`[手動・外部]` の全項目について、逐項の証跡を worklog に残した**
- [ ] **コア領域として敵対レビュー + 人間の逐行確認を通っている**(逐行確認は **PR 作成者以外**が行い、**実施記録行を確認者本人が記入**した)

## 6. テスト計画(NFR-019)

**要件が定義する CI のテストは 4 種**((a) 一致性 /(b) 越境 /(c) E2E 主要分岐 /(d) 同期故障系)。
**「単体」は `NFR-019` に存在しない** — `docs/development/templates/plan-template.md` の
「単体・一致性・越境・E2E・故障系」という 5 種の要約は誤りで、前計画書 6 節もこれを引いて誤帰属していた
(research.md 3-3 節)。本書は 4 種で書く。

| 種別 | 追加内容 |
| --- | --- |
| **(b) 越境アクセステスト** | ステップ 6〜9・12 — 正例 6 / 拒否例 / 書き込み 8 権限 / 管理経路 probe / 信頼境界。**DB レベルの「0 行 / 権限拒否」まで**で、`404` の判定と 13 組合せクラスの残り 12 は TSK-217 |
| **(a) 一致性 /(c) E2E /(d) 同期故障系** | **追加なし** |
| **構成検査(要件の 4 種に属さない — 設計判断)** | ステップ 5 のカタログ検査 / ステップ 3 の冪等性 / ステップ 11 の適用原子性 / ステップ 10 の TOCTOU。**`NFR-019` の種別として計上しない**(`data-model.md:239` が「越境テストとは別に構成そのものを検査する」と定める) |
| **mutation(要件の 4 種に属さない — 設計判断)** | ステップ 13〜15。**`NFR-018`(b)② を根拠に引かない** — 同項の対象列挙(状況判定・座標変換・捕球選手推定・成績集計の前処理・終了判定)に**認可構成は入っておらず**、実装判断で対象に加える規定もない。**「3 変異で必ず red」という件数にも要件典拠がない**(要件の閾値は「非等価変異の生存 0」) |
| **回帰(本物の資産)** | `test_repository_oracle_assets_are_valid` / `test_repository_derived_assets_are_valid` ほか既存 72 件が green のまま。**実行前後で oracle のバイトが一致**することを assert する |

**件数のハードコードは 1 箇所に集約する** — 既存 `tests/test_check_authz_catalog.py` の期待件数 20 箇所が
過去に他タスクを red にした連鎖(`H-85`)があるため、本タスクの新設分は**資産由来の導出**にする(ステップ 22)。

## 7. 検証(このタスクが終わったことの確認方法)

```bash
WT=../pitchlog-worktrees/feature-pg-authz-verification-g2

# 1. 認可資産の検査(違反 0)
uv run python scripts/check_authz_catalog.py --root "$WT"

# 2. oracle の封印が整合し、通常検証では reseal されないこと
git -C "$WT" diff --exit-code contracts/authz/

# 3. 品質ゲート一括(/check 相当)
cd "$WT" && uv run ruff check . && uv run ty check && uv run pytest tests/
cd "$WT/backend" && uv run ruff format --check . && uv run ruff check . && uv run ty check && uv run pytest

# 4. core-guard と CI 配線が新設資産にマッチすること
uv run pytest tests/test_core_guard.py tests/test_ci_wiring.py

# 5. 現在地導出
uv run python scripts/feature_status.py
```

**DB 必須テストの実行には `PITCHLOG_TEST_ADMIN_DSN` と `PITCHLOG_TEST_ROLE_DSN` の実値が必要**
(未設定は skip ではなく fail)。**ローカルでは人間が用意する**。CI では配線済み。

**人間が確認すること**: `search_path` 契約の是正が `REJ-003` と逐語一致していること /
カタログ検査の項目と `R-1`〜`R-8` の対応 / 187 件の `layer` と検査内容の対応 /
oracle の reseal 差分が `status` のみであること / `core-areas.json` の追加分。

## 8. 進め方

1. 本計画書 + [design.md](design.md) を**コア領域の敵対レビュー**へ:
   `python .claude/scripts/codex_run.py review adversarial -`
2. 指摘を反映(指摘反映を伴うレビュー 1 周ごとに frontmatter の `計画レビュー周回` を +1)
3. 収束したら**人間の承認**を求める → `承認: 済(YYYY-MM-DD・承認者)` へ
4. 承認後 `/implement` でステップ 1 から委任(1 委任 = 1 ステップ = 1 コミット・件名は `(ステップ k)`)
