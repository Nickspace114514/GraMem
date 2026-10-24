"""Authenticated, profile-scoped GraMem administration via Hermes dashboard."""

import hashlib
import json
import math
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr

router = APIRouter()
_lock = threading.RLock()


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Settings(StrictBody):
    values: dict
    revision: str


class Credential(StrictBody):
    kind: str
    value: SecretStr


class ModelSettings(StrictBody):
    model: str = Field(max_length=200)
    embedding_model: str = Field(max_length=200)
    embedding_dimensions: int = Field(ge=0, strict=True)
    embedding_revision: str = Field(min_length=1, max_length=100)
    timeout: float = Field(gt=0, le=120, allow_inf_nan=False)
    revision: str


class Operation(StrictBody):
    action: str
    scope: str = ""
    id: str = ""
    slot: str = ""
    content: str = Field(default="", max_length=2000)
    type: str = "knowledge"
    targets: list[str] = Field(default_factory=list, max_length=200)
    relations: list[dict[str, str]] = Field(default_factory=list, max_length=50)
    confirmed: bool = True
    authorization: bool = False


class ImportData(StrictBody):
    records: list[dict] = Field(max_length=10000)
    exclusions: list[dict] = Field(default_factory=list, max_length=10000)
    activate: bool = False
    scope: str = ""


class Document(StrictBody):
    filename: str = Field(max_length=200)
    data: str = Field(max_length=28000000)
    scope: str = ""
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=2000)


class KnowledgeControl(StrictBody):
    id: str
    action: str
    scope: str = ""


class ChatProcessing(StrictBody):
    scope: str = ""


def knowledge(e):
    from plugins.memory import import_provider_module

    return import_provider_module("gramem", "gramem.knowledge").Knowledge(e)


def home():
    from hermes_constants import get_hermes_home

    return get_hermes_home().resolve()


def digest(path):
    return hashlib.sha256(path.read_bytes() if path.exists() else b"").hexdigest()


def atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".control-")
    try:
        with os.fdopen(fd, "w") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def snapshot(path):
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = home() / "backups" / "hermes-control" / (stamp + "-" + path.name)
        atomic(destination, path.read_text())


@contextmanager
def engine(scope=""):
    from plugins.memory import import_provider_module

    # Resolve the installed provider instead of importing a different pip copy.
    Config = import_provider_module("gramem", "gramem.config").Config
    Engine = import_provider_module("gramem", "gramem.engine").Engine
    Model = import_provider_module("gramem", "gramem.model").Model
    FalkorGraph = import_provider_module("gramem", "gramem.graph").FalkorGraph
    from agent.secret_scope import get_secret

    cfg_path = home() / "gramem" / "config.json"
    if not cfg_path.exists():
        raise HTTPException(409, "该 profile 尚未配置 GraMem")
    cfg = Config.load(cfg_path)
    cfg.graph_name += "_" + hashlib.sha256(str(home()).encode()).hexdigest()[:12]
    e = Engine(
        home() / "gramem" / "memory.sqlite",
        cfg,
        Model(cfg, secret_resolver=get_secret),
        FalkorGraph(cfg, secret_resolver=get_secret),
    )
    try:
        Principal = import_provider_module("gramem", "gramem.config").Principal
        p = Principal(cfg.owner_id, "owner", cfg.owner_id, cfg.owner_id)
        if scope and scope != p.key:
            # Only existing identities can be selected by this administrator surface.
            exists = e.store.rows(
                "SELECT principal FROM memories WHERE principal=? UNION SELECT principal FROM exclusions WHERE principal=? UNION SELECT principal FROM knowledge_documents WHERE principal=? UNION SELECT principal FROM chat_turns WHERE principal=?",
                (scope, scope, scope, scope),
            )
            if not exists:
                raise HTTPException(404, "身份不存在")
            parts = scope.split("\x1f")
            if len(parts) != 3 or parts[0] != cfg.owner_id:
                raise HTTPException(403, "身份不属于当前 profile")
            p = Principal(
                parts[0], parts[1], parts[2], cfg.owner_id if parts[1] == "group" else parts[2]
            )
        yield e, p
    except (ValueError, KeyError, PermissionError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    finally:
        e.close()


@router.get("/overview")
def overview():
    with engine() as (e, p):
        scopes = e.store.rows(
            "SELECT principal,sum(count) count FROM (SELECT principal,count(*) count FROM memories GROUP BY principal UNION ALL SELECT principal,0 count FROM knowledge_documents GROUP BY principal UNION ALL SELECT principal,0 count FROM chat_turns GROUP BY principal) GROUP BY principal"
        )
        if p.key not in [x["principal"] for x in scopes]:
            scopes.insert(0, {"principal": p.key, "count": 0})
        return {
            "home": str(home()),
            "owner": p.key,
            "scopes": scopes,
            "status": e.status(),
            "usage_note": "这里的模型计数属于当前管理请求；后台宿主模型累计用量不在此请求计数中。",
        }


@router.get("/settings")
def settings():
    from plugins.memory import import_provider_module

    path = home() / "gramem" / "config.json"
    if not path.exists():
        raise HTTPException(409, "该 profile 尚未配置 GraMem")
    cfg = import_provider_module("gramem", "gramem.config").Config.load(path)
    return {"values": asdict(cfg), "revision": digest(path)}


@router.put("/settings")
def save_settings(body: Settings):
    from plugins.memory import import_provider_module

    Config = import_provider_module("gramem", "gramem.config").Config
    try:
        defaults = asdict(Config())
        for key, value in body.values.items():
            if key not in defaults:
                raise ValueError(f"unknown config key: {key}")
            expected = Config.__annotations__[key]
            if expected is int and (type(value) is not int):
                raise ValueError(f"{key} must be an integer")
            if expected is float and (type(value) not in (int, float) or not math.isfinite(value)):
                raise ValueError(f"{key} must be a finite number")
            if expected in (str, bool, dict, list) and type(value) is not expected:
                raise ValueError(f"invalid type for {key}")
        validated = Config(**body.values)
        if validated.permanent_access_count <= 0:
            raise ValueError("permanent_access_count must be positive")
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in validated.aliases.items()):
            raise ValueError("aliases must map strings to strings")
        normalized_aliases = {}
        for key, target in validated.aliases.items():
            platform, separator, account = key.partition(":")
            if not separator or not re.fullmatch(r"[a-z][a-z0-9_-]*", platform) or not account.strip():
                raise ValueError("账号关联需要有效的平台和账号 ID")
            if account != account.strip() or target != target.strip():
                raise ValueError("账号和共用身份的前后不能有空格")
            if platform == "telegram" and not re.fullmatch(r"[1-9][0-9]*", account):
                raise ValueError("Telegram 身份关联请使用正整数用户 ID，不能使用 @用户名或群组 ID")
            if platform == "email":
                if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", account):
                    raise ValueError("邮件身份关联需要完整邮箱地址")
                key = platform + ":" + account.casefold()
            if key in normalized_aliases:
                raise ValueError("同一个账号不能重复关联；邮箱大小写视为同一账号")
            normalized_aliases[key] = target
        validated.aliases = normalized_aliases
        if not all(isinstance(v, str) for v in validated.confirmation_types):
            raise ValueError("confirmation_types must contain strings")
        if not all(
            isinstance(k, str) and type(v) in (int, float) and math.isfinite(v)
            for k, v in validated.decay_rates.items()
        ):
            raise ValueError("decay_rates must map names to finite numbers")
        for name in (validated.api_key_env, validated.graph_password_env):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ValueError("invalid credential environment name")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,80}", validated.graph_name):
            raise ValueError("invalid graph namespace prefix")
        if any(c in validated.owner_id for c in ("\x1f", "\x00")):
            raise ValueError("invalid owner identity")
        # Reject NaN/Infinity and malformed nested values before touching disk.
        text = json.dumps(asdict(validated), ensure_ascii=False, indent=2, allow_nan=False)
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    with _lock:
        path = home() / "gramem" / "config.json"
        if body.revision != digest(path):
            raise HTTPException(409, "配置已被其他操作修改，请重新加载")
        snapshot(path)
        atomic(path, text + "\n")
    return {"ok": True, "restart_required": True, "revision": digest(path)}


@router.get("/credentials")
def credentials():
    from agent.secret_scope import get_secret
    from plugins.memory import import_provider_module

    cfg = import_provider_module("gramem", "gramem.config").Config.load(
        home() / "gramem" / "config.json"
    )
    return {
        kind: {"env": key, "is_set": bool(get_secret(key))}
        for kind, key in (("model", cfg.api_key_env), ("graph", cfg.graph_password_env))
    }


@router.get("/models")
def models():
    from plugins.memory import import_provider_module

    path = home() / "gramem" / "config.json"
    if not path.exists():
        raise HTTPException(409, "该 profile 尚未配置 GraMem")
    with _lock:
        cfg = import_provider_module("gramem", "gramem.config").Config.load(path)
        revision = digest(path)
    return {
        "provider": "alibaba",
        "base_url": cfg.base_url,
        "api_key_env": cfg.api_key_env,
        "timeout": cfg.timeout,
        "revision": revision,
        "chat": {"model": cfg.model, "role": "提取、分类、画像与聊天整理"},
        "embedding": {
            "model": cfg.embedding_model,
            "dimensions": cfg.embedding_dimensions,
            "revision": cfg.embedding_revision,
            "role": "语义检索与知识库向量",
        },
        "catalog": [
            {"id": "qwen3.8-flash", "name": "Qwen3.8 Flash", "kind": "chat"},
            {"id": "qwen3.5-plus", "name": "Qwen3.5 Plus", "kind": "chat"},
            {"id": "qwen3.5-flash", "name": "Qwen3.5 Flash", "kind": "chat"},
            {"id": "text-embedding-v4", "name": "Text Embedding V4", "kind": "embedding"},
            {"id": "qwen3.7-text-embedding", "name": "Qwen3.7 Text Embedding", "kind": "embedding"},
            {"id": "qwen3.7-text-embedding-flash", "name": "Qwen3.7 Text Embedding Flash", "kind": "embedding"},
        ],
    }


@router.put("/models")
def save_models(body: ModelSettings):
    from plugins.memory import import_provider_module

    Config = import_provider_module("gramem", "gramem.config").Config
    with _lock:
        path = home() / "gramem" / "config.json"
        if not path.exists():
            raise HTTPException(409, "该 profile 尚未配置 GraMem")
        if body.revision != digest(path):
            raise HTTPException(409, "配置已被其他操作修改，请重新加载")
        try:
            current = asdict(Config.load(path))
            updates = body.model_dump(exclude={"revision"})
            for key in ("model", "embedding_model"):
                value = updates[key].strip()
                if value and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", value):
                    raise ValueError("请填写阿里官方模型 ID，不含 OpenRouter 的供应商前缀")
                updates[key] = value
            if any(updates[k] != current[k] for k in ("embedding_model", "embedding_dimensions")):
                if updates["embedding_revision"] == current["embedding_revision"]:
                    updates["embedding_revision"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            current.update(updates)
            current.update(base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                           api_key_env="DASHSCOPE_API_KEY")
            validated = Config(**current)
            text = json.dumps(asdict(validated), ensure_ascii=False, indent=2, allow_nan=False)
        except (TypeError, ValueError, AttributeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        snapshot(path)
        atomic(path, text + "\n")
        revision = digest(path)
    return {"ok": True, "restart_required": True, "revision": revision}


@router.put("/credentials")
def save_credential(body: Credential):
    from hermes_cli.config import save_env_value
    from plugins.memory import import_provider_module

    cfg = import_provider_module("gramem", "gramem.config").Config.load(
        home() / "gramem" / "config.json"
    )
    keys = {"model": cfg.api_key_env, "graph": cfg.graph_password_env}
    if body.kind not in keys or not body.value.get_secret_value().strip():
        raise HTTPException(400, "请选择 GraMem 凭据并输入非空值")
    try:
        save_env_value(keys[body.kind], body.value.get_secret_value().strip())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "restart_required": True}


@router.get("/memories")
def memories(
    scope: str = "",
    q: str = Query("", max_length=2000),
    status: str = "active",
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
):
    if status not in {"active", "candidate", "superseded", "archived", "rejected", "forgotten"}:
        raise HTTPException(400, "无效状态")
    with engine(scope) as (e, p):
        # Page the complete SQL result; never silently inherit Engine.list's 200-row cap.
        clause = """m.principal=? AND m.status=? AND
          NOT EXISTS (SELECT 1 FROM exclusions x WHERE x.principal=m.principal
          AND (x.slot=m.slot OR x.slot='*') AND x.state IN ('deleted','suppressed'))"""
        args = [p.key, status]
        # Include descendants so pagination cannot expose suppressed merge conclusions.
        prefix = """WITH RECURSIVE blocked(id) AS (
          SELECT m.id FROM memories m JOIN exclusions x ON x.principal=m.principal
          AND x.slot IN (m.slot,'*') WHERE m.principal=? AND x.state!='active'
          UNION SELECT k.memory_id FROM knowledge_chunks k JOIN knowledge_documents d ON d.id=k.document_id
          WHERE d.principal=? AND (d.status IN ('redacted','blocked') OR EXISTS
          (SELECT 1 FROM exclusions x WHERE x.principal=d.principal AND x.slot IN ('document:'||d.id,'*') AND x.state!='active') OR EXISTS
          (SELECT 1 FROM knowledge_chunks c JOIN memories m ON m.id=c.memory_id JOIN exclusions x ON x.principal=m.principal AND x.slot IN (m.slot,'*') WHERE c.document_id=d.id AND x.state!='active'))
          UNION SELECT m.id FROM memories m WHERE m.principal=? AND EXISTS (
            SELECT 1 FROM chat_turns c JOIN json_each(c.source_ids) j
            WHERE c.principal=m.principal AND (j.value=m.source OR EXISTS (
              SELECT 1 FROM json_each(m.metadata,'$.source_ids') s WHERE s.value=j.value))
            AND (c.status!='ready' OR c.policy_epoch!=(
              SELECT coalesce(sum(epoch),0) FROM exclusions WHERE principal=m.principal)
              OR EXISTS (SELECT 1 FROM chat_native_state n WHERE n.turn_id=c.id AND n.active=0)))
          UNION SELECT m.id FROM memories m JOIN json_each(m.metadata,'$.targets') j
          JOIN blocked b ON b.id=j.value WHERE m.principal=?
        ) """
        clause += " AND m.id NOT IN (SELECT id FROM blocked)"
        args = [p.key, p.key, p.key, p.key, *args]
        if status == "active":
            clause += " AND m.valid_until IS NULL"
        if q:
            clause += " AND (instr(lower(m.content),lower(?))>0 OR instr(lower(m.slot),lower(?))>0 OR instr(lower(m.type),lower(?))>0 OR m.id=?)"
            args += [q, q, q, q]
        # Heavy recursive read: never hold the write lock other processes need.
        with e.store.read() as db:
            total = db.execute(
                prefix + "SELECT count(*) FROM memories m WHERE " + clause, args
            ).fetchone()[0]
            rows = [
                dict(r)
                for r in db.execute(
                    prefix
                    + "SELECT m.* FROM memories m WHERE "
                    + clause
                    + " ORDER BY m.updated DESC,m.id LIMIT ? OFFSET ?",
                    args + [size, (page - 1) * size],
                )
            ]
        for row in rows:
            row.pop("embedding", None)
            row["metadata"] = json.loads(row["metadata"])
        return {"items": rows, "total": total, "page": page, "size": size}


@router.get("/recall")
def recall(
    q: str = Query(min_length=1, max_length=2000), scope: str = "", historical: bool = False
):
    with engine(scope) as (e, p):
        result = e.recall(p, q, historical=historical)
        for row in result.get("memories", []):
            row.pop("embedding", None)
        return result


@router.get("/graph")
def graph(
    q: str = Query("", max_length=2000),
    scope: str = "",
    hops: int = Query(1, ge=1, le=3),
    historical: bool = False,
    limit: int = Query(150, ge=1, le=199),
):
    with engine(scope) as (e, p):
        # Engine.graph deliberately returns [] on backend failure; health must be checked separately.
        try:
            e.graph_backend.client.ping()
            healthy = True
        except Exception:
            healthy = False
        items = e.graph(p, q, hops=hops, historical=historical, limit_items=limit + 1)
        return {"items": items[:limit], "truncated": len(items) > limit, "healthy": healthy}


@router.get("/profile")
def profile(scope: str = ""):
    with engine(scope) as (e, p):
        return {"profile": e.profile(p), "exclusions": e.exclusions(p)}


@router.get("/queues")
def queues():
    with engine() as (e, _):
        return {
            "sources": e.store.rows(
                "SELECT id,principal,kind,status,attempts,retry_at,created FROM sources ORDER BY created DESC LIMIT 100"
            ),
            "graph": e.store.rows(
                "SELECT id,memory_id,principal,action,attempts,retry_at FROM graph_outbox ORDER BY id LIMIT 100"
            ),
        }


@router.post("/operation")
def operation(body: Operation):
    with engine(body.scope) as (e, p):

        def remember():
            metadata = {"relations": body.relations, "group_safe": p.scope == "group"}
            return {
                "id": e.remember(
                    p,
                    body.content,
                    kind=body.type,
                    slot=body.slot,
                    targets=body.targets,
                    action={"remember": "ADD", "update": "UPDATE", "merge": "MERGE"}[body.action],
                    metadata=metadata,
                    confirmed=body.confirmed,
                )
            }

        def confirm():
            e.confirm(p, body.id, reject=body.action == "reject")
            return {"ok": True}

        def exclude():
            slot = body.slot or e.get(p, body.id)["slot"]
            if not body.authorization:
                raise HTTPException(400, "需要确认遗忘或停用范围")
            return e.exclude(p, slot, state="deleted" if body.action == "forget" else "suppressed")

        def reactivate():
            if body.action == "reauthorize" and not body.authorization:
                raise HTTPException(400, "需要明确授权重新记住新事实")
            return e.reactivate(p, body.slot, reauthorize=body.action == "reauthorize")

        def reflect():
            from plugins.memory import import_provider_module

            reflection = import_provider_module("gramem", "gramem.reflection")
            return reflection.reflect(e, p)

        def consolidate():
            from plugins.memory import import_provider_module

            reflection = import_provider_module("gramem", "gramem.reflection")
            return {
                "consolidated": reflection.consolidate(e, p),
                "profile": reflection.reflect(e, p),
            }

        def maintain():
            return {"lifecycle_changes": e.maintain(), "graph_synced": e.flush_graph()}

        def worker():
            # Process just one durable job; never start a competing permanent worker.
            return {
                "knowledge_processed": knowledge(e).process_one(),
                "embedding_processed": knowledge(e).embed_one(),
                "processed": e.process_one(),
                "review_processed": e.review_one(),
                "graph_synced": e.flush_graph(limit_jobs=10),
            }

        def backup():
            destination = (
                home()
                / "backups"
                / "hermes-control"
                / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-knowledge.zip")
            )
            return knowledge(e).backup(destination)

        handlers = {
            "remember": remember,
            "update": remember,
            "merge": remember,
            "confirm": confirm,
            "reject": confirm,
            "forget": exclude,
            "suppress": exclude,
            "reactivate": reactivate,
            "reauthorize": reactivate,
            "reflect": reflect,
            "consolidate": consolidate,
            "maintain": maintain,
            "worker": worker,
            "sync_graph": lambda: {"graph_synced": e.flush_graph()},
            "backup": backup,
        }
        if body.action not in handlers:
            raise HTTPException(400, "未知管理操作")
        return handlers[body.action]()


@router.post("/import")
def import_data(body: ImportData):
    from plugins.memory import import_provider_module

    migrate = import_provider_module("gramem", "gramem.migrate")
    with engine(body.scope) as (e, p):
        migrate.import_exclusions(e, p, body.exclusions)
        return migrate.import_records(e, p, body.records, review=not body.activate)


@router.post("/document")
@router.post("/knowledge/upload")
def document(body: Document):
    import base64

    try:
        data = base64.b64decode(body.data, validate=True)
    except ValueError as exc:
        raise HTTPException(400, "文件编码错误") from exc
    if len(data) > 20_000_000:
        raise HTTPException(413, "文件最大 20 MB")
    with engine(body.scope) as (e, p):
        return knowledge(e).ingest(
            p,
            data=data,
            filename=body.filename,
            title=body.title,
            description=body.description,
            defer=True,
        )


@router.get("/knowledge")
def knowledge_list(
    scope: str = "",
    q: str = Query("", max_length=2000),
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
    historical: bool = False,
):
    with engine(scope) as (e, p):
        return knowledge(e).list(p, query=q, page=page, size=size, historical=historical)


@router.get("/knowledge/search")
def knowledge_search(
    q: str = Query(min_length=1, max_length=2000), scope: str = "", historical: bool = False
):
    with engine(scope) as (e, p):
        return knowledge(e).search(p, q, historical=historical)


@router.get("/knowledge/{id}/original")
def knowledge_original(id: str, scope: str = ""):
    from urllib.parse import quote

    with engine(scope) as (e, p):
        info, data = knowledge(e).original(p, id)
    return Response(
        data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(info["name"], safe=""),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.get("/knowledge/{id}")
def knowledge_read(id: str, scope: str = "", start: int = Query(0, ge=0)):
    with engine(scope) as (e, p):
        return knowledge(e).read(p, id, start=start)


@router.post("/knowledge/control")
def knowledge_control(body: KnowledgeControl):
    with engine(body.scope) as (e, p):
        kb = knowledge(e)
        if body.action == "retry":
            return kb.retry(p, body.id)
        if body.action == "reactivate":
            return e.reactivate(p, "document:" + body.id)
        if body.action not in {"forget", "suppress"}:
            raise HTTPException(400, "未知知识库操作")
        kb.get(p, body.id)
        return e.exclude(
            p, "document:" + body.id, state="deleted" if body.action == "forget" else "suppressed"
        )


def chats(e):
    from plugins.memory import import_provider_module

    return import_provider_module('gramem', 'gramem.chats').Chats(e)


def chat_backfill(e):
    from plugins.memory import import_provider_module

    return import_provider_module('gramem', 'gramem.chat_backfill').Backfill(e)


@router.get('/chats/process')
def chats_processing_status(scope: str = ''):
    with engine(scope) as (e, p):
        return chat_backfill(e).status(p)


@router.post('/chats/process')
def chats_process_all(body: ChatProcessing):
    with engine(body.scope) as (e, p):
        return chat_backfill(e).request(p)


@router.post('/chats/process/retry')
def chats_processing_retry(body: ChatProcessing):
    with engine(body.scope) as (e, p):
        return chat_backfill(e).retry(p)


@router.get('/chats/overview')
def chats_overview(scope: str = '', platform: str = '', session: str = '',
                   after: float | None = None, before: float | None = None):
    with engine(scope) as (e, p):
        return chats(e).overview(p, platform=platform, session=session, after=after, before=before)


@router.get('/chats')
def chats_search(q: str = '', scope: str = '', platform: str = '', session: str = '',
                 after: float | None = None, before: float | None = None,
                 start: int = Query(0, ge=0), size: int = Query(20, ge=1, le=100)):
    with engine(scope) as (e, p):
        return chats(e).search(p, q, platform=platform, session=session, after=after, before=before,
                               start=start, size=size)


@router.get('/chats/{id}/original')
def chat_original(id: str, scope: str = ''):
    with engine(scope) as (e, p):
        info, data = chats(e).original(p, id)
        return Response(data, media_type='application/json', headers={
            'Content-Disposition': 'attachment; filename="' + info['name'] + '"',
            'X-Content-SHA256': info['sha256'], 'Cache-Control': 'no-store',
        })


@router.get('/chats/{id}/bundle')
def chat_original_bundle(id: str, scope: str = ''):
    from plugins.memory import import_provider_module

    with engine(scope) as (e, p):
        info, data = import_provider_module('gramem', 'gramem.chat_audio').ChatAudio(e).bundle(p, id)
        return Response(data, media_type='application/zip', headers={
            'Content-Disposition': 'attachment; filename="' + info['name'] + '"',
            'X-Content-SHA256': info['sha256'], 'Cache-Control': 'no-store'})


@router.get('/chats/{id}/audio/{audio_id}/original')
def chat_audio_original(id: str, audio_id: str, scope: str = ''):
    from plugins.memory import import_provider_module

    with engine(scope) as (e, p):
        info, data = import_provider_module('gramem', 'gramem.chat_audio').ChatAudio(e).original(p, id, audio_id)
        return Response(data, media_type=info['mime'], headers={
            'Content-Disposition': 'inline; filename="' + info['name'] + '"',
            'X-Content-SHA256': info['sha256'], 'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff'})


@router.get('/chats/{id}')
def chat_read(id: str, scope: str = ''):
    with engine(scope) as (e, p):
        return chats(e).read(p, id)


@router.get('/network')
def memory_net(scope: str = '', q: str = '', id: str = '',
                      hops: int = Query(2, ge=1, le=3), historical: bool = False):
    from plugins.memory import import_provider_module

    with engine(scope) as (e, p):
        return import_provider_module('gramem', 'gramem.network').Network(e).query(
            p, q, id=id, hops=hops, maximum=80, historical=historical)
