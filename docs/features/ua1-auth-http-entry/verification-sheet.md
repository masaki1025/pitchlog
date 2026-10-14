# U-A1 δ 逐行確認の突合シート(PR #119)

**設計書 6.3 のコア領域の逐行確認を支援するための機械生成の表。**
**これは確認の代わりではない** — 何をどの順に読むか、各行が何を守っているつもりかを並べたもの。

- 対象: `git diff origin/develop...HEAD`(**79 ファイル・+6294 / -361**)
- うち**実質的に読むべきは製品コードと SQL の 14 ファイル・+614**
- 残りは契約資産(digest 連鎖は機械検証)・テスト(表明の追加)・文書

## 1. 製品コード(10 ファイル・+412 / -20)

| ファイル | 増減 | 何をするか | 守っているつもりのもの | 固定している試験 |
| --- | --- | --- | --- | --- |
| `api/routers/auth.py` | +125 | **入口 3 本**。ログイン / ログアウト / PW 変更。失敗の待ちは `anyio.sleep` で消費 | **不変条件 ①**(待ちが DB 接続もワーカーも占有しない)/ FR-033 / FR-036 | `test_api_login.py`・`test_api_auth_exit.py`・`db/test_api_login_entry.py`・`db/test_api_auth_exit_entry.py` |
| `api/schemas/auth.py` | +37 | 要求と応答の形。**応答に提示値を含めない** | NFR-014(`data-model.md:1678`) | `test_api_login.py`(提示値の非露出) |
| `api/app.py` | +37 / -1 | router 登録と **`_RenewedCookieMiddleware`**。誤り応答へ更新 Cookie を引き継ぎ、**`Set-Cookie` を載せる応答へ `Cache-Control: no-store`** | 提示値が共有キャッシュへ残らないこと(**敵対 2 回目 P0-1**) | `test_api_tenant_access.py`・`test_api_conventions.py` |
| `api/tenant_access.py` | +19 / -4 | 延長後の期限から `Max-Age` を計算し、`request.state.renewed_cookie` に控える | スライディング延長がブラウザへ届くこと(**改訂 14**) | `test_api_tenant_access.py` |
| `authz/team_login.py` | +93 | ログインの公開境界。接続資源の遅延取得。**NUL を含む入力を SQL NULL へ写す** | **不変条件 ②・③**(**敵対 1 回目 P0-3**) | `test_authz_app_layer_surface.py`・`db/test_api_login_entry.py` |
| `authz/password_change.py` | +71 | PW 変更の公開境界。署名器の同一性検査 → `decode` → DB | FR-036 / 境界の単一化 | `test_authz_password_change.py` |
| `authz/verified_tenant.py` | +17 / -7 | `verify_tenant_id` が**期限も返す**ように | 改訂 14 の 3 層の 1 段目 | `test_authz_verified_tenant.py`・`db/test_authz_verified_tenant.py` |
| `repositories/tenant_context_issuance.py` | +8 / -5 | 期限を落とさずに返す | 同 2 段目 | `test_api_tenant_access.py` |
| `authz/product_authn_contract.py` | +2 / -1 | 認証関数の署名の期待集合 | 契約の完全一致 | `test_product_authz_catalog.py` |
| `authz/runtime_contract.py` | +3 / -2 | **生成物**(再導出) | 保護対象の集合 | `db/test_runtime_contract_product_integration.py` |

### 読む順の推奨

1. **`authz/team_login.py`** — NUL の写しと、失敗が計数へ入ることの筋
2. **`api/routers/auth.py`** — 待ちをどこで消費しているか(**①の要点**)
3. **`api/app.py`** のミドルウェア — Cookie とキャッシュ指示の付け方
4. 残り 7 本

## 2. SQL 関数(4 ファイル・+202 / -87)

| ファイル | 増減 | 何をするか | 読むべき点 |
| --- | --- | --- | --- |
| `FUNCTION:authn:login_attempt(text, text, text).sql` | **+150** | 旧 `authn.login` を置き換え。照合を勧告ロックの前に。**成功はロックを取らない**。失敗だけが予約票を取り待ち時間を返す | **①** 成功がロックを取らないこと / **②** 失敗の計数と応答が名前と誤り方で変わらないこと / **④** 勧告ロックで直列化 / **R7** 設定値が欠けると計数前に返ること |
| `FUNCTION:authn:login(text, text).sql` | **-80** | **削除**(置き換え) | 旧署名が実 DB に残らないこと |
| `FUNCTION:authn:verify_token(uuid).sql` | +10 / -7 | `OUT tenant_id, OUT expires_at` へ。**失敗時は両方 NULL** | 呼び出し側が `(None, None)` を拒否と判定できること |
| `FUNCTION:authn:observe_rate_limit_counters().sql` | +42 | 現ウィンドウ外の行数と**カウンタ鍵の種類数** | **⑥** 物理削除しない / NFR-005 DB 側で絞る |

## 3. 不変条件との対応(`data-model.md` 8-6 節)

| 不変条件 | どこで満たすか | 残余リスク |
| --- | --- | --- |
| ① 第三者の連打で正規利用者を締め出せない | 鍵は試行元ごと。成功はロックを取らない。待ちは DB の外 | **R6** — 上限を超えると並行時に実効の制限がかからない(**10 章の相談へ**) |
| ② 計数・判定・応答が名前と誤り方で変わらない | 鍵に名前を含めない。照合は常に cost 12 を 1 回。NUL も同じ失敗経路へ | R2(分散した試行元)・R3(照合そのもの) |
| ③ 計数は失敗応答と同じコミットで確定 | 勧告ロックの内側 | **R7** — fail-closed の状態では計数しない(⑤ と両立しない) |
| ④ 並行した試行は直列化 | `pg_advisory_xact_lock(87001224, hashtext(source_key))` | — |
| ⑤ 値は関数が設定値から読む / 未設定なら拒否 | `authn.setting_positive_integer` | R7 の裏側 |
| ⑥ 物理削除しない | 監視は読むだけ | — |

## 4. 確認の記録欄(設計書 6.3)

**PR 本文の `- 実施記録: 対象= 範囲= 方法=` を、確認した本人が記入する。**
**この行は機械検証されない。**
