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
