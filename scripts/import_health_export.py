from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.health_import import HealthImporter


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(
            "Uso: import_health_export.py <arquivo.zip|db> <banco-condution-time.db>"
        )
    source = Path(sys.argv[1]).resolve(strict=True)
    target = Path(sys.argv[2]).resolve()
    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{target.as_posix()}",
            "INSTANCE_PATH": str(target.parent),
        }
    )
    result = HealthImporter(app).import_file(source)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
