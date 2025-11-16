import asyncio
from app.bot.loader import bot, dp
from app.core import llm, section_parser
from app.core.rules import rule_engine
from app.core.questions import question_flow
from app.core.sheets import sheets_client
from app.services.silence_monitor import get_monitor
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("[STARTUP] Loading data from Google Sheets...")

    llm.reload_lookups()
    rule_engine.reload()
    question_flow.reload()
    section_parser.reload_sections()
    sheets_client.welcome_messages_dict()
    sheets_client.bot_messages_dict()

    logger.info("[STARTUP] Data loaded successfully, starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())