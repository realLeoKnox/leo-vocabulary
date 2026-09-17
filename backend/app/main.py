from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from . import export_service, models, schemas, services
from .config import ensure_sqlite_directory, settings
from .database import Base, engine, get_db

ensure_sqlite_directory()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Alembic is used in Docker/production; create_all keeps local first-run development friendly.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name, version="0.1.0", openapi_url="/api/openapi.json",
    docs_url="/api/docs", lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/words", response_model=list[schemas.WordOut])
def list_words(
    q: str | None = None, priority: str | None = None, source_id: int | None = None,
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db),
):
    stmt = select(models.Word).where(models.Word.archived_at.is_(None)).options(*services.WORD_LOAD).order_by(models.Word.created_at.desc())
    if q:
        pattern = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(models.Word.word.ilike(pattern), models.Word.lemma.ilike(pattern)))
    if priority:
        stmt = stmt.where(models.Word.priority == priority)
    if source_id:
        stmt = stmt.join(models.Encounter).where(models.Encounter.source_id == source_id).distinct()
    words = db.scalars(stmt.offset(offset).limit(limit)).unique().all()
    return [services.word_to_out(word) for word in words]


@app.get("/api/words/{word_id}", response_model=schemas.WordOut)
def get_word(word_id: int, db: Session = Depends(get_db)):
    word = db.scalar(select(models.Word).options(*services.WORD_LOAD).where(models.Word.id == word_id))
    if not word:
        raise HTTPException(404, "词条不存在")
    return services.word_to_out(word)


@app.post("/api/words", response_model=schemas.WordOut, status_code=201)
def create_word(payload: schemas.WordCreate, db: Session = Depends(get_db)):
    if db.scalar(select(models.Word.id).where(models.Word.lemma == payload.lemma, models.Word.archived_at.is_(None))):
        raise HTTPException(409, "该 lemma 已存在，请编辑现有词条或通过导入增加遭遇记录")
    source = None
    if payload.source_id:
        source = db.get(models.Source, payload.source_id)
        if not source:
            raise HTTPException(404, "来源不存在")
    else:
        source, _ = services.get_or_create_source(db, schemas.SourceIn(name="手动添加", type="other", date=date.today()))
    occurred_at = datetime.combine(payload.encountered_at or date.today(), datetime.min.time(), tzinfo=timezone.utc)
    services.record_vocabulary_encounter(
        db, item=payload, source=source, context=payload.context, encounter_note=payload.note,
        origin="manual", familiarity="unknown", marked_unknown=True, occurred_at=occurred_at,
    )
    db.commit()
    word = db.scalar(select(models.Word).options(*services.WORD_LOAD).where(models.Word.lemma == payload.lemma))
    return services.word_to_out(word)


@app.put("/api/words/{word_id}", response_model=schemas.WordOut)
def update_word(word_id: int, payload: schemas.WordUpdate, db: Session = Depends(get_db)):
    word = db.scalar(select(models.Word).options(*services.WORD_LOAD).where(models.Word.id == word_id))
    if not word:
        raise HTTPException(404, "词条不存在")
    data = payload.model_dump(exclude_unset=True)
    if "lemma" in data:
        lemma = data["lemma"].strip().lower()
        conflict = db.scalar(select(models.Word.id).where(models.Word.lemma == lemma, models.Word.id != word_id))
        if conflict:
            raise HTTPException(409, "该 lemma 已被其他词条使用")
        word.lemma = lemma
    for field in ("word", "phonetic", "priority", "note"):
        if field in data:
            setattr(word, field, data[field].strip().lower() if field == "word" and data[field] else data[field])
    if payload.meanings is not None:
        word.meanings.clear()
        for index, item in enumerate(payload.meanings):
            word.meanings.append(models.Meaning(pos=item.pos.strip(), zh=item.zh.strip(), position=index))
    if payload.word_family is not None:
        word.family_members.clear()
        for member in dict.fromkeys(m.strip().lower() for m in payload.word_family if m.strip()):
            if member != word.lemma:
                word.family_members.append(models.WordFamilyMember(member=member))
    db.commit()
    db.refresh(word)
    word = db.scalar(select(models.Word).options(*services.WORD_LOAD).where(models.Word.id == word_id))
    return services.word_to_out(word)


@app.delete("/api/words/{word_id}", status_code=204)
def delete_word(word_id: int, db: Session = Depends(get_db)):
    word = db.get(models.Word, word_id)
    if not word:
        raise HTTPException(404, "词条不存在")
    word.archived_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=204)


@app.get("/api/sources", response_model=list[schemas.SourceOut])
def list_sources(db: Session = Depends(get_db)):
    rows = db.execute(
        select(models.Source, func.count(models.Encounter.id)).outerjoin(models.Encounter)
        .where(models.Source.archived_at.is_(None))
        .group_by(models.Source.id).order_by(models.Source.created_at.desc())
    ).all()
    return [schemas.SourceOut(
        id=source.id, uid=source.uid, name=source.name, type=source.source_type, date=source.source_date,
        description=source.description, encounter_count=count, created_at=source.created_at,
    ) for source, count in rows]


@app.post("/api/sources", response_model=schemas.SourceOut, status_code=201)
def create_source(payload: schemas.SourceCreate, db: Session = Depends(get_db)):
    source, created = services.get_or_create_source(db, payload)
    if not created:
        raise HTTPException(409, "相同名称、类型和日期的来源已存在")
    db.commit()
    return schemas.SourceOut(id=source.id, uid=source.uid, name=source.name, type=source.source_type, date=source.source_date,
                             description=source.description, encounter_count=0, created_at=source.created_at)


@app.delete("/api/sources/{source_id}", status_code=204)
def delete_source(source_id: int, db: Session = Depends(get_db)):
    source = db.get(models.Source, source_id)
    if not source:
        raise HTTPException(404, "来源不存在")
    source.archived_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=204)


@app.post("/api/import/preview", response_model=schemas.ImportPreview)
def import_preview(payload: schemas.ImportPayload, db: Session = Depends(get_db)):
    return services.preview_import(db, payload)


@app.post("/api/import", response_model=schemas.ImportResult)
def import_words(payload: schemas.ImportPayload, db: Session = Depends(get_db)):
    return services.run_import(db, payload)


@app.post("/api/encounters", response_model=schemas.EncounterOut, status_code=201)
def create_encounter(payload: schemas.EncounterCreate, db: Session = Depends(get_db)):
    """Shared entry point for future reader, morning-reading, and other learning modules."""
    try:
        source = services.resolve_source(
            db, source_id=payload.source_id, source_uid=payload.source_uid, source=payload.source
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    _, encounter, _, _, _ = services.record_vocabulary_encounter(
        db, item=payload.vocabulary, source=source, context=payload.context,
        encounter_note=payload.note, origin=payload.origin, familiarity=payload.familiarity,
        marked_unknown=payload.marked_unknown, token_index=payload.token_index,
        char_offset=payload.char_offset, external_ref=payload.external_ref,
        occurred_at=payload.occurred_at,
    )
    db.commit()
    encounter = db.scalar(
        select(models.Encounter).options(
            selectinload(models.Encounter.word), selectinload(models.Encounter.source)
        ).where(models.Encounter.id == encounter.id)
    )
    return services.encounter_to_out(encounter)


@app.get("/api/review/queue", response_model=list[schemas.WordOut])
def review_queue(mode: schemas.ReviewMode = "visual", limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    stmt = (
        select(models.Word).join(models.ReviewState)
        .where(models.ReviewState.mode == mode, models.ReviewState.due_at <= now, models.Word.archived_at.is_(None))
        .options(*services.WORD_LOAD).order_by(models.ReviewState.due_at, models.Word.created_at).limit(limit)
    )
    return [services.word_to_out(word) for word in db.scalars(stmt).unique().all()]


@app.post("/api/review/answer", response_model=schemas.ReviewStateOut)
def review_answer(payload: schemas.ReviewSubmit, db: Session = Depends(get_db)):
    state = db.scalar(select(models.ReviewState).where(
        models.ReviewState.word_id == payload.word_id, models.ReviewState.mode == payload.mode
    ))
    if not state:
        raise HTTPException(404, "复习状态不存在")
    encounter = None
    if payload.encounter_uid:
        encounter = db.scalar(select(models.Encounter).where(models.Encounter.uid == payload.encounter_uid))
        if not encounter:
            raise HTTPException(404, "关联的遭遇记录不存在")
    mastery_before = state.mastery
    interval_before = state.interval_days
    services.schedule_review(state, payload.rating)
    db.add(models.ReviewLog(
        word_id=payload.word_id, mode=payload.mode, rating=payload.rating,
        mastery_before=mastery_before, mastery_after=state.mastery,
        interval_before=interval_before, interval_after=state.interval_days,
        next_review_at=state.due_at, response_time_ms=payload.response_time_ms,
        encounter=encounter, context=payload.context,
    ))
    db.commit()
    db.refresh(state)
    return schemas.ReviewStateOut(mode=state.mode, mastery=state.mastery, interval_days=state.interval_days,
                                  repetitions=state.repetitions, lapses=state.lapses, due_at=state.due_at)


@app.get("/api/dashboard", response_model=schemas.DashboardStats)
def dashboard(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    due_today = db.scalar(select(func.count(models.ReviewState.id)).where(models.ReviewState.due_at <= now)) or 0
    new_words = db.scalar(select(func.count(models.Word.id)).where(
        models.Word.created_at >= week_ago, models.Word.archived_at.is_(None)
    )) or 0
    total_words = db.scalar(select(func.count(models.Word.id)).where(models.Word.archived_at.is_(None))) or 0
    mastered = db.scalar(
        select(func.count(func.distinct(models.Word.id))).join(models.ReviewState)
        .where(models.ReviewState.mode == "visual", models.ReviewState.mastery >= 80, models.Word.archived_at.is_(None))
    ) or 0
    source_rows = db.execute(
        select(models.Source, func.count(models.Encounter.id)).outerjoin(models.Encounter)
        .where(models.Source.archived_at.is_(None))
        .group_by(models.Source.id).order_by(models.Source.created_at.desc()).limit(5)
    ).all()
    stubborn_rows = db.execute(
        select(models.Word.id, models.Word.word, models.Word.lemma, func.sum(models.ReviewState.lapses).label("lapses"))
        .join(models.ReviewState).where(models.Word.archived_at.is_(None)).group_by(models.Word.id).order_by(func.sum(models.ReviewState.lapses).desc(), models.Word.created_at)
        .limit(8)
    ).all()
    return schemas.DashboardStats(
        due_today=due_today, new_words=new_words, mastered=mastered, total_words=total_words,
        recent_sources=[{"id": s.id, "name": s.name, "type": s.source_type, "date": s.source_date, "count": count}
                        for s, count in source_rows],
        stubborn_words=[{"id": row.id, "word": row.word, "lemma": row.lemma, "lapses": row.lapses or 0}
                        for row in stubborn_rows if (row.lapses or 0) > 0],
    )


def _export_response(export_type: str, rows: list[dict], export_format: str):
    if export_format == "csv":
        return PlainTextResponse(
            export_service.to_csv(rows), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{export_type}-v1.csv"'},
        )
    return export_service.envelope(export_type, rows)


@app.get("/api/export/vocabulary")
def export_vocabulary(
    format: str = Query("json", pattern="^(json|csv)$"), db: Session = Depends(get_db)
):
    return _export_response("vocabulary", export_service.vocabulary_rows(db), format)


@app.get("/api/export/reviews")
def export_reviews(
    format: str = Query("json", pattern="^(json|csv)$"), date_from: date | None = None,
    date_to: date | None = None, db: Session = Depends(get_db),
):
    return _export_response("review_history", export_service.review_rows(db, date_from, date_to), format)


@app.get("/api/export/encounters")
def export_encounters(
    format: str = Query("json", pattern="^(json|csv)$"), date_from: date | None = None,
    date_to: date | None = None, db: Session = Depends(get_db),
):
    return _export_response("encounter_history", export_service.encounter_rows(db, date_from, date_to), format)


@app.get("/api/export/statistics")
def export_statistics(
    format: str = Query("json", pattern="^(json|csv)$"), date_from: date | None = None,
    date_to: date | None = None, db: Session = Depends(get_db),
):
    rows = [export_service.statistics(db, date_from, date_to)]
    return _export_response("statistics", rows, format)


@app.get("/api/export/all")
def export_all(db: Session = Depends(get_db)):
    return export_service.export_all(db)


# Direct deployment: serve the production Vue build from the same process.
# Docker leaves FRONTEND_DIST unset and continues to use the dedicated Nginx container.
if settings.frontend_dist:
    frontend_path = Path(settings.frontend_dist).expanduser().resolve()
    if not frontend_path.is_dir():
        raise RuntimeError(f"FRONTEND_DIST does not exist or is not a directory: {frontend_path}")
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
