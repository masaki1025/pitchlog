---
feature: pg-authz-verification-g2
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2
branch: feature/pg-authz-verification-g2
created: 2026-09-09
計画レビュー周回: 1        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
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
第 1 群の実測・凍結 oracle・満たすべき要件 **`R-1`〜`R-8`** は同書が正で、**本書へ内容を複製しない**(設計書 7.1-1)。
**依存**: [TSK-348](https://app.notion.com/p/3d693b75e687816b8911f266f9bb59c5)(`data-model.md` v0.2 の改訂ゲート — **本タスクは待たないが、本タスクのマージ前にマージされていることが望ましい**)
**受け取り先**: [TSK-344](https://app.notion.com/p/3d593b75e687811f8ad5f5da4a8af046)(実スキーマ適用後の越境テスト再実行)/
[TSK-349](https://app.notion.com/p/3d693b75e68781cdaa22f364955f9fab)(移行バッチ用ロールの実機検証と退役検査)/
[TSK-343](https://app.notion.com/p/3d593b75e68781469990ca4e61fca9d2)(ORM・`models`・`migration`・**設計書 5.1・10.1 の改訂**)
**下調べ**: [research.md](research.md)(401 行 — 調査サブエージェント 3 本 + 原典の直接確認。全事実に典拠)
**詳細設計**: [design.md](design.md)(DDL 生成器の入力契約・検査 ID 一覧・変異軸と kill 判定の写像・fixture 構造)

**要件**: [`NFR-010`](../../requirements/requirements-pitchlog-2026-07-22.md)(テナント分離)/ `NFR-019`(b)(越境アクセステスト)/
`NFR-014`(シークレット)/ `NFR-012`(操作ログ)/ `FR-034`(認可行列・既定拒否)/ `FR-035`・`FR-037`(管理経路)/ `FR-041`(共有と 7 操作)

### なぜやるか

**`docs/design/data-model.md` 12-4 節(approved v0.1)がマージゲートを正本として定めている。**

> **RLS のポリシー / ロール DDL の適用と、実スキーマに対する越境テストが green になるまで、
> DB を利用する製品機能をマージまたは有効化しない**(暫定的にアプリ層分離で先行する場合も同じ条件)

通過条件①(RLS ポリシーとロール DDL が適用されている)と**越境テストの作成・実行が本タスクの所有**。
**backend の製品機能を出す上のクリティカルパスそのものである。**

**いまの実体**(research.md 4 節の実測): `contracts/authz/auth-catalog.json` の 187 entries は
`enforcement_test_owner.status` が**全件 `planned`**。`backend/src/pitchlog/` は `__init__.py` と `main.py` のみ。
**候補 DDL の SQL 実体がどこにも無い**。**RLS を実 SQL で検査するテストは 1 本も無い。**

### なぜ改訂 2 か

TSK-270 の計画レビューが 3 周連続で否決され、**人間の裁定 2026-08-31** で第 1 群(契約と前提の凍結・
旧ステップ 1〜5)だけを承認範囲とした(台帳 `H-68`「実体のない段階での設計」)。第 1 群は PR #33 で完了し、
**oracle 15 資産が凍結済み**。本書はその実測を踏まえて第 2 群・第 3 群を確定する。

### PO 裁定(2026-09-09 取得済み)

| # | 論点 | 裁定 |
| --- | --- | --- |
| **D-1** | 第 2 群の射程 | **凍結資産の全量をやる** — 187 enforcement + 231 変異 + 276 相互作用 + MC/DC。cut set だけに絞らない |
| **D-3** | DDL 適用器の実装手段 | **psycopg 直書き**。TSK-343 を待たない(`tests/test_ci_wiring.py:1272` に触れない) |
| **D-4** | oracle の裁定待ち 2 件 | **frozen 値を確定として承認** — 管理コマンド **8**・`SCOPE:ALL_LOGICAL` **29**。要件書の「7 操作」との **1:N 写像を明示**して食い違いを解消する |
| **D-5** | 正本側の未処理 3 件(`search_path` の P0 / 返却契約の不一致 / 定義の言い換えによる重複) | **[TSK-348](https://app.notion.com/p/3d693b75e687816b8911f266f9bb59c5) として v0.2 の改訂ゲートを 1 本立てる**。**本タスクの射程外**。本タスクは正しい値(`pg_temp` 末尾明示・認可済み業務行を返す)を前提に進む |

> **`D-5` は当初の裁定 `D-2`(「本タスクの先頭ステップで直す」)を置き換える。**
> 計画レビュー 1 周目の `P0-1` が、`search_path` 契約の是正は**版繰り上げを伴う構造的変更**であり
> 7.6-3 の「実装追随の節更新」に該当しない(= 確定ゲート事項)と判定したため、前提が変わった。
> **コア領域 24 ステップのタスクへ確定ゲートを入れると台帳 `H-68`「隣接規範の引き込み」の型**になる。

**`D-4` の根拠(実測)**: `issue_invitation` と `revoke_invitation` は **4 つ目の前提条件が違う**
(`participant_capacity` vs `invitation_active`)。1 つの ID に統合すると和集合か片方採用になり、
**失効が定員に縛られる**(定員超過を解消できず詰む)か **最初の招待が発行できない**。
要件書の「7」は条項の数え方(`FR-041/list_item-006` に発行と失効が同居)で、**認可上は別条件の 2 操作**。
`SCOPE:ALL_LOGICAL` 29 件は全 37 経路に掛かる横断的主張で、縮めると
`NFR-019`(b) の「無効化中に構築された除外キャッシュが残らないこと」を落とす。

### 計画レビュー 1 周目で訂正した前提(重要)

| # | 当初の記述 | 実測による訂正 |
| --- | --- | --- |
| 1 | 適用器を **1 トランザクション**にする | **誤り。** `ddl-elements.json` の `TX:PROVISIONING` は **`atomic: false`**(`ordered_application`)。原子なのは `TX:REPRESENTATIVE_MANAGEMENT`(`authorization_and_side_effect`)と、それだけ。**順序適用 + 冪等による収束**が正 |
| 2 | ステップ 17・18 を別コミットにして **reseal は 1 回** | **両立しない。** `boundary-proposal.json` と `ddl-elements.json` は**ともに封印 6 資産**。別コミットなら 2 回 reseal になる。**1 ステップ・1 コミット・1 reseal へ統合する** |
| 3 | reseal で **`oracle_commit` が更新される** | **誤り。** `_build_oracle_seal` は `input_assets[].git_blob_digest` と `sealed_assets[].canonical_sha256` だけを再計算する。`oracle_commit_semantics` は `last_committed_step_4_input_baseline` に固定で、検査器がその値を要求する |
| 4 | 資産の `status` を変えれば足りる | **足りない。** `check_authz_catalog.py` が `scope.status == "candidate_probe_only"` ほか 4 値と `PENDING-MANAGEMENT-COMMAND-COUNT.status == "pending_human_decision"`・`frozen_value == 8`・`alternative_value == 7` を**ハード要求**する。**検査器の契約変更を同一コミットに含める** |
| 5 | 関数 SQL を生成してその `pg_get_functiondef` digest を検査する | **自己 oracle 化する。** 資産に body・引数型・戻り列が無く(`contains_sql_body: false` は検査器が要求する値)、生成物の digest を自分で oracle 化しても green にできる。**body を先行コミットで固定してから検査を置く**(第 1 群の `expectations_must_precede_observation_code` と同型) |
| 6 | 設計書 10.1 を本タスクで追随する | **正本と衝突。** `data-model.md` の受け取り先表が **10.1 の改訂を TSK-343** へ割り当てている。**射程外**にする |
| 7 | ステップ 23 で「途中の反映コミットにはステップ記法を付けない」 | **現在地導出を壊す。** `feature_status.py` の `is_documentation_path` は `docs/` 配下と `.md` だけを文書とみなし、それ以外の無記法コミットを `implementation` に分類して進捗を不明にする。**反映は該当ステップ番号 + 付記**で行う(例 `(ステップ 5 レビュー反映 2 周目)`) |

## 2. スコープ

### やること

1. **関数 body と DDL の SQL 実体**を新設資産として置く(**先行コミット** — 自己 oracle 化を防ぐ)
2. **DDL 生成器**(資産を単一の入力として SQL を組む。手打ちの識別子を持たない)
3. **DDL 適用器**(**順序適用・非原子**・`ordered_steps` 5 件の順序を契約として持つ・冪等で収束)
4. **4 ロール実接続の行列**(`table_owner` / `app_role` / `management_caller` / `outsider_role`)
5. **カタログ検査**(構成そのもの — `R-1`・`R-2`・`R-8`)
6. **越境テスト**(正例 / 拒否例 / **6 前提 × 認可行列各行** / 書き込み / 管理経路 probe / TOCTOU / 失敗点 / 信頼境界)
7. **mutation の全量**(231 変異 + 276 相互作用 + 最小 cut set 24 + **MC/DC の写像を新設**・kill 5 条件)
8. **enforcement テスト 187 件の実在化**(`planned` → `implemented` + **結合を壊す負例**)
9. **第 3 群**: 7→8 写像の作成 / 裁定の反映と検査器の契約変更と 1 回の reseal / `scope` の消化 /
   引き渡し 3 資産の確定 / `core-areas.json` 登録 / `test_ci_wiring.py` の追記 / 期待件数のハードコード撤去

### やらないこと(**`H-68` 対策 — 隣接規範を引き込む要求を書かない**)

| 項目 | 送り先 | 理由 |
| --- | --- | --- |
| **`data-model.md` の 3 件の是正**(`search_path` の P0 / 返却契約の不一致 / 定義の言い換えによる重複) | **[TSK-348](https://app.notion.com/p/3d693b75e687816b8911f266f9bb59c5)** | **`D-5`**。版繰り上げを伴う構造的変更 = 7.3 の確定ゲート事項。本タスクへ入れると `H-68` の型 |
| **設計書 5.1・10.1 の改訂**と実装追随箇条 | **[TSK-343](https://app.notion.com/p/3d593b75e68781469990ca4e61fca9d2)** | `data-model.md` の受け取り先表が TSK-343 へ割り当てている(計画レビュー 1 周目 `P1-14`) |
| **移行バッチ用ロールの実機検証と退役検査** | **[TSK-349](https://app.notion.com/p/3d693b75e68781cdaa22f364955f9fab)** | `data-model.md` の本タスク宛の列挙に無い。入れると oracle 変更 + 母集合の `FR-038` 判定の見直し = `H-85` 連鎖 |
| HTTP 経路の判定(`404` / `400` / 存在秘匿の同値性)と `NFR-019`(b) の 13 クラスのうち残り 12 | **TSK-217** | `NFR-010` の測定方法が「**API 直叩き含む**」と定める。DB 層は「0 行」と「権限拒否」を区別してしまう。**本タスクの成果を「`NFR-010` 適合」と主張しない** |
| 実スキーマ上での越境テスト再実行 | **TSK-344** | 通過条件①の実スキーマは TSK-343 の成果。**本タスクは probe クラスタ上での作成・実行まで** |
| `contracts/authz/` を ADR-003 `D-12` へ位置づける(領域列挙・命名・`"version"`) | **申し送り(/pr で起票)** | ADR 改訂は確定ゲート 1 本。**触ると `H-68` の型** |
| アプリ用ロールへの `DELETE` の可否(製品スキーマ側) | **申し送り(/pr で起票)** | probe の ACL は凍結資産。製品スキーマの判断は正本側(`4.0-2`「物理削除しない」との関係) |
| `H-85` 対応案②(digest 連鎖の 1 段化) | **TSK-312 が別起票済み** | 台帳と TSK-312 計画が矛盾(research.md 5-U-6)。**③ だけを本タスクの射程**とする |
| ORM / `models` / `migration` | **TSK-343** | |
| 母集合(`requirement-claims.json`)の再分類 | — | 第 1 群で凍結済み |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PR レビュー / finalize-doc) |
| --- | --- | --- |
| [`docs/README.md`](../../README.md) | 索引の最終更新日を現行化 | —(常に現行化 — 7.2) |
| `.claude/core-areas.json` | `tenant-isolation.paths` へ新設パスを登録 + description 現行化 | **6.3 規則⑤(敵対レビュー + 人間承認)** |
| [`docs/development/harness-evaluation.md`](../../development/harness-evaluation.md) | **追記の判断は /pr のクローズ処理で行う**(該当時は本節へ宣言を先に追記してから台帳へ) | PR レビュー(`H-*` の追記では版を上げない — 7.6-3 前段) |
| [`docs/design/data-model.md`](../../design/data-model.md) | **反映なし**(3 件の是正は **TSK-348**) | — |
| [`docs/development/dev-harness-design-2026-08-07.md`](../../development/dev-harness-design-2026-08-07.md) | **反映なし**(10.1 の追随は **TSK-343**) | — |
| `docs/requirements/**` / `docs/adr/**` / `docs/ops/**` / `frontend/**` | **反映なし** | — |

### 正本体系外だが同一 PR で運ぶもの(/pr 突合の別枠宣言)

| ファイル | 変更内容 |
| --- | --- |
| `contracts/authz/function-bodies/**` | **新設** — 関数 body と DDL の SQL 実体(ステップ 1 の先行コミット。**封印 6 資産ではない**) |
| `contracts/authz/mcdc-map.json` | **新設** — MC/DC の判定・個別条件・独立影響を示すテスト対の写像(ステップ 15) |
| `contracts/authz/operation-count-mapping.json` | **新設** — 要件の「7 操作」と `operation_ids`(8)の 1:N 写像(ステップ 19) |
| `contracts/authz/boundary-proposal.json` / `ddl-elements.json` / `oracle-seal.lock.json` | ステップ 20(裁定の反映・`scope` の消化・1 回の reseal)。**`frozen_value` は変えない** |
| `backend/src/pitchlog/authz/**` | **新設** — DDL 生成器・適用器・カタログ検査 |
| `backend/tests/db/**` | 4 ロール fixture の拡張・越境テスト・mutation ランナー |
| `scripts/check_authz_catalog.py` / `tests/test_check_authz_catalog.py` | 検査の追加・**status 契約の変更**・期待件数の撤去 |
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
**未登録は `backend/src/**`** で、これがステップ 22 の対象。

### 合格条件の書き方(3 つの規律)

1. **`[機械]`**(コマンドで判定できる)と **`[手動・外部]`**(人間が確認して worklog へ記録する)に
   **書き分ける**。**`[手動・外部]` を機械 green の一部として数えない**
2. **合格条件を「検査が green」に置かず「割り当てが正しい」に置く** — 検査は literal 一致で通るため、
   literal を置くだけで green にできる(7.3-3 が P1 と定める「文言は直したが実効がない」型)
3. **件数を定数で持たない**(`H-53`)— 母集合は資産から導出し、**ID 集合の sha256 で exact-set 突合**する

### 適用は**非原子**である(訂正 1)

`TX:PROVISIONING` は `atomic: false` の `ordered_application`。したがって:

- **失敗時の回復手段は「再適用で収束する」こと**であり、rollback ではない。`R-5` の失敗点 5 種は
  「注入後に再適用して最終状態が一致する」ことと、**注入位置が資産由来である**ことを要求する
- **原子性を要求するのは `TX:REPRESENTATIVE_MANAGEMENT`**(`authorization_and_side_effect`・`atomic: true`)。
  これはステップ 10 の管理経路 probe が担う(認可と副作用が同一トランザクション)
- `TX:GLOBAL_MUTATION_ISOLATION` も `atomic: false`(使い捨てクラスタの起動〜破棄)

### 自己 oracle 化を防ぐ順序(訂正 5)

**関数 body は資産の外に置く** — 検査器が `contains_sql_body is False` を要求するため
`ddl-elements.json` へは入れられない。`contracts/authz/function-bodies/**` を**先行コミット**で置き、
**その次のコミットで digest 検査と構造検査を置く**(第 1 群の `environment-expectations.json` が
`oracle_policy.expectations_must_precede_observation_code: true` で守っているのと同じ規律)。
**`function-bodies/**` は封印 6 資産に含まれないので oracle の再封印を発火させない。**

### oracle を触る点は 1 ステップだけ(訂正 2・3・4)

`oracle-seal.lock.json` の `ORACLE_STEP5_REREVIEW` は**封印 6 資産の canonical digest 全体**を封印し、
**追加でも発火する**。`boundary-proposal.json` と `ddl-elements.json` は**ともに封印対象**。
→ **ステップ 20 の 1 コミットで、資産 2 件の status 変更・検査器の契約変更・テスト期待値の追随・
`--reseal-oracle` を一度に行う。** `oracle_commit` は**更新しない**(意味が固定されている)。
**再レビューの周回は 3 周を目安**とし、超えたら PO 裁定を起動する(7.3-6 の 6 周警告に倣う)。

### 実機検証の実施主体

**CI が機械判定の主体**。`backend` ジョブに `postgres:17.11-bookworm` サービスと
`PITCHLOG_TEST_ADMIN_DSN` / `PITCHLOG_TEST_ROLE_DSN` が配線済みで、使い捨てクラスタは Docker CLI 経由なので
CI でも動く。**ローカル実行は再現手順として文書化する**(環境変数の実値の用意は人間の作業 — `NFR-014`・設計書 12.1。
実測: `docker compose config` が `POSTGRES_USER` 欠落で失敗・`psql` は未導入)。
**ソケット bind を伴う起動確認は委任先へ出せない**ので、そこは `[手動・外部]` に書き分ける(`H-79` 対応案 (b))。

### ステップ番号の規律(枝番を作らない・無記法のコード変更を作らない)

**総数が変わり得るため、ステップコミット件名には総数接尾辞 `/N` を付けず `(ステップ k)` のみを使う。**
分割で単位が増えた場合も**整数連番のまま振り直す計画改訂**で扱う。

**レビュー指摘の反映は、該当ステップの番号 + 付記で行う**(例 `(ステップ 5 レビュー反映 2 周目)`)。
**コードに触れる無記法コミットを作らない** — `feature_status.py` は `docs/` 配下と `.md` 以外の
無記法コミットを `implementation` に分類して進捗を不明にする(訂正 7)。

### 規模の申し送り

**`D-1`(全量)により本計画は 25 ステップになる。** コア領域なので全ステップに人間の逐行確認が掛かり、
**スループットの上限は逐行確認**である(TSK-317 のカード自身が「逐行確認は並列化できない人的資源」と警告)。
停滞した場合の**自然な分割点はステップ 18/19 の境界**(第 2 群の完了 = マージゲートの通過条件①が揃う点)。

### 詳細設計

DDL 生成器の入力契約・カタログ検査の検査 ID 一覧・変異軸と kill 判定の写像・4 ロール fixture の構造は
**[design.md](design.md) が正**。本書には複製しない(設計書 7.1-1)。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

> **見出しに「実装ステップ」を含めるのは機構要件**。`.claude/scripts/codex_run.py` はステップ表を
> **見出しスタックで判定する**ため、小見出しは本見出しの配下に置くこと(祖先に「実装ステップ」があれば射程内)。

#### 実装ステップ — 第 2 群: 実機検証(1〜18)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **関数 body と DDL の SQL 実体を新設資産として置く**(先行コミット)— `contracts/authz/function-bodies/**`。読み取り関数は **`LANGUAGE SQL BEGIN ATOMIC`** に限定し、**動的 SQL を含まない**。**このコミットには検査を含めない**(`R-1`) | `[機械]` `ddl-elements.json` の `functions` 3 件・`tables` 6 件・`policies` 6 件・`roles` 7 件の**全 ID に対応する SQL がある**(ID 集合の sha256 で exact-set)・**`EXECUTE`/`format(`/文字列連結による動的 SQL が 0 件**・**`contains_sql_body: false` を変えていない**。`[手動・外部]` **body が `dependency_table_ids` 以外の relation を参照していない**ことを逐行で確認した |
| 2 | **DDL 生成器**(資産 + body → 実行可能な SQL)— psycopg 直書き(`D-3`)。**資産以外の識別子定数を持たない** | `[機械]` **資産を参照しない識別子リテラルが 0 件**・**負例: 資産から 1 要素を削ると生成物が変わる**(全要素で確認)・生成物が `force_rls` / `public_execute: false` / `search_path` 末尾 `pg_temp` を落とさない |
| 3 | **DDL 適用器** — `provisioning_claim.ordered_steps` 5 件(`PROVISION-01-CREATE-OWNER`〜`PROVISION-05-CLOSE-SET-PATH`)の**順序を資産から読んで実行**する。**`TX:PROVISIONING` は `atomic: false`** なので、**冪等な再適用が回復手段**(訂正 1) | `[機械]` 空クラスタへ 2 回適用してカタログが一致(冪等)・**古い直接 `GRANT` が 1 回目と 2 回目の双方で消えている**・**順序が資産由来**(コード上の並びを入れ替えても資産どおり実行される)・**負例: 手順 2 を手順 3 の後ろへ移すと適用そのものが失敗する**・**負例: 手順 5 の `REVOKE` を省略すると `pg_has_role(...,'SET')` が true のまま残り red**(`R-8`) |
| 4 | **4 ロール実接続 fixture** — `table_owner` / `app_role` / `management_caller` / `outsider_role`。**`SET ROLE` を使わない**。各テストの冒頭で `session_user` / `current_user` を照合 | `[機械]` 4 本すべてが別ユーザーで接続する・`tests/test_ci_wiring.py` の `assert "SET ROLE" not in conftest` が維持される・**照合を外すと red**・`requires_db` の 0 件収集 / 0 件実行ガードが維持される・DSN 未設定は skip ではなく fail・**新設 DSN 名を期待値資産へ先に固定してから配線した**(commit 順序で示す) |
| 5 | **カタログ検査(構成そのもの)** — `pg_policy` の 5 属性を正規化して exact 比較 / **ステップ 1 で凍結した body の digest との照合**(`pg_get_functiondef`・owner・language・security・volatility・leakproof・strict・parallel・`proconfig`・ACL の 10 属性 — `R-1`)/ **危険終点 = `rolsuper OR rolbypassrls OR 保護 relation/schema/routine の owner` と `SET` 到達集合の交差が空**(`R-2`。`SET` 到達と `USAGE` 到達を分ける)/ 列 ACL・schema ACL・default ACL / `search_path` 末尾 `pg_temp` が 1 回 / `CATALOG:PROVISIONER-CANNOT-SET-OWNER`・`-USE-OWNER`(`R-8`)/ **`BYPASSRLS` ロールが所有する全 object と全 `SECURITY DEFINER` routine が exact-set** | `[機械]` **負例 8 種で red**: 既存関数の body へ禁止 relation の **SELECT** を追加 / 同 **DML** を追加 / body に動的 SQL を導入 / superuser への間接所属 / 表 owner への所属 / アプリ自身の `SUPERUSER` 化 / 採用構成外の関数が 1 件増える / `PUBLIC` の `EXECUTE` を残す。**digest は先行コミットの body を正とする**(検査と同一コミットで body を作らない)。`[手動・外部]` **`R-1`・`R-2`・`R-8` の各要求と検査 ID の対応表を worklog に置いた**(未対応 0 件) |
| 6 | **越境テスト(正例)** — `claim-mutant-map.json` の `positive_cases.cases` 6 件 | `[機械]` `http-route-matrix.json` の allow セルと**正例テスト ID が 1:1**(sha256 で exact-set)・**許可された行だけが返る**(全件返す実装では red)・**返却契約は凍結資産の読み**(`return_contract` = 認可済み業務行 / `aggregation_contract: none` = 関数内で集計しない)に従う。**正本 3-6 節の表現との差は TSK-348 が解消する**(`D-5`) |
| 7 | **越境テスト(拒否例)** — 常に 404 の 4 資源 / **対象側が非共有なら要求元が付与していても返らない** / `PUBLIC` が越境関数を実行できない / `search_path` の乗っ取りが効かない / アプリ用ロールが関数を経由せず他テナント行を読めない | `[機械]` 12-4 節の**最低要求 4 件がすべて実行可能なテストとして存在**・deny セルと 1:1・**`REJ-001`/`REJ-002`/`REJ-003` の各構成に戻すと red になる**・**常に 404 の 4 資源は「返す経路を持たない」**(関数のシグネチャに当該列が存在しないことを検査する。付与の値で分岐させない) |
| 8 | **6 前提 × 認可行列各行の越境テスト**(`data-model.md:544` の要求)— 6 前提を満たした要素それぞれについて、要求粒度の行を認可行列から引き **`相手の付与 ∧ 要求元の付与` の双方**を検査する。**選手個別は `kind = 'self'` かつ在籍区分 `active`**。**チーム集計には在籍フィルタを掛けない** | `[機械]` **6 前提 × 認可行列の許可行の直積のすべてにテスト ID がある**(母集合を資産から導出し sha256 で exact-set。**手動列挙にしない**)・**「対象側は非共有・要求元だけ付与」の組み合わせが必ず含まれる**・**前提 ⑤ の例外(自テナントは付与・相互性を適用しないが上限には数える)にテストがある**・**1 行落とすと red** |
| 9 | **書き込みの検証** — 表権限 **8 種**(`SELECT`/`INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`/`REFERENCES`/`TRIGGER`/`MAINTAIN` — `R-6`)× ロール。`table_privilege_probe_matrix` 8 行。**共有行は SELECT のみ正例・全 DML は拒否** | `[機械]` 8 種が**単一の機械可読集合から**カタログ検査・実行行列・mutation へ生成されている・**「6 権限」という記述が 0 件**・`table_privilege_probe_matrix` と exact-set・**1 権限を落とすと red** |
| 10 | **管理経路の代表 probe 1 件** — `representative_management_probe`。**呼び出しロールに基表 DML が無い** + **`TX:REPRESENTATIVE_MANAGEMENT` の `atomic: true` に従い認可と副作用が同一トランザクション** | `[機械]` `management_caller` の `probe_management_effects` への直接アクセスが 8 権限すべてで deny・関数経由のみ成功・**副作用だけが commit される経路が無い**(認可失敗時に `probe_management_effects` の行が増えない)・**それ以上の管理操作を実装していない**(実装した操作の集合が資産と一致) |
| 11 | **TOCTOU の 2 接続試験**(`R-3`)— 認可確認の直後に barrier を置き、別トランザクションが認可状態を変える | `[機械]` **barrier を外すと red**・**認可行を lock するか認可条件を副作用 DML の同一文へ埋め込む**ことで linearization point が一意であることを示す・`VOLATILE` 関数が内部クエリごとに新しい snapshot を取る前提を試験が明示する |
| 12 | **失敗点 5 種の注入**(`R-5`)— ロール作成後 / policy 変更後 / body 置換後 / owner 変更後 / ACL 正規化途中。**非原子なので「再適用で収束する」ことを要求する**(訂正 1) | `[機械]` 5 点それぞれで注入したのち**再適用して全対象 catalog・membership・default ACL・fixture data が正常適用時と一致**・**注入位置が資産から導出されている**(最初の文より前に失敗させるだけでは合格しない)・**注入後に再適用しない場合の状態も記録される**(隠さない) |
| 13 | **信頼境界の残余リスク試験** — **アプリ用実接続から `set_config()` で他テナント ID を設定できる**ことを試験し、結果を残余リスクとして記録する(隠さない) | `[機械]` 試験が存在し**「設定できてしまう」ことを期待値として持つ**(将来塞がれたら red になる)。`[手動・外部]` 残余リスクを worklog へ**申し送り先つき**で記録した(トークン → GUC の結合の検証は TSK-217) |
| 14 | **mutation ランナーと kill 判定 5 条件** — `KILL-01-TARGETED-CATALOG-DELTA` / `KILL-02-TEST-EXECUTED` / `KILL-03-EXPECTED-FAILURE` / `KILL-04-NO-FIXTURE-FAILURE` / `KILL-05-GLOBAL-STATE-ISOLATION`(**使い捨てクラスタ**) | `[機械]` 5 条件が資産から導出されている・**`KILL-01` の負例(宣言外の属性も変える変異)で kill と数えない**・**`KILL-04` の負例(setup 失敗を kill に数える)で red**・**`KILL-05` の負例(共有クラスタでロール属性を変異させる)で red**・**変異ごとに新しい DB を作る**(製品適用器を巻き戻し装置にしない) |
| 15 | **MC/DC の写像を新設**(`contracts/authz/mcdc-map.json`)— 凍結資産には `AND`/`OR`/`NOT`/`CASE` の**判定形の名前しかない**ため、**判定・個別条件・独立影響を示すテスト対**を本タスクで作る | `[機械]` 各判定について**個別条件の一覧**と**独立影響を示すテスト対**がある・**テスト対の片方を落とすと当該条件の MC/DC が未達と判定される**・写像が `mcdc_decision_forms` の全判定形を覆う(exact-set)。`[手動・外部]` 判定の抽出が関数本体とポリシー述語の実体と一致している |
| 16 | **変異の全量実行** — 231 変異(`authorization_predicate` 205 / `configuration` 24 / `r8_provisioning` 2) | `[機械]` **非等価変異の生存 0**・変異集合が資産から導出され**件数を定数で持たない**(sha256 で exact-set)・等価変異は人手判定で分母から除外し**除外の記録がある**。`[手動・外部]` 等価判定の根拠を変異ごとに記録した |
| 17 | **2 因子相互作用 276 件 + 最小 cut set 24 件 + MC/DC の実行** | `[機械]` 276 件と 24 件が資産と exact-set・**ステップ 15 の写像に対して MC/DC を満たす**・**1 相互作用を落とすと red**・**cut set の 1 要素を落とすと red** |
| 18 | **enforcement テストの実在化** — `auth-catalog.json` の 187 entries を `planned` → `implemented`。**`layer` / `db_basis_rule_id` と assertion の結合を機械で縛る** | `[機械]` 187 件すべての `enforcement_test_owner.id` が `collect_pytest_node_ids` に実在する・**各 entry の `db_basis_rule_id` に対応する述語が当該テストの assertion に現れる**(5 規則 × 判定関数の写像を持つ)・**負例: ある entry のテストを常時成功にすると red**・**負例: `db_basis_rule_id` を別の規則へ入れ替えると red**・`planned` 残 0 件 |

#### 実装ステップ — 第 3 群: 引き渡し(19〜25)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 19 | **要件の「7 操作」と `operation_ids`(8)の 1:N 写像を新設**(`contracts/authz/operation-count-mapping.json` — `D-4`)。**前提条件の差つき**で持つ | `[機械]` 要件側の 7 単位と資産側の 8 ID が**漏れなく双方向に対応**(差集合 0)・`issue_invitation` = `participant_capacity` / `revoke_invitation` = `invitation_active` が写像に現れる・**「7 操作」という件数の主張を資産に書いていない**・**8 ID の側を件数リテラルで持たない**。`[手動・外部]` 要件書の 3 箇所(`FR-041` の許可リスト・制御資源の認可・`NFR-010` の管理者操作のスコープ)との対応を確認した |
| 20 | **裁定の反映・`scope` の消化・検査器の契約変更・1 回だけの reseal**(`D-4`・訂正 2・3・4)— `boundary-proposal.json` の `pending_human_reviews` 2 件を裁定済みへ / `ddl-elements.json` の `scope` を通った構成へ / **`check_authz_catalog.py` の status ハード要求を同一コミットで改訂** / `tests/test_check_authz_catalog.py` の追随 / `--reseal-oracle` を **1 回** | `[機械]` `frozen_value` の差分が 0(`8` と `29` のまま)・**`oracle_commit` の差分が 0**(意味が固定されている)・reseal 後に `check_authz_catalog.py` が rc=0・**`--reseal-oracle` なしでは差分が出ない**(通常検証で reseal されない)・**負例: 検査器を改訂せず資産だけ変えると `CatalogError`**・**reseal は本ステップで 1 回だけ**(以降のステップで封印 6 資産を触らない)。`[手動・外部]` **`ORACLE_STEP5_REREVIEW` の差分敵対レビューと人間査読を通した**(`reseal_policy.human_review_required: true`) |
| 21 | **引き渡し 3 資産の確定** — **対象は `contracts/authz/ddl-elements.json`(通った構成)・`auth-catalog.json`(`AUTH-*` の母集合)・`rejected-configs.json`(不採用構成)の 3 ファイル**。スキーマ版・安定 ID・共通正規化 ID・元 commit・blob digest を持たせる | `[機械]` **3 資産のパスが資産側に明記されている**(任意の 3 ファイルで条件を満たせない)・`git_blob_digest` で照合が通る・**`AUTH-*` の ID 集合の sha256 を持つ**(受け手が件数を数え直さずに突合できる)・**1 資産を差し替えると red** |
| 22 | **`core-areas.json` へ新設パスを登録**(6.3 規則⑤)+ `tests/test_core_guard.py` の発火試験 | `[機械]` `scripts/core_guard.py` の `matched_paths` が `backend/src/pitchlog/authz/*`・`contracts/authz/function-bodies/*` ほか新設パスにマッチ・`uv run pytest tests/test_core_guard.py` green・**登録を外すと発火しないことを負例で示す**。`[手動・外部]` **paths 追加の敵対レビュー + 人間承認**(逐行確認は PR 作成者以外) |
| 23 | **`tests/test_ci_wiring.py` の追記** — 使い捨てクラスタの配線と新設 DSN を固定する。**設計書 10.1 は射程外**(TSK-343 — 訂正 6) | `[機械]` `uv run pytest tests/test_ci_wiring.py` green・**pytest の実行回数が 1 のまま**・`-m` を含むコマンドが 0 件・**`docs/development/dev-harness-design-2026-08-07.md` の差分が 0** |
| 24 | **期待件数のハードコード撤去** — `tests/test_check_authz_catalog.py` の**既存 20 箇所すべて**と本タスクの新設分を**資産由来の導出**へ(`H-85` 対応案③。**追随は独立コミット** — 対応案①) | `[機械]` **`tests/test_check_authz_catalog.py` と本タスクの新設テストに件数リテラルが 0 件**(数値リテラルの機械検出。閾値や添字は許可リストで明示)・**資産を 1 要素増やすとテストが自動追随する**(実際に増やして確認)。`[手動・外部]` 許可リストに入れた数値とその理由を記録した |
| 25 | **成果物の敵対レビューの採否記録** — 対象 = 適用器・カタログ検査・越境テスト・mutation・引き渡し 3 資産。**指摘の反映は該当ステップ番号 + 付記のコミットで行う**(例 `(ステップ 5 レビュー反映 2 周目)`)。**本ステップは worklog だけを変更する**(訂正 7) | `[機械]` 最終周 P0/P1 = 0 で収束したことが worklog に記録されている・**本ステップのコミットが `docs/` 配下のみを変更している**(現在地導出を壊さない)。`[手動・外部]` 採否記録が worklog に周ごとにある(**指摘ゼロの周も採否記録を残す**) |

## 5. DoD(受け入れ基準)

- [ ] **関数 body と DDL の SQL 実体が先行コミットで固定され、検査が後続コミットに置かれている**(自己 oracle 化を防いだ)
- [ ] **読み取り関数が `LANGUAGE SQL BEGIN ATOMIC` に限定され、動的 SQL が 0 件**(`R-1`)
- [ ] **DDL 生成器が資産を単一の入力としている**(資産を参照しない識別子リテラル 0 件)
- [ ] **DDL 適用器が `ordered_steps` の順序を資産から読み、冪等で収束する**。**`atomic: false` の前提で書かれている**
- [ ] **4 ロールの実接続の行列がある**(`SET ROLE` の模擬を使っていない・各テストで `session_user` を照合)
- [ ] **カタログ検査が `R-1`・`R-2`・`R-8` の要求を満たし、負例 8 種で red になる**
- [ ] **12-4 節の越境テスト最低要求 4 件と、`data-model.md:544` の「6 前提 × 認可行列各行」が機械条件として存在する**(手動列挙にしていない)
- [ ] **「常に 404 の 4 資源」が「返す経路を持たない」形になっている**(付与の値で分岐させていない)
- [ ] **表権限 8 種が単一の機械可読集合から生成されている**(「6 権限」の記述が 0 件)
- [ ] **`TX:REPRESENTATIVE_MANAGEMENT` の原子性・TOCTOU・失敗点 5 種・信頼境界の残余リスク試験がある**
- [ ] **MC/DC の判定・個別条件・独立影響の写像を新設した**(凍結資産には判定形の名前しかなかった)
- [ ] **231 変異・276 相互作用・最小 cut set 24・MC/DC を実行し、非等価変異の生存が 0 件**。**件数を定数で持っていない**
- [ ] **`auth-catalog.json` の 187 件が `implemented` で、`db_basis_rule_id` と assertion の結合が機械で縛られている**(常時成功テストでは通らない)
- [ ] **要件の「7 操作」と `operation_ids`(8)の 1:N 写像を新設した**(`D-4`)
- [ ] **oracle の裁定・`scope` の消化・検査器の契約変更・reseal を 1 コミットで行い、reseal は 1 回だけ**。`frozen_value` と `oracle_commit` の差分が 0
- [ ] **引き渡し 3 資産のパスが資産側に明記され、`AUTH-*` の ID 集合 sha256 で受け手が突合できる**
- [ ] **`core-areas.json` へ新設パスを登録した**(6.3 規則⑤の敵対レビュー + 人間承認)
- [ ] **設計書 10.1 と `data-model.md` の差分が 0**(それぞれ TSK-343・TSK-348 の所有 — 訂正 6・`D-5`)
- [ ] **`tests/test_check_authz_catalog.py` の期待件数ハードコードを既存 20 箇所すべて撤去した**
- [ ] **本タスクの成果を「`NFR-010` 適合」と主張していない**。HTTP 経路の判定は TSK-217 へ送った
- [ ] **mutation を `NFR-019` のテスト種別として計上せず、`NFR-018`(b)② を根拠に引いていない**(6 節)
- [ ] **コードに触れる無記法コミットが 0 件**(現在地導出が「不明」に落ちていない)
- [ ] **申し送りを起票した** — ADR-003 `D-12` と `contracts/authz/` / アプリ用ロールの `DELETE` / `H-57` のジョブ行 / `closure-handoff-data-model.json` の「作成」と正本の「作成・実行」の差
- [ ] **TSK-348・TSK-349・TSK-343・TSK-344 と相互リンクした**
- [ ] **`[手動・外部]` の全項目について、逐項の証跡を worklog に残した**
- [ ] **コア領域として敵対レビュー + 人間の逐行確認を通っている**(逐行確認は **PR 作成者以外**が行い、**実施記録行を確認者本人が記入**した)

## 6. テスト計画(NFR-019)

**要件が定義する CI のテストは 4 種**((a) 一致性 /(b) 越境 /(c) E2E 主要分岐 /(d) 同期故障系)。
**「単体」は `NFR-019` に存在しない** — `docs/development/templates/plan-template.md` の
「単体・一致性・越境・E2E・故障系」という 5 種の要約は誤りで、前計画書 6 節もこれを引いて誤帰属していた
(research.md 3-3 節)。本書は 4 種で書く。

| 種別 | 追加内容 |
| --- | --- |
| **(b) 越境アクセステスト** | ステップ 6〜10・13 — 正例 / 拒否例 / **6 前提 × 認可行列各行** / 書き込み 8 権限 / 管理経路 probe / 信頼境界。**DB レベルの「0 行 / 権限拒否」まで**で、`404` の判定と 13 組合せクラスの残り 12 は TSK-217 |
| **(a) 一致性 /(c) E2E /(d) 同期故障系** | **追加なし** |
| **構成検査(要件の 4 種に属さない — 設計判断)** | ステップ 5 のカタログ検査 / ステップ 3 の冪等性 / ステップ 11 の TOCTOU / ステップ 12 の失敗点。**`NFR-019` の種別として計上しない**(`data-model.md:239` が「越境テストとは別に構成そのものを検査する」と定める) |
| **mutation(要件の 4 種に属さない — 設計判断)** | ステップ 14〜17。**`NFR-018`(b)② を根拠に引かない** — 同項の対象列挙(状況判定・座標変換・捕球選手推定・成績集計の前処理・終了判定)に**認可構成は入っておらず**、実装判断で対象に加える規定もない。**「3 変異で必ず red」という件数にも要件典拠がない**(要件の閾値は「非等価変異の生存 0」) |
| **回帰(本物の資産)** | `test_repository_oracle_assets_are_valid` / `test_repository_derived_assets_are_valid` ほか既存 72 件が green のまま。**ステップ 20 より前は oracle のバイトが変わらない**ことを assert する |

**件数のハードコードは資産由来の導出へ置き換える**(ステップ 24)— 既存 20 箇所が過去に他タスクを
red にした連鎖(`H-85`)があるため、**既存分もすべて撤去する**(対応案③ の射程どおり)。

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

# 5. 正本へ触れていないこと(TSK-343 / TSK-348 の所有)
git -C "$WT" diff --exit-code origin/develop...HEAD -- docs/design/data-model.md docs/development/dev-harness-design-2026-08-07.md

# 6. 現在地導出(コードの無記法コミットが無いこと)
uv run python scripts/feature_status.py
```

**DB 必須テストの実行には `PITCHLOG_TEST_ADMIN_DSN` と `PITCHLOG_TEST_ROLE_DSN` の実値が必要**
(未設定は skip ではなく fail)。**ローカルでは人間が用意する**。CI では配線済み。

**人間が確認すること**: 関数 body が `dependency_table_ids` 以外を参照していないこと /
カタログ検査の検査 ID と `R-1`〜`R-8` の対応表 / 187 件の `db_basis_rule_id` と assertion の結合 /
MC/DC の判定抽出が実体と一致していること / oracle の reseal 差分 / `core-areas.json` の追加分。

## 8. 進め方

1. 本計画書 + [design.md](design.md) を**コア領域の敵対レビュー**へ:
   `python .claude/scripts/codex_run.py review adversarial -`
2. 指摘を反映(指摘反映を伴うレビュー 1 周ごとに frontmatter の `計画レビュー周回` を +1)
3. 収束したら**人間の承認**を求める → `承認: 済(YYYY-MM-DD・承認者)` へ
4. 承認後 `/implement` でステップ 1 から委任(1 委任 = 1 ステップ = 1 コミット・件名は `(ステップ k)`)
