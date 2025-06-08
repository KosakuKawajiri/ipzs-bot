from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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
