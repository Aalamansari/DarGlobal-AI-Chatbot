from app.backend import tools


def test_search_listings_applies_all_filters():
    result = tools.search_listings(purpose="sale", city="Riyadh", property_type="apartment",
                                   min_bedrooms=3, max_bedrooms=3, max_price=1000000, limit=10)

    assert result["total_matches_in_snapshot"] > 0
    for listing in result["results"]:
        assert listing["purpose"] == "sale"
        assert "Riyadh" in listing["city"]
        assert listing["property_type"] == "apartment"
        assert listing["bedrooms"] == 3
        assert listing["price"] <= 1000000


def test_search_listings_sorting_and_limit():
    result = tools.search_listings(purpose="sale", sort="price_desc", limit=50)
    prices = [listing["price"] for listing in result["results"]]

    assert len(prices) == 10  # limit is capped at 10
    assert prices == sorted(prices, reverse=True)


def test_search_listings_no_match():
    result = tools.search_listings(city="Atlantis")
    assert result["total_matches_in_snapshot"] == 0
    assert result["results"] == []


def test_search_listings_is_safe_from_sql_injection():
    result = tools.search_listings(city="Riyadh'; DROP TABLE listings; --")
    assert result["results"] == []
    assert tools.search_listings(limit=1)["total_matches_in_snapshot"] > 0


def test_get_listing():
    some_id = tools.search_listings(limit=1)["results"][0]["id"]
    assert tools.get_listing(some_id)["id"] == some_id
    assert "error" in tools.get_listing(1)


def test_market_stats_grouped_by_city():
    result = tools.market_stats(purpose="sale", property_type="villa", group_by="city")
    groups = result["groups"]

    assert len(groups) > 0
    assert groups[0]["listings"] >= groups[-1]["listings"]
    for group in groups:
        assert group["min_price"] <= group["median_price"] <= group["max_price"]


def test_market_stats_ignores_unknown_group_column():
    result = tools.market_stats(group_by="price; DROP TABLE listings")
    assert result["groups"][0]["group"] == "all"


def test_list_darglobal_projects():
    qatar = tools.list_darglobal_projects(country="Qatar")
    assert qatar["count"] >= 1
    assert any("Les Vagues" in project["name"] for project in qatar["projects"])

    pagani = tools.list_darglobal_projects(query="pagani")
    assert pagani["count"] >= 1

    assert tools.list_darglobal_projects(country="Mars")["count"] == 0
