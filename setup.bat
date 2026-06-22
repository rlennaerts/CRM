@echo off
echo ============================================
echo  CRM Hub - Installatie
echo ============================================

REM Controleer of Python beschikbaar is
python --version >nul 2>&1
if errorlevel 1 (
    echo FOUT: Python niet gevonden. Download Python 3.11+ via https://python.org
    pause
    exit /b 1
)

REM Maak virtualenv aan als die nog niet bestaat
if not exist "venv" (
    echo Virtuele omgeving aanmaken...
    python -m venv venv
)

REM Activeer virtualenv
call venv\Scripts\activate.bat

REM Installeer packages
echo Packages installeren...
pip install -r requirements.txt

REM Installeer Playwright Chromium (voor VWE-koppeling)
echo Chromium downloaden voor VWE-koppeling...
playwright install chromium

REM Maak import-mappen aan
if not exist "imports\gaston" mkdir imports\gaston
if not exist "imports\sam"    mkdir imports\sam

REM Maak .env aan als die nog niet bestaat
if not exist ".env" (
    echo .env aanmaken met standaardwaarden...
    (
        echo # CRM Hub configuratie
        echo DATABASE_URL=sqlite+aiosqlite:///crm_hub.db
        echo APP_ENV=development
        echo SECRET_KEY=verander-dit-naar-iets-geheims
        echo.
        echo # VWE inloggegevens
        echo VWE_USERNAME=
        echo VWE_PASSWORD=
        echo.
        echo # Import-mappen ^(relatief aan de projectmap^)
        echo GASTON_EXPORT_DIR=imports/gaston
        echo SAM_EXPORT_DIR=imports/sam
        echo.
        echo # Server
        echo HOST=127.0.0.1
        echo PORT=8000
    ) > .env
    echo .env aangemaakt. Vul VWE_USERNAME en VWE_PASSWORD in!
)

echo.
echo ============================================
echo  Installatie voltooid!
echo  Start de applicatie met: start.bat
echo ============================================
pause
