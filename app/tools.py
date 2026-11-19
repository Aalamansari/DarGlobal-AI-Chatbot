"""Tools the agent can call. Each returns plain JSON-able data that cites its source URL."""
import statistics

from . import retrieval
from .data import darglobal_projects, db, listings_by_id

LISTING_FIELDS = (
    "id, url, purpose, title, property_type, price, currency, bedrooms, bathrooms, "
    "area_sqm, city, zone, district"
)


def search_listings(purpose=None, city=None, district=None, property_type=None,
                    min_price=None, max_price=None, min_bedrooms=None, max_bedrooms=None,
                    min_area=None, sort="price_asc", limit=6):
    where, args = [], []
    if purpose:
        where.append("purpose = ?"); args.append(purpose.lower())
    if city:
        where.append("city LIKE ?"); args.append(f"%{city}%")
    if district:
        where.append("(district LIKE ? OR zone LIKE ?)"); args += [f"%{district}%"] * 2
    if property_type:
        where.append("property_type LIKE ?"); args.append(f"%{property_type.lower().rstrip('s')}%")
    for col, op, val in (("price", ">=", min_price), ("price", "<=", max_price),
                         ("bedrooms", ">=", min_bedrooms), ("bedrooms", "<=", max_bedrooms),
                         ("area_sqm", ">=", min_area)):
        if val is not None:
            where.append(f"{col} {op} ?"); args.append(val)
    order = {"price_asc": "price IS NULL, price ASC", "price_desc": "price DESC",
             "area_desc": "area_sqm DESC", "newest": "published DESC"}.get(sort, "price ASC")
    sql = f"SELECT {LISTING_FIELDS} FROM listings"
    if where:
        sql += " WHERE " + " AND ".join(where)
    count = db().execute(sql.replace(LISTING_FIELDS, "COUNT(*)", 1), args).fetchone()[0]
    rows = db().execute(f"{sql} ORDER BY {order} LIMIT ?", args + [min(int(limit or 6), 10)]).fetchall()
    return {"total_matches_in_snapshot": count, "results": [dict(r) for r in rows]}


def get_listing(listing_id):
    l = listings_by_id().get(int(listing_id))
    if not l:
        return {"error": f"No listing {listing_id} in the snapshot"}
    return {k: v for k, v in l.items() if k not in ("lat", "lon", "image")}


def market_stats(purpose=None, city=None, property_type=None, group_by=None):
    """Price statistics over the snapshot, optionally grouped by city/district/property_type."""
    where, args = ["price IS NOT NULL", "price > 0"], []
    if purpose:
        where.append("purpose = ?"); args.append(purpose.lower())
    if city:
        where.append("city LIKE ?"); args.append(f"%{city}%")
    if property_type:
        where.append("property_type LIKE ?"); args.append(f"%{property_type.lower().rstrip('s')}%")
    group = group_by if group_by in ("city", "district", "property_type", "purpose") else None
    rows = db().execute(
        f"SELECT {group or 'NULL'} AS g, price, area_sqm FROM listings WHERE {' AND '.join(where)}", args
    ).fetchall()
    buckets = {}
    for r in rows:
        buckets.setdefault(r["g"] or "all", []).append(r)
    out = []
    for g, rs in buckets.items():
        prices = [r["price"] for r in rs]
        ppsqm = [r["price"] / r["area_sqm"] for r in rs if r["area_sqm"]]
        out.append({
            "group": g, "listings": len(rs),
            "median_price": round(statistics.median(prices)),
            "min_price": round(min(prices)), "max_price": round(max(prices)),
            "median_price_per_sqm": round(statistics.median(ppsqm)) if ppsqm else None,
        })
    out.sort(key=lambda x: -x["listings"])
    return {"currency": "SAR", "note": "Computed over the scraped sample, not the full market.",
            "groups": out[:15]}


def list_darglobal_projects(country=None, query=None):
    projects = darglobal_projects()
    res = []
    for p in projects:
        blob = " ".join(str(v) for v in p.values()).lower()
        if country and country.lower() not in blob:
            continue
        if query and not all(w in blob for w in query.lower().split()):
            continue
        res.append(p)
    return {"count": len(res), "projects": res[:20]}


def search_knowledge(query, source="any"):
    sources = {"darglobal": ["darglobal"], "wasalt": ["wasalt", "wasalt_listing"]}.get(source)
    hits = retrieval.search(query, k=6, sources=sources)
    return {"passages": [{"source": h["source"], "title": h["title"], "url": h["url"],
                          "text": h["text"]} for h in hits]}


REGISTRY = {
    "search_listings": search_listings,
    "get_listing": get_listing,
    "market_stats": market_stats,
    "list_darglobal_projects": list_darglobal_projects,
    "search_knowledge": search_knowledge,
}

SCHEMAS = [
    {"type": "function", "function": {
        "name": "search_listings",
        "description": "Filter Wasalt property listings in Saudi Arabia (sale or rent) by structured "
                       "criteria. Use for any question with a budget, city, bedroom count or property type. "
                       "Prices are in SAR (rent prices are per year unless stated).",
        "parameters": {"type": "object", "properties": {
            "purpose": {"type": "string", "enum": ["sale", "rent"]},
            "city": {"type": "string", "description": "e.g. Riyadh, Jeddah, Dammam, Khobar, Makkah"},
            "district": {"type": "string", "description": "Neighbourhood or zone, e.g. Al Narjis, North Riyadh"},
            "property_type": {"type": "string", "description": "apartment, villa, land, building, floor, rest house, shop, office..."},
            "min_price": {"type": "number"}, "max_price": {"type": "number"},
            "min_bedrooms": {"type": "integer", "description": "For an exact count (e.g. '3-bedroom') set min and max to the same value"},
            "max_bedrooms": {"type": "integer"},
            "min_area": {"type": "number", "description": "Minimum area in square metres"},
            "sort": {"type": "string", "enum": ["price_asc", "price_desc", "area_desc", "newest"]},
            "limit": {"type": "integer", "description": "Max 10"}}}}},
    {"type": "function", "function": {
        "name": "get_listing",
        "description": "Full details (description, agency, licence status) of one Wasalt listing by id.",
        "parameters": {"type": "object", "properties": {"listing_id": {"type": "integer"}},
                       "required": ["listing_id"]}}},
    {"type": "function", "function": {
        "name": "market_stats",
        "description": "Median / min / max prices and price per sqm across Wasalt listings, optionally "
                       "grouped. Use for 'average price', 'which area is cheaper', market comparisons.",
        "parameters": {"type": "object", "properties": {
            "purpose": {"type": "string", "enum": ["sale", "rent"]},
            "city": {"type": "string"}, "property_type": {"type": "string"},
            "group_by": {"type": "string", "enum": ["city", "district", "property_type", "purpose"]}}}}},
    {"type": "function", "function": {
        "name": "list_darglobal_projects",
        "description": "List Dar Global's international luxury developments (e.g. in Dubai, London, "
                       "Oman, Saudi Arabia, Spain...). Filter by country or keywords such as a brand partner.",
        "parameters": {"type": "object", "properties": {
            "country": {"type": "string"}, "query": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "search_knowledge",
        "description": "Semantic + keyword search over scraped page text: Dar Global project pages, company "
                       "info, amenities, payment plans, Wasalt service pages and listing descriptions. Use for "
                       "open questions that are not simple filters.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "source": {"type": "string", "enum": ["any", "darglobal", "wasalt"]}},
            "required": ["query"]}}},
]
