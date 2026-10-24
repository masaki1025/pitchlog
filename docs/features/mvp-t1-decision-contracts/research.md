# 採用済み判断の正式反映根拠

- PO採用原記録: feature/mvp-integration-lead e4ef090a、既decision-sheet。D01〜05は未回答のまま。
- receipt: /home/ymdms/.cache/pitchlog/mvp-decisions-d06-d07-20261024/po-adoption.json。これは署名/本人実値確認ではない。
- D07作者候補: /home/ymdms/.cache/pitchlog/t1-formal-out3-first-candidate-v2-20261024-d07a/handoff-v2.json、45成功、純入力SHA1b11153d627526f1b23bad5c73ab75436fc042d67a2c95cad6933afe58c1dc11。通常独立レビュー依頼済み、正式反映/7.7/P6未成立。
- D06作者候補: /home/ymdms/.cache/pitchlog/d06-priority-contract-adoption-20261024/。固定handoff待ち。故障想定/実DB0を区別する。
- 本unitは既承認544ステップ1の部分処理で、既T1候補ddc9ce8647d2bb5c4ee38f0f4e901aa50b875f5dや旧候補/封印を移植せず参照する。正式契約起点は4b2db690。


## D07限定正本の確定

2026-10-24T05:13:53.014357+00:00、rootは既PO委任に基づき、D07=A採用内容の最小要件追補候補（元a7edf93a56dc6b6f364890a4cd49cd6a360fcb4e45dafe64f561163f789a538f→審査版6f29239c3f0b50f60657edcc1f30553fb7538e5b6516a04c2a40d6060f7a3421、patch6aa8c85b815ff4d20f00d3bca2ce1a367fc150fa737e3e62dc4fc3c8186ea5b8）を確定した。作者initial_scope_plan_review、非作者rights_replacement_reviewの限定7.3第1回0/0/0・反映0周（証拠 /home/ymdms/.cache/pitchlog/reviews/d07a-requirements-gate-round1-independent-20261024/evidence.json、SHA256 0dc37f8f8a093004756592410d9df561b65532e5681ce027a219bb2c749659bc）を根拠とする。POの本スレッド実採用とrootの本文対象版確認を区別し、人間の実値逐行確認・署名は記録しない。D07適用は二死二三塁単打の一配置だけ。版2.17/approved/履歴/索引は確定に伴うmetadataで、正式developは未変更。

通常非作者候補レビューは /home/ymdms/.cache/pitchlog/reviews/d07a-formal-candidate-v2-independent-20261024/evidence.json（SHA256 f7465837c3bbe8b1991f682a940c735fbaca997cbb853b6905a1122c85bd80ab）、45+6局所構造検査と旧42row/109case/27fixture保持を確認。これはblindではない。schema単独の時機欠落/走者ID相反受理は既知未達で、正式接合前の必要観測・相関負例を残す。正式contracts/7.7/missing15/P6/P7/全T1着手条件はこの確定だけで変化しない。


## D06限定同期正本の確定と技術候補の差戻し

2026-10-24T05:21:52.982796+00:00、rootはPO委任により、同期正本5節の限定差分（審査版6f4c4b245c234ca7ee38b60355aacd33e618388509a4be35a2384c33c3225ca9、patch0e5b60890b301acc3606046f181ff1ff8368180aac59c4de94ea5afce493be51）を確定する。非作者rightsの限定7.3第1回0/0/0・反映0周、証拠 /home/ymdms/.cache/pitchlog/reviews/d06b-contract-independent-20261024/norm-round1.json（SHA256 ce379c586cde2c7b39f98849833e3b068a2841d667186a8d7aa8ca92e1f52c27）と本スレッドPOのB採用・全留保を根拠とする。同系譜・同半回のmによる重複TBだけで、P3や一般同値不成立を新規採用しない。版0.12/履歴/索引は確定metadataであり、正式develop未統合。

別の技術通常初回はD06-CODE-01 P1を採用（code-round1.json SHA086a596ecea3391050c9b5075a5e0bc9e0456d0a44c21475ba5fe338615c9d51）。PrefixEvidenceRefV1未定義はskipLibCheckなしでTS2304、skip時にprefix17/nullを誤受理。原cacheを不変保存し、root反映候補 /home/ymdms/.cache/pitchlog/d06-priority-contract-reflection1-20261024/ へ既upstream exact4field readonly型だけ追加。skipなし宣言/利用側6負例・no-anyは成功、限定非作者再検査待ち。66作者/独立比較は実Ready・DB・取消・耐久遮断の証明ではない。専用原本/実DDL・ACL/真正権威照会・正式4b2未収録P7参照schemaの供給・7.7/全P6/P7は残る。


D06正本commit前の計画整合検査で、§2には存在する要件/索引のパスをcheckerが§3から導出できず2件拒否した。直前のコマンドは最後のgit終了値だけを返したためcommitは成立したが、この検査を成功とは扱わない。編集範囲は増やさず§3へ同じ対象pathを明示して機械突合を是正する。以後依存コマンドは失敗時に停止する。


2026-10-24T05:27:13.381972+00:00、要件D07の確定byte変更により既共有認可前提の要件source git-blob束縛だけを追随。FR-034/認可前提値は不変で、既POの通常生成値追随委任によるroot処理。ADR実basenameを既存ADR-003-domain-calc-method.mdへ訂正し、存在しない案のパスを編集対象として残さない。


## ステップ2の固定候補・限定独立導出

2026-10-24T05:35:47.076325+00:00、rootはD07作者候補v2の純入力を新しいfork-none検証者へ、承認済み要件d0070222と対象範囲だけ添えて先渡しした。作者値/会話履歴/周辺cacheは渡さず、封印完了後にrootが候補比較した。封印 /home/ymdms/.cache/pitchlog/p6-d07-limited-derivation-20261024/seal.json SHA256f9aa6a10b0d8f70aee7d39fa1520f97c1fbac629a93b968183f33db96749dac9、derivation af8dffe2fc306912b22ed7b775e067e1611ccb66ee02991082789575157cceac。新2入力の六比較面/各23flag/得点・打点は全一致。比較は候補側rootが行ったもので、正式契約版段階B/全P6受理ではない。検証者には作者比較資料をまだ渡しておらず原導出/曝露履歴を不変保存する。

D06技術候補の初回P1に対するroot反映は非作者第2回相当で終結（型f41a48c44c373606ba1fbc661df783404755d24a1af1293223af40b9d7f48e28）。skipなし宣言/正常/no-any/否定6件が成功。正本7.3初回0・技術初回P1/反映1/第2回0を別系列で保持する。

- /home/ymdms/.cache/pitchlog/p6-d07-limited-candidate-comparison-20261024.json SHA256 1bcae8bbc08863e14de6c080cd3ea0221c9101e8a53794afef420e1834d67b90
- /home/ymdms/.cache/pitchlog/reviews/d06b-contract-independent-20261024/code-round2-reflection.json SHA256 12bc814b479c3b51836283467f8c822c690587a2130f8558eb9d3b2d06a8ccc4

正式6asset/新D06共有型・caseはまだ未反映。P7 upstream schemaの正式共有化/専用保存原本・認可・結果wireとreader、必要観測・ID相関の拒否、共通descriptor/T2参照/派生値/7.7、正式段階B/必要再検証・所有側範囲受理を残す。新2ケースはP8不足15をまだ削減せず、7marker閉鎖0・計算本体未着手を保持する。実Port/HTTP/DBの完成を計算本体の着手前へ追加せず、元544の対象別条件のうち実装後ゲートとして扱う。
