---
feature: u00-api-shell
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-16・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: 通常            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3da93b75e687818e9858f499ccce3b47
branch: feature/u00-api-shell
created: 2026-09-16
計画レビュー周回: 1        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: U-00 API 器(app factory・ルータ登録機構・エラー封筒・例外ハンドラ)

## 1. 背景・目的

- **Notion タスク**: [TSK-387 U-00 API 器](https://app.notion.com/p/3da93b75e687818e9858f499ccce3b47)
- **出所**: TSK-363「製品機能の実装単位を分割する」/ 計画書
  `docs/features/product-impl-unit-split/plan.md`(承認済 2026-09-13・山田正輝)の **帯 0 — 器**。
  単位表 `:196` が U-00 を定義する(**主所有 FR = なし・依存 = なし・機/意ともに非コア**)。
- **なぜやるか**: 後続の全単位(U-01・U-02・U-T1 以下)が U-00 に依存する
  (`docs/features/product-impl-unit-split/plan.md:197`,`:198`,`:204`)。FR 経路を持つ単位が
  それぞれ独自の app 構成・エラー形式を持ち始める前に、**器を 1 つに決める**のが目的。
- **要件との関係**: 本単位は**主所有 FR を持たない**。器として構造的に効く NFR は次のとおり
  (射程の詳細は [research.md](research.md) B-3):
  - **NFR-015 失敗の黙殺防止**(要件書 `:872-875`)— 例外ハンドラはサーバーログへ必ず顕在化させる
  - **NFR-014 シークレット**(同 `:867-870`)・**NFR-011 の測定方法**(同 `:855`)— ログに認証情報を出さない
  - **NFR-010 テナント分離**(同 `:846-850`)— 器のエラー応答の形が存在秘匿を壊さないこと
  - **NFR-019 テスト**(同 `:923-938`)— pytest を伴う。**(b) 越境テストの要求は空**
    (同 `:933` の発効条項 — 入口を 1 本も開かないため)
  - **FR-034**(同 `:645` `:681` `:687`)— 拒否時に理由コードを返さない・403 の分岐を持たない。
    **器のエラー封筒の形を直接縛る**

## 2. スコープ

### やること

- `create_app()`(app factory)と **ルータ登録機構**(静的列挙 — [design.md](design.md) 3 節)
- **エラー封筒**と**例外ハンドラ**、**バリデーションエラー(`RequestValidationError`)の封筒への写像**
  ([design.md](design.md) 2 節)
- **OpenAPI メタ**(`title` / `version` / `description` のみ)
- **`/health`**(既存の応答契約 `{"status": "ok"}` を変えずにルータへ移設)と **`/version`**
- **経路記述の書式を 1 つ決める**(FastAPI router + `response_model` + `operation_id` 命名規則 —
  [design.md](design.md) 4 節)。**これはコードの規約であって正本ではない**
  (`docs/features/product-impl-unit-split/plan.md:517`)
- `backend/src/pitchlog/main.py` を `app = create_app()` に置き換える
  (`[tool.fastapi] entrypoint = "pitchlog.main:app"` を維持するため **`app` は module 属性のまま残す**)

### やらないこと

| やらないこと | 理由 |
| --- | --- |
| **FR 経路を 1 本も登録しない** | 登録は `/health` `/version` のみ。入口を開くと `route_id` 付与 → `contracts/authz/*` 編集 → 機械判定でコア(`plan.md:300-315`) |
| **DB セッションを持たない**(lifespan でも張らない・`SELECT 1` も入れない) | 非コア判定は「**DB のデータへ到達しない**」1 点に乗っている(`plan.md:309`、`docs/design/data-model.md:2459-2466`) |
| **テナントデータを返す応答モデルを定義しない** | 同上 |
| **認証・認可ミドルウェアを置かない**(新たな認可判定を書かない) | **U-T1 の責務**(`plan.md:204`・非コア条件 1) |
| **同期セマンティクスの語彙を持たない** | 非コア条件 2(`plan.md:270`)。語彙の正は `docs/design/sync-protocol.md:53-65` |
| **404 / 403 の使い分け・情報漏洩の境界を決めない** | **TSK-346 の射程**(`docs/adr/ADR-004-merge-gate-scope.md:45`、`plan.md:499`)。器は封筒の形だけを決める |
| **フィールド単位の検証規則・DTO 側の写像を作らない** | **U-01(DTO 基盤)の責務**(`plan.md:197`)。器が持つのは `RequestValidationError` を封筒へ写す転送層のハンドラだけ([design.md](design.md) 未解決) |
| **業務規則由来の 400 を器で決めない** | 要件書 `:508` `:628` の 400 は業務規則(同時比較上限)であり各単位の責務 |
| **依存を 1 つも追加しない** — **`backend/pyproject.toml` / `backend/uv.lock`**(5 領域すべての paths)と **root の `pyproject.toml` / `uv.lock` / `.python-version`**(`guard_paths` に完全一致)の**いずれも変更しない** | lockfile はリポジトリに 2 つ実在する(`uv.lock` と `backend/uv.lock` — 実測)。**両方が別の経路で core-guard に当たる**(`.claude/core-areas.json:129`,`:190`,`:264`,`:313`,`:367` と `guard_paths`)。必要なら依存追加だけの単独 PR(出所 `plan.md:462`) |
| **`backend/tests/conftest.py` を触らない**(差分 0 行) | `backend/*conftest.py` は tenant-isolation のコア(`.claude/core-areas.json:314`。`*` が `/` を跨ぐ) |
| **`backend/src/pitchlog/db/` に 1 ファイルも足さない** | **上流計画の地雷制約**(出所 `plan.md:467`「1 ファイルも足さない。新規は `api/` `services/` `repositories/` `sync/` `domain/` のみ」)。**機械判定の理由ではない** — `core-areas.json` の `db/` 系 paths は既存ファイルの個別列挙で、新規ファイルを当てる包括パターンは無い(実測。1 周目レビュー P0 の訂正) |
| **生成 OpenAPI をコミットしない** | 収載先の決着は TSK-346([research.md](research.md) E-③) |
| **`docs/design/` に API 設計の正本を新設しない** | API 契約の正本は TSK-346。現時点で正本は存在しない(`plan.md:495-499`) |

## 3. 影響する正本

**すべて「反映なし」**。器は入口を開かず、既存の正本に追随を要する変更を持たない。

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし**(主所有 FR を持たず、NFR の記述変更も生じない) | — |
| `docs/design/data-model.md` | **反映なし**(入口を開かないので 12-4 の `route_id` 付与要求が掛からない — `:2454`) | — |
| `docs/design/sync-protocol.md` | **反映なし**(同期セマンティクスに触れない) | — |
| `docs/development/dev-harness-design-2026-08-07.md` | **反映なし** | — |
| `docs/adr/ADR-001〜004` | **反映なし**(ADR-003 D-11 の静的列挙要求は**満たす側**であり、ADR の改訂ではない) | — |
| `.claude/core-areas.json` | **反映なし**。`api/**` を paths に登録しない(器は非コアであり、追加は 6.3-⑤ の敵対レビュー+人間承認を要する) | — |
| `contracts/authz/*` | **反映なし**(入口を開かないため `route_id` を付与しない) | — |
| `contracts/README.md` | **反映なし**(OpenAPI を収載しない) | — |
| `docs/README.md`(索引) | **反映なし**(進行中 feature の静的一覧を持たない — `docs/README.md:29`) | — |
| `AGENTS.md` / `CLAUDE.md` | **反映なし** | — |

## 4. 実装方針

調査メモ: [research.md](research.md)(2026-09-16・spec-checker / decision-tracer / Explore の 3 並列 + 原典裏取り)
詳細設計: [design.md](design.md)(ファイル構成・エラー封筒・写像表・登録機構・経路記述の書式・検査述語)

### 重さ分類 = 通常 / コア領域判定 = 非コア

| 判定 | 根拠 |
| --- | --- |
| **機械判定: 非コア** | `.claude/core-areas.json` の実測 — `backend/src/pitchlog/api/**`・`backend/src/pitchlog/main.py`・`backend/tests/test_api_*.py` はどの area の paths にも `guard_paths` にも該当しない([research.md](research.md) D) |
| **意味判定(設計書 6.3): 非コア** | **入口を開かない** — `/health` `/version` は DB のデータへ到達しないので `docs/design/data-model.md:2438` の定義上「入口」ではない。`/health` は境界例表に名指しで「開かない」と載る(同 `:2494`)。`plan.md:309` が「非コア(確定)」とする |
| **レビュー経路: 通常レビュー** | `docs/features/product-impl-unit-split/plan.md:339`(器 3 本は非コア・通常レビュー・**降格の余地なし**) |

**非コアは触れるファイルに依存する。** 下の 3 つに触れた時点でコアへ落ち、人間の逐行確認が必要になる:
`backend/tests/conftest.py`(tenant-isolation)/ `backend/pyproject.toml`・`uv.lock`(5 領域すべて)/
`contracts/authz/*`(tenant-isolation)。**いずれも 2 節「やらないこと」で禁止し、
[design.md](design.md) 6 節の述語として機械検査する。**

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **エラー封筒と例外ハンドラ** — `api/__init__.py` / `api/schemas/__init__.py` / `api/schemas/base.py`(封筒モデル)/ `api/errors.py`(写像とハンドラ登録関数)、テスト用に `backend/tests/api_fixtures.py` と `backend/tests/test_api_errors.py` | **`backend/` で** `uv run pytest` green。① 封筒モデルに `code` が無い ② `RequestValidationError` → 422 + `fields`(`location` のみ・`input` を含まない)③ **403 を投げるテスト専用経路の応答が 404 かつ本文が 404 と同一・ログが ERROR**(挙動テスト。リテラル走査ではない)④ 未捕捉例外 → 500 + ERROR ログ + 本文に内部情報が無い ⑤ **毒性値を `Authorization` ヘッダとクエリに入れた 500 で、`caplog` に毒性値が現れない**。**`backend/` で** `uv run ruff check .` / `uv run ruff format --check .` / `uv run ty check` green |
| 2 | **app factory とルータ登録機構** — `api/app.py`(`create_app()` / `ROUTERS` タプル / ハンドラ登録)、`api/routers/__init__.py` / `api/routers/meta.py` へ `/health` を移設、`main.py` を `app = create_app()` に置き換え | **既存 `backend/tests/test_health.py` を 1 行も変えずに green**(応答 `{"status": "ok"}` が同一)。`backend/tests/test_api_app.py` が ① `ROUTERS` がモジュールトップレベルのタプルであること ② **`ROUTERS` 由来の `fastapi.routing.APIRoute` が `/health` の 1 本だけ**であること(`app.routes` の素の件数で数えない — FastAPI 既定の `/openapi.json` `/docs` `/redoc` が載るため)を検証。**`backend/` で** ruff / ruff format --check / ty green |
| 3 | **`/version`・OpenAPI メタ・規約テスト** — `meta.py` に `/version`、`create_app()` に OpenAPI メタ、`backend/tests/test_api_conventions.py` | `/version` が 200 で `{"version": "0.1.0"}`(`importlib.metadata` 由来)。**`ROUTERS` 由来の `APIRoute` が `/health` `/version` の 2 本のみ**。各経路に `response_model` と `operation_id` があり、`operation_id` が `contracts/authz/route-registry.json` の `enums.operation_ids` と交わらない。[design.md](design.md) 6 節の述語 1〜7 がすべて green。**`backend/` で** ruff / ruff format --check / ty green |

**検証コマンドはすべて `backend/` ディレクトリで実行する**(1 周目レビュー P1)。
リポジトリルートの `uv run pytest` は `tests/` しか見ず、ルートの ruff / ty は `backend` を
除外しているため(`pyproject.toml:25`,`:46`,`:49`)、ルートで走らせても U-00 のコードを検証しない。

**全ステップ共通 — 触れてはならないパス(コミット前に `git diff --name-only <base>..HEAD` で機械的に確認する)**:

| パス | 当たる先 |
| --- | --- |
| `backend/pyproject.toml` / `backend/uv.lock` | 5 領域すべての `paths` |
| `pyproject.toml` / `uv.lock` / `.python-version`(いずれもルート) | `guard_paths`(完全一致) |
| `backend/tests/conftest.py` | tenant-isolation(`backend/*conftest.py` — `*` が `/` を跨ぐ) |
| `conftest.py` / `tests/conftest.py`(ルート) | `guard_paths` |
| `contracts/**` | `contracts/authz/*` が tenant-isolation |
| `backend/tests/db/**` / `backend/migrations/**` | 5 領域すべて |
| `backend/src/pitchlog/db/**` | 上流計画の地雷(`plan.md:467`) |
| `backend/tests/test_authz*.py` | tenant-isolation(命名で当たる) |

**`git diff --stat` では不在を機械的に失敗にできない**(1 周目レビュー P0)。
`--name-only` の出力を上の一覧と突き合わせ、1 件でも一致したら止める。

## 5. DoD(受け入れ基準)

Notion タスク TSK-387 の DoD と同期。**原典由来でない項目は出所を併記する**
(カード記載の「経路予約」「器の線引き 1〜3」は原典 plan.md / design.md に対応記述が無く、
起票時の具体化である — [research.md](research.md) E-①②)。

- [ ] **DB セッションを持たない** — `api/app.py` `api/errors.py` `api/schemas/base.py` に
      `sqlalchemy` / `Session` / `engine` が出現しない(非コア条件 5 の具体化 — `plan.md:273`)
- [ ] **FR 経路を 1 本も登録しない** — 登録は `/health` `/version` のみ(`plan.md:309` の非コア判定の根拠)
- [ ] **テナントデータを返す応答モデルを定義しない**
- [ ] **認証・認可ミドルウェアを置かない**(U-T1 の責務 — `plan.md:204`)
- [ ] **同期セマンティクスの語彙を持たない**(非コア条件 2 — `plan.md:270`)
- [ ] **`backend/tests/conftest.py` の差分が 0 行**(既存 187 バイト・実測一致。`plan.md:569` が全計画書に要求)
- [ ] **`backend/pyproject.toml` / `backend/uv.lock` を変更しない**(5 領域全部の paths)。
      **あわせてルートの `pyproject.toml` / `uv.lock` / `.python-version` も変更しない**(`guard_paths` に完全一致。
      lockfile が 2 つ実在するため個別に条件化する — 1 周目レビュー P0)。
      `[tool.fastapi] entrypoint = "pitchlog.main:app"` を維持し `main.py` に `app = create_app()` を残す
- [ ] **`backend/src/pitchlog/db/` に 1 ファイルも足さない**
- [ ] テストは平場(`backend/tests/test_api_*.py`)に置く。fixture は `backend/tests/api_fixtures.py` へ明示 import
- [ ] **器が 403 を外へ出さない** — 403 を受け取ったら 404 へ落とし ERROR ログへ顕在化させる。
      **挙動テストで検証する**(リテラル走査では素通りを防げない — 1 周目レビュー P0)。
      根拠は台帳 `:39`「403 を返す分岐は存在しない」(PO 確認済み)。**カードには無い追加項目**
- [ ] **エラー封筒が `code`(理由コード)を持たない**。認可拒否について理由コードを禁じるのは要件書 `:645` `:681`。
      **全エラーへ広げるのは器の安全側規約であり要件の直接帰結ではない**(TSK-346 に従属 — 1 周目レビュー P1)
- [ ] **未捕捉例外がサーバーログへ ERROR で顕在化し、応答本文に内部情報を出さない**(NFR-015 要件書 `:872-875`)
- [ ] **ログにシークレットを出さない** — `api/errors.py` が要求の header / body / query / cookie を参照せず、
      毒性値を入れた 500 の否定テストで `caplog` に毒性値が現れない(NFR-014 要件書 `:867-870`・
      AGENTS.md「シークレットのログ出力は P0」。**例外メッセージ自体のマスキングは器の射程外**と明記する —
      1 周目レビュー P0)
- [ ] **既存 `/health` の応答契約 `{"status": "ok"}` を変えず、`backend/tests/test_health.py` が無変更で green**
      (PO 裁定 2026-08-19 由来・Phase 4 受入証跡が参照 — **カードには無い追加項目**)
- [ ] **`backend/` で** pytest / ruff check / ruff format --check / ty green(ルートで走らせても検証にならない)
- [ ] **横断要求(全単位共通・破っていないこと)**
  - [ ] **物理削除しない**(要件書 4.0-2)— 器は削除操作を持たない
  - [ ] **テナント分離を全機能に適用**(NFR-010)— 器はテナントデータを扱わない
  - [ ] **利用者入力は全出力経路で自動エスケープ・生 HTML 挿入禁止**(NFR-023)— 器は HTML を返さない

## 6. テスト計画

**NFR-019 のテスト種別への対応**(要件書 `:923-938`):

| 種別 | 本単位での扱い |
| --- | --- |
| **単体(pytest)** | **追加する** — ① 例外写像(422 / 404 / 405 / **403 → 404 fail-closed** / 500)② 封筒の形(`code` 不在・`fields` は `location` のみ・`input` を含まない)③ 未捕捉例外の ERROR ログ出力 ④ **毒性値がログに出ない否定テスト** ⑤ `create_app()` が `ROUTERS` を登録すること ⑥ `/health` `/version` の応答 ⑦ OpenAPI に U-00 の 2 経路だけが載ること(docs 系を除いて数える) |
| **(a) 一致性テスト** | **対象外** — ドメイン計算(NFR-018 の対象計算)を持たない |
| **(b) 越境アクセステスト** | **要求は空**。要件書 `:933` の発効条項「**未発効の経路を理由に不合格と判定してはならない**(実装が存在しない経路の越境テストは書けない)」による。**入口を 1 本も開かない**ため([research.md](research.md) B-3)。**網羅の免除ではない** — 経路が生えた単位で発効する |
| **(c) E2E** | **対象外** — 業務分岐を持たない |
| **(d) 同期プロトコル故障系** | **対象外** — 同期セマンティクスを持たない |
| **規約テスト(本単位で新設)** | `backend/tests/test_api_conventions.py` が [design.md](design.md) 6 節の述語 1〜7 を固定する。**述語 3(403 を外へ出さない)と 7(ログ)は挙動テスト**、残りはソース走査。**非コア判定が壊れたら CI が落ちる**形にするのが狙い |

**テストの配置**: すべて `backend/tests/` の平場。`backend/tests/db/` を使わない(5 領域すべてのコア)。
`test_authz*` の名前を使わない(tenant-isolation の paths に一致する — `.claude/core-areas.json:307`)。
共有 fixture は `backend/tests/api_fixtures.py` に置き、各テストモジュールが明示 import する
(**`conftest.py` を新設しない** — `backend/*conftest.py` に一致してコア化するため)。

**DB 非依存**: 器のテストは `requires_db` マーカを付けない。`backend/tests/` 直下は DB 非依存で、
DB 装置は `backend/tests/db/conftest.py` に閉じている([research.md](research.md) A)。
