from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.models import ConversationState
from app.role_router import RoleRouter


FOLLOW_UP_PATTERNS = (
    "continue",
    "continua",
    "e il resto",
    "e il resto?",
    "and then",
    "e poi",
    "the rest",
    "il resto",
    "expand",
    "espandi",
    "approfondisci",
    "finish it",
    "finiscilo",
    "finisci",
    "completa",
    "sviluppalo",
    "fammi la versione completa",
    "versione completa",
    "vai avanti",
    "prosegui",
    "continua da dove eri rimasto",
    "more",
    "altro",
)


@dataclass
class ConversationResolution:
    original_prompt: str
    effective_prompt: str
    is_follow_up: bool
    context: str
    state: Optional[ConversationState]


class ConversationStateManager:
    def __init__(self, db: Session, chat_id: str | int = "default", ttl_minutes: int = 45):
        self.db = db
        self.chat_id = str(chat_id or "default")
        self.session_key = f"chat:{self.chat_id}"
        self.ttl = timedelta(minutes=ttl_minutes)
        self.role_router = RoleRouter()
        self.ensure_schema()

    def ensure_schema(self) -> None:
        bind = self.db.get_bind()
        inspector = inspect(bind)
        if "conversation_state" not in inspector.get_table_names():
            return

        existing_columns = {column["name"] for column in inspector.get_columns("conversation_state")}
        column_definitions = {
            "chat_id": "VARCHAR(128) NOT NULL DEFAULT 'default'",
            "active_intent": "VARCHAR(64) NOT NULL DEFAULT ''",
            "last_assistant_response": "TEXT NOT NULL DEFAULT ''",
            "last_content_topic": "VARCHAR(255) NOT NULL DEFAULT ''",
            "last_content_format": "VARCHAR(64) NOT NULL DEFAULT ''",
            "last_output_type": "VARCHAR(64) NOT NULL DEFAULT ''",
        }
        for column_name, ddl in column_definitions.items():
            if column_name not in existing_columns:
                self.db.execute(text(f"ALTER TABLE conversation_state ADD COLUMN {column_name} {ddl}"))
        self.db.commit()

    def resolve(self, prompt: str) -> ConversationResolution:
        state = self.get_state()
        if state and self.is_expired(state):
            self.clear()
            state = None

        is_follow_up = self.is_follow_up(prompt)
        if is_follow_up and state:
            context = self.context_for_agents(state)
            effective_prompt = self._build_follow_up_prompt(prompt, state)
            return ConversationResolution(
                original_prompt=prompt,
                effective_prompt=effective_prompt,
                is_follow_up=True,
                context=context,
                state=state,
            )

        if state and self.is_topic_change(prompt, state):
            self.clear()
            state = None

        return ConversationResolution(
            original_prompt=prompt,
            effective_prompt=prompt,
            is_follow_up=False,
            context=self.context_for_agents(state) if state else "",
            state=state,
        )

    def get_state(self) -> Optional[ConversationState]:
        return (
            self.db.query(ConversationState)
            .filter(ConversationState.session_key == self.session_key)
            .first()
        )

    def update_after_response(
        self,
        user_message: str,
        effective_prompt: str,
        final_answer: str,
        agents_used: list[str],
        active_intent: Optional[str] = None,
        last_output_type: Optional[str] = None,
        active_goal: Optional[str] = None,
        task_id: Optional[int] = None,
    ) -> ConversationState:
        state = self.get_state()
        if not state:
            state = ConversationState(session_key=self.session_key, chat_id=self.chat_id)
            self.db.add(state)

        intent = active_intent or self.role_router.detect_intent(effective_prompt or user_message)
        spec = self.role_router.spec_for_intent(intent)
        is_follow_up = self.is_follow_up(user_message)
        if is_follow_up and state.active_topic:
            active_topic = state.active_topic
            active_task = state.active_task or self._compact(effective_prompt or user_message, 1800)
        else:
            active_topic = self.extract_topic(effective_prompt or user_message)
            active_task = self._compact(effective_prompt or user_message, 1800)

        state.active_topic = active_topic
        state.active_task = active_task
        state.active_agent = agents_used[0] if agents_used else "manager"
        state.active_intent = intent
        state.active_goal = active_goal
        state.chat_id = self.chat_id
        state.last_assistant_response = self._compact(final_answer, 3000)
        if intent == "content_creation":
            state.last_content_topic = self.extract_content_topic(effective_prompt or user_message)
            state.last_content_format = self.extract_content_format(effective_prompt or user_message)
            state.last_generated_content = self._compact(final_answer, 3000)
        state.last_output_type = last_output_type or spec.output_type
        state.last_user_message = self._compact(user_message, 1200)
        state.last_task_id = task_id
        state.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(state)
        return state

    def clear(self) -> None:
        state = self.get_state()
        if not state:
            return
        self.db.delete(state)
        self.db.commit()

    def context_for_agents(self, state: Optional[ConversationState] = None) -> str:
        state = state or self.get_state()
        if not state or self.is_expired(state):
            return ""

        parts = [
            "CONVERSATION STATE",
            f"Active topic: {state.active_topic or 'not set'}",
            f"Active task: {state.active_task or 'not set'}",
            f"Active agent: {state.active_agent or 'manager'}",
            f"Active intent: {state.active_intent or 'conversation'}",
            f"Last output type: {state.last_output_type or 'conversation'}",
        ]
        if state.active_goal:
            parts.append(f"Active goal: {state.active_goal}")
        if state.last_content_topic:
            parts.append(f"Last content topic: {state.last_content_topic}")
        if state.last_content_format:
            parts.append(f"Last content format: {state.last_content_format}")
        if state.last_generated_content:
            parts.append(f"Last generated content:\n{state.last_generated_content}")
        elif state.last_assistant_response:
            parts.append(f"Last assistant response:\n{state.last_assistant_response}")
        parts.append("Use this state only for direct follow-ups or clearly related messages.")
        return "\n".join(parts)

    def is_expired(self, state: ConversationState) -> bool:
        return datetime.utcnow() - state.updated_at > self.ttl

    def is_follow_up(self, prompt: str) -> bool:
        normalized = self._normalize(prompt)
        if normalized in FOLLOW_UP_PATTERNS:
            return True
        if re.fullmatch(r"(versione|version)\s+(reel|tiktok|linkedin|post|carousel|carosello|instagram|newsletter|video)\??", normalized):
            return True
        if re.fullmatch(r"(fammi|crea|prepara|dammi)?\s*(la\s*)?versione\s+(reel|tiktok|linkedin|post|carousel|carosello|instagram|newsletter|video)\??", normalized):
            return True
        if any(term in normalized for term in ("trasformalo in", "adattalo per", "adatta per")):
            return True
        if len(normalized.split()) <= 4 and any(pattern in normalized for pattern in FOLLOW_UP_PATTERNS):
            return True
        return bool(re.fullmatch(r"(and )?(then|next|more|continue|expand|finish)( please)?", normalized))

    def is_topic_change(self, prompt: str, state: ConversationState) -> bool:
        normalized = self._normalize(prompt)
        if self.is_follow_up(prompt):
            return False
        if len(normalized.split()) <= 3:
            return False

        new_topic = self.extract_topic(prompt)
        old_topic = state.active_topic or self.extract_topic(state.active_task)
        if not old_topic or not new_topic:
            return False

        similarity = SequenceMatcher(None, new_topic.lower(), old_topic.lower()).ratio()
        shared_terms = set(self._keywords(new_topic)).intersection(self._keywords(old_topic))
        topic_shift_terms = ("nuovo", "altra cosa", "cambia", "ora parliamo", "passiamo a")
        explicit_shift = any(term in normalized for term in topic_shift_terms)
        return explicit_shift or (similarity < 0.18 and not shared_terms)

    def extract_topic(self, text: str) -> str:
        clean = re.sub(r"\s+", " ", text).strip()
        clean = re.sub(r"^(task|messaggio utente|richiesta)\s*:\s*", "", clean, flags=re.IGNORECASE)
        words = clean.split()
        if len(words) <= 12:
            return clean[:255]
        keywords = self._keywords(clean)
        return " ".join(keywords[:10])[:255] or " ".join(words[:12])[:255]

    def _build_follow_up_prompt(self, prompt: str, state: ConversationState) -> str:
        return (
            "The user is sending a follow-up message. Continue the previous conversation instead "
            "of starting a new topic.\n\n"
            f"Follow-up message: {prompt}\n\n"
            f"Previous active topic: {state.active_topic}\n"
            f"Previous active task: {state.active_task}\n"
            f"Previous active agent: {state.active_agent}\n"
            f"Previous active intent: {state.active_intent or 'conversation'}\n"
            f"Previous output type: {state.last_output_type or 'conversation'}\n"
            f"Previous active goal: {state.active_goal or 'not set'}\n\n"
            f"Previous content topic: {state.last_content_topic or state.active_topic}\n"
            f"Previous content format: {state.last_content_format or 'not set'}\n\n"
            f"Previous generated content:\n{state.last_generated_content or state.last_assistant_response}\n\n"
            "Continue from the previous answer. If the previous output was incomplete, complete the missing sections. "
            "If the user asks for a new version like reel, TikTok, LinkedIn or carousel, transform the previous content/topic "
            "into that complete content asset. If the previous task was content_creation, return the missing content sections directly. "
            "Do not restart from scratch unless the user explicitly changes topic."
        )

    def extract_content_format(self, text: str) -> str:
        normalized = text.lower()
        if any(term in normalized for term in ("reel", "tiktok", "short", "video")):
            return "reel_tiktok"
        if any(term in normalized for term in ("carousel", "carosello")):
            return "carousel"
        if "newsletter" in normalized:
            return "newsletter"
        if any(term in normalized for term in ("linkedin", "post")):
            return "linkedin_post"
        if "instagram" in normalized:
            return "instagram_post"
        return "linkedin_post"

    def extract_content_topic(self, text: str) -> str:
        clean = re.sub(r"(?i)\b(crea|scrivi|fammi|prepara|genera|dammi|proponi|sviluppa|trasformalo|adattalo)\b", "", text)
        clean = re.sub(r"(?i)\b(un|una|il|la|lo|post|contenuto|script|caption|reel|tiktok|linkedin|carousel|carosello|newsletter|video|versione|per|su|riguardo|about)\b", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip(" .:;")
        return (clean or self.extract_topic(text))[:255]

    def _keywords(self, text: str) -> list[str]:
        stopwords = {
            "the",
            "and",
            "then",
            "with",
            "this",
            "that",
            "per",
            "con",
            "che",
            "una",
            "uno",
            "del",
            "della",
            "dei",
            "gli",
            "le",
            "il",
            "lo",
            "la",
            "un",
            "di",
            "da",
            "a",
            "e",
            "o",
            "in",
            "su",
            "mi",
            "mio",
            "mia",
            "voglio",
            "crea",
            "scrivi",
            "fammi",
            "dammi",
        }
        tokens = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", text.lower())
        return [token for token in tokens if len(token) > 2 and token not in stopwords]

    def _normalize(self, text: str) -> str:
        return re.sub(r"[^a-z0-9àèéìòù ]+", " ", text.lower()).strip()

    def _compact(self, text: str, max_chars: int) -> str:
        text = re.sub(r"\s+", " ", text or "").strip()
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 3].rstrip()}..."
