"""History Builder: timestamped multi-sensor SQLite logging and gap reports."""
import argparse
import csv
import json
import math
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

INTERVAL = 60
# Bounds are classroom validation rules, not sensor calibration specifications.
SENSORS = {
    'temperature': ('temperature_c', '°C', 0, 50),
    'humidity': ('humidity_percent', '%', 0, 100),
    'light': ('light_raw', 'raw units', None, None),
    'distance': ('distance_cm', 'cm', 0, None),
    'potentiometer': ('potentiometer_percent', '%', 0, 100),
}


def connect(path):
    """Create tables and a sensor/time index; preserve source value text."""
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS sensors (
        sensor_id TEXT PRIMARY KEY, unit TEXT NOT NULL,
        interval_seconds INTEGER NOT NULL CHECK(interval_seconds>0));
      CREATE TABLE IF NOT EXISTS readings (
        sensor_id TEXT NOT NULL REFERENCES sensors(sensor_id),
        sample_number INTEGER NOT NULL CHECK(sample_number>0),
        timestamp TEXT NOT NULL, raw_value TEXT NOT NULL,
        accepted_value REAL, source_status TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('ACCEPTED','REJECTED','INVALID','MISSING')),
        timestamp_source TEXT NOT NULL, source_file TEXT NOT NULL,
        PRIMARY KEY(sensor_id,timestamp), UNIQUE(sensor_id,sample_number));
      CREATE INDEX IF NOT EXISTS readings_time ON readings(sensor_id,timestamp);
    ''')
    return db


def validate(raw, source_status, lower, upper):
    """Retain rejected/missing values; never replace them with an estimate."""
    if not raw.strip() or source_status == 'MISSING':
        return None, 'MISSING'
    try:
        value = float(raw)
    except ValueError:
        return None, 'INVALID'
    if not math.isfinite(value):
        return None, 'INVALID'
    if source_status != 'OK' or (lower is not None and value < lower) or (upper is not None and value > upper):
        return None, 'REJECTED'
    return value, 'ACCEPTED'


def import_csv(db, path):
    """Use supplied timestamps exactly; refuse inconsistent replay grid/duplicates."""
    with open(path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError('Empty dataset')
    previous = None
    origin = datetime.fromisoformat(rows[0]['timestamp'])
    if origin.tzinfo is not None:
        raise ValueError('This dataset uses timezone-unspecified timestamps; use a separate timezone-aware import policy for other data.')
    with db:
        for sensor, (_, unit, _, _) in SENSORS.items():
            db.execute('INSERT OR IGNORE INTO sensors VALUES (?,?,?)', (sensor, unit, INTERVAL))
        for row in rows:
            stamp = datetime.fromisoformat(row['timestamp'])
            if stamp.tzinfo is not None or (previous is not None and stamp <= previous):
                raise ValueError('Timestamps must be increasing and timezone-unspecified')
            if (stamp-origin).total_seconds() % INTERVAL:
                raise ValueError('Timestamp is off the expected 60-second grid')
            n = int(row['sample_number'])
            for sensor, (column, _, lower, upper) in SENSORS.items():
                raw, source_status = row[column], row[sensor+'_status']
                accepted, status = validate(raw, source_status, lower, upper)
                db.execute('INSERT INTO readings VALUES (?,?,?,?,?,?,?,?,?)',
                           (sensor, n, stamp.isoformat(), raw, accepted, source_status, status,
                            'provided_csv_timezone_unspecified', Path(path).name))
            previous = stamp


def query_view(db, sensor, view):
    """Inclusive time windows are anchored to the latest database timestamp."""
    bounds = db.execute('SELECT MIN(timestamp),MAX(timestamp) FROM readings').fetchone()
    if bounds[0] is None:
        raise ValueError('No stored readings')
    origin, end = map(datetime.fromisoformat, bounds)
    seconds = {'last_hour': 3600, 'last_day': 86400}
    requested = end-timedelta(seconds=seconds[view]) if view in seconds else origin
    start = max(requested, origin)
    rows = db.execute('SELECT * FROM readings WHERE sensor_id=? AND timestamp>=? AND timestamp<=? ORDER BY timestamp',
                      (sensor, start.isoformat(), end.isoformat())).fetchall()
    interval = db.execute('SELECT interval_seconds FROM sensors WHERE sensor_id=?', (sensor,)).fetchone()[0]
    return start, end, requested, rows, interval, origin


def completeness(start, end, rows, interval, origin):
    """Count received versus absent slots, including absent boundary slots."""
    first = math.ceil((start-origin).total_seconds()/interval)
    last = math.floor((end-origin).total_seconds()/interval)
    by_time = {r['timestamp']: r for r in rows}
    gaps, run = [], []
    received = accepted = rejected = 0
    for i in range(first, last+1):
        stamp = origin+timedelta(seconds=i*interval)
        r = by_time.get(stamp.isoformat())
        if r is None or r['status']=='MISSING':
            run.append(stamp)
        else:
            received += 1
            accepted += r['status']=='ACCEPTED'
            rejected += r['status'] in ('REJECTED','INVALID')
            if run:
                gaps.append(run); run=[]
    if run:
        gaps.append(run)
    expected = max(0, last-first+1)
    separation = max(((datetime.fromisoformat(b['timestamp'])-datetime.fromisoformat(a['timestamp'])).total_seconds()
                      for a,b in zip(rows, rows[1:])), default=0)
    return dict(expected_readings=expected, received_readings=received, missing_readings=expected-received,
                accepted_readings=accepted, rejected_or_invalid_readings=rejected,
                completeness_percent=100*received/expected if expected else None,
                largest_missing_interval_seconds=max((len(g)*interval for g in gaps), default=0),
                largest_between_stored_readings_seconds=separation,
                gaps=[dict(first_missing_timestamp=g[0].isoformat(), last_missing_timestamp=g[-1].isoformat(),
                           missing_readings=len(g), missing_duration_seconds=len(g)*interval) for g in gaps])


def plot_segments(rows, interval):
    """NaN breaks prevent lines crossing absent, rejected, or missing readings."""
    xs, ys, previous = [], [], None
    for row in rows:
        stamp = datetime.fromisoformat(row['timestamp'])
        if previous is not None and (stamp-previous).total_seconds()>interval:
            xs.append(previous+timedelta(seconds=interval)); ys.append(float('nan'))
        xs.append(stamp)
        ys.append(row['accepted_value'] if row['accepted_value'] is not None else float('nan'))
        previous=stamp
    return xs, ys


def plot(db, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    fig, axes = plt.subplots(5,1,figsize=(12,12),sharex=True)
    for ax, sensor in zip(axes, SENSORS):
        start,end,_,rows,interval,origin=query_view(db,sensor,'full_history')
        stats=completeness(start,end,rows,interval,origin)
        xs,ys=plot_segments(rows,interval)
        ax.plot(xs,ys,linewidth=1,label='Accepted')
        bad=[r for r in rows if r['status']=='REJECTED' and math.isfinite(float(r['raw_value']))]
        if bad:
            ax.scatter([datetime.fromisoformat(r['timestamp']) for r in bad], [float(r['raw_value']) for r in bad], color='red',marker='x',label='Rejected')
        for gap in stats['gaps']:
            ax.axvspan(datetime.fromisoformat(gap['first_missing_timestamp'])-timedelta(seconds=interval/2),
                       datetime.fromisoformat(gap['last_missing_timestamp'])+timedelta(seconds=interval/2),color='gray',alpha=.22)
        ax.set_ylabel(SENSORS[sensor][1]); ax.set_title(sensor.title(),loc='left',fontsize=10)
        ax.grid(alpha=.2); ax.legend(loc='upper right',fontsize=8)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%b %d\n%H:%M'))
    axes[-1].set_xlabel('Timestamp supplied in CSV (timezone unspecified); shaded bands = absent readings')
    fig.suptitle('Module 6 sensor history — missing intervals preserved')
    fig.tight_layout(rect=[0,0,1,.97]); fig.savefig(output,dpi=160); plt.close(fig)


def build(source, output):
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    path=output/'sensor_history.db'
    if path.exists():
        raise FileExistsError('Use a fresh output folder; existing databases are not overwritten.')
    with connect(path) as db:
        import_csv(db,source)
        for view in ('last_hour','last_day','full_history'):
            report={'view':view,'timestamp_source':'Provided CSV timestamps; timezone unspecified; NOT reconstructed','sensors':{}}
            lines=[f'# {view.replace("_"," ").title()}', '', 'Timestamps are supplied by the CSV. Their timezone is unspecified.', '']
            lines += ['| Sensor | Expected | Received | Missing | Accepted | Rejected/invalid | Completeness | Largest missing interval | Largest stored separation |',
                      '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
            all_rows=[]
            for sensor in SENSORS:
                start,end,requested,rows,interval,origin=query_view(db,sensor,view)
                stats=completeness(start,end,rows,interval,origin)
                report.update(requested_start=requested.isoformat(),analyzed_start=start.isoformat(),end=end.isoformat(),interval_seconds=interval)
                report['sensors'][sensor]=stats
                all_rows.extend(rows)
                lines.append(f"| {sensor} | {stats['expected_readings']} | {stats['received_readings']} | {stats['missing_readings']} | {stats['accepted_readings']} | {stats['rejected_or_invalid_readings']} | {stats['completeness_percent']:.2f}% | {stats['largest_missing_interval_seconds']/60:g} min | {stats['largest_between_stored_readings_seconds']/60:g} min |")
            lines += ['',f'Inclusive window: {start.isoformat()} through {end.isoformat()}.',
                      'End is the latest stored timestamp, not the current clock. Inclusive windows include both endpoints (61 one-minute slots in one hour).',
                      'Counts are per sensor; five channels must not be mistaken for five sampling times.',
                      'Missing interval duration counts absent scheduled slots; stored separation includes the interval between neighboring observations.',
                      '', '## Gap details by sensor', '', '```json',json.dumps(report['sensors'],indent=2),'```', '',
                      'No missing measurements were filled, interpolated, smoothed, or averaged. Rejected readings are received but unusable under the stated acceptance rule.']
            (output/(view+'.md')).write_text('\n'.join(lines))
            (output/(view+'.json')).write_text(json.dumps(report,indent=2))
            with open(output/(view+'.csv'),'w',newline='') as f:
                writer=csv.writer(f); writer.writerow(all_rows[0].keys()); writer.writerows(tuple(r) for r in all_rows)
        plot(db,output/'full_history.png')
    print('Created SQLite database, three reports and query CSVs, and five-sensor plot:',output)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',default='data/module6_sample_sensor_history.csv')
    p.add_argument('--output',default='reports')
    a=p.parse_args(); build(a.source,a.output)
