# ステップ7の限定候補追随・追補v2（未承認）

旧SHA-256 `899abea1cdd8e7e3ea069a65c8b8ff79eaf0fdfe40ce2687ccf2559011200f59` の追加6資産案は、生成済みbackendモジュール3件の波及漏れが判明したため撤回した。旧文書のbytesとGit履歴は保持し、本書が照会を置き換える。

承認原本SHA-256 `935bac90426571acf1c9a66b8d41ff0097e14232421fc5f80ff966e9f5551cf4` の3節「追加波及が判明したらその具体差分をまとめて人間へ計画追補を求め、未宣言ファイルへ広げない」に従う。本書は下記9ファイルの候補追随を計画の対象へ加える提案である。実CI・実基準・実backend製品への適用は行っていない。

## 推奨する範囲

| 追加する正式パス | 候補で行う変更 |
| --- | --- |
| `contracts/tenant_boundary/cache-invalidation-contract.json` | CI外部入力に伴う識別値・射影・追記履歴の限定追随 |
| `contracts/tenant_boundary/db-api-inventory.json` | CI外部入力に伴う識別値・射影・追記履歴の限定追随 |
| `contracts/tenant_boundary/negative-fixtures.json` | CI外部入力に伴う識別値・射影・追記履歴の限定追随 |
| `contracts/tenant_boundary/repository-contract.json` | CI外部入力に伴う識別値・射影・追記履歴の限定追随 |
| `contracts/tenant_boundary/runtime-authz-contract.json` | CI外部入力に伴う識別値・射影・追記履歴の限定追随 |
| `contracts/tenant_boundary/tenant-context-allowlist.json` | CI外部入力に伴う識別値・射影・追記履歴の限定追随 |
| `backend/src/pitchlog/authz/runtime_contract.py` | 既存生成器による版・source_digest等の定数追随。権限や処理を新作しない |
| `backend/src/pitchlog/repositories/repository_contract.py` | 既存生成器による版・source_digest等の定数追随。権限や処理を新作しない |
| `backend/src/pitchlog/repositories/tenant_context_contract.py` | 既存生成器による版・source_digest等の定数追随。権限や処理を新作しない |

base/census/history-snapshots/比較manifestとCIは原計画の宣言を維持する。既存23履歴・179snapshotの内容と署名を保持し、新しい1履歴・9snapshotは未受理候補とする。凍結検査の条件・閾値・対象集合・既存検査器・正式actorを変更しない。

## 完全な候補と検査

候補patch SHA-256: `ad6642d2dd4cdaa37e1e0aeb92f42efadb506a40208e22b9b224911cb877a118`。完全な[前後値・識別子・射影・対象集合・Git出所](step7-candidate/metadata.json)、[適用差分](step7-candidate/candidate.patch)、[生成・検査手順](step7-candidate/README.md)を添付する。before/afterにはCI・8資産・3生成モジュール・manifestの全13ファイルを保存している。差分だけの省略値ではない。

CI SHA-256: `f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8` → `9bafa8ae1cb7b22b2b47301f2ffb8a5b2a7aeebad3f2f4d5faa5dd937dc2bd65`。

corpus入力digest: `b3accebe79a37392e96be2053fbd83b4b4471e204d4aee67d20094b9525e03ce` → `7279ca0247dd41e2b294151daac4361a1ae2a9b8ec364248495748a04bc7977c`。

| ファイル | before SHA-256 | after候補 SHA-256 |
| --- | --- | --- |
| `.github/workflows/ci.yml` | `f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8` | `9bafa8ae1cb7b22b2b47301f2ffb8a5b2a7aeebad3f2f4d5faa5dd937dc2bd65` |
| `backend/src/pitchlog/authz/runtime_contract.py` | `9c12b249f53cacec65c7517d3c2e2666042b04756a3c056851064e437356a155` | `17751948aefc104028828825edf86b80782a824ab12dee56641ae20b902e6a56` |
| `backend/src/pitchlog/repositories/repository_contract.py` | `2b4d53c4f14a6fc8c1afd83ddcccf65d97675a1304a736e59e7e1169f90e98f4` | `4888d7791df9e0763fc08c725159c7608435ddcdf28bd6ac738b93f35a61b733` |
| `backend/src/pitchlog/repositories/tenant_context_contract.py` | `523f763c57119a755b8d633e4834f29c743a4a5bff6482ca287548fb041b7f28` | `335a70402934030b64d63861e47787ec3db3c802720af66bba0f316558b84461` |
| `contracts/tenant_boundary/base-allowlist.json` | `8481bb75c1fac980d5e8b24d89ddf81e2abfaf6c59bcc916d0fe14a667d7f701` | `200286aea0699fb2b656883a88535b396c739ae697b2df9fb0a4074b09932cbe` |
| `contracts/tenant_boundary/cache-invalidation-contract.json` | `414d894910c6ec75e6aa28433a86ed08488204362ff1978ec3a37eac53aeb5ba` | `b9e59a21f2f2e3aa78573abc001df7efb883b90f48b292da0e5baac8bc8eedf6` |
| `contracts/tenant_boundary/census-baseline.json` | `392a6f9a42fa6a6976d3ad5eb94384c534a9984d734d2ef6b2eaef8296948968` | `2e5d6cc40ff8a465e195f0c2b8269b3c214339156123c8960f708692d6548a18` |
| `contracts/tenant_boundary/db-api-inventory.json` | `b103a48b6190e6e18cb45e456c75ec26321571c10fafc5d2c2152011f0bed8d3` | `522b6351474f200da48451edd511ba944c05d5159142b675f9ccec095d76b636` |
| `contracts/tenant_boundary/negative-fixtures.json` | `7abd1b2229377ae2ed65a359c6d6094e971177e5f0000c411cf5afc64d5d78dc` | `1d19b86015f97bedbedcc400abca028ecb09a7a2ef572f1008985acdb7863735` |
| `contracts/tenant_boundary/repository-contract.json` | `331c1a4c15e46196a48f3d758d697d42fe923a854b1a2748294d89b14b596cce` | `a4949f98f1a0ac3cc568233759cf78a2851b4d7643ea8b3a78dcdb58f5c4164b` |
| `contracts/tenant_boundary/runtime-authz-contract.json` | `94405b62eb9d5d79920aa55e158b8aedcc75e83c1126928a63c35afe57fcaf66` | `cf4ff7a8c6416874888a9c914cff164c83b1116b98152b4c9de74dec511508e9` |
| `contracts/tenant_boundary/tenant-context-allowlist.json` | `cf1e3b911e8fb598d3b20779227ad0f8c7d2431cbf251ca2003179284d87ea72` | `2cf76852e68238449f2d1c27a6bcbd64a5d43ed5c40975d6a7133004bf95f879` |
| `tests/fixtures/frozen-archive-cases/manifest.json` | `b3967bb282a813ac67d9a2959dfdae011ce771dac7fffc8c7846496d7e32e10f` | `4194544317988daa7bea513491a4bacbe99b41fda79d0a74c3de84328559e147` |

主担当は通常git apply --check・隔離適用後の全13 after bytes・9snapshot SHA、隔離適用後backend生成整合83件を確認した。候補のコミット後・入口への統合後のgenerate --checkも成功した。CI候補はbackend変更・生成器・root設定変更でも既存必須frontend検査を起動し、Python支援を明示Ruff/ty対象へ加える。現在の実CIへは未適用である。

## この照会が承認しないもの

これは計画の対象パスと候補生成・提示の追随だけである。7.7の実値受理、署名、担当受理、本人逐行確認、CI/基準の正式適用、公開・Draft解除・マージを含まない。accepted_by/date/on/signatureと新履歴のacceptance_id/approved_by/onは空欄のままにする。実PRの単一受理単位と正式前後SHAは未割当であり、正式適用前に完全値を再固定して別の7.7判断へ提示する。

計画査読3回・13件全採用・最終P0限定・最終反映後の未再査読範囲は保持する。本追補を新しい計画敵対レビューで可決したとは記録せず、追加レビュー枠も代記しない。6〜7のコード敵対基本第1回は別枠として実行中である。App.vueの入口追補は別の未承認提案で、本書へ混ぜない。

推奨は追加9ファイルの候補追随を承認し、正式適用は7.7受理まで保留すること。別案は本追補を保留し、実CI/正式基線を維持したまま入口とローカル検査の部分Draft提出まで進めること。どちらでも実Port/計算の仮実装、未提供値の成功扱い、GAP-05・原子性・1試合完遂の成立宣言は行わない。
