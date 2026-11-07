---
feature: ci-pytest-throughput
status: in-review
承認: PO委任によるCodex主担当/root判断（2026-11-07、原候補継承と非作者P1是正）
重さ分類: 通常
branch: feature/ci-pytest-throughput-finalization
created: 2026-11-07
計画レビュー周回: 0
確定ゲート周回: 0
---

# pytest 分割の 8 分割化と実行時間重み付き割当

## 1. 背景

固定 HEAD `12cc636dfaaea2ef6ecba2985492d3acb3f1dc30` の CI は、harness と backend を
それぞれ 4 シャードで実行している。実 CI のログでは収集順の剰余による割当が実行時間を
均しておらず、backend は 23〜35 分、harness は 8〜23 分の幅で、遅いシャードが
クリティカルパスになっている。検査内容と拒否条件を変えずに、シャード数と割当だけを
見直して待ち時間を短縮する。

## 2. スコープ

やること:

- backend を 4 から 8 シャードへ増やす。
- harness も 8 シャードへ増やす。backend の短縮後も harness がクリティカルパスに
  残らないことを、実 CI ログのシャード所要から確認する。
- 既存の実行時間ログ（CI run の pytest `--durations=25`）からテスト単位の重みを作り、
  重いテストから最も空いているシャードへ置く決定的な割当へ変える。
- 収集したテスト ID の和集合が全件と一致すること、新規テストが重みに無くても
  ちょうど 1 回だけ割り当てられることを `scripts/pytest_shards.py verify` で検査する。
- シャードごとの PostgreSQL service、必須チェック名、集約ジョブの失敗・キャンセル・
  未実行の拒否、カバレッジ計測と artifact を維持する。

やらないこと:

- テストの削除・skip・marker 選択・`--ignore` の追加による検査範囲の縮小。
- カバレッジ計測（`--cov`）や `fetch-depth` の削減。
- 必須チェック名・集約ジョブ名・GitHub Ruleset の変更。
- 有料 runner、main / develop への直接変更。
- 製品コード、共有台帳、正式な凍結資産、受理 record、seal の変更。

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `.github/workflows/ci.yml` | シャード数・表示・コメントの 8 分割化 | PR レビュー |
| `ci/pytest-shards.json` | 8 分割と実行時間重みの定義 | PR レビュー |
| `scripts/pytest_shard_plugin.py` | 重み付き決定的割当 | PR レビュー |
| `scripts/pytest_shards.py` | 重みの検証と全件被覆検査の強化 | PR レビュー |
| `tests/test_ci_wiring.py` | 配線契約の 8 分割追随 | 凍結資産（主担当が再導出） |
| `scripts/pytest_shard_plan.py` | 割当計算の単一実装（新規） | PR レビュー |
| `tests/test_pytest_shards.py` | 割当・新規テスト・拒否条件の単体検査（新規） | PR レビュー |

## 4. 実装方針

- 重さ分類: **通常**。コア領域（同期・状況計算・記録権・テナント分離・移行）の
  意味は変えない。
- 割当は `ci/pytest-shards.json` の重み（秒）を使う LPT（longest processing time）で
  決定的に行う。重みに無いテストは `default_weight_seconds` で必ず割り当てる。
- 乱数 UUID を含む node id は UUID を `<uuid>` に伏せて重みを引き、収集順を
  タイブレーカーに使う。同一プロセス内で全シャードが同じ全件集合から同じ割当を計算する。
- 被覆検査は分割前の全件収集と各シャードの収集結果を多重集合で比較し、欠落・重複・
  0 件シャード・重み定義の陳腐化を拒否する。
- シャードは従来どおり 1 ジョブ 1 PostgreSQL service とし、DB を共有しない。

## 5. 実装ステップ

| # | 内容 | 合格条件 |
| --- | --- | --- |
| 1 | 8 分割の CI 配線と、実行時間重み付きの決定的割当を実装する | CI の matrix と `ci/pytest-shards.json` が 8 で一致し、重み付き割当が全件を各 1 回だけ返す |
| 2 | 全件被覆・新規テスト取りこぼし・重み陳腐化・集約拒否・カバレッジ維持の検査を追加して実行する | `pytest_shards.py verify` が harness / backend で成功し、追加テストと配線テストが成功する |
| 3 | 変更前後の構成、短縮見込み、未検証点、主担当が必要な正式追随を記録する | `docs/features/ci-pytest-throughput/report.md` に実測値と推定値が区別して記録される |

## 6. テスト計画

- `tests/test_pytest_shards.py`: 重み付き割当の全件 1 回性、新規テストの既定重み、
  重いテストの分散、UUID 正規化、重みの不正値拒否。
- `tests/test_ci_wiring.py`: matrix 数・pytest コマンド・集約ゲート・カバレッジ
  artifact の 8 分割追随。
- `scripts/pytest_shards.py verify --suite harness` /
  `--suite backend --require-db`: 実収集 ID による全件被覆。
- `uv run ruff check .` / `uv run ty check` / 対象 pytest。

## 7. 完了条件（DoD）

- [ ] backend / harness の matrix と設定が 8 分割で一致する。
- [ ] 全テストが分割後もちょうど 1 回ずつ実行され、新規テストも取りこぼさない。
- [ ] 必須チェック名 `backend` / `harness` が維持され、集約が success 以外を拒否する。
- [ ] シャードごとに独立した PostgreSQL service があり、カバレッジ計測が維持される。
- [ ] 変更前後の構成・短縮見込み・未検証点が記録される。

## 8. 未了

- 8 分割の実 CI 所要時間は未実測（PR を作成しないため）。実測できるまでは推定と明記する。
- `tests/test_ci_wiring.py` の変更に伴う凍結資産（受理 record・hash・snapshot）の
  再導出は主担当が直列で行う。


## 非作者レビュー反映と正式接合（2026-11-07、PO委任Codex/root判断）

原候補1a0dea42f149b8a76bff9cd868bd66f16a620511は不変更で保全し、専用WT/枝feature/ci-pytest-throughput-integrationでrootを唯一writerとしてstep2/3追補を進める。非作者レビューで、backendの分割入力4pathだけを変更したPRがbackend-changesで選ばれず検査をskipできるP1を受領・採用。設定JSON/割当helper/plugin/検証CLIの4実入力を既paths-filterに追加、各1欠落の対向を既CI配線検査へ追加する。集約/DB分離/検査範囲/coverage/required名/edited分離は変更しない。候補のsource採用と正式受理/実8分割CIは別であり、変更前環境4分割golden由来の既1failを成功へ読み替えない。

主担当の後続正式追随は既報のenvironment-expectations、正本10.1/github-setup、frozen external/corpus/7.7へ限定して同枝で整合する。#197の通常統合と最終source固定後、実baseから完全値を公式導出し非作者確認/PO委任受理/最終HEAD証拠/全CIを行う。未統合候補の推定22～26分を実績へ読み替えず、実CIのqueue/16job同時実行効果も測定する。原作者が人間承認したとは記録しない。

正式追随の編集宣言（PO委任Codex/root、実装追随）: backend/tests/db/environment-expectations.jsonのsingle_command/provenanceだけ8分割へ揃え、source_revisionは実CI配線を供給する固定a3c08753全長へ束縛する。DB image/initdb/DSN必須/marker禁止/期待比較方式は不変。正本はdocs/development/dev-harness-design-2026-08-07.mdの10.1現行配線・変更履歴とdocs/development/github-setup.mdの現行分割記述・変更履歴、docs/README.mdの両索引日付/注記へ追随（7.6-3、版不変/PRレビュー）。既過去4分割の履歴は改変しない。これは正式7.7受理前の候補編集で、完全値と新PR番号/実baseを確定後に公式導出/非作者確認を行う。独立P2の入力順説明は正規化一意の場合へ限定し、衝突群は同収集順前提を明記、割当コード自体は変更しない。

新6path限定レビューのP2を採用し、10.1現行行に残るTSK-501のci.yml不変/触れない注記を当時の実装へ限定した。現在の8分割は7.7受理/corpus再導出を伴う追随と明示、過去変更履歴の本文・拒否条件・版番号は不変。

### 分割実行入力の検査経路登録（2026-11-07、PO委任Codex/root判断）

非作者分類REPORT-guard-scope.md（a741a26009df9ef0cad2f471dfef9cee1a548d075673c66be1b73f3bcb1c0d88）で実matcherが分割5入力を検出しないことを確認した。新しい意味コアを増やすのではなく、.claude/core-areas.json.guard_pathsへ設定JSON/唯一割当helper/plugin/verifyCLI/専用試験のexact5件を追加する。全既guard/areas/拒否を保持し、実matcherの各単独変更検出を対向へ固定。既197の歴史比較は旧基線を変更せず閉CI5拡張を別検証して逆射影し、欠落/余剰/重複/順序変更を拒否する。これはtest-only歴史オラクルの資格分離で、実core-guardから検出を除外しない。追加編集範囲は同JSON・tests/test_core_guard.py・本plan、source固定後に限定非作者確認/正式7.7/最終HEAD evidenceと全CIを行う。旧レビュー回数は保持する。

### 検査定義先行と歴史資格の分離（2026-11-07、PO委任Codex/root判断）

c8e32af6350fafa8235e2ec917fc9538c6998aa5は旧integration枝に未pushの保全候補として残す。同commitのJSON/基線試験共変更は既拒否対象のため正式採用せず、9b4f176eから本枝で試験/計画を先行commitし、次commitで宣言JSONだけを追加する。runtime有限例外は拡張しない。全件で見つかった2歴史試験は、閉CI5を検査した射影とtyped固定PR197原本のshadow実行へ限定して改訂し、現在のexact5/旧13検査経路の実matcher検査を維持する。旧979pass/2failと限定11成功を別記し、是正後の全件結果/限定独立レビューを追記する。正式PRは197通常merge後のbaseで旧PRの共変更を再承認しない。

是正固定4fb99cc15163560000fb264526ffe667e92cee69（9b4比3path diffSHA88261f3b61920a01f93e36fd3b5dd0ee94309af711a1016883b34b53981d7a5e）はroot全関連1122passed51.40秒/Ruff/Ty成功、非作者REPORT-guard-finalization.md SHA d4002bd25438afb2bfdfc7a2df682bd952c1b1ab19b9a5ce98f5780e972105ad・独立25passed30.37秒/新P0P1P2なしを根拠にPO委任Codex/rootが限定source採用（2026-11-07）。旧限定11/全979pass2failおよびc8保全は履歴保持。runtime全byte不変・既共変更拒否とguard検出維持を実Gitで確認済み。正式197merge後base/完全値7.7受理/corpus/PR最終証拠/全CIと実8分割所要計測は未成立で、本人署名/新blind/全MVP完成ではない。

## 正式PR198の固定と受理ゲート（2026-11-07、PO委任Codex/root判断）

PR197は45b74ac9320c43138a49215529c60bb685a8a977へ通常統合済み、source意味不変の同baseを7ea117d5で取込。PR198を実装済み候補97aでDraft作成し番号を確定、未受理の初回queued CI42330892555/body42330892629はcancel要求し完成証拠へ数えない。最終sourceを固定→公式helperによる全前後値候補→独立比較→PO委任受理→必要snapshot/生成module/corpusを公式導出→最終HEAD委任証拠を本文へ先に登録→通常push1回→実8分割全CIの順で閉じる。検査・必須contextを緩めない。

限定委任policyのtargetsにPR198/本枝だけを追加し、既対象/期限/拒否/本人署名を代記しない属性は維持する。今回のsource/code/domain契約は変えず、実外部freeze入力の移動だけを正式7.7へ一度受理する。意味のないdevelop追随で同じ受理を反復しない。

最終局所検査1127成功/2不合格は、歴史shadow参照のPR197最終SHAをtestへ直接置いたことによる凍結外出し検査の正当な拒否。検査/allowlistを緩めず、同0deb実値を既frozen-inputsのtyped行へ移し、型/源/祖先・旧有限例外の検査は保持する。旧反映1のinventory参照seal漏れ、反映2のこの掃引不足はcache保全し未push/未統合。sourceを再固定し、同正式45bから単一PR198の完全値を導出し直して限定非作者確認/CLI/局所全検査後に受理する。旧報告/周回は保持。
