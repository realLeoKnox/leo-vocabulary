from __future__ import annotations

import csv
import json
from datetime import date, datetime, time, timezone
from io import StringIO
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import models
from .services import WORD_LOAD


EXPORT_SCHEMA_VERSION = 1
RATING_NAMES = {0: "forgot", 1: "fuzzy", 2: "know", 3: "instant"}


def _iso(value):
    return value.isoformat() if value is not None else None


def vocabulary_rows(db: Session) -> list[dict]:
    words = db.scalars(select(models.Word).options(*WORD_LOAD).order_by(models.Word.lemma)).unique().all()
    rows = []
    for word in words:
        states = {state.mode: state for state in word.review_states}
        visual = states.get("visual")
        audio = states.get("audio")
        mastery_values = [state.mastery for state in word.review_states]
        last_seen = max((e.occurred_at for e in word.encounters), default=None)
        next_review = min((s.due_at for s in word.review_states), default=None)
        source_map = {}
        for encounter in word.encounters:
            source_map[encounter.source.uid] = {
                "uid": encounter.source.uid, "name": encounter.source.name,
                "type": encounter.source.source_type, "date": _iso(encounter.source.source_date),
            }
        rows.append({
            "vocabulary_uid": word.uid, "word": word.word, "lemma": word.lemma,
            "phonetic": word.phonetic,
            "meanings": [{"pos": meaning.pos, "zh": meaning.zh} for meaning in word.meanings],
            "word_family": [member.member for member in word.family_members],
            "priority": word.priority,
            "mastery": round(sum(mastery_values) / len(mastery_values)) if mastery_values else 0,
            "visual_mastery": visual.mastery if visual else 0,
            "audio_mastery": audio.mastery if audio else 0,
            "encounter_count": len(word.encounters), "created_at": _iso(word.created_at),
            "archived_at": _iso(word.archived_at),
            "last_seen_at": _iso(last_seen), "next_review_at": _iso(next_review),
            "tags": [], "notes": word.note, "sources": list(source_map.values()),
        })
    return rows


def review_rows(db: Session, date_from: date | None = None, date_to: date | None = None) -> list[dict]:
    stmt = select(models.ReviewLog).options(
        selectinload(models.ReviewLog.word), selectinload(models.ReviewLog.encounter)
    ).order_by(models.ReviewLog.reviewed_at)
    stmt = _apply_datetime_range(stmt, models.ReviewLog.reviewed_at, date_from, date_to)
    logs = db.scalars(stmt).all()
    return [{
        "review_uid": log.uid, "vocabulary_uid": log.word.uid, "lemma": log.word.lemma,
        "reviewed_at": _iso(log.reviewed_at), "review_mode": log.mode,
        "rating": RATING_NAMES.get(log.rating, str(log.rating)),
        "mastery_before": log.mastery_before, "mastery_after": log.mastery_after,
        "interval_before": log.interval_before, "interval_after": log.interval_after,
        "next_review_at": _iso(log.next_review_at), "response_time_ms": log.response_time_ms,
        "encounter_uid": log.encounter.uid if log.encounter else None, "context": log.context,
    } for log in logs]


def encounter_rows(db: Session, date_from: date | None = None, date_to: date | None = None) -> list[dict]:
    stmt = select(models.Encounter).options(
        selectinload(models.Encounter.word), selectinload(models.Encounter.source)
    ).order_by(models.Encounter.occurred_at)
    stmt = _apply_datetime_range(stmt, models.Encounter.occurred_at, date_from, date_to)
    encounters = db.scalars(stmt).all()
    return [{
        "encounter_uid": row.uid, "vocabulary_uid": row.word.uid, "lemma": row.word.lemma,
        "surface_form": row.surface_form, "occurred_at": _iso(row.occurred_at),
        "origin": row.origin, "familiarity": row.familiarity,
        "marked_unknown": row.marked_unknown, "first_marked_at": _iso(row.first_marked_at),
        "context": row.context, "note": row.note,
        "token_index": row.token_index, "char_offset": row.char_offset,
        "external_ref": row.external_ref,
        "source": {"uid": row.source.uid, "name": row.source.name, "type": row.source.source_type,
                   "date": _iso(row.source.source_date)},
    } for row in encounters]


def source_rows(db: Session) -> list[dict]:
    sources = db.scalars(select(models.Source).order_by(models.Source.created_at)).all()
    return [{
        "source_uid": source.uid, "name": source.name, "type": source.source_type,
        "date": _iso(source.source_date), "description": source.description,
        "created_at": _iso(source.created_at), "archived_at": _iso(source.archived_at),
    } for source in sources]


def review_state_rows(db: Session) -> list[dict]:
    states = db.scalars(select(models.ReviewState).options(selectinload(models.ReviewState.word))).all()
    return [{
        "vocabulary_uid": state.word.uid, "lemma": state.word.lemma, "mode": state.mode,
        "ease_factor": state.ease_factor, "interval_days": state.interval_days,
        "repetitions": state.repetitions, "lapses": state.lapses, "mastery": state.mastery,
        "due_at": _iso(state.due_at), "last_reviewed_at": _iso(state.last_reviewed_at),
    } for state in states]


def statistics(db: Session, date_from: date | None = None, date_to: date | None = None) -> dict:
    reviews = review_rows(db, date_from, date_to)
    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from else None
    end = datetime.combine(date_to, time.max, tzinfo=timezone.utc) if date_to else None
    word_stmt = select(models.Word)
    if start:
        word_stmt = word_stmt.where(models.Word.created_at >= start)
    if end:
        word_stmt = word_stmt.where(models.Word.created_at <= end)
    new_words = len(db.scalars(word_stmt).all())
    all_states = db.scalars(select(models.ReviewState)).all()
    visual = [row for row in reviews if row["review_mode"] == "visual"]
    audio = [row for row in reviews if row["review_mode"] == "audio"]
    reading = [row for row in reviews if row["review_mode"] == "reading"]

    def accuracy(items: list[dict]):
        return round(sum(item["rating"] in ("know", "instant") for item in items) / len(items), 4) if items else None

    return {
        "date_from": _iso(date_from), "date_to": _iso(date_to), "new_words": new_words,
        "reviews": len(reviews),
        "mastered_words": len({state.word_id for state in all_states if state.mastery >= 80}),
        "forgotten_words": len({row["vocabulary_uid"] for row in reviews if row["rating"] == "forgot"}),
        "visual_accuracy": accuracy(visual), "audio_accuracy": accuracy(audio),
        "reading_accuracy": accuracy(reading),
        "average_mastery": round(sum(state.mastery for state in all_states) / len(all_states), 2) if all_states else 0,
        "vocabulary_coverage": None,
        "study_days": len({row["reviewed_at"][:10] for row in reviews}),
    }


def export_all(db: Session) -> dict:
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "export_type": "learning_data_backup",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "sources": source_rows(db), "vocabulary": vocabulary_rows(db),
        "encounters": encounter_rows(db), "review_states": review_state_rows(db),
        "review_history": review_rows(db),
    }


def envelope(export_type: str, data) -> dict:
    return {
        "schema_version": EXPORT_SCHEMA_VERSION, "export_type": export_type,
        "exported_at": datetime.now(timezone.utc).isoformat(), "data": data,
    }


def to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for row in rows:
        writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                         for key, value in row.items()})
    return output.getvalue()


def _apply_datetime_range(stmt, column, date_from: date | None, date_to: date | None):
    if date_from:
        stmt = stmt.where(column >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        stmt = stmt.where(column <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    return stmt
