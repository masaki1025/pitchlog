# 2026-10-18 U-F3 / TSK-518 ログイン画面

## 承認・所有・基線

- ユーザーがC1 PR #147統合後のC2/U-F3実装・関連試験・既定レビュー・PR準備を承認。基線は`493342be37d4383ca572f8d1c826a3f184a4d213`。
- Codex D内でU-F3の非共有実装を並行担当。本worktree以外の編集・他PR変更なし。LoginScreen/固有spec/UF3資料のみ所有する。親がコミット・共有core登録・レビューを統括する。
- C1正規client/storeを再利用し、U-F13が経路/redirectを所有する。C2のmetadata照合は共通clientが所有し、U-F3では複製しない。
- 人間逐行確認は未実施。方法を推定記入しない。公開・マージを行わない。

## ステップ1

- 経路未登録LoginScreenを実装。mount時にC1のsession確認を呼び、login ack後のsession DTO検証済み結果だけをepoch/store/tenantと照合してauthenticated emitする。
- 401等は固定拒否、429は一般案内、session不正/通信失敗は認証結果未確認。明示GET再確認/正規logoutを提示し、資格情報・mutationを自動再送しない。passwordは送信開始・世代変更・unmount時に入力から破棄する。
- 18試験成功（正規APIをmockせずfetch境界で試験）。直接mount、login→session、固定拒否4状態、429、不明2状態、二重送信、明示GET、logout確定/未確認、再生成、旧session/旧login、安全側cache破棄、unmount、escape/labelを含む。
- `pnpm exec vitest run src/screens/LoginScreen.spec.ts`: 18 passed / 1 file（1.32s）。`vue-tsc --noEmit`・対象2ファイルのESLint・Prettier check・build成功。build closureはconforming、9 files / external 0 / violations 0。

## 申し送り

C1/C2/API/DTO/tenant/資格情報保存の独自実装なし。route接続・safe redirect・実API/DB通しは親のU-F13接続範囲。新規core登録・正式レビュー・本人逐行確認は未完了として維持する。

## ステップ2

- ステップ1は親セッションが`cffa8662`でコミットした。製品側ではemit条件からteam_nameの等価判定を除去し、表示名を認可キーにしない契約へ合わせた（authEpoch・認証済み状態・tenant ID照合は維持）。追加6試験で24件成功（1 file、0.87s）。
- 追加: 不正session DTO後のtenant GET/POST送信拒否、遅延旧logoutの安全側無効化、A→B→C後の旧loginと明示GET、認証確定後の世代変更、再確認中の操作抑止、入力/応答の存在秘匿・escape。
- C1の正規API・store・cacheをそのまま使用し、fetch境界だけを代替した。未確認時にtenant-bound通信が出ず、自動資格情報再送・変更要求の再送がない。旧応答から新tenant・成功を採用しない。
- researchへ旧典拠・現行要件・Vue変換の移植4点を記録した。本人確認は未実施、対象・範囲・方法を未記入で維持する。
- 全frontend品質gate成功: `vue-tsc --noEmit`、`eslint .`、`prettier --check .`、build（closure conforming・9 files・external 0・violations 0）、Vitest 69 files / 1,261 passed（72.59s）。最終対象24件も0.94sで再成功。正式レビューは親セッションが統括し、未実施を成功扱いにしない。
