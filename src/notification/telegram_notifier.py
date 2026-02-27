import os
import time
import requests
from src.settings.logger import logger


class TelegramNotifier:
    def __init__(
        self,
        token: str,
        chat_id: str,
        timeout_sec: int = 15,
        max_retries: int = 3,
        retry_backoff_base_sec: int = 2,
        retry_after_default_sec: int = 5,
    ):
        self.token = token
        self.chat_id = chat_id
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.retry_backoff_base_sec = retry_backoff_base_sec
        self.retry_after_default_sec = retry_after_default_sec
        self.base = f"https://api.telegram.org/bot{token}"

    @classmethod
    def from_env(
        cls,
        token_env: str = "SPG_TELEGRAM_BOT_TOKEN",
        chat_id_env: str = "SPG_TELEGRAM_CHAT_ID",
        timeout_sec: int = 15,
        max_retries: int = 3,
        retry_backoff_base_sec: int = 2,
        retry_after_default_sec: int = 5,
    ):
        token = os.getenv(token_env, "").strip()
        chat_id = os.getenv(chat_id_env, "").strip()
        if not token or not chat_id:
            raise RuntimeError(f"Missing {token_env} or {chat_id_env} in environment")
        return cls(
            token=token,
            chat_id=chat_id,
            timeout_sec=timeout_sec,
            max_retries=max_retries,
            retry_backoff_base_sec=retry_backoff_base_sec,
            retry_after_default_sec=retry_after_default_sec,
        )

    def _get_retry_after_seconds(self, response: requests.Response) -> int:
        raw = response.headers.get("Retry-After")
        if raw is not None:
            try:
                return max(1, int(raw))
            except (TypeError, ValueError):
                pass
        return self.retry_after_default_sec

    def _get_backoff_seconds(self, attempt: int) -> int:
        return self.retry_backoff_base_sec ** attempt

    def _post_with_retry(self, endpoint: str, data=None, files=None):
        url = f"{self.base}/{endpoint}"

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(url, data=data, files=files, timeout=self.timeout_sec)

                if resp.status_code == 429:
                    retry_after = self._get_retry_after_seconds(resp)
                    logger.warning(f"[Telegram] Rate limited (429). Waiting {retry_after}s...")
                    time.sleep(retry_after)
                    continue

                resp.raise_for_status()
                return resp

            except requests.exceptions.RequestException as e:
                logger.warning(f"[Telegram] Attempt {attempt}/{self.max_retries} failed: {e}")

                if attempt == self.max_retries:
                    logger.error(f"[Telegram] Giving up after {self.max_retries} attempts.")
                    raise e

                sleep_time = self._get_backoff_seconds(attempt)
                time.sleep(sleep_time)

    def send_message(self, text: str) -> None:
        data = {"chat_id": self.chat_id, "text": text}
        self._post_with_retry("sendMessage", data=data)

    def send_photo(self, photo_path: str, caption: str | None = None) -> None:
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
                        retry_after = self._get_retry_after_seconds(resp)
                        logger.warning(f"[Telegram] Rate limited (429). Waiting {retry_after}s...")
                        time.sleep(retry_after)
                        continue

                    resp.raise_for_status()
                    return
            except (requests.exceptions.RequestException, IOError) as e:
                logger.warning(f"[Telegram] Photo send attempt {attempt} failed: {e}")
                if attempt == self.max_retries:
                    raise e
                time.sleep(self._get_backoff_seconds(attempt))
