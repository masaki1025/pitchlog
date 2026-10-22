# ステップ7の追加9パス・範囲判断票（未承認）

## 固定対象と状態の読み方

本票は[固定追補v3](step7-scope-extension-v3.md)の判断補助であり、承認原本や旧提案を書き換えない。v3 SHA-256は `1002b6ca303948aed454ed0207b2bbcdabd9e466475657f86e1b6a6ae8730da7`。対象の歴史的前基線は `161ab6182577e8d4875406d5e48f42f9f2c2c130`、候補反映コミットは `473671100ea927168c1fe5434f315dd7e7d8381a`、公開固定HEADは `4e8a1ab2adde6bbf9bc113dd9537996b3fa7249e`（#171）、人間統合は `e648fbe9`。

**9パスともU-F8差分の状態は「公開済み候補」**。各正式パス自体は既存の共有資産で、候補コピー `step7-candidate/before/after/<正式パス>` が#171で統合済みという意味である。正式9パスにU-F8差分が反映された「既統合」ではなく、U-F8未公開候補でもない。他担当が同じ正式パスへ統合した変更とは区別する。#171マージは9パスの範囲承認・7.7受理を兼ねない。

[9パスだけの固定差分](step7-nine-paths-published.patch) SHA-256 `b666700c7a1ad4ea152e35a41425fb281a992f80afed87f8ea0a0b102c5a73ee` は、#171公開済み完全patchから該当9ブロックを順序どおり抜いたもの。新候補値の生成ではない。元の完全13パスpatch SHA-256は `5a012348e3a08b47513804f3a6740094182a025065dbb285c37fa0af12d8306b`。[当時の全前後値](step7-scope-extension-v3.md#現基線・完全前後値)と[公開固定候補](https://github.com/masaki1025/pitchlog/tree/4e8a1ab2adde6bbf9bc113dd9537996b3fa7249e/docs/features/uf8-full-game-followup/step7-candidate)を参照する。**これらは将来の受理に使う現基線値ではない。**

## 9パスの目的・差分・影響・担当

全行に共通する既承認との差は、承認計画3節に列挙されたCI/base-allowlist/census/history-snapshots/manifestを超える正式パスであること。CI検査段の外部入力追随で波及するため追加を提案するが、現在はfeature内コピーまでで、実適用権限はない。編集担当欄はU-F8の予定責任で、他担当の編集所有解除/受理の記録ではない。

| 正式パス | 目的・公開候補の実変更 | 既承認範囲との差 | 検査への影響・保持条件 | 実編集担当・順序 | U-F8差分の状態 |
| --- | --- | --- | --- | --- | --- |
| `contracts/tenant_boundary/cache-invalidation-contract.json` | CI外部入力の変更に伴うrevision/identity/source_digestと履歴追随。失効動作の新作なし | 未列挙のcache契約 | cache契約の入力/派生digestを一致させる。既存失効ルール・拒否試験・受理履歴は保持 | #174→#173後、U-F8が候補生成。正式反映は範囲承認/7.7後 | 公開済み候補 |
| `contracts/tenant_boundary/db-api-inventory.json` | inventory_revision/identityと履歴追随。SQL関数や許可行の追加なし | 未列挙のDB API目録 | 実目録との対応・snapshot保持を照合。検査対象を削らない | 同上 | 公開済み候補 |
| `contracts/tenant_boundary/negative-fixtures.json` | fixture_set_revision/identityと履歴追随。負例本文の変更なし | 未列挙の負例契約 | 既存負例/失敗条件を全保持。基準版だけ変えて未実施を合格にしない | 同上 | 公開済み候補 |
| `contracts/tenant_boundary/repository-contract.json` | revision/identity/source_digestと履歴追随。登録operation/SQL許可追加なし | 未列挙のrepository契約 | 派生Pythonとのsource digest/版一致。登録済み境界と拒否能力保持 | 同上 | 公開済み候補 |
| `contracts/tenant_boundary/runtime-authz-contract.json` | runtime revision/identity/source_digestと履歴追随。CAP/route/rule変更なし | 未列挙の実行時認可契約 | 生成定数と入力一致。認可・tenant拒否の実検査を維持 | 同上 | 公開済み候補 |
| `contracts/tenant_boundary/tenant-context-allowlist.json` | revision/identity/source_digestと履歴追随。bind/SQL許可変更なし | 未列挙のtenant文脈契約 | 文脈検査と派生Python一致。越境負例の除外禁止 | 同上 | 公開済み候補 |
| `backend/src/pitchlog/authz/runtime_contract.py` | 上記runtime契約から生成するrevisionとSOURCE_DIGESTの定数2箇所だけ | 計画のbackend製品差分なしを超える生成物 | generatorの再生成一致・runtime契約整合・既存認可試験。計算/認可動作の手書き追加なし | 同順序でU-F8が既存生成器を使用。手編集しない | 公開済み候補 |
| `backend/src/pitchlog/repositories/repository_contract.py` | repository契約のrevisionとSOURCE_DIGEST定数だけ | 未列挙のbackend生成物 | 再生成一致・repository整合・既存境界試験。新SQL/Portを足さない | 同上 | 公開済み候補 |
| `backend/src/pitchlog/repositories/tenant_context_contract.py` | tenant文脈契約のrevisionとSOURCE_DIGEST定数だけ | 未列挙のbackend生成物 | 再生成一致・tenant文脈契約整合・既存越境試験 | 同上 | 公開済み候補 |

6 JSONの当時の差分は、履歴追記を除けば表記したrevision/identityと4件のsource_digestだけである。3 Pythonも版/source digest定数のみ。現#174/#173が加える実登録/動作の差分をこの表へ紛れ込ませない。将来の再導出が表を超えたら自動適用せず、差分を再提示する。

## レビュー結果・検査証拠と未実施範囲

[既存査読結果の固定対象・原結果hash・抜粋](step7-review-evidence-2026-10-22.md)を添付する。

- 原計画査読3回/13件全採用/最終P0限定・最終反映未再査読を保持する。範囲票の新設で回数をリセットしない。
- 6〜7実装のClaude一次は39fadbba対象1回、P1=3/P2=8の11件全採用。敵対基本第1回は2fc46ddc→1194ab6eの60ファイル、P0/P1/P2=0だが当時E2E未成功で通過保留。第2回は1194ab6e→b5dd4972と影響、P0/P1/P2=0・技術査読通過。レビュー者の実DB/実テスト実施はなし。基本2枠消費、P0例外/追加枠は未取得。
- 上記レビューは当該固定範囲だけ。**v3/47367110の再生成値・固定履歴fingerprint試験・文書、本判断票と9パス抜粋は独立未再レビュー**。本票の主担当機械照合を独立査読へ数えない。正式値再固定後に追加の独立査読が必要な場合は追加枠の明示判断を得る。未実施の可決を記入しない。
- #171公開候補を隔離Gitへ通常applyし、完全13 after SHA、新9snapshot、旧24履歴/180snapshotのprefix/署名・bytes保持、corpus/archive検査、backend生成整合84件成功を実測済み。#171最終CIはharness29419成功2skip/frontend1793成功。これらは当時の固定HEADの証拠であり、#174/#173後の新値の検査済み証拠ではない。
- 機械照合の出所・全値・採否は[既存作業ログ](../../worklog/2026-10-20-uf8-full-game-followup.md)と[#171最終確認](https://github.com/masaki1025/pitchlog/pull/171#issuecomment-6318413005)。人間逐行確認・担当受理・署名は代記しない。

## 求める判断

- **A（推奨）**: 上表9パスの限定追随範囲を承認する。実反映は#174→#173の実統合後に基線・候補と全前後値を固定し、別途7.7本人受理・必要レビューを満たした後だけ。範囲承認を実値受理に流用しない。
- **B**: 範囲を保留し、ブラウザ検査の正式CI接続も保留する。独立UIの統合事実は保持する。

今は9パスの範囲判断を求める段階であり、新値受理や旧値の再受理を求めていない。通常ナビ/新機能/iPhone実装の追加承認をこの9パスへ抱き合わせない。
