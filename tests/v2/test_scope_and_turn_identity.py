"""Shared-chat detection is an allowlist; provider hash turns link to native rows."""

import hashlib
import sqlite3

import pytest
from test_context_gramem_fixes import native
from test_engine import OWNER
from test_provider import make_provider  # noqa: F401

from gramem.chat_import import import_sessions
from gramem.chats import Chats
from gramem.config import Config, is_shared_chat
from gramem.engine import Engine
from gramem.evidence import user_evidence


@pytest.mark.parametrize(
    "chat_type", ["group", "channel", "thread", "supergroup", "forum", "guild", "room", "webhook", "new-kind"]
)
def test_unknown_and_threaded_chats_are_shared(chat_type):
    assert is_shared_chat(chat_type)


@pytest.mark.parametrize("chat_type", ["dm", "direct", "private", "c2c", "DM", None, ""])
def test_known_private_chats_are_private(chat_type):
    assert not is_shared_chat(chat_type)


def test_thread_session_never_recalls_owner_private_memory(make_provider):  # noqa: F811
    private = make_provider(chat_type="dm")
    owner = private.config.principal("teams", "verified")
    private.engine.remember(owner, "用户的私人电话是保密的", kind="profile", slot="phone")
    thread = make_provider(chat_type="thread", chat_id="t1", hermes_home=str(private.home))
    thread.on_turn_start(1, "电话", author_id="verified")
    assert thread._current.scope == "group"
    assert "私人电话" not in thread.prefetch("私人电话")


def test_import_skips_thread_sessions(tmp_path):
    path = tmp_path / "state.db"
    native(path, [(1, "user", "线程里的问题", "u1", 1, 0), (2, "assistant", "回答", "a1", 1, 0)])
    with sqlite3.connect(path) as db:
        db.execute("UPDATE sessions SET chat_type='thread'")
    engine = Engine(tmp_path / "memory.sqlite", Config(aliases={"teams:verified": "owner"}))
    try:
        assert import_sessions(engine, path)["skipped_sessions"] == 1
        assert not engine.store.rows("SELECT * FROM chat_turns")
    finally:
        engine.close()


def test_provider_hash_turn_links_to_native_row_and_follows_rewind(tmp_path):
    user = "我明天要去机场"
    path = tmp_path / "state.db"
    native(path, [(1, "user", user, "u1", 1, 0), (2, "assistant", "好的", "a1", 1, 0)])
    engine = Engine(tmp_path / "memory.sqlite", Config(aliases={"teams:verified": "owner"}))
    archive = Chats(engine)
    try:
        digest = hashlib.sha256(user_evidence(user).encode()).hexdigest()
        id = archive.capture(OWNER, user, "好的", session="s", turn=digest, platform="teams")
        # Import must link, not duplicate, the provider's archive.
        assert import_sessions(engine, path)["imported"] == 0
        assert len(engine.store.rows("SELECT * FROM chat_turns")) == 1
        state = engine.store.rows("SELECT native_id,active FROM chat_native_state WHERE turn_id=?", (id,))
        assert state == [{"native_id": 1, "active": 1}]
        with sqlite3.connect(path) as db:
            db.execute("UPDATE messages SET active=0 WHERE id=1")
        import_sessions(engine, path)
        state = engine.store.rows("SELECT native_id,active FROM chat_native_state WHERE turn_id=?", (id,))
        assert state == [{"native_id": 1, "active": 0}]
        assert archive.search(OWNER)["total"] == 0
    finally:
        engine.close()


def test_ambiguous_repeated_input_stays_unlinked(tmp_path):
    user = "好的"
    path = tmp_path / "state.db"
    native(path, [(1, "user", user, "u1", 1, 0), (2, "assistant", "嗯", "a1", 1, 0),
                  (3, "user", user, "u3", 1, 0), (4, "assistant", "嗯", "a3", 1, 0)])
    engine = Engine(tmp_path / "memory.sqlite", Config(aliases={"teams:verified": "owner"}))
    try:
        digest = hashlib.sha256(user_evidence(user).encode()).hexdigest()
        id = Chats(engine).capture(OWNER, "好的 明白", "嗯", session="s", turn=digest, platform="teams")
        import_sessions(engine, path)
        if id:
            assert not engine.store.rows("SELECT * FROM chat_native_state WHERE turn_id=?", (id,))
    finally:
        engine.close()
