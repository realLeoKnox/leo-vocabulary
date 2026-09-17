# Architecture and extension boundaries

## Current domains

The application intentionally keeps four concepts separate:

1. **Vocabulary (`Word`)** — one personal entry per normalized `lemma`; meanings and family members enrich this entry.
2. **Provenance (`Source`)** — a generic named source. Its `source_type` is an open string, so future modules do not require a database enum migration.
3. **Learning events (`Encounter`, `ReviewLog`)** — append-only facts about seeing a word and reviewing it. Counts and dashboard values are derived from events; they are not the only copy of history.
4. **Current scheduling state (`ReviewState`)** — the mutable projection used to build review queues. It is separate from immutable review history.

Database integer IDs remain internal. `uid` values are stable external identities used by exports and cross-module API calls. Vocabulary and sources use soft deletion (`archived_at`) so explicit UI deletion does not erase encounter or review history.

## Service boundaries

`services.upsert_vocabulary` creates or enriches a lemma without knowing the input channel.

`services.record_encounter` writes one encounter event without changing vocabulary metadata.

`services.record_vocabulary_encounter` composes those operations. JSON import, manual creation, and `POST /api/encounters` all use it. A reader or morning-reading module should call the same operation instead of reproducing merge rules.

`services.schedule_review` only updates scheduling state. The review API records before/after snapshots in `ReviewLog`, keeping analytics independent of the scheduling algorithm.

`export_service` owns stable JSON/CSV projections. Frontend components should download these APIs rather than serialize UI state.

## Future Document module

Recommended first migration:

```text
Document
  id, uid, title, document_type, source_id?, exam_date?, set_number?, metadata, created_at

Passage
  id, uid, document_id, section, title?, content, order_index, metadata, created_at

WordOccurrence
  id, uid, passage_id, surface_form, normalized_form, vocabulary_id?,
  token_index?, char_start?, char_end?, context?
```

`WordOccurrence` should describe text structure, including words the user never marked. `Encounter` should remain a learning event. When the user marks a token, add nullable `word_occurrence_id` to `Encounter` and write through `record_vocabulary_encounter`. This separation makes passage coverage calculation possible without manufacturing encounters for every token.

A `Document` may reference a `Source`. Imported document encounters should use that source and `origin=reading` or `origin=morning_reading`. The current `external_ref` field is a lightweight bridge for importers before `WordOccurrence` exists; it is not a substitute for the future foreign key.

Morning reading should use `Document.document_type=morning_reading`, ordinary passages, and a future `PassageTargetWord` association. Reading progress belongs in a user progress/event table, not in `Document` or `Word`.

## Coverage projection

Coverage should be a query/projection over `WordOccurrence`, `Word`, and `ReviewState`, not stored on vocabulary rows. A first version can classify unique normalized tokens as:

- mastered: relevant mastery threshold reached;
- learning: vocabulary entry exists but is below the threshold;
- unknown: no vocabulary entry or explicitly marked unknown;
- newly marked: encounter created during the current reading session.

The denominator policy (tokens versus unique lemmas, stop words, punctuation, proper nouns, and inflections) must be fixed before implementing the percentage.

## Data portability

Export schema v1 uses stable UIDs and ISO timestamps. Available endpoints:

- `GET /api/export/vocabulary?format=json|csv`
- `GET /api/export/reviews?format=json|csv&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`
- `GET /api/export/encounters?format=json|csv&date_from=...&date_to=...`
- `GET /api/export/statistics?format=json|csv&date_from=...&date_to=...`
- `GET /api/export/all`

`export/all` includes sources, vocabulary, encounter history, review states, and review history. A restore endpoint is intentionally deferred. It should be implemented as a versioned importer that resolves UIDs and runs in a transaction; it must not insert exported database IDs.

## Deliberately deferred decisions

- document metadata JSON shape and indexing strategy;
- tokenization/lemmatization implementation and coverage denominator;
- multi-user ownership keys;
- persistent tag model (export v1 reserves `tags` as an empty list);
- full-backup restore conflict rules;
- TTS, PDF extraction, web crawling, and AI content generation.
