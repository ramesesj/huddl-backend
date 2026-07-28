#!/usr/bin/env python3
"""
build_database.py — regenerates hud_data.json from HUD's official ArcGIS
open-data services, filtered to Alameda County, CA.
─────────────────────────────────────────────────────────────────────────────
Why: the old hud_data.json was built by matching CITY NAMES against HUD's
national data, which pulled in "Dublin Village" (Alabama), "Albany Housing"
(Georgia), etc. This script filters GEOGRAPHICALLY — a bounding box around
Alameda County at query time, then the same strict city/ZIP county filter
HUDdl.py uses — so only real Alameda County records survive.

Usage:
    python build_database.py            # writes hud_data.json next to itself
    python build_database.py --dry-run  # fetch + report, don't write

Run it locally whenever you want fresh HUD data, commit the new
hud_data.json, and redeploy. (Or run it as a Render Cron Job.)

Requires: requests  (pip install requests)
"""

import argparse, json, os, re, sys, time

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "requests", "--quiet"])
    import requests

# Reuse the exact county filter from the backend.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from HUDdl import ALAMEDA_CITIES, _zip_in_alameda, _city_in_alameda  # noqa: E402

# ── HUD ArcGIS layers (org VTyQ9soqVukalItT = HUD eGIS) ──────────────────────
ARCGIS_BASE = "https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services"

LAYERS = [
    {"service": "Multifamily_Properties_Assisted",
     "hud_layer": "Multifamily Properties (Assisted)",
     "hud_program": "HUD Multifamily Assisted"},
    {"service": "LIHTC",
     "hud_layer": "Low Income Housing Tax Credits",
     "hud_program": "LIHTC"},
    {"service": "Public_Housing_Buildings",
     "hud_layer": "Public Housing Buildings",
     "hud_program": "Public Housing"},
    {"service": "Public_Housing_Developments",
     "hud_layer": "Public Housing Developments",
     "hud_program": "Public Housing"},
    {"service": "Public_Housing_Authorities",
     "hud_layer": "Public Housing Authorities",
     "hud_program": "Public Housing Authority"},
]

# Alameda County bounding box (WGS84). Slightly generous on purpose —
# the strict city/ZIP filter below trims neighbors (SF, Contra Costa, …).
BBOX = {"xmin": -122.374, "ymin": 37.44, "xmax": -121.462, "ymax": 37.912}

# HUD layers use different schemas; try these field names in order.
FIELD_CANDIDATES = {
    "title":   ["PROPERTY_NAME_TEXT", "PROJECT_NAME", "PROJECT", "FORMAL_PARTICIPANT_NAME",
                "PARTICIPANT_NAME", "DEVELOPMENT_NAME", "BLDG_NAME", "NAME", "PROJ_NAME"],
    "address": ["STD_ADDR", "PROJ_ADD", "ADDRESS", "FULL_ADDRESS", "STD_ADDR_TEXT",
                "ADDRESS_LINE1_TEXT", "BLDG_ADDRESS"],
    "city":    ["STD_CITY", "PROJ_CTY", "CITY", "STD_CITY_NAME", "PLACE_NAME"],
    "state":   ["STD_ST", "PROJ_ST", "STATE", "STATE_CODE", "STD_STATE"],
    "zip":     ["STD_ZIP5", "PROJ_ZIP", "ZIP", "ZIP_CODE", "ZIP5", "STD_ZIP"],
    "phone":   ["PHONE", "PHONE_NUMBER", "HA_PHN_NUM", "PHN_NUM"],
    "units":   ["TOTAL_UNIT_COUNT", "N_UNITS", "TOTAL_UNITS", "UNITS",
                "TOTAL_DWELLING_UNITS", "LI_UNITS", "ACC_UNITS"],
    "url":     ["WEBSITE", "URL", "WEB_ADDRESS"],
}

def pick(attrs: dict, keys: list[str]) -> str:
    """First non-empty attribute among candidate field names (case-insensitive)."""
    lower = {k.upper(): v for k, v in attrs.items()}
    for k in keys:
        v = lower.get(k.upper())
        if v not in (None, "", " ", "null", 0):
            return str(v).strip()
    return ""

def fetch_layer(service: str, layer_id: int = 0) -> list[dict]:
    """Page through an ArcGIS layer query, geographically limited to the bbox."""
    url = f"{ARCGIS_BASE}/{service}/FeatureServer/{layer_id}/query"
    out, offset = [], 0
    while True:
        params = {
            "where": "1=1",
            "geometry": json.dumps(BBOX),
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": "false",
            "resultOffset": offset,
            "resultRecordCount": 1000,
            "f": "json",
        }
        r = requests.get(url, params=params, timeout=60)
        r.raise_for_status()
        body = r.json()
        if "error" in body:
            raise RuntimeError(f"{service}: {body['error'].get('message')}")
        feats = body.get("features", [])
        out.extend(f.get("attributes", {}) for f in feats)
        if not body.get("exceededTransferLimit") and len(feats) < 1000:
            break
        offset += len(feats)
        time.sleep(0.5)
    return out

def in_alameda(city: str, state: str, zip_code: str) -> bool:
    if state and state.upper() not in ("CA", "CALIFORNIA"):
        return False
    zm = re.search(r"\d{5}", zip_code or "")
    if zm:
        return _zip_in_alameda(zm.group(0))
    return bool(city) and _city_in_alameda(city)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    records, report = [], []
    for layer in LAYERS:
        svc = layer["service"]
        try:
            attrs_list = fetch_layer(svc)
        except Exception as e:
            print(f"  [skip] {svc}: {e}")
            report.append((svc, "ERROR", 0, 0))
            continue

        kept = 0
        for a in attrs_list:
            city  = pick(a, FIELD_CANDIDATES["city"])
            state = pick(a, FIELD_CANDIDATES["state"])
            zip5  = pick(a, FIELD_CANDIDATES["zip"])
            if not in_alameda(city, state, zip5):
                continue
            title = pick(a, FIELD_CANDIDATES["title"])
            if not title:
                continue
            units = pick(a, FIELD_CANDIDATES["units"])
            records.append({
                "source":      "hud",
                "hud_layer":   layer["hud_layer"],
                "hud_program": layer["hud_program"],
                "title":       title.title() if title.isupper() else title,
                "url":         pick(a, FIELD_CANDIDATES["url"]),
                "address":     pick(a, FIELD_CANDIDATES["address"]),
                "city":        city.title() if city else "",
                "state":       "CA",
                "zip_code":    zip5,
                "phone":       pick(a, FIELD_CANDIDATES["phone"]),
                "email":       "",
                "price_range": "Income-based",
                "bedrooms":    [],
                "units":       units,
                "description": f"{layer['hud_layer']} · Alameda County, CA",
                "status":      "ok",
            })
            kept += 1
        report.append((svc, "OK", len(attrs_list), kept))
        print(f"  [HUD] {svc}: {len(attrs_list)} in bbox → {kept} in Alameda County")

    # Dedup (same property can appear via multiple programs — keep both
    # layers, but drop exact repeats within a layer)
    seen, unique = set(), []
    for r in records:
        key = (r["hud_layer"], r["title"].lower(), r["address"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(r)

    print(f"\n  Total: {len(unique)} Alameda County HUD records")
    for svc, status, total, kept in report:
        print(f"    {svc:38s} {status:5s} bbox={total:5d} kept={kept}")

    if args.dry_run:
        print("  (dry run — hud_data.json not written)")
        return 0
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "hud_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=1)
    print(f"  Wrote {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
