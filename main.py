from mtm_flash import setup_driver_headless, login_mtm, add_to_cart_and_checkout
from ipzs_flash import login_ipzs, add_to_cart_ipzs

import requests, re, os, json, time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

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

# ──────────────── MTM Monaco Config
MTM_ROOT   = "https://www.mtm-monaco.mc/index.php?route=common/home"

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

# ──────────────── File helpers
def ld(fp): return set(open(fp, encoding="utf-8").read().splitlines()) if os.path.exists(fp) else set()
def sv(fp,s): open(fp,"w",encoding="utf-8").write("\n".join(sorted(s)))
def lj(fp):
    if not os.path.exists(fp):
        return {}
    try:
        with open(fp, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"⚠️ Il file {fp} è corrotto o vuoto, verrà ignorato.")
        return {}
def sj(fp,d): open(fp,"w",encoding="utf-8").write(json.dumps(d, indent=2))

# ──────────────── IPZS scraping
def get_links(url):
    try:
        soup = BeautifulSoup(requests.get(url, timeout=10).content, "html.parser")
        return [a["href"] for a in soup.select("a.product-item-link") if a.get("href")]
    except:
        return []

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

FORMATS = ["%d %b %Y","%d %B %Y","%d/%m/%Y","%Y-%m-%d"]
def parse_date(txt):
    for f in FORMATS:
        try:
            return datetime.strptime(txt.strip(), f)
        except:
            pass
    return None

# ──────────────── Notifiche standard
def notify_new(prods, seen):
    for p in prods:
        if p["link"] in seen: continue
        if send(f"<b>Nuova moneta</b>\n{p['nome']}\n{p['prezzo']}\n{p['link']}"):
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
    if last and (n - datetime.fromisoformat(last)).seconds<3600: return False
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
            soup = BeautifulSoup(requests.get(url,timeout=10).content,"html.parser")
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
    to_flash = [
        p for p in products
        if (t := parse_tiratura(p["contingente"])) is not None
           and t <= IPZS_FLASH
           and "NON DISPONIBILE" not in p["disponibilita"].upper()
    ]
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

        time.sleep(1)

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
        msg = "<b>Flash-cart IPZS!</b>\nAggiunte al carrello (tiratura ≤ 500):\n"
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
	 
    # 1. prendo la homepage e tutte le categorie product/category
    homepage = BeautifulSoup(requests.get(MTM_ROOT, timeout=10).content, "html.parser")
    cat_links = [
         a["href"] for a in homepage.find_all("a", href=True)
         if "product/category" in a["href"]
	]
	 
     # 2. passo ciascuna categoria e prendo tutti i blocchi .product-thumb
    for cat_url in cat_links:
         try:
             cat_page = BeautifulSoup(requests.get(cat_url, timeout=10).content, "html.parser")
         except:
             continue
         for block in cat_page.select(".product-thumb"):
             a_tag = block.find("a", href=True)
             title_tag = block.select_one("h4")
             price_tag = block.select_one(".price")
             if not a_tag or not title_tag:
                 continue
             link  = a_tag["href"]
             title = title_tag.get_text(strip=True)
             price = price_tag.get_text(strip=True) if price_tag else "N/D"
             if link in seen:
                 continue
             new_products.append((title, price, link))
             seen.add(link)
 
    if not new_products:
         print("❌ Nessun nuovo prodotto, esco.")
         return

    added_titles = []              # <<< inizializza QUI
	
	# ➡️ Ora cicliamo su ciascun account MTM
    for acct in MTM_ACCOUNTS:
        user, pwd = acct["user"], acct["pwd"]
        if not user or not pwd:
            print(f"⚠️ Credenziali MTM mancanti per account {user!r}, salto.")
            continue

        print(f"🔐 Login MTM con account {user}")
        driver = setup_driver_headless()
        logged = login_mtm(driver, username=user, password=pwd)
        print(f"🔐 Login riuscito: {logged}")
        if not logged:
            driver.quit()
            continue

        for title, price, link in new_products:
            print(f"🛒 [{user}] aggiungo al carrello: {title}")
            ok = add_to_cart_and_checkout(driver, link)
            print(f"👉 [{user}] Risultato: {'OK' if ok else 'Fallito'}")
            if ok:
                added_titles.append(title)
            time.sleep(1)

        driver.quit()  # chiudi il driver per questo account

    # una sola notifica, con tutte le monete aggiunte da entrambi gli account
    if added_titles:
        cart_url = "https://www.mtm-monaco.mc/index.php?route=checkout/cart"
        msg = "<b>Flash monete Monaco!</b>\nSono state aggiunte al carrello:\n"
        for t in added_titles:
            msg += f"- {t}\n"
        msg += f"\n➡️ <a href=\"{cart_url}\">Vai al checkout MTM Monaco</a>"
        send(msg)

    # infine aggiorna il file seen_mtm.txt
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

    prods = []
    for l in links:
        p = scrape_ipzs(l)
        if p:
            prods.append(p)
        time.sleep(0.15)

    # 2️⃣ notifiche IPZS
    seen    = notify_new(prods, seen)
    alerted = notify_low(prods, alerted)
    dates   = notify_dates(prods, dates)
    flash_ipzs_cart(prods)
    sunday_ping()

    sv(SEEN_FILE, seen)
    sv(LOW_FILE, alerted)
    sj(DATE_FILE, dates)

    # 3️⃣ controllo MTM
    check_mtm_monaco()

if __name__ == "__main__":
    print("Start", datetime.now())
    main()
    print("End", datetime.now())
