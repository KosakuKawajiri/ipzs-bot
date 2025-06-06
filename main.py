import requests, re, os, json, time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ──────────────── File di stato

SEEN\_FILE       = "seen.txt"
LOW\_FILE        = "low\_mintage\_alerts.txt"
DATE\_FILE       = "date\_alerts.json"
SPIDER\_LOCK     = "last\_spider.json"
MTM\_SEEN\_FILE   = "seen\_mtm.txt"

# ──────────────── IPZS Config

CATEGORY\_URLS = \[
"[https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=1](https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=1)",
"[https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=2](https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=2)",
"[https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=3](https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=3)",
"[https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=4](https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=4)",
"[https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=5](https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/?p=5)",
]
DOMAIN = "[www.shop.ipzs.it](http://www.shop.ipzs.it)"

# ──────────────── Telegram

send = lambda msg: requests.post(
f"[https://api.telegram.org/bot{os.getenv('TELEGRAM\_TOKEN')}/sendMessage](https://api.telegram.org/bot{os.getenv%28'TELEGRAM_TOKEN'%29}/sendMessage)",
data={"chat\_id": os.getenv("CHAT\_ID"), "text": msg, "parse\_mode": "HTML"})

# ──────────────── Helpers

ld = lambda fp: set(open(fp,encoding="utf-8").read().splitlines()) if os.path.exists(fp) else set()
sv = lambda fp,s: open(fp,"w",encoding="utf-8").write("\n".join(sorted(s)))
lj = lambda fp: json.load(open(fp)) if os.path.exists(fp) else {}
sj = lambda fp,d: open(fp,"w").write(json.dumps(d,indent=2))

# ──────────────── IPZS – parsing link

get\_links = lambda url: \[a\["href"] for a in BeautifulSoup(requests.get(url).content,"html.parser").select("a.product-item-link") if a.get("href")]

def scrape\_ipzs(url):
try: soup = BeautifulSoup(requests.get(url).content,"html.parser")
except: return None
info = {"link": url}
info\["nome"] = soup.select\_one("h1.page-title span.base").get\_text(strip=True)
pr = soup.select\_one("span.price"); info\["prezzo"] = pr.get\_text(strip=True) if pr else "N/A"
stock = soup.select\_one("div.stock"); txt = stock.get\_text(strip=True).upper() if stock else ""
info\["disponibilita"] = "NON DISPONIBILE" if "NON DISPONIBILE" in txt else ("DISPONIBILE" if "DISPONIBILE" in txt else txt or "N/A")
attr = {}
for tr in soup.select("div.product-info-main table.data tr"):
th, td = tr.find("th"), tr.find("td")
if th and td: attr\[th.get\_text(strip=True).lower()] = td.get\_text(strip=True)
info\["contingente"] = attr.get("contingente") or attr.get("tiratura") or attr.get("numero pezzi","N/A")
info\["data disponibilita"] = attr.get("data disponibilità") or attr.get("data disponibilita","N/A")
info\["finitura"] = attr.get("finitura","N/A")
info\["metallo"] = attr.get("metallo","N/A")
info\["peso (gr)"] = attr.get("peso (gr)","N/A")
info\["in vendita da"] = attr.get("in vendita da","N/A")
return info

def parse\_tiratura(txt):
nums = re.findall(r"\d+", txt.replace(".","").replace(" ",""))
return int(nums\[0]) if nums else None

def parse\_date(txt):
for fmt in \["%d %b %Y","%d %B %Y","%d/%m/%Y","%Y-%m-%d"]:
try: return datetime.strptime(txt.strip(), fmt)
except: pass

# ──────────────── Notifiche IPZS

def notify\_new(prods,seen):
for p in prods:
if p\["link"] in seen: continue
if send(f"<b>Nuova moneta</b>\n{p\['nome']}\n{p\['prezzo']}\n{p\['link']}").status\_code == 200:
seen.add(p\["link"])
return seen

def notify\_low(prods,alerted):
for p in prods:
t=parse\_tiratura(p\["contingente"]); d=p\["disponibilita"]
if t and t<=1500 and "NON DISPONIBILE" not in d and p\["link"] not in alerted:
msg=(f"<b>Bassa tiratura disponibile</b>\n<b>Nome:</b> {p\['nome']}\n<b>Prezzo:</b> {p\['prezzo']}\n"
f"<b>Contingente:</b> {p\['contingente']}\n<b>Disponibilità:</b> {p\['disponibilita']}\n"
f"<b>In vendita da:</b> {p\['in vendita da']}\n<b>Data disponibilità:</b> {p\['data disponibilita']}\n"
f"<b>Finitura:</b> {p\['finitura']}\n<b>Metallo:</b> {p\['metallo']}\n<b>Peso:</b> {p\['peso (gr)']}\n"
f"<b>Link:</b> {p\['link']}")
if send(msg).status\_code == 200: alerted.add(p\["link"])
return alerted

def notify\_dates(prods,alerts):
bucket={}
for p in prods:
d=parse\_date(p\["data disponibilita"])
if d: bucket.setdefault(d.date(),\[]).append(p)
now=datetime.now(); tmr=(now+timedelta(days=1)).date()
if tmr in bucket and len(bucket\[tmr])>=3 and now\.hour>=8:
if alerts.get(str(tmr))!=str(now\.date()):
msg=f"<b>{len(bucket\[tmr])} monete disponibili il {tmr}</b>\n"
msg+="\n".join("- "+x\["nome"] for x in bucket\[tmr])
if send(msg).status\_code==200: alerts\[str(tmr)]=str(now\.date())
return alerts

def sunday\_ping():
n=datetime.now()
if n.weekday()==6 and n.hour==11:
send("🔁 Check domenicale: bot attivo.")

# ──────────────── Spider lock

SPIDER\_HOURS=(7,19)
def spider\_allowed():
now=datetime.now()
if now\.hour not in SPIDER\_HOURS: return False
lock=lj(SPIDER\_LOCK)
last=lock.get("ts")
if last and (now-datetime.fromisoformat(last)).seconds<3600: return False
sj(SPIDER\_LOCK,{"ts"\:now\.isoformat()}); return True

def spider(start,max\_urls=50,max\_depth=3):
queue=\[(u,0) for u in start]; visited=set(); prods=\[]
while queue and len(visited)\<max\_urls:
url,d=queue.pop(0)
if url in visited or d>max\_depth: continue
visited.add(url)
try: soup=BeautifulSoup(requests.get(url).content,"html.parser")
except: continue
if soup.select\_one("h1.page-title span.base"):
prods.append(url); continue
for a in soup.find\_all("a",href=True):
h=a\["href"].split("#")\[0]
if DOMAIN in h and not h.endswith(('.jpg','.png','.pdf')) and h not in visited:
queue.append((h,d+1))
return prods

# ──────────────── MTM Monaco

MTM\_ROOT="[https://www.mtm-monaco.mc/index.php?route=common/home](https://www.mtm-monaco.mc/index.php?route=common/home)"
MTM\_DOMAIN="[www.mtm-monaco.mc](http://www.mtm-monaco.mc)"

def check\_mtm\_monaco():
seen=ld(MTM\_SEEN\_FILE); new\_seen=set()
try: soup=BeautifulSoup(requests.get(MTM\_ROOT).content,"html.parser")
except: return
links=\[a\["href"] for a in soup.find\_all("a",href=True) if "product/category" in a\["href"]]
for url in links:
try: cat=BeautifulSoup(requests.get(url).content,"html.parser")
except: continue
for block in cat.select(".product-thumb"):
a=block.find("a",href=True); name=block.find("h4")
if not a or not name: continue
link=a\["href"]; title=name.get\_text(strip=True)
if link in seen: continue
if "accessori" in title.lower(): continue
price=block.select\_one(".price"); p=price.get\_text(strip=True) if price else "Prezzo N/D"
msg=f"💎 <b>Moneta MTM disponibile</b>\n{title}\n{p}\n{link}"
if send(msg).status\_code==200: new\_seen.add(link)
\# Salva solo quelli visti ora (lock antiflood 1h)
if new\_seen:
now=datetime.now()
new\_seen={f"{now\.isoformat()}|{url}" for url in new\_seen}
old\_seen={x for x in seen if (now-datetime.fromisoformat(x.split("|")\[0])).seconds<3600}
sv(MTM\_SEEN\_FILE,old\_seen|new\_seen)

# ──────────────── MAIN

def main():
print("Start",datetime.now())
seen=ld(SEEN\_FILE); alerted=ld(LOW\_FILE); dates=lj(DATE\_FILE)
links=set()
for u in CATEGORY\_URLS:
links.update(get\_links(u))
if spider\_allowed():
links.update(spider(CATEGORY\_URLS,50,3))
prods=\[]
for l in links:
p=scrape\_ipzs(l)
if p: prods.append(p)
time.sleep(0.15)
seen=notify\_new(prods,seen)
alerted=notify\_low(prods,alerted)
dates=notify\_dates(prods,dates)
sunday\_ping()
sv(SEEN\_FILE,seen); sv(LOW\_FILE,alerted); sj(DATE\_FILE,dates)
check\_mtm\_monaco()
print("End",datetime.now())

if **name**=="**main**":
main()
