SOURCE_PROVIDER = "health_connect"
SUPPORTED_DATABASE_NAME = "health_connect_export.db"
SUPPORTED_TABLES = {
    "sleep_session_record_table",
    "exercise_session_record_table",
    "weight_record_table",
    "body_fat_record_table",
    "steps_record_table",
}
ARCHIVE_SUFFIXES = {".zip", ".db", ".sqlite", ".sqlite3"}
MAX_ARCHIVE_MEMBER_BYTES = 2_000_000_000
MAX_ARCHIVE_TOTAL_BYTES = 4_000_000_000
IMPORT_BATCH_SIZE = 500

