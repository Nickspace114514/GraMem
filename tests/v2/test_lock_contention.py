"""Regressions for cross-process write-lock contention and its diagnostics."""

import logging
import os
import sqlite3
import threading

import pytest
from test_engine import OWNER, FakeGraph

from gramem import store as store_module
from gramem.config import Config
from gramem.engine import Engine


@pytest.fixture
def engine(tmp_path):
    e = Engine(tmp_path / "memory.sqlite", Config(), graph=FakeGraph())
    yield e
    e.close()


def other_writer(path):
    db = sqlite3.connect(str(path), timeout=0.2, isolation_level=None)
    db.execute("BEGIN IMMEDIATE")
    db.execute("ROLLBACK")
    db.close()


def test_read_snapshot_does_not_take_the_write_lock(engine):
    engine.remember(OWNER, "Hermes 使用独立的关系图数据库", kind="project")
    with engine.store.read() as db:
        assert db.execute("SELECT count(*) FROM memories").fetchone()[0] == 1
        other_writer(engine.store.path)  # would raise "database is locked" under BEGIN IMMEDIATE


def test_read_only_engine_paths_leave_writers_free(engine, monkeypatch):
    id = engine.remember(OWNER, "用户喜欢咖啡", kind="preference", slot="drink")
    original = engine.store.read
    seen = []

    def probe():
        cm = original()

        class Wrapped:
            def __enter__(self):
                db = cm.__enter__()
                other_writer(engine.store.path)
                seen.append(True)
                return db

            def __exit__(self, *exc):
                return cm.__exit__(*exc)

        return Wrapped()

    monkeypatch.setattr(engine.store, "read", probe)
    assert engine.get(OWNER, id)["id"] == id
    assert engine.list(OWNER)
    assert seen


def test_slow_write_transaction_is_logged_with_caller(engine, monkeypatch, caplog):
    monkeypatch.setattr(store_module, "SLOW_TRANSACTION_SECONDS", 0.0)
    with caplog.at_level(logging.WARNING, logger="gramem.store"):
        with engine.store.transaction() as db:
            db.execute("SELECT 1")
    assert "write transaction held" in caplog.text


def test_watchdog_reports_stack_of_stuck_holder_once(engine, monkeypatch, caplog):
    monkeypatch.setattr(store_module, "STUCK_TRANSACTION_SECONDS", 0.0)
    entered, release = threading.Event(), threading.Event()

    def hold():
        with engine.store.transaction():
            entered.set()
            release.wait(5)

    thread = threading.Thread(target=hold, name="stuck-holder")
    thread.start()
    entered.wait(5)
    try:
        with caplog.at_level(logging.WARNING, logger="gramem.store"):
            now = store_module.time.monotonic() + 1
            store_module._scan(now)
            store_module._scan(now + 1)  # rate limited
        reports = [r for r in caplog.records if "stuck-holder" in r.getMessage()]
        assert len(reports) == 1 and "release.wait" in reports[0].getMessage()
    finally:
        release.set()
        thread.join()
    assert engine.store._holder is None
    store_module._scan(store_module.time.monotonic() + 100)
    assert engine.store._holder is None


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs FIFOs")
def test_audio_cache_fifo_neither_blocks_nor_holds_the_lock(tmp_path):
    from gramem.chat_audio import ChatAudio

    home = tmp_path
    (home / "cache/audio").mkdir(parents=True)
    fifo = home / "cache/audio/voice.mp3"
    os.mkfifo(fifo)
    result = []
    thread = threading.Thread(target=lambda: result.append(_read(ChatAudio, fifo, home)))
    thread.start()
    thread.join(5)
    assert not thread.is_alive(), "reading a FIFO from the audio cache blocked"
    assert result == ["invalid_size"]


def _read(cls, path, home):
    try:
        cls._read_cache(str(path), home)
    except ValueError as exc:
        return str(exc)
    return "read"
