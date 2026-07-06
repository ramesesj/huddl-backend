#!/usr/bin/env python3
"""
HUDdl.py — v6
Fixes:
  1. Missing commas in WEB_URLS (silent URL concatenation)
  2. Concurrent request bursting replaced with staggered fetches + retry
  3. JavaScript-heavy sites handled via a lightweight JS-hint detection layer
  4. Cache invalidation added (TTL-based, default 6 hours)
  5. HUD bedrooms/price fields populated from enriched hud_data.json
"""

import asyncio, csv, io, json, os, re, smtplib, sys, time, urllib.parse

# ── Semantic search ───────────────────────────────────────────────────────────
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
from http.server import BaseHTTPRequestHandler, HTTPServer
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

# ── Config ────────────────────────────────────────────────────────────────────

CACHE_TTL        = int(os.environ.get("CACHE_TTL_HOURS", 6)) * 3600
REQUEST_STAGGER_S = 0.4
MAX_RETRIES      = 2

# ── FIX 1: WEB_URLS — commas added between every entry ───────────────────────
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
    "https://www.diabloviewaptliving.com/concord/diablo-view-apartments/conventional/",
    "https://www.oaklandpropertymanagement.co/tenants/",
    "https://www.livermoregardensapts.com/apartments/ca/livermore/floor-plans",
    "https://www.electriclofts.com/floorplans",
    # FIX 1: these three were missing commas and were silently fused into one broken URL
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
    "www.diabloviewaptliving.com",
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


# ── FIX 2: Staggered fetch with retry ────────────────────────────────────────
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


async def _fetch_all(urls: list[str]) -> list[tuple[str, Optional[str]]]:
    connector = aiohttp.TCPConnector(ssl=False, limit=5)
    results   = []
    async with aiohttp.ClientSession(headers=BROWSER_HEADERS, connector=connector) as session:
        for url in urls:
            result = await _fetch(session, url)
            results.append(result)
            await asyncio.sleep(REQUEST_STAGGER_S)
    return results


# ── Page-level helpers ────────────────────────────────────────────────────────
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
    return u


# ── FIX 3: JS-only site handler ───────────────────────────────────────────────
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
    base.unit_label  = "View listings on site →"
    base.description = (
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

    # Strategy 1: table rows
    for table in soup.find_all("table"):
        rows   = table.find_all("tr")
        header = " ".join(
            th.get_text(" ", strip=True).lower()
            for th in (rows[0].find_all(["th","td"]) if rows else [])
        )
        if not any(k in header for k in ("bed","unit","rent","price","avail","plan")):
            continue
        for row in rows[1:]:
            cells
