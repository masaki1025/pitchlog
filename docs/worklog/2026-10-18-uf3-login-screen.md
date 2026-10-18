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

## 正式レビュー第1周と採用修正

- 第1周対象`fe2d9c2c`。指定wrapper adversarial exit0・P0/P1/P2=0、Claude CLI exit0・P0=0/P1=0/P2=4。ログは`/home/ymdms/.cache/pitchlog/uf3-reviews/round1-{adversarial,claude}.log`。Claudeは静的評価、wrapperのVitestはread-only cache制約で起動前停止しており、独立再試験成功とは記録しない。
- 4件全採用: 明示再確認401→idle、認証済み後の再submit抑止、常設live/statusとfocus復帰、pendingガードの高感度試験。C1/共有client/store/router/core資産は変更なし。
- pendingガード一時除去の故障注入では二重操作試験が赤となった。元へ復元し、通常の全件試験に除外・timeout変更はない。
- server正規DTOに文字数制限がないことから旧maxlength50/128を除去。副題の色を明背景slate-600へ修正し、旧典拠とのclass差分とコントラスト根拠をresearchへ記録した。
- 第2周は第1周修正差分と影響に限定して2正式経路へ依頼する。本人逐行確認は未実施のまま維持する。

### 採用修正後の検査

型検査・ESLint全件・Prettier全件・buildが成功。全Vitestは69 files / 1,265 passed（72.52s）で、固有28件を含む。build closureはconforming・9 files・external 0・violations 0。追加の除外・timeout緩和なし。`git diff --check`成功。レビュー第2周の結果は別途記録する。

### 第2周の結果（採否待ち）

修正差分限定の正式第2周は両exit0。adversarial P0=0/P1=0/P2=1（statusがbusy form内にあり通知保留され得る）、Claudeは可決P0=0/P1=0/P2=3（認証済み再submit試験のhandler感度、darkラベルのコントラスト、空チーム名時のfocus先）。第3周は実行せず、親へ4件全採用の最小追随案を提示した。採否と未再レビュー範囲は別途固定し、本人確認を代行しない。第2周への入力後に確定した全frontend成功結果は前節のとおりであり、レビューが再試験したとは記録しない。

- 第2周prompt SHA-256: `7d5ab0db08483f45483f7d8cd082f935773c608a47ece61382b87964548d460f`
- adversarialログSHA-256: `b3697b740355e57e1979f2c457fb3597596bd1336c266e65f3a14deb251922a3`
- ClaudeログSHA-256: `b761547ecfec0b47db8efd217866a9211df6cc92035049d96744755fb611c7a1`

### 第2周の採否と最終追随

親が第2周4件を全採用した。statusをbusy form対象外へ配置、認証済み後submit試験の感度強化、darkラベルのコントラスト、空チーム名時のfocus先を修正した。固有30件成功。authenticated submitガード一時除去の故障注入ではfetch1回期待に対し2回となり追加試験が失敗、元へ復元した。通常検査には除外・timeout緩和なし。

第3周は実行しない。第2周後の未再レビューは上記製品の局所修正と試験・資料であり、本人逐行確認対象として残す。C1/C2/共有client/store/router/core資産や認証契約の変更なし。実スクリーンリーダー受入は未実施で、DOM試験の成功から実施済みを推定しない。最終全frontend品質検査の確定結果は別記する。

### 最終採用反映後の全検査

`vue-tsc --noEmit`、`eslint .`、`prettier --check .`、build、全Vitestが成功した。Vitestは69 files / 1,267 passed（75.72s、固有30件含む）、build closure conforming・9 files・external 0・violations 0。`git diff --check`成功。製品/specをこの検査後に変更していない。全件の除外・timeout緩和なし。親がコミットするまで本worktreeに5ファイルを保持する。

## PR準備（未提出）

親がレビュー追随を`01014f69022399909db128f56c92d7e8a1eb96be`へコミットした。新規`pr-preparation.md`に同HEADの全5ファイルとblob SHA-256、本人未記入欄、レビュー採否・最終未再レビュー差分・全frontend1,267成功を固定した。資料追加後は本人対象6ファイルへ増えるため、次HEADで再導出する。

軽量検査はdocs-status20文書/違反0・design propagation・diff checkが成功。正本同期は初回「影響する正本節なし」で失敗したため、既存plan§3.1へ正本反映なしと正本外同梱対象の宣言だけを補い、exit0に解消した。正本・shared・製品は変更なし。ハーネス運用評価台帳への追記なし（局所UI実装と通常レビュー追随であり、新しい制御目的・確定した運用傾向の追加はない）。

基線493342beのcore paths5領域とguard_pathsへの全5パス照合は0件。LoginScreen*未登録による意味コアの検出漏れであり、機械通過・本人未チェック拒否の成功とは扱わない。U-F13側の宣言/登録と接続受入を待ち、active維持・未提出とする。push/PR作成/commitは実施していない。
