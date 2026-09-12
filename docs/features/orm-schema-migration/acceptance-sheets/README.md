# ORM スキーマ移行の受入証跡突合シート

このディレクトリの N1・N3・N4・N7 は `scripts/generate_orm_acceptance_sheets.py` が機械生成する。対象・正本側・実装側は生成器が更新し、判定・理由と典拠は人間が記入する。

## 生成コマンド

```bash
uv run python scripts/generate_orm_acceptance_sheets.py
```

既定の再生成では判定欄と理由欄が空になる。

是正前の判定を安全な行だけ持ち越す場合:

```bash
uv run python scripts/generate_orm_acceptance_sheets.py --carry-judgments-from <是正前のrevision>
```

持ち越しモードは突合キーが不変・旧判定が差分でない・旧理由が契約 diff の変更識別子を含まない行だけを引き継ぐ。

## シート

- [N1 表の全数性](N1-table-completeness.md): 100 行
- [N3 不変列マトリクスの全数性](N3-immutability-completeness.md): 77 行
- [N4 削除系統の割り当て](N4-deletion-lifecycle.md): 54 行
- [N7 必須属性の全数性](N7-required-attributes.md): 96 行

## シートを作らない受け取り先

- N2: TSK-250 の 88 列写像の確定ゲートで閉じる。
- N5: TSK-356 の 88 列互換出力（FR-031）の往復検証で閉じる。
- N6: 運用証跡として、各環境の初回 migration 前に実施者・確認時点・endpoint 種別だけを PR 本文の実施記録行へ残す。URL や資格情報は記録しない。
