from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from ..core.config import settings
from .handlers import router

bot = Bot(token=settings.telegram_token, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
dp.include_router(router)
