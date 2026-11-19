from app.backend import data
from scraper.process import clean_projects


def test_property_type_from_category():
    assert data.get_property_type({"category": "Apartments for Sale in Saudi", "url": "x"}) == "apartment"
    assert data.get_property_type({"category": "Properties for Rent", "url": "x"}) == "property"
    assert data.get_property_type({"category": "3 bedroom Apartments for Rent", "url": "x"}) == "apartment"


def test_property_type_from_title_when_no_category():
    item = {"title": "Villa 235.5 SQM Facing North East", "url": "x"}
    assert data.get_property_type(item) == "villa"

    item = {"title": "Rest house with pool", "url": "x"}
    assert data.get_property_type(item) == "rest house"


def test_location_from_address():
    city, zone, district = data.get_location({"address": "Al-Mahdiyah, West Riyadh, Riyadh"})
    assert (city, zone, district) == ("Riyadh", "West Riyadh", "Al-Mahdiyah")


def test_location_prefers_breadcrumbs():
    item = {"city": "Jeddah", "address": "Al Rawdah, North Jeddah, Jeddah"}
    city, zone, district = data.get_location(item)
    assert city == "Jeddah"
    assert district == "Al Rawdah"


def test_area_and_numbers():
    assert data.get_area({"carpetArea": "235.5"}) == 235.5
    assert data.get_area({}) is None
    assert data.to_number("1,250,000") == 1250000
    assert data.to_number("abc") is None


def test_split_text_overlaps():
    pieces = data.split_text("a" * 2000, size=900, overlap=150)
    assert len(pieces) == 3
    assert all(len(piece) <= 900 for piece in pieces)
    assert data.split_text("") == []


def test_snapshot_is_loaded():
    assert len(data.listings) > 300
    assert len(data.projects) > 30
    assert len(data.chunks) > len(data.listings)
    assert data.snapshot_date != "unknown date"

    # no duplicate listing ids
    ids = [listing["id"] for listing in data.listings]
    assert len(ids) == len(set(ids))


def test_clean_projects_fills_description_and_drops_empty():
    projects = [{"name": "Les Vagues", "url": "https://darglobal.co.uk/les-vagues/", "description": "",
                 "bedrooms": "", "tabs": ["Qatar"]}]
    pages = [{"url": "https://darglobal.co.uk/les-vagues", "text": "Branded residences in Doha"}]

    cleaned = clean_projects(projects, pages)
    assert cleaned[0]["description"] == "Branded residences in Doha"
    assert "bedrooms" not in cleaned[0]
    assert "tabs" not in cleaned[0]
