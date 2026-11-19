import statistics

from app.backend import data, retrieval

LISTING_COLUMNS = ("id, url, purpose, title, property_type, price, currency, bedrooms, "
                   "bathrooms, area_sqm, city, zone, district")

SORT_OPTIONS = {
    "price_asc": "price ASC",
    "price_desc": "price DESC",
    "area_desc": "area_sqm DESC",
    "newest": "published DESC",
}


def build_filters(purpose=None, city=None, district=None, property_type=None,
                  min_price=None, max_price=None, min_bedrooms=None, max_bedrooms=None,
                  min_area=None):
    conditions = []
    values = []

    if purpose:
        conditions.append("purpose = ?")
        values.append(purpose.lower())
    if city:
        conditions.append("city LIKE ?")
        values.append("%" + city + "%")
    if district:
        conditions.append("(district LIKE ? OR zone LIKE ?)")
        values.append("%" + district + "%")
        values.append("%" + district + "%")
    if property_type:
        conditions.append("property_type LIKE ?")
        values.append("%" + property_type.lower().rstrip("s") + "%")
    if min_price is not None:
        conditions.append("price >= ?")
        values.append(min_price)
    if max_price is not None:
        conditions.append("price <= ?")
        values.append(max_price)
    if min_bedrooms is not None:
        conditions.append("bedrooms >= ?")
        values.append(min_bedrooms)
    if max_bedrooms is not None:
        conditions.append("bedrooms <= ?")
        values.append(max_bedrooms)
    if min_area is not None:
        conditions.append("area_sqm >= ?")
        values.append(min_area)

    if conditions:
        return " WHERE " + " AND ".join(conditions), values
    return "", values


def search_listings(purpose=None, city=None, district=None, property_type=None,
                    min_price=None, max_price=None, min_bedrooms=None, max_bedrooms=None,
                    min_area=None, sort="price_asc", limit=6):
    where, values = build_filters(purpose, city, district, property_type, min_price,
                                  max_price, min_bedrooms, max_bedrooms, min_area)
    order = SORT_OPTIONS.get(sort, "price ASC")
    limit = min(int(limit), 10)

    total = data.db.execute("SELECT COUNT(*) FROM listings" + where, values).fetchone()[0]
    sql = f"SELECT {LISTING_COLUMNS} FROM listings{where} ORDER BY {order} LIMIT ?"
    rows = data.db.execute(sql, values + [limit]).fetchall()

    return {"total_matches_in_snapshot": total, "results": [dict(row) for row in rows]}


def get_listing(listing_id):
    listing = data.listings_by_id.get(int(listing_id))
    
    if not listing:
        return {"error": f"No listing {listing_id} in the snapshot"}
    result = dict(listing)
    result.pop("image", None)
    
    return result


def market_stats(purpose=None, city=None, property_type=None, group_by=None):
    if group_by not in ["city", "district", "property_type", "purpose"]:
        group_by = None

    where, values = build_filters(purpose=purpose, city=city, property_type=property_type)
    if where:
        where += " AND price > 0"
    else:
        where = " WHERE price > 0"

    group_column = group_by if group_by else "'all'"
    sql = f"SELECT {group_column} AS grp, price, area_sqm FROM listings{where}"
    rows = data.db.execute(sql, values).fetchall()

    groups = {}
    for row in rows:
        name = row["grp"] or "unknown"
        if name not in groups:
            groups[name] = []
        groups[name].append(row)

    stats = []
    for name, group_rows in groups.items():
        prices = [row["price"] for row in group_rows]
        price_per_sqm = []
        for row in group_rows:
            if row["area_sqm"]:
                price_per_sqm.append(row["price"] / row["area_sqm"])

        stats.append({
            "group": name,
            "listings": len(group_rows),
            "median_price": round(statistics.median(prices)),
            "min_price": round(min(prices)),
            "max_price": round(max(prices)),
            "median_price_per_sqm": round(statistics.median(price_per_sqm)) if price_per_sqm else None,
        })

    stats.sort(key=lambda s: s["listings"], reverse=True)
    
    return {
        "currency": "SAR",
        "note": "Computed over the scraped sample, not the full market.",
        "groups": stats[:15],
    }


def list_darglobal_projects(country=None, query=None):
    found = []
    
    for project in data.projects:
        text = " ".join(str(value) for value in project.values()).lower()
        if country and country.lower() not in text:
            continue
        if query:
            words = query.lower().split()
            if not all(word in text for word in words):
                continue
        found.append(project)
    
    return {"count": len(found), "projects": found[:20]}


def search_knowledge(query, source="any"):
    if source == "darglobal":
        sources = ["darglobal"]
    elif source == "wasalt":
        sources = ["wasalt", "wasalt_listing"]
    else:
        sources = None

    passages = []
    for chunk in retrieval.search(query, k=6, sources=sources):
        passages.append({
            "source": chunk["source"],
            "title": chunk["title"],
            "url": chunk["url"],
            "text": chunk["text"],
        })
    
    return {"passages": passages}


TOOLS = {
    "search_listings": search_listings,
    "get_listing": get_listing,
    "market_stats": market_stats,
    "list_darglobal_projects": list_darglobal_projects,
    "search_knowledge": search_knowledge,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_listings",
            "description": "Filter Wasalt property listings in Saudi Arabia (sale or rent). Use for any "
                           "question with a budget, city, bedroom count or property type. Prices are in "
                           "SAR (rent is per year).",
            "parameters": {
                "type": "object",
                "properties": {
                    "purpose": {"type": "string", "enum": ["sale", "rent"]},
                    "city": {"type": "string", "description": "e.g. Riyadh, Jeddah, Dammam, Khobar, Makkah"},
                    "district": {"type": "string", "description": "Neighbourhood or zone, e.g. Al Narjis, North Riyadh"},
                    "property_type": {"type": "string", "description": "apartment, villa, land, building, floor, rest house..."},
                    "min_price": {"type": "number"},
                    "max_price": {"type": "number"},
                    "min_bedrooms": {"type": "integer", "description": "For an exact count (e.g. '3-bedroom') set min and max to the same value"},
                    "max_bedrooms": {"type": "integer"},
                    "min_area": {"type": "number", "description": "Minimum area in square metres"},
                    "sort": {"type": "string", "enum": ["price_asc", "price_desc", "area_desc", "newest"]},
                    "limit": {"type": "integer", "description": "Max 10"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_listing",
            "description": "Full details of one Wasalt listing by id.",
            "parameters": {
                "type": "object",
                "properties": {"listing_id": {"type": "integer"}},
                "required": ["listing_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "market_stats",
            "description": "Median, min and max prices and price per sqm across Wasalt listings, optionally "
                           "grouped. Use for average prices and comparing areas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "purpose": {"type": "string", "enum": ["sale", "rent"]},
                    "city": {"type": "string"},
                    "property_type": {"type": "string"},
                    "group_by": {"type": "string", "enum": ["city", "district", "property_type", "purpose"]},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_darglobal_projects",
            "description": "List Dar Global's international luxury developments (Dubai, London, Oman, Saudi "
                           "Arabia, Spain, Qatar). Filter by country or keywords like a partner brand.",
            "parameters": {
                "type": "object",
                "properties": {
                    "country": {"type": "string"},
                    "query": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Search the scraped page text: Dar Global project pages, company info, amenities, "
                           "payment plans, Wasalt pages and listing descriptions. Use for open questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "source": {"type": "string", "enum": ["any", "darglobal", "wasalt"]},
                },
                "required": ["query"],
            },
        },
    },
]
