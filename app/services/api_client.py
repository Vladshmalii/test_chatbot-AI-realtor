from typing import Any, Dict
import aiohttp
import logging
from ..core.config import settings

logger = logging.getLogger(__name__)


async def fetch_listings(filters: Dict[str, Any]) -> Dict[str, Any]:
    payload = {k: v for k, v in filters.items() if v not in (None, [], "", 0, False)}
    payload["key"] = settings.listings_api_key
    # payload["section"] = "rent"
    payload.setdefault("limit", settings.listings_limit)
    payload.setdefault("offset", settings.listings_offset)
    payload.setdefault("sort", "newest")

    url = settings.listings_api_url
    logger.info(f"[API] POST {url}")
    logger.info(f"[API] Payload: {payload}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=30) as response:
                text = await response.text()

                logger.info(f"[API] Response status: {response.status}")
                logger.info(f"[API] Response text: {text[:1000]}")  # ← ДОБАВЬ

                if response.status != 200:
                    return {"data": [], "total": 0, "status": None, "message": text}

                try:
                    raw = await response.json()
                    logger.info(f"[API] Response JSON: {raw}")  # ← ДОБАВЬ
                except Exception:
                    return {"data": [], "total": 0, "status": None, "message": text}

                items = raw.get("items") or raw.get("data") or []
                total = raw.get("count") or raw.get("total") or len(items)

                logger.info(f"[API] Found {len(items)} items, total: {total}")  # ← ДОБАВЬ

                return {
                    "data": items,
                    "total": total if isinstance(total, int) else len(items),
                    "status": raw.get("status"),
                    "message": raw.get("message"),
                }
    except Exception as e:
        logger.error(f"[API] Error: {e}", exc_info=True)
        return {"data": [], "total": 0, "status": None, "message": str(e)}
