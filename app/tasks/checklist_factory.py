"""
Maakt automatisch checklists aan voor voertuigen op basis van type/status.

Items hebben de volgende velden:
  label      – omschrijving van het controlepunt
  required   – True = verplicht voor goedkeuring
  category   – sectie-indeling (voor weergave en rapportage)
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checklist import Checklist, ChecklistItem, ChecklistType, ChecklistItemStatus
from app.models.vehicle import Vehicle


CHECKLIST_TEMPLATES: dict[str, list[dict]] = {
    "inkoop_controle": [
        {"label": "Kenteken geregistreerd in systeem", "required": True},
        {"label": "VIN gecontroleerd en geregistreerd", "required": True},
        {"label": "Kilometerstand genoteerd", "required": True},
        {"label": "Schade-inspectie uitgevoerd en gefotografeerd", "required": True},
        {"label": "Banden gecontroleerd (profiel + spanning)", "required": True},
        {"label": "Remmen gecontroleerd", "required": True},
        {"label": "Oliepeil gecontroleerd", "required": True},
        {"label": "Koelvloeistof gecontroleerd", "required": False},
        {"label": "Ruitenwisservloeistof gecontroleerd", "required": False},
        {"label": "Accu getest", "required": True},
        {"label": "Airco getest", "required": False},
        {"label": "Verwarming getest", "required": False},
        {"label": "Alle lichten gecontroleerd", "required": True},
        {"label": "Sleutels aanwezig (aantal)", "required": True},
        {"label": "Kentekenbewijs aanwezig", "required": True},
        {"label": "APK-datum gecontroleerd", "required": True},
        {"label": "Onderhoudsboekje aanwezig/gecontroleerd", "required": False},
    ],
    "voorbereiding": [
        {"label": "Voertuig inwendig gereinigd", "required": True},
        {"label": "Voertuig uitwendig gewassen en gepolijst", "required": True},
        {"label": "Ramen gereinigd", "required": True},
        {"label": "Velgen gereinigd", "required": True},
        {"label": "Onderhoud uitgevoerd (olie/filter)", "required": True},
        {"label": "APK aangevraagd / in orde", "required": True},
        {"label": "Schadereparatie afgerond", "required": False},
        {"label": "Carrosserie-herstel afgerond", "required": False},
        {"label": "Technische keuring intern uitgevoerd", "required": True},
        {"label": "Navigatie/software bijgewerkt", "required": False},
        {"label": "Bandenspanning ingesteld", "required": True},
        {"label": "Ruitenwisserbladen gecontroleerd/vervangen", "required": False},
        {"label": "Fotografie voor advertentie gemaakt", "required": True},
        {"label": "Advertentietekst gemaakt", "required": True},
        {"label": "Prijs vastgesteld en ingevoerd in systeem", "required": True},
    ],
    "aflevercheck": [
        {"label": "Voertuig schoon (binnen en buiten)", "required": True},
        {"label": "Tanken / afgesproken brandstofniveau", "required": True},
        {"label": "Kentekenbewijs op naam klant", "required": True},
        {"label": "Verzekering klant actief", "required": True},
        {"label": "Alle sleutels overhandigd", "required": True},
        {"label": "Onderhoudsboekje / garantiebewijs overhandigd", "required": False},
        {"label": "NAP-rapport overhandigd", "required": True},
        {"label": "Klant rondgeleid door voertuig", "required": True},
        {"label": "Klanthandtekening op afleverbon", "required": True},
        {"label": "Betaling ontvangen / financiering afgerond", "required": True},
        {"label": "Navigatie geprogrammeerd op klantadres", "required": False},
        {"label": "Bijzonderheden klant besproken", "required": False},
    ],
    "inruil_taxatie": [
        {"label": "Kenteken en VIN gecontroleerd", "required": True, "category": "Administratief"},
        {"label": "Kilometerstand genoteerd", "required": True, "category": "Administratief"},
        {"label": "NAP-controle uitgevoerd", "required": True, "category": "Administratief"},
        {"label": "Schade-inventarisatie gemaakt", "required": True, "category": "Carrosserie"},
        {"label": "Foto's gemaakt van schade", "required": True, "category": "Carrosserie"},
        {"label": "Technische staat beoordeeld", "required": True, "category": "Technisch"},
        {"label": "APK-datum genoteerd", "required": True, "category": "Administratief"},
        {"label": "Taxatiewaarde bepaald", "required": True, "category": "Administratief"},
        {"label": "Taxatierapport opgemaakt", "required": True, "category": "Administratief"},
        {"label": "Klant geïnformeerd over taxatiewaarde", "required": True, "category": "Administratief"},
    ],

    # ──────────────────────────────────────────────────────────
    # Technische keuring — gedetailleerde technische doorlichting
    # ──────────────────────────────────────────────────────────
    "technische_keuring": [
        # Motor & Aandrijflijn
        {"label": "Motorolie: peil en kwaliteit gecontroleerd", "required": True, "category": "Motor & Aandrijflijn"},
        {"label": "Motorolie: geen bijmenging koelvloeistof (mayonaise)", "required": True, "category": "Motor & Aandrijflijn"},
        {"label": "Koelvloeistof: peil en conditie gecontroleerd", "required": True, "category": "Motor & Aandrijflijn"},
        {"label": "Riem/ketting distributie: staat en vervanginterval gecontroleerd", "required": True, "category": "Motor & Aandrijflijn"},
        {"label": "Motorblok en pakking: geen lekkage zichtbaar", "required": True, "category": "Motor & Aandrijflijn"},
        {"label": "Uitlaat: geen roetuitstoot of ongewone geluiden", "required": True, "category": "Motor & Aandrijflijn"},
        {"label": "Transmissie/versnellingsbak: werking gecontroleerd (alle versnellingen)", "required": True, "category": "Motor & Aandrijflijn"},
        {"label": "Automaat: vloeistofpeil en kleur gecontroleerd", "required": False, "category": "Motor & Aandrijflijn"},
        {"label": "Koppeling: slijtage en werking gecontroleerd", "required": True, "category": "Motor & Aandrijflijn"},
        {"label": "Stuurbekrachtiging: vloeistof en werking gecontroleerd", "required": True, "category": "Motor & Aandrijflijn"},

        # Remsysteem
        {"label": "Remvloeistof: peil en kookpunt gecontroleerd", "required": True, "category": "Remsysteem"},
        {"label": "Remblokken voor: dikte gemeten (minimaal 3mm)", "required": True, "category": "Remsysteem"},
        {"label": "Remblokken achter: dikte gemeten (minimaal 3mm)", "required": True, "category": "Remsysteem"},
        {"label": "Remschijven voor: slijtage en beschadigingen gecontroleerd", "required": True, "category": "Remsysteem"},
        {"label": "Remschijven achter: slijtage en beschadigingen gecontroleerd", "required": True, "category": "Remsysteem"},
        {"label": "Handrem/elektrisch parkeerrem: werking gecontroleerd", "required": True, "category": "Remsysteem"},
        {"label": "ABS: werking gecontroleerd (geen foutcodes)", "required": True, "category": "Remsysteem"},
        {"label": "Remslangen: geen scheuren of slijtage", "required": True, "category": "Remsysteem"},

        # Wielophanging & Stuurinrichting
        {"label": "Schokdempers voor: geen lekkage, werking gecontroleerd", "required": True, "category": "Ophanging & Stuur"},
        {"label": "Schokdempers achter: geen lekkage, werking gecontroleerd", "required": True, "category": "Ophanging & Stuur"},
        {"label": "Draagarm rubbers: staat gecontroleerd", "required": True, "category": "Ophanging & Stuur"},
        {"label": "Kogelgewrichten: speling gecontroleerd", "required": True, "category": "Ophanging & Stuur"},
        {"label": "Stuurhuis/stuurstangen: speling en lekkage gecontroleerd", "required": True, "category": "Ophanging & Stuur"},
        {"label": "Wiellagerspeling: gecontroleerd alle vier de wielen", "required": True, "category": "Ophanging & Stuur"},
        {"label": "Spoorstangen: staat gecontroleerd", "required": True, "category": "Ophanging & Stuur"},
        {"label": "Wieluitlijning: gecontroleerd / aanbevolen", "required": False, "category": "Ophanging & Stuur"},

        # Banden & Velgen
        {"label": "Banden voor: profieldiepte gemeten (min. 1,6mm, aanbevolen 3mm+)", "required": True, "category": "Banden & Velgen"},
        {"label": "Banden achter: profieldiepte gemeten", "required": True, "category": "Banden & Velgen"},
        {"label": "Banden: gelijkmatige slijtage, geen beschadigingen of bobbels", "required": True, "category": "Banden & Velgen"},
        {"label": "Bandenspanning alle vier de wielen ingesteld", "required": True, "category": "Banden & Velgen"},
        {"label": "Reservewiel / punctuurset aanwezig en in orde", "required": True, "category": "Banden & Velgen"},
        {"label": "Velgen: geen barsten of ernstige schade", "required": True, "category": "Banden & Velgen"},
        {"label": "Wielmoeren: aangedraaid op juist aanhaalmoment", "required": True, "category": "Banden & Velgen"},

        # Elektrisch & Elektronica
        {"label": "Accu: spanning en capaciteit gemeten (CCA-test)", "required": True, "category": "Elektrisch"},
        {"label": "Dynamo: laadspanning gecontroleerd (13,8–14,4V)", "required": True, "category": "Elektrisch"},
        {"label": "OBD-uitlezing: geen actieve foutcodes", "required": True, "category": "Elektrisch"},
        {"label": "Alle buitenverlichting gecontroleerd (koplamp, achterlicht, richtingaanwijzer)", "required": True, "category": "Elektrisch"},
        {"label": "Remlichten gecontroleerd", "required": True, "category": "Elektrisch"},
        {"label": "Achteruitrijlicht gecontroleerd", "required": True, "category": "Elektrisch"},
        {"label": "Knipperlichten (alle vier) gecontroleerd", "required": True, "category": "Elektrisch"},
        {"label": "Mistlampen voor/achter gecontroleerd", "required": False, "category": "Elektrisch"},
        {"label": "Dashboard-indicatielampjes: geen ongewenste lampjes aan", "required": True, "category": "Elektrisch"},
        {"label": "Ruitenwissers voor: werking en staan van rubbers", "required": True, "category": "Elektrisch"},
        {"label": "Ruitenwisser achter: werking en rubber", "required": False, "category": "Elektrisch"},
        {"label": "Ruitensproeiinstallatie: vloeistof en werking", "required": True, "category": "Elektrisch"},
        {"label": "Claxon gecontroleerd", "required": True, "category": "Elektrisch"},
        {"label": "Centrale vergrendeling: alle deuren gecontroleerd", "required": True, "category": "Elektrisch"},
        {"label": "Elektrische ramen: alle ramen gecontroleerd", "required": False, "category": "Elektrisch"},
        {"label": "Verwarmde voorruit / spiegels: werking gecontroleerd", "required": False, "category": "Elektrisch"},

        # Klimaat & Comfort
        {"label": "Airconditioning: koeling gecontroleerd en getest", "required": True, "category": "Klimaat & Comfort"},
        {"label": "Airco: geen olie-/koudemiddellekkage", "required": True, "category": "Klimaat & Comfort"},
        {"label": "Verwarming: alle zones werken", "required": True, "category": "Klimaat & Comfort"},
        {"label": "Ventilatie: alle standen en luchtuitvoeren werken", "required": True, "category": "Klimaat & Comfort"},
        {"label": "Parkeersensoren voor/achter: werking gecontroleerd", "required": False, "category": "Klimaat & Comfort"},
        {"label": "Achteruitrijcamera: werking en beeld gecontroleerd", "required": False, "category": "Klimaat & Comfort"},

        # Koetswerk & Onderzijde (technisch)
        {"label": "Onderzijde: geen actieve roestvorming of doorgeroest", "required": True, "category": "Onderzijde"},
        {"label": "Uitlaatsysteem: geen lekkage, bevestiging en staat gecontroleerd", "required": True, "category": "Onderzijde"},
        {"label": "Remmen/aandrijfassen: geen olielekkage op de onderzijde", "required": True, "category": "Onderzijde"},
        {"label": "Carrosserie-bodemplaat: geen ernstige deuken of scheurvorming", "required": True, "category": "Onderzijde"},
        {"label": "Draagconstructie (chassis): geen onregelmatigheden of laswerk door schade", "required": True, "category": "Onderzijde"},

        # APK & Administratief
        {"label": "APK geldig of aangevraagd", "required": True, "category": "APK & Administratief"},
        {"label": "APK-keuring afgerond zonder afkeurpunten", "required": True, "category": "APK & Administratief"},
        {"label": "NAP-rapport gecontroleerd (geen km-fraude signalen)", "required": True, "category": "APK & Administratief"},
        {"label": "Brandstoftype correct ingesteld in systeem", "required": True, "category": "APK & Administratief"},
        {"label": "Proefrit van minimaal 10 km gereden", "required": True, "category": "APK & Administratief"},
        {"label": "Bevindingen proefrit genoteerd", "required": True, "category": "APK & Administratief"},
    ],

    # ──────────────────────────────────────────────────────────
    # Cosmetische keuring — uiterlijk en presentatie
    # ──────────────────────────────────────────────────────────
    "cosmetische_keuring": [
        # Exterieur
        {"label": "Motorkap: deuken, krassen, lak-/verfschade", "required": True, "category": "Exterieur — Voor"},
        {"label": "Voorbumper: schade, krassen, montageclips volledig", "required": True, "category": "Exterieur — Voor"},
        {"label": "Koplampglazen: helder (niet vergeeld of gebarsten)", "required": True, "category": "Exterieur — Voor"},
        {"label": "Grille en sierlijsten voor: compleet en onbeschadigd", "required": False, "category": "Exterieur — Voor"},
        {"label": "Voorruit: geen barsten, steenslag of ernstige krassen", "required": True, "category": "Exterieur — Voor"},
        {"label": "Ruitenwisserbladen voor: niet verouderd of streperig", "required": True, "category": "Exterieur — Voor"},

        {"label": "Linker voorscherm: deuken, roestvorming, lakschade", "required": True, "category": "Exterieur — Links"},
        {"label": "Linker voordeur: lakschade, deuken, werking deurgreep en -scharnier", "required": True, "category": "Exterieur — Links"},
        {"label": "Linker achterportier/paneel: lakschade en deuken", "required": True, "category": "Exterieur — Links"},
        {"label": "Linker achterspatbord: roestvorming en lakschade", "required": True, "category": "Exterieur — Links"},
        {"label": "Linker buitenspiegel: spiegelglas aanwezig, behuizing onbeschadigd, inklapbaar", "required": True, "category": "Exterieur — Links"},
        {"label": "Dorpels links: roest, deuken, sierlijsten compleet", "required": True, "category": "Exterieur — Links"},

        {"label": "Rechter voorscherm: deuken, roestvorming, lakschade", "required": True, "category": "Exterieur — Rechts"},
        {"label": "Rechter voordeur: lakschade, deuken, werking deurgreep en -scharnier", "required": True, "category": "Exterieur — Rechts"},
        {"label": "Rechter achterportier/paneel: lakschade en deuken", "required": True, "category": "Exterieur — Rechts"},
        {"label": "Rechter achterspatbord: roestvorming en lakschade", "required": True, "category": "Exterieur — Rechts"},
        {"label": "Rechter buitenspiegel: spiegelglas aanwezig, behuizing onbeschadigd, inklapbaar", "required": True, "category": "Exterieur — Rechts"},
        {"label": "Dorpels rechts: roest, deuken, sierlijsten compleet", "required": True, "category": "Exterieur — Rechts"},

        {"label": "Dak: deuken, roestvorming, lakschade", "required": True, "category": "Exterieur — Boven"},
        {"label": "Panoramadak/schuifdak: werking, rubber afdichting geen lekkage", "required": False, "category": "Exterieur — Boven"},
        {"label": "Antenne aanwezig en onbeschadigd", "required": False, "category": "Exterieur — Boven"},

        {"label": "Kofferdeksel/achterklep: lakschade, deuken, scharnierwering", "required": True, "category": "Exterieur — Achter"},
        {"label": "Achterbumper: schade, krassen, montageclips volledig", "required": True, "category": "Exterieur — Achter"},
        {"label": "Achterlichtunits: niet vergeeld, geen barsten, werking ok", "required": True, "category": "Exterieur — Achter"},
        {"label": "Uitlaatpijp(en): niet roestig, presentatie in orde", "required": False, "category": "Exterieur — Achter"},
        {"label": "Achterruit: geen barsten of ernstige krassen", "required": True, "category": "Exterieur — Achter"},
        {"label": "Ruitenwisser achter: rubber niet verouderd", "required": False, "category": "Exterieur — Achter"},
        {"label": "Trekhaak: aanwezig en staat (indien van toepassing)", "required": False, "category": "Exterieur — Achter"},

        # Velgen & Banden cosmetisch
        {"label": "Velgen voor: geen ernstige kerb damage of lakschade", "required": True, "category": "Velgen & Banden"},
        {"label": "Velgen achter: geen ernstige kerb damage of lakschade", "required": True, "category": "Velgen & Banden"},
        {"label": "Wielkapppen/wieldoppen: aanwezig en onbeschadigd", "required": False, "category": "Velgen & Banden"},
        {"label": "Banden: gelijkmatig slijtageprofiel, geen kale plekken", "required": True, "category": "Velgen & Banden"},

        # Interieur
        {"label": "Bestuurdersstoel: slijtage, scheuren, vlekken", "required": True, "category": "Interieur — Stoelen"},
        {"label": "Bijrijdersstoel: slijtage, scheuren, vlekken", "required": True, "category": "Interieur — Stoelen"},
        {"label": "Achterbank: slijtage, scheuren, vlekken", "required": True, "category": "Interieur — Stoelen"},
        {"label": "Gordels alle zitplaatsen: werking en staat", "required": True, "category": "Interieur — Stoelen"},
        {"label": "Hoofdsteunen: aanwezig en onbeschadigd", "required": True, "category": "Interieur — Stoelen"},

        {"label": "Dashboard: geen barsten, losse onderdelen of beschadigingen", "required": True, "category": "Interieur — Dashboard"},
        {"label": "Stuurwiel: slijtage en staat leerwerk/bekleding", "required": True, "category": "Interieur — Dashboard"},
        {"label": "Middenconsole en opbergvakken: compleet en onbeschadigd", "required": True, "category": "Interieur — Dashboard"},
        {"label": "Infotainmentsysteem: scherm, knoppen en speakers werken", "required": True, "category": "Interieur — Dashboard"},
        {"label": "Navigatie aanwezig en up-to-date (kaarten bijgewerkt)", "required": False, "category": "Interieur — Dashboard"},
        {"label": "Achteruitrijcamera-beeld: helder en niet beschadigd", "required": False, "category": "Interieur — Dashboard"},

        {"label": "Vloermatten: aanwezig (origineel), niet versleten of gescheurd", "required": True, "category": "Interieur — Vloer & Hemelbekleding"},
        {"label": "Tapijt: geen ernstige vlekken of slijtage", "required": True, "category": "Interieur — Vloer & Hemelbekleding"},
        {"label": "Hemelbekleding: geen vlekken, loslatende delen of waterinfiltratie", "required": True, "category": "Interieur — Vloer & Hemelbekleding"},
        {"label": "A-, B- en C-stijlbekleding: niet loslatend of beschadigd", "required": True, "category": "Interieur — Vloer & Hemelbekleding"},
        {"label": "Deurpanelen alle deuren: complete bekleding, deurrubbers intact", "required": True, "category": "Interieur — Vloer & Hemelbekleding"},

        {"label": "Kofferbak: vloerbedekking compleet, geen geur, geen waterinfiltratie", "required": True, "category": "Interieur — Kofferbak"},
        {"label": "Kofferbak: opbergvak reservewiel bereikbaar", "required": True, "category": "Interieur — Kofferbak"},
        {"label": "Kofferbakverlichting werkt", "required": False, "category": "Interieur — Kofferbak"},

        # Reiniging & Presentatie
        {"label": "Exterieur: gewassen, gedroogd en polished", "required": True, "category": "Reiniging & Presentatie"},
        {"label": "Velgen: schoon en ontvet", "required": True, "category": "Reiniging & Presentatie"},
        {"label": "Ramen binnen en buiten: streepvrij gereinigd", "required": True, "category": "Reiniging & Presentatie"},
        {"label": "Interieur: gestofzuigd en afgenomen", "required": True, "category": "Reiniging & Presentatie"},
        {"label": "Leder/kunstleder: geconditioneerd/behandeld", "required": False, "category": "Reiniging & Presentatie"},
        {"label": "Kofferbak: uitgestofzuigd en gereinigd", "required": True, "category": "Reiniging & Presentatie"},
        {"label": "Motorkap binnenste: gereinigd en gederst", "required": False, "category": "Reiniging & Presentatie"},
        {"label": "Geuren geëlimineerd (geen rookgeur, huisdierlucht e.d.)", "required": True, "category": "Reiniging & Presentatie"},
        {"label": "Fotografie voor advertentie: exterieur alle zijden", "required": True, "category": "Reiniging & Presentatie"},
        {"label": "Fotografie voor advertentie: interieur dashboard, stoelen, kofferbak", "required": True, "category": "Reiniging & Presentatie"},
    ],

    # ──────────────────────────────────────────────────────────
    # Rijklaar maken — gecombineerde technisch + cosmetisch
    # ──────────────────────────────────────────────────────────
    "rijklaar_maken": [
        # ── Technische controles ──
        {"label": "OBD-uitlezing: geen actieve foutcodes", "required": True, "category": "Technisch — Motor & Systemen"},
        {"label": "Motorolie: peil en kwaliteit OK", "required": True, "category": "Technisch — Motor & Systemen"},
        {"label": "Koelvloeistof: peil en conditie OK", "required": True, "category": "Technisch — Motor & Systemen"},
        {"label": "Ruitensproeiervloeistof bijgevuld", "required": True, "category": "Technisch — Motor & Systemen"},
        {"label": "Remvloeistof: peil OK", "required": True, "category": "Technisch — Motor & Systemen"},
        {"label": "Stuurbekrachtigingsvloeistof: peil OK (indien van toepassing)", "required": False, "category": "Technisch — Motor & Systemen"},
        {"label": "Distributieriem/-ketting: vervanginterval gecontroleerd", "required": True, "category": "Technisch — Motor & Systemen"},
        {"label": "Geen zichtbare lekkages (motorolie, koelvloeistof, remvloeistof)", "required": True, "category": "Technisch — Motor & Systemen"},

        {"label": "Remblokken voor: minimaal 4mm resterende dikte", "required": True, "category": "Technisch — Rem & Ophanging"},
        {"label": "Remblokken achter: minimaal 4mm resterende dikte", "required": True, "category": "Technisch — Rem & Ophanging"},
        {"label": "Remschijven: geen ernstige groeven of rand", "required": True, "category": "Technisch — Rem & Ophanging"},
        {"label": "Schokdempers: geen lekkage, werking OK", "required": True, "category": "Technisch — Rem & Ophanging"},
        {"label": "Stuurinrichting: geen overmatige speling", "required": True, "category": "Technisch — Rem & Ophanging"},
        {"label": "Wiellagerspeling: alle vier de wielen OK", "required": True, "category": "Technisch — Rem & Ophanging"},

        {"label": "Banden: minimaal 3mm profiel alle vier", "required": True, "category": "Technisch — Banden"},
        {"label": "Banden: geen beschadigingen, bobbels of onregelmatige slijtage", "required": True, "category": "Technisch — Banden"},
        {"label": "Bandenspanning ingesteld (zie typeplaat)", "required": True, "category": "Technisch — Banden"},
        {"label": "Reservewiel/punctuurset aanwezig", "required": True, "category": "Technisch — Banden"},

        {"label": "Accu getest (CCA): voldoende capaciteit", "required": True, "category": "Technisch — Elektrisch"},
        {"label": "Alle verlichting werkt (koplamp, achterlicht, richtingaanwijzers, remlichten)", "required": True, "category": "Technisch — Elektrisch"},
        {"label": "Ruitenwissers: werking en staat rubbers OK", "required": True, "category": "Technisch — Elektrisch"},
        {"label": "Airconditioning: koeling werkt correct", "required": True, "category": "Technisch — Elektrisch"},
        {"label": "Dashboard: geen storingslampen actief", "required": True, "category": "Technisch — Elektrisch"},
        {"label": "Centrale vergrendeling en elektrische ramen werken", "required": True, "category": "Technisch — Elektrisch"},

        {"label": "APK geldig of aangevraagd en goedgekeurd", "required": True, "category": "Technisch — APK & Proefrit"},
        {"label": "NAP-controle: geen fraude-indicaties", "required": True, "category": "Technisch — APK & Proefrit"},
        {"label": "Proefrit (min. 10 km) uitgevoerd: motor, versnellingsbak, remmen OK", "required": True, "category": "Technisch — APK & Proefrit"},

        # ── Cosmetisch exterieur ──
        {"label": "Motorkap: geen deuken of lakschade", "required": True, "category": "Cosmetisch — Exterieur"},
        {"label": "Voorbumper: geen ernstige schade of ontbrekende delen", "required": True, "category": "Cosmetisch — Exterieur"},
        {"label": "Koetswerk links: geen onacceptabele deuken of lakschade", "required": True, "category": "Cosmetisch — Exterieur"},
        {"label": "Koetswerk rechts: geen onacceptabele deuken of lakschade", "required": True, "category": "Cosmetisch — Exterieur"},
        {"label": "Dak: geen deuken of beschadigingen", "required": True, "category": "Cosmetisch — Exterieur"},
        {"label": "Kofferdeksel: geen deuken of lakschade", "required": True, "category": "Cosmetisch — Exterieur"},
        {"label": "Achterbumper: geen ernstige schade", "required": True, "category": "Cosmetisch — Exterieur"},
        {"label": "Alle ruiten: geen barsten of ernstige steenslag", "required": True, "category": "Cosmetisch — Exterieur"},
        {"label": "Buitenspiegels: compleet en onbeschadigd", "required": True, "category": "Cosmetisch — Exterieur"},
        {"label": "Velgen: geen ernstige kerb damage", "required": True, "category": "Cosmetisch — Exterieur"},

        # ── Cosmetisch interieur ──
        {"label": "Stoelen: geen ernstige slijtage, scheuren of vlekken", "required": True, "category": "Cosmetisch — Interieur"},
        {"label": "Dashboard: geen barsten of losse onderdelen", "required": True, "category": "Cosmetisch — Interieur"},
        {"label": "Stuurwiel: geen ernstige slijtage", "required": True, "category": "Cosmetisch — Interieur"},
        {"label": "Infotainment: scherm en knoppen functioneel", "required": True, "category": "Cosmetisch — Interieur"},
        {"label": "Hemelbekleding: geen vlekken of loslatende delen", "required": True, "category": "Cosmetisch — Interieur"},
        {"label": "Kofferbak: schoon en compleet", "required": True, "category": "Cosmetisch — Interieur"},
        {"label": "Geen ongewenste geur in interieur", "required": True, "category": "Cosmetisch — Interieur"},

        # ── Reiniging & Presentatie ──
        {"label": "Exterieur: volledig gewassen en gepolijst", "required": True, "category": "Reiniging & Presentatie"},
        {"label": "Interieur: gestofzuigd, afgenomen, ramen streepvrij", "required": True, "category": "Reiniging & Presentatie"},
        {"label": "Velgen: schoon", "required": True, "category": "Reiniging & Presentatie"},
        {"label": "Foto's voor advertentie gemaakt", "required": True, "category": "Reiniging & Presentatie"},

        # ── Administratief ──
        {"label": "Kilometerstand definitief geregistreerd in systeem", "required": True, "category": "Administratief"},
        {"label": "Vraagprijs vastgesteld en ingevoerd", "required": True, "category": "Administratief"},
        {"label": "Sleutels (aantal): geregistreerd", "required": True, "category": "Administratief"},
        {"label": "Onderhoudsboekje aanwezig / digitaal beschikbaar", "required": False, "category": "Administratief"},
        {"label": "Garantiebepalingen vastgesteld", "required": True, "category": "Administratief"},
        {"label": "Voertuig status in systeem bijgewerkt naar 'Klaar voor verkoop'", "required": True, "category": "Administratief"},
    ],
}


async def create_vehicle_checklist(
    db: AsyncSession,
    vehicle: Vehicle,
    checklist_type_str: str,
    assigned_to: str = None,
    work_order_id: int = None,
) -> Checklist:
    """Maak een nieuwe checklist aan voor een voertuig."""

    type_map = {
        "inkoop_controle": ChecklistType.INKOOP_CONTROLE,
        "voorbereiding": ChecklistType.VOORBEREIDING,
        "aflevercheck": ChecklistType.AFLEVERCHECK,
        "apk_voorbereiding": ChecklistType.APK_VOORBEREIDING,
        "inruil_taxatie": ChecklistType.INRUIL_TAXATIE,
        "technische_keuring": ChecklistType.TECHNISCHE_KEURING,
        "cosmetische_keuring": ChecklistType.COSMETISCHE_KEURING,
        "rijklaar_maken": ChecklistType.RIJKLAAR_MAKEN,
    }

    checklist_type = type_map.get(checklist_type_str, ChecklistType.VOORBEREIDING)
    template = CHECKLIST_TEMPLATES.get(checklist_type_str, [])

    title_map = {
        ChecklistType.INKOOP_CONTROLE: "Inkoop-controle",
        ChecklistType.VOORBEREIDING: "Voorbereiding voor verkoop",
        ChecklistType.AFLEVERCHECK: "Aflevercheck",
        ChecklistType.APK_VOORBEREIDING: "APK-voorbereiding",
        ChecklistType.INRUIL_TAXATIE: "Inruil / taxatie",
        ChecklistType.TECHNISCHE_KEURING: "Technische keuring",
        ChecklistType.COSMETISCHE_KEURING: "Cosmetische keuring",
        ChecklistType.RIJKLAAR_MAKEN: "Rijklaar maken",
    }

    vehicle_desc = f"{vehicle.make or ''} {vehicle.model or ''} ({vehicle.license_plate or 'geen kenteken'})".strip()
    title = f"{title_map[checklist_type]} — {vehicle_desc}"

    checklist = Checklist(
        vehicle_id=vehicle.id,
        work_order_id=work_order_id,
        checklist_type=checklist_type,
        title=title,
        assigned_to=assigned_to,
    )
    db.add(checklist)
    await db.flush()

    for i, item_def in enumerate(template):
        item = ChecklistItem(
            checklist_id=checklist.id,
            order=i,
            category=item_def.get("category"),
            label=item_def["label"],
            is_required=item_def["required"],
            status=ChecklistItemStatus.NIET_GECONTROLEERD,
        )
        db.add(item)

    await db.flush()
    return checklist
