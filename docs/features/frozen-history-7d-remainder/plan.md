---
feature: frozen-history-7d-remainder
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-26・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e593b75e687812dbce1f5aff1da56f5
branch: feature/frozen-history-7d-remainder
created: 2026-09-26
計画レビュー周回: 8        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: 7.7-4 の残り — 履歴アーカイブの規律(TSK-448)

**旧題「削除記録・履歴アーカイブ・安定した履歴 ID」は 2〜3 周目の射程見直しで失効した。**

## 1. 背景・目的

**Notion**: [TSK-448](https://app.notion.com/p/3e593b75e687812dbce1f5aff1da56f5)(出所: **TSK-431 の送り出し 4 件の 1 つ**。`docs/worklog/2026-09-24-tenant-boundary-baseline.md:118`)

**TSK-431 は 7D について「最小限」だけを実装した。** 比較元側 ∪ HEAD 側の走査を入れ、**比較元にあって HEAD に無い資産を検出したら無条件で不合格**にしたが、**記録の形は決めなかった**(`tenant-boundary-baseline/design.md:151` 逐語)。

**その結果、正当な削除を通す経路が存在しない。** 条文 `:574-579` は「凍結対象が 1 つも残らなくなったら宣言から取り除く」遷移を**正当なものとして定めている**のに、実装はそれを通せない。

**要件 FR/NFR との関係**: **要件書に上位根拠は無い**([research.md](research.md) 5 — 独立検証済み)。**根拠に要件書 4.0-2(物理削除しない)を引いてはならない** — 設計書 `10.1:900` が「要件書 4.0-2 の論理削除は**アプリ利用者データ**の規定であり、**本項の根拠ではない**」と明示している。**NFR-021 の append-only 検査も対象外**(母集団は `docs/ops/nfr021-acceptance` 配下のみ)。**法源は設計書 7.7 と 10.1/10.2 だけ。要件書の改訂は不要。**

### 本タスクが開くもの(**2 周目で見直した**)

**当初は `docs/features/product-authz-surface/plan.md:43`(★8)の「**PR B**(ランタイム契約の切り替え)は **7D の後**」を根拠に、本タスクが PR B を開くとしていた。**

**TSK-424 の回答(2026-09-26)で、PR B が待っているのは `contracts/tenant_boundary/runtime-authz-contract.json`(7 資産の 6 番目)の削除であることが確定した**(原典 `product-authz-surface/design.md` 9 節)。

**そして敵対レビュー 2 周目の P0 により、7 資産の削除は本タスクの射程では安全に閉じられないと判定した**([design.md](design.md) 0-2)。

**したがって本タスクは PR B を開かない。** **本タスクが閉じるのは「TSK-431 が作った実害(孤児 snapshot 29 件・66.3 %)の再発防止」と「参照の構造的抽出による孤児の可視化」であり、PR B の解錠は TSK-452 または TSK-443 の設計判断に移る**([design.md](design.md) 3-4)。

**この見直しを PR 本文と worklog に明記する。**

## 2. スコープ

**敵対レビュー 2 周(1 周目 新種 11 件・P0 2 件 / 2 周目 新種 3 件 + 処置不十分 6 件・P0 1 件)を反映して射程を絞った。** **人間の判断 2026-09-26 により、退去(削除)機構を外す。**

### やること

| | 中身 |
| --- | --- |
| **D4** | **履歴アーカイブの規律**(**本 PR の主題**)— **参照を構造的に抽出**し、**閾値を確定して機械化**し、**新規孤児ゼロを不変量にする**([design.md](design.md) 1 節) |
| **D5** | **実装の隔離** — 新モジュール `scripts/frozen_archive.py` へ書き、最終ステップで結線する(同 4 節) |
| **D1'** | **退去の記録形式と論理履歴の契約を「仕様」として確定し、受け取り先へ引き渡す**(**実装しない** — 同 3 節) |

### やらないこと

| 範囲 | 理由 / 受け取り先 |
| --- | --- |
| **凍結資産の退去(削除)を通す機構** | **`load_contract` が 7 資産すべてを無条件に読む必須入力で、削除すると退去の検査より前に落ちる。** **条件付きにすると検査入力を退去記録だけで外せる経路ができる**(空洞化)。**実行不能か空洞化の二択**([design.md](design.md) 0-2)。**人間の判断 2026-09-26。受け取り先: TSK-452(新設を提案)** |
| **D6 識別値の母集団の是正** | **本 PR の本番経路では到達しない**(比較元にのみ存在する資産は `load_contract` か削除拒否で、識別値 map の構築より前に落ちる)。**到達不能な変更をコア領域の PR に入れない**(3 周目 P1)。**受け取り先: TSK-452**([design.md](design.md) 2 節) |
| **PR B(TSK-443)のブロック解除** | **PR B が `runtime-authz-contract.json` の削除を選ぶ限り TSK-452 を待つ。** **削除しない形を採れば待たない**([design.md](design.md) 3-4)。**判断は TSK-443 の計画レビューと人間** |
| **record の論理キーの新設(旧 D3)** | **取り下げ。** **前提が誤りだった** — `parse_history` の prefix deep-equal が**既に同数置換を拒否**し、`_validate_repository_identifier_record` が**既に `acceptance_id` の重複を拒否**している(4 節) |
| **既存 v1 記録 7 件への ID の遡及・既存記録の訂正** | **TSK-450**([research.md](research.md) 7-3) |
| **既存の孤児 snapshot 29 件の削除** | **検出・grandfather・増加ゼロの保証までとし、回収は TSK-452 へ送る**([design.md](design.md) 1-5) |
| **7E**(バイト正規化) | **TSK-449** |
| **要件書の改訂** | 上位根拠が無い(1 節) |
| **`frozen-baselines` 系列への移設** | **移設対象外と判定済み**([research.md](research.md) 3-4) |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/development/dev-harness-design-2026-08-07.md`(7.7) | **反映なし** — 条文は変えない。本タスクは条文への適合であって改訂ではない | — |
| `docs/design/data-model.md` | **反映なし** | — |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし**(上位根拠が無い) | — |
| `docs/development/harness-evaluation.md` | **`## 候補` へ追記の判断は /pr のクローズ処理で行う**(本計画では確定しない) | PR レビュー |

**正本の新設・版繰り上げはない。**

**正本体系外だが同一 PR で更新するもの**

| ファイル | 変更内容 |
| --- | --- |
| `scripts/frozen_archive.py`(**新設**) | 参照の構造的抽出・量の閾値・新規孤児ゼロの不変量 |
| `scripts/check_tenant_boundary_bypass.py` | **ステップ 5 でのみ変更**(結線・`external_files` への追加) |
| `scripts/frozen_history.py` | **変更しない**(D6 を送り出したため) |
| `contracts/tenant_boundary/base-allowlist.json` | **本 PR の受理記録 1 件** + **7 資産の識別値** + **`inventory.sha256` の機械再計算**(検査器を触るため射影が動く) |
| `contracts/tenant_boundary/*.json`(7 資産) | **`external_files` へ `scripts/frozen_archive.py` 1 件の追加** + **トップレベル revision field と `current_identifiers` の同期更新** + **4 資産の `source_digest` の機械再計算**([design.md](design.md) 6-4 の S3) |
| `tests/test_check_tenant_boundary_bypass.py` | **`external_files` の exact-list を 4 ファイルへ更新** + **`_initialize_test_repository` が `scripts/frozen_archive.py` もコピーする** + **`test_every_frozen_baseline_asset_has_a_valid_chained_history` の authority 履歴期待件数を 2 → 3 へ**([design.md](design.md) 6-4 の S6)。**既存の検査意図は変えない** |
| `.claude/core-areas.json` | **`tenant-isolation.paths` へ `scripts/frozen_archive.py` / `tests/fixtures/frozen-archive-cases/*`(+ 独立テストモジュールを置く場合はそのパス)を登録**(設計書 6.3 — [design.md](design.md) 6-4 の S7) |
| `tests/test_core_guard.py` | **`TENANT_BOUNDARY_AREA_PATH_CASES` と exact-set を core-areas.json と同期**(同 S7) |
| `backend/src/pitchlog/authz/runtime_contract.py` / `repositories/repository_contract.py` / `repositories/tenant_context_contract.py`(**3 生成モジュール**) | **資産と一致する版・digest の更新だけ**([design.md](design.md) 6-4 の S5)。**本体の論理は変えない** |
| `contracts/tenant_boundary/history-snapshots/` | **追記のみ**(既存 47 件は 1 つも変更・削除しない) |
| `tests/fixtures/frozen-archive-cases/`(**新設**) | 前版比較の 11 ケース manifest と PR 受理モードの runner |

## 4. 実装方針

**調査の正**: [research.md](research.md) — **ただし冒頭の失効注記で「生存」と判定した節に限る**(0 節・6 節・7-1 は失効)。**設計判断の正**: [design.md](design.md)。**本節は結論だけを引き、内容を複製しない**(設計書 7.1-1)。

**重さ分類の根拠**: **コア領域(テナント分離)**。`scripts/check_tenant_boundary_bypass.py` / `scripts/frozen_history.py` / `contracts/tenant_boundary/*` はいずれも `.claude/core-areas.json` の `tenant-isolation` の paths。**sol xhigh・敵対レビュー + 人間の逐行確認必須。**

### 旧 D3 を取り下げた理由(1 周目 P1-4 — 原典で確認済み)

| 旧 D3 の前提 | 実際 |
| --- | --- |
| 「現行は位置だけなので同数置換を検出できない」 | **誤り。** `parse_history` は `head_records[:len(base_records)]` と `base_records` の **deep-equal** を要求する。**件数が同じで中身を差し替えれば prefix deep-equal が落ちる** |
| 「`(acceptance_id, 資産パス)` を論理キーにする」 | **成立しない。** tenant_boundary は **1 受理 1 記録**で、**1 記録が 7 資産すべての識別値を持つ**。**1 記録に複数キーが生じる** |
| 「`acceptance_id` の一意性が未検査」 | **誤り。** `_validate_repository_identifier_record` が **v2 記録全体で `acceptance_id` の重複を拒否している** |

**新しい機構は足さない。** **代わりに次の 2 つを明記する。**

- **v1 記録は位置 prefix の deep-equal だけで保護される**(ID を持たない)
- **TSK-450 は別の ID 名前空間を定義しない** — **既存 v1 を指す手段を足すときも `acceptance_id` の体系に寄せる**

**確定した裁定**([design.md](design.md)):

| # | 裁定 |
| --- | --- |
| **D4** | **`record_schema_version == 2` の記録だけを対象に、schema 上の 4 フィールドから構造的に抽出**する(64 桁 hex の全文検索は使わない。**v1 は参照を持たない**)。**抽出表は明示表とし、キー集合の `ASPECT_NAMES` との exact-set 一致に加え、分類値も期待表と exact-map 一致することを機械検査する**(「導出」しない — 3 周目 P1・4 周目 P1)。**結線位置は `_validate_repository_histories` の中で比較元 snapshot を materialize したコンテキストの、既存 `frozen_history.validate_repository_histories` が成功した直後**。**孤児は両側で算出して比較する**。**閾値は件数 500 / 32 MiB(計画予算 — 上限の証明ではない)/ 孤児は比較元値からの増加ゼロ**。**HEAD の新規 snapshot はすべて参照集合に含まれる**ことを不変量にする |
| **D5** | **実装は新モジュール `scripts/frozen_archive.py`**。**依存方向は `check_tenant_boundary_bypass.py → frozen_archive.py → frozen_history.py` の一方向**(2 周目 P1 — 双方向 import は循環初期化になる) |
| **D1'** | **退去の記録形式・論理履歴・正規化規則・fail-closed の一覧を仕様として確定**し、**TSK-452 / TSK-443 へ引き渡す**。**実装しない** |

**踏まないようにすること**

1. **「検査を弱めた」と判定される** → **本 PR は締める方向しかない**。**11 ケース corpus の内側で `前版 red → 新版 green` が 0 件**であることを固定 SHA の前版で示す。**全入力への非緩和は主張せず、構造検査 S1〜S3・S5〜S7 と逐行確認 S4 で支える**([design.md](design.md) 6-4)
2. **`contracts/tenant_boundary/` 直下に `.json` を置くと、それ自体が保護資産として列挙される** → **置かない**
3. **「関数は正しいが本番経路がその結果を使っていない」型** — TSK-431 の実装レビューで **3 周連続**で出た。**機構を壊す変異で本番経路テストが落ちるか**で判定する
4. **`frozen_history.py` を触ると 7 資産すべての射影が動く**(実測)→ **D5 の隔離で、結線までは触らない**
5. **到達不能な変更をコア領域の PR に入れない** → **D6 は TSK-452 へ送った**([design.md](design.md) 2 節)。**本 PR は `frozen_history.py` を 1 バイトも変えない**

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**前版比較の比較元 SHA は `b4ae7394a6ca038c8ea90ad9ddea40e00165ba7b`(本ブランチの分岐点)で固定する。**

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **draft PR を作る**(`acceptance_id` の PR 番号を先に確定させる)+ **比較ケース manifest 11 件と PR 受理モードの runner を `tests/fixtures/frozen-archive-cases/` へ固定する**([design.md](design.md) 6 節)+ **固定 SHA の前版を detached な作業木へ取り出し、11 ケースを当てて終了コードを記録する** + **孤児 snapshot の現況を構造的抽出で実測して記録する** + **変更対象の網羅リストを機械的に得る**(`scripts/frozen_archive.py` を 7 資産の `external_files` へ仮に足した状態でルートと `backend/` の全ゲートを回し、**落ちた検査をすべて記録して exact-set にする**。**計画の予測ではなく実測で確定する**) | **draft PR が存在し PR 番号が確定**。**runner が二親 merge と一致する event を作り、両版の CLI を PR 受理モードで呼ぶ**(不変量モードで代用していない)。**11 ケースの前版終了コードが design.md 6-3 の「前版」列と完全一致**。**孤児 29 件・1,021,201 バイトが構造的抽出で再現される**。**変更対象の網羅リストが実測で得られ、[design.md](design.md) 6-4 の S1〜S7 が列挙する対象と exact-set 一致する**(食い違えば S1〜S7 を先に直す — **この確認を経ずにステップ 2 へ進まない**) |
| 2 | **`scripts/frozen_archive.py`(新設・未結線)— 参照の構造的抽出**。**`record_schema_version == 2` の記録だけを対象**に 4 フィールドを走査 / `SNAPSHOT_REF_PREFIX` と 64 桁 hex と実ファイル名の一致 / **抽出表は明示表**(4 キーを「参照なし / extractor」に分類)で、**キー集合が `ASPECT_NAMES` と exact-set 一致し、分類値も期待表と exact-map 一致** | **`frozen_history.py` と `check_tenant_boundary_bypass.py` を 1 バイトも触らない**(差分で確認)。**`frozen_projection_sha256` / `source_digest` / 識別値の 64 桁 hex だけを持つ fixture で孤児判定に混入しない**。**`ASPECT_NAMES` に第 5 キーを足すと抽出表の未更新が red になる**(exact-set 一致の検査)。**現行の混在履歴(v1 + v2)から一意参照 18 件を再現する正例**(**実測確認済み**)と、**v2 の参照フィールド欠落を拒否する負例**。**v1 記録を v2 と同じ形で走査すると落ちる**ことを示す。**`declaration` / `movement_policy` に有効な `snapshot_ref` 形の値を置いても抽出されない負例**と、**4 キーの分類値を反転させると red になる変異試験**。**`frozen_history.py` の部品を import して使い、再実装しない**(NFR-018)。**import は一方向**(`frozen_archive → frozen_history`)で、**逆向きが存在しない**ことを試験する |
| 3 | 同(未結線)— **量の閾値**。総件数 / 総バイト / 孤児の件数とバイト。**孤児は両側で算出**(`base_orphans` / `head_orphans` — design.md 1-4)。**design.md 1-3 の確定値を使う** | 合成 fixture で**各量が閾値を超えると red**。**孤児は絶対値でなく比較元との差で判定**する(比較元に 29 件ある入力で red にならない)。**両側で異なる履歴・snapshot 集合を渡す試験**を置く(片側だけを見て通る実装にしない)。**現況(47 件・1,540,497 バイト・孤児 29 件)が閾値内** |
| 4 | 同(未結線)— **新規孤児ゼロの不変量**。「**HEAD にあって比較元に無い snapshot は、すべて HEAD の構造的参照集合に含まれる**」 | **同一受理内で記録を 2 回作り直し、前の試行の snapshot を残したまま HEAD を作ると red**。**前の試行の snapshot を除去すると green**。**比較元にすでにある孤児では red にならない**(grandfather) |
| 5 | **結線 — 1 コミット。** **`_validate_repository_histories` の中で、比較元 snapshot を materialize したコンテキストの、既存 `frozen_history.validate_repository_histories` が成功した直後に `frozen_archive` を呼ぶ**(design.md 1-4)+ **`scripts/frozen_archive.py` を 7 資産の `external_files` へ追加** + **authority へ本 PR の受理記録 1 件と 7 資産の識別値の更新** + **7 資産のトップレベル revision field と `current_identifiers` の同期更新** + **派生値の機械再計算**(4 資産の `source_digest` / `inventory.sha256` / 3 生成モジュールの版・digest)+ **既存テストの exact-list と authority 履歴件数の更新**(S6)+ **core-areas.json への登録と test_core_guard.py の同期**(S7)。**`frozen_history.py` は 1 バイトも変えない** | **実リポジトリに対して** `uv run python scripts/check_tenant_boundary_bypass.py` が green。**CLI の import が成功する**(循環 import が無い)。**本番 `check_repository` 経路の変異テスト**で: **新規孤児を残すと red** / **閾値超過で red** / **参照が非正規だと red** / **識別値を据え置くと red**。**比較元孤児と HEAD 孤児が別々に算出されている**ことを、両側で異なる集合を渡す試験で示す |
| 6 | **前版との差分比較を実行する**([design.md](design.md) 6 節)— 前版と HEAD へ**同一の 11 ケース**を当て、終了コードの組を集計する | **`前版 red → 新版 green` が 0 件**。**`前版 green → 新版 red` が `{4, 5, 6, 7, 11}` と exact-set 一致**。**集計は機械が行い、結果を worklog へ転記する** |
| 7 | **fail-closed の網羅**([design.md](design.md) 5 節の F1〜F11) | 各失敗が**非 zero 終了かつ合格と区別できる**。**すべて本番 `check_repository` 経路を通る変異テストで示す**(関数直呼びのテストだけで主張しない) |
| 8 | **確認対象コミットの SHA を固定した人間の逐行確認を worklog へ記録**(履歴は追加しない) | worklog に**確認対象コミットの SHA** と `対象= / 範囲= / 方法=`。**確認項目に「D4・D5 の実装対応」「前版差分比較の集計結果」「孤児の現況」「退去機構を入れていないこと」「D6 を送り出したこと」「D1' の仕様が実装でなく文書であること」「`frozen_history.py` が無変更であること」が列挙されている**。**確認後の差分は worklog 等の証跡ファイルに限る** |
| 9 | 全ゲート + PR 本文へ **[design.md](design.md) 7 節の 7 項目をそのまま転記** + **送り出しの対応表**(TSK-449 / 450 / 451 / **452 の新設提案**)+ **1 節「本タスクが開くもの」の見直しを明記** | `uv run pytest tests/` / `uv run ruff check .` / `uv run ty check` green。**backend のゲートも回す**。**PR 本文の「主張しない範囲」が design.md 7 節と同じ 7 項目・同じ順序**。**TSK-452 の起票提案と、PR B のブロックが解けていないことが PR 本文にある** |

## 5. DoD(受け入れ基準)

**各項目に検証手段を明記する** — **【機】= 機械検査 / 【逐】= 人間の逐行確認**(2 周目 P2)。

- [ ] 【機】**D4**: **参照が schema 上の 4 フィールドから構造的に抽出されている**。**`frozen_projection_sha256` / `source_digest` / 識別値の 64 桁 hex を孤児判定に混入させない**
- [ ] 【機】**D4**: **抽出対象が `record_schema_version == 2` の記録だけ**で、**v1 記録を v2 と同じ形で走査すると落ちる**
- [ ] 【機】**D4**: **抽出表が明示表**で、**キー集合が `ASPECT_NAMES` と exact-set 一致**し、**分類値も期待表と exact-map 一致**する。**第 5 キーを足すと未更新が red**・**分類値を反転させると red**
- [ ] 【機】**D4**: **「参照なし」と分類した `declaration` / `movement_policy` に有効な `snapshot_ref` 形の値を置いても抽出されない**
- [ ] 【機】**D4**: **現行の混在履歴から一意参照 18 件を再現する**。**v2 の参照フィールド欠落を拒否する**
- [ ] 【機】**D4**: **孤児を両側で算出する**(`base_orphans` / `head_orphans`)。**両側で異なる履歴・snapshot 集合を渡す試験がある**
- [ ] 【機】**D4**: **総件数 500 / 総バイト 32 MiB / 孤児は比較元値からの増加ゼロ** の閾値が実装され、超えると red
- [ ] 【逐】**D4**: **閾値の値とその根拠が design.md 1-3 に書かれており、「上限の証明」でなく「予算見直しまでの想定 horizon」として書かれている**。**「約 40 受理分を保証する」とは書いていない**
- [ ] 【機】**D4**: **HEAD にあって比較元に無い snapshot がすべて構造的参照集合に含まれる**(新規孤児ゼロ)
- [ ] 【機】**D4**: **既存の孤児 29 件を削除していない**。**比較元に 29 件ある入力で red にならない**(grandfather)
- [ ] 【逐】**D6 を送り出した**: **`frozen_history.py` を 1 バイトも変更していない**。**送り出した理由(本番経路で到達不能)と受け取り先(TSK-452)が design.md 2 節と PR 本文にある**
- [ ] 【機】**D5**: **ステップ 2〜4 のコミットが `frozen_history.py` と `check_tenant_boundary_bypass.py` を 1 バイトも変更していない**
- [ ] 【機】**D5**: **import が一方向で、CLI の import が成功する**(循環 import が無い)
- [ ] 【逐】**D5**: **`frozen_history.py` の既存関数をコピー実装していない**(NFR-018)
- [ ] 【逐】**D1'**: **退去の仕様(記録形式・論理履歴・正規化規則・fail-closed)が design.md 3 節に書かれている**。**実装は 1 行も入っていない**
- [ ] 【逐】**D1'**: **TSK-452 の新設提案と、PR B(TSK-443)への申し送り(第 3 の形と条文との距離)が PR 本文にある**
- [ ] 【機】**前版比較**: **11 ケース corpus の内側で `前版 red → 新版 green` が 0 件**。**`前版 green → 新版 red` が `{4, 5, 6, 7, 11}` と exact-set 一致**。**比較元 SHA が `b4ae7394` で固定され、両版が PR 受理モードで呼ばれている**
- [ ] 【機】**fail-closed**: [design.md](design.md) 5 節の F1〜F11 すべてが**非 zero 終了かつ合格と区別できる**(**1 行 = 1 種で数える**)
- [ ] 【機】**非緩和 S1**: **`scripts/frozen_history.py` の差分が 0 行**
- [ ] 【機】**非緩和 S2**: **`scripts/check_tenant_boundary_bypass.py` の差分が「`frozen_archive` の import 1 件」と「`_validate_repository_histories` 内の指定位置への呼び出しの追加」だけ**で、**既存の文を 1 つも変更・削除していない**(**追加のみ**)
- [ ] 【機】**非緩和 S3**: **7 資産の JSON への変更が [design.md](design.md) 6-4 の許可 exact-set(5 項目)だけ**。**`source_digest` 4 件と `inventory.sha256` は機械再計算の結果と一致する**(手で書いた値を通さない)
- [ ] 【機】**非緩和 S5**: **3 生成モジュールへの変更が、資産と一致する版・digest の更新だけ**。**本体の論理に差分が無い**
- [ ] 【機】**非緩和 S6**: **`tests/test_check_tenant_boundary_bypass.py` への変更が [design.md](design.md) 6-4 の 3 項目だけ**。**既存の検査意図を変えていない**
- [ ] 【機】**非緩和 S7**: **`.claude/core-areas.json` への変更が `tenant-isolation.paths` への新パス登録だけ**で、**`tests/test_core_guard.py` の exact-set が同期している**。**ほかの領域の paths を触っていない**
- [ ] 【機】**網羅の実測**: **ステップ 1 で得た変更対象の実測リストが、S1〜S7 の列挙と exact-set 一致する**
- [ ] 【機】**revision の同期**: **7 資産すべてで、`identity.field` が指すトップレベル revision field と `current_identifiers` が一致している**
- [ ] 【逐】**非緩和 S4**: **archive 検査が既存の判定の後に走り、既存の合否を変えない**
- [ ] 【逐】**主張の限定**: **PR 本文に「11 ケース corpus 内の差分比較」と書いてあり、「全入力で緩めていない」とは書いていない**([design.md](design.md) 6-4)
- [ ] 【機】**本番経路**: **すべてが本番 `check_repository` 経路を通る変異テストで示されている**
- [ ] 【機】**記録**: **本 PR の受理記録は authority に 1 件だけ**。**7 資産すべての新旧識別値を持つ**。**既存 snapshot を 1 つも変更・削除していない**
- [ ] 【逐】**逐行確認**: **確認対象コミットの SHA を固定して実施した**。**確認後の差分は証跡ファイルに限る**
- [ ] 【逐】**射程の明示**: **PR 本文の「主張しない範囲」が [design.md](design.md) 7 節と同じ 7 項目・同じ順序**。**「PR B を開かない」ことと 1 節の見直しが明記されている**
- [ ] 【逐】**文書整合**: **`research.md` 冒頭に節ごとの生死を exact-set の表で示してある**(**7-3 は生存**)。**計画書 4 節が「調査の正」を生存節に限定している**
- [ ] 【機】ルートと `backend/` の全ゲート green

## 6. テスト計画

**NFR-019 の条文が列挙するのは (a) 一致性 / (b) 越境 / (c) E2E / (d) 同期プロトコルの故障系の 4 種で、本タスクが足すのはそのいずれでもない。** 本タスクは**検査器自体の検査**であり、製品の経路を通らない。**下表の種別は本計画が便宜的に置く区分である。**

| 種別 | 足すもの | ステップ |
| --- | --- | --- |
| **単体** | 参照の構造的抽出(v2 限定)/ 抽出表のキー集合の exact-set 一致と分類値の exact-map 一致 | 2 |
| **単体** | 量の測定と閾値判定(孤児は両側で算出して比較) | 3 |
| **単体** | 新規孤児ゼロの不変量 | 4 |
| **故障系(変異)** | 参照でない 64 桁 hex の混入 / 抽出表の未更新 / 分類値の反転 / 「参照なし」へ有効な `snapshot_ref` を置く / 参照形式違反 / v1 を v2 として走査 / v2 の参照フィールド欠落 | 2 |
| **故障系(変異)** | 各量の閾値超過 / 比較元の孤児での誤検出 | 3 |
| **故障系(変異)** | 同一受理内での記録の作り直しで孤児が増える | 4 |
| **故障系(変異)** | **本番経路**: 新規孤児 / 閾値超過 / 参照の非正規 | 5 |
| **構造** | import が一方向であること / CLI の import 成功 / **非緩和 S1〜S3・S5〜S7 の差分検査**(派生値は機械再計算との一致まで) | 2・5 |
| **差分比較** | **固定 SHA の前版検査器との突合**(11 ケース manifest・PR 受理モード・転じた集合の exact-set 一致) | 6 |
| **故障系(変異)** | [design.md](design.md) 5 節の F1〜F11 | 7 |
