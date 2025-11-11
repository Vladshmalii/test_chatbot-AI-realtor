from typing import Any, Dict
import requests
from ..core.config import settings

def fetch_listings(filters: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(filters)
    payload["key"] = settings.listings_api_key
    payload["limit"] = settings.listings_limit
    payload["offset"] = settings.default_offset
    response = requests.post(settings.listings_api_url, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()
