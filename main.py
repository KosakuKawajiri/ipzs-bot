import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
import time

# Variabili file per storico/notifiche
SEEN_FILE = 'seen.txt'
LOW_STOCK_ALERT_FILE = 'low_stock_alerts.txt'
DATE_ALERTS_FILE = 'date_alerts.json'
EMPTY_RUNS_FILE = 'empty_runs.txt'
LAST_LINK_ALERT_FILE = 'last_link_alert.txt'

# Link critici da controllare settimanalmente
CRITICAL_LINKS = [
    'https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/',
    'https://www.shop.ipzs.it/it/'
]

# Funzione invio messaggi Telegram
def send_telegram_message(text):
    import os
    import requests

    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    if not TOKEN or not CHAT_ID:
        print("⚠️ Telegram token o chat ID non configurati.")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': text,
        'parse_mode': 'HTML'
    }
    try:
        r = requests.post(url, data=payload)
        if r.status_code == 200:
            return True
        else:
            print(f"Errore invio Telegram: {r.status_code} {r.text}")
            return False
    except Exception as e:
        print(f"Eccezione invio Telegram: {e}")
        return False

# --- Funzioni di scraping ---

def get_product_links(category_url):
    try:
        resp = requests.get(category_url, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"Errore richiesta categoria {category_url}: {e}")
        return []

    soup = BeautifulSoup(resp.content, 'html.parser')
    links = []
    for a in soup.select('a.product-item-link'):
        href = a.get('href')
        if href and href.startswith('http'):
            links.append(href)
    return links

def scrape_product_page(url):
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"Errore richiesta prodotto {url}: {e}")
        return None

    soup = BeautifulSoup(resp.content, 'html.parser')
    info = {}

    # Nome moneta
    nome_tag = soup.select_one('h1.page-title span.base')
    info['nome'] = nome_tag.get_text(strip=True) if nome_tag else "N/A"

    # Prezzo
    prezzo_tag = soup.select_one('span.price')
    info['prezzo'] = prezzo_tag.get_text(strip=True) if prezzo_tag else "N/A"

    # Disponibilità
    stock_div = soup.select_one('div.stock')
    if stock_div:
        classes = stock_div.get('class', [])
        if any(c in ['available', 'in-stock', 'stock available'] for c in classes):
            info['disponibilita'] = 'DISPONIBILE'
        else:
            info['disponibilita'] = stock_div.get_text(strip=True).upper()
    else:
        info['disponibilita'] = 'N/A'

    # Attributi tabella
    info_attrs = {}
    rows = soup.select('div.product-info-main table.data tr')
    for tr in rows:
        th = tr.find('th')
        td = tr.find('td')
        if th and td:
            key = th.get_text(strip=True).lower()
            value = td.get_text(strip=True)
            info_attrs[key] = value

    # Tiratura / Contingente / Numero pezzi
    info['contingente'] = info_attrs.get('contingente') or info_attrs.get('tiratura') or info_attrs.get('numero pezzi') or "N/A"
    info['data disponibilita'] = info_attrs.get('data disponibilità') or info_attrs.get('data disponibilita') or "N/A"
    info['finitura'] = info_attrs.get('finitura', 'N/A')
    info['metallo'] = info_attrs.get('metallo', 'N/A')
    info['peso (gr)'] = info_attrs.get('peso (gr)', 'N/A')
    info['in vendita da'] = info_attrs.get('in vendita da', 'N/A')

    info['link'] = url
    return info

# --- Gestione storico / file ---

def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f if line.strip())

def save_seen(seen_set):
    with open(SEEN_FILE, 'w', encoding='utf-8') as f:
        for item in sorted(seen_set):
            f.write(item + "\n")

def load_low_stock_alerts():
    if not os.path.exists(LOW_STOCK_ALERT_FILE):
        return set()
    with open(LOW_STOCK_ALERT_FILE, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f if line.strip())

def save_low_stock_alerts(alert_set):
    with open(LOW_STOCK_ALERT_FILE, 'w', encoding='utf-8') as f:
        for item in sorted(alert_set):
            f.write(item + "\n")

def load_date_alerts():
    if not os.path.exists(DATE_ALERTS_FILE):
        return {}
    with open(DATE_ALERTS_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except:
            return {}

def save_date_alerts(data):
    with open(DATE_ALERTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def load_last_link_alert_time():
    if not os.path.exists(LAST_LINK_ALERT_FILE):
        return None
    with open(LAST_LINK_ALERT_FILE, 'r', encoding='utf-8') as f:
        content = f.read().strip()
        if content == '':
            return None
        try:
            return datetime.fromisoformat(content)
        except:
            return None

def save_last_link_alert_time(dt):
    with open(LAST_LINK_ALERT_FILE, 'w', encoding='utf-8') as f:
        f.write(dt.isoformat())

# --- Funzioni notifiche avanzate ---

def notify_low_stock(products, alerted_set):
    # products è lista dict con info prodotto
    # alerted_set tiene i link già notificati per low stock
    new_alerts = []
    for p in products:
        try:
            cont = p.get('contingente', 'N/A')
            cont_int = int(''.join(filter(str.isdigit, cont))) if cont != 'N/A' else 999999
        except:
            cont_int = 999999

        disp = p.get('disponibilita', '').upper()
        if cont_int <= 1500 and 'NON DISPONIBILE' not in disp and p['link'] not in alerted_set:
            # Nuova notifica
            text = (
                f"<b>Moneta a bassa tiratura rilevata</b>\n"
                f"Nome moneta: {p.get('nome')}\n"
                f"Prezzo: {p.get('prezzo')}\n"
                f"Contingente: {p.get('contingente')}\n"
                f"Disponibilità: {p.get('disponibilita')}\n"
                f"In vendita da: {p.get('in vendita da')}\n"
                f"Data disponibilità: {p.get('data disponibilita')}\n"
                f"Finitura: {p.get('finitura')}\n"
                f"Metallo: {p.get('metallo')}\n"
                f"Peso (gr): {p.get('peso (gr)')}\n"
                f"Link: {p.get('link')}"
            )
            sent = send_telegram_message(text)
            if sent:
                new_alerts.append(p['link'])
                print(f"Notifica tiratura bassa inviata per {p['nome']}")

    for link in new_alerts:
        alerted_set.add(link)
    return alerted_set

def notify_date_availability(products, date_alerts):
    # Raggruppa prodotti per data disponibilità
    data_dict = {}
    for p in products:
        dd = p.get('data disponibilita')
        if dd and dd != 'N/A':
            data_dict.setdefault(dd, []).append(p)

    now = datetime.now()
    to_notify = []
    for date_str, prods in data_dict.items():
        if len(prods) >= 3:
            # Controlla se notifica già inviata per questa data
            notified = date_alerts.get(date_str, False)
            # Calcolo giorno prima alle 8:00
            try:
                date_obj = datetime.strptime(date_str, '%d %b %Y')  # es: '27 feb 2025'
            except:
                try:
                    date_obj = datetime.strptime(date_str, '%d %B %Y')
                except:
                    continue
            notify_time = date_obj - timedelta(days=1)
            notify_time = notify_time.replace(hour=8, minute=0, second=0, microsecond=0)

            if now >= notify_time and not notified:
                to_notify.append((date_str, prods))

    for date_str, prods in to_notify:
        testo = f"<b>Avviso disponibilità monete per data {date_str}</b>\n"
        testo += f"Sono presenti {len(prods)} monete con questa data disponibilità:\n"
        for p in prods:
            testo += f"- {p['nome']} ({p['link']})\n"
        sent = send_telegram_message(testo)
        if sent:
            date_alerts[date_str] = True
            print(f"Notifica disponibilità per data {date_str} inviata.")

    return date_alerts

def notify_new_products(products, seen_set):
    new_products = [p for p in products if p['link'] not in seen_set]
    for p in new_products:
        testo = (
            f"<b>Nuova moneta disponibile</b>\n"
            f"Nome: {p['nome']}\n"
            f"Prezzo: {p['prezzo']}\n"
            f"Disponibilità: {p['disponibilita']}\n"
            f"Tiratura/Contingente: {p['contingente']}\n"
            f"Link: {p['link']}"
        )
        sent = send_telegram_message(testo)
        if sent:
            seen_set.add(p['link'])
            print(f"Notifica nuova moneta inviata per {p['nome']}")
    return seen_set

def check_critical_links():
    missing = []
    for url in CRITICAL_LINKS:
        try:
            r = requests.head(url, timeout=5)
            if r.status_code != 200:
                missing.append(url)
        except Exception as e:
            missing.append(url)
    return missing

def notify_critical_links(missing_links, last_alert_time):
    now = datetime.now()
    if not missing_links:
        return last_alert_time

    # Notifica max 1 volta a settimana
    if last_alert_time and (now - last_alert_time).days < 7:
        print("Notifica link critici già inviata recentemente.")
        return last_alert_time

    testo = "<b>Attenzione: Link critici non raggiungibili</b>\n"
    for l in missing_links:
        testo += f"- {l}\n"

    sent = send_telegram_message(testo)
    if sent:
        print("Notifica link critici inviata.")
        return now
    else:
        return last_alert_time

def notify_daily_status():
    # Notifica semplice di check bot (ogni domenica alle 13)
    testo = "<b>Bot IPZS operativo</b> ✅"
    send_telegram_message(testo)
    print("Notifica stato giornaliero inviata.")

# --- MAIN ---

def main():
    print(f"Avvio bot IPZS - {datetime.now()}")

    seen = load_seen()
    low_stock_alerts = load_low_stock_alerts()
    date_alerts = load_date_alerts()
    last_link_alert_time = load_last_link_alert_time()

    category_urls = [
        'https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/',
        # aggiungi altre categorie se necessario
    ]

    all_products = []
    for cat_url in category_urls:
        print(f"Scraping categoria: {cat_url}")
        product_links = get_product_links(cat_url)
        print(f"Trovati {len(product_links)} prodotti nella categoria")
        for plink in product_links:
            pinfo = scrape_product_page(plink)
            if pinfo:
                all_products.append(pinfo)
            time.sleep(0.2)  # gentilezza verso server

    # Controllo link critici e notifica settimanale
    missing_links = check_critical_links()
    last_link_alert_time = notify_critical_links(missing_links, last_link_alert_time)
    if last_link_alert_time:
        save_last_link_alert_time(last_link_alert_time)

    # Notifica nuova moneta
    seen = notify_new_products(all_products, seen)
    save_seen(seen)

    # Notifica monete bassa tiratura (non sovrapposta a nuova moneta)
    low_stock_alerts = notify_low_stock(all_products, low_stock_alerts)
    save_low_stock_alerts(low_stock_alerts)

    # Notifica disponibilità date
    date_alerts = notify_date_availability(all_products, date_alerts)
    save_date_alerts(date_alerts)

    # Controllo se oggi è domenica alle 13:00 per notifica stato bot
    now = datetime.now()
    if now.weekday() == 6 and now.hour == 13:
        notify_daily_status()

    print("Esecuzione bot terminata.")

if __name__ == '__main__':
    main()
