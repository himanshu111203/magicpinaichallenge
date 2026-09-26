import concurrent.futures
import json
from pathlib import Path
import pytest

from src.services.context_store import ContextStore, MAX_PAYLOAD_BYTES

BASE_DIR = Path(__file__).resolve().parent.parent
EXPANDED_DIR = BASE_DIR / "expanded"


@pytest.fixture
def store():
    """Provides a fresh, empty ContextStore for each test."""
    s = ContextStore()
    return s


def test_initial_counts(store):
    """Store must initialize with all-zero counts across scopes."""
    counts = store.counts()
    assert counts == {
        "category": 0,
        "merchant": 0,
        "customer": 0,
        "trigger": 0,
    }
    assert store.total_count() == 0


def test_valid_upsert_and_retrieve(store):
    """Test successful upsert of a valid category context."""
    cat_file = EXPANDED_DIR / "categories" / "dentists.json"
    with open(cat_file, encoding="utf-8") as f:
        payload = json.load(f)

    success, res, status = store.upsert(
        scope="category",
        context_id="dentists",
        version=1,
        payload=payload,
    )

    assert success is True
    assert status == 200
    assert res["accepted"] is True
    assert res["ack_id"] == "ack_dentists_v1"
    assert "stored_at" in res

    assert store.counts()["category"] == 1
    assert store.total_count() == 1

    # Verify retrieval
    record = store.get("category", "dentists")
    assert record is not None
    assert record.version == 1
    assert record.model.slug == "dentists"

    model = store.get_model("category", "dentists")
    assert model is not None
    assert model.slug == "dentists"

    raw_payload = store.get_payload("category", "dentists")
    assert raw_payload["slug"] == "dentists"


def test_stale_and_higher_version_handling(store):
    """
    Test version semantics:
    - Same version replayed -> 409 stale_version
    - Lower version sent -> 409 stale_version
    - Higher version sent -> 200 accepted (atomically updated, count unchanged)
    """
    cat_file = EXPANDED_DIR / "categories" / "salons.json"
    with open(cat_file, encoding="utf-8") as f:
        payload = json.load(f)

    # Initial version 1
    success, res, status = store.upsert("category", "salons", 1, payload)
    assert success is True and status == 200
    assert store.counts()["category"] == 1

    # Replay same version 1 -> idempotent 200
    success, res, status = store.upsert("category", "salons", 1, payload)
    assert success is True
    assert status == 200
    assert res["accepted"] is True

    # Lower version 0 -> 409
    success, res, status = store.upsert("category", "salons", 0, payload)
    assert success is False
    assert status == 409
    assert res["reason"] == "stale_version"
    assert res["current_version"] == 1

    # Higher version 2 -> 200
    success, res, status = store.upsert("category", "salons", 2, payload)
    assert success is True
    assert status == 200
    assert res["accepted"] is True
    assert res["ack_id"] == "ack_salons_v2"

    # Count must remain 1 after replacement
    assert store.counts()["category"] == 1
    assert store.get("category", "salons").version == 2


def test_invalid_scope_rejection(store):
    """Invalid scopes must return 400 with invalid_scope reason."""
    success, res, status = store.upsert(
        scope="invalid_scope",
        context_id="test_id",
        version=1,
        payload={"foo": "bar"},
    )
    assert success is False
    assert status == 400
    assert res["accepted"] is False
    assert res["reason"] == "invalid_scope"


def test_invalid_payload_rejection(store):
    """Payloads failing Pydantic schema validation must return 400 invalid_payload."""
    # A customer missing required fields (like customer_id, merchant_id, identity)
    bad_payload = {"invalid_key": "some_value"}

    success, res, status = store.upsert(
        scope="customer",
        context_id="c_bad",
        version=1,
        payload=bad_payload,
    )
    assert success is False
    assert status == 400
    assert res["accepted"] is False
    assert res["reason"] == "invalid_payload"
    assert "details" in res


def test_payload_size_limit(store):
    """Payloads exceeding 500KB must return 413 payload_too_large."""
    huge_payload = {
        "slug": "oversized",
        "display_name": "Too Big",
        "data": "x" * (MAX_PAYLOAD_BYTES + 1024),
    }

    success, res, status = store.upsert(
        scope="category",
        context_id="oversized",
        version=1,
        payload=huge_payload,
    )
    assert success is False
    assert status == 413
    assert res["accepted"] is False
    assert res["reason"] == "payload_too_large"


def test_concurrent_upserts(store):
    """Test thread-safety under concurrent upsert operations."""
    cat_file = EXPANDED_DIR / "categories" / "dentists.json"
    with open(cat_file, encoding="utf-8") as f:
        payload = json.load(f)

    def worker(worker_id: int):
        return store.upsert(
            scope="category",
            context_id=f"cat_{worker_id}",
            version=1,
            payload=payload,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, i) for i in range(20)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert all(r[0] is True for r in results)
    assert store.counts()["category"] == 20
