from gramem.config import Config, Principal
from gramem.engine import Engine
from gramem.relations import Relations

OWNER = Principal('owner', 'owner', 'owner', 'owner')


class Model:
    available = True
    space = 'test'

    def __init__(self, relations, callback=None):
        self.relations = relations
        self.callback = callback
        self.calls = 0

    def embed(self, text):
        return None

    def extract(self, prompt, payload):
        self.calls += 1
        if self.callback:
            self.callback()
        return {'relations': self.relations}


def test_explicit_write_backfilled_once(tmp_path):
    relation = {'subject': '小明', 'predicate': 'WORKS_AT', 'object': '微软'}
    model = Model([relation])
    e = Engine(tmp_path / 'memory.sqlite', Config(), model=model)
    id = e.remember(OWNER, '小明在微软工作', kind='relationship')
    worker = Relations(e)
    assert worker.process_one()
    assert not worker.process_one()
    assert model.calls == 1
    assert e.store.rows('SELECT count(*) AS n FROM graph_outbox')[0]['n'] == 1
    import json
    row = e.store.rows('SELECT metadata FROM memories WHERE id=?', (id,))[0]
    assert json.loads(row['metadata'])['relations'] == [relation]


def test_no_relationship_is_completed(tmp_path):
    model = Model([])
    e = Engine(tmp_path / 'memory.sqlite', Config(), model=model)
    e.remember(OWNER, '今天很好')
    assert Relations(e).process_one()
    assert not Relations(e).process_one()
    assert not e.store.rows('SELECT * FROM graph_outbox')


def test_invented_names_filtered(tmp_path):
    model = Model([{'subject': 'Xiaoming', 'predicate': 'WORKS_AT', 'object': 'Microsoft'}])
    e = Engine(tmp_path / 'memory.sqlite', Config(), model=model)
    e.remember(OWNER, '小明在微软工作')
    assert Relations(e).process_one()
    assert not e.store.rows('SELECT * FROM graph_outbox')


def test_forget_during_extraction_cannot_restore_edges(tmp_path):
    relation = {'subject': '小明', 'predicate': 'WORKS_AT', 'object': '微软'}
    model = Model([relation])
    e = Engine(tmp_path / 'memory.sqlite', Config(), model=model)
    e.remember(OWNER, '小明在微软工作', slot='job')
    model.callback = lambda: e.exclude(OWNER, 'job')
    assert Relations(e).process_one()
    assert not e.store.rows("SELECT * FROM graph_outbox WHERE action='put'")


def test_existing_relation_not_duplicated(tmp_path):
    relation = {'subject': '小明', 'predicate': 'WORKS_AT', 'object': '微软'}
    e = Engine(tmp_path / 'memory.sqlite', Config(), model=Model([relation]))
    e.remember(OWNER, '小明在微软工作', metadata={'relations': [relation]})
    assert Relations(e).process_one()
    assert e.store.rows('SELECT count(*) AS n FROM graph_outbox')[0]['n'] == 1
