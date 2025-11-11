import json
import time
from typing import Any, Dict, List
import gspread
from gspread.client import Client
from .config import settings

class SheetsClient:
    def __init__(self) -> None:
        self._client: Client | None = None
        self._cache: Dict[str, tuple[float, Any]] = {}

    @property
    def client(self) -> Client:
        if self._client is None:
            credentials = json.loads(settings.google_service_account_json)
            self._client = gspread.service_account_from_dict(credentials)
        return self._client

    def fetch_records(self, worksheet: str) -> List[Dict[str, Any]]:
        cached = self._cache.get(worksheet)
        now = time.time()
        if cached and now - cached[0] < settings.cache_ttl_seconds:
            return cached[1]
        sheet = self.client.open_by_key(settings.google_spreadsheet_id)
        data = sheet.worksheet(worksheet).get_all_records()
        self._cache[worksheet] = (now, data)
        return data

    def welcome_messages(self) -> List[str]:
        records = self.fetch_records("Welcome")
        return [record.get("text") for record in records if record.get("text")]

    def questions(self) -> List[Dict[str, Any]]:
        records = self.fetch_records("Questions")
        result: List[Dict[str, Any]] = []
        for record in records:
            key = record.get("key")
            text = record.get("text")
            if key and text:
                result.append({"key": key, "text": text})
        return result

    def objections(self) -> Dict[str, str]:
        records = self.fetch_records("Objections")
        data: Dict[str, str] = {}
        for record in records:
            trigger = record.get("trigger")
            reply = record.get("reply")
            if trigger and reply:
                data[trigger.lower()] = reply
        return data

    def reactions(self) -> Dict[str, str]:
        records = self.fetch_records("Reactions")
        data: Dict[str, str] = {}
        for record in records:
            trigger = record.get("trigger")
            reply = record.get("reply")
            if trigger and reply:
                data[trigger.lower()] = reply
        return data

sheets_client = SheetsClient()
