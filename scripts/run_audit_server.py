from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app


if len(sys.argv) != 3:
    raise SystemExit("Uso: run_audit_server.py <database.db> <porta>")

database = Path(sys.argv[1]).resolve(strict=True)
port = int(sys.argv[2])
app = create_app(
    {
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}",
        "TESTING": False,
    }
)
app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
