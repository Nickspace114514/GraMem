"""Offline administrator migration of an explicitly verified contact to its Owner.

Stop all provider/worker writers and back up the database before calling. IDs of
memories and sources remain durable provenance IDs; chat IDs follow capture's
canonical scope/session/turn key. This is deliberately not an agent tool.
"""

import hashlib
import json

from .config import Principal
from .store import Store
from .tokens import compact


def migrate_verified_contact(engine, platform, author):
    owner = engine.config.principal(platform, author)
    contact = Principal(owner.owner, 'contact', f'{platform}:{author}', f'{platform}:{author}')
    if owner.scope != 'owner' or owner.subject != owner.owner:
        raise PermissionError('transport identity is not verified as this Owner')
    counts = {}
    with engine.store.transaction() as db:
        # Unfinished sources cannot acquire a new policy epoch without review.
        if db.execute("SELECT 1 FROM sources WHERE principal=? AND status NOT IN ('done','redacted')",
                      (contact.key,)).fetchone():
            raise ValueError('finish or redact contact source jobs before migration')
        for table in ('knowledge_documents', 'chat_backfill_jobs'):
            if db.execute(f'SELECT 1 FROM {table} WHERE principal=?', (contact.key,)).fetchone():
                raise ValueError('document/backfill migration requires separate review')
        turns = [dict(r) for r in db.execute('SELECT * FROM chat_turns WHERE principal=?', (contact.key,))]
        mapping = {r['id']: hashlib.sha256(compact([owner.key, r['session'], r['turn']]).encode()).hexdigest()
                   for r in turns}
        for r in turns:
            if db.execute('SELECT 1 FROM chat_turns WHERE id=? OR (principal=? AND session=? AND turn=?)',
                          (mapping[r['id']], owner.key, r['session'], r['turn'])).fetchone():
                raise ValueError('overlapping chat requires explicit conflict reconciliation')
        # Defer FK checks while remapping each dependent canonical chat ID.
        db.execute('PRAGMA defer_foreign_keys=ON')
        for r in turns:
            old, new = r['id'], mapping[r['id']]
            db.execute("UPDATE chat_turns SET id=?,principal=?,status=CASE WHEN status='redacted' THEN status ELSE 'pending' END,"
                       "policy_epoch=-1,organized=0,lease=0,retry_at=0 WHERE id=?", (new, owner.key, old))
            for table in ('chat_native_state', 'chat_audio', 'chat_backfill_items'):
                db.execute(f'UPDATE {table} SET turn_id=? WHERE turn_id=?', (new, old))
        counts['chat_turns'] = len(turns)
        ranks = {'active': 0, 'suppressed': 1, 'deleted': 2}
        for r in db.execute('SELECT * FROM exclusions WHERE principal=?', (contact.key,)).fetchall():
            current = db.execute('SELECT * FROM exclusions WHERE principal=? AND slot=?',
                                 (owner.key, r['slot'])).fetchone()
            state = max([r['state'], current['state'] if current else 'active'], key=ranks.__getitem__)
            db.execute('INSERT OR REPLACE INTO exclusions VALUES(?,?,?,?,?)',
                       (owner.key, r['slot'], state, r['epoch'] + (current['epoch'] if current else 0) + 1,
                        engine.clock()))
        db.execute('DELETE FROM exclusions WHERE principal=?', (contact.key,))
        memories = [dict(r) for r in db.execute('SELECT * FROM memories WHERE principal=?', (contact.key,))]
        db.execute('DELETE FROM graph_outbox WHERE principal=?', (contact.key,))
        for r in memories:
            engine._graph_event(db, contact, r['id'], 'delete')
        for table in ('memories', 'sources', 'source_turns', 'events', 'receipts', 'checkpoints', 'chat_audio'):
            counts[table] = db.execute(f'UPDATE {table} SET principal=? WHERE principal=?',
                                       (owner.key, contact.key)).rowcount
        db.execute('UPDATE memory_fts SET principal=? WHERE principal=?', (owner.key, contact.key))
        # Cached projections cannot cross a changed identity/policy boundary.
        for table in ('profiles', 'knowledge_network_state'):
            db.execute(f'DELETE FROM {table} WHERE principal IN (?,?)', (owner.key, contact.key))
        db.execute('DELETE FROM chat_summaries WHERE principal=?', (contact.key,))
        engine._profile_dirty(db, contact)
        engine._profile_dirty(db, owner)
        Store.changed(db)
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('migration foreign key violation')
    return {'counts': counts, 'chat_ids': mapping, 'memory_ids': [r['id'] for r in memories]}


def sync_migrated_graph(engine, owner, memory_ids):
    """Rebuild allowed relationships only after migrated chats pass policy review."""
    with engine.store.transaction() as db:
        for id in memory_ids:
            row = db.execute('SELECT * FROM memories WHERE id=? AND principal=?', (id, owner.key)).fetchone()
            if row and row['status'] == 'active' and engine._fact_allowed(db, owner, row):
                relations = json.loads(row['metadata']).get('relations', [])
                engine._add_edges(db, owner, id, relations)
