# mtm_flash.py
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ─────────────── Login e carrello MTM Monaco

MTM_SEEN_FILE = "seen_mtm.txt"

def setup_driver_headless():
    """
    Configura un Chrome headless con webdriver-manager.
    Ritorna un driver Selenium pronto all’uso.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")        # headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(
        ChromeDriverManager(version="124.0.6367.91").install(),
        options=chrome_options
    )
    return driver

def login_mtm(driver):
    """
    Esegue il login su MTM Monaco usando i secrets.
    Restituisce True se login avvenuto con successo, False altrimenti.
    """
    username = os.getenv("MTM_USERNAME")
    password = os.getenv("MTM_PASSWORD")
    if not username or not password:
        print("❌ MTM_USERNAME o MTM_PASSWORD non configurati.")
        return False

    # URL di login MTM (OpenCart standard)
    login_url = "https://www.mtm-monaco.mc/index.php?route=account/login"

    driver.get(login_url)
    time.sleep(1)  # attendi il caricamento del form

    # Trova il form di login: campo email, campo password, pulsante
    try:
        email_input = driver.find_element(By.NAME, "email")
        pass_input  = driver.find_element(By.NAME, "password")
    except:
        print("❌ Non ho trovato i campi di login su MTM.")
        return False

    email_input.clear()
    email_input.send_keys(username)
    pass_input.clear()
    pass_input.send_keys(password)

    # Trova e clicca il pulsante “Login”
    try:
        # In OpenCart, spesso il pulsante ha id="button-login" o name="login"
        btn = driver.find_element(By.CSS_SELECTOR, "input[type='submit']")
        btn.click()
    except:
        print("❌ Non ho trovato il pulsante di login.")
        return False

    time.sleep(2)  # attendi redirect

    # Verifica che la pagina contenga un link “logout” o la dashboard
    page_source = driver.page_source.lower()
    if "/index.php?route=account/logout" in page_source or "account/dashboard" in page_source:
        print("✅ Login MTM riuscito.")
        return True
    else:
        print("❌ Login MTM fallito.")
        return False

def add_to_cart_and_checkout(driver, product_url):
    """
    Visita direttamente la scheda prodotto MTM e aggiunge al carrello.
    Alla fine naviga alla pagina di checkout/cart.
    """
    # 1️⃣ Visita la pagina prodotto
    driver.get(product_url)
    time.sleep(1)  # attendi caricamento

    # 2️⃣ Trova e clicca il pulsante “Aggiungi al carrello”
    try:
        # In OpenCart standard, l’input con id="button-cart" fa l’add-to-cart
        add_btn = driver.find_element(By.ID, "button-cart")
        add_btn.click()
    except:
        print(f"❌ Non ho trovato il pulsante Aggiungi al carrello su {product_url}")
        return False

    # 3️⃣ Attendi conferma (es. messaggio toast) e vai al carrello
    time.sleep(1)
    try:
        driver.get("https://www.mtm-monaco.mc/index.php?route=checkout/cart")
    except:
        print("⚠️ Impossibile navigare alla pagina carrello.")
        return False

    print(f"✅ Prodotto {product_url} aggiunto al carrello, ora in checkout.")
    return True

def flash_purchase_mtm(product_url):
    """
    Funzione wrapper per Selenium:
    - Crea driver headless
    - Esegue login
    - Aggiunge al carrello
    - Lascia aperto il browser per eventuali interazioni manuali
    """
    driver = setup_driver_headless()
    try:
        ok = login_mtm(driver)
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

    except Exception as e:
        print("❌ Errore in flash_purchase_mtm:", e)
        driver.quit()
        return False

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
