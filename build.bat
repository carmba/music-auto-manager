@echo off
REM build.bat — Script de build para Windows
REM Execute no prompt de comando do Windows, na pasta do projeto

echo ============================================
echo   MUSIC AUTO MANAGER — Build para Windows
echo ============================================
echo.

REM Verificar Python
python --version
if %ERRORLEVEL% neq 0 (
    echo [ERRO] Python nao encontrado. Instale o Python 3.11+ e tente novamente.
    pause
    exit /b 1
)

REM Instalar dependencias
echo [1/4] Instalando dependencias...
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERRO] Falha ao instalar dependencias.
    pause
    exit /b 1
)

REM Criar pasta assets se nao existir
if not exist "assets" mkdir assets
if not exist "ffmpeg_bin" mkdir ffmpeg_bin

REM Baixar FFmpeg local para embutir no executavel
echo [2/4] Preparando FFmpeg bundled...
if exist "ffmpeg_bin\ffmpeg.exe" if exist "ffmpeg_bin\ffprobe.exe" (
    echo [OK] FFmpeg local encontrado em ffmpeg_bin\
) else (
    echo [INFO] Baixando FFmpeg para embutir no .exe...
    python -c "from utils import download_ffmpeg; raise SystemExit(0 if download_ffmpeg(print) else 1)"
    if %ERRORLEVEL% neq 0 (
        echo [ERRO] Falha ao baixar FFmpeg para o build.
        pause
        exit /b 1
    )
)

REM Build com PyInstaller
echo [3/4] Compilando com PyInstaller...
if exist "assets\icon.ico" (
    pyinstaller build_windows.spec
) else (
    echo [AVISO] icon.ico nao encontrado em assets\. Compilando sem icone...
    pyinstaller --onefile --windowed --name MusicAutoManager ^
        --add-data "assets;assets" ^
        --add-binary "ffmpeg_bin\ffmpeg.exe;ffmpeg_bin" ^
        --add-binary "ffmpeg_bin\ffprobe.exe;ffmpeg_bin" ^
        --hidden-import customtkinter ^
        --hidden-import tkinterdnd2 ^
        --hidden-import yt_dlp ^
        --hidden-import PIL._tkinter_finder ^
        main.py
)

if %ERRORLEVEL% neq 0 (
    echo [ERRO] Falha na compilacao.
    pause
    exit /b 1
)

echo [4/4] Build concluido!
echo.
echo O executavel esta em: dist\MusicAutoManager.exe
echo.
pause
