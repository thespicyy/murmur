@echo off
REM Murmur - lancement normal, sans console.
REM L'application vit dans l'icone pres de l'horloge.
REM Chemins resolus via %~dp0 : fonctionne depuis n'importe quel disque.

cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo Environnement introuvable. Cree-le avec :
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" -m murmur
