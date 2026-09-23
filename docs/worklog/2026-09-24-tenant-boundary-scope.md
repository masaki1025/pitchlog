---
date: 2026-09-24
topic: 迂回検査 条件 5・条件 2 の射程判定(TSK-440)
branch: fix/tenant-boundary-scope
---

# 作業ログ: 2026-09-24 迂回検査 条件 5・条件 2 の射程判定(TSK-440)

## やったこと

- `/task-start` — TSK-440(既存カード・ステータス `着手可`)から着手。
  `fix/tenant-boundary-scope` + worktree を `origin/develop`(`bf8ba5b`)起点で作成
- `/investigate` — 調査サブエージェント 3 本(spec-checker / decision-tracer / 実装構造)+ 自分の実測
  → [research.md](../features/tenant-boundary-scope/research.md)

## 決定(調査の結論として計画へ渡すもの)

- **条件 5 と条件 2 は別の問題として扱う。** 条件 2 はこの検査器の脅威モデルのどの項目にも対応せず、
  由来は上流分割計画の「面を混ぜない」規律(`product-impl-unit-split/plan.md:270` `:258`)
- **除外の単位をモジュールにしない。** 到達可能性は母集団の導出根拠には使えるが、
  モジュール除外の形にすると U-T1 が P0 で否決した「パスで丸ごと除外」と同じになる
  (`tenant-boundary-enforcement/design.md:463` `:470-471`)
- **他タブと合意した資産の境界**: 導出規則を資産に置くのは可 / **導出結果を資産に置くのは不可**。
  除外集合は検査の実行時に毎回導出する

## 未決・次の一歩

- `/plan` で計画書。**射程を絞るときは、絞った結果として落ちてはいけないものを同時に名指しする**
  (`worklog/2026-09-17-tenant-boundary-enforcement.md:240-247`)
- **既存の未承認履歴 7 件**(`contracts/tenant_boundary/*.json` 各 `:61-64`)の扱いは人間の判断が要る
