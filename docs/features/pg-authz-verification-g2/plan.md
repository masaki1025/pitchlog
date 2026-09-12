---
feature: pg-authz-verification-g2
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2
branch: feature/pg-authz-verification-g2
created: 2026-09-09
計画レビュー周回: 16        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
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
**依存**: [TSK-348](https://app.notion.com/p/3d693b75e687816b8911f266f9bb59c5)(`data-model.md` v0.2 の改訂ゲート)
**— 実装は並行して進めるが、`TSK-348` のマージを本タスクのマージの前提とする**(DoD 項目。承認済み正本と製品マージゲートが矛盾した期間を作らない — 計画レビュー 2 周目 `P1-12`)
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

### PO 裁定(2026-09-09 取得済み — 第 1 弾)

| # | 論点 | 裁定 |
| --- | --- | --- |
| **D-1** | 第 2 群の射程 | **凍結資産の全量をやる** — 187 enforcement + 231 変異 + 276 相互作用 + MC/DC。cut set だけに絞らない |
| **D-3** | DDL 適用器の実装手段 | **psycopg 直書き**。TSK-343 を待たない(`tests/test_ci_wiring.py:1272` に触れない) |
| **D-4** | oracle の裁定待ち 2 件 | **frozen 値を確定として承認** — 管理コマンド **8**・`SCOPE:ALL_LOGICAL` **29**。要件書の「7 操作」との **1:N 写像を明示**して食い違いを解消する |
| **D-5** | 正本側の未処理 3 件(`search_path` の P0 / 返却契約の不一致 / 定義の言い換えによる重複) | **[TSK-348](https://app.notion.com/p/3d693b75e687816b8911f266f9bb59c5) として v0.2 の改訂ゲートを 1 本立てる**。**本タスクの射程外**。本タスクは正しい値(`pg_temp` 末尾明示・認可済み業務行を返す)を前提に進む |
| **D-6** | 187 件の enforcement の実在化と oracle の封印の衝突 | **ステップ 22 へ統合する** — `auth-catalog.json` は seal の `input_assets` で、検査器が **`oracle_commit` 上の blob との一致まで**要求する。status を動かすには **`oracle_commit` の前進**が必要。**入力資産の変更・封印資産の変更・`oracle_commit` の前進・4 種の reseal・検査器の契約変更を集約し、差分敵対レビューを 1 回だけ払う**。**ただしコミット構造は `S-1` が置き換える**(2 段の基準コミット方式 — `oracle_commit` に自コミットの SHA は入れられないため 1 コミットでは構築不能。4 周目 `P1-8`) |
| **D-8** | 計画レビューが収束しない(**前周修正起因が 2 周連続で過半** — 7.3-6 の発火) | **第 2 群をさらに分割する** — **ステップ 1〜21(実体を作る)を本計画の承認範囲**とし、**引き渡しと封印(旧 21〜27)は実測後の計画改訂 3 で確定する**。TSK-270 が 3 周否決後に取ったのと同じ形(人間の裁定 2026-08-31)。**根本原因**: 第 1 群が凍結した oracle には第 2 群が必要とする母集合(関数 body・MC/DC の判定・失敗注入点・要件の小項)が無く、第 2 群が自作すると自己申告になる。文書段階で閉じようとすると台帳 `H-68` の型に入る |
| **D-7** | 正本の「作成 → REVOKE → GRANT を分割しない」と凍結資産の 03/04 分割 | **適用器側で同一トランザクションに収める**。`TX:PROVISIONING.atomic: false` は**5 ステップ全体**の話であり、部分原子性と矛盾しない。**資産も正本も変えない**。中間状態で `PUBLIC` が実行できないことを試験する |
| **D-9** | ステップ 17(`contract_only` の runtime テスト 152 件)の合格条件が凍結資産の定義と矛盾する | **ステップ 17 を表から撤去し `S-10` として改訂 3 へ送る**(2026-09-10・山田正輝)。**旧 18〜21 を 17〜20 へ連番で振り直し、総数を 20 とする**。根拠は 3 つで、① **`R-7` の原文**が「`contract_only` は schema-drift kill + **受取タスクの** runtime テスト ID を必須にする」と定め、**同じ行が「契約 lint を実副作用 kill として数える抜け道」を名指しで警戒している**(`../pg-authz-verification/plan.md:414`)② **`contract_only` の 165 行には `runtime_target` キーが存在しない**(`probe_executable` の 33 行は持つ)= **資産が runtime のターゲットを定義していない** ③ 157 件の理由コードは `route_universe_pending` で、**製品の HTTP 経路は存在せず本計画は `product_schema: false` を自ら宣言している**。**あわせて `S-9` の置換先を分割する**(一律 `TSK-317` 置換は**所有先が空白の claim を封印で固定する**)。**当初は 3 分割としたが、改訂 3 第 1 弾の敵対レビュー 1 周目 `P0-2` で `runtime_test_owner.id` の共有が判明したため撤回し、分割単位を `runtime_test_owner.id` とした**(具体は `S-9` を正とする)。**改訂 3 は本裁定の時点で開始する** — `feature_status.py:948-958` が完了ステップの欠番を `inconsistent` と判定するため、**17 を空けたまま 18〜21 を先行する経路が無い** | 
| **D-10** | 改訂 3 第 1 弾の敵対レビューが 2 周連続で否決し、**前周修正起因が過半**(7.3-6 の発火 — 2 周目は母集団 6 中 5 件がレビュアのラベルで起因) | **射程縮小**(2026-09-10・山田正輝)。**改訂 3 を 2 弾に分ける**: **第 1 弾(本改訂)= 機械的な作業のみ** — ステップ 17 の撤去・連番の振り直し・旧参照の除去・裁定と実測の記録。**第 2 弾 = `S-1`〜`S-10` の機械条件の確定**で、**ステップ 17〜20 の完了後に行う**。理由: 1〜2 周目の指摘が**「実体が無い段階で `S-*` の機械条件を紙の上で閉じようとすると無限後退する」に収束**しており、**裁定 `D-8` が既に診断した `H-68` の型**である(2 周目 `P1-6` の「CI の `fetch-depth` が浅く履歴検査を実行できない」は、**実装しないと分からない層**の典型)。**洗い出した論点は失わない** — `S-9` に確定済みの実測 4 件、`S-10` に確定すべき論点 9 件として記録した。**射程が変わったので次周は全文レビュー**(7.3-4) | 

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

### PO 裁定(2026-09-11〜12 取得済み — **改訂 3 第 2 弾**)

| # | 論点 | 裁定 |
| --- | --- | --- |
| **D-11** | `SHARED-AUTHORIZED-ROWS` の `aggregation_owner_task_id` | **新タスクへ移す**(起票済み — 下記)。**要件書の改訂は不要**((β)④ として既に列挙済み) |
| **D-12** | `deferred_equivalence_contract.owner_task_id` | **D-11 と同じ新タスクへ** |
| **D-13** | `guard_paths` の登録基準 | **規則で決める** — 「**凍結資産またはコア領域の成果物を検査する検査器とその対**」。**当面は規則から導いた 10 本を列挙で登録し、機械化は別タスクへ送る** |
| **D-14** | **改訂 3 第 2 弾の射程**(2026-09-12) | **2 本に分ける** — **本改訂(PR #2)= 封印系**(`S-1` の一部・`S-5`・`S-7` + owner 移管 + `S-8` の一部 — **`S-9` は裁定 `D-15` で PR #3 へ移した**)/ **PR #3 = ID 解決と受取契約**(`S-2`・`S-3`・`S-4`・`S-6`・`S-9`・`S-10` と **`S-8` のうち引き渡し 3 資産のパス・`test_ci_wiring.py` の追記** — **`S-9` は裁定 `D-15` で追加**)。**理由**: 後者は**受取タスクの DoD へ書き込む必要があり、先方が未着手**である。**分ければ本改訂は実測だけで閉じられる** |
| **D-15** | **`S-9`(受取先 178 件)の射程**(2026-09-12) | **丸ごと PR #3 へ送る** — **`contract_only` 158 行は `contract_only_reason_code: route_universe_pending`**、すなわち**経路の母集合が未確定だから受取先が決まっていない行**である。**受取タスクの名も「受取先を決める」であり、決める前の状態を確定所有者として封印することになる**(計画レビュー 3・4 周目が 2 周続けて `P0` 指摘)。**`D-14` の「受取タスクが未着手なら PR #3」と同じ理由で一貫する。****本改訂が触る封印資産は `boundary-proposal.json` と `ddl-elements.json` の 2 本になる** |
| **D-16** | **期待件数のハードコード撤去(旧 3 ステップ構成のステップ 1)の射程**(2026-09-12) | **別タスクへ送る**([起票済み](https://app.notion.com/p/3d993b75e68781578e53d7a2268aded7))。**理由**: **構文的な走査で「ハードコードが無い」を閉じることはできない**。**計画レビュー 4・5・6 周目が 3 周連続で抜け道を指摘した**(コンテナリテラルの中の値 → 文字列・変数への退避 → **1 桁の文字列化と出現の置換**)。**性質が意味的なので、新タスクでは「走査で閉じる」をやめ、『資産を 1 要素増やした fixture でテストの期待値が追随する』を変異で確かめる設計で起こす。****本改訂とは独立**(実測 — **ステップ 3 が変えるのは `S-5` の status 文字列と `S-7` の scope 値で、件数ではない**)。**本改訂は 3 → 2 ステップになる** |
| — | `CONTROL-READS` の `aggregation_owner_task_id` | **裁定不要・事実の是正**(`aggregation_location: none` なのに owner がある資産の欠陥) |

**起票済みの受取タスク**:

- **`D-11`/`D-12` の受取先**: 「FR-041 共有集計の対象別生成と等価性契約」(`3d993b75-e687-818d-8cb8-ec57508e73e0`)
- **`contract_only` 158 行の受取先**: 「contract_only 158 行の runtime テスト受取先を決める」(`3d993b75-e687-8144-bd42-ee08d678b68f`)— **PR #3 の射程**

#### `D-13` の規則を実測へ当てた結果(2026-09-12・TSK-343 マージ後)

| 判定 | 検査器 | 凍結資産を読む | コア領域該当 |
| --- | --- | --- | --- |
| **登録** | `check_authz_catalog` / `check_authz_function_bodies` / `check_mcdc_map` / `check_failure_injection_points` / `check_shared_preconditions` | **はい** | 1〜5 領域 |
| 対象外 | `check_nfr021_append_only` / `check_docs_status` / `check_doc_profiles` / `check_plan_docs_sync` | **いいえ** | **なし** |

**5 検査器 + その対 5 本 = 10 本**。**規則を人手で解釈せず機械で当てられた。**

#### **`S-1` ④ の記録を撤回する**(2026-09-12)

**worklog に「`oracle_commit` は seal に存在しない」と記録したが誤りである。**
**原典**: `oracle-seal.lock.json:4` に**トップレベルの `oracle_commit`**(`dd2cb92...`)があり、**`check_authz_catalog.py:4521-4529` が 6 資産の `oracle_context.oracle_commit` との一致を要求**する。
**誤った理由**: **存在しない入れ子 `seal["oracle_context"]["oracle_commit"]` を見て `None` を得た**。**探す場所を人が選んで外した実測である。**
**本節の `S-1` は最初から正しい。**

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

### 計画レビュー 2 周目で訂正した前提(実測)

| # | 当初の記述 | 実測による訂正 |
| --- | --- | --- |
| 8 | ステップ 18(187 件の status 変更)は封印に触らない | **触る。** `auth-catalog.json` は seal の **`input_assets`**。検査器は ① 現在のファイルの `git_blob_digest` が seal と一致 ② **`git rev-parse <oracle_commit>:<path>` の blob も一致**の 2 段を要求する。実測で 4 つの入力資産すべてが `oracle_commit`(`dd2cb92`)の blob と**バイト一致**。**status を動かすには `oracle_commit` の前進が必要**(裁定 `D-6`) |
| 9 | 正本の同一トランザクション要求は満たせている | **満たせていない。** 正本 3-2 節は「**作成 → REVOKE → GRANT を分割しない**(その隙間で `PUBLIC` が実行できる)」と定めるが、資産は `PROVISION-03-ASSIGN-OBJECTS` と `PROVISION-04-CLOSE-FUNCTION-ACL` に**分割**している。**適用器がコミット境界を決める**(裁定 `D-7`) |
| 10 | 引き渡しの母集合は **`AUTH-*`** | **実在しない。** `auth-catalog.json` の `catalog_entry_id` は**全 187 件が `CATALOG:*`**(`AUTH-` は 0 件)。TSK-250 の計画書が `AUTH-*` を期待しているのに資産は `CATALOG:*` で、**受け渡し契約の ID 体系が食い違っている**(申し送り) |
| 11 | `R-4` の受取先は `TSK-250.*` | **実データは 3 系統。** `contract_only` 165 件のうち **158 件の `receiving_task_id` は `TSK-270-GROUP-2`(= プレースホルダ。**裁定 `D-9` で本タスクの所有ではなくなった** — `S-9`・`S-10`)**・7 件が `TSK-217`。別枠で `TSK-250.runtime.*` 13 件 + `TSK-250.management.*` 8 件。~~**158 件は本タスクが runtime テストを持つ**(外部への受け渡しではない)~~ — **裁定 `D-9`(2026-09-10)で撤回した。**`R-7` が `contract_only` の runtime テストを**受取タスクの所有**と定めており、**本タスクは実テストを書かない**(`S-10`)|
| 12 | 失敗注入点 5 種は「資産由来」 | **資産に列が無い。** 実資産にあるのは 3 つの `transaction_boundaries` と 5 個の `ordered_steps` と完了時検査だけ。**失敗点の資産を新設する**(ステップ 13) |
| 13 | 6 前提は資産から導出できる | **できない。** 資産の `precondition_ids`(6 個)は**管理操作用の別概念**(`tenant_active`・`group_active`・`active_membership`・`participant_capacity`・`invitation_active`・`preserve_active_admin`)。共有関数の 6 前提は正本 3-6 節の別の列挙。**母集合を独立ステップで新設する**(ステップ 8。テストと同時に作らない) |
| 14 | 4 ロールの DSN を期待値資産へ追加する | **増やさない。** 既存 `PITCHLOG_TEST_ROLE_DSN` を**テンプレート**として使い、user とパスワードをロールごとに差し替える。`tests/test_ci_wiring.py` が既に「ロール DSN はユーザーだけ異なり host/db は同一」を検査しており、この形が想定されている。**CI 配線の変更が不要になる** |

### 計画レビュー 3 周目で訂正した前提(実測)

| # | 当初の記述 | 実測による訂正 |
| --- | --- | --- |
| 15 | manifest を body と同一コミットに置き `source_commit` に**そのコミットの SHA** を入れる | **構築不能。** コミット SHA は manifest 自身の blob を含む tree から決まるので、自コミットの SHA をその内容へ埋め込めない。**body(ステップ 1)→ manifest + 静的照合(ステップ 2)の 2 コミットへ分ける** |
| 16 | `enforcement_test_owner.id` を `implemented` にすればよい | **必ず red になる。** 実測で全 187 件が `TSK-270.step4.<claim>.db` 形式で **`::` が 0 件**。検査器は `implemented` の ID を `pytest --collect-only` の node ID と完全一致させる(`catalog_test_owner` 側は実 node ID)。**論理 ID → node ID の解決方式を決める必要がある**(方式が分岐 — **改訂 3 へ送る**) |
| 17 | 要件側 7 単位は `req-universe.json` の安定 ID で参照する | **参照できない。** 実測で `req-universe.json` に `list_item` は **0 件**(条レベルの `FR-041` のみ)。小項 ID は `contracts/authz/requirement-claims.json` 側にある(**改訂 3 へ送る**) |
| 18 | 失敗注入点は `step_id` で参照すれば足りる | **足りない。** 「policy 変更後・body 置換後・owner 変更後」はいずれも `PROVISION-03` 内、「ACL 正規化途中」は `PROVISION-04` 内の位置。**5 行すべてに同じ `step_id` を書いても現在の条件を満たせる**。**閉じた `injection_point_id` 5 個 + 適用器が発行する `checkpoint_id` + 相互重複禁止 + 実行ログとの exact-set** が要る |
| 19 | MC/DC の判定 ID は `mcdc-map.json` で exact-set 固定すれば足りる | **自己申告のまま。** 判定 ID の母集合が同資産自身以外にない。**架空の 4 判定を置いても機械 green にできる**。→ **判定 ID を body 側の注記として持たせ、ステップ 1 の先行コミットで凍結する**(body 由来の集合と exact-set 一致を要求する) |

## 2. スコープ

### やること — 第 1 弾(**ステップ 1〜20・完了**)

> **PR #52 でマージ済み**(`67e06a2`・2026-09-10)。**本節は第 1 弾の記録であり、本改訂の承認範囲ではない。**

**裁定 `D-8` により、第 1 弾は「実体を作る」までを承認範囲とした。****本段落は第 1 弾の記録であり、本改訂(改訂 3 第 2 弾)の承認範囲は裁定 `D-14` の封印系(ステップ 1〜2)である(**裁定 `D-16` で期待件数の撤去を別タスクへ送り 3 → 2 ステップ**)。**

1. **関数 body と DDL の SQL 実体**(ステップ 1・先行コミット)+ **manifest と静的照合**(ステップ 2)
2. **DDL 生成器**(ステップ 3)/ **DDL 適用器**(ステップ 4 — 裁定 `D-7` のコミット境界)
3. **4 ロール実接続の行列**(ステップ 5 — 新しい DSN 環境変数を増やさない)
4. **カタログ検査**(ステップ 6 — `R-1`・`R-2`・`R-8`)
5. **越境テスト**(ステップ 7〜13・16 — 正例 / 拒否例 / 6 前提 × 認可行列各行 / 書き込み 8 権限 /
   管理経路 probe / TOCTOU / 信頼境界)。**`contract_only` 158 件は含まない** — 裁定 `D-9` で受取タスクへ移管した(`S-10`)
6. **新設する母集合資産 3 本** — 共有関数の 6 前提(ステップ 9)/ 失敗注入点(ステップ 14)/
   MC/DC の写像(ステップ 18)。**いずれも封印 6 資産の外**
7. **mutation の全量**(ステップ 17・19・20 — 231 変異 + 276 相互作用 + cut set 24 + MC/DC・kill 5 条件)

**封印資産・入力資産には一切触らない。** 検査の基準は **`origin/develop...HEAD` の差分**であり、
作業ツリーの未コミット差分ではない(4 周目 `P1-4` の訂正 — `git diff --exit-code contracts/authz/` は
コミット済みの変更を見逃す)。**対象は凍結 15 パスの列挙**で、承認範囲が新設する
`function-bodies/**` / `shared-preconditions.json` / `failure-injection-points.json` / `mcdc-map.json` は
**この 15 パスに含まれない**(ディレクトリ全体の差分 0 とは両立しないため、パスを列挙して判定する)。

```bash
git diff --exit-code origin/develop...HEAD -- \
  contracts/authz/requirement-claims.json contracts/authz/requirement-claims.lock.json \
  contracts/authz/route-registry.json contracts/authz/route-registry.lock.json \
  contracts/authz/auth-catalog.json contracts/authz/auth-catalog.lock.json \
  contracts/authz/http-route-matrix.json contracts/authz/http-route-matrix.lock.json \
  contracts/authz/ddl-elements.json contracts/authz/rejected-configs.json \
  contracts/authz/claim-mutant-map.json contracts/authz/attack-tree.json \
  contracts/authz/boundary-proposal.json contracts/authz/verification-evidence.json \
  contracts/authz/oracle-seal.lock.json
```

### やること — **第 2 弾(本改訂の承認範囲 = ステップ 1〜2)**

**裁定 `D-14` により封印系だけを射程とする。**
**触るのは封印資産 2 本**(`boundary-proposal.json` / `ddl-elements.json`)**と検査器・配線だけで、入力資産には一切触らない**(**裁定 `D-15` で `claim-mutant-map.json` を触る `S-9` が PR #3 へ移った**)。

#### ステップ番号は **1 から振り直す**(**実測で確定**)

**`feature_status.py` の走査範囲は `merge-base(origin/develop, HEAD)..HEAD`**(`:761` の `read_commits`)。**現在の merge-base は `9c4791a`** で、**develop は PR #52 を既に含む**ため、**その後のステップ記法コミットは 0 件**である(実測)。
**したがって 21 から始めると完了集合が `{21}` になり欠番判定で `inconsistent` になる。**
**1 から振り直すのが正しい。**

#### **2 段コミットは本改訂では不要**(**実測で確定**)

| 資産の区分 | 中身 | 本改訂が触るか |
| --- | --- | --- |
| **`input_assets`(8)** | `requirement-claims` / `route-registry` / **`auth-catalog`** / `http-route-matrix`(+ lock) | **触らない** |
| **`sealed_assets`(6)** | **`ddl-elements`** / `rejected-configs` / `claim-mutant-map` / `attack-tree` / **`boundary-proposal`** / `verification-evidence` | **2 本を触る**(`claim-mutant-map` は裁定 `D-15` で PR #3 へ) |

**`oracle_commit_semantics` は `last_committed_step_4_input_baseline`** —**入力の基準**を指す印である(`:4524` が literal を要求)。
**本改訂は入力資産を 1 つも変えないので `oracle_commit` は動かさない。**
**したがって `S-1` の 2 段コミットは不要**で、**`--reseal-oracle` を 1 回回せば足りる**(`_build_oracle_seal()` は **`input_assets[].git_blob_digest`(不変)と `sealed_assets[]` の再構築(変わる)だけ**を行う — 実測)。

**`S-1` の要求(reseal と人間査読)は本改訂で完結する。**
**PR #3 は `auth-catalog.json`(入力資産)を変えるため、その PR 自身で 2 段コミットを要する**が、**これは `S-1` の残部ではなく PR #3 の実装制約である**(**送り先表と DoD の「7 件」に `S-1` が無いのはこのため** — 4 周目 `P2-9`)。

#### PR #3 へ送るもの(**空手形にしないため受取先を明記する**)

| 要件 | 送り先 | 理由 |
| --- | --- | --- |
| **`S-9`**(`claim-mutant-map.json` の受取先 178 件) | **PR #3** | **裁定 `D-15`** — **`contract_only` 158 行は `route_universe_pending` で受取先が未確定**であり、**確定所有者として封印できない**。**`probe_executable` 20 件だけを切り出すと `TSK-270-GROUP-2` が 158 件残り、置換後に対象集合を再導出できなくなる**(4 周目 `P0-1` の実測 — 全 198 行のうち既存 `TSK-250` 13 / `TSK-217` 7 が同じ分類に混ざる) |
| `S-2`(論理 ID → node ID・187 + 310 参照・status 更新) | **PR #3** | **`auth-catalog.json`(入力資産)を変えるので 2 段コミットが要る** |
| `S-3`(要件側 7 単位の source) | **PR #3** | `S-2` と同じ資産の話 |
| `S-4`(引き渡しマニフェストの ID 完全性) | **PR #3** | `S-2` の結果に依存 |
| `S-6`(受取契約・read-back・製品 adapter の事前凍結) | **PR #3** | **受取タスク(TSK-250 / TSK-217)の DoD へ書き込む必要があり、先方が未着手** |
| `S-10`(`contract_only` 158 行の受取契約・9 論点) | **PR #3** | 同上(受取タスクは起票済み) |
| `S-8` のうち **3 資産のパスと版・digest** | **PR #3** | `S-4` の ID 完全性に依存 |

**PR #3 は本改訂のマージ後に、同じ計画書の改訂 4 として起こす。**

#### マージ順序(**PO 裁定 2026-09-12**)

```
TSK-348(済)→ TSK-317 PR #1(済)→ TSK-343(済)→ **TSK-317 PR #2**
  → TSK-355 → **TSK-317 PR #3** → TSK-235
```

**PR #3 は TSK-355 の後**である。**PR #3 は `auth-catalog.json`(入力資産)を変えて `oracle_commit` を前進させ、TSK-355 は要件書の改訂で `requirement-claims.json`(同じく入力資産)を動かす** — **同じ seal の入力側を両方が触る**ため、順序を決めないとどちらかが再封印をやり直す。

**裁定の根拠**: **TSK-355 の確定ゲートが最長区間**(同型の前例 TSK-278 で 27 周)で、**この順序なら PR #3 はその間に計画・実装を進められる**(待つのはマージだけ)。**逆順にすると 2 つの長い作業が直列になり、さらに TSK-355 の承認済み計画の改訂と再承認で人間の手番が 1 回増える。**

→ **PR #3 の計画は、TSK-355 マージ後の状態を前提として起こす**(`requirement-claims.json` の digest と `oracle_commit` が動いた後の版に乗る)。

#### 別タスクへ送るもの(**裁定 `D-16`**)

| 要件 | 送り先 | 理由 |
| --- | --- | --- |
| **`S-8` のうち期待件数のハードコード撤去** | **[authz テストの期待件数ハードコードを資産由来の導出へ置き換える](https://app.notion.com/p/3d993b75e68781578e53d7a2268aded7)** | **構文的な走査では閉じられない**(3 周連続で抜け道)。**変異で確かめる設計に建て直す必要があり、本改訂の封印作業とは独立している** |

**本改訂に残る `S-8` は `core-areas.json` への登録だけ**である。

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
| `.claude/core-areas.json` | **本改訂で変更する**(ステップ 1)— **`guard_paths` へ 10 本**・**`tenant-isolation.paths` へ 9 パターン**(4 節の表が正)。**第 1 弾では変更しなかった**(裁定 `D-10` で第 2 弾へ送っていた) | **6.3 規則⑤(敵対レビュー + 人間承認)— 本改訂で払う** |
| [`docs/development/harness-evaluation.md`](../../development/harness-evaluation.md) | **該当した。`## 候補` へ 7 件追記 + 既存候補 1 件へ実測補記**(**内訳**: **TSK-317 由来 4 件**(母集団の人手列挙 / DB テスト残骸の fail-closed / ジョブ横断の不変条件 / guard の部分一致誤検知)+ **TSK-355 由来 3 件**(順序の循環 / 成果物と許容差分のずれ / `H-68` 型の送り先が空手形)。**TSK-355 の 3 件は同タスクの依頼による代理提出**(先方の PR はマージ順序上いちばん最後で数週間先になるため。**TSK-235 とも同じ理由で分担を合意済み**))(**`H-*` の新規採番はしない・版は上げない**)。**新設候補 ①「母集団を人が列挙する検査は、射程が動くたびに黙って古くなる」**(本タスクの 6 周のレビューで 8 回・層を変えて再発。既存の `feature_status.py` allowlist とステップ表の集合差を同根として束ねた)/ **新設候補 ②「順序の付記に理由を書かないと、複数の承認済み計画に跨って循環を作る」**(TSK-317 / TSK-343 / TSK-355 / TSK-235 の 4 タスクが循環。TSK-355 の依頼で本 PR が代理提出)/ **既存候補「`H-85` の連鎖を実行する手順が無い」へ実測補記**(`--reseal` は `_validate_manifest` に先に止められて到達せず、`reseal_catalog()` は `input_manifest` を触らない。**3 フラグの fail-early が非対称** — `--reseal-oracle` だけが自分の seal 検査を明示的に飛ばす)。**TSK-355 の候補 3 件はすべて本 PR が代理提出した。** | PR レビュー(`H-*` の追記では版を上げない — 7.6-3 前段) |
| [`docs/design/data-model.md`](../../design/data-model.md) | **反映なし**(3 件の是正は **TSK-348**) | — |
| [`docs/development/dev-harness-design-2026-08-07.md`](../../development/dev-harness-design-2026-08-07.md) | **反映なし**(10.1 の追随は **TSK-343**) | — |
| `docs/requirements/**` / `docs/adr/**` / `docs/ops/**` / `frontend/**` | **反映なし** | — |

### 正本体系外だが同一 PR で運ぶもの(/pr 突合の別枠宣言)

| ファイル | 変更内容 |
| --- | --- |
| `contracts/authz/function-bodies/**`(SQL 実体) | **新設** — 関数 body と DDL の SQL 実体。**ステップ 1 の先行コミット**。判定に `-- DECISION:` 注記を置く。**封印 6 資産ではない** |
| `contracts/authz/function-bodies/manifest.json` | **新設** — **ステップ 2**。`source_commit`(ステップ 1 のコミット SHA)+ **body ファイルの `blob_digest`**。**manifest 自身は照合対象に含めない**(自己 digest を避ける — 4 周目 `P1-1`) |
| `contracts/authz/shared-preconditions.json` | **新設** — 共有関数の 6 前提の母集合(正本 3-6 節からの抽出規則 + 元文書 digest つき。**ステップ 9**) |
| `contracts/authz/failure-injection-points.json` | **新設** — `R-5` の失敗注入点 5 種(**ステップ 14**) |
| `contracts/authz/mcdc-map.json` | **新設** — MC/DC の判定・個別条件・独立影響のテスト対(**ステップ 18**) |
| `contracts/authz/operation-count-mapping.json` | **改訂 3 第 2 弾の射程**(`S-3`)— 要件の 7 単位と `operation_ids`(8)の 1:N 写像。**本計画では作らない** |
| `contracts/authz/handoff-manifest.json` | **改訂 3 第 2 弾の射程**(`S-4`)。**本計画では作らない** |
| `contracts/authz/` の**凍結 15 パス** | **第 1 弾では変更しなかった。本改訂は `boundary-proposal.json` / `ddl-elements.json` の 2 本と `oracle-seal.lock.json` を変更する**(`S-5`・`S-7`・`S-1`)。**残り 12 パスは不変**(**`claim-mutant-map.json` は裁定 `D-15` で PR #3 へ**) |
| `backend/src/pitchlog/authz/**` | **新設** — DDL 生成器・適用器・カタログ検査 |
| `backend/tests/db/authz/**` / `backend/tests/db/conftest.py` | 4 ロール fixture の拡張・越境テスト・mutation ランナー |
| `scripts/check_authz_catalog.py` / `tests/test_check_authz_catalog.py` | **この中央 2 ファイルへは新設資産の検査を追加しない**(**実装済みのステップ 2・9・14 は、それぞれ独立した `scripts/check_authz_function_bodies.py` / `check_shared_preconditions.py` / `check_failure_injection_points.py` と対になるテストを新設しており、中央 2 ファイルは変更していない** — 実測。`S-8` もこの独立 6 パスを前提にしている)。**残るステップ 18 の `mcdc-map.json` も同じ形で独立した検査器を新設する。****status 契約の変更(`S-2`)は PR #3。****期待件数の撤去は裁定 `D-16` で別タスクへ。****本改訂が触るのは `S-5`・`S-7` の literal 追随と、重複行で潰れる 5 配列の多重度検査(4 節 2-d の表)だけ**(いずれもステップ 2) |
| `tests/test_core_guard.py` | **本改訂のステップ 1 で変更する** — 新設パスの発火試験と `core-areas.json` への登録。**第 1 弾では変更しなかった**(裁定 `D-10`) |
| `backend/tests/db/test_authz_*.py` | **新設 12 本** — カタログ検査 / 越境の正例・拒否例 / 6 前提行列 / 表権限 8 種 / 管理経路 probe / TOCTOU / 失敗注入 / 信頼境界 / ロール接続 / 適用器 / mutation 全量。**`requires_db` マーカー付きで `backend/tests/db/` 配下**(`environment-expectations.json` の `required_path` 契約) |
| `backend/tests/test_authz_*.py` | **新設 5 本** — **DB を必要としない**契約試験(DDL 生成器 / mutation の判定機構 / executor の観測 / 2 因子合成 × 2)。**`backend/tests/db/` の外に置く**(DB 必須テストの path 契約と分けるため) |
| `scripts/check_shared_preconditions.py` / `check_failure_injection_points.py` / `check_mcdc_map.py` と、対になる `tests/test_check_*.py` | **新設 6 本** — 新設資産それぞれの独立した検査器(中央 2 ファイルへ足さない方針)。**`guard_paths` への登録は本改訂のステップ 2**(**中央 2 ファイルを含めて 10 本** — 裁定 `D-13` の規則を当てた実測) |
| `tests/test_check_authz_function_bodies.py` | **追随** — `manifest.json` の `source_commit` を注記追加後のコミットへ変えたため、「body 導入前のコミット」を `--diff-filter=A` で探す形へ変更(**assertion は不変・弱体化していない**) |
| `docs/features/pg-authz-verification-g2/{plan,research,design}.md` / `catalog-check-map.md` | feature 作業ディレクトリ(記録・正本ではない) |

## 4. 実装方針

### 重さ分類の根拠 — **コア領域(テナント分離)**

設計書 6.3 の境界定義表がテナント分離に「**テナント境界の認可判定すべて** = `FR-034` の認可行列・既定拒否を
中心に、`FR-033`/`FR-035`/`FR-037` の認可源・管理経路、`FR-041` の共有操作…+ `NFR-010` の越境防止」を含める。
本タスクの成果は**その認可判定の物理構成そのもの**である。
→ **`sol xhigh`・敵対レビュー必須・人間の逐行確認必須**(PR 作成者以外)。

**core-guard は発火する** — `contracts/authz/*`・`backend/tests/db/*`・`scripts/check_authz_catalog.py`・
`tests/test_check_authz_catalog.py`・`backend/pyproject.toml`・`backend/uv.lock`・`backend/*conftest.py`・
`docker-compose.yml` が `tenant-isolation.paths`(22 件)に登録済み(導入 `d4373ec`)。
**未登録は `backend/src/pitchlog/authz/*` と新設検査器 8 本**で、**本改訂のステップ 1 で登録する**(4 節の表が正)。**現在のステップ表は本改訂の 1〜2 である**(第 1 弾の 1〜20 は「第 1 弾の実施記録」へ移した)。

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
  これは**ステップ 12** の管理経路 probe が担う(認可と副作用が同一トランザクション)
- `TX:GLOBAL_MUTATION_ISOLATION` も `atomic: false`(使い捨てクラスタの起動〜破棄)

**ただしコミット境界は適用器が決める(裁定 `D-7`)** — 正本 3-2 節は
「**`REVOKE ALL ON FUNCTION ... FROM PUBLIC`** を関数作成と**同一トランザクション**で行い…
**作成 → REVOKE → GRANT を分割しない**(その隙間で `PUBLIC` が実行できる)」と定める。
資産は `PROVISION-03-ASSIGN-OBJECTS` と `PROVISION-04-CLOSE-FUNCTION-ACL` に分割しているが、
**`atomic: false` は 5 ステップ全体の話**であって部分原子性を禁じていない。

→ **適用器は「関数作成 → `REVOKE` → 名前付き `GRANT`」を 1 トランザクションに収める。**
**中間状態で `PUBLIC` が越境関数を実行できないことを試験する**(ステップ 4 の合格条件)。
`R-5` の失敗注入は**このトランザクション境界を跨がない位置**に置く。

### 自己 oracle 化を防ぐ順序(訂正 5)

**関数 body は資産の外に置く** — 検査器が `contains_sql_body is False` を要求するため
`ddl-elements.json` へは入れられない。`contracts/authz/function-bodies/**` を**先行コミット**で置き、
**その次のコミットで digest 検査と構造検査を置く**(第 1 群の `environment-expectations.json` が
`oracle_policy.expectations_must_precede_observation_code: true` で守っているのと同じ規律)。
**`function-bodies/**` は封印 6 資産に含まれないので oracle の再封印を発火させない。**

### oracle を触る点は 1 ステップだけ(訂正 2・3・4・8 / 裁定 `D-6`)

`oracle-seal.lock.json` は **2 種の資産**を縛る:

| 種別 | 資産 | 検査 |
| --- | --- | --- |
| `input_assets`(8) | `requirement-claims` / `route-registry` / **`auth-catalog`** / `http-route-matrix` の各 json と lock | ① 現在のファイルの `git_blob_digest` が seal と一致 ② **`git rev-parse <oracle_commit>:<path>` の blob も一致** |
| `sealed_assets`(6) | `ddl-elements` / `rejected-configs` / `claim-mutant-map` / `attack-tree` / **`boundary-proposal`** / `verification-evidence` | canonical digest 全体の一致 |

**実測(2026-09-09)**: 4 つの入力資産すべてが `oracle_commit`(`dd2cb92`)時点の blob と**バイト一致**しており、
`check_authz_catalog.py` は rc=0。したがって **`auth-catalog.json` の status を動かすと ② が必ず落ちる** —
reseal で digest を更新しても `oracle_commit` 上の blob は古いままである。`_build_oracle_seal` は
`oracle_commit` を触らないので、**前進は手動編集 + 6 沈黙資産の `oracle_context.oracle_commit` の同時更新**になる。
**前例がある** — `7987774`「oracle 6 資産の `oracle_commit` を入力確定コミットへ差し替え・seal 再封印」、
および `dd2cb92` 自身が「要件書 v2.7 への追随・reseal ①②」。

→ **上記は第 1 弾時点の見立てであり、本改訂の実測で置き換わった。**

**裁定 `D-6` は当時「ステップ 22 の 1 コミットへ集約する」とし、裁定 `D-10` で改訂 3 第 2 弾へ送った。**
**第 1 弾(ステップ 1〜20)では oracle を変更しなかった。**

**本改訂の実測(2026-09-12)**: **本改訂は `input_assets`(8)を 1 つも変えない**ため、
**上記の「`oracle_commit` の前進」も「2 段コミット」も要らない**(2 節の実測)。
**`sealed_assets` の 2 本だけが変わるので、`--reseal-oracle` を 1 回回せば seal は再構築できる**(**裁定 `D-15` で `claim-mutant-map` が PR #3 へ移り 3 本 → 2 本**)。
**したがって oracle を触る点は本改訂でも 1 ステップ(ステップ 2)だけである。**

**`oracle_commit` の前進と 2 段コミットは PR #3 の実装制約**であり(PR #3 は `auth-catalog.json` = 入力資産を変える)、**本改訂の射程ではない。**
**再レビューの周回は 3 周を目安**とし、超えたら PO 裁定を起動する(7.3-6 の 6 周警告に倣う)。

### 実機検証の実施主体

**CI が機械判定の主体**。`backend` ジョブに `postgres:17.11-bookworm` サービスと
`PITCHLOG_TEST_ADMIN_DSN` / `PITCHLOG_TEST_ROLE_DSN` が配線済みで、使い捨てクラスタは Docker CLI 経由なので
CI でも動く。**ローカル実行は再現手順として文書化する**(環境変数の実値の用意は人間の作業 — `NFR-014`・設計書 12.1。
実測: `docker compose config` が `POSTGRES_USER` 欠落で失敗・`psql` は未導入)。
**ソケット bind を伴う起動確認は委任先へ出せない**ので、そこは `[手動・外部]` に書き分ける(`H-79` 対応案 (b))。

**DSN は増やさない(訂正 14)** — 4 ロールそれぞれに環境変数を割り当てると CI と compose の両方へ配線が要る。
代わりに **既存 `PITCHLOG_TEST_ROLE_DSN` をテンプレートとして使い、user とパスワードをロールごとに差し替える**。
`tests/test_ci_wiring.py` が既に「**ロール DSN はユーザーだけ異なり host/db は同一**」を検査しており、
この形が想定されている。パスワードは管理接続の `CREATE ROLE ... LOGIN PASSWORD` で設定する
(既存 `tested_role_connection` と同じ手つき)。**期待値資産の `dsn_environment_variables` は変更しない。**

### ステップ番号の規律(枝番を作らない・無記法のコード変更を作らない)

**総数が変わり得るため、ステップコミット件名には総数接尾辞 `/N` を付けず `(ステップ k)` のみを使う。**
分割で単位が増えた場合も**整数連番のまま振り直す計画改訂**で扱う。

**レビュー指摘の反映は、該当ステップの番号 + 付記で行う**(例 `(ステップ 5 レビュー反映 2 周目)`)。
**コードに触れる無記法コミットを作らない** — `feature_status.py` は `docs/` 配下と `.md` 以外の
無記法コミットを `implementation` に分類して進捗を不明にする(訂正 7)。

### 規模の申し送り

**裁定 `D-8` と `D-9` により、第 1 弾の承認範囲は 20 ステップ(第 2 群前半)だった。****本改訂の承認範囲は 2 ステップ(封印系)である**(裁定 `D-14`・`D-16`)。**以下は第 1 弾についての記述である。** コア領域なので全ステップに人間の逐行確認が掛かり、
**スループットの上限は逐行確認**である(TSK-317 のカード自身が「逐行確認は並列化できない人的資源」と警告)。
**第 2 群後半・第 3 群は改訂 3 第 2 弾で確定する**(4 節の `S-1`〜`S-10`)。
マージゲートの通過条件①が揃うのは改訂 3 第 2 弾の完了時点である。

### 詳細設計

DDL 生成器の入力契約・カタログ検査の検査 ID 一覧・変異軸と kill 判定の写像・4 ロール fixture の構造は
**[design.md](design.md) が正**。本書には複製しない(設計書 7.1-1)。

### 第 1 弾の実施記録(ステップ 1〜20・PR #52 でマージ済み)

> **本節は記録であり、本改訂の承認範囲ではない。**
> **見出しに「実装ステップ」を含めない**のは機構要件である —
> `scripts/feature_status.py:439` と `.claude/scripts/codex_run.py:82` は
> **「実装ステップ」を含む見出しの配下にある番号行をすべて読む**ため、
> **本表を残したまま新表を置くと両方の番号が合算され、`inconsistent` になる**
> (4 周目 `P0-1` の実測 — `StepTable(valid=False, total=20, reason='実装ステップ表の番号が連番でない')`)。
> **機構が読むステップ表は下記「実装ステップ」節の 1 本だけである。**

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **関数 body と DDL の SQL 実体を新設**(先行コミット)— `contracts/authz/function-bodies/**`。読み取り関数は **`LANGUAGE SQL BEGIN ATOMIC`** に限定し**動的 SQL を含まない**。**認可判定に `-- DECISION: <id>` の注記を置く**(ステップ 18 の判定母集合になる)。**manifest も検査も置かない**(訂正 15)。**注記の網羅性は機械では閉じない** — 機械が閉じるのは「**body に無い判定 ID を `mcdc-map.json` へ書けない**」「**後から判定を減らせない**」の 2 点だけで、**最初から注記を漏らすことは人手逐行確認でしか捕まらない**(4 周目 `P1-2`) | `[機械]` `ddl-elements.json` の `functions` 3 / `tables` 6 / `policies` 6 / `roles` 7 の**全 ID に対応する SQL がある**(ID 集合の sha256 で exact-set)・**`EXECUTE`/`format(`/文字列連結が 0 件**・**`-- DECISION:` 注記の構文が妥当で ID が一意**(注記の**網羅性は機械では判定しない** — 5 周目 `P1-1`)・`contains_sql_body: false` を変えていない。`[手動・外部]` **body の全認可判定に注記が付いていることを逐行で確認**した(ステップ 18 の母集合になる)・**body が `dependency_table_ids` 以外の relation を参照していない**ことを逐行で確認した |
| 2 | **body manifest と静的照合**(訂正 15)— `contracts/authz/function-bodies/manifest.json` に `source_commit`(**ステップ 1 のコミット SHA**)と **body ファイルの `blob_digest`**。**manifest 自身は照合対象に含めない**(自己 digest を避ける — 4 周目 `P1-1`)。照合は **① 現ファイルの digest ② `git rev-parse <source_commit>:<path>` の blob** の 2 段 | `[機械]` manifest の `source_commit` が**ステップ 1 のコミットを指す**・**照合対象がステップ 1 の body ファイルと exact-set 一致**(manifest 自身を含まない)・2 段の照合が通る・**負例: body を本コミットで書き換えると ② が落ちる**・**負例: `source_commit` を本コミット自身にすると解決できず red**・**負例: 照合対象から body 1 件を外すと red** |
| 3 | **DDL 生成器**(資産 + body → 実行可能な SQL)— psycopg 直書き(`D-3`)。**入力 2 つ以外の識別子定数を持たない** | `[機械]` **資産を参照しない識別子リテラルが 0 件**・**負例: 資産から 1 要素を削ると生成物が変わる**(全要素で確認)・生成物が `force_rls` / `public_execute: false` / `search_path` 末尾 `pg_temp` を落とさない |
| 4 | **DDL 適用器** — `ordered_steps` 5 件の順序を**資産から読んで**実行。**関数作成 + `REVOKE ALL ... FROM PUBLIC` + 名前付き `GRANT` を 1 トランザクションに収める**(裁定 `D-7`)。**各文の実行位置に `checkpoint_id`(step_id + 序数)を発行して実行ログへ残す**(ステップ 14 の母集合になる) | `[機械]` 空クラスタへ 2 回適用してカタログが一致(冪等)・**古い直接 `GRANT` が 1 回目と 2 回目の双方で消えている**・**順序が資産由来**・**中間状態で `PUBLIC` が越境関数を実行できない**・**実行ログの `checkpoint_id` が一意で序数が連番**・**負例: 作成と `REVOKE` を別トランザクションに分けると red**・**負例: 手順 2 を手順 3 の後ろへ移すと適用そのものが失敗する**・**負例: 手順 5 の `REVOKE` を省略すると red**(`R-8`) |
| 5 | **4 ロール実接続 fixture** — `table_owner` / `app_role` / `management_caller` / `outsider_role`。**既存 `PITCHLOG_TEST_ROLE_DSN` をテンプレートに user とパスワードを差し替える**(訂正 14)。**`SET ROLE` を使わない** | `[機械]` 4 本すべてが別ユーザーで接続する・**`environment-expectations.json` の差分が 0**・`assert "SET ROLE" not in conftest` が維持される・`session_user`/`current_user` 照合を外すと red・`requires_db` の 0 件収集/0 件実行ガードが維持される |
| 6 | **カタログ検査(構成そのもの)** — `pg_policy` の 5 属性の exact 比較 / **ステップ 2 の manifest を期待値とする body digest の照合**(10 属性 — `R-1`)/ **`CATALOG:FUNCTION-STRUCTURE:*`**(`BEGIN ATOMIC` / 動的 SQL 0 件 / 参照 relation の限定)/ **危険終点と `SET` 到達集合の交差が空**(`R-2`。`SET` 到達と `USAGE` 到達を分ける)/ 列 ACL・schema ACL・default ACL / `search_path` 末尾 `pg_temp` が 1 回 / `CATALOG:PROVISIONER-*` 2 件(`R-8`)/ **`BYPASSRLS` ロール所有 object と全 `SECURITY DEFINER` routine が exact-set** | `[機械]` **負例 9 種で red**: body へ禁止 relation の SELECT 追加 / 同 DML 追加 / 動的 SQL 導入 / **body を後続コミットで差し替え** / superuser への間接所属 / 表 owner への所属 / アプリの `SUPERUSER` 化 / 採用構成外の関数が 1 件増える / `PUBLIC` の `EXECUTE` を残す。`[手動・外部]` **`R-1`・`R-2`・`R-8` の各要求と検査 ID の対応表を worklog に置いた**(未対応 0 件) |
| 7 | **越境テスト(正例)** — `positive_cases.cases` 6 件 | `[機械]` allow セルと**正例テスト ID が 1:1**(sha256 で exact-set)・**許可された行だけが返る**・**返却契約は凍結資産の読み**(`aggregation_contract: none`) |
| 8 | **越境テスト(拒否例)** — 常に 404 の 4 資源 / **対象側が非共有なら要求元が付与していても返らない** / `PUBLIC` が越境関数を実行できない / `search_path` の乗っ取りが効かない / 関数を経由しない他テナント行の読み取り | `[機械]` 12-4 節の**最低要求 4 件がすべて実行可能なテストとして存在**・deny セルと 1:1・**`REJ-001`/`REJ-002`/`REJ-003` の各構成に戻すと red**・**常に 404 の 4 資源は関数のシグネチャに当該列が存在しない** |
| 9 | **共有関数の 6 前提の母集合を新設**(`contracts/authz/shared-preconditions.json`)— 正本 3-6 節の列挙から**抽出規則 + 元文書 blob digest つき**で作る。**テストはこのステップで書かない** | `[機械]` 6 件が正本の当該箇所から**逐語で抽出**されている(元文書 digest を持ち正本が変わると red)・**`route-registry.json` の `precondition_ids` との重複が 0 件**・**前提 ⑤ の例外**が独立の行として存在する |
| 10 | **6 前提 × 認可行列各行の越境テスト**(`data-model.md:544`) | `[機械]` **母集合はステップ 9 の資産 × allow セルから導出**(テストと同時に作らない)・**直積のすべてにテスト ID があり sha256 で exact-set**・**「対象側は非共有・要求元だけ付与」が必ず含まれる**・**1 行落とすと red**・**選手個別は `kind='self'` かつ在籍 `active`、チーム集計には在籍フィルタを掛けない** |
| 11 | **書き込みの検証** — 表権限 **8 種**(`R-6`)× ロール。`table_privilege_probe_matrix` 8 行 | `[機械]` 8 種が**単一の機械可読集合から**生成されている・**「6 権限」という記述が 0 件**・`table_privilege_probe_matrix` と exact-set・**1 権限を落とすと red** |
| 12 | **管理経路の代表 probe 1 件** — **`TX:REPRESENTATIVE_MANAGEMENT` の `atomic: true`** に従い認可と副作用が同一トランザクション | `[機械]` `management_caller` の直接アクセスが 8 権限すべてで deny・関数経由のみ成功・**認可失敗時に副作用行が増えない**・**それ以上の管理操作を実装していない** |
| 13 | **TOCTOU の 2 接続試験**(`R-3`)— **封鎖方式を実装する**: **認可行を lock する**か、**認可条件を副作用 DML の同一文へ埋め込む**(観測だけで満たした扱いにしない — 4 周目 `P1-7`) | `[機械]` **barrier を外すと red**・**2 方式のいずれかが実装されていることを機械で判定する**(認可行の `FOR UPDATE` か、副作用 DML の `WHERE` に認可条件が埋め込まれていること)・**負例: 認可 SELECT と副作用 DML を別文に分け lock を外すと red**・**linearization point が一意**であることを示す |
| 14 | **失敗注入点の資産を新設**(`contracts/authz/failure-injection-points.json` — 訂正 18)— **閉じた `injection_point_id` 5 個**(ロール作成後 / policy 変更後 / body 置換後 / owner 変更後 / ACL 正規化途中)。各行は `step_id` + **ステップ 4 の適用器が発行する `checkpoint_id`**(step 内の序数)+ 比較対象を持つ | `[機械]` **`injection_point_id` が閉じた 5 個で重複 0**・**5 行の `checkpoint_id` が相互に異なる**(同じ checkpoint を 5 回使えない)・**5 件の `checkpoint_id` がステップ 4 の実行ログに実在する**(架空の位置を書けない。**実行ログ全体との exact-set ではない** — 凍結 DDL は 7 ロール・3 スキーマ・6 表・6 ポリシー・3 関数・17 ACL で 5 文を大きく超えるため両立しない。4 周目 `P1-3`)・**5 件が指定した 5 種の位置(ロール作成後 / policy 変更後 / body 置換後 / owner 変更後 / ACL 正規化途中)に対応することを `operation_kind` で機械判定する**・**関数作成と `REVOKE` の間に注入点が無い**(`D-7` の境界を跨がない)・比較対象が列として列挙されている |
| 15 | **失敗点 5 種の注入と再適用**(`R-5`)— **非原子なので「注入 → 再適用 → 正常適用時と一致」を要求する** | `[機械]` 5 点すべてで**注入後に再適用して全比較対象が正常適用時と一致**・**注入位置はステップ 14 の資産由来**・**注入後に再適用しない場合の状態も記録される**・**最初の文より前に失敗させるだけでは合格しない** |
| 16 | **信頼境界の残余リスク試験** — アプリ用実接続から `set_config()` で他テナント ID を設定できることを試験し記録する | `[機械]` 試験が存在し**「設定できてしまう」ことを期待値として持つ**。`[手動・外部]` 残余リスクを worklog へ申し送り先つき(TSK-217)で記録した |
| 17 | **mutation ランナーと kill 判定 5 条件** — `KILL-01`〜`KILL-05`(`KILL-05` は**使い捨てクラスタ**) | `[機械]` 5 条件が資産から導出されている・**`KILL-01` の負例(宣言外の属性も変える変異)を kill と数えない**・**`KILL-04` の負例(setup 失敗を kill に数える)で red**・**`KILL-05` の負例(共有クラスタでロール属性を変異)で red**・**変異ごとに新しい DB を作る** |
| 18 | **MC/DC の写像を新設**(`contracts/authz/mcdc-map.json` — 訂正 19)— 判定 ID の母集合は**ステップ 1 で凍結した body の `-- DECISION:` 注記**から抽出する。判定・個別条件・独立影響のテスト対を持つ | `[機械]` **判定 ID 集合が body 由来の集合と exact-set 一致**(**架空の判定を足せない**・body を後から変えると manifest 照合で落ちるので**後から減らせない**)・各テスト対で **2 つのテスト ID が相異**・**対象条件以外の入力が同一**・**対象条件だけが反転**・**実測した判定結果が反転する**・`mcdc_decision_forms` の全判定形を覆う。`[手動・外部]` **注記の網羅性はここで担保する** — **機械では「最初から注記を漏らす」ことを捕まえられない**(4 周目 `P1-2`)。**body の全認可判定に注記が付いていることを逐行で確認し、判定の数と位置を worklog へ記録する** |
| 19 | **変異の全量実行** — 231 変異(`authorization_predicate` 205 / `configuration` 24 / `r8_provisioning` 2) | `[機械]` **非等価変異の生存 0**・変異集合が資産由来で**件数を定数で持たない**・等価変異は人手判定で分母から除外し**除外の記録がある** |
| 20 | **2 因子相互作用 276 + 最小 cut set 24 + MC/DC の実行** | `[機械]` 276 と 24 が資産と exact-set・**ステップ 18 の写像に対して MC/DC を満たす**・**1 相互作用を落とすと red**・**cut set の 1 要素を落とすと red**・**凍結 15 パスの差分が 0**(`origin/develop...HEAD` を基準に判定 — 4 周目 `P1-4`) |

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

> **見出しに「実装ステップ」を含めるのは機構要件**。`.claude/scripts/codex_run.py` はステップ表を
> **見出しスタックで判定する**ため、小見出しは本見出しの配下に置くこと(祖先に「実装ステップ」があれば射程内)。

#### 実装ステップ — **第 2 弾: 封印系(1〜2・本改訂の承認範囲)**

> **ステップ番号は 1 から振り直している**(2 節の実測 —
> **merge-base 以降のステップ記法コミットが 0 件**のため)。
> **機構が読むステップ表は本表だけである**(上記「第 1 弾の実施記録」は見出しに
> 「実装ステップ」を含めず射程外に置いた — 4 周目 `P0-1`)。

**2 本に分けた理由 — 封印は原子単位である**(**4 周目 `P0-4` の実測**):

**`check_authz_catalog.py:4588` の seal 照合は、`sealed_assets[]` の 6 本の
`canonical_sha256` を毎回再計算して seal と突き合わせる。**
したがって **`sealed_assets` を変更したコミットは、同じコミットで reseal しない限り必ず red になる。**

**封印資産を変える編集を複数ステップへ割ると、reseal 前の各コミットで検証が通らず、
「1 委任 = 1 ステップ → 検証 → 1 コミット」の完了点を作れない**(設計書 6.1)。
**そこで封印資産を変える作業をすべてステップ 2 の 1 コミットへ収め、
封印資産に触れない `core-areas.json` の登録を先行ステップにした。**
**これは 1 ステップ = 1 コミットの例外ではなく、2 ステップとも 1 コミットである。**

> **期待件数の撤去は裁定 `D-16` で別タスクへ送った**(1 節)。**本改訂の先行ステップは `core-areas.json` の登録 1 件だけになった。**

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | **`core-areas.json` への登録**(裁定 `D-13` + `S-8` の一部)— **`guard_paths` へ 10 本**・**`tenant-isolation.paths` へ 9 パターン**(いずれも下表で確定済み)。**封印資産に触れない** | `[機械]` **下表の 10 本と 9 パターンが登録されている**(exact-set)・**いずれか 1 件を外すと red**・**`tenant-isolation.paths` に追加した各パターンが実在ファイルへ 1 件以上マッチする**(**空振りのパターンを書けない**)・`uv run pytest tests/test_core_guard.py tests/test_ci_wiring.py` green。`[手動・外部]` **6.3 規則⑤の敵対レビュー + 人間承認** |
| 2 | **封印資産の確定と再封印**(owner 移管 + `S-5` + `S-7` + 検査器追随(**重複行で潰れる 5 配列の検査を含む**)+ `--reseal-oracle` **1 回**)— **2-a 〜 2-e を 1 コミットに収める**(上記の理由)。**`oracle_commit` は動かさない**(入力資産が不変のため — 2 節の実測) | `[機械]` **2-a 〜 2-e の全条件を満たす**(下記)・**reseal 後に `check_authz_catalog.py` が rc=0**・**`--reseal-oracle` を付けない通常検証では reseal されない**。`[手動・外部]` **差分敵対レビューと人間査読**(`reseal_policy.human_review_required`) |

##### ステップ 1 の登録先 — **`D-13` の規則を当てた結果**(**実測で確定済み**)

**`guard_paths`(完全一致・`frozenset`)へ 10 本** — 規則「**凍結資産またはコア領域の成果物を検査する検査器とその対**」:

| 検査器 | 対(テスト) |
| --- | --- |
| `scripts/check_authz_catalog.py` | `tests/test_check_authz_catalog.py` |
| `scripts/check_authz_function_bodies.py` | `tests/test_check_authz_function_bodies.py` |
| `scripts/check_mcdc_map.py` | `tests/test_check_mcdc_map.py` |
| `scripts/check_failure_injection_points.py` | `tests/test_check_failure_injection_points.py` |
| `scripts/check_shared_preconditions.py` | `tests/test_check_shared_preconditions.py` |

**`areas[].paths`(`tenant-isolation`・`fnmatch` で `*` が `/` を跨ぐ)へ 9 パターン** —
**既登録との差分だけを足す**(`scripts/check_authz_catalog.py` と `tests/test_check_authz_catalog.py` と
`contracts/authz/*` は**既に登録済み**であり、**再登録しない**):

`scripts/check_authz_function_bodies.py` / `scripts/check_mcdc_map.py` /
`scripts/check_failure_injection_points.py` / `scripts/check_shared_preconditions.py` /
`tests/test_check_authz_function_bodies.py` / `tests/test_check_mcdc_map.py` /
`tests/test_check_failure_injection_points.py` / `tests/test_check_shared_preconditions.py` /
`backend/src/pitchlog/authz/*`

**本改訂は「規則に合致するのに未登録の 11 本目」を検出する導出型の検査を作らない**(裁定 `D-13`)。
**導出型の一般化は別タスクの射程**であり、**`PR #56` の `schema_contract_asset_paths()`
(`tests/test_core_guard.py:778`)が同型の先例である** — **同じ形をここで作ると、
別タスクへ送った範囲を二重に持つことになる**(4 周目 `P1-6`)。
**本改訂の合格条件は「列挙した 10 本 + 9 パターンが登録されており、1 件外すと red」までである。**

##### ステップ 2 の内訳と合格条件

> **`S-9`(`claim-mutant-map.json` の受取先 178 件)は裁定 `D-15` で PR #3 へ送った。**
> **本改訂は `claim-mutant-map.json` に触らない。**

**2-a owner の移管と `CONTROL-READS` の事実是正**(裁定 `D-11` `D-12`)

**`boundary-proposal.json` の 3 境界を閉じた表で固定する**(**条件で一般化しない**):

| `boundary_id` | `aggregation_location` | `aggregation_owner_task_id` |
| --- | --- | --- |
| `BOUNDARY:SHARED-AUTHORIZED-ROWS` | `generated_sql_expression` | **`3d993b75-e687-818d-8cb8-ec57508e73e0` へ**(現 `TSK-235`) |
| `BOUNDARY:CONTROL-READS` | `none` | **キーごと削除**(現 `TSK-235` — **集計が無いのに集計 owner を持つ**) |
| `BOUNDARY:REPRESENTATIVE-MANAGEMENT` | `none` | **`TSK-250` のまま不変**(**本改訂は触らない**) |

あわせて `deferred_equivalence_contract.owner_task_id` を **`3d993b75-e687-818d-8cb8-ec57508e73e0`** へ。

`[機械]` **3 境界の当該フィールドが上表と完全一致**・
**`deferred_equivalence_contract.owner_task_id` が実 ID と完全一致**・
**負例: `REPRESENTATIVE-MANAGEMENT` の owner を消すと red /
形式だけ似た別 ID を入れると red / 空文字で red**。

> **「`aggregation_location: none` の境界に owner が無いこと」を合格条件にしてはならない**
> (4 周目 `P0-5` の実測)。**`REPRESENTATIVE-MANAGEMENT` も `none` で、正当な `TSK-250` owner を持つ**ため、
> **条件で一般化すると正しい実装が不合格になるか、正当な owner まで削られる。**
> **母集団は 3 境界の閉じた表である。**

**2-b `S-5` — `boundary-proposal.json` の裁定後の型を確定**

**資産と検査器を同時に変える**(下記「資産と検査器が二重に固定されている」)。

`[機械]` **`frozen_value` の差分が 0**・**`alternative_value` と `review_id` が不変**・
**検査器の literal が資産と一致**・**`tests/test_check_authz_catalog.py` が追随している**・
**負例: 資産だけ変えると red / 検査器だけ変えても red**。

**2-c `S-7` — `ddl-elements.json` の `scope` を確定**

`status: verified_probe_configuration` / `product_schema: false` /
`contains_sql_body: false` / `second_group_approval_required: false`。
**`check_authz_catalog.py:2673-2684` が 4 キーの exact 集合と 4 つの literal を要求する**ため、
**ここも資産と検査器を同時に変える**。

`[機械]` **4 キーが確定値と完全一致**・**検査器の literal が資産と一致**・
**`tests/test_check_authz_catalog.py` が 4 キーそれぞれの負例を持つ**。

`[手動・外部]` **「通った構成」の実行証跡は資産へ置けない** — **`scope` は 4 キー exact で、
参照フィールドを足すと `_expect_keys` が落ちる**(4 周目 `P1-7` の実測)。
**証跡は PR 本文と worklog へ置く** — **第 1 弾(PR #52 / `67e06a2`)の当該 CI run と、
そこで green になった検証ステップを明記する。**

**2-d 重複行で潰れる配列を 5 件だけ落とす**(**部分的な硬化 — 多重度を閉じる主張ではない**)

**検査器は配列を `set` / `dict` へ畳んでから exact-set を比べる**ので、
**同じ行を複製しても多重度が潰れて green になる**。

**この PR が封印する形は正しい**(**実測 2026-09-12**: 凍結 15 資産・**2290 配列**を走査して
**重複要素 0 件・重複 JSON キー 0 件**)。**したがって本改訂の封印が壊れる危険はない。**
**本項は「将来の混入を防ぐ」硬化であり、その範囲は下表の 5 件に限る。**

| 資産 | 配列 | 畳んでいる箇所 |
| --- | --- | --- |
| `oracle-seal.lock.json` | `input_assets` | `:4531`(`set`) |
| `boundary-proposal.json` | `boundaries` | `:4341`(`set`) |
| `boundary-proposal.json` | `pending_human_reviews` | `:4371`(`dict`) |
| `ddl-elements.json` | `transaction_boundaries` | 同型 |
| `ddl-elements.json` | `provisioning_claim.completion_catalog_expectations` | 同型 |

> **【撤回】7 周目に「変異で測ったので母集団は閉じた」と書いたが誤りである。**
> **走査の入口を「`dict` を要素に持つ配列」と私が選んだ**ため、
> **文字列の配列が漏れていた**(`pending_human_reviews[0].affected_ids_if_changed` /
> `tables[0..5].row_shape_ids` / `transaction_boundaries[0..2].step_ids` — **計 10 配列**)。
> **さらに JSON オブジェクトの重複キーは、解析後のオブジェクトを走っても観測できない**
> (`_read_json` が `json.loads` の last-wins で潰す — `:491`)。
> **「閉じる対象を人が選んだ」という、本 PR で 4 度目の同じ失敗である。**

**残る母集団(10 配列 + 重複キー)は別タスクへ送った** —
**[authz 凍結資産の多重度を検査器で閉じる(重複行・重複キー)](https://app.notion.com/p/3d993b75e68781b59bd3c55024f9ffea)**。
**本改訂は上表 5 件の部分的な硬化に留める。**

`[機械]` **上表 5 配列それぞれに行数と ID 一意性の検査がある**・
**負例: 5 配列それぞれで先頭行を 1 件複製すると、多重度検査が red を出す**
(**seal の digest 不一致では判定しない** — `ddl-elements` と `boundary-proposal` は
**digest 不一致だけでも必ず red になる**ため、**それでは検査を 1 行も書かなくても負例が通る**
〔8 周目 `P1-3`〕。**semantic validator を直接呼ぶか、変異後の seal を追随させて、
多重度検査の有無で結果が変わることを示す**)・
**負例: 多重度検査を外すと上記の負例が red でなくなる**・
**既に red だった配列の検査は変えない**。

**2-e oracle の再封印**(`--reseal-oracle` **1 回**)**2-e oracle の再封印**(`--reseal-oracle` **1 回**)

`[機械]` **seal の `oracle_commit` が `dd2cb92...` のまま**・
**`oracle_commit_semantics` が `last_committed_step_4_input_baseline` のまま**・
**`input_assets[].git_blob_digest` 8 件が不変**・
**`sealed_assets[]` のうち `boundary-proposal` / `ddl-elements` の
2 本だけ `canonical_sha256` が変わる**(**残り 4 本は不変** — **`claim-mutant-map` は裁定 `D-15` で PR #3 へ**)。

#### 資産と検査器が二重に固定されている(**`S-5` と `S-7` の実測**)

**検査器が現在値をハードコードしている**ので、**資産だけ・検査器だけの変更はどちらも red になる**:

| 箇所 | 現在の要求 |
| --- | --- |
| `check_authz_catalog.py:4339` | `proposal_status == "pending_tsk_235_confirmation"` |
| `:4380` | 操作数レビューの `status == "pending_human_decision"` |
| `:4396` | 射程レビューの `status == "pending_human_review"` |
| `:2673-2684` | `scope` が 4 キー exact で、`candidate_probe_only` / `false` / `false` / `true` |

**確定値は実装時に 1 案を選ぶのではなく、本計画で決める**(**承認対象に未確定の型を残さない** — 2 周目 `P1-6`):

| フィールド | 現在値 | **確定値** | 理由 |
| --- | --- | --- | --- |
| `proposal_status` | `pending_tsk_235_confirmation` | **`tsk_235_confirmed`** | **TSK-235 との突合は 4 論点すべてで完了**(先方の自己訂正コミット `04baf07`)。**何が完了したかを名前が保つ** |
| 操作数レビューの `status` | `pending_human_decision` | **`human_decided`** | **裁定 `D-4` で frozen 値 8 を承認済み** |
| 射程レビューの `status` | `pending_human_review` | **`human_decided`** | 同上(29) |
| `frozen_value` | 8 / 29 | **不変** | 裁定 `D-4` |
| `alternative_value` | 7 / `null` | **不変(維持)** | **「7 を採らなかった」記録が消えると、なぜ 8 なのかが後から読めない** |
| `review_id` の `PENDING-` 接頭辞 | `PENDING-*` | **不変(維持)** | **ID の安定性** — **改名すると `affected_ids_if_changed` 等の参照が壊れる** |
| `scope.status` | `candidate_probe_only` | **`verified_probe_configuration`** | 第 1 弾で probe 構成の実機検証が green になった |
| `scope.second_group_approval_required` | `true` | **`false`** | 第 2 群の承認が第 1 弾の完了で満たされた |
| `scope.product_schema` / `contains_sql_body` | `false` / `false` | **不変** | **SQL 本体は `contracts/authz/function-bodies/**` にあり manifest 自身は持たない** |

### 第 2 群後半・第 3 群 — **第 1 弾の承認範囲外だった要件の記録**

> **本節の `S-1`〜`S-10` のうち、`S-1`・`S-5`・`S-7` と `S-8` の一部(**`core-areas.json` への登録だけ**)が本改訂の射程である**(裁定 `D-14`)。
> **`S-2`・`S-3`・`S-4`・`S-6`・`S-9`・`S-10` と `S-8` のうち引き渡し 3 資産のパス・`test_ci_wiring.py` の追記は PR #3**(**`S-9` は裁定 `D-15`**)。
> **`S-8` のうち期待件数のハードコード撤去は別タスク**(裁定 `D-16`)。
> **`S-8` は 3 つの送り先へ分かれる** — **割り当ての正は 2 節の 2 つの送り先表**である。

**裁定 `D-8`(2026-09-09)**: 計画レビューが **3 周**を要し、**前周修正起因が 2 周連続で過半**になった
(7.3-6 の発火)。指摘の型は「**新設した母集合資産が自己申告で自明に green にできる**」に収束しており、
これを機械で縛るにはさらに上位の母集合が必要という**無限後退**に入っていた。

**根本原因**: 第 1 群が凍結した oracle には、第 2 群が必要とする母集合(関数 body・MC/DC の判定・
失敗注入点・要件の小項)が**無い**。第 2 群が自作すると自己申告になる。**実体を作る前に文書で閉じようとした**
のが台帳 `H-68` の型である。

→ **第 1 弾はステップ 1〜20(実体を作る)を承認範囲とした。**(**裁定 `D-9` で旧 17 を撤去し 21 → 20 になった**)
**これを終えれば、後半は実測に基づいて書ける**(第 1 群と同じ形 — 人間の裁定 2026-08-31)。

#### 改訂 3 **第 2 弾**が満たすべき要件(**失わないためにここへ記録する**)

> **本表は `S-1`〜`S-10` の要件そのものの記録であり、射程の割り当てではない。**
> **本改訂(PR #2)の射程は `S-1`・`S-5`・`S-7`・`S-8` の一部**(**`core-areas.json` 登録だけ** — **期待件数の撤去は裁定 `D-16` で別タスクへ**)**だけ**である。
> **`S-2`・`S-3`・`S-4`・`S-6`・`S-9`・`S-10` と `S-8` のうち引き渡し 3 資産のパス・`test_ci_wiring.py` の追記は PR #3**(裁定 `D-14`・`D-15`)。
> **`S-8` のうち期待件数のハードコード撤去は別タスク**(裁定 `D-16`)。
> **割り当ての正は 2 節の 2 つの送り先表**である。

> **【第 1 弾当時の宣言・本改訂では失効している】**
> **本節の `S-1`〜`S-10` はすべて改訂 3 第 2 弾の射程であり、第 1 弾の承認条件ではなかった**(裁定 `D-10`・2026-09-10)。
> **第 1 弾の承認範囲ではこれらの資産・配線・封印に触れなかった** — 触れると「実体が無い段階で機械条件を紙の上で閉じる」(`H-68` の型)へ戻るため。
> **本改訂(第 2 弾)はこの禁止の対象ではない** — **`S-1`・`S-5`・`S-7` と `core-areas.json` の登録に触れるのが本改訂の目的である。**
> 各行の「確定済み」と書いた部分は**実測の記録**であり、**合格条件は第 2 弾で確定する**。

| # | 要件 | 由来 |
| --- | --- | --- |
| `S-1` | **統合コミットを 2 段に分ける** — ① 入力・封印資産・検査器・追随テスト・derived lock を変更する基準コミット ② その**基準コミット SHA** を 6 資産の `oracle_context` と seal へ設定し `--reseal-oracle` するコミット。**`oracle_commit` に自コミットの SHA は入れられない**。各層の reseal は一度ずつでよく、差分敵対レビューは 2 コミットの範囲に対して 1 回にできる。**reseal フラグの実測(2026-09-10・TSK-355 のタブとの相互検証)**: **3 フラグは fail-early の挙動が非対称である**。**`--reseal-oracle` は `verify_seal=not args.reseal_oracle` を渡して自分の seal 検査を明示的に飛ばす**(`check_authz_catalog.py:4958`)ので、**封印資産を変更した状態から実行できる**。一方 **`--reseal` は `_validate_manifest` が reseal 分岐より先に走るため、`source_blob_digest` が不一致だと `--reseal` を付けても exit 1 で到達しない**。さらに **`reseal_catalog()`(`:1489-1503`)が更新するのは `claims[].decision_digest` と decision lock だけ**で、**`input_manifest`(`source_blob_digest` / `item_counts_by_kind` / `heading_ids` / `commit`)は一切触らない**。→ **本タスクの `S-9` は `claim-mutant-map.json`(oracle 層)しか変更しないため `--reseal-oracle` で足り、`_validate_manifest` にも掛からない**(要件書を変更しないので `source_blob_digest` が動かない)。**要件書を変更するタスク(TSK-355)は `--reseal` の前に `input_manifest` の手更新と `claims` への構造行の登録が必要**で、**これは本タスクの射程外**である | 3 周目 `P1-2` / **2026-09-10 の実測** |
| `S-2` | **論理 ID → pytest node ID の解決方式を決める** — 実測で `auth-catalog` の enforcement **187 件**が `TSK-270.step4.<claim>.db` 形式で **`::` が 0 件**。検査器は `implemented` の ID を `pytest --collect-only` の node ID と完全一致させる。**さらに本タスク所有の planned 論理 ID が別に 468 参照ある**(claim runtime / positive / interaction で 460・表権限で 8 — 4 周目 `P1-6`)。**187 + 468 のすべてについて**、資産を実 node ID へ変えるか独立の解決 manifest を設けるかを決める(方式が分岐)。**ただし 468 のうち `contract_only` 158 件は裁定 `D-9` で受取タスクへ移管したので、本タスクは node ID 解決も status 更新も行わない**(`S-10` — `runtime_test_owner.status` は `planned` のまま)。**本タスクが解決するのは残り 310 参照である。****status の更新もこの射程**。**実測の補足(2026-09-10・TSK-235 のタブからの申し送り)**: **`auth-catalog.json` の各 entry は owner を 2 つ持つ** — **`catalog_test_owner` は 187 件すべて `implemented`**・**`enforcement_test_owner` は 187 件すべて `planned`**(`TSK-270` 169 / `TSK-312` 18)。**`implemented` にするのは後者**である。**TSK-250 の計画書ステップ 19 の合格条件「全 `AUTH-*` に DDL 要素とテスト ID がある」は、文字面では前者(既に `implemented`)で通ってしまう**ため、**受取側が enforcement 側を見ることを `S-6` の受取契約で固定する** | 3 周目 `P1-3` / 4 周目 `P1-6` / **2026-09-10 の申し送り** |
| `S-3` | **要件側 7 単位の source を決め直す** — `req-universe.json` に `list_item` は **0 件**(条レベルのみ)。小項 ID は `contracts/authz/requirement-claims.json` 側にある。**同資産を source にするか、`req-universe.json` へ小項母集合を追加するか**(方式が分岐) | 3 周目 `P1-6` |
| `S-4` | **引き渡しマニフェストの ID 完全性を固定する** — 「実在する `CATALOG:*`」だけでは 1 件でも空集合でも通る。**`auth-catalog.json` の全 187 `catalog_entry_id` と exact-set 一致**を要求する。あわせて **TSK-250 側は 13 claim 行だが一意な runtime test ID は 8 件**(`FR-041/list_item-006` が 3 行、`list_item-007` が 4 行で ID を共有)— **「13 件」と「ID 集合」のどちらを read-back するか**を決める | 3 周目 `P1-7` |
| `S-5` | **`boundary-proposal.json` の裁定後の型を確定する** — 現在値には `proposal_status: pending_tsk_235_confirmation`・`PENDING-*` ID・2 種の pending status・`alternative_value: 7` がある。**どれを維持・改名・削除するかの exact 値と負例**を `scope` と同様に定める | 3 周目 `P1-8` |
| `S-6` | **`R-4` / `R-7` の受取契約を閉じる** — 受取タスク(TSK-250 / TSK-217)の DoD へ安定テスト ID を登録し、相互リンクし、**受取側から取得した集合と exact-set 突合**する。**製品 adapter / manifest の事前凍結**も `R-4` の要求 | 2 周目 `P0-6` / 3 周目の突合 |
| `S-7` | **`scope` の確定値**(参考 — 3 周目 `P1-6` で有効と判定済み): `status: "verified_probe_configuration"` / `product_schema: false` / `contains_sql_body: false` / `second_group_approval_required: false`。**上記以外の値を入れると red** | 2 周目 `P1-6` |
| `S-8` | 引き渡し 3 資産のパス(`ddl-elements.json` / `auth-catalog.json` / `rejected-configs.json`)・`core-areas.json` への新設パス登録(**本改訂のステップ 1**)・`test_ci_wiring.py` の追記(**PR #3**)・期待件数のハードコード撤去(**別タスク — 裁定 `D-16`。「既存 20 箇所すべて」という旧方針は 4 周目 `P1-8` で撤回した**)・成果物の敵対レビュー。**`guard_paths` へ登録すべき新設検査経路の実測(2026-09-10・TSK-235 のタブからの申し送り)= 6 本**: `scripts/check_authz_function_bodies.py` / `scripts/check_shared_preconditions.py` / `scripts/check_failure_injection_points.py` と、それぞれ対になる `tests/test_check_*.py` 3 本。**現行の `guard_paths` 30 件は `check_design_propagation` / `check_doc_coverage` / `check_processing_stages` をスクリプトとテストの対で個別列挙**しており、**命名規約上この 6 本も入る系列**である。**未登録のままでは、凍結資産を検査するスクリプトを弱めても逐行確認が発火しない**(台帳 `H-12` の型 — `docs/README.md` に「再発 5 件目」が記録済み)。**`guard_paths` 追加は 6.3 規則⑤(敵対レビュー + 人間承認)**。**送り先記録(6 周目 `P2-1`・`(B)`)**: **上記「6 本」は 2026-09-10 時点の人手列挙であり、ステップ 18 で `mcdc-map.json` の独立検査器とそのテストを新設するので 8 本になる。****第 2 弾では登録母集団を人手で列挙せず、`scripts/check_*.py` と対になる `tests/test_check_*.py` の実在から機械的に導く**(**本タスクは「人が列挙した集合が母集団になっている」型の欠陥を 6 周のレビューで 7 回踏んでいる** — 走査の鍵 / セル内の位置 / 歴史的記録の分類 / 対象ファイルの選定 / 抽出キー / DoD の否定範囲 / **本項の `guard_paths` の列挙**。台帳候補 A・E と同型) | 1〜2 周目 / **2026-09-10 の申し送り** |
| `S-9` | **プレースホルダ受取先を実 ID へ置換する**(4 周目 `P1-9`)— 凍結資産に `receiving_task_id: TSK-270-GROUP-2` が **178 件**残っている(**実測** — `contract_only` 158 + `probe_executable` 20)。**残存 0 件**を条件にする。封印資産の変更なので `S-1` の基準コミットに含める。**確定済みの事実(改訂 3 第 1 弾で実測)**: **① 分割単位は claim 行ではなく `runtime_test_owner.id` である** — `FR-041/list_item-014#request-validation`(`no_db_decision_point`)と `#participant-authorization`(`route_universe_pending`)が**同一 ID を共有**しており(共有 6 組のうち理由コードが混在するのはこの 1 組だけ)、**claim 行で分けると 1 つのテスト ID を 2 タスクが所有する**。**② `probe_executable` 20 件は `runtime_target` を持ち TSK-317 の probe 経路で実行できる**。**③ `contract_only` 158 件は `runtime_target` を持たず、本計画は `product_schema: false` を宣言しているので TSK-317 は受取先になれない**。**④ `claim-mutant-map.json` は oracle 層なので `--reseal-oracle` で足りる**(`_validate_manifest` は要件書の変更だけを見るため掛からない — `S-1` の実測)。**具体の分割・受取タスクの起票・検査条件は改訂 3 第 2 弾で確定する**(裁定 `D-10`) | 4 周目 `P1-9` / 裁定 `D-9` / 改訂 3 第 1 弾 1〜2 周目 |
| `S-10` | **`contract_only` 158 行の受取契約を確定する**(**裁定 `D-9`・2026-09-10 で新設** — 旧ステップ 17 の置き換え)。**確定済みの規範**: **`R-7` が「`contract_only` は schema-drift kill + 受取タスクの runtime テスト ID」と定めるので、TSK-317 は実テストを書かない**(書くと同条が名指しで警戒する「契約 lint を実副作用 kill として数える抜け道」になる)。**`runtime_test_owner.status` は `planned` のまま動かさない。****改訂 3 第 2 弾で確定すべき論点(1〜2 周目の敵対レビューで洗い出した — いずれも実体〔ステップ 17〜20〕と実 CI が無いと合格条件を書けないため送る。裁定 `D-10`)**: **(1) 分類の exact-set の比較元と基準コミット**(`S-1` ② が同じファイルの `oracle_context.oracle_commit` も必ず変えるため、「ファイル差分が `receiving_task_id` だけ」では成立しない — 正規化して比較する形が要る。1 周目 `P0-3` / 2 周目 `P1-4`)**(2) 受取先の許容集合の検査**(現行検査器 `check_authz_catalog.py:3803` は**非空文字列しか見ない**ので、リテラルを置くだけで通る。1 周目 `P0-3`)**(3) 同一 `runtime_test_owner.id` の行が同一受取先を持つことの検査**(`S-9` ① の不変条件)**(4) `TSK-217` の 7 件の機械的分離****(5) 158 claim 行と 152 の一意 ID の対応**(6 組の共有を取りこぼさない・件数は定数で持たない)**(6) 凍結 15 パスの差分の基準区間**(`S-1` が凍結 15 パスのほぼ全体を変更対象にしているため、**「`S-1`・`S-9` が宣言した資産のみ」では任意の変更を `S-1` 名目で通せる** — **許可パスと許可フィールドの閉じた集合**が要る。2 周目 `P0-3`)**(7) 履歴を要する検査の CI 実行可能性**(**実測: root の `harness` ジョブは `fetch-depth` を指定しておらず浅い履歴**〔`ci.yml:75`〕。`<base>^` を要する検査は履歴取得なしでは解決できず、**スキップすると無効・fail-closed だと CI が常時失敗する**。2 周目 `P1-6`)**(8) 受取側からの read-back と exact-set 突合**(`S-6` と同じ形にするかを明示する — **明示しないとローカル資産へ受取先リテラルを置くだけで通る**。2 周目 `P1-5`)**(9) 受取タスクの DoD へ課す条件**(152 の安定 ID / 158 claim の被覆 / **各テストで「claim の述語が assertion に現れ、常時成功にすると red」**— 旧ステップ 17 の負例条件を受取契約へ移す) | 裁定 `D-9`・`D-10` / 改訂 3 第 1 弾 1〜2 周目 |

**改訂 3 の進め方**: **裁定 `D-9`(2026-09-10)により、改訂 3 は本計画のステップ 16 完了時点で開始した**(旧予定は「ステップ 21 の完了後」)。**裁定 `D-10`(同日)により 2 弾に分ける** — **第 1 弾(本改訂)= 機械的な作業のみ**(ステップ 17 の撤去・連番の振り直し・旧参照の除去・裁定と実測の記録)。**第 2 弾 = `S-1`〜`S-10` の機械条件の確定**で、**ステップ 17〜20 の完了後**に行う。`status` は `active` のまま、`承認` を `未` へ戻して改訂し、**コア領域なので敵対レビューを通してから人間の承認を求める**。**ステップ 1〜16 は番号が動かないため履歴の書き換えを伴わない。**

## 5. DoD(受け入れ基準)

**第 1 弾の承認範囲は第 2 群前半(ステップ 1〜20)**であり、下記はその受け入れ基準だった(裁定 `D-8`・`D-9`)。**本改訂の受け入れ基準は次節「第 2 弾」である。**
**第 2 群後半・第 3 群の DoD は計画改訂 3 第 2 弾で確定する**(4 節の `S-1`〜`S-10`)。

- [ ] **関数 body がステップ 1 の先行コミットで固定され、manifest の `source_commit` がそのコミットを指す**。**2 段の照合(現ファイル + `git rev-parse`)が通り、後続コミットでの差し替えが red になる**
- [ ] **読み取り関数が `LANGUAGE SQL BEGIN ATOMIC` に限定され、動的 SQL が 0 件**。**認可判定に `-- DECISION:` 注記がある**(`R-1`)
- [ ] **DDL 生成器の入力が資産 + body の 2 つだけ**(資産を参照しない識別子リテラル 0 件)
- [ ] **適用器が `ordered_steps` の順序を資産から読み、関数作成 + `REVOKE` + `GRANT` を 1 トランザクションに収める**(裁定 `D-7`)。**中間状態で `PUBLIC` が実行できないことを試験した**
- [ ] **適用器が `checkpoint_id` を発行して実行ログへ残す**(ステップ 14 の母集合)。**冪等で、失敗注入後に再適用して正常適用時と一致する**(`R-5`)
- [ ] **4 ロールの実接続の行列がある**(`SET ROLE` の模擬を使わない・**新しい DSN 環境変数を増やしていない**)
- [ ] **カタログ検査が `R-1`・`R-2`・`R-8` を満たし、負例 9 種で red になる**
- [ ] **12-4 節の越境テスト最低要求 4 件と、`data-model.md:544` の「6 前提 × 認可行列各行」が機械条件として存在する**(母集合をステップ 9 で独立に新設し、テストと同時に作っていない)
- [ ] **「常に 404 の 4 資源」が関数のシグネチャに存在しない**(付与の値で分岐させていない)
- [ ] **表権限 8 種が単一の機械可読集合から生成されている**(「6 権限」の記述が 0 件)
- [ ] **`TX:REPRESENTATIVE_MANAGEMENT` の原子性・失敗注入 5 種・信頼境界の残余リスク試験がある**
- [ ] **`R-3` の封鎖方式を実装した** — **認可行を lock する**か**認可条件を副作用 DML の同一文へ埋め込む**(観測だけで満たした扱いにしていない — 4 周目 `P1-7`)
- [ ] **失敗注入点の 5 件が閉じた ID を持ち、`checkpoint_id` が相互に異なり、適用器の実行ログに実在する**(実行ログ全体との exact-set ではない — 4 周目 `P1-3`)。**5 種の位置に対応することを `operation_kind` で機械判定した**
- [ ] **`contract_only` 158 行について、本計画の承認範囲では「受取タスク所有の runtime テスト」と「その論理 ID → pytest node ID の解決」を実装していない**(**schema-drift kill は禁止対象ではない** — **実測で 231 変異のうち 173 件が `contract_only` のみを参照**しており、**それらはステップ 19 の全量実行が schema-drift チャネルで kill する本タスクの仕事である**。`contract_only` の意味は `kill_contract.contract_only_runtime_rule` = `runtime_kill_forbidden_handoff_test_required` のとおり**「runtime kill を禁じる」であって「schema-drift kill もしない」ではない**。5 周目 `P0-2`)(**裁定 `D-9`** で旧ステップ 17「152 個の実テストを書く」を撤去した — `R-7` が runtime テストを**受取タスクの所有**と定めており、TSK-317 が書くと同条が名指しで警戒する「契約 lint を実副作用 kill として数える抜け道」になる)。**検証方法**: **`runtime_test_owner.status` が 158 行すべて `planned` のまま**であり、**`runtime_test_owner.id` の論理 ID を pytest node ID へ解決する仕組みを本計画で作っていない**こと(**schema-drift kill を実行する mutation は対象外** — ステップ 19 の要求と両立させる)。**受取契約の確定は改訂 3 第 2 弾の `S-10`**(裁定 `D-10` — 本計画の DoD ではない)
- [ ] **MC/DC の判定 ID 集合が body 由来の集合と exact-set 一致する**(架空の判定を足せない・後から減らせない)。**疑似ペアを弾く 4 条件を機械で検査している**
- [ ] **注記の網羅性を人手逐行確認で担保した** — **機械では「最初から注記を漏らす」ことを捕まえられない**(4 周目 `P1-2`)。body の全認可判定に注記があることを確認し、判定の数と位置を worklog へ記録した
- [ ] **231 変異・276 相互作用・最小 cut set 24・MC/DC を実行し、非等価変異の生存が 0 件**。**件数を定数で持っていない**
- [ ] **凍結 15 パスの差分が 0** — 判定基準は **`origin/develop...HEAD`**(作業ツリーの未コミット差分ではない — 4 周目 `P1-4`)。新設資産はこの 15 パスに含まれない
- [ ] **`docs/design/data-model.md` と設計書 10.1 の差分が 0**(TSK-348・TSK-343 の所有)
- [ ] **[TSK-348](https://app.notion.com/p/3d693b75e687816b8911f266f9bb59c5) がマージ済みである**(本タスクのマージの前提)
- [ ] **本タスクの成果を「`NFR-010` 適合」と主張していない**。HTTP 経路の判定は TSK-217 へ送った
- [ ] **mutation を `NFR-019` のテスト種別として計上せず、`NFR-018`(b)② を根拠に引いていない**(6 節)
- [ ] **コードに触れる無記法コミットが 0 件**(現在地導出が「不明」に落ちていない)
- [ ] **改訂 3 が満たすべき要件 `S-1`〜`S-10` を 4 節に記録した**(失わないため)
- [ ] **申し送りを起票した** — ADR-003 `D-12` と `contracts/authz/` / アプリ用ロールの `DELETE` / `H-57` のジョブ行 / `AUTH-*` と `CATALOG:*` の ID 体系の食い違い / `closure-handoff-data-model.json` の「作成」と正本の「作成・実行」の差
- [ ] **TSK-348・TSK-349・TSK-343・TSK-344 と相互リンクした**
- [ ] **`[手動・外部]` の全項目について、逐項の証跡を worklog に残した**
- [ ] **コア領域として敵対レビュー + 人間の逐行確認を通っている**(逐行確認は **PR 作成者以外**が行い、**実施記録行を確認者本人が記入**した)

### 第 2 弾(ステップ 1〜2)— **本改訂の受け入れ基準**

> **第 1 弾(上記)は PR #52 で達成済み。本節が本改訂の受け入れ基準である。**
> **ステップ 1 は封印資産に触れず、ステップ 2 が封印資産の変更と reseal を 1 コミットで行う。**

#### ステップ 1 — `core-areas.json` への登録

- [ ] **`guard_paths` へ 4 節の表の 10 本を登録した**(exact-set・**1 本外すと red**)
- [ ] **`tenant-isolation.paths` へ 4 節の 9 パターンを登録した**(**既登録分を再登録していない**)
- [ ] **追加した各パターンが実在ファイルへ 1 件以上マッチする**
- [ ] **導出型の検査(規則に合致するのに未登録の 11 本目の検出)を作っていない**(裁定 `D-13` — 別タスク)
- [ ] **6.3 規則⑤の敵対レビューと人間承認を通した**

#### ステップ 2 — 封印資産の確定と再封印(**1 コミット**)

- [ ] **`boundary-proposal.json` の 3 境界が 4 節の閉じた表と完全一致**
      (**`REPRESENTATIVE-MANAGEMENT` の `TSK-250` は不変**)
- [ ] **`deferred_equivalence_contract.owner_task_id` が実 ID と完全一致**
- [ ] **`proposal_status` と 2 件の `status` が確定値**・**`frozen_value` / `alternative_value` / `review_id` は不変**
- [ ] **`scope` の 4 キーが確定値**で、**検査器の literal が資産と一致**し、**4 キーそれぞれの負例がある**
- [ ] **重複行で潰れる 5 配列に行数と ID 一意性の検査を置いた**(`input_assets` / `boundaries` / `pending_human_reviews` / `transaction_boundaries` / `provisioning_claim.completion_catalog_expectations`)
- [ ] **5 配列それぞれで、多重度検査が red を出す**(**seal の digest 不一致で判定していない** — **多重度検査を外すと負例が red でなくなる**)
- [ ] **既に red だった配列の検査を変えていない**
- [ ] **再封印の直前に、変更後の 3 ファイルへ重複が 0 件であることを実測した**(**全配列 + 全 JSON キー対を走る汎用走査**。**この実測が本改訂の封印を守る**)
- [ ] **残る母集団(10 配列 + 重複キー)を別タスクへ送った**と計画書に書いた
- [ ] **「多重度を閉じた」と主張していない**(**7 周目の当該記録は撤回済み**)
- [ ] **`--reseal-oracle` を 1 回だけ回した**
- [ ] **`oracle_commit` と `oracle_commit_semantics` が不変**
- [ ] **`input_assets` が 8 行のまま**(**重複なし**)で、**`git_blob_digest` 8 件が不変**。**`sealed_assets[]` の 2 本(`boundary-proposal` / `ddl-elements`)だけが変わった**
- [ ] **`claim-mutant-map.json` に触っていない**(裁定 `D-15` — `S-9` は PR #3)
- [ ] **「通った構成」の実行証跡を PR 本文と worklog へ記録した**(**`scope` へは置けない**)
- [ ] **差分敵対レビューと人間査読を通した**

#### 引き渡し

- [ ] **PR #3 へ送る 7 件を計画書へ受取先つきで書いた**(`S-2` `S-3` `S-4` `S-6` `S-9` `S-10` と **`S-8` のうち引き渡し 3 資産のパス・`test_ci_wiring.py` の追記**)
- [ ] **`S-8` の 3 つの送り先を書き分けた**(本改訂 = `core-areas.json` 登録 / PR #3 = 上記 / 別タスク = 期待件数の撤去)
- [ ] **コア領域として敵対レビュー + 人間の逐行確認を通っている**(**逐行確認は PR 作成者以外**・**実施記録行を確認者本人が記入する**)
- [ ] **引き渡し前に PR HEAD の `core-guard` 以外の全ジョブが green**
- [ ] **人間の逐行確認と PR 本文の記入の後、`edited` で起きた新 run の全ジョブが green**

#### マージ後の終了条件(**DoD ではない**)

- [ ] **マージ後の develop の run が全ジョブ green**

## 6. テスト計画(NFR-019)

**要件が定義する CI のテストは 4 種**((a) 一致性 /(b) 越境 /(c) E2E 主要分岐 /(d) 同期故障系)。
**「単体」は `NFR-019` に存在しない** — `docs/development/templates/plan-template.md` の
「単体・一致性・越境・E2E・故障系」という 5 種の要約は誤りで、前計画書 6 節もこれを引いて誤帰属していた
(research.md 3-3 節)。本書は 4 種で書く。

| 種別 | 追加内容 |
| --- | --- |
| **(b) 越境アクセステスト** | ステップ **7・8・10・11・12・16** — 正例 / 拒否例 / **6 前提 × 認可行列各行** / 書き込み 8 権限 / 管理経路 probe / 信頼境界。**DB レベルの「0 行 / 権限拒否」まで**で、`404` の判定と 13 組合せクラスの残り 12 は TSK-217 |
| **(a) 一致性 /(c) E2E /(d) 同期故障系** | **追加なし** |
| **構成検査(要件の 4 種に属さない — 設計判断)** | ステップ **6** のカタログ検査 / ステップ **4** の冪等性とコミット境界 / ステップ **13** の TOCTOU / ステップ **14・15** の失敗注入 / ステップ **2** の body 静的照合。**`NFR-019` の種別として計上しない**(`data-model.md:239` が「越境テストとは別に構成そのものを検査する」と定める) |
| **mutation(要件の 4 種に属さない — 設計判断)** | ステップ **17〜20**。**`NFR-018`(b)② を根拠に引かない** — 同項の対象列挙(状況判定・座標変換・捕球選手推定・成績集計の前処理・終了判定)に**認可構成は入っておらず**、実装判断で対象に加える規定もない。**「3 変異で必ず red」という件数にも要件典拠がない**(要件の閾値は「非等価変異の生存 0」) |
| **回帰(本物の資産)** | `test_repository_oracle_assets_are_valid` / `test_repository_derived_assets_are_valid` ほか既存 72 件が green のまま。**第 1 弾(ステップ 1〜20)の全期間で凍結 15 パスのバイトが変わらない**ことを assert した。**本改訂では対象を 12 パスへ縮める** — **`ddl-elements` / `boundary-proposal` と seal は本改訂が変更するため、15 パス全体で差分 0 を要求すると正しい実装が必ず落ちる**(4 周目 `P0-2`。**`claim-mutant-map` は裁定 `D-15` で PR #3 へ移ったので不変側に戻った**) |

**既存のハードコード撤去は裁定 `D-16` で別タスクへ送った**(2 節の送り先表)。**第 1 弾の新設テストは資産由来の導出にした** —
既存のハードコードが過去に他タスクを red にした連鎖(`H-85`)があるため、新設分で同じ型を作らない。
**「20 箇所」という前提は 4 周目 `P1-8` で撤回した**(**根拠のない数だった**)。**件数は受取タスクが変異で確かめる。**

## 7. 検証(このタスクが終わったことの確認方法)

```bash
# 絶対パスで置く(相対パス + cd の組み合わせは 2 回目の cd で壊れる — 5 周目 `P1-4`)
WT=/home/ymdms/projects/pitchlog-worktrees/feature-pg-authz-verification-g2

# 1. 認可資産の検査(違反 0)
uv run python scripts/check_authz_catalog.py --root "$WT"

# 2-a. 凍結 15 パスのうち **12 パスが不変**であること(基準は origin/develop...HEAD)
#      本改訂は sealed_assets の 2 本と seal を変更する。差分 0 を要求すると必ず落ちる(4 周目 P0-2)
git -C "$WT" diff --exit-code origin/develop...HEAD -- \
  contracts/authz/requirement-claims.json contracts/authz/requirement-claims.lock.json \
  contracts/authz/route-registry.json contracts/authz/route-registry.lock.json \
  contracts/authz/auth-catalog.json contracts/authz/auth-catalog.lock.json \
  contracts/authz/http-route-matrix.json contracts/authz/http-route-matrix.lock.json \
  contracts/authz/rejected-configs.json contracts/authz/attack-tree.json \
  contracts/authz/verification-evidence.json contracts/authz/claim-mutant-map.json

# 2-b. 変更する 3 パス**それぞれ**に差分があること(1 本だけ変えて通る経路を塞ぐ — 4 周目 P1-4)
for p in contracts/authz/ddl-elements.json contracts/authz/boundary-proposal.json \
         contracts/authz/oracle-seal.lock.json; do
  git -C "$WT" diff --quiet origin/develop...HEAD -- "$p" && { echo "差分が無い: $p"; exit 1; }
done

# 2-c. 空白だけの変更で通らないこと — seal が持つ canonical_sha256 が実際に動いたかを見る
#      (2-b は差分の有無しか見ないので、意味の変化はここで確かめる — 4 周目 P1-4)
uv run python - "$WT" <<'PY'
import json, subprocess, sys
wt = sys.argv[1]
base = json.loads(subprocess.run(
    ["git", "-C", wt, "show", "origin/develop:contracts/authz/oracle-seal.lock.json"],
    capture_output=True, text=True, check=True).stdout)
head = json.load(open(f"{wt}/contracts/authz/oracle-seal.lock.json"))
assert base["oracle_commit"] == head["oracle_commit"], "oracle_commit が動いている"
assert base["oracle_commit_semantics"] == head["oracle_commit_semantics"], "semantics が動いている"
# 行の集合ではなく「行の列」で比べる — 辞書化すると重複行が潰れて見逃す(5 周目 P0-1)
bi = [(a["path"], a["git_blob_digest"]) for a in base["input_assets"]]
hi = [(a["path"], a["git_blob_digest"]) for a in head["input_assets"]]
assert len(hi) == 8, f"input_assets が 8 行でない: {len(hi)}"
assert len({p for p, _ in hi}) == 8, "input_assets の path が重複している"
assert bi == hi, "入力資産の行が動いている"
b = [(a["path"], a["canonical_sha256"]) for a in base["sealed_assets"]]
h = [(a["path"], a["canonical_sha256"]) for a in head["sealed_assets"]]
assert len(h) == 6 and len({p for p, _ in h}) == 6, "sealed_assets が 6 行の一意な集合でない"
assert [p for p, _ in b] == [p for p, _ in h], "sealed_assets の並びが変わっている"
changed = {p for (p, d), (_, e) in zip(b, h) if d != e}
expected = {"contracts/authz/ddl-elements.json", "contracts/authz/boundary-proposal.json"}
assert changed == expected, f"canonical が変わった資産が期待と違う: {changed}"
print("seal OK")
PY

# 2-d. 変更後の 3 ファイルに重複が 0 件であること(**本改訂の封印を守るのはこの実測**)
#      全配列の要素と全 JSON キー対を走る汎用走査。列挙を含まないので取りこぼさない。
#      実装はテストとして置く(scripts ではなく tests 側 — 実行証跡が CI に残る)
uv run pytest tests/test_check_authz_catalog.py -k reseal_targets_have_no_duplicates -q

# 2-e. 5 配列の多重度検査が実効を持つこと(seal の digest 不一致で判定していない)
#      多重度検査を外すと負例が red でなくなることを示す
uv run pytest tests/test_check_authz_catalog.py -k multiplicity -q

# 3. 品質ゲート一括(/check 相当)
(cd "$WT" && uv run ruff check . && uv run ty check && uv run pytest tests/)
(cd "$WT/backend" && uv run ruff format --check . && uv run ruff check . && uv run ty check && uv run pytest)

# 4. core-guard が新設資産にマッチすること(`core-areas.json` への登録はステップ 2 の射程)
uv run pytest tests/test_core_guard.py tests/test_ci_wiring.py

# 5. 正本へ触れていないこと(TSK-343 / TSK-348 の所有)
git -C "$WT" diff --exit-code origin/develop...HEAD -- docs/design/data-model.md docs/development/dev-harness-design-2026-08-07.md

# 6. 現在地導出(コードの無記法コミットが無いこと)
uv run python scripts/feature_status.py
```

**DB 必須テストの実行には `PITCHLOG_TEST_ADMIN_DSN` と `PITCHLOG_TEST_ROLE_DSN` の実値が必要**
(未設定は skip ではなく fail)。**ローカルでは人間が用意する**。CI では配線済み。

**人間が確認すること**(**本改訂の承認範囲 = ステップ 1〜2 の分**):
**oracle の reseal 差分が `sealed_assets` の 2 本だけであること** /
**`core-areas.json` の追加分(10 本 + 9 パターン)** /
**`boundary-proposal.json` の 3 境界の owner が閉じた表と一致し、`TSK-250` が残っていること** /
**`scope` の確定値が第 1 弾の実行結果に裏づけられていること**(**証跡は PR 本文と worklog**)。

**第 1 弾(ステップ 1〜20)で人間が確認した事項は PR #52 の逐行確認記録が正**であり、
**本改訂では再確認しない** — 関数 body の参照 relation / カタログ検査と `R-1`〜`R-8` の対応表 /
187 件の `db_basis_rule_id` と assertion の結合 / MC/DC の判定抽出。

## 8. 進め方

1. 本計画書 + [design.md](design.md) を**コア領域の敵対レビュー**へ:
   `python .claude/scripts/codex_run.py review adversarial -`
2. 指摘を反映(指摘反映を伴うレビュー 1 周ごとに frontmatter の `計画レビュー周回` を +1)
3. 収束したら**人間の承認**を求める → `承認: 済(YYYY-MM-DD・承認者)` へ
4. 承認後 `/implement` で**ステップ 1 から**委任する(1 委任 = 1 ステップ = 1 コミット・件名は `(ステップ k)` — **総数接尾辞は付けない**(4 節「ステップ番号の規律」))。**第 1 弾の 1〜20 は再実装しない** — **番号は 1 から振り直してあり**(2 節の実測: **merge-base 以降のステップ記法コミットが 0 件**)、**第 1 弾の表は「実装ステップ」見出しの配下から外して機構の射程外へ置いた**(4 周目 `P0-1`)

> **`承認: 未` の間、現在地導出はステップ進捗を表示しない。** `scripts/feature_status.py:1390` の `if not approved(frontmatter)` が**履歴走査より前に return する**ため、**第 1 弾が完了済みでも「計画段階(承認待ち)」と表示される**(`progress=Progress(kind="not_applicable", note="計画段階")`)。**進捗が失われたのではなく、改訂中は表示されないだけである** — **再承認後は本改訂の 0/2 から始まる**(**第 1 弾の進捗は merge-base の向こう側にあり、`feature_status.py:761` の走査範囲に入らない**)。改訂 3 の敵対レビュー 1 周目 `P1-5`
