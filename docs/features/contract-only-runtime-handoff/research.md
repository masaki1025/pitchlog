---
feature: contract-only-runtime-handoff
type: research
date: 2026-09-13
---

# 調査メモ: `contract_only` 158 行の runtime テスト受取先(TSK-367)

## 問い

`contracts/authz/claim-mutant-map.json` の `claims` のうち**受取先が未確定の 158 行**について、
runtime 検査をどのタスクが受け取るかを決める。候補は 3 つ(Notion カード)—
**`TSK-217`** / **`TSK-344` 相当** / **製品機能の各実装タスク**。

調査は 3 本並列(spec-checker〔要件突合〕/ decision-tracer〔決定経緯〕/ Explore〔経路資産の解像度〕)。
調査時点(2026-09-13 午前)では **`ADR-004` / `data-model.md` v0.3 / 要件書 v2.8 は未マージ**で、
worktree `../pitchlog-worktrees/feature-merge-gate-clause` の版を典拠とした。

> **【2026-09-13 更新】3 正本は [PR #60](https://github.com/masaki1025/pitchlog/pull/60) で
> develop へマージ済み**(`0bc05b8`)。**本メモの `ADR-004` / `data-model.md` への参照は
> develop の版で読める**(内容は同一)。**本タスクの規則はこれらに依存していない**ため結論は不変。

## 結論(要約)

1. **方向は既に PO 裁定済みだった。** **裁定 `C`**(2026-09-12・山田正輝)が
   「**各 FR の実装タスクが自経路の HTTP 越境テストごと持つ**」と決め、
   「**単一の API 実装タスク**」を不採用にしている。**本カードの候補 3 が採択済み**で、
   **2026-09-12 13:48 に Notion カードのコメントで本タスクへ引き渡されている**。
   **本タスクの残作業は「方向を決める」ことではなく、規則の適用・例外の処理・引き渡し**である。
2. **受取先を「入口単位」で決めることは、現在の資産では原理的に不可能。** 3 段で独立に成立する
   — 入口を指す値が資産に無い / 158 行から `route_id` へ辿る写像が無い / 製品の HTTP 入口が 0 本。
   → **DoD 1 は「行ごと」では閉じられず、「群ごとの規則」でしか満たせない。**
3. **受け皿タスクが 1 件も実在しない。** 「製品 HTTP 経路(API)の実装 = **なし**」が実測記録されており、
   **裁定 `C` は「各 FR の実装タスクが持つ」と決めたが、その実装タスク群はまだ起票されていない**。
   **`S-10` の機械条件(受取側の read-back・受取タスクの DoD へ課す条件)が書けない**危険がある。
4. **分割単位は `runtime_test_owner.id`。** 母集団は **158 行 / 一意 152 ID**(共有 6 組)。
   **`route_universe_pending` 157 行で切ってはならない**(採用済みの不変条件に反する)。
5. **例外は `verification_contract` 7 行 + 入口の不在を主張する少数の行。**
   非 FR/NFR の 38 行は**大半が正真正銘の認可主張**であり、受け皿が無いわけではない(§5 で裁定)。

## 詳細と典拠

### 1. 裁定 `C` — 方向は決定済み(**最重要**)

**典拠**: `docs/worklog/2026-09-12-merge-gate-api-cycle.md:66`(PO 裁定・2026-09-12・山田正輝。逐語)

> | **C** 所有者 | **各 FR の実装タスク**が自経路の HTTP 越境テストごと持つ。**TSK-217 は対象横断の判定とハーネスの所有者として残し**、前提「FR-041 の実装が先。実装がないと構成できない」を**「FR-041 の実装 PR と同一変更」へ訂正**する | **「単一の API 実装タスク」を不採用**。契約の一貫性は 1 タスクで担保できるが、**そのタスク自身が最初のゲート通過の当事者になり、A・B が否決されると詰まる**。今回は A・B が通ったので致命ではないが、**per-PR の裁定 A と揃う方が構造が単純**である |

**引き渡しの記録**: 同 `:93`

> | **TSK-367**(既存) | 裁定 C = 本カードの候補 3。**射程は変えず方向だけ確定**。二重化を避けるためコメントで引き渡し |

**実際に引き渡されている**: Notion カードのコメント(2026-09-12T13:48:09Z・山田正輝)。逐語の要点 —

> **したがって 158 行のうち HTTP 経路に紐づくものは、原則として「その経路を開く FR の実装タスク」が受取先になります。**
> **TSK-217 が受け取るのは対象横断の判定**(認可行列の網羅・存在秘匿の同値性)**に限られます。**

**同 `:96`**: 「**製品 HTTP 経路の実装は単独タスクとして起票しない** — 裁定 C により各 FR の実装タスクが持つ。」

> **注意**: **裁定 `C` は正本ではない。** 同 `:43` が「**正本ではない** — Notion のタスク定義
> (設計書 7.4 の作業管理面。**確定ゲート不要**)」と明記している。
> 一方 **裁定 `A`・`B` は `ADR-004` + `data-model.md` 12-4 で条文化され、2026-09-13 に確定ゲートを通過**
> (`data-model.md:10` の変更履歴。**2026-09-13 に PR #60 でマージ済み**)。

### 2. 入口単位で決められないこと(3 段で独立に成立)

**① 入口を指す値が資産に無い**

- `method` / `http_method` / `verb` / `url` / `endpoint` / `uri` は **`contracts/authz/*.json` の全ファイルでヒット 0**
- HTTP 動詞リテラルも 0 件、`/api/...` 形の文字列も 0 件
- `route-registry.json:81` の唯一の `"path"` キーは値が `docs/features/pg-authz-verification/plan.md`(文書パス)
- 条文も同じことを言う — `data-model.md:2441`「**経路識別子は経路の識別子**であって、**入口の識別子ではない**」/
  `:2443`「**`route_id` と入口は 1 対 1 に対応しない**」

**② 158 行から `route_id` へ辿る写像が無い**

- `auth-catalog.json:14-38` の `route_scopes` は `route_scope_id` → **`route_kinds` の部分集合**を定義するだけ。
  **3 スコープは互いに重なっており**(`control_read` は 3 つすべてに属する)、**分割にすらなっていない**
- `SCOPE:DATA_READ` → 29 経路 / `SCOPE:CONTROL` → 12 経路 / `SCOPE:ALL_LOGICAL` → **37 経路全部**にばらける
- `auth-catalog.json` の `entries[]` に **`route_id` フィールドは 0 件**
- 代替経路も潰れている: `route-registry.json` の `routes[].source_claim_ids`(distinct **30 件**)と
  158 行の**交差 0 件** / `claim_dispositions`(185 件)とも**交差 0 件**

**③ 製品の HTTP 入口が 0 本**

- `backend/` の FastAPI 参照は `backend/src/pitchlog/main.py` の 1 ファイルのみ。
  ルートデコレータ総数 **1**(`main.py:8` の `@app.get("/health")`)。`APIRouter` は **0 件**
- その `/health` は境界例で**明示的に「開かない」**側 — `data-model.md:2494`
  「**DB のデータへ到達しない入口(`/health` など)| 開かない | 条件 3 を満たさない**」

→ **「開いている入口」は現時点で 0 本。** 受取先を既存の入口へ割り当てることは原理的に不可能であり、
**DoD 1 は「群ごとの規則」でしか閉じられない**(カードの DoD 1 が最初から選択肢を持つのはこのため)。

### 3. 分割単位 — **158 / 152 で切る。157 で切らない**

**典拠**: `docs/features/pg-authz-verification-g2/plan.md:710`(`S-9` 確定事実 ①・4 周目 `P0-2` 採用済み)

> **① 分割単位は claim 行ではなく `runtime_test_owner.id` である** — `FR-041/list_item-014#request-validation`(`no_db_decision_point`)と `#participant-authorization`(`route_universe_pending`)が**同一 ID を共有**しており(共有 6 組のうち理由コードが混在するのはこの 1 組だけ)、**claim 行で分けると 1 つのテスト ID を 2 タスクが所有する**。

**実測**(本タスクで再測。`contracts/authz/claim-mutant-map.json` を直接パース):

| 区分 | 値 |
| --- | --- |
| `claims` 全体 | 198 行 / `runtime_test_owner.id` 参照 198・一意 187・共有 8 組(余剰 11) |
| `execution_class: contract_only` | **165 行** |
| うち `receiving_task_id: TSK-270-GROUP-2`(未確定)| **158 行 / 一意 152 ID / 共有 6 組(余剰 6)** |
| うち `receiving_task_id: TSK-217`(確定済み)| 7 行(いずれも専用 owner を 1 対 1 で持ち、共有なし) |
| 158 行の理由コード | `route_universe_pending` **157** / `no_db_decision_point` **1** |

**不変条件**(同一 `runtime_test_owner.id` → 同一 `receiving_task_id`)は**全 8 組で成立**を再確認。

> **カード本文・TSK-317 の申し送りの誤り 3 件**(いずれも実測で確認・別タブも追認済み):
> **① ファイル名** — `claims` 等は `claim-mutant-map.json` にある(`auth-catalog.json` ではない)。
> **② 母集団** — 「`contract_only` が 158 行」ではなく「**165 行のうち未確定が 158 行**」。
> **③ 共有 ID** — 「8 組 / 重複 11」は**全 198 行**の数字。**158 行の中は 6 組 / 6**。
> **裁定 `D-15`(`docs/features/pg-authz-verification-g2/plan.md:90`)の「`contract_only` 158 行は `route_universe_pending`」も 1 行分不正確**
> (`D-9` ③ は「157 件」と正しく書いている)。

### 4. 受け皿タスクの不在(**最大の障害**)

**典拠**: `docs/features/merge-gate-api-cycle/research.md:362`(Notion 精査 2026-09-12 後のタスク配置表)

> | **製品 HTTP 経路(API)の実装** | **なし** | — | **12-4 のゲート** |

- `docs/worklog/2026-09-12-merge-gate-api-cycle.md:86-94` の引き渡し一覧で新規起票されたのは
  **TSK-379 / TSK-380 / TSK-381 の 3 件のみ**。**FR 実装タスクは 1 件も含まれない**
- ハーネス設計書も枠組みを定めていない — `docs/development/dev-harness-design-2026-08-07.md:894, :898`
  「**要件書の FR が定める製品機能の実装は、本章の Phase の対象外とする**」
  「**本節は製品機能の実装について順序・群・段階を定めない**」

**これは `D-14` が PR #3 を分けた理由そのものである** — `docs/features/pg-authz-verification-g2/plan.md:89`
「**受取タスクの DoD へ書き込む必要があり、先方が未着手**」。
**受取先を未起票のタスク群に置くと、`S-10` の機械条件((2) 受取先の許容集合の検査 /
(8) 受取側からの read-back と exact-set 突合 / (9) 受取タスクの DoD へ課す条件 — `docs/features/pg-authz-verification-g2/plan.md:711`)が書けず、
同じ詰まりを再生産する。**

### 5. エージェント間の食い違いと裁定 — **受け皿を持たない行は 38 ではなく 7 + 少数**

**食い違い**: Explore は「例外は `verification_contract` 7 行 + 1 行」、
spec-checker は「**非 FR/NFR の 38 行**が製品機能の実装タスクを持ちえない」と報告した。

**原典で裁定した(本タスクの実測)。spec-checker の 38 行は過大である。**

`claim_id` の系統と `layer` を交差集計すると、両者の重なりは **2 行だけ**(`SECTION-8/list_item-002`・`:006`):

| 系統 | 行数 | 主な `layer` |
| --- | --- | --- |
| **FR/NFR** | **120** | access_control 56 / operation_authorization 37 / authentication_boundary 12 / cache_authorization 9 / **verification_contract 5** / entry なし 1 |
| SECTION-3(ステークホルダー)| 10 | access_control 7 / operation_authorization 2 / authentication_boundary 1 |
| APPENDIX-C | 5 | authentication_boundary 4 / operation_authorization 1 |
| SECTION-2.2(**Won't**)| 4 | operation_authorization 3 / authentication_boundary 1 |
| SECTION-9(リスク表)| 4 | access_control 3 / operation_authorization 1 |
| APPENDIX-ITEM-A-5 | 3 | access_control 3 |
| SECTION-1.1 / 4.0-1 / 4.0-3 | 2 / 2 / 2 | access_control 2 / operation_authorization 4 |
| **SECTION-8(リリース判定基準)** | **2** | **verification_contract 2** |
| SECTION-4.0-2 / 6.2 / 6.4 / 7.1 | 1 / 1 / 1 / 1 | operation_authorization 2 / cache_authorization 1 / access_control 1 |

**非 FR/NFR の 38 行は、`contracts/authz/requirement-claims.json` で `classification: auth_claim` を持つ
正真正銘の認可主張である**(`classification_rule_id` は `AUTH_OPERATION_PERMISSION` /
`AUTH_ACCESS_SCOPE` / `AUTH_PRINCIPAL_STATE` など)。**要件書の非 FR 章から引かれているだけで、
入口で執行される主張であることに変わりはない。** 実例(`source_text` 逐語):

- `SECTION-2.2/list_item-002` — 「同一試合の複数人同時入力のマージ(入力は1試合につき1端末。**記録権 FR-013 が機構として保証**。閲覧は同時複数可)」→ **FR-013 の実装タスクが受ける**
- `SECTION-4.0-2/list_item-001` — 「**物理削除しない**: 利用者操作はすべて論理削除まで。物理削除はシステム管理者のDB保守作業のみ」→ **全変更系入口で執行される**
- `SECTION-3/heading-001/list_item-001` — 「**テナント**: ログインする契約チーム。データ分離の単位(NFR-010)」→ **access_control**

**したがって受け皿を持たない行は次の 2 群に絞られる**:

**(a) `layer: verification_contract` 7 行**(`db_basis_rule_id: DB_VERIFICATION_QUERY`)—
**入口の認可判定ではなく「検証手段」「リリース判定基準」の記述**。裁定 `C` の規則が当たらない:

`FR-034/heading-004/list_item-001` / `NFR-010/list_item-004`(測定方法)/ `NFR-011/list_item-003`(測定方法)/
`NFR-012/list_item-003`(測定方法)/ `NFR-019/paragraph-001`(正解ベクタの定義)/
`SECTION-8/list_item-002`(CI 全グリーン)/ `SECTION-8/list_item-006`(バックアップ復元リハーサル)

→ **裁定 `C` が `TSK-217` に残した「対象横断の判定とハーネス」と性格が一致する。有力な受け皿。**

**(b) 入口の不在を主張する行**(Won't 由来の一部)— 例 `SECTION-2.2/list_item-012`
「**セルフサインアップ**(チーム登録はシステム管理者による手動オンボーディング)」。
**入口を開かないことが要件なので「開く PR」が定義上存在しない。**
Won't 4 行のうち `list_item-002`・`list_item-008` は positive な主張で FR 側が受けられるため、
**厳密に (b) に当たるのは少数**。**行ごとの確定は計画段階で行う。**

### 6. 既定 7 行が `TSK-217` である根拠 — **「404/存在秘匿」ではない**

**割り当ての実際の根拠は機械的な分類である。** `scripts/check_authz_catalog.py:3357-3362` / `:3818-3821`:

```python
def _has_db_decision(claim: dict[str, object]) -> bool:
    decisions = claim.get("decidable_at")
    return isinstance(decisions, list) and any(
        isinstance(decision, dict) and decision.get("location") == "db"
        for decision in decisions
    )
```
```python
            if not _has_db_decision(source_claim):
                expected_class = "contract_only"
                expected_rule = "CONTRACT_ONLY_NO_DB_DECISION_POINT"
                expected_reasons = {"no_db_decision_point"}
```

→ **`decidable_at` に `db` を 1 件も持たない claim**(= HTTP 層でしか判定できない)が `no_db_decision_point`。

**7 行の実際の内容を `source_text` で確認したところ、存在秘匿に当たるのは 1 行だけ**である
(`FR-033/list_item-005`「失敗理由からチーム名の存在やパスワードの部分一致が推測できない」)。
残る 6 行はレート制限 2 / 認証構成の補足 1 / トークン失効 1 / PW ポリシー 1 / 人手の復旧経路 1。
**共通項は「認証境界であり DB に判定点を持たない」ことであって、「404/400/存在秘匿」ではない。**

> **`no_db_decision_point` → `TSK-217` という写像そのものを定めた文書は見つからない**(不明)。
> **`TSK-217` の計画書・DoD もリポジトリに存在しない**(`merge-gate-api-cycle/research.md:265`)。
> 射程は他タスクの委譲と Notion 本文でのみ確定 — 「**越境テストの実装のみ。API 実装を含まない**」(同 `:295-299`)。

### 7. `NFR-010` の「API直叩き含む」は誰への要求か — **条文からは決まらない**

`docs/requirements/requirements-pitchlog-2026-07-22.md:846`:

> - **測定方法**: 越境アクセスの自動テスト(API直叩き含む。CIに常設 → NFR-019)

**主語・述語を持たない体言止めの名詞句**であり、動作主を名指す語が無い。
**この「決まらなさ」は記録済みの事実である** — `ADR-004:68-71`:

> **条文だけでは決着しなかった。**(…)**同一文書の中で引っ張り合っており、字面の読みだけでは決まらない。** そのため PO 裁定を求めた。

→ **(a) 製品機能を実装する PR への要求**が現行の答えだが、**根拠は `NFR-010` の条文ではなく
`data-model.md` 12-4 + 裁定 `B`** である。`ADR-004:152` は「`NFR-010` を改訂する」案を**不採用**にしたため、
**`NFR-010` 本文は二読可能なまま残っている**。

### 8. `NFR-019(b)` の発効条項(**2026-09-13 マージ済み**)

**worktree 側 v2.8** `docs/requirements/requirements-pitchlog-2026-07-22.md:930`(逐語の要点):

> **本項(b)の越境テストは、対象となる経路が実装され、製品の外からの要求がその経路を通ってデータへ到達できるようになった時点をもって、その経路について発効する。発効前の経路に係る組合せを理由に本項(b)を不合格と判定してはならない**(…)。**未発効は網羅の免除ではない** — **上記に列挙した組合せを1件も減らさない**。**網羅がいつ成立していなければならないかは8章のリリース判定基準2が定めており、本条項はこれを変更しない**。

**調査時点のメインツリーには無かったが、PR #60(`0bc05b8`)で develop へ入った。**
**`requirement-claims.json` の `NFR-019/paragraph-001` の `source_text` も同時に更新された**
(本タスクの `B_SET` に含まれる owner。**受取先 `TSK-217` の判定は変わらない** — 追加された発効条項は
`(b)` の発効時点を定めるだけで、この owner の中身〔比較単位と正解ベクタの定義〕を変えていない)。
**発効は「経路」単位、12-4 のゲート判定は「入口」単位**という組合せになる
(`ADR-004:166-170` — 裁定は経路単位で下されたが条文は入口単位へ精密化。人間承認で明示確認)。

### 9. バッチ・内部経路の混入 — **0 件**(反証候補の消滅)

12-4 の境界例は「**バッチ(スケジュール実行・移行)は開かない**」(`data-model.md:2492`)、
「**内部経路は開かない**」(同 `:2491`)と定める。**該当行があれば裁定 `C` の規則は当たらない**が、実測は 0 件:

- `SCOPE:ALL_LOGICAL` は「HTTP 以外」ではなく「**論理経路の全体**」の意味
  (`route_kinds` の全 4 値 = `legacy_route` / `shared_data` / `control_read` / `management_operation`)。
  **列挙に batch / job / internal / migration に当たる値は 1 つも無い**
- 要件書本文の語彙スキャン(バッチ / 移行 / スケジュール / cron / ジョブ 等)で**バッチ起動の主張は 0 件**
- **移行を扱う `FR-038` 由来の claim は 158 行に 1 件も含まれない**
- `ddl-elements.json` の `functions` 3 件は全て `execute_role_ids: ["app_role"]`(= アプリ経路から呼ばれる)。
  **バッチ実行ロールも移行実行ロールも定義されていない**

> **留保**: 資産には「その主張がどの起動経路で成立するか」を記録するフィールドが**そもそも存在しない**。
> 上記 0 件は**要件書本文の語彙と `route_kinds` 列挙からの判定**であって、宣言的な根拠ではない。
> **機械判定には各 claim に到達経路の種別を持たせるフィールドが要る** —
> これは設計書自身が **`TSK-383`**(「入口を開く」の機械判定)へ送っている論点と同じもの(`data-model.md:10`)。

### 10. 隣接タスクとの射程境界

- **`TSK-380`**: `ADR-004:46` が **`http-route-matrix.json` の 37 経路の `test_owner` 再割り当て方式**を割り当て済み。
  現行は全件 `TSK-217.http-route.*`(`http-route-matrix.json:42-43` ほか)。
  **本タスクが「実装タスクへ割る方式」を決めると表裏になる** → **踏み込まない形にする**
- **`TSK-382`**: `SP-06` と 12-4 の射程外宣言・non-serving の字面衝突(`ADR-004:41-47`)。
  **non-serving の意味へ踏み込む必要が出たら送る**
- **`TSK-346`**: `NFR-010` が API 境界でどう効くか(404 / 403 の使い分け・情報漏洩の境界)
- **`TSK-381`**: `TSK-344` の DoD の見直し。**別タブが進行中**。
  `DoD 4` の帰結は **(a) 空の要求**で確定(`data-model.md` の測定経路行)
  → **`TSK-344` が受け取る行は 0 件**という本タスクの見立てと整合する。
  ただし「空」は削除でも免除でもなく、**`TSK-344` は「対象入口なし」と記録する義務を負う**
- **`TSK-367` は `ADR-004` の射程宣言表に現れない**(ADR-004 からの直接の割り当ては無い)。
  引き渡しは `TSK-378` の worklog とカードのコメント経由

## 未解決・申し送り

| # | 論点 | 状態 |
| --- | --- | --- |
| **1** | **受け皿タスクが未起票** — 裁定 `C` は「各 FR の実装タスクが持つ」と決めたが、その群は 1 件も存在しない。**`S-10` の機械条件が書けない**危険。**起票するか / 規則だけ置いて起票は各 FR 着手時に委ねるか**の判断が要る | **計画段階の最重要判断** |
| **2** | **係争点 1 行** `FR-041/list_item-014#request-validation` — 理由コードは `TSK-217` 側、`auth-catalog` に entry なし、共有相手は `route_universe_pending`。**裁定 `C` の下では共有相手が FR-041 実装タスクへ行くため、三すくみが解ける可能性がある**(§6 で既定 7 行の根拠が「404/存在秘匿」ではないと判明したため、`TSK-217` へ引く力が弱まった) | **計画段階で判断。解けなければ PO 裁定** |
| **3** | **`verification_contract` 7 行の受取先** — `TSK-217`(対象横断の判定)が有力だが、**`TSK-217` の正本記述が存在しない**ため DoD へ書き込む先が無い | **計画段階で判断** |
| **4** | **入口の不在を主張する行**(Won't 由来の一部)— 「開く PR」が定義上存在しない。**行ごとの確定が要る** | **計画段階で判断** |
| **5** | **`no_db_decision_point` → `TSK-217`** という写像を定めた文書が**見つからない** | **不明** |
| **6** | ~~未マージ依存~~ | **解消**(2026-09-13 — PR #60 でマージ済み。**本タスクは依存していないので結論は不変**。リベース後に全数値の一致を再確認)|
| **7** | **裁定 `C` は正本ではない**(Notion のタスク定義・確定ゲート不要)。**本タスクの成果を正本へ書くかどうか**は別判断 | **計画段階で判断** |

### 調査の限界

- **`TSK-217` の計画書・DoD はリポジトリに存在しない**。射程は他タスクの委譲と Notion 本文からの再構成
- **`TSK-270-GROUP-2` という文字列を誰がいつ書いたかの一次決定記録は不明**
  (`docs/worklog/2026-08-31-pg-authz-verification.md` に `GROUP-2` / `receiving` / `handoff` の語は 0 件)。
  ただし**当初は外部委譲ではなく「TSK-270 の第 2 群が自分で書く」想定だった**ことは確定
  (`claim-mutant-map.json` の論理 ID 接頭辞が `TSK-270.group2.runtime.*` の自己参照。
  `docs/features/pg-authz-verification-g2/plan.md:144` の取り消し線が撤回を記録)
- **`R-7`(`docs/features/pg-authz-verification/plan.md:413`)は「受取タスク」を定義しておらず、選び方の基準も書いていない。**
  **基準そのものは本タスクが新規に決める事項**であり、過去決定による拘束は 3 つだけ —
  **① 分割単位は `runtime_test_owner.id`** / **② 単一タスク一括は不採用(裁定 `C`)** /
  **③ 直叩きテストは入口を開く PR と同一 PR(`data-model.md:2532`)**
