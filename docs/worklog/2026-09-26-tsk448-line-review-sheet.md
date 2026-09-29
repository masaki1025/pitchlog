---
date: 2026-09-26
topic: TSK-448 逐行確認シート(コア領域 — テナント分離)
branch: feature/frozen-history-7d-remainder
---

# TSK-448 逐行確認シート

**確認対象**: `ec02a0d2440bb7749ec004ec4cc79776b78b9264` → `98083df4f0c0d135473333d8044629cb932452a8`
**総差分**: 12,450 行追加 / 28 行削除 / 37 ファイル

> **2026-09-30 更新(2 回目) — develop(`ec02a0d2` = PR #84)の取り込みでシートを実装へ追従させた。**
>
> **確認対象の変遷**:
>
> | | 範囲 | 差分 |
> | --- | --- | --- |
> | 当初 | `1a404101` → `a394ac5d` | 11,453 行追加 / 25 行削除 / 32 ファイル |
> | 1 回目の追従 | `33afd352` → `51557bb7` | 12,248 行追加 / 29 行削除 / 37 ファイル |
> | **現行** | **`ec02a0d2` → `98083df4`** | **12,450 行追加 / 28 行削除 / 37 ファイル** |
>
> **2 回目の追従で変わったのは受理記録の識別値・snapshot・比較元 SHA・派生 digest のみ。A-1〜A-5 の判断項目と B・C は内容が変わっていない**(**前版比較の結果 `{4, 5, 6, 7, 11}` も 3 度の再固定を通じて不変**)。
>
> **取り込みを逐行確認より先に済ませたのは、`plan.md:220` が「確認後の差分は証跡ファイルに限る」と定めているため**(先に確認すると、その後の取り込みが証跡以外の差分になる)。

**このシートの目的**: **機械で検証済みの部分と、人間にしか判断できない部分を分ける。** **機械が確かめたことを人が再確認する必要はない。**

---

## A. 人間にしか判断できないもの(**ここを見てください**)

### A-1. 新しい機構そのもの — `scripts/frozen_archive.py`(362 行)

**本 PR が足した唯一の実行される機構である。** 次を判断してください。

| 観点 | 問い |
| --- | --- |
| **抽出の正しさ** | **v2 記録だけを走査し、4 経路(`change.before/after` の `external_snapshots` / `asset_snapshots` の `snapshot_ref`)から抽出する**のは妥当か。**v1 を除外してよいか** |
| **明示表** | **`ASPECT_NAMES` から導出せず明示表を置いた**判断は妥当か。**分類値の exact-map 比較で誤分類を拘束できているか** |
| **閾値** | **500 件 / 32 MiB / 孤児は比較元からの増加ゼロ**。**予算であって上限の証明ではない**と書いたことを含めて妥当か |
| **不変量** | **「HEAD にあって比較元に無い snapshot は、すべて構造的参照集合に含まれる」**が、**TSK-431 が 29 件の孤児を作った経路を実際に塞ぐか** |

### A-2. 本番経路への結線 — `scripts/check_tenant_boundary_bypass.py`(+19 行 / 削除 0 行)

**追加のみで、既存の文を 1 つも変更・削除していない**(機械検証済み)。**判断してほしいのは位置**です。

- **`_validate_repository_histories` の中で、既存の `frozen_history.validate_repository_histories` が成功した直後**に呼んでいる
- **理由**: 前に置くと **archive のエラーが movement・履歴・識別値のエラーを隠す**
- **この順序でよいか**

### A-3. 射程の切り方(**人間の判断 2026-09-26 の再確認**)

| 外したもの | 理由 | 受け取り先 |
| --- | --- | --- |
| **退去(削除)の機構** | `load_contract` が 7 資産を無条件に読む必須入力で、削除すると退去の検査より前に落ちる。条件付きにすると検査入力を退去記録だけで外せる(空洞化)。**実行不能か空洞化の二択** | **TSK-461** |
| **D6 識別値母集団の是正** | **本 PR の本番経路では到達しない**(`load_contract` か削除拒否が先に落ちる)。到達不能な変更をコア領域の PR に入れない | **TSK-461** |
| **既存の孤児 29 件の回収** | `_validate_snapshot_append_only` の緩和は射程を超える | **TSK-461** |

**この 3 つを外した判断が今も妥当か**を確認してください。

### A-4. 「主張しない範囲」7 項目(design.md 7 節)

**PR 本文へそのまま転記する。** **主張しすぎていないか**を確認してください。

### A-5. develop 取り込みで生じた判断 3 件(**2026-09-30 追加**)

コミット `51557bb7` が PR #85・#86 を取り込んだ。次の 3 件は人間の判断が入っている。

**① 凍結資産を 7 件 → 8 件へ広げた**(承認: 山田正輝 2026-09-29)

> **現行の識別値**(`ec02a0d2` 取り込み後): base 19 / cache 6 / census 6 / inventory 8 / negative 10 / repository 7 / runtime 6 / tenant-context 9

#86 が `contracts/tenant_boundary/census-baseline.json` を追加したため、計画書を改訂して 8 資産すべてへ
`scripts/frozen_archive.py` を宣言した。**射程の拡大ではなく develop への追随**という整理である
(受理記録が 8 資産を覆うことは `frozen_history.py:438-447` のディレクトリ走査により選択の余地がない)。
**この整理でよいか**を確認してください。

**② 比較元を `1a404101` → `33afd352` へ再固定した**

design.md 6-2 の「比較元は道具なので develop を取り込むたびに再固定する」規則の適用。
再実測の結果、**緩和 0 件・締め `{4,5,6,7,11}` は変わらなかった**。
**「比較元を動かした結果として合格した」のではないこと**を確認してください。

**③ 未参照 snapshot 8 件を除去した**

#83 自身の中間コミットが作ったもので、**新しい比較元に 1 件も存在しない**(照合済み)。
design.md 1-4 が明示的に許している操作である。**比較元の snapshot は 1 件も変更・削除していない**
(develop の 70 件と削除 8 件の積集合が 0 件であることを機械照合済み)。

---

## B. 機械が検証済み(**再確認は不要**)

### B-1. 受理記録が実体と一致する(**実装レビュー 1 周目の P1-1**)

**`change.after.external_snapshots` — 4 件すべて実ファイルの sha256 と一致**

- `.github/workflows/ci.yml` — **一致** (`47d436cef5f1c9ae…`)
- `scripts/check_tenant_boundary_bypass.py` — **一致** (`8607fa7c6a4d6d34…`)
- `scripts/frozen_archive.py` — **一致** (`66e198f6c8ba13d2…`)
- `scripts/frozen_history.py` — **一致** (`0bd319d2118948d2…`)

**`change.after.asset_snapshots` — 7 件すべて `frozen_projection_content` の再計算値と一致**

- `base-allowlist.json` — **一致** (`c8478d5dd508f5e4…`)
- `cache-invalidation-contract.json` — **一致** (`55d22aa27ad4e0d3…`)
- `db-api-inventory.json` — **一致** (`cd197edafd53421d…`)
- `negative-fixtures.json` — **一致** (`6259be8cac882807…`)
- `repository-contract.json` — **一致** (`8de6f5922eaf6698…`)
- `runtime-authz-contract.json` — **一致** (`3cbe8c2be6aede44…`)
- `tenant-context-allowlist.json` — **一致** (`990be77fcbbcea58…`)

**回帰テスト** `test_current_checker_accepts_actual_repository_transition` が、**記録を実体からずらすと落ちる**ことを変異で確認済み。

### B-2. 孤児を 1 件も増やしていない

| | 値 |
| --- | ---: |
| 比較元の snapshot | 55 件 |
| HEAD の snapshot | 64 件 / 2,181,504 B |
| **本 PR が追加** | **9 件(未参照 0 件)** |
| **孤児** | **29 件 / 1,021,201 B(比較元と同じ)** |
| 閾値への余裕 | 64/500 件・2.08/32 MiB |

**TSK-431 は敵対レビュー 4 周の作り直しで 29 件の孤児を作った。本 PR は 9 件足して 0 件である。**

### B-3. 派生値が機械再計算と一致する

**7 資産の識別値・`source_digest` 4 件・`inventory.sha256`・生成モジュール 3 件。** **敵対レビューが独立に再計算して一致を確認済み**(1 周目の「確認できた事項」)。

- `base-allowlist.json` — `contract_revision:17`
- `cache-invalidation-contract.json` — `contract_revision:5`
- `db-api-inventory.json` — `inventory_revision:7`
- `negative-fixtures.json` — `fixture_set_revision:9`
- `repository-contract.json` — `contract_revision:6`
- `runtime-authz-contract.json` — `runtime_contract_revision:5`
- `tenant-context-allowlist.json` — `contract_revision:8`

### B-4. fail-closed F1〜F11 が本番経路で red になる

**`validate_snapshot_archive` を no-op へ変異させると 11 件中 10 件が落ちる**(変異で確認済み)。

**生き残る 1 件は F11(既存 snapshot の変更・削除)**で、これは `frozen_history.py` の `_validate_snapshot_append_only` が担う既存の検査。**`frozen_archive` が重複実装していないことの裏づけ**(NFR-018)。

### B-5. 検査を緩めていない(前版比較)

**比較元 `1a4041018c0b00fc0a86c11bec5ba0a38c3f2070`** に対して 11 ケースを両版へ当てた結果:

```
前版 red → 新版 green: 0 件            ← 緩めていない
前版 green → 新版 red: [4,5,6,7,11]   ← 期待と exact-set 一致
11 ケースすべてが design.md 6-3 の期待と一致
```

### B-6. 構造検査 S1〜S7

| # | 条件 | 実測 |
| --- | --- | --- |
| **S1** | `scripts/frozen_history.py` の差分 0 行 | **0 / 0 行** |
| **S2** | 検査器は追加のみ | **+19 / -0 行** |
| **S3** | 7 資産は許可 exact-set のみ | 識別値・`source_digest`・`inventory.sha256`・記録 1 件 |
| **S5** | 生成モジュール 3 件は版・digest のみ | **backend で 581 passed** |
| **S6** | 既存テストは 3 項目のみ | exact-list・コピー許可・履歴件数 |
| **S7** | core-areas への登録 | **`tests/test_frozen_archive_case_runner.py` を追加済み** |

---

## C. 目視しなくてよいファイル(**理由つき**)

| 種別 | ファイル数 | 行数 | 目視不要の理由 |
| --- | ---: | ---: | --- |
| **snapshot(content-addressed)** | 9 | 6,654 | **ファイル名が内容の sha256 である。** **B-1 で全件が実体と一致することを機械検証済み**。人が読む意味がない |
| **テスト** | 6 | 2,288 | **B-4(変異で 10/11 が落ちる)と B-5(前版比較)で実効性を確認済み**。**ただし A-1 の判断のために `test_frozen_archive.py` の変異ケースの網羅性だけは見る価値がある** |
| **文書** | 4 | 1,326 | 計画・設計・worklog。**A-3 と A-4 で該当箇所だけを見る** |

---

## D. 既知の failure(**本 PR の変更が原因ではない**)

### D-1. 解消済み — `test_checker_census_matches_merge_base`(**2026-09-30**)

**旧記載**: 比較元に可変参照 `origin/develop` を使っているため、マージ後は比較対象が同一物になり差分が必ず空になる。
`fix/census-baseline-pin` で是正中のため、その PR が入るまで本 PR はマージできない、としていた。

**→ `fix/census-baseline-pin` は PR #86 として develop へマージ済み。本取り込み(`51557bb7`)で解消した。**

### D-2. 現行 — backend の DB 試験 211 件が setup error(**環境要因**)

```
Failed: 被検査ロールがテスト開始前から存在する: pitchlog_test_role
backend/tests/db_fixtures.py:318
```

- **開発 DB に `pitchlog_test_role` が残っており、フィクスチャの事前条件を満たさない**(中断されたテスト実行の残留)
- **`origin/develop` の作業木で同じテストを回しても同一の失敗**(実測 2026-09-30)。本 PR の変更が原因ではない
- **是正**: 開発 DB から当該ロールを削除する。開発 DB は他セッションと共有のため、実行タイミングは人間が決める

---

## E. 実施記録(**確認した人が記入してください**)

- 確認対象コミット: `98083df4f0c0d135473333d8044629cb932452a8`
- 対象= 
- 範囲= 
- 方法= 
- 確認者= 
- 確認日= 

