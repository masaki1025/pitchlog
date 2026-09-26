---
feature: runtime-contract-switch
type: design
date: 2026-09-26
---

# 詳細設計: ランタイム契約をその場で製品化する(Y2)

**方式の決定**: 人間の判断(2026-09-26・山田正輝)で **Y2 = 暫定資産をその場で製品化する形**を採った。
削除する案(X)と、凍結対象を製品資産へ向け直す案(Y1)を採らない理由は 0 節。調査の典拠は [research.md](research.md)。

## 0. 方式の比較と、採らなかった案

| 案 | 内容 | 採らない理由 |
| --- | --- | --- |
| **X. 削除する**((a) 継承 / (b) 廃止) | `product-authz-surface/design.md` 9 節のとおり暫定資産を消す | 検査器が削除を 2 段で拒否する(research.md 2-2)。削除を通す機構は **TSK-461**(`未着手`)の射程で、TSK-448 はそれを「実行できないか空洞化するかの二択」と判定している |
| **Y1. 凍結対象を向け直す** | 暫定資産を宣言だけにして、`external_files` に `ddl-elements.json` を足す | **凍結はファイル単位でしかできない**(`frozen_projection.external_files` はファイル全体の sha256)。`ddl-elements.json` 全体が凍結され、**後続タスクの RLS ポリシー 1 行の変更まで、凍結基準の移動**(記録と承認)になる |
| **Y2. その場で製品化する(採用)** | 暫定資産を同じパスに残し、**製品のランタイム契約そのもの**に変える。値は `ddl-elements.json` から生成器で導く | — |

**Y2 で凍結について起きること**: 凍結の粒度・置き場・対象の対応は変わらない。**動くのは値だけ**(movement trigger の `baseline_value` の軸)。
記録は `base-allowlist.json` への v2 記録 1 件で済み、いまの検査器のまま通る(research.md 2-3)。

**条文(設計書 7.7)との関係**: 基準は削除しない。凍結対象(この資産の全トップレベル欄と外部 3 ファイル)も外さない。
したがって「削除のとき宣言をどうするか」(`:574-577`)には当たらず、**「値の変更」**(`:552-553`)として 7.7-2 の記録を 1 件書く。
`superseded_by` を取り除くことは資産の本文の値の変更であり、`baseline_control` の宣言を取り除くことではない。
計画の敵対レビュー 1 周目は、この読みを「成立する」と判定した(`:553`・`:581`)。

## 1. 切り替え後の資産の形

### 1-1. `contracts/tenant_boundary/runtime-authz-contract.json`(製品のランタイム契約)

| 欄 | 切り替え前 | 切り替え後 | 値の出所 |
| --- | --- | --- | --- |
| `schema_version` | 1 | 1 | 変えない |
| `runtime_contract_revision` | 4 | **比較元の値 + 1** | **最終ステップで、固定した比較元から 1 回だけ決める**(2-3・4-1)。数値をべた書きしない |
| `baseline_control` | v1 の記録 1 件 | **`identity.current_identifiers` だけを更新する。`history` は 1 バイトも変えない** | 7.7-2(履歴は追記のみ)・`frozen_history.py:519-527`(この資産の history には追記できない) |
| `asset_kind` | `tenant_boundary_runtime_authz_contract` | 同じ | 変えない |
| `provisional` | `true` | **`false`** | U-T1 の出力契約 ⑤(`tenant-boundary-enforcement/design.md:340`) |
| `superseded_by` | `ddl-elements.json` | **欄ごと取り除く**(`null` も置かない) | 切り替え後は指す先が無い |
| `canonicalization` | `json-sort-keys-utf8-v1` | 同じ | 変えない |
| `derived_from` | (無い) | **`contracts/authz/product/ddl-elements.json`**(新設) | 生成器の入力を資産自身に書く。検査はこの値と、実際の最終パスの一致を見る |
| `source_digest` | `f234b585…` | 再計算 | 既存の規則(`source_digest` だけを除いた全体の sha256) |
| `application_role.rolname` | `pitchlog_app` | 同じ | **宣言のまま**(製品資産に「アプリ用ロールはどれか」を示す欄が無い) |
| `application_role.attributes` | 7 属性 | **製品資産の `roles` のうち `role_id == rolname` の行から導く** | 対応表は 2-2 |
| `protected_objects.schemas` | `public` | **製品資産の `schemas` の全件**(`public`・`authz_private`) | 2-2 |
| `protected_objects.tables` | 45 件 | **製品資産の `tables` の全件**(45 件) | 2-2 |
| `protected_objects.functions` | 33 件 | **製品資産の `functions` の全件**(38 件 = トリガ 37 + `rls_helper` 1) | 2-2 |
| `dangerous_endpoint_fixtures` | 5 件 | 同じ | **宣言のまま**(試験の fixture ID であり、DDL から導けない) |

**新しいトップレベル欄(`derived_from`)を足しても、凍結の軸は `baseline_value` 以外に動かない**: `included = all_top_level_fields` は新しい欄を拒否せず、射影に取り込む(`frozen_history.py:999`)。JSON は `sort_keys=True` で正規化するので、キーの順序だけでは動かない(計画レビュー 1 周目の確認)。

**保護対象を「製品資産の全件」にする根拠**: PR A1 は、staged から導いた保護対象が「暫定資産の保護対象 ∪ 宣言済みの追加分 6 件」と exact に一致することを、検査ですでに固定している(`product-authz-surface/design.md:317`・`check_authz_catalog.py:4089-4167`)。
追加分 6 件の内訳は、漏れ 4 件(0015・0016・0017・0024)と `authz_private` スキーマ、補助関数 1 個(`ddl-elements.staged.json:59-116`)。計画レビュー 1 周目の実測では、スキーマ 1 + 1 = 2、表 45 + 0 = 45、関数 33 + 5 = 38 が exact-set で一致した。
**切り替えで保護対象が「黙って」変わることはない。** 変わる分は、この 6 件として事前に宣言されている。

**U-T1 のロール真正性検査への影響**: `engine.py` は、保護対象の所有者を危険ロールに加える(`backend/src/pitchlog/db/engine.py:251-303`)。
補助関数の所有者 `pitchlog_shared_fn_owner` は `bypass_rls: true`(`ddl-elements.staged.json:31-41`)なので、`rolbypassrls` の照会(`:243-249`)でもともと危険ロールに入る。**判定は厳しくなる方向にしか動かない**(推論)。
**ただし、既存の DB 試験はこれを証明しない**: 既存の fixture は `public.tenants` と public の関数 2 個しか作らない(`test_authz_tenant_binding.py:266` 付近)。`engine.py` は DB に無い保護対象を黙って飛ばす。→ **製品 DB での統合試験を足す**(5 節)。

### 1-2. `contracts/authz/product/ddl-elements.json`

- `ddl-elements.staged.json` から `git mv` する(9 節 1 項のとおり)
- **`runtime_contract` 欄は足さない**(9 節 1 項を改める — 6 節)
- **`pending_switch` と `provisional_contract_additions` を取り除く**。どちらも未発効状態(`product-authz-surface/design.md:305-322`)を表す欄で、切り替え後は意味を持たない。**漏れ 4 件の事実は、受理の記録(4 節)の `movement_fact` に書いて残す**(Notion カードの申し送り)
- `backend/src/pitchlog/authz/asset_spec.py:262` のパスを最終パスへ変える(`design.md:322`「spec の 1 行の変更で済む」)

### 1-3. `backend/src/pitchlog/authz/runtime_contract.py`(生成モジュール)

- 1-1 の資産から生成する。`PROVISIONAL = False` / `SUPERSEDED_BY = None` / `SOURCE_ASSET = "contracts/tenant_boundary/runtime-authz-contract.json"` / `SOURCE_DIGEST` = 1-1 の値
- **`SOURCE_ASSET` はランタイム契約の資産(tenant_boundary 側)を指す。** 9 節 2 項の「`SOURCE_ASSET` = 製品資産」は改める。`SOURCE_DIGEST` が digest を持つのはこの資産だからである
- `DERIVED_FROM = "contracts/authz/product/ddl-elements.json"` を足す(暫定の間は `None`)
- 公開シンボルの名前と型は変えない。U-T1 はこのモジュールだけを import する(`tenant-boundary-enforcement/design.md:341`)

## 2. 生成器

### 2-1. 置き場と結線

**置き場**: 2 つのモジュールに分ける(計画レビュー 2 周目 P1-6)。

| モジュール(新設) | 中身 | 使う側 |
| --- | --- | --- |
| `backend/src/pitchlog/authz/runtime_contract_state.py` | **副作用の無い共有 API**: 状態の判定(3-1)・導出(2-2)・述語の評価と違反 ID(3-2)・描画(資産 → モジュールの文字列)。ファイルは読むだけで書かない。バージョン管理の履歴を読まない | 生成器・`scripts/check_authz_catalog.py`・試験の**三者が直接呼ぶ**。状態の判定と保護対象の選択を、この 1 か所にしか書かない |
| `backend/src/pitchlog/authz/runtime_contract_generator.py` | CLI(2-3)。共有 API を呼び、ファイルを書き、`switch` では比較元の資産を履歴から読む | 開発者・CI・試験 |

実行は `cd backend && uv run python -m pitchlog.authz.runtime_contract_generator <mode>`。
**生成器はリポジトリの作業ツリーの中でだけ動く CLI である**(同 P2-2)。インストールされた製品の環境では使わない。リポジトリのルート(`contracts/` と `.git`)が見つからなければ、**終了コード 2** と明確なメッセージで止める。

**この置き場にする理由**(計画レビュー 1 周目 P0-2):
- **コア領域**: `backend/src/pitchlog/authz/*` は `tenant-isolation.paths` に入っている(`.claude/core-areas.json:318`)。生成器だけを変える将来の PR も、コア領域のレビューを避けられない。`core-areas.json` を変えずに済む
- **CI**: backend ジョブのパスフィルタは `backend/**`・`contracts/**`・`ci.yml`(`ci.yml:206-209`)。生成器・資産・製品資産のどれを変えても、backend の pytest(`check` 相当の試験)が必ず起動する。`scripts/` に置くと起動しない
- **前例**: 製品 DDL の生成器 `pitchlog.authz.ddl.generate_authz_ddl` が同じパッケージにある
- **ランタイムからは import しない**。`runtime_contract.py` と `engine.py` は生成器を参照しない(試験で表明する)

**凍結の外部ファイル 3 件(`check_tenant_boundary_bypass.py`・`frozen_history.py`・`ci.yml`)には触れない** — 触れると 7 資産すべての射影が動く(research.md 2-3)。

### 2-2. 導出の規則

**属性名の対応**:

| 製品資産 `roles[]` | ランタイム契約 `attributes` |
| --- | --- |
| `superuser` | `rolsuper` |
| `bypass_rls` | `rolbypassrls` |
| `login` | `rolcanlogin` |
| `create_role` | `rolcreaterole` |
| `create_db` | `rolcreatedb` |
| `replication` | `rolreplication` |
| `inherit` | `rolinherit` |

- `role_id`・`creation` 以外に対応の無いキーが役割行にあれば、**fail-closed で止める**(黙って落とさない)。`role_id == rolname` の行が 0 件または 2 件以上でも止める
- 保護対象は `(schema, name[, identity_args])` の辞書順に並べる。**現在の暫定資産の並びとは一致しない**。切り替えの時点で 1 回だけ並びが変わるのは値の変更に含まれ、記録に書く(4 節)
- 未発効状態では、staged から導いた保護対象を「暫定資産の保護対象 ∪ `provisional_contract_additions`」と exact に照合する(PR A1 の不変条件を、生成器の実装で再現する)

### 2-3. CLI の契約(計画レビュー 1 周目 P1-2)

| モード | 入力 | 書くもの | 規則 |
| --- | --- | --- | --- |
| `check`(既定) | 作業ツリー | **何も書かない** | 状態(3 節)を判定し、その状態で成り立つべき**すべて**の述語(3-2)を照合する。1 つでも違えば非 0 で終わり、違反 ID と差分を表示する |
| `render` | ランタイム契約の資産 | `runtime_contract.py` だけ | 資産は変えない。暫定・製品のどちらの状態でも使える |
| `switch --base <git rev>` | 最終パスの製品資産 + `<git rev>` のランタイム契約の資産 | ランタイム契約の資産と `runtime_contract.py` | **製品状態へ移す 1 回だけの操作**。`runtime_contract_revision` = **`<git rev>` の資産の値 + 1**(作業ツリーの値ではなく、固定した比較元から決める。何回実行しても同じ値になる)。更新の順序は lifecycle 欄と識別値 → 導出欄 → `source_digest` → モジュールの描画。**`<git rev>` の資産が暫定状態でなければ止める** |

- **冪等**: どのモードも、2 回目の実行は差分 0 になる
- **書き込み**: 各ファイルは一時ファイルへ書いてから置き換える(**ファイル単位で原子的。複数ファイル全体では原子的ではない**)。`switch` が 2 ファイルの間で止まった途中の状態は `check` が fail-closed で検出し、再実行で収束する(同 P2-1)。この故障試験は `switch` を入れるステップ(plan のステップ 6)に置く
- **決定性**: 出力はバイト単位で決定的。生成モジュールは `backend/` の `ruff format` で変わらない(`cd backend && uv run ruff format --check src/pitchlog/authz/runtime_contract.py`)

## 3. 状態と検査(U-T1 の二状態契約の改訂)

**改めるもの**: U-T1 の「切替後に暫定資産が残っていると red」(`tenant-boundary-enforcement/design.md:344`)と、それを実装した `test_authz_runtime_contract.py:135-139`(ファイルがあるだけで違反)。
**守る目的は変えない**: 切り替えの後、暫定の値が生きた入力として残らないこと・差し替えの漏れを検出できること(`:340-346`)。
**判定を「ファイルがあるか」から「中身が製品状態を満たすか」へ変える。**

### 3-1. 状態

| 状態 | 条件 | 成り立つべき述語 |
| --- | --- | --- |
| 暫定 | staged 無し ∧ 最終無し | D1〜D5・T1〜T8 |
| 未発効 | staged 有り ∧ 最終無し | D1〜D5・T1〜T8・U1 |
| **製品** | staged 無し ∧ 最終有り | D1〜D5・P1〜P11 |
| 不正 | staged 有り ∧ 最終有り | 常に違反 `BOTH_STAGED_AND_FINAL` |

### 3-2. 述語と違反 ID(計画レビュー 1 周目 P1-4・2 周目 P1-1・P1-4)

**各述語は独立の変異で red にする。** 試験は「変異 1 つにつき、期待した違反 ID の集合と exact に一致する」ことを表明する。
**既存の違反 ID は、意味が変わらないものは同じ名前で引き継ぐ**(3-3 の対応表)。

**全状態に共通 — 固定の宣言値**(DB から導かない値。2 周目 P1-4):

| ID | 述語 | 違反 ID | 変異 |
| --- | --- | --- | --- |
| D1 | ランタイム契約の資産がある | `PROVISIONAL_ASSET_MISSING`(既存の名前を引き継ぐ。製品状態でも同じ ID) | 資産を消す / 改名する |
| D2 | `application_role.rolname == "pitchlog_app"` | `DECLARED_ROLE_NAME_MISMATCH` | 別の実在ロール(`pitchlog_owner`・`pitchlog_shared_fn_owner`)に置き換える(2 変異) |
| D3 | `schema_version == 1`・`asset_kind == "tenant_boundary_runtime_authz_contract"`・`canonicalization == "json-sort-keys-utf8-v1"` | `DECLARED_VALUE_MISMATCH` | 3 欄をそれぞれ変える(3 変異) |
| D4 | `dangerous_endpoint_fixtures` == 5 件の `(category, fixture_id)` の exact-set(`runtime-authz-contract.json:442-463` の現在値) | `DANGEROUS_FIXTURES_MISMATCH` | 1 件落とす / 重複させる / fixture ID だけを別の `DANGER_*` に変える(3 変異) |
| D5 | `current_identifiers == [runtime_contract_revision:<値>]`・`source_digest` が正しい | `IDENTIFIER_MISMATCH` / `SOURCE_DIGEST_STALE` | 識別値の片方だけ変える / 欄を 1 つ変えて digest を据え置く |

**暫定・未発効**:

| ID | 述語 | 違反 ID | 変異 |
| --- | --- | --- | --- |
| T1 | 資産 `provisional: true` | `PROVISIONAL_FLAG_MISSING` | `false` にする |
| T2 | 資産 `superseded_by` == 最終パス | `SUPERSEDED_BY_MISMATCH` | 欄を消す / 別パス |
| T3 | 資産に `derived_from` が無い | `DERIVED_FROM_BEFORE_SWITCH` | 欄を足す |
| T4 | モジュール `PROVISIONAL is True` | `GENERATED_MODULE_IS_NOT_PROVISIONAL`(既存) | `False` にする |
| T5 | モジュール `SOURCE_ASSET` == ランタイム契約の資産のパス | `GENERATED_MODULE_SOURCE_MISMATCH`(既存) | 別パス |
| T6 | モジュール `SUPERSEDED_BY` == 最終パス | `GENERATED_MODULE_SUPERSEDED_BY_MISMATCH`(既存) | `None` にする |
| T7 | モジュール `DERIVED_FROM is None` | `GENERATED_MODULE_DERIVED_FROM_MISMATCH` | 最終パスを入れる |
| T8 | モジュール == 資産の描画結果(バイト一致 — T4〜T7 以外の定数) | `GENERATED_MODULE_STALE` | 保護表を 1 件変える / revision / digest(3 変異) |
| U1 | staged から導いた保護対象 == 暫定 ∪ 追加分 | `STAGED_PROTECTED_SET_MISMATCH` | 追加分を 1 件落とす |

**製品**:

| ID | 述語 | 違反 ID | 変異 |
| --- | --- | --- | --- |
| P1 | 資産 `provisional: false` | `PROVISIONAL_REMAINS` | `true` のまま |
| P2 | 資産に `superseded_by` 欄が無い | `SUPERSEDED_BY_REMAINS` | `null` を置く / 旧値を残す(2 変異) |
| P3 | 資産 `derived_from` == 最終パス | `DERIVED_FROM_MISMATCH` | staged を指す / 別パス / 欄が無い(3 変異) |
| P4 | 資産の導出欄 == 最終資産から導いた値 | `DERIVED_FIELDS_STALE` | 保護関数を 1 件落とす / 足す / 暫定の 33 件に戻す / 属性を 1 つ変える / スキーマを `public` だけに戻す(5 変異) |
| P5 | 最終資産に `pending_switch` が無い | `PENDING_SWITCH_REMAINS` | 残す |
| P6 | 最終資産に `provisional_contract_additions` が無い | `PROVISIONAL_ADDITIONS_REMAIN` | 残す |
| P7 | モジュール `PROVISIONAL is False` | `GENERATED_MODULE_IS_PROVISIONAL`(既存) | `True` のまま |
| P8 | モジュール `SUPERSEDED_BY is None` | `GENERATED_MODULE_HAS_SUPERSEDED_BY`(既存) | 旧値を残す |
| P9 | モジュール `SOURCE_ASSET` == ランタイム契約の資産のパス | `GENERATED_MODULE_SOURCE_MISMATCH`(既存) | 最終パスや staged を入れる |
| P10 | モジュール `DERIVED_FROM` == 最終パス | `GENERATED_MODULE_DERIVED_FROM_MISMATCH` | staged / `None` |
| P11 | モジュール == 資産の描画結果(バイト一致 — P7〜P10 以外の定数) | `GENERATED_MODULE_STALE` | `PROVISIONAL` だけ新しく保護対象が古い / revision が古い / digest が古い(3 変異) |

- **U-T1 の目的の継承**: 製品状態で「`provisional: false` にしつつ導出欄を暫定値のまま」は P4、「`derived_from` を staged に向ける」は P3、「モジュールだけ古い」は P7〜P11、「アプリ用ロールの名前を別の実在ロールへ変える」は D2 が止める
- **保護対象が切り替えで黙って変わらないこと**は、常時の述語ではなく **`switch` の自己検証**で固定する: ① 比較元 S で U1 が成り立つ(staged から導いた保護対象 == 暫定 ∪ 宣言済みの追加分 6 件)② 最終パスの製品資産 == S の staged の資産から `pending_switch` と `provisional_contract_additions` の 2 欄を除いたもの(exact)。① と ② から、切り替え後の保護対象 == 暫定 ∪ 追加分 6 件が導かれる。どちらかが成り立たなければ `switch` は何も書かずに止まる
- 述語の判定は**共有 API(2-1)の 1 か所にしか書かない**。生成器の `check`・`scripts/check_authz_catalog.py`・試験の三者がこれを呼ぶ

### 3-3. 既存の違反 ID の引き継ぎ(計画レビュー 2 周目 P1-1)

| 既存の ID(`test_authz_runtime_contract.py:127-156`) | 扱い | 理由 |
| --- | --- | --- |
| `PROVISIONAL_ASSET_MISSING` | **引き継ぐ**(D1。全状態) | 資産が無いことは、Y2 では全状態で違反 |
| `GENERATED_MODULE_IS_NOT_PROVISIONAL` | 引き継ぐ(T4) | 意味が同じ |
| `GENERATED_MODULE_SOURCE_MISMATCH` | 引き継ぐ(T5・P9) | 意味が同じ(期待値は両状態とも tenant_boundary 側のパス) |
| `GENERATED_MODULE_SUPERSEDED_BY_MISMATCH` | 引き継ぐ(T6) | 意味が同じ |
| `GENERATED_MODULE_IS_PROVISIONAL` | 引き継ぐ(P7) | 意味が同じ |
| `GENERATED_MODULE_HAS_SUPERSEDED_BY` | 引き継ぐ(P8) | 意味が同じ |
| `PROVISIONAL_ASSET_REMAINS` | **廃止** → P1 `PROVISIONAL_REMAINS`・P2 `SUPERSEDED_BY_REMAINS` へ置き換える | Y2 では資産のファイルが残ることが正しい状態になる。「暫定の値が残る」ことを中身で判定する(6 節に改訂として記録する) |
| `GENERATED_MODULE_REFERENCES_PROVISIONAL` | **廃止** → P9 `GENERATED_MODULE_SOURCE_MISMATCH` と P10 へ置き換える | Y2 ではモジュールが参照する資産のパスは切り替えの前後で同じ。「暫定を参照する」ことは P7(`PROVISIONAL`)と P10(`DERIVED_FROM`)で判定する |

**暫定・未発効の 2 状態の間で、既存の ID の集合は保たれる**(廃止の 2 件はどちらも製品状態だけの ID)。

### 3-4. 検査器側(`scripts/check_authz_catalog.py`)

- **状態の判定・保護対象の選択は共有 API(2-1)を呼ぶ**。`check_authz_catalog.py` は `backend/src` のモジュールをすでに読み込める(`:21-22`)。検査器の中に状態の判定を別に書かない
- トップレベルのキー集合(`:4250-4271`)を**状態で分ける**。製品状態では `pending_switch`・`provisional_contract_additions` を**禁止**する
- 件数 33 のべた書き(`:3962`)と `PRODUCT_PROVISIONAL_FUNCTION_GAPS`(`:168-179`)は未発効状態でだけ使う。製品状態では「ランタイム契約の保護関数 == 製品資産の関数の全件」を見る
- 暫定資産を比較元にした照合(`:4089-4167`・`:4321-4322`)は、製品状態では上の照合に置き換わる。**「ファイルがあるときだけ走る」分岐は作らない**(状態ごとに必ずどちらかが走る)

## 4. 受理の記録(7.7-2)

`base-allowlist.json`(履歴の authority)の `history` に v2 の記録を 1 件追記する。形式は #80 の記録(`base-allowlist.json:782-1536`)に揃える。

| 項目 | 内容 |
| --- | --- |
| `acceptance_id` | 本 PR(**draft PR を先に作って確定する** — 前例 `docs/worklog/2026-09-24-tenant-boundary-baseline.md` のステップ 1) |
| 識別値 | `runtime-authz-contract.json` だけが `比較元 + 1` になる。他の 6 資産は比較元と同じ値を新旧の両方に書く |
| `change.aspect` | **`["asset_snapshots", "declaration"]`**(計画レビュー 1 周目 P0-1)。許される aspect 名は `declaration` / `movement_policy` / `external_snapshots` / `asset_snapshots` の 4 種だけで(`frozen_history.py:20-26`)、実際の差分から exact-set で照合される(`:1565`)。本文の値の変更が `asset_snapshots`、`current_identifiers` の更新が `declaration` を動かす(`:448`)。**`baseline_value` は movement trigger の軸の名前で、aspect の名前ではない**。外部 3 ファイルは変えないので `external_snapshots` は入らない(比較元を最終ステップで固定するため、TSK-448 などの外部ファイルの変更は比較元の側に入る) |
| `before` / `after` | 比較元と受理後のスナップショット(`history-snapshots/` に追加) |
| `movement_fact` | ① 暫定から製品へ切り替えた(`provisional`・`superseded_by`・`derived_from`)② 保護関数 33 → 38・保護スキーマ 1 → 2 と、その内訳(**暫定資産が追随していなかった 4 関数 0015・0016・0017・0024** / `authz_private` / 補助関数 1)③ 保護対象の並びを辞書順に変えた ④ **この資産の v1 記録にある受理前の印(`source_commit` と承認の 2 欄)は、PR #72 のマージ後も受理値へ更新されておらず、追記のみの規律により書き換えず、この資産の `history` にそのまま残る** ⑤ 受理の対象とした比較元のコミット SHA(4-1) |
| `reason` | TSK-424 PR B として、U-T1 の暫定ランタイム契約を製品の DDL 資産から導いた値へ切り替えるため。削除ではなく同じパスで製品化したこと(人間の判断 2026-09-26)と、その理由(0 節) |
| `approved_by` / `approved_on` | **人間が PR 上で受理を明示した後に、その発話の日付と名前を逐語で書く**(`harness-evaluation.md:3904-3921` の規律) |

**記録の自然言語の欄に予約語を書かない**(計画レビュー 2 周目 P0-1): v2 の記録は、機械値の欄(`acceptance_id`・識別値の map・`change.aspect`・`change.before`・`change.after`)を除くすべての文字列について、`PENDING`・`TODO`・`TBD`・`未承認`・`未定`・`レビュー待ち` を拒否する(`frozen_history.py:39-41`・`:50-60`・`:1712-1725`)。
→ 9 節 5 項の「`PENDING_ACCEPTANCE` と『未承認(PR #72 のレビュー待ち)』を変更前の値としてそのまま記録する」は、**いまの検査器では書けない**。旧値そのものは、削除されない v1 の記録に残っている(`runtime-authz-contract.json:46`・`:66-67`)。本記録の `movement_fact` は、予約語を使わずにその事実を指す(④)。**旧値の正本は、変更されずに残る v1 の記録だけである**。`change.before` のスナップショットは凍結の射影で、この資産は `baseline_control` 全体を射影から除いているため(`runtime-authz-contract.json:12-17`・`frozen_history.py:1064-1091`)、v1 の history は入らない。v1 の記録は比較元との前方一致で保護されている(`frozen_history.py:224`)。authority 側の記録に旧値を自己完結的に残すことは、いまのスナップショットの形式ではできない。この改訂は 6 節に記録する。
**ステップ 6 のドライランで、ステップ 8 に入れる予定の記録をそのまま `frozen_history.py` の検査に通す**(机上で終わらせない)。

### 4-1. 最終フェンス(計画レビュー 1 周目 P1-1・P1-3)

**切り替え(資産の移動)と受理の記録は、同じ最終ステップの 1 コミットで入れる。** 分けると、間のコミットで凍結基準の検査が red になる(検査器は移動と記録の有無を一致させる — `frozen_history.py:543`)。

1. develop を取り込む(PR A2・TSK-448 など、比較元を動かす変更を先に入れる)。取り込んだ時点の `origin/develop` の先端のコミット SHA を **比較元 S**、取り込みを終えたステップ 7 までの HEAD を **H** とする
2. **製品化のドライラン**(plan のステップ 6 の仕組み)を H の複製で実行し、ステップ 8 のコミットを**そのまま作る**。ただし `approved_by` / `approved_on` の 2 欄だけは固定の値 `DRYRUN` / `1970-01-01` を入れる(予約語ではない)。**このコミットの tree の SHA をドライラン digest D とする**。D はステップ 8 の全パッチ(`git mv`・`asset_spec.py`・ランタイム契約の資産・生成モジュール・`base-allowlist.json` 全体・`history-snapshots/`)を含む
3. **人間が PR 上で、S・H・D を明記して受理する**(例:「S=<sha>・H=<sha>・D=<sha> で受理する」)。判断材料は、H までの全差分とドライランの差分(`git diff H <ドライランのコミット>`)
4. ステップ 8 を実行する直前に `git fetch` し、**`HEAD == H`・`origin/develop == S`・同じ手順で再計算した D の一致**をすべて確かめる。どれかが違えば 1 からやり直し、受理も取り直す(前の受理は使わない)
5. `switch --base S` を実行し、スナップショットと v2 記録(`movement_fact` に S を書く)を 1 コミットで入れる
6. **コミットの後にも**、そのコミットの親が H であることと、`approved_by` / `approved_on` を 2 の固定値に戻した tree の SHA が D と一致することを確かめ、結果を worklog に残す。全 CI を回す
7. **PR は、`origin/develop == S` の間にマージする**。マージの前に develop が動いたら、受理は失効する(1 からやり直す)

**機械で検出できる範囲**(計画レビュー 2 周目 P1-2・3 周目 P1-1): 検査器は `acceptance_id` と PR のイベントの一致、`approved_by` が空でないこと、`approved_on` の日付の形式しか見ない(`frozen_history.py:674`・`:1521`)。**「受理した差分」と「入れた差分」の一致は、検査器では検出できない**。上の 3〜7 は、S・H・D を人間の受理の発話と記録に残して、**手動のゲートとして**一致を確かめるものである。H が受理した実装の差分を、D が最終コミットの全パッチを、S が比較元を縛る。

**`switch` の拘束**(同 P1-3):
- `--base` はコミット SHA に正規化し、**`origin/develop` の先端と一致し、かつ HEAD の祖先でなければ止める**(PR の HEAD・無関係なコミット・古い祖先を拒否する)
- 書いた後に **`runtime_contract_revision == (S の資産の値) + 1`** を自ら確かめる(+2 などを拒否する)
- CLI の試験で、HEAD・無関係なコミット・古い祖先を `--base` に渡したときと、revision を +2 した資産のときに止まることを表明する

## 5. 製品 DB での統合試験(計画レビュー 1 周目 P1-5)

- **PR A2 の適用器**(`pitchlog.authz.product_provisioning` と、使い捨てクラスタの fixture — A2 plan のステップ 3)で製品 DDL を適用した DB を使う。A2 の `ProvisionedProductCatalog`(使い捨てクラスタ・適用器・観測用の接続・製品資産を持つ — A2 の `backend/tests/db_fixtures.py:476`・`:837`、コミット `4024bd69`)を使い、**試験は `backend/tests/db/` に置く**
- **所有者の照会は SQL を複製しない**。製品の接続時の検査(`engine.py` の `_verify_application_role_connection` の経路)を通す。切り替えの前は、その経路が読む契約の値を、共有 API が導いた製品の値に差し替えて呼ぶ(差し替えは試験の中だけ)
- **生成器が製品資産から導いたランタイム契約**(暫定の生成モジュールではない)の保護対象について、次を表明する:
  - スキーマ 2・表 45・関数 38 の**すべてが DB に実在する**(`identity_args` を含めて `pg_get_function_identity_arguments` と一致する)
  - 所有者の照会(`engine.py` と同じ SQL)が、**期待件数ちょうどの行**を返す(黙って飛ばされる対象が無い)
  - 危険ロールの集合に `pitchlog_shared_fn_owner` が入り、アプリ用ロールの真正性検査が通る
- **この試験は切り替えの前に入れる**(未発効状態でも、導出した契約を入力にすれば書ける)。切り替えの後は、生成モジュールを入力にした同じ試験になる
- **`engine.py` の「DB に無い保護対象を黙って飛ばす」挙動そのものは変えない**(U-T1 の射程 — 未解決 1)。本試験は、製品 DB ではその挙動に頼らずに全件が実在することを示すだけである

## 6. 改める既存の決定(人間の承認が要る)

| 決定 | 所在 | 改め方 |
| --- | --- | --- |
| PR B は暫定資産を削除する | `product-authz-surface/design.md:594`(9 節 3 項)・`:322` | 削除せず、同じパスで製品化する(1-1) |
| `runtime_contract` を製品資産に足す / `SOURCE_ASSET` = 製品資産 | 同 `:592-593`(9 節 1・2 項) | 足さない / `SOURCE_ASSET` はランタイム契約の資産(1-2・1-3) |
| 履歴の生存先を (a) か (b) で決める | 同 `:595-598`(9 節 4 項) | **生存先は動かない**(履歴はその場に残る)。合格条件「base の旧資産と HEAD の生存先を exact に突き合わせる」は、「同じパスの資産の値の変更が、記録 1 件で受理される」に読み替える |
| 受け渡しの場所 = `ddl-elements.json` / 切替後に暫定資産が残っていると red | `tenant-boundary-enforcement/design.md:341`・`:344` | 受け渡しの場所はランタイム契約の資産(`ddl-elements.json` はその導出元)/ 判定を中身で行う(3 節) |
| 既存の `test_authz_runtime_contract.py` は変えない | `product-authz-surface/design.md:312` | 変える(PR A1 の間の不変条件であり、切り替えで役目を終える) |
| 削除記録に `PENDING_ACCEPTANCE` と「未承認(PR #72 のレビュー待ち)」を変更前の値としてそのまま記録する | `product-authz-surface/design.md:599`(9 節 5 項) | 削除記録は無い。受理の記録の自然言語の欄には予約語を書けない(`frozen_history.py:39-41`)ので、旧値は変更されない v1 の記録にだけ残し、`movement_fact` は予約語を使わずにその事実を指す(4 節) |
| 違反 ID `PROVISIONAL_ASSET_REMAINS`・`GENERATED_MODULE_REFERENCES_PROVISIONAL` | `test_authz_runtime_contract.py:137-141`(U-T1) | 廃止して置き換える(3-3) |

**これらの文書は、本文を書き換えずに改訂の注記を追記する**(試験のコードは書き換える)(どの決定を、いつ、誰の判断で、どう改めたか)。

## 未解決・検討メモ

1. **保護対象が DB に実在しないときの扱い**(既存の弱さ・本 PR の射程外): `engine.py` の照会は、保護対象が DB に無ければ行を返さないだけで、欠落を検出しない(`engine.py:251-303`)。5 節の試験は製品 DB で全件の実在を示すが、実行時の検出は U-T1 の射程として申し送る
2. **同期モジュールの残り 2 本**(`repositories/repository_contract.py`・`tenant_context_contract.py`)も手で同期している(`a75549c0`)。本 PR の生成器は `runtime_contract.py` だけを扱う。一般化は申し送る
