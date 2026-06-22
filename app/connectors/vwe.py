"""
VWE connector — gebruikt Playwright om mijn.vwe.nl te bedienen.

Paginastructuur afgeleid uit de VWE Tampermonkey automatisering:

URL-patronen:
  /services/adv/list                     – advertentielijst (Angular, controller=AdvertisementMaintenanceCtrl)
  /services/adv/{id}/accessories         – opties-pagina (Angular checkboxes)
  /services/adv/{id}/summary             – samenvatting
  /services/adv/{id}/vehicleinfo         – voertuiginfo (o.a. titel-veld)

Bekende selectors:
  .vehicle-header h2 / h1                – advertentietitel (merk model uitvoering)
  .registration-number                   – kentekenplaatje
  .col-a-40 label[text="Bouwjaar"]       – bouwjaar-label, sibling bevat waarde
  label.accessory[title]                 – opties-labels (for=checkbox-id)
  form[action*="/accessories/save"]      – opslaan opties
  form[action*="/vehicleinfo/save"]      – opslaan voertuiginfo
  #General_Form_AdvertisementTitleAddendum – titelveld
  .popup-body.showroomcards-picker       – showroomkaart popup
  .options-item input[type="checkbox"]  – showroomkaart opties
"""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from loguru import logger
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, TimeoutError as PwTimeout

from app.config import settings


# ──────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────

@dataclass
class VweAdvertisement:
    """Eén advertentie uit de /services/adv/list pagina."""
    adv_id: str
    title: str
    license_plate: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    mileage: Optional[int] = None
    asking_price: Optional[float] = None
    status: Optional[str] = None  # bijv. "Actief", "Concept", "Verlopen"


@dataclass
class VweVehicle:
    """Gedetailleerde voertuigdata van de vehicleinfo-pagina."""
    vwe_id: str                          # = adv_id
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
    title: Optional[str] = None          # advertentietitel
    status: Optional[str] = None
    options: list[str] = field(default_factory=list)  # aangevinkte opties


@dataclass
class VweOption:
    """Eén optie op de accessories-pagina."""
    checkbox_id: str
    label: str
    is_checked: bool


# ──────────────────────────────────────────────────────────
# Connector
# ──────────────────────────────────────────────────────────

class VweConnector:
    """
    Playwright-connector voor mijn.vwe.nl.

    VWE is een Angular single-page app. Alle formulieren worden via Angular
    scope-updates bijgewerkt; label.click() triggert de Angular change detection.

    Gebruik als contextmanager:
        async with VweConnector() as vwe:
            await vwe.login()
            ads = await vwe.fetch_advertisement_list()
    """

    BASE = settings.vwe_base_url  # standaard "https://mijn.vwe.nl"

    def __init__(self, headless: bool = True):
        self._headless = headless
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._logged_in = False

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.close()

    # ── Lifecycle ──────────────────────────────────────────

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="nl-NL",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
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

    # ── Inloggen ───────────────────────────────────────────

    async def login(self) -> bool:
        if self._logged_in:
            return True

        if not settings.vwe_username or not settings.vwe_password:
            logger.error("VWE inloggegevens niet ingesteld (VWE_USERNAME / VWE_PASSWORD in .env)")
            return False

        try:
            await self._page.goto(f"{self.BASE}/login", wait_until="networkidle", timeout=30_000)
            await self._page.fill('input[type="email"], input[name="username"]', settings.vwe_username)
            await self._page.fill('input[type="password"], input[name="password"]', settings.vwe_password)
            await self._page.click('button[type="submit"], input[type="submit"]')
            await self._page.wait_for_load_state("networkidle", timeout=20_000)

            # Na login navigeert VWE naar /services/adv/list of een dashboard
            logged_in = "/login" not in self._page.url
            if logged_in:
                self._logged_in = True
                logger.info(f"VWE login geslaagd (url: {self._page.url})")
            else:
                logger.error("VWE login mislukt — controleer VWE_USERNAME en VWE_PASSWORD")
                await self.screenshot_for_debug("/tmp/vwe_login_mislukt.png")
            return logged_in

        except Exception as e:
            logger.error(f"VWE login fout: {e}")
            await self.screenshot_for_debug("/tmp/vwe_login_error.png")
            return False

    # ── Advertentielijst ───────────────────────────────────

    async def fetch_advertisement_list(self) -> list[VweAdvertisement]:
        """
        Haalt alle advertenties op van /services/adv/list.

        De pagina is een Angular-app. De advertenties staan in de Angular scope
        (controller: AdvertisementMaintenanceCtrl) maar ook als DOM-links.
        We lezen beide en combineren ze.
        """
        if not await self.login():
            return []

        try:
            await self._page.goto(f"{self.BASE}/services/adv/list", wait_until="networkidle", timeout=30_000)
            await self._wait_for_content('.search-items, [ng-controller="AdvertisementMaintenanceCtrl"]')
        except Exception as e:
            logger.error(f"VWE advertentielijst laden mislukt: {e}")
            return []

        # Probeer eerst via Angular scope (meest compleet)
        ads_from_scope = await self._fetch_ads_via_scope()
        if ads_from_scope:
            logger.info(f"VWE: {len(ads_from_scope)} advertenties via Angular scope")
            return ads_from_scope

        # Fallback: DOM-scraping
        return await self._fetch_ads_via_dom()

    async def _fetch_ads_via_scope(self) -> list[VweAdvertisement]:
        """Lees advertenties via Angular scope (meest betrouwbaar)."""
        result = await self._page.evaluate("""
            () => {
                const el = document.querySelector('[ng-controller="AdvertisementMaintenanceCtrl"]');
                if (!el) return null;
                const scope = window.angular?.element(el)?.scope?.();
                if (!scope?.advertisements) return null;

                return scope.advertisements.map(adv => {
                    // Zoek veldnamen dynamisch (VWE kan ze aanpassen)
                    const titleKey = Object.keys(adv).find(k =>
                        /title|titel|advertisementtitle/i.test(k) &&
                        typeof adv[k] === 'string' && adv[k].length > 4
                    ) || '';
                    const statusKey = Object.keys(adv).find(k =>
                        /status/i.test(k) && typeof adv[k] === 'string'
                    ) || '';
                    const idKey = Object.keys(adv).find(k =>
                        /^id$|advertisementid|advid/i.test(k)
                    ) || '';
                    const lpKey = Object.keys(adv).find(k =>
                        /kenteken|licenseplate|registration/i.test(k)
                    ) || '';
                    const priceKey = Object.keys(adv).find(k =>
                        /price|prijs|asking/i.test(k)
                    ) || '';

                    return {
                        adv_id: String(adv[idKey] || ''),
                        title: adv[titleKey] || '',
                        status: adv[statusKey] || '',
                        license_plate: adv[lpKey] || '',
                        asking_price: priceKey ? Number(adv[priceKey]) || null : null,
                    };
                }).filter(a => a.adv_id);
            }
        """)

        if not result:
            return []

        ads = []
        for r in result:
            adv = VweAdvertisement(
                adv_id=r["adv_id"],
                title=r["title"],
                status=r.get("status"),
                license_plate=r.get("license_plate") or None,
                asking_price=r.get("asking_price"),
            )
            # Haal merk/model uit de titel
            self._parse_title_into_adv(adv)
            ads.append(adv)

        return ads

    async def _fetch_ads_via_dom(self) -> list[VweAdvertisement]:
        """Fallback: lees advertentie-links uit de DOM."""
        ads = []
        links = await self._page.query_selector_all('a[href*="/services/adv/"]')
        seen_ids = set()

        for link in links:
            href = await link.get_attribute("href") or ""
            m = re.search(r"/services/adv/(\d+)/", href)
            if not m:
                continue
            adv_id = m.group(1)
            if adv_id in seen_ids:
                continue
            seen_ids.add(adv_id)

            title_el = await link.query_selector(".title, [class*='title'], strong, b")
            title = ""
            if title_el:
                title = (await title_el.inner_text()).strip()
            else:
                title = (await link.inner_text()).strip()[:120]

            adv = VweAdvertisement(adv_id=adv_id, title=title)
            self._parse_title_into_adv(adv)
            ads.append(adv)

        logger.info(f"VWE DOM fallback: {len(ads)} advertenties")
        return ads

    def _parse_title_into_adv(self, adv: VweAdvertisement):
        """
        Extraheer merk, model en jaar uit de advertentietitel.
        Zelfde logica als het Tampermonkey script.
        """
        MERKEN = [
            "alfa romeo", "aston martin", "land rover", "mercedes benz", "mercedes-benz",
            "volkswagen", "chevrolet", "citroen", "citroën", "mitsubishi",
            "abarth", "audi", "bmw", "byd", "cupra", "dacia", "ds", "fiat", "ford",
            "honda", "hyundai", "jaguar", "jeep", "kia", "lexus", "maserati", "mazda",
            "mercedes", "mini", "nissan", "opel", "peugeot", "porsche", "renault",
            "seat", "skoda", "smart", "subaru", "suzuki", "tesla", "toyota", "volvo", "vw",
        ]
        title_lower = adv.title.lower()
        for merk in sorted(MERKEN, key=len, reverse=True):
            if merk in title_lower:
                adv.make = merk.title()
                rest = adv.title[title_lower.index(merk) + len(merk):].strip()
                words = rest.split()
                adv.model = words[0] if words else None
                break

        year_match = re.search(r"\b(19[5-9]\d|20[0-3]\d)\b", adv.title)
        if year_match:
            adv.year = int(year_match.group(1))

    # ── Voertuigdetail (vehicleinfo) ───────────────────────

    async def fetch_vehicle_detail(self, adv_id: str) -> Optional[VweVehicle]:
        """
        Haalt gedetailleerde voertuiginfo op van /services/adv/{id}/vehicleinfo.

        Structuur van de vehicleinfo pagina:
        - .vehicle-header h2 of h1  — advertentietitel
        - .registration-number      — kenteken
        - .col-a-40 label           — veldlabels; de waarde staat in een sibling .col-a-60
        - #General_Form_AdvertisementTitleAddendum — titelveld
        """
        if not await self.login():
            return None

        try:
            await self._page.goto(
                f"{self.BASE}/services/adv/{adv_id}/vehicleinfo",
                wait_until="networkidle",
                timeout=30_000,
            )
        except Exception as e:
            logger.error(f"VWE vehicleinfo {adv_id}: {e}")
            return None

        vehicle = VweVehicle(vwe_id=adv_id)

        # Advertentietitel
        title_el = await self._page.query_selector(".vehicle-header h2, .vehicle-header h1")
        if title_el:
            vehicle.title = (await title_el.inner_text()).strip()

        # Titelveld (editable)
        title_field = await self._page.query_selector("#General_Form_AdvertisementTitleAddendum")
        if title_field and not vehicle.title:
            vehicle.title = (await title_field.input_value()).strip()

        # Kenteken
        lp_el = await self._page.query_selector(".registration-number")
        if lp_el:
            vehicle.license_plate = re.sub(r"[^A-Z0-9]", "", (await lp_el.inner_text()).upper())

        # Veldlabels in .col-a-40 → waarden in sibling .col-a-60
        vehicle.year = await self._read_label_value("Bouwjaar", int)
        vehicle.mileage = await self._read_label_value("Kilometerstand", lambda v: int(re.sub(r"\D", "", v)) if v else None)
        vehicle.fuel_type = await self._read_label_value("Brandstof")
        vehicle.color = await self._read_label_value("Kleur")
        vehicle.vin = await self._read_label_value("VIN") or await self._read_label_value("Chassisnummer")

        # APK datum
        apk_raw = await self._read_label_value("APK")
        if apk_raw:
            vehicle.apk_expiry = self._parse_date(apk_raw)

        # Vraagprijs
        price_raw = await self._read_label_value("Vraagprijs") or await self._read_label_value("Verkoopprijs")
        if price_raw:
            try:
                vehicle.asking_price = float(re.sub(r"[^\d,.]", "", price_raw).replace(",", "."))
            except ValueError:
                pass

        # Merk/model uit titel
        if vehicle.title:
            adv = VweAdvertisement(adv_id=adv_id, title=vehicle.title)
            self._parse_title_into_adv(adv)
            vehicle.make = adv.make
            vehicle.model = adv.model
            if not vehicle.year:
                vehicle.year = adv.year

        return vehicle

    async def _read_label_value(self, label_text: str, cast=None):
        """
        Leest een veldwaarde van de vehicleinfo pagina.

        Structuur: <div class="col-a-40"><label>Bouwjaar</label></div>
                   <div class="col-a-60">2021</div>
        """
        result = await self._page.evaluate(
            """(labelText) => {
                const labels = document.querySelectorAll('.col-a-40 label, .row label');
                for (const lbl of labels) {
                    if (lbl.textContent.trim() === labelText) {
                        const parent = lbl.closest('.col-a-40, .row');
                        if (!parent) continue;
                        const sibling = parent.nextElementSibling ||
                                        parent.closest('.row')?.querySelector('.col-a-60');
                        if (sibling) return sibling.textContent.trim();
                    }
                }
                return null;
            }""",
            label_text,
        )
        if result is None:
            return None
        if cast:
            try:
                return cast(result)
            except (ValueError, TypeError):
                return None
        return result or None

    # ── Opties (accessories) ───────────────────────────────

    async def fetch_options(self, adv_id: str) -> list[VweOption]:
        """
        Leest alle opties van /services/adv/{id}/accessories.

        Elke optie is een `label.accessory[title]` element.
        De label.for verwijst naar de bijbehorende checkbox.
        """
        if not await self.login():
            return []

        try:
            await self._page.goto(
                f"{self.BASE}/services/adv/{adv_id}/accessories",
                wait_until="networkidle",
                timeout=30_000,
            )
            await self._wait_for_content("label.accessory[title]", timeout=8_000)
        except PwTimeout:
            logger.warning(f"VWE opties {adv_id}: timeout wachten op label.accessory")
            return []
        except Exception as e:
            logger.error(f"VWE fetch_options {adv_id}: {e}")
            return []

        options = await self._page.evaluate("""
            () => {
                const labels = document.querySelectorAll('label.accessory[title]');
                return [...labels].map(lbl => {
                    const cbId = lbl.getAttribute('for');
                    const cb = cbId ? document.getElementById(cbId) : null;
                    return {
                        checkbox_id: cbId || '',
                        label: lbl.getAttribute('title').trim(),
                        is_checked: cb ? cb.checked : false,
                    };
                }).filter(o => o.label.length > 0);
            }
        """)

        return [VweOption(**o) for o in (options or [])]

    async def set_option(self, adv_id: str, checkbox_id: str, checked: bool) -> bool:
        """
        Zet één optie aan of uit via Angular-klik op het label.
        Verwacht dat de accessories-pagina al geladen is.
        """
        success = await self._page.evaluate(
            """([cbId, checked]) => {
                const cb = document.getElementById(cbId);
                if (!cb) return false;
                if (cb.checked === checked) return true;  // al correct

                // Klik op het label (triggert Angular change detection)
                const label = document.querySelector(`label[for="${cbId}"]`);
                if (label) {
                    label.click();
                    try {
                        const scope = window.angular?.element(label)?.scope?.();
                        if (scope) scope.$apply?.();
                    } catch(e) {}
                    return true;
                }
                return false;
            }""",
            [checkbox_id, checked],
        )
        return bool(success)

    async def save_options(self, adv_id: str) -> bool:
        """Sla de opties op via het formulier op de accessories-pagina."""
        try:
            submitted = await self._page.evaluate("""
                () => {
                    const form = document.querySelector('form[action*="/accessories/save"]');
                    if (!form) return false;
                    form.submit();
                    return true;
                }
            """)
            if submitted:
                await self._page.wait_for_load_state("networkidle", timeout=15_000)
                logger.info(f"VWE opties opgeslagen voor advertentie {adv_id}")
                return True
            logger.warning(f"VWE: geen save-formulier gevonden voor {adv_id}")
        except Exception as e:
            logger.error(f"VWE save_options {adv_id}: {e}")
        return False

    # ── Advertentietitel bijwerken ─────────────────────────

    async def update_advertisement_title(self, adv_id: str, new_title: str) -> bool:
        """
        Schrijft een nieuwe advertentietitel naar het titelveld en slaat op.

        Veld: #General_Form_AdvertisementTitleAddendum
        Formulier: form[action*="/vehicleinfo/save"]
        """
        if not await self.login():
            return False

        try:
            await self._page.goto(
                f"{self.BASE}/services/adv/{adv_id}/vehicleinfo",
                wait_until="networkidle",
                timeout=30_000,
            )

            field = await self._page.query_selector("#General_Form_AdvertisementTitleAddendum")
            if not field:
                logger.warning(f"VWE: titelveld niet gevonden voor {adv_id}")
                return False

            # Angular-aware invullen
            await field.focus()
            await field.fill(new_title)
            await self._page.evaluate(
                """(val) => {
                    const el = document.getElementById('General_Form_AdvertisementTitleAddendum');
                    if (!el) return;
                    el.value = val;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    try {
                        const scope = window.angular?.element(el)?.scope?.();
                        if (scope) {
                            scope.advertisementTitleAddendum = val;
                            scope.$apply?.();
                        }
                    } catch(e) {}
                }""",
                new_title,
            )

            # Opslaan
            submitted = await self._page.evaluate("""
                () => {
                    const form = document.querySelector('form[action*="/vehicleinfo/save"]');
                    if (!form) return false;
                    form.submit();
                    return true;
                }
            """)

            if submitted:
                await self._page.wait_for_load_state("networkidle", timeout=15_000)
                logger.info(f"VWE titel bijgewerkt voor {adv_id}: {new_title[:60]}")
                return True

        except Exception as e:
            logger.error(f"VWE update_advertisement_title {adv_id}: {e}")

        return False

    # ── Batch-operaties ────────────────────────────────────

    async def sync_all_vehicles(self) -> list[VweVehicle]:
        """
        Haal alle actieve advertenties op en verzamel voertuigdetails.
        Gebruik deze methode voor de periodieke sync.
        """
        ads = await self.fetch_advertisement_list()
        if not ads:
            return []

        active = [a for a in ads if not a.status or "verlopen" not in (a.status or "").lower()]
        logger.info(f"VWE: {len(active)} actieve advertenties ophalen...")

        vehicles = []
        for adv in active:
            try:
                vehicle = await self.fetch_vehicle_detail(adv.adv_id)
                if vehicle:
                    # Opties ophalen en als lijst opslaan
                    options = await self.fetch_options(adv.adv_id)
                    vehicle.options = [o.label for o in options if o.is_checked]
                    vehicle.status = adv.status
                    vehicles.append(vehicle)
                    logger.debug(f"VWE {adv.adv_id}: {vehicle.license_plate or vehicle.title[:40]}")
                await asyncio.sleep(0.5)  # beleefd richting VWE server
            except Exception as e:
                logger.error(f"VWE sync {adv.adv_id}: {e}")

        logger.info(f"VWE: {len(vehicles)} voertuigen gesynchroniseerd")
        return vehicles

    # ── Hulpfuncties ───────────────────────────────────────

    async def _wait_for_content(self, selector: str, timeout: int = 10_000):
        try:
            await self._page.wait_for_selector(selector, timeout=timeout)
        except PwTimeout:
            logger.debug(f"VWE: selector '{selector}' niet gevonden binnen {timeout}ms")

    def _parse_date(self, raw: str) -> Optional[date]:
        """Parseer verschillende datumformaten die VWE gebruikt."""
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d %m %Y"):
            try:
                return datetime.strptime(raw.strip(), fmt).date()
            except ValueError:
                continue
        # Probeer alleen maand/jaar (bijv. "12-2025")
        m = re.match(r"(\d{1,2})[-/](\d{4})", raw.strip())
        if m:
            try:
                return date(int(m.group(2)), int(m.group(1)), 1)
            except ValueError:
                pass
        return None

    # ── Debug ──────────────────────────────────────────────

    async def screenshot_for_debug(self, path: str = "/tmp/vwe_debug.png"):
        if self._page:
            try:
                await self._page.screenshot(path=path, full_page=True)
                logger.debug(f"VWE screenshot: {path}")
            except Exception:
                pass

    async def dump_page_structure(self) -> dict:
        """Geeft een overzicht van de huidige pagina-structuur terug (voor debugging)."""
        return await self._page.evaluate("""
            () => ({
                url: location.href,
                title: document.title,
                h1: document.querySelector('h1')?.textContent?.trim() || '',
                h2: document.querySelector('h2')?.textContent?.trim() || '',
                angularControllers: [...document.querySelectorAll('[ng-controller]')]
                    .map(el => el.getAttribute('ng-controller')),
                forms: [...document.querySelectorAll('form[action]')]
                    .map(f => f.getAttribute('action')),
                optionLabels: document.querySelectorAll('label.accessory[title]').length,
                registrationNumber: document.querySelector('.registration-number')?.textContent?.trim() || '',
            })
        """)
