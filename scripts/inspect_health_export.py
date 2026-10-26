from __future__ import annotations

import sqlite3
import sys
import zipfile
from pathlib import Path, PurePosixPath


RELEVANT_TERMS = (
    "sleep",
    "exercise",
    "workout",
    "training",
    "weight",
    "height",
    "body",
    "step",
    "distance",
    "calor",
    "heart",
    "vo2",
    "oxygen",
    "record",
    "metadata",
)


def safe_member(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: inspect_health_export.py <arquivo.zip>")
    archive_path = Path(sys.argv[1])
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        unsafe = [item.filename for item in members if not safe_member(item.filename)]
        databases = [
            item
            for item in members
            if safe_member(item.filename)
            and PurePosixPath(item.filename.replace("\\", "/")).name.casefold()
            == "health_connect_export.db"
        ]
        if unsafe:
            raise RuntimeError(f"ZIP contém caminhos inseguros: {unsafe!r}")
        if len(databases) != 1:
            raise RuntimeError(
                f"Esperado um health_connect_export.db; encontrados {len(databases)}."
            )
        member = databases[0]
        temp_root = Path.cwd() / ".desktop-smoke"
        temp_root.mkdir(exist_ok=True)
        database_path = temp_root / "health_connect_inspect.db"
        if database_path.exists():
            database_path.unlink()
        try:
            with archive.open(member) as source, database_path.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
            uri = f"file:{database_path.as_posix()}?mode=ro"
            with sqlite3.connect(uri, uri=True) as connection:
                tables = [
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                        "ORDER BY name"
                    )
                ]
                counts = {}
                relevant_schemas = {}
                for table in tables:
                    counts[table] = int(
                        connection.execute(
                            f'SELECT COUNT(*) FROM "{table}"'
                        ).fetchone()[0]
                    )
                    if any(term in table.casefold() for term in RELEVANT_TERMS):
                        relevant_schemas[table] = [
                            f"{row[1]}:{row[2] or '?'}"
                            for row in connection.execute(
                                f'PRAGMA table_info("{table}")'
                            )
                        ]
        finally:
            try:
                database_path.unlink(missing_ok=True)
            except OSError:
                pass
    print(f"ARCHIVE={archive_path.name}")
    print(f"ARCHIVE_SIZE={archive_path.stat().st_size}")
    print(f"DATABASE_MEMBER={member.filename}")
    print(f"DATABASE_SIZE={member.file_size}")
    print("TABLES")
    for table in tables:
        print(f"{table}\t{counts[table]}")
    print("RELEVANT_SCHEMAS")
    for table, columns in relevant_schemas.items():
        print(f"{table}\t{', '.join(columns)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
