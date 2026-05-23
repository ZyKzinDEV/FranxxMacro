@echo off
title FranxxMacro - Builder
echo.
echo  ============================================
echo   FRANXX MACRO - Compilador para .EXE
echo  ============================================
echo.

:: Verifica se o PyInstaller está instalado
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo  [!] PyInstaller nao encontrado. A instalar...
    pip install pyinstaller
    echo.
)

echo  [*] A compilar... (pode demorar 1-2 minutos)
echo.

pyinstaller ^
    --onefile ^
    --windowed ^
    --icon=assets\icon.ico ^
    --add-data "assets;assets" ^
    --add-data "profiles;profiles" ^
    --name "FranxxMacro" ^
    --hidden-import "pynput.keyboard._win32" ^
    --hidden-import "pynput.mouse._win32" ^
    --hidden-import "PIL._tkinter_finder" ^
    main.py

echo.
if exist dist\FranxxMacro.exe (
    echo  [OK] Compilado com sucesso!
    echo  [OK] Ficheiro: dist\FranxxMacro.exe
    echo.
    echo  Podes copiar o FranxxMacro.exe para qualquer pasta.
    echo  Os perfis sao guardados na mesma pasta do .exe
) else (
    echo  [ERRO] Compilacao falhou. Verifica os erros acima.
)

echo.
pause
