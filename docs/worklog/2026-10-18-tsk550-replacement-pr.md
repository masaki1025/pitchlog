# TSK-550 段階A resolver の別PR受理経路

## 番号取得時点

- 比較元: `origin/develop` `5bb1ff89306712c1de61c3a0152141c8f771b3a0`（#148統合後、初回比較元`156dd139`から追随）。既受理のtenant-boundary履歴23件を保持する。
- 旧Draft PR #149と `feature/ux1-fr014-rule-resolution` は未マージのまま保持する。旧#149の受理記録、受理済み値、レビュー証跡を変更・削除しない。
- #149の記録差替え・同一ID再使用案は、ハーネス設計書§7.7-2の追記専用・書換禁止と、資産の単一PR受理境界に反するため採用しない。§7.7-4はこの禁止の例外を与えない。
- 本PRは、#149の必要な製品差分とTB005・認可派生の限定是正を新しいPR IDで受理する経路。実PR番号の取得までは文書のみをpushし、製品候補と凍結資産の新値はローカルで再導出する。7.7正式受理前に新履歴へ仮番号・承認者・承認日を記入しない。
- 既定独立レビュー2回と#149固定HEAD `39fdcb6d`への追加1回を継承する。追加レビューのP0は旧履歴差替え（別PR化で処理）、P2は各記録案SHAの未固定。新PRへの履歴処理と後発差分は独立再レビュー未実施として区別する。

## 差分移植後に固定するもの

実PR ID、候補tree、oracle入力commit、比較元の全before値、候補の全after値、9資産・外部8ファイル・corpus・認可8入力・seal、各tenant-boundary/seed/oracle_input記録案のJSON実体とSHA、全体資料SHAを機械再導出し、一括で7.7正式受理へ提示する。旧#149の実値承認を新PRへ流用しない。正式履歴反映・既存DB適用・試合作成公開・本人逐行確認・Draft解除・マージは別ゲート。

## 移植照合（Draft PR #152）

- 実番号はDraft PR #152。番号取得時の公開HEADは文書のみの`ff7afd0f`。製品候補はローカルに限り、まだpushしない。
- 旧ブランチ`67a6a68b`から、段階A resolver、0033配置、認可/起動候補、TB005限定許可・負例と関連試験・承認済み正本/計画の差分を移した。旧#149専用の3資料（旧7.7記録案、再受理候補、候補射影）と11個の旧履歴snapshotは移していない。旧資料の完全値と承認証跡は旧ブランチに保持する。
- `contracts/tenant_boundary/base-allowlist.json`の旧#149末尾1行を除き、developの23行接頭部と一致させた。`contracts/migrations/seed-allowlist.json`の旧#149相当末尾1行を除き、developの3行接頭部と一致させた。`contracts/authz/frozen-baselines.json`のoracle履歴12行はdevelopと一致する。これらの新PR用履歴は正式受理まで追加しない。
- 旧作業ログと計画の#149記載は歴史的証跡として保持し、旧ブランチで保存する資料へのリンクは現在のPRの採用資料と誤認しない表記に改めた。#149差替え案は本PRの方針ではない。

## ローカル候補と7.7提出値（未受理）

- 製品候補の移植コミット`4b85b358acb87d32ec964bd76856eb0c1cfec3f6`をoracle入力commitとし、6oracle本文の参照だけを更新してsealを候補再計算した（`ab6fbf7aa4257cf06672873d9e0c49509dbe63eb`）。製品登録・権限・規則値の新たな拡大はない。現在の製品/資産入力treeは`047c6f11daed190f012950775b2ea4e9e3dbcb18`。入力treeは以下の資料自身を含まない。
- [完全な候補資料](../features/ux1-fr014-rule-resolution/step3-pr152-7-7-candidate.json) SHA-256 `e297aaf7fdd0cc0542488a488af0af61e2964aca82c4d237a79a7d505300f6d8`へ、9資産と外部8ファイルの前後値、corpus、認可8入力・seal、比較元、旧候補対応、承認未記入状態を収録。各履歴記録案の独立SHAはtenant-boundary `b76b13db0d3c992b3be4f58207d59adc67a97cf8aa96b9498d722c336e8a19fc`、seed `7e33f37146677b9efefc7384b3ecb8ff9d75049597b39530e3dc07efd0723732`、oracle_input `a4a8ea66f7cdccdb6dc2545e13a2c076bb6234f102cb1b5a0ab96b6a58b054fc`。3案はいずれも正式履歴でなく、承認者・承認日はnull。
- 9資産射影と外部8ファイルの前後値は旧#149の限定是正候補と同じ値であることを実ファイルから再導出して確認。これは旧7.7承認を流用する意味ではない。corpus実入力digestは`ab298c6cfa8d0e3a57fad7369dfb993771235cb6c0ea454da8fee846d401b117`、manifest既定値は受理前の`aad2db0462f394fb2de17ae0c1ed406724e3ad5d2769e29f523503c75522d10e`のまま。authz入力8 blobは新入力コミットと一致、6seal digestは新コミット参照に伴い再導出した。
- 限定試験`tests/test_stage_a_startup_tenant_boundary.py`は4件成功、認可`--skip-oracle`は1418件を検査し成功。tenant-boundary基線検査は履歴23件に対して候補識別値が進んでいるため予期した拒否（末尾識別値不一致）。通常認可検査・corpus pin・全件ゲートは正式7.7受理後まで合格扱いにしない。移植・受理案の後発差分は独立再レビュー未実施、既定2回＋追加1回を維持。

- **#148追随**: `origin/develop=5bb1ff89`をローカルへマージし、`docs/README.md`の1件競合は同期プロトコルv0.9行、TSK-550 data-model v1.1行、FR-014認可面行を同時に保持して解消した。#148の設計本文・伝播試験を保持し、凍結資産と既受理23/3/12件は不変。資料値をこの比較元から再導出した。

## PR #152 の7.7正式受理と反映（2026-10-18）

- 人間の受理対象は比較元`5bb1ff89`、候補入力tree`047c6f11daed190f012950775b2ea4e9e3dbcb18`、oracle入力commit`4b85b358`、一括資料SHA-256`e297aaf7fdd0cc0542488a488af0af61e2964aca82c4d237a79a7d505300f6d8`。tenant・seed・oracleの記録案SHA-256は順に`b76b13db0d3c992b3be4f58207d59adc67a97cf8aa96b9498d722c336e8a19fc`、`7e33f37146677b9efefc7384b3ecb8ff9d75049597b39530e3dc07efd0723732`、`a4a8ea66f7cdccdb6dc2545e13a2c076bb6234f102cb1b5a0ab96b6a58b054fc`。承認者は山田正輝、承認日は2026-10-18。3案の承認欄を正式履歴へ反映し、比較元の23/3/12件はそのまま接頭部として保持する。旧#149の記録・ブランチは変更・流用しない。
- 9資産の射影と外部8ファイルのbefore/afterを候補資料と照合してcontent-addressed snapshotへ保存した。比較corpusのpinは承認済み`ab298c6cfa8d0e3a57fad7369dfb993771235cb6c0ea454da8fee846d401b117`へ更新し、oracle sealの候補値を維持する。承認対象の入力ファイル、比較元、実値に変化があれば受理済み履歴を差し替えず別差分として扱う。
- 既定の独立レビュー2回と限定追加1回の証跡を維持する。別PR化、履歴処理、後発差分の独立再レビューは未実施。今回の7.7受理は本人によるPR全体の逐行確認、N3-061の是正、試合作成公開、既存DB適用の承認ではない。
