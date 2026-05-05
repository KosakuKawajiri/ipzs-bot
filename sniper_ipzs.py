import requests
from bs4 import BeautifulSoup
import time
import os
from datetime import datetime

# riutilizziamo le tue funzioni già esistenti
from main import send
from ipzs_flash import login_ipzs, add_to_cart_ipzs
from main import setup_driver_headless

URL = "https://www.shop.ipzs.it/it/"

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


def get_links():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(URL, headers=headers, timeout=10)
    soup = BeautifulSoup(r.content, "html.parser")

    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/it/" in href and ".html" in href:
            links.add(href)

    return links


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

    new_links = current_links - seen

    print(f"🔍 Nuovi link trovati: {len(new_links)}")

    for link in new_links:
        flash_product(link)

    seen.update(current_links)
    save_seen(seen)

    print("✅ SNIPER END", datetime.now())


if __name__ == "__main__":
    main()
