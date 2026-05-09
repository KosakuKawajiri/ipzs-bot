import os
import requests

def send(text: str) -> bool:
    token = os.getenv("TELEGRAM_TOKEN")
    chat  = os.getenv("CHAT_ID")

    if not token or not chat:
        return False

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": chat,
                "text": text,
                "parse_mode": "HTML"
            },
            timeout=10
        )

        r.raise_for_status()
        return True

    except:
        return False
