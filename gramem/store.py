import json
import logging
import os
import sqlite3
import sys
import threading
import time
import traceback
import weakref
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)
# Write transactions block every other GraMem process on this profile.
SLOW_TRANSACTION_SECONDS = 2.0
STUCK_TRANSACTION_SECONDS = 30.0
_STORES = weakref.WeakSet()
_WATCHDOG = None
_WATCHDOG_LOCK = threading.Lock()


def _watch():
    while True:
        time.sleep(5)
        _scan(time.monotonic())


def _scan(now):
    """Log the live stack of any thread holding a write transaction too long."""
    for store in list(_STORES):
        holder = store._holder
        if holder is None:
            continue
        ident, name, started = holder
        held = now - started
        last = store._last_report
        if held < STUCK_TRANSACTION_SECONDS or (last and last[0] == started and now - last[1] < 300):
            continue
        # Never write _holder here: the transaction may have just ended.
        store._last_report = (started, now)
        frame = sys._current_frames().get(ident)
        stack = "".join(traceback.format_stack(frame)) if frame else "(thread gone)"
        logger.warning(
            "GraMem write transaction held %.0fs by thread %s (pid %s) on %s:\n%s",
            held, name, os.getpid(), store.path.name, stack,
        )


def _start_watchdog():
    global _WATCHDOG
    with _WATCHDOG_LOCK:
        if _WATCHDOG is None or not _WATCHDOG.is_alive():
            _WATCHDOG = threading.Thread(target=_watch, name="gramem-lock-watchdog", daemon=True)
            _WATCHDOG.start()


SCHEMA_VERSION = 8
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value INTEGER NOT NULL);
INSERT OR IGNORE INTO meta VALUES('revision',0);
CREATE TABLE IF NOT EXISTS memories(
 id TEXT PRIMARY KEY, principal TEXT NOT NULL, slot TEXT NOT NULL, type TEXT NOT NULL,
 class TEXT NOT NULL, content TEXT NOT NULL, status TEXT NOT NULL, lifecycle TEXT NOT NULL,
 confidence REAL NOT NULL, importance REAL NOT NULL, strength REAL NOT NULL, decay REAL NOT NULL,
 created REAL NOT NULL, updated REAL NOT NULL, maintained REAL NOT NULL, valid_from REAL NOT NULL,
 valid_until REAL, accesses INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1,
 source TEXT, supersedes TEXT, metadata TEXT NOT NULL DEFAULT '{}', embedding TEXT,
 embedding_space TEXT, FOREIGN KEY(source) REFERENCES sources(id));
CREATE INDEX IF NOT EXISTS memory_scope ON memories(principal,status,type,slot);
CREATE INDEX IF NOT EXISTS memory_source ON memories(source);
CREATE TABLE IF NOT EXISTS sources(
 id TEXT PRIMARY KEY, principal TEXT NOT NULL, session TEXT NOT NULL, kind TEXT NOT NULL,
 content TEXT NOT NULL, created REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0, error TEXT,
 epoch INTEGER NOT NULL DEFAULT 0, result TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS source_jobs ON sources(status,retry_at);
CREATE TABLE IF NOT EXISTS source_turns(
 principal TEXT NOT NULL,session TEXT NOT NULL,turn TEXT NOT NULL,source_id TEXT NOT NULL,
 PRIMARY KEY(principal,session,turn,source_id),FOREIGN KEY(source_id) REFERENCES sources(id));
CREATE TABLE IF NOT EXISTS exclusions(
 principal TEXT NOT NULL, slot TEXT NOT NULL, state TEXT NOT NULL,
 epoch INTEGER NOT NULL DEFAULT 1, updated REAL NOT NULL,
 PRIMARY KEY(principal,slot));
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY, memory_id TEXT, principal TEXT NOT NULL, action TEXT NOT NULL,
 at REAL NOT NULL, detail TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS graph_outbox(
 id INTEGER PRIMARY KEY, memory_id TEXT NOT NULL, principal TEXT NOT NULL,
 action TEXT NOT NULL, payload TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 retry_at REAL NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS graph_jobs ON graph_outbox(retry_at,id);
CREATE TABLE IF NOT EXISTS profiles(
 principal TEXT NOT NULL,version INTEGER NOT NULL,content TEXT NOT NULL,
 sources TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(principal,version));
CREATE TABLE IF NOT EXISTS receipts(
 principal TEXT NOT NULL,session TEXT NOT NULL,turn TEXT NOT NULL,memory_id TEXT NOT NULL,
 PRIMARY KEY(principal,session,turn,memory_id));
CREATE TABLE IF NOT EXISTS checkpoints(
 id TEXT PRIMARY KEY,principal TEXT NOT NULL,session TEXT NOT NULL,created REAL NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(id UNINDEXED,principal UNINDEXED,terms);
CREATE TABLE IF NOT EXISTS knowledge_documents(
 id TEXT PRIMARY KEY,principal TEXT NOT NULL,name TEXT NOT NULL,title TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',sha256 TEXT NOT NULL,size INTEGER NOT NULL,
 suffix TEXT NOT NULL,mime TEXT NOT NULL,family TEXT NOT NULL,version INTEGER NOT NULL,
 previous TEXT,status TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,
 epoch INTEGER NOT NULL,lease REAL NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0,
 error TEXT NOT NULL DEFAULT '',pages INTEGER NOT NULL DEFAULT 0,
 origin TEXT NOT NULL DEFAULT '{}',UNIQUE(principal,sha256));
CREATE INDEX IF NOT EXISTS knowledge_scope ON knowledge_documents(principal,family,version);
CREATE TABLE IF NOT EXISTS knowledge_chunks(
 document_id TEXT NOT NULL,memory_id TEXT NOT NULL,ordinal INTEGER NOT NULL,
 page INTEGER NOT NULL,method TEXT NOT NULL,
 PRIMARY KEY(document_id,ordinal),FOREIGN KEY(document_id) REFERENCES knowledge_documents(id),
 FOREIGN KEY(memory_id) REFERENCES memories(id));
CREATE INDEX IF NOT EXISTS knowledge_memory ON knowledge_chunks(memory_id);
CREATE TABLE IF NOT EXISTS chat_turns(
 id TEXT PRIMARY KEY,principal TEXT NOT NULL,session TEXT NOT NULL,turn TEXT NOT NULL,
 platform TEXT NOT NULL,context TEXT NOT NULL,created REAL NOT NULL,
 original BLOB NOT NULL,sha256 TEXT NOT NULL,user_text TEXT NOT NULL,assistant_text TEXT NOT NULL,
 source_ids TEXT NOT NULL DEFAULT '[]',status TEXT NOT NULL DEFAULT 'pending',
 policy_epoch INTEGER NOT NULL DEFAULT -1,organized INTEGER NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0,
 lease REAL NOT NULL DEFAULT 0,retry_at REAL NOT NULL DEFAULT 0,
 UNIQUE(principal,session,turn));
CREATE INDEX IF NOT EXISTS chat_scope ON chat_turns(principal,session,created);
CREATE INDEX IF NOT EXISTS chat_jobs ON chat_turns(status,retry_at,lease);
CREATE TABLE IF NOT EXISTS chat_native_state(
 turn_id TEXT PRIMARY KEY,native_id INTEGER NOT NULL,active INTEGER NOT NULL,
 FOREIGN KEY(turn_id) REFERENCES chat_turns(id));
CREATE TABLE IF NOT EXISTS chat_audio(
 id TEXT PRIMARY KEY,turn_id TEXT NOT NULL,principal TEXT NOT NULL,source_path TEXT NOT NULL,
 name TEXT NOT NULL,mime TEXT NOT NULL DEFAULT '',sha256 TEXT NOT NULL DEFAULT '',size INTEGER NOT NULL DEFAULT 0,
 transcript TEXT NOT NULL DEFAULT '',transcript_basis TEXT NOT NULL DEFAULT 'unknown',
 metadata TEXT NOT NULL DEFAULT '{}',state TEXT NOT NULL DEFAULT 'missing',error TEXT NOT NULL DEFAULT '',created REAL NOT NULL,
 FOREIGN KEY(turn_id) REFERENCES chat_turns(id));
CREATE INDEX IF NOT EXISTS chat_audio_turn ON chat_audio(principal,turn_id);
CREATE TABLE IF NOT EXISTS chat_summaries(
 id TEXT PRIMARY KEY,principal TEXT NOT NULL,session TEXT NOT NULL,created REAL NOT NULL,
 policy_epoch INTEGER NOT NULL,content TEXT NOT NULL,turn_ids TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS knowledge_network_state(
 principal TEXT PRIMARY KEY,revision TEXT NOT NULL DEFAULT '',lease REAL NOT NULL DEFAULT 0,
 generation TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS chat_backfill_jobs(
 id TEXT PRIMARY KEY,principal TEXT NOT NULL,state TEXT NOT NULL,
 created REAL NOT NULL,updated REAL NOT NULL,cutoff REAL NOT NULL,
 lease REAL NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0,
 retry_at REAL NOT NULL DEFAULT 0,imported INTEGER NOT NULL DEFAULT 0,
 skipped_sessions INTEGER NOT NULL DEFAULT 0,native_cursor INTEGER NOT NULL DEFAULT 0,
 error TEXT NOT NULL DEFAULT '');
CREATE UNIQUE INDEX IF NOT EXISTS chat_backfill_active ON chat_backfill_jobs(principal)
 WHERE state IN ('importing','processing');
CREATE TABLE IF NOT EXISTS chat_backfill_items(
 job_id TEXT NOT NULL,turn_id TEXT NOT NULL,PRIMARY KEY(job_id,turn_id),
 FOREIGN KEY(job_id) REFERENCES chat_backfill_jobs(id),
 FOREIGN KEY(turn_id) REFERENCES chat_turns(id));
PRAGMA user_version=8;
"""
assert f"PRAGMA user_version={SCHEMA_VERSION};" in SCHEMA


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._holder = None
        self._last_report = None
        self.db = sqlite3.connect(
            str(self.path), timeout=15, check_same_thread=False, isolation_level=None
        )
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        # Simultaneous opens can deadlock while upgrading a shared journal-mode
        # lock; SQLite may return BUSY immediately despite the connection timeout.
        deadline = time.monotonic() + 15
        while True:
            try:
                self.db.execute("PRAGMA journal_mode=WAL")
                break
            except sqlite3.OperationalError as exc:
                if (
                    getattr(exc, "sqlite_errorcode", None) != sqlite3.SQLITE_BUSY
                    or time.monotonic() >= deadline
                ):
                    self.db.close()
                    raise
                time.sleep(0.01)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA secure_delete=ON")
        try:
            # user_version is set by the same transaction that creates the schema, so a
            # current version means nothing is left to do. Skipping the write lock here
            # keeps a burst of provider starts from queueing behind each other.
            if self.db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                # Serialize version check, migration and schema creation across provider processes.
                with self.transaction() as db:
                    version = db.execute("PRAGMA user_version").fetchone()[0]
                    if version not in {0, 2, 3, 4, 5, 6, 7, SCHEMA_VERSION}:
                        raise RuntimeError(f"unsupported database version {version}")
                    if version == 2:
                        columns = {r[1] for r in db.execute("PRAGMA table_info(sources)")}
                        if "result" not in columns:
                            db.execute(
                                "ALTER TABLE sources ADD COLUMN result TEXT NOT NULL DEFAULT '{}'"
                            )
                    # executescript would implicitly commit the migration lock.
                    for statement in SCHEMA.split(";"):
                        if statement.strip():
                            db.execute(statement)
        except BaseException:
            self.db.close()
            raise
        os.chmod(self.path, 0o600)
        _STORES.add(self)
        _start_watchdog()

    @contextmanager
    def transaction(self):
        """Write transaction: takes the database write lock immediately."""
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            thread = threading.current_thread()
            started = time.monotonic()
            self._holder = (thread.ident, thread.name, started)
            try:
                yield self.db
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            finally:
                self._holder = None
                held = time.monotonic() - started
                if held > SLOW_TRANSACTION_SECONDS:
                    caller = traceback.extract_stack(limit=6)[:-2]
                    logger.warning(
                        "GraMem write transaction held %.1fs by %s: %s",
                        held, thread.name,
                        " <- ".join(f"{f.name}:{f.lineno}" for f in reversed(caller)),
                    )

    @contextmanager
    def read(self):
        """Consistent read snapshot that never takes the write lock.

        Only for blocks that do not write; a write inside would need to upgrade
        the lock and can fail immediately with SQLITE_BUSY.
        """
        with self.lock:
            self.db.execute("BEGIN")
            try:
                yield self.db
            finally:
                self.db.execute("COMMIT")

    def rows(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    @property
    def revision(self):
        return self.rows("SELECT value FROM meta WHERE key='revision'")[0]["value"]

    @staticmethod
    def changed(db):
        db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")

    @contextmanager
    def knowledge_dispatch(self):
        """Serialize file and database operations across all engines on this profile."""
        path = self.path.with_suffix(".knowledge.lock")
        with path.open("a+b") as handle:
            os.chmod(path, 0o600)
            try:
                import fcntl
            except ImportError:
                import msvcrt

                if path.stat().st_size == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def graph_dispatch(self):
        # An OS lock releases on crash and serializes graph writers across Engine instances.
        path = self.path.with_suffix(".graph.lock")
        with path.open("a+b") as handle:
            os.chmod(path, 0o600)
            acquired = False
            try:
                try:
                    import fcntl
                except ImportError:
                    import msvcrt

                    if path.stat().st_size == 0:
                        handle.write(b"0")
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError:
                pass
            try:
                yield acquired
            finally:
                if acquired:
                    try:
                        import fcntl
                    except ImportError:
                        import msvcrt

                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def backup(self, destination: Path):
        destination = Path(destination)
        if destination.resolve() == self.path.resolve():
            raise ValueError("backup destination equals database")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            target = sqlite3.connect(str(destination))
            try:
                self.db.backup(target)
            finally:
                target.close()
        os.chmod(destination, 0o600)

    def close(self):
        with self.lock:
            _STORES.discard(self)
            self.db.close()


def decode(row):
    for key in ("metadata", "embedding", "result"):
        if key in row and isinstance(row[key], str):
            row[key] = json.loads(row[key])
    return row
