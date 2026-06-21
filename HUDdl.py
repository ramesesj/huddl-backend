#!/usr/bin/env python3
"""
HUDdl.py  — v3 (Render-optimized)
Lightweight version for Render free tier.
- Scrapes 25 Bay Area housing websites
- Queries small HUD endpoints only (no large Excel downloads)
- Full CORS open for browser access
"""

import asyncio, csv, io, json, os, re, smtplib, urllib.parse
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

# ── URLs to crawl ─────────────────────────────────────────────────────────────
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

# ── Known HUD / public housing data for Alameda County ───────────────────────
# Static data seeded from official HUD sources — avoids large file downloads
# that crash Render's free tier. Add more entries here as you find them.
HUD_STATIC: list[dict] = [
    # HUD Field Offices
    {
        "source": "hud", "hud_layer": "HUD Offices",
        "hud_program": "HUD Field Office",
        "title": "HUD San Francisco Regional Office",
        "address": "One Embarcadero Center, Suite 1600",
        "city": "San Francisco", "state": "CA", "zip_code": "94111",
        "phone": "415-489-6400", "email": "",
        "url": "https://www.hud.gov/contactus/local",
        "description": "HUD Field Office serving Alameda County and the Bay Area",
        "price_range": "", "bedrooms": [], "units": "", "status": "ok",
    },
    # Public Housing Authorities
    {
        "source": "hud", "hud_layer": "Public Housing Authorities",
        "hud_program": "Public Housing Authority",
        "title": "Housing Authority of the County of Alameda (HACA)",
        "address": "22941 Atherton Street",
        "city": "Hayward", "state": "CA", "zip_code": "94541",
        "phone": "510-538-8876", "email": "",
        "url": "https://www.haca.net",
        "description": "Public Housing Authority serving Alameda County",
        "price_range": "", "bedrooms": [], "units": "", "status": "ok",
    },
    {
        "source": "hud", "hud_layer": "Public Housing Authorities",
        "hud_program": "Public Housing Authority",
        "title": "Oakland Housing Authority (OHA)",
        "address": "1805 Harrison Street",
        "city": "Oakland", "state": "CA", "zip_code": "94612",
        "phone": "510-874-1500", "email": "",
        "url": "https://www.oakha.org",
        "description": "Public Housing Authority serving Oakland and Alameda County",
        "price_range": "", "bedrooms": [], "units": "~15,000", "status": "ok",
    },
    {
        "source": "hud", "hud_layer": "Public Housing Authorities",
        "hud_program": "Public Housing Authority",
        "title": "Housing Authority of the City of Alameda",
        "address": "701 Atlantic Avenue",
        "city": "Alameda", "state": "CA", "zip_code": "94501",
        "phone": "510-747-4300", "email": "",
        "url": "https://www.alamedahsg.org",
        "description": "Public Housing Authority serving the City of Alameda",
        "price_range": "", "bedrooms": [], "units": "", "status": "ok",
    },
    {
        "source": "hud", "hud_layer": "Public Housing Authorities",
        "hud_program": "Public Housing Authority",
        "title": "Berkeley Housing Authority",
        "address": "2180 Milvia Street",
        "city": "Berkeley", "state": "CA", "zip_code": "94704",
        "phone": "510-981-5400", "email": "",
        "url": "https://www.cityofberkeley.info/housing-authority",
        "description": "Public Housing Authority serving Berkeley",
        "price_range": "", "bedrooms": [], "units": "", "status": "ok",
    },
    # Homeless Services / CoC
    {
        "source": "hud", "hud_layer": "Homeless Services/CoC Grantee Areas",
        "hud_program": "Continuum of Care",
        "title": "EveryOne Home — Alameda County CoC (CA-502)",
        "address": "224 W. Winton Avenue",
        "city": "Hayward", "state": "CA", "zip_code": "94544",
        "phone": "510-670-5944", "email": "",
        "url": "https://www.everyonehome.org",
        "description": "Continuum of Care grantee · Alameda County, CA · CoC #CA-502",
        "price_range": "", "bedrooms": [], "units": "", "status": "ok",
    },
    # Low Income Housing Tax Credits — notable Alameda County projects
    {
        "source": "hud", "hud_layer": "Low Income Housing Tax Credits",
        "hud_program": "LIHTC",
        "title": "EBALDC — East Bay Asian Local Development Corporation",
        "address": "310 8th Street Suite 200",
        "city": "Oakland", "state": "CA", "zip_code": "94607",
        "phone": "510-287-5353", "email": "",
        "url": "https://ebaldc.org",
        "description": "LIHTC affordable housing developer · Alameda County, CA",
        "price_range": "", "bedrooms": [], "units": "", "status": "ok",
    },
    {
        "source": "hud", "hud_layer": "Low Income Housing Tax Credits",
        "hud_program": "LIHTC",
        "title": "Eden Housing — Alameda County Properties",
        "address": "22645 Grand Street",
        "city": "Hayward", "state": "CA", "zip_code": "94541",
        "phone": "510-582-1460", "email": "",
        "url": "https://www.edenhousing.org",
        "description": "LIHTC affordable housing developer · Alameda County, CA",
        "price_range": "", "bedrooms": [], "units": "3,000+", "status": "ok",
    },
    # USDA Rural Housing
    {
        "source": "hud", "hud_layer": "USDA Rural Housing",
        "hud_program": "USDA Rural Development",
        "title": "USDA Rural Development California Office",
        "address": "430 G Street, Suite 4169",
        "city": "Davis", "state": "CA", "zip_code": "95616",
        "phone": "530-792-5800", "email": "",
        "url": "https://www.rd.usda.gov/ca",
        "description": "USDA Rural Development · California State Office",
        "price_range": "", "bedrooms": [], "units": "", "status": "ok",
    },
    # Public Housing Developments
    {
        "source": "hud", "hud_layer": "Public Housing Developments",
        "hud_program": "Public Housing",
        "title": "Lockwood Gardens — Oakland Housing Authority",
        "address": "315 105th Avenue",
        "city": "Oakland", "state": "CA", "zip_code": "94603",
        "phone": "510-874-1500", "email": "",
        "url": "https://www.oakha.org",
        "description": "Public Housing Development · Oakland, CA",
        "price_range": "", "bedrooms": [], "units": "224", "status": "ok",
    },
    {
        "source": "hud", "hud_layer": "Public Housing Developments",
        "hud_program": "Public Housing",
        "title": "Tassafaronga Village — Oakland Housing Authority",
        "address": "975 85th Avenue",
        "city": "Oakland", "state": "CA", "zip_code": "94621",
        "phone": "510-874-1500", "email": "",
        "url": "https://www.oakha.org",
        "description": "Public Housing Development · Oakland, CA",
        "price_range": "", "bedrooms": [], "units": "157", "status": "ok",
    },
]

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

PHONE_RE = re.compile(r"(\+?1[\s.\-]?)?(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PRICE_RE = re.compile(r"\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:/mo(?:nth)?)?")
BED_RE   = re.compile(r"(\d)\s*(?:bed(?:room)?s?|br)", re.IGNORECASE)


# ── Data model ────────────────────────────────────────────────────────────────
@dataclass
class Listing:
    source: str = "web"
    hud_layer: str = ""
    hud_program: str = ""
    url: str = ""
    title: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    phone: str = ""
    email: str = ""
    price_range: str = ""
    bedrooms: list[str] = field(default_factory=list)
    units: str = ""
    description: str = ""
    status: str = "ok"


# ── Web crawler ───────────────────────────────────────────────────────────────
async def _fetch(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                return url, await r.text(errors="replace")
            return url, None
    except Exception:
        return url, None


def _parse(url, html):
    soup = BeautifulSoup(html, "html.parser")
    lst = Listing(source="web", url=url)
    t = soup.find("title")
    lst.title = t.get_text(strip=True)[:120] if t else urllib.parse.urlparse(url).netloc
    addr = (soup.find(attrs={"itemprop": "streetAddress"})
            or soup.find(class_=re.compile(r"address", re.I))
            or soup.find(id=re.compile(r"address", re.I)))
    if addr:
        lst.address = addr.get_text(" ", strip=True)[:200]
    text = soup.get_text(" ")
    phones = PHONE_RE.findall(text)
    if phones:
        lst.phone = re.sub(r"[^\d+\-() ]", "", "".join(phones[0])).strip()
    emails = EMAIL_RE.findall(text)
    lst.email = next((e for e in emails if not re.search(
        r"(example|noreply|no-reply|sentry|cdn)", e, re.I)), "")
    prices = PRICE_RE.findall(text)
    lst.price_range = prices[0] if prices else ""
    beds = list(dict.fromkeys(BED_RE.findall(text)))
    lst.bedrooms = [f"{b} bed" for b in beds[:6]]
    meta = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    if meta and meta.get("content"):
        lst.description = meta["content"][:300]
    else:
        p = soup.find("p")
        if p:
            lst.description = p.get_text(" ", strip=True)[:300]
    return lst


async def crawl_web():
    connector = aiohttp.TCPConnector(ssl=False, limit=10)
    async with aiohttp.ClientSession(headers=BROWSER_HEADERS, connector=connector) as s:
        pages = await asyncio.gather(*[_fetch(s, u) for u in WEB_URLS])
    results = []
    for url, html in pages:
        if html:
            results.append(_parse(url, html))
        else:
            results.append(Listing(source="web", url=url,
                                   title=urllib.parse.urlparse(url).netloc,
                                   status="error"))
    return results


# ── Combined crawl ────────────────────────────────────────────────────────────
async def crawl_all():
    print(f"\nStarting HUDdl crawl…")
    web_results = await crawl_web()
    print(f"  Web: {len(web_results)} sites | HUD static: {len(HUD_STATIC)} records")
    return [asdict(l) for l in web_results] + HUD_STATIC


# ── Contact helpers ───────────────────────────────────────────────────────────
def send_email(smtp_host, smtp_port, smtp_user, smtp_password,
               from_addr, to_addr, subject, body):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as srv:
            srv.ehlo(); srv.starttls()
            srv.login(smtp_user, smtp_password)
            srv.sendmail(from_addr, to_addr, msg.as_string())
        return {"ok": True, "message": f"Email sent to {to_addr}"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


def initiate_voip_call(phone_number):
    digits = re.sub(r"\D", "", phone_number)
    if not digits:
        return {"ok": False, "message": "No valid phone number."}
    tel_uri = f"tel:+1{digits}" if len(digits) == 10 else f"tel:{digits}"
    return {"ok": True, "tel_uri": tel_uri, "message": f"Open {tel_uri} in your VoIP client."}


# ── Search / export ───────────────────────────────────────────────────────────
def _matches(lst, q):
    if not q:
        return True
    hay = " ".join([lst.get("title",""), lst.get("address",""), lst.get("city",""),
                    lst.get("description",""), lst.get("price_range",""),
                    lst.get("hud_layer",""), lst.get("hud_program",""),
                    lst.get("units",""), " ".join(lst.get("bedrooms",[]))]).lower()
    return q.lower() in hay


def _source_ok(lst, source):
    return source in ("all","") or lst.get("source","") == source


def to_csv(listings):
    if not listings:
        return ""
    fields = ["source","hud_layer","hud_program","title","address","city",
              "state","zip_code","phone","email","price_range","units",
              "bedrooms","description","url","status"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for l in listings:
        row = dict(l)
        row["bedrooms"] = ", ".join(row.get("bedrooms") or [])
        w.writerow(row)
    return buf.getvalue()


# ── HTTP server ───────────────────────────────────────────────────────────────
_cache: list[dict] = []


def _cors(h):
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")


class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, data, ct, status=200):
        self.send_response(status)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        _cors(self); self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, status=200):
        self._send(json.dumps(obj, ensure_ascii=False).encode(),
                   "application/json", status)

    def do_OPTIONS(self):
        self.send_response(204); _cors(self); self.end_headers()

    def do_GET(self):
        global _cache
        p = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(p.query)

        def param(k, d=""):
            return qs.get(k, [d])[0]

        if p.path in ("/api/listings", "/api/hud"):
            if not _cache:
                _cache = asyncio.run(crawl_all())
            q      = param("q").lower()
            source = param("source", "all").lower()
            layer  = param("layer").lower()
            data   = [l for l in _cache
                      if _source_ok(l, source) and _matches(l, q)
                      and (not layer or layer in l.get("hud_layer","").lower())]
            if p.path == "/api/hud":
                data = [l for l in data if l.get("source") == "hud"]
            self._json(data)

        elif p.path == "/api/voip":
            self._json(initiate_voip_call(param("phone")))

        elif p.path == "/api/export":
            if not _cache:
                _cache = asyncio.run(crawl_all())
            q      = param("q").lower()
            source = param("source","all").lower()
            data   = [l for l in _cache if _source_ok(l, source) and _matches(l, q)]
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
    print(f"\n🏠  HUDdl v3 API  →  http://{host}:{port}")
    print("  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nHUDdl stopped.")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8787))
    run_server(port=port)
