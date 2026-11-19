"""Loads the scraped snapshot, normalises it, and exposes it as SQLite + text chunks.

Two kinds of data, two kinds of storage:
  * Listings (price, bedrooms, city...) -> SQLite, queried with filters.
  * Free text (project pages, descriptions, about pages) -> chunks for hybrid retrieval.
"""
import json
import re
import sqlite3
from functools import lru_cache

from .config import RAW_DIR


def _load(name, default):
    path = RAW_DIR / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _num(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def _ptype(rec):
    cat = rec.get("category") or ""
    m = re.match(r"(.+?)\s+for\s+", cat, re.I)
    if m:
        t = m.group(1).strip().lower()
        t = re.sub(r"^\d+\s*bedroom\s+", "", t)
        if t.endswith("ies"):
            t = t[:-3] + "y"
        elif t.endswith("s"):
            t = t[:-1]
        return t
    title = (rec.get("title") or "").lower()
    m = re.match(r"([a-z ]+?)(?:\s+\d|\s+with|\s+for|\s+facing|$)", title)
    if m and m.group(1).strip():
        return m.group(1).strip()
    slug = rec["url"].rstrip("/").split("/")[-1]
    return slug.split("-")[0]


def _location(rec):
    """Prefer breadcrumbs; fall back to 'District, Zone, City' address string."""
    parts = [p.strip() for p in (rec.get("address") or "").split(",") if p.strip()]
    city = rec.get("city") or (parts[-1] if parts else None)
    zone = rec.get("zone") or (parts[-2] if len(parts) >= 3 else None)
    district = rec.get("district") or (parts[0] if len(parts) >= 2 else None)
    return city, zone, district


def _area(attrs):
    for k in ("builtUpArea", "carpetArea", "landArea", "plotArea", "area", "propertyArea"):
        v = _num(attrs.get(k))
        if v:
            return v
    return None


def normalise_listing(r):
    attrs = r.get("attrs") or {}
    city, zone, district = _location(r)
    return {
        "id": r["id"],
        "source": "wasalt",
        "url": r["url"],
        "purpose": r["purpose"],
        "title": r.get("title"),
        "property_type": _ptype(r),
        "main_type": r.get("main_type"),
        "price": _num(r.get("price")),
        "currency": r.get("currency") or "SAR",
        "bedrooms": _num(attrs.get("noOfBedrooms")),
        "bathrooms": _num(attrs.get("noOfBathrooms")),
        "area_sqm": _area(attrs),
        "city": city,
        "zone": zone,
        "district": district,
        "address": r.get("address"),
        "lat": _num(r.get("lat")),
        "lon": _num(r.get("lon")),
        "description": r.get("description") or "",
        "company": r.get("company"),
        "rega_licensed": bool(r.get("rega_licensed")),
        "published": r.get("published"),
        "image": r.get("image"),
    }


@lru_cache
def listings():
    raw = _load("wasalt_listings.json", [])
    seen, out = set(), []
    for r in raw:
        if r.get("id") in seen:
            continue
        seen.add(r["id"])
        out.append(normalise_listing(r))
    return out


@lru_cache
def listings_by_id():
    return {l["id"]: l for l in listings()}


@lru_cache
def darglobal_projects():
    return _load("darglobal_projects.json", [])


@lru_cache
def db():
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.row_factory = sqlite3.Row
    cols = [
        "id", "url", "purpose", "title", "property_type", "price", "currency",
        "bedrooms", "bathrooms", "area_sqm", "city", "zone", "district",
        "company", "rega_licensed", "published",
    ]
    con.execute(f"CREATE TABLE listings ({', '.join(cols)})")
    con.executemany(
        f"INSERT INTO listings VALUES ({', '.join('?' * len(cols))})",
        [[l[c] for c in cols] for l in listings()],
    )
    return con


def _split(text, size=900, overlap=150):
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= size:
        return [text] if text else []
    parts, i = [], 0
    while i < len(text):
        parts.append(text[i : i + size])
        i += size - overlap
    return parts


@lru_cache
def chunks():
    """Every piece of free text the assistant can retrieve, with its source URL."""
    out = []
    for p in _load("darglobal_pages.json", []):
        title = p["title"] or p["url"].rstrip("/").split("/")[-1].replace("-", " ").title()
        for j, c in enumerate(_split(p["text"])):
            out.append({"source": "darglobal", "title": title, "url": p["url"], "text": c})
    for p in _load("wasalt_pages.json", []):
        for j, c in enumerate(_split(p["text"])):
            out.append({"source": "wasalt", "title": p["title"], "url": p["url"], "text": c})
    for l in listings():
        loc = ", ".join(x for x in (l["district"], l["city"]) if x)
        price = f"{l['price']:,.0f} {l['currency']}" if l["price"] else "price on request"
        text = (
            f"[Listing {l['id']}] {l['title']} for {l['purpose']} in {loc}. "
            f"Price {price}. {l['description']}"
        )
        out.append({"source": "wasalt_listing", "title": l["title"], "url": l["url"],
                    "listing_id": l["id"], "text": text[:900]})
    return out
