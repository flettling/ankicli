import pickle
import sqlite3
from pathlib import Path
from typing import Any, Optional

import pytest


def _write_profile_db(base: Path, profiles: dict[str, dict[str, Any]], global_config: Optional[dict[str, Any]] = None) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    db_path = base / "prefs21.db"
    con = sqlite3.connect(db_path)
    try:
        con.execute("create table profiles (name text primary key, data blob not null)")
        con.execute(
            "insert into profiles (name, data) values (?, ?)",
            ("_global", pickle.dumps(global_config or {}, protocol=pickle.HIGHEST_PROTOCOL)),
        )
        for name, data in profiles.items():
            con.execute(
                "insert into profiles (name, data) values (?, ?)",
                (name, pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)),
            )
        con.commit()
    finally:
        con.close()
    return db_path


@pytest.fixture
def write_profile_db():
    return _write_profile_db
