"""Regressions for the three memory defects found in the 2026-10 review."""
import threading

import pytest
from test_engine import CONTACT, OWNER, FakeModel, item
from test_provider import make_provider  # noqa: F401

from gramem.engine import Engine
from gramem.knowledge import Knowledge


@pytest.mark.parametrize('control', ['document', 'chunk'])
def test_control_classifier_hides_suppressed_document_and_derived_values(make_provider, control):  # noqa: F811
    provider = make_provider(platform='cli', chat_type='direct')
    kb = Knowledge(provider.engine)
    doc = kb.ingest(OWNER, data='停用正文标记：青藤项目采用银杏存储。'.encode(), filename='private.md')
    provider.engine.remember(OWNER, '派生正文标记：青藤项目使用银杏存储。', targets=doc['ids'], action='MERGE', slot='summary')
    slot = 'document:' + doc['id'] if control == 'document' else provider.engine.get(OWNER, doc['ids'][0])['slot']
    provider.engine.exclude(OWNER, slot, state='suppressed')
    captured = []
    class Capture(FakeModel):
        def extract(self, prompt, payload):
            captured.append(payload)
            return {'request': False}
    provider.engine.model = Capture()
    provider.on_turn_start(1, '请忘记另一个主题')
    assert captured
    assert not any('正文标记' in r['fact'] for r in captured[-1]['memories'])
    assert not any('private.md' in r['fact'] for r in captured[-1]['memories'])


@pytest.mark.parametrize('old_outcome', ['success', 'failure', 'after_new_done'])
def test_expired_worker_cannot_commit_or_reset_new_claim(tmp_path, old_outcome):
    now = [10000.0]
    class Blocking(FakeModel):
        def __init__(self, content):
            super().__init__({'memories': [item(content)]})
            self.started = threading.Event()
            self.release = threading.Event()
            self.fail = False
        def extract(self, prompt, payload):
            self.started.set()
            assert self.release.wait(5), 'test worker did not release'
            if self.fail:
                raise RuntimeError('old worker failed after takeover')
            return self.result
    old_model = Blocking('我偏好简短解释')
    new_model = Blocking('我偏好详细解释')
    path = tmp_path / 'memory.sqlite'
    old = Engine(path, model=old_model, clock=lambda: now[0])
    new = Engine(path, model=new_model, clock=lambda: now[0])
    threads = []
    try:
        source = old.enqueue(OWNER, '我偏好简短解释；我偏好详细解释', session='s', turn='1')
        threads = [threading.Thread(target=old.process_one), threading.Thread(target=new.process_one)]
        threads[0].start()
        assert old_model.started.wait(2)
        now[0] += max(300, old.config.timeout * 3) + 1
        threads[1].start()
        assert new_model.started.wait(2)
        if old_outcome == 'after_new_done':
            new_model.release.set()
            threads[1].join(2)
        old_model.fail = old_outcome == 'failure'
        old_model.release.set()
        threads[0].join(2)
        if old_outcome != 'after_new_done':
            state = old.store.rows('SELECT status,attempts FROM sources WHERE id=?', (source,))[0]
            assert state == {'status': 'working', 'attempts': 2}
        new_model.release.set()
        threads[1].join(2)
        assert not any(t.is_alive() for t in threads)
        assert old.store.rows('SELECT status FROM sources WHERE id=?', (source,)) == [{'status': 'done'}]
        assert [r['content'] for r in old.list(OWNER)] == ['我偏好详细解释']
    finally:
        old_model.release.set()
        new_model.release.set()
        for thread in threads:
            if thread.ident is not None:
                thread.join(5)
        old.close()
        new.close()


def test_new_document_version_archives_transitive_summaries_and_keeps_history(tmp_path):
    engine = Engine(tmp_path / 'memory.sqlite')
    kb = Knowledge(engine)
    try:
        first = kb.ingest(OWNER, data='当前方案采用苹果存储。'.encode(), filename='architecture.md')
        contact = kb.ingest(CONTACT, data='当前方案采用苹果存储。'.encode(), filename='architecture.md')
        summary = engine.remember(OWNER, '摘要：当前方案采用苹果存储。', targets=first['ids'], action='MERGE', slot='summary')
        derived = engine.remember(OWNER, '派生摘要：当前方案采用苹果存储。', targets=[summary], action='MERGE', slot='derived')
        second = kb.ingest(OWNER, data='当前方案改用橙子存储。'.encode(), filename='architecture.md')
        assert engine.get(OWNER, derived)['status'] == 'superseded'
        assert '苹果' not in engine.recall(OWNER, '当前方案')['context']
        assert '橙子' in engine.recall(OWNER, '当前方案')['context']
        assert '苹果' in engine.recall(OWNER, '当前方案', historical=True)['context']
        assert kb.original(OWNER, first['id'])[1] == '当前方案采用苹果存储。'.encode()
        assert engine.get(CONTACT, contact['ids'][0])['status'] == 'active'
        assert second['version'] == 2
    finally:
        engine.close()
