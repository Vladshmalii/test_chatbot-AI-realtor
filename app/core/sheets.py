import time
from typing import Any, Dict, List, Optional
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from .config import settings


class SheetsClient:
    def __init__(self, cache_ttl: int = 300) -> None:
        self._client: Optional[gspread.Client] = None
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = cache_ttl

    @property
    def client(self) -> gspread.Client:
        if self._client is None:
            creds = Credentials.from_service_account_file(
                settings.google_service_account_file,
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive",
                ],
            )
            self._client = gspread.authorize(creds)
        return self._client

    def fetch_records(self, sheet_name: str) -> List[Dict[str, Any]]:
        key = sheet_name
        now = time.time()
        cached = self._cache.get(key)
        if cached and now - cached["ts"] < self._cache_ttl:
            return cached["data"]
        sheet = self.client.open_by_key(settings.google_spreadsheet_id)
        ws = sheet.worksheet(sheet_name)
        records = ws.get_all_records()
        self._cache[key] = {"data": records, "ts": now}
        return records

    def welcome(self) -> List[Dict[str, Any]]:
        return self.fetch_records("weclome_messages")

    def objections(self) -> List[Dict[str, Any]]:
        return self.fetch_records("objections")

    def reactions(self) -> List[Dict[str, Any]]:
        return self.fetch_records("reactions")

    def districts(self) -> List[Dict[str, Any]]:
        return self.fetch_records("districts")

    def analytics(self) -> List[Dict[str, Any]]:
        return self.fetch_records("analytics")

    def dictionaries(self) -> List[Dict[str, Any]]:
        return self.fetch_records("dictionaries")

    def questions(self) -> List[Dict[str, Any]]:
        return self.fetch_records("questions")

    def sections(self) -> List[Dict[str, Any]]:
        return self.fetch_records("sections")

    def filter_patterns(self) -> List[Dict[str, Any]]:
        return self.fetch_records("filter_patterns")

    def write_analytics(
        self,
        user_id: int,
        username: str,
        language: str,
        started_at: datetime,
        last_action: str,
        lead: bool,
        avg_budget: Optional[int],
        reason_decline: str,
        response_time: Optional[int]
    ) -> None:
        sheet = self.client.open_by_key(settings.google_spreadsheet_id)
        ws = sheet.worksheet("analytics")
        row = [
            user_id,
            username or "",
            language,
            started_at.strftime("%Y-%m-%d %H:%M:%S"),
            last_action,
            "Yes" if lead else "No",
            avg_budget or "",
            reason_decline or "",
            response_time or ""
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")

    def write_viewing_request(
            self,
            user_id: int,
            username: str,
            phone: str,
            name: str,
            listings: List[Dict[str, Any]],
            filters: Dict[str, Any]
    ) -> None:
        from ..core.llm import build_summary

        sheet = self.client.open_by_key(settings.google_spreadsheet_id)
        ws = sheet.worksheet("viewings")

        listing_ids = []
        apartments_info = []

        for item in listings:
            listing_id = item.get("id")
            if listing_id:
                listing_ids.append(str(listing_id))

            addr = item.get("address") or {}
            street = addr.get("street") or ""
            house = addr.get("house") or ""
            micro = addr.get("microarea") or ""
            rooms = item.get("rooms") or ""
            area = item.get("area_total") or ""
            floor = item.get("floor") or ""
            floors_total = item.get("floors_total") or ""
            price = (item.get("prices") or {}).get("value") or ""

            location = f"{street}, {house}" if street and house else micro
            details = []
            if rooms:
                details.append(f"{rooms}к")
            if area:
                try:
                    a = float(area)
                    details.append(f"{int(a) if a.is_integer() else a}м²")
                except:
                    pass
            if floor and floors_total:
                details.append(f"{floor}/{floors_total}п")
            if price:
                try:
                    details.append(f"{int(float(price)):,}".replace(",", " "))
                except:
                    pass

            apartment_str = f"{location} ({', '.join(details)})" if details else location
            apartments_info.append(apartment_str)

        listing_ids_str = ", ".join(listing_ids) if listing_ids else ""
        apartments_text = " | ".join(apartments_info) if apartments_info else ""
        filters_str = build_summary(filters)

        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            user_id,
            username or "",
            phone or "",
            name or "",
            listing_ids_str,
            apartments_text,
            filters_str
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")


    def welcome_messages_dict(self) -> Dict[str, str]:
        rows = self.welcome()
        out: Dict[str, str] = {}
        for r in rows:
            k = str(r.get("key", "")).strip().lower()
            t = str(r.get("text", "")).strip()
            if k and t:
                out[k] = t
        return out

    def bot_messages_dict(self) -> Dict[str, str]:
        rows = self.fetch_records("bot_messages")
        out: Dict[str, str] = {}
        for r in rows:
            k = str(r.get("key", "")).strip().lower()
            t = str(r.get("text", "")).strip()
            if k and t:
                out[k] = t
        return out


sheets_client = SheetsClient(cache_ttl=settings.sheets_cache_ttl)
