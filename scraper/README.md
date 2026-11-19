# Data collection

The data in `data/raw/` was collected on 19 Nov 2026 with the scripts in this folder.

| Script | Source | Output |
|---|---|---|
| `browser/wasalt_listings.js` | Random sample (seed 42) of 240 sale + 110 rent URLs from Wasalt's public sitemap | `wasalt_listings.json` (320 listings; the rest were removed ads returning 404) |
| `browser/wasalt_pages.js` | Wasalt home page (FAQ) and corporate page | `wasalt_pages.json` |
| `browser/darglobal.js` | Dar Global `/projects` page (structured project cards) + project, partner, about, FAQ and press pages | `darglobal_projects.json`, `darglobal_pages.json` |
| `process.py` | The files above | Cleaned projects + `meta.json` |

## Why browser scripts instead of requests/BeautifulSoup

Both sites put a bot check in front of plain HTTP clients: Cloudflare on wasalt.sa and Imperva on darglobal.co.uk, both returning challenge pages or 403s. Building a scraper that gets around those checks would be the wrong call. Instead, the pages were read from a normal browser session on each site, using the same requests a visitor makes.

What the scripts read:
- **Wasalt listings:** schema.org JSON-LD (price, bedrooms, address) plus the page's `__NEXT_DATA__` (location, attributes, licence status).
- **Dar Global projects:** the project cards inside the `/projects` page's `__NEXT_DATA__`. Pages that render on the client fall back to the text inside their `__NEXT_DATA__`.

## Responsible collection

- **robots.txt:** only paths it allows. Wasalt's `/search` is disallowed and was not touched; Dar Global allows `/projects/`, `/press/` and `/blog/`.
- **Rate:** one request every 1.2–1.5 seconds, and a small sample (320 of about 60,000 listings).
- **Bot checks:** the listing script stops immediately if a bot-check page appears.
- **No personal data:** agent and broker names and phone numbers are never stored, only agency names.

## Re-running

1. Open the site in a normal browser, open DevTools → Console, paste a script and press Enter. Each script downloads its JSON file when it finishes.
2. Move the files into `data/raw/`.
3. Run `python -m scraper.process`, then `python -m scripts.build_index` to rebuild the search index.

In production this would run on a schedule, comparing the sitemap with the previous run, through an approved data feed or partner API rather than page scraping.
