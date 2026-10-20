---
feature: tsk550-stage-a-core-registration
status: active
承認: 済（2026-10-19・山田正輝、候補SHA-256 8739118d47a2274371e40bebff44b0bd1ff9b29ec0e9df661ad91613aeaced95）
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3f993b75e687810fa2b0e0b6edc228bc
branch: feature/tsk550-stage-a-core-registration
created: 2026-10-19
計画レビュー周回: 2
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: TSK-550 段階A起動入口のコア領域先行登録

## 1. 背景・目的

TSK-550の段階A resolver候補PR #152では、新規`backend/src/pitchlog/db/stage_a_startup.py`がコア領域の未登録パスとしてroot検査に拒否される。既存TSK-550計画のステップ7・8は後続の`backend/tests/test_rule_resolution.py`専用であり、同じPRで起動入口を先に登録すると、後続ステップ7の追加層と衝突する。2026-10-19のPO方針に従い、本PRで起動入口のパスだけを先行登録し、統合後の基線を#152へ渡す。FR-014の製品機能は#152のまま、TSK-372の不変性是正は別単位のまま維持する。

## 2. スコープ

### やること

- 最新`origin/develop`の`.claude/core-areas.json`、`scripts/core_guard.py`、`tests/test_core_guard.py`を基線とする。
- `backend/src/pitchlog/db/stage_a_startup.py`という**完全パス1件**をtenant-isolationとgame-stateの2領域へ宣言・登録する。対象ファイルが本PRの基線に存在しなくても、後続#152での変更パス検出対象とする。
- 既存のU-R1/RG1等の宣言・登録を保持し、追加層の中間状態と登録後の検出・未記入逐行確認の拒否を試験する。

### やらないこと

- 起動入口やDB関数・migration・認可・規則データ・試合保存などの製品コードを変更しない。
- TSK-550本体計画のステップ7・8、TSK-372のmanifest/ORM/不変性実装、凍結資産の受理履歴を変更しない。
- コア判定を緩和せず、未記入の人間逐行確認を実施済みとして扱わない。

## 3. 影響する正本・資産

| 対象 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/requirements/requirements-pitchlog-2026-07-22.md`、`docs/development/dev-harness-design-2026-08-07.md` | 反映なし。6.3の意味境界を既存のまま適用する | 本計画の6.1敵対レビューと人間承認 |
| `scripts/core_guard.py`、`tests/test_core_guard.py` | tenant-isolation・game-stateへ起動入口1パスの追加層を宣言し、guard試験を追加。既存追加層は保持 | コア領域PRの敵対レビューと人間逐行確認 |
| `.claude/core-areas.json` | 上記2領域へ同一完全パス1件を登録。その他の領域・パスは変更しない | 宣言コミットより後の別コミット、基線・guard検査、コア領域PRの人間逐行確認 |
| 7.7凍結資産・受理履歴 | 変更しない。受理済み#152履歴はこのPRへ移さず、#152が最新基線を取り込んだ際に実値を再導出する | 変更が必要と判明した場合は別差分・正式ゲートへ戻す |

## 4. 実装方針

認可を伴う起動入口と規則snapshotの公開判定に関わるパスのため、6.3のtenant-isolationとgame-stateへ重複帰属させる。コア領域に触れるため重さ分類はコア領域とする。後続#152が本PRを取り込んだ時点で当該パスは比較元の登録済み層となる。#152の既存ステップ7では、**両領域の**`AREA_PATH_ADDITIONS`から統合済み起動入口を外し、`test_rule_resolution.py`の追加パスだけへ回転する。起動入口は両領域のJSON基線に残す。これにより#152の元のステップ7・8の対象・順序を変更せず、試験パスだけを追加できる。

### 実装ステップ（コミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | `scripts/core_guard.py`の2領域へ当該完全パスを`AREA_PATH_ADDITIONS`として宣言し、`tests/test_core_guard.py`に宣言層・基線据置き・未宣言追加拒否・将来パス一致の試験を追加する。既存の複数パス宣言領域に対する一領域内の部分追加拒否も維持確認する | JSONを変更せず、既存宣言の保持を確認。宣言済み・JSON据置きの中間状態が現行guardの二層契約で許容されることを限定試験で確認する。片方の領域だけへの本パス登録を「部分追加」と誤分類しない。件名に`(ステップ 1/2)`を1個だけ含める |
| 2 | `.claude/core-areas.json`のtenant-isolation・game-stateに当該完全パス1件を登録する | ステップ1とは別コミット。比較元の全パスを維持し、head側で将来の起動入口パスが両領域へ一致し、未記入の人間逐行確認を拒否する。rootのruff/ty/pytest・基線/guard関連試験を確認し、件名に`(ステップ 2/2)`を1個だけ含める |

ステップ2まで本PRは製品登録0件の先行パス登録であり、#152のステップ3完了、TSK-372是正、試合作成公開を意味しない。コミット済み差分のレビューと人間逐行確認はPRゲートで行い、マージは人間判断とする。

## 5. DoD

- [ ] 起動入口の完全パス1件がtenant-isolation・game-stateへ登録され、既存の登録・宣言を保持する。
- [ ] 宣言とJSON登録が別コミットで、2ステップの検査結果を記録する。
- [ ] 既存のguard拒否規則と未記入人間逐行確認の拒否を維持する。
- [ ] #152への引き継ぎ事項として、実統合SHAの取り込み、両領域の宣言を試験パスだけへ回転すること、起動入口をJSON基線に保持することをPR本文または作業ログに記録する。元のステップ7・8の対象・順序は変更しない。
- [ ] コア領域PRの敵対レビュー・本人逐行確認・CIを確認し、人間判断でのみマージする。

## 6. テスト計画

- **単体・負例**: `tests/test_core_guard.py`へ2領域の完全パス一致、基線据置き、未宣言追加拒否、未記入逐行確認拒否を追加する。部分追加拒否は既存の複数パス宣言領域の一領域内の一部だけを入れた場合として維持確認し、今回の1パスを片方の領域だけへ入れた場合と混同しない。
- **一致性**: `AREA_PATH_ADDITIONS`とJSONの追加層、既存基線の全パスを照合する。
- **品質ゲート**: rootの`uv run ruff check .`、`uv run ty check`、`uv run pytest tests/`と、PR headに対するcore-guardを確認する。PRで人間チェックが未記入ならcore-guardの拒否を期待し、チェックを代記しない。
