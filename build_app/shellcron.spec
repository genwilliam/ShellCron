# ShellCron Shell Spec (macOS PyInstaller)

# This spec builds a standalone .app from the project source.
# Used by: build_app/build.py
# 
# Note: The .app is an optional packaging format.
# Default usage is via the CLI: `shcron`

a = Analysis(
    ['src/shellcron/cli/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('src/shellcron/daemon', 'daemon'),
        ('src/shellcron/web', 'web'),
        ('src/shellcron/cli', 'cli'),
    ],
    hiddenimports=[
        'flask', 'apscheduler', 'requests', 'werkzeug',
        'jinja2', 'markupsafe', 'click', 'typer',
        'itsdangerous', 'blinker', 'tzlocal',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ShellCron',
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
    icon=['build_app/icons/ShellCron.icns'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ShellCron',
)

app = BUNDLE(
    coll,
    name='ShellCron.app',
    icon='build_app/icons/ShellCron.icns',
    bundle_identifier='com.shellcron.app',
)
