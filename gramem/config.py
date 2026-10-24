import json
import math
import re
from dataclasses import dataclass, field, fields
from pathlib import Path

DECAY = dict(
    identity=0.001,
    preference=0.003,
    skill=0.005,
    project=0.01,
    relationship=0.003,
    episodic=0.03,
    knowledge=0.01,
    temporary=0.2,
)


# Chat types known to be one-to-one. Everything else (group, channel, thread,
# supergroup, forum, guild, room, webhook, future types) is treated as shared so
# private memory never reaches a conversation other people can read.
PRIVATE_CHAT_TYPES = frozenset({"dm", "direct", "private", "c2c"})


def is_shared_chat(chat_type):
    """True unless the chat type is known to be private; missing means direct/CLI."""
    if chat_type is None or chat_type == "":
        return False
    return str(chat_type).lower() not in PRIVATE_CHAT_TYPES


@dataclass
class Config:
    recall_tokens: int = 1024
    always_limit: int = 3
    relevant_limit: int = 8
    historical_limit: int = 4
    graph_recall_enabled: bool = True
    graph_recall_hops: int = 2
    graph_recall_limit: int = 3
    graph_recall_tokens: int = 256
    extraction_tokens: int = 1800
    extraction_input_tokens: int = 4000
    max_items: int = 5
    model: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key_env: str = "DASHSCOPE_API_KEY"
    provider_preference: str = "price"
    embedding_provider_preference: str = "throughput"
    embedding_model: str = ""
    embedding_dimensions: int = 0
    embedding_revision: str = "1"
    timeout: float = 30
    min_confidence: float = 0.7
    min_future_use: float = 0.6
    min_stability: float = 0.55
    activate_threshold: float = 0.55
    temporary_activate_threshold: float = 0.35
    review_threshold: float = 0.35
    archive_threshold: float = 0.1
    permanent_threshold: float = 0.85
    permanent_access_count: int = 20
    reinforcement: float = 0.02
    decay_rates: dict = field(default_factory=lambda: dict(DECAY))
    graph_url: str = "redis://127.0.0.1:6380/0"
    graph_name: str = "gramem"
    graph_password_env: str = "GRAMEM_GRAPH_PASSWORD"
    owner_id: str = "owner"
    aliases: dict = field(default_factory=dict)
    trusted_cli_owner: bool = False
    capture_owner_in_groups: bool = False
    knowledge_auto_archive: bool = True
    chat_auto_archive: bool = True
    knowledge_ocr_languages: str = "chi_sim+eng"
    timezone: str = "UTC"
    auto_approve: bool = True
    confirmation_types: list = field(
        default_factory=lambda: ["identity", "occupation", "current_location", "health"]
    )

    def __post_init__(self):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        if not isinstance(self.timezone, str):
            raise ValueError("invalid timezone")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("invalid timezone") from exc
        for key in (
            "model",
            "base_url",
            "api_key_env",
            "embedding_model",
            "embedding_revision",
            "graph_url",
            "graph_name",
            "graph_password_env",
            "owner_id",
        ):
            if not isinstance(getattr(self, key), str):
                raise ValueError(f"{key} must be a string")
        for key in ("provider_preference", "embedding_provider_preference"):
            if getattr(self, key) not in ("price", "throughput"):
                raise ValueError(f"invalid {key}")
        for key in ("api_key_env", "graph_password_env"):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", getattr(self, key)):
                raise ValueError(f"invalid {key}")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,80}", self.graph_name):
            raise ValueError("invalid graph namespace prefix")
        if not self.owner_id or any(c in self.owner_id for c in ("\x1f", "\x00")):
            raise ValueError("invalid owner identity")
        for key in (
            "trusted_cli_owner",
            "capture_owner_in_groups",
            "graph_recall_enabled",
            "knowledge_auto_archive",
            "chat_auto_archive",
            "auto_approve",
        ):
            if type(getattr(self, key)) is not bool:
                raise ValueError(f"{key} must be boolean")
        if (
            not isinstance(self.knowledge_ocr_languages, str)
            or not re.fullmatch(
                r"[a-z][a-z0-9_]*(?:\+[a-z][a-z0-9_]*)*", self.knowledge_ocr_languages
            )
            or len(self.knowledge_ocr_languages) > 100
        ):
            raise ValueError("invalid OCR languages")
        if not isinstance(self.aliases, dict) or any(
            not isinstance(k, str)
            or not isinstance(v, str)
            or not v
            or any(c in k + v for c in ("\x1f", "\x00"))
            for k, v in self.aliases.items()
        ):
            raise ValueError("invalid identity aliases")
        for key in (
            "recall_tokens",
            "extraction_tokens",
            "extraction_input_tokens",
            "max_items",
            "permanent_access_count",
        ):
            if type(getattr(self, key)) is not int or getattr(self, key) <= 0:
                raise ValueError(f"{key} must be a positive integer")
        for key in ("always_limit", "relevant_limit", "historical_limit", "embedding_dimensions"):
            if type(getattr(self, key)) is not int or getattr(self, key) < 0:
                raise ValueError(f"{key} must be a nonnegative integer")
        for key, maximum in (
            ("graph_recall_hops", 3),
            ("graph_recall_limit", 10),
            ("graph_recall_tokens", 4096),
        ):
            value = getattr(self, key)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"invalid {key}")
        for key in (
            "min_confidence",
            "min_future_use",
            "min_stability",
            "activate_threshold",
            "temporary_activate_threshold",
            "review_threshold",
            "archive_threshold",
            "permanent_threshold",
            "reinforcement",
        ):
            value = getattr(self, key)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"invalid {key}")
        if (
            type(self.timeout) not in (int, float)
            or not math.isfinite(self.timeout)
            or not 0 < self.timeout <= 120
            or not isinstance(self.decay_rates, dict)
            or any(
                not isinstance(k, str)
                or type(v) not in (int, float)
                or not math.isfinite(v)
                or v < 0
                for k, v in self.decay_rates.items()
            )
        ):
            raise ValueError("invalid timeout, owner or decay rates")
        if not isinstance(self.confirmation_types, list) or any(
            not isinstance(v, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", v)
            for v in self.confirmation_types
        ):
            raise ValueError("invalid confirmation types")

    @classmethod
    def load(cls, path: Path):
        raw = json.loads(path.read_text()) if path.exists() else {}
        if not isinstance(raw, dict):
            raise ValueError("configuration must be an object")
        unknown = set(raw) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        return cls(**raw)

    def principal(self, platform: str, user_id: str, *, group: str = ""):
        # Only administrator-written transport aliases can join identities.
        key = f"{platform}:{user_id.casefold() if platform == 'email' else user_id}"
        person = self.aliases.get(key)
        if platform == "cli" and self.trusted_cli_owner:
            person = self.owner_id
        person = person or key
        if group:
            return Principal(self.owner_id, "group", f"{platform}:{group}", person)
        return Principal(
            self.owner_id, "owner" if person == self.owner_id else "contact", person, person
        )


@dataclass(frozen=True)
class Principal:
    owner: str
    scope: str
    subject: str
    actor: str

    def __post_init__(self):
        if any(
            not isinstance(value, str)
            for value in (self.owner, self.scope, self.subject, self.actor)
        ):
            raise ValueError("invalid principal")
        if any(
            "\x1f" in value or "\x00" in value for value in (self.owner, self.subject, self.actor)
        ):
            raise ValueError("invalid principal delimiter")
        if self.scope not in {"owner", "contact", "group"} or not all(
            (self.owner, self.subject, self.actor)
        ):
            raise ValueError("invalid principal")
        if self.scope == "owner" and self.actor != self.owner:
            raise PermissionError("owner memory requires verified owner")

    @property
    def key(self):
        return f"{self.owner}\x1f{self.scope}\x1f{self.subject}"
