---
feature: req-v1-9-nfr021-wsl2
type: research
date: 2026-08-11
---

# 調査メモ: NFR-021 の WSL2 追随と継続検証(GitHub Actions で WSL2 が使えるか)

## 問い

1. 要件書 NFR-021 が WSL2 前提に追随していない箇所はどこか。設計書側の確定済み解釈は何か
2. 設計書 10.1 の `win-setup` ジョブ(「windows-latest で README のセットアップ手順を再現」)は WSL2 前提で成立するか。GitHub Actions のホストランナーで WSL2 は使えるのか

## 結論(要約)

- 追随漏れは**要件書 NFR-021 の 3 点**(要件文「Windows 11で完結」/ 測定方法「Windowsクリーン環境での再現」/ 手順の置き場「README に整備」)。設計書側は既に「**WSL2 を含む Windows 11 上で完結**」「**セットアップ再現手順は onboarding.md が正**」と解釈を確定させており、文言はそこから写せる
- `windows-latest`(現 Windows Server 2025)で **WSL2 は動く**。イメージに WSLv2 2.7.11.0 が含まれる。したがって「windows-latest で WSL2 は使えない」は**誤り**
- ただし GitHub は hosted runner の入れ子仮想化を「**experimental / at your own risk**」= 公式サポート外と明記しており、安定性・性能・互換性を保証しない。**必須の継続検証基盤としては不適切**
- `ubuntu-latest` は非 WSL 固有の Linux 手順の検証には妥当だが、「WSL2 上で完結」の証明にはならない(`/mnt/c` 相互運用・Windows 側 PATH 混入・`wsl.conf`/systemd ライフサイクル・性能差が対象外)
- よって **win-setup のランナー選定は Phase 4 の実装時に決める**のが妥当。本タスクでは設計書 10.1 の win-setup 行を「**ランナー未決・Phase 4 で選定**」へ訂正する — `windows-latest` の固定指定を残したままでは「必須の継続検証基盤として不適切」という本調査の結論と矛盾するため(計画レビュー 1 周目 P1-5)。参照先を `README` → `onboarding.md` に直すのも同時に行う

## 詳細と典拠

### A. 要件書と設計書の食い違い(リポ内)

| 項目 | 要件書(未追随) | 設計書(確定済み) |
| --- | --- | --- |
| 要件文 | `docs/requirements/requirements-pitchlog-2026-07-22.md:689`「開発環境はWindows 11で完結する(PostgreSQLはネイティブ版またはDocker)」 | `docs/development/dev-harness-design-2026-08-07.md:19`(変更履歴 v0.11)「NFR-021 は『WSL2 を含む Windows 11 上で完結』と解釈」 |
| 測定方法 | 同 `:690`「Windowsクリーン環境でのセットアップ再現」 | — |
| 手順の置き場 | 同 `:689`「セットアップ・起動手順をREADMEに整備する」 | 同 `:710`(論点C)「セットアップ再現手順は **onboarding.md が正**」 |

設計書側に残る WSL2 名残(本タスクで是正):

- `dev-harness-design-2026-08-07.md:92`(2.3 継承表)—「開発環境は Windows 11 で完結 … **WSL 判断は論点C**」← 論点C は決着済みなのに未更新
- 同 `:396`(8.3)—「**Windows 11 ネイティブ**(NFR-021)と WSL/CI(Linux)の両方で…論点Cの決着に影響されない」
- 同 `:561`(10.1)— win-setup「windows-latest で **README** のセットアップ手順を再現」
- 同 `:699`(13 章 Phase 4 完了条件)—「クリーン環境で **README** 手順どおりセットアップ成功」

### B. GitHub Actions で WSL2 が使えるか(Web 調査 2026-08-11)

実行: `codex_run.py research`(gpt-5.6-terra・high・read-only + live search)。公式ドキュメント優先・公表日確認を指示。

| 論点 | 結論 | 典拠 |
| --- | --- | --- |
| `windows-latest` で WSL2 | **使える**。`windows-latest` は 2025-09 に Windows Server 2025 へ移行。Windows2025 イメージ(`20260803.218.1`)に `WSLv1: Enabled` / `Default, WSLv2: 2.7.11.0` | [runner-images Windows2025-Readme](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md) / [Changelog 2025-07-31](https://github.blog/changelog/2025-07-31-github-actions-new-apis-and-windows-latest-migration-notice/) |
| 公式サポートの有無 | 入れ子仮想化は「**experimental / at your own risk**」。安定性・性能・互換性の保証なし | [GitHub-hosted runners](https://docs.github.com/en/actions/concepts/runners/github-hosted-runners) |
| VM 内 WSL2 の要件 | nested virtualization が必要(最終更新 2026-07-30) | [WSL FAQ](https://learn.microsoft.com/en-us/windows/wsl/faq) |
| `windows-2022` | イメージ一覧(`20260802.262.1`)は **WSLv1 のみ**記載。WSL2 は列挙なし → 使うなら `windows-2025` に固定し `wsl -l -v` で Version 2 をアサートする | [runner-images Windows2022-Readme](https://github.com/actions/runner-images/blob/main/images/windows/Windows2022-Readme.md) |
| WSL1 での代替 | 使えるが**不十分**。managed VM・完全な Linux カーネル・system call 互換性・systemd がない。検証できるのは apt・シェル・ランタイム・ユーザー空間依存のみ | [WSL1 vs WSL2](https://learn.microsoft.com/en-us/windows/wsl/compare-versions)(最終更新 2024-11-19) |
| `Vampire/setup-wsl@v7` | 既定が **WSL2**(`wsl-version: 1` で WSL1)。作者が windows-2022 / 2025 / latest でテスト。**第三者 Action** で GitHub の保証ではない。distro は同梱されず Action が導入 | [README](https://github.com/Vampire/setup-wsl) / [test.yaml](https://github.com/Vampire/setup-wsl/blob/master/.github/workflows/test.yaml) |
| larger runners | GitHub 管理 VM。入れ子仮想化の正式サポートを示す公式記載は**見つからず = 不明** | [Larger runners](https://docs.github.com/en/actions/concepts/runners/larger-runners) |
| self-hosted | 実機なら通常の WSL2 要件を満たせる。VM なら親側で仮想化拡張を公開する必要 | [WSL FAQ](https://learn.microsoft.com/en-us/windows/wsl/faq) |
| `ubuntu-latest` で代替 | 非 WSL 固有の Linux 手順の検証には妥当・安定。ただし「WSL2 上で完結」の証明にはならない | [WSL2 アーキテクチャ](https://learn.microsoft.com/en-us/windows/wsl/about) |

`ubuntu-latest` で検証対象外になるもの:

- `/mnt/c` の DrvFS・NTFS 権限変換・大小文字・実行権限([file-permissions](https://learn.microsoft.com/en-us/windows/wsl/file-permissions))
- Windows 側コマンド呼出し・`WSLENV`・**Windows 側 PATH の混入と変換**([filesystems](https://learn.microsoft.com/en-us/windows/wsl/filesystems))
  - ※ 本プロジェクトは実際にこれを踏んでいる — Windows 側 pyenv-win のシムが WSL の PATH に紛れて `python` が壊れた(`docs/development/onboarding.md:29` に罠として記録済み)。`ubuntu-latest` だけでは検出できない類の問題である
- `wsl.conf`・起動停止・systemd 有効化と WSL 固有のライフサイクル([systemd](https://learn.microsoft.com/en-us/windows/wsl/systemd)・最終更新 2025-03-17)
- `/mnt/c` 上と Linux FS 上の性能差([filesystems](https://learn.microsoft.com/en-us/windows/wsl/filesystems))

Codex の一行判定: 「`windows-latest` で WSL2 は使えない」は**現行では誤り**。ただし公式サポート外の実験的機能なので、**必須の継続検証基盤としては不適切**。

## 未解決・申し送り

- **win-setup のランナー選定(Phase 4 へ申し送り)**。候補: (a) `ubuntu-latest` を必須の週次検証にし WSL 固有部分は対象外と明記 / (b) `windows-2025` に固定して WSL2 ジョブを置くが非必須(情報収集)扱い・冒頭で `wsl -l -v` をアサート / (c) a + b の併用 / (d) WSL 固有部分は self-hosted runner または手動チェックリストに寄せる。ハーネス設計者の回答が未着
- **要件書の測定方法は CI 方針に依存させない方針で書く**。他 NFR と同様「何を測るか」の粒度(= 「WSL2 クリーン環境でのセットアップ再現」)。ランナー選定は設計書 10.1 の役割
- **採用時点で再確認すべき事項**(Codex 出力を鵜呑みにしない — 設計書 9.2): Windows2025-Readme の WSLv2 記載(イメージ版数は更新され続ける)/ GitHub-hosted runners ドキュメントの「experimental / at your own risk」の原文
