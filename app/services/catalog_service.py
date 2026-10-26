from __future__ import annotations

import re
import unicodedata


def _key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.casefold()).strip("_") or "other"


SUBJECT_CATALOG = {
    "matematica": ("Matemática", "blue", "#246BFD"),
    "historia": ("História", "amber", "#D97706"),
    "geografia": ("Geografia", "teal", "#0F9F8F"),
    "portugues": ("Português", "violet", "#7C3AED"),
    "linguagens": ("Linguagens", "violet", "#7C3AED"),
    "literatura": ("Literatura", "rose", "#E64980"),
    "biologia": ("Biologia", "green", "#22A06B"),
    "fisica": ("Física", "indigo", "#4F46E5"),
    "quimica": ("Química", "cyan", "#0891B2"),
    "filosofia": ("Filosofia", "slate", "#64748B"),
    "sociologia": ("Sociologia", "orange", "#EA580C"),
    "ingles": ("Inglês", "red", "#DC2626"),
    "redacao": ("Redação", "pink", "#DB2777"),
    "programacao": ("Programação", "emerald", "#059669"),
    "other": ("Outro", "gray", "#667085"),
}


def subject_catalog_item(subject: str) -> dict:
    subject_key = _key(subject)
    configured = SUBJECT_CATALOG.get(subject_key)
    if configured is None:
        subject_key = "other"
        configured = SUBJECT_CATALOG[subject_key]
        display_name = " ".join((subject or "").split()) or configured[0]
    else:
        display_name = configured[0]
    return {
        "subject_key": subject_key,
        "display_name": display_name,
        "color_key": configured[1],
        "color": configured[2],
    }


# AndroidX Health Connect ExerciseSessionRecord (IDs 0-83). Este catálogo é
# mantido somente para compatibilidade com integrações AndroidX. O SQLite
# exportado pelo Health Connect NÃO usa estes valores.
ANDROIDX_EXERCISE_SESSION_TYPES = {
    0: ("other", "Outro", "activity", "#667085"),
    2: ("badminton", "Badminton", "medal", "#F59E0B"),
    4: ("baseball", "Beisebol", "circle-dot", "#EA580C"),
    5: ("basketball", "Basquete", "circle-dot", "#F97316"),
    8: ("cycling", "Ciclismo", "bike", "#0EA5E9"),
    9: ("stationary_cycling", "Bicicleta ergométrica", "bike", "#0284C7"),
    10: ("functional_training", "Treinamento funcional", "activity", "#7C3AED"),
    11: ("boxing", "Boxe", "badge", "#DC2626"),
    13: ("calisthenics", "Exercício livre", "person-standing", "#8B5CF6"),
    14: ("cricket", "Críquete", "trophy", "#65A30D"),
    16: ("dance", "Dança", "music-2", "#DB2777"),
    25: ("elliptical", "Elíptico", "activity", "#0891B2"),
    26: ("exercise_class", "Aula de exercício", "users", "#7C3AED"),
    27: ("fencing", "Esgrima", "medal", "#64748B"),
    28: ("american_football", "Futebol americano", "trophy", "#B45309"),
    29: ("australian_football", "Futebol australiano", "trophy", "#B45309"),
    31: ("frisbee", "Frisbee", "disc-3", "#0D9488"),
    32: ("golf", "Golfe", "flag", "#16A34A"),
    33: ("guided_breathing", "Respiração guiada", "wind", "#06B6D4"),
    34: ("gymnastics", "Ginástica", "person-standing", "#8B5CF6"),
    35: ("handball", "Handebol", "circle-dot", "#F97316"),
    36: ("hiit", "HIIT", "zap", "#DC2626"),
    37: ("hiking", "Trilha", "mountain", "#16A34A"),
    38: ("ice_hockey", "Hóquei no gelo", "trophy", "#0284C7"),
    39: ("ice_skating", "Patinação no gelo", "snowflake", "#0EA5E9"),
    44: ("martial_arts", "Artes marciais", "medal", "#DC2626"),
    46: ("paddling", "Remada", "waves", "#0891B2"),
    47: ("paragliding", "Parapente", "wind", "#0EA5E9"),
    48: ("pilates", "Pilates", "person-standing", "#7C3AED"),
    50: ("racquetball", "Raquetebol", "circle-dot", "#F59E0B"),
    51: ("rock_climbing", "Escalada", "mountain", "#92400E"),
    52: ("roller_hockey", "Hóquei sobre patins", "trophy", "#F97316"),
    53: ("rowing", "Remo", "waves", "#0891B2"),
    54: ("rowing_machine", "Remo ergométrico", "activity", "#0E7490"),
    55: ("rugby", "Rúgbi", "trophy", "#65A30D"),
    56: ("running", "Corrida", "footprints", "#22A06B"),
    57: ("treadmill", "Esteira", "footprints", "#16A34A"),
    58: ("sailing", "Vela", "sailboat", "#0284C7"),
    59: ("scuba_diving", "Mergulho", "waves", "#0369A1"),
    60: ("skating", "Patinação", "move", "#8B5CF6"),
    61: ("skiing", "Esqui", "snowflake", "#0284C7"),
    62: ("snowboarding", "Snowboard", "snowflake", "#2563EB"),
    63: ("snowshoeing", "Caminhada na neve", "footprints", "#0EA5E9"),
    64: ("soccer", "Futebol", "circle-dot", "#16A34A"),
    65: ("softball", "Softbol", "circle-dot", "#EA580C"),
    66: ("squash", "Squash", "circle-dot", "#F59E0B"),
    68: ("stairs", "Escada", "stairs", "#EA580C"),
    69: ("stair_machine", "Máquina de escada", "stairs", "#C2410C"),
    70: ("strength", "Musculação", "dumbbell", "#246BFD"),
    71: ("stretching", "Alongamento", "person-standing", "#7C3AED"),
    72: ("surfing", "Surfe", "waves", "#0284C7"),
    73: ("open_water_swimming", "Natação em águas abertas", "waves", "#0369A1"),
    74: ("swimming", "Natação", "waves", "#0EA5E9"),
    75: ("table_tennis", "Tênis de mesa", "circle-dot", "#F59E0B"),
    76: ("tennis", "Tênis", "circle-dot", "#D97706"),
    78: ("volleyball", "Vôlei", "circle-dot", "#F97316"),
    79: ("walking", "Caminhada", "footprints", "#22A06B"),
    80: ("water_polo", "Polo aquático", "waves", "#0284C7"),
    81: ("weightlifting", "Levantamento de peso", "dumbbell", "#1D4ED8"),
    82: ("wheelchair", "Cadeira de rodas", "accessibility", "#64748B"),
    83: ("yoga", "Yoga", "person-standing", "#9333EA"),
}

# android.health.connect.datatypes.ExerciseSessionType (API nativa da
# plataforma). Estes são os valores persistidos em health_connect_export.db.
PLATFORM_EXERCISE_SESSION_TYPES = {
    0: ("other", "Desconhecido", "activity", "#667085"),
    1: ("badminton", "Badminton", "medal", "#F59E0B"),
    2: ("baseball", "Beisebol", "circle-dot", "#EA580C"),
    3: ("basketball", "Basquete", "circle-dot", "#F97316"),
    4: ("cycling", "Ciclismo", "bike", "#0EA5E9"),
    5: ("stationary_cycling", "Bicicleta ergométrica", "bike", "#0284C7"),
    6: ("boot_camp", "Boot camp", "activity", "#7C3AED"),
    7: ("boxing", "Boxe", "badge", "#DC2626"),
    8: ("calisthenics", "Calistenia", "person-standing", "#8B5CF6"),
    9: ("cricket", "Críquete", "trophy", "#65A30D"),
    10: ("dance", "Dança", "music-2", "#DB2777"),
    11: ("exercise_class", "Aula de exercício", "users", "#7C3AED"),
    12: ("fencing", "Esgrima", "medal", "#64748B"),
    13: ("american_football", "Futebol americano", "trophy", "#B45309"),
    14: ("australian_football", "Futebol australiano", "trophy", "#B45309"),
    15: ("frisbee", "Frisbee", "disc-3", "#0D9488"),
    16: ("golf", "Golfe", "flag", "#16A34A"),
    17: ("guided_breathing", "Respiração guiada", "wind", "#06B6D4"),
    18: ("gymnastics", "Ginástica", "person-standing", "#8B5CF6"),
    19: ("handball", "Handebol", "circle-dot", "#F97316"),
    20: ("hiit", "HIIT", "zap", "#DC2626"),
    21: ("hiking", "Trilha", "mountain", "#16A34A"),
    22: ("ice_hockey", "Hóquei no gelo", "trophy", "#0284C7"),
    23: ("ice_skating", "Patinação no gelo", "snowflake", "#0EA5E9"),
    24: ("martial_arts", "Artes marciais", "medal", "#DC2626"),
    25: ("paddling", "Remo com pá", "waves", "#0891B2"),
    26: ("paragliding", "Parapente", "wind", "#0EA5E9"),
    27: ("pilates", "Pilates", "person-standing", "#7C3AED"),
    28: ("racquetball", "Raquetebol", "circle-dot", "#F59E0B"),
    29: ("rock_climbing", "Escalada", "mountain", "#92400E"),
    30: ("roller_hockey", "Hóquei com patins", "trophy", "#F97316"),
    31: ("rowing", "Remo", "waves", "#0891B2"),
    32: ("rugby", "Rugby", "trophy", "#65A30D"),
    33: ("running", "Corrida", "footprints", "#22A06B"),
    34: ("treadmill", "Corrida na esteira", "footprints", "#16A34A"),
    35: ("sailing", "Vela", "sailboat", "#0284C7"),
    36: ("scuba_diving", "Mergulho", "waves", "#0369A1"),
    37: ("skating", "Patinação", "move", "#8B5CF6"),
    38: ("skiing", "Esqui", "snowflake", "#0284C7"),
    39: ("snowboarding", "Snowboard", "snowflake", "#2563EB"),
    40: ("snowshoeing", "Caminhada com raquetes de neve", "footprints", "#0EA5E9"),
    41: ("soccer", "Futebol", "circle-dot", "#16A34A"),
    42: ("softball", "Softbol", "circle-dot", "#EA580C"),
    43: ("squash", "Squash", "circle-dot", "#F59E0B"),
    44: ("stairs", "Subida de escadas", "stairs", "#EA580C"),
    45: ("strength", "Treino de força", "dumbbell", "#246BFD"),
    46: ("stretching", "Alongamento", "person-standing", "#7C3AED"),
    47: ("surfing", "Surfe", "waves", "#0284C7"),
    48: ("open_water_swimming", "Natação em águas abertas", "waves", "#0369A1"),
    49: ("swimming", "Natação em piscina", "waves", "#0EA5E9"),
    50: ("table_tennis", "Tênis de mesa", "circle-dot", "#F59E0B"),
    51: ("tennis", "Tênis", "circle-dot", "#D97706"),
    52: ("volleyball", "Vôlei", "circle-dot", "#F97316"),
    53: ("walking", "Caminhada", "footprints", "#22A06B"),
    54: ("water_polo", "Polo aquático", "waves", "#0284C7"),
    55: ("weightlifting", "Levantamento de peso", "dumbbell", "#1D4ED8"),
    56: ("wheelchair", "Cadeira de rodas", "accessibility", "#64748B"),
    57: ("yoga", "Yoga", "person-standing", "#9333EA"),
    58: ("other", "Outro treino", "activity", "#667085"),
    59: ("stair_machine", "Máquina de escadas", "stairs", "#C2410C"),
    60: ("elliptical", "Elíptico", "activity", "#0891B2"),
    61: ("rowing_machine", "Máquina de remo", "activity", "#0E7490"),
}

# Nome histórico usado por serviços internos. Daqui em diante ele representa o
# catálogo correto para o banco exportado pela API nativa.
EXERCISE_TYPES = PLATFORM_EXERCISE_SESSION_TYPES

TRAINING_ALIASES = {
    "Musculação": "strength",
    "Corrida": "running",
    "Caminhada": "walking",
    "Natação": "swimming",
    "Ciclismo": "cycling",
    "Esporte": "sport",
    "Mobilidade": "mobility",
    "Outro": "other",
}
MANUAL_TRAINING_TYPES = {
    "sport": ("Esporte", "trophy", "#F97316"),
    "mobility": ("Mobilidade", "person-standing", "#7C3AED"),
    "futsal": ("Futsal", "circle-dot", "#16A34A"),
    "circuit": ("Circuito", "refresh-cw", "#7C3AED"),
}


def exercise_catalog_item(code: int | None = None, key: str | None = None) -> dict:
    if code is not None and code in PLATFORM_EXERCISE_SESSION_TYPES:
        internal_key, label, icon, color = PLATFORM_EXERCISE_SESSION_TYPES[code]
        return {
            "training_key": internal_key,
            "display_name": label,
            "icon": icon,
            "color": color,
            "recognized": True,
        }
    if code is not None:
        return {
            "training_key": "other",
            "display_name": "Outro",
            "icon": "activity",
            "color": "#667085",
            "recognized": False,
        }
    normalized = TRAINING_ALIASES.get(key or "", key or "other")
    for internal_key, label, icon, color in PLATFORM_EXERCISE_SESSION_TYPES.values():
        if internal_key == normalized:
            return {
                "training_key": internal_key,
                "display_name": label,
                "icon": icon,
                "color": color,
                "recognized": True,
            }
    if normalized in MANUAL_TRAINING_TYPES:
        label, icon, color = MANUAL_TRAINING_TYPES[normalized]
        return {
            "training_key": normalized,
            "display_name": label,
            "icon": icon,
            "color": color,
            "recognized": True,
        }
    return {
        "training_key": "other",
        "display_name": "Outro",
        "icon": "activity",
        "color": "#667085",
        "recognized": False,
    }


def manual_training_options() -> list[dict]:
    preferred = (
        "strength", "running", "treadmill", "walking", "cycling",
        "stationary_cycling", "swimming", "functional_training", "soccer",
        "futsal", "basketball", "volleyball", "tennis", "table_tennis",
        "badminton", "elliptical", "rowing", "stairs", "hiking",
        "snowboarding", "skiing", "yoga", "pilates", "stretching", "dance",
        "boxing", "martial_arts", "hiit", "circuit", "calisthenics", "other",
    )
    by_key = {
        value[0]: {
            "value": value[0],
            "label": value[1],
            "icon": value[2],
            "color": value[3],
        }
        for value in PLATFORM_EXERCISE_SESSION_TYPES.values()
    }
    by_key.update(
        {
            "futsal": {"value": "futsal", "label": "Futsal", "icon": "circle-dot", "color": "#16A34A"},
            "circuit": {"value": "circuit", "label": "Circuito", "icon": "refresh-cw", "color": "#7C3AED"},
        }
    )
    return [by_key[item] for item in preferred if item in by_key]
