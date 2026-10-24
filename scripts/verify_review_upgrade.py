"""Verify schema/provenance repair on disposable copies, without models or graph writes.

The caller must supply a copied home, never a running profile. The safety marker is
created only by the operator that prepared the snapshot.
"""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from gramem.chat_import import import_sessions
from gramem.config import Config
from gramem.engine import Engine


def digest(rows):
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def verify(home):
    home = Path(home).resolve()
    if not (home / '.disposable-review-snapshot').is_file():
        raise RuntimeError('disposable snapshot marker required')
    memory = home / 'gramem/memory.sqlite'
    native = home / 'state.db'
    config = home / 'gramem/config.json'
    with sqlite3.connect(memory) as db:
        before_version = db.execute('PRAGMA user_version').fetchone()[0]
        originals = db.execute('SELECT id,original,sha256 FROM chat_turns ORDER BY id').fetchall()
        facts = digest(db.execute('SELECT * FROM memories ORDER BY id').fetchall())
        exclusions = digest(db.execute('SELECT * FROM exclusions ORDER BY principal,slot').fetchall())
        links = dict(db.execute('SELECT id,source_ids FROM chat_turns'))
    with sqlite3.connect(native) as db:
        cursor = db.execute('SELECT coalesce(max(id),0) FROM messages').fetchone()[0]
    native_hash, config_hash = hashlib.sha256(native.read_bytes()).hexdigest(), hashlib.sha256(config.read_bytes()).hexdigest()
    engine = Engine(memory, Config.load(config))  # No model, graph or secret resolver.
    try:
        result = import_sessions(engine, native, after_id=cursor)
        assert result['imported'] == 0, result
        with engine.store.transaction() as db:
            assert db.execute('PRAGMA user_version').fetchone()[0] == 7
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
            assert [tuple(r) for r in db.execute('SELECT id,original,sha256 FROM chat_turns ORDER BY id')] == originals
            assert digest([tuple(r) for r in db.execute('SELECT * FROM memories ORDER BY id')]) == facts
            assert digest([tuple(r) for r in db.execute('SELECT * FROM exclusions ORDER BY principal,slot')]) == exclusions
            after = dict(db.execute('SELECT id,source_ids FROM chat_turns'))
            stats = {
                'from_schema': before_version, 'to_schema': 7, 'existing_chats': len(originals),
                'repaired_source_links': sum(after[id] != sources for id, sources in links.items()),
                'native_linked_chats': db.execute('SELECT count(*) FROM chat_native_state').fetchone()[0],
                'inactive_native_chats': db.execute('SELECT count(*) FROM chat_native_state WHERE active=0').fetchone()[0],
                'source_turn_links': db.execute('SELECT count(*) FROM source_turns').fetchone()[0],
                'preserved_originals_facts_exclusions': True,
            }
        assert hashlib.sha256(native.read_bytes()).hexdigest() == native_hash
        assert hashlib.sha256(config.read_bytes()).hexdigest() == config_hash
        stats['preserved_native_and_config'] = True
        print(json.dumps(stats, ensure_ascii=False))
    finally:
        engine.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('copied_home', type=Path)
    verify(parser.parse_args().copied_home)
