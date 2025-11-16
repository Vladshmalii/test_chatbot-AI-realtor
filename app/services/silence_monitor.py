import asyncio
import logging
import time
from typing import Dict, Any
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from ..core.sheets import sheets_client

logger = logging.getLogger(__name__)

SILENCE_THRESHOLD = 900
CHECK_INTERVAL = 30


class SilenceMonitor:
    def __init__(self, bot: Bot, storage):
        self.bot = bot
        self.storage = storage
        self._task = None
        self._running = False
        self._notified_users = set()

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("[SILENCE_MONITOR] Started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[SILENCE_MONITOR] Stopped")

    async def _monitor_loop(self):
        while self._running:
            try:
                await asyncio.sleep(CHECK_INTERVAL)
                await self._check_all_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SILENCE_MONITOR] Error in loop: {e}", exc_info=True)

    async def _check_all_sessions(self):
        try:
            now = time.time()

            logger.info(f"[SILENCE_MONITOR] Checking sessions at {now}")

            all_keys = []
            try:
                all_keys = await self.storage.get_keys()
                logger.info(f"[SILENCE_MONITOR] Found {len(all_keys)} sessions")
            except AttributeError as e:
                logger.error(f"[SILENCE_MONITOR] Storage doesn't support get_keys: {e}")
                return

            for key in all_keys:
                if not isinstance(key, StorageKey):
                    continue

                user_id = key.user_id
                chat_id = key.chat_id

                if user_id in self._notified_users:
                    continue

                try:
                    data = await self.storage.get_data(key)
                    if not data:
                        continue

                    last_activity = data.get("last_activity")
                    if not last_activity:
                        logger.info(f"[SILENCE_MONITOR] User {user_id} has no last_activity")
                        continue

                    silence_duration = now - last_activity
                    logger.info(
                        f"[SILENCE_MONITOR] User {user_id}: silence={int(silence_duration)}s (threshold={SILENCE_THRESHOLD}s)")

                    if silence_duration >= SILENCE_THRESHOLD:
                        await self._send_silence_message(chat_id, user_id, key)

                except Exception as e:
                    logger.error(f"[SILENCE_MONITOR] Error checking session {user_id}: {e}")
                    continue

        except Exception as e:
            logger.error(f"[SILENCE_MONITOR] Error in check_all_sessions: {e}", exc_info=True)

    async def _send_silence_message(self, chat_id: int, user_id: int, key: StorageKey):
        try:
            reactions = sheets_client.fetch_records("reactions")
            silence_message = None

            for row in reactions:
                trigger = str(row.get("trigger", "")).strip().lower()
                if trigger == "silence":
                    silence_message = str(row.get("response", "")).strip()
                    break

            if not silence_message:
                silence_message = "Я зберіг ваш запит, можете повернутися в будь-який час 👌"

            await self.bot.send_message(chat_id, silence_message)

            self._notified_users.add(user_id)

            data = await self.storage.get_data(key)
            if data:
                data["last_activity"] = time.time()
                data["silence_notified"] = True
                await self.storage.set_data(key, data)

            logger.info(f"[SILENCE_MONITOR] Sent silence message to user {user_id}")

        except Exception as e:
            logger.error(f"[SILENCE_MONITOR] Failed to send message to {user_id}: {e}", exc_info=True)


_monitor_instance = None


def get_monitor(bot: Bot, storage) -> SilenceMonitor:
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = SilenceMonitor(bot, storage)
    return _monitor_instance