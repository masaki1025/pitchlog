---
feature: core-guard-uf5-postmerge-tests
status: active
承認: 済(2026-10-14・利用者、計画コミット30a1b2deとステップ1を承認)
重さ分類: コア領域
worktree: /home/ymdms/projects/pitchlog-worktrees/fix-core-guard-uf5-postmerge-tests
branch: fix/core-guard-uf5-postmerge-tests
created: 2026-10-14
計画レビュー周回: 2
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: U-F5 統合後の core-guard 試験前提修正

## 1. 背景・目的と所有

PR #127 は `b81ae1ac` で `develop` に統合済みである。最新 `origin/develop` で `tests/test_core_guard.py` を実行すると 239 件成功・3 件失敗となった。失敗は、U-F5 の3パターンが tenant-isolation と data-migration に吸収済みであるのに、試験が「U-F5 は未登録」「U-F8 は paths の末尾」という統合前の状態を期待するためである。

本fixは [U-F5（TSK-520）](https://app.notion.com/p/3f493b75e68781ac8f9be34909d424a2) の登録済みコア領域試験と[要件書 NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md)の回帰検査を回復する小規模な試験修正である。`/team` 接続計画は本fix完了まで停止する。U-F5全体、U-F13残部、TSK-520を完了扱いにしない。

## 2. スコープ

変更対象は `tests/test_core_guard.py`、本計画、調査記録、作業ログ、Claude向け引継ぎだけとする。`.claude/core-areas.json`、`scripts/core_guard.py`、製品コード、CI構成は変更しない。試験の削除・skip、人間逐行確認の必須判定、変更検出、不正な追加・削除・並べ替えの拒否を緩和しない。

## 3. 影響する正本

| 正本 | 反映 |
| --- | --- |
| [要件書](../../requirements/requirements-pitchlog-2026-07-22.md) | 反映なし。NFR-019の既存回帰検査を回復する |
| [開発ハーネス設計書](../../development/dev-harness-design-2026-08-07.md) | 反映なし。6.1・6.3の既存ゲートを適用する |

## 4. 契約と実装方針

`validate_area_path_layers` は登録コミット候補を「基線と同一」または「基線の末尾へ宣言済み追加層を宣言順に全件連結」のどちらかに制限する。このため、各追加層の内部順序と登録時の追記順は契約である。一方、後続の追加層が登録されれば過去の層は末尾ではなくなるため、U-F8やU-F5を恒久的な末尾に固定する契約はない。

実developでは次を検証する。

- U-F6の`frontend/src/api/client*`がsync-protocolとrecording-rightsに、`frontend/src/api/*`がtenant-isolationに一度だけ存在し、それぞれの対象外領域には存在しない。
- U-F8の`GameScreen*`が5領域に一度だけ存在する。
- U-F5の3パターンがtenant-isolationとdata-migrationに宣言順の連続ブロックとして一度だけ存在し、他3領域には存在しない。
- 既存のRLS・ADR-001・U-M1・U-F2と追跡ファイル一致を保持し、tenant-isolationではそれらに続くU-F6→U-F8→U-F5、sync-protocolとrecording-rightsではU-F6→U-F8、data-migrationではU-F8→U-F5の相対順を確認する。各登録ブロックは末尾位置に依存しない一意な連続列として検査する。
- `make_repo_with_actual_core_areas`と`test_area_registration`の固定件数・末尾前提も同じ登録ブロック検査へ追随させる。

「未登録→宣言のみ→登録済み」は実developの末尾状態から逆算せず、既存の隔離Git履歴試験で検証する。登録済み基線のU-F5後方へ宣言済みの後続パスを別コミットで登録した履歴でも過去ブロックの保持を検査する。旧基線へ未宣言パスを足す既存の拒否試験は別に維持し、将来追加の受理と未宣言追加の拒否を混同しない。部分追加、削除、同時変更、順序変更の拒否試験も維持する。

### 実装ステップ（コミット単位）

| ステップ | 変更 | 合格条件 |
| --- | --- | --- |
| 1 | `tests/test_core_guard.py` の失敗3件、`make_repo_with_actual_core_areas`、`test_area_registration`を、領域別の登録・一意性・連続ブロック・全履歴順で検証する形へ直す。隔離履歴の三段階、宣言済み後続登録、未宣言追加拒否を別々に明示検証する。計画・worklog・Claude引継ぎへ結果を記録する | 直接失敗3件、`tests/test_core_guard.py`全体、U-F5/U-F6/U-F8と既存RLS・ADR-001・U-M1・U-F2の保持、既存の人間逐行確認拒否・不正変更拒否、root Ruff・ty・文書検査・`git diff --check`が成功する。`scripts/core_guard.py`と`.claude/core-areas.json`の差分が0行 |

## 5. DoD

- 最新developで再現した3件が通り、U-F5・U-F6・U-F8の登録保持を実設定から検査する。
- 固定末尾ではなく、契約上必要な領域・一意性・連続ブロック・履歴順を検査する。
- 隔離履歴で未登録、宣言のみ、登録済みを順に検証する。
- U-F5より後に宣言済みパスが追加された隔離履歴でも登録保持試験が通り、旧基線への未宣言追加は引き続き拒否される。
- 検出と未記入の人間逐行確認拒否を含む既存の負例が通る。
- 独立敵対コードレビューと人間逐行確認をPRで必須とし、利用者の判断までマージしない。

## 6. テスト計画

| 種別 | 検査 |
| --- | --- |
| 直接回帰 | 再現した失敗3件 |
| 実設定 | U-F5・U-F6・U-F8の領域と対象外領域、一意性、連続順、RLS・ADR-001・U-M1・U-F2を含む履歴順、追跡ファイル一致 |
| 隔離履歴 | 未登録→宣言のみ→登録済み、宣言済み後続登録後の過去ブロック保持 |
| 負例 | 部分追加・削除・並べ替え・同時変更拒否、U-F5/U-F8変更の人間逐行確認未記入拒否 |
| 品質ゲート | `tests/test_core_guard.py`全体、root Ruff・ty、docs-status、plan-doc同期、`git diff --check`、PR CI |

## 7. レビューと承認

計画は独立敵対レビュー後に採否と最終差分を記録し、人間承認を得てからステップ1へ進む。実装後はコア領域PRとして反対側レビューと敵対レビューを行い、PR本文に人間逐行確認の「対象・範囲・方法」欄を設ける。未実施のチェックは代記しない。

第1周は P0 0 / P1 3 / P2 1で否決。全件採用し、固定件数を持つ補助関数・登録試験、後続の宣言済み登録と未宣言拒否の分離、既存RLS・ADR-001・U-M1・U-F2の保持、U-F6の領域と全領域の相対順、正本の「反映なし」宣言を追記した。

第2周は第1周の反映差分と影響節を確認し、可決 P0 0 / P1 0 / P2 0。利用者は2026-10-14に計画コミット`30a1b2de`とステップ1を承認した。
