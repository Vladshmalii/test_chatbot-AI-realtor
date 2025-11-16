import re
from typing import Any, Dict, List, Tuple, Optional
from .sheets import sheets_client
import logging

logger = logging.getLogger(__name__)
_WORDS_RE = re.compile(r"[^\w\u0400-\u04FF]+", flags=re.UNICODE)


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.replace("і", "и").replace("ї", "и").replace("є", "е").replace("ґ", "г")
    s = _WORDS_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _ints(text: str) -> List[int]:
    return [int(x) for x in re.findall(r"\d+", (text or "").replace("\u00a0", ""))]


_LOCATION_SYNONYMS: Dict[str, Dict[str, int]] = {"district": {}, "microarea": {}, "street": {}}
_LOCATION_NAMES: Dict[str, Dict[int, str]] = {"district": {}, "microarea": {}, "street": {}}
_CONDITION_BY_LABEL: Dict[str, set] = {}
_CONDITION_SYNONYM_TO_LABEL: Dict[str, str] = {}
_CONDITION_ID_BY_LABEL: Dict[str, int] = {}
_FILTER_PATTERNS: Dict[str, List[Dict[str, Any]]] = {}


def _load_locations() -> Tuple[Dict[str, Dict[str, int]], Dict[str, Dict[int, str]]]:
    rows = sheets_client.fetch_records("districts")
    syn: Dict[str, Dict[str, int]] = {"district": {}, "microarea": {}, "street": {}}
    names: Dict[str, Dict[int, str]] = {"district": {}, "microarea": {}, "street": {}}

    for r in rows:
        location_type = str(r.get("type") or "").strip().lower()
        synonym = str(r.get("synonym") or "").strip()
        official_name = str(r.get("official_name") or "").strip()

        try:
            target_id = int(r.get("target_id")) if r.get("target_id") not in (None, "") else None
        except (ValueError, TypeError):
            target_id = None

        if location_type in syn and synonym and target_id:
            normalized_key = _norm(synonym)
            if normalized_key:
                syn[location_type][normalized_key] = target_id
                if official_name:
                    names[location_type][target_id] = official_name

    return syn, names


def _load_conditions() -> Tuple[Dict[str, set], Dict[str, str], Dict[str, int]]:
    rows = sheets_client.dictionaries()
    by_label: Dict[str, set] = {}
    syn_to_label: Dict[str, str] = {}
    id_by_label: Dict[str, int] = {}

    for r in rows:
        label = str(r.get("label") or "").strip()
        synonyms_str = str(r.get("synonyms") or "").strip()

        try:
            condition_id = int(r.get("id"))
        except (ValueError, TypeError):
            condition_id = None

        if not label or not condition_id:
            continue

        normalized_label = _norm(label)

        if normalized_label not in by_label:
            by_label[normalized_label] = set()

        by_label[normalized_label].add(normalized_label)
        syn_to_label[normalized_label] = label
        id_by_label[label] = condition_id

        if synonyms_str:
            for synonym in synonyms_str.split(";"):
                synonym = synonym.strip()
                if synonym:
                    normalized_syn = _norm(synonym)
                    if normalized_syn:
                        by_label[normalized_label].add(normalized_syn)
                        syn_to_label[normalized_syn] = label

    return by_label, syn_to_label, id_by_label


def _load_filter_patterns() -> Dict[str, List[Dict[str, Any]]]:
    patterns: Dict[str, List[Dict[str, Any]]] = {}
    try:
        rows = sheets_client.filter_patterns()
        for row in rows:
            filter_key = str(row.get("filter_key", "")).strip().lower()
            pattern_type = str(row.get("pattern_type", "")).strip().lower()
            pattern_text = str(row.get("pattern_text", "")).strip()

            value_min = row.get("value_min")
            value_max = row.get("value_max")
            value_list = row.get("value_list")

            if value_min == "" or value_min is None:
                value_min = None
            else:
                try:
                    value_min = int(value_min)
                except:
                    value_min = None

            if value_max == "" or value_max is None:
                value_max = None
            else:
                try:
                    value_max = int(value_max)
                except:
                    value_max = None

            if value_list and value_list != "":
                if str(value_list).upper() == "LAST":
                    value_list = "LAST"
                else:
                    try:
                        value_list = int(value_list)
                    except:
                        value_list = None
            else:
                value_list = None

            if filter_key not in patterns:
                patterns[filter_key] = []

            patterns[filter_key].append({
                "type": pattern_type,
                "text": pattern_text,
                "min": value_min,
                "max": value_max,
                "list": value_list
            })
    except Exception as e:
        logger.error(f"Failed to load filter_patterns: {e}", exc_info=True)

    return patterns


def reload_lookups() -> None:
    global _LOCATION_SYNONYMS, _LOCATION_NAMES, _CONDITION_BY_LABEL, _CONDITION_SYNONYM_TO_LABEL, _CONDITION_ID_BY_LABEL, _FILTER_PATTERNS
    _LOCATION_SYNONYMS, _LOCATION_NAMES = _load_locations()
    _CONDITION_BY_LABEL, _CONDITION_SYNONYM_TO_LABEL, _CONDITION_ID_BY_LABEL = _load_conditions()
    _FILTER_PATTERNS = _load_filter_patterns()
    logger.info(f"[LLM] Loaded {len(_FILTER_PATTERNS)} filter pattern keys")


reload_lookups()


def _match_condition_labels(text: str) -> List[str]:
    normalized = _norm(text)
    tokens = f" {normalized} "
    matched_labels: List[str] = []

    for normalized_label, synonyms in _CONDITION_BY_LABEL.items():
        for synonym in synonyms:
            if f" {synonym} " in tokens:
                label = _CONDITION_SYNONYM_TO_LABEL.get(synonym) or _CONDITION_SYNONYM_TO_LABEL.get(normalized_label)
                if label and label not in matched_labels:
                    matched_labels.append(label)
                break

    return matched_labels


def _stem(word: str) -> str:
    if len(word) <= 3:
        return word

    endings = [
        'ого', 'ому', 'ими', 'ыми', 'ому', 'ого', 'ой', 'ый', 'ий', 'ас', 'яс', 'ое', 'ее',
        'ом', 'ою', 'ам', 'ами', 'ах', 'ів', 'ов', 'ей', 'ям', 'ями', 'ях',
        'а', 'у', 'ю', 'о', 'е', 'і', 'и', 'ь', 'ї'
    ]

    for ending in sorted(endings, key=len, reverse=True):
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[:-len(ending)]

    return word


def _match_single_location(text: str) -> Dict[str, Any]:
    normalized = _norm(text)
    result = {"district_id": [], "microarea_id": [], "street_id": []}

    street_id = _LOCATION_SYNONYMS["street"].get(normalized)
    if street_id:
        result["street_id"].append(street_id)
        return result

    words = normalized.split()
    for word in words:
        stemmed_word = _stem(word)

        for syn_key, syn_id in _LOCATION_SYNONYMS["street"].items():
            if _stem(syn_key) == stemmed_word:
                if syn_id not in result["street_id"]:
                    result["street_id"].append(syn_id)
                break

        for syn_key, syn_id in _LOCATION_SYNONYMS["microarea"].items():
            if _stem(syn_key) == stemmed_word:
                if syn_id not in result["microarea_id"]:
                    result["microarea_id"].append(syn_id)
                break

        for syn_key, syn_id in _LOCATION_SYNONYMS["district"].items():
            if _stem(syn_key) == stemmed_word:
                if syn_id not in result["district_id"]:
                    result["district_id"].append(syn_id)
                break

    return result


def _match_locations(text: str) -> Dict[str, Any]:
    parts = [part.strip() for part in re.split(r"[;,]", text) if part.strip()]

    enhanced_parts = []
    last_base_name = None

    for part in parts:
        if re.match(r'^\d+-?(й|и|ий|ый|і)$', part.strip(), re.IGNORECASE):
            if last_base_name:
                enhanced_parts.append(f"{last_base_name} {part}")
            else:
                enhanced_parts.append(part)
        else:
            enhanced_parts.append(part)
            match = re.match(r'(.+?)\s+\d+-?(й|и|ий|ый|і)$', part, re.IGNORECASE)
            if match:
                last_base_name = match.group(1)
            else:
                last_base_name = part

    combined_result = {"district_id": [], "microarea_id": [], "street_id": []}

    for part in enhanced_parts:
        part_result = _match_single_location(part)

        for key in ("district_id", "microarea_id", "street_id"):
            for item in part_result[key]:
                if item not in combined_result[key]:
                    combined_result[key].append(item)

    if combined_result["street_id"]:
        return {
            "street_id": combined_result["street_id"],
            "explicit_street": True,
            "district_id": [],
            "microarea_id": []
        }

    return combined_result


def _apply_pattern_match(key: str, answer: str) -> Optional[Dict[str, Any]]:
    if key not in _FILTER_PATTERNS:
        return None

    lower_answer = answer.lower()
    logger.info(f"[PATTERN] key={key}, checking patterns: {len(_FILTER_PATTERNS[key])}")

    for pattern in _FILTER_PATTERNS[key]:
        pattern_type = pattern["type"]
        pattern_text = pattern["text"]
        keywords = [kw.strip().lower() for kw in pattern_text.split(",") if kw.strip()]

        logger.info(f"[PATTERN] type={pattern_type}, keywords={keywords[:3]}...")

        matched = False
        if pattern_type == "word":
            normalized = _norm(answer)
            for keyword in keywords:
                if _norm(keyword) in normalized.split():
                    matched = True
                    break
        elif pattern_type == "phrase":
            for keyword in keywords:
                if keyword in lower_answer:
                    matched = True
                    break
        elif pattern_type == "skip":
            for keyword in keywords:
                if keyword in lower_answer:
                    return {}
        elif pattern_type == "special":
            for keyword in keywords:
                logger.info(f"[PATTERN] Checking special keyword '{keyword}' in '{lower_answer}'")
                if keyword in lower_answer:
                    matched = True
                    logger.info(f"[PATTERN] MATCHED special: {keyword}")
                    break

        if matched:
            result = {}

            if key == "rooms" and pattern["list"] is not None:
                result["rooms_in"] = [pattern["list"]]
            elif key == "floor":
                if pattern.get("list") == "LAST":
                    result["floor_only_last"] = True
                elif pattern["min"] is not None or pattern["max"] is not None:
                    if pattern["min"] is not None:
                        result["floor_min"] = pattern["min"]
                    if pattern["max"] is not None:
                        result["floor_max"] = pattern["max"]
            elif key == "area":
                if pattern["min"] is not None:
                    result["area_min"] = pattern["min"]
                if pattern["max"] is not None:
                    result["area_max"] = pattern["max"]
            elif key == "price":
                if pattern["min"] is not None:
                    result["price_min"] = pattern["min"]
                if pattern["max"] is not None:
                    result["price_max"] = pattern["max"]

            logger.info(f"[PATTERN] RESULT for key={key}: {result}")
            return result

    return None

def parse_to_filters(key: str, answer: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    lower_answer = answer.lower()

    pattern_result = _apply_pattern_match(key, answer)
    if pattern_result is not None:
        logger.info(f"[PARSE] Pattern matched for {key}: {pattern_result}")
        return pattern_result

    if key in ("price", "budget"):
        numbers = [x for x in _ints(answer) if x > 1000]

        if len(numbers) == 1:
            num = numbers[0]
            if any(word in lower_answer for word in ["до", "максимум", "не більше", "не больше", "макс"]):
                result["price_max"] = num
                result["price_min"] = None
            elif any(word in lower_answer for word in
                     ["від", "от", "мінімум", "минимум", "не менше", "не меньше", "мін", "мин"]):
                result["price_min"] = num
                result["price_max"] = None
            else:
                result["price_max"] = num
                result["price_min"] = None
        elif len(numbers) > 1:
            result["price_min"] = min(numbers)
            result["price_max"] = max(numbers)
        return result

    if key == "rooms":
        numbers = [x for x in _ints(answer) if 0 < x < 8]
        lower_text = lower_answer

        filtered_rooms = []
        for num in numbers:
            if re.search(rf'\b{num}-(й|я|і|ий|ій|ый|ой|ая|яя|є|ої|го|му)\b', lower_text, re.IGNORECASE):
                continue

            pattern = rf'\b{num}\b.{{0,20}}(кімнат|комнат|кімн|комн|к\b)'
            if re.search(pattern, lower_text, re.IGNORECASE):
                filtered_rooms.append(num)

        if filtered_rooms:
            result["rooms_in"] = filtered_rooms
        elif numbers and not any(word in lower_text for word in ["етаж", "этаж", "пов"]):
            if len(numbers) == 2 and any(word in lower_text for word in ["від", "от", "до"]):
                min_rooms = min(numbers)
                max_rooms = max(numbers)
                result["rooms_in"] = list(range(min_rooms, max_rooms + 1))
            else:
                result["rooms_in"] = numbers
        return result

    if key == "area":
        numbers = [x for x in _ints(answer) if 15 <= x <= 500]

        if len(numbers) == 1:
            num = numbers[0]
            num_str = str(num)

            has_min_local = re.search(
                rf"(від|от|мінімум|минимум|не менше|не меньше|мін|мин)\s*{num_str}(?:\s*(м|м2|м²|кв|кв\.м|квм))?",
                lower_answer
            )
            has_max_local = re.search(
                rf"(до|максимум|не більше|не больше|макс)\s*{num_str}(?:\s*(м|м2|м²|кв|кв\.м|квм))?",
                lower_answer
            )

            if has_min_local:
                result["area_min"] = num
                result["area_max"] = None
            elif has_max_local:
                result["area_max"] = num
                result["area_min"] = None
            else:
                result["area_min"] = num
                result["area_max"] = None

        elif len(numbers) > 1:
            result["area_min"] = min(numbers)
            result["area_max"] = max(numbers)

        return result

    if key == "floor":
        lower_text = lower_answer

        if re.search(r'(\d+)\s*-\s*(\d+)', lower_text):
            match = re.search(r'(\d+)\s*-\s*(\d+)', lower_text)
            min_floor = int(match.group(1))
            max_floor = int(match.group(2))
            if 1 <= min_floor <= 50 and 1 <= max_floor <= 50:
                result["floor_min"] = min_floor
                result["floor_max"] = max_floor
                return result

        numbers = [x for x in _ints(answer) if 1 <= x <= 50]

        filtered_floors = []
        for num in numbers:
            pattern = rf'\b{num}\b.{{0,20}}(етаж|этаж|пов)'
            if re.search(pattern, lower_answer, re.IGNORECASE):
                filtered_floors.append(num)

        if not filtered_floors and len(numbers) == 1:
            filtered_floors = numbers

        if len(filtered_floors) == 1:
            num = filtered_floors[0]
            if any(word in lower_answer for word in ["до", "максимум", "не більше", "не больше", "макс"]):
                result["floor_min"] = 1
                result["floor_max"] = num
            elif any(word in lower_answer for word in
                     ["від", "от", "мінімум", "минимум", "не менше", "не меньше", "мін", "мин"]):
                result["floor_min"] = num
                result["floor_max"] = 50
            else:
                result["floor_min"] = num
                result["floor_max"] = num
        elif len(filtered_floors) > 1:
            result["floor_min"] = min(filtered_floors)
            result["floor_max"] = max(filtered_floors)
        return result

    if key in ("floors_total", "building_floors"):
        numbers = [x for x in _ints(answer) if 1 <= x <= 30]

        if len(numbers) == 1:
            num = numbers[0]
            if any(word in lower_answer for word in ["до", "максимум", "не більше", "не больше", "макс"]):
                result["floors_total_min"] = 1
                result["floors_total_max"] = num
            elif any(word in lower_answer for word in
                     ["від", "от", "мінімум", "минимум", "не менше", "не меньше", "мін", "мин"]):
                result["floors_total_min"] = num
                result["floors_total_max"] = 30
            else:
                result["floors_total_min"] = num
                result["floors_total_max"] = num
        elif len(numbers) > 1:
            result["floors_total_min"] = min(numbers)
            result["floors_total_max"] = max(numbers)
        return result

    if key in ("condition", "state"):
        labels = _match_condition_labels(answer)
        if labels:
            condition_ids = [_CONDITION_ID_BY_LABEL[label] for label in labels if label in _CONDITION_ID_BY_LABEL]
            if condition_ids:
                result["condition_in"] = condition_ids
        return result

    if key == "section":
        from .section_parser import detect_section
        section = detect_section(answer)
        if section:
            result["section"] = section
        return result

    if key == "district":
        return _match_locations(answer)

    return result


def _title_from_id(kind: str, location_id: int) -> str:
    name = _LOCATION_NAMES.get(kind, {}).get(location_id)
    return name if name else f"{kind} #{location_id}"


def build_summary(filters: Dict[str, Any]) -> str:
    parts: List[str] = []

    if filters.get("district_id"):
        names = [_title_from_id("district", i) for i in filters["district_id"]]
        parts.append(f"Район: {', '.join(names)}")

    if filters.get("microarea_id"):
        names = [_title_from_id("microarea", i) for i in filters["microarea_id"]]
        parts.append(f"Мікрорайон: {', '.join(names)}")

    if filters.get("street_id"):
        names = [_title_from_id("street", i) for i in filters["street_id"]]
        parts.append(f"Вулиця: {', '.join(names)}")

    if filters.get("rooms_in"):
        parts.append(f"Кімнати: {', '.join(map(str, filters['rooms_in']))}")

    price_min = filters.get("price_min")
    price_max = filters.get("price_max")
    if price_min and price_max:
        parts.append(f"Бюджет: {price_min}-{price_max} грн")
    elif price_max:
        parts.append(f"Бюджет до {price_max} грн")
    elif price_min:
        parts.append(f"Бюджет від {price_min} грн")

    area_min = filters.get("area_min")
    area_max = filters.get("area_max")
    if area_min and area_max:
        parts.append(f"Площа: {area_min}-{area_max} м²")
    elif area_max:
        parts.append(f"Площа до {area_max} м²")
    elif area_min:
        parts.append(f"Площа від {area_min} м²")

    floor_min = filters.get("floor_min")
    floor_max = filters.get("floor_max")
    if floor_min is not None or floor_max is not None:
        if floor_min == floor_max and floor_min is not None:
            parts.append(f"Поверх: {floor_min}")
        elif floor_min and floor_max:
            parts.append(f"Поверх: {floor_min}-{floor_max}")
        elif floor_min:
            parts.append(f"Поверх: від {floor_min}")
        elif floor_max:
            parts.append(f"Поверх: до {floor_max}")

    floors_total_min = filters.get("floors_total_min")
    floors_total_max = filters.get("floors_total_max")
    if floors_total_min is not None or floors_total_max is not None:
        if floors_total_min == floors_total_max and floors_total_min is not None:
            parts.append(f"Поверховість будинку: {floors_total_min}")
        elif floors_total_min and floors_total_max:
            parts.append(f"Поверховість будинку: {floors_total_min}-{floors_total_max}")
        elif floors_total_min:
            parts.append(f"Поверховість будинку: від {floors_total_min}")
        elif floors_total_max:
            parts.append(f"Поверховість будинку: до {floors_total_max}")

    if filters.get("condition_label_in"):
        parts.append(f"Стан: {', '.join(filters['condition_label_in'])}")

    return "\n".join(parts) if parts else "Параметри не задані"