; build_windows.spec — Spec do PyInstaller para Music Auto Manager
; Usar no Windows com: pyinstaller build_windows.spec

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[
        # Incluir binários do FFmpeg se presentes localmente
        ('ffmpeg_bin/*.exe', 'ffmpeg_bin'),
    ],
    datas=[
        ('assets/*', 'assets'),
        ('settings.json', '.'),
    ],
    hiddenimports=[
        'customtkinter',
        'tkinterdnd2',
        'PIL._tkinter_finder',
        'yt_dlp',
        'yt_dlp.extractor',
        'yt_dlp.downloader',
        'yt_dlp.postprocessor',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MusicAutoManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # Sem janela de terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',  # Coloque icon.ico na pasta assets/
)
