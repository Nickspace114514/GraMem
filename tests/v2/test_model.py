import json
import threading

import httpx
from test_engine import OWNER, FakeModel, item

from gramem.config import Config
from gramem.engine import Engine
from gramem.model import Model


def test_openrouter_preferences_reach_text_and_embedding_requests():
    requests = []
    cfg = Config(model="qwen/qwen3.8-flash", base_url="https://openrouter.ai/api/v1",
                 api_key_env="OPENROUTER_API_KEY", embedding_model="qwen/qwen3-embedding-8b",
                 embedding_dimensions=3, provider_preference="price",
                 embedding_provider_preference="throughput")
    model = Model(cfg, secret_resolver=lambda key: "test")
    model.client.close()
    def reply(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if request.url.path.endswith("embeddings"):
            return httpx.Response(200, json={"data": [{"embedding": [.1, .2, .3]}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
    model.client = httpx.Client(transport=httpx.MockTransport(reply))
    try:
        model.extract("test", {})
        assert model.embed("synthetic") == [.1, .2, .3]
        assert requests[0]["provider"]["sort"] == "price"
        assert requests[0]["reasoning"] == {"enabled": False}
        assert "enable_thinking" not in requests[0]
        assert requests[1]["provider"]["sort"] == "throughput"
        assert "reasoning" not in requests[1]
        assert requests[1]["dimensions"] == cfg.embedding_dimensions
    finally:
        model.close()


def test_token_usage_isolated_between_concurrent_worker_threads():
    model = Model(Config(model="test"), secret_resolver=lambda key: "test")
    model.client.close()
    model.client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "{}"}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3},
                },
            )
        )
    )
    snapshots = []

    def call():
        model.extract("check", {})
        snapshots.append(model.thread_usage)

    threads = [threading.Thread(target=call) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert snapshots == [{"calls": 1, "input_tokens": 7, "output_tokens": 3}] * 2
    assert model.usage == {"calls": 2, "input_tokens": 14, "output_tokens": 6}
    assert model.thread_usage == {}
    model.close()


def test_failed_attempt_token_usage_survives_retry(tmp_path):
    class Metered(FakeModel):
        def __init__(self):
            super().__init__({"bad": "schema"})
            self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

        def extract(self, prompt, payload):
            self.usage["calls"] += 1
            self.usage["input_tokens"] += 10
            self.usage["output_tokens"] += 5
            return self.result

    model = Metered()
    engine = Engine(tmp_path / "memory.db", model=model)
    try:
        engine.enqueue(OWNER, "我偏好简短解释", session="s")
        engine.process_one()
        result = json.loads(engine.store.rows("SELECT result FROM sources")[0]["result"])
        assert result["outcome"] == "failed_attempt"
        model.result = {"memories": [item()]}
        with engine.store.transaction() as db:
            db.execute("UPDATE sources SET retry_at=0")
        engine.process_one()
        assert engine.status()["durable_usage"] == {"input_tokens": 20, "output_tokens": 10}
    finally:
        engine.close()
