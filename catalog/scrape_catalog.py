"""
SHL Catalog Scraper
Scrapes Individual Test Solutions from https://www.shl.com/solutions/products/product-catalog/
Run once before starting the API server:  python scrape_catalog.py
Outputs: shl_catalog.json
"""
import json
import time
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://www.shl.com"
CATALOG_URL = "https://www.shl.com/solutions/products/product-catalog/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

# Test type codes used by SHL
TEST_TYPE_MAP = {
    "A": "Ability & Aptitude",
    "B": "Biodata & Situational Judgement",
    "C": "Competencies",
    "D": "Development & 360",
    "E": "Assessment Exercises",
    "K": "Knowledge & Skills",
    "M": "Motivation",
    "P": "Personality & Behavior",
    "S": "Simulations",
}


def fetch_page(url: str, retries: int = 3, delay: float = 1.5) -> BeautifulSoup | None:
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            print(f"  [warn] {url} attempt {attempt+1} failed: {e}")
            time.sleep(delay)
    return None


def parse_test_types(cell_text: str) -> list[str]:
    """Extract test type codes from a table cell."""
    codes = re.findall(r"\b[ABCDEKMS]\b", cell_text)
    return list(dict.fromkeys(codes))  # deduplicate, preserve order


def scrape_catalog_page(url: str) -> list[dict]:
    """Scrape one page of the catalog table."""
    soup = fetch_page(url)
    if not soup:
        return []

    products = []
    # The catalog renders as a table; rows have product name links + attribute dots
    rows = soup.select("table tbody tr")
    if not rows:
        # fallback: try div-based layout
        rows = soup.select(".product-catalogue-training-catalogue__row")

    for row in rows:
        try:
            # Name + link
            link_tag = row.find("a")
            if not link_tag:
                continue
            name = link_tag.get_text(strip=True)
            href = link_tag.get("href", "")
            url_full = urljoin(BASE_URL, href) if href else ""

            # Test type codes — SHL marks them with filled circles / letters in cells
            cells = row.find_all("td")
            # Gather all text from the row to find type codes
            row_text = " ".join(c.get_text(separator=" ", strip=True) for c in cells)
            test_types = parse_test_types(row_text)

            # Remote / adaptive flags (look for checkmarks or "yes" text)
            remote_text = row_text.lower()
            remote_testing = "yes" in remote_text or "✓" in remote_text
            adaptive = "adaptive" in remote_text or "irt" in remote_text

            # Description — sometimes in a tooltip or sub-row
            desc_tag = row.find(class_=re.compile(r"desc|detail|tooltip", re.I))
            description = desc_tag.get_text(strip=True) if desc_tag else ""

            products.append(
                {
                    "name": name,
                    "url": url_full,
                    "test_types": test_types,
                    "test_type_labels": [TEST_TYPE_MAP.get(t, t) for t in test_types],
                    "remote_testing": remote_testing,
                    "adaptive_irt": adaptive,
                    "description": description,
                }
            )
        except Exception as e:
            print(f"  [warn] row parse error: {e}")
            continue

    return products


def scrape_product_detail(product: dict) -> dict:
    """Enrich a product with its detail page description."""
    if not product.get("url"):
        return product
    soup = fetch_page(product["url"])
    if not soup:
        return product

    # Try common selectors for description text
    for sel in [".product-hero__description", ".product-detail__description",
                "article p", ".content p"]:
        tag = soup.select_one(sel)
        if tag:
            product["description"] = tag.get_text(strip=True)[:800]  # cap length
            break

    # Also grab duration if present
    duration_tag = soup.find(string=re.compile(r"\d+\s*min", re.I))
    if duration_tag:
        product["duration"] = duration_tag.strip()

    time.sleep(0.5)  # polite crawl delay
    return product


def get_all_catalog_urls() -> list[str]:
    """Collect all paginated catalog URLs (Individual Test Solutions filter)."""
    # SHL uses ?start=0&type=1 style pagination; type=1 = Individual Test Solutions
    urls = []
    start = 0
    page_size = 12  # SHL default

    while True:
        url = f"{CATALOG_URL}?start={start}&type=1&solutions=true"
        soup = fetch_page(url)
        if not soup:
            break

        # Check if this page has products
        rows = soup.select("table tbody tr") or soup.select(".product-catalogue-training-catalogue__row")
        if not rows:
            print(f"  No more rows at start={start}, stopping.")
            break

        urls.append(url)
        print(f"  Found {len(rows)} rows at start={start}")

        # Check for next-page link
        next_link = soup.select_one("a[rel='next'], .pagination__next, a.next")
        if not next_link:
            break
        start += page_size

    return urls if urls else [CATALOG_URL]


def main():
    print("=== SHL Catalog Scraper ===")
    print("Step 1: Discovering catalog pages...")
    page_urls = get_all_catalog_urls()
    print(f"  Found {len(page_urls)} pages to scrape.")

    print("Step 2: Scraping product listings...")
    all_products = []
    seen_urls = set()
    for page_url in page_urls:
        products = scrape_catalog_page(page_url)
        for p in products:
            if p["url"] not in seen_urls:
                seen_urls.add(p["url"])
                all_products.append(p)
        print(f"  Total unique products so far: {len(all_products)}")
        time.sleep(1.0)

    print(f"Step 3: Enriching {len(all_products)} products with detail pages...")
    for i, product in enumerate(all_products):
        print(f"  [{i+1}/{len(all_products)}] {product['name']}")
        all_products[i] = scrape_product_detail(product)

    out_path = "shl_catalog.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_products, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Done. {len(all_products)} products saved to {out_path}")
    # Print a quick summary
    type_counts = {}
    for p in all_products:
        for t in p.get("test_types", []):
            type_counts[t] = type_counts.get(t, 0) + 1
    print("Test type breakdown:", dict(sorted(type_counts.items())))


if __name__ == "__main__":
    main()
