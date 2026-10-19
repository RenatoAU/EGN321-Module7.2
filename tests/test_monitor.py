import sqlite3
import time
from datetime import datetime, timezone
from app import Monitor, create_app
from alert_logic import update

def test_persistence_noise_and_hysteresis():
    state,count='NORMAL',0
    for value in (31,29,31,None,31,31):
        state,count=update(state,count,value)
        assert state=='NORMAL'
    state,count=update(state,count,31)
    assert state=='ALERT'
    assert update(state,count,29)[0]=='ALERT'
    assert update(state,count,None)[0]=='ALERT'
    assert update(state,count,28.5)[0]=='NORMAL'

def test_archive_unchanged_and_restart_cursor(tmp_path):
    m=Monitor(tmp_path)
    m.tick()
    with m.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM readings').fetchone()[0]==8780
        assert db.execute("SELECT MIN(timestamp) FROM readings").fetchone()[0]=='2026-10-01T08:00:00'
        assert db.execute("SELECT COUNT(*) FROM readings WHERE sensor_id='temperature' AND status='REJECTED'").fetchone()[0]==3
    restarted=Monitor(tmp_path)
    restarted.tick()
    with restarted.connect() as db:
        assert db.execute('SELECT cursor FROM monitor_state').fetchone()[0]==2
        assert db.execute('SELECT COUNT(*) FROM monitor_readings').fetchone()[0]==2
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    client=create_app(restarted).test_client()
    assert client.get('/').status_code==200
    assert client.get('/history').status_code==200

def test_stale_hides_current_and_failed(tmp_path):
    m=Monitor(tmp_path,interval=1)
    m.tick()
    with m.connect() as db:
        db.execute('UPDATE monitor_readings SET received_utc=?',(datetime.fromtimestamp(time.time()-4,timezone.utc).isoformat(),))
    assert m.snapshot()['current'] is None
    assert m.snapshot()['data_status']=='STALE'
    assert m.snapshot()['health']=='DEGRADED'
    with m.connect() as db:
        db.execute('UPDATE monitor_readings SET received_utc=?',(datetime.fromtimestamp(time.time()-11,timezone.utc).isoformat(),))
    assert m.snapshot()['health']=='FAILED'

def test_missing_and_rejected_preserved(tmp_path):
    import json
    m=Monitor(tmp_path,demo=True)
    for value,status in (('', 'MISSING'),('85','OUT_OF_RANGE')):
        (tmp_path/'control.json').write_text(json.dumps(dict(value=value,status=status)))
        m.tick()
        assert m.snapshot()['current'] is None
    with m.connect() as db:
        rows=db.execute('SELECT * FROM monitor_readings').fetchall()
    assert rows[0]['status']=='MISSING'
    assert rows[1]['status']=='REJECTED'
    assert rows[1]['raw_value']=='85'
