import os
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ─────────── Login IPZS ───────────
def login_ipzs(driver):
    login_url = "https://www.shop.ipzs.it/it/customer/account/login/"
    driver.get(login_url)

    print(f"🌐 URL iniziale: {driver.current_url}")

    # ─────────── Gestione Queue-it ───────────
    if "queue-it" in driver.current_url.lower():
        print("⏳ Queue-it rilevato: attendo uscita dalla coda...")

        try:
            WebDriverWait(driver, 300).until(
                lambda d: "queue-it" not in d.current_url.lower()
            )
            print(f"✅ Uscito dalla coda. Nuovo URL: {driver.current_url}")

        except Exception as e:
            print(f"❌ Timeout attesa Queue-it: {e}")
            return False

    # ─────────── Attesa login page reale ───────────
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "email"))
        )
    except Exception as e:
        print(f"❌ Campo email non trovato: {e}")
        print(f"🔎 URL corrente: {driver.current_url}")
        return False

    # ─────────── Login ───────────
    driver.find_element(By.ID, "email").send_keys(os.getenv("MTM_USERNAME"))
    driver.find_element(By.ID, "passw").send_keys(os.getenv("MTM_PASSWORD"))
    driver.find_element(By.ID, "send3").click()

    try:
        WebDriverWait(driver, 15).until(
            EC.url_contains("/it/customer/account/")
        )
        print("✅ Login IPZS riuscito.")
        return True

    except Exception as e:
        print(f"❌ Login IPZS fallito: {e}")
        print(f"🔎 URL finale: {driver.current_url}")
        return False

# ─────────── Aggiungi al carrello IPZS ───────────
def add_to_cart_ipzs(driver, product_url):
    driver.get(product_url)

    # attendi che il campo quantità sia presente
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "qty"))
    )
    qty = driver.find_element(By.ID, "qty")
    qty.clear()
    qty.send_keys("1")

    # clicca il pulsante "Aggiungi al Carrello"
    add_btn = driver.find_element(By.ID, "product-addtocart-button")
    add_btn.click()

    # attendi O toast di successo O redirect al carrello
    try:
        WebDriverWait(driver, 10).until(lambda d: 
            "/checkout/cart" in d.current_url
            or len(d.find_elements(By.CSS_SELECTOR, ".message-success")) > 0
        )
        print(f"✅ add_to_cart_ipzs: prodotto aggiunto ({driver.current_url})")
        return True
    except Exception as e:
        print(f"❌ add_to_cart_ipzs fallito per {product_url}: {e}; current_url={driver.current_url}")
        return False
