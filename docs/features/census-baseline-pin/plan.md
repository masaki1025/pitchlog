---
feature: census-baseline-pin
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-28・山田正輝 / 計画改訂の再承認 2026-09-28)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e793b75e68781448bf1fac3f8fa1f5a
branch: fix/census-baseline-pin
created: 2026-09-26
計画レビュー周回: 4        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: センサス差分の比較元を資産側へ宣言し、7.7 の手続で置く

## 1. 背景・目的

Notion タスク: <https://app.notion.com/p/3e793b75e68781448bf1fac3f8fa1f5a>(TSK-460)

**`develop` の CI が赤である。** TSK-440(PR #80)のマージ直後から `harness` ジョブだけが
落ちている(run `36227732876` = failure / 直前の `36210079997` = success。**他 9 ジョブは
success**)。

```
tests/test_check_tenant_boundary_bypass.py::test_checker_census_matches_merge_base
E   assert frozenset()
1 failed, 292 passed in 80.19s
```

**原因**: TSK-440 が入れたテストが、比較元に**可変参照 `origin/develop`** を使っている。

```python
merge_base = _resolve_merge_base("origin/develop", "HEAD")   # tests/…:1758
```

440 のブランチ上では `merge_base` が「440 前の develop」だったので差分が出ていた。
**マージ後は比較元と HEAD が同一物になり、差分は必ず空**なので `assert added` が必ず落ちる。

**develop を取り込んだ全ブランチで落ちる。** `harness` は必須チェックなので、
**取り込んだ時点でマージできなくなる**。TSK-448 は実測で **1958 passed / 1 failed・
唯一の failure が本テスト**。TSK-236(#81)・448(#83)は本件だけで塞がっており、
TSK-444(#82)・424(#84)は本件 + 別件(母集合の試験)で塞がっている。

**要件との関係**: 製品要件(FR/NFR)への追加・変更はない。**検査器本体の合否写像は
1 バイトも変えない**ため、テナント分離の防御力は増減しない。

## 2. スコープ

### ★ 方針(計画レビュー 4 周を経た人間の裁定 2026-09-28)

**センサスの比較元を、資産側の機械可読な宣言として新設し、設計書 7.7 の手続で置く。**

**4 周の経緯**:

| 周 | 判定 | 決め手 |
| --- | --- | --- |
| 1 | 否決 P1:3 / P2:2 | 「歴史的事実の再現」と言いながら after を固定していない |
| 2 | 否決 **P0:1** | **固定 SHA のソース直書きが 7.7-1 違反。機構として実装済み**(`check_frozen_baselines.py` の走査) |
| 3 | 否決 **P0:1** | 削除案に対し**第 4 の経路**(受理記録の snapshot)を発見。削除で失う保証も過小評価 |
| 4 | 否決 **P0:1** | **その結線も 7.7-1 の対象**。`acceptance_id` と期待件数は未宣言の基準値 |

**4 周目の P0 を全面的に受け入れる。** 本変更は「既存の宣言を参照するだけ」ではなく、
**census 検査に対して基準を新たに置く行為**である。`"masaki1025/pitchlog#80"` は
「どの内容を比較元にするか」を一意に決めるので**基準の識別値**であり、期待件数は
**合否を決める基準値**である。したがって **7.7-1(宣言の外出し)と 7.7-2(更新の記録)が
掛かる。**

### ★ 実現可能性を実測で確定した(2026-09-28)

**snapshot だけで完結する案は成立しない。** 実測:

```
✗ load_contract 失敗: ContractError: DB API inventory の集合が封印値と不一致
   expected=c67f944e… actual=e2be3e82…
```

**原因**: 封印は `hashlib.sha256(inventory_bytes)` = **生のファイルバイト列**
(`check_tenant_boundary_bypass.py:828`)。asset snapshot は `baseline_control` と
`source_digest` を除いた**射影**なので、**元のバイト列は原理的に復元できない**。

**成立する組合せを実測で確定した:**

```
git から展開: 127 件(旧 7 資産 + 旧 fixture)
旧 helper: /tmp/…/scripts/frozen_history.py   ← snapshot から隔離ロード
★ load_contract 成功  負例 68 / 正例 5
```

#### 比較元は 1 経路にする(自己レビューでの設計簡素化 2026-09-28)

**当初は「checker・helper は受理記録の snapshot から / 資産・fixture は Git から」の
2 経路にしていた。1 経路へ改める。**

実測: **Git 由来の checker・helper の digest は、受理記録の snapshot 側と完全一致する。**

```
checker: 4e4c22633db5765fc8c5bf0ae7e4969dc1d9742c8035e0ced8bbb61940aed878
helper : 0bd319d2118948d288d338bc80dcb3885d0ee5834f7dea6d9d0ef33ecb5d40e8
   ← git(アンカー)と PR #80 の記録の external_snapshots で一致
```

**2 経路は守りを強くしていなかった。** どちらの経路も、壊れたときの帰結は
fail-closed(落ちる)で同じであり、**復旧の余地が増えるわけではない**。
一方で経路が 2 つあると、**混成(旧 checker + 現行 helper)・snapshot_ref の正規形・
entry 欠落**といった**その構成にしか存在しない失敗様式**を増やす。

| 部品 | 出所 | 守り |
| --- | --- | --- |
| **旧 checker・旧 helper・旧 7 資産・旧 fixture(129 件)** | **Git(宣言されたアンカー)の 1 経路** | **宣言が持つツリー digest と突合** |
| **アンカー識別値・ツリー digest・算出規則・相互検査の `acceptance_id`** | **資産側の新設宣言** | ソースに書かない(7.7-1-2) |

**ツリー digest は決定的に算出できる**(実測)。

```
4 パスを含めたファイル数: 129 / digest 214a708144881fede3ec914a9cbcb767cbfae0fe030a5197c6f47bc83b9c895a
再計算で一致: True
```

算出規則(宣言に明記する): **`contracts/tenant_boundary` /
`tests/fixtures/tenant_boundary` / `scripts/check_tenant_boundary_bypass.py` /
`scripts/frozen_history.py` の 4 パスを `git ls-tree -r --name-only` で列挙して昇順に並べ、
各要素について「相対パス + NUL + 内容の sha256(小文字 hex) + LF」を連結した列の sha256。**

**さらに、無料で付く相互検査を行う。** 宣言が持つ `acceptance_id` で PR #80 の受理記録を
引き、**その `external_snapshots` が持つ checker・helper の `sha256` が、
Git から materialize した同名ファイルの digest と一致すること**を確かめる。
**「宣言されたアンカー」と「受理時に記録された内容」が別々の経路で同じ物を指していること**の
確認であり、**片方だけが書き換えられた状態を検出する**。

**内容が 1 バイトでも違えば落ちる**(7.7-3 fail-closed)。

### やること

- **`contracts/tenant_boundary/census-baseline.json` を新設**し、census 基準を機械可読に宣言する
  - アンカーの識別値(`b4ae7394…`)と解決方法
  - 凍結対象との対応(**129 件を宣言アンカーから Git で materialize する 1 経路**)
  - **ツリー digest と算出規則**、および**相互検査に使う `acceptance_id`**
  - 同一性の粒度(`CensusIdentity` の構成)
  - **合否写像**(下記。**件数ではなく述語 5 件**)
  - **追記専用の履歴**に、本 PR の設置を表す 7.7-2 の記録 1 件
    (直前 `NO_BASELINE` / 新しい識別値 / 変更前後 / 動かした事実・理由・**承認者・承認日**)
- **テストは宣言を読む。** `acceptance_id`・commit・期待件数を**テストソースに書かない**
- **比較元の組み立てを実装する** — 宣言されたアンカーから 129 件を materialize し、
  **ツリー digest を突合**し、**旧 checker と旧 helper を `sys.modules` から隔離して**ロードする
- **ソースに書いてよいもの・いけないものを線引きする**(下記)
- **fail-closed を実装する**(7.7-3)
- **テストを改名する**(`…matches_merge_base` は事実と違う)
- `_resolve_merge_base` を削除する(本変更で未使用。参照は 1 箇所のみ — 実測済み)
- **`test_generated_provenance_corpus_never_weakens_develop` の自己比較時の明示 skip**
  を**注入可能な形**で実装する(1 周目 `P2-1` / 3 周目 `P1-1`)
- **worklog の裁定を現行化する**(3 周目 `P1-2`。撤回済みの決定を撤回と明記して残す)

### テストソースに書いてよいもの・いけないもの

**4 周目のレビューが線を引いている**(逐語):

> ソースに残せるのは、**基準値ではない安定した schema key や宣言ロケータ**までです。

| ソースに書く | ソースに書かない(宣言へ置く) |
| --- | --- |
| **宣言ファイルのパス**(`contracts/tenant_boundary/census-baseline.json`)= 宣言ロケータ | アンカー識別値(`b4ae7394…`) |
| **宣言の schema key**(`anchor`・`tree_digest` など) | ツリー digest(`214a7081…`) |
| | 相互検査の `acceptance_id`(`masaki1025/pitchlog#80`) |
| | 合否写像の述語の定義 |

**宣言ロケータをソースに書くこと自体は避けられない** — どこかに「宣言はここにある」と
書かなければ宣言を読めない。**ロケータは基準の値ではなく、基準の在り処である。**

### ★ 合否写像は「件数」ではなく「述語」にする(4 周目 `P1-1` の是正)

4 周目が実測で示した問題:

> 期待値 `added={'TB002': 13}` / `removed={'TB002': 9, 'TB007': 184}` の入力は
> **現行 `backend/src`** である。checker・契約が不変でも、**製品ソースの追加・削除・
> 行移動・symbol 変更で件数や `CensusIdentity` が動く。**
> 現行入力と exact 件数を併用するなら、**今後の `backend/src` 変更はすべて基準更新として
> 再導出・記録する必要がある。**

**件数を基準値にすると、製品コードを触るたびに受理記録を書くことになる。** これは
TSK-448 が 3 回踏んだ「**比較や検証の道具が、検証対象の現況に依存する**」型そのものである。

**したがって合否写像を、`backend/src` の変化に対して安定な述語として宣言する:**

1. `added` と `removed` の**コード集合が `{TB002, TB007}` に収まる**
2. `removed` のうち **TB007 は、宣言済みの緩和と対応する**(要素ごと)
   — 既存 `_assert_removed_tb007_matches_declared_relaxations`
3. `removed` のうち **TB002 で裁定対象でないものは、現行センサスに TB002 として残る**
4. **`added` が、両版の条件 2 の候補抽出から導かれる集合と完全一致する**(下記)
5. `added` と `removed` が**ともに空ではない**

**述語 4 が 5 周目 `P1-1` の是正である。** 指摘は「述語 4 件では **`added` 13 件のうち
12 件を失っても合格する**」— 非空判定しか掛かっていなかった。

**是正**: `added` を**導出される集合と完全一致**させる。

> **`added` == { 現行 `backend/src` の AST から独立に列挙した候補サイトのうち、
> その symbol が現行版の条件 2 の候補抽出に一致し、
> かつアンカー版の候補抽出には一致しないもの }**

**★ 右辺を現行センサスからフィルタしてはいけない**(6 周目 `P1-1`)。
両辺が同じ `_checker_census(candidate)` を出所にすると、
**candidate が 1 サイトを取りこぼしたとき両辺から同時に消えて完全一致のまま合格する**。
**右辺は AST と両版の契約だけから作る。**

**変異も「`added` の後処理で 1 件落とす」では不足**で、
**candidate checker の出力から 1 サイトを欠落させる形**にする。

**両版の契約から機械的に導ける**ので、件数を基準値にしない。

**件数は宣言にもテストにも書かない。** 実測値(`13 / 9 / 184`)は**本 PR 時点の観測**として
worklog・PR 本文・逐行確認シートへ記録するにとどめる。

**「件数を捨てると、許された種別の中で緩和が無制限に増えるのではないか」への回答**:
**増えない。** 述語 2 の実体である `_assert_removed_tb007_matches_declared_relaxations`
(`tests/…:1007-1060`)は、**消えた TB007 を 1 件ずつ** AST で追い、
**宣言された緩和の機構で説明できることを要素ごとに要求している**
(`matching_calls` を突き止め、`lexically_bound_name_ids` などの `explanations` で説明する)。

- **新しい種類の緩和**は説明に失敗して**赤**になる
- **同じ種類の件数が増える**のは、**宣言がすでに許している範囲**である
- 宣言そのものを広げるには**検査器の保証宣言を書き換える**ことになり、
  それはコア paths の変更として敵対レビューと人間の逐行確認を通る

**したがって件数は、この要素ごとの検査にすでに包含されていた代用の縛りである。**
捨てても拘束は落ちない。

### やらないこと

- **テストを削除しない**(3 周目の実測で、失う保証が大きいことが確定した)
- **期待件数を基準値として固定しない**(上記)
- **`scripts/check_tenant_boundary_bypass.py` と `scripts/frozen_history.py` を変更しない**
- **製品の挙動は変えない**(4 節「配布モジュールの同期」を除き `backend/` を触らない)
- **自前の受理検査を作らない**(5 周目 `P0-2` — 下記「既存機構へ合流する」)
- **`scripts/frozen-baseline-scan-allowlist.json` / `contracts/authz/frozen-baselines.json` を変更しない**(**`ci.yml` は変更する** — 9 周目 `P1-2`)
- **ハーネス運用評価台帳への追記を本タスクから行わない**(TSK-448 が引き取り済み)

### 削除しない根拠(3 周目 `P0-1` の実測)

```
baseline=362 current=182 added=13 removed=193
added_codes={'TB002': 13}      removed_codes={'TB002': 9, 'TB007': 184}
```

**同じ比較を行う別装置は存在しない**(`rg -n 'candidate - reference'` で 1 箇所のみ)。
前版比較コーパス 712 ケースは `_source_is_tb007_red` 経由で **TB007 しか見ない**。

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| — | **反映なし。** 製品要件・設計・ADR・運用手順のいずれにも影響しない。新設するのは契約資産であって正本ではない | — |

### 正本体系外だが同一 PR で更新するもの

| ファイル | 変更内容 |
| --- | --- |
| **`contracts/tenant_boundary/census-baseline.json`** | **新設**(census 基準の宣言 + 7.7-2 の履歴 1 件) |
| `tests/test_check_tenant_boundary_bypass.py` | 比較元の差し替え・改名・fail-closed・退行検査・skip |
| `docs/features/census-baseline-pin/plan.md` | 本計画書 |
| `docs/worklog/2026-09-26-census-baseline-pin.md` | 作業ログ(**撤回済みの裁定を撤回と明記して残す**) |
| `docs/features/census-baseline-pin/verification-sheet.md` | **逐行確認シート**(コア領域 — 設計書 6.3) |

## 4. 実装方針

### 重さ分類 = コア領域(テナント分離)

`.claude/core-areas.json` の「テナント分離」の **`paths`** に
`tests/test_check_tenant_boundary_bypass.py` が**完全一致で列挙されている**(機械で判定)。
**sol xhigh・敵対レビュー・人間の逐行確認が必須。**

### このテストが主張すること

> **現行の検査器は、宣言されたアンカー時点の検査器と比べて、
> 現行 `backend/src` 全文に対する違反センサスの差分が、TB002 と TB007 に収まっている。**

**歴史の再現ではない。** candidate は現行の検査器、入力は現行の `backend/src`。
**アンカー側だけが固定される。** 両端を固定すると 2 つの固定物の比較になり、
現行コードを一切拘束しなくなる。

### 比較元の役割による使い分け(TSK-448 との突き合わせで得た整理)

| | 比較元の役割 | 扱い |
| --- | --- | --- |
| **センサス差分**(本テスト) | 「何を動かしたか」の**記録** | **不動のアンカー**。資産側に宣言 |
| **前版比較コーパス** | 「動かす前の自分」を作る**道具** | **可変参照 `origin/develop`**。自己比較の文脈では skip |

### ★ 直前値は `NO_BASELINE` で正しい(7 周目の再裁定)

**5 周目 `P0-1` を撤回する。** 同じレビュアの 3 周目 `P2-1` と矛盾しており、
**原典は 3 周目の側を支持する。**

| 周 | 同じ対象への判定 |
| --- | --- |
| **3 周目 `P2-1`** | 「現行テストの `merge-base(origin/develop, HEAD)` は **PR ごとに動く相対比較元であり、『特定コミット・版・digest が変わらない』という凍結宣言ではない**」 |
| **5 周目 `P0-1`** | 「直前状態を `NO_BASELINE` とするのは実状態と不一致。既に merge-base を比較基準として使っている」 |

**原典の決め手**(設計書 7.7-2 の 2 項・`:590`):

> **直前の基準の識別値** — 当該行為の直前に、**当該検査へ現に置かれていた基準の識別値**。
> **1 つも置かれていなかったときに限り**、置かれていなかったことを表す値を書く。

**旧テストは識別値をどこにも置いていない。** 実行のたびに `origin/develop` から導出して
いただけで、**コミットも版も digest も置かれていなかった**。
7.7 の背景も「凍結を謳う検査は、**基準となるコミット・版・digest を持つ**」と
定義している(`:520`)。7.7-1-2 の禁止も「**基準の値を**検査器のソースへ直書きしない」で、
**置かれた値が存在しない以上、対象になる値がない**。

**したがって census 検査は本変更までに基準を 1 つも持たず、直前値は `NO_BASELINE` が正しい。**
**これは機構が強制する値**(`frozen_history.py:534`)**と一致する。**

**帰結**: 6 周目 `P0-2`(可変基準を中央 v2 で表現できない)と
7 周目 `P0-1`(`previous_baseline` を宣言へ書く案の否決)は、
**いずれも「可変基準を記録せよ」を前提としており、前提ごと消える。**
**`previous_baseline` を宣言へ置く案は撤回する**(7.7-1 の「宣言は現に凍結している基準だけを
表す」にも反していた — `:577`)。

**旧テストが何をしていたかは、`movement_fact` と `reason` に事実として書く。**
**それは基準の記録ではなく、行為の説明である。**

### ★ 既存機構へ合流する(5 周目 `P0-2` の是正)

5 周目の指摘: **新設資産はどの追記専用検査にも入らない。**
`check_frozen_baselines.py --ci` が green でも新資産の履歴は比較されず、
**初回記録を後から書き換え・削除しても誰も捕まえられない**(7.7-2 違反)。

**自前で受理検査を作らない。既存機構へ合流する。**

**経路を 6 周目 `P0-1` で訂正した(スパイクで実測)。**

**履歴検査の資産集合は `FROZEN_BASELINE_ASSETS` から来ていない。**
比較元・HEAD 双方の **`contracts/tenant_boundary/*.json` の独立列挙**から作られる
(`check_tenant_boundary_bypass.py:5758` / `:5786`)。
**ファイルを置いた時点で対象になる。**

**既存機構が要求する形(スパイクで実測済み)**:

| 項目 | 実測 |
| --- | --- |
| 新資産の `history` | **空にする。** 非 authority へ履歴を置くと拒否される(`frozen_history.py:493`) |
| `history_authority` | **`false`**(権限は `base-allowlist.json`) |
| 7.7-2 記録の置き場 | **`base-allowlist.json` の authority history へ v2 を 1 件** |
| 受理 ID | **GitHub event 由来の `owner/repo#N` と完全一致**(`frozen_history.py:672`)。**ブランチ名は不可** |
| 資産本体の内容 | **自由**。種別ごとの schema 要求はない(`anchor` などの独自フィールドが通ることを実測) |
| 遷移の検出 | **`baseline_set` / `baseline_value` / `pass_fail_mapping` の 3 つが立ち、affected は 8 資産**(実測) |

**`FROZEN_BASELINE_ASSETS` への 1 行追加も併せて行う**(`load_contract` の
`_validate_baseline_control` 対象にするため — `:1348`)。
**これにより既存テストの `assert history` が空履歴で落ちる**(`tests/…:3351`)ので、
**そのテストの更新も本タスクの射程に含める**。

**代償(受け入れる)**: 検査器を 1 行変えるので **8 資産すべての射影が動く**。
**識別値の繰り上げと v2 受理記録 1 件**(承認値が要る)が付く。
TSK-440 と TSK-235 で実施済みの手続である。

**合流に要る形(実測)**: `_validate_baseline_control` は `baseline_control` に
**`{identity, movement_policy, history, history_authority}` の exact-set** を要求する
(`check_tenant_boundary_bypass.py:1348` から呼ばれる)。**資産本体の内容は自由**で、
資産種別ごとの schema は要求されない。`history_authority` は **`false`**
(権限は `base-allowlist.json`)。**非権限資産も履歴を 1 件以上持つ**(実測: 既存 6 資産とも 1 件)。

**新資産は比較元に存在しない。** `frozen_history.py` の `asset_name not in base_assets`
経路(`:319`)が要求する形に従う。**この経路の実挙動を実装前に実測する**(ステップ 1 の合格条件)。

**センサスへの影響**: 変えるのは**定数タプル 1 行だけ**で合否写像は動かないので、
`backend/src` に対する違反センサスは変わらない。**述語が保たれることを実測で確認する**
(ステップ 2 の合格条件)。

### 受理の単位と、直前・直後の算出方法(7.7-4 の委任)

**7.7-2 は「受理の単位をどう取るか、直前・直後の状態をどう算出するかは本節では定めない」と
各資産へ委ねている。** 本資産は次のように定める。

| 項目 | 定め |
| --- | --- |
| **受理の単位** | **本ブランチ `fix/census-baseline-pin` が `develop` へ統合される 1 回** |
| **識別子** | **ブランチ名**(PR 番号を使わない — 下記) |
| **直前の状態** | **`NO_BASELINE`**(上記「直前値は `NO_BASELINE` で正しい」— 旧テストは識別値を 1 つも置いていなかった)。**機構が強制する値と一致する** |
| **直後の状態** | 本コミットで置く宣言の識別値(**完全 SHA の固定アンカー**) |
| **行為の種別** | **基準なしからの初回配置ではない。可変基準から固定基準への差し替え**(値・解決方法・置き場・識別値解釈の 4 つが動く) |
| **直前値の導出** | **PR 受理時点の実 base SHA から導出する**。計画時点の `1a404…` を固定しない |

**PR 番号を識別子に使わない理由**: PR 番号は**PR を作るまで確定しない**。使うと、
宣言を置くコミットが PR 作成の後になり、**「宣言はあるが記録がない」か
「記録はあるが宣言がない」中間状態が必ず生まれる**。
**ブランチ名は着手時点で確定している**ので、**宣言と記録を最初のコミットで同時に書ける**。

(既存 7 資産が `acceptance_id: owner/repo#N` を使うのは、それらが**既に存在する資産へ
追記する**ためで、初回設置の本件とは事情が違う。7.7-4 はこの選択を各資産へ委ねている。)

### ★ 宣言と実装の対応は、実装を凍結対象に入れて機構で保証する(6 周目 `P1-2`)

**6 周目の指摘**: `pass_fail_mapping` が観測するのは
`frozen_projection.external_files` の内容だけ(`frozen_history.py:1314`)。
**census の実装(比較元の組み立て・述語・宣言の消費)がそこに入っていなければ、
実装を弱めても movement にならない。**

**したがって census 資産の `external_files` は資産固有にする。**
既存 7 資産は共通の 3 ファイル(checker / helper / ci.yml)だが、
**census 資産はそれに加えて census の実装モジュールを持つ。**

**★ それでも pytest 収集経由では迂回できる**(9 周目 `P1-2`)。
**非凍結側の wrapper で `pytest.skip` するか、`conftest.py` の収集フックで除外すれば、
専用モジュールを無変更のまま実行されなくできる。**

**出口: census を pytest 収集経由ではなく、`ci.yml` から専用コマンドで直接叩く。**
**`ci.yml` は既に全資産の `external_files` に入っている**ので、
**そのステップを消すこと自体が `pass_fail_mapping` movement になり、
識別値の繰り上げと受理記録を要求する。**
**どのみち検査器のタプル変更で 8 資産の射影が動くので、追加の代償はない。**
(**「`.github/workflows/ci.yml` を変更しない」は撤回する。**)

**★ 切り出しの境界は「entrypoint と結線まで」**(8 周目 `P1-1`/`P1-2`)。
**比較元組み立て・述語・宣言消費だけを出しても、呼び出し口が非凍結なら検査を迂回できる**
(`pass_fail_mapping` が観測するのは宣言された `external_files` の内容だけ —
`frozen_history.py:1347`)。**最小の pytest entrypoint と結線まで専用ファイルへ出して凍結する。**
**「entrypoint の迂回・削除でも movement が立つ」負例を置く。**

**★ 実装を専用モジュールへ切り出す。** `tests/test_check_tenant_boundary_bypass.py` を
まるごと凍結対象にすると、**census と無関係な 292 件のテストを 1 行直すたびに
識別値の繰り上げと受理記録が要る**ことになる。
**census の比較元組み立て・述語・宣言消費だけを専用モジュールへ出し、それを凍結する。**

**副作用**: 「全資産が同じ 3 実装を持つ」ことを固定している既存テスト
(`tests/…:2508`)は、**資産別の期待 mapping を検査する形へ変更する**。

**退行テスト**: **census の実装モジュールだけを変更したとき、識別値の繰り上げと
authority record を要求する**ことを固定する。

**実測で確かめた前提**:

- **`external_files` は機構上 資産ごとに持てる**(`frozen_history.py:412-413` が
  `base_components[asset_name].external_files` と資産単位で読む)。
  **同一性を固定しているのはテストだけ**(`tests/…:2508`)
- **資産ファイルの集合と `FROZEN_BASELINE_ASSETS` の一致は別のテストが固定している**
  (`tests/…:2505`)。**ファイルを置いたらタプルへ足すのは必須**
- **切り出す実装モジュールは `tests/` 配下なので `check_frozen_baselines.py` の
  hex 走査対象になる**(`SCAN_SOURCE_ROOTS`)。**40/64 桁の値を 1 つも書けない** —
  アンカーも digest も宣言から読む本方針と整合する

**これが 7.7-4 の「宣言と実装の対応をどう保証するか」への答えである。**
自前の両方向検査(前版の案)より、**既存機構に載せるほうが強い**。

### 参考: 前版で検討した両方向の結線検査(補助として残す)

**digest で実装を固定しない。** テストモジュールは他の理由でも変わるので、
digest を置くと**無関係な変更のたびに基準更新が要る**ことになり、
4 周目 `P1-1` が指摘した「道具が現況へ依存する」型に戻る。

**代わりに、宣言と実装の対応そのものを機械で検査する**(ステップ 5)。

| 向き | 検査 | 捕まえるもの |
| --- | --- | --- |
| **宣言 → 実装** | 宣言が持つフィールドの**全数表**と、実装が読んだキーの集合が**完全一致** | **宣言にあるのに読まれていない値**(宣言が飾りになる) |
| **実装 → 宣言** | 比較元の組み立てに使った値が**すべて宣言由来** | **宣言外の値をこっそり使う**(ステップ 4 の正の結線検査) |

**両方向を揃えないと片側が抜ける** — 前者だけだと宣言外の値を足せるし、
後者だけだと宣言を空にできる。

### 中間コミットの CI は赤でよい(9 周目 `P1-1`)

**ステップ 1〜9 の各時点で CI green にはならない。** 新資産と検査器変更で movement が
立つ一方、**受理記録はステップ 10 まで書けない**(6 周目 `P0-3` — 凍結対象の変更が全部
終わらないと `change.after` が正しくない)。

**したがって各ステップの合格条件に「全件 green」を課さない。**
**課すのは当該ステップの影響範囲のテストだけ**とし、**全件は最終状態で 1 回確かめる**。
(全件実行は 1 回あたり約 11 分かかるため、ステップごとに 2 回回すと実装が待ちで埋まる。)

### ★ 配布モジュールの同期(計画改訂 2026-09-28 — 実装レビュー `P1-4`)

**当初の計画は「製品コードを触らない」と書いていたが、識別値を繰り上げる以上
これは成立しない。** 計画を改訂して射程へ入れる。

**「製品挙動を変えない」は、計画外の製品コード変更を事後承認済みにする根拠にならない**
(実装レビューの指摘。そのとおりである)。**したがって事後の文言修正では済ませず、
対象・理由・ステップ・テストを明記して承認を得る。**

#### 対象 3 ファイル

| ファイル | 定数 | 値 |
| --- | --- | --- |
| `backend/src/pitchlog/repositories/tenant_context_contract.py` | `CONTRACT_REVISION` / `SOURCE_DIGEST` | 7 → 8 |
| `backend/src/pitchlog/repositories/repository_contract.py` | `CONTRACT_REVISION` / `SOURCE_DIGEST` | 5 → 6 |
| `backend/src/pitchlog/authz/runtime_contract.py` | `RUNTIME_CONTRACT_REVISION` / `SOURCE_DIGEST` | 4 → 5 |

#### 必要な理由

**これらは契約資産の内容を製品側へ配る写しであり、資産と完全一致を要求される。**
ステップ 10 で 8 資産の識別値を繰り上げるため、**同期しなければ backend のテストが
落ちる**(実測: `3 failed` — `test_generated_allowlist_matches_asset` ほか)。

**製品の挙動は変えない。** 変わるのは資産との同一性を表す定数と digest だけである。

#### 実装ステップ

**ステップ 10 の直後**に行う(識別値が確定してからでないと値が決まらない)。
**ステップ記法は付けない**(ステップ表の実装ステップではなく、ステップ 10 の帰結)。

#### 必要なテスト

**新規テストは足さない。** 既存の 3 件が同期を検査している。

    backend/tests/test_authz_tenant_context.py::test_generated_allowlist_matches_asset
    backend/tests/test_authz_repository_contract.py::test_generated_repository_contract_matches_asset
    backend/tests/test_authz_runtime_contract.py::test_generated_runtime_contract_matches_active_asset

**この層はリポジトリルートの pytest では collect されない**(`backend/` で回す必要がある)。
**PR 前に `cd backend && uv run pytest -m "not requires_db"` を必ず回す。**

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **census の実装(比較元組み立て・述語・宣言消費・最小の pytest entrypoint と結線)を専用モジュールへ切り出す。** この時点では既存テストから呼ぶだけで、宣言はまだ無い | `[機械]` `uv run pytest tests/` 全件 green(挙動を変えていない)/ `ruff check` / `ty check` green / **切り出したモジュールに 40/64 桁の値が 1 つも無い**(`check_frozen_baselines.py --ci` green) |
| 2 | **`contracts/tenant_boundary/census-baseline.json` を新設する**(`history: []` / `history_authority: false` / 宣言 = アンカー識別値・ツリー digest・算出規則・**資産固有の `external_files`(checker / helper / ci.yml / **ステップ 1 で切り出した census 実装モジュール**)**・同一性の粒度・合否写像 5 件・フィールド全数表)。**`FROZEN_BASELINE_ASSETS` へ 1 行追加**し、**`assert history` が空履歴で落ちる既存テスト**と**「全資産が同じ 3 実装」を固定している既存テスト(`tests/…:2508`)**を更新する。**受理記録はここで書かない**(6 周目 `P0-3`) | `[機械]` 宣言が `_validate_baseline_control` を通る / **宣言した `external_files` がすべて実在する**(8 周目 `P1-3` — 履歴検査は HEAD の `external_files` をその場で読み fail-closed する `:5847`)/ **`asset_name not in base_assets` 経路で `baseline_set` が立つ**ことを実測 / 既存テストが green |
| 3 | **比較元の組み立てを実装する。** 宣言されたアンカーから **129 件**を materialize し、**宣言のツリー digest と突合**する。**相互検査**(宣言の `acceptance_id` で引いた受理記録の checker・helper の `sha256` と一致)を行う。**旧 checker と旧 helper を `sys.modules` から隔離して**ロードする。テストを **`test_checker_census_matches_declared_anchor`** へ改名し、`_resolve_merge_base` を削除する | `[機械]` **本ブランチで当該テストが green**(着手時点は 1 failed)/ **`uv run pytest tests/` 全件 green** / **`_resolve_merge_base` への参照が 0 件** / **旧 helper が一時ディレクトリ配下から読まれていることを実測**(`frozen_history.__file__`)/ **現行の `scripts/` を読んでいないことを実測** / `ruff check` / `ty check` green |
| 4 | **合否写像を述語で実装する**(件数を書かない)。述語 5 件 = ① コード集合が `{TB002,TB007}` に収まる ② removed TB007 が宣言済み緩和と要素ごとに対応 ③ 非裁定 TB002 が現行センサスに残る ④ **`added` が AST 由来の導出集合と完全一致**(現行センサスからフィルタしない — 6 周目 `P1-1`)⑤ 両方とも非空。**宣言から読んで**適用する | `[機械]` 5 述語が green / **テストソースにも宣言にも件数が現れない** / **述語を 1 つずつ壊すと赤**(5 種)/ **candidate checker の出力から 1 サイトを欠落させると ④ が赤**(6 周目 `P1-1` の再現。`added` の後処理で落とす形では不足) |
| 5 | **fail-closed と退行の固定。** ① 宣言が読めない ② 宣言の必須フィールド欠落 ③ **アンカーが解決できない**(履歴書き換え・commit 消失)④ **ツリー digest 不一致** ⑤ materialize したファイル数が宣言と不一致 ⑥ **相互検査の記録が引けない / 一意でない** ⑦ **相互検査の digest 不一致** ⑧ **module-cache 混入**(現行 `scripts/` を読む)— **いずれも落とす**(skip・中立にしない) | `[機械]` **8 条件を 1 つずつ壊して赤になることを実測**(戻すと green に復帰)/ **退行の負例 4 種**(`origin/develop` 由来へ戻す / merge-base へ戻す / 作業ツリーの checker を読む / **collection 時に git 由来 bytes をキャッシュする**〔4 周目 `P1-4`〕)がいずれも fail |
| 6 | **実装の凍結が効いていることを固定する**(8 周目 `P1-1`/`P1-2`)。**entrypoint を迂回・削除しても movement が立つ**負例を置く。補助として**両方向の結線検査**(宣言 → 実装の全数消費 / 実装 → 宣言の宣言外不使用)も置く | `[機械]` **census 実装モジュールだけを変更すると `pass_fail_mapping` movement が立ち、識別値繰り上げと authority record を要求する**ことを実測 / **entrypoint の迂回・削除でも movement が立つ**ことを実測 / 両方向の結線検査が green |
| 7 | **前版比較テストの自己比較時の明示 skip を注入可能な形で実装する**(3 周目 `P1-1`)。SHA 解決を差し替え可能にし、**base == head なら理由つき skip、base != head なら 712 ケースを実行**。**両分岐を自動テストで固定する** | `[機械]` **base == head を注入 → skipped**(passed ではない)/ **base != head を注入 → 実行して green** / skip の理由文字列が出力に現れる |
| 8 | **記録成果物の更新**(3 周目 `P1-2`)。worklog の決定節を現行化し、**撤回済みの決定を撤回と明記して残す**(消さない) | `[機械]` `docs-lint` green `[手動]` 撤回した決定とその理由が読んで追える |
| 9 | **逐行確認シートの生成**(設計書 6.3)。**A: 基準を新設する判断と 7.7 の手続 / B: 比較元の組み立て(単一経路 + ツリー digest + 相互検査)/ C: 合否写像を述語にした判断 / D: fail-closed 8 条件の実測**の 4 節で是非が決まる構成 | `[手動]` 全判定項目にアンカー(ファイル:行)と実測値 `[機械]` 実測値が再実行で再現する |
| 10 | **7.7-2 の受理記録を authority へ 1 件書く**(**最終ステップ** — 凍結対象の変更が全部終わってから。6 周目 `P0-3`)。**承認値が要る**。`acceptance_id` は **GitHub event 由来の `owner/repo#N`**。8 資産の識別値繰り上げと `change.before`/`after` の snapshot をここで確定する | `[機械]` `check_repository` が受理する / **予約 marker を含まない** / **孤児 snapshot 0 件** / **書き直していない**(1 コミット) |

## 5. DoD(受け入れ基準)

### 是正の中身

- [ ] **census 基準が `contracts/tenant_boundary/census-baseline.json` に機械可読で宣言されている**
- [ ] **テストソースに、アンカー commit・`acceptance_id`・期待件数のいずれも書かれていない**
- [ ] **合否写像が述語で宣言され、件数が基準値になっていない**
- [ ] **`develop` を取り込んだ状態でも通る** — 着手時点の本ブランチがその状態だった
- [ ] **比較元 129 件が宣言アンカー由来**で、**宣言のツリー digest と一致**することが実測で確認されている
- [ ] **相互検査**(受理記録の checker・helper の `sha256` との一致)が通っている
- [ ] **現行の `scripts/` を読んでいない**ことが実測で確認されている
- [ ] **fail-closed 8 条件**で落ちることを 1 つずつ実測している
- [ ] **退行の負例 4 種**(git 由来 3 種 + collection 時キャッシュ)が fail する
- [ ] **テストソースに、アンカー・ツリー digest・`acceptance_id`・期待件数のいずれも書かれていない**(宣言ロケータと schema key のみ)
- [ ] **前版比較テストが自己比較で skipped・非自己比較で実行**されることを両分岐とも注入で固定
- [ ] **7.7-2 の受理記録の直前値が正しい** — **census 資産は `NO_BASELINE`**(8 周目の裁定。機構が強制する値と一致)/ **既存 7 資産は比較元の各現行識別値**
- [ ] **新資産が `FROZEN_BASELINE_ASSETS` に入り、既存の追記専用機構の対象になっている**
- [ ] **`added` が AST 由来の導出集合と完全一致する**(**candidate checker の出力から 1 サイト欠落させると赤** — `added` の後処理で落とす形では不足。6 周目 `P1-1`)
- [ ] **7.7-2 の受理記録が最終ステップで 1 件書かれ、書き直していない**(宣言はステップ 2・記録はステップ 10。**同一コミットは要求しない** — 6 周目 `P0-3` により記録は凍結対象の変更が全部終わってからでないと `change.after` が正しくならない)
- [ ] **Git 由来のツリーが、宣言されたツリー digest と一致する**(不一致なら落ちる)
- [ ] **宣言と実装の対応が両方向で検査されている**(全数消費 / 宣言外不使用)
- [ ] **「宣言のない基準」も「基準のない宣言」も、どのコミット時点でも存在しない**
- [ ] テスト名が事実と一致している

### 触っていないことの確認

- [ ] `scripts/frozen_history.py` / `contracts/authz/frozen-baselines.json` / `scripts/frozen-baseline-scan-allowlist.json` を **1 バイトも変えていない**
- [ ] **`backend/` の変更が配布モジュール 3 件の識別値・digest 同期だけ**である(製品の挙動を変えていない)
- [ ] **`backend/` の変更が配布モジュール 3 件の識別値・digest 同期だけ**である(製品の挙動を変えていない)
- [ ] **`ci.yml` の変更が census 専用コマンドの追加だけ**である(9 周目 `P1-2`)
- [ ] `scripts/check_tenant_boundary_bypass.py` の変更が **`FROZEN_BASELINE_ASSETS` への 1 行追加だけ**である(合否写像を動かしていない)
- [ ] **8 資産すべての識別値が繰り上がり、v2 受理記録 1 件が書かれている**

### ゲート(CI 10 ジョブ)

- [ ] **最終 PR head で必須ジョブがすべて green**
- [ ] **`backend` と `frontend` は skip されず実行され、green である** — **`contracts/**` がパスフィルタに含まれるため**(実測。4 版までの「skipped 期待」は誤りだった)
- [ ] `harness` の全コマンドが green — `uv sync --locked --dev` / **`check_frozen_baselines.py --ci`** / `ruff check .` / `ty check` / `pytest -c pyproject.toml tests/`
- [ ] **`tenant-boundary-bypass`** / **`docs-lint`** / **`nfr021-append-only`** / **`secrets`** が green
- [ ] **`core-guard`** が green — PR 本文のチェック文言を `scripts/core_guard.py` の `REQUIRED_CHECK_TEXT` と完全一致で書き、人間が `- [x]` を入れ、実施記録行を埋めている
- [ ] **敵対レビュー + 人間の逐行確認**(コア領域 — 設計書 6.3)

### 記録

- [ ] worklog の決定が現行化され、**撤回した決定が撤回と明記されて残っている**
- [ ] PR 本文に**4 周の経緯・実現可能性の実測・失わなかったもの**が書かれている
- [ ] 逐行確認シートが生成されている

## 6. テスト計画

NFR-019 の種別では **単体(ハーネスの自己検査)**。**製品の挙動を変えないため**、越境・E2E・
故障系・一致性の追加はない。**ただし配布モジュール 3 件の同期は行う**(下記)。

| 種別 | 足すもの | 置き場所 |
| --- | --- | --- |
| **単体(自己検査)** | **比較元の出所の検査** — 129 件が宣言アンカー由来 / ツリー digest 一致 / 相互検査一致 / 現行 `scripts/` を読んでいない | `tests/test_check_tenant_boundary_bypass.py` |
| **単体(自己検査)** | **fail-closed 8 条件** | 同上 |
| **単体(自己検査)** | **合否写像の述語 5 件**と、その 1 つずつの変異 / **candidate checker の出力から 1 サイト欠落させると `added` が赤** | 同上 |
| **単体(自己検査)** | **自己比較の明示 skip**(両分岐を注入で固定) | 同上 |
| **負例(変異による確認)** | **退行 4 種**(`origin/develop` 由来 / merge-base / 作業ツリー / collection 時キャッシュ)。恒久テストではなく実施記録 | worklog・PR 本文・逐行確認シート |

**既存テストで守りにするもの**: `_assert_removed_tb007_matches_declared_relaxations`
(**本方針では失わない**)/ 前版比較コーパス 712 ケースの判定ロジック /
`tests/test_check_tenant_boundary_bypass.py` の残り 291 件。

## 7. 申し送り

**中央の凍結基準台帳(`contracts/authz/frozen-baselines.json`)へ寄せる案は採らない。**
スキーマの `declarations` / `placements` が `additionalProperties: false` で `oracle_input`
のみ、`frozen_targets` は `const`(実測: `$.placements: 未知キー: ['census_anchor']`)。
台帳の一般化は本タスクの射程を超える。

**TSK-236 も同じ壁に当たり、中央台帳ではなく descriptor
(`contracts/state-transition/input_axes_descriptor_v1.json` の `freezeBaseline`)へ
独立した系列を置いた**(2026-09-26 の連絡)。**本タスクの新設資産も同じ形**であり、
台帳を一般化する側が後から両方を寄せられる。

**台帳を一般化する側への不足事項**(3 周目が洗い出したもの): `series` 名 / `identity` /
`granularity` / `frozen_targets` の選定 / snapshot から census を導く比較戦略の登録 /
初回配置の locator と `LEGACY_PLACEMENTS` の扱い / `implementation_bindings` の自己変更の記録。
