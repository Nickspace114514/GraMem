import pytest
from test_engine import CONTACT, OWNER, FakeGraph, FakeModel, item

from gramem.config import Config
from gramem.engine import Engine
from gramem.migrate import import_records
from gramem.tokens import compact


class Reviewer(FakeModel):
    def __init__(self, approved=True):
        super().__init__()
        self.approved = approved
        self.payloads = []

    def extract(self, prompt, payload):
        self.calls += 1
        self.payloads.append(payload)
        if self.before_return:
            self.before_return()
        return {
            "decisions": [{"id": r["id"], "approved": self.approved} for r in payload["candidates"]]
        }


@pytest.fixture
def engine(tmp_path):
    e = Engine(tmp_path / "m.sqlite", model=Reviewer(), graph=FakeGraph())
    e.clock = lambda: 10000
    yield e
    e.close()


@pytest.mark.parametrize("kind", ["identity", "occupation", "current_location", "health"])
def test_extraction_performs_final_approval_without_second_model_call(engine, kind):
    fact = {**item("我现在住在新加坡"), "type": kind, "slot": kind}
    engine.model = FakeModel({"memories": [fact]})
    engine.enqueue(OWNER, fact["evidence"], session="s")
    engine.process_one()
    row = engine.list(OWNER)[0]
    assert row["metadata"]["approval"]["mode"] == "llm"
    assert row["metadata"]["approval"]["stage"] == "extraction"
    assert not engine.list(OWNER, status="candidate")
    assert not engine.review_one()
    assert engine.model.calls == 1


def test_automatic_extraction_replaces_singleton_and_graph_atomically(engine):
    old = engine.remember(OWNER, "我住上海", kind="current_location")
    fact = dict(
        item("我现在住新加坡"),
        type="current_location",
        slot="current_location",
        action="SUPERSEDE",
        targets=[old],
        relations=[{"subject": "用户", "predicate": "LIVES_IN", "object": "新加坡"}],
    )
    engine.model = FakeModel({"memories": [fact]})
    engine.enqueue(OWNER, fact["evidence"], session="s")
    engine.process_one()
    assert engine.get(OWNER, old)["status"] == "superseded"
    engine.flush_graph()
    assert engine.graph(OWNER)[0]["object"] == "新加坡"


def test_legacy_candidates_batch_approved_and_only_then_publish_graph(engine):
    ids = [
        engine.remember(
            OWNER,
            f"我叫测试{i}",
            kind="identity",
            confirmed=False,
            metadata={
                "relations": [{"subject": "用户", "predicate": "NAMED", "object": f"测试{i}"}]
            },
        )
        for i in range(3)
    ]
    assert all(engine.get(OWNER, id)["lifecycle"] == "auto_review" for id in ids)
    assert not engine.graph(OWNER)
    assert engine.review_one()
    assert engine.model.calls == 1
    assert len(engine.list(OWNER)) == 3
    engine.flush_graph()
    assert len(engine.graph(OWNER)) == 3
    assert not engine.review_one()
    assert all(engine.get(OWNER, id)["metadata"]["approval"]["approved"] for id in ids)


def test_import_review_is_automatic_and_can_reject(engine):
    import_records(engine, OWNER, [{"text": "用户学习 Python"}])
    engine.model.approved = False
    engine.review_one()
    row = engine.list(OWNER, status="rejected")[0]
    assert row["metadata"]["approval"]["approved"] is False
    assert not engine.list(OWNER, status="candidate")
    assert not engine.recall(OWNER, "Python")["memories"]


def test_reviews_never_mix_principal_scopes(engine):
    engine.remember(OWNER, "Owner 名字", kind="identity", confirmed=False)
    engine.remember(CONTACT, "联系人名字", kind="identity", confirmed=False)
    engine.review_one()
    engine.review_one()
    assert len(engine.model.payloads) == 2
    assert all(len(p["candidates"]) == 1 for p in engine.model.payloads)


def test_failed_model_review_retries_after_restart(engine):
    id = engine.remember(OWNER, "我叫测试", kind="identity", confirmed=False)
    engine.model = FakeModel({"decisions": [{"id": "r0", "approved": "true"}]})
    assert engine.review_one()
    assert not engine.review_one()
    row = engine.get(OWNER, id)
    assert row["metadata"]["auto_review"]["error"] == "invalid_review_schema"
    assert row["status"] == "candidate"
    path = engine.store.path
    engine.close()
    reopened = Engine(path, model=Reviewer(), graph=FakeGraph())
    try:
        reopened.clock = lambda: 10031
        assert reopened.review_one()
        assert reopened.get(OWNER, id)["status"] == "active"
    finally:
        reopened.close()


def test_inflight_review_lease_prevents_duplicate_model_calls(engine):
    engine.remember(OWNER, "测试身份", kind="identity", confirmed=False)
    other = Engine(engine.store.path, model=Reviewer())
    other.clock = engine.clock
    try:
        engine.model.before_return = lambda: assert_no_work(other)
        engine.review_one()
        assert other.model.calls == 0
    finally:
        other.close()


def assert_no_work(engine):
    assert not engine.review_one()


def test_dead_review_lease_recovers(engine):
    id = engine.remember(OWNER, "测试身份", kind="identity", confirmed=False)
    with engine.store.transaction() as db:
        row = engine._visible(db, OWNER, id)
        row["metadata"]["auto_review"] = {"lease": "crashed", "attempts": 1, "retry_at": 10300}
        db.execute("UPDATE memories SET metadata=? WHERE id=?", (compact(row["metadata"]), id))
    assert not engine.review_one()
    engine.clock = lambda: 10301
    assert engine.review_one()
    assert engine.get(OWNER, id)["status"] == "active"


def test_forgetting_during_llm_approval_never_resurrects(engine):
    id = engine.remember(OWNER, "测试身份", kind="identity", slot="name", confirmed=False)
    engine.model.before_return = lambda: engine.exclude(OWNER, "name")
    engine.review_one()
    assert (
        engine.store.rows("SELECT status FROM memories WHERE id=?", (id,))[0]["status"]
        == "forgotten"
    )
    assert not engine.list(OWNER)
    assert not engine.graph(OWNER)


def test_target_change_during_review_cannot_replace_newer_fact(engine):
    old = engine.remember(OWNER, "上海", kind="current_location")
    proposal = engine.remember(OWNER, "新加坡", kind="current_location", confirmed=False)
    newest = []
    engine.model.before_return = lambda: newest.append(
        engine.remember(OWNER, "北京", kind="current_location")
    )
    engine.review_one()
    assert engine.get(OWNER, proposal)["status"] == "candidate"
    assert engine.get(OWNER, newest[0])["status"] == "active"
    assert engine.get(OWNER, old)["status"] == "superseded"
    engine.model.before_return = None
    engine.review_one()
    assert engine.get(OWNER, proposal)["status"] == "rejected"
    assert engine.get(OWNER, newest[0])["status"] == "active"


def test_unproven_legacy_candidate_rejected_without_guessing(engine):
    with engine.store.transaction() as db:
        id = engine._insert(db, OWNER, "没有来源的旧身份", "identity", "name", confirmed=False)
    engine.review_one()
    assert engine.get(OWNER, id)["status"] == "rejected"
    assert engine.model.calls == 0


def test_legacy_manual_mode_remains_explicit_opt_out(engine):
    engine.config.auto_approve = False
    id = engine.remember(OWNER, "测试身份", kind="identity", confirmed=False)
    assert engine.get(OWNER, id)["lifecycle"] == "awaiting_confirm"
    assert not engine.review_one()


def test_config_automatic_approval_requires_boolean():
    assert Config().auto_approve is True
    with pytest.raises(ValueError):
        Config(auto_approve="true")
