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
"[https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=1](https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=1)",
"[https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=2](https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=2)",
"[https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=3](https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=3)",
"[https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=4](https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=4)",
"[https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=5](https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=5)",
]
DOMAIN = "[www.shop.ipzs.it](http://www.shop.ipzs.it)"

# ──────────────── Telegram

send = lambda msg: requests.post(
f"[https://api.telegram.org/bot{os.getenv('TELEGRAM_TOKEN')}/sendMessage](https://api.telegram.org/bot{os.getenv%28'TELEGRAM_TOKEN'%29}/sendMessage)",
data={"chat_id": os.getenv("CHAT_ID"), "text": msg, "parse_mode": "HTML"})

# ──────────────── Helpers

ld = lambda fp: set(open(fp,encoding="utf-8").read().splitlines()) if os.path.exists(fp) else set()
sv = lambda fp,s: open(fp,"w",encoding="utf-8").write("\n".join(sorted(s)))
lj = lambda fp: json.load(open(fp)) if os.path.exists(fp) else {}
sj = lambda fp,d: open(fp,"w").write(json.dumps(d,indent=2))

# ──────────────── IPZS – parsing link

get_links = lambda url: [a["href"] for a in BeautifulSoup(requests.get(url).content,"html.parser").select("a.product-item-link") if a.get("href")]

def scrape_ipzs(url):
try: soup = BeautifulSoup(requests.get(url).content,"html.parser")
except: return None
info = {"link": url}
info["nome"] = soup.select_one("h1.page-title span.base").get_text(strip=True)
pr = soup.select_one("span.price"); info["prezzo"] = pr.get_text(strip=True) if pr else "N/A"
stock = soup.select_one("div.stock"); txt = stock.get_text(strip=True).upper() if stock else ""
info["disponibilita"] = "NON DISPONIBILE" if "NON DISPONIBILE" in txt else ("DISPONIBILE" if "DISPONIBILE" in txt else txt or "N/A")
attr = {}
for tr in soup.select("div.product-info-main table.data tr"):
th, td = tr.find("th"), tr.find("td")
if th and td: attr[th.get_text(strip=True).lower()] = td.get_text(strip=True)
info["contingente"] = attr.get("contingente") or attr.get("tiratura") or attr.get("numero pezzi","N/A")
info["data disponibilita"] = attr.get("data disponibilità") or attr.get("data disponibilita","N/A")
info["finitura"] = attr.get("finitura","N/A")
info["metallo"] = attr.get("metallo","N/A")
info["peso (gr)"] = attr.get("peso (gr)","N/A")
info["in vendita da"] = attr.get("in vendita da","N/A")
return info

def parse_tiratura(txt):
nums = re.findall(r"\d+", txt.replace(".","").replace(" ",""))
return int(nums[0]) if nums else None

def parse_date(txt):
for fmt in ["%d %b %Y","%d %B %Y","%d/%m/%Y","%Y-%m-%d"]:
try: return datetime.strptime(txt.strip(), fmt)
except: pass

# ──────────────── Notifiche IPZS

def notify_new(prods,seen):
for p in prods:
if p["link"] in seen: continue
if send(f"<b>Nuova moneta</b>\n{p['nome']}\n{p['prezzo']}\n{p['link']}").status_code == 200:
seen.add(p["link"])
return seen

def notify_low(prods,alerted):
for p in prods:
t=parse_tiratura(p["contingente"]); d=p["disponibilita"]
if t and t<=1500 and "NON DISPONIBILE" not in d and p["link"] not in alerted:
msg=(f"<b>Bassa tiratura disponibile</b>\n<b>Nome:</b> {p['nome']}\n<b>Prezzo:</b> {p['prezzo']}\n"
f"<b>Contingente:</b> {p['contingente']}\n<b>Disponibilità:</b> {p['disponibilita']}\n"
f"<b>In vendita da:</b> {p['in vendita da']}\n<b>Data disponibilità:</b> {p['data disponibilita']}\n"
f"<b>Finitura:</b> {p['finitura']}\n<b>Metallo:</b> {p['metallo']}\n<b>Peso:</b> {p['peso (gr)']}\n"
f"<b>Link:</b> {p['link']}")
if send(msg).status_code == 200: alerted.add(p["link"])
return alerted

def notify_dates(prods,alerts):
bucket={}
for p in prods:
d=parse_date(p["data disponibilita"])
if d: bucket.setdefault(d.date(),[]).append(p)
now=datetime.now(); tmr=(now+timedelta(days=1)).date()
if tmr in bucket and len(bucket[tmr])>=3 and now\.hour>=8:
if alerts.get(str(tmr))!=str(now\.date()):
msg=f"<b>{len(bucket[tmr])} monete disponibili il {tmr}</b>\n"
msg+="\n".join("- "+x["nome"] for x in bucket[tmr])
if send(msg).status_code==200: alerts[str(tmr)]=str(now\.date())
return alerts

def sunday_ping():
n=datetime.now()
if n.weekday()==6 and n.hour==13:
send("🔁 Ping domenicale: bot attivo.")

# ──────────────── Spider lock

SPIDER_HOURS=(7,19)
def spider_allowed():
now=datetime.now()
if now\.hour not in SPIDER_HOURS: return False
lock=lj(SPIDER_LOCK)
last=lock.get("ts")
if last and (now-datetime.fromisoformat(last)).seconds<3600: return False
sj(SPIDER_LOCK,{"ts"\:now\.isoformat()}); return True

def spider(start,max_urls=50,max_depth=3):
queue=[(u,0) for u in start]; visited=set(); prods=[]
while queue and len(visited)\<max_urls:
url,d=queue.pop(0)
if url in visited or d>max_depth: continue
visited.add(url)
try: soup=BeautifulSoup(requests.get(url).content,"html.parser")
except: continue
if soup.select_one("h1.page-title span.base"):
prods.append(url); continue
for a in soup.find_all("a",href=True):
h=a["href"].split("#")[0]
if DOMAIN in h and not h.endswith(('.jpg','.png','.pdf')) and h not in visited:
queue.append((h,d+1))
return prods

# ──────────────── MTM Monaco

MTM_ROOT="[https://www.mtm-monaco.mc/index.php?route=common/home](https://www.mtm-monaco.mc/index.php?route=common/home)"
MTM_DOMAIN="[www.mtm-monaco.mc](http://www.mtm-monaco.mc)"

def check_mtm_monaco():
seen=ld(MTM_SEEN_FILE); new_seen=set()
try: soup=BeautifulSoup(requests.get(MTM_ROOT).content,"html.parser")
except: return
links=[a["href"] for a in soup.find_all("a",href=True) if "product/category" in a["href"]]
for url in links:
try: cat=BeautifulSoup(requests.get(url).content,"html.parser")
except: continue
for block in cat.select(".product-thumb"):
a=block.find("a",href=True); name=block.find("h4")
if not a or not name: continue
link=a["href"]; title=name.get_text(strip=True)
if link in seen: continue
if "accessori" in title.lower(): continue
price=block.select_one(".price"); p=price.get_text(strip=True) if price else "Prezzo N/D"
msg=f"💎 <b>Moneta MTM disponibile</b>\n{title}\n{p}\n{link}"
if send(msg).status_code==200: new_seen.add(link)
\# Salva solo quelli visti ora (lock antiflood 1h)
if new_seen:
now=datetime.now()
new_seen={f"{now\.isoformat()}|{url}" for url in new_seen}
old_seen={x for x in seen if (now-datetime.fromisoformat(x.split("|")[0])).seconds<3600}
sv(MTM_SEEN_FILE,old_seen|new_seen)

# ──────────────── MAIN

def main():
print("Start",datetime.now())
seen=ld(SEEN_FILE); alerted=ld(LOW_FILE); dates=lj(DATE_FILE)
links=set()
for u in CATEGORY_URLS:
links.update(get_links(u))
if spider_allowed():
links.update(spider(CATEGORY_URLS,50,3))
prods=[]
for l in links:
p=scrape_ipzs(l)
if p: prods.append(p)
time.sleep(0.15)
seen=notify_new(prods,seen)
alerted=notify_low(prods,alerted)
dates=notify_dates(prods,dates)
sunday_ping()
sv(SEEN_FILE,seen); sv(LOW_FILE,alerted); sj(DATE_FILE,dates)
check_mtm_monaco()
print("End",datetime.now())

if **name**=="**main**":
main()
