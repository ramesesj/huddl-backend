#!/usr/bin/env python3
"""
HUDdl.py — v5 (unit-level results)
Each card = one rentable unit, not one website.
Extracts individual units with bedroom count, price, availability,
address, phone, and email from each page.
Falls back to a single property-level card when unit data isn't parseable.
"""

import asyncio, csv, io, json, os, re, smtplib, sys, urllib.parse

# ── Semantic search (inline — no separate file needed on Render) ──────────────
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
    import re as _re
    q = query.lower().strip()
    terms: set[str] = {q}
    if q in _ALIAS_MAP:
        terms.update(a.lower() for a in SYNONYMS[_ALIAS_MAP[q]])
    tokens = _re.split(r"[\s,/]+", q)
    for tok in tokens:
        tok = tok.strip()
        if not tok: continue
        terms.add(tok)
        if tok in _ALIAS_MAP:
            terms.update(a.lower() for a in SYNONYMS[_ALIAS_MAP[tok]])
    for i in range(len(tokens)-1):
        bigram = f"{tokens[i]} {tokens[i+1]}"
        if bigram in _ALIAS_MAP:
            terms.update(a.lower() for a in SYNONYMS[_ALIAS_MAP[bigram]])
    return list(terms)
from dataclasses import asdict, dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

try:
    import aiohttp
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "aiohttp", "beautifulsoup4", "--quiet"])
    import aiohttp
    from bs4 import BeautifulSoup

# ── Web URLs ──────────────────────────────────────────────────────────────────
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
    "https://www.apartments.com/alameda-county-ca/",
]

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
}

PHONE_RE  = re.compile(r"(\+?1[\s.\-]?)?(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})")
EMAIL_RE  = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PRICE_RE  = re.compile(r"\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:/mo(?:nth)?)?")
BED_RE    = re.compile(r"(\d+)\s*(?:bed(?:room)?s?|br)\b", re.IGNORECASE)
BATH_RE   = re.compile(r"(\d+(?:\.\d+)?)\s*(?:bath(?:room)?s?|ba)\b", re.IGNORECASE)
SQFT_RE   = re.compile(r"([\d,]+)\s*(?:sq\.?\s*ft\.?|square\s*feet)", re.IGNORECASE)
AVAIL_RE  = re.compile(
    r"(available\s*now|immediate|call\s*for\s*availability|"
    r"waiting\s*list|coming\s*soon|leasing\s*now|move.in\s*ready)",
    re.IGNORECASE
)


# ── Data model ────────────────────────────────────────────────────────────────
@dataclass
class Unit:
    source: str = "web"
    hud_layer: str = ""
    hud_program: str = ""
    property_name: str = ""   # e.g. "Alderwood Apartments"
    unit_label: str = ""      # e.g. "2 Bed / 1 Bath"
    url: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    phone: str = ""
    email: str = ""
    price: str = ""
    bedrooms: str = ""        # e.g. "2"
    bathrooms: str = ""       # e.g. "1"
    sqft: str = ""
    availability: str = ""    # e.g. "Available Now"
    description: str = ""
    status: str = "ok"


# ── Fetch ─────────────────────────────────────────────────────────────────────
async def _fetch(session, url: str) -> tuple[str, Optional[str]]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=18)) as r:
            if r.status == 200:
                return url, await r.text(errors="replace")
            return url, None
    except Exception:
        return url, None


# ── Page-level helpers ────────────────────────────────────────────────────────
def _page_phone(text: str) -> str:
    m = PHONE_RE.findall(text)
    if m:
        return re.sub(r"[^\d+\-() ]", "", "".join(m[0])).strip()
    return ""


def _page_email(text: str) -> str:
    emails = EMAIL_RE.findall(text)
    return next((e for e in emails
                 if not re.search(r"(example|noreply|no-reply|sentry|cdn|wp)", e, re.I)), "")


def _page_title(soup) -> str:
    t = soup.find("title")
    return t.get_text(strip=True)[:100] if t else ""


def _page_address(soup) -> str:
    a = (soup.find(attrs={"itemprop": "streetAddress"})
         or soup.find(class_=re.compile(r"\baddress\b", re.I))
         or soup.find(id=re.compile(r"\baddress\b", re.I)))
    return a.get_text(" ", strip=True)[:200] if a else ""


def _base_unit(url: str, soup, text: str) -> Unit:
    """Skeleton unit populated with page-level data."""
    u = Unit(source="web", url=url)
    u.property_name = _page_title(soup)
    u.address       = _page_address(soup)
    u.phone         = _page_phone(text)
    u.email         = _page_email(text)
    return u


# ── Unit-level extractors ─────────────────────────────────────────────────────

def _extract_floor_plan_rows(url: str, soup, text: str) -> list[Unit]:
    """
    Generic extractor that looks for repeating floor-plan / availability
    blocks common to property management sites using table rows, plan cards,
    or dl/dt structures.
    """
    base = _base_unit(url, soup, text)
    units: list[Unit] = []

    # ── Strategy 1: table rows with bed/price columns ──────────────────────
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        header = " ".join(th.get_text(" ", strip=True).lower()
                          for th in (rows[0].find_all(["th","td"]) if rows else []))
        if not any(k in header for k in ("bed","unit","rent","price","avail","plan")):
            continue
        for row in rows[1:]:
            cells = [td.get_text(" ", strip=True) for td in row.find_all(["td","th"])]
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
            return units

    # ── Strategy 2: div/article/li cards with class hints ─────────────────
    card_selectors = [
        {"class": re.compile(r"(floor.?plan|floorplan|unit.?card|plan.?card|"
                              r"availability|listing.?item|rental.?item|"
                              r"apt.?card|apartment.?item)", re.I)},
        {"class": re.compile(r"(plan|unit|listing|rental|room)", re.I)},
    ]
    for sel in card_selectors:
        cards = soup.find_all(["div","article","li","section"], attrs=sel)
        if len(cards) < 2:
            continue
        for card in cards[:40]:
            ct = card.get_text(" ", strip=True)
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
                href = link["href"]
                u.url = href if href.startswith("http") else urllib.parse.urljoin(url, href)
            units.append(u)
        if len(units) >= 2:
            return _dedup(units)

    # ── Strategy 3: parse all bed/price co-occurrences in paragraphs ──────
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


def _make_label(u: Unit) -> str:
    parts = []
    if u.bedrooms:
        parts.append(f"{u.bedrooms} Bed")
    if u.bathrooms:
        parts.append(f"{u.bathrooms} Bath")
    if u.sqft:
        parts.append(f"{u.sqft} sq ft")
    return " / ".join(parts) if parts else "Unit"


def _dedup(units: list[Unit]) -> list[Unit]:
    """Remove duplicate units by (bedrooms, price, sqft)."""
    seen = set()
    out = []
    for u in units:
        key = (u.bedrooms, u.price, u.sqft)
        if key not in seen:
            seen.add(key)
            out.append(u)
    return out


def _fallback_unit(url: str, soup, text: str) -> list[Unit]:
    """Single property-level card when no unit data found."""
    base = _base_unit(url, soup, text)
    beds_all  = list(dict.fromkeys(BED_RE.findall(text)))
    price_all = PRICE_RE.findall(text)
    avail     = AVAIL_RE.search(text)
    base.bedrooms    = beds_all[0] if beds_all else ""
    base.price       = price_all[0] if price_all else ""
    base.availability= avail.group(0).title() if avail else ""
    base.unit_label  = ("Studio – " + beds_all[-1] + " Bed" if len(beds_all) > 1
                        else _make_label(base))
    base.description = (soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
                        or {}).get("content", "")[:300]
    if not base.description:
        p = soup.find("p")
        if p:
            base.description = p.get_text(" ", strip=True)[:300]
    return [base]


def parse_page(url: str, html: str) -> list[Unit]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ")
    units = _extract_floor_plan_rows(url, soup, text)
    if not units:
        units = _fallback_unit(url, soup, text)
    # Stamp property name on all units
    prop_name = _page_title(soup)
    for u in units:
        if not u.property_name:
            u.property_name = prop_name
    return units


# ── Web crawler ───────────────────────────────────────────────────────────────
async def crawl_web() -> list[Unit]:
    connector = aiohttp.TCPConnector(ssl=False, limit=10)
    async with aiohttp.ClientSession(headers=BROWSER_HEADERS, connector=connector) as s:
        pages = await asyncio.gather(*[_fetch(s, u) for u in WEB_URLS])
    results: list[Unit] = []
    for url, html in pages:
        if html:
            units = parse_page(url, html)
            results.extend(units)
            print(f"  [web] {urllib.parse.urlparse(url).netloc}: {len(units)} unit(s)")
        else:
            results.append(Unit(source="web", url=url,
                                property_name=urllib.parse.urlparse(url).netloc,
                                unit_label="Property",
                                status="error"))
    return results


# ── HUD JSON loader ───────────────────────────────────────────────────────────
def load_hud_data() -> list[dict]:
    json_path = os.path.join(os.path.dirname(__file__), "hud_data.json")
    if not os.path.isfile(json_path):
        print("  [HUD] hud_data.json not found — using static fallback")
        return _static_fallback()
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        # Convert HUD records to unit-shaped dicts
        out = []
        for r in data:
            out.append({
                "source":        "hud",
                "hud_layer":     r.get("hud_layer",""),
                "hud_program":   r.get("hud_program",""),
                "property_name": r.get("title",""),
                "unit_label":    r.get("units","") + " units" if r.get("units") else "HUD Property",
                "url":           r.get("url",""),
                "address":       r.get("address",""),
                "city":          r.get("city",""),
                "state":         r.get("state","CA"),
                "zip_code":      r.get("zip_code",""),
                "phone":         r.get("phone",""),
                "email":         r.get("email",""),
                "price":         "",
                "bedrooms":      "",
                "bathrooms":     "",
                "sqft":          "",
                "availability":  "",
                "description":   r.get("description",""),
                "status":        "ok",
            })
        print(f"  [HUD] Loaded {len(out)} records from hud_data.json")
        return out
    except Exception as e:
        print(f"  [HUD] Error: {e}")
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
            "phone":"415-489-6400","email":"","price":"","bedrooms":"",
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
            "phone":"510-538-8876","email":"","price":"","bedrooms":"",
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
            "phone":"510-874-1500","email":"","price":"","bedrooms":"",
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
            "phone":"510-670-5944","email":"","price":"","bedrooms":"",
            "bathrooms":"","sqft":"","availability":"",
            "description":"Continuum of Care grantee · Alameda County, CA · CoC #CA-502",
            "status":"ok",
        },
    ]


# ── Combined crawl ────────────────────────────────────────────────────────────
async def crawl_all() -> list[dict]:
    print("\nStarting HUDdl crawl…")
    web_units = await crawl_web()
    hud_units = load_hud_data()
    print(f"  Web: {len(web_units)} units | HUD: {len(hud_units)} records")
    return [asdict(u) for u in web_units] + hud_units


# ── Contact helpers ───────────────────────────────────────────────────────────
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


# ── Search / export ───────────────────────────────────────────────────────────
def _matches(u: dict, q: str) -> bool:
    """Semantic search — expands query through real estate synonym dictionary."""
    if not q:
        return True
    hay = " ".join([
        u.get("property_name",""), u.get("unit_label",""),
        u.get("address",""), u.get("city",""), u.get("zip_code",""),
        u.get("description",""), u.get("price",""),
        u.get("hud_layer",""), u.get("hud_program",""),
        u.get("bedrooms",""), u.get("bathrooms",""),
        u.get("sqft",""), u.get("availability",""),
    ]).lower()
    for term in _expand(q):
        if term and term in hay:
            return True
    return False


def _source_ok(u: dict, source: str) -> bool:
    return source in ("all","") or u.get("source","") == source


def to_csv(units: list[dict]) -> str:
    if not units:
        return ""
    fields = ["source","hud_layer","hud_program","property_name","unit_label",
              "address","city","state","zip_code","phone","email",
              "price","bedrooms","bathrooms","sqft","availability",
              "description","url","status"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for u in units:
        w.writerow(u)
    return buf.getvalue()


# ── HTTP server ───────────────────────────────────────────────────────────────
_cache: list[dict] = []


def _cors(h):
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")


class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, data: bytes, ct: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        _cors(self); self.end_headers(); self.wfile.write(data)

    def _json(self, obj, status=200):
        self._send(json.dumps(obj, ensure_ascii=False).encode(),
                   "application/json", status)

    def do_OPTIONS(self):
        self.send_response(204); _cors(self); self.end_headers()

    def do_GET(self):
        global _cache
        p  = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(p.query)

        def param(k, d=""):
            return qs.get(k, [d])[0]

        if p.path in ("/api/listings", "/api/hud"):
            if not _cache:
                _cache = asyncio.run(crawl_all())
            q      = param("q").lower()
            source = param("source","all").lower()
            layer  = param("layer").lower()
            data   = [u for u in _cache
                      if _source_ok(u, source) and _matches(u, q)
                      and (not layer or layer in u.get("hud_layer","").lower())]
            if p.path == "/api/hud":
                data = [u for u in data if u.get("source") == "hud"]
            self._json(data)

        elif p.path == "/api/export":
            if not _cache:
                _cache = asyncio.run(crawl_all())
            q      = param("q").lower()
            source = param("source","all").lower()
            data   = [u for u in _cache if _source_ok(u, source) and _matches(u, q)]
            if param("format","json") == "csv":
                b = to_csv(data).encode()
                self.send_response(200)
                self.send_header("Content-Type","text/csv")
                self.send_header("Content-Disposition",
                                 'attachment; filename="huddl_export.csv"')
                self.send_header("Content-Length", str(len(b)))
                _cors(self); self.end_headers(); self.wfile.write(b)
            else:
                self._json(data)

        elif p.path == "/api/refresh":
            _cache.clear()
            _cache.extend(asyncio.run(crawl_all()))
            self._json({"ok": True, "count": len(_cache)})

        else:
            self._json({"error": "Not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or "{}")
        if self.path == "/api/email":
            result = send_email(
                smtp_host    = os.environ.get("SMTP_HOST",     "smtp.gmail.com"),
                smtp_port    = int(os.environ.get("SMTP_PORT", 587)),
                smtp_user    = os.environ.get("SMTP_USER",     ""),
                smtp_password= os.environ.get("SMTP_PASSWORD", ""),
                from_addr    = os.environ.get("SMTP_USER",     ""),
                to_addr      = body.get("to",""),
                subject      = body.get("subject","Housing Inquiry"),
                body         = body.get("body",""),
            )
            self._json(result)
        else:
            self._json({"error": "Not found"}, 404)


def run_server(host="0.0.0.0", port=8787):
    server = HTTPServer((host, port), APIHandler)
    print(f"\n🏠  HUDdl v5 API  →  http://{host}:{port}")
    print("  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nHUDdl stopped.")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8787))
    run_server(port=port)
