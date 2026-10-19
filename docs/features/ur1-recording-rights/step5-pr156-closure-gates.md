# PR #156 の未受理差分と閉鎖条件（2026-10-19）

比較元は `origin/develop=015dfa9db0b7b8740369911a9cb5195dd59a62ea`、ローカル取込 HEAD は `8a2f332626a57762cab90d6957a56624a5e8e650`。公開中の Draft PR HEAD は `836232d619e0b6b543186eb07b1c204a5af24745`。以下の JSON と ORM シートは**未コミット候補**であり、正式資産承認・7.7 受理・本人逐行確認を表さない。実台帳、端末資格、製品 `RecordingRightsPort` は未提供。

## 正本参照だけの候補

| 資産・フィールド | before | after（候補） | 検証 |
| --- | --- | --- | --- |
| `contracts/authz/shared-preconditions.json` の `source_documents[path=docs/design/data-model.md].git_blob_digest` | `21a85f5e794baaa05376b06aec7185cada6c33c8` | `b1dc01f4f263fb31e1d257b2f1e937dc45a99dc0` | 実 Git blob と一致。`preconditions` 6 行、要求書側参照、抽出規則は不変 |
| `contracts/db/schema-manifest.json` の `canonical_source.sha256` | `a4504bbb2cf3fcbec13ea4fbb0ccd7d8ab2b9b66dafec3fc01f763ed06b16bfc` | `1f25908d029887ddfcbad213cf66ee9fdb1311b7e7cf8a62e47c1396f36dfdc3` | 実ファイル SHA-256 と一致。表・列・制約・権限は不変 |

候補ファイル全体の SHA-256 は順に `3a9eab110571f88f23225bd2e9db386756b4bb38f34ee8bfb83be9e00e46bc6d`、`463cfcce9e80fd259da10095204222a4affca2cdd95d67b652d315955f3d1faf`。両資産には `baseline_control` がなく、`frozen-baselines.json` および tenant-boundary の9資産が凍結する対象にも含まれない。この2値だけの追随に 7.7 記録は不要。正本参照2値は2026-10-19にPOが変更差分を承認し、ORM新規行も同日判定した。

## ORM シートの再生成と人間判定

N1=103、N3=106（+1）、N4=55、N7=101（+1）。既存363行の `(正本側,実装側)` を対応付けて判定・理由の差分が**0**であることを確認した。新規2行は2026-10-19のPO判定に従い「対象外」と理由・典拠を記入した。N7の既存行は出現位置の再採番だけを追随した。`tests/test_orm_acceptance_sheets.py` の行数期待値も新しい実数に追随し、未判定検出は維持した。

| 新規行 | 正本と実装の対応 | 確定判定・理由 |
| --- | --- | --- |
| N3 `出現106: 不変` | data-model §12-8 の「D4非再利用・復旧世代の具体的な発行/保存機構、RG1の安全な解除とI6の永続化写像」の受け取り先行。manifest の `immutability` に該当候補なし | **対象外**。ここでいう不変条件は復元外予約・fence等のプロトコルと実装担当の分界であり、列更新禁止の定義ではない。典拠 `data-model.md:12-8`、`schema-manifest.json` の `immutability` |
| N7 `候補038: 記述語: 保持する` | data-model §6-1 の外部復旧世代行共有fenceを業務DB commit/rollback結果確定まで保持する規則。生成器は近接する `recording_generations` 列契約を候補表示する | **対象外**。行ロックの保持期間と障害時停止の規則で、`recording_generations` の必須列・NULL性・defaultを新たに定めない。典拠 `data-model.md:6-1`、`schema-manifest.json` の `recording_generations.columns` |

2行の人間判定反映後、`test_acceptance_sheet_judgments_are_complete` を含むORMシート試験13件が成功。D4非再利用と外部fence保持は、それぞれ U-R1 新5・新7と U-R1/U-S1 の契約・試験で追跡し、ORM上の「対象外」を検証免除としない。

## TB002 の限定登録候補（正式受理待ち）

現行の47件は本物のD4・復旧世代であり、「誤検知」裁定にも、`owner_paths`へのファイル全体追加にも入れない。候補は`base-allowlist.json`の`condition_2_scoped_findings`に**単一ファイルの実SHA-256と47組の行番号・シンボル**を登録する。検査器はソースSHA・パス・個別行・シンボルがすべて一致するTB002だけを除き、TB001/3/4/5/7と任意DB APIは従来通り判定する。登録済みソースへの変更はSHA不一致で全47件を再拒否する。隣接ファイルと他経路も拒否する。`owner_paths`、`allowed_symbols`、既存adjudicationは不変。これはコード/契約の**未受理ローカル候補**である。

| 拒否理由・必要操作 | 件数 | 検査器が示す行番号 |
| --- | ---: | --- |
| D4/復旧世代の型、Protocol、公開引数・結果 | 14 | 55, 56, 66, 67, 73, 76, 77, 83, 86, 92, 107, 147, 192, 193 |
| D4/復旧世代の正整数検証・暗号AAD直列化 | 10 | 201, 202, 203, 204, 212, 213, 222, 223, 231, 232 |
| 保存済み開始の同一要求再交付・記録値使用 | 7 | 256, 257, 337, 338（2件）, 340, 345 |
| 外部現復旧世代・fence・DB scopeの再照合 | 9 | 269, 271, 282, 283, 285, 299, 352, 353, 392 |
| owner束縛予約、claim一度限り、保存値への接続 | 7 | 356, 359, 368, 370, 376, 385, 397 |

`int`という広い検出語も14件あるため、シンボルだけで汎用許可しない。全47組の完全表は候補JSONにあり、製品ファイルSHA-256は`c20d596ba80a7c9e792a472ddde295a261b0dee2977627e7f0391765bdca59c3`。`initial_grant.py`は既承認の隔離候補で、実台帳やPortの権限を加えない。コアの意味範囲に合わせ、同ファイルを`sync-protocol`、`recording-rights`、`tenant-isolation`の3領域へ1パスずつ追加する候補も含める。基線に旧RG1パスは統合済みなので、guard宣言は今回の1パスだけを新しい追加層とする。宣言→JSON登録のコミット分離は、正式受理後の手順に維持する。

7.7はPR #156の最終HEADを単一受理単位とし、8資産のrevision・射影と新snapshot、archive corpusを最終候補で導出する。`base-allowlist.json`の履歴集約先へ同PRの**単一**未マージ記録を追加する案とし、既存履歴とbeforeを保護する。現候補には受理記録・承認者・日付を入力しない。`frozen-inputs`は今回の検査器を参照しないため不変。未受理期間の凍結検査が赤になることを正常合格とは呼ばない。

[9資産・外部参照を含む受理payload案](step5-pr156-7.7-payload-proposal.json)はbefore/afterを完全に列挙し、承認者・承認日を持たない`受理待ち`の文書である（SHA-256 `34915e053e6804df9c9385f98d8702b7595505a1276b595e65baac0e46e33e3c`）。正式台帳には未入力。

現在の限定候補の射影を実ファイルから計算した結果を下表に置く。**正式7.7の最終値ではない**。`after`は実ファイルと検査器に対して各revisionだけを1増やしたメモリ上の候補で、受理済みの台帳やsnapshotを編集していない。snapshot名はafter射影SHA-256と同値である。独立レビューによるコード変更、PR最終HEADに対する受理記録で変わる場合がある。最終7.7の完全値はその後に再導出する。

| 資産 | revision before→候補after | before射影 | 候補after射影＝snapshot名 |
| --- | --- | --- | --- |
| base-allowlist | 33→34 | `e3dcdd745a721431a5ecdfd0cfa43f9f5839a79678d34e81fa76a3ea15746046` | `7c62db133f0859f581313fac39279bdad6c62d182d33541f250a54eaba42787c` |
| cache-invalidation-contract | 15→16 | `161d2815a06778fbac0bb679b5a5aa1d1295db2e7e0ed971d2b343a654daf32f` | `c6b7450246c54d7b7661ae2c66f7fcf6f891d9fe7488238ac6b2e13385a232e9` |
| census-baseline | 14→15 | `c717da79aee3504ab5176f88cd502ad40170389df7ad1aa60d4fb5c86e5f241f` | `f74d9491dae3daf08f01ed1ea20ac50ca4043c4feb567cc551d71e0c650a1d3e` |
| db-api-inventory | 15→16 | `66ec5e8410adeab61f78bcb4ce72ec4ea55b32588d96e95d172013b2a8658999` | `21a15b0f90a35c2f0ffe42387cd5f7f39dac142c0987bfee9f0dcda37fa11bd7` |
| negative-fixtures | 17→18 | `3513677e5ea3dff4db6471ef2b4ade93c91095ef5a3f43e085a5b8ee59c43d82` | `9b5197e65f12bbdec64e87a4bf09470efffb0e7618efa0ec09e96428d337bc02` |
| repository-contract | 21→22 | `0daf9ec4b9d5dc7eea364a0001804ba187f3bed87e02850f2da5b21613dc0e11` | `586f21e1d5c16f302f1a21eab7d8d8a49fe7438a5a144b1d29c8b3c97e52bd45` |
| runtime-authz-contract | 17→18 | `061eeb9e96f110e059ad51bf3026d9b420f7c636a24045809afa33e7a0f6b393` | `0007c3f333a5d2c95cb7af118731818d49b033814fafcb635bd583e7c280cee3` |
| tenant-context-allowlist | 16→17 | `16e7a9a6a263f00381a327d8f05bce597dd036d67333ebfc55e035f1e8f9e2c2` | `fe056d4b4b96058d5e9d72899f17fca69bcbb19f87d78f9ab32d430631d74129` |

archive corpusの現行正式digestは`b3accebe79a37392e96be2053fbd83b4b4471e204d4aee67d20094b9525e03ce`。8資産を上表のrevisionへ上げた隔離コピーに対し、既存`runner.corpus_input_digest`で算出した候補afterは`1535ff098defae52a7cdd653e54032d9244f118f62c6801f8fc4fc3c1f085085`（手計算と隔離コピーの2方法が一致）。新履歴は`pinned_prefixes.history_record_count=6`より後ろなのでcorpus入力から除外され、承認者・日付の仮記入は不要。検査器の実SHA-256は`3e2cec0a25096b010973f3734c2746bd4386e413ebf44519ad8db0851846b883→3b7b90f8476b30c0596439b33ce75db1c23c6c930b359e03804f00df280e0e7e`。レビュー後の候補が同一なら、この値を正式受理資料へ採用する。

## U-S1への項目別回答と #156 合格条件

U-S1主担当スレッド `01a14f9e-f825-7441-b7e1-1179a938254f` へ直接回答した。分類の対象は U-S1 §13 の**接続契約**と、U-R1候補による**実提供**を分ける。

| 照会項目 | 分類 | 候補照合根拠と残条件 |
| --- | --- | --- |
| 検証済み端末文脈 | **受理（契約）** | U-S1 `design.md` §13 の両公開入口必須引数、U-R1 `step5-connection-fixed-candidate.md` §U-S1 が一致。U-R1 `initial_grant.py` の `lock_valid_device` は内部再照合候補。認証発行と実Port注入は**担当外（#156）**・未提供 |
| 確定不保持/旧世代のFalseと照合不能例外 | **受理（契約）** | U-S1 §13 の B4/B9 対 B7/B10 を採用。実 `RecordingRightsPort` とD5未消費の入口結合証拠は**要修正（後続実接合）** |
| `FunctionWriter` | **受理（契約）** | U-S1 `sync/ports.py` と §13 の `run_function` だけを固定関数へ渡す境界を受理。任意SQL/Session/tenant指定は増やさない。U-R1の実関数登録は**要修正（後続）** |
| 外部fenceの寿命・結果不明時の隔離 | **受理（契約）／要修正（実提供）** | U-S1 `sync/write_fence.py` はscope終了後release、結果不明でquarantineする候補。U-R1 `initial_grant.py` の `RecoveryEpochFence` は `assert_held` のProtocolだけで、耐久相関・隔離解除・権威ある結果照会を実装しない。実台帳耐久性は**担当外（#156）**で、新7等の別ゲート |

耐久照会の提供担当はU-R1の外部台帳adapter/復旧契約、開始要求・attemptの保存点はU-G1/U-R1受理待ち。現 `DurableGenerationSource` の公開署名は `reserve(attempt_id, tenant_id, game_id, start_request_id)`、`claim(...)`、`current_recovery_generation()` のProtocolだけで、保存先は未配置の復元外専用PostgreSQL案、commit不明を解消する権威ある照会署名・永続相関ID・実証は**未提供**。U-S1 `WriteFencePort` のProtocolも製品adapterを提供しない。契約受理と製品Port提供・耐久性合格を区別する。

#156は正本v0.12と新5の**隔離候補**を提出するDraftであり、新5全体の完了や実Port・耐久台帳の合格を主張しない。このPRを閉じる条件は、上の2参照の正式資産判断、TB002の限定認可/凍結契約の承認と7.7最終値の受理、必要な独立レビュー、関連検査/CI、コア領域の人間逐行確認である。Draft解除・マージは人間判断。これらが未成立の間は未受理の資産・履歴・本人確認欄を記入しない。
