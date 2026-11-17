"""Phone-only DeepSeek organization; never edits Harness session files."""
import sqlite3
import os
from contextlib import contextmanager
from pathlib import Path


class PhoneArchive:
    def __init__(self, path=None):
        self.path = Path(path or os.path.expanduser('~/.config/agent-phone/control/phone-archive.sqlite'))

    @contextmanager
    def db(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Create privately before SQLite opens it.
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        db = sqlite3.connect(self.path)
        try:
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS archived (session TEXT PRIMARY KEY)')
                yield db
        finally:
            db.close()

    def ids(self):
        with self.db() as db:
            return [r[0] for r in db.execute('SELECT session FROM archived')]

    def set(self, sid, archived):
        with self.db() as db:
            if archived:
                db.execute('INSERT OR IGNORE INTO archived VALUES (?)', (sid,))
            else:
                db.execute('DELETE FROM archived WHERE session=?', (sid,))
        return self.ids()
