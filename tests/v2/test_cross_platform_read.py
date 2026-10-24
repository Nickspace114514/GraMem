"""Cross-platform history import and lossless, policy-checked tool pagination."""

import json
import sqlite3

import pytest
from test_chats import Organizer
from test_context_gramem_fixes import native
from test_engine import OWNER, FakeModel
from test_provider import make_provider  # noqa: F401

from gramem.chat_import import import_sessions
from gramem.chats import Chats
from gramem.config import Config
from gramem.engine import Engine
from gramem.identity_migration import migrate_verified_contact
from gramem.tokens import count


def test_telegram_history_import_uses_verified_identity_and_skips_shared(tmp_path):
    path = tmp_path / 'state.db'
    native(path, [(1, 'user', 'Telegram 历史问题', 'u1', 1, 0),
                  (2, 'assistant', '历史回答', 'a1', 1, 0)])
    with sqlite3.connect(path) as db:
        db.execute("UPDATE sessions SET source='telegram'")
    cfg = Config(aliases={'telegram:verified': 'owner'})
    engine = Engine(tmp_path / 'memory.sqlite', cfg, model=Organizer())
    try:
        assert import_sessions(engine, path, principal=OWNER)['imported'] == 1
        assert Chats(engine).process_one()
        assert Chats(engine).search(OWNER, platform='telegram')['total'] == 1
        outsider = cfg.principal('telegram', 'unverified')
        assert Chats(engine).search(outsider)['total'] == 0
        id = engine.store.rows('SELECT id FROM chat_turns')[0]['id']
        with pytest.raises(PermissionError):
            Chats(engine).read(outsider, id)
        with sqlite3.connect(path) as db:
            db.execute("UPDATE sessions SET chat_type='group'")
        assert import_sessions(engine, path)['skipped_sessions'] == 1
    finally:
        engine.close()


def test_chat_read_continuations_reconstruct_both_speakers_within_budget(make_provider):  # noqa: F811
    provider = make_provider(platform='cli', chat_type='direct')
    user = '用户原话：中文🙂、引号"和换行\n' * 100
    assistant = '助手回复：保留完整末尾，路径\\与🙂\n' * 140
    archive = Chats(provider.engine)
    id = archive.capture(OWNER, user, assistant, session='other-platform-session',
                         turn='u1', platform='telegram')
    expected = archive.read(OWNER, id)
    assembled = {'user': '', 'assistant': ''}
    start = 0
    for _ in range(100):
        raw = provider.handle_tool_call('gramem_chats', {'action': 'read', 'id': id, 'start': start})
        page = json.loads(raw)
        assert count(raw) <= provider.config.recall_tokens
        assert page['start'] == start
        for speaker in assembled:
            assembled[speaker] += page[speaker]
        if page['next'] is None:
            assert not page['truncated']
            break
        assert page['truncated'] and page['next'] > start
        start = page['next']
    else:
        pytest.fail('read did not finish')
    assert assembled == {speaker: expected[speaker] for speaker in assembled}
    # Every continuation rechecks visibility, including policy changes mid-read.
    provider.engine.exclude(OWNER, '*', state='suppressed')
    assert 'error' in json.loads(provider.handle_tool_call(
        'gramem_chats', {'action': 'read', 'id': id, 'start': start}))


@pytest.mark.parametrize('start', [-1, True, 1.5, 10000])
def test_chat_read_rejects_invalid_offsets(make_provider, start):  # noqa: F811
    provider = make_provider(platform='cli', chat_type='direct')
    id = Chats(provider.engine).capture(OWNER, '问题', '回答', session='s', turn='1', platform='cli')
    result = json.loads(provider.handle_tool_call('gramem_chats', {'action': 'read', 'id': id, 'start': start}))
    assert 'error' in result


def test_optional_entity_labels_cannot_poison_reviewed_chat(tmp_path):
    engine = Engine(tmp_path / 'memory.sqlite')
    try:
        archive = Chats(engine)
        engine.exclude(OWNER, 'private', state='suppressed')
        id = archive.capture(OWNER, '讨论 GraMem 与 SQLite', '好的',
                             session='s', turn='1', platform='telegram')
        engine.model = FakeModel({
            'turns': [{'id': id, 'allowed': True}], 'controls': [],
            'items': [{'turn_id': id, 'text': '讨论数据库', 'topic': '技术',
                       'evidence': '讨论 GraMem 与 SQLite',
                       'entities': ['Gramem', 'SQLite', None, {}, 'SQLite']}]})
        assert archive.process_one()
        assert archive.read(OWNER, id)['user'] == '讨论 GraMem 与 SQLite'
        summary = json.loads(engine.store.rows('SELECT content FROM chat_summaries')[0]['content'])
        assert summary[0]['entities'] == ['SQLite']
        engine.exclude(OWNER, '*', state='suppressed')
        assert archive.process_one()
        with pytest.raises(PermissionError):
            archive.read(OWNER, id)
    finally:
        engine.close()


def test_verified_identity_migration_preserves_provenance_and_rewind(tmp_path):
    cfg = Config(aliases={'telegram:verified': 'owner'})
    engine = Engine(tmp_path / 'memory.sqlite', cfg, model=Organizer())
    archive = Chats(engine)
    old = Config().principal('telegram', 'verified')
    try:
        source = engine.enqueue(old, '讨论 GraMem', session='s', turn='1')
        with engine.store.transaction() as db:
            db.execute("UPDATE sources SET status='done',content='' WHERE id=?", (source,))
        fact = engine.remember(old, 'GraMem 使用 SQLite', slot='architecture')
        with engine.store.transaction() as db:
            db.execute('UPDATE memories SET source=? WHERE id=?', (source, fact))
        ids = [archive.capture(old, '讨论 GraMem', '好的', session='s', turn=str(i),
                               platform='telegram', source_ids=[source] if i == 1 else []) for i in (1, 2)]
        archive.reconcile_native(old, ids[1], 5, False)
        originals = {id: engine.store.rows('SELECT original,sha256 FROM chat_turns WHERE id=?', (id,))[0] for id in ids}
        engine.exclude(OWNER, 'unrelated', state='suppressed')
        result = migrate_verified_contact(engine, 'telegram', 'verified')
        assert result['counts']['memories'] == 1 and result['counts']['chat_turns'] == 2
        assert archive.search(old)['total'] == archive.search(OWNER)['total'] == 0
        assert archive.process_one()
        assert archive.search(OWNER)['total'] == 1
        for id in ids:
            new = result['chat_ids'][id]
            assert engine.store.rows('SELECT original,sha256 FROM chat_turns WHERE id=?', (new,))[0] == originals[id]
        assert engine.conversation_sources(OWNER, '讨论 GraMem', session='s', turn='1') == [source]
        assert engine.store.rows('SELECT principal FROM memories WHERE id=?', (fact,))[0]['principal'] == OWNER.key
        assert not engine.store.rows('PRAGMA foreign_key_check')
        assert migrate_verified_contact(engine, 'telegram', 'verified')['counts']['chat_turns'] == 0
        with pytest.raises(PermissionError):
            migrate_verified_contact(engine, 'telegram', 'unverified')
    finally:
        engine.close()


def test_migration_collision_rolls_back_without_losing_either_original(tmp_path):
    engine = Engine(tmp_path / 'memory.sqlite', Config(aliases={'telegram:v': 'owner'}))
    archive = Chats(engine)
    old = Config().principal('telegram', 'v')
    try:
        a = archive.capture(old, '旧原文', '旧回答', session='s', turn='1', platform='telegram')
        b = archive.capture(OWNER, '新原文', '新回答', session='s', turn='1', platform='telegram')
        with pytest.raises(ValueError, match='overlapping'):
            migrate_verified_contact(engine, 'telegram', 'v')
        assert archive.read(old, a)['user'] == '旧原文'
        assert archive.read(OWNER, b)['user'] == '新原文'
    finally:
        engine.close()


def test_native_rewind_retires_failed_sources_without_resurrecting_text(tmp_path):
    engine = Engine(tmp_path / 'memory.sqlite', model=Organizer())
    archive = Chats(engine)
    try:
        source = engine.enqueue(OWNER, 'GraMem 历史问题', session='s', turn='1')
        id = archive.capture(OWNER, 'GraMem 历史问题', '回答', session='s', turn='1',
                             platform='telegram', source_ids=[source])
        original = engine.store.rows('SELECT original FROM chat_turns WHERE id=?', (id,))[0]
        archive.reconcile_native(OWNER, id, 1, False)
        # Repeated reconciliation also repairs failures left by earlier releases.
        with engine.store.transaction() as db:
            db.execute("UPDATE sources SET status='failed',error='model_request' WHERE id=?", (source,))
        archive.reconcile_native(OWNER, id, 1, False)
        assert not engine.process_one()
        row = engine.store.rows('SELECT status,error,content,result FROM sources WHERE id=?', (source,))[0]
        assert row['status'] == 'redacted' and row['error'] is None and row['content'] == ''
        assert json.loads(row['result'])['outcome'] == 'native_inactive'
        assert archive.overview(OWNER)['jobs'] == [{'status': 'native_inactive', 'count': 1}]
        assert engine.store.rows('SELECT original FROM chat_turns WHERE id=?', (id,))[0] == original
        assert archive.search(OWNER)['total'] == 0
    finally:
        engine.close()


def test_rewind_does_not_retire_a_source_still_linked_to_live_evidence(tmp_path):
    engine = Engine(tmp_path / 'memory.sqlite')
    archive = Chats(engine)
    try:
        source = engine.enqueue(OWNER, 'GraMem 历史问题', session='s', turn='1')
        ids = [archive.capture(OWNER, 'GraMem 历史问题', '回答', session='s', turn=str(i),
                               platform='telegram', source_ids=[source]) for i in (1, 2)]
        archive.reconcile_native(OWNER, ids[0], 1, False)
        assert engine.store.rows('SELECT status FROM sources WHERE id=?', (source,))[0]['status'] == 'pending'
        archive.reconcile_native(OWNER, ids[1], 3, False)
        assert engine.store.rows('SELECT status FROM sources WHERE id=?', (source,))[0]['status'] == 'redacted'
    finally:
        engine.close()
