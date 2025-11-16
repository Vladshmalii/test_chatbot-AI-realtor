# crud.py

from typing import Any, Dict, List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.llm import build_summary
from . import models


async def get_or_create_user(
        session: AsyncSession,
        telegram_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str]
) -> models.User:
    result = await session.execute(
        select(models.User).where(models.User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = models.User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name
        )
        session.add(user)
        await session.flush()
    else:
        user.username = username
        user.first_name = first_name
        user.last_name = last_name

    return user


async def get_active_dialog(session: AsyncSession, user: models.User) -> models.Dialog:
    result = await session.execute(
        select(models.Dialog)
        .where(models.Dialog.user_id == user.id, models.Dialog.is_active == True)
        .order_by(models.Dialog.created_at.desc())
    )
    dialog = result.scalar_one_or_none()

    if dialog is None:
        dialog = models.Dialog(user_id=user.id)
        session.add(dialog)
        await session.flush()

    return dialog


async def mark_dialog_finished(session: AsyncSession, dialog: models.Dialog) -> None:
    dialog.is_active = False


async def update_contact(
        session: AsyncSession,
        user: models.User,
        dialog: models.Dialog,
        phone: str
) -> None:
    user.phone_number = phone
    dialog.contact_shared = True


async def append_message(
        session: AsyncSession,
        dialog: models.Dialog,
        sender: str,
        content: str
) -> models.Message:
    message = models.Message(dialog_id=dialog.id, sender=sender, content=content)
    session.add(message)
    return message


async def save_filters(
        session: AsyncSession,
        dialog: models.Dialog,
        filters: Dict[str, Any],
        completed: bool
) -> models.FilterSnapshot:
    snapshot = models.FilterSnapshot(
        dialog_id=dialog.id,
        data=filters,
        completed=completed
    )
    session.add(snapshot)
    return snapshot


async def log_api_request(
        session: AsyncSession,
        dialog: models.Dialog,
        payload: Dict[str, Any],
        response: Optional[Dict[str, Any]]
) -> models.ApiRequest:
    record = models.ApiRequest(
        dialog_id=dialog.id,
        payload=payload,
        response=response
    )
    session.add(record)
    return record


async def log_view(
        session: AsyncSession,
        dialog: models.Dialog,
        listing_id: int,
        payload: Dict[str, Any],
        display_index: int
) -> models.View:
    view = models.View(
        dialog_id=dialog.id,
        listing_id=listing_id,
        payload=payload,
        display_index=display_index
    )
    session.add(view)
    await session.flush()
    return view


async def get_all_views(session: AsyncSession, dialog: models.Dialog) -> List[models.View]:
    result = await session.execute(
        select(models.View)
        .where(models.View.dialog_id == dialog.id)
        .order_by(models.View.created_at.desc())
    )
    return list(result.scalars().all())


async def get_next_display_index(session: AsyncSession, dialog: models.Dialog) -> int:
    result = await session.execute(
        select(func.max(models.View.display_index)).where(models.View.dialog_id == dialog.id)
    )
    max_idx = result.scalar_one_or_none()
    return (max_idx or 0) + 1

async def get_views_by_display_indices(
        session: AsyncSession,
        dialog: models.Dialog,
        indices: List[int]
) -> List[models.View]:
    result = await session.execute(
        select(models.View)
        .where(
            models.View.dialog_id == dialog.id,
            models.View.display_index.in_(indices)
        )
    )
    return list(result.scalars().all())


async def get_viewing_requests_by_listing_ids(
        session: AsyncSession,
        dialog: models.Dialog,
        listing_ids: List[int]
) -> List[models.ViewingRequest]:
    result = await session.execute(
        select(models.ViewingRequest)
        .where(
            models.ViewingRequest.dialog_id == dialog.id,
            models.ViewingRequest.listing_id.in_(listing_ids)
        )
    )
    return list(result.scalars().all())


async def latest_filters(session: AsyncSession, dialog: models.Dialog) -> Dict[str, Any]:
    result = await session.execute(
        select(models.FilterSnapshot)
        .where(models.FilterSnapshot.dialog_id == dialog.id)
        .order_by(models.FilterSnapshot.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    return record.data if record else {}


def filters_summary(filters: Dict[str, Any]) -> str:
    return build_summary(filters)

async def update_user_name(session: AsyncSession, user: models.User, name: str) -> None:
    user.first_name = name
    await session.commit()