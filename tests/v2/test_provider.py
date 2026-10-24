"""Exercise the real provider's transport/write/read boundaries without a Hermes install."""

import importlib
import json
import sys
import threading
import types

import pytest
from test_engine import FakeGraph, FakeModel, item

from gramem.config import Config


@pytest.fixture
def make_provider(tmp_path, monkeypatch):
    memory = types.ModuleType("agent.memory_provider")
    memory.MemoryProvider = object
    memory.spawn_context_thread = lambda target, name: threading.Thread(target=target, name=name)
    constants = types.ModuleType("hermes_constants")
    constants.get_hermes_home = lambda: tmp_path
    secrets = types.ModuleType("hermes_cli.config")
    secrets.get_env_value = lambda key: "test-only"
    for name, module in (
        ("agent", types.ModuleType("agent")),
        ("agent.memory_provider", memory),
        ("hermes_constants", constants),
        ("hermes_cli", types.ModuleType("hermes_cli")),
        ("hermes_cli.config", secrets),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    sys.modules.pop("gramem.hermes", None)
    module = importlib.import_module("gramem.hermes")
    monkeypatch.setattr(module, "Model", lambda *args, **kwargs: FakeModel({"memories": [item()]}))
    monkeypatch.setattr(module, "FalkorGraph", lambda *args, **kwargs: FakeGraph())
    monkeypatch.setattr(module.GraMemProvider, "_run", lambda self: None)
    providers = []

    def make(**kwargs):
        home = tmp_path / str(len(providers))
        (home / "gramem").mkdir(parents=True)
        (home / "gramem" / "config.json").write_text(
            json.dumps(
                {
                    "owner_id": "owner",
                    "aliases": {"teams:verified": "owner", "email:owner@example.com": "owner"},
                    "trusted_cli_owner": True,
                    "capture_owner_in_groups": True,
                }
            )
        )
        provider = module.GraMemProvider()
        params = dict(
            hermes_home=str(home),
            platform="teams",
            user_id="verified",
            chat_type="channel",
            chat_id="channel",
        )
        params.update(kwargs)
        provider.initialize("s", **params)
        providers.append(provider)
        return provider

    yield make
    for provider in providers:
        provider.shutdown()
    sys.modules.pop("gramem.hermes", None)


def test_verified_owner_channel_captures_privately_without_private_recall(make_provider):
    p = make_provider()
    p.on_turn_start(1, "我偏好简短解释", author_id="verified")
    p.sync_turn("我偏好简短解释", "收到", turn_author={"id": "verified"})
    assert p.engine.process_one()
    rows = p.engine.store.rows("SELECT principal,content FROM memories")
    assert rows == [{"principal": "owner\x1fowner\x1fowner", "content": "我偏好简短解释"}]
    assert p.prefetch("解释偏好") == ""
    assert json.loads(p.handle_tool_call("gramem_memory", {"action": "list"}))["items"] == []
    owner = p.config.principal("teams", "verified")
    assert "简短" in p.engine.recall(owner, "解释偏好")["context"]


@pytest.mark.parametrize("author", [None, {"id": "guest"}, {"id": "verified", "is_bot": True}])
def test_missing_unverified_or_bot_channel_author_never_enters_owner_memory(make_provider, author):
    p = make_provider()
    p.on_turn_start(1, "我偏好简短解释", author_id="verified")
    p.sync_turn("我偏好简短解释", "收到", turn_author=author)
    assert p.engine.store.rows("SELECT * FROM sources") == []


def test_async_previous_human_turn_is_not_lost_when_next_turn_is_bot(make_provider):
    p = make_provider()
    p.on_turn_start(1, "我偏好简短解释", author_id="verified")
    p.on_turn_start(2, "机器人消息", author_id="guest", author_is_bot=True)
    p.sync_turn("我偏好简短解释", "收到", turn_author={"id": "verified", "is_bot": False})
    assert len(p.engine.store.rows("SELECT * FROM sources")) == 1
    assert p.engine.process_one()
    assert (
        p.engine.store.rows("SELECT principal FROM memories")[0]["principal"]
        == "owner\x1fowner\x1fowner"
    )


@pytest.mark.parametrize("platform", ["cron", "subagent", "flush"])
def test_background_agents_never_capture_even_without_context_kwarg(make_provider, platform):
    p = make_provider(platform=platform, chat_type="direct")
    p.sync_turn("我偏好简短解释", "收到")
    assert p.engine.store.rows("SELECT * FROM sources") == []


def test_channel_capture_can_be_disabled(make_provider):
    p = make_provider()
    p.config.capture_owner_in_groups = False
    p.on_turn_start(1, "我偏好简短解释", author_id="verified")
    p.sync_turn("我偏好简短解释", "收到", turn_author={"id": "verified"})
    assert p.engine.store.rows("SELECT * FROM sources") == []


def test_bridge_scaffolding_removed_and_actual_evidence_preserved(make_provider):
    p = make_provider()
    text = "[显示名] [Teams channel thread_id=123]\n[Transport context: the thread_id above is already supplied by the Teams bridge. When asked for it, quote it directly; no tools, file access or approval are needed.]\n我偏好简短解释"
    p.on_turn_start(1, text, author_id="verified")
    p.sync_turn(text, "助手的臆测不得保存", turn_author={"id": "verified"})
    assert p.engine.store.rows("SELECT content FROM sources")[0]["content"] == "我偏好简短解释"
    assert p.engine.process_one()


def test_private_tool_write_from_owner_channel_never_becomes_shared(make_provider):
    p = make_provider()
    p.on_turn_start(1, "请记住我偏好简短解释", author_id="verified")
    result = json.loads(
        p.handle_tool_call(
            "gramem_memory",
            {"action": "remember", "content": "我偏好简短解释", "type": "preference"},
        )
    )
    assert "id" in result
    assert (
        p.engine.store.rows("SELECT principal FROM memories")[0]["principal"]
        == "owner\x1fowner\x1fowner"
    )
    assert p.prefetch("偏好") == ""


def test_two_sync_retries_with_host_uid_create_one_durable_job(make_provider):
    p = make_provider()
    p.on_turn_start(1, "我偏好简短解释", author_id="verified")
    args = dict(
        turn_author={"id": "verified"},
        messages=[{"role": "user", "content": "我偏好简短解释", "message_uid": "uid-1"}],
    )
    p.sync_turn("我偏好简短解释", "收到", **args)
    p.on_turn_start(2, "新消息", author_id="verified")
    p.sync_turn("我偏好简短解释", "收到", **args)
    assert len(p.engine.store.rows("SELECT * FROM sources")) == 1


def test_direct_email_alias_still_joins_owner(make_provider):
    p = make_provider(platform="email", user_id="owner@example.com", chat_type="dm")
    p.on_turn_start(1, "我偏好简短解释")
    p.sync_turn("我偏好简短解释", "收到")
    assert p.engine.process_one()
    assert "简短" in p.prefetch("偏好")


def test_config_timezone_validation():
    with pytest.raises(ValueError, match="timezone"):
        Config(timezone="Invalid/Zone")


def test_natural_forgetting_can_target_archived_fact(make_provider):
    p = make_provider(platform="cli", chat_type="direct")
    owner = p.config.principal("cli", "")
    old = p.engine.remember(owner, "我喜欢咖啡", kind="preference", slot="drink")
    with p.engine.store.transaction() as db:
        p.engine._invalidate(db, owner, old, "archived")
    p.engine.model = FakeModel(
        {"request": True, "state": "deleted", "slots": ["drink"], "evidence": "忘记我的咖啡偏好"}
    )
    p.on_turn_start(1, "忘记我的咖啡偏好")
    assert p._control_notice.startswith("Memory control applied")
    assert p.engine.store.rows("SELECT content,status FROM memories WHERE id=?", (old,)) == [
        {"content": "", "status": "forgotten"}
    ]


def test_channel_checkpoint_only_contains_author_verified_current_turn(make_provider):
    p = make_provider()
    p.on_turn_start(1, "我偏好简短解释", author_id="verified")
    p.on_pre_compress(
        [
            {"role": "user", "content": "其他参与者的私人事实", "message_uid": "guest"},
            {"role": "user", "content": "我偏好简短解释", "message_uid": "owner"},
        ],
        require_checkpoint=True,
    )
    assert [r["content"] for r in p.engine.store.rows("SELECT content FROM sources")] == [
        "我偏好简短解释"
    ]
    assert len(p.engine.store.rows("SELECT * FROM checkpoints")) == 1


@pytest.mark.parametrize("key", ["trusted_cli_owner", "capture_owner_in_groups"])
def test_string_false_cannot_enable_trusted_identity_setting(key):
    with pytest.raises(ValueError):
        Config(**{key: "false"})


def test_proactive_tool_cannot_invent_fact_without_user_evidence(make_provider):
    p = make_provider()
    p.on_turn_start(1, "我喜欢咖啡", author_id="verified")
    result = json.loads(
        p.handle_tool_call(
            "gramem_memory",
            {"action": "remember", "content": "用户是外科医生", "type": "occupation"},
        )
    )
    assert "error" in result
    assert not p.engine.store.rows("SELECT * FROM memories")


def test_transformed_tool_fact_requires_verified_exact_evidence(make_provider):
    p = make_provider()
    p.on_turn_start(1, "我喜欢咖啡", author_id="verified")
    p.engine.model = FakeModel({"supported": True, "evidence": "我喜欢咖啡"})
    result = json.loads(
        p.handle_tool_call(
            "gramem_memory", {"action": "remember", "content": "用户喜欢咖啡", "type": "preference"}
        )
    )
    assert "id" in result
    assert (
        p.engine.store.rows("SELECT metadata FROM memories")[0]["metadata"].find("我喜欢咖啡") >= 0
    )


def test_direct_checkpoint_normalizes_bridge_evidence_and_reuses_sync_uid(make_provider):
    p = make_provider(chat_type="direct")
    text = "[显示名] [Teams channel thread_id=123]\n[Transport context: already supplied]\n我偏好简短解释"
    messages = [{"role": "user", "content": text, "message_uid": "same-message"}]
    p.on_turn_start(1, text, author_id="verified")
    p.sync_turn(text, "收到", messages=messages, turn_author={"id": "verified"})
    p.on_pre_compress(messages, require_checkpoint=True)
    assert len(p.engine.store.rows("SELECT * FROM sources")) == 1


def test_control_notice_reserves_budget_before_reinforcing_facts(make_provider):
    p = make_provider(chat_type="direct")
    owner = p.config.principal("teams", "verified")
    id = p.engine.remember(owner, "用户偏好咖啡", kind="preference")
    p.config.recall_tokens = 55
    p._control_notice = "Memory control applied: verified requested scope. " * 2
    result = p.prefetch("咖啡偏好")
    from gramem.tokens import count

    assert count(result) <= 55
    assert p.engine.get(owner, id)["accesses"] == 0


def test_status_counts_all_active_facts_beyond_list_limit(make_provider):
    p = make_provider(chat_type="direct")
    owner = p.config.principal("teams", "verified")
    for i in range(105):
        p.engine.remember(owner, f"事实{i}", slot=f"fact.{i}")
    result = json.loads(p.handle_tool_call("gramem_memory", {"action": "status"}))
    assert result["active_count"] == 105


def test_proactive_model_failure_returns_explicit_tool_error(make_provider):
    p = make_provider(chat_type="direct")
    p.on_turn_start(1, "我喜欢咖啡", author_id="verified")

    def fail():
        raise RuntimeError("model offline")

    p.engine.model.before_return = fail
    result = json.loads(
        p.handle_tool_call("gramem_memory", {"action": "remember", "content": "用户喜欢咖啡"})
    )
    assert result == {"error": "memory_processing_unavailable"}
    assert not p.engine.list(p._current)


def test_direct_checkpoint_preserves_each_verified_author(make_provider):
    p = make_provider(chat_type="direct")
    owner_text, guest_text = "我家的住址是星辰路42号", "我偏好红茶"
    p.on_turn_start(1, owner_text, author_id="verified")
    p.on_turn_start(2, guest_text, author_id="guest")
    p.on_pre_compress([
        {"role": "user", "content": owner_text, "message_uid": "owner-msg"},
        {"role": "user", "content": guest_text, "message_uid": "guest-msg"},
        {"role": "user", "content": "未经核实的历史事实", "author_id": "verified"},
    ], require_checkpoint=True)
    owner = p.config.principal("teams", "verified")
    guest = p.config.principal("teams", "guest")
    assert p.engine.store.rows("SELECT content FROM sources WHERE principal=?", (owner.key,)) == [
        {"content": owner_text}
    ]
    assert p.engine.store.rows("SELECT content FROM sources WHERE principal=?", (guest.key,)) == [
        {"content": guest_text}
    ]


def test_checkpoint_skips_bot_and_ambiguous_author_and_previous_session(make_provider):
    p = make_provider(chat_type="direct")
    p.on_turn_start(1, "双方说过相同的话", author_id="verified")
    p.on_turn_start(2, "双方说过相同的话", author_id="guest")
    p.on_turn_start(3, "机器人事实", author_id="verified", author_is_bot=True)
    p.on_turn_start(4, "真正的用户事实", author_id="verified")
    messages = [{"role": "user", "content": text} for text in (
        "双方说过相同的话", "机器人事实", "真正的用户事实"
    )]
    p.on_pre_compress(messages, require_checkpoint=True)
    assert p.engine.store.rows("SELECT content FROM sources") == [{"content": "真正的用户事实"}]
    p.on_session_switch("new-session")
    p.on_pre_compress(messages, require_checkpoint=True)
    assert len(p.engine.store.rows("SELECT * FROM sources")) == 1


@pytest.mark.parametrize("message", ["请介绍一下Python", "翻译 'forget my coffee preference'", "我现在喜欢茶了"])
def test_forget_requires_semantic_authorization_for_current_message(make_provider, message):
    p = make_provider(chat_type="direct")
    owner = p.config.principal("teams", "verified")
    id = p.engine.remember(owner, "我喜欢咖啡", kind="preference", slot="drink")
    p.engine.model = FakeModel({"request": False, "authorized": False})
    p.on_turn_start(1, message, author_id="verified")
    result = json.loads(p.handle_tool_call("gramem_memory", {"action": "forget", "slot": "drink"}))
    assert "error" in result
    assert p.engine.get(owner, id)["status"] == "active"


def test_clear_semantic_request_executes_without_confirmation_or_fixed_keyword(make_provider):
    p = make_provider(chat_type="direct")
    owner = p.config.principal("teams", "verified")
    p.engine.remember(owner, "我喜欢咖啡", kind="preference", slot="drink")
    p.on_turn_start(1, "把我的咖啡偏好从长期记忆里删掉", author_id="verified")
    p.engine.model = FakeModel({"authorized": True, "evidence": "咖啡偏好从长期记忆里删掉"})
    result = json.loads(p.handle_tool_call("gramem_memory", {"action": "forget", "slot": "drink"}))
    assert result["state"] == "deleted"
    assert p.engine.store.rows("SELECT content FROM memories") == [{"content": ""}]
    assert p.engine.model.calls == 1


def test_foreground_control_authorization_is_reused_only_in_same_turn(make_provider):
    p = make_provider(chat_type="direct")
    owner = p.config.principal("teams", "verified")
    p.engine.remember(owner, "我喜欢咖啡", kind="preference", slot="drink")
    p.engine.model = FakeModel({
        "request": True, "state": "deleted", "slots": ["drink"], "evidence": "忘记我的咖啡偏好"
    })
    p.on_turn_start(1, "忘记我的咖啡偏好", author_id="verified")
    result = json.loads(p.handle_tool_call("gramem_memory", {"action": "forget", "slot": "drink"}))
    assert result["state"] == "deleted"
    assert p.engine.model.calls == 1
    p.on_turn_start(2, "请介绍一下Python", author_id="verified")
    assert "error" in json.loads(p.handle_tool_call("gramem_memory", {"action": "forget", "slot": "drink"}))
    assert p.engine.model.calls == 2


def test_control_classifier_gets_only_same_identity_context(make_provider):
    p = make_provider(chat_type="direct")
    owner = p.config.principal("teams", "verified")
    p.engine.remember(owner, "我喜欢咖啡", kind="preference", slot="drink")
    p.on_turn_start(1, "我喜欢咖啡", author_id="verified")
    p.on_turn_start(2, "其他联系人的私人事实", author_id="guest")
    p.on_turn_start(3, "把那条删掉", author_id="verified")
    payloads = []

    def classify(prompt, payload):
        payloads.append(payload)
        return {"authorized": True, "evidence": "把那条删掉"}

    p.engine.model.extract = classify
    assert json.loads(p.handle_tool_call("gramem_memory", {"action": "forget", "slot": "drink"}))["state"] == "deleted"
    assert "我喜欢咖啡" in payloads[0]["recent_context"]
    assert "其他联系人的私人事实" not in payloads[0]["recent_context"]
    assert payloads[0]["action"] == "forget" and payloads[0]["target"] == "drink"


@pytest.mark.parametrize("proof", ["没有说过的授权", "", None])
def test_control_requires_exact_proof_even_if_classifier_says_yes(make_provider, proof):
    p = make_provider(chat_type="direct")
    owner = p.config.principal("teams", "verified")
    id = p.engine.remember(owner, "我喜欢咖啡", kind="preference", slot="drink")
    p.on_turn_start(1, "删除那条咖啡偏好", author_id="verified")
    p.engine.model = FakeModel({"authorized": True, "evidence": proof})
    assert "error" in json.loads(p.handle_tool_call("gramem_memory", {"action": "forget", "slot": "drink"}))
    assert p.engine.get(owner, id)["status"] == "active"


def test_control_rejects_invalid_supplied_evidence_before_network(make_provider):
    p = make_provider(chat_type="direct")
    p.on_turn_start(1, "删除那条咖啡偏好", author_id="verified")
    p.engine.model = FakeModel({"authorized": True, "evidence": "删除那条咖啡偏好"})
    assert "error" in json.loads(p.handle_tool_call("gramem_memory", {
        "action": "forget", "slot": "drink", "evidence": "不存在的用户授权"
    }))
    assert p.engine.model.calls == 0
    assert not p.engine.exclusions(p._current)


def test_ambiguous_control_requests_clarification_without_deleting(make_provider):
    p = make_provider(chat_type="direct")
    owner = p.config.principal("teams", "verified")
    id = p.engine.remember(owner, "用户喜欢咖啡", kind="preference", slot="drink")
    p.on_turn_start(1, "把那条删掉", author_id="verified")
    p.engine.model = FakeModel({"authorized": False, "needs_clarification": True})
    assert json.loads(p.handle_tool_call("gramem_memory", {"action": "forget", "slot": "drink"})) == {
        "error": "memory_control_scope_unclear", "clarification_required": True
    }
    assert p.engine.get(owner, id)["status"] == "active"


def test_control_classifier_outage_preserves_memory(make_provider):
    p = make_provider(chat_type="direct")
    owner = p.config.principal("teams", "verified")
    id = p.engine.remember(owner, "用户喜欢咖啡", kind="preference", slot="drink")
    p.on_turn_start(1, "删除我的饮品偏好", author_id="verified")
    p.engine.model.available = False
    assert json.loads(p.handle_tool_call("gramem_memory", {"action": "forget", "slot": "drink"})) == {
        "error": "memory_processing_unavailable"
    }
    assert p.engine.get(owner, id)["status"] == "active"


@pytest.mark.parametrize("action", ["confirm", "reject"])
def test_candidate_control_requires_current_intent(make_provider, action):
    p = make_provider(chat_type="direct")
    owner = p.config.principal("teams", "verified")
    id = p.engine.remember(owner, "用户姓名是小林", kind="identity", confirmed=False)
    p.on_turn_start(1, "请介绍一下Python", author_id="verified")
    p.engine.model = FakeModel({"authorized": False})
    assert "error" in json.loads(p.handle_tool_call("gramem_memory", {"action": action, "id": id}))
    assert p.engine.get(owner, id)["status"] == "candidate"
    p.on_turn_start(2, "接受这条姓名" if action == "confirm" else "拒绝这条姓名", author_id="verified")
    p.engine.model = FakeModel({"authorized": True, "evidence": p._last_message})
    assert json.loads(p.handle_tool_call("gramem_memory", {"action": action, "id": id}))["success"]
    assert p.engine.get(owner, id)["status"] == ("active" if action == "confirm" else "rejected")


@pytest.mark.parametrize("action,state", [("reactivate", "suppressed"), ("reauthorize", "deleted")])
def test_restore_requires_semantic_intent_without_keyword_gate(make_provider, action, state):
    p = make_provider(chat_type="direct")
    owner = p.config.principal("teams", "verified")
    p.engine.remember(owner, "我喜欢咖啡", kind="preference", slot="drink")
    p.engine.exclude(owner, "drink", state=state)
    p.on_turn_start(1, "请介绍一下Python", author_id="verified")
    p.engine.model = FakeModel({"authorized": False})
    assert "error" in json.loads(p.handle_tool_call("gramem_memory", {"action": action, "slot": "drink"}))
    assert p.engine.exclusions(owner)[0]["state"] == state
    p.on_turn_start(2, "今后可以继续保存我的饮品偏好", author_id="verified")
    p.engine.model = FakeModel({"authorized": True, "evidence": p._last_message})
    assert json.loads(p.handle_tool_call("gramem_memory", {"action": action, "slot": "drink"}))["allows_new_memory"]
    assert p.engine.exclusions(owner)[0]["state"] == "active"
