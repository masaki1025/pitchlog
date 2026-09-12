"""操作イベントの確定内容を構成する全 18 列を不変にする。"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025_operation_event_immutable"
down_revision: str | Sequence[str] | None = "0024_players_identity_trigger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION_NAME = "prevent_operation_events_content_update"
_TRIGGER_NAME = "trg_operation_events_content_immutable"


def upgrade() -> None:
    """操作イベントの保護対象を未分類だった 9 列にも拡張する。"""
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FUNCTION_NAME}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(
                NEW.tenant_id,
                NEW.id,
                NEW.game_id,
                NEW.generation,
                NEW.d1,
                NEW.d5,
                NEW.event_kind,
                NEW.payload,
                NEW.state_diff,
                NEW.ledger_kind,
                NEW.is_tombstone,
                NEW.target_generation,
                NEW.target_d1,
                NEW.expected_version,
                NEW.change_order,
                NEW.legacy_row_identifier,
                NEW.migration_unverified,
                NEW.import_batch_id
            ) IS DISTINCT FROM ROW(
                OLD.tenant_id,
                OLD.id,
                OLD.game_id,
                OLD.generation,
                OLD.d1,
                OLD.d5,
                OLD.event_kind,
                OLD.payload,
                OLD.state_diff,
                OLD.ledger_kind,
                OLD.is_tombstone,
                OLD.target_generation,
                OLD.target_d1,
                OLD.expected_version,
                OLD.change_order,
                OLD.legacy_row_identifier,
                OLD.migration_unverified,
                OLD.import_batch_id
            ) THEN
                RAISE EXCEPTION 'operation_events confirmed content is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(f"DROP TRIGGER {_TRIGGER_NAME} ON operation_events")
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER_NAME}
        BEFORE UPDATE OF
            tenant_id,
            id,
            game_id,
            generation,
            d1,
            d5,
            event_kind,
            payload,
            state_diff,
            ledger_kind,
            is_tombstone,
            target_generation,
            target_d1,
            expected_version,
            change_order,
            legacy_row_identifier,
            migration_unverified,
            import_batch_id
        ON operation_events
        FOR EACH ROW
        EXECUTE FUNCTION {_FUNCTION_NAME}()
        """
    )


def downgrade() -> None:
    """操作イベントの不変性トリガを 0005 の 9 列へ戻す。"""
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FUNCTION_NAME}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(
                NEW.tenant_id,
                NEW.id,
                NEW.game_id,
                NEW.generation,
                NEW.d1,
                NEW.d5,
                NEW.event_kind,
                NEW.payload,
                NEW.state_diff
            ) IS DISTINCT FROM ROW(
                OLD.tenant_id,
                OLD.id,
                OLD.game_id,
                OLD.generation,
                OLD.d1,
                OLD.d5,
                OLD.event_kind,
                OLD.payload,
                OLD.state_diff
            ) THEN
                RAISE EXCEPTION 'operation_events confirmed content is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(f"DROP TRIGGER {_TRIGGER_NAME} ON operation_events")
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER_NAME}
        BEFORE UPDATE OF
            tenant_id,
            id,
            game_id,
            generation,
            d1,
            d5,
            event_kind,
            payload,
            state_diff
        ON operation_events
        FOR EACH ROW
        EXECUTE FUNCTION {_FUNCTION_NAME}()
        """
    )
