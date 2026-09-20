import sqlite3
from pathlib import Path
from threading import RLock
from typing import Protocol
from ..models.domain import Case

class CaseRepository(Protocol):
    def get(self, case_id: str) -> Case | None: ...
    def save(self, case: Case) -> None: ...

class SQLiteCaseRepository:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute("CREATE TABLE IF NOT EXISTS investigations (id TEXT PRIMARY KEY, state TEXT NOT NULL)")
        self.connection.commit()

    def get(self, case_id: str):
        with self.lock:
            row = self.connection.execute("SELECT state FROM investigations WHERE id = ?", (case_id,)).fetchone()
            return Case.model_validate_json(row[0]) if row else None

    def save(self, case: Case):
        validated = Case.model_validate(case.model_dump(exclude_computed_fields=True))
        with self.lock, self.connection:
            self.connection.execute("INSERT INTO investigations VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET state=excluded.state",
                                    (case.investigation.id, validated.model_dump_json(exclude_computed_fields=True)))

    def close(self):
        self.connection.close()
