import requests
from bs4 import BeautifulSoup
import time
import os
from datetime import datetime

# riutilizziamo le tue funzioni già esistenti
from main import send
from ipzs_flash import login_ipzs, add_to_cart_ipzs
from mtm_flash import setup_driver_headless

URL = "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/"

SEEN_FILE = "sniper_seen.txt"


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE, "r") as f:
        return {line.strip() for line in f}


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        for url in seen:
            f.write(url + "\n")


def get_links(retries=3):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    for attempt in range(retries):
        try:
            r = requests.get(URL, headers=headers, timeout=10)

            if r.status_code != 200:
                print(f"⚠️ Status code {r.status_code}")
                time.sleep(2)
                continue

            soup = BeautifulSoup(r.content, "html.parser")

            links = set()

            for a in soup.select("a.product-item-link"):
                href = a.get("href")

                if not href:
                    continue

                href = href.split("?")[0].split("#")[0]

                links.add(href)

            return links

        except requests.exceptions.RequestException as e:
            print(f"⚠️ Tentativo {attempt+1}/{retries} fallito: {e}")
            time.sleep(3)

    print("❌ IPZS non raggiungibile")
    return set()


def flash_product(link):
    print(f"🔥 NUOVO LINK → FLASH: {link}")

    driver = setup_driver_headless()

    if not login_ipzs(driver):
        print("❌ Login fallito")
        driver.quit()
        return

    ok = add_to_cart_ipzs(driver, link)

    if ok:
        send(f"🚀 SNIPER: aggiunta al carrello!\n{link}")
    else:
        send(f"⚠️ SNIPER fallito:\n{link}")

    driver.quit()


def main():
    print("🚀 SNIPER START", datetime.now())

    seen = load_seen()
    current_links = get_links()

    if not current_links:
        print("⚠️ Nessun link ottenuto")
        return

    new_links = current_links - seen

    print(f"🔍 Nuovi link trovati: {len(new_links)}")

    driver = setup_driver_headless()

    login_ipzs(driver)

    for link in new_links:
        add_to_cart_ipzs(driver, link)

    driver.quit()

    seen.update(current_links)
    save_seen(seen)

    print("✅ SNIPER END", datetime.now())


if __name__ == "__main__":
    main()
