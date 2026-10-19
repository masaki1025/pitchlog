"""試合の適用規則スナップショットを初回保存後に保護する。

初回 INSERT と同値更新を許し、保存後の異値 UPDATE を拒否する。BEFORE トリガは
保護列の直接更新を、AFTER トリガは別列更新に連鎖する BEFORE トリガが最終行で
値を書き換える経路を塞ぐ。どちらも SQLSTATE 23514 で拒否する。
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0033_game_rules_immutable"
down_revision: str | Sequence[str] | None = "0032_rg1_restore_gate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BEFORE_FUNCTION = "public.prevent_games_applied_rules_update"
_AFTER_FUNCTION = "public.verify_games_applied_rules_final"
_BEFORE_TRIGGER = "trg_games_applied_rules_immutable"
_AFTER_TRIGGER = "trg_games_applied_rules_final_immutable"


def upgrade() -> None:
    """INSERT を許し、保存後の異値 UPDATE を最終行で拒否する。"""
    op.execute(
        f"""
        CREATE FUNCTION {_BEFORE_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF OLD.applied_rules IS DISTINCT FROM NEW.applied_rules THEN
                RAISE EXCEPTION 'games.applied_rules is immutable after insert'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_AFTER_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF OLD.applied_rules IS DISTINCT FROM NEW.applied_rules THEN
                RAISE EXCEPTION 'games.applied_rules is immutable after insert'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_BEFORE_TRIGGER}
        BEFORE UPDATE OF applied_rules ON public.games
        FOR EACH ROW
        EXECUTE FUNCTION {_BEFORE_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_AFTER_TRIGGER}
        AFTER UPDATE ON public.games
        FOR EACH ROW
        WHEN (OLD.applied_rules IS DISTINCT FROM NEW.applied_rules)
        EXECUTE FUNCTION {_AFTER_FUNCTION}()
        """
    )


def downgrade() -> None:
    """追加したトリガと関数だけを除去し、既存行には触れない。"""
    op.execute(f"DROP TRIGGER {_AFTER_TRIGGER} ON public.games")
    op.execute(f"DROP TRIGGER {_BEFORE_TRIGGER} ON public.games")
    op.execute(f"DROP FUNCTION {_AFTER_FUNCTION}()")
    op.execute(f"DROP FUNCTION {_BEFORE_FUNCTION}()")
