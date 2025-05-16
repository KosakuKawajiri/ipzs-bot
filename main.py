import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import hashlib
import json

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

BASE_URL = "https://www.shop.ipzs.it"
MONETE_URL = f"{BASE_URL}/it/catalog/category/view/s/monete/id/3/"
HOME_URL = f"{BASE_URL}/it/"

SEEN_FILE = "seen.txt"
EMPTY_RUNS_FILE = "empty_runs.txt"
CRITICAL_LINKS_FILE = "critical_links.txt"
LOW_MINTAGE_ALERTS_FILE = "low_mintage_alerts.txt"
AVAILABILITY_ALERTS_FILE = "availability_alerts.json"

MONTHS_MAP = {
    "gen": "01", "feb": "02", "mar": "03", "apr": "04", "mag": "05", "giu": "06",
    "lug": "07", "ago": "08", "set": "09", "ott": "10", "nov": "11", "dic": "12"
}

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Errore invio telegram: {e}")

def check_critical_links():
    now = datetime.now()
    alert_needed = False

    if not os.path.exists(CRITICAL_LINKS_FILE):
        with open(CRITICAL_LINKS_FILE, "w") as f:
            f.write((now - timedelta(days=7)).isoformat())
        send_telegram_message("[TEST] File critical_links.txt creato")
        return

    with open(CRITICAL_LINKS_FILE, "r") as f:
        try:
            last_alert_time = datetime.fromisoformat(f.read().strip())
        except ValueError:
            last_alert_time = now - timedelta(days=7)

    if (now - last_alert_time).days < 7:
        return

    for url in [MONETE_URL, HOME_URL]:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                alert_needed = True
        except:
            alert_needed = True

    if alert_needed:
        send_telegram_message("❗️ Uno dei link critici del sito IPZS non è più raggiungibile. Verifica se è necessario aggiornare il mapping.")
        with open(CRITICAL_LINKS_FILE, "w") as f:
            f.write(now.isoformat())

def convert_date(date_str):
    try:
        parts = date_str.strip().split()
        if len(parts) == 3:
            day, month_abbr, year = parts
            return datetime.strptime(f"{day}/{MONTHS_MAP[month_abbr.lower()]}/{year}", "%d/%m/%Y")
    except:
        pass
    return None

def load_file_lines(path):
    if not os.path.exists(path):
        with open(path, "w") as f:
            if path.endswith(".json"):
                json.dump({}, f)
            f.write("")
        send_telegram_message(f"[TEST] File {path} creato")
    if path.endswith(".json"):
        with open(path, "r") as f:
            return json.load(f)
    with open(path, "r") as f:
        return set(line.strip() for line in f)

def save_to_file(path, data):
    if path.endswith(".json"):
        with open(path, "w") as f:
            json.dump(data, f)
    else:
        with open(path, "a") as f:
            if isinstance(data, str):
                f.write(data + "\n")
            else:
                f.writelines([item + "\n" for item in data])

def notify_low_mintage(details):
    msg = (
        f"<b>NOME MONETA:</b> {details.get('nome')}\n"
        f"<b>PREZZO:</b> {details.get('prezzo')}\n"
        f"<b>CONTINGENTE:</b> {details.get('tiratura')}\n"
        f"<b>DISPONIBILITA:</b> {details.get('disponibilita')}\n"
        f"<b>IN VENDITA DA:</b> {details.get('in_vendita_da')}\n"
        f"<b>DATA DISPONIBILITA:</b> {details.get('data_disponibilita')}\n"
        f"<b>FINITURA:</b> {details.get('finitura')}\n"
        f"<b>METALLO:</b> {details.get('metallo')}\n"
        f"<b>PESO (gr):</b> {details.get('peso')}\n"
        f"<b>LINK:</b> {details.get('link')}"
    )
    send_telegram_message(msg)

def parse_monete():
    try:
        response = requests.get(MONETE_URL, timeout=10)
    except Exception as e:
        print(f"Errore richiesta: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    items = soup.select("li.item")
    results = []
    for item in items:
        link = item.select_one("a.product-item-link")
        if link:
            results.append(link["href"])
    return results

# Altri metodi che elaborano i link, analizzano i dettagli, e applicano le condizioni verranno aggiunti qui.

if __name__ == "__main__":
    send_telegram_message("[TEST] Routine IPZS avviata ✅")
    check_critical_links()
    # parse_monete(), controlli availability e low mintage vanno aggiunti
