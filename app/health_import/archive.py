from __future__ import annotations

import shutil
import zipfile
from pathlib import Path, PurePosixPath

from app.health_import.constants import (
    MAX_ARCHIVE_MEMBER_BYTES,
    MAX_ARCHIVE_TOTAL_BYTES,
    SUPPORTED_DATABASE_NAME,
)


class HealthArchiveError(ValueError):
    pass


def _is_safe_member(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts


def prepare_database(source: Path, work_dir: Path) -> Path:
    source = source.resolve(strict=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    target = work_dir / SUPPORTED_DATABASE_NAME
    if source.suffix.casefold() != ".zip":
        if source.name.casefold() != SUPPORTED_DATABASE_NAME:
            raise HealthArchiveError(
                "Selecione um ZIP do Health Connect ou health_connect_export.db."
            )
        shutil.copy2(source, target)
        return target

    try:
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
            if any(not _is_safe_member(item.filename) for item in members):
                raise HealthArchiveError("O ZIP contém caminhos inseguros.")
            if any(item.file_size > MAX_ARCHIVE_MEMBER_BYTES for item in members):
                raise HealthArchiveError("O ZIP contém um arquivo grande demais.")
            if sum(item.file_size for item in members) > MAX_ARCHIVE_TOTAL_BYTES:
                raise HealthArchiveError("O conteúdo do ZIP excede o limite seguro.")
            databases = [
                item
                for item in members
                if not item.is_dir()
                and PurePosixPath(item.filename.replace("\\", "/")).name.casefold()
                == SUPPORTED_DATABASE_NAME
            ]
            if len(databases) != 1:
                raise HealthArchiveError(
                    "O ZIP deve conter exatamente um health_connect_export.db."
                )
            with archive.open(databases[0]) as input_file, target.open("wb") as output:
                shutil.copyfileobj(input_file, output, length=1024 * 1024)
    except zipfile.BadZipFile as exc:
        raise HealthArchiveError("O arquivo ZIP está corrompido.") from exc
    return target

