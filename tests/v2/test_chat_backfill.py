"""Bulk chat organization survives restart and respects provenance, scope and exclusions."""

import hashlib
import json
import sqlite3
import threading

import pytest
from test_chats import Organizer, capture
from test_engine import CONTACT, GROUP, OWNER

from gramem.chat_backfill import Backfill
from gramem.chats import Chats
from gramem.config import Config
from gramem.engine import Engine


class Model(Organizer):
    def extract(self, prompt, payload):
        if 'turns' in payload:
            self.calls += 1
        return super().extract(prompt,payload)


@pytest.fixture
def engine(tmp_path):
    e = Engine(tmp_path/'memory.sqlite',Config(aliases={'teams:verified':'owner'}),model=Model(),clock=lambda:1000)
    yield e
    e.close()


def native(path, *, turns=12):
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE sessions(id,source,user_id,chat_type,origin_json,started_at,chat_id);
        CREATE TABLE messages(id INTEGER PRIMARY KEY,session_id,role,content,timestamp,_compressed_summary,message_uid,platform_message_id);
        INSERT INTO sessions VALUES('s','teams','verified','dm','{}',1,'d');
        INSERT INTO sessions VALUES('other','teams','guest','dm','{}',1,'d');
        INSERT INTO sessions VALUES('group','teams','verified','channel','{}',1,'d');''')
        for i in range(turns):
            for role,content,offset in [('user','GraMem 原话 '+str(i),0),('assistant','讨论记录 '+str(i),.1)]:
                db.execute('INSERT INTO messages(session_id,role,content,timestamp,_compressed_summary,message_uid) VALUES(?,?,?,?,0,?)',
                           ('s',role,content,i+1+offset,role+str(i)))
        for session in ['other','group']:
            db.execute('INSERT INTO messages(session_id,role,content,timestamp,_compressed_summary,message_uid) VALUES(?,?,?,?,0,?)',
                       (session,'user','不得合并的独立记录',3,session+'u'))
            db.execute('INSERT INTO messages(session_id,role,content,timestamp,_compressed_summary,message_uid) VALUES(?,?,?,?,0,?)',
                       (session,'assistant','不同身份',4,session+'a'))
        db.execute("INSERT INTO messages(session_id,role,content,timestamp,_compressed_summary,message_uid) VALUES('s','user','新的未来对话',2000,0,'future-user')")
        db.execute("INSERT INTO messages(session_id,role,content,timestamp,_compressed_summary,message_uid) VALUES('s','assistant','不在本次范围',2001,0,'future-assistant')")


def pump(e, path=None, *, maximum=200):
    task = Backfill(e)
    for _ in range(30):
        task.step(path,maximum=maximum)
        status = task.status(OWNER)
        if status['job']['state'] == 'completed':
            return status['job']
    raise AssertionError(task.status(OWNER))


def test_one_click_imports_every_chunk_scoped_to_old_history_and_preserves_originals(engine,tmp_path):
    path = tmp_path/'state.db'
    native(path,turns=17)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    task = Backfill(engine)
    assert task.request(OWNER)['job']['state']=='importing'
    assert task.step(path,maximum=3)
    assert task.status(OWNER)['job']['imported']==3
    result = pump(engine,path,maximum=3)
    assert result['total']==result['done']==result['ready']==result['imported']==17
    assert result['remaining']==0 and result['skipped_sessions']==1
    assert engine.model.calls==3  # 8 + 8 + 1 turns, not one blocking HTTP request.
    assert Chats(engine).search(OWNER)['total']==17
    assert not Chats(engine).search(CONTACT)['items']
    assert '未来' not in str(Chats(engine).search(OWNER))
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    for row in engine.store.rows('SELECT original,sha256 FROM chat_turns'):
        assert hashlib.sha256(bytes(row['original'])).hexdigest()==row['sha256']


def test_repeated_click_reuses_active_job_and_skips_done_records(engine):
    archive, task = Chats(engine), Backfill(engine)
    finished = capture(archive,turn='done')
    assert archive.process_one()
    calls = engine.model.calls
    for i in range(10):
        capture(archive,turn=str(i))
    capture(archive,p=CONTACT,session='other')
    first = task.request(OWNER)['job']
    assert task.request(OWNER)['job']['id']==first['id']
    assert first['total']==10
    result = pump(engine)
    assert result['done']==10 and engine.model.calls==calls+2
    assert engine.store.rows('SELECT organized FROM chat_turns WHERE id=?',(finished,))[0]['organized']==1
    assert engine.store.rows('SELECT organized FROM chat_turns WHERE principal=?',(CONTACT.key,))[0]['organized']==0
    assert task.request(OWNER)['job']['total']==0
    result = pump(engine)
    assert result['done']==0 and engine.model.calls==calls+2


def test_restart_retains_task_and_failed_batches_can_retry(engine,tmp_path):
    archive, task = Chats(engine), Backfill(engine)
    capture(archive)
    task.request(OWNER)
    task.step()
    engine.model.extract = lambda prompt,payload:{'turns':[],'items':[]}
    assert not task.step()
    progress = task.status(OWNER)['job']
    assert progress['state']=='processing' and progress['retrying']==progress['remaining']==1
    assert progress['error']=='records_retrying'
    path = engine.store.path
    restored = Engine(path,engine.config,model=Model(),clock=lambda:1001)
    try:
        job = Backfill(restored)
        assert job.status(OWNER)['job']['id']==progress['id']
        assert job.retry(OWNER)['job']['retrying']==0
        assert job.step()
        assert job.status(OWNER)['job']['state']=='completed'
    finally:
        restored.close()


def test_no_model_does_not_falsely_complete_organization(engine):
    archive, task = Chats(engine), Backfill(engine)
    capture(archive)
    engine.model.available=False
    assert archive.process_one()
    assert engine.store.rows('SELECT organized FROM chat_turns')[0]['organized']==0
    task.request(OWNER)
    task.step()
    assert not task.step()
    assert task.status(OWNER)['job']['error']=='model_unavailable'
    assert task.status(OWNER)['job']['remaining']==1
    engine.model.available=True
    task.retry(OWNER)
    assert pump(engine)['done']==1


def test_suppressed_and_secret_turns_keep_originals_but_cannot_surface(engine):
    archive, task = Chats(engine), Backfill(engine)
    private = capture(archive,'禁提标记：旧 GraMem 事项')
    secret = capture(archive,'api_key=sk-example-secret-private-12345',turn='secret')
    capture(archive,'GraMem 正常讨论',turn='normal')
    originals = {r['id']:bytes(r['original']) for r in engine.store.rows('SELECT id,original FROM chat_turns')}
    engine.exclude(OWNER,'private',state='suppressed')
    task.request(OWNER)
    result = pump(engine)
    assert result['total']==result['done']==3 and result['protected']==2
    assert archive.search(OWNER)['total']==1
    for id in [private,secret]:
        assert bytes(engine.store.rows('SELECT original FROM chat_turns WHERE id=?',(id,))[0]['original'])==originals[id]
        with pytest.raises(PermissionError):
            archive.original(OWNER,id)
    assert '禁提标记' not in json.dumps(task.status(OWNER),ensure_ascii=False)


def test_group_and_disabled_archive_cannot_request_bulk_processing(engine):
    with pytest.raises(PermissionError):
        Backfill(engine).request(GROUP)
    engine.config.chat_auto_archive=False
    with pytest.raises(RuntimeError):
        Backfill(engine).request(OWNER)


def test_expired_job_worker_cannot_overwrite_new_workers_progress(engine):
    now = [1000]
    engine.clock=lambda:now[0]
    capture(Chats(engine))
    task=Backfill(engine)
    task.request(OWNER)
    task.step()
    started,release=threading.Event(),threading.Event()
    def hold():
        started.set()
        assert release.wait(5)
    engine.model.before_return=hold
    other=Engine(engine.store.path,engine.config,model=Model(),clock=lambda:now[0])
    thread=threading.Thread(target=task.step)
    try:
        thread.start()
        assert started.wait(2)
        now[0]+=301
        assert Backfill(other).step()
        release.set()
        thread.join(2)
        result=Backfill(other).status(OWNER)['job']
        assert result['state']=='completed' and result['done']==1
        assert len(other.store.rows('SELECT * FROM chat_summaries'))==1
    finally:
        release.set()
        thread.join(5)
        other.close()


def test_missing_native_history_is_reported_without_losing_archived_work(engine,tmp_path):
    capture(Chats(engine))
    task=Backfill(engine)
    task.request(OWNER)
    result=pump(engine,tmp_path/'missing.db')
    assert result['done']==1 and result['error']=='history_unavailable'


def test_schema_five_migrates_without_reprocessing_finished_archives(tmp_path):
    path=tmp_path/'memory.sqlite'
    first=Engine(path,model=Model())
    try:
        id=capture(Chats(first))
        assert Chats(first).process_one()
        original=first.store.rows('SELECT original FROM chat_turns WHERE id=?',(id,))[0]['original']
    finally:
        first.close()
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE chat_backfill_items')
        db.execute('DROP TABLE chat_backfill_jobs')
        db.execute('PRAGMA user_version=5')
    restored=Engine(path,model=Model())
    try:
        assert restored.store.rows('PRAGMA user_version')[0]['user_version']==8
        assert restored.store.rows('SELECT original FROM chat_turns WHERE id=?',(id,))[0]['original']==original
        assert Backfill(restored).status(OWNER)['pending']==0
        Backfill(restored).request(OWNER)
        assert pump(restored)['total']==0 and restored.model.calls==0
    finally:
        restored.close()
