# TSK-544 T1正式契約への射影候補（J5/J6）

状態: **7.7未受理・正式契約未編集の候補**。正本は要件書v2.16とADR-003 v0.9（2026-10-21の単一7.3ゲート、確定コミット`52625ed6a6d7d27a212acfee16b97c8a97d987a5`）。契約比較元は#153統合後の`origin/develop`=`cad0f1eb6a66103321d99a369c5cbb17b57087cd`であり、T1枝への取込HEADは`73f5a8e8faacea88edfacde9139ae38ddd84e5b8`。本書は期待値の独立導出、契約所有側の受理、7.7実値の人間確認を代行しない。

## 入力と検証器の最小差分

| 変更先 | 射影する確定規則 | 未確定・停止点 |
| --- | --- | --- |
| `input_axes_descriptor_v1.json`とschema | `event.perPitch.homeTouchOrder`を別軸にし、`not-required`と順序付き`observed`をexactに区別する。同一候補集合の順序反転も別coverage値。23フラグの必要十分条件、OUT3・RBIの閉入力と相反・越境を既存8制約のT1部分へ写す | #153後の共通digest、T2参照差分、軸の値域と無限の選手IDをcoverage代表値へ射影する方法は所有側レビュー。集合だけに正規化しない |
| `state_transition_contract_v1.json`とschema | `matrixRows`/`operationRows`/`undoRows`の既存109 caseを保持し、T1の閉入力・J6の順序必須条件・OUT3→非HR上限→得点者別RBI→COLDの評価順を規範行とcaseに追加する | 完全な10列期待値、履歴差分、各行のIDと出力値はP-6独立導出・所有側受理前に固定しない。J6の入力は出力11列目にしない |
| 手動fixture・branch coverage・handoff | 追加行/caseと原典の対応、正常と拒否の双方向負例、両runnerの消費対象を追随する | 受理履歴・凍結digest・署名は7.7値確認後。既存受理行と#153のT2成果を上書きしない |

`HomeTouchOrderV1 = {kind:"not-required"} | {kind:"observed", scorers: ScorerRef[1..4]}`、`ScorerRef = {kind:"runner", runner_id: PlayerRef} | {kind:"batter", batter_id: PlayerRef}`。`PlayerRef`は正式選手IDと一時UUIDをタグで区別する。OUT3後の有効得点候補集合を順序とは独立に作り、`observed.scorers`のexact-setと照合する。順序が必須なのは、規定最終回以降の後攻勝越し局面で、**非HRかつ有効候補数が決勝点成立までの必要人数を超える場合だけ**。不要時は`not-required`または整合した`observed`を許し、観測有無で計上値を変えない。既存caseは不要variantを明示して移し、暗黙の既定値にしない。原wire・codec版・順序列の保存先と限定resolverはU-S1の公開型/認可/拒否順が決まるまで正式化しない。

## J6正常・拒否・境界caseの候補

| 候補ID | 入力分岐・原典 | 必須の比較面または拒否 | 正式化前に必要なもの |
| --- | --- | --- | --- |
| `T1-S20-ORDER-A/B` | 同じ規則snapshot・同じ有効候補A/B、非HR、観測順だけA→B/B→A（A-1、E-1） | チームの勝越し点数が同じでも個人得点・RBIの帰属とcoverage値を別にする | 正式入力座標、全10列、P-6独立期待値 |
| `T1-S20-HR` | 打者を含む3人の有効HR、規定最終回以降の後攻（A-1、RBI-06） | 非HR上限を適用せず3人を計上し、打者本人を含むRBI判定へ渡す | 正式caseとP-6比較 |
| `T1-S20-EARLY` | 規定最終回より前の後攻勝越し（FR-005、A-1） | 非HR上限を発火させず有効者全員。順序不要 | 正式caseと規則snapshot型 |
| `T1-S20-OUT3` | 接触済みだが踏み忘れアピール等でOUT3後に無効（OUT3-01〜05） | 無効者は順序列に要求せず、得点/RBI/上限へ入れない | アウト種別・対象の閉観測型 |
| `T1-S20-MISSING/EXTRA/DUP/CROSS` | 必要時に順序欠落・候補不足/余剰・重複・他scope参照（E-1） | それぞれ独立して拒否。時刻/位置/最終得点で補完しない | 拒否型と優先順のU-S1受理 |
| `T1-S20-REPLAY` | 同一D5で順序またはcodec版を変更（E-1、同期DI2） | 原wireの同一性不一致として既存再送境界で拒否。取消は保存済み差分を逆適用 | U-S1の原本保存型と実接合試験 |

負例は外形S-1と意味拒否を混同しない。参照の未解決・別試合・別テナント、無効者を含む順序、候補集合不一致、必須時の`not-required`、未知codec版を別caseにする。これらのD5消費/拒否原本/混在バッチの前方確定はU-S1の既存契約へ接続し、T1独自のACKやHTTP分割を設けない。

## P-6追加7件の正式case化の境界

旧blind v2（SHA-256 `e12ae8b589aa48971a9b7ba4a408cc4b90aaa6ae9c27df9ca328493a18df04e4`）と旧比較候補は保全する。7件の正式`caseId`は現行109件には存在せず、すべて未割当。`001/002/003/004/006`はOUT3/HRの型付き入力と全出力を新caseへ固定してから、契約commit・blob/ファイルhash・blind ID↔case ID・比較射影を別版でP-6へ渡す。`005/007`は得点面とRBI面を分け、打球種別、失策または野手選択の有無、併殺送球失策の有無、走者の継続・停止後再発進、失策がなければ得点したかという記録員観測を必要なRBI-01〜09分岐に対応付ける。原典と独立した観測が無い欄は不足のままとし、期待値から逆算しない。旧版への曝露は解消済みとしない。

## 直列統合・停止点

TSK-564の#153は2026-10-21に`cad0f1eb6a66103321d99a369c5cbb17b57087cd`で統合された。`game_end_contract_v1.json`・同schema・`appendix_e_consumer_handoff_v1.json`を編集し、共通descriptorとT1契約/schemaのblobは変更していない。**直列順の前段だけ成立**し、T1正式編集・T2追随・7.7は未成立。T1変更後はT2の`inputAxesDescriptor.digest`、schema const、両loaderの定数、handoff artifactsへ機械的に波及しうる。T2の意味・本人署名を代行せず、参照hashの計算法（RFC8785とファイルbytes）を区別する。

P-6段階Aの固定結果/未検証範囲、G6-S01〜S08の担当別受理、P-7の公開入力同値性・認可済み読取口・J6原入力保存型が未成立。正式契約の編集はこれらのうち計画が要求する先行条件と編集所有を満たした後、コアレビュー・所有側受理・7.7完全前後値の人間確認の順で行う。製品計算コードと正式7.7は本候補では開始しない。

## P-7の実コード境界と残る受理

U-S1担当枝の`prefix_path.py`では、⑦の`validator.validate(event, writer)`は原イベントを受け、T5/O4の後に`_projection_event()`がC2の選手参照写像とP2のD2採番を入れたイベントを作り、T4の`projection.apply(projected_event, writer)`へ渡す。この二つはPython値として同一ではない。T1が参照する論理入力について、①一時/正式IDを同scopeの同じ選手へ結ぶこと、②D2確定前後でT1の結果に関与する順序値が同値であること、③⑦のT1評価は後段C2の未解決拒否を前倒しせず、O4とC2の既存順を保持することをU-X1の入力型とU-S1の接続契約で証明する必要がある。成り立たなければT5後への評価移動とO4対内容拒否の優先順差分をPOへ示す。コードを読んだだけで同値性を受理済みとしない。

同scopeの既存の部品には、`GameReadToken`（`games.applied_rules`を含む単一試合行）、`PlayerReadToken`（最大200件・選手ID等の絞込）、`OperationEventOrderReadToken`（D2順の有限範囲）がある。しかし、これだけでは**適用済みT1履歴prefixの定義、投影前状態の確定版、名簿の時点、規則snapshotの閉型**を公開したことにならない。D3/confirmed_watermarkを履歴prefixへ流用しない。認可済みの登録token・戻り型・同scope寿命はデータ所有側とU-S1から項目別に受ける。原wire/codec版/homeTouchOrderの保存表・型版・限定resolver・codec許容集合は未提供で、既存`OperationEvent.payload/state_diff`を原本保存へ読み替えない。公開契約の受理と実Port SHA/HTTP・DB結合試験を別に扱う。

**U-S1差分回答（担当枝`2ed6ced8`）**: 同担当は、⑦でC2成功を必須にすると現状O4より後のC2失敗が前倒しとなり、prepareをT5後へ移すと現状⑦の内容拒否がO4より後になる、と具体的な競合条件を示した。したがって「同値性は未証明」のまま。T1側の閉型/normalizerは、タグ付きPlayerRefとC2後の正式IDを同scopeで同一人物へ結ぶこと、assigned D2が論理位置を変えないこと、規則・名簿・投影前状態・履歴prefixが一イベント内で固定されること、preparedを同一event/contextだけで使うことを示す必要がある。この証明が不成立なら、拒否優先順の新判断をPOへ出す。U-S1は原本保存要求の集約窓口を受理したが、物理保存・認可・型版の実装担当は未指定。data-model所有の窓口はU-R1、wire/codecの窓口は506・U-S1、閉意味型はTSK-544であり、U-R1のdata-model所有を新adapter実装受諾と扱わない。

## P-8残件の分類（同一論点は一行へ集約）

| 分類 | 対象と現在の到達点 | 次の完成物・担当 |
| --- | --- | --- |
| 候補完成・正式反映待ち | J5の着手前/実装後分界とJ6の`HomeTouchOrderV1`、OUT3後の有効候補だけの順序、RBIへの後段受渡しは正本v2.16/ADR v0.9で確定。S20のHR/非HR/早期回/OUT3/反転・欠落・重複・越境の候補caseは本書へ固定 | TSK-544が正式規範行・schema・負例へ射影し、契約所有側/コアレビュー・7.7へ。P-6の期待値は別検証者 |
| 候補未完成 | S05の操作payloadのID/条件依存閉包、S07/S32の走者イベントと進塁上書きの相反排除、S09/GAP-06の第3アウト型付き観測、S08/GAP-02の23フラグ各キーの入力必要十分条件と双方向負例、RBI-01〜09の条件付き観測field | TSK-544が既存[入力・case候補](../ux1-state-calc/tsk544-p8-candidates/t1-input-and-cases.md)と[23フラグ/RBI/G6表](../ux1-state-calc/tsk544-p8-candidates/t1-flag-rbi-g6-matrix.md)の`pending`を原典照合し、閉じない箇所を具体的に裁定へ出す。判定不能を`false`にしない |
| 担当回答待ち | G6-S01/03/06の選手・打順と保存規則snapshotの公開型、S02/07/08の回不一致・Given拒否の結果ID/D5境界、P-7の⑦/T4入力同値性・読取口・J6原本保存 | U-G1/データ所有側、U-S1、必要時506が各公開契約を回答。TSK-544は候補の入力軸と拒否caseを保持し、実Port完成を着手前条件に足さない |
| 新しい仕様判断待ち | G6-S04/05の再開始および半回・アウト・カウントの適格条件、S09〜S11のD+1以外の履歴長、S11/S13/S22の原典不足 | PO/TSK-546へ具体分岐を提示。既決のD+1内だけを候補へ含め、他履歴長へ一般化しない |
| 独立検証待ち | 正式109件のP-6段階A固定範囲と未検証範囲、追加7件の全10列正式case（005/007の打点入力不足を含む） | P-6担当がblind入力から導出・封印し、TSK-544は後からID対応/比較射影を渡す。著者の自己計算は独立検証に算入しない |

#153統合後の実値は次表のとおり。Git blobとファイルbytesのSHA-256、descriptor自身のRFC8785 digestを混同しない。**右列は#153統合による実差分であり、未完成のT1正式候補のafter値ではない。**

| 資産 | #153直前`cad0f1eb^1` | 統合後`cad0f1eb` |
| --- | --- | --- |
| 要件書source blob（develop） | `ee6d2508dbdecf34d90c34fc022ff162f73dd3d2` | 同左。T1枝の承認済みv2.16 blobは別に`297f8cf2653c65c846ea3feff7b7a9c563afbe3e`、SHA-256 `569b761b55f83923d8a6352705bbac3527103d4194a2819a06ac06296ee7060a`。**develop未統合** |
| 共通descriptor blob/ファイルSHA-256/自己digest | `d971360817271f91ddc73c2e674e0c760ead7baf` / `fab52a2e17ba868ec7f818468241901a2cb12ad98e9cf19c20b52235d184ed56` / `sha256:5107f929d35ae48e01e25e0410a95235521b778ce53bae945ca5d7e2e956dd57` | 全値同左 |
| T1契約blob/ファイルSHA-256 | `b178ff9cbed997866989eb7dc93476683f762e4a` / `54448fcb5b6e598e3610bc77d60a0a3ce1895f8afee8c5361a040f4aff4244bb` | 全値同左 |
| T2契約blob/ファイルSHA-256 | `bac1dae002cb51ae7cc215f51dbd86897dd9823b` / `87052798e37dbc78e687c6be65e9d194aadbaffa77d38df8151f72fa8c6808a2` | `c73a01e72fca5eb8a7e4765d2abdc335eb8a9c68` / `4a777153143788c111bbdec0097268f5aae45af050388509fd02350da9d0ace4` |
| T2 schema blob/ファイルSHA-256 | `0054ba48bbe6b41a4483bbed2ab146550cfa147a` / `253849d4eea5d7bee65f5a7d715124ee3e8ab54a0890ec4b5d98b5790e366840` | `a4aea4c4ff2e2ea164fe4f1d17a0a5e705823fb7` / `2fa7fb0dc0e0f9f389054ec4825fcb3f341e64aa7a36d932bf31a0ff53813c26` |
| handoff blob/ファイルSHA-256 | `41515de45491c8f3533e9ca0cd19e952cdd766e5` / `d2b5aa439eef4af51d5ae0601e6f8e1d9d79e84d772706b2c0c11d2da0e6f510` | `e735556fed769514a52b99158cd0ec6df83aa986` / `9f0ed33c6bf029ed50b604be7b4b5757f598cc2ccb9964833d98a24ff5e79a7e` |

現T2契約/schema、T1契約/schema、両loaderは同じdescriptor自己digest `sha256:5107f929d35ae48e01e25e0410a95235521b778ce53bae945ca5d7e2e956dd57`を参照し、handoffはT1契約・T2契約・descriptorの各**ファイルbytes** digestを参照する。T1の新`homeTouchOrder`軸・閉入力・case・負例、23フラグ表、G6-S01〜S08の担当別受理が未完了のため、**T1正式候補のafter digestはまだ存在しない**。値を仮置きして7.7受理へ出さず、確定差分から再計算する。既存#153の受理履歴・T2意味・署名は変更しない。
