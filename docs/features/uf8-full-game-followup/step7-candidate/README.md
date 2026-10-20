# ステップ7: CI・凍結資産の未受理候補

このディレクトリは正式7.7受理前の**候補**である。実`.github/workflows/ci.yml`、実`contracts/tenant_boundary/`、実比較corpus manifest、backend製品モジュールには適用していない。計画承認を実値受理へ流用しない。`accepted_by`、`accepted_date`、`accepted_on`、`signature`、追記履歴の`acceptance_id`、`approved_by`、`approved_on`は空欄。旧23履歴・旧署名はbefore/after共通prefixで不変であり、追記へ転記していない。旧候補はGitの`b303eae226881942804f611e1a8ef820bc0a2c6d`に保全されている。

## 出所と完全影響

`metadata.json`の`source_git_base`は現在のGitで得たmerge-base `7c1afebab31facc71e8cfc2731da1a9fa392de4e`、`candidate_checkout_head`は`b303eae226881942804f611e1a8ef820bc0a2c6d`。全正式入力のbefore bytesをそのHEADとbaseのblobへ照合し、dirtyなら生成を拒否する。Draft 6〜7の同一PR番号、正式受理直前・直後SHAは未割当である。

- 宣言済み: CI、`base-allowlist.json`、`census-baseline.json`、history snapshot、比較corpus manifest。
- 凍結逆依存: CIは8資産の`frozen_projection.external_files`に入る。未宣言の6資産は`cache-invalidation-contract.json`、`db-api-inventory.json`、`negative-fixtures.json`、`repository-contract.json`、`runtime-authz-contract.json`、`tenant-context-allowlist.json`。
- 生成コード逆依存: `.env.example`を含む2,277個の非secret・非legacy tracked fileを機械走査し、固定`SOURCE_ASSET`・`SOURCE_DIGEST`・revisionを持つ`backend/src/pitchlog/authz/runtime_contract.py`、`backend/src/pitchlog/repositories/repository_contract.py`、`backend/src/pitchlog/repositories/tenant_context_contract.py`を追加で検出した。これらも**before/afterの完全bytesとpatchだけ**で、実製品は0差分。追加9対象を含む具体追補と質問は主担当が別途提示する。旧`step7-scope-extension.md`は不完全・未承認のまま固定し、本候補の承認根拠へ数えない。
- `frozen-inputs.json`は9資産集合に残るがCIを外部凍結対象に含まず、識別子`contract_revision:4`は不変。

`metadata.json`には宣言場所、前後識別子、射影digest、全外部hash、before blob ID、全13前後ファイルhash、資産path・固定digestの逆参照先、旧履歴・snapshot件数、corpus digestを置く。`before/`と`after/`はCI、影響8資産、manifest、生成済み3モジュールの完全bytesを保存する。`candidate.patch`はこれら13ファイルの差分と新規snapshot9件を含み、`new-snapshots/`の各ファイル名は内容SHA-256である。

| 対象 | before | after候補 |
| --- | --- | --- |
| CI SHA-256 | `f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8` | `1a2082bc3abfcb9f3396abbb282762c0e2203b1f9621d9621a9dd4fb3d5d154d` |
| base / census識別子 | `contract_revision:33` / `contract_revision:14` | `contract_revision:34` / `contract_revision:15` |
| 履歴・snapshot | 23件・179件 | 旧prefix23件+未受理1件・旧179件+新9件 |
| corpus入力digest | `b3accebe79a37392e96be2053fbd83b4b4471e204d4aee67d20094b9525e03ce` | `1356037ce602f4004007b8cfd4177a4bbd809d9ecf0d3f7df0885304fdd7177f` |
| 完全patch SHA-256 | 旧候補`4d0f254c91d124a553a3416cdf95c1a6cd994eb81ce67b0b80d26319f37953fc` | `b39c5a6970b2fb8411b3ae0296cc17833d5d262090408a83fc56e2b1ce2ededf` |

## 再生成と検証

リポジトリルートで次を実行する。生成器は自分の一時stagingで構成し、既存出力がGit保全値またはhash検証済みの前回未受理出力である場合だけ置き換える。新旧snapshotの混入を拒否し、同一入力で`--check`を再実行しても全bytesは同じである。

```sh
PYTHONPATH=backend/src:scripts:tests/fixtures/frozen-archive-cases backend/.venv/bin/python docs/features/uf8-full-game-followup/step7-candidate/generate.py
PYTHONPATH=backend/src:scripts:tests/fixtures/frozen-archive-cases backend/.venv/bin/python docs/features/uf8-full-game-followup/step7-candidate/generate.py --check
```

`--check`は現在の正式入力のGit出所と候補全bytesを照合し、隔離copyへpatchを実適用して全after bytes・新snapshotと比較する。常設`GameScreenCandidate.spec.ts`は実ツリーの可変CI/資産/manifestや新snapshot不存在を前提にせず、候補内部の固定before/after hash、対象集合、旧履歴prefix、人間欄、patch hashと対象を検査する。正式適用後や無関係なdevelop進行で常設frontend試験を赤にしない。`generate.py`は既存`frozen_history`の射影・movement・snapshot関数、`runner.corpus_input_digest`、`runtime_contract_state.asset_digest`と`render_runtime_contract`を利用する。repository/tenant-contextの配布モジュールは今回変更されるrevisionとcanonical digestの二定数だけを前bytesから置換し、隔離適用後の既存完全一致試験で全生成値を照合する。

既存`validate_snapshot_archive`で前179・後188snapshot、孤児33件は不変、新9件の参照漏れなし。既存`runner.validate_corpus_inputs`は候補afterで成功。隔離Git archiveへpatchを適用した`test_generated_runtime_contract_matches_active_asset`、`test_generated_repository_contract_matches_asset`、`test_generated_allowlist_matches_asset`の3件が成功した。これは空の人間受理欄を通す正式history受理検査ではない。

## CI候補とブラウザの未達

CI候補は既存必須frontend jobに`backend/**`の保守的filter、40分のjob上限、既存backend依存同期、明示Ruff/tyで`GameScreenE2eSupport.py`と`generate.py`を検査する行、固定PostgreSQL imageとChromium、`pnpm run test:browser`を追加する。既存mise/uv pin、frontend必須列、backend起動方式、検査器は維持する。明示Ruff/tyはリポジトリルートから実行して成功した。実CIには適用していない。

封鎖検査は`cd frontend && pnpm run test:browser`、直接経路は`pnpm exec playwright test --config src/screens/GameScreen.playwright.config.ts --project sealed-ui`。実App・実Auth HTTP・HTTPS・専用outer/inner DBを使用し、別`real-game`は正式Port/driver未提供のためdummy SHA/IDでも明示失敗する。`--project`なしの全projectも未達である。使い捨て認証主体・鍵・Cookie・nonce・本文・チーム名をconsoleやDOM snapshotへ出さず、0700/0600の自前一時領域を後始末する。Playwrightが子出力を消しても親の所有markerを維持し、失敗時DOMコピーを限定抑止する。last-run reporterの状態は`/dev/null`へ捨て、teardown後に出力先を再作成させない。

遅延応答試験の手動再確認は`docs/features/auth-login-session-correlation/plan.md`と既存`LoginScreen.vue`・`auth.ts`の相関契約に従う。不確実な応答時は認証情報を再送せず、実UIの「状態を再確認」を押した実session GET 200・tenant一致とteam一覧GET完了を確認してから`/games`へ戻る。通常の遅延成功時も実session GET 200・tenant一致と最終`/games`の封鎖表示が必要で、任意の画面への着地を成功にしない。

主担当の最終安定sourceに対するhost5実測は封鎖5件中**1成功・4失敗**で、並行DB検査中のChromium`net::ERR_NETWORK_CHANGED`が安全probeで確認された。変更途中のhost4は最終証拠へ数えない。全件DB終了後の直列browser再測定は主担当待ちであり、封鎖5件全成功、logout旧Cookie拒否の最終確認、実gamePort、GAP-05、原子性、1試合完遂、正式7.7受理はいずれも未達である。旧計画査読3回13採用と6〜7コードPR/敵対査読の枠は別管理し、6〜7敵対はまだ0回。人間記録・新scope承認を代記しない。
