---
feature: frozen-history-7d-remainder
date: 2026-09-26
---

# 詳細設計: 7.7-4 の残り — 履歴アーカイブの規律(TSK-448)

**調査の正**: [research.md](research.md)。**本書は裁定だけを書き、調査の内容を複製しない**(設計書 7.1-1)。

**改訂履歴**

| 周 | 変えたこと |
| --- | --- |
| 1 周目 | **D3(論理キー)を取り下げ**(前提が誤り)。**D5(実装の隔離)を新設**。論理履歴・正規化規則・構造的抽出・閾値を確定 |
| 8 周目 | **S6 に authority 履歴件数(2 → 3)の更新を許可**。**S7 を新設**(`.claude/core-areas.json` への登録と `tests/test_core_guard.py` の exact-set 同期 — 設計書 6.3)。**あわせてステップ 1 に「変更対象の網羅リストを機械的に得る」を追加**し、この種の挙げ漏れを計画の予測ではなく実測で閉じる |
| 7 周目 | **S3 の項目 2 を「トップレベル revision field と `current_identifiers` の同期更新」へ**(P1 — 7 資産すべてが `integer_revision_field` 方式で、据え置いても更新しても red だった)。**既存テストの exact-list を変更対象へ追加**(P1) |
| 6 周目 | **S3 に派生更新を許可**(P1 — `external_files` の変更が 4 資産の `source_digest`・`base-allowlist` の `inventory.sha256`・3 つの生成モジュールへ波及する。**実測で確認**) |
| 5 周目 | **非緩和の構造検査を実行可能な条件へ是正**(P1 — `frozen_archive` の呼び出しは既存関数の本体へ足すので「既存関数の本体に差分が無い」は達成不能だった。`external_files` の追加先も 7 資産の JSON であって検査器ではない) |
| 4 周目 | **抽出表を「分類値まで exact-map 比較」へ**(P1 — キー集合だけでは誤分類を拘束できない)。**結線順序を `validate_repository_histories` の成功直後に確定**。**fail-closed を番号つき exact-set(11 種)へ**。**非緩和の主張を 11 ケース corpus 内に限定** |
| 3 周目 | **D6(識別値母集団)を TSK-452 へ送り出した**(P1 — 本番経路で到達不能でケース 8 が成立しない)。**参照抽出を v2 限定の明示表へ**。**結線位置を `_validate_repository_histories` 内に確定** |
| 2 周目 | **退去(削除)を通す機構を射程から外した**(P0 — 下記 0-2)。**人間の判断 2026-09-26。** 本タスクは**履歴アーカイブの規律**に絞る。**退去の仕様は実装せず、契約として書いて送り出す** |

---

## 0. 射程

### 0-1. 本 PR に入れるもの

| | 中身 |
| --- | --- |
| **D4** | **履歴アーカイブの規律**(**本 PR の主題**)— **参照を構造的に抽出**し、**閾値を確定して機械化**し、**新規孤児ゼロを不変量にする** |
| **D5** | **実装の隔離** — 新モジュールへ書き、最終ステップで結線する |
| **D1'** | **退去の記録形式と論理履歴の契約を「仕様」として確定する**(**実装しない**)。受け取り先への引き渡し |

### 0-2. 退去を通す機構を外した理由(敵対レビュー 2 周目 P0 — 原典で確認済み)

**`scripts/check_tenant_boundary_bypass.py` の `load_contract` は `FROZEN_BASELINE_ASSETS` の 7 資産すべてを無条件に読む必須入力である**(逐語)。

```python
for asset_path in FROZEN_BASELINE_ASSETS:
    if asset_path not in asset_values:
        asset_values[asset_path], _ = _read_json(repository_root / asset_path)
    _validate_baseline_control(asset_values[asset_path], asset_path.as_posix())
```

**資産ファイルを削除すると、退去の記録を検査する前にここで落ちる。** **したがって「非 authority 資産なら削除できる」は成立しない** — **7 資産のどれ 1 つも削除できない。**

**`load_contract` を一律に条件付きへ変えると、DB API inventory・negative fixtures・tenant-context・cache-invalidation の検査入力を、退去記録だけで外せる経路ができる**(テナント境界検査の空洞化)。

**「実行不能か空洞化の二択」であり、448 の射程(7D の残り)では安全に閉じられない。** **人間の判断 2026-09-26 により、退去機構を外す。**

### 0-3. 送り出すもの

| 範囲 | 受け取り先 | 引き渡すもの |
| --- | --- | --- |
| **D6 識別値の母集団の是正**(`previous` = 比較元 ∪ HEAD / `new` = HEAD 現役のみ) | **TSK-452** | **本書 2 節**。**本 PR では本番経路に到達しない**(`load_contract` が先に落ちる)ため、**到達不能な変更をコア領域の PR に入れない**(敵対レビュー 3 周目 P1) |
| **退去を通す機構**(資産ごとの「運用上必須 / 退去可能」の機械可読な確定・退去後の `load_contract` と検査能力の設計) | **TSK-452(新設を提案)** | **本書 3 節の仕様**(記録形式・論理履歴・fail-closed の一覧) |
| **PR B(TSK-443)の暫定資産の扱い** | **TSK-443** | **本書 3-4**(**削除しない形なら 448 / 452 を待たない**) |
| **既存 v1 記録への ID の遡及・既存記録の訂正** | **TSK-450** | — |
| **孤児 snapshot 29 件の実削除** | **TSK-452** | **本 PR は grandfather と増加ゼロまで** |
| **7E**(バイト正規化) | **TSK-449** | — |

---

## 1. D4 — 履歴アーカイブの規律(本 PR の主題)

### 1-1. 実害(TSK-431 が作った)

**孤児 snapshot 29 件・1,021,201 バイト(全体の 66.3 %)が回収不能**([research.md](research.md) 4)。

**原因**: 敵対レビュー 4 周で記録を作り直すたび、旧 snapshot が参照を失った。**`_validate_snapshot_append_only` が削除を拒否する**ので回収できない。

**現行の 3 閾値は `history` 配列の byte 長しか数えておらず、実装に検査が 1 つも無い**(`tenant-boundary-baseline/plan.md:141`)。**実際に増えているのは snapshot 側で、資産内 history の約 70 倍。**

### 1-2. 参照の構造的抽出

**64 桁 hex の全文検索では判定できない** — **7 資産には `frozen_projection_sha256` / `source_digest` / 識別値など、snapshot 参照でない 64 桁 hex が存在する**(敵対レビュー 1 周目 P1-7)。

#### v2 記録だけを抽出対象にする(敵対レビュー 3 周目 P1)

**現行の authority 履歴は v1 と v2 の混在である**(実測: `base-allowlist.json` の `history` は 2 件で `[0]` が v1・`[1]` が v2)。

**v1 の `change.before` / `after` は `{state, frozen_projection_sha256}` の 2 キーで、4 状態キーを持たない。** **全記録を同じ形で走査すると現行リポジトリ自身が落ちる。** **欠落を任意扱いにすると、v2 の参照フィールド欠落を見逃す。**

**したがって `record_schema_version == 2` の記録だけを抽出対象とし、v1 は「snapshot 参照を持たない」と明記する。**

#### 抽出表(**明示表。`ASPECT_NAMES` から「導出」しない** — 敵対レビュー 3 周目 P1)

**`ASPECT_NAMES` が与えるのは 4 個の名前だけで、どの値が配列か・どこに `snapshot_ref` があるかという型と経路の情報を持たない。** **「機械導出」は成立しない。**

**代わりに、4 キーすべてを分類する明示表を置き、次の 2 つを機械検査する**(敵対レビュー 4 周目 P1 — **キー集合の一致だけでは、`declaration` や `movement_policy` に誤った extractor を割り当てても現行データで空集合を返して通ってしまう**)。

1. **表のキー集合が `ASPECT_NAMES` と exact-set 一致する**(網羅性の拘束)
2. **表の分類値が下表と exact-map 一致する**(誤分類の拘束)

| `ASPECT_NAMES` のキー | 分類 | extractor |
| --- | --- | --- |
| `declaration` | **参照なし** | — |
| `movement_policy` | **参照なし** | — |
| `external_snapshots` | **参照あり** | 配列の各要素の `snapshot_ref` |
| `asset_snapshots` | **参照あり** | 配列の各要素の `snapshot_ref` |

**走査経路**

```
authority.history[*]  (record_schema_version == 2 のものだけ)
  .change.before.external_snapshots[*].snapshot_ref
  .change.before.asset_snapshots[*].snapshot_ref
  .change.after.external_snapshots[*].snapshot_ref
  .change.after.asset_snapshots[*].snapshot_ref
```

**各値は `SNAPSHOT_REF_PREFIX` で始まり、残りが 64 桁小文字 hex で、`history-snapshots/` の実ファイル名と一致すること**を同時に検査する。

**将来の record 直下参照**(`retired_history_ref` — 3 節の仕様)は **`ASPECT_NAMES` の外にある**ので、**record レベルの別の抽出表**として持つ。**「表へ 1 行足すだけ」が成立するのは、この record レベルの表のほうである。**

#### 合格条件

- **現行の混在履歴から一意参照 18 件を再現する正例**(**実測で確認済み** — v2 一意参照 18 / snapshot 実ファイル 47 / 参照されている 18 / 孤児 29 件・1,021,201 バイト / 総バイト 1,540,497)
- **v2 の参照フィールド欠落を拒否する負例**
- **「参照なし」の誤分類を捕まえる負例**: **`declaration` と `movement_policy` のそれぞれに、有効な `snapshot_ref` の形をした値を置いても抽出されない**
- **分類を反転させる変異試験**: **4 キーそれぞれについて分類値を反転させると red になる**(`参照なし` ↔ `extractor`)

### 1-3. 閾値(値と根拠)

| 量 | 現況(実測 2026-09-26) | 閾値 | 根拠 |
| --- | --- | --- | --- |
| **`history-snapshots/` の件数** | **47 件** | **500 件** | **1 受理あたりの新規 snapshot は `現役資産数(7) + 変更された一意 external digest 数` で、`external_files` は現況 3・ステップ 5 後は 4**。**11 件 / 受理**。**受理 40 回分 + 現況 = 487 件**に余裕を見て 500。**これは「現行 4 external files・現行サイズを前提にした約 40 回分の計画予算」であって上限の証明ではない**(`external_files` の件数にも各 snapshot のサイズにも上限が無いので、1 回の受理だけで到達しうる) |
| **同ディレクトリの総バイト数** | **1,540,497 バイト** | **33,554,432 バイト(32 MiB)** | **現況の 1 受理あたり増分は約 0.5 MB。40 受理で +20 MB**。**容量予算として 32 MiB を置き、超えたら閾値の見直しを強制する**(**同じく上限の証明ではない**) |
| **孤児の件数** | **29 件** | **比較元の孤児件数(増加ゼロ)** | **絶対値ではなく base-relative**。**既存 29 件は grandfather し、1 件でも増えたら red** |
| **孤児の総バイト数** | **1,021,201 バイト** | **比較元の孤児バイト数(増加ゼロ)** | 同上 |

**「上限」ではなく「予算見直しまでの想定 horizon」として書く**(敵対レビュー 2 周目 P2 — 「1 受理あたり最大 8 件」という上限の主張は撤回した)。**`external_files` に件数の上限は無いので、閾値は上限の証明ではなく予算である。** **超えたら red にし、そのとき人間が予算を見直す。** **「約 40 受理分を保証する」とは書かない**(敵対レビュー 3 周目 P2)。

### 1-4. 新規孤児ゼロの不変量

**「受理確定まで snapshot を書かない」は成立しない** — **参照を解決するには HEAD に実ファイルが無ければならない。**
**「前の試行の参照を引き継ぐ」も採らない** — **実遷移に無い snapshot を参照として残すと `before`/`after` の exactness が壊れる。**

**最終 HEAD に対する直接の不変量を置く。**

> **HEAD の `history-snapshots/` に存在して比較元に存在しない snapshot は、そのすべてが HEAD の構造的参照集合(1-2)に含まれる。**

#### 結線位置と入力(敵対レビュー 3 周目 P1)

**`load_contract` が持つのは HEAD 資産だけである。** **比較元資産と比較元 snapshot ディレクトリが同時に存在するのは、`_validate_repository_histories` が比較元を読み、`_materialize_git_snapshots` の一時ディレクトリを開いている区間だけ**である(両関数とも `check_tenant_boundary_bypass.py` に実在 — 実測)。

**したがって結線位置を次に固定する。**

> **`_validate_repository_histories` の中で、比較元 snapshot の一時ディレクトリを materialize したコンテキスト内で、既存の `frozen_history.validate_repository_histories` が成功した直後に `frozen_archive` の検査を呼ぶ。**

**「成功した直後」まで固定する理由**(敵対レビュー 4 周目 P2): **前に置くと archive のエラーが movement・履歴・識別値のエラーを隠す。** **後ろに置けば既存の失敗の意味が保たれる。** **終了コードは同じでも、最初に報告される不整合の意味が実装者の判断で変わってはならない。**

**両側の孤児を次のとおり定義する。**

```
base_orphans = 比較元の snapshot 集合 − 比較元 authority の v2 参照集合
head_orphans = HEAD  の snapshot 集合 − HEAD  authority の v2 参照集合
```

**判定は `head_orphans` の件数・バイト数が `base_orphans` のそれを超えないこと。** **両側で異なる履歴・snapshot 集合を渡す試験を置く**(片側だけを見て通る実装にしない)。

**PR 中間コミットで作った不要な snapshot は最終 HEAD から除去できる**(まだ比較元に無いので `_validate_snapshot_append_only` の削除禁止に掛からない)。**比較元にすでにある孤児 29 件だけが grandfather される。**

### 1-5. 既存 29 件を回収しない理由

**「孤児」は参照不能な blob であって、7.7-2 の履歴 record そのものではない。** **したがって `:605`(既存の記録を削除する変更を受理しない)を直接の根拠にはしない**(敵対レビュー 1 周目 P2-10)。

**回収しない理由は 2 つ。**

1. **`_validate_snapshot_append_only` が比較元に存在する snapshot の削除を一律に拒否しており、この検査の緩和は本 PR の射程を超える**
2. **回収には「どの blob が到達可能な record の backing か」の確定が要り、それは退去の仕様(3 節)が実装されてからでないと固定できない**

**受け取り先: TSK-452。** **既存集合は上記の実測値で固定し、増加ゼロを本 PR で保証する。**

---

## 2. D6 — 識別値の母集団の是正(**TSK-452 へ送り出した**)

**敵対レビュー 3 周目 P1 により、本 PR の射程から外した。**

### 問題(記録として残す)

**現行は `previous_baseline_identifiers` を `sorted(head_components)` で作る**(`frozen_history.py` の `check_repository`)。**比較元にあって HEAD に無い資産が母集団から落ちる。** **7.7-2 の 2 は「行為の直前に現に置かれていた識別値」を要求する**(`:588`)ので、**退去が実装された時点で条文違反になる。**

### 外した理由

**この是正は本 PR の本番経路では到達しない。**

- **比較元にだけ存在する資産は、7 資産のどれかなら `load_contract` の `_read_json` で落ちる**
- **それ以外でも `evaluate_repository_movement` の削除拒否で、識別値 map の構築より前に落ちる**

**したがって前版も新版も red であり、「前版 green → 新版 red」を示せない。** **到達不能な変更をコア領域の PR に入れない。**

### 引き渡す仕様(TSK-452 が実装する)

| map | 母集団 | 比較元にのみ存在する資産の値 |
| --- | --- | --- |
| `previous_baseline_identifiers` | **比較元 ∪ HEAD** | **比較元の `current_identifiers`**(実際に置かれていた値) |
| `new_baseline_identifiers` | **HEAD の現役資産だけ** | **含めない** |

**`new_baseline_identifiers` を HEAD の現役資産だけにする理由**(敵対レビュー 2 周目 P1): **退去したパスを `NO_BASELINE` として残すと、次回の受理では比較元・HEAD の双方からそのパスが消えるのに、`_validate_repository_identifier_record` が履歴末尾の `new_baseline_identifiers` と現役集合を exact-map 比較するため、変更のない次回 PR まで不合格になる。**

**本 PR は `frozen_history.py` の識別値まわりを 1 バイトも変えない。** **本 PR の本番挙動の差は D4 の締め分だけである。**

---

## 3. D1' — 退去の仕様(**実装しない。TSK-452 / TSK-443 へ引き渡す**)

**本節は 448 が決めた契約であって、448 の実装対象ではない。** **受け取り先はこれを出発点にできる。**

### 3-1. 記録形式

**現行 v2 の `change` は `{subject, aspect, before, after}` で、`before` / `after` はどちらも `ASPECT_NAMES`(`declaration` / `movement_policy` / `external_snapshots` / `asset_snapshots`)の 4 キー exact-set である。** **`frozen-baselines` の `change_series_retired`(`before: declaration` / `after: absent`)をそのまま移植できない。**

**`change` の形は変えず、退去の実体を record トップレベルへ置く。**

```
record.change.aspect    : 既存の aspect 集合に "asset_retired" を含む(実差分から機械導出)
record.retired_assets   : 配列。退去があるときだけ存在してよい(空配列は不合格)
record.retired_assets[i]: {path, before, retired_history_ref} の 3 キー exact-set
    path                : 比較元に存在し HEAD に存在しない資産パス
    before              : 退去直前の当該資産の baseline_control の実内容(比較元と deep-equal)
    retired_history_ref : "contracts/tenant_boundary/history-snapshots/<sha256>"
```

**`after` に相当するものは置かない** — **条文 `:577`「取り除いたことを表す宣言を残さない」**(tombstone を作らない)。

**名前空間の分離**(敵対レビュー 2 周目 P1): **`ASPECT_NAMES` は「`change.aspect` の許容値」と「`before`/`after` の必須 4 キー」を兼用している。** **実装するときは状態キー 4 種と record aspect 5 種を別定数へ分ける。** **`asset_retired` を `ASPECT_NAMES` へ足すと `_snapshot_state` が第 5 キーを要求してしまう。**

**前段検査の二重性**(同 P1): **v2 record の exact-set 検査は `_validate_v2_record` だけでなく、先に実行される `_validate_baseline_control`(`check_tenant_boundary_bypass.py`)にもある。** **両方を同時に更新しないと `retired_assets` が extra key として拒否される。**

**予約 marker**(同 P1): **`retired_assets.before` には現行 v1 履歴が入り、その中に `PENDING_ACCEPTANCE` や未承認 marker が実在する。** **`_reject_v2_reserved_markers` の除外リストへ `retired_assets` の 3 キーを足さないと、正当な退去が拒否される。**

### 3-2. 論理履歴

**退避しただけでは「写しを保存した」にすぎず、7.7-2 `:605` を満たしたと言えない**(敵対レビュー 1 周目 P0-1)。

**論理履歴** = **HEAD に現存する全資産の `history`** ∪ **authority の全 v2 record の `retired_assets[*].retired_history_ref` から復元した履歴**。**各記録は provenance として資産パスを保持する。**

**現役の非 authority 6 資産の v1 履歴を含める**(敵対レビュー 2 周目 P2 — 含めないと退去を境に母集団が変わる)。

**不変量(PR 受理モード・不変量モードの両方)**

1. **到達可能性**: 履歴中のすべての `retired_history_ref` が HEAD の `history-snapshots/` 配下で解決できる。**不変量モードの到達起点は HEAD authority の全 v2 record**
2. **不変性**: **ファイル名の sha256 と内容の sha256 が一致する**
3. **正規性**: **読み込んだ配列を規定 serializer で再直列化し、ファイルの実バイト列と一致する**(敵対レビュー 2 周目 P2 — 決定性の試験だけでは、空白やキー順だけ違う非正規 JSON を拒否できない)
4. **復元可能性**: 解決した内容が JSON 配列であり、各要素が履歴 record の形である

### 3-3. 正規化バイト列の規則

```
json.dumps(history_array, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
  .encode("utf-8")           # 末尾改行なし
sha256(bytes).hexdigest()     # → ファイル名(64 桁小文字 hex・拡張子なし)
```

**`_snapshot_state` は serializer ではない**(敵対レビュー 2 周目 P2 — 1 周目の「既存正規化を共用」という記述は参照先が不正確だった)。**serializer を独立した 1 関数として切り出し、writer と reader の両方が使う。**

### 3-4. PR B(TSK-443)への申し送り

**PR B は `contracts/tenant_boundary/runtime-authz-contract.json`(`FROZEN_BASELINE_ASSETS` の 6 番目)を削除する計画である**(TSK-424 の回答 2026-09-26・原典 `product-authz-surface/design.md` 9 節)。

**事実**: **この資産の中身はテナント境界の判定の入力に使われていない。** `load_contract` では `_read_json` → `_validate_baseline_control` を通るだけで、`_load_*` の対象ではない。中身を使うのは検査器の外(`backend/src/pitchlog/authz/runtime_contract.py` の `SOURCE_ASSET` と `scripts/check_authz_catalog.py` の `PROVISIONAL_RUNTIME_CONTRACT`)である。

**したがって、この資産に限れば削除は判定入力を外すことにならない。** **ただし「7 資産のどれかを消せる経路を作る」こと自体は残る。**

**448 からの申し送り**: **`product-authz-surface/design.md` 9 節の (a) 継承 / (b) 廃止 の 2 案に加え、「同じパスを保ったまま状態遷移させる第 3 の形」がある。** **ファイルを消さなければ 448 / 452 の退去機構を待つ必要がない。**

**ただし条文との距離に差がある。** **`superseded_by` のような「退役したこと」を表す宣言を残すと `:577`(取り除いたことを表す宣言を残さない)に当たる可能性がある。** **(a) 継承(凍結対象が製品資産へ移り、基準の宣言はそちらに残る)のほうが条文との距離が近い。** **採否は TSK-443 の計画レビューと人間の判断。**

### 3-5. 迂回できない点(実測)

**保護資産の母集団は `FROZEN_BASELINE_ASSETS` ではなく `contracts/tenant_boundary/` ディレクトリそのものである。**

- 比較元: `_git_tenant_boundary_assets` が `ls-tree -r <revision>` で**独立列挙**(直下の `.json` だけ)
- HEAD: `_head_tenant_boundary_assets` が**実ファイルを `iterdir` で列挙**
- **`FROZEN_BASELINE_ASSETS` の出現は定義と `load_contract` のループの 2 箇所だけ**で、movement の走査には使われていない

**したがって「先に定数から外してからファイルを消す」順序では通らない。** **ファイルがディレクトリから消えた時点で `比較元 - HEAD` に現れ、現行の無条件拒否に当たる。**

### 3-6. 「ファイルを残す」形の条文上の根拠

**条文 `:574-576` の逐語**

> **行為のあと、その基準に対応する凍結対象が 1 つも残らないときは、宣言から当該基準を取り除く。**
> **対応が残るときは、基準の宣言を残し、外した対応を、その対応を定めていた宣言または実装から取り除く**

**PR B で消えるのは「暫定的な値」であって、「凍結する対象」そのものではない。** ランタイム契約の値は製品資産へ移るだけで、凍結すべき対象は残る。

**この読みに立てば、`runtime-authz-contract.json` を残したまま `baseline_control.identity.frozen_projection` を製品資産へ向け直す形は、tombstone ではなく「対応が残るケース」の正規の扱いである。** **`:577` に当たらない。** **`frozen_target_mapping` 軸が動くので 7.7-2 の記録 1 件が要るが、これは現行の機構でそのまま書ける。**

**9 節 4 の (a) 継承との違いはファイルを消すかどうかだけ**で、**旧ファイルを残す版の (a)** なら削除が発生しない。

**採否は TSK-443 の計画レビューと人間の判断。** **448 からは「定数を外す迂回は効かない」という事実と、この読みがあることまでを材料として出す。**

### 3-7. fail-closed の一覧(退去を実装するとき)

| 失敗点 | 期待 |
| --- | --- |
| `retired_history_ref` が解決できない / 内容の sha256 がファイル名と不一致 / 非正規バイト列 / 復元結果が配列でない | 非 zero 終了 |
| 退去があるのに記録が無い / `retired_assets` が空 | 非 zero 終了 |
| `retired_assets` が実際の退去集合と exact-set 一致しない(過剰・不足) | 非 zero 終了 |
| `retired_assets[*].before` が比較元の `baseline_control` と deep-equal でない | 非 zero 終了 |
| `asset_retired` を申告したが実差分に退去が無い | 非 zero 終了 |
| 退去した資産の直前識別値が記録に無い | 非 zero 終了 |

---

## 4. D5 — 実装の隔離

**`scripts/frozen_history.py` は 7 資産すべての `external_files` に入っている**(実測)。**1 バイト触れば 7 資産の `baseline_value` 軸が動き、記録と識別値更新のない中間コミットは本番検査で不合格になる。**

**採る形**:

- **実装は新モジュール `scripts/frozen_archive.py` へ置く。** **どの資産の `external_files` にも入っていないので、射影は動かない**
- **依存方向を一方向に固定する**(敵対レビュー 2 周目 P1 — 双方向 import は循環初期化になる):

```
check_tenant_boundary_bypass.py  ──┬──> frozen_archive.py ──> frozen_history.py
                                   └──> frozen_history.py
```

  **`frozen_history.py` は `frozen_archive.py` を import しない。** **統括は `check_tenant_boundary_bypass.py` が行う。** **CLI の import 試験を合格条件に入れる**
- **`frozen_history.py` の既存関数を再実装しない**(NFR-018)

---

## 5. fail-closed の網羅(本 PR の実装分 — **番号つき exact-set・11 種**)

**1 行 = 1 種と数える**(スラッシュでまとめない — 敵対レビュー 4 周目 P2)。**ステップ 7 はこの 11 種を exact-set として扱う。**

| # | 失敗点 | 期待 |
| --- | --- | --- |
| **F1** | **snapshot の総件数が閾値を超える** | 非 zero 終了 |
| **F2** | **snapshot の総バイト数が閾値を超える** | 非 zero 終了 |
| **F3** | **`head_orphans` の件数が `base_orphans` より多い** | 非 zero 終了 |
| **F4** | **`head_orphans` の総バイト数が `base_orphans` より多い** | 非 zero 終了 |
| **F5** | **HEAD の新規 snapshot が構造的参照集合に含まれない**(新規孤児) | 非 zero 終了 |
| **F6** | **参照値が `SNAPSHOT_REF_PREFIX` で始まらない** | 非 zero 終了 |
| **F7** | **参照値の残りが 64 桁小文字 hex でない** | 非 zero 終了 |
| **F8** | **参照値が `history-snapshots/` の実ファイルと一致しない** | 非 zero 終了 |
| **F9** | **v2 記録の参照フィールドが欠落している** | 非 zero 終了 |
| **F10** | **抽出表のキー集合または分類値が期待表と一致しない** | 非 zero 終了 |
| **F11** | **既存 snapshot の変更・削除**(現行の検査) | 非 zero 終了 |

**いずれも「合格と区別できる結果」であること**(7.7-3)。

**v1 記録を v2 と同じ形で走査してしまう欠陥は、F10 ではなく合格条件の正例(現行の混在履歴が green)で捕まえる**(1-2)。

---

## 6. 前版との差分比較

### 6-1. 向きが変わった

**退去を射程から外したので、本 PR は検査を緩めない。** **締める方向しかない。**

**合格条件**:

- **`前版 red → 新版 green` が 0 件**(**この 11 ケース corpus の内側で緩めていないこと**)
- **`前版 green → 新版 red` が `{4, 5, 6, 7, 11}` と exact-set 一致**(**締めたところが意図どおりであることの証明**)

### 6-2. 比較元の固定と実行経路

**比較元 SHA は `b4ae7394a6ca038c8ea90ad9ddea40e00165ba7b`(本ブランチの分岐点)で literal 固定する。** **その SHA を detached で取り出した清潔な作業木で旧検査器を走らせる。**

**実行経路を特定する**(敵対レビュー 2 周目 P1 — 「base/head の組」だけでは経路が決まらない):

- **同一の合成リポジトリについて、二親 merge と一致する GitHub event(`base.ref` / `base.sha` / `head.sha` / `repository.full_name` / `pull_request.number`)を作る**
- **各版の CLI(`check_tenant_boundary_bypass.py`)を PR 受理モードで呼ぶ runner を fixture に固定する**
- **不変量モードを注入して代用しない**(PR 受理固有の実遷移照合を通らないため)

### 6-3. 比較ケース manifest(**exact-set・11 件**)

**`tests/fixtures/frozen-archive-cases/` に固定する。**

| # | ケース | 前版 | 新版 |
| --- | --- | --- | --- |
| 1 | **変更なしの受理**(現行の正例をそのまま再現) | green | **green** |
| 2 | **通常の movement + 正しい記録**(既存の正例) | green | **green** |
| 3 | **識別値の据え置き**(既存の負例) | red | **red** |
| 4 | **新規孤児あり**(参照されない新規 snapshot を残す) | **green** | **red** |
| 5 | **snapshot の件数が閾値超過** | **green** | **red** |
| 6 | **snapshot の総バイトが閾値超過** | **green** | **red** |
| 7 | **参照値が非正規**(prefix 違い / 桁数違い / 実ファイル不在)。**比較元と HEAD の双方に同一の非正規 v2 prefix を置く**(敵対レビュー 3 周目 P2 — 追記 record を非正規にすると前版も既存の `_external_snapshots` で落ちるため前版 green にならない) | **green** | **red** |
| 8 | **追記 record の参照を非正規にする** | red | **red** |
| 9 | **比較元にすでにある孤児 29 件相当**(grandfather) | green | **green** |
| 10 | **v1 と v2 が混在する現行の履歴**(一意参照 18 件を再現) | green | **green** |
| 11 | **v2 記録の参照フィールドが欠落**。**比較元と HEAD の双方に同一の、`snapshot_ref` が欠落した既存 v2 prefix を置く**(HEAD だけを欠落させると prefix deep-equal で、追記 record に置くと `_validate_v2_record` で、いずれも前版 red になる — 敵対レビュー 4 周目 P2) | **green** | **red** |

**判定は両版の終了コードの組を機械が集計して行う**(人の目で見比べない)。

### 6-4. 主張の限界(敵対レビュー 4 周目 P2)

**11 ケースから言えるのは「この固定 corpus の内側で `red → green` が 0 件」までである。** **全入力に対して「検査を緩めていない」ことの証明にはならない。**

**全体の非緩和は、別の条件で支える。**

| # | 条件 | 検証 |
| --- | --- | --- |
| **S1** | **`scripts/frozen_history.py` の差分が 0 行** | **【機】差分検査** |
| **S2** | **`scripts/check_tenant_boundary_bypass.py` の差分が「`frozen_archive` の import 1 件」と「`_validate_repository_histories` 内の指定位置への呼び出しの追加」だけ**である。**既存の文を 1 つも変更・削除していない**(**追加のみ**) | **【機】差分の構造検査** |
| **S3** | **7 資産の JSON への変更が、下表の「許可される変更」だけ**である | **【機】差分の構造検査** |
| **S5** | **3 つの生成モジュールへの変更が、資産と一致する版・digest の更新だけ**である | **【機】差分の構造検査** |
| **S6** | **`tests/test_check_tenant_boundary_bypass.py` への変更が、下記 3 項目だけ**である | **【機】差分の構造検査** |
| **S7** | **`.claude/core-areas.json` への変更が `tenant-isolation.paths` への新パス登録だけ**で、**`tests/test_core_guard.py` の exact-set がそれと同期している** | **【機】差分の構造検査** |
| **S4** | **archive 検査は既存の判定の後に走り、既存の合否を変えない** | **【逐】人間の逐行確認** |

#### S3 が許可する変更(**exact-set** — 敵対レビュー 6 周目 P1)

**`external_files` へ 1 行足すと、機械的に再計算しなければならない派生値がある。** **実測(2026-09-26)**:

| 派生値 | 対象 | 件数 |
| --- | --- | --- |
| **`source_digest`** | `cache-invalidation-contract.json` / `repository-contract.json` / `runtime-authz-contract.json` / `tenant-context-allowlist.json` | **4 資産** |
| **`inventory.sha256`** | `base-allowlist.json`(`db-api-inventory.json` を封印している) | **1 件** |

**したがって S3 が許可する変更は次の exact-set とする。**

1. **各資産の `baseline_control.identity.frozen_projection.external_files` への `scripts/frozen_archive.py` 1 件の追加**(7 資産)
2. **各資産の「`identity.field` が指すトップレベル revision field」と `current_identifiers` の同期更新**(7 資産)

   **7 資産はすべて `scheme: integer_revision_field`** で、**`_validate_baseline_control` がトップレベルの revision field と `current_identifiers` の一致を要求する**(敵対レビュー 7 周目 P1 — **実測**)。**`current_identifiers` だけを許可すると、据え置いても更新しても red になる。**

   | 資産 | `identity.field` | 現在値 |
   | --- | --- | ---: |
   | `base-allowlist.json` | `contract_revision` | 15 |
   | `cache-invalidation-contract.json` | `contract_revision` | 3 |
   | `db-api-inventory.json` | `inventory_revision` | 5 |
   | `negative-fixtures.json` | `fixture_set_revision` | 7 |
   | `repository-contract.json` | `contract_revision` | 4 |
   | `runtime-authz-contract.json` | `runtime_contract_revision` | 3 |
   | `tenant-context-allowlist.json` | `contract_revision` | 6 |

   **両者の一致を機械検査する。** **確定した revision 値に対して、項目 3・4 と S5 の派生値を再計算する。**
3. **上表 4 資産の `source_digest` の機械再計算**
4. **`base-allowlist.json` の `inventory.sha256` の機械再計算**
5. **`base-allowlist.json` の `baseline_control.history` への受理記録 1 件の追記**

**これ以外の差分が 1 行でもあれば red。** **3〜4 は「機械再計算の結果と一致すること」まで検査する**(手で書いた値を通さない)。

#### S5 が対象とする生成モジュール(**exact-set・3 件** — 実測)

```
backend/src/pitchlog/authz/runtime_contract.py
backend/src/pitchlog/repositories/repository_contract.py
backend/src/pitchlog/repositories/tenant_context_contract.py
```

**許可されるのは、対応する資産と一致する版・digest の更新だけ。** **本体の論理に差分があれば red。**

#### S6 が対象とする既存テスト(敵対レビュー 7 周目 P1)

**`tests/test_check_tenant_boundary_bypass.py` は `external_files` を 3 ファイルの exact-list として固定しており、合成リポジトリにもその 3 つしかコピーしない。** **7 資産へ `scripts/frozen_archive.py` を足すと、exact-list の assertion が落ち、合成リポジトリでは新しい外部凍結対象を解決できない。**

**変更してよいのは次だけ。**

1. **`external_files` の exact-list を 4 ファイルへ更新**(`test_all_assets_freeze_mode_wiring_and_declare_single_authority` / `test_default_base_ref_belongs_only_to_frozen_checker_procedure` ほか)
2. **`_initialize_test_repository` が `scripts/frozen_archive.py` もコピーする**
3. **`test_every_frozen_baseline_asset_has_a_valid_chained_history` の authority 履歴期待件数を 2 → 3 へ更新**(本 PR が受理記録 1 件を足すため — 敵対レビュー 8 周目 P1)

**既存の検査意図を変える変更があれば red。**

#### S7 — コア領域への登録(設計書 6.3 — 敵対レビュー 8 周目 P1)

**`scripts/frozen_history.py` は `.claude/core-areas.json` の `tenant-isolation.paths` に登録済みである**(実測。`scripts/check_tenant_boundary_bypass.py` / `contracts/tenant_boundary/*` / `tests/fixtures/tenant_boundary/*` / `tests/test_check_tenant_boundary_bypass.py` / `tests/test_frozen_history.py` も同様)。

**本 PR が新しい強制点を作る以上、次を `tenant-isolation.paths` へ登録する。**

```
scripts/frozen_archive.py
tests/fixtures/frozen-archive-cases/*
tests/test_frozen_archive.py        (独立したテストモジュールを置く場合)
```

**登録すると `tests/test_core_guard.py` の `TENANT_BOUNDARY_AREA_PATH_CASES` と `test_actual_core_area_paths_are_exact_expected_set` の exact-set も同期更新が必要**になる。**許可するのはこの同期だけで、ほかの領域の paths を触れば red。**

**S2 の書き方の注意**(敵対レビュー 5 周目 P1): **`frozen_archive` の呼び出しは `_validate_repository_histories` の本体へ足すのだから、「既存関数の本体に差分が無い」とは書けない。** **拘束すべきは「既存の文を変更・削除していない(追加のみ)」である。**

**PR 本文には「11 ケース corpus 内の差分比較」と書き、「全入力で緩めていない」とは書かない。**

---

## 7. 主張しない範囲(番号付き exact-set)

**[plan.md](plan.md) の最終ステップと DoD は本節を参照し、この 7 項目をそのまま PR 本文へ転記する。**

1. **「7.7 へ完全に適合した」とは主張しない。** **7E(TSK-449)・センチネル記録の訂正(TSK-450)・次回以降の評価器選択(TSK-451)は未解決のまま残る**
2. **凍結資産の退去(削除)を通せるようにしていない。** **7 資産はいずれも引き続き削除できず、`load_contract` が fail-closed で落とす。** **退去の仕様は本書 3 節に契約として書き、TSK-452 へ送る**(理由は 0-2)
3. **PR B(TSK-443)のブロックを解いていない。** **PR B が `runtime-authz-contract.json` の削除を選ぶ限り、TSK-452 を待つ。** **削除しない形を採れば待たない**(本書 3-4)
4. **識別値の母集団を是正していない。** **`previous_baseline_identifiers` が比較元にのみ存在する資産を落とす defect は残る。** **本 PR の本番経路では到達しないため TSK-452 へ送った**(本書 2 節)
5. **既存 v1 記録 7 件に ID を与えない。** **配列位置でしか指せない状態は TSK-450 が解く**
6. **既存の孤児 snapshot 29 件を回収しない。** **本 PR は検出・grandfather・増加ゼロの保証までで、回収は TSK-452 へ送る**
7. **「CI が通ったこと」を不変性の保証としない。** **10.2 の強制が未達である**(必須チェックの発行元が未拘束・`TSK-433` で追跡中)。7.7 自身が `:645-650` で同じ非保証を明示している
