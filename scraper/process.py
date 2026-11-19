"""Cleans the files saved by the browser scripts and writes data/raw/meta.json.

Usage: put the downloaded JSON files in data/raw/, then run  python -m scraper.process
"""
import json
from datetime import date
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def read(name):
    with open(RAW_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def write(name, value):
    with open(RAW_DIR / name, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=1)


def clean_projects(projects, pages):
    pages_by_url = {}
    for page in pages:
        pages_by_url[page["url"].rstrip("/")] = page

    cleaned = []
    for project in projects:
        project = dict(project)
        project.pop("tabs", None)

        # project cards often have no description, so use the start of the project page
        page = pages_by_url.get((project.get("url") or "").rstrip("/"))
        if not project.get("description") and page:
            project["description"] = page["text"][:500]

        for key in list(project):
            if project[key] in ("", None):
                project.pop(key)
        cleaned.append(project)
    return cleaned


def main():
    pages = read("darglobal_pages.json")
    projects = clean_projects(read("darglobal_projects.json"), pages)
    write("darglobal_projects.json", projects)

    listings = read("wasalt_listings.json")
    wasalt_pages = read("wasalt_pages.json")

    meta = {
        "collected_on": date.today().isoformat(),
        "sources": {
            "darglobal.co.uk": {"projects": len(projects), "pages": len(pages)},
            "wasalt.sa": {"listings": len(listings), "pages": len(wasalt_pages)},
        },
    }
    write("meta.json", meta)
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
