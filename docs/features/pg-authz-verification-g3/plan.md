---
feature: pg-authz-verification-g3
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-16・山田正輝・射程改訂を再承認) # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2
branch: feature/pg-authz-verification-g3
created: 2026-09-09
計画レビュー周回: 46        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: TSK-317 改訂 4 — 受取先の実 ID 化と封印

> **【2026-09-14 PO 裁定 `D-26`】本書を改訂 4 の契約だけに切り出した。**
>
> **理由**: **計画レビューの `P0` が 3 周連続で 4 件から減らず、3 周目の 6 件中 4 件が「追随漏れ」**
> (本文を直したのに DoD・検証節・`design.md` が置き去りになる型)**だった**。
> **原因は構造**で、**改訂前の本書は 1,268 行あり、同じ事実が 3 箇所ずつ書かれ、
> 完了済みの第 1 弾・第 2 弾への言及が 58 箇所**あった。**1 箇所直すたびに残りが置き去りになる。**
> **台帳の既存候補「1 つの集合の定義が複数の節に分かれているとき、片方だけを直す」そのもの。**
>
> **切り出した内容の所在**: 第 1 弾(ステップ 1〜20)= [PR #52](https://github.com/masaki1025/pitchlog/pull/52) /
> 第 2 弾(封印系)= [PR #59](https://github.com/masaki1025/pitchlog/pull/59) /
> **`S-1`〜`S-10` の全文・訂正 1〜19・裁定 `D-1`〜`D-21` = git 履歴**(本書の `72e7261` 以前)**と
> 各 worklog**。**改訂 4 が必要とする事実だけを本書へ引き写した。**

---

## 1. 背景・目的

**Notion**: [TSK-317 — PostgreSQL 認可構成の実機検証 第 2 群・第 3 群](https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2)(**進行中**)
**調査**: [research.md](research.md) / **詳細設計**: [design.md](design.md)

### いま塞いでいるもの

**`contracts/authz/claim-mutant-map.json` にプレースホルダ `receiving_task_id: "TSK-270-GROUP-2"` が
178 件残っている**(実測)。**この置換が済むまで、認可主張の runtime テストを誰も所有できない。**

**受取先の規則は TSK-367(完了)が確定済み**で、**本改訂はそれを消費して書き写す側**である。
**規則の正は `docs/features/contract-only-runtime-handoff/plan.md` の 2 節**(develop にマージ済み)。

### 関連する要件・正本

- [NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-019)(b)の認可行列 — **本改訂は実テストを書かない**
- [`docs/design/data-model.md`](../../design/data-model.md) 3-2 / 3-6 節(越境関数と `search_path` の契約)
- **`R-7`**: `contract_only` は **schema-drift kill + 受取タスクの runtime テスト ID** と定める
  → **TSK-317 は実テストを書かない**(書くと「契約 lint を実副作用 kill として数える抜け道」になる)

### PO 裁定(2026-09-14 — 改訂 4)

| # | 論点 | 裁定 |
| --- | --- | --- |
| **D-22** | **改訂 4 の射程** | **`S-9` + `S-10` へ絞る。** **裁定 `D-14` が PR #3 へ割り当てた 7 項目のうち 5 項目を送る**(2 節)。**理由**: **3 項目が「いま閉じられない」**(`S-2` は射程に穴・`S-3` は 7 単位が 1:1 に写せない・`S-6` は受取側 DoD が無く機械部分が実行不能)。**加えて `S-2` を含めると入力資産を触るので 2 段コミットが復活する** |
| **D-23** | **`reason_code` の owner 単位の畳み込み** | **畳まない。** **行の属性として扱い、owner 単位の不変条件は `receiving_task_id` にだけ課す**。**理由**: `FR-041/list_item-014` の 2 行が割れるのは**資産の実態**で、TSK-367 の `plan.md:87`「行ごとの判定が割れたら即エラー」を `reason_code` へ拡張する根拠が見つからなかった。**`S-9` ① とは両立する**(受取先は owner 単位・理由コードは行単位) |
| **D-24** | **文書内部整合の検査器** | **改訂 4 では作らない。別タスクへ送る**(2 節)。**理由**: **既存 0 件で新規実装が要り**、パーサの罠が 4 つ、**`guard_paths` 登録が 3 箇所へ波及**する。**「完全性の証明を本体と同じ射程に置くと輪になる」型**(台帳) |
| **D-25** | **`U-T1`(TSK-363)の依存の欠落** | **別タスクとして起票した**(2 節)。`data-model.md` が `U-T1` の構成要素 4 つ(`:238` / `:244` / `:246` / `:2845`)を TSK-317 へ送っているのに、**TSK-363 の `U-T1` の依存列は `U-00` のみ**だった |
| **D-29** | **backend の凍結基準を進める**(2026-09-17・山田正輝) | **`D-28` の「#63 のマージを待って台帳へ 1 件足す」を撤回し、`backend/tests/db/authz/mutation_composition.py` の 2 行を直す。** **撤回の理由**: **PR #63 は close されることになった**(TSK-386 が分割され、**条文タスク `feature/frozen-baseline-clause`** と **実装 `TSK-421`(着手可・未着手)** になった)。**`D-28` が前提にした台帳 `contracts/authz/frozen-baselines.json` は `TSK-421` が実装するまで存在しない。** **`D-28` で却下した 2 つの理由も消えた** — #63 が close されるので衝突しない / **基準を進める形なら 178 件の置換規則を backend へ二重実装しない**。**変更は 2 行**: `STEP2_BASE_REVISION` を `099a8fa`(封印 7 資産が最終状態・HEAD の祖先)へ進め、`STEP2_CHANGED_CANONICAL_ASSET_PATHS` を空にする(**承認済み差分が新基準へ畳み込まれるため**)。**`AUTHZ_STEP2_BASE_REVISION`(`check_authz_catalog.py` 自身の基準版を読む)と `AUTHZ_GUARD_BASE_REVISION`(`core-areas.json` の別対象)は触らない** — **値は同じだが対象が違う**(`TSK-421` のカードが「統合すると core-guard の基準まで暗黙にリベースされる」と警告)。**代償**: `boundary-proposal` と `ddl-elements` が元基準から変わっていた理由がコード上から消える。**`TSK-421` が台帳へ移すときに `reason` として正式な記録に置き換わる。** **マージ順の制約**: **本 PR → `TSK-421`**(逆だと台帳へ古い基準が固定され、178 件の置換が再び red になる) |
| **D-28** | **backend 側の第 2 の凍結への対応**(2026-09-16・山田正輝) | **射程へ `contracts/authz/frozen-baselines.json` の 1 本だけを足す。コードは触らない。** **経緯**: `backend/tests/db/authz/mutation_composition.py` が `STEP2_BASE_REVISION` を基準に封印 6 資産の**意味本文**を固定しており、承認済みの意味変更を 2 資産分しか列挙していないため、178 件の置換で CI の backend ジョブが red になった(**実 red・本 PR 起因**)。**私の段 1 は `contracts/` しか見ておらず、`backend/` 側の第 2 の凍結を確かめていなかった。** **PR #63(TSK-386)がこの構造を `contracts/authz/frozen-baselines.json` へ移設中**で、同台帳は `supersedes` 付きの系列として**基準の前進を人間承認つきの正式操作**に設計している(`oracle_input` で実施済み 2 件。2 件目は**当の PR 自身のコミットを指す**)。**したがって #63 を先にマージし、その拡張点へ `oracle_meaning` 基準を 1 件足す。** **マージ順を ③↔④ で入れ替える。** 却下した案: 現行定数の拡張(#63 が当該 3 定数を削除するので確実に衝突し、178 件の置換規則を backend へ二重実装することになる) |
| **D-27** | **承認後の射程改訂の再承認**(2026-09-16・山田正輝) | **許可パスを 3 資産・閉包を 4 段へ広げる改訂を再承認した。** **経緯**: **実装中に `mcdc-map.json` が `claim-mutant-map.json` の blob digest を固定していること**(`check_mcdc_map.py:294-301`)**が判明し、許可パス 2 本では完了不能だった**(実測で再現)。**私(Claude)は計画改訂と実装を同じコミットへ入れ、再承認を取らずに進めた** — **実装後の敵対レビューが `P0`「承認済み計画に従っていない」として検出した**(AGENTS.md 絶対規則 5)。**正しい手順は「実装を止めて計画改訂の承認を求める」であり、射程を広げる判断は PO のものだった。** **封印は緩んでいない**(`mcdc-map.json` は seal の外 — 入力 8 資産にも封印 6 資産にも含まれない) |
| **D-26** | **本書の切り出し** | **改訂 4 の契約だけにする**(冒頭)。**理由**: `P0` が 3 周連続 4 件で、**うち 4/6 が追随漏れ**だった |

---

## 2. スコープ

### やること

**「受取先の実 ID 化と、それを守る検査」に閉じる。**

1. **受取先の検査を新設する**(`S-10` (2)(3)(6))— **4 層**(文法 / 参照整合 / owner 単位の一致 / 差分閉包)
2. **178 件を置換する**(`S-9`)
3. **`--reseal-oracle` で再封印する**

**1〜3 は不可分で 1 コミット**(4 節)。

### やらないこと

- **`contracts/authz/auth-catalog.json` を変更しない**(= `S-2` を含めない)。
  **触ると入力資産が動き 2 段コミットが復活する**
- **新しい `contract_only_reason_code` を導入しない**(4 節に根拠)
- **実テストを書かない**(`R-7`)
- **`--reseal` / `--reseal-derived` / `--skip-*` を使わない**

### 送るもの(**受取先を実 ID で書く** — 空手形にしない)

| 項目 | 受取先 | 受取範囲 | 送る理由 |
| --- | --- | --- | --- |
| **`S-2`**(論理 ID → node ID) | **[論理 ID → pytest node ID の解決方式を決める](https://app.notion.com/p/3db93b75e6878113bed3cb8a5b33669d)** | 母集団を「TSK-270 所有の planned 論理 ID の全部」へ広げて確定 + 解決方式 + `status` を上げる条件 | **射程に穴**。`requirement-claims.json` に **TSK-270 所有が別に 193 参照**ある(`test_owner` 402 のうち 187 は auth-catalog と同一・残り 215 の接尾辞は `.http` 195 / `.cache` 20)。**`187 + 310` は全部ではなく、射程外とする根拠が無い** |
| **`S-3`**(要件側 7 単位の source) | **[要件側 7 単位の source を決める](https://app.notion.com/p/3db93b75e68781fc821fe62a4efd5af2)** | `FR-041/list_item-016` の裁定 + `stable_id` の源の確定 + `operation-count-mapping.json` | **7 単位の列挙がどこにも存在しない**。**`FR-041/list_item-016` が 2 操作を 1 行に含み `atomic_claims` の分割も無い**ので**安定 ID へ 1:1 に写せない** |
| **`S-4`** + **`S-8` の一部** | **[引き渡しマニフェストを新設する](https://app.notion.com/p/3db93b75e6878111b8a7e7111f3e510e)** | `handoff-manifest.json` の新設 + `tests/test_ci_wiring.py` への配線の固定 | **丸ごと新設**。**ID 集合の digest を持つフィールドは全資産に 0 件**・**元 commit は 2/3**・**blob digest は 1/3 しか記録が無く種類も割れている** |
| **文書内部整合の検査器**(`D-24`) | **[文書の内部整合を検査する](https://app.notion.com/p/3db93b75e68781d694b2cf53a8b3d119)** | 件数ラベル vs 中身 + 名乗る母数 vs 実数の 3 段突合 | 上記 |
| **`U-T1` の依存の欠落**(`D-25`) | **[U-T1 の入力を確定する](https://app.notion.com/p/3db93b75e687813a9386f3b1f1e682ed)** | 実装入力の名指し + probe → 製品の写像 + TSK-363 側への追記 | **TSK-363 はマージ済み**。**追記であって単位の切り直しではない** |
| **`PENDING:FR-nnn` 139 owner の置換義務の検査** | **[TSK-383](https://app.notion.com/p/3d993b75e68781ad8663dce3ac2484a2)**(「経路を開く」の機械判定)+ **[TSK-363 の 23 カード](https://app.notion.com/p/3d893b75e68781de948bfe5ef4679652)の DoD** | **owner → 入口の割当表**(**TSK-367 の正本 `:254` `:313` が要求しているが資産が未作成**)+ 入口検出 + 過少/過剰の判定 | **「入口を開いたか」の機械判定が未整備**で、**それ無しに作ると fail-open な検査を封印資産の守りとして固定してしまう** |
| **`S-10` (8)(9) の充足**(13 owner の `read-back` と退化の負例) | **受取側の着手待ち** — **[TSK-217](https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2)**(射程の正は Notion カード)/ **[TSK-410](https://app.notion.com/p/3da93b75e68781fb978fedba7ef499e0)** / **[TSK-411](https://app.notion.com/p/3da93b75e687818da3aac516470d8c40)** | **受けた owner 集合を資産と exact-set 突合する** + **退化の負例** | **受取側からの `read-back` は、受取側が行わなければ `read-back` にならない**。**TSK-317 が DoD へ書いて読み返すのは循環**(8 周目 `P0`)。**本改訂は条文を渡すところまで** |
| **`S-6`**(受取契約・`read-back`・製品 adapter) | **受取側の着手待ち** — **[TSK-250](https://app.notion.com/p/3c593b75e6878152b3edd6cf4f26b30b)** / **TSK-217** | **両者が DoD を持ってから** | **`[機械]` 部分が実行不能**(**両タスクとも未着手で DoD が無く突合先が空**)。**「製品 adapter」の定義がどこにも無い**。**`TSK-250` は `data-model.md` ではない**ので v0.3 approved は前提を崩さない |

> **`S-6` だけ新規起票していない。** **受取側が DoD を持つまで送っても受け取れず、
> それ自体が「送り先が空手形になる」型になる**ため。**待っている対象を上表に明記した。**

---

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| [`docs/README.md`](../../README.md) | **台帳行の最終更新日を現行化**(台帳へ候補 2 件を追記したため — `pr/SKILL.md` 手順 1-3 ④) | PR レビュー |
| [`docs/development/harness-evaluation.md`](../../development/harness-evaluation.md) | **`## 候補` へ 1 件を新設し、既存候補 1 件へ事例を追加する**(`H-*` は採番しない・版は上げない — 7.6-3 前段)。**新設**: 機械検査(CI)の射程と、作業する主体が実際に持つ経路を取り違えると、機械で閉じられる確認を人手へ回す。**追加**: 「正本の行番号引用は書き手自身の手で古くなる」へ、**他 PR のマージでファイルが伸びてずれる**事例 | PR レビュー |
| `.claude/core-areas.json` | **反映なし** — **本改訂が触る検査器とテストは `guard_paths` に登録済み**(PR #59)。新規パスを足さない | — |
| `docs/design/**` / `docs/requirements/**` / `docs/adr/**` / `docs/development/**` / `docs/ops/**` | **反映なし** | — |
| `contracts/**` を除く `backend/**` / `frontend/**` | **反映なし** | — |

> **本節の散文で正本のパスをバッククォートや相対リンクで名指さないこと。**
> **`check_plan_docs_sync.py` の `markdown_link_paths` + `backtick_paths` が拾い、
> `反映なし` を含まない行はすべて反映宣言として読まれる**(2 周目 `P1-7` — **注記自身が違反を作った**)。

### 正本体系外で本改訂が変更するもの(/pr 突合の別枠宣言)

| ファイル | 変更内容 |
| --- | --- |
| **`contracts/authz/claim-mutant-map.json`** | **178 件の `receiving_task_id` を実 ID / `PENDING:` へ置換**。**`sealed_assets` 側なので `canonical_sha256` が変わる** |
| **`contracts/authz/mcdc-map.json`** | **`sources.claim_mutant_map.blob_digest` の追随のみ**(**2026-09-16 実装時に判明** — `check_mcdc_map.py:294-301` が blob を固定しており、追随しないと完了不能。**seal の外なので封印は緩まない**) |
| **`contracts/authz/oracle-seal.lock.json`** | **`--reseal-oracle` による再封印**。**`sealed_assets` の `claim-mutant-map` の行が変わる**。**`oracle_commit` は本改訂では動かさないが、develop(PR #64 / TSK-355)の取り込みで `0cf994f4…` → `24ef4fcc…` へ前進した値に追随している** |
| **`scripts/check_authz_catalog.py`** | **受取先の検査 4 層を新設** |
| **`tests/test_check_authz_catalog.py`** | **上記の正例・負例** |
| **`backend/tests/db/authz/mutation_composition.py`** | **凍結基準を `099a8fa` へ進め、承認済み差分の集合を空にする 2 行**(裁定 `D-29`)。**全 5 コア領域の `paths` に該当する** |
| `docs/features/pg-authz-verification-g3/**` / `docs/worklog/2026-09-14-pg-authz-verification-g3.md` | 本書・`design.md`・`research.md`・作業ログ |

**上記以外の `contracts/authz/**` は 1 バイトも変えない**(4 節の差分閉包 段 1)。

---

## 4. 実装方針

### 重さ分類 = **コア領域**(テナント分離)

`contracts/authz/*` は `.claude/core-areas.json` の `tenant-isolation.paths` に含まれる(実測)。
→ **`sol xhigh`・敵対レビュー必須・人間の逐行確認必須**(設計書 6.3)。

### 封印は単一コミットで閉じる(**実測**)

**`claim-mutant-map.json` は `sealed_assets`(`asset_role: expectation`)側**であり、
**入力 8 資産**(`check_authz_catalog.py` の `required_input_paths` — `:5215-5223`)**に含まれない。**

**したがって本改訂は入力資産に触れず、`oracle_commit` を動かす必要が無い。**
**`--reseal-oracle` のみ・単一コミットで閉じる。** **これは `S-9` ④ の逐語と一致する。**

**`S-2` を同じ改訂に入れると 2 段コミットが復活する** — **実機で再現した**:
`auth-catalog.json` を 1 文字変えると ① フラグ無しは `decision lock と不一致`
② `--reseal-derived` は lock を書くが同じ実行の oracle 段で落ちる ③ **`--reseal-oracle` は 1 バイトも書かない**
(`_build_oracle_seal` が `oracle_commit` を触らないため、入力 blob の commit 照合が必ず落ちる)。
**「これから作るコミット」を基準点に指定できないことが 2 段コミットの機構的な理由**であり、
**`oracle_commit_semantics: "last_committed_step_4_input_baseline"` がその意味を持っている。**

**reseal 系のフラグは 3 つで相互排他**(`--reseal` `:5417` / `--reseal-derived` `:5422` /
`--reseal-oracle` `:5427`・排他判定は `:5607-5613`)。**`--skip-derived`(`:5432`)と `--skip-oracle`(`:5437`)も実在するが**
(**`argparse.SUPPRESS` でヘルプに出ない** — 2026-09-14 に是正)**検査のスキップであって封印は閉じない**。
**本改訂は `--skip-*` を使わない。**

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

> **見出しに「実装ステップ」を含めるのは機構要件**(`codex_run.py` が見出しスタックで判定する)。
>
> **表に載せるのは「承認後に残る作業」だけである**(2 周目 `P0-2`)。
> **`S-10` の 9 論点の処置・射程宣言・送り先表は本計画改訂そのものであり、承認時点で完了している。**
>
> **「検査の新設」と「178 件の置換」を別ステップにしない**(初周 `P0-3`)—
> **`feature_status.py:919` は 1 件名に 2 つのステップトークンがあると `inconsistent` を返す。**
> **資産に `TSK-270-GROUP-2` が 178 件ある以上、検査だけ先に入れると即 red になり完了点を作れない。**

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | **受取先の検査 4 層を新設し、178 件を置換して `--reseal-oracle` する** | `[機械]` **下記「合格条件」の 4 層すべて + 置換の導出との exact-set 一致**。`[手動・外部]` **人間の逐行確認** |

### 合格条件 — **層① 文法**

**改訂 4 の完了後に資産が取り得る値の閉じた集合**:

```
TASK_ID     ::= "TSK-" [0-9]{3}
PENDING_REF ::= "PENDING:" ("FR" | "NFR") "-" [0-9]{3}
```

**`PENDING:TASK-*` は文法から外す**(3 周目 `P0-4`)。**理由**: **本改訂が `TSK-410` / `TSK-411` へ
解決するので、完了後は `PENDING:TASK-*` が 0 件になる。** **値域に残すと、
今回解決した 2 別名以外の架空タスク別名が恒久検査を通り、誤った受取先を後から正規に封印できる。**

**負例**: **`TSK-270-GROUP-2` が red** / **`PENDING:TASK-ANYTHING` が red** /
**`TSK-1234`(4 桁)が red** / **本改訂の前は非空文字列しか見ていなかったこと**(`_expect_string` だけ。現在は `_validate_receiving_task_id_syntax` — `:3728`)**を検査を外して示す**。

### 合格条件 — **層② 参照整合**

- **`PENDING:FR-nnn` / `PENDING:NFR-nnn` は、要件書に実在する条見出しを指すものだけを許す**
- **母集団は `^#### (FR|NFR)-[0-9]{3}` にマッチする見出しから導出する**
  (2026-09-14 の実測で **65 件** — FR-001〜042 の 42 + NFR-001〜023 の 23)。**件数を定数で持たない**
- **`TASK_ID` も実在確認が要る**が、**Notion は CI から引けない**ので
  **「文法を満たす」までを機械の合格条件とし、実在は人間の逐行確認で見る**(下記)
- **負例**: **`PENDING:FR-999` が red**

### 合格条件 — **層③ owner 単位の一致**

- **同一 `runtime_test_owner.id` の行は同一 `receiving_task_id` を持つ**(`S-9` ①・`S-10` (3))。
  **共有 8 組で破ると red**
- **`reason_code` は畳まない**(裁定 `D-23`)— **行の属性のまま**

### 合格条件 — **層④ 差分閉包**(4 段)

**基準版**(`origin/develop...HEAD` の merge-base)**と比較する。**

**段 1 — 変更してよいパスの閉じた集合**:

```
contracts/authz/claim-mutant-map.json
contracts/authz/oracle-seal.lock.json
contracts/authz/mcdc-map.json
```

> **【2026-09-16 実装時に是正】`mcdc-map.json` を許可パスへ足した。**
> **`check_mcdc_map.py:294-301` が `sources.claim_mutant_map.blob_digest` で
> `claim-mutant-map.json` の blob を固定している**ため、**置換すると
> `authz-mcdc-map: 違反: claim-mutant-map の digest 連鎖が不一致` で落ちる**(実測)。
> **許可パス 2 本では完了不能だった。**
>
> **封印は緩まない** — **`mcdc-map.json` は seal の外である**
> (入力 8 資産にも封印 6 資産にも含まれない。実測)。
> **したがって「別の封印資産を同時に変えて reseal する」経路は開かない。**
> **代わりに段 4 で `mcdc-map.json` 側の閉包を掛ける。**

**この 3 本以外の `contracts/authz/**` が 1 バイトでも変わったら red。**
**とくに他の封印資産 5 本**(`ddl-elements` / `rejected-configs` / `attack-tree` /
`boundary-proposal` / `verification-evidence`)**と入力 8 資産は不変。**

**段 2 — `claim-mutant-map.json` で変更してよいフィールド**:

- **`claims[].receiving_task_id`(対象 178 行に限る)のみ**。
  **対象 = 基準版で `receiving_task_id == "TSK-270-GROUP-2"` の行すべて**
  (**`contract_only` 158 + `probe_executable` 20**)。
  **`execution_class` で絞ってはいけない**(5 周目 `P0-1` — **絞ると `probe_executable` 20 行の
  正しい置換が段 2 で red になり、残すと層① で red になって合格不能**)
- **`claim_id` の集合が変わったら red**(行の追加・削除)
- **それ以外のフィールドが 1 つでも変わったら red**(`reason_code` / `execution_class` /
  `runtime_test_owner` / `classification_rule_id` を含む)
- **`oracle_context.oracle_commit` は不変**

**段 3 — `oracle-seal.lock.json` で変更してよい値**:

- **`sealed_assets[]` のうち `path == "contracts/authz/claim-mutant-map.json"` の行の
  `canonical_sha256` だけ**
- **`oracle_commit` / `oracle_commit_semantics` / `review_policy` / `reseal_policy` は不変**
- **`input_assets[]` の 8 行と他の `sealed_assets[]` 5 行は不変**

**段 4 — `mcdc-map.json` で変更してよい値**(**2026-09-16 追加**):

- **`sources.claim_mutant_map.blob_digest` だけ**
- **`sources.body_manifest` / `decisions` / `schema_version` / `asset_kind` は不変**
- **段 2・段 3 と同じ「期待版との完全一致」で見る**

**4 段が無いと、対象外 owner を文法上有効な別タスクへ変えたり、
別の封印資産を同時に変更して `--reseal-oracle` したり、
`mcdc-map.json` の `decisions` を digest 追随に紛れ込ませたりしても通る。**

### 置換先の導出(**152 owner 全件**)

**母集団は `U`**(`contract_only` ∧ `receiving_task_id == "TSK-270-GROUP-2"`)**の 152 owner 全部。**
**非 FR-* の 46 owner だけでは閉じない**(初周 `P0-1`)— **TSK-367 の正本 `:107` が
`FR-034` の 51 owner の宛先を定めており、FR 接頭辞を持つ owner も override の対象になる。**
**46 だけと突合すると、48 件を誤って `PENDING:FR-034` にしても件数条件が通る。**

| 規則 | 対象 | 宛先の導出 |
| --- | --- | --- |
| **`R-A′`** | FR 接頭辞が宛先を返す owner | **`claim_id` の接頭辞の FR**。**その FR が入口を開かない場合は執行先へ寄せる** |
| **`FR-034` の特例** | **51 owner** | **48 → `PENDING:FR-041`**(heading 配下 47 + `list_item-002` 1)/ **3 → `TSK-217`**。`FR-034` 自身は入口を持たない |
| **override 表**(`(+1)` 行を含む) | FR 接頭辞が宛先を返さない owner | 表の宛先 |
| **`R-B`** | 対象横断の判定とハーネス | **`TSK-217`** |
| **除外** | `NFR-012/list_item-003` | **`:134` は改訂 2 の取り消し漏れ。`FR-037` が正**(`:150` `:165`) |

**宛先の導出は override 表だけに依存させない** — **override 表(`(+1)` 行を含む)+ `R-B` 内容表 +
`B_SET` 内訳の和**を取る。**2026-09-14 時点の develop `569954d` では override 表が 44/46**
(`NFR-019/paragraph-001` と `SECTION-8/list_item-002` が `R-B` 内容表と `B_SET` 内訳にだけある)。

**合格条件**: **152 owner すべてに宛先が付き、置換結果が導出結果と exact-set で一致する。**
**1 つでも宛先が付かなければ red。** **件数はすべて資産と TSK-367 の正本から導出し、定数で持たない。**

#### `PENDING:TASK-*` の別名 → 実 ID の写像

**TSK-367 の override 表は別名のまま**で、**どの別名がどの TSK かを書いていない。**
**書かないと実装者が補完して受取先を逆にできる**(2 周目 `P0-3`)。

| 別名 | owner | 実 ID | 典拠 |
| --- | --- | --- | --- |
| **`PENDING:TASK-RECOVERY`** | `SECTION-8/list_item-006` / `NFR-009/list_item-004` | **`TSK-411`** | [バックアップ復元の復旧手順を確定し検証する](https://app.notion.com/p/3da93b75e687818da3aac516470d8c40)のカード本文が「受け取る 2 owner」として逐語で列挙 |
| **`PENDING:TASK-REQ-LABEL`** | `SECTION-4.0-3/table_row-003` | **`TSK-410`** | [要件書: ラベル語彙のチーム拡張に対応する FR 条項を新設する](https://app.notion.com/p/3da93b75e68781fb978fedba7ef499e0)のカード本文が「当該 owner」として名指し |

**exact-set 突合は別名を解決したあとで行う。**
**別名が 1 つでも残っていたら red**(層① が `PENDING:TASK-*` を許さないので機械で落ちる)。

#### 引く commit(**版が動く**)

**【2026-09-16 実測で確定】TSK-367 の是正 6 件は、本改訂の導出結果を 1 件も変えない。**
**したがって本改訂は是正 PR を待たない。**

**引いた版**: develop `35d5ad5`(**PR #65 マージ後**)。
**PR #65 は TSK-217 の射程調整であり、`contract-only-runtime-handoff/plan.md` を 1 行も触っていない**
(同ファイルの最終変更は `ccad476` = PR #62 の時点)。**6 件の是正はまだ develop に入っていない。**

| 是正 | 本改訂への影響 | 理由 |
| --- | --- | --- |
| `:134` の `NFR-012/list_item-003` → `TSK-217` の削除 | **無し** | **上表の「除外」で既に外し、`PENDING:FR-037` へ解決している**(実測で確認) |
| `:156` の override 表へ 2 件追加(44 → 46) | **無し** | **`NFR-019/paragraph-001` と `SECTION-8/list_item-002` は `R-B` 内容表と `B_SET` 内訳から既に `TSK-217` へ解決している**(**3 表の和を取る設計が効いた**) |
| `:164` `:165` のラベル(17 → 16 / 6 → 7) | **無し** | **表示のみ**。実装の明示割当は既に `FR-041` 16 / `FR-037` 7 |
| `:399` `:446` の件数 | **無し** | 文章のみ |

**是正 PR がマージされたら、`R_A_PRIME_OVERRIDE_TARGETS` の内容が変わらないことを再確認する**
(**内容は変わらないはずだが、確認は要る** — 追随義務として記録する)。

### 13 owner の受取契約(**4 周目 `P0` — 切り出しで落ちていた**)

**実 ID を書いて封印しただけでは `R-7` を満たさない。** **`R-7` は `contract_only` を
「schema-drift kill + 受取タスクの runtime テスト ID」と定めており、
受取側が実際にそのテストを持つことまでが契約である。**

**`S-10` (8)(9) は、13 owner についても本改訂では閉じない**(**8 周目 PO 判断 2026-09-16**)。

**当初は「13 owner については本改訂で閉じる」としたが、成立しない。**
**`S-10` (8) は「受取側からの read-back」を要求するが、受取 3 タスクとも未着手で DoD が空である。**
**TSK-317 が DoD へ書いてそれを読み返すのは循環であり、受取側からの read-back ではない。**
**受取側の行動を TSK-317 の完了条件にすると、完了不能な未宣言依存になる。**

**したがって `S-6` と同じ扱いにする** — **受取側の着手待ちへ送る**(2 節の送り先表)。
**`S-6` を送ったのと同じ理由であり、`S-10` (8)(9) だけ別扱いにしていたのが不整合だった。**

**本改訂が行うのは次の 3 つで、これを「受取契約を閉じた」とは呼ばない**:

| 集合 | owner 数 | 受取先 | 受取先の状態 |
| --- | --- | --- | --- |
| **`B_SET`** | **10** | **TSK-217** | **起票済み・未着手**(**計画書と DoD がリポジトリに存在せず、射程の正は Notion カード本文**) |
| **`PENDING:TASK-RECOVERY`** | **2** | **TSK-411** | **起票済み・未着手**。**カード本文が「受け取る 2 owner」を逐語で列挙している** |
| **`PENDING:TASK-REQ-LABEL`** | **1** | **TSK-410** | **起票済み・未着手**。**カード本文が「当該 owner」を名指ししている** |

#### 本改訂が課す 4 つ(**`S-10` (8)(9) の逐語を 13 owner へ当てたもの**)

| # | 本改訂が行うこと | 扱い |
| --- | --- | --- |
| **1 登録** | **受取タスクの DoD へ、受け取る owner の安定 ID を書き込む** | **`[手動・外部]`** |
| **2 相互リンク** | **TSK-317 と受取タスクを双方のコメントで相互に記録する** | **`[手動・外部]`** |
| **3 条文化** | **受取 DoD へ 2 つの条文を書く** — **(a) 受けた owner 集合を資産と exact-set 突合する**(`S-10` (8) の read-back)/ **(b) 各テストで「claim の述語が assertion に現れ、常時成功にすると red」**(`S-10` (9) の退化の負例) | **`[手動・外部]`** |

**`S-10` (8)(9) の充足は受取タスクが行う。** **本改訂は条文を渡すところまでである。**

##### `read-back` の突合は受取タスクへ送る(**7 周目 `P0` — 5・6 周目の設計を撤回**)

**5 周目に「取得は人間・突合は機械」へ分け、6 周目に証跡のスキーマを閉じたが、
7 周目のレビューが「証跡は依然として資産だけから自動生成できる」ことを実測で示した**
(`dod_excerpt = id` で通る・URL は束縛されていない・`card_last_edited` は任意の日付形式・
例示値そのものが禁止集合に無い)。

**設計そのものが循環していた。** **受取側の DoD はまだ空である**
(TSK-411 のカードは「DoD に明記した」が未チェック)。
**TSK-317 が DoD へ書き、それを TSK-317 が読み返しても検証にならない。**

**分け直す**:

| 契約 | 誰が | いつ |
| --- | --- | --- |
| **1 登録** — 受取カードの DoD へ owner の安定 ID を書く | **TSK-317(本改訂)** | 本改訂 |
| **2 相互リンク** — 双方のコメントで相互に記録する | **TSK-317(本改訂)** | 本改訂 |
| **4 退化の負例の条文化** — 「claim の述語が assertion に現れ、常時成功にすると red」を受取 DoD へ書く | **TSK-317(本改訂)** | 本改訂 |
| **3 read-back の突合** | **受取タスクの人間** | **受取タスクの着手時** |

**`read-back` は「受取側が、自分が受けた owner 集合を資産と突合して確認する」ものである。**
**書いた側が読み返すのは検証ではない。**

**受取タスクの DoD へ次を書く**(本改訂の 1 登録の一部):

> - [ ] **TSK-317 から受けた owner 集合を `contracts/authz/claim-mutant-map.json` と
>   exact-set で突合し、差集合 0 を確認した**(`receiving_task_id` が自タスク ID の行)

**証跡ファイル `readback-evidence.json` は作らない**(7 周目 `P0` — **自動生成できる証跡は証拠にならない**)。
**本改訂が機械で確かめるのは資産側だけ**(手順 1〜4)。**Notion 側は人間の逐行確認の観点 4 で見る。**

### `contract_only_reason_code` の導出は変えない

**`expected_reasons` の導出(`:4229-4247`)は `_has_db_decision` / `runtime_target_kind` /
`management_claim_ids` の 3 つに分岐し、`receiving_task_id` に依存しない。**
**したがって受取先を置換しても壊れない。** **新しい理由コードも導入しない。**

**将来 足すなら 2 箇所が要る** — **定数 `CONTRACT_ONLY_REASON_CODES`(`:212`)と導出分岐(`:4229-4247`)**。
**定数追加だけでは `:4249-4251` で「導出理由と不一致」で落ちる**(2026-09-14 に実験で確認)。

### 明示的に確定しないもの

- **`no_db_decision_point` → `TSK-217` の写像** — **これを定めた文書は存在しない**
  (2 系統の独立走査で追認)。**本改訂の前は検査器が受取先について非空文字列しか見ていなかった**(現在は `_validate_receiving_task_id_syntax` — `:3728`)。
  **本改訂は「写像は無い」と記録するだけで、写像を作らない。**
- **既定 7 行の根拠** — **カード本文の「404 / 400 / 存在秘匿の同値性」は実データと合わない**。
  **7 行の `source_text` に `404` も `400` も 0 件**で、**存在秘匿は 1 行だけ**
  (残りはレート制限 2 / 認証構成の補足 1 / トークン失効 1 / PW ポリシー 1 / 人手の復旧経路 1)。
- **TSK-367 が `no_db_decision_point` → TSK-217 の 100% 一致を意図的に崩した件**
  (`FR-041/list_item-014#request-validation` を FR-041 へ回した)— **記録する**。
  **`_has_db_decision` を見た実装者が矛盾と誤認しないため。**

### 実装時に確定する範囲(7.3-7)

- **4 層の検査の実装形**(`re` か `_expect_closed_value` か、負例の生成方法)
- **3 表の和を取る実装**(パーサの罠 4 つ〔説明の丸括弧内の `/` / 継続短縮形 `-003` /
  `(+1)` 文法 / 同一キーの複数行〕の扱い方)。**本書は「和を取り資産と exact-set で突合する」までを契約とする**
- **すべての実測値** — **178 / 158 / 152 / 46 / 65 の各値。**
  **本書の数は 2026-09-14 の実測であり、実装時に測り直して worklog へ記録する。**

---

## 5. DoD(受け入れ基準)

- [ ] **`TSK-270-GROUP-2` の残存が 0 件**(資産から導出・件数を定数で持たない)
- [ ] **置換先が `U` の 152 owner 全件について導出され、資産と exact-set で一致している**
- [ ] **`FR-034` の 51 owner が 48 → `PENDING:FR-041` / 3 → `TSK-217`** になっている
- [ ] **`PENDING:FR-nnn` の 139 owner は `PENDING:` のまま残っている**(置換は入口を開く PR が行う)
- [ ] **`TSK-410` 1 owner / `TSK-411` 2 owner が実タスク ID へ解決されている**
- [ ] **`PENDING:TASK-*` が 0 件**(層① が値域から外している)
- [ ] **`probe_executable` 20 件が `TSK-317`**(`S-9` ②)
- [ ] **層①〜④ がそれぞれ負例で赤くなることを示した**
- [ ] **差分閉包の 4 段が検証節のスクリプトで実行できる**
- [ ] **`oracle_commit` が不変**・**`auth-catalog.json` に触れていない**
- [ ] **`--reseal-oracle` のみを使った**
- [ ] **`oracle_commit` 上の blob 一致を合格条件の根拠にしていない**(`git rev-parse` が失敗すると黙って通る fail-open — `:5206-5214`)
- [ ] **派生資産の `input_manifest` のキー名を直接アサートしていない**(TSK-386 で 2 キーが消える)
- [ ] **受取カード 3 枚**(`TSK-217` / `TSK-410` / `TSK-411`)**の DoD へ 13 owner の安定 ID を書いた**(登録)
- [ ] **TSK-317 と受取 3 タスクを双方のコメントで相互に記録した**(相互リンク)
- [ ] **受取 DoD へ 2 つの条文を書いた** — **(a) 受けた owner 集合を資産と exact-set 突合する** / **(b) claim の述語が assertion に現れ、常時成功にすると red**
- [ ] **「受取契約を閉じた」と書いていない**(**`S-10` (8)(9) の充足は受取タスクが行う** — 8 周目 PO 判断)
- [ ] **段 1 の許可パスが 3 本**(`claim-mutant-map` / `oracle-seal.lock` / `mcdc-map`)**で、それ以外の `contracts/authz/**` が不変**
- [ ] **段 4 が `mcdc-map.json` の `sources.claim_mutant_map.blob_digest` だけを許している**
- [ ] **`uv run pytest tests/` が全件 green**(**MC/DC 検査 2 件を含む**)
- [ ] **段 2 の許可対象が 178 行**(`contract_only` 158 + `probe_executable` 20)**である**(**`execution_class` で絞っていない**)
- [ ] **段 2〜段 4 が merge-base と HEAD を読んでいる**(**作業ツリーを読んでいない・基準コミットを定数で固定していない**)
- [ ] **段 4 が `mcdc-map.json` の生 JSON の重複キーを検出する**(`object_pairs_hook`)
- [ ] **TSK-217 のカードへ 10 owner の安定 ID を追記した**(**TSK-367 が「6 件が明記されていない」と報告**)
- [ ] **送る 6 項目に受取先の実 ID がある**(2 節)
- [ ] **TSK-367 からの依頼 3 点が読める**(規則は TSK-367 が確定済み / 本改訂は消費する側 / 正は先方の 2 節)
- [ ] **引いた commit を明記した**
- [ ] **コア領域の手続きを通した**(敵対レビュー + 人間の逐行確認)

---

## 6. テスト計画(NFR-019)

**本改訂は製品コードを書かないので、`NFR-019` の 5 種別のうち「単体」だけが対象である。**

| 種別 | 何を足すか |
| --- | --- |
| **単体** | `tests/test_check_authz_catalog.py` へ **層①〜④ の正例と負例**。**負例は当該 validator を直接呼び、当該検査を外すと通ることを示す**(規律 5) |
| 一致性 / 越境 / E2E / 故障系 | **足さない**(製品経路を触らない) |

**母集団は導出元から得る**(規律 4)— **178 / 152 / 65 のいずれも定数で持たない。**

---

## 7. 検証(このタスクが終わったことの確認方法)

> **【4 周目 `P0` で設計し直した】検証は「差分を列挙する」のではなく
> 「期待版を構築して完全一致を見る」形にする。**
>
> **理由**: **差分を列挙する形は、列挙し忘れた軸がそのまま抜け道になる。**
> **4 周目のレビューは、私が書いた 3 つのスクリプトすべてで迂回を再現した** —
> **段 1 は `grep -v` が正常時に exit 1・禁止パス検出時に exit 0 で合否が逆**、
> **段 2 は非対象 owner の `receiving_task_id` 変更を通し `claims` 外も見ていない**、
> **段 3 はトップレベルの未知キーと `sealed_assets` の並べ替えを通した。**
>
> **期待版との完全一致なら、許可した以外のすべての変化が自動的に red になる。**

> **【8 周目 PO 判断 2026-09-16】本節は「門」ではない。**
>
> **8 周目のレビューが「一時 worktree でも、手順 4 以降で作業ツリーを直せば迂回できる」と指摘し、
> これを「同じ面への patch 要求」と自ら分類した。** **そのとおりである** —
> **人間が手で走らせる手順に迂回不能性を持たせようとしていたのが誤りだった。**
> **手で走らせる以上、どんな順序で何を確かめても、走らせる人が途中で変えられる。**
>
> **迂回不能性は CI が持つ。** **層①〜④ は `scripts/check_authz_catalog.py` と
> `tests/test_check_authz_catalog.py` に入る**(ステップ 1 の成果物)**ので、
> `harness` ジョブの `pytest tests/` が PR の HEAD の clean checkout で走らせる**
> (`ci.yml:78` に `fetch-depth: 0`・人間は介在しない)。
>
> **本節はその再実行手順であり、「人間が完了を確認するため」のものである。**
> **一時 worktree は再現性のために残すが、それを保証とは呼ばない。**
> **この面は射程から外し、`P0` として追わない。**

```bash
WT=/home/ymdms/projects/pitchlog-worktrees/feature-pg-authz-verification-g3
cd "$WT"
set -e   # 途中で落ちたら止める(4 周目 P0-1)

# 0. 検証は HEAD の clean checkout で走らせる(**7 周目 P0**)
#    作業ツリーで走らせると、開始時にクリーンでも「手順 3 のあとに作業ツリーだけ正しく直す」
#    経路が残る(段 2〜4 は merge-base と HEAD を読み「変更なし」を許容し、
#    手順 4・6 は作業ツリーを読む — 「段」ではなく本ブロックの手順番号)。
#    git status --porcelain も --untracked-files=all を固定しないと Git 設定で抑制できる。
#    一時 worktree を切れば、以降のすべての手順が同じ HEAD スナップショットを見る。
VERIFY_DIR=$(mktemp -d)/verify
git worktree add --detach "$VERIFY_DIR" HEAD
# trap は「自分がいるディレクトリ」を消しに行くので、先に出てから消す(実測で pwd エラーを再現)
trap 'cd "$WT"; git -C "$WT" worktree remove --force "$VERIFY_DIR" 2>/dev/null || true' EXIT
cd "$VERIFY_DIR"
echo "0 OK — HEAD の clean checkout で検証する($VERIFY_DIR)"
# 注: clean checkout では uv が venv を作り直す(実測で 8 パッケージ・約 0.6 秒 + フルコピー)。
#     ハードリンクが効かない旨の警告が出るが検証結果には影響しない。

# 1. 残存 0 件と分布(資産から導出)
uv run python - <<'EOF'
import json, collections, sys
d = json.load(open("contracts/authz/claim-mutant-map.json"))
c = collections.Counter(x["receiving_task_id"] for x in d["claims"])
if "TSK-270-GROUP-2" in c:
    sys.exit(f"残存 {c['TSK-270-GROUP-2']} 件")
if [k for k in c if k.startswith("PENDING:TASK-")]:
    sys.exit("PENDING:TASK-* の別名が残っている")
print(sorted(c.items()))
EOF

# 2. 差分閉包 段 1 — 変更してよいパスは 3 本だけ(合否判定にする — D-27)
uv run python - <<'EOF'
import subprocess, sys
ALLOWED = {
    "contracts/authz/claim-mutant-map.json",
    "contracts/authz/oracle-seal.lock.json",
    "contracts/authz/mcdc-map.json",
}
changed = subprocess.check_output(
    ["git", "diff", "--name-only", "origin/develop...HEAD", "--", "contracts/"],
    text=True).split()
forbidden = sorted(set(changed) - ALLOWED)
if forbidden:
    sys.exit("禁止パスが変更されている: " + ", ".join(forbidden))
print(f"contracts/ の変更は許可 3 本のみ({len(changed)} 件)")
EOF

# 3. 差分閉包 段 2〜段 4 — 期待版を構築して完全一致を見る
#    基準側は merge-base、比較側は HEAD。どちらも git show で読み、作業ツリーは読まない
#    (5 周目 P1-3 — 基準コミットを定数で固定しない)。手順 0 の clean checkout は
#    手順 4・6 のためのもので、本手順の正しさはそれに依存しない。
uv run python - <<'EOF'
import json, subprocess, sys, copy

def at(rev, path):
    return json.loads(subprocess.check_output(["git", "show", f"{rev}:{path}"], text=True))

def ser(obj):
    # dict は挿入順を保つので、並べ替えも差として出る(sort_keys を使わない)
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False)

MB = subprocess.check_output(["git", "merge-base", "origin/develop", "HEAD"], text=True).strip()
CMM = "contracts/authz/claim-mutant-map.json"
SEAL = "contracts/authz/oracle-seal.lock.json"

# --- 段 2: claim-mutant-map ---
# 基準側 = merge-base、比較側 = HEAD。ともにコミット済みを読む(作業ツリーは読まない)
base, head = at(MB, CMM), at("HEAD", CMM)

# 許可対象 = 基準版で receiving_task_id == "TSK-270-GROUP-2" の行すべて
#   contract_only 158 + probe_executable 20 = 178(5 周目 P0-1 — execution_class で絞らない)
target_idx = {i for i, c in enumerate(base["claims"])
              if c.get("receiving_task_id") == "TSK-270-GROUP-2"}
if not target_idx:
    sys.exit("対象行が 0 件。基準版の取り方が誤っている")

expected = copy.deepcopy(base)
if len(expected["claims"]) != len(head["claims"]):
    sys.exit("claims の行数が変わった")
for i, (e, h) in enumerate(zip(expected["claims"], head["claims"])):
    if e["claim_id"] != h["claim_id"]:
        sys.exit(f"claim の並びが変わった: {e['claim_id']} vs {h['claim_id']}")
    if i in target_idx:
        e["receiving_task_id"] = h["receiving_task_id"]   # 対象行だけ HEAD を採る
if ser(expected) != ser(head):
    sys.exit(f"{CMM}: 対象 178 行の receiving_task_id 以外が変わっている")
print(f"段 2 OK — 対象 {len(target_idx)} 行の receiving_task_id だけが変わった")

# --- 段 3: oracle-seal.lock ---
sb, sh = at(MB, SEAL), at("HEAD", SEAL)
exp = copy.deepcopy(sb)
if len(exp["sealed_assets"]) != len(sh["sealed_assets"]):
    sys.exit("sealed_assets の件数が変わった")
hit = 0
for e, h in zip(exp["sealed_assets"], sh["sealed_assets"]):
    if e["path"] != h["path"]:
        sys.exit(f"sealed_assets の並びが変わった: {e['path']} vs {h['path']}")
    if e["path"] == CMM:
        e["canonical_sha256"] = h["canonical_sha256"]     # この 1 leaf だけ HEAD を採る
        hit += 1
if hit != 1:
    sys.exit(f"claim-mutant-map の sealed_assets 行が {hit} 件(1 件であるべき)")
if ser(exp) != ser(sh):
    sys.exit(f"{SEAL}: claim-mutant-map 行の canonical_sha256 以外が変わっている")
print("段 3 OK — seal の変更はその 1 leaf だけ")

# --- 段 4: mcdc-map(重複キーも見る)---
MC = "contracts/authz/mcdc-map.json"
def raw(rev, path):
    return subprocess.check_output(["git", "show", f"{rev}:{path}"], text=True)
def pairs(text):
    # 恒久検査(_parse_unique_mcdc_map_json)と同じ厳しさで読む。
    # parse_constant を落とすと NaN / Infinity が通る(実装後レビュー 3 周目 P1)
    def reject_constant(c):
        sys.exit(f"{MC}: 標準外の数値定数がある: {c}")
    dup = []
    def hook(items):
        seen = set()
        for k, _ in items:
            if k in seen: dup.append(k)
            seen.add(k)
        return dict(items)
    obj = json.loads(text, object_pairs_hook=hook, parse_constant=reject_constant)
    return obj, dup

mb_obj, mb_dup = pairs(raw(MB, MC))
hd_obj, hd_dup = pairs(raw("HEAD", MC))
# 基準版と HEAD の両方を見る。基準版だけに重複を注入すると期待版が汚れるため
# (実装後レビュー 2 周目 P1 — mb_dup を取得して使っていなかった)
if mb_dup or hd_dup:
    sys.exit(f"{MC}: 重複キーがある: 基準版={sorted(set(mb_dup))} HEAD={sorted(set(hd_dup))}")
em = copy.deepcopy(mb_obj)
em["sources"]["claim_mutant_map"]["blob_digest"] = hd_obj["sources"]["claim_mutant_map"]["blob_digest"]
if ser(em) != ser(hd_obj):
    sys.exit(f"{MC}: sources.claim_mutant_map.blob_digest 以外が変わっている")
print("段 4 OK — mcdc-map の変更はその 1 leaf だけ(重複キーなし)")
EOF

# 4. 置換先が規則の導出と exact-set 一致(段 2 と独立 — 値そのものを見る)
#    導出の実装はステップ 1 の成果物。ここではその出力と資産を突合する。
uv run python scripts/check_authz_catalog.py

# 5. 正本反映の突合(本改訂は正本を変更しない)
uv run python scripts/check_plan_docs_sync.py --plan docs/features/pg-authz-verification-g3/plan.md --base origin/develop

# 6. 現在地導出と品質ゲート
uv run python scripts/feature_status.py
uv run ruff check . && uv run ty check && uv run pytest tests/
```

> **判定ロジックの負例検査(2026-09-14 実測)** — **4 周目のレビュアが再現した迂回 3 つが塞がることを確かめた**:
>
> | 注入 | 期待 | 実測 |
> | --- | --- | --- |
> | 無変更 | green | **green** |
> | 対象 owner の `receiving_task_id` を置換 | green | **green** |
> | **非対象 owner**(`TSK-250` → `TSK-217`)を変更 | red | **red** |
> | **`claims` 外**(`schema_version`)を変更 | red | **red** |
> | **未知のトップレベルキー**を追加 | red | **red** |
> | 対象行の**別フィールド**(`contract_only_reason_code`)を変更 | red | **red** |
>
> **段 1 も同様に確かめた**(変更なし / 許可 3 本 = green、禁止パス注入 = red)。
> **段 3 は段 2 と同じ「期待版との完全一致」なので同型である。**

> **段 2・段 3 の限界(明示 — 5 周目 `P2` で説明を是正)**: **JSON の重複キーは `json.loads` が
> 後勝ちで畳むので、段 2・段 3 では検出できない。**
> **`check_authz_catalog.py` の `_expect_keys` も落とせない** — **同スクリプトは先に通常の
> `json.loads` で読む**(`:588`)**ので、`_expect_keys` から重複キーは見えない。**
> **実際に落とすのは `tests/test_check_authz_catalog.py` の `object_pairs_hook` を使う恒久検査**
> (`_strict_json_object` — `:405` / 段 4 の負例 — `:3106`)**であり、手順 6 の `pytest tests/` で掛かる。**
> **したがって全検証経路としては red になるが、「手順 4 が守る」という説明は誤りだった。**
>
> **段 4 はこの限界を持たない(実装後レビュー 1 周目 `P1-1`)**: **`mcdc-map.json` は凍結 15 資産の
> 重複キー検査の対象外**なので、恒久検査に頼れない。**段 4 だけは `object_pairs_hook` で
> 基準版と HEAD の両方の生 JSON を読み、重複キーを自分で落とす。**

**人間が確認すること**(**コア領域 — 逐行確認必須**):

| # | 観点 | なぜ人間が要るか |
| --- | --- | --- |
| 1 | **152 owner の置換先が TSK-367 の規則と一致するか** | **規則の適用は意味判断を含む**(`R-A′` の「その FR が入口を開かない場合は執行先へ寄せる」) |
| 2 | **`FR-034` の 51 owner の割り当て**(48 → `FR-041` / 3 → `TSK-217`) | **FR 自身が入口を持たない、という判断の妥当性** |
| 3 | **`TSK-410` / `TSK-411` が実在し、当該 owner を受け取るカードか** | **Notion は CI から引けない**(層② の限界) |
| 4 | **13 owner の受取契約が受取側へ届いているか**(下記) | **Notion カードの DoD は機械で見られない** |
| 5 | **射程を `S-9`/`S-10` へ絞る判断**(裁定 `D-22`) | **裁定 `D-14` の再割り当てである** |

## 8. 進め方

1. 本計画書 + [design.md](design.md) を**コア領域の敵対レビュー**へ:
   `python .claude/scripts/codex_run.py review adversarial -`
2. 指摘を反映(**採用反映を伴うレビュー 1 周ごとに frontmatter の `計画レビュー周回` を +1**)
3. 収束したら**人間の承認**を求める → `承認: 済(YYYY-MM-DD・承認者)` へ
4. 承認後 `/implement` で**ステップ 1 を委任する**(1 委任 = 1 ステップ = 1 コミット・
   件名に完全トークン `(ステップ 1/1)` をちょうど 1 個)
5. `/check` → `/pr`(**コア領域なので敵対レビュー + 人間の逐行確認のチェックが付く**)

> **`承認: 未` の間、現在地導出はステップ進捗を表示しない**(`feature_status.py`)。
> **`codex_run.py implement` も `承認: 済` でないと拒否する。**

## 9. 人間の逐行確認(**2026-09-16 実施 — コア領域の必須手順**)

**判定: 4 件とも「是」。差し戻しなし。**

### 機械で閉じた範囲(人手不要と判定した根拠)

**計画書 7 節が「人間が確認すること」として挙げた 4 観点のうち、3 観点は機械で閉じた。**

| 観点 | 閉じ方 |
| --- | --- |
| **① 152 owner の置換先が TSK-367 の規則と一致するか** | 原典の override 表を解析し `R_A_PRIME_OVERRIDE_TARGETS` と exact-set 比較 → **44 / 44・差分 0**。**パーサ監査**(表内の全 backtick token を分類し、owner 断片の読み飛ばしが 0)も実施 |
| **② `FR-034` の 51 owner の割り当て** | 原典 `:107` が宣言する「53 行 / 51 owner — 50 行 / 48 owner + 3 行 / 3 owner」を資産から再測 → **完全一致**。`contract_only` の宛先が 2 種以外に無いことも確認 |
| **③ `TSK-410` / `TSK-411` の実在** | **Notion を直接取得した**。計画書は「Notion は CI から引けない」と書いたが、**それは CI の話**で、コネクタ経由では引ける。タスクID プロパティが実在し、3 owner とも本文に逐語 |
| **④ 13 owner の受取契約** | `TSK-217` はカードのスコープ節の 10 owner 表と資産が **10 / 10 一致**(既存 7 も一致・7 + 10 = 17・互いに素)。`TSK-411` は DoD に 2 owner の所有が明記 |

### 人間が判断した 4 件

| # | 対象 | 判断 |
| --- | --- | --- |
| **差** | **`TSK-410` の受取契約が runtime テストの所有を約束していない** | **是**(封印する)+ 後続 2 つ |
| **j1** | `SECTION-3/table_row-002` を `FR-041` → `FR-037` へ移した判断 | **是** |
| **j2** | `SECTION-4.0-2/list_item-001`(物理削除しない)を `TSK-217` へ戻した裁定 | **是**(現状維持) |
| **j3** | `SECTION-8/list_item-006`・`NFR-009/list_item-004` を `TSK-411` 新設で受ける二重否定 | **是** |

### 申し送り(判断に付随して確定したもの)

1. **`TSK-410` は中継点である** — カードの DoD は「認可主張が**その FR 条項へ帰属できる**」までで、
   **runtime テストの所有を約束していない**。**`PENDING:FR-*` と同じ性格なのに実 TSK ID で封印される**ため、
   層① の文法は通り、**次の置換を強制する機構が無い**。
   **恒久的な検出は [TSK-383](https://app.notion.com/p/3d993b75e68781ad8663dce3ac2484a2)(置換義務の検査)へ送る**
   — 既に `PENDING:FR-nnn` 139 owner の置換義務を送っている先と同じ受け皿である。
   **当座は先方カードへコメントで DoD への追記を依頼した**(2026-09-16)。
2. **`FR-037` の実装タスクは `FR-041` に依存する** — `SECTION-3/table_row-002` の条文が
   **共同分析グループの管理操作(`FR-041` — 作成/招待の発行・失効/参加/離脱/付与変更/役割変更/終了)を
   明示的に含む**。`R-A′` は「執行される入口を開く FR」を見るので、システム管理者の入口である
   `FR-037` へ寄せる判断は正しいが、**テストを書く時点で `FR-041` が要る**。割り当ての誤りではなく順序の問題。
3. **`TSK-217` の owner #9 は残余置き場としての割り当てである** —
   `SECTION-4.0-2/list_item-001` の条文は**二重**で、前半「利用者操作はすべて論理削除まで」は真に横断的だが、
   **後半「物理削除はシステム管理者の DB 保守作業のみ」は `FR-037` の territory**
   (j1 の行が「DB保守」をシステム管理者の権限として挙げ、その行は `FR-037` へ行く)。
   **`TSK-217` のカード自身が「『ハーネス』の定義は未確定・運用例 2 件を超えて射程を広げない」と書いており、
   owner #9 はその 2 例のどちらでもない**(根拠欄も「届かない」)。
   **カードが宣言している「定義の確定は PO 裁定へ送る」の際に、owner #9 を併せて整理する。**

### 確認に使った補助

**機械生成の突合シート**(原典のセルを逐語で並べ、抽出 owner と定数を対照)を用意して確認した。
**シートは一回限りの検証補助であり、リポジトリには置かない**(2 節「文書検査器を作らない」の方針どおり)。
