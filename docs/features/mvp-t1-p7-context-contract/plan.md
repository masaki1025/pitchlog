---
feature: mvp-t1-p7-context-contract
status: active
承認: 済（PO委任によるCodex判断・局所契約候補）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-t1-p7-context-contract
created: 2026-10-24
計画レビュー周回: 2
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# T1/P7の文脈参照と構築境界の局所契約候補

## 1. 背景・目的

TSK544固定`7d6ce5443d71f6f7803d2ceed7e04c7ff87422ad`を起点とする隔離候補である。
要件v2.16/ADR-003 v0.9の確定`52625ed6a6d7d27a212acfee16b97c8a97d987a5`を採用済み規範として扱う。
正本採用とT1製品計算未着手を混同しない。既採用B+D・undo依存交代除外A、同scopeの4値source/意味版/digestとprefix完全性の要請を維持する。
本計画の承認対象は、未受理の完全Readyや新結果を作らず、既存の参照外殻・readonly宣言・構築条件・構造負例・所有対応を閉じる1単位だけである。

今回の作業はplan/researchの起案のみ。独立計画レビューと主担当のPO委任判断前にschema・宣言・試験を作らない。
既存544計画/旧U-X1/P7/providerのレビュー回数・採否を引き継ぎ、本枝の1単位をそれらの完了へ読み替えない。

## 2. スコープ

将来実装する候補の配置先は本featureの`candidate/`だけとする。`contracts/`や製品JS artifactの配置ではない。
候補を作る前に、この限定ディレクトリをcoreへ登録する2つの先行コミットを同一branch上で直列化する。

| 予定パス（docs/features/mvp-t1-p7-context-contract配下） | 所有する成果 |
| --- | --- |
| `candidate/context-refs.schema.json` | US1既存`ContentRefV1/T1ReadKeyV1/PrefixEvidenceRefV1/T1ContextRefsV1`のexact外殻。必要な既存mappingページ型は定義を参照して区別する。4意味payloadや新しい完了証拠fieldを発明しない |
| `candidate/context-refs.d.ts` | 同じ外殻のreadonly型宣言。schemaで表す制約・runtimeで別検証する制約を注記し、構造型をReadyや権威証拠として公開しない |
| `candidate/constructor-contract.md` | 構造受理、同scope/版の照合、出所/意味完全性検証を別段階にするconstructor契約。実装関数/Port/HTTP結果は追加しない |
| `candidate/structure-cases.json` | 新規の純入力と構造accept/rejectの負例。得点/RBI/状態拒否優先/ACK/回復の期待値は含めない |
| `candidate/source-ownership.md` | 各fieldの固定source、意味版/digest、供給/消費所有、受理済み/候補/未閉鎖を対応付ける |

実行検証の編集先は既存`tests/test_state_transition_contract_schema.py`の本候補専用テストだけ。
変更範囲は本plan/research、上記候補5パス、既存試験1パス、および先行登録の
`scripts/core_guard.py`・`tests/test_core_guard.py`・`.claude/core-areas.json`に限定する。
製品・旧feature・正本・正式assets・共通conftest・依存lockを変更しない。
規則snapshotは既存単一codec/F-1の定義への参照とsource対応に留め、独立schema/normalizer/計算をコピーしない。
PlayerRef/J6タグ、時点名簿・投影前状態・有効履歴prefixの未閉鎖payloadを`any/object`や自由JSONでReadyへ穴埋めしない。

## 3. 影響する正本

**反映なし**。既存要件/ADRの確定済み規範を入力にする局所候補であり、本枝で正本7.3・正式contracts/7.7・descriptor/T2参照digestを変更しない。
既存544計画、レビュー/承認履歴、正式入力case、P6盲検・期待値・原封印・比較資料へ触れない。
新しい意味fieldや正式配置が必要と判明した場合は、その差分だけ別単位へ返す。

`tests/test_state_transition_contract_schema.py`は既存2領域に登録済みだが、それだけでは新候補資産の単独変更を検知しない。
ハーネス6.3のpaths規則①/③/⑤に従い、`docs/features/mvp-t1-p7-context-contract/candidate/*`を
`game-state`と`sync-protocol`の双方へ限定追加する。外殻schema/d.ts/構造caseと、それらの構築境界・source所有契約の5ファイルを覆う。
本feature外、plan/research、他のdocs全体へ広げず、既存paths/guard_paths/領域集合/拒否規則を削除・縮小しない。
これは機械可読pathsの追加であり、正本の意味範囲を変更しない。追加自体の敵対レビュー・人間承認は6.3⑤に従う。
新しいtest/script/製品パスが必要なら勝手に足さず、必要な宣言と別単位へ分ける。

## 4. 実装方針・コミット単位

US1固定`cb0b1601f2ec76265f317e5104d4df387cf44344`の外殻schemaと接続契約、544固定点の
`t1-g6-rbi-review-candidate.md:99–108`を照合し、sourceに存在するfieldだけで閉じる。
tenant/game、wire D4と別の内部世代、D1/D5、business scope/lineage、4sourceのcontract ID/意味版/digestを対応付ける。
UUID・正整数・digest・必須/余剰・readonlyを区別する。新しいタグ値、正規化、意味上限/既定値を追加しない。

### prefix終端証拠とReadyの境界

既存`PrefixEvidenceRefV1`はsnapshot/lineage/before_d1/content_refを持つが、**履歴全体の終端証拠のexact fieldは未閉鎖**。
既存`T1MappingEvidencePageV1.continuation=null`はmappingページの終端であり、履歴全体の完全性証明へ流用しない。
完了証拠の要請を削らず、今回のschema受理範囲は既存参照外殻までとし、履歴全体の終端証拠の具体型/source受理は別依存と明示する。
新しい`complete:true`等を設けたり、D3/現在名簿から完成を推定したりしない。

constructor契約は構造受理だけからReadyを返せないこと、同scope/版/digest整合だけでは実出所/完全性を証明しないことを明記する。
未閉鎖payload/終端証拠がある間は完全Ready constructorの実装と実接続を対象外にする。
規則snapshotの意味は既存codec/F-1へ、PlayerRef/他3payloadは544/各供給側の閉型へ参照し、代替型を定義しない。
純入力の構造不正と、意味/出所がこの単位では判定不能な入力を分け、後者を「意味上正常」と採点しない。

O4は希望D2の1行占有ではなく、永続行2件の同値であるとの照合を維持する。
完全Ready＋O4は必要契約未閉鎖の③未証明であり、ReadyへD2一意検査を勝手に足して優先を決めない。
既存⑦→O4→C2・DI2/DI3・P3の既定順を保持し、B+D/除外Aを再裁定しない。

### 実装ステップ（本枝のコミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | core追加層を宣言し、その受理・拒否試験を先行固定する | `scripts/core_guard.py`の領域別追加層と`tests/test_core_guard.py`だけを変更。2領域それぞれに上記限定globを宣言し、現JSONは不変のまま、据え置き/完全追加を受理、部分追加・未宣言追加・既存層の削除/置換/並べ替え・同一コミットでのJSON/基線定義共変更を拒否。候補ファイルは0 |
| 2 | 宣言済み限定globを別コミットでJSONへ登録する | `.claude/core-areas.json`の対象2領域末尾へ各1件だけ追加。ステップ1の宣言/試験は変更0、候補ファイルは0。実JSONで予定5パス各単独変更が未記入の人間確認チェックを拒否し、両領域への帰属と限定外非包含を検証 |
| 3 | 既存文脈参照外殻・readonly宣言・構築境界・構造負例・source所有の局所候補を固定する | 候補5パスと既存構造試験だけでsource fieldに対照し、schema/宣言の対応と構造正負例が成功。先行登録済みcore3パスは変更0。新意味・完全Ready・prefix終端証明の捏造0。未閉鎖依存/固定SHAを記録し、独立候補レビューへ提出 |

各ステップを`(ステップ 1/3)`、`(ステップ 2/3)`、`(ステップ 3/3)`の別コミットにし、指示されたステップだけ実施して止まる。
番号取得用PRは作らず、同一branch上の親子コミットで宣言→JSON→候補を証明する。
登録済みの従来追加層は据え置き層として保持してから新しい追加層へ回転し、旧登録・拒否試験を落とさない。
`validate_area_path_layers`/`verify_area_path_baseline`の拒否条件、`BASELINE_DEFINITION_PATHS`、必須チェック文言、guard_pathsは変更しない。

先行試験は既存`tests/test_core_guard.py`へ`test_p7_context_candidate_core_`で始まる関数として置く。
宣言のみ/登録済みの2状態を明示して検証し、候補未作成のステップ1/2でも実ファイルの存在を仮定せず緑にする。
既存の登録集合assertは据え置き層＋今回の限定追加層の2状態へ追随させ、旧層の全件保持・順序・実在検査は残す。
実JSONの対象2領域が片側だけ登録された状態は登録集合試験で拒否する。
追加前の実JSONを固定した合成Git履歴から、宣言コミット→別JSONコミットを実CLIで受理すること、共変更は拒否することを確認する。
登録後は実JSONを使い、将来候補5パスそれぞれの単独変更だけを持つ合成PRの未チェック拒否/チェック済み受理を検証する。
globが本featureのcandidate配下だけを覆い、plan/research・隣接featureを新たに含めないこと、対象2領域以外のpathsが不変であることも検証する。
候補作成後の実在5ファイル被覆はステップ3で確認する。存在条件を外して旧登録の実在検査を弱めない。

既存試験で利用済みの`schema_checker._validate_instance`を用い、既存checker/正式schemaは変更しない。
同helperは`format`を検査しないため、UUID形式は同試験内の標準UUID検査で別に検証し、format検査済みと誤記しない。
必要なキーワードの対応範囲も検査し、未対応を黙って通さない。新しい依存/validator実装を製品へ置かない。
d.tsはschemaの必須field/型/readonlyと対応する宣言かを静的照合し、欠落/余剰/readonly除去の負例を設ける。
外殻の整数宣言をTSドメインの`number`演算許可やBigInt/十進文字列ABIの決定へ読み替えない。
本単位はTSコンパイラによる製品型適合・同一artifact実行の証明を含めない。

## 5. DoD

- core追加層の宣言/試験、別JSON登録、候補の3コミットがこの順に固定され、候補だけを後発変更しても必須チェックが発火する。
- 対象2領域へ限定glob各1件だけが追加され、既存領域/paths/guard_paths/拒否試験の削除・縮小がない。
- 5つの候補と構造試験が固定され、source hash/参照所有/構造と意味出所の境界を独立レビューできる。
- 既存規範52625ed6を採用済みとして扱い、規則snapshotのコピーやT1計算コードを追加しない。
- 4値source/意味版/digest・prefix完全性の要請を保持し、未閉鎖3payload/J6タグ/終端証拠をReadyへ補完しない。
- 本枝の合格をT1/P7全成立、正式schema/7.7、独立期待値、実Port/DB/HTTP/公開の合格にしない。
- 外部実接続の成功を候補契約整備の前提に追加しない。新意味fieldが必要なら具体依存として別表へ返す。

## 6. テスト計画

ステップ1/2は`uv run pytest tests/test_core_guard.py`で既存拒否を含めて検証する。
ステップ1はJSON不変、ステップ2は宣言/試験不変、ステップ3はcore3パス不変を各コミット差分で確認する。
追加層の合成履歴・単独変更PRの実CLI検証を同試験へ置き、候補作成前から実行可能にする。

`tests/test_state_transition_contract_schema.py`へ`test_p7_context_candidate_`で始まる局所テストを追加し、
同pathを`-k p7_context_candidate`で実行する。既存の正式ベクタ/期待値を本候補の試験入力に読み込まない。
候補schemaだけを根に、合成した純入力から必須/余剰、型（boolと整数含む）、UUID/digest、参照構造、未対応キーワード、readonly宣言対応を検証する。
scope/版/出所の不一致などschemaだけで判定できないものはconstructor契約の未検証境界として残し、構造成功をReady成功へ変換しない。
root Ruff/ty、docs-status/計画同期、差分/JSON参照検査を行う。新testpath/製品/正式入力は差分0、core資産は上記限定3パスだけを確認する。
今回の起案では試験・schema・JSON登録を作らず、計画再レビュー/主担当判断後も指示された上表の1ステップだけ実施する。

### 計画承認

2026-10-23T15:45:14.146059+00:00、Codex主担当/rootはPO委任4/5/7/8/10に基づきplan e02226a20e4fba9f1946ed09d9d59fc3507cb2c25a6d01307f41ddc5359fb1a5 / research2cd2562b36e48ea0bf56aaeb8d1d0e13cf5e7c8eca1456ff98bae5ec51fe7a96を承認。非作者/root/independent_reviewの第1回P1=1（新候補資産のcore捕捉不足）は全採用、第2回差分/影響は可決0/0/0。3ステップのうち個別指示する1ステップずつ実行し、共有書込を重複させない。未閉鎖意味・完全Ready・正式7.7/P6/T1製品未着手の境界は不変。山田正輝の個別値確認/署名・人間逐行確認は代記しない。

### 固定候補の検査基線追補

2026-10-23T15:47:43.171942+00:00、Codex主担当/rootはPO委任4/8/10により、ステップ1対象tests/test_core_guard.pyの2既存試験（actual_core_area_paths_follow_merge_base_layers、area_registration）がorigin/develop先端の未取得O5登録を固定枝の削除と誤認する不整合へ限定是正を許可。比較をこの枝とorigin/developの実merge-baseへ揃え、固定比較元の全paths/順序・許可層以外拒否・既存登録実在を保持する。製品core_guardのPR実base照合/拒否条件を変更しない。先端O5登録を取得済みとは記録せず、正式統合前に実baseから全登録/guard_pathsを保持して照合するゲートを残す。現ステップのJSON不変・別ステップJSON反映を維持。2既存試験で再現した2failedを履歴保持し、最終コード独立レビューで是正差分/非緩和を確認する。新意味/新編集path/ステップ総数の変更なし。

2026-10-24 00:49 JST記録、主担当/rootは同じPO委任で、全対象試験の276 passed / 8 failed（既報2件を含む）を受け、実merge-base比較への限定是正を計8件へ拡張する指示を出した。追加6件は`test_product_rls_paths_remain_in_develop_baseline`、`test_uf8_game_screen_paths_are_registered_in_all_areas`、`test_us1_sync_apply_paths_are_registered_in_both_areas`、`test_uf5_team_paths_are_registered_for_tenant_and_migration`、`test_ur1_registered_paths_are_retained_after_declaration_rotation`、`test_uf13_declaration_retains_json_and_checks_product_registration`。各件も先端だけのsync母集団登録による同原因の不一致であり、新登録を固定枝へ取得したことにはしない。従来層の全保持・順序・実在と許可層以外の拒否を残す。ステップ1終端のコード独立レビューへ、この8件の是正と元の失敗を渡す。JSON不変、実PR guard不変、正式統合前の全登録/guard_paths保持ゲートは上記のまま。
