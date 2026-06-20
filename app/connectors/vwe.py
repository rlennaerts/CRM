"""
VWE connector — gebruikt Playwright om mijn.vwe.nl te bedienen.
VWE heeft geen API; alle interactie gaat via de webUI.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from loguru import logger
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from app.config import settings


@dataclass
class VweVehicle:
    vwe_id: str
    license_plate: Optional[str] = None
    vin: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    variant: Optional[str] = None
    year: Optional[int] = None
    mileage: Optional[int] = None
    fuel_type: Optional[str] = None
    color: Optional[str] = None
    apk_expiry: Optional[date] = None
    asking_price: Optional[float] = None
    status: Optional[str] = None


@dataclass
class VweCustomer:
    vwe_id: str
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


class VweConnector:
    """
    Playwright-gebaseerde connector voor mijn.vwe.nl.

    Ondersteunt:
    - Inloggen en sessie beheren
    - Voertuigen ophalen (inkoop, verkoop, inruil)
    - Klantgegevens ophalen
    - Taxaties opzoeken
    - Voertuigstatus bijwerken
    """

    def __init__(self):
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._logged_in = False

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="nl-NL",
        )
        self._page = await self._context.new_page()
        logger.info("VWE Playwright browser gestart")

    async def close(self):
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_playwright"):
            await self._playwright.stop()
        self._logged_in = False
        logger.info("VWE browser gesloten")

    async def login(self) -> bool:
        """Inloggen op mijn.vwe.nl."""
        if self._logged_in:
            return True

        try:
            await self._page.goto(f"{settings.vwe_base_url}/login", wait_until="networkidle")

            # Vul inloggegevens in — pas selectors aan op basis van de echte VWE UI
            await self._page.fill('input[name="username"], input[type="email"]', settings.vwe_username)
            await self._page.fill('input[name="password"], input[type="password"]', settings.vwe_password)
            await self._page.click('button[type="submit"], input[type="submit"]')

            await self._page.wait_for_load_state("networkidle")

            # Controleer of login geslaagd is door te zoeken naar een element dat alleen na login zichtbaar is
            success = await self._page.query_selector(".dashboard, .main-menu, [data-logged-in]") is not None
            if success:
                self._logged_in = True
                logger.info("Succesvol ingelogd bij VWE")
            else:
                logger.error("VWE login mislukt")
            return success

        except Exception as e:
            logger.error(f"VWE login fout: {e}")
            return False

    async def fetch_vehicles(self, status_filter: Optional[str] = None) -> list[VweVehicle]:
        """Haal voertuigen op uit VWE."""
        if not await self.login():
            return []

        vehicles = []
        try:
            url = f"{settings.vwe_base_url}/voorraad"
            if status_filter:
                url += f"?status={status_filter}"

            await self._page.goto(url, wait_until="networkidle")

            # Pas de selectors aan op de echte VWE pagina-structuur
            rows = await self._page.query_selector_all("table.vehicle-list tr[data-id], .vehicle-card[data-id]")

            for row in rows:
                vwe_id = await row.get_attribute("data-id")
                if not vwe_id:
                    continue

                vehicle = VweVehicle(vwe_id=vwe_id)

                # Kenteken
                lp_el = await row.query_selector(".license-plate, [data-field='kenteken']")
                if lp_el:
                    vehicle.license_plate = (await lp_el.inner_text()).strip()

                # Merk/model
                make_el = await row.query_selector(".make, [data-field='merk']")
                if make_el:
                    vehicle.make = (await make_el.inner_text()).strip()

                model_el = await row.query_selector(".model, [data-field='model']")
                if model_el:
                    vehicle.model = (await model_el.inner_text()).strip()

                vehicles.append(vehicle)

            logger.info(f"VWE: {len(vehicles)} voertuigen opgehaald")

        except Exception as e:
            logger.error(f"VWE fetch_vehicles fout: {e}")

        return vehicles

    async def fetch_customers(self) -> list[VweCustomer]:
        """Haal klantgegevens op uit VWE."""
        if not await self.login():
            return []

        customers = []
        try:
            await self._page.goto(f"{settings.vwe_base_url}/klanten", wait_until="networkidle")

            rows = await self._page.query_selector_all("table.customer-list tr[data-id], .customer-card[data-id]")
            for row in rows:
                vwe_id = await row.get_attribute("data-id")
                if not vwe_id:
                    continue

                customer = VweCustomer(vwe_id=vwe_id)

                name_el = await row.query_selector(".customer-name, [data-field='naam']")
                if name_el:
                    full_name = (await name_el.inner_text()).strip()
                    parts = full_name.split(" ", 1)
                    customer.first_name = parts[0]
                    customer.last_name = parts[1] if len(parts) > 1 else ""

                email_el = await row.query_selector(".email, [data-field='email']")
                if email_el:
                    customer.email = (await email_el.inner_text()).strip()

                customers.append(customer)

            logger.info(f"VWE: {len(customers)} klanten opgehaald")

        except Exception as e:
            logger.error(f"VWE fetch_customers fout: {e}")

        return customers

    async def get_vehicle_detail(self, vwe_id: str) -> Optional[VweVehicle]:
        """Haal detail op van één voertuig."""
        if not await self.login():
            return None

        try:
            await self._page.goto(
                f"{settings.vwe_base_url}/voorraad/{vwe_id}",
                wait_until="networkidle",
            )

            vehicle = VweVehicle(vwe_id=vwe_id)

            fields = {
                "license_plate": "[data-field='kenteken'], .license-plate",
                "vin": "[data-field='vin'], .vin-number",
                "make": "[data-field='merk'], .vehicle-make",
                "model": "[data-field='model'], .vehicle-model",
                "color": "[data-field='kleur'], .vehicle-color",
                "fuel_type": "[data-field='brandstof'], .fuel-type",
            }

            for attr, selector in fields.items():
                el = await self._page.query_selector(selector)
                if el:
                    setattr(vehicle, attr, (await el.inner_text()).strip())

            return vehicle

        except Exception as e:
            logger.error(f"VWE get_vehicle_detail({vwe_id}) fout: {e}")
            return None

    async def update_vehicle_status(self, vwe_id: str, new_status: str) -> bool:
        """Pas de status van een voertuig aan in VWE."""
        if not await self.login():
            return False

        try:
            await self._page.goto(
                f"{settings.vwe_base_url}/voorraad/{vwe_id}/bewerken",
                wait_until="networkidle",
            )

            status_select = await self._page.query_selector("select[name='status'], #vehicle-status")
            if status_select:
                await status_select.select_option(value=new_status)
                await self._page.click('button[type="submit"]')
                await self._page.wait_for_load_state("networkidle")
                logger.info(f"VWE voertuig {vwe_id} status bijgewerkt naar {new_status}")
                return True

        except Exception as e:
            logger.error(f"VWE update_vehicle_status fout: {e}")

        return False

    async def screenshot_for_debug(self, path: str = "/tmp/vwe_debug.png"):
        """Sla screenshot op voor debuggen."""
        if self._page:
            await self._page.screenshot(path=path, full_page=True)
            logger.debug(f"Screenshot opgeslagen: {path}")
