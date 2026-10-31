"""Durable, private one-click processing of all previous unorganized chat records."""

import uuid
from pathlib import Path

from .chat_import import import_sessions
from .chats import Chats
from .config import Principal

UNFINISHED = """t.status!='redacted' AND NOT EXISTS (
    SELECT 1 FROM chat_native_state n WHERE n.turn_id=t.id AND n.active=0)
    AND (t.organized=0 OR t.status IN ('pending','working') OR t.policy_epoch!=?)"""


class Backfill:
    def __init__(self, engine):
        self.e = engine

    def _track(self, db, p, job):
        # Policy changes during historical review can invalidate previously organized rows.
        db.execute('''INSERT OR IGNORE INTO chat_backfill_items(job_id,turn_id)
                      SELECT ?,t.id FROM chat_turns t WHERE t.principal=? AND t.created<=? AND ''' + UNFINISHED,
                   (job['id'],p.key,job['cutoff'],self.e._epoch(db,p)))

    def _progress(self, db, p, job):
        if not job:
            return None
        now, epoch = self.e.clock(), self.e._epoch(db,p)
        rows = db.execute('''SELECT t.status,t.organized,t.policy_epoch,t.lease,t.retry_at,t.attempts,
                             coalesce(n.active,1) AS native_active
                             FROM chat_backfill_items i JOIN chat_turns t ON t.id=i.turn_id
                             LEFT JOIN chat_native_state n ON n.turn_id=t.id
                             WHERE i.job_id=? AND t.principal=?''', (job['id'],p.key)).fetchall()
        ready = protected = working = retrying = done = 0
        for row in rows:
            finished = not row['native_active'] or row['status'] == 'redacted' or (row['organized'] == 1 and
                       row['status'] in {'ready','silent'} and row['policy_epoch'] == epoch)
            if finished:
                done += 1
                ready += row['status'] == 'ready' and bool(row['native_active'])
                protected += not row['native_active'] or row['status'] in {'silent','redacted'}
            elif row['lease'] > now:
                working += 1
            elif row['retry_at'] > now and row['attempts'] > 0:
                retrying += 1
        return {k:job[k] for k in ('id','state','created','updated','cutoff','imported','skipped_sessions','error','retry_at')} | {
            'total':len(rows),'done':done,'remaining':len(rows)-done,'ready':ready,
            'protected':protected,'working':working,'retrying':retrying,
            'pending':len(rows)-done-working-retrying}

    def _status(self, db, p):
        job = db.execute('SELECT * FROM chat_backfill_jobs WHERE principal=? ORDER BY created DESC,rowid DESC LIMIT 1', (p.key,)).fetchone()
        pending = db.execute('SELECT count(*) FROM chat_turns t WHERE t.principal=? AND ' + UNFINISHED,
                             (p.key,self.e._epoch(db,p))).fetchone()[0]
        return {'job':self._progress(db,p,job),'pending':pending,
                'model_available':bool(self.e.model and self.e.model.available),
                'archive_enabled':self.e.config.chat_auto_archive}

    def status(self, p):
        Chats._private(p)
        with self.e.store.transaction() as db:
            return self._status(db,p)

    def request(self, p):
        Chats._private(p)
        if not self.e.config.chat_auto_archive:
            raise RuntimeError('chat archiving is disabled')
        now = self.e.clock()
        with self.e.store.transaction() as db:
            active = db.execute("SELECT * FROM chat_backfill_jobs WHERE principal=? AND state IN ('importing','processing')", (p.key,)).fetchone()
            if not active:
                id = uuid.uuid4().hex
                db.execute("INSERT INTO chat_backfill_jobs(id,principal,state,created,updated,cutoff) VALUES(?,?,'importing',?,?,?)",
                           (id,p.key,now,now,now))
                active = db.execute('SELECT * FROM chat_backfill_jobs WHERE id=?', (id,)).fetchone()
                self._track(db,p,active)
                # Retry old failures promptly, without stealing an active record lease.
                db.execute('''UPDATE chat_turns SET retry_at=0 WHERE lease<? AND id IN
                              (SELECT turn_id FROM chat_backfill_items WHERE job_id=?)''', (now,id))
            return self._status(db,p)

    def retry(self, p):
        Chats._private(p)
        now = self.e.clock()
        with self.e.store.transaction() as db:
            job = db.execute('SELECT * FROM chat_backfill_jobs WHERE principal=? ORDER BY created DESC,rowid DESC LIMIT 1', (p.key,)).fetchone()
            if not job or job['state'] == 'completed':
                raise ValueError('no unfinished processing task')
            if job['lease'] >= now:
                return self._status(db,p)
            db.execute("UPDATE chat_backfill_jobs SET state=?,retry_at=0,error='',updated=? WHERE id=?",
                       ('importing' if job['state']=='failed' else job['state'],now,job['id']))
            self._track(db,p,job)
            db.execute('''UPDATE chat_turns SET retry_at=0 WHERE lease<? AND id IN
                          (SELECT turn_id FROM chat_backfill_items WHERE job_id=?)''', (now,job['id']))
            return self._status(db,p)

    def step(self, native_path=None, *, maximum=200):
        """One import chunk or one model batch; safe across process restart and concurrent workers."""
        if type(maximum) is not int or maximum < 1:
            raise ValueError('invalid import batch size')
        now = self.e.clock()
        lease = now + max(300,self.e.config.timeout * 3)
        # Idle polls must not take the write lock; many pollers share one database.
        if not self.e.store.rows("SELECT 1 FROM chat_backfill_jobs WHERE state IN ('importing','processing') AND lease<? AND retry_at<=? LIMIT 1", (now,now)):
            return False
        with self.e.store.transaction() as db:
            job = db.execute("SELECT * FROM chat_backfill_jobs WHERE state IN ('importing','processing') AND lease<? AND retry_at<=? ORDER BY updated,created LIMIT 1", (now,now)).fetchone()
            if not job:
                return False
            job = dict(job)
            attempt = job['attempts'] + 1
            db.execute('UPDATE chat_backfill_jobs SET lease=?,attempts=? WHERE id=?', (lease,attempt,job['id']))
        owner, scope, subject = job['principal'].split('\x1f')
        p = Principal(owner,scope,subject,subject)

        def owned(db):
            return db.execute('SELECT * FROM chat_backfill_jobs WHERE id=? AND principal=? AND lease=? AND attempts=?',
                              (job['id'],p.key,lease,attempt)).fetchone()

        try:
            Chats._private(p)
            if job['state'] == 'importing':
                def track(id):
                    with self.e.store.transaction() as db:
                        if owned(db):
                            inserted = db.execute('INSERT OR IGNORE INTO chat_backfill_items(job_id,turn_id) SELECT ?,id FROM chat_turns WHERE id=? AND principal=?',
                                                  (job['id'],id,p.key)).rowcount
                            if inserted:
                                db.execute('UPDATE chat_backfill_jobs SET imported=imported+1 WHERE id=?', (job['id'],))
                result = import_sessions(self.e,native_path,maximum=maximum,principal=p,before=job['cutoff'],on_import=track,after_id=job['native_cursor']) if native_path else {'imported':0,'skipped_sessions':0,'cursor':job['native_cursor']}
                with self.e.store.transaction() as db:
                    if owned(db):
                        self._track(db,p,job)
                        db.execute('UPDATE chat_backfill_jobs SET state=?,skipped_sessions=?,native_cursor=?,lease=0,updated=?,error=?,retry_at=0 WHERE id=?',
                                   ('processing' if result['imported'] < maximum else 'importing',result['skipped_sessions'],result['cursor'],self.e.clock(),
                                    'history_unavailable' if native_path and not Path(native_path).exists() else '',job['id']))
                return True
            with self.e.store.transaction() as db:
                if not owned(db):
                    return False
                self._track(db,p,job)
                progress = self._progress(db,p,job)
            worked = False
            if progress['remaining']:
                if self.e.model and self.e.model.available:
                    worked = Chats(self.e).process_one(principal=p,job_id=job['id'])
                else:
                    with self.e.store.transaction() as db:
                        if owned(db):
                            db.execute("UPDATE chat_backfill_jobs SET lease=0,retry_at=?,updated=?,error='model_unavailable' WHERE id=?", (now+30,now,job['id']))
                    return False
            with self.e.store.transaction() as db:
                if owned(db):
                    self._track(db,p,job)
                    progress = self._progress(db,p,job)
                    complete = progress['remaining'] == 0
                    error = 'records_retrying' if progress['retrying'] else 'history_unavailable' if job['error']=='history_unavailable' else ''
                    db.execute('UPDATE chat_backfill_jobs SET state=?,lease=0,retry_at=?,updated=?,error=? WHERE id=?',
                               ('completed' if complete else 'processing',0 if complete or worked else now+2,self.e.clock(),error,job['id']))
                    return worked or complete
        except Exception:
            with self.e.store.transaction() as db:
                if owned(db):
                    # Error codes contain no original text, model replies or credentials.
                    db.execute("UPDATE chat_backfill_jobs SET state='failed',lease=0,updated=?,error='history_processing_failed' WHERE id=?", (self.e.clock(),job['id']))
            return False
        return False
