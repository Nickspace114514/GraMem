"""Idle background polling must not take the profile's SQLite write lock.

Many agents can poll one profile database at once. Each poll used to open
BEGIN IMMEDIATE even with nothing to do, so a few hundred idle pollers kept the
write lock busy and real writers (and new Store opens) starved.
"""

import sqlite3
import threading

import pytest
from test_engine import FakeGraph, FakeModel

from gramem.chat_backfill import Backfill
from gramem.chats import Chats
from gramem.config import Config
from gramem.engine import Engine
from gramem.knowledge import Knowledge
from gramem.relations import Relations


@pytest.fixture
def engine(tmp_path):
    cfg = Config(auto_approve=True, embedding_model="test-embed")
    e = Engine(tmp_path / "memory.sqlite", cfg, model=FakeModel(), graph=FakeGraph())
    e.store.db.execute("PRAGMA busy_timeout=150")
    yield e
    e.close()


@pytest.fixture
def writer(engine):
    """Another process holding the write lock for the whole test."""
    db = sqlite3.connect(str(engine.store.path), timeout=1, isolation_level=None)
    db.execute("BEGIN IMMEDIATE")
    yield db
    db.execute("ROLLBACK")
    db.close()


POLLERS = {
    "extract": lambda e: e.process_one(),
    "review": lambda e: e.review_one(),
    "chats": lambda e: Chats(e).process_one(),
    "backfill": lambda e: Backfill(e).step(),
    "relations": lambda e: Relations(e).process_one(),
    "knowledge": lambda e: Knowledge(e).process_one(),
    "embed": lambda e: Knowledge(e).embed_one(),
}


@pytest.mark.parametrize("name", sorted(POLLERS))
def test_idle_poll_returns_false_while_another_process_holds_the_write_lock(engine, writer, name):
    assert not POLLERS[name](engine)


def test_opening_a_current_database_does_not_wait_for_the_write_lock(engine, writer):
    from gramem.store import Store

    opened = []
    thread = threading.Thread(target=lambda: opened.append(Store(engine.store.path)))
    thread.start()
    thread.join(3)
    alive = thread.is_alive()
    writer.execute("ROLLBACK")
    thread.join(20)
    writer.execute("BEGIN IMMEDIATE")  # keep the fixture teardown balanced
    assert not alive, "opening an up-to-date database blocked on the write lock"
    for store in opened:
        store.close()


def test_idle_poll_still_finds_real_work(engine):
    engine.store.db.execute("PRAGMA busy_timeout=15000")
    now = engine.clock()
    with engine.store.transaction() as db:
        db.execute(
            "INSERT INTO sources(id,principal,session,kind,content,created,status,attempts,retry_at,epoch) "
            "VALUES('s1',?,'sess','turn','我偏好简短解释',?,'pending',0,0,0)",
            ("owner\x1fowner\x1fowner", now),
        )
    assert engine.process_one()


def test_poll_delay_is_jittered_backs_off_and_is_capped():
    from gramem.polling import poll_delay

    assert 1.0 <= poll_delay(0, rand=lambda: 0.0) <= 1.0001
    assert 1.4 <= poll_delay(0, rand=lambda: 1.0) <= 1.6
    assert poll_delay(3, rand=lambda: 0.0) > poll_delay(1, rand=lambda: 0.0)
    assert poll_delay(100, rand=lambda: 1.0) <= 45.0
