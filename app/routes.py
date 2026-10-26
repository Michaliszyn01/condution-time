from datetime import datetime

from flask import Blueprint, render_template, request

from app.services.home_service import get_home_page_data
from app.services.history_service import (
    HistoryFilterError,
    get_history_page_data,
    parse_history_filters,
)
from app.services.nutrition_service import get_nutrition_page_data
from app.services.record_service import get_daily_record_counts
from app.services.session_service import get_session_page_data
from app.services.sleep_service import get_sleep_page_data
from app.services.study_service import build_study_page_data
from app.services.training_service import get_training_page_data
from app.services.computer_service import get_computer_page_data
from app.services.notification_service import list_notifications
from app.services.analytics_utils import (
    build_date_navigation,
    get_app_timezone,
    get_local_today,
)
from app.services.catalog_service import manual_training_options


main = Blueprint("main", __name__)


def _selected_date():
    today = get_local_today()
    raw = request.args.get("date")
    if not raw:
        return today
    try:
        selected = today.fromisoformat(raw)
    except ValueError:
        return today
    return min(selected, today)


@main.get("/")
def home():
    return render_template(
        "pages/home.html",
        active_page="home",
        home_page_data=get_home_page_data(),
    )


@main.get("/historico")
def historico():
    try:
        filters = parse_history_filters(request.args)
        errors = {}
        status_code = 200
    except HistoryFilterError as exc:
        filters = parse_history_filters({})
        errors = exc.errors
        status_code = 400
    return (
        render_template(
            "pages/historico.html",
            active_page="historico",
            page_title="Histórico",
            page_description="Consulte e gerencie suas atividades registradas.",
            history_data=get_history_page_data(filters),
            history_errors=errors,
        ),
        status_code,
    )


@main.get("/estudo")
def estudo():
    selected = _selected_date()
    study_data = build_study_page_data(selected)

    return render_template(
        "pages/estudo.html",
        active_page="estudo",
        page_title="Categoria • Estudo",
        page_description="Acompanhe seu desempenho nos estudos.",
        page_date_label=study_data["reference_label"],
        study_data=study_data,
        date_navigation=build_date_navigation(selected, "/estudo"),
    )


@main.get("/treino")
def treino():
    selected = _selected_date()
    training_data = get_training_page_data(selected)

    return render_template(
        "pages/treino.html",
        active_page="treino",
        page_title="Categoria • Treino",
        page_description="Acompanhe seu desempenho físico.",
        page_date_label=training_data["reference_label"],
        training_data=training_data,
        date_navigation=build_date_navigation(selected, "/treino"),
    )


@main.get("/sono")
def sono():
    selected = _selected_date()
    sleep_data = get_sleep_page_data(selected)

    return render_template(
        "pages/sono.html",
        active_page="sono",
        page_title="Categoria • Sono",
        page_description="Acompanhe a qualidade do seu descanso.",
        page_date_label=sleep_data["reference_label"],
        sleep_data=sleep_data,
        date_navigation=build_date_navigation(selected, "/sono"),
    )


@main.get("/computador")
def computador():
    selected = _selected_date()
    return render_template(
        "pages/computador.html",
        active_page="computador",
        page_title="Categoria • Uso do computador",
        page_description="Veja como seu tempo no PC foi utilizado.",
        computer_data=get_computer_page_data(selected),
        date_navigation=build_date_navigation(selected, "/computador"),
    )


@main.get("/alimentacao")
def alimentacao():
    nutrition_data = get_nutrition_page_data()

    return render_template(
        "pages/alimentacao.html",
        active_page="alimentacao",
        page_title="Categoria • Alimentação",
        page_description="Acompanhe a qualidade da sua alimentação.",
        page_date_label=nutrition_data["reference_label"],
        nutrition_data=nutrition_data,
    )


@main.get("/registrar")
def registrar():
    today = get_local_today()
    selected = _selected_date()
    daily_counts = get_daily_record_counts(selected)
    now = datetime.now(get_app_timezone())

    def status_text(category: str) -> str:
        count = daily_counts[category]
        if category == "sleep" and count == 0:
            return "Ainda não registrado"
        if count == 0:
            return "Nenhum registro nesta data"
        if count == 1:
            return "1 registro nesta data"
        return f"{count} registros nesta data"

    register_options = {
        "categories": [
            {
                "value": "study",
                "label": "Estudo",
                "description": "Registre matérias, tempo e aprendizado.",
                "status": status_text("study"),
                "icon": "book-open",
                "theme": "blue",
                "endpoint": "main.estudo",
            },
            {
                "value": "sleep",
                "label": "Sono",
                "description": "Registre horários e qualidade do descanso.",
                "status": status_text("sleep"),
                "icon": "moon-star",
                "theme": "purple",
                "endpoint": "main.sono",
            },
            {
                "value": "training",
                "label": "Treino",
                "description": "Registre atividade, duração e intensidade.",
                "status": status_text("training"),
                "icon": "dumbbell",
                "theme": "green",
                "endpoint": "main.treino",
            },
            {
                "value": "nutrition",
                "label": "Alimentação",
                "description": "Registre refeições, hidratação e qualidade.",
                "status": status_text("nutrition"),
                "icon": "utensils",
                "theme": "orange",
                "endpoint": "main.alimentacao",
            },
        ],
        "study_subjects": [
            "Matemática",
            "Linguagens",
            "História",
            "Geografia",
            "Biologia",
            "Física",
            "Química",
            "Redação",
            "Programação",
            "Outra",
        ],
        "focus_ratings": ["Baixa", "Regular", "Boa", "Muito boa", "Excelente"],
        "study_origins": ["Sessão monitorada", "Estudo manual", "Outro"],
        "sleep_qualities": ["Péssima", "Ruim", "Regular", "Boa", "Excelente"],
        "rested_options": ["Sim", "Parcialmente", "Não"],
        "sleep_origins": [
            {"label": "Manual", "disabled": False},
            {"label": "Relógio", "disabled": True},
            {"label": "Importação futura", "disabled": True},
        ],
        "training_types": manual_training_options(),
        "performance_ratings": ["Ruim", "Regular", "Bom", "Muito bom", "Excelente"],
        "discomfort_levels": ["Nenhum", "Leve", "Moderado", "Forte"],
        "nutrition_modes": ["Refeição", "Hidratação"],
        "meal_types": [
            "Café da manhã",
            "Almoço",
            "Lanche",
            "Jantar",
            "Ceia",
            "Outra",
        ],
        "yes_no_unknown": ["Sim", "Não", "Não sei"],
        "meal_qualities": ["Muito ruim", "Ruim", "Regular", "Boa", "Excelente"],
        "water_units": ["ml", "L"],
        "today": today.isoformat(),
        "selected_date": selected.isoformat(),
        "selected_date_label": (
            "Hoje" if selected == today else selected.strftime("%d/%m/%Y")
        ),
        "current_time": now.strftime("%H:%M"),
    }

    return render_template(
        "pages/registrar.html",
        active_page="registrar",
        page_title="Registrar atividade",
        page_description="Escolha uma categoria para adicionar informações ao seu dia.",
        register_options=register_options,
    )


@main.get("/sessao")
def sessao():
    session_page_data = get_session_page_data()

    return render_template(
        "pages/sessao.html",
        active_page="sessao",
        page_title="Nova sessão",
        page_description="Escolha seu foco e comece a transformar tempo em progresso.",
        session_options=session_page_data["options"],
        active_session=session_page_data["active_session"],
    )


@main.get("/configuracoes")
def configuracoes():
    return render_template(
        "pages/configuracoes.html",
        active_page="configuracoes",
        page_title="Configurações",
        page_description="Preferências do aplicativo no Windows.",
    )


@main.get("/perfil")
def perfil():
    from app.services.profile_page_service import get_profile_page_data

    return render_template(
        "pages/perfil.html",
        active_page="perfil",
        page_title="Perfil",
        page_description="Sua evolução histórica, metas e conquistas.",
        profile_data=get_profile_page_data(
            request.args.get("period", "30d"),
            request.args.get("tab", "overview"),
            achievement_category=request.args.get("category", "all"),
            achievement_status=request.args.get("status", "all"),
        ),
    )


@main.get("/notificacoes")
def notificacoes():
    status = request.args.get("status", "all")
    notification_type = request.args.get("type") or None
    page = request.args.get("page", 1, type=int)
    try:
        notification_data = list_notifications(
            status=status,
            notification_type=notification_type,
            page=page,
        )
    except ValueError:
        status = "all"
        notification_data = list_notifications(page=page)
    return render_template(
        "pages/notificacoes.html",
        active_page="notificacoes",
        page_title="Notificações",
        page_description="Avisos úteis gerados pelo Condution Time.",
        notification_data=notification_data,
        notification_status=status,
        notification_type=notification_type,
    )
