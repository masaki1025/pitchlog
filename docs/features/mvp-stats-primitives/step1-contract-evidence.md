# ステップ1(a) 閉入力・共通count事実・独立期待の候補

対象: 主担当採用済`mvp-stats-primitives/plan.md`末尾のステップ1(a)。編集は`primitive-{input,output,cases}.candidate.json`と本evidenceの4パスだけ。正式contracts/共通model/生成器/製品/DB/registry/refsを変更していない。候補の正式受理と独立非作者レビューは未実施。

## 具体的な比較契約

`primitive-input.candidate.json`はDraft2020-12閉schema。全23flagはrequired boolean（追加/不足/NULL拒否）、実before/afterの回・表裏・カウント・アウト・得点・打順・走者、実参加者と成績の帰属先、PA開始/完了/番号・途中投手交代時の実count、結果ID/安打種別/表示snapshot、実効outs数量/対象、走者別有効得点・RBI分岐/数量、明示的盗塁観測を持つ。primitiveはT1の結果を再裁定しない。

出力は26個の既確定count/十分統計、値/整数表示/状態/理由、選手・source別寄与、同じFR-022の7列PA行（識別欄・欠測状態を併置）、source/model版を比較する。PA/AB/H/2B/3B/HR/TB/BB/HBP/K/SH/SF/妨害出塁、球数/outs/投手K/BB/HBP/被安打/被HR、走者別得点/RBI/失点、盗塁・失策まで一つの宣言・同じtyped count/add engineで扱う。いずれかのsourceが未実装ならその依存metricだけsource_unavailableを残し、他の閉じた群を先行できる。率の完成はステップ3で、ここでは分子/分母の十分統計参照だけを列挙する。

PAは一つのcanonical PA行から数え、1球ごとにPAを加算しない。Kはoutsと独立。塁打や複数outs/得点/RBIをtrue=1で埋めない。第3out後にoutsが0へ戻ってもbefore/after差分から数量を推測しない。RBIが未供給でもPA行の既知欄を保持し、RBIセルをnull/source_unavailableにする。走者の失点は責任投手、継承BBはA-2の正式帰属に従い、BFへ転用しない。

`primitive-output.candidate.json`のpendingはD02（公式/練習/合算写像）、D03（登板）、D04（BF）、D05（OPS）を全てnull/decision_pendingで維持。0球出場/未完PA/継承/再登板を観測として保持しても公式登板/BFを作らない。既決JST暦年を再裁定しない。

## 真正sourceとJSON型の分離

JSON型合格、receipt UUID、hash文字列、fixtureの説明だけで認可/真正性は成立しない。正式`ReadPlayExportPrimitives`/登録providerが同tenant transactionで以下を別に解決・照合する責務を契約へ記載した。

- assembly/provider receiptの実在と受理、tenant/game・membership epoch/RG1 fence。
- 受理event/D5/ledger、実記録権世代・D4 binding digest・D1/D2、checkpoint ID/revision、slot/PlayRowの確定版と原payload/投影digest。
- rule/vocabulary/T1 artifact/model/投影schema hash、computed_metric_keysと完全性。
- 実PA開始完了/参加者/交代・責任、outs/有効点/RBI/盗塁観測が正式sourceと一致すること。
- Sの有効・適用済最新版を選び、取消/置換/退役/監査controlを集計から除外。旧世代の有効playは保持。同D5再送/重複sourceを二重算入しない。
- T6は正式終了receiptと同じ公開成績pointer/最新版/同modelを確認し、同tenant/player/JST暦年/原game type keyでDB絞込する。`finished`文字列単独で確定扱いしない。

device_provisionalは未commit ledger/物理rowなし・未割当D1/D2を明示し、device operation UUIDをaccepted DB eventと混同しない。実device/base checkpointの資格は別境界で検証し、provisional値を公式pointerへ公開しない。confirmed scopeへ同じ入力を渡す対向は拒否。

候補caseのprovider_binding_rowsは独立harnessの照合fixtureであり、本番の受理済provider receiptではない。モデル/artifact等のhashもfixture識別子であって実版受理の主張ではない。正式providerのSQL/RLS/実ledger/checkpoint/版結合の実測は後続ステップに残る。controlにT1全値が無い場合も23個falseを補完せず、S選択で外すか未対応sourceを非成功にする。

## 原典から固定した独立期待

正本は現要件のFR-020/022、4.0-2、A-1/A-2/A-3/A-4/A-5、E-1の23flag外延・数量規律、E-2 SO-01〜05/RBI-01〜09。方式はADR-003 D-1/D-1-d、NFR-005/018。計画2.1〜2.3と全27対応表をこの具体的な閉型へ落とした。

`primitive-cases.candidate.json`には**55個の具体的input/expected JSON**（元50個を保持、provider拒否2件/RBI適用域拒否3件を追加）と、500/501window・23flag exact-setの**2個の有限展開比較面**を置いた。期待nonzeroは作者が原典から手指定し、それ以外のknown-zero、per-player credits、PA行/整数表示/pendingを明示した。製品artifact・生成器・native runtime出力・P-6封印を期待の算出元にしていない。構造scaffoldの共用は期待計算ではない。

例: 振逃げ生存はK1/outs0、振逃げ送球outはK1/outs1、三振併殺はK1/outs2。3人の有効HRはHR1/TB4/R3/RBI3。3-1継承四球は実投球を現投手、BBを前投手へ。1PA中2球は球数2だがPA1。置換single→doubleは旧singleを除きH1/TB2。取消は0。既有効2世代の同D1=1は球数2。T6は9007199254740993+2=9007199254740995を正確に保持し、再開/旧版/別年/別raw keyは除外。source不明をknown0にせずnull/unavailable。異tenant/game/ledger/checkpoint/slot/model/artifact、重複source、flag欠落/追加/NULL、投球種別不一致は拒否。

ケースの物理T1/source適合・独立期待の正式受理は非作者確認前。候補作者による静的整合確認を独立受理の代わりにしない。

## ステップ1(b)直後の実装単位

正式対象別契約/独立期待/検査基盤の受理後、root指示で、共通model ID/hash/type参照解決とtyped record/collection・integer0/1/count/add・enum-hit種別→TB lookup・整数formatterを生成する。投球数だけに縮小せず、PA/AB/H/2B3BHR/BB/HBP/K/outs等のsourceが閉じた群を同じengineへ通す。source_unavailable群を仮false/0で埋めない。

αのPython/TS比較は同一宣言の生成target、βの実表SQLはWHERE/GROUP BY/COUNT/SUM/window＋索引。共通count式の手書きコピー/全eventアプリ集計/TS同artifact例外拡大をしない。T6は同canonical T5 count事実とcomputed_metric_keysを受け取り、DBで十分統計を合算。欠測factのnullを0へCOALESCEしない。window後にkeysetを掛け、500→501で累積を再開始しない。target/typed受け口/完成表示、比較の反例、性質、非等価変異を同一対象変更へ揃える。

必要なfield/operatorはinput候補x-d1-field_operations、primitive ID/source/reducer/formatterはoutput候補x-primitive_definitions、各独立期待はcasesへ列挙済み。モデル/生成器に表現不足がある場合は具体式だけをrootへ返し、D-1未対応を手書きSQLや新意味で埋めない。

## 検証と未成立

共有DSN/DB/製品artifact/生成器を使わず、既jsonschemaでDraft2020-12自己schema検証、全55caseの正例/意図的schema拒否、全expected出力schema、23flag全required/true被覆、既知countsと手指定credit数量の整合を静的確認した。これは型・期待文書の内部整合であり、source認可/数学実行/SQL/3層/実画面/CSVの成功ではない。

新しい野球意味の裁定要求は追加していない。未回答D02〜05、未実装native variant/source projection、正式providerの真正照合、独立期待受理、D-1モデル/実生成/DB実行・3層が未成立。完了packet/hash/原典一覧はcacheへ保存し、作者writerを停止する。

補足: available/value/display/reasonとsource_unavailable/nullは説明だけでなく出力schemaのoneOfでも区別し、PAのRBI欠測も型で結合した。T5 factのcomputed_metric_keysとnullable sufficient statisticsを明示し、空集合の真正0と部分factの欠測を区別する。source/bodyの具体既存パスと未供給のadapter責務はinput候補x-native-field-bindingsへ固定した。


## 非作者レビューP1-01/P1-02の最小修復

REPORT SHA256 `0483f0ffe2a7d522868a92cef85f474cdb900b9d42c00010c0717d7bfdd9c11c`（P0=0/P1=2）を採用。通常walk正例のbefore.ballsを0→3、nonpitch steal正例のbefore/after.runner_idsへ当該走者を明示し、provider fixtureのbound_source_observationsも同じ原典側状態へ揃えた。成功BB1/SB1等の算入期待は変更しない。元のB0四球/走者不在盗塁入力は新しいprovider/source拒否ケースとして保全し、T5に四球や盗塁の野球判定を追加していない。

50既caseを同じ限定面で確認した。通常結果球walkはB3、継承walkは既3-1のまま。申告敬遠non_pitchは通常四球の4球目条件と区別して0球の既規範を維持。盗塁成功者のbefore/after所属を確認し、空走者の元不整合を成功入力へ残さない。その他のK/out0/1/2・第三out reset・PA開始/完了・有効/無効得点・T6/拒否期待は保持。この限定点検を全source/native野球判断の新受理と呼ばない。

A-1 OUT3末尾の入力域除外をschemaへ反映。valid_run=falseではrbi_branch=null/rbi_credited=false/rbi_batter_id=nullを閉じ、RBI-*へ渡さない。valid_run=trueでは既9分岐の必須参照を維持する。mixed正例の無効到達に付いていたRBI-09をnullへ訂正し、有効2得点/RBI1/投手責任の期待値はそのまま保持。元の無効+RBI09入力、無効+算入true、有効+branch欠測の3つをschema拒否へ追加した。RBI再裁定・責任推測は追加していない。

修復後55case、元50caseの期待出力は全件同一。26primitive/全23flag/T5→T6/D-1/外部provider認可責務/D02〜05 pendingを維持。静的schema/期待整合の再確認を行い、実装artifact・生成器を期待の算出元にしていない。採用前の同非作者限定再確認とroot採否は未実施。修復packetへSHA/差分範囲/原典/未成立を固定後、writerを停止する。

## 2026-11-04 主担当の操作単位採用と1(b)開始

PO委任によるCodex主担当/root判断。修復1のexact4集合SHA256 `85e0770c5fa2776a7e45f573125f6281abbd32f5fb5c65c46210d9d5814a8c76`を現物で照合し、非作者初回REPORT `0483f0ffe2a7d522868a92cef85f474cdb900b9d42c00010c0717d7bfdd9c11c`の2件を是正、同非作者の限定再確認 `60ec4fdebf0d62dc394ddf2f2881655c7031aac0548631b35d4401f0cf371a90`で未解消P0/P1=0を確認して、本対象群の契約候補/規範期待を有限採用する。元50期待出力と不整合inputの拒否保全、全55schemaとRBI有効/無効適用域の独立確認を継承する。P-6 blindや本人逐行確認/署名、実source provider・DB真正性の受理ではない。

指定範囲のステップ1(b)を開始し、D-1の閉型参照/整数・boolean/有限reducer/実Python・TS・SQL生成の不足を実装する。採用済み対象群を実計算し、全体開始待ちや投球数だけのsampleへ縮めない。正式契約配置・source registry・DB適用・モデル版の最終受理はrootが後段で直列化する。1(b)で候補schema/期待を製品出力へ合わせて緩めず、表現不足や新意味が判明した場合は具体的に分離し、独立単位のコードを進める。T5/T6完成や既未回答4件を完了扱いにしない。
