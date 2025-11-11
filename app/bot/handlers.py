import asyncio
import random
from typing import Any, Dict, List
from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from ..core.llm import parse_to_filters
from ..core.rules import rule_matcher
from ..core.sheets import sheets_client
from ..db import crud
from ..db.base import session_scope
from ..db import models
from ..services import filters as filter_service
from ..services.api_client import fetch_listings
from ..services.listings import extra_offers_message, render_cards
from .keyboards import contact_keyboard
from .states import RealtorState

router = Router()

async def log_agent_message(dialog_id: int, content: str) -> None:
    def task() -> None:
        with session_scope() as session:
            dialog = session.get(models.Dialog, dialog_id)
            if dialog:
                crud.append_message(session, dialog, "agent", content)
    await asyncio.to_thread(task)

async def ensure_context(message: Message, state: FSMContext) -> Dict[str, Any]:
    data = await state.get_data()
    if data.get("dialog_id"):
        return data
    result = await asyncio.to_thread(lambda: _init_context(message))
    await state.update_data(dialog_id=result["dialog_id"], filters=result["filters"], answered=result["answered"], questions=result["questions"], current_index=result["current_index"], pending_key=None)
    await state.set_state(RealtorState.collecting)
    return await state.get_data()

def _init_context(message: Message) -> Dict[str, Any]:
    questions = sheets_client.questions()
    def task() -> Dict[str, Any]:
        with session_scope() as session:
            from_user = message.from_user
            user = crud.get_or_create_user(session, from_user.id, from_user.username, from_user.first_name, from_user.last_name)
            dialog = crud.get_active_dialog(session, user)
            return {"dialog_id": dialog.id, "filters": crud.latest_filters(session, dialog)}
    result = task()
    result.update({"answered": [], "questions": questions, "current_index": 0})
    return result

async def send_message(message: Message, dialog_id: int, text: str, reply_markup: Any | None = None) -> None:
    await message.answer(text, reply_markup=reply_markup)
    await log_agent_message(dialog_id, text)

@router.message(CommandStart())
async def start_dialog(message: Message, state: FSMContext) -> None:
    await state.clear()
    context = await asyncio.to_thread(lambda: _init_context(message))
    await state.update_data(**context, pending_key=None)
    await state.set_state(RealtorState.collecting)
    greetings = sheets_client.welcome_messages()
    greeting = random.choice(greetings) if greetings else "Привіт! Я ШІ Ріелтор, допоможу підібрати квартиру."
    await asyncio.to_thread(lambda: _log_user_text(message))
    await send_message(message, context["dialog_id"], greeting)
    await ask_next_question(message, state)

async def ask_next_question(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    questions: List[Dict[str, Any]] = data.get("questions", [])
    answered: List[str] = data.get("answered", [])
    index = data.get("current_index", 0)
    while index < len(questions) and questions[index]["key"] in answered:
        index += 1
    if index >= len(questions):
        await state.update_data(current_index=index, pending_key=None)
        await request_contact(message, state)
        return
    question = questions[index]
    await state.update_data(current_index=index, pending_key=question["key"])
    await send_message(message, data["dialog_id"], question["text"])

async def request_contact(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("contact_requested"):
        return
    await send_message(message, data["dialog_id"], "Я вже підібрав для вас кілька варіантів по вашим фільтрам! Будь ласка, поділіться вашим номером, щоб я міг відправити результати.", reply_markup=contact_keyboard())
    await state.update_data(contact_requested=True)
    await state.set_state(RealtorState.waiting_contact)

def _persist_filters(dialog_id: int, filters: Dict[str, Any], completed: bool) -> None:
    with session_scope() as session:
        dialog = session.get(models.Dialog, dialog_id)
        if dialog:
            crud.save_filters(session, dialog, filters, completed)

@router.message(RealtorState.collecting, F.text)
async def handle_text(message: Message, state: FSMContext) -> None:
    context = await state.get_data()
    if not context.get("dialog_id"):
        context = await ensure_context(message, state)
    await asyncio.to_thread(lambda: _log_user_text(message))
    data = await state.get_data()
    questions: List[Dict[str, Any]] = data.get("questions", sheets_client.questions())
    answered_set = set(data.get("answered", []))
    filters_data: Dict[str, Any] = data.get("filters", {})
    pending_key = data.get("pending_key")
    updates: Dict[str, Any] = {}
    if pending_key:
        result = parse_to_filters(pending_key, message.text or "")
        if result:
            answered_set.add(pending_key)
            updates = filter_service.merge_filters(updates, result)
    for question in questions:
        if question["key"] in answered_set:
            continue
        parsed = parse_to_filters(question["key"], message.text or "")
        if parsed:
            answered_set.add(question["key"])
            updates = filter_service.merge_filters(updates, parsed)
    await state.update_data(answered=list(answered_set))
    combined_filters = filter_service.merge_filters(filters_data, updates)
    await state.update_data(filters=combined_filters)
    if updates:
        await asyncio.to_thread(lambda: _persist_filters(data["dialog_id"], combined_filters, filter_service.is_complete(combined_filters)))
    reaction = rule_matcher.match_objection(message.text or "") or rule_matcher.match_reaction(message.text or "")
    if reaction:
        await send_message(message, data["dialog_id"], reaction)
    if filter_service.is_complete(combined_filters):
        await request_contact(message, state)
        return
    await ask_next_question(message, state)

def _log_user_text(message: Message) -> None:
    with session_scope() as session:
        from_user = message.from_user
        user = crud.get_or_create_user(session, from_user.id, from_user.username, from_user.first_name, from_user.last_name)
        dialog = crud.get_active_dialog(session, user)
        crud.append_message(session, dialog, "user", message.text or "")

@router.message(RealtorState.waiting_contact, F.contact)
async def handle_contact(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    contact = message.contact
    phone = contact.phone_number
    await asyncio.to_thread(lambda: _log_contact_message(data["dialog_id"], phone))
    await asyncio.to_thread(lambda: _store_contact(data["dialog_id"], phone))
    await state.set_state(RealtorState.finished)
    await message.answer("Дякую! Зараз надішлю варіанти.", reply_markup=ReplyKeyboardRemove())
    await log_agent_message(data["dialog_id"], "Дякую! Зараз надішлю варіанти.")
    filters_payload = data.get("filters", {})
    response = await asyncio.to_thread(lambda: fetch_listings(filters_payload))
    await asyncio.to_thread(lambda: _log_api(data["dialog_id"], filters_payload, response))
    cards = render_cards(response)
    if cards:
        for card in cards:
            await send_message(message, data["dialog_id"], card)
    total = response.get("total") or len(response.get("data") or [])
    await send_message(message, data["dialog_id"], extra_offers_message(total))
    await asyncio.to_thread(lambda: _finalize_dialog(data["dialog_id"]))

@router.message(RealtorState.waiting_contact)
async def remind_contact(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await asyncio.to_thread(lambda: _log_user_text(message))
    await send_message(message, data["dialog_id"], "Будь ласка, скористайтесь кнопкою, щоб поділитися номером телефону.", reply_markup=contact_keyboard())

def _store_contact(dialog_id: int, phone: str) -> None:
    with session_scope() as session:
        dialog = session.get(models.Dialog, dialog_id)
        if dialog and dialog.user:
            crud.update_contact(session, dialog.user, dialog, phone)

def _log_api(dialog_id: int, payload: Dict[str, Any], response: Dict[str, Any]) -> None:
    with session_scope() as session:
        dialog = session.get(models.Dialog, dialog_id)
        if dialog:
            crud.log_api_request(session, dialog, payload, response)
            for item in (response.get("data") or [])[:3]:
                listing_id = item.get("id") or 0
                crud.log_view(session, dialog, listing_id, item)

def _finalize_dialog(dialog_id: int) -> None:
    with session_scope() as session:
        dialog = session.get(models.Dialog, dialog_id)
        if dialog:
            crud.mark_dialog_finished(session, dialog)

def _log_contact_message(dialog_id: int, phone: str) -> None:
    with session_scope() as session:
        dialog = session.get(models.Dialog, dialog_id)
        if dialog:
            crud.append_message(session, dialog, "user", f"Поділився контактом: {phone}")
