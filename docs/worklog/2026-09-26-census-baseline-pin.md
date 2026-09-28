---
date: 2026-09-26
topic: マージすると必ず赤になるテストを直す — センサス差分の比較元の固定
branch: fix/census-baseline-pin
---

# 作業ログ: 2026-09-26 センサス差分の比較元の固定(TSK 新規)

## やったこと

### 着手(/task-start)

ブランチ `fix/census-baseline-pin` / worktree `../pitchlog-worktrees/fix-census-baseline-pin`
(起点 `origin/develop` = `1a404101`)。

**重さ分類 = コア領域(テナント分離)。** 機械で判定した — `.claude/core-areas.json` の
「テナント分離」領域の **`paths`** に `tests/test_check_tenant_boundary_bypass.py` が
そのまま列挙されている(glob ではなく完全一致)。したがって **sol xhigh・敵対レビュー +
人間の逐行確認が必須**になる。

Notion タスクは 着手可 → 進行中。

## 事象(着手時の実測)

**`develop` の CI が赤。** TSK-440(PR #80)のマージ直後から。

```
run 36227732876  2026-09-26T07:45:09Z  failure   ← 440 のマージ直後
run 36210079997  2026-09-26T01:56:29Z  success
```

失敗ジョブは **`harness` 1 つだけ**で、他 9 ジョブ(backend / frontend / secrets /
docs-lint / core-guard / tenant-boundary-bypass / nfr021-append-only /
backend-changes / frontend-changes)は success。

`origin/develop` で単体実行しても再現する。

```
tests/test_check_tenant_boundary_bypass.py::test_checker_census_matches_merge_base
E   assert frozenset()
1 failed, 292 passed in 80.19s
```

## 原因

`test_checker_census_matches_merge_base` が **可変参照 `origin/develop` を比較元に
している**。

```python
merge_base = _resolve_merge_base("origin/develop", "HEAD")
baseline_checker = _load_checker_from_revision(merge_base, ...)
added, removed = _compare_checker_census(baseline_checker, checker, ...)
assert added
```

440 のブランチ上では `merge_base` が「440 前の develop」だったのでセンサス差分が出ていた。
**マージ後は `merge_base(origin/develop, HEAD)` が develop 自身**になり、比較元と HEAD が
同一物になる。**差分は必ず空**なので `assert added` が必ず落ちる。

**develop 上でも、develop を取り込んだ全ブランチでも落ちる。** `harness` は必須チェック
なので、**取り込んだ時点でマージできなくなる**。

## 出所と裏取り

**448master セッションからの報告**(2026-09-26)。本セッションは 440 の作成者であり、
**原典で裏を取ったうえで自分の欠陥だと確認した**(上記の実測はすべて本セッションが独立に取得)。

**440 側は敵対レビュー 7 周・前版比較コーパス 712 ケース・4 機構の変異試験を通したが、
本件は検出されなかった。自ブランチ上ではテストが正しく緑になるためである。**

TSK-448 は **同型を敵対レビュー 2 周目で事前に指摘され**、比較元を固定 SHA へ変えていた。
**片方は事前に止まり、片方はマージ後に発現した。**

## 決定

### 是正方針(人間の裁定 2026-09-26)

**比較元を 440 の分岐点 `b4ae7394` へ literal で固定する。**

**採らなかった案**: `assert added` / `assert removed` を落として「差分があるなら
TB002・TB007 に収まる」だけにする案。**マージ後はこのテストが何も主張しなくなり、
空振りを合格と読む形**になるため。TSK-235 が台帳へ出した「スキップは空振りと同じで
当該ステップの存在理由を失う」と同型になる。

**受け入れる代償**: 将来 TB002・TB007 以外で検査器を動かすとこのテストが赤になり、
固定 SHA と期待コード集合の更新が要る。**凍結基準と同じ規律**として受け入れる。
この手続をテストの docstring へ書く。

### 作業場所(人間の裁定 2026-09-26)

**専用の fix タスクとして切る。** TSK-235 へ折り込むと、develop が緑に戻るのが
235 の残り 9 件・凍結基準の受理・force-push・逐行確認をすべて終えたあとになり、
448・236・442・444 をその間待たせるため。235 の計画外の変更にもなる。

### 台帳候補の所在(重複回避の合意)

**TSK-448 の `/pr` クローズ処理で提出する。** 本タスクからは出さない。
要点は「**自ブランチでのみ成立する主張をテストに書くと、マージした瞬間に必ず赤になる**」で、
機構上の原因は**可変参照を比較元にしたこと**。事例として 440(マージ後に発現)と
448(敵対レビューで事前に検出)の対比を渡した。

## 未決・次の一歩

- `/plan` で実装計画書を書く(コア領域なので承認ゲートを通る)
- 触ってはいけないもの: `scripts/check_tenant_boundary_bypass.py` /
  `scripts/frozen_history.py` / `contracts/tenant_boundary/` / `.github/workflows/ci.yml`
  — いずれも tenant_boundary 7 資産の凍結射影の外部対象で、**1 バイト変えると受理記録の
  `after` がずれ、書き直すと `history-snapshots` が孤児として永久に残る**
- 変更はテストファイル 1 つに閉じる見込み。閉じない場合は計画段階で報告する
