"""Native provenance and rewind regressions from the Context/GraMem review."""
import hashlib
import json
import sqlite3

import pytest
from test_chats import Organizer
from test_engine import CONTACT, OWNER, FakeModel, item

from gramem.chat_backfill import Backfill
from gramem.chat_import import import_sessions
from gramem.chats import Chats
from gramem.config import Config
from gramem.engine import Engine
from gramem.network import Network


@pytest.fixture
def engine(tmp_path):
    e = Engine(tmp_path/'memory.sqlite', Config(aliases={'teams:verified': 'owner'}), model=Organizer())
    yield e
    e.close()


def native(path, messages):
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE sessions(id,source,user_id,chat_type,origin_json,started_at,chat_id);
            CREATE TABLE messages(id INTEGER PRIMARY KEY,session_id,role,content,timestamp,
            _compressed_summary DEFAULT 0,message_uid,platform_message_id,active DEFAULT 1,compacted DEFAULT 0);
            INSERT INTO sessions VALUES('s','teams','verified','dm','{}',1,'d');''')
        for id, role, content, uid, active, compacted in messages:
            db.execute('''INSERT INTO messages(id,session_id,role,content,timestamp,message_uid,active,compacted)
                VALUES(?,'s',?,?,?,?,?,?)''', (id, role, content, id, uid, active, compacted))


def test_cleared_legacy_source_recovered_and_existing_archive_repaired(engine, tmp_path):
    user = '我喜欢喝黑咖啡'
    engine.model = FakeModel({'memories': [{**item(user), 'slot': 'drink.preference'}]})
    source = engine.enqueue(OWNER, user, session='s', turn='u1')
    assert engine.process_one()
    assert engine.store.rows('SELECT content FROM sources WHERE id=?', (source,))[0]['content'] == ''
    archive = Chats(engine)
    id = archive.capture(OWNER, user, '好的', session='s', turn='u1', platform='teams')
    original = archive.original(OWNER, id)[1]
    with engine.store.transaction() as db:
        db.execute('DELETE FROM source_turns')  # Pre-fix database, with discarded source text.
    path = tmp_path/'state.db'
    native(path, [(1, 'user', user, 'u1', 1, 0), (2, 'assistant', '好的', 'a1', 1, 0)])
    assert import_sessions(engine, path)['imported'] == 0
    row = engine.store.rows('SELECT original,sha256,source_ids FROM chat_turns WHERE id=?', (id,))[0]
    assert bytes(row['original']) == original
    assert row['sha256'] == hashlib.sha256(original).hexdigest()
    assert json.loads(row['source_ids']) == [source]
    engine.exclude(OWNER, 'coffee.topic', state='suppressed')  # Different canonical slot.
    assert engine.list(OWNER) == []
    assert not engine.recall(OWNER, '咖啡', historical=True)['context']


def test_turn_links_survive_chunk_budget_change_and_identity_isolation(engine):
    user = '我偏好明确的项目说明。' * 80
    engine.config.extraction_input_tokens = 40
    sources = engine.enqueue(OWNER, user, session='s', turn='u')
    assert isinstance(sources, list) and len(sources) > 1
    with engine.store.transaction() as db:
        db.execute("UPDATE sources SET content='',status='done'")
    engine.config.extraction_input_tokens = 100
    assert engine.conversation_sources(OWNER, user, session='s', turn='u') == sorted(sources)
    assert not engine.conversation_sources(CONTACT, user, session='s', turn='u')
    assert not engine.conversation_sources(OWNER, user, session='s', turn='different')
    assert not engine.conversation_sources(OWNER, user, session='other', turn='u')


def test_multimodal_native_import_links_normalized_legacy_evidence(engine, tmp_path):
    user = [{'type': 'text', 'text': '我喜欢黑咖啡'}, {'type': 'image_url', 'image_url': {'url': 'image'}}]
    source = engine.enqueue(OWNER, '我喜欢黑咖啡', session='s', turn='u1')
    with engine.store.transaction() as db:
        db.execute('DELETE FROM source_turns')
        db.execute("UPDATE sources SET content='',status='done'")
    path = tmp_path/'state.db'
    encoded = '\x00json:' + json.dumps(user, ensure_ascii=False)
    native(path, [(1, 'user', encoded, 'u1', 1, 0), (2, 'assistant', '收到', 'a1', 1, 0)])
    assert import_sessions(engine, path)['imported'] == 1
    row = engine.store.rows('SELECT * FROM chat_turns')[0]
    assert row['user_text'] == '我喜欢黑咖啡'
    assert json.loads(row['source_ids']) == [source]
    assert json.loads(bytes(row['original']))['messages'][0]['content'] == encoded


def test_native_import_excludes_rewound_users_replies_and_boundaries(engine, tmp_path):
    path = tmp_path/'state.db'
    native(path, [(1, 'user', '保留的用户原话', 'u1', 0, 1),
                  (2, 'assistant', '保留的压缩原话', 'a1', 0, 1),
                  (3, 'user', '撤销的用户原话', 'u2', 0, 0),
                  (4, 'assistant', '撤销的助手原话', 'a2', 0, 0),
                  (5, 'assistant', '有效的后续回答', 'a3', 1, 0),
                  (6, 'user', '新的有效问题', 'u3', 1, 0),
                  (7, 'assistant', '新的有效回答', 'a4', 1, 0)])
    assert import_sessions(engine, path)['imported'] == 2
    rows = engine.store.rows('SELECT * FROM chat_turns ORDER BY created')
    assert rows[0]['assistant_text'] == '保留的压缩原话\n\n有效的后续回答'
    assert '撤销' not in str(rows)
    assert rows[1]['user_text'] == '新的有效问题'


@pytest.mark.parametrize('rewind', ['user', 'assistant', 'missing'])
def test_existing_native_archive_rewind_hides_all_projections_and_preserves_original(engine, tmp_path, rewind):
    user = 'GraMem 使用 SQLite'
    source = engine.enqueue(OWNER, user, session='s', turn='u1')
    fact = engine.remember(OWNER, user, slot='architecture')
    with engine.store.transaction() as db:
        db.execute('UPDATE memories SET source=? WHERE id=?', (source, fact))
    path = tmp_path/'state.db'
    native(path, [(1, 'user', user, 'u1', 1, 0), (2, 'assistant', '已讨论项目', 'a1', 1, 0)])
    import_sessions(engine, path)
    archive = Chats(engine)
    assert archive.process_one()
    row = engine.store.rows('SELECT * FROM chat_turns')[0]
    task = Backfill(engine)
    with engine.store.transaction() as db:
        db.execute('UPDATE chat_turns SET organized=0 WHERE id=?', (row['id'],))
    task.request(OWNER)
    with sqlite3.connect(path) as db:
        if rewind == 'missing':
            db.execute('DELETE FROM messages')
        else:
            db.execute('UPDATE messages SET active=0,compacted=0 WHERE role=?', (rewind,))
    # A bulk cursor past the row must still reconcile existing imports.
    assert import_sessions(engine, path, after_id=100)['imported'] == 0
    assert not archive.search(OWNER)['items']
    assert not archive.overview(OWNER)['timeline']
    for reader in [archive.read, archive.original]:
        with pytest.raises(PermissionError):
            reader(OWNER, row['id'])
    assert not engine.recall(OWNER, 'GraMem', historical=True)['context']
    assert not engine.list(OWNER)
    assert 'SQLite' not in str(Network(engine).query(OWNER))
    assert not archive.process_one()
    assert task.step(path)
    assert task.step(path)
    assert task.status(OWNER)['job']['state'] == 'completed'
    assert task.status(OWNER)['job']['protected'] == 1
    saved = engine.store.rows('SELECT original,sha256 FROM chat_turns WHERE id=?', (row['id'],))[0]
    assert bytes(saved['original']) == bytes(row['original']) and saved['sha256'] == row['sha256']


def test_rewind_during_classification_cannot_erase_original(engine):
    archive = Chats(engine)
    id = archive.capture(OWNER, '禁提标记事项', '原始回复', session='s', turn='u', platform='teams')
    original = engine.store.rows('SELECT original FROM chat_turns WHERE id=?', (id,))[0]['original']
    engine.exclude(OWNER, 'topic', state='deleted')
    engine.model = FakeModel({'turns': [{'id': id, 'allowed': False, 'erase': True}], 'items': []})
    engine.model.before_return = lambda: archive.reconcile_native(OWNER, id, 1, False)
    assert archive.process_one()
    assert bytes(engine.store.rows('SELECT original FROM chat_turns WHERE id=?', (id,))[0]['original']) == bytes(original)
    assert not archive.process_one()


def test_provider_archive_detects_reply_only_rewind_without_native_snapshot(engine, tmp_path):
    archive = Chats(engine)
    id = archive.capture(OWNER, '保留用户输入', '撤销助手原话', session='s', turn='u1', platform='teams')
    original = archive.original(OWNER, id)[1]
    path = tmp_path/'state.db'
    native(path, [(1, 'user', '保留用户输入', 'u1', 1, 0),
                  (2, 'assistant', '撤销助手原话', 'a1', 0, 0)])
    import_sessions(engine, path)
    assert not archive.search(OWNER)['items']
    assert bytes(engine.store.rows('SELECT original FROM chat_turns WHERE id=?', (id,))[0]['original']) == original


def test_schema_six_upgrade_adds_links_without_changing_archive(engine):
    id = Chats(engine).capture(OWNER, '原话', '答复', session='s', turn='u', platform='teams')
    row = engine.store.rows('SELECT * FROM chat_turns WHERE id=?', (id,))[0]
    path = engine.store.path
    engine.close()
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE source_turns')
        db.execute('DROP TABLE chat_native_state')
        db.execute('PRAGMA user_version=6')
    upgraded = Engine(path)
    try:
        assert upgraded.store.rows('PRAGMA user_version')[0]['user_version'] == 8
        assert upgraded.store.rows('SELECT * FROM chat_turns WHERE id=?', (id,))[0] == row
        assert upgraded.store.rows('SELECT * FROM source_turns') == []
        assert upgraded.store.rows('SELECT * FROM chat_native_state') == []
    finally:
        upgraded.close()
