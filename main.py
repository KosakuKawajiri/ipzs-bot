import requests
from bs4 import BeautifulSoup
import hashlib
import os

# === CONFIGURAZIONE ===
URL = "https://www.shop.ipzs.it/monete.html"
KEYWORDS = ["tiratura limitata", "2 euro", "emissione", "commemorativa", "proof", "emissione test"]
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# === FUNZIONE TELEGRAM ===
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            print("Errore nell'invio Telegram:", response.text)
    except Exception as e:
        print("Errore connessione Telegram:", e)

# === CARICA HASH VECCHI ===
def load_seen_hashes():
    if not os.path.exists("seen.txt"):
        return set()
    with open("seen.txt", "r") as f:
        return set(line.strip() for line in f.readlines())

def save_seen_hash(content_hash):
    with open("seen.txt", "a") as f:
        f.write(content_hash + "\n")

# === ESTRAI E VERIFICA CONTENUTI ===
def check_site():
    try:
        res = requests.get(URL, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        items = soup.find_all("li", class_="item")

        # AGGIUNGI UN BLOCCO FALSO PER IL TEST
        fake_html = '<li class="item"><h2>EMISSIONE TEST SPECIALE</h2><a href="/it/emissione-test">Vai al prodotto</a><p>Questa è una tiratura limitata</p></li>'
        fake_soup = BeautifulSoup(fake_html, "html.parser")
        items.append(fake_soup.li)

        seen = load_seen_hashes()
        new_found = 0

        for item in items:
            text = item.get_text().lower()
            if any(keyword in text for keyword in KEYWORDS):
                content_hash = hashlib.md5(text.encode()).hexdigest()
                if content_hash not in seen:
                    title_tag = item.find("h2")
                    title = title_tag.get_text(strip=True) if title_tag else "Nuova emissione IPZS!"
                    link_tag = item.find("a", href=True)
                    link = link_tag["href"] if link_tag else URL
                    message = f"💰 *{title}*\n🔗 https://www.shop.ipzs.it{link}"
                    send_telegram_message(message)
                    save_seen_hash(content_hash)
                    new_found += 1

        if new_found == 0:
            print("✅ Nessuna nuova emissione trovata.")
        else:
            print(f"📬 Inviate {new_found} notifiche Telegram.")
    except Exception as e:
        print("Errore durante il controllo del sito:", e)

# === AVVIO SINGOLO ===
if __name__ == "__main__":
    check_site()
