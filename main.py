from mtm_flash import setup_driver_headless, login_mtm, add_to_cart_and_checkout
from ipzs_flash import login_ipzs, add_to_cart_ipzs

import requests, re, os, json, time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ──────────────── MTM Credentials
MTM_ACCOUNTS = [
    {"user": os.getenv("MTM_USERNAME"),        "pwd": os.getenv("MTM_PASSWORD")},
    {"user": os.getenv("MTM_USERNAME_ALTERN"), "pwd": os.getenv("MTM_PASSWORD")},
]

# ──────────────── File di stato
SEEN_FILE       = "seen.txt"
LOW_FILE        = "low_mintage_alerts.txt"
DATE_FILE       = "date_alerts.json"
SPIDER_LOCK     = "last_spider.json"
MTM_SEEN_FILE   = "seen_mtm.txt"

# ──────────────── Soglie tirature IPZS
IPZS_LOW_HIGH = 1500  # alert standard
IPZS_FLASH    = 500   # flash-cart

# ──────────────── IPZS Config
CATEGORY_URLS = [
    f"https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p={i}"
    for i in range(1, 6)
]
DOMAIN = "www.shop.ipzs.it"

# ──────────────── Requests session hardening
session = requests.Session()
retry = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
)

adapter = HTTPAdapter(max_retries=retry)
session.mount("https://", adapter)
session.mount("http://", adapter)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    )
}

# ──────────────── MTM Monaco Config
MTM_ROOT   = "https://www.mtm-monaco.mc/index.php?route=common/home"

# ──────────────── Telegram helper
from utils import send
from utils import file_lock

# ──────────────── File helpers
def ld(fp): return set(open(fp, encoding="utf-8").read().splitlines()) if os.path.exists(fp) else set()
def sv(fp,s):
	with file_lock:
		open(fp,"w",encoding="utf-8").write("\n".join(sorted(s)))
def sj(fp,d):
    with file_lock:
        open(fp,"w",encoding="utf-8").write(json.dumps(d, indent=2))
def lj(fp):
    if not os.path.exists(fp):
        return {}
    try:
        with open(fp, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"⚠️ Il file {fp} è corrotto o vuoto, verrà ignorato.")
        return {}

# ──────────────── IPZS scraping
def get_links(url):
    try:
        r = session.get(
            url,
            headers=HEADERS,
            timeout=(3, 6)
        )

        if not is_valid_ipzs_page(r.text):
            print(f"⚠️ HTML sospetto su category page: {url}")
            return []

        soup = BeautifulSoup(r.content, "html.parser")
        return [a["href"] for a in soup.select("a.product-item-link") if a.get("href")]
    except:
        return []

def scrape_ipzs(url):
    try:
        r = session.get(
                url,
                headers=HEADERS,
                timeout=(3, 6)
            )
        if r.status_code != 200:
            return None
        if not is_valid_ipzs_page(r.text):
            print(f"⚠️ HTML sospetto su product page: {url}")
            return None
        soup = BeautifulSoup(r.content, "html.parser")
    except:
        return None

    info = {"link": url}
    title_el = soup.select_one("h1.page-title span.base")
    if not title_el:
        return None
    info["nome"] = title_el.get_text(strip=True)
    pr = soup.select_one("span.price")
    info["prezzo"] = pr.get_text(strip=True) if pr else "N/A"

    stock = soup.select_one("div.stock")
    raw = stock.get_text(strip=True).upper() if stock else ""
    info["disponibilita"] = (
        "NON DISPONIBILE" if "NON DISPONIBILE" in raw else
        "DISPONIBILE"     if "DISPONIBILE"     in raw else
        raw or "N/A"
    )

    attrs = {}
    for tr in soup.select("div.product-info-main table.data tr"):
        th, td = tr.find("th"), tr.find("td")
        if th and td:
            attrs[th.get_text(strip=True).lower()] = td.get_text(strip=True)

    info["contingente"]        = attrs.get("contingente") or attrs.get("tiratura") or attrs.get("numero pezzi","N/A")
    info["data disponibilita"] = attrs.get("data disponibilità") or attrs.get("data disponibilita","N/A")
    info["finitura"]           = attrs.get("finitura","N/A")
    info["metallo"]            = attrs.get("metallo","N/A")
    info["peso (gr)"]          = attrs.get("peso (gr)","N/A")
    info["in vendita da"]      = attrs.get("in vendita da","N/A")

    return info


def parse_tiratura(txt):
    nums = re.findall(r"\d+", txt.replace(".","").replace(" ",""))
    return int(nums[0]) if nums else None


def parse_price(txt):
    txt = (
        txt.replace("€", "")
           .replace("EUR", "")
           .replace(".", "")
           .replace(",", ".")
           .strip()
    )
    try:
        return float(txt)
    except:
        return None


def normalize_text(txt):
    return (txt or "").lower().strip()


def is_fs_2euro(product):
    text = " ".join([
        normalize_text(product.get("nome")),
        normalize_text(product.get("finitura")),
    ])

    has_2euro = (
        "2 euro" in text
        or "2€" in text
        or "2 eur" in text
        or "2 €" in text
        or "2 Euro" in text
    )
    has_fs = any(x in text for x in [
        "fs",
        "proof",
        "fondo specchio"
    ])
    return has_2euro and has_fs


def should_flash_cart(product):
    tiratura = parse_tiratura(product.get("contingente", ""))
    prezzo = parse_price(product.get("prezzo", ""))

    if tiratura is None or prezzo is None:
        return False, None
    # RULE 1
    if tiratura <= 500 and prezzo <= 2000:
        return True, "RULE_1"
    # RULE 2
    if tiratura <= 1000 and prezzo <= 1000:
        return True, "RULE_2"
    # RULE 3
    if tiratura <= 2000 and prezzo <= 300:
        return True, "RULE_3"
    # RULE 4
    if tiratura <= 5000 and prezzo <= 200:
        return True, "RULE_4"
    # RULE 5
    if tiratura <= 10000 and prezzo <= 100:
        return True, "RULE_5"
    # RULE 6
    if (
        tiratura <= 20000
        and prezzo <= 100
        and is_fs_2euro(product)
    ):
        return True, "RULE_6"

    return False, None

FORMATS = ["%d %b %Y","%d %B %Y","%d/%m/%Y","%Y-%m-%d"]


def parse_date(txt):
    for f in FORMATS:
        try:
            return datetime.strptime(txt.strip(), f)
        except:
            pass
    return None


def is_valid_ipzs_page(html):
    html = html.lower()
    bad_signals = [
        "queue-it",
        "captcha",
        "access denied",
        "temporarily unavailable",
    ]
    if any(x in html for x in bad_signals):
        return False
    good_signals = [
        "product-item-link",
        "page-title",
        "product-addtocart-button",
    ]
    return any(x in html for x in good_signals)

# ──────────────── Notifiche standard
def notify_new(prods, seen):
    for p in prods:
        if p["link"] in seen:
            continue

        if "NON DISPONIBILE" in p["disponibilita"].upper():
            continue

        if send(
            f"<b>Nuova moneta</b>\n"
            f"{p['nome']}\n"
            f"{p['prezzo']}\n"
            f"{p['link']}"
        ):
            seen.add(p["link"])

    return seen

def notify_low(prods, alerted):
    for p in prods:
        t = parse_tiratura(p["contingente"])
        if t and t <= IPZS_LOW_HIGH and "NON DISPONIBILE" not in p["disponibilita"].upper() and p["link"] not in alerted:
            msg = (
                f"<b>Moneta a bassa tiratura</b>\n"
                f"- NOME MONETA: {p['nome']}\n"
                f"- PREZZO: {p['prezzo']}\n"
                f"- CONTINGENTE: {p['contingente']}\n"
                f"- DISPONIBILITA: {p['disponibilita']}\n"
                f"- LINK: {p['link']}"
            )
            if send(msg):
                alerted.add(p["link"])
    return alerted

def notify_dates(prods, alerts):
    bucket = {}
    for p in prods:
        d = parse_date(p["data disponibilita"])
        if d:
            bucket.setdefault(d.date(), []).append(p)
    now = datetime.now()
    tomorrow = (now + timedelta(days=1)).date()

    if tomorrow in bucket and len(bucket[tomorrow])>=3 and now.hour>=8:
        key = str(tomorrow)
        if alerts.get(key) != str(now.date()):
            msg = f"<b>{len(bucket[tomorrow])} monete disponibili il {tomorrow}</b>\n"
            msg += "\n".join(f"- {x['nome']}" for x in bucket[tomorrow])
            if send(msg):
                alerts[key] = str(now.date())
    return alerts

def sunday_ping():
    n = datetime.now()
    if n.weekday()==6 and n.hour==11:
        send("🔁 Check domenicale: bot attivo")

# ──────────────── Spider semplice
SPIDER_HOURS=(7,19)
def spider_allowed():
    n = datetime.now()
    if n.hour not in SPIDER_HOURS: return False
    lock = lj(SPIDER_LOCK)
    last = lock.get("ts")
    if last and (n - datetime.fromisoformat(last)).total_seconds() < 3600: return False
    sj(SPIDER_LOCK,{"ts":n.isoformat()})
    return True

def spider(start, max_urls=50, max_depth=3):
    queue = [(u,0) for u in start]
    visited, prods = set(), []
    while queue and len(visited)<max_urls:
        url,depth = queue.pop(0)
        if url in visited or depth>max_depth: continue
        visited.add(url)
        try:
            r = session.get(
                url,
                headers=HEADERS,
                timeout=(3, 6)
            )

            if not is_valid_ipzs_page(r.text):
                print(f"⚠️ HTML sospetto su category page: {url}")
                return []

            soup = BeautifulSoup(r.content, "html.parser")
        except:
            continue
        if soup.select_one("h1.page-title span.base"):
            prods.append(url); continue
        for a in soup.find_all("a",href=True):
            h = a["href"].split("#")[0]
            if DOMAIN in h and not h.endswith((".jpg",".png",".pdf")) and h not in visited:
                queue.append((h,depth+1))
    return prods

# ──────────────── Flash-cart IPZS - Checkout carrello (tiratura ≤ 500)
FLASH_LOG_FILE = "ipzs_flash_log.json"

def flash_ipzs_cart(products):
    # 1️⃣ Filtra i prodotti ≤ soglia FLASH
    to_flash = []
    for p in products:
        if "NON DISPONIBILE" in p["disponibilita"].upper():
            continue
        should_flash, rule = should_flash_cart(p)
        
        if should_flash:
            p["flash_rule"] = rule
            to_flash.append(p)
            
    print(f"🔍 flash_ipzs_cart → prodotti candidati (≤{IPZS_FLASH}): {[p['link'] for p in to_flash]}")

    if not to_flash:
        print("ℹ️ flash_ipzs_cart → nessun prodotto da flash-carto, esco.")
        return

    # 2️⃣ Carica storico flash
    flash_log = {}
    if os.path.exists(FLASH_LOG_FILE):
        try:
            flash_log = lj(FLASH_LOG_FILE)
            print(f"🧾 flash_ipzs_cart → log caricato: {flash_log}")
        except Exception as e:
            print(f"⚠️ flash_ipzs_cart → errore lettura {FLASH_LOG_FILE}: {e}; userò log vuoto")
    else:
        print(f"ℹ️ flash_ipzs_cart → {FLASH_LOG_FILE} non esiste, userò log vuoto")

    today = datetime.now().date()
    added = []

    # 3️⃣ Login IPZS
    driver = setup_driver_headless()
    if not login_ipzs(driver):
        print("❌ flash_ipzs_cart → login IPZS fallito, esco.")
        driver.quit()
        return
    print("✅ flash_ipzs_cart → login IPZS riuscito")

    # 4️⃣ Per ciascun prodotto, controlla se è già stato flashato nell’ultimo mese
    for p in to_flash:
        link = p["link"]
        last = flash_log.get(link)
        last_dt = None
        if last:
            try:
                last_dt = datetime.strptime(last, "%Y-%m-%d").date()
            except:
                print(f"⚠️ flash_ipzs_cart → formato data invalido in log per {link}: {last}")
        days = (today - last_dt).days if last_dt else None
        print(f"   • {link} — ultimo flash: {last_dt} ({days} giorni fa)")

        # decido se posso riflashare
        if last_dt is None or (today - last_dt).days >= 30:
            print(f"     → OK, provo add_to_cart")
            success = add_to_cart_ipzs(driver, link)
            print(f"       add_to_cart_ipzs → {'OK' if success else 'Fallito'}")
            if success:
                added.append(p["nome"])
                flash_log[link] = today.isoformat()
        else:
            print("     → saltato (flash già fatto meno di 30 giorni fa)")

        time.sleep(0.3)

    driver.quit()

    # 5️⃣ Salvo log aggiornato
    try:
        sj(FLASH_LOG_FILE, flash_log)
        print(f"💾 flash_ipzs_cart → log salvato: {flash_log}")
    except Exception as e:
        print(f"❌ flash_ipzs_cart → errore salvataggio log: {e}")

    # 6️⃣ Notifica Telegram
    if added:
        cart_url = "https://www.shop.ipzs.it/it/checkout/"
        msg = "<b>Flash-cart IPZS!</b>\nMonete aggiunte al carrello secondo regole:\n"
        msg += "\n".join(f"- {t}" for t in added)
        msg += f"\n\n➡️ <a href=\"{cart_url}\">Vai al checkout IPZS</a>"
        print(f"✉️ flash_ipzs_cart → invio notifica Telegram per: {added}")
        send(msg)
    else:
        print("ℹ️ flash_ipzs_cart → nessuna aggiunta, nessuna notifica inviata")
	    
# ──────────────── Flash-cart MTM Monaco - Checkout carrello
def check_mtm_monaco():
    print("ℹ️ Avvio controllo MTM Monaco")
    seen = set()
    if os.path.exists(MTM_SEEN_FILE):
        with open(MTM_SEEN_FILE, "r", encoding="utf-8") as f:
            seen = {line.strip() for line in f if line.strip()}
    print(f"🧾 Link già visti: {len(seen)}")

    # --- costruisco new_products con il tuo scraping MTM Monaco ---
    new_products = []

    headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    # 1. prendo la homepage e tutte le categorie product/category
    for i in range(3):
        try:
            response = session.get(MTM_ROOT, headers=headers, timeout=20)            

            if response.status_code != 200:
                print(f"⚠️ MTM status code anomalo: {response.status_code}")
                time.sleep(3)
                continue

            homepage = BeautifulSoup(response.content, "html.parser")

            # 🛡️ Controllo HTML valido
            cat_links = list(set(
                a["href"] for a in homepage.find_all("a", href=True)
                if "product/category" in a["href"]
            ))
            
            if not cat_links:
                print("⚠️ MTM pagina caricata ma nessuna categoria trovata (possibile blocco o errore)")
                time.sleep(3)
                continue
			
            break

        except Exception as e:
            print(f"⚠️ Tentativo {i+1} fallito MTM: {e}")
            time.sleep(3)
    else:
        print("❌ MTM non raggiungibile dopo 3 tentativi")
        return
	 
    # 2. passo ciascuna categoria e prendo tutti i blocchi .product-thumb
    def fetch_category(cat_url):
        try:
            response = session.get(cat_url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.content, "html.parser")
            return soup.select(".product-thumb")
        except:
            return []

    from concurrent.futures import as_completed

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch_category, url) for url in cat_links]

        for future in as_completed(futures):
            blocks = future.result()

            for block in blocks:
                a_tag = block.find("a", href=True)
                title_tag = block.select_one("h4")
                price_tag = block.select_one(".price")

                if not a_tag or not title_tag:
                    continue

                link  = a_tag["href"]
                title = title_tag.get_text(strip=True)

                # 🎯 PRE-FILTRO # (personalizzabile, inserire nell'elenco le parole chiave di interesse)
                if not any(k in title.upper() for k in ["PROOF", "BE", "ORO", "ARGENTO", "2 EURO", "FS", "LIMITED"]):
                    continue

                if link in seen:
                    continue

                price = price_tag.get_text(strip=True) if price_tag else "N/D"

                new_products.append((title, price, link))
                seen.add(link)

                print(f"⚡ TARGET: {title} - STOP anticipato, trovata moneta interessante")

                # 🚀 STOP anticipato
                return handle_mtm_checkout(new_products, seen)
        
def handle_mtm_checkout(new_products, seen):
    print(f"🆕 Nuovi prodotti trovati MTM: {len(new_products)}")

    added_titles = []

    for acct in MTM_ACCOUNTS:
        user, pwd = acct["user"], acct["pwd"]

        if not user or not pwd:
            continue

        print(f"🔐 Login MTM con account {user}")
        driver = setup_driver_headless()

        if not login_mtm(driver, username=user, password=pwd):
            driver.quit()
            continue

        for title, price, link in new_products:
            print(f"🛒 [{user}] aggiungo: {title}")
            ok = add_to_cart_and_checkout(driver, link)

            if ok:
                added_titles.append(title)

            time.sleep(1)

        driver.quit()

    if added_titles:
        cart_url = "https://www.mtm-monaco.mc/index.php?route=checkout/cart"

        msg = "<b>Flash monete Monaco!</b>\n"
        msg += "Sono state aggiunte:\n"
        msg += "\n".join(f"- {t}" for t in added_titles)
        msg += f"\n\n➡️ <a href=\"{cart_url}\">Checkout</a>"

        send(msg)

    if not added_titles:
        print("ℹ️ Nessun prodotto interessante MTM")
    
    with open(MTM_SEEN_FILE, "w", encoding="utf-8") as f:
        for url in seen:
            f.write(url + "\n")

# ──────────────── MAIN
def main():
    seen    = ld(SEEN_FILE)
    alerted = ld(LOW_FILE)
    dates   = lj(DATE_FILE)

    # 1️⃣ scraping IPZS
    links = set()
    for u in CATEGORY_URLS:
        links.update(get_links(u))
    if spider_allowed():
        links.update(spider(CATEGORY_URLS))

    def safe_scrape(url):
        try:
            return scrape_ipzs(url)
        except:
            return None

    prods = []

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(safe_scrape, url) for url in links]

        for future in as_completed(futures):
            p = future.result()
            if p:
                prods.append(p)

    # 2️⃣ notifiche IPZS
    seen    = notify_new(prods, seen)
    alerted = notify_low(prods, alerted)
    dates   = notify_dates(prods, dates)
    flash_ipzs_cart(prods)

    # SALVA SUBITO
    sv(SEEN_FILE, seen)
    sv(LOW_FILE, alerted)
    sj(DATE_FILE, dates)

    # Controllo domenicale
    sunday_ping()

    # 3️⃣ controllo MTM
    check_mtm_monaco()

if __name__ == "__main__":
    print("Start", datetime.now())
    main()
    print("End", datetime.now())
