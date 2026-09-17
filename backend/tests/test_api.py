import os
from pathlib import Path

TEST_DB = Path("/tmp/cet4_vocab_test.db")
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"

from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine

Base.metadata.create_all(bind=engine)
client = TestClient(app)


PAYLOAD = {
    "schema_version": 1,
    "source": {"name": "Test Reading", "type": "reading", "date": "2026-09-17"},
    "words": [{
        "word": "contributing", "lemma": "contribute", "phonetic": "/test/",
        "meanings": [{"pos": "v.", "zh": "贡献；导致"}],
        "word_family": ["contribution"], "priority": "high",
        "context": "Factors contributing to change.", "note": "contribute to",
    }],
}


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_import_preview_create_then_merge():
    preview = client.post("/api/import/preview", json=PAYLOAD)
    assert preview.status_code == 200
    assert preview.json()["create_count"] == 1

    result = client.post("/api/import", json=PAYLOAD)
    assert result.status_code == 200
    assert result.json()["created"] == 1

    second_payload = {**PAYLOAD, "source": {"name": "Test Reading 2", "type": "reading", "date": "2026-09-18"}}
    second = client.post("/api/import", json=second_payload)
    assert second.status_code == 200
    assert second.json()["merged"] == 1

    words = client.get("/api/words").json()
    assert len(words) == 1
    assert words[0]["encounter_count"] == 2
    assert words[0]["word_family"] == ["contribution"]


def test_review_channels_are_independent():
    word = client.get("/api/words").json()[0]
    answer = client.post("/api/review/answer", json={"word_id": word["id"], "mode": "visual", "rating": 3})
    assert answer.status_code == 200
    assert answer.json()["mastery"] == 20
    refreshed = client.get(f"/api/words/{word['id']}").json()
    states = {state["mode"]: state for state in refreshed["review_states"]}
    assert states["visual"]["mastery"] == 20
    assert states["audio"]["mastery"] == 0


def test_crud_word():
    response = client.post("/api/words", json={
        "word": "indicate", "lemma": "indicate", "meanings": [{"pos": "v.", "zh": "表明"}],
        "word_family": ["indication"], "priority": "normal",
    })
    assert response.status_code == 201
    word_id = response.json()["id"]
    update = client.put(f"/api/words/{word_id}", json={"note": "常见学术词", "priority": "high"})
    assert update.status_code == 200
    assert update.json()["note"] == "常见学术词"
    assert client.delete(f"/api/words/{word_id}").status_code == 204


def test_common_encounter_api_supports_future_modules():
    source = client.get("/api/sources").json()[0]
    response = client.post("/api/encounters", json={
        "vocabulary": {"word": "capabilities", "lemma": "capability", "meanings": []},
        "source_uid": source["uid"], "origin": "morning_reading", "familiarity": "fuzzy",
        "marked_unknown": True, "context": "We develop our capabilities through practice.",
        "token_index": 4, "char_offset": 15, "external_ref": "passage:future-demo",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["lemma"] == "capability"
    assert data["origin"] == "morning_reading"
    assert data["source_name"] == source["name"]
    assert data["uid"]


def test_review_history_snapshots_and_exports():
    word = next(item for item in client.get("/api/words").json() if item["lemma"] == "contribute")
    state_before = next(item for item in word["review_states"] if item["mode"] == "visual")
    answer = client.post("/api/review/answer", json={
        "word_id": word["id"], "mode": "visual", "rating": 0, "response_time_ms": 1250,
        "encounter_uid": word["encounters"][0]["uid"], "context": "reviewed from a passage",
    })
    assert answer.status_code == 200

    reviews = client.get("/api/export/reviews").json()
    assert reviews["schema_version"] == 1
    latest = reviews["data"][-1]
    assert latest["vocabulary_uid"] == word["uid"]
    assert latest["rating"] == "forgot"
    assert latest["mastery_before"] == state_before["mastery"]
    assert latest["mastery_after"] == answer.json()["mastery"]
    assert latest["response_time_ms"] == 1250

    vocabulary = client.get("/api/export/vocabulary").json()
    assert vocabulary["schema_version"] == 1
    exported_word = next(item for item in vocabulary["data"] if item["lemma"] == "contribute")
    assert exported_word["vocabulary_uid"] == word["uid"]
    assert "last_seen_at" in exported_word
    assert "visual_mastery" in exported_word

    encounters_csv = client.get("/api/export/encounters?format=csv")
    assert encounters_csv.status_code == 200
    assert "encounter_uid" in encounters_csv.text

    backup = client.get("/api/export/all").json()
    assert backup["schema_version"] == 1
    assert {"sources", "vocabulary", "encounters", "review_states", "review_history"} <= backup.keys()
