import requests, re, os, json, time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ────────── File di stato
SEEN_FILE  = "seen.txt"
LOW_FILE   = "low_mintage_alerts.txt"
DATE_FILE  = "date_alerts.json"
SPIDER_LCK = "last_spider.json"

# ────────── URL di partenza
CATEGORY_URLS = [f"https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p={i}" for i in range(1,6)]
DOMAIN = "www.shop.ipzs.it"

# ────────── Telegram
def send(text:str)->bool:
    token=os.getenv("TELEGRAM_TOKEN"); chat=os.getenv("CHAT_ID")
    if not token or not chat: return False
    try:
        r=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                        data={"chat_id":chat,"text":text,"parse_mode":"HTML"},timeout=10)
        r.raise_for_status(); return True
    except: return False

# ────────── Helpers file
ld=lambda fp: set(open(fp).read().splitlines()) if os.path.exists(fp) else set()
sv=lambda fp,s: open(fp,"w").write("\n".join(sorted(s)))
sj=lambda fp,d: open(fp,"w").write(json.dumps(d,indent=2))
def lj(fp):
    if not os.path.exists(fp): 
        return {}
    try:
        return json.load(open(fp, encoding="utf-8"))
    except json.JSONDecodeError:
        # file vuoto o corrotto → ripartiamo puliti
        return {}

# ────────── Scraping categoria
def get_links(cat):
    soup=BeautifulSoup(requests.get(cat,timeout=10).content,"html.parser")
    return [a["href"] for a in soup.select("a.product-item-link") if a.get("href")]

# ────────── Scraping prodotto
def scrape(url):
    soup=BeautifulSoup(requests.get(url,timeout=10).content,"html.parser")
    info={"link":url}
    info["nome"]=soup.select_one("h1.page-title span.base").get_text(strip=True)
    pr=soup.select_one("span.price")
    info["prezzo"]=pr.get_text(strip=True) if pr else "N/A"
    stock=soup.select_one("div.stock")
    if stock:
        raw=stock.get_text(strip=True).upper()
        info["disponibilita"]="NON DISPONIBILE" if "NON DISPONIBILE" in raw else "DISPONIBILE"
    else: info["disponibilita"]="N/A"
    attrs={}; 
    for tr in soup.select("div.product-info-main table.data tr"):
        th,td=tr.find("th"),tr.find("td")
        if th and td: attrs[th.text.lower().strip()]=td.text.strip()
    info["contingente"]=attrs.get("contingente") or attrs.get("tiratura") or attrs.get("numero pezzi","N/A")
    info["data disponibilita"]=attrs.get("data disponibilità") or attrs.get("data disponibilita","N/A")
    info["finitura"]=attrs.get("finitura","N/A")
    info["metallo"]=attrs.get("metallo","N/A")
    info["peso (gr)"]=attrs.get("peso (gr)","N/A")
    info["in vendita da"]=attrs.get("in vendita da","N/A")
    return info

# ────────── Parsing
def tiratura(txt): 
    nums=re.findall(r"\d+",txt.replace(".","").replace(" ","")); 
    return int(nums[0]) if nums else None
FORMATS=["%d %b %Y","%d %B %Y","%d/%m/%Y","%Y-%m-%d"]
def pdate(t):
    for f in FORMATS:
        try: return datetime.strptime(t.strip().lower(),f)
        except: pass

# ────────── Notifiche
def alert_low(p):
    msg=(f"<b>MONETA A BASSA TIRATURA!</b>\n"
         f"- NOME MONETA: {p['nome']}\n"
         f"- PREZZO: {p['prezzo']}\n"
         f"- CONTINGENTE: {p['contingente']}\n"
         f"- DISPONIBILITA: {p['disponibilita']}\n"
         f"- IN VENDITA DA: {p['in vendita da']}\n"
         f"- DATA DISPONIBILITA: {p['data disponibilita']}\n"
         f"- FINITURA: {p['finitura']}\n"
         f"- METALLO: {p['metallo']}\n"
         f"- PESO (gr): {p['peso (gr)']}\n"
         f"- LINK: {p['link']}")
    send(msg)

# ────────── Spider medio (slot 6-18)
SPIDER_HOURS=(6,18)
def spider(start,max_urls=100,max_depth=4):
    from collections import deque
    q=deque([(u,0) for u in start]); seen=set(); prods=[]
    while q and len(seen)<max_urls:
        url,d=q.popleft()
        if url in seen or d>max_depth: continue
        seen.add(url)
        soup=BeautifulSoup(requests.get(url,timeout=10).content,"html.parser")
        if soup.select_one("h1.page-title span.base"): prods.append(url); continue
        for a in soup.find_all("a",href=True):
            h=a["href"].split("#")[0]
            if DOMAIN in h and not h.endswith((".jpg",".png",".pdf")):
                q.append((h,d+1))
    return prods

def spider_ok():
    now=datetime.now()
    if now.hour not in SPIDER_HOURS: return False
    lock=lj(SPIDER_LCK)
    last=lock.get("ts")
    if last and (now-datetime.fromisoformat(last)).seconds<3600: return False
    sj(SPIDER_LCK,{"ts":now.isoformat()}); return True

# ────────── MAIN
def main():
    seen=ld(SEEN_FILE); alerted=ld(LOW_FILE); dates=lj(DATE_FILE)

    links=set()
    for u in CATEGORY_URLS: links.update(get_links(u))
    if spider_ok(): links.update(spider(CATEGORY_URLS))

    prods=[]; 
    for l in links:
        p=scrape(l); 
        if p: prods.append(p)
        time.sleep(0.15)

    # Nuove monete
    for p in prods:
        if p["link"] not in seen:
            send(f"<b>Nuova moneta</b>\n{p['nome']}\n{p['prezzo']}\n{p['link']}")
            seen.add(p["link"])

    # Bassa tiratura
    for p in prods:
        t=tiratura(p["contingente"])
        if t and t<=1500 and "NON DISPONIBILE" not in p["disponibilita"] and p["link"] not in alerted:
            alert_low(p); alerted.add(p["link"])

    # Data disponibilità (giorno-prima)
    bucket={}
    for p in prods:
        d=pdate(p["data disponibilita"])
        if d: bucket.setdefault(d.date(),[]).append(p)
    now=datetime.now(); tomorrow=(now+timedelta(days=1)).date()
    if tomorrow in bucket and len(bucket[tomorrow])>=3 and now.hour>=6:
        if dates.get(str(tomorrow))!=str(now.date()):
            msg=f"<b>{len(bucket[tomorrow])} monete disponibili il {tomorrow}</b>\n"
            msg+="\n".join("- "+x["nome"] for x in bucket[tomorrow])
            send(msg); dates[str(tomorrow)]=str(now.date())

    # ping domenicale
    if now.weekday()==6 and now.hour==11:
        send("🔁 Bot IPZS attivo (controllo domenicale)")

    sv(SEEN_FILE,seen); sv(LOW_FILE,alerted); sj(DATE_FILE,dates)

if __name__=="__main__":
    print("Start",datetime.now()); main(); print("End",datetime.now())
