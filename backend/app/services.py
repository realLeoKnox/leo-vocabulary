from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from math import ceil

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from . import models, schemas


WORD_LOAD = (
    selectinload(models.Word.meanings),
    selectinload(models.Word.family_members),
    selectinload(models.Word.encounters).selectinload(models.Encounter.source),
    selectinload(models.Word.review_states),
)


def normalize(value: str) -> str:
    return value.strip().lower()


def get_or_create_source(db: Session, source: schemas.SourceIn) -> tuple[models.Source, bool]:
    stmt = select(models.Source).where(
        models.Source.name == source.name.strip(),
        models.Source.source_type == source.type,
        models.Source.source_date == source.date,
    )
    existing = db.scalar(stmt)
    if existing:
        existing.archived_at = None
        if source.description and not existing.description:
            existing.description = source.description
        return existing, False
    row = models.Source(
        name=source.name.strip(), source_type=source.type, source_date=source.date, description=source.description
    )
    db.add(row)
    db.flush()
    return row, True


def resolve_source(
    db: Session, *, source_id: int | None = None, source_uid: str | None = None,
    source: schemas.SourceIn | None = None,
) -> models.Source:
    if source_id is not None:
        row = db.get(models.Source, source_id)
    elif source_uid is not None:
        row = db.scalar(select(models.Source).where(models.Source.uid == source_uid))
    elif source is not None:
        row, _ = get_or_create_source(db, source)
    else:
        row = None
    if row is None:
        raise LookupError("来源不存在")
    return row


def ensure_review_states(db: Session, word: models.Word) -> None:
    modes = {state.mode for state in word.review_states}
    now = datetime.now(timezone.utc)
    for mode in ("visual", "audio"):
        if mode not in modes:
            db.add(models.ReviewState(word=word, mode=mode, due_at=now))


def upsert_vocabulary(
    db: Session, item: schemas.WordInput | schemas.VocabularyUpsertIn
) -> tuple[models.Word, bool, int, int]:
    """Create or enrich one lemma without knowing where it was encountered."""
    lemma = normalize(item.lemma)
    word = db.scalar(select(models.Word).options(*WORD_LOAD).where(models.Word.lemma == lemma))
    created = word is None
    if created:
        word = models.Word(
            word=normalize(item.word), lemma=lemma, phonetic=item.phonetic, priority=item.priority, note=item.note
        )
        db.add(word)
        db.flush()
    else:
        word.archived_at = None
        word.word = word.word or normalize(item.word)
        word.phonetic = word.phonetic or item.phonetic
        if item.priority == "high" or (item.priority == "normal" and word.priority == "low"):
            word.priority = item.priority
        word.note = word.note or item.note

    existing_meanings = {(m.pos, m.zh) for m in word.meanings}
    meanings_added = 0
    for position, meaning in enumerate(item.meanings):
        key = (meaning.pos.strip(), meaning.zh.strip())
        if key not in existing_meanings:
            db.add(models.Meaning(word=word, pos=key[0], zh=key[1], position=len(existing_meanings) + position))
            existing_meanings.add(key)
            meanings_added += 1

    existing_family = {m.member for m in word.family_members}
    family_added = 0
    for member in item.word_family:
        member = normalize(member)
        if member and member != lemma and member not in existing_family:
            db.add(models.WordFamilyMember(word=word, member=member))
            existing_family.add(member)
            family_added += 1

    ensure_review_states(db, word)
    return word, created, meanings_added, family_added


def record_encounter(
    db: Session, *, word: models.Word, source: models.Source, surface_form: str,
    context: str | None = None, note: str | None = None, origin: str = "other",
    familiarity: str | None = None, marked_unknown: bool = False,
    token_index: int | None = None, char_offset: int | None = None,
    external_ref: str | None = None, occurred_at: datetime | None = None,
) -> models.Encounter:
    """Single event writer shared by imports, readers, morning reading, and manual entry."""
    occurred_at = occurred_at or datetime.now(timezone.utc)
    row = models.Encounter(
        word=word, source=source, surface_form=normalize(surface_form), context=context, note=note,
        origin=origin, familiarity=familiarity, marked_unknown=marked_unknown,
        first_marked_at=occurred_at if marked_unknown else None, token_index=token_index,
        char_offset=char_offset, external_ref=external_ref, encountered_at=occurred_at.date(),
        occurred_at=occurred_at,
    )
    db.add(row)
    db.flush()
    return row


def record_vocabulary_encounter(
    db: Session, *, item: schemas.WordInput | schemas.VocabularyUpsertIn, source: models.Source,
    context: str | None = None, encounter_note: str | None = None, origin: str = "other",
    familiarity: str | None = None, marked_unknown: bool = False,
    token_index: int | None = None, char_offset: int | None = None,
    external_ref: str | None = None, occurred_at: datetime | None = None,
) -> tuple[models.Word, models.Encounter, bool, int, int]:
    word, created, meanings_added, family_added = upsert_vocabulary(db, item)
    encounter = record_encounter(
        db, word=word, source=source, surface_form=item.word, context=context,
        note=encounter_note, origin=origin, familiarity=familiarity, marked_unknown=marked_unknown,
        token_index=token_index, char_offset=char_offset, external_ref=external_ref,
        occurred_at=occurred_at,
    )
    return word, encounter, created, meanings_added, family_added


def preview_import(db: Session, payload: schemas.ImportPayload) -> schemas.ImportPreview:
    source_exists = db.scalar(select(models.Source.id).where(
        models.Source.name == payload.source.name.strip(),
        models.Source.source_type == payload.source.type,
        models.Source.source_date == payload.source.date,
    ))
    lemmas = [normalize(item.lemma) for item in payload.words]
    existing = dict(db.execute(select(models.Word.lemma, models.Word.id).where(models.Word.lemma.in_(lemmas))).all())
    seen_new: set[str] = set()
    items = []
    create_count = 0
    for index, lemma in enumerate(lemmas):
        exists_id = existing.get(lemma)
        action = "merge" if exists_id or lemma in seen_new else "create"
        if action == "create":
            create_count += 1
            seen_new.add(lemma)
        items.append(schemas.ImportPreviewItem(index=index, lemma=lemma, action=action, existing_word_id=exists_id))
    return schemas.ImportPreview(
        valid=True, source_action="reuse" if source_exists else "create", total=len(items),
        create_count=create_count, merge_count=len(items) - create_count, items=items,
    )


def run_import(db: Session, payload: schemas.ImportPayload) -> schemas.ImportResult:
    source, _ = get_or_create_source(db, payload.source)
    created = merged = meanings_added = family_added = 0
    import_date = payload.source.date or date.today()
    occurred_at = datetime.combine(import_date, time.min, tzinfo=timezone.utc)
    for item in payload.words:
        _, _, was_created, meaning_count, family_count = record_vocabulary_encounter(
            db, item=item, source=source, context=item.context, encounter_note=item.note,
            origin="json_import", familiarity="unknown", marked_unknown=True, occurred_at=occurred_at,
        )
        created += int(was_created)
        merged += int(not was_created)
        meanings_added += meaning_count
        family_added += family_count
        db.flush()  # makes duplicate lemmas inside one payload merge correctly
    db.commit()
    return schemas.ImportResult(
        source_id=source.id, total=len(payload.words), created=created, merged=merged,
        encounters_added=len(payload.words), meanings_added=meanings_added, family_members_added=family_added,
    )


def word_to_out(word: models.Word) -> schemas.WordOut:
    return schemas.WordOut(
        id=word.id, uid=word.uid, word=word.word, lemma=word.lemma, phonetic=word.phonetic,
        meanings=[schemas.MeaningIn(pos=m.pos, zh=m.zh) for m in word.meanings],
        word_family=[m.member for m in word.family_members], priority=word.priority, note=word.note,
        encounter_count=len(word.encounters), created_at=word.created_at,
        encounters=[encounter_to_out(e) for e in sorted(word.encounters, key=lambda row: row.occurred_at, reverse=True)],
        review_states=[schemas.ReviewStateOut(
            mode=s.mode, mastery=s.mastery, interval_days=s.interval_days, repetitions=s.repetitions,
            lapses=s.lapses, due_at=s.due_at,
        ) for s in word.review_states],
    )


def encounter_to_out(encounter: models.Encounter) -> schemas.EncounterOut:
    return schemas.EncounterOut(
        id=encounter.id, uid=encounter.uid, vocabulary_uid=encounter.word.uid, lemma=encounter.word.lemma,
        source_id=encounter.source_id, source_name=encounter.source.name,
        source_type=encounter.source.source_type, surface_form=encounter.surface_form,
        context=encounter.context, note=encounter.note, origin=encounter.origin,
        familiarity=encounter.familiarity, marked_unknown=encounter.marked_unknown,
        token_index=encounter.token_index, char_offset=encounter.char_offset,
        external_ref=encounter.external_ref, encountered_at=encounter.encountered_at,
        occurred_at=encounter.occurred_at,
    )


def schedule_review(state: models.ReviewState, rating: int) -> None:
    now = datetime.now(timezone.utc)
    if rating == 0:
        state.repetitions = 0
        state.interval_days = 1
        state.ease_factor = max(1.3, state.ease_factor - 0.2)
        state.lapses += 1
        state.mastery = max(0, state.mastery - 18)
    elif rating == 1:
        state.repetitions = 0
        state.interval_days = 1
        state.ease_factor = max(1.3, state.ease_factor - 0.1)
        state.mastery = max(0, state.mastery - 5)
    else:
        state.repetitions += 1
        if state.repetitions == 1:
            state.interval_days = 1 if rating == 2 else 3
        elif state.repetitions == 2:
            state.interval_days = 4 if rating == 2 else 7
        else:
            bonus = 1.0 if rating == 2 else 1.3
            state.interval_days = max(1, ceil(state.interval_days * state.ease_factor * bonus))
        state.ease_factor = min(3.0, state.ease_factor + (0.0 if rating == 2 else 0.1))
        state.mastery = min(100, state.mastery + (12 if rating == 2 else 20))
    state.last_reviewed_at = now
    state.due_at = now + timedelta(days=state.interval_days)


def start_of_today_utc() -> datetime:
    return datetime.combine(date.today(), time.min, tzinfo=timezone.utc)
