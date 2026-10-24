"""Regressions for project-wide consistency, forgetting and adapter review."""

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from test_engine import CONTACT, OWNER, FakeGraph, FakeModel, item

from gramem.cli import main
from gramem.config import Config
from gramem.documents import chunks, ingest
from gramem.engine import Engine
from gramem.graph import FalkorGraph
from gramem.migrate import import_records, load_records
from gramem.model import Model
from gramem.reflection import consolidate, reflect
from gramem.store import Store


@pytest.fixture
def engine(tmp_path):
    e = Engine(tmp_path / "memory.sqlite", graph=FakeGraph(), clock=lambda: 10000)
    yield e
    e.close()


def test_profile_tracks_new_confirmed_and_reactivated_facts(engine):
    engine.remember(OWNER, "喜欢咖啡", kind="preference", slot="drink")
    assert "preference" in engine.profile(OWNER)
    id = engine.remember(OWNER, "擅长Python", kind="skill", slot="skill")
    assert engine.profile(OWNER)["skill"][0]["id"] == id
    candidate = engine.remember(OWNER, "姓名测试", kind="identity", confirmed=False)
    assert "identity" not in engine.profile(OWNER)
    engine.confirm(OWNER, candidate)
    assert "identity" in engine.profile(OWNER)
    engine.exclude(OWNER, "drink", state="suppressed")
    assert "preference" not in engine.profile(OWNER)
    engine.reactivate(OWNER, "drink")
    assert "preference" in engine.profile(OWNER)


def test_merge_equal_to_target_still_replaces_all_targets_and_keeps_provenance(engine):
    a = engine.remember(OWNER, "偏好清晰且简短的解释", kind="preference", slot="detail")
    b = engine.remember(OWNER, "偏好简短的解释", kind="preference", slot="detail")
    engine.model = FakeModel({"merges": [{"ids": [a, b], "content": "偏好清晰且简短的解释"}]})
    assert consolidate(engine, OWNER) == 1
    rows = engine.list(OWNER)
    assert len(rows) == 1
    merged = rows[0]
    assert merged["id"] not in {a, b}
    assert set(merged["metadata"]["targets"]) == {a, b}
    assert {r["id"] for r in engine.list(OWNER, status="superseded")} == {a, b}
    engine.exclude(OWNER, "detail", state="suppressed")
    assert not engine.recall(OWNER, "解释")["context"]


def test_duplicate_add_and_unchanged_singleton_remain_idempotent(engine):
    id = engine.remember(OWNER, "用户偏好简短解释", kind="preference", slot="detail")
    assert engine.remember(OWNER, "用户偏好简短解释", kind="preference", slot="detail") == id
    current = engine.remember(OWNER, "现在在新加坡", kind="current_location")
    assert engine.remember(OWNER, "现在在新加坡", kind="current_location") == current
    assert len(engine.list(OWNER)) == 2
    assert not engine.list(OWNER, status="superseded")


def test_document_erasure_follows_duplicate_secondary_source(engine):
    with engine.store.transaction() as db:
        for source, kind in [("chat", "conversation"), ("document", "document")]:
            db.execute(
                "INSERT INTO sources(id,principal,session,kind,content,created,status) VALUES(?,?,'',?,'原始事实',10000,'done')",
                (source, OWNER.key, kind),
            )
        id = engine._insert(db, OWNER, "原始事实", "knowledge", "fact", source="chat")
        assert engine._insert(db, OWNER, "原始事实", "knowledge", "fact", source="document") == id
        sibling = engine._insert(db, OWNER, "原始事实及相邻重叠内容", "knowledge", "document.chunk", source="document")
    assert engine.get(OWNER, id)["source"] == "chat"
    assert engine.exclude(OWNER, "fact")["document_sources_erased"] == 1
    assert all(r["status"] == "forgotten" and r["content"] == "" for r in engine.store.rows(
        "SELECT content,status FROM memories WHERE id IN (?,?)", (id, sibling)
    ))
    assert not engine.recall(OWNER, "原始事实")["context"]


def test_forget_document_erases_overlaps_and_derived_facts_without_cross_scope_loss(engine, tmp_path):
    text = " ".join(f"word{i}" for i in range(1000))
    pieces = list(chunks(text))
    overlap = set(pieces[0].split()) & set(pieces[1].split())
    marker = sorted(overlap)[len(overlap) // 2]
    path = tmp_path / "overlap.txt"
    path.write_text(text)
    imported = ingest(engine, OWNER, path)
    contact = ingest(engine, CONTACT, path)
    other = tmp_path / "unrelated.txt"
    other.write_text("另一份独立的文档资料")
    unrelated = ingest(engine, OWNER, other)
    slot = engine.get(OWNER, imported["ids"][0])["slot"]
    derived = engine.remember(OWNER, "文档归纳的派生事实", targets=[imported["ids"][1]], action="MERGE")
    result = engine.exclude(OWNER, slot)
    assert result["document_sources_erased"] == 1
    assert not engine.recall(OWNER, marker)["context"]
    forgotten = set(imported["ids"]) | {derived}
    assert all(r["status"] == "forgotten" and r["content"] == "" for r in engine.store.rows(
        "SELECT id,status,content FROM memories WHERE principal=?", (OWNER.key,)
    ) if r["id"] in forgotten)
    assert engine.store.rows("SELECT content,status FROM sources WHERE id=?", (imported["source"],)) == [
        {"content": "", "status": "redacted"}
    ]
    assert not forgotten.intersection(r["id"] for r in engine.store.rows("SELECT id FROM memory_fts"))
    assert engine.get(OWNER, unrelated["ids"][0])["content"] == "另一份独立的文档资料"
    assert len(engine.list(CONTACT)) == contact["chunks"]
    engine.reactivate(OWNER, slot, reauthorize=True)
    assert not engine.recall(OWNER, marker)["context"]
    assert engine.get(OWNER, unrelated["ids"][0])["status"] == "active"


def test_cached_reflection_cannot_recall_expired_sources(engine):
    id = engine.remember(OWNER, "短期项目状态", kind="project")
    engine.model = FakeModel({"projects": [{"fact": "短期项目状态", "source_ids": [id]}]})
    assert reflect(engine, OWNER)["projects"]
    assert engine.profile(OWNER)["projects"]  # Preserve the source-grounded reflection cache.
    with engine.store.transaction() as db:
        db.execute("UPDATE memories SET decay=100 WHERE id=?", (id,))
    engine.clock = lambda: 10000 + 86400
    assert engine.profile(OWNER) == {}


def test_two_initial_singleton_candidates_cannot_both_become_current(engine):
    a = engine.remember(OWNER, "目前在上海", kind="current_location", confirmed=False)
    b = engine.remember(OWNER, "目前在新加坡", kind="current_location", confirmed=False)
    engine.confirm(OWNER, a)
    with pytest.raises(ValueError, match="stale"):
        engine.confirm(OWNER, b)
    assert [r["id"] for r in engine.list(OWNER)] == [a]


def test_document_commit_rechecks_specific_exclusion(engine, tmp_path, monkeypatch):
    from gramem import knowledge

    path = tmp_path / "facts.txt"
    path.write_text("用户已要求遗忘的旧主题")
    original = knowledge.extract

    def concurrent_forget(data, suffix, **kwargs):
        text = original(data, suffix)
        engine.exclude(OWNER, "old.topic")
        return text

    monkeypatch.setattr(knowledge, "extract", concurrent_forget)
    with pytest.raises(PermissionError):
        ingest(engine, OWNER, path)
    assert not engine.store.rows("SELECT * FROM memories")
    assert not engine.store.rows("SELECT * FROM sources")


def test_duplicate_retains_all_raw_document_provenance_for_forgetting(engine):
    with engine.store.transaction() as db:
        for source in ("doc-a", "doc-b"):
            db.execute(
                "INSERT INTO sources(id,principal,session,kind,content,created,status) VALUES(?,?,'','document','旧偏好原文',10000,'done')",
                (source, OWNER.key),
            )
            id = engine._insert(db, OWNER, "旧偏好", "preference", "drink", source=source)
    engine.exclude(OWNER, "drink")
    with pytest.raises(PermissionError):
        engine.get(OWNER, id)
    assert engine.store.rows("SELECT DISTINCT content FROM sources") == [{"content": ""}]
    assert engine.store.rows("SELECT content FROM memories") == [{"content": ""}]


def test_duplicate_without_edges_still_adds_evidence_and_source(engine):
    id = engine.remember(OWNER, "用户喜欢咖啡", kind="preference", slot="drink")
    with engine.store.transaction() as db:
        db.execute(
            "INSERT INTO sources(id,principal,session,kind,content,created,status) VALUES('new',?,'','conversation','',10000,'done')",
            (OWNER.key,),
        )
        engine._insert(
            db,
            OWNER,
            "用户喜欢咖啡",
            "preference",
            "drink",
            source="new",
            metadata={"evidence": "我喜欢咖啡"},
        )
    row = engine.get(OWNER, id)
    assert row["source"] == "new" and row["metadata"]["evidence"] == "我喜欢咖啡"


def test_graph_relation_extra_keys_never_become_query_parameters(engine):
    relation = {
        "subject": "项目",
        "predicate": "USES",
        "object": "FalkorDB",
        "x='x' MATCH (n) DELETE n //": "attack",
    }
    engine.remember(OWNER, "项目使用FalkorDB", metadata={"relations": [relation]})
    payload = json.loads(engine.store.rows("SELECT payload FROM graph_outbox")[0]["payload"])
    assert set(payload) == {
        "subject",
        "predicate",
        "object",
        "id",
        "valid_from",
        "memory_id",
        "principal",
    }
    graph = FalkorGraph(Config())
    try:
        with pytest.raises(ValueError, match="parameter"):
            graph._query("RETURN 1", {"x='x' MATCH": "invalid"})
    finally:
        graph.close()


def test_graph_path_cannot_bridge_an_expired_current_fact(engine):
    a = engine.remember(
        OWNER,
        "起点到中点",
        metadata={"relations": [{"subject": "起点", "predicate": "TO", "object": "中点"}]},
    )
    b = engine.remember(
        OWNER,
        "中点到终点",
        metadata={"relations": [{"subject": "中点", "predicate": "TO", "object": "终点"}]},
    )
    engine.flush_graph()
    for edge in engine.graph_backend.items.values():
        if edge["memory_id"] == b:
            edge["path_ids"] = [a, b]
    with engine.store.transaction() as db:
        db.execute("UPDATE memories SET valid_until=9999 WHERE id=?", (a,))
    assert engine.graph(OWNER) == []


def test_consolidation_cannot_use_ids_not_in_bounded_model_input(engine):
    for i in range(6):
        engine.remember(OWNER, f"用户偏好第{i}条", kind="preference", slot="detail")
    excluded_ids = [r["id"] for r in engine.list(OWNER)[4:]]
    engine.model = FakeModel({"merges": [{"ids": excluded_ids, "content": "合并偏好"}]})
    with pytest.raises(ValueError, match="sources"):
        consolidate(engine, OWNER)
    assert len(engine.list(OWNER)) == 6


def test_import_review_is_never_transiently_active_and_activation_keeps_one_singleton(engine):
    original = engine.remember(OWNER, "当前上海", kind="current_location")
    import_records(
        engine, OWNER, [{"id": "a", "content": "当前新加坡", "type": "current_location"}]
    )
    assert engine.get(OWNER, original)["status"] == "active"
    assert not engine.store.rows(
        "SELECT * FROM events WHERE action='ADD' AND memory_id!=?", (original,)
    )
    import_records(
        engine,
        OWNER,
        [{"id": "b", "content": "当前北京", "type": "current_location"}],
        review=False,
    )
    assert len(engine.list(OWNER)) == 1
    assert engine.list(OWNER)[0]["content"] == "当前北京"


def test_malformed_import_is_atomic_and_cli_invalid_config_is_actionable(engine, tmp_path, capsys):
    with pytest.raises(ValueError):
        import_records(
            engine, OWNER, [{"content": "有效事实"}, {"content": "无效槽位", "slot": 42}]
        )
    assert not engine.list(OWNER)
    path = tmp_path / "export.json"
    path.write_text('{"items":{"bad":"shape"}}')
    with pytest.raises(ValueError):
        load_records(path)
    home = tmp_path / "profile"
    (home / "gramem").mkdir(parents=True)
    (home / "gramem" / "config.json").write_text('{"timezone":"Invalid/Zone"}')
    with pytest.raises(SystemExit) as exit:
        main(["--home", str(home), "status"])
    assert exit.value.code == 2
    assert "invalid timezone" in capsys.readouterr().err


def test_concurrent_schema_two_upgrade_is_atomic(tmp_path):
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE sources(id TEXT PRIMARY KEY,principal TEXT,session TEXT,kind TEXT,content TEXT,created REAL,status TEXT DEFAULT 'pending',attempts INTEGER DEFAULT 0,retry_at REAL DEFAULT 0,error TEXT,epoch INTEGER DEFAULT 0)"
        )
        db.execute("PRAGMA user_version=2")

    def open_store(_):
        store = Store(path)
        try:
            return store.rows("PRAGMA integrity_check")
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(open_store, range(4))) == [[{"integrity_check": "ok"}]] * 4


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), "0.1"])
def test_config_rejects_values_that_break_decay_or_lifecycle(value):
    with pytest.raises(ValueError):
        Config(decay_rates={"project": value})


@pytest.mark.parametrize("vector", [["1", "2"], [True, 1], [float("nan"), 1], "12"])
def test_malformed_api_embeddings_fail_safely(vector):
    model = Model(
        Config(embedding_model="test", embedding_dimensions=2), secret_resolver=lambda _: "test"
    )
    model.client.close()

    def response(request):
        if isinstance(vector, list) and any(type(v) is float for v in vector):
            return httpx.Response(200, content=b'{"data":[{"embedding":[NaN,1]}]}')
        return httpx.Response(200, json={"data": [{"embedding": vector}]})

    model.client = httpx.Client(transport=httpx.MockTransport(response))
    try:
        with pytest.raises(RuntimeError, match="embedding"):
            model.embed("事实")
    finally:
        model.close()


def test_valid_api_response_without_usage_still_extracts_and_embeds():
    model = Model(Config(model="test", embedding_model="test"), secret_resolver=lambda _: "test")
    model.client.close()

    def response(request):
        return httpx.Response(
            200,
            json={
                "usage": None,
                **(
                    {"data": [{"embedding": [1, 2]}]}
                    if request.url.path.endswith("embeddings")
                    else {"choices": [{"message": {"content": "{}"}}]}
                ),
            },
        )

    model.client = httpx.Client(transport=httpx.MockTransport(response))
    try:
        assert model.extract("test", {}) == {}
        assert model.embed("fact") == [1.0, 2.0]
        assert model.usage["calls"] == 2
    finally:
        model.close()


def test_checkpoint_and_sync_fallback_use_the_same_dedup_identity(engine):
    text = "我偏好简短说明"
    engine.enqueue(OWNER, text, session="s", turn=hashlib.sha256(text.encode()).hexdigest())
    engine.checkpoint(OWNER, [{"role": "user", "content": text}], session="s")
    assert len(engine.store.rows("SELECT id FROM sources")) == 1


def test_old_related_fact_participates_in_conflicts_beyond_recent_window(engine):
    old = engine.remember(
        OWNER, "灯塔项目使用PostgreSQL", kind="project", slot="project.lighthouse.database"
    )
    for i in range(40):
        engine.clock = lambda i=i: 10001 + i
        engine.remember(OWNER, f"第{i}条无关知识", slot=f"unrelated.{i}")
    candidate = item("灯塔项目改用SQLite")
    candidate.update(
        type="project", slot="project.lighthouse.database", action="UPDATE", targets=["m0"]
    )
    engine.model = FakeModel({"memories": [candidate]})
    engine.enqueue(OWNER, candidate["content"], session="s")
    assert engine.process_one()
    assert engine.get(OWNER, old)["status"] == "superseded"


def test_historical_fts_can_find_records_older_than_five_hundred(engine):
    old = engine.remember(OWNER, "灯塔项目原始数据库PostgreSQL", slot="lighthouse.old")
    with engine.store.transaction() as db:
        engine._invalidate(db, OWNER, old)
        for i in range(501):
            engine.clock = lambda i=i: 10001 + i
            id = engine._insert(db, OWNER, f"无关历史第{i}条", "knowledge", f"old.{i}")
            engine._invalidate(db, OWNER, id)
    assert (
        "PostgreSQL"
        in engine.recall(OWNER, "灯塔项目原始数据库PostgreSQL", historical=True)["context"]
    )


def test_repeated_confirmation_candidate_does_not_duplicate_or_publish_graph(engine):
    meta = {"relations": [{"subject": "用户", "predicate": "IN", "object": "上海"}]}
    first = engine.remember(
        OWNER, "当前在上海", kind="current_location", metadata=meta, confirmed=False
    )
    assert (
        engine.remember(
            OWNER, "当前在上海", kind="current_location", metadata=meta, confirmed=False
        )
        == first
    )
    assert len(engine.list(OWNER, status="candidate")) == 1
    assert not engine.store.rows("SELECT * FROM graph_outbox")
    engine.confirm(OWNER, first)
    engine.flush_graph()
    assert len(engine.graph(OWNER)) == 1


def test_empty_vector_scope_does_not_make_paid_query_embedding_request(engine):
    class NoPaidQuery(FakeModel):
        def embed(self, text):
            pytest.fail("empty scope should not call embedding API")

    engine.model = NoPaidQuery()
    assert engine.recall(OWNER, "无记忆的问题")["context"] == ""


def test_suppression_hides_transitive_merge_sources_without_erasing_them(engine):
    a = engine.remember(OWNER, "用户喜欢咖啡", kind="preference", slot="drink")
    b = engine.remember(
        OWNER, "用户偏好咖啡交流", kind="preference", slot="combined", action="MERGE", targets=[a]
    )
    c = engine.remember(
        OWNER,
        "用户偏好咖啡交流活动",
        kind="preference",
        slot="derived",
        action="MERGE",
        targets=[b],
        metadata={"relations": [{"subject": "用户", "predicate": "LIKES", "object": "咖啡活动"}]},
    )
    engine.flush_graph()
    engine.exclude(OWNER, "drink", state="suppressed")
    assert not engine.list(OWNER)
    assert not engine.recall(OWNER, "咖啡活动", historical=True)["context"]
    assert not engine.graph(OWNER, historical=True)
    assert engine.profile(OWNER) == {}
    with pytest.raises(PermissionError):
        engine.get(OWNER, c)
    engine.reactivate(OWNER, "drink")
    assert engine.get(OWNER, c)["content"] == "用户偏好咖啡交流活动"
    assert engine.graph(OWNER)
