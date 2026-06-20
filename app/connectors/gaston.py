"""
Gaston connector — verwerkt exports (CSV/Excel) van het Gaston cloud DMS.
Gaston ondersteunt geen API; data wordt geëxporteerd en dan verwerkt.
"""

import os
import glob
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import pandas as pd
from loguru import logger

from app.config import settings


@dataclass
class GastonWorkOrder:
    gaston_id: str
    order_number: str
    license_plate: Optional[str] = None
    customer_name: Optional[str] = None
    customer_id: Optional[str] = None
    order_type: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    mechanic: Optional[str] = None
    planned_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    parts_cost: Optional[float] = None
    labour_cost: Optional[float] = None


@dataclass
class GastonAppointment:
    gaston_id: str
    license_plate: Optional[str] = None
    customer_name: Optional[str] = None
    appointment_type: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    mechanic: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class GastonCustomer:
    gaston_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    street: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    is_business: bool = False


class GastonConnector:
    """
    Verwerkt Gaston CSV/Excel exports.

    Gaston kan exporteren naar:
    - Werkorders (work_orders export)
    - Afspraken / planbord (appointments export)
    - Klanten (customers export)

    Plaats de exports in de map ingesteld via GASTON_EXPORT_DIR.
    Bestanden worden verwerkt en daarna gearchiveerd.
    """

    def __init__(self):
        self.export_dir = Path(settings.gaston_export_dir)
        self.archive_dir = self.export_dir / "verwerkt"
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def _find_latest_export(self, prefix: str) -> Optional[Path]:
        """Vind het meest recente exportbestand met het gegeven prefix."""
        patterns = [
            self.export_dir / f"{prefix}*.csv",
            self.export_dir / f"{prefix}*.xlsx",
            self.export_dir / f"{prefix}*.xls",
        ]
        files = []
        for pattern in patterns:
            files.extend(glob.glob(str(pattern)))

        if not files:
            return None

        return Path(max(files, key=os.path.getmtime))

    def _read_file(self, path: Path) -> Optional[pd.DataFrame]:
        """Lees CSV of Excel exportbestand."""
        try:
            if path.suffix.lower() == ".csv":
                # Probeer verschillende encodings (Gaston gebruikt soms Windows-1252)
                for enc in ["utf-8", "utf-8-sig", "cp1252", "latin-1"]:
                    try:
                        df = pd.read_csv(path, encoding=enc, sep=None, engine="python")
                        logger.info(f"Gaston: {path.name} gelezen ({len(df)} regels, encoding={enc})")
                        return df
                    except UnicodeDecodeError:
                        continue
            else:
                df = pd.read_excel(path, engine="openpyxl" if path.suffix == ".xlsx" else "xlrd")
                logger.info(f"Gaston: {path.name} gelezen ({len(df)} regels)")
                return df
        except Exception as e:
            logger.error(f"Gaston: kan {path.name} niet lezen: {e}")
            return None

    def _archive(self, path: Path):
        """Verplaats verwerkt bestand naar archief."""
        dest = self.archive_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{path.name}"
        path.rename(dest)
        logger.info(f"Gaston: {path.name} gearchiveerd")

    def _safe_str(self, val) -> Optional[str]:
        if pd.isna(val):
            return None
        return str(val).strip() or None

    def _safe_float(self, val) -> Optional[float]:
        try:
            return float(val) if not pd.isna(val) else None
        except (ValueError, TypeError):
            return None

    def _safe_datetime(self, val) -> Optional[datetime]:
        if pd.isna(val):
            return None
        try:
            return pd.to_datetime(val).to_pydatetime()
        except Exception:
            return None

    def fetch_work_orders(self) -> list[GastonWorkOrder]:
        """Verwerk Gaston werkorder-export."""
        path = self._find_latest_export("werkorders")
        if not path:
            logger.debug("Gaston: geen werkorder-export gevonden")
            return []

        df = self._read_file(path)
        if df is None:
            return []

        # Kolom-mapping — pas aan op basis van echte Gaston kolomnamen
        col_map = {
            "id": ["id", "werkorder_id", "nr", "nummer"],
            "order_number": ["werkordernummer", "ordernummer", "number"],
            "license_plate": ["kenteken", "license_plate"],
            "customer_name": ["klantnaam", "klant", "customer"],
            "customer_id": ["klant_id", "customer_id", "relatienummer"],
            "order_type": ["type", "werktype", "soort"],
            "status": ["status"],
            "description": ["omschrijving", "description", "werkzaamheden"],
            "mechanic": ["monteur", "mechanic", "medewerker"],
            "planned_date": ["geplande_datum", "datum_gepland", "planned_date"],
            "completed_date": ["afrond_datum", "datum_afgerond", "completed_date"],
            "parts_cost": ["onderdelen_kosten", "parts_cost", "materiaalkosten"],
            "labour_cost": ["loonkosten", "labour_cost", "arbeidskosten"],
        }

        # Normaliseer kolomnamen
        df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
        resolved = {}
        for field, aliases in col_map.items():
            for alias in aliases:
                if alias in df.columns:
                    resolved[field] = alias
                    break

        orders = []
        for _, row in df.iterrows():
            gaston_id = self._safe_str(row.get(resolved.get("id", "id"), None))
            order_number = self._safe_str(row.get(resolved.get("order_number", ""), None))
            if not gaston_id:
                continue

            orders.append(GastonWorkOrder(
                gaston_id=gaston_id,
                order_number=order_number or gaston_id,
                license_plate=self._safe_str(row.get(resolved.get("license_plate", ""), None)),
                customer_name=self._safe_str(row.get(resolved.get("customer_name", ""), None)),
                customer_id=self._safe_str(row.get(resolved.get("customer_id", ""), None)),
                order_type=self._safe_str(row.get(resolved.get("order_type", ""), None)),
                status=self._safe_str(row.get(resolved.get("status", ""), None)),
                description=self._safe_str(row.get(resolved.get("description", ""), None)),
                mechanic=self._safe_str(row.get(resolved.get("mechanic", ""), None)),
                planned_date=self._safe_datetime(row.get(resolved.get("planned_date", ""), None)),
                completed_date=self._safe_datetime(row.get(resolved.get("completed_date", ""), None)),
                parts_cost=self._safe_float(row.get(resolved.get("parts_cost", ""), None)),
                labour_cost=self._safe_float(row.get(resolved.get("labour_cost", ""), None)),
            ))

        self._archive(path)
        logger.info(f"Gaston: {len(orders)} werkorders verwerkt")
        return orders

    def fetch_appointments(self) -> list[GastonAppointment]:
        """Verwerk Gaston afspraken/planbord export."""
        path = self._find_latest_export("afspraken") or self._find_latest_export("planbord")
        if not path:
            logger.debug("Gaston: geen afspraken-export gevonden")
            return []

        df = self._read_file(path)
        if df is None:
            return []

        df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]

        appointments = []
        for _, row in df.iterrows():
            gaston_id = self._safe_str(row.get("id") or row.get("afspraak_id"))
            if not gaston_id:
                continue

            appointments.append(GastonAppointment(
                gaston_id=gaston_id,
                license_plate=self._safe_str(row.get("kenteken")),
                customer_name=self._safe_str(row.get("klantnaam") or row.get("klant")),
                appointment_type=self._safe_str(row.get("type") or row.get("soort")),
                start_time=self._safe_datetime(row.get("begintijd") or row.get("start")),
                end_time=self._safe_datetime(row.get("eindtijd") or row.get("eind")),
                mechanic=self._safe_str(row.get("monteur") or row.get("medewerker")),
                status=self._safe_str(row.get("status")),
                notes=self._safe_str(row.get("notities") or row.get("opmerkingen")),
            ))

        self._archive(path)
        logger.info(f"Gaston: {len(appointments)} afspraken verwerkt")
        return appointments

    def fetch_customers(self) -> list[GastonCustomer]:
        """Verwerk Gaston klanten-export."""
        path = self._find_latest_export("klanten") or self._find_latest_export("relaties")
        if not path:
            logger.debug("Gaston: geen klanten-export gevonden")
            return []

        df = self._read_file(path)
        if df is None:
            return []

        df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]

        customers = []
        for _, row in df.iterrows():
            gaston_id = self._safe_str(row.get("id") or row.get("klant_id") or row.get("relatienummer"))
            if not gaston_id:
                continue

            is_business = str(row.get("type", "")).lower() in ("bedrijf", "zakelijk", "b")
            customers.append(GastonCustomer(
                gaston_id=gaston_id,
                first_name=self._safe_str(row.get("voornaam")),
                last_name=self._safe_str(row.get("achternaam") or row.get("naam")),
                company_name=self._safe_str(row.get("bedrijfsnaam") or row.get("bedrijf")),
                email=self._safe_str(row.get("email") or row.get("emailadres")),
                phone=self._safe_str(row.get("telefoon")),
                street=self._safe_str(row.get("straat") or row.get("adres")),
                postal_code=self._safe_str(row.get("postcode")),
                city=self._safe_str(row.get("plaats") or row.get("stad")),
                is_business=is_business,
            ))

        self._archive(path)
        logger.info(f"Gaston: {len(customers)} klanten verwerkt")
        return customers
