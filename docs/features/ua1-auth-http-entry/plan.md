---
feature: ua1-auth-http-entry
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-10-09・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3ee93b75e68781c99d5bd3a15f6e83b5
branch: feature/ua1-auth-http-entry
created: 2026-10-09
計画レビュー周回: 3        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 2          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: U-A1 δ 認証の HTTP の入口(ログイン・PW 変更・ログアウト)

## 1. 背景・目的

Notion タスク: [TSK-470](https://app.notion.com/p/3ee93b75e68781c99d5bd3a15f6e83b5)(優先度 高・見積 8・親 = U-A1)
要件: FR-033(ログイン・レート制限)/ FR-036(PW 変更)/ FR-035(管理者ログインにもレート制限)/
NFR-010・NFR-011・NFR-019 — 正本は `../../requirements/requirements-pitchlog-2026-07-22.md`
調査: [research.md](research.md) / 暫定設計: [design.md](design.md)

U-A1 は α(正本)→ β(DB 層)→ γ(アプリ層)→ **δ(HTTP の入口)**の 4 単位に分かれている
(人間の決定 H-6・2026-10-03)。α〜γ はマージ済みで、**製品の外から認証へ到達する経路はまだ 1 本も無い**
(`backend/src/pitchlog/api/` の経路は `/health` と `/version` の 2 本だけ)。本単位がそれを開く。
**スコアラーはログインしないと記録を始められない。** リハーサルの経路上にある。

### 着手の根拠(ブロック中からの解除)

待ち合わせ 3 本のうち **γ のマージ**(#100)と **TSK-344**(#97)は開通済み。残る
「要件書 10 章のセキュリティ詳細の相談」は未実施だが、**正本が暫定設計の道を明示している**。

> 入口を開く前に、要件書 10 章の相談で決まった具体設計か、**人間が承認した暫定設計を持ち**、
> それが下の不変条件を満たすことを確かめる(`../../design/data-model.md:1787`)

要件書 10 章の当該行自体が「**FR-033 の暫定設計で着手**」である。
**本計画書の承認をもって、[design.md](design.md) 1〜4 節を「人間が承認した暫定設計」とする。**

### 人間の裁定(2026-10-09・山田正輝 — すべて本計画の推奨どおり)

| # | 項目 | 裁定 |
| --- | --- | --- |
| 1 | **レート制限の暫定設計** | **承認。** [design.md](design.md) 1 節の 4 案目 — **照合を先に済ませ、成功はロックを取らずに抜ける。失敗だけが予約票を取り、待ちは DB の外で消費する**。残余リスクは同 4 節 |
| 2 | **「試行が制限される」の読み** | **承認。「失敗した試行の応答速度に上限が掛かること」**と読む(根拠 = 不変条件 ② の「正しい資格情報による成功は対象外」)|
| 2-a | **不変条件 ④ から成功を外す読み** | **承認。** ④ の括弧書き「同時の失敗を数え落とさない」が条文の目的で、**成功は計数の対象ではない**([design.md](design.md) 5-2-b)|
| 3 | **閾値の置き場** | **承認。** **付録C には書かず** `system_settings` に置く([design.md](design.md) 3 節 E) |
| 4 | **ループバック TCP を締めるか** | **承認 — 締めない。** 運用文書に前提を書き、`_local_endpoint()` の判定は変えない。締めると `docker-compose.yml` だけでなく **CI の DB 試験(`127.0.0.1:5432` / `sslmode=disable`)も落ちる**(4 節) |
| 5 | **U-M1(#95)への依存** | **承認 — 依存に置く。** Cookie から提示値を取り出す処理は 2026-10-07 の裁定で U-M1 へ移っており、**ログアウトと PW 変更はそれが無いと叩けない**。δ が自前で足すと NFR-018 の二重実装になる |
| 6 | **配備先での確認を誰がいつ行うか** | **承認。** 本 PR では**手順の整備と、使い捨て Postgres を配備先に見立てた再現**まで。**実配備先での確認は人間の作業として DoD に残す**(`data-model.md:1550` が「入口を開く配備先」での確認を求めており、PR の中では実施できない) |

## 2. スコープ

### やること

- **レート制限の具体設計(暫定)の実装** — 直列化・逓増遅延・遅延の算定。β の計数の器への反映(DB 関数の置き換えを含む)
- **HTTP の入口 3 本** — ログイン / PW 変更 / ログアウト
- **`Set-Cookie` の発行と、スライディング延長への追随**
- **`route_id` の付与** — `contracts/authz/route-registry.json` / `http-route-matrix.json`
- **直叩きテスト**(12-4 の裁定 B)と **12-4 の判定記録**
- **`.claude/core-areas.json` への paths 登録**(`backend/src/pitchlog/api/*` 系)
- **行の累積の監視**
- **運用文書と、配備先に見立てた実測**
- **U-A1 の feature 文書 4 箇所の射程の現行化**と **`data-model.md` 12-8 節の本文 1 行の現行化**

### やらないこと

- **Cookie から提示値を取り出す処理と CSRF の検査** — 2026-10-07 の裁定で U-M1 のステップ 12 へ移った。
  δ は **`Set-Cookie` を出す側**だけを持つ。二重実装は NFR-018 違反
- **ログアウトの保護された入口** — 裁定 ⑫ により γ の `logout_token()` が持つ。δ は HTTP 経路だけ
- **要件書 10 章の相談そのもの** — 暫定設計で着手し、相談の結果が出たら置き換わる
- **`_local_endpoint()` の判定の変更** — 1 節の裁定 5
- **管理者ログインの入口**(FR-035)— 管理コンソールの単位の射程。カウント単位を混ぜないことだけ守る
- **`backend/tests/conftest.py` の変更** — DoD により差分 0 行

## 3. 影響する正本

**更新するもの**(各行にファイルパスを 1 つだけ書く — `check_plan_docs_sync.py` が行単位で抽出する)

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/design/data-model.md` | 12-4 の判定記録 + 12-8 節の本文 1 行の現行化 + 変更履歴表に 1 行(**版は上げない** — 7.6-3 前段) | PR レビュー |
| `docs/README.md` | `data-model.md` の最終更新日の現行化 + **新設する運用文書 2 本の索引行を足す**(`docs/ops/` は索引の掲載対象) | PR レビュー |
| `docs/ops/deployment.md` | **新設** — DB ログ設定の前提 / DB 接続の前提(ローカルか証明書検証付き TLS)/ レート制限の設定値の投入手順 | **/finalize-doc**(新設は敵対レビュー + 人間承認 — AGENTS.md 絶対規則 4) |
| `docs/ops/key-rotation.md` | **新設** — 署名鍵の入れ替え手順と実地確認の記録 | **/finalize-doc**(同上) |

**反映なし(明示)**

| 正本 | 判定 |
| --- | --- |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし** — 暫定設計の段階で要件書は動かさない。付録C の行は「未決(10章)」のまま |
| `docs/design/sync-protocol.md` | **反映なし** — 認証の入口は同期プロトコルの射程外 |
| `docs/adr/ADR-004-merge-gate-scope.md` | **反映なし** — 12-4 のゲートを使う側であり、条文は変えない |

**正本体系外だが同一 PR で更新するもの**(`/pr` 手順 2-2 の突合対象外)

| ファイル | 変更内容 |
| --- | --- |
| `.claude/core-areas.json` | `tenant-isolation` の `paths` へ 2 行 — **6.3-⑤ の敵対レビュー + 人間承認の対象** |
| `scripts/core_guard.py` / `tests/test_core_guard.py` | 回転式の窓口の宣言を新 2 件へ置換し、期待値を追随(**同一コミットで `.claude/core-areas.json` は触らない**) |
| `contracts/authz/route-registry.json` / `http-route-matrix.json` | 認証 3 経路 + `claim_dispositions` の付録C 由来の主張 |
| `contracts/authz/product/ddl-elements.json` / `function-bodies/` | `authn.login_attempt` の宣言と本体、旧 `authn.login` の除去 |
| `contracts/authz/product/probe-product-map.json` | 旧署名の対応行の追随 |
| `contracts/tenant_boundary/*` | 署名 pin と DB API 目録が**動く見込み**。動けば受理記録 1 件 |
| `tests/fixtures/tenant_boundary/positive/**` / `tests/test_check_tenant_boundary_bypass.py` | **【承認後の改訂 8】** `verified_tenant` へ公開関数を 1 本足すと、**allowlist の正例 fixture は exact-set で突き合わされる**(`check_tenant_boundary_bypass.py:1409-1418`)。**fixture は symbol ごとに 1 ファイル**(`verify_tenant_id` → `authz/verified_tenant.py` / `logout_token` → `authz/verified_tenant/__init__.py`)なので**新規 1 本が要る**。検査器の単体テストも `verified_tenant` の許可 symbol を 2 本で固定している(`:6269`)|
| `backend/src/pitchlog/api/*` / `backend/src/pitchlog/authz/verified_tenant.py` / 同 `runtime_contract.py` | 入口 3 本・公開境界・保護対象の生成モジュール |
| `backend/tests/test_api_conventions.py` | ルータの経路の表明のみ更新。**他の 4 表明は維持** |
| `contracts/authz/shared-preconditions.json` | **【承認後の改訂 12】** 同資産は `source_documents` で **`docs/design/data-model.md` の git blob digest を pin している**(`:19`・`document_role = mapping_target`)。**ステップ 1 が同文書を変えるので取り直しが要る。** `contracts/db/schema-manifest.json` と**同じ型の追随先がもう 1 つあった**ことを、develop の取り込み後の全件で見つけた。波及は無い(本資産を pin している資産は無く、oracle seal の入力にも封印対象にも含まれない)。**6 つの共有前提の対応付けには影響しない** — ステップ 1 が触るのは変更履歴行と 12-8 節の他タスク参照だけである |
| `docs/features/ua1-team-auth/design.md` / 同 `plan.md` / `docs/features/ua1-auth-db-layer/plan.md` / `docs/features/ua1-auth-app-layer/plan.md` | δ の射程から Cookie/CSRF の「読む側」を外し、U-M1 へ移った旨と典拠を書く |
| `docs/features/ua1-auth-db-layer/design.md` 6 節 | **【承認後の改訂 6】** 同節のキー表は `auth.team_login.max_failures` / `.lock_seconds` を挙げ、備考に**「具体設計でキーが変わり得る — δ が反映」**と明記している(`:114`)。本タスクが具体設計を確定させたので、**新 4 キー**(`.window_seconds` / `.throttle_threshold` / `.throttle_step_ms` / `.throttle_max_ms`)へ差し替え、旧 2 キーが**チームのログイン経路では読まれなくなった**ことを書く。**ステップ 5** |

## 4. 実装方針

**重さ分類 = コア領域**(テナント分離)。`contracts/authz/*`・`backend/src/pitchlog/authz/*`・
`backend/tests/db/*`・`docs/design/data-model.md` が該当し、**さらに `core-areas.json` 自体を変更する**
ので 6.3-⑤ の対象。→ ADR-001 により **sol xhigh・敵対レビュー必須・人間の逐行確認必須**。

暫定設計の本体・不変条件への適合・採らなかった案・残余リスクは [design.md](design.md)。
本節では実装上の順序だけを定める。

### 窓口(`core-areas.json`)を 2 コミットに分ける

**【承認後の改訂 1 — 2026-10-09・山田正輝】** 承認時の分割は誤っていた。実測で次が分かった。

**`AREA_PATH_ADDITIONS` は累積する台帳ではなく、「この PR が基線へ足す分」だけを宣言する
回転式の窓口である。** `validate_area_path_layers` の docstring(`scripts/core_guard.py:323-331`)—
「基線そのもの、または基線へ**宣言済み追加層を全件加えた形だけ**を受理する。部分追加、削除、置換、
並べ替え、未宣言追加はいずれも拒否する」。

- **既存の宣言は基線に入っている**ので、そこへ足して 5 件にすると「宣言 5 / 実際の追加 2」で拒否される。
  **置き換えが正しい**(JSON 側の既存 paths は消さない — 外すのは宣言からだけ)
- **`core_guard.py:30` の「先に固定する」はコミット順序の強制ではない。** CI(`ci.yml:55` →
  `core_guard.py:350`)が見るのは **merge-base と PR head の比較**で、コードが強制するのは
  **JSON と `core_guard.py` / テストを同一コミットで変えることの禁止**だけである。
  中間コミットの JSON 内容は検査しない

したがって分割は次のとおり。

- **ステップ 2** = `scripts/core_guard.py` の宣言を**新 2 件へ置換**し、`tests/test_core_guard.py` の
  期待値を追随させる。**`.claude/core-areas.json` は触らない**
- **ステップ 3** = `.claude/core-areas.json` **のみ**

**取り込み時点の develop は `tests/test_core_guard.py` が 2 件赤い**(#81 がマージ後に窓口を
空へ戻していないため — `8164c87a` では 215 passed、`f833154b` で 2 failed)。
**本ステップで宣言を自分の 2 件へ置き換えると、本ブランチ上ではこの赤も消える。**

### U-M1(#95)への依存(1 節の裁定 6)

**ログインは Cookie を読まない**(資格情報を本文で受け、`Set-Cookie` を返す)ので先に実装できる。
**ログアウトと PW 変更は要求から提示値を取り出す必要があり、その処理は U-M1 が持つ。**
**【改訂 11】その処理は `backend/src/pitchlog/api/request_presentation.py` の `require_presented_token(request) -> str` で、#95 の**ステップ 8**(本計画が書いていた「ステップ 12」は第 3 改訂前の古い番号)。**実装済み・未マージ**(`5899b9c2`)。Cookie(`__Host-pitchlog_token`)から提示値を不透明な文字列のまま返し、CSRF も同じ関数が見る。
ステップ表はこの順に並べ、**ステップ 8 以降を U-M1 のマージ後**に置く。

### ループバック TCP の扱い(1 節の裁定 5)

γ の計画書は DoD(`../ua1-auth-app-layer/plan.md:363`)で「締める」と書きながら、
3 節(`:150-155`)で「δ へ申し送る・判定内容は変えずに残す」としており**両立していない**。
本計画は**締めない**方を採る。8-2 節が求めているのは**配備先の接続の性質**であり、
開発と CI の接続形態は別の問題である。**運用文書に前提を書き、配備先での確認項目に入れる。**

### 検査器に値を直書きしない

閾値・ウィンドウ・遅延はすべて `system_settings` から読む(不変条件 ⑤)。
**検査器やテストに実値を直書きしない** — 基準を検査器のソースに持たせると、7.7-1 を満たさないまま
7.7-2 の充足を問えなくなる型を踏む。

### 実装ステップ(コミット単位)

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | **射程の記述を現行化する** — U-A1 の feature 文書 4 箇所から Cookie/CSRF の「読む側」を外し、U-M1 へ移った旨と典拠を書く。`data-model.md` 12-8 節の本文 1 行を番号で指さない形へ。変更履歴表に 1 行・`docs/README.md` | docs 系 3 検査が exit 0 / **変更履歴の既存行が 1 文字も動いていない** / 版が上がっていない / **【改訂 12】`data-model.md` を pin している資産の digest を取り直してある**(`contracts/db/schema-manifest.json` と `contracts/authz/shared-preconditions.json` の 2 件)/ **`check_shared_preconditions` と `test_schema_manifest` が exit 0** |
| 2 | **【承認後の改訂 13 — #95 の取り込みで不要になった】窓口を回す** — **本ステップは実施済みだが、#95(U-M1)のステップ 7 が `backend/src/pitchlog/api/*` と `backend/tests/test_api_*.py` を基線へ入れたため、δ の宣言は取り込みで落とした**(`scripts/core_guard.py` と `.claude/core-areas.json` は develop と一致)。δ の対象 3 ファイルはいずれも既存 glob に該当する。**宣言は回転式の窓口なので、足さずに済むなら足さない。** 以下は当時の記述 —  `scripts/core_guard.py` の `AREA_PATH_ADDITIONS["tenant-isolation"]` を**新 2 行へ置換**(既存の宣言は基線に入っているので外す)。`tests/test_core_guard.py` の期待値を追随させ、**実 JSON は「基線のまま」と「基線 + 新 2 件を同順で全件」の 2 状態だけ**を受けるようにする。**`.claude/core-areas.json` は触らない** | `uv run pytest tests/test_core_guard.py` **全件 green**(develop から引き継いだ 2 件の赤を含めて解消)/ `.claude/core-areas.json` の差分が 0 行 / `ruff check` `ty check` green |
| 3 | **【承認後の改訂 13 — 同上で不要になった】窓口を登録する** — **`.claude/core-areas.json` への登録は行わない**(基線が既に覆う)。以下は当時の記述 —  `.claude/core-areas.json` の `tenant-isolation.paths` の**末尾へ**、宣言と**同じ順序で** 2 行。**他のファイルは触らない**(同一コミットでの JSON とコードの同時変更は `core_guard` が拒否する) | `tests/test_core_guard.py` green / `backend/src/pitchlog/api/app.py` と `backend/tests/test_api_conventions.py` がコア領域と判定される |
| 4 | **`authn.login` を `authn.login_attempt` へ置き換える** — 試行元を受け、**照合を勧告ロックの前**に行う。**成功はロックを取らずにトークン行を作り `token_id` を返す**。**失敗だけが試行元のみを鍵にロックを取り**、失敗数から応答間隔を決め、予約票(`rate_limit_counters.locked_until`)を進めて**待ち時間を返す**。**待ちはアプリ側でコミット後に消費**し、DB 接続もロックも保持しない。遅延は**現ウィンドウ + 直前ウィンドウの失敗数の合計**で決める。**旧 2 引数版を除去**し、SQL manifest・`probe-product-map.json`・`runtime_contract.py` の `PROTECTED_FUNCTIONS`・生成モジュール・`backend/tests/db/test_product_authz_authn_app.py`・**`backend/tests/test_product_authz_catalog.py`**・**`backend/tests/test_product_authz_probe_product_map.py`**・**`backend/src/pitchlog/authz/product_authn_contract.py`**(認証関数の署名を完全一致で検査する期待集合)・**`backend/tests/db/test_product_authz_authn_security.py`**・**`backend/tests/db/test_product_authz_authn_limited.py`**(旧署名を直接呼ぶ)・**`contracts/tenant_boundary/runtime-authz-contract.json`**(生成器の入力資産。`protected_objects` に旧署名がある。**生成器の再導出で `runtime_contract_revision` と `current_identifiers` も動くが、それは本ステップの範囲**。ステップ 13 は**受理記録**〔PR 番号を鍵にする履歴 1 件〕であって版の繰り上げではない)を追随 | **旧 `authn.login(text,text)` が実 DB に存在しない**ことを試験で固定 / **成功が、先行する失敗が何件積まれていても一定時間で返る**(勧告ロックを取らないことを含めて確認)/ **同一試行元の失敗の応答が、間隔あたり 1 件に揃う** / **ウィンドウ境界をまたいだ 2 件が同じ鍵で計数される** / **待ちの間に DB 接続とロックを保持していない** / 戻り値がトークン行 ID である / 既存の DB テストが緑 |
| 5 | **設定値の投入経路と fail-closed** — **【改訂 6 で境界を明示】** 本ステップは**経路**を持つ: `ua1-auth-db-layer/design.md` 6 節のキー表を新 4 キーへ差し替え、妥当条件と fail-closed の挙動を書き、**未設定・不正値でログインを拒否する**ことの試験を置く(条文の逐語どおり — `data-model.md:1793`)。**運用文書(`docs/ops/deployment.md`)への手順の記載はステップ 12** — 新設は /finalize-doc ゲートで、本ステップでは文書を作らない | 4 キーのいずれかが欠落・不正ならログインが拒否される / **実値が検査器・テストに直書きされていない** |
| 6 | **ログインの HTTP 経路** — ルータ・スキーマ・`verified_tenant` 側の公開境界・`Set-Cookie` の発行。**【承認後の改訂 7】** `Max-Age` の出どころが無いので、`authn.login_attempt` へ **`OUT expires_at timestamptz` を加える**(発行済みの期限。アプリ用ロールは `tenant_tokens` も `setting_positive_integer` も直接叩けず、署名付き提示値にも期限が入っていないため、**関数から返す以外に経路が無い**)。ステップ 9 の「延長が起きた要求で `Set-Cookie` を出し直す」も同じ値を使う。**待ちは経路側で消費し、DB 接続を保持しない。かつ待ちと照合でイベントループを塞がない**。**【改訂 8】公開関数を 1 本足すことの追随先 6 件**: `backend/tests/test_api_app.py`(経路を 2 本で固定)/ `backend/tests/test_authz_verified_tenant.py`(`__all__` と公開名を 2 関数で固定)/ `backend/tests/test_authz_app_layer_surface.py`(公開操作・呼び出し元・DB 到達点を完全一致で固定)/ `contracts/tenant_boundary/base-allowlist.json`(TB005 — 境界内で DB API を使える symbol の目録)/ 正例 fixture 1 本の新設 / `tests/test_check_tenant_boundary_bypass.py`。**【改訂 9】公開関数の置き場は `verified_tenant.py` ではなく新モジュール `backend/src/pitchlog/authz/team_login.py` とする** — 検査器は fixture のパスからモジュール名を導き(`check_tenant_boundary_bypass.py:1456`)、`fixture` は symbol ごとに一意でなければならない(`:884`)。同じモジュール名を導けるパスは `X.py` と `X/__init__.py` の 2 通りだけで**どちらも使用済み**なので、**1 モジュールに許可 symbol は 2 本までという構造上の上限**がある。置き場を分ければ機構を変えずに済み、**`verified_tenant.py` の「署名を照合した ID だけを渡す境界」という既存の役割とも合う**(ログインは提示値を照合せず、資格情報から発行する) | 正しい資格情報で `Set-Cookie`(`__Host-pitchlog_token`・`HttpOnly`・`Secure`・`SameSite=Strict`・`Max-Age`)が返る / **提示値が応答本文・URL・ログに出ない** / `test_api_conventions.py` の DB 用語・`errors.py`・`operation_id`・403 の 4 表明が維持されている |
| 7 | **行の累積の監視** — **【承認後の改訂 10】** 本ステップは**経路**を持ち、**運用文書への記載はステップ 12**(ステップ 5 と同じ線)。`rate_limit_counters` は `function_only` でアプリ用ロールが直接読めないので、**`authn` に観測用の `SECURITY DEFINER` 関数を 1 本足す**。付与先は**管理関数所有用ロール**(`record_admin_login_failure` と同じ側。アプリ用ロールには与えない — 運用の関心でありログインの経路ではない)。返すのは**現ウィンドウ外の行数**と**カウンタ鍵(`scope_key`)の種類数**(**【確定ゲート 2 周目の指摘 5 で訂正】**「試行元の種類数」ではない — 鍵の前置きで絞らず表全体を数えるため、`team:` や `admin:` の鍵も含む)。典拠は `data-model.md:1797`「**チーム名の長さの上限(8-1)と累積量の監視は方式によらず置く**」。追随はステップ 4 と同じ 14 ファイルの型(SQL 本体 + manifest / `ddl-elements.json` / `probe-product-map.json` / `runtime-authz-contract.json` / `product_authn_contract.py` の `AUTHN_FUNCTION_GRANTEES`〔完全一致〕/ 生成し直した `runtime_contract.py` / 製品カタログと probe の試験 / DB 試験)| 監視の値が取得できる / **監視が物理削除を伴わない**(⑥)/ **アプリ用ロールからは実行できない** / 既存の DB 試験が緑 |
| 8 | **【U-M1 のマージ後】PW 変更とログアウトの HTTP 経路** — PW 変更は現行 PW 必須・**実行端末も再ログイン**(新トークンを返さない)。ログアウトは γ の `logout_token()` を呼ぶ | FR-036 の受入基準どおり / ログアウト後に同じ提示値が通らない / 旧 PW 由来のトークンが全経路で失効する |
| 9 | **Cookie の期限をスライディング延長へ追随させる** — 延長が起きた要求で `Set-Cookie` を出し直す。**【承認後の改訂 14 — 人間の裁定 2026-10-10・山田正輝】延長後の期限の出どころが無い**ので、**`authn.verify_token(uuid)` に `OUT expires_at timestamptz` を足す**(現状は `RETURNS uuid` で、期限を返さない。`tenant_tokens` はアプリ用ロールから直接読めないため、**関数から返す以外に経路が無い** — 改訂 7 で `login_attempt` に同じ理由で足したのと同じ型)。期限は **`verified_tenant.verify_tenant_id`(γ)→ `repositories.tenant_context_issuance.issue_tenant_context_from_presented_token`(#95)→ `api.tenant_access.require_tenant_access`** の 3 層を通して経路へ届ける。**却下した案**: アプリ側で `auth.token_ttl_seconds` を読んで計算する — 「期限 = 今 + TTL」が DB とアプリの 2 箇所に出て、時計のズレ分だけ Cookie の寿命が前後する。追随は改訂 7・ステップ 4 と同じ型(SQL 本体 + `manifest.json` / `ddl-elements.json` / `probe-product-map.json` / `runtime-authz-contract.json` / `runtime_contract.py` / `product_authn_contract.py` / 製品カタログと probe の試験 / DB 試験)に、**上記 3 モジュールと公開境界の完全一致の表明**を加える | DB 側の期限が延びた要求で Cookie の `Max-Age` も更新される / 延長が起きない要求では `Set-Cookie` を出さない / **`pg_get_function_identity_arguments` は OUT 引数を含む**ので、署名を固定している試験の期待値を**緩めずに**新しい形へ更新する |
| 10 | **【承認後の改訂 15 — 2026-10-10】本ステップは 3 段・3 コミットに分ける**(件名は `(ステップ 10/13 第1段)`〜`第3段`。#95 が計画の改訂で同じ分割を行った前例に倣う — `fab1acc6`「ステップ 2 を 3 本に分け oracle の追随と再封印を足す」)。**第1段** = 資産と検査器の期待集合(`98ad97de` 相当)/ **第2段** = `oracle_commit` を第1段の コミットへ進め digest 連鎖を追随(`7c3e6d9c` 相当)/ **第3段** = `frozen-baselines.json` へ `oracle_input` の記録 1 件 + `--reseal-oracle` で再封印(`2e9fe0cf` 相当)。**あわせて、経路種別の値域を広げる**(人間の裁定 2026-10-10・山田正輝): **`route_kind` に `authentication_entry` を新設**し、δ の 3 経路を exact-set で固定する。**既存種別へは相乗りしない** — `record_and_aggregate` は検査器が 6 本の exact-set で固定し (`check_authz_catalog.py:2142`)、かつ `design` origin を要求する(`:2361`)が、δ の 2 主張は付録C 由来で `requirement` である。**検査器は 3 箇所を揃えて広げる** — `ROUTE_KINDS`(`:303`)/ `expected_keys_by_kind`(`:2328`)/ `disposition_by_kind`(`:2706`)。**3 つとも `ROUTE_KINDS` との一致を assert している**。**【改訂 11 — #95 の取り込み後へ移す】`route_id` の付与** — `route-registry.json` と `http-route-matrix.json` へ 3 経路。**`claim_dispositions` は `routed` へ**(`in_registry` という値は存在しない — `check_authz_catalog.py:313` の `CLAIM_DISPOSITIONS = {"out_of_registry","routed"}`)。**付録C 由来のうち δ のものは 2 件だけ**(`table_row-004` トークン有効期限 / `table_row-006` レート制限の閾値。`blockquote-001` は FR-037、`table_row-009/010` は FR-041 の単位)。**2 資産は oracle seal で既存 commit に固定**されており、#95 が実際に通した 3 段(入力と lock → oracle の差し替えと**人間の再確認** → 履歴と再封印)を踏む。**#95 がマージされると `oracle_commit` が `1f32e12a` → `cc949c69` へ動く**ので、**先に貼ると貼り直しが 2 回**になる。追随先に `route-registry.lock.json` / `http-route-matrix.lock.json` / `oracle-seal.lock.json` / **`tests/fixtures/authz_claims/route-registry{,.lock}.json`** を含む | `matrix_route_id = "HTTP:" + route_id` の規則を守る / `operation_id` 集合と交わらない / `check_authz_catalog` ほか契約検査が緑 |
| 11 | **直叩きテストと越境テスト** — 12-4 の裁定 B。**失敗応答が、存在するチーム名と存在しない名前で同じ照会・同じカウンタ更新・同じ cost 12 の照合を通る**ことを確かめる | 3 経路すべてに直叩きテストがある / 本文・ステータスが一致し、**実行される照会と `crypt` の回数が一致する** / **行の有無による実行時間の差を、存在する名前と存在しない名前それぞれ 30 回の計測で突き合わせ、中央値の差が遅延の最小段(250ms)未満であることを示す** / NFR-019(b) の該当分 |
| 12 | **運用文書・配備先の実測・12-4 の判定記録** — DB ログ設定の前提と**実際の出力の確認**(使い捨て Postgres を配備先に見立てる)/ 署名鍵の入れ替えの**実地確認 1 回** / 設定値の投入手順 / DB 接続の前提。判定記録は **PR 本文に「誰が・いつ・どの実スキーマで green を確認したか」と入口識別子**、**【確定ゲート 1 周目の指摘 9 で訂正】** `route_id` と method/path の組は **`data-model.md` 本体に書かない** — 経路識別子の正は `contracts/authz/http-route-matrix.json` の `route_id`(`data-model.md:2531`)で、**入口ごとの組は通過判定の記録として PR 本文へ書く**(同 `:2665`) | 束縛値が DB のログに出ないことを**使い捨て Postgres の実測で**示す / 鍵の入れ替えを 1 回実施した記録がある / 判定記録が 12-4 の要求 4 項目を満たす / **新設した運用文書 2 本が `docs/README.md` の索引に載っている** / **実配備先での確認は未実施として DoD に残り、その旨が運用文書に書かれている**(1 節の裁定 6) |
| 13 | **凍結資産の受理記録**(動いた場合・PR 番号の確定後) | 検査器 `--base-ref origin/develop` が 0 件 / `tests/test_frozen_*` green / 予約 marker 不在 |

**既知の赤窓**: ステップ 4 以降、凍結資産が動いた時点からステップ 13 まで `frozen_history` 系ゲートは赤。
**各ステップの合格条件からこのゲートを明示的に除外する**(書かないと `/implement` が止まる)。
`acceptance_id` は PR 番号と突合されるため、**ステップ 13 は PR 作成後**になる。

## 5. DoD

Notion カードの DoD と同期。

- [ ] 採ったレート制限の具体設計が `data-model.md` 8-6 節の不変条件 ①〜⑥ を満たす
      (とくに ① 第三者の失敗連打で正規利用者を締め出せない)— 適合表は [design.md](design.md) 2 節
- [ ] 失敗応答の内容と時間差がチーム名の存在で変わらない(FR-033)—
      **同じ照会・同じカウンタ更新・同じ cost 12 の照合を通ることで示す**
- [ ] NFR-019 の越境テスト(HTTP 層)・入口を外から直接叩くテスト(12-4 の裁定 B)
- [ ] シークレットをハードコードしない・**提示値をログ・応答本文・URL に出さない**(NFR-014 / `data-model.md:1678` — P0)
- [ ] `core-areas.json` への paths 登録を本 PR で行う
- [ ] `backend/tests/conftest.py` の差分が 0 行
- [ ] **【人間の作業】実配備先での確認** — DB の `log_parameter_max_length` 2 設定と実際のログ出力 / DB 接続がローカルか証明書検証付き TLS / 署名鍵の入れ替え手順の実地確認(`data-model.md:1550`。**PR の中では実施できない** — 1 節の裁定 6)
- [ ] pytest / ruff / ty green
- [ ] 物理削除しない / テナント分離を全機能に適用 / 自動エスケープ

## 6. テスト計画(NFR-019)

| 種別 | 対象 | 置き場 |
| --- | --- | --- |
| **単体**(DB なし) | 試行元の正規化(IPv4 / IPv6 の /64 / 取得不能で `src:unknown`)/ `Set-Cookie` の属性 / 応答スキーマに提示値が出ない / 遅延の段の算定 | `backend/tests/test_authz_*.py`・`backend/tests/test_api_*.py` |
| **単体**(実 DB) | 直列化(並行試行が 1 件ずつ)/ ウィンドウ境界で遅延が消えない / 設定値の fail-closed が**ログインの拒否**になる(4 キーのいずれかが欠落・不正) / 旧 `authn.login` の不在 / 発行済みトークンが無影響 | `backend/tests/db/test_*.py`(`pytestmark = pytest.mark.requires_db`) |
| **(b) 越境アクセステスト** | **発効する** — 本単位が「製品の外からの要求がその経路を通ってデータへ到達できる」状態を作る(NFR-019(b))。列挙された組合せを 1 件も減らさない | `backend/tests/db/` |
| **直叩き**(12-4 裁定 B) | ログイン / PW 変更 / ログアウトの 3 経路を製品の外から叩く | `backend/tests/test_api_*.py` + 実 DB 側 |
| **故障系** | 設定値の欠落・不正 / 試行元が取得できない / 署名鍵の不備 / 並行試行 | 上記に分散 |
| **一致性(NFR-018)** | **対象外** — 認証は NFR-018 の列挙に含まれない |

**既存の形に合わせる**: DB を使わないものは `backend/tests/test_*.py` 直下、使うものは
`backend/tests/db/test_*.py`。**同名ファイルを両側に置くのが既存の規則**
(`test_authz_verified_tenant.py` と `test_authz_log_safety.py` が前例)。
