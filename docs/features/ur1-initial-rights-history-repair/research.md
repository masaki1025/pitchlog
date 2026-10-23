# U-R1初期付与の履歴修復: 限定調査

2026-10-24、rootのPO委任判断により新branch/worktreeを作成した。作成前に同名branch/path不存在を確認し、実develop `31194a39c9083bbef6c14bde19c24a3e49d09f2e` を起点にした。主repoのローカルdevelopは別固定点だったため、その可変HEADを起点にしていない。`origin/develop`は確認時31194a39だった。旧0aaaは短縮OIDがtreeと衝突するため、commit `0aaa22e09d7e1a0301d03f7c63d188d9bba76844` と確定した。

- worktree: `/home/ymdms/projects/pitchlog-worktrees/feature-ur1-initial-rights-history-repair`
- branch: `feature/ur1-initial-rights-history-repair`
- 編集はこのplan/researchだけ。merge/cherry-pick/source/凍結資産/旧枝編集、DB/テスト起動、push/PR/closeはしていない。

## 拒否された履歴と分離

旧 `f48b5944fd94777bd132cd12a2da8e4727cfee8d` は`.claude/core-areas.json`と`tests/test_core_guard.py`を同時に変更する。実base31194の`BASELINE_DEFINITION_PATHS`はcore_guard.pyとtest_core_guard.pyを含み、現`verify_area_path_baseline`はこの共変更を拒否する。rootの独立履歴監査では旧173の違反はこの1件のみ、175/API/UI/browser/組立f5は違反0との通知を受領した。局所テスト成功で歴史上の共変更拒否が消えるとは扱わない。

新4表は宣言＋試験、別JSON登録、初期付与source/試験/限定候補、実番号に対する新row/policy/最終検査を分ける。旧f48のcommitやJSON+試験同居作法を再利用しない。旧173/156全枝、0aaa/旧保全物/受理記録を保持し、新PRへの公開handoff後にだけrootが旧PRをcloseする。旧docs番号取得PRを再びmergeする案は採らない。

## coreの実観測と提案

実baseではinitial_grant.pyもtest_initial_recording_right_candidate.pyもcoreのどの領域にも捕捉されていない。旧0aaaのJSON登録はsource1pathをsync-protocol/recording-rights/tenant-isolationの3領域へ追加している。新計画では実行試験の単独変更を取り逃さないよう、source/test exact2pathsを同じ3領域へ順序付きで追加する（計6追記）。rootはこの対象強化を計画レビューに含める方向を受領。既存path/順序/guard_paths/拒否の縮小はしない。

stage1では現JSON全byte不変・source/test不存在を確認し、合成状態で登録前/後を検証する。実sourceまたはtestが存在すれば、実JSONで2paths/3領域登録が必須。stage2はJSON登録済み/部品未作成、stage3は登録済み/両実ファイル実在・捕捉を要求する。存在する製品に対する未登録を「候補未作成」の理由で通さない。既存層の実在検査と、後発source/test各単独変更の実CLI人間確認拒否を保持する。

現在の追加層（O5 populationとstage_a_startup）は実JSONに着地済みのまま保持して回転する。旧tests修正をJSON commitへ持ち込まない。initの旧byteは日本語docstring1行だけで業務計算を持たず、広いrecording_rights globは追加しない。

## 必要なsourceと固定供給点

旧差分をcommitごと取り込まず、下表の内容と現在baseとの差分を対象path単位で再構成する。型/アルゴリズム/性能の変更はしない。生成定数3filesは実凍結候補から既存方式で作り、旧値を先に正と決めない。旧lockの無関係な差分をコピーせず、必要な通常依存cryptography==50.0.1由来だけを導入する。

供給commitはすべて `0aaa22e09d7e1a0301d03f7c63d188d9bba76844`。

| path | blob | file SHA256 |
| --- | --- | --- |
| backend/src/pitchlog/recording_rights/__init__.py | db4764637dfd0e2858a22d6cacf00bcfaee4f0cb | c924a9de3dd158bcb86f91791690cd67188614a40b0385a8946b988e723a0612 |
| backend/src/pitchlog/recording_rights/initial_grant.py | faddc7402cc1ba8d76ebcd020ad8d7b77d92991d | c20d596ba80a7c9e792a472ddde295a261b0dee2977627e7f0391765bdca59c3 |
| backend/tests/test_initial_recording_right_candidate.py | 5e21ab6b3326d38b4dffd654e98b4fc0384b5c81 | 3f1009973bd890ce3ac6507117ec2227555d57ec4c7e8f4c9a009902acec8cdc |
| scripts/check_tenant_boundary_bypass.py | 2f4117a06713495d3b8d24e617015ab6278b4c56 | 3b7b90f8476b30c0596439b33ce75db1c23c6c930b359e03804f00df280e0e7e |
| tests/test_census_baseline_check.py | de2ca054c5b34b82ca69f08841f34a4cb82ee017 | ae5e4d9e4ed0145374acd8036ca13410785f6890fb4e29a0ac93a6b8d0078f01 |
| tests/fixtures/tenant_boundary/census-scoped-digests.json | efed6bf6db3123eebce2114beaee359b54a3e6b3 | 0053c7ff7f60f2696accffd2df9755a2ba531afc5bda7f7969d6e7d091e6f76a |

旧検査差分はTB002の初期付与1file/source hash/exact47箇所だけを限定登録し、hash不一致や範囲外を除外しない。censusの旧43checker入力→独立AST18入力はfixtureの2digestでexact拘束し、欠損/改変/余剰/形式不正の拒否を維持する。これらの意味の再設計や汎用許可は行わない。

## base26件/192snapshotと新実ID

実baseの権威履歴は26件、末尾`masaki1025/pitchlog#174`、正式history-snapshotsは192files。旧0aaaの27件中prefix26件は実baseと完全同一である。新候補はこの26prefixを保持し、旧#173の27件目をコピーしない。旧未参照snapshot/重複proposalを新正式archiveへ持ち込まない。必要snapshotは新PR実値受理後、実参照されbaseにないものだけを追加する。

9資産はplanに列挙したtenant_boundaryの9files。外部8対象は既存方式の `.github/workflows/ci.yml`、`scripts/check_tenant_boundary_bypass.py`、`scripts/frozen_archive.py`、`scripts/frozen_history.py`、`tests/domain/test_boot_seal.py`、`tests/test_census_baseline_check.py`、`tests/test_ci_wiring.py`、`tests/test_plan_generation.py`。変更不要の外部は固定byte/hash照合だけであり、新しい編集権限ではない。独立P6素材/封印の内容は読まない。

policy targets追加と新test core登録を含む**実候補**から9資産/8外部を再照合する。旧値との同一性を先に仮定せず、変わった値は理由/根拠を列挙し、同じ値だけ旧の完全値照合を再利用する。新PR番号/固定head/単一履歴単位はrootが別に受理する。受理前の履歴赤を保持し、承認者/新番号の仮値を正式台帳へ埋めない。新PR取得はsourceを含むstage3固定commitのDraftで行う。

## 旧証拠を重複コピーしない参照

以下は旧固定commit上の証拠として保持する。新PRの新ID/head受理そのものには使わない。

- [親9表・承認/レビュー7回と新5境界](https://github.com/masaki1025/pitchlog/blob/0aaa22e09d7e1a0301d03f7c63d188d9bba76844/docs/features/ur1-recording-rights/plan.md)
- [旧新5提出状態の写し](https://github.com/masaki1025/pitchlog/blob/0aaa22e09d7e1a0301d03f7c63d188d9bba76844/docs/features/ur1-initial-rights-followup/plan.md)
- [旧#173の実#174後9資産/8外部候補](https://github.com/masaki1025/pitchlog/blob/0aaa22e09d7e1a0301d03f7c63d188d9bba76844/docs/features/ur1-recording-rights/step5-pr173-post174-7.7-acceptance-brief.md)
- [旧完全payload案](https://github.com/masaki1025/pitchlog/blob/0aaa22e09d7e1a0301d03f7c63d188d9bba76844/docs/features/ur1-recording-rights/step5-pr173-post174-7.7-payload-proposal.json)、[旧record案](https://github.com/masaki1025/pitchlog/blob/0aaa22e09d7e1a0301d03f7c63d188d9bba76844/docs/features/ur1-recording-rights/step5-pr173-post174-7.7-record-proposal.json)、同固定点の`step5-pr173-post174-candidate-snapshots/`とderivation.json。
- [旧引継ぎ・枝/保全物/未実装境界](https://github.com/masaki1025/pitchlog/blob/0aaa22e09d7e1a0301d03f7c63d188d9bba76844/docs/features/ur1-recording-rights/step5-pr173-tab-handoff-2026-10-23.md)、同固定点の`step5-followup-handoff.md`、`docs/worklog/2026-10-22-ur1-pr173-review.md`、`docs/worklog/2026-10-24-ur1-pr173-post174-rederive.md`。

旧source/test/proposal/文書/保全物に存在するP1→修正0、metadata0、旧2系列レビュー、旧29919成功/2skipやbackend未完走を保持する。新4ステップで親新5/9全条件・実Port/実DB接合/MVP完成を認定しない。rootによる旧PR公開handoff/closeはsourceと残件が新PRで公開されてからの別実行とする。

## policyと次の判断

実baseの`docs/features/mvp-delegated-core-review/policy.json`は有効で、旧173を含む6targetsを持つ。`core_guard._load_delegation_policy`は最終HEADのtargetsを読み、`_verify_delegation_base_policy`はbase有効性を別確認する。したがって新番号確定後の新PR/固定branch1組追加は現機構で可能だが、data差分自体も非作者レビューへ渡す。既存targets/根拠/失効/厳格照合を変更せず、guardに迂回口を作らず、人間checkbox自動記入もしない。

起案段階では製品/検査/正式資産を編集していない。独立計画レビュー・root判断後の個別step指示を待つ。実台帳/端末資格/鍵管理/実RecordingRightsPort/開始同一transactionと共有DB・運用openは未提供のまま残す。

独立全文計画第1回: /root/o5_final_review、plan b8151548/researchb6aef4d5、可決0/0/0。rootはplan末尾の対象版/日時/PO委任根拠で4段階の限定履歴修復を承認。旧173/156/0aaa/後発履歴拒否とMVP未完条件は保持。

## 承認ステップ1/4の実装

独立非作者o5の第1回全文計画レビュー0/0/0を受け、rootがPO委任承認を`15d5d7ee059330611ce60924863911256c44c04e`へ記録した。今回はこの基線からステップ1だけを実装した。編集はscripts/core_guard.pyの追加層宣言、既存tests/test_core_guard.py、このresearch。plan/実core JSON/初期付与source/test/凍結/依存/他worktreeは変更していない。旧0aaaやf48commitのmerge/cherry-pickも行っていない。

追加層はinitial_grant.pyとtest_initial_recording_right_candidate.pyのexact2pathsを、sync-protocol/recording-rights/tenant-isolationに同順で宣言。旧O5 population/stage_a_startup層はPRE_INITIAL_RIGHTS_PATH_ADDITIONSとして既存登録・旧段階の検査へ保持した。過去の登録試験は当時の追加層を明示して検査し、現在宣言との混同を避ける。旧全登録/順序/実在と拒否試験を削除していない。製品guardの全関数・classは承認基線とAST同一で、BASELINE_DEFINITION_PATHS・共変更拒否・委任処理・required human checkの判定変更は0。

新段階試験は登録前＋両file不在、登録済み＋両file不在、登録済み＋両file実在を受理。sourceだけ/testだけの実在、両実在なのに未登録、領域の片側/部分/対象外登録、順序反転/重複、旧削除/置換/未宣言追加を拒否する。実stage1のJSONとsource/test有無も同じ条件で照合し、将来sourceが存在する段階の未登録を無条件で許可しない。合成repoで実JSONから宣言→別JSONcommitを実CLI検証し、登録後の2files各単独変更は未記入human check拒否/チェック済み受理を確認する。合成tmpだけに部品と同名pathを作り、実wtに部品を作成していない。

### 検査結果と途中版

初回core全件379成功/21.20秒。その後、登録済みでも片側fileだけが実在する2負例を補った。初回対象Ruffでは新試験の行長/一行分岐25件を検出し、手動改行で是正した（root ruff formatは未実行）。型検査を省略して成功にはせず、是正後にroot全体Ruff/tyを再実行してともにexit0。

最終版の`uv run pytest tests/test_core_guard.py -n 4 -q`は**381 passed / 23.32秒**、失敗/skip/timeout0。root Ruff/ty、docs-status（21 documents/0 violations）、plan sync、git diff --check成功。実core JSONは承認基線とbyte完全一致、SHA256 `5dc107bb5ee2f7ee9b0faab55eb1c22b5751619f2df0c14cd4c505c6e874ab0e`。実initial_grant.py/test_initial_recording_right_candidate.pyは双方不在である。

実Git履歴predicateも変更せず確認した。旧f48はchanged definitions=[tests/test_core_guard.py]、親にAREA_PATH_ADDITIONS定義あり、JSON同時変更により違反true。今回の承認基線15d5では違反false。実base31194→承認基線に対するverify_area_path_baselineは31194を返し受理。step1commit後も同predicate/基線を再確認し、結果とHEAD/diffを引渡しに固定する。旧実PR拒否を内容成功で隠さない。

固定source SHA256:

- core_guard.py: `e8a5404133c1f9a0875ebaa27a13349346b4e882b4df7315eb3d98cfae1afff0`
- test_core_guard.py: `e508b79a38044e7a293dd0956e86cf6161e4935e45e8cad4ecf7f297e62b8435`
- 承認15d5からこの2pathsのfull-index binary差分: `53bf82b9724354eeed61088e4ba3b79449bcd16bc28dcf297131720f746133c5`

ステップ2JSON登録/ステップ3部品は未着手。DB/実Port/MVP完成・新PR/7.7受理・policy対象追加・push/公開/旧PRcloseへ進んでいない。P6/秘密を読まず、新運用鍵/秘密を発行していない。旧レビュー系列と親9ステップの未完条件を維持し、step1の独立コード確認へ引き渡す。
