import pytest
from test_engine import CONTACT, OWNER, FakeGraph, FakeModel

from gramem.documents import ingest
from gramem.engine import Engine
from gramem.migrate import import_exclusions, import_records
from gramem.reflection import consolidate, reflect


@pytest.fixture
def engine(tmp_path):
    e = Engine(tmp_path / "m.sqlite", graph=FakeGraph())
    yield e
    e.close()


def test_import_defaults_to_review_and_does_not_change_existing_fact(engine):
    id = engine.remember(OWNER, "User prefers tea", kind="preference")
    records = [
        {"id": "external-1", "text": "User prefers tea"},
        {"id": "external-2", "text": "User likes Linux"},
    ]
    report = import_records(engine, OWNER, records)
    assert report == {"imported": 1, "duplicate": 1, "skipped": 0, "quarantined": 0}
    assert engine.get(OWNER, id)["status"] == "active"
    assert len(engine.list(OWNER, status="candidate")) == 1
    assert "Linux" not in engine.recall(OWNER, "Linux")["context"]
    assert import_records(engine, OWNER, records)["duplicate"] == 2


def test_import_exclusions_before_data_never_resurrects(engine):
    import_exclusions(engine, OWNER, [{"slot": "communication.detail", "state": "deleted"}])
    result = import_records(
        engine, OWNER, [{"id": "external", "text": "旧用户偏好详细说明"}], review=False
    )
    assert result["quarantined"] == 1
    assert not engine.list(OWNER)


def test_document_import_scoped_retrievable_and_idempotent(engine, tmp_path):
    path = tmp_path / "guide.md"
    path.write_text("GraMem 的关系图存储在独立 FalkorDB 中。事实来源由记忆引擎管理。" * 40)
    result = ingest(engine, OWNER, path)
    assert result["chunks"] >= 2
    before = len(engine.list(OWNER))
    ingest(engine, OWNER, path)
    assert len(engine.list(OWNER)) == before
    assert "FalkorDB" in engine.recall(OWNER, "独立关系图")["context"]
    assert not engine.recall(CONTACT, "独立关系图")["context"]


def test_reflection_source_validation_and_erasure(engine):
    a = engine.remember(
        OWNER, "User prefers concise explanations", kind="preference", slot="detail"
    )
    b = engine.remember(OWNER, "User prefers concise reports", kind="preference", slot="reports")
    engine.model = FakeModel(
        {
            "stable_patterns": [
                {"fact": "User consistently prefers concise writing", "source_ids": [a, b]}
            ]
        }
    )
    assert reflect(engine, OWNER)["stable_patterns"]
    engine.exclude(OWNER, "detail")
    assert all(r["content"] == "{}" for r in engine.store.rows("SELECT content FROM profiles"))


def test_reflection_cannot_invent_pattern_from_one_source(engine):
    a = engine.remember(OWNER, "User prefers concise explanations", kind="preference")
    engine.model = FakeModel(
        {"stable_patterns": [{"fact": "Unsupported broad personality", "source_ids": [a]}]}
    )
    with pytest.raises(ValueError):
        reflect(engine, OWNER)
    assert not engine.store.rows("SELECT * FROM profiles")


def test_consolidation_preserves_history_and_targets_same_slot(engine):
    a = engine.remember(
        OWNER, "User prefers concise explanations", kind="preference", slot="detail"
    )
    b = engine.remember(OWNER, "User prefers clear explanations", kind="preference", slot="detail")
    engine.model = FakeModel(
        {"merges": [{"ids": [a, b], "content": "User prefers concise and clear explanations"}]}
    )
    assert consolidate(engine, OWNER) == 1
    assert len(engine.list(OWNER)) == 1
    assert len(engine.list(OWNER, status="superseded")) == 2


def test_exclusion_semantics_fail_closed_when_model_omits_check(engine):
    engine.exclude(OWNER, "communication.detail")
    candidate = {
        "type": "preference",
        "slot": "renamed.detail",
        "content": "User likes long explanations",
        "evidence": "User likes long explanations",
        "confidence": 0.9,
        "future_use": 0.9,
        "stability": 0.9,
        "personalization": 0.9,
        "uniqueness": 0.9,
    }
    engine.model = FakeModel({"memories": [candidate]})
    engine.enqueue(OWNER, candidate["evidence"], session="s")
    engine.process_one()
    assert not engine.list(OWNER)
    candidate["excluded"] = True
    with engine.store.transaction() as db:
        db.execute("UPDATE sources SET retry_at=0")
    engine.process_one()
    assert not engine.list(OWNER)
    assert engine.store.rows("SELECT content FROM sources")[0]["content"] == ""


def test_weekly_failure_retries_and_new_principal_is_not_delayed(engine):
    from gramem.reflection import weekly

    engine.clock = lambda: 10000
    a = engine.remember(OWNER, "用户偏好简短说明", kind="preference")
    engine.model = FakeModel({"stable_patterns": [{"fact": "不受支持的模式", "source_ids": [a]}]})
    weekly(engine)
    assert engine.store.rows("SELECT action FROM events WHERE action='weekly_failed'")
    first = engine.model.calls
    weekly(engine)
    assert engine.model.calls == first
    b = engine.remember(CONTACT, "联系人喜欢茶", kind="preference")
    engine.model.result = {"interests": [{"fact": "喜欢茶", "source_ids": [b]}]}
    weekly(engine)
    assert engine.model.calls == first + 1
    engine.clock = lambda: 14000
    engine.model.result = {"communication": [{"fact": "偏好简短说明", "source_ids": [a]}]}
    weekly(engine)
    assert engine.model.calls == first + 2
