import pytest

from gramem.config import Config, Principal
from gramem.engine import Engine
from gramem.tokens import count

OWNER = Principal("owner", "owner", "owner", "owner")
CONTACT = Principal("owner", "contact", "email:guest@example.com", "email:guest@example.com")
GROUP = Principal("owner", "group", "teams:g1", "owner")


class FakeModel:
    available = True
    space = "test-vector-v1"
    usage = {}

    def __init__(self, result=None):
        self.result = result or {"memories": []}
        self.calls = 0
        self.before_return = None

    def extract(self, prompt, payload):
        self.calls += 1
        if self.before_return:
            self.before_return()
        return self.result

    def embed(self, text):
        return None

    def close(self):
        pass


class FakeGraph:
    def __init__(self):
        self.items = {}
        self.failed = False

    def apply(self, action, p):
        if self.failed:
            raise ConnectionError("offline")
        if action == "put":
            self.items[p["id"]] = dict(p)
        elif action == "expire":
            for r in self.items.values():
                if r["memory_id"] == p["memory_id"] and r["principal"] == p["principal"]:
                    r["valid_until"] = p["valid_until"]
        else:
            self.items = {
                k: v
                for k, v in self.items.items()
                if v["memory_id"] != p["memory_id"] or v["principal"] != p["principal"]
            }

    def search(self, p, query, **kw):
        return [
            r for r in self.items.values() if r["principal"] == p
            and (
                not kw.get("match_text")
                or any(name.casefold() in query.casefold() for name in (r["subject"], r["object"]))
            )
        ]

    def close(self):
        pass


@pytest.fixture
def engine(tmp_path):
    e = Engine(tmp_path / "memory.sqlite", Config(), graph=FakeGraph())
    yield e
    e.close()


def item(content="我偏好简短解释", **kw):
    return dict(
        type="preference",
        slot="communication.detail",
        content=content,
        evidence=content,
        confidence=0.9,
        future_use=0.9,
        stability=0.9,
        personalization=0.8,
        uniqueness=0.8,
        action="ADD",
        targets=[],
        **kw,
    )


def test_chinese_recall_budget_and_scope(engine):
    private = engine.remember(OWNER, "Hermes 使用独立的关系图数据库", kind="project")
    engine.remember(CONTACT, "Guest prefers tea", kind="preference")
    result = engine.recall(OWNER, "关系图数据库", session="s", turn="1")
    assert private in [r["id"] for r in result["memories"]]
    assert count(result["context"]) <= engine.config.recall_tokens
    assert "Guest" not in result["context"]
    assert "Hermes" not in engine.recall(CONTACT, "关系图数据库")["context"]


def test_one_call_extraction_and_durable_retry(engine):
    m = FakeModel({"memories": [item()]})
    engine.model = m
    source = engine.enqueue(OWNER, "我偏好简短解释", session="s", turn="1")
    assert source == engine.enqueue(OWNER, "我偏好简短解释", session="s", turn="1")
    assert engine.process_one()
    assert m.calls == 1
    assert not engine.process_one()
    assert len(engine.list(OWNER)) == 1
    row = engine.list(OWNER)[0]
    assert row["importance"] == pytest.approx(0.86)
    assert row["strength"] == pytest.approx(0.774)


def test_unsubstantiated_model_memory_rejected(engine):
    candidate = item()
    candidate["evidence"] = "not said"
    engine.model = FakeModel({"memories": [candidate]})
    engine.enqueue(OWNER, "我偏好简短解释", session="s")
    engine.process_one()
    assert engine.list(OWNER) == []
    assert engine.status()["jobs"] == [{"status": "pending", "count": 1}]


def test_invalid_conflict_id_never_mutates_other_scope(engine):
    contact_id = engine.remember(CONTACT, "Guest prefers tea", kind="preference")
    candidate = item()
    candidate.update(action="UPDATE", targets=[contact_id])
    engine.model = FakeModel({"memories": [candidate]})
    engine.enqueue(OWNER, "我偏好简短解释", session="s")
    engine.process_one()
    assert engine.get(CONTACT, contact_id)["status"] == "active"
    assert engine.list(OWNER) == []


def test_high_risk_confirmation_preserves_previous_value(engine):
    engine.config.auto_approve = False
    old = engine.remember(OWNER, "用户目前在上海", kind="current_location")
    candidate = item("用户目前在新加坡")
    candidate.update(
        type="current_location", slot="current_location", action="SUPERSEDE", targets=[old]
    )
    engine.model = FakeModel({"memories": [candidate]})
    engine.enqueue(OWNER, "用户目前在新加坡", session="s")
    engine.process_one()
    assert engine.get(OWNER, old)["status"] == "active"
    proposed = engine.list(OWNER, status="candidate")[0]
    assert proposed["lifecycle"] == "awaiting_confirm"
    engine.confirm(OWNER, proposed["id"])
    assert engine.get(OWNER, old)["status"] == "superseded"
    assert "新加坡" in engine.recall(OWNER, "当前城市")["context"]


def test_history_is_explicit_and_does_not_reinforce(engine):
    old = engine.remember(OWNER, "项目采用 PostgreSQL", kind="project", slot="project.storage")
    engine.remember(
        OWNER,
        "项目采用 SQLite",
        kind="project",
        slot="project.storage",
        action="UPDATE",
        targets=[old],
    )
    assert "PostgreSQL" not in engine.recall(OWNER, "项目数据库")["context"]
    result = engine.recall(OWNER, "项目 PostgreSQL", historical=True)
    assert "PostgreSQL" in result["context"]
    assert engine.get(OWNER, old)["accesses"] == 0


def test_selected_only_retry_safe_reinforcement(engine):
    a = engine.remember(OWNER, "用户偏好简短说明", kind="preference")
    b = engine.remember(OWNER, " unrelated obscure fact ", kind="knowledge")
    engine.recall(OWNER, "解释", session="s", turn="1")
    first = engine.get(OWNER, a)["strength"]
    engine.recall(OWNER, "解释", session="s", turn="1")
    assert engine.get(OWNER, a)["strength"] == first
    assert engine.get(OWNER, a)["accesses"] == 1
    assert engine.get(OWNER, b)["accesses"] == 0
    engine.recall(OWNER, "解释", session="s", turn="2")
    assert engine.get(OWNER, a)["accesses"] == 2


def test_budget_never_truncates_fact_or_reinforces_undelivered_item(engine):
    id = engine.remember(OWNER, "用户偏好 " + "非常详细" * 100, kind="preference")
    result = engine.recall(OWNER, "说明", budget=40)
    assert result["context"] == ""
    assert engine.get(OWNER, id)["accesses"] == 0


def test_forget_scrubs_provenance_profiles_and_pending_graph(engine):
    candidate = item("用户偏好青柠汽水")
    candidate["relations"] = [{"subject": "用户", "predicate": "PREFERS", "object": "青柠汽水"}]
    engine.model = FakeModel({"memories": [candidate]})
    source = engine.enqueue(OWNER, "用户偏好青柠汽水", session="s")
    engine.process_one()
    id = engine.list(OWNER)[0]["id"]
    engine.flush_graph()
    assert engine.graph(OWNER)
    derived = engine.remember(
        OWNER,
        "用户偏好青柠汽水和薄荷茶",
        kind="preference",
        slot="drinks",
        action="MERGE",
        targets=[id],
    )
    assert engine.profile(OWNER)
    engine.exclude(OWNER, "communication.detail")
    assert engine.recall(OWNER, "青柠汽水", historical=True)["context"] == ""
    assert (
        engine.store.rows("SELECT content FROM memories WHERE id=?", (derived,))[0]["content"] == ""
    )
    assert (
        engine.store.rows("SELECT content FROM sources WHERE id=?", (source,))[0]["content"] == ""
    )
    assert engine.profile(OWNER) == {}
    assert engine.graph(OWNER, historical=True) == []
    engine.flush_graph()
    assert engine.graph_backend.items == {}


def test_suppress_is_reversible_but_delete_is_not(engine):
    id = engine.remember(OWNER, "用户喜欢咖啡", kind="preference", slot="drink")
    engine.exclude(OWNER, "drink", state="suppressed")
    assert not engine.recall(OWNER, "咖啡")["context"]
    engine.reactivate(OWNER, "drink")
    assert engine.get(OWNER, id)["content"] == "用户喜欢咖啡"
    engine.exclude(OWNER, "drink")
    with pytest.raises(PermissionError):
        engine.reactivate(OWNER, "drink")
    with pytest.raises(PermissionError):
        engine.remember(OWNER, "用户喜欢茶", kind="preference", slot="drink")
    engine.reactivate(OWNER, "drink", reauthorize=True)
    assert engine.store.rows("SELECT content FROM memories WHERE id=?", (id,))[0]["content"] == ""
    engine.remember(OWNER, "用户喜欢茶", kind="preference", slot="drink")
    assert "咖啡" not in engine.recall(OWNER, "饮料", historical=True)["context"]


def test_forget_wins_race_against_extraction(engine):
    m = FakeModel({"memories": [item()]})
    engine.model = m
    engine.enqueue(OWNER, "我偏好简短解释", session="s")
    m.before_return = lambda: engine.exclude(OWNER, "communication.detail")
    engine.process_one()
    assert engine.list(OWNER) == []
    assert engine.status()["jobs"] == [{"status": "redacted", "count": 1}]


def test_graph_failure_does_not_block_and_stale_graph_filtered(engine):
    id = engine.remember(
        OWNER,
        "A 依赖 B",
        kind="project",
        slot="dependency",
        metadata={"relations": [{"subject": "A", "predicate": "DEPENDS_ON", "object": "B"}]},
    )
    engine.flush_graph()
    engine.graph_backend.failed = True
    engine.exclude(OWNER, "dependency")
    assert engine.flush_graph() == 0
    assert engine.graph(OWNER) == []
    assert engine.status()["graph_pending"] > 0
    assert engine.store.rows("SELECT content FROM memories WHERE id=?", (id,))[0]["content"] == ""
    engine.graph_backend.failed = False
    engine.clock = lambda: 99999999999
    engine.flush_graph()
    assert engine.graph_backend.items == {}


def test_graph_scope_and_temporal_invalidation(engine):
    id = engine.remember(
        OWNER,
        "A 依赖 B",
        kind="project",
        slot="dep",
        metadata={"relations": [{"subject": "A", "predicate": "DEPENDS_ON", "object": "B"}]},
    )
    engine.flush_graph()
    assert len(engine.graph(OWNER)) == 1
    assert engine.graph(CONTACT) == []
    engine.remember(OWNER, "A 依赖 C", kind="project", slot="dep", action="UPDATE", targets=[id])
    assert engine.graph(OWNER) == []
    assert len(engine.graph(OWNER, historical=True)) == 1


def test_project_continuity_and_current_context_are_scoped(engine):
    engine.remember(
        OWNER, "当前项目 GraMem", kind="active_project", metadata={"project_key": "gramem"}
    )
    engine.remember(
        OWNER,
        "下一步验证 Hermes 接入",
        kind="project_next_step",
        metadata={"project_key": "gramem"},
    )
    engine.remember(
        OWNER, "另一个项目保密计划", kind="project_next_step", metadata={"project_key": "other"}
    )
    packet = engine.recall(OWNER, "继续")["context"]
    assert not packet  # Trivial acknowledgement does not pay for recall.
    packet = engine.recall(OWNER, "继续当前任务")["context"]
    assert "Hermes" in packet and "另一个项目" not in packet
    assert engine.recall(CONTACT, "继续当前任务")["context"] == ""


def test_group_requires_owner_and_shared_safe_fact(engine):
    with pytest.raises(PermissionError):
        engine.remember(GROUP, "用户喜欢茶", kind="preference", metadata={"group_safe": True})
    with pytest.raises(PermissionError):
        engine.remember(GROUP, "群项目决定使用 GraMem", kind="decision")
    engine.remember(GROUP, "群项目决定使用 GraMem", kind="decision", metadata={"group_safe": True})
    assert engine.recall(OWNER, "群项目 GraMem")["context"] == ""
    assert engine.recall(GROUP, "群项目 GraMem")["context"]
    assert engine.enqueue(GROUP, "群项目决定使用 GraMem", session="s") is None


def test_decay_archive_and_permanent_memory(engine):
    start = engine.clock()
    engine.clock = lambda: start
    id = engine.remember(OWNER, "用户当前在写代码", kind="current_activity")
    permanent = engine.remember(OWNER, "用户偏好简短说明", kind="preference")
    with engine.store.transaction() as db:
        db.execute("UPDATE memories SET lifecycle='permanent' WHERE id=?", (permanent,))
    engine.clock = lambda: start + 40 * 86400
    engine.maintain()
    assert engine.get(OWNER, id)["status"] == "archived"
    assert engine.get(OWNER, permanent)["strength"] == pytest.approx(0.9)


def test_checkpoint_survives_restart_and_backup(tmp_path):
    path = tmp_path / "m.db"
    e = Engine(path)
    checkpoint = e.checkpoint(
        OWNER,
        [
            {"role": "user", "content": "我偏好简短解释"},
            {"role": "assistant", "content": "建议存秘密"},
        ],
        session="s",
    )
    e.store.backup(tmp_path / "backup.db")
    e.close()
    e = Engine(tmp_path / "backup.db", model=FakeModel({"memories": [item()]}))
    assert e.store.rows("SELECT id FROM checkpoints")[0]["id"] == checkpoint
    assert e.process_one()
    assert len(e.list(OWNER)) == 1
    assert len(e.store.rows("SELECT * FROM sources")) == 1
    e.close()


def test_aliases_only_trusted_transport_config():
    c = Config(owner_id="nick", aliases={"email:nick@example.com": "nick", "teams:uuid": "nick"})
    assert c.principal("email", "NICK@example.com").scope == "owner"
    assert c.principal("teams", "uuid").scope == "owner"
    assert c.principal("email", "guest@example.com").scope == "contact"
    assert c.principal("cli", "").scope == "contact"
    with pytest.raises(PermissionError):
        Principal("nick", "owner", "nick", "guest")


@pytest.mark.parametrize(
    "content", ["api_key=secret-key-123", "password=bad", "-----BEGIN RSA PRIVATE KEY-----"]
)
def test_secrets_never_enter_sources_or_memories(engine, content):
    with pytest.raises(ValueError):
        engine.remember(OWNER, content)
    assert engine.enqueue(OWNER, content, session="s") is None
    assert not engine.store.rows("SELECT * FROM sources")


def test_large_evidence_chunked_and_json_atomic_on_invalid_batch(engine):
    engine.model = FakeModel({"memories": [item(), {"bad": "schema"}]})
    engine.enqueue(OWNER, "我偏好简短解释", session="s")
    engine.process_one()
    assert not engine.list(OWNER)
    large = "有长期价值的项目说明。" * 1000
    engine.enqueue(OWNER, large, session="large")
    chunks = engine.store.rows("SELECT content FROM sources WHERE session='large' ORDER BY rowid")
    assert "".join(r["content"] for r in chunks) == large
    assert all(count(r["content"]) <= engine.config.extraction_input_tokens for r in chunks)


def test_multihop_graph_cannot_traverse_suppressed_bridge(engine):
    bridge = engine.remember(OWNER, "项目连接中间实体", slot="bridge")
    endpoint = engine.remember(
        OWNER,
        "中间实体连接目标数据库",
        slot="endpoint",
        metadata={"relations": [{"subject": "中间实体", "predicate": "USES", "object": "数据库"}]},
    )
    engine.flush_graph()
    for edge in engine.graph_backend.items.values():
        edge["path_ids"] = [bridge, endpoint]
    assert len(engine.graph(OWNER, hops=2)) == 1
    engine.exclude(OWNER, "bridge", state="suppressed")
    assert engine.graph(OWNER, hops=2) == []
    assert engine.graph(OWNER, hops=2, historical=True) == []
    engine.reactivate(OWNER, "bridge")
    assert len(engine.graph(OWNER, hops=2)) == 1


def test_dated_episode_with_low_stability_is_kept_and_anchored(engine):
    candidate = item("10月4日8:30去万里文化中心参加志愿者活动")
    candidate.update(
        type="episodic",
        slot="event.volunteer",
        stability=0.2,
        future_use=0.95,
        event_at="2026-10-04T08:30:00+08:00",
    )
    engine.model = FakeModel({"memories": [candidate]})
    source = engine.enqueue(OWNER, candidate["evidence"], session="event")
    assert engine.process_one()
    assert engine.list(OWNER)[0]["metadata"]["event_at"] == candidate["event_at"]
    result = __import__("json").loads(
        engine.store.rows("SELECT result FROM sources WHERE id=?", (source,))[0]["result"]
    )
    assert result["retained"] == 1 and result["states"] == {"active": 1}


def test_filtered_and_empty_jobs_explain_why_no_memory_created(engine):
    candidate = item()
    candidate["future_use"] = 0.1
    engine.model = FakeModel({"memories": [candidate]})
    engine.enqueue(OWNER, candidate["evidence"], session="filtered")
    engine.process_one()
    row = engine.store.rows("SELECT result FROM sources")[0]
    result = __import__("json").loads(row["result"])
    assert result["outcome"] == "filtered"
    assert result["skipped"] == {"low_future_use": 1}
    engine.model = FakeModel()
    engine.enqueue(OWNER, "这是一条普通闲聊内容", session="empty")
    engine.process_one()
    outcome = engine.store.rows(
        "SELECT json_extract(result,'$.outcome') AS outcome FROM sources WHERE session='empty'"
    )[0]
    assert outcome["outcome"] == "model_empty"


def test_schema_two_database_upgrades_in_place_without_losing_facts(tmp_path):
    import sqlite3

    from gramem.store import SCHEMA

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.executescript(
            SCHEMA.replace(", result TEXT NOT NULL DEFAULT '{}'", "").replace(
                "user_version=8", "user_version=2"
            )
        )
        db.execute(
            "INSERT INTO sources(id,principal,session,kind,content,created) VALUES('legacy',?,'s','conversation','原始证据',1)",
            (OWNER.key,),
        )
    engine = Engine(path)
    assert engine.store.rows("PRAGMA user_version")[0]["user_version"] == 8
    assert engine.store.rows("SELECT content,result FROM sources") == [
        {"content": "原始证据", "result": "{}"}
    ]
    engine.close()


def test_graph_network_dispatch_never_holds_fact_write_transaction(engine):
    engine.remember(
        OWNER,
        "项目使用独立图",
        metadata={"relations": [{"subject": "项目", "predicate": "USES", "object": "图"}]},
    )
    old_apply = engine.graph_backend.apply

    def apply(action, payload):
        # A concurrent foreground change during graph I/O must be able to commit.
        engine.remember(OWNER, "用户偏好清晰解释", slot="during.graph.io")
        old_apply(action, payload)

    engine.graph_backend.apply = apply
    assert engine.flush_graph() == 1
    assert len(engine.list(OWNER)) == 2


def test_second_graph_dispatcher_does_not_overtake_inflight_writer(engine):
    second = Engine(engine.store.path, graph=engine.graph_backend)
    try:
        engine.remember(
            OWNER,
            "项目使用独立图",
            metadata={"relations": [{"subject": "项目", "predicate": "USES", "object": "图"}]},
        )
        with engine.store.graph_dispatch() as acquired:
            assert acquired
            assert second.flush_graph() == 0
            assert second.status()["graph_pending"] == 1
        assert second.flush_graph() == 1
    finally:
        second.close()


@pytest.mark.parametrize("action", ["ADD", "IGNORE"])
def test_automatic_duplicate_enriches_graph_after_proactive_save(engine, action):
    content = "项目使用独立FalkorDB"
    id = engine.remember(OWNER, content, kind="project", slot="project.graph")
    candidate = item(content)
    candidate.update(
        type="project",
        slot="project.graph",
        action=action,
        relations=[{"subject": "项目", "predicate": "USES", "object": "FalkorDB"}],
    )
    engine.model = FakeModel({"memories": [candidate]})
    engine.enqueue(OWNER, content, session="auto")
    assert engine.process_one()
    engine.flush_graph()
    assert len(engine.list(OWNER)) == 1
    assert engine.graph(OWNER)[0]["memory_id"] == id
    assert engine.graph(OWNER)[0]["object"] == "FalkorDB"
    assert engine.get(OWNER, id)["source"]


def test_explicit_current_activity_activates_without_long_term_stability(engine):
    candidate = item("我正在编写项目文档")
    candidate.update(
        type="current_activity",
        slot="current_activity",
        future_use=0.3,
        stability=0.2,
        personalization=0.8,
        uniqueness=0.6,
    )
    engine.model = FakeModel({"memories": [candidate]})
    engine.enqueue(OWNER, candidate["evidence"], session="temporary")
    engine.process_one()
    row = engine.list(OWNER)[0]
    assert row["class"] == "temporary" and row["status"] == "active"
    assert "编写项目文档" in engine.recall(OWNER, "下一步")["context"]
