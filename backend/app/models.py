from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uid() -> str:
    from uuid import uuid4
    return str(uuid4())


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("name", "source_type", "source_date", name="uq_source_identity"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=new_uid)
    name: Mapped[str] = mapped_column(String(200), index=True)
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    source_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    encounters: Mapped[list[Encounter]] = relationship(back_populates="source", cascade="all, delete-orphan")


class Word(Base):
    __tablename__ = "words"

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=new_uid)
    word: Mapped[str] = mapped_column(String(120), index=True)
    lemma: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    phonetic: Mapped[str | None] = mapped_column(String(160), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal", index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    meanings: Mapped[list[Meaning]] = relationship(back_populates="word", cascade="all, delete-orphan", order_by="Meaning.position")
    family_members: Mapped[list[WordFamilyMember]] = relationship(back_populates="word", cascade="all, delete-orphan")
    encounters: Mapped[list[Encounter]] = relationship(back_populates="word", cascade="all, delete-orphan")
    review_states: Mapped[list[ReviewState]] = relationship(back_populates="word", cascade="all, delete-orphan")
    review_logs: Mapped[list[ReviewLog]] = relationship(back_populates="word", cascade="all, delete-orphan")

    @property
    def encounter_count(self) -> int:
        return len(self.encounters)


class Meaning(Base):
    __tablename__ = "meanings"
    __table_args__ = (UniqueConstraint("word_id", "pos", "zh", name="uq_meaning"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), index=True)
    pos: Mapped[str] = mapped_column(String(30))
    zh: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
    word: Mapped[Word] = relationship(back_populates="meanings")


class WordFamilyMember(Base):
    __tablename__ = "word_family_members"
    __table_args__ = (UniqueConstraint("word_id", "member", name="uq_family_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), index=True)
    member: Mapped[str] = mapped_column(String(120), index=True)
    word: Mapped[Word] = relationship(back_populates="family_members")


class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=new_uid)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    surface_form: Mapped[str] = mapped_column(String(120))
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str] = mapped_column(String(40), default="other", index=True)
    familiarity: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    marked_unknown: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    first_marked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_ref: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    encountered_at: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    word: Mapped[Word] = relationship(back_populates="encounters")
    source: Mapped[Source] = relationship(back_populates="encounters")
    review_logs: Mapped[list[ReviewLog]] = relationship(back_populates="encounter")


class ReviewState(Base):
    __tablename__ = "review_states"
    __table_args__ = (UniqueConstraint("word_id", "mode", name="uq_review_state_mode"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(20), index=True)  # visual | audio
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    mastery: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    word: Mapped[Word] = relationship(back_populates="review_states")


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=new_uid)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(20), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    mastery_before: Mapped[int] = mapped_column(Integer, default=0)
    mastery_after: Mapped[int] = mapped_column(Integer, default=0)
    interval_before: Mapped[int] = mapped_column(Integer, default=0)
    interval_after: Mapped[int] = mapped_column(Integer, default=0)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    encounter_id: Mapped[int | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    word: Mapped[Word] = relationship(back_populates="review_logs")
    encounter: Mapped[Encounter | None] = relationship(back_populates="review_logs")
