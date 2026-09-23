---
feature: tenant-boundary-scope
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域          # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e493b75e68781cb819ce706fa3252b1
branch: fix/tenant-boundary-scope
created: 2026-09-24
計画レビュー周回: 0        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: 迂回検査 条件 5・条件 2 の射程を判定する(TSK-440)

## 1. 背景・目的

- Notion タスク: [TSK-440](https://app.notion.com/p/3e493b75e68781cb819ce706fa3252b1)
- 調査: [research.md](research.md)

`scripts/check_tenant_boundary_bypass.py`(U-T1 / TSK-390 が新設したテナント境界の迂回検査)が、
**テナント境界と無関係な 3 パッケージで 719 件を検出する**。

| | TB007(条件 5) | TB002(条件 2) | 計 |
| --- | --- | --- | --- |
| `domaincheck` | 430 | 2 | 432 |
| `domaingen` | 70 | 78 | 148 |
| `domainmut` | 109 | 30 | 139 |
| | **609** | **110** | **719** |

- 38 ファイル。**3 パッケージの外は 0 件**
- **2026-09-24 に `tenant-boundary-bypass` が必須チェックへ入った**(TSK-434)ため、**誤検知が実害に変わった**。
  PR #74 は `harness` / `tenant-boundary-bypass` が red でマージできない
- **この領域にコードが増えるたびに件数が増える**(TSK-235 の是正だけで +25 件)

**関係する要件**: NFR-010 チーム間データ分離(`docs/requirements/requirements-pitchlog-2026-07-22.md:846-850`)。
ただし同 `:850` の測定方法は**ランタイムの越境アクセステスト**であり、
**「静的な迂回検査を置け」「解決不能なら拒否せよ」は要件正本に存在しない**(research.md §4)。
本検査器の根拠は開発ハーネス側の統制と、U-T1 の脅威モデル
(`docs/features/tenant-boundary-enforcement/design.md:426-454`)である。

## 2. スコープ

### やること

- **条件 5(TB007)の未解決 callable の既定値**を、`TenantContext` への到達可能性で分岐させる
- **条件 2(TB002)のパターン `generation` を契約名 `generation_no` へ絞る**
- 上記それぞれについて **通り抜けるものを明記**し、**落ちてはいけないものを負例で守る**
- `tenant-boundary-enforcement/design.md` 6-0 へ射程を明文化する
- 凍結基準の受理手続(`contract_revision` + 履歴 1 件)

### やらないこと

- **パス・パッケージ・モジュール単位の除外を allowlist へ足すこと**
  (`design.md:457` `:463` `:470-471` が P0 で否決済み。母集団を狭める型)
- **一般的な型推論器を作ること**(`design.md:454` が明示的に否定)
- **脅威モデルを正本へ上げること**(人間の判断 2026-09-24 = 上げない)
- **既存の未承認履歴 7 件の是正**(人間の判断 2026-09-24 = 本タスクでは触らない)
- **`conservative_member_names` を広げること** — この集合は inventory の member 名の
  非空部分集合しか許されず(`scripts/check_tenant_boundary_bypass.py:843-857`)、
  `strip` / `get` のような一般メソッドは**機構的に足せない**
- 誤検知を避けるための**呼び出し側 36 ファイル 582 箇所の改変**
  (変更の理由がコードから読めなくなる。TSK-235 のレビュー対象も動く)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし**(条文に静的検査の射程規定が無い) | — |
| `docs/design/sync-protocol.md` | **反映なし**(条件 2 の語彙確定は同期単位へ申し送る) | — |
| `docs/design/data-model.md` | **反映なし** | — |
| `docs/adr/**` | **反映なし** | — |
| `docs/development/dev-harness-design-2026-08-07.md` | **反映なし**(6.3 の境界定義表は動かさない) | — |
| `docs/development/harness-evaluation.md` | 既存候補へ実測を追記(クローズ処理で判断) | PR レビュー |
| `docs/README.md` | 上記を反映した場合の最終更新日 | PR レビュー |

**`docs/features/tenant-boundary-enforcement/design.md` は正本ではない**(feature 設計書)。
6-0 節への追記は本 PR のレビューで行う。

## 4. 実装方針

**重さ分類 = コア領域**。ハーネス設計書 6.3 の**テナント分離**に該当し、
`.claude/core-areas.json` が `contracts/tenant_boundary/*` と `scripts/check_tenant_boundary_bypass.py` を
登録済み。**敵対レビュー + 人間の逐行確認が必須**。

### 4-1. 条件 5(TB007)— 何を変えるか

**TB007 は 2 箇所からしか出ていない**(実測で検算済み):

| 発火点 | 件数 | 内容 |
| --- | --- | --- |
| `scripts/check_tenant_boundary_bypass.py:2963` | **607** | 由来を完全修飾名へ解決できない callable |
| 同 `:2924` | **2** | `dataclasses.replace`(第 0 引数の provenance が `unknown` に落ちた場合) |

**どちらも根拠は「由来を解決できなかった」ことだけ**である。
解決できた場合は `constructor_symbol` と一致しなければ**無罪**(`:2970-2971`)。
→ **この 2 分岐の既定値だけを切り替えれば 609 件は全部消える。母集団は 1 ファイルも削らない。**

#### 2 つのレジーム

| | 適用範囲 | TB007 の扱い |
| --- | --- | --- |
| **A 境界面** | `TenantContext` の生成面へつながりうるモジュール | 現行のまま + **さらに厳しくする**(4-4) |
| **B 圏外** | つながらないモジュール | **`:2963` と `:2924`(`provenance == "unknown"` の場合)だけ**が reject → accept |

**レジーム B でも red のまま残るもの**(3 パッケージで 0 件であることを実測で確認済み):
`object.__new__` / `object.__setattr__` / `type(context)(...)` / 解決済み構築の allowlist 照合 /
発行証跡・動的構築系、そして **TB001〜TB006・TB008 のすべて**。

→ `design.md:463`「丸ごと除外すると、後から直接 SQL や認可迂回を足しても永久に検査対象外になる」は
**成立しない**(直 SQL は TB005、認可迂回は TB001/TB003 が発火し続ける)。**負例で機械的に示す**(4-4)。

#### 到達可能性の定義(fail-closed)

**無向**の import グラフで、anchor 集合から到達できるか。
**無向にする理由**: モジュールが `TenantContext` を作るには、**名指せる**(有向到達)か
**手渡される**(anchor 側がこのモジュールを import して呼ぶ)かのどちらかが要る。
無向なら「境界面から呼べて、かつレジーム B」が**定義上ありえない**。

| 項目 | 規則 |
| --- | --- |
| **`from pkg import name` の辺** | **`pkg.name` がモジュールとして実在すればそこへ張る。実在しないときだけ `pkg` へ張る。両方は張らない**(★ 下記) |
| **相対 import** | **`node.level` を解決して絶対名へ正規化**(現行検査器は `node.level` を見ていない)。**グラフ構築専用の新規関数に閉じ、既存の alias 解決には触れない** |
| `TYPE_CHECKING` 内 | 辺を張る(実測で結論は変わらないが広い側 = 安全側) |
| 動的アクセス | **`import_module` / `__import__` / `load_module` / `exec_module` の呼び出し**、および **第 2 引数が定数でない `getattr`** を持つモジュールは**無条件にレジーム A** |
| AST 解析不能・グラフ未供給 | **全モジュールをレジーム A**(fail-closed) |

**★ 辺の張り方は実測で決めた。** 「`pkg` と `pkg.name` の両方へ張る」(広い側 = 一見 fail-closed)にすると、
`from pitchlog.domainmut import operators_lang` のようなサブパッケージ import が
**ルートパッケージ `pitchlog` への辺**を生む。`pitchlog/__init__.py` は**docstring 1 行だけ**なのに
**48 モジュールが触る hub** になり、**無向到達が 3 パッケージ 44 件中 43 件を引き戻して射程変更がほぼ無効化される**
(実測: 両方張る = 43/44 がレジーム A / dotted 優先 = 0/44)。
→ **`pitchlog/__init__.py` は anchor に含めない**(再エクスポートを 1 つも持たないため anchor の意味もない)。

#### anchor(起点)— 3 系統、すべて widen 方向のみ

| 系統 | 規則 |
| --- | --- |
| **A1 契約シンボル** | 7 資産が宣言する完全修飾シンボルを**定義するモジュール、および文字列リテラルとして含むモジュール**(導出) |
| **A2 DB 面** | `sqlalchemy` / `psycopg` / `asyncpg` を import するモジュール、`db-api-inventory.json` 由来のモジュール(導出) |
| **A3 宣言パス** | `base-allowlist.json` の新フィールド `scope.anchor_path_prefixes`(**規則として資産に置く**) |

**A1 に「文字列リテラル」を入れるのは必須。** `backend/src/pitchlog/repositories/tenant_context_contract.py` は
`CONSTRUCTOR_SYMBOL = "pitchlog.repositories.context.TenantContext"` を**文字列で持つだけで import が 0 本**であり、
これが無いと**テナント文脈契約そのものを宣言するモジュールが圏外へ落ちる**。

**A3 の初期値**: `pitchlog/db/`・`pitchlog/authz/`・`pitchlog/repositories/`・`pitchlog/api/`・`pitchlog/main.py`。
**`pitchlog/__init__.py` は入れない**(上記 ★)。
**A3 は 3 パッケージを落とすためのものではない** — A1+A2 だけで 3 パッケージは 44 件全部レジーム B になる。
A3 は**素朴な anchor だと圏外へ落ちる API 入口層を取り戻すため**にある。

#### 実装上の足場

- **merge-base と HEAD の全ファイルは既に読まれ AST 解析されている**
  (`:3976-3977` の `_git_snapshot` → `_definitions`)。**追加の git 呼び出しも追加の parse も要らない**
- レジーム写像は**資産に一切書かず、`check_repository` の実行時に毎回導出する**。
  資産に置くのは **anchor の宣言とグラフの張り方の定義だけ**

#### 第一案を捨てた記録

当初は「到達できないモジュールを**走査母集団から外す**」案だった。**3 つの理由で捨てた。**

1. **実測**: `TenantContext` へ到達できず **DB 面へ到達できる**モジュールが **11 件**
   (`pitchlog.db.*` 8 / `pitchlog.authz.*` 2 ほか)。**迂回検査が最も見たいコードが除外される**
2. **`design.md:463` が同じ構造を P0 で否決済み**だった(独立に実測で再発見した)
3. 負例 `C5_CONTEXT_UNKNOWN_FACTORY` は **import を 1 つも持たない**ため**緑になる**

### 4-2. 条件 2(TB002)

**`(?:^|_)generation(?:_|$)` → `(?:^|_)generation_no(?:_|$)`**(`contracts/tenant_boundary/base-allowlist.json`)

- **根拠**: 条件 2 の他 6 パターンはいずれも**契約名そのもの**で、**`generation` だけが一般語**だった。
  要件 FR-013(`requirements-pitchlog-2026-07-22.md:321`)は「記録権には**世代番号**を持たせ」と書いており、
  **`seq_no` / `revision_no` と同じ `_no` 形が契約名の自然形**
- **条件 2 はこの検査器の脅威モデルのどの項目にも対応していない**(research.md §3)。
  由来は上流分割計画の「**面を混ぜない**」規律(`product-impl-unit-split/plan.md:270` `:258`)で、
  対応するコア領域は**同期プロトコル**行。**テナント分離の防御ではない**
- **実測**(検査器の `_normalize_identifier` をそのまま使って照合): **110 件 → 0 件**。
  `pitchlog.sync.contracts.generation_no` は**赤のまま**
- 既存負例 `C2_GENERATION_IMPORT` は `generation` を import しており**緑になる**ので、
  `generation_no` を import する形へ更新する

### 4-3. 通り抜けるもの(PR 本文へそのまま載せる)

**1〜4 は本設計が残す穴、5〜6 は本設計以前から存在する穴。**

1. **静的 import が無い実行時エッジ。** プラグイン登録・entry point・設定ファイル経由の文字列 import で
   境界面のコードが圏外モジュールを呼ぶ経路。動的アクセスの fail-closed は**呼び出し側**を A にするだけで、
   **呼ばれる側**は B のままになりうる。現状 `backend/pyproject.toml` の entry point は
   `pitchlog.main:app` の 1 本だけ(A3 で anchor 済み)だが、**将来増えても自動では追随しない**。
2. **サブプロセス越しの経路。** 3 パッケージは `subprocess` を使う。プロセスを跨ぐので
   in-process の `TenantContext` は渡らないが、**生成した SQL やコードを製品側へ流し込む経路**は
   静的グラフに映らない。**脅威モデルに対応項目が無い**別種の穴である。
3. **同一 PR 内でのファイル分割。** レジーム A のファイルから未解決 callable を**新規の孤島ファイル**へ移すと、
   新規ファイルには baseline が無いので TB009 は当たらない。無向到達の議論により
   「境界面から呼べない場所」へ移すことになるので実害は無い、というのが論拠だが、
   **これは静的グラフが実行時の呼び出し関係を正しく上界していることに依存**しており、1・2 と同じ地盤に立つ。
4. **同期単位が D4 の欄を `generation` や `record_generation` と命名した場合、条件 2 は検出しない。**
   条件 2 は単位分割の規律なので**セキュリティ上の後退ではない**。同期単位へ語彙の確定を申し送る。
5. **`backend/src` の外。** 検査器は `backend/src` しか走査しない(`:3788-3803`)。
   `backend/tests` も `frontend` も最初から圏外。本設計はこれを変えない。
6. **悪意ある committer。** `design.md:442-450` が明示的に守らないと宣言済み。
   anchor を減らす PR は凍結射影を動かして人間承認へ上がるが、**承認者が見落とせば通る**。

**この設計が新しく引く線**: `design.md:454`「一般的な型解決器は作らない」に加えて、
**「一般的な呼び出しグラフも作らない」**。**この線を引いた決定文は現在どこにも無い**ので、
本 PR が初めて明文化する(9 ステップ目)。

#### 自己申告の弱点

- **`scope.anchor_path_prefixes`(A3)は人が書くリストである。** 「anchor は widen のみ」と TB011 で
  守るが、**リストの不足を検出する機構は無い**。将来「都合の悪いパスを書かない」圧力がかかりうる。
- **検査器が肥大する。** 4044 行に導出器とレジーム写像が乗り、全体が `external_files` に入っているため、
  **今後この 1 ファイルのどんな小さな変更でも履歴 1 件 + `contract_revision` 更新が発生する**。
  今回はその凍結対象を**大きくする方向**へ動かす。
- **`develop` でレジーム B が 0 件であることは両建ての証明にはなるが、レジーム B の実装が正しい証明にはならない。**
  develop 単体では緩和側のコードパスが 1 度も実行されない。
  **負例と `feature/domain-calc-dsl` への当て込みだけがレジーム B の唯一の実測手段**であり、
  後者は本 worktree では再現しない。
- **負例ハーネスへ合成モジュールを 1 本足す(4-4 (v))のは、テストを検査器に寄せる動きである。**
  1 本だけ・fixture 定義不変・`SCOPE_B_*` 4 本を同時投入で正当化しているが、
  **「なぜ 1 本なら良くて 10 本なら駄目か」に原理的な線は引けていない。**

### 4-4. 落ちてはいけないもの(両建て)

`harness-evaluation.md:3343`「**射程を狭めただけでは通らないよう、宣言した保証範囲に対しては厳しくする両建てが要る**」/
`docs/worklog/2026-09-17-tenant-boundary-enforcement.md:240-247`
「**絞った結果として落ちてはいけないものを同時に名指しする**」。

#### (i) 名指し — `scope.must_remain_on_surface` として規則で資産へ置く

次に一致する全ファイルが**レジーム A であり続ける**ことを検査器が実行時に検証し、
外れたら **TB011** で red にする。

1. `backend/src/pitchlog/repositories/**`(**`tenant_context_contract.py` を含む**)
2. `backend/src/pitchlog/db/**`(素朴な anchor だと落ちる 11 件を全部含む)
3. `backend/src/pitchlog/authz/**`
4. `backend/src/pitchlog/api/**` と `backend/src/pitchlog/main.py`(リクエスト入口層)
5. **7 資産のいずれかがシンボルを宣言している全モジュール**(A1 の導出結果と一致すること)

**`develop` では 1〜5 の合計が全モジュールと一致する見込み**であり、
**「develop のコードは 1 件も緩まない」がそのまま宣言になる**。これを合格条件にする(ステップ 3)。

#### (ii) 収縮そのものを red にする — TB009

merge-base と HEAD の**両方**でレジーム写像を導出し(両版のソースは既に読まれている)、
`baseline = A かつ head = B` のファイルは中身によらず **TB009**。
**「import を消して圏外へ逃げる」を逃げた瞬間に検出する。**
`_application_population_violations`(`:3907-3953`)の TB008 と同じ形に揃える
(**母集団の空洞化を別コードで red にする前例がこの検査器の中に既にある**)。

#### (iii) レジーム A を今より厳しくする — 緩和より先に入れる

- `:2946-2952` の `provenance in {"db","non_db","tenant_context"}` による属性呼び出し免除を、
  **レジーム A では `tenant_context` のみに縮める**
- `:2953-2959` の `db_result` / `non_db_attribute` 免除を、
  **レジーム A では `conservative_member_names` に載るメンバ名に限る**
- **合格条件**: この厳格化を入れた状態で **`develop` の全モジュールを全行走査して新規違反 0 件**。
  1 件でも出たら**ステップを止めて判断する**(空振りだったか、本物の漏れを見つけたかのどちらか)

#### (iv) 負例(`negative-fixtures.json` へ追加)

| ID | 何を守るか | 期待 |
| --- | --- | --- |
| `SCOPE_B_DIRECT_SQL` | **`design.md:463` の否決理由が成立しないこと**。レジーム B へ直 SQL | `TB005` |
| `SCOPE_B_AUTHZ_BYPASS` | 同上。レジーム B へ認可迂回形 | `TB001` |
| `SCOPE_B_OBJECT_SETATTR` | レジーム B でも `object.__setattr__` 改竄は red | `TB007` |
| `SCOPE_B_TYPE_CALL` | レジーム B でも `type(context)(...)` は red | `TB007` |
| `SCOPE_SHRINK_IMPORT_REMOVED` | **import を消して圏外へ逃げる** | `TB009` |
| `SCOPE_SHRINK_ANCHOR_SEVERED` | 中継モジュールの import を削って下流を一括で落とす | `TB009` |
| `SCOPE_ANCHOR_STRING_ONLY` | 契約シンボルを**文字列でしか持たない**モジュールが A に留まる | `TB007` |
| `SCOPE_SURFACE_MUST_REMAIN` | `must_remain_on_surface` 一致ファイルが B に落ちた状態 | `TB011` |
| `SCOPE_DYNAMIC_GETATTR` | 非定数 `getattr` を持つ孤島が A へ引き戻される | `TB007` |
| `SCOPE_SURFACE_TIGHTENED` | (iii) の厳格化 | `TB007` |

#### (v) 既存 68 負例のうち転ぶのは 1 本だけ(実測)

負例は**二重に走る** — `tests/test_check_tenant_boundary_bypass.py:519` が `scan_source` を直に呼び、
`:546` が **temp リポジトリへ実コミット列を作って `check_repository` を通す**。

- `scan_source` の `scope` 引数の**既定値をレジーム A(厳しい側)**にすることで、`:519` は **68 本すべて不変**
- `:546` で緑に転ぶのは **`C5_CONTEXT_UNKNOWN_FACTORY` ただ 1 本**
  (import 0 本 かつ `:2963` の分岐。他の import 無し 25 本は TB004/TB005/`:2908`/`:2938` でレジーム非依存)

**対処**: fixture 定義には触れず、`_initialize_test_repository`(`:222-244`)へ
**負例モジュール群を import する合成の境界面モジュールを 1 本**足す。
負例は `pitchlog/services/*` = サービス層であり、境界面から呼ばれる位置にあるのが実態に即している。
ID・パス・期待値が変わらないので **`fixture_set_revision` は動かない**。

**これが「テストを検査器に合わせて緩めた」に見えうることは自覚する。**
だから (iv) の `SCOPE_B_*` 4 本を**同時に**入れ、
**レジーム B が実際に何を落とし何を落とさないかを fixture 側の細工抜きで直接示す**。

### 4-5. 凍結基準の手続(実装より重い)

- `contracts/tenant_boundary/base-allowlist.json:19-21` の `frozen_projection.external_files` に
  **検査器本体**が入っている → **1 行変えるだけで凍結射影が動く**。
  `movement_policy.movement_triggers` に `pass_fail_mapping` が含まれ、
  **合否写像の変更も「基準を動かす」**と資産自身が宣言している
- 機械的に要求されるもの(`scripts/check_tenant_boundary_bypass.py:694-719`):
  履歴を**ちょうど 1 件**追加 / **`contract_revision` の更新が必須**(現在 13)/
  履歴の before/after の `frozen_projection_sha256` が実スナップショットと一致 /
  **動いていないのに履歴を足すと red** / **merge-base の既存履歴の変更・削除は red**
- `negative-fixtures.json` も自前の `baseline_control` を持つので**同様の手続が要る**

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**厳しくする側を緩和より先に入れる。** ステップ 1 は検査器に触れないので凍結射影が動かない。

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **到達可能性の導出器**を新規モジュールとして作る(検査器からは結線しない)。無向グラフ・dotted 優先の辺・相対 import の `node.level` 解決・動的アクセスの fail-closed | `[機械]` 新規単体テスト green(直接/推移/相対 import・`TYPE_CHECKING`・`from pkg import name` の 3 ケース・循環で停止)。`uv run python scripts/check_frozen_baselines.py` で**凍結射影が動いていない**こと |
| 2 | **資産へ導出規則を足す**: `base-allowlist.json` に `scope`(`anchor_path_prefixes` / `must_remain_on_surface` / `graph`)。`_strict_keys` の許可キーへ `scope` を追加。`contract_revision` 13 → 14 と履歴 1 件 | `[機械]` `check_frozen_baselines.py` green・`check_tenant_boundary_bypass.py` が develop で exit 0 `[手動]` **`scope` に導出結果(モジュール名の列挙)が 1 件も入っていない**ことを逐行確認 |
| 3 | **導出器を検査器本体へ取り込み、両版のレジーム写像を計算する(まだ判定は変えない)**。`scan_source` に `scope` を追加し**既定値はレジーム A** | `[機械]` 既存テスト全部 green(68 負例含む)。**`feature/domain-calc-dsl` で 719 件のまま**(= 挙動が変わっていない証明)。**develop でレジーム B が 0 モジュール** `[手動]` 既存 alias 解決へ手が入っていないことを diff で確認 |
| 4 | **負例ハーネスへ境界面エッジを 1 本**(4-4 (v)) | `[機械]` `:546` が 68 本すべて green のまま・`fixture_set_revision` が動いていない `[手動]` 追加モジュールが負例の期待値に影響する構文を含まないこと |
| 5 | **TB009 / TB011 を先に入れる**(収縮検査と境界面保持検査)+ 負例 `SCOPE_SHRINK_*` 2 本・`SCOPE_SURFACE_MUST_REMAIN`。`fixture_set_revision` + 履歴 1 件 | `[機械]` 新負例が red・既存 68 本と develop は green `[手動]` TB009 が「import を消した」以外で発火しないこと |
| 6 | **レジーム A を厳しくする**(4-4 (iii))+ 負例 `SCOPE_SURFACE_TIGHTENED` | `[機械]` **develop 全モジュールの全行走査で新規違反 0 件**(1 件でも出たら停止して判断) `[手動]` 縮めた免除が inventory 制約と矛盾しないこと |
| 7 | **レジーム B の緩和を入れる**(`:2963` と `:2924`)+ 残り負例(`SCOPE_B_*` 4 本・`SCOPE_ANCHOR_STRING_ONLY`・`SCOPE_DYNAMIC_GETATTR`) | `[機械]` develop exit 0 かつレジーム B が 0 モジュール。**`feature/domain-calc-dsl` で TB007 が 0 件(719 → 110)** `[手動]` 消えた 609 件が 4-1 の 2 分岐由来であること(メッセージ別集計で 607 + 2) |
| 8 | **条件 2 のパターン絞り込み**と `C2_GENERATION_IMPORT` の `generation_no` 化 | `[機械]` 条件 2 の負例 7 本が red・`GenerationError` / `MutationGeneration` 系が緑。**`feature/domain-calc-dsl` で 110 → 0 件(合計 719 → 0)** |
| 9 | **`tenant-boundary-enforcement/design.md` 6-0 へ射程を明文化**(未解決の既定値・通り抜けるもの・両建ての宣言) | `[手動]` 6-0 の既存の線引きと矛盾しないこと |
| 10 | **凍結基準の確定と PR 本文**(4-3 を転記) | `[機械]` `check_frozen_baselines.py` / `core_guard.py` / CI 一式 `[手動]` **コア領域の逐行確認**(設計書 `:377`) |

## 5. DoD(受け入れ基準)

- [ ] 条件 5・条件 2 の射程が判定され、**根拠が脅威モデル(`design.md` 6-0)へ接続**されている
- [ ] `feature/domain-calc-dsl` で **719 → 0 件**(または残る検出が真陽性として説明されている)
- [ ] **`develop` でレジーム B が 0 モジュール**(= 現存コードの検査が 1 件も緩まない)
- [ ] **何が通り抜けうるか**が PR 本文に明記されている(4-3 の 6 件 + 新しく引く線)
- [ ] **両建てが入っている**: TB009(収縮検査)・TB011(境界面保持)・レジーム A の厳格化
- [ ] **落ちてはいけないもの**(4-4)が負例で守られ、**再武装が実測で示されている**
- [ ] `contracts/tenant_boundary/` の管理資産を変えた場合、`contract_revision` と sha256 inventory が整合している
- [ ] pytest / ruff / ty green
- [ ] **コア領域(テナント分離)** → sol xhigh・敵対レビュー + **人間の逐行確認**

## 6. テスト計画

NFR-019 の種別では**単体**に属する(検査器自身のテスト)。ランタイムの越境テストは本タスクの射程外。

| 追加するもの | 種別 | 置き場 |
| --- | --- | --- |
| 到達可能性の導出器の単体テスト(直接・推移・相対・`TYPE_CHECKING`・`from pkg import name`・循環) | 単体 | `tests/test_check_tenant_boundary_bypass.py` |
| **辺の張り方の回帰**(dotted 優先。両方張るとルートパッケージが hub になることを負例で固定) | 単体 | 同上 |
| レジーム写像の両版計算(merge-base / HEAD) | 単体 | 同上 |
| グラフ未供給時に全モジュールがレジーム A になること | 単体 | 同上 |
| `SCOPE_B_*` 4 本 / `SCOPE_SHRINK_*` 2 本 / `SCOPE_ANCHOR_STRING_ONLY` / `SCOPE_SURFACE_MUST_REMAIN` / `SCOPE_DYNAMIC_GETATTR` / `SCOPE_SURFACE_TIGHTENED` | 負例 fixture | `tests/fixtures/tenant_boundary/negative/` + `negative-fixtures.json` |
| 条件 2 の `generation_no` 負例(既存 `C2_GENERATION_IMPORT` の更新) | 負例 fixture | 同上 |

**既存 68 負例・正例 5 件は exact-set で守られている**ので、増減はすべて資産と同時更新する。
**`scan_source` の `scope` 既定値をレジーム A にすることで、既存 68 本の単体走査は 1 本も変わらない。**
