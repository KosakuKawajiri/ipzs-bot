import os
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ─────────── Login IPZS ───────────
def login_ipzs(driver):
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    login_url = "https://www.shop.ipzs.it/it/customer/account/login/"
    driver.get(login_url)
    time.sleep(5)
    print(f"🌐 URL iniziale: {driver.current_url}")

    # ─────────── Gestione Queue-it ───────────
    if "queue-it" in driver.current_url.lower():
        print("⏳ Queue-it rilevato: attendo uscita dalla coda...")

        try:
            WebDriverWait(driver, 300).until(
                lambda d: "queue-it" not in d.current_url.lower()
            )
            print(f"✅ Uscito dalla coda. Nuovo URL: {driver.current_url}")

            driver.get(login_url)
            time.sleep(2)
            print(f"🔁 Riapro login page: {driver.current_url}")

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


    # ─────────── Login robusto anti-stale ───────────
    try:
        WebDriverWait(driver, 20).until(
            lambda d: "queue-it" not in d.current_url.lower()
        )

        time.sleep(2)
        
        email_input = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.ID, "email"))
        )
        password_input = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.ID, "passw"))
        )

        email_input.clear()
        email_input.send_keys(os.getenv("IPZS_USERNAME"))
        time.sleep(1)

        # rifetch elemento per evitare stale
        password_input = driver.find_element(By.ID, "passw")
        password_input.clear()
        password_input.send_keys(os.getenv("IPZS_PASSWORD"))
        time.sleep(1)

        # rifetch bottone
        login_btn = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.ID, "send3"))
        )
        time.sleep(1)
        login_btn.click()

    except Exception as e:
        print(f"❌ Errore compilazione login: {e}")
        print(f"🔎 URL corrente: {driver.current_url}")

        try:
            print(driver.page_source[:3000])
        except:
            pass

        return False

    # ─────────── Attesa redirect post-login ───────────
    time.sleep(3)

    if "queue-it" in driver.current_url.lower():
        print("⏳ Queue-it rilevato dopo il login...")

        try:
            WebDriverWait(driver, 300).until(
                lambda d: "queue-it" not in d.current_url.lower()
            )

            print(f"✅ Uscito dalla Queue-it post-login: {driver.current_url}")

        except Exception as e:
            print(f"❌ Timeout Queue-it post-login: {e}")
            return False

    # ─────────── Verifica login riuscito ───────────
    try:
        WebDriverWait(driver, 20).until(
            lambda d:
                "customer/account" in d.current_url.lower()
                and "login" not in d.current_url.lower()
        )

        print("✅ Login IPZS riuscito.")
        return True

    except Exception as e:
        print(f"❌ Login IPZS fallito: {e}")
        print(f"🔎 URL finale: {driver.current_url}")

        try:
            print(driver.page_source[:3000])
        except:
            pass

        return False
       

# ─────────── Aggiungi al carrello IPZS ───────────
def add_to_cart_ipzs(driver, product_url):
    driver.get(product_url)

    # ─────────── Gestione Queue-it sulla pagina prodotto ───────────
    if "queue-it" in driver.current_url.lower():
        print("⏳ Queue-it rilevato sulla pagina prodotto...")

        try:
            WebDriverWait(driver, 300).until(
                lambda d: "queue-it" not in d.current_url.lower()
            )

            driver.get(product_url)
            print(f"🔁 Riapro pagina prodotto: {driver.current_url}")

        except Exception as e:
            print(f"❌ Timeout Queue-it prodotto: {e}")
            return False

    # ─────────── Attesa campo quantità ───────────
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "qty"))
        )
    except Exception as e:
        print(f"❌ Campo quantità non trovato: {e}")
        print(f"🔎 URL corrente: {driver.current_url}")
        return False

    qty = driver.find_element(By.ID, "qty")
    qty.clear()
    qty.send_keys("1")

    # ─────────── Click Aggiungi al carrello ───────────
    try:
        add_btn = driver.find_element(By.ID, "product-addtocart-button")
        add_btn.click()
    except Exception as e:
        print(f"❌ Pulsante add-to-cart non trovato: {e}")
        return False

    # ─────────── Verifica successo ───────────
    try:
        WebDriverWait(driver, 10).until(
            lambda d:
                "/checkout/cart" in d.current_url
                or len(d.find_elements(By.CSS_SELECTOR, ".message-success")) > 0
        )

        print(f"✅ add_to_cart_ipzs: prodotto aggiunto ({driver.current_url})")
        return True

    except Exception as e:
        print(
            f"❌ add_to_cart_ipzs fallito per {product_url}: {e}; "
            f"current_url={driver.current_url}"
        )
        return False
