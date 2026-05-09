import requests
from bs4 import BeautifulSoup
import time
import os
from datetime import datetime

# riutilizziamo le tue funzioni già esistenti
from utils import send
from ipzs_flash import login_ipzs, add_to_cart_ipzs
from mtm_flash import setup_driver_headless

URL = "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/"

SEEN_FILE = "sniper_seen.json"

import json

def load_seen():
    if not os.path.exists(SEEN_FILE):
        return {}
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2)

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

# Effettiva disponibilità prodotto - check con Selenium
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

def is_product_available(driver, url):

    try:
        driver.get(url)

        WebDriverWait

        html = driver.page_source.upper()

        if "NON DISPONIBILE" in html:
            return False

        buttons = driver.find_elements(By.ID, "product-addtocart-button")

        if buttons:
            return True

        return False

    except Exception as e:
        print(f"⚠️ Selenium availability check error: {e}")
        return False

def smart_add_to_cart(driver, link, retries=3):

    for attempt in range(1, retries + 1):

        print(f"🛒 Tentativo add-to-cart #{attempt}")

        try:

            ok = add_to_cart_ipzs(driver, link)

            if ok:
                print("✅ Add-to-cart riuscito")
                return True

        except Exception as e:
            print(f"⚠️ Errore add-to-cart: {e}")

        # backoff progressivo
        wait_time = attempt * 2

        print(f"⏳ Attendo {wait_time}s prima del retry")

        time.sleep(wait_time)

    print("❌ Tutti i tentativi add-to-cart falliti")

    return False

def main():
    print("🚀 SNIPER START", datetime.now())

    seen = load_seen()
    current_links = get_links()

    if not current_links:
        print("⚠️ Nessun link ottenuto")
        return
    
    driver = setup_driver_headless()

    if not login_ipzs(driver):
        print("❌ Login IPZS fallito")
        driver.quit()
        return

    triggered = []

    for link in current_links:

        available = is_product_available(driver, link)

        old_status = seen.get(link)

        # trigger SOLO quando passa a disponibile
        if available and old_status != "AVAILABLE":

            print(f"🚨 Disponibile ORA: {link}")

            ok = smart_add_to_cart(driver, link)

            if ok:
                triggered.append(link)
                send(
                    f"<b>SNIPER IPZS</b>\n"
                    f"Moneta disponibile intercettata!\n\n"
                    f"{link}"
                )

        seen[link] = "AVAILABLE" if available else "NOT_AVAILABLE"

    driver.quit()

    save_seen(seen)

    print(f"✅ Trigger effettuati: {len(triggered)}")

    print("✅ SNIPER END", datetime.now())


if __name__ == "__main__":
    main()
