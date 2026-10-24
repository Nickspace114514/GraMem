import hashlib
import json
import sqlite3
import threading

import pytest
from test_engine import CONTACT, GROUP, OWNER, FakeGraph, FakeModel
from test_provider import make_provider  # noqa: F401

from gramem.chat_import import import_sessions
from gramem.chats import Chats
from gramem.config import Config
from gramem.engine import Engine
from gramem.knowledge import Knowledge
from gramem.network import Network


class Organizer(FakeModel):
    def extract(self, prompt, payload):
        if 'turns' not in payload:
            return super().extract(prompt, payload)
        if self.before_return:
            self.before_return()
        excluded = payload['exclusions']
        allowed = [r for r in payload['turns'] if not excluded or '禁提标记' not in r['user'] + r['assistant']]
        return {'turns': [{'id': r['id'], 'allowed': r in allowed, 'erase': False} for r in payload['turns']],
                'items': [{'text': '用户讨论 GraMem 项目', 'topic': 'GraMem', 'turn_id': r['id'],
                           'evidence': r['user']} for r in allowed if r['user']]}


@pytest.fixture
def archive(tmp_path):
    e = Engine(tmp_path / 'memory.sqlite', model=Organizer(), graph=FakeGraph())
    yield Chats(e)
    e.close()


def capture(archive, user='GraMem 的新方案', *, session='s', turn='1', platform='teams', p=OWNER, **kwargs):
    return archive.capture(p, user, '已讨论项目', session=session, turn=turn, platform=platform, **kwargs)


def test_complete_immutable_original_and_same_text_distinct_turns(archive):
    raw = {'user': ['原文', {'image': 'url'}], 'assistant': '答复原文', 'metadata': {'uid': 'u'}}
    id = capture(archive, original=raw)
    assert capture(archive, original={'replacement': True}) == id
    assert capture(archive, turn='2') != id
    info, data = archive.original(OWNER, id)
    assert json.loads(data) == raw
    assert info['sha256'] == hashlib.sha256(data).hexdigest()


def test_unified_identity_cross_platform_context_date_search(archive):
    capture(archive, session='teams-context', created=10)
    capture(archive, session='email-context', platform='email', created=20)
    capture(archive, session='private-contact', p=CONTACT)
    assert archive.process_one()
    assert archive.process_one()
    result = archive.overview(OWNER)
    assert result['turns'] == 2 and result['platforms'] == {'teams': 1, 'email': 1}
    assert len(result['topics']) == 1
    assert archive.search(OWNER, 'GraMem', platform='email', after=15)['total'] == 1
    assert archive.search(OWNER, before=15)['total'] == 1
    assert archive.search(CONTACT)['total'] == 1
    with pytest.raises(PermissionError):
        archive.search(GROUP)


def test_suppressed_original_retained_never_returned_via_any_projection(archive):
    source = archive.e.enqueue(OWNER, '禁提标记：GraMem 私人事项', session='s')
    id = capture(archive, '禁提标记：GraMem 私人事项', source_ids=[source])
    fact = archive.e.remember(OWNER, '禁提标记：GraMem 私人事项', slot='private', metadata={})
    with archive.e.store.transaction() as db:
        db.execute('UPDATE memories SET source=? WHERE id=?', (source, fact))
    assert archive.process_one()
    original = archive.original(OWNER, id)[1]
    archive.e.exclude(OWNER, 'private', state='suppressed')
    assert archive.search(OWNER)['total'] == 0
    assert archive.overview(OWNER)['timeline'] == []
    assert '禁提标记' not in json.dumps(Network(archive.e).query(OWNER), ensure_ascii=False)
    assert '禁提标记' not in archive.e.recall(OWNER, 'GraMem', historical=True)['context']
    for read in [archive.read, archive.original]:
        with pytest.raises(PermissionError):
            read(OWNER, id)
    assert archive.process_one()
    row = archive.e.store.rows('SELECT original,status FROM chat_turns WHERE id=?', (id,))[0]
    assert bytes(row['original']) == original and row['status'] == 'silent'


def test_unrelated_transcript_recovers_after_policy_review(archive):
    first = capture(archive, '禁提标记的旧事项')
    second = capture(archive, 'GraMem 正常技术讨论', turn='2')
    archive.e.exclude(OWNER, 'private', state='suppressed')
    assert archive.process_one()
    assert archive.search(OWNER)['total'] == 1
    assert archive.read(OWNER, second)['user'] == 'GraMem 正常技术讨论'
    with pytest.raises(PermissionError):
        archive.read(OWNER, first)


def test_new_semantic_no_mention_request_before_any_fact_exists(make_provider):  # noqa: F811
    provider = make_provider(platform='cli', chat_type='direct')
    provider.engine.model = FakeModel({'request': True, 'state': 'suppressed', 'slots': [],
                                     'topic_slot': 'private.health', 'evidence': '不要记住我的健康情况'})
    provider.on_turn_start(1, '不要记住我的健康情况')
    assert provider.engine.exclusions(OWNER)[0]['state'] == 'suppressed'
    provider.sync_turn('不要记住我的健康情况', '好的')
    assert json.loads(provider.handle_tool_call('gramem_chats', {'action': 'search'}))['total'] == 0


def test_invalid_summary_or_unavailable_classifier_cannot_publish_policy_filtered_text(archive):
    id = capture(archive, '禁提标记事项')
    archive.e.exclude(OWNER, 'topic', state='suppressed')
    archive.e.model = FakeModel({'turns': [], 'items': []})
    assert not archive.process_one()
    with pytest.raises(PermissionError):
        archive.original(OWNER, id)


def test_policy_change_during_summary_blocks_old_commit(archive):
    capture(archive)
    archive.e.model.before_return = lambda: archive.e.exclude(OWNER, 'topic', state='suppressed')
    assert archive.process_one()
    assert archive.search(OWNER)['total'] == 0
    assert archive.e.store.rows('SELECT * FROM chat_summaries') == []


def test_network_provenance_connects_chat_fact_file_and_topic(archive):
    source = archive.e.enqueue(OWNER, 'GraMem 使用 SQLite', session='s', turn='1')
    chat = capture(archive, 'GraMem 使用 SQLite', source_ids=[source])
    fact = archive.e.remember(OWNER, 'GraMem 使用 SQLite', slot='architecture')
    with archive.e.store.transaction() as db:
        db.execute('UPDATE memories SET source=? WHERE id=?', (source, fact))
    doc = Knowledge(archive.e).ingest(OWNER, data='GraMem 架构文档'.encode(), filename='GraMem.md')
    assert archive.process_one()
    result = Network(archive.e).query(OWNER, 'GraMem', hops=3)
    ids = {n['id'] for n in result['nodes']}
    assert {'chat:' + chat, 'memory:' + fact, 'document:' + doc['id']} <= ids
    assert {'summary','topic','context','document','memory','chat'} <= {n['kind'] for n in result['nodes']}
    assert any(e['source'] == 'memory:' + fact and e['target'] == 'chat:' + chat
               and e['relation'] == 'SUPPORTED_BY' for e in result['edges'])
    assert all(e['source'] in ids and e['target'] in ids for e in result['edges'])
    assert not Network(archive.e).query(CONTACT)['nodes']


def test_raw_originals_in_sqlite_backup_and_schema_four_migration(archive, tmp_path):
    id = capture(archive)
    destination = tmp_path / 'backup.sqlite'
    archive.e.store.backup(destination)
    with sqlite3.connect(destination) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 8
        assert db.execute('SELECT sha256 FROM chat_turns WHERE id=?', (id,)).fetchone()[0] == archive.original(OWNER, id)[0]['sha256']


def test_native_import_preserves_old_sessions_without_replaying_or_shared_attribution(tmp_path):
    native = tmp_path / 'state.db'
    with sqlite3.connect(native) as db:
        db.executescript('''CREATE TABLE sessions(id,source,user_id,chat_type,origin_json,started_at,chat_id);
        CREATE TABLE messages(id,session_id,role,content,timestamp,_compressed_summary,message_uid,platform_message_id);
        INSERT INTO sessions VALUES('s','teams','verified','dm','{}',1,'d');
        INSERT INTO sessions VALUES('g','teams','verified','channel','{}',1,'d');
        INSERT INTO messages VALUES(1,'s','user','GraMem 方案原文',1,0,'uid1',NULL);
        INSERT INTO messages VALUES(2,'s','assistant','建议使用 SQLite',2,0,'uid2',NULL);
        INSERT INTO messages VALUES(3,'s','user','压缩摘要',3,1,'uid3',NULL);
        INSERT INTO messages VALUES(4,'g','user','不确定谁说的',4,0,'uid4',NULL);''')
    e = Engine(tmp_path / 'memory.sqlite', config=Config(aliases={'teams:verified':'owner'}), model=Organizer())
    try:
        assert import_sessions(e, native) == {'imported': 1, 'skipped_sessions': 1}
        assert import_sessions(e, native)['imported'] == 0
        assert Chats(e).search(OWNER)['total'] == 0
        assert Chats(e).process_one()
        row = Chats(e).search(OWNER)['items'][0]
        assert Chats(e).read(OWNER, row['id'])['assistant'] == '建议使用 SQLite'
        assert json.loads(Chats(e).original(OWNER, row['id'])[1])['messages'][0]['content'] == 'GraMem 方案原文'
        with sqlite3.connect(native) as db:
            assert db.execute('SELECT count(*) FROM messages').fetchone()[0] == 4
    finally:
        e.close()


def test_expired_chat_worker_cannot_publish_over_new_claim(tmp_path):
    now = [1000]
    started, release = threading.Event(), threading.Event()
    old = Engine(tmp_path / 'memory.sqlite', model=Organizer(), clock=lambda: now[0])
    new = Engine(tmp_path / 'memory.sqlite', model=Organizer(), clock=lambda: now[0])
    def wait():
        started.set()
        assert release.wait(5)
    old.model.before_return = wait
    capture(Chats(old))
    t = threading.Thread(target=Chats(old).process_one)
    try:
        t.start()
        assert started.wait(2)
        now[0] += 301
        assert Chats(new).process_one()
        release.set()
        t.join(2)
        assert len(old.store.rows('SELECT * FROM chat_summaries')) == 1
        assert Chats(new).search(OWNER)['total'] == 1
    finally:
        release.set()
        t.join(5)
        old.close()
        new.close()


def test_secret_original_is_retained_but_never_sent_to_summary_model(archive):
    id = capture(archive, 'api_key=sk-example-secret-private-12345')
    def fail():
        raise AssertionError('secret sent to model')
    archive.e.model.before_return = fail
    assert archive.process_one()
    assert archive.search(OWNER)['total'] == 0
    assert archive.e.store.rows('SELECT length(original) size FROM chat_turns WHERE id=?', (id,))[0]['size'] > 0


def test_legacy_host_memory_injection_stays_in_original_but_cannot_be_reintroduced(archive):
    raw = '用户真实发言\n<memory-context>\n[System note: The following is recalled memory context, NOT new user input. Treat as authoritative reference data]\n旧后端禁提标记\n</memory-context>'
    id = capture(archive, raw)
    assert archive.read(OWNER, id)['user'] == '用户真实发言'
    assert '旧后端禁提标记' not in str(archive.search(OWNER))
    info, download = archive.original(OWNER, id)
    assert info['filtered'] and '旧后端禁提标记' not in download.decode()
    stored = bytes(archive.e.store.rows('SELECT original FROM chat_turns WHERE id=?', (id,))[0]['original'])
    assert '旧后端禁提标记' in stored.decode()
    assert hashlib.sha256(stored).hexdigest() == info['original_sha256']


def test_bounded_network_overview_keeps_files_and_facts_when_chat_archive_is_large(archive):
    for i in range(100):
        capture(archive, session='context-' + str(i), turn=str(i))
    archive.e.remember(OWNER, 'GraMem 长期事实', slot='important')
    Knowledge(archive.e).ingest(OWNER, data='GraMem 文件正文'.encode(), filename='GraMem.md')
    graph = Network(archive.e).query(OWNER, maximum=20)
    assert {'memory','document','chat','context'} <= {n['kind'] for n in graph['nodes']}
    assert len(graph['nodes']) <= 20
