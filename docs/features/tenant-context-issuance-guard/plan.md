---
feature: tenant-context-issuance-guard
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-10-06・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e693b75e6878136891fca40b09db799
branch: feature/tenant-context-issuance-guard
created: 2026-10-05
計画レビュー周回: 3        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: TenantContext の発行を専用モジュールへ機械的に封じ込める

## 1. 背景・目的

Notion タスク: [TSK-457](https://app.notion.com/p/3e693b75e6878136891fca40b09db799)(優先度 高・コア領域〔テナント分離〕)

TSK-440 は `scripts/check_tenant_boundary_bypass.py` の条件 5(TB007)の保証範囲を縮小した。当初はコア paths へ `backend/src/pitchlog/api/**` と `backend/src/pitchlog/services/**` を足して「残りは人間の逐行確認が担う」形にする予定だったが、**6.3-⑤ の敵対レビューで承認不可**となり撤回された。P0 の逐語(`../tenant-boundary-scope/plan.md:243-245`):

> `api/**` と `services/**` は、構築可能性ではなく「置かれそうな場所」を選んだヒューリスティックである。
> 保証外にした `registry[k].make_context(t)` は**配置場所に制約がない**ため、静的保証の縮小と釣り合う境界になっていない。

結果、TSK-440 は「**代償なしの保証縮小であり、人間が残余リスクを明示的に受容する案件**」として承認されている(同 `:259-260`)。本タスクはその見返りとして明示的に約束された**本来の解**である(同 `:267-275`・`../tenant-boundary-enforcement/design.md:492`)。

根本の事実: `backend/src/pitchlog/repositories/context.py` の `TenantContext.__init__` は公開で、実行時の防御がない。**静的 allowlist が唯一の防御**であり、緩めた分は機構でしか埋まらない。

**要件との対応**(典拠は [research.md](research.md) §7):

- **NFR-010 チーム間データ分離**(Must — 要件書 `:846-850`)。本タスクが手段を強める対象。ただし条文は**手段を指定していない**
- **FR-034 データ所有権制御**(Must — 同 `:599-645`)
- **NFR-010 はどの実装単位にも属さない横断要求**で、各単位の DoD へ「この横断要求を破っていない」を入れる(`../product-impl-unit-split/design.md:116` `:120-121`)
- **NFR-019**(同 `:923-933`)が唯一の実質的な制約。バックエンドのテストは pytest に集約する

調査の全典拠は [research.md](research.md)。人間の裁定 2 件は `../../worklog/2026-10-05-tenant-context-issuance-guard.md` が正。

## 2. スコープ

### やること

- `TenantContext` の公開 constructor を封じ、発行能力(capability)を持つ呼び出しからしか構築できなくする
- その発行能力を**名指せるモジュール**を、資産が列挙する集合(`allowed_test_modules | allowed_product_modules`)に縛る静的検査を足す
- **発行入口のシンボル**(U-M1 が作る発行関数)も同じ仕組みで保護する。許可外モジュールが**発行関数を import して registry へ転送する**経路を閉じる(敵対レビュー 1 周目 `P0`)
- 発行モジュール外からの構築・import・registry 登録を拒否することを**負例で示す**
- `repositories/binding.py` の強制点を他の 3 箇所と同じ強さへ揃え、**4 強制点の対称性を AST テストで固定**する
- 保証単位を**機構の境界そのもの**として宣言する(裁定 2)

### やらないこと

| やらないこと | 理由 |
| --- | --- |
| **発行専用モジュールの実体を作る** | **裁定 1** — U-M1 ステップ 8 の所有 |
| **`allowed_product_modules` への登録** | 同上。本タスクでは `[]` のまま |
| **0 件必須の分岐(`check_tenant_boundary_bypass.py:1178-1185`)の解除** | 同上。U-T1 が「製品の入口が開く前に allowlist へ製品モジュールが入ることを禁じる」と定める(`../tenant-boundary-enforcement/design.md:60`) |
| **設計書 7.7 の受理記録** | 裁定 1 — U-M1 ステップ 8 の所有 |
| **コア paths(`.claude/core-areas.json`)への追加** | 触る全ファイルが既存 glob に該当する。**1 行も足さない**(§4-5) |
| **TB008 のような新しい検査コードの新設** | 裁定 5。capability 名の保護だけで DoD の「import・registry 登録の拒否」が満たされる(§4-3) |
| **既存の逐語同文ブロック(4 箇所)の変更** | TSK-440 の合格条件。新ブロックを**隣に追補**する |
| **`design.md` 6-0「守らないもの」1〜5 の撤回** | 静的検査の保証範囲の話であり、実行時機構はその射程を変えない |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `backend/src/pitchlog/repositories/context.py` | capability 型・私有 sentinel・`__init__` 署名・docstring の**追補** | PR レビュー |
| `backend/src/pitchlog/repositories/binding.py` | exact 型検査 + 発行証跡へ揃える | PR レビュー |
| `scripts/check_tenant_boundary_bypass.py` | dataclass・`_strict_keys`・検証・返却・`_check_integrity_reference`・`_check_dynamic_call` | PR レビュー |
| `contracts/tenant_boundary/tenant-context-allowlist.json` | **4 欄追加**(発行能力のシンボルと許可シンボル / 発行入口のシンボルと許可シンボル)・`contract_revision` +1・`source_digest` 再計算 | 凍結受理(7.7) |
| `contracts/tenant_boundary/base-allowlist.json` | `allowed_symbols` の署名 pin 追随・`contract_revision` +1・**受理記録 1 件** | 凍結受理(7.7) |
| `contracts/tenant_boundary/negative-fixtures.json` | 負例 **3 件**(直接形のみ。発行入口の 2 本は台帳に載せず合成契約の単体テストで扱う — レビュー 2 周目 `P1`)・`fixture_set_revision` +1 | 凍結受理(7.7) |
| `contracts/tenant_boundary/census-baseline.json` | **`pass_fail_mapping.predicates[1].derivation` の一般化**(共通記号の行差の扱いを宣言へ足す — **裁定 6**)・識別値 +1 | 凍結受理(7.7) |
| `contracts/tenant_boundary/{cache-invalidation-contract,db-api-inventory,repository-contract,runtime-authz-contract}.json` | 識別値 +1 のみ(内容は不変) | 凍結受理(7.7) |
| `backend/src/pitchlog/repositories/tenant_context_contract.py` | **4 定数追加** + revision / digest 追随 | PR レビュー |
| `backend/src/pitchlog/repositories/repository_contract.py`・`backend/src/pitchlog/authz/runtime_contract.py` | revision / digest 追随のみ | PR レビュー |
| `backend/tests/test_authz_tenant_context.py` | `make_tenant_context` の新署名・封鎖の単体テスト・docstring の新 assert・`_generated_snapshot()` と stale 変異の 4 欄追随 | PR レビュー |
| `backend/tests/test_authz_tenant_binding.py` | 強制点の対称性の AST テスト・`binding.py` の挙動差の実行時テスト | PR レビュー |
| `tests/test_check_tenant_boundary_bypass.py` | 検査器の単体テスト・合成契約のテスト・`EXPECTED_NEGATIVE_IDS` に 3 件 | PR レビュー |
| `tests/fixtures/tenant_boundary/positive/pitchlog/repositories/context.py` | 署名追随 | PR レビュー |
| `tests/test_census_baseline_check.py` | `_measured_allowlist_suppression` の一般化と、共通行の変異 3 ケースの作り直し(**裁定 6**) | PR レビュー |
| `tests/fixtures/frozen-archive-cases/manifest.json` | `corpus_inputs.digest` の再 pin 1 行のみ(`pinned_prefixes`・`files`・`trees`・`cases` は不変) | PR レビュー |
| `tests/fixtures/tenant_boundary/negative/pitchlog/services/c5_context_{registry_issuer,capability_import,capability_getattr}.py` | **新設 3**(発行入口の 2 件は fixture ではなく合成契約の単体テストで扱う) | PR レビュー |
| `docs/features/tenant-boundary-enforcement/design.md` | 1-1 と 6-0 へ保証単位ブロックを**追補**、`:492` に本タスクの到達点 | /finalize-doc |
| `docs/features/tenant-context-issuance-guard/design.md` | **新設**(保証単位・採らなかった案・申し送り) | 計画ゲート |

### 反映なし(明示)

| 正本 | 理由 |
| --- | --- |
| `.claude/core-areas.json` | **1 行も足さない。** 本タスクが変更する**コード・契約・テスト**が既存 glob(`backend/src/pitchlog/repositories/*`・`backend/tests/test_authz*.py`・`scripts/check_tenant_boundary_bypass.py`・`contracts/tenant_boundary/*`・`tests/fixtures/tenant_boundary/*`・`tests/test_check_tenant_boundary_bypass.py`)に該当するため**追加は 0 件**(追補する設計文書と worklog はコア paths に該当しない)。DoD の「ディレクトリ全体を足さない」を構造的に満たし、6.3-⑤ の P0 を踏めない |
| `contracts/tenant_boundary/frozen-inputs.json` | 射影に検査器を含まない唯一の資産。識別値は据え置き、受理記録には同値で列挙する |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | NFR-010 / FR-034 は性質を Must で要求し**手段を指定しない**([research.md](research.md) §7)。NFR-019 も改訂不要 |
| `docs/design/data-model.md` | 裁定 A-3 は不変。移行は発行モジュールの利用者ではない(同 §3)。`:16` の γ 帰属の現行化は**射程外 — 申し送り** |
| `docs/adr/` | **新設しない**。決定の置き場は `../tenant-boundary-enforcement/design.md` 1-1 / 6-0 で、本タスクはそこへ 1 ブロック足して完結する。既存 ADR 4 本はいずれも横断的な方式選択(モデル選定・フロントエンド・ドメイン計算方式・マージゲート) |
| `docs/features/tenant-boundary-scope/verification-sheet.md` | TSK-440 の受理記録。閉じた単位の合格シートは動かさない |
| `docs/development/dev-harness-design-2026-08-07.md` 7.7 | 7.7 の**受理記録の作成**は U-M1 ステップ 8(裁定 1)。本タスクは凍結資産の受理記録を書くが、7.7 の手続き文書自体は変えない |
| `docs/features/ua1-auth-app-layer/plan.md` | `:76` が既に本タスクを申し送り済み。**このファイルは未マージの `feature/ua1-auth-app-layer` 上にあり、本 worktree には存在しない**(レビュー F7)。**U-M1 ステップ 8 の現物計画との逐語突合は未確認**と記す。`../ua1-team-auth/design.md:264`・同 `plan.md:110`・`../../design/data-model.md:16` が生成と登録を γ に割り当てたままなのは、**裁定 b'(2026-10-05)による上書き前の記述**であり、現行化は射程外 — 申し送り |

## 4. 実装方針

調査の典拠は [research.md](research.md) が正(/investigate・2026-10-05)。本節では結論だけを引き、内容を複製しない。

### 4-0. 重さ分類の根拠

**コア領域**。`.claude/core-areas.json` の `tenant-isolation` が列挙する paths(`backend/src/pitchlog/repositories/*`・`scripts/check_tenant_boundary_bypass.py`・`contracts/tenant_boundary/*`・`tests/fixtures/tenant_boundary/*`)を触る。CLAUDE.md の列挙「テナント分離」に該当する。
→ ADR-001 により **sol xhigh・敵対レビュー必須・人間の逐行確認必須**。

### 4-1. 確定している裁定(動かさない)

| # | 裁定 | 出所 |
| --- | --- | --- |
| 1 | **射程は「機構と検査器まで」**。発行モジュールの実体・登録・生成箇所・7.7 の受理記録は U-M1 ステップ 8 | 人間・2026-10-05・山田正輝 |
| 2 | **DoD は機構の境界で書き直す**。「同一プロセス内の任意コードに対する信頼境界ではない」の宣言は撤回しない | 同上 |
| 3 | **`__init__` に capability 引数**を採る(`__new__` 封鎖ではない) | 人間・2026-10-05 |
| 4 | **`binding.py` の非対称を閉じる** | 同上 |
| 5 | **検査規則は capability 名の保護のみ**(TB008 を新設しない) | 同上 |
| 6 | **センサス基準の反実仮想導出を記号単位の行差へ一般化する**(`anchor` の繰り上げも `__new__` 封鎖への差し替えも採らない) | 人間・2026-10-07・山田正輝 |

### 4-2. 機構 — 発行能力を「名前」にして、名指せる場所を縛る

`backend/src/pitchlog/repositories/context.py` に発行能力の型と**モジュール私有の単一実体**を置き、`TenantContext.__init__` がその実体を実引数に要求する(identity 検査)。前例は `repositories/transaction.py:28` `:63-66` の `_HANDLE_CREATION_TOKEN`(sentinel + 二重要求)と同形。

**3 枚の線を分けて置く**:

| 線 | 何で守るか | 守らないもの |
| --- | --- | --- |
| **実行時** | identity(`is` 比較)。同型の別実体でも落ちる | 能力を受け取った後のコード |
| **静的** | 名前。発行能力を名指せるモジュールが閉集合 | 変更行の外(差分検査の射程) |
| **型** | 注釈。`ty` と読み手のためだけにある | **守っていない**(型は信用しない) |

`__init__` 据え置きを採る理由(裁定 3): 検査器 `:4540` が `TenantContext.__init__` を**ハードコードで免除**しており、資産の `integrity_proof_factory_allowed_symbols` も同シンボルを指す。`__new__` 封鎖だとこの 2 つを追加で動かす。

### 4-3. 検査器 — 守る名前を 2 つ増やす

`_check_integrity_reference`(`scripts/check_tenant_boundary_bypass.py:4732`)の `protected` を 2 件から **4 件**にする。**許可条件は 4 件それぞれ別に持たせる**(一律に一般化しない — レビュー F3・F4):

| 保護対象 | 許可条件 | 変更 |
| --- | --- | --- |
| 発行証跡の秘密 | 許可シンボルのみ(現状維持) | **変えない** |
| 発行証跡の導出関数 | 許可シンボルのみ(現状維持) | **変えない** |
| **発行能力(新)** | 許可シンボル **または** 許可モジュール(`allowed_test_modules \| allowed_product_modules`) | 新規 |
| **発行入口(新)** | 同上。**値が空のあいだは判定しない**(U-M1 が自分の発行関数名を入れるまで不活性) | 新規 |

既存 2 件の許可条件を広げると、許可テストモジュール内の未許可関数から秘密・導出関数を参照できるようになる。**既存 2 件は 1 文字も変えない。**

この関数は `visit_ImportFrom`(`:4877`)・`visit_Name`(Load 文脈・`:5084`)・`visit_Attribute`(`:5096`)の 3 入口から呼ばれる(**実測確認済み**)。したがって:

- **import の拒否** → `visit_ImportFrom` が拾う
- **registry 登録の拒否** → `registry["k"] = <capability>` の右辺は Load 文脈なので `visit_Name` が拾う
- **発行入口の直接の転送の拒否** → 許可外モジュールが `from <発行モジュール> import <発行関数>` と書けば `visit_ImportFrom` が、`registry["k"] = <発行関数>` と書けば `visit_Name` が拾う(敵対レビュー 1 周目 `P0`)

**ここで線を引く(敵対レビュー 2 周目 `P0` — 打ち切りの判断)**: 照合は**名前の直接比較**(完全修飾名または末尾名)であり、起源追跡はしない。したがって**許可モジュール側で別名に再公開した関数**(`exported = issue_tenant_context` としたうえで許可外から `from … import exported`)や、`getattr` で発行入口を取り出す形は**閉じない**。これは `design.md` 6-0「守らないもの 2」(構築シンボル以外の属性名で、再輸出写像でも解決できない callable を経由した構築)と**同じ射程**であり、**本タスクはその宣言を撤回しない**。保証文に明記する(§4-4 の 7)。

この線を引く理由: 「すべての抜け道を条文の閉じた一覧で捉えようとすると、敵対レビューが 1 周に 1 件ずつ出し続けて終わらない」(`../../development/harness-evaluation.md:4014`)。U-T1 のテナント境界が同台帳の 4 例目で、**有効だった手当ては「脅威モデルを設計書へ明文化して線を引いた」**こと(同 `:4040-4054`)。本タスクも 1 周目「import 転送」→ 2 周目「別名再公開」と同型の指摘が続いたため、**列挙ではなく線で閉じる**。
- **動的参照** → `_check_dynamic_call` の `getattr` 判定に発行能力を足す。ただし現行は保護名の末尾一致で**無条件に** TB007 を出すため、1 要素足すだけだと**許可モジュールからの `getattr` も拒否してしまう**(レビュー F3)。発行能力の行にだけ許可モジュール判定を掛け、既存 2 件の判定は変えない

**発行入口の 2 欄の契約**(2 周目 `P1` — ローダに明記する):

- **両欄が空のあいだは不活性**。発行入口の判定を一切行わない(本タスクの状態)
- **入口を設定したら完全修飾名を要求**する(既存の `constructor_symbol` と同じ検査)
- **片方だけの設定は拒否**する(`ContractError`)

既存の欄は非空を要求するものがあるため、**空を許す欄であることをローダの検証に明示的に書く**。`_strict_keys` はキーの exact-set しか見ない。

**新しい検出ロジックは 1 行も書かない。**

**U-M1 ステップ 8 に渡るもの(正確に書く — レビュー F2)**: 本タスクが足す**参照規則は登録値を読むだけ**なので、`allowed_product_modules` に値が入れば自動で開く。しかし **U-M1 が「資産に 1 行足すだけ」で済むわけではない**。U-M1 は少なくとも次を行う:

1. `check_tenant_boundary_bypass.py:1178-1185` の **0 件必須の分岐の解除**(資産の編集だけでは解除できない)
2. その拒否を固定しているテスト `tests/test_check_tenant_boundary_bypass.py:5828` の改訂
3. 資産の `source_digest` 再計算・`contract_revision` 繰り上げ・配布モジュールの追随
4. 凍結資産の受理記録(検査器を触るので 8 本 +1)と設計書 7.7 の手続き
5. 発行専用モジュールの実体と `PRODUCT_APPLICATION_PATHS` への追加

これらはすべて裁定 1 が U-M1 ステップ 8 へ割り当てた項目である。**本計画は「U-M1 は検査器を再度触らずに開ける」とは主張しない。**

**U-M1 への制約(申し送り — 2 周目 `P1`)**: 照合は**末尾名でも一致する**ため、発行関数の名前が他モジュールの無関係な同名の関数・変数と衝突すると誤検出になる。U-M1 は発行関数に**リポジトリ内で一意な固有名**を選び、設定時に**全行走査で衝突 0 件**を確認すること。衝突検査をステップ 8 の合格条件に入れる。

### 4-4. 保証単位の宣言(裁定 2)

既存の 4 箇所の逐語同文ブロックには**一切触れず**、新しいブロックを隣に追補する。

> **保証するもの**
> 1. 有効な `TenantContext` は、`pitchlog.repositories.context` が私有する**単一の発行能力**を実引数に受けた構築からしか得られない。能力を渡さない構築・同型の別実体を渡した構築は実行時に失敗する
> 2. 発行能力を名指すコードは、資産が列挙するモジュール(`allowed_test_modules | allowed_product_modules`)**または資産が列挙する許可シンボル**の中にしか置けない(許可シンボルは `context.py` 自身の内部参照のための例外 — 下記 8)。import・属性参照・`getattr` のいずれでも、それ以外からの名指しは TB007 になる
> 3. **発行入口のシンボル**(資産が名指す発行関数)も同じ制限を受ける。したがって allowlist 外のモジュールは、発行能力を名指すことも、**発行関数をその名前で import して registry へ登録することもできない**。本単位の時点で `allowed_product_modules` と発行入口はいずれも空である。**この状態で保証されるのは、(i) 製品モジュールが許可資産に 1 件も登録されていないことと、(ii) 検査対象行における発行能力の直接参照を静的に拒否することの 2 つ**である。**発行入口の判定は 2 欄が空のあいだ働かない** — U-M1 が値を設定した時点から有効になる。いずれも同一プロセス内の任意コードに対する実行時の不可能性ではない(下記 4)、かつ名前が直接現れない転送には及ばない(下記 7)
>
> **保証しないもの**(既存宣言と同じ線)
> 4. **同一プロセス内で発行能力の導出経路へ到達する任意コード**。発行能力は同一プロセス内の攻撃者に対する信頼境界ではない。これは発行証跡について既に置いた宣言と同じ境界であり、本機構はそれを**撤回も縮小もしない**
> 5. **静的検査の母集団の外**。検査器が見るのは変更行であり、変更されない既存行は見ない
> 6. **構築された値の真正性**。従来どおり API 層(TSK-217 / U-A1)の責務
> 7. **名前が現れない転送**。**本タスクが追加する参照規則(発行能力・発行入口)**の照合は名前の直接比較(完全修飾名または末尾名)であり、起源追跡はしない。**許可モジュール側で別名に再公開した発行関数の持ち出し**、`getattr` による取り出し、`registry[k].make_context(t)` のように callable の由来が静的に解決できない呼び出しは**いずれも閉じない**。これは 6-0「守らないもの 2」と同じ射程であり、本機構はその宣言を**撤回しない**。**既存の条件 5 の保証は 1 文字も縮まない** — 構築シンボルについては再輸出写像による起源解決(1-1 / 6-0 の「赤にするもの (v)」)が従来どおり働く。限定が掛かるのは**今回追加する 2 件の参照規則だけ**である
> 8. **許可の単位**。発行能力と発行入口の許可は「許可シンボル **または** 許可モジュール」である。許可シンボルは `context.py` 自身の内部参照のためにあり、**モジュール単位の制限に 1 つだけ例外を開ける**(2 周目 `P1`)

**「`registry[k].make_context(t)` 形が閉じる」の定義**(DoD の 5 項目目 — **敵対レビュー 2 周目を受けて限定した**): 呼び出し行が赤くなることではない。**発行能力と発行入口を、allowlist 外のモジュールが直接その名前で名指せないこと**を指す。閉じる場所は呼び出し側ではなく名指す側である。

**閉じないものを同時に宣言する**: 別名で再公開された発行関数の持ち出し・`getattr` による取り出し・由来が静的に解決できない属性経由の呼び出し。これらは 6-0「守らないもの 2」の射程そのもので、**本タスクは撤回も縮小もしない**。

**なぜ列挙で閉じないか**: 「すべての抜け道」を条文の閉じた一覧で捉えようとすると敵対レビューが 1 周に 1 件ずつ出し続けて終わらない(`../../development/harness-evaluation.md:4014`。U-T1 テナント境界が 4 例目で、有効だった手当ては**脅威モデルを明文化して線を引いた**こと)。本タスクは**名前の直接比較という機構の境界をそのまま宣言**し、その外を保証外に置く。

`context.py` の docstring は**追補のみ**。`backend/tests/test_authz_tenant_context.py:95-104` は 5 つの部分文字列の `in` 判定なので、既存文を 1 文字も変えなければ落ちない(確認済み)。

### 4-5. コア paths を 1 行も足さない根拠

`scripts/core_guard.py` は `fnmatch.fnmatchcase` を使い `*` が `/` を跨ぐ。**本タスクが変更するコード・契約・テストは、いずれも既存 glob に該当する**(`backend/src/pitchlog/repositories/*`・`backend/tests/test_authz*.py`・`scripts/check_tenant_boundary_bypass.py`・`contracts/tenant_boundary/*`・`tests/fixtures/tenant_boundary/*`・`tests/test_check_tenant_boundary_bypass.py`)。したがって**追加は 0 件**で、`AREA_PATH_ADDITIONS` の窓口も使わず、TSK-344 との順序調整も不要。

**正確に言うと**(レビュー F8): 追補する設計文書と worklog はコア paths に該当しない。また既存の `repositories/*` は本タスクの強制点以外のファイルも覆う。DoD の「強制点・検査器・テストだけが入っている」は、**既存 paths 全体の厳密な記述ではなく、本タスクが 1 行も足さないこと**で満たす。6.3-⑤ で承認不可になった形(ディレクトリ全体の追加)を構造的に踏めない。

### 4-6. 凍結資産の扱い

検査器を 1 バイト変えると、凍結資産 9 本のうち **8 本の識別値を繰り上げる**必要がある(`scripts/frozen_history.py:1474-1482` が機械強制。`frozen-inputs.json` だけが射影に検査器を含まない)。記録は `base-allowlist.json` に 1 件(`history_authority: true` は同資産のみ)。配布モジュール 3 本の revision 追随も要る。

手続き上の注意([research.md](research.md) §6 — TSK-440 の実例):

- `change.after` は revision を上げた**後**の射影で算出する(revision 欄自身が射影に含まれる)
- `change.before` は **merge-base 側**の射影であって作業ツリーの更新前値ではない
- **承認が先** — 「逐行確認 → 承認 → 記録を書く → CI → マージ」。予約 marker(`未承認` `PENDING` `TODO` `TBD` `未定` `レビュー待ち`)は拒否される
- 凍結 SHA は**変異テストが走っていない状態で読む**

**既知の赤窓**: ステップ 1 で `base-allowlist.json` が動いた時点から、ステップ 7 まで `frozen_history` 系ゲートは赤(`射影が動いた資産は識別値の更新が必要`)。各ステップの合格条件はこのゲートを**対象外とする**。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **機構の実体**。`context.py` に発行能力の型・私有 sentinel・`__init__` の capability 必須化・docstring の追補。`contracts/tenant_boundary/base-allowlist.json` の署名 pin と正例 fixture `tests/fixtures/tenant_boundary/positive/pitchlog/repositories/context.py` を追随。`backend/tests/test_authz_tenant_context.py` の `make_tenant_context` を新署名へ、封鎖の単体テストと docstring の新 assert を追加 | `cd backend && uv run pytest` green / 能力なしの構築と同型の別実体を渡した構築がいずれも失敗 / `test_tenant_repository_product_definition_passes_bypass_scan` が `context.py` で violation 0 / `ruff check` `ty check` green / **凍結ゲートは対象外** |
| 2 | **契約資産に 4 欄**(発行能力のシンボルと許可シンボル / **発行入口のシンボルと許可シンボル** — 発行入口は空で置き、U-M1 が値を入れる)。検査器の dataclass(`:164-180`)・`_strict_keys`(`:1059-1079`)・検証・返却、配布モジュール `tenant_context_contract.py`、`backend/tests/test_authz_tenant_context.py:47-73` の `_generated_snapshot()` と stale 変異 parametrize を追随。**`source_digest` はここで 1 度追随させる**(欄を足すと digest が変わり、ローダが不一致を拒否するため — レビュー F5。`contract_revision` の繰り上げはステップ 7)。**規則はまだ接続しない** | `test_generated_allowlist_matches_asset` green / 新 4 欄の stale 変異が赤 / 全負例・正例・製品全行走査の結果が**前後で完全一致** / **凍結ゲートは対象外** |
| 3 | **検査器の新しい規則**。`_check_integrity_reference` の `protected` に **2 件**(発行能力・発行入口。許可はいずれも「シンボル or モジュール」。**発行入口は値が空なら判定しない**)、`_check_dynamic_call` の `getattr` 判定に発行能力を追加。既存 2 件の許可条件は**変えない**。検査器単体テストを `tests/test_check_tenant_boundary_bypass.py` に追加 | 既存 112 負例が全件従来どおり red / 未許可モジュールからの import・Load 参照・`getattr` が TB007 / `allowed_test_modules` のモジュールと `context.py` 内部が素通り / **合成契約で `allowed_product_modules` と発行入口に値を入れると、そのモジュールだけが発行能力と発行入口を名指せる**(U-M1 が開く形の先行検証)/ **両欄が空のあいだは発行入口の判定が一切働かない** / **片方だけ設定した契約が `ContractError` で拒否される** / **凍結ゲートは対象外** |
| 4 | **負例 3 件 + 発行入口の単体テスト 2 件**。負例台帳へ載せるのは発行能力の 3 件(`c5_context_{registry_issuer,capability_import,capability_getattr}.py`)だけにする。**発行入口の 2 件は負例台帳に載せない** — 負例ランナー 2 本はいずれも `load_contract(REPOSITORY_ROOT)` で**実契約**を読み、本タスクでは発行入口が空で不活性のため red にできない(2 周目 `P1`)。発行入口は**合成 `Contract` を渡す検査器単体テスト**で扱う | 負例ランナー 2 本が 3 件とも TB007 で red / **合成契約で発行入口に値を入れると、許可外モジュールからの直接 import と直接登録が TB007** / 既存負例が 1 本も緑化していない / **`fixture_set_revision` はまだ上げない** / **凍結ゲートは対象外** |
| 5 | **`binding.py` の強制点を exact 型 + 発行証跡へ揃え、4 強制点の対称性を AST テストで固定**。あわせて**挙動差を実行時テストで固定**する(レビュー F6 — AST の対称性だけでは拒否が実際に起きることを示せない) | **発見規則**(実測で確定 — 収束確認周): 「`backend/src/pitchlog/repositories/` 配下(**`context.py` を除く**)で、`TenantContext` 値の属性(`tenant_id` または `_integrity_proof`)を読むか `_has_valid_integrity_proof()` を呼ぶ関数」。この規則が拾うのは **5 関数**である。**宣言集合も 5 件**とし、内訳を分ける — **強制点 4 件**(`TenantRepositoryBase.execute` / `_tenant_transaction` / `_TenantTransactionScope.__enter__` / `_TenantTransaction.run`)と、**理由付きの免除 1 件**(`TenantRepositoryBase._execute_operation` — `context.tenant_id` をバインド引数に渡すが、`execute` からのみ到達し、そこで exact 型検査と証跡検査が済んでいる)。合格条件は ① 発見集合 == 宣言集合 ② **強制点 4 件がいずれも exact 型検査と発行証跡の検査を持つ** ③ 免除 1 件の呼び出し元が `execute` だけである ④ **5 つ目の強制点を足した変異で必ず落ちる** / 4 箇所すべてが exact 型検査と発行証跡の検査を持つ / **`_tenant_transaction` の直呼びで、派生型と証跡改竄がいずれも SQL 発行 0 件・期待メッセージで拒否される** / 既存 binding テストが**例外メッセージ逐語のまま** green / **凍結ゲートは対象外** |
| 6 | **正本の反映**。`docs/features/tenant-context-issuance-guard/design.md` 新設(保証単位・採らなかった案・申し送り)、`../tenant-boundary-enforcement/design.md` 1-1 と 6-0 へ保証単位ブロックを追補・`:492` を本タスクの到達点へ、worklog 追記 | **既存 4 箇所の逐語同文ブロックが `git diff` で 1 文字も動いていない** / 新ブロックが追補先で逐語同文 / `check_docs_status` ほか docs 系検査 green / **凍結ゲートは対象外** |
| 7 | **凍結資産の受理記録**(**人間の逐行確認・承認の後、かつ PR 作成の後** — 下記「ステップ 7 の実行順序」)。8 本の識別値 +1(`frozen-inputs.json` は据え置き・記録には同値で列挙)、`source_digest` 再計算、配布モジュール 3 本の revision / digest 追随、`base-allowlist.json` に受理記録 1 件、**`tests/fixtures/frozen-archive-cases/manifest.json` の `corpus_inputs.digest` 再 pin** | `/check` 全 green / `tests/test_frozen_*` green / `python scripts/check_tenant_boundary_bypass.py --base-ref origin/develop` が 0 件 / 予約 marker 不在 / 9 資産すべてが `previous_/new_baseline_identifiers` に列挙され `aspect` に `external_snapshots` を含む |

#### ステップ 1 の是正(**2026-10-07・裁定 6**)— 表の総数は動かさない

全件検証で、ステップ 1 の署名 pin の追随が `tests/test_census_baseline_check.py` の 8 件を赤にすることが判明した(develop では 48 passed)。原因はセンサス基準の反実仮想導出が **anchor に無いエントリの追加しか帰属できない**ことで、`base-allowlist.json` の**共通記号の行**を書き換えると入口で fail-closed になる。署名 pin を据え置く道は無い(`scripts/check_tenant_boundary_bypass.py:5114` `:5680-5692` が製品定義と pin の一致を要求する)。

**是正の射程**: `contracts/tenant_boundary/census-baseline.json` の `derivation` 宣言と `tests/test_census_baseline_check.py` の `_measured_allowlist_suppression` を、**共通記号の行差を帰属できる形へ一般化する**。

**コミットは `(ステップ 1/7 是正)`** とし、**実装ステップ表の総数 7 は動かさない**。総数を変えると既存 6 コミットの `/7` が `scripts/feature_status.py:517` で不整合になる(前例: `a1e5313d`「(ステップ 6/13 是正)」)。

#### ステップ 7 の実行順序(**実測で判明 — 2026-10-07**)

受理記録の `acceptance_id` は `owner/repository#number` で、`scripts/frozen_history.py:674-680` が **GitHub event からの導出値との一致**を要求する。したがって**記録は PR 作成の後にしか書けない**。本計画の初版は「ステップ 7 → /pr」の順で書いていたが、**実際の順序は次である**(前例: `ba1a02d6`「凍結基準の受理記録を足す — U-A1 β の認証の DB 層(PR #96) (ステップ 13/13)」):

1. 人間の逐行確認・承認(**2026-10-07 受領済み**)
2. /sync-docs → **/pr(PR 番号が確定する)**
3. ドライランで S(比較元 SHA)・H(HEAD)・D(受理後の射影)を求め、PR 本文へ載せる
4. 人間が S・H・D を受理する
5. **ステップ 7 のコミット**(識別値の繰り上げ・`source_digest`・配布 3 本・受理記録 1 件・**比較 corpus の digest 再 pin**)

**比較 corpus の digest の再 pin をステップ 7 に含める**: 本タスクは検査器と `contracts/tenant_boundary` を動かすので `tests/fixtures/frozen-archive-cases/manifest.json` の `corpus_inputs.digest` が必ず動く(現況 42 件の赤のうち 34 件がこれに連鎖する)。これは**設計どおりの発火**であり、前例 `6b787555`(「比較 corpus の digest を再導出し連鎖する 33 件を解消する」)が同じ手当てを取っている。触るのは `corpus_inputs.digest` の 1 行だけで、`pinned_prefixes`・`files`・`trees`・`cases` は変えない。

## 5. DoD(受け入れ基準)

Notion タスクの DoD を**裁定 2 の形で書き直したもの**(カードにもコメントで記録済み)。

- [ ] **発行能力を持たない構築が実行時に失敗する** — 能力を渡さない構築・同型の別実体を渡した構築のいずれも(§4-4 の 1)
- [ ] **発行能力を名指せるモジュールが、資産が列挙する集合に限られる** — import・属性参照・`getattr` の 3 経路すべてで(同 2)
- [ ] **発行入口のシンボルも同じ制限を受け、許可外モジュールが発行関数を「その名前で」import して registry へ登録できない**(同 3 — 敵対レビュー 1 周目 `P0` の是正)
- [ ] **合法な発行コードを専用モジュールへ移しただけでは閉じない**ことを踏まえた設計になっている — 公開 constructor が能力を要求する形で閉じている
- [ ] **TSK-440 が保証外にした `registry[k].make_context(t)` 形について、この機構が閉じる範囲と閉じない範囲が負例で示されている** — 閉じる = 発行能力と発行入口を allowlist 外が**直接その名前で名指せない**。閉じない = 別名での再公開・`getattr`・由来が解決できない属性経由(6-0「守らないもの 2」の射程。**撤回しない**)。**両方をテストで固定している**
- [ ] **保証しない範囲が宣言されている**(同 4〜7)。既存宣言と同じ線を引き、撤回も縮小もしていない
- [ ] **強制点・検査器・テストだけがコア paths に入っている** — 本タスクは `.claude/core-areas.json` を**1 行も変えない**(§4-5)
- [ ] **4 強制点の対称性が AST テストで固定されている**
- [ ] **`allowed_product_modules` は `[]` のまま**、0 件必須の分岐は解除していない(裁定 1)
- [ ] 既存 4 箇所の逐語同文ブロックが 1 文字も動いていない
- [ ] pytest / ruff / ty green

## 6. テスト計画

バックエンドは **pytest に集約**(NFR-019 柱書 — 要件書 `:925`)。

**種別の判定**:

| 種別 | 判定 | 根拠 |
| --- | --- | --- |
| (a) クライアント/サーバー一致性 | **対象外** | NFR-018 の列挙(状況判定・座標変換・捕球選手推定・成績集計の前処理・終了判定 — 要件書 `:892`)に `TenantContext` は含まれない |
| (b) 越境アクセステスト | **未発効** | 本タスクは経路を作らない(`allowed_product_modules` は `[]`)。ただし**未発効は網羅の免除ではない**(同 `:933`)。列挙された組合せを 1 件も減らさず、U-M1 へ申し送る |
| (c) E2E | 対象外 | 入口が存在しない |
| (d) 故障系 | 対象外 | 対象は同期プロトコル。本タスクと交差しない |

**追加するテスト**:

| 置き場 | 種別 | 内容 |
| --- | --- | --- |
| `backend/tests/test_authz_tenant_context.py` | 単体 | 能力なしの構築が失敗 / 同型の別実体が失敗 / 許可経路の発行が有効な証跡を持つ(既存の改竄検出テストが依然 green)/ docstring の**既存 5 逐語が残り**新語が入る / 発行能力の型が `@final` |
| 同上 | 一致性(資産↔配布) | 新 4 欄が配布モジュールと一致 / 新 4 欄の stale 変異が赤 |
| `backend/tests/test_authz_tenant_binding.py` | 構造(AST) | **強制点の対称性**。発見規則(`repositories/` 配下・`context.py` を除く・`TenantContext` 値の属性を読むか `_has_valid_integrity_proof()` を呼ぶ)が拾う **5 関数**と宣言集合(強制点 4 + 理由付き免除 1 = `_execute_operation`)の exact-set 一致 / 強制点 4 件が exact 型検査と発行証跡の検査を持つ / 免除 1 件の呼び出し元が `execute` だけ / **5 つ目を足した変異で落ちる**(レビュー F9・2 周目 `P1`・3 周目・収束確認周) |
| `backend/tests/`(実行時負例) | 単体 | 発行能力を持たない転送経路からの構築が失敗することを実行時に示す(**静的には赤にできない形**であることを docstring に明記)|
| `backend/tests/test_authz_tenant_binding.py` | 単体(挙動) | `_tenant_transaction` の直呼びで、派生型と証跡改竄が **SQL 発行 0 件**で拒否される(ステップ 5 の挙動差の固定) |
| `tests/test_check_tenant_boundary_bypass.py` | 負例(台帳) | 新負例 **3 本**が red(`EXPECTED_NEGATIVE_IDS` の exact-set)/ 未許可モジュールの 3 経路(import・Load 参照・`getattr`)が TB007 |
| 同上 | 単体(合成契約) | 発行入口に値を入れた合成 `Contract` で、許可外からの**直接 import と直接登録**が TB007 / 許可モジュールは素通り / **両欄が空なら判定が働かない** / **片方だけの設定が `ContractError`** |
| 同上 | 保証外の明示 | **別名で再公開した発行関数の持ち出しは red にならない**ことをテストで固定し、docstring に「6-0 守らないもの 2 の射程であり意図的に閉じていない」と書く(2 周目 `P0` の線引き) |
| 同上 | 回帰(既存 2 件) | **許可テストモジュール内の未許可関数から発行証跡の秘密・導出関数を参照すると依然 red**(既存 2 件の許可条件を広げていないことの証明 — レビュー F4) |
| 同上 | 回帰 | **既存 TB007 負例が 1 本も緑化していない** / 正例 fixture 全体 green / 製品全行走査 green(新規則が自分自身を赤にしないことの機械証明) |

**DB テスト**: 共有開発 DB は消失しているため、必要なら使い捨ての postgres を立てて CI と同じ形で DSN を向ける。
