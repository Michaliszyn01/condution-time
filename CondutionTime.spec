from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH)
icon_candidate = project_root / "assets" / "condution_time.ico"
desktop_icon = str(icon_candidate) if icon_candidate.is_file() else None

datas = [
    (str(project_root / "app" / "templates"), "app/templates"),
    (str(project_root / "app" / "static"), "app/static"),
    (str(project_root / "migrations"), "migrations"),
    (str(project_root / "assets"), "assets"),
]

hiddenimports = (
    [
        "logging.config",
        "desktop.ipc_client",
        "desktop.ipc_server",
        "desktop.runtime_state",
        "desktop.monitoring.agent",
        "desktop.monitoring.foreground",
        "desktop.monitoring.idle",
        "desktop.monitoring.classifier",
        "desktop.monitoring.aggregator",
        "desktop.monitoring.repository",
        "app.health_import.archive",
        "app.health_import.schema_detector",
        "app.health_import.health_connect_reader",
        "app.health_import.mapper",
        "app.health_import.repository",
        "app.health_import.importer",
        "app.health_import.watcher",
        "app.services.profile_service",
        "app.services.profile_page_service",
    ]
    + collect_submodules("webview")
    + collect_submodules("pystray")
)

analysis = Analysis(
    [str(project_root / "desktop" / "launcher.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="CondutionTime",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=desktop_icon,
)

bundle = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CondutionTime",
)
