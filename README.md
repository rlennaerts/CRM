# CRM Hub — Integratie-platform

Centrale hub die mijn.vwe, Gaston, SAM en het werkplaatsplanbord met elkaar verbindt.

## Architectuur

```
mijn.vwe (bot)  ──┐
Gaston (export) ──┤──▶  CRM Hub (FastAPI + SQLite)  ──▶  Dashboard
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

---

## Installatie op Windows (geen Docker nodig)

### Vereisten

- **Python 3.11 of hoger** — download via https://python.org  
  *(vink bij installatie "Add Python to PATH" aan)*

### Stap 1: Eenmalige installatie

Dubbelklik op `setup.bat` of voer uit in een opdrachtprompt:

```
setup.bat
```

Dit doet automatisch:
- Virtualenv aanmaken
- Alle packages installeren
- Chromium downloaden (voor VWE-koppeling)
- Import-mappen aanmaken (`imports\gaston`, `imports\sam`)
- `.env` aanmaken met standaardwaarden

### Stap 2: Inloggegevens invullen

Open `.env` in Kladblok en vul in:

```
VWE_USERNAME=jouw@email.nl
VWE_PASSWORD=jouwwachtwoord
```

### Stap 3: Starten

Dubbelklik op `start.bat`

Het dashboard is bereikbaar op: **http://localhost:8000**  
API-documentatie: **http://localhost:8000/docs**

---

## Gaston & SAM exports verwerken

Plaats geëxporteerde bestanden in:

```
imports\gaston\  → werkorders*.csv, afspraken*.csv, klanten*.csv
imports\sam\     → voorraad*.csv, verkoop*.csv, klanten*.csv
```

De sync pikt ze automatisch op. Of start handmatig via het dashboard of:
- `POST /api/sync/gaston`
- `POST /api/sync/sam`
- `POST /api/sync/vwe`
- `POST /api/sync/all`

---

## Upgrade naar PostgreSQL (later)

Wanneer je root/server-toegang hebt en PostgreSQL wilt gebruiken, pas je `.env` aan:

```
DATABASE_URL=postgresql+asyncpg://user:wachtwoord@localhost:5432/crm_hub
```

En installeer de extra driver:
```
pip install asyncpg psycopg2-binary
```

De Docker Compose configuratie (`docker-compose.yml`) staat klaar voor die situatie.

---

## Kolomnamen aanpassen

Gaston en SAM exporteren soms in andere kolomnamen. Pas de `col_map` dictionaries aan in:
- `app/connectors/gaston.py`
- `app/connectors/sam.py`
