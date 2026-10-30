---
feature: mvp-delegated-core-review
status: in-review
承認: 済(2026-10-23・PO委任によるCodex判断)
重さ分類: コア領域
worktree: ../../..
notion: https://chatgpt.com/space/page_711a9b1ac7d88191a6b0bc313a60db01
branch: feature/mvp-delegated-core-review
created: 2026-10-23
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画: 初回MVPに限定したPO委任確認

## 1. 背景・目的

POの2026-10-23 /goal第4・5・10節は今回MVPの最終差分確認と通常統合をCodex主担当へ委任し、現行core-guardが人間確認のみの場合の最小例外整備を明示許可した。人間確認の自動チェックや本人署名の代行を避け、独立レビュー証拠と最終版を検査する。NFR-019の検査経路を維持する。

## 2. スコープ

今回MVPだけのrepo+PR番号+headブランチの完全一致対応表へ限定。既存検出パス・拒否条件・通常人間確認経路は保持する。委任資料が存在する場合は不正資料を人間チェックで迂回させない。実装はscripts/core_guard.py内に限定（新helperへの検査漏れを避ける）、tests/test_core_guard.py、既存CIを変更しない公開GitHub APIへの無認証GET、PR templateとpr skillの委任分岐、根拠を収める本feature/policy.jsonと、その検査経路登録用の.claude/core-areas.json。署名鍵/秘密新規発行・意味仕様・7.7基準・共有DB・運用公開は対象外。

## 3. 影響する正本

`docs/development/dev-harness-design-2026-08-07.md`6.3/10.1、`docs/development/github-setup.md`2章、`docs/README.md`へ今回限定例外の参照を反映（既存体制全体は再設計しない）。POの明示指示の追随節更新として7.6-3前段のPRレビューで処理する。既存正本の版番号・別件in-review v1.20は動かさない。6.3一般規則は書換えず、今回MVP/PO委任日/対象対応表/失効条件への限定注記を置くだけとする。独立レビューでこのゲート解釈も確認する。

正本外の対象: 本feature文書、core_guard.py、test_core_guard.py、.github/pull_request_template.md、.claude/skills/pr/SKILL.md。

## 4. 実装方針

コア/検査経路変更。人間確認の文言・検出基線は維持し、PR本文に独立した `PO-DELEGATION-EVIDENCE: <同一PRのissuecomment URL>` を置いた場合だけ追加経路を使う。証拠は最終commit後に外部コメントとして固定し、コミット内自己参照循環を避ける。

policy.jsonに今回のPO指示の原文抜粋・日時・この会話を根拠とする旨・対象repo/PR番号/headブランチのexact対応表・有効状態・証拠掲載GitHub主体を明記。候補HEADのcommitted blobを読む。撤回/MVP終了後はenabled=falseで拒否。新PRへの対象追加はレビュー対象差分とする。通常マージ直前に主担当も撤回の有無を確認する。

証拠は固定公開GitHub APIへ、既定TLS・無認証・timeout・redirect拒否・1MiB上限付きGETで取得する。同一PRへのOWNER/MEMBER/COLLABORATORコメント・policyの掲載主体・マーカー直後の重複キーなしJSONであることを検査。本文marker複数/不正URL/API失敗は拒否。構造はauthority_sha256、pr、base、head、diff_sha256、paths、reviewer_agent、candidate_agents、independent、verdict、findings、report。base/headはイベントと完全一致、diff/pathsはgit diff --no-ext-diff --binary --no-renames base...headから再計算。authority_sha256はpolicy blobと一致。対象PR番号/branch/repo・純正40桁SHA・独立したagent識別（candidate_agentsにreviewerがいない）・independent=true・可決・未解消P0/P1ゼロ・非空の具体レビュー報告を必須とする。著者の『承認済み』だけでは通らない。認証値をログ出力しない。

機械保証の限界: 会話のPO本人性、レビューの意味的正しさ・実際の曝露履歴や、列挙されたagent情報の真実性は暗号認証しない。実際の独立taskに最終差分を渡して得た結果だけを掲載し、その出典を報告に記す。既存人間チェックも自己申告であるが、新経路は版・差分・証拠所在・重大未解消を構造検査する。人間が逐行確認/署名したとは表示しない。P6 blind/本人暗号署名の代替には使わない。

policy.jsonは新しい検査経路であるため、ステップ1で必須パス宣言と登録前後両方に対応する検査・試験を置き、ステップ2で.claude/core-areas.jsonのguard_paths末尾へ完全一致1件を登録する。検査器はpolicyが未登録でも当該パス変更を検出する固定下限を持つ（JSON登録の削除による迂回を許さない）。area pathsの既存層/共変更拒否は維持し、JSONとcore_guard/testを別コミットにする。policyだけ変更したPRも証拠欠落を拒否する。

### 実装ステップ（コミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 委任検査と拒否試験、policyパス宣言、既存CI経路での無認証照合、文書/テンプレート整合（JSON未変更） | Git実差分+模擬GitHub応答で正常経路/各欠落/版不一致/自己レビュー/未解消重大/API失敗/不正URLを検証。既存core guard試験維持。root Ruff/ty/pytest成功。独立レビュー後、実最終HEADの証拠コメントを掲載してCI評価 |
| 2 | policyパスをguard_pathsへ登録 | 宣言親コミットが先行し、JSON末尾1件のみ追加。policy単独変更の未確認拒否、全既存登録不変、基線検査/対象pytest成功 |

## 5. DoD

- [ ] 独立計画レビュー/PO委任判断を対象SHA付きで記録。
- [ ] 明示対象だけを扱い、対象外・証拠欠落・版不一致・重大未解消を拒否する。
- [ ] 検出パス・既存人間経路・認可を弱めず、人間チェックを自動ONにしない。
- [ ] 最終差分の独立レビューと実CIが成立してから通常merge。#176等後続PRも最終HEADごとに証拠を固定。
- [ ] PO本人の暗号署名/P6資格留保の代替としない。

## 6. テスト計画

既存core guard単体/合成Git履歴に委任API応答注入を追加。実API失敗はfail-closed。テストは本物の秘密を使わない。対象pytest/Ruff/ty→意味のある区切りでroot全件。CIの全必須結果を回収し、失敗を成功へ読み替えない。

## 計画レビュー採否

第1回全文レビュー: `/root/product_connection`、SHA256 `aefa9cf7559c7c085c342c915898a5312074618ee2beca4fae3922c88736f5ad`、否決P0=0/P1=2/P2=1。全件採用。PR番号のexact対応を必須化、policy自体の検査経路としての宣言・別JSON登録と欠落拒否を追加、正本は今回委任参照注記に限定。

第2回反映差分・影響節: `/root/product_connection`、対象11b07fd1、plan SHA256 `735094855097a2ab617b89799bca4883f2ac257d6f42c3f8df705a2d193b1478`、可決 P0=0/P1=0/P2=0。

PO委任によるCodex判断: 2026-10-23T11:49:01.269922+00:00、Codex主担当 `/root`。上記対象版を2026-10-23 PO指示4/5/10の限定例外整備許可に基づき承認する。6.3一般体制を変更せず、本人逐行確認/署名を代記しない。対象PRは#177およびpolicyの明示対応表に限る。

## 実装・検証記録

ステップ1 `64c9eec7`はcore-areas JSON未変更。ステップ2はpolicy完全一致1パスの末尾登録だけ。両版の対象試験はそれぞれ336件成功（最終45.50秒/exit0）。Ruff/ty全体、文書20件0違反、diff-check成功。失効したbase policyを古い有効headで復活させる要求も拒否する。base policy欠落のbootstrapは#177専用branchだけ。実GitHub証拠照合/最終CI/独立実装レビューはこれから実施する。

ハーネス評価台帳への追記なし。本件はPOの期間限定MVP委任への明示対応で、恒久的統制の評価/再設計は行わない。実際の独立レビューtaskの報告だけをGitHub証拠コメントに掲載し、作成者の自己判定で代用しない。

本段階で通常マージ許可を成立扱いにしない。独立レビュー後に最終HEAD/実diff/authority hashへ結び付けたコメントを掲載し、CIの全必須結果を回収して判断する。根拠は2026-10-23 PO委任、判断者はCodex主担当。山田正輝の個別確認・署名とは扱わない。


## ステップ1の差戻し修正（2026-10-23）

初回CI run39950625656のtenant-boundary-bypassは、GH_TOKEN設定のためのci.yml変更が
既存8資産の外部凍結観測を動かし、履歴追記0件で拒否された。既存レビュー回数は維持する。
PO委任によるCodex主担当判断で、ステップ1範囲の取得実装を公開APIへの無認証GETへ変更し、
ci.ymlを実PR基線1ab398ccとバイト同一へ復元する。正式資産・revision・履歴・snapshotは変更しない。
非公開化・rate limit・HTTP/ネット/TLS/JSON異常はfail-closedとし、保証を緩めない。
後発差分は新固定HEADへの第2回差分レビュー対象とする。旧HEADの証拠は履歴として残し、
新HEADの確認に流用しない。初回失敗と根拠はresearch.mdに記録する。

### CI起因の取得方法是正（ステップ1範囲の差戻し）

CI run39950625656のtenant-boundary-bypassは、認証用CI2行が既存8資産の外部凍結対象を動かし未受理だったため失敗。失敗を保持する。公開APIを無認証・固定URL・既定TLS・redirect拒否・サイズ上限・取得不能拒否で読む方式へ是正し、CIを基線とバイト同一へ復元するPO委任判断で、新たな7.7基準更新を作らない。

修正実装開始時のactive遷移が後追いとなったため、コードコミット前にこのメタデータ遷移を記録する。未レビューの変更を旧固定HEADの確認済みと扱わない。意味仕様・既存拒否能力の緩和なし、最終新HEADの第2回差分レビューと証拠再固定を行う。

最終是正版: core350 passed/20.89s、Ruff/ty全体、文書20件0違反、diff-check成功。実無認証API取得成功。正式資産9件と全外部対象は基線とバイト一致、movement=False/affected=[]、作業木を対象とするchecker違反0。コミット後の正式PRイベントでも再検証し、旧d5d85134証拠は新HEADでは拒否する。

### PR188の限定対象追加（2026-10-30、PO委任によるCodex主担当判断）

既採用の対象表方式を維持し、policy.jsonへ実PR188/feature/mvp-game-start-atomic-candidateの完全一致1組だけ追加する。POのMVP継続委任に基づく対象具体化であり、source d1aa2422の既非作者review/正式記録と公開版を一致させた後に行う。core検出/拒否条件/本人確認欄を変更しない。最終commit後の外部証拠は実base/head/diff/path/独立結果を固定し、証拠不在/版違い/重大未解消は従来どおり拒否する。対象追加自体を非作者確認してから保存し、最終CI/通常mergeは別条件とする。本人署名/逐行確認ではない。

対象追加の保存判断: PO委任によるCodex主担当判断（2026-10-30）。packet a3863731bd5bb4de6b57719900df9f8c3c112b6c0893ddd1923c0e9766a81501と実2path、独立REPORT c993e36f8dea09804a17d50aa52cd5f9ba02c8dff978ec52a6da4590760b877c（P0/P1=0、関連coreguard81成功）を照合してPR188対象1組の追加を採用。coordinate_gate_reviewは同patch起案者のため当該policyの確認を作者整合として区別し、独立採否には使わない。最終全差分レビュー/evidence/CI/通常mergeは残る。
