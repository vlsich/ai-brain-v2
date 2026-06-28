from __future__ import annotations

import asyncio
import logging
import re

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.brain_core import BrainCore
from app.brain_os import BrainOS
from app.config import get_settings
from app.database import SessionLocal, init_db
from app.knowledge_graph import KnowledgeGraph
from app.memory import Memory
from app.response_formatter import ResponseFormatter
from app.scheduler import AutonomousScheduler
from app.semantic_memory import SemanticMemory


logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply_text(
        update,
        format_static_reply(
            "start",
            "Ciao, sono AI Brain. Scrivimi in linguaggio naturale: posso rispondere, "
            "recuperare memoria e attivare gli agenti quando serve.\n\n"
            "Esempi:\n"
            "- Chi sono?\n"
            "- Creami una strategia TikTok per AI Brain\n"
            "- Proponi 5 contenuti LinkedIn\n"
            "- Briefing giornaliero\n"
            "- Quali sono le priorita?"
        ),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply_text(
        update,
        format_static_reply(
            "help",
            "Comandi disponibili:\n"
            "/start - avvia il bot\n"
            "/help - mostra esempi\n\n"
            "Puoi scrivere messaggi semplici o task complessi:\n"
            "- Cosa ricordi di me?\n"
            "- Analizza questo mercato e crea un piano contenuti\n"
            "- Crea 3 script TikTok coerenti con la mia strategia\n"
            "- Cosa dovrei fare oggi?\n"
            "- Review settimanale\n"
            "- Salva questa decisione: focus su TikTok per 30 giorni\n"
            "- Segna task completato 3\n"
            "- Quali sono i miei obiettivi?\n"
            "- Aggiorna progresso obiettivo 2 a 35%"
        ),
    )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    message = update.message.text.strip()
    if not message:
        return

    logger.info("Telegram message received chat_id=%s text=%r", update.effective_chat.id if update.effective_chat else None, message)

    if is_chat_id_request(message):
        chat_id = update.effective_chat.id if update.effective_chat else "non disponibile"
        await reply_text(update, format_static_reply(message, f"Il tuo chat id Telegram e:\n{chat_id}"))
        return

    await update.message.chat.send_action(action=ChatAction.TYPING)

    try:
        chat_id = update.effective_chat.id if update.effective_chat else "telegram"
        result = await asyncio.to_thread(run_chat, message, chat_id)
        await reply_text(update, result["reply"])
        logger.info(
            "Telegram reply sent task_id=%s agents=%s memories=%s length=%s quality_score=%s",
            result["task_id"],
            ", ".join(result["agents_used"]),
            len(result["memories_used"]),
            len(result["reply"]),
            result.get("quality_score"),
        )
    except Exception:
        logger.exception("Telegram message handling failed")
        await reply_text(
            update,
            format_static_reply("errore telegram", "Ho avuto un errore mentre elaboravo il messaggio. Riprova tra poco."),
        )


def run_chat(message: str, chat_id: str | int = "telegram") -> dict:
    db = SessionLocal()
    try:
        brain_os = BrainOS(db, chat_id=chat_id, telegram_mode=True)
        result = brain_os.handle_chat(message)
        result["quality_score"] = ResponseFormatter(get_settings().telegram_max_response_chars).quality_score(result["reply"])
        return result
    finally:
        db.close()


def format_static_reply(message: str, text: str) -> str:
    settings = get_settings()
    formatter = ResponseFormatter(telegram_max_chars=settings.telegram_max_response_chars)
    return formatter.format_telegram(message, text)


async def reply_text(update: Update, text: str) -> None:
    if not update.message:
        return

    for chunk in split_message(text):
        try:
            await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
        except TelegramError:
            logger.exception("Telegram HTML parsing failed, falling back to plain text")
            await update.message.reply_text(strip_html(chunk))


def split_message(text: str) -> list[str]:
    settings = get_settings()
    max_length = settings.telegram_max_response_chars
    if len(text) <= max_length:
        return [text]

    chunks = []
    current = ""
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) > max_length:
            if current:
                chunks.append(current)
            if len(block) > max_length:
                chunks.extend(split_long_block(block, max_length))
                current = ""
            else:
                current = block
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def split_long_block(block: str, max_length: int) -> list[str]:
    lines = block.splitlines()
    chunks = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}".strip() if current else line
        if len(candidate) > max_length:
            if current:
                chunks.append(current)
            current = line[:max_length]
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def strip_html(text: str) -> str:
    return re.sub(r"</?[^>]+>", "", text)


def is_chat_id_request(message: str) -> bool:
    normalized = message.lower().strip(" ?")
    return normalized in {
        "qual è il mio chat id",
        "qual e il mio chat id",
        "qual è il mio chat id?",
        "qual e il mio chat id?",
        "chat id",
        "mio chat id",
    }


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.error:
        logger.error(
            "Telegram update failed",
            exc_info=(type(context.error), context.error, context.error.__traceback__),
        )
    else:
        logger.error("Telegram update failed without exception context")


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing. Set it in .env before starting the bot.")

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(start_autonomous_scheduler)
        .post_shutdown(stop_autonomous_scheduler)
        .build()
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_error_handler(error_handler)
    return application


async def start_autonomous_scheduler(application: Application) -> None:
    scheduler = AutonomousScheduler(application, get_settings())
    application.bot_data["autonomous_scheduler"] = scheduler
    scheduler.start()


async def stop_autonomous_scheduler(application: Application) -> None:
    scheduler = application.bot_data.get("autonomous_scheduler")
    if scheduler:
        await scheduler.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    db = SessionLocal()
    try:
        Memory(db).ensure_core_memories()
        BrainCore(db).seed()
        SemanticMemory(db).sync_from_long_term_memory()
        KnowledgeGraph(db).refresh_from_current_state()
    finally:
        db.close()
    application = build_application()
    logger.info("Starting Telegram bot polling")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
