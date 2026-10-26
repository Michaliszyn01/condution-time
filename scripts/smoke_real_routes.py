from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: smoke_real_routes.py <condution_time.db>")
    database = Path(sys.argv[1]).resolve(strict=True)
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}",
        }
    )
    routes = (
        "/",
        "/registrar",
        "/estudo",
        "/perfil",
        "/treino",
        "/sono",
        "/computador",
        "/alimentacao",
        "/historico",
        "/health",
        "/api/profile",
        "/api/profile/study",
        "/api/profile/physical",
        "/api/profile/computer",
    )
    with app.test_client() as client:
        statuses = {route: client.get(route).status_code for route in routes}
    print(json.dumps(statuses, ensure_ascii=False, sort_keys=True))
    return 0 if all(value == 200 for value in statuses.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
