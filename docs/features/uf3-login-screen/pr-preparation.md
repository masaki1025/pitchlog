# U-F3 / TSK-518 PR準備資料（未提出）

## Draft提出時の最新状態（2026-10-18）

コア登録の不足は解消済み。宣言8a73dd21/試験45f6acd6→JSON単独a794a637→記録ea1b3bdaの順で登録し、root全29,672成功/2 skip（1500.71秒）、core264・Ruff/ty・基線・製品/spec2件検出・本人未記入拒否に成功。専用cluster撤去済み。製品2blobは従来の検査HEADa4b98244から不変で、frontend1,267成功/backend2,574成功4 skip・型/lint/整形/buildを保持する。

plan in-review、通常push/Draft作成は承認済み。全9差分ファイルが本人対象。新しいcore3ファイルと上限後UI反映は未再レビュー、本人欄は未記入。以下のactive/登録不足/未許可/未実施root欄は過去の記録であり現状へ読み替えない。TSK-518全体・U-F13接続/通し受入・公開/マージは未完了。


## 最新候補の再検証（2026-10-18）

以下が現在の状態であり、後続に保持した旧HEAD・旧未実施欄は過去の準備記録である。

- 実基線: `156dd139a893845428a1ecab69632143f7694e0b`（#143実統合）。製品検査HEAD: `a4b982441b25b260a4532b5148bc8fb1c08166d7`。worktreeはディスク側へ復元し通常mergeした。
- frontend **69 files / 1,267 passed**、root全件 **29,670 passed / 2 skipped**（1698.99秒）、backend全件 **2,574 passed / 4 skipped**（3049.63秒）、全終了コード0。型・ESLint・Prettier・build、root/backend Ruff・ty・backend format、tenant境界・frozen不変量・認可catalog成功。独立した専用DBを終了し、共有DB/他担当の作業へ破壊的変更なし。
- backendのwarning1は既存db_fixtures再読込、skip4は既存の製品化後dry-run。除外追加・timeout緩和なし。検査後の記録更新で製品/specの2ファイルのSHA-256が固定manifestと同じことを確認する。
- **LoginScreen*は意味上Tだがまだ機械未登録**。追加1パターンは未承認で、本PRの全ゲート通過とは記録しない。status active、本人欄は空、push/PR/CIは未実施。従来の2経路各2周のレビュー採否と最終反映の未再レビューを維持する。
- U-F13の宣言/登録待ちと、C1の完了・#143共有編集待ちを区別する。後者は解消済み。実画面/API/DB通し・TSK-520受入・TSK-528全体は未完了で、経路未登録の本画面から公開しない。
- C1の新しいlogin/session相関候補はU-F13専用branch `379aef25`の判断資料に固定し、別の未承認契約として扱う。既C1の受理/本人回答を取り消さず、本UIへ新DTOや新storage契約を無断追加しない。


## 概要

正規C1 clientを再利用する経路未登録LoginScreenを実装した。loginのack後にsession DTO検証が成功し、現世代・認証済み状態・tenant IDが一致した場合だけauthenticated emitする。認証拒否・未認証・結果未確認を分け、明示GET再確認とlogoutだけを許し、資格情報・mutationを自動再送しない。

**未提出・計画active維持。core path未登録のためPR作成へ進めない。** 製品は実装・試験済みだが、機械未検出を検査の成功と扱わず、本人逐行確認・U-F13での実画面→実API→実DB受入を未実施とする。push・PR作成・公開・マージは本資料作成時に行っていない。

## 関連

- Notionタスク: <https://app.notion.com/p/3f493b75e687814ca3c7fead50df2a14>（TSK-518）
- 実装計画書: [plan.md](plan.md)
- 移植4点・採否: [research.md](research.md)
- 作業記録: [2026-10-18-uf3-login-screen.md](../../worklog/2026-10-18-uf3-login-screen.md)
- 専用branch: `feature/uf3-login-screen`
- develop基線: `493342be37d4383ca572f8d1c826a3f184a4d213`
- 検査対象HEAD: `01014f69022399909db128f56c92d7e8a1eb96be`

本資料初版と計画§3.1の追随は864abff7152e530323dd90c80eaa8fdc535020c6へコミット済み。製品/specのblobは上記検査対象HEADと同一。最終報告HEADの本人対象は本資料を含む全6ファイルであり、以下の旧5ファイル表だけで最終確認済みとは扱わない。TSK-518全体やU-F13接続の完了とはしない。

## 正本への反映（設計書7.6）

- [x] 正本影響を確認した（正本反映なし。計画§3.1の宣言と一致）。
- [ ] 更新した正本の変更履歴表に追記した（正本更新なしのため非該当）。
- [ ] docs/README.mdを現行化した（正本更新なしのため非該当）。

`check_plan_docs_sync.py`は初回「影響する正本節なし」でexit1。既存planへ正本反映なしと正本外の同梱対象だけを宣言し、同検査exit0になった。検査を緩和していない。ハーネス運用評価台帳への追記なし。今回の局所UI実装と通常のレビュー修正に、新しいハーネスの制御目的・確定した運用傾向の追加はない。

## テスト

- [ ] /check 全グリーン（root/backend全件を本U-F3候補で再実施しておらず、core path未登録も残る）。
- [ ] DoDを満たしている（本人確認・機械登録・接続受入を未了として維持）。

| 検査 | 結果 |
| --- | --- |
| frontend全件 | **69 files / 1,267 passed**、75.72秒。固有30件を含む |
| vue-tsc / ESLint / Prettier | 全件成功 |
| build | 成功。closure conforming、9 files / external 0 / violations 0 |
| 差分検査 | `git diff --check`成功 |
| plan正本同期 | §3.1追随後exit0 |
| docs-status | 20 documents / 0 violations、exit0 |
| design propagation | exit0 |
| backend/root全件 | U-F3候補では未実施。C1等の別HEAD成功を本候補の全品質成功へ流用しない |
| 実画面受入 | 未実施。経路未登録でありU-F13接続側が実画面→実API→実DBを確認する |

pending/認証済みhandlerのガードを一時除去する故障注入では各対象試験が失敗し、製品を復元した。故障注入の対象選択を全件試験の代用とはせず、通常全件では除外・timeout条件変更なし。

## レビュー（設計書6.3）

- [x] 反対側レビュー済み（実Claude CLI、2周。第1周P2=4、第2周P2=3を全採用）。
- [x] codex_run.py review adversarial 済み（2周。第1周P2=0、第2周P2=1を全採用）。
- [ ] コア領域/検査経路の変更: 人間による逐行確認を実施した
- 実施記録: 対象= 範囲= 方法=

両経路ともP0/P1は0。第2周後はstatusのbusy対象外配置、darkラベル、空チーム名時のfocus、handler感度試験と記録だけを追随し、**未再レビュー**として本人確認へ残す。第3周は実施していない。wrapperによるVitest再実行はread-only環境の一時ファイル制約で開始できず、独立再試験成功とは扱わない。Claudeは静的評価であり試験を実行していない。契約・計画の承認を本人逐行確認へ流用しない。

### 本人逐行確認対象（基準01014f69の5ファイル・最終差分全6ファイル）

対象は基線493342be37d4383ca572f8d1c826a3f184a4d213からHEADまでの全差分。各行を認証成功境界、旧Cookie/旧応答、epoch/tenant照合、未確認拒否、非再送、存在秘匿、escape、アクセシビリティ、移植差分と突合できるよう固定する。確認方法は本人回答前に推定して記入しない。

| ファイル | HEAD blobのSHA-256 |
| --- | --- |
| `docs/features/uf3-login-screen/plan.md` | `10a8006f135224850e292e3d81163fdbad954c764a3bba954d9794dc58446069` |
| `docs/features/uf3-login-screen/research.md` | `4e8b0ed78d789c2906a4a6c2c0bdee1f3c2eeeb81ee44df0acca155ab0d3cea9` |
| `docs/worklog/2026-10-18-uf3-login-screen.md` | `f8846b3dd24c8b0ace354134939f89a933193f00309ba13c5c03810b20a05e1f` |
| `frontend/src/screens/LoginScreen.spec.ts` | `25c5b6eeeda65723aae9925f7cb607047b81ae2ec978ae37b231d6c6c580443f` |
| `frontend/src/screens/LoginScreen.vue` | `531cd5025c9cb4f7daa7ac62e07d534b3a119d815fa9c2c7fd4267f7ae4c164a` |

最終HEADの本人対象は、この旧5ファイルと本PR準備資料の計6ファイル。表のhashは明示した基準01014f69の固定値で、後続資料差分を含む最終HEADのhashとは偽らない。確認対象範囲は最終HEADに対する `git diff --no-renames origin/develop...HEAD` の全差分とする。

## コア領域の意味判定と機械検出

- 意味範囲: テナント分離（T）。S/G/R/Dの製品変更はない。
- 基線core-areas.jsonの各5領域pathsとguard_pathsに、renameを無効化した5変更パスを機械照合した。**全領域0件、guard0件**。
- `LoginScreen.vue` / `LoginScreen.spec.ts` / `LoginScreen*`を包含する登録が存在せず、**意味上のコア変更が未検出**。非コア扱い・core gate通過とはしない。
- 未登録状態では本人欄未チェックを拒否する保証がないため、その非検出を本人確認ゲート合格の証跡に使わない。
- U-F13所有の承認済み宣言→JSON登録順序を維持し、登録後に対象検出・未チェック拒否・基線検査を再実施する。本PRでcore登録・検査器・共有凍結資産を無断変更しない。

この不足のため通常PRクローズ処理へ進まず`status: active`を維持する。検査が揃っていない状態を`in-review`や完了へ偽装しない。

## 後続依存・停止条件

C2の応答tenant確定契約とU-F13のroute/guard/safe redirectを親セッションが統合する。本画面にはroute path・router import・独自API/DTO・独自tenant供給を加えない。実API/DBの一覧・登録・編集・越境・認証切替受入は、その接続した最終候補で確認する。15経路全体・公開・マージは別の承認条件を維持する。

## 現在地導出（機械出力全文）

`feature_status.py`は全worktreeを列挙する仕様のため出力全文を保持する。U-F3の「不明（無記法の実装コミット混在）」は親のレビュー追随コミットがステップ記法なしのための非ブロッキング警告であり、ハーネスや履歴を書き換えて消していない。

<details>
<summary>PR準備時のfeature_status.py全文</summary>

```text
feature: feature/adr003-authz-candidate (feature/adr003-authz-candidate)
  段階: 未取得(plan 不在)
  ステップ進捗: 未判定(plan 不在)
  PR 状態: 未取得
  縮退: plan 不在

feature: adr003-d2iv-applicability (feature/adr003-d2iv-applicability)
  段階: 計画段階(計画レビュー周回 0 周・承認待ち)（確定ゲート 2 周）
  ステップ進捗: 未判定(計画段階)
  PR 状態: 未取得
  計画レビュー周回: 0
  確定ゲート周回: 2
  実行方式: 通常
  反映周コミット突合: 対象外(develop へマージ済み)
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: data-model-canonical (feature/data-model-canonical)
  段階: 実装状況: 不明
  ステップ進捗: 不明
  PR 状態: 未取得
  計画レビュー周回: 5
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: domain-calc-dsl (feature/domain-calc-dsl)
  段階: 実装前(全 60 ステップ)(ステップ記法のコミットなし(書式未一致の可能性))
  ステップ進捗: 0/60(ステップ記法のコミットなし(書式未一致の可能性))
  PR 状態: 未取得
  計画レビュー周回: 6
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 対象外(develop へマージ済み)
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: harness-gate-blockage-and-merge-resolution (feature/harness-gate-blockage-and-merge-resolution)
  段階: PR 段階(OPEN)（確定ゲート 2 周）
  ステップ進捗: 未判定(PR 段階)
  PR 状態: OPEN
  計画レビュー周回: 2
  確定ゲート周回: 2
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 確認待ち(実値の照合は対話セッションで)

feature: product-authz-surface (feature/product-authz-surface)
  段階: PR 段階(MERGED・/task-done 待ち)
  ステップ進捗: 未判定(PR 段階)
  PR 状態: MERGED
  計画レビュー周回: 12
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 対象外(develop へマージ済み)
  Notion 期待: 確認待ち(/task-done 待ち)(実値の照合は対話セッションで)

feature: req-legacy-frontend-gaps (feature/req-legacy-frontend-gaps)
  段階: 計画段階(計画レビュー周回 1 周・承認待ち)
  ステップ進捗: 未判定(計画段階)
  PR 状態: 未取得
  計画レビュー周回: 1
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: feature/review-substitution-ruling (feature/review-substitution-ruling)
  段階: 未取得(plan 不在)
  ステップ進捗: 未判定(plan 不在)
  PR 状態: 未取得
  縮退: plan 不在

feature: t2-provenance-checker (feature/t2-provenance-checker)
  段階: 実装中(ステップ 3/4 完了)
  ステップ進捗: 3/4
  PR 状態: 未取得
  計画レビュー周回: 2
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: tsk237-appendix-a-vectors (feature/tsk237-appendix-a-vectors)
  段階: 未取得(plan 重複)
  ステップ進捗: 未判定(plan 重複)
  PR 状態: 未取得
  縮退: plan 重複

feature: tsk344-dod-revision (feature/tsk344-dod-revision)
  段階: 計画段階(計画レビュー周回 0 周・承認待ち)
  ステップ進捗: 未判定(計画段階)
  PR 状態: 未取得
  計画レビュー周回: 0
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: tsk506-sync-http-entry (feature/tsk506-sync-http-entry)
  段階: 実装中(ステップ 3/5 完了)
  ステップ進捗: 3/5
  PR 状態: 未取得
  計画レビュー周回: 4
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: tsk545-game-end-unresolved (feature/tsk545-game-end-unresolved)
  段階: 実装前(全 3 ステップ)(ステップ記法のコミットなし(書式未一致の可能性))
  ステップ進捗: 0/3(ステップ記法のコミットなし(書式未一致の可能性))
  PR 状態: 未取得
  計画レビュー周回: 2
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: ud1-game-trash (feature/ud1-game-trash)
  段階: 計画段階(計画レビュー周回 0 周・承認待ち)
  ステップ進捗: 未判定(計画段階)
  PR 状態: 未取得
  計画レビュー周回: 0
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: uf8-game-recording (feature/uf8-game-recording)
  段階: 実装完了・/pr 前
  ステップ進捗: 10/10
  PR 状態: 未取得
  計画レビュー周回: 3
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: ug1-game-lifecycle (feature/ug1-game-lifecycle)
  段階: 実装状況: 不明
  ステップ進捗: 不明
  PR 状態: 未取得
  計画レビュー周回: 2
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: ug2-play-correction-acceptance (feature/ug2-play-correction-acceptance)
  段階: 計画段階(計画レビュー周回 0 周・承認待ち)
  ステップ進捗: 未判定(計画段階)
  PR 状態: 未取得
  計画レビュー周回: 0
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 対象外(計画書 未コミット)
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: feature/ur1-abc-plan-sync (feature/ur1-abc-plan-sync)
  段階: 未取得(plan 不在)
  ステップ進捗: 未判定(plan 不在)
  PR 状態: 未取得
  縮退: plan 不在

feature: ur1-recording-rights (feature/ur1-recording-rights)
  段階: 実装状況: 不整合(完了ステップに欠番がある)
  ステップ進捗: 不整合(完了ステップに欠番がある)
  PR 状態: 未取得
  計画レビュー周回: 7
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 警告(反映周番号の集合が確定ゲート周回と一致しない)
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: us1-sync-port-surface (feature/us1-sync-port-surface)
  段階: 実装状況: 不整合(ステップ記法が不正)（確定ゲート 2 周）
  ステップ進捗: 不整合(ステップ記法が不正)
  PR 状態: 未取得
  計画レビュー周回: 3
  確定ゲート周回: 2
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: ux1-fr014-rule-resolution (feature/ux1-fr014-rule-resolution)
  段階: 実装状況: 不整合(完了ステップに欠番がある)（確定ゲート 3 周）
  ステップ進捗: 不整合(完了ステップに欠番がある)
  PR 状態: 未取得
  計画レビュー周回: 4
  確定ゲート周回: 3
  実行方式: 通常
  反映周コミット突合: 警告(反映周番号の集合が確定ゲート周回と一致しない)
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: ux1-state-calc (fix/ux1-state-calc)
  段階: PR 段階
  ステップ進捗: 未判定(PR 段階)
  PR 状態: 未取得(縮退)
  計画レビュー周回: 5
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 未取得(実値の照合は対話セッションで)

feature: census-baseline-pin (fix/census-baseline-pin)
  段階: 実装前(全 10 ステップ)(ステップ記法のコミットなし(書式未一致の可能性))
  ステップ進捗: 0/10(ステップ記法のコミットなし(書式未一致の可能性))
  PR 状態: 未取得
  計画レビュー周回: 4
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 対象外(develop へマージ済み)
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: core-guard-uf8-postmerge-tests (fix/core-guard-uf8-postmerge-tests)
  段階: PR 段階(MERGED・/task-done 待ち)
  ステップ進捗: 未判定(PR 段階)
  PR 状態: MERGED
  計画レビュー周回: 3
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 確認待ち(/task-done 待ち)(実値の照合は対話セッションで)

feature: oracle-input-baseline (fix/oracle-input-baseline)
  段階: 実装中(差し戻し修正)（確定ゲート 8 周）
  ステップ進捗: 不明(無記法の実装コミット混在)
  PR 状態: 未取得
  計画レビュー周回: 6
  確定ゲート周回: 8
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: auth-session-verification-contract (feature/auth-session-verification-contract)
  段階: PR 段階(MERGED・/task-done 待ち)
  ステップ進捗: 未判定(PR 段階)
  PR 状態: MERGED
  計画レビュー周回: 2
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 対象外(develop へマージ済み)
  Notion 期待: 確認待ち(/task-done 待ち)(実値の照合は対話セッションで)

feature: tenant-match-metadata-contract (feature/tenant-match-metadata-contract)
  段階: 実装前(全 2 ステップ)
  ステップ進捗: 0/2
  PR 状態: 未取得
  計画レビュー周回: 2
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: tsk550-contract-evidence-split (feature/tsk550-contract-evidence-split)
  段階: 実装完了・/pr 前
  ステップ進捗: 1/1
  PR 状態: 未取得
  計画レビュー周回: 0
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: tsk550-delta-acceptance-a1c11248 (feature/tsk550-delta-acceptance-a1c11248)
  段階: 実装完了・/pr 前
  ステップ進捗: 1/1
  PR 状態: 未取得
  計画レビュー周回: 0
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: tsk550-independent-acceptance (feature/tsk550-independent-acceptance)
  段階: 実装完了・/pr 前
  ステップ進捗: 1/1
  PR 状態: 未取得
  計画レビュー周回: 0
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: tsk550-stagea-contract-acceptance (feature/tsk550-stagea-contract-acceptance)
  段階: 実装完了・/pr 前
  ステップ進捗: 1/1
  PR 状態: 未取得
  計画レビュー周回: 0
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: feature/tsk550-step1-gate-materials (feature/tsk550-step1-gate-materials)
  段階: 未取得(plan 不在)
  ステップ進捗: 未判定(plan 不在)
  PR 状態: 未取得
  縮退: plan 不在

feature: uf13-team-route-acceptance (feature/uf13-team-route-acceptance)
  段階: 実装前(全 3 ステップ)(ステップ記法のコミットなし(書式未一致の可能性))
  ステップ進捗: 0/3(ステップ記法のコミットなし(書式未一致の可能性))
  PR 状態: 未取得
  計画レビュー周回: 4
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 対象外(develop へマージ済み)
  Notion 期待: 進行中(実値の照合は対話セッションで)

feature: uf3-login-screen (feature/uf3-login-screen)
  段階: 実装状況: 不明
  ステップ進捗: 不明(無記法の実装コミット混在)
  PR 状態: 未取得
  計画レビュー周回: 2
  確定ゲート周回: 0
  実行方式: 通常
  反映周コミット突合: 一致
  Notion 期待: 進行中(実値の照合は対話セッションで)
```

</details>


## 承認済みコア登録の反映（2026-10-18）

山田正輝の追加承認に基づき、宣言/試験コミット→宣言追随試験コミット→JSONだけの別コミットでLoginScreen*をTへ登録。登録後core全264成功、実製品/spec2件検出、基線成功、本人未記入拒否を確認。先行264件中1失敗は1パターンの登録前状態を削除負例へ混同した試験、登録後1失敗は旧U-S1試験のtenant領域全体一致だった。登録済み基線からの削除負例、宣言済み追加だけを許す共通基線検証へ是正し、既存U-F5/U-F6/U-F8/RG1保持・未宣言/欠落/人間未記入拒否を維持。

製品2ファイルは既検査時から不変。追加コア差分のためroot全件をこの固定候補で再検証する。既定レビュー上限後の宣言/試験/JSON差分は未再レビューとして本人対象へ追加し、新たなレビュー実施済みとはしない。通常push/Draft作成は許可済み、本人確認・公開・マージは未実施。

## 2026-10-19: 認証相関追補後の本人対象

現在の差分は既存9ファイルを維持する。後発表示差分は未再レビュー、本人逐行確認は未実施。方法を推定しない。過去の1,267件は以前の候補で、今回の単独は1,273件成功。最新developの同期改訂をmergeしたがUI製品/specは不変。

| 対象 | SHA-256 |
| --- | --- |
| `frontend/src/screens/LoginScreen.vue` | `101dd37001dd0bd5cd53caa8bb5fd04a1d0fb887650115616d257944b23245aa` |
| `frontend/src/screens/LoginScreen.spec.ts` | `477fca50e2f70411b8824319ba490b70a80837efc4bbdd6929edbceb4b1be04c` |

- [ ] コア領域/検査経路の変更: 人間による逐行確認を実施した
- 実施記録: 対象= 範囲= 方法=
