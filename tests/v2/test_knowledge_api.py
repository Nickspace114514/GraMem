"""Authenticated router behavior with the real database and profile-scoped engines."""

import base64
import importlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[2] / "integrations/control-panel/dashboard/api.py"
    spec = importlib.util.spec_from_file_location("knowledge_api_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("A", "B"):
        directory = tmp_path / name / "gramem"
        directory.mkdir(parents=True)
        (directory / "config.json").write_text(json.dumps({"owner_id": name}))
    monkeypatch.setattr(module, "home", lambda: tmp_path / "A")
    memory = types.ModuleType("plugins.memory")
    memory.import_provider_module = lambda provider, name: importlib.import_module(name)
    secrets = types.ModuleType("agent.secret_scope")
    secrets.get_secret = lambda key: None
    monkeypatch.setitem(sys.modules, "plugins", types.ModuleType("plugins"))
    monkeypatch.setitem(sys.modules, "plugins.memory", memory)
    monkeypatch.setitem(sys.modules, "agent", types.ModuleType("agent"))
    monkeypatch.setitem(sys.modules, "agent.secret_scope", secrets)
    app = FastAPI()
    app.include_router(module.router)
    yield TestClient(app), module, tmp_path


def test_upload_parse_search_download_and_profile_isolation(client):
    http, module, root = client
    raw = "架构知识库支持长期文件留存".encode()
    response = http.post(
        "/knowledge/upload", json={"filename": "架构.md", "data": base64.b64encode(raw).decode()}
    )
    assert response.status_code == 200, response.text
    doc = response.json()
    assert doc["status"] == "queued"
    assert http.get(f"/knowledge/{doc['id']}/original").content == raw
    assert http.post("/operation", json={"action": "worker"}).json()["knowledge_processed"]
    hit = http.get("/knowledge/search", params={"q": "长期"}).json()["items"][0]
    assert hit["document_id"] == doc["id"] and hit["page"] == 1
    assert http.get(f"/knowledge/{doc['id']}").json()["items"]
    module.home = lambda: root / "B"
    assert not http.get("/knowledge").json()["items"]
    assert http.get(f"/knowledge/{doc['id']}/original").status_code == 400
    module.home = lambda: root / "A"
    assert http.get(f"/knowledge/{doc['id']}/original").content == raw


def test_document_controls_hide_memory_search_and_download(client):
    http, _, _ = client
    doc = http.post(
        "/document",
        json={"filename": "notes.txt", "data": base64.b64encode("用户知识内容".encode()).decode()},
    ).json()
    http.post("/operation", json={"action": "worker"})
    assert http.get("/memories", params={"q": "用户知识"}).json()["items"]
    assert (
        http.post("/knowledge/control", json={"id": doc["id"], "action": "suppress"}).status_code
        == 200
    )
    assert not http.get("/memories", params={"q": "用户知识"}).json()["items"]
    assert http.get(f"/knowledge/{doc['id']}/original").status_code == 400
    assert (
        http.post("/knowledge/control", json={"id": doc["id"], "action": "reactivate"}).status_code
        == 200
    )
    assert http.get(f"/knowledge/{doc['id']}/original").status_code == 200
    assert (
        http.post("/knowledge/control", json={"id": doc["id"], "action": "forget"}).status_code
        == 200
    )
    assert not http.get("/knowledge", params={"historical": True}).json()["items"]
    assert http.get(f"/knowledge/{doc['id']}/original").status_code == 400
    backup = http.post("/operation", json={"action": "backup"})
    assert backup.status_code == 200, backup.text
    assert backup.json()["documents"] == 0


@pytest.mark.parametrize('blocked_by', ['silent', 'epoch', 'rewind'])
@pytest.mark.parametrize('provenance', ['source', 'metadata'])
def test_memory_pagination_hides_chat_sources_and_transitive_conclusions(client, blocked_by, provenance):
    from gramem.chats import Chats

    http, module, _ = client
    with module.engine() as (e, p):
        source = e.enqueue(p, '私人咖啡偏好', session='s', turn='u')
        chat = Chats(e).capture(p, '私人咖啡偏好', '原话回复', session='s', turn='u',
                                platform='cli', source_ids=[source])
        fact = e.remember(p, '咖啡标记原始记忆', slot='drink', metadata={
            'source_ids': [source]} if provenance == 'metadata' else {})
        if provenance == 'source':
            with e.store.transaction() as db:
                db.execute('UPDATE memories SET source=? WHERE id=?', (source, fact))
        merged = e.remember(p, '咖啡标记第一层结论', slot='summary', action='MERGE', targets=[fact])
        derived = e.remember(p, '咖啡标记第二层结论', slot='derived', action='MERGE', targets=[merged])
        safe = e.remember(p, '正常可见项目说明', slot='project')
        with e.store.transaction() as db:
            if blocked_by == 'silent':
                db.execute("UPDATE chat_turns SET status='silent' WHERE id=?", (chat,))
            elif blocked_by == 'epoch':
                db.execute('UPDATE chat_turns SET policy_epoch=-1 WHERE id=?', (chat,))
            else:
                db.execute('INSERT INTO chat_native_state VALUES(?,?,0)', (chat, 1))
        assert [r['id'] for r in e.list(p)] == [safe]
    response = http.get('/memories', params={'size': 1}).json()
    assert response['total'] == 1 and response['items'][0]['id'] == safe
    assert http.get('/memories', params={'page': 2, 'size': 1}).json()['items'] == []
    for status in ['active', 'superseded']:
        result = http.get('/memories', params={'q': '咖啡标记', 'status': status}).json()
        assert result['items'] == [] and result['total'] == 0
    assert http.get('/memories', params={'q': derived}).json()['total'] == 0


def test_upload_and_query_validation(client):
    http, _, _ = client
    assert http.post("/document", json={"filename": "bad.exe", "data": "YWJj"}).status_code == 400
    assert http.post("/document", json={"filename": "x.md", "data": "%%%"}).status_code == 400
    assert (
        http.post(
            "/document", json={"filename": "x.md", "data": "YWJj", "unexpected": True}
        ).status_code
        == 422
    )
    assert http.get("/knowledge", params={"page": 0}).status_code == 422
    assert http.get("/knowledge/search", params={"q": ""}).status_code == 422


def test_chat_api_original_network_and_suppression_are_scoped(client):
    from gramem.chats import Chats

    http, module, root = client
    with module.engine() as (e, p):
        id = Chats(e).capture(p, 'GraMem 跨平台技术讨论', '记录原文', session='s', turn='u', platform='teams')
    assert http.get('/chats').json()['items'][0]['id'] == id
    assert http.get('/chats/overview').json()['turns'] == 1
    original = http.get(f'/chats/{id}/original')
    assert original.status_code == 200 and original.headers['cache-control'] == 'no-store'
    assert original.json()['user'] == 'GraMem 跨平台技术讨论'
    assert http.get('/network').json()['nodes']
    module.home = lambda: root / 'B'
    assert http.get('/chats').json()['items'] == []
    assert http.get(f'/chats/{id}/original').status_code == 400
    module.home = lambda: root / 'A'
    with module.engine() as (e, p):
        e.exclude(p, 'private', state='suppressed')
    assert http.get('/chats').json()['items'] == []
    assert http.get('/network').json()['nodes'] == []
    assert http.get(f'/chats/{id}/original').status_code == 400


def test_memory_net_api_live_weights_and_history(client):
    http, module, _ = client
    with module.engine() as (e, p):
        old = e.remember(p, '旧方案保留 JSON', slot='plan', kind='event')
        new = e.remember(p, '新方案使用 SQLite', slot='plan', kind='event', action='UPDATE', targets=[old])
        row = e.get(p, new)
    current = http.get('/network').json()
    assert 'memory:' + old not in {n['id'] for n in current['nodes']}
    node = next(n for n in current['nodes'] if n['id'] == 'memory:' + new)
    for key in ('strength','confidence','importance','lifecycle','status','version'):
        assert node[key] == row[key]
    assert node['effective_strength'] <= row['strength']
    history = http.get('/network', params={'historical':True}).json()
    assert history['historical'] is True and history['as_of'] > 0
    assert any(n['id'] == 'memory:' + old and n['status'] == 'superseded' for n in history['nodes'])
    assert any(n['kind'] == 'event' for n in history['nodes'])


def test_bulk_chat_api_durable_job_reuse_profile_scope_and_progress(client):
    from test_chats import Organizer

    from gramem.chat_backfill import Backfill
    from gramem.chats import Chats
    from gramem.config import Principal

    http, module, root = client
    with module.engine() as (e, p):
        Chats(e).capture(p,'GraMem 未整理旧记录','原件答复',session='s',turn='1',platform='teams')
        contact = Principal(p.owner,'contact','email:guest','email:guest')
        Chats(e).capture(contact,'独立联系人记录','答复',session='c',turn='1',platform='email')
    assert http.get('/chats/process').json()['pending']==1
    first = http.post('/chats/process',json={}).json()
    assert first['job']['total']==1 and first['job']['state']=='importing'
    assert http.post('/chats/process',json={}).json()['job']['id']==first['job']['id']
    assert http.post('/chats/process',json={'path':'/arbitrary/history.db'}).status_code==422
    assert http.post('/chats/process',json={'scope':'foreign\x1fowner\x1fforeign'}).status_code==404
    assert http.get('/chats/process',params={'scope':contact.key}).json()['job'] is None
    with module.engine() as (e, p):
        e.model=Organizer()
        task=Backfill(e)
        assert task.step() and task.step()
    progress = http.get('/chats/process').json()['job']
    assert progress['done']==progress['total']==1 and progress['state']=='completed'
    assert http.post('/chats/process/retry',json={}).status_code==400
    module.home=lambda:root/'B'
    assert http.get('/chats/process').json()['job'] is None


def test_bulk_chat_api_reports_waiting_model_then_allows_retry(client):
    from gramem.chat_backfill import Backfill
    from gramem.chats import Chats

    http,module,_ = client
    with module.engine() as (e,p):
        Chats(e).capture(p,'GraMem 等待模型的旧记录','原件',session='s',turn='1',platform='teams')
    http.post('/chats/process',json={})
    with module.engine() as (e,p):
        task=Backfill(e)
        task.step()
        task.step()
    assert http.get('/chats/process').json()['job']['error']=='model_unavailable'
    retried=http.post('/chats/process/retry',json={}).json()['job']
    assert retried['error']=='' and retried['remaining']==1


def test_chat_audio_api_original_bundle_and_identity_profile_protection(client):
    import hashlib
    import io
    import zipfile

    from test_chat_audio import WAVE, messages
    from test_chats import Organizer

    from gramem.chat_audio import ChatAudio
    from gramem.chats import Chats

    http, module, root = client
    home = root / 'A'
    path = home / 'cache/audio/reply.wav'
    path.parent.mkdir(parents=True)
    path.write_bytes(WAVE)
    with module.engine() as (e, p):
        e.model = Organizer()
        id = Chats(e).capture(p, '语音测试', 'MEDIA:' + str(path), session='s', turn='u', platform='cli')
        ChatAudio(e).capture(p, id, messages(path, '禁提标记的文案'), home=home)
        assert Chats(e).process_one()
        other = Chats(e).capture(p, '另一段聊天', '文字', session='s', turn='other', platform='cli')
    data = http.get('/chats/' + id).json()
    audio = data['audio'][0]
    route = f"/chats/{id}/audio/{audio['id']}/original"
    response = http.get(route)
    assert response.status_code == 200 and response.content == WAVE
    assert response.headers['x-content-sha256'] == hashlib.sha256(WAVE).hexdigest()
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['content-type'] == 'audio/wav'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert http.get(f"/chats/{other}/audio/{audio['id']}/original").status_code == 400
    bundle = http.get(f'/chats/{id}/bundle')
    assert bundle.status_code == 200 and bundle.headers['content-type'] == 'application/zip'
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as z:
        assert z.read('audio/' + audio['name']) == WAVE
    path.unlink()
    assert http.get(route).content == WAVE
    module.home = lambda: root / 'B'
    assert http.get(route).status_code == 400 and http.get(f'/chats/{id}/bundle').status_code == 400
    module.home = lambda: home
    with module.engine() as (e, p):
        e.exclude(p, 'private.voice', state='suppressed')
        e.model = Organizer()
        assert Chats(e).process_one()
    assert http.get(route).status_code == 400
    assert http.get('/chats/' + id).status_code == 400
    assert http.get(f'/chats/{id}/bundle').status_code == 400
    assert not any(node['kind'] == 'audio' for node in http.get('/network').json()['nodes'])
