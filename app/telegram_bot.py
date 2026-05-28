from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.memory import Memory
from app.orchestrator import Orchestrator
from app.response_formatter import ResponseFormatter


logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply_text(
        update,
        (
            "Ciao, sono AI Brain. Scrivimi in linguaggio naturale: posso rispondere, "
            "recuperare memoria e attivare gli agenti quando serve.\n\n"
            "Esempi:\n"
            "- Chi sono?\n"
            "- Creami una strategia TikTok per AI Brain\n"
            "- Proponi 5 contenuti LinkedIn"
        ),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply_text(
        update,
        (
            "Comandi disponibili:\n"
            "/start - avvia il bot\n"
            "/help - mostra esempi\n\n"
            "Puoi scrivere messaggi semplici o task complessi:\n"
            "- Cosa ricordi di me?\n"
            "- Analizza questo mercato e crea un piano contenuti\n"
            "- Crea 3 script TikTok coerenti con la mia strategia"
        ),
    )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    message = update.message.text.strip()
    if not message:
        return

    logger.info("Telegram message received chat_id=%s text=%r", update.effective_chat.id if update.effective_chat else None, message)
    await update.message.chat.send_action(action=ChatAction.TYPING)

    try:
        result = await asyncio.to_thread(run_chat, message)
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
        await reply_text(update, "Ho avuto un errore mentre elaboravo il messaggio. Riprova tra poco.")


def run_chat(message: str) -> dict:
    db = SessionLocal()
    try:
        orchestrator = Orchestrator(db)
        result = orchestrator.handle_chat(message)
        settings = get_settings()
        formatter = ResponseFormatter(telegram_max_chars=settings.telegram_max_response_chars)
        result["reply"] = formatter.format_telegram(message, result["reply"])
        result["quality_score"] = formatter.quality_score(result["reply"])
        return result
    finally:
        db.close()


async def reply_text(update: Update, text: str) -> None:
    if not update.message:
        return

    for chunk in split_message(text):
        await update.message.reply_text(chunk)


def split_message(text: str) -> list[str]:
    settings = get_settings()
    max_length = settings.telegram_max_response_chars
    if len(text) <= max_length:
        return [text]

    chunks = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > max_length:
            chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    return chunks


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

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    db = SessionLocal()
    try:
        Memory(db).ensure_core_memories()
    finally:
        db.close()
    application = build_application()
    logger.info("Starting Telegram bot polling")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
