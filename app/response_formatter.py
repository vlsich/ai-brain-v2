from __future__ import annotations

import ast
import html
import json
import re
from typing import Any


SECTION_LABELS = (
    "vittorie",
    "wins",
    "blocchi",
    "blockers",
    "priorita",
    "priorità",
    "priorities",
    "task",
    "raccomandazioni",
    "raccomandazione",
    "recommendations",
    "analisi",
    "analysis",
    "prossimo passo",
    "prossimi passi",
    "next steps",
)


SECTION_TITLES = {
    "daily_briefing": "📅 Daily Briefing",
    "priorities": "🎯 Priorities",
    "wins": "🏆 Wins",
    "blockers": "🚧 Blockers",
    "analysis": "💡 Analysis",
    "recommendations": "📌 Recommendations",
    "next_steps": "🚀 Next Steps",
}


EXECUTIVE_SECTION_TITLES = {
    "executive_summary": "Executive Summary",
    "analysis": "Analysis",
    "recommendations": "Recommendations",
    "next_actions": "Next Actions",
}


class ResponseFormatter:
    def __init__(self, telegram_max_chars: int = 2500):
        self.telegram_max_chars = telegram_max_chars

    def format_chat(self, user_message: str, raw_reply: str) -> str:
        max_chars = None if self._wants_detail(user_message) else self.telegram_max_chars
        return self._format(user_message=user_message, raw_reply=raw_reply, max_chars=max_chars, markdown=False)

    def format_telegram(self, user_message: str, raw_reply: str) -> str:
        max_chars = None if self._wants_detail(user_message) else self.telegram_max_chars
        return self._format(user_message=user_message, raw_reply=raw_reply, max_chars=max_chars, markdown=True)

    def format_task_list(self, tasks: Any, markdown: bool = True) -> str:
        points = self._coerce_points(tasks)
        if not points:
            points = ["Nessun task operativo disponibile."]
        return self._render_executive_response(
            summary="La lista task e stata consolidata in priorita operative.",
            analysis=points,
            recommendations=["Dai precedenza ai task piu vicini a obiettivi, monetizzazione e crescita audience."],
            next_actions=points[:3],
            markdown=markdown,
        )

    def format_briefing(
        self,
        wins: Any = None,
        blockers: Any = None,
        priorities: Any = None,
        analysis: Any = None,
        recommendations: Any = None,
        next_steps: Any = None,
        markdown: bool = True,
    ) -> str:
        analysis_points = []
        analysis_points.extend([f"Win: {point}" for point in self._coerce_points(wins, limit=3)])
        analysis_points.extend([f"Blocco: {point}" for point in self._coerce_points(blockers, limit=3)])
        analysis_points.extend(self._coerce_points(analysis, limit=3))
        priority_points = self._coerce_points(priorities, limit=5)
        return self._render_executive_response(
            summary="Il briefing evidenzia cosa sta avanzando, cosa blocca il lavoro e quali priorita meritano attenzione oggi.",
            analysis=analysis_points or priority_points,
            recommendations=self._coerce_points(recommendations, limit=4) or ["Proteggi il focus sui task che avvicinano obiettivi business e personal brand."],
            next_actions=self._coerce_points(next_steps, limit=4) or priority_points[:3],
            markdown=markdown,
        )

    def format_review(self, review: Any, markdown: bool = True) -> str:
        payload = review if isinstance(review, dict) else {}
        return self._render_executive_response(
            summary="La review sintetizza progressi, decisioni e allineamento rispetto agli obiettivi.",
            analysis=self._coerce_points(payload.get("progress") or payload.get("alignment") or review, limit=5),
            recommendations=self._coerce_points(payload.get("recommendations"), limit=4) or ["Riduci dispersione e concentra la prossima settimana su un risultato misurabile."],
            next_actions=["Scegli la priorita principale della prossima settimana.", "Trasformala in 3 task eseguibili.", "Collega ogni task a un obiettivo attivo."],
            markdown=markdown,
        )

    def format_decision(self, decision: Any, markdown: bool = True) -> str:
        payload = decision if isinstance(decision, dict) else {"decision": decision}
        analysis = [
            payload.get("title"),
            payload.get("decision"),
            payload.get("reasoning"),
            payload.get("expected_outcome"),
        ]
        return self._render_executive_response(
            summary="La decisione e stata trasformata in un punto operativo da monitorare.",
            analysis=self._coerce_points(analysis, limit=5),
            recommendations=self._coerce_points(payload.get("recommendations"), limit=4) or ["Mantieni la decisione collegata a un obiettivo e verifica se produce il risultato atteso."],
            next_actions=["Definisci il primo task collegato alla decisione.", "Rivedi la decisione quando cambiano dati, priorita o risultati."],
            markdown=markdown,
        )

    def format_content_plan(self, plan: Any, markdown: bool = True) -> str:
        payload = plan if isinstance(plan, dict) else {}
        analysis_items = []
        if payload.get("summary"):
            analysis_items.append(payload["summary"])
        analysis_items.extend(self._coerce_points(payload.get("plans"))[:4])
        analysis_items.extend(self._coerce_points(payload.get("ideas"))[:5])
        task_items = self._coerce_points(payload.get("tasks"))[:6]
        return self._render_executive_response(
            summary="Il piano contenuti e stato convertito in un framework operativo da Content Director.",
            analysis=analysis_items or self._coerce_points(plan, limit=5),
            recommendations=["Pubblica prima il contenuto con hook piu chiaro e CTA piu vicina alla monetizzazione.", "Mantieni focus su finance, fiducia e conversione audience."],
            next_actions=task_items[:4] or ["Scegli un contenuto e chiedimi di trasformarlo in script pronto da registrare."],
            markdown=markdown,
        )

    def format_recommendations(self, recommendations: Any, markdown: bool = True) -> str:
        points = self._coerce_points(recommendations)
        return self._render_executive_response(
            summary="Le raccomandazioni sono state sintetizzate in decisioni operative.",
            analysis=points,
            recommendations=points,
            next_actions=points[:3],
            markdown=markdown,
        )

    def _format(self, user_message: str, raw_reply: str, max_chars: int | None, markdown: bool) -> str:
        parsed = self._extract_structured(raw_reply)
        if parsed is not None:
            formatted = self._format_structured(user_message, parsed, markdown)
            if formatted:
                return self._truncate(formatted, max_chars, markdown=markdown)

        cleaned = self._clean_text(raw_reply)
        if not cleaned:
            formatted = self._render_executive_response(
                summary="Non ci sono abbastanza informazioni per una risposta affidabile.",
                analysis=["Il contesto disponibile non basta per distinguere obiettivo, vincoli e prossima azione."],
                recommendations=["Chiedere un solo dato mancante prima di procedere."],
                next_actions=["Dimmi l'obiettivo principale o il risultato che vuoi ottenere."],
                markdown=markdown,
            )
            return self._truncate(formatted, max_chars, markdown=markdown)

        role = self._executive_role(user_message)

        direct_answer = self._first_useful_sentences(cleaned, max_sentences=2)
        if (
            self._is_briefing_request(user_message)
            or self._looks_like_labeled_digest(direct_answer)
            or self._needs_compact_title(user_message, direct_answer)
        ):
            direct_answer = self._digest_title(user_message)
        wins_points = self._extract_label_points(cleaned, labels=("vittorie", "wins"), limit=3)
        blocker_points = self._extract_label_points(cleaned, labels=("blocchi", "blockers"), limit=3)
        priority_points = self._extract_label_points(cleaned, labels=("priorita", "priorità", "priorities", "task"), limit=4)
        analysis_points = self._extract_key_points(cleaned, limit=3, exclude_text=direct_answer)
        plan_points = self._extract_plan_points(cleaned, limit=4, exclude_text=" ".join([direct_answer, " ".join(analysis_points)]))
        next_step = self._next_step(user_message, cleaned)

        if not plan_points:
            plan_points = analysis_points[:2]

        combined_analysis = self._dedupe_points(([direct_answer] if not self._is_briefing_request(user_message) else []) + analysis_points)
        if wins_points:
            combined_analysis.extend([f"Win: {point}" for point in wins_points])
        if blocker_points:
            combined_analysis.extend([f"Blocco: {point}" for point in blocker_points])
        recommendations = self._extract_label_points(cleaned, labels=("raccomandazioni", "raccomandazione", "recommendations"), limit=4)

        formatted = self._render_executive_response(
            summary=self._executive_summary(user_message, direct_answer, role),
            analysis=combined_analysis or [direct_answer],
            recommendations=recommendations or self._executive_recommendations(user_message, role),
            next_actions=(priority_points or plan_points or [next_step])[:4],
            markdown=markdown,
        )
        return self._truncate(formatted, max_chars, markdown=markdown)

    def quality_score(self, text: str) -> float:
        if not text.strip():
            return 0.0

        score = 1.0
        length = len(text)
        if length > self.telegram_max_chars:
            score -= min((length - self.telegram_max_chars) / self.telegram_max_chars, 0.35)
        allowed_section_icons = ("📅", "🎯", "💡", "🚀", "🏆", "🚧", "📌")
        text_without_allowed_icons = text
        for icon in allowed_section_icons:
            text_without_allowed_icons = text_without_allowed_icons.replace(icon, "")
        if re.search(r"[\U0001F300-\U0001FAFF]", text_without_allowed_icons):
            score -= 0.15
        if any(marker in text.lower() for marker in ("memory context", "score=", "matched=", "dettagli agenti")):
            score -= 0.2
        if text.count("#") > 2:
            score -= 0.1
        if "Prossimo Passo" in text or "Prossimo step" in text or "Prossimo passo:" in text:
            score += 0.08
        if "Piano Operativo" in text or "Piano operativo" in text or "Punti chiave:" in text or len(text) < 450:
            score += 0.05

        return round(max(0.0, min(1.0, score)), 3)

    def _format_structured(self, user_message: str, payload: Any, markdown: bool) -> str:
        if isinstance(payload, list):
            return self.format_task_list(payload, markdown=markdown)
        if not isinstance(payload, dict):
            return ""

        keys = set(payload)
        normalized = user_message.lower()
        if {"wins", "blockers", "priorities"}.intersection(keys) or "briefing" in normalized:
            return self.format_briefing(
                wins=payload.get("wins"),
                blockers=payload.get("blockers"),
                priorities=payload.get("priorities") or payload.get("tasks"),
                analysis=payload.get("analysis"),
                recommendations=payload.get("recommendations"),
                next_steps=payload.get("next_steps"),
                markdown=markdown,
            )
        if {"plans", "ideas", "tasks"}.intersection(keys) or any(term in normalized for term in ("contenuto", "contenuti", "idee", "piano editoriale")):
            return self.format_content_plan(payload, markdown=markdown)
        if {"decision", "reasoning", "expected_outcome"}.intersection(keys) or "decision" in normalized:
            return self.format_decision(payload, markdown=markdown)
        if {"progress", "completed_tasks", "alignment"}.intersection(keys) or "review" in normalized:
            return self.format_review(payload, markdown=markdown)
        if {"recommendations", "raccomandazioni"}.intersection(keys):
            return self.format_recommendations(payload.get("recommendations") or payload.get("raccomandazioni"), markdown=markdown)

        return ""

    def _render_executive_response(
        self,
        summary: Any,
        analysis: Any,
        recommendations: Any,
        next_actions: Any,
        markdown: bool,
    ) -> str:
        return self._join_sections(
            [
                self._render_executive_section("executive_summary", summary, markdown, numbered=False, paragraph=True),
                self._render_executive_section("analysis", analysis, markdown),
                self._render_executive_section("recommendations", recommendations, markdown),
                self._render_executive_section("next_actions", next_actions, markdown, numbered=True),
            ]
        )

    def _render_executive_section(
        self,
        section_key: str,
        content: Any,
        markdown: bool,
        numbered: bool = False,
        paragraph: bool = False,
    ) -> str:
        points = self._dedupe_points(self._coerce_points(content, limit=6))
        if not points:
            points = [self._fallback_section_point(section_key)]

        title = EXECUTIVE_SECTION_TITLES[section_key]
        if paragraph:
            body = " ".join(points[:2])
            body = self._escape_html(body) if markdown else body
        elif numbered:
            body = "\n".join(
                f"{index}. {self._escape_html(point) if markdown else point}"
                for index, point in enumerate(points[:5], start=1)
            )
        else:
            body = "\n".join(f"• {self._escape_html(point) if markdown else point}" for point in points[:5])

        if markdown:
            return f"<b>{self._escape_html(title)}</b>\n{body}"
        return f"{title}\n{body}"

    def _fallback_section_point(self, section_key: str) -> str:
        fallbacks = {
            "executive_summary": "Il punto e stato sintetizzato in forma operativa.",
            "analysis": "Il contesto va letto rispetto a obiettivi, vincoli e impatto business.",
            "recommendations": "Concentrare l'azione su cio che produce avanzamento misurabile.",
            "next_actions": "Definire il prossimo task concreto e collegarlo a un obiettivo.",
        }
        return fallbacks[section_key]

    def _executive_role(self, user_message: str) -> str:
        normalized = user_message.lower()
        if any(term in normalized for term in ("contenuto", "contenuti", "post", "script", "tiktok", "instagram", "youtube", "newsletter", "piano editoriale")):
            return "content_director"
        if any(term in normalized for term in ("obiettivo", "obiettivi", "goal", "progresso", "priorità", "priorita")):
            return "goal_advisor"
        if any(term in normalized for term in ("business", "strategia", "strategy", "monetizzazione", "audience", "lead", "clienti")):
            return "strategy_consultant"
        return "executive_team"

    def _executive_summary(self, user_message: str, direct_answer: str, role: str) -> str:
        direct_answer = self._compact_mobile_line(direct_answer, max_chars=220)
        if role == "content_director":
            return f"Come Content Director: {direct_answer or 'la richiesta riguarda un output contenuto da rendere eseguibile.'}"
        if role == "strategy_consultant":
            return f"Come Strategy Consultant: {direct_answer or 'la richiesta va tradotta in priorita e decisioni operative.'}"
        if role == "goal_advisor":
            return f"Stato obiettivi: {direct_answer or 'la richiesta riguarda progresso, priorita e prossime azioni.'}"
        return direct_answer or "Il team executive ha sintetizzato la richiesta in una risposta operativa."

    def _executive_recommendations(self, user_message: str, role: str) -> list[str]:
        if role == "content_director":
            return [
                "Trasforma l'idea in un framework pronto da eseguire: hook, struttura, CTA e canale.",
                "Mantieni il contenuto centrato su finance, fiducia e conversione audience.",
            ]
        if role == "strategy_consultant":
            return [
                "Concentra risorse sul vincolo che sblocca piu crescita o monetizzazione.",
                "Converti la raccomandazione in task misurabili entro questa settimana.",
            ]
        if role == "goal_advisor":
            return [
                "Prioritizza i task che supportano direttamente gli obiettivi attivi.",
                "Aggiorna il progresso con una metrica semplice e verificabile.",
            ]
        if "?" in user_message:
            return ["Usa la risposta per decidere il prossimo passo, non solo per accumulare informazioni."]
        return ["Trasforma questa risposta in un task operativo con owner, priorita e obiettivo collegato."]

    def _render_section(
        self,
        section_key: str,
        content: Any,
        markdown: bool,
        numbered: bool = False,
    ) -> str:
        points = self._dedupe_points(self._coerce_points(content))
        if not points:
            return ""

        title = SECTION_TITLES.get(section_key, section_key)
        if section_key == "daily_briefing":
            body = "\n".join(self._escape_html(point) if markdown else point for point in points[:2])
        elif numbered:
            body = "\n".join(
                f"{index}. {self._escape_html(point) if markdown else point}"
                for index, point in enumerate(points, start=1)
            )
        else:
            body = "\n".join(f"• {self._escape_html(point) if markdown else point}" for point in points)

        if markdown:
            return f"<b>{self._escape_html(title)}</b>\n{body}"
        return f"{title}\n{body}"

    def _join_sections(self, sections: list[str]) -> str:
        return "\n\n".join(section.strip() for section in sections if section and section.strip())

    def _coerce_points(self, value: Any, limit: int = 8) -> list[str]:
        if value in (None, "", []):
            return []
        if isinstance(value, str):
            text = self._clean_text(value)
            raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
            if len(raw_lines) <= 1:
                raw_lines = re.split(r"(?<=[.!?])\s+", text)
            return self._dedupe_points(
                [
                    self._compact_mobile_line(self._clean_point(line))
                    for line in raw_lines
                    if self._is_useful_sentence(self._clean_point(line))
                ]
            )[:limit]
        if isinstance(value, dict):
            return [self._compact_mobile_line(self._flatten_item(value))]
        if isinstance(value, (list, tuple, set)):
            points = []
            for item in value:
                if item in (None, ""):
                    continue
                if isinstance(item, str):
                    points.extend(self._coerce_points(item, limit=limit))
                else:
                    points.append(self._compact_mobile_line(self._flatten_item(item)))
            return self._dedupe_points([point for point in points if point])[:limit]
        return [self._compact_mobile_line(str(value))]

    def _compact_mobile_line(self, text: str, max_chars: int = 170) -> str:
        text = self._remove_raw_metadata(" ".join(str(text).split()))
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 3].rstrip()}..."

    def _remove_raw_metadata(self, text: str) -> str:
        text = re.sub(r"\b(id|source_task_id|matched_keywords|score|created_at|updated_at|completed_at):\s*[^-]+", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\btarget=", "target: ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bprogress=", "progresso: ", text, flags=re.IGNORECASE)
        text = re.sub(r"\[([^\]]+)\]", r"(\1)", text)
        text = re.sub(r"\s+-\s+-\s+", " - ", text)
        return text.strip(" -")

    def _extract_structured(self, text: str) -> Any | None:
        stripped = text.strip()
        if not stripped:
            return None

        candidate = self._strip_code_fence(stripped)
        parsed = self._parse_structured(candidate)
        if parsed is not None:
            return parsed
        return self._parse_embedded_structured(candidate)

    def _clean_text(self, text: str) -> str:
        text = self._structured_to_text(text)
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"#{1,6}\s*", "", text)
        text = text.replace("---", "\n")
        text = re.sub(r"[*~>]+", "", text)
        text = re.sub(r"[•●◆◇▶▷]+", "-", text)
        text = re.sub(r"\[[a-z_]+\]", "", text)
        text = re.sub(r"\[([^\]]+)\]", r"(\1)", text)
        text = re.sub(r"\btarget=", "target: ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bprogress=", "progresso: ", text, flags=re.IGNORECASE)
        text = self._strip_raw_structure_tokens(text)
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
            "contenuto",
            "contenuti",
            "idee",
            "finance",
            "finanza",
            "brand",
            "task",
            "priorità",
            "priorita",
            "briefing",
            "review",
            "decisione",
            "decisioni",
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
            normalized_line = line.lower().strip(" :")
            if self._starts_any_section_label(line) or normalized_line in SECTION_LABELS:
                continue
            if normalized_line.startswith(("briefing giornaliero", "review settimanale")):
                continue
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

    def _extract_label_points(self, text: str, labels: tuple[str, ...], limit: int) -> list[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        points: list[str] = []
        capture = False
        normalized_labels = tuple(label.lower().strip(":") for label in labels)

        for line in lines:
            normalized = line.lower().strip(" :")
            if any(normalized.startswith(label) for label in normalized_labels):
                capture = True
                _, _, inline_value = line.partition(":")
                if inline_value.strip():
                    points.append(self._clean_point(inline_value))
                continue

            if capture and self._starts_any_section_label(line):
                break
            if capture:
                point = self._clean_point(line)
                if self._is_useful_sentence(point):
                    points.append(point)
                if len(points) >= limit:
                    break

        return self._dedupe_points(points)[:limit]

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
        return self._escape_html(text) if markdown else text

    def _render_sections(self, sections: list[tuple[str, str | list[str]]], markdown: bool, user_message: str) -> str:
        rendered_sections = []
        for title, content in sections:
            if isinstance(content, list):
                body_lines = [line for line in content if line.strip()]
                if not body_lines:
                    continue
                if markdown:
                    if title in {"Priorities", "Next Steps"}:
                        body = self._render_numbered_lines(body_lines) if title == "Priorities" else self._render_bullet_lines(body_lines)
                    elif self._is_content_ideas_request(user_message):
                        body = self._render_content_ideas(body_lines)
                    else:
                        body = self._render_bullet_lines(body_lines)
                else:
                    if title in {"Priorities", "Next Steps"}:
                        body = "\n".join(f"{index}. {line}" for index, line in enumerate(body_lines, start=1))
                    else:
                        body = "\n".join(f"- {line}" for line in body_lines)
            else:
                if not content.strip():
                    continue
                body = self._escape_html(content) if markdown else content

            if markdown:
                rendered_sections.append(f"<b>{self._escape_html(self._section_title(title))}</b>\n{body}")
            else:
                rendered_sections.append(f"{self._section_title(title)}\n{body}")

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
            suffix = self._escape_html(suffix)
        return f"{truncated}\n\n{suffix}"

    def _render_plan_lines(self, lines: list[str], user_message: str) -> str:
        if self._is_action_plan_request(user_message):
            return "\n".join(f"• {self._escape_html(line)}" for line in lines)
        return "\n".join(f"• {self._escape_html(line)}" for line in lines)

    def _render_numbered_lines(self, lines: list[str]) -> str:
        return "\n".join(f"{index}. {self._escape_html(line)}" for index, line in enumerate(lines, start=1))

    def _render_bullet_lines(self, lines: list[str]) -> str:
        return "\n".join(f"• {self._escape_html(line)}" for line in lines)

    def _render_content_ideas(self, lines: list[str]) -> str:
        rendered = []
        for index, line in enumerate(lines, start=1):
            title, _, detail = line.partition(":")
            if detail:
                rendered.append(f"{index}. <b>{self._escape_html(title.strip())}</b>\n   {self._escape_html(detail.strip())}")
            else:
                rendered.append(f"{index}. {self._escape_html(line)}")
        return "\n\n".join(rendered)

    def _is_content_ideas_request(self, message: str) -> bool:
        normalized = message.lower()
        return any(term in normalized for term in ("idee", "ideas", "format", "contenuti", "content ideas"))

    def _is_action_plan_request(self, message: str) -> bool:
        normalized = message.lower()
        return any(term in normalized for term in ("checklist", "azione", "to do", "todo", "piano d'azione", "action plan"))

    def _is_briefing_request(self, message: str) -> bool:
        normalized = message.lower()
        return any(term in normalized for term in ("briefing", "giornaliero", "daily"))

    def _escape_html(self, text: str) -> str:
        return html.escape(text, quote=False)

    def _section_title(self, title: str) -> str:
        titles = {
            "Daily Briefing": "📅 Daily Briefing",
            "Priorities": "🎯 Priorities",
            "Analysis": "💡 Analysis",
            "Next Steps": "🚀 Next Steps",
            "Wins": "🏆 Wins",
            "Blockers": "🚧 Blockers",
            "Recommendations": "📌 Recommendations",
        }
        return titles.get(title, title)

    def _structured_to_text(self, text: str) -> str:
        stripped = text.strip()
        if not stripped:
            return ""

        candidate = self._strip_code_fence(stripped)
        parsed = self._parse_structured(candidate)
        if parsed is None:
            parsed = self._parse_embedded_structured(candidate)
        if parsed is None:
            return text
        return self._flatten_structured(parsed)

    def _strip_code_fence(self, text: str) -> str:
        match = re.fullmatch(r"```(?:json|python)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else text

    def _parse_structured(self, text: str) -> Any | None:
        if not text.startswith(("{", "[")):
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return None
        return parsed if isinstance(parsed, (dict, list, tuple)) else None

    def _parse_embedded_structured(self, text: str) -> Any | None:
        decoder = json.JSONDecoder()
        candidates: list[tuple[int, Any]] = []

        for index, char in enumerate(text):
            if char not in "{[":
                continue
            try:
                parsed, end = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, (dict, list)):
                candidates.append((end, parsed))

        if not candidates:
            return None

        for _, parsed in sorted(candidates, key=lambda item: item[0], reverse=True):
            if isinstance(parsed, dict) and {"summary", "plans", "ideas", "tasks"}.intersection(parsed):
                return parsed

        return max(candidates, key=lambda item: item[0])[1]

    def _flatten_structured(self, value: Any) -> str:
        if isinstance(value, dict):
            return self._flatten_dict(value)
        if isinstance(value, (list, tuple)):
            return "\n".join(self._flatten_item(item) for item in value if item)
        return str(value)

    def _flatten_dict(self, payload: dict[str, Any]) -> str:
        preferred_order = (
            "summary",
            "title",
            "wins",
            "blockers",
            "priorities",
            "recommendations",
            "analysis",
            "plans",
            "ideas",
            "tasks",
            "next_steps",
        )
        lines: list[str] = []
        used_keys = set()

        for key in preferred_order:
            if key in payload:
                lines.extend(self._flatten_key_value(key, payload[key]))
                used_keys.add(key)

        for key, value in payload.items():
            if key not in used_keys:
                lines.extend(self._flatten_key_value(str(key), value))

        return "\n".join(line for line in lines if line.strip())

    def _flatten_key_value(self, key: str, value: Any) -> list[str]:
        label = self._humanize_key(key)
        if isinstance(value, dict):
            return [f"{label}: {self._flatten_item(value)}"]
        if isinstance(value, (list, tuple)):
            lines = [f"{label}:"]
            lines.extend(f"- {self._flatten_item(item)}" for item in value if item)
            return lines
        if value is None or value == "":
            return []
        return [f"{label}: {value}"]

    def _flatten_item(self, item: Any) -> str:
        if not isinstance(item, (dict, list, tuple, str)) and hasattr(item, "__dict__"):
            item = {
                key: getattr(item, key)
                for key in (
                    "title",
                    "platform",
                    "priority",
                    "status",
                    "objective",
                    "hook",
                    "due_date",
                    "estimated_minutes",
                    "decision",
                    "reasoning",
                    "expected_outcome",
                )
                if hasattr(item, key) and getattr(item, key) not in (None, "")
            }
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("name") or "Elemento").strip()
            details = []
            for key in ("platform", "priority", "status", "objective", "hook", "due_date", "estimated_minutes"):
                value = item.get(key)
                if value not in (None, ""):
                    details.append(f"{self._humanize_key(key)}: {value}")
            return f"{title} - " + " - ".join(details) if details else title
        if isinstance(item, (list, tuple)):
            return " - ".join(str(part) for part in item if part not in (None, ""))
        return str(item)

    def _humanize_key(self, key: str) -> str:
        labels = {
            "summary": "Sintesi",
            "title": "Titolo",
            "wins": "Vittorie",
            "blockers": "Blocchi",
            "priorities": "Priorita",
            "recommendations": "Raccomandazioni",
            "analysis": "Analisi",
            "plans": "Piano",
            "ideas": "Idee",
            "tasks": "Task",
            "next_steps": "Prossimi passi",
            "platform": "Canale",
            "priority": "Priorita",
            "status": "Stato",
            "objective": "Obiettivo",
            "hook": "Hook",
            "due_date": "Scadenza",
            "estimated_minutes": "Minuti",
        }
        return labels.get(key, key.replace("_", " ").strip().title())

    def _strip_raw_structure_tokens(self, text: str) -> str:
        if not re.search(r"[{}\[\]]", text):
            return text
        text = re.sub(r'["{}\\[\\]]', "", text)
        text = re.sub(r"\bNone\b|\bnull\b", "", text)
        text = re.sub(r"\bTrue\b|\bFalse\b|\btrue\b|\bfalse\b", "", text)
        text = re.sub(r",\s*(?=[A-Za-z_ ]+:)", "\n", text)
        text = re.sub(r":\s*\n", ":\n", text)
        return text

    def _clean_point(self, line: str) -> str:
        line = re.sub(r"^[-\d. )]+", "", line).strip()
        line = self._remove_internal_labels(line)
        line = self._strip_raw_structure_tokens(line)
        return " ".join(line.split())

    def _dedupe_points(self, points: list[str]) -> list[str]:
        deduped = []
        seen = set()
        for point in points:
            key = point.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(point)
        return deduped

    def _starts_any_section_label(self, line: str) -> bool:
        normalized = line.lower().strip()
        return any(normalized.startswith(f"{label}:") for label in SECTION_LABELS)

    def _looks_like_labeled_digest(self, text: str) -> bool:
        lowered = text.lower()
        return sum(1 for label in SECTION_LABELS if f"{label}:" in lowered) >= 2

    def _needs_compact_title(self, user_message: str, title: str) -> bool:
        normalized = user_message.lower()
        operational_terms = ("briefing", "review", "task", "priorit", "idee", "contenut")
        return len(title) > 140 and any(term in normalized for term in operational_terms)

    def _digest_title(self, user_message: str) -> str:
        normalized = user_message.lower()
        if "briefing" in normalized or "giornalier" in normalized:
            return "Briefing operativo pronto per oggi."
        if "review" in normalized or "settimanal" in normalized:
            return "Review operativa pronta."
        if "task" in normalized or "priorit" in normalized:
            return "Priorita operative aggiornate."
        if "idee" in normalized or "contenut" in normalized:
            return "Idee contenuto organizzate per l'azione."
        return "Sintesi operativa pronta."

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
            "brain state summary",
            "questa sintesi rappresenta",
            "identita:",
            "identità:",
            "business profile:",
            "obiettivi e priorita:",
            "obiettivi e priorità:",
            "brand positioning:",
            "content strategy:",
            "preferenze:",
            "user prefers",
            "decisioni:",
            "lessons:",
            "tasks:",
            "agent instructions:",
            "active strategic goals",
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
