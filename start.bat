@echo off
echo ============================================
echo  CRM Hub starten...
echo ============================================

REM Activeer virtualenv
call venv\Scripts\activate.bat

REM Maak import-mappen aan als ze ontbreken
if not exist "imports\gaston" mkdir imports\gaston
if not exist "imports\sam"    mkdir imports\sam

REM Lees PORT uit .env als die bestaat
set PORT=8000
for /f "tokens=1,2 delims==" %%a in (.env) do (
    if "%%a"=="PORT" set PORT=%%b
)

echo Applicatie beschikbaar op: http://localhost:%PORT%
echo Druk Ctrl+C om te stoppen.
echo.

python -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% --reload
