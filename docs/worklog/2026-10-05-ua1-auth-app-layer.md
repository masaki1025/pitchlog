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

## 決定

- 提示値の唯一の正規形は `<小文字・ハイフン付き UUID>.<小文字 hex 64 桁の HMAC-SHA256>`。HMAC の対象は UUID の正規形の ASCII バイト列。UUID の大文字・ハイフンなし・波括弧付き・前後空白、署名の大文字 hex・base64 の標準/URL 安全形・padding 有無は受理しない。
- 公開シンボルは `TokenPresentation` だけ。モジュールの `__all__` と非 `_` 名前空間の両方を exact-set 試験で固定した。署名失敗・形式失敗の例外メッセージは同一で、鍵・ID・提示値・署名を含めない。
- TB002 照合対象の製品モジュール識別子: `token_presentation`, `TokenPresentation`, `_PRESENTATION_PATTERN`, `_UUID`, `__all__`, `__init__`, `__slots__`, `_hmac`, `_re`, `canonical_id`, `decode`, `encode`, `expected`, `key`, `match`, `self`, `signature`, `signature_hex`, `token_id`, `value`。
- TB002 照合対象の試験モジュール識別子: `test_authz_token_presentation`, `TokenPresentation`, `UUID`, `_CANONICAL_ID`, `_TOKEN_ID`, `alternate`, `alternate_id`, `base64`, `canonical_id`, `error`, `expected_signature`, `forged_value`, `hmac`, `invalid_id`, `invalid_value`, `key`, `name`, `public_names`, `pytest`, `secrets`, `signature`, `signature_bytes`, `signature_hex`, `signer`, `standard_base64`, `test_alternate_signature_encodings_are_rejected`, `test_alternate_uuid_spellings_are_rejected`, `test_encode_and_decode_use_canonical_uuid_as_hmac_message`, `test_malformed_presentation_is_rejected`, `test_modified_id_is_rejected`, `test_public_symbols_are_exact_set`, `test_signature_from_another_key_is_rejected_without_leaking_input`, `token_presentation`, `upper_hex`, `urlsafe_base64`, `value`。

## 未決・次の一歩

- 鍵の環境変数からの読み取りと起動時検証は計画のステップ 2。ステップ 1 では実装しない。
