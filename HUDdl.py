#!/usr/bin/env python3
"""
HUDdl.py — v6.4
─────────────────────────────────────────────────────────────────────────────
Changes from v6.3:
  • DEEP CRAWL — the crawler now follows "next page" pagination links AND
    the property-detail links inside directory pages, instead of scraping
    only the single entry URL per site. Limits (env-tunable):
        MAX_PAGES_PER_SITE    (default 15)  pages fetched per plain site
        MAX_JS_PAGES_PER_SITE (default 5)   pages rendered per JS site
        CONCURRENT_SITES      (default 6)   sites crawled in parallel
    First crawl now takes ~1–2 minutes (still cached for CACHE_TTL hours).

Changes from v6.2:
  • HEADLESS BROWSER — JS-only sites (apartments.com, electriclofts, etc.)
    are now rendered in headless Chromium via Playwright, so their actual
    listings are extracted instead of a "view on site" link card.
    Requires:  pip install playwright  &&  playwright install chromium
    On Render, set the Build Command to:
        pip install -r requirements.txt && playwright install --with-deps chromium
    Set env HEADLESS=0 to disable (falls back to v6.2 link cards).

Changes from v6.1:
  • ALAMEDA COUNTY FILTER — every result (web + HUD) is now checked against
    Alameda County cities, ZIP ranges, and state before entering the cache.
    Fixes out-of-state results (hud_data.json is full of name-collision
    records: "Dublin Village" in Alabama, "Albany Housing" in Georgia, etc.)
  • Table extractor no longer stops at the first matching table — it now
    collects units from ALL tables on a page.
  • Card extractor cap raised 40 → 100 and all selectors are scanned.
  • Dedup key widened — previously (beds, price, sqft) collapsed distinct
    units that shared specs (and collapsed ALL units with empty specs).
  • NEW directory extractor — property-directory pages (midpen, EAH, EBALDC,
    Wilson PM, Seville, CRPM, …) used to collapse into ONE fallback card.
    Now each property card with a link becomes its own result.
  • Removed diabloviewaptliving.com — that property is in Concord
    (Contra Costa County), not Alameda County.
"""

import asyncio, csv, io, json, os, re, smtplib, sys, threading, time, urllib.parse

SYNONYMS: dict[str, list[str]] = {
    "studio":["studio","eff","efficiency","bachelor","0br","0 br","0bed","0 bed","open plan","single room"],
    "1 bedroom":["1 bed","1bed","1br","1 br","one bed","one bedroom","1b","one-bedroom","1-bed","1-br","1 b/r","single bedroom"],
    "2 bedroom":["2 bed","2bed","2br","2 br","two bed","two bedroom","2b","two-bedroom","2-bed","2-br","2 b/r","double bedroom"],
    "3 bedroom":["3 bed","3bed","3br","3 br","three bed","three bedroom","3b","three-bedroom","3-bed","3-br","3 b/r"],
    "4 bedroom":["4 bed","4bed","4br","4 br","four bed","four bedroom","4b"],
    "5 bedroom":["5 bed","5bed","5br","5 br","five bed","five bedroom","5b"],
    "1 bathroom":["1 bath","1bath","1ba","1 ba","one bath","one bathroom","1 full bath","1.0 bath"],
    "2 bathroom":["2 bath","2bath","2ba","2 ba","two bath","two bathroom","2 full bath","2.0 bath"],
    "half bath":["half bath","half-bath","0.5 bath","powder room","lavatory"],
    "apartment":["apartment","apt","flat","unit","suite","rental"],
    "townhouse":["townhouse","townhome","town home","town house","th","rowhouse","row house","attached home"],
    "condo":["condo","condominium","co-op","coop","cooperative"],
    "house":["house","home","single family","sfr","single-family","detached","residence","bungalow","cottage"],
    "duplex":["duplex","duplex unit","2-unit","two-unit","half duplex"],
    "loft":["loft","industrial loft","open loft","warehouse loft"],
    "room":["room","room for rent","boarding","shared","housemate","roommate","rooms","furnished room"],
    "affordable":["affordable","low income","low-income","income restricted","income-restricted","income based","income-based","subsidized","below market","below-market","bmi","reduced rent","ami","area median income"],
    "section 8":["section 8","section8","s8","hcv","housing choice voucher","voucher","housing voucher","hap","housing assistance"],
    "public housing":["public housing","ph","pha","housing authority","government housing","hud housing"],
    "lihtc":["lihtc","tax credit","low income housing tax credit","tax credit property","affordable tax credit","htc"],
    "hud":["hud","department of housing","housing and urban development","federal housing","hud assisted","hud property"],
    "usda":["usda","rural housing","rural development","rd housing","rural rental"],
    "senior housing":["senior","seniors","elderly","55+","62+","age restricted","age-restricted","retirement","independent living","senior living","senior community"],
    "disabled":["disabled","disability","ada","accessible","handicap","handicapped","wheelchair","mobility impaired","section 811","811"],
    "veteran":["veteran","veterans","vash","va housing","military housing","vet","vets","hud-vash","hudvash"],
    "homeless":["homeless","transitional","transitional housing","shelter","emergency housing","coc","continuum of care","rapid rehousing","supportive housing"],
    "family":["family","families","family housing","family friendly","children","kids","child","with kids"],
    "parking":["parking","garage","carport","car port","covered parking","assigned parking","off-street","parking space"],
    "laundry":["laundry","washer","dryer","w/d","w/d hookup","laundry room","in-unit laundry","coin laundry"],
    "pet friendly":["pet","pets","pet friendly","pet-friendly","dogs allowed","cats allowed","dog friendly","cat friendly","pets ok","pets welcome"],
    "ac":["ac","a/c","air conditioning","air conditioner","central air","central a/c","cooling","air-conditioned"],
    "pool":["pool","swimming pool","community pool","lap pool"],
    "gym":["gym","fitness","fitness center","workout room","exercise room","fitness room","weight room"],
    "furnished":["furnished","fully furnished","turnkey","turn key","furniture included"],
    "available":["available","available now","immediate","immediately","move in ready","move-in ready","vacant","open","ready now","for rent","for lease","leasing now","now leasing"],
    "waiting list":["waiting list","waitlist","wait list","no vacancy","coming soon","not available","call for availability"],
    "oakland":["oakland","oak","east oakland","west oakland","north oakland","temescal","fruitvale","montclair","rockridge","grand lake","lake merritt","downtown oakland"],
    "berkeley":["berkeley","berk","north berkeley","south berkeley","west berkeley","downtown berkeley","uc berkeley","cal"],
    "fremont":["fremont","frem","mission san jose","warm springs","irvington","centerville","niles","ardenwood"],
    "hayward":["hayward","hay","south hayward","mt eden","fairview"],
    "san leandro":["san leandro","sl","san leandro hills"],
    "alameda":["alameda","the island","bay farm"],
    "livermore":["livermore","liv","livermore valley","tri-valley"],
    "pleasanton":["pleasanton","stoneridge"],
    "dublin":["dublin","dub","emerald glen","fallon"],
    "union city":["union city","uc","decoto"],
    "newark":["newark"],
    "emeryville":["emeryville","emery"],
    "castro valley":["castro valley","cv"],
    "short term":["short term","short-term","month to month","month-to-month","mtm","m2m","flexible lease","no lease","temporary"],
    "long term":["long term","long-term","annual","year lease","12 month","12-month","yearly"],
    "new construction":["new construction","new build","newly built","brand new","new development","new apartments","just built"],
    "application":["application","apply","apply now","rental application","leasing office","apply online"],
    "no credit check":["no credit check","no credit","credit flexible","bad credit ok","second chance"],
    "utilities included":["utilities included","all bills paid","all utilities","util incl","water included","heat included"],
    "large":["large","spacious","roomy","big","oversized","xl","extra large"],
    "small":["small","cozy","compact","tiny","micro","intimate"],
}

_ALIAS_MAP: dict[str, str] = {}
for _can, _aliases in SYNONYMS.items():
    for _a in _aliases:
        _ALIAS_MAP[_a.lower()] = _can
    _ALIAS_MAP[_can.lower()] = _can

def _expand(query: str) -> list[str]:
    q = query.lower().strip()
    terms: set[str] = {q}
    if q in _ALIAS_MAP:
        terms.update(a.lower() for a in SYNONYMS[_ALIAS_MAP[q]])
    tokens = re.split(r"[\s,/]+", q)
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        terms.add(tok)
        if tok in _ALIAS_MAP:
            terms.update(a.lower() for a in SYNONYMS[_ALIAS_MAP[tok]])
    for i in range(len(tokens) - 1):
        bigram = f"{tokens[i]} {tokens[i+1]}"
        if bigram in _ALIAS_MAP:
            terms.update(a.lower() for a in SYNONYMS[_ALIAS_MAP[bigram]])
    return list(terms)

from dataclasses import asdict, dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

try:
    import aiohttp
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "aiohttp", "beautifulsoup4", "--quiet"])
    import aiohttp
    from bs4 import BeautifulSoup

# Playwright is optional — without it, JS-only sites degrade to link cards.
try:
    from playwright.async_api import async_playwright
    _PLAYWRIGHT_OK = True
except ImportError:
    _PLAYWRIGHT_OK = False

# ── Config ────────────────────────────────────────────────────────────────────

CACHE_TTL         = int(os.environ.get("CACHE_TTL_HOURS", 6)) * 3600
REQUEST_STAGGER_S = 0.4
MAX_RETRIES       = 2

# Deep-crawl limits (v6.4)
MAX_PAGES_PER_SITE    = int(os.environ.get("MAX_PAGES_PER_SITE", 15))
MAX_JS_PAGES_PER_SITE = int(os.environ.get("MAX_JS_PAGES_PER_SITE", 5))
CONCURRENT_SITES      = int(os.environ.get("CONCURRENT_SITES", 6))

WEB_URLS: list[str] = [
    "https://www.affordablehousing.com/alameda-county-ca/",
    "https://alderwoodapartments.rentals/availability/",
    "https://www.trinitywayapts.com/apartments/ca/fremont/floor-plans",
    "https://parktowerapartments.eprodesse.com/floorplans",
    "https://elevatetomillspringspark.com/floor-plans",
    "https://ebaldc.org/property",
    "https://capstone-props.com/availability",
    "https://brookvalechateau.com/floorplans",
    "https://edfeontheblvd.com",
    "https://www.waterstonefremont.com/apartments/ca/fremont/floor-plans",
    "https://www.wilsonpm.com/rentals",
    "https://www.sevillepropertymanagement.com/vacancies",
    "https://www.midpen-housing.org/find-housing/",
    "https://eahhousing.org/apartment-search/",
    "https://www.esring.com/searchlisting",
    "https://andersenjung.com/rental-property/",
    "https://www.ptlamgmt.com/hayward/peppertree-apartments/conventional/",
    "https://www.fountainsatemeraldpark.com/dublin/fountains-at-emerald-park/conventional/",
    # REMOVED (v6.2): https://www.diabloviewaptliving.com/concord/... — Concord
    # is in Contra Costa County, not Alameda County.
    "https://www.oaklandpropertymanagement.co/tenants/",
    "https://www.livermoregardensapts.com/apartments/ca/livermore/floor-plans",
    "https://www.electriclofts.com/floorplans",
    "https://www.apartments.com/alameda-county-ca/",
    "https://www.crpmrealty.com/availability",
    "https://www.mosaicaptsonmission.com/floorplans",
    "https://www.oaktreepropertygroup.com/oakland",
]

JS_ONLY_SITES = {
    "www.apartments.com",
    "edfeontheblvd.com",
    "www.electriclofts.com",
    "www.fountainsatemeraldpark.com",
    "elevatetomillspringspark.com",
    "parktowerapartments.eprodesse.com",
}

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
}

PHONE_RE = re.compile(r"(\+?1[\s.\-]?)?(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PRICE_RE = re.compile(r"\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:/mo(?:nth)?)?")
BED_RE   = re.compile(r"(\d+)\s*(?:bed(?:room)?s?|br)\b", re.IGNORECASE)
BATH_RE  = re.compile(r"(\d+(?:\.\d+)?)\s*(?:bath(?:room)?s?|ba)\b", re.IGNORECASE)
SQFT_RE  = re.compile(r"([\d,]+)\s*(?:sq\.?\s*ft\.?|square\s*feet)", re.IGNORECASE)
AVAIL_RE = re.compile(
    r"(available\s*now|immediate|call\s*for\s*availability|"
    r"waiting\s*list|coming\s*soon|leasing\s*now|move.in\s*ready)",
    re.IGNORECASE,
)

# ── Alameda County geo-filter (v6.2) ─────────────────────────────────────────
# All 14 incorporated cities + unincorporated communities in Alameda County.
ALAMEDA_CITIES = {
    "alameda", "albany", "berkeley", "dublin", "emeryville", "fremont",
    "hayward", "livermore", "newark", "oakland", "piedmont", "pleasanton",
    "san leandro", "union city",
    # unincorporated
    "san lorenzo", "castro valley", "ashland", "cherryland", "fairview",
    "sunol",
}

# ZIP ranges covering Alameda County (inclusive).
_ALAMEDA_ZIP_RANGES = [
    (94501, 94502),   # Alameda
    (94536, 94552),   # Fremont, Hayward, Castro Valley, Livermore(94550/51)
    (94555, 94555),   # Fremont (Ardenwood)
    (94560, 94560),   # Newark
    (94566, 94566),   # Pleasanton
    (94568, 94568),   # Dublin
    (94577, 94580),   # San Leandro, San Lorenzo
    (94586, 94588),   # Sunol, Union City, Pleasanton/Dublin
    (94601, 94627),   # Oakland, Piedmont
    (94661, 94662),   # Oakland (Montclair), Emeryville
    (94701, 94720),   # Berkeley, Albany
]

# "City, ST 12345" — used to pull location out of free-text addresses/cards.
CITY_ST_ZIP_RE = re.compile(r"([A-Za-z .'\-]+),\s*([A-Z]{2})\.?\s+(\d{5})")

def _zip_in_alameda(zip_code: str) -> bool:
    try:
        z = int(zip_code[:5])
    except (ValueError, TypeError):
        return False
    return any(lo <= z <= hi for lo, hi in _ALAMEDA_ZIP_RANGES)

def _city_in_alameda(city: str) -> bool:
    c = city.strip().lower()
    return any(a == c or a in c for a in ALAMEDA_CITIES)

def _in_alameda(u: dict) -> bool:
    """True if a unit/record is (or may be) located in Alameda County, CA.

    Strictness depends on where the location info came from:
      • STRUCTURED city/state/zip (HUD records, per-card directory parses)
        describe the LISTING itself → enforce strictly.
      • FREE-TEXT page address on web units is often the management
        company's OFFICE (footer/contact block), not the rental → only use
        it to reject clearly out-of-state pages. A CA office outside the
        county must NOT wipe out a site's listings (the URL list is already
        hand-curated to Alameda County properties).
    """
    is_web = u.get("source") != "hud"

    state = (u.get("state") or "").strip().upper()
    if state and state not in ("CA", "CALIFORNIA"):
        return False

    zm = re.search(r"\d{5}", u.get("zip_code") or "")
    if zm:
        return _zip_in_alameda(zm.group(0))

    city = (u.get("city") or "").strip()
    if city:
        return _city_in_alameda(city)

    # No structured location — inspect the free-text address (advisory only
    # for web units; the page address is frequently the office, not the unit).
    addr = u.get("address") or ""
    m = CITY_ST_ZIP_RE.search(addr)
    if m:
        c, st, zc = m.group(1).strip(), m.group(2).upper(), m.group(3)
        if st != "CA":
            return False
        if _zip_in_alameda(zc) or _city_in_alameda(c):
            return True
        # CA address that isn't clearly Alameda: keep curated web sources,
        # drop HUD records (those must prove their location).
        return is_web
    m2 = re.search(r",\s*([A-Z]{2})\s+\d{5}", addr)
    if m2 and m2.group(1).upper() != "CA":
        return False

    # No usable location info at all:
    #   • web units come from the hand-curated Alameda County URL list → keep
    #   • HUD records come from a national dataset → drop unless proven local
    return is_web

# ── Data model ────────────────────────────────────────────────────────────────
@dataclass
class Unit:
    source: str = "web"
    hud_layer: str = ""
    hud_program: str = ""
    property_name: str = ""
    unit_label: str = ""
    url: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    phone: str = ""
    email: str = ""
    price: str = ""
    bedrooms: str = ""
    bathrooms: str = ""
    sqft: str = ""
    availability: str = ""
    description: str = ""
    status: str = "ok"

# ── Fetch ─────────────────────────────────────────────────────────────────────
async def _fetch(session: "aiohttp.ClientSession", url: str) -> tuple[str, Optional[str]]:
    for attempt in range(MAX_RETRIES + 1):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    return url, await r.text(errors="replace")
                if r.status in (429, 503):
                    wait = 2 ** (attempt + 2)
                    print(f"  [fetch] {url} → HTTP {r.status}, retrying in {wait}s…")
                    await asyncio.sleep(wait)
                    continue
                print(f"  [fetch] {url} → HTTP {r.status} (no retry)")
                return url, None
        except asyncio.TimeoutError:
            print(f"  [fetch] {url} → timeout (attempt {attempt + 1})")
        except Exception as e:
            print(f"  [fetch] {url} → {type(e).__name__}: {e} (attempt {attempt + 1})")
        if attempt < MAX_RETRIES:
            await asyncio.sleep(1.5 * (attempt + 1))
    return url, None

# ── Headless browser fetch (v6.3) ────────────────────────────────────────────
# JS-only sites ship an empty HTML shell and build the listings client-side.
# Headless Chromium loads the page, executes the JavaScript, waits for the
# network to go quiet, and hands back the RENDERED HTML — which then flows
# through the exact same extractors as every other site.

HEADLESS_ENABLED  = os.environ.get("HEADLESS", "1") != "0"
RENDER_NAV_MS     = 30_000   # max time for initial navigation
RENDER_IDLE_MS    = 10_000   # max wait for network-idle after load
RENDER_SETTLE_MS  = 2_000    # grace period for late-running scripts

def _headless_available() -> bool:
    return HEADLESS_ENABLED and _PLAYWRIGHT_OK

async def _block_heavy(route):
    # Skip images/fonts/media — big, slow, and useless for text extraction.
    if route.request.resource_type in ("image", "font", "media"):
        await route.abort()
    else:
        await route.continue_()

async def _render_page(page, url: str) -> Optional[str]:
    """Render one URL in an existing Playwright page; return HTML or None."""
    try:
        await page.goto(url, timeout=RENDER_NAV_MS, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=RENDER_IDLE_MS)
        except Exception:
            pass  # busy sites never go idle — settle time below
        await page.wait_for_timeout(RENDER_SETTLE_MS)
        return await page.content()
    except Exception as e:
        print(f"  [render] {urllib.parse.urlparse(url).netloc} → "
              f"{type(e).__name__}: {e}")
        return None

# ── Page helpers ──────────────────────────────────────────────────────────────
def _page_phone(text: str) -> str:
    m = PHONE_RE.findall(text)
    if m:
        return re.sub(r"[^\d+\-() ]", "", "".join(m[0])).strip()
    return ""

def _page_email(text: str) -> str:
    emails = EMAIL_RE.findall(text)
    return next(
        (e for e in emails
         if not re.search(r"(example|noreply|no-reply|sentry|cdn|wp)", e, re.I)),
        "",
    )

def _page_title(soup) -> str:
    t = soup.find("title")
    return t.get_text(strip=True)[:100] if t else ""

def _page_address(soup) -> str:
    a = (
        soup.find(attrs={"itemprop": "streetAddress"})
        or soup.find(class_=re.compile(r"\baddress\b", re.I))
        or soup.find(id=re.compile(r"\baddress\b", re.I))
    )
    return a.get_text(" ", strip=True)[:200] if a else ""

def _base_unit(url: str, soup, text: str) -> Unit:
    u = Unit(source="web", url=url)
    u.property_name = _page_title(soup)
    u.address       = _page_address(soup)
    u.phone         = _page_phone(text)
    u.email         = _page_email(text)
    # NOTE: we deliberately do NOT promote the page address into structured
    # city/state/zip — on management-company sites that address is usually
    # the OFFICE, and treating it as the listing's location caused entire
    # sites to be filtered out. Structured fields are only set from
    # per-listing card text (see _extract_directory_cards).
    return u

# ── JS-only detection ─────────────────────────────────────────────────────────
def _is_js_only(url: str, html: str) -> bool:
    domain = urllib.parse.urlparse(url).netloc
    if domain in JS_ONLY_SITES:
        return True
    soup         = BeautifulSoup(html, "html.parser")
    visible_text = soup.get_text(" ", strip=True)
    script_tags  = len(soup.find_all("script"))
    if len(visible_text) < 300 and script_tags > 3:
        return True
    return False

def _js_only_card(url: str, html: str) -> list[Unit]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ")
    base = _base_unit(url, soup, text)
    base.unit_label   = "View listings on site →"
    base.description  = (
        "This site loads listings via JavaScript. "
        "Click the link to view available units directly."
    )
    base.availability = "See website"
    base.status       = "js_rendered"
    return [base]

# ── Unit extractors ───────────────────────────────────────────────────────────
def _extract_floor_plan_rows(url: str, soup, text: str) -> list[Unit]:
    base  = _base_unit(url, soup, text)
    units: list[Unit] = []

    # v6.2: collect from ALL matching tables (was: return after first one).
    for table in soup.find_all("table"):
        rows   = table.find_all("tr")
        header = " ".join(
            th.get_text(" ", strip=True).lower()
            for th in (rows[0].find_all(["th", "td"]) if rows else [])
        )
        if not any(k in header for k in ("bed","unit","rent","price","avail","plan")):
            continue
        for row in rows[1:]:
            cells     = [td.get_text(" ", strip=True) for td in row.find_all(["td","th"])]
            cell_text = " ".join(cells)
            beds  = BED_RE.search(cell_text)
            price = PRICE_RE.search(cell_text)
            baths = BATH_RE.search(cell_text)
            sqft  = SQFT_RE.search(cell_text)
            avail = AVAIL_RE.search(cell_text)
            if not (beds or price):
                continue
            u = Unit(**{k: v for k, v in asdict(base).items()})
            u.bedrooms     = beds.group(1) if beds else ""
            u.bathrooms    = baths.group(1) if baths else ""
            u.price        = price.group(0) if price else ""
            u.sqft         = sqft.group(1).replace(",","") if sqft else ""
            u.availability = avail.group(0).title() if avail else ""
            u.unit_label   = _make_label(u)
            u.description  = cell_text[:200]
            units.append(u)
    if units:
        return _dedup(units)

    # v6.2: scan all card selectors (was: return after the first selector
    # producing ≥2 hits), and raised the per-selector cap 40 → 100.
    card_selectors = [
        {"class": re.compile(
            r"(floor.?plan|floorplan|unit.?card|plan.?card|"
            r"availability|listing.?item|rental.?item|apt.?card|apartment.?item)",
            re.I,
        )},
        {"class": re.compile(r"(plan|unit|listing|rental|room)", re.I)},
    ]
    for sel in card_selectors:
        cards = soup.find_all(["div","article","li","section"], attrs=sel)
        if len(cards) < 2:
            continue
        for card in cards[:100]:
            ct    = card.get_text(" ", strip=True)
            beds  = BED_RE.search(ct)
            price = PRICE_RE.search(ct)
            if not (beds or price):
                continue
            baths = BATH_RE.search(ct)
            sqft  = SQFT_RE.search(ct)
            avail = AVAIL_RE.search(ct)
            link  = card.find("a", href=True)
            u = Unit(**{k: v for k, v in asdict(base).items()})
            u.bedrooms     = beds.group(1) if beds else ""
            u.bathrooms    = baths.group(1) if baths else ""
            u.price        = price.group(0) if price else ""
            u.sqft         = sqft.group(1).replace(",","") if sqft else ""
            u.availability = avail.group(0).title() if avail else ""
            u.unit_label   = _make_label(u)
            u.description  = ct[:200]
            if link:
                href  = link["href"]
                u.url = href if href.startswith("http") else urllib.parse.urljoin(url, href)
            units.append(u)
    if len(units) >= 2:
        return _dedup(units)

    for tag in soup.find_all(["p","li","dd","dt","span","div"]):
        ct = tag.get_text(" ", strip=True)
        if len(ct) > 400 or len(ct) < 8:
            continue
        beds  = BED_RE.search(ct)
        price = PRICE_RE.search(ct)
        if not (beds and price):
            continue
        baths = BATH_RE.search(ct)
        sqft  = SQFT_RE.search(ct)
        avail = AVAIL_RE.search(ct)
        u = Unit(**{k: v for k, v in asdict(base).items()})
        u.bedrooms     = beds.group(1)
        u.bathrooms    = baths.group(1) if baths else ""
        u.price        = price.group(0)
        u.sqft         = sqft.group(1).replace(",","") if sqft else ""
        u.availability = avail.group(0).title() if avail else ""
        u.unit_label   = _make_label(u)
        u.description  = ct[:200]
        units.append(u)

    return _dedup(units) if units else []

# ── Directory extractor (v6.2) ────────────────────────────────────────────────
# Property-directory pages (midpen-housing, eahhousing, ebaldc, wilsonpm,
# sevillepropertymanagement, crpmrealty, esring, andersenjung, oaktree…)
# list many properties WITHOUT bed/price info in the HTML. The old parser
# required beds-or-price, so these pages collapsed into a single fallback
# card. This extractor emits one result per property card.
_DIR_CARD_CLASS = re.compile(
    r"(propert|communit|listing|result|teaser|development|vacanc)", re.I
)

def _card_name(card) -> str:
    """Property name from a card: its heading, else its link text."""
    heading = card.find(["h1", "h2", "h3", "h4", "h5", "strong"])
    if heading:
        name = heading.get_text(" ", strip=True)
        if 3 <= len(name) <= 90:
            return name
    link = card.find("a", href=True)
    if link:
        name = link.get_text(" ", strip=True)
        if 3 <= len(name) <= 90:
            return name
    return ""

def _extract_directory_cards(url: str, soup, text: str) -> list[Unit]:
    base = _base_unit(url, soup, text)

    # A "qualifying" card has a link and a plausible property name.
    # v6.3.1 fix: the old "skip any element containing another matching
    # element" rule misfired when a card's INNER pieces (property-title,
    # listing-address, …) also matched the class pattern — the real card got
    # skipped and its pieces didn't qualify, so whole directories vanished.
    # Now: collect qualifying elements, then drop only those that contain
    # ANOTHER qualifying card (true outer wrappers).
    candidates = soup.find_all(["div", "article", "li", "section"],
                               class_=_DIR_CARD_CLASS)
    quals = [c for c in candidates
             if c.find("a", href=True) and _card_name(c)]
    qual_set = set(id(c) for c in quals)
    cards = [c for c in quals
             if not any(id(d) in qual_set
                        for d in c.find_all(["div", "article", "li", "section"],
                                            class_=_DIR_CARD_CLASS))]

    seen: set = set()
    out: list[Unit] = []
    for card in cards:
        link = card.find("a", href=True)
        name = _card_name(card)
        href = link["href"]
        full = href if href.startswith("http") else urllib.parse.urljoin(url, href)
        key  = (name.lower(), full)
        if key in seen:
            continue
        seen.add(key)

        ct = card.get_text(" ", strip=True)
        u  = Unit(**{k: v for k, v in asdict(base).items()})
        u.property_name = name
        u.url           = full
        u.unit_label    = "Property"
        u.description   = ct[:200]

        addr_el = card.find(class_=re.compile(r"address|location", re.I))
        if addr_el:
            u.address = addr_el.get_text(" ", strip=True)[:200]
        m = CITY_ST_ZIP_RE.search(u.address) or CITY_ST_ZIP_RE.search(ct)
        if m:
            u.city, u.state, u.zip_code = m.group(1).strip(), m.group(2), m.group(3)

        beds  = BED_RE.search(ct)
        price = PRICE_RE.search(ct)
        avail = AVAIL_RE.search(ct)
        if beds:  u.bedrooms     = beds.group(1)
        if price: u.price        = price.group(0)
        if avail: u.availability = avail.group(0).title()

        out.append(u)
        if len(out) >= 120:
            break
    # Fewer than 3 cards is probably page furniture, not a directory.
    return out if len(out) >= 3 else []

def _make_label(u: Unit) -> str:
    parts = []
    if u.bedrooms:  parts.append(f"{u.bedrooms} Bed")
    if u.bathrooms: parts.append(f"{u.bathrooms} Bath")
    if u.sqft:      parts.append(f"{u.sqft} sq ft")
    return " / ".join(parts) if parts else "Unit"

def _dedup(units: list[Unit]) -> list[Unit]:
    # v6.2: widened key — the old (beds, price, sqft) key collapsed distinct
    # units sharing specs, and collapsed ALL units whose specs were empty.
    seen = set()
    out  = []
    for u in units:
        key = (u.bedrooms, u.bathrooms, u.price, u.sqft,
               u.unit_label, u.url, (u.description or "")[:80])
        if key not in seen:
            seen.add(key)
            out.append(u)
    return out

def _fallback_unit(url: str, soup, text: str) -> list[Unit]:
    base      = _base_unit(url, soup, text)
    beds_all  = list(dict.fromkeys(BED_RE.findall(text)))
    price_all = PRICE_RE.findall(text)
    avail     = AVAIL_RE.search(text)
    base.bedrooms     = beds_all[0] if beds_all else ""
    base.price        = price_all[0] if price_all else ""
    base.availability = avail.group(0).title() if avail else ""
    base.unit_label   = (
        "Studio – " + beds_all[-1] + " Bed"
        if len(beds_all) > 1 else _make_label(base)
    )
    meta = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    base.description  = (meta.get("content","") if meta else "")[:300]
    if not base.description:
        p = soup.find("p")
        if p:
            base.description = p.get_text(" ", strip=True)[:300]
    return [base]

def parse_page(url: str, html: str, rendered: bool = False) -> list[Unit]:
    # rendered=True → html came from headless Chromium; JS already executed,
    # so skip the JS-only shortcut and extract normally.
    if not rendered and _is_js_only(url, html):
        print(f"  [web] {urllib.parse.urlparse(url).netloc}: JS-rendered, returning link card")
        return _js_only_card(url, html)
    soup  = BeautifulSoup(html, "html.parser")
    text  = soup.get_text(" ")
    units = _extract_floor_plan_rows(url, soup, text)
    # v6.2: directory pages — if the directory extractor finds more distinct
    # properties than the floor-plan extractor found units, prefer it.
    dir_units = _extract_directory_cards(url, soup, text)
    if len(dir_units) > len(units):
        units = dir_units
    if not units:
        units = _fallback_unit(url, soup, text)
    prop_name = _page_title(soup)
    for u in units:
        if not u.property_name:
            u.property_name = prop_name
    return units

# ── Web crawler ───────────────────────────────────────────────────────────────
def _link_card(url: str) -> Unit:
    """Minimal 'visit the site' card, used when a JS site can't be rendered."""
    return Unit(
        source="web",
        url=url,
        property_name=urllib.parse.urlparse(url).netloc.replace("www.", ""),
        unit_label="View listings on site →",
        description=("This site loads listings via JavaScript. "
                     "Click the link to view available units directly."),
        availability="See website",
        status="js_rendered",
    )

# ── Deep crawl (v6.4) ────────────────────────────────────────────────────────
# The old crawler fetched exactly ONE page per site, so listings on page 2+
# and units behind property-detail links were invisible. The deep crawler,
# per site: extracts from the entry page, then follows (a) pagination links
# ("next", "»", numbered pages, ?page=N) and (b) the detail links attached
# to directory cards — up to MAX_PAGES_PER_SITE pages, same domain only.

_ARROW_CHARS = "»›→>«‹←<"

def _is_pag_text(txt: str) -> bool:
    """True for link text like 'Next', 'Next »', '»', '2', 'Load more'."""
    t = (txt or "").strip().lower()
    if not t or len(t) > 20:
        return False
    core = t.strip(" " + _ARROW_CHARS)
    if core in ("next", "next page", "more", "load more", "older",
                "see more", "view more", "show more"):
        return True
    if core.isdigit() and len(core) <= 3:
        return True
    if not core and any(c in t for c in "»›→>"):   # bare forward arrow
        return True
    return False

def _find_pagination(url: str, soup) -> list[str]:
    base = urllib.parse.urlparse(url)
    out: list[str] = []
    seen: set = set()
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(url, a["href"].split("#")[0])
        p = urllib.parse.urlparse(href)
        if p.scheme not in ("http", "https") or p.netloc != base.netloc:
            continue
        if href.rstrip("/") == url.rstrip("/"):
            continue
        rel = " ".join(a.get("rel") or []).lower()
        txt = a.get_text(" ", strip=True)
        if ("next" in rel
                or _is_pag_text(txt)
                or re.search(r"([?&](page|pg|paged?)=\d+|/page/\d+)", href, re.I)):
            if href not in seen:
                seen.add(href)
                out.append(href)
    return out[:8]

def _dedup_units(units: list[Unit]) -> list[Unit]:
    """Cross-page dedup: same property+unit+price seen on multiple pages."""
    seen: set = set()
    out: list[Unit] = []
    for u in units:
        key = (u.property_name, u.unit_label, u.price, u.bedrooms, u.sqft, u.url)
        if key not in seen:
            seen.add(key)
            out.append(u)
    return out

def _extract_units(url: str, soup, text: str) -> list[Unit]:
    """Floor-plan/table/card units, or directory cards if those find more."""
    units = _extract_floor_plan_rows(url, soup, text)
    dirs  = _extract_directory_cards(url, soup, text)
    return dirs if len(dirs) > len(units) else units

async def _crawl_site(session, start_url: str) -> list[Unit]:
    netloc  = urllib.parse.urlparse(start_url).netloc
    visited: set[str] = set()
    queue: list[tuple[str, str]] = [(start_url, "listing")]
    dir_cards: dict[str, Unit] = {}   # detail-url -> its directory card
    results: list[Unit] = []
    start_fallback: list[Unit] = []   # used only if the whole site yields 0

    while queue and len(visited) < MAX_PAGES_PER_SITE:
        url, kind = queue.pop(0)
        norm = url.rstrip("/")
        if norm in visited:
            continue
        visited.add(norm)

        _, html = await _fetch(session, url)
        await asyncio.sleep(REQUEST_STAGGER_S)

        if not html:
            if url == start_url:
                results.append(Unit(source="web", url=url, property_name=netloc,
                                    unit_label="Property", status="error"))
            elif kind == "detail" and url in dir_cards:
                results.append(dir_cards[url])   # keep the card we came from
            continue

        if _is_js_only(url, html):
            if url == start_url:
                results.extend(_js_only_card(url, html))
            elif kind == "detail" and url in dir_cards:
                results.append(dir_cards[url])
            continue

        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ")
        title = _page_title(soup)

        if kind == "detail":
            units = _extract_floor_plan_rows(url, soup, text)
            if units:
                for u in units:
                    u.property_name = title or u.property_name
                    if not u.url:
                        u.url = url
                results.extend(units)
            elif url in dir_cards:
                results.append(dir_cards[url])   # detail page had no specifics
            continue

        # listing page
        units = _extract_floor_plan_rows(url, soup, text)
        dirs  = _extract_directory_cards(url, soup, text)
        if len(dirs) > len(units):
            for d in dirs:
                d_net = urllib.parse.urlparse(d.url).netloc
                if d.url and d_net == netloc and d.url.rstrip("/") not in visited:
                    dir_cards[d.url] = d
                    queue.append((d.url, "detail"))
                else:
                    results.append(d)            # off-site or already seen
        elif units:
            for u in units:
                if not u.property_name:
                    u.property_name = title
            results.extend(units)
        elif url == start_url:
            start_fallback = _fallback_unit(url, soup, text)

        for p_url in _find_pagination(url, soup):
            queue.append((p_url, "listing"))

    if not results and start_fallback:
        results = start_fallback
    results = _dedup_units(results)
    print(f"  [web] {netloc}: {len(results)} unit(s) from {len(visited)} page(s)")
    return results

async def _crawl_js_sites(urls: list[str]) -> list[Unit]:
    """Deep-crawl JS-only sites in headless Chromium (pagination only)."""
    if not urls:
        return []
    if not _headless_available():
        return [_link_card(u) for u in urls]
    out: list[Unit] = []
    done: set[str] = set()
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            ctx = await browser.new_context(
                user_agent=BROWSER_HEADERS["User-Agent"],
                viewport={"width": 1366, "height": 900},
                locale="en-US",
            )
            page = await ctx.new_page()
            await page.route("**/*", _block_heavy)
            for start in urls:
                netloc = urllib.parse.urlparse(start).netloc
                site_units: list[Unit] = []
                visited: set[str] = set()
                q = [start]
                while q and len(visited) < MAX_JS_PAGES_PER_SITE:
                    url = q.pop(0)
                    norm = url.rstrip("/")
                    if norm in visited:
                        continue
                    visited.add(norm)
                    html = await _render_page(page, url)
                    if not html:
                        continue
                    soup = BeautifulSoup(html, "html.parser")
                    text = soup.get_text(" ")
                    units = _extract_units(url, soup, text)
                    title = _page_title(soup)
                    for u in units:
                        if not u.property_name:
                            u.property_name = title
                    site_units.extend(units)
                    q.extend(_find_pagination(url, soup))
                if site_units:
                    site_units = _dedup_units(site_units)
                    out.extend(site_units)
                    print(f"  [web] {netloc}: {len(site_units)} unit(s) "
                          f"from {len(visited)} rendered page(s)")
                else:
                    out.append(_link_card(start))
                    print(f"  [web] {netloc}: nothing extracted → link card")
                done.add(start)
            await browser.close()
    except Exception as e:
        print(f"  [render] Chromium failed to start: {e} "
              "(did you run `playwright install chromium`?)")
    out.extend(_link_card(u) for u in urls if u not in done)
    return out

async def crawl_web() -> list[Unit]:
    if _headless_available():
        js_urls    = [u for u in WEB_URLS
                      if urllib.parse.urlparse(u).netloc in JS_ONLY_SITES]
        plain_urls = [u for u in WEB_URLS if u not in js_urls]
    else:
        js_urls, plain_urls = [], list(WEB_URLS)

    results: list[Unit] = []
    connector = aiohttp.TCPConnector(ssl=False, limit=10)
    async with aiohttp.ClientSession(headers=BROWSER_HEADERS,
                                     connector=connector) as session:
        sem = asyncio.Semaphore(CONCURRENT_SITES)
        async def bounded(u):
            async with sem:
                return await _crawl_site(session, u)
        for site_units in await asyncio.gather(*(bounded(u) for u in plain_urls)):
            results.extend(site_units)

    results.extend(await _crawl_js_sites(js_urls))
    return results

# ── HUD loader ────────────────────────────────────────────────────────────────
def load_hud_data() -> list[dict]:
    json_path = os.path.join(os.path.dirname(__file__), "hud_data.json")
    if not os.path.isfile(json_path):
        print("  [HUD] hud_data.json not found — using static fallback")
        return _static_fallback()
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        out = []
        for r in data:
            raw_beds     = r.get("bedrooms", [])
            bedrooms_str = ", ".join(raw_beds) if isinstance(raw_beds, list) else str(raw_beds or "")
            out.append({
                "source":        "hud",
                "hud_layer":     r.get("hud_layer", ""),
                "hud_program":   r.get("hud_program", ""),
                "property_name": r.get("title", ""),
                "unit_label":    (
                    r.get("units","") + " units"
                    if r.get("units") else "HUD Property"
                ),
                "url":           r.get("url", ""),
                "address":       r.get("address", ""),
                "city":          r.get("city", ""),
                "state":         r.get("state", ""),
                "zip_code":      r.get("zip_code", ""),
                "phone":         r.get("phone", ""),
                "email":         r.get("email", ""),
                "price":         r.get("price_range") or "Income-based",
                "bedrooms":      bedrooms_str,
                "bathrooms":     "",
                "sqft":          "",
                "availability":  "",
                "description":   r.get("description", ""),
                "status":        "ok",
            })
        print(f"  [HUD] Loaded {len(out)} records from hud_data.json")
        return out
    except Exception as e:
        print(f"  [HUD] Error loading hud_data.json: {e}")
        return _static_fallback()

def _static_fallback() -> list[dict]:
    return [
        {
            "source":"hud","hud_layer":"HUD Offices","hud_program":"HUD Field Office",
            "property_name":"HUD San Francisco Regional Office",
            "unit_label":"Field Office",
            "url":"https://www.hud.gov/contactus/local",
            "address":"One Embarcadero Center, Suite 1600",
            "city":"San Francisco","state":"CA","zip_code":"94111",
            "phone":"415-489-6400","email":"","price":"Income-based","bedrooms":"",
            "bathrooms":"","sqft":"","availability":"",
            "description":"HUD Field Office serving Alameda County and the Bay Area",
            "status":"ok",
        },
        {
            "source":"hud","hud_layer":"Public Housing Authorities",
            "hud_program":"Public Housing Authority",
            "property_name":"Housing Authority of the County of Alameda (HACA)",
            "unit_label":"Public Housing Authority",
            "url":"https://www.haca.net","address":"22941 Atherton Street",
            "city":"Hayward","state":"CA","zip_code":"94541",
            "phone":"510-538-8876","email":"","price":"Income-based","bedrooms":"",
            "bathrooms":"","sqft":"","availability":"",
            "description":"Public Housing Authority serving Alameda County",
            "status":"ok",
        },
        {
            "source":"hud","hud_layer":"Public Housing Authorities",
            "hud_program":"Public Housing Authority",
            "property_name":"Oakland Housing Authority (OHA)",
            "unit_label":"Public Housing Authority",
            "url":"https://www.oakha.org","address":"1805 Harrison Street",
            "city":"Oakland","state":"CA","zip_code":"94612",
            "phone":"510-874-1500","email":"","price":"Income-based","bedrooms":"",
            "bathrooms":"","sqft":"","availability":"",
            "description":"Public Housing Authority serving Oakland and Alameda County",
            "status":"ok",
        },
        {
            "source":"hud","hud_layer":"Homeless Services/CoC Grantee Areas",
            "hud_program":"Continuum of Care",
            "property_name":"EveryOne Home — Alameda County CoC (CA-502)",
            "unit_label":"CoC Grantee",
            "url":"https://www.everyonehome.org","address":"224 W. Winton Avenue",
            "city":"Hayward","state":"CA","zip_code":"94544",
            "phone":"510-670-5944","email":"","price":"Income-based","bedrooms":"",
            "bathrooms":"","sqft":"","availability":"",
            "description":"Continuum of Care grantee · Alameda County, CA · CoC #CA-502",
            "status":"ok",
        },
    ]

# ── TTL cache ─────────────────────────────────────────────────────────────────
_cache: list[dict] = []
_cache_ts: float   = 0.0

def _cache_is_stale() -> bool:
    return (not _cache) or (time.time() - _cache_ts > CACHE_TTL)

# v6.4.1: the deep crawl takes 1–2 minutes. Running it inside the HTTP
# request handler froze the (single-threaded) server, so the frontend hit
# its timeout: "Could not reach the server." Now the crawl runs in a
# background thread; requests are answered immediately — with cached data
# if we have any, or HTTP 202 "crawling" if the first crawl is still going.
_refresh_lock = threading.Lock()
_refreshing   = False

def _start_background_refresh() -> bool:
    """Kick off a crawl in a daemon thread. Returns False if already running."""
    global _refreshing
    with _refresh_lock:
        if _refreshing:
            return False
        _refreshing = True

    def _run():
        global _refreshing
        try:
            asyncio.run(_refresh_cache())
        except Exception as e:
            print(f"  [crawl] background refresh failed: {e}")
        finally:
            with _refresh_lock:
                _refreshing = False

    threading.Thread(target=_run, daemon=True).start()
    return True

async def _refresh_cache() -> None:
    global _cache, _cache_ts
    print("\nStarting HUDdl crawl…")
    web_units = await crawl_web()
    hud_units = load_hud_data()
    print(f"  Web: {len(web_units)} units | HUD: {len(hud_units)} records")

    # v6.2: hard Alameda County filter on everything entering the cache.
    combined = [asdict(u) for u in web_units] + hud_units
    kept     = [u for u in combined if _in_alameda(u)]
    dropped  = len(combined) - len(kept)
    if dropped:
        print(f"  [filter] Dropped {dropped} result(s) outside Alameda County, CA")

    _cache    = kept
    _cache_ts = time.time()

async def crawl_all() -> list[dict]:
    await _refresh_cache()
    return _cache

# ── Search / export ───────────────────────────────────────────────────────────
def _matches(u: dict, q: str) -> bool:
    if not q:
        return True
    hay = " ".join([
        u.get("property_name",""), u.get("unit_label",""),
        u.get("address",""),       u.get("city",""),
        u.get("zip_code",""),      u.get("description",""),
        u.get("price",""),         u.get("hud_layer",""),
        u.get("hud_program",""),   u.get("bedrooms",""),
        u.get("bathrooms",""),     u.get("sqft",""),
        u.get("availability",""),
    ]).lower()
    return any(term and term in hay for term in _expand(q))

def _source_ok(u: dict, source: str) -> bool:
    return source in ("all","") or u.get("source","") == source

def to_csv(units: list[dict]) -> str:
    if not units:
        return ""
    fields = [
        "source","hud_layer","hud_program","property_name","unit_label",
        "address","city","state","zip_code","phone","email",
        "price","bedrooms","bathrooms","sqft","availability",
        "description","url","status",
    ]
    buf = io.StringIO()
    w   = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for u in units:
        w.writerow(u)
    return buf.getvalue()

# ── Email ─────────────────────────────────────────────────────────────────────
def send_email(smtp_host, smtp_port, smtp_user, smtp_password,
               from_addr, to_addr, subject, body):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = from_addr
        msg["To"]      = to_addr
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as srv:
            srv.ehlo(); srv.starttls()
            srv.login(smtp_user, smtp_password)
            srv.sendmail(from_addr, to_addr, msg.as_string())
        return {"ok": True, "message": f"Email sent to {to_addr}"}
    except Exception as e:
        return {"ok": False, "message": str(e)}

# ── HTTP server ───────────────────────────────────────────────────────────────
class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, data: bytes, ct: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, status=200):
        self._send(json.dumps(obj, ensure_ascii=False).encode(), "application/json", status)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        p  = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(p.query)
        def param(k, d=""): return qs.get(k, [d])[0]

        # Never crawl inside a request — answer now, refresh in background.
        if _cache_is_stale():
            _start_background_refresh()

        # First crawl still running and nothing cached yet → tell the
        # frontend to check back (HTTP 202), don't leave it hanging.
        if not _cache and p.path in ("/api/listings", "/api/hud", "/api/export"):
            self._json({"status": "crawling",
                        "message": "First crawl in progress — retry shortly."},
                       202)
            return

        if p.path in ("/api/listings", "/api/hud"):
            q      = param("q").lower()
            source = param("source","all").lower()
            layer  = param("layer").lower()
            data   = [
                u for u in _cache
                if _source_ok(u, source)
                and _matches(u, q)
                and (not layer or layer in u.get("hud_layer","").lower())
            ]
            if p.path == "/api/hud":
                data = [u for u in data if u.get("source") == "hud"]
            self._json(data)

        elif p.path == "/api/export":
            q      = param("q").lower()
            source = param("source","all").lower()
            data   = [u for u in _cache if _source_ok(u, source) and _matches(u, q)]
            if param("format","json") == "csv":
                b = to_csv(data).encode()
                self.send_response(200)
                self.send_header("Content-Type","text/csv")
                self.send_header("Content-Disposition",'attachment; filename="huddl_export.csv"')
                self.send_header("Content-Length", str(len(b)))
                self._cors()
                self.end_headers()
                self.wfile.write(b)
            else:
                self._json(data)

        elif p.path == "/api/refresh":
            started = _start_background_refresh()
            self._json({"ok": True, "started": started, "count": len(_cache)})

        elif p.path == "/api/status":
            age_minutes = int((time.time() - _cache_ts) / 60) if _cache_ts else -1
            self._json({
                "count":         len(_cache),
                "cache_age_min": age_minutes,
                "cache_ttl_hrs": CACHE_TTL // 3600,
                "stale":         _cache_is_stale(),
                "refreshing":    _refreshing,
            })

        else:
            self._json({"error": "Not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or "{}")
        if self.path == "/api/email":
            result = send_email(
                smtp_host     = os.environ.get("SMTP_HOST","smtp.gmail.com"),
                smtp_port     = int(os.environ.get("SMTP_PORT", 587)),
                smtp_user     = os.environ.get("SMTP_USER",""),
                smtp_password = os.environ.get("SMTP_PASSWORD",""),
                from_addr     = os.environ.get("SMTP_USER",""),
                to_addr       = body.get("to",""),
                subject       = body.get("subject","Housing Inquiry"),
                body          = body.get("body",""),
            )
            self._json(result)
        else:
            self._json({"error": "Not found"}, 404)

def run_server(host="0.0.0.0", port=8787):
    server = ThreadingHTTPServer((host, port), APIHandler)
    _start_background_refresh()   # warm the cache at boot, don't make users wait
    print(f"\n🏠  HUDdl v6.4.1 API  →  http://{host}:{port}")
    print(f"   Headless browser: {'ON' if _headless_available() else 'OFF (link cards for JS sites)'}")
    print(f"   Cache TTL: {CACHE_TTL // 3600}h  |  Stagger: {REQUEST_STAGGER_S}s  |  Retries: {MAX_RETRIES}")
    print("   Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nHUDdl stopped.")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8787))
    run_server(port=port)
