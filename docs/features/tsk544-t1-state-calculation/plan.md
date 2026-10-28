---
feature: tsk544-t1-state-calculation
status: active
承認: 済(2026-10-20・山田正輝)
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3f893b75e68781e5a55ce961b18fab3f
branch: feature/mvp-first-ball-writer-binding
created: 2026-10-20
計画レビュー周回: 10
確定ゲート周回: 2
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: TSK-544 T1 状況計算

**承認記録**: 2026-10-20、山田正輝がSHA-256 `40340ce0c2f399e35240c19ce64496656eeae93d4854ba2ba6eb3d6984d720fd` の本計画を承認した。追加独立レビューのP1 3件を採用した最終反映差分が未再レビューであることを含む承認である。承認記録によるfrontmatterと本段落の追記は指定SHAの後続記録であり、J5/J6の意味、正本7.3、契約7.7、P-6成立、製品計算コードの開始許可には拡張しない。現枝でT1を実行する唯一の計画を本書とし、[旧U-X1計画](../ux1-state-calc/plan.md)は2026-10-17承認済みの上位方針・T2以降の参照として保持する。旧計画のT1実行ステップを旧枝で重ねて実行しない。旧計画の全文・承認・レビュー実績を本書へ複製しない。

レビュー履歴は旧計画5周、TSK-544のP-8最小追補2周、J5/J6旧パス追補の採用反映2周、今回の採用反映1周で**通算10周**。J5/J6第1回はP0=1/P1=3、第2回はP0=1/P1=1を採用した。第3回P0限定は残存P0=1（旧計画のbranch/worktreeとT1枝の不一致）で、採用反映がないため周回数に加えない。今回許可された追加独立レビューはP0=0/P1=3/P2=0で否決。3件を採用した最終差分と、旧G6-S最終修正は**未再レビュー**。この追加レビューを7.3正本レビュー、契約候補2回のレビュー、P-6独立導出へ読み替えない。旧パスの未承認差分は[保全パッチ](https://github.com/masaki1025/pitchlog/blob/8d51453df3ef528c0470623faac23983feff2fde/docs/features/tsk544-t1-state-calculation/old-j5-j6-unapproved-candidate.patch.b64)に保存した。正本・契約に反映済みとは扱わない。

## 1. 背景・目的

11/12の段階提供では本物のT1状況計算を用いて1球を記録・保存・再読込する。ADR-003 v0.8 D-14-m、要件書v2.15、[旧計画](../ux1-state-calc/plan.md)のT1/T2限定経過措置とP-1〜P-9を適用する。分析40行、D-2全体の発効、無条件の凍結解除は対象外。FR-040の直接補正導線は延期され、これを含む従来MVP全体の完成とは記録しない。NFR-018に従いTSK-538の単一TS計算核・同一JS artifactを利用し、手書きの別計算を置かない。

原典と候補: [旧設計](../ux1-state-calc/design.md)、[T1入力・case候補](https://github.com/masaki1025/pitchlog/tree/7912b9c63e4b35a06fed667ee976cc8f91a4f457/docs/features/ux1-state-calc/tsk544-p8-candidates)、[J5/J6本文・型候補](https://github.com/masaki1025/pitchlog/blob/aec6768cbd0089c61b1b2ad0a8382947fa561cdf/docs/features/ux1-state-calc/tsk544-p8-candidates/t1-j5-j6-decision-candidate.md)、[P-6/P-7/P-8受渡し](https://github.com/masaki1025/pitchlog/blob/35a7f5761a105c77cbfee7820cf01ca2af84a37c/docs/features/ux1-state-calc/tsk544-p6-p7-p8-handoff.md)。候補中の未裁定値は正式仕様ではない。

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


## N3：同一artifactへの既計算入口の接合（PO委任承認）

2026-10-26T12:17:01.232728+00:00、PO委任によるCodex /root判断でN3具体案c0938282a54047902a0064f99c5308235d671abae6d4bad874aae93cd91dae3f/handoff1ac47fae0e8442b7217ff237e0373151b1f9ba1e91272cf578a2258fd8873c66を承認する。最終非著者n3_plan_independent f9c7c3c79653fd3f4509270778d826ba486755ce40a2926abc906adb09454c5b/checks4c7516aba10be08fed6b827b7bdb1a9cd7b4e2921429b8ca5c6029502b1c0f70（0/0/0）、固定43blob/既5参照SHA・破棄専用型接合診断0を根拠とし、実artifact/保存成功とはしない。元大枠作者mvpの4faf165c…は作者側整合確認だけで独立承認へ数えない。

実worktreeは正式3a24起点→ordinary8ecの通常依存merge95924ecb。N1安全providerの完成をこの純計算接合の前提へ戻さず並行先行する。既ordinaryのping/deriveState/deriveOrdinaryPitch3口を保持し、既T2ed07のderiveFirstPitchWithContinuation、既roster366eのvalidateInitialGameRosterを単一TS/publicApiに接ぐ5口だけを提供する。新T2意味/新計算/別Python計算/枝artifact上書き0、同before/Derived・旧body/DTO/旧caseID移行を保持する。N1権利/初期snapshot/同期原子保存/HTTP/readの未供給を成功へ補完しない。T2/roster所有範囲は実装の取り込みではなく既固定供給への接続依存として別記する。

exact集合は同案exactpaths.jsonのruntime/test/generated10（publicApi/sourcewrapper2/既spec4+新artifactspec/生成2）と別所有依存10（contract6/caller2/test2）。source作者はruntime10だけ、rootは既origin/hash一致の依存10を供給し、正式JSON/本plan/Git/台帳はroot唯一writer。entry/build/policy/host/first_pitch保護8pathは3系列同byteで変更禁止。旧publicApi全bodyを保ち、共有derivedJson差は旧T2全値比較で不一致なら停止、期待値やschemaを緩めない。Node/Chromiumは5口を同一実artifact SHA/sizeで確認し、既全domain・両caller実host/型lint/再build一致・canonical拒否を検査する。最終別非作者のsource/依存全値・最終HEAD確認後に採用する。

実corepreflightは全20pathが既領域で捕捉（root-preflight.json）、uncovered0なので新paths変更ゲートは追加せず最終coreレビューは維持する。新branchにはN3だけを進め、旧ordinary PR187凍結参照移設の別編集と共有書込みしない。旧187/186の親merge前義務・全MVP目標/レビュー履歴は維持し、この候補を正式develop提供・本人確認・P6blind/fullP6受理と呼ばない。


2026-10-26T12:36:47.684161+00:00、PO委任によるCodex /root判断でN3 source10を受理。handoff8812f98ebb4bf93d882d2dfb9da3144901182caee18a69d7a24e110633108dd8/manifestb938e7d2391029b0a72c6887777bd02dcc150d3818a0e60e54624cb4604f1c1f、非作者67684d90b00a8a1b135a34282743a093818574b8e1b7479f807c0c8e842b0ded/checksc0c31ddd15d6e88e618bee4e2c1ed6033eae45e9eeb5e86a1045f079ed90dd65（0/0/0）と全10/依存10/保護8の実byteを照合。旧ordinary21関数/T2追加2関数text保持、独立旧artifact3,096全値一致・実host/DTO31成功。作者frontend2126/domain286/backend domain430成功、型lintformat/Node24.16/Chromium149の同artifact5口67caseを確認（Node JSONnumber1件は既host先行拒否と別資格）。生成d5a026aefb486170ab70126708a76a792f0493644fc14fa32499a6442c8ea045/18447byte再現。

最初のroot保存scriptがmanifest名を誤り未編集停止し、後続pushで依存供給b7e8だけを先にremote保存した。源10の未保存を完成と扱わず、正しいsource10-manifestで全一致を再確認して本保存する。作者の初回cwd/ty環境失敗、独立uv runのignored venv生成もcache履歴を保持。正式T2全受理/初期snapshot/記録権・認可/実1球保存・再読込/全T1/MVP完成は未達のまま。親187通常統合と必要持越し検査、N1同writer provider/N2投影/N4HTTP-readへ接合する。


### 2026-10-26T15:09:28.937632+00:00: N2-A真正started初期snapshotの限定追補

PO委任によるCodex /root判断。既step2 PR-1aのN2だけを具体化し、cache first-ball-started-snapshot-scope-20261026/N2-ADDENDUM.md SHA06753a2bf40e3803e0399cc912bdb4fbccb3a2c6479c922a9b8f642849818bd9/exactpaths a9dc7676b124e8b0d37b642ad36a790456276238edec73b96f56e2285c995787を承認する。非作者第1回1d999422…/checks78297d52…（0/0/0）を採用、source実装前にcore捕捉/必要宣言を先行し、案の完成時core再確認を先行条件の代替にはしない。新source4はstarted_snapshot.py/started_snapshot_operations.py/test_started_snapshot.py/test_started_snapshot_operations.pyだけ。既CAP4再利用、追加grant0、未登録tokenの実run拒否。真正empty初期条件の証明後にだけbefore/rules/boardを構築、欠損0補完/別Python計算/initialprivate EXEC流用をしない。HTTP公開・Port・実保存activationは後続義務で、N1全完成をpure reader着手条件へ戻さない。

rootの依存供給版はfeature/mvp-first-ball-started-snapshot c6b1e800（開始cf4fbcdaへ既受理N3b7cd158cを通常merge）。5競合のruntime4はN3固定全byte、TS8全byte同値/artifactd5a026…18447B/公開5口と開始backend認可保存を保持。独立ca24ecaa466863d7074b8333516a7bc11830dc56d5136fe50dc1e9b4e153dd6a/checks77eda7f2…（0/0/0）、同domain320成功4.66s（既tail34併存を含む）で源供給版として採用。pnpmのunsafe symlink拒否は初回失敗として保全し、同既installed Vitest/同config/jsdom/fileParallelismを使うprogrammatic実行でenvDir=false/cacheDir分離、元source/期待値不変。node_modules symlinkは削除済み。正式develop/実HTTP/DB保存成功ではない。

rootはcore有限層source2の確認・保存→N2 JSON14追記の別commit→source4の作者指名を直列実行する。現在はN2source未実装、core sourceは別N1WTの唯一作者core_followup_layers、N2JSON/Git/親plan/台帳はrootだけ。製品source4はrootの捕捉成立通知前に編集しない。
### 2026-10-26T14:21:21.744075+00:00: 最初の実1球保存・N1-U1限定追補の承認

PO委任によるCodex /root判断。対象は58e045ad67b08406bf22df6241e19a414e43b223起点のfeature/mvp-first-ball-right-verification、既step2 PR-1aの実Port/実HTTP/同TX保存へ至る有限実装である。全体計画・全操作DoDを変更しない。先頭操作は通常ボール1球（N3 combinedのbatting-result / batting-result.ball / pitch-event、実started snapshot由来、balls0→1）。T1純計算の開始を実Port完成待ちへ戻さない。

cache first-ball-provider-concrete-scope-20261026/reflection1/addendum.md SHAe577ee3a04b30854d25156c3e5cb4fb63ae526424956f9b886c24544632107d7、exactpaths.json SHAf2ed3eafdbdf7e77b8a967d507abf900e515f8f00af3c74bcc03575e3f3fcbc4を本追補の固定内容として承認する。独立第1回86c61ac6…のP1=2を全採用し、第2回e31d8df641fefe41f1c66bf7caa27be0bc67e7d18bef5dd09a73d20568ca7aa8（0/0/0）で閉鎖した。本人による実値確認・署名・新blind・P6全成立とは記録しない。source作者の自己批准ではない。

N1-U1は未登録parser/private token/固定SQL2宣言とSECDEF renderer/bytes exact例外/拒否試験のexact8pathだけ。元の広いN1案にあった新sync worker/新business LOGINを先行条件にせず、既app同writer＋狭い検証に具体化する。CAPはSYNC_FIRST_BALL:bind_device/CAP:sync_first_ball:bind_deviceとSYNC_FIRST_BALL:check_current_right/CAP:sync_first_ball:check_current_right。正式JSON・CAP/catalog/body・runtime登録の反映はrootが別に直列受理する。nonce/lease/終結/quarantine未供給をfixture成功/常true/資格Contextへ補完しない。U1だけではPORT_IMPLEMENTATIONS未登録、実SQL成功positive0、実保存activation不可。未対応取消・訂正等を成功にせず全MVPへ残す。

sourceはexactpathsの既存1/新7だけ、function_operations.py beforeSHA0d9fb0c3f6eb948076bbd242def54f1eb8f519849babb2bb495ed28a63407745。既INITIAL2bytes長/一般bytes禁止/全旧assertと拒否先行順を保持。transaction.py/ports.py/DB/migration/正式JSON/初期権発行能力へ変更0。端末資格hashの既単一実装を再利用し重複計算を作らない。nonce assertion ABIの実供給は別N1-U2として残し、SQLrendererは未供給関数をtrueへ代替しない。

先にcore pathを独立補足d65e2027f97dc1dc93b942774800581c7479e079ff214220567f9bc852311ef2（0/0/0）で確認した17suffixだけ追記する。sync6/right6/tenant5、旧全宣言/除外/guard保持、exact8を各3領域で捕捉。coreJSON afterSHA3975fada465c8b32ad666f39facb1686f05d9f540be7bf397bfa387ddb45208a。rootが計画・core追加を先行保存後、source8唯一作者を指定する。source・Git・formal・台帳の並行書込を分離し、最終sourceを非作者へ渡して受理する。


2026-10-26T14:33:32.525031+00:00、N1-U1 source第1回独立364cf54f0410111be0a5e998257d1c5b79d867504e429344e62f759c53a637fa/checks685452be…はP0/P1/P2=0/1/0。正bigintを受理するcheck_current_rightのinternal_generation/recovery_generationが実psycopg SQLではINTEGERへ狭まる反例を採用する。PO委任によるCodex /root判断で既exact8内の通常不具合是正を許可する。新exact関数の当該2位置のみBigIntegerへ束縛し、2^31境界/2^63上限とbool/負値拒否を実compileで検証する。旧INITIAL・一般intのSQL型/期待値/全旧assertを維持し、汎用整数型拡張をしない。作者410成功と独立410成功/追加反例1失敗を別々に保持。第2回差分確認までsource8は未採用、runtime/Port/SQL成功の未成立は維持する。


2026-10-26T14:40:48.857487+00:00、PO委任によるCodex /root判断でN1-U1 source8を限定採用保存する。初回差分40749d…/第1回独立364cf54f…のP1を保持し、反映1差分4e624d608282a2b0f7a525f75b7df0efbbd1a972302f6f3accccfad8aee5c356・source8全差分6de352aa38df53e151a9c1e4d25119c263ce2554be68c65f8aa5524f13ca8f7aを照合。第2回非作者39d5399e14463224ff675d716164c441e707f2dbbfef1d15dd4cdbc555538db3/checks984bc92d…（0/0/0）、独立428成功14.35s/作者428成功13.43s、旧INITIAL13関数×2shape=26 SQL全文同値/_canonical_bind AST同一/他6byte保持/旧assert保持を確認した。実psycopg BIGINT compile対向でP1を解消し、Ruff/tyも成功。

保存する成果はcanonical proof parser・未登録exact2token/関数宣言・固定SQLrenderer・限定bytes/bigint境界・拒否試験だけ。nonce/外部lease/実終結/quarantine/Port/DB適用・SQL成功positive/1球保存は未供給。正式CAP/catalog受理も後続。既全MVP範囲を縮小しない。

root別coreguard全506の341赤は新17suffixに旧HTTP歴史fixtureと宣言層が未追随のためで、U1source成功と別に残す。先行coreJSON17追加を最終core手続き成立と誤記せず、最小の宣言層・有限歴史fixture追随（scripts/core_guard.py/tests/test_core_guard.py exact2、旧拒否・検出・全旧assert保持）をrootが別追補/独立レビューで閉じるまで通常統合不可。core検査を除外したり必須拒否を緩めて通さない。


2026-10-26T15:07:46.615839+00:00、PO委任によるCodex /root判断でN1/N2 core有限層の最小追補を承認する。対象d4b15142、PLAN 0c779fa0956f7a2769d9b9dade804f00312a816214447b17b9ac4c57ecabf40f/layer-map 7b3468c57a6c97881eb90b721224d1aa4ddf29efc19cc581eb3c1e0af60808cc/exact2 d736bd4ce35ac350ee94aa5d6173c97922140bd6e7705e3e2526de6e40992b07、非作者第1回d38ea29c363d6f4868b3975e584bec542dcbcd7f6f1a1621533cfeca220f4391/checks9dfe4e08…（0/0/0）を現物照合した。scripts/core_guard.pyとtests/test_core_guard.pyだけを唯一作者core_followup_layersへ割り当てる。N1既17/N2予定14は任意metadataから作らず閉mapに固定、既旧validate本文/旧AREA_PATH_ADDITIONS/同commit拒否/全旧assert・decoratorを保持し、5状態25遷移の11許可14拒否を実Gitで検証する。未知/部分/削除/順序入替/想定外areaを許可する一般化をしない。

歴史fixtureは独立mapによる全field保持の有限投影、新raw JSON捕捉は別入口で必須検証。元coreJSON17先行保存と341赤を当時成功に改記せず、是正履歴を保持する。rootはsource定義の非作者確認・別commit保存後にN2JSONを別commit登録し、その後N2source4を開く。source2とcoreJSON/plan/Git/正式JSONの編集者を分離する。source2が通っても実Port/DB/HTTP/1球保存成功とはしない。


2026-10-26T15:11:02.616216+00:00、core exact2内の後発歴史fixture具体化をPO委任によるCodex /root判断で許可。旧test_http_core_declaration_retains_initial_layer_and_all_predicatesのassertを保持し、そのoriginal/current入力だけにexact新helper2名除去＋verifyのexactwrapper呼出1を旧呼出へ戻す有限AST投影を使う。未知helper/他body変更は残して旧assertで拒否、新helper本体の正しさはraw現sourceの実Git対向/拒否削除mutationで別検証する。旧validate/AREA/同commit拒否/全旧assertを変更せず、追加の意味承認ではない。source独立レビューへ後発差分を明示する。


2026-10-26T15:24:06.070458+00:00、core source第1回独立adb4a5838a92745ec2d1713b7f1289762711b3bd4920aefd6f1ea2f5baf737bb/checks5f9f6a8b…のP1=1を採用する。新raw capture testが各層を単独で末尾比較しN1→N2/N2→N1を誤拒否する2反例を保持し、PO委任によるCodex /root判断で既test1内の全層順合成suffix比較＋両order/全5状態raw回帰へ是正する。production判定/旧429assertを変更せず、597成功は現N1-only入力資格、未来N2捕捉成功とはしない。第2回差分確認までcore是正は未採用、N2 JSON/source4も未着手とする。


2026-10-26T15:33:22.762327+00:00、PO委任によるCodex /root判断でcore source2反映1を採用保存。独立第1回adb4a583…P1を保持し、第2回0ed57ceaf44f2961cc68967f2d39bc734e9089b29d723b65a6c3894d589a5726/checks33e420e9…（0/0/0）で閉鎖。production13e018…不変/test49dfb436…、旧429assert・decorator保持/旧validate・AREA・同commit拒否body不変、独立101成功5.29s/元反例2不変成功・作者全603成功55.15s/Rufftyを照合。旧341赤/旧597N1-only成功と未来複合層の資格を分ける。新全5状態のraw捕捉と旧歴史fixtureの有限投影を独立に実証した。JSONはこのcommitで編集せず、N2は依存mergeと実before照合後に別JSON commitで14追加し、その後source4を開く。core是正を実保存/全MVP完成へ広げない。


### 2026-10-26T15:50:52.318991+00:00: N1-U2-A実writer bindingの限定実装承認

PO委任によるCodex /root判断。新WT feature-mvp-first-ball-writer-bindingは既受理0014b0f3起点、source13 beforeはd4と全byte同じ。反映1 N1-U2-UNIT 6f4f348c697807ed97a8027ad5789c067561b87443bcdf3e7c61de068a850df5/exactpaths 352c55a65d268ac49395e76cdbff53dc974f77b7ddc28e247f63e2af2208c4cf/outcomes閉表を採用し、独立第1回05af2bce…P1=2を保持、第2回63afdd869a1d73bb221729d066adc9fa3efc8115fe84458277c9d2751b7c6585（0/0/0）で閉鎖した。元current_userをsession_userとした誤根拠を撤回、NOLOGIN矛盾ではなく未供給runtime固定EXECから主体を具体化する。未assert生存/0admission/NULLは終結証拠にせず、ENTRY_CLOSED_UNADMITTED/UNKNOWNで耐久隔離しnewlease/epoch/evidenceを閉じる。21対向は計画だけ、実DB成功未主張。

source13を唯一作者writer_binding_unitへ割り当てる。既app同writer・新v3専用sync_binding peer/候補UID20005・control専用限定EXEC LOGIN/補助2表は既MVP保証を具体化する今回の承認候補で、汎用業務DML/initialactor拡張/新署名key/新運用資格発行をしない。v1/v2は不変、同TX/期限/ドレイン/本物xid8/commit・rollback・未進入・不明の4分類を実2DBで検証する。実施は隔離DBのみ、共有DB適用/公開は不可。source完成後も登録・N2/T1/T2/projection/HTTPへの接続と全MVPは別義務。

rootが固定依存5を先行供給。__init__/evidence/store_contractは7c04全byte、stop_contractはpure型3とhelper5の元AST厳密部分集合だけ（公開操作/新ports ABIは未供給、fake型0）、control-phase-schema.sqlは原schema先頭3表prefixだけ。他11表/全F2/F3/runtime完成へ広げない。独立9f932c5e3b4bc071d7c6467c9d02a28a3a8e34526b7f0c6309992a0d3f688301（0/0/0）、実import/正常型/未供給API例外を確認した。root依存5＋source13全て既coreで捕捉、pure試験名はtest_sync_apply_writer_binding.py。manifest/root5・migration/registry/formal/models登録/plan/Gitはrootだけ、作者13以外を無断編集しない。DB実行はrootの登録/migration供給と排他的許可後、fixture偽table/常true/fake leaseを本物へ代替しない。


2026-10-26T16:32:26.607012+00:00、実PG17のSECDEF統計可視性診断に基づくstats反映2をPO委任によるCodex /root判断で承認。独立c132e8bcea77d6f820cbed20833db5122696377d786f0671f027d49dbba58a90/checksbcd75d56…（0/0/0）。新read_writer_database_identity(uuid)限定helper1/既read_writer_identityのINVOKER自己観測へ具体化し、SQL物理TX権威は実fullxid8/PID/PGinstance/postmaster/nonce/epoch/lifetimeで保持。backend_startは実scope自己観測の相関値、typed私有発行時に実6値を再読照合し、raw同一物理TXの偽相関startをSQLで独立認証できるとは記録しない。広stats/approle membership/app engine資格貸与を禁止、旧案撤回を保持し、専用_InitialAuthVerifierRuntime/_verify_initial_cookieの閉口だけをbrokerへ再利用。旧初期actor/3cmd/権限は拡張しない。SQLfreeze22ddは新6署名packetへ更新し非作者source/実DBへ渡す。

同source13内のモデルmetadataも既正本の形式へ整合する。sync_fence2表のschema/nameと権限は保持、LifecycleMixin、bindings=対象外/更新可/退役なし・state/close_id条件付き1回close以外全不変、admissions=対象外/追記専用/退役なし・全列不変。PK/UQ/FKの既roles/cross_tenant infoを明示、tenant/gameの複合所有整合をFKで守る。UPDATE/DELETE/TRUNCATEから不変証跡を保護し、closed→openを許可しない実DBtriggerを同SQL内に具体化する。追加private trigger関数はPUBLIC/app/actor EXEC0、同NOLOGIN ownerか既ownerで限定。source13外のmigration/manifest/登録はrootが直列供給する。新DB namespaceに対応する既検査の論理名正規化は旧50全値を保持する最小差分として別確認する。新control専用PGを含む所有4PGは実2DB(sourcecontrol/business)＋既ledgerprimary/witnessであり、共有DB/運用公開はしない。

### N1-U2のroot所有DB供給範囲

2026-10-27 JST、PO委任によるCodex /root判断で既承認補助2表の配置を具体化する。固定packet2（model aef329e9c46375b7de16c725a5eadc6902211bf5914a4693d5d18ed6031ed1fe / SQL 69ea20ef3d2facb2c2f2eca1dff9eed52a4b967029c3c10f68cb92dde5488359）を基に、rootだけがbackend/migrations/versions/0037_sync_writer_binding.py、backend/src/pitchlog/db/writer_binding/{__init__,models}.py、backend/tests/test_sync_apply_writer_binding_migration.pyを編集する。models.pyは既単一モデルのTableを公開する登録入口だけで、計算・モデルのコピーを作らない。既all_modelsの走査/全モデル捕捉を維持する。0037は0036後、専用sync_fence schemaの2表を静的なop.create_tableで配置し、RLS ENABLE/FORCE・PUBLIC権限撤去で未登録時default-denyを保持する。運用actor/function/ACLは別の正式供給であり、migration単独で機能稼働とはしない。既行の仮値補完/共有DB適用/物理削除はしない。履歴を失うdowngradeは拒否する。静的DDLのモデル全列/制約一致・拒否・登録を検証し、最終独立レビュー後に採用する。author source13とroot新4pathは非重複、モデルの著者差分をrootが変更しない。

2026-10-27 JST、PO委任によるCodex /root判断で実fullprofile供給のcache候補作成を割り当てる。唯一作者n3_plan_independent（この差分の以後の独立採否には使用しない）はbackend/src/pitchlog/authz/first_ball_product.py、同product_role_contract.py、product_table_rls.py、product_function_acl.py、product_control_access.py、product_catalog.py、product_provisioning.py、classification.pyとscripts/check_authz_catalog.pyのexact9pathだけをcacheへ実装する。既decl/profileを保持し、sync_fenceのexact2表・新3role/3schema・U2の7関数/U1の2関数に閉じる。実抽出候補はroles14→17/schemas8→11/tables50→52/functions79→88/policies70→77/columnACL123→144/表builtinACL33→36であり、実DB照合前の候補数値。旧全entry prefix/属性/拒否/検査assertは維持、未知・欠落・部分profile・余剰権限を引き続き拒否する。単なるcheckerの件数緩和で通さない。新namespaceをpublicへ改名せず、関数SQLの実body/owner/SECDEF-INVOKER/EXECとpacket2を束縛する。canonicalJSON/runtime契約/generatedruntime/operation_registry/7.7/plan/Gitはrootが直列反映し、最終sourceと全前後値の別非作者レビュー後にだけ採用。新author差分を旧独立レビューで覆わず、role運用資格の新規発行や共有DB適用は含めない。Alembic autogenerateの専用schema対応は必要な後続として明記し、本9pathに無断で混ぜない。

同日、上記product supply cache候補の検証対象としてbackend/tests/test_sync_apply_product_supply.py新設とtests/test_check_authz_catalog.py末尾追加のexact2pathをPO委任により追加承認。旧全文/全assert保持、新exact部分の欠落・改変・余剰だけでなく旧部分の改変も拒否する。unapplyで新SECDEFへPUBLIC EXECを再付与せず、履歴・限定ACLを保つ。既仕様で決まらない退役/削除を仮定せず、必要なら明示拒否/未提供としてrootへ提示する。control既存role属性検証の独立指摘調査は別差分として扱い、作者source13の旧固定点を消さない。

2026-10-27 JST、N1-U2 source13第1回非作者REPORT8a4e77ba3f14e24392d7a4726aa7438b5dd7826a778eb547d59f5422d098784b/checks79bd38f0…のP0/P1/P2=0/1/0を採用。control専用DBはbusiness DBのcatalog検査で覆えない。control SQLの既存owner属性/両向membershipとactor逆向membership/connlimit/validuntilの未検査を修正する。唯一作者writer_binding_unitが既13中writer-binding-control.sqlとtest_sync_apply_writer_binding.pyだけを編集、他11byte/packet2 businessSQLとmodelを保持。既2roleの固定属性と両向membership0を権限付与前に検査し、不一致は拒否する。ALTERで権限修復せず、既存不正設定を正常へ読み替えない。旧source13/322成功とP1反例を保持し、反映1の全前後値を別非作者第2回確認後に採用する。実DB対向8本/追加故障coverageは別未実施、P1是正だけで実耐久性を主張しない。

同日、root migration exact4を非作者第1回report37b1167e29b82654b17f2dd2b9655bcf9e3b545507d7c7f2654766f948a49576/checksbaf95fca…（0/0/0）で限定採用する。独立9成功1.07s/0037hygiene0/固定model全29+5列・型・timezone・UUID属性/全制約/PG dialect FKcompile/default-deny8文/GRANT POLICY0/逆適用拒否/同Table alias全走査を確認。rootsource manifest e5f4f6a6…と同byte、source13のP1未解消・正式profile/実DB未供給を残す。未受理source13を参照するHEADを不完全にpushせず、モデル/供給の保存順を調整する。

2026-10-27 JST、PO委任によるCodex /root判断でN1-U2 source13反映1を限定採用保存する。元manifest75ef3784…/旧第1回REPORT8a4e77ba…P1-1を保持し、反映1 manifest e614e9d6a445a1b2e38824ff336ac77c0c844a3bdcea56caff2adf46ff7d778d/patch2904a08c…を照合。非作者第2回REPORTfc87c9b1bc9331e1de82dfa76aba9a1aebf024700d21f0516cc48e664cc5dd60/checks835c694f…（0/0/0）、全13実SHA/変更exact2/他11・packet2保持/GRANT以降同byte/旧pure27AST prefix保持、独立337成功0.81s/Rufftyを根拠にする。control両roleの全固定属性・両向membership0をGRANT前拒否し、ALTER修復せず旧P1をsource上で閉鎖した。制御フローdouble7を実DB証明と混同しない。

root migration exact4の別独立37b1167e…も採用し、参照する単一モデルと同時に保存してHEADの未存在importを残さない。保存対象は作者13＋root4＋既親planのみ。正式catalog/registry/manifest source SHA/7.7/実DB8本と既role変異/追加故障系/CI/通常統合は別未達。未対応operationを成功とせず、nonce/lease/DB終結を仮のPortへ置換しない。次の供給10source/正式asset候補の採否は、このsource限定採用へ含めない。

### 製品認可供給の限定追補（候補作成中、正式採否は別）

2026-10-27 JST、PO委任によるCodex /root判断で既承認9sourceへbackend/src/pitchlog/authz/asset_spec.pyのexact1 invoker kind/順序対応をcache候補範囲として追加した。0037は表2だけでありU2関数を配置するという初期候補作者の誤前提を撤回する。fullprofileがU2 7関数＋U1 2関数を実CREATEし、read_writer_identityだけINVOKER、他8はSECDEF（内部guard含む）。guardへ固定4triggerを同梱、未知invoker/SECURITY反転/順序不正を拒否する。新profileのunapplyはSQL生成/実行前の明示拒否とし、PUBLIC EXECの再付与・証拠削除をしない。旧profile挙動を保持する。

正本実装追随/構造候補の唯一作者first_ball_u1_independentへcache exact3path（docs/design/data-model.md、contracts/db/schema-manifest.json、backend/tests/test_schema_manifest.py）を割り当てた。既6-1節の最小6-1-a writer2表追補と、3-4のwriter lease/nonce2行・既初期権一意2行だけを追加する。列/既一意predicate/記録結果/tenant/権限・耐久保証は変えない。manifest旧50のうちgame_start_attempts/recording_right_deliveriesのbusiness_unique.source_rowだけを既checkerの正形式へ修正（必要参照section追記）、旧構造と他48全objectは保持し新2表全構造を追加。旧quote形式のKeyErrorによるbaseline3赤と是正後値を別に保存する。

新schemaはsync_fenceを維持する。論理名をtable.nameへ正規化する際は全物理schema/重複を明示検査し、新exact2だけsync_fence、旧50のNone/publicを保持する。未知schema/同名別schema/既表schema偽装は拒否し、schemaを単に無視して通さない。FKは閉検査した実Tableの論理名でmanifestへ対応付ける。旧全assert/制約・負例を保持、モデルとDDLの単一実装は変えない。正本の改訂区分/全前後値とsource差分を別非作者へ渡し、実装追随節更新として扱える範囲を確認後にrootが正式反映する。本人承認・全P6/全T1/実DB完成を代記しない。

2026-10-26T15:34:43.870576+00:00、PO委任によるCodex /root判断でN2 coreJSON14を独立7a144fa54cd4ecdd9fbeb5fbbb5a11615b2f3550298eec515d184ff7322879b8/checks4da98cfa…（0/0/0）に基づき反映。core定義0014b0f3の依存merge後、実before3975fada465c8b32ad666f39facb1686f05d9f540be7bf397bfa387ddb45208a/after4f794a7d629e7629dc36943ac9eef8f36ceff0b21941c62026766af42a551955を照合し、実wrapperでN1→N1N2を受理。旧全field/prefixを保持するexact14suffixだけ、source4をsync/game-state/rights/tenant全4領域で捕捉する。JSONはsource定義と別commitへ保存し、保存後にsource4唯一作者を指名する。正式SQL登録/HTTP404解消/現在rights/実1球保存は未提供のまま。


2026-10-26T16:21:57.650043+00:00、PO委任によるCodex /root判断でN2-A source4を限定採用保存。patch7ce4299e…/manifest879643e5…/独立3f7f9515941f39a328a5a6fd0703d23e1b0abd3fbc52e3ff0ca9a9b96dacfc75/checksb65a27d6…（0/0/0）と4実SHA/core4f794a7d…/N3artifactd5a026…を照合した。作者7module596成功4.78s/独立596成功4.76s、実handle.runの不正context/証跡/失効等5拒否、generation lock実psycopg BIGINT2を確認。source4の元は全未存在、同handle/lock-read/保存名簿・rules/全generation空条件からだけ初期snapshotを返し、0補完・別Python計算・真偽proof発行をしない。初期88/中間595/最終596の版とstatic環境失敗・独立probe入力誤認を保全。候補4tokenは実executorで未登録拒否、正式登録/7.7/startedDTO・HTTP/404解消/現在rights/1球保存は未達のまま、次の限定登録と実owned読取へ進む。

### N2-B1：既CAPだけによる開始直後read登録

2026-10-27 JST、PO委任によるCodex /root判断で、受理済N2-A e8d24790/依存追随c3fb7d1bの次の登録単位を具体化する。root唯一編集のexact3sourceはbackend/src/pitchlog/repositories/operation_registry.py、started_snapshot_operations.py、backend/tests/test_started_snapshot_operations.py。既STARTED_SNAPSHOT_OPERATIONSの4宣言をPRODUCT_OPERATIONSへ追加し、既4read CAP/全tenant/game等値/LIMIT3または1/全世代存在確認/単一TS計算を保持する。CAP/grant/SQL/新writer資格の発行や認可迂回を追加しない。

Aの未登録境界試験は、正式登録後も同じcapabilityを名乗る未登録派生型を拒否する対向へ具体化し、実executorの未登録拒否/失効/SQL未到達を維持する。別の正常試験でexact4型だけの解決、元context tenant注入/元game/固定LIMIT、immutable結果を実handleで照合する。元全SQL/型/未知入力対向のassertを保持し、サーバー・DB保存やGET404解消の実証とは呼ばない。runtime登録母集合と参照値に影響がある場合は実差分を導出し別に正式受理、未受理状態を完成扱いにしない。作者root、最終差分は別非作者レビュー後に採用保存する。N2初期readerは記録済みeventがあれば拒否し続け、記録後状態を0で補わない。実DB/HTTP/画面/記録後projection復元は後続として維持する。

N2-B1の実登録後、周辺12moduleは795成功/3失敗46.43s。うち2件は登録母集合の既47token/30利用CAPが51token/32利用CAPへ正当に増えたsource宣言・exact試験未追随。新規DB CAPやgrant追加ではなく既catalogのgame_lineups/play_rows readを利用する。PO委任による通常整合変更としてbackend/src/pitchlog/repositories/repository_contract.py、backend/tests/test_authz_repository_contract.py、test_authz_capability_registration.pyを有限追加し、旧47/30prefix・全型→CAP対応を保ったexact4/2追記とする。runtime-authz-contract/7.7正式値の未受理は別に残し、仮承認は注入しない。

残1件は既開始sourceの_assert_initial_actor_transactionがcontext読取の宣言集合へ未登録であり、N2がtransaction.pyを変更した結果ではない。backend/tests/test_authz_tenant_binding.pyの強制点集合へ実関数1を追加し、既exact型/発行証跡検査を免除せず同じAST検査で確認する通常追随を承認。旧5強制点と_execute_operation唯一免除/全旧負例は保持する。未知読取点の自動受理や免除拡張をしない。最終レビューへ基線由来と今回登録由来の差分を分けて渡す。

2026-10-27 JST、N2-B1の全前後値の対象はcontracts/tenant_boundary/repository-contract.json revision28→29であり、runtime-authz-contract revision23は変更しないことを実物で確定。未受理候補の初回full-valuesでasset-only digestを正式凍結射影と誤表示したため、旧f778dfb9…をfull-values.asset-only-invalid.jsonに保全し、正式frozen_history.frozen_projection_contentと宣言external4実byteで再導出した。修正full-values bdfec377fa58cb3e3953f2980c27b648bec8a3815c0f11ba82e1de3e0250a789、before b0f3695caf14e103bf72d5af501c6f3a77f9e7e2f08b7748a954e9a2d8a6b834/after41d627b412ed082f97974ab12d6ec9d479a46e3d27b752aea3e741c5850eed53。旧誤値を受理した事実はない。

非作者最終REPORTdf4355e285fd540b8467c6e6eb08aa4c594b2c845d53fc24a23d56a070ceb927/checksc6498c8e…は初回導出P1-1→是正を保持し最終0/0/0。全source7 SHA/旧47token30CAP prefix/他全object・関数面・A reader・transaction・runtime23不変、独立301成功＋正式JSON未反映2赤/50.19s、追加actualhandle不正context20対向SQL0/Rufftyを確認。rootはPO委任によるCodex判断でsource7と候補JSON1の採用をroot-adoption.json（実日時/判断者/完全raw SHA/根拠/留保）へ記録してJSON29を反映する。source7 manifest a161ff1e…/patch e9047c4b…、SOURCE_DIGEST da12d999bb8a186a924cf8dafe0623f6e0421d49655a3f243d21dd4a08b4ccba。公開7.7 authority履歴/実PR最終core証拠・CI・通常統合は別義務、今回の候補値採用から全成立を導出しない。本人逐行確認・署名代記なし。

JSON29反映後の同一候補でrootは登録・repository・tenant強制点・既開始/通常処理の影響12moduleをまとめて実行し、798成功47.10sを確認した（既Starlette非推奨warning1、失敗0）。反映前796成功/2正式JSON一致赤を消さず、新入力で両一致を閉じた。source7/正式候補1/既planだけを保存する。runtime/7.7authority/public最終HEAD受理/CI・実DB・HTTP等の別義務は維持する。

### 実保存用function token4件のroot登録単位

2026-10-27 JST、PO委任によるCodex /root判断で、受理済source13とN2 read接合4027547aから次の有限単位を実装する。編集rootのみ、exact source4はrepositories/operation_registry.py、repositories/repository_contract.py、backend/tests/test_authz_repository_contract.py、新backend/tests/test_sync_apply_function_registration.py（前2はbackend/src/pitchlog/配下）。既RG1/段階A4登録を全値保持し、受理済private U1 bind_device/check_current_rightとwriter read_writer_identity/assert_writer_bindingの計4 immutable宣言だけをPRODUCT_FUNCTION_OPERATIONSへ追加する。型/6入力・32byte/BIGINT境界/戻り値/decoder/SQL・認可・tenant束縛を変えず、既app scopeの同Session実行器へ接ぐ。DB actor/HTTP/Port成功を仮に返さない。PRODUCT_OPERATIONSの51token/32既利用CAP/旧関数4は保持、初期actor専用registry/phase能力は拡張しない。

repository-contract revision29→30と生成digest/function ID末尾4の完全前後値を候補として導出し、source4/JSON1を別非作者review後にrootが採用反映する。正式値受理/public7.7/CI・実DB成功は別義務。旧段階A検査は旧4prefixとindex3を保持したまま全8ID/DB関数対応をexact検査する。新試験ではactualhandleで型4のtenant注入/元bind/結果型/失効と、同CAP派生型・不正文脈・入力長・欠損結果をSQL前/decoderで拒否する。テストdoubleの応答を実DB成功と数えない。

登録前のroot実PG17限定診断43ea53e0…で、void戻りの実text表現はstr空文字・現在のNone-only decoderでは正当結果が拒否されると判明した。既source13のpure None fixture成功を実driver接続成功とした事実はなく、実U2 DB0を維持する。SQL ABI/guard/原文を変えず、exact writer assert列だけの結果adapterを別cache単位で候補化し、rawdriver空文字のみcanonicalNoneへ正規化・その他値拒否/他関数不変を独立検証する。仮成功応答・bool true返却への変更や拒否の一般緩和をしない。root診断の初回image tag不在はDB0で記録、installed17.11-bookwormで診断後は所有container/volumeを削除した。

同登録の初回局所検査は343成功/旧4関数exact集合1赤。受理済新4宣言を加えた実集合を検査するため、backend/tests/test_function_operations_boundary.pyの当該1testだけをrootの有限範囲へ追加する。旧RG1/段階A4と新4の全ID/型対応を8件のexact集合で検査し、他旧assert/負例を保持する。登録型の未知受理へ広げず、同じ入力で赤を再走しない。製品source3/試験2の計5sourceと候補JSON1の採否へまとめる。

### データモデル1.5の限定7.3確定と構造反映

2026-10-27 JST、PO委任によるCodex /root判断。初回REPORT35933866…のP1=2（構造初掲載の誤分類・未実行DDLを実装済みとする検出）を全採用し、反映1 ce88bdb0…/差分dfc02288…を第2回4356c91cfe08c7b807de469d1fa36990b8a51a31b0af200afbef92e73346c296/checkse5fe37c3…（0/0/0）で確認。1.5本文は旧1.4履歴/本文を保持、新2表の固定構造と参照整合に限定し、backendPython3.12の0036全upgrade ASTへ閉じて元return/raise反例2を拒否、独立35成功/Rufftyを確認した。版上げ不要というrootの初回誤分類は撤回し、限定7.3として確定した。

root確定metadataはroot-decision66da16f4784d7f00217a4d63e0b5f6d2faae09d5b3baab9acd25bee659e9a8bd（初回index末尾2セル未追随の旧53f17…を保全）、追認REPORT6e1ab812dd08aa4dcb8638f3982fbd6bdaf995c62e6f3f238d69211982e5c210/checks78390749…（0/0/0）。実判断者/UTC日時/対象hash/留保は同cacheに固定、本人確認・署名代記0。sourceはdoc approvedと1.5履歴1行、schema canonicalSHA6ae73d93c6fde8b54d94e9c6fd3d9cc5b46767d911d3701ed737cfa1bf0d8d51だけ、indexに1.5現行表示/日付と旧履歴保持、test1は反映1固定byte。actual-adoption.jsonで実HEADからの全4前後SHAを採番して反映する。旧48表全object/旧2は参照形式のみ/新2全構造を保持、正式認可67候補/7.7/runtime24/実DB/HTTP/1球保存は別未達。型付き4function登録の作業中sourceとは保存範囲を分ける。

2026-10-27 JST、VOID結果adapterのexact2をPO委任によるCodex /root判断で限定採用する。manifest1607137afcd8a90c348f4553500fee9179625c4d5ca6e48678f015361f0ac455/patch2dfdd1bf288ba24e7fc647c7553001ad70aed6cae315a874c229ce2f8e588a46、非作者REPORT061bdf6ec87090d30b3ccb72318bd7d86b94f5a94299265a91a9e5e46f0cb426/checks386c7cb6…（0/0/0）を根拠とする。exact assert selected列だけの実driver空文字→canonicalNone変換、Noneを含む他14値/追加18変異拒否、旧20登録SQL/bind/selected型/processor全値保持、caller型破棄、SQL例外の同一オブジェクト伝播を独立92成功/Rufftyで確認。原VOID SQL/全guard/旧None-only decoder/他11sourceを維持し、実PGprimitive診断とpure型境界の資格を分ける。new9再適用P1は別product67の問題でありこの修正から閉鎖を導出しない。実U2/実DB8本/1球保存/HTTP/正式7.7は別未達。

2026-10-27 JST、保存用4function登録source5＋repository30候補1をPO委任によるCodex /root判断で採用。source manifest573d3ea5…/full-values2b8e6d0e…、非作者REPORT23bb29d749de971246631c2e29295efa0bfbc717bf9ee52d77796421dee472d7/checks33eafbbf…（0/0/0）。旧4登録AST prefix/51DML・CAP32/初期actor専用registry/全private型/SQLguard・bind・VOID処理・role供給は保持。JSON全前後値は正式helperのexternal4込みでbefore41d627…/after945166…と全raw/source_digestを独立照合し、他全object/旧prefix保持を確認。独立377成功0.81s/追加20対向と入力47拒否SQL0/Rufftyを根拠とし、runtime一部doubleの資格を実actor/実DBへ拡張しない。actual root-adoption.jsonへ実日時/判断者/対象hash/留保を記録してJSON30を反映。正式7.7authority/public最終HEAD/実DB8本/HTTP保存は別未達。

### 認可供給・最終派生値の保存点（PO指示により中断）

2026-10-27 JST、PO委任によるCodex /root判断でproduct67反映1を限定採用。元第1回c8d34611…の再適用P1を全採用し、反映1 manifest2be3a83853e5942367d2b633e6783f375ce7e90b687cacb3136a13e25c559c92/旧67全値・他64保持を確認。第2回非作者REPORT6acc495b45518ce0b8d38a4ac220e5ed3932cd52eb1657d7152afbe7f808094c/checks60f25fd7…は0/0/0、独立160＋9成功/追加27 body変異拒否。新9だけ未存在CREATE原文/既存全属性・owner・ABI・prosrc・ACL・guard4構造一致でskip、不一致固定拒否・既存分岐変更0、元418文を保持。実二度apply/実属性変異・DB8本は未実施。root-adoption ee2d1d1f…で全67実before/afterを照合反映した。

runtime24/generatedmodule/ledger source SHA2の最終exact3はroot full-values f8f782b2…/ledger-values29ca1bb8…を第1回非作者REPORTae3c96a62ad0264657fcaa19d11f667de092a0dbd288097c45903cf668373838/checks25198656…（0/0/0）で照合。中間candidate24を流用せず実product e41f738d…/正式before23から公式導出、旧8/50/79→11/52/88の全prefix/app7属性・他objectを保持。正式helper外部4完全射影849176…→95b410…/raw/module bebc6f…を確認。ledger authority90c/adaptere12の2参照だけを受理済source955実byteへ追随し、他全object/schema1を保持。実root-adoption.jsonの日時/判断者/対象SHAを記録して反映。本人署名/逐行確認は代記しない。公開7.7authority/最終core/CI/実DB/HTTP/1球保存は別未達。

POから『切りのよいところで一度作業中断』を受領したため、本単位の整合・局所検査・保存pushで止める。実DB8本を新規起動せず、次の開始点はproductの実二度適用・exact catalog/属性変異、実Cookie/v3/nonce/samewriter/U1/終結DB8。次接合のpure V5 codecは別cache（未本体反映）、実Port/同writer結果frame/T1-T2投影/HTTP・UI・記録後GETは後続であり、MVP全体の目標・安全条件を縮小しない。

中断前の整合同一候補で、新認可供給/保存関数登録/VOID境界/52表manifestの影響4moduleをまとめて実行し303成功2.62s。実profile静的整合が成立する保存点に到達した。全件/実DB/二度適用/HTTPの成功ではなく、旧2622成功10fixture追随赤は別残件として維持する。codec独立確認はPO中断指示で未完のまま保存（pause-checkpoint a88573a8…、静的読取りのみ、独立検査/採用判定未実施）。新しい実DB試験は起動せず、全担当を停止する。

### 初球V5 codecの限定採用単位と後続の内容判定接合

本単位は既2026-10-25操作単位追補の「型写像の有限確認→実接合前のexact指定」を具体化する、旧ステップ2内の純部品である。T1/T2数学・既23flag/履歴/全MVP義務・全旧レビュー/未完履歴を変更しない。U-S1/U-F8のV5境界をT1実経路へつなぐ限定範囲を主担当が引き受け、T2規範や独立P-6の所有を取り込まない。

**採用対象はexact2だけ**: `backend/src/pitchlog/sync/first_ball_v5.py`（SHA256 `1364ce1cf3fc5d8562e9fc24d86868a7e049a63f4c7d79269c128d837137cd03`）と`backend/tests/test_sync_apply_first_ball_v5.py`（`5034c354c9bacd684f8b41797895a9ae987560c3a93336114a347078057b4e60`）。元base59c24e4bで両pathは未存在。manifest `d38522d1f06b0916a33685e9192ec8c0c7cb549c39b47b96d658664a65d9d4a0`、patch `fdad4ddd2a2a135266546792fb9dbd286a5677abb6239e840897c0caa89a04e8`が固定対象。作者first_ball_u1_independentの40成功/Ruff/format/tyと6非等価変異拒否は作者資格のまま、非作者product_supply_independentの最終63d30e11b4d640aeba7038db9afce23c8c3e67e8638a1175a50b15a67a95574f/checks3d7d80498c6ac6f9347218b5f50968b330a3c70bc818a1fe1c804e4d982f1eb7（P0/P1/P2=0/0/0、独立40成功0.69秒・追加11拒否・独立4変異拒否・旧9path全byte保持）を採否根拠とする。旧中断checkpoint/未完レビュー記録を消さず、この後発の限定source確認と区別する。rootは実before/after・対象版・判断者・日時・根拠を記録して採用し、本人の逐行確認/署名を代記しない。

**閉じた対応**: exact `str` のwire安定ID`"1"`だけを、既`OPERATION_EVENT_PARTICIPATIONS`の番号1/正本名「毎球入力」/V5/DBliteral `play_input`から導出済みの`PLAY_INPUT_EVENT_KIND`へ解決する。bool/int/文字変種/別番号/内部literalをwire別名として受け入れず、入力を含まない固定例外で拒否する。数学・新規alias・第2のhash式・認可成功・保存成功を生成しない。本部品はprivileged同期核向けであり、registered Portのimport許可を変更しない。

**原値と順序**: `SyncRequest.from_payload`/`SyncEvent.v5`は受信した`"1"`を保持する。既`event_source`→`event_source_fingerprint`は原V5〜V11と欠落/nullを区別し、`operation_fingerprint`はその指紋＋path＋registrationを既単一実装で指紋化する。HTTPで先に`play_input`へ置換すると両指紋が変わるため禁止する。D5再掲/異内容・拒否原本・W2照合の原V5はそのままにし、DBliteralへの解釈だけを既⑦へ接ぐ。既認可/RG1→D5→権利→連番→内容/状態→O4の先行順・D5消費/UNKNOWNの扱いは変更しない。

**実経路はP2**: 毎球は既同期正本の論理位置参加と`GameScreenPitchEvent.PITCH_EVENT_PATH`に従いP2を用いる。以前の数学部品記録にある通常P1の仮定を実画面経路の根拠へ拡張しない。既P2のD2採番/O4を省略せず、本codecの採用だけでP2/HTTP/Portを接続済みとはしない。

**後続の別source範囲（今回未実装）**: rootが対象版を固定して別に実装指示するexact2は、既`backend/src/pitchlog/sync/prefix_path.py`と新`backend/tests/test_sync_apply_first_ball_v5_connection.py`。前者の`_event_kind`はrawV5がexact wire1のときだけ本helperで局所kindを得て既表へ照合し、それ以外は現行内部literal/型/拒否文言を保持する。同じ局所解決を⑦内のP2参加区分判定にも用いるが、未知入力を先に`_event_kind`へ流して既P2の拒否文言/枝を変えない。`_d2`/`_state_diff`/`_event_insert_token`/`_projection_event`は既`_event_kind`経由の解決を再利用し、`SyncEvent`やV7/V8をcodec理由で再生成・書換えしない。指紋source・HTTP・Port/registry・数学・保存SQLはこの後続exact2にも含めない。

後続受入では、wire1のDB列だけplay_inputとなり元V5/指紋/W2原値は同じ、旧内部literal/未知値の拒否理由不変、P2参加判定/D2必須・O4呼出不変、D5再掲/異内容・権利/連番拒否がcodec呼出より先、返却後/故障後の原event不変を確認する。既prefix/P2/apply/idempotencyの関連検査・旧assertを保持し、必要な実凍結値/行位置への影響だけを正式手順で追随する。新しい公開拒否IDや「全取消未確認でもD5未消費」の判断を作らない。

実Port/同writerの初期snapshot・T1/T2一回評価frame・投影原子保存・E-1 intake・記録後GET・実画面は別後続の必須義務。既request_fingerprint生成器の未供給は実Control caller前の限定照合依存であり、既数学や本pure部品の着手待ちへ戻さない。rootの実反映までsource2はcache候補であり、後続exact2の実装や保存成功をこの追補案から先取りしない。

2026-10-27 16:34 JST、PO委任によるCodex /root判断。追補案ADDENDUM SHA d1fbf224a150b6157e9e2249522d44a1e8998affcc52f4b3b646ed124f386331、計画非作者レビューe6fa19e4eb758136c62d25d76399934ac39dc14de4c2d49367d9ff946f92392e（P0/P1/P2=0/0/0）を根拠に、上記純codec exact2と別途の接合exact2の範囲を承認する。実装・正式統合・実DB接続の完了を意味せず、後続sourceは別固定版で独立レビューする。

2026-10-27 16:49 JST、PO委任によるCodex /root判断。0c970d1b起点の初球V5接合exact2、patch c9ea0c0949c2f99783b1145f1056173728b2194aaf8b0f0966f59d56ee756bfdを、非作者レビュー2f57acb9d6c013b56e000109eb4cb4a1a197fd751792ffc3c061c483f9fa6154（P0/P1/P2=0/0/0、独立95件・旧版対照33件）を根拠に採用。原V5・D5指紋・既拒否順とP2/O4を保持。実Port・HTTP・DB保存の提供または正式統合を意味しない。

### 初球T1/T2計算値のpure formatter単位（限定追補案・未承認／未実装）

既親ステップ2・操作単位追補の次の独立部品として、既`CombinedRequest`/`CombinedSuccess`の全計算値を閉JSONへ写し、同じ全値として読み戻す。単一TS計算/T2/23flag/履歴の意味は変えず、型/表現/値の照合だけを担う。既V5 codec/⑦接合と独立し、実writer/Port/DB/HTTP完成を本pure単位の着手前条件へ戻さない。T1/T2本体・全MVPの残義務を保持する。

**exact2**: 新`backend/src/pitchlog/domainrt/first_ball_projection.py`と新`backend/tests/domainrt/test_first_ball_projection.py`。既coreの`backend/src/pitchlog/domainrt/*`/`backend/tests/domainrt/*`で捕捉される。他source/既試験/契約JSON/TS/artifact/host/registry/API/DB/正本は変更しない。新しい計算契約を別に作らず、既`mvp-first-pitch-t2-connection/plan.md`の採用記録・typed caller・正式採用ABI/caseを一次参照する（契約中の生成当時AUTHOR/NOT_APPROVEDラベルは消さず、後発採用記録と区別する）。

**内部値の閉形状案**: `FirstBallCalculationValue`はexact4 keys `{formatVersion,artifactSha256,request,response}`。`formatVersion`は固定文字列`first-ball-calculation-v1`、`artifactSha256`は呼出側が明示する小文字hex64桁、request/responseは既DTOのalias wire全値をそのまま保持する。before全state/scoreboard・全rules、T1の既8member（countEffect、PA終了、batterDestination、runnerDefaultAdvance、outEffect、23statFlags、after全state/board、historyContext全要素/順序/差分/23flags）、T2の実評価済み非終了tag・evaluation_point・4家族根拠を省略しない。別名変換・整数の再計算・差分再生成・既定0/空配列/falseの補完・観測されない選手IDの生成をしない。artifact hashはhost検証済み実値を後続callerが供給すべき値であり、このformatterは値だけから実artifact利用を証明しない。

**API案**: `format_first_ball_calculation(request: CombinedRequest, response: CombinedSuccess, *, artifact_sha256: str) -> str`と、`read_first_ball_calculation(raw: str, *, expected_request: CombinedRequest, expected_response: CombinedSuccess, expected_artifact_sha256: str) -> FirstBallCalculationValue`の2入口。formatは同じ閉値をJSONへ写すだけ。readは独立に渡された期待pair/hashとの**全値一致**を必須とし、raw自身を期待値へ流用して「検証済み」にしない。optional期待値・部分一致・未知field無視・不一致時のraw採用を提供しない。expected pairの真正性/同一評価はこの値APIだけでは証明できない。正しく型付けされた偽pairを両方へ同時供給した場合に数学的に正しいと判定する機構ではなく、同値を保存/再取得できたことだけを示す。

既JSON parserのduplicate/nonfinite拒否・`_WireFrozen`/既decoderと`_check_frozen_members`等を再利用し、exact型・全field/alias・canonical decimal・strict boolを再検査する。モデルやその入れ子を強制変更した場合も黙認せず、responseの実型はCombinedSuccessだけを受ける。FirstPitchFailure/T2NotEvaluatedResponse（partial T1を含む）やokの0/1は候補へ昇格させない。format/readは新しい独立objectへ防御的に実体化し、元model/dumpの後発変更と相互aliasを避ける。比較はstrict検証済みalias wireのcanonical JSON全値で行い、PythonのTrue==1や順序無視の集合化で相違を潰さない（object key順だけはJSON同値、array順/件数は保持）。固定エラーには入力/raw/資格候補を含めず、原例外で値を露出しない。

| 受入群 | 具体例と必須結果 |
| --- | --- |
| 実単一artifactの正常全値 | 既12case中の成功4件`REAL-UI-R9-L9-DH`/`OLD-R7-NULL`/`OLD-R9-NULL`/`OLD-R9-NULL-DH`を既callerで一度評価し、その実結果→format→readと期待pairを全値比較。3規則family/両DH値を保持し、元case期待値/schemaとも従来どおり照合する |
| 未評価/既失敗 | 同12case中の非成功8件（R8/別延長/コールド/TBによるT2未評価、異結果/既B1/TB中/裏による既T1失敗）をformatへ渡して固定拒否。旧エラーを新成功へ補完しない |
| 型/形状/表現 | 各wrapper/入れ子の欠落・余剰・別名/重複・非有限・number/非canonical decimal・bool/0/1混同、unknown formatVersion/hash形状、非nullable欄へのnull・tuple要素の型不一致・非JSON/型偽装を拒否。既ABIが許すnull（extensionLimit/tiebreak/runner destination等）と正規tuple（空tupleを含む）は保持し、tupleとJSON arrayの可逆な対応・要素順/件数を全値比較する。nullやtupleを一律拒否せず、既ABIを狭めも緩めもしない |
| 23flags/after/履歴の全比較 | 実成功値から各23flag・after scalar・history kind/順序/件数/前後値/差分flagsを1箇所ずつ変更し、型に適合する変更でも固定expected pairに対するreadを拒否。部分一致やfield除去変異を生存させない |
| T2/rules/出所値 | R/L/DH・T2 tag/evaluation_point/4family根拠・artifact hash・request beforeの各差替え、別成功caseとの組合せを固定expected pairとのreadで拒否。Pythonで終了条件を再判定しない |
| 不変性/故障 | 元model/dump/返却値の後発変更が既JSON/別返却へ混入しない。強制field追加/欠損/偽instanceを拒否。取得失敗を保存候補へ補完しない。format/read中はhost/DB/Port/ファイルI/Oへ到達しないことも対向で確認 |
| 非等価変異 | field落とし、23flag部分一致、history切捨て/順序無視、T2省略、partial成功化、期待値照合迂回を実source変異で検出。既T1/T2/JSON/hostの関連検査を保持 |

**後続DB/Port境界**: 本DTOはReady/rights/nonce/実writer資格/数学評価証明/保存ACKではない。format/readの成功から認可・同一評価・実保存・T2全成立を導出しない。後続privileged bridgeが①同じ生存writerで真正N2 before/rules/名簿を読む、②固定hostの単一T1→T2評価からexpected pair/実artifact identityを得る、③同writer/event/D5へ私有束縛し1回だけ投影へ消費する。registered Portはhost/DB/transactionを推移importせず、guard拒否を緩めない。formatterの型だけをprivate証明へ変換しない。

DB格納先・V7/V8写像・D5/event/request fingerprint・HTTP wire・保存後GETの真正expected取得は本単位では確定/実装しない。後続で実保存row/slot/D3/PlayRow/FKをbounded照合し、元受信値/既指紋式を変えず同TXへ接ぐ。再取得のexpectedは生の保存blobだけから自己承認させず、真正原本と実単一artifact又は正式に受理した同評価証跡との結合を別途閉じる。純値往復をDB再読込/1球保存の完成と扱わない。

本追補の計画確認・rootのPO委任承認後に上記exact2へ着手し、対象版/全前後SHA/非作者source review/関連検査を固定して採否へ返す。現在は案の作成だけで、実装/正式採用は未実施。全T1/取消・訂正/成績CSV/故障・復旧/実機などMVP全体の完成条件は維持する。

2026-10-27 17:12 JST、PO委任によるCodex /root判断。追補反映1 SHA ac0f07b0d95ae31610675ba49ae0086227e13615fa09872b3d0b3fcc0ac28bec、非作者第1回898b96e2…のnullable/tuple P2を採用し、第2回6dd2b88fb88348ac7478e4b2263fabf14fcf2349d48d7f080631c7e8a9af94c8（残0）を根拠に上記exact2の計画を承認する。sourceの実装・レビュー・採用および実DB保存は引き続き未完。

### 初球の実Port・同writer保存・記録後GET（単位1を限定承認）

既親ステップ2の操作単位追補を、最初の `batting-result.ball` 一球の実経路へ具体化する。T1/T2数学/23flag/取消・訂正/全MVPの意味・品質を変えない。根拠は既T1計画86～117、443～末尾のpure保存値追補、`mvp-first-pitch-t2-connection/plan.md`、data-model4-2/5-2/5-3/M03、sync-wire-schema/design.md N-8。本案はcacheだけであり、rootが非作者計画確認・PO委任判断を対象版/日時/根拠とともに記録してから、その単位のsourceへ着手する。旧レビュー/P2是正/未達履歴を保持する。

**固定読取基線**：writer-binding HEAD `f581c148974e6954e196554a2e69146594d1b202`。先行のpure `domainrt/first_ball_projection.py` exact2は別担当/既承認単位を維持し、重ねて編集しない。以下は小単位ごとにsource固定→非作者確認→root反映を行う。正式登録・共有assetの書込はrootが直列化する。

#### 単位1：同writerの私有評価frame（最初に着手できる製品単位）

**exact4候補**：新 `backend/src/pitchlog/sync/first_ball_frame.py`、新 `backend/src/pitchlog/sync/first_ball_bridge.py`、新 `backend/tests/test_sync_apply_first_ball_frame.py`、新 `backend/tests/test_sync_apply_first_ball_bridge.py`。

- frameは元event/D5・原指紋・tenant/game/generation/D1・同じ生存writer・真正before/rules/roster・検証済artifact identityと、既CombinedRequest/CombinedSuccessの実pairに私有束縛する。発行者はprivileged bridgeだけ。型が同じなだけのDTO、偽pair、別writer/別event/別D5、失効writer、再使用frameを拒否する。formatter/readの成功を数学/権利/保存の証明へ変換しない。
- bridgeだけが実 `_TenantTransaction` を受け、既 `read_initial_started_snapshot(handle, game)` を同handleで再利用する。snapshotの全不在確認（event/slot/PlayRow）を保持する。read時に真正before/保存rules/名簿を確保し、既 `evaluate_first_pitch_with_continuation` を**一回だけ**呼ぶ。別Session・別transaction・先読みHTTP snapshotの転用・固定結果は不可。初期名簿の既検証を二重実装しない。
- registered Portがhost/transaction/dbを推移importできない現guardを維持する。host呼出しはprivileged bridge側に置き、Port側はSQLなしのtokenと私有frame、coreが発行した閉じた呼出入口だけを扱う。任意の外部callbackからframeを発行・bindできるAPIは作らない。exact型・発行元・同writer/lifetime・登録表を検査する。kernelからbridgeへのbind位置/opaque入口の具体型は本単位の型レビューで固定し、dynamic importやguard例外で通さない。
- この単位の受入は実artifact一回評価、同writerの実read構成、frame拒否・失効・再消費・partial/host故障対向。実DB接続がない試験はpure/transaction double資格と明記する。次のkernel接合前に本単位のsourceを非作者へ渡す。実Port/保存の完成はまだ主張しない。

#### 単位2：初球V7/V8の閉写像（野球意味を増やさない）

**exact3候補**：新 `backend/src/pitchlog/sync/first_ball_payload.py`、新 `backend/tests/test_sync_apply_first_ball_payload.py`、既 `docs/features/tsk544-t1-state-calculation/plan.md` の写像表への最小追記（root専有）。必要なfrontend DTO側は単位6で別指定する。

- N-8はV7/V8の種別別内形を各イベント実装単位へ委任する。wire一般objectを「既に閉じたpayload」と扱わない。実装前に**V7のexact member/形式版とV8のexact member**を一枚の型表で固定し、既CombinedRequest/Success・pure FirstBallCalculationValueとの全field対応を非作者が確認する。この型の具体化は委任内、未確定の野球意味は採用しない。
- 採る関係は、V7に記録員の実入力（球種key/正式result key/正規化コース/任意球速等）と再現に必要な実評価値を欠落なく保持し、V8に当該一球の新confirmed-playのdifference（変更state/boardのbefore/after＋全23flags）を対応させる。historyContext全stackをV8へ重複保存しない。T2の評価済みtag/4家族根拠、after全state/board、artifact版、request before/rulesをどのV7 memberへ置くかは型表で明示し、本案の語を仮のwire名として実装しない。
- raw SyncEvent/V5/V7/V8と既D5指紋式は維持する。受信後にV7/V8を実計算値で黙って上書きせず、送信された値と同writer実pairの全値一致を内容検証で確認する。整合しないものを仮成功にしない。初回のrequest作成側は同じTS核を使い、サーバー検証とコピー計算を作らない。
- first-ballだけの型/規則scopeを明示し、course/球種等の既FR-002必須観測を省略しない。未入力球速を0へ補完しない。観測不足/未知key/部分23flags/partial T2は拒否する。T2未評価等を既B3理由や取引故障へどう運ぶかは既契約に照合し、新公開拒否ID/D5消費規則を創作しない。受理済みclosed ABI外の試合規則を固定falseで通さない。

#### 単位3：PlayRowの閉insert/readと既イベントidentity利用

**exact4 source候補**：新 `backend/src/pitchlog/sync/first_ball_tokens.py`（SQLなし値型）、新 `backend/src/pitchlog/repositories/first_ball_operations.py`（固定SQL/registration）、新 `backend/tests/test_first_ball_operations.py`、新 `backend/tests/db/test_first_ball_projection_atomic.py`。

- 既 `OperationEventReadToken(game,generation,D1)` は全列/idを同tenant・現行行条件で返す。event INSERT後に同writerで再利用し、D5/位置/行1件を照合してPlayRow.source_event_idを得る。新identity read/tokenを無条件に追加しない。
- PlayRowは既表/列へ投影し、wireV5=`1`・OperationEvent.event_kind=`play_input`・PlayRow.event_kind=`pitch`を混同しない。PlayRow.play_numberは投影の論理表示番号でありD2をコピーしない（M03）。初球=表示1を採る場合も真正な空試合確認と既採番規則へ束縛し、後続の汎用D1/D2番号規則へ拡張しない。
- tenant/game/source_event FK、同試合名簿からの打者/投手/捕手/打順、admin/tenant語彙の所属、値域/NULL/版/hidden属性を閉じる。23flags/T2/afterの専用列をPlayRowへ新設する前提にしない。正本はOperationEvent、PlayRowは決定的な投影のまま。
- `CAP:play_rows:insert` はproduct catalogに存在するが、tokenの実登録/許可とは別。rootが出力された最小registration差分を `backend/src/pitchlog/repositories/repository_contract.py` と `contracts/tenant_boundary/repository-contract.json` へ直列反映する。必要なら同時に供給するruntime登録/正式assetの**個々のpathと全値**を別固定し、包括的な全asset編集許可にはしない。既capability-catalogを名前だけで変更せず、app汎用grantを追加しない。
- 既Port文書が要求する適用核のDB印/トリガを、ContextVarだけで実証済みと扱わない。PlayRow実insertに必要な既DBguardの成立範囲を先に照合し、不足があれば**そのSQL/trigger/migration/正式body pathだけ**を別exact単位として非作者core確認後に追加する。既制約/tenant/RLS/FORCE/不可分性は緩めない。

#### 単位4：実Port登録とP2 kernel接合

**exact5候補**：新 `backend/src/pitchlog/sync/first_ball_ports.py`、既 `backend/src/pitchlog/sync/ports.py`、既 `backend/src/pitchlog/sync/prefix_path.py`、新 `backend/tests/test_sync_apply_first_ball_ports.py`、新 `backend/tests/test_sync_apply_first_ball_persistence.py`。単位1のbridge/frameの変更が必要ならその差分だけ別固定して担当を一本化する。

- **実RecordingRightsPortも別の接続依存**：現基線のPORT_IMPLEMENTATIONSは空、holds_recording_right等はProtocol定義だけである。旧U-R1の固定済み実Port候補が再利用できれば対象SHA/範囲を照合して採用し、無い場合は新 `backend/src/pitchlog/sync/first_ball_rights.py` と新 `backend/tests/test_sync_apply_first_ball_rights.py` のexact2を単位4より先の別小単位としてrootが固定する。実V12/current D4/復旧世代/保持端末/同writer結合、RG1の前後・commit検査は既U-R1/Control provider/tokenを使い、常時True・固定保持者・使い回しreadで代用しない。既providerのSQL/import閉包をPortへ持ち込まない。新しい権利意味やwireを作らず、本T1計算単位へ既UR1の所有を吸収しない。
- PORT_IMPLEMENTATIONSへ実クラスだけを明示登録する。既exact型・推移import・SQL/DB/host/transaction禁止を保持し、未登録型/派生型/危険importは従来どおり拒否する。port_guard.pyの禁止条件除外はスコープに含めない。必要なbindはprivileged coreに限定し、registered Portからhost/DBへimportで到達しない。
- 既経路を維持する：実認可/C2・RG1→D5再掲/異内容照合→記録権→連番→⑦の実snapshot/T1→T2一回評価＋V7/V8検証→O4/D2→同TX D5/event/prefix/PlayRow/無効化意図→⑧RG1→commit。登録検査やframeの空bindだけを先行しても、snapshot/readや数学呼出をD5/権利/連番の前へ移さない。
- 同writerのvalidatorが得た一つの実frameをprojectionで一度消費する。projectionへ渡るeventは既kernelによってC2参照解決と採番後D2へ写されるため、原eventのobject同一性だけを要求しない。元D5/原指紋/位置と、coreが許可したC2/D2変換だけを別に束縛して照合し、それ以外のfield差替えは拒否する。D5再掲/権利・連番拒否では数学/投影を呼ばない。OperationEvent保存とPlayRow投影が同じslot/event/実pairに属することを照合し、O4や途中故障ではframeを失効させ全rollbackする。D06とUNKNOWN/結果照会/後着遮断/全取消未確認時の扱いを維持する。別DB transactionを成功へ見せない。
- 初球以外は未対応として明示し、他操作の成功fallbackを置かない。これは狭い経路の提供であり、全T1/取消/訂正の完成ではない。

#### 単位5：保存後の真正GET（初期snapshotとは別）

**exact4候補**：新 `backend/src/pitchlog/repositories/recorded_snapshot.py`、新 `backend/src/pitchlog/repositories/recorded_snapshot_operations.py`、新 `backend/tests/test_recorded_snapshot.py`、新 `backend/tests/db/test_first_ball_saved_roundtrip.py`。最小read tokenがPortから使われる場合は値型を単位3のfirst_ball_tokens.pyへ追加し、同pathを他担当と並行編集しない。

- 初期snapshotの「event/slot/PlayRow不在」拒否を削らず、記録後専用readで同tenant/gameのcanonical event・slot/D3・PlayRow FK/有効版をbounded照合する。snapshotを得るreadの整合性と保存水位を明示し、他端末未送信値を混ぜない。最初のscopeは初球1件を明示し、未実装の複数行復元を初期0で代用しない。
- persisted blobだけをexpectedに自己流用しない。真正な開始原本/保存rules/正式artifactから再現した実pair、又は別途正式受理した同評価証跡との一致で検証する。新しいGET要求で再現評価することと、保存TX内の二重評価禁止を区別する。after/scoreboard/history/23flags/T2の全値とPlayRow一覧の実値を返す。
- 履歴順は世代連結順＋D1、表示順は正式論理順、DB WHERE/limit/ページングを維持。一般シーズン全件読込を実装しない。初球保存後に初期snapshotへ戻らない再起動対向を付ける。

#### 単位6：実HTTP・画面の最初の縦断（前単位と分けて固定）

**候補pathを次の境界確認時にexact確定**：新 `backend/src/pitchlog/api/schemas/first_ball.py`、新 `backend/src/pitchlog/api/routers/sync.py`、既 `backend/src/pitchlog/api/routers/games.py`、既 `backend/src/pitchlog/api/app.py`、既 `frontend/src/screens/GameScreenPitchEvent.ts`、既 `frontend/src/screens/GameScreenPitchCommit.ts`、新 `frontend/src/api/client.recordedGame.ts`、新 `backend/tests/api/test_first_ball_roundtrip.py`、新 `frontend/src/screens/GameScreenFirstBallRoundtrip.spec.ts`。現app.ROUTERSにsync routeは無く、既E-1核はsync/model.pyのfrom_payloadとsync/apply.pyのapply_sync_requestにある。新routerはこれらを再利用し、既HTTP候補（TSK-506）が別枝で保存済みなら、その実SHA/実装範囲を照合して先に再利用する。既frontend/src/api/client.syncEvents.tsのPOST /games/{game_id}/sync/eventsに整合させる。HTTPの認可/nonce/拒否群と正式route登録のexact差分は、本単位の型確認後に別固定してから着手する。backend/tests/apiディレクトリは現基線に無いため試験pathは新規候補である。

- 既本物の認証session/C2/tenant・記録権・nonce/RG1・既E-1 intakeを再利用。画面が同TS核で実観測からV7/V8を作り、durable queue内のD1採番/保持・既D5/再送を維持してP2へ送る。APIでrawV5/指紋を正規化上書きしない。
- 受入の最初の製品証拠は**画面新規作成→開始→初期記録権→コース/球種/ボールの実入力→1球実DB保存→再読込でballs1と同じ1行/履歴/23flags/T2を復元**。事前投入試合、固定成功ACK、純JSON往復、PlayRowだけの読取では代替しない。保存後GETは単位5を使う。

**検査と終了条件**：各単位は影響範囲だけを検査し、固定候補で非作者core確認する。実DB原子性/越境/再送/結果不明/権利失効/通信断復旧は隔離DB・専用port/一時dirで行い、共有DBへ適用しない。core/正式登録の全値・必要な7.7・必須CIを最終版で満たして通常統合する。実機/1試合リハーサルはPOへ接続先・データ準備・操作・期待結果・制限を引き渡し、未実施を完了へ読み替えない。最初の1球が通ってもMVP全体/全T1完了ではない。

2026-10-27 17:34 JST、PO委任によるCodex /root判断。追補案SHA43c8bc4b811b68c0eb7231b2c89e73b882d85c37082f9833f15bff52e73c2090、非作者レビュー66bf169a88cd82009c4b4466c778b50a5fe63a3f3792aa6151b8976fba5daf14（残0）を根拠に、単位1 exact4の着手のみ承認する。後続単位は候補であり、V7/V8型表・Port接合・登録・GET・HTTPの各実装前に対象と条件を別固定する。実Port/実DB/画面成功は未成立。

2026-10-27 17:36 JST、PO委任によるCodex /root判断。pure formatter exact2 source patch caa4c7cb718bde8bf8a3f94663bee8c4906d908deea0b82e102ba06f0798442f、非作者レビューcbe21556fe1e0a67186236cbb31a5e9bcaca1a6444336893aefdae3e7de43e01（残0、独立603成功・6変異拒否）を根拠に採用。実tree関連173成功。独立expectedの真正性・同writer・実保存・再読込の証明には使用しない。

2026-10-27 17:40 JST、PO委任によるCodex /root判断。単位1の同一artifact identityを評価結果と束縛する具体入口を限定追補する。既typed callerはhashを返さないため、privileged bridgeが既open_domain_hostを一度開き、同hostの検証済みsourceのUTF-8 SHAを取り、同hostでderiveFirstPitchWithContinuationを一回呼び、既decodeを使う。既typed callerと同じ要求実型・全frozen member検査を保持し、hash不一致・host故障は閉じる。同source同host・一回呼出・既callerとの全値一致を対向検査し、前後ファイルhashを実使用証拠にしない。exact4以外の変更・野球計算複製・実Port/保存成功の先取りはしない。

### E-1原wire指紋のpure部品（限定追補）

既親ステップ2・初球操作単位の次の独立部品として、現`docs/design/sync-protocol.md` 4-5「E-1 wire専用の内容同一性」（455–459）の既決規範を実装する。調査`e1-wire-fingerprint-investigation-20261027/REPORT.md` SHA c690dc7340445c79233297a6d34444bc1a0150275cac6992713d898152bbae2cを根拠とし、旧codec・既DTO指紋・保存済み指紋・D5/拒否順・復旧意味を変更しない。実Port/DB/HTTP完成をこのpure部品の着手条件へ戻さない。

**編集所有**：実装作者のexact2は新`backend/src/pitchlog/sync/wire_fingerprint.py`と新`backend/tests/test_sync_apply_wire_fingerprint.py`。既`sync/idempotency.py`/`model.py`/`apply.py`/`prefix_path.py`/`rejection.py`/旧codec/TS/registry/HTTP/DB/正本は変更しない。契約側の最小新規候補は`contracts/state-transition/wire_fingerprint_vectors_v1.json`（新規1資源）。作者はcacheだけへ作成し、正式contracts/Git/親planへの適用はroot唯一writerとする。正式vectorを伴う3資源の前後集合と、core-areas既`backend/src/pitchlog/sync/*`・`backend/tests/test_sync_apply_*.py`・`contracts/state-transition/*`捕捉を照合する。正式vectorの実producer/consumer検出・既凍結対象への影響があればrootが既CLIで実導出する。scan除外・文字列分割・既検査の免除で通さない。

**公開値API案**：

- `freeze_wire_event(raw_event: Mapping[str, object]) -> WireEventValue`
- `wire_event_fingerprint(event: WireEventValue) -> str`
- `wire_request_fingerprint(*, game_id: str, d4: str, events: tuple[WireEventValue, ...]) -> str`

WireEventValueはJSON object全体の防御的な再帰不変snapshotで、認可/Ready/nonce/実writer/数学評価/保存証明ではない。既`freeze_json`と`source_fingerprint`を再利用する。受信後の未変換JSON値が入力前提であり、DTO/DB/規則から欠落欄を補完しない。JSONテキストの読取/duplicate-key受付分類はこのAPIへ新設しない。rawを作る実HTTP parserと送信body耐久保持は後続供給のままとする。

freezeは原eventのキー/値をすべて保持し、再帰的に別objectへ移して元dict/listとのaliasを切る。JSONのnull/bool/int/finite float/str/object/arrayを保持し、array順/件数を変えない。tuple/MappingProxyへの内部不変化はJSON array/objectとの対応だけとする。型変換、Unicode正規化、大文字小文字/UUID修正、文字列数値化、float→int化、未知fieldの削除、登録DTO生成は行わない。S-2で拒否される未知event_kind、数値型違い、欠落/null、registrationの不正JSON値も意味検査せず保持する。JSON外のPython値、非文字列object key、非有限値、UTF-8へ表現できない値は既正規化器に従い失敗し、別の値へ修復しない。これらの例外をHTTP/S-STOP/O5等へ割り当てる判断はしない。

**event指紋**：既`source_fingerprint`へexact3 `{codec_version: 1, wire_event: 原event全体, registration: 原event内registration又はnull}`を渡し、戻り値へ`wire-v1:`を付ける。codec_versionはexact int1固定でcallerの別版を黙認しない。registrationが存在すれば元event内にも同じ原値を保持する。欠落時の外側registrationはnullだが、元event内にregistration:nullがある場合とは異なる指紋になる。自由なregistrations引数/DB値/意味変換後eventで補わない。

**request指紋**：exact4 `{codec_version: 1, game_id: URL束縛正規形UUID, d4: 要求D4文字列, events: D1昇順のevent専用指紋配列}`を同じ正規化器へ渡し、`wire-request-v1:`を付ける。各event hashは原snapshotからこの部品が計算し、callerの自由なhash列を受けない。元events tupleを並べ替えず、複製した参照列だけを正規D1順にする。要求入力は既S-1成立済みの非空E-1イベント列を前提とする。URL game_id/要求D4の正規外形、各D1のexact int・正のsafe integer・重複なし・各eventのgame_id/D4一致を既S-1定義と照合し、違反時は指紋を返さない。boolをintとしてsort、欠落D1への0補完、文字列D1の数値化、同値D1の任意tie-breakを行わない。既S-1外形条件を新しい意味仕様として再裁定しない。S-2のevent_kind/payload/state_diff等はrequest指紋の成立前条件へ追加しない。

V12/認証資格/現在の原本・経路/結果/理由/attempt_id/停止参照/再開許可はwrapperに加えない。wire event内の送信済み原値から対象fieldを抜く実装にはしない（既S-1が要求レベルfieldの誤配置を拒否する境界は別）。既`event_source_fingerprint`/`operation_fingerprint`を呼び替えたり、同じD5の既legacy領域を新wire領域へ相互一致させたりしない。

**正規化・例外**：`source_fingerprint`のsort_keys/ensure_ascii=False/UTF8/空白なし/allow_nan=Falseをそのまま使い、独自の第2正規化器を作らない。配列順、欠落/null、bool/int、int/floatを区別する。1と1.0は異なり、Python JSON読取後の1e0と1.0は同じ。Python自身のdict全値比較（True==1等）をhash同一性判定へ使わない。入力/raw/資格を例外文字列・原例外chainへ露出せず、固定の専用例外を`from None`で返す。失敗を空hash/既定event/保存候補へ補完しない。計算中にhost/Port/DB/network/ファイルI/Oへ到達しない。

**正式vector候補（最小新規1資源）**：固定version、規範参照、試験ID、原JSONテキスト（数値lexemeを残す）、既Python規則で読んだ入力のcanonical JSON文字列/UTF8 SHA、event/requestの固定期待hashと同一/相違関係を持つ。正常な初球用synthetic例はV7/V8の正式投影契約を代用しないと明記する。期待値は試験中に製品関数で生成せず、非作者が原入力から独立に全byte/全hashを再導出してrootへ渡す。正式配置前のcache vectorや旧review-example-onlyの7hashを、正式contracts受理と呼ばない。整数/実数を同一にする新規仕様は作らない。

| 受入群 | 具体例と必須結果 |
| --- | --- |
| 基本と全値 | 原wire/event wrapper/request wrapperのcanonical byteと固定hashが正式採用vectorへ一致。元event key順/Unicode escape/空白だけの違いは同じ。wire-v1/request-v1の領域を混用しない |
| 欠落/null・登録 | payload/state_diff等の欠落とnull、registration欠落とnullを区別。registrationのfalse/数値/array/不正objectもそのままeventと外側wrapperへ保持。自由な登録引数・DB補完はAPIに存在しない |
| 数値/文字列/順序 | 1と1.0、trueと1、-0.0と0.0、array順/件数、Unicode正規化前後を区別。1e0と1.0は同じ。1e-6/1e-7/1e20/大整数、整数に見えるobject key10/2、BMP/非BMP key順を既Python規則で固定 |
| S-1とS-2の分離 | 正規D1順以外のイベント並びでも同要求hash。重複/欠落/型違い/範囲外D1、別game/D4、不正URL UUIDはhashを返さない。未知event_kindや不正S-2 payloadは意味変換せず別hashを生成し、正規値へ直さない |
| 除外値と原本不変 | 要求のV12/attempt等を変えてもhash不変（wrapper引数に持たない）。受信原wire V5番号を内部literalへ変えれば別hash。後発の元dict/list変更がsnapshot/hashへ混入せず、元tuple順を変更しない |
| 不正型/故障 | JSON外型、NaN/Infinity、UTF8不能、強制変異/偽instanceを固定例外で拒否。原入力を例外に出さない。旧指紋の再計算/保存/原本読取を呼ばないことを対向で確認 |
| 非等価source変異 | wrapper field落とし/原V5上書き/registration補完、欠落null同一化、int/float同一化、D1 sort除去/array順無視、prefix領域混用、未知S-2削除、不変化省略を試験が検出する |

**JS互換性の制限**：JS標準JSON.parse/stringifyだけでは本v1と互換でない。実調査で1.0→1、-0.0→0、1e-6/1e-7/1e20の表記差、safe integer外の丸めを確認した。既定sortのUTF16順、sort後objectの数字key再列挙も一致しない。このpure実装はサーバーPythonの正本規則だけを供給し、TS canonicalizerやlossless parserを新規実装しない。初球の正規生成値をsafe integerとdecimal文字列等で表すことは可能だが、公開E-1の任意不正入力を新しい範囲制限で消して同等性を偽らない。clientが指紋を供給する確認口の接続には、元body/codec版の耐久保持と同じv1結果を得る受渡しを別途閉じる。直列化規則を変えるなら既正本どおりcodec版変更が必要であり、この単位では変更しない。

**後続の未提供境界**：E-1 HTTP/raw parser、SyncEventBatch/実公開混在単一ACK、認可/RG1後の全D5分類、未使用D5の当該D1位置での原本解決、T8/T9/accepted/recheckの全保存経路へのwire領域接合、request hash→AttemptBinding・event hash→EventPhaseBinding/D5の同writer私有束縛、端末送信前body/版耐久保存・停止/再起動/再送は別source単位。旧自由なfingerprint引数を公開して真正性を代替しない。formatterやこの値型から認可/実数学/実保存を証明しない。DB格納先・V7/V8正式写像・原指紋との実照合・保存後GETも本単位で採用しない。

rootのPO委任による対象版付き計画確定後、作者exact2とcache vector候補へ着手する。正式vector/必要影響値はrootが独立全値照合を経て反映し、候補固定版のsource非作者レビュー・関連既指紋/S-1/旧D5回帰・非等価変異を閉じる。正式vector未受理を完了とせず、実E-1/HTTP/Port/DB接続・最初の1球保存/再読込・全T1/P6・MVP完成とも別に報告する。本案は未承認・未実装である。

2026-10-27 17:40 JST、PO委任によるCodex /root判断。追補案c6485e5c16bd7d737f339d48e5982961583d73eb5993d0976fd39e17f25dac26、非作者レビュー984bc4b1d95c607bb750be4de80b1523bc3b772e2e6e8d41d9c4fa274c14b248（残0）を根拠にpure実装exact2とcache vector候補に限り着手を承認する。正式vector・HTTP・端末・保存は未成立、正式資産反映には独立全値照合が必要。

### 記録世代の同期読取列契約の是正

2026-10-27 17:45 JST、PO委任によるCodex /root判断。開始処理との実接合で、同期repositoryが保護列を除く12列を返す一方、同期consumerが追加後のモデル全14列を期待し失敗する不一致を修正する。編集範囲はbackend/src/pitchlog/sync/{tokens.py,apply.py,prefix_path.py}、backend/src/pitchlog/repositories/sync_apply.py、backend/tests/test_sync_apply_{prefix_path,apply,rejection,operations_boundary}.py、backend/tests/db/test_sync_apply_operations_boundary.pyのexact9。既12列の順序をSQL依存のない単一契約へ移し、read/number/lockと両consumerが共有する。proof_digest/recovery_generationを公開せず、既tenant・認可・記録権・SQL条件・FOR UPDATE・拒否順を維持する。テスト用14列行は実契約へ追随し、3 tokenの全列順・保護列非投影・同lockを純検査と隔離実DBで確かめる。非作者core review、影響検査、対象版の証拠後に採用し、CI全件や記録権の提供をこの修正だけで成立としない。

2026-10-27、PO委任によるCodex /root判断。上記列契約の実DB試験は既operations_boundaryに外部DB供給分岐があるため、同path追記を取りやめ、新規backend/tests/db/test_sync_generation_projection_owned.pyへ限定する。既owned fixtureと実Cookie/app scopeを使い、共有DBへ接続しない。他の範囲・保護列・独立レビュー条件は維持する。

2026-10-27 18:15 JST、PO委任によるCodex /root判断。wire指紋source exact2 patch c011d05f37abcb7a967f7aca68fa1d6eda0753b4ecca8c89777552710bc7d119および新vector f2a1e9fb9557d72eeabe14bb5980be2efcd6aef706912ef74fbe960aae722487を、非作者レビュー1a0767a707e04119cba90ed845f8f42eedb20c7553ea229b050a1b0a90d98a02（残0、製品importなしevent32/request8全値独立再導出・100件）に基づき採用。既正式9資産の実external依存は変わらず、既7.7再受理は不要。実tree100件成功。新規vectorの適用はPO委任判断でありP6 blind・本人署名ではなく、旧全viewの未登録30pair/実E-1接続・端末/DB耐久性/必須CIは未解消。

2026-10-27 18:26 JST、PO委任によるCodex /root判断。初球同writer frame/bridge exact4反映1 patch 1c51d31b067c4f9d2989c7ceca97d9e4107e3c51914c5599c9b3b7cbf9a0edd6を採用。非作者第1回f66a84ae…の実TX寿命P1を既writer lifetime検査で是正、第2回3bff1bbaab00c19adadce80dba714d835a57a8c9712ccc1ace13dbbc03a59177残0、独立62成功、実tree58成功。実Port・実認可・DB・HTTPの接続は未成立。

### E-1 raw wire指紋のcore接合（段階1のみ限定承認）

未承認・未実装。観測WT feature-mvp-first-ball-writer-binding、HEAD57d198d6013282ea71292103d3505992d41b4479。HEADだけでdirty差分を除外したとは言わず、実読取18資産のSHAをobserved-source.jsonへ固定した。repo/Git/DB変更0、DB/pytest/CI実行0。新しい野球意味の判断なし。既親T1 planの操作単位追補へrootが採否・所有・独立レビューを記録するための候補であり、これだけで実HTTP/Port成功とはしない。

## 現実装と既決条件

sync-protocol 4-5「E-1 wire専用の内容同一性」は既決。pure wire_fingerprintはeventをwire-v1:、要求をwire-request-v1:で生成できる。原event内registration（不正値も含む）以外から登録側入力を補わない。V12/現在の経路/結果/拒否理由を指紋へ追加しない。DTO入口と保存済み指紋を変更/移行せず、別領域同D5はDI3/B3bとする。

現在SyncEventにはregistration/raw snapshotを保持する欄がなく、旧from_payloadはregistrationを未知keyとして拒否する。旧SyncRequestは一要求一pathであり、公開E-1の混在要求全体を既pathへ先に一括決定できない。既506枝も確認したが、この実WTにsync HTTP routerは存在しない。古いwire_codec候補や読取済みDB行から原wireを復元して真正入力とはしない。

apply._preflight_d1はoperation_fingerprint(event,path,registrations[event.d5])で全D5を分類する。prefix_path._apply_lockedとrejection._apply_lockedも別TX内で同式を再計算し、IdempotencyLedgerInsertTokenへ同値を渡す。idempotency.recheck_and_insert_result/insert_result_or_recheckはtoken.source_fingerprintを再使用するので、正しいtokenを渡せば競合再照合式の変更は不要。prefix_pathのaccepted台帳/T1とOperationEvent/T2、D3/T3、projection/T4、mapping/T6、通知intentは同TXのまま維持する。

T8/T9はrejection._commit_resultが台帳と原本を同TXへ書く。ただし_originalはevent_source(event)というDTO再構成にoperation_fingerprintを付けるため原registration/未知S-2値を失う。prefix_path._require_rejected_originalは同game/D4/D1/拒否種別/D2継承と原本指紋対台帳を検証する。wire原本を保存するだけでこの既読取互換は閉じない。_original_fingerprintの旧fallbackを新wire envelopeに流用してはいけない。

ordering.apply_p2_eventはprefixの共通局所経路を呼ぶ。P3/change_pathは独立で旧operation_fingerprintを用いる。今回のE-1/D1接合でP3をwire領域へ無断変更しない。bridge._fingerprintも旧operation_fingerprint(event,'P2',None)を用いるため、最終kernelだけwireへ替えるとframeとの同一性が分裂する。

順序は①認証/S-1受付（HTTPの所有）→③自tenant試合認可→③-a RG1→④全D5内部分類→⑤未使用の記録権→⑥D1順/欠落→⑦当該位置の内容/状態/実評価→原子保存→⑧RG1再確認。保存済み結果は現在V12や原本を読み直さず再掲。rejected_d5の元経路を必要とする未使用だけ、そのD1位置で不変拒否原本を読む。後方原本不良をpreflightで検出して前方を止めない。既D06/O4と結果不明/再送条件を変えない。

## 推奨段階とexactpaths候補

各段階でrootの計画採用・core非作者レビューを行う。初球の狭い新規P2成功を先に実装できるが、T8/T9/競合/再掲のwire同一性が未接続なまま公開E-1を開いてはならない。未実装variant/登録は既G-Fで閉じ、成功応答を返さない。

### 1: 原wire request sourceの閉部品（pure、先行可能）

新backend/src/pitchlog/sync/wire_source.pyと新backend/tests/test_sync_apply_wire_source.py（exact2）。既wire_fingerprintを呼び、URL game/D4/codec1・原event tuple・D5索引・D1昇順索引・request/event指紋を防御的不変化する。constructor自由呼出しやdigest文字列引数で真正性を作らず、純粋値とHTTPが発行する受付資格を区別する。任意型registrationをrawのまま保持し、正規PlayerRegistrationは⑦当該位置でその同じrawからだけ作る。未知S-2を削らず、S-1と内容拒否を混同しない。

最初のexact2は値検査だけで、実HTTP資格を発行したとは言わない。既model/idempotencyとDTO型は変更しない。要求sourceと実認証contextを結ぶ私有受付issuerは次の実入口単位の責務として明記する。

### 2: D5 source選択と原本codec（pure+局所core、未公開）

新backend/src/pitchlog/sync/wire_original.py、新backend/tests/test_sync_apply_wire_original.py、新backend/src/pitchlog/sync/source_binding.py、新backend/tests/test_sync_apply_source_binding.py（exact4）を基本案とする。rootが既ファイルへ統合する場合も同一範囲に限定する。

wire sourceはopaqueな私有資格とし、認証contextのtenant/整合proof、実request identity、raw event index/D1/D5/game/D4/codec、request/event指紋、raw registration、内容検査用eventへの損失のない写像を照合する。type(str)digestだけ、caller指定registration、公開fingerprints tuple、DTOからrawを再構成する代替は受け付けない。S-2型違いもhash比較は厳密でbool==1等のPython同値に頼らない。E-1 sourceに他request/他eventを差しても発行しない。受付originを入口の実経路で不変に区別する。legacy専用入口だけ従来のDTO式を使う。E-1由来はsource資格の欠落・偽造・不正・期限切れのいずれでもfail-closedとし、DTO式へ降格/fallbackしない。任意のoriginフラグをcallerに申告させず、E-1実受付issuerが原snapshotと同時に束縛する。sourceなしをlegacyと推定してはいけない。

T8/T9向けは版付きraw原本envelopeを定義し、raw全値・wire fingerprint・必要な既W2識別を保持する。指紋を原rawから再計算し台帳と照合。旧DTO原本は既decoderのまま受ける。未知版/partial/余剰/改竄を拒否し、新wire原本を旧DTOflatとして読まない。元経路の解決は保存済み不変原本の既規則だけで行い、推測しない。物理JSON列に収まるか既token/型/DBACLを確認し、不要なmigrationを追加しない。

### 3: 全D5 read/writeとwriter/frame接合（ここが不可分の実core境界）

既backend/src/pitchlog/sync/apply.py、prefix_path.py、rejection.py、ordering.py、first_ball_bridge.py（source exact5）と対応既tests/test_sync_apply_apply.py、test_sync_apply_prefix_path.py、test_sync_apply_rejection.py、test_sync_apply_ordering.py、test_sync_apply_first_ball_bridge.py（test exact5）。source_binding/wire_originalのaccepted APIのみに依存し、既operation_fingerprint/source_fingerprint本体を変更しない。idempotency.pyはread-only再利用を第一案とする。

preflight・局所再掲・accepted/T8/T9 insert・競合再照合・原本W2照合・bridge全て同じ原event wire fingerprintを用いる。request hashをD5へ書かず、旧DTOとwireの自動照合/再hash/移行を禁止する。取りこぼした一箇所を互換fallbackで隠さない。raw受付資格はrequest lifetime、実writer資格はイベントTX lifetimeとして分ける。preflightが返すwriterをイベントTXへ転用しない。

イベント局所で同じ実TenantTransaction/PortWriter/実top-level Session TX・tenant proofを捕捉し、既_writer_lifetime/_assert_writer_lifetimeと現live_writer_bindingを再利用する。AttemptBinding.request_fingerprintは計算済request専用値、EventPhaseBinding.event_fingerprintは当該raw event専用値。これらdataclass外形一致だけは真正性にならない。実controller lease/nonce、同writer identity照合を経て私有registryへ結ぶ。phase/D1/D5/位置/tenant/game/D4/codec/source/寿命の全不一致を拒否。別writer・終了/inactive/replaced/nested TX・改変event・二重消費を閉じる。

bridgeは真正wire sourceがある場合だけその同一event hashをframeへ保持し、原V5='1'/V7/V8・rawを上書きせず局所codec/実host1回評価へ渡す。DTO callerの既比較・旧fingerprintは全byte/全値保持する。registered Portからsource_bindingのprivileged DB/host importへ到達しない構造を守る。既Port guard/登録/トリガ/認可を緩めない。

この段階は現SyncRequest一pathの制約を解消しない。新規初球P2だけのprivate接合試験は可能だが公開混在E-1対応とは呼ばない。

### 4: 実E-1 intake/混在単一ACKと正式公開（別入口単位）

候補exactpathsは新backend/src/pitchlog/api/routers/sync.py、新backend/src/pitchlog/sync/wire_intake.py、新backend/tests/test_sync_apply_wire_intake.py、新backend/tests/test_sync_apply_wire_dispatch.py、および既api/app.py・sync/apply.py、同API試験。実route登録/認可registry/正式metadataはrootが既route registryと現506候補を照合して追加exactpathsを固定してから着手する。現WTに当該routerがないため、既提供済みとして扱わない。

実Cookie認証→S-1/raw freeze→認可/RG1→全D5分類→D1位置でlazy原本/経路解決、全体一ACK・停止規則を実装。SyncEventBatch候補/506成果を再利用し、未知未実装を成功扱いしない。API起動登録だけ/fixture成功/常時成功Portで実HTTP接合を代替しない。端末が元body/codecを耐久保持して再起動/結果照会/再送できる境界も別実装が必要。JS number/Unicode/指数表現の互換を既Python版と同一と決めつけない。

## 必須対向の最小一覧

A. pure既vector event32/request8を保持。registration欠落/null/false/数値/array/未知field、V5 raw'1'と内部literal、V7/V8欠落/null、1/1.0/bool、Unicode、array順、D1順、raw後変更、request/event領域混同を拒否/区別。
B. 全D5経路: accepted/rejected/evacuatedで初回hash=再照合hash=保存hash=再送hash、同rawはDI2（現V12無効/語彙変更/原本削除後も再掲）、同D5変更rawはB3b。wire対旧DTO同D5を自動互換しない。recheck一意競合で先着同値/異値の双方、非D5制約故障をO4/偽再掲に変換しない。
C. 順序spy: 無認証/S-1違反/越境はD5 readもraw原本readも0、RG1閉でD5 read0。後続不良rejected_d5を前方前に読まない。既D5再掲でrights/数学/原本解決0。D1gap、旧D4、⑤不成立、未知S-2/未実装variantの既拒否分類と原子性を維持。
D. 原本: raw全値/registrationと台帳digest一致、版/欠落/余剰/改竄/別game/D4/D1/旧D5/誤D2継承拒否。旧flat原本全既case保持。rejected_d5解決は不変原本だけ。
E. writer: E-1 originのsource欠落/偽造/期限切れはDTO selector呼出し0で閉じ、legacy専用入口だけ旧式の全値不変を確認する。caller origin偽装・E-1からlegacy内部関数への持込・例外時のDTO再試行を拒否する。raw受付資格の偽造/別context/別request/別event/別registration、phase position/D1/D5差、request hashとevent hash交換、別writer/別TX/失活/差替え/nested、二重消費を拒否。host評価は該当未使用イベント⑦だけ1回。変換event/保存projectionのhashをrawhashと取り違えない。
F. 実owned DB/HTTP（最後）: accepted T1..T6、T8、T9、各書込直後故障で全rollback、結果不明で照会/旧要求終結・後着遮断の既条件、実retry競合、tenant越境、非pool/同writer認証を実証。API成功とDB事前投入読取を区別し、初球画面入力→実API→実DB→GETを別到達点として記録。

## 検査/レビュー順

source単位ごと影響pytest/Ruff/ty/Port guard、正式CLIのproducer/consumer・core path・凍結射影/coverage/参照値をまとめて導出する。既正式9資産/7.7値が実際に変わる場合だけ前後値付き受理を追加する。独立core reviewはsource版・差分SHA・旧DTO保持と反例を記録する。統合候補が固まって必須全件CIを一回、同入力の赤を反復しない。現段階の所要時間は未算定（実506/SyncEventBatch採用版とsource_binding設計の独立確認が必要）。pure第1段階の着手を実HTTP/DB完成待ちに戻す必要はない。

2026-10-27 20:14 JST、PO委任によるCodex /root判断。計画反映1 SHA4fd984b64c03c34c6e0347bbb60f76f994be7f9e550d9cef528fc1719da214a6、非作者第1回2a1cb793…のE-1資格欠落P1を採用、第2回e634165f7dbadf0068afa336cec9061233598e3111f27a165b105d725f164758残0を根拠に段階1 raw source pure exact2の着手だけ承認する。E-1の資格欠落はfail-closed、legacy入口だけ旧方式。段階2以降・HTTP・全D5・同writer・実DBは未承認/未接続。

2026-10-27 20:21 JST、PO委任によるCodex /root判断。E-1原wire source段階1 exact2 patch 2a18bb8ebcb7499cc4be65e8eb3c19d89dc8619031f208967fd4d425eae6120eを、非作者レビュー5ba527e1cf8d4869d856454cc7de259d59054df351bd9612fd514069718c0afe残0・独立75成功/5対向に基づき採用。実tree関連175成功。pure不変値はS1受付・認証・origin・同writer資格ではなく、P3/旧DTO/全D5/HTTP/DB接続は未成立。

### 単位2：初球V7/V8型表の固定とpure閉codec（限定追補案）

既「初球の実Port・同writer保存・記録後GET」単位2だけを具体化する。新野球意味・旧拒否順/D5/保護列/認可/耐久性保証は変えない。既型表反映1の対象はcache first-ball-v7-v8-type-table-20261027/reflection1/manifest.json SHA6478dfd6509488b43c7e0128cfea4368e4e3ac95cdf57f22752de324c2081c3a、TYPE-TABLE.md SHAe5b4971fa54be2763db71b85507d40e296bea1742cf560a611c341c5aaecffac、type-fields.json SHA9555f1650b070b08539a7a20b9551f3c67d3f28818630d9b72c7028b649c80d3。全6資産の全SHA・全52member・既66DTO宣言/継承をTYPE-TARGET.json SHA72d2620c6731a5e9367880f2967a7771cc75e5c6e76a18052b988943ff2af921へ固定した。原典bf0822abから今回読取57d198d6013282ea71292103d3505992d41b4479まで該当16原典は全byte不変（primary-compatibility.json）。

非作者第1回75fee69d426f9c9f8b307e34f644bfd14ad9591c34fc141011e6b338c10669a9のP2（V7.response誤参照）と、反映1/第2回4ff42fdaf7a32a7d4fbac6a7c910b0ae2176047b9314e50dcb7861f05a0a79b8・checksd233b801b7c9943d5e5ded4ac7eb9db89bf5542ffb40e34566bf3da270cd8b1f（残0）を維持する。型表承認はpure具体化の資格であり、P6 blind/実装/実UI/DB完了ではない。rootはこの追補の実対象版・日時・判断者・根拠を「PO委任によるCodex判断」として記録してから限定着手を指示する。本人が実値確認/署名したとは記録しない。

**exact2 source**: 新backend/src/pitchlog/sync/first_ball_payload.py、新backend/tests/test_sync_apply_first_ball_payload.py。**必要vector1**: contracts/state-transition/first_ball_payload_vectors_v1.jsonのcache候補を同時作成。正式配置/親plan/7.7等はroot唯一writer。sync/*・test_sync_apply_*・contracts/state-transition/*の既core捕捉を照合し、producer/consumer新規参照の発見は既CLIで導出する。除外や検査緩和をしない。既domain DTO/TS/artifact/host/formatter/frame/bridge/Port/registry/SQL/API/UIは変更しない。

**閉形状（下記の省略をTYPE-TARGET全値への置換で解釈しない）**:
- V7 exact4 = formatVersion literal first-ball-play-v1、observations、participants、calculation。
- observations exact5 = pitchTypeKey(nonempty str)、course exact3(unit literal1/263・x/y canonical unsigned decimal string k0..263)、pitchSpeed exact2(kmh=符号付十進文字列又はnull・outsideRangeConfirmed=strict bool)、stance(decimal string1..25又はnull)、battingSide(右/左/null)。全key必須、nullableは型表で指定したmemberだけ。未観測を0/右/空配列へ補完しない。速度は非負限定/60..170硬拒否にしない。型表のregex/単位/確認条件は全値固定対象のまま、未知精度/Double投影をここで仮決めしない。
- participants exact4 = batterId/pitcherId/catcherId(canonical UUID strings)、battingOrder(初球scope string1)。client値は同frameに由来する独立期待参照へ全一致を要求するが、codec自身が所属/現出場を認定しない。
- calculationは既FirstBallCalculationValue exact4とCombinedRequest/Success全値を無変更再利用。打撃結果はcalculation.request.t1.resultIdの一箇所に記録者の選択を保持。初球batting-result.ball以外を成功へfallbackせず、T2未評価/partialは拒否する。
- V8は既HistoryDifference exact3(stateFields/scoreboard/statFlags)を無変更再利用し、calculation.response.value.t1.historyContext[0].differenceへ全一致。初球historyは既ABIの厳密1要素、V8に全stack/新wrapper/Readyを増やさない。全23flag・T1after全欄・T2のtag/時点/4根拠を省略しない。絶対boardはcalculation.response.value.t1.after.scoreboardへ保持、空差分を0scoreへ変えない。

**pure APIと保証の境界**: 閉DTOのformat/parse・V7/V8相互一致だけを実装し、parse/validateは独立に供給する既期待calculationと期待participantsへの全値一致を必須にする。optional期待値・raw自身のexpected流用・正規化書換えを提供しない。型適合の偽pairを両側へ同時注入すればpure値一致でしかなく、真正性は後続私有frameが供給することを明示試験する。raw SyncEvent/V5/V7/V8/既wire専用・旧D5指紋は不変。alias/型・bool-int・数値表現/未知fieldの不一致を黙って修復せず、固定例外で入力/原例外を表示しない。host/数学/Port/DB/network/file I/Oをcodecの実行から呼ばない。domainrtへ到達するこのprivileged codecをregistered Portのimport閉包へ持ち込まない。

**vectorと受入**: 1新規版付きJSONは型表SHA/原典ref・case ID・V7/V8原JSON・独立期待calc/participants・成功全値又は固定拒否分類を持つ。正式採用済みT1/T2の成功4ケース（3規則family）と非成功8ケースは既原典値を変えず再利用し、説明用synthetic観測/名簿はpure資格とする。未知key/省略/null/型/別alias/別participants/原V7V8差替え、全23flag/after/history/T2各改変、course端点0/263/未選択/範囲外、速度null/負/0/範囲外確認・stance null/1/25・両打実側の非推測を検査する。期待値は試験中に製品codecで生成せず、全case ID/件数と全値比較を凍結。候補vectorの非作者再導出とsourceレビュー後、rootが正式反映する。新P6 blindや正式型表未提示配置の拡張とはしない。

作業中はexact2 Ruff/format/ty・関連pureを実行。全値の落とし/比較省略/null補完/型変換/履歴切詰め・raw改変など非等価変異の検出を確認し、既formatter/first-pitch/T2/指紋/同期拒否試験・旧assetを保持する。最終候補を固定し候補作成非関与レビュアーへ渡す。正式vector/必須CI未成立を完了とせず、sourceの有効化はrootの採用記録後とする。

**後続留保（pure着手前条件へ戻さない）**: 現UI float座標→B7整数k/263/Y反転の単一TS接合、Double物理投影と速度精度/overflow/実設定確認、bounded語彙/名簿照合、真正同writer frame・1回消費とC2/D2変換、T2非成功の既公開拒否写像、実RecordingRightsPort/DB印/原子保存/GET/HTTP/端末body耐久は未提供のまま。PlayRowを先行実装する場合もD2をplay_numberへコピーせず、保護列/tenant/同TX/拒否順を変えない。これらの不在を型に適合した定数値・fixtureの常時成功で埋めない。MVP/全T1受入条件は維持する。

### 初球PlayRow insert：最小供給単位と保存依存

固定読取基線 `57d198d6013282ea71292103d3505992d41b4479`。既親plan単位3、実model/schema-manifest/正式DDL・CAP/tenant repository契約・既イベントread・確定済みFR-002/B-7を照合した。**SQLなしtoken＋未登録固定SQL宣言＋純試験のexact3は先行できる。実保存activationにはruntime登録とDB側適用印が別に必要。** 本packetはscope候補であり実装/正式採用ではない。

## 最小exactpaths

| 段階 | exact path | 供給するもの/保持する境界 |
|---|---|---|
| 先行A | `backend/src/pitchlog/sync/first_ball_tokens.py` 新 | SQLなし不変値型 `FirstBallPlayRowInsertToken` と必要なら同源限定 `FirstBallPlayRowReadToken`。host/DB/transactionをimportせず、値だけで認可・同writer成功を表さない |
| 先行A | `backend/src/pitchlog/repositories/first_ball_operations.py` 新 | canonical PlayRow Tableの固定INSERTと、tenant/game/source_eventへ閉じたLIMIT2 read宣言。登録tupleを宣言するだけでPRODUCT_OPERATIONSへ追加しない。独自の野球/座標計算なし |
| 先行A | `backend/tests/test_first_ball_operations.py` 新 | 全41列/SQL/bind/閉preflight/不正型・越境・未登録SQL0・上限の純対向。成功資格はSQL/row doubleまで |
| 後続root | `operation_registry.py` / 生成`repository_contract.py` / 正式`contracts/tenant_boundary/repository-contract.json` | 新token exact型・insert CAP1・read/insert operationだけを既prefixへ追加。DB印の拒否/正常証拠と非作者確認前にはruntimeを有効化しない |
| 後続 | `backend/tests/db/test_first_ball_projection_atomic.py` | owned fixture/実app/Cookie/正規scope・同writer bindingを使う原子性。共有DBやfixtureの常時成功資格へ接続しない |

既unit3のtest命名を維持する案。新repositories/*はtenant-isolationに捕捉されるが、sync/game-stateの意味登録をそれで代用しない。rootが新SQL/test pathのcore登録を既手順で直列処理し、必要な宣言先行/JSON別commitを維持する。元guardの検出/拒否/対象pathを除外しない。

## 全列の由来

**全41列を `all41-column-origins.json` に物理型・nullable/default・由来・FK/CHECK/PK/immutabilityとともに固定。** 型表の原典由来を再利用し、列を追加/削除していない。

| 列群 | 初球の供給源 |
|---|---|
| tenant_id / game_id | 生存した同writer contextと認可済URL/event/private frame。callerの自由tenant値をbindしない |
| id | 受理TX内で割り当てた新UUID。D5再掲では再投影/再割当しない |
| source_event_id | 同TXで既OperationEventReadToken(game,generation,D1)が返した新現行イベントのid。payloadの自由UUIDを採用しない |
| play_number | **真正empty初球の表示番号1という限定実装案**。D1/D2は表示番号ではない。D2をコピー/一般採番へ拡張しない |
| event_kind | このpitch-event scopeの`pitch`。wire V5=`1`、OperationEvent.kind=`play_input`とは別 |
| batting_order / batter_id / pitcher_id / catcher_id | 同writerの保存初期名簿・既単一TS射影からの期待参照と、V7 participantsの完全一致 |
| batting_side / stance | 実観測の右/左/null・1..25/null。両打を推測せず、0/右へ不足を補完しない |
| pitch_type_key / batting_result_key | 記録員が選んだ正式球種key・`batting-result.ball`。同tenant語彙/正式結果・有効性照合はFKだけで成立扱いにしない |
| course_x/course_y | 元eventに正準整数kと単位1/263を保持。既B7の単一TS/採用済み変換から物理投影値を受け取る。Pythonでk/263/Y反転を再実装しない |
| pitch_speed | 任意球速の欠損null・有限値。0/負値を未入力扱いしない。範囲外の実確認を60..170硬拒否で代替しない |
| version / hidden_at | 新規native projectionの初版1、可視null。再送upsertでversionを増やさない |
| import_batch_id / legacy_row_identifier / migration_unverified | native新規記録scopeに限るnull/null/false。移行由来を検証済みにする定数ではない |
| 他の作戦/打球/牽制/失策/press等 | この限定初球で非該当又は未観測のnullable欄はnull。入力された未対応観測は捨てず内容codecで拒否し、MVPから機能を削除しない |

先行Aは既に投影されたtyped値の保存形だけを受ける。物理Double列のcourse/球速に独自の算式/丸め/クランプを入れない。finite/range/UUID/型と固定scopeの検査は行うが、単なる値tokenを真正sourceの証明にはしない。

## 既OperationEventReadTokenとFKの閉じ方

既readは同tenant/game/generation/D1・replaced_at=NULLに閉じて全列を返す。新identity readは追加不要。PlayRowの既FKは `(tenant_id,source_event_id)→operation_events(tenant_id,id)` であり、**同gameのFKではない**ため、rowが読めるだけでgame/D5/実pair一致へ昇格できない。

insert前の同handle preflightで現行1行、id/game/generation/D1/D5/kind=`play_input`、replaced/retired/import状態、coreが確定したD2/許可済C2変換を照合する。既readがretired条件をSQLに持たない点もvalidatorで明示拒否する。必要な原指紋一致は既IdempotencyLedgerReadTokenの受理済D5/fingerprintと私有frame/nonce結合を用い、新hash recipeを作らない。generation/D1/D5/D2/原指紋等は検証用でありPlayRow新列やplay_numberへ転用しない。

新readが必要なら同game/source_eventのvisible/native行を最大2件だけ読む。先行AではそのSQL宣言に限定し、正式token/operation登録はrootの後続段階。INSERT結果1行とreadbackの全列/id/FKを一致させ、0/複数/別game/別D5/旧世代/retired/partialを成功としない。bounded readを全件走査に置換しない。

## 認可/DB適用印の不足

正式product CAPはplay_rows read/insert/update、正式ACLはpitchlog_app SELECT/INSERT/UPDATE、RLS+FORCEとtenant_owned ALL/WITH CHECKが既存。一方、tenant repository契約は現時点readのみ、insert token/operationは未登録。新insertのために新CAPやappの広いGRANTを追加する必要はないが、既DB権限があることは核の許可ではない。

**0006の既triggerはid/source_event_id/legacy_row_identifierのUPDATE保護だけ。ports.pyが明記する「適用核の印を要求するDB trigger」のINSERT保証は現取得した正式DDL/モデルからは供給されていない。** `_SYNC_APPLY_ACTIVE` ContextVarやPortWriter exact型の成功で代替しない。

実登録前の別最小unitで、既writer_binding/admissionの真正PG identity・同TX・tenant/game/D5/原指紋・nonce寿命/1回消費を使うDB側限定資格を設計・実証する。clientが設定できるGUCのboolだけを印にしない。SQL/trigger/migration/SECDEF owner/ACL/body/profileの具体exactpathと全前後値は、その設計固定後にrootが承認・正式反映する。既binding ownerへ必要性不明のGRANTや新汎用roleを先に足さない。本packetは新DBguardの実装範囲や正式受理を包括承認するものではない。

## 原子性と必要な受入

既経路を維持する：認可/C2・RG1→D5→記録権→D1→⑦snapshot/同TX一回T1/T2/V7V8照合→O4/D2→D5台帳/slot/event/D3→T4 PlayRow→無効化意図→⑧RG1→commit。insertは同じPortWriter/handleだけから実行し、Session/新scope/独立commitを開かない。実活性top-level TX ownerは採用済frame lifetime検査へ束縛する。

- pure: canonical Table/全列/bind/CAP/固定値・NULL・UUID/finite/未知field/別table・tenant混入・FK原本0/2行・旧/別event・未登録SQL0を検査。旧SQL/型/認可/拒否対向を保持する。
- owned DB: genuine初期名簿/開始/記録権・admissionから実eventと1行を保存、同TX全列readback。別tenant/game/nonce/権利失効/直接DML/別writer/結果不明/再送で拒否・二重行なしを確認する。
- fault: ledger/slot/event/D3/PlayRow/意図の各途中とcommit前RG1で、**business TX**の不可分rollbackを実観測。外部Controlの耐久監査/lease消費/UNKNOWN quarantineが残ることを全取消失敗へ読み替えず、反対にその残存を業務commit成功とも扱わない。全取消未確認でD5未消費/新D5置換を許可しない。

初球scopeに新たな野球意味判断は見つけていない。未決は①pure型表採用/観測・語彙供給、②B7/Doubleと球速の技術的投影接点、③DB核資格の最小SQL設計/登録、④実Port/GET/HTTP接合。これらは未登録の先行Aを妨げる追加の全体ゲートではない。DB activation/製品完成は成立扱いにしない。

本確認は原典のread-only解析。pure/source/DB試験は実行しておらず、repo/Git/正式資産/DB変更・起動0。全原典SHAはprimary-manifest.json、正式値の抜粋はcurrent-formal-facts.json、段階別pathはexactpaths.jsonへ固定した。

2026-10-27 20:26 JST、PO委任によるCodex /root判断。V7/V8 pure codec追補c56cd48ef0c65b5c6b33503d42d0b50305463760d7dd553c5a2f806fa17663f4、非作者d6cc1688e37287e4578cae7cfee196f6b9cf237dbff03111506a925fe7eda7f3残0を根拠にpure exact2+cache vectorのみ着手を承認。PlayRow scope588de14b06d5b065a62a95a39233cce02ac80e5b89b8c34bee086a36ebbff749、非作者06e611aa0808792b4d64266f424a7142aa7ec515359369c675e74d95d32e83ce残0を根拠に未登録token/固定SQL宣言/pure test exact3のみ着手を承認。両候補の正式採用にはsource非作者確認が必要。DB印/実登録/Port/HTTP/保存と再読込を成立扱いにしない。

2026-10-27 20:38 JST、PO委任によるCodex /root判断。未登録PlayRow token/固定SQL宣言/pure test exact3 patch6e5574191ee21b27fc7164f6ee842848a057df49354259c7fce22232ea627302を、非作者review c1c07a0b8f94ce3027923624a27a108e7d67f5c8cfadfff738d90db5971e7763残0・独立98成功に基づき採用。実tree98成功。同game/event/D5/ledger、tenant/限定read/D2非コピーを保持。未登録であることを維持し、実writer資格・DB適用印・実保存/GETを成立としない。

2026-10-27 20:47 JST、PO委任によるCodex /root判断。固定HEAD ba47a1d7c69276b744f93e0270dfb8ca58975a58を対象に、E-1段階2追補 `e1-source-selection-original-stage2-addendum-20261027/ADDENDUM.md` SHA-256 4b1202fdc23f92cc4cb2b497d28fd88a01cadef6b1f87a90da3c1b8f0444c93bを承認する。非作者plan review b02e229a99e7f67cf14d907ffd7148feb13029769fc4d1effce2ed85708dc894は重大・軽微指摘0、原典11点を実blob照合。対象は新 `backend/src/pitchlog/sync/wire_original.py`、`backend/src/pitchlog/sync/source_binding.py` と各対応新testのexact4に限定する。E-1真正receipt未発行では閉拒否、legacy専用入口以外への降格を禁止し、raw原本の型保持と台帳/スコープ照合を維持する。issuer・旧core接合・公開HTTP・DB耐久はこの承認に含まれず、PG roundtrip・非作者source/core確認を後続条件とする。

2026-10-27 20:51 JST、PO委任によるCodex /root判断。初球codecの既承認exact2に加え、作者作成の合成87caseを新 `backend/tests/fixtures/first_ball_payload_vectors_v1.json` へtest専用fixtureとして同梱し、testの当該読取先だけを変更する。元cache fixture SHA-256 d565c1d44a9ef13f13c4bf92525a52500920da5bf3dfa91bc70876cbfdf37b4dをbyte保持する。非作者review 98e1686a212771f915b9506afaca124c6c1d765f25477175451ca0143e497cfa はcache vectorを含む限定採否であり、正式contract/golden/P-6独立blind期待値として扱わない。正式12数学caseは従前どおり実artifactと既contractを比較する。実treeの対象検査、配置先差分と非作者確認を採用条件とする。

2026-10-27 20:54 JST、PO委任によるCodex /root判断。初球V7/V8 pure codec候補 `417852be` を限定採用する。作者source patch SHA 99b6b3faa83ea46c0e8607a95358cca53955cf15a011a52ca67edb1a3e6f4d6a、非作者review 98e1686a212771f915b9506afaca124c6c1d765f25477175451ca0143e497cfa 残0・独立479件/12変異、後発fixture配置とtest読取先の非作者確認 d695a28149a49a6795ef42eafcb726b359f389d2474334a74abc19b351e22f2a 残0・旧cache配置なし479件を根拠とする。root実tree479件/Ruff・format成功。synthetic fixtureは正式契約やP-6盲検ではない。真正writer/権利、原wire、Port/DB/HTTP/GETの接続・実端末検証は未了。

2026-10-27、PO委任によるCodex /root判断。E-1段階2 source4 patch SHA 08747620274c209aed0f9aba2b585a5a4aee9448fd94654bc231524ca71d98c8 を `a93e0e16` へ限定採用。非作者review 8712ca7be4c27a77fb29e2cffb6c5d054e41b723b3f48b3fd63ff51049368f32 残0・独立251成功・既553 byte保持・event32再導出を根拠とし、root実tree251件/Ruff・formatも成功。真正issuer未供給の閉拒否と旧方式への降格禁止は保持。実HTTP、T8/T9/D5 core、同writer、DB JSONB roundtrip、Portは未接続であり、1球保存を成立扱いにしない。

2026-10-27、PO委任によるCodex /root判断。DB側初球書込み印の反映2 `first-ball-db-insert-stamp-plan-20261027/reflection2/PLAN-CANDIDATE.md` SHA 1ba4db2b3e6b3eebbef8253fd75f6d5f232c7642a20e5150a3e4eb8fb038197d について、非作者review df253ad34bbe6dbddf9559be4166ac1df1d39e88b77ccd84f348b1aeab9d4089 と反映2追認 0a4fa2bfaa6999a5af259807fc1b8221c6bbdba9e9c627362208bb381ce4e964 を根拠に、unit Aの未適用source/pureだけ承認する。対象は `backend/src/pitchlog/sync/control_provider/writer_binding_models.py`、新 `backend/migrations/versions/0038_first_ball_write_admission.py`、新 `backend/src/pitchlog/authz/first_ball_write_stamp.py`、新 `backend/tests/test_first_ball_write_stamp.py` のexact4。実head 0037を確認。既profileへの実登録、正式契約資産、DB適用、trigger activationは含まない。device→right→consume順、同top-level TXとlock、偽装/失効/rollback拒否、既合法経路matrixと隔離PG対向は後続の必須条件。追加review後にだけsource採否を判断する。

2026-10-27、PO委任によるCodex /root判断。DB印unit Aの関連検査で、既 `test_alembic_environment.py::test_all_model_modules_are_discovered_and_registered` が新modelの走査未登録を検出（300成功1失敗）。既 `backend/src/pitchlog/db/writer_binding/models.py` のexact1pathをunit Aへ追加し、既単一 `FirstBallWriteAdmission` のreexport/同table参照だけを供給する。model重複定義・実DB migration適用・runtime/profile/trigger activationはしない。関連検査・非等価変異・独立reviewを完了し、当該失敗を成功へ読み替えない。

2026-10-27、PO委任によるCodex /root判断。E-1段階3候補 `e1-stage3-core-binding-readiness-20261027/PLAN-CANDIDATE.md` SHA fa582fa7f7a48413c76422c4b2998c0893f2c946ae1a2d22525cb72acf790b5b と、段階3計画非作者review 1c01cca8661936b3e44d0963bc35992194d5ab42dd9eba110e91ebfb7a21f5c2 P0/P1=0/P2=1を根拠に、3A-1の非発行accessor exact2（既 `backend/src/pitchlog/sync/source_binding.py`、既 `backend/tests/test_sync_apply_source_binding.py`）のみ承認。review P2の実broker `_phase_wire` position/d1/event_count各1以外の既拒否を保持し、複数位置はpure検査に限る。実broker拡張は別scope。3A-2・3B・issuer・HTTP・DBは未承認/未接続で、資格を発行するfactoryやDTO降格を追加しない。

2026-10-27、PO委任によるClaude主担当判断（Codex上限によりCodexから主担当を引継ぎ。本人署名・人間逐行確認ではない）。E-1段階3 3A-1 exact2の作者候補 `e1-stage3-core-binding-readiness-20261027/implementation-3a1/` source2.patch SHA 29b4bb639efb3071c1bebab6233f30513f11c96e8bb74c984420ec4f716a12fc に対する非作者review（Fable 5.1サブエージェント）`implementation-3a1/independent-review/REPORT.md` SHA baf65a4e6efc64390e8067f5e280af187c44db89d34dfcd105d414edf3e626eb はP0/P1=0/P2=3、独立165/関連587成功。P2-1（描画中の選択実体差替えの試験空白）は試験1caseを追加して閉じ、実装の同一性検査を外す変異で当該caseが失敗することを確認（cc676e8d、source SHA 54455497…、test SHA 66653983…、関連588成功）。P2-2：`_LegacyState.context`・`_Selection.entry_context`・`legacy_dto_source`のkwarg追加は計画本文に明示のない最小拡張だが、未束縛legacyを新accessorだけで閉拒否する方向でありABIは不変のため、本判断で範囲内の最小追補として追認する（`legacy_dto_source`のbody不変は成立しない）。P2-3：返却値はhash不可でset/dict keyに使えない点を3B接合時の注意として保持。3A-2・3B・issuer・HTTP・DBは引き続き未承認/未接続。

2026-10-28、PO委任によるClaude主担当判断（本人署名・人間逐行確認ではない）。D09=α（PO採用）の範囲内の実装選択として、writer bindingが(tenant, attempt, phase)ごとに生涯1回（PK・不変trigger・assertのINTO STRICT・`transaction_id=own_xid`）である一方、初球1要求がpreflight TXと局所適用TX（T9は3TX）を通る不整合（D09対応表反映1 `d09-abi-equivalence-20261028/reflection1/TABLE.md` G19・§6、E-1段階3反映3 open issue）について、**(i) F1（件数1）に限り1要求1 bound TXとする**案を採る。③の試合存在読取（binding前・別TX・読取のみ。B6非開示のため）の後、bind_writer→bind_device→RG1→D5分類→D3→⑤→⑥→⑦→（P1書込／T8／T9／再掲）→⑧→commitを同一top-level TXで行い、T8/T9/再掲への分岐は最初の書込（`recheck_and_insert_result`）より前に確定させ、savepointを使わない。書込後の例外は分岐させず全体rollback（B7）。DB・migration・SQLは変更しない（unit Aの印の同top-level TX条件と整合）。**成立条件**：T-20相当の実PG試験で、受理・B4・T9・再掲のいずれもbound TXが1つで、分岐が書込前に確定することを確認する。確認できなければ(i)は不成立とし、(ii)（TXごとのphase採番）へ切り替え、attempt単位の遮断記録（T-25）を必須の追加実装とする。(iii)（PKのlease単位化）は印の一回性を弱めDB・unit Aの再審査を要するため採らない。sync-protocol 6-2の記述（③→preflight→各イベントTX）との整合は、改訂時に設計書7.6の決定表で扱いを判断する。d1>1の一般化はMVP-D15回答後に再決定する。本判断はcore構造変更の着手承認ではなく、E-1段階3B計画へ反映し、計画の非作者reviewと採否を経て実装する。

2026-10-28、PO委任によるClaude主担当判断（本人署名・人間逐行確認ではない）。前段の1要求1 bound TX判断の訂正と補足。(1) **訂正**：前段の「最初の書込（`recheck_and_insert_result`）」は不正確。初球はP2経路で、`_apply_locked` が `prefix_path.py:670` の `order_resolver`（`_assign_d2`）を通じてT5のD2再採番（`ordering.py:90,95`）を先に書き得る。「最初の書込」は「`_apply_locked` 内で最初に `scope.run` する書込token（P2ではT5と `:714` の早い方）」と読み替え、分岐確定と書込開始の境界は `:668` の `order_resolver` 呼出の前とする（E-1段階3反映4の非作者review P1-1、D09対応表反映2のP2-2）。(2) **B5の順序**：sync-protocol 6-2の段階順（②認証=B5→③認可=B6→③-a RG1=B7、入れ替え不可、`docs/design/sync-protocol.md:712-722`）とD10=A（認証段階のB5）に従い、端末資格の照合をbindingの前の②に置く。②は端末資格の状態（失効を含む）を読取のみで照合し、不成立ならB5（D5/原本read 0、退避なし、端末の未送信は削除しない）。その後③→bind_writer→RG1→bind_device（DB側の再照合と印の発行）とし、②と③の間に失効した競合でbind_deviceが失敗した場合も、D5 readの前なのでB5として返す（退避なし）。cache上の仕分け（DECISIONS A-5「bind_writerの直後にbind_device」）は承認記録ではないため、本判断で上記に置き換える。(3) E1 entryはbind_writerの前に自ら `read_rg1_open` を呼び、その呼出点の `RG1Unavailable` だけをB7に写す（broker要求0）。bind_writer内部から出る `RG1Unavailable`／`WriterBindingUnavailable` は写像せず伝播させる（同review P2-1）。

2026-10-28、PO委任によるClaude主担当判断（本人署名・人間逐行確認ではない）。DB印unit B計画反映2 `first-ball-db-insert-stamp-plan-20261027/unit-b/reflection2/PLAN-CANDIDATE.md` SHA 975f3c363b34ef5fd0fce96ff600b7022b4daf4ce14a82ce7f1c351bc0f51c8c と非作者plan review（Fable 5.1、P0/P1=0・P2=4）を根拠に、**unit A反映2（source5-r2.patch SHA 7eb81362…c07d、実PG 21/21・非作者2観点adopt）とunit Bを1 step＝1 commitで結合する候補の作成**を承認する。範囲は同計画の結合step 23 path（新規7・変更16）。P2は実装で閉じる：(1) PortWriterはDML registryの`run`しか持たずPortからbind/rightへ届かない事実を「示せないこと」に明記し、U09/3Bの入口条件とする（静的試験は「bind/rightがrun_function相当の経路でだけ実行されrun_in_savepoint/begin_nestedに届かない」へ）。(2) PL/pgSQL block走査器は新ファイルにせず、core登録済みの既 `backend/tests/test_sync_right_sql.py` に同居させる（core-areas.jsonを動かさない）。(3) 後始末は開始前のvolume一覧との差分で自runの分だけを消す手順へ置換。(4) F14の静的試験(a)の対象を`prefix_path._apply_locked`に限定。保留だった2点：正本data-model 6-1-aへの新表追記は設計書7.6の「実装追随の節更新」として扱い、結合stepの直前のdocs commitに分ける（版繰上げはしない）。正式資産（runtime contract revision 24→25等）の変更に伴う7.7受理は、結合stepの最終byte確定後に単一受理記録として1回だけ行い、それまで受理済みとは書かない。共有DB・本番DBへの適用は本承認に含まない。本承認は候補作成までで、branchへのcommitは結合候補の非作者review・実PG確認の後に別途判断する。

2026-10-28、PO委任によるClaude主担当判断（本人署名・人間逐行確認ではない）。開始済み試合readのHTTP入口（U13、別route `GET /games/{id}/started`、DECISIONS A-1・A-2・A-3・A-11）の計画候補反映3 `started-read-http-20261027/reflection3/PLAN-CANDIDATE.md` SHA d1b85ebbda626aa78b094afe7d858854815aa78ca08e5049a72ae802a8ed9111 を採用し、同計画のステップ単位での実装着手を承認する。根拠は反映2の非作者review（Fable 5.1）adopt・P0/P1=0・P2=5と、反映3でのP2全件反映（判定保留の比較点を修復済み基線で取り直す、ステップ4を作者commitとroot commitの2段に分けroot commit後に完了を測る、#188へinitial_* 3件の置き場所を末尾と指定、A-2のREAD ONLY TX上のFOR UPDATE拒否プローブを必須化、行番号訂正）。initial_* 3件の期待集合への追加は#188側の修正とし、U13は`started_game_detail`の1件だけを足す。基線WBの機械ゲート2つ（tenant境界の受理record欠落、authz catalogのoracle seal未再封印）が契約エラーで止まる問題はU13の範囲外の基線修復単位とし、修復後に判定保留2項目が合格するまでPR化・統合へ進まない。#188合流版ではfrozen-inputsの移動（rev 6→7）と単一受理がrootの責任で1回必要。計画9節の確定点12（作者が共有DBを指すDSNのまま試験を1回実行）は、共有DBを読取のみで確認しpublic空・試験用role 0・余分なDB 0で残骸がないことを確かめて閉じた。


2026-10-28、PO委任によるCodex主担当判断。unit A+B結合候補 combined-after-docs.patch SHA 9d2e34dc65de53cf33e0f34229931a52e3630a2574c8ad19f357ad2b56dcebee、docs.patch SHA da528b42333d8cad9b81fc7ca6db70bbb386aba1b0bccc8f15d46968d165c5f9 を限定採用する。非作者ACL/RLS敵対review 3796d298fbcfa7d579f2af83e7931bf8c2910aaeb0c2f6db4d3a83139e2e4107 残0・独立owned PG27/27（共有DSN2変数unset）/pure489、計画review 44e5af8abe7a178b66c23b3d630989146e30e08b89fab7b1444a6dda5aa424fa P0/P1=0/P2=2を根拠とする。P2は旧T09(f)コメントを実観測へ修正し、下記未完条件を保持する。data-model節/README/canonical SHAは既7.6実装追随判断に基づく前置docs commit、A+Bは単一step commitとする。本人署名・人間逐行確認ではない。

既計画の観測訂正（意味仕様の新規採用ではない）：(1) T09(f)のrun_in_savepoint(bind token)はDML registry外としてPythonで拒否されSQL/SAVEPOINTを発行しない。同TXはtop-levelのままで後続run_function(bind)は成功し得る。ROLLBACK TO後未RELEASEの拒否は実D5一意衝突T18(a)で別検証。(2) gateを入口前に閉じるとassert_writer_bindingが42501を返しcheck_current_rightの55000へ届かない。assert通過後の競合による55000は未再現。(3) binding欠落時は既assertのINTO STRICT由来P0002。正常保存・確定拒否への自動写像はせず、呼出側の分類/D06を別途検証。(4) 期限切れrightは42501でstatement/TX失敗、device_verified残置の観測はsavepoint取消後に限る。全取消やTX中断中の保持の証明とはしない。

候補取り込み後もC5 root全件、C10製品DB/tenant/catalog、T18(c) record_d1_intents PK衝突、T15(c)旧body DB再構築運用、U09/3Bの実Port経路、S13〜15追加後の全件再検査は未完。非DB全件の基線100失敗比較を全件成功にしない。正式7.7値の単一受理、unit C正式profile/activation、最終HEADレビュー・必須CI、実API/画面保存は別義務として残す。

2026-10-28、unit A+B取込は前置docs b7baf20f / 結合 d189a40e。候補24path全SHAを照合後、計画review P2のT09(f)コメント1行だけ実観測へ修正しAST不変を確認、実WT集中489件成功3.12秒。ACL reviewは後始末留保追記により最終REPORT SHAが4845f37347eef41e261dd9931f4779cb5ed32d7a5fa29d367defa300509eb05fへ変わった（検査結果不変、以前の3796d298…は追記前）。開始前volume一覧を保存していないため匿名volumeの帰属推測削除は行わない。正式受理/activation/全件CI/実縦断未達を維持。

2026-10-28、PO委任によるCodex主担当判断。E-1段階3反映6 PLAN-CANDIDATE.md SHA e2d3d60d91a3c81a2f4ec95cec5c1fa18dac2051f91de46f0f000c15ab3a8dcf を、非作者re-review 676d97fd4bde5557d16df2e91d583580aabab8c0b8a8caa1bd8406609df25cfb P0/P1=0/P2=1に基づき3A-2・3Bの計画として限定採用する。P2は追補5431555f5b0c47143bd2da9521ba2c96209b084517d1fe06b530d0f7190cafdfのとおり、端末/試合(a)(b)を先に判定し双方一致時だけDB照会(c)を1回呼ぶ二段構造。同時不一致は既表11→12のB5優先。eager引数評価・自由callback・例外のfalse化を禁止する。旧反映5review全文はcache探索でも未取得で、その要約による反映記録と今回の実計画全文確認を区別する。反映5の旧P1（⑧mark_written条件）は同gated1回/受理T8/T9対向・変異を含む反映6で計画上解消。

3A-2/3Bのexactpaths/段階順・単球F1/1要求1bound top-level TX/書込境界は同反映6を正とし、②端末読取部品の未適用候補5pathを含む。Port4署名を変えず、任意frame迂回や偽issuerを作らない。source差分をcacheで実装し、独立source reviewと影響検査後にstep単位で採否を決める。unit A+B差分を保持し、正式資産・公開HTTP・実Port・正式activationは別単位。T-20等の実PG条件、D09同等性表の未担保行、P3/配信/多件・未提供Portは未達を維持し、成立した部品からの実装と製品接続の完成を混同しない。

2026-10-28、PO委任によるCodex主担当判断。製品DB基線修復計画 `db-baseline-schema-diagnostic-ef921539/PLAN-CANDIDATE.md` SHA f809e96b4cb73567feb49be1b775e86ce6a4f0ae5b9df59a69cc534302a50c33 を、非作者plan review60eef328e0e64e0b208d375bdff6cf5fa5caee6aaac0da9699e1f4dfa138e6e1 追加指摘0に基づき採用。exact5はdb/stage_a_startup.py、tests/db_fixtures.py、tests/db/initial_recording_right_scope_support.py、tests/db/test_stage_a_rule_candidates.py、新tests/db/test_stage_a_writer_storage.py（全てbackend配下）。0036止まりと0037/38依存の不整合を、owner同TXの明示writer storage配置と実構造照合、後段fullinstallerで修復する。未知future自動適用/owner移管/構造拒否の弱化/共有DB適用はしない。配置rollback・有限状態resume・非公開保持・最終catalog/appACLのownedPG対向と非作者source review後に採否判断。正式資産へ追加差分が必要なら別途rootへ返す。

2026-10-28、PO委任によるCodex主担当判断。E-1 3A-2 exact2 patch cee48a7e890cc1507b66ba34925297a92c2c26ae3f76ea84637caad4d8a171ab を、非作者review67a6968cca6621a4a8e9be510ee50ff4f7b797a2ffde30d223741af70bb2c710 追加指摘0・関連533成功/6変異検出/旧155prefix・他1296byte維持に基づき限定採用。実WT対象216成功0.62秒。pure W2 viewであり実台帳資格ではない。legacyのscope/kind/D2意味検証は既callerに残し、3B/実PG/issuer/HTTP/Portへの接続は未達。元test期待を緩めず、旧helper再利用で第2の計算を追加していない。

2026-10-28、PO委任によるCodex主担当判断。unit C最小追補 `first-ball-unit-c-minimal-addendum-20261028/PLAN-CANDIDATE.md` SHA94986aeb4f25e65c2b641f3ae3567be8db11c6493d5e1286ed4d1937a10235be を、非作者plan review a8c5ff31d48b21f9497304a5c38ca8c6478d7bf5a7252890351fcd61e202e007 追加指摘0に基づき限定採用。source4/test既5・新activation test/歴史SQL fixtureのexactpaths、新body91と既5は同計画とnew-body-assets.json/existing-body-assets.jsonの列挙集合を正とする。rootの正式asset書込は直列化し、作者はcacheで描画/生成/対向を供給する。旧SQLの歴史fixture隔離と新単一源、ACL和集合/2trigger閉検査/既guard保持を必須にする。runtime/frozen/参照値等の追加pathは実producer差分後にrootが判断し、勝手に範囲を増やさない。rendererのCREATE OR REPLACEと正式parserのCREATE FUNCTION形式の整合も検証し、既DBへの無条件置換はしない。基線修復をpure準備の着手条件へ追加せず並行するが、ownedPG正常/故障/再適用・非作者source review/必要な正式受理まではactivation完了・製品提供とはしない。

2026-10-28、PO委任によるCodex主担当判断。unit Cの新guard2triggerをproduct_catalog閉CatalogQueryIdで観測する実差分に伴い、既backend/tests/test_product_authz_catalog.py exact1をscopeへ追加する。既期待mapは全QueryId固定であり、新観測map/数/SQL対向を厳密追随するため必要。汎用query許可・既検査の除外はしない。source最終非作者reviewで追加差分も確認する。

2026-10-28、PO委任によるCodex主担当判断。unit Cの新lock invoker関数を正式登録するため、既asset_specのread_writer_identity(uuid) exact1制約へ、承認済guard_first_ball_projection_lock()のexact1を追加する必要がある実検査結果を確認。backend/src/pitchlog/authz/asset_spec.py と backend/tests/test_authz_asset_spec.py のexact2をscopeへ追加する。旧exact条件を保持し、新guardのowner/trigger戻り/空引数/security/EXECUTE無し/body等は正式単一宣言と全一致のみ許可。一般invoker許可・既guard拒否の弱化はしない。806成功/30失敗の中間状態を保存し、是正後の新入力検査と非作者最終差分確認を必須とする。

2026-10-28、PO委任によるCodex主担当判断。unit Cの既installerはdefiner→invokerで関数を適用するため、計画のlock先/admit後ではlock未定義でtrigger配置に失敗する実接合条件を確認。汎用順序は変えず、admit definer先→lock invoker後→lock canonical末尾で閉trigger2を配置/再適用検査する順へ限定訂正する。両関数定義後にだけtriggerを置き、既guard/triggerと新2triggerの全属性・順序を厳密検査する不変条件を維持。最終source独立reviewの対象とする。

2026-10-28、PO委任によるCodex主担当判断。unit C既producerのread-only導出でprotected_objects.functionsへguard2のみ追加、schemas/tables/role属性不変の実差分を確認したため、cache生成候補のcontracts/tenant_boundary/runtime-authz-contract.jsonとbackend/src/pitchlog/authz/runtime_contract.py exact2をscopeへ追加する。既正規generatorで導出し全before/afterを固定、正式repoへの反映/必要な7.7受理はrootの最終単位で行う。DERIVED_FIELDS_STALEを期待値緩和や検査除外で消さず、正式値受理前を完了としない。

2026-10-28、PO委任によるCodex主担当判断。DB基線修復reflection1 fullsource5.patch SHA7e1a27d5525cbb94870c53556377201bc7053feb8b8c85c09643af7aae406f8a をfad10d49へ限定採用。初回非作者8a8e22d4…P1=2（必須故障実証不足）をtest1pathのみで反映し、再レビュー0dcb51fc872568580238989826d527431f11fbf209a8e322610944d381fa98b7 残0/独立owned7成功/13catalog全値不変/漏れcommit変異検出を根拠とする。旧候補のowned19成功と新7を版別に保持。実WT5file SHA全一致・Ruff成功。正式owner/RLS/UNAPPLY拒否は維持。旧UNAPPLY/owner-only試験群の既不整合、tenant受理record/oracle整合、unitC正式activation・全件CI・実HTTP/画面は別未完であり、基線全件成功としない。

2026-10-28、PO委任によるCodex主担当判断。E-1条件fと実rightsの最小追補PORT-PHASE-ADDENDUM-CANDIDATE.md SHAcc40a2d25ce7b61bab22c91e4e429a2f1d738a6496db02bc1ae7c35c13111c04、transport/V12追補SHA01829734bddfee584efc4823788daf85e032f780e00684264ea969190c72a291を、非作者plan review079b10022ffc2f53c648a9015bee4f605118ceb9e5fc0deb6e9b93a60a5cc240 P0/P1/P2=0に基づき技術方針として採用。今回のsource着手追加はtransaction.py/gate.py/sync/tokens.py（backend/src/pitchlog配下）と新backend/tests/test_sync_port_predecision_phase.py、backend/tests/db/test_sync_port_predecision_phase.pyのexact5、既3Bcallsiteに限定。Port4ABI/同handle/実writer資格を保持、私有phaseが⑤/⑦業務DMLとsavepointをSQL前拒否し、核1回bindと正規right stampだけをactual lease/nonce/contextへ有限束縛する。未知Select/汎用function/偽tokenを許可せず、必要read exact集合/phase-kind表は実装packetへ固定する。実Port/HTTP資格・UR1codec・browsertransportの追加pathは各所有WTで実在pathと受入を固定した別単位として後続判断し、この追補だけで公開・実資格供給を成立扱いにしない。境界finishは既scope hookの1回を再利用し二重closeしない。UNKNOWNを確定拒否や成功に写像しない。

2026-10-28、PO委任によるCodex主担当判断。U06 PlayRow登録plan SHA781e06da748b121a0cb0db75e4a396b4592ed59a78dc48a104da2b8d03d9f5b2を、非作者e49578f83a2ef98275ed1ba852c8b7cd10c4855083da3e8bfb185c7e1fbee19e P0/P1/P2=0に基づき限定採用。exactpaths.json（d68ea7a9…）の既source6/新ownedtest1、root専有repository_contract.py/JSON2のみ。既token2/CAP利用、SQL/41列/preflight/新GRANT/数学/Port ABI変更0。作者はunit C固定候補を明記した隔離依存としてsourceと契約生成候補を供給、root正式資産書込は直列化する。token51→53/CAP32→33等は実直前版から導出し、旧prefix/未登録派生型の拒否と正式installer/真正bind/right/同TXの成功・故障対向を保持。実frame→物理値はU08/U10の未提供依存、ball exact3以外への一般化不可。正式7.7/実Port/HTTP/画面/初球完成を先行成立としない。

2026-10-28、PO委任によるCodex主担当判断。U06登録時に既先行SQLのINSERT RETURNING全41列が正式capability validatorで拒否され、既executorの非SELECT結果がrowcountのみである不整合を実確認。既ガードを緩めず、同exact9内でRETURNINGを除去しINSERT結果((1,),)を厳密確認→同TXの既LIMIT2 readで全41列を回収する最小是正を採用。全列入力/bind/tenant/preflight/DB印を保持し、rowcount不一致・read欠損/複数は非成功、別TX読取にしない。「既SQL不変」の先行指定はこのRETURNING除去だけ読み替え、pure期待は実executor契約へ整合。新権限・新計算・拒否弱化はなく最終非作者source reviewで確認する。

2026-10-28、PO委任によるCodex主担当判断。writer-binding 8aaac330で採用済みU08/U10 B1計画 SHA 25f60f88ba2f90de07ecebe96ead6970af5b98a43f2e0ec612ca4ee38fe3b268 を本枝にも適用する。exact4で原eventと採番後eventの照合、同writer/source/phase/nonce束縛と真正frame一回消費を実装し、B2未供給時のrollbackを維持。非作者plan review 202c0159dc851d4bab73698cf605b8de550dd2a34d04b14322a6bf754df97806 指摘0。source初回のD2範囲P1を反映し、再レビュー d402e290fa76cd65903d74eca011af29a8497fdb6cc8fc49f41bf92c3328dbe3 指摘0を根拠にcombined.patch SHA 300f75cd4006df4a3a55607280289c1873734f8f6d1f952a82ba579a9524b4e1を採用する。物理値変換・語彙read・実DB保存・HTTPは別途必要。本人署名・人間逐行確認ではない。

2026-10-28、PO委任によるCodex主担当判断。既採用D09 G20の実装追補計画 SHA 999e47896696642011be57fb35d30bce7b3f52ecff6c168f8e9e61d7173aec61 を非作者plan review SHA bc93aa8e8f8fe1c42f847c94204b53d1c0feb9322ea53d8db0f62a12b99ba4f7 指摘0に基づき採用する。binding_control.py、durable_rights_ledger/adapter.pyと既pure/owned test各1のexact4。既採用の5種類を2つのexecute/fetchだけで識別し、commit失敗・UNKNOWN等の隔離を維持。journalのrejected後の安全なcloseと再起動を実PG/故障対向で検証し、source非作者review後に採用する。新たな意味裁定・本人署名・実DB成立とは扱わない。

2026-10-28、PO委任によるCodex主担当判断。G20 source変更で既testがmanifest.jsonのauthority.adapter_sha256との不一致を検出し、owned fixtureも同一致を要求すると実確認したため、backend/src/pitchlog/durable_rights_ledger/manifest.json exact1を既scopeへ追加する。adapter実byteから該当SHAのみ再導出し、他属性・旧拒否・検査を保持。最終source確定後に値を再確認し、非作者reviewへ含める。313成功/1失敗を全成功とはしない。

2026-10-28、PO委任によるCodex主担当判断。E1②端末状態readの登録計画反映1 SHA 154a257b423e57d4cd51e4981acf284b37c6ecfb2342d3d9272f462595b19a9e を非作者再review SHA c312227187a8c978017263bf7f5209038c182093974f1bfdfb016e9c13d48abf 指摘0を根拠に採用。初回P1の「同型手作り拒否」を既exact正規token/正規UUIDの受理と、同名別型・同CAP未知・派生・異型UUID拒否へ訂正。既関数SQL/入力/decoder・②→③/B5順を保持し、registry/source/test5とroot正式資産2のexact7で登録する。正式値は直列反映直前版から再導出し、DB function activation・実PG・issuerは別途必要。本人署名・実機能完成ではない。

2026-10-28、PO委任によるCodex主担当判断。G20 step1 source4 SHA d8c06b9c7d22226c7b3de6918408199cf0579dca8724cb4d340299ae2fd65426 を非作者review SHA 7b2cb7379391f39bdcd0f9f7e759b48e69f7a2e3e5132659944d6c8eb5564c32 指摘0・独立新44＋追加4対向を根拠に採用。作者関連315成功・変異6検出、manifest実hash一致。2SQLのexecute/fetchだけの限定分類とUNKNOWN隔離・journal失敗時停止を維持。step2の実PG診断/途中故障/再起動は未実施であり、実DB完成・本人確認とは扱わない。
