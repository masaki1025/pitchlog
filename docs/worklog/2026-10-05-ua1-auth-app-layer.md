---
date: 2026-10-05
topic: TSK-469 U-A1 γ 認証のアプリ層(署名と検証・TenantContext の生成)
branch: feature/ua1-auth-app-layer
---

# 作業ログ: 2026-10-05 TSK-469 U-A1 γ 認証のアプリ層

## やったこと

- ステップ 1: `backend/src/pitchlog/authz/token_presentation.py` を新設。`TokenPresentation` がトークン行の UUID を HMAC-SHA256 で署名し、提示値の形式と署名を照合して UUID を返す。鍵は `bytes` 引数で受け、環境変数・DB は読まない。
- DB 不要の `backend/tests/test_authz_token_presentation.py` を追加。正規形の往復、HMAC 対象、公開シンボルの exact-set、別表記・不正形式・鍵違い・ID 差し替えの拒否を確認した。`pytest -c pyproject.toml tests/test_authz_token_presentation.py -q`: **17 passed**。`ruff format`: **1 file reformatted, 240 files left unchanged**。`ruff check` / `ty check`: **All checks passed**。実行時は読み取り専用の既定 `uv` キャッシュを避け、`UV_CACHE_DIR=/tmp/pitchlog-ua1-uv-cache` と `--offline` を付けた。
- 正規形の負例の red を確認した。ソースは変更せず、実行中だけ提示値のパターンを大文字 UUID とハイフンなし UUID も通す形に緩めると、`test_alternate_uuid_spellings_are_rejected` は **2 failed, 3 passed** になった。拒否が失われたのは大文字 UUID とハイフンなし UUID の 2 入力。元のパターンでは 17 件すべて green。
- TB002 を実測した。`base-allowlist.json` の `conditions` のうち `error == "TB002"` の正規表現 7 件を読み、導入した 2 ファイルの Python AST からモジュール名・クラス名・関数名・引数名・代入先名・import 名を採り、各識別子へ `re.search` を実行した。**両ファイルとも一致 0 件**。凍結資産への裁定追加は不要。
- ステップ 2: `authz/signing_key_config.py` で環境変数の標準 Base64・padding 付き正規形を復号し、復号後 32 バイト以上を必須化した。`create_app()` が `PITCHLOG_TOKEN_SIGNING_KEY_B64` を読み、設定に不備があればアプリ生成前に例外を送出し、通過した鍵を `app.state.token_presentation` の署名器へ渡す。`.env.example` には CSPRNG (`secrets.token_bytes(32)`) による生成コマンドだけを記載し、実値は載せていない。
- `backend/tests/test_authz_signing_key_config.py` に `create_app()` 経由の欠落・短い鍵・不正符号化・別表記の拒否と、署名器への配線確認を追加。`"A" * 40` は文字列長 40 だが復号後 30 バイトで、実際に起動拒否される。既存の API 試験は各ファイル内で試験用の乱数鍵を設定し、`backend/tests/conftest.py` は変更していない。
- 検証: `backend/` で `uv run --offline ruff format`: **2 files reformatted, 241 files left unchanged**、再実行: **243 files left unchanged**。`uv run --offline ruff check` / `uv run --offline ty check`: **All checks passed**。`uv run --offline pytest -c pyproject.toml tests/ -q`: **964 passed, 4 skipped, 385 errors**。エラーは DB 必須試験の接続 fixture で、この環境では DB に接続できなかった。非 DB の独立実行 `tests/ --ignore=tests/db -m 'not requires_db' -q --tb=short`: **955 passed, 4 skipped, 17 deselected**。指定の全件実行では `tests/db/` 配下の非 DB 試験 9 件も通過している。いずれも `UV_CACHE_DIR=/tmp/pitchlog-ua1-uv-cache` を指定した。
- ステップ 2 の TB002 を実測。`base-allowlist.json` の `conditions` で `error == "TB002"` の正規表現 7 件を取得し、変更した Python 6 ファイルの現行 AST と `HEAD` の AST の差から導入識別子を採った。モジュール名・クラス名・関数名・引数名・`Name`・import 名に `re.search` を適用し、**固有 39 識別子、該当 0 件**。凍結資産の変更は不要。
- ステップ 3 の配線先訂正: 計画書 §4-5 の `create_engine()` は SQLAlchemy の import 名であり、製品の配線先は `backend/src/pitchlog/db/engine.py` の `create_database_engine()` である。
- ステップ 3: `authz/database_transport.py` を新設し、正規化後の URL を SQLAlchemy psycopg dialect の接続引数へ展開して `connect_args` を重ね、engine 生成前に通信経路を検証した。ローカルは明示した UNIX ドメインソケットの絶対パス、IPv4 `127.0.0.0/8`、IPv6 `::1` のみ。`localhost` と接続先省略は除外した。リモートは `sslmode=verify-full` を必須とし、GSS が TLS に優先する経路を防ぐため `gssencmode=disable` を接続引数に明示した。`PGHOSTADDR` と service によるローカル接続先の上書きも拒否する。
- `backend/tests/test_authz_database_transport.py` の engine 生成試験で `sslmode` 未指定・`prefer`・`require`・`verify-ca`・リモートの `disable`・名前解決に依存する `localhost`・接続先の上書きを拒否した。ローカル 3 形態とリモート `verify-full` の受理、DBAPI 直前の `sslmode` と `gssencmode` も DB 接続なしで確認した。既存の非 DB/DB 試験用 URL には、各接続先に応じて明示的な `sslmode` を足した。
- 検証: `backend/` で `uv run --offline ruff format`: 初回 **1 file reformatted, 244 files left unchanged**、最終 **245 files left unchanged**。`uv run --offline ruff check` / `uv run --offline ty check`: **All checks passed**。指定の `pytest -c pyproject.toml tests/ -q -m "not requires_db"` は **984 passed, 4 skipped, 385 deselected** だが、`tests/db/conftest.py` の既存終了時フックが DB 必須試験 0 件をエラーとするため終了コード 1。`--ignore=tests/db` を足した補助実行は追加試験前に **973 passed, 4 skipped, 17 deselected** で終了コード 0。追加試験は単独で **20 passed**。すべて `UV_CACHE_DIR=/tmp/pitchlog-ua1-uv-cache` を指定した。
- 既存 DB 試験 `test_schema_revision_and_application_engine_use_the_database` の実行を試みたが、共通 fixture の管理接続が `psycopg.OperationalError: connection is bad` となり試験本体へ進めなかった。使い捨て DB の接続先は fixture 上 `127.0.0.1` と確認し、その URL 変換で `sslmode=disable` を明示した。実 DB で壊れていないことの確認は未了。
- ステップ 3 の TB002 を実測。`base-allowlist.json` の `TB002` 正規表現 7 件に対し、新設 2 ファイルと既存変更 6 ファイルの Python AST と `HEAD` の AST の差から導入識別子を抽出し、検査器と同じ snake_case 相当の正規化後に `re.search` した。**固有 56 識別子、該当 0 件**。凍結資産への裁定追加は不要。
- ステップ 4: `authz/verified_tenant.py` に公開入口 `verify_tenant_id()` を 1 つ作った。関数内で `TokenPresentation.decode()` を先に実行し、成功した戻り値だけを固定 SQL `authn.verify_token(:token_id)` に束縛する。生の UUID を受け取る DB 呼び出し関数は作らず、署名器は実際の `TokenPresentation` 型に限定した。署名不正と DB 関数の NULL はどちらも `None` とし、DB 例外は入力を含まない文言に変換する。例外の `__context__` に SQLAlchemy の引数が残らないよう、DB 例外を捕捉したブロックの外で再送出する。`TenantContext` は生成しない。
- `backend/tests/test_authz_verified_tenant.py` で公開シンボルの exact-set、照合後の ID だけの DB 到達、生の UUID・改ざん提示値・偽の decode オブジェクトからの DB 非到達、DB NULL と例外文言を確認した。**6 passed**。
- `backend/tests/db/test_authz_verified_tenant.py` に `requires_db` を付け、実 DB 上で正常トークンのテナント ID と利用時刻・期限の更新を確認してから、**ログアウト失効、認証情報の世代繰り上げ、テナント無効化、主体とトークンのテナント不一致、期限切れ**を各 1 件作り、正しく署名した提示値が `None` となり行が更新されないことを確認する試験を追加した。実行を試みたが、共通 fixture の管理接続が `psycopg.OperationalError: connection is bad` で止まり、**5 件とも本体は未実行**。実 DB での負例と延長は未確認。DB ログ設定は変更していない。
- 非 DB 全件 `pytest -c pyproject.toml tests/ -q -m "not requires_db" --ignore=tests/db`: **981 passed, 4 skipped, 17 deselected**。`ruff format`: **248 files left unchanged**、`ruff check` / `ty check`: **All checks passed**。実行には `UV_CACHE_DIR=/tmp/pitchlog-ua1-uv-cache` と `uv run --offline` を使用した。
- ステップ 4 の TB002 を実測。新設した Python 3 ファイルの AST からモジュール名・クラス名・関数名・引数名・代入先名・属性名・import 名など **固有 109 識別子**を採り、検査器と同じ snake_case 相当の正規化を施し、`base-allowlist.json` の TB002 正規表現 7 件と照合した。**該当 0 件**。SQL 中の `generation` は Python 識別子ではない。
- ステップ 5: `backend/tests/test_authz_app_layer_surface.py` に公開操作と DB 到達点の期待集合を置いた。実装の Python AST から公開関数・クラス操作、製品コードから公開操作への呼び出し、`authn.*` を含む SQL 実行箇所を導出し、非空かつ exact-set で照合する。公開操作 6 件、DB 到達点 1 件(`verify_tenant_id` → `authn.verify_token`)。既存の製品呼び出し元 4 件(型注釈で結び付く `presentation.decode()` を含む)も exact-set とした。公開操作 6 件それぞれの不正入力と、正しく署名した提示値に対する DB NULL の負例を追加した。`verify_token` の検証と延長は同一呼び出しで、別々の到達点に数えない。
- β の関数資産を実測。`authn.logout(uuid)` は存在し、対象トークン行の `expires_at` を更新し、`pitchlog_app` に EXECUTE が付与されている。`authn.change_password(uuid, text, text)` も存在する。ただし本単位の製品コードには両関数の呼び出し元がないため、DB 到達点の機械可読マップには両方を **`None`(未接続)** と明記した。HTTP のログアウト・パスワード変更経路は δ の射程であり、このステップでは追加しない。
- 空集合変異を実施。試験ファイルの公開操作期待集合と DB 到達点期待集合をそれぞれ一時的に空にし、各照合試験を `pytest` で実行した。**どちらも終了コード 1 / 1 failed / `期待集合が空です`**。原状に戻した。恒久試験にも期待集合・導出集合の空集合拒否を入れた。
- 実装側の呼び出し元追加変異を実施。`backend/src/pitchlog/authz/_step5_mutation_probe.py` を一時的に作り、`verify_tenant_id()` を呼ぶ関数と `connection.execute('SELECT authn.logout(...)')` を呼ぶ関数を追加した。**先に AST で新関数 2 件と呼び出し式 2 件が実装へ届いたことを確認**。その後、公開呼び出し元と DB 到達点の照合試験は **終了コード 1 / 2 failed** となり、失敗出力に新しい呼び出し元が両方現れた。一時ファイルを削除した。恒久試験でもソース複製への公開操作・公開呼び出し元・DB 呼び出しの追加変異が各照合を失敗させる。関数内の SQL 変数を `exec_driver_sql` へ渡す `change_password` 呼び出し変異も検出した。
- ステップ 5 の TB002 を実測。新設試験ファイルの Python AST からモジュール名・関数名・クラス名・引数名・Name・Attribute・import 名を採り、検査器と同じ snake_case 相当へ正規化し、`base-allowlist.json` の TB002 正規表現 7 件と照合した。**固有 188 識別子、該当 0 件**。凍結資産や検査器は変更していない。
- ステップ 5 の最終検証(`backend/`、`UV_CACHE_DIR=/tmp/pitchlog-ua1-uv-cache`、`uv run --offline`): 指定の非 DB 全件は **996 passed, 4 skipped, 17 deselected**。`ruff format`: **249 files left unchanged**、`ruff check` / `ty check`: **All checks passed**。実 DB の試験は本ステップで追加・実行していない。

## 決定

- 提示値の唯一の正規形は `<小文字・ハイフン付き UUID>.<小文字 hex 64 桁の HMAC-SHA256>`。HMAC の対象は UUID の正規形の ASCII バイト列。UUID の大文字・ハイフンなし・波括弧付き・前後空白、署名の大文字 hex・base64 の標準/URL 安全形・padding 有無は受理しない。
- 公開シンボルは `TokenPresentation` だけ。モジュールの `__all__` と非 `_` 名前空間の両方を exact-set 試験で固定した。署名失敗・形式失敗の例外メッセージは同一で、鍵・ID・提示値・署名を含めない。
- TB002 照合対象の製品モジュール識別子: `token_presentation`, `TokenPresentation`, `_PRESENTATION_PATTERN`, `_UUID`, `__all__`, `__init__`, `__slots__`, `_hmac`, `_re`, `canonical_id`, `decode`, `encode`, `expected`, `key`, `match`, `self`, `signature`, `signature_hex`, `token_id`, `value`。
- TB002 照合対象の試験モジュール識別子: `test_authz_token_presentation`, `TokenPresentation`, `UUID`, `_CANONICAL_ID`, `_TOKEN_ID`, `alternate`, `alternate_id`, `base64`, `canonical_id`, `error`, `expected_signature`, `forged_value`, `hmac`, `invalid_id`, `invalid_value`, `key`, `name`, `public_names`, `pytest`, `secrets`, `signature`, `signature_bytes`, `signature_hex`, `signer`, `standard_base64`, `test_alternate_signature_encodings_are_rejected`, `test_alternate_uuid_spellings_are_rejected`, `test_encode_and_decode_use_canonical_uuid_as_hmac_message`, `test_malformed_presentation_is_rejected`, `test_modified_id_is_rejected`, `test_public_symbols_are_exact_set`, `test_signature_from_another_key_is_rejected_without_leaking_input`, `token_presentation`, `upper_hex`, `urlsafe_base64`, `value`。
- ステップ 2 の鍵は、CSPRNG 由来の 32 バイト以上を**標準 Base64 の padding 付き正規形**で設定する。`b64decode(validate=True)` の結果を再符号化して元の値と照合するため、非 ASCII・不正文字・padding 欠落・同一バイト列へ復号される非正規形を拒否する。環境変数値から生成元の乱数性を証明することはできないため、生成コマンドを設定契約として固定した。
- ステップ 2 の TB002 照合対象の導入識別子: `Exception`, `SigningKeyConfigurationError`, `ValueError`, `base64`, `binascii`, `bytes`, `key`, `len`, `require_signing_key_configuration`, `signing_key_config`, `str`, `value`, `variable_name`(`signing_key_config.py`); `TokenPresentation`, `_SIGNING_KEY_VARIABLE`, `os`, `require_signing_key_configuration`, `signing_key`(`app.py`); `SigningKeyConfigurationError`, `TokenPresentation`, `_SIGNING_KEY_VARIABLE`, `alphabet`, `alternate`, `app`, `base64`, `canonical`, `create_app`, `encoded_key`, `error`, `final_value`, `invalid_key`, `key`, `monkeypatch`, `pytest`, `secrets`, `str`, `test_alternate_base64_spelling_prevents_app_creation`, `test_authz_signing_key_config`, `test_create_app_uses_configured_signing_key`, `test_invalid_encoding_prevents_app_creation`, `test_missing_signing_key_prevents_app_creation`, `test_short_decoded_signing_key_prevents_app_creation`, `token_id`, `uuid4`, `value`(`test_authz_signing_key_config.py`); `_configure_signing_key`, `base64`, `encoded_key`, `monkeypatch`, `secrets`(`test_api_app.py` / `test_api_conventions.py`); `base64`, `encoded_key`, `import_module`, `monkeypatch`, `secrets`(`test_health.py`)。

## 未決・次の一歩

- ステップ 5 まで実装済み。委任元がステップ 5 のコミットを作る。実 DB 負例 5 件は接続可能な環境で実行し、結果を確認する必要がある。ステップ 6 以降には着手していない。

## 2026-10-07 裁定⑫の追随(ステップ 5 の是正)

- `verified_tenant.py` に公開入口 `logout_token()` を追加。実際の `TokenPresentation` 型に限定し、`decode()` で署名を照合した ID だけを `authn.logout()` へ渡す。DB 関数は `void` なので戻り値は常に `None`。DB 例外は捕捉ブロックの外で入力を含まない `RuntimeError` に変換する。`TenantContext` は生成していない。
- 集合を **公開操作 7 件 / DB 到達点 2 件**へ是正した。到達点は `verify_tenant_id → authn.verify_token`(検証と延長は同一呼び出し)と `logout_token → authn.logout`。`authn.change_password` は `None`(本単位から未接続)のまま明示した。理由は `data-model.md` 8-3 節②の逐語列挙が「検証・延長・ログアウト」であり、PW 変更を含まないため。製品呼び出し元の exact-set は 5 件。
- DB 不要の負例実測: 生 UUID 文字列・署名 1 文字改変・署名なし・別鍵の提示値は**各 DB 到達 0 回 / `None`**。偽の署名器・派生クラスは**各 DB 到達 0 回 / `TypeError`**。正しい提示値は**DB 到達 1 回 / `None`**。DB 例外は到達 1 回の後に `RuntimeError` となり、`__context__` と `__cause__` は `None`、公開メッセージと `traceback.format_exception()` の全文に提示値・トークン ID が含まれないことを確認した。
- 実 DB 試験の `logged_out` ケースを公開入口経由に変更。正しい提示値でログアウトしたあとにトークン行の期限短縮と最終使用時刻の不変を観測し、同じ提示値の `verify_tenant_id()` が `None` を返すことを検査する。**実行は setup の管理接続で `psycopg.OperationalError: connection is bad` となり、試験本体は未実行**(4 deselected, 1 error)。DB のログ設定は変えていない。
- 空集合変異は期待集合 2 種をそれぞれ空にし、**先に AST で代入の空集合化を確認**したあと各照合を実行した。両方とも **終了コード 1 / 1 failed / `期待集合が空です`**。実装側へ `logout_token()` の新しい呼び出し元と `authn.change_password()` の新しい DB 呼び出し元を一時追加し、**先に AST で新関数 2 件と呼び出し式 2 件を確認**したあと照合を実行した。**終了コード 1 / 2 failed** で、失敗出力に両呼び出し元が現れた。変異を原状に戻した。
- TB002: 変更した Python 4 ファイルを `HEAD` の AST と比較して導入識別子を採り、検査器と同じ snake_case 相当の正規化で `base-allowlist.json` の正規表現 7 件と照合した。**固有 21 識別子、該当 0 件**。
- 最終検証(`backend/`、`UV_CACHE_DIR=/tmp/pitchlog-ua1-uv-cache`、`uv run --offline`): 非 DB 全件 **1004 passed, 4 skipped, 17 deselected**。`ruff format`: **249 files left unchanged**、`ruff check --fix` / `ty check`: **All checks passed**。
- β の SQL の `expires_at = greatest(logged_out_at, previous_last_used_at)` は、式の上では期限が `logged_out_at` **以上**となる。今回の実 DB 試験はこの大小関係の断定に頼らず、期限の短縮と同じ提示値での検証失敗を観測する。

## 2026-10-07 ステップ 6(故障系)

- `backend/tests/test_authz_failure_mutations.py` を新設。既存試験の期待を書き換えず、製品ソースを一時ディレクトリへ複製して守りを外す。**red の前に**変異後 AST が異なること・変更文が複製先にあること・子プロセスがその複製先からモジュールを import することを確認する。試験後に元のバイト列へ戻し、元ソースとの差分 0 を確認してから同じ試験を green で実行する。作業ツリーの製品ソースには変異を残さない。

| 条件文の群 | 既存試験との対応・補足 | 実装側で外した守り | red → green |
| --- | --- | --- | --- |
| ① 署名の改ざん | `test_authz_verified_tenant.py::test_logout_rejects_unsigned_values_without_db[tampered_signature]` | ①②共通: `TokenPresentation.decode()` の `compare_digest` 判定を無効化 | ①②の合計 **2 failed → 2 passed**(各 1 件) |
| ② 鍵の入れ替え後のトークン | `test_authz_token_presentation.py::test_signature_from_another_key_is_rejected_without_leaking_input`。旧鍵の提示値を別鍵で拒む同じ事実なので、①と 1 変異に寄せた | ①と同じ | ①②の合計に含む |
| ③ 不正な形式の提示値 | 既存 `test_malformed_presentation_is_rejected` に加え、新設ファイルの `test_valid_signed_value_with_suffix_is_rejected`。既存の余分な文字の入力は署名自体も不正なので、正しい署名に末尾文字を足す負例を補った | `fullmatch` を `match` へ変更 | **1 failed → 1 passed** |
| ④ 鍵の欠落・短い鍵で起動拒否 | `test_authz_signing_key_config.py::test_missing_signing_key_prevents_app_creation` / `test_short_decoded_signing_key_prevents_app_creation`(2 ケース) | 鍵設定関数の冒頭で固定長鍵を返し、起動時検証を飛ばす | **3 failed → 3 passed** |
| ⑤ TLS でない設定を拒否 | `test_authz_database_transport.py::test_engine_rejects_unverified_or_ambiguous_transport`(12 ケース。`create_database_engine()` 経由) | 通信設定検証関数を冒頭で返す | **12 failed → 12 passed** |
| ⑥ 署名未照合 ID の `verify_token` / `logout` 非到達 | `test_authz_verified_tenant.py::test_unsigned_id_and_tampered_value_never_open_db` / `test_logout_rejects_unsigned_values_without_db[raw_uuid]`。到達点そのものは `test_authz_app_layer_surface.py::test_db_reach_is_exact_set_and_absences_are_explicit` | 両公開入口の `presentation.decode()` を生 UUID の解析へ置換 | **2 failed → 2 passed** |

- 条件文にある**正しく署名された失効済み・無効テナントの ID**は `tests/db/test_authz_verified_tenant.py::test_signed_invalid_token_returns_no_tenant` の 5 ケース(`logged_out` / `stale_credential` / `disabled` / `wrong_tenant` / `expired`)に対応する。委任元が使い捨て Postgres で実行済み。本サンドボックスでは管理接続が立たないため、この DB 依存の変異・再実行は行っていない。新設試験の対応表は計画書の条件文を起点に、参照する関数とパラメータ名の実在を確認する。
- TB002: 新設ファイルの AST からモジュール名・関数名・クラス名・引数名・`Name`・`Attribute`・import 名を採り、検査器と同じ snake_case 相当で正規化し、`base-allowlist.json` の候補パターン 7 件と照合した。**固有 124 識別子、該当 0 件**。
- 最終検証(`backend/`、`UV_CACHE_DIR=/tmp/pitchlog-ua1-uv-cache`、`uv run --offline`): 非 DB 全件 **1011 passed, 4 skipped, 17 deselected**。`ruff format`: **1 file reformatted, 249 files left unchanged**、`ruff check --fix` / `ty check`: **All checks passed**。ステップ 7 の作業には着手していない。

## 2026-10-07 ステップ 7 のログ・例外確認(本委任の範囲のみ)

- **例外の条件文からの照合**: 既存 `test_authz_verified_tenant.py::test_logout_db_error_omits_presentation_and_id_from_full_traceback` は、DB 例外に提示値と ID が含まれていても、公開 `RuntimeError` のメッセージ・`__context__`・`__cause__`・`traceback.format_exception()` 全文から両値が消えることを確認済み。一方、既存 `test_db_error_message_omits_token_id` はメッセージと `__context__` だけで、全トレースは未確認だった。既存試験は書き換えず、`test_authz_log_safety.py::test_verify_db_exception_hides_material_from_full_traceback` で照合側のメッセージ・文脈・全トレースに提示値・ID・鍵の Base64 値がないことを補った。同ファイルで起動時の不正鍵と通信設定の拒否についても、例外メッセージと全トレースに設定値がないことを確認した。
- **SQLAlchemy の実測と是正**: `sqlalchemy.engine` に INFO ハンドラを付け、DB を使わず SQLite engine から実際の `verify_tenant_id()` と `logout_token()` を呼んだ。両 SQL のログを採取でき、`hide_parameters=False` では束縛したトークン ID が **出た**。同じ入力で `hide_parameters=True` なら **出ず**、提示値は両条件で出なかった。各条件 8 レコード。製品の `create_database_engine()` に `hide_parameters=True` を設定し、engine 属性と `echo` が無効であることを試験で固定した。SQL の `:token_id` 束縛は維持した。ログ設定を INFO に上げても束縛値を出さない範囲を製品 engine で確保した。
- **アプリの実測**: `pitchlog` ロガーに DEBUG ハンドラを付け、試験用メッセージを 1 件受けることを先に確認した。その後、正しい鍵による `create_app()`、鍵の欠落・短さによる起動拒否、明示ローカル DB 設定の受理と不正 TLS 設定の拒否を実行し、捕捉したログに鍵の Base64・hex・`repr`、署名付き提示値、トークン ID がないことを機械照合した。ハンドラはメモリ内だけに保持し、設定は試験後に復元する。
- **psycopg の確認範囲**: `psycopg` ロガーに DEBUG ハンドラを付けて失敗するローカル接続を実行したところ、接続試行・失敗の **3 レコード**を採取できた。この測定は SQL 実行を伴わないため、束縛 ID の非露出の根拠にはしない。実際の `authn.verify_token`・`authn.logout` 呼び出しでは実 DB が要るため、`tests/db/test_authz_log_safety.py::test_real_driver_and_engine_logs_omit_auth_material` を `requires_db` で追加した。製品 engine と `psycopg` DEBUG / SQLAlchemy INFO の整形済みログを採取し、SQL の実行と提示値・ID・鍵・接続パスワードの非露出を確認する。**この環境では実 DB 試験を実行しておらず、委任元の使い捨て Postgres での結果待ち**。DB サーバーのログ設定は変更していない。
- **δ・運用側への申し送り**: δ の HTTP 経路は今回設定を固定した製品 `create_database_engine()` を使う必要がある。別の engine を作るなら同じ束縛値非表示設定が要る。`hide_parameters=True` は SQLAlchemy の束縛値ログと SQLAlchemy 例外を隠す設定であり、Postgres サーバーの文ログや、手動で有効化する psycopg の低層 libpq トレース(`psycopg.pq._debug.PGconnDebug`)の設定までは制御しない。配備時にこれらを有効化しない運用確認が要る。後者はローカルの psycopg 実装を読んで確認したもので、この委任では実際に有効化していない。
- **検証**: `backend/` で `uv run --offline ruff format`: 初回 **2 files reformatted, 250 files left unchanged**、最終 **252 files left unchanged**。`ruff check --fix` / `ty check`: **All checks passed**。影響範囲の `tests/test_authz_*.py -m 'not requires_db'`: **574 passed, 4 skipped, 17 deselected**。最後の試験内の機密値を失敗出力へ載せない微修正後、追加ファイルを単独で再実行し **6 passed**。初回は `-m` 指定がなく、同じ glob に含まれる DB 必須の `test_authz_tenant_binding.py` が管理接続 fixture で **17 errors** になった。DB 試験本体は実行されず、非 DB 指定で再実行した。全件試験は実行していない。
- **TB002**: 新設した非 DB/DB 試験ファイル 2 件と製品 `engine.py` の `HEAD` 差分の Python AST から、モジュール・クラス・関数・引数・名前・属性・import・キーワード引数の導入識別子を抽出。検査器と同じ snake_case 相当への正規化後、`base-allowlist.json` の TB002 正規表現 **7 件**へ照合し、**固有 147 識別子、該当 0 件**。凍結資産は変更していない。

## 2026-10-07 ステップ 7 の実 DB ログ試験是正

- 委任元の使い捨て Postgres で `test_real_driver_and_engine_logs_omit_auth_material` が 1 件 red。他 5 件は passed との報告。SQLAlchemy の `authn.verify_token` / `authn.logout` のログには `[SQL parameters hidden due to hide_parameters=True]` が出ており、束縛値の非表示は実 DB でも確認できた。`driver_messages` の非空要求は不適切だった。委任元は通常の認証 SQL で psycopg DEBUG が 0 件と報告したが、旧試験は捕捉ハンドラが INFO になっていたため、その空集合だけでは非出力を立証しない。
- 旧試験の `caplog.at_level()` は psycopg DEBUG の後に SQLAlchemy INFO を適用していた。後者が共通捕捉ハンドラのレベルも INFO に変えるため、psycopg DEBUG を捕捉できない形だった。設定順を SQLAlchemy INFO → psycopg DEBUG に直した。
- 同一試験内の**陽性対照**として、ローカルの接続失敗を発生させ、`psycopg` ロガーの `connection attempt` と `connection failed` の両方を捕捉できることを先に要求する。`caplog` を消し、製品 engine の物理接続を先に開いて接続ログを分離し、再度消してから検証・ログアウト・再検証の SQL 区間だけを採取する。この区間では psycopg のログ **0 件**を明示的に要求し、出力が増えた場合は red として再評価する。SQLAlchemy の 2 関数のログと、両ロガーへの認証素材の非露出の照合は維持した。
- DB を使わない一時的な同形の `caplog` 探針を実行した。旧順序では既知の接続失敗 DEBUG を `caplog.records` に採れず、陽性対照は **1 failed**。是正後の順序では **1 passed**。どちらも一時ファイルは削除した。実 DB を要する本試験の再実行は委任元待ちであり、是正後の green は未観測。DB サーバーのログ設定は変更していない。
- 影響範囲の非 DB authz 試験は **574 passed, 4 skipped, 17 deselected**。`ruff format`: 初回 **1 file reformatted, 251 files left unchanged**、最終 **252 files left unchanged**。`ruff check --fix` / `ty check`: **All checks passed**。導入識別子を Python AST と TB002 正規表現 7 件で再照合し、**固有 157 件、該当 0 件**。製品コードと禁止された資産は今回の是正で変更していない。

## 2026-10-07 ステップ 7 の正本の現行化と U-M1 への申し送りの確認(委任元)

- **正本の現行化**: `data-model.md` 12-8 節「実装時に確定する範囲」の残件の 1 項目を現行化した。
  計画書 4-8 は `:2928` と書いていたが、**#97・#98 の取り込みで `:2972` へ移っていた**ので、
  行番号ではなく**文言**(「署名と検証・テナント文脈の生成 = **TSK-469**(U-A1 γ)」)で特定した。
  新しい所有は 署名と検証 = TSK-469 / 発行の機構と検査器 = TSK-457 /
  発行モジュールの実体・登録・生成箇所 = U-M1 ステップ 8 の 3 つ。**版は据え置き**(実装追随 — 7.6-3 前段)。
  変更履歴に 1 行、`docs/README.md` の最終更新日を 2026-10-06 → 2026-10-07 へ。
- **digest 2 件**: 計画書 4-8 の警告どおり**両方**を取り直した(TSK-475 は片方だけ直して CI で落ちた)。
  `shared-preconditions.json` の `git_blob_digest` = `7047aee9…`(ハッシュ化コマンドで取得)/
  `schema-manifest.json` の `canonical_source.sha256` = `48b64926…`(`sha256sum` — 資産自身の再現手順)。
  **値は取り直す時点の develop(`1fdf1eec`)を基準にした。先に測って焼き込んでいない。**
  `check_docs_status.py` 0 violations / `tests/test_check_shared_preconditions.py` 9 passed /
  `backend/tests/test_schema_manifest.py` 14 passed。**取り直した後にもう一度実測して一致を確認した。**
- **U-M1 への申し送り(4-7 節)の所在を原典で確認した**。`um1-player-roster-opponent/plan.md` の
  第 3 改訂(2026-10-07 承認・`74e29eda`)に、裁定 b'・TSK-457 の射程・受理記録 1 件化・
  **ログアウトの入口は γ が持つ(依存表 6)**が記録されている。機械で辿れる形という合格条件を満たす。
- **ただし 4-7 節の 2 項目は、記録の後に現況が動いた**。申し送り先へ伝えた:
  - **4-7 の 4「TSK-457 が未着手・担当者なし」は古い。** TSK-457 は**ステップ 6/7 まで実装済み**で、
    ステップ 7(凍結資産の繰り上げと受理記録)が**人間の逐行確認待ち**である(2026-10-07 実測)
  - **4-7 の 6「越境テストは U-M1 のステップ 8 で発効する」の番号が変わった。** 第 3 改訂の
    番号の付け替えで、**データ経路の入口を開くのはステップ 9** である(新 8 = 要求面・Cookie と CSRF)
- **`_PUBLIC_CALLERS` の形は変えていない**。(呼び出し元, 呼び出し先)の 2 要素タプルの集合のまま、
  裁定⑫の是正で `logout_token → decode` の 1 対を足しただけである。
  **U-M1 ステップ 9 が 1 対を足す予定とのことだが、集合の形は変わらないので支障はない。**
- **実 DB のログ試験**: 委任先の 1 回目は `tests/db/test_authz_log_safety.py` が 1 件 red だった。
  原因は製品ではなく試験の設計で、**`caplog.at_level()` の適用順**が psycopg DEBUG の後に
  SQLAlchemy INFO を置いており、**共通ハンドラのレベルが INFO へ上書きされて psycopg を捕捉できない**形だった。
  **「出なかった」と「見ていなかった」が区別できない**ので、陽性対照(接続失敗のログを先に捕まえる)を
  入れる形へ是正した。使い捨て Postgres で再実行し **6 passed**。

## 2026-10-08 `/pr` クローズ処理(結果サマリ)

### 実装したもの(7 ステップ・7 コミット)

| ステップ | 実装 |
| --- | --- |
| 1 | `authz/token_presentation.py` — 提示値の署名と検証(HMAC・定数時間比較) |
| 2 | `authz/signing_key_config.py` + `create_app()` への配線 — 署名鍵の環境変数と起動時検証 |
| 3 | `authz/database_transport.py` + `db/engine.py` への配線 — DB 接続の通信経路の検証 |
| 4 | `authz/verified_tenant.py` `verify_tenant_id()` — **署名を照合した ID だけを `authn.verify_token()` へ渡す**公開入口 |
| 5 | 公開操作と DB 到達点の**集合**を定める表面試験(負例つき)。**裁定 ⑫ の追随**で `logout_token()` を追加し 6/1 → 7/2 へ |
| 6 | 故障系 6 群の**変異試験** — 守りを 1 つずつ壊して red を観測し、バイト列を戻して green を確認する |
| 7 | **ログの漏れを塞ぐ** + 正本 1 行の現行化 + U-M1 への申し送りの確認 |

### 正本へ反映したもの

| 正本 | 反映 | ゲート |
| --- | --- | --- |
| `docs/design/data-model.md` | **12-8 節(射程宣言)の残件 1 行**を裁定 b'・⑪ に追随させた。**署名と検証 = TSK-469 / 発行の機構と検査器 = TSK-457 / 発行モジュールの実体・登録・生成箇所 = U-M1 のデータ経路の入口を開くステップ**の 3 つへ分けた。**版は据え置き**(実装追随 — 設計書 7.6-3 前段)。変更履歴に 1 行 | PR レビュー |
| `docs/development/harness-evaluation.md` | **既存候補 2 件へ事例追加 + `## 候補` へ新規 1 件**。**`H-*` の新規採番はしていない**(`H-91` は PO 判断で他タブ側 — 当方が先取りしない)。版は据え置き。変更履歴に 1 行 | PR レビュー |
| `docs/README.md` | `data-model.md` 行(2026-10-07)と**評価台帳行**(2026-10-08・候補 105 → **106 件**)の最終更新日と実測を現行化 | PR レビュー |

**`contracts/tenant_boundary/` 配下と `scripts/check_tenant_boundary_bypass.py` の差分は 0 行**(計画書 §3 の宣言どおり)。
**設計書 7.7 の受理記録も作っていない** — 触れた 2 資産(`contracts/authz/shared-preconditions.json` /
`contracts/db/schema-manifest.json`)は `baseline_control` を持たず、**digest の取り直しのみ**である。

### 台帳への追記の判断(`/pr` 手順 1-3)

**該当する**と判断し、**同一 PR で** ① 計画書 3 節へ宣言 → ② 台帳へ 3 件 → ③ 変更履歴 1 行 → ④ `docs/README.md` を現行化した。
**いずれも事例追加・候補であり、`H-*` は与えていない**(1 タスクのため。採番は昇格条件の成立を待つ)。

1. **既存候補「正本の行番号引用は、その正本自身を編集した瞬間に書き手自身の手で古くなる」へ 6 事例目** —
   **腐るのは行番号だけではない。ステップ番号も同じ速さで腐る。** 行番号は `:NNN` という走査できる形を持つが、
   **ステップ番号・節番号は普通の文章の一部**で、**外れても文として自然に読め、別の実在するステップを指す**。
   同じ日に 2 件踏み、**うち 1 件は他タブへ誤った指摘を送って差し戻された**(実害の一歩手前)。
   **対応案 (e)**: 他タスクの成果物は番号ではなく**内容**で指す
2. **既存候補「『何も起きていない』型の合格条件は、母集団を自分で閉じられないと実測できない」へ 2 事例目** —
   **1 事例目を指摘した側(本タブ)が翌日に同じ型を作りかけた。**
   **「閉じられない」と「見ていない」は別の失敗**で、後者は**陽性対照**で解ける。**対応案 (d)**
3. **新規候補「合格条件が観測経路を名指ししていたため、誰も見ていなかった経路の NFR-014 違反が実測で出た」** —
   **機能した点の候補**。ただし**限界**も書いた: 経路を名指しする形式は**名指しの網羅性を保証しない**
4. **既存候補「正本の改訂が、計画段階では見えない派生資産の追随を強制し、重さ分類の前提を崩す」へ 2 事例目** —
   **`/pr` の品質チェックで実測して見つけた**(下記)

### `/pr` の突合で見つけた取りこぼし 1 件(是正済み)

**事象**: `tests/test_orm_acceptance_sheets.py` が red。
**ステップ 7 で `data-model.md` の変更履歴に足した 1 行の散文**が、たまたま **`不変`・`書き換えない`** を含んでいた。
N3 受入シートは**本書全文から設計指定の 9 語を文書順に機械抽出する**ので、
**この 1 行だけで `出現 NNN` の採番が全部ずれ、人間判定 99 件を持ち越せない状態になっていた**。
**条文は 1 文字も変えていない。**

**是正(原因側を直した)**: シートを再生成して判定を内容照合で復元する道(TSK-474 が払った実費 — 42/89 が落ちた)ではなく、
**変更履歴の散文から 9 語を外した**。「8-3 節 ② の**不変条件**」→「8-3 節 ② の**検証の手順の条文**」/
「**書き換えない**」→「**そのまま残す**」。**意味は保ち、母集団を汚さない。**
同じ行に**なぜそう書くか**の注記を残した(次に変更履歴を足す人が同じ語を使わないように)。

**結果**: `tests/test_orm_acceptance_sheets.py` **13 passed**(シートの差分 0 行)。
**人間判定 355 件(N1 102 / N3 99 / N4 54 / N7 100)は 1 件も失われていない。**

**`data-model.md` が動いたので digest 2 件を取り直した**(TSK-475 の失敗型 — 片方だけ直さない):
`shared-preconditions.json` の `git_blob_digest` = `7047aee9…` → **`2d20816e…`** /
`schema-manifest.json` の `canonical_source.sha256` = `48b64926…` → **`c66ebb26…`**。
**取り直した後にもう一度実測して一致を確認した**(`hash-object` の実測値とも一致)。
`tests/test_check_shared_preconditions.py` + `tests/test_orm_acceptance_sheets.py` **22 passed** /
`backend/tests/test_schema_manifest.py` **14 passed** / `check_docs_status.py` **0 violations**。

**この取りこぼしが出た理由**: ステップ 7 の検証を**影響範囲**(authz 系 + digest 2 件)に絞ったとき、
**`data-model.md` を母集団にする検査**を影響範囲に数えていなかった。
**正本を 1 行でも触ったら、その正本を全文走査する検査も影響範囲である。**

### 残した申し送り

- **δ・運用側**: `hide_parameters=True` が隠すのは **SQLAlchemy の束縛値ログと SQLAlchemy 例外**だけである。
  **Postgres サーバーの文ログ**と、**手動で有効化する psycopg の低層トレース**は制御しない。
  **配備時にこれらを有効にしない運用確認が要る**
- **U-M1**: `_PUBLIC_CALLERS` は(呼び出し元, 呼び出し先)の 2 要素タプルの**集合**のままで、
  **形は変えていない**。U-M1 側が 1 対を足す予定だが支障はない
- **TSK-457**: 本単位は**テナント文脈を生成しない**。発行の機構と検査器は 457 の射程である
- **δ(TSK-470)— P1-②(ループバック TCP)**: 敵対レビューの読みは**原典で正しい**
  (`data-model.md` 8-2 節がローカル接続を **UNIX ドメインソケット**と定義している)。
  だが `docker-compose.yml` は **`127.0.0.1:5432`** を公開しており、**条文どおりに締めると開発 DB が落ちる**。
  **本単位はログインの経路を開かないので、締める実益がここには無い。**
  `_local_endpoint()` は**判定内容を変えずに残した**。
  **δ がログインの経路を開くときに、compose を UNIX ソケットへ寄せたうえで締める**
- **ハーネス(別タスク)— スキーマ契約テストの母集団の規則**: ステップ 7 の
  `backend/tests/db/test_authz_log_safety.py` が `pitchlog.db.engine`(**接続の工場**)を import するため
  母集団へ拾われ、`tests/test_core_guard.py` の
  `test_schema_contract_test_population_does_not_depend_on_branch` が red になる。
  **同じ形で入っているファイルは他に 2 件**(`backend/tests/test_authz_connection_guard.py` /
  `backend/tests/test_authz_log_safety.py`)あり、**表明が `backend/tests/db/test_authz_` という
  接頭辞で切っているため見逃されていた** — **規則が広すぎるのであって、本 PR の新設ファイルが
  特異なのではない**。**3 件とも `core-areas.json` の別パターンで既に保護対象**
  (`backend/tests/db/*` / `backend/tests/test_authz*.py`)なので、
  **規則を狭めても保護範囲は 1 件も減らない**(当方実測)。
  **`tests/test_core_guard.py` は検査経路そのもの**なので本単位では触らない

### 検証

**利用者の指示により全件は回していない**(CI に任せる)。影響範囲のみ:
ステップ 6 = **81 passed / 8s**、ステップ 7 = **76 passed / 8s** + **実 DB 6 passed / 23s**(使い捨て Postgres)。
`check_docs_status.py` **0 violations**。`ruff format` / `ruff check` / `ty check` 通過。
**TB002 の識別子照合 157 件・一致 0 件。**
