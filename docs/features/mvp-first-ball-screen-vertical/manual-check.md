# 作成・開始・通常投球・四球・死球の手動確認（隔離環境）

## 現在の提供候補と実証

Draft PR #191の実装1fa8f21a、同source20で実画面の新規作成→開始→通常3球、無走者四球→次打者の1球、初球死球→次打者の1球、commit後ACK本文喪失からの原要求再送・復元の4経路が成功した（238.18秒）。実認証/API/broker/単一artifact/owned PGとnative表を照合し、事前投入試合・固定成功応答を使用していない。cache terminal-pitches-step5-https-r3-20261031/result.json SHA0e6f6ec2da566526aac9074063758ced515ea2d9fec88a72329f80638653d503。

保存コミットのsource20は実行前後と全byte同一、最終frontend133files/2857tests成功127.42秒。後続7646daabの差は旧backend試験の生成childコード折返しで、子/親AST不変。正式develop・全T1/MVP・実機の完成ではない。現在の自動環境は終了済みで、固定公開URLはない。以下は必要時に同じ製品版の専用環境を起動する手順である。

## 旧通常3球の実証（歴史版）

固定HEAD `e81c4edb5d2f55d67579e7e47aa9bbb24b6de055`、同一owned PostgreSQL・実API/brokers・実認証/初期記録権・製品artifact・Chromium・loopback HTTPSで、**画面新規作成→開始→ボール/見逃しストライク/ボール→同一要求再送→reload**を実証した。pytest全体1 passed / 148.93秒。サーバー再取得後は2ボール・1ストライク・履歴/PlayRow各3、nativeのplay_rows/operation_events/event_slots/accepted idempotency_ledgerも各3。D1/D2は(1,1)/(2,1001)/(3,2001)。事前投入したfixture試合を新規作成の証拠に数えていない。

証跡：`~/.cache/pitchlog/ordinary37-screen-success-20261030/result.json`（SHA-256 `770658e2982effc1620d01d568076e604c656fe0ed580dd219129ea10fbf0ab3`）。これは候補環境の自動実証で、正式develop統合・対象実機・1試合リハーサル・MVP完成とは別である。当時の任意hold追補は歴史記録として保持し、現在の入口は下記を使う。

## 同じPCで接続するための準備

固定の公開URLはない。ホストにdocker/owned PGを起動できる環境、node/pnpm、Playwright Chromium、backendの既存`.venv`を用意する。コマンドはdockerを操作できるホストで実行する。保持中はこのWTのsourceを編集せず、並行開発は別WTで行う。

既存の検証専用TLS資材を再利用する。公開証明書の期限は **2026-10-31 14:57:45 JST**、SANは127.0.0.1/localhost。期限後は更新準備が必要で、この手順では証明書/鍵を発行しない。鍵の内容を表示・共有・commitしない。

```bash
cd /home/ymdms/projects/pitchlog-worktrees/feature-mvp-terminal-pitches/backend
mkdir -p /home/ymdms/.cache/pitchlog/pytest-tmp-manual-terminal \
  /home/ymdms/.cache/pitchlog/browser-tmp-manual-terminal \
  /home/ymdms/.cache/pitchlog/frontend-tmp-manual-terminal
env -u PITCHLOG_TEST_ADMIN_DSN -u PITCHLOG_TEST_ROLE_DSN \
  PYTHONPATH=tests:src \
  TMPDIR=/home/ymdms/.cache/pitchlog/frontend-tmp-manual-terminal \
  PITCHLOG_PYTEST_TMPDIR=/home/ymdms/.cache/pitchlog/pytest-tmp-manual-terminal \
  PITCHLOG_E2E_BROWSER_TMPDIR=/home/ymdms/.cache/pitchlog/browser-tmp-manual-terminal \
  PITCHLOG_E2E_TLS_CERT_PATH=/home/ymdms/.cache/pitchlog/first-ball-https-tls-20261030/cert.pem \
  PITCHLOG_E2E_TLS_KEY_PATH=/home/ymdms/.cache/pitchlog/first-ball-https-tls-20261030/key.pem \
  PITCHLOG_E2E_MANUAL_HOLD_SECONDS=1800 \
  /home/ymdms/projects/pitchlog-worktrees/feature-mvp-first-ball-vertical/backend/.venv/bin/python \
    -m pytest \
    'tests/db/test_ordinary_screen_e2e.py::test_screen_three_ordinary_pitches_https_save_replay_reload[walk]' \
    -s -q --rootdir .
```

この1caseだけを選ぶrunが専用fixtureを準備し、自動画面でボール3球→四球→次打者1球・真terminal元要求再送・reload・DB照合の後に、API/Vite/両brokerが生存するcontext内で30分保持する。失敗した試験は手動holdへ進まない。接続先は表示される `PITCHLOG_E2E_MANUAL_ORIGIN=https://127.0.0.1:...`、チーム名は `PITCHLOG_E2E_MANUAL_TEAM_NAME` の引用符内（引用符は入力しない）。コマンドを実行した同じPCのブラウザで開く。ログインのパスワードは既存の**公開fixture値** `public-owned-vertical-password-A1`（運用資格ではない）。実利用者データは入力しない。

holdは既定0（通常試験は待機しない）、明示指定は1..3600秒。期限またはCtrl-Cで既存contextのcleanupへ戻り、専用環境/URL/試験データは終了する。hold表示時点では画面/DB照合済みだが、pytest全体の成功は期限到達後のsource同一性確認まで待つ。Ctrl-Cは中断として扱う。ブラウザの自己署名TLS確認後も、画面の実環境検査が不成立なら保存を進めない。

## 手動操作と期待結果

1. 表示されたfixtureチーム名と公開パスワードでログインする。自動試験で作られた試合は閲覧できる。自分で作成・開始する確認には、一覧の「新規作成」から**別の新規試合**を作る。
2. 自動試験と同じ入力例は、日時2026-10-31 10:00（日本時間）、区分「その他」（`game_other`）、fixtureの両チーム、大会は「新規」で任意の区別できる名前。「準備中の試合を作成」→「作成した試合IDの保存値を確認」へ進む。
3. 「この端末を登録」を押す。両チームの実名簿から重複しない選手を選び、守備位置を設定する。DH有効なら打順1～8に守備2～9、打順9をDH、10行目を投手1にする。DH無効なら9人へ守備1～9を重複なく割り当てる。
4. 「試合を開始」→「サーバーから復元／再取得」へ進み、通常投球フォームとサーバー確認済み0ボール・0ストライクを確認する。
5. 実際の条件を確かめて、同一ブラウザプロファイル/閲覧モード/サイト保存領域、Lockdown非適用の4確認欄を選ぶ。各球で結果・実球種・コース図の選択を確認し、「投球を確定・保存」を1回押す。環境条件が満たされていない状態をチェックで代用しない。

| 操作順 | 選ぶ結果 | サーバー再取得後のボール/ストライク | 確認済み履歴 |
|---|---|---|---|
| 1 | ボール | 1 / 0 | 1件 |
| 2 | 見逃しストライク | 1 / 1 | 2件 |
| 3 | ボール | 2 / 1 | 3件 |

各球は「サーバー確認済みの状態」を待ってから次へ進む。回・表裏・得点・アウト・走者はこの3球で変化しない。最後にページをreloadし、サーバー再取得で同じ2ボール・1ストライク・履歴3件を確認する。暫定表示や端末の未確認分は保存済みと数えない。

四球・死球を確認するときは、それぞれ別の新規試合から始める。四球はボールを3球保存した後、結果「四球」と「次の打者を確認」で実名簿の2番を選ぶ。死球は開始直後に結果「死球」と同じ次打者確認を選ぶ。球種・コース・端末条件も確認して保存する。

| 経路 | 終端保存・再取得後 | 次打者のボール保存・reload後 |
|---|---|---|
| 無走者で3ボール→四球 | 0ボール/0ストライク、一塁走者、2番、履歴4件 | 1ボール/0ストライク、一塁走者、2番、履歴5件 |
| 開始直後の死球 | 0ボール/0ストライク、一塁走者、2番、履歴1件 | 1ボール/0ストライク、一塁走者、2番、履歴2件 |

四球・死球と次打者の1球では、得点・アウトは変わらない。表示中ページのPlayRow数は有限ページの件数で、試合全体の保存済み履歴長とは区別する。再送・応答喪失の故障注入は自動試験で実施し、手動確認のためにDevToolsから元要求や資格を抜き出さない。

未応答では成功と扱わず、「先頭の未確認要求を同じ内容で再送」を使う。新しい要求への置換や連打で解決しない。同一要求の再送で二重保存しないことは上記自動実証に含む。手動確認の結果は試合ID・操作・表示・時刻を記録し、Cookie/端末資格/要求原文は共有しない。

## 制限と実機リハーサルへの条件

現在の経路は通常の非終端投球（ボール・見逃し/空振りストライク・通常非バントのファウル）と、無走者の明示四球/死球を対象とする。在塁時の四球/死球、三振、第3アウト、打球/走者/交代、取消・過去訂正・終了/再開、成績/CSVは未完成部分があり、この有限経路の成功から完成としない。打席側・球速・構えは現画面では未入力として保存する。未接続操作の拒否は成功ではない。MVP全体の受入対象は維持する。

loopback/self-signed TLSは**同PCの隔離確認用**で、LAN/iPhone/iPadから使う信頼済み接続先は未準備。実機担当は山田正輝。iPhone Safari/iPad Safari/PC Chrome・Edgeの確認と1試合リハーサルには、端末から到達可能なチーム用HTTPS、正しいホスト名と信頼できる有効証明書、同一originのAPI、実Web Locks/IndexedDB、通常/プライベートを混在させない記録環境を準備する。公開・共有DB適用・有料資源・秘密発行は既存の承認境界に従う。

対象実機、LAN/運用HTTPS、オフライン復旧・負荷・運用復旧と全1試合は実施待ち。自動Chromiumや証明書例外を実機/運用TLSの受入へ読み替えない。

旧 `feature-mvp-first-ball-vertical` / `test_screen_start_e2e.py -k first_ball_https` の1球hold手順と54b83002の実証は歴史版。現ordinary候補との互換を再実証したものではなく、現在の手動環境準備は上のterminal候補のowned fixtureを使い、起動時に選んだ1caseと製品版を記録する。
