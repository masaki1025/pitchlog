---
feature: tsk544-t1-state-calculation
status: active
承認: 済(2026-10-20・山田正輝)
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3f893b75e68781e5a55ce961b18fab3f
branch: feature/mvp-t1-ordinary-pitches
created: 2026-10-20
計画レビュー周回: 10
確定ゲート周回: 2
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: TSK-544 T1 状況計算

**承認記録**: 2026-10-20、山田正輝がSHA-256 `40340ce0c2f399e35240c19ce64496656eeae93d4854ba2ba6eb3d6984d720fd` の本計画を承認した。追加独立レビューのP1 3件を採用した最終反映差分が未再レビューであることを含む承認である。承認記録によるfrontmatterと本段落の追記は指定SHAの後続記録であり、J5/J6の意味、正本7.3、契約7.7、P-6成立、製品計算コードの開始許可には拡張しない。現枝でT1を実行する唯一の計画を本書とし、[旧U-X1計画](../ux1-state-calc/plan.md)は2026-10-17承認済みの上位方針・T2以降の参照として保持する。旧計画のT1実行ステップを旧枝で重ねて実行しない。旧計画の全文・承認・レビュー実績を本書へ複製しない。

レビュー履歴は旧計画5周、TSK-544のP-8最小追補2周、J5/J6旧パス追補の採用反映2周、今回の採用反映1周で**通算10周**。J5/J6第1回はP0=1/P1=3、第2回はP0=1/P1=1を採用した。第3回P0限定は残存P0=1（旧計画のbranch/worktreeとT1枝の不一致）で、採用反映がないため周回数に加えない。今回許可された追加独立レビューはP0=0/P1=3/P2=0で否決。3件を採用した最終差分と、旧G6-S最終修正は**未再レビュー**。この追加レビューを7.3正本レビュー、契約候補2回のレビュー、P-6独立導出へ読み替えない。旧パスの未承認差分は保全パッチ（固定Git 8d51453df3ef528c0470623faac23983feff2fde:docs/features/tsk544-t1-state-calculation/old-j5-j6-unapproved-candidate.patch.b64、blob 97353bcac644a031b8ab8739f2c8055378e2173c）に保存した。正本・契約に反映済みとは扱わない。

## 1. 背景・目的

11/12の段階提供では本物のT1状況計算を用いて1球を記録・保存・再読込する。ADR-003 v0.8 D-14-m、要件書v2.15、[旧計画](../ux1-state-calc/plan.md)のT1/T2限定経過措置とP-1〜P-9を適用する。分析40行、D-2全体の発効、無条件の凍結解除は対象外。FR-040の直接補正導線は延期され、これを含む従来MVP全体の完成とは記録しない。NFR-018に従いTSK-538の単一TS計算核・同一JS artifactを利用し、手書きの別計算を置かない。

原典と候補: [旧設計](../ux1-state-calc/design.md)、T1入力・case候補（固定Git 7912b9c63e4b35a06fed667ee976cc8f91a4f457:docs/features/ux1-state-calc/tsk544-p8-candidates、tree d0a3593577a8aa7ed4448b2bf8a7a6666800173a）、J5/J6本文・型候補（固定Git aec6768cbd0089c61b1b2ad0a8382947fa561cdf:docs/features/ux1-state-calc/tsk544-p8-candidates/t1-j5-j6-decision-candidate.md、blob 8e3357852e098001a307699b17e4f1354f24b341）、P-6/P-7/P-8受渡し（固定Git 35a7f5761a105c77cbfee7820cf01ca2af84a37c:docs/features/ux1-state-calc/tsk544-p6-p7-p8-handoff.md、blob 10fc0962b844086d0bcdfee47f4597a9faa2c59b）。候補中の未裁定値は正式仕様ではない。

## 2. スコープ

本書はTSK-544の**T1のみ**を所有する。T1のP-8閉入力、23フラグ必要十分表、OUT3/RBI/G6-S/S20の規範行・case・負例、J5/J6の7.3候補、正式契約候補、独立P-6への入力と比較資料、P-7公開境界の受領、T1製品核・接続・検証を扱う。J1〜J6の採用済み方針を具体化するが、未提示のfield/意味/caseを承認済みとしない。

旧計画に残るのはT2/TSK-545、T3〜T6、FR-007/011の後続、分析40行、TSK-237、D-2の全体発効条件。T2の計画・所有・規範意味は変更しない。T1の共通descriptor変更がT2参照digestに及ぶ場合だけ、TSK-545所有側の受理を得て機械的に追随する。U-F8画面、U-S1同期適用、U-R1記録権、TSK-506 HTTP、P-6独立期待値の所有は移さない。FR-012の原子性と実Port接続を維持する。

## 3. 影響する正本・資産

| 対象 | 今回の計画作成差分 | 将来の反映と停止ゲート |
| --- | --- | --- |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **今回反映なし（旧正式反映の履歴は保持）** | v2.16のJ5のXC-13時点分界とJ6の付録A-1/E-1入力を2026-10-21のPO承認に基づき確定。契約の7.7は別ゲート |
| `docs/adr/ADR-003-domain-calc-method.md` | **今回反映なし（旧正式反映の履歴は保持）** | v0.9のD-11のT1限定検証時点を同じ7.3ゲートで確定。D-2全体は維持 |
| `docs/README.md` | **今回反映なし（旧正式反映の履歴は保持）** | v2.16/v0.9の確定を索引へ反映し、既存履歴を保持 |
| `docs/development/dev-harness-design-2026-08-07.md` | **反映なし** | 機構変更は予定しない |
| `contracts/state-transition/`、凍結履歴・署名 | **反映なし** | 正本確定後、T1行/case/schema/descriptor/負例・T2参照・派生資産の候補を作り、コアレビュー、所有側受理、7.7実値の人間確認後に正式反映 |
| `.claude/core-areas.json`、検査器 | **反映なし** | 検査緩和・例外追加はしない。必要な変更は別計画・ゲート |
| `docs/features/mvp-delegated-core-review/policy.json` | 今回PR186/head branch exact対だけを追加 | 今回MVP委任の既手続きで対象化。既対象・publisher・権限・期限・拒否条件は不変、最終HEADの独立レビュー後に公開証拠を掲載 |
| 本計画、旧パスの候補・作業ログ | T1実行計画を新設し、旧未承認追補を保全・整理 | 本計画の6.1レビューとPO計画承認。候補を正本とみなさない |

将来の契約反映時には、その**実差分**に合わせ本節を更新し、計画同期検査を再実行する。今回の正本確定は契約の7.7受理や将来の検査対象除外を意味しない。

## 4. 実装方針・停止点

1. 本計画の6.1レビューとPO承認は上記のとおり成立済み。J5/J6本文・型・直接影響する整合差分は別の7.3レビュー3回と2026-10-21のPO**正本本文承認**を経てv2.16/v0.9の`approved`へ確定した。第3回はP0限定、第2回P1採用反映は独立再レビュー未実施。正式契約の7.7実値受理や製品実装開始は別ゲート。
2. 正本確定後、T1 P-8正式契約差分、全ID/原典/入力/出力・拒否/負例、前後digest、7.7記録案を候補として固定する。共通descriptorのT2参照影響はTSK-545と直列調整する。**P-6段階Aの独立導出の固定結果と未検証範囲を受領してから**、コアレビュー・所有側受理・7.7実値の人間確認へ進む。どれか欠ければ正式資産へ反映しない。
3. P-6は現行109 caseのblind入力を先渡しし、独立導出・hash固定の後にID対応・比較射影を渡す。**段階Aの固定結果/未検証範囲受領 → 7.7実値確認 → 正式契約版での段階B比較・必要な未曝露再検証 → P-6担当と契約所有側による範囲/結果の受理**を順序として維持する。比較資料の受領だけでは段階A/P-6成立ではない。追加7件、005/007の打点観測不足、旧版への曝露は別残件であり109件の一部検証を全件成立としない。
4. P-7は着手前に公開型・同一イベント評価値・拒否順・配線責任をU-S1/U-F8/U-R1/506と項目別に受理する。実Portの完成SHA、実HTTP・隔離DB結合試験は**実装後・マージ前**のゲート。仮PortやHTTP独自の混在バッチ分割を作らない。
5. T1製品計算コードは本計画承認、P-1〜P-9の**T1対象別**条件、正式契約とP-6/P-7の着手前範囲が全成立した後にだけ開始する。正本確定だけで開始しない。実T1 source/artifact/manifest entry/製品入口/3層試験は製品ステップの成果物であり着手前へ循環させない。実HTTP/DB、FR-012同一transaction、再送、拒否、全取消はマージ前に実証する。

### 実装ステップ(コミット単位)

| # | ステップ(何を作るか) | 合格条件(検証方法) |
| --- | --- | --- |
| 1 | **T1正式契約の先行追随**。7.3確定後のJ5/J6とP-8閉入力・23フラグ・OUT3/RBI/G6-S/S20の規範行/case/負例を、契約schema/descriptor/hand-offへ反映。G6-S01〜S08は全IDを収録対象とし、S01/03/06は名簿・規則snapshot、S02/07/08はU-S1の拒否分類・snapshot公開型、S04/05は再開始と半回/アウト/カウントのPO/TSK-546判断を受けて固定する。S09〜S11は原典で保証されたD+1だけとし、他の履歴長は未裁定としてID別に残す。T2は共通参照値だけ所有側と直列追随し意味を変えない。 | G6-S01〜S08の全IDについて担当別受理、S09〜S11のD+1内の閉包、その他規範ID/未裁定IDの照合、T1/T2契約・派生/凍結履歴の関連検査、コアレビュー、所有側受理、7.7より前のP-6段階A固定結果/未検証範囲の受領、7.7完全前後値の人間確認。S01〜S08に未決が1件でもあればステップ未完了。承認前に正式資産へ書かない。 |
| 2 | **PR-1a T1状況判定の同一変更**。TSK-538基盤でTS正本と同一JS artifact、manifest entry、製品Port接続、両runner、3層検査を一対象一変更として完成する。FR-040延期を明示しT2を含めない。 | P-1〜P-9のT1対象別開始記録、全正式caseの両runner消費・独立期待値照合、descriptor exact-set/値域/digest、再現ビルド、3層検査、実HTTP/隔離DBの1球保存・再読込・再送1回適用・拒否・全取消。コアレビュー、CI、人間逐行確認とPRレビューを別途満たす。 |

## 5. DoD（TSK-544 T1受入基準）

- [x] **計画単位**: 旧未承認追補を保全し、現枝で本書を唯一のT1実行計画として認識する。計画同期の3失敗を差分と宣言の整合で解消し、6.1レビューの採否・未再レビュー差分を保持してPOから本書の最終承認を受けた（2026-10-20、対象SHAは冒頭）。
- [x] **正本単位**: J5/J6の最終本文・入力型・影響範囲を7.3で別審査し、POが2026-10-21に正本本文を明示承認した。FR-040延期、T2、分析40行、D-2全体、FR-012は維持する。第2回P1採用反映の独立再レビュー未実施を残余として保持する。
- [ ] **ステップ1**: T1の閉入力、23キー必要十分条件、OUT3/RBI/G6-S/S20の規範行/case/双方向負例と未裁定IDを逐行照合する。G6-S01〜S08は担当別全件受理、S09〜S11はD+1内のみ。schema/descriptor、T2共通参照値、両runner/handoff、凍結履歴/派生digest、既存全契約検査を揃え、独立コアレビュー・所有側受理・P-6段階Aの固定範囲/未検証範囲を記録する。7.7の完全な前後値と履歴追記を人間が受理するまで正式資産へ反映しない。
- [ ] **着手前**: P-1〜P-9をT1対象別に判定し、P-6段階Bの正式比較・必要な未曝露再検証と所有側の範囲/結果受理、P-7の公開型・同一イベント評価値・拒否順・配線責任の担当別受理を確認する。作成者自身の期待値確認を独立検証に数えない。
- [ ] **ステップ2**: T1の正本・派生物・製品呼出部・3層検査を同一変更へ収める。manifestには1論理directTargetId、source/generated/entrypoints、内容hash、vectors/properties/mutation、FR-040未採用を宣言する。両runnerが全正式caseを消費し、descriptor exact-set/値域/digest、製品入口と直接呼出しと期待値の比較、独立収集器、非等価変異生存0、片側出力改変のnegative checkを必須CIで確認する。実Port・実HTTP/隔離DBで1球保存/再読込、FR-012同一transaction、再送、閉鎖/失効/越境拒否、全取消をマージ前に実証する。コアレビューと人間逐行確認は実施した場合のみ記録する。

**現時点**: 計画承認とJ5/J6正本7.3確定は成立した。正式契約の7.7、P-2/P-6/P-7/P-8、U-S1原wire・codec版/順序保存、T2参照受理は未成立。実Port SHA/HTTP・DB証跡は実装後ゲート。T2、分析40行、D-2全体の条件は旧計画と別担当のまま。

## 6. テスト計画（NFR-019）

| 種別 | T1へ追加・追随する検査 | 実施時点 |
| --- | --- | --- |
| 一致性 (a) | 正式全caseをpytest/Vitest両runnerで消費し、期待値・製品入口・派生物の比較、descriptor射影、再現ビルドと3層を確認 | ステップ2とマージ前CI。P-6独立導出は別検証者 |
| 単体 | P-8閉入力、23キー、OUT3/RBI/G6-S/S20の正常/拒否・双方向負例、プロパティ層、変異層。未宣言field・同D5順序変更の拒否、取消再実行時の保存観測を検証 | ステップ1契約試験、ステップ2製品試験 |
| 越境 | 同一scope参照・別試合/別チームID、記録権閉鎖/失効、保存・投影の全取消 | 実Port接合後・マージ前の隔離DB |
| E2E | U-F8から実HTTPで1球送信し、DB保存・再読込・再送1回適用を確認 | 実装後・マージ前。U-F7キューは公開前の別ゲート |
| 故障系 | 前方確定/対象イベント取消、同期拒否、DB障害時ロールバック、再現ビルド不一致と契約版不一致 | 対象実装後・マージ前 |

計画段階では`feature_status.py`・`check_plan_docs_sync.py`・実装ラッパーの静的経路、計画/文書状態試験、差分検査を行う。`codex_run.py implement`が**未承認**を拒否するのは正常で、branch/worktree/ステップ表を別途機械照合する。計算の独立実装を作らず、自己照合を独立検証と数えない。

## 2026-10-25 操作単位での最小追補（PO委任承認済み）

### 委任・既承認との関係

POは2026-10-25の本Goalで「操作単位で必要な契約を成立させ、成立した操作から本体実装する順序への変更」を明示承認した。§4-5とDoD着手前の「T1全操作が全成立してから」の順序だけを本追補の操作単位に置き換える。元7d6ce544の本計画を同じpathへ再利用し、元ファイルSHA256 1361976b9061aa10dc2c5f00d97a1cb98b36395e48233d1f9b0c3f428422deda、既10計画反映/2確定ゲート・未再レビュー履歴を保持する。以後の実行枝はfeature/mvp-t1-first-pitch、契約追随PR185は別有限成果として維持。T1全体のDoD・全MVP・取消/訂正・NFR-018/019・必須CI/拒否条件は維持し、T2所有をT1へ吸収しない。

### 最初の操作と閉じた入力

初回表・0対0・0out・無走者・0ball/0strike・打順1・非TB・未終了の開始済み試合で、`eventKind=batting-result`、`resultId=batting-result.ball`、`pitchEventKind=pitch-event`を1球記録する。正式dcd4fda8のmatrixRows[3]とST-MATRIX-0529a0eb116d64a9を使用する。既caseの規範結果を変更しない。規則snapshot、同tenant/gameの開始済状態・名簿/打者/投手/守備側、正規化済入力・readonly参照の出所を閉じる。synthetic純入力は型/意味の検証だけで実issuer/認可/RG1証拠ではない。最初の公開能力はこの操作・状態範囲だけを明示し、他の結果/走者/終了/取消等を成功へfallbackしない。

型は既t1_out3_input_schema_v1.jsonと既4readonly、契約caseのinputCoordinate/historyInput.beforeを原典とする。単一TS核のJSON境界は整数を既decimalCodecの十進文字列へ正規化し、number/coercion/default/余剰field/欠落/未知enumを拒否する。新JSON入力/出力型のexact fieldとこの元型への写像を実装前の非作者確認へ渡す。結果はcountEffect/plateAppearanceEnded/batterDestination/runnerDefaultAdvance/outEffect/23statFlags、遷移後状態/scoreboard、確定履歴差分を完全比較する。既計算結果をサーバーへ手書きで複製しない。

### 操作単位の開始条件

- **U1 規範・型**: 対象行/case/入力型/23flag/状態・履歴比較面を固定。first-ballの既正式規範は実在。全13不足分岐やP7他操作markerは、この操作と共有安全性に依存するものだけを条件とし、一律に前提へ戻さない。
- **U2 独立検証**: pure-packet-v1（manifest18d6004eb3e56c28a5adf668259291f38c1cef657ef2ee35a65789066f3390e0）の純入力とprimary規範だけを新fork none検証者へ渡し、導出結果/読取履歴/hashを先にsealしてから正式case/作者期待値と比較する。新agentだけで未曝露資格を成立扱いにせず、過去P6の資格/曝露/封印と別に範囲受理する。
- **U3 基盤と境界**: TSK538の既NodeDomainHost/単一IIFE/decimalCodec/両runner/build/構成検査基盤を再利用する。P7はこの通常P1プレイに必要な固定before/payload/context/roster/結果型/配線責任を型と役割で受理する。実Port/DB/HTTPの完成は数学核sourceの着手条件に足さず、後述の実経路完了ゲートで必須とする。
- **U4 本追補承認**: 非作者の有限計画確認とPO委任root判断を、対象版/hash/日時/根拠で記録する。U1〜U4が揃った範囲から、旧ステップ2の一球単位として数学核を実装する。未充足項目を受理済みにせず、未充足に依存しない部品と実接合準備は並行可能。

### T2・保存投影と拒否の境界

T1の純計算と、T2を含む製品保存の成立を分ける。正式T2の6outcomeには初回通常プレイの「非該当」外形がまだ無く、この1球の終了条件不成立をschema外no-decision/固定falseで代用しない。T2所有側の既計画・E11/E07/既方針を照合し、初回通常継続の選択/非該当の型・根拠・実評価を最小接続依存として別途閉じる。T1数学核はT2結果を生成しないためその実装を独立して進め、実API保存の成功はT2境界成立後に実証する。T2全体の実装・完了をT1へ混ぜない。

保存は既U-S1単一適用核とPortWriterの同一transactionのみを使い、event/状態差分/投影/成績根拠/無効化意図/D5確定の不可分性を保持する。投影に必要な選手/出場/投手責任・行47/55等の物理保存型を実sourceへ照合する。新たなコピー計算やno-op projection/常時許可validator/rightsを置かない。実認証・C2/tenant・初期記録権・D4/V12・RG1が必須。既認可/再送照合/連番/内容/状態/O4の順とD06を維持する。未実装操作は公開能力外として成功応答を禁止し、内部unsupportedを既取引故障/結果照会の契約へ接合する。新しい公開拒否ID/D5消費規則を仮に作らず、全取消が確認できないときはD5未消費や置換可能とみなさない。

### 一球単位の編集範囲と実装・検査

まず本計画の追補だけをレビューする。数学核候補の予定sourceはfrontend/src/domain/{state.ts,stateRules.ts,stateTypes.ts,publicApi.ts}、同domainのunit/artifact試験、既frontend/scripts/domain-build/とfrontend/public/domainの再現生成物、backendの既domainrt host/runner接続試験。spike8e1bf431の該当TS計算/型/codecを選別再利用し、spike_domain Python/SpikeRights/仮Projection/常時成功validatorは採用しない。scopeにない結果を公開して後続完成とみなさない。型写像の有限案を非作者確認後、必要な既sourceの最小改訂だけを宣言して実装する。契約/manifest/登録・Port・API/画面の具体pathは実接合前にこの同じ追補へexact指定し、共有編集はrootへ一本化する。

この単位の実装順は、型/独立期待値の確認→単一TS核/同artifactと両hostの実検査→本物のT2/validation/projection Port接合→画面で新規作成/開始/一球入力/実DB保存/再読込。同操作の拒否・越境・権利失効・原子性故障・同D5再送1回適用・結果不明照会を実行し、未送信/確定を区別する。作業中は影響検査、統合候補で全必須CI/最終HEAD独立レビュー/委任証拠を完了。既phase2/core_guard/BOOTの対象検出や拒否を緩めず、T1全targetの完了や3層成立は全範囲が揃った時だけ記録する。部分実装が既mandatory CIを通せない場合はDraft/隔離実証として保存し、成功へ読み替えず必要な同一T1変更の残りを完成させる。

旧DoDの全操作/23flag/OUT3/RBI/G6/取消、成績/CSV・通信断耐久/担当交代/実機/復旧は引き続き完成対象。親計画以外の新しい全体計画を作らず、進行・固定版・証拠・残依存は既主台帳へ集約する。

2026-10-25T14:08:54.565473+00:00、Codex rootは今回PO指示と既委任4/5/8/10に基づき本操作単位追補を承認。対象草案SHA16c3f920f5bad37719a4c9c1553f298634f833e98080124e1ff83175a37ad3c2、非作者review7e649891b3eeef34cd3fa1014575170f8e13e8bed102c31b418cd290ff64164b/evidence744557226d6e6b5b0488c02d90a985411f785d62b58d45802baaff704f6de055、計画指摘0。新JSON境界の出力不足/整数終端の指摘2件は型案reflection2 b03e9d697c89f6ceb6d4c91fd5af047ea1f20da16c5ef7436d9cef096015c2aeへ採用し同非作者確認残0。境界の完全型案を同dir first-pitch-boundary.jsonへそのまま保存する（規範計算の別実装ではなくABI宣言）。この計画承認でU4のみを閉じ、U1の型受領・U2の限定独立結果受理・U3の役割/基盤確認の実記録は別途必要。本文の未充足を実装開始済みとはせず、人間本人の確認/全T1/P6/P7/実保存を代記しない。

2026-10-25T14:12:08.187229+00:00、rootはU1〜U4を数学核の操作単位に限定して受理し、最初のballの本体source実装開始を許可。開始receipt SHAba6b37151029e3e781e722e44d5a4bb0d5ee4eb266fbeaffefc142c4475fc479、この1球の既規範/型・独立意味確認＋曝露後の既採用row一致・基盤19成功・担当責務を固定した。独立結果はstrict primary unknown/条件付き解釈の留保を保持する通常の独立整合として受領し、厳密blind資格/全P6へ昇格しない。絶対board/全stack/wire/認可/実保存は未知を埋めず、数学核は実入力boardを保持し一deltaだけ返す。サーバ側は公式選手の通常P1/registration=None/order_resolver=Noneに限定し、別SyncEventへ変換されるためobject identity一致で拒否せず、既canonical原本と検証時before/context/prefix・同writerへ束縛する責務を受ける。T2/実Port/実保存の未供給は数学source開始へ前倒しせず、実経路の必須未達として残す。新sourceと公開入口の拒否/品質検査はこれから行い、T1全体や実画面経路を完了扱いにしない。

2026-10-25T14:14:27.402045+00:00、非作者はU2/U3の有限責務と限定独立意味確認を追加確認し残指摘0（review42b81cd912a70cd4998d06ad586ba3f96c464c6f5dfba71e53ea2ccaaed9b8a1/evidence8167ded155928a37d2b7356bae853ad2aa8ccb4ee82f5c9b00b605707d3fa21b、28局所照合）。rootは前記開始receiptの限定範囲をこの最終証拠で確認した。ここから単一TS数学核のsource実装に移る。実接合の未達は保持する。

2026-10-25T14:30:28.570347+00:00、最初の数学核候補のexact source/試験/生成物は以下9path: frontend/src/domain/stateTypes.ts, frontend/src/domain/stateRules.ts, frontend/src/domain/state.ts, frontend/src/domain/publicApi.ts, frontend/src/domain/publicApi.spec.ts, frontend/src/domain/firstPitchArtifact.spec.ts, frontend/public/domain/pitchlog-domain.js, frontend/public/domain/pitchlog-domain.json, backend/tests/domainrt/test_first_pitch.py。sourceの式はspike型/ball規則/23flag初期化/JSON整形を選別再利用し、private導出は未対応scopeをnull、公開JSONは非成功errorとして返す。既ASTが認めない添字構文はsource側を許可済みのown entry走査へ是正し、checker/policy/拒否を変更しない。同artifact c420afc9949f4c52f2b188ccb81ac1a103f9eb78b2f9affc38c1348d38487b15/6973byteの再現build、frontend75/Node host2、実headless Chromiumの全値一致/未対応拒否、型lintを確認。これは数学核候補の検査であり実開始/保存/全T1/必須CIの成立ではない。候補をcommit固定し非作者source確認へ渡す。

2026-10-25T14:45:00.340633+00:00、数学核source2c63255fの独立初回レビューはP0=0/P1=1/P2=0（evidencefe9ad17ddfe8b9537fd1357f9e7154121235b8fa1ac81bd6fdb7ea46785db83a）。閉じた4error enumに無いINVALID_STATEが出る指摘を採用し、新codeを追加せず既INVALID_REQUESTへ是正。実NodeHost応答の承認schema検査、4不正型回帰、既hostの数値JSON先行拒否も明示検査に追加した。計算式/成功結果/既AST拒否/型宣言は不変。新artifact28d07c5c52fc08aebbf84bf0105368708cd7d14367a112e1b913d83177b4312d/6975byteを同実headless browserで全値一致確認。初回75/21/型lint/再現hashと422不正全非成功の独立結果は旧版証拠として保持し、反映差分だけの再確認へ進む。

2026-10-25T14:59:40.711894+00:00、rootは既ステップ2の一球単位を製品サーバ側の型付き呼出部品へ進める。有限追加pathはbackend/src/pitchlog/domainrt/first_pitch.pyとbackend/tests/domainrt/test_first_pitch_adapter.pyだけ。既open_domain_host固定製品root/Node版/hash/寿命制限を再利用し、数学式をPythonへ複製せず同deriveStateを呼ぶ。入出力は受理済b03e9d69の閉型/十進整数/23flag/after/一deltaを厳格に束縛し、未知code/余分field/欠落/不正整数をプロトコル違反として拒否、unsupportedは非成功のまま返す。docs/features/作者case期待値を製品runtimeの入力にしない。新認可/記録権/同TX保存をこの数学接続部品が提供したとはみなさない。実hostを使う正例とdecoder故障系を区別して検査し、別非作者レビュー後に正式接合する。既U1〜U4で閉じた型/意味の同一実装への接続具体化としてPO委任により承認、別の開始承認待ちは作らない。

2026-10-26 JST、数学核796cd89c（2c63255fからの差分SHA bf15f305f5bcf2143c3ab7792dc5788f03a5b2bee0a31e21d20c011b83225eb9）の反映差分を非作者creation_pathが確認。evidence de56668d8b27946bc1af6df87ec7c6990983a9b4490f7cd08036bc8e1f0341e1、review741d685f2d779193c4a27d90e4a4ece001bc3a69fb697fc4c647ff3d1cc57c17、P0/P1/P2=0。422不正要求全非成功/既4code schema一致、NodeHost既拒否保持、artifact同hash再現を確認した。rootはPO委任によるCodex判断としてこの有限数学sourceを受理、通常push済み。root全frontend93file/1923成功99.38sも別確認。これは親全体DoD・開始/実保存の受入ではない。creation_pathは次のPython adapter2path作者へ役割変更し、そのsourceの最終レビューは別非作者へ割り当てる。

2026-10-26 JST、サーバ型adapter2pathの作者creation_pathはhandoff aa64dde3a88b088b6e129ff01abbc22e4760c2e4a4242dc323cf1909f922073dで編集停止。別非作者t1_remaining_out3_casesの最終evidence0ecfe615c24f6c927ef3f7c4c5bcf8b10e30b68f9cee19203b7edb073101cf4e/reviewc09a4c0b88e2d2f7d5bd068dc440f38ca88b30f4d8aa9f3e4f78d669901c7a6bはP0/P1/P2=0、最終固定版全208成功3.40s・Ruff/ty成功。rootはsource8e5e5b144aa530ac7d972dd94054ba2660e1bb7522c5864a29c449b34350f5e4/test9c42221945bc0a51a579a8a5a955b5128a78321994194dd61998c193f056f827を実hash照合し、PO委任によるCodex判断で当該有限部品を受理・接合する。既math source9不変。実固定Node正例1/未対応5とdecoder故障unitを区別し、T2・認可・初期由来・同TX保存・UI/API/DB・全CIの成立を主張しない。

2026-10-26 JST、新T2 callerの故障試験が既decode_first_pitch_responseにもstateFields/state_fieldsの二重配置を受理して余剰名を落とす挙動を再現した。閉ABIの不足検査でありrootは通常不具合修正として、backend/src/pitchlog/domainrt/first_pitch.pyとbackend/tests/domainrt/test_first_pitch_adapter.pyの2pathだけを有限是正する。JSON重複/nonfinite先拒否・strict/alias-only検証に加え、入力wire objectとalias付きJSON-mode dumpの全構造同値を要求して黙った正規化/余剰名脱落を拒否する。正規成功値・既4code・DTO構築API・math source/artifactを変えず、bool/int同値は既exact bool/strictを維持する。cache verify-first-pitch-alias-920191f3で作者creation_pathが2pathだけ実装、別非作者差分確認・既NodeHostの正例/故障/旧208等を検査してrootが接合する。T2 branchの既first_pitch.pyはauthor作業中に変更せず、後続dependency追随で直列反映する。PO委任によるCodex /root判断で承認。旧レビューの0/208成功と、この後発反例を両方保持し、過去検査が二重aliasも検証済みだったとはしない。

2026-10-26 JST、前記二重alias是正は作者handoff77a24dd82f8c5b2b4093c55ffa217a86a2e72bac34807dfd7dfd5679c74d00aaで固定。旧sourceで8失敗/40成功を再現した後、parsed wireとstrict alias JSON dumpの構造同値を追加した。別非作者out3のevidence59f16acf7c739ee7df0b842c44611368308a0c3e4628b01fba98eeaf6b06ad08/review54d8d6c75a45a922c42cc91ae71085a340fd7c4e20a37bd79c2f71ad792ffc5aは指摘0、独立旧208＋新48=256成功4.21s。旧29source定義/20test helper/DTO構築/4code/host/math/artifact不変、member順/ASCII escapeの意味同一受理とbool-int拒否も確認。rootはsourceafa6e21ac9cc3cce8877a57ac593596dbe3de8504e949d64eccf46ed315f9e20/test496172b26ed7de79314e4c6f6d4df40377d77b4f73439155859194b71a90a443を実SHA照合しPO委任受理する。旧0/208で未検出だった履歴は保持し、API/DB保存の達成へ広げない。


## 2026-10-26 初球数学部品のDraft提出単位

2026-10-25T20:05:34.568863+00:00、PO委任によるCodex判断（Codex /root）として、今回の提出状態in-reviewは最初のball数学核/同artifact/型付き固定host callerにだけ適用する。親TSK-544全体のステップ1/2・DoDやHTTP/DBマージ前義務は未完のまま維持する。後続実装時は同じ唯一の親計画をactiveへ戻し、既10周/2確定ゲート/後発レビューと未充足を保持する。新しいT1全体計画は作らない。

今回の実差分は数学/adapter/試験/生成物11pathと本計画/first-pitch-boundary.jsonの2pathのみ。§3の旧正本反映は過去の成立履歴であり、今回requirements/ADR/README/contracts/core定義を変更しない。未収録の旧候補4参照は実在Git blob/treeへ固定し、内容の新受理/全差分移植をせず参照可能性だけを回復する。

first-ballの成功と未対応拒否/alias重複拒否を実Node/同hash Chromium/単一TS実装で検証済み。公式develop30f67へ追随した5478b8c3で数学11pathとST-MATRIX-0529a0eb116d64a9全値不変、backend domainrt全256成功3.91s。既frontend1923成功と独立237成功は別実行・対象として記録する。Draft提出は計算部品の公開と必須検査・レビューを進めるためであり、実DBを事前投入した実証/認可迂回/仮成功を含まない。

今回の局所締めで§4 PR1aおよび実経路の実認証/初期記録権/T2/Port/原子的保存/再送/結果不明/画面再読込のマージ前義務を削除しない。満たす前はDraftのまま保持する。全T1/全P6/P7/P8/MVP完成、本人逐行確認・署名を代記しない。委任policyへ対象PRを追加する場合は実PR番号/head branchのexact対のみ、既対象/拒否条件を保持し独立確認後に公開証拠を記録する。

2026-10-25T20:07:32.941337+00:00、実製品差分を持つDraft PR186（feature/mvp-t1-first-pitch）を公開。PO委任によるCodex /root判断で、既policyのtargets末尾へこのexact対1件だけを追記する。ポリシー本文/既11対象/検査拒否条件/人間欄を変更しない。全最終差分へ含め非作者確認・対象HEAD証拠を取得する。Draft/マージ前の実HTTP/DB未達は保持する。

2026-10-25T20:52:13.433380+00:00、CI40229702557はbackend/frontend成功、core-guardの公開JSON形式是正後の限定再実行も成功。harnessは30241成功/1失敗/2skipで失敗確定。既test_t1_append_later_policy_target_append_keeps_record_frozenが試験用PR186を固定しており、本PR186対象追加と重複して実loaderが正しく拒否した。rootはPO委任の通常試験入力追随としてtests/test_human_review_signature.pyの後続合成event番号をfixtureの既targets最大値+1へ定め、追記先も同じ合成event番号/branchに束縛する。全旧policy/record/期待文/拒否assertと製品checkerは保持する。本1pathだけを追加scopeとし、最終差分レビュー/当該module/CIを再固定する。親全T1のDoDと実HTTP/DBマージ前義務は維持。修正開始のため本提出状態だけactiveへ戻し、全DoD完成や同意味の再承認は主張しない。

2026-10-25T20:59:20.720890+00:00、上記fixture番号の通常是正後、正規stock tests/test_human_review_signature.py全131成功36.18s、Ruff/ty成功。合成後続番号はfixtureの既登録最大値+1で一意、policyへの追加も同event.number/head_branchを使う。期待文/record bytes不変assert・既policy拒否・製品checkerは変更0。今回数学提出だけin-reviewへ戻し、最終HEADの非作者差分確認と必須CIは別途必要。旧harness1失敗/30241成功/2skipを新全件成功に改記しない。


## 2026-10-26 通常非PA投球33の操作単位追補

既親544の旧step2内の次単位。基線は正式30f67＋既初球256838cc依存merge済みの942c5783edae8ad859a3363e87dfb60c033f6f13（feature/mvp-t1-ordinary-pitches）。新全体計画を作らず、本追補採用後は同じ親をactiveへ戻す。旧10計画周/2確定ゲート、初球Draft/レビュー/失敗、既全MVP義務を保持する。本候補作成者t2_first_pitch_plan_reviewは新blind導出者でも最終非作者plan reviewerでもない。

### 1. 閉じる範囲と既規範

ballはS0..2×B0..2の9、called/swinging/foulはS0..1×B0..3の各8、合計33。初回表/O0/空塁/0対0/打順1/TBfalse/未終了/既before・board全0の範囲は初球と同じで、B/Sだけを広げる。scoreboard等の欠損を0生成しない。S2foul4、第3strike、第4ball、PA終端、走者/打順/次回、6未被覆、HR矛盾は個別留保し成功へfallbackしない。MVPから除外する意味ではない。

差分/confirmed-play/pushはADR-003 D-8:433・要件E-1:1573の既決事項。変化したstate/board fieldだけのbefore/afterと23flag全値からconfirmed-play1件を先頭へ積む。新ADR/野球意味の裁定は不要。旧4代表の6効果/23flag/入力/期待値/history全値を保持し、finite guardへの正式拡張だけを受理する。

### 2. 最初の閉包：正式norm・参照・ABI（製品核着手前）

(1) 既matrix4行のB/S eq葉を上記finite inへ変更し、natural row ID/49行/効果/remarksを保持。mustOperationCoverageとbranch mapping4参照を追随。29norm行や29正式caseの重複追加はしない。既104caseは全object同値、残12caseはcase-id-mapによりID/rowRefだけ明示移行しinputCoordinate/expected/historyInput/raw/normalized等を全値保持。coverageのB1一件だけ追加して116→117、新caseはST-COVERAGE-8d5c59594f90b5bd。history lookup脱落をmain4-exact-bindingで閉じる。

(2) authorに許すsourceは既check_required_set_coverage.pyと既testだけ。既eq意味を保持し、finite inで陽に束縛されたstate値の到達可能性を既predicate評価で導く。in値setの等値扱い、無関係operationの自由値、入力expectedから不足を埋める処理は拒否。旧history/baselineCaseIdsのbyteを書換えず、下記派生vector資産の明示12ID移行情報を使って旧→現caseの同値/一意な到達を検証する（欠落/重複/別row/入力・期待・history片側変更を拒否）。これは履歴参照の移行であり、旧承認を新subjectの承認へ流用しない。

(3) required-set coverage実集合176→177、追加(state.count.balls,1)だけ・削除0を実consumerから再導出。旧history/currentStep95までをprefix同値保持し、最終全値と新step96候補をrootが実値で受理後appendする。根拠値はacceptance-delta.json/元candidateに保持。実受理日時/承認欄はrootだけが埋め、仮承認でgreenにしない。game_end宣言件数116→117、handoffのraw SHA、checker変更で実際に影響する派生値だけを同batchで追随する。

(4) contracts配下へordinary専用request/response schema・readonly d.ts・33全値vectorsを新設。vectorsは4正式rowへのexact binding、旧4代表の全値一致、12ID移行情報、33空stack全値＋履歴tail保持1対向を含む。正式規範は(1)の4行であり、vectorを規範の代用品としない。既history型のkind/差分閉構造/十進整数を参照して実ABIを確定し、旧作者schemaのhistory欠落/request exact4/response singletonをそのまま採用しない。

(5) rootだけがshadow候補JSON・既生成CLIによる全前後測定・非作者の有限規範/全値/履歴参照確認を受け、7.7/新subjectを通常ゲートで実受理する。state subject候補a8fb88…→ec26ae…、coverage digest df2215…→bff28a…は未受理値であり最終checker差分から再測定する。旧PR185 RBI5限定Gate6署名・carry・P6封印を新subjectへ使わない。descriptor f479/criteria/manualfixture2射影が不変なら、それらの再設計や新凍結履歴を増やさない。新subject受理に既一般ゲートで不足する具体pathが判明した場合はその差分だけrootへ戻し、旧RBI5専用拒否を緩めない。

### 3. 新ABIと単一実装

新公開operationはT1-onlyのderiveOrdinaryPitch。入力は旧4field＋必須 history:{stack:[HistoryEntry,...]}（空配列可、欠損の[]補完不可）。before/履歴は閉型・canonical decimal/bigint・nested closedで検証してsnapshot化。履歴の型検証は真正性/全過去操作再計算を保証しない。独自の切捨て深さ上限を加えない。

成功は旧8member相当の新ordinary値。ball/strikeのcountEffect・after・23flag全値、historyContext=[newConfirmedEntry,...input.history.stack]。newentryは同一T1評価の実before/after/flagsから一回生成し、tail全内容/順序を防御的に保持する。初球deriveState/FirstPitchRequest/Value/4error/対応scopeは完全不変。新操作も既4errorを使用し、型不正とscope外を閉じ、固定case-ID成功/期待値lookup・Pythonコピー式を作らない。

state.tsのprivate count核を共有して既ball/newordinaryを評価し、二重計算を避ける。public側の履歴構成も一箇所。spike41d7175dの変化field差分/23flags方式だけを既規範に照合して移植し、未知key無視parser・広い操作表・Pythonspike・仮rights/projectionは輸入しない。既decimalCodec/entry/build/AST・構成checker/hostを再利用し拒否を緩めない。

Python新callerは固定open_domain_host()で新literal operation1call、strict/frozen/alias-only/duplicate/nonfinite/全wire-dump一致を再利用し、historyの差分/pushやcount式を計算しない。既first_pitch.py/hostは変更しない。

T2 continuation候補ed07と198組は本WTに無く今回依存merge/実装しない。旧T2候補・既6outcomeは不変。本T1値から実保存へ接ぐ前に、同before/Derivedで一回T1→T2を評価するT2所有側の有限追補を必須とする。未評価T2を固定false/no-decision/保存成功へ補完しない。

### 4. exact編集と最小順序

exactpaths.jsonが唯一の許可候補。rootはparent plan/contracts/append/正式参照/Git/台帳のみwriter。authorは隔離WTのchecker2と数学12pathだけを指示された段階で編集する。新schema/vecをauthorが正式共有へ直接書かず、shadow/cache候補をrootへ渡す。

| 単位 | 実装/受理 | 解除条件 |
| --- | --- | --- |
| A | shadow4guard/12ID/117case/coverage177、checker finite-in・履歴移行、ordinary ABI/33vec | 既4全値保持・有限規範とABIの非作者確認、実全前後集合/subject/必要consumer値のroot受理。旧P6比較は数学射影だけとして資格受理 |
| B | 単一TS/privatecount/public/同artifact＋Python固定caller/両runner | Aの成立範囲からsource着手。33全値＋tail1/反例、旧ABI全回帰、再現hash/実Node・同artifactブラウザ、型lint、別非作者source確認 |

履歴tail対向は初球calledの実entry Hと実after(S1B0)を使い、ballへhistory.stack=[H]を渡してS1B1/history=[Eball,H]を完全比較。H欠落/切捨て/逆順/flag差替え/後発入力変更混入、history欠落/unknownkey/非canonical、B3ball/S2strikes/S2foul/PA/走者/未知/他before、旧firstballが新たに成功しない負例を含む。33数学と旧代表4/新tailの比較資格を記録し、新blind/fullP6・wire/auth/save成立へ昇格しない。

### 5. 旧mergeゲート・未完の保持

本追補は親§4 PR1a/DoDを削除しない。実認証/C2/tenant/初期由来/記録権D4/V12/RG1/T2/同writer projection+D5/再送/unknown/実HTTP・画面保存再読込はmerge前の後続必須。全Port/全T1/全P6を数学source開始の前提へ戻さず、未実装をsuccessにしない。承認後も全T1/取消/成績/CSV/実機/復旧/MVP未完を保持する。

§3の今回宣言は親planとexact contracts/checker/数学sourceだけへ更新し、requirements/ADR/README本文反映なし（旧履歴保持）。新branchの公開/委任policy exactPR対/最終HEAD証拠/必須CIはrootが実PR確定後に通常手続きで行う。ここでは実PR/承認日時/署名を創作しない。


2026-10-26T07:44:31.048361+00:00、PO委任によるCodex判断（Codex /root）。対象追補案SHA f430dd51c404e80b333cc62e8c18e2794e51a76933585fa41ef66975096b929f、exactpaths SHA bd01d015ecfdbdadcfef1b0250a7180c29cf411519eaecf87805f506ff1b18f7、非作者限定計画review ca35fbd3cedf13a7382bc4ca4183cb289b4d079f799a86ef274c4e5209ec443f（未解消0）を根拠に追補の範囲・順序を承認する。人間本人の個別実値確認・署名ではない。単位Aのchecker2pathとcache内ABI/正式値候補作成だけの開始を許可し、正式契約/append/Git/本planはrootだけが編集する。単位Aの実受理前に単位Bの数学本体sourceへ進まない。旧全T1/実HTTP・原子保存のmerge義務・MVP全機能を維持する。


2026-10-26T08:10:10.222884+00:00、通常33の単位Aで実consumer check_branch_row_mapping.py:710が旧eq/and/or/notのみを解釈し、正式拡張候補のfinite-in葉を「規範行の述語引数が不正」として拒否する実影響を確認した。PO委任によるCodex /root判断で、同単位Aへ scripts/check_branch_row_mapping.py / tests/test_branch_row_mapping.py の既2pathだけを追加する。inはexact keys{op,axisId,values}・既知fixture座標axis・非空配列・重複なし・型一致membershipに限定し、旧eq/and/or/not/未知op・不正args拒否を保持。bool/intの同値化や期待値による穴埋めは拒否する。有限inの0/1正例・2非該当、missingaxis/empty/nonlist/duplicate/extra/bool-int異型の対向と実shadow4参照/旧全moduleを検査する。正式JSON/履歴/署名/判定基準の緩和はしない。作者t2はこの追加2のbeforeSHAを固定して着手でき、最終差分は別非作者へ渡す。数学本体12pathは単位A実受理前には変更しない。


2026-10-26T09:56:37.383765+00:00、PO委任によるCodex /root判断で通常33単位Aのconsumer source4だけを採用保存する。作者t2のhandoff012e2d1235ab54cc9b424283b064caff1ef65e8b6da446f5be517d651fc99a17/最終source4 e7e3df…、別作者rg1の後発test1 a130f480…/delta0f3df282…を追跡し、非作者初回123d2857690ca6b4c1dcae8d7fa3ef121b0455e2695317ffc9d29d89345c7d7b（0/0/1）→反映1最終4dbedd593c1805b6ab6b5a71124a480310c2fd762b4cf9f1d8da9cf9e1f6280c/checks4eb34293006a30bb3a8ac1eb81ac22b51c82a4597f81364c1773def7b195e306（残0）を照合した。旧93test全AST/decorator/assert保持、歴史copyは固定Git treeに閉じ、新vector混入拒否2対向を追加。旧4assertの新117側混在を歴史fixtureへ束縛して解消し、新current33/117/177対向を別に保持した。

旧live164成功71.52sは現117検査の証明ではなかった。初回shadow全164は159成功5失敗65.76s（旧4不整合＋空承認1の正当拒否）、反映1限定live25成功/shadow24成功1正当拒否、独立24成功6.13sを別実行として保持。branch module29/33+tail schema/全12ID/104保持/coverage177/ec26 subjectは別非作者で実導出照合した。新承認3欄はまだnullで、署名・凍結・7.7の受理済みを意味しない。保存はsource4＋planのみ、正式9/履歴/旧署名/数学12は変更しない。

現PR185/RBI5限定Gate6は新33 subjectを正しく拒否する。旧記録・本人署名を付け替えず、今回実PRに限る追加手続きの最小候補を作成中で、非作者初回0/1/0（新ready後のlocal技術分岐と統合後の不変継承の具体化不足）を採用した反映案がある。最終計画採否・実PR確定・新subject/ABI全値のroot受理が残り、単位A全成立/数学開始とはしない。全Port/全T1/全P6の完成を追加前提に戻さず、この操作の残手続きだけを閉じる。


2026-10-26T10:13:14.239412+00:00、PO委任によるCodex /root判断で通常33の正式9資産候補を当該枝へ反映し、被覆step96の実値採否を記録する。source4の最終独立4dbedd59…、正式9/全前後値の独立123d2857…/complete-values58b05967634a3ba8fac90b02bf4eac7d651358529a3cb3620ca42ad9eacc4a37を根拠とする。前176→177、追加(state.count.balls,1)だけ/削除0、旧17履歴prefix・旧baselineCaseIds・旧104case全object/12caseの期待値と履歴を保持。変更は4有限guard/12ID参照移行/新case1/必須stackを持つABI4と派生参照であり、他配置/得点意味/P6全成立を採用しない。3承認欄へ実JST日付2026-10-26/実判断者Codexを記録し、旧空欄の正当拒否と8他資産同byteを維持する。全9実before/after SHAはcache root-formal9-reflection/receipt.jsonへ固定する。

この反映/step96実値採否は新Gate6公開受理・最終CI成功ではない。旧185は今回subjectを正しく拒否し、旧署名・旧recordは保持したままである。後続限定Gate6手続きを次の通り承認する。候補原案3d8d24…→反映1 dbfc1de511fd3e83f000373f0ba160ce069a1b6fd90fbdb424f003a5055d84f0、非作者初回47f4127d…（0/1/0）→最終fa1a8b6c5429412ead091d5dfa90bdeb4c2518cf56884694cfec243ea84324cb/checksdea4be577c4a32064b7519c686feea748c3fa1c2999b4194b4773796dde22abf（残0）。

## 通常33の限定Gate6手続き追補（PO委任承認）

exact追加6はscripts/check_human_review_signature.py、tests/test_human_review_signature.py、新contracts/state-transition/gate6_t1_ordinary_pitch_v1.jsonとgate6_t1_ordinary_pitch_schema_v1.json、docs/features/mvp-delegated-core-review/policy.json、当該親planだけ。既一般core_guard/workflow/正本/署名keyは変更0。旧185record/schema/本人署名/sheet/carry/policy原本は固定30f67 anchorで既同validator bodyにより検証し、型/拒否本体を複製・省略しない。必要private固定readerだけを注入し、CLI/record任意revision選択や旧コードcheckout/execは禁止する。

新record/schemaは今回feature/mvp-t1-ordinary-pitchesの**取得した実PR**にだけ束縛する。placeholder/null/番号創作を拒否。rootはsource4/正式9実差分のDraftを公開後actual番号を固定し、現policyへ既targets全prefix/全fieldを保持した末尾exact1だけ追記する。新checker/test作者はt2を予定し、実PR後のroot具体通知で着手する。新record/schema/正式9/現policy/親plan/Git/台帳はrootのみwriter、作者はcache候補を供給できる。

有限bodyは旧185同bodyの固定検証後、4guard B/Sのexact有限集合・他45row/4row出力/23flag/他guard不変、旧104全object/12IDmap/期待値とhistory全保持/新case1だけを再構成しsubject全体を比較する。schemaと固定全値から新ABI4/33vector/必須history.stack/全tail保持/派生5・coverage177/旧17prefix＋step96/normal248/descriptor等の不変を検査する。任意hash自己申告・余分case/field/row/axis・型同値化を拒否する。旧RBI署名を新subjectの承認へ付替えない。人間本人確認/P6全成立/P7全成立/T1BodyStartComplete等はfalseの限定scopeReceiptへ固定する。

3modeを接続する。A local --gate6-carryは新2asset片方でも存在すれば両方readyと実番号を必須に技術bodyを検査し、fetch0/公開委任未確認/新受理なしの文言でのみ0終了する。B今回actualPR --ciはrepo/branch/番号/base/head/checkout同tree・validator最終blob・既公開委任証拠/非作者/重大指摘0を全必須とし、不正BからC又は旧経路へfallbackしない。C統合後の他PRはcurrent記録より先にevent.baseの新record/schema/9資産と旧固定入力を読み、raw全同値を要求してから旧185固定同body＋有限bodyを検査する。fetch0/新受理なしで、連動書換え/削除/base偽装/pending/dirty・非同treeを拒否し、後続PR自体の通常core/独立/CIは免除しない。両base/currentに新2assetが無い旧treeだけは既経路を保持する。

実Git/公開CLIでA/B/C正例と前記全拒否、旧185全負例を確認する。最終HEAD/diff/path/現policy hashは自己参照recordへ入れず既PO-DELEGATION-EVIDENCEの実コメントで検査する。正式反映後のraw hashはroot実値を使い、旧cacheの空3欄版hashを偽採用しない。独立最終source/実値確認・公開Gate6/必須CIの未達は未達のまま保存し、単位B数学の着手判断と全T1/実HTTP・保存mergeゲートを混同しない。


2026-10-26T10:20:13.100731+00:00、実Draft PR187 https://github.com/masaki1025/pitchlog/pull/187 をfeature/mvp-t1-ordinary-pitches HEADfe4590ed0d3bb1074ed626b56dee5df713c1258fで公開した。source4/正式9と初球PR186依存の実コード差分を含み、番号だけの文書PRではない。root実反映後の被覆/branch全195成功74.19s（session46502exit0）、公開Gate6は旧185専用なのでまだ成功ではない。PO委任によるCodex /root判断で対象実番号187/branchを新手続きに固定し、作者t2のchecker/test exact2path着手を許可する。record/schema候補はcacheへ供給し正式2asset/現policy187末尾1/Git/planはrootだけが編集する。既186target/全旧prefixを保持し、PR186又は他PRを新187として受理しない。数学12はこの単位の限定条件成立前には進めない。


2026-10-26T10:48:38.191039+00:00、PO委任によるCodex /root判断でGate6 source2と新record/schema/現policy187末尾1を限定採用する。作者handoff ef84b19b7378bd62bae17e4696132746fb796cf0b2d680f69e430603b57cabed、非作者最終c1808081d5ce07bb5d76b12825af6d9c2d9812f65060e34f02446080f7e60830/checks43bb70fd6bed93aadfb4e0442ebaeaf2eca18c2fd167db3f8b8b88b94a13dc9e（0/0/0）、独立22成功26.97sを照合した。旧63関数126assert/全decorator・旧185固定reader代入後bodyと正式9全rawを保持、A技術/B実187/Cbase-first・不正Bのfallback禁止を検証。実formal3前後SHAはcache root-formal3-reflection.jsonへ固定した。作者184成功/資産未反映1赤と最後13成功は別入力として保持し、今から実反映版の公開CLI技術検査と全moduleを確認する。公開委任証拠・最終HEAD・CIは未成立で、数学開始/全T1成立を代記しない。


2026-10-26T10:50:16.014390+00:00、PO委任によるCodex /root判断で通常33単位Aの操作限定開始条件を成立と判断し、単位Bの数学source12だけの着手を許可する。根拠は正式9実受理fe4590ed/独立bc604218…・consumer195成功、Gate6 source2/record/schema/policyの最終独立c1808081…残0と実保存11ed285c後の公開CLI --gate6-carry技術検査exit0（session78104）。直前の未commit policyでの旧prefix拒否33036exit1は、既guardが最終HEADからpolicyを読むための正当拒否であり、判定sourceを変更せず保存により解消した。A技術成功を公開委任受理/必須CI/新blindへ読み替えない。既全185moduleはsession42817で進行中。公開Gate6/最終HEAD証拠/CIと実認証・T2・同期原子保存/HTTP/画面再読込はmerge前義務のまま、数学source開始の新前提には追加しない。編集exact12は承認済みimplementation-plan-20261026/exactpaths.jsonのauthor_step2_math_existing8/new4、rootはこの12へ並行編集しない。未実装PA終端/走者/取消等を成功扱いにせず全MVP範囲を維持する。


2026-10-26T10:55:10.461653+00:00、rootの実反映版全moduleは175成功10失敗223.17s（session42817exit1）。新ordinary対向は通ったが、旧PR183/他PRの合成dispatch10件が実checkoutの新33資産存在を拾い旧範囲の外へ入った。PO委任によるCodex /root判断で既tests/test_human_review_signature.pyの歴史fixtureだけを当該旧test7関数（param含め10件）へ拡張し、既固定Git anchor入力を実temp rootへ供給する。対象名・旧各assert/decorator/期待値/製品checkerは保持、current必須repository testそのものや新33 fixtureには適用しない。旧testの期待値を新受理へ書換えず、既歴史fixture2の実体を再利用し現/歴史を分離する通常追随で、根拠なき同失敗再実行はしない。rootが当該test1だけ編集、数学作者の12pathへ重ね書き0。独立確認と変わった入力での限定検査後に保存する。


2026-10-26T10:57:56.197930+00:00、単位Bの実backend domain全検査で224失敗/56成功7.29s。旧初球2moduleの_caseが移行前caseIDをliteral lookupしてStopIterationとなる同一原因を確認した。PO委任によるCodex /root判断でbackend/tests/domainrt/test_first_pitch.py（before9a589ccfc302d5e84b2c1fade9fc4fddcb4a08d1389298ee09aeda18d2e1e4db）とtest_first_pitch_adapter.py（496172b26ed7de79314e4c6f6d4df40377d77b4f73439155859194b71a90a443）のexact2だけを通常の生成参照追随へ追加する。_case既lookupに正式ordinary_pitch_vectors_v1.jsonのcaseIdMigrations exact旧→新を適用し、旧入力/全期待assert/decorator・受理範囲/製品first_pitch.py/hostは不変。任意IDfallback/未知ID成功/期待値変更は不可、移行は正式12件内だけ。数学作者がこの2だけ追加編集し全before/after・旧assert保持/旧失敗ログと新全domainを固定、別非作者へ最終差分として渡す。全T1/同期保存/公開受理完了は主張しない。


2026-10-26T10:59:52.307600+00:00、PO委任によるCodex /root判断で後発歴史fixture1を受理。非作者dc795e9c4407937abd20b3b11a0934d861676764ed695dea1ba56739e05469cd/checks647b617031718fa09fe6b6b14733e2f05e7762acb8788f6107bc14e6c0088470（残0）、独立10成功18.70s/175deselected、root10成功17.90s/Ruff成功とafter6d6b24038dee2b9993a7d28d3e32747e66c627fbcdb370eb9f3c4b4ff97b77e6を照合。fixture1以外77定義/全assert/decorator・製品checker不変を維持。最初の歴史rootに現実行blob2が不足して2成功8失敗だったrunを保持し、現実行checker/testのexactbyteだけ供給して解消した。旧175成功10失敗を全成功に改記せず、保存後に実全moduleを一度再確認する。数学14pathの並行編集はこの検査sourceと交差しない。


2026-10-26T11:04:59.082904+00:00、歴史fixture反映後のroot実全module185成功225.23s（session82533exit0）。旧175成功10失敗/初回追随2成功8失敗を保持し、検査source/旧期待値を緩めず歴史入力分離で解消した。これは公開Gate6の外部証拠/最終CI成功ではない。数学単位B source14は別作者が固定停止、実Node/Chromium33＋tail、backend280成功後最終ordinary28成功、frontend95files1964成功のpacketを別非作者へ渡している。source14は未採用/未commitとして並行作業を区別する。


2026-10-26T11:06:39.319839+00:00、PO委任によるCodex /root判断で通常33単位B数学source14を受理保存。author ordinary_pitch_math/handoffe3c7a122c7447056a334938f03249ef2dccd6e2b6e807375fb942b9b4ad930aa/source14-manifeste70f83f74af2699db2f67953843469b06245e80c3f126eab00aeaf5d5b75da2a/patch49eff735408fb52966ba1c72c6af335454306aec83fe4a170462f5dece169b09。非作者最終80ef48574beef6e9c39a5780d1f8bb11b22fc1dee8dd07c05a0a4b6d93bc3d02/checks7e85a765fc9d20458328ce792be4c9b673057111df2b0b821a7aaf616a298815（0/0/0）と全14実SHAを照合した。独立backend265成功3.18s/frontend104成功2.17s、追加Node80座標=33成功47scope拒否、15履歴欄/巨大signed/23flag/2tail保持。作者TSdomain124成功、frontend95files1964成功、backend280成功後最終ordinary28成功（284全再走ではない）、実Node/Chromium33＋実called→ballS1B1/[E,H]完全一致、型/lint/format・再build hash同値。artifactfeb4fa1c…9827byte。

旧deriveState/初球ABI4error/scopeとbackend旧全assert/他定義を保持、private count核の単一TS実装と固定Pythonhost一回呼出を維持する。初回build構文拒否/旧caseIDlookupによるTScollection1赤・backend224赤と正式map追随の解消をcacheへ保持。成功は33の数学・履歴境界であり、T2 continuation/実保存・画面記録/全T1・P6/P7全成立ではない。次は最終HEAD公開証拠・必須CI/親merge依存と、実開始/同期Port/同TXprojection・再取得の接合。未対応操作は明示非成功のまま全MVPから削らない。


2026-10-26T11:13:35.251131+00:00、最終実PR187のGitHubbase3a24と旧checker30f67固定が一致せず公開Bを必ず拒否するP1を最終非作者6379c768…が検出した。PO委任によるCodex /root判断で採用し、既exact6範囲内の通常基線追随として是正する。旧規範anchor30f67/正式9/旧185全値は不変。通常merge efae7336で正式3aへ追随し、policyは正式12prefix（184含む）を保って186/187を末尾追加、test末尾競合は両系統全定義を保存した。新PUBLIC_BASEは実3aだけへ有限束縛、record.authority/schemaのbaseRevisionも実3a、anchorは30のままとし、bodyは正式3apolicy=旧11＋184だけを全field照合した上で186/187を要求する。旧原本を新値へ差替えず、B実base/同tree/head検査を緩めない。record/schema rawhashは実値へ追随。旧anchor/未知baseの拒否を追加し、旧期待assertを維持する。初回合成22positiveはbase30であり実公開base未検証だった資格とP1を保持し、公開成功証拠には使わない。非作者の反映差分/影響確認後に保存・公開B実検査へ進む。


2026-10-26T11:21:34.017766+00:00、PO委任によるCodex /root判断でactual-base第2回差分を受理保存。反映manifest691a1a28f79a19ee9bbfe1553e577f5a47e9060c1a984f7d69e120fd7f9cb1fe、非作者a4245dc40ccfe5224329c7a656096a1c4fe660ea25bb52d5f305093625368051/checksd23358564764f06c991ceebc780c70588fbd99b827cbf71e81e3fec85085ed5e（0/0/0）。旧P1をsource上で解消、数学14/正式9/旧reader/body不変、通常mergeの競合2path以外親blob正継承・旧ordinary78定義/正式develop新6定義AST/旧146assert・全decoratorを保持。独立24成功26.74s/192deselected、root56成功76.95s/160deselected・双方local技術CLIexit0を照合した。record2dee3598…/schema256f4595…は公開authority.baseRevisionだけ実3aへ追随し規範anchor30を変更しない。保存後の実公開HEAD/外部委任証拠/最終全216/CIは別未達として実検証する。


2026-10-26T11:58:59.990452+00:00、実CI187でcore/docs/tenant/frontendは成功、harness source scanが新5literal（規範anchor重複を除く4値）を拒否した。root実公開Gate6 Bは8ec版でDELEGATED VERIFIED、実署名全216成功であり、この赤を計算失敗/承認撤回へ読み替えない。PO委任によるCodex /root判断で既入力枠への有限登録案372074732c7e9ef18e9d604fa01e4761384bd283e9edc6e917e1fe283c9f149dを承認する。非作者第1回全文e974b3b80f0a8a7836f4793d2e2c2b971992594b0ab8f6cb983a99152a9290b0/checksdb1db209f74a0fef5be86b3b1fc4dfa899a53ecff98f4561f764a5c27c1bbd6e（0/0/0）を根拠にする。

exact Python3はscripts/check_human_review_signature.py、tests/test_required_set_coverage.py、tests/test_human_review_signature.pyだけ。作者initial_storage_norm_reviewは当該3とcache field/history候補を所有しrootが別通知後に実装する。既frozen-inputsへpurpose/consumer付きexact4値と外部consumer2を追加し、実#187の7.7 v2履歴/snapshotはroot唯一writerが確定する。旧全entry/prefix/snapshot/数学14/正式9/旧185/policyの意味・署名keyは保持、allowlist追加/文字列分割/scan除外/新generalbaseline機構0。初回Bは登録4値の実beforeafter・非作者全値・7.7・最終head/blob外部core証拠を必須とし、単なるcurrentJSON読取を旧hardpin同等と偽らない。closed frame/4flags各is False/authority/9asset/有限normbody・旧原本の拒否をsourceで保持、Cはactualbase registry先読/current全byte一致・共同改変/欠落拒否。既216/旧coverage全assert保持＋16分類対向を実装し、機械7.7接合不能は未解決として返す。旧4値以外の意味更新を今回通常機能として許可しない。正式反映前positive syntheticは実受理と区別し、最終源/全4値/履歴を別非作者へ渡す。


2026-10-26T14:04:48.523943+00:00、未採用frozen4 source3の追加反例でBのexternal dirty＋metadata自己整合が通ることを確認した。実対象版拒否の不足としてP0=1（SUPPLEMENT a3b528629eca1734fd3e5e2520fb885ec3bbdb2a20e777e880af1155fe70ff67）を採用し、source3はこのままmerge不可。旧2ade10/独立64成功は当時の範囲として保持し、公開8ec版の成功へ遡及しない。PO委任によるCodex /root判断で最小是正反映1案caa0b9a5e6d9bcff4927804aed28600c9199edc01a1e04b133071709d4994f96/exactscope8dc81855188eba35a186175a32c49b2b7ebcca51662e89e03aabc979e97a0462を承認する。非作者第1回b5821392…（P1=2）を全採用、第2回8b833b7cfa4f315142f8b8a89e72f76c011463edf8d6d4f19f3015afa8f16e66/checksfb3ec275514c308f2fe12589e68036adc33cd4e4bf6f12398a9a405563a0a75f（0/0/0）を照合した。

exact source是正はscripts/check_human_review_signature.py とtests/test_human_review_signature.pyの2だけ、coverage側a34f1323…と旧4実値/数学14/正式9/旧185/署名keyは保持。B/C共通の実7.7 helperが消費した全external current bytes・履歴authority/参照snapshotをevent.head blobへ明示束縛し、HEAD一致でもconsumerだけdirtyの反例を拒否する。C変更なしrouteは既どおり新受理0/fetch0。変更有routeは実PR188/実branch/exact既2entry全宣言・必要revision/external2の有限集合だけ、old4/旧全entryの全objectを保持し、actualbase先読/正当V2Transitionと当該PRの既core外部head/diff証拠を必須にする。任意PR登録や一般ledger再設計、snapshot自己申告だけの許可はしない。188側consumer2/正式JSONの反映は別owner/rootに残す。

新source作者をrootが指定し、旧source3の差分/失敗/P0を引継ぎ、是正後は基本第2回のsource差分＋影響レビューへ渡す（回数reset0）。承認案の追加対向・旧共同改変/元head再利用拒否を維持し、実metadata/source/最終headの全値をrootが受理するまで公開成功へ昇格しない。


2026-10-26T14:39:15.253873+00:00、PO委任によるCodex /root判断でfrozen固定4入力の登録source3＋正式5を受理。source基本第2回2f2f6e1bc06b03399ec072aa0d37eb96806e7053cb993de9a2101ae50e80ed6a（0/0/0）で未採用source3のP0を是正、既oldsourceレビュー2ade10…/P0 supplementa3b5…/新39対向/旧定義assert保持を保全した。固定source7ff033…/fed597…/coveragea34f1323…、全signature+coverage483成功462.19sとRuff/tyを照合。実正式5の全前後値は非作者83138215dc2b096e7a17697f96a391c06bf146f4f3fc2e52f70877f4171ad9d3/checks58257d51…（0/0/0）がactual3a前9asset+external8/後9asset+capturedexternal10から再導出し、旧31履歴/旧全entry/旧snapshot226/他7raw/既4pin全objectを保持した。

rootが実判断者/実日付をapproved_by/onへ記録し、masaki1025/pitchlog#187 v2履歴1追記＋registry5→6/fourentry/external2＋snapshot3だけを反映。nulldraft/synthetic構造確認と実委任受理を分離し、山田正輝の逐行確認・署名を代記しない。全実before/afterと対象sourceはcache corrective-source-round2/root-formal-acceptance.jsonへ固定。新最終HEAD/blob証拠・実公開Gate6 B・必須CI・実保存merge前義務はまだ未成立、旧8ec公開成功を流用しない。
