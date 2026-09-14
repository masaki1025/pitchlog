---
feature: pg-authz-verification-g3
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2
branch: feature/pg-authz-verification-g3
created: 2026-09-09
計画レビュー周回: 38        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
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
| **D-13** | `guard_paths` の登録基準 | **規則で決める** — 「**凍結資産またはコア領域の成果物を検査する検査器とその対**」。**当面は規則から導いたパスを登録し、機械化は別タスクへ送る** |
| **D-14** | **改訂 3 第 2 弾の射程**(2026-09-12) | **2 本に分ける** — **本改訂(PR #2)= 封印系**(`S-1` の一部・`S-5`・`S-7` + owner 移管 + `S-8` の一部 — **`S-9` は裁定 `D-15` で PR #3 へ移した**)/ **PR #3 = ID 解決と受取契約**(`S-2`・`S-3`・`S-4`・`S-6`・`S-9`・`S-10` と **`S-8` のうち引き渡し 3 資産のパスと版・digest・`test_ci_wiring.py` の追記** — **`S-9` は裁定 `D-15` で追加**)。**理由**: 後者は**受取タスクの DoD へ書き込む必要があり、先方が未着手**である。**分ければ本改訂は実測だけで閉じられる** |
| **D-15** | **`S-9`(受取先 178 件)の射程**(2026-09-12) | **丸ごと PR #3 へ送る** — **`contract_only` 158 行は `contract_only_reason_code: route_universe_pending`**(**【2026-09-14 是正】実測は `route_universe_pending` 157 / `no_db_decision_point` 1** — **単一の理由コードではない**。`S-9` ① が既にこの混在を記録している)、すなわち**経路の母集合が未確定だから受取先が決まっていない行**である。**受取タスクの名も「受取先を決める」であり、決める前の状態を確定所有者として封印することになる**(計画レビュー 3・4 周目が 2 周続けて `P0` 指摘)。**`D-14` の「受取タスクが未着手なら PR #3」と同じ理由で一貫する。****本改訂が触る封印資産は `boundary-proposal.json` と `ddl-elements.json` の 2 本になる** |
| **D-16** | **期待件数のハードコード撤去(旧 3 ステップ構成のステップ 1)の射程**(2026-09-12) | **別タスクへ送る**([起票済み](https://app.notion.com/p/3d993b75e68781578e53d7a2268aded7))。**理由**: **構文的な走査で「ハードコードが無い」を閉じることはできない**。**計画レビュー 4・5・6 周目が 3 周連続で抜け道を指摘した**(コンテナリテラルの中の値 → 文字列・変数への退避 → **1 桁の文字列化と出現の置換**)。**性質が意味的なので、新タスクでは「走査で閉じる」をやめ、『資産を 1 要素増やした fixture でテストの期待値が追随する』を変異で確かめる設計で起こす。****本改訂とは独立**(実測 — **ステップ 2 が変えるのは `S-5` の status 文字列と `S-7` の scope 値で、件数ではない**)。**本改訂は 3 → 2 ステップになる** |
| **D-17** | **合格条件の書き方**(2026-09-12) | **検査基盤を先行ステップへ切り出す**。**理由**: **計画レビューが 12 周で同じ欠陥を 8 回、場所を変えて再生産した**。**P0 は 4 周連続ゼロなのに P1 が 1 → 3 → 4 と増えている** — **属性を箇所ごとに書いているため、レビューが合格条件を 1 つずつ順に当たる構造**になっていた。**規則 1 つ + 機構 1 つへ移し、周回が箇所数に比例しないようにする** |
| **D-19** | **試験設計の置き場所**(2026-09-12) | **計画書から `design.md` へ出す**。**理由**: **33 周で指摘が同じ 4 箇所(探針の軸 / `g` の入口 / DoD の 1 対 1 / 伝播漏れ)に出続けた**。**原因は計画書の中で「テストが完全であることの証明」を書こうとしていたこと**で、**探針を足せば軸が足りず、軸を足せば直積が足りない、と再帰的に終わらない**。**設計書 6.1 の plan = 契約 / design = 詳細設計へ戻す** — **計画書は「封印する値が正しい」「検査を外すと負例が通る」までの契約を持ち、導出器・探針・全数性・直積は `design.md` A〜F 節が正**(本書には複製しない — 7.1-1) |
| **D-18** | **検査基盤の射程**(2026-09-12) | **`D-17` を巻き戻し、検査基盤を丸ごと別タスクへ送る**([起票済み](https://app.notion.com/p/3d993b75e687810f8265fc44999fb9c2))。**理由**: **基盤自体が新しい `P0` を 3 件生んだ**(**条件 ID の母集合がまだ欠ける / ID が粗すぎて 1 個に 3 検査が束ねられる / 導出器 `g` が同ステップで変える検査器に依存して循環する**)。**22 周で実装が 1 歩も進んでおらず、基盤を計画書の文章で閉じようとするのをやめる** |
| **D-20** | **規則⑤ レビューが出した登録漏れ 7 件**(2026-09-13) | **本 PR で `tenant-isolation.paths` へ登録する**。**対象**: `backend/tests/` 直下の認可契約テスト 5 本(`test_authz_ddl` / `test_authz_mutation` / `test_authz_mutation_composition` / `test_authz_mutation_composition_full` / `test_authz_mutation_execution`)と、表権限契約の検査が使う支援機構とその試験(`wording_scan.py` / `test_wording_scan.py`)。**根拠**: 設計書 6.3「**判定に迷うコードは含む側に倒す**(fail-closed)」。**これらを変えれば DDL・mutation・表権限契約を弱められるのに強化レビューを迂回できる**(規則①)。**`wording_scan.py` は汎用処理を含むが規則② によりファイル全体が対象**。**7 件とも基準 `56c281c` に既存で非起因だが、`test_authz_mutation_composition_full.py` は本 PR が変更している**。**`guard_paths` は変えない**(規則⑤ レビューが 12 パスの exact-set を確認済み) |
| **D-21** | **規則⑤ 5 周目が出した同期の共通実装の未登録**(2026-09-13) | **本 PR で `sync-protocol` と `recording-rights` の両領域へ登録する**(規則③ の重複帰属)。**対象**: `frontend/src/lib/sync/receptionInput.ts` と `receptionInput.spec.ts`。**同期応答の受け取り境界の fail-closed 検査の単一実装**で、**`ackEnvelope` / `resendRange` ほか 7 ファイルが使う**のに**共通実装だけが未登録**だった。**根拠**: **使う側は全部登録済み**・**所有者が無く放置すれば誰も拾わない**(どの計画書にも言及 0 件 — 実測)・**依存ギャップのクラス全体を実測したところ 3 件のみで、うち 2 件は PNG 画像**なので**ロジックの穴はこの 1 組だけ**・設計書 6.3「**判定に迷うコードは含む側に倒す**」。**非起因**(基準版から既存) |
| — | `CONTROL-READS` の `aggregation_owner_task_id` | **裁定不要・事実の是正**(`aggregation_location: none` なのに owner がある資産の欠陥) |

**起票済みの受取タスク**:

- **`D-11`/`D-12` の受取先**: 「FR-041 共有集計の対象別生成と等価性契約」(`3d993b75-e687-818d-8cb8-ec57508e73e0`)
- **`contract_only` 158 行の受取先**: 「contract_only 158 行の runtime テスト受取先を決める」(`3d993b75-e687-8144-bd42-ee08d678b68f`)— **PR #3 の射程**

#### `D-13` の規則を実測へ当てた結果(2026-09-12・TSK-343 マージ後)

| 判定 | 検査器 | `f` が返す理由 |
| --- | --- | --- |
| **`f` が返す(既登録)** | `check_design_propagation` / `check_doc_coverage` / `check_processing_stages` | `areas[].paths` にマッチするファイルを開く |
| **`f` が返す(未登録)** | `check_authz_catalog` / `check_authz_function_bodies` / `check_mcdc_map` / `check_failure_injection_points` / `check_shared_preconditions` | `contracts/authz/` 配下を開く |
| **`f` が返す(未登録)** | **`check_docs_status`** | **`docs/design/data-model.md` ほか正本を開く**(**監査フックの実測で判明** — 静的検索では取りこぼしていた)|
| **`f` が返さない** | `check_nfr021_append_only` / `check_doc_profiles` / `check_plan_docs_sync` | どちらも開かない |

**`f` の出力 = 検査器 9 本 × 名前の対 = 18 パス。うち 6 パスは既登録、12 パスが未登録。**
**本改訂が足すのはその差分 12 パスである**(25 周目 `P1-1` — **以前は「コア領域該当なし」という
人手の判定を理由に書いていたが、合格条件は `f` の出力すべてが登録されていることである**)。
**判定は `design.md` C 節の述語を実行して得る**(**人手で解釈しない**)。

#### **`S-1` ④ の記録を撤回する**(2026-09-12)

**worklog に「`oracle_commit` は seal に存在しない」と記録したが誤りである。**
**原典**: `oracle-seal.lock.json:4` に**トップレベルの `oracle_commit`**(`dd2cb92...`)があり、**`check_authz_catalog.py:4521-4529` が 6 資産の `oracle_context.oracle_commit` との一致を要求**する。
**誤った理由**: **存在しない入れ子 `seal["oracle_context"]["oracle_commit"]` を見て `None` を得た**。**探す場所を人が選んで外した実測である。**
**本節の `S-1` は最初から正しい。**

### PO 裁定(2026-09-14 — **改訂 4**)

| # | 論点 | 裁定 |
| --- | --- | --- |
| **D-22** | **改訂 4 の射程**(2026-09-14・山田正輝) | **`S-9` + `S-10` へ絞る。** **裁定 `D-14` が PR #3 へ割り当てた 7 項目のうち 5 項目を送る**(下表)。**理由**: **3 項目が「いま閉じられない」ことが調査で分かった**(`S-2` は射程に穴・`S-3` は 7 単位が 1:1 に写せない・`S-6` は受取側 DoD が無く機械部分が実行不能)。**加えて `S-2` を含めると `auth-catalog.json`(入力資産)を触るので 2 段コミットが復活する** — **絞ると単一コミットで閉じる**(下記「封印は単一コミットで閉じる」) |
| **D-23** | **`reason_code` の owner 単位の畳み込み**(2026-09-14・山田正輝) | **畳まない。** **`contract_only_reason_code` は行の属性として扱い、owner 単位の不変条件は `receiving_task_id` にだけ課す**。**理由**: `FR-041/list_item-014` の 2 行が `no_db_decision_point` / `route_universe_pending` に割れるのは**資産の実態**であり、**TSK-367 の `plan.md:87`「行ごとの判定が割れたら即エラー」を `reason_code` へ拡張する根拠が見つからなかった**。**`S-9` ①(分割単位は `runtime_test_owner.id`)とは両立する** — **受取先は owner 単位・理由コードは行単位** |
| **D-24** | **文書内部整合の検査器**(2026-09-14・山田正輝) | **改訂 4 では作らない。別タスクへ送る。** **理由**: **既存 0 件で新規実装が要り**、パーサの罠が 4 つ(説明の丸括弧内の `/` / 継続短縮形 `-003` / `(+1)` 文法 / 同一キーの複数行)あり、**`guard_paths` 登録が 3 箇所へ波及する**。**台帳が繰り返し記録している「完全性の証明を本体と同じ射程に置くと輪になる」型そのもの**(TSK-348 の候補・TSK-363 で 2 例目)。**改訂 4 では一回限りの検証に留める** |
| **D-25** | **`U-T1`(TSK-363)の依存の欠落**(2026-09-14・山田正輝) | **別タスクとして起票した** — **[U-T1 の入力を確定する](https://app.notion.com/p/3db93b75e687813a9386f3b1f1e682ed)**(2026-09-14 起票)。**受取範囲**: ① `U-T1` の実装入力を資産のパスとキーで名指しする ② probe → 製品の写像規則を決める ③ `U-T1` のカードと TSK-363 の `design.md` の帰属表へ依存を追記する。**改訂 4 の射程に入れない。** **理由**: `data-model.md` が `U-T1` の構成要素 4 つ(`:238` 物理 DDL の書式 / `:244` `:2844` スキーマ検査の対象集合と合格述語 / `:246` 名前解決経路の非注入 / `:2845` RLS ポリシー・ロール DDL の実機確定)を TSK-317 へ送っているが、**TSK-363 の `U-T1` の依存列は `U-00` のみ**。**`ddl-elements.json` は `product_schema: false`(probe 構成)で、probe → 製品の写像規則が未作成** |

#### 改訂 4 で送るもの(**空手形にしない — 受取先を実 ID で書く**)

**すべて 2026-09-14 に起票済み。** **受取範囲を各カードの DoD に書いた。**

| 項目 | 受取先(**実 ID**) | 受取範囲 | 送る理由 |
| --- | --- | --- | --- |
| **`S-2`**(論理 ID → node ID) | **[論理 ID → pytest node ID の解決方式を決める](https://app.notion.com/p/3db93b75e6878113bed3cb8a5b33669d)** | **母集団を「TSK-270 所有の planned 論理 ID の全部」へ広げて確定** + 解決方式 + `status` を上げる条件 | **射程に穴**。`requirement-claims.json` に **TSK-270 所有が別に 193 参照**ある(`test_owner` 402 のうち 187 は auth-catalog と同一・残り 215 の接尾辞は `.http` 195 / `.cache` 20)。**`187 + 310` は全部ではなく、射程外とする根拠が資産にも本書にも無い** |
| **`S-3`**(要件側 7 単位の source) | **[要件側 7 単位の source を決める](https://app.notion.com/p/3db93b75e68781fc821fe62a4efd5af2)** | `FR-041/list_item-016` の裁定 + `stable_id` の源の確定 + `operation-count-mapping.json` | **7 単位の列挙がどこにも存在しない**。**`FR-041/list_item-016` が 2 操作を 1 行に含み `atomic_claims` の分割も無い**ので**安定 ID へ 1:1 に写せない**(資産側の `operation_ids` は 8) |
| **`S-4`** + **`S-8` の一部** | **[引き渡しマニフェストを新設する](https://app.notion.com/p/3db93b75e6878111b8a7e7111f3e510e)** | `handoff-manifest.json` の新設 + `tests/test_ci_wiring.py` への配線の固定 | **丸ごと新設**。**ID 集合の digest を持つフィールドは全資産に 0 件**・**元 commit は 2/3**・**blob digest は 1/3 しか記録が無く種類も割れている** |
| **文書内部整合の検査器** | **[文書の内部整合を検査する](https://app.notion.com/p/3db93b75e68781d694b2cf53a8b3d119)** | 件数ラベル vs 中身 + 名乗る母数 vs 実数の 3 段突合 | 裁定 `D-24`。**既存 0 件で新規実装が要り、パーサの罠が 4 つ・`guard_paths` 登録が 3 箇所へ波及する** |
| **`U-T1` の依存の欠落**(裁定 `D-25`) | **[U-T1 の入力を確定する](https://app.notion.com/p/3db93b75e687813a9386f3b1f1e682ed)** | 実装入力の名指し + probe → 製品の写像 + TSK-363 側への追記 | **TSK-363 はマージ済みでカード 23 枚も起票済み**。**追記であって単位の切り直しではない**ので別タスクが適切 |
| **`S-6`**(受取契約・`read-back`・製品 adapter) | **受取側の着手待ち** — **[TSK-250](https://app.notion.com/p/3c593b75e6878152b3edd6cf4f26b30b)** / **TSK-217**(**計画書・DoD がリポジトリに存在しない** — 射程の正は Notion カード本文) | **両者が DoD を持ってから**、安定テスト ID の登録・相互リンク・`read-back` の exact-set 突合 | **`[機械]` 部分が実行不能**。**両タスクとも未着手で DoD が存在せず、突合先が空**。**「製品 adapter」の定義がどこにも無い**(出現 4 箇所すべてが語の反復)。**`TSK-250` は `data-model.md` ではない**(`closure-handoff-data-model.json` が `source_task: TSK-342` / `destination_task: TSK-250` と記録)ので **v0.3 approved は前提を崩さない** |

> **`S-6` だけ新規起票していない。** **受取側が着手して DoD を持つまで、送っても受け取れないため**
> (**送り先が空手形になる、という台帳の候補そのものになる**)。
> **代わりに「何を待っているか」を上表に明記した** — **待っているのは TSK-250 / TSK-217 の DoD の存在である。**

### 計画レビュー 1 周目で訂正した前提(重要)

| # | 当初の記述 | 実測による訂正 |
| --- | --- | --- |
| 1 | 適用器を **1 トランザクション**にする | **誤り。** `ddl-elements.json` の `TX:PROVISIONING` は **`atomic: false`**(`ordered_application`)。原子なのは `TX:REPRESENTATIVE_MANAGEMENT`(`authorization_and_side_effect`)と、それだけ。**順序適用 + 冪等による収束**が正 |
| 2 | ステップ 17・18 を別コミットにして **reseal は 1 回** | **両立しない。** `boundary-proposal.json` と `ddl-elements.json` は**ともに封印 6 資産**。別コミットなら 2 回 reseal になる。**1 ステップ・1 コミット・1 reseal へ統合する** |
| 3 | reseal で **`oracle_commit` が更新される** | **誤り。** `_build_oracle_seal` は `input_assets[].git_blob_digest` と `sealed_assets[].canonical_sha256` だけを再計算する。`oracle_commit_semantics` は `last_committed_step_4_input_baseline` に固定で、検査器がその値を要求する |
| 4 | 資産の `status` を変えれば足りる(**【2026-09-14 陳腐化】本行が挙げる `candidate_probe_only` と `pending_human_decision` は既に反転済み** — 現値は **`verified_probe_configuration`** と **`human_decided`**。第 2 弾で消化された) | **足りない。** `check_authz_catalog.py` が `scope.status == "candidate_probe_only"` ほか 4 値と `PENDING-MANAGEMENT-COMMAND-COUNT.status == "pending_human_decision"`・`frozen_value == 8`・`alternative_value == 7` を**ハード要求**する。**検査器の契約変更を同一コミットに含める** |
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
**コミット構造の正はステップ表である** — **ステップ 2 の 1 コミットで資産変更と reseal を行う**
(25 周目 `P1-2` — **本節の「2 段コミット不要」は理由の説明であって、コミット数の定義ではない**)。
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
| `S-8` のうち **3 資産のパスと版・digest**・**`test_ci_wiring.py` の追記** | **PR #3** | `S-4` の ID 完全性に依存(**`test_ci_wiring.py` は引き渡し資産の配線を固定するので同じ単位**) |

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
| **`S-8` のうち `core-areas.json` の導出型検査**(**規則に合致するのに未登録のファイルを本番経路で検出する**) | **[core-areas.json の登録を導出型の検査で閉じる](https://app.notion.com/p/3d993b75e68781e6bcb4e42c79ddd789)** | **裁定 `D-13`** — **本改訂は `f` を負例の母集団の導出にだけ使い、本番経路へは組み込まない**。**組み込みは `core_guard.py` の変更を伴い、射程が別である** |
| **`S-8` のうち期待件数のハードコード撤去** | **[authz テストの期待件数ハードコードを資産由来の導出へ置き換える](https://app.notion.com/p/3d993b75e68781578e53d7a2268aded7)** | **構文的な走査では閉じられない**(3 周連続で抜け道)。**変異で確かめる設計に建て直す必要があり、本改訂の封印作業とは独立している** |

**本改訂に残る `S-8` は `core-areas.json` への登録だけ**である。

### やること — **改訂 4(本改訂の承認範囲 = 実装ステップ 1 本 + 本書で確定する文書)**

**「受取先の実 ID 化と、それを守る検査」に閉じる**(裁定 `D-22`)。

**塞いでいるもの**: `contracts/authz/claim-mutant-map.json` に
**プレースホルダ `receiving_task_id: "TSK-270-GROUP-2"` が 178 件**残っている(実測)。
**この置換が済むまで、認可主張の runtime テストを誰も所有できない。**

#### 消費する規則(**正は他タスクの文書**)

**受取先の規則は TSK-367(完了)が確定済み**で、**本改訂はそれを消費して `claim-mutant-map.json` へ書き写す側**である。
**規則の正は `docs/features/contract-only-runtime-handoff/plan.md` の 2 節**(develop にマージ済み)。

**引くときは commit を明記する** — **2026-09-14 時点の develop `569954d` では override 表が 44/46 で、
`:134` に改訂 2 の取り消し漏れがある**(下記「消費する側の防御」)。
**TSK-367 が `feature/tsk217-scope-alignment` で 6 件を是正中**で、**マージ後に引き直す。**

#### 封印は単一コミットで閉じる(**実測**)

**`claim-mutant-map.json` は `sealed_assets`(`asset_role: expectation`)側**であり、
**入力 8 資産(`check_authz_catalog.py:4800-4808` の `required_input_paths`)に含まれない。**

**したがって本改訂は `auth-catalog.json`(入力資産)に触れず、`oracle_commit` を動かす必要が無い。**
**`--reseal-oracle` のみ・単一コミットで閉じる。** **これは `S-9` ④ の逐語と一致する。**

**`S-2` を同じ改訂に入れると `auth-catalog.json` を触るので 2 段コミットが復活する** —
**実機で再現した**: `auth-catalog.json` を 1 文字変えると ① フラグ無しは `decision lock と不一致`
② `--reseal-derived` は lock を書くが同じ実行の oracle 段で落ちる ③ **`--reseal-oracle` は 1 バイトも書かない**
(`_build_oracle_seal` が `oracle_commit` を触らないため、`oracle_commit` 上の blob 照合が必ず落ちる)。
**「これから作るコミット」を基準点に指定できないことが 2 段コミットの機構的な理由であり、
`oracle_commit_semantics: "last_committed_step_4_input_baseline"` がその意味を持っている。**

#### 消費する側の防御(**文書が壊れている前提で組む**)

**宛先の導出を override 表だけに依存させない。** **override 表(`(+1)` 行を含む)+ `R-B` 内容表 +
`B_SET` 内訳の和**を取り、**`:134` を除外**し、**資産の非 FR-* 46 owner と exact-set で突合してから書き込む。**
**突合が合わなければ red にする。**

**根拠(2026-09-14 の実測)**: 資産の `U`(`contract_only` ∧ `receiving_task_id == "TSK-270-GROUP-2"`)は
**158 行 / owner 一意 152 / 非 FR-* 46**。**override 表は 44 しか持たない。**
**残る 2 件**(`NFR-019/paragraph-001` / `SECTION-8/list_item-002`)**は `R-B` 内容表と `B_SET` 内訳にだけある。**
**孤児 owner は 0 件だが、「全件」を名乗る表が母集団の一部しか持っていない。**

**これは資産の再導出では検出できない層である** — **資産から取れるのは「いま資産に何が書かれているか」だけで、
「文書が資産に対して何を約束しているか」は資産からは出てこない。**

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

> **【2026-09-14】現行の宣言は下の「【改訂 4】の反映」表が正。**
> **直下の表は改訂 3 第 2 弾(PR #59)の記録であり、現行の宣言ではない**(2 周目 `P1-7` —
> **`check_plan_docs_sync.py` が旧表の 2 件を現行宣言として読み、`status: in-review` へ移すと違反へ昇格する**)。

### 改訂 3 第 2 弾の反映 — **本節には置かない**(2 周目 `P1-7`)

**PR #59 で反映済みの宣言を本節に残すと、`check_plan_docs_sync.py` が現行宣言として読む**
(`affected_section_lines` は次の `## ` 見出しまでを射程にするため、`###` の小見出しでは切れない)。
**`status: in-review` へ移した時点で違反へ昇格し、PR ゲートを通らない。**

> **注記の書き方にも同じ罠がある** — **本節の散文で正本のパスをバッククォートや相対リンクで名指すと、
> それ自体が反映宣言として読まれる**(`markdown_link_paths` + `backtick_paths`。
> **`反映なし` を含む行だけが除外される**)。**本節では正本のパスを表以外で書かない。**

**記録は「第 2 弾の実施記録」節と [PR #59](https://github.com/masaki1025/pitchlog/pull/59) が持つ。**
**本節は改訂 4 の宣言だけを持つ。**

#### **【改訂 4】の反映**(**上表は改訂 3 第 2 弾のもの** — 本改訂の反映は下表が正)

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| [`docs/README.md`](../../README.md) | **反映なし**(索引に載る正本を変更しないため) | — |
| `.claude/core-areas.json` | **反映なし** — **`check_authz_catalog.py` と `tests/test_check_authz_catalog.py` は `guard_paths` に登録済み**(第 2 弾のステップ 1)。**新規パスを足さない** | — |
| [`docs/development/harness-evaluation.md`](../../development/harness-evaluation.md) | **反映なし**(現時点)。**`/pr` のクローズ処理で追記を判断し、該当するなら本節へ宣言を先に追記してから台帳を書く**(`pr/SKILL.md` 手順 1-3)。**該当しない場合は worklog に理由を残す** | PR レビュー |
| `docs/design/**` / `docs/requirements/**` / `docs/adr/**` / `docs/development/**` / `docs/ops/**` | **反映なし** | — |

**正本体系外で本改訂が変更するもの**:

| ファイル | 変更内容 |
| --- | --- |
| **`contracts/authz/claim-mutant-map.json`** | **178 件の `receiving_task_id` を実 ID / `PENDING:` へ置換**(`S-9`)。**`sealed_assets` 側なので `canonical_sha256` が変わる** |
| **`contracts/authz/oracle-seal.lock.json`** | **`--reseal-oracle` による再封印**。**`sealed_assets` の `claim-mutant-map` の行だけが変わり `oracle_commit` は不変** |
| **`scripts/check_authz_catalog.py`** | **受取先の文法と値域の検査を新設**(`S-10` (2)(3)) |
| **`tests/test_check_authz_catalog.py`** | **上記の正例・負例** |
| `contracts/authz/operation-count-mapping.json` | **本改訂では作らない**(`S-3` は裁定 `D-22` で送った) |
| `contracts/authz/handoff-manifest.json` | **本改訂では作らない**(`S-4` は裁定 `D-22` で送った) |
| **`contracts/authz/auth-catalog.json`** | **触らない**(`S-2` は裁定 `D-22` で送った)。**触ると 2 段コミットが復活する** |

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
| `scripts/check_authz_catalog.py` / `tests/test_check_authz_catalog.py` | **この中央 2 ファイルへは新設資産の検査を追加しない**(**実装済みのステップ 2・9・14 は、それぞれ独立した `scripts/check_authz_function_bodies.py` / `check_shared_preconditions.py` / `check_failure_injection_points.py` と対になるテストを新設しており、中央 2 ファイルは変更していない** — 実測。`S-8` もこの独立 6 パスを前提にしている)。**残るステップ 18 の `mcdc-map.json` も同じ形で独立した検査器を新設する。****status 契約の変更(`S-2`)は PR #3。****期待件数の撤去は裁定 `D-16` で別タスクへ。****本改訂が触るのは 3 件**(いずれもステップ 2。**対象資産は base の seal から導く凍結 15 パス**)— **① `S-5`・`S-7` の literal 追随** / **② 重複行で潰れる配列の多重度検査**(**母集団は導出器 `g` の出力** — 4 節 2-d の層 ①)/ **③ 凍結 15 パスの全配列 + 全 JSON キー対を走る恒久検査と、その負例 6 種**(同 層 ②。**`tests/test_check_authz_catalog.py` へ追加する**) |
| `tests/test_core_guard.py` | **本改訂のステップ 1 で変更する** — 新設パスの発火試験と `core-areas.json` への登録。**第 1 弾では変更しなかった**(裁定 `D-10`) |
| `backend/tests/db/test_authz_*.py` | **新設 12 本** — カタログ検査 / 越境の正例・拒否例 / 6 前提行列 / 表権限 8 種 / 管理経路 probe / TOCTOU / 失敗注入 / 信頼境界 / ロール接続 / 適用器 / mutation 全量。**`requires_db` マーカー付きで `backend/tests/db/` 配下**(`environment-expectations.json` の `required_path` 契約) |
| `backend/tests/test_authz_*.py` | **新設 5 本** — **DB を必要としない**契約試験(DDL 生成器 / mutation の判定機構 / executor の観測 / 2 因子合成 × 2)。**`backend/tests/db/` の外に置く**(DB 必須テストの path 契約と分けるため) |
| `scripts/check_shared_preconditions.py` / `check_failure_injection_points.py` / `check_mcdc_map.py` と、対になる `tests/test_check_*.py` | **新設 6 本** — 新設資産それぞれの独立した検査器(中央 2 ファイルへ足さない方針)。**`guard_paths` への登録は本改訂のステップ 1**(**中央 2 ファイルを含めて 12 パス** — 裁定 `D-13` の規則を監査フックで当てた実測) |
| `tests/test_check_authz_function_bodies.py` | **追随** — `manifest.json` の `source_commit` を注記追加後のコミットへ変えたため、「body 導入前のコミット」を `--diff-filter=A` で探す形へ変更(**assertion は不変・弱体化していない**) |
| `docs/features/pg-authz-verification-g3/{plan,research,design}.md` / `catalog-check-map.md` | feature 作業ディレクトリ(記録・正本ではない) |

## 4. 実装方針

### 重さ分類の根拠 — **コア領域(テナント分離)**

設計書 6.3 の境界定義表がテナント分離に「**テナント境界の認可判定すべて** = `FR-034` の認可行列・既定拒否を
中心に、`FR-033`/`FR-035`/`FR-037` の認可源・管理経路、`FR-041` の共有操作…+ `NFR-010` の越境防止」を含める。
本タスクの成果は**その認可判定の物理構成そのもの**である。
→ **`sol xhigh`・敵対レビュー必須・人間の逐行確認必須**(PR 作成者以外)。

**core-guard は発火する** — `contracts/authz/*`・`backend/tests/db/*`・`scripts/check_authz_catalog.py`・
`tests/test_check_authz_catalog.py`・`backend/pyproject.toml`・`backend/uv.lock`・`backend/*conftest.py`・
`docker-compose.yml` が `tenant-isolation.paths`(22 件)に登録済み(導入 `d4373ec`)。
**未登録は `backend/src/pitchlog/authz/*` と新設検査器 8 本**で、**本改訂のステップ 1 で登録する**([design.md](design.md) C 節が正)。**現在のステップ表は本改訂の 1〜2 である**(第 1 弾の 1〜20 は「第 1 弾の実施記録」へ移した)。

### 合格条件の書き方(5 つの規律)

1. **`[機械]`**(コマンドで判定できる)と **`[手動・外部]`**(人間が確認して worklog へ記録する)に
   **書き分ける**。**`[手動・外部]` を機械 green の一部として数えない**
2. **合格条件を「検査が green」に置かず「割り当てが正しい」に置く** — 検査は literal 一致で通るため、
   literal を置くだけで green にできる(7.3-3 が P1 と定める「文言は直したが実効がない」型)
3. **件数を定数で持たない**(`H-53`)— 母集合は資産から導出し、**ID 集合の sha256 で exact-set 突合**する
4. **母集団は列挙せず「導出元 `S` + 導出器 `f` + `f` の全数性を `S` 自身で示す」で書く**。
   **`S` は本ステップの diff の外にあり、計画書を書き換えても変わらないものにする。**
   **導出器と探針の設計は [design.md](design.md) A 節が正**(裁定 `D-19`)—
   **本書には複製しない**(設計書 7.1-1)。
5. **封印資産の値を変える負例は、当該 semantic validator を直接呼ぶ**。
   **封印資産の変異は `seal` の digest 不一致だけでも必ず red になる**ので、
   **`check_authz_catalog.py` 全体を回して red を見ても、目的の検査が効いている証拠にならない。**
   **検査コードの変異**と**CLI の副作用**は別の型で、
   **確かめ方は [design.md](design.md) A 節が正。**

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

**裁定 `D-8` と `D-9` により、第 1 弾の承認範囲は 20 ステップ(第 2 群前半)だった。****本改訂の承認範囲は 2 ステップ(封印系)である**(裁定 `D-14`・`D-16`・`D-18`)。**以下は第 1 弾についての記述である。** コア領域なので全ステップに人間の逐行確認が掛かり、
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

### 第 2 弾の実施記録(ステップ 1〜2・PR #59 でマージ済み)

> **見出しに「実装ステップ」を含めず射程外に置いた**(第 1 弾と同じ扱い — 4 周目 `P0-1`)。
> **機構が読むステップ表は下の「実装ステップ」節だけである。**

#### 第 2 弾のステップ表(**完了** — 封印系 1〜2)

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
| 1 | **`core-areas.json` への登録**(裁定 `D-13` + `S-8` の一部)— **`guard_paths` へ 12 パス**・**`tenant-isolation.paths` へ 9 パターン**(いずれも [design.md](design.md) C 節が正)**+ 裁定 `D-20` の 7 件**・**裁定 `D-21` の 2 件**(`sync-protocol` と `recording-rights` の両領域)。**封印資産に触れない** | `[機械]` **`f` の出力 18 パスと 9 パターンが登録されている**(exact-set)・**`tenant-isolation.paths` に追加した各パターンが実在ファイルへ 1 件以上マッチする**(**空振りのパターンを書けない**)・**裁定 `D-20` の 7 件それぞれで `core_guard.matched_paths()` が非空**・**負例: `D-20` の追加を 1 つ外すと red**・**`D-21` の 2 件が両領域それぞれ単独の設定で一致し、各領域から 1 件外すと red**・`uv run pytest tests/test_core_guard.py tests/test_ci_wiring.py` green。**負例の母集団と導出器は下記「ステップ 1 の登録先」** |
| 2 | **封印資産の確定と再封印**(owner 移管 + `S-5` + `S-7` + 検査器追随(**重複行で潰れる配列の検査を含む**)+ `--reseal-oracle` **1 回**)— **2-a 〜 2-e を 1 コミットに収める**(上記の理由)。**`oracle_commit` は動かさない**(入力資産が不変のため — 2 節の実測) | `[機械]` **2-a 〜 2-e の全条件を満たす**(下記)・**reseal 後に `check_authz_catalog.py` が rc=0**・**`--reseal-oracle` を付けない通常検証では reseal されない**。`[手動・外部]` **差分敵対レビューと人間査読**(`reseal_policy.human_review_required`) |

##### ステップ 1 の登録先 — **`D-13` の規則を当てた結果**(**実測で確定済み**)

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

`[機械]` **上表の全箇所が期待値と完全一致**・
**`deferred_equivalence_contract.owner_task_id` が実 ID と完全一致**。

**母集団・導出器・全数性は [design.md](design.md) D 節が正。**
**実測(2026-09-12)— `f` の出力は 5 箇所**(**私が数えていた 4 箇所ではない** — 13 周目 `P1-4`):

| パス | 現在値 | 本改訂の扱い |
| --- | --- | --- |
| `boundaries[0].aggregation_owner_task_id`(`SHARED-AUTHORIZED-ROWS`)| `TSK-235` | **`3d993b75-e687-818d-8cb8-ec57508e73e0` へ** |
| `boundaries[1].aggregation_owner_task_id`(`CONTROL-READS`)| `TSK-235` | **キーごと削除** |
| `boundaries[2].aggregation_owner_task_id`(`REPRESENTATIVE-MANAGEMENT`)| `TSK-250` | **不変** |
| `deferred_equivalence_contract.owner_task_id` | `TSK-235` | **`3d993b75-e687-818d-8cb8-ec57508e73e0` へ** |
| **`trust_boundary.verification_owner_task_id`** | `TSK-217` | **不変**(**現行 validator が検査していない** — **本改訂で検査を足す**) |

> **`trust_boundary.verification_owner_task_id` は私の列挙から漏れていた**(13 周目 `P1-4`)。
> **現行 validator もここを検査していないので、書き換えて reseal しても
> 私が書いた 4 箇所の負例はすべて通っていた。**
> **これが「自分で列挙した集合を `S` にすると縁が無検査になる」の実例である。**

**母集団の各要素について、期待から外れる変異で red になる**:

| 箇所 | 変異 | 期待 |
| --- | --- | --- |
| `SHARED-AUTHORIZED-ROWS` | **旧 owner(`TSK-235`)のまま維持** | red |
| `CONTROL-READS` | **owner を再追加する**(削除したはずのキーを戻す) | red |
| `REPRESENTATIVE-MANAGEMENT` | **owner を消す**・**別の値へ変える** | red |
| `deferred_equivalence_contract.owner_task_id` | **更新せず旧 owner のまま** | red |
| **`trust_boundary.verification_owner_task_id`** | **`TSK-217` 以外へ変える・消す** | red(**現行は green になる** — 本改訂で検査を足す)|

**加えて全箇所共通**: **形式だけ似た別 ID を入れると red / 空文字で red**。
**規律 5 により、負例は `validate_boundary_proposal` を直接呼び、その関数が投げることを確かめる**(**`check_authz_catalog.py` 全体を回して red を見ない**)。

> **「`aggregation_location: none` の境界に owner が無いこと」を合格条件にしてはならない**
> (4 周目 `P0-5` の実測)。**`REPRESENTATIVE-MANAGEMENT` も `none` で、正当な `TSK-250` owner を持つ**ため、
> **条件で一般化すると正しい実装が不合格になるか、正当な owner まで削られる。**
> **母集団は導出器の出力である**(実測 5 箇所 — [design.md](design.md) D 節)。
> **下表の 3 境界は「何をどう変えるか」の期待値であって、母集団の定義ではない**(24 周目 `P1-5` — **以前は「母集団は 3 境界の閉じた表」と断定していた**)。

**2-b `S-5` — `boundary-proposal.json` の裁定後の型を確定**

**資産と検査器を同時に変える**(下記「資産と検査器が二重に固定されている」)。

`[機械]` **`frozen_value` の差分が 0**・**`alternative_value` と `review_id` が不変**・
**検査器の literal が資産と一致**・**`tests/test_check_authz_catalog.py` が追随している**・
**母集団と全数性は [design.md](design.md) F 節が正。**

**base の全 leaf を 3 つに分類する**(**分類は本計画の確定値表から決める**)。
**新設する leaf は母集団に入らない** — **本改訂は `boundary-proposal.json` へ leaf を追加しない**(**`CONTROL-READS` の owner を削除するだけ**。**追加が出たら計画違反として別に検出する** —
**「base に無い leaf が変更後にある」を独立した合格条件にする**):

| 区分 | 期待 |
| --- | --- |
| **本改訂が変える leaf** | **確定値へ。確定値以外の値にすると red** |
| **本改訂が変えない leaf** | **変えると red**(**「不変」を明示していない leaf も含む**)|
| **本改訂が削除する leaf**(`CONTROL-READS` の owner) | **残っていると red** |

> **`S` を「検査器が literal 比較しているフィールド」にしてはいけない**(13 周目 `P1-3`)。
> **検査器は本改訂の同じステップで改変するので独立した `S` にならない**し、
> **`raw[...]` の AST 走査では `operation_review.get(...)` 形の比較を拾えない**
> (`check_authz_catalog.py:4380` — 実測)。
> **本計画自身の確定値表も `S` にできない**(**自分が書いた表だから**)。
> **独立しているのは資産そのものだけである。**

**変える leaf の確定値は下表**(**参考 — 合格条件は導出器の出力 × 上の 3 分類が正**):

| 変異させるフィールド | 期待 |
| --- | --- |
| `proposal_status` を確定値以外へ | red |
| 操作数レビューの `status` を確定値以外へ | red |
| 射程レビューの `status` を確定値以外へ | red |
| `frozen_value`(8)を変える | red |
| `frozen_value`(29)を変える | red |
| `alternative_value`(7)を変える・消す | red |
| **`alternative_value`(`null`)へ任意の値を入れる** | red(**`null` も「不変」の対象である** — 12 周目 `P1-2`)|
| `review_id` の `PENDING-` 接頭辞を改名する | red |

**加えて: 資産だけ変えると red / 検査器だけ変えても red**(**資産と検査器が二重に固定されていることの確認**)。
**規律 5 の validator は `validate_boundary_proposal`**(自己監査 2026-09-12 — **どれを呼ぶかを書かないと実装者が選べる**)。

**2-c `S-7` — `ddl-elements.json` の `scope` を確定**

`status: verified_probe_configuration` / `product_schema: false` /
`contains_sql_body: false` / `second_group_approval_required: false`。
**`check_authz_catalog.py:2673-2684` が 4 キーの exact 集合と 4 つの literal を要求する**ため、
**ここも資産と検査器を同時に変える**。

`[機械]` **4 キーが確定値と完全一致**・**検査器の literal が資産と一致**・
**`tests/test_check_authz_catalog.py` が 4 キーそれぞれの負例を持つ**。
**規律 5 の validator は `validate_ddl_elements`。**

`[手動・外部]` **「通った構成」の実行証跡は資産へ置けない** — **`scope` は 4 キー exact で、
参照フィールドを足すと `_expect_keys` が落ちる**(4 周目 `P1-7` の実測)。
**証跡は PR 本文と worklog へ置く** — **第 1 弾(PR #52 / `67e06a2`)の当該 CI run と、
そこで green になった検証ステップを明記する。**

**2-d 多重度の是正** — **層 ①(検査器の多重度検査)と層 ②(資産の恒久検査)の 2 層**。
**対象・導出器・探針・実測は [design.md](design.md) B 節が正。**

`[機械]` **層 ① の対象すべてに行数と要素一意性の検査がある**・
**層 ② の恒久検査が凍結 15 パスを覆う**・
**design.md B 節が定める負例すべてで red**・
**負例は当該 semantic validator を直接呼んで確かめる**(規律 5)。

**2-e oracle の再封印**(`--reseal-oracle` **1 回**)

`[機械]` **seal の `oracle_commit` が `dd2cb92...` のまま**・
**`oracle_commit_semantics` が `last_committed_step_4_input_baseline` のまま**・
**`input_assets[].git_blob_digest` 8 件が不変**・
**`sealed_assets[]` のうち `boundary-proposal` / `ddl-elements` の
2 本だけ `canonical_sha256` が変わる**(**残り 4 本は不変** — **`claim-mutant-map` は裁定 `D-15` で PR #3 へ**)。

**母集団と全数性は [design.md](design.md) E 節が正。**
**不変を要求した箇所それぞれについて、動かすと red になる**:

| 変異 | 期待 |
| --- | --- |
| `oracle_commit` を別のコミットへ | red |
| `oracle_commit_semantics` を別の literal へ | red |
| `input_assets` の 8 行のいずれかの digest を変える | red(**8 行すべてで**)|
| `sealed_assets` の**変えない 4 本**のいずれかの `canonical_sha256` を変える | red |
| `review_policy` / `reseal_policy` を変える | red |
| `schema_version` / `asset_kind` を変える | red |
| **`input_assets[]`/`sealed_assets[]` の行の `path` を変える** | red |
| **`sealed_assets[]` の行の `asset_role` / `asset_kind` を変える** | red |
| **`--reseal-oracle` を付けない通常検証で reseal される** | red |

**規律 5 により、負例は `validate_oracle_seal` を直接呼び、その関数が投げることを確かめる。**

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


### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

> **見出しに「実装ステップ」を含めるのは機構要件**。`.claude/scripts/codex_run.py` はステップ表を
> **見出しスタックで判定する**ため、小見出しは本見出しの配下に置くこと(祖先に「実装ステップ」があれば射程内)。

#### 実装ステップ — **改訂 4: 受取先の実 ID 化と封印(1 ステップ)**

> **【2 周目 `P0-2` で 3 → 1 へ】表に載せるのは「承認後に残る作業」だけである。**
> **当初の表はステップ 2「`S-10` の 9 論点に処置を付ける」・ステップ 3「射程宣言と送り先表を書く」を
> 含んでいたが、これらは本計画改訂そのものであり、承認時点で既に書き終えている。**
> **承認後に対応する実装差分が作れず、空コミットなしでは完了できなかった。**
> **文書の作業は計画そのものなので、ステップ表から外して「本改訂で確定したこと」として記録する。**
>
> **【初周 `P0-3`】「文法検査の新設」と「178 件の置換」を別ステップにして同一コミットへ載せる形も
> 規約違反だった** — **`feature_status.py:919` は 1 件名に 2 つのステップトークンがあると
> `inconsistent` を返す。** **1 つの論理ステップへ統合した。**

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | **受取先の検査を新設し、178 件を置換して `--reseal-oracle` する**(`S-9` + `S-10` (2)(3)(6))— **検査の新設と置換は不可分**(**資産に `TSK-270-GROUP-2` が 178 件ある以上、検査だけ先に入れると即 red になり完了点を作れない**)。**検査は 4 層**: **① 文法 ② 参照整合 ③ owner 単位の一致 ④ 差分閉包** | `[機械]` **下記「ステップ 1 の合格条件」が正** |

##### ステップ 1 の合格条件(**4 層すべて**)

**① 文法**

```
TASK_ID    ::= "TSK-" [0-9]{3}
PENDING_REF ::= "PENDING:" ( ("FR"|"NFR") "-" [0-9]{3} | "TASK-" [A-Z-]+ )
```

- **`TSK-270-GROUP-2` が文法から外れ red になる**(負例)
- **現行が非空文字列しか見ないこと**(`:3867-3868`)**を、検査を外した負例で示す**

**② 参照整合**(**初周 `P0-2`**)

- **`PENDING:FR-nnn` / `PENDING:NFR-nnn` は、要件書の条見出しに実在するものだけを許す**
- **母集団は `^#### (FR|NFR)-[0-9]{3}` にマッチする見出しから導出する**(2026-09-14 の実測で **65 件** —
  **FR-001〜042 の 42 + NFR-001〜023 の 23**)。**件数を定数で持たない**
- **`PENDING:FR-999` が red になる**(負例)
- **`PENDING:TASK-*` は要件書を参照しない**(起票済みタスクの別名。**実 ID へ解決するのが原則**で、
  **改訂 4 では `TSK-410` / `TSK-411` の 3 owner がこれに当たり、`PENDING:` を残さない**)

**③ owner 単位の一致**(`S-9` ①・`S-10` (3))

- **同一 `runtime_test_owner.id` の行は同一 `receiving_task_id` を持つ**。**共有 8 組で破ると red**
- **`reason_code` は畳まない**(裁定 `D-23`)— **行の属性のまま**

**④ 差分閉包**(**初周 `P0-4`**)

**閉じた集合を 3 段で書く**(**2 周目 `P0-4`** — **1 段目だけでは別の封印資産を同時に変えて reseal できた**)。

**段 1 — 変更してよいパスの閉じた集合**(**凍結 15 パス全体に対して**):

```
contracts/authz/claim-mutant-map.json
contracts/authz/oracle-seal.lock.json
```

**この 2 本以外の `contracts/authz/**` が 1 バイトでも変わったら red。**
**とくに他の封印資産 5 本**(`ddl-elements` / `rejected-configs` / `attack-tree` /
`boundary-proposal` / `verification-evidence`)**と入力 8 資産は不変であること。**

**段 2 — `claim-mutant-map.json` の中で変更してよいフィールド**:

- **`claims[].receiving_task_id`(対象 owner に限る)のみ。**
- **`claim_id` の集合が変わったら red**(行の追加・削除)。
- **それ以外のフィールドが 1 つでも変わったら red**(`reason_code` / `execution_class` /
  `runtime_test_owner` / `classification_rule_id` を含む)。
- **`oracle_context.oracle_commit` は不変。**

**段 3 — `oracle-seal.lock.json` の中で変更してよい値**:

- **`sealed_assets[]` のうち `path == "contracts/authz/claim-mutant-map.json"` の行の
  `canonical_sha256` だけ。**
- **`oracle_commit` / `oracle_commit_semantics` / `review_policy` / `reseal_policy` は不変。**
- **`input_assets[]` の 8 行は不変**(本改訂は入力資産を触らない)。
- **他の `sealed_assets[]` 5 行は不変。**

**この 3 段が無いと、対象外 owner を文法上有効な別の実タスクへ変えたり、
別の封印資産を同時に変更して `--reseal-oracle` したりしても、正規に封印できる。**

##### ステップ 1 の置換先の導出(**初周 `P0-1` で全 152 owner へ広げた**)

**当初は「3 表の和 − `:134`」を非 FR-* 46 owner とだけ突合する形にしていたが、閉じていなかった。**
**TSK-367 の正本 `:107` が `FR-034` の 51 owner の宛先を定めており**
(**heading 配下 48 − `heading-004/list_item-001` = 47 → `FR-041`** /
**`FR-034/list_item-002` = 1 → `FR-041`** / **残り 3 → `TSK-217`**)、
**FR 接頭辞を持つ owner も override の対象になる。**
**非 FR-* 46 とだけ突合すると、48 件を誤って `PENDING:FR-034` にしても件数条件は通ってしまう。**

**したがって母集団を `U` の 152 owner 全部にする。**

| 規則 | 対象 | 宛先の導出 |
| --- | --- | --- |
| **`R-A′`** | FR 接頭辞が宛先を返す owner | **`claim_id` の接頭辞の FR**。**ただしその FR が入口を開かない場合は執行先へ寄せる** |
| **`FR-034` の特例** | **51 owner** | **48 → `PENDING:FR-041`** / **3 → `TSK-217`**(`FR-034` 自身は入口を持たない) |
| **override 表**(`(+1)` 行を含む) | FR 接頭辞が宛先を返さない owner | **表の宛先** |
| **`R-B`** | 対象横断の判定とハーネス | **`TSK-217`** |
| **除外** | `NFR-012/list_item-003` | **`:134` は改訂 2 の取り消し漏れ。`FR-037` が正**(`:150` `:165`) |

##### `PENDING:TASK-*` の別名 → 実 ID の写像(**2 周目 `P0-3`**)

**TSK-367 の override 表は別名のまま**(`PENDING:TASK-RECOVERY` 2 件 / `PENDING:TASK-REQ-LABEL` 1 件)で、
**どの別名がどの TSK に対応するかを書いていない。** **書かないと、実装者が補完して受取先を逆にできる。**

| 別名 | owner | 実 ID | 典拠 |
| --- | --- | --- | --- |
| **`PENDING:TASK-RECOVERY`** | `SECTION-8/list_item-006` / `NFR-009/list_item-004` | **`TSK-411`** | [バックアップ復元の復旧手順を確定し検証する](https://app.notion.com/p/3da93b75e687818da3aac516470d8c40)。**カード本文が「受け取る 2 owner」としてこの 2 件を逐語で列挙している** |
| **`PENDING:TASK-REQ-LABEL`** | `SECTION-4.0-3/table_row-003` | **`TSK-410`** | [要件書: ラベル語彙のチーム拡張に対応する FR 条項を新設する](https://app.notion.com/p/3da93b75e68781fb978fedba7ef499e0)。**カード本文が「当該 owner」としてこの 1 件を名指ししている** |

**exact-set 突合は「別名を解決したあと」で行う** — **override 表の値をそのまま比較すると、
`PENDING:TASK-RECOVERY` と `TSK-411` が不一致になって実 ID 化と両立しない**(2 周目 `P0-3`)。

**合格条件**: **上表の写像で解決した結果が資産に書かれていること。**
**別名が 1 つでも残っていたら red。** **写像が逆になっていたら red**
(**owner ごとに実 ID を固定しているので、逆にすると owner と実 ID の対応が崩れる**)。

**合格条件**: **152 owner すべてに宛先が付き、置換結果が導出結果と exact-set で一致する。**
**どれか 1 つでも宛先が付かなければ red。** **件数はすべて資産と TSK-367 の正本から導出し、定数で持たない。**

##### 引く commit(**版が動く**)

**TSK-367 の `plan.md` は `feature/tsk217-scope-alignment` で 6 件が是正される予定**
(`:134` の取り消し漏れ / `:399` `:446` の古い件数 / `:156` の「全件」宣言 / `:164` `:165` のラベル)。
**改訂 4 は是正 PR のマージ後の版を引く。** **引いた commit を worklog へ記録する。**
**マージ前に実装する場合は、上表の「除外」で `:134` を明示的に外す。**

### 第 2 群後半・第 3 群 — **第 1 弾の承認範囲外だった要件の記録**

> **【2026-09-12】本節に残る「改訂 3 第 2 弾で確定する」「第 1 弾(本改訂)= 機械的な作業のみ」などの現在形は、いずれも第 1 弾当時の記述である。**
> **現在の射程は 2 ステップ**(`core-areas.json` 登録 / 封印資産の確定と reseal)**で、割り当ての正は 2 節の送り先表である。**

> **本節の `S-1`〜`S-10` のうち、`S-1`・`S-5`・`S-7` と `S-8` の一部(**`core-areas.json` への登録だけ**)が本改訂の射程である**(裁定 `D-14`)。
> **`S-2`・`S-3`・`S-4`・`S-6`・`S-9`・`S-10` と `S-8` のうち引き渡し 3 資産のパスと版・digest・`test_ci_wiring.py` の追記は PR #3**(**`S-9` は裁定 `D-15`**)。
> **`S-8` のうち期待件数のハードコード撤去は別タスク**(裁定 `D-16`)。
> **`S-8` は 4 つの送り先へ分かれる** — **割り当ての正は 2 節の送り先表である。**

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
> **`S-2`・`S-3`・`S-4`・`S-6`・`S-9`・`S-10` と `S-8` のうち引き渡し 3 資産のパスと版・digest・`test_ci_wiring.py` の追記は PR #3**(裁定 `D-14`・`D-15`)。
> **`S-8` のうち期待件数のハードコード撤去は別タスク**(裁定 `D-16`)。
> **割り当ての正は 2 節の送り先表である。**

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
| `S-8` | 引き渡し 3 資産のパスと版・digest(`ddl-elements.json` / `auth-catalog.json` / `rejected-configs.json` — **PR #3**)・`core-areas.json` への新設パス登録(**本改訂のステップ 1**。**下記「人手で列挙せず機械的に導く」は裁定 `D-13`(2026-09-12)が上書きした** — **本改訂は規則から導いたパスを登録し、導出型の一般化は別タスクへ送る**。**要件としての「機械的に導く」は撤回ではなく延期であり、受取先は [core-areas.json の登録を導出型の検査で閉じる](https://app.notion.com/p/3d993b75e68781e6bcb4e42c79ddd789)**)・`test_ci_wiring.py` の追記(**PR #3**)・期待件数のハードコード撤去(**別タスク — 裁定 `D-16`。「既存 20 箇所すべて」という旧方針は 4 周目 `P1-8` で撤回した**)・成果物の敵対レビュー。**`guard_paths` へ登録すべき新設検査経路の実測(2026-09-10・TSK-235 のタブからの申し送り)= 6 本**: `scripts/check_authz_function_bodies.py` / `scripts/check_shared_preconditions.py` / `scripts/check_failure_injection_points.py` と、それぞれ対になる `tests/test_check_*.py` 3 本。**現行の `guard_paths` 30 件は `check_design_propagation` / `check_doc_coverage` / `check_processing_stages` をスクリプトとテストの対で個別列挙**しており、**命名規約上この 6 本も入る系列**である。**未登録のままでは、凍結資産を検査するスクリプトを弱めても逐行確認が発火しない**(台帳 `H-12` の型 — `docs/README.md` に「再発 5 件目」が記録済み)。**`guard_paths` 追加は 6.3 規則⑤(敵対レビュー + 人間承認)**。**送り先記録(6 周目 `P2-1`・`(B)`)**: **上記「6 本」は 2026-09-10 時点の人手列挙であり、ステップ 18 で `mcdc-map.json` の独立検査器とそのテストを新設するので 8 本になる。****第 2 弾では登録母集団を人手で列挙せず、`scripts/check_*.py` と対になる `tests/test_check_*.py` の実在から機械的に導く**(**本タスクは「人が列挙した集合が母集団になっている」型の欠陥を 6 周のレビューで 7 回踏んでいる** — 走査の鍵 / セル内の位置 / 歴史的記録の分類 / 対象ファイルの選定 / 抽出キー / DoD の否定範囲 / **本項の `guard_paths` の列挙**。台帳候補 A・E と同型) | 1〜2 周目 / **2026-09-10 の申し送り** |
| `S-9` | **プレースホルダ受取先を実 ID へ置換する**(4 周目 `P1-9`)— 凍結資産に `receiving_task_id: TSK-270-GROUP-2` が **178 件**残っている(**実測** — `contract_only` 158 + `probe_executable` 20)。**残存 0 件**を条件にする。封印資産の変更なので `S-1` の基準コミットに含める。**確定済みの事実(改訂 3 第 1 弾で実測)**: **① 分割単位は claim 行ではなく `runtime_test_owner.id` である** — `FR-041/list_item-014#request-validation`(`no_db_decision_point`)と `#participant-authorization`(`route_universe_pending`)が**同一 ID を共有**しており(共有 6 組のうち理由コードが混在するのはこの 1 組だけ)、**claim 行で分けると 1 つのテスト ID を 2 タスクが所有する**。**② `probe_executable` 20 件は `runtime_target` を持ち TSK-317 の probe 経路で実行できる**。**③ `contract_only` 158 件は `runtime_target` を持たず、本計画は `product_schema: false` を宣言しているので TSK-317 は受取先になれない**。**④ `claim-mutant-map.json` は oracle 層なので `--reseal-oracle` で足りる**(`_validate_manifest` は要件書の変更だけを見るため掛からない — `S-1` の実測)。**具体の分割・受取タスクの起票・検査条件は改訂 3 第 2 弾で確定する**(裁定 `D-10`) | 4 周目 `P1-9` / 裁定 `D-9` / 改訂 3 第 1 弾 1〜2 周目 |
| `S-10` | **`contract_only` 158 行の受取契約を確定する**(**裁定 `D-9`・2026-09-10 で新設** — 旧ステップ 17 の置き換え)。**確定済みの規範**: **`R-7` が「`contract_only` は schema-drift kill + 受取タスクの runtime テスト ID」と定めるので、TSK-317 は実テストを書かない**(書くと同条が名指しで警戒する「契約 lint を実副作用 kill として数える抜け道」になる)。**`runtime_test_owner.status` は `planned` のまま動かさない。****改訂 3 第 2 弾で確定すべき論点(1〜2 周目の敵対レビューで洗い出した — いずれも実体〔ステップ 17〜20〕と実 CI が無いと合格条件を書けないため送る。裁定 `D-10`)**: **(1) 分類の exact-set の比較元と基準コミット**(`S-1` ② が同じファイルの `oracle_context.oracle_commit` も必ず変えるため、「ファイル差分が `receiving_task_id` だけ」では成立しない — 正規化して比較する形が要る。1 周目 `P0-3` / 2 周目 `P1-4`)**(2) 受取先の許容集合の検査**(現行検査器 `check_authz_catalog.py:3867-3868`(**【2026-09-14】`:3803` から行が動いた**)は**非空文字列しか見ない**ので、リテラルを置くだけで通る。1 周目 `P0-3`)**(3) 同一 `runtime_test_owner.id` の行が同一受取先を持つことの検査**(`S-9` ① の不変条件)**(4) `TSK-217` の 7 件の機械的分離****(5) 158 claim 行と 152 の一意 ID の対応**(6 組の共有を取りこぼさない・件数は定数で持たない)**(6) 凍結 15 パスの差分の基準区間**(`S-1` が凍結 15 パスのほぼ全体を変更対象にしているため、**「`S-1`・`S-9` が宣言した資産のみ」では任意の変更を `S-1` 名目で通せる** — **許可パスと許可フィールドの閉じた集合**が要る。2 周目 `P0-3`)**(7) 履歴を要する検査の CI 実行可能性**(**【2026-09-14 陳腐化・解消】`ci.yml:78` に `fetch-depth: 0` があり、履歴を要する検査は CI で実行可能である。以下は当時の記述** — **実測: root の `harness` ジョブは `fetch-depth` を指定しておらず浅い履歴**〔`ci.yml:75`〕。`<base>^` を要する検査は履歴取得なしでは解決できず、**スキップすると無効・fail-closed だと CI が常時失敗する**。2 周目 `P1-6`)**(8) 受取側からの read-back と exact-set 突合**(`S-6` と同じ形にするかを明示する — **明示しないとローカル資産へ受取先リテラルを置くだけで通る**。2 周目 `P1-5`)**(9) 受取タスクの DoD へ課す条件**(152 の安定 ID / 158 claim の被覆 / **各テストで「claim の述語が assertion に現れ、常時成功にすると red」**— 旧ステップ 17 の負例条件を受取契約へ移す) | 裁定 `D-9`・`D-10` / 改訂 3 第 1 弾 1〜2 周目 |

**改訂 3 の進め方**: **裁定 `D-9`(2026-09-10)により、改訂 3 は本計画のステップ 16 完了時点で開始した**(旧予定は「ステップ 21 の完了後」)。**裁定 `D-10`(同日)により 2 弾に分ける** — **第 1 弾(本改訂)= 機械的な作業のみ**(ステップ 17 の撤去・連番の振り直し・旧参照の除去・裁定と実測の記録)。**第 2 弾 = `S-1`〜`S-10` の機械条件の確定**で、**ステップ 17〜20 の完了後**に行う。`status` は `active` のまま、`承認` を `未` へ戻して改訂し、**コア領域なので敵対レビューを通してから人間の承認を求める**。**ステップ 1〜16 は番号が動かないため履歴の書き換えを伴わない。**

### 射程宣言 — **本書で確定する範囲 / 実装時に確定する範囲**(7.3-7)

**本書で確定する範囲**(**承認の対象**):

- **封印する値そのもの** — owner 5 箇所の期待値 / `S-5` の確定値表 / `scope` の 4 キー
- **ステップの分割と各ステップのコミット構造**(2 ステップ・封印資産の変更は 1 コミット)
- **母集団を導出元から得ること**(規律 4)と**負例が当該検査のせいで落ちていること**(規律 5)
- **送り先**(PR #3 / 別タスク 4 件)と**触らないもの**(`claim-mutant-map.json` ほか)

**実装時に確定する範囲**(**本書では確定しない**):

- **`design.md` A〜F 節の試験設計の細部** — **導出器の実装形・探針の生成の幅と深さ・
  全数性試験の具体形・比較元の実装**。**本書は「母集団は導出元から」「負例は当該 validator を
  直接呼ぶ」「当該検査を外すと負例が通る」までを契約とし、その満たし方は実装で決める。**
- **`<BASE>` の実 SHA** — **実装の最初のコミットの親**。**実装開始時に確定し worklog へ記録する。**
- **すべての実測値** — **`f` / `g` の出力・`w` / `d` の値。**
  **本書と `design.md` の数は参考であり、実装時に測り直して worklog へ記録する。**

> **この境界は計画レビュー 36 周の結果である**(2026-09-12)。
> **P0 は 9 周連続でゼロ**、**封印する値はレビューが独立に再現済み**(19 周目)。
> **残る指摘は「試験設計の精度」に集中しており、封印が壊れる型ではない。**
> **精度を計画書の文章で閉じようとすると再帰的に終わらない**ことが `D-19` で分かったため、
> **実装期に機構で満たす範囲として宣言する。**

### `S-10` の 9 論点の処置(**初周 `P1-5`** — 「確定する」だけでは足りない)

| # | 論点 | 処置 |
| --- | --- | --- |
| **(1)** | 分類の exact-set の比較元と基準コミット | **本改訂で確定** — **比較元は `origin/develop...HEAD` の merge-base 版**。**正規化して比較する**(ステップ 1 の層④)。**`S-1` ② が `oracle_commit` を変える問題は本改訂には無い**(入力資産を触らないので `oracle_commit` が動かない) |
| **(2)** | 受取先の許容集合の検査 | **本改訂で確定** — ステップ 1 の層①②。**行番号は `:3867-3868`**(`:3803` から動いた) |
| **(3)** | 同一 `runtime_test_owner.id` の行が同一受取先 | **本改訂で確定** — ステップ 1 の層③ |
| **(4)** | `TSK-217` の 7 件の機械的分離 | **本改訂で確定** — **置換後は 7 + 10 = 17**。**既存 7 件(`FR-033` / `FR-035` / `FR-036` 系・全件 `no_db_decision_point`)と本改訂が足す 10 件は互いに素**(実測)。**件数は資産から導出し定数で持たない** |
| **(5)** | 158 claim 行と 152 の一意 ID の対応 | **本改訂で確定** — **owner 単位で宛先を決め、行へ展開する**。**共有 6 組を取りこぼさない**(`U` の中の重複)。**件数は導出** |
| **(6)** | 凍結 15 パスの差分の基準区間 | **本改訂で確定** — **許可パスは `contracts/authz/claim-mutant-map.json` と `oracle-seal.lock.json` の 2 本だけ**。**許可フィールドは `claims[].receiving_task_id`(対象 owner に限る)と seal の `sealed_assets[]` の当該行のみ**。**閉じた集合で書く**(ステップ 1 の層④) |
| **(7)** | 履歴を要する検査の CI 実行可能性 | **解消済み** — **`ci.yml:78` に `fetch-depth: 0` がある**(2026-09-14 実測)。**当時の「浅い履歴」という前提は陳腐化していた** |
| **(8)** | 受取側からの `read-back` と exact-set 突合 | **書き分ける** — **`PENDING:FR-nnn` の 139 owner には課せない**(**受取タスクが 1 件も起票されていない**ため `read-back` の相手が無い)。**課せるのは `B_SET` 10(`TSK-217`)+ `TSK-410` 1 + `TSK-411` 2 = 13 owner**。**139 owner の置換義務の検査は本改訂では作らず送る**(下記) |
| **(9)** | 受取タスクの DoD へ課す条件 | **(8) と同じ書き分け** — **13 owner については受取タスクの DoD へ書く**。**139 owner については置換義務の検査へ**。**「claim の述語が assertion に現れ、常時成功にすると red」は受取契約として `S-6` の受取先へ送る**(受取側が DoD を持ってから) |

#### `PENDING:FR-nnn` 139 owner の後続義務の送り先(**2 周目 `P1-5`**)

**本改訂は `PENDING:FR-nnn` を残すが、「いつ誰が実 ID へ置換するか」を強制する検査は作らない。**
**作らない理由**: **「入口を開いたか」の機械判定が未整備**であり
(受け取り先は **[TSK-383](https://app.notion.com/p/3d993b75e68781ad8663dce3ac2484a2)**)、
**それ無しに「入口を開く PR が自分の owner を置換したか」は機械で判定できない**。
**本改訂で人手判定の検査を作ると、fail-open な検査を封印資産の守りとして固定してしまう。**

| 義務 | 送り先 | 内容 |
| --- | --- | --- |
| **入口を開く PR が同一 PR で自分の owner を置換する**(**過少も過剰も red**) | **[TSK-383](https://app.notion.com/p/3d993b75e68781ad8663dce3ac2484a2)**(「経路を開く」の機械判定を CI へ入れる) | **「入口を開いた」の機械判定が前提**。判定ができれば「開いた入口に対応する owner が `PENDING:` のまま残っていないか」を機械で言える |
| **各 FR の実装単位が自分の owner を置換する** | **[TSK-363 が起票した 23 単位](https://app.notion.com/p/3d893b75e68781de948bfe5ef4679652)の各カードの DoD** | **入口を開く 15 単位が対象**。TSK-363 は既にカードへ「入口を開く PR は同一 PR に直叩きテストを含む」を書いている。**owner の置換も同じ場所へ足す** |

**本改訂が作るのは「いま残っている `PENDING:` が文法と参照整合を満たすこと」までである**
(ステップ 1 の層①②)。**「いつ消えるか」は上記 2 つの送り先が持つ。**

#### `contract_only_reason_code` の導出をどうするか(**初周 `P1-5`**)

**本改訂は導出を変えない。** **理由**: `:3818-3836` の `expected_reasons` の導出は
**`_has_db_decision` / `runtime_target_kind` / `management_claim_ids` の 3 つに分岐しており、
`receiving_task_id` に依存しない。** **したがって受取先を置換しても `expected_reasons` は壊れない。**

**新しい理由コードも導入しない。** **`TSK-410` / `TSK-411` の 3 owner も `route_universe_pending` のまま**で、
**導出と矛盾しない**(**当該 claim に `location: db` の判定点があり、`runtime_target_kind` を持たず、
`management_claim_ids` に無い** → `{"route_universe_pending", "ddl_target_pending"}` のいずれか)。

**もし将来 理由コードを足すなら 2 箇所が要る** — **定数 `CONTRACT_ONLY_REASON_CODES`(`:118-120`)と
`expected_reasons` の導出分岐(`:3818-3836`)**。**定数追加だけでは `:3838` で
「導出理由と不一致」で落ちる**(2026-09-14 に実験で確認)。**本改訂はこの事実を記録するに留める。**

### 射程宣言 — **改訂 4**(7.3-7)

**本書で確定する範囲**(**承認の対象**):

- **受取先の値域と文法**(`TASK_ID` / `PENDING_REF` の 2 つの生成規則)
- **`claim-mutant-map.json` の 178 件の置換先**(**3 表の和 − `:134` を、資産の非 FR-* 46 と exact-set 突合**)
- **ステップの分割とコミット構造**(**実装ステップは 1 本・単一コミットで封印が閉じる** — **文書の作業は本書そのものなのでステップ表に載せない**)
- **`S-10` の 9 論点の「本改訂で確定 / 送る」の別**
- **送る 5 項目の受取先**(空手形にしない)

**実装時に確定する範囲**(**本書では確定しない**):

- **文法検査の実装形**(`re` か `_expect_closed_value` か、負例の生成方法)
- **3 表の和を取る実装**(パーサの罠 4 つ〔説明の丸括弧内の `/` / 継続短縮形 `-003` / `(+1)` 文法 /
  同一キーの複数行〕の扱い方)。**本書は「和を取り資産と exact-set で突合する」までを契約とし、
  その満たし方は実装で決める**
- **すべての実測値** — **178 / 158 / 152 / 46 の各値。**
  **本書の数は 2026-09-14 の実測であり、実装時に測り直して worklog へ記録する。**

**本改訂が確定しないもの**(**明示**):

- **`no_db_decision_point` → `TSK-217` の写像** — **これを定めた文書は存在しない**
  (2 系統の独立走査で追認)。**検査器は受取先について非空文字列しか見ていない**(`:3867-3868`)。
  **本改訂は「写像は無い」と記録するだけで、写像を作らない。**
- **既定 7 行の根拠** — **カード本文の「404 / 400 / 存在秘匿の同値性」は実データと合わない**。
  **7 行の `source_text` に `404` も `400` も 0 件**で、**存在秘匿は 1 行だけ**
  (残りはレート制限 2 / 認証構成の補足 1 / トークン失効 1 / PW ポリシー 1 / 人手の復旧経路 1)。
  **本改訂は事実を記録するだけで、根拠を作り直さない。**
- **`no_db_decision_point` → TSK-217 の 100% 一致を TSK-367 が意図的に崩した件** —
  **`FR-041/list_item-014#request-validation` を FR-041 へ回した**。
  **`_has_db_decision` を見た実装者が矛盾と誤認しないよう記録する。**

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

- [ ] **`f` の出力すべてが `guard_paths` に登録されている**(**`f` は [design.md](design.md) C 節が正**)
- [ ] **`f` の出力の各要素を 1 件ずつ外すと red**(**「いずれか 1 件」ではなく全件**)
- [ ] **`tenant-isolation.paths` へ [design.md](design.md) C 節の 9 パターンを登録した**(**既登録分を再登録していない**)
- [ ] **追加した各パターンが実在ファイルへ 1 件以上マッチする**(**空振りのパターンを書けない**)
- [ ] **design.md C 節が定める全数性試験と探針を実装した**
- [ ] **`f` の出力を実装時に測って worklog へ記録した**
      (**`f` を呼ぶ恒久テストを `tests/` へコミットしていない** — 恒久化は別タスク)
- [ ] **導出型の検査(規則に合致するのに未登録の 13 本目の検出)を作っていない**(裁定 `D-13`)
- [x] **6.3 規則⑤の敵対レビューと人間承認を通した**(**敵対レビュー 6 周で収束**・**人間承認 2026-09-13・山田正輝**)

#### ステップ 2 — 封印資産の確定と再封印(**1 コミット**)

**資産の値**

- [ ] **`boundary-proposal.json` の owner 5 箇所が 4 節の閉じた表と完全一致**
      (**`REPRESENTATIVE-MANAGEMENT` の `TSK-250` と `trust_boundary` の `TSK-217` は不変**)
- [ ] **`deferred_equivalence_contract.owner_task_id` が実 ID と完全一致**
- [ ] **`proposal_status` と 2 件の `status` が確定値**・**`frozen_value` / `alternative_value` / `review_id` は不変**
- [ ] **`scope` の 4 キーが確定値**
- [ ] **base に無い leaf が変更後にある場合は red**(**新設は計画違反**)
- [ ] **`claim-mutant-map.json` に触っていない**(裁定 `D-15` — `S-9` は PR #3)

**検査器**

- [ ] **検査器の literal が資産と一致し、`tests/test_check_authz_catalog.py` が追随している**
- [ ] **層 ① の対象すべてに行数と要素一意性の検査を置いた**
- [ ] **層 ② の恒久検査が凍結 15 パスを覆う**
- [ ] **`input_assets` の重複行を拒む検査を足した**(`sealed_assets` 側は既存のまま)

**試験設計**(**[design.md](design.md) A〜F 節が正** — 裁定 `D-19`)

- [ ] **母集団を 5 つとも design.md の導出器から得ている**(**計画書の表を母集団にしていない**)
- [ ] **design.md が定める全数性試験と探針をすべて実装した**
- [ ] **design.md が定める負例をすべて実装し、red になることを示した**
- [ ] **当該検査を外すと、その負例が red でなくなることを示した**(**負例がその検査のせいで落ちている証拠** — `D-19` が契約として残した条件)
- [ ] **封印資産の値を変える負例は、当該 semantic validator を直接呼んでいる**
      (`2-a` `2-b` = `validate_boundary_proposal` / `2-c` = `validate_ddl_elements` /
      `2-d` = 資産の区分ごとの入口 / `2-e` = `validate_oracle_seal`)
- [ ] **実測値をすべて実装時に取り直し、worklog へ記録した**(**数を計画書から取らない**)

**封印**

- [ ] **`--reseal-oracle` を 1 回だけ回した**
- [ ] **`oracle_commit` と `oracle_commit_semantics` が不変**
- [ ] **`input_assets` が 8 行のまま**(**重複なし**)で、**`git_blob_digest` 8 件が不変**。
      **`sealed_assets[]` の 2 本(`boundary-proposal` / `ddl-elements`)だけが変わった**
- [ ] **通常検証で reseal されない**(**design.md A 節の負例の形**)
- [ ] **「通った構成」の実行証跡を PR 本文と worklog へ記録した**(**`scope` へは置けない**)
- [ ] **差分敵対レビューと人間査読を通した**

#### 引き渡し

- [ ] **PR #3 へ送る 7 件を計画書へ受取先つきで書いた**(`S-2` `S-3` `S-4` `S-6` `S-9` `S-10` と **`S-8` のうち引き渡し 3 資産のパスと版・digest・`test_ci_wiring.py` の追記**)
- [ ] **`S-8` の 4 つの送り先を書き分けた**(**本改訂** = `core-areas.json` 登録 / **PR #3** = 引き渡し 3 資産のパスと版・digest・`test_ci_wiring.py` / **別タスク A** = 期待件数の撤去 / **別タスク B** = `core-areas.json` の導出型検査)
- [ ] **コア領域として敵対レビュー + 人間の逐行確認を通っている**(**逐行確認は PR 作成者以外**・**実施記録行を確認者本人が記入する**)
- [ ] **引き渡し前に PR HEAD の `core-guard` 以外の全ジョブが green**
- [ ] **人間の逐行確認と PR 本文の記入の後、`edited` で起きた新 run の全ジョブが green**

#### マージ後の終了条件(**DoD ではない**)

- [ ] **マージ後の develop の run が全ジョブ green**

### 本改訂が承認時点で既に確定していること(**ステップ表に載せない**)

**次の 3 つは本計画改訂そのものであり、承認された時点で完了している。**
**承認後の作業ではないのでステップ表に載せない**(2 周目 `P0-2`)。

| # | 確定したこと | 場所 |
| --- | --- | --- |
| 1 | **`S-10` の 9 論点すべてに処置を付けた** | 「`S-10` の 9 論点の処置」節 |
| 2 | **射程宣言と送り先表(実 ID つき)** | 「改訂 4 で送るもの」節・「射程宣言 — 改訂 4」節 |
| 3 | **陳腐化の是正** | `plan.md` / `design.md` の各該当箇所(**`【2026-09-14 是正】` で検索できる**) |

### 改訂 4 — **本改訂の受け入れ基準**

- [ ] **`TSK-270-GROUP-2` の残存が 0 件**(資産から導出・件数を定数で持たない)
- [ ] **置換先が 3 表の和 − `:134` と一致し、資産の非 FR-* 46 owner と exact-set で突合できている**
- [ ] **`PENDING:FR-nnn` の 139 owner は `PENDING:` のまま残っている**(**置換は入口を開く PR が行う** — 過少も過剰も red)
- [ ] **`TSK-410` / `TSK-411` の 3 owner は実タスク ID へ解決されている**(**起票済みなので解決できる** — 「着手済みか」ではなく「起票済みか」が判断基準)
- [ ] **`probe_executable` 20 件が `TSK-317`**(`S-9` ②)
- [ ] **文法検査が `TSK-270-GROUP-2` を落とす**ことを負例で示した
- [ ] **同一 `runtime_test_owner.id` の行が同一 `receiving_task_id` を持つ**ことを検査した(`S-9` ①)
- [ ] **`reason_code` は畳んでいない**(裁定 `D-23` — 行の属性のまま)
- [ ] **`oracle_commit` が動いていない**・**`auth-catalog.json` に触れていない**
- [ ] **`--reseal-oracle` のみを使った**(`--reseal` / `--reseal-derived` を使っていない)
- [ ] **`oracle_commit` 上の blob 一致を合格条件の根拠にしていない**(`:4796-4799` の fail-open)
- [ ] **派生資産の `input_manifest` のキー名を直接アサートしていない**(TSK-386 で 2 キーが消える)
- [ ] **`S-10` の 9 論点すべてに「本改訂で確定 / 送る」の別が付いている**
- [ ] **送る 5 項目に受取先がある**(`S-2` / `S-3` / `S-4` + `S-8` の一部 / `S-6` / 文書検査器)
- [ ] **TSK-367 からの依頼 3 点が読める**(規則は TSK-367 が確定済み / 本改訂は消費する側 / 正は先方の 2 節)
- [ ] **引いた commit を明記した**(TSK-367 の是正 PR のマージ前後で母数が変わる)
- [ ] **陳腐化 5 件を是正した**
- [ ] **`no_db_decision_point` → TSK-217 の写像が存在しないことを明記した**
- [ ] **コア領域の手続きを通した**(敵対レビュー + 人間の逐行確認)

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

> **【改訂 4】本節は改訂 4 の検証である。** **改訂 3 第 2 弾までの検証手順は
> 「第 2 弾の実施記録」の各ステップの合格条件が持つ**(初周 `P1-7` — **旧手順は
> `claim-mutant-map` 不変・`ddl-elements` / `boundary-proposal` / seal の変更を要求しており、
> 改訂 4 とは真逆だった**)。

```bash
# worktree ルートで実行する(絶対パス)
WT=/home/ymdms/projects/pitchlog-worktrees/feature-pg-authz-verification-g3
cd "$WT"

# 1. 残存 0 件と分布(資産から導出 — 件数を定数で持たない)
uv run python - <<'EOF'
import json, collections
d = json.load(open("contracts/authz/claim-mutant-map.json"))
c = collections.Counter(x["receiving_task_id"] for x in d["claims"])
assert "TSK-270-GROUP-2" not in c, f"残存 {c['TSK-270-GROUP-2']} 件"
print(sorted(c.items()))
EOF

# 2. 認可資産の検査(封印込み・違反 0)
uv run python scripts/check_authz_catalog.py

# 3. 差分閉包 — 変わったのが対象 owner の receiving_task_id だけであること
uv run python - <<'EOF'
import json, subprocess
base = subprocess.check_output(
    ["git", "show", f"{subprocess.check_output(['git','merge-base','origin/develop','HEAD'],text=True).strip()}:contracts/authz/claim-mutant-map.json"],
    text=True)
b = {c["claim_id"]: c for c in json.loads(base)["claims"]}
h = {c["claim_id"]: c for c in json.load(open("contracts/authz/claim-mutant-map.json"))["claims"]}
assert set(b) == set(h), "claim_id の集合が変わった"
diff = {k: (b[k], h[k]) for k in b if b[k] != h[k]}
for k, (x, y) in diff.items():
    changed = {f for f in set(x) | set(y) if x.get(f) != y.get(f)}
    assert changed == {"receiving_task_id"}, f"{k}: {changed}"
print(f"変更 {len(diff)} 行・変わったフィールドは receiving_task_id だけ")
EOF

# 4. oracle_commit が動いていない / auth-catalog.json に触れていない
git diff origin/develop...HEAD -- contracts/authz/oracle-seal.lock.json | grep -E '^[+-].*oracle_commit'  # 空
git diff --name-only origin/develop...HEAD | grep 'auth-catalog'                                          # 空

# 5. 正本反映の突合(本改訂は正本を変更しない)
uv run python scripts/check_plan_docs_sync.py --plan docs/features/pg-authz-verification-g3/plan.md --base origin/develop

# 6. 品質ゲート
uv run ruff check . && uv run ty check && uv run pytest tests/
```

**人間が確認すること**(**コア領域 — 逐行確認必須**):

| # | 観点 | なぜ人間が要るか |
| --- | --- | --- |
| 1 | **178 件の置換先が TSK-367 の規則と一致するか** | **規則の適用は意味判断を含む**(`R-A′` の「その FR が入口を開かない場合は執行先へ寄せる」) |
| 2 | **`FR-034` の 51 owner の割り当て**(48 → `FR-041` / 3 → `TSK-217`)**が正しいか** | **FR 自身が入口を持たない、という判断の妥当性** |
| 3 | **文法検査が `TSK-270-GROUP-2` を確実に落とすか** | 負例の十分性 |
| 4 | **差分閉包の許可集合が狭すぎ・広すぎでないか** | **広すぎると対象外 owner を正規に封印できる**(初周 `P0-4`) |
| 5 | **射程を `S-9`/`S-10` へ絞る判断**(裁定 `D-22`) | **裁定 `D-14` の再割り当てである** |

## 8. 進め方

1. 本計画書 + [design.md](design.md) を**コア領域の敵対レビュー**へ:
   `python .claude/scripts/codex_run.py review adversarial -`
2. 指摘を反映(指摘反映を伴うレビュー 1 周ごとに frontmatter の `計画レビュー周回` を +1)
3. 収束したら**人間の承認**を求める → `承認: 済(YYYY-MM-DD・承認者)` へ
4. 承認後 `/implement` で**ステップ 1 から**委任する(1 委任 = 1 ステップ = 1 コミット・件名は `(ステップ k)` — **総数接尾辞は付けない**(4 節「ステップ番号の規律」))。**第 1 弾の 1〜20 は再実装しない** — **番号は 1 から振り直してあり**(2 節の実測: **merge-base 以降のステップ記法コミットが 0 件**)、**第 1 弾の表は「実装ステップ」見出しの配下から外して機構の射程外へ置いた**(4 周目 `P0-1`)

> **`承認: 未` の間、現在地導出はステップ進捗を表示しない。** `scripts/feature_status.py:1390` の `if not approved(frontmatter)` が**履歴走査より前に return する**ため、**第 1 弾が完了済みでも「計画段階(承認待ち)」と表示される**(`progress=Progress(kind="not_applicable", note="計画段階")`)。**進捗が失われたのではなく、改訂中は表示されないだけである** — **再承認後は本改訂の 0/2 から始まる**(**第 1 弾の進捗は merge-base の向こう側にあり、`feature_status.py:761` の走査範囲に入らない**)。改訂 3 の敵対レビュー 1 周目 `P1-5`
