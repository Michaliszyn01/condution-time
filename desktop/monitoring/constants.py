MONITOR_SAMPLE_INTERVAL_SECONDS = 2
IDLE_THRESHOLD_SECONDS = 300
MIN_BLOCK_SECONDS = 3
MAX_SAMPLE_GAP_SECONDS = 30
MIN_CLASSIFIED_TIME_SECONDS = 300
COMPUTER_DATA_RETENTION_DAYS = 90

CLASSIFICATIONS = {"productive", "distracting", "neutral", "ignored"}
CATEGORIES = {
    "study",
    "programming",
    "work",
    "communication",
    "entertainment",
    "social",
    "gaming",
    "system",
    "other",
}

DEFAULT_RULES = {
    "chatgpt.exe": ("ChatGPT", "productive", "study"),
    "code.exe": ("Visual Studio Code", "productive", "programming"),
    "code-insiders.exe": ("Visual Studio Code Insiders", "productive", "programming"),
    "cursor.exe": ("Cursor", "productive", "programming"),
    "codium.exe": ("VSCodium", "productive", "programming"),
    "pycharm64.exe": ("PyCharm", "productive", "programming"),
    "devenv.exe": ("Visual Studio", "productive", "programming"),
    "notion.exe": ("Notion", "productive", "work"),
    "excel.exe": ("Microsoft Excel", "productive", "work"),
    "winword.exe": ("Microsoft Word", "productive", "work"),
    "powerpnt.exe": ("Microsoft PowerPoint", "productive", "work"),
    "rocketleague.exe": ("Rocket League", "distracting", "gaming"),
    "robloxplayerbeta.exe": ("Roblox", "distracting", "gaming"),
    "steam.exe": ("Steam", "neutral", "gaming"),
    "discord.exe": ("Discord", "neutral", "communication"),
    "spotify.exe": ("Spotify", "neutral", "entertainment"),
    "chrome.exe": ("Google Chrome", "neutral", "other"),
    "msedge.exe": ("Microsoft Edge", "neutral", "other"),
    "firefox.exe": ("Mozilla Firefox", "neutral", "other"),
    "explorer.exe": ("Explorador de Arquivos", "ignored", "system"),
    "searchhost.exe": ("Pesquisa do Windows", "ignored", "system"),
    "startmenuexperiencehost.exe": ("Menu Iniciar", "ignored", "system"),
    "applicationframehost.exe": ("Aplicativo do Windows", "ignored", "system"),
    "dwm.exe": ("Gerenciador de Janelas", "ignored", "system"),
    "taskmgr.exe": ("Gerenciador de Tarefas", "ignored", "system"),
    "lockapp.exe": ("Tela de Bloqueio", "ignored", "system"),
    "logonui.exe": ("Tela de Entrada", "ignored", "system"),
    "condutiontime.exe": ("Condution Time", "ignored", "system"),
}

PROJECT_CAPABLE_EXECUTABLES = {
    "code.exe",
    "code-insiders.exe",
    "cursor.exe",
    "codium.exe",
}
SITE_CAPABLE_EXECUTABLES = {"chrome.exe"}
SITE_ALLOWLIST = {"chatgpt"}

BROWSERS = {"chrome.exe", "msedge.exe", "firefox.exe"}
PDF_READERS = {"acrord32.exe", "acrobat.exe", "sumatrapdf.exe"}
TERMINALS = {
    "windowsterminal.exe",
    "powershell.exe",
    "pwsh.exe",
    "cmd.exe",
}
