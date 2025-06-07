from mtm_flash import setup_driver_headless, login_mtm, add_to_cart_and_checkout
import requests, re, os, json, time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

TEST_MTM_LINKS = [
"https://www.mtm-monaco.mc/index.php?route=product/product&path=74&product_id=110"
]

# ──────────────── File di stato

SEEN_FILE       = "seen.txt"
LOW_FILE        = "low_mintage_alerts.txt"
DATE_FILE       = "date_alerts.json"
SPIDER_LOCK     = "last_spider.json"
MTM_SEEN_FILE   = "seen_mtm.txt"

# ──────────────── IPZS Config

CATEGORY_URLS = [
"https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=1",
"https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=2",
"https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=3",
"https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=4",
"https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=5",
]
DOMAIN = "www.shop.ipzs.it"

# ──────────────── Telegram helper

def send(text: str) -> bool:
token = os.getenv("TELEGRAM_TOKEN")
chat  = os.getenv("CHAT_ID")
if not token or not chat:
return False
try:
r = requests.post(
f"https://api.telegram.org/bot{token}/sendMessage",
data={"chat_id": chat, "text": text, "parse_mode": "HTML"},
timeout=10
)
r.raise_for_status()
return True
except:
return False

# ──────────────── Helpers file

def ld(fp):
return set(open(fp, encoding="utf-8").read().splitlines()) if os.path.exists(fp) else set()

def sv(fp, s):
open(fp, "w", encoding="utf-8").write("\n".join(sorted(s)))

def lj(fp):
if not os.path.exists(fp):
return {}
try:
return json.load(open(fp, encoding="utf-8"))
except json.JSONDecodeError:
return {}

def sj(fp, d):
open(fp, "w", encoding="utf-8").write(json.dumps(d, indent=2))

# ──────────────── IPZS – parsing link

def get_links(url):
try:
soup = BeautifulSoup(requests.get(url, timeout=10).content, "html.parser")
return [a["href"] for a in soup.select("a.product-item-link") if a.get("href")]
except:
return []

# ──────────────── IPZS – scraping pagina prodotto

def scrape_ipzs(url):
try:
soup = BeautifulSoup(requests.get(url, timeout=10).content, "html.parser")
except:
return None
info = {"link": url}
info["nome"] = soup.select_one("h1.page-title span.base").get_text(strip=True)

pr = soup.select_one("span.price")
info["prezzo"] = pr.get_text(strip=True) if pr else "N/A"

stock = soup.select_one("div.stock")
raw_text = stock.get_text(strip=True).upper() if stock else ""
if "NON DISPONIBILE" in raw_text:
    info["disponibilita"] = "NON DISPONIBILE"
elif "DISPONIBILE" in raw_text:
    info["disponibilita"] = "DISPONIBILE"
else:
    info["disponibilita"] = raw_text or "N/A"

attrs = {}
for tr in soup.select("div.product-info-main table.data tr"):
    th = tr.find("th")
    td = tr.find("td")
    if th and td:
        key = th.get_text(strip=True).lower()
        val = td.get_text(strip=True)
        attrs[key] = val

info["contingente"] = attrs.get("contingente") or attrs.get("tiratura") or attrs.get("numero pezzi", "N/A")
info["data disponibilita"] = attrs.get("data disponibilità") or attrs.get("data disponibilita", "N/A")
info["finitura"] = attrs.get("finitura", "N/A")
info["metallo"] = attrs.get("metallo", "N/A")
info["peso (gr)"] = attrs.get("peso (gr)", "N/A")
info["in vendita da"] = attrs.get("in vendita da", "N/A")

return info

# ──────────────── Parsing

def parse_tiratura(txt):
nums = re.findall(r"\d+", txt.replace(".", "").replace(" ", ""))
return int(nums[0]) if nums else None

FORMATS = ["%d %b %Y", "%d %B %Y", "%d/%m/%Y", "%Y-%m-%d"]
def parse_date(txt):
for f in FORMATS:
try:
return datetime.strptime(txt.strip(), f)
except:
pass
return None

# ──────────────── Notifiche IPZS

(omesse per brevità, identiche)

# ──────────────── MTM Monaco

def check_mtm_monaco():
print("ℹ️ Avvio controllo MTM Monaco")
seen = set()
if os.path.exists(MTM_SEEN_FILE):
with open(MTM_SEEN_FILE, "r", encoding="utf-8") as f:
for line in f:
url = line.strip()
if url:
seen.add(url)
print(f"🧾 Link già visti (seen_mtm.txt): {len(seen)}")

new_products = []
for link in TEST_MTM_LINKS:
    title = "Prodotto DI TEST MTM"
    price = "Prezzo-N/D"
    if link not in seen:
        new_products.append((title, price, link))
        seen.add(link)

print(f"🔍 Nuovi prodotti trovati: {len(new_products)}")
if not new_products:
    print("❌ Nessun nuovo prodotto MTM, esco.")
    return
print("✅ Nuovi prodotti pronti per login Selenium")

driver = setup_driver_headless()
logged = login_mtm(driver)
print(f"🔐 Login riuscito: {logged}")
if not logged:
    driver.quit()
    return

added_titles = []
for title, price, link in new_products:
    print(f"🛒 Aggiungo al carrello: {title}")
    ok = add_to_cart_and_checkout(driver, link)
    print(f"👉 Risultato: {'OK' if ok else 'Fallito'}")
    if ok:
        added_titles.append(title)
    time.sleep(1)

print(f"📦 Totale prodotti aggiunti al carrello: {len(added_titles)}")
driver.quit()

# Salva visto
with open(MTM_SEEN_FILE, "w", encoding="utf-8") as f:
    for url in seen:
        f.write(url + "\n")
		
# ──────────────── MAIN

def main():
seen      = ld(SEEN_FILE)
alerted   = ld(LOW_FILE)
dates     = lj(DATE_FILE)

links = set()
for u in CATEGORY_URLS:
    links.update(get_links(u))
if spider_allowed():
    links.update(spider(CATEGORY_URLS, 50, 3))

prods = []
for l in links:
    p = scrape_ipzs(l)
    if p:
        prods.append(p)
    time.sleep(0.15)

seen    = notify_new(prods, seen)
alerted = notify_low(prods, alerted)
dates   = notify_dates(prods, dates)
sunday_ping()

sv(SEEN_FILE, seen)
sv(LOW_FILE, alerted)
sj(DATE_FILE, dates)

check_mtm_monaco()

if name == "main":
print("Start", datetime.now())
main()
print("End", datetime.now())
