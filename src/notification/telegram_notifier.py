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

    def _post_with_retry(self, endpoint: str, data=None, files=None):
        """
        Helper to retry requests on failure with 429 handling.
        """
        url = f"{self.base}/{endpoint}"
        
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(url, data=data, files=files, timeout=self.timeout_sec)
                
                if resp.status_code == 429:
                    # Too Many Requests - Respect Retry-After or default to exponential backoff
                    retry_after = int(resp.headers.get("Retry-After", 5))
                    logger.warning(f"[Telegram] Rate limited (429). Waiting {retry_after}s...")
                    time.sleep(retry_after)
                    continue  # Retry
                
                resp.raise_for_status()
                return resp
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"[Telegram] Attempt {attempt}/{self.max_retries} failed: {e}")
                
                if attempt == self.max_retries:
                    logger.error(f"[Telegram] Giving up after {self.max_retries} attempts.")
                    raise e
                
                # Exponential backoff: 2s, 4s, 8s...
                sleep_time = 2 ** attempt
                time.sleep(sleep_time)

    def send_message(self, text: str) -> None:
        data = {"chat_id": self.chat_id, "text": text}
        self._post_with_retry("sendMessage", data=data)

    def send_photo(self, photo_path: str, caption:str | None = None) -> None:
        # We need to re-open the file on each retry if needed, but _post_with_retry 
        # takes a files dict. Requests 'files' param handles file objects.
        # Ideally we open inside the retry loop, but to keep _post_with_retry generic,
        # we can't easily do that without passing a callback.
        # However, for 429s we can reuse the open file handle if we seek(0)?
        # Simpler: just try/catch block here with specific logic or accept that 
        # file read errors are rare compared to network errors.
        
        # Actually, let's keep the file open logic here for safety
        
        url = f"{self.base}/sendPhoto"
        
        for attempt in range(1, self.max_retries + 1):
            try:
                with open(photo_path, "rb") as f:
                    files = {"photo": f}
                    data = {"chat_id": self.chat_id}
                    if caption:
                        data["caption"] = caption
                    
                    resp = requests.post(url, data=data, files=files, timeout=self.timeout_sec)
                    
                    if resp.status_code == 429:
                        retry_after = int(resp.headers.get("Retry-After", 5))
                        logger.warning(f"[Telegram] Rate limited (429). Waiting {retry_after}s...")
                        time.sleep(retry_after)
                        continue
                        
                    resp.raise_for_status()
                    return 
            except (requests.exceptions.RequestException, IOError) as e:
                logger.warning(f"[Telegram] Photo send attempt {attempt} failed: {e}")
                if attempt == self.max_retries:
                    raise e
                time.sleep(2 ** attempt)