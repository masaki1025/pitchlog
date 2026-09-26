---
feature: tenant-session-supply
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e593b75e687817eb0caec8f93d11be5
branch: feature/tenant-session-supply
created: 2026-09-26
計画レビュー周回: 0        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: TenantRepositoryBase._session を満たす Session の供給(TSK-444 / TSK-424 PR C)

## 1. 背景・目的

**Notion**: [TSK-444](https://app.notion.com/p/3e593b75e687817eb0caec8f93d11be5)(優先度 **高**)
**計画段階の調査**: [research.md](research.md)。**本書が事実を述べるときは正本・資産を直接引く**

> **行番号の基準**: 断りのない限り **`origin/develop` = `b4ae7394`** 時点。確認は `git show b4ae7394:<path>`。

**DB を使う全単位が本タスクを待っている。** `backend/src` に `sessionmaker` / `Session(` は **0 件**で、
`TenantRepositoryBase._session` は抽象プロパティのまま満たす手段が公開されていない
(`backend/src/pitchlog/repositories/base.py:155-158`)。**製品コードに `TenantRepositoryBase` のサブクラスは 0 件**。

### 複数 operation を 1 トランザクションで回す必要は、正本が既に要求している

| 典拠 | 要求 |
| --- | --- |
| 要件書 `:303`(FR-012) | べき等キー記録・イベント保存・prefix 更新・状態遷移が**単一の DB トランザクションで確定する** |
| 要件書 `:391`(FR-018) | **紐づけ判定と削除が同一トランザクション**で行われ、**判定後に紐づいた場合は失敗する** |
| `../../design/data-model.md:1757-1759`(FR-041) | **上限検査の前にグループ行を排他ロックし挿入まで保持**、**または `SERIALIZABLE` + 再試行** |
| `../../design/sync-protocol.md:1258-1264` | **P2 = T1・T2・T3・T4・T5・T6 の 6 要素**を 1 トランザクション |

現行は **1 呼び出し = 1 トランザクション**(`base.py:194` の `with _tenant_transaction(...)` が
`_execute_operation` の内側)なので、**どれも満たせない**。

### 【調査で覆った与件】禁止ではなく未実装だった

着手時は「U-T1 が 1 束縛 1 文を課している」と見ていたが、**そういう条文も検査も存在しない**。

- `../tenant-boundary-enforcement/plan.md:173` ①「発行 SQL **列**の先頭が束縛文」— **列**と書いており件数の上限が無い
- `../tenant-boundary-enforcement/design.md:403`「**束縛より前に**他の SQL が出ないこと」— 制約は**前だけ**
- **既存の合格テストが 1 束縛 2 文を正例として固定**している
  (`backend/tests/test_authz_tenant_binding.py:1226`。テスト名は **`..._is_first_...`** であって `is_only` ではない)

**矛盾しているのは条文ではなく実装形**であり、U-T1 が射程を絞った結果の**未実装**である。

## 2. スコープ

### やること

1. **`_session` を満たす Session の供給**を製品コードへ置く
2. **複数の登録済み operation を 1 トランザクションで実行する単位**を提供する
   (**1 回の束縛の内側で複数 operation** — 束縛を 2 回行う形は取れない。4-2)
3. **`allowed_symbols`(凍結基準)への追加**を 7.7-2 に適合する形で記録する
4. **`repository-contract.json` の `public_surface`** の変更を正本へ反映する

### やらないこと

| 項目 | 行き先・理由 |
| --- | --- |
| **FR-018 / FR-039 / FR-017 の述語 SQL と入口の実装** | **U-M1(TSK-393)**。FR-015/017/018/039 の主所有は U-M1(`../product-impl-unit-split/design.md:75`)。本タスクは**機構だけ**を提供する(4-1 の裁定 1) |
| **capability の登録**(`PRODUCT_CAPABILITY_IDS` を空でなくする) | **経路を持つ単位**(`../product-authz-surface/plan.md:42` ★7)。本タスクは空のまま残す |
| **`FOR UPDATE` を capability のノード型へ入れること** | **採らない**(4-1 の裁定 3)。`SERIALIZABLE` + 再試行を機構側で提供する |
| **`TenantContext` の生成を製品モジュールへ開くこと** | **U-A1(TSK-217)**。`tenant-context-allowlist.json` の `allowed_product_modules` は `[]` のまま |
| **一覧経路・ページング** | **U-01 の所有**(`../tenant-boundary-enforcement/plan.md:174`) |
| **同期プロトコルの T1〜T9 境界の実装** | **U-S1 / 同期側**。本タスクは「6 要素を 1 トランザクションに載せられる機構」までで、**経路ごとの境界は決めない** |
| **`insert` / `update` の operation token の登録形式** | **それを開く単位が registry と一緒に定める**(`../product-authz-surface/design.md:618`) |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/requirements/` | **反映なし**。本タスクは FR を実装しない(2 節) | — |
| `docs/design/data-model.md` | **反映なし**。3-3 節の規律(`:318-327`)を**守る側**であり変えない | — |
| `docs/design/sync-protocol.md` | **反映なし**。8-1 の境界は同期側の所有 | — |
| `docs/adr/` | **新設なし**。既決の制約の実装であり新しい決定を持たない(行ロック方式は `data-model.md:1760` が「実装の判断」と明示済み) | — |
| **`contracts/tenant_boundary/repository-contract.json`** | `public_surface` へ**トランザクション単位の入口**を追加。`contract_revision` `4` → `5`・`source_digest` 更新 | **コア領域**(`tenant-isolation`)→ 敵対レビュー + 人間の逐行確認 |
| **`contracts/tenant_boundary/base-allowlist.json`** | `allowed_symbols` へ**供給シンボルとトランザクション単位**を追加。`contract_revision` `15` → `16`。**v2 履歴を 1 件追記** | **凍結基準**(7.7)+ 同上 |
| **`contracts/tenant_boundary/db-api-inventory.json`** | 新シンボルが使う API を `allowed_api_ids` に載せるため**触る場合のみ**。触ったら allowlist の `inventory.sha256` も更新(`base-allowlist.json:799-803`) | 同上 |
| **`contracts/tenant_boundary/history-snapshots/`** | v2 記録の content-addressed snapshot を追加(追記専用) | 同上 |
| `docs/README.md` | **反映なし**(正本の新設・版繰り上げが無い) | — |

**正本体系外だが同一 PR で更新するもの**: `backend/src/pitchlog/repositories/*`・`backend/src/pitchlog/repositories/repository_contract.py`(生成モジュール)・`tests/fixtures/tenant_boundary/positive/*`・`backend/tests/*`・`tests/test_check_tenant_boundary_bypass.py`。

## 4. 実装方針

**重さ分類 = コア領域**。`backend/src/pitchlog/repositories/*` と `contracts/tenant_boundary/*` は
`tenant-isolation` のコア paths。**敵対レビュー + 人間の逐行確認が必須**(設計書 6.3)。
加えて **`base-allowlist.json` は凍結基準**なので 7.7 の更新経路に載る。

詳細な API 形・束縛ライフサイクル・シーケンスは [design.md](design.md) に分離する。

### 4-1. 本タスクで決めること(裁定)

| # | 事項 | 決定 | 根拠 |
| --- | --- | --- | --- |
| **1** | **FR-018 の述語 SQL とロックを誰が決めるか** | **機構は本タスク / 述語 SQL と入口は U-M1**。`data-model.md:2033`「具体的なロック方式・SQL は実装計画へ送る」の**委譲先が正本に書かれていない**ため、ここで線を引く | FR-015/017/018/039 の主所有は U-M1(`../product-impl-unit-split/design.md:75`)。本タスクは `tenant-boundary` 基盤側(`../tenant-boundary-baseline/plan.md:38`) |
| **2** | **複数 operation の束ね方** | **1 回の `_tenant_transaction` の内側で、登録済み operation を順に実行して 1 回で commit する**。束縛はトランザクション単位で 1 回・先頭の文 | `binding.py:60-61` がキーの存在だけで再束縛を拒否し、**印を消すコードがリポジトリ全体に無い**(実測)。束縛 2 回の形は取れない |
| **3** | **FR-018 の並行性 — 行ロックか `SERIALIZABLE` か** | **`SERIALIZABLE` + 再試行を機構として提供し、`FOR UPDATE` は capability のノード型へ入れない** | 正本が 2 案を同格で示し「**どちらを採るかは実装の判断**」(`data-model.md:1760`)。`FOR UPDATE` 案は `capability_registration.py` の `_ALLOWED_NODE_TYPES`(**マージ済み A1 の資産**)を広げ、かつ「ロック対象が宣言した 1 表と一致するか」の検査を新設することになる。**再試行はトランザクション単位の層で表現でき、capability の閉世界を触らない** |
| **4** | **「1 operation = 1 表」** | **緩めない**。複数表の不変条件は、1 表ずつの operation を同じトランザクションで順に実行して満たす | `capability_registration.py:1256-1257` が exact-set 比較。**1 トランザクションあたりの operation 数への制約は条文に無い**(調査)→ 本タスクと直交 |
| **5** | **分離レベルの既定値** | **既定は変えない**。`SERIALIZABLE` は**トランザクション単位が明示的に要求したときだけ**適用する | 分離レベルを定めた条文が**どこにも無い**(要件書に `分離レベル` 0 件)。既定を動かすと射程外への影響が読めない |
| **6** | **savepoint / `begin_nested`** | **使わない**。採否の判断材料が正本に無く、束縛の先頭性との関係も未定義 | **言及なし**(`db-api-inventory.json:883` に API 登録があるだけ) |

### 4-2. 最初にぶつかる制約(実測)

**1 つの `Session` は生涯 1 回しか束縛できない。** `_BOUND_TENANT_INFO_KEY` の全出現は 3 行だけ:

```
binding.py:14  定数定義  /  binding.py:60  存在チェック(拒否)  /  binding.py:65  書き込み
```

**`pop` / `del` / クリアは `backend/` `tests/` のいずれにも存在しない**(実測)。
しかも `:60` は **tenant_id を比較せずキーの存在だけ**で拒否するので、**同一テナントの再入も落ちる**。

→ **トランザクション単位は「1 Session = 1 トランザクション = 1 束縛 = N operation」の形にする。**
Session の再利用を許す設計(印を消す)は**取らない** — `data-model.md:326-327` が
「リクエストごとに Session を作り、テナント横断・リクエスト横断で共有しない」と定めているため。

### 4-3. 【要注意】変異テストが実ソースを literal で参照している

`tests/test_check_tenant_boundary_bypass.py:644-652` は **`backend/src` の実ソースを文字列置換**して変異を作る:

```python
source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
mutated = source.replace("            execution_result = self._session.execute(\n", ...)
```

**アンカー文字列がソースから消えると `assert mutated != source` が red になる。**
`base.py` の当該行を触る本タスクは、**この更新が不可避**(ステップ 8)。

### 4-4. 承認記録の出所を着手前に決める

**TSK-446 では承認記録の出所が取れず、敵対レビューが 3 周連続で P0 を出した。**
今回は **TSK-431 の 7C(PR #78・マージ済み)が機械強制**している:

```
scripts/frozen_history.py:39-41   予約 marker を拒否 {"PENDING","TODO","TBD","未承認","未定","レビュー待ち"}
scripts/frozen_history.py:1521    approved_by は非空・approved_on は実在する ISO 日付
```

**プレースホルダは書けない。** よって**ステップ 1 で出所を確定**し、worklog へ記録してから実装に入る。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**各ステップの合格判定は「全件実行」で行う**(TSK-446 の 2 周目の教訓 — 絞り込み実行では 34 本の red を見落とした)。
**総数が変わりうるためステップ記法に `/<N>` を書かない**(設計書 6.1 の厳密文法③)。

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **承認記録の出所を確定し、リポジトリへ記録する** — `allowed_symbols` を動かす前提。worklog へ取得元・方式を書く | worklog に**逐語転記できる出所**が記録されている。`frozen_history.py:39-41` の予約 marker に当たらない形であること |
| 2 | **負例テストを先に置く** — ① 束縛が先頭でない ② 公開面が exact-set から外れた ③ 未登録 token を混ぜた ④ 異なる `TenantContext` を同一トランザクションへ混ぜた ⑤ `SERIALIZABLE` 要求時に再試行しない | **5 種すべてが red**。red の出力を worklog へ**実出力つきで**残す(TSK-446 の 3 周目 P1-4 の教訓) |
| 3 | **Session 供給モジュールを追加する** — `backend/src/pitchlog/repositories/session.py`(新設)。`create_database_engine()` の `Engine` からリクエスト単位の `Session` を作る。**生の `Session` を返さない**形にする | `backend/src` に Session 生成が 1 件入る。**公開面 exact-set のテストが red のまま**(ステップ 5 で資産を合わせる) |
| 4 | **トランザクション単位を追加する** — 1 回の束縛の内側で登録済み operation を順に実行し 1 回で commit する入口。`SERIALIZABLE` + 再試行を要求できる形 | ステップ 2 の 5 種が **green**。**期待失敗**: 公開面 exact-set・生成モジュール一致・`allowed_symbols` 未登録による TB005 は **red のまま** |
| 5 | **契約資産と生成モジュールを更新する** — `repository-contract.json` の `public_surface` + `contract_revision` + `source_digest`、`repository_contract.py` | 生成モジュール ≡ 資産のテストが green。**期待失敗**: TB005 と凍結基準は red のまま |
| 6 | **`allowed_symbols` へ登録し、正例 fixture を足す** — `base-allowlist.json` + `tests/fixtures/tenant_boundary/positive/`。`db-api-inventory.json` を触るなら `inventory.sha256` も | 迂回検査(`scripts/check_tenant_boundary_bypass.py`)が green。**期待失敗**: 凍結基準の履歴未追記で red |
| 7 | **凍結基準の履歴を v2 形式で追記する** — 9 キー exact-set・7 資産の新旧識別値・content-addressed snapshot。**承認記録はステップ 1 の出所から逐語転記** | `scripts/frozen_history.py` の検査が green。**同一受理で 2 件追記は red** であることを確認 |
| 8 | **変異テストの literal アンカーを更新する** — `tests/test_check_tenant_boundary_bypass.py:644-682` ほか | `assert mutated != source` が成立する。**変異が対象の検査へ届くこと**を欠落変異で確認 |
| 9 | **越境テストと故障系テストを足す** — 6 節 | 全件実行で **red 0 件** |

## 5. DoD(受け入れ基準)

- [ ] **`TenantRepositoryBase._session` を満たす供給**が製品コードにあり、**生の `Session`・任意クエリ・汎用 CRUD を公開していない**(`../tenant-boundary-enforcement/plan.md:174`)
- [ ] **業務トランザクションの発行 SQL 列の先頭が束縛文**である(同 `:173` ①。観測窓は `Session.begin()` 以降)
- [ ] **複数の登録済み operation を 1 トランザクションで実行できる**。**束縛はトランザクション単位で 1 回**
- [ ] **「1 operation = 1 表」を緩めていない**(`capability_registration.py:1256-1257` を変更しない)
- [ ] **`FOR UPDATE` を capability のノード型へ入れていない**(4-1 の裁定 3)
- [ ] **`SERIALIZABLE` + 再試行を要求できる**。既定の分離レベルは変えていない
- [ ] **ロール真正性検査(checkout ごと)を通る**。**検査頻度を下げる最適化をしていない**(`../tenant-boundary-enforcement/plan.md:151`)
- [ ] **`allowed_symbols` への追加を 7.7-2 に適合する v2 形式で記録**した。**承認記録は取得元を明記して逐語転記**してあり、**推定値が 1 つも無い**
- [ ] **`tenant-context-allowlist.json` の `allowed_product_modules` が `[]` のまま**
- [ ] **`PRODUCT_CAPABILITY_IDS` / `PRODUCT_OPERATION_TOKEN_TYPES` / `CROSS_TENANT_FUNCTIONS` が空のまま**
- [ ] 迂回検査(`scripts/check_tenant_boundary_bypass.py`)が green
- [ ] pytest / ruff / ty green
- [ ] 横断要求: **物理削除しない** / テナント分離を全機能に適用 / 自動エスケープ
- [ ] **コア領域** → 敵対レビュー + **人間の逐行確認**

## 6. テスト計画

**DB を使う**。`backend/tests/db/` 配下は `requires_db` マーカー付き(`backend/tests/db/environment-expectations.json`)。

| 対象 | 種別(NFR-019) | 確認すること |
| --- | --- | --- |
| 束縛の先頭性 | **越境** | 複数 operation を回しても、**発行 SQL 列の先頭が束縛文**(SQL observer で観測) |
| 複数 operation の原子性 | **故障系** | 2 件目で例外 → **1 件目もロールバックされる**。commit 後に GUC が空文字 |
| 文脈の混在 | **越境** | 同一トランザクションへ**異なる `TenantContext`** を混ぜると `TenantBindingError` |
| 未登録 token | **越境** | registry に無い token を混ぜると red。**偽造 token で red** |
| 公開面 | **単体** | 公開シンボルが exact-set。**生の `Session`・`Result`・ORM instance を返さない** |
| `SERIALIZABLE` + 再試行 | **故障系** | 直列化失敗を注入して**再試行が起きる**。**再試行回数の上限**で打ち切る |
| Session のライフサイクル | **単体** | **リクエストごとに新しい Session**。テナント横断・リクエスト横断で共有しない |
| 迂回検査 | **越境** | 新シンボルの**署名 exact 一致**。`allowed_api_ids` が最小 |
| 欠落変異 | **故障系** | 上記の各検査を無効化すると、対応する負例が**期待する red を失う** |

**実行手順**(`backend/` で。CI と同じ順):

```
docker compose up -d
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest -c pyproject.toml --cov
```

**`--cov` は機械契約が `comparison: "exact"` で固定している**(`backend/tests/db/environment-expectations.json:163`)。

ハーネス側(リポジトリルート)は `uv run ruff check .` / `uv run ty check` / `uv run pytest tests/`。
**`ruff format` はハーネス側では走らせない**(AGENTS.md)。
