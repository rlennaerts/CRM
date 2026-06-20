"""
SAM connector — verwerkt exports van het SAM (Sales Aftersales Management) systeem.
SAM is een legacy Windows-applicatie; data wordt geëxporteerd als CSV/Excel.
"""

import os
import glob
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import pandas as pd
from loguru import logger

from app.config import settings


@dataclass
class SamVehicle:
    sam_id: str
    license_plate: Optional[str] = None
    vin: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    mileage: Optional[int] = None
    color: Optional[str] = None
    fuel_type: Optional[str] = None
    purchase_price: Optional[float] = None
    trade_in_value: Optional[float] = None
    asking_price: Optional[float] = None
    sale_price: Optional[float] = None
    status: Optional[str] = None
    is_trade_in: bool = False
    owner_sam_id: Optional[str] = None


@dataclass
class SamSale:
    sam_id: str
    vehicle_sam_id: Optional[str] = None
    customer_sam_id: Optional[str] = None
    sale_date: Optional[datetime] = None
    sale_price: Optional[float] = None
    trade_in_vehicle: Optional[str] = None
    trade_in_value: Optional[float] = None
    salesperson: Optional[str] = None
    status: Optional[str] = None
    delivery_date: Optional[datetime] = None


@dataclass
class SamCustomer:
    sam_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    street: Optional[str] = None
    house_number: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    is_business: bool = False


class SamConnector:
    """
    Verwerkt SAM (Sales Aftersales Management) CSV/Excel exports.

    SAM exporteert o.a.:
    - Voertuigenvoorraad (inkoop, verkoop, inruil/taxatie)
    - Verkooptransacties
    - Klantendossiers
    """

    def __init__(self):
        self.export_dir = Path(settings.sam_export_dir)
        self.archive_dir = self.export_dir / "verwerkt"
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def _find_latest_export(self, prefix: str) -> Optional[Path]:
        patterns = [
            self.export_dir / f"{prefix}*.csv",
            self.export_dir / f"{prefix}*.xlsx",
            self.export_dir / f"{prefix}*.xls",
            self.export_dir / f"*{prefix}*.csv",
            self.export_dir / f"*{prefix}*.xlsx",
        ]
        files = []
        for pattern in patterns:
            files.extend(glob.glob(str(pattern)))
        if not files:
            return None
        return Path(max(files, key=os.path.getmtime))

    def _read_file(self, path: Path) -> Optional[pd.DataFrame]:
        try:
            if path.suffix.lower() == ".csv":
                for enc in ["utf-8", "utf-8-sig", "cp1252", "latin-1"]:
                    try:
                        df = pd.read_csv(path, encoding=enc, sep=None, engine="python")
                        logger.info(f"SAM: {path.name} gelezen ({len(df)} regels)")
                        return df
                    except UnicodeDecodeError:
                        continue
            else:
                df = pd.read_excel(path, engine="openpyxl" if path.suffix == ".xlsx" else "xlrd")
                logger.info(f"SAM: {path.name} gelezen ({len(df)} regels)")
                return df
        except Exception as e:
            logger.error(f"SAM: kan {path.name} niet lezen: {e}")
            return None

    def _archive(self, path: Path):
        dest = self.archive_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{path.name}"
        path.rename(dest)
        logger.info(f"SAM: {path.name} gearchiveerd")

    def _safe_str(self, val) -> Optional[str]:
        try:
            if pd.isna(val):
                return None
        except (TypeError, ValueError):
            pass
        return str(val).strip() or None

    def _safe_float(self, val) -> Optional[float]:
        try:
            return float(val) if not pd.isna(val) else None
        except (ValueError, TypeError):
            return None

    def _safe_int(self, val) -> Optional[int]:
        try:
            return int(val) if not pd.isna(val) else None
        except (ValueError, TypeError):
            return None

    def _safe_datetime(self, val) -> Optional[datetime]:
        try:
            if pd.isna(val):
                return None
        except (TypeError, ValueError):
            pass
        try:
            return pd.to_datetime(val).to_pydatetime()
        except Exception:
            return None

    def fetch_vehicles(self) -> list[SamVehicle]:
        """Verwerk SAM voorraad/voertuigen export."""
        path = (
            self._find_latest_export("voorraad")
            or self._find_latest_export("voertuigen")
            or self._find_latest_export("stock")
        )
        if not path:
            logger.debug("SAM: geen voertuigen-export gevonden")
            return []

        df = self._read_file(path)
        if df is None:
            return []

        df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]

        vehicles = []
        for _, row in df.iterrows():
            sam_id = self._safe_str(
                row.get("id") or row.get("voertuig_id") or row.get("stocknummer")
            )
            if not sam_id:
                continue

            status_raw = self._safe_str(row.get("status") or row.get("voertuigstatus")) or ""
            is_trade_in = "inruil" in status_raw.lower() or "taxatie" in status_raw.lower()

            vehicles.append(SamVehicle(
                sam_id=sam_id,
                license_plate=self._safe_str(row.get("kenteken")),
                vin=self._safe_str(row.get("vin") or row.get("chassisnummer")),
                make=self._safe_str(row.get("merk")),
                model=self._safe_str(row.get("model") or row.get("type")),
                year=self._safe_int(row.get("bouwjaar") or row.get("jaar")),
                mileage=self._safe_int(row.get("km_stand") or row.get("kilometerstand") or row.get("km")),
                color=self._safe_str(row.get("kleur") or row.get("kleur_exterieur")),
                fuel_type=self._safe_str(row.get("brandstof")),
                purchase_price=self._safe_float(row.get("inkoopprijs") or row.get("inkoop")),
                trade_in_value=self._safe_float(row.get("inruilwaarde") or row.get("taxatiewaarde")),
                asking_price=self._safe_float(row.get("vraagprijs") or row.get("verkoopprijs")),
                sale_price=self._safe_float(row.get("verkoopprijs_definitief") or row.get("verkoop")),
                status=status_raw or None,
                is_trade_in=is_trade_in,
                owner_sam_id=self._safe_str(row.get("klant_id") or row.get("eigenaar_id")),
            ))

        self._archive(path)
        logger.info(f"SAM: {len(vehicles)} voertuigen verwerkt")
        return vehicles

    def fetch_sales(self) -> list[SamSale]:
        """Verwerk SAM verkoop-export."""
        path = self._find_latest_export("verkoop") or self._find_latest_export("sales")
        if not path:
            logger.debug("SAM: geen verkoop-export gevonden")
            return []

        df = self._read_file(path)
        if df is None:
            return []

        df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]

        sales = []
        for _, row in df.iterrows():
            sam_id = self._safe_str(row.get("id") or row.get("verkoop_id") or row.get("transactienummer"))
            if not sam_id:
                continue

            sales.append(SamSale(
                sam_id=sam_id,
                vehicle_sam_id=self._safe_str(row.get("voertuig_id") or row.get("stocknummer")),
                customer_sam_id=self._safe_str(row.get("klant_id") or row.get("klantnummer")),
                sale_date=self._safe_datetime(row.get("verkoopdatum") or row.get("datum")),
                sale_price=self._safe_float(row.get("verkoopprijs") or row.get("prijs")),
                trade_in_vehicle=self._safe_str(row.get("inruil_kenteken") or row.get("inruil")),
                trade_in_value=self._safe_float(row.get("inruilwaarde")),
                salesperson=self._safe_str(row.get("verkoper") or row.get("medewerker")),
                status=self._safe_str(row.get("status")),
                delivery_date=self._safe_datetime(row.get("leverdatum") or row.get("aflever_datum")),
            ))

        self._archive(path)
        logger.info(f"SAM: {len(sales)} verkopen verwerkt")
        return sales

    def fetch_customers(self) -> list[SamCustomer]:
        """Verwerk SAM klanten-export."""
        path = (
            self._find_latest_export("klanten")
            or self._find_latest_export("relaties")
            or self._find_latest_export("customers")
        )
        if not path:
            logger.debug("SAM: geen klanten-export gevonden")
            return []

        df = self._read_file(path)
        if df is None:
            return []

        df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]

        customers = []
        for _, row in df.iterrows():
            sam_id = self._safe_str(row.get("id") or row.get("klant_id") or row.get("klantnummer"))
            if not sam_id:
                continue

            is_business = str(row.get("type", "") or row.get("klanttype", "")).lower() in (
                "bedrijf", "zakelijk", "b", "company"
            )
            customers.append(SamCustomer(
                sam_id=sam_id,
                first_name=self._safe_str(row.get("voornaam")),
                last_name=self._safe_str(row.get("achternaam") or row.get("naam")),
                company_name=self._safe_str(row.get("bedrijfsnaam") or row.get("bedrijf")),
                email=self._safe_str(row.get("email") or row.get("emailadres")),
                phone=self._safe_str(row.get("telefoon") or row.get("tel")),
                mobile=self._safe_str(row.get("mobiel") or row.get("gsm")),
                street=self._safe_str(row.get("straat") or row.get("adres")),
                house_number=self._safe_str(row.get("huisnummer") or row.get("nr")),
                postal_code=self._safe_str(row.get("postcode")),
                city=self._safe_str(row.get("plaats") or row.get("stad")),
                is_business=is_business,
            ))

        self._archive(path)
        logger.info(f"SAM: {len(customers)} klanten verwerkt")
        return customers
