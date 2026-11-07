# 通常49・実出場成績HTTP接合

準備版（実PG未実行）。起点9f7e4ad882557a0434e31fd4bc086f0d9dc68471はrootの正常49/fullcatalog/故障/余剰xmin拒否4passed97.45秒の版。この実証を新HTTPシナリオ成功へ読み替えない。

既r20のscript生成だけを共通関数へ抽出し、前後SHA dd7092273b5fa6dfef2ef6f968565ab2cbca96f95b931f4cb1394aaf10b776b4で全byte一致。旧候補試験のinstall呼出・fault/越境/不正対向は変更せず、正常49新試験は候補installerを一切呼ばない。

同一実新規試合のstart0球→通常3球→投手0球交代/同D5再掲→終了v1→再開（公式対象外）→4球目→再終了v2→GET/reload/試合・season・双方CSVを用意。raw entryの実side/player、交代前後のnative版/S/source IDs/slotの完全同一、CP変更、交代playerの0 physical pitch、要求event ID/実proof一致、v1失効/v2の真正pointerをhost read-onlyで照合する。開始0球時の成績未供給を0補完せず、実proofだけ確認する。P3/全試合0球/実画面/実機は未達のまま。

準備検査はdriver/既D03/0049構造の80passed3.45秒、driverだけの後発3passed、対象Ruff/全Ty0。旧script byte比較・新scriptのdeterministic/compile・候補DDL/権限install無しを純対向で確認。新試験はCURRENT49/fullcatalog/5helper owner・外部EXECなし/主要hookを配置から読み取る。名簿/語彙以外のfixture補完はしない。

固定HEAD/patchをrootへ送付後、recovery先行と共通owned lockの次順で1回を実行する。共有DSN unset、全source前後SHAとfixture cleanupを保存し、失敗時は同入力反復せず停止原因を固定する。新テストの最終非作者確認は別。
