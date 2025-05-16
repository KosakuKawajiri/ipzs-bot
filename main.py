import requests
from bs4 import BeautifulSoup
import os
import json
from datetime import datetime, timedelta
import time

# --- Configurazione ambiente (Telegram)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# --- File di stato
SEEN_FILE = 'seen.txt'
LOW_MINTAGE_ALERTS_FILE = 'low_mintage_alerts.txt'
LAST_ALERT_FILE = 'last_alert.txt'
DATA_ALERTS_FILE = 'data_alerts.json'
EMPTY_RUNS_FILE = 'empty_runs.txt'

# --- Link critici da monitorare per remapping
CRITICAL_LINKS = [
    'https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/',
    'https://www.shop.ipzs.it/it/'
]

# --- Funzione per inviare messaggi Telegram
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    try:
        resp = requests.post(url, data=payload)
        resp.raise_for_status()
    except Exception as e:
        print(f"Errore invio Telegram: {e}")

# --- Funzioni utilitarie per file di stato
def load_list(filename):
    if not os.path.exists(filename):
        return set()
    with open(filename, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f if line.strip())

def save_list(filename, items):
    with open(filename, 'w', encoding='utf-8') as f:
        for item in items:
            f.write(item + '\n')

def load_json(filename):
    if not os.path.exists(filename):
        return {}
    with open(filename, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except:
            return {}

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

# --- Controllo settimanale link critici
def check_critical_links():
    now = datetime.now()
    last_alert_time = None
    if os.path.exists(LAST_ALERT_FILE):
        with open(LAST_ALERT_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if content:
                try:
                    last_alert_time = datetime.fromisoformat(content)
                except:
                    last_alert_time = None

    one_week_ago = now - timedelta(days=7)
    if last_alert_time and last_alert_time > one_week_ago:
        # Notifica già inviata entro l'ultima settimana
        return

    missing_links = []
    for link in CRITICAL_LINKS:
        try:
            resp = requests.head(link, timeout=10)
            if resp.status_code != 200:
                missing_links.append(link)
        except:
            missing_links.append(link)

    if missing_links:
        msg = "<b>Attenzione!</b> Alcuni link critici non sono più raggiungibili e richiedono remapping:\n"
        for ml in missing_links:
            msg += f"- {ml}\n"
        send_telegram_message(msg)
        with open(LAST_ALERT_FILE, 'w', encoding='utf-8') as f:
            f.write(now.isoformat())

# --- Scraping dettagliato di un singolo prodotto
def scrape_product_page(url):
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        info = {}
        # Questi selettori sono esempi, adatta alla struttura reale del sito
        info['nome'] = soup.select_one('.product-name').get_text(strip=True) if soup.select_one('.product-name') else 'N/A'
        info['prezzo'] = soup.select_one('.price').get_text(strip=True) if soup.select_one('.price') else 'N/A'

        for row in soup.select('.product-attributes tr'):
            cols = row.find_all('td')
            if len(cols) == 2:
                key = cols[0].get_text(strip=True).lower()
                val = cols[1].get_text(strip=True)
                info[key] = val

        info['link'] = url
        return info
    except Exception as e:
        print(f"Errore scraping pagina prodotto {url}: {e}")
        return None

# --- Funzione principale di scraping
def scrape_all():
    today = datetime.now().date()
    seen = load_list(SEEN_FILE)
    low_mintage_alerts = load_list(LOW_MINTAGE_ALERTS_FILE)
    new_coins = []
    low_mintage_coins = []

    # Step 1: Controllo link critici
    # (Questa funzione è chiamata separatamente per evitare duplicati)

    # Step 2: Scraping pagina categoria principale (primo link critico)
    try:
        resp = requests.get(CRITICAL_LINKS[0], timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Estrazione link prodotti: cambia selettore secondo sito
        product_links = [a['href'] for a in soup.select('.product-item-link') if a.has_attr('href')]

        for prod_url in product_links:
            if prod_url in seen:
                continue
            info = scrape_product_page(prod_url)
            if not info:
                continue

            # Controllo tiratura o contingente
            tiratura_keys = ['tiratura', 'contingente', 'numero pezzi']
            tiratura_val = None
            for key in tiratura_keys:
                if key in info:
                    try:
                        val = int(''.join(filter(str.isdigit, info[key])))
                        tiratura_val = val
                        break
                    except:
                        continue

            disponibilita = info.get('disponibilita', '').lower()
            is_available = any(status in disponibilita for status in ['disponibile', 'in vendita', 'prodotto in esaurimento'])

            if tiratura_val is not None and tiratura_val <= 1500 and is_available:
                if prod_url not in low_mintage_alerts:
                    low_mintage_coins.append(info)
                    low_mintage_alerts.add(prod_url)
            else:
                new_coins.append(info)

            seen.add(prod_url)

    except Exception as e:
        print(f"Errore scraping lista prodotti: {e}")

    save_list(SEEN_FILE, seen)
    save_list(LOW_MINTAGE_ALERTS_FILE, low_mintage_alerts)

    return new_coins, low_mintage_coins

# --- Notifica monete a bassa tiratura (trigger istantaneo)
def notify_low_mintage(coins):
    msg = "<b>Monete a bassa tiratura disponibili!</b>\n\n"
    for coin in coins:
        msg += f"- NOME MONETA: {coin.get('nome','N/A')}\n"
        msg += f"- PREZZO: {coin.get('prezzo','N/A')}\n"
        msg += f"- CONTINGENTE: {coin.get('contingente', coin.get('tiratura', 'N/A'))}\n"
        msg += f"- DISPONIBILITA: {coin.get('disponibilita','N/A')}\n"
        msg += f"- IN VENDITA DA: {coin.get('in vendita da','N/A')}\n"
        msg += f"- DATA DISPONIBILITA: {coin.get('data disponibilita','N/A')}\n"
        msg += f"- FINITURA: {coin.get('finitura','N/A')}\n"
        msg += f"- METALLO: {coin.get('metallo','N/A')}\n"
        msg += f"- PESO (gr): {coin.get('peso (gr)','N/A')}\n"
        msg += f"- LINK: {coin.get('link','N/A')}\n\n"
    send_telegram_message(msg)

# --- Funzione per notificare monete nuove generiche
def notify_new_coins(coins):
    if not coins:
        return
    msg = "<b>Nuove monete trovate:</b>\n\n"
    for coin in coins:
        nome = coin.get('nome','N/A')
        link = coin.get('link','N/A')
        prezzo = coin.get('prezzo','N/A')
        msg += f"- {nome} - {prezzo}\n{link}\n\n"
    send_telegram_message(msg)

# --- Controllo notifiche per date disponibilità con almeno 3 monete
def notify_date_availability():
    # Carica dati storico date
    data_alerts = load_json(DATA_ALERTS_FILE)
    today = datetime.now().date()
    # Scarico nuovamente la lista monete viste
    seen = load_list(SEEN_FILE)
    # Questa funzione è semplificata per esempio: si può migliorare con scraping completo

    # Per semplicità rileviamo date disponibilità da monete viste salvate in seen.txt 
    # (se hai file dettagliati potresti usare quelli, altrimenti da scraping)

    # Qui si ipotizza di ri-scansionare prodotti per aggiornare date disponibili:
    # Per demo usiamo solo i prodotti già visti (non ottimale ma indicativo)
    date_counts = {}

    # Questo è un esempio minimale: in un uso reale faresti scraping o logica separata

    # ... implementazione personalizzata a seconda dei dati che tieni ...

    # Supponiamo date_counts = {"2025-05-20": 4, "2025-05-22": 1} per demo

    # Se non hai dati reali, puoi saltare questa funzione o aggiungere la logica completa

    # Se ci sono date con almeno 3 monete per giorno successivo, invia notifica

    tomorrow = today + timedelta(days=1)
    for date_str, count in date_counts.items():
        try:
            d = datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            continue
        if d == tomorrow and count >= 3:
            # Controlla se già notificato
            last_notif_date = data_alerts.get(date_str)
            if last_notif_date != str(today):
                msg = f"<b>Attenzione!</b>\nPer il {date_str} sono previste almeno {count} nuove monete disponibili."
                send_telegram_message(msg)
                data_alerts[date_str] = str(today)
                save_json(DATA_ALERTS_FILE, data_alerts)

# --- Notifica domenicale alle 13:00 (routine)
def notify_sunday_routine():
    now = datetime.now()
    if now.weekday() == 6 and now.hour == 13:  # Domenica ore 13
        send_telegram_message("Routine domenicale attiva: bot in esecuzione regolare.")

# --- Main
def main():
    print("Avvio scraping...")
    check_critical_links()  # Controlla link critici e invia alert settimanale

    new_coins, low_mintage_coins = scrape_all()

    if low_mintage_coins:
        notify_low_mintage(low_mintage_coins)

    if new_coins:
        notify_new_coins(new_coins)

    notify_date_availability()

    notify_sunday_routine()

    print("Esecuzione completata.")

if __name__ == '__main__':
    main()
