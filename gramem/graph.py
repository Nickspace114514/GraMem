"""Independent FalkorDB temporal graph. The local DB holds only a sync outbox.

All graph reads are revalidated against authoritative memory state by Engine.
No graph failure blocks retention, recall or lifecycle transitions.
"""

import hashlib
import os
import re

import redis


def literal(value):
    # Values are strings supplied as Cypher parameters, never identifiers/query fragments.
    return (
        "'"
        + str(value)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        + "'"
    )


class FalkorGraph:
    def __init__(self, config, secret_resolver=os.getenv):
        self.secret_resolver = secret_resolver
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,100}", config.graph_name):
            raise ValueError("invalid graph namespace")
        self.name = config.graph_name
        self.client = redis.Redis.from_url(
            config.graph_url,
            password=secret_resolver(config.graph_password_env) or None,
            socket_connect_timeout=2,
            socket_timeout=3,
            decode_responses=True,
        )

    def _query(self, text, parameters, *, readonly=False):
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) for k in parameters):
            raise ValueError("invalid graph parameter name")
        params = " ".join(k + "=" + literal(v) for k, v in parameters.items())
        command = "GRAPH.RO_QUERY" if readonly else "GRAPH.QUERY"
        return self.client.execute_command(
            command, self.name, "CYPHER " + params + " " + text, "--compact"
        )

    def apply(self, action, payload):
        p = dict(payload)
        if action == "put":
            p["left"] = hashlib.sha256(
                (p["principal"] + "\x1f" + p["subject"]).encode()
            ).hexdigest()
            p["right"] = hashlib.sha256(
                (p["principal"] + "\x1f" + p["object"]).encode()
            ).hexdigest()
            self._query(
                """MERGE (a:Entity {id:$left,scope:$principal}) SET a.name=$subject
            MERGE (b:Entity {id:$right,scope:$principal}) SET b.name=$object
            MERGE (a)-[r:FACT {id:$id}]->(b)
            SET r.memory_id=$memory_id,r.scope=$principal,r.predicate=$predicate,
                r.valid_from=$valid_from,r.valid_until=''""",
                p,
            )
        elif action == "expire":
            self._query(
                "MATCH ()-[r:FACT {memory_id:$memory_id,scope:$principal}]->() SET r.valid_until=$valid_until",
                p,
            )
        elif action == "delete":
            self._query("MATCH ()-[r:FACT {memory_id:$memory_id,scope:$principal}]->() DELETE r", p)
            # Remove unreferenced entity values too. Preserve entities supported by other facts.
            self._query("MATCH (e:Entity {scope:$principal}) WHERE NOT (e)-[:FACT]-() DELETE e", p)
        else:
            raise ValueError("invalid graph action")

    def search(self, principal, query="", *, historical=False, hops=1, limit=50, match_text=False):
        hops = min(3, max(1, int(hops)))
        limit = min(800, max(1, int(limit)))
        if not query.strip():
            # Every entity is a seed; one hop already contains the entire graph.
            hops = 1
        params = {"principal": principal, "query": query.casefold()}
        active = "" if historical else " AND r.valid_until=''"
        path_active = "" if historical else " AND edge.valid_until=''"
        seed_match = (
            "toLower(seed.name)=$query OR (size(seed.name)>=2 AND $query CONTAINS toLower(seed.name))"
            if match_text
            else "toLower(seed.name) CONTAINS $query"
        )
        # Traverse either endpoint but preserve the stored direction in the returned triple.
        # Keep alternative paths until Engine has checked authoritative SQLite exclusions.
        reply = self._query(
            f"""MATCH (seed:Entity {{scope:$principal}})
        WHERE $query='' OR ({seed_match})
        MATCH path=(seed)-[:FACT*0..{hops - 1}]-(a:Entity {{scope:$principal}})-[r:FACT]-(b:Entity {{scope:$principal}})
        WHERE r.scope=$principal{active}
        AND all(edge IN relationships(path) WHERE edge.scope=$principal{path_active})
        AND all(node IN nodes(path) WHERE node.scope=$principal)
        RETURN DISTINCT r.id,r.memory_id,startNode(r).name,r.predicate,endNode(r).name,
        r.valid_from,r.valid_until,[edge IN relationships(path) | edge.memory_id],length(path) AS distance
        ORDER BY distance,r.id LIMIT {limit}""",
            params,
            readonly=True,
        )
        names = (
            "id",
            "memory_id",
            "subject",
            "predicate",
            "object",
            "valid_from",
            "valid_until",
            "path_ids",
            "distance",
        )
        rows = reply[1] if len(reply) > 1 else []

        # FalkorDB compact scalar cells are [type,value].
        def scalar(cell):
            if isinstance(cell, list) and len(cell) == 2 and isinstance(cell[0], int):
                value = cell[1]
                return [scalar(v) for v in value] if isinstance(value, list) else value
            return cell

        return [dict(zip(names, [scalar(cell) for cell in row], strict=True)) for row in rows]

    def health(self):
        return self.client.ping()

    def close(self):
        self.client.close()
