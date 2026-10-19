import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from pathlib import Path

def setup(folder):
    Path(folder).mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('monitor.' + str(Path(folder).resolve()))
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(Path(folder)/'application.jsonl', maxBytes=2_000_000, backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
    return logger

def event(logger, name, level='INFO', **fields):
    logger.log(getattr(logging, level), json.dumps(dict(timestamp=datetime.now(timezone.utc).isoformat(), event=name, **fields)))
