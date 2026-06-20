# CRM Hub — Integratie-platform

Centrale hub die mijn.vwe, Gaston, SAM en het werkplaatsplanbord met elkaar verbindt.

## Architectuur

```
mijn.vwe (bot)  ──┐
Gaston (export) ──┤──▶  CRM Hub (FastAPI + PostgreSQL)  ──▶  Dashboard
SAM (export)    ──┘
```

## Functionaliteit

| Module | Beschrijving |
|---|---|
| **VWE connector** | Playwright-bot die mijn.vwe.nl automatiseert (login, voertuigen ophalen, status bijwerken) |
| **Gaston connector** | Verwerkt CSV/Excel exports van Gaston (werkorders, afspraken, klanten) |
| **SAM connector** | Verwerkt CSV/Excel exports van SAM (voorraad, verkopen, klanten) |
| **Sync engine** | Slaat alles op in één centrale database met deduplicatie |
| **Checklists** | Automatische inkoop-/prep-/afleverchecks per voertuig |
| **Signalering** | Alerts voor APK-verloop, voertuigen die te lang in prep staan, e.d. |
| **Dashboard** | Realtime overzicht van voorraad, werkorders en signaleringen |
| **Taakplanner** | Automatische sync elke 15–30 minuten |

## Installatie

### 1. Omgevingsbestand aanmaken

```bash
cp .env.example .env
# Vul .env in met je gegevens
```

### 2. Opstarten met Docker

```bash
docker compose up -d
```

Het dashboard is bereikbaar op http://localhost:8000

### 3. Of lokaal draaien

```bash
# PostgreSQL en Redis moeten lokaal draaien
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload
```

## Gaston & SAM exports verwerken

Plaats geëxporteerde bestanden in de geconfigureerde mappen:

```
/data/imports/gaston/  → werkorders*.csv, afspraken*.csv, klanten*.csv
/data/imports/sam/     → voorraad*.csv, verkoop*.csv, klanten*.csv
```

De sync pikt ze automatisch op. Of start handmatig via:
- `POST /api/sync/gaston`
- `POST /api/sync/sam`
- `POST /api/sync/vwe`
- `POST /api/sync/all`

## VWE koppeling

De VWE-connector gebruikt Playwright om mijn.vwe.nl te bedienen.
Stel in `.env` in:
```
VWE_USERNAME=jouw@email.nl
VWE_PASSWORD=jouwwachtwoord
```

> **Let op**: De precieze CSS-selectors in `app/connectors/vwe.py` moeten afgestemd
> worden op de huidige VWE-pagina-structuur. Gebruik de `screenshot_for_debug()`
> methode om te inspecteren wat de bot ziet.

## API-documentatie

Na opstarten beschikbaar op: http://localhost:8000/docs

## Kolomnamen aanpassen

Gaston en SAM exporteren soms in andere kolomnamen. De connectors proberen
automatisch te matchen op aliassen. Pas de `col_map` dictionaries aan in:
- `app/connectors/gaston.py`
- `app/connectors/sam.py`
