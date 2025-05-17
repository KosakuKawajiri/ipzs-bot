import requests, re, os, json, time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ───────────────────────── File di stato
SEEN_FILE            = "seen.txt"
LOW_STOCK_FILE       = "low_stock_alerts.txt"
DATE_ALERTS_FILE     = "date_alerts.json"
LAST_LINK_ALERT_FILE = "last_link_alert.txt"
SPIDER_LOCK_FILE     = "last_spider.json"

# ───────────────────────── URL radice (prime 5 pagine)
CATEGORY_URLS = [
    "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=1",
    "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=2",
    "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=3",
    "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=4",
    "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=5",
]
CRITICAL_LINKS = [CATEGORY_URLS[0], "https://www.shop.ipzs.it/it/"]
DOMAIN = "www.shop.ipzs.it"

# ───────────────────────── Telegram helper
def send_telegram(text:str)->bool:
    token=os.getenv("TELEGRAM_TOKEN"); chat=os.getenv("CHAT_ID")
    if not token or not chat:
        print("TOKEN/CHAT_ID assenti."); return False
    try:
        r=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                        data={"chat_id":chat,"text":text,"parse_mode":"HTML"},timeout=10)
        r.raise_for_status(); return True
    except Exception as e:
        print("Telegram err:",e); return False

# ───────────────────────── File helpers
def load_set(fp):  return set(open(fp,encoding="utf-8").read().splitlines()) if os.path.exists(fp) else set()
def save_set(fp,s): open(fp,"w",encoding="utf-8").write("\n".join(sorted(s)))
def load_json(fp): return json.load(open(fp,encoding="utf-8")) if os.path.exists(fp) else {}
def save_json(fp,d): open(fp,"w",encoding="utf-8").write(json.dumps(d,indent=2))

# ───────────────────────── Scraping categoria
def get_product_links(cat):
    try:
        soup=BeautifulSoup(requests.get(cat,timeout=10).content,"html.parser")
        return [a["href"] for a in soup.select("a.product-item-link") if a.get("href")]
    except Exception as e:
        print("Categoria err:",e); return []

# ───────────────────────── Scraping prodotto
def scrape_product(url):
    try: soup=BeautifulSoup(requests.get(url,timeout=10).content,"html.parser")
    except Exception as e:
        print("Prodotto err:",url,e); return None
    info={"link":url}
    info["nome"]=soup.select_one("h1.page-title span.base").get_text(strip=True)
    price=soup.select_one("span.price")
    info["prezzo"]=price.get_text(strip=True) if price else "N/A"
    stock=soup.select_one("div.stock"); 
    if stock:
        cls=" ".join(stock.get("class",[]))
        info["disponibilita"]="DISPONIBILE" if "available" in cls else stock.get_text(strip=True).upper()
    else: info["disponibilita"]="N/A"
    attrs={}
    for tr in soup.select("div.product-info-main table.data tr"):
        th,td=tr.find("th"),tr.find("td")
        if th and td: attrs[th.get_text(strip=True).lower()]=td.get_text(strip=True)
    info["contingente"]=attrs.get("contingente") or attrs.get("tiratura") or attrs.get("numero pezzi","N/A")
    info["data disponibilita"]=attrs.get("data disponibilità") or attrs.get("data disponibilita","N/A")
    info["finitura"]=attrs.get("finitura","N/A")
    info["metallo"]=attrs.get("metallo","N/A")
    info["peso (gr)"]=attrs.get("peso (gr)","N/A")
    info["in vendita da"]=attrs.get("in vendita da","N/A")
    return info

# ───────────────────────── Spider leggero
def spider(start,max_urls=50,max_depth=3):
    queue=[(u,0) for u in start]; visited=set(); prods=[]
    while queue and len(visited)<max_urls:
        url,d=queue.pop(0)
        if url in visited or d>max_depth: continue
        visited.add(url)
        try: soup=BeautifulSoup(requests.get(url,timeout=10).content,"html.parser")
        except: continue
        if soup.select_one("h1.page-title span.base"):
            prods.append(url); continue
        for a in soup.find_all("a",href=True):
            h=a["href"].split("#")[0]
            if DOMAIN in h and not h.endswith((".jpg",".png",".pdf")) and h not in visited:
                queue.append((h,d+1))
    return prods

# ───────────────────────── Parsing helpers
def parse_tiratura(txt):
    nums=re.findall(r"\d+", txt.replace(".","").replace(" ",""))
    return int(nums[0]) if nums else None
FORMATS=["%d %b %Y","%d %B %Y","%d/%m/%Y","%Y-%m-%d"]
def parse_date(txt):
    for f in FORMATS:
        try: return datetime.strptime(txt.strip().lower(),f)
        except: pass

# ───────────────────────── Notifiche
def notify_new(prods,seen):
    for p in prods:
        if p["link"] in seen: continue
        if send_telegram(f"<b>Nuova moneta</b>\n{p['nome']}\n{p['prezzo']}\n{p['link']}"):
            seen.add(p["link"])
    return seen

def notify_low(prods,alerted):
    for p in prods:
        t=parse_tiratura(p["contingente"]); disp=p["disponibilita"]
        if t and t<=1500 and "NON DISPONIBILE" not in disp and p["link"] not in alerted:
            msg=(f"<b>Bassa tiratura ({t}) disponibile</b>\n{p['nome']}\n{p['link']}")
            if send_telegram(msg): alerted.add(p["link"])
    return alerted

def notify_dates(prods,alerts):
    bucket={}
    for p in prods:
        d=parse_date(p["data disponibilita"])
        if d: bucket.setdefault(d.date(),[]).append(p)
    now=datetime.now(); tomorrow=(now+timedelta(days=1)).date()
    if tomorrow in bucket and len(bucket[tomorrow])>=3 and now.hour>=8:
        if alerts.get(str(tomorrow))!=str(now.date()):
            msg=f"<b>{len(bucket[tomorrow])} monete disponibili il {tomorrow}</b>\n"
            msg+="\n".join("- "+x["nome"] for x in bucket[tomorrow])
            if send_telegram(msg): alerts[str(tomorrow)]=str(now.date())
    return alerts

def sunday_ping():
    n=datetime.now()
    if n.weekday()==6 and n.hour==13:
        send_telegram("🔁 Ping domenicale: bot attivo.")

# ───────────────────────── Spider scheduling
SPIDER_HOURS=(7,19)
def spider_allowed():
    now=datetime.now()
    if now.hour not in SPIDER_HOURS: return False
    lock=load_json(SPIDER_LOCK_FILE)
    last=lock.get("ts")
    if last and (now-datetime.fromisoformat(last)).seconds<3600: return False
    save_json(SPIDER_LOCK_FILE,{"ts":now.isoformat()}); return True

# ───────────────────────── MAIN
def main():
    seen      = load_set(SEEN_FILE)
    alerted   = load_set(LOW_STOCK_FILE)
    date_alrt = load_json(DATE_ALERTS_FILE)

    manual=set()
    for u in CATEGORY_URLS:
        manual.update(get_product_links(u))

    spider_links=set()
    if spider_allowed():
        spider_links=set(spider(CATEGORY_URLS,50,3))

    links=list(manual|spider_links)
    prods=[]; print("Tot link:",len(links))
    for l in links:
        p=scrape_product(l)
        if p: prods.append(p)
        time.sleep(0.15)

    seen      = notify_new(prods,seen)
    alerted   = notify_low(prods,alerted)
    date_alrt = notify_dates(prods,date_alrt)
    sunday_ping()

    save_set(SEEN_FILE,seen)
    save_set(LOW_STOCK_FILE,alerted)
    save_json(DATE_ALERTS_FILE,date_alrt)

if __name__=="__main__":
    print("Start",datetime.now()); main(); print("Done",datetime.now())
