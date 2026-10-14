# 調査記録: U-F5 統合後の core-guard 試験3件

## 基点と再現

- 基点: `origin/develop` `b81ae1ac`（PR #127統合）
- 専用branch: `fix/core-guard-uf5-postmerge-tests`
- `tests/test_core_guard.py`: 239件成功、3件失敗

失敗対象:

1. `test_product_rls_paths_remain_in_develop_baseline`
2. `test_uf8_game_screen_paths_are_registered_in_all_areas`
3. `test_uf5_team_paths_are_declared_for_tenant_and_migration`

## 原因

3件とも統合前後を兼用する条件が、統合後の比較元を正しく扱えていない。1件目はU-F8までを固定末尾とし、2件目は全領域でU-F8を末尾に固定し、3件目はU-F5が比較元に未登録であることを要求する。

`.claude/core-areas.json`ではU-F6、U-F8、U-F5が必要領域に保持されている。`scripts/core_guard.py`の追加層はU-F5のtenant-isolation・data-migration用3パターンを宣言しており、検査器の失敗ではない。

## 順序契約

追加層検査は候補を `baseline` または `baseline + declared additions` に限定するため、登録時の末尾追記と追加層内部の宣言順は契約である。後続追加を禁止する規則はなく、過去層の恒久的な末尾位置は契約ではない。実設定では一意な連続ブロックと履歴の相対順を確認し、絶対末尾は固定しない。

後続パス耐性は、U-F5登録済みの基線へ別の宣言済み追加層を登録する隔離履歴で確認する。旧基線へ宣言なしでパスを加える操作は検査器が拒否する契約なので、既存の負例として分離する。既存の固定件数を持つ`make_repo_with_actual_core_areas`と`test_area_registration`も後続登録に耐える検査へ改める。

## 変更しないもの

- `.claude/core-areas.json`
- `scripts/core_guard.py`
- 製品コードとCI構成
- U-F5/U-F8の人間逐行確認未記入拒否
- 追加層の部分追加・削除・並べ替え・同時変更拒否
