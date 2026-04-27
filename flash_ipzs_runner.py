from main import (
    get_links,
    scrape_ipzs,
    parse_tiratura,
    CATEGORY_URLS,
    IPZS_FLASH,
    flash_ipzs_cart
)

import time


def main():
    print("🚀 Avvio workflow separato Flash IPZS")

    links = set()

    for url in CATEGORY_URLS:
        links.update(get_links(url))

    print(f"🔎 Trovati {len(links)} link prodotto")

    products = []

    for link in links:
        p = scrape_ipzs(link)
        if p:
            products.append(p)
        time.sleep(0.2)

    print(f"📦 Prodotti validi trovati: {len(products)}")

    flash_ipzs_cart(products)

    print("✅ Fine workflow Flash IPZS")


if __name__ == "__main__":
    main()
