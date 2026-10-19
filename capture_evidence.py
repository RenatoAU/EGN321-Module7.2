"""Real HTTP + browser evidence with synthetic fault inputs; never modifies source CSV."""
import json
from contextlib import nullcontext
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
if '--no-browser' not in sys.argv:
    from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent
os.chdir(ROOT)
runtime=ROOT/'test_runtime'
evidence=ROOT/'evidence'
if runtime.exists():
    raise SystemExit('test_runtime already exists: rename it before a fresh test.')
runtime.mkdir()
evidence.mkdir(exist_ok=True)

def control(**fields):
    temporary=runtime/'control.tmp'
    temporary.write_text(json.dumps(fields))
    temporary.replace(runtime/'control.json')

def status():
    with urllib.request.urlopen('http://127.0.0.1:5057/api/status',timeout=2) as response:
        return json.load(response)

def wait_for(predicate,timeout=15):
    end=time.time()+timeout
    while time.time()<end:
        try:
            data=status()
            if predicate(data): return data
        except (OSError,ValueError): pass
        time.sleep(.1)
    raise AssertionError('Condition timed out')

control(value=24)
output=open(evidence/'process_output.txt','w')
process=subprocess.Popen([sys.executable,'supervisor.py','--runtime',str(runtime),'--interval','0.5','--port','5057','--demo'],stdout=output,stderr=subprocess.STDOUT)
results={}
try:
    with (nullcontext(None) if '--no-browser' in sys.argv else sync_playwright()) as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox']) if p else None
        page=browser.new_page(viewport={'width':1280,'height':900}) if browser else None
        def capture(name,data):
            results[name]=data
            (evidence/(name+'.json')).write_text(json.dumps(data,indent=2))
            with urllib.request.urlopen('http://127.0.0.1:5057/') as response:
                (evidence/(name+'.html')).write_bytes(response.read())
            if page:
                page.goto('http://127.0.0.1:5057/')
                page.screenshot(path=str(evidence/(name+'.png')))
        capture('01_dashboard_healthy',wait_for(lambda d:d['health']=='HEALTHY'))
        with urllib.request.urlopen('http://127.0.0.1:5057/history') as response:
            (evidence/'02_original_history.html').write_bytes(response.read())
        if page:
            page.goto('http://127.0.0.1:5057/history')
            page.screenshot(path=str(evidence/'02_original_history.png'))
        control(value=32)
        capture('03_alert_active',wait_for(lambda d:d['alert']=='ALERT'))
        control(value=27)
        capture('04_alert_cleared',wait_for(lambda d:d['alert']=='NORMAL'))
        control(pause=True)
        capture('05_stale',wait_for(lambda d:d['data_status']=='STALE'))
        capture('06_failed',wait_for(lambda d:d['health']=='FAILED'))
        control(value='',status='MISSING')
        capture('07_missing',wait_for(lambda d:d['data_status']=='MISSING'))
        control(value=24)
        wait_for(lambda d:d['health']=='HEALTHY')
        old_pid=int((runtime/'child.pid').read_text())
        with sqlite3.connect(runtime/'monitor.db') as db:
            before=db.execute('SELECT COUNT(*) FROM monitor_readings').fetchone()[0]
            archive_before=db.execute('SELECT COUNT(*) FROM readings').fetchone()[0]
        os.kill(old_pid,signal.SIGKILL if hasattr(signal,'SIGKILL') else signal.SIGTERM)
        recovered=wait_for(lambda d:int((runtime/'child.pid').read_text())!=old_pid and d['health']=='HEALTHY')
        capture('08_recovered_healthy',recovered)
        with sqlite3.connect(runtime/'monitor.db') as db:
            integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
            after=db.execute('SELECT COUNT(*) FROM monitor_readings').fetchone()[0]
            archive_after=db.execute('SELECT COUNT(*) FROM readings').fetchone()[0]
        assert after>=before and archive_before==archive_after==8780 and integrity=='ok'
        results['recovery']=dict(old_pid=old_pid,new_pid=int((runtime/'child.pid').read_text()),before=before,after=after,archive_rows=archive_after,integrity=integrity)
        if browser: browser.close()
    log=(runtime/'application.jsonl').read_text()
    for name in ('STARTUP','READING_PROCESSED','ALERT_ACTIVATED','ALERT_CLEARED','MISSING_OR_STALE_DATA','PROCESS_INTERRUPTED','RESTART_SCHEDULED','RECOVERY_READY'):
        assert name in log,name
    (evidence/'verification.json').write_text(json.dumps(results,indent=2))
    shutil.copy2(runtime/'application.jsonl',evidence/'application.jsonl')
    with sqlite3.connect(runtime/'monitor.db') as source,sqlite3.connect(evidence/'verified_monitor.db') as target:
        source.backup(target)
    print('PASS: real HTTP dashboard, alert/clear, stale/missing, FAILED, killed child, automatic restart, SQLite integrity and final HEALTHY. Evidence captured in Linux with synthetic inputs at 0.5 seconds.')
finally:
    child_file=runtime/'child.pid'
    process.terminate()
    process.wait(timeout=10)
    if child_file.exists():
        try: os.kill(int(child_file.read_text()),signal.SIGTERM)
        except ProcessLookupError: pass
    output.close()
