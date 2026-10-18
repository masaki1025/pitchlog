# T2 P-8未受理候補

本ディレクトリは `docs/features/t2-provenance-checker/plan.md` の2026-10-18追補に基づく候補資産。
正式な`contracts/state-transition/`への変更、独立期待値の確定、再署名、P-6受理は行っていない。

検査コマンド（リポジトリルート）:

```sh
./.venv/bin/python scripts/check_required_set_coverage.py --candidate docs/features/t2-provenance-checker/candidates/p8_candidate_v1.json
```

- `p8_candidate_v1.json`: candidateId=`t2-p8-followup-v1`、schemaVersion=1。基準T2契約のRFC8785 digestを照合する。21件の相関要求（N>R拒否6件、N<R/N=R非拒否15件）、E08/E06/E04の具体入力5件、採用済み保持参照を含むlifecycle3件、表示セル入力/期待種別のfixture5件。
- `p8_candidate_schema_v1.json`: 候補の閉じた型。ruleSnapshot・decision・normalizedCaseと参照先の閉包は現行T2 schemaから複製した。正式なschemaの改訂ではない。
- `requirements-followup.patch`: E11限定明文と裁定4件の正本追随案。未適用。要件版・変更履歴を勝手に確定しない。550側承認済みE12追補はこのpatchに再起案せず、別枝の統合・版番号調整を先行条件として保持する。

正本patchは空白だけのcontext行を含めない0行contextの形式。適用可能性の検査は`git apply --check --unidiff-zero docs/features/t2-provenance-checker/candidates/requirements-followup.patch`で行う（正式適用は別ゲート）。

検査の保証範囲:

- 相関は候補descriptorから既存導出器内の候補要求型で導出し、候補契約の全件とexact-set照合する。既存12件のinvalid境界を変えず、禁止された`start-inning:R+1`のinvalid宣言を使わない。
- decision候補は現行行の出力と照合。E08は通常終了の出力のoutcomeだけをコールドへ置換する承認済み裁定の候補であり、先攻10点リード・R=L=9・9回以降適用の段・9回裏完了後の10回表の評価位置を使う。裏開始済みなのでxMarkはrecorded-score。正式分岐IDは未登録。
- 既存の具体入力/正規化検査を再利用し、設定段数と成立段数、段順入替の同一性を検査する。ここで製品用のコールド判定関数をコピー実装していない。全プレイ列での到達性や成立段数のドメイン再計算は保証しない。
- lifecycleは宣言前の完了評価から3値を保持し、phase/認可/投影prefixの整合性を別fixtureで実行検査する。詳細は[採用境界](adopted-boundaries-2026-10-19.md)。
- displayCasesは対象セル、開始有無、直近表完了、裏不要、記録得点を持つ入力/期待fixture。schemaと集合の検査であり、表示関数の出力比較は未実施。セル導出源の候補型/担当境界は採用境界に記載済み。正式な型反映、担当受理、製品の表示検証、P-6が残る。GAP-05はopen。

期待値は候補作成者が記入したもの。検査成功は製品T2の実行、P-6独立検証、正式被覆更新や担当受理を意味しない。CLIは`candidate-only`/`not-performed`/`runtimeOutputsCompared=false`/`formalCoverageUpdated=false`を明示する。

- `p8_boundary_evidence_v1.json`: 作者の人工fixture。context5、score観測2、kind/payload42、表示比較5。byte digestをschema/bundleで固定し候補検査器が実行する。独立期待値・製品出力はnot-performedのまま。
