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

## 決定

- 提示値の唯一の正規形は `<小文字・ハイフン付き UUID>.<小文字 hex 64 桁の HMAC-SHA256>`。HMAC の対象は UUID の正規形の ASCII バイト列。UUID の大文字・ハイフンなし・波括弧付き・前後空白、署名の大文字 hex・base64 の標準/URL 安全形・padding 有無は受理しない。
- 公開シンボルは `TokenPresentation` だけ。モジュールの `__all__` と非 `_` 名前空間の両方を exact-set 試験で固定した。署名失敗・形式失敗の例外メッセージは同一で、鍵・ID・提示値・署名を含めない。
- TB002 照合対象の製品モジュール識別子: `token_presentation`, `TokenPresentation`, `_PRESENTATION_PATTERN`, `_UUID`, `__all__`, `__init__`, `__slots__`, `_hmac`, `_re`, `canonical_id`, `decode`, `encode`, `expected`, `key`, `match`, `self`, `signature`, `signature_hex`, `token_id`, `value`。
- TB002 照合対象の試験モジュール識別子: `test_authz_token_presentation`, `TokenPresentation`, `UUID`, `_CANONICAL_ID`, `_TOKEN_ID`, `alternate`, `alternate_id`, `base64`, `canonical_id`, `error`, `expected_signature`, `forged_value`, `hmac`, `invalid_id`, `invalid_value`, `key`, `name`, `public_names`, `pytest`, `secrets`, `signature`, `signature_bytes`, `signature_hex`, `signer`, `standard_base64`, `test_alternate_signature_encodings_are_rejected`, `test_alternate_uuid_spellings_are_rejected`, `test_encode_and_decode_use_canonical_uuid_as_hmac_message`, `test_malformed_presentation_is_rejected`, `test_modified_id_is_rejected`, `test_public_symbols_are_exact_set`, `test_signature_from_another_key_is_rejected_without_leaking_input`, `token_presentation`, `upper_hex`, `urlsafe_base64`, `value`。
- ステップ 2 の鍵は、CSPRNG 由来の 32 バイト以上を**標準 Base64 の padding 付き正規形**で設定する。`b64decode(validate=True)` の結果を再符号化して元の値と照合するため、非 ASCII・不正文字・padding 欠落・同一バイト列へ復号される非正規形を拒否する。環境変数値から生成元の乱数性を証明することはできないため、生成コマンドを設定契約として固定した。
- ステップ 2 の TB002 照合対象の導入識別子: `Exception`, `SigningKeyConfigurationError`, `ValueError`, `base64`, `binascii`, `bytes`, `key`, `len`, `require_signing_key_configuration`, `signing_key_config`, `str`, `value`, `variable_name`(`signing_key_config.py`); `TokenPresentation`, `_SIGNING_KEY_VARIABLE`, `os`, `require_signing_key_configuration`, `signing_key`(`app.py`); `SigningKeyConfigurationError`, `TokenPresentation`, `_SIGNING_KEY_VARIABLE`, `alphabet`, `alternate`, `app`, `base64`, `canonical`, `create_app`, `encoded_key`, `error`, `final_value`, `invalid_key`, `key`, `monkeypatch`, `pytest`, `secrets`, `str`, `test_alternate_base64_spelling_prevents_app_creation`, `test_authz_signing_key_config`, `test_create_app_uses_configured_signing_key`, `test_invalid_encoding_prevents_app_creation`, `test_missing_signing_key_prevents_app_creation`, `test_short_decoded_signing_key_prevents_app_creation`, `token_id`, `uuid4`, `value`(`test_authz_signing_key_config.py`); `_configure_signing_key`, `base64`, `encoded_key`, `monkeypatch`, `secrets`(`test_api_app.py` / `test_api_conventions.py`); `base64`, `encoded_key`, `import_module`, `monkeypatch`, `secrets`(`test_health.py`)。

## 未決・次の一歩

- ステップ 2 まで実装済み。次は委任元がステップ 2 のコミットを作る。ステップ 3 の DB 接続 TLS 検証には着手していない。
