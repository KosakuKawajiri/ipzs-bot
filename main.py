import os
import json
import time
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# === CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CATALOG_URL = "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/"
HOMEPAGE_URL = "https://www.shop.ipzs.it/it/"

SEEN_FILE = "seen.txt"
EMPTY_RUNS_FILE = "empty_runs.txt"
CRITICAL_LINKS_FILE = "critical_links.txt"
AVAILABILITY_ALERTS_FILE = "availability_alerts.json"
LOW_MINTAGE_ALERTS_FILE = "low_mintage_alerts.txt"

# === FUNCTIONS ===
def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Token o Chat ID non presenti. Messaggio non inviato.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    response = requests.post(url, data=payload)
    if not response.ok:
        print("Errore invio telegram:", response.text)


def initialize_files():
    for f in [SEEN_FILE, EMPTY_RUNS_FILE, CRITICAL_LINKS_FILE, AVAILABILITY_ALERTS_FILE, LOW_MINTAGE_ALERTS_FILE]:
        if not os.path.exists(f):
            with open(f, "w") as file:
                file.write("" if f != AVAILABILITY_ALERTS_FILE else "{}")
            send_telegram_message(f"[TEST] Creato file: <b>{f}</b>")


def check_critical_links():
    # Controlla i due link critici una volta a settimana
    now = datetime.now()
    last_alert_time = now - timedelta(days=8)
    if os.path.exists(CRITICAL_LINKS_FILE):
        with open(CRITICAL_LINKS_FILE, "r") as f:
            content = f.read().strip()
            if content:
                try:
                    last_alert_time = datetime.fromisoformat(content)
                except ValueError:
                    pass

    if (now - last_alert_time).days < 7:
        return  # Salta notifica se già inviata recentemente

    broken = []
    for url in [CATALOG_URL, HOMEPAGE_URL]:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                broken.append(url)
        except Exception:
            broken.append(url)

    if broken:
        msg = "🚨 <b>Link IPZS non più disponibili:</b>\n" + "\n".join(broken)
        send_telegram_message(msg)
        with open(CRITICAL_LINKS_FILE, "w") as f:
            f.write(now.isoformat())


def routine_test_message():
    now = datetime.now()
    # Domenica alle 13
    if now.weekday() == 6 and now.hour == 13:
        send_telegram_message("🔄 <b>Routine attiva</b> — IPZS bot in esecuzione settimanale ✅")


# === MAIN LOGIC ===
if __name__ == "__main__":
    send_telegram_message("[TEST] Routine IPZS avviata ✅")
    initialize_files()
    check_critical_links()
    routine_test_message()

    # Placeholder per scraping da completare
    print("Scraping e analisi da implementare...")
