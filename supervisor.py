"""One command supervises the combined dashboard and replay worker."""
import subprocess
import sys
import time
from pathlib import Path
from logging_config import setup, event

if __name__ == '__main__':
    args = sys.argv[1:]
    runtime = args[args.index('--runtime')+1] if '--runtime' in args else 'runtime'
    log = setup(runtime)
    child = None
    try:
        while True:
            child = subprocess.Popen([sys.executable,str(Path(__file__).with_name('app.py')),*args])
            Path(runtime,'child.pid').write_text(str(child.pid))
            event(log,'PROCESS_STARTED',pid=child.pid)
            code = child.wait()
            event(log,'PROCESS_INTERRUPTED',exit_code=code,pid=child.pid)
            event(log,'RESTART_SCHEDULED',delay_seconds=1)
            time.sleep(1)
    except KeyboardInterrupt:
        if child and child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
        event(log,'SUPERVISOR_STOPPED')
