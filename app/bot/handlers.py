import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove, KeyboardButton, ReplyKeyboardMarkup, InputMediaPhoto
from sqlalchemy import select, delete
from ..core.llm import parse_to_filters, _ints
from ..core.questions import question_flow
from ..core.section_parser import detect_section
from ..db import crud
from ..db.base import session_scope
from ..db import models
from ..services.api_client import fetch_listings
from .states import RealtorState
from ..core.sheets import sheets_client
from ..core.rules import rule_engine

logger = logging.getLogger(__name__)
router = Router()

WELCOME = sheets_client.welcome_messages_dict()
BOT_MESSAGES = sheets_client.bot_messages_dict()
QUESTIONS_TEXT = (
    f"{WELCOME.get('greeting', '').strip()}\n\n"
    f"{WELCOME.get('instructions', '').strip()}\n\n"
    f"{WELCOME.get('example', '').strip()}"
).strip()

PENDING_KEY_ALLOWED_FILTERS = {
    "district": {"street_id", "microarea_id", "district_id", "explicit_street"},
    "location": {"street_id", "microarea_id", "district_id", "explicit_street"},
    "region": {"street_id", "microarea_id", "district_id", "explicit_street"},
    "rooms": {"rooms_in"},
    "floor": {"floor_min", "floor_max"},
    "floors_total": {"floors_total_min", "floors_total_max"},
    "building_floors": {"floors_total_min", "floors_total_max"},
    "price": {"price_min", "price_max"},
    "budget": {"price_min", "price_max"},
    "area": {"area_min", "area_max"},
    "condition": {"condition_in"},
    "state": {"condition_in"},
    "sort": {"sort"},
}


async def update_last_activity(state: FSMContext):
    await state.update_data(last_activity=time.time())


def extract_name_from_text(text: str) -> tuple[str | None, str]:
    patterns = [
        r'^([А-ЯЁІЇЄҐа-яёіїєґA-Za-z]{2,20}),\s*(.+)',
        r'^(?:мене звуть|меня зовут|я)\s+([А-ЯЁІЇЄҐа-яёіїєґA-Za-z]{2,20})(?:,|\s)+(.+)',
        r'^([А-ЯЁІЇЄҐа-яёіїєґA-Za-z]{2,20})\s*[–-]\s*(.+)',
    ]

    text = text.strip()

    for pattern in patterns:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip().capitalize()
            rest = match.group(2).strip()
            return name, rest

    return None, text


async def log_agent_message(dialog_id: int, content: str) -> None:
    async with session_scope() as session:
        dialog = await session.get(models.Dialog, dialog_id)
        if dialog:
            await crud.append_message(session, dialog, "agent", content)


async def log_user_text(message: Message) -> None:
    async with session_scope() as session:
        u = message.from_user
        user = await crud.get_or_create_user(session, u.id, u.username, u.first_name, u.last_name)
        dialog = await crud.get_active_dialog(session, user)
        await crud.append_message(session, dialog, "user", message.text or "")


async def send_message(message: Message, dialog_id: int, text: str, reply_markup=None) -> None:
    await message.answer(str(text), reply_markup=reply_markup)
    await log_agent_message(dialog_id, str(text))


def contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📞 Поділитись контактом", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def render_listing_caption(item: dict, index: int) -> str:
    title = item.get("title") or "Квартира"
    addr = item.get("address") or {}
    street = addr.get("street")
    house = addr.get("house")
    micro = addr.get("microarea")
    rooms = item.get("rooms")
    area = item.get("area_total")
    floor = item.get("floor")
    floors_total = item.get("floors_total")
    cond = item.get("condition")
    price = (item.get("prices") or {}).get("value")

    caption = f"<b>#{index}</b>\n\n"

    if price:
        try:
            caption += f"<b>💰 {int(float(price)):,}</b>\n".replace(",", " ")
        except Exception:
            caption += f"<b>💰 {price} </b>\n"

    caption += f"<b>{title}</b>\n"

    meta = []
    if rooms:
        meta.append(f"{rooms} кімн.")
    if area:
        try:
            a = float(area)
            meta.append(f"{int(a) if a.is_integer() else a} м²")
        except Exception:
            pass
    if floor and floors_total:
        meta.append(f"{floor}/{floors_total} пов.")
    if cond:
        meta.append(str(cond))

    if meta:
        caption += " • ".join(meta) + "\n"

    addr_parts = [p for p in [micro, street, house] if p]
    if addr_parts:
        caption += "📍 " + " ".join(addr_parts)

    desc = (item.get("description") or "").strip()
    if desc:
        desc = re.sub(r"\bID\s*\d+\b", "", desc)
        desc = desc.replace("\n", " ").strip()
        if len(desc) > 900:
            desc = desc[:900].rstrip() + "…"
        caption += f"\n\n{desc}"

    return caption.strip()


def extract_photos(item: dict) -> List[str]:
    from urllib.parse import urlsplit, urlunsplit, quote
    BASE_MEDIA = "https://re24.com.ua/"

    def strip_control(s: str) -> str:
        return "".join(ch for ch in str(s) if ch.isprintable()).replace("\\", "/").strip().strip('"').strip("'")

    def ensure_absolute(url: str) -> str:
        url = strip_control(url)
        if not url:
            return ""
        if url.startswith(("http://", "https://")):
            return url
        return BASE_MEDIA.rstrip("/") + "/" + url.lstrip("/")

    def clean_url_format(url: str) -> str:
        url = ensure_absolute(url)
        try:
            parts = urlsplit(url)
            scheme = "https" if parts.scheme in ("", "http", "https") else parts.scheme
            netloc = parts.netloc or urlsplit(BASE_MEDIA).netloc
            path = quote(parts.path.replace("//", "/"), safe="/._-")
            query = quote(parts.query, safe="=&._-")
            return urlunsplit((scheme, netloc, path, query, ""))
        except Exception:
            return ""

    def is_valid_image(url: str) -> bool:
        return url.lower().startswith(("http://", "https://")) and url.lower().endswith(
            (".jpg", ".jpeg", ".png", ".webp"))

    def extract_from_dict(obj: dict) -> str:
        for key in ("url", "name", "mini", "src", "href"):
            if key in obj and obj[key]:
                return str(obj[key])
        return ""

    def parse_nested_structure(data) -> list:
        result = []

        def flatten(obj):
            if obj is None:
                return []
            if isinstance(obj, str):
                stripped = obj.strip()
                if not stripped:
                    return []
                try:
                    return flatten(json.loads(stripped))
                except Exception:
                    return [stripped] if stripped else []
            if isinstance(obj, list):
                flattened = []
                for item in obj:
                    flattened.extend(flatten(item))
                return flattened
            if isinstance(obj, dict):
                for key in ("items", "photos", "images", "list", "data"):
                    if key in obj:
                        return flatten(obj[key])
                return [obj]
            return []

        result = flatten(data)
        return result

    def gather_photo_data(item_dict: dict) -> list:
        for key in ("photos", "images", "media", "gallery", "pictures", "photos_json", "images_json", "photo"):
            if key in item_dict and item_dict[key]:
                raw = parse_nested_structure(item_dict[key])
                if raw:
                    return raw

        extra = item_dict.get("extra") or {}
        for key in ("photos", "images", "gallery"):
            if key in extra and extra[key]:
                raw = parse_nested_structure(extra[key])
                if raw:
                    return raw
        return []

    raw_photos = gather_photo_data(item)
    urls = []

    for photo in raw_photos:
        if isinstance(photo, str):
            url = clean_url_format(photo)
        elif isinstance(photo, dict):
            url = clean_url_format(extract_from_dict(photo))
        else:
            url = ""

        if url and is_valid_image(url):
            urls.append(url)

    unique_urls = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    return unique_urls[:10]


async def send_listing_with_photos(message: Message, dialog_id: int, item: dict, index: int) -> None:
    caption = render_listing_caption(item, index)
    photos = extract_photos(item)

    if not photos:
        await send_message(message, dialog_id, caption)
        return

    try:
        if len(photos) == 1:
            await message.answer_photo(photo=photos[0], caption=caption, parse_mode="HTML")
        else:
            media_group = [
                              InputMediaPhoto(media=photos[0], caption=caption, parse_mode="HTML")
                          ] + [
                              InputMediaPhoto(media=url) for url in photos[1:]
                          ]
            await message.answer_media_group(media=media_group)
        await log_agent_message(dialog_id, caption)
    except Exception as e:
        logger.error(f"Failed to send photos: {e}", exc_info=True)
        await send_message(message, dialog_id, caption)


async def init_context(message: Message) -> Dict[str, Any]:
    async with session_scope() as session:
        u = message.from_user
        user = await crud.get_or_create_user(session, u.id, u.username, u.first_name, u.last_name)
        dialog = await crud.get_active_dialog(session, user)
        filters = await crud.latest_filters(session, dialog)
        return {
            "dialog_id": dialog.id,
            "filters": filters,
            "offset": 0,
            "last_total": 0,
            "last_activity": time.time()
        }


def extract_numbers(text: str) -> List[int]:
    numbers = re.findall(r'\b\d+\b', text or "")
    return [int(n) for n in numbers]


def parse_all_filters(text: str) -> Dict[str, Any]:
    lower_text = text.lower()
    result: Dict[str, Any] = {}

    for key in ["district", "price", "area", "condition", "rooms", "floor", "section"]:
        parsed = parse_to_filters(key, text) or {}
        if parsed:
            result.update(parsed)

    return result


def smart_parse_filters(text: str, existing_filters: Dict[str, Any]) -> Dict[str, Any]:
    parsed_all = parse_all_filters(text)

    if parsed_all:
        return parsed_all

    numbers = extract_numbers(text)
    if not numbers:
        return {}

    result: Dict[str, Any] = {}
    needs_price = "price_max" not in existing_filters and "price_min" not in existing_filters
    needs_area = "area_min" not in existing_filters and "area_max" not in existing_filters
    needs_rooms = "rooms_in" not in existing_filters

    for num in sorted(numbers):
        if num <= 7 and needs_rooms:
            result.setdefault("rooms_in", []).append(num)
        elif 20 <= num <= 500 and needs_area:
            if "area_min" not in result:
                result["area_min"] = num
            else:
                result["area_max"] = num
            needs_area = False
        elif num > 500 and needs_price:
            if "price_min" not in result:
                result["price_max"] = num
            else:
                if result.get("price_max", 0) < num:
                    result["price_min"] = result["price_max"]
                    result["price_max"] = num
                else:
                    result["price_min"] = num
            needs_price = False

    return result


def has_meaningful_filters(filters: Dict[str, Any]) -> bool:
    if not filters:
        return False
    return any(v for v in filters.values() if v not in (None, [], "", False))


def filter_by_allowed_keys(filters: Dict[str, Any], allowed_keys: set) -> Dict[str, Any]:
    return {k: v for k, v in filters.items() if k in allowed_keys}


def apply_location_filters(filters_data: Dict[str, Any], new_filters: Dict[str, Any]) -> Dict[str, Any]:
    logger.info(f"[APPLY_FILTERS] INPUT filters_data: {filters_data}")
    logger.info(f"[APPLY_FILTERS] INPUT new_filters: {new_filters}")

    has_street = bool(new_filters.get("street_id"))
    has_microarea = bool(new_filters.get("microarea_id"))
    has_district = bool(new_filters.get("district_id"))

    logger.info(f"[APPLY_FILTERS] has_street={has_street}, has_microarea={has_microarea}, has_district={has_district}")

    has_any_location = has_street or has_microarea or has_district

    if has_any_location:
        logger.info(f"[APPLY_FILTERS] Has location - removing old locations from filters_data")

        result = {k: v for k, v in filters_data.items() if
                  k not in ("district_id", "microarea_id", "street_id", "explicit_street")}

        logger.info(f"[APPLY_FILTERS] After removing locations: {result}")

        if has_street:
            logger.info(f"[APPLY_FILTERS] Adding street_id: {new_filters['street_id']}")
            result["street_id"] = list(dict.fromkeys(new_filters["street_id"]))
            result["explicit_street"] = True
        elif has_microarea:
            logger.info(f"[APPLY_FILTERS] Adding microarea_id: {new_filters['microarea_id']}")
            result["microarea_id"] = list(dict.fromkeys(new_filters["microarea_id"]))
        elif has_district:
            logger.info(f"[APPLY_FILTERS] Adding district_id: {new_filters['district_id']}")
            result["district_id"] = list(dict.fromkeys(new_filters["district_id"]))

        for key, value in new_filters.items():
            if key not in ("district_id", "microarea_id", "street_id", "explicit_street"):
                result[key] = value

        logger.info(f"[APPLY_FILTERS] OUTPUT result: {result}")
        return result

    logger.info(f"[APPLY_FILTERS] No location changes - merging all filters")

    result = dict(filters_data)
    for key, value in new_filters.items():
        if key not in ("district_id", "microarea_id", "street_id", "explicit_street"):
            result[key] = value

    logger.info(f"[APPLY_FILTERS] OUTPUT result: {result}")
    return result


async def save_filters_to_db(dialog_id: int, filters_data: Dict[str, Any]) -> None:
    async with session_scope() as session:
        dialog = await session.get(models.Dialog, dialog_id)
        if dialog:
            await crud.save_filters(session, dialog, filters_data, True)


async def handle_show_listings(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    dialog_id = data["dialog_id"]
    filters_data = data.get("filters", {}) or {}
    offset = int(data.get("offset", 0))

    floor_only_last = filters_data.pop("floor_only_last", False)

    payload = {
        **filters_data,
        "limit": 3,
        "offset": offset,
        "sort": filters_data.get("sort", "newest")
    }

    resp = await fetch_listings(payload)

    async with session_scope() as session:
        dialog = await session.get(models.Dialog, dialog_id)
        if dialog:
            await crud.log_api_request(session, dialog, payload, resp)

    items = resp.get("data") or []

    if floor_only_last:
        items = [item for item in items if item.get("floor") == item.get("floors_total")]

    total = len(items) if floor_only_last else (resp.get("total") or 0)

    await state.update_data(last_total=total)

    if not items:
        msg = BOT_MESSAGES.get('no_results')
        await send_message(message, dialog_id, msg)
        return

    async with session_scope() as session:
        dialog = await session.get(models.Dialog, dialog_id)
        if not dialog:
            return
        base_index = await crud.get_next_display_index(session, dialog)

        for offset_idx, item in enumerate(items):
            display_idx = base_index + offset_idx
            await send_listing_with_photos(message, dialog_id, item, display_idx)

            listing_id = item.get("id") or 0
            await crud.log_view(session, dialog, listing_id, item, display_idx)

    remaining = max(total - offset - len(items), 0)

    if remaining > 0:
        template = BOT_MESSAGES.get('remaining_options')
        msg = template.replace('{remaining}', str(remaining))
        await send_message(message, dialog_id, msg)
    else:
        msg = BOT_MESSAGES.get('all_shown')
        await send_message(message, dialog_id, msg)


@router.message(CommandStart())
async def start_dialog(message: Message, state: FSMContext) -> None:
    global BOT_MESSAGES, WELCOME, QUESTIONS_TEXT
    WELCOME = sheets_client.welcome_messages_dict()
    BOT_MESSAGES = sheets_client.bot_messages_dict()
    QUESTIONS_TEXT = (
        f"{WELCOME.get('greeting', '').strip()}\n\n"
        f"{WELCOME.get('instructions', '').strip()}\n\n"
        f"{WELCOME.get('example', '').strip()}"
    ).strip()

    async with session_scope() as session:
        u = message.from_user
        user = await crud.get_or_create_user(session, u.id, u.username, u.first_name, u.last_name)
        dialog = await crud.get_active_dialog(session, user)
        existing_filters = await crud.latest_filters(session, dialog)
        has_name = bool(user.first_name)

    if existing_filters and has_meaningful_filters(existing_filters):
        from ..core.llm import build_summary
        summary = build_summary(existing_filters)

        msg = (
            f"У вас вже є налаштовані фільтри:\n\n{summary}\n\n"
            f"Хочете продовжити пошук з цими параметрами чи почати спочатку?\n\n"
            f"Напишіть \"продовжити\" або \"новий пошук\""
        )

        await log_user_text(message)
        context = await init_context(message)
        context["filters"] = existing_filters
        await state.update_data(**context)
        await state.set_state(RealtorState.browsing)
        await send_message(message, context["dialog_id"], msg)
    else:
        await state.clear()
        context = await init_context(message)
        await state.update_data(**context)

        if not has_name:
            await state.set_state(RealtorState.collecting_name)
            name_question = WELCOME.get('ask_name', 'Як можу до вас звертатись?')
            await send_message(message, context["dialog_id"], name_question)
        else:
            await state.set_state(RealtorState.browsing)
            await log_user_text(message)
            await send_message(message, context["dialog_id"], QUESTIONS_TEXT)


@router.message(RealtorState.collecting_filters)
async def handle_collecting_filters(message: Message, state: FSMContext) -> None:
    await update_last_activity(state)

    logger.info(f"[COLLECTING] Received message: {message.text}")

    data = await state.get_data()
    dialog_id = data.get("dialog_id")

    if not dialog_id:
        context = await init_context(message)
        await state.update_data(**context)
        data = await state.get_data()
        dialog_id = data["dialog_id"]

    await log_user_text(message)
    text = message.text or ""

    if rule_engine.is_new_search(text):
        async with session_scope() as session:
            await session.execute(
                delete(models.ViewingRequest).where(models.ViewingRequest.dialog_id == dialog_id)
            )
            await session.commit()

        await state.update_data(
            filters={},
            offset=0,
            pending_key=None,
            last_user_message=None,
            current_question_key=None,
            asked_questions=[]
        )
        await save_filters_to_db(dialog_id, {})
        await state.set_state(RealtorState.browsing)
        template = BOT_MESSAGES.get('search_restarted', 'Добре, починаємо пошук спочатку!')
        msg = template.replace('{questions_text}', QUESTIONS_TEXT)
        await send_message(message, dialog_id, msg)
        return

    filters_data = data.get("filters", {}) or {}
    current_question_key = data.get("current_question_key")
    asked_questions = data.get("asked_questions", [])

    logger.info(f"[COLLECTING] filters_data={filters_data}")
    logger.info(f"[COLLECTING] current_question_key={current_question_key}")
    logger.info(f"[COLLECTING] asked_questions={asked_questions}")

    if current_question_key:
        if rule_engine.is_skip(text):
            logger.info(f"[COLLECTING] User skipped filter: {current_question_key}")
            if current_question_key not in asked_questions:
                asked_questions.append(current_question_key)

            await state.update_data(filters=filters_data, asked_questions=asked_questions)
            next_question = question_flow.get_next_question(filters_data, asked_questions)

            if next_question:
                await state.update_data(current_question_key=next_question["key"])
                await send_message(message, dialog_id, next_question["question"])
            else:
                await state.set_state(RealtorState.browsing)
                await state.update_data(current_question_key=None, asked_questions=[])
                msg = BOT_MESSAGES.get('search_updated', 'Окей, підлаштовую підбір під ваші побажання.')
                await send_message(message, dialog_id, msg)
                await handle_show_listings(message, state)
            return

        parsed = parse_to_filters(current_question_key, text) or {}
        logger.info(f"[COLLECTING] parsed={parsed}")

        if parsed:
            filters_data = apply_location_filters(filters_data, parsed)
            await state.update_data(filters=filters_data)
            await save_filters_to_db(dialog_id, filters_data)
            if current_question_key not in asked_questions:
                asked_questions.append(current_question_key)
        else:
            any_filters = parse_all_filters(text)
            logger.info(f"[COLLECTING] any_filters={any_filters}")

            if any_filters:
                filters_data = apply_location_filters(filters_data, any_filters)
                await state.update_data(filters=filters_data)
                await save_filters_to_db(dialog_id, filters_data)

                if current_question_key not in asked_questions:
                    asked_questions.append(current_question_key)
            else:
                logger.info(f"[COLLECTING] No filters parsed, sending clarify message")
                msg = BOT_MESSAGES.get('clarify_answer', 'Не зрозумів відповідь.')
                await send_message(message, dialog_id, msg)
                return

    await state.update_data(filters=filters_data, asked_questions=asked_questions)
    next_question = question_flow.get_next_question(filters_data, asked_questions)
    logger.info(f"[COLLECTING] next_question={next_question}")

    if next_question:
        await state.update_data(current_question_key=next_question["key"])
        await send_message(message, dialog_id, next_question["question"])
    else:
        logger.info(f"[COLLECTING] All questions answered, switching to browsing")
        await state.set_state(RealtorState.browsing)
        await state.update_data(current_question_key=None, asked_questions=[])

        msg = BOT_MESSAGES.get('search_updated', 'Окей, підлаштовую підбір під ваші побажання.')
        await send_message(message, dialog_id, msg)
        await handle_show_listings(message, state)


@router.message(RealtorState.browsing)
async def handle_browsing(message: Message, state: FSMContext) -> None:
    await update_last_activity(state)

    logger.info(f"[BROWSING] Received message: {message.text}")

    data = await state.get_data()
    dialog_id = data.get("dialog_id")

    if not dialog_id:
        context = await init_context(message)
        await state.update_data(**context)
        await state.set_state(RealtorState.browsing)
        data = await state.get_data()
        dialog_id = data["dialog_id"]

    await log_user_text(message)
    text = message.text or ""

    if rule_engine.is_viewing(text):
        await state.set_state(RealtorState.viewing_selection)
        msg = BOT_MESSAGES.get('ask_which_objects')
        await send_message(message, dialog_id, msg)
        return

    filters_data = data.get("filters", {}) or {}

    if rule_engine.is_new_search(text):
        async with session_scope() as session:
            await session.execute(
                delete(models.ViewingRequest).where(models.ViewingRequest.dialog_id == dialog_id)
            )
            await session.commit()

        await state.update_data(
            filters={},
            offset=0,
            pending_key=None,
            last_user_message=None
        )
        await save_filters_to_db(dialog_id, {})
        template = BOT_MESSAGES.get('search_restarted', 'Добре, починаємо пошук спочатку!')
        msg = template.replace('{questions_text}', QUESTIONS_TEXT)
        await send_message(message, dialog_id, msg)
        return

    if rule_engine.is_more(text):
        offset = data.get("offset", 0) + 3
        await state.update_data(offset=offset)
        await handle_show_listings(message, state)
        return

    pending_key = data.get("pending_key")
    if pending_key:
        updates = parse_to_filters(pending_key, text) or {}
        if updates:
            allowed_keys = PENDING_KEY_ALLOWED_FILTERS.get(pending_key)
            if allowed_keys:
                updates = filter_by_allowed_keys(updates, allowed_keys)

            filters_data = apply_location_filters(filters_data, updates)
            await state.update_data(filters=filters_data, pending_key=None, offset=0, last_user_message=None)
            await save_filters_to_db(dialog_id, filters_data)
            msg = BOT_MESSAGES.get('search_updated', 'Окей, підлаштовую підбір під ваші побажання.')
            await send_message(message, dialog_id, msg)
            await handle_show_listings(message, state)
            return

        await state.update_data(pending_key=None, last_user_message=None)
        msg = BOT_MESSAGES.get('clarify_answer', 'Не зрозумів відповідь.')
        await send_message(message, dialog_id, msg)
        return

    objection = rule_engine.match_objection(text)
    logger.info(f"[BROWSING] objection={objection}")
    if objection:
        response = (objection.get("response") or "").strip()
        key = (objection.get("key") or "").strip().lower()

        if key:
            await state.update_data(pending_key=key, last_user_message=text)
        if response:
            await send_message(message, dialog_id, response)
        return

    logger.info(f"[BROWSING] About to parse filters")
    new_filters = smart_parse_filters(text, filters_data)
    logger.info(f"[BROWSING] new_filters={new_filters}")

    if new_filters:
        filters_data = apply_location_filters(filters_data, new_filters)
        await state.update_data(filters=filters_data, offset=0)
        await save_filters_to_db(dialog_id, filters_data)

        missing = question_flow.get_missing_filters(filters_data)
        logger.info(f"[BROWSING] missing={missing}")

        if missing:
            next_question = question_flow.get_next_question(filters_data, [])
            logger.info(f"[BROWSING] next_question={next_question}")
            if next_question:
                logger.info(f"[BROWSING] Switching to collecting_filters")
                await state.set_state(RealtorState.collecting_filters)
                await state.update_data(
                    filters=filters_data,
                    current_question_key=next_question["key"],
                    asked_questions=[]
                )
                logger.info(f"[BROWSING] State switched, sending question")
                await send_message(message, dialog_id, next_question["question"])
                return

        await handle_show_listings(message, state)
        return

    if not has_meaningful_filters(filters_data):
        msg = BOT_MESSAGES.get('need_one_parameter', 'Будь ласка, вкажіть параметри.')
        await send_message(message, dialog_id, msg)
        return

    msg = BOT_MESSAGES.get('not_understood', 'Не зрозумів ваш запит.')
    await send_message(message, dialog_id, msg)


@router.message(RealtorState.viewing_selection)
async def handle_viewing_selection(message: Message, state: FSMContext) -> None:
    await update_last_activity(state)

    data = await state.get_data()
    dialog_id = data["dialog_id"]
    await log_user_text(message)
    text = message.text or ""
    numbers = extract_numbers(text)

    async with session_scope() as session:
        dialog = await session.get(models.Dialog, dialog_id)
        if not dialog:
            return

        selected_views = []

        if numbers:
            selected_views = await crud.get_views_by_display_indices(session, dialog, numbers)

        if not selected_views:
            all_views = await crud.get_all_views(session, dialog)
            all_listings = [v.payload for v in all_views]

            matched_indices = []
            normalized_text = text.lower()

            for idx, listing in enumerate(all_listings):
                addr = listing.get("address") or {}
                street = (addr.get("street") or "").lower()
                house = str(addr.get("house") or "").lower()
                micro = (addr.get("microarea") or "").lower()

                if (street and street in normalized_text) or \
                        (micro and micro in normalized_text) or \
                        (house and house in normalized_text):
                    matched_indices.append(idx)

            if matched_indices:
                selected_views = [all_views[idx] for idx in matched_indices if idx < len(all_views)]

        if not selected_views:
            msg = BOT_MESSAGES.get('objects_not_found')
            await send_message(message, dialog_id, msg)
            return

        unique_views = []
        seen_ids = set()
        for view in selected_views:
            if view.listing_id not in seen_ids:
                seen_ids.add(view.listing_id)
                unique_views.append(view)

        selected_listing_ids = [v.listing_id for v in unique_views]
        logger.info(f"[VIEWING] Selected listing_ids: {selected_listing_ids}")

        already_requested = await crud.get_viewing_requests_by_listing_ids(session, dialog, selected_listing_ids)
        already_requested_ids = {v.listing_id for v in already_requested}
        logger.info(f"[VIEWING] Already requested listing_ids: {already_requested_ids}")

        new_views = [v for v in unique_views if v.listing_id not in already_requested_ids]
        duplicate_views = [v for v in unique_views if v.listing_id in already_requested_ids]

        if duplicate_views and not new_views:
            addresses = [
                f"{(v.payload.get('address') or {}).get('street') or ''}, {(v.payload.get('address') or {}).get('house') or ''}".strip(
                    ', ')
                for v in duplicate_views
            ]
            addresses = [addr for addr in addresses if addr]

            if addresses:
                addresses_text = "\n• " + "\n• ".join(addresses)
                template = BOT_MESSAGES.get('already_requested_all', 'Ви вже записані на перегляд.')
                msg = template.replace('{addresses}', addresses_text)
            else:
                msg = BOT_MESSAGES.get('already_requested_all', 'Ви вже записані на перегляд.')

            await send_message(message, dialog_id, msg)
            await state.set_state(RealtorState.browsing)
            return

        if duplicate_views:
            addresses = [
                f"{(v.payload.get('address') or {}).get('street') or ''}, {(v.payload.get('address') or {}).get('house') or ''}".strip(
                    ', ')
                for v in duplicate_views
            ]
            addresses = [addr for addr in addresses if addr]

            if addresses:
                addresses_text = ", ".join(addresses)
                template = BOT_MESSAGES.get('already_requested_partial',
                                            'Увага: ви вже записані на перегляд {addresses}.')
                msg = template.replace('{addresses}', addresses_text)
                await send_message(message, dialog_id, msg)

        selected_view_ids = [v.id for v in new_views]

    await state.update_data(selected_view_ids=selected_view_ids)
    await state.set_state(RealtorState.viewing_request)

    count = len(new_views)
    apartments_word = "квартиру" if count == 1 else "квартир"

    addresses = []
    for view in new_views:
        payload = view.payload
        addr = payload.get("address") or {}
        street = addr.get("street") or ""
        house = addr.get("house") or ""
        micro = addr.get("microarea") or ""
        rooms = payload.get("rooms")
        area = payload.get("area_total")

        location = f"{street}, {house}" if street and house else street or micro

        details = []
        if rooms:
            details.append(f"{rooms}-кімн")
        if area:
            try:
                a = float(area)
                details.append(f"{int(a) if a.is_integer() else a}м²")
            except Exception:
                pass

        if location and details:
            addresses.append(f"{location} ({', '.join(details)})")
        elif location:
            addresses.append(location)

    template = BOT_MESSAGES.get('selected_apartments', 'Обрано {count} {apartments_word}:{addresses}')
    if addresses:
        addresses_text = "\n• " + "\n• ".join(addresses)
        msg = template.replace('{count}', str(count)).replace('{apartments_word}', apartments_word).replace(
            '{addresses}', addresses_text)
    else:
        msg = template.replace('{count}', str(count)).replace('{apartments_word}', apartments_word).replace(
            '{addresses}', '')

    await send_message(message, dialog_id, msg, reply_markup=contact_keyboard())


@router.message(RealtorState.viewing_request, F.contact)
async def handle_viewing_contact(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    dialog_id = data["dialog_id"]
    phone = message.contact.phone_number
    filters = data.get("filters", {})
    selected_view_ids = data.get("selected_view_ids", [])

    async with session_scope() as session:
        dialog = await session.get(models.Dialog, dialog_id)
        if not dialog:
            return

        user = await session.get(models.User, dialog.user_id)
        if not user:
            return

        await crud.update_contact(session, user, dialog, phone)

        result = await session.execute(
            select(models.View).where(models.View.id.in_(selected_view_ids))
        )
        listings = [view.payload for view in result.scalars().all()]

    import asyncio

    def write_to_sheets():
        sheets_client.write_viewing_request(
            user_id=user.telegram_id,
            username=user.username or "",
            phone=phone,
            name=user.first_name or "",
            listings=listings,
            filters=filters
        )

    await asyncio.to_thread(write_to_sheets)

    msg = BOT_MESSAGES.get('thank_you_contact')
    await message.answer(msg, reply_markup=ReplyKeyboardRemove())
    await log_agent_message(dialog_id, msg)
    await state.set_state(RealtorState.browsing)


@router.message(RealtorState.viewing_request, F.contact)
async def handle_viewing_contact(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    dialog_id = data["dialog_id"]
    phone = message.contact.phone_number
    filters = data.get("filters", {})
    selected_view_ids = data.get("selected_view_ids", [])

    async with session_scope() as session:
        dialog = await session.get(models.Dialog, dialog_id)
        if not dialog:
            return

        user = await session.get(models.User, dialog.user_id)
        if not user:
            return

        await crud.update_contact(session, user, dialog, phone)

        result = await session.execute(
            select(models.View).where(models.View.id.in_(selected_view_ids))
        )
        listings = [view.payload for view in result.scalars().all()]

    import asyncio

    def write_to_sheets():
        sheets_client.write_viewing_request(
            user_id=user.telegram_id,
            username=user.username or "",
            phone=phone,
            name=user.first_name or "",
            listings=listings,
            filters=filters
        )

    await asyncio.to_thread(write_to_sheets)

    msg = BOT_MESSAGES.get('thank_you_contact')
    await message.answer(msg, reply_markup=ReplyKeyboardRemove())
    await log_agent_message(dialog_id, msg)
    await state.set_state(RealtorState.browsing)


@router.message(RealtorState.collecting_name)
async def handle_collecting_name(message: Message, state: FSMContext) -> None:
    await update_last_activity(state)

    data = await state.get_data()
    dialog_id = data.get("dialog_id")

    if not dialog_id:
        context = await init_context(message)
        await state.update_data(**context)
        data = await state.get_data()
        dialog_id = data["dialog_id"]

    await log_user_text(message)
    text = message.text or ""

    name, rest = extract_name_from_text(text)

    if not name:
        words = text.strip().split()
        if words:
            name = words[0].capitalize()
            rest = " ".join(words[1:]) if len(words) > 1 else ""
        else:
            msg = BOT_MESSAGES.get('clarify_name', 'Будь ласка, вкажіть своє ім\'я')
            await send_message(message, dialog_id, msg)
            return

    async with session_scope() as session:
        u = message.from_user
        user = await crud.get_or_create_user(session, u.id, u.username, u.first_name, u.last_name)
        await crud.update_user_name(session, user, name)

    await state.set_state(RealtorState.browsing)

    if rest and len(rest) > 5:
        filters_data = data.get("filters", {}) or {}
        new_filters = smart_parse_filters(rest, filters_data)

        if new_filters:
            filters_data = apply_location_filters(filters_data, new_filters)
            await state.update_data(filters=filters_data, offset=0)
            await save_filters_to_db(dialog_id, filters_data)

            missing = question_flow.get_missing_filters(filters_data)

            if missing:
                next_question = question_flow.get_next_question(filters_data, [])
                if next_question:
                    await state.set_state(RealtorState.collecting_filters)
                    await state.update_data(
                        filters=filters_data,
                        current_question_key=next_question["key"],
                        asked_questions=[]
                    )
                    greeting = f"Приємно, {name}! {next_question['question']}"
                    await send_message(message, dialog_id, greeting)
                    return

            greeting = f"Приємно, {name}! Шукаю для вас варіанти..."
            await send_message(message, dialog_id, greeting)
            await handle_show_listings(message, state)
            return

    greeting = f"Приємно, {name}! {QUESTIONS_TEXT}"
    await send_message(message, dialog_id, greeting)