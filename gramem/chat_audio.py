"""Private immutable audio originals linked to an authenticated chat turn."""

import hashlib
import io
import json
import os
import re
import stat
import tempfile
import zipfile
from pathlib import Path

from .chats import Chats, text_content
from .store import Store
from .tokens import compact

MAX_BYTES = 20_000_000
SUFFIXES = {'.mp3', '.wav', '.ogg', '.opus', '.m4a', '.aac', '.caf', '.flac', '.webm', '.aiff'}
MEDIA = re.compile(r'''MEDIA:\s*(?:"([^"\r\n]+)"|'([^'\r\n]+)'|([^\s"<>]+))''')


def refs(text):
    return list(dict.fromkeys(next(v for v in m.groups() if v) for m in MEDIA.finditer(text_content(text))
                             if Path(next(v for v in m.groups() if v)).suffix.lower() in SUFFIXES))


def _json(value):
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        return None


def descriptors(messages):
    """Tools prove synthesis input; a reply reference alone never invents a transcript."""
    calls, replies, items = {}, set(), {}
    for m in messages:
        if m.get('role') != 'assistant':
            continue
        replies.update(refs(m.get('content', '')))
        tool_calls = _json(m.get('tool_calls'))
        for call in tool_calls if isinstance(tool_calls, list) else []:
            if not isinstance(call, dict) or not isinstance(call.get('function'), dict):
                continue
            if call['function'].get('name') == 'text_to_speech':
                args = _json(call['function'].get('arguments'))
                if isinstance(args, dict):
                    calls[str(call.get('id') or call.get('call_id') or '')] = args
    for m in messages:
        if m.get('role') not in {'tool', 'function'}:
            continue
        cid = str(m.get('tool_call_id') or m.get('call_id') or '')
        if cid not in calls:
            continue
        result = _json(m.get('content'))
        if not isinstance(result, dict) or result.get('success') is not True:
            continue
        paths = result.get('file_paths') or [result.get('file_path')]
        if not isinstance(paths, list):
            continue
        spoken = result.get('spoken_text')
        basis = 'tts_spoken_text' if isinstance(spoken, str) else 'tts_input'
        transcript = spoken if isinstance(spoken, str) else calls[cid].get('text', '')
        if not isinstance(transcript, str):
            transcript, basis = '', 'unknown'
        for path in paths[:20]:
            if not isinstance(path, str) or Path(path).suffix.lower() not in SUFFIXES:
                continue
            items[path] = {'path': path, 'transcript': transcript, 'transcript_basis': basis,
                           'metadata': {'tool_call_id': cid, 'native_tool_message_id': m.get('id'),
                                        'provider': str(result.get('provider') or '')[:100],
                                        'delivery_basis': 'reply_reference' if path in replies else 'tts_tool_result'}}
    for path in replies:
        items.setdefault(path, {'path': path, 'transcript': '', 'transcript_basis': 'unknown',
                                'metadata': {'delivery_basis': 'reply_reference'}})
    return list(items.values())


def sniff(data):
    if len(data) > 1 and data[0] == 255 and data[1] & 246 == 240:
        return 'audio/aac', '.aac'
    if data.startswith(b'ID3') or (len(data) > 1 and data[0] == 255 and data[1] & 224 == 224):
        return 'audio/mpeg', '.mp3'
    if data[:4] == b'RIFF' and data[8:12] == b'WAVE':
        return 'audio/wav', '.wav'
    if data.startswith(b'OggS'):
        return 'audio/ogg', '.ogg'
    if data[4:8] == b'ftyp':
        return 'audio/mp4', '.m4a'
    if data.startswith(b'caff'):
        return 'audio/x-caf', '.caf'
    if data.startswith(b'fLaC'):
        return 'audio/flac', '.flac'
    if data[:4] == b'FORM' and data[8:12] in {b'AIFF', b'AIFC'}:
        return 'audio/aiff', '.aiff'
    if data.startswith(b'\x1aE\xdf\xa3'):
        return 'audio/webm', '.webm'
    raise ValueError('invalid_audio')


class ChatAudio:
    def __init__(self, engine):
        self.e = engine
        self.root = engine.store.path.parent / 'chats' / 'audio'

    def blob(self, id):
        if not re.fullmatch('[a-f0-9]{64}', id):
            raise ValueError('invalid audio id')
        return self.root / id[:2] / (id + '.blob')

    @staticmethod
    def _read_cache(path, home):
        source = Path(path)
        if not source.is_absolute() or '..' in source.parts or any(ord(c) < 32 for c in path):
            raise ValueError('unsupported_path')
        resolved = source.resolve()
        roots = [home / 'cache/audio', home / 'audio_cache', home / 'voice-memos']
        if not any(root.resolve() in resolved.parents for root in roots):
            raise ValueError('unsupported_path')
        # O_NONBLOCK: a FIFO or device in the cache must not block the caller.
        fd = os.open(resolved, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES:
                raise ValueError('invalid_size')
            data = handle.read(MAX_BYTES + 1)
            if len(data) != info.st_size:
                raise ValueError('invalid_size')
        return data

    def _write_blob(self, id, data):
        destination = self.blob(id)
        for directory in [self.root.parent, self.root, destination.parent]:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(directory, 0o700)
        fd, temp = tempfile.mkstemp(dir=destination.parent, prefix='.audio-')
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, destination)
            directory_fd = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            Path(temp).unlink(missing_ok=True)

    def capture(self, p, turn_id, messages, *, home=None):
        Chats._private(p)
        home = Path(home) if home is not None else self.e.store.path.parent.parent
        captured = 0
        for item in descriptors(messages):
            id = hashlib.sha256(compact([p.key, turn_id, item['path']]).encode()).hexdigest()
            # Read the source before taking any lock: file I/O must never run
            # inside a SQLite write transaction shared with other processes.
            data, digest, size, mime = b'', '', 0, ''
            name = 'voice-' + id[:16] + Path(item['path']).suffix.lower()
            error = ''
            try:
                data = self._read_cache(item['path'], home)
                mime, suffix = sniff(data)
                name = 'voice-' + id[:16] + suffix
                digest, size = hashlib.sha256(data).hexdigest(), len(data)
            except FileNotFoundError:
                error = 'missing_source'
            except (OSError, ValueError) as exc:
                code = str(exc) if isinstance(exc, ValueError) else ''
                error = code if code in {'unsupported_path', 'invalid_audio', 'invalid_size'} else 'unavailable_source'
            state = 'missing' if error else 'stored'
            # knowledge_dispatch serializes blob writes against purges.
            with self.e.store.knowledge_dispatch():
                with self.e.store.transaction() as db:
                    turn = db.execute('SELECT * FROM chat_turns WHERE id=? AND principal=?', (turn_id, p.key)).fetchone()
                    if not turn:
                        raise PermissionError('chat is unavailable')
                    existing = db.execute('SELECT * FROM chat_audio WHERE id=?', (id,)).fetchone()
                    if turn['status'] == 'redacted' or (existing and existing['state'] in {'stored', 'redacted'}):
                        continue
                if data and not error:
                    self._write_blob(id, data)
                with self.e.store.transaction() as db:
                    turn = db.execute('SELECT * FROM chat_turns WHERE id=? AND principal=?', (turn_id, p.key)).fetchone()
                    existing = db.execute('SELECT * FROM chat_audio WHERE id=?', (id,)).fetchone()
                    if not turn or turn['status'] == 'redacted' or (existing and existing['state'] in {'stored', 'redacted'}):
                        # Redacted or captured by another process while writing the blob.
                        if data and not error and not (existing and existing['state'] == 'stored'):
                            self.blob(id).unlink(missing_ok=True)
                        continue
                    db.execute('''INSERT INTO chat_audio VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(id) DO UPDATE SET name=excluded.name,mime=excluded.mime,
                        sha256=excluded.sha256,size=excluded.size,state=excluded.state,error=excluded.error''',
                               (id, turn_id, p.key, item['path'], name, mime, digest, size,
                                item['transcript'], item['transcript_basis'], compact(item['metadata']),
                                state, error, self.e.clock()))
                    if not existing or existing['state'] != state:
                        # New speech is new policy evidence; revalidate before exposing audio.
                        db.execute("UPDATE chat_turns SET organized=0,status='pending',policy_epoch=-1,lease=0,retry_at=0,attempts=attempts+1 WHERE id=?", (turn_id,))
                        summaries = db.execute('SELECT turn_ids FROM chat_summaries WHERE principal=? AND EXISTS(SELECT 1 FROM json_each(turn_ids) WHERE value=?)', (p.key, turn_id)).fetchall()
                        for summary in summaries:
                            for other in json.loads(summary['turn_ids']):
                                db.execute("UPDATE chat_turns SET organized=0 WHERE id=? AND principal=? AND status!='redacted'", (other, p.key))
                        db.execute('DELETE FROM chat_summaries WHERE principal=? AND EXISTS(SELECT 1 FROM json_each(turn_ids) WHERE value=?)', (p.key, turn_id))
                        Store.changed(db)
                        self.e._profile_dirty(db, p)
                        captured += 1
        return captured

    def info(self, db, turn_id):
        return [{'id': r['id'], 'name': r['name'], 'mime': r['mime'], 'sha256': r['sha256'],
                 'size': r['size'], 'state': r['state'], 'error': r['error'],
                 'transcript': r['transcript'], 'transcript_basis': r['transcript_basis'],
                 'role': 'assistant', 'metadata': json.loads(r['metadata'])}
                for r in db.execute("SELECT * FROM chat_audio WHERE turn_id=? AND state!='redacted' ORDER BY created,id", (turn_id,))]

    def original(self, p, turn_id, id):
        with self.e.store.knowledge_dispatch(), self.e.store.transaction() as db:
            turn = db.execute('SELECT * FROM chat_turns WHERE id=? AND principal=?', (turn_id, p.key)).fetchone()
            if not turn or not Chats(self.e)._visible(db, p, turn):
                raise PermissionError('chat audio unavailable or excluded')
            row = db.execute("SELECT * FROM chat_audio WHERE id=? AND turn_id=? AND principal=? AND state='stored'", (id, turn_id, p.key)).fetchone()
            if not row:
                raise KeyError('audio original unavailable')
            data = self.blob(id).read_bytes()
            if len(data) != row['size'] or hashlib.sha256(data).hexdigest() != row['sha256']:
                raise RuntimeError('audio original integrity failure')
            return {'id': id, 'name': row['name'], 'mime': row['mime'], 'sha256': row['sha256']}, data

    def bundle(self, p, turn_id):
        with self.e.store.knowledge_dispatch(), self.e.store.transaction() as db:
            info, raw = Chats(self.e)._original(db, p, turn_id)
            audio = self.info(db, turn_id)
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr('chat.json', raw)
                for item in audio:
                    if item['state'] == 'stored':
                        data = self.blob(item['id']).read_bytes()
                        if hashlib.sha256(data).hexdigest() != item['sha256'] or len(data) != item['size']:
                            raise RuntimeError('audio original integrity failure')
                        item['archive_path'] = 'audio/' + item['name']
                        z.writestr(item['archive_path'], data)
                z.writestr('manifest.json', compact({'chat': info, 'audio': audio, 'schema': 8,
                    'note': 'TTS input is synthesis evidence, not an ASR transcript or a delivery receipt.'}))
            return {'name': 'chat-' + turn_id[:16] + '-originals.zip', 'sha256': hashlib.sha256(output.getvalue()).hexdigest()}, output.getvalue()

    def purge_redacted(self):
        # File lock must be held by the caller. Unlink after transaction commits.
        with self.e.store.transaction() as db:
            rows = db.execute("SELECT a.id FROM chat_audio a JOIN chat_turns t ON t.id=a.turn_id WHERE t.status='redacted' OR a.state='redacted'").fetchall()
            for row in rows:
                db.execute("UPDATE chat_audio SET source_path='',name='',mime='',sha256='',size=0,transcript='',metadata='{}',state='redacted',error='' WHERE id=?", (row['id'],))
        for row in rows:
            self.blob(row['id']).unlink(missing_ok=True)

    def reconcile(self):
        with self.e.store.knowledge_dispatch():
            self.purge_redacted()
            states = {r['id']: r['state'] for r in self.e.store.rows('SELECT id,state FROM chat_audio')}
            for file in self.root.glob('*/*'):
                if file.name.startswith('.audio-') or (file.suffix == '.blob' and states.get(file.stem) != 'stored'):
                    file.unlink(missing_ok=True)
            return {'missing_audio_originals': sum(not self.blob(id).exists() for id, state in states.items() if state == 'stored')}
