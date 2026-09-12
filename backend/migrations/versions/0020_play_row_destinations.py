"""プレイ行の行き先に対応する型付き列を追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_play_row_destinations"
down_revision: str | Sequence[str] | None = "0019_play_row_original_text"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_course_range_checks() -> None:
    """列名を含む定義から座標範囲 CHECK を一意に特定して削除する。"""
    for column_name in ("course_x", "course_y"):
        op.execute(
            f"""
            DO $migration$
            DECLARE
                constraint_name text;
                matched_count integer := 0;
            BEGIN
                FOR constraint_name IN
                    SELECT conname
                    FROM pg_constraint
                    WHERE conrelid = 'play_rows'::regclass
                      AND contype = 'c'
                      AND pg_get_constraintdef(oid) LIKE '%{column_name}%'
                LOOP
                    matched_count := matched_count + 1;
                    EXECUTE format(
                        'ALTER TABLE play_rows DROP CONSTRAINT %I',
                        constraint_name
                    );
                END LOOP;

                IF matched_count <> 1 THEN
                    RAISE EXCEPTION
                        'play_rows.{column_name} の範囲 CHECK が % 件ある',
                        matched_count;
                END IF;
            END
            $migration$;
            """
        )


def upgrade() -> None:
    """正本のプレイ行行き先を型付き列と語彙参照で表現する。"""
    _drop_course_range_checks()
    op.execute("ALTER TABLE play_rows ALTER COLUMN course_x TYPE double precision")
    op.execute("ALTER TABLE play_rows ALTER COLUMN course_y TYPE double precision")
    op.execute("ALTER TABLE play_rows ALTER COLUMN pitch_speed TYPE double precision")
    op.create_check_constraint(
        "ck_play_rows_course_x_range",
        "play_rows",
        "course_x IS NULL OR course_x BETWEEN 0 AND 1",
    )
    op.create_check_constraint(
        "ck_play_rows_course_y_range",
        "play_rows",
        "course_y IS NULL OR course_y BETWEEN 0 AND 1",
    )

    op.add_column(
        "play_rows", sa.Column("batting_order", sa.BigInteger(), nullable=True)
    )
    op.add_column("play_rows", sa.Column("batting_side", sa.Text(), nullable=True))
    op.add_column("play_rows", sa.Column("strategy_key", sa.Text(), nullable=True))
    op.add_column(
        "play_rows", sa.Column("strategy_detail_key", sa.Text(), nullable=True)
    )
    op.add_column(
        "play_rows", sa.Column("strategy_result_key", sa.Text(), nullable=True)
    )
    op.add_column("play_rows", sa.Column("batter_status", sa.Text(), nullable=True))
    op.add_column("play_rows", sa.Column("stance", sa.Text(), nullable=True))
    op.add_column("play_rows", sa.Column("pitch_type_key", sa.Text(), nullable=True))
    op.add_column(
        "play_rows", sa.Column("batting_result_key", sa.Text(), nullable=True)
    )
    op.add_column(
        "play_rows",
        sa.Column("secondary_batting_result_key", sa.Text(), nullable=True),
    )
    op.add_column("play_rows", sa.Column("batted_ball_type", sa.Text(), nullable=True))
    op.add_column(
        "play_rows", sa.Column("batted_ball_strength", sa.Text(), nullable=True)
    )
    op.add_column("play_rows", sa.Column("hit_x", sa.Double(), nullable=True))
    op.add_column("play_rows", sa.Column("hit_y", sa.Double(), nullable=True))
    op.add_column("play_rows", sa.Column("pickoff_type", sa.Text(), nullable=True))
    op.add_column("play_rows", sa.Column("pickoff_detail", sa.Text(), nullable=True))
    op.add_column("play_rows", sa.Column("error_type", sa.Text(), nullable=True))
    op.add_column("play_rows", sa.Column("press", sa.Text(), nullable=True))
    op.add_column("play_rows", sa.Column("fake_run", sa.Text(), nullable=True))
    op.add_column("play_rows", sa.Column("comment", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_play_rows_hit_x_range",
        "play_rows",
        "hit_x IS NULL OR hit_x BETWEEN 0 AND 1",
    )
    op.create_check_constraint(
        "ck_play_rows_hit_y_range",
        "play_rows",
        "hit_y IS NULL OR hit_y BETWEEN 0 AND 1",
    )

    op.create_foreign_key(
        "fk_play_rows_strategy",
        "play_rows",
        "tenant_vocabularies",
        ["tenant_id", "strategy_key"],
        ["tenant_id", "key"],
        ondelete="NO ACTION",
        match="SIMPLE",
    )
    op.create_foreign_key(
        "fk_play_rows_strategy_detail",
        "play_rows",
        "tenant_vocabularies",
        ["tenant_id", "strategy_detail_key"],
        ["tenant_id", "key"],
        ondelete="NO ACTION",
        match="SIMPLE",
    )
    op.create_foreign_key(
        "fk_play_rows_strategy_result",
        "play_rows",
        "tenant_vocabularies",
        ["tenant_id", "strategy_result_key"],
        ["tenant_id", "key"],
        ondelete="NO ACTION",
        match="SIMPLE",
    )
    op.create_foreign_key(
        "fk_play_rows_pitch_type",
        "play_rows",
        "tenant_vocabularies",
        ["tenant_id", "pitch_type_key"],
        ["tenant_id", "key"],
        ondelete="NO ACTION",
        match="SIMPLE",
    )
    op.create_foreign_key(
        "fk_play_rows_batting_result",
        "play_rows",
        "admin_vocabularies",
        ["batting_result_key"],
        ["key"],
        ondelete="NO ACTION",
        match="SIMPLE",
    )
    op.create_foreign_key(
        "fk_play_rows_secondary_batting_result",
        "play_rows",
        "admin_vocabularies",
        ["secondary_batting_result_key"],
        ["key"],
        ondelete="NO ACTION",
        match="SIMPLE",
    )
    op.create_foreign_key(
        "fk_play_rows_batted_ball_type",
        "play_rows",
        "admin_vocabularies",
        ["batted_ball_type"],
        ["key"],
        ondelete="NO ACTION",
        match="SIMPLE",
    )
    op.create_foreign_key(
        "fk_play_rows_batted_ball_strength",
        "play_rows",
        "admin_vocabularies",
        ["batted_ball_strength"],
        ["key"],
        ondelete="NO ACTION",
        match="SIMPLE",
    )

    op.drop_column("play_rows", "compatibility_payload")


def downgrade() -> None:
    """型付き列を除去し、旧来の未定義 JSONB 列を復元する。"""
    op.add_column(
        "play_rows",
        sa.Column("compatibility_payload", postgresql.JSONB(), nullable=False),
    )

    op.drop_constraint(
        "fk_play_rows_batted_ball_strength", "play_rows", type_="foreignkey"
    )
    op.drop_constraint("fk_play_rows_batted_ball_type", "play_rows", type_="foreignkey")
    op.drop_constraint(
        "fk_play_rows_secondary_batting_result", "play_rows", type_="foreignkey"
    )
    op.drop_constraint("fk_play_rows_batting_result", "play_rows", type_="foreignkey")
    op.drop_constraint("fk_play_rows_pitch_type", "play_rows", type_="foreignkey")
    op.drop_constraint("fk_play_rows_strategy_result", "play_rows", type_="foreignkey")
    op.drop_constraint("fk_play_rows_strategy_detail", "play_rows", type_="foreignkey")
    op.drop_constraint("fk_play_rows_strategy", "play_rows", type_="foreignkey")
    op.drop_constraint("ck_play_rows_hit_y_range", "play_rows", type_="check")
    op.drop_constraint("ck_play_rows_hit_x_range", "play_rows", type_="check")

    op.drop_column("play_rows", "comment")
    op.drop_column("play_rows", "fake_run")
    op.drop_column("play_rows", "press")
    op.drop_column("play_rows", "error_type")
    op.drop_column("play_rows", "pickoff_detail")
    op.drop_column("play_rows", "pickoff_type")
    op.drop_column("play_rows", "hit_y")
    op.drop_column("play_rows", "hit_x")
    op.drop_column("play_rows", "batted_ball_strength")
    op.drop_column("play_rows", "batted_ball_type")
    op.drop_column("play_rows", "secondary_batting_result_key")
    op.drop_column("play_rows", "batting_result_key")
    op.drop_column("play_rows", "pitch_type_key")
    op.drop_column("play_rows", "stance")
    op.drop_column("play_rows", "batter_status")
    op.drop_column("play_rows", "strategy_result_key")
    op.drop_column("play_rows", "strategy_detail_key")
    op.drop_column("play_rows", "strategy_key")
    op.drop_column("play_rows", "batting_side")
    op.drop_column("play_rows", "batting_order")

    _drop_course_range_checks()
    op.execute("ALTER TABLE play_rows ALTER COLUMN pitch_speed TYPE numeric")
    op.execute("ALTER TABLE play_rows ALTER COLUMN course_y TYPE numeric")
    op.execute("ALTER TABLE play_rows ALTER COLUMN course_x TYPE numeric")
    op.execute(
        "ALTER TABLE play_rows ADD CHECK (course_x IS NULL OR course_x BETWEEN 0 AND 1)"
    )
    op.execute(
        "ALTER TABLE play_rows ADD CHECK (course_y IS NULL OR course_y BETWEEN 0 AND 1)"
    )
