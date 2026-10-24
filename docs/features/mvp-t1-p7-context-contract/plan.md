---
feature: mvp-t1-p7-context-contract
status: active
承認: 済（外殻候補・第7/8/9/10節。第11節の23flag/必要観測追補だけ未承認）
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


## 7. ステップ3/3後続：閉payload候補の限定追補（PO委任承認済み）

2026-10-24、PO委任4/5/7/8/10に基づく主担当/rootの起案指示。対象基線は`b2b825a4d48dbda34358733680c164f618444557`。
当初の外殻だけという制限（第1/2/4/5/6節）を、以下の**候補整備だけ**へ拡張する追補である。既存ステップ表の総数3、1→2→3の実コミット、承認・計画レビュー2回と採否、コードレビューの実施済み/待ちを保持し、過去を閉payload提供済みに書き換えない。新しい第4ステップを作らない。
今回の編集はplan/researchの2ファイルだけ。追補の非作者レビューと対象版を指定したrootのPO委任承認後にのみ、個別指示されたステップ3/3の後続候補を作る。この追補を起案したCodexはその非作者レビューを担当しない。

### 成果物・fieldと根拠

候補5パスと既存`tests/test_state_transition_contract_schema.py`の専用試験だけを後続編集範囲とする。core3パス・正式contracts/descriptor/T2 digest・旧544計画・製品・P6は変更0。
既存外殻4定義とそのdigest、既存caseは保持し、同じschema内の別`$defs`とreadonly宣言へ次の閉型を追加する。既存根`T1ContextRefsV1`の受理をReadyへ拡張しない。
下表の型名/field名/参照の格納表現は**新しいDTO候補**であり、正本で採用済みの名前・保存方式とは記録しない。`additionalProperties:false`・必須field・閉unionを用い、未知の内容を自由JSON、任意`any/object`、省略可能な穴で受理しない。

| 後続候補の範囲 | 意味・値域の固定根拠と、具体化する構造 |
| --- | --- |
| `PlayerRefV1`、`ScorerRefV1`、`HomeTouchOrderV1` | 要件v2.16付録E-1のJ6段落（1374行）/FR-015が正式IDと一時UUIDのタグ区別を要求。PlayerRefのliteral/ID格納キーは委任内の候補として明示してUUIDを検査する。ScorerRefの`kind:runner/runner_id`と`kind:batter/batter_id`、HomeTouchOrderの`kind:not-required`または`kind:observed/scorers`は正本どおり。観測列は1〜4、一意、順序を保持し同着variantを作らない。有効候補exact-set/攻撃側/同scope/C2照合はconstructor境界へ分け、構造だけで得点/RBIを確定しない |
| `T1RosterAtEventV1` | 544同固定点G6/RBI候補99〜108行、要件FR-001/007/011/015。同key・source参照・名簿版/適用時点、team別の選手参照、打順枠、守備/交代の有効関係を閉entry列で表す。打順1〜9は正式descriptor `state.battingOrder`、守備位置は既存FR-011/対応する採用済み語彙に対応付ける。警告だけの守備不足を新たな合法性拒否へ変えない。現在players一覧から過去名簿を生成せず、同一枠重複/越境/未証明写像を構築不可とする |
| `T1PreStateV1` | 正式`input_axes_descriptor_v1.json`のstate10軸を欠落なく対応。half=top/bottom、outs=0..2、strikes=0..2、balls=0..3、battingOrder=1..9、tiebreakActive/gameEnded=boolean。inning/両得点は正本FR-005/F-1の回/得点に対応し、descriptorの境界記号N/R/L/Mを実値としない。塁はfirst/second/thirdの閉じた在不在＋PlayerRefで表し、8 occupancy値との対応を示す。同key/source/状態版/名簿版、打者、半回適用印・membershipへの閉参照を持ち、C2後の投影を事前状態にしない |
| `T1EffectivePrefixV1`と有限ページ/終端証拠 | 544同候補105〜108行、US1 `cb0b1601`接続契約§3-1/3-2、同期正本のD1/D2/D5・有効版/墓標/変更版・O4。snapshot/lineage/対象境界/内容版、全ページの順序、各有効entryのevent参照・D1/D2の種別上の有無・D5・版/membership・origin参照、undo/replay窓の差分/印参照を閉じる。任意event JSONを埋めず、採用済み操作分類と閉じた内容参照へ対応し、監査に残る旧D5/旧版を現有効集合へ混ぜない。D2のない従属/同期専用種別へD2を捏造せず、D1を再生順にしない |
| `constructor-contract.md`/`source-ownership.md` | 各fieldに固定source・採用状態・意味版/内容digest・供給/消費者を記録。規則値は単一`rule_snapshot.py`/F-1参照だけとし、4値の同key/scope/世代/対象D1/lineage/時点/版とcontent参照を照合する。規則型/codecをコピーしない。実装関数、read token、署名、ACL/新wire/resultIDは追加しない |

ページ型の候補はsnapshot/版/境界を全ページへ束縛し、先頭・安定cursor連鎖・抜け/重複のない順序・最終cursor・供給側の全対象集合との照合証拠を表す閉manifestとして設計する。空prefixにも先頭=終端の証拠が必要で、単なる`complete:true`、自己申告件数/digest、D3、mappingの`continuation:null`を全履歴終端としない。schemaはmanifestの構造しか検査できない。供給側の真正な発行・同scope全ページの実読了/集合一致はconstructorの必要条件として残し、架空の発行済み証拠や実Ready成功caseを作らない。
版識別子・cursor・manifest・PlayerRefタグliteralの表現や正本が指定しない数値格納型は委任内具体化の**候補**としてsource所有表へ明記し、意味に基づかない上限/既定値を足さない。event/変更/墓標/差分の参照先が未閉型なら、その型/供給証拠を未閉鎖として列挙し、参照文字列の非空性を意味閉包と採点しない。

### 合格条件・停止点

既存5成果物を更新し、schema/d.tsの対応、新定義の必須/余剰/union/値域/UUID、PlayerRefのタグ取り違え、J6の長さ/重複/順序、state10軸/runner occupancy対応、名簿・版・scope・prefix参照の出所対応を既存専用試験で検査する。新しい構造正負caseとconstructor条件対応を分け、ページ抜け/重複/混在snapshot/版/cursor不連鎖/早い終端/未証明originが**構築条件を満たさない**ことを記録する。構造成功でも出所・完全性未証明のcaseはReady成功にせず、runtime検証未実装を明記する。既存checkerが未対応のkeywordは黙って無視せず、既存試験内で対応可能な閉表現/局所検査を使い、新validatorや共通helperを増設しない。

既存外殻4定義digest/旧caseの保持、root Ruff/ty、専用構造試験（`-k p7_context_candidate`）、core既存試験と5パス被覆、docs-status/計画同期/差分検査を行う。意味計算の期待値・P6資料を試験入力にせず、正式契約への反映や全23フラグ/OUT3/RBI/G6-S閉包・P6/P7担当別受理・7.7を代替しない。後続のコード固定版を非作者レビューへ渡し、現基線の未取得登録は実統合前に実baseへ追随して全保持を再検査する。

新しいO4順/Ready+O4到達性の断定、状態拒否とO4が同時成立する場合の新優先、旧codecにない観測/半回の移行既定値、因果だけで拒否する新P3結果、未知依存の公的失敗分類は今回のDTO選択に含めない。既採用⑦→O4→C2/B+D/除外Aを維持し、必要な新意味だけを根拠・具体入力・影響付きでrootへ返す。正式descriptorに未反映のJ6や新候補fieldを正式採用済みにしない。
**本追補は実Port/HTTP/DB完成を契約準備の開始条件へ追加せず、完全Ready実装・製品T1計算・初球だけの開始許可も与えない。** 544の全開始条件、正式7.7/全23フラグ/G6閉包/P6/P7未達は継続する。今回の追補の独立レビューと委任承認は次段に別記し、旧承認を新scopeへ流用しない。


### 閉payload候補追補のPO委任承認

2026-10-23T19:14:58.360660+00:00、Codex主担当/rootはPO4/5/7/8/10と2026-10-24の縦断優先指示に基づき、対象HEAD5dcccce3、plan75cb708d1d2efe624f7f562ad02c628e8602cee8e17c7aac8aad036db7056b6c/research7fd45847421d7954416a41c011a57e4d2c8d31b501798c2151d33bbfb4ceb421を承認。非作者rights_replacement_reviewの限定追加第1回P0=0/P1=0/P2=0と根拠・source固定点を照合した。DTO命名/格納・構築境界を既採用意味に沿って具体化する候補作業の承認であり、正式型受理・Ready・全T1意味閉包・P6/P7・7.7・製品計算の開始を代替しない。旧3段階/外殻4定義/旧case/全レビュー実績・中間失敗を保持し、この範囲のstep3/3後続候補だけを個別実装する。山田正輝の個別確認/署名・人間逐行確認を代記しない。


## 8. ステップ3/3後続：operation-contentの閉型候補（未承認）

2026-10-24、主担当/rootのPO委任4/5/7/8/10に基づく起案指示。対象基線は`7d80d3e4a337bcd0639a4d4e7755cda1a4571a28`。既存3段階/総数3・旧承認・計画/候補/コードの全レビュー履歴を保持し、次の限定単位をステップ3/3の後続とする。第7節の7markerを全て解消したと記録しない。今回の編集は本plan/researchのみで、この追補の非作者確認・対象版を指定したrootの委任承認と個別実装指示前に候補/試験を変更しない。

### 実装する集合と出所

後続の編集所有は従来のcandidate5files、既存`tests/test_state_transition_contract_schema.py`の`p7_context_candidate`専用部分、本researchだけ。planの実施記録を除き、core3・正式contracts/descriptor/T2・正本・P6・製品/UF8 sourceは変更しない。候補schema/d.ts・構造case・constructor・source所有対応を同じ単位で更新し、外殻4定義/同一性digest・旧25case・旧宣言を保持する。

| 閉型候補の集合 | 固定した意味・fieldと実装境界 |
| --- | --- |
| 操作4型 `T1GameEndPayloadV1/T1SubstitutionPayloadV1/T1TiebreakStartPayloadV1/T1AdhocRegistrationPayloadV1` | 正式operationRows10行を操作別に重複除去した4payloadShapeを直接対応させる。終了宣言は空object。交代はsubstitutionType=4値、outgoing/incomingPlayerId必須、battingOrderSlot/defensivePositionId任意。TBはrunnerPlacementの既存2値・leadoffBatter1..9・inning>=1。その場登録はname/throws/bats必須、uniformNumber/temporaryPlayerId任意。既存任意fieldの不在を既定値で埋めず、必須化/削除しない。PlayerRef/同scope・打順/守備/DH・規則snapshotとの照合をconstructor条件へ対応 |
| 毎球の閉観測型 `T1RunnerOutcomeV1/T1RunnerEventPayloadV1/T1RunnerAdvanceOverridesV1/T1ThirdOutObservationV1/T1ThirdOutTimingV1/T1InterferenceRulingV1/T1OfficialScoringV1/T1RbiObservationsV1` | FR-003/004、OUT3-01..05、ADV、INT、RBI-01..09と正式descriptorの既採用観測/表現能力を具体化。走者ごとの停止/アウト/到達・企図塁・アウト種別、手動上書き、第三アウトの有無/種類/対象、走者別時機、妨害の採用結果/授与塁/帰塁先、公式失策と野手参照、RBIの走者別継続/再発進・失策なし得点可否を閉じる。新タグliteralはDTO候補として出所を明記し、原典で決まらない結果条件を補わない。例外3種以外の時機2値/同時の扱いは正本どおり |
| `T1PerPitchPayloadV1/T1OperationContentV1` | kind/pitchEventKind、結果ID・上記観測・既存HomeTouchOrderV1を閉unionへ束ねる。結果/走者状態等のIDを正式語彙seedと有限snapshotへ照合し、非空refだけで内容を合法としない。J6のsnake/順序・有効候補exact-set境界を維持。statFlags23キーは計算出力であり、利用者の入力payloadへ追加しない |
| 既存entry.contentとの接合 | 今回具体化したkindだけを閉内容型へ束縛し、operation_kind/contentの食違いを負例にする。undo/P3原本・版関係等で閉内容が未供給なら既存の明示unresolvedを残し、未知kindを汎用objectで通さない。部分的な閉union候補をoperation-content全kind/他6marker/全T1の意味閉包と称さない |

各fieldの出所/意味版/hash/任意性と、schemaで判定する構造・constructorに残る参照/相反/観測要否の条件を分ける。正式`operationPayloadShape.properties`の自由objectや既存historyInputを、閉内容schemaとして流用しない。新語彙を意味が既知のIDへ推測変換せず、元の原入力/タグ/不在を損失なく保持する。名前carrierの既存stringは候補で保持するが、ADR D-8の正式例外/比較境界の整合済みとは記録しない。正式整合の具体案と根拠はresearch末尾へ固定し、rootの後段正本ゲートへ返す。

U-F8固定/現HEAD eb83787cのRawPlayObservation/RawSubstitutionDraftは表示用raw入力で、正式payloadの提供ではない。field対応とdefense→defensive等のadapter対応を候補に記録するが、画面の任意question key/回答から意味を推測しない。今回はUF8 sourceを編集せず、未回答null・型違い・文脈違いを内容の既定値へ変換しない。

### 検査・合格条件と停止点

専用構造試験で4操作のraw shape/field/任意性・enum・余剰/欠落、追加readonly宣言、毎球観測のtag/走者別参照/時機/J6順序、operation kindとの組合せ、語彙/原典射影を検証する。既存helper/専用宣言照合は既採用任意field・追加閉型に必要な限定文法だけへ対応し、外殻の全必須/余剰拒否や旧拒否を弱めない。正式raw shapeをそのまま表す場合は、任意fieldも許可集合/型を閉じて不在を保持する。any/自由properties/未対応keywordの黙認・新製品validatorは不可。未実装の意味要否/出所照合を構造成功やruntime Ready成功と採点しない。計算結果/P6期待値を新caseへ取り込まない。

root Ruff/ty、専用pytest（`-k p7_context_candidate`）、既存core試験/候補5パス被覆、旧保持hash、docs-status/計画同期/差分検査を必要範囲で行い、固定コード版を非作者レビューへ渡す。7d80の実施済み検査/中間失敗・既存レビューは履歴として保持し、今回の追補は未レビューである。

旧codecの観測/対象半回欠落、元scope不明の既存行、新状態拒否とO4の競合、新P3公開分岐・一般同値不成立の公開分類、未裁定の野球分岐はこの単位で決めない。FR-040は延期のまま。D2は正本のbigint構造域とordering.py実経路の非負域を分け、実装だけを根拠に原典の域を狭めない。membership/半回印/P3原本/undo差分/selection/terminalの実閉内容・真正issuer/有限読了は後続で具体化する。実Port/HTTP/DB完成をこの候補整備の開始条件へ追加せず、正式7.7/23フラグ/G6閉包/P6/P7・全T1計算の開始条件を代替しない。


2026-10-23T20:27:05.012303+00:00、Codex主担当/rootはPO4/5/7/8/10と縦断優先指示に基づき、限定追補HEAD6b821b6f/plan c469e4d7b1bfbb0bca9523d72fa8217f7fbaec422611489382606b32b775452d/research726a57e0b415497ea0640f9eebd9c284adf19d23294aa46b4ee723d26f93f61aを承認。非作者rights_replacement_reviewの限定計画確認P0=0/P1=0/P2=0、full-index binarydiffebd7f6aa2ce34a3ad290f974cf77693df86c142394e8c04f33328fd5f1d03751一致と根拠を受領した。既存第8節のcandidate5files/既存専用試験/researchへ操作4型・既採用毎球観測・閉union/原典射影を具体化する同step3/3の作業だけを指示する。D8/namecarrierの正式整合/旧codec欠落/新拒否意味は未採用のまま後段へ返し、旧レビュー/原典/23フラグ・P6/P7/P8全条件を保持。実Port/HTTP/DB/耐久完成を本候補着手条件へ追加せず、製品計算本体/正式7.7/Readyの開始許可とはしない。PO委任によるCodex判断であり、人間本人の逐行確認/署名を代記していない。


## 9. ステップ3/3後続：残4kind共通のV10対象参照（PO委任承認）

対象基線は`3c23eeeac8f4dbc3065afb0716c865223281d12b`。第8節はundo/P3原本を留保しているため、その承認を流用せず、今回の最小単位だけを追補する。第8節承認e703と、7bの非作者P1=1→3c23限定0/58件・実TS正例2/負例10の受領を保持する。旧総数3/ステップ履歴/全レビュー通算は変更しない。本起案はplan/researchだけで、非作者確認とrootの対象版承認・実装指示後に同step3/3の候補を作る。

| 今回の閉型候補 | field/値域と根拠・範囲 |
| --- | --- |
| `T1WireTargetReferenceV1` | V10の`game_id/d4/d1`を全必須・余剰拒否とする。正式wire設計2-3 L-1/L-6の小文字UUID正規形、L-3の非空不透明D4文字列、L-2の整数D1=1..2^53-1。原値を保持し、UUIDの大小文字変換・D4数値化・丸めをしない。この上限はwire D1の規約であり既存内部key/D2の域を狭めない |
| `T1ResolvedTargetReferenceV1` | `wire: T1WireTargetReferenceV1`と`internal_generation`の閉対応。後者の構造は既存T1ReadKeyV1同名fieldと辞書同一の正整数。wire D4と内部世代を別々に保持する候補であり、値を並べただけで解決済み/同scopeとしない。実写像の発行権威・対象event/版・同tenant/game/lineage/対象時点の一致はconstructor残件 |
| `T1DependentAddressProjectionV1` | `event_kind`を2/10/11/12の**文字列**で区別する4variantと、上記`target_reference`だけの閉射影。sync-protocol5-5/7-6/8-1のundo/プレイ修正/論理削除/交代修正に対応。全wireイベント/envelopeではなくV5/V10の投影型で、D5・V7・P3のV11等を不要にする型ではない。既存entry/content/全47定義にはまだ接続・変更しない |

固定規範は観測develop `a10bcd5efa74f6c0f8b5ba5fef0721f4b58b89ec`（同対象本文は547から不変）のsync-protocol4-3/5-5/7-6/8-1、sync-wire-schema/design2-3/2-4/2-6/3-2/3-3/3-4で、完全hashはresearchへ固定する。現在worktreeにない正式改訂を取り込んだとは記録しない。旧内部`change_path._target`の`game/d4/d1`とwireの`game_id/d4/d1`は別面として対応を明記し、そのparserの数値変換/上限だけを規範根拠にしない。

編集所有は既存candidate5files・既存schema試験のp7_context_candidate専用部分/renderer・researchだけ。3定義とreadonly宣言/構造正負入力/出所・構築境界を追加し、3c23の全47定義・238case・11constructor対応・空型never是正・外殻hashを保持する。schemaで正規UUID/opaque原値/整数bool拒否/安全整数上下限/必須余剰/4tagを検査し、既存閉文法・readonly照合だけを利用する。TSではopaque string/構造宣言とし、JSON値域/真正性/実失効の保証をTS代入だけから主張しない。局所pytest/Ruff/ty/docs/計画同期/保持hashで固定し、重いcore全件は反復しない。

V10はS-2の処理段階値である。本型の負例をHTTP入口の新S-1拒否へ移さず、公開B14/D5消費やundoの新失敗分類を追加しない。4kindのV7内容は未供給のまま、P3 V11の物理表現もwire設計3-4/U-G2の残件とする。V7を空objectと決めたり、expected_versionを現実装のintだけから正式採用したりしない。undo差分/全後続依存・membership/元半回/有限prefix・P7D06等の未採用結果や優先順は本単位へ混ぜない。正式21分岐の実数はresearchへ別記し、構造fixture成功を規範case/P6blind/正式受理へ代替しない。

**この単位でoperation-content残4kindの完全閉包は0、7markerの消去も0。** 採用済みV10の3field/4kind対応とwire/内部の型境界を先に供給する単位であり、T1OperationContentV1の5/9 kindを9/9完成へ書き換えない。正式7.7/23flags/G6/P6/P7・全T1計算本体/Readyの開始条件を保持し、実Port/HTTP/DB完成をこの型準備の前条件へ追加しない。


2026-10-23T22:07:50Z、PO委任によるCodex主担当/root判断として、676dffe442be8a866b0ec688360ad827dbc50835の第9節（plan SHA2a15f03436142a632be31fd8bd2dbe1425c61275e75d5d689a25fb3d69f7fe98、research SHAfba01039f4d5eda005d6f82e3ffae1bd5b22e353ea3a66c5b8d20c157d7463f9、標準binarydiff178173c3345800a48f45091e906f4a658e43d2b90f9009d083f1794a41ce1d9a）だけを承認し、同step3/3の3閉型候補実装を指示する。新追補作成に非関与のcsv_reviewによる新節限定第1回レビュー0/0/0と規範対応/実数照合を根拠にする。レビュアーの旧外殻作成関与は開示されており、旧外殻全体の独立再確認やP6 blind資格には広げない。旧第8節/空型是正の非作者系列・正式T1全開始条件を保持し、7marker消去0/残4kind閉包0を覆さない。人間本人の個別実値確認・署名を代記しない。

## 10. ステップ3/3後続：OUT3-04/05の純入力・作者導出を分離した最小case候補（未承認）

基線`6a579374c190a76b7be4107d27f1c2e2a5584c2e`の3閉型は非作者rights限定0（独立415件/292schema+9edge/実TS7正16負/旧hash一致）をroot経由で受領した。旧第9節と全レビュー通算を保持する。本節は正式不足15分岐のうちOUT3-04/05の2分岐へ向けた**規範case候補**を供給する別単位で、第8/9節の構造case承認を意味期待値作成へ流用しない。旧ステップ総数3は変えず、非作者確認・rootの対象版承認後に同ステップ3/3の後続候補として実装する。今はplan/researchだけを編集する。

### 対向2入力と今回閉じる不足

要件v2.16 FR-003/FR-005・A-1 OUT3-04/05・A-3、E-1、ADR-003 v0.9 D-6/D-8/D-11が採用済み原典である。1回表・二死二三塁・単打、打者は一塁へ到達済み、二塁走者は三塁で非フォースのタッグアウトとなり第3アウト、三塁走者は本塁到達という同一入力を作る。変更点は`thirdOutTimingByRunner.third`の`home-before-third-out`/`not-before-third-out`だけとする。実走者のPlayerRef、手動上書き、`thirdOutObservation={kind:"other-third-out",out_person:二塁走者}`を明示し、OUT3-01/02/03を除外できる原観測を保持する。非サヨナラ・妨害/失策なし・TB非適用で固定し、不要J6/RBI観測は既存の明示variantで保持する。missing値をfalse等へ補完せず、現有の閉観測型を再利用する。

正式manual fixtureのinputCoordinateは7基本軸とinterferenceRuling文字列だけを許すため、この実走者/手動結果/第3アウト種別/時機を現在の正式fixtureへ格納できない。正式descriptorにも第3アウト種別の閉入力が未反映で、OUT3の得点可否を区別する規範行/case bindingと比較面の具体化が未供給である。本単位はその不足を2つの純入力・作者導出・原典対応で具体化し、rootの後段正式化へ渡す。新外殻3型等だけを増やす単位にはしない。

| 編集パス（本feature配下。実装は承認後） | 成果・境界 |
| --- | --- |
| `candidate/t1-pure-inputs-v1.json`（新規） | 中立format版・中立input ID・入力だけを持つ2件。既存閉型で表せる投影前10状態軸/同一試合・攻撃側の正式PlayerRefと名簿/保存規則snapshotの必要値/毎球観測を固定する。入力にbranch ID、作者case名、期待値、採否、導出理由、author資料へのリンク/hashを入れない。完全Ready発行証拠を捏造しない |
| `candidate/t1-author-derived-v1.json`（新規） | 中立input IDで対応する作者側branch対応、原典・row参照候補、期待値、導出根拠、正式化の不足を保持する。既存正式case/P6期待値を参照・コピーせず原典から作る。OUT3適用前後の候補/計上得点者・得点数/RBI対象・打点数、実適用後のアウト/攻守交代/カウント/走者/得点などを区別し、正式E-1の6比較field・23flag全キーを省略しない。基礎matrix行の既定効果と手動結果/OUT3後の適用値を混同しない。既存規範で導けないfieldが出ればそのfieldだけを未解決としてrootへ返し、推測値で完全caseとしない |
| 既存`candidate/source-ownership.md`・`constructor-contract.md`・research | 上記2入力・観測の既存型対応、作者側の正式schema/descriptor/row binding差分案、比較面・未達と安全な将来packet切出し手順を追記。期待値の実値/逐件理由はauthor JSONだけに置き、純入力fileへ混ぜない |
| 既存`tests/test_state_transition_contract_schema.py`の候補専用部分 | 新2fileの厳格shape/中立ID対応、2入力の差が時機1箇所だけであること、既存観測/状態部分の構造、author outputの全field・23key・source対応、純入力に作者資料や判定fieldがないこと、旧50定義/292case/11constructor/旧宣言byte保持を確認する。既存core被覆試験のexact file集合だけを旧5+新2へ増やす（既存`candidate/*`登録範囲内）。新型・renderer変更や別の計算実装は作らない |

現有schema/d.ts/structure-casesは変更0。新2fileは既登録`candidate/*`でgame-state/sync-protocol両方に検出されるため、core定義/JSONの追加変更は不要。formal assets、旧544/UF8/US1、主担当台帳、正本、製品source、P6の旧封印/期待値・所有不明JSONは編集/参照しない。既存6mapping/各2case・missing15を保持し、当候補作成だけでmissing15→13を宣言しない。root後段の正式schema/descriptor/行/case/派生資産整合・独立受理・7.7実値反映後にのみ該当不足を閉じる。

### 検証・独立性・停止点

2つの合法入力は互いにOUT3-04/05の対向負例にもなり、必要時機の欠落/別走者への付替えはローカル変異入力で観測欠落として検出する。HTTP公開結果ID・P7D06・新拒否優先/D5消費は採用しない。計算器を作って作者期待値を自己生成せず、原典による作者導出を明示する。既存専用pytest/保持hash・Ruff/ty/docs/計画同期で固定し、重いcore/DB/本体を起動しない。新case群が完全比較面を満たさなければ、部分oracleをformal completeと称さず具体field不足を返す。

将来blind検証へ渡せるのは、純入力fileの**内容だけ**を中立名`inputs.json`へコピーしたpacket、採用済み規範原典、固定版・範囲だけである。本plan/research/author file/著者会話/branch mapping・旧case比較を同梱しない。非継承の未曝露検証者が導出を封印・hash固定した後に、rootが別の作者資料で比較する。候補作者や本会話を新検証者へ継承させず、新規agentだから未曝露とは認定しない。本単位ではpacketの手順/入力保持を準備するだけで、P6blind起動・封印・受理を実施したとは記録しない。

**case供給の到達点は不足2分岐に対応する新純入力2件と分離作者導出、正式closureは後段ゲート待ち。** 7markerやT1全開始条件を減らすものではなく、全23flags/G6/残13分岐の規範case/P7/7.7/Ready/T1計算は別残件を維持する。実Port/HTTP/DB完成をこの候補準備の着手条件にしない。


2026-10-24、PO委任によるCodex主担当/root判断として、1efe07958cf2dd8b474dc1aaccdcf404e4b9df74の第10節（planSHA5b8cffe4ab272c2f0ffc901baf058d4f0197851fc917fde2e6570bc9c7c95246/research63ba7c514b7b48c9bcd830bf13e05130be32d10e9835664fd039944cee4bc027、標準diff57f4058bbe9bc085073bd559c0f319981cd9b166fd62e3f6ebd34880ba38782c）だけを承認し、指定対向2入力/作者値の分離候補実装を指示する。新節作成に非関与のcsv_reviewによる新節限定第1回0/0/0と、要件A-1 OUT3-04/05との照合を根拠とする。旧外殻へのレビュアー関与は開示し、旧外殻全体の独立確認やP6未曝露資格に広げない。正式schema/descriptor/binding/独立導出/受理/7.7は後段条件で、missing15の先行削減・T1本体開始は認めない。純入力と作者期待/理由/branch資料を分離し、futureblindは純入力だけを受領して封印後に比較する。人間本人の実値確認/署名を代記しない。

## 11. ステップ3/3後続：単打の有限域で23flag条件・RBI因果観測を閉じる候補（PO委任承認済み）

基線は`ee7568bdda78f71de50498212741d4d81244e280`。既承認§10で供給した入力のRBI不足に対する次単位であり、旧総数3・段階/レビュー通算・旧50定義/292構造入力/11constructor・純入力v1/author-v1/evaluation-v2を保持する。今回はplan/researchだけを起案し、非作者計画レビューと主担当の対象版承認前にcandidate/試験/製品を編集しない。全T1のXC-13を一度に完了させる計画ではなく、既採用FR-003/OUT3/RBIの条件が一意な有限域と、その域の23keyを閉じる同step3/3の1単位である。

### 11.1 固定する域Dと23keyの必要十分条件

域Dは「1回表・二死二三塁・普通の単打・pitch-event・公式失策/妨害なし・打者一塁・R2は非フォースの三塁タッグアウト・R3は本塁到達」で、両走者の実結果は明示overrideとする。OUT3-01/02/03不適用と非サヨナラをGivenから照合し、規則snapshot/名簿/PlayerRefは既供給の値を使う。既定進塁を参照しないためD07の選択を前提にしない。RBIの必要原観測は新しい合成入力として別版へ固定し、v1/v2の不足を事実追加で埋めない。RBI-01/02は併殺/公式失策なし、05は二死/失策なし、06は本塁打でない、07は押出しでないという原典条件によりこの域で不適用となる。

| 対象（全23key、域D内の条件） | 根拠・今回の閉鎖範囲 |
| --- | --- |
| 常時trueの7key: 投球回算入アウト/投球数/被安打/打席/打数/安打/塁打 | 実アウト1・pitch-event・単打・打席終了と打数控除事由なし。E-1/E-2、A-2/A-3、FR-022。これはD内の必要十分条件で、全結果IDに対する条件表ではない |
| 常時falseの13key: 奪三振/与四球/与死球/被本塁打/失策/本塁打/犠打/犠飛/四球/死球/三振/打撃妨害出塁/走塁妨害出塁 | 各定義の該当結果/公式記録がDにない。E-1/A-2/A-3/FR-020/022。失策なしをRBI因果なしの証拠にはしない |
| 得点/失点 | Dの必要観測が揃うとき、OUT3後・上限後の計上得点者R3が存在することと同値。Dではthirdの時機がhome-before-third-outのときだけ。責任投手の個別帰属やscoreboard絶対値を決定したとはしない |
| 打点 | DのRBI入力域が空ならfalse。R3が入力域に入るときは、RBI-03/04の必要観測を確認し、03に適合ならtrue、04ならfalse、両方不適合なら08でtrue。必要観測欠落時には完全23flag出力を作らず、作者の部分既知/unknownと入力不足を別に記録する |

D外の有効化条件、他結果/操作、犠打失策等の追加記録員判断、OUT3-01..03の対象/先行関係、RBI-01/02/05/06/07の全case、J6サヨナラ上限の全分岐は今回未閉である。Dの20定数keyについて反対の真偽が成立する合法入力は域外なので、そのactivation/deactivation witnessを今回供給したとは数えない。全23flag/全球面/全T1開始成立への昇格は不可。

### 11.2 入力に欠ける事実と閉DTO候補（保存wire/公開結果ではない）

既存`T1RbiObservationsV1.runnerContinuityByRunner`のnot-required/observedと、走者別kept-running/stopped-and-restartedは不変で再利用する。not-requiredは観測の不在であり「ミスプレイなし」「走り続けた」ではない。追加候補`T1RbiMisplayObservationsV1`は`cause_by_runner`と`restart_by_runner`の2field全必須・余剰拒否objectとし、両fieldそれぞれがnot-required、またはobserved/by_runnerの閉unionを持つ。runner-keyはbatter/first/second/thirdだけで、各観測は同プレイの当該PlayerRefへ束縛する。causeの各値は`person:PlayerRefV1`、`held_too_long:boolean`、`unnecessary_throw:boolean`、restartの各値は`person:PlayerRefV1`、`after_observing_misplay:boolean`だけを持つ全必須・余剰拒否objectとする。因果とrestartを別fieldにすることで、因果不在のタグと明示falseを区別し、片方だけ観測済みの入力も表す。純入力v2では既存per_pitchとは別の候補観測fieldとして合成し、旧閉型へ黙ってpropertyを追加せず、正式wire位置を決めたとも扱わない。

held_too_long/unnecessary_throwは、RBI-03/04がいう「当該走者の生還に結びつく持ちすぎ/無用送球」の記録員観測で、全プレイ一般にその動作があったという無関係な事実ではない。両trueを許し勝手に排他化しない。停止再発進の観測だけではRBI-04の「ミスプレイを見て再発進した」まで分からないため、restartのtrue/falseは**当該持ちすぎ/無用送球を見たことが再発進の契機だったか**の観測として別保持する。これらをresultId/no-error/時刻/送球先から推定せず、RBI branch/打点可否自体を入力する型にも代えない。値を観測者が入力しても真正性/同scopeの発行済み証拠にはしない。

入力相関は原典の必要条件だけとする。(a) OUT3後のRBI入力域にR3が入るとき、そのR3の因果観測が必要。(b) 関係する持ちすぎ/無用送球が観測trueなら、R3の継続/停止再発進観測が必要。(c) (a)(b)が必要な局面でそのR3が停止再発進なら、ミスプレイを見た再発進かの観測が必要。(d) kept-runningと同一期間のrestart true、両因果falseと当該ミスプレイへのrestart true、別走者/別scope/対象キーの不一致は同時に真にできない。不必要な観測は要求せず、既に明示された原値を削除/既定化しない。欠落・未表現・矛盾は候補内部の検査項目集合で表し、順序付き公開拒否/結果ID/D5消費にしない。D06への新しい選択を含めない。

### 11.3 有限閉鎖・負例・成果物

Dで変動させる因子は、thirdの時機2値、因果観測5値（not-required、observedのboolean対4通り）、既存継続観測3値（not-required/kept-running/stopped-and-restarted）、restart観測3値（not-required/observed false/observed true）で、**2×5×3×3=90構造セル**。各セルを原典/必要観測/矛盾条件へ対応させ、正常・必要入力不足・矛盾（同時指摘可）の件数と範囲を固定する。得点無効のセルでRBI観測欠落を新拒否にしない。型違い/未知tag/空必須観測/対象差替え等はこの90とは別の構造変異で、正例数に混ぜない。既採用原典だけでは一意に分類できないセルが判明すれば、具体fieldと条文不足をunknown/対象外として数えて主担当へ返し、期待値補完で正常セルにしない。

23keyは原典ID・D内必要十分条件・必要観測・適用順・正常/負例IDの23行を完全に対応させる。変動3keyは条件真でflagをfalseにする負例と条件偽でtrueにする負例を各々持つ（最低6対向変異）。定数20keyはDのGivenを保持してflagだけ反転する矛盾入力を各1件（最低20変異）とし、**計26以上の出力反転負例**を置く。定数keyの域外の反対条件20方向は未収録と明示し、これを全球域の双方向負例完了に数えない。意味の正しさは非作者の原典照合で別途確認し、作者表との一致だけで機械保証済みにしない。

承認後の編集先は、`candidate/t1-rbi-observation-contract-v1.json`（新観測の閉型/出所・必要相関）、`candidate/t1-single-flag-conditions-v1.json`（23行・域/原典対応・被覆宣言）、`candidate/t1-rbi-observation-inputs-v2.json`（新中立IDの合成純入力、共通Givenと90セル。期待/branch/判定/理由を入れない）、`candidate/t1-rbi-observation-author-v3.json`（対応ID・作者条件評価/期待値・理由・負例/未閉範囲）の新4file、既存source-ownership/constructor/research、既存schema試験の本候補専用部分だけ。旧50定義/schema/d.ts/292case/11constructor/v1/v2各fileは不変。全新fileは登録済candidate/*に含まれ、core3/正式資産/正本/製品/旧P6は変更しない。外部refが必要なら同じ候補schemaの既存PlayerRefV1へのexact参照だけを使い、保存schemaコピー/汎用resolverの追加をしない。

試験は型・閉grammar・有限集合のexact被覆/重複/欠落・観測相関・原典ID・23key/負例対応・既存hash保持・core被覆を検査する。既存generic schema/比較の範囲を使い、任意イベントから得点/RBI/flagを返す別計算器/製品validatorは作らない。新pureと作者資料は先に分離して固定し、将来未曝露検証者へ作者条件表/期待値/会話を渡さない。合成事実は不足観測軸の被覆用に新規作成し、旧期待値や封印へ一致させる目的でv1を改変しない。

DoDは90セルの出所/観測充足/未閉範囲、D内23条件行、必要な入力不足/相反・26以上の反転負例と未実施方向の明示、既存全保持、局所pytest/Ruff/ty/docs/計画同期・非作者限定レビューへの固定版提出である。**unknown消去数は合格条件にしない。** 正式missing15/closure0、D06/D07未回答、全XC-13/7marker/G6/P2/P6/P7/P8/7.7・T1製品開始未達を保持する。実Port/DB/HTTP/製品artifact実測をこの契約候補準備の着手前条件に追加しない。


2026-10-24T01:09:40.769070+00:00、PO委任によるCodex主担当/root判断として、f86e3d76の第11節（plan d6ed064df28cf203070102d29e5f54f80c56a726fa1d502f0b5098c31795e3ea / research be52806e8668492ebea656f128e5d9d20fc5a046c2aaf0bf0ef95811235c4e49、標準diff6d8c355abcfa50b0530310ac0cb533069ab312a3203647c7f621e5cd369f5438）を承認する。新節作成に非関与のcsv_reviewによる限定第1回0/0/0、採用済みFR-003/OUT3/RBIと23flagの原典照合、実core捕捉を根拠とする。レビュアーの旧外殻への関与を開示し、旧candidate全体の独立確認や新P6資格へ拡張しない。D内の観測/条件・中立入力90セル・作者分離・負例対応を同step3/3の指定範囲にだけ実装し、旧50/292/11/v1/v2を保持する。D06/D07/正式missing15/7marker/全開始条件・正式受理は不変で、別計算器/仮観測/unknown消去を合格条件としない。本人の実値確認・逐行確認・署名を代記しない。
