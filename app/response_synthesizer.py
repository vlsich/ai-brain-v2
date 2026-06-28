from __future__ import annotations

import logging

from app.config import get_settings
from app.context_builder import CognitiveContext
from app.response_formatter import ResponseFormatter


logger = logging.getLogger(__name__)


class ResponseSynthesizer:
    def __init__(self, telegram_mode: bool = False):
        self.settings = get_settings()
        self.telegram_mode = telegram_mode
        self.formatter = ResponseFormatter(telegram_max_chars=self.settings.telegram_max_response_chars)

    def synthesize(self, raw_response: str, context: CognitiveContext | None = None, format_message: str | None = None) -> str:
        message = format_message or (context.effective_prompt if context else "")
        if context and not format_message:
            message = f"{context.role_spec.intent} {message}".strip()

        if self.telegram_mode:
            final = self.formatter.format_telegram(message, raw_response)
        else:
            final = self.formatter.format_chat(message, raw_response)

        logger.info(
            "Response synthesized intent=%s length=%s quality=%s",
            context.role_spec.intent if context else "unknown",
            len(final),
            self.formatter.quality_score(final),
        )
        return final

    def quality_score(self, text: str) -> float:
        return self.formatter.quality_score(text)
