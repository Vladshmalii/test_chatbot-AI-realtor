from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from ..core.llm import build_summary
from . import models

def get_or_create_user(session: Session, telegram_id: int, username: Optional[str], first_name: Optional[str], last_name: Optional[str]) -> models.User:
    user = session.query(models.User).filter_by(telegram_id=telegram_id).one_or_none()
    if user is None:
        user = models.User(telegram_id=telegram_id, username=username, first_name=first_name, last_name=last_name)
        session.add(user)
        session.flush()
    else:
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
    return user

def get_active_dialog(session: Session, user: models.User) -> models.Dialog:
    dialog = session.query(models.Dialog).filter_by(user_id=user.id, is_active=True).order_by(models.Dialog.created_at.desc()).first()
    if dialog is None:
        dialog = models.Dialog(user_id=user.id)
        session.add(dialog)
        session.flush()
    return dialog

def mark_dialog_finished(session: Session, dialog: models.Dialog) -> None:
    dialog.is_active = False

def update_contact(session: Session, user: models.User, dialog: models.Dialog, phone: str) -> None:
    user.phone_number = phone
    dialog.contact_shared = True

def append_message(session: Session, dialog: models.Dialog, sender: str, content: str) -> models.Message:
    message = models.Message(dialog_id=dialog.id, sender=sender, content=content)
    session.add(message)
    return message

def save_filters(session: Session, dialog: models.Dialog, filters: Dict[str, Any], completed: bool) -> models.FilterSnapshot:
    snapshot = models.FilterSnapshot(dialog_id=dialog.id, data=filters, completed=completed)
    session.add(snapshot)
    return snapshot

def log_api_request(session: Session, dialog: models.Dialog, payload: Dict[str, Any], response: Optional[Dict[str, Any]]) -> models.ApiRequest:
    record = models.ApiRequest(dialog_id=dialog.id, payload=payload, response=response)
    session.add(record)
    return record

def log_view(session: Session, dialog: models.Dialog, listing_id: int, payload: Dict[str, Any]) -> models.ViewRequest:
    view = models.ViewRequest(dialog_id=dialog.id, listing_id=listing_id, payload=payload)
    session.add(view)
    return view

def latest_filters(session: Session, dialog: models.Dialog) -> Dict[str, Any]:
    record = session.query(models.FilterSnapshot).filter_by(dialog_id=dialog.id).order_by(models.FilterSnapshot.created_at.desc()).first()
    return record.data if record else {}

def filters_summary(filters: Dict[str, Any]) -> str:
    return build_summary(filters)
