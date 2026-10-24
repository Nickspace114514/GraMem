"""Exercise real installed GraMem against isolated profile homes."""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

source = Path(__file__).resolve().parents[1] / "dashboard" / "api.py"
spec = importlib.util.spec_from_file_location("control_api_tests", source)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
app = FastAPI()
app.include_router(module.router)
client = TestClient(app)
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    original_home = module.home
    for name in ("A", "B"):
        p = root / name
        (p / "gramem").mkdir(parents=True)
        (p / "gramem" / "config.json").write_text(json.dumps({"owner_id": name}))
    module.home = lambda: root / "A"
    # Save, search, pagination and isolation use the real Engine and SQLite.
    for i in range(205):
        response = client.post(
            "/operation",
            json={"action": "remember", "content": f"中文架构第{i}条", "slot": f"architecture.{i}"},
        )
        assert response.status_code == 200, response.text
    page = client.get("/memories?q=中文&page=3&size=100").json()
    assert page["total"] == 205 and len(page["items"]) == 5, page
    item = page["items"][0]
    result = client.post(
        "/operation",
        json={
            "action": "update",
            "content": "新版中文架构",
            "slot": item["slot"],
            "targets": [item["id"]],
        },
    ).json()
    assert result.get("id"), result
    assert client.get("/memories?status=superseded").json()["total"] == 1
    denied = client.post("/operation", json={"action": "forget", "slot": item["slot"]})
    assert denied.status_code == 400
    result = client.post(
        "/operation", json={"action": "suppress", "slot": item["slot"], "authorization": True}
    )
    assert result.status_code == 200, result.text
    assert client.get("/memories?q=新版").json()["total"] == 0
    assert (
        client.post("/operation", json={"action": "reactivate", "slot": item["slot"]}).status_code
        == 200
    )
    assert client.get("/memories?q=新版").json()["total"] == 1
    assert client.get("/memories?scope=unknown").status_code == 404
    module.home = lambda: root / "B"
    assert client.get("/memories").json()["total"] == 0
    module.home = lambda: root / "A"
    assert client.get("/memories").json()["total"] == 205
    assert client.get("/personality").status_code == 404
    config = client.get("/settings").json()
    original_config_bytes = (root / "A" / "gramem" / "config.json").read_bytes()
    for aliases in (
        {"telegram:@someone": "A"},
        {"telegram:-100123": "A"},
        {"telegram:0": "A"},
        {"email:invalid": "A"},
        {"email:Nick@Example.org": "A", "email:nick@example.org": "other"},
        {"slack:": "A"},
        {"no-platform": "A"},
        {"slack:U123": " A"},
    ):
        rejected = client.put("/settings", json={
            "values": {**config["values"], "aliases": aliases}, "revision": config["revision"],
        })
        assert rejected.status_code == 400, rejected.text
        assert (root / "A" / "gramem" / "config.json").read_bytes() == original_config_bytes
    response = client.put("/settings", json={
        "values": {**config["values"], "aliases": {
            "telegram:1000000001": "A", "email:Nick@Example.org": "A",
            "slack:UOTHER": "friend", "custom-platform:a:b": "friend",
        }}, "revision": config["revision"],
    })
    assert response.status_code == 200, response.text
    config = client.get("/settings").json()
    assert config["values"]["aliases"]["email:nick@example.org"] == "A"
    from plugins.memory import import_provider_module
    linked = import_provider_module("gramem", "gramem.config").Config(**config["values"])
    assert linked.principal("telegram", "1000000001").scope == "owner"
    assert linked.principal("slack", "UOTHER").subject == "friend"
    assert linked.principal("telegram", "999999").scope == "contact"
    assert linked.principal("telegram", "1000000001", group="-100123").scope == "group"
    assert list((root / "A" / "backups" / "hermes-control").glob("*-config.json"))
    module.home = lambda: root / "B"
    assert client.get("/settings").json()["values"]["aliases"] == {}
    module.home = lambda: root / "A"
    invalid = {**config["values"], "recall_tokens": -1}
    assert (
        client.put(
            "/settings", json={"values": invalid, "revision": config["revision"]}
        ).status_code
        == 400
    )
    valid = {**config["values"], "recall_tokens": 2048}
    assert (
        client.put("/settings", json={"values": valid, "revision": config["revision"]}).status_code
        == 200
    )
    assert (
        client.put("/settings", json={"values": valid, "revision": config["revision"]}).status_code
        == 409
    )
    assert (
        client.post("/operation", json={"action": "backup"}).json()["graph_backup_required"] is True
    )
    assert (
        client.post(
            "/operation", json={"action": "remember", "content": "safe", "unexpected": True}
        ).status_code
        == 422
    )
    assert client.post("/document", json={"filename": "test.txt", "data": "%%%"}).status_code == 400
    assert client.post("/document", json={"filename": "test.exe", "data": ""}).status_code == 400
    active = client.get("/memories?size=100").json()["items"]
    merge = client.post(
        "/operation",
        json={
            "action": "merge",
            "content": "合并后的中文架构",
            "slot": "architecture.merged",
            "targets": [active[0]["id"], active[1]["id"]],
        },
    )
    assert merge.status_code == 200, merge.text
    candidate = client.post(
        "/operation",
        json={
            "action": "remember",
            "content": "候选偏好事实",
            "slot": "preference.confirmed",
            "type": "identity",
            "confirmed": False,
        },
    ).json()["id"]
    assert client.post("/operation", json={"action": "confirm", "id": candidate}).status_code == 200
    rejected = client.post(
        "/operation",
        json={
            "action": "remember",
            "content": "拒绝候选偏好",
            "slot": "preference.rejected",
            "type": "identity",
            "confirmed": False,
        },
    ).json()["id"]
    assert client.post("/operation", json={"action": "reject", "id": rejected}).status_code == 200
    assert client.get("/memories?status=rejected").json()["total"] == 1
    original = client.post(
        "/operation",
        json={
            "action": "remember",
            "content": "传递来源原事实",
            "type": "preference",
            "slot": "source.root",
        },
    ).json()["id"]
    derived = client.post(
        "/operation",
        json={
            "action": "merge",
            "content": "传递来源派生事实",
            "type": "preference",
            "slot": "source.derived",
            "targets": [original],
        },
    ).json()["id"]
    client.post(
        "/operation",
        json={
            "action": "merge",
            "content": "传递来源二级派生",
            "type": "preference",
            "slot": "source.child",
            "targets": [derived],
        },
    )
    assert (
        client.post(
            "/operation", json={"action": "suppress", "slot": "source.root", "authorization": True}
        ).status_code
        == 200
    )
    for status in ("active", "superseded"):
        assert (
            client.get("/memories", params={"q": "传递来源", "status": status}).json()["total"] == 0
        )
    assert (
        client.post("/operation", json={"action": "reactivate", "slot": "source.root"}).status_code
        == 200
    )
    assert client.get("/memories", params={"q": "传递来源"}).json()["total"] == 1
    # The dashboard reflection button must actually dispatch source-grounded model reflection.
    from plugins.memory import import_provider_module

    model_module = import_provider_module("gramem", "gramem.model")
    original_model = model_module.Model
    calls = []

    class ProfileModel:
        available = True
        space = "test"
        usage = {}

        def __init__(self, *args, **kwargs):
            pass

        def embed(self, text):
            return None

        def extract(self, prompt, payload):
            calls.append(prompt)
            return {
                "communication": [
                    {"fact": "已确认事实的测试归纳", "source_ids": [payload[0]["id"]]}
                ]
            }

        def close(self):
            pass

    model_module.Model = ProfileModel
    try:
        result = client.post("/operation", json={"action": "reflect"})
        assert result.status_code == 200, result.text
        assert result.json()["communication"][0]["fact"] == "已确认事实的测试归纳"
        assert len(calls) == 1
    finally:
        model_module.Model = original_model
    forgotten = client.post(
        "/operation",
        json={"action": "forget", "slot": "preference.confirmed", "authorization": True},
    )
    assert forgotten.status_code == 200, forgotten.text
    assert client.get("/memories?q=候选偏好").json()["total"] == 0
    assert (
        client.post(
            "/operation", json={"action": "reauthorize", "slot": "preference.confirmed"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/operation",
            json={"action": "reauthorize", "slot": "preference.confirmed", "authorization": True},
        ).status_code
        == 200
    )
    assert client.get("/memories?q=候选偏好").json()["total"] == 0
    imported = client.post(
        "/import",
        json={
            "records": [
                {
                    "id": "old-test",
                    "content": "迁移的可靠知识",
                    "type": "knowledge",
                    "slot": "migration.test",
                }
            ]
        },
    )
    assert imported.status_code == 200, imported.text
    import base64

    document = client.post(
        "/document",
        json={
            "filename": "notes.md",
            "data": base64.b64encode("显式导入的中文知识文档。".encode()).decode(),
        },
    )
    assert document.status_code == 200, document.text
    # Real FalkorDB integration in the temporary home's distinct graph namespace.
    with module.engine() as (e, p):
        graph_name = e.graph_backend.name
        try:
            assert e.graph_backend.client.ping()
            graph_id = e.remember(
                p,
                "测试项目使用隔离数据库",
                slot="graph.test",
                metadata={
                    "relations": [
                        {
                            "subject": "GraMem Sandbox",
                            "predicate": "USES",
                            "object": "Isolated Database",
                        }
                    ]
                },
            )
            e.flush_graph(limit_jobs=1000)
            edges = e.graph(p, "GraMem Sandbox", hops=1)
            assert any(edge["memory_id"] == graph_id for edge in edges), edges
            new_id = e.remember(
                p,
                "测试项目升级隔离数据库",
                slot="graph.test",
                targets=[graph_id],
                action="UPDATE",
                metadata={
                    "relations": [
                        {
                            "subject": "GraMem Sandbox",
                            "predicate": "USES",
                            "object": "New Isolated Database",
                        }
                    ]
                },
            )
            e.flush_graph(limit_jobs=1000)
            assert all(edge["memory_id"] != graph_id for edge in e.graph(p, "GraMem Sandbox"))
            assert {graph_id, new_id} <= {
                edge["memory_id"] for edge in e.graph(p, "GraMem Sandbox", historical=True)
            }
            e.exclude(p, "graph.test", state="suppressed")
            assert e.graph(p, "GraMem Sandbox", historical=True) == []
        finally:
            e.graph_backend.client.execute_command("GRAPH.DELETE", graph_name)
    module.home = original_home
print(
    "PASS: 205-row Chinese search/pagination, update history, exclusions, A→B→A scope isolation, removed Hermes routes, config conflict detection, config validation, SQLite backup, merge, confirm/reject, forget/reauthorize, migration, document ingestion, real FalkorDB provenance/version/exclusion checks, strict bodies and upload validation"
)
