import requests
from bs4 import BeautifulSoup
import hashlib
import os
from datetime import datetime

# === CONFIGURAZIONE ===
CATALOG_URL = "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/"
HOMEPAGE_URL = "https://www.shop.ipzs.it/it/"
KEYWORDS = ["tiratura limitata", "2 euro", "emissione", "commemorativa", "proof"]
TELEGRAM_TOKEN = "7341199633:AAEuCGfffO3N9dyZtCfM-SrlqBjByc1XtEU"
CHAT_ID = 80114152

# === TELEGRAM ===
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload)
    except:
        pass

# === FILE HANDLING ===
def load_file(filename):
    if not os.path.exists(filename):
        return set()
    with open(filename, "r") as f:
        return set(line.strip() for line in f.readlines())

def append_to_file(filename, line):
    with open(filename, "a") as f:
        f.write(line + "\n")

# === SITO IPZS MONETE ===
def check_monete_page():
    try:
        res = requests.get(CATALOG_URL, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.find_all("li", class_="item")

        seen = load_file("seen.txt")
        new_found = 0

        for item in items:
            text = item.get_text().lower()
            if any(keyword in text for keyword in KEYWORDS):
                content_hash = hashlib.md5(text.encode()).hexdigest()
                if content_hash not in seen:
                    title_tag = item.find("h2")
                    title = title_tag.get_text(strip=True) if title_tag else "Nuova emissione IPZS!"
                    link_tag = item.find("a", href=True)
                    link = link_tag["href"] if link_tag else CATALOG_URL
                    message = f"💰 *{title}*\n🔗 https://www.shop.ipzs.it{link}"
                    send_telegram_message(message)
                    append_to_file("seen.txt", content_hash)
                    new_found += 1

        if new_found == 0:
            append_to_file("empty_runs.txt", datetime.now().isoformat())
        return new_found
    except:
        return -1  # errore generico, nessuna notifica inviata

# === CONTROLLO LINK STRATEGICI ===
def check_critical_links():
    alerts = []
    now = datetime.now()

    last_alert_file = "last_url_alert.txt"
    if os.path.exists(last_alert_file):
        with open(last_alert_file, "r") as f:
            content = f.read().strip()
            if content:
                try:
                    last_alert_time = datetime.fromisoformat(content)
                    if (now - last_alert_time).days < 7:
                        return  # Niente notifica se già inviata meno di 7 giorni fa
                except ValueError:
                    pass  # Se il contenuto è invalido, si procede con il controllo link

    for url in [CATALOG_URL, HOMEPAGE_URL]:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                alerts.append(f"⚠️ Link non più valido: {url}")
        except:
            alerts.append(f"⚠️ Errore nel controllare: {url}")

    if alerts:
        send_telegram_message("🚨 *Attenzione: alcuni link IPZS potrebbero essere cambiati!*\n\n" + "\n".join(alerts))
        with open(last_alert_file, "w") as f:
            f.write(now.isoformat())

# === NOTIFICA SETTIMANALE ===
def send_weekly_ping():
    now = datetime.now()
    if now.weekday() == 6 and now.hour == 13:  # domenica ore 13
        send_telegram_message("✅ Routine attiva: controllo IPZS automatico funzionante.")

# === AVVIO ===
if __name__ == "__main__":
    new_items = check_monete_page()
    if new_items != -1:
        check_critical_links()
        send_weekly_ping()
