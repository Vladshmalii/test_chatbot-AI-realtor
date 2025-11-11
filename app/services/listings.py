from typing import Any, Dict, List

def render_cards(response: Dict[str, Any]) -> List[str]:
    listings = response.get("data") or []
    cards: List[str] = []
    for item in listings[:3]:
        title = item.get("title") or "Квартира"
        price = item.get("price")
        address = item.get("address")
        area = item.get("area_total")
        rooms = item.get("rooms")
        link = item.get("url")
        parts = [title]
        if price:
            parts.append(f"Ціна: {price}")
        if address:
            parts.append(f"Адреса: {address}")
        if area:
            parts.append(f"Площа: {area}")
        if rooms:
            parts.append(f"Кімнат: {rooms}")
        if link:
            parts.append(link)
        cards.append("\n".join(parts))
    return cards

def extra_offers_message(total: int) -> str:
    if total <= 3:
        return "Маю більше варіантів за вашими параметрами, дайте знати якщо цікаво."
    remaining = max(total - 3, 0)
    return f"Ще {remaining} пропозицій за вашими фільтрами, готовий поділитись після дзвінка."
