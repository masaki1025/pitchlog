# 初球の手動確認（隔離環境）

## 実証済みの範囲

固定HEAD `54b83002b04357f776801a0d2e4c77d157508da8`、同一owned DB・実API/broker・Chromium・loopback HTTPSで、画面新規作成→開始→初球ボール保存→サーバー再取得→同一要求再送→reloadを実証。pytest全体1 passed / 46.29秒。reload後は1ボール・0ストライク・履歴1・PlayRow1、得点/アウト/走者/scoreboard不変。DBのplay_rows/operation_events/event_slots/idempotency_ledgerも各1件。

証跡は `~/.cache/pitchlog/first-ball-https-evidence-20261030/result.json` と `attempt5-playwright.log`。正式develop統合・対象実機・全操作・MVP完成の証拠ではない。

## 接続先と起動

自動試験の環境は終了済みで、固定の公開URLはない。以下の明示holdで専用環境を起動し、表示される `PITCHLOG_MANUAL_URL` のloopback URLを同じPCのブラウザで開く（hold機能の反映版を使用）。`PITCHLOG_MANUAL_TEAM` が試験チーム名。LAN公開や共有DBへの適用は行わない。

```bash
cd /home/ymdms/projects/pitchlog-worktrees/feature-mvp-first-ball-vertical/backend
env -u PITCHLOG_TEST_ADMIN_DSN -u PITCHLOG_TEST_ROLE_DSN \
  PYTHONPATH=tests:src \
  PITCHLOG_PYTEST_TMPDIR=/tmp/opencode/pytest-tmp-manual-first-ball \
  PITCHLOG_E2E_TLS_CERT_PATH=/home/ymdms/.cache/pitchlog/first-ball-https-tls-20261030/cert.pem \
  PITCHLOG_E2E_TLS_KEY_PATH=/home/ymdms/.cache/pitchlog/first-ball-https-tls-20261030/key.pem \
  PITCHLOG_E2E_MANUAL_HOLD_SECONDS=1800 \
  .venv/bin/python -m pytest tests/db/test_screen_start_e2e.py \
    -k first_ball_https -s -q --rootdir .
```

自動縦断とDB件数検査が通った後、最大30分保持する。終了は期限またはCtrl-Cで、当該owned環境だけを後始末する。TLS資材はPOが許可した検証専用自己署名・1日有効。鍵の内容を表示/共有/commitしない。証明書の期限が切れた場合は同じ検証専用範囲で再準備する。

ログインのパスワードは既存の**公開fixture値** `public-owned-vertical-password-A1`（運用資格ではない）。実利用者データは投入しない。ブラウザでは検証用自己署名証明書の確認が必要。

## 操作と期待結果

1. 上記URLへログインし、一覧の「新規作成」から別の試合を作る。区分はテストで通した「その他」（内部key `game_other`）、両チームはfixtureのチーム、大会は新規名にする。
2. 「作成した試合IDの保存値を確認」へ進み、「この端末を登録」を実行。両チームの実名簿から重複しない選手と守備位置を選ぶ。DH有効なら10人（打順9人と投手）を設定する。
3. 「試合を開始」を押す。開始応答保存後に実サーバー再取得へ進む。必要に応じて「サーバーから復元／再取得」を押す。
4. 実際の環境条件を確認して4項目をチェックし、実球種を選択。コース図をタップして「ボールを確定・保存」を押す。未確認条件を満たしたと偽ってチェックしない。
5. サーバー表示が1ボール・0ストライク・履歴1件になる。ページをreloadして同じ表示になることを確認する。得点・アウト・走者は変わらない。

未応答では保存成功と表示せず、旧要求の確認／再送へ進む。新規確定を連打して別要求へ置換しない。自動縦断では同じ要求を1回再送し二重保存しないことを実DBで確認している。

## 既知の制限と実機条件

この候補の画面接続は初球ボールのみ。2球目以降・取消・訂正・終了・成績/CSVは後続接続で、MVP全体から除外していない。正式7.7/認可資産/通常統合も別途継続する。

loopback URLと今回の証明書はiPhone/iPadからの接続先ではない。実機リハーサルには、端末から到達可能で信頼されるチーム用HTTPS環境を別途用意し、Safari/Chrome/Edgeの対象条件で確認する。自動ChromiumやTLS信頼例外を対象実機・運用TLSの受入へ読み替えない。
