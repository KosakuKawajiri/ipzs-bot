from mtm_flash import setup_driver_headless, login_mtm, add_to_cart_and_checkout
import requests, re, os, json, time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

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
def notify_new(prods, seen):
    for p in prods:
        if p["link"] in seen:
            continue
        text = (
            f"<b>Nuova moneta</b>\n"
            f"{p['nome']}\n"
            f"{p['prezzo']}\n"
            f"{p['link']}"
        )
        if send(text):
            seen.add(p["link"])
    return seen

def notify_low(prods, alerted):
    for p in prods:
        t = parse_tiratura(p["contingente"])
        disp = p["disponibilita"]
        if t and t <= 1500 and "NON DISPONIBILE" not in disp and p["link"] not in alerted:
            msg = (
                f"<b>Moneta a bassa tiratura</b>\n"
                f"- NOME MONETA: {p['nome']}\n"
                f"- PREZZO: {p['prezzo']}\n"
                f"- CONTINGENTE: {p['contingente']}\n"
                f"- DISPONIBILITA: {p['disponibilita']}\n"
                f"- IN VENDITA DA: {p['in vendita da']}\n"
                f"- DATA DISPONIBILITA: {p['data disponibilita']}\n"
                f"- FINITURA: {p['finitura']}\n"
                f"- METALLO: {p['metallo']}\n"
                f"- PESO (gr): {p['peso (gr)']}\n"
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

    if tomorrow in bucket and len(bucket[tomorrow]) >= 3 and now.hour >= 8:
        key = str(tomorrow)
        if alerts.get(key) != str(now.date()):
            msg = f"<b>{len(bucket[tomorrow])} monete disponibili il {tomorrow}</b>\n"
            msg += "\n".join(f"- {x['nome']}" for x in bucket[tomorrow])
            if send(msg):
                alerts[key] = str(now.date())
    return alerts

def sunday_ping():
    now = datetime.now()
    # Domenica alle 12:00/13:00 locali corrisponde a 11:00 UTC
    if now.weekday() == 6 and now.hour == 11:
        send("🔁 Check domenicale: bot attivo")

# ──────────────── Spider IPZS
SPIDER_HOURS = (7, 19)
def spider_allowed():
    now = datetime.now()
    if now.hour not in SPIDER_HOURS:
        return False
    lock = lj(SPIDER_LOCK)
    last = lock.get("ts")
    if last and (now - datetime.fromisoformat(last)).seconds < 3600:
        return False
    sj(SPIDER_LOCK, {"ts": now.isoformat()})
    return True

def spider(start, max_urls=50, max_depth=3):
    queue = [(u, 0) for u in start]
    visited = set()
    prods = []

    while queue and len(visited) < max_urls:
        url, depth = queue.pop(0)
        if url in visited or depth > max_depth:
            continue
        visited.add(url)

        try:
            soup = BeautifulSoup(requests.get(url, timeout=10).content, "html.parser")
        except:
            continue

        if soup.select_one("h1.page-title span.base"):
            prods.append(url)
            continue

        for a in soup.find_all("a", href=True):
            href = a["href"].split("#")[0]
            if DOMAIN in href and not href.endswith((".jpg", ".png", ".pdf")) and href not in visited:
                queue.append((href, depth + 1))

    return prods

# ──────────────── MTM Monaco
MTM_ROOT    = "https://www.mtm-monaco.mc/index.php?route=common/home"
MTM_DOMAIN  = "www.mtm-monaco.mc"

def check_mtm_monaco():
    """
    Trova nuove monete MTM e, se ne esistono, apre un driver headless,
    esegue il login e aggiunge tutte le nuove monete al carrello in una sola sessione.
    Alla fine invia un singolo messaggio Telegram con la lista delle monete
    aggiunte e il link al carrello.
    """

    # Carica le righe di seen_mtm.txt (contengono solo l'URL)
    seen = set()
    if os.path.exists(MTM_SEEN_FILE):
        with open(MTM_SEEN_FILE, "r", encoding="utf-8") as f:
            for line in f:
                url = line.strip()
                if url:
                    seen.add(url)

    new_products = []  # lista di (title, price, link) per le nuove monete
    try:
        homepage = BeautifulSoup(requests.get(MTM_ROOT, timeout=10).content, "html.parser")
    except:
        return

    # 1️⃣ Trova tutti i link di categoria (product/category) nella homepage
    cat_links = [a["href"] for a in homepage.find_all("a", href=True) if "product/category" in a["href"]]

    # 2️⃣ Per ogni categoria, estrai i blocchi .product-thumb
    for cat_url in cat_links:
        try:
            cat_page = BeautifulSoup(requests.get(cat_url, timeout=10).content, "html.parser")
        except:
            continue

        for block in cat_page.select(".product-thumb"):
            a_tag = block.find("a", href=True)
            name_tag = block.find("h4")
            if not a_tag or not name_tag:
                continue

            link = a_tag["href"]
            title = name_tag.get_text(strip=True)

            # Filtra prodotti non-numismatici (es. accessori)
            if "accessori" in title.lower():
                continue

            if link in seen:
                continue  # già notificato in precedenza

            # Estrai prezzo
            price_tag = block.select_one(".price")
            price = price_tag.get_text(strip=True) if price_tag else "Prezzo N/D"

            new_products.append((title, price, link))
            seen.add(link)  # segno come “visto” immediatamente

    # 3️⃣ Se non ci sono nuove monete, aggiorno seen_mtm.txt e esco
    if not new_products:
        with open(MTM_SEEN_FILE, "w", encoding="utf-8") as f:
            for url in seen:
                f.write(url + "\n")
        return

    # 4️⃣ Preparo il driver headless e faccio il login
    driver = setup_driver_headless()
    logged = login_mtm(driver)
    if not logged:
        driver.quit()
        return  # non riesco a fare login, skip

    # 5️⃣ Aggiungo ogni nuovo prodotto al carrello
    added_titles = []
    for title, price, link in new_products:
        ok = add_to_cart_and_checkout(driver, link)
        if ok:
            added_titles.append(title)
        time.sleep(1)  # piccolo delay per non sovraccaricare

    # 6️⃣ Invio un unico messaggio con l’elenco delle monete aggiunte e il link al carrello
    if added_titles:
        cart_url = "https://www.mtm-monaco.mc/index.php?route=checkout/cart"
        msg = "<b>Flash-Compra MTM Monaco</b>\n"
        msg += "Sono state aggiunte le seguenti monete nel carrello:\n"
        for t in added_titles:
            msg += f"- {t}\n"
        msg += f"\n➡️ <a href=\"{cart_url}\">Vai al carrello</a>"
        send(msg)

    # 7️⃣ Chiudo il driver
    driver.quit()

    # 8️⃣ Salvo il nuovo seen_mtm.txt (solo gli URL)
    with open(MTM_SEEN_FILE, "w", encoding="utf-8") as f:
        for url in seen:
            f.write(url + "\n")

# ──────────────── MAIN
def main():
    seen      = ld(SEEN_FILE)
    alerted   = ld(LOW_FILE)
    dates     = lj(DATE_FILE)

    # 1️⃣ Raccolta link IPZS (manual + spider)
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

    # 2️⃣ Notifiche IPZS
    seen    = notify_new(prods, seen)
    alerted = notify_low(prods, alerted)
    dates   = notify_dates(prods, dates)
    sunday_ping()

    # 3️⃣ Salva stati IPZS
    sv(SEEN_FILE, seen)
    sv(LOW_FILE, alerted)
    sj(DATE_FILE, dates)

    # 4️⃣ Controlla MTM Monaco
    check_mtm_monaco()

if __name__ == "__main__":
    print("Start", datetime.now())
    main()
    print("End", datetime.now())
