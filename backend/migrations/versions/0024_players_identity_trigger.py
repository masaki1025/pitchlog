"""選手の内部 ID を不変にするトリガを追加する。"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024_players_identity_trigger"
down_revision: str | Sequence[str] | None = "0023_play_runner_status_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION_NAME = "prevent_players_identity_update"
_TRIGGER_NAME = "trg_players_identity_immutable"


def upgrade() -> None:
    """選手の内部 ID を保護する不変性トリガを追加する。"""
    op.execute(
        f"""
        CREATE FUNCTION {_FUNCTION_NAME}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(NEW.id) IS DISTINCT FROM ROW(OLD.id) THEN
                RAISE EXCEPTION 'players.id is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER_NAME}
        BEFORE UPDATE OF id ON players
        FOR EACH ROW
        EXECUTE FUNCTION {_FUNCTION_NAME}()
        """
    )


def downgrade() -> None:
    """選手の内部 ID を保護する不変性トリガを除去する。"""
    op.execute(f"DROP TRIGGER {_TRIGGER_NAME} ON players")
    op.execute(f"DROP FUNCTION {_FUNCTION_NAME}()")
