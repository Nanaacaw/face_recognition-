import os
import time
import requests
from src.settings.logger import logger

class TelegramNotifier:
    def __init__(self, token:str, chat_id: str, timeout_sec: int = 15, max_retries: int = 3):
        self.token = token
        self.chat_id = chat_id
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.base = f"https://api.telegram.org/bot{token}"

    @classmethod
    def from_env(cls):
        token = os.getenv("SPG_TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("SPG_TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            raise RuntimeError("Missing SPG_TELEGRAM_BOT_TOKEN or SPG_TELEGRAM_CHAT_ID in environment")
        return cls(token=token, chat_id=chat_id)

    def _post_with_retry(self, url, data=None, files=None):
        """Helper to retry requests on failure."""
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(url, data=data, files=files, timeout=self.timeout_sec)
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                logger.warning(f"[Telegram] Attempt {attempt}/{self.max_retries} failed: {e}")
                if attempt == self.max_retries:
                    logger.error(f"[Telegram] Giving up after {self.max_retries} attempts.")
                    raise e
                time.sleep(2 * attempt) 

    def send_message(self, text: str) -> None:
        url = f"{self.base}/sendMessage"
        data = {"chat_id": self.chat_id, "text": text}
        for attempt in range(1, self.max_retries + 1):
            try:
                requests.post(url, data=data, timeout=self.timeout_sec).raise_for_status()
                return
            except requests.exceptions.RequestException as e:
                logger.warning(f"[Telegram] Msg attempt {attempt} failed: {e}")
                if attempt == self.max_retries:
                    raise e
                time.sleep(2 * attempt)

    def send_photo(self, photo_path: str, caption:str | None = None) -> None:
        url = f"{self.base}/sendPhoto"
        
        # Simple retry loop that handles file re-opening
        for attempt in range(1, self.max_retries + 1):
            try:
                with open(photo_path, "rb") as f:
                    files = {"photo": f}
                    data = {"chat_id": self.chat_id}
                    if caption:
                        data["caption"] = caption
                    
                    requests.post(url, data=data, files=files, timeout=self.timeout_sec).raise_for_status()
                    return # Success
            except (requests.exceptions.RequestException, IOError) as e:
                logger.warning(f"[Telegram] Photo send attempt {attempt} failed: {e}")
                if attempt == self.max_retries:
                    raise e
                time.sleep(2 * attempt)