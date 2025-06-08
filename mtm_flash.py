# mtm_flash.py
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager


# ─────────────── Login e carrello MTM Monaco

MTM_SEEN_FILE = "seen_mtm.txt"

def setup_driver_headless():
    """
    Configura un Chrome headless usando il chromedriver di sistema.
    Ritorna un driver Selenium pronto all’uso.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    # usa il chromedriver installato da apt-get
    service = Service("/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def login_mtm(driver, username=None, password=None):
    """
    Esegue il login su MTM Monaco usando i secrets.
    Restituisce True se login avvenuto con successo, False altrimenti.
    """
    username = username or os.getenv("MTM_USERNAME")
    password = password or os.getenv("MTM_PASSWORD")
    if not username or not password:
        print("❌ MTM_USERNAME o MTM_PASSWORD non configurati.")
        return False    

    login_url = "https://www.mtm-monaco.mc/index.php?route=account/login"
    driver.get(login_url)
    time.sleep(1)

    try:
        email_input = driver.find_element(By.NAME, "email")
        pass_input  = driver.find_element(By.NAME, "password")
    except Exception as e:
        print("❌ Non ho trovato i campi di login:", e)
        return False

    email_input.clear()
    email_input.send_keys(username)
    pass_input.clear()
    pass_input.send_keys(password)

    try:
        btn = driver.find_element(By.CSS_SELECTOR, "input[type='submit']")
        btn.click()
    except Exception as e:
        print("❌ Non ho trovato il pulsante di login:", e)
        return False

    time.sleep(2)

    # verifica riuscita del login controllando il titolo della pagina
    title = driver.title.lower()
    print(f"🏷️ Titolo pagina dopo login: {driver.title!r}")
    if "votre compte" in title or "mon compte" in title or "logout" in src.lower():
        print("✅ Login MTM riuscito.")
        return True
    else:
        print("❌ Login MTM fallito.")
        return False

def add_to_cart_and_checkout(driver, product_url):
    """
    Visita la pagina prodotto MTM e aggiunge al carrello.
    Poi naviga alla pagina di checkout/cart.
    """
    driver.get(product_url)
    time.sleep(2)  # attendi caricamento completo

    # 1️⃣ Trova e clicca il bottone via ID
    try:
        add_btn = driver.find_element(By.ID, "button-cart")
        add_btn.click()
        print("✅ Click sul pulsante Aggiungi al carrello eseguito.")
    except Exception as e:
        print(f"❌ Errore clic Aggiungi al carrello su {product_url}: {e}")
        return False

    # 2️⃣ Lascia un paio di secondi per eseguire eventuale JS interno
    time.sleep(2)

    # 3️⃣ Naviga al carrello
    try:
        driver.get("https://www.mtm-monaco.mc/index.php?route=checkout/cart")
        print("✅ Navigato al carrello.")
    except Exception as e:
        print("⚠️ Impossibile navigare alla pagina carrello:", e)
        return False

    return True

def flash_purchase_mtm(product_url, username=None, password=None):
    """
    Funzione wrapper per Selenium:
    - Crea driver headless
    - Esegue login
    - Aggiunge al carrello
    - Lascia aperto il browser per eventuali interazioni manuali
    """
    driver = setup_driver_headless()
    try:
        ok = login_mtm(driver, username=username, password=password)
        if not ok:
            driver.quit()
            return False
        success = add_to_cart_and_checkout(driver, product_url)
        if not success:
            driver.quit()
            return False
        # A questo punto il carrello è pronto.
        # Puoi, se vuoi, procedere al checkout automatico inserendo dati di spedizione.
        # Ma almeno il carrello è popolato e puoi intervenire manualmente velocemente.
        return True
    #except Exception as e:
       # print("❌ Errore in flash_purchase_mtm:", e)
       # driver.quit()
       # return False
    finally:
        driver.quit()
   

# ===== Esempio di utilizzo standalone =====
if __name__ == "__main__":
    # Esempio: usa il primo argomento come URL prodotto
    import sys
    if len(sys.argv) < 2:
        print("Usage: python mtm_flash.py <product_url>")
        sys.exit(1)

    prod_url = sys.argv[1]
    if flash_purchase_mtm(prod_url):
        print("🔔 Flash purchase flow completato.")
    else:
        print("❌ Flash purchase flow fallito.")
