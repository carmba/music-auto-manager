@echo off
REM build_installer.bat - Build completo + instalador Inno Setup

setlocal

echo ============================================
echo   MUSIC AUTO MANAGER - Build Instalador
echo ============================================
echo.

call build.bat
if %ERRORLEVEL% neq 0 (
    echo [ERRO] Build do executavel falhou.
    pause
    exit /b 1
)

if not exist "dist\MusicAutoManager\MusicAutoManager.exe" (
    echo [ERRO] dist\MusicAutoManager\MusicAutoManager.exe nao encontrado.
    pause
    exit /b 1
)

set ISCC_EXE="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC_EXE% (
    set ISCC_EXE="C:\Program Files\Inno Setup 6\ISCC.exe"
)

if not exist %ISCC_EXE% (
    echo [ERRO] Inno Setup nao encontrado.
    echo Instale em: https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)

echo [OK] Inno Setup encontrado em %ISCC_EXE%

echo [1/1] Gerando instalador...
%ISCC_EXE% installer_windows.iss
if %ERRORLEVEL% neq 0 (
    echo [ERRO] Falha ao gerar instalador.
    pause
    exit /b 1
)

echo.
echo [SUCESSO] Instalador gerado em dist\MusicAutoManager-Setup.exe
echo.
pause
