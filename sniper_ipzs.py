import requests
from bs4 import BeautifulSoup
import time
import os
from datetime import datetime
import pickle

# riutilizziamo le tue funzioni già esistenti
from utils import send
from ipzs_flash import login_ipzs
from mtm_flash import setup_driver_headless

URL = "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/"

SEEN_FILE = "sniper_seen.json"
COOKIE_FILE = "cookies_ipzs.pkl"
STORAGE_FILE = "ipzs_storage.json"

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


def save_cookies(driver):
    with open(COOKIE_FILE, "wb") as file:
        pickle.dump(driver.get_cookies(), file)
    print("🍪 Cookie IPZS salvati")


def save_storage(driver):
    storage = {
        "localStorage": driver.execute_script(
            "return {...localStorage};"
        ),
        "sessionStorage": driver.execute_script(
            "return {...sessionStorage};"
        )
    }
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(storage, f)
    print("💾 Storage IPZS salvato")


def load_cookies(driver):
    if not os.path.exists(COOKIE_FILE):
        return False
    try:
        driver.get("https://www.shop.ipzs.it")
        with open(COOKIE_FILE, "rb") as file:

            cookies = pickle.load(file)

        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except:
                pass

        driver.refresh()
        print("🍪 Cookie caricati")
        return True

    except Exception as e:
        print(f"⚠️ Errore load cookies: {e}")
        return False


def load_storage(driver):
    if not os.path.exists(STORAGE_FILE):
        return False

    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            storage = json.load(f)
        driver.get("https://www.shop.ipzs.it")
        for k, v in storage.get("localStorage", {}).items():
            driver.execute_script(
                f"localStorage.setItem('{k}', '{v}');"
            )
        for k, v in storage.get("sessionStorage", {}).items():
            driver.execute_script(
                f"sessionStorage.setItem('{k}', '{v}');"
            )            
        driver.refresh()
        print("💾 Storage IPZS caricato")
        return True

    except Exception as e:
        print(f"⚠️ Errore load storage: {e}")
        return False


def warm_session(driver):
    try:
        warm_pages = [
            "https://www.shop.ipzs.it/it/",
            "https://www.shop.ipzs.it/it/customer/account/",
            URL
        ]
        
        for page in warm_pages:
            print(f"🔥 Warm session: {page}")

            driver.get(page)

            if "queue-it" in driver.current_url.lower():
                print("⏳ Queue-it durante warm session")
                WebDriverWait(driver, 120).until(
                    lambda d: "queue-it" not in d.current_url.lower()
                )

            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            WebDriverWait(driver, 5).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )

        print("✅ Sessione riscaldata")
        return True
    except Exception as e:

        print(f"⚠️ Warm session failed: {e}")
        return False


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

def sniper_check_and_cart(driver, url, retries=3):

    for attempt in range(1, retries + 1):

        print(f"🔎 Tentativo sniper #{attempt}: {url}")

        try:

            driver.get(url)

            # ───────── Queue-it detection
            if "queue-it" in driver.current_url.lower():

                print("⏳ Queue-it rilevato")

                try:
                    WebDriverWait(driver, 120).until(
                        lambda d: "queue-it" not in d.current_url.lower()
                    )

                    print("✅ Uscito da Queue-it")

                    driver.get(url)

                except TimeoutException:
                    print("❌ Timeout Queue-it")
                    return "CART_FAILED"

            # ───────── Attesa render pagina
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            html = driver.page_source.upper()

            # ───────── Disponibilità negativa
            if "NON DISPONIBILE" in html:
                print("❌ Prodotto NON DISPONIBILE")
                return "NOT_AVAILABLE"

            # ───────── Cerca bottone add-to-cart
            buttons = driver.find_elements(By.ID, "product-addtocart-button")

            if not buttons:
                print("⚠️ Bottone add-to-cart non trovato")

                # retry intelligente
                if attempt < retries:

                    wait_time = attempt * 2

                    print(f"⏳ Retry tra {wait_time}s")

                    time.sleep(wait_time)

                    continue

                return "CART_FAILED"

            # ───────── Set quantità
            try:

                qty = driver.find_element(By.ID, "qty")

                qty.clear()

                qty.send_keys("1")

            except Exception as e:
                print(f"⚠️ Campo qty non trovato: {e}")

            # ───────── Click add-to-cart
            try:

                buttons[0].click()
                time.sleep(0.5)

            except Exception as e:

                print(f"⚠️ Click fallito: {e}")

                if attempt < retries:

                    wait_time = attempt * 2

                    print(f"⏳ Retry click tra {wait_time}s")

                    time.sleep(wait_time)

                    continue

                return "CART_FAILED"

            # ───────── Verifica successo
            try:

                WebDriverWait(driver, 8).until(
                    lambda d:
                        "/checkout/cart" in d.current_url
                        or len(d.find_elements(By.CSS_SELECTOR, ".message-success")) > 0
                )

                print("✅ ADD-TO-CART RIUSCITO")

                return "AVAILABLE"

            except TimeoutException:

                print("⚠️ Nessuna conferma add-to-cart")

                if attempt < retries:

                    wait_time = attempt * 2

                    print(f"⏳ Retry conferma tra {wait_time}s")

                    time.sleep(wait_time)

                    continue

                return "CART_FAILED"

        except Exception as e:

            print(f"⚠️ Errore sniper globale: {e}")

            if attempt < retries:

                wait_time = attempt * 2

                print(f"⏳ Retry globale tra {wait_time}s")

                time.sleep(wait_time)

                continue

            return "CART_FAILED"

    return "NOT_AVAILABLE"


def main():
    print("🚀 SNIPER START", datetime.now())

    seen = load_seen()
    current_links = get_links()

    if not current_links:
        print("⚠️ Nessun link ottenuto")
        return
    
    driver = setup_driver_headless()

    logged = False

    # prova cookie
    if load_cookies(driver):

        driver.get("https://www.shop.ipzs.it/it/customer/account/")

        if (
            "customer/account" in driver.current_url.lower()
            and "login" not in driver.current_url.lower()
        ):
            print("✅ Sessione IPZS ripristinata via cookie")
            logged = True

    # fallback login classico
    if not logged:
        print("🔐 Sessione non valida → login classico")
        logged = login_ipzs(driver)

    if not logged:
        print("❌ Login IPZS fallito")
        driver.quit()
        return

    warm_session(driver)
    save_cookies(driver)

    triggered = []

    for link in current_links:

        old_status = seen.get(link)

        # trigger SOLO se prima NON disponibile
        if old_status != "AVAILABLE_CARTED":

            print(f"🚨 Controllo sniper: {link}")

            status = sniper_check_and_cart(driver, link)

            if status == "AVAILABLE":

                triggered.append(link)

                seen[link] = "AVAILABLE_CARTED"

                save_cookies(driver)

                send(
                    f"<b>SNIPER IPZS</b>\n"
                    f"Moneta disponibile intercettata!\n\n"
                    f"{link}"
                )

            elif status == "NOT_AVAILABLE":

                seen[link] = "NOT_AVAILABLE"

            elif status == "CART_FAILED":

                print("⚠️ Cart fallito ma prodotto disponibile")

                seen[link] = "CART_FAILED"

                send(
                    f"<b>SNIPER IPZS</b>\n"
                    f"Prodotto disponibile ma add-to-cart FALLITO\n\n"
                    f"{link}"
                )

        else:

            print(f"ℹ️ Già disponibile in precedenza: {link}")

    driver.quit()

    save_seen(seen)

    print(f"✅ Trigger effettuati: {len(triggered)}")

    print("✅ SNIPER END", datetime.now())


if __name__ == "__main__":
    main()
