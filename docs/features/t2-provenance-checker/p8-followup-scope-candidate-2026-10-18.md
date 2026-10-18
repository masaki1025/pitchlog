# P-8契約追随の最小追補・判断対象の抜粋

状態: **未承認の範囲候補**。既存計画の4ステップ、承認、レビュー回数を変更しない。
比較点: T2枝の引継ぎHEAD `0ed529f6` / origin/develop `156dd139`。
本書の作成・記録は調査成果であり、下表の規範行・case・正本の変更は未適用。

今回承認されたCLI予約値偽装の限定是正は元ステップ1の範囲内で別途実施する。
E11=A、E07=B、E09=B、E02=A、E10=A、E08=AとE12のN>R拒否/N=R非拒否は既承認。
**判断対象は以下の具体的な追随範囲と未確定の表現設計だけ**で、意味裁定の再承認は求めない。

## 変更対象・意味・理由・独立期待値への影響

パスの略記: C=`contracts/state-transition/`、S=`scripts/`、REQ=`docs/requirements/requirements-pitchlog-2026-07-22.md`。
各行の「意味追加なし」は、承認済みの意味を変えないという意味であり、現行契約の被覆が十分という意味ではない。

| 対象 | 具体的な変更対象・範囲 | 意味の変更有無 | 必要な理由・現物照合 | P-6独立期待値への影響 |
| --- | --- | --- | --- | --- |
| E11=A | REQ FR-020柱書へ、攻守交代後の評価位置と攻撃開始を区別する限定明文を追補 | 追加なし。既承認の限定を明記 | C/game_end_contract_v1.json の COLD-08/COLD-09/XMARK-02はbottom/0死/走者なし/0-0かつx-mark。FR-020 XMARK-01負例・XMARK-02正例、FR-005、F-1 COLD-02と一致 | 既存3行・102caseの値は変更不要。原典追補後の対象版・根拠への独立照合は残る |
| E07=B | decision.xMarkは単一値を維持。GAP-05の表示導出入力・対象セル・検証契約を追加（下節） | 追加なし。出力のセル配列化はしない | schemaはrecorded-score/x-mark/blankを許すが、契約はblank 0行/0case。coverageのtargetCellは「直近に完了した表に対応する裏の得点セル」。単一値維持だけではXMARK-03を被覆できない | 既存248caseのxMark値は変更不要。新しいセル表示caseは別の独立期待値対象。GAP-05は未解消のまま維持 |
| E02=A | REQ FR-010/FR-005の促しを追補。C/game_end_contract_v1.jsonへ宣言済み状態の行・case、必要なschema/descriptor・展開器/checker追随 | prompt=falseは既決。宣言後outcome等の既存フィールドの扱いは表現設計が未確定 | 現8行はすべてstate.gameEnded=falseで宣言後を主張しない。既存trueを一律falseへ反転する変更は不適切 | 新規宣言後caseは独立確認が必要。既存行の期待値を一括変更しない |
| E10=A | REQ FR-007/FR-005の促しの意味を追補。再開から再宣言までを示す入力文脈をdescriptor/schemaへ追加し、専用行・caseでlock=false/detected=true/prompt=trueを保持 | 3値と通知の意味は既決。再開状態をどこへ保持するかは表現設計 | state.gameEnded=falseだけでは通常進行と再開を区別できない。毎球の強制ダイアログや再ロックは導入しない | 入力型が増えるため、既存248caseの既定文脈・新規再開caseとも対象版を固定して独立照合する |
| E09=B | REQ FR-005/006のロック中undo可・交代不可・undo後再評価を追補。C/state_transition_contract_v1.jsonのoperationRows/undoRows・対応schemaと544/545/U-F8受け口へ対応づけ、必要な操作caseを追加 | 追加なし。終了宣言後の権限は拡張しない | T2 decisionには操作許可フィールドがない。T2へ権限フィールドを推測追加して閉じることはできない | 操作/undo/再評価の新規caseを独立対象へ追加。T1資産変更は元provenance計画のT1不変条件を超えるため、別途明示した範囲だけで実施 |
| E08=A | REQ F-1へPO製品優先規則として記録。通常終了とコールドの同時成立を固定したT2行・caseを追加し、cold-endを主張 | 追加なし。条文からの導出とは記録しない | NORMAL/XMARK行はコールド空、COLD行は通常終了との同時成立を固定していない | 新規競合caseを独立確認。既存通常終了・コールド単独の値を変更しない |
| E12 | 550側承認済み追補の統合後、C/input_axes_descriptor_v1.jsonの組合せ規則へ相関要求、C/game_end_contract_v1.jsonへruleValidationCases（候補名）、schemaへ閉じた相関型、S/check_deriver_dependencies.pyへ相関要求型、S/check_required_set_coverage.pyへexact-set検査を追加 | 追加なし。N>R拒否、N=Rはこの条件で非拒否 | 既存validationErrors 12件は単一軸の不正境界。相関をそこへ押し込まず、禁止値start-inning:R+1も宣言しない。deferredValidationErrorsの既存12件は保持し相関要求を別集計 | 新しい拒否・非拒否要求をT2側で独立確認。550の保存入口試験を流用しない。規則入力の新コレクションを消費する製品側試験も別途必要 |
| G6-E05 | サヨナラ前得点の観測入力をdescriptor/schemaへ追加する案と、既存履歴文脈から導出する案を比較し、行前提とcaseを機械照合 | サヨナラ前は同点/劣勢という意味は既決。観測形式を決める | 状態は適用後なので前得点を直接表せない。自然言語remarksの追記だけでは不足。棚卸し資料の「E05=段2件で成立1件」は正式G6-E06との混同 | 前後得点・有効得点を含むcaseの独立再計算が必要。得点上限の544側受理と区別 |
| G6-E06/E04 | 設定2段で成立1件、設定あり成立0件の具体入力・行・caseを追加。COLD-09は配列逆順で同一出力を検証 | 追加なし。COLD-07/08/09の既存明文への追随 | COLD-08は設定1件/成立1件に限定し、remarksで設定複数の場合を除外している | 新規caseを独立確認。配列順変異検査は値の独立検証そのものとは数えない |
| G6-E14 | 操作kind/payloadの不整合を入力正規化で拒否する案と、宣言済み到達不可として除外する案を比較。descriptor・schema・checker・caseの適用範囲を限定 | **境界の具体設計は未確定**。どちらを選んでも既存比較面を黙って縮小しない | ADR-003 D-8は終了判定の入力をプレイ入力列+規則スナップショットとする。「eventに依存しない」という旧メモだけでは異常入力の免除根拠にならない | 正常/拒否の対象母集団が変わるため、独立確認範囲と除外根拠を明示 |
| DRAW残件 | C/game_end_coverage_declaration_v1.json のuncoveredClauseBranchesを正として、DRAW-01〜10の検証先・行/case・宣言検証を対応づける。branch_row_mapping/gap_registerも整合させる | 意味追加は提案しない。意味判断が必要なら別途選択肢を提示 | 全10件がGAP-04で未被覆として残る。DRAW-05だけoperationRows/ST-OPERATION-e6c67c06707d5759のcrossLayerResolutionあり。これを全件被覆としない | 追加した各層のcaseを独立対象化。保存時拒否と実行時終了のcaseを区別する |

E01のプレイ適用後/攻守交代後の評価時点はcase設計で区別する。E03/S22は546の受理と544反映、E13はFR-040不採用裁定の統合・manifest宣言を確認する。どちらも他担当の完了を代記しない。

## 共通で波及する資産

- 入力軸/型を変える項目: descriptorのschema・digest・projection、T1/T2のinputAxesDescriptor参照、必要な展開器・派生被覆記録・依存読取りallowlist。
- T2トップレベルを変える項目: Python `backend/src/pitchlog/domaincheck/runners/handoff.py` とTS `frontend/src/testing/handoffLoader.ts` の閉じたキー集合、共通変異fixture・両loader試験、C/appendix_e_consumer_handoff_v1.jsonのdigest。
- 行/caseを変える項目: C/clause_branch_register_v1.json・branch_row_mapping_v1.json・game_end_coverage_declaration_v1.jsonの固定集合、S/expand_game_end_cases.pyの再現展開、S/check_required_set_coverage.pyと対応試験、gate6の再署名材料を追随する。既存受理履歴を削除・置換しない。
- 原典と期待値を改訂する項目: provenance.sourcesの構造化典拠集合を追随するが、not-performedは維持し独立検証済みへ書き換えない。

## E12の能動検証候補

相関要求は `requirementKind=rule-correlation`、`ruleId=cold-start-not-after-regulation`、具体的な規則スナップショットと期待 `reject` / `not-rejected-by-this-rule` を保持する。

最低例: R=9/L=12/タイブレークなし/点差1の1段で、N=10を拒否しN=9をこの条件では拒否しない。N<R、複数段の一段だけ違反、段順逆転、R下端/中間/上端も扱う。R=99で値域内N>Rを捏造しない。
要求は実装出力から逆算せず、宣言から導出してexact-set照合する。欠落・重複・期待逆転・入力と関係の不一致・未知キーを拒否し、常時拒否/常時通過の変異を落とす。

550枝 `40933555` のE12要件追補は承認済みだがdevelop未統合。developの要件v2.15はD-14-mの内容であり、550側の同番号とは内容が異なる。**統合と版番号調整を先行条件**とし、追補をdevelop反映済みとは記録しない。

## GAP-05の入力・対象セル・検証方法候補

推奨: E07=Bのまま、表示側の契約/fixtureに対象セル `{inning, half}`、開始済みセル集合、記録得点、直近完了の表、対応する未開始の裏、終了理由/宣言時点を保持する。T2の単一xMarkからX対象セルを特定し、セルごとにXMARK-01→02→03の順で評価する。

| 具体入力 | 対象セルと期待 | 拒否する変異 |
| --- | --- | --- |
| 5回表完了時の後攻リードでコールド検知・宣言前 | 5回裏=X、6〜9回の両セル=blank | 将来回もX、宣言までXを出さない |
| 5回裏途中のコールド | 5回裏=記録得点、6〜9回=blank | 開始済み裏をXにする |
| 7回表途中の打切り宣言 | 7回表=記録得点、7回裏と以後=blank | 未開始表/裏をX、将来回を0にする |
| 9回表完了時に後攻リード | 9回裏=X | half=bottomだけで開始済み扱いする |
| 攻撃開始直後・初球確定前 | 当該セル=整数0 | 初球未確定を未開始扱いする |

対案はT2へ対象セル入力軸を追加する方式で、全射影・組合せ要求への波及が大きい。どちらも、入力→要求→行→case→検査の被覆と担当受理が揃うまでGAP-05を閉じない。

## 判断してほしい具体的な範囲

1. 上表の行・case・正本・mechanismへの限定追随と共通波及資産を、元provenance計画の除外範囲から追加すること。過去の4ステップ/コミット件名/レビュー回数は保持する。
2. 表現設計の推奨案: 再開文脈を入力に明示、宣言後outcomeは既存の終了理由を保持する案、GAP-05は表示契約へ収容、サヨナラ前得点は観測入力化、E14は入力正規化で拒否する案。これらは意味裁定の再承認ではなく、公開型・母集団・検証境界の判断。

判断後も、正本確定（7.6/7.3）、具体資産の正式承認、7.7受理履歴の追記、明示再署名、P-6独立期待値の受理、544/545等の担当受理を別々に管理する。
provenanceだけの旧再署名材料を、規範行/case変更後の再署名材料として流用しない。push/Draft PRの許可も本追補の承認とは区別する。
