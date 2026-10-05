---
date: 2026-10-04
topic: U-A1 β — 認証の DB 層(TSK-468)
branch: feature/ua1-auth-db-layer
---

# 作業ログ: 2026-10-04 U-A1 β — 認証の DB 層(TSK-468)

## やったこと

## 決定

## 未決・次の一歩

## 計画レビュー 1 周目(`codex_run.py review adversarial`)

**P0 1 / P1 12 / P2 1 — 全件採用**。

| # | 重大度 | 要旨 | 反映先 |
| --- | --- | --- | --- |
| 1 | P0 | PW 変更に有効なトークンの検証が無い(失効済み ID と現行 PW で更新できる) | design 5 節(`verify_token` と同じ有効性条件を先に確かめる)・plan ステップ 8・6 節 |
| 2 | P1 | 正規化の案 B は「DB の 1 つの関数」に反する | design 3 節(B を採らない・単一関数を保てなければ人間に上げる) |
| 3 | P1 | 計数の設定値の未設定で拒否する試験が無い | design 5 節・plan ステップ 8 |
| 4 | P1 | 存在秘匿を戻り値だけで判定 | design 8 節(計数と `crypt` 呼び出し回数の観測)・plan ステップ 1・8 |
| 5 | P1 | 「他テナントの ID を拒否」は認証前の契約と合わない | plan 6 節(ID 非列挙・テナント食い違い不可・署名は γ) |
| 6 | P1 | ステップ 6 のコミットで派生資産が古くなり CI が red | plan ステップ 6・11(同じコミットで digest と突合シート) |
| 7 | P1 | ステップ 7〜9 で P4 が red | plan ステップ 7(資産一式 + `rederive` + 受理記録を同じコミット)・design 8 節 |
| 8 | P1 | 最低要求④を件数検査に置き換えていた | plan ステップ 7・10・J-2・design 8 節(④は適用判定、0 件試験は付与先 exact の構成検査へ) |
| 9 | P1 | `authn_crypto` が移行バッチ用ロールの EXECUTE 0 件の検査対象外 | plan ステップ 3(対象スキーマを資産から導く)・7(全メンバー関数の `PUBLIC` 剥奪) |
| 10 | P1 | 拡張が実カタログと照合されない | plan ステップ 3(`pg_extension` と所属スキーマの exact) |
| 11 | P1 | 資産から消す変異はトートロジー性を証明しない | plan ステップ 4・design 8 節(独立の期待集合・新規適用で red) |
| 12 | P1 | 固定件数「6 か所」の見積もり | plan ステップ 4(全数探索して一覧を記録) |
| 13 | P1 | Notion DoD の同期工程が無い | plan 5 節 DoD(承認時に更新・突合を記録) |
| 14 | P2 | 種別名の食い違い | design(`definer` に統一) |

## 計画レビュー 2 周目

**P0 0 / P1 9 / P2 1 — 全件採用**。

| # | 重大度 | 要旨 | 反映先 |
| --- | --- | --- | --- |
| 1 | P1 | 「6 ロール」の照合は製品資産(4 → 5)と一致しない(6 = 製品 5 + 移行バッチ用 1) | plan ステップ 4・design 2 節(段階化・移行バッチ用は別の期待集合) |
| 2 | P1 | migration の正規化関数が `migration_trigger` の照合に入らない | plan ステップ 4(トリガ / 通常関数の区別)・6 |
| 3 | P1 | ステップ 3 の拡張要素が要素の検証と接続していない | plan ステップ 3(`extensions` を任意の要素群に・正例と負例) |
| 4 | P1 | 不変条件①を既存トークンの生存だけで判定 | design 7 節(β はロックを適用しない — 具体設計は δ)・plan ステップ 8 |
| 5 | P1 | 照合のコストを検証しない | design 8 節(実もダミーもコスト 12)・plan ステップ 8 |
| 6 | P1 | 64 文字上限が migration 後の挿入を拘束しない | design 4 節(`CHECK` 制約)・plan ステップ 6 |
| 7 | P1 | 世代更新と検証の並行契約が無い | design 9 節(ロック順と確定境界)・plan 6 節 |
| 8 | P1 | 中間コミットの受理記録に承認境界が無い | plan 4 節・ステップ 7/10/11・design 8 節(受理記録は人間の受理後にステップ 11 で 1 回。中間は受理記録の検査だけ red を許容) |
| 9 | P1 | リスク欄 R3・R4 が反映に追随していない | plan 8 節 |
| 10 | P2 | 故障系の「失敗」が曖昧 | plan 6 節(認証失敗を `NULL` で返し計数が同じコミットで残る) |

## 計画レビュー 3 周目

**P0 2 / P1 7 / P2 0 — 全件採用**。

| # | 重大度 | 要旨 | 反映先 |
| --- | --- | --- | --- |
| 1 | P0 | `change_password` の共有ロック → 更新ロックの昇格が相互待ちを生む | design 9 節(最初から `FOR UPDATE`・ロック保持を強制する並行試験) |
| 2 | P0 | `now()` はトランザクション開始時刻なので、ログアウト後に検証が古い時刻で延長し得る | design 9 節(ロック後の `clock_timestamp()`・ログアウトが先にロックを持つ順序の試験) |
| 3 | P1 | ステップ 6 の正規化関数の資産宣言で P4 が red | plan ステップ 6(同じコミットで `rederive`・P4 を合格条件に) |
| 4 | P1 | 「同じ照会」を判定できない | design 8 節(`pg_stat_user_tables` の差分)・plan ステップ 1・8 |
| 5 | P1 | 64 文字の上限がログイン入力に掛かっていない | design 5 節(`login` は 65 文字超を `NULL`)・plan ステップ 8 |
| 6 | P1 | 管理者用の設定キーが未確定 | design 6 節(全件列挙・値の妥当条件・fail-closed) |
| 7 | P1 | 初期発行と管理者計数の受入試験が無い | plan ステップ 9 |
| 8 | P1 | ステップ 1 の実測結果をステップ 6 へ反映する経路が無い | design 10 節・plan ステップ 1(案 A 以外なら計画を更新して再承認) |
| 9 | P1 | 決定済みの 64 文字が正本の実装追随から漏れる | plan 3 節・ステップ 6(8-1 節に確定値) |

## 計画レビュー 4 周目

**P0 0 / P1 8 / P2 0 — 全件採用**。P0 の推移 1 → 0 → 2 → 0。

| # | 要旨 | 反映先 |
| --- | --- | --- |
| 1 | `core-areas.json` と `test_core_guard.py` を同じコミットで変えると core-guard が拒否 | plan ステップ 2(登録だけ)・3(試験の行) |
| 2 | 逐行確認前の core-guard green と早期 draft PR が成立しない | plan 4 節・ステップ 2/12/13(draft PR を先に開かない・core-guard はステップ 12 以降) |
| 3 | 認証関数所有用ロールに `public` の `USAGE` が無い | plan ステップ 7・design 1 節(`USAGE` と正規化関数の `EXECUTE`) |
| 4 | 65 文字超だけが一様な失敗経路から外れる | design 5 節(長さで分岐しない)・plan ステップ 8 |
| 5 | 表の走査回数では「同じ照会」を検証できない | design 8 節・plan ステップ 1/8(`pg_stat_statements` の queryid と回数) |
| 6 | 不変条件 ② の担当が計画内で矛盾 | plan J-3(計数と戻り値は β、ロックの判定と応答は δ) |
| 7 | リセットのポリシー試験が無い | plan ステップ 9 |
| 8 | 受理した最終状態とコミットを結び付けていない | plan ステップ 12/13(S・H・D を固定し、一致した場合だけ記録 — PR B の前例) |

## 計画レビュー 5 周目

**P0 0 / P1 10 / P2 0 — 全件採用**。P1 の推移 12 → 9 → 7 → 8 → 10(減らない)。**人間の判断(2026-10-04): 5 周目を反映し、差分の実効確認 1 周で承認へ**(機構の細部は実装の各ステップの実測と、コア領域の実装後の敵対レビュー・逐行確認で拾う)。

| # | 要旨 | 反映先 |
| --- | --- | --- |
| 1 | core-guard は宣言済みの追加層しか許さない | plan ステップ 2/3(既存の paths で全件一致なら登録しない・一致しなければ先に追加層を宣言) |
| 2 | ステップ 12 では core-guard も red | plan 4 節(人間の確認を待つ 2 検査を例外として明記) |
| 3 | `/pr` 後のステップ 13 が標準経路で実行できない | plan ステップ 13(例外経路として Claude が直接 1 コミット・前例 PR B) |
| 4 | D の算出規則・代替値・再照合が無い/早期記録の文言が残る | plan 4 節・ステップ 12/13(PR B と同じ規則・コミット後に再照合) |
| 5 | CI の試験クラスタに `pg_stat_statements` の条件が無い | plan ステップ 1/8・design 8 節(事前読み込み・`track = all`・負例) |
| 6 | `rederive` が凍結識別値の更新を検証しない | plan ステップ 5(revision・`current_identifiers`・生成物) |
| 7 | 計数の一意索引を選んだ場合の反映経路が無い | plan ステップ 1・design 7/10 節 |
| 8 | β のテスト計画にロック中の試験が残る | plan 6 節・ステップ 8(ロック中は δ) |
| 9 | 過去のウィンドウを参照しない義務の試験が無い | plan ステップ 8・6 節 |
| 10 | 「前後の空白」の範囲が未確定 | design 3 節(White_Space)・plan 3 節/ステップ 6(8-1 節に追記) |

## 計画レビュー 6 周目(差分の実効確認だけ — 人間の指示)

**P0 0 / P1 5 / P2 0 — 全件採用**(いずれも 5 周目の反映の詰め)。core-guard の例外を逐行確認チェック未完了だけに限定 / 受理の直前に fetch と D の再計算 / `pg_stat_statements` の対象を `disposable_postgres_cluster()` の起動引数に / ステップ 1 の合格条件に一意索引の場合の再承認 / 過去ウィンドウの非参照を `EXPLAIN` で確かめる。

**計画レビューはここで終える**(人間の判断)。累計 6 周・指摘 56 件・全件採用・不採用 0。

## ステップ 1 の実測(2026-10-05)

詳細は design.md 10-1 節。使い捨てコンテナ(PG 17.11・試験クラスタと同じ initdb 引数)と、`origin/develop` の使い捨て worktree で測った。測定用の SQL・スクリプトはリポジトリに入れていない。

- ① **案 A は移行バッチ用ロールに正規化関数の `EXECUTE` を要る**(生成列への `INSERT` と `UPDATE … SET name` が `permission denied`)。同ロールの関数 `EXECUTE` は空であることを要求されている(`product_catalog.py:865`)→ **案 A1 を提案し、計画を更新**(J-4)。`alembic check` は生成列の式の違いを検出しない
- ② 直列化: 直列化なしは 15 行に重複。勧告ロックと一意索引はどちらも数え落とし 0 → **勧告ロックを提案**(J-5)
- ③ 受理記録の無い中間コミット: red は **tenant-boundary-bypass ジョブの受理記録の検査**と **`test_frozen_archive.py` の corpus digest(12 件)**。後者は同じコミットで再 pin すれば避けられる → 計画 4 節に規則を足した。迂回の走査はステップ 13 まで走らない
- ④〜⑥ `pg_stat_statements`(`track = all`)で失敗 3 種の関数内 SQL が同じ `queryid`・同じ回数、`crypt` は `track_functions = all` で 1 回ずつ。既定の `top` は関数内の SQL を数えない
- ⑦ 「前後の空白」= Unicode `White_Space` の 25 文字を `btrim` の第 2 引数で除く。小文字化は `pg_c_utf8`(glibc の版に依らない)
- 調査用サブエージェント(③)は前のセッションの終了と、その後の人間の停止で中断した。③ は自分で測り直した。使い捨ての作業ブランチ `probe/frozen-red`・`probe/merge`(ローカルのみ・未 push)は、強制削除がフックで禁止のため残っている
- **計画を更新し(承認欄を「未」へ)、再承認を待つ**(design.md 10 節の規則)

## 計画レビュー 7 周目(ステップ 1 の実測による更新の差分だけ)

**P0 0 / P1 4 / P2 0 — 全件採用**。

| # | 要旨 | 反映先 |
| --- | --- | --- |
| 1 | 案 A1 の安全条件(純関数・`SECURITY INVOKER`)が検査になっていない | plan ステップ 6・design 10-1 ①(属性のカタログ照合と変異試験・差し替え経路が無いことの維持) |
| 2 | 勧告ロックを全計数経路が同じ鍵で通る保証がない | plan ステップ 8・9・design 10-1 ②(鍵・照会・更新に同じ値を使い照会の前に取る・両関数で行が無い状態からの並行試験) |
| 3 | 中間コミットで迂回の走査が走らない | plan 4 節・design 10-1 ③(履歴の検査だけを差し替えた走査を各ステップで一時実行し、出力を worklog に残す) |
| 4 | ステップ 7 の「全スキーマ」とステップ 3 の検査範囲の食い違い | plan ステップ 7(資産に宣言した製品スキーマの全域) |

**再承認(2026-10-05・山田正輝)**: J-4 = 案 A1・J-5 = 勧告ロック(どちらも推奨どおり)。ステップ 2 へ進む。

## ステップ 2(2026-10-05)

- `origin/develop`(`85fce8a7` — #87 のマージ後)を取り込んだ(`2fc11f9b`・衝突 0 件)
- 新しく作るファイルを `core-areas.json` の paths と照合 → **全件一致・JSON は登録しない**(design.md 11 節)。backend の新しい試験は `test_authz_*`・`test_product_authz_*`・`product_authz_*`・`db/*` の名前に限る

## ステップ 3(2026-10-05)

- Codex へ委任(`codex_run.py implement`)。**モデルの混雑(`Selected model is at capacity`)で 4 回中断**した(OpenAI 側の混雑と判断 — 同じ秒に別タブも弾かれている。手元に親を失った Codex は無かった)。最後は `--resume` で同じセッションを継続して完了
- 実現の要点と後続への注意は design.md 12 節
- 確認(Claude が実行):
  - backend: `ruff check`・`ruff format --check`・`ty check` green / 影響範囲の非 DB 試験 230 件 green / ランタイム契約の生成器 `check` rc=0
  - DB 試験(`tests/db/` の製品 authz 5 ファイル): 1 回目は 47 passed・1 error(故障注入 `AFTER-HELPER-FUNCTION-DROP` の後片付けのエラー)。単独 7 件・同じ組の再実行 47 件はどちらも全件 green で再現しなかった
  - ハーネス: `ruff check .`・`ty check` green / `tests/test_check_authz_catalog.py`・`tests/test_check_authz_function_bodies.py`・`tests/test_frozen_archive.py` 203 件 green / `check_authz_catalog`・`check_authz_function_bodies`・`check_failure_injection_points`・`check_shared_preconditions` rc=0
  - **迂回の走査**(受理記録の検査だけを差し替えた一時実行 — 計画 4 節 ①): `tenant-boundary bypass check: ok`(rc=0)。差し替えない元の検査も rc=0(このステップは資産を変えないので受理記録の不一致は生じない)
  - 変更 16 ファイルは全件がコア領域の paths に一致(design.md 11 節の置き場の規則どおり)

## ステップ 4(2026-10-05)

- Codex へ `--resume` で委任(混雑による中断なし)。全数探索の一覧・独立の期待集合と段階化・migration 由来の関数の 2 種別は design.md 2-1 節
- **ステップ 6 へ持ち越した判断**: `migration_function` の取り外しは何もしない実装 → 正規化関数へ付与した後の `DROP ROLE` の失敗と、往復で元へ戻らないおそれ(推論)。ステップ 6 で 0027 の `REVOKE` と合わせて決め、往復試験で確かめる(design.md 2-1 節)
- 確認(Claude が実行):
  - backend: `ruff check`・`ruff format --check`・`ty check` green / 影響範囲の非 DB 試験 355 passed・4 skipped(切り替えドライランの既存のスキップ)/ 生成器 `check` rc=0
  - DB 試験(`tests/db/` の製品 authz・ランタイム契約の統合 等 9 ファイル): 94 passed
  - ハーネス: `ruff check .`・`ty check` green / `tests/test_check_authz_catalog.py`・`tests/test_check_authz_function_bodies.py` 167 passed / `check_authz_catalog`・`check_authz_function_bodies`・`check_failure_injection_points`・`check_shared_preconditions`・`check_tenant_boundary_bypass` rc=0
  - **迂回の走査**(受理記録の検査だけを差し替えた一時実行): `tenant-boundary bypass check: ok`(rc=0)
  - 新しいファイル `backend/src/pitchlog/authz/product_role_contract.py` は `backend/src/pitchlog/authz/*` に一致(design.md 11 節)

## ステップ 5(2026-10-05)

- Codex へ `--resume` で委任(中断なし)。`rederive` と受理記録の雛形 → design.md 13 節
- `origin/develop` が取り込み後に進んでいた(#92 — 台帳の docs だけ)。β への影響なし。**取り込みは計画 R4 どおりステップ 13 の直前の 1 回にする**。中間の `rederive` の比較元は `git merge-base HEAD origin/develop`
- 確認(Claude が実行): backend の `ruff`・`format --check`・`ty` green / ランタイム契約の試験 101 passed・4 skipped / 生成器 `check` rc=0 / **`rederive --base HEAD` rc=0(差分 0)** / ハーネス `ruff`・`ty` green・`tests/test_frozen_history.py`・`tests/test_frozen_archive.py` 133 passed / `check_tenant_boundary_bypass` ok / **迂回の走査(差し替え版)** ok / `contracts/**` の差分 0

## ステップ 5 の是正(2026-10-05)

- 迂回の走査(差し替え版)が `runtime_contract_acceptance.py` の `importlib.import_module` を TB005 で検出。**ステップ 5 の確認時はファイルが未追跡で走査の対象外だった**(走査はリポジトリの追跡ファイルを見る)→ 静的 import に直し、`337bceaa`(ステップ 5/13 是正)。**以後、新しいファイルは `git add -N` で追跡に入れてから走査する**

## ステップ 6(2026-10-05)

- Codex へ `--resume` で委任(中断なし)+ 差し戻し 1 回(schema manifest の生成列の列定義)。決定は design.md 14 節
- Claude の分: data-model.md 3-4 節の 2 行を主表へ移した(「実装」列を外し、他の 4 列は不変)・8-1 節に上限 64 文字と空白 25 文字を書いた / digest 2 か所(`shared-preconditions.json` blob `f93b06e5` → `90659ae9`・`schema-manifest.json` SHA-256 `6f5b6d59…` → `7a75921e…`)/ 比較 corpus の digest の再 pin(`2f649f73…` → `e4d59d79…`)
- **受入突合シート**: `--carry-judgments-from HEAD` で再生成 → 行数は不変、**判定が空になった 11 行**(N3 10 行 = 正本の書き足し・tenants の更新可能列の `retired_at`・表の移動による 027/028 の入れ替え / N7 1 行 = 054)。**旧判定の引き継ぎ(N3 = 対象外 10 行・N7 = 一致 1 行。027 と 054 の理由は実装に合わせて更新)を人間が承認(2026-10-05・山田正輝「承認する」)**
- 確認(Claude が実行):
  - backend: `ruff`・`format --check`・`ty` green / 非 DB 試験 413 passed・4 skipped(是正後に `test_schema_manifest.py`・ランタイム契約の試験 115 件を再実行し green)/ 生成器 `check` rc=0 / `rederive --base $(merge-base)` rc=0(収束済み — revision 8 → 9)
  - DB 試験: 131 passed(migration・往復・スキーマ監査・製品 authz・移行バッチ用ロール・正規化関数ほか 14 ファイル)/ 是正後に `test_schema_audit.py`・`test_alembic_migrations.py`・`test_product_authz_normalize_function.py` を再実行し 32 passed
  - ハーネス: `ruff`・`ty` green / `test_check_authz_catalog.py`・`test_check_authz_function_bodies.py`・`test_orm_acceptance_sheets.py`・`test_frozen_archive.py` 216 passed / `test_frozen_history.py` 含む凍結資産 133 passed / 検査器 5 本 rc=0(`check_authz_catalog`・`check_authz_function_bodies`・`check_failure_injection_points`・`check_shared_preconditions`・`check_docs_status`)
  - **迂回の走査**(差し替え版・新しいファイルを追跡に入れて): `ok` / 元の検査は受理記録の検査の 1 件だけ(「履歴末尾と 7 資産の識別値が不一致」— design.md 14 節)

## ステップ 6 の是正(2026-10-05)

- **迂回の走査は作業ツリーでなく HEAD のコミット(と `base...HEAD` の差分)を読む**(`check_tenant_boundary_bypass.py:5647` の `git show`・`:807`)。**コミット前に走らせた確認は 1 つ前のコミットを見ていた** → ステップ 6 の `models.py:69`(`sqlalchemy.text` — TB005 は変更行だけを見る)を見逃した。ステップ 6 のコミットを一時 worktree で走査して再現を確かめ、`column("retired_at").is_(None)` に直して `6f9bd072`(ステップ 6/13 是正)。是正後の HEAD で走査 ok。この時点の HEAD の走査でステップ 3〜6 の他の違反は 0 件
- **以後、迂回の走査はコミットの後に走らせ、違反があれば是正コミットを足す**

## ステップ 7(2026-10-05)

- Codex へ `--resume` で委任(中断なし)+ 差し戻し 1 回(DB 試験 5 件 — 拡張の重複追加・ロール削除の試験が適用で先に失敗・旧い「0 件」の表明・危険ロールの所有者照会・保護スキーマ 2 件の固定。探索で適用器の DB 試験の指紋も直した)。決定は design.md 15 節
- 確認(Claude が実行):
  - backend: `ruff`・`format --check`・`ty` green / 非 DB 試験 400 passed・4 skipped / 生成器 `check` rc=0 / `rederive` 収束(revision 9 のまま)
  - DB 試験(製品 authz 全ファイル・スキーマ監査・migration・往復・ランタイム契約の統合・適用器): 1 回目 129 passed・5 failed → 是正後 **134 passed**
  - ハーネス: `ruff`・`ty` green / `test_check_authz_catalog.py`・`test_check_authz_function_bodies.py`・`test_orm_acceptance_sheets.py`・`test_frozen_archive.py`・`test_frozen_history.py` 313 passed / 検査器 4 本 rc=0 / 比較 corpus の digest は Codex が再 pin 済み
