# 無走者BB/HBPの再利用調査（2026-10-30）

本候補の作者記録。基点 `e81c4edb5d2f55d67579e7e47aa9bbb24b6de055`。編集は子plan/research＋親TSK544末尾参照の3pathだけ。製品/contract/正式資産/ref/commit/push/台帳/PG変更0。別主画面WTへ触れていない。

## 既準備とspikeの実byte

`~/.cache/pitchlog/walk-fourth-pitch-readiness-20261030/REPORT.md` のSHAは指定 `e4f8f004becc374036fec7556570813e1528a0395d68c9e7c617c248909728db` と一致。旧準備は無死/初回表/打順1のwalk witnessであり、その初期状態限定を新操作全体の範囲には採用しない。

| source | パス | SHA-256 |
| --- | --- | --- |
| 41d7175dcc28730c61f28ff0d9de8c27664e4628 | frontend/src/domain/state.ts | a83626eddee4546f33b3def5d8b66a0c7475410b770c62db7f7bf1892598e284 |
| 同上 | frontend/src/domain/stateRules.ts | d38e6d62bf03fcd868d3c8b835fe7911fa272ba6ba6f0a1ce40cd8dc317fa2bf |
| 同上 | frontend/src/domain/forward.ts | d87198981ecc60fc06f82b378bd43293127fd53cfadd44b364312cf4d746155d |
| 同上 | frontend/src/domain/publicApi.ts | a3bb04d55384f16ab11e44fcbafae2e8c79c9a332f73b7a70065f7279b37a33c |

Git実objectから再計測。8e1bf431は完全SHA `8e1bf4310f3db2a4e9f3302b2e3bc2833287feae`、state.ts/stateRules.tsは上記と同byte。forward.tsは8e1bf431には存在しないので、roundtrip41d7175d由来としてだけ扱う。publicApi全輸入はせず、現在の閉型・extra/非canonical拒否を保持する。

旧probeはartifact `df16864ceef00dbd30b29548f317a013d151e7d14a524c1ede153362af5b5c3d` の実Node実行。今回再実行・未曝露独立導出ではない。既BB golden `ST-MATRIX-5b16ca2951847cc5` / `ST-COVERAGE-46b323eb34acae8d` は5面/23flags一致、after.runnersだけspike=`loaded`／正準=`first-second-third`の不一致を記録している。現TSのRunners/publicApi/historyScalarもloadedを使う。期待をloadedへ変更して全一致にしない。今回は空塁→firstなのでその差は成功出力へ現れないが、旧差を別不一致として保全し、他塁操作を採用する前に正準wire↔内部enumの明示変換/契約全値確認を行う。旧ABIのloadedを無断変更することも本単位に含めない。

## 既規範と供給不足

- 要件E-1 XC-06のPA/reset/打者行先、全23flags、ADV-01〜04、A-3打数除外、FR020のB=四球のみ、A-2責任投手が根拠。現state_transition_contract_v1のmatrixRowsにBB/HBPの既規範行が実在する。無走者15count全応答/状態独立性と新ABIの不足を追加する。既一三塁のcaseを無走者へ書き換えない。
- BB/HBPともspike stateRulesはpa=true/reach1/out0/force/reset-reset。state.tsの打順n%9+1、BB/HBP flags、BBだけwalks+1を選別再利用できる。無走者なので既走者のforce計算を新実装しなくてよい。T1の新一塁占有は打者の出塁で、runnerDefaultAdvanceの不在3枠はnot-applicableのまま。
- 現state.tsはderive/deriveOrdinaryを単一applyCountRuleへ接ぐ。新計算を別terminal核へコピーせず同helperのcount/PA/行先/flags/afterをfactorする。既publicApiのhistory差分生成を使い、spike forward全体を第二の履歴核として足さない。
- ordinaryStateSupportedはinning>=1、0..2out、打順1..9、全塁/非負scoreを扱う。数学のBB/HBPもその局所型を共有し、runners=emptyと各countだけを追加条件にする。前回open/規則/TBの真正整合はT2/保存接続側。

## v1を黙って広げられない実理由

`ordinaryPitchContinuation.ts` のprefix()はversion1・ordinary-only長、finishはcount以外不変/PA=falseを検査する。`domainrt/ordinary_pitch_continuation.py::PrefixRef`、`repositories/ordinary_prefix.py::CheckpointDocument` もversion1/T2型を閉じる。terminalを通すためにこれらのassertを削ると旧ABIの意味が変わる。

新v2はplay長とD1/D2/水位を区別し、旧開始/ordinary-only sourceから実bridge証拠を保存する。v2数学入力の形は真正性証明ではない。実接続は同TXでcurrent checkpoint/原本/ledger/規則/配置を照合する。T2は `firstPitchContinuation.ts::evaluateEndConditionNoEnd` を共有し、PA終了だけを理由に固定no-endを出さない。既ordinary37後続もv2で扱い、一塁runnerと責任投手を保持する必要がある。

`sync/ordinary_pitch_projection.py` はframe→既source照合→41列PlayRow/history/checkpointを同TXで扱うがPlayRunnerを投影していない。現write stampはpayloadの全fieldを厳密固定しており、新runner能力をそこへ暗黙追加できない。v2専用prepare/consumeとexpected runner全値を固定して同じ実TXへ接ぐ。既table PlayRunnerのtenant/player/投手/親play FK、base1..3、status_source=auto/manual、active tenant/play/base一意、親論理削除を再利用する。新規runnerの責任投手を現在投手固定で決めると、BBの打席途中交代帰属を誤るため、最初の実PAでは交代なしの真正証拠を要求する。

## rootへ返す最小判断

子planの操作範囲・15手規範例＋810交差の検査・T1開始ゲートと後続依存の分離を別非作者が確認し、rootが対象SHA採否/step1を指示する。P6/7.7/正式pin/実DBの資格を代記せず、必要な本操作分を個別に記録する。新野球意味未決は現調査では発見していない。runner statusの実保存文字列、v2 stamp/関数/ACL集合は段階4の有限物理packetへ具体化する技術供給で、旧物理の無制限変更許可ではない。
