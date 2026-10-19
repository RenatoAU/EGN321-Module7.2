"""Capture a real paused-replay investigation; no invented readings or times."""
import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def run(label):
    out = ROOT / 'investigations' / label
    out.mkdir(parents=True, exist_ok=False)  # Never overwrite earlier evidence.
    runtime = out / 'runtime'
    runtime.mkdir()
    def stamp():
        return datetime.now(timezone.utc).isoformat()
    def control(paused):
        temporary = runtime / 'control.tmp'
        temporary.write_text(json.dumps({'pause': paused}))
        temporary.replace(runtime / 'control.json')
    actions = []
    def action(event, **fields):
        item = dict(timestamp=stamp(), component='Investigator', event=event, **fields)
        actions.append(item)
        with (out/'actions.jsonl').open('a') as f:
            f.write(json.dumps(item)+'\n')
    def get(path):
        with urllib.request.urlopen('http://127.0.0.1:5058'+path, timeout=2) as r:
            return r.status, r.read()
    def wait(predicate, timeout=15):
        end = time.monotonic()+timeout
        while time.monotonic() < end:
            try:
                state = json.loads(get('/api/status')[1])
                if predicate(state):
                    return state
            except (OSError, ValueError):
                pass
            time.sleep(.05)
        raise AssertionError('Expected condition not reached')
    def capture(name):
        code, raw = get('/api/status')
        state = json.loads(raw)
        dashboard_code, html = get('/')
        with sqlite3.connect(runtime/'monitor.db') as db:
            rows = db.execute('SELECT * FROM monitor_readings ORDER BY id').fetchall()
            archive = db.execute('SELECT COUNT(*) FROM readings').fetchone()[0]
            integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
        result = dict(captured_utc=stamp(), api_http=code, dashboard_http=dashboard_code,
                      database_integrity=integrity, replay_rows=len(rows), archive_rows=archive,
                      replay_prefix_sha256=hashlib.sha256(json.dumps(rows).encode()).hexdigest(), state=state)
        (out/(name+'.json')).write_text(json.dumps(result,indent=2))
        (out/(name+'.html')).write_bytes(html)
        action('CAPTURE_'+name.upper(), health=state['health'], data_status=state['data_status'],
               latest_id=state['latest']['id'], dashboard_http=dashboard_code, replay_rows=len(rows))
        return result, rows
    source = ROOT/'data/module6_sample_sensor_history.csv'
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    output = (out/'process_output.txt').open('w')
    control(False)
    process = subprocess.Popen([sys.executable, str(ROOT/'app.py'), '--runtime', str(runtime),
                               '--interval', '0.5', '--port', '5058', '--demo'],
                              cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
    try:
        wait(lambda s: s['health']=='HEALTHY' and s['latest']['id']>=3)
        normal, prefix = capture('01_normal')
        control(True)
        action('SOURCE_PAUSED', exact_action='atomically set runtime/control.json to {"pause": true}',
               expected='no new deliveries; STALE after >1.5s; FAILED after >5s')
        wait(lambda s:s['data_status']=='STALE' and s['health']=='DEGRADED')
        stale, _ = capture('02_stale')
        wait(lambda s:s['health']=='FAILED')
        failed, frozen = capture('03_failed')
        assert stale['replay_rows']==failed['replay_rows']
        # Rule out a database write failure without altering application tables.
        with sqlite3.connect(runtime/'monitor.db') as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE monitor_state SET cursor=cursor WHERE id=1')
            db.rollback()
        action('DATABASE_WRITE_PROBE_OK', result='BEGIN IMMEDIATE and no-op UPDATE succeeded; rolled back')
        action('HYPOTHESIS_SELECTED', cause='paused source', alternative='SQLite lock/write failure',
               evidence='frozen latest id, live HTTP, integrity ok, write probe ok; no DB exception')
        control(False)
        action('SOURCE_RESUMED', exact_action='atomically set control.json to {"pause": false}')
        wait(lambda s:s['health']=='HEALTHY' and s['latest']['id']>failed['state']['latest']['id'])
        recovered, after = capture('04_recovered')
        assert after[:len(prefix)]==prefix
        assert recovered['archive_rows']==normal['archive_rows']==8780
        assert recovered['database_integrity']=='ok' and recovered['dashboard_http']==200
        assert recovered['state']['alert']=='NORMAL'
        assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
        action('VERIFICATION_PASSED', prefix_preserved=True, source_csv_sha256=source_hash,
               same_pid=process.pid, temperature_alert='NORMAL', input_resumed=True)
        (out/'verification.json').write_text(json.dumps(dict(passed=True, pid=process.pid,
            source_sha256=source_hash, prefix_preserved=True, archive_rows=8780,
            normal_rows=normal['replay_rows'], failed_rows=failed['replay_rows'],
            recovered_rows=recovered['replay_rows'], platform=sys.platform,
            environment='Assistant execution environment; original CSV values; accelerated classroom replay'),indent=2))
    finally:
        process.terminate()
        process.wait(timeout=10)
        output.close()
        shutil.copy2(runtime/'application.jsonl',out/'application.jsonl')
        with sqlite3.connect(runtime/'monitor.db') as db, sqlite3.connect(out/'verified_monitor.db') as target:
            db.backup(target)
    print('PASS: '+str(out))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--label', default=datetime.now(timezone.utc).strftime('run_%Y%m%dT%H%M%S'))
    args=parser.parse_args()
    if Path(args.label).name != args.label or args.label in ('.','..'):
        parser.error('label must be one directory name')
    run(args.label)
