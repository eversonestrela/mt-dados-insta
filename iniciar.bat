@echo off
chcp 65001 >nul
cd /d "%~dp0"
title MT em Dados

if not exist ".venv\Scripts\python.exe" (
    echo Preparando o ambiente pela primeira vez. Isso leva alguns minutos...
    py -3 -m venv .venv || python -m venv .venv
    if errorlevel 1 (
        echo.
        echo Nao encontrei o Python. Instale em https://www.python.org/downloads/
        echo e marque a opcao "Add python.exe to PATH" durante a instalacao.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

echo.
echo Painel em http://127.0.0.1:8765  (deixe esta janela aberta para os posts sairem)
echo.
".venv\Scripts\python.exe" iniciar.py %*
pause
