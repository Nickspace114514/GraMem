"""Memory net: scoped records, events and weights projected from authoritative storage."""

import hashlib
import json
import uuid
from collections import deque
from dataclasses import replace

from .chat_audio import ChatAudio
from .chats import Chats
from .config import Principal
from .engine import strength
from .graph import FalkorGraph
from .knowledge import Knowledge
from .tokens import compact, limit


class Network:
    FORMAT = 3
    REFRESH_SECONDS = 60

    def __init__(self, engine):
        self.e = engine

    def snapshot(self, p, *, historical=False):
        nodes, edges = {}, {}
        now = self.e.clock()

        def node(kind, ref, label, **extra):
            id = kind + ':' + ref
            nodes[id] = {'id': id, 'kind': kind, 'ref': ref, 'label': limit(label, 100), **extra}
            return id

        def edge(left, right, relation):
            id = hashlib.sha256(compact([p.key, left, right, relation]).encode()).hexdigest()
            edges[id] = {'id': id, 'source': left, 'target': right, 'relation': relation}

        library, chats = Knowledge(self.e), Chats(self.e)
        with self.e.store.transaction() as db:
            epoch = self.e._epoch(db, p)
            all_memories = db.execute('SELECT * FROM memories WHERE principal=? ORDER BY updated DESC LIMIT 5000', (p.key,)).fetchall()
            usable = [r for r in all_memories if r['status'] in
                      ({'active','superseded','archived','candidate','rejected'} if historical else {'active'})
                      and (historical or r['valid_until'] is None) and self.e._fact_allowed(db, p, r)]
            source_to_turn = {}
            if p.scope != 'group':
                turns = chats._rows(db, p)
                for r in turns:
                    tid = node('chat', r['id'], r['user_text'] or r['assistant_text'],
                               session=r['session'], platform=r['platform'], context=r['context'],
                               created=r['created'], status=r['status'])
                    cid = node('context', r['session'], r['platform'] + ' · ' + r['session'],
                               session=r['session'], platform=r['platform'])
                    edge(cid, tid, 'CONTAINS')
                    for a in ChatAudio(self.e).info(db, r['id']):
                        aid = node('audio', a['id'], '助手语音 · ' + a['name'],
                                   created=r['created'], status=a['state'], role='assistant',
                                   chat_id=r['id'], mime=a['mime'], sha256=a['sha256'], size=a['size'],
                                   transcript_basis=a['transcript_basis'])
                        edge(tid, aid, 'HAS_AUDIO')
                    for source in json.loads(r['source_ids']):
                        source_to_turn[source] = tid
                for s in db.execute('SELECT * FROM chat_summaries WHERE principal=? AND policy_epoch=?', (p.key, epoch)):
                    items = [i for i in json.loads(s['content']) if 'chat:' + i['turn_id'] in nodes]
                    if not items:
                        continue
                    sid = node('summary', s['id'], '；'.join(i['text'] for i in items),
                               session=s['session'], created=s['created'])
                    for item in items:
                        edge(sid, 'chat:' + item['turn_id'], 'SUPPORTED_BY')
                        topic = item['topic'].strip()
                        topic_id = hashlib.sha256(topic.casefold().encode()).hexdigest()[:24]
                        topic_node = node('topic', topic_id, topic)
                        edge(sid, topic_node, 'ABOUT')
                        edge('chat:' + item['turn_id'], topic_node, 'ABOUT')
                        for name in item.get('entities', []):
                            entity = node('entity', hashlib.sha256(name.casefold().encode()).hexdigest()[:24], name)
                            edge(sid, entity, 'MENTIONS')
                            edge('chat:' + item['turn_id'], entity, 'MENTIONS')
            documents = db.execute('SELECT * FROM knowledge_documents WHERE principal=? ORDER BY created DESC LIMIT 1000', (p.key,)).fetchall()
            for d in documents:
                if library._allowed(db, p, d) and (historical or d['status'] != 'superseded'):
                    node('document', d['id'], d['title'] or d['name'], version=d['version'],
                         created=d['created'], updated=d['updated'], status=d['status'])
            for r in usable:
                mid = node('memory', r['id'], r['content'], type=r['type'], slot=r['slot'],
                           memory_class=r['class'], confidence=r['confidence'], strength=r['strength'],
                           effective_strength=strength(r, now), importance=r['importance'],
                           decay=r['decay'], status=r['status'], lifecycle=r['lifecycle'],
                           created=r['created'], updated=r['updated'], maintained=r['maintained'],
                           valid_from=r['valid_from'], valid_until=r['valid_until'],
                           accesses=r['accesses'], version=r['version'], weight_basis='memory')
                meta = json.loads(r['metadata'])
                for source in [r['source'], *meta.get('source_ids', [])]:
                    if source in source_to_turn:
                        edge(mid, source_to_turn[source], 'SUPPORTED_BY')
                for link in db.execute('SELECT document_id FROM knowledge_chunks WHERE memory_id=?', (r['id'],)):
                    did = 'document:' + link[0]
                    if did in nodes:
                        edge(did, mid, 'CONTAINS')
                # Entities from evidence-backed existing relations connect the two graphs.
                for rel in meta.get('relations', []):
                    for name in [rel.get('subject', ''), rel.get('object', '')]:
                        if name:
                            entity = node('entity', hashlib.sha256(name.casefold().encode()).hexdigest()[:24], name)
                            edge(mid, entity, 'MENTIONS')
            for r in usable:
                for target in json.loads(r['metadata']).get('targets', []):
                    if 'memory:' + target in nodes:
                        edge('memory:' + r['id'], 'memory:' + target, 'DERIVED_FROM')
            # Audit events refer only to visible memories. Never expose arbitrary event detail,
            # exclusion controls, erased content, or missing/foreign memory references.
            audit = db.execute('SELECT * FROM events WHERE principal=? AND memory_id IS NOT NULL ORDER BY at DESC,id DESC LIMIT 5000', (p.key,)).fetchall()
            actions = {'ADD':'记住', 'UPDATE':'更新', 'MERGE':'合并', 'RETRIEVE':'回想',
                       'LIFECYCLE':'生命周期变化', 'CONFIRM':'确认', 'REJECT':'拒绝',
                       'AUTO_APPROVE':'自动批准', 'AUTO_REJECT':'自动拒绝', 'ENRICH':'补充',
                       'IGNORE':'重复记录', 'review':'等待审核', 'auto_review':'自动审核',
                       'awaiting_confirm':'等待确认', 'archived':'归档'}
            for r in audit:
                mid = 'memory:' + r['memory_id']
                if mid in nodes:
                    eid = node('event', str(r['id']), actions.get(r['action'], r['action']) + ' · ' + nodes[mid]['label'],
                               action=r['action'], created=r['at'], memory_id=r['memory_id'])
                    edge(eid, mid, 'RECORDED_FOR')
            topics = [n for n in nodes.values() if n['kind'] in {'topic', 'entity'}]
            # Literal shared names are associations, never inferred factual relations.
            for n in list(nodes.values()):
                if n['kind'] not in {'memory', 'document'}:
                    continue
                for t in topics:
                    if len(t['label']) >= 2 and t['label'].casefold() in n['label'].casefold():
                        edge(n['id'], t['id'], 'MENTIONS')
            # NEXT describes recorded time order only, never a causal or factual claim.
            timeline = sorted((n for n in nodes.values() if n['kind'] in {'chat','document','event'}),
                              key=lambda n: (n['created'], n['id']))
            for left, right in zip(timeline, timeline[1:], strict=False):
                edge(left['id'], right['id'], 'NEXT')
            self._weights(nodes, edges)
            revision = compact([self.FORMAT, db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0], epoch, historical, int(now // self.REFRESH_SECONDS)])
        return {'nodes': list(nodes.values()), 'edges': list(edges.values()), 'revision': revision,
                'as_of': now, 'historical': historical,
                'truncated': len(all_memories) == 5000 or len(audit) == 5000 or len(documents) == 1000}

    @staticmethod
    def _weights(nodes, edges):
        """Aggregate unique backing memories along typed provenance; ignore time/name bridges.

        Metrics on records describe their associated memories, not the truth of every utterance.
        Unassessed records have null metrics and an explicit basis, never invented confidence.
        """
        support = {id: ({id} if n['kind'] == 'memory' else set()) for id, n in nodes.items()}
        transfers = []
        for e in edges.values():
            left, right = nodes[e['source']], nodes[e['target']]
            left['connection_count'] = left.get('connection_count', 0) + 1
            right['connection_count'] = right.get('connection_count', 0) + 1
            if e['relation'] == 'SUPPORTED_BY':
                if left['kind'] == 'memory' and right['kind'] == 'chat':
                    transfers.append((left['id'], right['id']))
                elif left['kind'] == 'summary' and right['kind'] == 'chat':
                    transfers.append((right['id'], left['id']))
            elif e['relation'] == 'CONTAINS' and left['kind'] in {'document','context'}:
                transfers.append((right['id'], left['id']))
            elif e['relation'] in {'ABOUT','MENTIONS'} and right['kind'] in {'topic','entity'}:
                transfers.append((left['id'], right['id']))
            elif e['relation'] == 'RECORDED_FOR':
                transfers.append((right['id'], left['id']))
            elif e['relation'] == 'HAS_AUDIO' and left['kind'] == 'chat' and right['kind'] == 'audio':
                transfers.append((left['id'], right['id']))
        # The transfer graph is a DAG with at most memory -> chat -> summary -> topic.
        # Four passes handle arbitrary edge insertion order without propagating into facts.
        for _ in range(4):
            for source, target in transfers:
                support[target].update(support[source])
        for id, n in nodes.items():
            ids = sorted(support[id])
            n['support_count'] = len(ids)
            n.setdefault('connection_count', 0)
            if n['kind'] == 'memory':
                continue
            n['weight_basis'] = 'memory_reference' if n['kind'] == 'event' and ids else 'related_memories' if ids else 'unassessed'
            n['weight_memory_ids'] = [nodes[mid]['ref'] for mid in ids[:20]]
            n['weight_sources_truncated'] = len(ids) > 20
            for key in ('confidence','strength','effective_strength','importance'):
                n[key] = max((nodes[mid][key] for mid in ids), default=None)
            if n['kind'] == 'event' and ids:
                memory = nodes[ids[0]]
                n.update(status=memory['status'], lifecycle=memory['lifecycle'], version=memory['version'])

    def query(self, p, query='', *, id='', hops=2, maximum=80, historical=False):
        if type(hops) is not int or not 1 <= hops <= 3 or not 1 <= maximum <= 200:
            raise ValueError('invalid network limits')
        snap = self.snapshot(p, historical=historical)
        nodes = {n['id']: n for n in snap['nodes']}
        if id and id not in nodes:
            raise PermissionError('network node unavailable')
        seeds = [id] if id else [n['id'] for n in snap['nodes']
                                if not query or query.casefold() in n['label'].casefold()]
        if not id and not query:
            # A bounded overview must represent files and facts even with many chat turns.
            groups = [[n['id'] for n in snap['nodes'] if n['kind'] == kind]
                      for kind in ('memory','document','summary','topic','entity','chat','context','event','audio')]
            seeds = [group[i] for i in range(4) for group in groups if len(group) > i]
        adjacent = {}
        for e in snap['edges']:
            adjacent.setdefault(e['source'], []).append(e['target'])
            adjacent.setdefault(e['target'], []).append(e['source'])
        picked, queue = set(), deque((s, 0) for s in seeds[:maximum])
        while queue and len(picked) < maximum:
            current, depth = queue.popleft()
            if current in picked:
                continue
            picked.add(current)
            if depth < hops:
                queue.extend((n, depth + 1) for n in adjacent.get(current, []) if n not in picked)
        return {'nodes': [nodes[n] for n in sorted(picked)],
                'edges': [e for e in snap['edges'] if e['source'] in picked and e['target'] in picked],
                'total_nodes': len(nodes), 'truncated': snap['truncated'] or len(picked) == maximum,
                'as_of': snap['as_of'], 'historical': historical,
                'note': 'Memory weights come from the memory object; effective_strength includes current decay. Other weights are maxima over unique associated memories, not independent probabilities. Null means unassessed. Event weights reflect current memory state. SUPPORTED_BY/DERIVED_FROM are provenance; ABOUT/MENTIONS/CONTAINS/RECORDED_FOR/NEXT are navigation; NEXT is time order, not causation.'}

    def sync_one(self):
        with self.e.store.graph_dispatch() as acquired:
            return self._sync_one() if acquired else False

    def _sync_one(self):
        """Publish a generation into an independent graph; reads always revalidate SQLite."""
        if not isinstance(self.e.graph_backend, FalkorGraph):
            return False
        now = self.e.clock()
        with self.e.store.transaction() as db:
            scopes = [r[0] for r in db.execute('SELECT principal FROM memories UNION SELECT principal FROM chat_turns UNION SELECT principal FROM knowledge_documents')]
            candidates = []
            revision = str(db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])
            for scope in scopes:
                db.execute('INSERT OR IGNORE INTO knowledge_network_state(principal) VALUES(?)', (scope,))
                state = db.execute('SELECT * FROM knowledge_network_state WHERE principal=?', (scope,)).fetchone()
                try:
                    published = json.loads(state['revision'])
                    if not isinstance(published, dict):
                        published = {}
                except (ValueError, TypeError):
                    published = {}
                age = now - published.get('as_of', 0)
                if state['lease'] < now and (published.get('format') != self.FORMAT or
                        published.get('revision') != revision or age >= self.REFRESH_SECONDS):
                    candidates.append((published.get('as_of', 0), scope))
            if not candidates:
                return False
            # Oldest first avoids starving other platforms as weights decay or revisions change.
            selected = min(candidates)[1]
            db.execute('UPDATE knowledge_network_state SET lease=? WHERE principal=?', (now + 300, selected))
        owner, scope, subject = selected.split('\x1f')
        p = Principal(owner, scope, subject, owner if scope == 'group' else subject)
        snap = self.snapshot(p, historical=True)
        generation = uuid.uuid4().hex
        name = self.e.config.graph_name
        if len(name) > 90:
            name = name[:50] + '_' + hashlib.sha256(name.encode()).hexdigest()[:20]
        backend = FalkorGraph(replace(self.e.config, graph_name=name + '_knowledge'),
                              secret_resolver=self.e.graph_backend.secret_resolver)
        try:
            for n in snap['nodes']:
                backend._query('MERGE (n:Knowledge {scope:$scope,id:$id,generation:$generation}) SET n.kind=$kind,n.label=$label,n.ref=$ref,n.confidence=toFloat($confidence),n.strength=toFloat($strength),n.effective_strength=toFloat($effective_strength),n.importance=toFloat($importance),n.support_count=toInteger($support_count),n.weight_basis=$weight_basis,n.status=$status,n.lifecycle=$lifecycle,n.as_of=toFloat($as_of),n.attributes=$attributes',
                               {'scope': selected, 'generation': generation,
                                **{k: n[k] if n.get(k) is not None else '' for k in
                                   ['id','kind','label','ref','confidence','strength','effective_strength','importance','support_count','weight_basis','status','lifecycle']},
                                'as_of': snap['as_of'], 'attributes': compact(n)})
            for e in snap['edges']:
                backend._query('MATCH (a:Knowledge {scope:$scope,id:$left,generation:$generation}), (b:Knowledge {scope:$scope,id:$right,generation:$generation}) MERGE (a)-[r:LINK {id:$id}]->(b) SET r.relation=$relation,r.scope=$scope',
                               {'scope': selected, 'generation': generation, 'left': e['source'], 'right': e['target'], 'id': e['id'], 'relation': e['relation']})
            with self.e.store.transaction() as db:
                # A policy change while publishing invalidates this generation.
                current = str(db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])
                if current == revision:
                    db.execute('UPDATE knowledge_network_state SET revision=?,generation=?,lease=0 WHERE principal=? AND lease=?',
                               (compact({'format':self.FORMAT,'revision':revision,'as_of':snap['as_of']}), generation, selected, now + 300))
                else:
                    db.execute('UPDATE knowledge_network_state SET lease=0 WHERE principal=? AND lease=?', (selected, now + 300))
            backend._query('MATCH (n:Knowledge {scope:$scope}) WHERE n.generation<>$generation DETACH DELETE n',
                           {'scope': selected, 'generation': generation})
        except Exception:
            with self.e.store.transaction() as db:
                db.execute('UPDATE knowledge_network_state SET lease=? WHERE principal=? AND lease=?', (now + 10, selected, now + 300))
            return False
        finally:
            backend.close()
        return True
