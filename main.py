import requests, re, os, json, time
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime, timedelta

# ============ FILE di STATO ============ #
SEEN_FILE              = "seen.txt"
LOW_STOCK_ALERT_FILE   = "low_stock_alerts.txt"
DATE_ALERTS_FILE       = "date_alerts.json"
LAST_LINK_ALERT_FILE   = "last_link_alert.txt"

# ============ URL di PARTENZA (5 pagine) ============ #
CATEGORY_URLS = [
    "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=1",
    "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=2",
    "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=3",
    "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=4",
    "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=5",
]

CRITICAL_LINKS = [
    CATEGORY_URLS[0],
    "https://www.shop.ipzs.it/it/",
]

DOMAIN = "www.shop.ipzs.it"

# ========= Telegram helper ============= #
def send_telegram_message(text:str)->bool:
    token  = os.getenv("TELEGRAM_BOT_TOKEN")
    chatid = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chatid:
        print("⚠️  TOKEN/CHAT_ID mancanti")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id":chatid,"text":text,"parse_mode":"HTML"}, timeout=10)
        r.raise_for_status(); return True
    except Exception as e:
        print("Telegram error:", e); return False

# ========= Utils file ================== #
def load_set(fp):  return set(open(fp,encoding="utf-8").read().splitlines()) if os.path.exists(fp) else set()
def save_set(fp,s): open(fp,"w",encoding="utf-8").write("\n".join(sorted(s)))
def load_json(fp): return json.load(open(fp,encoding="utf-8")) if os.path.exists(fp) else {}
def save_json(fp,d): open(fp,"w",encoding="utf-8").write(json.dumps(d,indent=2))

# ========= Parsing helper ============== #
def parse_tiratura(txt:str)->int|None:
    nums=re.findall(r"\d+", txt.replace(".", "").replace(" ", ""))
    return int(nums[0]) if nums else None

DATE_FMT = ["%d %b %Y","%d %B %Y","%d/%m/%Y","%Y-%m-%d"]
def parse_date(txt:str):
    t=txt.strip().lower()
    for f in DATE_FMT:
        try: return datetime.strptime(t,f)
        except: continue
    return None

# ========= Scraping prodotto =========== #
def scrape_product(url:str)->dict|None:
    try:
        soup=BeautifulSoup(requests.get(url,timeout=10).content,"html.parser")
    except Exception as e:
        print("Prodotto err:",url,e); return None
    info={"link":url}
    info["nome"]=soup.select_one("h1.page-title span.base").get_text(strip=True)
    price=soup.select_one("span.price")
    info["prezzo"]=price.get_text(strip=True) if price else "N/A"
    stock=soup.select_one("div.stock")
    if stock:
        cls=" ".join(stock.get("class",[]))
        info["disponibilita"]="DISPONIBILE" if "available" in cls else stock.get_text(strip=True).upper()
    else: info["disponibilita"]="N/A"
    attrs={}
    for tr in soup.select("div.product-info-main table.data tr"):
        th,td=tr.find("th"),tr.find("td")
        if th and td:
            attrs[th.get_text(strip=True).lower()]=td.get_text(strip=True)
    info["contingente"]=attrs.get("contingente") or attrs.get("tiratura") or attrs.get("numero pezzi","N/A")
    info["data disponibilita"]=attrs.get("data disponibilità") or attrs.get("data disponibilita","N/A")
    info["finitura"]=attrs.get("finitura","N/A")
    info["metallo"]=attrs.get("metallo","N/A")
    info["peso (gr)"]=attrs.get("peso (gr)","N/A")
    info["in vendita da"]=attrs.get("in vendita da","N/A")
    return info

# ========= Spider leggero =============== #
def spider(start_urls:list, max_urls:int=50, max_depth:int=3)->list[str]:
    to_visit=[(u,0) for u in start_urls]
    visited=set()
    product_links=[]
    while to_visit and len(visited)<max_urls:
        url,depth=to_visit.pop(0)
        if url in visited or depth>max_depth: continue
        visited.add(url)
        try:
            html=requests.get(url,timeout=10).content
        except: continue
        soup=BeautifulSoup(html,"html.parser")
        # se è una scheda prodotto => salva e salta children
        if soup.select_one("h1.page-title span.base"):
            product_links.append(url); continue
        # altrimenti scansiona link interni
        for a in soup.find_all("a",href=True):
            href=a["href"].split("#")[0]
            if DOMAIN not in href: continue
            if href.endswith((".jpg",".png",".pdf")): continue
            if href in visited: continue
            to_visit.append((href,depth+1))
    return product_links

# ========= Notifiche (stesse funzioni di prima, invariato) =================== #
def notify_new(products, seen:set):
    for p in products:
        if p["link"] in seen: continue
        msg=(f"<b>Nuova moneta</b>\n{p['nome']}\nPrezzo: {p['prezzo']}\n{p['link']}")
        if send_telegram_message(msg): seen.add(p["link"])
    return seen

def notify_low(products, alerted:set):
    for p in products:
        t=parse_tiratura(p["contingente"] or "")
        if t and t<=1500 and 'NON DISPONIBILE' not in p["disponibilita"] and p["link"] not in alerted:
            msg=(f"<b>Bassa tiratura ({t}) disponibile!</b>\n{p['nome']}\n{p['link']}")
            if send_telegram_message(msg): alerted.add(p["link"])
    return alerted

def notify_dates(products, date_alerts:dict):
    bucket={}
    for p in products:
        d=parse_date(p["data disponibilita"])
        if d: bucket.setdefault(d.date(), []).append(p)
    now=datetime.now(); tomorrow=(now+timedelta(days=1)).date()
    if tomorrow in bucket and len(bucket[tomorrow])>=3 and now.hour==8:
        if date_alerts.get(str(tomorrow))!=str(now.date()):
            msg=f"<b>{len(bucket[tomorrow])} monete usciranno il {tomorrow}</b>\n"
            msg+="\n".join(f"- {x['nome']}" for x in bucket[tomorrow])
            if send_telegram_message(msg): date_alerts[str(tomorrow)]=str(now.date())
    return date_alerts

def sunday_ping():
    n=datetime.now()
    if n.weekday()==6 and n.hour==13:
        send_telegram_message("🔁 Bot IPZS operativo (ping domenicale).")

# ========= MAIN ==============================================================
def main():
    seen, alerted = load_set(SEEN_FILE), load_set(LOW_STOCK_ALERT_FILE)
    date_alerts   = load_json(DATE_ALERTS_FILE)

    # 1️⃣ raccolta link via lista manuale + spider leggero
    manual_links=set()
    for u in CATEGORY_URLS:
        manual_links.update(get_product_links(u))
    spider_links=set(spider(CATEGORY_URLS, max_urls=50, max_depth=3))
    all_links=list(manual_links|spider_links)

    # 2️⃣ scraping dettagli
    products=[]; print(f"Raccolgo {len(all_links)} link prodotto…")
    for link in all_links:
        p=scrape_product(link)
        if p: products.append(p)
        time.sleep(0.15)  # throttling

    # 3️⃣ notifiche
    seen      = notify_new(products, seen)
    alerted   = notify_low(products, alerted)
    date_alerts = notify_dates(products, date_alerts)
    sunday_ping()

    # 4️⃣ salva stati
    save_set(SEEN_FILE, seen)
    save_set(LOW_STOCK_ALERT_FILE, alerted)
    save_json(DATE_ALERTS_FILE, date_alerts)
    print("Done:", datetime.now())

if __name__=="__main__":
    main()
