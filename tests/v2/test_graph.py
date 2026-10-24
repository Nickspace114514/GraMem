"""Graph retrieval boundaries and optional real FalkorDB integration.

Set GRAMEM_TEST_GRAPH_URL to a disposable FalkorDB to run the integration cases.
Each case owns a random namespace and removes it in teardown.
"""

import os
import uuid

import pytest
from test_engine import CONTACT, OWNER, FakeGraph

from gramem.config import Config
from gramem.engine import Engine
from gramem.graph import FalkorGraph
from gramem.tokens import compact, count


def remember_edge(engine, p, content, subject, object, *, slot=""):
    return engine.remember(
        p, content, kind="knowledge", slot=slot,
        metadata={"relations": [{"subject": subject, "predicate": "USES", "object": object}]},
    )


@pytest.fixture
def engine(tmp_path):
    e = Engine(tmp_path / "memory.sqlite", graph=FakeGraph(), clock=lambda: 10000)
    yield e
    e.close()


def test_graph_deduplicates_only_after_validating_alternative_paths(engine):
    bad = engine.remember(OWNER, "已停用的中间连接", slot="bad")
    good = engine.remember(OWNER, "仍有效的中间连接", slot="good")
    id = remember_edge(engine, OWNER, "远端数据库配置", "中间服务", "数据库")
    engine.flush_graph()
    edge = next(iter(engine.graph_backend.items.values()))
    engine.graph_backend.search = lambda *a, **k: [
        {**edge, "path_ids": [bad, id]},
        {**edge, "path_ids": [good, id]},
        {**edge, "path_ids": [good, id]},
    ]
    engine.exclude(OWNER, "bad", state="suppressed")
    result = engine.graph(OWNER, "项目", hops=2)
    assert len(result) == 1
    assert result[0]["path_ids"] == [good, id]
    assert result[0]["distance"] == 2
    engine.exclude(OWNER, "good", state="suppressed")
    assert engine.graph(OWNER, "项目", hops=2) == []


def test_graph_rejects_foreign_paths_and_malformed_rows(engine):
    foreign = engine.remember(CONTACT, "其他人的事实")
    id = remember_edge(engine, OWNER, "有效数据库配置", "项目", "数据库")
    engine.flush_graph()
    edge = next(iter(engine.graph_backend.items.values()))
    engine.graph_backend.search = lambda *a, **k: [
        None, {}, {**edge, "path_ids": 3}, {**edge, "path_ids": [foreign, id]},
        {**edge, "id": []}, {**edge, "object": None}, edge,
    ]
    assert len(engine.graph(OWNER)) == 1


def test_automatic_graph_recall_supplements_lexically_unrelated_source_fact(engine):
    id = remember_edge(engine, OWNER, "它使用独立图数据库保存关系", "GraMem", "FalkorDB")
    engine.flush_graph()
    result = engine.recall(OWNER, "GraMem 的架构是什么？", session="s", turn="1")
    assert [r["id"] for r in result["memories"]] == [id]
    assert result["memories"][0]["tier"] == "graph"
    assert '"subject":"GraMem"' in result["context"]
    assert result["tokens"] <= engine.config.recall_tokens
    assert engine.get(OWNER, id)["accesses"] == 1
    engine.recall(OWNER, "GraMem 的架构是什么？", session="s", turn="1")
    assert engine.get(OWNER, id)["accesses"] == 1
    assert engine.recall(CONTACT, "GraMem 的架构是什么？")["context"] == ""


def test_graph_recall_budget_and_limit_only_reinforce_delivered_facts(engine):
    ids = [remember_edge(engine, OWNER, f"独立配置编号{i}", "GraMem", f"Component{i}") for i in range(5)]
    engine.flush_graph()
    engine.config.graph_recall_limit = 2
    engine.config.graph_recall_tokens = 180
    result = engine.recall(OWNER, "GraMem", session="s", turn="1")
    graph_lines = result["context"].splitlines()[1:]
    assert 0 < len(result["memories"]) <= 2
    assert sum(count(line + "\n") for line in graph_lines) <= 180
    delivered = {r["id"] for r in result["memories"]}
    assert all(engine.get(OWNER, id)["accesses"] == (1 if id in delivered else 0) for id in ids)
    engine.config.graph_recall_tokens = 1
    assert engine.recall(OWNER, "GraMem", session="s", turn="2")["context"] == ""
    assert all(engine.get(OWNER, id)["accesses"] == (1 if id in delivered else 0) for id in ids)


def test_graph_delivery_rechecks_path_after_other_retrieval_work(engine):
    bridge = engine.remember(OWNER, "中间连接", slot="bridge")
    id = remember_edge(engine, OWNER, "远端数据库配置", "GraMem", "数据库")
    engine.flush_graph()
    edge = next(iter(engine.graph_backend.items.values()))
    engine.graph_backend.search = lambda *a, **k: [{**edge, "path_ids": [bridge, id]}]

    class Model:
        space = "race-test"

        def embed(self, text):
            engine.exclude(OWNER, "bridge", state="suppressed")
            return None

        def close(self):
            pass

    engine.model = Model()
    with engine.store.transaction() as db:
        db.execute("UPDATE memories SET embedding='[1]',embedding_space='race-test' WHERE id=?", (id,))
    result = engine.recall(OWNER, "GraMem")
    assert result["context"] == ""
    assert engine.get(OWNER, id)["accesses"] == 0


def test_graph_failure_backoff_and_disable_preserve_normal_recall(engine):
    id = engine.remember(OWNER, "用户偏好简短说明", kind="preference")
    calls = []

    def unavailable(*args, **kwargs):
        calls.append(1)
        raise ConnectionError("isolated graph offline")

    engine.graph_backend.search = unavailable
    assert id in {r["id"] for r in engine.recall(OWNER, "表达偏好")["memories"]}
    engine.recall(OWNER, "表达偏好")
    assert len(calls) == 1
    engine.clock = lambda: 10031
    engine.recall(OWNER, "表达偏好")
    assert len(calls) == 2
    engine.config.graph_recall_enabled = False
    engine.clock = lambda: 10062
    assert engine.recall(OWNER, "表达偏好")["context"]
    assert len(calls) == 2


def test_graph_only_vector_candidates_still_obey_graph_limit(engine):
    ids = [remember_edge(engine, OWNER, f"独立配置编号{i}", "GraMem", f"Component{i}") for i in range(5)]
    engine.flush_graph()

    class Model:
        space = "orthogonal-vectors"

        def embed(self, text):
            return [0.0, 1.0]

        def close(self):
            pass

    engine.model = Model()
    with engine.store.transaction() as db:
        db.execute("UPDATE memories SET embedding='[1,0]',embedding_space='orthogonal-vectors'")
    engine.config.graph_recall_limit = 1
    result = engine.recall(OWNER, "GraMem")
    assert len(result["memories"]) == 1
    assert result["memories"][0]["id"] in ids
    assert result["memories"][0]["tier"] == "graph"


def test_historical_graph_only_candidates_obey_sub_budget_and_do_not_reinforce(engine):
    id = remember_edge(engine, OWNER, "旧配置记录", "GraMem", "OldDB", slot="database")
    engine.flush_graph()
    with engine.store.transaction() as db:
        engine._invalidate(db, OWNER, id)
    engine.config.graph_recall_tokens = 1
    assert engine.recall(OWNER, "GraMem", historical=True)["context"] == ""
    engine.config.graph_recall_tokens = 256
    result = engine.recall(OWNER, "GraMem", historical=True)
    assert [r["id"] for r in result["memories"]] == [id]
    assert result["memories"][0]["tier"] == "historical"
    assert engine.get(OWNER, id)["accesses"] == 0


@pytest.mark.parametrize("key,value", [
    ("graph_recall_enabled", "false"), ("graph_recall_hops", True),
    ("graph_recall_hops", 4), ("graph_recall_limit", 0),
    ("graph_recall_limit", 11), ("graph_recall_tokens", 0),
])
def test_graph_recall_configuration_is_bounded(key, value):
    with pytest.raises(ValueError):
        Config(**{key: value})


@pytest.fixture
def live_engine(tmp_path):
    url = os.getenv("GRAMEM_TEST_GRAPH_URL")
    if not url:
        pytest.skip("GRAMEM_TEST_GRAPH_URL is required for a disposable FalkorDB")
    cfg = Config(graph_url=url, graph_name="gramem_validation_" + uuid.uuid4().hex[:16])
    graph = FalkorGraph(cfg)
    e = Engine(tmp_path / "live.sqlite", cfg, graph=graph, clock=lambda: 10000)
    try:
        assert graph.health()
        yield e
    finally:
        try:
            graph.client.execute_command("GRAPH.DELETE", cfg.graph_name)
        finally:
            e.close()


def test_live_incoming_edges_natural_question_and_blank_graph_keep_direction(live_engine):
    e = live_engine
    id = remember_edge(e, OWNER, "它使用独立图数据库", "GraMem", "FalkorDB")
    e.flush_graph()
    for query in ("GraMem", "FalkorDB", ""):
        edges = e.graph(OWNER, query, hops=3)
        assert len(edges) == 1
        assert (edges[0]["subject"], edges[0]["object"]) == ("GraMem", "FalkorDB")
        assert edges[0]["distance"] == 1
    result = e.recall(OWNER, "FalkorDB 被哪个项目使用？")
    assert id in {r["id"] for r in result["memories"]}
    assert e.graph(CONTACT, "FalkorDB") == []


def test_live_multihop_dedup_and_valid_alternative_after_suppression(live_engine):
    e = live_engine
    ab = remember_edge(e, OWNER, "首条连接", "起点", "中间服务", slot="ab")
    ac = remember_edge(e, OWNER, "另一条起始连接", "起点", "旁路服务", slot="ac")
    cb = remember_edge(e, OWNER, "旁路连接", "旁路服务", "中间服务", slot="cb")
    target = remember_edge(e, OWNER, "末端配置", "中间服务", "末端数据库", slot="target")
    e.flush_graph()
    before = e.graph(OWNER, "起点", hops=3)
    assert len({edge["id"] for edge in before}) == len(before) == 4
    assert next(edge for edge in before if edge["memory_id"] == target)["path_ids"] == [ab, target]
    e.exclude(OWNER, "ab", state="suppressed")
    # Suppression is authoritative in SQLite before any graph deletion/expiry.
    after = e.graph(OWNER, "起点", hops=3)
    endpoint = next(edge for edge in after if edge["memory_id"] == target)
    assert endpoint["path_ids"] == [ac, cb, target]
    assert endpoint["distance"] == 3
    e.exclude(OWNER, "cb", state="suppressed")
    assert target not in {edge["memory_id"] for edge in e.graph(OWNER, "起点", hops=3)}


def test_live_graph_history_and_forgetting(live_engine):
    e = live_engine
    old = remember_edge(e, OWNER, "旧数据库选择", "GraMem", "OldDB", slot="database")
    e.flush_graph()
    new = e.remember(OWNER, "新数据库选择", slot="database", action="UPDATE", targets=[old], metadata={
        "relations": [{"subject": "GraMem", "predicate": "USES", "object": "NewDB"}]
    })
    e.flush_graph()
    assert {edge["memory_id"] for edge in e.graph(OWNER, "GraMem")} == {new}
    assert {edge["memory_id"] for edge in e.graph(OWNER, "GraMem", historical=True)} == {old, new}
    e.exclude(OWNER, "database")
    assert not e.graph(OWNER, "GraMem", historical=True)
    e.flush_graph()
    assert not e.graph_backend.search(OWNER.key, "GraMem", historical=True)


def test_live_auto_two_hop_recall_respects_shared_budget(live_engine):
    e = live_engine
    remember_edge(e, OWNER, "架构起点配置", "GraMem", "中间服务")
    endpoint = remember_edge(e, OWNER, "下游持久化配置", "中间服务", "FalkorDB")
    e.flush_graph()
    result = e.recall(OWNER, "GraMem")
    assert endpoint in {r["id"] for r in result["memories"]}
    assert all(r["tier"] == "graph" for r in result["memories"])
    assert result["tokens"] <= e.config.recall_tokens
    assert sum(count(line + "\n") for line in result["context"].splitlines()[1:]) <= e.config.graph_recall_tokens
    e.config.graph_recall_enabled = False
    assert e.recall(OWNER, "GraMem")["context"] == ""
    assert "relations" in compact(result)
