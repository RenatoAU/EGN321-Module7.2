"""Deterministic competing-cause tests, without real-time sleeps."""
import json
import sqlite3
from datetime import datetime
import pytest
import app
from app import Monitor, create_app

def test_cause1_paused_replay_and_recovery(tmp_path, monkeypatch):
    m=Monitor(tmp_path,interval=.5,demo=True)
    m.tick()
    before=m.snapshot()
    epoch=datetime.fromisoformat(before['latest']['received_utc']).timestamp()
    (tmp_path/'control.json').write_text(json.dumps({'pause':True}))
    monkeypatch.setattr(app.time,'time',lambda:epoch+2)
    m.tick()
    state=m.snapshot()
    assert state['latest']['id']==before['latest']['id']
    assert state['health']=='DEGRADED' and state['input_alert']=='STALE_DATA'
    assert state['current'] is None
    assert create_app(m).test_client().get('/').status_code==200
    monkeypatch.setattr(app.time,'time',lambda:epoch+6)
    m.tick()
    assert m.snapshot()['health']=='FAILED'
    monkeypatch.undo()
    (tmp_path/'control.json').write_text(json.dumps({'pause':False}))
    m.tick()
    recovered=m.snapshot()
    assert recovered['health']=='HEALTHY' and recovered['input_alert']=='NORMAL'
    assert recovered['latest']['id']==before['latest']['id']+1
    with m.connect() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT COUNT(*) FROM readings').fetchone()[0]==8780
    logs=[json.loads(line) for line in (tmp_path/'application.jsonl').read_text().splitlines()]
    transition=next(e for e in logs if e['event']=='HEALTH_CHANGED' and e['health']=='DEGRADED')
    assert transition['reason']=='NO_DELIVERY' and transition['severity']=='WARNING'
    assert transition['previous_health']=='HEALTHY'
    assert any(e['event']=='INPUT_ALERT_CHANGED' and e['input_alert']=='NORMAL' and
               e['previous_alert']=='STALE_DATA' for e in logs)

def test_cause2_database_lock_confirm_then_reject(tmp_path, monkeypatch):
    m=Monitor(tmp_path,demo=True)
    m.tick()
    def fast_connection():
        db=sqlite3.connect(m.path,timeout=.05)
        db.row_factory=sqlite3.Row
        return db
    monkeypatch.setattr(m,'connect',fast_connection)
    locker=sqlite3.connect(m.path)
    locker.execute('BEGIN EXCLUSIVE')
    try:
        with pytest.raises(sqlite3.OperationalError,match='locked'):
            m.tick()
    finally:
        locker.rollback()
        locker.close()
    m.tick()
    assert m.snapshot()['latest']['id']==2
    assert m.snapshot()['health']=='HEALTHY'

def test_temperature_alert_still_works(tmp_path):
    m=Monitor(tmp_path,demo=True)
    (tmp_path/'control.json').write_text(json.dumps({'value':32}))
    for _ in range(3): m.tick()
    assert m.snapshot()['alert']=='ALERT'
    (tmp_path/'control.json').write_text(json.dumps({'value':27}))
    m.tick()
    assert m.snapshot()['alert']=='NORMAL' and m.snapshot()['health']=='HEALTHY'
