"""Optional OpenAI-compatible processing. No provider keys are persisted."""

import hashlib
import math
import os
import threading
from collections import OrderedDict

import httpx

from .tokens import compact


class Model:
    def __init__(self, config, secret_resolver=os.getenv):
        self._embedding_cache = OrderedDict()
        self._cache_lock = threading.Lock()
        self.config = config
        self.secret_resolver = secret_resolver
        self.client = httpx.Client(timeout=config.timeout)
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
        self._usage_lock = threading.Lock()
        self._thread_usage = threading.local()

    @property
    def thread_usage(self):
        return dict(getattr(self._thread_usage, "counts", {}))

    @property
    def available(self):
        return bool(self.config.model and self.secret_resolver(self.config.api_key_env))

    @property
    def space(self):
        return compact(
            [
                self.config.base_url,
                self.config.embedding_model,
                self.config.embedding_dimensions,
                self.config.embedding_revision,
            ]
        )

    def _post(self, endpoint, payload):
        from urllib.parse import urlparse

        if urlparse(self.config.base_url).hostname == "openrouter.ai":
            payload = dict(payload)
            payload["provider"] = {"sort": self.config.embedding_provider_preference
                if endpoint == "/embeddings" else self.config.provider_preference,
                "allow_fallbacks": True}
            if endpoint != "/embeddings":
                payload.pop("enable_thinking", None)
                payload["reasoning"] = {"enabled": False}
                payload["response_format"] = {"type": "json_object"}
                payload["provider"]["require_parameters"] = True
        key = self.secret_resolver(self.config.api_key_env)
        if not key:
            raise RuntimeError("memory model key is unavailable")
        try:
            response = self.client.post(
                self.config.base_url.rstrip("/") + endpoint,
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
                timeout=min(5, self.config.timeout)
                if endpoint == "/embeddings"
                else self.config.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError("memory model request failed") from exc
        if not isinstance(data, dict):
            raise RuntimeError("invalid memory model response")
        usage = data.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}

        def token_count(key):
            value = usage.get(key)
            return max(0, value) if type(value) is int else 0

        delta = {
            "calls": 1,
            "input_tokens": token_count("prompt_tokens"),
            "output_tokens": token_count("completion_tokens"),
        }
        with self._usage_lock:
            for k, v in delta.items():
                self.usage[k] += v
        counts = getattr(self._thread_usage, "counts", {})
        self._thread_usage.counts = {k: counts.get(k, 0) + v for k, v in delta.items()}
        return data

    def extract(self, prompt, payload):
        import json

        data = self._post(
            "/chat/completions",
            {
                "model": self.config.model,
                "temperature": 0,
                **(
                    {"enable_thinking": False}
                    if self.config.model.lower().startswith("qwen")
                    else {}
                ),
                **(
                    {"response_format": {"type": "json_object"}}
                    if not self.config.model.lower().startswith("qwen")
                    else {}
                ),
                "max_tokens": self.config.extraction_tokens,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": compact(payload)},
                ],
            },
        )
        try:
            content = data["choices"][0]["message"]["content"].strip()
            if content.startswith("```") and content.endswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
            raise RuntimeError("invalid memory model result") from exc

    def embed(self, text):
        if not self.config.embedding_model:
            return None
        cache_key = hashlib.sha256((self.space + text).encode()).hexdigest()
        with self._cache_lock:
            if cache_key in self._embedding_cache:
                self._embedding_cache.move_to_end(cache_key)
                return list(self._embedding_cache[cache_key])
        payload = {"model": self.config.embedding_model, "input": text}
        if self.config.embedding_dimensions:
            payload["dimensions"] = self.config.embedding_dimensions
        try:
            vector = self._post("/embeddings", payload)["data"][0]["embedding"]
            if (
                not isinstance(vector, list)
                or not vector
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)
            ):
                raise ValueError("invalid vector")
            if self.config.embedding_dimensions and len(vector) != self.config.embedding_dimensions:
                raise ValueError("embedding dimension mismatch")
            vector = [float(v) for v in vector]
            with self._cache_lock:
                self._embedding_cache[cache_key] = tuple(vector)
                if len(self._embedding_cache) > 256:
                    self._embedding_cache.popitem(last=False)
            return vector
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("invalid memory embedding") from exc

    def close(self):
        self.client.close()
