---
feature: tsk544-t1-state-calculation
status: active
承認: 済(2026-10-20・山田正輝)
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3f893b75e68781e5a55ce961b18fab3f
branch: feature/mvp-t1-first-pitch
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
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **7.3承認済み候補からapprovedへ確定** | v2.16のJ5のXC-13時点分界とJ6の付録A-1/E-1入力を2026-10-21のPO承認に基づき確定。契約の7.7は別ゲート |
| `docs/adr/ADR-003-domain-calc-method.md` | **7.3承認済み候補からapprovedへ確定** | v0.9のD-11のT1限定検証時点を同じ7.3ゲートで確定。D-2全体は維持 |
| `docs/README.md` | **approved状態・版・日付へ追随** | v2.16/v0.9の確定を索引へ反映し、既存履歴を保持 |
| `docs/development/dev-harness-design-2026-08-07.md` | **反映なし** | 機構変更は予定しない |
| `contracts/state-transition/`、凍結履歴・署名 | **反映なし** | 正本確定後、T1行/case/schema/descriptor/負例・T2参照・派生資産の候補を作り、コアレビュー、所有側受理、7.7実値の人間確認後に正式反映 |
| `.claude/core-areas.json`、検査器 | **反映なし** | 検査緩和・例外追加はしない。必要な変更は別計画・ゲート |
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
