from __future__ import annotations

import ast
import html
import json
import re
from typing import Any


EXECUTIVE_REPORT_TERMS = (
    "make a report",
    "executive report",
    "formal analysis",
    "formal report",
    "report formale",
    "rapporto formale",
    "analisi formale",
    "business report",
    "formato executive",
    "executive summary",
)


class ResponseFormatter:
    """Adaptive final response layer for chat, API and Telegram."""

    def __init__(self, telegram_max_chars: int = 2500):
        self.telegram_max_chars = telegram_max_chars

    def format_chat(self, user_message: str, raw_reply: str) -> str:
        max_chars = None if self._wants_detail(user_message) else self.telegram_max_chars
        return self._format(user_message, raw_reply, max_chars=max_chars, markdown=False)

    def format_telegram(self, user_message: str, raw_reply: str) -> str:
        max_chars = None if self._wants_detail(user_message) else self.telegram_max_chars
        return self._format(user_message, raw_reply, max_chars=max_chars, markdown=True)

    def format_task_list(self, tasks: Any, markdown: bool = True) -> str:
        return self._render_dashboard(
            goals=[],
            priorities=self._coerce_points(tasks) or ["Nessun task operativo disponibile."],
            progress=[],
            risks=[],
            next_actions=["Scegli il primo task e chiudilo prima di aprire nuove idee."],
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
        progress = self._coerce_points(wins, limit=4) + self._coerce_points(analysis, limit=3)
        return self._render_dashboard(
            goals=[],
            priorities=self._coerce_points(priorities, limit=6),
            progress=progress,
            risks=self._coerce_points(blockers, limit=4),
            next_actions=self._coerce_points(next_steps, limit=5) or self._coerce_points(recommendations, limit=5),
            markdown=markdown,
        )

    def format_review(self, review: Any, markdown: bool = True) -> str:
        payload = review if isinstance(review, dict) else {}
        return self._render_dashboard(
            goals=self._coerce_points(payload.get("alignment"), limit=4),
            priorities=self._coerce_points(payload.get("priorities"), limit=5),
            progress=self._coerce_points(payload.get("progress") or payload.get("completed_tasks") or review, limit=5),
            risks=self._coerce_points(payload.get("blockers") or payload.get("risks"), limit=4),
            next_actions=self._coerce_points(payload.get("recommendations"), limit=5)
            or ["Scegli una priorita per la prossima settimana e trasformala in 3 task."],
            markdown=markdown,
        )

    def format_decision(self, decision: Any, markdown: bool = True) -> str:
        payload = decision if isinstance(decision, dict) else {"decision": decision}
        text = self._clean_text(
            "\n".join(
                str(value)
                for value in (
                    payload.get("context"),
                    payload.get("decision"),
                    payload.get("reasoning"),
                    payload.get("expected_outcome"),
                )
                if value
            )
        )
        return self._render_strategy(
            user_message="decision support",
            cleaned=text or self._flatten_structured(payload),
            markdown=markdown,
        )

    def format_content_plan(self, plan: Any, markdown: bool = True) -> str:
        payload = plan if isinstance(plan, dict) else {}
        content = self._flatten_structured(payload) if payload else self._clean_text(str(plan))
        return self._render_content_creation(content, user_message="content plan", markdown=markdown)

    def format_recommendations(self, recommendations: Any, markdown: bool = True) -> str:
        points = self._coerce_points(recommendations)
        return self._render_conversation(
            cleaned="\n".join(points) if points else "Mi concentrerei su una sola mossa concreta e misurabile.",
            markdown=markdown,
        )

    def quality_score(self, text: str) -> float:
        if not text.strip():
            return 0.0

        score = 1.0
        lower = text.lower()
        if len(text) > self.telegram_max_chars:
            score -= min((len(text) - self.telegram_max_chars) / self.telegram_max_chars, 0.35)
        if any(marker in lower for marker in ("memory context", "score=", "matched=", "dettagli agenti", "{", "}", "['", "']")):
            score -= 0.2
        if "executive summary" in text and not any(term in lower for term in EXECUTIVE_REPORT_TERMS):
            score -= 0.25
        if self._has_duplicate_lines(text):
            score -= 0.15
        if "\n\n" in text:
            score += 0.05
        return round(max(0.0, min(1.0, score)), 3)

    def _format(self, user_message: str, raw_reply: str, max_chars: int | None, markdown: bool) -> str:
        parsed = self._extract_structured(raw_reply)
        if parsed is not None:
            structured = self._format_structured(user_message, parsed, markdown=markdown)
            if structured:
                return self._truncate(structured, max_chars, markdown=markdown)

        if "proactive daily business briefing" in user_message.lower():
            formatted = self._render_plain_text(str(raw_reply), markdown=markdown)
            return self._truncate(formatted, max_chars, markdown=markdown)

        cleaned = self._clean_text(raw_reply)
        if not cleaned:
            cleaned = "Mi manca un dato essenziale per rispondere bene. Qual e il risultato concreto che vuoi ottenere?"

        if self._needs_executive_report(user_message):
            formatted = self._render_executive_report(cleaned, markdown=markdown)
            return self._truncate(formatted, max_chars, markdown=markdown)

        intent = self._detect_intent(user_message)
        mode = self._mode_for_intent(intent)

        if mode == "content_creation":
            formatted = self._render_content_creation(cleaned, user_message=user_message, markdown=markdown)
        elif mode == "strategy":
            formatted = self._render_strategy(user_message, cleaned, markdown=markdown)
        elif mode == "dashboard":
            formatted = self._render_dashboard_from_text(cleaned, markdown=markdown)
        elif mode == "research":
            formatted = self._render_research(user_message, cleaned, markdown=markdown)
        else:
            formatted = self._render_conversation(cleaned, markdown=markdown)

        return self._truncate(formatted, max_chars, markdown=markdown)

    def _detect_intent(self, user_message: str) -> str:
        text = user_message.lower().strip()

        if self._is_content_intent(text):
            if any(term in text for term in ("carousel", "carosello")):
                return "carousel"
            if any(term in text for term in ("reel", "tiktok", "video", "short", "script")):
                return "video"
            if "newsletter" in text:
                return "newsletter"
            if any(term in text for term in ("linkedin", "post")):
                return "linkedin"
            if "instagram" in text:
                return "instagram"
            return "linkedin"
        if any(term in text for term in ("decidere", "decisione", "scelta", "scegliere", "conviene", "cosa faresti")):
            return "decision_support"
        if any(term in text for term in ("carousel", "carosello")):
            return "carousel"
        if any(term in text for term in ("linkedin", "post linkedin")):
            return "linkedin" if self._looks_like_content_request(text) else "business_strategy"
        if any(term in text for term in ("instagram", "reel", "stories", "story")):
            return "instagram" if self._looks_like_content_request(text) else "business_strategy"
        if any(term in text for term in ("tiktok", "video", "short", "youtube", "script")):
            return "video" if self._looks_like_content_request(text) else "business_strategy"
        if "newsletter" in text:
            return "newsletter" if self._looks_like_content_request(text) else "business_strategy"

        if any(term in text for term in ("obiettivi", "obiettivo", "goals", "goal")):
            return "goals"
        if any(term in text for term in ("task", "cosa devo fare", "cosa dovrei fare", "completato")):
            return "tasks"
        if any(term in text for term in ("priorita", "priorità", "briefing", "review", "settimanale", "giornaliero")):
            return "review"

        if any(term in text for term in ("ricerca", "research", "fonti", "evidence", "approfondisci")):
            return "research"
        if any(term in text for term in ("analizza", "analisi", "market size", "mercato", "benchmark", "competitor")):
            return "analysis"
        if any(term in text for term in ("confronta", "comparazione", "comparison", "vs", "pro e contro")):
            return "comparison"

        if any(term in text for term in ("strategia", "strategy", "business", "monetizzazione", "funnel", "posizionamento", "offerta", "crescita", "growth", "audience", "personal brand")):
            return "business_strategy"

        if any(term in text for term in ("consiglio", "consigli", "secondo te", "aiutami", "coach", "coaching")):
            return "advice"
        if text.endswith("?") or len(text.split()) <= 10:
            return "simple_question"
        return "coaching"

    def _mode_for_intent(self, intent: str) -> str:
        if intent in {"simple_question", "advice", "coaching"}:
            return "conversation"
        if intent in {"business_strategy", "decision_support"}:
            return "strategy"
        if intent in {"carousel", "linkedin", "instagram", "newsletter", "video"}:
            return "content_creation"
        if intent in {"goals", "tasks", "priorities", "review"}:
            return "dashboard"
        if intent in {"analysis", "research", "comparison"}:
            return "research"
        return "conversation"

    def _looks_like_content_request(self, text: str) -> bool:
        action_terms = ("scrivi", "crea", "creare", "prepara", "genera", "fammi", "dammi", "proponi", "idee", "script", "copy", "caption", "hook", "versione", "trasformalo", "trasforma", "adattalo", "adatta")
        return any(term in text for term in action_terms)

    def _is_content_intent(self, text: str) -> bool:
        if "previous active intent: content_creation" in text:
            return True
        direct_terms = (
            "crea un contenuto",
            "creare un contenuto",
            "versione reel",
            "versione linkedin",
            "versione tiktok",
            "versione carousel",
            "versione carosello",
            "trasformalo in",
            "adattalo per",
            "adatta per",
        )
        if any(term in text for term in direct_terms):
            return True
        content_terms = ("post", "reel", "carousel", "carosello", "script", "caption", "linkedin", "tiktok", "instagram", "newsletter", "video", "contenuto", "contenuti")
        action_terms = ("crea", "creare", "scrivi", "fammi", "prepara", "genera", "dammi", "proponi", "sviluppa", "versione", "trasforma", "trasformalo", "adatta", "adattalo")
        return any(term in text for term in content_terms) and any(action in text for action in action_terms)

    def _render_conversation(self, cleaned: str, markdown: bool) -> str:
        lines = self._dedupe_points(self._extract_readable_lines(cleaned, limit=7))
        if not lines:
            lines = ["Ti risponderei partendo dal punto piu pratico: chiarire prima la prossima decisione."]

        paragraphs: list[str] = []
        for line in lines[:4]:
            if self._looks_like_action(line):
                continue
            paragraphs.append(self._paragraph(line, markdown))
            if len(paragraphs) >= 2:
                break

        action_lines = [line for line in lines if self._looks_like_action(line)]
        if action_lines:
            paragraphs.append(self._render_list(action_lines[:3], markdown=markdown, numbered=True))

        if not paragraphs:
            paragraphs = [self._paragraph(lines[0], markdown)]
        return self._join_sections(paragraphs)

    def _render_strategy(self, user_message: str, cleaned: str, markdown: bool) -> str:
        points = self._dedupe_points(self._extract_readable_lines(cleaned, limit=12))
        main = points[:1] or ["La scelta va valutata rispetto a posizionamento, ritorno atteso e costo operativo."]
        current = points[1:3] or ["Il contesto va semplificato: focus su una leva principale, non su troppe iniziative insieme."]
        options = self._strategy_options(user_message, points)
        recommendation = self._remove_overlaps(self._pick_recommendation(points), main + current + options)
        if not recommendation:
            recommendation = ["Sceglierei l'opzione piu misurabile e reversibile."]
        next_move = self._remove_overlaps(self._next_moves(user_message, points), main + current + options + recommendation)
        if not next_move:
            next_move = self._default_next_moves(user_message)

        return self._join_sections(
            [
                self._section("🎯 Main idea", main, markdown, paragraph=True),
                self._section("Current situation", current, markdown),
                self._section("Strategic options", options, markdown, numbered=True),
                self._section("Recommendation", recommendation, markdown, paragraph=True),
                self._section("Next move", next_move, markdown, numbered=True),
            ]
        )

    def _render_content_creation(self, cleaned: str, user_message: str, markdown: bool) -> str:
        content = self._strip_explanatory_preface(cleaned)
        blocks = [] if self._contains_internal_context(content) else self._content_blocks(content)
        blocks = self._ensure_complete_content_blocks(blocks, user_message)

        rendered = []
        for title, body in blocks:
            title = self._normalize_content_title(title)
            if markdown:
                rendered.append(f"<b>{self._escape_html(title)}</b>\n{self._escape_html(body)}")
            else:
                rendered.append(f"{title}\n{body}")
        return self._join_sections(rendered)

    def _ensure_complete_content_blocks(self, blocks: list[tuple[str, str]], user_message: str) -> list[tuple[str, str]]:
        normalized_request = user_message.lower()
        normalized_titles = {self._normalize(title) for title, _ in blocks}
        asks_only_hooks = any(term in normalized_request for term in ("solo hook", "soltanto hook", "only hooks", "solo gli hook"))
        if asks_only_hooks:
            return blocks

        target_format = self._requested_content_format(normalized_request)
        topic = self._content_topic_from_text(user_message, blocks)
        generic_only = len(blocks) == 1 and self._normalize(blocks[0][0]) in {"contenuto", "content"}
        completed = [] if generic_only and target_format in {"linkedin", "reel_tiktok", "carousel"} else list(blocks)
        has_hook = any("hook" in title for title in normalized_titles)
        has_cta = any("cta" in title or "call to action" in title for title in normalized_titles)
        has_body = any(title in normalized_titles for title in ("body", "corpo", "script", "post"))
        has_visual = any("visual" in title or "direzione" in title for title in normalized_titles)
        has_slide = any("slide" in title for title in normalized_titles)

        if target_format == "carousel":
            if not has_slide:
                completed.extend(
                    [
                        ("Titolo", f"{topic}: cosa capire prima di investire"),
                        ("Slide 1", f"Gli {topic} sembrano semplici, ma non vanno scelti a caso."),
                        ("Slide 2", "Il primo errore e guardare solo il rendimento passato."),
                        ("Slide 3", "La domanda giusta e: quale indice replica, quali costi ha e quanto e coerente col tuo obiettivo?"),
                        ("Slide 4", "Usali come strumenti, non come scorciatoie: metodo, orizzonte temporale e rischio vengono prima."),
                        ("Slide finale", "Prima di scegliere, scrivi obiettivo, durata dell'investimento e rischio massimo accettabile."),
                    ]
                )
            if not has_cta:
                completed.append(("CTA", "Salva il carosello e usalo come checklist prima di valutare un ETF."))
            return completed

        if target_format == "reel_tiktok":
            if not has_hook:
                completed.insert(0, ("Hook iniziale", f"Gli {topic} non sono complicati. Il problema e che molti li comprano senza sapere cosa stanno comprando."))
            if not has_body:
                completed.append(
                    (
                        "Script parlato",
                        "Quando valuti un ETF, non partire dal rendimento passato. "
                        "Parti da tre cose: quale indice replica, quanto costa ogni anno e se e coerente con il tuo orizzonte temporale. "
                        "Un ETF puo essere uno strumento semplice, ma solo se lo inserisci dentro un metodo. "
                        "Se lo scegli perche 'sta salendo', non stai investendo: stai inseguendo.",
                    )
                )
            if not has_visual:
                completed.append(("Visual / scena", "Parla in camera. A schermo mostra 3 parole: indice, costi, orizzonte. Chiudi con una mini-checklist visuale."))
            if not has_cta:
                completed.append(("CTA finale", "Salva questo video prima di scegliere il prossimo ETF."))
            if "caption breve" not in normalized_titles and "caption" not in normalized_titles:
                completed.append(("Caption breve", f"Prima di scegliere un ETF, guarda queste 3 cose. Metodo prima del rendimento."))
            return completed

        if target_format == "linkedin":
            if not has_hook:
                completed.insert(0, ("Hook", f"Gli {topic} sono semplici da comprare. Ma non sempre sono semplici da capire."))
            if not has_body:
                completed.append(
                    (
                        "Corpo del post",
                        "Molti investitori scelgono un ETF partendo dalla domanda sbagliata: 'quanto ha reso?'.\n\n"
                        "La domanda migliore e: cosa replica? Quanto costa? E soprattutto: e coerente con il mio obiettivo?\n\n"
                        "Un ETF non e una strategia. E uno strumento.\n\n"
                        "La strategia nasce prima: orizzonte temporale, rischio accettabile, capitale da investire e regole "
                        "per non cambiare idea al primo movimento di mercato.\n\n"
                        "Se parti dallo strumento, rischi di inseguire performance. Se parti dal metodo, costruisci decisioni piu solide.",
                    )
                )
            if not has_cta:
                completed.append(("CTA", "Prima di scegliere il prossimo ETF, scrivi nero su bianco obiettivo, durata e rischio massimo."))
            if "hashtag" not in normalized_titles:
                completed.append(("Hashtag opzionali", "#ETF #investimenti #finanzapersonale #educazionefinanziaria"))
            return completed

        if not has_body and len(completed) == 1:
            completed.append(("Body", "Sviluppa l'idea con contesto, valore pratico e un esempio concreto."))
        if not has_cta:
            completed.append(("CTA", "Salva questo contenuto e applica il primo passaggio oggi."))
        return completed

    def _requested_content_format(self, normalized_request: str) -> str:
        if any(term in normalized_request for term in ("reel", "tiktok", "short", "video")):
            return "reel_tiktok"
        if any(term in normalized_request for term in ("carousel", "carosello")):
            return "carousel"
        if "newsletter" in normalized_request:
            return "newsletter"
        if any(term in normalized_request for term in ("linkedin", "post")):
            return "linkedin"
        return "linkedin"

    def _content_topic_from_text(self, user_message: str, blocks: list[tuple[str, str]]) -> str:
        text = user_message
        joined = " ".join(body for _, body in blocks)
        if "etf" in f"{text} {joined}".lower():
            return "ETF"
        topic_patterns = (
            r"riguardo\s+([^.\n]+)",
            r"sugli?\s+([^.\n]+)",
            r"su\s+([^.\n]+)",
            r"about\s+([^.\n]+)",
        )
        for pattern in topic_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return self._clean_content_topic(match.group(1))
        return "questo tema"

    def _contains_internal_context(self, text: str) -> bool:
        lowered = text.lower()
        return any(
            marker in lowered
            for marker in (
                "role routing",
                "conversation state",
                "brain state summary",
                "the user is sending a follow-up message",
                "previous active topic",
                "previous generated content",
                "memorie usate",
                "completion rules",
            )
        )

    def _clean_content_topic(self, topic: str) -> str:
        topic = re.sub(r"\b(per|il|la|lo|gli|le|un|una|di|del|della|nel|nella|mio|tuo|semplice|contenuto)\b", " ", topic, flags=re.IGNORECASE)
        topic = re.sub(r"\s+", " ", topic).strip(" .:;?")
        return topic.upper() if topic.lower() == "etf" else topic

    def _render_dashboard_from_text(self, cleaned: str, markdown: bool) -> str:
        points = self._dedupe_points(self._extract_readable_lines(cleaned, limit=14))
        goals = [point for point in points if self._contains_any(point, ("obiettivo", "goal", "brand", "business"))][:4]
        priorities = [point for point in points if self._contains_any(point, ("prior", "task", "fare", "pubblica", "crea", "scrivi", "aggiorna", "chiudi"))][:5]
        progress = [point for point in points if self._contains_any(point, ("progress", "complet", "fatto", "win", "avanz"))][:4]
        risks = [point for point in points if self._contains_any(point, ("risch", "blocco", "problema", "ritardo", "dispersione"))][:4]
        next_actions = [point for point in points if self._looks_like_action(point)][:5]

        return self._render_dashboard(goals, priorities, progress, risks, next_actions, markdown=markdown)

    def _render_dashboard(
        self,
        goals: list[str],
        priorities: list[str],
        progress: list[str],
        risks: list[str],
        next_actions: list[str],
        markdown: bool,
    ) -> str:
        next_actions = self._remove_overlaps(next_actions, priorities)
        if not next_actions:
            next_actions = ["Chiudi la prima priorita e aggiorna lo stato prima di aggiungere nuovi task."]
        return self._join_sections(
            [
                self._section("🎯 Goals", goals or ["Focus: crescita del personal brand finance e sistema contenuti sostenibile."], markdown),
                self._section("📌 Priorities", priorities or ["Scegli una priorita operativa collegata a crescita, fiducia o monetizzazione."], markdown, numbered=True),
                self._section("✅ Progress", progress or ["Nessun avanzamento specifico rilevato nel messaggio."], markdown),
                self._section("⚠ Risks", risks or ["Il rischio principale e disperdere energie su troppe iniziative non collegate."], markdown),
                self._section("➡ Next actions", next_actions or ["Definisci il prossimo task concreto e chiudilo oggi."], markdown, numbered=True),
            ]
        )

    def _render_research(self, user_message: str, cleaned: str, markdown: bool) -> str:
        points = self._dedupe_points(self._extract_readable_lines(cleaned, limit=12))
        question = [user_message.strip()]
        answer = points[:2] or ["La risposta richiede una lettura dei dati disponibili e delle ipotesi operative."]
        explicit_conclusion = [point for point in points if self._contains_any(point, ("conclusione", "quindi", "in sintesi"))]
        evidence = self._remove_overlaps(points[2:6], explicit_conclusion) or ["Non sono presenti evidenze strutturate nella risposta di partenza."]
        conclusion = explicit_conclusion[:2] or points[6:8] or points[-1:]

        return self._join_sections(
            [
                self._section("Question", question, markdown, paragraph=True),
                self._section("Answer", answer, markdown, paragraph=True),
                self._section("Evidence", evidence, markdown),
                self._section("Conclusion", conclusion, markdown, paragraph=True),
            ]
        )

    def _render_executive_report(self, cleaned: str, markdown: bool) -> str:
        points = self._dedupe_points(self._extract_readable_lines(cleaned, limit=12))
        summary = points[:2] or ["Il punto principale e stato sintetizzato in forma direzionale."]
        analysis = points[2:6] or points[:3]
        recommendations = [point for point in points if self._looks_like_action(point)][:4] or points[6:9] or summary[:1]
        next_actions = self._remove_overlaps(recommendations[:3], recommendations) or ["Trasforma la raccomandazione principale in un task con metrica e scadenza."]

        return self._join_sections(
            [
                self._section("Executive Summary", summary, markdown, paragraph=True),
                self._section("Analysis", self._remove_overlaps(analysis, summary) or analysis, markdown),
                self._section("Recommendations", self._remove_overlaps(recommendations, summary + analysis) or recommendations, markdown),
                self._section("Next Actions", self._remove_overlaps(next_actions, recommendations) or next_actions, markdown, numbered=True),
            ]
        )

    def _section(
        self,
        title: str,
        content: Any,
        markdown: bool,
        numbered: bool = False,
        paragraph: bool = False,
    ) -> str:
        points = self._dedupe_points(self._coerce_points(content, limit=6))
        if not points:
            return ""

        if paragraph:
            body = self._paragraph(" ".join(points[:2]), markdown)
        else:
            body = self._render_list(points, markdown=markdown, numbered=numbered)

        if markdown:
            return f"<b>{self._escape_html(title)}</b>\n{body}"
        return f"{title}\n{body}"

    def _paragraph(self, text: str, markdown: bool) -> str:
        text = self._limit_sentences(" ".join(str(text).split()), max_sentences=3)
        return self._escape_html(text) if markdown else text

    def _render_list(self, points: list[str], markdown: bool, numbered: bool) -> str:
        clean_points = self._dedupe_points([self._compact_line(point) for point in points if point])[:6]
        if numbered:
            return "\n".join(
                f"{index}. {self._escape_html(point) if markdown else point}"
                for index, point in enumerate(clean_points, start=1)
            )
        return "\n".join(f"• {self._escape_html(point) if markdown else point}" for point in clean_points)

    def _render_plain_text(self, text: str, markdown: bool) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text.strip())
        return self._escape_html(text) if markdown else text

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

    def _clean_text(self, text: str) -> str:
        parsed = self._extract_structured(text)
        if parsed is not None:
            text = self._flatten_structured(parsed)

        text = re.sub(r"```(?:json|python)?\s*|\s*```", "", str(text), flags=re.IGNORECASE)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"</?[^>]+>", "", text)
        text = text.replace("\r\n", "\n")
        text = "\n".join(line for line in text.splitlines() if not self._is_internal_line(line))
        text = self._strip_raw_structure_tokens(text)
        text = re.sub(r"[*~]+", "", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _extract_structured(self, text: str) -> Any | None:
        stripped = str(text).strip()
        if not stripped:
            return None

        candidate = self._strip_code_fence(stripped)
        parsed = self._parse_structured(candidate)
        if parsed is not None:
            return parsed
        return self._parse_embedded_structured(candidate)

    def _strip_code_fence(self, text: str) -> str:
        match = re.fullmatch(r"```(?:json|python)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else text

    def _parse_structured(self, text: str) -> Any | None:
        stripped = text.strip()
        if not stripped.startswith(("{", "[")):
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
        try:
            parsed = ast.literal_eval(stripped)
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
        return max(candidates, key=lambda item: item[0])[1]

    def _flatten_structured(self, value: Any) -> str:
        if isinstance(value, dict):
            lines: list[str] = []
            for key, item in value.items():
                label = self._humanize_key(str(key))
                if isinstance(item, (list, tuple)):
                    lines.append(f"{label}:")
                    lines.extend(f"- {self._flatten_item(child)}" for child in item if child not in (None, ""))
                elif isinstance(item, dict):
                    lines.append(f"{label}: {self._flatten_item(item)}")
                elif item not in (None, ""):
                    lines.append(f"{label}: {item}")
            return "\n".join(lines)
        if isinstance(value, (list, tuple)):
            return "\n".join(self._flatten_item(item) for item in value if item not in (None, ""))
        return str(value)

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
            title = str(item.get("title") or item.get("name") or item.get("decision") or "Elemento").strip()
            details = []
            for key in ("platform", "priority", "status", "objective", "hook", "due_date", "estimated_minutes"):
                value = item.get(key)
                if value not in (None, ""):
                    details.append(f"{self._humanize_key(key)}: {value}")
            return f"{title} - " + " - ".join(details) if details else title
        if isinstance(item, (list, tuple)):
            return " - ".join(str(part) for part in item if part not in (None, ""))
        return str(item)

    def _coerce_points(self, value: Any, limit: int = 8) -> list[str]:
        if value in (None, "", []):
            return []
        if isinstance(value, str):
            return self._dedupe_points(self._extract_readable_lines(value, limit=limit))
        if isinstance(value, dict):
            return self._coerce_points(self._flatten_structured(value), limit=limit)
        if isinstance(value, (list, tuple, set)):
            points: list[str] = []
            for item in value:
                points.extend(self._coerce_points(item, limit=limit))
            return self._dedupe_points(points)[:limit]
        return [self._compact_line(str(value))]

    def _extract_readable_lines(self, text: str, limit: int = 10) -> list[str]:
        text = self._clean_text(text) if re.search(r"[{}\[\]`]", str(text)) else str(text)
        text = re.sub(r"\s+\d+[.)]\s+", "\n", text)
        raw_lines = []
        for line in text.splitlines():
            line = line.strip(" -•\t")
            if not line:
                continue
            pieces = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ù0-9#])", line)
            raw_lines.extend(piece.strip(" -•\t") for piece in pieces if piece.strip())

        points = []
        for line in raw_lines:
            line = self._clean_point(line)
            if not self._is_useful_line(line):
                continue
            points.append(self._compact_line(line))
            if len(points) >= limit:
                break
        return self._dedupe_points(points)

    def _clean_point(self, line: str) -> str:
        line = re.sub(r"^\d+[.)]\s*", "", line).strip()
        line = re.sub(r"^(analysis|recommendations|next actions|executive summary|sintesi|raccomandazioni|prossimi passi)\s*:\s*", "", line, flags=re.IGNORECASE)
        line = self._strip_raw_structure_tokens(line)
        if self._normalize(line) in {"executive summary", "analysis", "recommendations", "next actions"}:
            return ""
        return " ".join(line.split()).strip(" -")

    def _strip_raw_structure_tokens(self, text: str) -> str:
        text = re.sub(r"\b(id|source_task_id|matched_keywords|score|created_at|updated_at|completed_at)\s*[:=]\s*[^-;\n]+", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\bNone\b|\bnull\b|\bTrue\b|\bFalse\b|\btrue\b|\bfalse\b", "", text)
        if re.search(r"[{}\[\]]", text):
            text = re.sub(r'["{}\\[\\]]', "", text)
            text = re.sub(r",\s*(?=[A-Za-z_ ]+:)", "\n", text)
        return text.strip(" -:,")

    def _content_blocks(self, text: str) -> list[tuple[str, str]]:
        text = re.sub(
            r"\s+(?=(hook|corpo|body|slide\s*\d+|cta|caption|post|script|titolo|apertura|chiusura)\s*:)",
            "\n",
            text,
            flags=re.IGNORECASE,
        )
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        blocks: list[tuple[str, list[str]]] = []
        current_title = ""
        current_body: list[str] = []

        for line in lines:
            title_match = re.match(r"^(#{1,3}\s*)?(hook|slide\s*\d+|cta|caption|post|script|titolo|apertura|corpo|body|chiusura)\s*:?\s*(.*)$", line, flags=re.IGNORECASE)
            if title_match:
                if current_title or current_body:
                    blocks.append((current_title or "Contenuto", current_body))
                current_title = title_match.group(2).strip()
                current_body = [title_match.group(3).strip()] if title_match.group(3).strip() else []
            else:
                current_body.append(line)

        if current_title or current_body:
            blocks.append((current_title or "Contenuto", current_body))

        if not blocks:
            points = self._extract_readable_lines(text, limit=8)
            return [("Contenuto", "\n".join(points))] if points else []
        return [(title, "\n".join(body).strip()) for title, body in blocks if "\n".join(body).strip()]

    def _normalize_content_title(self, title: str) -> str:
        title = title.strip()
        if re.match(r"slide\s*\d+", title, flags=re.IGNORECASE):
            return title.title()
        if title.lower() == "hook":
            return "# Hook"
        if title.lower() == "cta":
            return "CTA"
        return title[:1].upper() + title[1:]

    def _strip_explanatory_preface(self, text: str) -> str:
        lines = []
        for line in text.splitlines():
            if re.match(r"^(ecco|certamente|ti preparo|qui sotto|versione pronta)", line.strip(), flags=re.IGNORECASE):
                continue
            lines.append(line)
        return "\n".join(lines).strip() or text.strip()

    def _strategy_options(self, user_message: str, points: list[str]) -> list[str]:
        option_points = [point for point in points if self._contains_any(point, ("opzione", "option", "scenario", "alternativa", "tradeoff"))]
        if option_points:
            return option_points[:4]
        if "newsletter" in user_message.lower():
            return [
                "Lanciare una newsletter pilota per validare promessa, frequenza e interesse.",
                "Aspettare e usarla solo quando offerta e posizionamento sono piu chiari.",
            ]
        return [
            "Focus stretto: una leva principale, un canale prioritario, una metrica.",
            "Approccio ampio: piu canali e piu test, ma con rischio maggiore di dispersione.",
        ]

    def _pick_recommendation(self, points: list[str]) -> list[str]:
        candidates = [point for point in points if self._looks_like_recommendation(point)]
        return candidates[:2] or points[:1] or ["Sceglierei l'opzione piu misurabile e reversibile."]

    def _next_moves(self, user_message: str, points: list[str]) -> list[str]:
        actions = [point for point in points if self._looks_like_action(point)]
        if actions:
            return actions[:3]
        return self._default_next_moves(user_message)

    def _default_next_moves(self, user_message: str) -> list[str]:
        if any(term in user_message.lower() for term in ("linkedin", "profilo")):
            return ["Riscrivi la headline.", "Definisci 3 pillar contenuto.", "Pubblica un post manifesto entro 24 ore."]
        if "tiktok" in user_message.lower():
            return ["Scegli 2 format ricorrenti.", "Scrivi 10 hook finance.", "Pubblica 3 video e misura retention."]
        return ["Definisci il test minimo.", "Scegli la metrica di successo.", "Rivedi la decisione dopo il primo dato concreto."]

    def _remove_overlaps(self, points: list[str], previous: list[str]) -> list[str]:
        previous_norm = " ".join(self._normalize(point) for point in previous)
        filtered = [point for point in points if self._normalize(point) not in previous_norm]
        return self._dedupe_points(filtered)

    def _limit_sentences(self, text: str, max_sentences: int) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        useful = [sentence.strip() for sentence in sentences if sentence.strip()]
        return " ".join(useful[:max_sentences])

    def _compact_line(self, text: str, max_chars: int = 190) -> str:
        text = " ".join(str(text).split())
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 3].rstrip()}..."

    def _dedupe_points(self, points: list[str]) -> list[str]:
        deduped = []
        seen = set()
        for point in points:
            key = self._normalize(point)
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(point)
        return deduped

    def _normalize(self, text: str) -> str:
        return re.sub(r"[^a-z0-9àèéìòù]+", " ", str(text).lower()).strip()

    def _contains_any(self, text: str, terms: tuple[str, ...]) -> bool:
        lowered = text.lower()
        return any(term in lowered for term in terms)

    def _looks_like_action(self, text: str) -> bool:
        return bool(
            re.search(
                r"\b(crea|scrivi|pubblica|scegli|misura|definisci|lancia|aggiorna|trasforma|testa|ottimizza|collega|riscrivi)\b",
                text.lower(),
            )
        )

    def _looks_like_recommendation(self, text: str) -> bool:
        return self._contains_any(text, ("consiglio", "raccomando", "conviene", "sceglierei", "meglio", "dovresti", "farei"))

    def _is_useful_line(self, line: str) -> bool:
        if len(line.strip()) < 4:
            return False
        lower = line.lower()
        noisy = (
            "memory context",
            "brain state summary",
            "dettagli agenti",
            "score=",
            "matched=",
            "source_task_id",
            "risposta finale locale",
            "manager agent",
            "research agent",
            "content agent",
            "active goals",
            "usa queste memorie",
        )
        return not any(marker in lower for marker in noisy)

    def _is_internal_line(self, line: str) -> bool:
        return not self._is_useful_line(line)

    def _has_duplicate_lines(self, text: str) -> bool:
        lines = [self._normalize(line) for line in text.splitlines() if self._normalize(line)]
        return len(lines) != len(set(lines))

    def _needs_executive_report(self, user_message: str) -> bool:
        lowered = user_message.lower()
        return any(term in lowered for term in EXECUTIVE_REPORT_TERMS)

    def _wants_detail(self, message: str) -> bool:
        lowered = message.lower()
        return any(term in lowered for term in ("dettaglio", "dettagliato", "approfondisci", "completo", "piano completo", "senza limiti"))

    def _humanize_key(self, key: str) -> str:
        labels = {
            "summary": "Sintesi",
            "title": "Titolo",
            "wins": "Progressi",
            "blockers": "Rischi",
            "priorities": "Priorita",
            "recommendations": "Azioni consigliate",
            "analysis": "Lettura",
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

    def _escape_html(self, text: str) -> str:
        return html.escape(str(text), quote=False)

    def _join_sections(self, sections: list[str]) -> str:
        return "\n\n".join(section.strip() for section in sections if section and section.strip())

    def _truncate(self, text: str, max_chars: int | None, markdown: bool = False) -> str:
        text = text.strip()
        if max_chars is None or len(text) <= max_chars:
            return text

        suffix = "Risposta sintetizzata per Telegram. Scrivimi 'approfondisci' per la versione completa."
        suffix = self._escape_html(suffix) if markdown else suffix
        available = max_chars - len(suffix) - 4
        truncated = text[:available].rstrip()
        last_break = max(truncated.rfind("\n\n"), truncated.rfind(". "), truncated.rfind("\n"))
        if last_break > available * 0.55:
            truncated = truncated[:last_break].rstrip()
        return f"{truncated}\n\n{suffix}"
