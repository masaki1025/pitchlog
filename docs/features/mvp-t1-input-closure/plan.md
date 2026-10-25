---
feature: mvp-t1-input-closure
status: active
承認: 済（2026-10-25・PO委任によるCodex判断）
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3f893b75e68781e5a55ce961b18fab3f
branch: feature/mvp-t1-input-closure
created: 2026-10-25
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# T1入力閉鎖の有限実行手順

## 1. 背景・目的

[TSK544](https://app.notion.com/p/3f893b75e68781e5a55ce961b18fab3f)の承認済みT1計画7d6ce544のステップ1内で、G6-S02の入力相関を先行供給する。[要件正本](../../requirements/requirements-pitchlog-2026-07-22.md)FR-003/FR-009、NFR-018/019を根拠とする。T1を実行する唯一の上位計画と既10計画反映/2確定ゲート周を保持し、本書で本体開始条件や既意味を変更しない。正式起点はdevelop dcd4fda8（PR183統合済み）。

## 2. スコープ

型検査と指定inning/現在inningの一致が必要であること、不一致時の状態変更0を、既正式payload/状態型へ束縛する。次の4pathだけが最初の実装対象である。

- contracts/state-transition/t1_g6_s02_input_schema_v1.json
- contracts/state-transition/t1_g6_s02_inputs_v1.json
- contracts/state-transition/t1_g6_s02_author_cases_v1.json
- tests/test_state_transition_contract_schema.py

3JSONは既候補の全byteを再利用し、author_casesのcandidate_only=trueを保持する。これは作者の必要条件ケースでありP6封印/独立期待値や完全S02の正式受理を表明しない。既operationRows3payload/既positive2件と完全一致を検査する。回不一致でmust-not-applyをother-preconditionsへ弱める変異を拒否する。一致だけでappliedへ昇格しない。

公開結果ID/D5、他G6、13不足分岐、7marker、23flag、製品T1計算/別計算器、Port/DB/HTTPは本単位で供給しない。未掲載単打配置へのD07拡張や観測推定、既D06拒否順変更も行わない。後続P8ケースは別の有限範囲確認後に扱う。正式共有資産とGitの唯一writerはroot、候補作者と独立レビュー担当は分離する。

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| requirements/design/ADR/development/ops | 反映なし。既意味の必要条件を収録するのみ | 既原典との一致をPRレビュー |

本plan/researchと宣言済み契約/試験を編集対象とする。通常提供に必要な当該PRだけの既PO委任policy target登録もrootが最小追記する。旧本人署名・carry範囲の変更や検査拒否緩和は含めず、必要な継承手続きは別有限確認と独立レビューを要する。共有識別値/派生値への実影響が判明した場合だけ完全前後値を固定し、既7.7でrootが受理する。未影響値の再承認は求めない。

## 4. 実装方針

状況計算の入力契約に触れるコア領域である。既core-areasのcontracts/state-transition/*と既schema試験捕捉を実確認し、core拒否条件は変更しない。候補はcache t1-g6-s02-current-candidate-20261025、author handoff ef5ec43245aede032d4b0f4c8543194cbaf07007b10e7c8cd0175e98b19c4019、非作者evidence59ec3f7ffbb28fd0280f6cd091bc52a2c912a46f5cca30da9b62455504c72b07。候補への非作者確認と本有限計画への確認を区別する。旧268試験定義を保持し、親/PR183のレビュー履歴をリセットしない。

### 実装ステップ(コミット単位)

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 固定4pathの有限型/相関ケースを収録 | 前後SHA一致、既型/参照一致、20局所検査/義務弱化・適用昇格等の変異拒否、旧試験保持、Ruff/ty成功 |
| 2 | 実影響値・最終差分・必須CIを確認し通常提供 | 影響する場合だけ既7.7、最終HEADの非作者確認/PO委任証拠/必須CI。完全S02やT1本体の成立とは別記 |

本書のPO委任承認後にrootが指定ステップだけを実施する。署名/本人逐行確認/P6資格は代記しない。人間の再承認待ちを設けず、技術受理は実対象版/根拠/日時を記録する。

## 5. DoD

- 指定4pathが正式branchで再現でき、型/相関と現規範参照が検査される。
- 不一致ではpre_state_after全値不変を必須にし、必要条件一致だけの成功昇格を拒否する。
- candidate_onlyと公開結果/D5未供給を保持する。親S02全閉鎖/P8不足13/P7/P6/本体/MVP完成を主張しない。
- 最終差分/必要正式値/必須CI/通常統合までの証拠を対応付ける。TSK544全DoDは親計画のまま未達範囲を保持する。

## 6. テスト計画

NFR-019の単体/一致性として既schema試験へ追加し、extra/型/回不一致/状態改変/弱化/成功昇格/既参照ずれを拒否する。候補独立20成功/167変異拒否は当該候補の証拠であり、正式反映後にも対象検査を行う。統合候補固定後に必須全件CIを実施、実DB/実機試験は本入力準備単位の成果として数えない。P6封印/期待値本文を開かず、新blind導出とも呼ばない。

## 有限手順の承認記録

2026-10-25T11:45:57.153332+00:00、Codex主担当/rootはPO委任4/5/8/10に基づき対象dcd4fda8/plan486bbc3823b4bba0201fdbb58a21ecc30c75d896e6d6d5c7ea7761557d2efe58/research b699a98b7bb62680a4bad82b33d8b67800bdfa6411be9268a8012444d1f69a44を承認。非作者creation_pathの限定計画確認は可決0/0/0、evidence72b93e7e5491271816874ea0ca9b18481cda46f0b324a8552d58c9b4fde06bff。指摘反映0周。既候補の独立source確認とは別の計画確認1回で、親544/183の実績をリセットしない。まずステップ1の4pathだけ実施する。本人署名/逐行確認/P6新blind/完全S02/T1本体開始を成立扱いにしない。

## 次の有限範囲：RBI03/04と正常false境界

親544ステップ1内の次の候補はRBI03/04の4観測組合せと、その正常counterbranchである既RBI08の1ケース。原典A-3の先頭一致順、既D07二死二三塁単打の限定、明示OUT3-04/無失策を保持する。新しい意味を追加せず、停止後のミスプレイ観測因果bool=falseを、負例や到達不可扱いではなく正常RBI08へ結ぶ。既RBI08代表は置換せず追加ケースを閉た形で扱う。

対象候補はcache t1-p8-remaining13-candidate-20261025/false-boundary-candidate、handoff707c5661b54819848a80cd071bfbca017b76f5eb2846b3410da4cf944306650b、11path結合patch6983efafaf24c21020a40b5a232d60c9ae9bd0beb06840f83cdc585f827f9170。編集対象は次だけ（既S02の4pathを取り消さず、schema試験の両追加を同時保持する）。

- contracts/state-transition/branch_row_mapping_schema_v1.json
- contracts/state-transition/branch_row_mapping_v1.json
- contracts/state-transition/input_axes_descriptor_v1.json
- contracts/state-transition/manual_fixture_branch_coverage_v1.json
- contracts/state-transition/state_transition_contract_v1.json
- contracts/state-transition/state_transition_manual_fixture_schema_v1.json
- contracts/state-transition/state_transition_manual_fixtures_v1.json
- contracts/state-transition/t1_observation_binding_rules_v1.json
- contracts/state-transition/t1_out3_input_schema_v1.json
- scripts/check_branch_row_mapping.py
- tests/test_state_transition_contract_schema.py

ステップ1の別有限追補として候補を接合し、ステップ2で必要正式値を完全導出/独立照合/PO委任受理する。表の2ステップ番号や親レビュー周回は変更しない。既44row/111case全object/全操作・取消/required21/旧bindings/履歴を保持し、5row/5caseだけ追加する。追加fixture/mappingの形式は任意ケースを許可する抜穴にせず、実source case/row/branch/6効果・正逆exact対応と未知/欠落/重複/改変を検査する。

新入力bool葉のfalse/true正常coverageをproduction consumerで実測し、falsecase欠落/打点変異が拒否されることを必須にする。T2全4656 identity/順序不変も実consumerで確認する。候補415成功/6失敗の6件は未受理凍結識別値であり、greenとは扱わない。新独立導出は純入力/primary規範だけを別forkへ渡しseal先行後比較するが、全P6/完全資格・完全6wire・本体開始への拡張はしない。

この範囲の新候補source/追加形式の非作者確認とroot承認後だけ接合する。正式schema/fixture/descriptor等の識別値/履歴、旧Gate6署名範囲の継承、共有参照の採用はrootが別の必要最小範囲を固定し、既署名/日付を変更せず、現PR対象/全値/最終版の独立証拠を追跡する。未受理値のまま提供完了としない。製品計算/実Port稼働をこの契約整備の前提へ追加しない。

2026-10-25T13:02:42.072685+00:00、rootはPO委任によるCodex判断でRBI03/04＋正常false境界の11path有限範囲を承認。対象plan前SHA256 87109616d37e85cf5fc0a200893b6c3c33585ffc07e13d1f73cf974e2f90eb09、非作者review66fe7a3903619297e9f4b42db6408fd6704354d2665394fc00c10b58f1918471は可決0/0/0。415成功/6未受理凍結失敗と、旧111/44/T24656同値を照合した。これは計画/source候補の有限受領であり、正式7.7値・完全P6/資格・最終CI・T1本体許可ではない。rootは隔離接合でS02全20追加を保持し、正当に増えた5row/5caseのexact件数49/116への検査追随だけを別確認する。正式branch反映は必要な全前後値/識別値/継承受理が閉じた版で行う。

2026-10-25T13:12:36.838715+00:00、rootはPO委任によるCodex判断で、実装済みS02の3契約JSON/試験sourceを含む進行中候補のDraft公開だけを先行する。7.7の履歴値に実PR番号が必要なため、番号未取得の仮受理を正式値として投入しない。通常/prの最終クローズ・全件品質完了は未了と明記し、status active/人間確認未チェックを保持する。これは文書だけの完了PRでもマージ許可でもない。最終候補で既必須CI/独立最終HEAD確認/全値/委任検査を完了する。ハーネス評価台帳への追記なし（今回の限定接合作業だけでは新しい一般傾向を確定できない）。

## Gate6の今回限定append受理手続き

rootはPO委任に基づき、既PR183 carry/schema/旧本人署名・sheetを不変に保ち、新PR185のRBI5行5case appendとdescriptor digest置換だけを受ける別記録を追加する。対象4pathはscripts/check_human_review_signature.py、tests/test_human_review_signature.py、contracts/state-transition/gate6_t1_input_append_schema_v1.json、contracts/state-transition/gate6_t1_input_append_v1.json。既7.7の全値・前後関係は引き続き必要で、旧受理を新本人確認へ拡張しない。

設計base c9adce0f、design SHA ba58ff3edc534ed264936292eb0ff3d6928d4dd24fa8ccaf9c96f4727857baf2、非作者有限設計review ee5893d7a4dcebf42b4611069d3cff4054edc187f5e9a7de24d6df075debcfb3は指摘0。具体化は共有純検査bodyと固定anchor専用private readerを使う。公開rev切替/monkeypatch/旧コード動的実行/一時Git checkoutを採用しない。旧anchor祖先性/全署名byte/旧carry exact/旧対象digestを検査した上で、今回差分は許可位置のexact再構成で現対象全digestへ束縛する。既operation/undo/T2射影不変を保持する。

今回新受理は実PR185/branch/base/head/既core_guard委任証拠へ束縛。後続PRはbaseとの全対象不変のみ継承する。欠落・失効・他PR・版不一致・重大指摘未解消・任意の承認文字列・旧行改変・未知/重複/不足case・余剰field・checkout不一致を拒否する試験を追加する。技術検査だけを最終委任/P6/P7/本体開始成立にしない。source候補をcacheで作り、非作者最終source確認後だけrootが正式反映する。PR184の既helper作者による同sourceの独立採否は不可とし、役割履歴を保持する。

2026-10-25T13:17:19.949623+00:00、判断者Codex rootは上記限定4path/設計具体化をPO委任により承認。新記録の最終受理値は未確定であり今回の計画承認とは別。

## 既GAP登録への追加行の双方向接続

2026-10-25T13:40:25.814655+00:00、rootはPO委任により、RBI候補で追加された行の既GAP06への参照追随としてcontracts/state-transition/gap_register_v1.jsonの1pathを有限追加する。実check_gap_register CLIが既GAP06.rowIdsに新matrix行4件のassetOnlyを検出したことを根拠とする。GAP06のstate=open/既branchIds/旧rowIds・fixtureCaseIds prefixと他gap全objectを保持し、既checkerが要求する双方向exact集合だけを追記する。未供給をclosedへ改めず、新意味/拒否順/観測推測を追加しない。必要criterion/全identity/履歴/参照値は実差分に応じて完全再導出/非作者照合する。既計画/source11の整合に必要な最小参照追随として扱い、checker緩和・既承認の再取得をしない。正式writerはroot、作者creation_pathはcache反映候補だけを作る。

2026-10-25T13:44:13.651182+00:00、同じgap登録追随についてGAP09も既state=resolved/既branch/旧prefixを保持し新4row参照だけを双方向exact集合へ追記する。tests/test_gap_register.pyの既exact件数GAP06=2/GAP09=4を正当な追加後6/8へ追随する1testpathも有限追加。旧state期待open4/resolved5/fixture件数/負例は不変とし、参照更新で新機能の完了や全P8を主張しない。rootはPO委任による通常派生値追随としてこの範囲を承認、作者はcacheだけを編集。
