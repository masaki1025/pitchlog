---
feature: mvp-interference-product
status: active
承認: 済（PO委任Codex主担当/root、2026-11-08 19:44 JST）
重さ分類: コア領域
branch: feature/mvp-interference-product-20261108
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-interference-product-20261108
created: 2026-11-08
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
---

# 妨害操作の製品接続計画

状態: active。既承認 `docs/features/mvp-game-operations-product/plan.md` の step1/2 にある妨害操作を、打球群固定 `2b762ede4c868c09156d898bd2d9ecb0c08f9c54` の後続別familyとして実装する。PO委任rootの2026-11-08指示で枝を分離し、打球群の公式artifact/旧53をこの枝の着手で書き換えない。

## 既決根拠と範囲

要件書付録E `INT-01`〜`INT-07`、FR-004の裁定原本、`contracts/state-transition/state_transition_contract_v1.json` matrixRows28〜30、既 `T1InterferenceRulingV1` の閉形を使う。打撃妨害の採用側、走塁妨害の授与塁、守備妨害のアウト対象/帰塁先は記録者・審判入力を唯一の根拠にする。結果ID・走者位置から推定しない。状態・得点・旗は既TS唯一核のRuleへ実観測を渡し、BE/SQLへ別計算を作らない。現行正式給源で欠ける裁定形式は候補packetとしてrootへ渡し、未観測を成功させない。

編集所有は専用WT `feature-mvp-interference-product-20261108` の frontend domainの妨害rule/唯一state核の有限flag導出/API/provider/画面と各専用spec、backend domainrtの閉型・sync V7観測/物理投影の有限検証と各専用pytest、本計画だけ。共有 `contracts/`・authz SQL・registry・正式pin・T5・台帳はroot唯一writerへbefore SHA付きpatch提案で渡す。旧 `BattedHitT1Input` の旧形/過去期待値を変更せず、新 secondary-result 専用閉variantを別に作る。

## 実装単位

| # | 単位 | 到達条件 |
|---|---|---|
| 1 | 閉裁定を唯一核へ接続 | 代表INT-02/06/04から全7分岐へ、原典の裁定原本・実ID/在塁/帰塁を要求し、旧通常/打球/RunnerEvent/NPを維持 |
| 2 | 画面・元原本・保存へ接続 | 採用側・授与塁・アウト対象の明示値をV7とT1で全値照合し、未採用実プレイ/RBI/OUT3を推測しない |
| 3 | 統合・独立確認 | rootが閉schema/SQL/pinを直列接合した同候補で画面→同期/再掲→GET/物理/T5を検証し、純候補/実PG/正式受理を区別 |

各実装ステップは元mvp-game-operations-product計画のstep1/2に属し、妨害固有の新たな野球意味を作らない。原典から一意に決まらない入力だけ具体例と必要観測を示して閉じる。
