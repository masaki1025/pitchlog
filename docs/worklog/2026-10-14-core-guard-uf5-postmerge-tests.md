# U-F5統合後 core-guard 試験前提修正（2026-10-14）

## 調査

- PR #127統合点`b81ae1ac`を最新`origin/develop`として専用worktreeを作成した。
- `tests/test_core_guard.py`全体を再現実行し、239件成功・3件失敗を確認した。
- 原因はU-F5登録が比較元へ吸収済みなのに、3試験がU-F8固定末尾またはU-F5未登録を期待することだった。
- U-F5はtenant-isolation/data-migration、U-F8は5領域、U-F6はAPIに対応する既存領域へ登録済みである。
- `.claude/core-areas.json`と`scripts/core_guard.py`の動作変更は不要と判断した。

## 計画

固定末尾を延長する修正は行わない。登録時に必要な追加層内部順と、吸収後も保持すべき領域・一意性・連続ブロック・履歴の相対順を検査する。隔離履歴で未登録→宣言→登録を検査し、U-F5後続パスを足した合成状態でも過去登録の検査が成立することを確認する。検出・人間逐行確認拒否・不正変更拒否は弱めない。

計画承認前は製品・試験コードを変更しない。

## 計画レビュー採否

第1周は P0 0 / P1 3 / P2 1で否決。全件採用した。

- P1: 失敗3件以外に固定件数を持つ補助関数と登録試験も対象へ加え、宣言済み後続登録の受理と旧基線への未宣言追加拒否を分離した。
- P1: 固定末尾を外してもRLS・ADR-001・U-M1・U-F2と追跡ファイル一致を保持する条件を加えた。
- P1: U-F6の2パターンについて対象領域・対象外領域・一意性を定め、sync-protocol、recording-rights、tenant-isolation、data-migrationの相対順を明記した。
- P2: 影響確認した正本をパスで示し、機械突合が読む「反映なし」に揃えた。

第2周は第1周の反映差分と影響節を対象に実施し、可決 P0 0 / P1 0 / P2 0。実装計画は人間承認待ち。

## 実装承認と着手基点

- 利用者は2026-10-14に計画コミット`30a1b2de`とステップ1を承認した。
- 着手直前に`git fetch origin`を実行し、`origin/develop`は引き続きPR #127統合点`b81ae1ac`であることを確認した。計画基点以後の差分は0件で、前提への影響はない。

## ステップ1実装・検証

- `tests/test_core_guard.py`だけを変更した。登録パスを固定末尾・固定件数で判定せず、一意な宣言順の連続ブロックとして検査する`assert_registered_block`を追加した。
- 実設定ではU-F6の`client*`をsync-protocol/recording-rights、`api/*`をtenant-isolationだけに一意に保持し、U-F8を5領域、U-F5をtenant-isolation/data-migrationだけに保持することを確認する。RLS・ADR-001・U-M1・U-F2からU-F6・U-F8・U-F5までの相対順と追跡ファイル一致も維持する。
- 隔離Git履歴を未登録→宣言のみ→U-F5登録→宣言済み後続登録まで進め、U-F5が末尾でなくなっても登録ブロックが残ることを確認した。同じ後続追加を旧U-F5宣言で評価すると拒否され、未宣言追加拒否が維持される。
- U-F5/U-F8変更の人間逐行確認未記入拒否を含む対象15件は15件成功。`tests/test_core_guard.py`全体は242件成功。
- root Ruff、共有Python環境を明示したty、docs-status、plan-doc同期、`git diff --check`は成功。最初のtyは共有バイナリがworktreeの仮想環境を自動検出せず108件のimportエラーとなり、`--python /home/ymdms/projects/pitchlog/.venv`で正規環境を指定した再実行は成功した。
- `.claude/core-areas.json`と`scripts/core_guard.py`の差分は0行。試験削除・skip・検出条件・必須チェック文言の変更はない。
