"""Voice evidence, immutable originals, identity/policy boundaries and backup recovery."""

import hashlib
import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from test_chats import Organizer
from test_engine import CONTACT, GROUP, OWNER
from test_provider import make_provider  # noqa: F401

from gramem.chat_audio import ChatAudio, descriptors
from gramem.chat_import import import_sessions
from gramem.chats import Chats
from gramem.config import Config
from gramem.engine import Engine
from gramem.knowledge import Knowledge
from gramem.network import Network

WAVE = b'RIFF' + (40).to_bytes(4, 'little') + b'WAVEfmt ' + b'\0' * 40


def messages(path, text='GraMem 语音中的方案是长期保留原件。', *, cid='voice-1', result=True):
    return [{'role': 'assistant', 'content': '', 'tool_calls': [{'id': cid, 'function': {
                'name': 'text_to_speech', 'arguments': json.dumps({'text': text})}}]},
            {'role': 'tool', 'tool_call_id': cid, 'tool_name': 'text_to_speech',
             'content': json.dumps({'success': result, 'provider': 'test-tts', 'file_path': str(path)})},
            {'role': 'assistant', 'content': 'MEDIA:' + str(path)}]


@pytest.fixture
def voice(tmp_path):
    home = tmp_path / 'profile'
    e = Engine(home / 'gramem/memory.sqlite', Config(trusted_cli_owner=True), model=Organizer())
    path = home / 'cache/audio/original.wav'
    path.parent.mkdir(parents=True)
    path.write_bytes(WAVE)
    yield e, home, path
    e.close()


def capture(e, home, path, *, turn='u', text='GraMem 语音方案', p=OWNER):
    chats = Chats(e)
    id = chats.capture(p, '继续讨论 GraMem', 'MEDIA:' + str(path), session='s', turn=turn, platform='cli')
    assert ChatAudio(e).capture(p, id, messages(path, text), home=home) == 1
    assert chats.process_one()
    return id


def test_voice_original_survives_cache_cleanup_and_bundle_backup_restore(voice, tmp_path):
    e, home, path = voice
    id = capture(e, home, path)
    chats, audio = Chats(e), ChatAudio(e)
    raw = chats.original(OWNER, id)[1]
    info = chats.read(OWNER, id)['audio'][0]
    assert info['transcript_basis'] == 'tts_input'
    assert info['mime'] == 'audio/wav' and info['sha256'] == hashlib.sha256(WAVE).hexdigest()
    assert 'source_path' not in info and str(home) not in str(info)
    assert chats.search(OWNER, '语音方案')['total'] == 1
    assert chats.original(OWNER, id)[1] == raw and '语音方案' not in raw.decode()
    assert audio.blob(info['id']).stat().st_mode & 0o777 == 0o600
    assert audio.blob(info['id']).parent.stat().st_mode & 0o777 == 0o700
    path.unlink()
    assert audio.original(OWNER, id, info['id'])[1] == WAVE
    bundle_info, bundle = audio.bundle(OWNER, id)
    assert bundle_info['sha256'] == hashlib.sha256(bundle).hexdigest()
    with zipfile.ZipFile(io.BytesIO(bundle)) as z:
        manifest = json.loads(z.read('manifest.json'))
        assert z.read('chat.json') == raw
        assert z.read(manifest['audio'][0]['archive_path']) == WAVE
    backup = tmp_path / 'all-originals.zip'
    assert Knowledge(e).backup(backup)['chat_audio'] == 1
    restored_home = tmp_path / 'restored'
    with zipfile.ZipFile(backup) as z:
        z.extractall(restored_home / 'gramem')
        assert json.loads(z.read('manifest.json'))['schema'] == 8
    restored = Engine(restored_home / 'gramem/memory.sqlite')
    try:
        assert ChatAudio(restored).original(OWNER, id, info['id'])[1] == WAVE
        assert Chats(restored).original(OWNER, id)[1] == raw
    finally:
        restored.close()


def test_new_voice_revalidates_completed_chat_and_stale_worker(voice):
    e, home, path = voice
    chats = Chats(e)
    id = chats.capture(OWNER, 'GraMem 对话', 'MEDIA:' + str(path), session='s', turn='u', platform='cli')
    e.model.before_return = lambda: ChatAudio(e).capture(OWNER, id, messages(path), home=home)
    assert chats.process_one()
    assert e.store.rows('SELECT status,organized FROM chat_turns')[0]['status'] == 'pending'
    with pytest.raises(PermissionError):
        chats.read(OWNER, id)
    e.model.before_return = None
    assert chats.process_one()
    assert chats.read(OWNER, id)['audio']
    calls = e.model.calls
    assert ChatAudio(e).capture(OWNER, id, messages(path), home=home) == 0
    assert not chats.process_one() and e.model.calls == calls


def test_voice_privacy_rewind_scope_and_deleted_originals(voice):
    e, home, path = voice
    id = capture(e, home, path, text='禁提标记，私人语音内容')
    audio = ChatAudio(e)
    aid = Chats(e).read(OWNER, id)['audio'][0]['id']
    with pytest.raises(PermissionError):
        audio.original(CONTACT, id, aid)
    with pytest.raises(PermissionError):
        audio.original(GROUP, id, aid)
    e.exclude(OWNER, 'private.voice', state='suppressed')
    assert Chats(e).process_one()
    assert not Chats(e).search(OWNER)['items']
    assert not Network(e).snapshot(OWNER)['nodes']
    assert audio.blob(aid).read_bytes() == WAVE
    for method, args in [(audio.original, (OWNER, id, aid)), (audio.bundle, (OWNER, id))]:
        with pytest.raises(PermissionError):
            method(*args)
    e.exclude(OWNER, '*', state='deleted')
    assert Chats(e).process_one()
    assert not audio.blob(aid).exists()
    row = e.store.rows('SELECT * FROM chat_audio')[0]
    assert row['state'] == 'redacted' and not row['transcript'] and not row['source_path']
    assert not ChatAudio(e).capture(OWNER, id, messages(path), home=home)


@pytest.mark.parametrize('unsafe', ['outside', 'symlink', 'invalid', 'missing'])
def test_audio_does_not_read_arbitrary_paths_and_reports_missing(voice, tmp_path, unsafe):
    e, home, path = voice
    if unsafe == 'outside':
        path = tmp_path / 'outside.wav'
        path.write_bytes(WAVE)
    elif unsafe == 'symlink':
        outside = tmp_path / 'outside.wav'
        outside.write_bytes(WAVE)
        path.unlink()
        path.symlink_to(outside)
    elif unsafe == 'invalid':
        path.write_bytes(b'not audio')
    else:
        path.unlink()
    id = capture(e, home, path)
    info = Chats(e).read(OWNER, id)['audio'][0]
    assert info['state'] == 'missing' and not info['sha256']
    with pytest.raises(KeyError):
        ChatAudio(e).original(OWNER, id, info['id'])
    with zipfile.ZipFile(io.BytesIO(ChatAudio(e).bundle(OWNER, id)[1])) as z:
        assert not any(name.startswith('audio/') for name in z.namelist())


def test_unknown_voice_is_hidden_under_exclusions_and_model_never_guesses(voice):
    e, home, path = voice
    id = Chats(e).capture(OWNER, '普通话题', 'MEDIA:' + str(path), session='s', turn='u', platform='cli')
    ChatAudio(e).capture(OWNER, id, [{'role': 'assistant', 'content': 'MEDIA:' + str(path)}], home=home)
    e.exclude(OWNER, 'private.topic', state='suppressed')
    assert Chats(e).process_one()
    assert e.store.rows('SELECT status FROM chat_turns')[0]['status'] == 'silent'
    assert not Chats(e).search(OWNER)['items']


def test_network_voice_weights_follow_the_chat_source_and_integrity_is_checked(voice):
    e, home, path = voice
    source = e.enqueue(OWNER, 'GraMem 原件', session='s', turn='u')
    id = capture(e, home, path)
    Chats(e).reconcile_native(OWNER, id, 1, True, [source])
    fact = e.remember(OWNER, 'GraMem 原件', slot='plan')
    with e.store.transaction() as db:
        db.execute('UPDATE memories SET source=? WHERE id=?', (source, fact))
    result = Network(e).snapshot(OWNER)
    node = next(n for n in result['nodes'] if n['kind'] == 'audio')
    assert node['confidence'] == e.get(OWNER, fact)['confidence']
    assert node['weight_memory_ids'] == [fact]
    assert any(edge['relation'] == 'HAS_AUDIO' and edge['target'] == node['id'] for edge in result['edges'])
    ChatAudio(e).blob(node['ref']).write_bytes(b'corrupt')
    with pytest.raises(RuntimeError):
        ChatAudio(e).original(OWNER, id, node['ref'])
    with pytest.raises(RuntimeError):
        ChatAudio(e).bundle(OWNER, id)
    with pytest.raises(RuntimeError):
        Knowledge(e).backup(home.parent / 'corrupt.zip')


def test_native_history_repairs_old_chat_voice_links_and_hides_rewound_tool(voice):
    e, home, path = voice
    native = home / 'state.db'
    with sqlite3.connect(native) as db:
        db.executescript('''CREATE TABLE sessions(id,source,user_id,chat_type,origin_json,started_at,chat_id);
        CREATE TABLE messages(id INTEGER PRIMARY KEY,session_id,role,content,timestamp,_compressed_summary,message_uid,
        tool_calls,tool_call_id,tool_name,active,compacted);
        INSERT INTO sessions VALUES('s','cli','','dm','{}',1,'d');
        INSERT INTO messages VALUES(1,'s','user','继续讨论 GraMem',1,0,'u',NULL,NULL,NULL,1,0);''')
        for index, m in enumerate(messages(path), 2):
            db.execute('INSERT INTO messages VALUES(?,?,?,?,?,0,NULL,?,?,?,1,0)',
                       (index, 's', m['role'], m['content'], index, json.dumps(m.get('tool_calls')),
                        m.get('tool_call_id'), m.get('tool_name')))
    id = Chats(e).capture(OWNER, '继续讨论 GraMem', 'MEDIA:' + str(path), session='s', turn='u', platform='cli')
    raw = Chats(e).original(OWNER, id)[1]
    assert import_sessions(e, native)['imported'] == 0
    assert Chats(e).process_one()
    info = Chats(e).read(OWNER, id)['audio'][0]
    assert ChatAudio(e).original(OWNER, id, info['id'])[1] == WAVE
    assert Chats(e).original(OWNER, id)[1] == raw
    with sqlite3.connect(native) as db:
        db.execute('UPDATE messages SET active=0 WHERE id=3')
    import_sessions(e, native)
    with pytest.raises(PermissionError):
        ChatAudio(e).original(OWNER, id, info['id'])
    assert ChatAudio(e).blob(info['id']).read_bytes() == WAVE


def test_provider_captures_only_current_voice_turn_and_can_export_original(make_provider):  # noqa: F811
    provider = make_provider(platform='teams', chat_type='dm')
    provider.engine.model = Organizer()
    path = provider.home / 'cache/audio/new.wav'
    path.parent.mkdir(parents=True)
    path.write_bytes(WAVE)
    current = [{'role': 'user', 'content': '旧输入', 'message_uid': 'old'}, *messages(path, '旧文案'),
               {'role': 'user', 'content': '当前 GraMem 输入', 'message_uid': 'new'}, *messages(path, '当前朗读文案', cid='new-voice')]
    provider.sync_turn('当前 GraMem 输入', 'MEDIA:' + str(path), messages=current)
    p = provider._current
    assert Chats(provider.engine).process_one()
    id = Chats(provider.engine).search(p)['items'][0]['id']
    info = Chats(provider.engine).read(p, id)['audio'][0]
    assert info['transcript'] == '当前朗读文案'
    result = json.loads(provider.handle_tool_call('gramem_chats', {'action': 'audio', 'id': id, 'audio_id': info['id']}))
    assert Path(result['path']).read_bytes() == WAVE


def test_descriptor_does_not_infer_text_from_failed_or_other_tools(voice):
    _, _, path = voice
    assert descriptors(messages(path, result=False)[:-1]) == []
    unknown = descriptors(messages(path, result=False))[0]
    assert unknown['transcript_basis'] == 'unknown' and not unknown['transcript']
    assert descriptors([{'role': 'assistant', 'tool_calls': 'invalid'}]) == []


def test_schema_seven_upgrade_keeps_chat_original_bytes_and_old_summaries(voice):
    e, _, path = voice
    chats = Chats(e)
    id = chats.capture(OWNER, '旧聊天', '旧答复', session='s', turn='old', platform='cli')
    assert chats.process_one()
    raw = chats.original(OWNER, id)[1]
    summaries = e.store.rows('SELECT * FROM chat_summaries')
    database = e.store.path
    e.close()
    with sqlite3.connect(database) as db:
        db.execute('DROP TABLE chat_audio')
        db.execute('PRAGMA user_version=7')
    upgraded = Engine(database)
    try:
        assert upgraded.store.rows('PRAGMA user_version')[0]['user_version'] == 8
        assert Chats(upgraded).original(OWNER, id)[1] == raw
        assert upgraded.store.rows('SELECT * FROM chat_summaries') == summaries
        assert not upgraded.store.rows('SELECT * FROM chat_audio')
        assert path.exists()
    finally:
        upgraded.close()
