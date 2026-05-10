import requests
from bs4 import BeautifulSoup
import time
import os
from datetime import datetime, timedelta
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

# Effettiva disponibilità prodotto - check con Selenium
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

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


def should_check(link_data):
    if not isinstance(link_data, dict):
        return True
        
    status = link_data.get("status")
    last_check = link_data.get("last_check")
    
    if not last_check:
        return True
    try:
        last_dt = datetime.fromisoformat(last_check)
    except:
        return True
        
    age = datetime.now() - last_dt

    # prodotti già disponibili → ricontrollo ogni 24h
    if status == "AVAILABLE_CARTED":
        return age > timedelta(hours=24)
        
    # prodotti vecchi NON disponibili → ogni 6h
    return age > timedelta(hours=6)


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
                "window.localStorage.setItem(arguments[0], arguments[1]);",
                k,
                v
            )
        for k, v in storage.get("sessionStorage", {}).items():
            driver.execute_script(
                "window.localStorage.setItem(arguments[0], arguments[1]);",
                k,
                v
            )           
        driver.refresh()
        print("💾 Storage IPZS caricato")
        return True

    except Exception as e:
        print(f"⚠️ Errore load storage: {e}")
        return False


def clear_session_files():
    for file in [COOKIE_FILE, STORAGE_FILE]:
        try:
            if os.path.exists(file):
                os.remove(file)
                print(f"🧹 File sessione eliminato: {file}")
        except Exception as e:
            print(f"⚠️ Errore delete {file}: {e}")


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

def sniper_check_availability(driver, url, retries=3):
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
                #buttons[0].click()
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
        load_storage(driver)
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
        print("⚠️ Primo login fallito → recovery")
        driver.quit()
        clear_session_files()
        time.sleep(5)
        driver = setup_driver_headless()
        logged = login_ipzs(driver)

        if not logged:
            print("❌ Recovery login fallito")
            send(
                "<b>SNIPER IPZS</b>\n"
                "Recovery login IPZS fallito"
            )
            driver.quit()
            return

        print("✅ Recovery login riuscito")

    warm_session(driver)
    save_cookies(driver)
    save_storage(driver)
    

    triggered = []

    for link in current_links:
        link_data = seen.get(link, {})
        
        if not should_check(link_data):
            print(f"⏩ Skip intelligente: {link}")
            continue
            
        print(f"🚨 Controllo sniper: {link}")
        status = sniper_check_availability(driver, url)

        if status == "AVAILABLE":
            
            triggered.append(link)
            seen[link] = {
                "status": "AVAILABLE_CARTED",
                "last_check": datetime.now().isoformat()
            }
            save_cookies(driver)
            save_storage(driver)
            send(
                f"<b>SNIPER IPZS</b>\n"
                f"Moneta disponibile intercettata!\n\n"
                f"{link}"
            )

        elif status == "NOT_AVAILABLE":
            seen[link] = {
                "status": "NOT_AVAILABLE",
                "last_check": datetime.now().isoformat()
            }

        elif status == "CART_FAILED":
            print("⚠️ Cart fallito ma prodotto disponibile")
            seen[link] = {
                "status": "CART_FAILED",
                "last_check": datetime.now().isoformat()
            }
            send(
                f"<b>SNIPER IPZS</b>\n"
                f"Prodotto disponibile ma add-to-cart FALLITO\n\n"
                f"{link}"
            )

    driver.quit()

    save_seen(seen)

    print(f"✅ Trigger effettuati: {len(triggered)}")

    print("✅ SNIPER END", datetime.now())


if __name__ == "__main__":
    main()
