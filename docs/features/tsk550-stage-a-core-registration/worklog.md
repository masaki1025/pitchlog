# TSK-550 段階A起動入口のコア領域先行登録 作業ログ

## 2026-10-19: 最新develop取り込みと競合解消

- 本人逐行確認は未実施のまま、`origin/develop=ba339cf8`を通常mergeで取り込んだ。競合は`.claude/core-areas.json`、`scripts/core_guard.py`、`tests/test_core_guard.py`の3ファイル。developのU-R1/RG1、LoginScreen、router/Appの登録を保持し、登録済みRG1とrouter/Appの宣言を追加層から回転させた。#158固有の`stage_a_startup.py`だけをgame-state・tenant-isolationの追加層に残し、両領域のJSON末尾へ各1件登録した。#158の宣言・JSON別コミット履歴は通常mergeで保持し、履歴を書き換えない。
- 最新developの既定試験と#158の起動入口試験を統合し、宣言済み追加層・基線据置き・未宣言追加拒否・後続の試験パスへの回転を確認した。`uv run pytest tests/test_core_guard.py -q`は268成功、`uv run ruff check scripts/core_guard.py tests/test_core_guard.py`と`uv run ty check`は成功。コア領域の追加差分レビュー・PR最終HEADのCI・本人逐行確認は別ゲート。以前のレビューや本人確認をこの競合解消差分へ自動延長しない。
- 競合解消差分の限定敵対レビューを`154ce5b4`対`ba339cf8`で実施した。実モデル`gpt-6-sol`・effort`xhigh`、判定は可決、P0/P1/P2は各0。レビュアは既存登録の全保持、2領域の宣言とJSON、未宣言追加拒否、後続の宣言回転、未記入の人間確認拒否を確認した。既済みの全文レビューを繰り返さず、過去のレビューを今回の差分へ自動延長していない。rootの`uv run ruff check .`と`uv run ty check`も成功した。

## 2026-10-19: 計画承認

- 山田正輝が比較元`015dfa9d`、計画SHA-256 `8739118d47a2274371e40bebff44b0bd1ff9b29ec0e9df661ad91613aeaced95`の専用2ステップ計画を承認した。承認欄追記後のファイルSHAは承認対象の原案SHAと異なるため、原案の識別値をここに保持する。
- 第2回レビュー後の反映差分は独立再レビュー未実施。P1の指摘を採用し、#152取り込みを本PRのDoDから外して申し送りに限定した差分を人間が承認した。コアPRのコード敵対レビューと本人逐行確認は別ゲートとして残す。

## 2026-10-19: ステップ1

- `origin/develop`=`015dfa9d`を再取得して承認時の比較元と一致することを確認した。
- 起動入口の完全パスをtenant-isolation・game-stateの追加層へ宣言。既存RG1宣言とJSON基線は据置き。宣言のみの中間状態、両領域登録、未宣言追加拒否、後続の宣言回転を試験に追加した。複数パスの部分追加拒否は既存試験で維持する。
- `uv run pytest tests/test_core_guard.py -q`: 264成功。`uv run ruff check scripts/core_guard.py tests/test_core_guard.py`、`uv run ty check`: 成功。

## 2026-10-19: ステップ2

- JSONのgame-state・tenant-isolationに`backend/src/pitchlog/db/stage_a_startup.py`を各1件追加。RG1と既存の全登録を保持した。U-S1登録確認試験の旧「残り3領域はすべて据置き」前提を、今回の2領域のみ宣言済み追加層として検証する形に追随した。
- `uv run pytest tests/test_core_guard.py -q`: 264成功。`uv run ruff check .`、`uv run ty check`: 成功。
- root `uv run pytest tests/ -q`は99%まで実行したが、DB依存の失敗を確認して中断。`--lf -n 0`で`tests/domain/mut/test_lang_operators.py::test_each_language_mutants_are_actually_killed[sql]`が`127.0.0.1:5432`接続拒否と確定した。`docker compose ps`も`POSTGRES_PASSWORD`未設定で起動構成を解釈できない。秘密設定を読まず、全件成功とは記録しない。PR CIで再確認する。
- TSK-372正式カードへ`games.applied_rules`限定先行単位の対象・DoD・影響・所有側受諾をコメント`3fd93b75-e687-8157-b42d-001db6aa17e0`で照会。返答前につき受諾未確認。候補worktree`feature/orm-applied-rules-immutability-candidate`の`d8cc9448`を保持し、全23表へ拡大しない。

## 2026-10-19: コア敵対レビュー第1回の採否・#152申し送り

- 第1回全文レビューはP0 0/P1 1/P2 1。P1「実JSONに基づく将来パス変更と未記入チェック拒否の回帰試験がない」は**採用**し、登録コミットの履歴有無でステップ1中間状態とステップ2以後を分ける試験を宣言コミットへ追加する。P2「#152への申し送り不足」は**採用**し、本節を追記する。反映差分と影響箇所を第2回レビュー対象にする。
- #152はこの専用PRの**実統合SHA**を確認して最新developを取り込む。`backend/src/pitchlog/db/stage_a_startup.py`はgame-state・tenant-isolation双方のJSON基線に残し、両領域の`AREA_PATH_ADDITIONS`を登録済み起動入口から`backend/tests/test_rule_resolution.py`の追加パスだけへ回転する。既存RG1宣言・登録を落とさず、#152の元のステップ7・8の対象と順序は変えない。後続の新基線で7.7実値を再導出し、#152の既受理履歴は書き換えない。
- 第2回差分レビューはP0 0/P1 0/P2 0。第1回P1・P2は解消と判定された。レビュー環境は読取専用でpytestを実行できなかったため、実行側でcore-guard 265件成功、Ruff・ty・基線検査成功を別途確認した。第2回後の本行とPR本文の記録更新は独立再レビュー対象外の文書追記として人間確認に残す。

## 2026-10-19: 計画レビュー

- 起点: `origin/develop` `5bb1ff89306712c1de61c3a0152141c8f771b3a0`。TSK-550本体#152はDraft・HEAD `401ea428`。本PRは起動入口の完全パスを先にJSON基線へ載せ、#152の既存ステップ7・8を後続試験パス用に維持するための独立2ステップ。
- 6.1コア領域計画レビュー第1回（全文）は**否決 P0 0/P1 2/P2 0**。P1①: #152へ取り込む際、tenant-isolation・game-stateの両宣言から統合済み起動入口を外し、試験パスだけへ回転することが未記載。**採用**し、計画4節・DoDへ記載。P1②: 今回の1パスを片方の領域だけへ登録してもguardは各領域を独立評価するため、「部分追加拒否」と呼べない。**採用**し、部分追加負例を既存の複数パス宣言領域の一領域内へ限定、今回の2領域登録は別の一致性確認とした。
- 第1回レビューは、U-R1/RG1の既存宣言保持、未作成ファイルのパス一致、2コミット分離、7.7既受理値の据置きには指摘なし。P1反映差分と影響節だけを第2回レビュー対象とする。指摘反映により計画レビュー周回を1とした。
- 計画承認・製品/guard実装・push/PR作成・本人逐行確認・マージは未実施。

- 第2回（第1回P1反映差分＋影響節）は**否決 P0 0/P1 1/P2 0**。P1: 本PRのDoDが統合後の#152による取込作業そのものを要求しており、本PRの2ステップでは達成できない。**採用**し、本PRのDoDを#152への引継ぎ内容のPR本文または作業ログへの記録に限定した。反映後の差分は基本枠上限のため独立再レビュー未実施で、人間の計画承認対象とする。計画レビュー周回は2。
- 第1回・第2回ともP0なし。追加レビュー枠は使っていない。既存#152本体の計画レビュー周回4、コアPRレビュー既定2回＋追加1回とは別のレビュー対象として記録する。
- 計画worktreeは`origin/develop` `5bb1ff89`から開始し、第2回レビュー中に#155統合後の`015dfa9d`へfast-forwardした。追加3ファイルはU-X1の計画・設計・作業ログで、core-guard/JSON・受理資産との交差はなかった。実装開始時には再度最新developを照合する。
