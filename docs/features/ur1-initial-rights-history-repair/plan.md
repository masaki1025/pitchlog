---
feature: ur1-initial-rights-history-repair
status: in-review
承認: 済（PO委任によるCodex判断・限定履歴修復）
重さ分類: コア領域
worktree: ../../..
branch: feature/ur1-initial-rights-history-repair
created: 2026-10-24
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# U-R1初期付与候補の履歴修復計画

## 1. 背景・目的

実develop `31194a39c9083bbef6c14bde19c24a3e49d09f2e` 起点に、初期記録権付与の隔離部品だけをclean replacement PRへ再構成する。旧#173の `f48b5944fd94777bd132cd12a2da8e4727cfee8d` はcore JSONと基線定義試験を同一commitで変更し、実PRのcore guardが拒否した。内容単体の成功をnormal merge可能の証拠にしない。拒否条件・対象path・人間確認を緩めず、宣言→別JSON登録→実部品→新PR受理の履歴を作る。

この回はplan/researchだけを起案する。独立計画レビューとrootのPO委任承認後も、指定された1ステップだけ実施する。旧#173/156の全枝、旧HEAD `0aaa22e09d7e1a0301d03f7c63d188d9bba76844`、正式旧記録、保全物を保持し、merge/cherry-pick/force pushで旧履歴を運ばない。他作業の巨大branchへ移さず、必要なpathの内容だけを固定sourceから再構成する。

親の意味と9ステップは[U-R1親計画](../ur1-recording-rights/plan.md)を参照する。本4表は親新5の初期付与部品の提出履歴を修復する単位であり、親9表を置換/短縮しない。旧proxy planを再コピーしない。親計画review7回、旧#156/#170/#173の各レビュー系列、今回のP1→修正0・最終metadata0、旧成功/skip/中断と未完条件を保持する。新計画の回数で旧系列をリセットしない。

## 2. スコープと再利用

実装source/型/アルゴリズム/性能/認可の意味は旧0aaaの初期付与候補を維持する。実台帳、端末資格、運用鍵、実RecordingRightsPort、開始同一transaction、RG1 open、HTTP/画面接合を追加しない。D4/V12/復旧世代の実配置と製品開始条件を受理したことにしない。規則codec/計算をコピーしない。

| 区分 | 編集を許可する最小paths |
| --- | --- |
| ステップ1の宣言/検査 | `scripts/core_guard.py`、既存`tests/test_core_guard.py`。追加層とその試験だけ。判定関数/拒否条件/BASELINE_DEFINITION_PATHS/委任検証/既存必須文言は変更しない |
| ステップ2の登録 | `.claude/core-areas.json`だけ。下記exact2pathsを対象3領域末尾へ追加する |
| ステップ3の部品/試験 | `backend/src/pitchlog/recording_rights/__init__.py`、`backend/src/pitchlog/recording_rights/initial_grant.py`、既存候補path `backend/tests/test_initial_recording_right_candidate.py`。固定旧byteを再利用し、型/性能/業務意味を変えない |
| 必要依存 | `backend/pyproject.toml`、`backend/uv.lock`。既存sourceに必要な`cryptography==50.0.1`と同pin由来の推移依存だけ。旧lock全体を無条件コピーしない |
| 限定検査追随 | `scripts/check_tenant_boundary_bypass.py`、既存`tests/test_census_baseline_check.py`、`tests/fixtures/tenant_boundary/census-scoped-digests.json`。旧候補のsource hash付きTB002 exact47箇所/旧43→独立AST18のdigest拘束・範囲外拒否を保持 |
| 9凍結資産の候補 | `contracts/tenant_boundary/{base-allowlist,cache-invalidation-contract,census-baseline,db-api-inventory,frozen-inputs,negative-fixtures,repository-contract,runtime-authz-contract,tenant-context-allowlist}.json`。既存方式で実baseから初期付与差分だけを導出。frozen-inputsを含む不変資産は照合対象であり不要な書換えをしない |
| 生成定数3paths | `backend/src/pitchlog/authz/runtime_contract.py`、`backend/src/pitchlog/repositories/repository_contract.py`、`backend/src/pitchlog/repositories/tenant_context_contract.py`。実候補資産から既存生成方式でrevision/digestを追随 |
| ステップ4の正式反映 | 上記9資産内の権威履歴`base-allowlist.json`へ新実PRのrow1件だけ。`contracts/tenant_boundary/history-snapshots/<sha256>`は受理後、必要かつbaseに存在しない参照分だけ。`tests/fixtures/frozen-archive-cases/manifest.json`は既存方式で当該追加分へ追随 |
| ステップ4の委任対象 | `docs/features/mvp-delegated-core-review/policy.json`のtargetsに、新実PR番号/固定branchの1組だけを追加。既存targets/authority/有効条件を保持 |
| 作業証拠 | このfeatureのplan/researchのみ。旧proposal/handoff/重複snapshotは固定旧HEAD/path/blob/SHA参照で保持し再コピーしない。新PR受理案の完全9資産/8外部値、対象headと資料SHAをresearchへ固定する |

`.env`/秘密、旧worktree、親計画、legacy、正本本文、DB migration、正式認可catalog/関数56件、backend共通conftestは変更しない。旧63pathsの一括移植をしない。必要な意味/追加pathが見つかった場合は局所不足としてrootへ戻し、無断で拡大しない。

## 3. 影響する正本

**本文反映なし**。既存#148/162/174の確定本文と親9ステップを保持する。今回の変更は承認済み初期付与部品の履歴修復、限定凍結追随と新ID受理であり、新仕様/権限/型/性能変更を含まない。6.1/6.3の先行宣言・別登録と7.7の完全値/単一受理を守る。正式9資産の変更とpolicy targets追加は最終非作者レビューの対象とし、計画承認だけで正式受理完了にしない。

## 4. コミット分離とステップ

### core登録の限定集合と段階条件

`sync-protocol`、`recording-rights`、`tenant-isolation`それぞれの追加層を、順序付きexact集合
`backend/src/pitchlog/recording_rights/initial_grant.py`、`backend/tests/test_initial_recording_right_candidate.py`
とする。前者は旧登録3領域を保持し、後者は実行試験の単独変更も捕捉する追加である。initは固定docstringだけで業務処理を持たず、無関係なrecording_rights全体globを追加しない。

ステップ1は現JSON全byte不変・source/test双方不在を確認する。実JSONに登録前/登録後の合成2状態を用意し、source未作成でも宣言/別登録を検証できる試験とする。実設定で未登録を無条件に許可する試験にはしない。source/testのどちらかが存在する段階では、実JSONのexact2paths/3領域登録と実在ファイル捕捉を必須にする。片側file/領域だけの登録・部分集合は拒否する。ステップ2はsource/test不在のままJSON登録済みを要求し、ステップ3以後は両ファイル実在と登録済みを要求する。旧実在検査を外さず、候補不存在を偽造しない。

現在のO5 populationとstage_a_startupの追加層は実JSONに着地済みとして保持してから回転する。実baseの全paths/順序/guard_paths/領域集合を保持し、追加対象外領域は不変。削除/置換/並べ替え/未宣言追加/同一commitのJSON+基線定義変更を拒否する。登録済み後のsource/test各単独変更を合成PRの実CLIで検査し、必須人間確認欠落を拒否する。委任によるレビュー証跡の受理と、人間checkboxを自動で埋める行為を混同しない。

### 実装ステップ（コミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 追加層と登録前後のguard試験を先行宣言 | core_guard.py/既存guard試験だけ。現JSON・実部品0変更。旧層保持、段階条件、共変更拒否、後発単独変更捕捉、範囲外拒否が緑 |
| 2 | 宣言済みexact2pathsを別JSON commitで登録 | core JSONだけで計6行追加。宣言/試験/sourceは変更0。実JSONから全登録・全旧層不変を検査し、将来source/testの各単独変更を捕捉 |
| 3 | 初期付与部品/対象試験/限定検査・凍結候補/証拠を再構成 | 固定sourceの再利用と既存生成追随だけ。実source/test存在時の実JSON捕捉が必須。新ID受理前は履歴赤を未達として保持。sourceを含む固定commitまで作り、その実差分で新Draft PR番号を取得する。番号だけのdocs PRをmergeしない |
| 4 | 新実PRの単一7.7受理とpolicy対象1組、最終検査/レビュー | 実base26件・snapshot192件を保持。完全9資産/8外部を独立照合しrootが新ID/固定headを受理してから新row1件・必要snapshotだけ反映。policyは新PR/固定branchの1組だけ。全直接差分とデータ追加を非作者が確認し、合成merge上の実PR guard/履歴/archive/CIと対象版一致を確認 |

各件は`(ステップ 1/4)`〜`(ステップ 4/4)`で別commitとし、指定された1件だけ進める。ステップ2へ旧f48の試験変更を同居させず、旧0aaa/156/173のcommit自体をmerge/cherry-pickしない。rootが公開を指示する前にpush/PR作成をしない。実PR番号取得はステップ3のsource候補を含むDraftで行い、番号取得だけの別docs PRを統合しない。

### 新PR単一受理とpolicyの停止点

実baseは26件prefix（末尾#174）/snapshot192件。旧#173rowを新PRへコピーせず、実新IDに対するrow1件だけを新規に作る。実base/headを固定して9資産のbefore/after完全射影、8外部対象、snapshot参照/byte/hash、corpus入力digestを導出する。新PR番号や承認欄を仮値で正式台帳へ埋めない。policy追加とsource/test登録を含む実候補から全値を再照合し、旧9資産/8外部値との同一性を先に仮定しない。完全同一の値は旧の完全値照合/採否を証拠として再利用し、変わった値は根拠と差分を列挙して再提示する。rootが今回の新PR番号/対象head/履歴単位を別に明示して受理する。実baseが移動した場合も再導出し、旧受理を自動延長しない。

新snapshotの正式追加は新PR実値受理後だけ。192件を改変/削除せず、旧173の未参照10件や重複候補snapshotを持ち込まない。既存snapshotと同hashなら再追加しない。記録beforeと26prefixは固定し、27件目に相当する新ID1行以外を変更しない。baseが動けばcount/prefixを実際から取り直してrootへ提示する。

現core guardはHEADのpolicy.targetsで実PR番号/branchを照合し、base policyの有効状態を別確認する。既存仕組みを使い、番号確定後に`{pr: 新実番号, branch: feature/ur1-initial-rights-history-repair}`1組だけ追加する。旧targetsを削除せず、guard判定/権限根拠/失効/証跡厳密照合を変更しない。policyデータ自体の差分を最終非作者レビューへ渡す。委任証跡を固定HEAD/diffへ束縛し、未実施の人間checkboxを自動記入しない。

## 5. DoDと提供境界

旧履歴違反を輸入しない4段階のclean履歴で、初期付与候補のsource/test/限定凍結追随と新PR受理がレビュー可能になる。公開面/型/業務意味/性能を変えず、旧候補の拒否試験と既存source限定許可のexact-setを維持する。実PRのnormal merge条件を満たしたかは合成merge/最終CI/対象HEADの照合で判断し、ローカル内容成功だけで認定しない。

旧#173/#156は、新PRに必要な製品・試験・証拠・未完事項を公開handoffし、置換先を明記した後にだけrootがcloseする。元枝/保全物/旧受理記録は残す。本計画ではPRへの送信/closeを実行せず、最終公開ゲートはroot判断とする。

実DB行ロックを使う候補試験と、実製品Port/台帳/端末資格の提供を区別する。実Port・開始同一取引/運用D4/V12・実UI・共有DB・運用open・MVP完了は未提供のまま。新運用秘密/署名鍵を発行しない。

## 6. 検査

- 各ステップの変更path集合・親子commit・diff SHA、JSON不変/別登録を機械比較。既存`tests/test_core_guard.py`全件と新段階試験、実PR baseの旧全paths/guard_paths保持、候補単独変更の拒否を確認する。
- ステップ3: 既存`backend/tests/test_initial_recording_right_candidate.py`、限定生成/runtime/repository/tenant-context契約試験、root census既存＋追加、TB002のsource hash/exact47箇所と範囲外/欠落/改変/余剰/不正形式の負例。旧source/test hash一致と限定依存lock由来を記録する。DB試験は既存disposable fixture/実role/専用port/tmpのみ、共有DB/.envへ触れずcleanupする。実Port完成としない。
- ステップ3の履歴未受理による凍結/history/archive赤は具体的に残し、旧成功29919/2skip・backend中断・再導出版各結果を今回の成功へ流用しない。
- ステップ4: root/backend Ruff・ty、必要なbackend/root pytest（既存CIと同じ対象、失敗/skip/環境未達を明記）、認可catalog/function56保持、生成定数・census、9資産/8外部完全値、frozen history/archive/manifest、docs-status/plan sync、diff検査。実PR合成merge（第1親base、第2親最終head）でcore/PR_ACCEPTANCE/最終CIを確認する。通常feature HEADにeventを注入するだけで成功にしない。
- P6盲検・期待値・原封印を閲覧/再生成しない。8外部対象に含まれる既存seal試験は必要な固定byte/hash照合までとし、独立P6素材を証拠として読まない。署名/秘密をログへ出さない。検査結果・対象SHA・留保をresearchへ残し、独立非作者レビューへ渡す。

### 計画承認

2026-10-23T17:06:05.579506+00:00、Codex主担当/rootはPO委任4/5/6/8/9/10に基づきplan b815154815885f5ad0d6ef9a59871f5217560da5250819902ab087c430a587eb / researchb6aef4d58bce2cd62bc25a574714c76d5893f7674ca90248e744e24dae85f66bを承認。非作者/root/o5_final_reviewの第1回全文計画レビューは可決0/0/0、固定供給6filesの旧0aaa blob一致・実base26/192/56関数と段階分離を確認。元U-R1計画7回/旧全レビューと後発historyP1を保持する。実装はrootが個別指示する1stepずつ、新PR番号/新headの7.7受理とpolicy限定データ追加自体も別の非作者確認を要する。人間逐行確認/署名を代記せず、拒否条件/旧history/ブランチを書き換えない。
