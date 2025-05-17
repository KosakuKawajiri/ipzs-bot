import requests, re, os, json, time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# === Costanti / file di stato =================================================
SEEN_FILE              = "seen.txt"
LOW_STOCK_ALERT_FILE   = "low_stock_alerts.txt"
DATE_ALERTS_FILE       = "date_alerts.json"
LAST_LINK_ALERT_FILE   = "last_link_alert.txt"

CATEGORY_URLS = [
    "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/"
]

CRITICAL_LINKS = [
    CATEGORY_URLS[0],
    "https://www.shop.ipzs.it/it/",
]

# === Telegram helper ==========================================================
def send_telegram_message(text:str)->bool:
    token  = os.getenv("TELEGRAM_BOT_TOKEN")
    chatid = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chatid:
        print("⚠️  TOKEN/CHAT_ID non configurati: messaggio non inviato")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id":chatid,"text":text,"parse_mode":"HTML"}, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        print("Errore invio Telegram:", e)
        return False

# === Utility file -------------------------------------------------------------
def load_set(path):  return set(open(path, encoding="utf-8").read().splitlines()) if os.path.exists(path) else set()
def save_set(path, data:set): open(path,"w",encoding="utf-8").write("\n".join(sorted(data)))
def load_json(path): return json.load(open(path,encoding="utf-8")) if os.path.exists(path) else {}
def save_json(path,d): open(path,"w",encoding="utf-8").write(json.dumps(d,indent=2))

# === Scraping categoria → link monete -----------------------------------------
def get_product_links(cat_url):
    try:
        soup = BeautifulSoup(requests.get(cat_url,timeout=10).content,"html.parser")
        return [a["href"] for a in soup.select("a.product-item-link") if a.get("href")]
    except Exception as e:
        print("Errore categoria:", e); return []

# === Scraping pagina prodotto -------------------------------------------------
def scrape_product(url:str)->dict|None:
    try:
        soup = BeautifulSoup(requests.get(url,timeout=10).content,"html.parser")
    except Exception as e:
        print("Errore prodotto:", url, e); return None

    info = {"link":url}

    # Nome
    h = soup.select_one("h1.page-title span.base")
    info["nome"] = h.get_text(strip=True) if h else "N/A"

    # Prezzo
    p = soup.select_one("span.price")
    info["prezzo"] = p.get_text(strip=True) if p else "N/A"

    # Disponibilità
    stock = soup.select_one("div.stock")
    if stock:
        cls = " ".join(stock.get("class",[]))
        info["disponibilita"] = "DISPONIBILE" if "available" in cls else stock.get_text(strip=True).upper()
    else:
        info["disponibilita"] = "N/A"

    # Tabella attributi
    attrs={}
    for tr in soup.select("div.product-info-main table.data tr"):
        th,td = tr.find("th"), tr.find("td")
        if th and td:
            attrs[th.get_text(strip=True).lower()] = td.get_text(strip=True)

    info["contingente"]        = attrs.get("contingente") or attrs.get("tiratura") or attrs.get("numero pezzi","N/A")
    info["data disponibilita"] = attrs.get("data disponibilità") or attrs.get("data disponibilita","N/A")
    info["finitura"]           = attrs.get("finitura","N/A")
    info["metallo"]            = attrs.get("metallo","N/A")
    info["peso (gr)"]          = attrs.get("peso (gr)","N/A")
    info["in vendita da"]      = attrs.get("in vendita da","N/A")

    return info

# === Parsing numeri tiratura (robusto) ----------------------------------------
def parse_tiratura(text:str)->int|None:
    nums = re.findall(r"\d+", text.replace(".", "").replace(" ","").replace(" ", ""))
    if not nums: return None
    try: return int(nums[0])
    except: return None

# === Parsing date disponibilità (multi-formato) -------------------------------
DATE_FORMATS = ["%d %b %Y", "%d %B %Y", "%d/%m/%Y", "%Y-%m-%d"]

def parse_date(text:str)->datetime|None:
    text=text.strip().lower()
    for fmt in DATE_FORMATS:
        try: return datetime.strptime(text, fmt)
        except: continue
    return None

# === Notifiche ----------------------------------------------------------------
def notify_new(products, seen:set):
    for p in products:
        if p["link"] in seen: continue
        msg = (f"<b>Nuova moneta disponibile</b>\n"
               f"Nome: {p['nome']}\nPrezzo: {p['prezzo']}\n"
               f"Disponibilità: {p['disponibilita']}\n"
               f"Tiratura/Contingente: {p['contingente']}\n{p['link']}")
        if send_telegram_message(msg): seen.add(p["link"])
    return seen

def notify_low_tiratura(products, alerted:set):
    for p in products:
        t = parse_tiratura(p["contingente"])
        if t is None or t>1500: continue
        if 'NON DISPONIBILE' in p['disponibilita']: continue
        if p["link"] in alerted: continue
        msg=(f"<b>Moneta a bassa tiratura rilevata</b>\n"
             f"Nome: {p['nome']}\nPrezzo: {p['prezzo']}\nContingente: {p['contingente']}\n"
             f"Disponibilità: {p['disponibilita']}\nIn vendita da: {p['in vendita da']}\n"
             f"Data disponibilità: {p['data disponibilita']}\nFinitura: {p['finitura']}\n"
             f"Metallo: {p['metallo']}\nPeso: {p['peso (gr)']}\n{p['link']}")
        if send_telegram_message(msg):
            alerted.add(p["link"])
    return alerted

def notify_date_cluster(products, date_alerts:dict):
    # raggruppa per date
    bucket={}
    for p in products:
        d=parse_date(p["data disponibilita"])
        if d: bucket.setdefault(d.date(), []).append(p)

    now=datetime.now()
    tomorrow=(now+timedelta(days=1)).date()

    if tomorrow in bucket and len(bucket[tomorrow])>=3:
        if date_alerts.get(str(tomorrow))==str(now.date()):
            return date_alerts  # già notificato oggi
        if now.hour!=8:         # invia SOLO alle 08:00
            return date_alerts
        msg=f"<b>Almeno {len(bucket[tomorrow])} monete disponibili il {tomorrow}</b>\n"
        for p in bucket[tomorrow]:
            msg+=f"- {p['nome']} ({p['link']})\n"
        if send_telegram_message(msg):
            date_alerts[str(tomorrow)]=str(now.date())
    return date_alerts

def check_links_weekly():
    last=load_json(LAST_LINK_ALERT_FILE).get("ts")
    now=datetime.now()
    if last and (now-datetime.fromisoformat(last)).days<7: return
    broken=[]
    for url in CRITICAL_LINKS:
        try:
            if requests.head(url,timeout=5).status_code!=200: broken.append(url)
        except: broken.append(url)
    if broken and send_telegram_message("⚠️ Link critici non raggiungibili:\n"+"".join(f"- {u}\n" for u in broken)):
        save_json(LAST_LINK_ALERT_FILE, {"ts":now.isoformat()})

def sunday_ping():
    n=datetime.now()
    if n.weekday()==6 and n.hour==13:
        send_telegram_message("🔁 Routine domenicale: bot attivo.")

# === MAIN =====================================================================
def main():
    print("Start:", datetime.now())

    seen           = load_set(SEEN_FILE)
    low_alerted    = load_set(LOW_STOCK_ALERT_FILE)
    date_alerts    = load_json(DATE_ALERTS_FILE)

    all_products=[]
    for cat in CATEGORY_URLS:
        for link in get_product_links(cat):
            p=scrape_product(link)
            if p: all_products.append(p)
            time.sleep(0.2)

    seen        = notify_new(all_products, seen)
    low_alerted = notify_low_tiratura(all_products, low_alerted)
    date_alerts = notify_date_cluster(all_products, date_alerts)

    save_set(SEEN_FILE, seen)
    save_set(LOW_STOCK_ALERT_FILE, low_alerted)
    save_json(DATE_ALERTS_FILE, date_alerts)

    check_links_weekly()
    sunday_ping()
    print("Done")

if __name__=="__main__":
    main()
