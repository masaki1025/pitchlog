---
feature: u00-api-shell
type: research
date: 2026-09-16
---

# 調査メモ: U-00 API 器(app factory・ルータ登録機構・エラー封筒・例外ハンドラ)

## 問い

TSK-387 の実装計画を書くために、次の 5 点を典拠つきで確かめる。

1. 器が作るエラー封筒・例外ハンドラに、要件側の拘束はあるか
2. `/health` `/version` の要件上の足場はどこか。既存 `/health` との関係は
3. U-00 の非コア判定は何に乗っているか。どう振る舞うと壊れるか
4. Notion カードの DoD は原典のどこに対応するか(対応しない項目はあるか)
5. 依存追加なしで実装できるか。CI は何を要求するか

調査は 3 並列(spec-checker = 要件突合 / decision-tracer = 決定経緯 / Explore = 現行実測)。
旧システム調査(legacy-analyst)は外した — U-00 は業務経路を 1 本も持たず、旧 Baseball_Scoring の
実挙動・88 列構造と接する面が無いため。移行系の論点は後続単位に出る。

## 結論(要約)

1. **エラー封筒の「形式」は未決だが、「返してはいけないもの」は既決で強い。**
   要件書 FR-034 が拒否時に**理由コードを返さない**・**403 を返す分岐は存在しない**を閉じている。
   汎用の `code` 必須フィールドを器が配ると、器の構造として存在秘匿(NFR-010)を壊す。
2. **U-00 は新規構築ではなく、既存の裸の `app` の作り替えである。**
   `/health` は既に実装済み・テスト済みで、`{"status": "ok"}` という契約と Phase 4 受入証跡がある。
3. **非コア判定は「入口を開かない」1 点だけに乗っている。**
   ヘルスチェックに DB 疎通を入れた瞬間に入口化し、`route_id` 付与 → `contracts/authz/*` 編集 →
   機械判定でコアへ落ちる。DoD に検査可能な述語として置く必要がある。
4. **Notion カードの「経路予約 `/health` `/version` のみ」と DoD 10 件は、原典(plan.md / design.md)に
   対応する記述が無い起票時の具体化である。** 計画書側で典拠を新設するか、原典の 5 条件へ翻訳する。
5. **依存追加なしで実装できる。** ただし CI の backend ジョブは `ruff format --check` を回し、
   backend 側に `per-file-ignores` が無いためテスト関数にも docstring が要る。

## 詳細と典拠

### A. 現行の器の実測(Explore)

| 事実 | 典拠 |
| --- | --- |
| `main.py` は 11 行。`app = FastAPI()` とハンドラ 1 本のみ。**`create_app()` は無い** | `backend/src/pitchlog/main.py:5` |
| `FastAPI()` は引数なし(title / version / docs_url / lifespan / exception_handler すべて未指定)。`include_router`・ミドルウェア・例外ハンドラは**存在しない** | 同上 |
| **`/health` は既に実装済み**。応答は `200` + `{"status": "ok"}` | `backend/src/pitchlog/main.py:8-11` |
| **`/health` のテストも既存**。`@pytest.mark.anyio` + `ASGITransport(app=app)` + `from pitchlog.main import app` | `backend/tests/test_health.py:6`,`:9-12` |
| `backend/src/pitchlog/api/` は**存在しない**。`src/pitchlog/` 直下は `__init__.py` / `main.py` / `authz/` / `db/` のみ | 実測(`ls`) |
| `backend/tests/conftest.py` は **187 バイト**(カード記載と一致)。`anyio_backend` fixture 1 個だけで DB も HTTP クライアントも持たない | `backend/tests/conftest.py` |
| DB 接続の重い装置は `backend/tests/db/conftest.py`(28961 バイト)に閉じている。**`tests/` 直下のテストは DB 非依存** | `backend/tests/db/conftest.py:744`,`:759`,`:786` |
| `docs/design/` は `data-model.md` と `sync-protocol.md` の 2 本のみ。**API 設計の正本は存在しない** | 実測(`ls docs/design/`) |
| HTTP 形状・エンドポイント・ペイロード形式は「**未決。実装計画へ送る**」と設計書が明記 | `docs/design/sync-protocol.md:1552` |

**依存の充足**(依存追加なしで実装できる):

| 依存 | 版 | 典拠 |
| --- | --- | --- |
| fastapi[standard] | 0.141.1 | `backend/pyproject.toml:7` |
| pydantic | 2.13.4(推移依存) | `backend/uv.lock:472-473` |
| httpx(dev) | 0.28.1 | `backend/pyproject.toml:15` |
| anyio(dev) | 4.14.2 | `backend/pyproject.toml:14` |

app factory・例外ハンドラ・ルータ登録・封筒(pydantic モデル)・ASGI テストはこの範囲で書ける。
**依存追加が必要な設計(multipart・構造化ログライブラリ等)を選ぶと、その瞬間に 5 領域コアの PR になる**
(`docs/features/product-impl-unit-split/plan.md:462`,`:481`)。

**CI が要求すること**(`.github/workflows/ci.yml:181-231`・`backend/**` 変更で発火):
`uv sync --locked --dev` → `ruff check .` → **`ruff format --check .`** → `ty check` →
`pytest -c pyproject.toml --cov` → alembic 3 種。
- **`ruff format --check` は backend ジョブにだけある**(ルートのハーネスジョブには無い)。
  AGENTS.md の「`ruff format` は未導入」はルート限定の話。
- backend の `pyproject.toml` に **`per-file-ignores` が無い** → ルートの `"tests/**" = ["D103"]` は効かず、
  **テスト関数にも docstring が必須**(`backend/pyproject.toml:29-39`、ルートは `pyproject.toml:36`)。
- `[tool.ty.src] include = ["src", "tests"]` により新設する `api/` も型検査対象
  (`backend/pyproject.toml:44-45`)。

**既存コードの作法**(新規コードが合わせる先): `__init__.py` は日本語 1 行 docstring のみ・再エクスポートなし
(`backend/src/pitchlog/db/__init__.py:1`)。モジュール定数は `_` 前置、Google convention の
`Args:` / `Returns:` / `Raises:` を日本語で書く、例外メッセージも日本語
(代表例 `backend/src/pitchlog/db/url.py:1-27`)。注釈なしの関数は既存コードに見当たらない。

### B. 要件側の拘束(spec-checker・原典で裏取り済み)

#### B-1. エラー応答 — 形式は未規定・「返してはいけないもの」は Must

要件書全文に**エラーボディのスキーマ・共通形式・エラーコード体系を定めた FR/NFR は存在しない**
(`OpenAPI` / `Swagger` / `バージョニング` / `/api` はヒット 0 件)。一方で次は既決:

| 規定 | 典拠 |
| --- | --- |
| 集合要求は**除外**、単一リソース名指しは **404**。**いずれも理由コードを返さない**。403 は存在を漏らすため使わない | 要件書 `:645` |
| 制御資源の拒否も**すべて 404・理由コードなし** | 要件書 `:681` |
| 制御資源へのあらゆる要求は「許可」か「**404**」に**一意に定まる** | 要件書 `:687` |
| 旧 SPA の 403/404 使い分けは**移植しない**。**403 を返す分岐は存在しない**(PO 確認済み・TSK-308 裁定 B-4) | 改善台帳 `docs/improvements-from-baseball-scoring.md:39` |
| 非開示規則: 応答コードは自テナント非存在と同一・**本文に理由コードを返さない**・利用者通知に内部原因を出さない・**サーバーログには記録する** | `docs/design/sync-protocol.md:885-892` |

要件書が名指ししている HTTP ステータスは **404**(上表)と **400**(同時比較上限超過は要求全体を 400 で拒否・
切り捨てない — 要件書 `:508`,`:628`)の 2 つだけ。

**失敗の黙殺防止(NFR-015 Must)**: 「データ保存・同期・バックアップ・出力の失敗、スキップ、自動補正は、
利用者または管理者が**気づける形(画面通知・ログ)で必ず顕在化**する」(要件書 `:872-875`、4.0-2 `:163`)。
→ **例外を握り潰して一律 500・ログ無しの器は NFR-015 違反**。応答は秘匿しつつサーバーログには顕在化させる
二面構成が要件から導かれる(`sync-protocol.md:885-892` と同じ構え)。

**文言規定**: 多言語対応は Won't(NFR-022 `:972`)なので日本語で確定するが、**エラー文言そのものを定めた条項は無い**。

#### B-2. `/health` `/version` の足場

| 項目 | 判定 | 典拠 |
| --- | --- | --- |
| `/health` の要件条項 | **直接の条項なし**。最も近いのは NFR-021 の測定方法「backend/frontend が起動して疎通確認できること」・証跡欄「HTTP 疎通の応答コード」 | 要件書 `:961`,`:963` |
| 既存 `/health` の契約を誰が決めたか | **PO 裁定 2026-08-19**(「どのスロットが作るかの決定が正本に無く」と明記)。契約 = `200` + `{"status": "ok"}` | `docs/features/backend-skeleton/plan.md:124`、`docs/worklog/2026-08-19-backend-skeleton.md:18`,`:42` |
| **`/version`** | **要件に記載なし**。可否の規定も無い。要件書の `version` ヒットは CSV の `schema_version`(付録D `:696`)と受入証跡の `release_version`(`:959`)のみ | 走査: 要件書全文・改善台帳全文 |
| NFR-016 死活監視(Should) | 「**外形監視**を構成する」— **アプリ内 health エンドポイントの実装を要求してはいない** | 要件書 `:877-880` |
| NFR-017 ログ保持(Should) | サーバーログを **30 日以上**保持 | 要件書 `:882-885` |

#### B-3. 横断 NFR が器レイヤでどう効くか

| NFR | 器での効き方 | 典拠 |
| --- | --- | --- |
| **NFR-023**(出力エンコード) | 対象経路の列挙は「記録・分析画面/カルテPDF・スコアカード・分析PDF/CSV/管理コンソールの横断一覧/移行レポート」で、**API の JSON 応答・エラー応答は含まれていない**。**「エラー封筒に入力をエコーしない」を NFR-023 由来と書くと過剰帰属**。器に要件上の根拠があるのは CSP 設定だけ | 要件書 `:965-969` |
| **NFR-014**(シークレット) | app factory の設定読み込みが規律の受け口。加えて NFR-011 の測定方法が「DB・コード・**ログ**のレビュー」なので、**例外ハンドラのログ出力に認証情報・トークンが載らない**ことが器の責務 | 要件書 `:867-870`,`:855` |
| **NFR-005**(集計規律) | 器に業務経路が無いので直接は効かない。効くのは応答モデル基底にページング DTO を置くかだけ。**ページング応答の形式(offset/cursor・メタの持ち方)は要件に未規定** | 要件書 `:816-820`、台帳 `:29` |
| **NFR-010**(テナント分離) | 器が「例外種別ごとに異なるステータス・異なる本文」を返す汎用ハンドラを持つと、下流が 404 を返そうとしても **404 と 500 の差で存在が漏れる**経路ができる | 要件書 `:846-850` |
| **NFR-019**(テスト) | **(b) 越境テストには明文の発効条項がある** — 「**未発効の経路を理由に不合格と判定してはならない**(実装が存在しない経路の越境テストは書けないため、そう読むとどの PR もマージできなくなる)」。**入口を 1 本も開かない U-00 では (b) の要求は空** | 要件書 `:933` |

#### B-4. 認証・認可の配置

要件書は認可の**実装配置**(ミドルウェア/依存関係/リポジトリ層)を一切規定せず、結果(誰が何に到達できるか・
拒否の応答形)だけを定める。→ **U-00 に認可を置かない方針は要件と矛盾しない**。

注意: FR-034 の「既定拒否の原則」(`:608`)は**射程が FR-041 が新設する権限・経路に限られる**と同条が明記しており、
**「全 HTTP 経路が既定で拒否」という条文は要件書に存在しない**。
また NFR-018(b)③「入口の全列挙」(`:908`)は**ドメイン計算の実行入口**であって HTTP 経路ではない —
器のルータ登録機構の典拠に使わないこと。

### C. U-00 の原典と隣接単位の境界(decision-tracer・原典で裏取り済み)

#### C-1. 原典は plan.md の 1 行

- 単位表 `docs/features/product-impl-unit-split/plan.md:196` =
  `| **U-00** | API 器(app factory・ルータ登録機構・エラー封筒・例外ハンドラ) | — | 非 | **非** | — |`
  (**主所有 FR = 空欄・依存 = 空欄**)
- **`design.md` に U-00 は一度も現れない**。帰属表 4-1/4-2 は FR 主所有・分担を持つ単位だけを列挙しており、
  U-00 / U-01 / U-02 は表に無い(`docs/features/product-impl-unit-split/design.md:67-108`)
- U-00 に明示された経路方面の責務は 1 つだけ:
  「① **U-00 が経路記述の書式を 1 つ決める**(コードの規約であって正本ではない)」(`plan.md:517`)

#### C-2. 非コア判定は「入口を開かない」1 点に乗っている

`plan.md:292-315`(**承認後の是正**・2026-09-13 ADR-004 approved を受けて):

> **器 3 本**(`U-00` / `U-01` / `U-02`)| **非コア(確定)** |
> **入口を開かない** — `/health` `/version` は**DB のデータへ到達しない**ので 12-4 の定義上「入口」ではない

「入口」の正本定義: **製品の外からの要求を受け取り、DB のデータへ到達する 1 本の口**
(`docs/design/data-model.md:2438`)。「開く」の 3 条件の第 3 は**処理が DB のデータを読むか書く**(同 `:2459-2466`)。
`/health` は境界例の表に名指しで「**開かない**」と載っている(同 `:2494`)。

レビュー経路: **通常レビュー・降格の余地なし**(`plan.md:339`)。「非コアで通せるのは器 3 本だけ」(`plan.md:312`)。

#### C-3. 隣接単位

| 単位 | 担当 | 典拠 |
| --- | --- | --- |
| **U-T1** | テナント境界の**強制点**(app ロール接続・`set_config` 文脈束縛・未設定時 fail-closed・越境関数経由のリポジトリ基底・迂回検査)。主所有 FR-034。依存 = U-00 | `plan.md:204`、`design.md:80` |
| **U-01** | DTO 基盤(共通型・ID・時刻・**ページング**・**バリデーション写像**)。依存 = U-00 | `plan.md:197` |
| **U-02** | legacy 経路の**予約**(製品コード 0 行・テスト専用)。依存 = U-00 | `plan.md:198`,`:484` |

**「経路予約」という語を単位に与えているのは U-02 だけ**であり、契約 2 は「**経路予約は所有と分離する**」
(`plan.md:180`)。U-01 が**バリデーション写像**を持つ点は、カード側スコープ「バリデーションエラーの封筒への
写像」と面が接する — 計画書で切り分けを書く必要がある(→ 未解決 ③)。

#### C-4. 器が持ってはいけないものの由来(非コアで通せる 5 条件)

`plan.md:254-277` の 5 条件。上流は次のとおり:

| 条件 | 禁止対象 | 上流 |
| --- | --- | --- |
| 1 | 新たな認可判定(許可は U-T1 の公開関数呼び出しのみ) | 設計書 6.3 tenant-isolation `docs/development/dev-harness-design-2026-08-07.md:389` |
| 2 | **同期セマンティクスの語彙**(`idempotenc`/`seq_no`/`tombstone`/`revision_no`/`generation`) | 同 6.3 `:386`、語彙の正は `docs/design/sync-protocol.md:53-65`。**`応答` は HTTP 応答一般としてのみ可・D9 ACK の意味で使わない**(同 `:75`) |
| 3 | NFR-018 対象計算 | 要件書 `:888-891` / `ADR-003:388` |
| 4 | キャッシュ無効化契約 | 設計書 6.3 `:389` |
| 5 | **テナントデータは U-T1 の越境関数経由だけ**(`session.execute`/`select(`/`text(`/`engine.`/`raw_connection` を禁止側に置く) | 設計書 6.3 `:389`、DB セッション規律の原典は `docs/design/data-model.md:308-331` |

#### C-5. エラー封筒・API 規約は「未決定」— ただし外枠が 4 件ある

エラー封筒の構造・フィールド・例外→ステータス写像・`operation_id` 命名・OpenAPI 生成方式について
決めた記録は**リポジトリ内に無い**(探索: `docs/**` 全体・`contracts/**`)。**この計画で初めて決める事項**。

ただし器が自由に決められない外枠:

1. **404/403 の使い分けと情報漏洩の境界は TSK-346 の射程**
   (`docs/adr/ADR-004-merge-gate-scope.md:45`、`plan.md:499`「矛盾したら TSK-346 が正」)
2. **拒否応答の形は要件書が既に閉じている**(B-1 の表)
3. **`operation_id` は既存の別語彙と衝突する** — リポジトリ内の `operation_id` は FastAPI のものではなく
   `contracts/authz/route-registry.json:40`(`enums.operation_ids`)の**管理操作 8 件の識別子**で、
   `scripts/check_authz_catalog.py:1946`,`:2011` が exact-set 検証している。
   `contracts/authz/*` は tenant-isolation のコア。経路識別子の正は `route_id`(`data-model.md:2439`,`:2449-2451`)
4. **ADR-003 D-11 が「フレームワークの route / API ハンドラ登録の列挙」を要求**している
   (`docs/adr/ADR-003-domain-calc-method.md:240`)。**ルータ登録機構は将来この列挙器に読まれる**ので、
   動的登録で静的に数えられない形にすると後で衝突する

#### C-6. `conftest.py` コア化と `pyproject.toml` 不変の出所

**conftest**: TSK-281「コア領域 paths のコード側充填」(計画承認 2026-09-02・徳光尋弥・重さ分類コア領域)。
- 登録理由 = 「**conftest 迂回**: 親 conftest の `pytest_ignore_collect` 等で保護テストの収集を外せる」
  (`docs/features/core-area-paths/plan.md:94`)。fail-closed 採用(同 `:110`)
- 発火した事故は PR #33 が core-guard 非発火のままマージされた件(同 `:20`)
- glob が広いことは既知の実測 — 「`backend/*conftest.py` の `*` が `/` を跨ぐので**全階層にマッチ**」
  (`docs/features/product-impl-unit-split/research.md:180`)
- DoD の根拠 = 地雷表 `plan.md:465`(「1 行でも編集したらコア。fixture は
  `backend/tests/api_fixtures.py` に置き**明示 import**」)+ リスク⑤ `plan.md:482` + テスト計画 `plan.md:569`

**計画に効く実測**: 既存 `conftest.py` の `anyio_backend` は U-00 の API テストでも必要になるが、
**それは既存 conftest 由来で足りる**(差分 0 行を守れる)。新規 fixture(`app` / `client` 等)だけを
`api_fixtures.py` へ置き、テストモジュールで明示 import する形が地雷表と整合する。

**pyproject**: `plan.md:462`「**依存追加禁止**(5 領域全部のコア)。**`[tool.fastapi] entrypoint =
"pitchlog.main:app"` を維持**。依存が要るなら**依存追加だけの単独 PR** に切る」。
`entrypoint` と `app` の出所は backend-skeleton(`docs/features/backend-skeleton/plan.md:124`、
`docs/worklog/2026-08-19-backend-skeleton.md:42-43`)。
**現物は app オブジェクト指定であって factory 指定ではない**(`backend/pyproject.toml:47-48`)ため、
`main.py` に `app = create_app()` を残せば `entrypoint` も既存テストの import も無変更で済む。

### D. core-guard の当たり判定(実測)

`scripts/core_guard.py:212-226`,`:249-280`: PR イベントでのみ作動。`.claude/core-areas.json` の
`guard_paths`(完全一致)と各 area の `paths`(`fnmatch.fnmatchcase`・**`*` は `/` を跨ぐ**)に
差分パスが 1 つでも当たったら、PR 本文に
`- [x] コア領域/検査経路の変更: 人間による逐行確認を実施した` が無い限り **exit 1**。

| パス | 判定 | 典拠 |
| --- | --- | --- |
| `backend/src/pitchlog/api/**`(新設) | **未登録 = 発火しない** | `.claude/core-areas.json` 全文の実測 |
| `backend/src/pitchlog/main.py` | **未登録 = 発火しない** | 同上 |
| `backend/tests/test_health.py` | **未登録 = 発火しない** | 同上 |
| `backend/tests/test_api_*.py`(新設) | **未登録 = 発火しない**(`test_authz*` を避ければ) | 同上・`plan.md:466` |
| **`backend/tests/conftest.py`** | **発火**(tenant-isolation の `backend/*conftest.py` に一致) | `.claude/core-areas.json:314` |
| **`backend/pyproject.toml` / `uv.lock`** | **発火(5 領域すべて)** | 同 `:128-129`,`:189-190`,`:263-264`,`:312-313`,`:366-367` |
| `contracts/authz/*` | **発火**(tenant-isolation) | 同 `:295` |
| `backend/tests/db/*` | **発火(5 領域すべて)** | 同 |

### E. エージェント間の食い違いと裁定

**① Notion カードの「経路予約 `/health` `/version` のみ」に原典が無い(decision-tracer)— 裁定: 指摘のとおり**

自分で原典を確認した結果:
- `plan.md:190` は「**分担・経路予約は design.md 4 節が正**」と述べるが、**design.md 4 節に U-00 の行は無い**
  (`design.md:67-108` を実読。4-1 は FR 主所有、4-2 は分担 5 件、4-3 は重複帰属 5 件で、いずれも器 3 本を含まない)
- `plan.md` 全体で `/version` が現れるのは `:309` の 1 箇所のみで、**「入口ではない」ことの例示**として出てくる。
  U-00 に経路を予約させる記述ではない
- 「経路予約」という語を単位に与えているのは **U-02 だけ**(`plan.md:198`)

→ **カードの当該行は起票時の具体化**であり、原典の裏付けは「`/health` `/version` は入口ではない」までしかない。
計画書では**「経路予約」という語を使わず**、`plan.md:309` を典拠に
「登録する経路は `/health` `/version` に限る(いずれも DB のデータへ到達しない)」と書くのが原典に忠実。

**② カードの DoD 10 件・「器の線引き 1〜3」に原典が無い(decision-tracer)— 裁定: 指摘のとおり**

リポジトリ全文 grep で「線引き」を追ったところ、**器の線引きの本体はどこにも存在せず**、参照は
`plan.md:290` と `docs/worklog/2026-09-13-product-impl-unit-split.md:101` の 2 箇所だけ
(どちらも「線引き 1」「線引き 3」と番号で参照するのみ)。
原典が単位別 DoD として定めているのは次の 4 件だけ:
横断要求(`plan.md:183`)/ 主所有 FR を 5 領域に当てた結果(`plan.md:182`・U-00 は 0 件)/
面切り失敗時の停止手順(`plan.md:252`)/ **`backend/tests/conftest.py` の差分 0 行**(`plan.md:569`)。

→ カードの DoD は**原典の 5 条件(`plan.md:267-273`)+ 地雷表(`plan.md:462-466`)を U-00 向けに具体化したもの**
と読める。計画書へ写すときは**条件番号と地雷表の行へ紐づけて**書き、出所が原典でない項目はそう明記する。

**③ OpenAPI の置き場が矛盾している(decision-tracer)— 裁定: 現時点では矛盾ではない**

- `plan.md:519`③「**生成した OpenAPI は `backend/` 配下に置き `contracts/` へ収載しない**」
- 設計書 4 章 `dev-harness-design-2026-08-07.md:184` は `contracts/` を「OpenAPIスキーマ・付録Eゴールデンベクタ」の置き場と記す
- `contracts/README.md` も「**将来は** …… OpenAPI スキーマを**収載します**」

原典を読んだ結果、**両者は時間軸が違う**。`plan.md:495-499` は `contracts/README.md` の「将来収載」を根拠に
「**現時点で正本は存在しない**」と明示したうえで、収載の決着先を **TSK-346** としている。
→ 正本(設計書)と計画書が同時点で逆を向いてはいない。ただし **U-00 が生成 OpenAPI をコミットするなら**、
将来の収載先との差は計画書で明示的に扱う必要がある。**そもそも FastAPI は実行時に生成するので、
生成物をコミットしない選択なら論点自体が立たない**。

**④ spec-checker と decision-tracer が一致している点**(食い違いなし・裏取り済み)

- エラー封筒の形式は未決定(両者一致)
- 拒否応答の形(404・理由コードなし・403 分岐なし)は既決(両者一致・要件書 `:645`,`:681` と台帳 `:39` で確認)
- `/version` に要件上の典拠は無い(両者一致)

## 未解決・申し送り

① **エラー封筒に `code` フィールドを持たせるか** — 持たせると FR-034(`:645`)の「理由コードを返さない」と
   衝突する形を器が既定として配ることになる。かつ 404/403 の決着先は TSK-346(`ADR-004:45`)。
   **器の封筒は「テナント/認可に関わる分岐を持たない」ことを明示し、写像は各単位・TSK-346 側へ残す**のが
   原典と整合する。計画書 4 章で明示的に扱う(設計判断そのものは /plan の仕事)。

② **`/version` を実装するか** — 要件に典拠が無く、バージョン情報の外部公開可否の規定も無い
   (要件書 2.2 Won't にも該当なし)。カード由来の項目なので、**実装する/しないを計画書で判断し理由を書く**。
   実装するなら「要件に規定なし・カード起票時の具体化」と性格を明記する。

③ **バリデーションエラーの封筒への写像は U-00 か U-01 か** — カードのスコープは U-00 に置いているが、
   原典の単位表 `plan.md:197` は **U-01(DTO 基盤)が「バリデーション写像」を持つ**と書く。
   面が重なるので計画書 2 章「やらないこと」で切り分ける。

④ **既存 `/health` の応答契約を変えるか** — `{"status": "ok"}` は PO 裁定由来で Phase 4 受入証跡が参照している
   (`docs/worklog/2026-08-19-backend-skeleton.md:42`)。器の共通応答モデルを `/health` にも適用すると
   この契約と既存テストを変えることになる。変えるなら計画書に明記が要る。

⑤ **DoD に「DB へ到達しない」を検査可能な述語で置く** — 非コア判定はこの 1 点に乗っている(C-2)。
   カードの「`api/app.py` `api/errors.py` `api/schemas/base.py` に `sqlalchemy` / `Session` / `engine` が
   出現しない」は、原典の 5 条件目(`plan.md:273` の `session.execute|select(|text(|engine.|raw_connection`)を
   具体化したもの。**ヘルスチェックの lifespan で DB セッションを張らない**ことも同じ述語に含める。

⑥ **ルータ登録機構は静的に列挙可能な形にする** — ADR-003 D-11 が「フレームワークの route /
   API ハンドラ登録の列挙」を要求する(`ADR-003:240`)。動的登録にすると将来の列挙器と衝突する。

⑦ **Web 技術調査は未実施** — FastAPI の app factory・例外ハンドラ・`RequestValidationError` の
   標準的な扱いについて外部情報が要るなら /research(Codex 委任)を併用する。本メモはリポ内調査のみ。
