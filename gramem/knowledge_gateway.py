"""Archive real, authorized owner attachments through Hermes' native inbound hook."""

import asyncio
import logging
import re
from pathlib import Path

from .config import Config, is_shared_chat
from .engine import Engine
from .knowledge import SUFFIXES, Knowledge

logger = logging.getLogger(__name__)


async def archive_inbound(event=None, gateway=None, **kwargs):
    source = getattr(event, "source", None)
    media = getattr(event, "media_urls", None) or []
    if (
        not source
        or not media
        or getattr(source, "is_bot", False)
        or not getattr(source, "user_id", None)
    ):
        return
    # This hook precedes native authorization. Use the SAME native check before any read/write.
    authorize = getattr(gateway, "_is_user_authorized_for_source", None)
    resolve = getattr(gateway, "_resolve_profile_home_for_source", None)
    if not callable(authorize) or not callable(resolve) or not authorize(source):
        return
    if getattr(source, "profile_route_rejected", False):
        return
    home = Path(resolve(source)).resolve()
    cfg_path = home / "gramem" / "config.json"
    if not cfg_path.is_file():
        return
    cfg = Config.load(cfg_path)
    platform = getattr(getattr(source, "platform", None), "value", "")
    p = cfg.principal(platform, str(source.user_id))
    if not cfg.knowledge_auto_archive or p.scope != "owner":
        return
    if (
        is_shared_chat(getattr(source, "chat_type", "dm"))
        and not cfg.capture_owner_in_groups
    ):
        return
    text = str(getattr(event, "text", "") or "")
    if re.search(
        r"忘记|遗忘|不要.*(?:保存|留存|记住)|仅.*(?:这次|本次)|forget|do not (?:save|store)|don't (?:save|store)",
        text,
        re.I,
    ):
        return
    # The adapter's cache may belong to the transport profile before runtime rehoming.
    from hermes_constants import get_hermes_home

    transport_home = Path(get_hermes_home()).resolve()
    homes = {home, transport_home}
    roots = [
        h / d
        for h in homes
        for d in ("cache/images", "cache/documents", "image_cache", "document_cache")
    ]
    files = []
    for raw in media:
        if not isinstance(raw, str) or "://" in raw:
            continue
        path = Path(raw).resolve()
        if (
            path.suffix.lower() not in SUFFIXES
            or not path.is_file()
            or not any(root.resolve() in path.parents for root in roots)
        ):
            continue
        # Hermes document cache prefixes names with doc_<uuid12>_.
        name = re.sub(r"^doc_[a-f0-9]{12}_", "", path.name)
        files.append((path, name))
    if not files:
        return

    def save():
        engine = Engine(home / "gramem" / "memory.sqlite", cfg)
        try:
            library = Knowledge(engine)
            for path, name in files[:20]:
                try:
                    library.ingest(
                        p,
                        path,
                        filename=name,
                        description=text[:2000],
                        origin={
                            "platform": platform,
                            "chat_id": str(source.chat_id),
                            "message_id": str(getattr(event, "message_id", "") or ""),
                        },
                        defer=True,
                    )
                except (ValueError, PermissionError, OSError):
                    logger.info(
                        "GraMem attachment archive skipped: invalid file or memory controls"
                    )
        finally:
            engine.close()

    # I/O is off the gateway event loop; no model call and no outbound message.
    await asyncio.to_thread(save)
