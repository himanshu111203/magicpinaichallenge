import pytest

from src.services.conversation_store import (
    ConversationStore,
    TurnRecord,
    normalize_text,
)


@pytest.fixture
def store():
    s = ConversationStore()
    return s


def test_normalize_text():
    assert normalize_text("  Hello  World! ") == "hello world!"
    assert normalize_text("UPPERCASE\n\tSTRING") == "uppercase string"


def test_create_and_get_conversation(store):
    turn = TurnRecord(from_role="vera", body="Hi Dr. Meera", ts="2026-04-26T10:00:00Z", turn_number=1)
    conv = store.create_conversation(
        conversation_id="conv_001",
        merchant_id="m_001",
        customer_id=None,
        trigger_id="trg_001",
        suppression_key="research:dentists:2026-W17",
        initial_turn=turn,
    )

    assert conv.conversation_id == "conv_001"
    assert len(conv.turns) == 1
    assert conv.turns[0].body == "Hi Dr. Meera"
    assert store.count() == 1

    fetched = store.get("conv_001")
    assert fetched is not None
    assert fetched.merchant_id == "m_001"


def test_has_sent_body_verbatim_detection(store):
    turn1 = TurnRecord(from_role="vera", body="Hello! We noticed a dip in calls.", ts="2026-04-26T10:00:00Z", turn_number=1)
    store.create_conversation("conv_002", "m_002", initial_turn=turn1)

    # Identical body
    assert store.has_sent_body("conv_002", "Hello! We noticed a dip in calls.") is True
    # Minor casing and spacing variations
    assert store.has_sent_body("conv_002", "  hello! we noticed a dip in calls.  ") is True
    # Different body
    assert store.has_sent_body("conv_002", "Different follow up message.") is False


def test_merchant_turns_do_not_count_as_vera_sent_bodies(store):
    turn1 = TurnRecord(from_role="vera", body="Hi there!", ts="2026-04-26T10:00:00Z", turn_number=1)
    turn2 = TurnRecord(from_role="merchant", body="Yes please tell me more.", ts="2026-04-26T10:01:00Z", turn_number=2)

    store.create_conversation("conv_003", "m_003", initial_turn=turn1)
    store.add_turn("conv_003", turn2)

    assert store.has_sent_body("conv_003", "Hi there!") is True
    # Merchant's message was not sent by Vera
    assert store.has_sent_body("conv_003", "Yes please tell me more.") is False


def test_end_conversation(store):
    store.create_conversation("conv_004", "m_004")
    assert store.get("conv_004").status == "active"

    res = store.end_conversation("conv_004")
    assert res is True
    assert store.get("conv_004").status == "ended"
