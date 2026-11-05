"""有効打球語彙の正準keyset順を支えるpartial索引を追加する。"""

from alembic import op

revision = "0040_batted_vocabulary_index"
down_revision = "0039_ordinary_pitch_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """既行や権限を変えず、実keysetと同じ照合順の索引だけを作る。"""
    op.execute(
        """CREATE INDEX ix_admin_vocabularies_batted_ball_key_c
        ON public.admin_vocabularies (key COLLATE "C")
        WHERE category = 'batted_ball' AND disabled = false"""
    )


def downgrade() -> None:
    """記録データを変えず、追加した索引だけを取り外す。"""
    op.drop_index(
        "ix_admin_vocabularies_batted_ball_key_c",
        table_name="admin_vocabularies",
        schema="public",
    )
