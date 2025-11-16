import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from ..core.config import settings

logger = logging.getLogger(__name__)

_ZW_RE = re.compile(r"[\u200B\u200C\u200D\u2060\uFEFF]")

def clean_url(u: str) -> str:
    if not u:
        return ""
    return _ZW_RE.sub("", str(u)).strip().replace("\r", "").replace("\n", "")

def _extract_photos(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = item.get("photos")
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            arr = json.loads(raw)
            return [x for x in arr if isinstance(x, dict)]
        except Exception:
            return []
    if isinstance(raw, list) and raw and isinstance(raw[0], str):
        try:
            arr = json.loads(raw[0])
            return [x for x in arr if isinstance(x, dict)]
        except Exception:
            return []
    if isinstance(raw, list) and all(isinstance(x, dict) for x in raw):
        return raw
    return []

def _absolutize_name(name: str) -> str:
    name = clean_url(name)
    if not name:
        return ""
    if name.startswith("http://"):
        name = "https://" + name[len("http://"):]
    if name.startswith("https://"):
        return name
    base = (getattr(settings, "listings_media_base", "") or "https://re24.com.ua/").rstrip("/") + "/"
    return urljoin(base, name.lstrip("/"))
