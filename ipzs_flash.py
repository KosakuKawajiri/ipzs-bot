from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os

#----------------- Istruzioni per login
def login_ipzs(driver):
    driver.get("https://www.shop.ipzs.it/it/customer/account/login/")
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "email"))
    )
    driver.find_element(By.ID, "email").send_keys(os.getenv("MTM_USERNAME"))
    driver.find_element(By.ID, "passw").send_keys(os.getenv("MTM_PASSWORD"))
    driver.find_element(By.ID, "send3").click()
    # aspetta redirect alla dashboard
    try:
        WebDriverWait(driver, 10).until(
            EC.url_contains("/it/customer/account/")
        )
        print("✅ Login IPZS riuscito.")
        return True
    except:
        print("❌ Login IPZS fallito.")
        return False

#----------------- Istruzioni per aggiungere al carrello
def add_to_cart_ipzs(driver, product_url):
    driver.get(product_url)
    # attendi che il campo qty sia presente
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "qty"))
    )
    qty = driver.find_element(By.ID, "qty")
    qty.clear()
    qty.send_keys("1")

    # clicca il pulsante
    add_btn = driver.find_element(By.ID, "product-addtocart-button")
    add_btn.click()

    # attendi che compaia un toast o redirect al carrello
    try:
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".message-success"))
        )
        return True
    except:
        return False
