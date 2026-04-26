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

REM Build com PyInstaller (onedir via spec)
echo [3/5] Compilando com PyInstaller...
pyinstaller build_windows.spec

if %ERRORLEVEL% neq 0 (
    echo [ERRO] Falha na compilacao.
    pause
    exit /b 1
)

echo [4/5] Validando saida...
if not exist "dist\MusicAutoManager\MusicAutoManager.exe" (
    echo [ERRO] dist\MusicAutoManager\MusicAutoManager.exe nao encontrado.
    pause
    exit /b 1
)
if not exist "dist\MusicAutoManager\ffmpeg_bin\ffmpeg.exe" (
    echo [ERRO] ffmpeg.exe nao foi empacotado em dist\MusicAutoManager\ffmpeg_bin.
    pause
    exit /b 1
)
if not exist "dist\MusicAutoManager\ffmpeg_bin\ffprobe.exe" (
    echo [ERRO] ffprobe.exe nao foi empacotado em dist\MusicAutoManager\ffmpeg_bin.
    pause
    exit /b 1
)

echo [5/5] Build concluido!
echo.
echo Saida principal: dist\MusicAutoManager\MusicAutoManager.exe
echo.
pause
