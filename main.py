import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time

# === CONFIG ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = "https://www.shop.ipzs.it/it/catalog/category/view/s/monete/id/3/"
HOMEPAGE_URL = "https://www.shop.ipzs.it/it/"
SEEN_FILE = "seen.txt"
EMPTY_RUNS_FILE = "empty_runs.txt"
CRITICAL_ALERT_FILE = "last_alert.txt"
DATA_ALERT_FILE = "data_alerts.json"
ROUTINE_HOUR = 13
ROUTINE_WEEKDAY = 6  # Domenica

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    requests.post(url, data=data)


def fetch_page(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception:
        return None


def check_links():
    now = datetime.now()
    if os.path.exists(CRITICAL_ALERT_FILE):
        with open(CRITICAL_ALERT_FILE, "r") as f:
            try:
                last_alert = datetime.fromisoformat(f.read().strip())
                if (now - last_alert).days < 7:
                    return
            except ValueError:
                pass

    for url in [BASE_URL, HOMEPAGE_URL]:
        if fetch_page(url) is None:
            send_telegram_message(f"⚠️ Il link critico non è più raggiungibile:\n{url}")

    with open(CRITICAL_ALERT_FILE, "w") as f:
        f.write(now.isoformat())


def extract_monete(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.select("li.item.product.product-item")


def estrai_dati_monetari(card):
    nome = card.select_one("strong.product.name.product-item-name").text.strip()
    link = card.select_one("a.product.photo.product-item-photo")["href"]
    prezzo = card.select_one("span.price").text.strip()
    dettagli = card.select("div.product.details.product-item-details div")

    data = {
        "nome": nome,
        "link": link,
        "prezzo": prezzo,
        "contingente": "",
        "disponibilita": "",
        "in_vendita_da": "",
        "data_disponibilita": "",
        "finitura": "",
        "metallo": "",
        "peso": ""
    }

    for det in dettagli:
        txt = det.text.lower()
        if "tiratura" in txt or "contingente" in txt or "pezzi" in txt:
            data["contingente"] = txt
        elif "non disponibile" in txt:
            data["disponibilita"] = "NON DISPONIBILE"
        elif "disponibile" in txt or "esaurimento" in txt:
            data["disponibilita"] = "DISPONIBILE"
        elif "in vendita da" in txt:
            data["in_vendita_da"] = det.text.strip()
        elif "data disponibilità" in txt:
            data["data_disponibilita"] = det.text.strip().split(":")[-1].strip()
        elif "finitura" in txt:
            data["finitura"] = txt
        elif "metallo" in txt:
            data["metallo"] = txt
        elif "peso" in txt:
            data["peso"] = txt
    return data


def already_seen(link):
    if not os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "w") as f:
            f.write("")
        send_telegram_message("[TEST] Creato file seen.txt")
        return False

    with open(SEEN_FILE, "r") as f:
        return link in f.read()


def save_seen(link):
    with open(SEEN_FILE, "a") as f:
        f.write(link + "\n")


def check_low_mintage(data):
    if data["disponibilita"] != "DISPONIBILE":
        return False

    for chiave in ["tiratura", "contingente", "pezzi"]:
        if chiave in data["contingente"]:
            numeri = [int(s.replace(".", "")) for s in data["contingente"].split() if s.replace(".", "").isdigit()]
            if numeri and numeri[0] <= 1500:
                return True
    return False


def alert_low_mintage(data):
    msg = (
        f"⚠️ Moneta a bassa tiratura rilevata:\n"
        f"- NOME MONETA: {data['nome']}\n"
        f"- PREZZO: {data['prezzo']}\n"
        f"- CONTINGENTE: {data['contingente']}\n"
        f"- DISPONIBILITA: {data['disponibilita']}\n"
        f"- IN VENDITA DA: {data['in_vendita_da']}\n"
        f"- DATA DISPONIBILITA: {data['data_disponibilita']}\n"
        f"- FINITURA: {data['finitura']}\n"
        f"- METALLO: {data['metallo']}\n"
        f"- PESO (gr): {data['peso']}\n"
        f"- LINK: {data['link']}"
    )
    send_telegram_message(msg)


def notify_shared_release(monete):
    date_count = {}
    date_links = {}

    for data in monete:
        data_disp = data["data_disponibilita"]
        if not data_disp:
            continue
        date_count[data_disp] = date_count.get(data_disp, 0) + 1
        date_links.setdefault(data_disp, []).append((data["nome"], data["link"]))

    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d %b %Y").lower()

    for data_disp, count in date_count.items():
        if count >= 3 and tomorrow in data_disp.lower():
            key = f"{data_disp}"
            already_sent = False
            if os.path.exists(DATA_ALERT_FILE):
                with open(DATA_ALERT_FILE, "r") as f:
                    already_sent = key in f.read()
            else:
                with open(DATA_ALERT_FILE, "w") as f:
                    f.write("")

            if not already_sent and datetime.now().hour == 8:
                msg = f"📆 Almeno 3 monete saranno disponibili il {data_disp}:\n"
                for nome, link in date_links[data_disp]:
                    msg += f"🔹 {nome}\n{link}\n"
                send_telegram_message(msg)
                with open(DATA_ALERT_FILE, "a") as f:
                    f.write(f"{key}\n")


def notify_routine():
    now = datetime.now()
    if now.weekday() == ROUTINE_WEEKDAY and now.hour == ROUTINE_HOUR:
        send_telegram_message("🔁 Routine attiva regolarmente.")


def main():
    notify_routine()
    check_links()

    html = fetch_page(BASE_URL)
    if html is None:
        return

    cards = extract_monete(html)
    if not cards:
        if not os.path.exists(EMPTY_RUNS_FILE):
            with open(EMPTY_RUNS_FILE, "w") as f:
                f.write("")
            send_telegram_message("[TEST] Creato file empty_runs.txt")
        return

    nuovi_dati = []
    for card in cards:
        data = estrai_dati_monetari(card)
        if not already_seen(data["link"]):
            save_seen(data["link"])
            nuovi_dati.append(data)

    for data in nuovi_dati:
        if check_low_mintage(data):
            alert_low_mintage(data)

    notify_shared_release(nuovi_dati)


if __name__ == "__main__":
    main()
