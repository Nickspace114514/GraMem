"""Regressions: unresolved controls and unrelated policy changes must not destroy data."""

import json

from test_engine import OWNER, FakeModel, item
from test_knowledge import library, save  # noqa: F401
from test_provider import make_provider  # noqa: F401


def test_classifier_outage_holds_only_the_current_turn(make_provider):  # noqa: F811
    p = make_provider(chat_type="direct")
    owner = p.config.principal("teams", "verified")
    kept = p.engine.remember(owner, "用户喜欢咖啡", kind="preference", slot="drink")
    p.engine.model.available = False
    p.on_turn_start(1, "忘记我喜欢咖啡这件事", author_id="verified")
    assert p.engine.exclusions(owner) == []
    assert "could not be resolved" in p._control_notice
    # No recall for the held turn, only the notice.
    assert "咖啡" not in p.prefetch("咖啡")
    p.sync_turn("忘记我喜欢咖啡这件事", "好的", turn_author={"id": "verified"})
    assert not p.engine.store.rows("SELECT * FROM sources")
    assert not p.engine.store.rows("SELECT * FROM chat_turns")
    # The next turn is normal again.
    p.engine.model.available = True
    p.on_turn_start(2, "我喜欢什么饮料", author_id="verified")
    assert not p._control_notice
    assert "咖啡" in p.prefetch("咖啡")
    assert p.engine.get(owner, kept)["status"] == "active"


def test_malformed_classification_does_not_pause_memory(make_provider):  # noqa: F811
    p = make_provider(chat_type="direct")
    owner = p.config.principal("teams", "verified")
    p.engine.model = FakeModel({"unexpected": True})
    p.on_turn_start(1, "forget that", author_id="verified")
    assert p.engine.exclusions(owner) == []


def test_dont_forget_is_not_a_memory_control(make_provider):  # noqa: F811
    p = make_provider(chat_type="direct")
    model = FakeModel({"request": False})
    p.engine.model = model
    for turn, text in enumerate(["别忘记我的生日是三月", "不要忘了明天开会", "Don't forget my flight"]):
        p.on_turn_start(turn, text, author_id="verified")
    assert model.calls == 0
    p.on_turn_start(9, "别忘了买牛奶，另外忘记我的旧地址", author_id="verified")
    assert model.calls == 1


def test_unrelated_suppression_keeps_queued_conversation(tmp_path):
    from test_engine import Engine, FakeGraph

    from gramem.config import Config

    engine = Engine(tmp_path / "memory.sqlite", Config(), graph=FakeGraph())
    try:
        engine.model = FakeModel({"memories": [item(excluded=False)]})
        source = engine.enqueue(OWNER, "我偏好简短解释", session="s", turn="1")
        engine.exclude(OWNER, "unrelated.slot", state="suppressed")
        assert engine.process_one()
        row = engine.store.rows("SELECT status,content FROM sources WHERE id=?", (source,))[0]
        assert row["status"] == "done"
        assert engine.recall(OWNER, "简短解释")["memories"]
    finally:
        engine.close()


def test_reactivation_after_queueing_stays_fail_closed(tmp_path):
    from test_engine import Engine, FakeGraph

    from gramem.config import Config

    engine = Engine(tmp_path / "memory.sqlite", Config(), graph=FakeGraph())
    try:
        engine.exclude(OWNER, "drink", state="suppressed")
        engine.model = FakeModel({"memories": [item()]})
        source = engine.enqueue(OWNER, "我偏好简短解释", session="s", turn="1")
        engine.reactivate(OWNER, "drink")
        assert engine.process_one()
        row = engine.store.rows("SELECT status FROM sources WHERE id=?", (source,))[0]
        assert row["status"] == "redacted"
    finally:
        engine.close()


def test_unrelated_control_during_parse_requeues_document(library, monkeypatch):  # noqa: F811
    from gramem import knowledge

    doc = save(library, defer=True)
    original = knowledge.extract
    calls = []

    def suppress_other(data, suffix, **kwargs):
        if not calls:
            library.engine.exclude(OWNER, "unrelated.slot", state="suppressed")
        calls.append(1)
        return original(data, suffix)

    monkeypatch.setattr(knowledge, "extract", suppress_other)
    assert library.process_one()
    row = library.store.rows("SELECT status,name FROM knowledge_documents WHERE id=?", (doc["id"],))[0]
    assert row["status"] == "queued" and row["name"]
    assert library.blob(doc["id"]).exists()
    assert library.process_one()
    row = library.store.rows("SELECT status FROM knowledge_documents WHERE id=?", (doc["id"],))[0]
    assert row["status"] == "ready"
    assert library.search(OWNER, "关系图")["items"]
    assert len(calls) == 2


def test_lease_takeover_does_not_block_document(library, monkeypatch):  # noqa: F811
    from gramem import knowledge

    doc = save(library, defer=True)
    original = knowledge.extract

    def steal(data, suffix, **kwargs):
        with library.store.transaction() as db:
            db.execute("UPDATE knowledge_documents SET lease=lease+1 WHERE id=?", (doc["id"],))
        return original(data, suffix)

    monkeypatch.setattr(knowledge, "extract", steal)
    assert library.process_one()
    row = library.store.rows("SELECT status,name FROM knowledge_documents WHERE id=?", (doc["id"],))[0]
    assert row["status"] == "processing" and row["name"]
    assert library.blob(doc["id"]).exists()
    assert json.dumps(row)  # row is plain data
