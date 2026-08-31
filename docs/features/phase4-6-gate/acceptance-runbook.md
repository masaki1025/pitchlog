# 受入ランブック(Phase 4-6 — NFR-021 `gate_kind: phase4`)

**実施者 = 要件書 8 章の判定者(PO)。** Claude は操作補助と記録の起草のみ。本書は計画書の**運用手順 B・C** を実行するための手引きで、**規範は `docs/development/onboarding.md`(v1.2 approved)の逐語**である — 本書と食い違ったら onboarding が正。

## 固定済みの値(運用手順 A で確定・変更しない)

| 項目 | 値 |
| --- | --- |
| **`T`**(試験対象コミット) | `3873ce8586a54e273a722540a07896335d7aceb4` |
| `T` を含むブランチ | `feature/phase4-6-gate`(push 済み・remote head = `T`) |
| `short_sha`(証跡ファイル名用) | `3873ce8586a5` |
| `T` の `onboarding.md` blob OID | `43836beff93a5751daf30aaacdd2c050b5d54ac5` |
| 予約(閉じる対象) | `attempt_id: phase4-001-20260819T142916Z` / `attempt_seq: 1` |

## 実行順序

**onboarding の章順に従う。** 受入判定では **2-1 → 2-2** を挟むのが v1.1 / v1.2 の追加点。

| 順 | 章 | 内容 | 備考 |
| --- | --- | --- | --- |
| 1 | **0 章** | **新規 WSL2 ディストリビューションを作る**(`wsl --install -d Ubuntu-26.04`) | **既存ディストリを使い回さない** — 残留状態が手順の欠落を隠すため。既に `Ubuntu-26.04` がある場合は別名で作るか、`wsl --unregister` してから作る(**既存の作業環境を消さないよう注意**) |
| 2 | 1 章 | 基礎パッケージと単体ツール | |
| 3 | 2 章 | リポジトリ取得(clone) | clone 直後は `main` が checkout される |
| 4 | **2-1 節** | **候補コミットの固定** | 下記コマンド。**detached にしない** |
| 5 | **2-2 節** | **アーキテクチャの採取** | 下記ブロック。**不適合なら中断して連絡** |
| 6 | 3〜5 章 | Node・pnpm・Claude Code / Codex / Notion 紐づけ | |
| 7 | 6 章 | ハーネスの動作確認(**項目 3 が合格項目 1**) | 項目 5 は `develop` 上で git_guard が拒否することの確認 |
| 8 | 7 章 | 依存の導入と検証(**7-1 が合格項目 2・3**) | |
| 9 | 8 章 | 開発 DB と起動疎通(**8-2 が合格項目 4・8-3 が合格項目 5**) | |

### 4. 2-1 節 — 候補コミットの固定

```bash
git fetch origin feature/phase4-6-gate
git switch -C develop 3873ce8586a54e273a722540a07896335d7aceb4
git branch --show-current        # develop であること
git rev-parse HEAD               # 3873ce8586a54e273a722540a07896335d7aceb4 と完全一致
```

**ブランチ名を `develop` に保つのは必須。** detached HEAD では `git_guard` が発火せず、**6 章 項目 5(保護ブランチへのコミットが拒否されることの確認)が成立しない**。

### 5. 2-2 節 — アーキテクチャの採取

onboarding 2-2 節のブロックをそのまま実行する。**出力の「証跡セルへ貼る 1 物理行」をそのままコピーして渡してほしい。**

- `適合: arch=<arch>`・**終了コード 0** なら次へ
- **`不適合:` が出たら受入を続行せず、その出力を添えて連絡** → 計画書の**経路 A**(証跡に `failed` を記録して予約を閉じる)へ分岐する

## 合格項目 5 つ(要件書 `:921`)と採取するコマンド

| # | 合格項目 | 章 | コマンド | 記録するもの |
| --- | --- | --- | --- | --- |
| 1 | ハーネスの pytest | 6 章 項目 3 | `uv run pytest tests/` | 終了コード + 件数(例 `652 passed`) |
| 2 | backend の pytest | 7-1 | `(cd backend && uv sync --locked --dev && uv run pytest)` | 終了コード + 件数 |
| 3 | frontend の Vitest | 7-1 | `(cd frontend && pnpm install --frozen-lockfile && pnpm test)` | 終了コード + 件数 |
| 4 | 開発 DB へ接続 | 8-2 | onboarding 8-2 の手順(`docker compose up -d` → 接続確認) | **接続の応答**(例 `PostgreSQL 17.x` / `docker compose ps` が healthy) |
| 5 | backend・frontend が起動して疎通 | 8-3 | onboarding 8-3 の手順 | **HTTP 疎通の応答コード**(例 backend `/health` が 200・frontend が 200) |

## 私に渡していただく値(証跡の 12 欄)

**この 12 個が揃えば私が証跡を起草します。** 数値・文字列はコピーで構いません。

| 欄 | 採り方 |
| --- | --- |
| **日時** | 受入を実施した日時(JST。開始〜終了でも可) |
| **commit SHA** | `3873ce8586a54e273a722540a07896335d7aceb4`(固定値・確認のみ) |
| **Windows 版** | PowerShell で `[System.Environment]::OSVersion.Version` または `winver` の表示 |
| **WSL 版** | `wsl --version` の 1 行目(WSL のバージョン) |
| **ディストリビューション版** | WSL 内で `lsb_release -d` または `cat /etc/os-release \| head -2` |
| **onboarding 版** | `1.2`(固定値・確認のみ) |
| **onboarding blob SHA** | `43836beff93a5751daf30aaacdd2c050b5d54ac5`(固定値・確認のみ) |
| **主要ツールの版(python / uv / node / docker)** | `python3 -V` / `uv --version` / `node -v` / `docker --version` |
| **実行コマンドと終了コード** | 合格項目 1〜5 のコマンドと各終了コード(`echo $?`) |
| **各合格項目の期待値と実測値** | 上表の「記録するもの」5 件 |
| **標準出力またはログ成果物への参照** | **2-2 節が出力した「証跡セルへ貼る 1 物理行」をそのまま**(`host_raw=…; wsl_dpkg=…`) |
| **判定者** | お名前 |

## 判定(運用手順 C)

1. 受入証跡 README の**人手確認項目**を確認する — 6 ラベルの実在と、値が受入プロファイルに適合していること
2. **`passed` / `failed` を判定していただく**(判定は判定者の専権。私は転記のみ)
3. **`passed` の場合、その時点の `origin/develop` の完全 OID を `phase4_base_sha` として記録**していただく
   ```bash
   git fetch origin develop && git rev-parse origin/develop
   ```
   これを判定時点で採るのは、10.1 が「**判定時点**の `origin/develop`」と定めているため

## 中断してよい条件(fail-closed)

次のいずれかなら**受入を続行せず連絡**してほしい。無理に進めない方が安全である。

- 2-2 節が `不適合:` を出した(採取不能 / 許容表にない値 / 3 値の不一致)
- `git branch --show-current` が `develop` にならない、または `rev-parse HEAD` が `T` と一致しない
- 合格項目のいずれかが失敗し、**手順の範囲内で解決できない**
- 手順が一意でなく、どう進めばよいか分からない箇所があった(**これも記録すべき指摘**)

**途中で止まった場合も証跡は作る** — 到達済みの実測値と失敗理由を記録し、未実施の欄には非空の理由値を入れて `result: failed` として予約を閉じる(計画書の経路 A)。
