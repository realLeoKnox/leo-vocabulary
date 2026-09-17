from datetime import date as Date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Priority = Literal["high", "normal", "low"]
SourceType = str
ReviewMode = Literal["visual", "audio"]


class MeaningIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pos: str = Field(min_length=1, max_length=30)
    zh: str = Field(min_length=1, max_length=1000)


class SourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    type: SourceType = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_-]*$")
    date: Date | None = None
    description: str | None = Field(default=None, max_length=2000)


class SourceCreate(SourceIn):
    pass


class SourceOut(SourceIn):
    id: int
    uid: str
    encounter_count: int = 0
    created_at: datetime


class EncounterOut(BaseModel):
    id: int
    uid: str
    vocabulary_uid: str
    lemma: str
    source_id: int
    source_name: str
    source_type: str
    surface_form: str
    context: str | None
    note: str | None
    origin: str
    familiarity: str | None
    marked_unknown: bool
    token_index: int | None
    char_offset: int | None
    external_ref: str | None
    encountered_at: Date
    occurred_at: datetime


class ReviewStateOut(BaseModel):
    mode: ReviewMode
    mastery: int
    interval_days: int
    repetitions: int
    lapses: int
    due_at: datetime


class WordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    word: str = Field(min_length=1, max_length=120)
    lemma: str = Field(min_length=1, max_length=120)
    phonetic: str | None = Field(default=None, max_length=160)
    meanings: list[MeaningIn] = Field(min_length=1)
    word_family: list[str] = Field(default_factory=list, max_length=30)
    priority: Priority = "normal"
    context: str | None = Field(default=None, max_length=4000)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("word", "lemma")
    @classmethod
    def normalize_word(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("word_family")
    @classmethod
    def normalize_family(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip().lower() for item in value if item.strip()))


class WordCreate(WordInput):
    source_id: int | None = None
    encountered_at: Date | None = None


class WordUpdate(BaseModel):
    word: str | None = Field(default=None, min_length=1, max_length=120)
    lemma: str | None = Field(default=None, min_length=1, max_length=120)
    phonetic: str | None = Field(default=None, max_length=160)
    meanings: list[MeaningIn] | None = None
    word_family: list[str] | None = None
    priority: Priority | None = None
    note: str | None = Field(default=None, max_length=2000)


class WordOut(BaseModel):
    id: int
    uid: str
    word: str
    lemma: str
    phonetic: str | None
    meanings: list[MeaningIn]
    word_family: list[str]
    priority: str
    note: str | None
    encounter_count: int
    created_at: datetime
    encounters: list[EncounterOut] = Field(default_factory=list)
    review_states: list[ReviewStateOut] = Field(default_factory=list)


class VocabularyUpsertIn(BaseModel):
    """Transport-neutral vocabulary attributes used by non-import modules."""
    model_config = ConfigDict(extra="forbid")
    word: str = Field(min_length=1, max_length=120)
    lemma: str = Field(min_length=1, max_length=120)
    phonetic: str | None = Field(default=None, max_length=160)
    meanings: list[MeaningIn] = Field(default_factory=list)
    word_family: list[str] = Field(default_factory=list, max_length=30)
    priority: Priority = "normal"
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("word", "lemma")
    @classmethod
    def normalize_word(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("word_family")
    @classmethod
    def normalize_family(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip().lower() for item in value if item.strip()))


class EncounterCreate(BaseModel):
    """Common command for JSON import, readers, morning reading, and future modules."""
    model_config = ConfigDict(extra="forbid")
    vocabulary: VocabularyUpsertIn
    source_id: int | None = None
    source_uid: str | None = None
    source: SourceIn | None = None
    context: str | None = Field(default=None, max_length=4000)
    note: str | None = Field(default=None, max_length=2000)
    origin: str = Field(default="other", min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_-]*$")
    familiarity: Literal["unknown", "fuzzy", "known"] | None = None
    marked_unknown: bool = False
    token_index: int | None = Field(default=None, ge=0)
    char_offset: int | None = Field(default=None, ge=0)
    external_ref: str | None = Field(default=None, max_length=200)
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def require_one_source(self):
        if sum(value is not None for value in (self.source_id, self.source_uid, self.source)) != 1:
            raise ValueError("source_id、source_uid、source 必须且只能提供一个")
        return self


class ImportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    source: SourceIn
    words: list[WordInput] = Field(min_length=1, max_length=1000)


class ImportPreviewItem(BaseModel):
    index: int
    lemma: str
    action: Literal["create", "merge"]
    existing_word_id: int | None = None


class ImportPreview(BaseModel):
    valid: bool
    source_action: Literal["create", "reuse"]
    total: int
    create_count: int
    merge_count: int
    items: list[ImportPreviewItem]


class ImportResult(BaseModel):
    source_id: int
    total: int
    created: int
    merged: int
    encounters_added: int
    meanings_added: int
    family_members_added: int


class ReviewSubmit(BaseModel):
    word_id: int
    mode: ReviewMode
    rating: Literal[0, 1, 2, 3]  # 忘了 / 模糊 / 认识 / 秒懂
    response_time_ms: int | None = Field(default=None, ge=0, le=3_600_000)
    encounter_uid: str | None = None
    context: str | None = Field(default=None, max_length=4000)


class ReviewLogOut(BaseModel):
    uid: str
    vocabulary_uid: str
    lemma: str
    reviewed_at: datetime
    mode: str
    rating: str
    mastery_before: int
    mastery_after: int
    interval_before: int
    interval_after: int
    next_review_at: datetime | None
    response_time_ms: int | None
    encounter_uid: str | None
    context: str | None


class DashboardStats(BaseModel):
    due_today: int
    new_words: int
    mastered: int
    total_words: int
    recent_sources: list[dict]
    stubborn_words: list[dict]
