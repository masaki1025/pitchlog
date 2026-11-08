# 妨害操作の製品接続計画

状態: active。既承認 `docs/features/mvp-game-operations-product/plan.md` の step1/2 にある妨害操作を、打球群固定 `2b762ede4c868c09156d898bd2d9ecb0c08f9c54` の後続別familyとして実装する。PO委任rootの2026-11-08指示で枝を分離し、打球群の公式artifact/旧53をこの枝の着手で書き換えない。

## 既決根拠と範囲

要件書付録E `INT-01`〜`INT-07`、FR-004の裁定原本、`contracts/state-transition/state_transition_contract_v1.json` matrixRows28〜30、既 `T1InterferenceRulingV1` の閉形を使う。打撃妨害の採用側、走塁妨害の授与塁、守備妨害のアウト対象/帰塁先は記録者・審判入力を唯一の根拠にする。結果ID・走者位置から推定しない。状態・得点・旗は既TS唯一核のRuleへ実観測を渡し、BE/SQLへ別計算を作らない。現行正式給源で欠ける裁定形式は候補packetとしてrootへ渡し、未観測を成功させない。

編集所有は専用WT `feature-mvp-interference-product-20261108` の frontend domainの妨害rule/唯一state核の有限flag導出/API/provider/画面と各専用spec、backend domainrtの閉型・sync V7観測/物理投影の有限検証と各専用pytest、本計画だけ。共有 `contracts/`・authz SQL・registry・正式pin・T5・台帳はroot唯一writerへbefore SHA付きpatch提案で渡す。旧 `BattedHitT1Input` の旧形/過去期待値を変更せず、新 secondary-result 専用閉variantを別に作る。

## 実装単位

1. 既代表INT-02（打撃妨害罰則採用）、INT-06（守備妨害で打者アウト）、INT-04（走塁妨害で打者への授与）を、原典の全裁定入力・ID/在塁/帰塁条件で有限接続する。旧通常/打球/RunnerEvent/NPの拒否を保つ。
2. INT-01/03/05/07へ、既裁定が揃う範囲を同じ核/同じ元原本から拡張する。RBI/OUT3や未採用実プレイを推測しない。
3. rootが閉schema/SQL/pinを直列接合した同候補で画面→同期/再掲→GET/物理/T5を検証する。候補純成功と実PG/正式受理を区別し、未達はMVP残件として保持する。

各実装ステップは元mvp-game-operations-product計画のstep1/2に属し、妨害固有の新たな野球意味を作らない。原典から一意に決まらない入力だけ具体例と必要観測を示して閉じる。
