import os
import secrets


def _positive_int_from_env(name: str, default: int) -> int:
    """Lê metas positivas sem deixar uma variável inválida quebrar a aplicação."""
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


class Config:
    """Configuração padrão, substituível por variáveis de ambiente."""

    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///condution_time.db",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False
    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "America/Sao_Paulo")
    DEFAULT_SLEEP_TARGET_MINUTES = _positive_int_from_env(
        "DEFAULT_SLEEP_TARGET_MINUTES",
        480,
    )
    DEFAULT_HYDRATION_TARGET_ML = _positive_int_from_env(
        "DEFAULT_HYDRATION_TARGET_ML",
        2000,
    )
    DEFAULT_DISTRACTION_LIMIT_SECONDS = _positive_int_from_env(
        "DEFAULT_DISTRACTION_LIMIT_SECONDS",
        7200,
    )
    MONITOR_SAMPLE_INTERVAL_SECONDS = _positive_int_from_env(
        "MONITOR_SAMPLE_INTERVAL_SECONDS",
        2,
    )
    IDLE_THRESHOLD_SECONDS = _positive_int_from_env(
        "IDLE_THRESHOLD_SECONDS",
        300,
    )
    COMPUTER_DATA_RETENTION_DAYS = _positive_int_from_env(
        "COMPUTER_DATA_RETENTION_DAYS",
        90,
    )
