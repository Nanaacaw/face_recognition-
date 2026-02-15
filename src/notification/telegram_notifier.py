import os
import requests

class TelegramNotifier:
    def __init__(self, token:str, chat_id: str, timeout_sec: int = 15):
        self.token = token
        self.chat_id = chat_id
        self.timeout_sec = timeout_sec
        self.base = f"https://api.telegram.org/bot{token}"

    @classmethod
    def from_env(cls):
        token = os.getenv("SPG_TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("SPG_TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            raise RuntimeError("Missing SPG_TELEGRAM_BOT_TOKEN or SPG_TELEGRAM_CHAT_ID in environment")
        return cls(token=token, chat_id=chat_id)

    def send_message(self, text: str) -> None:
        url = f"{self.base}/sendMessage"
        resp = requests.post(
            url,
            data={"chat_id":self.chat_id, "text": text},
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()

    def send_photo(self, photo_path: str, caption:str | None = None) -> None:
        url = f"{self.base}/sendPhoto"
        with open(photo_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": self.chat_id}
            if caption:
                data["caption"] = caption
            resp = requests.post(url, data=data, files=files, timeout=self.timeout_sec)
            resp.raise_for_status()