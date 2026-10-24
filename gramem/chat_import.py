"""Read-only native chat import with verified identity and durable bulk pagination."""

import base64
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from .chats import Chats, dialogue_text, text_content
from .config import is_shared_chat
from .evidence import user_evidence


def _audio(archive, connection, p, id, message, live, home):
    from .chat_audio import ChatAudio

    rows = [dict(r) for r in connection.execute('''SELECT * FROM messages
        WHERE session_id=? AND _compressed_summary=0 AND id>? AND ''' + live + '''
        AND id<coalesce((SELECT min(id) FROM messages WHERE session_id=? AND role='user'
        AND _compressed_summary=0 AND ''' + live + ''' AND id>?),9223372036854775807) ORDER BY id''',
        (message['session_id'], message['id'], message['session_id'], message['id']))]
    for row in rows:
        row['content'] = native_content(row['content'])
    return ChatAudio(archive.e).capture(p, id, rows, home=home)


def native_content(value):
    # SessionDB serializes multimodal content with this sentinel.
    if isinstance(value, str) and value.startswith('\x00json:'):
        return json.loads(value[6:])
    return value


HASH_TURN = re.compile('[0-9a-f]{64}')


def _by_evidence_digest(connection, session, digest):
    matches = [m for m in connection.execute(
        "SELECT * FROM messages WHERE session_id=? AND role='user' ORDER BY id", (session,))
        if hashlib.sha256(user_evidence(native_content(m['content'])).encode()).hexdigest() == digest]
    # Identical repeated inputs cannot be told apart; leave them unlinked.
    return matches[0] if len(matches) == 1 else None


def _live(message):
    return bool(message.get('active', 1) or message.get('compacted', 0))


def _reconcile(engine, archive, connection, sessions, columns, live, home):
    identities = [name for name in ('message_uid', 'platform_message_id') if name in columns]
    match = ' OR '.join(['CAST(id AS TEXT)=?', *[name + '=?' for name in identities]])
    rows = engine.store.rows('''SELECT t.*,n.native_id FROM chat_turns t
        LEFT JOIN chat_native_state n ON n.turn_id=t.id''')
    for row in rows:
        if row['session'] not in sessions:
            continue
        _, _, p = sessions[row['session']]
        if row['principal'] != p.key:
            continue
        if row['native_id'] is not None:
            message = connection.execute("SELECT * FROM messages WHERE session_id=? AND role='user' AND id=?",
                                         (row['session'], row['native_id'])).fetchone()
        else:
            message = connection.execute("SELECT * FROM messages WHERE session_id=? AND role='user' AND (" + match + ')',
                                         (row['session'], *([row['turn']] * (len(identities) + 1)))).fetchone()
            if message is None and HASH_TURN.fullmatch(row['turn'] or ''):
                # The provider falls back to sha256(user evidence) when the host gave no
                # message id. Link it to the native row by the same exact digest so rewinds
                # apply and the import loop does not archive the turn twice.
                message = _by_evidence_digest(connection, row['session'], row['turn'])
        if message is None:
            if row['native_id'] is not None:
                archive.reconcile_native(p, row['id'], row['native_id'], False)
            continue
        message = dict(message)
        active = _live(message)
        # Old imports may contain a rewound reply even when the user anchor remains.
        # Retain their original bytes but fail closed on that entire archived unit.
        original = json.loads(bytes(row['original'])) if row['original'] else {}
        for item in original.get('messages', []):
            if not isinstance(item, dict) or not isinstance(item.get('id'), int):
                continue
            native = connection.execute('SELECT * FROM messages WHERE session_id=? AND id=?',
                                        (row['session'], item['id'])).fetchone()
            if native is None or not _live(dict(native)):
                active = False
        for audio in engine.store.rows('SELECT metadata FROM chat_audio WHERE turn_id=?', (row['id'],)):
            native_id = json.loads(audio['metadata']).get('native_tool_message_id')
            if isinstance(native_id, int):
                native = connection.execute('SELECT * FROM messages WHERE session_id=? AND id=?', (row['session'], native_id)).fetchone()
                if native is None or not _live(dict(native)):
                    active = False
        if not original.get('messages') and row['assistant_text']:
            # Provider captures predate native row IDs. Match the exact stored reply
            # within this turn, so rewinding only its answer cannot retain the old reply.
            replies = [dict(r) for r in connection.execute('''SELECT * FROM messages
                WHERE session_id=? AND role='assistant' AND _compressed_summary=0 AND id>?
                AND id<coalesce((SELECT min(id) FROM messages WHERE session_id=? AND role='user'
                AND _compressed_summary=0 AND id>?),9223372036854775807) ORDER BY id''',
                (row['session'], message['id'], row['session'], message['id']))]
            matching = [r for r in replies if dialogue_text(native_content(r['content'])) == row['assistant_text']]
            if matching and not any(_live(r) for r in matching):
                active = False
        sources = engine.conversation_sources(p, native_content(message['content']),
                                              session=row['session'], turn=row['turn'])
        archive.reconcile_native(p, row['id'], message['id'], active, sources)
        if active:
            _audio(archive, connection, p, row['id'], message, live, home)


def import_sessions(engine, path, *, maximum=200, principal=None, before=None,
                    on_import=None, after_id=None):
    if type(maximum) is not int or maximum < 1 or (after_id is not None and
            (type(after_id) is not int or after_id < 0)):
        raise ValueError('invalid import batch size/cursor')
    path = Path(path)
    cursor = after_id or 0
    imported = skipped = 0

    def result():
        return {'imported':imported,'skipped_sessions':skipped} | (
            {'cursor':cursor} if after_id is not None else {})

    if not path.exists():
        return result()
    archive = Chats(engine)
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro',uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('BEGIN')
        columns = {r['name'] for r in connection.execute('PRAGMA table_info(messages)')}
        live = '(active=1 OR compacted=1)' if {'active', 'compacted'} <= columns else (
            'active=1' if 'active' in columns else '1')
        sessions = {}
        for row in connection.execute('SELECT * FROM sessions ORDER BY started_at'):
            session = dict(row)
            platform = session.get('source','')
            try:
                origin = json.loads(session.get('origin_json') or '{}')
                if not isinstance(origin,dict):
                    raise ValueError('invalid origin')
            except (ValueError,TypeError):
                skipped += 1
                continue
            shared = is_shared_chat(session.get('chat_type') or origin.get('chat_type'))
            author = session.get('user_id') or origin.get('user_id') or ''
            if platform not in {'teams','slack','email','photon','telegram','cli'} or shared or (not author and platform!='cli'):
                # Older shared histories lack per-message authenticated authors. Never infer one.
                skipped += 1
                continue
            p = engine.config.principal(platform,author)
            if not principal or p.key == principal.key:
                sessions[session['id']] = (session,origin,p)
        # Repair existing imports as well as new rows; bulk cursors must not skip rewinds.
        _reconcile(engine, archive, connection, sessions, columns, live, path.parent)
        users = connection.execute('''SELECT * FROM messages WHERE role='user' AND _compressed_summary=0
                                      AND ''' + live + ''' AND id>? AND (? IS NULL OR timestamp<=?) ORDER BY id''', (cursor,before,before))
        for row in users:
            message = dict(row)
            cursor = message['id']
            sid = message['session_id']
            if sid not in sessions or not message.get('content'):
                continue
            session, origin, p = sessions[sid]
            turn = str(message.get('message_uid') or message.get('platform_message_id') or message['id'])
            if engine.store.rows('SELECT 1 FROM chat_turns WHERE principal=? AND session=? AND turn=?', (p.key,sid,turn)):
                continue
            if engine.store.rows('''SELECT 1 FROM chat_native_state n JOIN chat_turns t ON t.id=n.turn_id
                    WHERE t.principal=? AND t.session=? AND n.native_id=?''', (p.key, sid, message['id'])):
                continue  # Already archived by the provider under another turn identity.
            # Bound one dialogue by the next actual user message, rather than copying the
            # tail of a whole session for every turn. Bulk cursors avoid rescanning old rows.
            following = [dict(m) for m in connection.execute('''SELECT * FROM messages
                WHERE session_id=? AND role='assistant' AND _compressed_summary=0 AND id>?
                AND ''' + live + ''' AND id<coalesce((SELECT min(id) FROM messages
                WHERE session_id=? AND role='user' AND _compressed_summary=0 AND ''' + live + ''' AND id>?),9223372036854775807)
                AND (? IS NULL OR timestamp<=?) ORDER BY id''', (sid,message['id'],sid,message['id'],before,before))
                if m['content']]
            if not following:
                continue  # A later request/regular scan can pick up the completed reply.
            user = native_content(message['content'])
            assistant = '\n\n'.join(text_content(native_content(m['content'])) for m in following)

            def serializable(item):
                return {k:{'base64':base64.b64encode(v).decode()} if isinstance(v,bytes) else v
                        for k,v in item.items() if k in
                        {'id','session_id','role','content','timestamp','platform_message_id','message_uid'}}

            original = {'session':{k:session.get(k) for k in
                        ['id','source','user_id','chat_id','chat_type','thread_id','origin_json','started_at']},
                        'messages':[serializable(message),*[serializable(m) for m in following]]}
            sources = engine.conversation_sources(p, user, session=sid, turn=turn)
            id = archive.capture(p,user,assistant,session=sid,turn=turn,platform=session['source'],
                                 context=session.get('chat_id') or origin.get('chat_id') or '',
                                 created=message['timestamp'],original=original,source_ids=sources)
            if id:
                archive.reconcile_native(p, id, message['id'], True, sources)
                _audio(archive, connection, p, id, message, live, path.parent)
                with engine.store.transaction() as db:
                    db.execute("UPDATE chat_turns SET status='pending' WHERE id=? AND status='ready' AND organized=0", (id,))
                imported += 1
                if on_import:
                    on_import(id)
            if imported >= maximum:
                break
        return result()
    finally:
        connection.close()
