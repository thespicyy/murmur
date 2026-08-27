@echo off
REM Murmur - lancement avec console de diagnostic.
REM Affiche les etats, les textes dictes et les latences.
REM A utiliser quand quelque chose ne va pas ; sinon prefere lancer.bat.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Environnement introuvable. Cree-le avec :
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m murmur --console
pause
