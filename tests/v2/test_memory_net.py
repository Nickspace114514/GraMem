"""Memory-net projections track authoritative weights without creating new facts."""
import json
import math

import pytest
from test_chats import archive, capture  # noqa: F401
from test_engine import CONTACT, OWNER, engine  # noqa: F401
from test_provider import make_provider  # noqa: F401

from gramem.network import Network
from gramem.tokens import count


def by_id(e, *, historical=False):
    return {n['id']: n for n in Network(e).snapshot(OWNER, historical=historical)['nodes']}


def test_live_weights_decay_reinforcement_and_permanence(engine):  # noqa: F811
    now = [100000.0]
    engine.clock = lambda: now[0]
    id = engine.remember(OWNER, 'GraMem 采用 SQLite 保存记忆', kind='project')
    with engine.store.transaction() as db:
        db.execute('UPDATE memories SET confidence=.83,importance=.72,strength=.61,decay=.02 WHERE id=?', (id,))
    now[0] += 86400
    row, node = engine.get(OWNER, id), by_id(engine)['memory:' + id]
    for key in ('confidence','importance','strength','status','lifecycle','version','maintained'):
        assert node[key] == row[key]
    assert node['effective_strength'] == pytest.approx(.61 * math.exp(-.02))
    # Projection is read-only: decay never overwrites the memory object.
    assert engine.get(OWNER, id)['strength'] == .61
    revision = engine.store.revision
    engine.recall(OWNER, 'GraMem SQLite', session='s', turn='one')
    assert engine.store.revision > revision
    reinforced = by_id(engine)['memory:' + id]
    assert reinforced['strength'] == engine.get(OWNER, id)['strength']
    assert reinforced['strength'] > node['effective_strength']
    assert reinforced['lifecycle'] == 'reinforced'
    with engine.store.transaction() as db:
        db.execute("UPDATE memories SET lifecycle='permanent' WHERE id=?", (id,))
    now[0] += 100 * 86400
    assert by_id(engine)['memory:' + id]['effective_strength'] == reinforced['strength']


def test_maintenance_updates_revision_even_without_lifecycle_transition(engine):  # noqa: F811
    start = engine.clock()
    id = engine.remember(OWNER, 'GraMem 数据长期保存在 SQLite', kind='project')
    revision = engine.store.revision
    engine.clock = lambda: start + 3600
    assert engine.maintain() == 0
    assert engine.store.revision > revision
    assert by_id(engine)['memory:' + id]['strength'] == engine.get(OWNER, id)['strength'] < .9


def test_record_aggregation_is_deduplicated_and_never_flows_through_time_edges(archive):  # noqa: F811
    source = archive.e.enqueue(OWNER, 'GraMem 采用 SQLite', session='s', turn='1')
    first = capture(archive, 'GraMem 采用 SQLite', source_ids=[source], created=10)
    unrelated = capture(archive, '没有来源记忆的原话', turn='2', session='other', created=20)
    id = archive.e.remember(OWNER, 'GraMem 采用 SQLite', slot='architecture')
    with archive.e.store.transaction() as db:
        db.execute('UPDATE memories SET source=?,confidence=.74,strength=.51 WHERE id=?', (source,id))
    assert archive.process_one() and archive.process_one()
    nodes = by_id(archive.e)
    assert nodes['chat:' + first]['confidence'] == .74
    assert nodes['chat:' + first]['strength'] == .51
    assert nodes['context:s']['support_count'] == 1
    topics = [n for n in nodes.values() if n['kind'] == 'topic']
    assert topics[0]['support_count'] == 1  # Direct mention + chat + summary is one memory.
    assert nodes['chat:' + unrelated]['confidence'] is None
    assert nodes['chat:' + unrelated]['strength'] is None
    assert nodes['chat:' + unrelated]['weight_basis'] == 'unassessed'
    assert nodes['chat:' + unrelated]['connection_count'] > 0


def test_event_history_versions_and_chronology_remain_scoped(engine):  # noqa: F811
    now = [100000.0]
    engine.clock = lambda: now[0]
    old = engine.remember(OWNER, 'GraMem 旧方案使用 JSON', kind='event', slot='plan')
    now[0] += 10
    new = engine.remember(OWNER, 'GraMem 新方案使用 SQLite', kind='event', slot='plan',
                          action='UPDATE', targets=[old])
    engine.remember(CONTACT, '其他人的独立事件', kind='event')
    current = by_id(engine)
    assert 'memory:' + old not in current and 'memory:' + new in current
    history = Network(engine).snapshot(OWNER, historical=True)
    nodes = {n['id']: n for n in history['nodes']}
    assert nodes['memory:' + old]['status'] == 'superseded'
    assert nodes['memory:' + old]['valid_until'] == now[0]
    events = [n for n in nodes.values() if n['kind'] == 'event']
    assert {n['action'] for n in events} >= {'ADD','UPDATE'}
    assert all(n['strength'] == nodes['memory:' + n['memory_id']]['strength'] for n in events)
    assert '其他人' not in json.dumps(history, ensure_ascii=False)
    assert any(e['relation'] == 'NEXT' and nodes[e['source']]['created'] <= nodes[e['target']]['created'] for e in history['edges'])


def test_excluded_history_cannot_contribute_events_weights_or_timeline_bridges(archive):  # noqa: F811
    source = archive.e.enqueue(OWNER, '禁提标记 GraMem', session='s', turn='1')
    id = capture(archive, '禁提标记 GraMem', source_ids=[source])
    fact = archive.e.remember(OWNER, '禁提标记 GraMem', slot='private')
    with archive.e.store.transaction() as db:
        db.execute('UPDATE memories SET source=? WHERE id=?', (source,fact))
        # Audit detail must never surface even while the corresponding memory is visible.
        db.execute("UPDATE events SET detail=? WHERE memory_id=?", ('{"secret":"never expose raw detail"}',fact))
    assert archive.process_one()
    assert 'never expose' not in json.dumps(Network(archive.e).snapshot(OWNER, historical=True))
    archive.e.exclude(OWNER, 'private', state='suppressed')
    assert archive.process_one()
    snap = Network(archive.e).snapshot(OWNER, historical=True)
    assert snap['nodes'] == [] and snap['edges'] == []
    assert archive.e.store.rows('SELECT length(original) size FROM chat_turns WHERE id=?', (id,))[0]['size'] > 0


def test_query_weights_are_identical_to_full_snapshot_not_the_bounded_neighborhood(archive):  # noqa: F811
    source = archive.e.enqueue(OWNER, 'GraMem 使用 SQLite', session='s', turn='1')
    id = capture(archive, 'GraMem 使用 SQLite', source_ids=[source])
    fact = archive.e.remember(OWNER, 'GraMem 使用 SQLite', slot='architecture')
    with archive.e.store.transaction() as db:
        db.execute('UPDATE memories SET source=? WHERE id=?', (source,fact))
    assert archive.process_one()
    nodes = by_id(archive.e)
    result = Network(archive.e).query(OWNER, id='chat:' + id, maximum=1)
    assert len(result['nodes']) == 1 and not result['edges']
    assert result['nodes'][0]['confidence'] == nodes['chat:' + id]['confidence']
    assert result['nodes'][0]['support_count'] == 1


def test_graph_refreshes_decaying_weights_without_revision_change_and_services_each_scope(engine, monkeypatch):  # noqa: F811
    import gramem.network as module

    published = []

    class Graph:
        secret_resolver = staticmethod(lambda key: None)

        def __init__(self, *args, **kwargs):
            pass

        def _query(self, query, params):
            published.append((query,params))

        def close(self):
            pass

    monkeypatch.setattr(module, 'FalkorGraph', Graph)
    engine.graph_backend = Graph()
    now = [100000.0]
    engine.clock = lambda: now[0]
    engine.remember(OWNER, 'Owner 使用 SQLite')
    engine.remember(CONTACT, '联系人自己的记录')
    network = Network(engine)
    revision = engine.store.revision
    assert network.sync_one() and network.sync_one()
    assert not network.sync_one()
    states = engine.store.rows('SELECT principal,revision FROM knowledge_network_state')
    assert {r['principal'] for r in states} == {OWNER.key,CONTACT.key}
    assert all(json.loads(r['revision'])['as_of'] == now[0] for r in states)
    first = [p for q,p in published if 'toFloat($effective_strength)' in q and p['kind'] == 'memory']
    assert len(first) == 2
    now[0] += 61
    assert engine.store.revision == revision
    assert network.sync_one() and network.sync_one()
    assert not network.sync_one()
    second = [p for q,p in published if 'toFloat($effective_strength)' in q and p['kind'] == 'memory'][2:]
    assert len(second) == 2
    assert all(b['effective_strength'] < a['effective_strength'] for a,b in zip(first,second,strict=True))
    assert all(json.loads(p['attributes'])['strength'] == p['strength'] for p in second)


@pytest.mark.parametrize('budget', [512,1024])
def test_native_memory_net_tool_total_budget_includes_weights_and_edges(make_provider, budget):  # noqa: F811
    provider = make_provider(chat_type='direct')
    p = provider.config.principal('teams','verified')
    for i in range(10):
        provider.engine.remember(p, 'GraMem SQLite 项目记忆 ' + str(i), slot='project:' + str(i))
    provider.config.recall_tokens = budget
    response = provider.handle_tool_call('gramem_network', {'query':'GraMem','historical':True})
    assert count(response) <= budget
    result = json.loads(response)
    assert result['nodes'] and result['truncated']
    assert all('confidence' in n and 'effective_strength' in n for n in result['nodes'])
    ids = {n['id'] for n in result['nodes']}
    assert all(e['source'] in ids and e['target'] in ids for e in result['edges'])
