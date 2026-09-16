---
feature: u00-api-shell
type: design
date: 2026-09-16
---

# 詳細設計: U-00 API 器

調査の典拠は [research.md](research.md)。本書は plan.md 4 節から参照される詳細設計であり、
機構が読む状態と実装ステップ表は plan.md のみに置く。

## 1. ファイル構成

| パス | 役割 |
| --- | --- |
| `backend/src/pitchlog/api/__init__.py` | パッケージ docstring のみ(既存 `db/` `authz/` の作法に合わせる) |
| `backend/src/pitchlog/api/app.py` | `create_app()`・ルータ登録機構・OpenAPI メタ |
| `backend/src/pitchlog/api/errors.py` | 例外ハンドラと封筒生成 |
| `backend/src/pitchlog/api/schemas/__init__.py` | パッケージ docstring のみ |
| `backend/src/pitchlog/api/schemas/base.py` | エラー封筒モデル・メタ応答モデル |
| `backend/src/pitchlog/api/routers/__init__.py` | パッケージ docstring のみ |
| `backend/src/pitchlog/api/routers/meta.py` | `/health` `/version` |
| `backend/src/pitchlog/main.py` | `app = create_app()` に置き換え |
| `backend/tests/api_fixtures.py` | `app` / `client` フィクスチャ(**明示 import 用・conftest にしない**) |
| `backend/tests/test_api_*.py` | 器のテスト(平場) |

上記はいずれも `.claude/core-areas.json` の `paths` / `guard_paths` に該当しない(実測 — [research.md](research.md) D)。
DoD が名指しする 3 ファイル(`api/app.py` / `api/errors.py` / `api/schemas/base.py`)を上記の名前で作る。
`backend/tests/conftest.py`(187 バイト)は**触らない** — 既存の `anyio_backend` フィクスチャで足りる。

## 2. エラー封筒

### 2-1. 形

```json
{"error": {"message": "…"}}
```

バリデーション失敗のときだけ `fields` が加わる:

```json
{"error": {"message": "入力に誤りがあります", "fields": [{"location": "body.player_name"}]}}
```

### 2-2. 決定と、その根拠の強さ

**根拠の性格を 2 つに分ける**(1 周目レビュー P1 — 要件の直接帰結と、安全側の設計判断を混ぜない)。

#### (A) 要件の直接帰結(器が破ってはならない)

| 決定 | 根拠 |
| --- | --- |
| **認可・テナント境界に由来する拒否で、理由コードを本文に返さない** | 要件書 `:645` `:681`「いずれも理由コードを返さない」/ `docs/design/sync-protocol.md:885-892`「本文に理由コードを返さない」 |
| **器は 403 を外へ出さない**(§2-3 の fail-closed 写像で構造的に閉じる) | `docs/improvements-from-baseball-scoring.md:39`(I-2 改訂・PO 確認済み)「**403 を返す分岐は存在しない**」 |
| **失敗はサーバーログへ必ず顕在化させる** | NFR-015(要件書 `:872-875`)・4.0-2(`:163`) |
| **ログにシークレット・認証情報を出さない** | NFR-014(要件書 `:867-870`)・NFR-011 の測定方法(`:855`)・AGENTS.md「シークレットのハードコード・ログ出力は P0」 |

#### (B) 安全側の U-00 規約(要件の直接帰結ではない・**TSK-346 に従属する**)

TSK-346(API 契約の正本)が後から別の形を定めたら、**TSK-346 が正**である
(`docs/features/product-impl-unit-split/plan.md:499-500`)。それまでの暫定規約として次を採る。

| 決定 | 性格 |
| --- | --- |
| **封筒に `code` フィールドを置かない**(認可由来に限らず全エラーで) | 要件が禁じるのは認可拒否の理由コードだけ。**全エラーへ広げるのは器の規約** — 経路ごとに封筒の形が分かれるのを防ぎ、認可由来の応答だけ形が違う状態を作らないため |
| **404 の本文を固定文言の単一形にし、呼び出し側が差し替える口を用意しない** | 同上。要件は「404 に一意に定まる」(`:687`)までで、文言の固定までは定めない |
| **`fields` は `location` だけを返し、`input`(入力値)と pydantic の内部メッセージを返さない** | 要件に規定なし。存在秘匿の目的に照らした予防的設計。**NFR-023 を根拠にしない** — 同条の対象経路列挙に API の JSON 応答は含まれない(要件書 `:967`) |
| **応答本文に内部情報(例外型名・traceback・SQL・接続先)を出さない** | 同上 |

**テナント/認可に関わる判断を器は持たない。** 404 をいつ返すかは各単位と U-T1 の責務であり、
404 / 403 の使い分けと情報漏洩の境界の決着先は **TSK-346**
(`docs/adr/ADR-004-merge-gate-scope.md:45`)。器が決めるのは**封筒の形と写像だけ**である。

### 2-3. 例外 → ステータス・封筒・ログの写像

| 例外 | ステータス | 封筒 | ログ |
| --- | --- | --- | --- |
| `RequestValidationError` | **422**(FastAPI 既定を維持) | `message` 固定 + `fields`(`location` のみ) | INFO |
| `StarletteHTTPException` (404) | 404 | `message` 固定のみ | INFO |
| `StarletteHTTPException` (405) | 405 | `message` 固定のみ | INFO |
| **`StarletteHTTPException` (403)** | **404 へ落とす(fail-closed)** | 404 と同一の封筒 | **ERROR**(「403 を生成した実装がある」ことを顕在化させる) | 
| `StarletteHTTPException`(上記以外) | 受け取った値のまま | `message` 固定 | INFO |
| **未捕捉の `Exception`** | **500** | `message` 固定(内部情報なし) | **ERROR + traceback** |

**403 の扱いが 1 周目レビューの P0 だった。** 当初は「その他 4xx はそのまま返す」としており、
`api/` に `403` リテラルが無いことを走査しても **403 が素通りする経路が残っていた**。
本版は**挙動で閉じる**:

- 器は 403 を外へ出さない。403 を受け取ったら **404 へ写す**(存在秘匿の方向へ倒す = 要件の目的と一致)
- 同時に **ERROR ログへ出す**。黙って握り潰すと NFR-015(失敗の黙殺防止)に触れ、
  403 を投げた実装の誤りも見えなくなる
- 検査は**リテラル走査ではなく挙動テスト**で行う —
  テスト専用の `APIRouter` に `HTTPException(403)` を投げる経路を足した `create_app()` を組み立て、
  応答が 404・本文が 404 と同一・ログが ERROR であることを確認する
- **この写像は TSK-346 が 403 の使用を定めたら見直す**((B) と同じ従属関係)

**422 を 400 に変えない。** 要件書が 400 を名指しするのは「同時比較上限を超える集合の要求を
要求全体で拒否する」業務規則(`:508` `:628`)であり、スキーマ検証の失敗ではない。

### 2-4. ログの規律(NFR-014 / NFR-011 / AGENTS.md P0)

**器が完全なマスキングを保証することはできない**(例外メッセージや変数値に何が載るかは例外を投げる側の問題)。
器が負う責務を**器の中で閉じる形に限定**し、検査可能にする。

| 規律 | 検査 |
| --- | --- |
| **器は要求の header / body / query / cookie をログへ出さない**(そもそも参照しない) | `api/errors.py` に `request.headers` / `request.body` / `request.query_params` / `cookies` が出現しないことを走査 |
| **未捕捉例外は `logger.exception` で traceback を出す**(NFR-015) | 挙動テスト(§2-3) |
| **毒性値がログに出ない**(否定テスト) | `Authorization` ヘッダとクエリに毒性値を入れた要求で 500 を起こし、`caplog` のテキストに毒性値が現れないことを確認する |
| **例外メッセージ自体のマスキングは器の射程外** | 例外を投げる側(各単位)の責務。本書に明記して申し送る |

## 3. ルータ登録機構

```python
ROUTERS: tuple[APIRouter, ...] = (meta.router,)
```

- `create_app()` は `ROUTERS` を順に `include_router` する。**モジュールトップレベルのタプル**とし、
  `pkgutil.walk_packages` 等の**動的探索を使わない**。
- 根拠: ADR-003 D-11 が「実在入口 = ラッパー利用箇所の静的列挙 + **フレームワークの route /
  API ハンドラ登録の列挙**」を要求する(`docs/adr/ADR-003-domain-calc-method.md:240`)。
- **本単位で `ROUTERS` に入るのは `meta.router` だけ**(`/health` `/version` の 2 経路)。

## 4. 経路記述の書式(器が決める規約)

`docs/features/product-impl-unit-split/plan.md:517`「**U-00 が経路記述の書式を 1 つ決める**
(コードの規約であって正本ではない)」に対応する。**正本ではない** — 収載の決着先は TSK-346。

1. 経路は `APIRouter` に定義し、`ROUTERS` へ明示登録する
2. 各経路に **`response_model` を明示**する
3. 各経路に **`operation_id` を明示**する。値は snake_case の `<領域>_<資源>_<動作>`(例: `meta_health_read`)
4. **`operation_id` は `contracts/authz/route-registry.json` の `enums.operation_ids` と重ならない** —
   同ファイルの `operation_ids` は FastAPI のものではなく**管理操作 8 件の識別子**
   (`create_group` / `issue_invitation` / … 実測)で、`scripts/check_authz_catalog.py:1946`,`:2011` が
   exact-set 検証している
5. **`route_id`(`ROUTE:...`)は別軸**であり、正は `contracts/authz/http-route-matrix.json`
   (`docs/design/data-model.md:2438`)。**器は `route_id` を付与しない** — 入口を 1 つも開かないので
   同 `:2454` の付与要求が掛からない
6. `tags` と `summary` は日本語(AGENTS.md のコメント規約に合わせる)

## 5. `/health` `/version` と OpenAPI メタ

| 経路 | 応答 | 決定 |
| --- | --- | --- |
| `GET /health` | `{"status": "ok"}` | **既存契約を変えない**。PO 裁定 2026-08-19 由来で Phase 4 受入証跡が参照している(`docs/features/backend-skeleton/plan.md:124`、`docs/worklog/2026-08-19-backend-skeleton.md:42`)。`response_model` を付けるだけで JSON は同一にする |
| `GET /version` | `{"version": "0.1.0"}` | 版は `importlib.metadata.version("pitchlog-backend")` から取る(`backend/pyproject.toml:2-3`)。**pyproject を読み書きしない** |

- **`/version` が返すのはアプリ版のみ**。依存一覧・コミットハッシュ・環境名・ホスト名を返さない
  (要件に公開可否の規定が無いため露出面を最小にする — [research.md](research.md) 未解決 ②)。
- **どちらも DB のデータへ到達しない**。lifespan で DB セッションを張らない・`SELECT 1` を入れない。
  これが U-00 の非コア判定そのもの(`docs/design/data-model.md:2459-2466`。`/health` は境界例表に
  名指しで「開かない」— 同 `:2494`)。
- OpenAPI メタは `title` / `version`(アプリ版)/ `description` の 3 つだけを与える。
  `docs_url` は FastAPI 既定のまま(本番での開閉は要件に規定が無く、器の射程外)。
- **`app.routes` には FastAPI 既定の `/openapi.json` `/docs` `/docs/oauth2-redirect` `/redoc` が載る**
  (1 周目レビュー P1)。経路数の検査は **`fastapi.routing.APIRoute` のインスタンスかつ
  `ROUTERS` 由来のもの**に限定し、`app.routes` の素の件数で数えない。

## 6. 非コアを保つための検査可能な述語

DoD へそのまま写す。`backend/tests/test_api_conventions.py` が固定する。

| # | 述語 | 検査方法 | 由来 |
| --- | --- | --- | --- |
| 1 | `api/**` に `sqlalchemy` / `Session` / `engine` / `session.execute` / `select(` / `text(` / `raw_connection` が出現しない | ソース走査 | 非コア条件 5(`plan.md:273`) |
| 2 | `api/**` に同期語彙 `idempotenc` / `seq_no` / `tombstone` / `revision_no` / `generation` が出現しない | ソース走査 | 非コア条件 2(`plan.md:270`)。語彙の正は `docs/design/sync-protocol.md:53-65`。**`応答` は HTTP 応答一般としてのみ使う**(同 `:75`) |
| 3 | **器が 403 を外へ出さない** | **挙動テスト**(§2-3。リテラル走査では不十分 — 1 周目 P0) | `docs/improvements-from-baseball-scoring.md:39` |
| 4 | **U-00 が登録する `APIRoute` が `/health` `/version` の 2 本だけ** | `ROUTERS` 由来の `APIRoute` を抽出(docs 系を除く — §5) | `plan.md:309` |
| 5 | エラー封筒のモデルに `code` フィールドが無い | モデル定義の検査 | §2-2 (B) |
| 6 | `operation_id` が `route-registry.json` の `enums.operation_ids` と交わらない | 集合演算 | §4-4 |
| 7 | **`api/errors.py` が要求の header / body / query / cookie を参照しない** + **毒性値がログに出ない** | 走査 + 否定テスト | §2-4(1 周目 P0) |

`api/**` に新たな認可判定を置かない(非コア条件 1)・キャッシュ無効化契約を持たない(同 4)・
NFR-018 対象計算を持たない(同 3)は、**そもそも該当コードを書かない**ことで満たす。

## 未解決・検討メモ

- **バリデーション写像の帰属**: カードのスコープは U-00 に置くが、原典の単位表
  `docs/features/product-impl-unit-split/plan.md:197` は **U-01(DTO 基盤)が「バリデーション写像」を持つ**と書く。
  本書は「**`RequestValidationError` を封筒へ写す例外ハンドラ**(転送層)は U-00、
  **フィールド単位の検証規則と DTO 側の写像**は U-01」と切る。
- **`fields` の `location` 書式**: pydantic の `loc` タプルをドット連結する。
  配列添字の扱いは経路が生えてから確定でよい(器にはボディを持つ経路が無い)。
- **生成 OpenAPI をコミットするか**: 本単位では**コミットしない**(FastAPI が実行時に生成する)。
  収載の決着先は TSK-346([research.md](research.md) E-③)。
- **例外メッセージのマスキング**: 器の射程外(§2-4)。例外を投げる各単位へ申し送る。
