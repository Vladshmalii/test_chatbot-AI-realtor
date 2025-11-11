from fastapi import FastAPI, Request
from aiogram.types import Update
from .bot.loader import bot, dp
from .core.config import settings

app = FastAPI()

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

@app.on_event("startup")
async def on_startup() -> None:
    await bot.set_webhook(settings.telegram_webhook_url)

@app.post(settings.telegram_webhook_path)
async def webhook(request: Request) -> dict:
    payload = await request.json()
    update = Update.model_validate(payload)
    await dp.feed_update(bot, update)
    return {"ok": True}
