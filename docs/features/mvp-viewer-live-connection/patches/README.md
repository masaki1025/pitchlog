# 共有接合patch

`shared-integration.patch` は、閲覧機能を製品appへ接続するための共有path差分です。このfeatureブランチには共有pathの直接変更を含めず、接合確認はpatch適用済みの一時worktreeで行います。

## 適用

リポジトリルートで、固定基線 `5cb4407d2f4df63428f15d8da8c576ff684e5a16` 起点のfeatureブランチへ:

```bash
git apply docs/features/mvp-viewer-live-connection/patches/shared-integration.patch
```

## 含む接合

- `backend/src/pitchlog/api/app.py`: 閲覧router登録
- `backend/src/pitchlog/api/tenant_access.py`: C2照合対象operation追加
- `contracts/authentication/cookie_identity_v1.json`: 同token Cookie対象operation追加
- `backend/src/pitchlog/authz/{ordinary_pitch_product,terminal_pitch_product,runtime_contract}.py`: 閲覧専用SQL 2関数の宣言・本文・runtime contract
- `backend/src/pitchlog/repositories/{function_operations,operation_registry,repository_contract}.py`: 閲覧tokenの型境界・固定関数登録・repository contract
- `contracts/authz/product/ddl-elements.json` / `function-bodies/manifest.json` / 新規body 2本: 正式認可資産
- `contracts/tenant_boundary/{repository-contract,runtime-authz-contract}.json`: 能力・token・operation・保護関数
- `frontend/src/router.ts`: `/games/:gameId/view`
- `frontend/src/screens/GameScreenEntryNavigation.ts`: 認証後戻り先に `/view` を1形だけ追加
- `frontend/src/screens/GameScreenEntry.{vue,spec.ts}`: 試合一覧からライブ閲覧への導線
- 上記に伴う既存試験の期待値更新

閲覧専用のbackend実装・画面・controller・transport・試験は、このpatchではなくfeatureブランチ側にあります。

## 検証

patch適用済みの一時worktreeで、少なくとも次を実行します。

```bash
cd backend
uv run pytest tests/test_viewer_read_sql.py tests/test_authz_repository_contract.py \
  tests/test_terminal_pitch_product.py tests/test_stats_native_function_registration.py \
  tests/test_function_operations_boundary.py tests/test_viewer_probe.py \
  tests/test_started_snapshot.py -q
```

2026-11-07の実測では435 passed。実HTTPS/owned PGの2試験は `handoff.md` を参照してください。
