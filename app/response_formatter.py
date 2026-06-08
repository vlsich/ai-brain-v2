from __future__ import annotations

import re


class ResponseFormatter:
    def __init__(self, telegram_max_chars: int = 2500):
        self.telegram_max_chars = telegram_max_chars

    def format_chat(self, user_message: str, raw_reply: str) -> str:
        max_chars = None if self._wants_detail(user_message) else self.telegram_max_chars
        return self._format(user_message=user_message, raw_reply=raw_reply, max_chars=max_chars, markdown=False)

    def format_telegram(self, user_message: str, raw_reply: str) -> str:
        max_chars = None if self._wants_detail(user_message) else self.telegram_max_chars
        return self._format(user_message=user_message, raw_reply=raw_reply, max_chars=max_chars, markdown=True)

    def _format(self, user_message: str, raw_reply: str, max_chars: int | None, markdown: bool) -> str:
        cleaned = self._clean_text(raw_reply)
        if not cleaned:
            return self._render_simple(
                "Non ho abbastanza informazioni per rispondere bene. Puoi darmi un po' piu di contesto?",
                max_chars=max_chars,
                markdown=markdown,
            )

        if self._is_simple_request(user_message):
            return self._render_simple(
                self._first_useful_sentences(cleaned, max_sentences=3),
                max_chars=max_chars,
                markdown=markdown,
            )

        direct_answer = self._first_useful_sentences(cleaned, max_sentences=2)
        analysis_points = self._extract_key_points(cleaned, limit=3, exclude_text=direct_answer)
        plan_points = self._extract_plan_points(cleaned, limit=4, exclude_text=" ".join([direct_answer, " ".join(analysis_points)]))
        next_step = self._next_step(user_message, cleaned)

        if not plan_points:
            plan_points = analysis_points[:2]

        sections = [
            ("Risposta diretta", direct_answer),
            ("Analisi", analysis_points),
            ("Piano operativo", plan_points),
            ("Prossimo step", next_step),
        ]
        formatted = self._render_sections(sections, markdown=markdown)
        return self._truncate(formatted, max_chars, markdown=markdown)

    def quality_score(self, text: str) -> float:
        if not text.strip():
            return 0.0

        score = 1.0
        length = len(text)
        if length > self.telegram_max_chars:
            score -= min((length - self.telegram_max_chars) / self.telegram_max_chars, 0.35)
        if re.search(r"[\U0001F300-\U0001FAFF]", text):
            score -= 0.15
        if any(marker in text.lower() for marker in ("memory context", "score=", "matched=", "dettagli agenti")):
            score -= 0.2
        if text.count("#") > 2:
            score -= 0.1
        if "Prossimo step" in text or "Prossimo passo:" in text:
            score += 0.08
        if "Piano operativo" in text or "Punti chiave:" in text or len(text) < 450:
            score += 0.05

        return round(max(0.0, min(1.0, score)), 3)

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"#{1,6}\s*", "", text)
        text = text.replace("---", "\n")
        text = re.sub(r"[*_~>]+", "", text)
        text = re.sub(r"[•●◆◇▶▷]+", "-", text)
        text = re.sub(r"[\U0001F300-\U0001FAFF]", "", text)
        text = re.sub(r"\[[a-z_]+\]", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()

    def _is_simple_request(self, message: str) -> bool:
        normalized = message.lower().strip()
        strategic_terms = (
            "strategia",
            "strategy",
            "piano",
            "funnel",
            "content",
            "crescita",
            "conversione",
            "business",
            "contenuti",
            "finance",
            "finanza",
            "brand",
        )
        if any(term in normalized for term in strategic_terms):
            return False

        simple_patterns = (
            "chi sono",
            "chi è",
            "chi e",
            "cosa ricordi",
            "cosa sai",
            "riassumi",
            "spiegami in breve",
        )
        return len(normalized.split()) <= 10 or any(pattern in normalized for pattern in simple_patterns)

    def _wants_detail(self, message: str) -> bool:
        normalized = message.lower()
        detail_patterns = (
            "dettaglio",
            "dettagliato",
            "approfondisci",
            "completo",
            "piano completo",
            "long form",
            "senza limiti",
        )
        return any(pattern in normalized for pattern in detail_patterns)

    def _first_useful_sentences(self, text: str, max_sentences: int) -> str:
        compact = " ".join(
            line.strip("- ").strip()
            for line in text.splitlines()
            if self._is_useful_sentence(line)
        )
        compact = self._remove_internal_labels(compact)
        sentences = re.split(r"(?<=[.!?])\s+", compact)
        useful = [sentence.strip() for sentence in sentences if self._is_useful_sentence(sentence)]
        if not useful:
            return compact[:500].strip()
        return " ".join(useful[:max_sentences]).strip()

    def _extract_key_points(self, text: str, limit: int, exclude_text: str = "") -> list[str]:
        points: list[str] = []
        exclude_lower = exclude_text.lower()
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            line = re.sub(r"^[-\d. )]+", "", line).strip()
            line = self._remove_internal_labels(line)
            if not self._is_useful_sentence(line):
                continue
            if line.endswith(":") or line.lower() in exclude_lower:
                continue
            if line.lower() in {"content pillars", "format consigliati", "funnel contenuti", "direzione strategica"}:
                continue
            if len(line) > 180:
                line = f"{line[:177].rstrip()}..."
            if line not in points:
                points.append(line)
            if len(points) >= limit:
                break
        return points

    def _extract_plan_points(self, text: str, limit: int, exclude_text: str = "") -> list[str]:
        action_markers = (
            "crea",
            "usa",
            "pubblica",
            "scegli",
            "trasforma",
            "collega",
            "posiziona",
            "misura",
            "testa",
            "ottimizza",
            "porta",
            "costruisci",
        )
        candidates = self._extract_key_points(text, limit=12, exclude_text=exclude_text)
        action_points = [
            point
            for point in candidates
            if any(marker in point.lower() for marker in action_markers)
        ]
        return (action_points or candidates)[:limit]

    def _next_step(self, user_message: str, text: str) -> str:
        normalized = user_message.lower()
        if any(word in normalized for word in ("strategia", "strategy", "piano", "crescita")):
            return "scegli un canale prioritario e lo trasformo in un piano editoriale di 7 giorni."
        if any(word in normalized for word in ("post", "script", "video", "contenuto", "contenuti")):
            return "scegli il format migliore e lo sviluppo in una bozza pronta da pubblicare."
        if "?" in user_message:
            return "dimmi se vuoi che lo trasformi in una decisione operativa."
        return "dimmi il canale o l'obiettivo principale e preparo la versione esecutiva."

    def _render_simple(self, text: str, max_chars: int | None, markdown: bool) -> str:
        text = self._truncate(text.strip(), max_chars, markdown=False)
        return self._escape_markdown_v2(text) if markdown else text

    def _render_sections(self, sections: list[tuple[str, str | list[str]]], markdown: bool) -> str:
        rendered_sections = []
        for title, content in sections:
            if isinstance(content, list):
                body_lines = [line for line in content if line.strip()]
                if not body_lines:
                    continue
                if markdown:
                    body = "\n".join(f"\\- {self._escape_markdown_v2(line)}" for line in body_lines)
                else:
                    body = "\n".join(f"- {line}" for line in body_lines)
            else:
                if not content.strip():
                    continue
                body = self._escape_markdown_v2(content) if markdown else content

            if markdown:
                rendered_sections.append(f"*{self._escape_markdown_v2(title)}*\n{body}")
            else:
                rendered_sections.append(f"{title}\n{body}")

        return "\n\n".join(rendered_sections)

    def _truncate(self, text: str, max_chars: int | None, markdown: bool = False) -> str:
        text = text.strip()
        if max_chars is None or len(text) <= max_chars:
            return text

        suffix = "Risposta sintetizzata per Telegram. Chiedimi 'approfondisci' per il piano completo."
        truncated = text[: max_chars - len(suffix) - 4].rstrip()
        last_break = max(truncated.rfind("\n\n"), truncated.rfind(". "), truncated.rfind("\n"))
        if last_break > max_chars * 0.55:
            truncated = truncated[:last_break].rstrip()
        if markdown:
            suffix = self._escape_markdown_v2(suffix)
        return f"{truncated}\n\n{suffix}"

    def _escape_markdown_v2(self, text: str) -> str:
        return re.sub(r"([_*\[\]()~`>#+\-=|{}.!])", r"\\\1", text)

    def _remove_internal_labels(self, text: str) -> str:
        patterns = (
            "Manager Agent - risposta finale locale",
            "Research Agent - sintesi locale",
            "Content Agent - bozza locale",
            "FinanceContentStrategist - strategia locale",
            "MEMORY CONTEXT",
            "Memorie usate:",
            "Dettagli agenti:",
        )
        for pattern in patterns:
            text = text.replace(pattern, "")
        return text.strip(" :-")

    def _is_useful_sentence(self, sentence: str) -> bool:
        stripped = sentence.strip()
        if len(stripped) < 8:
            return False
        noisy_markers = (
            "usa queste memorie",
            "non contraddire",
            "task:",
            "id=",
            "score=",
            "matched=",
            "source_task_id",
            "il task e stato processato",
            "il task è stato processato",
            "usa la ricerca come base",
            "formato suggerito",
            "punti chiave:",
            "sintesi:",
            "dettagli agenti:",
            "memorie usate:",
            "memory context",
            "regole globali",
            "risposta finale locale",
            "strategia locale",
            "bozza locale",
            "sintesi locale",
        )
        lowered = stripped.lower()
        if any(marker in lowered for marker in noisy_markers):
            return False
        if re.fullmatch(r"\[?[a-z_ ]+\]?", stripped):
            return False
        return True
