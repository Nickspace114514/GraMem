"""Explicit, idempotent JSON/JSONL import. Never discovers or overwrites live stores."""

import hashlib
import json

from .engine import SECRET, SINGLETONS
from .tokens import compact


def load_records(path):
    text = path.read_text()
    if text.lstrip().startswith("["):
        return _records(json.loads(text))
    if text.lstrip().startswith("{"):
        try:
            raw = json.loads(text)
            return _records(raw.get("items", raw.get("memories", [raw])))
        except json.JSONDecodeError:
            pass
    return _records([json.loads(line) for line in text.splitlines() if line.strip()])


def _records(records):
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        raise ValueError("import requires a list of record objects")
    return records


def import_records(engine, p, records, *, review=True):
    _records(records)
    report = {"imported": 0, "duplicate": 0, "skipped": 0, "quarantined": 0}
    with engine.store.transaction() as db:
        blocked = bool(
            db.execute(
                "SELECT 1 FROM exclusions WHERE principal=? AND state!='active'", (p.key,)
            ).fetchone()
        )
        for r in records:
            content = r.get("content", r.get("text", ""))
            if (
                not isinstance(content, str)
                or not content.strip()
                or len(content) > 2000
                or SECRET.search(content)
                or r.get("status") in {"forgotten", "rejected", "deleted"}
            ):
                report["skipped"] += 1
                continue
            source_id = str(r.get("id") or hashlib.sha256(content.encode()).hexdigest())
            import_key = hashlib.sha256(compact([p.key, source_id, content]).encode()).hexdigest()
            exists = db.execute(
                "SELECT id FROM memories WHERE principal=? AND json_extract(metadata,'$.import_key')=?",
                (p.key, import_key),
            ).fetchone()
            exact = db.execute(
                "SELECT id FROM memories WHERE principal=? AND content=? AND status IN ('active','candidate')",
                (p.key, content),
            ).fetchone()
            if exists or exact:
                report["duplicate"] += 1
                continue
            kind = r.get("type", "knowledge")
            if kind not in {
                "identity",
                "occupation",
                "preference",
                "skill",
                "technical_environment",
                "relationship",
                "project",
                "active_project",
                "project_goal",
                "project_stage",
                "project_state",
                "decision",
                "project_question",
                "project_next_step",
                "project_risk",
                "constraint",
                "current_location",
                "current_activity",
                "current_goal",
                "current_constraint",
                "current_status",
                "episodic",
                "knowledge",
            }:
                kind = "knowledge"
            slot = r.get("slot") or f"import:{source_id}"
            if not isinstance(slot, str) or not slot or len(slot) > 200 or slot == "*":
                raise ValueError("invalid import slot")
            if not engine._allowed(db, p, slot):
                report["skipped"] += 1
                continue
            if blocked:
                # Historical semantic exclusions cannot be matched safely from opaque export IDs.
                report["quarantined"] += 1
                continue
            source = "import:" + import_key
            db.execute(
                "INSERT OR IGNORE INTO sources(id,principal,session,kind,content,created,status) VALUES(?,?,'','import',?,?,'done')",
                (source, p.key, content, engine.clock()),
            )
            meta = r.get("metadata") or r.get("metadata_") or {}
            if isinstance(meta, str):
                meta = json.loads(meta)
            if not isinstance(meta, dict):
                raise ValueError("invalid import metadata")
            meta = {
                k: meta[k]
                for k in ("project_key", "continuity_slot", "relations", "group_safe")
                if k in meta
            }
            meta.update(
                import_key=import_key,
                external_id=source_id,
                external_source_ids=r.get("source_ids", []),
            )
            historical = r.get("status") in {"superseded", "archived"}
            targets = []
            if not review and not historical and kind in SINGLETONS:
                targets = [
                    row[0]
                    for row in db.execute(
                        "SELECT id FROM memories WHERE principal=? AND type=? AND status='active'",
                        (p.key, kind),
                    )
                ]
            id = engine._insert(
                db,
                p,
                content,
                kind,
                slot,
                source=source,
                metadata=meta,
                confirmed=not review,
                review=review,
                targets=targets,
                action="SUPERSEDE" if targets else "ADD",
            )
            if not review and historical:
                engine._invalidate(db, p, id, r["status"])
            report["imported"] += 1
    return report


def import_exclusions(engine, p, records):
    _records(records)
    total = 0
    for r in records:
        slot = r.get("slot") or r.get("key")
        state = r.get("state") or r.get("status")
        if slot and state in {"deleted", "suppressed"}:
            engine.exclude(p, slot, state=state)
            total += 1
    return total
