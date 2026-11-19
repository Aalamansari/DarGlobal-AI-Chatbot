import json
import re
import sqlite3

from app.backend.config import RAW_DIR


def load_json(filename, default=None):
    path = RAW_DIR / filename
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def to_number(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def get_property_type(item):
    # category looks like "Apartments for Sale in Saudi"
    category = (item.get("category") or "").lower()

    if " for " in category:
        name = category.split(" for ")[0]
        name = re.sub(r"^\d+ bedroom ", "", name)
        if name.endswith("ies"):
            name = name[:-3] + "y"
        elif name.endswith("s"):
            name = name[:-1]
        return name

    # no category, so use the start of the title e.g. "Villa 300 SQM Facing North"
    title = (item.get("title") or "").lower()
    words = []
    
    for word in title.split():
        if word in ("with", "for", "facing") or word[0].isdigit():
            break
        words.append(word)
    
    if words:
        return " ".join(words)

    return item["url"].split("/")[-1].split("-")[0]


def get_location(item):
    # address looks like "Al-Mahdiyah, West Riyadh, Riyadh"
    parts = []
    
    for part in (item.get("address") or "").split(","):
        if part.strip():
            parts.append(part.strip())

    city = item.get("city")
    zone = item.get("zone")
    district = item.get("district")

    if not city and len(parts) >= 1:
        city = parts[-1]
    
    if not zone and len(parts) >= 3:
        zone = parts[-2]
    
    if not district and len(parts) >= 2:
        district = parts[0]

    return city, zone, district


def get_area(attrs):
    for key in ["builtUpArea", "carpetArea", "landArea", "plotArea", "area", "propertyArea"]:
        area = to_number(attrs.get(key))
        if area:
            return area
    
    return None


def clean_listing(item):
    attrs = item.get("attrs") or {}
    city, zone, district = get_location(item)

    return {
        "id": item["id"],
        "url": item["url"],
        "purpose": item["purpose"],
        "title": item.get("title"),
        "property_type": get_property_type(item),
        "price": to_number(item.get("price")),
        "currency": item.get("currency") or "SAR",
        "bedrooms": to_number(attrs.get("noOfBedrooms")),
        "bathrooms": to_number(attrs.get("noOfBathrooms")),
        "area_sqm": get_area(attrs),
        "city": city,
        "zone": zone,
        "district": district,
        "address": item.get("address"),
        "description": item.get("description") or "",
        "company": item.get("company"),
        "rega_licensed": bool(item.get("rega_licensed")),
        "published": item.get("published"),
        "image": item.get("image"),
    }


def load_listings():
    result = []
    seen_ids = set()
    
    for item in load_json("wasalt_listings.json", []):
        if item["id"] in seen_ids:
            continue
        seen_ids.add(item["id"])
        result.append(clean_listing(item))
    
    return result


def create_database(listings):
    columns = [
        "id", "url", "purpose", "title", "property_type", "price", "currency",
        "bedrooms", "bathrooms", "area_sqm", "city", "zone", "district",
        "company", "rega_licensed", "published",
    ]
    
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE listings (" + ", ".join(columns) + ")")

    placeholders = ", ".join(["?"] * len(columns))
    
    for listing in listings:
        row = [listing[col] for col in columns]
        conn.execute("INSERT INTO listings VALUES (" + placeholders + ")", row)
    
    return conn


def split_text(text, size=900, overlap=150):
    text = re.sub(r"\s+", " ", text).strip()
    
    pieces = []
    start = 0
    
    while start < len(text):
        pieces.append(text[start:start + size])
        start += size - overlap
    
    return pieces


def create_chunks(listings):
    chunks = []

    for page in load_json("darglobal_pages.json", []):
        title = page["title"]
        if not title:
            title = page["url"].rstrip("/").split("/")[-1].replace("-", " ").title()
        for piece in split_text(page["text"]):
            chunks.append({"source": "darglobal", "title": title, "url": page["url"], "text": piece})

    for page in load_json("wasalt_pages.json", []):
        for piece in split_text(page["text"]):
            chunks.append({"source": "wasalt", "title": page["title"], "url": page["url"], "text": piece})

    for listing in listings:
        place = ", ".join([x for x in [listing["district"], listing["city"]] if x])
        if listing["price"]:
            price = f"{listing['price']:,.0f} {listing['currency']}"
        else:
            price = "price on request"
        text = f"[Listing {listing['id']}] {listing['title']} for {listing['purpose']} in {place}. Price {price}. {listing['description']}"
        chunks.append({"source": "wasalt_listing", "title": listing["title"], "url": listing["url"], "text": text[:900]})

    return chunks


# loading everything once when the app starts
listings = load_listings()
listings_by_id = {listing["id"]: listing for listing in listings}
projects = load_json("darglobal_projects.json", [])
chunks = create_chunks(listings)
db = create_database(listings)

meta = load_json("meta.json", {})
snapshot_date = meta.get("collected_on", "unknown date")