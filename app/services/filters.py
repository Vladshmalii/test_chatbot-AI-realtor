from typing import Any, Dict

QUESTION_KEYS = ["district", "price", "rooms", "area", "floor", "condition"]

FILTER_KEY_MAPPING = {
    "district": ["district_id", "microarea_id", "street_id"],
    "price": ["price_min", "price_max"],
    "rooms": ["rooms_in"],
    "area": ["area_min", "area_max"],
    "floor": ["floor_min", "floor_max"],
    "condition": ["condition_in"]
}

def merge_filters(existing: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(existing)
    for key, value in updates.items():
        if isinstance(value, list):
            merged[key] = sorted(set(merged.get(key, []) + value))
        else:
            merged[key] = value
    return merged

def is_complete(filters: Dict[str, Any]) -> bool:
    for question in QUESTION_KEYS:
        keys = FILTER_KEY_MAPPING.get(question, [])
        if not any(key in filters for key in keys):
            return False
    return True

def missing_keys(filters: Dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for question in QUESTION_KEYS:
        keys = FILTER_KEY_MAPPING.get(question, [])
        if not any(key in filters for key in keys):
            missing.append(question)
    return missing
