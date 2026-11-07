"""D03の真正entry原本の追記専用候補。未配備。"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    Table,
    Text,
    Uuid,
)

from pitchlog.db.base import Base


class PitcherEntrySource(Base):
    """原本は消さず、現在複合資格で実効contextを完全照合する。"""

    __table__ = Table(
        "pitcher_entry_sources",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("proof_sha256", Text, nullable=False),
        Column("origin_kind", Text, nullable=False),
        Column("start_attempt_id", Uuid, nullable=True),
        Column("source_event_id", Uuid, nullable=True),
        Column("generation", BigInteger, nullable=False),
        Column("d1", BigInteger, nullable=True),
        Column("slot_version", BigInteger, nullable=True),
        Column("player_id", Uuid, nullable=False),
        Column("defending_side", Text, nullable=False),
        Column("inning", BigInteger, nullable=False),
        Column("half", Text, nullable=False),
        Column("proof_kind", Text, nullable=False),
        Column("source_fingerprint", Text, nullable=False),
        Column("artifact_sha256", Text, nullable=False),
        Column("context_sha256", Text, nullable=False),
        PrimaryKeyConstraint("tenant_id", "game_id", "proof_sha256"),
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_pitcher_entry_game",
            ondelete="NO ACTION",
            match="FULL",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_pitcher_entry_player",
            ondelete="NO ACTION",
            match="FULL",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "start_attempt_id"],
            ["game_start_attempts.tenant_id", "game_start_attempts.attempt_id"],
            name="fk_pitcher_entry_start",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="fk_pitcher_entry_event",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "(origin_kind='start' AND start_attempt_id IS NOT NULL "
            "AND source_event_id IS NULL AND d1 IS NULL AND slot_version IS NULL "
            "AND inning=1 AND half='top') OR "
            "(origin_kind IN ('play','substitution','reopen') "
            "AND start_attempt_id IS NULL AND source_event_id IS NOT NULL "
            "AND d1 IS NOT NULL AND slot_version IS NOT NULL "
            "AND d1>0 AND slot_version>0)",
            name="ck_pitcher_entry_origin",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "generation"],
            [
                "recording_generations.tenant_id",
                "recording_generations.game_id",
                "recording_generations.generation",
            ],
            name="fk_pitcher_entry_generation",
            ondelete="NO ACTION",
            match="FULL",
        ),
        CheckConstraint(
            "(origin_kind='substitution' AND proof_kind='pitcher-defensive-entry') OR "
            "(origin_kind IN ('start','play','reopen') "
            "AND proof_kind='defensive-half-entry')",
            name="ck_pitcher_entry_reason",
        ),
        CheckConstraint(
            "generation>0 AND inning>0 AND "
            "((half='top' AND defending_side='home') OR "
            "(half='bottom' AND defending_side='away'))",
            name="ck_pitcher_entry_half",
        ),
        CheckConstraint(
            "proof_kind IN ('defensive-half-entry','pitcher-defensive-entry') AND "
            "proof_sha256 ~ '^[a-f0-9]{64}$' AND "
            "context_sha256 ~ '^[a-f0-9]{64}$' AND "
            "artifact_sha256 ~ '^[a-f0-9]{64}$' AND source_fingerprint<>''",
            name="ck_pitcher_entry_hashes",
        ),
        Index("ix_pitcher_entry_source_player", "tenant_id", "game_id", "player_id"),
        schema="sync_fence",
        info={"append_only": True, "formal_acceptance": "pending"},
    )
