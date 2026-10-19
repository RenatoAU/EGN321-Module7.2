"""Module 7: existing Module 6 archive plus a separately identified replay stream."""
import argparse
import csv
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, jsonify, render_template
from waitress import serve
import history
from alert_logic import update
from logging_config import setup, event

ROOT = Path(__file__).resolve().parent

def utc():
    return datetime.now(timezone.utc).isoformat()

class Monitor:
    def __init__(self, folder, interval=2, demo=False):
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder/'monitor.db'
        self.interval, self.demo = interval, demo
        self.log = setup(self.folder)
        self.started = time.time()
        self.last_health = None
        self.last_input_alert = None
        with open(ROOT/'data/module6_sample_sensor_history.csv', newline='') as f:
            self.rows = list(csv.DictReader(f))
        with history.connect(self.path) as db:
            if not db.execute('SELECT COUNT(*) FROM readings').fetchone()[0]:
                history.import_csv(db, ROOT/'data/module6_sample_sensor_history.csv')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS monitor_readings (
              id INTEGER PRIMARY KEY, received_utc TEXT NOT NULL,
              source_timestamp TEXT NOT NULL, raw_value TEXT NOT NULL,
              accepted_value REAL, status TEXT NOT NULL, provenance TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS monitor_state (
              id INTEGER PRIMARY KEY CHECK(id=1), cursor INTEGER NOT NULL,
              alert TEXT NOT NULL, high_count INTEGER NOT NULL);
            INSERT OR IGNORE INTO monitor_state VALUES(1,0,'NORMAL',0);
            ''')
        event(self.log, 'STARTUP', pid=os.getpid(), mode='synthetic_test' if demo else 'module6_replay')
        event(self.log, 'RECOVERY_READY', archive_rows=8780)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def tick(self):
        control = {}
        if self.demo and (self.folder/'control.json').exists():
            control = json.loads((self.folder/'control.json').read_text())
        with self.connect() as db:
            state = db.execute('SELECT * FROM monitor_state').fetchone()
            if not control.get('pause') and state['cursor'] < len(self.rows):
                row = self.rows[state['cursor']]
                raw = str(control.get('value', row['temperature_c']))
                source_status = control.get('status', row['temperature_status'])
                value, status = history.validate(raw, source_status, 0, 50)
                previous = db.execute('SELECT received_utc FROM monitor_readings ORDER BY id DESC LIMIT 1').fetchone()
                count = state['high_count']
                if previous and time.time()-datetime.fromisoformat(previous[0]).timestamp() > 3*self.interval:
                    count = 0
                alert, count = update(state['alert'], count, value)
                db.execute('INSERT INTO monitor_readings(received_utc,source_timestamp,raw_value,accepted_value,status,provenance) VALUES(?,?,?,?,?,?)',
                           (utc(),row['timestamp'],raw,value,status,'SYNTHETIC_TEST' if self.demo else 'MODULE6_ACCELERATED_REPLAY'))
                db.execute('UPDATE monitor_state SET cursor=?,alert=?,high_count=? WHERE id=1', (state['cursor']+1,alert,count))
                db.commit()
                event(self.log, 'READING_PROCESSED', component='Replay', sample_number=state['cursor']+1, reading_id=state['cursor']+1, database_path=str(self.path), status=status, source_timestamp=row['timestamp'], value=value)
                if alert != state['alert']:
                    event(self.log, 'ALERT_ACTIVATED' if alert == 'ALERT' else 'ALERT_CLEARED', value=value)
        snapshot = self.snapshot()
        health = snapshot['health']
        reason = ('NO_DELIVERY' if snapshot['data_status']=='STALE' else
                  'NO_VALID_INPUT' if snapshot['valid_age_seconds'] > 3*self.interval else
                  'INVALID_READING' if snapshot['data_status'] not in ('ACCEPTED','WAITING') else
                  'TEMPERATURE_ALERT' if snapshot['alert']=='ALERT' else 'FRESH_VALID_INPUT')
        fields = dict(component='Health', previous_health=self.last_health, health=health,
                      reason=reason, age_seconds=snapshot['age_seconds'],
                      valid_age_seconds=snapshot['valid_age_seconds'],
                      stale_after_seconds=3*self.interval, failed_after_seconds=10*self.interval,
                      latest_reading_id=snapshot['latest']['id'] if snapshot['latest'] else None,
                      database_path=str(self.path))
        if health != self.last_health:
            event(self.log, 'HEALTH_CHANGED', level='ERROR' if health=='FAILED' else
                  'WARNING' if health=='DEGRADED' else 'INFO', **fields)
            if health in ('DEGRADED','FAILED'):
                event(self.log, 'MISSING_OR_STALE_DATA', level='WARNING', **fields)
            self.last_health = health
        if snapshot['input_alert'] != self.last_input_alert:
            event(self.log, 'INPUT_ALERT_CHANGED', level='WARNING' if snapshot['input_alert']!='NORMAL' else 'INFO',
                  previous_alert=self.last_input_alert, input_alert=snapshot['input_alert'], **fields)
            self.last_input_alert = snapshot['input_alert']

    def snapshot(self):
        with self.connect() as db:
            row = db.execute('SELECT * FROM monitor_readings ORDER BY id DESC LIMIT 1').fetchone()
            state = db.execute('SELECT * FROM monitor_state').fetchone()
            good = db.execute("SELECT received_utc FROM monitor_readings WHERE status='ACCEPTED' ORDER BY id DESC LIMIT 1").fetchone()
            recent = [dict(r) for r in db.execute('SELECT * FROM monitor_readings ORDER BY id DESC LIMIT 40')]
        age = time.time()-datetime.fromisoformat(row['received_utc']).timestamp() if row else time.time()-self.started
        valid_age = time.time()-datetime.fromisoformat(good[0]).timestamp() if good else time.time()-self.started
        stale = age > 3*self.interval
        if max(age,valid_age) > 10*self.interval:
            health = 'FAILED'
        elif stale or (row and row['status'] != 'ACCEPTED') or state['alert']=='ALERT' or valid_age > 3*self.interval:
            health = 'DEGRADED'
        elif row is None:
            health = 'RECOVERING'
        else:
            health = 'HEALTHY'
        current = row['accepted_value'] if row and not stale and row['status']=='ACCEPTED' else None
        return dict(health=health, alert=state['alert'],
                    input_alert='STALE_DATA' if stale else 'NO_VALID_INPUT' if valid_age > 3*self.interval else 'NORMAL',
                    valid_age_seconds=round(valid_age,2), data_status='STALE' if stale else row['status'] if row else 'WAITING',
                    current=current, latest=dict(row) if row else None, age_seconds=round(age,2), recent=recent,
                    interval=self.interval, mode='SYNTHETIC TEST' if self.demo else 'MODULE 6 ACCELERATED REPLAY')

    def worker(self):
        while True:
            try:
                self.tick()
            except Exception as exc:
                event(self.log, 'APPLICATION_ERROR', level='ERROR', component='Worker', exception_type=type(exc).__name__, database_path=str(self.path), error=repr(exc))
                os._exit(1)  # supervisor restarts the entire failed worker/server unit
            time.sleep(self.interval)

def create_app(monitor):
    app = Flask(__name__)
    @app.get('/')
    def dashboard():
        return render_template('dashboard.html', **monitor.snapshot())
    @app.get('/api/status')
    def status():
        return jsonify(monitor.snapshot())
    @app.get('/history')
    def archive():
        with monitor.connect() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM readings WHERE sensor_id='temperature' ORDER BY timestamp")]
        return render_template('history.html', rows=rows)
    @app.errorhandler(Exception)
    def error(exc):
        from werkzeug.exceptions import HTTPException
        if isinstance(exc, HTTPException):
            return exc
        event(monitor.log,'APPLICATION_ERROR',level='ERROR',error=repr(exc))
        return jsonify(health='FAILED',error='Request failed; inspect application log'),503
    return app

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime',default='runtime')
    parser.add_argument('--interval',type=float,default=2)
    parser.add_argument('--port',type=int,default=5000)
    parser.add_argument('--demo',action='store_true')
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error('interval must be positive')
    monitor = Monitor(args.runtime,args.interval,args.demo)
    threading.Thread(target=monitor.worker,daemon=True).start()
    serve(create_app(monitor),host='127.0.0.1',port=args.port,threads=4)
